"""多 Agent 运行时：命名空间隔离、幂等、trace 传播与熔断。

它把"每个 Agent 各自接一条链路"变成"所有 Agent 走同一个判定入口"：

    Agent Runtime → Adapter → AgentRuntime.handle → Policy Engine
                            → Executor（仅 allow 时，至多一次）
                            → Adapter.to_agent_response → Agent Runtime

核心层没有新增任何 Agent 专用分支：这里只调用 `policy.engine.evaluate` 与
`enforcement` 的审计端口，Agent 之间的差异全部留在 Adapter 与能力声明里。

隔离的四条硬规则（计划 §5 / §多 Agent 安全测试）：

1. **命名空间**：审计与幂等台账的键是 `<adapter.namespace>:<event_id>`。
   Agent A 的 event_id 不会命中 Agent B 的记录，A 的判定也不会替 B 放行；
2. **审批**：写入台账的审批结论带 `agent` 字段，读取时逐条比对——
   A 的审批不能用于 B，即使两侧的 action_hash 恰好相同；
3. **trace**：trace 登记表记录 `owner_agent`。伪造父 trace（引用别的 Agent 的
   trace，或引用不存在的 trace）一律拒绝，不做"宽容处理"；
4. **熔断**：同一个 `request_id` 下的受治理事件数超过上限即阻断。
   两个 Agent 互相发消息触发的无限循环必须能被终止，而不是把预算烧完。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Tuple

from policy.evidence import EvidenceBundle
from policy.engine import EngineError, evaluate
from policy.models import (
    SCHEMA_VERSION,
    Decision,
    Operation,
    PolicyContextError,
    RuleSet,
    ValidationResult,
)
from policy.loader import LoaderError

from .base import Adapter, AdapterRegistry, RegistryError
from .models import (
    AdapterEventError,
    AgentEvent,
    AgentResponse,
    EnforcementLevel,
    EventType,
    ResponseKind,
)

__all__ = [
    "AGENT_RUNTIME_SCHEMA_VERSION",
    "DEFAULT_BREAKER_LIMIT",
    "DEFAULT_WINDOW_SECONDS",
    "REASON_CODES",
    "AgentRuntime",
    "PolicyTimeout",
    "RuntimeLedgerError",
    "RuntimeOutcome",
    "TraceRegistry",
    "sanitize_message",
]

AGENT_RUNTIME_SCHEMA_VERSION = "1.0"
DEFAULT_BREAKER_LIMIT = 50
DEFAULT_WINDOW_SECONDS = 60

# 面向 Agent 的受控原因码。Adapter 只能从这里取，不能自己编——
# 否则"错误响应能被 Agent 理解"就退化成每个 Adapter 各说各话。
REASON_CODES: Mapping[str, str] = {
    "allow": "动作已获批准，可以执行一次",
    "allow_with_warnings": "动作已获批准（有警告），可以执行一次",
    "policy_block": "策略判定为阻断",
    "policy_timeout": "策略判定超时，按失败策略阻断",
    "engine_error": "策略引擎不可用，按失败策略阻断",
    "context_error": "上下文缺失或不合法（安全关键字段不得猜测）",
    "unknown_event": "事件类型不被该 Adapter 的能力声明支持",
    "unknown_version": "协议版本不受支持",
    "unknown_tool": "工具不在该 Agent 的工具表里",
    "capability_unavailable": "该 Agent 不具备强制阻断能力，无法治理此类动作",
    "evidence_unavailable": "验证器证据链未接入，受治理写入按失败策略阻断",
    "enforcement_unavailable": "Phase 4 受控执行链未接入，受治理写入按失败策略阻断",
    "enforcement_block": "Phase 4 受控执行前检查未通过",
    "postcheck_unavailable": "Phase 4 事后验证不可用，按失败策略阻断",
    "postcheck_failed": "Phase 4 事后验证要求修复或发现不一致",
    "postcheck_validated": "Phase 4 事后验证通过",
    "trace_forged": "trace 来源无法验证（自称的父 trace 不属于本 Agent）",
    "event_replay": "该事件已判定过：为避免重复执行，重放一律阻断",
    "event_id_reuse": "同一事件标识被复用到了不同参数：标识不再可信",
    "request_busy": "同一请求的受治理事件数超过上限（疑似互相触发的循环），已阻断",
    "ledger_unavailable": "运行时台账不可读或不可写，按失败策略阻断",
    "execution_failed": "工具执行失败，按失败策略阻断",
    "internal_error": "适配层内部错误，按失败策略阻断",
}

_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()

# 脱敏模式：只描述"确定形态"的内部信息（绝对路径、密钥样式）。
#
# 反斜杠刻意不写成字面量：正则里成对的反斜杠（字符类里的转义反斜杠）既难读，
# 也容易在改动里被转义层吃掉；这里用字符码构造，模式反而稳定可读。
_BSLASH = chr(92)
_QUOTE = chr(34)
_SQUOTE = chr(39)

_WIN_PREFIX = _BSLASH + _BSLASH + "|[A-Za-z]:[" + _BSLASH + "/]|/"
_PATH_RE = re.compile(
    "(?:" + _WIN_PREFIX + ")" + "[^ " + _QUOTE + _SQUOTE + "]+"
    + "|(?:/)[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+"
)
_SECRET_RE = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9_-]{8,}|bearer\s+\S+|api[_-]?key\s*[=:]\s*\S+)"
)


@dataclass(frozen=True)
class RuntimeOutcome:
    """一次 `handle` 的完整结果，可直接序列化进审计。"""

    response: AgentResponse
    outcome_code: str
    event: Optional[AgentEvent] = None
    decision: Optional[ValidationResult] = None
    delegated: bool = False
    elapsed_ms: int = 0
    detail: str = ""


class PolicyTimeout(Exception):
    """策略判定超出内部预算：按失败策略阻断。"""


class RuntimeLedgerError(Exception):
    """运行时幂等台账不可验证：受治理事件必须失败关闭。"""


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve()).casefold()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _process_file_lock(path: Path) -> Iterator[None]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+b")
        if handle.seek(0, 2) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
    except OSError as error:
        raise RuntimeLedgerError(f"台账锁不可用: {path.name}（{error}）") from error

    try:
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + 5
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise RuntimeLedgerError(f"台账锁超时: {path.name}") from error
                    time.sleep(0.01)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def sanitize_message(text: str, *, limit: int = 400) -> str:
    """把内部错误文本压成一行、去掉绝对路径与密钥样式。

    返回给 Agent 的内容必须**足够短且不含内部信息**：Agent 需要知道
    "被拒绝了、原因码是什么、怎么修"，不需要知道本机路径或规则库细节。
    """

    import re

    if not isinstance(text, str):
        text = str(text)
    collapsed = " ".join(text.split())
    collapsed = _PATH_RE.sub("<path>", collapsed)
    collapsed = _SECRET_RE.sub("<redacted>", collapsed)
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 3] + "..."
    return collapsed


def _utc_now() -> str:
    import datetime as clock

    return clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class TraceRegistry:
    """trace 登记表：谁能声明哪条 trace。

    只用**摘要**：记 `trace_id`、`owner_agent`、`parent_trace_id` 与请求标识，
    不记事件内容。伪造父 trace（引用他人或引用不存在的 trace）在这里被拒绝。
    """

    def __init__(self, path: Optional[Path | str] = None) -> None:
        self.path = None if path is None else Path(path)
        self._lock = threading.RLock()

    @contextmanager
    def _guard(self) -> Iterator[None]:
        if self.path is None:
            with self._lock:
                yield
            return
        with _path_lock(self.path):
            lock_path = self.path.with_name(self.path.name + ".lock")
            with _process_file_lock(lock_path):
                yield

    def _entries_unlocked(self) -> list[dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return []
        if not self.path.is_file():
            raise RuntimeLedgerError(f"trace 登记表不是文件: {self.path.name}")
        records: list[dict[str, Any]] = []
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise RuntimeLedgerError(
                f"trace 登记表不可读: {self.path.name}（{error}）"
            ) from error
        allowed = {
            "trace_schema_version",
            "trace_id",
            "owner_agent",
            "parent_trace_id",
            "request_id",
        }
        for line_number, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeLedgerError(
                    f"trace 登记表第 {line_number} 行不是合法 JSON"
                ) from error
            if not isinstance(item, dict):
                raise RuntimeLedgerError(
                    f"trace 登记表第 {line_number} 行必须是对象"
                )
            if item.get("trace_schema_version") != AGENT_RUNTIME_SCHEMA_VERSION:
                raise RuntimeLedgerError(
                    f"trace 登记表第 {line_number} 行协议版本未知或缺失"
                )
            unknown = sorted(set(item) - allowed)
            if unknown:
                raise RuntimeLedgerError(
                    f"trace 登记表第 {line_number} 行出现未知字段 {unknown}"
                )
            for field in ("trace_id", "owner_agent"):
                value = item.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise RuntimeLedgerError(
                        f"trace 登记表第 {line_number} 行的 {field} 必须是非空字符串"
                    )
            parent = item.get("parent_trace_id")
            if parent is not None and (
                not isinstance(parent, str) or not parent.strip()
            ):
                raise RuntimeLedgerError(
                    f"trace 登记表第 {line_number} 行的 parent_trace_id 非法"
                )
            if not isinstance(item.get("request_id"), str):
                raise RuntimeLedgerError(
                    f"trace 登记表第 {line_number} 行的 request_id 必须是字符串"
                )
            records.append(item)
        return records

    def _entries(self) -> list[dict[str, Any]]:
        with self._guard():
            return self._entries_unlocked()

    @staticmethod
    def _owner(entries: list[dict[str, Any]], trace_id: str) -> Optional[str]:
        for item in reversed(entries):
            if item["trace_id"] == trace_id:
                return str(item["owner_agent"])
        return None

    def owner(self, trace_id: str) -> Optional[str]:
        return self._owner(self._entries(), trace_id)

    def known(self, trace_id: str) -> bool:
        return any(item.get("trace_id") == trace_id for item in self._entries())

    def register(
        self,
        *,
        trace_id: str,
        owner_agent: str,
        parent_trace_id: Optional[str] = None,
        request_id: str = "",
    ) -> None:
        if self.path is None:
            return
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise RuntimeLedgerError("trace_id 必须是非空字符串")
        if not isinstance(owner_agent, str) or not owner_agent.strip():
            raise RuntimeLedgerError("owner_agent 必须是非空字符串")
        if parent_trace_id is not None and (
            not isinstance(parent_trace_id, str) or not parent_trace_id.strip()
        ):
            raise RuntimeLedgerError("parent_trace_id 必须是非空字符串或 null")
        if not isinstance(request_id, str):
            raise RuntimeLedgerError("request_id 必须是字符串")
        record = {
            "trace_schema_version": AGENT_RUNTIME_SCHEMA_VERSION,
            "trace_id": trace_id.strip(),
            "owner_agent": owner_agent.strip(),
            "parent_trace_id": None if parent_trace_id is None else parent_trace_id.strip(),
            "request_id": request_id,
        }
        with self._guard():
            for existing in self._entries_unlocked():
                if existing["trace_id"] != record["trace_id"]:
                    continue
                if existing == record:
                    return
                raise RuntimeLedgerError(
                    f"trace {record['trace_id']!r} 已登记且绑定信息不同；"
                    "trace 所有权与父链不可覆盖"
                )
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(
                        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                    )
                    handle.flush()
            except OSError as error:
                raise RuntimeLedgerError(
                    f"trace 登记表不可写: {self.path.name}（{error}）"
                ) from error

    def check(
        self,
        *,
        agent_id: str,
        trace_id: Optional[str],
        parent_trace_id: Optional[str],
    ) -> str:
        """校验自称的 trace 来源；返回空串表示通过，否则返回拒绝原因。"""

        entries = self._entries()
        for candidate, label in ((parent_trace_id, "父 trace"), (trace_id, "trace")):
            if candidate is None:
                continue
            owner = self._owner(entries, candidate)
            if owner is not None and owner != agent_id:
                return (
                    f"{label} {candidate!r} 属于 Agent {owner!r}："
                    "伪造父 trace 会让来源不可验证，拒绝"
                )
        if parent_trace_id is not None and not any(
            item["trace_id"] == parent_trace_id for item in entries
        ):
            return (
                f"父 trace {parent_trace_id!r} 不在 trace 登记表里："
                "引用一条从未发放过的 trace 等于伪造来源，拒绝"
            )
        return ""


def _agreed_value(values: Mapping[str, int], field: str) -> int:
    """多个 Adapter 对同一个阈值必须**全体一致**，分歧一律报错。

    取 min 会让"某个 Agent 放宽了阈值"变成静默生效；取 max 则相反。
    两种都不是调用方能预测的行为，而 AGENTS 核心约束 3 要求"冲突不得静默忽略"。
    """

    distinct = set(values.values())
    if len(distinct) > 1:
        detail = "、".join(f"{agent_id}={value}" for agent_id, value in sorted(values.items()))
        raise RegistryError(
            f"多个 Adapter 声明的 {field} 不一致：{detail}；"
            "同一运行时只解析一个阈值，分歧必须显式解决"
        )
    return next(iter(distinct))


def _resolve_thresholds(
    adapters: Mapping[str, Adapter],
    breaker_limit: Optional[int],
    window_seconds: Optional[int],
) -> tuple[int, int]:
    """熔断阈值三级优先：**显式参数 > adapter 配置（全体一致）> 模块常数**。

    `adapters/<agent_id>/adapter.yaml` 早就声明了 `max_events_per_window` / `window_seconds`，
    但在这次接线之前**没有任何读取点**——声明了却不执行，等于这条约束不存在，
    而且"改配置能调阈值"是一句空话。显式参数优先是为了让一致性套件 / 测试 / 闭环
    能刻意把阈值调小（它们要证明的是"熔断真的会发生"）。

    两个维度**各自**判定一致性：只消费 `window_seconds` 时不去管别处的
    `max_events_per_window` 是否一致，否则显式传了阈值也会被无关分歧绊倒。

    注意（已知复核边界）：`adapter.yaml` **不在** `approved.json` 的已审核哈希范围内
    （那只覆盖 `manifest.yaml`），因此改这里的阈值不需要重新审核。
    """

    if breaker_limit is not None and window_seconds is not None:
        return breaker_limit, window_seconds

    limits: dict[str, int] = {}
    windows: dict[str, int] = {}
    for agent_id, adapter in adapters.items():
        config = getattr(adapter, "config", None)
        if config is None:
            raise RegistryError(
                f"Adapter {agent_id!r} 缺少能力声明配置（config）：无法解析熔断阈值"
            )
        limits[agent_id] = (
            DEFAULT_BREAKER_LIMIT
            if config.max_events_per_window is None
            else config.max_events_per_window
        )
        windows[agent_id] = (
            DEFAULT_WINDOW_SECONDS if config.window_seconds is None else config.window_seconds
        )

    if breaker_limit is None:
        breaker_limit = _agreed_value(limits, "max_events_per_window")
    if window_seconds is None:
        window_seconds = _agreed_value(windows, "window_seconds")
    return breaker_limit, window_seconds


class AgentRuntime:
    """多 Agent 的公共判定入口。

    `ledger_path` 是本运行时的审计与幂等台账（追加写 JSONL）。没有配置它时，
    幂等与 trace 校验退化为**进程内**状态——这依然是被测行为的一部分，
    但生产接线必须给一个路径，否则"重复 event_id 不得执行两次"跨进程就不成立。
    """

    def __init__(
        self,
        *,
        adapters: Mapping[str, Adapter],
        rules: RuleSet,
        registry: Optional[AdapterRegistry] = None,
        ledger_path: Optional[Path | str] = None,
        trace_path: Optional[Path | str] = None,
        workspace: Optional[Path | str] = None,
        breaker_limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
        clock_time: Optional[Callable[[], str]] = None,
        evaluator: Callable[[RuleSet, Any], ValidationResult] = evaluate,
        clock: Callable[[], float] = time.monotonic,
        enforcers: Optional[Mapping[str, Any]] = None,
        evidence_providers: Optional[
            Mapping[str, Callable[[AgentEvent, Any], EvidenceBundle]]
        ] = None,
    ) -> None:
        if not adapters:
            raise RegistryError("AgentRuntime 至少需要一个 Adapter")
        # 阈值先解析再校验：下面这几行拿到的永远是 int，None 不会漏到 725 行的比较里。
        breaker_limit, window_seconds = _resolve_thresholds(adapters, breaker_limit, window_seconds)
        if breaker_limit <= 0:
            raise RegistryError("breaker_limit 必须是正整数")
        # window_seconds 此前没有下限校验：0 或负数会让 _window_events 恒返回 0，
        # 熔断永远不触发（fail-open）。它必须和 breaker_limit 一样在构造期就失败。
        if window_seconds <= 0:
            raise RegistryError("window_seconds 必须是正整数")
        self.adapters = dict(adapters)
        self.rules = rules
        self.registry = registry
        self.ledger_path = None if ledger_path is None else Path(ledger_path)
        self.trace = TraceRegistry(trace_path)
        # 受控工作区：范围校验（越界即拒绝）永远相对真正被执行的那一份。
        # 覆盖 adapter 配置里的默认值，是同一个 Adapter 指向另一份工作区的唯一入口。
        self.workspace = None if workspace is None else Path(workspace).resolve()
        self.breaker_limit = breaker_limit
        self.window_seconds = window_seconds
        self.clock_time = clock_time or _utc_now
        self.evaluator = evaluator
        self.clock = clock
        self.enforcers = dict(enforcers or {})
        self.evidence_providers = dict(evidence_providers or {})
        self._memory: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ 台账
    @contextmanager
    def _ledger_guard(self) -> Iterator[None]:
        if self.ledger_path is None:
            with self._lock:
                yield
            return
        with _path_lock(self.ledger_path):
            lock_path = self.ledger_path.with_name(self.ledger_path.name + ".lock")
            with _process_file_lock(lock_path):
                yield

    def _read_entries_unlocked(self) -> list[dict[str, Any]]:
        if self.ledger_path is None:
            return [dict(item) for item in self._memory]
        if not self.ledger_path.exists():
            return []
        if not self.ledger_path.is_file():
            raise RuntimeLedgerError(f"运行时台账不是文件: {self.ledger_path.name}")
        try:
            text = self.ledger_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise RuntimeLedgerError(
                f"运行时台账不可读: {self.ledger_path.name}（{error}）"
            ) from error
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeLedgerError(
                    f"运行时台账第 {line_number} 行不是合法 JSON"
                ) from error
            if not isinstance(item, dict):
                raise RuntimeLedgerError(f"运行时台账第 {line_number} 行必须是对象")
            if item.get("runtime_schema_version") != AGENT_RUNTIME_SCHEMA_VERSION:
                raise RuntimeLedgerError(
                    f"运行时台账第 {line_number} 行协议版本未知或缺失"
                )
            records.append(item)
        return records

    def _entries(self) -> list[dict[str, Any]]:
        with self._ledger_guard():
            return self._read_entries_unlocked()

    def _append_unlocked(self, record: Mapping[str, Any]) -> None:
        payload = dict(record)
        try:
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise RuntimeLedgerError("运行时台账记录无法序列化") from error
        if self.ledger_path is None:
            self._memory.append(payload)
            return
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
                handle.flush()
        except OSError as error:
            raise RuntimeLedgerError(
                f"运行时台账不可写: {self.ledger_path.name}（{error}）"
            ) from error

    def _append(self, record: Mapping[str, Any]) -> None:
        with self._ledger_guard():
            self._append_unlocked(record)

    @staticmethod
    def ledger_key(namespace: str, event_id: str) -> str:
        """命名空间键：Agent A 的事件永远不会命中 Agent B 的记录。"""

        return f"{namespace}:{event_id}"

    def history_for(self, agent_id: str) -> Tuple[Mapping[str, Any], ...]:
        """某个 Agent 自己的历史（跨 Agent 隔离的最直接证据）。"""

        return tuple(
            item for item in self._entries() if item.get("agent") == agent_id
        )

    def lookup(self, agent_id: str, event_id: str) -> Optional[Mapping[str, Any]]:
        adapter = self.adapters.get(agent_id)
        namespace = agent_id if adapter is None else adapter.namespace
        key = self.ledger_key(namespace, event_id)
        found: Optional[Mapping[str, Any]] = None
        for item in self._entries():
            if item.get("ledger_key") == key:
                found = item
        return found

    def _claim(self, adapter: Adapter, event: AgentEvent) -> Optional[Mapping[str, Any]]:
        key = self.ledger_key(adapter.namespace, event.event_id)
        with self._ledger_guard():
            for item in reversed(self._read_entries_unlocked()):
                if (
                    item.get("kind") == "claim"
                    and
                    item.get("ledger_key") == key
                    and item.get("event_type") == event.event_type.value
                ):
                    return item
            self._append_unlocked(
                {
                    "runtime_schema_version": AGENT_RUNTIME_SCHEMA_VERSION,
                    "kind": "claim",
                    "agent": adapter.agent_id,
                    "namespace": adapter.namespace,
                    "ledger_key": key,
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "request_id": event.request_id,
                    "payload_digest": event.payload_digest,
                    "recorded_at": self.clock_time(),
                }
            )
        return None

    def _window_events(self, agent_id: str) -> int:
        """本 Agent 在最近 window_seconds 秒内的受治理事件数（熔断计数）。"""

        now = _parse_time(self.clock_time())
        if now is None:
            # 时间不可读：窗口算不出来就按全部历史计数——宁可早熔断，
            # 也不能因为时钟问题让循环失去上限。
            return sum(
                1
                for item in self._entries()
                if item.get("agent") == agent_id and item.get("kind") in (None, "claim")
            )
        count = 0
        for item in self._entries():
            if item.get("agent") != agent_id or item.get("kind") not in (None, "claim"):
                continue
            recorded = _parse_time(str(item.get("recorded_at") or ""))
            if recorded is None or (now - recorded).total_seconds() <= self.window_seconds:
                count += 1
        return count

    # ------------------------------------------------------------------ 判定
    def handle(
        self,
        agent_id: str,
        raw_event: Any,
        *,
        execute: Optional[Callable[[AgentEvent], Any]] = None,
        execute_on_allow: bool = True,
    ) -> RuntimeOutcome:
        """处理一条原始事件：判定、执行（至多一次）、翻译回 Agent 响应。

        任何异常路径都返回**阻断**响应，绝不抛给 Agent 运行时：
        Agent 侧看到异常会自己决定怎么处理，那等于把失败关闭交给了外部。
        """

        started = self.clock()
        try:
            return self._handle(
                agent_id,
                raw_event,
                execute=execute,
                execute_on_allow=execute_on_allow,
                started=started,
            )
        except RuntimeLedgerError as error:
            return self._refuse(
                agent_id=agent_id,
                request_id="",
                event_id="",
                code="ledger_unavailable",
                detail=sanitize_message(str(error)),
                started=started,
            )
        except Exception as error:  # noqa: BLE001 - Adapter 边界必须把异常收敛成阻断响应
            return self._refuse(
                agent_id=agent_id,
                request_id="",
                event_id="",
                code="internal_error",
                detail=sanitize_message(f"{type(error).__name__}: {error}"),
                started=started,
            )

    def _handle(
        self,
        agent_id: str,
        raw_event: Any,
        *,
        execute: Optional[Callable[[AgentEvent], Any]],
        execute_on_allow: bool,
        started: float,
    ) -> RuntimeOutcome:
        adapter = self.adapters.get(agent_id)
        if adapter is None:
            return self._refuse(
                agent_id=agent_id,
                request_id="",
                event_id="",
                code="capability_unavailable",
                detail=f"Agent {agent_id!r} 没有接入 adapter：没有能力声明就没有治理",
                started=started,
            )

        # 先做与 Adapter 无关的预检：能力上限、版本、拒绝的工具。
        try:
            event = adapter.to_policy_event(raw_event, workspace=self.workspace)
        except AdapterEventError as error:
            return self._adapt_failure(agent_id, error, started=started)

        response_kind = adapter.manifest.response_kind
        if not event.decision_requested:
            # 只记录不判定的事件（agent.start / agent.message / …）。
            self._append(
                {
                    "runtime_schema_version": AGENT_RUNTIME_SCHEMA_VERSION,
                    "agent": agent_id,
                    "agent_version": adapter.agent_version,
                    "kind": "recorded",
                    "namespace": adapter.namespace,
                    "ledger_key": self.ledger_key(adapter.namespace, event.event_id),
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "request_id": event.request_id,
                    "trace_id": event.trace_id,
                    "payload_digest": event.payload_digest,
                    "recorded_at": self.clock_time(),
                    "recorded": True,
                }
            )
            response = self._response(
                agent_id=agent_id,
                event=event,
                decision=Decision.ALLOW,
                code="allow",
                detail="该事件只登记，不参与判定",
                response_kind=response_kind,
                native=None,
            )
            return RuntimeOutcome(
                response=response,
                outcome_code="recorded",
                event=event,
                elapsed_ms=int((self.clock() - started) * 1000),
            )

        # trace 来源校验：伪造父 trace 在这里被拒绝，而不是留给下游猜。
        trace_issue = self.trace.check(
            agent_id=agent_id,
            trace_id=event.trace_id,
            parent_trace_id=event.parent_trace_id,
        )
        if trace_issue:
            return self._refuse(
                agent_id=agent_id,
                request_id=event.request_id,
                event_id=event.event_id,
                code="trace_forged",
                detail=trace_issue,
                started=started,
                event=event,
                response_kind=response_kind,
            )

        # 熔断：Agent 之间互相触发的循环必须能被终止。
        # 计数口径是本 Agent 在窗口内的受治理事件数——循环里的 request_id
        # 每次都可能是新的，按请求计数永远数不到上限（这是实测出来的坑）。
        if self._window_events(agent_id) >= self.breaker_limit:
            self._record(event, adapter, decision=Decision.BLOCK, code="request_busy", executed=False)
            return self._refuse(
                agent_id=agent_id,
                request_id=event.request_id,
                event_id=event.event_id,
                code="request_busy",
                detail=(
                    f"该 Agent 在最近 {self.window_seconds} 秒内已有 "
                    f"{self.breaker_limit} 条受治理事件："
                    "疑似 Agent 之间互相触发的循环，按失败策略终止"
                ),
                started=started,
                event=event,
                response_kind=response_kind,
            )

        # 幂等：同一 event_id 不得导致工具执行两次。
        previous = None if not execute_on_allow else self._claim(adapter, event)
        if previous is not None:
            same_payload = previous.get("payload_digest") == event.payload_digest
            return self._refuse(
                agent_id=agent_id,
                request_id=event.request_id,
                event_id=event.event_id,
                code="event_replay" if same_payload else "event_id_reuse",
                detail=(
                    "该 event_id 已经判定过：为避免重复执行，重放一律阻断"
                    if same_payload
                    else "同一 event_id 被复用到了不同参数：事件标识不再可信"
                ),
                started=started,
                event=event,
                response_kind=response_kind,
            )

        try:
            context = adapter.to_policy_context(event, workspace=self.workspace)
        except (AdapterEventError, PolicyContextError) as error:
            self._record(event, adapter, decision=Decision.BLOCK, code="context_error", executed=False)
            return self._refuse(
                agent_id=agent_id,
                request_id=event.request_id,
                event_id=event.event_id,
                code="context_error",
                detail=sanitize_message(str(error)),
                started=started,
                event=event,
                response_kind=response_kind,
            )

        # 顺序很重要：主体核对（构上下文）先于能力门禁。写错主体的请求应当是
        # "上下文错误"，而不是被能力上限掩盖成"能力不足"——前者能修，后者只能换 Agent。
        gate = self._capability_gate(adapter, event)
        if gate is not None:
            self._record(event, adapter, decision=Decision.BLOCK, code=gate[0], executed=False)
            return self._refuse(
                agent_id=agent_id,
                request_id=event.request_id,
                event_id=event.event_id,
                code=gate[0],
                detail=gate[1],
                started=started,
                event=event,
                response_kind=response_kind,
            )

        evidence: Optional[EvidenceBundle] = None
        if self._is_mutating(adapter, event):
            provider = self._component(self.evidence_providers, adapter)
            if provider is None:
                self._record(
                    event,
                    adapter,
                    decision=Decision.BLOCK,
                    code="evidence_unavailable",
                    executed=False,
                )
                return self._refuse(
                    agent_id=agent_id,
                    request_id=event.request_id,
                    event_id=event.event_id,
                    code="evidence_unavailable",
                    detail=(
                        "受治理写入没有配置 Phase 5 evidence provider；"
                        "缺少验证器证据时不能把跳过的规则当作通过"
                    ),
                    started=started,
                    event=event,
                    response_kind=response_kind,
                )
            try:
                evidence = provider(event, context)
            except Exception as error:  # noqa: BLE001 - 证据链异常必须失败关闭
                self._record(
                    event,
                    adapter,
                    decision=Decision.BLOCK,
                    code="evidence_unavailable",
                    executed=False,
                )
                return self._refuse(
                    agent_id=agent_id,
                    request_id=event.request_id,
                    event_id=event.event_id,
                    code="evidence_unavailable",
                    detail=sanitize_message(f"{type(error).__name__}: {error}"),
                    started=started,
                    event=event,
                    response_kind=response_kind,
                )
            if not isinstance(evidence, EvidenceBundle):
                self._record(
                    event,
                    adapter,
                    decision=Decision.BLOCK,
                    code="evidence_unavailable",
                    executed=False,
                )
                return self._refuse(
                    agent_id=agent_id,
                    request_id=event.request_id,
                    event_id=event.event_id,
                    code="evidence_unavailable",
                    detail="evidence provider 必须返回 EvidenceBundle",
                    started=started,
                    event=event,
                    response_kind=response_kind,
                )

        try:
            decision = self._evaluate(context, adapter, evidence=evidence)
        except PolicyTimeout as error:
            self._record(event, adapter, decision=Decision.BLOCK, code="policy_timeout", executed=False)
            return self._refuse(
                agent_id=agent_id,
                request_id=event.request_id,
                event_id=event.event_id,
                code="policy_timeout",
                detail=str(error),
                started=started,
                event=event,
                response_kind=response_kind,
            )
        except (EngineError, LoaderError) as error:
            self._record(event, adapter, decision=Decision.BLOCK, code="engine_error", executed=False)
            return self._refuse(
                agent_id=agent_id,
                request_id=event.request_id,
                event_id=event.event_id,
                code="engine_error",
                detail=sanitize_message(str(error)),
                started=started,
                event=event,
                response_kind=response_kind,
            )
        except BaseException as error:  # noqa: BLE001 - evaluator 的任意异常都必须失败关闭
            self._record(event, adapter, decision=Decision.BLOCK, code="engine_error", executed=False)
            return self._refuse(
                agent_id=agent_id,
                request_id=event.request_id,
                event_id=event.event_id,
                code="engine_error",
                detail=sanitize_message(f"{type(error).__name__}: {error}"),
                started=started,
                event=event,
                response_kind=response_kind,
            )

        if decision.decision is Decision.BLOCK:
            code = "policy_block"
            self._record(event, adapter, decision=Decision.BLOCK, code=code, executed=False)
            response = self._response(
                agent_id=agent_id,
                event=event,
                decision=Decision.BLOCK,
                code=code,
                detail="",
                response_kind=response_kind,
                native=None,
                result=decision,
            )
            return RuntimeOutcome(
                response=response,
                outcome_code=code,
                event=event,
                decision=decision,
                elapsed_ms=int((self.clock() - started) * 1000),
            )

        if self._is_mutating(adapter, event):
            enforcer = self._component(self.enforcers, adapter)
            if enforcer is None:
                self._record(
                    event,
                    adapter,
                    decision=Decision.BLOCK,
                    code="enforcement_unavailable",
                    executed=False,
                )
                return self._refuse(
                    agent_id=agent_id,
                    request_id=event.request_id,
                    event_id=event.event_id,
                    code="enforcement_unavailable",
                    detail=(
                        "受治理写入没有配置 Phase 4 enforcer；"
                        "Policy allow 不能替代工具注册表、权限、审批与 action_hash"
                    ),
                    started=started,
                    event=event,
                    response_kind=response_kind,
                )
            if event.event_type is EventType.TOOL_POST_EXECUTE:
                try:
                    postcheck = enforcer.post(raw_event)
                except Exception as error:  # noqa: BLE001 - 事后验证失效必须显式阻断
                    self._record(
                        event,
                        adapter,
                        decision=Decision.BLOCK,
                        code="postcheck_unavailable",
                        executed=False,
                    )
                    return self._refuse(
                        agent_id=agent_id,
                        request_id=event.request_id,
                        event_id=event.event_id,
                        code="postcheck_unavailable",
                        detail=sanitize_message(f"{type(error).__name__}: {error}"),
                        started=started,
                        event=event,
                        response_kind=response_kind,
                    )
                if postcheck is None:
                    self._record(
                        event,
                        adapter,
                        decision=Decision.BLOCK,
                        code="postcheck_unavailable",
                        executed=False,
                    )
                    return self._refuse(
                        agent_id=agent_id,
                        request_id=event.request_id,
                        event_id=event.event_id,
                        code="postcheck_unavailable",
                        detail="事后事件没有对应的执行前状态或验证结果",
                        started=started,
                        event=event,
                        response_kind=response_kind,
                    )
                if postcheck.status.value != "validated":
                    self._record(
                        event,
                        adapter,
                        decision=Decision.BLOCK,
                        code="postcheck_failed",
                        executed=False,
                    )
                    return self._refuse(
                        agent_id=agent_id,
                        request_id=event.request_id,
                        event_id=event.event_id,
                        code="postcheck_failed",
                        detail=f"事后验证状态：{postcheck.status.value}",
                        started=started,
                        event=event,
                        response_kind=response_kind,
                    )
                self._record(
                    event,
                    adapter,
                    decision=decision.decision,
                    code="postcheck_validated",
                    executed=False,
                )
                return RuntimeOutcome(
                    response=self._response(
                        agent_id=agent_id,
                        event=event,
                        decision=decision.decision,
                        code="postcheck_validated",
                        detail="",
                        response_kind=response_kind,
                        native=None,
                        result=decision,
                        executed=False,
                    ),
                    outcome_code="postcheck_validated",
                    event=event,
                    decision=decision,
                    delegated=True,
                    elapsed_ms=int((self.clock() - started) * 1000),
                )
            try:
                specification = enforcer.spec_for(event.tool)
                if specification is None:
                    raise RegistryError(f"工具 {event.tool!r} 不在 Phase 4 Tool Registry")
            except Exception as error:  # noqa: BLE001 - 注册表本身失效必须失败关闭
                self._record(
                    event,
                    adapter,
                    decision=Decision.BLOCK,
                    code="enforcement_unavailable",
                    executed=False,
                )
                return self._refuse(
                    agent_id=agent_id,
                    request_id=event.request_id,
                    event_id=event.event_id,
                    code="enforcement_unavailable",
                    detail=sanitize_message(f"{type(error).__name__}: {error}"),
                    started=started,
                    event=event,
                    response_kind=response_kind,
                )
            try:
                principal = context.principal
                request = enforcer.build_request(
                    spec=specification,
                    action_id=event.event_id,
                    request_id=event.request_id,
                    trace_id=event.trace_id,
                    subject=None if principal is None else principal.subject,
                    roles=() if principal is None else tuple(sorted(principal.roles)),
                    params=event.params,
                )
            except Exception as error:  # noqa: BLE001 - 参数不合法是动作阻断，不是平台降级
                self._record(
                    event,
                    adapter,
                    decision=Decision.BLOCK,
                    code="enforcement_block",
                    executed=False,
                )
                return self._refuse(
                    agent_id=agent_id,
                    request_id=event.request_id,
                    event_id=event.event_id,
                    code="enforcement_block",
                    detail=sanitize_message(f"Phase 4 请求无效：{type(error).__name__}: {error}"),
                    started=started,
                    event=event,
                    response_kind=response_kind,
                )
            try:
                precheck = enforcer.pre(
                    request,
                    policy_decision=decision,
                    dry_run=not execute_on_allow,
                )
            except Exception as error:  # noqa: BLE001 - 授权链失效必须失败关闭
                self._record(
                    event,
                    adapter,
                    decision=Decision.BLOCK,
                    code="enforcement_unavailable",
                    executed=False,
                )
                return self._refuse(
                    agent_id=agent_id,
                    request_id=event.request_id,
                    event_id=event.event_id,
                    code="enforcement_unavailable",
                    detail=sanitize_message(f"{type(error).__name__}: {error}"),
                    started=started,
                    event=event,
                    response_kind=response_kind,
                )
            if not precheck.allowed:
                reason = precheck.decision.reason_code.value
                self._record(
                    event,
                    adapter,
                    decision=Decision.BLOCK,
                    code="enforcement_block",
                    executed=False,
                )
                return self._refuse(
                    agent_id=agent_id,
                    request_id=event.request_id,
                    event_id=event.event_id,
                    code="enforcement_block",
                    detail=f"Phase 4 pre-check 阻断：{reason}",
                    started=started,
                    event=event,
                    response_kind=response_kind,
                )

        # allow / allow_with_warnings：执行器**恰好**被调用一次。
        executed = False
        detail = ""
        if execute is not None and execute_on_allow:
            try:
                execute(event)
                executed = True
            except Exception as error:  # noqa: BLE001 - 执行失败也是显式结论
                detail = sanitize_message(f"{type(error).__name__}: {error}")
                self._record(
                    event,
                    adapter,
                    decision=Decision.BLOCK,
                    code="execution_failed",
                    executed=False,
                )
                return RuntimeOutcome(
                    response=self._response(
                        agent_id=agent_id,
                        event=event,
                        decision=Decision.BLOCK,
                        code="execution_failed",
                        detail=detail,
                        response_kind=response_kind,
                        native=None,
                        result=decision,
                        executed=False,
                    ),
                    outcome_code="execution_failed",
                    event=event,
                    decision=decision,
                    elapsed_ms=int((self.clock() - started) * 1000),
                    detail=detail,
                )
        elif not execute_on_allow:
            detail = "调用方要求不执行（只判定）"
        else:
            detail = "由 Agent 运行时执行"

        code = (
            "allow_with_warnings"
            if decision.decision is Decision.ALLOW_WITH_WARNINGS
            else "allow"
        )
        self._record(event, adapter, decision=decision.decision, code=code, executed=executed)
        response = self._response(
            agent_id=agent_id,
            event=event,
            decision=decision.decision,
            code=code,
            detail=detail,
            response_kind=response_kind,
            native=None,
            result=decision,
            executed=executed,
        )
        return RuntimeOutcome(
            response=response,
            outcome_code=code,
            event=event,
            decision=decision,
            delegated=not executed,
            elapsed_ms=int((self.clock() - started) * 1000),
            detail=detail,
        )

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _component(components: Mapping[str, Any], adapter: Adapter) -> Any:
        return components.get(adapter.namespace) or components.get(adapter.agent_id)

    @staticmethod
    def _is_mutating(adapter: Adapter, event: AgentEvent) -> bool:
        specification = None if event.tool is None else adapter.tools.get(event.tool)
        operation = adapter.canonical_operation(event)
        return specification is not None and (
            (operation is not None and operation is not Operation.READ)
            or (operation is None and specification.direction.value == "outbound")
        )

    def _capability_gate(self, adapter: Adapter, event: AgentEvent) -> Optional[tuple[str, str]]:
        """能力不足时的显式拒绝（不是"跳过治理"）。"""

        mutating = self._is_mutating(adapter, event)
        if not mutating:
            # 只读动作不需要"执行前阻断"：判定与记录本身就是治理。
            return None
        if event.event_type is EventType.TOOL_PRE_EXECUTE:
            # 执行前事件：这次判定本身就是"能不能做"的门禁。
            pass
        # 无论上游给的是执行前还是执行后事件，"某个 Agent 在治理写类动作"这件事
        # 都要求它有执行前阻断能力：只拿到事后事件时，副作用已经发生，
        # 平台能做的只是判定与记录——那不是 enforcement，必须说出来。
        if adapter.ceiling.level is EnforcementLevel.FULL:
            # 完整 enforcement：能力足够，交给判定与受控执行链路。
            return None
        if adapter.manifest.blocking.value == "post_only":
            return (
                "capability_unavailable",
                f"Agent {adapter.agent_id} 只有事后钩子：副作用已经产生才能标错，"
                "不能作为执行前阻断；该 Agent 的上限是只读，写类动作一律拒绝",
            )
        return (
            "capability_unavailable",
            f"Agent {adapter.agent_id} 不具备执行前阻断能力"
            f"（blocking={adapter.manifest.blocking.value}）："
            "平台不得把它标记为完整 enforcement，受治理动作在这里显式拒绝",
        )

    def _evaluate(
        self,
        context: Any,
        adapter: Adapter,
        *,
        evidence: Optional[EvidenceBundle] = None,
    ) -> ValidationResult:
        budget_ms = adapter.config.timeout_ms
        box: dict[str, Any] = {}

        def run() -> None:
            try:
                if evidence is None:
                    box["result"] = self.evaluator(self.rules, context)
                else:
                    box["result"] = self.evaluator(self.rules, context, evidence=evidence)
            except BaseException as error:  # noqa: BLE001 - 任何异常都必须回到调用方
                box["error"] = error

        worker = threading.Thread(target=run, name="agent-policy-evaluate", daemon=True)
        worker.start()
        worker.join(budget_ms / 1000)
        if worker.is_alive():
            raise PolicyTimeout(f"策略判定超过内部预算 {budget_ms} ms")
        error = box.get("error")
        if error is not None:
            raise error
        return box["result"]

    def _record(
        self,
        event: AgentEvent,
        adapter: Adapter,
        *,
        decision: Decision,
        code: str,
        executed: bool,
    ) -> None:
        self._append(
            {
                "runtime_schema_version": AGENT_RUNTIME_SCHEMA_VERSION,
                "kind": "final",
                "agent": adapter.agent_id,
                "namespace": adapter.namespace,
                "agent_version": adapter.agent_version,
                "ledger_key": self.ledger_key(adapter.namespace, event.event_id),
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "request_id": event.request_id,
                "trace_id": event.trace_id,
                "parent_trace_id": event.parent_trace_id,
                "tool": event.tool,
                "operation": None if event.operation is None else event.operation.value,
                "payload_digest": event.payload_digest,
                "decision": decision.value,
                "reason_code": code,
                "executed": executed,
                "recorded_at": self.clock_time(),
                "rule_set_hash": self.rules.identity,
            }
        )

    def _response(
        self,
        *,
        agent_id: str,
        event: Optional[AgentEvent],
        decision: Decision,
        code: str,
        detail: str,
        response_kind: ResponseKind,
        native: Optional[str],
        result: Optional[ValidationResult] = None,
        executed: bool = False,
    ) -> AgentResponse:
        event_id = "" if event is None else event.event_id
        request_id = "" if event is None else event.request_id
        return AgentResponse(
            agent_id=agent_id,
            request_id=request_id,
            event_id=event_id,
            decision=decision,
            reason_code=code,
            message=sanitize_message(detail) if detail else REASON_CODES.get(code, ""),
            remediation=(
                ("阅读被阻断的规则并以正确层次重写改动", "不要重试同一动作：先修上下文或改实现")
                if decision is Decision.BLOCK
                else ()
            ),
            required_action=None if result is None else result.required_action,
            violations=(
                ()
                if result is None
                else tuple(item.canonical_id for item in result.violations)
            ),
            matched_rules=() if result is None else tuple(result.matched_rules),
            trace_id=None if event is None else event.trace_id,
            executed=executed,
            response_kind=response_kind,
            native=native,
        )

    def _refuse(
        self,
        *,
        agent_id: str,
        request_id: str,
        event_id: str,
        code: str,
        detail: str,
        started: float,
        event: Optional[AgentEvent] = None,
        response_kind: ResponseKind = ResponseKind.JSON,
    ) -> RuntimeOutcome:
        response = self._response(
            agent_id=agent_id,
            event=event,
            decision=Decision.BLOCK,
            code=code,
            detail=detail,
            response_kind=response_kind,
            native=None,
        )
        if event is None:
            object.__setattr__(response, "request_id", request_id)
            object.__setattr__(response, "event_id", event_id)
        return RuntimeOutcome(
            response=response,
            outcome_code=code,
            event=event,
            elapsed_ms=int((self.clock() - started) * 1000),
            detail=sanitize_message(detail),
        )

    def _adapt_failure(
        self, agent_id: str, error: Exception, *, started: float
    ) -> RuntimeOutcome:
        """把 Adapter 的失败翻译成受控原因码：错误文本不进 Agent 响应正文。"""

        text = sanitize_message(str(error))
        lowered = text.lower()
        if "未知规范事件版本" in text or "版本" in text and "拒绝消费" in text:
            code = "unknown_version"
        elif "未知事件类型" in text or "不支持事件" in text:
            code = "unknown_event"
        elif "未知工具" in text:
            code = "unknown_tool"
        elif "路径" in text or "上下文" in text or "缺少" in text or "主体" in text:
            code = "context_error"
        else:
            code = "context_error" if "context" in lowered else "internal_error"
        return self._refuse(
            agent_id=agent_id,
            request_id="",
            event_id="",
            code=code,
            detail=text,
            started=started,
        )

    def simulate(
        self,
        agent_id: str,
        raw_event: Any,
        *,
        exact_once: bool = True,
    ) -> tuple[RuntimeOutcome, list[AgentEvent]]:
        """一致性套件与闭环工具的入口：记录"工具是否真的被调用"。

        返回 (结果, 被调用的工具调用列表)。`exact_once=True` 时，同一份记录
        作为幂等台账使用——第二次同样的 event_id 会因为重放而被阻断。
        """

        calls: list[AgentEvent] = []

        def execute(event: AgentEvent) -> None:
            calls.append(event)

        outcome = self.handle(
            agent_id,
            raw_event,
            execute=execute,
            execute_on_allow=exact_once,
        )
        return outcome, calls

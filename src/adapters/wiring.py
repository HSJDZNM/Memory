"""Agent 通道清点：把「没接线」变成可观测、可失败的显式状态。

背景（治理根因 R2 / 缺口 G13、G1，见
`docs/project/engineering-policy-platform/reviews/governance-remediation/00-remediation-plan.md`）：

- `adapters.dsh.hooks.check_wiring()` 在 `hooks_config_path is None` 时直接 `return ""`（= 通过）；
- 全仓库没有任何模块回答"本机有哪些 Agent 运行时、各自接没接线、最近一次留痕是什么时候"。
  审计账本看起来永远完整漂亮，恰恰是因为**没接线的通道根本不写记录**——这是幸存者偏差被写进了监控口径。

本模块只做一件事：把"接线"当成一个**可观测、可失败的输出**，逐通道给出显式状态。
设计约束（每条都对应一个测试）：

1. **只有 `wired` 算通过**：`wired` = 桥挂上了 + hooks 配置里有指向 `adapters.dsh.hooks` 的命令
   + 审计目标存在且有新鲜留痕。"读不到 / 解析失败 / 路径不存在"一律是显式失败态，绝不折叠成"正常"；
2. **确定性排序**：通道按 `channel_id` 排序，墙钟时间不参与排序；
   相同输入 + 相同 `now` 得到逐字节相同的 JSON；
3. **报告里不出现绝对路径**（AGENTS.md 第 19 条）：路径一律相对探测根渲染，
   探测根之外的路径渲染成 `<external>/<文件名>`；
4. **钩子命令原文不入报告**：命令可能带凭据，只留 sha256 摘要与受控的
   `--config` / `--audit` / `--hooks-config` 取值（取值本身是路径，按第 3 条渲染）；
5. **工具表只读导入** `adapters.dsh.adapter.TOOL_TABLE`（那是 T3 的写域，本模块不得复制一份）：
   漂移只做**报告**，本轮不作为阻断项（见 `ToolDriftReport.report_only`）。

探测的"真实事实"来自主机配置，不来自仓库声明：

- `$DSH_HOME`（或 `~/.dsh` 等等价位置）下的 `profiles/<name>/cordis.patch.yml`：
  桥（`policy-hook.plugin.mjs` 或 `@deepseek-ai/dsh-hooks-*`）是不是真的挂上去了；
- 桥声明的 hooks 配置（`--hooks-config` / `configPath`）里有没有指向 `adapters.dsh.hooks` 的命令；
- 钩子命令里的 `--audit`（或 `--config` 指向的 adapter 配置里的 `audit_log`）对应的 JSONL
  存不存在、最后一条记录是什么时间；
- `$DSH_HOME/sessions/**/*.jsonl[.zstd]` 里**运行期真实出现过**的工具名，
  与 `TOOL_TABLE` 比对（R5：声明与运行期现实之间没有漂移检测）。
"""

from __future__ import annotations

import datetime as clock
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

import yaml

__all__ = [
    "FAILURE_STATUSES",
    "ChannelReport",
    "ChannelStatus",
    "DEFAULT_OBSERVED_SESSIONS",
    "DEFAULT_STALE_AFTER_SECONDS",
    "ToolDriftReport",
    "ToolObservationStatus",
    "WIRING_SCHEMA_VERSION",
    "WiringError",
    "WiringReport",
    "declared_tool_table",
    "probe_wiring",
]

# 输出协议版本：消费方看不懂必须拒绝（与 audit_schema_version 同一条思路）。
WIRING_SCHEMA_VERSION = "1.0"

DEFAULT_STALE_AFTER_SECONDS = 7 * 24 * 3600
DEFAULT_OBSERVED_SESSIONS = 8

PROFILE_PATCH_NAME = "cordis.patch.yml"
PROFILE_ROOT_NAME = "cordis.yml"
PROFILE_MANIFEST_NAME = "package.json"
PROFILES_DIR_NAME = "profiles"
SESSIONS_DIR_NAME = "sessions"

# 桥的两种形态：本仓库的进程内转发插件，或 dsh 自带的 Claude Code / Codex 方言桥。
IN_PROCESS_PLUGIN_SUFFIX = "policy-hook.plugin.mjs"
BRIDGE_PACKAGES = (
    "@deepseek-ai/dsh-hooks-claude-code",
    "@deepseek-ai/dsh-hooks-codex",
)

# 运行期自检（hooks.check_wiring）用的同一个标记：命令里必须出现它才算接入策略 Hook。
POLICY_HOOK_MARKER = "adapters.dsh.hooks"

MAX_AUDIT_LINES = 50_000
MAX_SESSION_LINES = 400

# 两个运行期默认值：清点必须与运行期同口径，因此这两个数**不是**本模块自己定的，
# 而是各自实现里的既有默认值，由契约测试逐字比对（改一边不改另一边会红）：
# - src/adapters/dsh/adapter.py 的 load_config：timeout_ms 缺省 5000（内部预算）；
# - src/adapters/dsh/policy-hook.plugin.mjs 的 DEFAULT_TIMEOUT_MS：config.timeoutMs 缺省 30000。
DEFAULT_INTERNAL_BUDGET_MS = 5000
IN_PROCESS_DEFAULT_TIMEOUT_MS = 30000

# patch 层里 §§!!js§§ 之类的自定义标签会被 _PatchLoader 换成这个前缀的占位串：
# 值读不出数值，所以"不等式成立"证明不了（不是"非法"，也不假装它是默认值）。
_UNINTERPRETED_TAG_PREFIX = "<uninterpreted-tag:"

_TOOL_TABLE_SOURCE = "src/adapters/dsh/adapter.py:TOOL_TABLE"


class WiringError(RuntimeError):
    """用法或输入错误（CLI 退出码 2）。

    注意与"某通道没接线"的区别：后者是**正常的显式状态**（退出码 1），不是异常。
    """


class ChannelStatus(str, Enum):
    """通道状态。除 `WIRED` 外全部是失败态（`--check` 一律退出非 0）。"""

    WIRED = "wired"
    NOT_WIRED = "not_wired"
    HOOKS_CONFIG_MISSING = "hooks_config_missing"
    HOOKS_CONFIG_UNPARSABLE = "hooks_config_unparsable"
    NO_AUDIT_TARGET = "no_audit_target"
    AUDIT_NEVER_WRITTEN = "audit_never_written"
    STALE = "stale"
    # 预算不等式不满足：接线在，但 dsh 侧超时会先杀掉 Hook，而"被杀"在 dsh 协议里等于放行。
    # AGENTS.md 第 10 条把它算作失败关闭的一部分，运行期 hooks.check_wiring 也把它当错误返回——
    # 静态清点必须同结论，否则就是两套口径。
    TIMEOUT_BUDGET_VIOLATED = "timeout_budget_violated"
    # 预算不等式**证明不了**：读数缺失 / 解析失败（adapter 配置读不到、timeout_ms 非法等）。
    # "证明不了"按失败处理——读不到不等于不等式成立，更不等于通过。与 VIOLATED 分开是为了让
    # 读者能区分"算出来不满足"与"根本算不出来"：两者的处置不同。
    TIMEOUT_BUDGET_UNKNOWN = "timeout_budget_unknown"
    # —— 下面几个是"读不到 / 结构坏了"的显式失败态：
    #    它们与上面的区别只是成因，处置相同——绝不因为"读不出来"就当成"没问题"。
    PROFILE_UNREADABLE = "profile_unreadable"
    HOOKS_CONFIG_UNREADABLE = "hooks_config_unreadable"
    AUDIT_UNREADABLE = "audit_unreadable"
    AUDIT_UNPARSABLE = "audit_unparsable"

    @property
    def is_wired(self) -> bool:
        return self is ChannelStatus.WIRED


FAILURE_STATUSES: tuple[ChannelStatus, ...] = tuple(
    status for status in ChannelStatus if not status.is_wired
)


class ToolObservationStatus(str, Enum):
    """工具漂移的观察源状态。读不到观察源也是显式状态，不是"无漂移"。"""

    OBSERVED = "observed"
    OBSERVATION_UNAVAILABLE = "observation_unavailable"
    DISABLED = "disabled"


@dataclass(frozen=True)
class _PathRenderer:
    """把绝对路径渲染成相对探测根的字符串（AGENTS.md 第 19 条）。"""

    root: Optional[Path]

    def render(self, path: Optional[Path | str]) -> Optional[str]:
        if path is None:
            return None
        candidate = Path(path)
        if self.root is not None:
            try:
                relative = candidate.resolve().relative_to(Path(self.root).resolve())
            except (OSError, ValueError):
                relative = None
            if relative is not None:
                text = relative.as_posix()
                return "." if text in ("", ".") else text
        return "<external>/" + candidate.name

    def render_name(self, name: str) -> str:
        """插件条目名可能是包名，也可能是绝对路径（本仓库的 .mjs 插件）——只渲染后者。"""

        if "/" in name or "\\" in name or name.endswith((".mjs", ".js", ".cjs")):
            return self.render(name) or name
        return name


@dataclass(frozen=True)
class ChannelReport:
    """一个 Agent 运行时通道的接线事实与留痕事实。"""

    channel_id: str
    kind: str
    status: ChannelStatus
    detail: str
    profile: Optional[str] = None
    profile_dir: Optional[str] = None
    patch: Optional[str] = None
    bundles: tuple[str, ...] = ()
    bridge: Optional[Mapping[str, Any]] = None
    hooks_config: Optional[str] = None
    hooks_config_exists: Optional[bool] = None
    hook_command_digest: Optional[str] = None
    hook_flags: Mapping[str, str] = field(default_factory=dict)
    audit_path: Optional[str] = None
    audit_records: int = 0
    audit_bad_lines: int = 0
    last_record_at: Optional[str] = None
    age_seconds: Optional[int] = None
    stale_after_seconds: Optional[float] = None
    timeout_budget: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status.is_wired

    def summary(self) -> str:
        return f"{self.channel_id}: {self.status.value} — {self.detail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "kind": self.kind,
            "status": self.status.value,
            "wired": self.status.is_wired,
            "detail": self.detail,
            "profile": self.profile,
            "profile_dir": self.profile_dir,
            "patch": self.patch,
            "bundles": list(self.bundles),
            "bridge": None if self.bridge is None else dict(self.bridge),
            "hooks_config": self.hooks_config,
            "hooks_config_exists": self.hooks_config_exists,
            "hook_command_digest": self.hook_command_digest,
            "hook_flags": dict(sorted(self.hook_flags.items())),
            "audit_path": self.audit_path,
            "audit_records": self.audit_records,
            "audit_bad_lines": self.audit_bad_lines,
            "last_record_at": self.last_record_at,
            "age_seconds": self.age_seconds,
            "stale_after_seconds": self.stale_after_seconds,
            "timeout_budget": dict(sorted(self.timeout_budget.items())),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ToolDriftReport:
    """工具表（声明）与运行期观察（现实）之间的漂移。**只报告，不阻断**。"""

    declaration_source: str
    declared: tuple[str, ...]
    observation_status: ToolObservationStatus
    observation_source: Optional[str]
    observation_detail: str
    sessions_scanned: int
    runtime_declared: tuple[str, ...]
    runtime_called: tuple[str, ...]
    observed_not_in_table: tuple[str, ...]
    table_not_observed: tuple[str, ...]
    declaration_error: Optional[str] = None
    report_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "declaration_source": self.declaration_source,
            "declaration_error": self.declaration_error,
            "declared_count": len(self.declared),
            "declared": list(self.declared),
            "observation_status": self.observation_status.value,
            "observation_source": self.observation_source,
            "observation_detail": self.observation_detail,
            "sessions_scanned": self.sessions_scanned,
            "runtime_declared": list(self.runtime_declared),
            "runtime_called": list(self.runtime_called),
            "observed_not_in_table": list(self.observed_not_in_table),
            "table_not_observed": list(self.table_not_observed),
            "report_only": self.report_only,
        }


@dataclass(frozen=True)
class WiringReport:
    """整份清点结果。`ok` 只在"至少一个通道，且每个通道都 wired"时为真。"""

    dsh_home_label: str
    dsh_home_source: str
    candidates: tuple[tuple[str, bool], ...]
    probe_status: str
    profiles_dir: Optional[str]
    project_root: Optional[str]
    stale_after_seconds: float
    channels: tuple[ChannelReport, ...]
    tools: ToolDriftReport
    notes: tuple[str, ...] = ()
    skipped: bool = False
    skip_reason: Optional[str] = None

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(channel.summary() for channel in self.channels if not channel.ok)

    @property
    def ok(self) -> bool:
        # 一个通道都没探到 = 什么都没证明，不是"全绿"。
        return bool(self.channels) and not self.failures

    @property
    def result(self) -> str:
        """终态：§§pass§§ / §§fail§§ / §§skipped§§。

        §§skipped§§ 只在"探遍了候选根，这台机器上根本没有可发现的 Agent 运行时"时出现，
        而且**绝不是 pass**：跳过不等于通过（G3 的教训用在清点上）。
        发现了运行时却没接线 / 配置读不到 / 解不开，一律是 §§fail§§。
        """

        if self.skipped:
            return "skipped"
        return "pass" if self.ok else "fail"

    @property
    def reproduce(self) -> Optional[str]:
        if not self.skipped:
            return None
        return "在有 dsh 运行时的机器上执行：python -m adapters.cli wiring --check"

    def to_dict(self) -> dict[str, Any]:
        return {
            "wiring_schema_version": WIRING_SCHEMA_VERSION,
            "probe": {
                "dsh_home": self.dsh_home_label,
                "dsh_home_source": self.dsh_home_source,
                "candidates": [
                    {"label": label, "exists": exists} for label, exists in self.candidates
                ],
                "status": self.probe_status,
                "profiles_dir": self.profiles_dir,
                "project_root": self.project_root,
                "stale_after_seconds": self.stale_after_seconds,
                "notes": list(self.notes),
            },
            "channels": [channel.to_dict() for channel in self.channels],
            "counts": {
                "total": len(self.channels),
                "wired": sum(1 for channel in self.channels if channel.ok),
                "failed": len(self.failures),
            },
            "failures": list(self.failures),
            "tools": self.tools.to_dict(),
            "result": self.result,
            "environment_skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "reproduce": self.reproduce,
        }

# --------------------------------------------------------------------------- 小工具


def _parse_timestamp(value: Any) -> Optional[clock.datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = clock.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=clock.timezone.utc)
    return parsed.astimezone(clock.timezone.utc)


def _utc_now() -> clock.datetime:
    return clock.datetime.now(clock.timezone.utc)


def _coerce_now(now: Optional[clock.datetime]) -> clock.datetime:
    if now is None:
        return _utc_now()
    if not isinstance(now, clock.datetime):
        raise WiringError("now 必须是 datetime，得到 " + type(now).__name__)
    if now.tzinfo is None:
        raise WiringError("now 必须带时区（否则 stale 判定依赖本机时区，不可复现）")
    return now.astimezone(clock.timezone.utc)


def _string_flag(command: str, flag: str) -> Optional[str]:
    """从命令行里取 `--flag value` 或 `--flag=value`（引号都认）。

    刻意只做词法提取：这里回答的是"接线声明指向哪个文件"，不是"这条命令安全吗"。
    """

    pattern = re.compile(
        r"(?:^|\s)" + re.escape(flag) + r"(?:=|\s+)(\"[^\"]*\"|'[^']*'|\S+)"
    )
    match = pattern.search(command)
    if match is None:
        return None
    return match.group(1).strip().strip('"').strip("'")


def _command_digest(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]


_ABSOLUTE_PATH_RE = re.compile(
    r"[A-Za-z]:[\\/][^\s'\"<>|]*" r"|(?<![\w.])/(?:[\w.@+-]+/)*[\w.@+-]*"
)


def _redact_absolute(text: str) -> str:
    """异常消息里可能带绝对路径（AGENTS.md 第 19 条：证据里不得出现绝对路径）。"""

    return _ABSOLUTE_PATH_RE.sub("<abs>", text)


def _resolve(base: Path, raw: str) -> Path:
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (base / candidate)


def _hook_commands(document: Any) -> list[str]:
    """按 dsh 的 hooks 配置形状取所有命令。

    与 `adapters.dsh.hooks.check_wiring` 的遍历口径保持一致（同一个文档必须得到同一个结论），
    契约测试会拿运行期自检的结果与本模块的结论互相验证。
    """

    commands: list[str] = []
    section = document.get("hooks") if isinstance(document, Mapping) else None
    if not isinstance(section, Mapping):
        return commands
    for groups in section.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            entries = group.get("hooks")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, Mapping) and isinstance(entry.get("command"), str):
                    commands.append(entry["command"])
    return commands


def _hook_timeout(document: Any, marker: str) -> Optional[float]:
    """取"指向策略 Hook 的那条命令"声明的 timeout（秒），用于预算不等式的事实记录。"""

    section = document.get("hooks") if isinstance(document, Mapping) else None
    if not isinstance(section, Mapping):
        return None
    found: Optional[float] = None
    for groups in section.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            entries = group.get("hooks")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                command = entry.get("command")
                if not isinstance(command, str) or marker not in command:
                    continue
                timeout = entry.get("timeout")
                if isinstance(timeout, (int, float)) and not isinstance(timeout, bool):
                    found = float(timeout)
    return found


class _PatchLoader(yaml.SafeLoader):
    """载入 patch 层时**认识结构但不执行**自定义标签（例如 dsh 允许的 §§!!js§§ 表达式）。

    用裸 §§yaml.safe_load§§ 会把 §§!!js§§ 判成"不可解析"——那是**假红**：文件对 dsh 完全正常，
    只是我们不去执行它的表达式。这里退化成占位值，如实记下遇到了哪些标签。
    """

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self.unknown_tags: list[str] = []


def _unknown_tag_constructor(loader: _PatchLoader, suffix: str, node: Any) -> str:
    loader.unknown_tags.append(suffix)
    return "<uninterpreted-tag:" + suffix + ">"


_PatchLoader.add_multi_constructor("!", _unknown_tag_constructor)
_PatchLoader.add_multi_constructor("tag:yaml.org,2002:", _unknown_tag_constructor)


def _load_patch(text: str) -> tuple[Any, tuple[str, ...]]:
    """解析 patch 层，返回（文档, 遇到的自定义标签）。语法错误仍然抛 §§yaml.YAMLError§§。"""

    loader = _PatchLoader(text)
    try:
        document = loader.get_single_data()
    finally:
        loader.dispose()
    return document, tuple(sorted(set(loader.unknown_tags)))


def _flatten_patch_entries(document: Any) -> list[Mapping[str, Any]]:
    """把 patch 层里所有带 `name` 的条目摊平。

    dsh 的 patch 语法允许 `insert` / `id` 等包装，本模块只关心"谁被挂上去了"，
    因此做深度优先的宽松遍历；结构本身不是列表/映射时由调用方报错（不能假装读懂了）。
    """

    found: list[Mapping[str, Any]] = []

    def walk(node: Any, depth: int) -> None:
        if depth > 6:
            return
        if isinstance(node, Mapping):
            if isinstance(node.get("name"), str):
                found.append(node)
                return
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(document, 0)
    return found


# --------------------------------------------------------------------------- 工具漂移


def declared_tool_table() -> Mapping[str, Any]:
    """只读导入 dsh 的工具表（唯一声明源）。

    **不得复制一份**：复制出来的表会随 upstream 改动而静默过期，那正是 R5 描述的
    "声明式数据与运行期现实之间没有漂移检测"。
    """

    from .dsh.adapter import TOOL_TABLE

    return TOOL_TABLE


class _ObservationUnavailable(RuntimeError):
    """观察源不可用（缺依赖 / 读不到）。这是显式状态，不是"没有漂移"。"""


def _session_files(sessions_dir: Path) -> list[Path]:
    files = [
        path
        for path in sessions_dir.rglob("*")
        if path.is_file() and (path.name.endswith(".jsonl") or path.name.endswith(".jsonl.zstd"))
    ]
    # 最近优先；mtime 相同时用路径做确定性 tie-break（同一批文件常在同一秒创建）。
    files.sort(key=lambda path: (-path.stat().st_mtime, path.as_posix()))
    return files


def _record_lines(handle: Any, cap: int) -> Iterator[Mapping[str, Any]]:
    for index, line in enumerate(handle):
        if index >= cap:
            return
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, Mapping):
            yield record


def _session_records(path: Path, cap: int) -> Iterator[Mapping[str, Any]]:
    """逐行读一份会话记录；`.zstd` 需要 zstandard（缺了就是显式的观察源不可用）。"""

    if path.name.endswith(".zstd"):
        try:
            import zstandard  # noqa: PLC0415 - 只在真的读到压缩会话时才需要
        except ImportError as error:
            raise _ObservationUnavailable(
                "缺少 zstandard：无法解压 dsh 会话记录"
                "（装它，或用 --observe-sessions 0 显式关掉观察）"
            ) from error
        with path.open("rb") as handle:
            with zstandard.ZstdDecompressor().stream_reader(handle) as reader:
                yield from _record_lines(io.TextIOWrapper(reader, encoding="utf-8"), cap)
        return
    with path.open("r", encoding="utf-8") as handle:
        yield from _record_lines(handle, cap)


def observe_runtime_tools(
    sessions_dir: Optional[Path], *, limit: int
) -> tuple[ToolObservationStatus, str, int, tuple[str, ...], tuple[str, ...], Optional[str]]:
    """从 dsh 会话记录里取"运行期真实出现过的工具名"。

    取两处：`data.header.tools[].name`（该会话可用的工具清单）与
    `data.message.content[]` 里 `type=tool_use` 的 `name`（真的被调用过的工具）。
    只提取工具名，**不读也不留任何会话正文**。
    """

    source = "$DSH_HOME/" + SESSIONS_DIR_NAME
    if limit <= 0:
        return (ToolObservationStatus.DISABLED, "未观察（--observe-sessions 0）", 0, (), (), None)
    if sessions_dir is None or not sessions_dir.is_dir():
        return (
            ToolObservationStatus.OBSERVATION_UNAVAILABLE,
            "会话目录不存在：观察不到运行期工具（漂移未评估，不是“无漂移”）",
            0,
            (),
            (),
            source,
        )
    files = _session_files(sessions_dir)[:limit]
    if not files:
        return (
            ToolObservationStatus.OBSERVATION_UNAVAILABLE,
            "会话目录里没有 *.jsonl/*.jsonl.zstd：观察不到运行期工具（漂移未评估）",
            0,
            (),
            (),
            source,
        )
    declared: set[str] = set()
    called: set[str] = set()
    scanned = 0
    for path in files:
        try:
            records = list(_session_records(path, MAX_SESSION_LINES))
        except _ObservationUnavailable as error:
            return (
                ToolObservationStatus.OBSERVATION_UNAVAILABLE,
                str(error),
                scanned,
                (),
                (),
                source,
            )
        except (OSError, UnicodeDecodeError) as error:
            return (
                ToolObservationStatus.OBSERVATION_UNAVAILABLE,
                "会话记录不可读（" + type(error).__name__ + "）",
                scanned,
                (),
                (),
                source,
            )
        scanned += 1
        for record in records:
            data = record.get("data")
            if not isinstance(data, Mapping):
                continue
            header = data.get("header")
            if isinstance(header, Mapping):
                for tool in header.get("tools") or []:
                    if isinstance(tool, Mapping) and isinstance(tool.get("name"), str):
                        declared.add(tool["name"])
            message = data.get("message")
            if isinstance(message, Mapping):
                for part in message.get("content") or []:
                    if (
                        isinstance(part, Mapping)
                        and part.get("type") == "tool_use"
                        and isinstance(part.get("name"), str)
                    ):
                        called.add(part["name"])
    detail = (
        "扫描 " + str(scanned) + " 份会话记录（每份最多 "
        + str(MAX_SESSION_LINES) + " 行，只取工具名）"
    )
    return (
        ToolObservationStatus.OBSERVED,
        detail,
        scanned,
        tuple(sorted(declared)),
        tuple(sorted(called)),
        source,
    )


def tool_drift(*, sessions_dir: Optional[Path], limit: int) -> ToolDriftReport:
    """TOOL_TABLE（声明）vs 运行期观察（现实）。漂移只报告，不阻断。"""

    try:
        table: Mapping[str, Any] = declared_tool_table()
        declaration_error: Optional[str] = None
    except Exception as error:  # noqa: BLE001 - 声明读不到必须显式说出来，不是"无漂移"
        table = {}
        declaration_error = type(error).__name__ + ": " + _redact_absolute(str(error))
    declared = tuple(sorted(table))
    (status, detail, scanned, runtime_declared, runtime_called, source) = observe_runtime_tools(
        sessions_dir, limit=limit
    )
    observed = set(runtime_declared) | set(runtime_called)
    return ToolDriftReport(
        declaration_source=_TOOL_TABLE_SOURCE,
        declared=declared,
        observation_status=status,
        observation_source=source,
        observation_detail=detail,
        sessions_scanned=scanned,
        runtime_declared=runtime_declared,
        runtime_called=runtime_called,
        # 声明读不到时**不报漂移**：拿不到表就说"这些工具不在表里"是另一种假安全感。
        observed_not_in_table=(
            tuple(sorted(observed - set(table))) if declaration_error is None else ()
        ),
        table_not_observed=(
            tuple(sorted(set(table) - observed)) if observed and declaration_error is None else ()
        ),
        declaration_error=declaration_error,
        report_only=True,
    )


# --------------------------------------------------------------------------- 审计留痕


@dataclass(frozen=True)
class _AuditFacts:
    status: ChannelStatus
    detail: str
    records: int
    bad_lines: int
    last_record_at: Optional[str]
    age_seconds: Optional[int]
    warnings: tuple[str, ...]


def _audit_facts(
    audit_path: Optional[Path],
    *,
    renderer: _PathRenderer,
    now: clock.datetime,
    stale_after_seconds: float,
) -> _AuditFacts:
    """读审计 JSONL，返回"留痕状态"。

    ""没有目标"" / ""目标不存在"" / ""读不到"" / ""一行都解析不出来"" / ""有记录但太旧""
    是五个不同的事实，
    每一个都必须能被单独说出来——把任一种折叠成"正常"就是本模块要消灭的那种假安全感。
    """

    if audit_path is None:
        return _AuditFacts(
            ChannelStatus.NO_AUDIT_TARGET,
            "接线里没有声明审计目标（命令没有 --audit，adapter 配置也没有 audit_log）："
            "留痕无从证明",
            0,
            0,
            None,
            None,
            (),
        )
    rendered = renderer.render(audit_path)
    if audit_path.is_dir():
        return _AuditFacts(
            ChannelStatus.AUDIT_UNREADABLE,
            "审计目标是一个目录（不是 JSONL 文件）：" + str(rendered),
            0,
            0,
            None,
            None,
            (),
        )
    if not audit_path.exists():
        return _AuditFacts(
            ChannelStatus.AUDIT_NEVER_WRITTEN,
            "审计目标不存在：" + str(rendered) + "（该通道从未留痕）",
            0,
            0,
            None,
            None,
            (),
        )
    try:
        with audit_path.open("r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError) as error:
        return _AuditFacts(
            ChannelStatus.AUDIT_UNREADABLE,
            "审计文件读不到（" + type(error).__name__ + "）：" + str(rendered),
            0,
            0,
            None,
            None,
            (),
        )
    warnings: list[str] = []
    if len(lines) > MAX_AUDIT_LINES:
        warnings.append(
            "审计文件超过 " + str(MAX_AUDIT_LINES) + " 行，"
            "只统计前 " + str(MAX_AUDIT_LINES) + " 行"
        )
        lines = lines[:MAX_AUDIT_LINES]
    records = 0
    bad_lines = 0
    last: Optional[clock.datetime] = None
    last_text: Optional[str] = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            bad_lines += 1
            continue
        if not isinstance(record, Mapping):
            bad_lines += 1
            continue
        stamp = _parse_timestamp(record.get("timestamp"))
        if stamp is None:
            bad_lines += 1
            continue
        records += 1
        if last is None or stamp > last:
            last = stamp
            last_text = record.get("timestamp")
    if records == 0:
        detail = "审计文件存在但没有任何可解析的记录：" + str(rendered)
        detail += "（" + str(bad_lines) + " 行不可解析）" if bad_lines else "（文件为空）"
        return _AuditFacts(
            ChannelStatus.AUDIT_UNPARSABLE if bad_lines else ChannelStatus.AUDIT_NEVER_WRITTEN,
            detail,
            0,
            bad_lines,
            None,
            None,
            tuple(warnings),
        )
    if bad_lines:
        # AuditLedger 只容忍"最后一行被进程杀成半行"，因此不把整份文件升级成失败态，
        # 但必须说出来：否则"少数损坏行"会被当成"审计完全可信"。
        warnings.append(
            "审计里有 " + str(bad_lines) + " 行不可解析（与 AuditLedger 的口径一致："
            "可能只是被截断的最后一行）；上面的结论只基于其余记录"
        )
    assert last is not None  # records > 0 时必然成立
    age = int((now - last).total_seconds())
    if age < 0:
        warnings.append("最后一条留痕的时间晚于当前时间（时钟偏移），按 0 处理")
        age = 0
    if age > stale_after_seconds:
        return _AuditFacts(
            ChannelStatus.STALE,
            "最后一条留痕 " + str(last_text) + " 距现在 " + str(age) + "s，超过阈值 "
            + format(stale_after_seconds, "g") + "s：" + str(rendered),
            records,
            bad_lines,
            last_text,
            age,
            tuple(warnings),
        )
    return _AuditFacts(
        ChannelStatus.WIRED,
        "接线成立且留痕新鲜：最后一条 " + str(last_text) + "（" + str(age) + "s 前）",
        records,
        bad_lines,
        last_text,
        age,
        tuple(warnings),
    )


# --------------------------------------------------------------------------- 通道探测


@dataclass(frozen=True)
class _Bridge:
    """profile patch 里挂上去的桥（只保留接线需要的事实）。"""

    entry_name: str
    kind: str
    hooks_ref: Optional[str]
    hooks_source: Optional[str]
    project_dir: Optional[str]
    dsh_side_timeout_ms: Optional[float]
    dsh_side_timeout_source: Optional[str] = None
    timeout_unreadable: bool = False
    command: Optional[str] = None
    invalid_timeout: Optional[str] = None
    notes: tuple[str, ...] = ()


def _bridge_from_entry(entry: Mapping[str, Any], renderer: _PathRenderer) -> Optional[_Bridge]:
    name = entry.get("name")
    if not isinstance(name, str):
        return None
    config = entry.get("config")
    config_map: Mapping[str, Any] = config if isinstance(config, Mapping) else {}
    notes: list[str] = []
    if config is not None and not isinstance(config, Mapping):
        notes.append("桥条目的 config 不是映射（结构不可读）：" + renderer.render_name(name))
    if name.endswith(IN_PROCESS_PLUGIN_SUFFIX):
        command = config_map.get("command")
        if not isinstance(command, str):
            notes.append("进程内插件没有声明 command：接线无法成立")
            command = None
        project_dir = config_map.get("projectDir")
        # 插件装配时就要求 timeoutMs 是正整数（policy-hook.plugin.mjs 会直接抛错），
        # 缺省时用它的 DEFAULT_TIMEOUT_MS：所以"没写"是可读的事实（默认值），"写了但不合法"是中断。
        raw_timeout = config_map.get("timeoutMs")
        invalid_timeout: Optional[str] = None
        timeout_unreadable = False
        if raw_timeout is None:
            timeout_ms: Optional[float] = float(IN_PROCESS_DEFAULT_TIMEOUT_MS)
            timeout_source = "plugin-default"
        elif isinstance(raw_timeout, str) and raw_timeout.startswith(_UNINTERPRETED_TAG_PREFIX):
            # 表达式（例如 !!js 30 * 1000）：dsh 会求值，本模块不求值——数值读不出来，
            # 于是"内部预算 < dsh 侧超时"证明不了（不是非法，也不是默认值）。
            timeout_ms = None
            timeout_source = "config.timeoutMs(表达式，未求值)"
            timeout_unreadable = True
        elif (
            isinstance(raw_timeout, bool)
            or not isinstance(raw_timeout, (int, float))
            or float(raw_timeout) < 1
            or float(raw_timeout) != int(raw_timeout)
        ):
            timeout_ms = None
            timeout_source = "config.timeoutMs(非法)"
            invalid_timeout = repr(raw_timeout)
        else:
            timeout_ms = float(raw_timeout)
            timeout_source = "config.timeoutMs"
        return _Bridge(
            entry_name=name,
            kind="in-process-plugin",
            hooks_ref=None if command is None else _string_flag(command, "--hooks-config"),
            hooks_source="--hooks-config",
            project_dir=project_dir if isinstance(project_dir, str) else None,
            dsh_side_timeout_ms=timeout_ms,
            dsh_side_timeout_source=timeout_source,
            timeout_unreadable=timeout_unreadable,
            command=command,
            invalid_timeout=invalid_timeout,
            notes=tuple(notes),
        )
    if name.startswith(BRIDGE_PACKAGES):
        config_path = config_map.get("configPath")
        if not isinstance(config_path, str):
            notes.append("方言桥没有声明 configPath：接线无法成立")
            config_path = None
        project_dir = config_map.get("projectDir")
        default_timeout = config_map.get("defaultTimeoutMs")
        return _Bridge(
            entry_name=name,
            kind="dsh-hooks-bridge",
            hooks_ref=config_path,
            hooks_source="configPath",
            project_dir=project_dir if isinstance(project_dir, str) else None,
            dsh_side_timeout_ms=(
                float(default_timeout)
                if isinstance(default_timeout, (int, float))
                and not isinstance(default_timeout, bool)
                else None
            ),
            dsh_side_timeout_source=(
                "config.defaultTimeoutMs" if isinstance(default_timeout, (int, float)) else None
            ),
            notes=tuple(notes),
        )
    return None


@dataclass(frozen=True)
class _BridgeScan:
    bridge: Optional[_Bridge]
    detected: tuple[str, ...]
    notes: tuple[str, ...]


def _scan_bridges(entries: Sequence[Mapping[str, Any]], renderer: _PathRenderer) -> _BridgeScan:
    found: list[_Bridge] = []
    notes: list[str] = []
    for entry in entries:
        bridge = _bridge_from_entry(entry, renderer)
        if bridge is not None:
            found.append(bridge)
    if len(found) > 1:
        notes.append(
            "profile patch 里挂了多个策略桥："
            + ", ".join(sorted(renderer.render_name(b.entry_name) for b in found))
            + "；判定取文件顺序里的第一个（其余的不静默忽略）"
        )
    detected = tuple(sorted(renderer.render_name(b.entry_name) for b in found))
    if not found:
        return _BridgeScan(None, detected, tuple(notes))
    return _BridgeScan(found[0], detected, tuple(notes) + found[0].notes)


def _render_flag_value(renderer: _PathRenderer, value: str) -> str:
    """命令行取值只在它是绝对路径时渲染（相对路径本身就是安全的）。"""

    return renderer.render(value) if Path(value).is_absolute() else value


def _resolve_ref(
    raw: str, bases: Sequence[tuple[str, Path]], renderer: _PathRenderer
) -> tuple[Path, str, tuple[str, ...]]:
    """按给定顺序解析一个引用路径，取第一个**真实存在**的结果。

    返回 `(路径, 用到的基准, 试过的所有基准)`；都不存在时返回第一个候选，
    并把试过的基准全部带出来——"在哪儿找过"必须可见，否则"没找到"和"没找"长得一样。
    """

    attempts: list[str] = []
    first: Optional[tuple[Path, str]] = None
    for label, base in bases:
        candidate = _resolve(base, raw)
        if first is None:
            first = (candidate, label)
        attempts.append(label + "=" + str(renderer.render(candidate)))
        if candidate.exists():
            return candidate, label, tuple(attempts)
    assert first is not None  # 调用方保证 bases 非空
    return first[0], first[1], tuple(attempts)


def _profile_bundles(profile_dir: Path, notes: list[str]) -> tuple[str, ...]:
    """读 profile 的 bundles 声明（信息性输入：损坏只记警告，不改接线判定）。"""

    manifest = profile_dir / PROFILE_MANIFEST_NAME
    if not manifest.is_file():
        return ()
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        notes.append(
            "package.json 读不到或不可解析（" + type(error).__name__ + "）：bundles 未知"
            "（信息性输入，不改变接线判定）"
        )
        return ()
    if not isinstance(document, Mapping):
        return ()
    profile = document.get("dsh")
    profile = profile.get("profile") if isinstance(profile, Mapping) else None
    bundles = profile.get("bundles") if isinstance(profile, Mapping) else None
    if not isinstance(bundles, list):
        return ()
    return tuple(sorted(item for item in bundles if isinstance(item, str)))


def _probe_channel(
    *,
    profile_dir: Path,
    profile_name: str,
    renderer: _PathRenderer,
    bases: Sequence[tuple[str, Path]],
    now: clock.datetime,
    stale_after_seconds: float,
) -> ChannelReport:
    """探一个 dsh profile 通道，返回显式状态（不做任何猜测性放行）。"""

    channel_id = "dsh:" + profile_name
    notes: list[str] = []
    bundles = _profile_bundles(profile_dir, notes)
    profile_rel = renderer.render(profile_dir)
    patch = profile_dir / PROFILE_PATCH_NAME
    patch_rel = renderer.render(patch)
    base_kwargs: dict[str, Any] = {
        "channel_id": channel_id,
        "kind": "dsh-profile",
        "profile": profile_name,
        "profile_dir": profile_rel,
        "patch": patch_rel,
        "bundles": bundles,
        "stale_after_seconds": stale_after_seconds,
    }

    def make(status: ChannelStatus, detail: str, **extra: Any) -> ChannelReport:
        extra_warnings = tuple(extra.pop("warnings", ()))
        return ChannelReport(
            status=status,
            detail=detail,
            warnings=tuple(notes) + extra_warnings,
            **{**base_kwargs, **extra},
        )

    if patch.exists() and not patch.is_file():
        return make(
            ChannelStatus.PROFILE_UNREADABLE, "profile patch 层不是普通文件：" + str(patch_rel)
        )
    if not patch.is_file():
        return make(
            ChannelStatus.HOOKS_CONFIG_MISSING,
            "profile patch 层不存在（" + str(patch_rel) + "）：无法证明接线——"
            "dsh 在配置读不到时照常启动且不报错",
        )
    try:
        patch_text = patch.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return make(
            ChannelStatus.PROFILE_UNREADABLE,
            "profile patch 层读不到（" + type(error).__name__ + "）：" + str(patch_rel),
        )
    try:
        document, tolerated_tags = _load_patch(patch_text)
    except yaml.YAMLError as error:
        return make(
            ChannelStatus.HOOKS_CONFIG_UNPARSABLE,
            "profile patch 层不可解析（" + type(error).__name__ + "）：" + str(patch_rel),
        )
    if tolerated_tags:
        notes.append(
            "profile patch 层含有本模块不解释的自定义标签（" + ", ".join(tolerated_tags)
            + "）：按占位值继续做接线事实的发现，不执行任何表达式"
        )
    if document is None:
        document = []
    if not isinstance(document, (list, Mapping)):
        return make(
            ChannelStatus.HOOKS_CONFIG_UNPARSABLE,
            "profile patch 层结构不是列表/映射：" + type(document).__name__
            + "（" + str(patch_rel) + "）",
        )
    entries = _flatten_patch_entries(document)
    scan = _scan_bridges(entries, renderer)
    notes.extend(scan.notes)
    if scan.bridge is None:
        return make(
            ChannelStatus.NOT_WIRED,
            "profile patch 里没有挂载策略桥（policy-hook.plugin.mjs / @deepseek-ai/dsh-hooks-*）："
            "该通道零治理零留痕",
        )
    bridge = scan.bridge
    if bridge.invalid_timeout is not None:
        # 插件在装配时就抛错（must be a positive integer）：该通道根本起不来。
        return make(
            ChannelStatus.NOT_WIRED,
            "桥的 config.timeoutMs 非法（" + bridge.invalid_timeout + "）："
            "policy-hook.plugin.mjs 会在装配时抛错（必须是正整数），该通道起不来",
        )
    bridge_fact: dict[str, Any] = {
        "entry": renderer.render_name(bridge.entry_name),
        "kind": bridge.kind,
        "ref_source": bridge.hooks_source,
        "detected": list(scan.detected),
    }
    if bridge.hooks_ref is None:
        return make(
            ChannelStatus.HOOKS_CONFIG_MISSING,
            "桥没有声明 hooks 配置路径（" + str(bridge.hooks_source) + "）：运行期接线自检会被关掉"
            "（hooks.check_wiring 在 None 时直接返回空串 = 通过）",
            bridge=bridge_fact,
        )

    channel_bases: tuple[tuple[str, Path], ...] = tuple(bases)
    if bridge.project_dir is not None:
        declared_dir = Path(bridge.project_dir)
        if not declared_dir.is_absolute():
            declared_dir = profile_dir / declared_dir
        channel_bases = (("bridge.projectDir", declared_dir),) + tuple(
            item for item in channel_bases if item[0] != "bridge.projectDir"
        )

    hooks_path, hooks_base, hooks_attempts = _resolve_ref(bridge.hooks_ref, channel_bases, renderer)
    hooks_rel = renderer.render(hooks_path)
    if hooks_path.is_dir():
        return make(
            ChannelStatus.HOOKS_CONFIG_UNREADABLE,
            "桥声明的 hooks 配置是一个目录（不是 JSON 文件）：" + str(hooks_rel),
            bridge=bridge_fact,
            hooks_config=hooks_rel,
            hooks_config_exists=True,
        )
    if not hooks_path.is_file():
        return make(
            ChannelStatus.HOOKS_CONFIG_MISSING,
            "桥声明的 hooks 配置不存在：" + str(hooks_rel) + "（解析基准 " + hooks_base
            + "；试过 " + "; ".join(hooks_attempts) + "）——dsh 读不到就不注册任何 hook",
            bridge=bridge_fact,
            hooks_config=hooks_rel,
            hooks_config_exists=False,
        )
    try:
        hooks_text = hooks_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return make(
            ChannelStatus.HOOKS_CONFIG_UNREADABLE,
            "hooks 配置读不到（" + type(error).__name__ + "）：" + str(hooks_rel),
            bridge=bridge_fact,
            hooks_config=hooks_rel,
            hooks_config_exists=True,
        )
    try:
        hooks_document = json.loads(hooks_text)
    except json.JSONDecodeError as error:
        return make(
            ChannelStatus.HOOKS_CONFIG_UNPARSABLE,
            "hooks 配置不可解析（" + type(error).__name__ + "）：" + str(hooks_rel)
            + "——dsh 读不到就不注册任何 hook",
            bridge=bridge_fact,
            hooks_config=hooks_rel,
            hooks_config_exists=True,
        )

    commands = _hook_commands(hooks_document)
    config_policy_commands = [command for command in commands if POLICY_HOOK_MARKER in command]
    bridge_command = bridge.command if bridge.kind == "in-process-plugin" else None
    bridge_policy_command = (
        bridge_command
        if isinstance(bridge_command, str) and POLICY_HOOK_MARKER in bridge_command
        else None
    )
    if bridge.kind == "in-process-plugin":
        # 两条都必须成立：dsh 执行的是桥命令；而那条命令带 --hooks-config 时会自己读
        # 同一个 hooks 配置做接线自检——自检不过，Hook 会对每次调用返回 wiring_error。
        if bridge_policy_command is None:
            return make(
                ChannelStatus.NOT_WIRED,
                "桥的命令没有调用 " + POLICY_HOOK_MARKER + "：dsh 不会调用策略 Hook",
                bridge=bridge_fact,
                hooks_config=hooks_rel,
                hooks_config_exists=True,
            )
        if not config_policy_commands:
            return make(
                ChannelStatus.NOT_WIRED,
                "桥带了 --hooks-config，但该 hooks 配置里没有指向 " + POLICY_HOOK_MARKER
                + " 的命令：Hook 的运行期自检会判 wiring_error，"
                "每次工具调用都被阻断（不是放行，但也不是治理）",
                bridge=bridge_fact,
                hooks_config=hooks_rel,
                hooks_config_exists=True,
            )
        policy_commands = [bridge_policy_command]
    else:
        if not config_policy_commands:
            return make(
                ChannelStatus.NOT_WIRED,
                "桥挂上了，但 hooks 配置里没有任何命令指向 " + POLICY_HOOK_MARKER
                + "：dsh 不会调用策略 Hook（hooks 配置里 " + str(len(commands)) + " 条命令）",
                bridge=bridge_fact,
                hooks_config=hooks_rel,
                hooks_config_exists=True,
            )
        policy_commands = config_policy_commands
    policy_command = policy_commands[0]
    if len(policy_commands) > 1:
        notes.append(
            "有多条调用策略 Hook 的命令（" + str(len(policy_commands))
            + " 条），取文档顺序里的第一条"
        )
    flags: dict[str, str] = {}
    for flag in ("--config", "--hooks-config", "--audit"):
        value = _string_flag(policy_command, flag)
        if value:
            flags[flag] = _render_flag_value(renderer, value)

    # 内部预算：要么从 adapter 配置读到，要么按运行期默认值
    # （adapter.py 的 load_config 缺省 5000ms）。
    # 读不到 / 解析失败 / 非法值 => budget_input_error，最后按"证明不了不等式"处理（失败态）。
    internal_budget_ms: Optional[int] = None
    internal_budget_source: Optional[str] = None
    budget_input_error: Optional[str] = None
    adapter_config_ref = _string_flag(policy_command, "--config")
    if adapter_config_ref is None:
        return make(
            ChannelStatus.NOT_WIRED,
            "钩子命令没有 --config：" + POLICY_HOOK_MARKER + " 需要 adapter 配置才能启动，"
            "缺它时进程以用法错误退出（dsh 侧等于每次调用都被阻断）",
            bridge=bridge_fact,
            hooks_config=hooks_rel,
            hooks_config_exists=True,
        )
    config_path, config_base, _ = _resolve_ref(adapter_config_ref, channel_bases, renderer)
    config_rel = renderer.render(config_path)
    if not config_path.is_file():
        budget_input_error = (
            "adapter 配置不存在（" + str(config_rel) + "，解析基准 " + config_base + "）"
        )
        notes.append(budget_input_error + "：audit_log 与 timeout_ms 取不到")
    else:
        try:
            config_document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
            budget_input_error = (
                "adapter 配置不可读或不可解析（" + type(error).__name__ + "）：" + str(config_rel)
            )
            notes.append(budget_input_error)
            config_document = None
        if isinstance(config_document, Mapping):
            declared_audit = config_document.get("audit_log")
            if declared_audit is not None and not isinstance(declared_audit, str):
                notes.append("adapter 配置的 audit_log 不是字符串：按未声明处理")
            elif isinstance(declared_audit, str):
                flags.setdefault("audit_log", declared_audit)
            budget = config_document.get("timeout_ms")
            if budget is None:
                # 运行期 load_config 的缺省值，不是本模块自己定的。
                internal_budget_ms = DEFAULT_INTERNAL_BUDGET_MS
                internal_budget_source = "runtime-default"
                notes.append(
                    "adapter 配置没有 timeout_ms：按运行期默认值 "
                    + str(DEFAULT_INTERNAL_BUDGET_MS) + "ms 计算内部预算"
                )
            elif isinstance(budget, int) and not isinstance(budget, bool) and budget > 0:
                internal_budget_ms = budget
                internal_budget_source = "config.timeout_ms"
            else:
                budget_input_error = (
                    "adapter 配置的 timeout_ms 非法（" + repr(budget)
                    + "）：运行期 load_config 会拒绝该配置，Hook 起不来"
                )
                notes.append(budget_input_error)
        elif config_document is not None:
            budget_input_error = "adapter 配置结构不是映射：" + str(config_rel)
            notes.append(budget_input_error)

    audit_ref = _string_flag(policy_command, "--audit")
    if audit_ref is None:
        audit_ref = flags.get("audit_log")
    audit_path: Optional[Path] = None
    if audit_ref is not None:
        audit_path, _, _ = _resolve_ref(audit_ref, channel_bases, renderer)
    facts = _audit_facts(
        audit_path, renderer=renderer, now=now, stale_after_seconds=stale_after_seconds
    )

    # 两个"dsh 侧超时"都要看：进程内插件的 timeoutMs 决定 ctx.shell 何时杀进程，
    # hooks.json 的 timeout 决定 Hook 自己（--hooks-config 自检）认为的预算。
    # 取**最小值**做不等式：任一条路径先触发，Hook 都会被杀，而"被杀"等于放行。
    hooks_timeout = _hook_timeout(hooks_document, POLICY_HOOK_MARKER)
    hooks_config_timeout_ms = None if hooks_timeout is None else hooks_timeout * 1000.0
    if bridge.timeout_unreadable:
        # 进程内插件的 timeoutMs 是表达式：它的值可能比 hooks.json 里的 timeout 更小，
        # 因此连"上界"都证明不了——不能拿 hooks.json 的那个数当结论。
        limits: list[float] = []
    else:
        limits = [
            value
            for value in (bridge.dsh_side_timeout_ms, hooks_config_timeout_ms)
            if value is not None
        ]
    dsh_side_timeout_ms = min(limits) if limits else None
    budget_fact: dict[str, Any] = {
        "dsh_side_timeout_ms": dsh_side_timeout_ms,
        "dsh_side_timeout_source": bridge.dsh_side_timeout_source,
        "in_process_timeout_ms": bridge.dsh_side_timeout_ms,
        "hooks_config_timeout_ms": hooks_config_timeout_ms,
        "internal_budget_ms": internal_budget_ms,
        "internal_budget_source": internal_budget_source,
        "input_error": budget_input_error,
        "ok": None,
    }
    if (
        budget_input_error is None
        and dsh_side_timeout_ms is not None
        and internal_budget_ms is not None
    ):
        budget_fact["ok"] = dsh_side_timeout_ms > internal_budget_ms

    status = facts.status
    detail = facts.detail
    if budget_input_error is not None:
        # 读不到 = 证明不了这个不等式成立。按"证明不了就拒绝"处理：失败态，绝不是 wired。
        status = ChannelStatus.TIMEOUT_BUDGET_UNKNOWN
        detail = (
            "证明不了“内部预算 < dsh 侧超时”：" + budget_input_error
            + "——读不到不等于不等式成立（AGENTS.md 第 10 条）；留痕状态：" + facts.detail
        )
    elif dsh_side_timeout_ms is None:
        status = ChannelStatus.TIMEOUT_BUDGET_UNKNOWN
        unreadable_reason = (
            "dsh 侧超时是表达式（" + str(bridge.dsh_side_timeout_source) + "），本模块不求值"
            if bridge.timeout_unreadable
            else "dsh 侧超时没有可读的声明"
            "（进程内插件会缺省用插件的 DEFAULT_TIMEOUT_MS，方言桥需要 config.defaultTimeoutMs "
            "或 hooks.json 里给策略 Hook 写 timeout）"
        )
        detail = (
            "证明不了“内部预算 < dsh 侧超时”：" + unreadable_reason
            + "；留痕状态：" + facts.detail
        )
    elif budget_fact.get("ok") is False:
        # 这不是"未接线"，而是"接上了也会被先杀掉"：dsh 侧的 timeout 一到就杀进程，
        # 而"被杀"在 dsh 协议里等于放行（AGENTS.md 第 10 条）。
        # 运行期自检（hooks.check_wiring）把这一条当错误返回，静态清点必须同结论：
        # 运行期判错、清点判过 = 两套口径，正是本轮要消灭的东西。
        status = ChannelStatus.TIMEOUT_BUDGET_VIOLATED
        detail = (
            "dsh 侧 timeout=" + format(dsh_side_timeout_ms, "g") + "ms 不大于内部预算 "
            + str(internal_budget_ms) + "ms：dsh 会先杀掉 Hook，而被杀等于放行"
            "（AGENTS.md 第 10 条）；留痕状态：" + facts.detail
        )

    return make(
        status,
        detail,
        bridge=bridge_fact,
        hooks_config=hooks_rel,
        hooks_config_exists=True,
        hook_command_digest=_command_digest(policy_command),
        hook_flags=flags,
        audit_path=renderer.render(audit_path),
        audit_records=facts.records,
        audit_bad_lines=facts.bad_lines,
        last_record_at=facts.last_record_at,
        age_seconds=facts.age_seconds,
        timeout_budget=budget_fact,
        warnings=facts.warnings,
    )



# --------------------------------------------------------------------------- 探测入口


_HOME_LABELS: Mapping[str, str] = {
    "env:DSH_HOME": "$DSH_HOME",
    "default:~/.dsh": "~/.dsh",
    "env:APPDATA/dsh": "%APPDATA%/dsh",
    "env:LOCALAPPDATA/dsh": "%LOCALAPPDATA%/dsh",
    "--dsh-home": "--dsh-home",
}


def _dsh_home_candidates() -> list[tuple[str, Path]]:
    """按"环境变量优先、等价位置兜底"的顺序列出候选 dsh 配置根。"""

    candidates: list[tuple[str, Path]] = []
    env_home = os.environ.get("DSH_HOME")
    if env_home:
        candidates.append(("env:DSH_HOME", Path(env_home)))
    candidates.append(("default:~/.dsh", Path.home() / ".dsh"))
    for variable in ("APPDATA", "LOCALAPPDATA"):
        value = os.environ.get(variable)
        if value:
            candidates.append(("env:" + variable + "/dsh", Path(value) / "dsh"))
    return candidates


def probe_wiring(
    *,
    dsh_home: Optional[Path | str] = None,
    project_root: Optional[Path | str] = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    observed_sessions: int = DEFAULT_OBSERVED_SESSIONS,
    now: Optional[clock.datetime] = None,
) -> WiringReport:
    """清点本机 Agent 运行时通道。**不抛"没接线"的异常**：那是报告里的显式状态。

    抛 `WiringError` 的只有"调用方给错了参数"（阈值非正、now 无时区、project_root 不存在）。
    """

    if (
        isinstance(stale_after_seconds, bool)
        or not isinstance(stale_after_seconds, (int, float))
        or stale_after_seconds <= 0
    ):
        raise WiringError("stale_after_seconds 必须是正数秒，得到 " + repr(stale_after_seconds))
    if (
        isinstance(observed_sessions, bool)
        or not isinstance(observed_sessions, int)
        or observed_sessions < 0
    ):
        raise WiringError("observed_sessions 必须是非负整数，得到 " + repr(observed_sessions))
    moment = _coerce_now(now)

    notes: list[str] = []
    if dsh_home is not None:
        explicit = Path(dsh_home)
        candidates: tuple[tuple[str, Path], ...] = (("--dsh-home", explicit),)
        source = "--dsh-home"
        home: Optional[Path] = explicit if explicit.is_dir() else None
        if home is None:
            notes.append("显式指定的 dsh 根不存在或不是目录：--dsh-home")
    else:
        discovered = _dsh_home_candidates()
        candidates = tuple(discovered)
        home = None
        source = "missing"
        for label, path in discovered:
            if path.is_dir():
                home = path
                source = label
                break

    renderer = _PathRenderer(home)
    candidate_labels = tuple((label, path.is_dir()) for label, path in candidates)

    channels: tuple[ChannelReport, ...] = ()
    profiles_rel: Optional[str] = None
    skipped = False
    skip_reason: Optional[str] = None
    if home is None:
        probe_status = "dsh_home_missing"
        probed = ", ".join(label for label, _ in candidate_labels)
        if dsh_home is None:
            # 环境跳过：本机根本没有可发现的 Agent 运行时。它**不是 pass**（跳过不等于通过），
            # 也不该报成 fail——那会让任何没有 Agent 的机器上这条命令永远红着，最后被当噪声。
            # 显式指定 --dsh-home 却不存在不算跳过：那是"你声称有运行时"，按失败处理。
            skipped = True
            skip_reason = (
                "本机没有可发现的 Agent 运行时：探测过的候选根（" + probed + "）都不存在。"
                "这是环境跳过，不是通过——没有任何通道被观察到，也没有任何接线被证明。"
            )
        notes.append(
            "没有找到 dsh 配置根（探测过 " + probed + "）：没有任何通道可以证明已接线"
            "——这不是“通过”，是“没得证明”"
        )
    else:
        profiles_dir = home / PROFILES_DIR_NAME
        profiles_rel = renderer.render(profiles_dir)
        if not profiles_dir.is_dir():
            probe_status = "profiles_dir_missing"
            notes.append("profiles 目录不存在：" + str(profiles_rel) + "（无法枚举通道）")
        else:
            probe_status = "ok"
            root_bases: list[tuple[str, Path]] = []
            if project_root is not None:
                declared_root = Path(project_root)
                if not declared_root.is_dir():
                    raise WiringError("--project-root 不存在或不是目录：" + declared_root.name)
                root_bases.append(("--project-root", declared_root))
            probed: list[ChannelReport] = []
            # 刻意不叫 skipped：那个名字是"环境跳过"终态的标志位，同名会把它覆盖成目录清单。
            not_profiles: list[str] = []
            for profile_dir in sorted(
                (item for item in profiles_dir.iterdir() if item.is_dir()),
                key=lambda item: item.name,
            ):
                if not (
                    (profile_dir / PROFILE_ROOT_NAME).exists()
                    or (profile_dir / PROFILE_PATCH_NAME).exists()
                ):
                    not_profiles.append(str(renderer.render(profile_dir)))
                    continue
                bases = tuple(root_bases) + (("profile 目录", profile_dir),)
                probed.append(
                    _probe_channel(
                        profile_dir=profile_dir,
                        profile_name=profile_dir.name,
                        renderer=renderer,
                        bases=bases,
                        now=moment,
                        stale_after_seconds=stale_after_seconds,
                    )
                )
            if not_profiles:
                notes.append(
                    "跳过不是 profile 的目录（既没有 " + PROFILE_ROOT_NAME + " 也没有 "
                    + PROFILE_PATCH_NAME + "）：" + ", ".join(sorted(not_profiles))
                )
            if not probed:
                notes.append("profiles 目录里没有任何 profile：没有通道可以证明已接线")
            # 排序键只有 channel_id：墙钟时间不参与排序，同样的输入得到同样的顺序。
            channels = tuple(sorted(probed, key=lambda channel: channel.channel_id))

    sessions_dir = None if home is None else home / SESSIONS_DIR_NAME
    tools = tool_drift(sessions_dir=sessions_dir, limit=observed_sessions)
    return WiringReport(
        dsh_home_label=_HOME_LABELS.get(source, source),
        dsh_home_source=source,
        candidates=candidate_labels,
        probe_status=probe_status,
        profiles_dir=profiles_rel,
        project_root=renderer.render(project_root) if project_root is not None else None,
        stale_after_seconds=float(stale_after_seconds),
        channels=channels,
        tools=tools,
        notes=tuple(notes),
        skipped=skipped,
        skip_reason=skip_reason,
    )

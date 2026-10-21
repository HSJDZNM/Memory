"""批次台账（C1-a / C1-b）：把本会话提议过的目标文件落成可按会话折叠的追加写账本。

为什么需要它（04 5.46 / 04 5.68 / 05 3.3）：dsh 的 Hook 是**每次工具调用一个新进程**，批次
状态跨不了进程；判定粒度是单次编辑。C1-a 只回答"这个会话提议过哪些文件"（只报告）；
C1-b 追加**结算**与**逐目标折叠**，让 pre_evidence 可以把"同一批里已结算且真的落地的目标"
作为判定范围的一部分。本模块仍然**不做判定**：它只回答"账本里记了什么、哪些成员可证明"，
allow / block 仍由 policy.engine.evaluate 决定。

四条写死的口径：

1. **按会话分文件**：<root>/<session_id>.jsonl，一条记录一行 JSON，UTF-8 + LF，追加写。
   session_id 不是安全的文件名时**拒绝记录**（不 sanitize：洗过的名字会把两个会话并进一个
   文件，那正是"并发会话互相污染"的形状）；
2. **batch_ref 是目标集合的稳定摘要**：同一会话、同一批目标，两次计算逐字节相同。它覆盖
   session_id + 排序去重的目标集合，因此不同会话不会撞成同一个批次；recorded_at 不参与
   摘要——时间是"这条记录什么时候写下"的事实，不是"这批目标是什么"的事实；
3. **结算只写事实、不改判定**：settle 记录 outcome=allowed 当且仅当这次 Hook 的最终退出码是 0；
   content_sha256 是**动作之后目标文件的期望哈希**（取自 pre_evidence 的 proposal 摘要），
   由读取侧与当前磁盘比对来证明"提议的内容真的在树里"。账本不可写 / 读不出由调用方显式降级，
   本模块绝不把异常吞成"记录成功"；
4. **逐目标折叠、最后一条胜出**：proposal / settle / abandon 三种记录按文件顺序折叠；同一目标
   以最后一条 proposal 为"最新意图"，settle 必须对应这次 proposal 的 event_id，abandon 只有在
   它晚于最新 proposal 时才算数。1.0 的记录按 proposal 读、永远不可结算（legacy）。

TTL / 保留：ttl_hours 只服务 prune_expired()。清理是**维护动作**，不参与 batch_ref 计算
（按时间过滤会让"同一批目标"在不同时刻得到两个摘要）。为避免一个写错的 root 把别的
.policy 文件当批次删掉，清理只在目录名恰好是 pre-evidence-batches 时执行。

本模块不导入 hooks（hooks 要导入本模块），也不导入 adapter / policy 的判定路径：读取侧
需要的路径规范化与写类工具集合由调用方以**显式参数**传入（validate_target / write_tools），
因此这里不做任何"猜项目结构"的事。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, FrozenSet, Iterable, Mapping, Optional, Tuple

__all__ = [
    "BATCH_LEDGER_SCHEMA_VERSION",
    "BATCH_DIRNAME",
    "SUPPORTED_BATCH_LEDGER_SCHEMA_VERSIONS",
    "BATCH_VIEW_NOTE",
    "BatchLedgerError",
    "BatchView",
    "append_abandon",
    "append_settlement",
    "append_target",
    "batch_ref",
    "batch_view",
    "prune_expired",
    "read_records",
    "read_targets",
    "session_filename",
    "targets_digest",
]

# 账本文件自己的协议轴（AGENTS 第 55 条：加键就是改协议）。**不是**审计记录那条轴：
# 判定记录的键集合变更是 adapters.dsh.hooks.AUDIT_SCHEMA_VERSION 的事，两者各走各的。
# 1.0（C1-a）：记录形状固定为
#   {schema_version, session_id, event_id, tool, target, recorded_at}。
# 1.1（C1-b）：记录多出 kind（proposal / settle / abandon）；settle 追加 outcome /
#   reason_code / content_sha256；abandon 追加 reason。1.0 记录按 proposal 读、
#   永远不可结算（没有 settle 可言），因此升级不会把旧记录读成"已允许"。
BATCH_LEDGER_SCHEMA_VERSION = "1.1"
SUPPORTED_BATCH_LEDGER_SCHEMA_VERSIONS: FrozenSet[str] = frozenset({"1.0", "1.1"})

# 默认落点目录名。TTL 清理只在这个名字的目录里执行（安全边界，见 prune_expired）。
BATCH_DIRNAME = "pre-evidence-batches"

# 摘要前缀：把"摘要覆盖了哪些字段"写进被哈希的字节里，将来改口径必然改变摘要，
# 而不是悄悄产出一个"看起来一样、其实含义不同"的值。1.0 的前缀保持不变：
# 升级账本协议不改变 batch_ref 的含义（它仍然只覆盖 session + 目标集合）。
_TARGETS_DIGEST_PREFIX = "pre-evidence-batch-targets/1.0\n"
_BATCH_REF_PREFIX = "pre-evidence-batch/1.0\n"

# session_id 直接当文件名，必须是**单段**安全名字：没有分隔符、没有控制字符、不是 "." / ".."。
# 拒绝而不是清洗：清洗会把两个不同会话映到同一个文件（见模块 docstring 第 1 条）。
_SESSION_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")

# 记录种类与 settle 结果都是闭集：不认识就跳过并计数，绝不默认放行。
KIND_PROPOSAL = "proposal"
KIND_SETTLE = "settle"
KIND_ABANDON = "abandon"
_KINDS: FrozenSet[str] = frozenset({KIND_PROPOSAL, KIND_SETTLE, KIND_ABANDON})
OUTCOME_ALLOWED = "allowed"
OUTCOME_BLOCKED = "blocked"
_OUTCOMES: FrozenSet[str] = frozenset({OUTCOME_ALLOWED, OUTCOME_BLOCKED})

# 审计 pre_evidence.batch 的固定说明：读账本的人不必去猜"members 到底进了什么"。
BATCH_VIEW_NOTE = (
    "batch 块是 C1-b 的判定范围说明：included 里的目标已被结算为 allowed、且其 content_sha256 "
    "与当前取证工作区里的文件一致，因此被并入 PipelineRequest.changed_files；它不改变取证树"
    "（tree.scope 仍是当前磁盘树 + 本次提议），也不把被 block / 未结算 / 未落地的提议读成变更。"
    "status=partial 表示有目标被排除或截断（见 excluded / truncated）；status=unreadable 表示"
    "账本整份读不出来，本次按单文件判定（changed 回退为动作目标），这件事必须从审计读到。"
    "members_digest 覆盖 included 集合，是本次实际使用的批次身份（batch_ref 只是每条记录写入时的"
    "目标集合快照，同一会话会随目标增长而变化）"
)

# 路径校验器可以抛出的错误类型：调用方（pre_evidence）把 policy 的路径规范化包成 ValueError，
# 本模块不认识 policy 的类型，也不把"证明不了"降级成"排除了就不算失败"。
ValidateTarget = Callable[[str], str]


class BatchLedgerError(Exception):
    """批次台账写不进去 / 读不懂：调用方必须显式降级（fail-open 报告），不得当成"记上了"。"""


@dataclass(frozen=True)
class BatchView:
    """账本折叠出的"这一批有哪些可证明的成员"。

    members 只是**候选**：调用方决定是否把它们并进 changed_files（into_decision）。
    excluded 里的名单是审计要读的一等输出——"这个目标没进批次"与"这个目标不存在"必须分得开。
    """

    status: str
    members: Tuple[str, ...]
    excluded: Mapping[str, Tuple[str, ...]]
    settled: Mapping[str, int]
    truncated: int
    skipped_lines: int
    invalid_lines: int
    members_digest: str
    note: str = BATCH_VIEW_NOTE

    @property
    def applied(self) -> bool:
        """本次是否真的把成员带进了 changed_files。空成员 / 读不出时都是 False。"""

        return bool(self.members) and self.status != "unreadable"


def session_filename(session_id: Any) -> str:
    """session_id → 账本文件名。不安全的名字直接拒绝（不 sanitize）。"""

    if not isinstance(session_id, str):
        raise BatchLedgerError(
            f"session_id 不是字符串（{type(session_id).__name__}）：无法确定本会话的账本文件"
        )
    candidate = session_id.strip()
    if not _SESSION_ID_RE.match(candidate) or candidate in {".", ".."}:
        raise BatchLedgerError(
            "session_id 不是安全的文件名（只接受 [A-Za-z0-9][A-Za-z0-9_.-]*，最长 128；"
            "不能是 . / ..）：拒绝把它拼进批次账本路径"
        )
    return candidate + ".jsonl"


def _clean_targets(targets: Iterable[Any]) -> list[str]:
    cleaned: set[str] = set()
    for item in targets:
        if not isinstance(item, str):
            raise BatchLedgerError(f"目标不是字符串（{type(item).__name__}）：无法计算批次摘要")
        value = item.strip()
        if value:
            cleaned.add(value)
    return sorted(cleaned)


def targets_digest(targets: Iterable[Any]) -> str:
    """目标集合的稳定摘要：排序去重后覆盖，同一集合两次计算逐字节相同。"""

    cleaned = _clean_targets(targets)
    payload = _TARGETS_DIGEST_PREFIX + "\n".join(cleaned)
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def batch_ref(session_id: Any, targets: Iterable[Any]) -> str:
    """批次引用：session_id + 目标集合的稳定摘要（同一批目标两次计算相同）。

    注意它的**已知局限**（C1-b 的 D1）：它覆盖"写下这条记录之后"的目标集合，因此同一会话
    每条记录的值都不同，只有前缀可比。审计里"这次实际用了哪一批"的身份是 members_digest。
    """

    filename = session_filename(session_id)
    payload = (
        _BATCH_REF_PREFIX
        + filename[: -len(".jsonl")]
        + "\n"
        + targets_digest(targets)
    )
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- 读


def _normalized_record(record: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """一条已解析的 JSON → 规范化记录；结构不成立返回 None（由调用方计 skipped）。"""

    version = record.get("schema_version")
    if version not in SUPPORTED_BATCH_LEDGER_SCHEMA_VERSIONS:
        return None
    kind = KIND_PROPOSAL if version == "1.0" else record.get("kind")
    if kind not in _KINDS:
        return None
    session_id = record.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    normalized: dict[str, Any] = {
        "schema_version": version,
        "kind": kind,
        "session_id": session_id.strip(),
        "event_id": None,
        "tool": None,
        "target": None,
        "outcome": None,
        "reason_code": None,
        "content_sha256": None,
        "recorded_at": None,
    }
    event_id = record.get("event_id")
    if isinstance(event_id, str) and event_id.strip():
        normalized["event_id"] = event_id.strip()
    recorded_at = record.get("recorded_at")
    if isinstance(recorded_at, str) and recorded_at.strip():
        normalized["recorded_at"] = recorded_at.strip()
    if kind == KIND_PROPOSAL:
        tool = record.get("tool")
        target = record.get("target")
        if not isinstance(tool, str) or not tool.strip():
            return None
        if not isinstance(target, str) or not target.strip() or normalized["event_id"] is None:
            return None
        normalized["tool"] = tool.strip()
        normalized["target"] = target.strip()
        return normalized
    if kind == KIND_SETTLE:
        target = record.get("target")
        outcome = record.get("outcome")
        reason_code = record.get("reason_code")
        if not isinstance(target, str) or not target.strip() or normalized["event_id"] is None:
            return None
        if outcome not in _OUTCOMES:
            return None
        if not isinstance(reason_code, str) or not reason_code.strip():
            return None
        content_sha = record.get("content_sha256")
        if content_sha is not None and not (
            isinstance(content_sha, str) and content_sha.startswith("sha256:")
        ):
            return None
        normalized["target"] = target.strip()
        normalized["outcome"] = outcome
        normalized["reason_code"] = reason_code.strip()
        normalized["content_sha256"] = content_sha
        return normalized
    # abandon：target / event_id 都可选；reason 必需。
    target = record.get("target")
    if target is not None and (not isinstance(target, str) or not target.strip()):
        return None
    reason = record.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None
    normalized["target"] = None if target is None else target.strip()
    normalized["reason_code"] = reason.strip()
    return normalized


def read_records(path: Path | str) -> tuple[list[dict[str, Any]], int]:
    """读出规范化记录与**跳过了几行**。

    跳过的行是事实不是噪声：Hook 被 dsh 杀掉会留下半行 JSON，将来也可能出现本版本不认识的
    schema_version。两种情况都不能让"这批目标"悄悄少一个，所以调用方要把跳过数写进审计。
    文件不存在 = 空集合（这是"还没有记录"，不是"读失败"）。
    """

    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], 0
    except (OSError, UnicodeDecodeError) as error:
        raise BatchLedgerError(
            f"批次账本 {target.name} 读不出来（{type(error).__name__}）：证明不了已记录的目标集合"
        ) from error

    records: list[dict[str, Any]] = []
    skipped = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(raw, dict):
            skipped += 1
            continue
        normalized = _normalized_record(raw)
        if normalized is None:
            skipped += 1
            continue
        records.append(normalized)
    return records, skipped


def read_targets(path: Path | str) -> tuple[list[str], int]:
    """兼容读法（C1-a 的调用方与测试）：只取 target 列表与跳过行数。"""

    records, skipped = read_records(path)
    return [record["target"] for record in records if record["target"]], skipped


# --------------------------------------------------------------------------- 写


def _write_line(path: Path, record: Mapping[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
    except OSError as error:
        raise BatchLedgerError(
            f"批次账本追加写失败（{type(error).__name__}: {error}）"
        ) from error


def _prepare(root: Path | str, session_id: Any) -> tuple[Path, str]:
    filename = session_filename(session_id)
    directory = Path(root)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise BatchLedgerError(
            f"批次账本目录建不出来（{type(error).__name__}: {error}）"
        ) from error
    if not directory.is_dir():
        raise BatchLedgerError(f"批次账本落点不是目录：{directory.name}")
    return directory / filename, session_id.strip()


def append_target(
    *,
    root: Path | str,
    session_id: Any,
    event_id: Any,
    tool: Any,
    target: Any,
    recorded_at: Any,
) -> tuple[Path, list[str], int]:
    """把本次事件的目标追加进本会话的账本；返回 (文件路径, 目标集合, 跳过行数)。

    顺序是**先读后写**：摘要覆盖的是"写下这条之后文件里已记录的目标集合"。读失败直接抛，
    不追加——半份集合算出来的 batch_ref 会把两个不同的批次读成同一批。
    """

    filename = session_filename(session_id)
    for name, value in (
        ("event_id", event_id),
        ("tool", tool),
        ("target", target),
        ("recorded_at", recorded_at),
    ):
        if not isinstance(value, str) or not value.strip():
            raise BatchLedgerError(f"批次记录字段 {name} 必须是非空字符串")
    path, normalized_session = _prepare(root, session_id)
    assert path.name == filename
    normalized_target = target.strip()

    existing, skipped = read_targets(path)
    record = {
        "schema_version": BATCH_LEDGER_SCHEMA_VERSION,
        "kind": KIND_PROPOSAL,
        "session_id": normalized_session,
        "event_id": event_id.strip(),
        "tool": tool.strip(),
        "target": normalized_target,
        "recorded_at": recorded_at.strip(),
    }
    _write_line(path, record)
    # 只有追加成功才把它算进集合：写失败时对外报的是"没记上"，不是"记上了一半"。
    return path, existing + [normalized_target], skipped


def append_settlement(
    *,
    root: Path | str,
    session_id: Any,
    event_id: Any,
    target: Any,
    outcome: str,
    reason_code: Any,
    content_sha256: Optional[str],
    recorded_at: Any,
) -> Path:
    """追加一条结算记录（在审计 append 之前写；失败由调用方降级，不改判定）。"""

    if outcome not in _OUTCOMES:
        raise BatchLedgerError(f"未知结算结果 {outcome!r}：只接受 {sorted(_OUTCOMES)}")
    for name, value in (
        ("event_id", event_id),
        ("target", target),
        ("reason_code", reason_code),
        ("recorded_at", recorded_at),
    ):
        if not isinstance(value, str) or not value.strip():
            raise BatchLedgerError(f"结算记录字段 {name} 必须是非空字符串")
    if content_sha256 is not None and not (
        isinstance(content_sha256, str) and content_sha256.startswith("sha256:")
    ):
        raise BatchLedgerError("content_sha256 必须是 sha256: 开头的字符串或 None")
    path, normalized_session = _prepare(root, session_id)
    record: dict[str, Any] = {
        "schema_version": BATCH_LEDGER_SCHEMA_VERSION,
        "kind": KIND_SETTLE,
        "session_id": normalized_session,
        "event_id": event_id.strip(),
        "target": target.strip(),
        "outcome": outcome,
        "reason_code": reason_code.strip(),
        "recorded_at": recorded_at.strip(),
    }
    if content_sha256 is not None:
        record["content_sha256"] = content_sha256
    _write_line(path, record)
    return path


def append_abandon(
    *,
    root: Path | str,
    session_id: Any,
    reason: Any,
    recorded_at: Any,
    target: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Path:
    """追加一条作废记录：target 省略 = 作废该会话在它之前的所有目标。"""

    for name, value in (("reason", reason), ("recorded_at", recorded_at)):
        if not isinstance(value, str) or not value.strip():
            raise BatchLedgerError(f"作废记录字段 {name} 必须是非空字符串")
    for name, value in (("target", target), ("event_id", event_id)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise BatchLedgerError(f"作废记录字段 {name} 必须是非空字符串或 None")
    path, normalized_session = _prepare(root, session_id)
    record: dict[str, Any] = {
        "schema_version": BATCH_LEDGER_SCHEMA_VERSION,
        "kind": KIND_ABANDON,
        "session_id": normalized_session,
        "reason": reason.strip(),
        "recorded_at": recorded_at.strip(),
    }
    if target is not None:
        record["target"] = target.strip()
    if event_id is not None:
        record["event_id"] = event_id.strip()
    _write_line(path, record)
    return path


# --------------------------------------------------------------------------- 折叠


def _file_sha256(workspace: Path, relative: str) -> Optional[str]:
    try:
        data = (workspace / relative).read_bytes()
    except OSError:
        return None
    return "sha256:" + sha256(data).hexdigest()


def batch_view(
    *,
    root: Path | str,
    session_id: Any,
    exclude_event_id: Optional[str],
    workspace: Path | str,
    max_targets: int,
    validate_target: ValidateTarget,
    write_tools: FrozenSet[str],
) -> BatchView:
    """把本会话的账本折叠成"可证明的成员 + 被排除的目标"。

    所有"证明不了"的情况都进 excluded / skipped / invalid，**绝不**把一个无法证明的目标当成
    allowed 成员。调用方负责在读取失败时给 status=unreadable 并回退单文件判定。
    """

    filename = session_filename(session_id)
    normalized_session = session_id.strip()
    path = Path(root) / filename
    records, skipped_lines = read_records(path)

    states: dict[str, dict[str, Any]] = {}
    invalid_lines = 0
    global_abandon_seq = -1
    for index, record in enumerate(records):
        if record["session_id"] != normalized_session:
            # 同一文件里出现别的会话：不是本会话的事实，计入 invalid（不是静默忽略）。
            invalid_lines += 1
            continue
        kind = record["kind"]
        target = record["target"]
        if kind == KIND_ABANDON and target is None:
            global_abandon_seq = index
            continue
        if target is None:
            invalid_lines += 1
            continue
        try:
            normalized_target = validate_target(target)
        except ValueError:
            invalid_lines += 1
            continue
        state = states.setdefault(
            normalized_target,
            {"proposal": None, "settles": {}, "abandon": None},
        )
        if kind == KIND_PROPOSAL:
            if record["event_id"] == exclude_event_id:
                # 本次动作自己的提议：不是"同批已提议"的对象，直接不作为候选。
                continue
            state["proposal"] = {**record, "seq": index, "target": normalized_target}
        elif kind == KIND_SETTLE:
            state["settles"][record["event_id"]] = {
                **record,
                "seq": index,
                "target": normalized_target,
            }
        else:
            state["abandon"] = {**record, "seq": index, "target": normalized_target}

    excluded: dict[str, list[str]] = {
        "blocked": [],
        "unsettled": [],
        "not_landed": [],
        "abandoned": [],
        "legacy": [],
    }
    eligible: list[str] = []
    settled_counts = {"allowed": 0, "blocked": 0, "abandoned": 0}
    for target in sorted(states):
        state = states[target]
        proposal = state["proposal"]
        if proposal is None:
            if state["settles"] or state["abandon"] is not None:
                invalid_lines += 1
            continue
        seqs = [proposal["seq"]]
        seqs.extend(item["seq"] for item in state["settles"].values())
        if state["abandon"] is not None:
            seqs.append(state["abandon"]["seq"])
        latest_seq = max(seqs)
        if latest_seq < global_abandon_seq:
            excluded["abandoned"].append(target)
            settled_counts["abandoned"] += 1
            continue
        abandon = state["abandon"]
        if abandon is not None and abandon["seq"] > proposal["seq"]:
            excluded["abandoned"].append(target)
            settled_counts["abandoned"] += 1
            continue
        if proposal["schema_version"] == "1.0":
            # 1.0 记录没有 kind / outcome，永远不可结算：它不是"未结算"，而是"读不懂结果"。
            excluded["legacy"].append(target)
            continue
        settle = state["settles"].get(proposal["event_id"])
        if settle is None:
            excluded["unsettled"].append(target)
            continue
        if settle["outcome"] == OUTCOME_BLOCKED:
            excluded["blocked"].append(target)
            settled_counts["blocked"] += 1
            continue
        settled_counts["allowed"] += 1
        if proposal["tool"] not in write_tools:
            invalid_lines += 1
            continue
        expected = settle["content_sha256"]
        actual = _file_sha256(Path(workspace), target)
        if expected is None or actual is None or expected != actual:
            excluded["not_landed"].append(target)
            continue
        eligible.append(target)

    truncated = 0
    if max_targets <= 0:
        truncated = len(eligible)
        members: list[str] = []
    elif len(eligible) > max_targets:
        truncated = len(eligible) - max_targets
        members = eligible[:max_targets]
    else:
        members = eligible

    noise = (
        skipped_lines > 0
        or invalid_lines > 0
        or truncated > 0
        or any(values for values in excluded.values())
    )
    if members and not noise:
        status = "applied"
    elif noise:
        status = "partial"
    else:
        status = "empty"
    return BatchView(
        status=status,
        members=tuple(members),
        excluded={key: tuple(sorted(value)) for key, value in excluded.items()},
        settled=dict(settled_counts),
        truncated=truncated,
        skipped_lines=skipped_lines,
        invalid_lines=invalid_lines,
        members_digest=targets_digest(members),
    )


# --------------------------------------------------------------------------- 清理


def prune_expired(
    root: Path | str,
    *,
    ttl_hours: int,
    keep_path: Optional[Path | str] = None,
    now: Optional[float] = None,
) -> int:
    """删除落点目录里 mtime 超过 TTL 的 *.jsonl，返回删除个数。

    两条安全边界都写死在实现里：

    - **目录名必须是 pre-evidence-batches**（解析后的真实路径也算）：一个写错的 root 若指向
      .policy/，这里会把审计、台账、审批文件当"过期批次"删掉——TTL 清理不值得冒这个险；
    - 本次会话自己的文件永不删除（keep_path），符号链接目录/文件一律跳过（只删真实目录下的
      真实文件），每个文件的 OSError 单独吞掉（删不掉只是磁盘占用，不是证据）。

    清理失败**不**改变判定，也**不**改变 batch 记录状态；它只影响磁盘占用。
    """

    directory = Path(root)
    try:
        resolved = directory.resolve()
    except OSError:  # pragma: no cover - 路径解析失败时不做任何删除
        return 0
    if resolved.name != BATCH_DIRNAME or not resolved.is_dir():
        return 0
    if ttl_hours <= 0:
        return 0
    cutoff = (time.time() if now is None else now) - ttl_hours * 3600
    keep = None if keep_path is None else Path(keep_path).resolve()
    removed = 0
    try:
        children = sorted(resolved.iterdir())
    except OSError:  # pragma: no cover - 目录不可读时不做任何删除
        return 0
    for child in children:
        try:
            if child.suffix != ".jsonl" or child.is_symlink() or not child.is_file():
                continue
            if keep is not None and child.resolve() == keep:
                continue
            if child.stat().st_mtime < cutoff:
                child.unlink()
                removed += 1
        except OSError:
            continue
    return removed

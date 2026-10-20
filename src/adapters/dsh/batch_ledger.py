"""批次台账（C1-a，只报告）：把本会话已提议的目标文件落成可按会话折叠的追加写账本。

为什么需要它（04 5.46 / 04 5.68 / 05 3.3）：dsh 的 Hook 是**每次工具调用一个新进程**，批次
状态跨不了进程；判定粒度是单次编辑，`(conftest.py,)` 与 `(conftest.py, order_service.py)`
两种批次会得到 block / allow 两个结论——"先写测试"这条正路会被自己的取证打成警告。
C1-a 只回答"这个会话提议过哪些文件"，**不进** `policy.engine.evaluate`：本模块不导入 policy、
不读规则、不产生任何 allow / block。

三条写死的口径：

1. **按会话分文件**：`<root>/<session_id>.jsonl`，一条记录一行 JSON，UTF-8 + LF，追加写。
   session_id 不是安全的文件名时**拒绝记录**（不 sanitize：洗过的名字会把两个会话并进一个
   文件，那正是"并发会话互相污染"的形状，也正是本台阶要防的事）；
2. **batch_ref 是目标集合的稳定摘要**：同一会话、同一批目标，两次计算逐字节相同。它覆盖
   `session_id + 排序去重的目标集合`，因此不同会话不会撞成同一个批次；`recorded_at` 不参与
   摘要——时间是"这条记录什么时候写下"的事实，不是"这批目标是什么"的事实；
3. **失败不改变判定**：任何 I/O / 解析失败都抛 `BatchLedgerError`，由 Hook 转成一行 stderr
   与审计里的显式状态（`batch.recorded=false` + reason）；本模块**绝不**把异常吞成"记录成功"。

TTL / 保留：`ttl_hours` 只服务 `prune_expired()`。清理是**维护动作**，不参与 batch_ref 计算
（按时间过滤会让"同一批目标"在不同时刻得到两个摘要）。为避免一个写错的 root 把别的
`.policy` 文件当批次删掉，清理只在目录名恰好是 `pre-evidence-batches` 时执行。

本模块不导入 `hooks`（hooks 要导入本模块）；也不导入 `policy`——它只写事实，不做判定。
"""

from __future__ import annotations

import json
import re
import time
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Optional

__all__ = [
    "BATCH_LEDGER_SCHEMA_VERSION",
    "BATCH_DIRNAME",
    "BatchLedgerError",
    "append_target",
    "batch_ref",
    "prune_expired",
    "read_targets",
    "session_filename",
    "targets_digest",
]

# 账本文件自己的协议轴（AGENTS 第 55 条：加键就是改协议）。**不是**审计记录那条轴：
# 判定记录的键集合变更是 `adapters.dsh.hooks.AUDIT_SCHEMA_VERSION` 的事，两者各走各的。
# "1.0" = 首次建轴（C1-a）：记录形状固定为
# {schema_version, session_id, event_id, tool, target, recorded_at}。
BATCH_LEDGER_SCHEMA_VERSION = "1.0"

# 默认落点目录名。TTL 清理只在这个名字的目录里执行（安全边界，见 prune_expired）。
BATCH_DIRNAME = "pre-evidence-batches"

# 摘要前缀：把"摘要覆盖了哪些字段"写进被哈希的字节里，将来改口径必然改变摘要，
# 而不是悄悄产出一个"看起来一样、其实含义不同"的值。
_TARGETS_DIGEST_PREFIX = "pre-evidence-batch-targets/1.0\n"
_BATCH_REF_PREFIX = "pre-evidence-batch/1.0\n"

# session_id 直接当文件名，必须是**单段**安全名字：没有分隔符、没有控制字符、不是 "." / ".."。
# 拒绝而不是清洗：清洗会把两个不同会话映到同一个文件（见模块 docstring 第 1 条）。
_SESSION_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class BatchLedgerError(Exception):
    """批次台账写不进去 / 读不懂：调用方必须显式降级（fail-open），不得当成"记上了"。"""


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
    """批次引用：`session_id + 目标集合` 的稳定摘要（同一批目标两次计算相同）。"""

    filename = session_filename(session_id)
    payload = (
        _BATCH_REF_PREFIX
        + filename[: -len(".jsonl")]
        + "\n"
        + targets_digest(targets)
    )
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def read_targets(path: Path | str) -> tuple[list[str], int]:
    """读出账本里已记录的目标集合与**跳过了几行**。

    跳过的行是事实不是噪声：Hook 被 dsh 杀掉会留下半行 JSON，将来也可能出现本版本不认识的
    `schema_version`。两种情况都不能让"这批目标"悄悄少一个，所以调用方要把跳过数写进审计。
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

    targets: list[str] = []
    skipped = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(record, dict):
            skipped += 1
            continue
        if record.get("schema_version") != BATCH_LEDGER_SCHEMA_VERSION:
            # 未知版本 = 读不懂的内容。跳过**并且**计数：它的目标可能因此不在摘要里，
            # 这件事必须能从审计的 skipped_lines 读到（AGENTS 第 3 条：未知版本不得静默忽略）。
            skipped += 1
            continue
        value = record.get("target")
        if not isinstance(value, str) or not value.strip():
            skipped += 1
            continue
        targets.append(value.strip())
    return targets, skipped


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

    directory = Path(root)
    filename = session_filename(session_id)
    for name, value in (
        ("event_id", event_id),
        ("tool", tool),
        ("target", target),
        ("recorded_at", recorded_at),
    ):
        if not isinstance(value, str) or not value.strip():
            raise BatchLedgerError(f"批次记录字段 {name} 必须是非空字符串")
    normalized_session = session_id.strip()
    normalized_target = target.strip()

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise BatchLedgerError(
            f"批次账本目录建不出来（{type(error).__name__}: {error}）"
        ) from error
    if not directory.is_dir():
        raise BatchLedgerError(f"批次账本落点不是目录：{directory.name}")

    path = directory / filename
    existing, skipped = read_targets(path)
    record = {
        "schema_version": BATCH_LEDGER_SCHEMA_VERSION,
        "session_id": normalized_session,
        "event_id": event_id.strip(),
        "tool": tool.strip(),
        "target": normalized_target,
        "recorded_at": recorded_at.strip(),
    }
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
    except OSError as error:
        raise BatchLedgerError(
            f"批次账本追加写失败（{type(error).__name__}: {error}）"
        ) from error
    # 只有追加成功才把它算进集合：写失败时对外报的是"没记上"，不是"记上了一半"。
    return path, existing + [normalized_target], skipped


def prune_expired(
    root: Path | str,
    *,
    ttl_hours: int,
    keep_path: Optional[Path | str] = None,
    now: Optional[float] = None,
) -> int:
    """删除落点目录里 mtime 超过 TTL 的 `*.jsonl`，返回删除个数。

    两条安全边界都写死在实现里：

    - **目录名必须是 `pre-evidence-batches`**（解析后的真实路径也算）：一个写错的 root 若指向
      `.policy/`，这里会把审计、台账、审批文件当"过期批次"删掉——TTL 清理不值得冒这个险；
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

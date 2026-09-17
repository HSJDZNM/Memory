"""审计链：追加写的 JSONL + 摘要链 + OWASP 口径的日志安全。

设计要点（Phase 4 文档第 6 步与"日志失效与安全"一节）：

- **只写摘要与结论**：工具参数原文、源码内容、模型输出一律不落盘；敏感字段只留哈希。
- **注入安全**：换行、控制字符、超长参数在写入前被中和或截断，日志行数不因载荷而改变。
- **体积上限**：单条记录超过上限直接失败关闭（AuditError），而不是悄悄截断成"看起来完整"的证据。
- **摘要链**：每条记录带 sequence 与 prev_digest，改动历史会破坏链，verify() 能指出来。
- **失败语义**：AuditError 由调用方按风险策略处理——受治理动作默认失败关闭（block）。

本模块不导入任何 Agent SDK，也不知道审计的消费方是谁。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence

from .models import (
    AuditError,
    AuditRecord,
    AuditStage,
    digest_of,
    parse_audit_record,
    to_timestamp,
    utc_now,
)

__all__ = [
    "DEFAULT_MAX_RECORD_BYTES",
    "AuditChain",
    "AuditSink",
    "FileAuditSink",
    "NullAuditSink",
    "REDACTION_PATTERNS",
    "SECRET_VALUE_PATTERNS",
    "contains_secret_value",
    "redact_text",
    "sanitize_payload",
]

DEFAULT_MAX_RECORD_BYTES = 16384
_MAX_STRING_CHARS = 2000
_MAX_DEPTH = 6
_MAX_ITEMS = 64

# 绝对路径与密钥样式：审计里出现它们就等于把环境信息或凭据写进了日志。
_ABS_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\)[^\s'\"]+"  # Windows 盘符 / UNC
    r"|(?<![\w:/])/(?:home|root|etc|usr|var|opt|srv|tmp|mnt|Users)/[^\s'\"]*"  # POSIX 绝对路径
)
# 控制字符一律转义：\x00-\x08、\x0b、\x0c、\x0d（CR）、\x0e-\x1f、\x7f。
# CR 也被转义，避免"看起来像新记录"的载荷出现在审计文本里（OWASP 日志注入）。
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?i)\b(?:sk|pk|ghp|gho|glpat|xox[baprs])[-_][A-Za-z0-9_\-]{8,}"
        ),
        "<redacted-secret>",
    ),
    (
        # "Authorization: Bearer <token>" 必须整体吃掉：否则前缀先被替换，剩下的 token
        # 原文就再也匹配不上任何模式了（复核 D4 的复现）。可选 bearer 前缀因此写在这里。
        re.compile(
            r"(?i)\b(?:api[_-]?key|password|passwd|secret|token|authorization)"
            r"\s*[=:]\s*(?:bearer\s+)?\S+"
        ),
        "<redacted-secret>",
    ),
    (re.compile(r"(?i)\bbearer\s+\S+"), "<redacted-secret>"),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "<redacted-key>",
    ),
)


# 落盘判定的**窄**口径：只认形态确定的凭据。审计脱敏可以用宽口径（多抹一点没有代价），
# 但"参数值能不能写进台账"不能用宽口径——api_key = os.environ[...] 这类普通代码
# 会被宽口径误判，导致委派执行的事后验证大面积退化成"证据不足"。
SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(?:sk|pk|ghp|gho|glpat|xox[baprs])[-_][A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def contains_secret_value(value: Any) -> bool:
    """参数值里是否出现确定形态的凭据；命中就不落盘，宁可事后判"证据不足"。"""

    if not isinstance(value, str):
        value = str(value)
    return any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS)


def redact_text(
    text: Any, *, workspace: Optional[Path | str] = None, limit: int = _MAX_STRING_CHARS
) -> str:
    """脱敏 + 中和：绝对路径、密钥、控制字符都不进审计；长度截断后标注。"""

    if not isinstance(text, str):
        text = str(text)
    if workspace is not None:
        for variant in {str(workspace), Path(workspace).as_posix()}:
            if variant:
                text = text.replace(variant, "<workspace>")
    text = _ABS_PATH_RE.sub("<abs>", text)
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    text = _CONTROL_RE.sub(lambda match: "\\x%02x" % ord(match.group(0)), text)
    if len(text) > limit:
        text = text[: limit - 14] + "...[truncated]"
    return text


def sanitize_payload(
    value: Any, *, workspace: Optional[Path | str] = None, depth: int = 0
) -> Any:
    """把任意载荷递归收敛成"可安全落盘"的形状：字符串脱敏、容器限量、深度受限。"""

    if depth > _MAX_DEPTH:
        return "<depth-limited>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value, workspace=workspace)
    if isinstance(value, Mapping):
        items = list(value.items())[:_MAX_ITEMS]
        return {
            redact_text(key, workspace=workspace, limit=200): sanitize_payload(
                item, workspace=workspace, depth=depth + 1
            )
            for key, item in items
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)[:_MAX_ITEMS]
        return [sanitize_payload(item, workspace=workspace, depth=depth + 1) for item in items]
    return redact_text(value, workspace=workspace, limit=500)


class AuditSink(Protocol):
    """审计端口。写入失败必须抛 AuditError，由调用方按风险策略决定是否继续。"""

    def append(
        self,
        stage: AuditStage,
        *,
        payload: Mapping[str, Any],
        trace_id: Optional[str] = None,
        action_id: Optional[str] = None,
        request_id: Optional[str] = None,
        tool_id: Optional[str] = None,
    ) -> AuditRecord:
        ...


@dataclass
class NullAuditSink:
    """不落盘的审计端口：只用于测试或显式的降级场景（高风险动作不允许使用）。"""

    available: bool = False

    def append(self, stage: AuditStage, **_kwargs: Any) -> AuditRecord:
        raise AuditError("NullAuditSink 不提供持久化审计：按失败策略拒绝继续")


@dataclass
class AuditChain:
    """在已有记录之上维护摘要链的纯计算逻辑（便于单测与重放）。"""

    @staticmethod
    def next_record(
        records: Sequence[Mapping[str, Any]],
        *,
        stage: AuditStage,
        payload: Mapping[str, Any],
        trace_id: Optional[str] = None,
        action_id: Optional[str] = None,
        request_id: Optional[str] = None,
        tool_id: Optional[str] = None,
        now: Optional[Any] = None,
        workspace: Optional[Path | str] = None,
    ) -> AuditRecord:
        previous = ""
        sequence = 1
        for item in records:
            if item.get("schema_version") is None:
                continue
            sequence = int(item.get("sequence", sequence)) + 1
            previous = str(item.get("digest", ""))
        return AuditRecord(
            sequence=sequence,
            stage=stage,
            trace_id=trace_id,
            action_id=action_id,
            request_id=request_id,
            tool_id=tool_id,
            recorded_at=now or utc_now(),
            payload=sanitize_payload(payload, workspace=workspace),
            prev_digest=previous,
        )

    @staticmethod
    def verify(records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
        """校验摘要链与序号连续性，返回问题列表（空列表 = 链完整）。"""

        issues: list[str] = []
        previous = ""
        expected_sequence = 1
        for index, item in enumerate(records):
            try:
                record = parse_audit_record(item)
            except AuditError as error:
                issues.append(f"#{index}: 记录不可解析（{error}）")
                continue
            if record.sequence != expected_sequence:
                issues.append(
                    f"#{index}: 序号 {record.sequence} 与期望 {expected_sequence} 不一致（记录被删除或插入）"
                )
            if record.prev_digest != previous:
                issues.append(f"#{index}: prev_digest 与上一条摘要不一致（链被改动）")
            previous = record.digest
            expected_sequence = record.sequence + 1
        return tuple(issues)


class FileAuditSink:
    """JSONL 审计端口。

    同一个文件里可能存在本层的链式记录与其他历史记录（例如 Phase 2 的 dsh 审计行）；
    链只跟随本层记录，外来行被计数并在 verify() 里显式报告，而不是假装看不见。
    """

    def __init__(
        self,
        path: Path | str,
        *,
        workspace: Optional[Path | str] = None,
        max_record_bytes: int = DEFAULT_MAX_RECORD_BYTES,
    ) -> None:
        self.path = Path(path)
        self.workspace = None if workspace is None else Path(workspace)
        self.max_record_bytes = max_record_bytes
        self.available = True

    # ------------------------------------------------------------------ 读
    def records(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(item for item, _ in self._scan())

    def _scan(self) -> list[tuple[Mapping[str, Any], bool]]:
        if not self.path.is_file():
            return []
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise AuditError(f"审计日志不可读: {self.path.name}（{error}）") from error
        rows: list[tuple[Mapping[str, Any], bool]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # 只有最后一行可能被写坏（进程被杀）；中间行损坏视为审计不可信。
                rows.append(({"raw": line}, False))
                continue
            if isinstance(record, Mapping):
                rows.append((record, record.get("schema_version") is not None))
            else:
                rows.append(({"raw": line}, False))
        return rows

    def chain_records(self) -> tuple[Mapping[str, Any], ...]:
        """只返回本层的链式记录（用于续链与校验）。"""

        return tuple(item for item, chained in self._scan() if chained)

    def foreign_records(self) -> int:
        return sum(1 for _, chained in self._scan() if not chained)

    def verify(self) -> tuple[str, ...]:
        return AuditChain.verify(self.chain_records())

    # ------------------------------------------------------------------ 写
    def append(
        self,
        stage: AuditStage,
        *,
        payload: Mapping[str, Any],
        trace_id: Optional[str] = None,
        action_id: Optional[str] = None,
        request_id: Optional[str] = None,
        tool_id: Optional[str] = None,
        now: Optional[Any] = None,
    ) -> AuditRecord:
        if not self.available:
            raise AuditError("审计端口被标记为不可用：按失败策略拒绝继续")
        record = AuditChain.next_record(
            self.chain_records(),
            stage=stage,
            payload=payload,
            trace_id=trace_id,
            action_id=action_id,
            request_id=request_id,
            tool_id=tool_id,
            now=now,
            workspace=self.workspace,
        )
        line = json.dumps(json.loads(record.model_dump_json()), ensure_ascii=False, sort_keys=True)
        if len(line.encode("utf-8")) > self.max_record_bytes:
            raise AuditError(
                f"审计记录超过 {self.max_record_bytes} 字节上限："
                "宁可失败关闭，也不写一条被截断的证据"
            )
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
                handle.flush()
        except OSError as error:
            raise AuditError(f"审计日志不可写: {self.path.name}（{error}）") from error
        return record

    def final_digest(self) -> str:
        records = self.chain_records()
        return "" if not records else str(records[-1].get("digest", ""))

    def describe(self) -> dict[str, Any]:
        """审计健康度摘要（供 CLI / 证据使用，不含任何载荷内容）。"""

        records = self.chain_records()
        return {
            "path": self.path.as_posix(),
            "chained_records": len(records),
            "foreign_records": self.foreign_records(),
            "issues": list(self.verify()),
            "final_digest": self.final_digest(),
            "updated_at": to_timestamp(utc_now()),
            "digest": digest_of([record.get("digest") for record in records]),
        }

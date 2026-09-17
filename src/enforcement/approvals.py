"""人工审批记录：与 action_hash 绑定、有主体、有时效、单次使用。

Phase 4 文档要求"参数绑定授权与人工门禁"。这里刻意不做任何"自然语言批准"的解析：

- 审批是一条结构化记录（JSON），由人工门禁或审批系统产生；
- 它绑定 action_hash，因此同时绑定参数、工具 schema 与主体，换参数即失效；
- 它有自己的有效期，过期即失效；
- 它只能被消费一次（台账里留 approval_used）。

授予者必须持有 repo.approve 权限——审批权与执行权分开，不能自己批自己。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pydantic import Field, model_validator

from policy.models import StrictModel, canonical_identifier

from .models import (
    ENFORCEMENT_SCHEMA_VERSION,
    EnforcementError,
    to_timestamp,
    utc_now,
)

__all__ = [
    "APPROVAL_SCHEMA_VERSION",
    "ApprovalError",
    "ApprovalRecord",
    "load_approval",
    "verify_approval",
]

APPROVAL_SCHEMA_VERSION = "1.0"


class ApprovalError(EnforcementError):
    """审批缺失、不合法、过期、跨主体或已被使用。一律按失败关闭处理。"""


class ApprovalRecord(StrictModel):
    """一条结构化人工审批。"""

    schema_version: str = ENFORCEMENT_SCHEMA_VERSION
    approval_id: str = Field(min_length=1)
    action_hash: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    subject: str = Field(min_length=1, description="被授权的主体：审批不跨主体")
    granted_by: str = Field(min_length=1, description="审批人标识")
    granted_by_roles: Sequence[str] = Field(
        default_factory=tuple, description="审批人当时持有的角色；必须包含审批角色"
    )
    granted_at: datetime
    expires_at: datetime
    note: str = ""

    @model_validator(mode="after")
    def _check_window(self) -> "ApprovalRecord":
        if self.expires_at <= self.granted_at:
            raise ApprovalError("审批有效期必须为正：过期时间不得早于签发时间")
        return self


def load_approval(path: Path | str) -> ApprovalRecord:
    """读取审批 JSON；未知字段、缺字段、时间格式错误一律拒绝。"""

    approval_path = Path(path)
    if not approval_path.is_file():
        raise ApprovalError(f"审批文件不存在: {approval_path.name}")
    try:
        document = json.loads(approval_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApprovalError(f"审批文件不可解析: {approval_path.name}（{error}）") from error
    if not isinstance(document, Mapping):
        raise ApprovalError("审批文件必须是 JSON 对象")
    try:
        return ApprovalRecord.model_validate(dict(document))
    except ApprovalError:
        raise
    except Exception as error:  # pydantic ValidationError
        raise ApprovalError(f"审批记录不合法：{error}") from error


def verify_approval(
    record: Optional[ApprovalRecord],
    *,
    action_hash: str,
    action_id: str,
    tool_id: str,
    subject: Optional[str],
    approval_roles: Sequence[str],
    used: bool,
    now: Optional[datetime] = None,
) -> None:
    """校验审批与当前动作完全一致；任何不符都抛 ApprovalError。"""

    if record is None:
        raise ApprovalError("该动作需要人工审批，但没有提供与当前 action_hash 绑定的审批记录")
    moment = now or utc_now()
    if record.action_hash != action_hash:
        raise ApprovalError(
            "审批绑定的 action_hash 与当前动作不一致：参数、主体或 schema 已经变化，旧审批作废"
        )
    if record.action_id != action_id:
        raise ApprovalError("审批绑定的 action_id 与当前动作不一致")
    if record.tool_id != tool_id:
        raise ApprovalError("审批绑定的工具与当前动作不一致")
    if subject is None or record.subject != subject:
        raise ApprovalError("审批主体与当前请求主体不一致：审批不得跨主体复用")
    if moment < record.granted_at:
        raise ApprovalError("审批签发时间在未来：凭据不可信，拒绝执行")
    if moment >= record.expires_at:
        raise ApprovalError(f"审批已过期（{to_timestamp(record.expires_at)}）")
    granted_roles = {canonical_identifier(role) for role in record.granted_by_roles}
    allowed_roles = {canonical_identifier(role) for role in approval_roles}
    if not granted_roles & allowed_roles:
        raise ApprovalError(
            "审批人没有审批权：授予者角色 "
            f"{sorted(granted_roles) or ['<none>']} 与具备审批权的角色 {sorted(allowed_roles)} 无交集"
        )
    if used:
        raise ApprovalError("审批已被使用：单次审批不得重复提交同一个动作")


def approval_payload(record: ApprovalRecord) -> dict[str, Any]:
    return json.loads(record.model_dump_json())

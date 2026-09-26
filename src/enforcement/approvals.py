"""人工审批记录：绑定一次具体调用（默认、更严格）或绑定"一类调用"（可选档）。

Phase 4 文档要求"参数绑定授权与人工门禁"。这里刻意不做任何"自然语言批准"的解析：

- 审批是一条结构化记录（JSON），由人工门禁或审批系统产生；
- 它有自己的有效期，过期即失效；
- 未知字段、未知 binding、自相矛盾的字段组合一律在加载期报错。

两种绑定档位（binding）：

1. **action（默认，单次绑定，更严格）**：逐位绑定 action_hash 与 action_id。
   action_hash 覆盖工具 schema、规范化参数、主体、权限与上下文摘要，
   因此"换参数继续用旧条子"在数学上不可能；一次消费之后即失效。
2. **pattern（模式化）**：绑定"工具 + 规范化参数模式 + 主体/角色 + 生效窗口 + 次数上限"。
   它解决的是一个真实可用性缺陷：action_id / tool_use_id 是 Agent 运行时每次现生成的，
   人签条子时不可能知道下一个编号，于是"同一条命令、只换调用编号"条子立刻作废，
   受治理的会话连 pytest 都跑不了。

**模式化审批不削弱任何防重放性质**：

- 按 action_id 的重复拦截完全不变，由台账与审计链两处把关（与审批无关）；
- 次数上限由台账**先原子占用、再执行**，写进审计；用尽 / 过期 / 主体不符一律拒绝；
- 参数一变、模式匹配不上即拒绝（旧授权自动失效）；
- 单次绑定仍然是默认档，且不许与模式字段混写（自相矛盾的声明直接拒绝）。

授予者必须持有 repo.approve 权限——审批权与执行权分开，不能自己批自己。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pydantic import Field, field_validator, model_validator

from policy.models import StrictModel, canonical_identifier

from .models import (
    ENFORCEMENT_SCHEMA_VERSION,
    EnforcementError,
    to_timestamp,
    utc_now,
)

__all__ = [
    "APPROVAL_SCHEMA_VERSION",
    "ApprovalBinding",
    "ApprovalError",
    "ApprovalRecord",
    "approval_payload",
    "load_approval",
    "verify_approval",
]

APPROVAL_SCHEMA_VERSION = "1.0"

# 参数模式名与参数名同口径（稳定标识符）：允许点号，便于将来扩展到嵌套结构。
_PATTERN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class ApprovalError(EnforcementError):
    """审批缺失、不合法、过期、跨主体、次数用尽或已被使用。一律按失败关闭处理。"""


class ApprovalBinding(str, Enum):
    """审批绑定档位。默认 action（单次绑定）；pattern 是可选档，不是替代品。"""

    ACTION = "action"
    PATTERN = "pattern"


class ApprovalRecord(StrictModel):
    """一条结构化人工审批。

    binding=action 时必须有 action_hash 与 action_id 且 max_uses=1、param_patterns 为空；
    binding=pattern 时二者必须缺省（模式化审批应当对未来那次调用有效），
    且必须声明至少一条 param_patterns 与次数上限——否则"模式"就成了无边界的通行证。
    """

    schema_version: str = ENFORCEMENT_SCHEMA_VERSION
    approval_id: str = Field(min_length=1)
    binding: ApprovalBinding = ApprovalBinding.ACTION
    action_hash: Optional[str] = Field(
        default=None, min_length=1, description="单次绑定：被授权动作的 action_hash（逐位一致）"
    )
    action_id: Optional[str] = Field(
        default=None, min_length=1, description="单次绑定：被授权动作的 action_id（逐位一致）"
    )
    tool_id: str = Field(min_length=1)
    subject: str = Field(min_length=1, description="被授权的主体：审批不跨主体")
    granted_by: str = Field(min_length=1, description="审批人标识")
    granted_by_roles: Sequence[str] = Field(
        default_factory=tuple, description="审批人当时持有的角色；必须包含审批角色"
    )
    granted_at: datetime
    expires_at: datetime
    max_uses: int = Field(
        default=1, ge=1, description="这条审批最多允许几次调用；单次绑定只能是 1"
    )
    param_patterns: Mapping[str, str] = Field(
        default_factory=dict,
        description="模式化绑定：参数名 -> 整串匹配正则（对规范化后的取值做 re.fullmatch）",
    )
    note: str = ""

    @field_validator("param_patterns")
    @classmethod
    def _check_patterns(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        if not isinstance(value, Mapping):
            raise ApprovalError("param_patterns 必须是 参数名 -> 正则 的映射")
        normalized: dict[str, str] = {}
        for raw_name, raw_pattern in value.items():
            name = str(raw_name).strip()
            if not name or _PATTERN_NAME_RE.fullmatch(name) is None:
                raise ApprovalError(f"审批模式里的参数名必须是稳定标识符，得到 {raw_name!r}")
            if not isinstance(raw_pattern, str) or not raw_pattern.strip():
                raise ApprovalError(f"审批模式 {name!r} 的正则不能为空")
            pattern = raw_pattern.strip()
            try:
                re.compile(pattern)
            except re.error as error:
                raise ApprovalError(f"审批模式 {name!r} 的正则不合法: {error}") from error
            normalized[name] = pattern
        return normalized

    @model_validator(mode="after")
    def _check_shape(self) -> "ApprovalRecord":
        if self.expires_at <= self.granted_at:
            raise ApprovalError("审批有效期必须为正：过期时间不得早于签发时间")
        if self.binding is ApprovalBinding.ACTION:
            if not self.action_hash or not self.action_id:
                raise ApprovalError(
                    "单次绑定（binding=action）必须声明 action_hash 与 action_id："
                    "不知道绑哪一次调用就不是单次绑定"
                )
            if self.max_uses != 1:
                raise ApprovalError(
                    "单次绑定（binding=action）的 max_uses 只能是 1；"
                    "要多次使用请显式改成 binding=pattern 并写清参数模式与上限"
                )
            if self.param_patterns:
                raise ApprovalError(
                    "单次绑定（binding=action）不得声明 param_patterns："
                    "两种档位的字段混写会让'到底绑了什么'无法解释"
                )
        else:
            if self.action_hash or self.action_id:
                raise ApprovalError(
                    "模式化审批（binding=pattern）不得声明 action_hash / action_id："
                    "调用编号是运行期现生成的，绑它等于把条子签死；要绑单次请写 binding=action"
                )
            if not self.param_patterns:
                raise ApprovalError(
                    "模式化审批必须声明至少一条 param_patterns："
                    "没有参数模式的'一类调用'等于一张无边界通行证"
                )
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


def pattern_text(value: Any, *, name: str) -> str:
    """把规范化后的参数取值渲染成可做整串匹配的文本；不支持的形状直接拒绝。"""

    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    raise ApprovalError(
        f"参数 {name!r} 的取值类型是 {type(value).__name__}，不支持模式匹配："
        "模式只支持字符串 / 整数 / 布尔参数，列表类参数请改用 binding=action 的单次绑定"
    )


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
    params: Optional[Mapping[str, Any]] = None,
    uses: int = 0,
) -> None:
    """校验审批与当前动作一致；任何不符都抛 ApprovalError。

    公共性质（两种档位都查）：工具、主体、签发时间不在未来、未过期、授予者持有审批角色。
    binding=action 追加：action_hash 与 action_id 逐位一致，且未被消费过（used=False）。
    binding=pattern 追加：次数未用尽，且每个声明的参数模式都整串匹配当前规范化取值。
    """

    if record is None:
        raise ApprovalError("该动作需要人工审批，但没有提供与当前 action_hash 绑定的审批记录")
    moment = now or utc_now()
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

    if record.binding is ApprovalBinding.ACTION:
        if record.action_hash != action_hash:
            raise ApprovalError(
                "审批绑定的 action_hash 与当前动作不一致：参数、主体或 schema 已经变化，旧审批作废"
            )
        if record.action_id != action_id:
            raise ApprovalError("审批绑定的 action_id 与当前动作不一致")
        if used:
            raise ApprovalError("审批已被使用：单次审批不得重复提交同一个动作")
        return

    # binding=pattern
    if uses >= record.max_uses:
        raise ApprovalError(
            f"审批的次数上限已用尽（已用 {uses}/{record.max_uses} 次）：必须重新签发"
        )
    if params is None:
        raise ApprovalError(
            "模式化审批需要本次请求的规范化参数才能校验模式：拿不到参数就拒绝（证明不了即失败关闭）"
        )
    for name in sorted(record.param_patterns):
        pattern = record.param_patterns[name]
        if name not in params:
            raise ApprovalError(
                f"审批模式声明的参数 {name!r} 不在本次请求里：模式匹配不上，拒绝执行"
            )
        text = pattern_text(params[name], name=name)
        if re.fullmatch(pattern, text) is None:
            raise ApprovalError(
                f"参数 {name!r} 的取值不匹配审批模式 {pattern!r}（整串匹配）："
                "参数一变旧授权自动失效"
            )


def approval_payload(record: ApprovalRecord) -> dict[str, Any]:
    return json.loads(record.model_dump_json())

"""Action Request：把一次工具调用规范化成不可变、可哈希、可绑定的请求。

职责：

1. **参数 allowlist 与规范化**：只有注册表声明过的参数能进来；类型、长度、正则、
   枚举与路径作用域逐项校验。未知参数直接拒绝——allowlist 只看完整名字，
   不做前缀匹配，也不做"看着像"的猜测。
2. **上下文摘要**：把显式 PolicyContext（以及可选的检索来源 ID）压成一个摘要，
   让"这次动作是在什么上下文里提出的"进入 action_hash，但不把源码或用户消息写进审计。
3. **action_hash**：工具身份 + schema 版本与哈希 + 规范化参数 + 主体 + 权限 +
   上下文摘要 + request/action 标识。哈希一致才可能有授权。

本模块不执行任何工具、不读规则、不写审计。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from policy.context import repo_relative_path
from policy.models import (
    PolicyContext,
    PolicyContextError,
    canonical_identifier,
)

from .models import (
    ActionRequest,
    ActionRequestError,
    EffectKind,
    ParamSpec,
    ParamType,
    ParamValue,
    ReasonCode,
    ToolSpec,
    digest_of,
    utc_now,
)

__all__ = [
    "ActionRequestError",
    "build_action_request",
    "context_digest",
    "normalize_params",
    "redacted_request_payload",
    "required_permissions_for",
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _fail(reason: ReasonCode, detail: str) -> ActionRequestError:
    return ActionRequestError(f"[{reason.value}] {detail}")


def _require_identifier(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(ReasonCode.PARAM_INVALID, f"{where} 必须是非空字符串，得到 {value!r}")
    token = value.strip()
    if not _IDENTIFIER_RE.match(token):
        raise _fail(
            ReasonCode.PARAM_INVALID,
            f"{where} 必须匹配 {_IDENTIFIER_RE.pattern}（便于审计关联，不接受任意文本），得到 {value!r}",
        )
    return token


def _normalize_path(value: Any, *, name: str, workspace: Optional[Path]) -> str:
    """路径参数统一成工作区相对路径；逃出工作区一律拒绝。"""

    if not isinstance(value, str) or not value.strip():
        raise _fail(ReasonCode.PARAM_INVALID, f"参数 {name} 必须是路径字符串，得到 {value!r}")

    raw = value.strip()
    if workspace is None:
        # 没有工作区锚点时只接受相对路径：绝对路径无法证明落在受控范围内。
        if Path(raw).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", raw):
            raise _fail(
                ReasonCode.PATH_OUT_OF_SCOPE,
                f"参数 {name} 是绝对路径 {raw!r}，但没有声明工作区锚点，拒绝处理",
            )
        try:
            return repo_relative_path(raw)
        except PolicyContextError as error:
            raise _fail(ReasonCode.PATH_OUT_OF_SCOPE, str(error)) from error

    try:
        return repo_relative_path(raw, repo_root=workspace)
    except PolicyContextError as error:
        raise _fail(
            ReasonCode.PATH_OUT_OF_SCOPE,
            f"参数 {name} 不在受控工作区 {Path(workspace).name} 内：{error}",
        ) from error


def _normalize_scalar(spec: ParamSpec, raw: Any, *, workspace: Optional[Path]) -> Any:
    """按声明的类型规范化单个值；类型不符宁可拒绝，也不做宽松转换。"""

    name = spec.name
    if spec.type is ParamType.STRING:
        if not isinstance(raw, str):
            raise _fail(ReasonCode.PARAM_INVALID, f"参数 {name} 必须是字符串，得到 {type(raw).__name__}")
        return raw
    if spec.type is ParamType.PATH:
        return _normalize_path(raw, name=name, workspace=workspace)
    if spec.type is ParamType.INTEGER:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise _fail(ReasonCode.PARAM_INVALID, f"参数 {name} 必须是整数，得到 {raw!r}")
        return raw
    if spec.type is ParamType.BOOLEAN:
        if not isinstance(raw, bool):
            raise _fail(ReasonCode.PARAM_INVALID, f"参数 {name} 必须是布尔值，得到 {raw!r}")
        return raw
    if spec.type is ParamType.STRING_LIST:
        if not isinstance(raw, (list, tuple)):
            raise _fail(
                ReasonCode.PARAM_INVALID, f"参数 {name} 必须是字符串列表，得到 {type(raw).__name__}"
            )
        items: list[str] = []
        for item in raw:
            if not isinstance(item, str) or not item.strip():
                raise _fail(ReasonCode.PARAM_INVALID, f"参数 {name} 的元素必须是非空字符串")
            token = item.strip()
            if spec.max_item_chars is not None and len(token) > spec.max_item_chars:
                raise _fail(
                    ReasonCode.PARAM_INVALID,
                    f"参数 {name} 的单个元素长度 {len(token)} 超过上限 {spec.max_item_chars}",
                )
            items.append(token)
        if spec.max_items is not None and len(items) > spec.max_items:
            raise _fail(
                ReasonCode.PARAM_INVALID,
                f"参数 {name} 的元素个数 {len(items)} 超过上限 {spec.max_items}",
            )
        return tuple(items)
    raise _fail(ReasonCode.PARAM_INVALID, f"参数 {name} 声明了未知类型 {spec.type!r}")


def _check_constraints(spec: ParamSpec, value: Any) -> None:
    name = spec.name
    text = None
    if isinstance(value, str):
        text = value
    if text is not None:
        if spec.max_chars is not None and len(text) > spec.max_chars:
            raise _fail(
                ReasonCode.PARAM_INVALID,
                f"参数 {name} 长度 {len(text)} 超过上限 {spec.max_chars}",
            )
        if spec.pattern is not None and re.fullmatch(spec.pattern, text) is None:
            raise _fail(
                ReasonCode.PARAM_INVALID,
                f"参数 {name} 不匹配声明模式 {spec.pattern!r}（整串匹配）",
            )
        if spec.enum and text not in spec.enum:
            raise _fail(
                ReasonCode.PARAM_INVALID,
                f"参数 {name} 取值 {text!r} 不在允许集合 {list(spec.enum)} 内",
            )


def _param_value(spec: ParamSpec, value: Any) -> ParamValue:
    if isinstance(value, tuple):
        chars = sum(len(item) for item in value)
        canonical: Any = list(value)
    elif isinstance(value, bool):
        chars = 1
        canonical = value
    else:
        chars = len(str(value))
        canonical = value
    return ParamValue(
        name=spec.name,
        type=spec.type,
        value=value,
        chars=chars,
        digest=digest_of({"name": spec.name, "value": canonical}),
        secret=spec.secret,
    )


def normalize_params(
    spec: ToolSpec, raw: Mapping[str, Any], *, workspace: Optional[Path | str] = None
) -> Tuple[ParamValue, ...]:
    """按注册表声明的参数表规范化调用参数。未知参数、缺失必需项、类型错误一律拒绝。"""

    if not isinstance(raw, Mapping):
        raise _fail(ReasonCode.PARAM_INVALID, f"工具参数必须是映射，得到 {type(raw).__name__}")

    anchor = None if workspace is None else Path(workspace)
    declared = {item.name: item for item in spec.parameters}
    unknown = sorted(str(name) for name in raw if name not in declared)
    if unknown:
        raise _fail(
            ReasonCode.PARAM_UNKNOWN,
            f"{spec.id}: 出现未声明的参数 {unknown}；"
            f"允许的参数为 {sorted(declared)}。allowlist 只做完整匹配，不做前缀或模糊匹配",
        )

    values: list[ParamValue] = []
    for name, param in sorted(declared.items()):
        if name not in raw or raw[name] is None:
            if param.required:
                raise _fail(
                    ReasonCode.PARAM_REQUIRED_MISSING,
                    f"{spec.id}: 缺少必需参数 {name}；缺失的安全关键参数不得由调用方猜测",
                )
            continue
        value = _normalize_scalar(param, raw[name], workspace=anchor)
        _check_constraints(param, value)
        values.append(_param_value(param, value))
    return tuple(values)


def required_permissions_for(spec: ToolSpec, params: Sequence[ParamValue]) -> Tuple[str, ...]:
    """工具声明的权限 + 参数取值触发的额外权限（参数绑定授权）。"""

    required = set(spec.required_permissions)
    for item in params:
        declaration = spec.parameter(item.name)
        if declaration is None or not declaration.escalating_values:
            continue
        candidates = item.value if isinstance(item.value, tuple) else (item.value,)
        if any(str(candidate) in declaration.escalating_values for candidate in candidates):
            assert declaration.requires_permission is not None
            required.add(declaration.requires_permission)
    return tuple(sorted(required))


def context_digest(
    context: Optional[PolicyContext], *, sources: Sequence[str] = (), extra: Optional[Mapping[str, Any]] = None
) -> str:
    """把显式上下文压成摘要；没有上下文的动作也要留下"当时没有上下文"的痕迹。"""

    payload: dict[str, Any] = {
        "policy_context": None if context is None else json.loads(context.model_dump_json()),
        "sources": sorted(str(item) for item in sources),
    }
    if extra:
        payload["extra"] = json.loads(json.dumps(dict(extra), default=str, sort_keys=True))
    return digest_of(payload)


def build_action_request(
    spec: ToolSpec,
    raw_params: Mapping[str, Any],
    *,
    action_id: str,
    request_id: str,
    agent: str,
    trace_id: Optional[str] = None,
    agent_version: Optional[str] = None,
    subject: Optional[str] = None,
    roles: Sequence[str] = (),
    permissions: Sequence[str] = (),
    context: Optional[PolicyContext] = None,
    sources: Sequence[str] = (),
    context_extra: Optional[Mapping[str, Any]] = None,
    workspace: Optional[Path | str] = None,
    ttl_seconds: int = 60,
    now: Optional[Any] = None,
) -> ActionRequest:
    """构造不可变 Action Request；参数与标识都会被规范化后进入 action_hash。"""

    if not isinstance(spec, ToolSpec):
        raise ActionRequestError(f"spec 必须是 ToolSpec，得到 {type(spec).__name__}")
    if ttl_seconds <= 0:
        raise ActionRequestError("ttl_seconds 必须为正：没有时效的允许结果等于永久授权")

    moment = now or utc_now()
    params = normalize_params(spec, raw_params, workspace=workspace)
    from datetime import timedelta

    return ActionRequest(
        action_id=_require_identifier(action_id, where="action_id"),
        request_id=_require_identifier(request_id, where="request_id"),
        trace_id=None if trace_id is None else str(trace_id).strip() or None,
        agent=agent,
        agent_version=None if agent_version is None else canonical_identifier(str(agent_version)),
        tool_id=spec.id,
        tool_name=spec.tool_name,
        tool_schema_version=spec.schema_version,
        tool_schema_hash=spec.schema_hash,
        risk=spec.risk,
        effect=spec.effect if isinstance(spec.effect, EffectKind) else EffectKind(spec.effect),
        driver=spec.driver,
        params=params,
        param_digest=digest_of({item.name: item.canonical() for item in params}),
        subject=None if subject is None else str(subject).strip() or None,
        roles=tuple(sorted({canonical_identifier(role) for role in roles if str(role).strip()})),
        permissions=tuple(sorted(set(permissions))),
        context_digest=context_digest(context, sources=sources, extra=context_extra),
        workspace=None if workspace is None else Path(workspace).as_posix(),
        created_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds),
    )


def redacted_request_payload(request: ActionRequest) -> dict[str, Any]:
    """审计 / CLI 输出用的请求视图：secret 参数只留摘要，绝不打印原文。"""

    payload = json.loads(request.model_dump_json())
    payload["params"] = [
        {
            "name": item.name,
            "type": item.type.value,
            "chars": item.chars,
            "digest": item.digest,
            "secret": item.secret,
            "value": None if item.secret else item.canonical(),
        }
        for item in request.params
    ]
    return payload

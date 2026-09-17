"""PolicyContext 规范化器：Adapter 进入核心层的唯一入口。

职责：把"原始请求"变成规范化的 PolicyContext，不读取文件、不调用 LLM、不猜字段。

规范化规则（对应 Phase 1 文档第 2 步）：

1. 路径统一为仓库相对 "/" 路径；绝对路径必须能用 repo_root 归一，否则拒绝；
2. language / layer / module / project / agent 统一小写（canonical_identifier）；
3. operation 使用受控枚举，未知操作直接拒绝，不降级为"无操作"；
4. dependencies 去重并按稳定顺序排序（由模型负责，这里只保证入口一致）；
5. 路径逃出仓库、空主体、安全关键字段缺失一律拒绝（失败关闭）；
6. 不根据文件名、目录或扩展名推断 principal、权限或审批状态。

build_context 与 normalize_context 互为一组：后者对规范化过的上下文是恒等回环。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional

from pydantic import ValidationError

from .models import (
    Operation,
    PolicyContext,
    PolicyContextError,
    Principal,
    RuleValidationError,
    normalize_repo_path,
)

__all__ = [
    "CONTEXT_FIELDS",
    "REQUIRED_FIELDS",
    "build_context",
    "normalize_context",
    "normalize_operation",
    "repo_relative_path",
]

# 安全关键字段：缺失时必须失败关闭，不得猜测、不得退化成"无策略通过"。
REQUIRED_FIELDS: tuple[str, ...] = ("request_id", "file", "layer")

CONTEXT_FIELDS: frozenset[str] = frozenset(PolicyContext.model_fields)

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _is_absolute_path(value: str) -> bool:
    """跨平台判断绝对路径：Windows 盘符、UNC、以分隔符开头、或平台绝对路径。"""

    return bool(
        _WINDOWS_DRIVE_RE.match(value) or value.startswith(("/", "\\")) or os.path.isabs(value)
    )


def repo_relative_path(value: Any, *, repo_root: Path | str | None = None) -> str:
    """把路径规范化为仓库相对路径。

    相对路径直接规范化（拒绝 ".." 逃逸）；绝对路径必须落在 repo_root 之内，
    否则抛出 PolicyContextError —— 宁可拒绝，也不能把仓库外的文件当成仓库内文件。
    """

    if not isinstance(value, str):
        raise PolicyContextError(f"file 必须是字符串，得到 {type(value).__name__}")

    raw = value.strip()
    if not raw:
        raise PolicyContextError("file 不能为空")

    raw = raw.replace("\\", "/")
    if not _is_absolute_path(raw):
        return normalize_repo_path(raw)

    if repo_root is None:
        raise PolicyContextError(f"绝对路径需要 repo_root 才能转成仓库相对路径: {raw!r}")

    anchor = Path(repo_root).resolve()
    target = Path(raw).resolve()
    anchor_parts = anchor.parts
    target_parts = target.parts
    head = target_parts[: len(anchor_parts)]
    if len(target_parts) <= len(anchor_parts) or [item.lower() for item in head] != [
        item.lower() for item in anchor_parts
    ]:
        raise PolicyContextError(f"路径不在仓库 {anchor} 之内，拒绝处理: {raw!r}")

    return normalize_repo_path("/".join(target_parts[len(anchor_parts) :]))


def normalize_operation(value: Any) -> Optional[Operation]:
    """把操作规范化为受控枚举；未知操作报错而不是当成"没有操作"。"""

    if value is None or isinstance(value, Operation):
        return value
    if not isinstance(value, str):
        raise PolicyContextError(f"operation 必须是字符串，得到 {type(value).__name__}")

    token = value.strip().lower()
    if not token:
        raise PolicyContextError("operation 不能是空字符串；没有操作就写 null")
    try:
        return Operation(token)
    except ValueError:
        known = sorted(item.value for item in Operation)
        raise PolicyContextError(
            f"未知操作 {value!r}；受控操作枚举为 {known}，拒绝猜测"
        ) from None


def _check_principal(value: Any) -> Optional[Principal]:
    """principal 只能由调用方显式提供；不得从文件名、路径或用户消息推断。"""

    if value is None or isinstance(value, Principal):
        return value
    if isinstance(value, Mapping):
        try:
            return Principal.model_validate(dict(value))
        except ValidationError as error:
            raise PolicyContextError(
                str(RuleValidationError.from_pydantic(error, model_name="principal"))
            ) from error
    raise PolicyContextError(
        f"principal 必须是 {{subject, roles}} 结构或 null，得到 {type(value).__name__}；"
        "主体信息不得由 Adapter 猜测"
    )


def build_context(
    data: Mapping[str, Any], *, repo_root: Path | str | None = None
) -> PolicyContext:
    """把原始映射规范化成 PolicyContext；任何不符合约定的输入都直接失败。"""

    if not isinstance(data, Mapping):
        raise PolicyContextError(f"上下文必须是映射，得到 {type(data).__name__}")

    unknown = sorted(set(data) - CONTEXT_FIELDS)
    if unknown:
        raise PolicyContextError(
            f"未知上下文字段 {unknown}；允许的字段为 {sorted(CONTEXT_FIELDS)}"
        )

    missing = [name for name in REQUIRED_FIELDS if not str(data.get(name) or "").strip()]
    if missing:
        raise PolicyContextError(f"安全关键字段缺失：{missing}；不得猜测，按失败策略拒绝执行")

    payload: dict[str, Any] = dict(data)
    payload["file"] = repo_relative_path(payload["file"], repo_root=repo_root)
    payload["operation"] = normalize_operation(payload.get("operation"))
    payload["principal"] = _check_principal(payload.get("principal"))

    try:
        return PolicyContext(**payload)
    except ValidationError as error:
        raise PolicyContextError(
            str(RuleValidationError.from_pydantic(error, model_name="PolicyContext"))
        ) from error


def normalize_context(context: PolicyContext) -> PolicyContext:
    """把已有 PolicyContext 归一化；对规范化过的上下文是恒等操作。"""

    if not isinstance(context, PolicyContext):
        raise PolicyContextError(
            f"normalize_context 只接受 PolicyContext，得到 {type(context).__name__}"
        )
    return build_context(context.model_dump())

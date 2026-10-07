"""Action Request 模型的不变量：哈希口径与取值口径必须指向同一个参数集合。

对应 AGENTS.md 第 14 条：action_hash 覆盖工具 schema 哈希、规范化参数、主体、权限与
上下文摘要——"参数变一个字符旧授权即失效"。重名参数会让这条承诺落空：
param() / value_of() 取首个匹配，而 hash_payload() 的 params 是字典推导（last-wins）。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from enforcement.action import _check_constraints
from enforcement.models import (
    ActionRequest,
    ActionRequestError,
    DriverKind,
    EffectKind,
    ParamSpec,
    ParamType,
    ParamValue,
    PathKind,
    RiskLevel,
    digest_of,
    utc_now,
)


@pytest.mark.parametrize(
    "declaration",
    [
        {"name": "timeoutMs", "type": "integer", "enum": ("1", "2")},
        {"name": "run_in_background", "type": "boolean", "pattern": "true|false"},
        {"name": "argv", "type": "string_list", "max_items": 2, "max_chars": 10},
        {"name": "argv", "type": "string_list", "max_items": 2, "enum": ("a",)},
    ],
)
def test_text_constraints_on_unsupported_types_are_rejected_at_load(declaration):
    """pattern / max_chars / enum 只对 string 与 path 生效：声明在别的类型上加载期拒绝。

    action._check_constraints 只对字符串取值做这三项校验，静默跳过等于"接受了但不执行"。
    """

    with pytest.raises(ValidationError) as error:
        ParamSpec(**declaration)

    assert "只适用于 string 与 path" in str(error.value)


def test_declared_text_constraints_are_never_silently_skipped():
    """绕过加载期校验的 Spec（model_construct）也不许静默跳过已声明的约束。"""

    spec = ParamSpec.model_construct(
        name="timeoutMs",
        type=ParamType.INTEGER,
        required=True,
        description="",
        max_chars=None,
        max_items=None,
        max_item_chars=None,
        pattern="\\d+",
        enum=(),
        path_scope=None,
        path_kind=PathKind.FILE,
        blocked_prefixes=(),
        escalating_values=(),
        requires_permission=None,
        secret=False,
    )

    with pytest.raises(ActionRequestError) as error:
        _check_constraints(spec, 5)

    assert "无法执行这些约束" in str(error.value)


def param(name: str, value: str) -> ParamValue:
    return ParamValue(
        name=name,
        type=ParamType.STRING,
        value=value,
        chars=len(value),
        digest=digest_of({"name": name, "value": value}),
    )


def request_payload(**overrides):
    payload = dict(
        schema_version="1.0",
        action_id="a-1",
        request_id="r-1",
        agent="dsh",
        tool_id="fs.write",
        tool_name="write",
        tool_schema_version="1.0",
        tool_schema_hash="sha256:s",
        risk=RiskLevel.REVERSIBLE_WRITE,
        effect=EffectKind.FILE_WRITE,
        driver=DriverKind.FILE_WRITE,
        param_digest="sha256:p",
        context_digest="sha256:c",
        created_at=utc_now(),
    )
    payload.update(overrides)
    return payload


def test_duplicate_param_names_are_rejected():
    """重名参数让「哈希绑定的值」与「执行时读的值」可以是两个不同的值。

    旧口径实测（.tmp/repro-dup-params.py）：两份请求只有**首个** content 不同
    （A / B）、末个相同（LAST），action_hash 逐字节相同，而 value_of("content")
    分别是 A / B——一份授权因此能落到另一个参数值上执行。
    """

    with pytest.raises(ValidationError) as error:
        ActionRequest(
            **request_payload(),
            params=(param("content", "A"), param("content", "LAST")),
        )
    assert "重复" in str(error.value)


def test_distinct_param_values_still_produce_distinct_hashes():
    """反真空：单值请求的参数一变，action_hash 必须跟着变。"""

    first = ActionRequest(**request_payload(), params=(param("content", "A"),))
    second = ActionRequest(**request_payload(), params=(param("content", "B"),))

    assert first.action_hash != second.action_hash
    assert first.value_of("content") == "A"

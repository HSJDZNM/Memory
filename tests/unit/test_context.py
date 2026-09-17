"""Phase 1 上下文规范化测试：路径、枚举、去重、失败关闭、不猜字段。"""

from __future__ import annotations

import pytest

from policy.context import (
    CONTEXT_FIELDS,
    REQUIRED_FIELDS,
    build_context,
    normalize_context,
    normalize_operation,
    repo_relative_path,
)
from policy.models import Operation, PolicyContext, PolicyContextError, Principal

from conftest import REPO_ROOT, make_context

WINDOWS_PATH = "src" + chr(92) + "order" + chr(92) + "controller.py"


def test_windows_and_posix_paths_normalize_identically() -> None:
    windows = build_context(
        {"request_id": "req-1", "file": WINDOWS_PATH, "layer": "Controller"}
    )
    posix = build_context(
        {"request_id": "req-1", "file": "src/order/controller.py", "layer": "controller"}
    )

    assert windows.file == posix.file == "src/order/controller.py"
    assert windows.model_dump() == posix.model_dump()


@pytest.mark.parametrize(
    "raw",
    [
        "../secrets.env",
        "src/../../escape.py",
        "./../outside.py",
        "..",
    ],
)
def test_paths_escaping_the_repository_are_rejected(raw: str) -> None:
    with pytest.raises(PolicyContextError) as error:
        build_context({"request_id": "req-1", "file": raw, "layer": "controller"})

    assert "逃出仓库" in str(error.value) or "仓库根目录" in str(error.value)


@pytest.mark.parametrize(
    "raw",
    [
        "/etc/passwd",
        "C:/Users/other/repo/file.py",
        "D:" + chr(92) + "repo" + chr(92) + "file.py",
        chr(92) + chr(92) + "server" + chr(92) + "share" + chr(92) + "file.py",
    ],
)
def test_absolute_paths_outside_the_repository_are_rejected(raw: str) -> None:
    with pytest.raises(PolicyContextError) as error:
        build_context(
            {"request_id": "req-1", "file": raw, "layer": "controller"}, repo_root=REPO_ROOT
        )

    assert "拒绝处理" in str(error.value) or "repo_root" in str(error.value)


def test_absolute_path_inside_repository_becomes_relative() -> None:
    absolute = str(REPO_ROOT / "examples" / "good_controller.py")

    context = build_context(
        {"request_id": "req-1", "file": absolute, "layer": "controller"}, repo_root=REPO_ROOT
    )

    assert context.file == "examples/good_controller.py"


def test_absolute_path_without_repo_root_is_rejected() -> None:
    with pytest.raises(PolicyContextError) as error:
        repo_relative_path(str(REPO_ROOT / "examples" / "good_controller.py"))

    assert "repo_root" in str(error.value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("src/order/controller.py", "src/order/controller.py"),
        ("./src//order/controller.py", "src/order/controller.py"),
        ("  src/order/controller.py  ", "src/order/controller.py"),
        (WINDOWS_PATH, "src/order/controller.py"),
    ],
)
def test_repo_relative_path_variants(raw: str, expected: str) -> None:
    assert repo_relative_path(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("EDIT", Operation.EDIT),
        ("  execute ", Operation.EXECUTE),
        (Operation.READ, Operation.READ),
        (None, None),
    ],
)
def test_operation_normalization_is_fixed(raw: object, expected: object) -> None:
    assert normalize_operation(raw) is expected


@pytest.mark.parametrize("raw", ["deploy", "", "  ", 7, ["edit"]])
def test_unknown_operation_is_rejected(raw: object) -> None:
    """未知操作必须报错：降级成"没有操作"会让 operation 范围的规则悄悄失效。"""

    with pytest.raises(PolicyContextError):
        normalize_operation(raw)


def test_dimension_case_policy_is_uniform() -> None:
    context = build_context(
        {
            "request_id": "  req-1  ",
            "file": "src/order/controller.py",
            "layer": "  Controller ",
            "language": "Python",
            "module": "Order",
            "project": "Shop",
            "agent": "DSH",
            "task": "  Add order creation API  ",
            "trace_id": "  trace-9 ",
        }
    )

    assert context.request_id == "req-1"
    assert context.layer == "controller"
    assert context.language == "python"
    assert context.module == "order"
    assert context.project == "shop"
    assert context.agent == "dsh"
    assert context.trace_id == "trace-9"
    # task 是给人的描述，只去首尾空白，不做大小写折叠
    assert context.task == "Add order creation API"


def test_dependencies_are_deduped_and_stably_sorted() -> None:
    context = build_context(
        {
            "request_id": "req-1",
            "file": "src/order/controller.py",
            "layer": "controller",
            "dependencies": ["Service", "repository", "REPOSITORY", "  ", "orm"],
        }
    )

    assert context.dependencies == ("orm", "repository", "service")


@pytest.mark.parametrize("missing", REQUIRED_FIELDS)
def test_missing_safety_critical_field_fails_closed(missing: str) -> None:
    payload = {"request_id": "req-1", "file": "src/order/controller.py", "layer": "controller"}
    payload.pop(missing)

    with pytest.raises(PolicyContextError) as error:
        build_context(payload)

    assert missing in str(error.value)
    assert "安全关键字段缺失" in str(error.value)


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_safety_critical_field_fails_closed(blank: object) -> None:
    with pytest.raises(PolicyContextError):
        build_context({"request_id": "req-1", "file": "a.py", "layer": blank})


def test_unknown_context_field_is_rejected() -> None:
    with pytest.raises(PolicyContextError) as error:
        build_context(
            {
                "request_id": "req-1",
                "file": "src/order/controller.py",
                "layer": "controller",
                "layers": "controller",
            }
        )

    assert "layers" in str(error.value)


def test_context_has_no_permission_or_approval_fields() -> None:
    """审批与权限不进入上下文：它们由规则声明，由 Decision 表达。"""

    assert "approval" not in CONTEXT_FIELDS
    assert "permissions" not in CONTEXT_FIELDS
    assert "roles" not in CONTEXT_FIELDS


def test_principal_is_only_taken_from_input() -> None:
    without = build_context(
        {"request_id": "req-1", "file": "prod/infra/deploy_controller.py", "layer": "controller"}
    )
    with_principal = build_context(
        {
            "request_id": "req-1",
            "file": "prod/infra/deploy_controller.py",
            "layer": "controller",
            "principal": {"subject": "local-user", "roles": ["Developer", "DEVELOPER"]},
        }
    )

    # 文件名与路径不得推断主体：没有显式提供就是 None
    assert without.principal is None
    assert with_principal.principal == Principal(subject="local-user", roles=frozenset({"developer"}))


@pytest.mark.parametrize(
    "principal",
    ["local-user", {"roles": ["developer"]}, {"subject": ""}, 7],
)
def test_invalid_principal_is_rejected(principal: object) -> None:
    with pytest.raises(PolicyContextError):
        build_context(
            {
                "request_id": "req-1",
                "file": "src/order/controller.py",
                "layer": "controller",
                "principal": principal,
            }
        )


def test_normalize_context_is_idempotent() -> None:
    first = normalize_context(make_context(layer="Controller", language="Python"))
    second = normalize_context(first)

    assert first == second
    assert second.model_dump() == first.model_dump()


def test_normalize_context_rejects_foreign_objects() -> None:
    with pytest.raises(PolicyContextError):
        normalize_context({"request_id": "req-1"})  # type: ignore[arg-type]


def test_build_context_rejects_non_mapping() -> None:
    with pytest.raises(PolicyContextError):
        build_context(["request_id"])  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["trace_id", "task", "module", "language"])
def test_blank_optional_dimension_is_rejected(field: str) -> None:
    """可选字段也要守约定：不知道就写 null，不要写空串（空串会掩盖拼写错误）。"""

    payload: dict[str, object] = {
        "request_id": "req-1",
        "file": "src/order/controller.py",
        "layer": "controller",
        field: "   ",
    }

    with pytest.raises(PolicyContextError):
        build_context(payload)


def test_build_context_returns_frozen_model() -> None:
    context = build_context(
        {"request_id": "req-1", "file": "src/order/controller.py", "layer": "controller"}
    )

    with pytest.raises(Exception):
        context.layer = "service"  # type: ignore[misc]

    assert isinstance(context, PolicyContext)

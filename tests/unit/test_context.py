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
from policy.models import (
    Operation,
    PolicyContext,
    PolicyContextError,
    Principal,
    normalize_repo_path,
)

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


# ------------------------------------------------------------------ P8：越界理由要能一次改对

# 与读类（src/adapters/models.py::normalize_event_path）同口径的句子；这里只断言"有没有、
# 是不是同一句"，句子本身写在 `policy.models.USABLE_REPO_PATH_HINT` 里，一处定义、多处引用。
USABLE_ALTERNATIVE = "可用的替代"


def _alternative_tail(message: str) -> str:
    """取"可用的替代"及其之后的部分：新增的话只说形态，不得复述本机布局。"""

    index = message.index(USABLE_ALTERNATIVE)
    return message[index:]


def test_absolute_path_outside_the_repository_names_the_usable_form() -> None:
    """绝对路径越界：拒绝方向与原因一个字不变，但理由要写清"改成什么形态就能过"（P8）。"""

    raw = "/outside/repo/file.py"
    with pytest.raises(PolicyContextError) as error:
        repo_relative_path(raw, repo_root=REPO_ROOT)

    message = str(error.value)
    # 为什么被拦：既有部分保持原样（范围与原始取值都还在）
    assert "路径不在仓库" in message
    assert "拒绝处理" in message
    assert repr(raw) in message
    # 可用的替代：仓库相对路径 + 范围根记为 "."，且不用 .. 往外走
    tail = _alternative_tail(message)
    assert "仓库相对路径" in tail
    assert "记为 ." in tail
    assert ".." in tail
    # 新增的话不泄露本机布局
    assert str(REPO_ROOT) not in tail
    assert REPO_ROOT.as_posix() not in tail


def test_parent_escape_names_the_usable_form() -> None:
    """相对路径 ".." 逃逸：写类走的这条路同样给出可用形态（P8 的第二条现场）。"""

    raw = "../outside.py"
    with pytest.raises(PolicyContextError) as error:
        repo_relative_path(raw)

    message = str(error.value)
    assert "逃出仓库根目录" in message
    assert repr(raw) in message
    tail = _alternative_tail(message)
    assert "仓库相对路径" in tail
    assert "记为 ." in tail


def test_normalize_repo_path_parent_escape_names_the_usable_form() -> None:
    """`normalize_repo_path` 是 ".." 逃逸的现场：与 repo_relative_path 同一句话。"""

    with pytest.raises(PolicyContextError) as error:
        normalize_repo_path("../outside.py")

    message = str(error.value)
    assert "逃出仓库根目录" in message
    assert _alternative_tail(message)


def test_the_alternative_sentence_is_identical_across_both_entry_points() -> None:
    """同一条口径只写一遍：两种越界现场给出的"可用的替代"逐字相同。"""

    with pytest.raises(PolicyContextError) as absolute:
        repo_relative_path("/outside/file.py", repo_root=REPO_ROOT)
    with pytest.raises(PolicyContextError) as escape:
        normalize_repo_path("../outside.py")

    assert _alternative_tail(str(absolute.value)) == _alternative_tail(str(escape.value))


# --------- 反向不变量：范围内的路径逐字节不变（P8 只加理由，一个字都不放宽）


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("src/order/controller.py", "src/order/controller.py"),
        ("./src/order/controller.py", "src/order/controller.py"),
        ("src//order//controller.py", "src/order/controller.py"),
        ("src/order/controller.py/", "src/order/controller.py"),
        (WINDOWS_PATH, "src/order/controller.py"),
        ("  src/order/controller.py  ", "src/order/controller.py"),
    ],
)
def test_in_range_relative_paths_are_byte_identical(raw: str, expected: str) -> None:
    assert repo_relative_path(raw) == expected
    assert normalize_repo_path(raw) == expected


def test_in_range_absolute_path_is_byte_identical() -> None:
    absolute = str(REPO_ROOT / "src" / "order" / "controller.py")

    assert repo_relative_path(absolute, repo_root=REPO_ROOT) == "src/order/controller.py"


@pytest.mark.parametrize("raw", [".", "./"])
def test_allow_root_true_normalizes_the_root_to_dot(raw: str) -> None:
    """`allow_root=True`（要目录的调用点）：范围根归一化为 "."，两条入口一致。"""

    assert repo_relative_path(raw, allow_root=True) == "."
    assert normalize_repo_path(raw, allow_root=True) == "."


@pytest.mark.parametrize("raw", [".", "./"])
def test_allow_root_false_still_rejects_the_root(raw: str) -> None:
    """`allow_root=False`（要文件的调用点）：根继续被拒，不是被"放宽"成 "."。"""

    with pytest.raises(PolicyContextError):
        repo_relative_path(raw)
    with pytest.raises(PolicyContextError):
        normalize_repo_path(raw)


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_paths_stay_rejected_with_or_without_allow_root(raw: str) -> None:
    """空路径与纯空白不是"范围根"：allow_root 两种取值都必须拒绝。"""

    for allow_root in (False, True):
        with pytest.raises(PolicyContextError):
            repo_relative_path(raw, allow_root=allow_root)
        with pytest.raises(PolicyContextError):
            normalize_repo_path(raw, allow_root=allow_root)

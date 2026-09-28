"""Q7：「测试已落地、目标模块还不存在」= 待实现，不是 validator crashed。

来源：08 号报告 §5 Q1 / 14 号报告 §5 Q7（三次独立复现）。真机形状：先写测试、再写实现时，
测试文件 import 还不存在的**项目内**模块/名字 → pytest 在收集期以退出码 2 结束 →
旧口径把它归成 crashed（= 验证器不可用）→ critical 覆盖两个 checker → 紧接着的生产文件被拦。
被惩罚的正是正确的开发顺序，模型的绕法是"先把测试暂存成可通过的占位"。

本文件测的是**判据本身**（`validators.adapters.pytest_runner.diagnose_collection_failure`）：

| 形态 | 期望 |
| --- | --- |
| 项目内模块还不存在（真机原文 1） | pending_implementation |
| 项目内模块在、名字不在（真机原文 2） | pending_implementation |
| 同一批两个测试模块都因项目内缺失 | pending_implementation（两条都在，稳定排序） |
| 第三方包缺失 | collection_failure（真违规，仍然阻断） |
| 测试模块语法错误 | collection_failure（真违规，仍然阻断） |
| 环形导入（名字其实在模块里） | collection_failure |
| exit 1（断言失败） | 不做收集期判定（现状不变） |
| exit 2 但输出里没有收集失败原文 | 不做收集期判定（保持 crashed 失败关闭） |

真机原文采集脚本与读数：`.tmp/round-15/fix-tdd-state/collect_pytest_shapes.py` /
`red-pytest-shapes.txt`（pytest 9.1.1、本机）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import validators_config
from policy.evidence import PendingImplementation
from validators.adapters.pytest_runner import (
    COLLECTION_FAILURE,
    PENDING_IMPLEMENTATION,
    diagnose_collection_failure,
)

CONFIG = validators_config()

# --------------------------------------------------------------------------- 真机原文

# 真机原文 1：`from shop.pending_repository import PendingRepository`，模块整体还不存在。
# 顶层包 shop 已经在这棵树里（src/shop/__init__.py 存在），模块不在。
MISSING_INTERNAL_MODULE = (
    "=================================== ERRORS ====================================" + chr(10)
    + "______________ ERROR collecting tests/test_pending_repository.py ______________" + chr(10)
    + "ImportError while importing test module '<abs>'." + chr(10)
    + "Hint: make sure your test modules/packages have valid Python names." + chr(10)
    + "Traceback:" + chr(10)
    + "tests" + chr(92) + "test_pending_repository.py:1: in <module>" + chr(10)
    + "    from shop.pending_repository import PendingRepository" + chr(10)
    + "E   ModuleNotFoundError: No module named 'shop.pending_repository'" + chr(10)
    + "!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!" + chr(10)
)

# 真机原文 2：模块已经落地（就是本次要写的那个文件），AuditEntry 这个名字还没写进去。
MISSING_INTERNAL_NAME = (
    "=================================== ERRORS ====================================" + chr(10)
    + "_______________ ERROR collecting tests/test_audit_repository.py _______________" + chr(10)
    + "ImportError while importing test module '<abs>'." + chr(10)
    + "Hint: make sure your test modules/packages have valid Python names." + chr(10)
    + "Traceback:" + chr(10)
    + "tests" + chr(92) + "test_audit_repository.py:1: in <module>" + chr(10)
    + "    from shop.audit_repository import AuditEntry" + chr(10)
    + "E   ImportError: cannot import name 'AuditEntry' from 'shop.audit_repository' "
    + "(<abs>/src/shop/audit_repository.py)" + chr(10)
)

# 真机原文 3：第三方包缺失——顶层包不在项目索引里，谁都证明不了它是"还没实现"。
MISSING_THIRD_PARTY = (
    "=================================== ERRORS ====================================" + chr(10)
    + "_________________ ERROR collecting tests/test_third_party.py __________________" + chr(10)
    + "ImportError while importing test module '<abs>'." + chr(10)
    + "Traceback:" + chr(10)
    + "tests" + chr(92) + "test_third_party.py:1: in <module>" + chr(10)
    + "    import requests_absent_package" + chr(10)
    + "E   ModuleNotFoundError: No module named 'requests_absent_package'" + chr(10)
)

# 真机原文 4：测试模块自己语法错误（收集期就结束，退出码同样是 2）。
SYNTAX_ERROR = (
    "=================================== ERRORS ====================================" + chr(10)
    + "____________________ ERROR collecting tests/test_broken.py ____________________" + chr(10)
    + "Traceback:" + chr(10)
    + "E     File \"<abs>/tests/test_broken.py\", line 1" + chr(10)
    + "E       def broken(:" + chr(10)
    + "E   SyntaxError: invalid syntax" + chr(10)
)

# 真机原文 6：conftest 加载失败（pytest 退出码 4、stdout 全空、理由只在 stderr：
# .tmp/round-15/fix-tdd-state/red-conftest-shape.txt）。整套测试跑不起来 → 真违规。
CONFTEST_FAILURE = (
    "ImportError while loading conftest '<abs>/tests/conftest.py'." + chr(10)
    + "tests" + chr(92) + "conftest.py:1: in <module>" + chr(10)
    + "    import requests_absent_package" + chr(10)
    + "E   ModuleNotFoundError: No module named 'requests_absent_package'" + chr(10)
)

# 真机原文 5：断言失败（退出码 1）——现状不变，不归收集期判定。
ASSERTION_FAILURE = (
    "F                                                                        [100%]" + chr(10)
    + "================================== FAILURES ===================================" + chr(10)
    + "___________________________________ test_no ___________________________________" + chr(10)
    + "FAILED tests/test_assertion.py::test_no - assert 1 == 2" + chr(10)
)


def workspace_with_module(tmp_root: Path) -> Path:
    """一棵最小的树：顶层包 shop 存在，audit_repository 存在、existing 存在。"""

    workspace = tmp_root / "workspace"
    (workspace / "src" / "shop").mkdir(parents=True, exist_ok=True)
    (workspace / "tests").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "shop" / "__init__.py").write_text("", encoding="utf-8", newline="")
    (workspace / "src" / "shop" / "audit_repository.py").write_text(
        '"""审计仓储。"""' + chr(10) + chr(10) + chr(10)
        + "class AuditRepository:" + chr(10)
        + '    """仓储。"""' + chr(10),
        encoding="utf-8",
        newline="",
    )
    return workspace


def diagnose(text: str, *, workspace: Path, exit_code: int = 2):
    return diagnose_collection_failure(
        text, exit_code=exit_code, workspace=workspace, project=CONFIG.project
    )


# --------------------------------------------------------------------------- 正例：待实现


def test_missing_project_module_is_pending_implementation(tmp_root: Path) -> None:
    diagnosis = diagnose(MISSING_INTERNAL_MODULE, workspace=workspace_with_module(tmp_root))

    assert diagnosis is not None
    assert diagnosis.verdict == PENDING_IMPLEMENTATION
    assert diagnosis.test_modules == ("tests/test_pending_repository.py",)
    assert diagnosis.missing_targets == ("shop.pending_repository",)
    assert "待实现" in diagnosis.reason
    # 理由必须说得出"改成什么形态就能过"（AGENTS 第 50 条）
    assert diagnosis.fix


def test_missing_project_name_is_pending_implementation(tmp_root: Path) -> None:
    """真机收据的形状：模块在树里、`AuditEntry` 这个名字还没写进去。"""

    diagnosis = diagnose(MISSING_INTERNAL_NAME, workspace=workspace_with_module(tmp_root))

    assert diagnosis is not None
    assert diagnosis.verdict == PENDING_IMPLEMENTATION
    assert diagnosis.test_modules == ("tests/test_audit_repository.py",)
    assert diagnosis.missing_targets == ("shop.audit_repository:AuditEntry",)
    assert "AuditEntry" in diagnosis.reason


def test_two_collect_errors_in_one_run_are_both_reported(tmp_root: Path) -> None:
    """同一批里两个测试模块都还没法收集：两条都要在，且顺序稳定。"""

    text = MISSING_INTERNAL_MODULE + MISSING_INTERNAL_NAME
    first = diagnose(text, workspace=workspace_with_module(tmp_root))
    second = diagnose(text, workspace=workspace_with_module(tmp_root))

    assert first is not None and second is not None
    assert first.verdict == PENDING_IMPLEMENTATION
    assert first.test_modules == (
        "tests/test_audit_repository.py",
        "tests/test_pending_repository.py",
    )
    assert first.missing_targets == (
        "shop.audit_repository:AuditEntry",
        "shop.pending_repository",
    )
    assert json.dumps(first.reason) == json.dumps(second.reason)


def test_the_diagnosis_only_uses_repository_relative_paths(tmp_root: Path) -> None:
    """证据里不得出现绝对路径（AGENTS 第 19 条）：测试模块名必须是仓库相对路径。"""

    workspace = workspace_with_module(tmp_root)
    diagnosis = diagnose(MISSING_INTERNAL_NAME, workspace=workspace)

    assert diagnosis is not None
    payload = json.dumps(
        {
            "test_modules": diagnosis.test_modules,
            "missing_targets": diagnosis.missing_targets,
            "reason": diagnosis.reason,
            "fix": diagnosis.fix,
        },
        ensure_ascii=False,
    )
    assert str(workspace) not in payload
    assert "C:" not in payload
    assert "Users" not in payload


# --------------------------------------------------------------------------- 反例：不许放宽


def test_a_third_party_module_is_a_real_failure_not_pending(tmp_root: Path) -> None:
    """第三方包缺失不是"待实现"：顶层包不在项目索引里，谁都证明不了它还没写。"""

    diagnosis = diagnose(MISSING_THIRD_PARTY, workspace=workspace_with_module(tmp_root))

    assert diagnosis is not None
    assert diagnosis.verdict == COLLECTION_FAILURE
    assert diagnosis.missing_targets == ()
    assert "requests_absent_package" in diagnosis.reason
    assert "待实现" not in diagnosis.reason


def test_a_syntax_error_is_a_real_failure_not_pending(tmp_root: Path) -> None:
    diagnosis = diagnose(SYNTAX_ERROR, workspace=workspace_with_module(tmp_root))

    assert diagnosis is not None
    assert diagnosis.verdict == COLLECTION_FAILURE
    assert "SyntaxError" in diagnosis.reason
    assert "待实现" not in diagnosis.reason


def test_a_circular_import_is_a_real_failure_even_though_the_name_exists(tmp_root: Path) -> None:
    """环形导入的名字往往**在**模块里：这种形状绝不能判成"待实现"。"""

    workspace = workspace_with_module(tmp_root)
    (workspace / "src" / "shop" / "audit_repository.py").write_text(
        '"""审计仓储。"""' + chr(10) + chr(10) + chr(10)
        + "class AuditEntry:" + chr(10)
        + '    """一条审计记录。"""' + chr(10) + chr(10)
        + '    from shop.audit_repository import AuditEntry  # 自引用：环形导入的形状' + chr(10),
        encoding="utf-8",
        newline="",
    )
    text = MISSING_INTERNAL_NAME.replace(
        "E   ImportError: cannot import name 'AuditEntry' from 'shop.audit_repository' "
        + "(<abs>/src/shop/audit_repository.py)",
        "E   ImportError: cannot import name 'AuditEntry' from partially initialized module "
        + "'shop.audit_repository' (most likely due to a circular import)",
    )

    diagnosis = diagnose(text, workspace=workspace)

    assert diagnosis is not None
    assert diagnosis.verdict == COLLECTION_FAILURE
    assert diagnosis.missing_targets == ()


def test_a_name_bound_anywhere_in_the_module_counts_as_present(tmp_root: Path) -> None:
    """名字只要在模块里出现过（赋值 / 导入 / 参数都算）就不判"待实现"：可能漏、不误报。"""

    workspace = workspace_with_module(tmp_root)
    (workspace / "src" / "shop" / "audit_repository.py").write_text(
        '"""审计仓储。"""' + chr(10) + chr(10) + chr(10)
        + "def build(entry: object) -> object:" + chr(10)
        + '    """占位。"""' + chr(10) + chr(10)
        + "    AuditEntry = entry" + chr(10)
        + "    return AuditEntry" + chr(10),
        encoding="utf-8",
        newline="",
    )

    diagnosis = diagnose(MISSING_INTERNAL_NAME, workspace=workspace)

    assert diagnosis is not None
    assert diagnosis.verdict == COLLECTION_FAILURE


def test_a_broken_conftest_is_a_real_failure_even_at_exit_four(tmp_root: Path) -> None:
    """conftest 出错：退出码 4、stdout 全空——仍然是真违规，不是"待实现"也不是"工具坏了"。"""

    diagnosis = diagnose(
        CONFTEST_FAILURE, workspace=workspace_with_module(tmp_root), exit_code=4
    )

    assert diagnosis is not None
    assert diagnosis.verdict == COLLECTION_FAILURE
    assert diagnosis.missing_targets == ()
    assert "requests_absent_package" in diagnosis.reason
    assert "待实现" not in diagnosis.reason


def test_an_assertion_failure_is_not_a_collection_failure(tmp_root: Path) -> None:
    """退出码 1：现状不变（断言失败走既有的 FAILED 解析路径）。"""

    assert diagnose(
        ASSERTION_FAILURE, workspace=workspace_with_module(tmp_root), exit_code=1
    ) is None


def test_exit_without_any_tool_message_is_not_diagnosed(tmp_root: Path) -> None:
    """工具"跑不成"但没有任何收集失败原文：保持 crashed / 失败关闭，绝不猜成"待实现"。"""

    workspace = workspace_with_module(tmp_root)

    assert diagnose(
        "ERROR: usage: pytest [options] [file_or_dir] [file_or_dir]" + chr(10),
        workspace=workspace,
    ) is None
    assert diagnose("", workspace=workspace) is None
    # 退出码 4 但没有 conftest 原文（例如参数用法错误）：同样判不了
    assert diagnose("ERROR: usage: no such option: --nope" + chr(10), workspace=workspace, exit_code=4) is None


# --------------------------------------------------------------------------- 证据模型


def test_pending_implementation_payload_is_readable_and_stable() -> None:
    pending = PendingImplementation(
        validator_id="tool.pytest",
        validator_version="1.0",
        checkers=("failing_tests",),
        test_modules=("tests/test_audit_repository.py",),
        missing_targets=("shop.audit_repository:AuditEntry",),
        reason="待实现",
        fix="把 AuditEntry 落地",
    )

    assert pending.validator == "tool.pytest@1.0"
    assert pending.to_payload() == {
        "validator": "tool.pytest@1.0",
        "checkers": ["failing_tests"],
        "test_modules": ["tests/test_audit_repository.py"],
        "missing_targets": ["shop.audit_repository:AuditEntry"],
        "reason": "待实现",
        "fix": "把 AuditEntry 落地",
    }
    # 说不出"哪个测试模块、因为哪个项目内缺失的目标"的记录**构不出来**：
    # 否则它会长成"没有理由的放行"（Q7 的要害不是放宽，而是把理由写下来）。
    with pytest.raises(Exception) as error:
        PendingImplementation(
            validator_id="tool.pytest",
            validator_version="1.0",
            reason="待实现",
            fix="落地",
        )
    assert "missing_targets" in str(error.value)

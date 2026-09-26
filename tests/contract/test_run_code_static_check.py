"""G9 第二道闸测试：声明与执行一致、失败关闭，并且**如实标注已知绕过**。

背景（实测）：`exec.run_code` 是 driver=none + post_checks=[] + 无命令白名单，
唯一门禁是人工审批——审批一过就是任意代码，且不产生任何执行证据。本轮的处置是给它加
**数据驱动的结构化静态检查**（检查项写在注册表里，代码里没有硬编码判断），并且：

1. 解析不了 = 拒绝（不是跳过）；
2. 委派类进程工具必须在「结构化检查」与「显式不可治理声明」之间**显式**选一个，
   两者都不写 = 加载期报错（没有默认值，也不允许"大家都写个字段应付"）；
3. 不可治理声明不是静默通过：pre-check 输出显式状态、进审计、决策至少 allow_with_warnings；
4. **这不是沙箱**：下面的测试既验证能拦住的形态，也把拦不住的形态固定成事实。
"""

from __future__ import annotations

import copy
import json

import pytest

from enforcement.audit import FileAuditSink
from enforcement.codecheck import check_code
from enforcement.ledger import EnforcementLedger
from enforcement.models import (
    SUPPORTED_CODE_CHECKS,
    CheckStatus,
    Decision,
    ParamType,
    ReasonCode,
)
from enforcement.precheck import check_list, pre_execute
from enforcement.registry import load_registry, registry_document_from_mapping

from enforcement_support import (
    ENFORCEMENT_APPROVED,
    ENFORCEMENT_REGISTRY,
    TEST_REGISTRY_TOOLS,
    EnforcementPaths,
    approval_for,
    enforcement_paths,
    make_action,
    registry_document,
    write_registry,
)

pytestmark = pytest.mark.contract

FORBIDDEN_SOURCES = (
    "import os",
    "from os import system",
    "import subprocess",
    "import socket",
    "open('leak.txt', 'w')",
    "__import__('os')",
    "eval('1 + 1')",
    "os.system('whoami')",
)


def repository_registry():
    return load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry


def executed_code_spec(registry):
    spec = registry.tool("exec.run_code")
    assert spec is not None
    return spec


# --------------------------------------------------------------------------- 声明与执行一致


def test_repository_run_code_declares_the_second_gate():
    """真实注册表的声明：run_code 不能再是"只有审批一道门"。"""

    spec = executed_code_spec(repository_registry())
    assert spec.driver.value == "none", "这条测试的前提：平台不执行它"
    assert spec.code_check is not None, "driver=none 的进程类工具必须声明第二道闸"
    assert spec.code_check.kind in SUPPORTED_CODE_CHECKS
    assert spec.code_check.param == "code"
    declaration = spec.parameter("code")
    assert declaration is not None and declaration.type is ParamType.STRING
    assert spec.code_check.forbidden_imports and spec.code_check.forbidden_calls
    assert spec.code_check.known_gaps, "已知绕过形态必须如实登记，不能留空"


def test_declared_surfaces_actually_block_the_repository_declaration():
    """声明什么就拦什么：用真实注册表的声明跑真实代码。"""

    declaration = executed_code_spec(repository_registry()).code_check
    for source in FORBIDDEN_SOURCES:
        result = check_code(source, declaration)
        assert not result.passed, f"{source!r} 竟然通过了检查"
        assert result.reason_code is ReasonCode.CODE_BLOCKED, source

    clean = check_code("total = sum(range(10))\nprint(total)", declaration)
    assert clean.passed and clean.reason_code is ReasonCode.ALLOW
    assert "已知不可覆盖的形态" in clean.detail


def test_parse_failure_is_a_refusal_not_a_skip():
    declaration = executed_code_spec(repository_registry()).code_check
    for source in ("def (:\n", "", "   "):
        result = check_code(source, declaration)
        assert not result.passed, repr(source)
        assert result.reason_code is ReasonCode.CODE_PARSE_FAILED, repr(source)


def test_precheck_blocks_governed_code_that_touches_a_forbidden_surface(enforcement_paths):
    request = make_action(
        enforcement_paths.registry_object(),
        enforcement_paths,
        "exec.delegated",
        {"code": "import os", "description": "读环境变量"},
        roles=("owner",),
    )
    outcome = pre_execute(
        request,
        registry=enforcement_paths.registry_object(),
        ledger=EnforcementLedger(enforcement_paths.ledger),
        sink=FileAuditSink(enforcement_paths.audit, workspace=enforcement_paths.workspace),
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.CODE_BLOCKED
    assert outcome.decision.check("code_check").status is CheckStatus.FAILED


def test_clean_code_passes_the_check_and_still_needs_the_approval(enforcement_paths):
    request = make_action(
        enforcement_paths.registry_object(),
        enforcement_paths,
        "exec.delegated",
        {"code": "print(1)", "description": "demo"},
        roles=("owner",),
    )
    checks, _spec, warnings = check_list(
        request,
        registry=enforcement_paths.registry_object(),
        ledger=EnforcementLedger(enforcement_paths.ledger),
        sink=FileAuditSink(enforcement_paths.audit, workspace=enforcement_paths.workspace),
    )

    code_check = next(item for item in checks if item.check == "code_check")
    assert code_check.status is CheckStatus.PASSED
    # 结构性检查不是沙箱：这条事实必须进警告，而不是被读成"隔离了"
    assert "code_check_structural_only" in warnings

    outcome = pre_execute(
        request,
        registry=enforcement_paths.registry_object(),
        ledger=EnforcementLedger(enforcement_paths.ledger),
        sink=FileAuditSink(enforcement_paths.audit, workspace=enforcement_paths.workspace),
    )
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_REQUIRED


# --------------------------------------------------------------------------- 已知绕过（如实记录）


def test_known_bypass_is_recorded_instead_of_hidden():
    """**这条测试断言的是"拦不住"**，因此它同时是免责声明与回归哨兵。

    静态检查看的是语法结构：`(lambda: 0).__globals__["__builtins__"]["open"]` 里
    没有一个被禁的**名字**，名字藏在表达式的下标里。想靠"再往清单里加一个名字"补上，
    只会变成打地鼠——
    真正的隔离属于运行时沙箱，不属于本阶段。

    把它固定成测试，是为了防止两件事：
    (1) 有人把结构性检查当成沙箱（把"查过了"读成"隔离了"）；
    (2) 有人悄悄缩小 known_gaps 的登记范围，让缺口在文档里消失。
    """

    declaration = executed_code_spec(repository_registry()).code_check
    bypass = "leak = (lambda: 0).__globals__['__builtins__']['open']\n" \
             "leak('leak.txt', 'w')"

    result = check_code(bypass, declaration)

    assert result.passed, "这条形态当前就拦不住；若哪天拦住了，请更新 known_gaps 与 04 文档"
    assert any("下标" in gap for gap in declaration.known_gaps), (
        "拦不住的形态必须登记在注册表的 known_gaps 里：缺口不许只存在于代码里"
    )


# --------------------------------------------------------------------------- 加载期不变量


def delegated_tool(**overrides):
    """取测试注册表里的委派类替身（exec.delegated，与 run_code 同形）并覆盖字段。"""

    tool = copy.deepcopy(
        dict(next(item for item in TEST_REGISTRY_TOOLS if item["id"] == "exec.delegated"))
    )
    tool.update(overrides)
    return tool


def load_registry_with(tmp_root, tool, *, name: str = "registry"):
    root = tmp_root / name
    registry_path, _ = write_registry(root, tools=(tool,), approve=False)
    return load_registry(registry_path, approved_path=None)


def test_delegated_process_tool_without_a_second_gate_is_refused_at_load(tmp_root):
    tool = delegated_tool()
    tool.pop("code_check")

    with pytest.raises(Exception) as error:
        load_registry_with(tmp_root, tool, name="no-gate")
    assert "code_check" in str(error.value) and "ungoverned" in str(error.value)


def test_unknown_code_check_kind_is_refused_at_load(tmp_root):
    tool = delegated_tool(code_check={**delegated_tool()["code_check"], "kind": "looks_safe"})

    with pytest.raises(Exception) as error:
        load_registry_with(tmp_root, tool, name="unknown-kind")
    assert "未知代码检查" in str(error.value)


def test_code_check_param_must_be_a_declared_string_param(tmp_root):
    missing = delegated_tool(
        code_check={**delegated_tool()["code_check"], "param": "payload"}
    )
    with pytest.raises(Exception) as error:
        load_registry_with(tmp_root, missing, name="missing-param")
    assert "不是已声明的参数" in str(error.value)

    wrong_type = delegated_tool(
        code_check={**delegated_tool()["code_check"], "param": "description"}
    )
    wrong_type["parameters"] = [dict(item) for item in wrong_type["parameters"]]
    for item in wrong_type["parameters"]:
        if item["name"] == "description":
            item["type"] = "integer"
    with pytest.raises(Exception) as error:
        load_registry_with(tmp_root, wrong_type, name="wrong-type")
    assert "必须是 string 参数" in str(error.value)


def test_code_check_without_any_surface_is_refused_at_load(tmp_root):
    tool = delegated_tool(
        code_check={
            "kind": "python_forbidden_surface",
            "param": "code",
            "forbidden_imports": [],
            "forbidden_calls": [],
            "forbidden_attributes": [],
        }
    )

    with pytest.raises(Exception) as error:
        load_registry_with(tmp_root, tool, name="empty-check")
    assert "至少要声明" in str(error.value)


# --------------------------------------------------------------------------- 显式不可治理声明


def ungoverned_tool():
    tool = delegated_tool()
    tool.pop("code_check")
    tool["id"] = "exec.ungoverned"
    tool["tool_name"] = "ungoverned_runner"
    tool["ungoverned"] = {
        "reason": "该工具的动作语义由外部运行时决定，平台拿不到可判定的结构",
        "declared_by": "security-review",
    }
    return tool


def test_ungoverned_declaration_is_an_explicit_state_not_a_silent_pass(tmp_root):
    paths = EnforcementPaths(tmp_root)
    write_registry(paths.root, tools=(ungoverned_tool(),))
    registry = paths.load().registry
    assert registry.tool("exec.ungoverned") is not None

    request = make_action(
        registry,
        paths,
        "exec.ungoverned",
        {"code": "print(1)", "description": "demo"},
        roles=("owner",),
    )
    outcome = pre_execute(
        request,
        registry=registry,
        ledger=EnforcementLedger(paths.ledger),
        sink=FileAuditSink(paths.audit, workspace=paths.workspace),
        approval=approval_for(request),
    )

    coverage = outcome.decision.check("governance_coverage")
    assert coverage is not None
    assert coverage.status is CheckStatus.SKIPPED
    assert coverage.reason_code is ReasonCode.UNGOVERNED_DECLARED
    assert "security-review" in coverage.detail
    # 不是静默通过：决策至少是 allow_with_warnings
    assert outcome.decision.decision is Decision.ALLOW_WITH_WARNINGS

    records = [
        json.loads(line)
        for line in paths.audit.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    payloads = [item["payload"] for item in records if item.get("stage") == "pre_decision"]
    assert payloads, "不可治理声明必须留下审计记录"
    audited = [
        check
        for payload in payloads
        for check in payload.get("checks", [])
        if check.get("check") == "governance_coverage"
    ]
    assert audited and audited[0]["reason_code"] == ReasonCode.UNGOVERNED_DECLARED.value
    assert payloads[0]["decision"] == Decision.ALLOW_WITH_WARNINGS.value


def test_ungoverned_and_code_check_cannot_coexist(tmp_root):
    tool = ungoverned_tool()
    tool["code_check"] = delegated_tool()["code_check"]

    with pytest.raises(Exception) as error:
        load_registry_with(tmp_root, tool, name="both")
    assert "不得同时声明" in str(error.value)


def test_ungoverned_only_applies_to_delegated_process_tools(tmp_root):
    tool = copy.deepcopy(dict(next(item for item in TEST_REGISTRY_TOOLS if item["id"] == "fs.read")))
    tool["ungoverned"] = {"reason": "随便声明一下", "declared_by": "someone"}

    with pytest.raises(Exception) as error:
        load_registry_with(tmp_root, tool, name="not-delegated")
    assert "只适用于" in str(error.value)


def test_registry_document_round_trip_keeps_the_declaration():
    """声明是数据：从映射加载出来的 spec 必须与写进去的一致（不是运行时另算一份）。"""

    document = registry_document(tools=(delegated_tool(),))
    spec = registry_document_from_mapping(copy.deepcopy(document)).tool("exec.delegated")
    assert spec.code_check is not None
    assert spec.code_check.kind == "python_forbidden_surface"
    assert tuple(spec.code_check.forbidden_imports) == ("os", "socket", "subprocess")

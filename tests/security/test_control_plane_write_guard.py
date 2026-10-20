"""C3 第三件 v1：危险动作前置阻断的三条路径（写 / 删除 / 执行）。

05 §4 C3 的门写的是「删除/执行/控制面写被前置阻断」。2026-10-21 裁定草案 §4 的实测：

| 路径 | 修前 |
| --- | --- |
| 写类工具到 `policies/` `registry/` `adapters/` `api/` `validation/` | 已前置阻断（`blocked_prefixes`） |
| 写类工具到 `<受控项目>/.policy/` | **没有阻断**——读面从 B3 起已封住它，写面却没封 |
| 删除 | dsh 工具表没有 delete 操作；`Remove-Item` 不在命令白名单 → `command_not_allowlisted` |
| 执行 | `run_code` 的结构化静态检查 → `code_blocked` |

本文件把三条路径钉在**同一份固定请求集**上（与读数 §3 的前后矩阵同一组用例）：
写面只翻 `.policy` 那一格、近似前缀 `.policyx/` 不误伤、`policies/` 仍被拦，
删除与执行两条路径的**既有 reason code 一个字不变**。

另外两条纪律也在这里钉住：

1. **数据缺口修复之后不能靠"以后再补一条前缀"写回同类问题**：坏的 `blocked_prefixes` 声明
   必须在**注册表加载期**就被拒绝（与 `read_guard` 的加载期校验同一口径），而不是等运行期
   "命中不了"才发现；
2. **改数据必须重审**：四个写类工具的 `schema_hash` 与已审核清单一致（否则 pre-check 会以
   `schema_not_approved` 拒绝整个工具，`is_approved` 就是那条不变式）。

判定路径一个字不改：这里只读真实注册表、真实 pre-check 的结论，不构造任何替代判定。
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from enforcement.action import build_action_request
from enforcement.audit import FileAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import (
    CheckStatus,
    Decision,
    ReasonCode,
    RegistryError,
)
from enforcement.precheck import pre_execute
from enforcement.registry import load_registry, registry_document_from_mapping

from conftest import REPO_ROOT
from enforcement_support import ENFORCEMENT_APPROVED, ENFORCEMENT_REGISTRY

pytestmark = pytest.mark.security

WRITE_TOOLS = ("fs.edit", "fs.write", "orc.fs.edit", "orc.fs.write")


def _real_registry():
    return load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry


def _precheck(tmp_root: Path, tool_id: str, params: dict, *, action_id: str):
    registry = _real_registry()
    spec = registry.tool(tool_id)
    assert spec is not None
    request = build_action_request(
        spec,
        params,
        action_id=action_id,
        request_id=action_id,
        agent=spec.agent,
        agent_version="0.1.6-alpha.2",
        trace_id=None,
        subject="local-user",
        roles=("developer",) if spec.agent == "orchestrator" else ("owner",),
        permissions=registry.permissions_for(
            ("developer",) if spec.agent == "orchestrator" else ("owner",)
        ),
        workspace=REPO_ROOT,
        ttl_seconds=registry.grant_ttl_seconds,
    )
    return pre_execute(
        request,
        registry=registry,
        ledger=EnforcementLedger(tmp_root / (action_id + "-ledger.jsonl")),
        sink=FileAuditSink(tmp_root / (action_id + "-audit.jsonl"), workspace=REPO_ROOT),
        approval=None,
    )


def _check(outcome, name: str):
    return outcome.decision.check(name)


# --------------------------------------------------------------------------- 路径 1：写


def test_the_trust_root_write_is_blocked(tmp_root: Path) -> None:
    """`.policy/` 下的信任根写入被 `path_prefixes` 拦下（注册表 1.3 补的数据）。"""

    outcome = _precheck(
        tmp_root,
        "fs.write",
        {"file_path": ".policy/audit.jsonl", "content": "{\"sequence\": 1}\n"},
        action_id="cp-audit-write",
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.PATH_OUT_OF_SCOPE
    check = _check(outcome, "path_prefixes")
    assert check is not None and check.status is CheckStatus.FAILED
    assert ".policy" in check.detail


def test_the_approval_ticket_cannot_be_rewritten(tmp_root: Path) -> None:
    """审批条子被改一个字，旧授权就失效——这正是"写面也必须封"的理由。"""

    outcome = _precheck(
        tmp_root,
        "fs.edit",
        {
            "file_path": ".policy/approval.json",
            "old_string": '"granted_by": "dshznm"',
            "new_string": '"granted_by": "mallory"',
        },
        action_id="cp-approval-rewrite",
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.PATH_OUT_OF_SCOPE


def test_the_orchestrator_writer_uses_the_same_trust_root(tmp_root: Path) -> None:
    """两个 Agent 的信任根边界必须一致：编排层写 .policy 同样被拦。"""

    outcome = _precheck(
        tmp_root,
        "orc.fs.write",
        {"file_path": ".policy/enforcement-ledger.jsonl", "content": "{}\n"},
        action_id="cp-orc-write",
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.PATH_OUT_OF_SCOPE


def test_the_lookalike_prefix_is_not_harmed(tmp_root: Path) -> None:
    """精度：`.policyx/` 不是 `.policy` 之下（前缀按路径分段边界匹配）。"""

    outcome = _precheck(
        tmp_root,
        "fs.write",
        {"file_path": ".policyx/audit.jsonl", "content": "{}\n"},
        action_id="cp-lookalike",
    )

    check = _check(outcome, "path_prefixes")
    assert check is not None and check.status is CheckStatus.PASSED
    assert outcome.decision.decision is not Decision.BLOCK


def test_the_rule_directory_is_still_blocked(tmp_root: Path) -> None:
    """回归：`policies/` 在补 `.policy` 之后仍然被拦（本次不改既有拦截面）。"""

    outcome = _precheck(
        tmp_root,
        "fs.write",
        {"file_path": "policies/security/SEC-001.yaml", "content": "id: SEC-001\n"},
        action_id="cp-policies-regression",
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.PATH_OUT_OF_SCOPE


# --------------------------------------------------------------------------- 路径 2：删除


@pytest.mark.parametrize(
    "tool_id, command, action_id",
    [
        ("exec.pwsh", "Remove-Item -Recurse .", "cp-remove-pwsh"),
        ("exec.bash", "rm -rf .policy", "cp-remove-bash"),
    ],
)
def test_delete_paths_stay_outside_the_allowlist(
    tmp_root: Path, tool_id: str, command: str, action_id: str
) -> None:
    """dsh 工具表没有 delete 操作；命令类删除动作连白名单都进不去。

    这条钉的是**现状码**：`command_not_allowlisted`，不是 `.policy` 的前缀闸。
    两者是不同的闸——前缀闸只管声明了 `blocked_prefixes` 的 path 参数，命令文本里的删除
    动作由白名单 + 片段清单管。
    """

    outcome = _precheck(
        tmp_root, tool_id, {"command": command, "description": "删除路径探针"},
        action_id=action_id,
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.COMMAND_NOT_ALLOWLISTED
    check = _check(outcome, "command_allowlist")
    assert check is not None and check.status is CheckStatus.FAILED
    # 前缀闸对命令类工具是 SKIPPED：它没有 path 参数，不假装查过
    prefix_check = _check(outcome, "path_prefixes")
    assert prefix_check is not None and prefix_check.status is CheckStatus.SKIPPED


# --------------------------------------------------------------------------- 路径 3：执行


def test_run_code_forbidden_surface_is_blocked(tmp_root: Path) -> None:
    """run_code 的结构化静态检查：`import os` 在授权之前就被 code_check 拦下。"""

    outcome = _precheck(
        tmp_root,
        "exec.run_code",
        {"code": "import os\nprint(os.getcwd())\n", "description": "执行路径探针"},
        action_id="cp-run-code-os",
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.CODE_BLOCKED
    check = _check(outcome, "code_check")
    assert check is not None and check.status is CheckStatus.FAILED


def test_run_code_benign_surface_passes_the_structural_check(tmp_root: Path) -> None:
    """对照：无害代码不会被 code_check 拦；它止步于人工审批门禁（`approval_required`）。

    两件事分开读：`code_check` 是"代码里有没有禁用面"，审批是"这个高风险动作谁批的"。
    把前者当成后者，就会把"审批缺失"误读成"代码不安全"。
    """

    outcome = _precheck(
        tmp_root,
        "exec.run_code",
        {"code": "print('ok')\n", "description": "执行路径对照"},
        action_id="cp-run-code-benign",
    )

    check = _check(outcome, "code_check")
    assert check is not None and check.status is CheckStatus.PASSED
    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_REQUIRED


# --------------------------------------------------------------------------- 数据面：重审与加载期拒绝


def test_the_new_prefix_is_covered_by_the_reviewed_hash() -> None:
    """改数据必须重审：四个写类工具的当前描述必须与已审核哈希一致。

    改 `blocked_prefixes` 之后忘记 `registry --approve` 时，pre-check 会以
    `schema_not_approved` 拒绝**整个工具**——这条不变式正是它要保证的东西。
    """

    registry = _real_registry()
    for tool_id in WRITE_TOOLS:
        spec = registry.tool(tool_id)
        assert spec is not None, tool_id
        assert registry.is_approved(spec), f"{tool_id} 的受保护前缀没有进已审核哈希"


def _registry_document() -> dict:
    return yaml.safe_load(ENFORCEMENT_REGISTRY.read_text(encoding="utf-8"))


def _mutate_write_prefix(document: dict, mutations) -> dict:
    """在真实注册表的副本上改一处写类工具的 `blocked_prefixes` 声明。"""

    payload = copy.deepcopy(document)
    tool = next(item for item in payload["tools"] if item["id"] == "fs.write")
    parameter = next(item for item in tool["parameters"] if item["name"] == "file_path")
    mutations(parameter)
    return payload


@pytest.mark.parametrize(
    "mutations, needle",
    [
        # 前导斜杠有"绝对路径"与"写顺手了"两种读法；代码不替作者选一种，直接拒绝。
        (lambda p: p.update({"blocked_prefixes": ["/etc"]}), "不要以 / 开头"),
        (lambda p: p.update({"blocked_prefixes": [".."]}), "规范的工作区相对路径"),
        (lambda p: p.update({"blocked_prefixes": [""]}), "规范的工作区相对路径"),
        (lambda p: p.update({"blocked_prefixes": ["a//b"]}), "规范的工作区相对路径"),
        (
            lambda p: p.update({"blocked_prefixes": [".policy", ".POLICY"]}),
            "不得重复",
        ),
        # 反斜杠写法归一化后同样是绝对路径：Windows 上一个 etc 前缀既不可靠也不可读
        (lambda p: p.update({"blocked_prefixes": ["\\etc"]}), "不要以 / 开头"),
    ],
)
def test_broken_blocked_prefixes_declarations_are_rejected_at_load_time(
    mutations, needle: str
) -> None:
    """坏的 `blocked_prefixes` 声明在加载期被拒（失败关闭，不是"运行期命中不了"）。"""

    document = _mutate_write_prefix(_registry_document(), mutations)

    with pytest.raises(RegistryError) as error:
        registry_document_from_mapping(document)
    assert needle in str(error.value)


def test_blocked_prefixes_on_a_non_path_parameter_is_rejected() -> None:
    """`blocked_prefixes` 只适用于 path 参数：声明在 string 上会被静默跳过。"""

    payload = copy.deepcopy(_registry_document())
    tool = next(item for item in payload["tools"] if item["id"] == "fs.write")
    content = next(item for item in tool["parameters"] if item["name"] == "content")
    content["blocked_prefixes"] = ["x"]

    with pytest.raises(RegistryError) as error:
        registry_document_from_mapping(payload)
    assert "只适用于 path 参数" in str(error.value)


def test_the_real_registry_still_loads() -> None:
    """反真空：上面那些拒绝不是"整个注册表都加载不了"造成的。"""

    registry = registry_document_from_mapping(_registry_document())
    assert registry.tool("fs.write") is not None

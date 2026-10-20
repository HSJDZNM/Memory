"""受控执行的信任根不能被「自动放行」的写工具改写（AGENTS 第 13 条 / L31）。

`registry/tool-registry.yaml` 的 `fs.edit` / `fs.write` 是 `approval: none` 的自动放行
写工具，它们此前只声明 `path_scope: workspace`：`policies/` `registry/` `adapters/`
`api/` `validation/` 这些**定义治理本身**的目录（规则、工具授权、适配器声明、已审核哈希）
都能被它们改写。编排层同形的 `orc.fs.edit` / `orc.fs.write` 一直是挡着的，两侧不对称留下
的是一条无门禁的篡改路径——改完注册表 / 哈希 / 声明，只有运行期"描述与已审核哈希对不上"
时才会被发现。

注册表 1.3（C3 第三件 v1）把 `.policy/` 补进同一份 `blocked_prefixes`：受控项目里的
**信任根**（审批条子 `approval.json`、审计账本 `audit.jsonl`、受控执行台账）同样定义治理，
而读面从 B3（注册表 1.2 的 `read_guard`）起就已经挡着它——同一条信任根两条路，读挡着、
写敞着，等于没挡。四个写类工具（dsh 的两个 + 编排层的两个）都必须声明它。

注册表 1.4（2026-10-21，04 5.87）再把 `.git` 与 `.github/workflows` 补进同一份列表：
它们不是"数据"而是**执行面**——`.git/hooks/*` 在下一次 `git commit` 时执行、
`.git/config` 能把 hook 路径（core.hooksPath）或 alias 指到别处、workflow 文件决定 CI
还跑不跑。改它们等于改"谁能被执行 / 哪些检查会跑"，与文档、语料（改的是判定依据或读数）
分得开。精度由**路径分段边界**保证：`.gitignore`、`.github/ISSUE_TEMPLATE/` 与
`.github/workflowsx/` 都不在前缀之下。

本文件两组断言缺一不可：

1. **数据面**：注册表里每个"不改就能自动放行"的写工具都必须声明同一组受保护前缀；
2. **行为面**：拿真注册表跑一次 pre-check，信任根写入必须是 block 且原因是 `path_prefixes`
   （reason_code `path_out_of_scope`）；对照组（受控项目内的普通文件、近似前缀 `.policyx/`）
   不被这道闸拦。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enforcement.action import build_action_request
from enforcement.audit import FileAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import CheckStatus, Decision, ReasonCode
from enforcement.precheck import pre_execute
from enforcement.registry import load_registry

from conftest import REPO_ROOT
from enforcement_support import ENFORCEMENT_APPROVED, ENFORCEMENT_REGISTRY

pytestmark = pytest.mark.contract

# 控制面：这些目录里的数据定义了"什么受治理、授权给谁、按什么口径判"。
# `.policy` 是受控项目里的**信任根**（审批条子 / 审计账本 / 台账）：它不定义规则，但定义
# "这次治理发生过什么"，因此与上面五个目录同级保护（读面从注册表 1.2 起已同样保护）。
# `.git` 与 `.github/workflows` 是**执行面**（注册表 1.4）：hook 会被下一次 git 命令执行、
# `.git/config` 能改 hook 路径、workflow 决定 CI 是否还跑——改它们就是改执行链本身。
CONTROL_PLANE_PREFIXES = {
    "policies",
    "registry",
    "adapters",
    "api",
    "validation",
    ".policy",
    ".git",
    ".github/workflows",
}

# 四个自动放行的写工具：两个 dsh 侧 + 两个编排层。少一个就是一条无门禁的改写路径。
AUTO_APPROVED_WRITE_TOOLS = {"fs.edit", "fs.write", "orc.fs.edit", "orc.fs.write"}


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
        roles=("developer",),
        permissions=registry.permissions_for(("developer",)),
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


def test_every_auto_approved_write_tool_guards_the_control_plane() -> None:
    """自动放行的写工具不得触达控制面：编排层挡着的前缀，dsh 这一段也必须挡。"""

    registry = _real_registry()
    auto = [
        spec
        for spec in registry.tools
        if spec.effect.value == "file_write" and spec.approval.value == "none"
    ]
    # 反真空：这条检查必须真的覆盖到四个自动放行写工具（dsh 的 fs.* 与编排层的 orc.fs.*）。
    # 只断言 fs.edit / fs.write 时，编排层那两条即使前缀表被悄悄改窄也发现不了。
    assert AUTO_APPROVED_WRITE_TOOLS <= {spec.id for spec in auto}

    missing = {
        spec.id: sorted(CONTROL_PLANE_PREFIXES - set(spec.parameter("file_path").blocked_prefixes))
        for spec in auto
        if CONTROL_PLANE_PREFIXES - set(spec.parameter("file_path").blocked_prefixes)
    }
    assert missing == {}, missing


def test_the_guard_blocks_a_control_plane_write(tmp_root: Path) -> None:
    """已审核哈希文件本身也不能被自动放行的写工具改写。"""

    outcome = _precheck(
        tmp_root,
        "fs.write",
        {"file_path": "registry/tool-registry.approved.json", "content": "{}\n"},
        action_id="guard-approved",
    )

    assert outcome.decision.decision is Decision.BLOCK
    check = outcome.decision.check("path_prefixes")
    assert check is not None and check.status is CheckStatus.FAILED
    assert "受保护前缀" in check.detail


@pytest.mark.parametrize(
    "tool_id, case_id, params",
    [
        # 信任根：审批条子 / 审计账本 / 受控执行台账。
        ("fs.edit", "approval-edit",
         {"file_path": ".policy/approval.json",
          "old_string": '"granted_by": "dshznm"', "new_string": '"granted_by": "mallory"'}),
        ("fs.write", "audit-write",
         {"file_path": ".policy/audit.jsonl", "content": "{\"sequence\": 1}\n"}),
        ("fs.write", "ledger-write",
         {"file_path": ".policy/enforcement-ledger.jsonl", "content": "{\"kind\": \"claim\"}\n"}),
        # 拼写归一化：大小写、"./"、以及前缀本身（边界等值）都必须命中。
        # blocked_path_prefix 的口径是 casefold + 去尾斜杠，Windows 文件系统不区分大小写，
        # 所以 .POLICY 与 .policy 是同一个目标——漏掉它就是一个真实可用的绕过。
        ("fs.edit", "upper-edit",
         {"file_path": ".POLICY/approval.json", "old_string": "a", "new_string": "b"}),
        ("fs.write", "dot-prefix-write",
         {"file_path": "./.policy/audit.jsonl", "content": "{}\n"}),
        ("fs.write", "exact-prefix-write",
         {"file_path": ".policy", "content": "x\n"}),
        # 编排层的两个自动放行写工具：两个 Agent 的信任根边界必须一致。
        ("orc.fs.edit", "orc-edit",
         {"file_path": ".policy/approval.json", "old_string": "a", "new_string": "b"}),
        ("orc.fs.write", "orc-write",
         {"file_path": ".policy/audit.jsonl", "content": "{}\n"}),
    ],
)
def test_the_guard_blocks_the_trust_root_write(
    tmp_root: Path, tool_id: str, case_id: str, params: dict
) -> None:
    """写 .policy/ 下的信任根必须被 path_prefixes 拦下（注册表 1.3 的数据缺口修复）。"""

    outcome = _precheck(
        tmp_root, tool_id, params, action_id=f"guard-trust-{case_id}"
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.PATH_OUT_OF_SCOPE
    check = outcome.decision.check("path_prefixes")
    assert check is not None and check.status is CheckStatus.FAILED
    assert "受保护前缀" in check.detail
    assert ".policy" in check.detail


@pytest.mark.parametrize(
    "tool_id, case_id, params, needle",
    [
        # 执行面：写 hook / 改 .git/config / 写 workflow 与写信任根同级（注册表 1.4）。
        ("fs.write", "git-hook-write",
         {"file_path": ".git/hooks/pre-commit", "content": "#!/bin/sh\nexit 0\n"}, ".git"),
        ("fs.edit", "git-config-edit",
         {"file_path": ".git/config", "old_string": "hooksPath = x",
          "new_string": "hooksPath = y"}, ".git"),
        ("fs.write", "workflow-edited",
         {"file_path": ".github/workflows/ci.yml", "content": "on: push\n"},
         ".github/workflows"),
        # 编排层写工具同样是自动放行：两个 Agent 的执行面边界必须一致。
        ("orc.fs.write", "orc-git-hook-write",
         {"file_path": ".git/hooks/pre-commit", "content": "#!/bin/sh\nexit 0\n"}, ".git"),
        # 拼写归一化：大小写与 "./" 是同一个目标（Windows 文件系统不区分大小写）。
        ("fs.write", "git-upper-write",
         {"file_path": ".GIT/hooks/pre-commit", "content": "#!/bin/sh\nexit 0\n"}, ".git"),
        ("fs.write", "workflow-dot-write",
         {"file_path": "./.github/workflows/ci.yml", "content": "on: push\n"},
         ".github/workflows"),
    ],
)
def test_the_guard_blocks_the_execution_surface_write(
    tmp_root: Path, tool_id: str, case_id: str, params: dict, needle: str
) -> None:
    """写 .git/ 与 .github/workflows/ 必须被 path_prefixes 拦下（注册表 1.4 的数据）。"""

    outcome = _precheck(
        tmp_root, tool_id, params, action_id=f"guard-exec-{case_id}"
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.PATH_OUT_OF_SCOPE
    check = outcome.decision.check("path_prefixes")
    assert check is not None and check.status is CheckStatus.FAILED
    assert "受保护前缀" in check.detail
    assert needle in check.detail


@pytest.mark.parametrize(
    "file_path",
    [
        ".gitignore",  # 不是 .git 之下（分段边界）
        ".github/ISSUE_TEMPLATE/bug.md",  # 只封 workflows，.github 其余部分放行
        ".github/workflowsx/ci.yml",  # 近似前缀不是 workflows 之下
    ],
)
def test_the_guard_does_not_block_the_execution_surface_lookalikes(
    tmp_root: Path, file_path: str
) -> None:
    """精度：执行面前缀按路径分段边界匹配，日常改 .gitignore / 模板不误伤。"""

    outcome = _precheck(
        tmp_root,
        "fs.write",
        {"file_path": file_path, "content": "placeholder\n"},
        action_id="guard-exec-precision-" + file_path.replace("/", "-").replace(".", "d"),
    )

    check = outcome.decision.check("path_prefixes")
    assert check is not None and check.status is CheckStatus.PASSED
    assert outcome.decision.decision is not Decision.BLOCK


def test_the_guard_does_not_block_the_lookalike_prefix(tmp_root: Path) -> None:
    """精度：.policyx/ 不是 .policy 之下——前缀按路径分段边界匹配，不做字符串前缀。"""

    outcome = _precheck(
        tmp_root,
        "fs.write",
        {"file_path": ".policyx/audit.jsonl", "content": "{}\n"},
        action_id="guard-lookalike",
    )

    check = outcome.decision.check("path_prefixes")
    assert check is not None and check.status is CheckStatus.PASSED
    assert outcome.decision.decision is not Decision.BLOCK


def test_the_rule_directory_is_still_blocked(tmp_root: Path) -> None:
    """回归：policies/（定义判定依据本身）在补 .policy 之后仍然被拦。"""

    outcome = _precheck(
        tmp_root,
        "fs.write",
        {"file_path": "policies/security/SEC-001.yaml", "content": "id: SEC-001\n"},
        action_id="guard-policies",
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.PATH_OUT_OF_SCOPE
    assert outcome.decision.check("path_prefixes").status is CheckStatus.FAILED


def test_the_guard_does_not_block_an_ordinary_workspace_file(tmp_root: Path) -> None:
    """对照组：这道闸只说控制面，受控项目里的普通文件照旧走正常授权链路。"""

    outcome = _precheck(
        tmp_root,
        "fs.write",
        {"file_path": "src/shop/cart_service.py", "content": "VALUE = 1\n"},
        action_id="guard-ordinary",
    )

    check = outcome.decision.check("path_prefixes")
    assert check is not None and check.status is CheckStatus.PASSED

"""只读命令族的**读面**闸门：注册表数据 + 真实 pre-check 的两面证据（B3 / 04 号 5.70）。

04 号 5.70 的读数：`exec.pwsh` 的只读命令族不受 `path_scope` 约束——写类参数的路径走
`policy.context.repo_relative_path` 的范围校验，而**命令文本里的路径操作数不走那一层**，
于是 `git show HEAD:.policy/approval.json`、`git log -p -- .policy/audit.jsonl` 在审批层
全部 PASS，读到的是信任根（审批条子与审计账本）。

本文件两条断言缺一不可（与 `test_registry_control_plane_guard.py` 同形）：

1. **数据面**：每个 `shell_command` 工具都必须为它的只读族声明 `read_guard`，且受保护前缀
   里含信任根 `.policy`——没有数据的闸门永远不会触发；
2. **行为面**：拿真注册表跑一次 pre-check，`git show HEAD:.policy/approval.json` 必须 block
   且原因是 `read_guard`；对照组（合法的只读命令）不被这道闸拦。

它**不**覆盖：选项取值（`--output=<路径>` 由 `forbidden_command_fragments` 管）、被引号
包裹且含空格的路径、git 配置与别名展开——结构性检查不是沙箱（AGENTS 第 17 条末句）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enforcement.audit import FileAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import CheckStatus, Decision, ReasonCode
from enforcement.precheck import pre_execute

from conftest import REPO_ROOT
from enforcement_support import ENFORCEMENT_APPROVED, ENFORCEMENT_REGISTRY

pytestmark = pytest.mark.contract

#: 信任根：审批条子、审计账本、已审核哈希派生出来的治理记录都在这里。
TRUST_ROOT_PREFIX = ".policy"

#: 只读族：这些族里的命令会读内容，因此必须过读面闸门。
READ_FAMILIES = {"readonly"}


def _real_registry():
    from enforcement.registry import load_registry

    return load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry


def _precheck(tmp_root: Path, command: str, *, action_id: str):
    from enforcement.action import build_action_request

    registry = _real_registry()
    spec = registry.tool("exec.pwsh")
    assert spec is not None
    request = build_action_request(
        spec,
        {"command": command, "description": "read face guard"},
        action_id=action_id,
        request_id=action_id,
        agent="dsh",
        agent_version="0.1.6-alpha.2",
        trace_id=None,
        subject="local-user",
        # owner 才有 shell.exec：permissions 先过，读面闸门才是这条用例的被测对象
        roles=("owner",),
        permissions=registry.permissions_for(("owner",)),
        workspace=REPO_ROOT,
        ttl_seconds=registry.grant_ttl_seconds,
    )
    return pre_execute(
        request,
        registry=registry,
        ledger=EnforcementLedger(tmp_root / (action_id + "-ledger.jsonl")),
        sink=FileAuditSink(tmp_root / (action_id + "-audit.jsonl"), workspace=REPO_ROOT),
        approval=None,
        dry_run=True,
    )


def test_every_read_family_declares_its_read_guard() -> None:
    """数据面：读了内容的命令族必须有读面数据，而且必须点名信任根。"""

    registry = _real_registry()
    shells = [spec for spec in registry.tools if spec.driver.value == "shell_command"]
    # 反真空：这条检查必须真的覆盖到 dsh 的两个命令类工具
    assert {"exec.pwsh", "exec.bash"} <= {spec.id for spec in shells}

    missing: dict[str, list[str]] = {}
    for spec in shells:
        read_family_ids = {family.id for family in spec.command_families} & READ_FAMILIES
        if not read_family_ids:
            continue
        if spec.read_guard is None:
            missing[spec.id] = ["<未声明 read_guard>"]
            continue
        gaps: list[str] = []
        uncovered = sorted(read_family_ids - set(spec.read_guard.families))
        if uncovered:
            gaps.append(f"未覆盖的只读族 {uncovered}")
        if TRUST_ROOT_PREFIX not in spec.read_guard.forbidden_path_prefixes:
            gaps.append(f"受保护前缀缺 {TRUST_ROOT_PREFIX!r}")
        if "revision_path" not in spec.read_guard.path_forms:
            gaps.append("<rev>:<path> 形态不在 path_forms 里")
        if gaps:
            missing[spec.id] = gaps
    assert missing == {}, missing


@pytest.mark.parametrize(
    "command",
    [
        # 04 号 5.70 的原始读数：改前这两条在审批层 PASS
        "git show HEAD:.policy/approval.json",
        "git log -p -- .policy/audit.jsonl",
        # 换拼写仍然命中（归一化 + 大小写不敏感 + 路径分段边界，不是字面子串）
        "git log -p -- ./.policy/audit.jsonl",
        "git show HEAD:.POLICY/approval.json",
    ],
)
def test_the_trust_root_is_not_readable_through_the_read_family(
    tmp_root: Path, command: str
) -> None:
    outcome = _precheck(tmp_root, command, action_id="read-face-trust-root")

    assert outcome.decision.decision is Decision.BLOCK
    check = outcome.decision.check("read_guard")
    assert check is not None and check.status is CheckStatus.FAILED
    assert check.reason_code is ReasonCode.READ_GUARD_BLOCKED
    # 与命令片段层分开：这两条命令里没有任何被禁片段，片段检查必须是 PASSED
    assert outcome.decision.check("command_fragments").status is CheckStatus.PASSED
    # 拒绝理由要给出"改成什么形态就能过"（AGENTS 第 50 条）
    assert "改成受控项目内的相对路径" in check.detail


def test_a_read_that_leaves_the_controlled_project_is_blocked(tmp_root: Path) -> None:
    """`<rev>:<path>` 形态里冒号右侧真的是 `..`：片段清单看不出它（没有 `../` 子串）。"""

    outcome = _precheck(tmp_root, "git show HEAD:..", action_id="read-face-escape")

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.READ_GUARD_BLOCKED
    assert outcome.decision.check("command_fragments").status is CheckStatus.PASSED


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git diff",
        "git log --oneline -5",
        "git log -p -- src/enforcement/precheck.py",
        "git show HEAD:src/enforcement/models.py",
    ],
)
def test_legal_read_only_commands_are_not_flagged(tmp_root: Path, command: str) -> None:
    """对照组：合法的只读命令不许被这道闸拦（它们仍可能缺审批，那由审批检查管）。"""

    outcome = _precheck(tmp_root, command, action_id="read-face-legal")

    check = outcome.decision.check("read_guard")
    assert check is not None and check.status is CheckStatus.PASSED, command
    assert outcome.decision.reason_code is not ReasonCode.READ_GUARD_BLOCKED, command

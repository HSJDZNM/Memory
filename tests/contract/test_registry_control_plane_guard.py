"""受控执行的信任根不能被「自动放行」的写工具改写（AGENTS 第 13 条 / L31）。

`registry/tool-registry.yaml` 的 `fs.edit` / `fs.write` 是 `approval: none` 的自动放行
写工具，它们此前只声明 `path_scope: workspace`：`policies/` `registry/` `adapters/`
`api/` `validation/` 这些**定义治理本身**的目录（规则、工具授权、适配器声明、已审核哈希）
都能被它们改写。编排层同形的 `orc.fs.edit` / `orc.fs.write` 一直是挡着的，两侧不对称留下
的是一条无门禁的篡改路径——改完注册表 / 哈希 / 声明，只有运行期"描述与已审核哈希对不上"
时才会被发现。

本文件两条断言缺一不可：

1. **数据面**：注册表里每个"不改就能自动放行"的写工具都必须声明同一组受保护前缀；
2. **行为面**：拿真注册表对 `registry/tool-registry.yaml` 跑一次 pre-check，必须是 block
   且原因是 `path_prefixes`；对照组（受控项目内的普通文件）不被这道闸拦。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enforcement.audit import FileAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import CheckStatus, Decision
from enforcement.precheck import pre_execute

from conftest import REPO_ROOT
from enforcement_support import ENFORCEMENT_APPROVED, ENFORCEMENT_REGISTRY

pytestmark = pytest.mark.contract

# 控制面：这些目录里的数据定义了"什么受治理、授权给谁、按什么口径判"。
CONTROL_PLANE_PREFIXES = {"policies", "registry", "adapters", "api", "validation"}


def _real_registry():
    from enforcement.registry import load_registry

    return load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry


def _precheck(tmp_root: Path, tool_id: str, params: dict, *, action_id: str):
    from enforcement.action import build_action_request

    registry = _real_registry()
    spec = registry.tool(tool_id)
    request = build_action_request(
        spec,
        params,
        action_id=action_id,
        request_id=action_id,
        agent="dsh",
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
    # 反真空：这条检查必须真的覆盖到 dsh 的两个自动放行写工具
    assert {"fs.edit", "fs.write"} <= {spec.id for spec in auto}

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

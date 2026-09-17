"""Phase 4 受控执行闭环：在受控工作区里重放"授权 → 执行 → 验证 → 审计"。

    python tools/enforcement_loop.py            # 跑完整闭环，结论写到 .tmp/artifacts/
    python tools/enforcement_loop.py --json     # 只打印结论

它证明四件事（对应 Phase 4 的退出条件）：

1. 允许的动作只执行一次，并留下与 action_hash 绑定的短时效授权；
2. 同一动作重放不会再执行（台账 + 审计链两处都拦得住）；
3. 事后验证失败会回滚（声明了 file_snapshot 的工具），并给出 repair_required；
4. 一条 trace 从 pre-check 到终态可被重放出来。

所有产物都写在 .tmp/phase-4-demo/ 下，不触碰仓库真实文件。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEMO_ROOT = REPO_ROOT / ".tmp" / "phase-4-demo"
WORKSPACE = DEMO_ROOT / "workspace"
AUDIT = DEMO_ROOT / "audit.jsonl"
LEDGER = DEMO_ROOT / "ledger.jsonl"
REGISTRY = REPO_ROOT / "registry" / "tool-registry.yaml"
APPROVED = REPO_ROOT / "registry" / "tool-registry.approved.json"
RESULT = REPO_ROOT / ".tmp" / "artifacts" / "phase-4-enforcement-result.json"

SOURCE = """from service import OrderService


def create_order(payload: dict) -> dict:
    return OrderService().create(payload)
"""


@dataclass
class Scenario:
    name: str
    passed: bool
    detail: str = ""
    facts: dict[str, Any] = field(default_factory=dict)


def prepare() -> None:
    shutil.rmtree(DEMO_ROOT, ignore_errors=True)
    (WORKSPACE / "src" / "shop").mkdir(parents=True, exist_ok=True)
    (WORKSPACE / "src" / "shop" / "order_controller.py").write_text(
        SOURCE, encoding="utf-8", newline=""
    )


def services():
    from enforcement.audit import FileAuditSink
    from enforcement.drivers import drivers_for
    from enforcement.executor import ControlledExecutor
    from enforcement.ledger import EnforcementLedger
    from enforcement.registry import load_registry

    registry = load_registry(REGISTRY, approved_path=APPROVED).registry
    sink = FileAuditSink(AUDIT, workspace=WORKSPACE)
    ledger = EnforcementLedger(LEDGER)
    executor = ControlledExecutor(
        ledger=ledger,
        drivers=drivers_for(registry.tools),
        sink=sink,
        max_grant_ttl_seconds=registry.max_grant_ttl_seconds,
    )
    return registry, sink, ledger, executor


def action_for(registry, *, action_id: str, old: str, new: str):
    from enforcement.action import build_action_request

    return build_action_request(
        registry.tool("fs.edit"),
        {
            "file_path": "src/shop/order_controller.py",
            "old_string": old,
            "new_string": new,
            "replace_all": False,
        },
        action_id=action_id,
        request_id=action_id,
        agent="dsh",
        agent_version="0.1.5-rc.1",
        trace_id="phase-4-demo",
        subject="local-user",
        roles=("developer",),
        permissions=registry.permissions_for(["developer"]),
        workspace=WORKSPACE,
        ttl_seconds=registry.grant_ttl_seconds,
    )


def run() -> list[Scenario]:
    from enforcement.models import FinalOutcome, PostStatus
    from enforcement.precheck import pre_execute
    from enforcement.trace import load_trace

    registry, sink, ledger, executor = services()
    scenarios: list[Scenario] = []

    # 1) 允许 → 执行一次 → 事后验证通过
    request = action_for(registry, action_id="demo:edit-1", old="from service import OrderService",
                         new="from service import OrderService\nfrom util import clock")
    pre = pre_execute(request, registry=registry, ledger=ledger, sink=sink)
    outcome = executor.execute(
        request, spec=registry.tool("fs.edit"), pre=pre.decision, workspace=WORKSPACE
    )
    content = (WORKSPACE / "src" / "shop" / "order_controller.py").read_text(encoding="utf-8")
    effect = None if outcome.evidence is None else outcome.evidence.file("src/shop/order_controller.py")
    scenarios.append(
        Scenario(
            name="allow_executes_once_and_validates",
            passed=(
                pre.decision.decision.value == "allow"
                and outcome.record.status.value == "executed"
                and outcome.post is not None
                and outcome.post.status is PostStatus.VALIDATED
                and outcome.final.outcome is FinalOutcome.DELIVERED
                and "from util import clock" in content
                and effect is not None
                and effect.changed
            ),
            detail="允许的动作只执行一次，并带上文件哈希 / diff 的事后证据",
            facts={
                "action_hash": request.action_hash,
                "grant_id": None if pre.decision.grant is None else pre.decision.grant.grant_id,
                "grant_ttl_seconds": int(
                    (pre.decision.grant.expires_at - pre.decision.grant.issued_at).total_seconds()
                )
                if pre.decision.grant is not None
                else None,
                "exit_code": outcome.record.exit_code,
                "post_status": None if outcome.post is None else outcome.post.status.value,
                "diff_digest": None if effect is None else effect.diff_digest,
            },
        )
    )

    # 2) 重放同一个动作：不执行第二次（台账与审计链都拦得住）
    replay = pre_execute(request, registry=registry, ledger=ledger, sink=sink)
    content_after = (WORKSPACE / "src" / "shop" / "order_controller.py").read_text(encoding="utf-8")
    scenarios.append(
        Scenario(
            name="replay_never_executes_twice",
            passed=replay.decision.decision.value == "block"
            and replay.decision.reason_code.value == "action_replay"
            and content_after == content,
            detail="同一 action_id 的第二次请求被阻断，文件没有第二次变化",
            facts={"reason_code": replay.decision.reason_code.value},
        )
    )

    # 3) 事后验证失败 → 回滚到执行前内容，并判 repair_required
    broken = action_for(
        registry,
        action_id="demo:edit-2",
        old="    return OrderService().create(payload)",
        new="    return OrderService().create(payload",
    )
    pre_broken = pre_execute(broken, registry=registry, ledger=ledger, sink=sink)
    outcome_broken = executor.execute(
        broken, spec=registry.tool("fs.edit"), pre=pre_broken.decision, workspace=WORKSPACE
    )
    restored = (WORKSPACE / "src" / "shop" / "order_controller.py").read_text(encoding="utf-8")
    scenarios.append(
        Scenario(
            name="post_check_failure_rolls_back",
            passed=(
                outcome_broken.post is not None
                and outcome_broken.post.status is PostStatus.REPAIR_REQUIRED
                and outcome_broken.post.rollback is not None
                and outcome_broken.post.rollback.status == "applied"
                and outcome_broken.final.outcome is FinalOutcome.ROLLED_BACK
                and restored == content
            ),
            detail="语法验证失败 → 回滚到执行前内容（只对声明 file_snapshot 的工具）",
            facts={
                "post_reason": None
                if outcome_broken.post is None
                else outcome_broken.post.reason_code.value,
                "rollback": None
                if outcome_broken.post is None or outcome_broken.post.rollback is None
                else outcome_broken.post.rollback.status,
                "final": outcome_broken.final.outcome.value,
            },
        )
    )

    # 4) 高风险动作：默认阻断（需要人工审批）
    high_risk = _high_risk_request(registry)
    needs_approval = pre_execute(high_risk, registry=registry, ledger=ledger, sink=sink)
    scenarios.append(
        Scenario(
            name="high_risk_needs_an_approval",
            passed=needs_approval.decision.decision.value == "block"
            and needs_approval.decision.reason_code.value in {"approval_required", "permission_denied"},
            detail="高权限动作缺少绑定审批时被阻断；审批由人工门禁签发（approve 子命令）",
            facts={
                "reason_code": needs_approval.decision.reason_code.value,
                "required_action": None
                if needs_approval.decision.required_action is None
                else needs_approval.decision.required_action.value,
            },
        )
    )

    # 5) trace 可重放
    report = load_trace(AUDIT, trace_id="phase-4-demo", require_final=False)
    stages = [entry.stage.value for entry in report.entries]
    scenarios.append(
        Scenario(
            name="trace_is_replayable",
            passed=report.ok and "pre_decision" in stages and "execution" in stages,
            detail="审计链按阶段可重放：request → … → pre_decision → execution → post_evidence → final_decision",
            facts={"stages": stages, "issues": list(report.issues)},
        )
    )
    return scenarios


def _high_risk_request(registry):
    from enforcement.action import build_action_request

    # 用仓库真实注册表里的高权限工具；命令在白名单内，唯一缺的是人工审批。
    return build_action_request(
        registry.tool("exec.pwsh"),
        {"command": "git status --short", "description": "demo"},
        action_id="demo:shell-1",
        request_id="demo:shell-1",
        agent="dsh",
        trace_id="phase-4-demo",
        subject="local-user",
        roles=("owner",),
        permissions=registry.permissions_for(["owner"]),
        workspace=WORKSPACE,
        ttl_seconds=registry.grant_ttl_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4 受控执行闭环")
    parser.add_argument("--json", action="store_true", help="只打印结论 JSON")
    parser.add_argument("--keep", action="store_true", help="保留演示目录（默认保留）")
    args = parser.parse_args(argv)

    prepare()
    scenarios = run()
    payload = {
        "phase": 4,
        "workspace": WORKSPACE.relative_to(REPO_ROOT).as_posix(),
        "audit": AUDIT.relative_to(REPO_ROOT).as_posix(),
        "result": "pass" if all(item.passed for item in scenarios) else "fail",
        "scenarios": [
            {"name": item.name, "passed": item.passed, "detail": item.detail, "facts": item.facts}
            for item in scenarios
        ],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for item in scenarios:
            mark = "PASS" if item.passed else "FAIL"
            print(f"[{mark}] {item.name}: {item.detail}")
        print(f"result: {payload['result']}  (证据: {RESULT.relative_to(REPO_ROOT).as_posix()})")
        if not all(item.passed for item in scenarios):
            # 失败时把关键事实打出来，便于定位（不含任何敏感内容）
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

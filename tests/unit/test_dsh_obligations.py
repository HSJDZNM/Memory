"""台阶 3c：**受治理会话**里的义务记账（Hook 侧，方案 §3.3 的"会话内只记账"）。

这一节钉三件事：

1. 判定带「待实现」时，声明了 `obligations_ledger` 的会话会往账本里记一条义务，
   而**判定一字不变**（仍然 `allow_with_warnings`、仍然退出 0）；
2. 没有声明账本 = 不记账（不是"没有义务"）；
3. 账本写不了**不改判定**（warn 期），但必须在 stderr 上显式说出来 ——
   静默失败会让"这次没记上"与"这次没有义务"长得一样。

**解除不在这条路径上记**（本文件第 4 条用例钉住）：解除只认一次**真实** pytest 运行，
而那份结构化证据（这次到底选中并执行了哪些测试）在预取证摘要里不存在；按
`served_checkers` 猜会把"选了一堆用例却一个都没跑起来"读成跑过了 —— 那是往
"义务被悄悄清掉"的方向错。解除由 `python -m policy.check --obligations` 记。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from conftest import dsh_event, make_checker_rule, write_dsh_config

from adapters.dsh.adapter import load_config
from adapters.dsh.hooks import EXIT_ALLOW, AuditLedger, DshPreExecuteHook
from policy.evidence import EvidenceBundle, PendingImplementation
from policy.models import RuleSet

TARGET = "src/shop/order_controller.py"

PENDING = PendingImplementation(
    validator_id="tool.pytest",
    validator_version="1.0",
    checkers=("failing_tests",),
    test_modules=("tests/test_order_service.py",),
    missing_targets=("shop.order_service:cancel_order",),
    reason="待实现：选中的测试在收集期就失败了——它 import 的项目内目标还不存在。",
    fix="先把 shop.order_service:cancel_order 落地，再重跑取证。",
)


class _PendingProvider:
    """交一份带「待实现」的证据包（形状与真流水线一致：bundle + summary）。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        return SimpleNamespace(
            bundle=EvidenceBundle(pending_implementation=(PENDING,)),
            summary={"status": "collected", "pending_implementation": [PENDING.to_payload()]},
        )


def _rules() -> RuleSet:
    return RuleSet(rules=(make_checker_rule("TESTING-002", checker="failing_tests"),))


def _pre_evidence_block(project: Path, shadow: Path) -> dict:
    return {
        "enabled": True,
        "registry_root": str(project.parent),
        "workspace": str(project),
        "shadow_root": str(shadow),
        "exclude": [".policy/**", "**/__pycache__/**"],
        "validators": ["tool.pytest"],
        "timeout_ms": 5000,
    }


def _hook(tmp_root: Path, project: Path, *, ledger) -> DshPreExecuteHook:
    config_path = write_dsh_config(
        tmp_root / "config" / "dsh-adapter.yaml",
        project_root=project,
        rules=tmp_root / "rules",
        pre_evidence=_pre_evidence_block(project, tmp_root / "shadow"),
        obligations_ledger=None if ledger is None else str(ledger),
    )
    return DshPreExecuteHook(
        config=load_config(config_path),
        rules=_rules(),
        ledger=AuditLedger(tmp_root / "audit.jsonl"),
        evidence_provider=_PendingProvider(),
    )


def _payload(project: Path) -> dict:
    return dsh_event("pre-tool-use-edit-allow.json", cwd=str(project))


def _records(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_a_pending_decision_books_an_obligation_without_changing_the_decision(
    tmp_root: Path, dsh_project, capsys
) -> None:
    ledger = tmp_root / "obligations.jsonl"
    hook = _hook(tmp_root, dsh_project, ledger=ledger)

    outcome = hook.handle(_payload(dsh_project))

    # 判定一字未变：待实现仍是 allow_with_warnings + 退出 0。
    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    assert outcome.reason_code == "allow_with_warnings"
    assert outcome.decision is not None and outcome.decision.pending_findings

    records = _records(ledger)
    assert [item["kind"] for item in records] == ["pending"], records
    assert records[0]["rule_id"] == "TESTING-002"
    assert records[0]["target"] == TARGET
    assert records[0]["test_module"] == "tests/test_order_service.py"
    assert records[0]["missing_target"] == "shop.order_service:cancel_order"
    # 命中必须在**进程 stderr** 上看得见（L5 的 warn 期要能数命中数）：
    # `outcome.stderr` 是给模型看的那一份，这两条通道不许混。
    assert "obligations recorded=1" in capsys.readouterr().err


def test_without_a_declaration_nothing_is_recorded(tmp_root: Path, dsh_project) -> None:
    """没有声明账本 = 不记账：账本文件不许被凭空创建出来。"""

    ledger = tmp_root / "not-declared.jsonl"
    hook = _hook(tmp_root, dsh_project, ledger=None)

    outcome = hook.handle(_payload(dsh_project))

    assert outcome.exit_code == EXIT_ALLOW
    assert outcome.reason_code == "allow_with_warnings"
    assert not ledger.exists()


def test_an_unwritable_ledger_is_loud_but_does_not_change_the_decision(
    tmp_root: Path, dsh_project, capsys
) -> None:
    """写不了账本不改判定（warn 期），但必须显式写一行 —— 静默失败就是"没记上"冒充"没有义务"。"""

    ledger = tmp_root / "ledger-as-directory"
    ledger.mkdir()
    hook = _hook(tmp_root, dsh_project, ledger=ledger)

    outcome = hook.handle(_payload(dsh_project))

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    assert outcome.reason_code == "allow_with_warnings"
    assert "OBLIGATIONS LEDGER UNAVAILABLE" in capsys.readouterr().err


def test_the_hook_records_no_discharge(tmp_root: Path, dsh_project) -> None:
    """Hook 只记义务，**不记解除**：解除要一次真实 pytest 运行的结构化证据，这条路径没有。"""

    ledger = tmp_root / "obligations.jsonl"
    hook = _hook(tmp_root, dsh_project, ledger=ledger)

    hook.handle(_payload(dsh_project))
    second = dsh_event(
        "pre-tool-use-edit-allow.json", cwd=str(dsh_project), tool_use_id="call-2"
    )
    hook.handle(second)

    kinds = [item["kind"] for item in _records(ledger)]
    assert kinds == ["pending", "pending"], kinds

"""Phase 6 多 Agent 闭环：在受控工作区里重放"事件 → 判定 → 响应"。


    python tools/agent_loop.py            # 跑完整闭环，结论写到 .tmp/artifacts/
    python tools/agent_loop.py --json     # 只打印结论

它证明六件事（对应 Phase 6 的退出条件）：

1. 同一个语义事件（Controller 直连 Repository）在**每个** Adapter 上都得到同一个结论，
   且被阻断时原生工具一次都没有被调用；
2. 允许的改动在每个 Adapter 上恰好执行一次；
3. 能力不足的协议消费者（只有 PostToolUse）在接入时就被标成只读，
   并且对写类动作显式给出 capability_unavailable，而不是跳过治理；
4. 跨 Agent 隔离：A 的 event_id 不会命中 B 的台账，A 的判定也不会替 B 放行；
5. 伪造父 trace 与重复 event_id 都被拒绝（幂等）；
6. 支持矩阵与已审核哈希一致；改能力声明必须重新审核。

所有产物都写在 .tmp/phase-6-demo/ 下，受控工作区指向仓库内的探针夹具，
不触碰仓库真实文件。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEMO_ROOT = REPO_ROOT / ".tmp" / "phase-6-demo"
RESULT = REPO_ROOT / ".tmp" / "artifacts" / "phase-6-agents-result.json"
WORKSPACE = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"

AGENTS = ("dsh", "generic-json", "legacy-post-only")

# 语义动作：在 Controller 里直接依赖 Repository（ARCH-001 禁止的那件事）。
VIOLATING = "from repository import OrderRepository"
CLEAN = "value = 1"


@dataclass
class Scenario:
    name: str
    passed: bool
    detail: str = ""
    facts: dict[str, Any] = field(default_factory=dict)


def _load(*, state_name: str = "main", breaker_limit: int = 50):
    from adapters.conformance import conformance_enforcer, conformance_evidence
    from adapters.loader import load_adapters, load_registry_from_repo
    from adapters.runtime import AgentRuntime
    from policy.loader import load_rule_set

    registry = load_registry_from_repo(REPO_ROOT)
    rules = load_rule_set([REPO_ROOT / "policies"], repo_root=REPO_ROOT)
    adapters = load_adapters(list(AGENTS), root=REPO_ROOT, registry=registry)
    state_root = DEMO_ROOT / state_name
    state_root.mkdir(parents=True, exist_ok=True)
    enforcer = conformance_enforcer(
        adapters["dsh"], workspace=WORKSPACE, state_root=state_root / "enforcement"
    )
    runtime = AgentRuntime(
        adapters=adapters,
        rules=rules,
        registry=registry,
        ledger_path=state_root / "ledger.jsonl",
        trace_path=state_root / "traces.jsonl",
        workspace=WORKSPACE,
        breaker_limit=breaker_limit,
        enforcers={"dsh": enforcer},
        evidence_providers={"dsh": conformance_evidence},
    )
    return registry, rules, adapters, runtime


def _dsh_event(session: str, call: str, text: str, **extra: Any) -> dict:
    raw = {
        "hook_event_name": "PreToolUse",
        "session_id": session,
        "tool_name": "edit",
        "tool_use_id": call,
        "cwd": str(WORKSPACE),
        "tool_input": {
            "file_path": "src/shop/order_controller.py",
            "old_string": "pass",
            "new_string": text,
        },
    }
    raw.update(extra)
    return raw


def _generic_event(key: str, text: str, tool: str = "edit") -> dict:
    return {
        "schema_version": "1.0",
        "event_id": f"{key}:call",
        "event_type": "tool.pre_execute",
        "request_id": f"{key}:call",
        "tool": tool,
        "operation": "edit" if tool == "edit" else "read",
        "principal": {"subject": "local-user", "roles": ["developer"]},
        "payload": {
            "path": "src/shop/order_controller.py",
            "params": {"new_string": text},
        },
    }


def scenario_equivalent_decisions(adapters, runtime) -> Scenario:
    """同一个语义动作在每个 Adapter 上得到同一个结论。"""

    facts: dict[str, Any] = {"decisions": {}, "tool_calls": {}}
    ok = True
    for index, agent in enumerate(AGENTS):
        if agent == "dsh":
            raw = _dsh_event(f"eq-{index}", "c1", VIOLATING)
        elif agent == "generic-json":
            raw = _generic_event(f"eq-{index}", VIOLATING)
        else:
            raw = {
                "hook_event_name": "PostToolUse",
                "session_id": f"eq-{index}",
                "tool_name": "save_file",
                "tool_use_id": "c1",
                "cwd": str(WORKSPACE),
                "tool_input": {
                    "file_path": "src/shop/order_controller.py",
                    "text": VIOLATING,
                },
            }
        calls: list[Any] = []
        outcome = runtime.handle(agent, raw, execute=calls.append)
        facts["decisions"][agent] = outcome.outcome_code
        facts["tool_calls"][agent] = len(calls)
        if outcome.response.decision.value != "block" or calls:
            ok = False
    return Scenario(
        name="blocked-action-never-executes",
        passed=ok,
        detail="违规改动在每个 Agent 上都被阻断，且原生工具一次都没被调用",
        facts=facts,
    )


def scenario_allow_executes_once(adapters, runtime) -> Scenario:
    calls: list[Any] = []
    outcome = runtime.handle("dsh", _dsh_event("allow-1", "c1", CLEAN), execute=calls.append)
    replay = runtime.handle("dsh", _dsh_event("allow-1", "c1", CLEAN), execute=calls.append)
    return Scenario(
        name="allowed-action-executes-exactly-once",
        passed=(
            outcome.outcome_code in ("allow", "allow_with_warnings")
            and replay.outcome_code == "event_replay"
            and len(calls) == 1
        ),
        detail="允许的动作恰好执行一次；同一 event_id 重放被幂等阻断",
        facts={
            "decision": outcome.outcome_code,
            "replay": replay.outcome_code,
            "tool_calls": len(calls),
        },
    )


def scenario_capability_degradation(registry, runtime) -> Scenario:
    descriptor = registry.as_list().get("legacy-post-only")
    calls: list[Any] = []
    outcome = runtime.handle(
        "legacy-post-only",
        {
            "hook_event_name": "PostToolUse",
            "session_id": "cap-1",
            "tool_name": "save_file",
            "tool_use_id": "c1",
            "cwd": str(WORKSPACE),
            "tool_input": {"file_path": "src/shop/order_controller.py", "text": CLEAN},
        },
        execute=calls.append,
    )
    return Scenario(
        name="capability-shortfall-fails-closed",
        passed=(
            descriptor.enforcement.value == "read_only"
            and outcome.outcome_code == "capability_unavailable"
            and not calls
        ),
        detail="只有 PostToolUse 的 Agent 被标成只读，写类动作显式拒绝",
        facts={
            "enforcement": descriptor.enforcement.value,
            "reasons": list(descriptor.ceiling_reasons),
            "outcome": outcome.outcome_code,
        },
    )


def scenario_cross_agent_isolation(runtime) -> Scenario:
    first = runtime.handle("dsh", _dsh_event("iso-1", "c1", CLEAN), execute=lambda e: None)
    second = runtime.handle("generic-json", _generic_event("iso-1", CLEAN), execute=lambda e: None)
    keys = {
        item.get("ledger_key") for item in runtime._entries() if item.get("ledger_key")  # noqa: SLF001
    }
    return Scenario(
        name="cross-agent-namespaces-are-separate",
        passed=(
            "dsh:iso-1:c1" in keys
            and "generic-json:iso-1:call" in keys
            and second.outcome_code != "event_replay"
        ),
        detail="同一个 event_id 在两个 Agent 下互不影响（命名空间隔离）",
        facts={
            "dsh": first.outcome_code,
            "generic-json": second.outcome_code,
            "ledger_keys": sorted(keys)[:6],
        },
    )


def scenario_trace_provenance(runtime) -> Scenario:
    forged = runtime.handle(
        "dsh", _dsh_event("trace-1", "c1", CLEAN, parent_trace_id="never-issued"), execute=lambda e: None
    )
    runtime.trace.register(trace_id="trace-root", owner_agent="dsh", request_id="r:1")
    child = runtime.handle(
        "dsh",
        _dsh_event("trace-2", "c1", CLEAN, trace_id="trace-child", parent_trace_id="trace-root"),
        execute=lambda e: None,
    )
    return Scenario(
        name="trace-provenance-is-verifiable",
        passed=(
            forged.outcome_code == "trace_forged"
            and child.outcome_code in ("allow", "allow_with_warnings")
            and child.response.trace_id == "trace-child"
        ),
        detail="伪造父 trace 被拒绝；来源可验证的 trace 被原样保留",
        facts={"forged": forged.outcome_code, "child": child.outcome_code, "trace": child.response.trace_id},
    )


def scenario_breaker(runtime) -> Scenario:
    codes: list[str] = []
    for index in range(8):
        agent = "dsh" if index % 2 == 0 else "generic-json"
        raw = (
            _dsh_event(f"loop-{index}", f"c{index}", CLEAN)
            if agent == "dsh"
            else _generic_event(f"loop-{index}", CLEAN, tool="read")
        )
        codes.append(f"{agent}:{runtime.handle(agent, raw, execute=lambda e: None).outcome_code}")
    return Scenario(
        name="cross-agent-loop-is-terminated",
        passed=any(code == "dsh:request_busy" for code in codes),
        detail="窗口内事件数到上限即熔断（互相触发的循环不会烧完预算）",
        facts={"sequence": codes},
    )


def scenario_support_matrix(registry, conformance) -> Scenario:
    listing = registry.as_list()
    levels = {item.agent_id: item.enforcement.value for item in listing.descriptors}
    approved = all(item.approved for item in listing.descriptors)
    return Scenario(
        name="support-matrix-distinguishes-levels",
        passed=(
            approved
            and levels.get("dsh") == "full"
            and levels.get("legacy-post-only") == "read_only"
            and levels.get("generic-json") == "read_only"
            and conformance is not None
            and conformance.ok
        ),
        detail="支持矩阵区分 full / read_only，且所有能力声明都经过审核",
        facts={
            "levels": levels,
            "reviewed_by": listing.reviewed_by,
            "conformance_checks": 0 if conformance is None else len(conformance.checks),
        },
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 多 Agent 闭环")
    parser.add_argument("--json", action="store_true", help="只打印 JSON 结论")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

    from adapters.conformance import run_conformance

    # 每轮从空目录开始：台账是本轮的幂等记录。复用上一轮的文件会让本轮的事件
    # 立刻被判成"重放"，闭环就会因为"上一轮跑过"而失败——那与被测行为无关。
    shutil.rmtree(DEMO_ROOT, ignore_errors=True)

    registry, rules, adapters, runtime = _load()
    loop_runtime = _load(state_name="breaker", breaker_limit=3)[3]
    conformance = run_conformance(
        adapters=adapters,
        rules=rules,
        workspace=WORKSPACE,
        outside=WORKSPACE.parent / "outside-workspace.py",
        ledger_dir=DEMO_ROOT / "conformance-ledger",
        trace_path=DEMO_ROOT / "conformance-traces.jsonl",
        breaker_limit=3,
    )

    scenarios = [
        scenario_equivalent_decisions(adapters, runtime),
        scenario_allow_executes_once(adapters, runtime),
        scenario_capability_degradation(registry, runtime),
        scenario_cross_agent_isolation(runtime),
        scenario_trace_provenance(runtime),
        scenario_breaker(loop_runtime),
        scenario_support_matrix(registry, conformance),
    ]
    passed = all(item.passed for item in scenarios)
    payload = {
        "phase": 6,
        "result": "pass" if passed else "fail",
        "workspace": WORKSPACE.relative_to(REPO_ROOT).as_posix(),
        "demo_root": DEMO_ROOT.relative_to(REPO_ROOT).as_posix(),
        "agents": list(AGENTS),
        "matrix": {
            item.agent_id: {
                "enforcement": item.enforcement.value,
                "approved": item.approved,
                "protocol": item.protocol,
                "agent_version": item.agent_version,
            }
            for item in registry.as_list().descriptors
        },
        "scenarios": [
            {"name": item.name, "passed": item.passed, "detail": item.detail, "facts": item.facts}
            for item in scenarios
        ],
        "conformance": {
            "checks": len(conformance.checks),
            "coverage": conformance.summary()["coverage"],
            "failures": [item.to_dict() for item in conformance.failures],
        },
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if passed else 1

    print(f"Phase 6 多 Agent 闭环：{'pass' if passed else 'fail'}")
    for item in scenarios:
        mark = "PASS" if item.passed else "FAIL"
        print(f"  [{mark}] {item.name}: {item.detail}")
        if not item.passed:
            print(f"         facts: {json.dumps(item.facts, ensure_ascii=False)}")
    print(f"  一致性套件：{len(conformance.checks)} 项检查，{len(conformance.failures)} 项失败")
    print(f"  结论写到 {RESULT.relative_to(REPO_ROOT).as_posix()}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

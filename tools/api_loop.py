"""Phase 7 Policy API 闭环：把"服务化之后语义没变"这件事证明出来。

    python tools/api_loop.py            # 跑完整闭环，结论写到 .tmp/artifacts/
    python tools/api_loop.py --json     # 只打印结论

它证明七件事（对应 Phase 7 的退出条件）：

1. **同一份规则、两条路径、同一个结论**：本地 `policy.engine.evaluate` 与经 HTTP 的
   `/v1/policy/evaluate` 对等价上下文给出**整份相等**的决策载荷（JSON 值相等，字段顺序
   不属于契约——比的是决定，不是两侧序列化出来的字节）；
2. **两个协议消费者等价**：Phase 6 的一致性套件同时跑 `generic-json`（进程内）与
   `http-api`（经 API 判定），两者的 outcome 与决定必须一致；
3. **服务异常不返回默认 allow**：超时得到 504（不是 allow）、策略服务不可达时
   Adapter 得到 `policy_unavailable` 的阻断响应；
4. **幂等**：同一个 idempotency_key 重放返回原响应且标记 replayed，换请求体得到 409；
5. **租户隔离**：令牌只能访问自己的租户，跨租户引用别人的 decision_ref 得到 403；
6. **readiness 反映真实依赖**：规则目录不可用时 readiness 失败，evaluate 得到
   `rule_set_unavailable`；
7. **审计可锚定**：观测日志的摘要链能封成对外锚，删掉尾部记录后校验失败。

所有产物都在 `.tmp/phase-7-api/` 下；HTTP 用的是**本机真实端口**（127.0.0.1），
不打外网、不改仓库真实文件。
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEMO_ROOT = REPO_ROOT / ".tmp" / "phase-7-api"
RESULT = REPO_ROOT / ".tmp" / "artifacts" / "phase-7-api-result.json"
FIXTURE_PROJECT = REPO_ROOT / "tests" / "fixtures" / "validators" / "project"
AGENT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"
TOKEN = "loop-alpha-token"
OPS_TOKEN = "loop-ops-token"
HOST = "127.0.0.1"


@dataclass
class Scenario:
    name: str
    passed: bool
    detail: str = ""
    facts: dict[str, Any] = field(default_factory=dict)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def build_config(port: int) -> Path:
    """把"两个租户 + 三条客户端"写成一份临时部署配置（路径相对仓库根）。"""

    from policy_api.config import hash_token

    workspace = DEMO_ROOT / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    shutil.copytree(FIXTURE_PROJECT, workspace)
    config = DEMO_ROOT / "policy-api.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    document = """
schema_version: "1.0"
service_name: phase7-loop
deployment: loop
base_url: http://{host}:{port}
limits:
  max_request_bytes: 65536
  max_response_bytes: 262144
  max_context_bytes: 32768
  max_prompt_chars: 8000
  max_concurrency: 4
budgets:
  evaluate_ms: 2000
  retrieve_ms: 2000
  validate_ms: 10000
rate_limit:
  capacity: 1000
  refill_per_second: 1000.0
audit:
  enabled: true
  path: {audit}
metrics_clients: [ops-monitor]
tenants:
  - tenant_id: alpha
    display_name: Alpha
    project: alpha-project
    project_root: {workspace}
    rules_root: {workspace}
    rules: [rules]
    audit_log: {alpha_audit}
  - tenant_id: beta
    display_name: Beta
    project: beta-project
    project_root: {workspace}
    rules_root: {workspace}
    rules: [rules]
    audit_log: {beta_audit}
clients:
  - client_id: alpha-client
    token_sha256: {token}
    tenants: [alpha]
    projects: [alpha-project]
    roles: [developer]
  - client_id: beta-client
    token_sha256: {beta}
    tenants: [beta]
    projects: [beta-project]
    roles: [developer]
  - client_id: ops-monitor
    token_sha256: {ops}
    tenants: [alpha, beta]
    roles: [ops]
""".format(
        host=HOST,
        port=port,
        workspace=workspace.relative_to(REPO_ROOT).as_posix(),
        audit=(DEMO_ROOT / "audit.jsonl").relative_to(REPO_ROOT).as_posix(),
        alpha_audit=(DEMO_ROOT / "audit.alpha.jsonl").relative_to(REPO_ROOT).as_posix(),
        beta_audit=(DEMO_ROOT / "audit.beta.jsonl").relative_to(REPO_ROOT).as_posix(),
        token=hash_token(TOKEN),
        beta=hash_token("loop-beta-token"),
        ops=hash_token(OPS_TOKEN),
    )
    config.write_text(document.lstrip(), encoding="utf-8", newline="\n")
    # 规则集必须与"本地引擎那一侧"逐字节相同：闭环要比的是**决定**，
    # 不是"两套规则碰巧给出的结果"。因此把仓库规则的副本放进受控工作区，
    # 让 HTTP Adapter 的声明（rules: [rules]）指向它。
    #
    # 同时给 HTTP Adapter 写一份自己的 adapter 配置：它的 project 必须落在
    # 该令牌被授权的项目内（`alpha-project`），否则 API 会（正确地）用
    # project_not_allowed 拒绝——那不是"决定不一致"，是环境没摆对。
    adapter_config = DEMO_ROOT / "http-adapter.yaml"
    adapter_config.write_text(
        "\n".join(
            [
                "# 闭环用的 HTTP Adapter 配置（只给 tools/api_loop.py 使用，不提交）",
                'schema_version: "1.0"',
                "project_root: .",
                "project: alpha-project",
                "rules:",
                "  - rules",
                "timeout_ms: 5000",
                "layers:",
                '  - pattern: "**/*_controller.py"',
                "    layer: controller",
                '  - pattern: "**/*_service.py"',
                "    layer: service",
                '  - pattern: "**/*_repository.py"',
                "    layer: repository",
                '  - pattern: "**/*.py"',
                "    layer: module",
                "default_layer: null",
                "languages:",
                '  - pattern: "**/*.py"',
                "    language: python",
                "default_language: text",
                "principal:",
                "  subject: local-user",
                "  roles: [developer]",
                "ledger_alias: http-api",
                "max_events_per_window: 200",
                "window_seconds: 60",
                # 审计写在受控工作区里，不散落到仓库根：闭环只动 .tmp/。
                "audit_log: .tmp/phase-7-api/workspace-audit.jsonl",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    rules = workspace / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    for source in sorted((REPO_ROOT / "policies").rglob("*.yaml")):
        parts = source.relative_to(REPO_ROOT / "policies").parts
        target = rules / "_".join(parts)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return config


def start_server(runtime: Any, port: int) -> Any:
    """在后台线程起一个真实的 uvicorn（真端口、真协议），返回 server 句柄。"""

    import uvicorn

    from policy_api.app import create_app

    server = uvicorn.Server(
        uvicorn.Config(create_app(runtime), host=HOST, port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, name="phase7-api", daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if getattr(server, "started", False):
            return server
        time.sleep(0.05)
    raise RuntimeError("uvicorn 未能在 20s 内启动")


# --------------------------------------------------------------------------- 场景


def scenario_local_and_api_agree(runtime: Any) -> Scenario:
    """同一上下文：本地引擎与 HTTP API 的决策载荷整份相等（比 JSON 值，不比字节）。"""

    from policy.context import build_context
    from policy.engine import evaluate
    from policy_api.probe import HttpApiClient

    tenant = runtime.store.get("alpha")
    rules = tenant.rules()
    payload = {
        "file": "src/shop/order_controller_bad.py",
        "layer": "controller",
        "language": "python",
    }
    context = build_context(
        {"request_id": "loop:agree", **payload}, repo_root=tenant.project_root
    )
    local = evaluate(rules, context).to_decision_dict()

    client = HttpApiClient(runtime.config.base_url, token=TOKEN)
    status, body = client.post(
        "/v1/policy/evaluate",
        {
            "api_version": "1.0",
            "request_id": "loop:agree",
            "tenant": "alpha",
            "principal": {"subject": "loop", "roles": ["developer"]},
            "context": payload,
        },
    )
    remote = body.get("decision") if status == 200 else None
    same = status == 200 and remote == local
    return Scenario(
        "本地引擎与 HTTP API 的决策载荷整份相等",
        same,
        "一致" if same else f"HTTP {status} / {json.dumps(body, ensure_ascii=False)[:200]}",
        {
            "decision": local["decision"],
            "rule_set_hash": local["rule_set_hash"],
            "api_status": status,
        },
    )


def scenario_consumers_agree(runtime: Any) -> Scenario:
    """Phase 6 的一致性套件：进程内 JSON 消费者 与 经 API 的消费者结论一致。"""

    from adapters.base import AdapterRegistry
    from adapters.conformance import SCENARIOS, render_event, run_conformance
    from adapters.json_adapter import JsonAdapter
    from adapters.loader import load_adapter_config, load_registry_from_repo
    from policy.engine import evaluate
    from policy_api.probe import HttpApiAdapter, HttpApiClient

    registry: AdapterRegistry = load_registry_from_repo(REPO_ROOT)
    workspace = DEMO_ROOT / "workspace"
    # 用闭环自己写出来的 adapter 配置：它的 project 必须落在该令牌被授权的项目内
    # （`alpha-project`），否则 API 会用 project_not_allowed 拒绝——那是环境没摆对，
    # 不是"决定不一致"。
    config_path = DEMO_ROOT / "http-adapter.yaml"
    adapters: dict[str, Any] = {}

    # 同一个协议、同一条判定入口，只是一个走进程内、一个走 HTTP。
    # 能力声明沿用 generic-json 的 read_only：HTTP 只是**传输**，它并不执行工具，
    # 也不接入 Phase 4；给它声明 full 只会让"写类动作被能力门禁拦下"看起来像是
    # "API 决定的"。声明与真实接线一致，是 Phase 6 就定下的纪律。
    base_manifest = registry.manifest("generic-json")
    http_manifest = base_manifest.model_copy(
        update={"agent_id": "http-api", "display_name": "HTTP API 消费者"}
    )
    adapter_config = load_adapter_config(config_path)
    adapters["http-api"] = HttpApiAdapter(
        manifest=http_manifest,
        config=adapter_config,
        config_path=config_path,
        base_dir=REPO_ROOT,
        client=HttpApiClient(runtime.config.base_url, token=TOKEN),
    )
    adapters["generic-json"] = JsonAdapter(
        manifest=base_manifest,
        config=adapter_config,
        config_path=config_path,
        base_dir=REPO_ROOT,
    )

    rules = runtime.store.get("alpha").rules()
    report = run_conformance(
        adapters=adapters,
        rules=rules,
        workspace=workspace,
        outside=str(workspace.parent / "outside"),
        ledger_dir=DEMO_ROOT / "conformance",
        trace_path=DEMO_ROOT / "conformance" / "traces.jsonl",
    )
    failures = [item for item in report.failures]

    # 套件本身证明的是"两个消费者在**同一套语义**下走完了全部场景"；
    # 它不比较"决定的内容"（泛型 JSON 消费者不接受控执行，写类动作按能力上限拒绝）。
    # 决定内容的等价性在这里逐场景比对：同一个渲染事件，本地引擎与 HTTP API 的决定必须一致。
    divergences: list[dict[str, Any]] = []
    compared = 0
    for scenario in SCENARIOS:
        if scenario.event_type != "tool.pre_execute" or scenario.path is None:
            continue
        raw = render_event(adapters["http-api"], scenario, index=0, workspace=workspace)
        try:
            event = adapters["http-api"].to_policy_event(raw)
            context = adapters["http-api"].to_policy_context(event, workspace=workspace)
        except Exception as error:  # noqa: BLE001 - 渲染不出来的场景不参与比对（套件已单独报告）
            divergences.append({"scenario": scenario.name, "error": type(error).__name__})
            continue
        local = evaluate(rules, context).to_decision_dict()
        remote = adapters["http-api"].decide(event, workspace=workspace)
        compared += 1
        if remote != local:
            divergences.append(
                {
                    "scenario": scenario.name,
                    "local": local.get("decision"),
                    "remote": remote.get("decision"),
                }
            )

    equal = [item for item in divergences if item.get("error") is None]
    facts = {
        "summary": dict(report.summary()),
        "failures": [item.name for item in failures][:5],
        "decisions_compared": compared,
        "decisions_divergent": [item for item in divergences if item.get("error") is None],
        "skipped": [item for item in divergences if item.get("error") is not None],
    }
    # 本闭环里的两个消费者都声明 read_only（HTTP 只是传输、不执行工具），
    # 因此套件那条"至少要有一个完整 enforcement 的 Adapter"在这里必然失败——
    # 它测的是别的东西（谁有执行能力），把它算成"决定不等价"是错误归因。
    # 这里只认两件事：没有**除它以外**的失败，且逐场景决定零分歧。
    unexpected = [item.name for item in failures if item.name != "at_least_one_full_adapter"]
    return Scenario(
        "两个协议消费者（进程内 / 经 HTTP）走到同一套结论，且逐场景决定整份相等",
        not unexpected and not equal and compared >= 4,
        f"{len(report.checks)} 项检查（read_only 上限 1 项预期内），决定比对 {compared} 例",
        {**facts, "unexpected_failures": unexpected},
    )


def scenario_timeout_is_not_allow(runtime: Any) -> Scenario:
    """下游超时 → 504；调用方要更小的预算 → 504；绝不返回 allow。"""

    from policy_api.errors import ErrorCode
    from policy_api.testing import call

    def slow_evaluate(rules: Any, context: Any) -> Any:
        time.sleep(0.5)
        from policy.engine import evaluate as real

        return real(rules, context)

    import policy_api.runtime as runtime_module

    saved = runtime_module.evaluate
    runtime_module.evaluate = slow_evaluate
    try:
        payload = {
            "api_version": "1.0",
            "request_id": "loop:timeout",
            "tenant": "alpha",
            "budget_ms": 50,
            "principal": {"subject": "loop", "roles": ["developer"]},
            "context": {"file": "src/shop/order_service.py", "layer": "service"},
        }
        response = call(runtime, "evaluate", payload, token=TOKEN)
    finally:
        runtime_module.evaluate = saved
    code = (response.body.get("error") or {}).get("code")
    return Scenario(
        "策略超时返回 504（超时绝不等于 allow）",
        response.status == 504 and code == ErrorCode.EVALUATE_TIMEOUT.value,
        f"HTTP {response.status} / {code}",
        {"status": response.status, "code": code},
    )


def scenario_unreachable_api_fails_closed(runtime: Any) -> Scenario:
    """策略服务不可达：Adapter 必须得到阻断响应，而不是放行。"""

    from adapters.loader import load_adapter_config, load_registry_from_repo
    from policy.models import Decision
    from policy_api.probe import HttpApiAdapter, HttpApiClient

    registry = load_registry_from_repo(REPO_ROOT)
    config_path = REPO_ROOT / "adapters" / "generic-json" / "adapter.yaml"
    dead = free_port()  # 没有任何进程监听这个端口
    adapter = HttpApiAdapter(
        manifest=registry.manifest("generic-json").model_copy(update={"agent_id": "http-dead"}),
        config=load_adapter_config(config_path),
        config_path=config_path,
        client=HttpApiClient(f"http://{HOST}:{dead}", token=TOKEN, timeout=1.0),
    )
    event = adapter.to_policy_event(
        {
            "schema_version": "1.0",
            "event_id": "loop:dead:1",
            "event_type": "tool.pre_execute",
            "request_id": "loop:dead",
            "agent_version": adapter.agent_version,
            "principal": {"subject": "local-user", "roles": ["developer"]},
            "tool": "write",
            "operation": "create",
            "payload": {"path": "src/shop/order_service.py", "text": "x = 1\n"},
        }
    )
    decision = adapter.decide(event, workspace=DEMO_ROOT / "workspace")
    blocked = decision.get("decision") == Decision.BLOCK.value
    rule_ids = [item.get("rule_id") for item in decision.get("violations", [])]
    return Scenario(
        "策略服务不可达 → Adapter 阻断（失败关闭，不放行）",
        blocked and "API-000" in rule_ids,
        f"decision={decision.get('decision')} rules={rule_ids}",
        {"decision": decision.get("decision"), "rules": rule_ids},
    )


def scenario_idempotency(runtime: Any) -> Scenario:
    """同一个 key 重放返回原响应；同一个 key 换了请求体就是冲突。"""

    from policy_api.testing import call

    base = {
        "api_version": "1.0",
        "request_id": "loop:idem",
        "tenant": "alpha",
        "idempotency_key": "loop-key-1",
        "principal": {"subject": "loop", "roles": ["developer"]},
        "context": {"file": "src/shop/order_controller.py", "layer": "controller"},
    }
    first = call(runtime, "evaluate", base, token=TOKEN)
    second = call(runtime, "evaluate", base, token=TOKEN)
    changed = call(
        runtime,
        "evaluate",
        {**base, "context": {"file": "src/shop/order_service.py", "layer": "service"}},
        token=TOKEN,
    )
    conflict = (changed.body.get("error") or {}).get("code")
    same = (
        first.status == 200
        and second.status == 200
        and first.body == second.body
        and second.headers.get("Idempotency-Replayed") == "true"
    )
    return Scenario(
        "幂等键重放不重复判定，换请求体则冲突",
        same and conflict == "idempotency_key_conflict",
        f"replay={second.headers.get('Idempotency-Replayed')} conflict={conflict}",
        {
            "same_body": first.body == second.body,
            "replayed": second.headers.get("Idempotency-Replayed"),
            "conflict": conflict,
        },
    )


def scenario_tenant_isolation(runtime: Any) -> Scenario:
    """跨租户不可见：alpha 的决策引用不能给 beta 用，令牌也不能"顺手"访问别的租户。"""

    from policy_api.testing import call

    evaluated = call(
        runtime,
        "evaluate",
        {
            "api_version": "1.0",
            "request_id": "loop:iso",
            "tenant": "alpha",
            "principal": {"subject": "loop", "roles": ["developer"]},
            "context": {"file": "src/shop/order_controller.py", "layer": "controller"},
        },
        token=TOKEN,
    )
    cross = call(
        runtime,
        "retrieve",
        {
            "api_version": "1.0",
            "request_id": "loop:iso2",
            "tenant": "beta",
            "principal": {"subject": "loop", "roles": ["developer"]},
            "context": {"file": "src/shop/order_service.py", "layer": "service", "task": "review"},
            "decision_ref": "loop:iso",
        },
        token="loop-beta-token",
    )
    forbidden = call(
        runtime,
        "evaluate",
        {
            "api_version": "1.0",
            "request_id": "loop:iso3",
            "tenant": "beta",
            "principal": {"subject": "loop", "roles": ["developer"]},
            "context": {"file": "src/shop/order_controller.py", "layer": "controller"},
        },
        token=TOKEN,
    )
    cross_code = (cross.body.get("error") or {}).get("code")
    return Scenario(
        "跨租户隔离：A 的决策与 B 的令牌都不能替对方放行",
        evaluated.status == 200
        and cross_code == "forbidden"
        and forbidden.status == 401,
        f"cross={cross_code} foreign_token={forbidden.status}",
        {"cross": cross_code, "foreign_token": forbidden.status},
    )


def scenario_readiness_fails_without_rules(runtime: Any) -> Scenario:
    """规则目录不可用：readiness 失败，evaluate 得到 rule_set_unavailable。"""

    from policy_api.testing import call

    tenant = runtime.store.get("alpha")
    rules_dir = tenant.rule_dirs[0]
    backup = DEMO_ROOT / "rules-backup"
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    shutil.move(str(rules_dir), str(backup))
    try:
        readiness = runtime.readiness(force=True)
        response = call(
            runtime,
            "evaluate",
            {
                "api_version": "1.0",
                "request_id": "loop:norules",
                "tenant": "alpha",
                "principal": {"subject": "loop", "roles": ["developer"]},
                "context": {"file": "src/shop/order_service.py", "layer": "service"},
            },
            token=TOKEN,
        )
        code = (response.body.get("error") or {}).get("code")
    finally:
        shutil.move(str(backup), str(rules_dir))
        runtime.readiness(force=True)
    return Scenario(
        "规则集不可用时 readiness 失败且 evaluate 失败关闭",
        not readiness.get("ready") and code == "rule_set_unavailable",
        f"ready={readiness.get('ready')} code={code}",
        {"ready": readiness.get("ready"), "code": code},
    )


def scenario_audit_is_anchorable(runtime: Any) -> Scenario:
    """观测日志可锚定：删掉尾部一条记录后，锚校验必须失败。"""

    from policy_api.observability import seal_audit, verify_seal

    log = runtime.request_log
    seal = seal_audit(log)
    clean = verify_seal(log, seal)
    path = log.path
    records = log.read_back()
    tampered = False
    if path is not None and len(records) >= 2:
        text = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(text[:-1]) + "\n", encoding="utf-8", newline="\n")
        issues = verify_seal(log, seal)
        tampered = bool(issues)
    return Scenario(
        "观测日志的摘要链可对外锚定，删尾会被发现",
        not clean and tampered,
        f"records={seal.get('records')} digest={str(seal.get('chain_digest'))[:20]}…",
        {"records": seal.get("records"), "clean_issues": list(clean), "tamper_detected": tampered},
    )


SCENARIOS = (
    scenario_local_and_api_agree,
    scenario_consumers_agree,
    scenario_timeout_is_not_allow,
    scenario_unreachable_api_fails_closed,
    scenario_idempotency,
    scenario_tenant_isolation,
    scenario_readiness_fails_without_rules,
    scenario_audit_is_anchorable,
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 7 Policy API 闭环")
    parser.add_argument("--json", action="store_true", help="只打印结论 JSON")
    args = parser.parse_args(argv)

    from policy_api.testing import build_runtime

    port = free_port()
    config_path = build_config(port)
    runtime = build_runtime(config_path, root=REPO_ROOT)
    readiness = runtime.readiness(force=True)
    server = start_server(runtime, port)
    scenarios: list[Scenario] = []
    try:
        for scenario in SCENARIOS:
            try:
                scenarios.append(scenario(runtime))
            except Exception as error:  # 场景自身崩了也算失败，并写出原因
                import traceback

                scenarios.append(
                    Scenario(
                        scenario.__name__,
                        False,
                        type(error).__name__ + ": " + str(error)[:200],
                        {"traceback": traceback.format_exc(limit=4)},
                    )
                )
    finally:
        server.should_exit = True
        time.sleep(0.2)

    payload = {
        "phase": 7,
        "workspace": DEMO_ROOT.relative_to(REPO_ROOT).as_posix(),
        "endpoint": f"http://{HOST}:{port}",
        "readiness": readiness.get("state"),
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
            print("[" + mark + "] " + item.name + ": " + item.detail)
        print(
            "result: "
            + payload["result"]
            + "  (证据: "
            + RESULT.relative_to(REPO_ROOT).as_posix()
            + ")"
        )
        if payload["result"] != "pass":
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

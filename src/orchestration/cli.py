"""编排层的命令行入口。

    python -m orchestration.cli self-check
    python -m orchestration.cli graph
    python -m orchestration.cli run --task task.json --engine auto
    python -m orchestration.cli status --task-id demo-1

退出码与仓库其它 CLI 一致：0 正常 / 1 检查未通过 / 2 配置或用法错误。
**任何一条路径都不会给"默认 allow"**：平台不可达就是不 reachable，报错退出。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .checkpoint import JsonCheckpointStore
from .client import ApiPolicyClient, ResilientPolicyClient
from .engines import StepExecutor
from .errors import OrchestrationError
from .graph import DEFAULT_SPEC, END
from .models import STATE_SCHEMA_VERSION, GraphState, RunLimits, RunStatus, empty_state
from .nodes import Change, NODES, ScriptedAuthor, TaskSpec
from .runtime import OrchestrationConfig, build_assembly, registry_identity

EXIT_OK = 0
EXIT_UNHEALTHY = 1
EXIT_ERROR = 2

DEFAULT_REGISTRY = Path("registry/tool-registry.yaml")
DEFAULT_APPROVED = Path("registry/tool-registry.approved.json")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_document(path: Path | str) -> Mapping[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("任务文件必须是 JSON 对象")
    return document


def task_from_document(document: Mapping[str, Any]) -> tuple[TaskSpec, ScriptedAuthor]:
    """任务文件 → (TaskSpec, 作者)。作者是**可替换端口**：这里用声明式的脚本作者。"""

    changes = document.get("changes")
    if not isinstance(changes, Sequence) or not changes:
        raise ValueError("任务文件必须声明 changes（本轮允许的候选改动）")
    parsed: list[Change] = []
    for item in changes:
        if not isinstance(item, Mapping):
            raise ValueError("changes 的每一项都必须是对象")
        parsed.append(
            Change(
                path=str(item["path"]),
                summary=str(item.get("summary", "")),
                old=None if item.get("old") is None else str(item["old"]),
                replacement=None if item.get("replacement") is None else str(item["replacement"]),
                content=None if item.get("content") is None else str(item["content"]),
                tokens=int(item.get("tokens", 0) or 0),
                cost_units=int(item.get("cost_units", 0) or 0),
            )
        )
    task = TaskSpec(
        task_id=str(document["task_id"]),
        target=str(document["target"]),
        requirement=str(document.get("requirement", "")),
        layer=str(document.get("layer", "service")),
        language=str(document.get("language", "python")),
        module=None if document.get("module") is None else str(document["module"]),
        query=str(document.get("query", "")),
        principal=dict(
            document.get("principal") or {"subject": "orchestrator", "roles": ["developer"]}
        ),
        acceptance=tuple(str(item) for item in document.get("acceptance", []) or []),
        trace_id=None if document.get("trace_id") is None else str(document["trace_id"]),
    )
    return task, parsed  # type: ignore[return-value]


def build_config(args: argparse.Namespace, document: Mapping[str, Any]) -> OrchestrationConfig:
    repo = _repo_root()
    workspace = Path(args.workspace).resolve() if args.workspace else repo
    default_root = Path(".tmp/phase-8/cli")
    checkpoints = (
        Path(args.checkpoints).resolve() if args.checkpoints else default_root / "checkpoints"
    )
    approvals = (
        Path(args.approvals).resolve() if args.approvals else default_root / "approvals"
    )
    approvals.mkdir(parents=True, exist_ok=True)
    return OrchestrationConfig(
        workspace=workspace,
        checkpoint_dir=checkpoints,
        registry_path=Path(args.registry).resolve() if args.registry else repo / DEFAULT_REGISTRY,
        approved_path=Path(args.approved).resolve() if args.approved else repo / DEFAULT_APPROVED,
        audit_path=Path(args.audit).resolve() if args.audit else checkpoints.parent / "audit.jsonl",
        ledger_path=(
            Path(args.ledger).resolve() if args.ledger else default_root / "ledger.jsonl"
        ),
        approvals_dir=approvals,
        api_base_url=args.api_url,
        api_token=args.token,
        tenant=args.tenant,
        engine=args.engine,
        limits=RunLimits.model_validate(document.get("limits", {}) or {}),
    )


# --------------------------------------------------------------------- 自检


def self_check(args: argparse.Namespace) -> int:
    """装配自检：图、引擎、注册表、checkpoint、状态协议各答一个问题。"""

    checks: list[dict[str, Any]] = []

    problems = DEFAULT_SPEC.problems()
    shape = (
        f"{len(NODES)} 个节点、{len(DEFAULT_SPEC.edges)} 条静态边、"
        f"{len(DEFAULT_SPEC.routers)} 个条件分支"
    )
    checks.append(
        {"check": "graph_spec", "ok": not problems, "detail": "；".join(problems) or shape}
    )

    from .langgraph_engine import langgraph_version

    version = langgraph_version()
    engine_ok = True
    engine_detail = f"langgraph {version}" if version else "未安装 langgraph：auto 会使用参考引擎"
    try:
        executor = StepExecutor(
            node_context=_probe_context(),
            store=None,
            engine_name="self-check",
        )
        from .runtime import select_engine

        engine, name = select_engine("auto", executor=executor)
        engine_detail += f"；auto → {name}"
    except OrchestrationError as error:
        engine_ok = False
        engine_detail = error.detail
    checks.append({"check": "engine", "ok": engine_ok, "detail": engine_detail})

    repo = _repo_root()
    identity = registry_identity(repo / DEFAULT_REGISTRY, repo / DEFAULT_APPROVED)
    registry_detail = (
        f"注册表身份 {identity}" if identity else "注册表或已审核哈希不可用：受控工具无法授权"
    )
    checks.append(
        {"check": "tool_registry", "ok": identity is not None, "detail": registry_detail}
    )

    # 自检的临时目录只用工作区内的 .tmp/：受限沙箱里系统临时目录可能不可写
    # （在那里 mkdtemp 成功、写文件被拒），而"自检失败"必须是真失败，不是环境噪声。
    directory = _repo_root() / ".tmp" / "phase-8" / "cli" / "self-check"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        store = JsonCheckpointStore(directory)
        state = empty_state("self-check", limits=RunLimits())
        record = __import__("orchestration.checkpoint", fromlist=["build_record"]).build_record(
            state, engine="self-check", sequence=1
        )
        store.save(record)
        loaded = store.load("self-check")
        ok = loaded.state_digest == record.state_digest
        detail = "写入 / 读回 / 摘要校验通过" if ok else "checkpoint 读回后摘要不一致"
    except OrchestrationError as error:
        ok = False
        detail = error.detail
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    checks.append({"check": "checkpoint_store", "ok": ok, "detail": detail})

    checks.append(
        {
            "check": "state_protocol",
            "ok": True,
            "detail": f"编排状态协议 {STATE_SCHEMA_VERSION}（决策协议与世代只从核心取值）",
        }
    )

    if args.api_url:
        try:
            client = ResilientPolicyClient(
                ApiPolicyClient(args.api_url, token=args.token or ""), failure_threshold=3
            )
            readiness = client.readiness()
            checks.append(
                {
                    "check": "policy_api",
                    "ok": bool(readiness.ready),
                    "detail": (
                        f"state={readiness.state} rule_set={readiness.rule_set_hash}"
                        f" index={readiness.index_version}"
                    ),
                }
            )
        except OrchestrationError as error:
            checks.append({"check": "policy_api", "ok": False, "detail": error.detail})

    payload = {"checks": checks, "ok": all(item["ok"] for item in checks)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for item in checks:
            print(f"[{'ok' if item['ok'] else 'FAIL'}] {item['check']}: {item['detail']}")
    return EXIT_OK if payload["ok"] else EXIT_UNHEALTHY


def _probe_context():
    """自检用的最小节点上下文：只用于构造执行器，不调用平台。"""

    from .approvals import ApprovalGate
    from .client import ScriptedPolicyClient
    from .nodes import NodeContext
    from .tools import RecordingToolRunner

    return NodeContext(
        task=TaskSpec(
            task_id="self-check", target="README.md", requirement="self-check", layer="docs"
        ),
        client=ScriptedPolicyClient(),
        runner=RecordingToolRunner(),
        author=ScriptedAuthor([]),
        approvals=ApprovalGate(None),
        workspace=Path("."),
    )


# --------------------------------------------------------------------- 图与状态


def graph_command(args: argparse.Namespace) -> int:
    payload = {
        "entry": DEFAULT_SPEC.entry,
        "end": END,
        "nodes": [node.value for node in NODES],
        "edges": [{"source": e.source, "target": e.target} for e in DEFAULT_SPEC.edges],
        "routers": [
            {"name": r.name, "source": r.source, "targets": dict(r.targets)}
            for r in DEFAULT_SPEC.routers
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"入口 {payload['entry']} → 出口 {payload['end']}")
        for edge in payload["edges"]:
            print(f"  {edge['source']} → {edge['target']}")
        for router in payload["routers"]:
            pairs = sorted(router["targets"].items())
            targets = "、".join(f"{label}→{target}" for label, target in pairs)
            print(f"  {router['source']} --[{router['name']}]--> {targets}")
    return EXIT_OK


def status_command(args: argparse.Namespace) -> int:
    store = JsonCheckpointStore(Path(args.checkpoints).resolve())
    if not store.exists(args.task_id):
        print(f"没有找到 {args.task_id} 的 checkpoint", file=sys.stderr)
        return EXIT_UNHEALTHY
    record = store.load(args.task_id)
    state = GraphState.model_validate(dict(record.state))
    payload = {
        "task_id": record.task_id,
        "engine": record.engine,
        "stage": record.stage,
        "revision": record.revision,
        "sequence": record.sequence,
        "status": state.status.value,
        "counters": state.counters.model_dump(mode="json"),
        "failure": None if state.failure is None else state.failure.model_dump(mode="json"),
        "traces": [f"{item.node.value}:{item.decision.value}" for item in state.traces],
        "compatibility": record.compatibility.model_dump(mode="json"),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{payload['task_id']}：{payload['status']}"
            f"（阶段 {payload['stage']}，revision {payload['revision']}）"
        )
        if payload["failure"]:
            print(f"  失败：{payload['failure']['code']} — {payload['failure']['detail']}")
        print("  判定：" + ("、".join(payload["traces"]) or "无"))
    return EXIT_OK


def run_command(args: argparse.Namespace) -> int:
    document = _load_document(args.task)
    task, changes = task_from_document(document)  # type: ignore[misc]
    config = build_config(args, document)
    assembly = build_assembly(config, task=task, author=ScriptedAuthor(changes))
    state = empty_state(
        task.task_id,
        limits=config.limits,
        trace_id=task.trace_id,
        request_id=f"{task.task_id}:request",
    )
    report = assembly.engine.run(task_id=task.task_id, state=state)
    payload = report.to_payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"任务 {report.task_id}：{report.status.value}"
            f"（引擎 {report.engine}，{len(report.steps)} 步）"
        )
        for step in report.steps:
            print(f"  {step.node:<22} {step.label:<6} {step.status}")
        if report.failure is not None:
            print(f"  失败：{report.failure.code.value} — {report.failure.detail}")
    if report.status is RunStatus.COMPLETED:
        return EXIT_OK
    if report.status in (RunStatus.NEEDS_HUMAN, RunStatus.BLOCKED):
        return EXIT_UNHEALTHY
    return EXIT_ERROR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orchestration", description="Phase 8 编排层 CLI")
    # `--json` 在子命令前后都能用：脚本里更常见的写法是放在子命令后面。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="输出机器可读载荷")
    parser.add_argument("--json", action="store_true", help="输出机器可读载荷")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser(
        "self-check", parents=[common], help="装配自检：图 / 引擎 / 注册表 / checkpoint / 状态协议"
    )
    check.add_argument("--api-url", default=None)
    check.add_argument("--token", default=None)
    check.set_defaults(handler=self_check)

    graph = subparsers.add_parser(
        "graph", parents=[common], help="打印图定义（节点 / 边 / 条件分支）"
    )
    graph.set_defaults(handler=graph_command)

    status = subparsers.add_parser("status", parents=[common], help="读 checkpoint 的摘要")
    status.add_argument("--task-id", required=True)
    status.add_argument("--checkpoints", default=".tmp/phase-8/cli/checkpoints")
    status.set_defaults(handler=status_command)

    run = subparsers.add_parser("run", parents=[common], help="按任务文件跑一次工作流（可恢复）")
    run.add_argument("--task", required=True, help="任务 JSON 路径")
    run.add_argument("--engine", default="auto", choices=("auto", "reference", "langgraph"))
    run.add_argument("--workspace", default=None)
    run.add_argument("--checkpoints", default=None)
    run.add_argument("--registry", default=None)
    run.add_argument("--approved", default=None)
    run.add_argument("--audit", default=None)
    run.add_argument("--ledger", default=None)
    run.add_argument("--approvals", default=None)
    run.add_argument("--api-url", default=None)
    run.add_argument("--token", default=None)
    run.add_argument("--tenant", default=None)
    run.set_defaults(handler=run_command)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except OrchestrationError as error:
        print(f"[{error.code.value}] {error.detail}", file=sys.stderr)
        return EXIT_UNHEALTHY
    except (OSError, ValueError, KeyError) as error:
        print(f"配置或用法错误：{type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())

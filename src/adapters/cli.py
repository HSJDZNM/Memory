"""Adapter CLI：支持矩阵、能力声明审核、一致性套件与事件检查。

命令：

    python -m adapters.cli matrix                     # 支持矩阵（数据来自能力声明）
    python -m adapters.cli approve --reviewer <name>  # 审核能力声明（写 approved.json）
    python -m adapters.cli check --json               # 一致性套件（多 Agent 同一套语义）
    python -m adapters.cli check --agent dsh --agent generic-json
    python -m adapters.cli inspect --event event.json --agent generic-json
    python -m adapters.cli wiring [--json] [--check]   # 本机 Agent 通道清点（接线 + 留痕）

退出码：0 = 通过（或环境跳过）；1 = 检查失败（漂移 / 能力不足 / 一致性失败 / 通道未接线）；
2 = 用法或配置错误。
"与 Phase 4 的注册表审核同一条思路"：能力声明是数据，改声明必须重新审核。
"""

from __future__ import annotations

import argparse
import datetime as clock
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from adapters.base import (
    APPROVED_SCHEMA_VERSION,
    DEFAULT_ADAPTERS_ROOT,
    DEFAULT_APPROVED_PATH,
    AdapterRegistry,
    RegistryError,
)
from adapters.conformance import run_conformance
from adapters.json_adapter import agent_response_from_decision
from adapters.loader import (
    load_adapter,
    load_registry_from_repo,
    repo_root,
)
from adapters.models import AdapterManifest, AgentEvent, EnforcementLevel
from adapters.runtime import AgentRuntime
from adapters.wiring import (
    DEFAULT_OBSERVED_SESSIONS,
    DEFAULT_STALE_AFTER_SECONDS,
    WiringError,
    WiringReport,
    probe_wiring,
)
from policy.loader import LoaderError, load_rule_set

__all__ = ["build_parser", "main", "run_approve", "run_check", "run_matrix", "run_wiring"]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

CONFORMANCE_WORKSPACE = "tests/fixtures/agent_events/workspace"


def _utc_now() -> str:
    return clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z")


def _load_rules(root: Path) -> Any:
    return load_rule_set([root / "policies"], repo_root=root)


def _manifest_documents(registry: AdapterRegistry) -> dict[str, AdapterManifest]:
    return {agent_id: registry.manifest(agent_id) for agent_id in registry.manifests}


def run_matrix(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        registry = load_registry_from_repo(root, require_approval=False)
    except RegistryError as error:
        print(f"[adapters] 注册表不可用：{error}", file=sys.stderr)
        return EXIT_USAGE

    listing = registry.as_list()
    payload = {
        "schema_version": listing.approved_schema_version or APPROVED_SCHEMA_VERSION,
        "approved": None if listing.approved_path is None else listing.approved_path,
        "reviewed_by": listing.reviewed_by,
        "approved_at": listing.approved_at,
        "adapters": [item.to_dict() for item in listing.descriptors],
        "counts": {
            "full": len(listing.governed()),
            "read_only": len(listing.read_only()),
            "unsupported": len(listing.unsupported()),
        },
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"adapter support matrix（{len(listing.descriptors)} 个协议消费者）")
        for item in listing.descriptors:
            mark = {"full": "FULL", "read_only": "READ-ONLY", "unsupported": "UNSUPPORTED"}[
                item.enforcement.value
            ]
            print(f"  {item.agent_id:<20} {mark:<12} {item.agent_version:<20} {item.protocol}")
            for reason in item.ceiling_reasons:
                print(f"      - {reason}")
        drifted = [item.agent_id for item in listing.descriptors if not item.approved]
        if drifted:
            print(
                "未审核或已漂移：" + ", ".join(drifted)
                + "（python -m adapters.cli approve --reviewer <name>）",
                file=sys.stderr,
            )
    drifted = [item.agent_id for item in listing.descriptors if not item.approved]
    return EXIT_FAILED if drifted else EXIT_OK


def run_approve(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        registry = load_registry_from_repo(root, require_approval=False)
    except RegistryError as error:
        print(f"[adapters] 注册表不可用：{error}", file=sys.stderr)
        return EXIT_USAGE

    listing = registry.as_list()
    skipped = [
        item.agent_id
        for item in listing.descriptors
        if item.enforcement is EnforcementLevel.UNSUPPORTED
    ]
    if skipped and not args.allow_unsupported:
        print(
            "[adapters] 拒绝审核：以下 Adapter 的能力上限是 unsupported（能力不足）："
            + ", ".join(sorted(skipped))
            + "；先补能力声明，或显式加 --allow-unsupported 把它们记进矩阵（计划 §6）",
            file=sys.stderr,
        )
        return EXIT_USAGE

    target = Path(args.approved) if args.approved else root / DEFAULT_APPROVED_PATH
    payload = {
        "schema_version": APPROVED_SCHEMA_VERSION,
        "reviewed_by": args.reviewer,
        "approved_at": _utc_now(),
        "adapters": {
            item.agent_id: {
                "manifest_digest": item.manifest_digest,
                "agent_version": item.agent_version,
                "protocol": item.protocol,
                "protocol_version": item.protocol_version,
                "fixtures": list(item.fixtures),
                "enforcement": item.enforcement.value,
                "requested_enforcement": (
                    None if item.requested_enforcement is None else item.requested_enforcement.value
                ),
                "ceiling_reasons": list(item.ceiling_reasons),
            }
            for item in listing.descriptors
        },
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    print(
        json.dumps(
            {
                "approved": target.as_posix(),
                "reviewed_by": args.reviewer,
                "adapters": sorted(payload["adapters"]),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return EXIT_OK


def run_check(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    approved = Path(args.approved) if args.approved else root / DEFAULT_APPROVED_PATH
    try:
        registry = AdapterRegistry.load(
            root / DEFAULT_ADAPTERS_ROOT,
            approved_path=approved,
            require_approval=not args.allow_unapproved,
        )
    except RegistryError as error:
        print(f"[adapters] 注册表不可用：{error}", file=sys.stderr)
        return EXIT_USAGE

    listing = registry.as_list()
    selected = list(args.agent or listing.ids)
    unknown = sorted(set(selected) - set(listing.ids))
    if unknown:
        print(f"[adapters] 未知 Agent {unknown}", file=sys.stderr)
        return EXIT_USAGE

    payload: dict[str, Any] = {
        "result": "pass",
        "matrix": {item.agent_id: item.enforcement.value for item in listing.descriptors},
        "selected": selected,
    }
    failures: list[str] = []

    try:
        rules = _load_rules(root)
    except LoaderError as error:
        print(f"[adapters] 规则集不可用：{error}", file=sys.stderr)
        return EXIT_USAGE

    adapters = {}
    for agent_id in selected:
        descriptor = listing.get(agent_id)
        if descriptor.enforcement is EnforcementLevel.UNSUPPORTED:
            failures.append(f"{agent_id}: 能力上限是 unsupported（未审核或能力不足），无法接入")
            continue
        try:
            adapters[agent_id] = load_adapter(agent_id, root=root, registry=registry)
        except RegistryError as error:
            failures.append(f"{agent_id}: {error}")

    # 工作区：默认用仓库内的探针夹具项目，保证"路径越界"测的是真实边界。
    workspace = (
        (root / args.workspace).resolve() if args.workspace else (root / CONFORMANCE_WORKSPACE)
    )
    if not workspace.is_dir():
        print(f"[adapters] 受控工作区不存在：{workspace}", file=sys.stderr)
        return EXIT_USAGE
    # "越界"的基准是**受控工作区的同级路径**，随工作区一起走。
    # 写成"仓库的上一级"会把绝对路径的测试绑死在仓库位置上：工作区换成
    # 别处时，那条"绝对路径越界"反而变成"在受控范围内"，测试静默失效。
    outside = workspace.parent / "outside-workspace.py"

    if adapters:
        # 每次运行都用一份新的台账：一致性套件测的是"这一次的语义等价"，
        # 复用上一轮的记录只会让上一轮的 event_id 把本轮拦成重放。
        # 台账保留在 .tmp/ 下，便于事后解释；它们是构建产物，可随时删除。
        stamp = clock.datetime.now(clock.timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        run_dir = root / ".tmp" / "adapters" / ("run-" + stamp)
        report = run_conformance(
            adapters=adapters,
            rules=rules,
            workspace=workspace,
            outside=outside,
            ledger_dir=run_dir / "ledger",
            trace_path=run_dir / "traces.jsonl",
            breaker_limit=args.breaker_limit,
        )
        payload["ledger_dir"] = (run_dir / "ledger").relative_to(root).as_posix()
        payload["conformance"] = report.summary()
        if not report.ok:
            failures.append(f"一致性套件失败 {len(report.failures)} 项")

        # 契约不变量：Adapter 声明的工具表必须让 Runtime 认得出来
        # （"声明了却无法映射"是静默失效最常见的形态）。
        for agent_id, adapter in sorted(adapters.items()):
            unmapped = [
                name
                for name, spec in adapter.tools.items()
                if spec.direction.value == "outbound" and spec.operation is None
            ]
            if unmapped:
                failures.append(f"{agent_id}: 出站工具没有受控操作 {sorted(unmapped)}")

    payload["failures"] = failures
    payload["result"] = "pass" if not failures else "fail"
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"一致性套件：{payload.get('conformance', {}).get('checks', 0)} 项检查")
        for item in payload.get("conformance", {}).get("failures", []):
            print(f"  FAIL {item['adapter']}/{item['scenario']}/{item['check']}: {item['detail']}")
        for line in failures:
            print(f"  FAIL {line}")
        if not failures:
            print("  pass")
    return EXIT_OK if not failures else EXIT_FAILED


def _inspect_payload(
    adapter: Any, event: AgentEvent, runtime_outcome: Any
) -> Mapping[str, Any]:
    context = None
    try:
        context = adapter.to_policy_context(event, workspace=adapter.workspace)
    except Exception as error:  # noqa: BLE001 - 检查命令要把失败如实打印出来
        context = error
    return {
        "event": {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "agent_id": event.agent_id,
            "tool": event.tool,
            "operation": None if event.operation is None else event.operation.value,
            "payload_digest": event.payload_digest,
            "trace_id": event.trace_id,
            "parent_trace_id": event.parent_trace_id,
        },
        "context": (
            None
            if context is None
            else (
                {"error": str(context)}
                if isinstance(context, Exception)
                else json.loads(context.model_dump_json())
            )
        ),
        "outcome_code": runtime_outcome.outcome_code,
        "response": (
            runtime_outcome.response.model_dump(mode="json")
            if hasattr(runtime_outcome.response, "model_dump")
            else agent_response_from_decision(runtime_outcome.response)
        ),
    }


def run_inspect(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    approved = Path(args.approved) if args.approved else root / DEFAULT_APPROVED_PATH
    try:
        registry = AdapterRegistry.load(
            root / DEFAULT_ADAPTERS_ROOT,
            approved_path=approved,
            require_approval=not args.allow_unapproved,
        )
    except RegistryError as error:
        print(f"[adapters] 注册表不可用：{error}", file=sys.stderr)
        return EXIT_USAGE
    try:
        adapter = load_adapter(args.agent, root=root, registry=registry)
    except RegistryError as error:
        print(f"[adapters] {error}", file=sys.stderr)
        return EXIT_USAGE

    raw = json.loads(Path(args.event).read_text(encoding="utf-8"))
    rules = _load_rules(root)
    runtime = AgentRuntime(
        adapters={adapter.agent_id: adapter}, rules=rules, workspace=adapter.workspace
    )
    try:
        outcome = runtime.handle(adapter.agent_id, raw)
        event = outcome.event
        if event is None:
            payload = {"outcome_code": outcome.outcome_code, "detail": outcome.detail}
        else:
            payload = _inspect_payload(adapter, event, outcome)
    except Exception as error:  # noqa: BLE001
        payload = {"error": f"{type(error).__name__}: {error}"}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return EXIT_OK


def _fixture_path(root: Path, agent_id: str, name: str) -> Path:
    """兼容性 fixture 一律是**仓库相对路径**。

    manifest 的校验也守这一条："事件样本在哪"必须写在声明里，而不是让读取方
    按 Agent id 去猜一个目录（猜错的代价是"样本存在但检查不到"）。
    """

    return root / name.strip()


def run_events(args: argparse.Namespace) -> int:
    """列出每个 Agent 的最小真实事件 fixture（兼容性测试的输入清单）。"""

    root = Path(args.root).resolve()
    approved = Path(args.approved) if args.approved else root / DEFAULT_APPROVED_PATH
    try:
        registry = AdapterRegistry.load(
            root / DEFAULT_ADAPTERS_ROOT,
            approved_path=approved,
            require_approval=not args.allow_unapproved,
        )
    except RegistryError as error:
        print(f"[adapters] 注册表不可用：{error}", file=sys.stderr)
        return EXIT_USAGE
    payload: dict[str, Any] = {}
    missing: list[str] = []
    for item in registry.as_list().descriptors:
        files = {
            name: _fixture_path(root, item.agent_id, name).is_file() for name in item.fixtures
        }
        payload[item.agent_id] = {
            "agent_version": item.agent_version,
            "protocol_version": item.protocol_version,
            "fixtures": files,
        }
        missing.extend(f"{item.agent_id}/{name}" for name, ok in files.items() if not ok)
    payload["missing"] = sorted(missing)
    payload["result"] = "pass" if not missing else "fail"
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return EXIT_OK if not missing else EXIT_FAILED


def _print_wiring(report: WiringReport) -> None:
    """人类可读的通道清点：每个通道一行状态 + 理由，失败项写 stderr。"""

    print(
        "Agent 通道清点：dsh 配置根 = " + report.dsh_home_label
        + "（来源 " + report.dsh_home_source + "）"
    )
    print("  探测状态：" + report.probe_status + "；通道 " + str(len(report.channels)) + " 个")
    for channel in report.channels:
        mark = "WIRED" if channel.ok else channel.status.value
        print("  " + channel.channel_id + "  [" + mark + "]")
        print("      " + channel.detail)
        if channel.audit_path is not None:
            print(
                "      留痕：" + channel.audit_path
                + "（记录 " + str(channel.audit_records) + " 条，最后一条 "
                + str(channel.last_record_at) + "）"
            )
        if channel.bundles:
            print("      bundles：" + ", ".join(channel.bundles))
        for warning in channel.warnings:
            print("      警告：" + warning, file=sys.stderr)
    for note in report.notes:
        print("  说明：" + note)
    tools = report.tools
    print("工具漂移（只报告，本轮不作为阻断项）：")
    print("  声明源：" + tools.declaration_source + "（" + str(len(tools.declared)) + " 项）")
    print("  观察源：" + str(tools.observation_source) + "；" + tools.observation_detail)
    if tools.declaration_error is not None:
        print("  声明读不到：" + tools.declaration_error, file=sys.stderr)
    else:
        print(
            "  运行期出现过但不在表里："
            + (", ".join(tools.observed_not_in_table) if tools.observed_not_in_table else "无")
        )
        print(
            "  表里有但本轮没观察到："
            + (", ".join(tools.table_not_observed) if tools.table_not_observed else "无")
        )
    if report.skipped:
        # 跳过必须可判定：它既不是 pass 也不是 fail，原因与复现命令都写出来。
        print("结果：skipped（环境跳过：本机没有可发现的 Agent 运行时——不是通过）", file=sys.stderr)
        print("  原因：" + str(report.skip_reason), file=sys.stderr)
        print("  复现：" + str(report.reproduce), file=sys.stderr)
        return
    if report.ok:
        print("结果：pass（" + str(len(report.channels)) + " 个通道全部接线且有新鲜留痕）")
        return
    print("结果：fail（未接线 / 无留痕 " + str(len(report.failures)) + " 个通道）", file=sys.stderr)
    for failure in report.failures:
        print("  FAIL " + failure, file=sys.stderr)
    print("加 --check 可以让它成为门禁（退出码 1）", file=sys.stderr)


def run_wiring(args: argparse.Namespace) -> int:
    """通道清点（R2 / G13 / G1）：把「没接线」变成可观测、可失败的显式状态。

    不带 --check 时它是一份报告（退出码 0）；带 --check 时任一通道未接线 / 无留痕即退出 1。
    ``不接线`` 本身不是异常，因此它必须是**状态**，而不是崩溃或者静默通过。
    """

    now = None
    if args.now:
        try:
            now = clock.datetime.fromisoformat(str(args.now).replace("Z", "+00:00"))
        except ValueError:
            print("[adapters] --now 不是 ISO8601 时间：" + str(args.now), file=sys.stderr)
            return EXIT_USAGE
    try:
        report = probe_wiring(
            dsh_home=args.dsh_home,
            project_root=args.project_root,
            stale_after_seconds=args.stale_after,
            observed_sessions=args.observe_sessions,
            now=now,
        )
    except WiringError as error:
        print("[adapters] 通道清点无法进行：" + str(error), file=sys.stderr)
        return EXIT_USAGE

    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_wiring(report)
    if args.require_runtime and report.skipped:
        # 与 tools/dsh_sandbox_loop.py 的 --require-dsh 同一条思路：
        # 这个开关问的是"本机真的有运行时吗"，环境跳过必须能让它变红。
        return EXIT_FAILED
    if args.check and report.result == "fail":
        return EXIT_FAILED
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m adapters.cli",
        description="多 Agent 适配层：支持矩阵、能力声明审核、一致性套件、事件检查与通道清点。",
    )
    parser.add_argument("--root", default=None, help="仓库根目录（默认自动定位）")
    parser.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出"
    )
    parser.add_argument(
        "--approved",
        default=None,
        help=f"已审核清单路径（默认 {DEFAULT_APPROVED_PATH}）",
    )
    parser.add_argument(
        "--allow-unapproved",
        action="store_true",
        help="允许使用未审核的 Adapter（只用于审核前的本地检查，不用于生产接线）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _with_json(parser):
        """子命令也接受 --json：命令行里写在子命令之后是人类最自然的写法。"""

        parser.add_argument(
            "--json",
            action="store_true",
            default=argparse.SUPPRESS,
            help="以 JSON 输出",
        )
        return parser


    _with_json(sub.add_parser("matrix", help="打印支持矩阵")).set_defaults(func=run_matrix)

    approve = sub.add_parser("approve", help="审核能力声明并写入 approved.json")
    approve.add_argument("--reviewer", required=True, help="审核人标识（写进已审核清单）")
    approve.add_argument(
        "--allow-unsupported",
        action="store_true",
        help="允许把能力不足（unsupported）的 Adapter 一并记进矩阵",
    )
    approve.set_defaults(func=run_approve)

    check = _with_json(sub.add_parser("check", help="跑一致性套件"))
    check.add_argument("--agent", action="append", default=None, help="只跑指定 Agent（可重复）")
    check.add_argument("--workspace", default=None, help="受控工作区（默认用仓库内的探针项目）")
    check.add_argument(
        "--breaker-limit",
        type=int,
        default=3,
        help="熔断阈值（默认 3；必须小于循环场景的重复次数）",
    )
    check.set_defaults(func=run_check)

    inspect = _with_json(sub.add_parser("inspect", help="检查一条事件：规范事件、上下文与结论"))
    inspect.add_argument("--agent", required=True)
    inspect.add_argument("--event", required=True, help="事件 JSON 文件")
    inspect.set_defaults(func=run_inspect)

    events = _with_json(sub.add_parser("events", help="列出各 Agent 的最小真实事件 fixture"))
    events.set_defaults(func=run_events)

    wiring = _with_json(
        sub.add_parser("wiring", help="清点本机 Agent 通道：接线状态与留痕状态（未接线即失败）")
    )
    wiring.add_argument(
        "--check",
        action="store_true",
        help="有任一通道未接线 / 无留痕时退出 1（默认只报告，退出 0）",
    )
    wiring.add_argument(
        "--require-runtime",
        action="store_true",
        help="环境跳过（本机没有可发现的 Agent 运行时）也退出 1：跳过不能被读成通过",
    )
    wiring.add_argument(
        "--dsh-home",
        default=None,
        help="dsh 配置根（默认 $DSH_HOME，其次 ~/.dsh 等等价位置）",
    )
    wiring.add_argument(
        "--project-root",
        default=None,
        help="钩子命令里相对路径的解析基准（默认用桥声明的 projectDir，其次 profile 目录）",
    )
    wiring.add_argument(
        "--stale-after",
        type=float,
        default=DEFAULT_STALE_AFTER_SECONDS,
        help=f"留痕陈旧阈值（秒，默认 {DEFAULT_STALE_AFTER_SECONDS} = 7 天）",
    )
    wiring.add_argument(
        "--observe-sessions",
        type=int,
        default=DEFAULT_OBSERVED_SESSIONS,
        help=f"工具漂移最多扫描最近 N 份 dsh 会话记录"
        f"（默认 {DEFAULT_OBSERVED_SESSIONS}；0 = 不观察）",
    )
    wiring.add_argument(
        "--now",
        default=None,
        help="覆盖当前时间（ISO8601，仅用于可复现的报告；不写进输出）",
    )
    wiring.set_defaults(func=run_wiring)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    args = build_parser().parse_args(argv)
    # --json 在父解析器与子解析器上都声明，并且都用 default=argparse.SUPPRESS：
    # 子解析器的默认值会覆盖父级，写 --json check 会被默认值悄悄改回 False。
    # SUPPRESS 让"没给"不写属性、"给了"写 True，两种位置都成立。
    args.json = bool(getattr(args, "json", False))
    args.approved = getattr(args, "approved", None)
    args.allow_unapproved = bool(getattr(args, "allow_unapproved", False))
    args.now = getattr(args, "now", None)
    args.require_runtime = bool(getattr(args, "require_runtime", False))
    args.root = str(Path(args.root).resolve()) if args.root else str(repo_root())
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

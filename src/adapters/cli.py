"""Adapter CLI：支持矩阵、能力声明审核、一致性套件与事件检查。

命令：

    python -m adapters.cli matrix                     # 支持矩阵（数据来自能力声明）
    python -m adapters.cli approve --reviewer <name>  # 审核能力声明（写 approved.json）
    python -m adapters.cli check --json               # 一致性套件（多 Agent 同一套语义）
    python -m adapters.cli check --agent dsh --agent generic-json
    python -m adapters.cli inspect --event event.json --agent generic-json
    python -m adapters.cli wiring [--json] [--check]   # 本机 Agent 通道清点（接线 + 留痕）
    python -m adapters.cli host-version [--json] [--check] [--require-runtime]
                                            # 声明版本 vs 宿主实际版本（活体探测；漂移即红灯）
    python -m adapters.cli host-version --record-check [--json]
                                            # CI 形态：不探测宿主，比对「声明 vs 观测记录」
    python -m adapters.cli host-version --record [--json]
                                            # 唯一写入口：把这次实测写进观测记录

host-version 的四种形态与退出码（README「多 Agent 适配」一节有同口径说明）：

- 报告（默认，不带 --check）：0（只打印，不改退出码）；
- --check（本机活体探测）：0 = match / unavailable / not_declared+read_only；
  1 = drift、recording_stale、能力上限 full 却声明不出读法；加 --require-runtime 时
  unavailable 也 1；2 = 用法错误；
- --record-check（CI 硬门禁，不依赖宿主）：0 = 声明与记录逐条一致；1 = 记录缺失 / 不完整 /
  未知协议版本 / 声明≠记录 / 记录的 manifest 哈希与当前声明不一致 / full 却声明不出读法；
  2 = 用法错误；
- --record（唯一写入口）：0 = 已写入；1 = 拒写（drift / 读不到宿主 / 一个条目都没有）；
  2 = 用法错误。

注意 adapter 这一层有**两条互不代替**的事实轴：manifest 声明「这个 Agent 能做什么」，
host-version 声明「声明写的是哪个产品版本，以及主机上真正装着的是不是同一个」。
两者都不改变 allow / block：版本不一致不是拦截条件。
"与 Phase 4 的注册表审核同一条思路"：能力声明是数据，改声明必须重新审核——
观测记录是这条纪律的延伸：**改了 manifest 就要重跑 --record**，否则 CI 红在"记录过期"上。
"""

from __future__ import annotations

import argparse
import datetime as clock
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from adapters.base import (
    APPROVED_SCHEMA_VERSION,
    DEFAULT_ADAPTERS_ROOT,
    DEFAULT_APPROVED_PATH,
    AdapterRegistry,
    RegistryError,
)
from adapters.conformance import run_conformance
from adapters.host_version import (
    DEFAULT_OBSERVED_PATH,
    DEFAULT_PROBE_TIMEOUT_MS,
    READING_GUIDE as HOST_VERSION_READING_GUIDE,
    HostVersionError,
    HostVersionRecordError,
    HostVersionReport,
    ObservedHostVersions,
    build_observed_record,
    check_declared_versions,
    check_recorded_versions,
    load_observed_record,
    record_failure_report,
    record_refusal_report,
    write_observed_record,
)
from adapters.json_adapter import agent_response_from_decision
from adapters.loader import (
    load_adapter,
    load_registry_from_repo,
    repo_root,
)
from adapters.models import AgentEvent, EnforcementLevel
from adapters.runtime import AgentRuntime
from adapters.wiring import (
    DEFAULT_OBSERVED_SESSIONS,
    DEFAULT_STALE_AFTER_SECONDS,
    READING_GUIDE,
    WIRING_SCOPE_RELATIVE,
    WiringError,
    WiringReport,
    build_reading_context,
    load_declared_scope,
    probe_wiring,
)
from policy.loader import LoaderError, load_rule_set

__all__ = [
    "build_parser",
    "main",
    "run_approve",
    "run_check",
    "run_host_version",
    "run_matrix",
    "run_wiring",
]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

CONFORMANCE_WORKSPACE = "tests/fixtures/agent_events/workspace"


def _utc_now() -> str:
    return clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z")


def _load_rules(root: Path) -> Any:
    return load_rule_set([root / "policies"], repo_root=root)


def run_matrix(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    # 其余子命令（approve / check / inspect / events / host-version）都按 --approved 走，
    # 只有 matrix 走 load_registry_from_repo——它固定读 DEFAULT_APPROVED_PATH。静默忽略
    # 用户显式给的清单正是本模块反对的形态（"我明明指定了"变成空操作），所以这里显式拒绝。
    if Path(args.approved).resolve() != Path(DEFAULT_APPROVED_PATH).resolve():
        print(
            "[adapters] matrix 不支持 --approved：本子命令固定读 "
            f"{DEFAULT_APPROVED_PATH}；approve / check / inspect / events / host-version "
            "才按 --approved 走",
            file=sys.stderr,
        )
        return EXIT_USAGE
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

    # 与 run_check 同一口径：读事件、解析 JSON、加载规则集都是**输入**，读不到时给
    # 「[adapters] 消息 + 退出码 2」，不许把 FileNotFoundError / JSONDecodeError /
    # LoaderError 打成原始 traceback。
    try:
        raw = json.loads(Path(args.event).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"[adapters] 事件文件不可读：{error}", file=sys.stderr)
        return EXIT_USAGE
    try:
        rules = _load_rules(root)
    except LoaderError as error:
        print(f"[adapters] 规则集不可用：{error}", file=sys.stderr)
        return EXIT_USAGE
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
    """人类可读的通道清点：每个通道先给**两根各自独立的事实轴**，再给理由，失败项写 stderr。

    N20：以前只有一行 `[WIRED]`/"audit_never_written"，读者没法区分"接线在、但没有留痕"
    与"接线根本不在"。现在接线事实与留痕事实分行打印，谁坏了就写在谁那一行。
    """

    print(
        "Agent 通道清点：dsh 配置根 = " + report.dsh_home_label
        + "（来源 " + report.dsh_home_source + "）"
    )
    print("  探测状态：" + report.probe_status + "；通道 " + str(len(report.channels)) + " 个")
    # 口径写在最前面：一次 WIRED 是"此刻两根轴都成立"的快照，不是治理已开启的长期证据。
    print("  口径：" + READING_GUIDE)
    total = len(report.channels)
    wiring_ok = sum(1 for channel in report.channels if channel.wiring_status.is_wired)
    freshness_ok = sum(1 for channel in report.channels if channel.freshness_status.is_fresh)
    print(
        "  事实合计：接线成立 " + str(wiring_ok) + "/" + str(total)
        + "；留痕新鲜 " + str(freshness_ok) + "/" + str(total)
    )
    # 台阶 4（1.3）：覆盖账的两行——只**加行**，上面既有行一个字符不动。
    # 机器行与 tools/exemption_expiry.py 的 HITS: 同型（跨文件契约：只加行、不改既有行）。
    coverage = report.coverage()
    print("  " + coverage["headline"]["text"])
    print("  " + coverage["headline"]["machine_line"])
    if coverage["differences"]["status"] != "available":
        print("      差集不可用（不是 0）：" + str(coverage["differences"]["reason"]), file=sys.stderr)
    for channel in report.channels:
        mark = "WIRED" if channel.ok else channel.status.value
        print("  " + channel.channel_id + "  [" + mark + "]")
        print("      接线事实：" + channel.wiring_status.value)
        print("      留痕事实：" + channel.freshness_status.value)
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
    # 台阶 4（1.3）：声明侧读数——边界声明由**调用方**读好交给报告；读不到就是显式三态
    # （unavailable + reason），不让整份报告写不出来，也不把“读不到”折成 0。
    declared_scope = load_declared_scope(Path(args.root) / WIRING_SCOPE_RELATIVE)
    try:
        report = probe_wiring(
            dsh_home=args.dsh_home,
            project_root=args.project_root,
            stale_after_seconds=args.stale_after,
            observed_sessions=args.observe_sessions,
            now=now,
            declared_scope=declared_scope,
        )
    except WiringError as error:
        print("[adapters] 通道清点无法进行：" + str(error), file=sys.stderr)
        return EXIT_USAGE

    payload = report.to_dict()
    if args.json:
        # 台阶 4（21 号 §2.5）：旁注——这份读数属于哪棵树、读的是哪一份边界声明、哪台宿主。
        # 它**只进 --json**，且不改任何通道状态 / result / failures / 退出码（--check 的判据
        # 一个字段都不读它）。树摘要要遍历仓库（有声明好的排除项），因此不做无谓的旁路计算。
        payload["reading_context"] = build_reading_context(root=Path(args.root))
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


def _parse_probe_binaries(
    values: Optional[Sequence[str]], known: set[str]
) -> tuple[dict[str, str], Optional[str]]:
    """解析 --probe-binary AGENT=PATH；返回 (覆盖表, 错误理由)。

    指向未知 Agent 一律是用法错误：静默忽略会让"我明明指定了"变成空操作。
    """

    overrides: dict[str, str] = {}
    for raw in values or ():
        token = str(raw)
        agent_id, separator, path = token.partition("=")
        agent_id = agent_id.strip()
        path = path.strip()
        if not separator:
            return {}, f"--probe-binary 必须是 AGENT=PATH 形态，得到 {token!r}"
        if not agent_id or not path:
            return {}, f"--probe-binary 的 AGENT 与 PATH 都不能为空，得到 {token!r}"
        if agent_id not in known:
            return {}, (
                f"--probe-binary 指向注册表里没有的 Agent {agent_id!r}："
                f"可用的有 {sorted(known)}"
            )
        overrides[agent_id] = path
    return overrides, None


def _print_host_version(report: HostVersionReport) -> None:
    """人类可读的比对结果：每条先给状态，再给声明 / 宿主 / 记录；失败项写 stderr。"""

    if report.mode == "record":
        header = (
            "声明版本 vs 提交进仓库的观测记录（CI 形态：不探测宿主；记录 "
            + str(report.record_path)
            + "，记录于 " + str(report.record_recorded_at) + "）"
        )
    else:
        header = "声明版本 vs 宿主实际版本（活体探测；口径：" + HOST_VERSION_READING_GUIDE + "）"
    print(header)
    for item in report.findings:
        print("  " + item.agent_id + "  [" + item.status.value + "]")
        if item.status.value in ("match", "drift") and item.observed_version is not None:
            relation = "=" if item.status.value == "match" else "不等于"
            source = "记录里的实测值" if item.source == "record" else "宿主"
            origin = (
                "" if item.recorded_at is None
                else "（记录于 " + str(item.recorded_at) + "）"
            )
            print(
                "      声明 " + item.declared_version + " " + relation + " " + source + " "
                + str(item.observed_version) + origin
            )
        elif item.status.value == "not_declared":
            print("      未声明 host_version；能力上限 " + item.enforcement)
        elif item.status.value == "unavailable":
            print(
                "      读不到宿主版本（探测 " + str(item.probe) + "，能力上限 "
                + item.enforcement + "）"
            )
        print("      " + item.detail)
    counts = report.to_dict()["counts"]
    print(
        "  合计：实际比对 " + str(report.covered) + "/" + str(report.total)
        + "；match " + str(counts["match"]) + "，drift " + str(counts["drift"])
        + "，recording_stale " + str(counts["recording_stale"])
        + "，unavailable " + str(counts["unavailable"])
        + "，not_declared " + str(counts["not_declared"])
    )
    for note in report.notes:
        print("  说明：" + note)
    if report.result == "record_refused":
        print(
            "结果：record_refused（拒绝写入观测记录——记录只装「已核对过」的证据）",
            file=sys.stderr,
        )
        for failure in report.failures:
            print("  FAIL " + failure, file=sys.stderr)
        return
    if report.result in ("record_missing", "record_invalid"):
        print(
            "结果：" + report.result
            + "（记录缺失 / 不完整：有门禁就必须有数据——它不是通过，也不是跳过）",
            file=sys.stderr,
        )
        for failure in report.failures:
            print("  FAIL " + failure, file=sys.stderr)
        return
    if report.result == "fail":
        print("结果：fail（" + str(len(report.failures)) + " 项）", file=sys.stderr)
        for failure in report.failures:
            print("  FAIL " + failure, file=sys.stderr)
        return
    if report.result == "unavailable":
        print(
            "结果：unavailable（声明了探测但这次读不到宿主版本——它不是通过）",
            file=sys.stderr,
        )
        print("加 --require-runtime 可以让它成为门禁（退出码 1）", file=sys.stderr)
        return
    if report.mode == "record":
        print(
            "结果：pass（实际比对 " + str(report.covered) + "/" + str(report.total)
            + "：声明与观测记录一致，且不依赖宿主）"
        )
        return
    print(
        "结果：pass（实际比对 " + str(report.covered) + "/" + str(report.total)
        + "：声明与宿主一致）"
    )


def _print_record_written(record: ObservedHostVersions, label: str) -> None:
    """写记录是人类动作（也是一次评审请求），输出必须自证写了什么、什么时候、按什么读法。"""

    print(
        "观测记录已写入 " + label + "（" + str(len(record.entries)) + " 条，记录于 "
        + record.recorded_at + "）："
    )
    for entry in record.entries:
        print(
            "  " + entry.agent_id + "  observed " + entry.observed_version
            + "  读法 " + entry.probe_text
        )
        print("      manifest " + entry.manifest_digest)
    print(
        "口径：记录只能由 --record 写入；CI 用 host-version --record-check 比对「声明 vs 记录」，"
        "它不探测宿主。"
    )
    print("改了 adapters/<agent>/manifest.yaml 必须重跑 --record，否则 CI 会红在「记录过期」上。")


def _record_label(path: Path, root: Path) -> str:
    """记录文件在报告里的名字：**仓库相对路径**（报告里绝不出现本机绝对路径）。"""

    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def run_host_version(args: argparse.Namespace) -> int:
    """声明版本 vs 宿主实际版本（R14）与观测记录（修复轮 15：Q8 的尾巴）。

    为什么必须存在：manifest 的 agent_version 说明写着「已实测的产品版本」，但在修复轮 14
    之前没有任何地方把它与宿主实际版本比过——宿主升级后声明仍旧，而一致性套件、
    事件 fixture 重放与支持矩阵全部照常通过。那是一条**静默漂移**。

    为什么它不是拦截判定：版本不一致不改变任何 allow / block（AGENTS.md 第 24 / 29 条
    管的是能力上限）。把它做成放行条件，会让「宿主升级」直接封成「平台不可用」。

    修复轮 15 补上的是**后半个问题**：活体探测在没有宿主的 CI 上读不到版本 → unavailable
    → 退出 0，于是"检查修好了，却没有任何地方会为它红"。所以这里多两条路径：

    - --record-check（CI 形态，不依赖宿主）：比对「声明 vs 提交进仓库的观测记录」并且校验
      记录钉住的 manifest 哈希；记录缺失 / 不完整 / 不一致一律退出 1；
    - --record（唯一写入口）：把这次实测固化成记录。只在全部 match、且至少有一条时写入——
      drift / 读不到 / 空记录都拒写（半份记录看起来像证据，比没有更坏）。

    本机形态 --check 的四状态语义一个字不放宽，只新增第五种 recording_stale（记录过期）。
    """

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

    timeout_ms = int(getattr(args, "timeout_ms", DEFAULT_PROBE_TIMEOUT_MS))
    if timeout_ms <= 0:
        print("[adapters] --timeout-ms 必须是正整数", file=sys.stderr)
        return EXIT_USAGE

    listing = registry.as_list()
    manifests = {
        item.agent_id: registry.manifest(item.agent_id) for item in listing.descriptors
    }
    enforcement_by_agent = {
        item.agent_id: item.enforcement.value for item in listing.descriptors
    }

    record_mode = bool(getattr(args, "record_check", False))
    write_mode = bool(getattr(args, "record", False))
    if record_mode and write_mode:
        print(
            "[adapters] 拒绝：--record 写记录、--record-check 只读记录做比对，两者不能同时使用",
            file=sys.stderr,
        )
        return EXIT_USAGE
    host_only_flags = (
        ("--probe-binary", "probe_binary"),
        ("--require-runtime", "require_runtime"),
    )
    for flag, attribute in host_only_flags:
        if record_mode and getattr(args, attribute, None):
            print(
                f"[adapters] 拒绝：--record-check 不探测宿主，{flag} 在这里没有意义"
                "（CI 形态读的是提交进仓库的记录）；静默忽略它会把「我明明指定了」变成空操作",
                file=sys.stderr,
            )
            return EXIT_USAGE

    overrides, failure = _parse_probe_binaries(
        getattr(args, "probe_binary", None), set(listing.ids)
    )
    if failure is not None:
        print(f"[adapters] {failure}", file=sys.stderr)
        return EXIT_USAGE

    record_path = (
        Path(args.record_path)
        if getattr(args, "record_path", None)
        else root / DEFAULT_OBSERVED_PATH
    )
    label = _record_label(record_path, root)

    if write_mode:
        # 写入前先做一次完整的活体比对：记录只装「已核对过」的证据。
        report = check_declared_versions(
            manifests,
            enforcement_by_agent=enforcement_by_agent,
            overrides=overrides,
            timeout_ms=timeout_ms,
        )
        try:
            record = build_observed_record(manifests, report, recorded_at=_utc_now())
        except HostVersionError as error:
            refused = record_refusal_report(report, error)
            if args.json:
                print(json.dumps(refused.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
            else:
                _print_host_version(refused)
            print(f"[adapters] 拒绝写入观测记录：{error}", file=sys.stderr)
            return EXIT_FAILED
        try:
            write_observed_record(record, record_path)
        except HostVersionError as error:
            print(f"[adapters] {error}", file=sys.stderr)
            return EXIT_FAILED
        if args.json:
            payload = {"result": "pass", "mode": "record-write", "record_path": label}
            payload.update(record.to_dict())
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_record_written(record, label)
        return EXIT_OK

    if record_mode:
        try:
            record = load_observed_record(record_path, label=label)
        except HostVersionRecordError as error:
            report = record_failure_report(error, record_label=label)
        else:
            report = check_recorded_versions(
                manifests,
                enforcement_by_agent=enforcement_by_agent,
                record=record,
                record_label=label,
            )
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_host_version(report)
        # 记录形态是硬门禁：pass 之外的每一种结果（缺记录 / 记录不完整 / 声明≠记录）都退出 1。
        return EXIT_OK if report.result == "pass" else EXIT_FAILED

    record = None
    record_error = None
    try:
        record = load_observed_record(record_path, label=label)
    except HostVersionRecordError as error:
        # 记录缺失 / 读不了不改变活体四状态语义：它只写进 notes，并指向 CI 形态。
        record_error = str(error)

    report = check_declared_versions(
        manifests,
        enforcement_by_agent=enforcement_by_agent,
        overrides=overrides,
        timeout_ms=timeout_ms,
        record=record,
        record_label=label,
        record_error=record_error,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_host_version(report)

    if getattr(args, "require_runtime", False) and report.result == "unavailable":
        # 与 tools/dsh_sandbox_loop.py 的 --require-dsh 同一条思路：这个开关问的是
        # "本机真的有可探测的宿主运行时吗"，环境跳过必须能让它变红。
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

    host_version = _with_json(
        sub.add_parser(
            "host-version",
            help="比对声明版本与宿主实际版本（漂移即失败；它不是拦截判定）",
        )
    )
    host_version.add_argument(
        "--check",
        action="store_true",
        help="出现 drift / recording_stale（或能力上限 full 却没声明 host_version）时退出 1"
        "（默认只报告）",
    )
    host_version.add_argument(
        "--record",
        action="store_true",
        help="把这次实测的宿主版本写进观测记录（唯一写入口；只在全部 match 且至少一条时写入，"
        "否则拒写并退出 1）",
    )
    host_version.add_argument(
        "--record-check",
        action="store_true",
        help="CI 形态：不探测宿主，比对「声明 vs 观测记录 + 记录里的 manifest 哈希」；"
        "记录缺失 / 不完整 / 未知协议版本 / 声明不一致一律退出 1",
    )
    host_version.add_argument(
        "--record-path",
        default=None,
        metavar="PATH",
        help=f"观测记录路径（默认 {DEFAULT_OBSERVED_PATH}）",
    )
    host_version.add_argument(
        "--require-runtime",
        action="store_true",
        help="读不到宿主版本（二进制不在 / 非零退出 / 输出解析不出 / 超时）也退出 1："
        "环境跳过不能被读成通过",
    )
    host_version.add_argument(
        "--probe-binary",
        action="append",
        default=None,
        metavar="AGENT=PATH",
        help="用指定的可执行文件替换该 Agent 声明里的裸命令名（可重复；只影响这一次探测，"
        "不改变声明本身）",
    )
    host_version.add_argument(
        "--timeout-ms",
        type=int,
        default=DEFAULT_PROBE_TIMEOUT_MS,
        help=f"单次探测超时（毫秒，默认 {DEFAULT_PROBE_TIMEOUT_MS}）",
    )
    host_version.set_defaults(func=run_host_version)
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
    args.record = bool(getattr(args, "record", False))
    args.record_check = bool(getattr(args, "record_check", False))
    args.record_path = getattr(args, "record_path", None)
    args.root = str(Path(args.root).resolve()) if args.root else str(repo_root())
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

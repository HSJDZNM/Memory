"""policy.check：命令行入口。

用法:

    python -m policy.check examples/bad_controller.py --layer controller
    python -m policy.check examples/good_controller.py --layer controller
    python -m policy.check --check-rules

Phase 5 起默认走**验证器流水线**：先由 AST / 依赖图 / 外部工具产生确定性证据，再交给引擎判定。
依赖因此不再需要调用方声明；--dependencies 仍然可用，含义是“显式声明依赖、不用 AST 证据”。

退出码：

    0 = 通过（ALLOW）
    1 = 发现违规（BLOCK / ALLOW_WITH_WARNINGS，含需要人工审批的 block）
    2 = 配置或执行错误（规则目录不可读、规则损坏、路径不合法、上下文不完整、未知 checker、
        验证器注册表不可用，以及"声明了 --changed 却没有 --operation"这种自相矛盾调用）

CLI 输出面向人（--json 时输出面向机器），Engine 结果始终保持结构化。
--json 的顶层是 CLI 包装（output_schema_version / context / rule_set / reported_imports /
evidence / exit_code / layer_source / check_volume），其中 result 就是完整的 PolicyDecision
协议载荷，可被 policy.parse_decision 直接消费；evidence 是本次验证器运行的完整事实
（验证器状态、工具版本与配置哈希、依赖、发现、阻断点）。

**包装层也有自己的协议版本**（2026-09-30 裁定）：output_schema_version 只描述**外层包装**的形状，
与决策协议（policy.models.SCHEMA_VERSION）各自演进、谁也不跟随谁。1.0 是**追认**的
——它指"台阶 3c 之前的形状"（那时 check_volume 里还没有 obligations_open / obligations_note
两个键，见台阶 3c 记录 §2.5）；当前形状记为 1.1。给包装加键 / 改语义都要按 AGENTS 第 55 条
递增这个版本，因为消费方（脚本、门禁、手册）按它读键集合。

两个**只增不改**的读数（07 号报告 P4 / P5）：

- layer_source 说明 layer 是**从哪来的**（declared / platform_test_layout / filename_guess）。
  缺 --layer 时先查平台数据 validation/test-layout.yaml 的 test_patterns，命中即 layer=test；
  没命中才按文件名推断。受治理 Hook 路径与验证器路径因此共用同一份"哪些路径算测试"的声明，
  不再对同一个文件给出相反结论。
- check_volume 把"这次到底查了多少"写成结构化摘要：跳过不等于通过；缺维度（调用方没说
  operation 之类的维度）会让 complete=false——这个 allow 比完整判定弱。
  完全没给 --operation 的既有命令仍可执行（README 与文档里的 60+ 处命令依赖它），
  只有"给了 --changed 却没给 --operation"这种自相矛盾的调用才失败关闭（退出码 2）。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

# 验证器层的配置错误类型。core（models/engine/context/scope/loader）不导入 Adapter，
# 只有 CLI（应用层）在这里装配验证器流水线；tests/contract 里有守住这条边界的用例。
# 平台测试路径声明（validation/test-layout.yaml）也由验证器层的 loader 读取，
# 保证 test_patterns 只有一份解释权。
from validators.registry import RegistryError as ValidatorConfigError  # noqa: E402
from validators.registry import load_test_layout  # noqa: E402

from .context import build_context, normalize_context, repo_relative_path
from .engine import EngineError, evaluate
from .loader import LoaderError, load_rule_set
from .models import (
    BLOCKING_SEVERITIES,
    KNOWN_SCOPE_DIMENSIONS,
    SCHEMA_VERSION,
    Decision,
    Operation,
    PolicyContext,
    PolicyContextError,
    RuleSet,
    ValidationResult,
    Violation,
    canonical_identifier,
)
from .obligations import ObligationsError
from .scope import match_scope

__all__ = [
    "CHECK_VOLUME_NOTE",
    "EXIT_ALLOWED",
    "EXIT_ERROR",
    "EXIT_VIOLATION",
    "LAYER_SOURCE_DECLARED",
    "LAYER_SOURCE_FILENAME_GUESS",
    "LAYER_SOURCE_PLATFORM_TEST_LAYOUT",
    "OUTPUT_SCHEMA_VERSION",
    "SKIP_REASON_EVIDENCE_NOT_COLLECTED",
    "SKIP_REASON_MISSING_DIMENSION",
    "SKIP_REASON_SCOPE_MISMATCH",
    "build_check_volume",
    "build_parser",
    "context_payload",
    "default_rule_dirs",
    "exit_code_for",
    "infer_layer",
    "load_platform_test_layout",
    "main",
    "parse_dependencies",
    "python_imports",
    "render_check_volume",
    "render_json",
    "render_text",
    "repo_root",
    "resolve_layer",
    "run",
]

EXIT_ALLOWED = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2

# --json **外层包装**自己的协议版本（它不等于决策协议版本，也不跟随平台阶段）。
# 1.0 是追认的形状：台阶 3c 给 check_volume 加了 obligations_open / obligations_note 两个键
# （J1(c)），按 AGENTS 第 55 条"加键就是改协议"本应同批递增，当时只在记录里写了理由
# （台阶 3c 记录 §2.5：把它当 CLI 包装、不是跨进程协议载荷）而没有版本号。2026-09-30 的裁定
# 把这件事定下来：**1.0 = 台阶 3c 之前的形状，当前形状 = 1.1**，并登记进 AGENTS 第 55 条。
# 消费方（脚本 / 门禁 / 学习手册）按它判断"外层键集合是哪一版"；决策载荷仍是 result 里的
# SCHEMA_VERSION，两者互不代替。
OUTPUT_SCHEMA_VERSION = "1.1"

DEFAULT_RULE_DIRS = ("policies",)

KNOWN_LAYERS = (
    "controller",
    "service",
    "repository",
    "model",
    "schema",
    "view",
    "client",
    "adapter",
    "gateway",
    "middleware",
    "util",
    "test",
)

UNKNOWN_LAYER = "unknown"


def repo_root() -> Path:
    """仓库根目录：从本模块位置向上回溯到含 policies/ 或 .git 的目录。"""

    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "policies").is_dir() or (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def default_rule_dirs(root: Path | None = None) -> tuple[Path, ...]:
    anchor = root if root is not None else repo_root()
    return tuple(anchor / name for name in DEFAULT_RULE_DIRS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m policy.check",
        description="对固定上下文运行机器可执行规则，输出 allow / allow_with_warnings / block。",
    )
    parser.add_argument("file", nargs="?", help="待检查的文件（仓库相对路径或绝对路径）")
    parser.add_argument(
        "--rules",
        action="append",
        default=None,
        metavar="DIR",
        help="规则目录，可重复；默认 policies/",
    )
    parser.add_argument(
        "--dependencies",
        default=None,
        metavar="A,B",
        help="逗号分隔的直接依赖：显式声明并覆盖 AST / 依赖图证据（留空 = 声明没有依赖）",
    )
    parser.add_argument(
        "--layer",
        default=None,
        help="架构层（安全关键维度，用于 scope 匹配）；不提供时按文件名推断并标注",
    )
    parser.add_argument(
        "--language",
        default="python",
        help="上下文语言；默认 python。传空字符串表示语言未知，语言相关的规则会被跳过",
    )
    parser.add_argument(
        "--module",
        default=None,
        help="模块名。刻意不从文件路径推断：猜错模块会让规则在错误的范围上生效",
    )
    parser.add_argument("--project", default=None, help="上下文项目名")
    parser.add_argument("--agent", default=None, help="产生该请求的 Agent 标识")
    parser.add_argument("--task", default=None, help="任务描述（只记录，不参与匹配）")
    parser.add_argument("--request-id", default=None, help="覆盖自动生成的 request_id")
    parser.add_argument(
        "--trace-id",
        default=None,
        help="跨检索、决策、执行、验证的 trace 标识；不提供时留空，不伪造",
    )
    parser.add_argument(
        "--operation",
        default=None,
        choices=[item.value for item in Operation],
        help="被治理的操作类型（受控枚举）",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="被验证项目的工作区根目录；默认仓库根（依赖图按它解析项目内模块）",
    )
    parser.add_argument(
        "--config-root",
        default=None,
        help="validation/ 配置所在目录；默认仓库根",
    )
    parser.add_argument(
        "--changed",
        action="append",
        default=None,
        metavar="FILE",
        help="本次变更集里的文件（可重复）；测试验证器需要它，缺失属于证据不足",
    )
    parser.add_argument(
        "--validators",
        default=None,
        metavar="A,B",
        help="只运行这些验证器（allowlist）；没跑的 checker 会失败关闭",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    parser.add_argument(
        "--check-rules",
        action="store_true",
        help="只校验规则集（不检查文件）；损坏时退出码 2",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="保留本次运行的临时目录（默认用完即删，目录在 .tmp/validators 下）",
    )
    parser.add_argument(
        "--obligations",
        default=None,
        metavar="PATH",
        help=(
            "义务账本（JSONL）：本次判定里的「待实现」记进去、流水线里真实跑成的 pytest 运行"
            "记进去并解除对应义务；check_volume 会据此给出 obligations_open。"
            "不给这一项 = 不记账（不是「没有义务」）"
        ),
    )
    return parser


def infer_layer(file: str | None) -> str:
    """按文件名推断架构层；推断不出来就是 unknown，不猜测、不默认。

    这是 CLI 的便利功能，不属于核心规范化器：Adapter 必须显式提供 layer。
    """

    if not file:
        return UNKNOWN_LAYER
    stem = Path(file).stem.lower()
    for layer in KNOWN_LAYERS:
        if layer in stem:
            return layer
    return UNKNOWN_LAYER


# 分层的三个来源。写进 --json 顶层与文本输出：读者必须能分清"层是声明的"、
# "层来自平台数据"还是"层是按文件名猜的"——三者混在一起就回到了 P4 的旧问题。
LAYER_SOURCE_DECLARED = "declared"
LAYER_SOURCE_PLATFORM_TEST_LAYOUT = "platform_test_layout"
LAYER_SOURCE_FILENAME_GUESS = "filename_guess"

# 平台数据判定为测试路径时使用的层名。它必须与 dsh 示例配置的 test_layer 一致，
# 但那不是靠约定，而是由 tests/contract/test_dsh_layer_declaration.py 钉住。
PLATFORM_TEST_LAYER = "test"

# 文本输出里"这个层是怎么来的"：按来源说口径。平台数据判定时不许再说"推断"——
# 那是猜的层与查出来的层的区别，两者给出相反结论时读数的人得看得出来。
LAYER_SOURCE_NOTES: dict[str, str] = {
    LAYER_SOURCE_PLATFORM_TEST_LAYOUT: (
        "  （命中平台测试路径声明 validation/test-layout.yaml 的 test_patterns，"
        "未显式声明 --layer）"
    ),
    LAYER_SOURCE_FILENAME_GUESS: "  （由文件名推断，未显式声明）",
}


def load_platform_test_layout(args: argparse.Namespace, *, root: Path) -> Any:
    """读取平台级"哪些路径算测试"的声明（validation/test-layout.yaml）。

    刻意复用验证器层的 loader（`validators.registry.load_test_layout`）：test_patterns
    的解释权只有一份。自己再写一个 YAML 解析器就等于第二套口径，而 P4 的成因正是两套口径
    ——平台数据说是测试、文件名推断说是生产层，同一个文件于是拿到相反结论。

    --config-root 的解析与 collect_evidence 完全同源（锚是**仓库根**，不是 --workspace）：
    配置在哪与目标文件属于哪个工作区是两件事，混用一个锚会让"带 --workspace 跑一次"变成
    "读不到配置"（退出码 2）。
    """

    config_root = resolve_directory(args.config_root, anchor=root, fallback=root)
    return load_test_layout(root=config_root)


def resolve_layer(
    args: argparse.Namespace, *, anchor: Path, root: Path, file_path: Path
) -> tuple[str, str]:
    """定层与来源（唯一口径）：declared → platform_test_layout → filename_guess。

    - 显式给了 --layer：就是它，来源 declared；
    - 否则命中平台数据 test_patterns：layer=test，来源 platform_test_layout；
    - 否则维持按文件名推断，来源 filename_guess（推断不出来就是 unknown，不默认）。

    anchor 是**工作区**（--workspace），用它算相对路径：命中判定必须发生在上下文里那个
    路径上，否则"带工作区前缀"的写法会让两条路径匹配不同的字符串。
    root 是**仓库根**，用它定位 validation/ 配置（与 collect_evidence 同源）。

    平台数据读不到时抛 RegistryError，由 run() 按配置错误处理（退出码 2）——
    与"验证器注册表不可用"同一口径：配置读不到时既不猜也不放行。
    """

    if args.layer:
        return canonical_identifier(args.layer), LAYER_SOURCE_DECLARED
    # 与 build_context 用同一个规范化器：判定与匹配必须基于同一个字符串。
    relative = repo_relative_path(str(file_path), repo_root=anchor)
    layout = load_platform_test_layout(args, root=root)
    if layout.is_test(relative):
        return PLATFORM_TEST_LAYER, LAYER_SOURCE_PLATFORM_TEST_LAYOUT
    return infer_layer(args.file), LAYER_SOURCE_FILENAME_GUESS


def parse_dependencies(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    items = [canonical_identifier(item) for item in raw.split(",")]
    return tuple(sorted({item for item in items if item}))


def python_imports(source: str) -> tuple[str, ...]:
    """只用于报告，不参与判定：解析 Python 源码的 import 顶层模块名。"""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return tuple(sorted(modules))


def resolve_directory(value: str | None, *, anchor: Path, fallback: Path) -> Path:
    """把目录参数解析成绝对路径：先按当前工作目录，再按仓库根，最后原样返回。

    为什么需要它：CLI 可能从仓库根、也可能从 docs/project/learning/phase-5 这样的子目录启动
    （学习手册就是从两个工作目录各跑一遍的）。同一个相对参数必须在两处指向同一个目录。
    """

    if not value:
        return fallback
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    if candidate.is_dir():
        return candidate.resolve()
    from_anchor = anchor / candidate
    if from_anchor.is_dir():
        return from_anchor.resolve()
    return candidate.resolve()


def resolve_workspace(args: argparse.Namespace, root: Path) -> Path:
    """解析 --workspace：默认就是仓库根。

    这是 workspace 的**唯一口径**：validators.cli 也走这里（锚同样是仓库根），
    因此同一个参数在两个入口指向同一个目录——两处各解析一遍就是两套语义。
    """

    return resolve_directory(getattr(args, "workspace", None), anchor=root, fallback=root)


def resolve_target_file(args: argparse.Namespace, root: Path) -> Path:
    """定位待检查文件：相对路径优先按 --workspace 解析，其次按当前工作目录解析。

    这也是 target 的**唯一口径**（validators.cli 的 check / pipeline 走同一条规则）：
    带工作区前缀的路径（"--workspace X" 配 "X/某文件"）因此能被认出来并归一化成
    工作区相对路径，而不是被判成"文件不存在"。文件定位不到时抛 PolicyContextError，
    两个入口都按配置错误（退出码 2）处理——那是"用错了"而不是"证据不足"。
    """

    if not args.file:
        raise PolicyContextError("缺少待检查文件：除 --check-rules 外必须提供 file")

    candidate = Path(args.file)
    if not candidate.is_absolute():
        workspace = resolve_workspace(args, root)
        if (workspace / candidate).is_file():
            candidate = workspace / candidate
    if not candidate.is_file():
        raise PolicyContextError(f"待检查文件不存在: {args.file}")
    return candidate.resolve()


def build_context_args(args: argparse.Namespace, root: Path) -> tuple[PolicyContext, str]:
    """把 CLI 参数转换为 PolicyContext；安全关键字段缺失时直接失败。

    返回值带上**分层来源**：层与"层是怎么定的"必须是同一次解析的产物。
    分两次算会让报告出来的口径与真正参与 scope 匹配的值有机会不一致——
    那正是"读数与判定对不上"这类问题的起点。
    """

    file_path = resolve_target_file(args, root)
    anchor = resolve_workspace(args, root)
    layer, layer_source = resolve_layer(args, anchor=anchor, root=root, file_path=file_path)

    data: dict[str, Any] = {
        "request_id": args.request_id or f"cli-{uuid.uuid4().hex[:12]}",
        # 用绝对路径进入规范化器：它会按 anchor（--workspace 或仓库根）转成仓库相对路径。
        # 否则 "--workspace X" 配上 "X/中文/文件.py" 这种写法会让上下文里留下带前缀的路径。
        "file": str(file_path),
        "layer": layer,
        "language": canonical_identifier(args.language) if args.language else None,
        "operation": args.operation,
        "project": args.project,
        "agent": args.agent,
        "module": args.module,
        "task": args.task,
        "trace_id": args.trace_id,
    }
    if args.dependencies is None:
        data["dependencies"] = ()
    else:
        data["dependencies"] = parse_dependencies(args.dependencies)

    return build_context(data, repo_root=anchor), layer_source


def exit_code_for(result: ValidationResult) -> int:
    return EXIT_ALLOWED if result.decision is Decision.ALLOW else EXIT_VIOLATION


def context_payload(context: PolicyContext) -> dict[str, Any]:
    return json.loads(context.model_dump_json())


# --------------------------------------------------------------------------- P5：检查量摘要

CHECK_VOLUME_NOTE = (
    "skipped ≠ passed；complete=false 表示本次有规则因为调用方没声明某个维度而"
    "根本没被查，这个 allow 比完整判定弱"
)

SKIP_REASON_EVIDENCE_NOT_COLLECTED = "evidence_not_collected"
SKIP_REASON_MISSING_DIMENSION = "missing_dimension"
SKIP_REASON_SCOPE_MISMATCH = "scope_mismatch"

# 固定顺序：输出的键序不随规则集与本次判定变化（相同输入必须得到逐字节相同的输出）。
SKIP_REASON_ORDER = (
    SKIP_REASON_EVIDENCE_NOT_COLLECTED,
    SKIP_REASON_MISSING_DIMENSION,
    SKIP_REASON_SCOPE_MISMATCH,
)

# 缺维度时告诉调用方该补哪个参数：诊断要给"改成什么形态就能过"。
DIMENSION_FLAGS: dict[str, str] = {
    "operation": "--operation",
    "language": "--language",
    "layer": "--layer",
    "module": "--module",
    "project": "--project",
    "agent": "--agent",
}


def _dimension_sort_key(name: str) -> tuple[int, str]:
    """按 scope 的维度顺序排（与 match_scope 的遍历顺序一致）；未知维度排在最后。"""

    if name in KNOWN_SCOPE_DIMENSIONS:
        return (KNOWN_SCOPE_DIMENSIONS.index(name), name)
    return (len(KNOWN_SCOPE_DIMENSIONS), name)


def build_check_volume(
    rules: RuleSet,
    context: PolicyContext,
    result: ValidationResult,
    *,
    evidence: Any | None = None,
    obligations: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """把"这次到底查了多少"写成结构化摘要（只读，不改变任何判定）。

    为什么不能只报 skipped 条数（07 号报告 P5）：缺 `--operation` 时 TESTING-001/002
    只是进 skipped_rules，判定照样 allow、退出码不变——两个 allow 在读数上长得一模一样。
    这里把三件事分开：

    - **范围不匹配**：规则与本次上下文无关（例如 layer 不同）；
    - **缺维度**：规则声明了某个维度，而调用方没有给值 —— 规则**根本没被查**；
    - **没有证据提供者**：范围命中，但本次调用没有验证器流水线（证据类 checker 无法判定）。

    分类只依赖结构化事实（`rule.scope` 与上下文的比较结果、scope 是否命中），
    **不解析 SkippedRule.reasons 文本**：文本是给人看的渲染，不是判定输入。
    每条被跳过的规则恰好落进一个桶，因此 skipped_by_reason 各桶之和 = skipped_rule_count。

    `missing_dimensions` 从数据算：对每条被跳过的规则，把 `rule.scope` 声明的维度与
    本次上下文的实际取值逐一比较，列出"规则要、上下文没有"的维度名。
    `complete = not missing_dimensions`：声明得够不够全，与"有没有证据"是两条轴。
    `served_checkers` 只认证据报告（EvidenceBundle.served_checkers），不认声明。

    台阶 3c（J1(c)）：调用方**显式**给出义务账摘要时，`complete` 还要再与 `obligations_open == 0`
    取合取——一份"有规则根本没被查"的读数与一份"有义务还挂着"的读数都不该被读成完整判定。
    没给账本时**不加任何键**：缺键的意思是"这次没有账本可读"，不是"0 条未结义务"
    （两者必须能分开读，AGENTS 第 46/50 条）。
    """

    canonical = normalize_context(context)
    by_id = {rule.canonical_id: rule for rule in rules.rules}
    reasons = {name: 0 for name in SKIP_REASON_ORDER}
    severities: dict[str, int] = {}
    blocking_skipped = 0
    missing: list[str] = []

    for item in result.skipped_rules:
        rule = by_id.get(item.rule_id)
        if rule is None:
            # 规则集里没有的 ID：不替它猜级别（与审计侧 skipped_by_severity 的口径一致），
            # 也说不清它为什么被跳过——按"规则与本次无关"记，绝不冒充满足维度。
            severities["unknown"] = severities.get("unknown", 0) + 1
            reasons[SKIP_REASON_SCOPE_MISMATCH] += 1
            continue

        severity = rule.severity.value
        severities[severity] = severities.get(severity, 0) + 1
        if rule.severity in BLOCKING_SEVERITIES:
            blocking_skipped += 1

        scope_result = match_scope(rule.scope, canonical)
        if scope_result.matched:
            # 范围命中却仍进 skipped_rules：引擎只有一条这样的路径——本次调用没有验证器
            # 流水线，而这条规则需要证据类 checker（仅凭上下文就能判的 checker 不会被跳过）。
            # 判据是"scope 命中"这条结构化事实，不是 reasons 里那句话。
            reasons[SKIP_REASON_EVIDENCE_NOT_COLLECTED] += 1
            continue

        absent = [
            comparison.dimension
            for comparison in scope_result.comparisons
            if not comparison.matched and comparison.actual is None
        ]
        if absent:
            reasons[SKIP_REASON_MISSING_DIMENSION] += 1
            for dimension in absent:
                if dimension not in missing:
                    missing.append(dimension)
            continue
        reasons[SKIP_REASON_SCOPE_MISMATCH] += 1

    missing.sort(key=_dimension_sort_key)
    served: tuple[str, ...] = () if evidence is None else tuple(evidence.served_checkers)
    volume = {
        "rule_count": len(rules.rules),
        "effective_rule_count": len(result.matched_rules),
        "skipped_rule_count": len(result.skipped_rules),
        "skipped_by_reason": {name: reasons[name] for name in SKIP_REASON_ORDER},
        "skipped_by_severity": {name: severities[name] for name in sorted(severities)},
        "blocking_capable_skipped": blocking_skipped,
        "served_checkers": list(served),
        "missing_dimensions": missing,
        "complete": not missing,
        "note": CHECK_VOLUME_NOTE,
    }
    if obligations is not None:
        open_count = int(obligations["obligations_open"])
        volume["obligations_open"] = open_count
        volume["obligations_note"] = str(obligations["note"])
        volume["complete"] = volume["complete"] and open_count == 0
    return volume


def render_check_volume(volume: Mapping[str, Any]) -> list[str]:
    """把检查量摘要渲染成文本：只新增行，不改既有行，缺维度时给一行显眼的 INCOMPLETE。"""

    reasons = ", ".join(
        f"{name}={count}" for name, count in volume["skipped_by_reason"].items()
    )
    severities = (
        ", ".join(f"{name}={count}" for name, count in volume["skipped_by_severity"].items())
        or "<none>"
    )
    served = ", ".join(volume["served_checkers"]) or "<none>"
    missing = ", ".join(volume["missing_dimensions"]) or "<none>"
    lines = [
        "check volume: rule_count={rule_count} effective_rule_count={effective_rule_count} "
        "skipped_rule_count={skipped_rule_count} blocking_capable_skipped="
        "{blocking_capable_skipped} complete={complete}".format(**volume),
        f"  skipped_by_reason: {reasons}",
        f"  skipped_by_severity: {severities}",
        f"  served_checkers: {served}",
        f"  missing_dimensions: {missing}",
    ]
    if volume["missing_dimensions"]:
        flags = ", ".join(DIMENSION_FLAGS.get(name, name) for name in volume["missing_dimensions"])
        lines.append(
            "INCOMPLETE: 本次有 "
            f"{volume['skipped_by_reason'][SKIP_REASON_MISSING_DIMENSION]} 条规则因为没有声明"
            f"维度而根本没有被查（缺 {missing}）；补 {flags} 后重跑——"
            "skipped ≠ passed，这个 allow 比完整判定弱"
        )
    if "obligations_open" in volume:
        # 台阶 3c：义务账的读数是**单独一行**，不与「缺维度」混成同一句话——
        # complete 可能因为两个不同的原因变成 false，理由必须说得出来（AGENTS 第 52 条）。
        lines.append("  obligations_open: " + str(volume["obligations_open"]))
        if volume["obligations_open"]:
            lines.append(
                "OPEN OBLIGATIONS: 本次有 "
                + str(volume["obligations_open"])
                + " 条未结义务（覆盖它的测试还没能真的跑起来）；"
                "解除只由一次真实 pytest 运行判定——让测试真的跑一次，并带上同一个 --obligations 账本"
            )
    return lines


def render_text(
    context: PolicyContext,
    rules: RuleSet,
    result: ValidationResult | None,
    imports: Sequence[str] = (),
    *,
    report: Any | None = None,
    layer_source: str | None = None,
    check_volume: Mapping[str, Any] | None = None,
) -> str:
    # 文档承诺"不提供 --layer 时标明层是怎么来的"：标明这件事必须在输出里看得见，
    # 否则读者分不清 layer=controller 是声明的、来自平台数据的，还是按文件名猜的。
    # 只有 policy.check 的 run() 会传 check_volume；其他入口（validators.cli 的流水线文本）
    # 不传就保持原样——只增不改，任何既有行的字节都不动。
    layer_note = LAYER_SOURCE_NOTES.get(layer_source or "", "")
    lines = [] if report is None else [render_report(report), ""]
    lines.extend([
        f"file: {context.file}",
        f"layer: {context.layer}{layer_note}",
        f"language: {context.language or '<unknown>'}",
        f"operation: {'<none>' if context.operation is None else context.operation.value}",
        f"module: {context.module or '<not provided>'}",
        f"rules: {len(rules)} ({rules.identity})",
    ])
    if imports:
        lines.append("imports (reported, not used for the decision): " + ", ".join(imports))
    lines.append("")

    if result is None:
        lines.append(f"PASS: 规则集校验通过，共 {len(rules)} 条规则")
        return chr(10).join(lines)

    lines.append(f"schema: {SCHEMA_VERSION} / policy: {result.policy_version}")
    lines.append("matched: " + (", ".join(result.matched_rules) or "<none>"))
    if result.skipped_rules:
        lines.append("skipped (规则范围不匹配，未参与判断):")
        for item in result.skipped_rules:
            lines.append(f"  - {item.rule_id}: " + "; ".join(item.reasons))
    else:
        lines.append("skipped: <none>")
    if check_volume is not None:
        # P5：把"这次到底查了多少"写在判定之前——读者要先看出这个 allow 是完整判定还是残缺判定。
        lines.extend(render_check_volume(check_volume))
    lines.append("")

    if result.required_action is not None:
        lines.append(f"BLOCK: 需要人工审批（required_action={result.required_action.value}）")

    if result.passed:
        lines.append(f"PASS: 未发现违规（decision={result.decision.value}）")
        return chr(10).join(lines)

    counts = result.severity_counts
    summary = ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
    if result.pending_findings:
        # pending **不在** severity_counts 里（那是"违规"的分布，见 ValidationResult）。
        # 不把它补进这一行，pending-only 的批次就会打出 decision=allow_with_warnings
        # 配 required_action=None——一行读不出理由的 FAIL（台阶 3b 的 B5）。
        summary = (summary + ", " if summary else "") + (
            f"pending_findings={len(result.pending_findings)}"
        )
    detail = summary or f"required_action={result.required_action.value}"
    lines.append(f"FAIL: decision={result.decision.value}（{detail}）")
    for violation in result.violations:
        lines.append("")
        lines.extend(_finding_lines(violation))
    if result.pending_findings:
        # 同一个渲染函数、另一个段标题：pending 条目的字段与 violations 逐字段同形，
        # 但**不许**混在同一份清单里——"真的报了违规"与"这次没能查成"必须分开读。
        lines.append("")
        lines.append(
            "pending_findings（"
            + str(len(result.pending_findings))
            + " 条：不是违规，是本次没能查成的说明）:"
        )
        for finding in result.pending_findings:
            lines.append("")
            lines.extend(_finding_lines(finding))
    if not result.violations:
        if result.required_action is not None:
            lines.append("（本次没有违规记录：阻断来自授权门禁，不是违规）")
        elif result.pending_findings:
            lines.append(
                "（本次没有违规记录：decision 是 "
                + result.decision.value
                + "，理由是上面 pending_findings 那一段，不是违规）"
            )
    return chr(10).join(lines)


def _finding_lines(entry: Violation) -> list[str]:
    """单条发现的文本渲染：violations 与 pending_findings **共用这一份**。

    两个通道的条目逐字段同形（同一个 _evidence_payload 形状），所以渲染也必须是同一份；
    分开写两份会让它们将来各自漂移，而"读起来一样"正是这一次要把它们分开的原因。
    """

    evidence = entry.evidence
    location = f"{evidence.subject} @ {evidence.kind}"
    if evidence.line is not None:
        location += f":{evidence.line}"
    rendered = [
        f"[{entry.severity.value}] {entry.canonical_id} {location}",
        f"  reason: {entry.message}",
        f"  evidence: {evidence.kind}={evidence.value}"
        + (f" — {evidence.detail}" if evidence.detail else ""),
    ]
    if evidence.kind == "dependency":
        rendered.append("  expected dependency direction: controller -> service -> repository")
    return rendered


def render_json(
    context: PolicyContext,
    rules: RuleSet,
    result: ValidationResult | None,
    imports: Sequence[str] = (),
    *,
    exit_code: int | None = None,
    report: Any | None = None,
    layer_source: str | None = None,
    check_volume: Mapping[str, Any] | None = None,
) -> str:
    if exit_code is None:
        exit_code = EXIT_ALLOWED if result is None else exit_code_for(result)
    if check_volume is None and result is not None:
        # 直接调用 render_json 的地方（学习手册里就是这么用的）也要拿到这一段读数：
        # 缺省从同一次运行的数据现算，绝不写一个"看起来像"的常量。
        check_volume = build_check_volume(
            rules,
            context,
            result,
            evidence=None if report is None else report.bundle,
        )
    payload: dict[str, Any] = {
        "check_volume": check_volume,
        "context": context_payload(context),
        "rule_set": {
            "count": len(rules),
            "ids": list(rules.ids),
            "identity": rules.identity,
            "sources": list(rules.source_paths),
            "schema_version": SCHEMA_VERSION,
        },
        "reported_imports": list(imports),
        "evidence": None if report is None else report.to_payload(),
        "exit_code": exit_code,
        # CLI 包装字段：result 之外的读数，不进决策协议载荷（决策协议版本见
        # policy.models.SCHEMA_VERSION，这里不写死一个字面量）。
        "layer_source": layer_source,
        # 包装自己的版本（加键 / 改语义就要动它，AGENTS 第 55 条）：
        # 它说的是"外层这些键是哪一版形状"，不替代 result 的 schema_version。
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "result": None if result is None else result.to_decision_dict(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def build_validator_request(
    args: argparse.Namespace,
    *,
    anchor: Path,
    context: PolicyContext,
    rules: RuleSet,
) -> Any:
    """把 CLI 参数组装成一次验证请求（Phase 5 的默认证据来源）。"""

    from validators.pipeline import PipelineRequest

    workspace = resolve_workspace(args, anchor)
    changed = tuple(
        sorted({item.replace("\\", "/") for item in (args.changed or ()) if item.strip()})
    )
    explicit = None if args.dependencies is None else parse_dependencies(args.dependencies)
    only = tuple(item.strip() for item in (args.validators or "").split(",") if item.strip())
    return PipelineRequest(
        target=context.file,
        workspace=workspace,
        context=context,
        rules=rules,
        changed_files=changed,
        explicit_dependencies=explicit,
        only=only,
    )


def render_report(report: Any) -> str:
    """渲染验证器证据段（实现放在验证器层，这里只做转发，避免两处口径漂移）。"""

    from validators.pipeline import render_report as _render

    return _render(report)


def collect_evidence(
    args: argparse.Namespace,
    *,
    anchor: Path,
    context: PolicyContext,
    rules: RuleSet,
) -> Any:
    """运行验证器流水线；配置不可用时抛 ValidatorConfigError（退出码 2，绝不降级放行）。"""

    from validators.pipeline import run_pipeline
    from validators.registry import load_config

    config_root = resolve_directory(args.config_root, anchor=anchor, fallback=anchor)
    config = load_config(root=config_root)
    request = build_validator_request(args, anchor=anchor, context=context, rules=rules)
    return run_pipeline(request, config=config, keep_temp=bool(args.keep_temp))


def obligation_summary(
    args: argparse.Namespace,
    *,
    context: PolicyContext,
    result: ValidationResult,
    report: Any | None,
) -> Mapping[str, Any]:
    """台阶 3c：把本次判定与本次流水线的事实记进义务账，并给出摘要。

    记账是**只增**的：它不改变 `result`、不改变退出码（L5 warn 期的口径，方案 §3.3 的
    "会话内只记账、不判罚"）。但账本读不懂 / 写不了时**失败关闭**（调用方返回退出码 2）——
    `--obligations` 是调用方显式声明的输入，"声明了却读不懂"与"没声明"必须能分开读。

    `python -m policy.check` 是**本机门禁**这一侧的记账点：它手里同时有判定（pending_findings）
    与真流水线（这次 pytest 到底跑成没有），因此解除义务的那条 `test_run` 只能在这里记。
    """

    from .obligations import (
        PYTEST_VALIDATOR_ID,
        book_pending_findings,
        real_pytest_run,
        record_test_run,
        summarize,
    )

    ledger = Path(args.obligations)
    snapshot = ()
    if report is not None:
        snapshot = tuple(report.pending_implementation)
    book_pending_findings(
        ledger,
        findings=result.pending_findings,
        target=context.file,
        pending_snapshot=[item.to_payload() for item in snapshot],
    )
    if report is not None:
        record = report.record(PYTEST_VALIDATOR_ID)
        if record is not None:
            nodeids = selected_nodeids(report)
            selected = tuple(
                sorted({str(item).split("::")[0].replace("\\", "/") for item in nodeids})
            )
            record_test_run(
                ledger,
                target=context.file,
                selected_tests=selected,
                python_tests_executed=real_pytest_run(
                    pytest_status=record.status.value,
                    served_checkers=report.served_checkers,
                    selected_tests=selected,
                ),
                source="policy.check",
            )
    return summarize(ledger)


def selected_nodeids(report: Any) -> tuple[str, ...]:
    """流水线报告里这次**选中**的测试（`selection.nodeids`；取不到就是空元组，不猜）。"""

    selection = getattr(report, "selection", None)
    if not isinstance(selection, Mapping):
        return ()
    nodeids = selection.get("nodeids")
    if not isinstance(nodeids, (list, tuple)):
        return ()
    return tuple(str(item) for item in nodeids if item)


def run(argv: Sequence[str] | None = None, *, root: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    anchor = root if root is not None else repo_root()
    rule_dirs = (
        tuple(Path(item) for item in args.rules) if args.rules else default_rule_dirs(anchor)
    )

    declared_changes = [item for item in (args.changed or ()) if item.strip()]
    if declared_changes and args.operation is None and not args.check_rules:
        # 失败关闭的边界是**标定过的**：只对"自相矛盾"的调用生效——声明了变更集
        # （"这是一次变更"）却不说是什么操作，判定必然是残缺的，补一句 --operation 就能改对。
        # 完全不给 --operation 的调用仍然可执行：README 与 60+ 处文档写的都是
        # `python -m policy.check <file> --layer X`，强行要求 --operation 会把它们全变成
        # 配置错误，还会把文档里的 allow 例子变成 block（--operation edit 会激活 TESTING-001）。
        print(
            "config error: 配置自相矛盾：--changed 声明了变更集，却没有 --operation；"
            "声明了「这是一次变更」却不说是什么操作，判定必然是残缺的。"
            "请显式给出 --operation（"
            + "/".join(item.value for item in Operation)
            + "）",
            file=sys.stderr,
        )
        return EXIT_ERROR

    try:
        rules = load_rule_set(rule_dirs, repo_root=anchor)
    except LoaderError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR

    report = None
    evidence = None
    layer_source = None
    try:
        context: PolicyContext | None = None
        if not args.check_rules:
            context, layer_source = build_context_args(args, anchor)
        imports = ()
        if args.file and not args.check_rules:
            # 这里只是"报告用"的导入列表：读不了就不报，让流水线去判（它会按失败关闭
            # 给出 py.source failed 的阻断点），不要因为一份报告把它变成配置错误。
            try:
                imports = python_imports(
                    resolve_target_file(args, anchor).read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError):
                imports = ()
        if context is not None:
            report = collect_evidence(args, anchor=anchor, context=context, rules=rules)
            evidence = report.bundle
        result = None if context is None else evaluate(rules, context, evidence=evidence)
    except (PolicyContextError, ValueError, OSError) as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except EngineError as error:
        print(f"engine error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except ValidatorConfigError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR

    if context is None:
        context = PolicyContext(
            request_id=args.request_id or f"cli-{uuid.uuid4().hex[:12]}",
            file="policies",
            layer=UNKNOWN_LAYER,
        )

    # P5：读数与判定必须来自同一次运行——evidence 就是交给引擎的那个证据包。
    obligations = None
    if result is not None and args.obligations:
        try:
            obligations = obligation_summary(args, context=context, result=result, report=report)
        except ObligationsError as error:
            print(f"config error: 义务账本不可用：{error}", file=sys.stderr)
            return EXIT_ERROR
    volume = (
        None
        if result is None
        else build_check_volume(
            rules, context, result, evidence=evidence, obligations=obligations
        )
    )

    if args.json:
        rendered = render_json(
            context,
            rules,
            result,
            imports,
            report=report,
            layer_source=layer_source,
            check_volume=volume,
        )
    else:
        rendered = render_text(
            context,
            rules,
            result,
            imports,
            report=report,
            layer_source=layer_source,
            check_volume=volume,
        )
    print(rendered)
    return EXIT_ALLOWED if result is None else exit_code_for(result)



def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

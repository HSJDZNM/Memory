"""policy.check：命令行入口。

用法:

    python -m policy.check examples/bad_controller.py
    python -m policy.check examples/good_controller.py
    python -m policy.check --check-rules

退出码：

    0 = 通过（ALLOW）
    1 = 发现违规（BLOCK / ALLOW_WITH_WARNINGS，含需要人工审批的 block）
    2 = 配置或执行错误（规则目录不可读、规则损坏、路径不合法、上下文不完整、未知 checker）

CLI 输出面向人（--json 时输出面向机器），Engine 结果始终保持结构化。
--json 的顶层是 CLI 包装（context / rule_set / reported_imports / exit_code），
其中 result 就是完整的 PolicyDecision 协议载荷，可被 policy.parse_decision 直接消费。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence

from .context import build_context
from .engine import EngineError, evaluate
from .loader import LoaderError, load_rule_set
from .models import (
    SCHEMA_VERSION,
    Decision,
    Operation,
    PolicyContext,
    PolicyContextError,
    RuleSet,
    ValidationResult,
    canonical_identifier,
)

__all__ = [
    "EXIT_ALLOWED",
    "EXIT_ERROR",
    "EXIT_VIOLATION",
    "build_parser",
    "context_payload",
    "default_rule_dirs",
    "exit_code_for",
    "infer_layer",
    "main",
    "parse_dependencies",
    "python_imports",
    "render_json",
    "render_text",
    "repo_root",
    "run",
]

EXIT_ALLOWED = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2

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
        default="",
        metavar="A,B",
        help="逗号分隔的直接依赖；不提供时只做导入报告，不用 import 列表判定",
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
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    parser.add_argument(
        "--check-rules",
        action="store_true",
        help="只校验规则集（不检查文件）；损坏时退出码 2",
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


def build_context_args(args: argparse.Namespace, root: Path) -> PolicyContext:
    """把 CLI 参数转换为 PolicyContext；安全关键字段缺失时直接失败。"""

    if not args.file:
        raise PolicyContextError("缺少待检查文件：除 --check-rules 外必须提供 file")

    file_path = Path(args.file)
    if not file_path.is_file():
        raise PolicyContextError(f"待检查文件不存在: {args.file}")

    data: dict[str, Any] = {
        "request_id": args.request_id or f"cli-{uuid.uuid4().hex[:12]}",
        "file": args.file,
        "layer": canonical_identifier(args.layer) if args.layer else infer_layer(args.file),
        "language": canonical_identifier(args.language) if args.language else None,
        "operation": args.operation,
        "project": args.project,
        "agent": args.agent,
        "module": args.module,
        "task": args.task,
        "trace_id": args.trace_id,
    }
    if args.dependencies == "":
        data["dependencies"] = ()
    else:
        data["dependencies"] = parse_dependencies(args.dependencies)

    return build_context(data, repo_root=root)


def exit_code_for(result: ValidationResult) -> int:
    return EXIT_ALLOWED if result.decision is Decision.ALLOW else EXIT_VIOLATION


def context_payload(context: PolicyContext) -> dict[str, Any]:
    return json.loads(context.model_dump_json())


def render_text(
    context: PolicyContext,
    rules: RuleSet,
    result: ValidationResult | None,
    imports: Sequence[str] = (),
) -> str:
    lines = [
        f"file: {context.file}",
        f"layer: {context.layer}",
        f"language: {context.language or '<unknown>'}",
        f"operation: {'<none>' if context.operation is None else context.operation.value}",
        f"module: {context.module or '<not provided>'}",
        f"rules: {len(rules)} ({rules.identity})",
    ]
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
    lines.append("")

    if result.required_action is not None:
        lines.append(f"BLOCK: 需要人工审批（required_action={result.required_action.value}）")

    if result.passed:
        lines.append(f"PASS: 未发现违规（decision={result.decision.value}）")
        return chr(10).join(lines)

    counts = result.severity_counts
    summary = ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
    detail = summary or f"required_action={result.required_action.value}"
    lines.append(f"FAIL: decision={result.decision.value}（{detail}）")
    for violation in result.violations:
        lines.append("")
        location = f"{violation.evidence.subject} @ {violation.evidence.kind}"
        lines.append(f"[{violation.severity.value}] {violation.canonical_id} {location}")
        lines.append(f"  reason: {violation.message}")
        lines.append(
            f"  evidence: {violation.evidence.kind}={violation.evidence.value}"
            + (f" ({violation.evidence.detail})" if violation.evidence.detail else "")
        )
        lines.append("  expected dependency direction: controller -> service -> repository")
    if not result.violations:
        lines.append("（本次没有违规记录：阻断来自授权门禁，不是违规）")
    return chr(10).join(lines)


def render_json(
    context: PolicyContext,
    rules: RuleSet,
    result: ValidationResult | None,
    imports: Sequence[str] = (),
    *,
    exit_code: int | None = None,
) -> str:
    if exit_code is None:
        exit_code = EXIT_ALLOWED if result is None else exit_code_for(result)
    payload: dict[str, Any] = {
        "context": context_payload(context),
        "rule_set": {
            "count": len(rules),
            "ids": list(rules.ids),
            "identity": rules.identity,
            "sources": list(rules.source_paths),
            "schema_version": SCHEMA_VERSION,
        },
        "reported_imports": list(imports),
        "exit_code": exit_code,
        "result": None if result is None else result.to_decision_dict(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def run(argv: Sequence[str] | None = None, *, root: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    anchor = root if root is not None else repo_root()
    rule_dirs = (
        tuple(Path(item) for item in args.rules) if args.rules else default_rule_dirs(anchor)
    )

    try:
        rules = load_rule_set(rule_dirs, repo_root=anchor)
    except LoaderError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR

    try:
        context = None if args.check_rules else build_context_args(args, anchor)
        imports = ()
        if args.file:
            imports = python_imports(Path(args.file).read_text(encoding="utf-8"))
        result = None if context is None else evaluate(rules, context)
    except (PolicyContextError, ValueError, OSError) as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except EngineError as error:
        print(f"engine error: {error}", file=sys.stderr)
        return EXIT_ERROR

    if context is None:
        context = PolicyContext(
            request_id=args.request_id or f"cli-{uuid.uuid4().hex[:12]}",
            file="policies",
            layer=UNKNOWN_LAYER,
        )

    renderer = render_json if args.json else render_text
    print(renderer(context, rules, result, imports))
    return EXIT_ALLOWED if result is None else exit_code_for(result)


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

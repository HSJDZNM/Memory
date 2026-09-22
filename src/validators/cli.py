"""validators.cli：验证器流水线的命令行入口。

    python -m validators.cli check <file>      只产出证据（不判定 allow / block）
    python -m validators.cli pipeline <file>   证据 + Policy Engine 判定
    python -m validators.cli registry          验证器注册表事实
    python -m validators.cli probe             探测外部工具（可用性 / 版本 / 配置）

退出码：0 通过（无发现、无阻断点）；1 有发现或失败关闭的阻断点；2 配置或用法错误。
probe 子命令恒以 0 结束：它只报告工具可用性与版本，缺失的工具在**判定**时才失败关闭。

判定永远由 Policy Engine 做：本 CLI 的 check 只回答"拿到了哪些证据"。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from policy.context import build_context
from policy.engine import EngineError, evaluate
from policy.loader import LoaderError, load_rule_set
from policy.models import Operation, PolicyContext, PolicyContextError, RuleSet

from . import PIPELINE_SCHEMA_VERSION
from .adapters.base import probe_tool
from .pipeline import PipelineReport, PipelineRequest, render_report, run_pipeline
from .registry import RegistryError, ValidationConfig, load_config, repo_root

__all__ = [
    "EXIT_ALLOWED",
    "EXIT_ERROR",
    "EXIT_FINDINGS",
    "build_parser",
    "main",
    "run",
]

EXIT_ALLOWED = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m validators.cli",
        description="把代码与外部工具输出变成确定性证据（Phase 5）。",
    )
    parser.add_argument(
        "command",
        choices=("check", "pipeline", "registry", "probe"),
        help="check=只产出证据；pipeline=证据+判定；registry=注册表事实；probe=工具探测",
    )
    parser.add_argument("file", nargs="?", help="待验证文件（工作区相对路径或绝对路径）")
    parser.add_argument("--workspace", default=None, help="工作区根目录，默认仓库根")
    parser.add_argument("--config-root", default=None, help="validation/ 配置所在目录，默认仓库根")
    parser.add_argument("--rules", action="append", default=None, metavar="DIR", help="规则目录，可重复")
    parser.add_argument("--layer", default=None, help="架构层（安全关键维度，必须显式声明）")
    parser.add_argument("--language", default="python", help="语言；空字符串表示未知")
    parser.add_argument("--module", default=None, help="模块名（刻意不从路径推断）")
    parser.add_argument("--operation", default=None, choices=[item.value for item in Operation])
    parser.add_argument("--request-id", default=None)
    parser.add_argument("--trace-id", default=None)
    parser.add_argument(
        "--changed",
        action="append",
        default=None,
        metavar="FILE",
        help="本次变更集里的文件（可重复），测试验证器需要它",
    )
    parser.add_argument(
        "--changed-from-git",
        default=None,
        metavar="REF",
        help="用 git diff --name-only <REF> 生成变更集（需要本机有 git）",
    )
    parser.add_argument(
        "--dependencies",
        default=None,
        metavar="A,B",
        help="显式声明依赖（覆盖 AST / 依赖图证据；只在需要重放历史场景时使用）",
    )
    parser.add_argument(
        "--validators",
        default=None,
        metavar="A,B",
        help="只运行这些验证器（allowlist）；少跑的 checker 会失败关闭",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读证据")
    parser.add_argument("--keep-temp", action="store_true", help="保留本次运行的临时目录")
    parser.add_argument("--show", default=None, help="registry 命令：显示单个验证器的声明")
    return parser


def _workspace(args: argparse.Namespace, anchor: Path) -> Path:
    """解析 --workspace：与 policy.check 用同一条规则（cwd → 仓库根 → 原样）。"""

    from policy.check import resolve_workspace

    return resolve_workspace(args, anchor)


def _changed_files(args: argparse.Namespace, anchor: Path) -> Tuple[str, ...]:
    items = list(args.changed or [])
    if args.changed_from_git:
        completed = _git_changed(args.changed_from_git, anchor)
        items.extend(completed)
    return tuple(sorted({item.replace("\\", "/") for item in items if item}))


def _git_changed(ref: str, anchor: Path) -> Tuple[str, ...]:
    import subprocess

    # -c core.quotepath=false：git 默认会把非 ASCII 路径 C 引号转义成
    # "docs/architecture/\344\275\277..."，得到的是**不可用**的路径，
    # 而仓库自己的文档目录就是中文名（policy.models.normalize_repo_path 也允许非 ASCII）。
    # 只影响这一次调用，不改用户的 git 配置。
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=false", "diff", "--name-only", ref],
        cwd=str(anchor),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        raise RegistryError(
            "git diff 失败（" + ref + "）：" + (completed.stderr or "").strip()
            + "；没有变更集时测试验证器会失败关闭"
        )
    return tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())


def build_context_from_args(args: argparse.Namespace, anchor: Path, workspace: Path) -> PolicyContext:
    if not args.file:
        raise PolicyContextError("缺少待验证文件")
    layer = args.layer
    if layer is None:
        raise PolicyContextError(
            "缺少 --layer：layer 是安全关键维度，适配器与 CLI 都不得从文件名推断"
        )
    language = args.language.strip().lower() if args.language else None
    return build_context(
        {
            "request_id": args.request_id or "validators-" + uuid.uuid4().hex[:12],
            "file": args.file,
            "layer": layer,
            "language": language,
            "module": args.module,
            "operation": args.operation,
            "trace_id": args.trace_id,
        },
        repo_root=workspace,
    )


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    anchor = repo_root()
    from policy.check import resolve_directory

    anchor = resolve_directory(args.config_root, anchor=anchor, fallback=anchor)
    workspace = _workspace(args, anchor)

    try:
        config = load_config(root=anchor)
    except RegistryError as error:
        print("config error: " + str(error), file=sys.stderr)
        return EXIT_ERROR

    if args.command == "registry":
        return _registry(args, config)
    if args.command == "probe":
        return _probe(args, config, workspace)

    rule_dirs = tuple(Path(item) for item in args.rules) if args.rules else (anchor / "policies",)
    try:
        rules = load_rule_set(rule_dirs, repo_root=anchor)
    except LoaderError as error:
        print("config error: " + str(error), file=sys.stderr)
        return EXIT_ERROR

    try:
        context = build_context_from_args(args, anchor, workspace)
        request = PipelineRequest(
            target=context.file,
            workspace=workspace,
            context=context,
            rules=rules,
            changed_files=_changed_files(args, workspace),
            explicit_dependencies=(
                None if args.dependencies is None else _explicit(args.dependencies)
            ),
            only=tuple(item.strip() for item in (args.validators or "").split(",") if item.strip()),
        )
        report = run_pipeline(request, config=config, keep_temp=args.keep_temp)
        if args.command == "pipeline":
            result = evaluate(rules, context, evidence=report.bundle)
            exit_code = EXIT_ALLOWED if result.passed else EXIT_FINDINGS
            print(_render_pipeline(context, rules, result, report, json_output=args.json, exit_code=exit_code))
            return exit_code
        exit_code = _evidence_exit_code(report)
        print(_render_evidence(context, report, json_output=args.json, exit_code=exit_code))
        return exit_code
    except (PolicyContextError, RegistryError, ValueError, OSError) as error:
        print("config error: " + str(error), file=sys.stderr)
        return EXIT_ERROR
    except EngineError as error:
        print("engine error: " + str(error), file=sys.stderr)
        return EXIT_ERROR


def _explicit(raw: str) -> Tuple[str, ...]:
    return tuple(sorted({item.strip().lower() for item in raw.split(",") if item.strip()}))


def _evidence_exit_code(report: PipelineReport) -> int:
    if report.blockers:
        return EXIT_FINDINGS
    blocking = [
        item
        for item in report.evidence
        if item.severity.value in ("error", "critical")
    ]
    return EXIT_FINDINGS if blocking else EXIT_ALLOWED


def _registry(args: argparse.Namespace, config: ValidationConfig) -> int:
    registry = config.registry
    if args.show:
        spec = registry.spec(args.show)
        if spec is None:
            print("config error: 注册表里没有验证器 " + args.show, file=sys.stderr)
            return EXIT_ERROR
        payload = {
            "validators": [
                {
                    "id": spec.id,
                    "version": spec.version,
                    "kind": spec.kind.value,
                    "stage": spec.stage,
                    "checkers": list(spec.checkers),
                    "facts": list(spec.facts),
                    "requires": list(spec.requires),
                    "critical": spec.critical,
                    "description": spec.description,
                    "tool": None
                    if spec.tool is None
                    else {
                        "command": list(spec.tool.command),
                        "argv": list(spec.tool.argv),
                        "config": spec.tool.config,
                        "version_requirement": spec.tool.version_requirement,
                    },
                }
            ]
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return EXIT_ALLOWED

    payload = {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "registry": config.registry_path.as_posix(),
        "project": config.project_path.as_posix(),
        "test_layout": config.layout_path.as_posix(),
        "stages": list(registry.stages),
        "defaults": registry.defaults.model_dump(),
        "rule_packs": [
            {"id": pack.id, "language": pack.language, "validators": list(pack.validators)}
            for pack in registry.rule_packs
        ],
        "checkers": {
            language: {key: list(value) for key, value in registry.checkers_for_language(language).items()}
            for language in sorted({pack.language for pack in registry.rule_packs})
        },
        "validators": [
            {
                "id": spec.id,
                "version": spec.version,
                "kind": spec.kind.value,
                "stage": spec.stage,
                "checkers": list(spec.checkers),
                "critical": spec.critical,
                "tool": None if spec.tool is None else spec.tool.command[0],
            }
            for spec in registry.validators
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return EXIT_ALLOWED


def _probe(args: argparse.Namespace, config: ValidationConfig, workspace: Path) -> int:
    lines: list[str] = []
    payload: dict[str, Any] = {"schema_version": PIPELINE_SCHEMA_VERSION, "tools": []}
    failures = 0
    tmp_dir = config.root / ".tmp" / "validators" / ("probe-" + uuid.uuid4().hex[:8])
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        for spec in config.registry.validators:
            if spec.tool is None:
                continue
            probe = probe_tool(
                spec.tool,
                timeout_ms=config.registry.defaults.probe_timeout_ms,
                max_output_bytes=config.registry.defaults.max_output_bytes,
                workspace=workspace,
                tmp_dir=tmp_dir,
            )
            payload["tools"].append(
                {
                    "validator": spec.id + "@" + spec.version,
                    "tool": spec.tool.command[0],
                    "status": probe.status.value,
                    "version": probe.version,
                    "requirement": spec.tool.version_requirement,
                    "reason": probe.reason,
                }
            )
            lines.append(
                spec.id
                + ": "
                + probe.status.value
                + (" version=" + probe.version if probe.version else "")
                + (" (" + probe.reason + ")" if probe.reason else "")
            )
            if not probe.ok and spec.critical:
                failures += 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for line in lines:
            print(line)
        print("缺失或不匹配的关键工具：" + str(failures) + "（用到它们的规则会失败关闭）")
    return EXIT_ALLOWED


def _render_evidence(
    context: PolicyContext,
    report: PipelineReport,
    *,
    json_output: bool,
    exit_code: int,
) -> str:
    if json_output:
        return json.dumps(
            _payload(context, report, None, exit_code), ensure_ascii=False, indent=2, sort_keys=True
        )
    return render_report(report)


def _render_pipeline(
    context: PolicyContext,
    rules: RuleSet,
    result: Any,
    report: PipelineReport,
    *,
    json_output: bool,
    exit_code: int,
) -> str:
    if json_output:
        return json.dumps(
            _payload(context, report, result, exit_code), ensure_ascii=False, indent=2, sort_keys=True
        )
    from policy.check import render_text

    header = _render_evidence(context, report, json_output=False, exit_code=exit_code)
    return header + chr(10) + chr(10) + render_text(context, rules, result, ())


def _payload(
    context: PolicyContext, report: PipelineReport, result: Any, exit_code: int
) -> Mapping[str, Any]:
    return {
        "context": json.loads(context.model_dump_json()),
        "exit_code": exit_code,
        "evidence": report.to_payload(),
        "result": None if result is None else result.to_decision_dict(),
        "schema_version": PIPELINE_SCHEMA_VERSION,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

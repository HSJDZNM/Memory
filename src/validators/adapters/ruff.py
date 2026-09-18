"""Ruff 适配器：外部 Linter 的原始输出 → 统一证据。

约定：

- 参数与配置来自注册表（validation/validators.yaml + validation/ruff.toml）；
- "哪条诊断归属于哪个规则"由**规则数据**决定（policies/coding/*.yaml 里的 codes），
  不由工具决定；没有归属的诊断计入 unmapped，出现在报告里但不参与判定；
- 工具缺失 / 版本不符 / 超时 / 崩溃 / 输出非法一律失败关闭，绝不当作"没有风格问题"。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from policy.evidence import EvidenceLocation, ValidationEvidence, ValidatorStatus
from policy.models import Rule

from ..models import ValidatorSpec
from ..registry import ValidationConfig
from .base import (
    AdapterResult,
    Probe,
    ToolError,
    build_argv,
    config_facts,
    parse_json_output,
    run_tool,
    sanitize_text,
)

__all__ = ["run_ruff", "map_diagnostics"]

_DIAGNOSTIC_STATUS = ValidatorStatus.FINDINGS


def run_ruff(
    *,
    spec: ValidatorSpec,
    config: ValidationConfig,
    probe: Probe,
    target_path: str,
    workspace: Path,
    rules: Sequence[Rule],
    python: str,
    tmp_dir: Path,
    python_paths: Sequence[Path] = (),
) -> AdapterResult:
    """对单个文件运行 Ruff 并把 JSON 诊断映射成证据。"""

    if spec.tool is None:
        raise ToolError("tool.ruff 缺少 tool 声明，无法运行外部 Linter")
    tool_config = config.config_path(spec)
    config_path, config_sha = config_facts(tool_config, root=config.root)
    timeout_ms = spec.timeout_ms or config.registry.defaults.timeout_ms
    max_output_bytes = spec.max_output_bytes or config.registry.defaults.max_output_bytes

    argv = build_argv(
        spec.tool,
        probe,
        python=python,
        workspace=workspace,
        config=tool_config,
        paths=(target_path,),
        tmp_dir=tmp_dir,
    )
    run = run_tool(
        spec.tool,
        probe,
        argv,
        workspace=workspace,
        tmp_dir=tmp_dir,
        timeout_ms=timeout_ms,
        max_output_bytes=max_output_bytes,
        findings_exit_codes=(1,),
        config=tool_config,
        python_paths=python_paths,
    )
    invocation = run.payload(
        tool=spec.tool.command[0], version=probe.version, config=config_path,
        config_sha256=config_sha,
    )
    if run.status is not ValidatorStatus.OK:
        return AdapterResult(status=run.status, tool=invocation, reason=run.reason)

    try:
        document = parse_json_output(run.stdout)
    except ToolError as error:
        return AdapterResult(
            status=ValidatorStatus.OUTPUT_INVALID, tool=invocation, reason=str(error)
        )
    if not isinstance(document, list):
        return AdapterResult(
            status=ValidatorStatus.OUTPUT_INVALID,
            tool=invocation,
            reason="Ruff 的 JSON 输出不是列表",
        )

    evidence, unmapped = map_diagnostics(
        document,
        rules=rules,
        workspace=workspace,
        target_path=target_path,
        tool=invocation,
        max_message_chars=config.registry.defaults.max_message_chars,
    )
    return AdapterResult(
        status=_DIAGNOSTIC_STATUS if evidence else ValidatorStatus.OK,
        evidence=evidence,
        tool=invocation,
        unmapped=unmapped,
        findings=len(document),
        reason=None if document else "没有诊断",
    )


def map_diagnostics(
    document: Sequence[Any],
    *,
    rules: Sequence[Rule],
    workspace: Path,
    target_path: str,
    tool: Any,
    max_message_chars: int,
) -> Tuple[Tuple[ValidationEvidence, ...], int]:
    """把 Ruff 诊断映射成证据：命中的规则产出证据，未映射的计入返回值。"""

    evidence: list[ValidationEvidence] = []
    unmapped = 0
    for item in document:
        if not isinstance(item, Mapping):
            unmapped += 1
            continue
        code = str(item.get("code") or "").upper()
        owners = [rule for rule in rules if _owns(rule, code)]
        if not owners:
            unmapped += 1
            continue
        location = item.get("location") or {}
        try:
            line = int(location.get("row"))
            column = max(0, int(location.get("column", 1)) - 1)
        except (TypeError, ValueError):
            line, column = None, None
        file_path = _relative_file(item.get("filename"), workspace, target_path)
        message = sanitize_text(
            str(item.get("message", "")).strip(), workspace=workspace, limit=max_message_chars
        )
        fix = "该诊断可由 ruff --fix 自动修复" if item.get("fix") else None
        for rule in owners:
            evidence.append(
                ValidationEvidence(
                    validator_id="tool.ruff",
                    validator_version="1.0",
                    checker="style_lint",
                    rule_id=rule.id,
                    rule_version=rule.version,
                    severity=rule.severity,
                    message=message or ("Ruff 诊断 " + code),
                    value=code or "ruff",
                    location=EvidenceLocation(file=file_path, line=line, column=column),
                    tool=tool,
                    fix=fix,
                )
            )
    return tuple(sorted(evidence, key=lambda item: item.sort_key)), unmapped


def _owns(rule: Rule, code: str) -> bool:
    body = getattr(rule.rule, "style_lint", None)
    if body is None:
        return False
    return not body.codes or code in body.codes


def _relative_file(raw: Any, workspace: Path, fallback: str) -> str:
    """把工具输出里的文件名映射回仓库相对路径；无法映射时用目标文件（不臆造新路径）。"""

    if not isinstance(raw, str) or not raw:
        return fallback
    candidate = Path(raw)
    try:
        resolved = candidate if candidate.is_absolute() else (workspace / candidate)
        return resolved.resolve().relative_to(Path(workspace).resolve()).as_posix()
    except (OSError, ValueError):
        return fallback

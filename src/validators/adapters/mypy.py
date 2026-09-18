"""mypy 适配器：类型检查输出 → 统一证据（端口已就位，仓库当前没有启用类型规则）。

与 Ruff 适配器同构：参数与配置来自注册表，诊断归属由规则数据决定，工具不可用一律失败关闭。
本机与 CI 都没有装 mypy 时，一旦有规则真的需要 type_check，就会以 critical 阻断——
这是写下来的策略，而不是"没装就跳过"。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Sequence, Tuple

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
    run_tool,
    sanitize_text,
    tool_label,
)

__all__ = ["MYPY_LINE_RE", "run_mypy"]

MYPY_LINE_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+)(?::(?P<column>\d+))?:\s*"
    r"(?P<severity>error|warning|note):\s*(?P<message>.*?)(?:\s+\[(?P<code>[A-Za-z0-9_\-]+)\])?$"
)


def run_mypy(
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
    """对单个文件运行类型检查并把诊断映射成证据。"""

    if spec.tool is None:
        raise ToolError("tool.mypy 缺少 tool 声明，无法运行类型检查")
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
        tool=tool_label(spec.tool), version=probe.version, config=config_path,
        config_sha256=config_sha,
    )
    if run.status is not ValidatorStatus.OK:
        return AdapterResult(status=run.status, tool=invocation, reason=run.reason)

    evidence, unmapped = map_diagnostics(
        run.stdout + "\n" + run.stderr,
        rules=rules,
        workspace=workspace,
        target_path=target_path,
        tool=invocation,
        max_message_chars=config.registry.defaults.max_message_chars,
    )
    return AdapterResult(
        status=ValidatorStatus.FINDINGS if evidence else ValidatorStatus.OK,
        evidence=evidence,
        tool=invocation,
        unmapped=unmapped,
        findings=len(evidence) + unmapped,
        reason=None if evidence else "没有类型诊断",
    )


def map_diagnostics(
    text: str,
    *,
    rules: Sequence[Rule],
    workspace: Path,
    target_path: str,
    tool: object,
    max_message_chars: int,
) -> Tuple[Tuple[ValidationEvidence, ...], int]:
    """把 mypy 的文本诊断映射成证据。"""

    evidence: list[ValidationEvidence] = []
    unmapped = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("Success:", "Found ")):
            continue
        match = MYPY_LINE_RE.match(line)
        if match is None:
            continue
        severity = match.group("severity")
        if severity == "note":
            continue
        code = (match.group("code") or "").upper()
        owners = [rule for rule in rules if _owns(rule, code)]
        if not owners:
            unmapped += 1
            continue
        message = sanitize_text(
            match.group("message").strip(), workspace=workspace, limit=max_message_chars
        )
        column = match.group("column")
        for rule in owners:
            evidence.append(
                ValidationEvidence(
                    validator_id="tool.mypy",
                    validator_version="1.0",
                    checker="type_check",
                    rule_id=rule.id,
                    rule_version=rule.version,
                    severity=rule.severity,
                    message=(severity + ": " + message) if message else severity,
                    value=code or "type_error",
                    location=EvidenceLocation(
                        file=_relative_file(match.group("file"), workspace, target_path),
                        line=int(match.group("line")),
                        column=None if column is None else max(0, int(column) - 1),
                    ),
                    tool=tool,
                )
            )
    return tuple(sorted(evidence, key=lambda item: item.sort_key)), unmapped


def _owns(rule: Rule, code: str) -> bool:
    body = getattr(rule.rule, "type_check", None)
    if body is None:
        return False
    return not body.codes or code in body.codes


def _relative_file(raw: str, workspace: Path, fallback: str) -> str:
    """同 Ruff 适配器：只接受目标文件或工作区里真实存在的文件，其余回退。"""

    candidate = Path(raw)
    try:
        anchor = Path(workspace).resolve()
        resolved = candidate if candidate.is_absolute() else (workspace / candidate)
        relative = resolved.resolve().relative_to(anchor).as_posix()
    except (OSError, ValueError):
        return fallback
    if relative == fallback or resolved.is_file():
        return relative
    return fallback

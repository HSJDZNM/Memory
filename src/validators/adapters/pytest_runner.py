"""pytest 适配器：最小相关测试的选择 + 运行结果 → 统一证据。

它同时服务两个 checker：

- missing_tests：变更集里的生产文件找不到任何相关测试（在选择阶段就能判定）；
- failing_tests：选中的测试跑失败了（按失败用例逐条产出证据）。

限制与隔离：只跑选中的 node id（上限来自 test-layout.yaml），禁用缓存插件、清空 addopts、
限时限量，环境变量只保留白名单，超时终止整棵进程树。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Sequence, Tuple

from policy.evidence import EvidenceLocation, ValidationEvidence, ValidatorStatus
from policy.models import Rule

from ..models import TestLayout, ValidatorSpec
from ..registry import ValidationConfig
from ..selection import TestSelection, select_tests
from .base import (
    AdapterResult,
    Probe,
    ToolError,
    build_argv,
    config_facts,
    run_tool,
    sanitize_text,
)

__all__ = ["FAILED_RE", "run_pytest", "selection_payload"]

FAILED_RE = re.compile(r"^(?P<kind>FAILED|ERROR)\s+(?P<nodeid>[^\s]+)(?:\s+-\s+(?P<message>.*))?$")


def run_pytest(
    *,
    spec: ValidatorSpec,
    config: ValidationConfig,
    probe: Probe,
    target_path: str,
    workspace: Path,
    rules: Sequence[Rule],
    python: str,
    tmp_dir: Path,
    changed_files: Sequence[str],
    python_paths: Sequence[Path] = (),
) -> AdapterResult:
    """选择并运行最小相关测试。"""

    if spec.tool is None:
        raise ToolError("tool.pytest 缺少 tool 声明，无法运行测试验证器")
    layout: TestLayout = config.layout
    timeout_ms = spec.timeout_ms or layout.limits.timeout_ms
    max_output_bytes = spec.max_output_bytes or layout.limits.max_output_bytes
    max_message_chars = config.registry.defaults.max_message_chars

    selection = select_tests(
        target_path=target_path,
        changed_files=changed_files,
        layout=layout,
        workspace=workspace,
        max_nodeids=layout.limits.max_nodeids,
    )
    evidence = list(
        _missing_evidence(
            selection, rules=rules, max_message_chars=max_message_chars
        )
    )

    tool_config = config.config_path(spec)
    config_path, config_sha = config_facts(tool_config, root=config.root)
    invocation_tool = spec.tool.command[0] if spec.tool.command[0] != "{python}" else "pytest"

    if not selection.nodeids:
        return AdapterResult(
            status=ValidatorStatus.FINDINGS if evidence else ValidatorStatus.OK,
            evidence=tuple(sorted(evidence, key=lambda item: item.sort_key)),
            reason=selection.reason,
            payload={"selection": selection.to_payload()},
        )

    argv = build_argv(
        spec.tool,
        probe,
        python=python,
        workspace=workspace,
        config=tool_config,
        nodeids=selection.nodeids,
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
        findings_exit_codes=(0, 1, 5),
        config=tool_config,
        python_paths=python_paths,
    )
    invocation = run.payload(
        tool=invocation_tool, version=probe.version, config=config_path,
        config_sha256=config_sha,
    )
    if run.status is not ValidatorStatus.OK:
        return AdapterResult(
            status=run.status,
            tool=invocation,
            reason=run.reason,
            payload={"selection": selection.to_payload()},
        )

    if run.exit_code == 5:
        return AdapterResult(
            status=ValidatorStatus.OK,
            tool=invocation,
            reason="选中的测试没有收集到任何用例（pytest 退出码 5）",
            payload={"selection": selection.to_payload()},
        )
    if run.exit_code not in (0, 1):
        return AdapterResult(
            status=ValidatorStatus.CONFIG_ERROR,
            tool=invocation,
            reason="pytest 退出码 " + str(run.exit_code) + " 表示用法或内部错误",
            payload={"selection": selection.to_payload()},
        )

    evidence.extend(
        _failure_evidence(
            run.stdout,
            rules=rules,
            workspace=workspace,
            target_path=target_path,
            tool=invocation,
            max_message_chars=max_message_chars,
        )
    )
    return AdapterResult(
        status=ValidatorStatus.FINDINGS if evidence else ValidatorStatus.OK,
        evidence=tuple(sorted(evidence, key=lambda item: item.sort_key)),
        tool=invocation,
        reason=None if evidence else "选中的测试全部通过",
        payload={"selection": selection.to_payload()},
    )


def selection_payload(selection: TestSelection) -> dict:
    return selection.to_payload()


def _missing_evidence(
    selection: TestSelection, *, rules: Sequence[Rule], max_message_chars: int
) -> Tuple[ValidationEvidence, ...]:
    evidence: list[ValidationEvidence] = []
    owners = [rule for rule in rules if getattr(rule.rule, "missing_tests", None) is not None]
    for path in selection.missing:
        for rule in owners:
            evidence.append(
                ValidationEvidence(
                    validator_id="tool.pytest",
                    validator_version="1.0",
                    checker="missing_tests",
                    rule_id=rule.id,
                    rule_version=rule.version,
                    severity=rule.severity,
                    message="生产文件 " + path + " 有变更，但找不到对应的测试文件",
                    value=path,
                    location=EvidenceLocation(file=path, line=None, column=None),
                    fix="为该文件补一个测试（命名或目录见 validation/test-layout.yaml）",
                )
            )
    return tuple(sorted(evidence, key=lambda item: item.sort_key))


def _failure_evidence(
    text: str,
    *,
    rules: Sequence[Rule],
    workspace: Path,
    target_path: str,
    tool: object,
    max_message_chars: int,
) -> Tuple[ValidationEvidence, ...]:
    owners = [rule for rule in rules if getattr(rule.rule, "failing_tests", None) is not None]
    if not owners:
        return ()
    evidence: list[ValidationEvidence] = []
    for raw in text.splitlines():
        match = FAILED_RE.match(raw.strip())
        if match is None:
            continue
        nodeid = match.group("nodeid")
        file_part, _, case = nodeid.partition("::")
        message = sanitize_text(
            (match.group("message") or match.group("kind")).strip(),
            workspace=workspace,
            limit=max_message_chars,
        )
        for rule in owners:
            evidence.append(
                ValidationEvidence(
                    validator_id="tool.pytest",
                    validator_version="1.0",
                    checker="failing_tests",
                    rule_id=rule.id,
                    rule_version=rule.version,
                    severity=rule.severity,
                    message=match.group("kind") + " " + nodeid + "：" + message,
                    value=case or nodeid,
                    location=EvidenceLocation(file=file_part or target_path, line=None, column=None),
                    tool=tool,
                )
            )
    return tuple(sorted(evidence, key=lambda item: item.sort_key))

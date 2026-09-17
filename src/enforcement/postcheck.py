"""Post-execute Validation：收集执行后的证据，并跑注册表声明的验证器。

证据只收集平台能证明的东西：

- 文件类动作：执行前后哈希、字节数、是否有变化、diff 摘要与（脱敏后的）片段；
- 进程类动作：退出码、是否超时、输出摘要；
- 工具返回值：一律当作**不可信数据**，只留摘要与脱敏片段，绝不参与策略判断。

验证器失败时给出两个不同的状态：

- repair_required：确定性验证没过（语法错误、非零退出、超时）——需要修复；
- inconsistent：工具声称成功、但目标根本没有变化——证据自相矛盾，不能被当作成功。

回滚只在注册表声明 file_snapshot、且平台侧确实保存过快照时才做；否则显式写 unsupported，
绝不假装所有副作用都可撤销。
"""

from __future__ import annotations

import ast
import difflib
import hashlib
from pathlib import Path
from typing import Optional, Sequence

from .audit import redact_text
from .drivers import FileSnapshot
from .models import (
    ActionRequest,
    CheckResult,
    CheckStatus,
    ExecutionRecord,
    ExecutionStatus,
    FileBaseline,
    FileEffect,
    PostDecision,
    PostEvidence,
    PostStatus,
    ProcessEffect,
    ReasonCode,
    RollbackMode,
    RollbackOutcome,
    ToolSpec,
    ValidatorOutcome,
    digest_of,
    utc_now,
)

__all__ = [
    "DIFF_EXCERPT_CHARS",
    "baseline_files",
    "collect_evidence",
    "file_target",
    "restore_snapshot",
    "validate",
]

DIFF_EXCERPT_CHARS = 1200


def file_target(request: ActionRequest) -> Optional[str]:
    """文件类动作的目标路径（注册表声明过的参数名）。"""

    for name in ("file_path", "path"):
        value = request.value_of(name)
        if isinstance(value, str) and value:
            return value
    return None


def _sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def baseline_files(
    request: ActionRequest, spec: ToolSpec, *, workspace: Optional[Path | str] = None
) -> tuple[FileBaseline, ...]:
    """执行前捕获目标文件基线：delegated 工具执行后靠它判断"到底变了没有"。"""

    if spec.effect.value != "file_write":
        return ()
    relative = file_target(request)
    if relative is None or workspace is None:
        return ()
    root = Path(workspace).resolve()
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        return ()
    if not target.exists() or target.is_dir():
        return (FileBaseline(path=relative, existed=False, captured_at=utc_now()),)
    content = target.read_bytes()
    return (
        FileBaseline(
            path=relative,
            existed=True,
            sha256=_sha256_bytes(content),
            bytes=len(content),
            captured_at=utc_now(),
        ),
    )


def _file_effect(
    relative: str,
    baseline: Optional[FileBaseline],
    *,
    workspace: Optional[Path | str],
    before_text: Optional[str] = None,
) -> FileEffect:
    root = Path(workspace).resolve() if workspace is not None else None
    target = None if root is None else (root / relative).resolve()
    if target is not None and root is not None and root != target and root not in target.parents:
        raise ValueError(f"路径 {relative!r} 逃出工作区，拒绝收集证据")

    existed_after = bool(target is not None and target.exists() and target.is_file())
    content_after = target.read_bytes() if existed_after and target is not None else b""

    baseline_recorded = baseline is not None
    existed_before = bool(baseline.existed) if baseline else False
    before_digest = baseline.sha256 if baseline else None
    before_bytes = baseline.bytes if baseline else 0
    after_digest = _sha256_bytes(content_after) if existed_after else None

    # 没有基线时"变了没有"是未知：既不能当成"变了"，也不能当成"没变"。
    changed = (
        ((existed_before != existed_after) or (before_digest != after_digest))
        if baseline_recorded
        else False
    )
    diff_digest = None
    diff_excerpt = ""
    truncated = False
    if changed:
        # 变更前文本只可能来自执行器保存的快照；没有快照就留空，绝不编造原文。
        before = "" if before_text is None else before_text
        after_text = "" if not existed_after else content_after.decode("utf-8", "replace")
        diff_lines = list(
            difflib.unified_diff(
                before.splitlines(),
                after_text.splitlines(),
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
                lineterm="",
            )
        )
        diff_text = "\n".join(diff_lines)
        diff_digest = digest_of(diff_text)
        diff_excerpt = redact_text(diff_text, workspace=workspace, limit=DIFF_EXCERPT_CHARS)
        truncated = len(diff_text) > DIFF_EXCERPT_CHARS

    return FileEffect(
        path=relative,
        existed_before=existed_before,
        exists_after=existed_after,
        baseline_recorded=baseline_recorded,
        sha256_before=before_digest,
        sha256_after=after_digest,
        bytes_before=before_bytes,
        bytes_after=len(content_after),
        changed=changed,
        diff_digest=diff_digest,
        diff_excerpt=diff_excerpt,
        truncated=truncated,
    )


def collect_evidence(
    request: ActionRequest,
    spec: ToolSpec,
    record: ExecutionRecord,
    *,
    workspace: Optional[Path | str] = None,
    baselines: Sequence[FileBaseline] = (),
    untrusted_result: Optional[str] = None,
    snapshot: Optional[FileSnapshot] = None,
    now=None,
) -> PostEvidence:
    """收集执行后证据。这里不做判断，只如实记录。"""

    files: list[FileEffect] = []
    if spec.effect.value == "file_write":
        relative = file_target(request)
        if relative is not None and workspace is not None:
            baseline = next((item for item in baselines if item.path == relative), None)
            before_text = None
            if snapshot is not None and snapshot.path == relative and snapshot.existed:
                # 平台自己执行时，变更前文本来自执行器保存的快照（永远不会是编造的）。
                before_text = snapshot.content.decode("utf-8", "replace")
            files.append(
                _file_effect(relative, baseline, workspace=workspace, before_text=before_text)
            )

    process = None
    if spec.effect.value == "process" or record.exit_code is not None or record.timed_out:
        process = ProcessEffect(
            exit_code=record.exit_code,
            timed_out=record.timed_out,
            stdout_digest=record.stdout_digest,
            stderr_digest=record.stderr_digest,
            output_excerpt=record.output_excerpt,
            output_truncated=record.output_excerpt.endswith("[truncated]"),
        )

    return PostEvidence(
        action_id=request.action_id,
        request_id=request.request_id,
        trace_id=request.trace_id,
        action_hash=request.action_hash,
        tool_id=request.tool_id,
        execution_status=record.status,
        files=tuple(files),
        process=process,
        untrusted_result_digest=None if untrusted_result is None else digest_of(untrusted_result),
        collected_at=now or utc_now(),
    )


def _change_expectation(spec: ToolSpec, request: ActionRequest) -> bool:
    """这次动作是否**应当**改变目标文件。"""

    if spec.effect.value != "file_write":
        return False
    return True


def validate(
    request: ActionRequest,
    spec: ToolSpec,
    record: ExecutionRecord,
    evidence: PostEvidence,
    *,
    workspace: Optional[Path | str] = None,
    now=None,
) -> tuple[PostDecision, PostEvidence]:
    """按注册表声明的 post_checks 做确定性验证。

    返回（决策, 带上验证器结论的证据）：证据是审计的一部分，验证器结论必须一并落盘，
    否则"谁验的、验了什么"就只能靠猜。
    """

    moment = now or utc_now()
    checks: list[CheckResult] = []
    outcomes: list[ValidatorOutcome] = []

    if record.status is ExecutionStatus.REFUSED:
        return _with_validators(PostDecision(
            status=PostStatus.NOT_REQUIRED,
            reason_code=ReasonCode.ALLOW,
            action_id=request.action_id,
            request_id=request.request_id,
            trace_id=request.trace_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            checks=(
                CheckResult(
                    check="post",
                    status=CheckStatus.SKIPPED,
                    reason_code=ReasonCode.ALLOW,
                    detail="动作没有被执行：没有需要验证的效果",
                ),
            ),
            detail="未执行，无需事后验证",
            evaluated_at=moment,
        ), evidence)

    if not spec.post_checks:
        return _with_validators(PostDecision(
            status=PostStatus.NOT_REQUIRED,
            reason_code=ReasonCode.ALLOW,
            action_id=request.action_id,
            request_id=request.request_id,
            trace_id=request.trace_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            checks=(
                CheckResult(
                    check="post",
                    status=CheckStatus.SKIPPED,
                    reason_code=ReasonCode.ALLOW,
                    detail="注册表没有为该工具声明 post_checks",
                ),
            ),
            detail="该工具没有声明事后验证器",
            evaluated_at=moment,
        ), evidence)

    for name in spec.post_checks:
        outcome, check = _run_post_check(
            name, request, spec, record, evidence, workspace=workspace
        )
        outcomes.append(outcome)
        checks.append(check)

    failed = [item for item in checks if item.status is CheckStatus.FAILED]
    evidence = evidence.model_copy(update={"validators": tuple(outcomes)})

    if record.status is ExecutionStatus.FAILED:
        reason = (
            ReasonCode.EXECUTION_TIMEOUT if record.timed_out else ReasonCode.EXECUTION_FAILED
        )
        status = PostStatus.REPAIR_REQUIRED
    elif not failed:
        reason = ReasonCode.ALLOW
        status = PostStatus.VALIDATED
    elif any(
        item.check in ("file_syntax", "exit_code_zero", "target_exists") for item in failed
    ):
        # 确定性验证没过 → 需要修复（比"证据不一致"更可操作）
        reason = ReasonCode.POST_CHECK_FAILED
        status = PostStatus.REPAIR_REQUIRED
    elif any(item.check in ("file_changed", "content_matches") for item in failed):
        # 只有"目标里看不到请求声明的结果"这一类失败时，才是证据自相矛盾
        reason = ReasonCode.POST_EVIDENCE_INCONSISTENT
        status = PostStatus.INCONSISTENT
    else:
        reason = ReasonCode.POST_CHECK_FAILED
        status = PostStatus.REPAIR_REQUIRED

    detail = "; ".join(f"{item.check}: {item.detail}" for item in failed) if failed else ""
    return (
        PostDecision(
            status=status,
            reason_code=reason,
            action_id=request.action_id,
            request_id=request.request_id,
            trace_id=request.trace_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            checks=tuple(checks),
            detail=detail,
            evaluated_at=moment,
        ),
        evidence,
    )


def _with_validators(
    decision: PostDecision, evidence: PostEvidence
) -> tuple[PostDecision, PostEvidence]:
    """没有跑验证器时的空结论：仍然把（空的）验证器列表显式写进证据。"""

    return decision, evidence.model_copy(update={"validators": ()})


def _run_post_check(
    name: str,
    request: ActionRequest,
    spec: ToolSpec,
    record: ExecutionRecord,
    evidence: PostEvidence,
    *,
    workspace: Optional[Path | str],
) -> tuple[ValidatorOutcome, CheckResult]:
    if name == "file_changed":
        target = file_target(request)
        effect = evidence.file(target) if target else None
        if effect is None:
            return _outcome(name, False, "没有收集到文件证据：目标路径缺失或工作区未声明")
        if not effect.baseline_recorded:
            # 没有执行前基线时的"变了"是猜测，不是证据：宁可判需要修复。
            return _outcome(name, False, "缺少执行前基线：无法证明这次动作产生了什么效果")
        if record.status is ExecutionStatus.DELEGATED and evidence.files and effect.changed:
            return _outcome(name, True, f"{effect.path} 哈希已变化")
        if effect.changed:
            return _outcome(name, True, f"{effect.path} 哈希已变化")
        return _outcome(
            name,
            False,
            f"{effect.path} 在执行前后没有任何变化：工具声称成功但目标未改变",
        )

    if name == "content_matches":
        target = file_target(request)
        if target is None or workspace is None:
            return _outcome(name, True, "非文件动作，跳过内容一致性检查")
        effect = evidence.file(target)
        if effect is None or not effect.exists_after:
            return _outcome(name, False, f"{target} 在执行后不存在：动作没有产生它声称的结果")
        content = (Path(workspace) / target).read_text(encoding="utf-8", errors="replace")
        expected = request.value_of("content")
        if isinstance(expected, str):
            if content == expected:
                return _outcome(name, True, f"{target} 与请求声明的写入内容一致")
            return _outcome(
                name,
                False,
                f"{target} 的内容与请求声明的 content 不一致（工具声称成功，目标却不是那个结果）",
            )
        new = request.value_of("new_string")
        old = request.value_of("old_string")
        if isinstance(new, str) and new and new not in content:
            return _outcome(name, False, f"{target} 里没有出现请求声明的 new_string")
        if isinstance(old, str) and isinstance(new, str) and old != new and not effect.changed:
            return _outcome(name, False, f"{target} 没有变化，替换结果无迹可循")
        return _outcome(name, True, f"{target} 与请求声明的变更一致")

    if name == "file_syntax":
        target = file_target(request)
        effect = evidence.file(target) if target else None
        if effect is None or not effect.exists_after:
            return _outcome(name, True, "目标不存在，跳过语法检查")
        if workspace is None or target is None or not target.endswith(".py"):
            return _outcome(name, True, "非 Python 目标，Phase 4 不做语法检查")
        content = (Path(workspace) / target).read_text(encoding="utf-8", errors="replace")
        try:
            ast.parse(content)
        except SyntaxError as error:
            return _outcome(name, False, f"{target}:{error.lineno} 语法错误：{error.msg}")
        return _outcome(name, True, f"{target} 语法解析通过")

    if name == "diff_recorded":
        target = file_target(request)
        effect = evidence.file(target) if target else None
        if effect is None or not effect.changed:
            return _outcome(name, True, "没有变化，无需 diff")
        if not effect.diff_digest:
            return _outcome(name, False, "目标发生变化但没有记录 diff 摘要")
        return _outcome(name, True, f"diff_digest={effect.diff_digest}")

    if name == "exit_code_zero":
        process = evidence.process
        if process is None:
            return _outcome(name, False, "没有进程证据：无法证明命令成功")
        if process.timed_out:
            return _outcome(name, False, "命令超时被终止：不能当作成功")
        if process.exit_code is None:
            return _outcome(name, False, "命令没有退出码：结果不可判定")
        if process.exit_code != 0:
            return _outcome(name, False, f"退出码 {process.exit_code}")
        return _outcome(name, True, "退出码 0")

    if name == "target_exists":
        target = file_target(request)
        effect = evidence.file(target) if target else None
        if effect is None:
            return _outcome(name, False, "没有文件证据")
        if effect.exists_after:
            return _outcome(name, True, f"{effect.path} 存在")
        return _outcome(name, False, f"{effect.path} 不存在")

    return _outcome(name, False, f"未知验证器 {name!r}：注册表加载阶段本应拦下它")


def _outcome(name: str, passed: bool, detail: str) -> tuple[ValidatorOutcome, CheckResult]:
    reason = ReasonCode.ALLOW if passed else ReasonCode.POST_CHECK_FAILED
    status = CheckStatus.PASSED if passed else CheckStatus.FAILED
    return (
        ValidatorOutcome(
            validator=name,
            status=status,
            detail=detail,
            evidence_digest=digest_of({"validator": name, "detail": detail}),
        ),
        CheckResult(check=name, status=status, reason_code=reason, detail=detail),
    )


def restore_snapshot(snapshot: FileSnapshot, *, workspace: Optional[Path | str]) -> RollbackOutcome:
    """按快照回滚：恢复原内容，或删除本次新建的文件。"""

    if workspace is None:
        return RollbackOutcome(
            mode=RollbackMode.FILE_SNAPSHOT, status="unsupported", detail="没有受控工作区，无法回滚"
        )
    root = Path(workspace).resolve()
    target = (root / snapshot.path).resolve()
    if root != target and root not in target.parents:
        return RollbackOutcome(
            mode=RollbackMode.FILE_SNAPSHOT, status="failed", detail="目标逃出工作区，拒绝回滚"
        )
    try:
        if snapshot.existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(snapshot.content)
            return RollbackOutcome(
                mode=RollbackMode.FILE_SNAPSHOT,
                status="applied",
                detail=f"已恢复 {snapshot.path} 的 {snapshot.size} 字节",
                restored=(snapshot.path,),
            )
        if target.exists():
            target.unlink()
        return RollbackOutcome(
            mode=RollbackMode.FILE_SNAPSHOT,
            status="applied",
            detail=f"已删除本次新建的 {snapshot.path}",
            restored=(snapshot.path,),
        )
    except OSError as error:
        return RollbackOutcome(
            mode=RollbackMode.FILE_SNAPSHOT, status="failed", detail=f"回滚失败：{error}"
        )

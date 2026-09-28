"""pytest 适配器：最小相关测试的选择 + 运行结果 → 统一证据。

它同时服务两个 checker：

- missing_tests：变更集里的生产文件找不到任何相关测试（在选择阶段就能判定）；
- failing_tests：选中的测试跑失败了（按失败用例逐条产出证据）。

退出码 2（收集失败）分成三种处置（Q7，08 号报告 §5 Q1 / 14 号报告 §5 Q7）：

| 形态 | 处置 |
| --- | --- |
| 收集失败，且原因是**项目内**某模块/名字在本次树里还不存在 | pending_implementation（待实现） |
| 收集失败，但原因是第三方包 / 语法错误 / 环形导入 / 目标解析不出 | failing_tests 的**真违规** |
| 退出码 2 但输出里没有收集失败原文；以及超时 / 被杀 / 工具缺失 | 保持 crashed / unavailable（失败关闭） |

第一条不是"放宽"：它只覆盖"这次要写的实现还没落地"这一种形状，而且要求能**证明**缺失
目标属于项目内（顶层包在树里、模块或名字不在）——证明不了就一律落回真违规。
它产出的是 warning（allow_with_warnings），不是 allow：账本必须读得出"覆盖它的测试尚未运行"。

限制与隔离：只跑选中的 node id（上限来自 test-layout.yaml），禁用缓存插件、清空 addopts、
限时限量，环境变量只保留白名单，超时终止整棵进程树。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

from policy.evidence import (
    EvidenceLocation,
    PendingImplementation,
    ValidationEvidence,
    ValidatorStatus,
)
from policy.models import PolicyContextError, Rule, normalize_repo_path

from ..depgraph import build_module_index
from ..models import ProjectProfile, TestLayout, ValidatorSpec
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
    tool_label,
)

__all__ = [
    "COLLECTION_FAILURE",
    "FAILED_RE",
    "PENDING_IMPLEMENTATION",
    "CollectionBlock",
    "CollectionDiagnosis",
    "diagnose_collection_failure",
    "run_pytest",
    "selection_payload",
]

FAILED_RE = re.compile(r"^(?P<kind>FAILED|ERROR)\s+(?P<nodeid>[^\s]+)(?:\s+-\s+(?P<message>.*))?$")

# 收集失败的两个判定口径（"待实现" / "真违规"）：它们是**状态值**，不是布尔——
# 读的人（与账本）必须分得开"这次的树还在构建中"与"这个测试真的跑不起来"。
PENDING_IMPLEMENTATION = "pending_implementation"
COLLECTION_FAILURE = "collection_failure"

# 收集失败影响的 checker 是 failing_tests（"选中的测试跑失败了"）。missing_tests 的证据来自
# 选择阶段（selection.missing），与 pytest 能不能收集无关，因此不受这条状态影响。
FAILING_TESTS_CHECKER = "failing_tests"

# pytest 收集失败的原文形态（真机读数：.tmp/round-15/fix-tdd-state/red-pytest-shapes.txt）。
# 头部是 "______ ERROR collecting tests/test_x.py ______"；路径里可能出现下划线，
# 所以只切右侧的装饰下划线，不吞掉路径本身的字符。
_COLLECT_HEADER_RE = re.compile(r"ERROR collecting\s+(?P<module>\S+)")
_MISSING_MODULE_RE = re.compile(
    r"ModuleNotFoundError: No module named ['\"](?P<module>[^'\"]+)['\"]"
)
_MISSING_NAME_RE = re.compile(
    r"ImportError: cannot import name ['\"](?P<name>[^'\"]+)['\"]"
    r" from ['\"](?P<module>[^'\"]+)['\"]"
)
# 环形导入：名字**在**模块里，只是模块还没初始化完。它是真问题，绝不能算"待实现"。
_CIRCULAR_RE = re.compile(r"partially initialized module|circular import", re.IGNORECASE)
# conftest 加载失败：pytest 以退出码 4 收场、stdout 全空、理由只在 stderr 里（真机实测：
# .tmp/round-15/fix-tdd-state/red-conftest-shape.txt）。它是"整套测试跑不起来"，
# 因此永远算真违规、绝不判"待实现"——把它算成"待实现"会让整批测试的不可运行被一句
# warning 盖过去。
_CONFTEST_LOAD_RE = re.compile(r"ImportError while loading conftest ['\"](?P<path>[^'\"]+)['\"]")
# 收集期失败的退出码：2 = 收集失败（pytest 自己的口径），4 = 用法/内部错误
# （conftest 加载失败走这一条）。其它退出码一律保持原来的失败关闭分类。
_COLLECTION_EXIT_CODES: Tuple[int, ...] = (2, 4)
# 异常行：形如 "E   ModuleNotFoundError: No module named 'x'"（"ImportError while importing…"
# 这种叙述句没有紧跟冒号的异常名，不会被它命中）。
_EXCEPTION_LINE_RE = re.compile(r"\b\w*(?:Error|Exception)\b\s*:")


@dataclass(frozen=True)
class CollectionBlock:
    """一条收集失败记录：哪个测试模块、哪一类原因、缺了什么、原文摘要。

    test_module 为 None 表示"连是哪个测试模块都读不出来"（路径不规范 / 是绝对路径且
    归一化失败）：这种形状**不允许**判成"待实现"——说不出"哪条测试跑不了"的放行没有理由。
    """

    test_module: Optional[str]
    kind: str  # missing_module | missing_name | other
    target: str  # "shop.x" / "shop.x:Name" / ""
    excerpt: str


@dataclass(frozen=True)
class CollectionDiagnosis:
    """一次收集失败的判定结果（PENDING_IMPLEMENTATION 或 COLLECTION_FAILURE）。"""

    verdict: str
    test_modules: Tuple[str, ...]
    missing_targets: Tuple[str, ...]
    blocks: Tuple[CollectionBlock, ...]
    reason: str
    fix: str


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

    # missing_tests.changed_only=false 表示这条规则不依赖变更集：即使没有变更集，
    # 也要对目标文件本身判"有没有对应测试"（默认 true，则必须知道这次改了什么）。
    changed_only = any(
        getattr(rule.rule, "missing_tests", None) is not None
        and rule.rule.missing_tests.changed_only
        for rule in rules
    )
    selection = select_tests(
        target_path=target_path,
        changed_files=changed_files if changed_only or changed_files else (target_path,),
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
    invocation_tool = tool_label(spec.tool, python=python)

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
        diagnosis = diagnose_collection_failure(
            run.stdout + chr(10) + run.stderr,
            exit_code=run.exit_code,
            workspace=workspace,
            project=config.project,
            limit=max_message_chars,
        )
        if diagnosis is None:
            # 判不了（输出里没有收集失败原文 / 工具根本没跑成）：保持失败关闭，绝不猜成"待实现"。
            return AdapterResult(
                status=run.status,
                tool=invocation,
                reason=run.reason,
                payload={"selection": selection.to_payload()},
            )
        if diagnosis.verdict == PENDING_IMPLEMENTATION:
            # Q7：这次的树还在构建中。**不进 served_checkers**（没查成的不能记成查过了），
            # **不产生 Blocker**（否则"先写测试"又会被拦）；由判定侧产出 warning。
            return AdapterResult(
                status=ValidatorStatus.PENDING_IMPLEMENTATION,
                evidence=tuple(sorted(evidence, key=lambda item: item.sort_key)),
                tool=invocation,
                reason=diagnosis.reason,
                payload={"selection": selection.to_payload()},
                pending=(
                    PendingImplementation(
                        validator_id=spec.id,
                        validator_version=spec.version,
                        checkers=(FAILING_TESTS_CHECKER,),
                        test_modules=diagnosis.test_modules,
                        missing_targets=diagnosis.missing_targets,
                        reason=diagnosis.reason,
                        fix=diagnosis.fix,
                    ),
                ),
            )
        # 真违规：收集失败是被测代码这一侧的问题（第三方包缺失 / 语法错误 / 环形导入…），
        # 不是"关键验证器不可用"。证据按普通路径交给引擎，severity 取规则自己的级别。
        evidence.extend(
            _collection_failure_evidence(
                diagnosis,
                rules=rules,
                target_path=target_path,
                tool=invocation,
            )
        )
        return AdapterResult(
            status=ValidatorStatus.FINDINGS if evidence else ValidatorStatus.OK,
            evidence=tuple(sorted(evidence, key=lambda item: item.sort_key)),
            tool=invocation,
            reason=diagnosis.reason,
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


# ------------------------------------------------------------------ 收集失败的三分（Q7）


def diagnose_collection_failure(
    text: str,
    *,
    exit_code: Optional[int],
    workspace: Path,
    project: ProjectProfile,
    limit: int = 600,
) -> Optional[CollectionDiagnosis]:
    """一次非零退出是不是"收集失败"，以及它是「待实现」还是真违规。

    返回 None = **判不了**（退出码不是 2，或输出里没有 `ERROR collecting` 原文）：
    调用方必须保持原来的失败关闭（crashed 等），绝不猜成"待实现"。

    "待实现"要求**每一条**收集失败都能被证明是"项目内还不存在"：
    任何一条落到第三方包、语法错误、环形导入、读不出目标或读不出测试模块，
    整次判定就是真违规。口径是**可能漏、不误报**——被误报的那一条会让一个真的跑不起来的
    测试以 warning 过关，那比"多花几分钟"危险得多（AGENTS 第 45 条的同一条纪律）。
    """

    if exit_code not in _COLLECTION_EXIT_CODES:
        return None
    blocks = _collect_blocks(text, workspace=workspace, limit=limit)
    conftest = _conftest_failure(text, workspace=workspace, limit=limit)
    if conftest is not None:
        # conftest 加载失败：它是真违规（整套测试跑不起来），把这条并进清单一起报。
        blocks = (conftest, *blocks)
    if not blocks:
        return None

    index = None
    if all(item.test_module is not None for item in blocks):
        try:
            index = build_module_index(workspace, project)
        except Exception:  # noqa: BLE001 - 建不出索引就证明不了"项目内还不存在"，落回真违规
            index = None

    missing: list[str] = []
    pending = index is not None
    for item in blocks:
        target = (
            None
            if index is None or item.test_module is None
            else _pending_target(item, index=index, workspace=workspace)
        )
        if target is None:
            pending = False
        else:
            missing.append(target)

    test_modules = tuple(sorted({item.test_module for item in blocks if item.test_module}))
    if pending and missing:
        targets = tuple(sorted(set(missing)))
        return CollectionDiagnosis(
            verdict=PENDING_IMPLEMENTATION,
            test_modules=test_modules,
            missing_targets=targets,
            blocks=blocks,
            reason=(
                "待实现：选中的测试 " + ", ".join(test_modules) + " 在收集期就失败了——"
                "它 import 的 " + ", ".join(targets) + " 属于项目内、但在本次取证树里还不存在。"
                "这不是测试失败（断言一条都没跑），而是这次的树还在构建中；"
                "本次写入被放行，覆盖它的测试尚未能运行"
            ),
            fix=(
                "先把 " + ", ".join(targets) + " 真正落地（目标模块文件，或模块里那个名字）"
                "再重跑取证；本次放行只说明「待实现」，测试是否通过要由后续动作的取证"
                "与 PostToolUse 事后核对重新算"
            ),
        )
    return CollectionDiagnosis(
        verdict=COLLECTION_FAILURE,
        test_modules=test_modules,
        missing_targets=(),
        blocks=blocks,
        reason=(
            "测试模块收集失败（pytest 退出码 2，不是断言失败）："
            + "；".join(_block_label(item) for item in blocks)
            + "。收集失败说明被测代码这一侧有问题（第三方依赖缺失 / 语法错误 / 环形导入 / "
            "conftest 或配置出错 / 目标读不出来都算）；它不是「关键验证器不可用」"
        ),
        fix="",
    )


def _collect_blocks(
    text: str, *, workspace: Path, limit: int
) -> Tuple[CollectionBlock, ...]:
    """把 pytest 输出切成一条条收集失败记录（按 `ERROR collecting` 头部切）。"""

    blocks: list[CollectionBlock] = []
    current: Optional[Tuple[Optional[str], list[str]]] = None
    for line in text.splitlines():
        match = _COLLECT_HEADER_RE.search(line)
        if match is not None:
            if current is not None:
                blocks.append(
                    _classify_block(current[0], current[1], workspace=workspace, limit=limit)
                )
            module = _normalize_test_module(match.group("module"), workspace=workspace)
            current = (module, [])
            continue
        if current is not None:
            current[1].append(line)
    if current is not None:
        blocks.append(_classify_block(current[0], current[1], workspace=workspace, limit=limit))
    return tuple(blocks)


def _conftest_failure(text: str, *, workspace: Path, limit: int) -> Optional[CollectionBlock]:
    """conftest 加载失败 → 一条显式的收集失败记录（永远不是"待实现"）。

    真机形态（pytest 9.1.1）：stdout 全空、退出码 4、理由在 stderr——
    `ImportError while loading conftest '<abs>'` + traceback。它说明**整套测试**跑不起来，
    所以按真违规处理：绑 failing_tests 规则、severity 取规则自己的级别。
    """

    match = _CONFTEST_LOAD_RE.search(text)
    if match is None:
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    return CollectionBlock(
        _normalize_test_module(match.group("path"), workspace=workspace),
        "conftest",
        "",
        _collect_excerpt(lines, workspace=workspace, limit=limit),
    )


def _classify_block(
    test_module: Optional[str], lines: Sequence[str], *, workspace: Path, limit: int
) -> CollectionBlock:
    """一个收集失败块 → 原因类别 + 缺失目标 + 原文摘要。"""

    body = chr(10).join(lines)
    excerpt = _collect_excerpt(lines, workspace=workspace, limit=limit)
    if _CIRCULAR_RE.search(body):
        # 环形导入：名字往往**在**模块里，只是模块还没初始化完。它是真问题。
        return CollectionBlock(test_module, "other", "", excerpt)
    match = _MISSING_NAME_RE.search(body)
    if match is not None:
        return CollectionBlock(
            test_module,
            "missing_name",
            match.group("module") + ":" + match.group("name"),
            excerpt,
        )
    match = _MISSING_MODULE_RE.search(body)
    if match is not None:
        return CollectionBlock(test_module, "missing_module", match.group("module"), excerpt)
    return CollectionBlock(test_module, "other", "", excerpt)


def _pending_target(
    block: CollectionBlock, *, index: object, workspace: Path
) -> Optional[str]:
    """这条收集失败是不是"项目内还不存在"？证明不了就返回 None（落回真违规）。

    两条口径都要求**项目内**先成立，且本次树里确实没有：

    - 模块缺失：顶层包已经在这棵树里（`index.top_levels`），但这个模块不在索引里；
      顶层包不在树里的一律不报——它可能是第三方，也可能是还没写的包（可能漏、不误报）；
    - 名字缺失：模块在索引里（`index.modules`），而这个名字在它的源码里**任何位置**
      都没出现（定义 / 导入 / 赋值 / 参数都算"出现"）。证明不了就当"存在"。
    """

    if block.kind == "missing_module":
        module = block.target
        top = module.split(".")[0]
        if top in index.top_levels and module not in index.modules:  # type: ignore[attr-defined]
            return module
        return None
    if block.kind == "missing_name":
        module, _, name = block.target.partition(":")
        path = index.modules.get(module)  # type: ignore[attr-defined]
        if path is None:
            return None
        if _module_binds_name(workspace / path, name):
            return None
        return block.target
    return None


def _module_binds_name(path: Path, name: str) -> bool:
    """模块源码里是否出现过这个名字（出现即算"有"，宁可不报）。

    读不到 / 不是 UTF-8 / 解析不了一律返回 True："证明不了"不能变成"那就当它没有"。
    """

    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return True
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                return True
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.asname == name:
                    return True
                if alias.asname is None and alias.name.split(".")[-1] == name:
                    return True
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if node.id == name:
                return True
        elif isinstance(node, ast.arg) and node.arg == name:
            return True
    return False


def _normalize_test_module(token: str, *, workspace: Path) -> Optional[str]:
    """测试模块 token → 仓库相对路径；归一化不了返回 None（该块不许判"待实现"）。

    口径与平台的 `policy.models.normalize_repo_path` 完全一致（证据里不许出现绝对路径、
    上跳或路径元字符），不在这里另写一套。
    """

    candidate = token.strip().rstrip("_.:").replace("\\", "/")
    if not candidate or candidate.startswith("-"):
        return None
    if re.match(r"^[A-Za-z]:", candidate) or candidate.startswith("/"):
        try:
            candidate = (
                Path(candidate).resolve().relative_to(Path(workspace).resolve()).as_posix()
            )
        except (OSError, ValueError):
            return None
    try:
        # 复用平台唯一的路径口径：绝对路径、上跳、路径元字符一律在这里被拒，
        # 返回 None → 这一块不参与"待实现"，证据位置回退到目标文件。
        return normalize_repo_path(candidate)
    except PolicyContextError:
        return None


def _collect_excerpt(lines: Sequence[str], *, workspace: Path, limit: int) -> str:
    """块内的可读摘要：优先"异常那一行"，没有就取第一行非空内容（脱敏后）。"""

    text = ""
    for raw in lines:
        stripped = raw.strip()
        if stripped and _EXCEPTION_LINE_RE.search(stripped):
            text = stripped
            break
    if not text:
        for raw in lines:
            stripped = raw.strip()
            if stripped:
                text = stripped
                break
    return sanitize_text(text, workspace=workspace, limit=limit)


def _block_label(block: CollectionBlock) -> str:
    where = block.test_module or "<未知测试模块>"
    return where + "：" + block.excerpt


def _collection_failure_evidence(
    diagnosis: CollectionDiagnosis,
    *,
    rules: Sequence[Rule],
    target_path: str,
    tool: object,
) -> Tuple[ValidationEvidence, ...]:
    """收集失败 → failing_tests 的**真违规**（severity 取规则自己的级别）。

    它不是"关键验证器不可用"：工具跑成了、也说了为什么，问题在被测代码这一侧。
    所以这里走普通证据路径（status=findings），由引擎按正常规则判定——该阻断就阻断。
    """

    owners = [rule for rule in rules if getattr(rule.rule, "failing_tests", None) is not None]
    if not owners:
        return ()
    evidence: list[ValidationEvidence] = []
    for block in diagnosis.blocks:
        where = block.test_module or "<未知测试模块>"
        for rule in owners:
            evidence.append(
                ValidationEvidence(
                    validator_id="tool.pytest",
                    validator_version="1.0",
                    checker=FAILING_TESTS_CHECKER,
                    rule_id=rule.id,
                    rule_version=rule.version,
                    severity=rule.severity,
                    message="测试模块收集失败（不是断言失败）：" + where + "：" + block.excerpt,
                    value=block.test_module or FAILING_TESTS_CHECKER,
                    location=EvidenceLocation(
                        file=block.test_module or target_path, line=None, column=None
                    ),
                    tool=tool,
                )
            )
    return tuple(sorted(evidence, key=lambda item: item.sort_key))


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

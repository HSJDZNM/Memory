r"""C3 最终树门禁 v1：对一棵树跑规则集 + 真实验证器，把 violations 汇总成门禁结论。

它是什么
========

05 §4 C3 的落地件之一，回答的问题只有一句：**这棵树（最终产物）上，规则集的 error 级违规
是否为 0**。v1 只做两件事：

1. **整树判定**：枚举树内受规则覆盖的文件，逐个构造与 python -m policy.check 同口径的
   PolicyContext，跑**真实验证器流水线**取证据，交给 policy.engine.evaluate；
2. **规则集哈希钉住**：--pin 写钉住文件，--check 比对，漂移即退出码 1。

**v1 不含「危险动作前置阻断」**（删除 / 执行 / 控制面写的前置阻断），那要等 B1/B3 之后
单独一轮；本工具**只读**，不写审计、不改任何 allow / block。

不重写判定，不重写取证
======================

- 判定只有一条路径：policy.engine.evaluate(rules, context, evidence=...)；
- 证据只有一条路径：policy.check.collect_evidence -> validators.pipeline.run_pipeline
  （真调用 Ruff / pytest 等，不 mock、不伪造证据）；
- 上下文只有一条路径：policy.check.build_context_args（层与层来源、路径规范化、changed
  的失败关闭边界都沿用 CLI 的实现）。本工具自己**不做**规则匹配、不做诊断归属、不算 decision。

分层 / 语言 / 规则目录的口径来自 --config <adapter 配置>（例如
<project>/.policy/dsh-adapter.yaml）：

- layers：按声明顺序取第一个命中（AdapterConfig.layer_resolution，与 Hook 路径同一份实现）；
  命中不了时退回 policy.check.resolve_layer 的既定顺序（平台 test-layout -> 文件名推断），
  并把 layer_origin 写进读数——**猜出来的层与声明的层必须能分开读**；
- languages / default_language：目标文件的语言；
- rules：默认规则目录（--rules 可覆盖）。

枚举与排除口径
==============

不给 --changed 时按 --all 枚举：

- 树遍历的排除清单是 provenance.worktree.DEFAULT_EXCLUDES（.git / .tmp / .venv /
  __pycache__ / 各类缓存等，**同一份声明**也是树摘要的口径），命中即**不再走进去**；
- 语言覆盖由数据决定：adapter 配置声明了语言、且 validation/validators.yaml 里有该语言的
  rule pack 才算「受规则覆盖」；uncovered_languages 里声明的语言按「按设计不取证」排除，
  未声明语言 / 没有 rule pack 的文件也排除——**排除项与逐类计数都写进读数**，
  「没查」不许读成「查过且干净」；
- --changed 是显式目标集：不受排除清单限制（显式指定的文件必须被判定，不能被悄悄丢掉），
  但必须落在 --workspace 之内、必须存在、adapter 配置必须为它声明语言，否则退出码 2。

退出码（照 tools/README.md 的「门禁退出码」表，失败关闭）
======================================================

- 0：所有文件都没有 **error / critical 级**违规。warning 级进入清单但**不**让门禁失败
  （此时文件的 decision 可能是 allow_with_warnings，这是引擎的既定口径）；
- 1：有 error / critical 级违规，**或**规则集漂移（--check）；
- 2：无法完成判定——adapter 配置读不到、验证器配置读不到、规则集加载失败、验证器不可用、
  证据缺失、树摘要证明不了、--changed 不合法、枚举结果为 0（没有可判定对象）。
  **「跑不了」绝不记成 0**。

--pin 只写钉住文件（不枚举树，写完退 0）；--check 是**叠加**在本次判定上的比对
（漂移与违规同时存在时退出码按 2 > 1 > 0 的优先级取）。

--json 载荷（AGENTS 第 55 条）
============================

FINAL_TREE_GATE_SCHEMA_VERSION = "1.0"——**首次建轴**（2026-10-20，C3 v1）：
workspace_scope / rule_set / files / violations / violations_by_severity / counts /
coverage / gate / reading_context。加键或改语义必须显式递增。

**没有时戳、没有 run 标识、没有绝对路径、没有耗时**：它是输入的纯函数，相同输入两次运行
逐字节相同（与 policy.check.OUTPUT_SCHEMA_VERSION 1.2 的同一条纪律）。reading_context
复用 provenance.reading_context 的统一形状（source = gate，include_run=False；
host.sandbox 读不到就是 unknown，不是「没有沙箱」，也不写 not_applicable 冒充）。

已知边界（写在这里，不让读者从输出反推）
======================================

- 每个目标文件各跑一次完整流水线（含外部工具），**大树很慢**；需要窄口径时用 --changed；
- RuleSet.identity 只覆盖**规则内容**（模型序列化后的稳定哈希）：改规则文件里的注释 / 空白
  不会漂移；「规则集换了加载顺序」按它的既定口径**不是**漂移（identity 与加载顺序无关），
  本工具不另造一个顺序敏感的哈希；
- 文件名推断出来的层（layer_origin=filename_guess）与 adapter 配置没声明语言的路径，
  都按 policy.check 的既定口径继续判定并在读数里标出来——v1 不因此让门禁失败；
- check_volume 的统计量按 policy.check.build_check_volume 现算；complete=false
  （缺维度）在 v1 里**只报告、不改变退出码**；
- 本工具不启动 dsh、不读审计/台账、不做任何写类动作。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from adapters.dsh.adapter import DshEventError  # noqa: E402
from adapters.dsh.adapter import load_config as load_adapter_config  # noqa: E402
from enforcement.audit import redact_text  # noqa: E402
from policy import check as policy_check  # noqa: E402
from policy.checkers import CONTEXT_CHECKERS  # noqa: E402
from policy.engine import EngineError, evaluate, matching_rules  # noqa: E402
from policy.loader import LoaderError, load_rule_set  # noqa: E402
from policy.models import BLOCKING_SEVERITIES, Decision, Severity  # noqa: E402
from provenance import reading_context as reading  # noqa: E402
from provenance.worktree import (  # noqa: E402
    DEFAULT_EXCLUDES,
    ProvenanceError,
    workspace_tree_digest,
)
from validators.globs import glob_match  # noqa: E402
from validators.registry import RegistryError  # noqa: E402
from validators.registry import load_config as load_validation_config  # noqa: E402

# 本载荷自己的版本轴（AGENTS 第 55 条）：**首次出现就带轴**。
FINAL_TREE_GATE_SCHEMA_VERSION = "1.0"

# 钉住文件自己的版本轴：它比门禁载荷更长寿（会被别的轮的树复用），所以各走各的。
PIN_SCHEMA_VERSION = "1.0"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_UNAVAILABLE = 2

#: 会被写进 --json 的 decision 计数键（键集合固定，不随本次结果增减）。
DECISIONS: tuple[str, ...] = tuple(item.value for item in Decision)

#: 按 severity 的计数字典：四个键恒定出现（0 也要写），读的人不必靠缺席去猜。
SEVERITIES: tuple[str, ...] = tuple(item.value for item in Severity)

#: 枚举排除的类别：与 DEFAULT_EXCLUDES 一起写进读数；四类恒定出现。
EXCLUSION_REASONS: tuple[str, ...] = (
    "excluded_by_glob",
    "language_undeclared",
    "language_not_covered_by_design",
    "language_without_rule_pack",
)

#: 层的来源：前三个直接复用 policy.check 的常量，第四个是本工具自己的名字。
LAYER_SOURCE_ADAPTER_CONFIG = "adapter_config"

GATE_OK = "pass"
GATE_FAIL = "fail"
GATE_UNAVAILABLE = "unavailable"
GATE_PINNED = "pinned"

PIN_FILE_REASON = "--pin 只写规则集钉住文件，没有枚举树"


class GateError(Exception):
    """无法完成判定（退出码 2）：读不到、装不起来、目标不合法、枚举为空。

    与「发现违规」必须能分开——两者都被读成 1 时调用方读不出「这次到底判没判」。
    消息里尽量用可读标签，路径由输出前的脱敏统一折叠。
    """


# --------------------------------------------------------------------------- 输出口径


def redact(text: Any) -> str:
    """输出口径的脱敏：先折叠绝对路径，再用运行期审计的同一份模式去密钥。"""

    return redact_text(reading.fold_absolute_paths(str(text), root=REPO))


def sanitize(value: Any) -> Any:
    """递归脱敏一个 JSON 值（与 tools/decision_diff.py 同口径，不另写一套）。"""

    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        result: dict = {}
        for key, item in value.items():
            name = redact(key)
            candidate = name
            suffix = 2
            while candidate in result:
                candidate = "%s#%d" % (name, suffix)
                suffix += 1
            result[candidate] = sanitize(item)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value


def dump_json(payload: Mapping[str, Any]) -> str:
    """稳定序列化：键排序 + 固定缩进 + 单尾换行，相同输入逐字节相同。"""

    return json.dumps(sanitize(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------- 规则集与钉住


def rule_set_payload(rules: Any) -> dict[str, Any]:
    """规则集的审计身份：identity 是 RuleSet 自己的稳定哈希（不是本工具另算的）。"""

    return {
        "count": len(rules),
        "decision_schema_version": _decision_schema_version(),
        "identity": rules.identity,
        "ids": list(rules.ids),
        "sources": list(rules.source_paths),
    }


def _decision_schema_version() -> str:
    from policy.models import SCHEMA_VERSION

    return SCHEMA_VERSION


def pin_payload(rules: Any) -> dict[str, Any]:
    return {"schema_version": PIN_SCHEMA_VERSION, "rule_set": rule_set_payload(rules)}


def write_pin(path: Path, rules: Any) -> None:
    """写钉住文件：UTF-8 / LF / 单尾换行；不含时戳、不含绝对路径、不含 run 标识。"""

    target = path.expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(pin_payload(rules), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as error:
        raise GateError("钉住文件写不了：" + redact(error)) from error


def read_pinned_identity(path: Path, *, label: str) -> str:
    """读钉住文件里的规则集身份；读不到 / 版本不认识 / 形状不对都是退出码 2。"""

    target = path.expanduser()
    if not target.is_file():
        raise GateError("钉住文件不存在：" + label)
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError("钉住文件读不懂：" + label + "（" + redact(error) + "）") from error
    if not isinstance(document, dict):
        raise GateError("钉住文件顶层必须是映射：" + label)
    version = document.get("schema_version")
    if version != PIN_SCHEMA_VERSION:
        raise GateError(
            "钉住文件的 schema_version 不认识："
            + repr(version)
            + "（本工具只接受 "
            + repr(PIN_SCHEMA_VERSION)
            + "）："
            + label
        )
    rule_set = document.get("rule_set")
    identity = rule_set.get("identity") if isinstance(rule_set, dict) else None
    if not isinstance(identity, str) or not identity:
        raise GateError("钉住文件缺少 rule_set.identity：" + label)
    return identity


# --------------------------------------------------------------------------- 输入解析


def resolve_config_root(value: str | None) -> Path:
    """--config-root 的解析与 policy.check 同源（锚是**仓库根**，不是 --workspace）。"""

    return policy_check.resolve_directory(value, anchor=REPO, fallback=REPO)


def load_adapter(path: Path) -> Any:
    try:
        return load_adapter_config(path)
    except DshEventError as error:
        raise GateError("adapter 配置不可用：" + str(error)) from error


def load_validation(config_root: Path) -> Any:
    try:
        return load_validation_config(root=config_root)
    except RegistryError as error:
        raise GateError("验证器配置不可用：" + str(error)) from error


def load_rules(args: argparse.Namespace, adapter: Any) -> Any:
    rule_dirs = (
        tuple(Path(item) for item in args.rules) if args.rules else tuple(adapter.rule_dirs)
    )
    try:
        return load_rule_set(rule_dirs, repo_root=REPO)
    except LoaderError as error:
        raise GateError("规则集加载失败：" + str(error)) from error


# --------------------------------------------------------------------------- 树枚举


def is_excluded(relative: str) -> bool:
    """命中 DEFAULT_EXCLUDES 的路径；目录按「名字」与「名字/」两种写法各试一次（同一口径）。"""

    for pattern in DEFAULT_EXCLUDES:
        if glob_match(pattern, relative) or glob_match(pattern, relative + "/"):
            return True
    return False


def language_exclusion(language: str | None, registry: Any) -> str | None:
    """语言的排除口径：None = 受 rule pack 覆盖；否则返回写进读数的类别。"""

    if not language:
        return "language_undeclared"
    if registry.packs_for(language):
        return None
    if registry.uncovered(language) is not None:
        return "language_not_covered_by_design"
    return "language_without_rule_pack"


def enumerate_tree(
    workspace: Path, adapter: Any, registry: Any
) -> tuple[list[str], dict[str, Any]]:
    """按 --all 枚举受规则覆盖的文件；返回 (目标相对路径, 排除读数)。"""

    excluded = {
        "globs": list(DEFAULT_EXCLUDES),
        "directories": 0,
        "files": 0,
        "by_reason": {name: 0 for name in EXCLUSION_REASONS},
    }
    found: list[str] = []

    def onerror(error: OSError) -> None:
        raise GateError("读不到目录（枚举不完整就不算数）：" + redact(error))

    for dirpath, dirnames, filenames in os.walk(workspace, onerror=onerror):
        here = Path(dirpath)
        kept: list[str] = []
        for name in sorted(dirnames):
            relative = _relative(here / name, workspace)
            if is_excluded(relative):
                excluded["directories"] += 1
                continue
            kept.append(name)
        dirnames[:] = kept

        for name in sorted(filenames):
            candidate = here / name
            if not candidate.is_file():
                continue
            relative = _relative(candidate, workspace)
            if is_excluded(relative):
                excluded["files"] += 1
                excluded["by_reason"]["excluded_by_glob"] += 1
                continue
            reason = language_exclusion(adapter.language_for(relative), registry)
            if reason is not None:
                excluded["by_reason"][reason] += 1
                continue
            found.append(relative)
    return sorted(found), excluded


def _relative(path: Path, root: Path) -> str:
    return Path(os.path.relpath(path, root)).as_posix()


def collect_targets(
    args: argparse.Namespace, workspace: Path, adapter: Any, registry: Any
) -> tuple[list[str], dict[str, Any]]:
    """目标集：--changed 显式列表，或 --all / 默认枚举；两者互斥，空集失败关闭。"""

    if args.changed is not None:
        if args.enumerate_all:
            raise GateError("--changed 与 --all 自相矛盾：声明了显式目标集又要求枚举整棵树")
        items = _split_changed(args.changed)
        if not items:
            raise GateError("--changed 解析后是空列表：空目标集不许读成「全部通过」")
        targets = _resolve_changed(workspace, items, adapter)
        return targets, {
            "globs": list(DEFAULT_EXCLUDES),
            "directories": 0,
            "files": 0,
            "by_reason": {name: 0 for name in EXCLUSION_REASONS},
        }
    targets, excluded = enumerate_tree(workspace, adapter, registry)
    if not targets:
        raise GateError(
            "枚举结果为 0 个受规则覆盖的文件：门禁没有可判定的对象，按无法完成判定处理"
            "（受规则覆盖 = adapter 配置声明了语言且 validators.yaml 有该语言的 rule pack）"
        )
    return targets, excluded


def _split_changed(values: Sequence[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        items.extend(part.strip() for part in str(value).split(",") if part.strip())
    return items


def _resolve_changed(workspace: Path, items: Sequence[str], adapter: Any) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for raw in items:
        token = str(raw).replace("\\", "/")
        if token.startswith("/") or (len(token) > 1 and token[1] == ":"):
            raise GateError("--changed 只接受工作区相对路径，拒绝绝对路径：" + token)
        if ".." in token.split("/"):
            raise GateError("--changed 不接受含 .. 的路径（越界一律拒绝）：" + token)
        candidate = workspace / token
        try:
            resolved = candidate.resolve()
            relative = resolved.relative_to(workspace).as_posix()
        except (OSError, ValueError) as error:
            raise GateError("--changed 目标越出 --workspace：" + token) from error
        if not resolved.is_file():
            raise GateError("--changed 目标不是文件：" + token)
        if relative in seen:
            continue
        seen.add(relative)
        language = adapter.language_for(relative)
        if not language:
            raise GateError(
                "adapter 配置没有为 " + relative + " 声明 language："
                "显式目标不能靠猜语言判定（AGENTS 核心约束 6）"
            )
        targets.append(relative)
    return sorted(targets)


# --------------------------------------------------------------------------- 单文件判定


def resolve_layer(
    *,
    workspace: Path,
    adapter: Any,
    relative: str,
    config_root: Path,
) -> tuple[str | None, str, str]:
    """定层与来源：adapter 声明 -> 平台 test-layout / 文件名推断（后两条走 policy.check）。

    返回 (显式传给 policy.check 的 layer 或 None, layer_source, layer_origin)。
    """

    resolution = adapter.layer_resolution(relative)
    if resolution.layer:
        origin = (
            LAYER_SOURCE_ADAPTER_CONFIG + "_default"
            if resolution.defaulted
            else LAYER_SOURCE_ADAPTER_CONFIG
        )
        return resolution.layer, policy_check.LAYER_SOURCE_DECLARED, origin
    # 没有声明：把「层怎么定」交给 policy.check 的唯一实现（平台 test-layout -> 文件名推断）。
    from policy.models import PolicyContextError

    namespace = argparse.Namespace(
        file=str(workspace / relative),
        layer=None,
        config_root=str(config_root),
    )
    try:
        layer, source = policy_check.resolve_layer(
            namespace, anchor=workspace, root=REPO, file_path=workspace / relative
        )
    except (RegistryError, PolicyContextError) as error:
        raise GateError("定层失败：" + str(error)) from error
    return layer, source, source


def _context_request_id(relative: str) -> str:
    """确定性的 request_id：两次运行必须逐字节相同（载荷里不许有随机量）。"""

    digest = hashlib.sha256(
        ("final-tree-gate/1.0\x00" + relative).encode("utf-8")
    ).hexdigest()
    return "ftg-" + digest[:16]


def _violation_payload(violation: Any, relative: str) -> dict[str, Any]:
    evidence = violation.evidence
    return {
        "evidence": {
            "detail": evidence.detail,
            "kind": evidence.kind,
            "subject": evidence.subject,
            "value": evidence.value,
        },
        "file": relative,
        "message": violation.message,
        "rule_id": violation.canonical_id,
        "rule_version": violation.rule_version,
        "severity": violation.severity.value,
    }


def _checker_evidence_gaps(bundle: Any, rules: Any, context: Any) -> list[dict[str, Any]]:
    """结构性回答「有 checker 拿不到证据吗」：读 engine 的匹配结果与证据包，不解析文本。"""

    gaps: list[dict[str, Any]] = []
    covered: set[str] = set()
    for blocker in bundle.blockers:
        for checker in blocker.checkers:
            if checker in covered:
                continue
            covered.add(checker)
            gaps.append(
                {
                    "checker": checker,
                    "kind": "blocker",
                    "reason": blocker.reason,
                    "status": blocker.status.value,
                    "validator": blocker.validator,
                }
            )
    matched, _skipped = matching_rules(rules, context)
    needed = sorted(
        {
            rule.enforcement.checker
            for rule in matched
            if rule.enforcement.checker
            and rule.enforcement.checker not in CONTEXT_CHECKERS
        }
    )
    for checker in needed:
        if checker in covered:
            continue
        if bundle.serves(checker) or bundle.pending_for(checker):
            continue
        gaps.append(
            {
                "checker": checker,
                "kind": "no_evidence",
                "reason": "没有任何验证器为 checker " + checker + " 提供证据（证据缺失，失败关闭）",
                "status": None,
                "validator": None,
            }
        )
    return gaps


def evaluate_file(
    args: argparse.Namespace,
    *,
    workspace: Path,
    adapter: Any,
    rules: Any,
    config_root: Path,
    relative: str,
    changed: Sequence[str],
) -> dict[str, Any]:
    """判定一个目标文件：policy.check 的上下文 + 真实验证器流水线 + 唯一判定入口。"""

    explicit_layer, expected_source, origin = resolve_layer(
        workspace=workspace,
        adapter=adapter,
        relative=relative,
        config_root=config_root,
    )
    language = adapter.language_for(relative)

    argv: list[str] = [
        str(workspace / relative),
        "--workspace",
        str(workspace),
        "--config-root",
        str(config_root),
        "--operation",
        args.operation,
        "--request-id",
        _context_request_id(relative),
    ]
    if explicit_layer:
        argv.extend(["--layer", explicit_layer])
    argv.extend(["--language", language or ""])
    for item in changed:
        argv.extend(["--changed", item])
    if args.validators:
        argv.extend(["--validators", args.validators])

    namespace = policy_check.build_parser().parse_args(argv)
    context, layer_source = policy_check.build_context_args(namespace, REPO)
    report = policy_check.collect_evidence(namespace, anchor=REPO, context=context, rules=rules)
    bundle = report.bundle
    result = evaluate(rules, context, evidence=bundle)

    gaps = _checker_evidence_gaps(bundle, rules, context)
    volume = policy_check.build_check_volume(rules, context, result, evidence=bundle)
    violations = [_violation_payload(item, relative) for item in result.violations]
    pending = [_violation_payload(item, relative) for item in result.pending_findings]

    return {
        "check_volume": {
            "blocking_capable_skipped": volume["blocking_capable_skipped"],
            "complete": volume["complete"],
            "missing_dimensions": list(volume["missing_dimensions"]),
            "served_checkers": list(volume["served_checkers"]),
            "skipped_by_reason": dict(volume["skipped_by_reason"]),
            "skipped_rule_count": volume["skipped_rule_count"],
        },
        "decision": result.decision.value,
        "evidence": {
            "blockers": [item.to_payload() for item in report.blockers],
            "gaps": gaps,
            "judgements": [item.to_payload() for item in report.judgements],
            "language_coverage": dict(report.language_coverage),
            "pending_implementation": [
                item.to_payload() for item in report.pending_implementation
            ],
            "pipeline_schema_version": report.schema_version,
            "served_checkers": list(report.served_checkers),
            "truncated_evidence": report.truncated_evidence,
            "unmapped_findings": report.unmapped_findings,
            "validators": [
                {
                    "reason": item.reason,
                    "status": item.status.value,
                    "validator": item.validator,
                }
                for item in report.validators
            ],
        },
        "file": relative,
        "language": context.language,
        "layer": context.layer,
        "layer_origin": origin,
        "layer_source": expected_source if explicit_layer else layer_source,
        "pending_findings": pending,
        "status": "evidence_unavailable" if gaps else "ok",
        "violations": violations,
    }


def _failed_file(relative: str, error: BaseException) -> dict[str, Any]:
    """单个文件判定失败：仍按同一形状交出记录，并让整次门禁按失败关闭收场。"""

    reason = type(error).__name__ + ": " + str(error)
    return {
        "check_volume": None,
        "decision": None,
        "evidence": {
            "blockers": [],
            "gaps": [
                {
                    "checker": None,
                    "kind": "exception",
                    "reason": reason,
                    "status": None,
                    "validator": None,
                }
            ],
            "judgements": [],
            "language_coverage": None,
            "pending_implementation": [],
            "pipeline_schema_version": None,
            "served_checkers": [],
            "truncated_evidence": 0,
            "unmapped_findings": 0,
            "validators": [],
        },
        "file": relative,
        "language": None,
        "layer": None,
        "layer_origin": None,
        "layer_source": None,
        "pending_findings": [],
        "status": "evidence_unavailable",
        "violations": [],
    }


# --------------------------------------------------------------------------- 载荷


def _reading_context(
    *,
    workspace: Path | None,
    digest: str | None,
    config_root: Path | None,
    adapter_path: Path | None,
) -> dict[str, Any]:
    """这份读数属于哪棵树 / 哪一套声明（provenance.reading_context 的统一形状）。

    三态纪律：读不到的声明写 unavailable + reason，树摘要没算写 unavailable；
    host.sandbox 由 host_block 默认成 unknown（本工具不探测沙箱）。**不写 run**。
    """

    declarations: dict[str, dict] = {}
    if config_root is not None:
        declarations[reading.DECLARATION_REGISTRY] = reading.declaration_block(
            config_root / "validation" / "validators.yaml", root=REPO
        )
        declarations[reading.DECLARATION_TEST_LAYOUT] = reading.declaration_block(
            config_root / "validation" / "test-layout.yaml", root=REPO
        )
    else:
        declarations[reading.DECLARATION_REGISTRY] = reading.unavailable(
            "验证器配置根未知：本次运行在读到配置之前就失败了"
        )
        declarations[reading.DECLARATION_TEST_LAYOUT] = reading.unavailable(
            "验证器配置根未知：本次运行在读到配置之前就失败了"
        )
    declarations[reading.DECLARATION_ADAPTER_CONFIG] = (
        reading.unavailable("adapter 配置路径未知：本次运行在读到它之前就失败了")
        if adapter_path is None
        else reading.declaration_block(adapter_path, root=REPO)
    )
    if workspace is None:
        tree = reading.unavailable(PIN_FILE_REASON)
    elif digest is None:
        tree = reading.unavailable("树摘要没有算出来：本次运行在枚举之前就失败了")
    else:
        tree = reading.tree_block(workspace, digest=digest)
    return reading.build(
        source=reading.SOURCE_GATE,
        tree=tree,
        declarations=declarations,
        host=reading.host_block(),
        include_run=False,
    )


def build_payload(
    *,
    args: argparse.Namespace,
    rules: Any,
    digest: str,
    tree_files: int,
    tree_bytes: int,
    mode: str,
    targets: Sequence[str],
    excluded: Mapping[str, Any],
    files: Sequence[Mapping[str, Any]],
    drift: Mapping[str, str] | None,
    config_root: Path,
    adapter_path: Path,
) -> dict[str, Any]:
    violations = [item for file in files for item in file["violations"]]
    by_severity = {name: 0 for name in SEVERITIES}
    for item in violations:
        by_severity[item["severity"]] += 1
    blocking = [item for item in violations if item["severity"] in BLOCKING_SEVERITIES]

    decisions = {name: 0 for name in DECISIONS}
    for file in files:
        decision = file["decision"]
        if decision in decisions:
            decisions[decision] += 1
    unavailable_files = [file for file in files if file["status"] != "ok"]

    reasons: list[str] = []
    if drift is not None:
        reasons.append("规则集漂移：pinned=" + drift["pinned"] + " current=" + drift["current"])
    if blocking:
        reasons.append(str(len(blocking)) + " 条 error/critical 级违规")
    if unavailable_files:
        detail = "；".join(
            file["file"] + "（" + _first_gap_reason(file) + "）" for file in unavailable_files
        )
        reasons.insert(0, "无法完成判定：" + detail)

    if unavailable_files:
        exit_code, status = EXIT_UNAVAILABLE, GATE_UNAVAILABLE
    elif drift is not None or blocking:
        exit_code, status = EXIT_FINDINGS, GATE_FAIL
    else:
        exit_code, status = EXIT_OK, GATE_OK

    missing_by_file = {
        file["file"]: list(file["check_volume"]["missing_dimensions"])
        for file in files
        if file["check_volume"] is not None and file["check_volume"]["missing_dimensions"]
    }
    layer_sources: dict[str, int] = {}
    for file in files:
        key = str(file["layer_source"])
        layer_sources[key] = layer_sources.get(key, 0) + 1

    return {
        "schema_version": FINAL_TREE_GATE_SCHEMA_VERSION,
        "coverage": {
            "complete": not missing_by_file,
            "files_incomplete": sorted(missing_by_file),
            "missing_dimensions": missing_by_file,
            "note": policy_check.CHECK_VOLUME_NOTE,
        },
        "counts": {
            "blocking_violations": len(blocking),
            "decisions": decisions,
            "files_ok": len(files) - len(unavailable_files),
            "files_unavailable": len(unavailable_files),
            "targets": len(files),
            "violations": len(violations),
        },
        "files": list(files),
        "gate": {
            "exit_code": exit_code,
            "reason": "；".join(reasons),
            "rule_set_drift": None if drift is None else dict(drift),
            "status": status,
        },
        "layer_sources": layer_sources,
        "reading_context": _reading_context(
            workspace=Path(args.workspace).resolve(),
            digest=digest,
            config_root=config_root,
            adapter_path=adapter_path,
        ),
        "rule_set": rule_set_payload(rules),
        "violations": violations,
        "violations_by_severity": by_severity,
        "workspace_scope": {
            "excluded": dict(excluded),
            "mode": mode,
            "operation": args.operation,
            "targets": list(targets),
            "tree_digest": {"bytes": tree_bytes, "files": tree_files, "sha256": digest},
        },
    }


def _first_gap_reason(file: Mapping[str, Any]) -> str:
    evidence = file.get("evidence") or {}
    gaps = evidence.get("gaps") or []
    if not gaps:
        return "证据缺失"
    return str(gaps[0].get("reason") or "证据缺失")


def failure_payload(reason: str) -> dict[str, Any]:
    """退出码 2 也要有机器可读载荷：失败关闭不能只表现为一行 stderr。"""

    return {
        "schema_version": FINAL_TREE_GATE_SCHEMA_VERSION,
        "gate": {
            "exit_code": EXIT_UNAVAILABLE,
            "reason": reason,
            "rule_set_drift": None,
            "status": GATE_UNAVAILABLE,
        },
        "reading_context": _reading_context(
            workspace=None, digest=None, config_root=None, adapter_path=None
        ),
    }


# --------------------------------------------------------------------------- 渲染


def render_text(payload: Mapping[str, Any]) -> str:
    """给人看的摘要：结论 -> 规则集 -> 每个文件的 decision 与违规 -> 漂移。"""

    gate = payload["gate"]
    lines = [
        "FINAL_TREE_GATE: "
        + str(gate["status"])
        + " exit="
        + str(gate["exit_code"]),
    ]
    if "rule_set" in payload:
        rule_set = payload["rule_set"]
        lines.append(
            "rule_set: identity=" + str(rule_set["identity"]) + " count=" + str(rule_set["count"])
        )
    if "workspace_scope" in payload:
        scope = payload["workspace_scope"]
        lines.append(
            "workspace: mode="
            + str(scope["mode"])
            + " operation="
            + str(scope["operation"])
            + " tree="
            + str(scope["tree_digest"]["sha256"]),
        )
    for file in payload.get("files", ()):
        lines.append(
            "["
            + str(file["status"])
            + "] "
            + file["file"]
            + " decision="
            + str(file["decision"]),
        )
        for item in file["violations"]:
            lines.append(
                "  - [" + item["severity"] + "] " + item["rule_id"] + "：" + item["message"]
            )
        for item in file.get("pending_findings", ()):
            lines.append("  - [pending] " + item["rule_id"] + "：" + item["message"])
    if gate.get("rule_set_drift"):
        drift = gate["rule_set_drift"]
        lines.append("RULE_SET_DRIFT: pinned=" + drift["pinned"] + " current=" + drift["current"])
    if gate["reason"]:
        lines.append("REASON: " + str(gate["reason"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------- CLI


def _operation_values() -> tuple[Any, ...]:
    from policy.models import Operation

    return tuple(Operation)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python tools/final_tree_gate.py",
        description=(
            "C3 最终树门禁 v1：对一棵树跑规则集 + 真实验证器，汇总 violations 并给出 "
            "0 / 1 / 2 门禁退出码；--pin / --check 钉住规则集身份。只读，不导入工作流框架。"
        ),
    )
    parser.add_argument(
        "--workspace", required=True, help="被判定树的根目录（目标文件都在它之内）"
    )
    parser.add_argument(
        "--config",
        required=True,
        metavar="PATH",
        help="adapter 配置（分层 / 语言 / 默认规则目录的来源，与 Hook 路径同一份实现）",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--changed",
        action="append",
        default=None,
        metavar="FILE",
        help="显式目标文件（可重复 / 逗号分隔；相对 --workspace）。不给时按 --all 枚举",
    )
    group.add_argument(
        "--all",
        action="store_true",
        dest="enumerate_all",
        help="枚举树内受规则覆盖的文件（不给 --changed 时的默认行为）",
    )
    group2 = parser.add_mutually_exclusive_group()
    group2.add_argument(
        "--pin", default=None, metavar="FILE", help="把当前规则集身份写进钉住文件（写完退 0）"
    )
    group2.add_argument(
        "--check",
        default=None,
        metavar="FILE",
        help="与钉住文件比对；规则集漂移退出码 1（读不到 / 版本不认识退出码 2）",
    )
    parser.add_argument(
        "--rules",
        action="append",
        default=None,
        metavar="DIR",
        help="规则目录，可重复；默认取 adapter 配置的 rules",
    )
    parser.add_argument(
        "--config-root",
        default=None,
        help="validation/ 配置所在目录；默认仓库根（与 policy.check 同源）",
    )
    parser.add_argument(
        "--operation",
        default="edit",
        choices=[item.value for item in _operation_values()],
        help=(
            "被治理的操作（受控枚举）。默认 edit：最终树是写类动作的产物，"
            "门禁把每个目标当作「一次 edit 到它自己」——这是显式口径，不从树推断"
        ),
    )
    parser.add_argument(
        "--validators",
        default=None,
        metavar="A,B",
        help="只运行这些验证器（透传验证器流水线；没跑的 checker 按失败关闭处理）",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读载荷")
    return parser


def _pin_result(args: argparse.Namespace, rules: Any) -> int:
    pin_path = Path(args.pin).expanduser()
    write_pin(pin_path, rules)
    if args.json:
        payload = {
            "gate": {
                "exit_code": EXIT_OK,
                "reason": "",
                "rule_set_drift": None,
                "status": GATE_PINNED,
            },
            "reading_context": _reading_context(
                workspace=None, digest=None, config_root=None, adapter_path=None
            ),
            "rule_set": rule_set_payload(rules),
            "schema_version": FINAL_TREE_GATE_SCHEMA_VERSION,
        }
        sys.stdout.write(dump_json(payload))
    else:
        sys.stdout.write("FINAL_TREE_GATE: pinned rule_set.identity=" + rules.identity + "\n")
    return EXIT_OK


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run_gate(args)
    except GateError as error:
        return _emit_failure(args, str(error))
    except (DshEventError, LoaderError, RegistryError, EngineError, OSError, ValueError) as error:
        # 已知的「装不起来 / 读不到」一律退出码 2；绝不以未捕获异常变成 1（那是「发现违规」）。
        return _emit_failure(args, type(error).__name__ + ": " + str(error))
    except Exception as error:  # noqa: BLE001 - 门禁对未知异常同样失败关闭
        return _emit_failure(
            args, "未预期异常（失败关闭）：" + type(error).__name__ + ": " + str(error)
        )


def _emit_failure(args: argparse.Namespace, reason: str) -> int:
    payload = failure_payload(reason)
    if args.json:
        sys.stdout.write(dump_json(payload))
    else:
        sys.stdout.write(
            "FINAL_TREE_GATE: " + GATE_UNAVAILABLE + " exit=" + str(EXIT_UNAVAILABLE) + "\n"
        )
        for line in redact(payload["gate"]["reason"]).splitlines() or [""]:
            sys.stdout.write("REASON: " + line + "\n")
    return EXIT_UNAVAILABLE


def _run_gate(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser()
    if not workspace.is_dir():
        raise GateError("--workspace 不存在或不是目录")
    workspace = workspace.resolve()

    adapter_path = Path(args.config).expanduser()
    adapter = load_adapter(adapter_path)
    config_root = resolve_config_root(args.config_root)
    validation_config = load_validation(config_root)
    rules = load_rules(args, adapter)

    if args.pin:
        return _pin_result(args, rules)

    drift: dict[str, str] | None = None
    if args.check:
        pinned = read_pinned_identity(Path(args.check), label="--check")
        current = rules.identity
        if pinned != current:
            drift = {"current": current, "pinned": pinned}

    try:
        digest = workspace_tree_digest(workspace)
    except (ProvenanceError, OSError, ValueError) as error:
        raise GateError("树的稳定摘要证明不了（失败关闭）：" + str(error)) from error

    targets, excluded = collect_targets(args, workspace, adapter, validation_config.registry)
    mode = "changed" if args.changed is not None else "all"

    files: list[dict[str, Any]] = []
    for relative in targets:
        try:
            files.append(
                evaluate_file(
                    args,
                    workspace=workspace,
                    adapter=adapter,
                    rules=rules,
                    config_root=config_root,
                    relative=relative,
                    changed=targets,
                )
            )
        except Exception as error:  # noqa: BLE001 - 一个文件判不了不许让整份载荷消失
            files.append(_failed_file(relative, error))

    payload = build_payload(
        args=args,
        rules=rules,
        digest=digest.sha256,
        tree_files=digest.files,
        tree_bytes=digest.bytes,
        mode=mode,
        targets=targets,
        excluded=excluded,
        files=files,
        drift=drift,
        config_root=config_root,
        adapter_path=adapter_path,
    )
    exit_code = payload["gate"]["exit_code"]
    return _emit(payload, render_text(payload), as_json=bool(args.json), exit_code=exit_code)


def _emit(payload: Mapping[str, Any] | None, text: str, *, as_json: bool, exit_code: int) -> int:
    if as_json and payload is not None:
        sys.stdout.write(dump_json(payload))
    else:
        sys.stdout.write(text + "\n")
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

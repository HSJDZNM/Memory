# 规范治理价值评测：把「平台判定 vs 第三方标注」变成可机器复算的读数。
#
# 当前实现 **只做 --suite fidelity**（方案 §5 W1：两跳 L1a / L1b + GV-01..04 + §6.5 的 P1/P2/P3 对照）。
# 其余套件（coverage / cve / agent / fault / retrieval / friction / ab）显式报用法错误，不假装支持。
#
# 用法::
#
#     python tools/governance_eval.py --suite fidelity                 # 跑一遍，写读数并判定
#     python tools/governance_eval.py --suite fidelity --json          # 打印完整载荷
#     python tools/governance_eval.py --suite fidelity --corpus-root .tmp/eval-corpora
#     python tools/governance_eval.py --suite fidelity --dataset bandit-functional
#     python tools/governance_eval.py --suite fidelity --fetch         # 先取语料（委托 tools/eval_corpus.py）
#     python tools/governance_eval.py --suite fidelity --record evaluation/results/fidelity-baseline.json
#     python tools/governance_eval.py --suite fidelity --check  evaluation/results/fidelity-baseline.json
#
# 退出码::
#
#     0 = 全部门槛判据 pass
#     1 = 有判据 fail，或**读不到**（语料没取到 / ruff 缺失 / 锁验证不过 / 扫描不完整）——
#         读不到一律显式写出原因，**绝不静默 pass**
#     2 = 用法或配置错误（未知 --suite、门槛文件读不了 / 字段不认识、目录给错）
#
# 两跳口径（方案 §5 W1，**两跳分开输出、禁止互相解释**）::
#
#     L1a  原始 ruff check --output-format=json 的诊断  vs 上游标注           -> 只报告，不进任何门槛
#     L1b  平台判定（真实验证器流水线）                 vs **同一次**原始 ruff 诊断 -> 期望 100%
#     GV-01 / GV-02 / GV-03 **都定义在 L1b 上**；GV-04 的口径见下。
#
#     L1b 的"同一次"怎么保证：harness 用**平台自己的** probe_tool / build_argv / run_tool
#     （注册表里的 tool.ruff 声明）跑一次原始 ruff，拿到 JSON 诊断；平台判定走
#     validators.pipeline.run_pipeline + policy.engine.evaluate。两侧的 ruff 版本、配置文件、
#     配置哈希与 argv 都记进载荷；此外还要做一次**一致性核对**（same_run_check）：平台自己的
#     证据投影（码 / 文件 / 行）必须与原始诊断逐条对得上——对不上就是"两次运行不是同一批诊断"，
#     如实写出来，不拿它解释别的读数。
#
# 口径（写下来，免得下一个人顺手改成好看的样子）
# ============================================
#
# 1. **码 -> rule_id 只有一份真相**：全部从 policy.loader.load_rule_set 读出来的规则体推出
#    （style_lint.codes）。本文件里**没有任何手写的码->规则映射表**；上游码到平台码只做一次
#    **机械前缀归一**（B ### -> S ###，声明在 evaluation/thresholds.yaml 的 code_aliases 里，带理由）。
# 2. **三分类分母互不污染**：平台已声明码 -> mapped；上游码无平台归属 -> capability_out
#    （既不算 TP 也不算 FN）；在 validation/ruff.toml 的 select 里、却没有任何规则归属的码
#    （实测 F811/F841）-> unmapped（只计数、不判定）。上游的空白期望标记（pycodestyle 的
#    "#: Okay"，声明在 thresholds 的 blank_code_tokens 里）是**负例**，不进任何一类，
#    只单独计数它覆盖到的诊断。
# 3. **位置可比性分三桶，绝不混算**（契约 v1.1 的 annotation_scopes）：
#    - line   ：expected_lines 非空 -> **行级**，进 GV-01 / GV-02 / GV-03；
#    - scope  ：expected_lines 为空、但上游给了位置区间（scope_end > scope_start）->
#               作用域级，单列一套命中/未命中读数；
#    - file   ：其余（契约里 line == 0，或上游只到文件/定义粒度，例如 pydocstyle 的 @expect）->
#               文件级，单列一套命中/未命中读数。
#    作用域级与文件级**绝不折进行级 TP/FP/FN**，也**绝不被丢掉**：三桶的条数与命中都要出现在载荷里。
# 4. **L1b 的分母只有 evidence.kind == "style_lint" 的违规**：那是 ruff 这条证据链。失败关闭产生的
#    critical 违规（evidence.kind == "validator"，例如 ruff 没能分析该文件）与其他 checker 的违规
#    （missing_docstring / forbidden_dependency / ...）**单列**，既不进 GV-01 的分子也不进分母——
#    它们是另外两类结论，混进来会让"精确率"变成别的东西。
# 5. **GV-04 有两个分母，都说出来**：
#    - platform_attributable（**门槛用这一个**）：标注码在**同一次原始 ruff 诊断里真的出现过**、
#      且能映射到平台规则，却没有 violation、也没有 skipped_rules / language_coverage 的说明；
#    - including_tool_differences（只报告）：连"ruff 自己就没报这个位置"的标注也算静默。
#    为什么门槛不用后者：上游工具与 ruff 是两套实现，它们不一致属于 L1a 的差（方案明说
#    "度量证据工具与上游标注的差，不是平台的责任"）。把 L1a 的差算成平台的静默漏报，
#    正是"用 L1a 的差值去解释或掩盖 L1b"那条禁令的反面形态。
# 6. **"有没有说明"是结构化的**：violation 的存在按 (file, line) 与规则身份比对；skipped_rules 的
#    说明用 **policy.scope.match_scope(rule.scope, context)** 重新算一遍（平台自己的匹配器，
#    不解析 skipped_rules 里的 reasons 文本）；language_coverage 读 PipelineReport 的状态字段。
#    三处都不看自由文本。
# 7. **样本量诚实**：每条规则输出 N（能映射到它的**行级**标注条数）。N < 预注册下限 ->
#    insufficient_sample：不参与门槛判定、**也不算通过**；没有标注的规则进
#    rules_without_external_labels 显式清单。
# 8. **读数带归属**：载荷顶层带 reading_context（哪棵树 / 哪个环境 / 哪套声明）+ 平台 revision，
#    写进 evaluation/results/fidelity-<revision>.json。
#
# 不承诺什么（与方案 §9 同一条纪律）
# ================================
#
# - L1b 全绿**不说明**这些诊断值得报：它只证明平台忠实转述了它声明的证据工具（方案 §2 R2）；
# - L1a 的差不是平台的账，但也不是"没问题"——它说明上游标注与 ruff 口径本就不完全一致；
# - 本读数不外推到 Python 之外，也不覆盖那 4 条非 style_lint 规则（它们没有第三方标注，在载荷里单列）；
# - 比例指标给 Wilson 区间；区间窄不代表样本有代表性，只代表样本大。

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import tomllib
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from policy.check import infer_layer  # noqa: E402
from policy.context import build_context  # noqa: E402
from policy.engine import evaluate  # noqa: E402
from policy.loader import load_rule_set  # noqa: E402
from policy.models import Rule, RuleSet  # noqa: E402
from policy.scope import match_scope  # noqa: E402
from provenance import reading_context as reading  # noqa: E402
from validators.pipeline import PipelineRequest, run_pipeline  # noqa: E402
from validators.registry import load_config  # noqa: E402

# --------------------------------------------------------------------------- 常量

# 本载荷自己的协议轴（AGENTS 第 55 条：加键 / 改语义就要动它）。
#
# 1.0 = **首次建轴**：本次会话里建立，且**首次发布之前**的形状增补（negative_control /
# coverage_tiers / snippet_materialization / l1b.blank_exclusion / datasets[].expected_empty …）
# 都在同一版本号内 —— 与 policy.check.OUTPUT_SCHEMA_VERSION 1.2 的裁定同型（"尚未发布，
# 形状修正在 1.2 内、不升版"，见 src/policy/check.py 的常量注释）。
# 判据不是"我觉得还没发布"，而是可复核的事实：仓库里只有**一份** fidelity 载荷形状
# （evaluation/results/fidelity-<rev>.json；fidelity-baseline.json 是它的**投影**，不是第二个载荷），
# 同一版本号下不存在第二种键集合。**首次被别的工具 / 文档消费之后再加键，必须 1.0 -> 1.1。**
GOVERNANCE_EVAL_SCHEMA_VERSION = "1.0"

SUITE_FIDELITY = "fidelity"
KNOWN_SUITES = (SUITE_FIDELITY,)
# 方案 §7 里点名的其余套件：**没有实现**。显式列出来，让"不支持"比"忘了跑"更容易看见。
UNIMPLEMENTED_SUITES = ("coverage", "cve", "agent", "fault", "retrieval", "friction", "ab")

THRESHOLDS_PATH = "evaluation/thresholds.yaml"
RESULTS_DIR = "evaluation/results"
DEFAULT_BASELINE = "evaluation/results/fidelity-baseline.json"
DEFAULT_CORPUS_ROOT = ".tmp/eval-corpora"
DEFAULT_LOCK_DIR = "evaluation/corpora"
EVAL_CORPUS_PATH = "tools/eval_corpus.py"

RUFF_VALIDATOR_ID = "tool.ruff"

WORK_ROOT = ".tmp/governance-eval"

STYLE_LINT_KIND = "style_lint"

SAMPLE_OK = "ok"
SAMPLE_INSUFFICIENT = "insufficient_sample"
SAMPLE_NO_LABELS = "no_external_labels"

CLASS_MAPPED = "mapped"
CLASS_UNMAPPED = "unmapped"
CLASS_CAPABILITY_OUT = "capability_out"
CLASS_BLANK = "blank_expectation"

POSITION_LINE = "line"
POSITION_SCOPE = "scope"
POSITION_FILE = "file"
# 负例（空白期望）自己的位置通道：它**不进**任何正例桶，只服务负例控制读数。
POSITION_BLANK = "blank"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

# 语料层必须导出的函数（【冻结接口契约 v1】）；annotation_scopes 是 v1.1 的**增量**，
# 缺了它也能跑（退回 Annotation 自带的位置），但读数里会写明用的是哪一份。
CORPUS_REQUIRED = ("available_datasets", "corpus_files", "load_annotations", "fetch", "verify")
CORPUS_OPTIONAL = ("annotation_scopes", "SOURCES")

SCOPES_SOURCE_CONTRACT = "eval_corpus.annotation_scopes"
SCOPES_SOURCE_FALLBACK = "annotation.position_fallback"


class UsageError(Exception):
    """用法 / 配置错误：退出码 2。"""


class Unavailable(Exception):
    """读不到（语料模块缺失 / 语料没取到 / ruff 不可用）：显式 unavailable，绝不静默 pass。"""


# --------------------------------------------------------------------------- 门槛（数据驱动的严格模型）


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CodeAlias(StrictModel):
    """上游码前缀 -> 平台码前缀的**机械归一**（不是映射表，理由写在数据里）。"""

    upstream_prefix: str = Field(min_length=1)
    platform_prefix: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ContextSpec(StrictModel):
    language: str = Field(min_length=1)
    layer: str = Field(min_length=1)
    operation: Optional[str] = None
    layer_source: str = Field(min_length=1)


class Contexts(StrictModel):
    corpus: ContextSpec
    fidelity_corpus_note: str = ""
    repo_scan: ContextSpec
    repo_scan_note: str = ""


class RepoScanSpec(StrictModel):
    enabled: bool = True
    listing: str = Field(min_length=1)
    exclude_prefixes: Tuple[str, ...] = ()
    attribution_method: str = ""
    attribution_note: str = ""


class PredictionP1(StrictModel):
    statement: str
    rule_id: str
    codes: Tuple[str, ...]
    metric: str
    operator: str
    value: float
    falsified_means: str


class PredictionP2(StrictModel):
    statement: str
    rule_id: str
    codes: Tuple[str, ...]
    metric: str
    operator: str
    value: float
    falsified_means: str


class PredictionP3(StrictModel):
    statement: str
    metric: str
    warning_share_operator: str
    warning_share_value: float
    error_share_operator: str
    error_share_value: float
    falsified_means: str


class Predictions(StrictModel):
    P1: PredictionP1
    P2: PredictionP2
    P3: PredictionP3


class FidelitySuite(StrictModel):
    datasets: Tuple[str, ...] = Field(min_length=1)
    min_annotations_per_rule: int = Field(ge=1)
    gv01_precision_error_min: float = Field(ge=0.0, le=1.0)
    gv01_precision_overall_min: float = Field(ge=0.0, le=1.0)
    gv02_recall_per_rule_min: float = Field(ge=0.0, le=1.0)
    gv03_attribution_accuracy_required: float = Field(ge=0.0, le=1.0)
    gv04_silent_miss_rate_max: float = Field(ge=0.0, le=1.0)
    require_corpus_lock: bool
    code_aliases: Tuple[CodeAlias, ...] = ()
    blank_code_tokens: Tuple[str, ...] = ()
    context: Contexts
    repo_scan: RepoScanSpec
    predictions: Predictions


class Thresholds(StrictModel):
    schema_id: str
    version: int = Field(ge=1)
    preregistered_on: str
    plan_ref: str
    metric_definitions: Mapping[str, str] = Field(default_factory=dict)
    suites: Mapping[str, FidelitySuite]


def load_thresholds(path: Path) -> Thresholds:
    """读预注册门槛；读不到 / 字段不认识一律报错（不猜、不取默认值）。"""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise UsageError("门槛文件读不到：" + str(error)) from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise UsageError("门槛文件不是合法 YAML：" + str(error)) from error
    if not isinstance(document, Mapping):
        raise UsageError("门槛文件顶层必须是映射，得到 " + type(document).__name__)
    try:
        return Thresholds.model_validate(dict(document))
    except ValidationError as error:
        raise UsageError("门槛文件字段不认识或取值越界：\n" + str(error)) from error


# --------------------------------------------------------------------------- 语料层（唯一契约实现）


def load_corpus_module(path: Path) -> Any:
    """按**绝对路径**加载契约模块 tools/eval_corpus.py（不依赖 sys.path 或包结构）。

    契约要求它导出 available_datasets / corpus_files / load_annotations / fetch / verify。
    缺一个就显式报不可用——本工具绝不自己解析标注（那是第二份真相）。
    """

    if not path.is_file():
        raise Unavailable(
            "语料层模块不存在：" + display(path) + "（契约实现由 eval-corpus 提供；"
            "在它落地之前可以用 --corpus-module 指向一份自测替身，但那不构成语料读数）"
        )
    spec = importlib.util.spec_from_file_location("governance_eval_corpus_contract", path)
    if spec is None or spec.loader is None:
        raise Unavailable("无法为 " + display(path) + " 建立模块规格（路径形态可疑）")
    module = importlib.util.module_from_spec(spec)
    # dataclass 在字符串注解下要靠 sys.modules 找回自己的模块；不注册会让它解析失败。
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - 语料层的任何异常都等于"读不到"
        raise Unavailable(
            "加载 " + display(path) + " 失败：" + type(error).__name__ + ": " + str(error)
        ) from error

    missing = [name for name in CORPUS_REQUIRED if not hasattr(module, name)]
    if missing:
        raise Unavailable(
            "语料层契约不完整：缺少 " + ", ".join(missing) + "（见【冻结接口契约 v1】）"
        )
    return module


EVAL_CORPUS_EXTRA_PATH = "tools/eval_corpus_extra.py"


def load_granularity_data(path: Path) -> Mapping[str, Any]:
    """读 tools/eval_corpus_extra.py 的**粒度声明**（数据，不是本文件的第二份表）。

    CODE_COVERAGE 只声明码 -> {dataset, granularity}；码 -> rule_id 仍然只从 policies/** 推出。
    读不到时**不猜**：状态写 unavailable，读数退回"按 annotation_scopes 的结构推断"那一档。
    """

    if not path.is_file():
        return {
            "status": "unavailable",
            "path": display(path),
            "reason": "粒度声明模块不存在（粒度只能按 annotation_scopes 的结构推断）",
            "granularities": {},
            "coverage": (),
        }
    spec = importlib.util.spec_from_file_location("governance_eval_granularity_data", path)
    if spec is None or spec.loader is None:
        return {
            "status": "unavailable",
            "path": display(path),
            "reason": "粒度声明模块无法建立模块规格",
            "granularities": {},
            "coverage": (),
        }
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - 读不到就是读不到
        return {
            "status": "unavailable",
            "path": display(path),
            "reason": "粒度声明模块加载失败：" + type(error).__name__ + ": " + str(error),
            "granularities": {},
            "coverage": (),
        }
    granularities = getattr(module, "ANNOTATION_GRANULARITIES", None)
    coverage = getattr(module, "CODE_COVERAGE", None)
    if not isinstance(granularities, Mapping) or coverage is None:
        return {
            "status": "unavailable",
            "path": display(path),
            "reason": "粒度声明模块没有导出 ANNOTATION_GRANULARITIES / CODE_COVERAGE",
            "granularities": {},
            "coverage": (),
        }
    return {
        "status": "available",
        "path": display(path),
        "digest": sha256_file(path),
        "module": module,
        "granularities": {str(key): str(value) for key, value in granularities.items()},
        "coverage": tuple(
            {
                "code": posix(item.get("code")).upper(),
                "dataset": posix(item.get("dataset")),
                "granularity": posix(item.get("granularity")),
            }
            for item in coverage
            if isinstance(item, Mapping)
        ),
    }


def dataset_granularities(granularity: Mapping[str, Any]) -> dict[str, set]:
    """数据集 -> 它声明过的粒度集合（用来判断"0 条标注是不是设计如此"）。"""

    result: dict[str, set] = {}
    for item in granularity.get("coverage", ()):
        result.setdefault(item["dataset"], set()).add(item["granularity"])
    return result


# --------------------------------------------------------------------------- 小工具


def display(path: Path | str | None) -> str:
    """路径一律仓库相对；工作区之外折成 <outside-workspace>（不放绝对路径）。"""

    return reading.display_path(path, root=REPO_ROOT)


def posix(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip()


def sha256_file(path: Path) -> Optional[str]:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def ratio(numerator: int, denominator: int) -> Optional[float]:
    """比率；分母为 0 时返回 None（**未评不是 0**，也不是 1）。"""

    if denominator <= 0:
        return None
    return numerator / denominator


def wilson_interval(successes: int, total: int, z: float = 1.96) -> Optional[Tuple[float, float]]:
    """比例的 Wilson 置信区间（方案 §6.2：比例指标给区间）。样本为 0 时返回 None。"""

    if total <= 0:
        return None
    phat = successes / total
    denominator = 1.0 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = (z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total))) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def interval_payload(successes: int, total: int) -> Optional[Mapping[str, float]]:
    interval = wilson_interval(successes, total)
    if interval is None:
        return None
    return {"low": round(interval[0], 6), "high": round(interval[1], 6)}


def compare(observed: Optional[float], operator: str, value: float) -> Optional[bool]:
    """门槛比较；observed 为 None（未评）时返回 None——**未评既不是通过也不是不通过**。"""

    if observed is None:
        return None
    if operator == "lt":
        return observed < value
    if operator == "gt":
        return observed > value
    if operator == "gte":
        return observed >= value
    if operator == "lte":
        return observed <= value
    raise UsageError("未知比较算子 " + repr(operator) + "：只接受 lt / gt / gte / lte")


def run_git(args: Sequence[str]) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout

# --------------------------------------------------------------------------- 数据形状


@dataclass(frozen=True)
class Diagnostic:
    """一条**原始** ruff 诊断（工具原话，未经过平台归属）。"""

    file: str
    line: Optional[int]
    code: str


@dataclass(frozen=True)
class Unit:
    """一条期望的**可比较形式**（三种位置桶共用同一个形状）。

    position == "line" 时 line 是 expected_lines 里的某一行（一行一个 Unit）；
    position == "scope" 时 [scope_start, scope_end] 是上游给的位置区间；
    position == "file" 时只有 file 这一级可比。
    """

    dataset: str
    file: str
    upstream_code: str
    platform_code: str
    kind: str
    classification: str
    position: str
    line: int
    scope_start: int
    scope_end: int

    @property
    def key(self) -> Tuple[str, str, str, int]:
        return (self.dataset, self.file, self.platform_code, self.line)


@dataclass
class CodeOwners:
    """码 -> 规则（**从平台规则集推出**，本文件不持有任何手写映射）。"""

    owners: dict[str, list[Rule]] = field(default_factory=dict)
    catch_all: list[Rule] = field(default_factory=list)

    def rules_for(self, code: str) -> list[Rule]:
        token = posix(code).upper()
        found = list(self.owners.get(token, ()))
        # 与 validators.adapters.ruff._owns 同语义：没有声明码的 style_lint 规则拥有全部码。
        # 当前仓库没有这种规则（实测 empty-codes = 0），但口径必须一致，不能只在这里"差不多"。
        for rule in self.catch_all:
            if rule not in found:
                found.append(rule)
        return found

    def declares(self, code: str) -> bool:
        return bool(self.rules_for(code))


def derive_code_owners(rules: RuleSet) -> CodeOwners:
    """码 -> 规则：唯一来源是 policies/**（经 load_rule_set）。"""

    result = CodeOwners()
    for rule in rules.rules:
        body = getattr(rule.rule, "style_lint", None)
        if body is None:
            continue
        codes = tuple(body.codes or ())
        if not codes:
            result.catch_all.append(rule)
            continue
        for code in codes:
            result.owners.setdefault(posix(code).upper(), []).append(rule)
    return result


def read_selected_codes(ruff_toml: Path) -> Tuple[Tuple[str, ...], Mapping[str, Any]]:
    """validation/ruff.toml 的 lint.select（+ per-file-ignores 现状）。"""

    try:
        with ruff_toml.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise UsageError("读不了 " + display(ruff_toml) + "：" + str(error)) from error
    lint = document.get("lint") or {}
    if not isinstance(lint, Mapping):
        raise UsageError("validation/ruff.toml 的 [lint] 不是映射")
    raw = lint.get("select") or ()
    if not isinstance(raw, (list, tuple)):
        raise UsageError("validation/ruff.toml 的 lint.select 不是列表")
    codes = tuple(sorted({posix(item).upper() for item in raw if posix(item)}))
    ignores = lint.get("per-file-ignores") or {}
    facts: dict[str, Any] = {
        "per_file_ignores": dict(ignores) if isinstance(ignores, Mapping) else {},
    }
    return codes, facts


def normalize_upstream_code(code: str, aliases: Sequence[CodeAlias]) -> Tuple[str, Optional[str]]:
    """上游码 -> 平台码的**机械前缀归一**；返回 (归一后的码, 用到的上游前缀或 None)。"""

    token = posix(code).upper()
    for alias in aliases:
        prefix = alias.upstream_prefix.upper()
        if prefix and token.startswith(prefix):
            return alias.platform_prefix.upper() + token[len(prefix) :], prefix
    return token, None


def classify_code(platform_code: str, owners: CodeOwners, selected: Iterable[str]) -> str:
    """三分：有规则归属 / 平台 select 了但没有规则 / 平台根本不认识。"""

    if owners.declares(platform_code):
        return CLASS_MAPPED
    if platform_code in set(selected):
        return CLASS_UNMAPPED
    return CLASS_CAPABILITY_OUT


def position_bucket(
    annotation_line: int, scope_start: int, scope_end: int, expected_lines: Sequence[int]
) -> str:
    """位置可比性分桶（模块 docstring 第 3 条；2026-10-07 按 Lead 裁定收紧）。

    优先级：
      1. expected_lines 非空 -> line（上游给了精确行）；
      2. scope 是**点**且落在 >= 1 的行上 -> line：**点作用域就是精确位置**。
         以前这里落到 file 桶，而 file 桶按 (file, code) 比对 = 把位置比对放开了；
         eval-corpus 已用不变式保证点作用域同时带 expected_lines，这里是防御性兜底
         （别的模块只给 line 也可能出现这种形状）；
      3. scope 是跨行区间 -> scope（区间级，单列）；
      4. 其余（契约里的 line == 0、[0, 0] 文件级哨兵、什么都没给）-> file。
    """

    if expected_lines:
        return POSITION_LINE
    if scope_start >= 1 and scope_end == scope_start:
        return POSITION_LINE
    if scope_start >= 1 and scope_end > scope_start:
        return POSITION_SCOPE
    if scope_end > scope_start:
        return POSITION_SCOPE
    return POSITION_FILE


@dataclass(frozen=True)
class AnnotationRecord:
    """**一条标注**（不按 expected_lines 展开）——样本量 N 用它，不用展开后的 Unit。"""

    dataset: str
    file: str
    upstream_code: str
    platform_code: str
    kind: str
    source: str
    classification: str
    position: str
    line: int
    expected_lines: Tuple[int, ...]


@dataclass(frozen=True)
class BlankScope:
    """上游的**负例**作用域（pycodestyle 的 "#: Okay"）：这一段期望一条诊断都没有。"""

    dataset: str
    file: str
    scope_start: int
    scope_end: int
    marker_line: int


def resolve_scope(
    annotation: Any, scope: Any
) -> Tuple[int, int, int, Tuple[int, ...]]:
    """(锚定行, scope_start, scope_end, expected_lines)；语料层没给作用域时退回锚定行。"""

    line = int(getattr(annotation, "line", 0) or 0)
    if scope is None:
        return line, line, line, ((line,) if line > 0 else ())
    return (
        line,
        int(getattr(scope, "scope_start", 0) or 0),
        int(getattr(scope, "scope_end", 0) or 0),
        tuple(int(item) for item in (getattr(scope, "expected_lines", ()) or ())),
    )


def build_units(
    *,
    dataset: str,
    pairs: Sequence[Tuple[Any, Any]],
    aliases: Sequence[CodeAlias],
    owners: CodeOwners,
    selected: Sequence[str],
    blank_tokens: Sequence[str],
) -> Tuple[
    list[Unit], list[AnnotationRecord], list[BlankScope], Mapping[str, int], Mapping[str, int]
]:
    """把语料层的 (Annotation, AnnotationScope) **配对**翻成可比较的 Unit。

    配对由调用方给出，且必须是**同一个对象**上的配对（scope.annotation），不要按 id()、也不要按值：
      - 按 id() 一定失败——load_annotations() 与 annotation_scopes() 是两次独立解析，各自造新实例；
      - 按值也不完全可靠——上游的多 token 用例会出现"同一个 Annotation 值、不同 expected_lines"，
        后者会被覆盖掉（eval-corpus 实测 pycodestyle 有 3 组）。
    所以唯一无歧义的配方是：只用一次 annotation_scopes()，注解从 scope.annotation 取。
    拿不到 annotation_scopes 时，配对退化成 (annotation, None)，位置按锚定行算。

    返回 (units, records, blank_scopes, 三分类计数, 位置桶计数)。**不解析上游文件**：位置语义全部来自语料层。
    行级标注按 expected_lines 展开成多个 Unit（一个期望行 = 一个可比单位）；records 保留
    标注本身的条数，样本量 N 用的是它。
    """

    blanks = {posix(token).upper() for token in blank_tokens}
    units: list[Unit] = []
    records: list[AnnotationRecord] = []
    blank_scopes: list[BlankScope] = []
    classification_counts: dict[str, int] = {}
    position_counts: dict[str, int] = {}
    for annotation, scope in pairs:
        code = posix(annotation.code).upper()
        annotation_line, scope_start, scope_end, expected = resolve_scope(annotation, scope)
        if code in blanks:
            # 负例（pycodestyle 的 "#: Okay"）：**刻意**也产出 record / unit，因为负例控制读数
            # 需要它的作用域（blank_scopes）。但它不进任何**正例**分母：
            #   - L1a 的 active 过滤掉 CLASS_BLANK；
            #   - L1b 的 expected 只由"原始诊断 × 规则归属"推出，Okay 不归属任何规则；
            #   - 样本量 N 与粒度三档只数 CLASS_MAPPED；
            #   - GV-04 只取 position == line 且 CLASS_MAPPED 的 unit。
            # 逐条核对见载荷里的 blank_exclusion / negative_control。
            classification = CLASS_BLANK
            platform_code = code
            blank_scopes.append(
                BlankScope(
                    dataset=dataset,
                    file=posix(getattr(annotation, "file", "")),
                    scope_start=scope_start,
                    scope_end=scope_end,
                    marker_line=annotation_line,
                )
            )
        else:
            platform_code, _normalized = normalize_upstream_code(annotation.code, aliases)
            classification = classify_code(platform_code, owners, selected)
        # 判定顺序（Lead 2026-10-07 裁定 A）：先判负例 -> 再判 line <= 0（文件级）
        # -> 再判点作用域 / expected_lines（行级）-> 最后才是多行作用域。
        # 负例**不走位置桶**：单行 Okay 块（line > 0、expected_lines 为空）如果落进行级桶，
        # 就会把负例混进正例的位置分布里（file 桶会从 83 变成 98 的那种错）。
        bucket = (
            POSITION_BLANK
            if classification == CLASS_BLANK
            else position_bucket(annotation_line, scope_start, scope_end, expected)
        )
        file = posix(getattr(annotation, "file", ""))
        kind = posix(getattr(annotation, "kind", ""))
        source = posix(getattr(annotation, "source", ""))

        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        position_counts[bucket] = position_counts.get(bucket, 0) + 1
        records.append(
            AnnotationRecord(
                dataset=dataset,
                file=file,
                upstream_code=posix(annotation.code),
                platform_code=platform_code,
                kind=kind,
                source=source,
                classification=classification,
                position=bucket,
                line=annotation_line,
                expected_lines=expected,
            )
        )
        if bucket == POSITION_LINE:
            if expected:
                lines = expected
            else:
                anchor = scope_start if scope_start >= 1 else annotation_line
                lines = (anchor,) if anchor >= 1 else ()
        else:
            # 文件级 / 作用域级不按行比：line 写 0 表示"这条期望没有位置可比"，
            # 于是 unit_matches 的文件桶分支只对真的没有位置的期望生效（不放松位置比对）。
            lines = (0,)
        for expected_line in lines:
            units.append(
                Unit(
                    dataset=dataset,
                    file=file,
                    upstream_code=posix(annotation.code),
                    platform_code=platform_code,
                    kind=kind,
                    classification=classification,
                    position=bucket,
                    line=int(expected_line),
                    scope_start=scope_start,
                    scope_end=scope_end,
                )
            )
    return units, records, blank_scopes, classification_counts, position_counts


# --------------------------------------------------------------------------- 平台接线


@dataclass
class RuffRunner:
    """用**平台自己的**注册表声明跑原始 ruff（保证与判定路径同一次口径）。"""

    spec: Any
    config: Any
    python: str
    probe: Any
    template_argv: Tuple[str, ...]
    config_path: Optional[Path]

    @property
    def version(self) -> Optional[str]:
        return getattr(self.probe, "version", None)

    def run(self, *, workspace: Path, target: str, tmp_dir: Path) -> Tuple[list[Diagnostic], Tuple[str, ...]]:
        from validators.adapters.base import build_argv, parse_json_output, run_tool

        tmp_dir.mkdir(parents=True, exist_ok=True)
        argv = build_argv(
            self.spec.tool,
            self.probe,
            python=self.python,
            workspace=workspace,
            config=self.config_path,
            paths=(target,),
            tmp_dir=tmp_dir,
        )
        run = run_tool(
            self.spec.tool,
            self.probe,
            argv,
            workspace=workspace,
            tmp_dir=tmp_dir,
            timeout_ms=self.spec.timeout_ms or self.config.registry.defaults.timeout_ms,
            max_output_bytes=self.spec.max_output_bytes
            or self.config.registry.defaults.max_output_bytes,
            findings_exit_codes=(1,),
            config=self.config_path,
        )
        if run.status.value != "ok":
            raise Unavailable(
                "原始 ruff 在本文件上没有跑成：status=" + run.status.value + " reason=" + str(run.reason)
            )
        try:
            document = parse_json_output(run.stdout)
        except Exception as error:  # noqa: BLE001 - 输出非法一律算读不到
            raise Unavailable(
                "原始 ruff 的 JSON 输出解析失败：" + type(error).__name__ + ": " + str(error)
            ) from error
        if not isinstance(document, list):
            raise Unavailable("原始 ruff 的 JSON 输出不是列表")
        diagnostics: list[Diagnostic] = []
        for item in document:
            if not isinstance(item, Mapping):
                continue
            location = item.get("location") or {}
            try:
                line: Optional[int] = int(location.get("row"))
            except (TypeError, ValueError):
                line = None
            diagnostics.append(
                Diagnostic(
                    file=diagnostic_file(item.get("filename"), workspace, target),
                    line=line,
                    code=posix(item.get("code")).upper(),
                )
            )
        return diagnostics, tuple(argv)


def diagnostic_file(raw: Any, workspace: Path, fallback: str) -> str:
    """工具输出里的文件名 -> 仓库相对路径；映射不了就回到目标文件（工具输出不可信）。"""

    if not isinstance(raw, str) or not raw:
        return fallback
    candidate = Path(raw)
    try:
        resolved = candidate if candidate.is_absolute() else (workspace / candidate)
        return resolved.resolve().relative_to(Path(workspace).resolve()).as_posix()
    except (OSError, ValueError):
        return fallback


def make_ruff_runner(config: Any, *, tmp_dir: Path, workspace: Path) -> RuffRunner:
    """探测工具版本并固化 argv 模板（一次探测、逐文件复用）。"""

    from validators.adapters.base import build_argv, probe_tool

    spec = config.spec(RUFF_VALIDATOR_ID)
    if spec is None or spec.tool is None:
        raise UsageError("注册表里没有 " + RUFF_VALIDATOR_ID + " 的声明，无法取原始诊断")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_tool(
        spec.tool,
        python=sys.executable,
        timeout_ms=config.registry.defaults.probe_timeout_ms,
        max_output_bytes=config.registry.defaults.max_output_bytes,
        workspace=workspace,
        tmp_dir=tmp_dir,
    )
    if not probe.ok:
        raise Unavailable(
            "外部证据工具不可用（" + RUFF_VALIDATOR_ID + "）：status=" + probe.status.value
            + " reason=" + str(probe.reason)
        )
    config_path = config.config_path(spec)
    template = build_argv(
        spec.tool,
        probe,
        python=sys.executable,
        workspace=workspace,
        config=config_path,
        paths=("<target>",),
        tmp_dir=tmp_dir,
    )
    return RuffRunner(
        spec=spec,
        config=config,
        python=sys.executable,
        probe=probe,
        template_argv=tuple(template),
        config_path=config_path,
    )

# --------------------------------------------------------------------------- 逐文件执行


@dataclass
class FileOutcome:
    """一个被测文件的一次完整读数（原始诊断 + 平台判定 + 两条说明通道）。"""

    dataset: str
    file: str
    annotations: int
    diagnostics: list[Diagnostic] = field(default_factory=list)
    raw_error: Optional[str] = None
    raw_argv: Tuple[str, ...] = ()
    style_violations: list[Any] = field(default_factory=list)
    other_violations: list[Any] = field(default_factory=list)
    failure_closed: list[Any] = field(default_factory=list)
    skipped_rule_ids: Tuple[str, ...] = ()
    skipped_structural_rule_ids: Tuple[str, ...] = ()
    coverage_status: str = ""
    coverage_reason: str = ""
    truncated: int = 0
    unmapped_findings: int = 0
    blockers: int = 0
    decision: str = ""
    evidence_pairs: list[Tuple[str, str, str, Optional[int]]] = field(default_factory=list)
    pipeline_error: Optional[str] = None


@dataclass
class DatasetOutcome:
    """一个数据集的一次读数。"""

    dataset: str
    revision: str = ""
    license: str = ""
    tier: str = ""
    title: str = ""
    registry_ref: str = ""
    corpus_root: str = ""
    scopes_source: str = SCOPES_SOURCE_FALLBACK
    annotations: int = 0
    records: list[AnnotationRecord] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    blank_scopes: list[BlankScope] = field(default_factory=list)
    expected_empty: bool = False
    empty_reason: str = ""
    classification_counts: Mapping[str, int] = field(default_factory=dict)
    position_counts: Mapping[str, int] = field(default_factory=dict)
    files: list[FileOutcome] = field(default_factory=list)
    lock: Mapping[str, Any] = field(default_factory=dict)
    dir_resolver: str = ""
    files_cross_check: Mapping[str, Any] = field(default_factory=dict)
    unavailable: list[Mapping[str, str]] = field(default_factory=list)


def classify_violation(violation: Any) -> str:
    """按**证据种类**给违规分类（不看文本）。

    style_lint  = ruff 这条证据链的命中（L1b 唯一的分母）；
    failure_closed = 失败关闭产生的 critical 违规（kind = validator / dependency）；
    other_checker  = 其他 checker 的命中（missing_docstring / forbidden_dependency / ...）。
    """

    kind = posix(getattr(getattr(violation, "evidence", None), "kind", ""))
    if kind == STYLE_LINT_KIND:
        return "style_lint"
    if kind in ("validator", "dependency"):
        return "failure_closed"
    return "other_checker"


def run_dataset(
    *,
    spec: Any,
    module: Any,
    corpus_root: Path,
    lock_dir: Path,
    work_root: Path,
    rules: RuleSet,
    config: Any,
    runner: RuffRunner,
    suite: FidelitySuite,
    owners: CodeOwners,
    selected: Sequence[str],
    dataset_granularity_sets: Mapping[str, set],
    extra_path: Path,
) -> DatasetOutcome:
    """跑一个数据集：取语料 -> 影子工作区 -> 原始 ruff + 平台流水线。"""

    dataset_id = spec.id
    outcome = DatasetOutcome(dataset=dataset_id)
    outcome.corpus_root = display(corpus_root)
    outcome.registry_ref = posix(getattr(spec, "registry_ref", ""))
    outcome.revision = posix(getattr(spec, "revision", ""))
    outcome.license = posix(getattr(spec, "license", ""))
    outcome.tier = posix(getattr(spec, "tier", ""))
    outcome.title = posix(getattr(spec, "title", ""))

    # 语料在本地待在哪，由语料层说了算（<root>/<id>@<rev>/），不在这里猜目录形状。
    if hasattr(module, "dataset_dir"):
        dataset_root = Path(module.dataset_dir(dataset_id, root=corpus_root))
        outcome.dir_resolver = "eval_corpus.dataset_dir"
    else:
        dataset_root = Path(corpus_root) / dataset_id
        outcome.dir_resolver = "corpus_root/<id>（语料层没有 dataset_dir）"
    annotations = list(module.load_annotations(dataset_id, root=corpus_root))
    outcome.annotations = len(annotations)
    try:
        contract_files = sorted(posix(item) for item in module.corpus_files(dataset_id, root=corpus_root))
    except Exception as error:  # noqa: BLE001 - 对不上就是一条读数，不是崩溃
        contract_files = []
        outcome.files_cross_check = {
            "consistent": None,
            "reason": "corpus_files 读不到：" + type(error).__name__ + ": " + str(error),
        }
    else:
        derived_files = sorted({posix(getattr(item, "file", "")) for item in annotations})
        outcome.files_cross_check = {
            "consistent": contract_files == derived_files,
            "contract_files": len(contract_files),
            "derived_files": len(derived_files),
            "only_in_contract": [item for item in contract_files if item not in set(derived_files)][:20],
            "only_in_annotations": [item for item in derived_files if item not in set(contract_files)][:20],
        }
    # 锁：漂移不许静默（AGENTS 第 12 条的同一条纪律）。
    # "锁文件在不在"与"verify 说通过没有"是两件事，分开写：verify 的 problems 里既有漂移，
    # 也有语料层自己的结构自检说明（例如上游期望指向的目标越界、已丢弃并计数），
    # 混在一起读会把"上游漂移"误读成"锁没记"，反之亦然。
    lock_file: Optional[Path] = None
    try:
        if hasattr(module, "lock_path"):
            lock_file = Path(module.lock_path(dataset_id, lock_dir))
        else:
            lock_file = Path(lock_dir) / (dataset_id + ".lock.json")
    except Exception as error:  # noqa: BLE001 - 位置推不出来就写明白
        outcome.lock = {
            "present": None,
            "path": None,
            "ok": None,
            "problems": ["锁文件位置推不出来：" + type(error).__name__ + ": " + str(error)],
        }
    try:
        ok, problems = module.verify(dataset_id, root=corpus_root, lock_dir=lock_dir)
        outcome.lock = {
            "present": None if lock_file is None else lock_file.is_file(),
            "path": display(lock_file) if lock_file is not None else None,
            "ok": bool(ok),
            "problems": [str(item) for item in problems],
        }
    except Exception as error:  # noqa: BLE001 - 验不了也是一种读数
        outcome.lock = {
            "present": None if lock_file is None else lock_file.is_file(),
            "path": display(lock_file) if lock_file is not None else None,
            "ok": None,
            "problems": ["verify 抛出 " + type(error).__name__ + ": " + str(error)],
        }

    if not annotations:
        # "0 条标注"有两种：**设计如此**（该数据集的码全是片段级，见 CODE_COVERAGE 的 granularity）
        # 与**出问题了**（语料没取到 / 解析器坏了）。两者必须分开，不能都写成 unavailable。
        declared = set(dataset_granularity_sets.get(dataset_id, set()))
        if declared and declared <= {"snippet"}:
            outcome.expected_empty = True
            outcome.empty_reason = (
                "该数据集在 " + display(extra_path) + " 的 CODE_COVERAGE 里只声明了 "
                + "/".join(sorted(declared)) + " 粒度：片段级期望不产出 Annotation，0 条是设计如此"
            )
        else:
            outcome.unavailable.append(
                {
                    "what": "annotations",
                    "reason": "语料层对 " + dataset_id + " 返回 0 条标注"
                    + ("（声明过的粒度：" + "/".join(sorted(declared)) + "）" if declared else "（没有粒度声明）"),
                }
            )
        return outcome

    scopes = None
    if hasattr(module, "annotation_scopes"):
        try:
            scopes = list(module.annotation_scopes(dataset_id, root=corpus_root))
            outcome.scopes_source = SCOPES_SOURCE_CONTRACT
            if len(scopes) != len(annotations):
                outcome.unavailable.append(
                    {
                        "what": "annotation_scopes",
                        "reason": "annotation_scopes 返回 " + str(len(scopes)) + " 条，"
                        "load_annotations 返回 " + str(len(annotations)) + " 条：两份读数对不上",
                    }
                )
        except Exception as error:  # noqa: BLE001 - 拿不到就退回，但读数里写明来源
            scopes = None
            outcome.unavailable.append(
                {
                    "what": "annotation_scopes",
                    "reason": "annotation_scopes 读不到（退回 Annotation 自带位置）："
                    + type(error).__name__ + ": " + str(error),
                }
            )
    if scopes is None:
        outcome.scopes_source = SCOPES_SOURCE_FALLBACK

    # 配对只能用**同一次调用**里的对象：scopes 给了就用 scope.annotation（1:1、无歧义），
    # 拿不到 scopes 才退回 load_annotations 的锚定行。load_annotations 在这里只用于
    # "两条读数条数必须相等"的核对（上面那条检查），不参与配对。
    if scopes is not None:
        pairs = [(scope.annotation, scope) for scope in scopes]
    else:
        pairs = [(annotation, None) for annotation in annotations]

    units, records, blank_scopes, classification_counts, position_counts = build_units(
        dataset=dataset_id,
        pairs=pairs,
        aliases=suite.code_aliases,
        owners=owners,
        selected=selected,
        blank_tokens=suite.blank_code_tokens,
    )
    outcome.units = units
    outcome.records = records
    outcome.blank_scopes = blank_scopes
    outcome.classification_counts = classification_counts
    outcome.position_counts = position_counts

    # 影子工作区：只放**被测文件**（语料是被测对象，仓库真实文件一个字不碰）。
    workspace = Path(work_root) / dataset_id / "workspace"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    by_file: dict[str, list[Any]] = {}
    for annotation in annotations:
        by_file.setdefault(posix(getattr(annotation, "file", "")), []).append(annotation)
    for relative in sorted(by_file):
        source = dataset_root / relative
        target = workspace / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        except OSError as error:
            outcome.unavailable.append(
                {"what": "file:" + relative, "reason": "语料文件复制不到影子工作区：" + str(error)}
            )

    context_spec = suite.context.corpus
    for index, relative in enumerate(sorted(by_file)):
        item = FileOutcome(dataset=dataset_id, file=relative, annotations=len(by_file[relative]))
        tmp_dir = Path(work_root) / dataset_id / "tmp" / ("f%04d" % index)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            diagnostics, argv = runner.run(workspace=workspace, target=relative, tmp_dir=tmp_dir)
            item.diagnostics = diagnostics
            item.raw_argv = argv
        except Unavailable as error:
            item.raw_error = str(error)
        payload: dict[str, Any] = {
            "request_id": "governance-eval-" + dataset_id + "-" + str(index),
            "file": relative,
            "language": context_spec.language,
            "layer": context_spec.layer,
        }
        if context_spec.operation:
            payload["operation"] = context_spec.operation
        try:
            context = build_context(payload, repo_root=workspace)
            report = run_pipeline(
                PipelineRequest(target=relative, workspace=workspace, context=context, rules=rules),
                config=config,
            )
            result = evaluate(rules, context, evidence=report.bundle)
        except Exception as error:  # noqa: BLE001 - 判定链路任何异常都记成显式读数
            item.pipeline_error = type(error).__name__ + ": " + str(error)
            outcome.files.append(item)
            continue
        item.decision = result.decision.value
        item.skipped_rule_ids = tuple(item_skip.rule_id for item_skip in result.skipped_rules)
        # "这条规则为什么不参与"必须是**结构化**的：用平台自己的匹配器重算一遍范围，
        # 不解析 skipped_rules 里的 reasons 文本（GV-04 的口径）。
        known = rules_by_id(rules)
        structural: list[str] = []
        for item_skip in result.skipped_rules:
            rule = known.get(item_skip.rule_id.split("@", 1)[0])
            if rule is not None and not match_scope(rule.scope, context).matched:
                structural.append(rule.id)
        item.skipped_structural_rule_ids = tuple(sorted(set(structural)))
        coverage = dict(report.language_coverage or {})
        item.coverage_status = posix(coverage.get("status"))
        item.coverage_reason = posix(coverage.get("reason"))
        item.truncated = int(report.truncated_evidence or 0)
        item.unmapped_findings = int(report.unmapped_findings or 0)
        item.blockers = len(report.blockers)
        for violation in result.violations:
            bucket = classify_violation(violation)
            if bucket == "style_lint":
                item.style_violations.append(violation)
            elif bucket == "failure_closed":
                item.failure_closed.append(violation)
            else:
                item.other_violations.append(violation)
        for evidence in report.evidence:
            # 只收 ruff 这条链的证据投影：same_run_check 的对照面是原始 ruff 诊断，
            # 把 py.docstring 之类的证据混进来会造出"平台多报了"的假结论。
            if posix(getattr(evidence, "checker", "")) != STYLE_LINT_KIND:
                continue
            location = getattr(evidence, "location", None)
            item.evidence_pairs.append(
                (
                    posix(getattr(evidence, "rule_id", "")),
                    posix(getattr(evidence, "value", "")).upper(),
                    posix(getattr(location, "file", "")) if location is not None else relative,
                    getattr(location, "line", None) if location is not None else None,
                )
            )
        outcome.files.append(item)
    return outcome


# --------------------------------------------------------------------------- 指标


def pool_index(pairs: Iterable[Tuple[str, str, Optional[int]]]) -> dict[Tuple[str, str], set]:
    index: dict[Tuple[str, str], set] = {}
    for file, code, line in pairs:
        index.setdefault((file, code), set()).add(line)
    return index


def unit_matches(pool: Mapping[Tuple[str, str], set], unit: Unit) -> bool:
    """这条期望在给定池子里命中了吗（按位置桶用不同的比较粒度）。"""

    if unit.position == POSITION_BLANK:
        return False
    lines = pool.get((unit.file, unit.platform_code))
    if lines is None:
        return False
    if unit.position == POSITION_LINE:
        return unit.line in lines
    if unit.position == POSITION_SCOPE:
        return any(item is not None and unit.scope_start <= item <= unit.scope_end for item in lines)
    # 文件级：只对**真的没有位置**（契约里 line == 0）的期望成立；有位置的期望进不了这个桶。
    return unit.line <= 0 and bool(lines)


def item_matched_by_units(units: Sequence[Unit], file: str, code: str, line: Optional[int]) -> bool:
    """这条诊断/违规被某条期望覆盖了吗（期望侧的反向查询）。"""

    for unit in units:
        if unit.file != file or unit.platform_code != code:
            continue
        if unit.position == POSITION_BLANK:
            continue
        if unit.position == POSITION_LINE:
            if line is not None and line == unit.line:
                return True
        elif unit.position == POSITION_SCOPE:
            if line is not None and unit.scope_start <= line <= unit.scope_end:
                return True
        elif unit.line <= 0:
            return True
    return False


def rules_by_id(rules: RuleSet) -> dict[str, Rule]:
    return {rule.id: rule for rule in rules.rules}


def position_breakdown(units: Sequence[Unit], pool: Mapping[Tuple[str, str], set]) -> Mapping[str, Any]:
    """三个位置桶各自的条数与命中（**分桶报告，绝不混算**）。"""

    result: dict[str, Any] = {}
    # 只报**正例**的三个位置桶；负例（blank）单独在 negative_control 里，
    # 混进来会让"位置分布"多出一个不该有的读数。
    for bucket in (POSITION_LINE, POSITION_SCOPE, POSITION_FILE):
        selected = [unit for unit in units if unit.position == bucket]
        matched = sum(1 for unit in selected if unit_matches(pool, unit))
        result[bucket] = {
            "expectations": len(selected),
            "matched": matched,
            "unmatched": len(selected) - matched,
            "rate": ratio(matched, len(selected)),
        }
    return result


def compute_l1a(units: Sequence[Unit], outcomes: Sequence[DatasetOutcome]) -> Mapping[str, Any]:
    """L1a：原始 ruff 诊断 vs 上游标注（**只报告**，不进任何门槛）。"""

    active = [unit for unit in units if unit.classification != CLASS_BLANK]
    blank = [unit for unit in units if unit.classification == CLASS_BLANK]
    diagnostics = [item for outcome in outcomes for file in outcome.files for item in file.diagnostics]
    pool = pool_index((item.file, item.code, item.line) for item in diagnostics)

    by_code: dict[str, dict[str, Any]] = {}
    unmatched: dict[str, int] = {}
    for item in diagnostics:
        entry = by_code.setdefault(
            item.code,
            {
                "code": item.code,
                "upstream_codes": [],
                "diagnostics": 0,
                "diagnostics_matched": 0,
                "expectations": {POSITION_LINE: 0, POSITION_SCOPE: 0, POSITION_FILE: 0},
                "matched": {POSITION_LINE: 0, POSITION_SCOPE: 0, POSITION_FILE: 0},
            },
        )
        entry["diagnostics"] += 1
        hit = item_matched_by_units(active, item.file, item.code, item.line)
        if hit:
            entry["diagnostics_matched"] += 1
        else:
            unmatched[item.code] = unmatched.get(item.code, 0) + 1
    for unit in active:
        entry = by_code.setdefault(
            unit.platform_code,
            {
                "code": unit.platform_code,
                "upstream_codes": [],
                "diagnostics": 0,
                "diagnostics_matched": 0,
                "expectations": {POSITION_LINE: 0, POSITION_SCOPE: 0, POSITION_FILE: 0},
                "matched": {POSITION_LINE: 0, POSITION_SCOPE: 0, POSITION_FILE: 0},
            },
        )
        if unit.upstream_code not in entry["upstream_codes"]:
            entry["upstream_codes"].append(unit.upstream_code)
        entry["expectations"][unit.position] += 1
        if unit_matches(pool, unit):
            entry["matched"][unit.position] += 1

    codes: list[Mapping[str, Any]] = []
    for code in sorted(by_code):
        entry = by_code[code]
        line_expectations = entry["expectations"][POSITION_LINE]
        line_matched = entry["matched"][POSITION_LINE]
        codes.append(
            {
                "code": code,
                "upstream_codes": sorted(entry["upstream_codes"]),
                "diagnostics": entry["diagnostics"],
                "diagnostics_matched": entry["diagnostics_matched"],
                "diagnostics_unmatched": entry["diagnostics"] - entry["diagnostics_matched"],
                "precision": ratio(entry["diagnostics_matched"], entry["diagnostics"]),
                "expectations_line": line_expectations,
                "matched_line": line_matched,
                "recall_line": ratio(line_matched, line_expectations),
                "expectations_scope": entry["expectations"][POSITION_SCOPE],
                "matched_scope": entry["matched"][POSITION_SCOPE],
                "expectations_file": entry["expectations"][POSITION_FILE],
                "matched_file": entry["matched"][POSITION_FILE],
            }
        )

    matched_diagnostics = sum(entry["diagnostics_matched"] for entry in by_code.values())
    total_diagnostics = sum(entry["diagnostics"] for entry in by_code.values())
    blank_inside = sum(
        1
        for item in diagnostics
        if any(
            item.file == scope.file
            and item.line is not None
            and scope.scope_start <= item.line <= scope.scope_end
            for outcome in outcomes
            for scope in outcome.blank_scopes
        )
    )
    return {
        "definition": (
            "L1a = 原始 ruff check --output-format=json 的诊断 vs 上游标注：度量**证据工具与上游标注**的差，"
            "只报告、不进任何门槛（它算不到平台的账上）"
        ),
        "expectations_by_position": position_breakdown(active, pool),
        "diagnostics_total": total_diagnostics,
        "diagnostics_matched": matched_diagnostics,
        "diagnostics_unmatched": total_diagnostics - matched_diagnostics,
        "diagnostics_without_location": sum(1 for item in diagnostics if item.line is None),
        "precision": ratio(matched_diagnostics, total_diagnostics),
        "recall_line": ratio(
            sum(entry["matched"][POSITION_LINE] for entry in by_code.values()),
            sum(entry["expectations"][POSITION_LINE] for entry in by_code.values()),
        ),
        "unmatched_by_code": dict(sorted(unmatched.items())),
        "blank_expectations": {
            "expectations": len(blank),
            "diagnostics_inside": blank_inside,
            "note": (
                "上游的空白期望标记（thresholds 的 blank_code_tokens）是负例：它不映射任何规则，"
                "这里只报它覆盖到多少条诊断；这些诊断同时也算在 unmatched 里，counts 不重复相加"
            ),
        },
        "by_code": codes,
        "coverage_caveats": coverage_caveats(outcomes),
    }


def coverage_caveats(outcomes: Sequence[DatasetOutcome]) -> list[Mapping[str, Any]]:
    """会让读数失真但**必须显式写出来**的事实（截断、跑不成、文件缺失）。"""

    caveats: list[Mapping[str, Any]] = []
    for outcome in outcomes:
        for file in outcome.files:
            if file.raw_error:
                caveats.append({"dataset": outcome.dataset, "file": file.file, "what": "raw_ruff", "detail": file.raw_error})
            if file.pipeline_error:
                caveats.append(
                    {"dataset": outcome.dataset, "file": file.file, "what": "pipeline", "detail": file.pipeline_error}
                )
            if file.truncated:
                caveats.append(
                    {
                        "dataset": outcome.dataset,
                        "file": file.file,
                        "what": "evidence_truncated",
                        "detail": "验证器证据被截断 " + str(file.truncated) + " 条：召回率可能因此偏低",
                    }
                )
            if file.blockers:
                caveats.append(
                    {
                        "dataset": outcome.dataset,
                        "file": file.file,
                        "what": "blockers",
                        "detail": "本次有 " + str(file.blockers) + " 个阻断点（失败关闭），见 failure_closed_violations",
                    }
                )
    return caveats

def compute_l1b(
    units: Sequence[Unit],
    records: Sequence[AnnotationRecord],
    outcomes: Sequence[DatasetOutcome],
    owners: CodeOwners,
    rules: RuleSet,
    suite: FidelitySuite,
    blank_tokens: Sequence[str] = (),
) -> Mapping[str, Any]:
    """L1b：平台判定 vs **同一次**原始 ruff 诊断（GV-01/02/03 都定义在这里）。"""

    known = rules_by_id(rules)
    diagnostics = [item for outcome in outcomes for file in outcome.files for item in file.diagnostics]
    expected: Counter = Counter()
    for item in diagnostics:
        for rule in owners.rules_for(item.code):
            expected[(rule.id, item.code, item.file, item.line)] += 1

    actual: Counter = Counter()
    actual_rows: list[Tuple[Any, str, str]] = []
    for outcome in outcomes:
        for file in outcome.files:
            for violation in file.style_violations:
                code = posix(violation.evidence.value).upper()
                target = posix(violation.evidence.file or violation.evidence.subject) or file.file
                actual[(violation.rule_id, code, target, violation.evidence.line)] += 1
                actual_rows.append((violation, code, target))

    true_positive = expected & actual
    false_positive = actual - expected
    false_negative = expected - actual

    def per_rule(counter: Counter, field_name: str) -> Counter:
        result: Counter = Counter()
        for (rule_id, _code, _file, _line), count in counter.items():
            result[rule_id] += count
        return result

    tp_by_rule = per_rule(true_positive, "tp")
    fp_by_rule = per_rule(false_positive, "fp")
    fn_by_rule = per_rule(false_negative, "fn")

    # 样本量 N = 能映射到该规则的**行级**标注条数（按标注计，不按 expected_lines 展开计）。
    annotations_line: Counter = Counter()
    annotations_scope: Counter = Counter()
    annotations_file: Counter = Counter()
    for record in records:
        if record.classification != CLASS_MAPPED:
            continue
        bucket = annotations_line if record.position == POSITION_LINE else (
            annotations_scope if record.position == POSITION_SCOPE else annotations_file
        )
        for rule in owners.rules_for(record.platform_code):
            bucket[rule.id] += 1

    rule_ids = sorted(
        {key[0] for key in expected}
        | {key[0] for key in actual}
        | set(annotations_line)
        | set(annotations_scope)
        | set(annotations_file)
    )
    per_rule_rows: list[Mapping[str, Any]] = []
    for rule_id in rule_ids:
        rule = known.get(rule_id)
        codes = sorted(
            posix(code) for code, owners_list in owners.owners.items() if any(item.id == rule_id for item in owners_list)
        )
        tp = int(tp_by_rule.get(rule_id, 0))
        fp = int(fp_by_rule.get(rule_id, 0))
        fn = int(fn_by_rule.get(rule_id, 0))
        sample_n = int(annotations_line.get(rule_id, 0))
        if sample_n == 0:
            sample_status = SAMPLE_NO_LABELS
        elif sample_n < suite.min_annotations_per_rule:
            sample_status = SAMPLE_INSUFFICIENT
        else:
            sample_status = SAMPLE_OK
        measured = bool(tp or fp or fn)
        per_rule_rows.append(
            {
                "rule_id": rule_id,
                "severity": None if rule is None else rule.severity.value,
                "codes": codes,
                "annotations_line": sample_n,
                "annotations_scope": int(annotations_scope.get(rule_id, 0)),
                "annotations_file": int(annotations_file.get(rule_id, 0)),
                "n": sample_n,
                "sample_status": sample_status,
                "l1b_status": "measured" if measured else "no_l1b_events",
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": ratio(tp, tp + fp),
                "recall": ratio(tp, tp + fn),
                "precision_ci": interval_payload(tp, tp + fp),
                "recall_ci": interval_payload(tp, tp + fn),
            }
        )

    gated = [
        row
        for row in per_rule_rows
        if row["sample_status"] == SAMPLE_OK and row["l1b_status"] == "measured"
    ]

    def aggregate_precision(rows: Sequence[Mapping[str, Any]]) -> Optional[float]:
        tp = sum(int(row["tp"]) for row in rows)
        fp = sum(int(row["fp"]) for row in rows)
        return ratio(tp, tp + fp)

    def aggregate_recall(rows: Sequence[Mapping[str, Any]]) -> Optional[float]:
        tp = sum(int(row["tp"]) for row in rows)
        fn = sum(int(row["fn"]) for row in rows)
        return ratio(tp, tp + fn)

    error_rows = [row for row in gated if row["severity"] == "error"]
    warning_rows = [row for row in gated if row["severity"] == "warning"]
    other_rows = [row for row in per_rule_rows if row not in gated]

    # 归属准确率（GV-03）：每一次平台命中，它的 rule_id 必须是该码的声明归属者之一。
    misattributed: list[Mapping[str, Any]] = []
    attributed = 0
    for (rule_id, code, file, line), count in actual.items():
        if any(item.id == rule_id for item in owners.rules_for(code)):
            attributed += count
        else:
            misattributed.append(
                {"rule_id": rule_id, "code": code, "file": file, "line": line, "count": count}
            )
    total_actual = sum(actual.values())

    # 分级 / 证据传递：只在**配对成功**的命中上判定（配对键已含 rule/code/file/line，
    # 所以这三项不可能不一致——真正带信息的是下面这些不变量，写清楚免得被读成"三项都验过了"）。
    severity_ok = 0
    message_ok = 0
    detail_ok = 0
    location_ok = 0
    matched_rows = 0
    for violation, code, target in actual_rows:
        if (violation.rule_id, code, target, violation.evidence.line) not in true_positive:
            continue
        matched_rows += 1
        rule = known.get(violation.rule_id)
        if rule is not None and violation.severity == rule.severity:
            severity_ok += 1
        if rule is not None and violation.message == rule.message:
            message_ok += 1
        if posix(violation.evidence.detail):
            detail_ok += 1
        if posix(violation.evidence.file) and violation.evidence.line is not None:
            location_ok += 1

    # 多重性：同一行同一个码报两次就是两条，平台必须逐条转述（actual 与 expected 作为**多重集**相等）。
    # "同键出现两次"本身不是重复缺陷——ruff 对 import a, b 就会在同一行报两条 F401。
    extra_copies = false_positive
    missing_copies = false_negative
    truncated = sum(file.truncated for outcome in outcomes for file in outcome.files)

    # 同一次核对：平台自己的证据投影 vs 原始诊断推出的对子。
    evidence_pairs: Counter = Counter()
    for outcome in outcomes:
        for file in outcome.files:
            for rule_id, code, target, line in file.evidence_pairs:
                evidence_pairs[(rule_id, code, target, line)] += 1
    same_run_missing = expected - evidence_pairs
    same_run_extra = evidence_pairs - expected

    return {
        "definition": (
            "L1b = 平台判定 vs **同一次**原始 ruff 诊断：度量归属 / 分级 / 聚合 / 证据传递是否忠实。"
            "GV-01 / GV-02 / GV-03 **都定义在这一跳上**"
        ),
        "scope": (
            "分母只有 evidence.kind == style_lint 的违规（ruff 这条证据链）；失败关闭与其他 checker 的违规单列"
        ),
        "expected_pairs": sum(expected.values()),
        "actual_pairs": total_actual,
        "tp": sum(true_positive.values()),
        "fp": sum(false_positive.values()),
        "fn": sum(false_negative.values()),
        "precision": ratio(sum(true_positive.values()), sum(true_positive.values()) + sum(false_positive.values())),
        "recall": ratio(sum(true_positive.values()), sum(true_positive.values()) + sum(false_negative.values())),
        "false_positive_detail": [
            {"rule_id": key[0], "code": key[1], "file": key[2], "line": key[3], "count": count}
            for key, count in sorted(false_positive.items())
        ][:50],
        "false_negative_detail": [
            {"rule_id": key[0], "code": key[1], "file": key[2], "line": key[3], "count": count}
            for key, count in sorted(false_negative.items())
        ][:50],
        "blank_exclusion": {
            "note": (
                "空白期望（负例，thresholds 的 blank_code_tokens）不进 GV-01/02 的任何分母："
                "expected 只由「原始诊断 × 规则归属」推出，而负例标记不归属任何规则；"
                "样本量 N 与粒度三档也只数 mapped。负例自己的读数在 negative_control（GV-FPneg）里"
            ),
            "blank_tokens": sorted(posix(token).upper() for token in blank_tokens),
            "expected_pairs_with_blank_code": sum(
                count for key, count in expected.items() if key[1] in {posix(t).upper() for t in blank_tokens}
            ),
            "sample_rows_with_blank_code": 0,
        },
        "per_rule": per_rule_rows,
        "gated_rules": [row["rule_id"] for row in gated],
        "ungated_rules": [
            {"rule_id": row["rule_id"], "sample_status": row["sample_status"], "l1b_status": row["l1b_status"]}
            for row in other_rows
        ],
        "aggregates": {
            "error_level": {
                "rules": [row["rule_id"] for row in error_rows],
                "tp": sum(int(row["tp"]) for row in error_rows),
                "fp": sum(int(row["fp"]) for row in error_rows),
                "fn": sum(int(row["fn"]) for row in error_rows),
                "precision": aggregate_precision(error_rows),
                "recall": aggregate_recall(error_rows),
            },
            "warning_level": {
                "rules": [row["rule_id"] for row in warning_rows],
                "tp": sum(int(row["tp"]) for row in warning_rows),
                "fp": sum(int(row["fp"]) for row in warning_rows),
                "fn": sum(int(row["fn"]) for row in warning_rows),
                "precision": aggregate_precision(warning_rows),
                "recall": aggregate_recall(warning_rows),
            },
            "overall": {
                "rules": [row["rule_id"] for row in gated],
                "tp": sum(int(row["tp"]) for row in gated),
                "fp": sum(int(row["fp"]) for row in gated),
                "fn": sum(int(row["fn"]) for row in gated),
                "precision": aggregate_precision(gated),
                "recall": aggregate_recall(gated),
            },
        },
        "invariants": {
            "note": (
                "配对键是 (rule_id, code, file, line)，所以这三项按构造不会不一致；"
                "下面这些才是真正带信息的核对（分级 / 措辞 / 证据内容 / 位置完整性 / 重复）"
            ),
            "matched_hits": matched_rows,
            "severity_matches_rule": {"correct": severity_ok, "total": matched_rows, "rate": ratio(severity_ok, matched_rows)},
            "message_matches_rule": {"correct": message_ok, "total": matched_rows, "rate": ratio(message_ok, matched_rows)},
            "evidence_detail_present": {"correct": detail_ok, "total": matched_rows, "rate": ratio(detail_ok, matched_rows)},
            "evidence_location_complete": {
                "correct": location_ok,
                "total": matched_rows,
                "rate": ratio(location_ok, matched_rows),
            },
            "multiplicity": {
                "note": "逐条转述工具的多重性：actual 与 expected 作为多重集相等才叫忠实",
                "multiset_equal": not extra_copies and not missing_copies,
                "extra_copies": sum(extra_copies.values()),
                "missing_copies": sum(missing_copies.values()),
                "extra_detail": [
                    {"rule_id": key[0], "code": key[1], "file": key[2], "line": key[3], "count": count}
                    for key, count in sorted(extra_copies.items())
                ][:20],
            },
            "truncated_evidence": {"count": truncated},
        },
        "gv03": {
            "definition": "GV-03 归属准确率 = 命中行的 rule_id 与码的声明归属一致的比例，**必须为 1.00**（错归属 = 公示了错误的理由）",
            "denominator": total_actual,
            "attributed": attributed,
            "accuracy": ratio(attributed, total_actual),
            "misattributed": misattributed[:50],
        },
        "same_run_check": {
            "note": "平台自己的证据投影必须与原始诊断推出的对子逐条对得上，否则两侧不是同一批诊断",
            "consistent": not same_run_missing and not same_run_extra,
            "missing_from_evidence": [
                {"rule_id": key[0], "code": key[1], "file": key[2], "line": key[3], "count": count}
                for key, count in sorted(same_run_missing.items())
            ][:50],
            "extra_in_evidence": [
                {"rule_id": key[0], "code": key[1], "file": key[2], "line": key[3], "count": count}
                for key, count in sorted(same_run_extra.items())
            ][:50],
        },
    }


def compute_gv04(
    units: Sequence[Unit],
    outcomes: Sequence[DatasetOutcome],
    owners: CodeOwners,
    suite: FidelitySuite,
) -> Mapping[str, Any]:
    """GV-04：标注为阳性、却既无 violation 也无 skipped_rules / language_coverage 说明的占比。"""

    diagnostics = pool_index(
        (item.file, item.code, item.line) for outcome in outcomes for file in outcome.files for item in file.diagnostics
    )
    coverage_by_file: dict[str, str] = {}
    structural_by_file: dict[str, set] = {}
    actual_by_location: dict[Tuple[str, str, Optional[int]], set] = {}
    for outcome in outcomes:
        for file in outcome.files:
            coverage_by_file[file.file] = file.coverage_status
            structural_by_file[file.file] = set(file.skipped_structural_rule_ids)
            for violation in file.style_violations:
                code = posix(violation.evidence.value).upper()
                target = posix(violation.evidence.file or violation.evidence.subject) or file.file
                actual_by_location.setdefault((target, code, violation.evidence.line), set()).add(violation.rule_id)

    active = [
        unit
        for unit in units
        if unit.position == POSITION_LINE and unit.classification == CLASS_MAPPED
    ]
    silent: list[Mapping[str, Any]] = []
    tool_positive = 0
    explained_violation = 0
    explained_skip = 0
    explained_coverage = 0
    tool_silent: list[Mapping[str, Any]] = []
    for unit in active:
        owner_ids = {rule.id for rule in owners.rules_for(unit.platform_code)}
        lines = diagnostics.get((unit.file, unit.platform_code))
        has_tool_positive = bool(lines) and unit.line in lines
        if has_tool_positive:
            tool_positive += 1
        if owner_ids & actual_by_location.get((unit.file, unit.platform_code, unit.line), set()):
            explained_violation += 1
            continue
        if owner_ids & structural_by_file.get(unit.file, set()):
            explained_skip += 1
            continue
        status = coverage_by_file.get(unit.file, "")
        if status and status != "covered":
            explained_coverage += 1
            continue
        record = {
            "dataset": unit.dataset,
            "file": unit.file,
            "code": unit.platform_code,
            "upstream_code": unit.upstream_code,
            "line": unit.line,
            "owner_rules": sorted(owner_ids),
            "tool_reported_this_location": has_tool_positive,
        }
        silent.append(record)
        if not has_tool_positive:
            tool_silent.append(record)

    total = len(active)
    platform_attributable = tool_positive
    platform_silent = len(silent) - len(tool_silent)
    return {
        "definition": (
            "GV-04 静默漏报率 = 行级、可映射的阳性标注里，既没有 violation、也没有 skipped_rules（按 rule.scope 与 "
            "context 的**结构化**比对）或 language_coverage 说明的占比；必须为 0"
        ),
        "denominator": total,
        "explained_by_violation": explained_violation,
        "explained_by_structural_skip": explained_skip,
        "explained_by_language_coverage": explained_coverage,
        "silent": len(silent),
        "silent_examples": silent[:50],
        "rate": ratio(len(silent), total),
        "platform_attributable": {
            "definition": (
                "门槛用的分母：标注码在**同一次原始 ruff 诊断里真的出现过**（平台确实拿到过这条阳性证据）"
            ),
            "denominator": platform_attributable,
            "silent": platform_silent,
            "rate": ratio(platform_silent, platform_attributable),
            "note": (
                "tool_silent 的那部分（= 上游标注了、ruff 自己就没报）属于 L1a 的差，"
                "方案明说那不是平台的责任；把它算进门槛就是拿 L1a 解释 L1b"
            ),
        },
        "including_tool_differences": {
            "denominator": total,
            "silent": len(silent),
            "rate": ratio(len(silent), total),
            "tool_silent": len(tool_silent),
            "tool_silent_examples": tool_silent[:50],
        },
    }

def compute_negative_control(
    blank_scopes: Sequence[BlankScope],
    outcomes: Sequence[DatasetOutcome],
    owners: CodeOwners,
    blank_tokens: Sequence[str],
) -> Mapping[str, Any]:
    """负例控制读数：上游 Okay 作用域内报出的**已声明码**诊断/违规 = 误报。

    它是"误报控制"，不是"检出率"，因此**与 GV-01 / GV-02 分开报**（Lead 2026-10-07 裁定）。
    没有预注册门槛 -> 只报告，不参与任何判据。
    """

    declared = set(owners.owners)
    scopes_by_file: dict[str, list[BlankScope]] = {}
    for scope in blank_scopes:
        scopes_by_file.setdefault(scope.file, []).append(scope)

    def covering(file: str, line: Optional[int]) -> Optional[BlankScope]:
        if line is None:
            return None
        for scope in scopes_by_file.get(file, ()):
            if scope.scope_start <= line <= scope.scope_end:
                return scope
        return None

    ruff_by_code: Counter = Counter()
    platform_by_code: Counter = Counter()
    inside_any = 0
    details: list[Mapping[str, Any]] = []
    for outcome in outcomes:
        for file in outcome.files:
            for item in file.diagnostics:
                if covering(item.file, item.line) is None:
                    continue
                inside_any += 1
                if item.code in declared:
                    ruff_by_code[item.code] += 1
                    details.append(
                        {"side": "ruff", "file": item.file, "line": item.line, "code": item.code}
                    )
            for violation in file.style_violations:
                code = posix(violation.evidence.value).upper()
                if covering(file.file, violation.evidence.line) is None:
                    continue
                if code in declared:
                    platform_by_code[code] += 1
                    details.append(
                        {
                            "side": "platform",
                            "file": file.file,
                            "line": violation.evidence.line,
                            "code": code,
                            "rule_id": violation.rule_id,
                        }
                    )
    return {
        "metric": "GV-FPneg",
        "definition": (
            "负例控制读数：上游空白期望标记（"
            + " / ".join(sorted(blank_tokens))
            + "）的作用域内，报出的**已声明码**诊断（ruff 侧）与违规（平台侧）都算误报；"
            "与 GV-01/02 分开报，且**没有预注册门槛**、不参与判定"
        ),
        "scope_semantics": (
            "作用域沿用语料层的 annotation_scopes：[scope_start, scope_end] 闭区间，"
            "标记行本身不属于作用域（见 tools/eval_corpus.py 的 _self_check 口径）"
        ),
        "scopes": len(blank_scopes),
        "files": len(scopes_by_file),
        "diagnostics_inside_any_code": inside_any,
        "ruff": {
            "declared_code_diagnostics": sum(ruff_by_code.values()),
            "by_code": dict(sorted(ruff_by_code.items())),
        },
        "platform": {
            "declared_code_violations": sum(platform_by_code.values()),
            "by_code": dict(sorted(platform_by_code.items())),
        },
        "examples": details[:50],
    }


def compute_coverage_tiers(
    *,
    rules: RuleSet,
    owners: CodeOwners,
    records: Sequence[AnnotationRecord],
    granularity: Mapping[str, Any],
    blank_tokens: Sequence[str],
) -> Mapping[str, Any]:
    """粒度三档 + 与逐规则表的合计对账（Lead 2026-10-07 的验收口径）。

    粒度**当数据读**：声明来自 tools/eval_corpus_extra.py 的 CODE_COVERAGE / ANNOTATION_GRANULARITIES；
    观测来自 annotation_scopes 的结构（line / scope / file 三个位置桶）。
    本文件里**没有第二份粒度表**——只有"怎么把观测到的桶叫成一档"这条映射。
    """

    declared_by_code = {
        item["code"]: item["granularity"] for item in granularity.get("coverage", ())
    }
    counts: dict[str, dict[str, int]] = {}
    for record in records:
        if record.classification in (CLASS_CAPABILITY_OUT, CLASS_UNMAPPED, CLASS_BLANK):
            continue
        for rule in owners.rules_for(record.platform_code):
            slot = counts.setdefault(rule.id, {"line": 0, "scope": 0, "file": 0})
            slot[record.position] = slot.get(record.position, 0) + 1

    rows: list[Mapping[str, Any]] = []
    mismatches: list[Mapping[str, Any]] = []
    for rule in sorted(rules.rules, key=lambda item: item.id):
        codes = sorted(
            code
            for code, rule_list in owners.owners.items()
            if any(item.id == rule.id for item in rule_list)
        )
        declared = sorted({declared_by_code[code] for code in codes if code in declared_by_code})
        observed = counts.get(rule.id, {"line": 0, "scope": 0, "file": 0})
        if observed["line"] > 0:
            tier = "line"
        elif observed["scope"] > 0 and observed["file"] == 0:
            # 有位置可比的作用域、但上游没给精确行：按冻结口径**不进 GV-01/02**，单列。
            tier = "scope"
        elif observed["file"] > 0 and observed["scope"] == 0:
            if declared and set(declared) <= {"definition"}:
                tier = "definition"
            elif declared and set(declared) <= {"file"}:
                tier = "file"
            else:
                tier = "definition_or_file"
        elif observed["file"] > 0 and observed["scope"] > 0:
            tier = "mixed"
        else:
            tier = "none"
        declared_note = "/".join(declared) if declared else "（未在 CODE_COVERAGE 里声明：按 annotation_scopes 的结构推断）"
        consistent = True
        if declared and set(declared) - {"snippet"} and tier == "none":
            consistent = False
            mismatches.append(
                {
                    "rule_id": rule.id,
                    "codes": codes,
                    "declared": declared,
                    "observed": "none",
                    "why": "声明了可测粒度，本次却一条标注都没有",
                }
            )
        rows.append(
            {
                "rule_id": rule.id,
                "severity": rule.severity.value,
                "checker": rule.enforcement.checker or "-",
                "codes": codes,
                "declared_granularity": declared_note,
                "annotations_line": observed["line"],
                "annotations_scope": observed["scope"],
                "annotations_file": observed["file"],
                "tier": tier,
                "consistent": consistent,
            }
        )
    tier_counts: Counter = Counter(row["tier"] for row in rows)
    return {
        "definition": (
            "三档粒度：line（行级，进 GV-01/02/03）/ definition 或 file（只到文件或定义级，单列）/ "
            "none（本次没有任何外部标签，显式列出）；合计必须等于规则总数"
        ),
        "declared_source": {
            "status": granularity.get("status"),
            "path": granularity.get("path"),
            "digest": granularity.get("digest"),
            "reason": granularity.get("reason"),
            "note": "码 -> rule_id 仍然只从 policies/** 推出；这里读的只是**粒度声明**",
        },
        "granularity_semantics": {
            key: value for key, value in (granularity.get("granularities") or {}).items()
        },
        "blank_tokens": sorted(blank_tokens),
        "tier_counts": dict(sorted(tier_counts.items())),
        "tiers": {
            tier: [row["rule_id"] for row in rows if row["tier"] == tier]
            for tier in ("line", "scope", "definition", "file", "definition_or_file", "mixed", "none")
            if any(row["tier"] == tier for row in rows)
        },
        # 三档汇总（Lead 的验收口径：行级 / 只到定义级 / 无标签，合计 = 规则总数）。
        # 这里把"行级"拆成两种口径，因为它们是**两件事**：
        #   - rules_with_line_expectations：有 expected_lines 的规则 = GV-01/02 的行级分母来源；
        #   - rules_with_any_positional：再加"只有作用域"的规则 = "有位置标注"的规则数。
        # 冻结口径规定作用域级**不进** GV-01/02，所以两个数不一样是设计，不是矛盾。
        "positional_rollup": {
            "rules_with_line_expectations": sum(1 for row in rows if row["tier"] == "line"),
            "rules_with_scope_expectations_only": sum(1 for row in rows if row["tier"] == "scope"),
            "rules_with_any_positional_expectations": sum(
                1 for row in rows if row["tier"] in ("line", "scope")
            ),
            "rules_definition_level_only": sum(
                1 for row in rows if row["tier"] in ("definition", "definition_or_file", "file", "mixed")
            ),
            "rules_without_any_labels": sum(1 for row in rows if row["tier"] == "none"),
            "rules_total": len(rows),
            "note": (
                "作用域级（scope）有位置可比性，但按冻结口径不进 GV-01/02；"
                "所以「有位置标注的规则数」通常大于「行级分母的规则数」，两个数都要报"
            ),
        },
        "rule_count": len(rows),
        "reconciles": sum(tier_counts.values()) == len(rules.rules) and len(rules.rules) > 0,
        "cross_check": {"consistent": not mismatches, "mismatches": mismatches},
        "per_rule": rows,
    }


MATERIALIZED_ROOT = ".tmp/eval-corpora-materialized"


def run_materialized(
    *,
    dataset_ids: Sequence[str],
    extra_module: Any,
    corpus_root: Path,
    out_root: Path,
    work_root: Path,
    rules: RuleSet,
    config: Any,
    runner: RuffRunner,
    owners: CodeOwners,
    selected: Sequence[str],
    suite: FidelitySuite,
    granularity: Mapping[str, Any],
) -> Mapping[str, Any]:
    """片段级语料的**文件级**读数（加性、可选；eval_corpus_extra 没导出就跳过）。

    oracle 由 eval-extend 声明为 file_level_code_set：比的是"这个物化文件里该出现的码集合"，
    **不是**行级期望——所以它**不进** GV-01/02 的行级分母，单列一套读数：
    命中 / 未命中 / FP（受测码出现在没有该期望的文件上）/ noise（同一文件上的**其它**已声明码，
    按声明**不算 FP**）。
    """

    block: dict[str, Any] = {
        "status": "not_available",
        "reason": "tools/eval_corpus_extra.py 没有导出 materialize_snippets",
        "datasets": {},
    }
    materialize = getattr(extra_module, "materialize_snippets", None)
    if materialize is None:
        return block
    declared_by_dataset: dict[str, set] = {}
    for item in granularity.get("coverage", ()):
        declared_by_dataset.setdefault(item["dataset"], set()).add(item["code"])
    results: dict[str, Any] = {}
    for dataset_id in dataset_ids:
        tested = sorted(declared_by_dataset.get(dataset_id, set()))
        # 只对**声明为片段级**的数据集物化（粒度当数据读；非片段级语料没有可物化的片段）。
        declared_granularities = {
            item["granularity"] for item in granularity.get("coverage", ()) if item["dataset"] == dataset_id
        }
        if not tested or "snippet" not in declared_granularities:
            continue
        entry: dict[str, Any] = {"dataset": dataset_id, "tested_codes": tested}
        try:
            outcome = materialize(dataset_id, corpus_root=corpus_root, out_root=out_root)
        except Exception as error:  # noqa: BLE001 - 物化不了就写 unavailable
            entry["status"] = "unavailable"
            entry["reason"] = type(error).__name__ + ": " + str(error)
            results[dataset_id] = entry
            continue
        entry.update(
            {
                "status": "available",
                "revision": posix(getattr(outcome, "revision", "")),
                "oracle": posix(getattr(outcome, "oracle", "")),
                "oracle_policy": posix(getattr(outcome, "oracle_policy", "")),
                "candidates": int(getattr(outcome, "candidates", 0)),
                "accepted": int(getattr(outcome, "accepted", 0)),
                "acceptance_rate": getattr(outcome, "acceptance_rate", None),
                "reject_reasons": dict(getattr(outcome, "reject_reasons", {}) or {}),
            }
        )
        file_expectations = dict(getattr(outcome, "file_expectations", {}) or {})
        if not file_expectations:
            entry["status"] = "empty"
            entry["reason"] = "物化结果里没有任何被接受的文件"
            results[dataset_id] = entry
            continue
        workspace = Path(work_root) / ("materialized-" + dataset_id) / "workspace"
        shutil.rmtree(workspace, ignore_errors=True)
        workspace.mkdir(parents=True, exist_ok=True)
        materialized_root = Path(getattr(outcome, "out_root", out_root))
        by_code: dict[str, dict[str, int]] = {code: {"expected": 0, "hit": 0, "missed": 0} for code in tested}
        expected_slots = hit = missed = false_positives = 0
        missed_detail: list[Mapping[str, Any]] = []
        fp_detail: list[Mapping[str, Any]] = []
        noise_by_code: Counter = Counter()
        undeclared_by_code: Counter = Counter()
        platform_mismatch: list[Mapping[str, Any]] = []
        failed_closed: list[Mapping[str, Any]] = []
        for index, (relative, codes) in enumerate(sorted(file_expectations.items())):
            name = Path(relative).name
            source = materialized_root / relative
            target = workspace / name
            try:
                target.write_bytes(source.read_bytes())
            except OSError as error:
                missed_detail.append({"file": relative, "reason": "copy_failed:" + type(error).__name__})
                continue
            expected = {posix(code).upper() for code in codes} & set(tested)
            tmp_dir = Path(work_root) / ("materialized-" + dataset_id) / "tmp" / ("f%04d" % index)
            tmp_dir.mkdir(parents=True, exist_ok=True)
            try:
                diagnostics, _argv = runner.run(workspace=workspace, target=name, tmp_dir=tmp_dir)
            except Unavailable as error:
                missed_detail.append({"file": relative, "reason": "raw_ruff:" + str(error)[:200]})
                continue
            reported = {item.code for item in diagnostics}
            declared_reported = {code for code in reported if owners.declares(code)}
            context_payload: dict[str, Any] = {
                "request_id": "governance-eval-materialized-" + dataset_id + "-" + str(index),
                "file": name,
                "language": suite.context.corpus.language,
                "layer": suite.context.corpus.layer,
            }
            if suite.context.corpus.operation:
                context_payload["operation"] = suite.context.corpus.operation
            context = build_context(context_payload, repo_root=workspace)
            report = run_pipeline(
                PipelineRequest(target=name, workspace=workspace, context=context, rules=rules),
                config=config,
            )
            result = evaluate(rules, context, evidence=report.bundle)
            platform_codes = {
                posix(violation.evidence.value).upper()
                for violation in result.violations
                if classify_violation(violation) == "style_lint"
            }
            unanalyzed = any(
                getattr(judgement, "outcome", "") == "unanalyzed" for judgement in report.judgements
            )
            if unanalyzed:
                # 失败关闭不是"不一致"：ruff 自己说"这个文件我分析不了"，平台据此拒绝判定。
                # 这类文件**单独列出**，不参与 platform==raw 的等值核对（否则会把设计行为读成差）。
                failed_closed.append({"file": relative, "reason": "analysis_failure：ruff 未能分析该文件"})
            elif platform_codes != declared_reported:
                platform_mismatch.append(
                    {"file": relative, "raw": sorted(declared_reported), "platform": sorted(platform_codes)}
                )
            for code in sorted(expected):
                by_code.setdefault(code, {"expected": 0, "hit": 0, "missed": 0})
                by_code[code]["expected"] += 1
                expected_slots += 1
                if code in reported:
                    by_code[code]["hit"] += 1
                    hit += 1
                else:
                    by_code[code]["missed"] += 1
                    missed += 1
                    missed_detail.append({"file": relative, "code": code})
            for code in sorted(declared_reported):
                if code in expected:
                    continue
                if code in set(tested):
                    false_positives += 1
                    fp_detail.append({"file": relative, "code": code, "expected": sorted(expected)})
                else:
                    noise_by_code[code] += 1
            for code in sorted(reported - declared_reported):
                undeclared_by_code[code] += 1
        entry.update(
            {
                "files_measured": len(file_expectations),
                "expected_slots": expected_slots,
                "hit": hit,
                "missed": missed,
                "false_positives": false_positives,
                "noise_findings": sum(noise_by_code.values()),
                "noise_by_code": dict(sorted(noise_by_code.items())),
                "undeclared_by_code": dict(sorted(undeclared_by_code.items())),
                "by_code": dict(sorted(by_code.items())),
                "missed_detail": missed_detail[:50],
                "false_positive_detail": fp_detail[:50],
                "platform_matches_raw": not platform_mismatch,
                "platform_mismatch": platform_mismatch[:20],
                "failed_closed_files": failed_closed[:20],
                "failed_closed_note": (
                    "这些文件 ruff 报 invalid-syntax（本次分析不成立），平台按失败关闭拒绝判定；"
                    "它们不进 platform==raw 的等值核对——那是设计行为，不是转述失真"
                ),
                "sample_note": (
                    "文件级集合比对，**不是行级期望**：不进 GV-01/02；每个码的样本量见 by_code 的 expected，"
                    "低于 thresholds 里 min_annotations_per_rule 的一律按 insufficient_sample 读"
                ),
                "insufficient_sample_codes": [
                    code
                    for code, item in sorted(by_code.items())
                    if item["expected"] < suite.min_annotations_per_rule
                ],
            }
        )
        results[dataset_id] = entry
    block["status"] = "available"
    block["reason"] = ""
    block["datasets"] = results
    block["out_root"] = display(out_root)
    return block


# --------------------------------------------------------------------------- P2 / P3 的本仓库对照扫描


@dataclass
class RepoScanOutcome:
    files: list[str] = field(default_factory=list)
    lines: int = 0
    digest: str = ""
    decisions_full: Mapping[str, int] = field(default_factory=dict)
    decisions_without_p2: Mapping[str, int] = field(default_factory=dict)
    blocks_full: int = 0
    blocks_without_p2: int = 0
    drop_ratio: Optional[float] = None
    findings_by_severity: Mapping[str, int] = field(default_factory=dict)
    findings_by_rule: Mapping[str, int] = field(default_factory=dict)
    failure_closed: int = 0
    other_checker: int = 0
    rule_findings: int = 0
    errors: list[Mapping[str, str]] = field(default_factory=list)
    unavailable: list[Mapping[str, str]] = field(default_factory=list)


def list_repo_files(spec: RepoScanSpec) -> list[str]:
    """扫描文件集：git 的**已跟踪**清单（读数可重放；未跟踪的临时文件不进基线）。"""

    if spec.listing != "git ls-files --cached":
        raise UsageError(
            "repo_scan.listing 只实现了 git ls-files --cached，得到 " + repr(spec.listing)
        )
    output = run_git(["ls-files", "--cached"])
    if output is None:
        raise Unavailable("git ls-files --cached 执行失败：拿不到扫描文件集，绝不猜一个")
    files = []
    for line in output.splitlines():
        relative = posix(line)
        if not relative.endswith(".py"):
            continue
        if any(relative.startswith(prefix) for prefix in spec.exclude_prefixes):
            continue
        files.append(relative)
    return sorted(files)


def run_repo_scan(
    *,
    suite: FidelitySuite,
    rules: RuleSet,
    config: Any,
    work_root: Path,
) -> RepoScanOutcome:
    """本仓库自身的一次扫描：同一批证据 + 两个规则集（P2 的归因方法）。"""

    outcome = RepoScanOutcome()
    if not suite.repo_scan.enabled:
        outcome.unavailable.append({"what": "repo_scan", "reason": "thresholds 里 repo_scan.enabled = false"})
        return outcome
    files = list_repo_files(suite.repo_scan)
    outcome.files = files
    outcome.digest = "sha256:" + hashlib.sha256("\n".join(files).encode("utf-8")).hexdigest()
    p2_rule_id = suite.predictions.P2.rule_id
    reduced = RuleSet(
        rules=tuple(rule for rule in rules.rules if rule.id != p2_rule_id),
        source_paths=rules.source_paths,
    )
    decisions_full: Counter = Counter()
    decisions_reduced: Counter = Counter()
    findings: Counter = Counter()
    per_rule: Counter = Counter()
    context_spec = suite.context.repo_scan
    tmp_root = Path(work_root) / "repo-scan" / "tmp"
    for index, relative in enumerate(files):
        target = REPO_ROOT / relative
        try:
            outcome.lines += len(target.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError) as error:
            outcome.errors.append({"file": relative, "what": "read", "detail": type(error).__name__})
            continue
        layer = infer_layer(relative) if context_spec.layer == "from_filename" else context_spec.layer
        payload: dict[str, Any] = {
            "request_id": "governance-eval-repo-" + str(index),
            "file": relative,
            "language": context_spec.language,
            "layer": layer,
        }
        if context_spec.operation:
            payload["operation"] = context_spec.operation
        tmp_dir = tmp_root / ("f%04d" % index)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            context = build_context(payload, repo_root=REPO_ROOT)
            report = run_pipeline(
                PipelineRequest(target=relative, workspace=REPO_ROOT, context=context, rules=rules),
                config=config,
            )
            evidence = report.bundle
        except Exception as error:  # noqa: BLE001 - 单个文件失败不能把整次扫描变成沉默
            outcome.errors.append(
                {"file": relative, "what": "pipeline", "detail": type(error).__name__ + ": " + str(error)}
            )
            continue
        full = evaluate(rules, context, evidence=evidence)
        without = evaluate(reduced, context, evidence=evidence)
        decisions_full[full.decision.value] += 1
        decisions_reduced[without.decision.value] += 1
        for violation in full.violations:
            bucket = classify_violation(violation)
            if bucket == "failure_closed":
                outcome.failure_closed += 1
                continue
            if bucket == "other_checker":
                outcome.other_checker += 1
            findings[violation.severity.value] += 1
            per_rule[violation.rule_id] += 1

    outcome.decisions_full = dict(sorted(decisions_full.items()))
    outcome.decisions_without_p2 = dict(sorted(decisions_reduced.items()))
    outcome.blocks_full = int(decisions_full.get("block", 0))
    outcome.blocks_without_p2 = int(decisions_reduced.get("block", 0))
    outcome.drop_ratio = ratio(outcome.blocks_full - outcome.blocks_without_p2, outcome.blocks_full)
    outcome.findings_by_severity = dict(sorted(findings.items()))
    outcome.rule_findings = sum(findings.values())
    outcome.findings_by_rule = dict(sorted(per_rule.items()))
    return outcome


# --------------------------------------------------------------------------- 预注册预测对照


def evaluate_predictions(
    suite: FidelitySuite,
    per_rule_rows: Sequence[Mapping[str, Any]],
    scan: RepoScanOutcome,
) -> Mapping[str, Any]:
    """§6.5 的三条预注册预测：跑完对照，**不调参**。"""

    known = {row["rule_id"]: row for row in per_rule_rows}
    p1_spec = suite.predictions.P1
    p1_row = known.get(p1_spec.rule_id)
    p1_observed = None if p1_row is None else p1_row.get("precision")
    p1_repo_hits = int(scan.findings_by_rule.get(p1_spec.rule_id, 0))
    p1 = {
        "statement": p1_spec.statement,
        "metric": p1_spec.metric,
        "operator": p1_spec.operator,
        "threshold": p1_spec.value,
        "falsified_means": p1_spec.falsified_means,
        "corpus": {
            "rule_id": p1_spec.rule_id,
            "codes": list(p1_spec.codes),
            "precision": p1_observed,
            "tp": None if p1_row is None else p1_row["tp"],
            "fp": None if p1_row is None else p1_row["fp"],
            "fn": None if p1_row is None else p1_row["fn"],
            "n": None if p1_row is None else p1_row["n"],
            "sample_status": None if p1_row is None else p1_row["sample_status"],
        },
        "repo_tree": {
            "precision": None,
            "hits": p1_repo_hits,
            "reason": (
                "本仓库这份树上**没有外部标注**：按 R1，平台的 Decision 不得当标签，"
                "所以本仓库侧的精确率算不出来（只报命中数）；方案 §6.5 依据的 10 个命中是人工核对，"
                "那是 L2 的人评，不是 L1 的读数"
            ),
        },
        "comparison_on_corpus": compare(p1_observed, p1_spec.operator, p1_spec.value),
        "usable_for_prediction": False,
        "verdict_note": (
            "这一行**不能**判定 P1，两个理由都写下来：(1) L1b 的精确率只说明平台忠实转述了 ruff——"
            "P1 说的是'这 10 个命中是不是名字启发式误报'，那是 L2 的人评或第二个独立扫描器才回答得了的；"
            "(2) 语料面 SEC-004 的样本量见 sample_status，低于预注册下限时不构成判定。"
            "本仓库面的精确率按 R1 不可算（平台的 Decision 不得当标签），只报命中数。"
        ),
    }

    p2_spec = suite.predictions.P2
    p2 = {
        "statement": p2_spec.statement,
        "metric": p2_spec.metric,
        "operator": p2_spec.operator,
        "threshold": p2_spec.value,
        "falsified_means": p2_spec.falsified_means,
        "rule_id": p2_spec.rule_id,
        "blocks_full": scan.blocks_full,
        "blocks_without_rule": scan.blocks_without_p2,
        "drop_ratio": scan.drop_ratio,
        "attribution_method": suite.repo_scan.attribution_method,
        "verdict": compare(scan.drop_ratio, p2_spec.operator, p2_spec.value),
    }

    p3_spec = suite.predictions.P3
    total = scan.rule_findings
    warning_share = ratio(int(scan.findings_by_severity.get("warning", 0)), total)
    error_share = ratio(int(scan.findings_by_severity.get("error", 0)), total)
    p3 = {
        "statement": p3_spec.statement,
        "metric": p3_spec.metric,
        "falsified_means": p3_spec.falsified_means,
        "findings_by_severity": dict(scan.findings_by_severity),
        "rule_findings": total,
        "warning_share": warning_share,
        "error_share": error_share,
        "warning_threshold": p3_spec.warning_share_value,
        "error_threshold": p3_spec.error_share_value,
        "warning_verdict": compare(warning_share, p3_spec.warning_share_operator, p3_spec.warning_share_value),
        "error_verdict": compare(error_share, p3_spec.error_share_operator, p3_spec.error_share_value),
        "corpus_note": (
            "口径：本仓库自身的已跟踪 Python 文件（thresholds 的 repo_scan 文件集），**不是**"
            "规则转化覆盖报告 §10.4 的 680 文件第三方语料（那份没有可重放的取用路径，tier C 明确"
            "\"不能当基线\"）。跨语料的数字不许直接比较，所以这里不宣称与 §10.4 的 86.4% 可比。"
        ),
    }
    return {
        "note": "方案 §6.5 的预注册预测：跑之前写下，跑完只对照、不调参",
        "P1": p1,
        "P2": p2,
        "P3": p3,
    }

# --------------------------------------------------------------------------- 判定与载荷


def build_verdicts(
    suite: FidelitySuite,
    *,
    l1b: Mapping[str, Any],
    gv04: Mapping[str, Any],
    unavailable: Sequence[Mapping[str, str]],
    lock_problems: Sequence[str],
    ruff_ready: bool,
    repo_scan: RepoScanOutcome,
    files_total: int,
    files_measured: int,
    coverage_tiers: Mapping[str, Any],
) -> Mapping[str, Any]:
    """把读数与预注册门槛比一遍。**未评（None）一律不算通过**。"""

    aggregates = l1b.get("aggregates", {})
    error_level = aggregates.get("error_level", {})
    overall = aggregates.get("overall", {})
    gated = [row for row in l1b.get("per_rule", []) if row["rule_id"] in set(l1b.get("gated_rules", []))]
    recall_failures = [
        {
            "rule_id": row["rule_id"],
            "recall": row["recall"],
            "n": row["n"],
            "tp": row["tp"],
            "fn": row["fn"],
        }
        for row in gated
        if row["recall"] is not None and row["recall"] < suite.gv02_recall_per_rule_min
    ]
    worst_recall = min((row["recall"] for row in gated if row["recall"] is not None), default=None)

    verdicts: dict[str, Any] = {}

    def verdict(name: str, *, observed, operator, threshold, reasons: Sequence[str]) -> None:
        passed = compare(observed, operator, threshold)
        verdicts[name] = {
            "observed": observed,
            "operator": operator,
            "threshold": threshold,
            "pass": passed,
            "status": "unavailable" if passed is None else ("pass" if passed else "fail"),
            "reasons": list(reasons),
        }

    verdict("gv01_precision_error", observed=error_level.get("precision"), operator="gte",
            threshold=suite.gv01_precision_error_min,
            reasons=[] if error_level.get("rules") else ["没有一条 error 级规则同时满足样本下限与可测条件"])
    verdict("gv01_precision_overall", observed=overall.get("precision"), operator="gte",
            threshold=suite.gv01_precision_overall_min,
            reasons=[] if overall.get("rules") else ["没有一条规则同时满足样本下限与可测条件"])
    verdict("gv02_recall_per_rule", observed=worst_recall, operator="gte",
            threshold=suite.gv02_recall_per_rule_min,
            reasons=[
                "未达标的规则：" + ", ".join(
                    sorted(item["rule_id"] + "=" + format(item["recall"], ".3f") for item in recall_failures)
                )
            ] if recall_failures else ([] if gated else ["没有一条规则同时满足样本下限与可测条件"]))
    verdict("gv03_attribution_accuracy", observed=l1b.get("gv03", {}).get("accuracy"), operator="gte",
            threshold=suite.gv03_attribution_accuracy_required,
            reasons=[
                item["rule_id"] + " 把 " + item["code"] + " 归给了自己"
                for item in l1b.get("gv03", {}).get("misattributed", [])[:10]
            ])
    verdict("gv04_silent_miss_rate",
            observed=gv04.get("platform_attributable", {}).get("rate"), operator="lte",
            threshold=suite.gv04_silent_miss_rate_max,
            reasons=[
                "平台侧静默：" + str(gv04.get("platform_attributable", {}).get("silent", 0)) + " 条"
            ])
    verdict("ruff_available", observed=1.0 if ruff_ready else None, operator="gte", threshold=1.0, reasons=[])
    # 语料层说有标注的文件，必须每一个都真的跑过（原始诊断 + 平台流水线）：
    # 少测一个文件就是一处覆盖洞，它会让召回率无声地变好看或变难看。
    verdict(
        "corpus_files_measured",
        observed=ratio(files_measured, files_total),
        operator="gte",
        threshold=1.0,
        reasons=[
            "有 " + str(files_total - files_measured) + " / " + str(files_total)
            + " 个标注文件没跑成（见 coverage_caveats 的 raw_ruff / pipeline 两类）"
        ] if files_measured < files_total else [],
    )
    verdict("corpus_lock", observed=0.0 if lock_problems else 1.0,
            operator="gte", threshold=1.0 if suite.require_corpus_lock else 0.0,
            reasons=list(lock_problems))
    verdict("corpus_available", observed=0.0 if unavailable else 1.0, operator="gte", threshold=1.0,
            reasons=[item["what"] + ": " + item["reason"] for item in unavailable])
    verdict("repo_scan_complete", observed=0.0 if repo_scan.errors else 1.0, operator="gte", threshold=1.0,
            reasons=[item["file"] + ": " + item["detail"] for item in repo_scan.errors[:10]])
    declared_source = coverage_tiers.get("declared_source", {})
    verdict("granularity_declarations",
            observed=1.0 if declared_source.get("status") == "available" else None,
            operator="gte", threshold=1.0,
            reasons=[] if declared_source.get("status") == "available" else [str(declared_source.get("reason"))])
    verdict("coverage_tier_reconcile",
            observed=1.0 if coverage_tiers.get("reconciles") and coverage_tiers.get("cross_check", {}).get("consistent") else 0.0,
            operator="gte", threshold=1.0,
            reasons=[
                item["rule_id"] + "：声明 " + "/".join(item["declared"]) + "，本次观测到 none"
                for item in coverage_tiers.get("cross_check", {}).get("mismatches", [])[:10]
            ] or ([] if coverage_tiers.get("reconciles") else ["三档合计与规则总数对不上"]))
    return verdicts


def baseline_record(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """从一次读数里抽出**可版本化**的稳定部分：口径、门槛、逐规则指标与判据。

    刻意**不含**仓库扫描（P2/P3 是只报告预测；本仓库随每次提交变化，把它放进基线等于让
    每次改代码都触发"漂移"），也不含时间戳 / 树摘要 / 运行 id。
    """

    l1b = payload.get("l1b", {})
    return {
        "suite": payload.get("suite"),
        "governance_eval_schema_version": payload.get("governance_eval_schema_version"),
        "thresholds": {
            "schema_id": payload.get("thresholds", {}).get("schema_id"),
            "version": payload.get("thresholds", {}).get("version"),
            "preregistered_on": payload.get("thresholds", {}).get("preregistered_on"),
        },
        "platform": {
            "rule_set_hash": payload.get("platform", {}).get("rule_set_hash"),
            "policy_version": payload.get("platform", {}).get("policy_version"),
            "ruff_version": payload.get("platform", {}).get("ruff_version"),
            "ruff_config_digest": payload.get("platform", {}).get("ruff_config_digest"),
        },
        "datasets": [
            {
                "id": item.get("id"),
                "revision": item.get("revision"),
                "annotations": item.get("annotations"),
                "classification_counts": item.get("classification_counts"),
                "position_counts": item.get("position_counts"),
                "scopes_source": item.get("scopes_source"),
            }
            for item in payload.get("datasets", [])
        ],
        "l1a": {
            "diagnostics_total": payload.get("l1a", {}).get("diagnostics_total"),
            "diagnostics_matched": payload.get("l1a", {}).get("diagnostics_matched"),
            "diagnostics_unmatched": payload.get("l1a", {}).get("diagnostics_unmatched"),
            "precision": payload.get("l1a", {}).get("precision"),
            "recall_line": payload.get("l1a", {}).get("recall_line"),
            "expectations_by_position": payload.get("l1a", {}).get("expectations_by_position"),
        },
        "l1b": {
            "expected_pairs": l1b.get("expected_pairs"),
            "actual_pairs": l1b.get("actual_pairs"),
            "tp": l1b.get("tp"),
            "fp": l1b.get("fp"),
            "fn": l1b.get("fn"),
            "precision": l1b.get("precision"),
            "recall": l1b.get("recall"),
            "gv03_accuracy": l1b.get("gv03", {}).get("accuracy"),
            "per_rule": [
                {
                    "rule_id": row.get("rule_id"),
                    "n": row.get("n"),
                    "sample_status": row.get("sample_status"),
                    "l1b_status": row.get("l1b_status"),
                    "tp": row.get("tp"),
                    "fp": row.get("fp"),
                    "fn": row.get("fn"),
                    "precision": row.get("precision"),
                    "recall": row.get("recall"),
                }
                for row in l1b.get("per_rule", [])
            ],
        },
        "gv04": {
            "denominator": payload.get("gv04", {}).get("denominator"),
            "rate_including_tool_differences": payload.get("gv04", {}).get("including_tool_differences", {}).get("rate"),
            "platform_attributable": payload.get("gv04", {}).get("platform_attributable"),
        },
        "rules_without_external_labels": payload.get("rules_without_external_labels"),
        "coverage_tier_counts": payload.get("coverage_tiers", {}).get("tier_counts"),
        "capability_out": payload.get("capability_out", {}).get("counts"),
        "unmapped": payload.get("unmapped", {}).get("counts"),
        "verdicts": {name: item.get("pass") for name, item in payload.get("verdicts", {}).items()},
    }


def diff_baseline(recorded: Any, current: Any, path: str = "") -> list[str]:
    """逐字段比对；返回人可读的漂移清单（空 = 一致）。"""

    if isinstance(recorded, Mapping) and isinstance(current, Mapping):
        drift: list[str] = []
        for key in sorted(set(recorded) | set(current)):
            if key not in recorded:
                drift.append(path + "." + str(key) + ": 基线里没有，本次多出来")
                continue
            if key not in current:
                drift.append(path + "." + str(key) + ": 基线里有，本次没有")
                continue
            drift.extend(diff_baseline(recorded[key], current[key], path + "." + str(key)))
        return drift
    if isinstance(recorded, list) and isinstance(current, list):
        drift = []
        if len(recorded) != len(current):
            drift.append(path + ": 长度 " + str(len(recorded)) + " -> " + str(len(current)))
        for index, (left, right) in enumerate(zip(recorded, current)):
            drift.extend(diff_baseline(left, right, path + "[" + str(index) + "]"))
        return drift
    if recorded != current:
        return [path + ": " + json.dumps(recorded, ensure_ascii=False) + " -> " + json.dumps(current, ensure_ascii=False)]
    return []


def render_summary(payload: Mapping[str, Any]) -> str:
    """给人看的摘要（--json 才打印完整载荷）。"""

    lines: list[str] = []
    platform = payload.get("platform", {})
    lines.append(
        "fidelity | rules=" + str(platform.get("rule_count"))
        + " hash=" + str(platform.get("rule_set_hash", ""))[:22]
        + " ruff=" + str(platform.get("ruff_version"))
        + " | " + str(payload.get("result", "?"))
    )
    for dataset in payload.get("datasets", []):
        lines.append(
            "  [" + str(dataset.get("id")) + "] rev=" + str(dataset.get("revision"))[:12]
            + " annotations=" + str(dataset.get("annotations"))
            + " files=" + str(dataset.get("files"))
            + " buckets=" + json.dumps(dataset.get("position_counts"), ensure_ascii=False)
            + " classes=" + json.dumps(dataset.get("classification_counts"), ensure_ascii=False)
        )
    l1a = payload.get("l1a", {})
    buckets = l1a.get("expectations_by_position", {})
    lines.append("")
    lines.append("[L1a] 原始 ruff 诊断 vs 上游标注（只报告）")
    lines.append(
        "  diagnostics=" + str(l1a.get("diagnostics_total"))
        + " matched=" + str(l1a.get("diagnostics_matched"))
        + " unmatched=" + str(l1a.get("diagnostics_unmatched"))
        + " precision=" + fmt(l1a.get("precision"))
    )
    for bucket in ("line", "scope", "file"):
        item = buckets.get(bucket, {})
        lines.append(
            "  " + bucket + ": expectations=" + str(item.get("expectations"))
            + " matched=" + str(item.get("matched"))
            + " rate=" + fmt(item.get("rate"))
        )
    lines.append("")
    lines.append("[L1b] 平台判定 vs 同一次原始 ruff 诊断（GV-01/02/03 定义在这里）")
    l1b = payload.get("l1b", {})
    lines.append(
        "  pairs expected=" + str(l1b.get("expected_pairs")) + " actual=" + str(l1b.get("actual_pairs"))
        + " TP=" + str(l1b.get("tp")) + " FP=" + str(l1b.get("fp")) + " FN=" + str(l1b.get("fn"))
        + " P=" + fmt(l1b.get("precision")) + " R=" + fmt(l1b.get("recall"))
    )
    lines.append("  rule                  sev      N  TP  FP  FN     P      R  sample")
    for row in l1b.get("per_rule", []):
        lines.append(
            "  " + str(row["rule_id"]).ljust(20)
            + " " + str(row["severity"] or "-").ljust(7)
            + " " + str(row["n"]).rjust(3)
            + " " + str(row["tp"]).rjust(3) + " " + str(row["fp"]).rjust(3) + " " + str(row["fn"]).rjust(3)
            + " " + fmt(row["precision"]).rjust(6) + " " + fmt(row["recall"]).rjust(6)
            + "  " + str(row["sample_status"])
        )
    aggregates = l1b.get("aggregates", {})
    for name in ("error_level", "warning_level", "overall"):
        item = aggregates.get(name, {})
        lines.append(
            "  " + name.ljust(14) + " rules=" + str(len(item.get("rules", [])))
            + " TP=" + str(item.get("tp")) + " FP=" + str(item.get("fp")) + " FN=" + str(item.get("fn"))
            + " P=" + fmt(item.get("precision")) + " R=" + fmt(item.get("recall"))
        )
    invariants = l1b.get("invariants", {})
    for name in ("severity_matches_rule", "message_matches_rule", "evidence_detail_present", "evidence_location_complete"):
        item = invariants.get(name, {})
        lines.append("  invariant " + name + ": " + str(item.get("correct")) + "/" + str(item.get("total"))
                     + " rate=" + fmt(item.get("rate")))
    lines.append(
        "  same_run_check consistent=" + str(l1b.get("same_run_check", {}).get("consistent"))
        + " multiplicity_equal=" + str(invariants.get("multiplicity", {}).get("multiset_equal"))
        + " truncated=" + str(invariants.get("truncated_evidence", {}).get("count"))
    )
    gv04 = payload.get("gv04", {})
    attributable = gv04.get("platform_attributable", {})
    including = gv04.get("including_tool_differences", {})
    lines.append("")
    lines.append("[GV-04] 静默漏报")
    lines.append(
        "  门槛分母（平台确实拿到过这条阳性）= " + str(attributable.get("denominator"))
        + " silent=" + str(attributable.get("silent")) + " rate=" + fmt(attributable.get("rate"))
    )
    lines.append(
        "  含工具差（只报告）= " + str(including.get("denominator"))
        + " silent=" + str(including.get("silent")) + " rate=" + fmt(including.get("rate"))
        + " 其中 ruff 本就没报 = " + str(including.get("tool_silent"))
    )
    negative = payload.get("negative_control", {})
    lines.append("")
    lines.append("[GV-FPneg] 负例控制读数（Okay 作用域内的已声明码 = 误报；只报告、无门槛）")
    lines.append(
        "  scopes=" + str(negative.get("scopes")) + " files=" + str(negative.get("files"))
        + " 落在作用域内的诊断（任意码）=" + str(negative.get("diagnostics_inside_any_code"))
        + " ruff 已声明码误报=" + str(negative.get("ruff", {}).get("declared_code_diagnostics"))
        + " 平台已声明码误报=" + str(negative.get("platform", {}).get("declared_code_violations"))
    )
    lines.append("  ruff by_code=" + json.dumps(negative.get("ruff", {}).get("by_code"), ensure_ascii=False))
    lines.append("  平台 by_code=" + json.dumps(negative.get("platform", {}).get("by_code"), ensure_ascii=False))
    materialized = payload.get("snippet_materialization", {})
    lines.append("")
    lines.append("[片段物化] 文件级集合比对（加性读数，不进 GV-01/02）status=" + str(materialized.get("status")))
    for name, item in (materialized.get("datasets") or {}).items():
        if item.get("status") != "available":
            lines.append("  " + name + " status=" + str(item.get("status")) + " reason=" + str(item.get("reason")))
            continue
        lines.append(
            "  " + name + " accepted=" + str(item.get("accepted")) + "/" + str(item.get("candidates"))
            + " rate=" + fmt(item.get("acceptance_rate"))
            + " files=" + str(item.get("files_measured"))
            + " hit=" + str(item.get("hit")) + " missed=" + str(item.get("missed"))
            + " FP=" + str(item.get("false_positives")) + " noise=" + str(item.get("noise_findings"))
            + " platform==raw=" + str(item.get("platform_matches_raw"))
            + " by_code=" + json.dumps(item.get("by_code"), ensure_ascii=False)
        )
    capability = payload.get("capability_out", {})
    unmapped = payload.get("unmapped", {})
    lines.append("")
    lines.append(
        "capability_out（上游码无平台归属）=" + str(capability.get("annotations"))
        + " codes=" + str(capability.get("codes"))
    )
    lines.append(
        "unmapped（平台 select 了但没有规则）=" + str(unmapped.get("codes"))
        + " annotations=" + str(unmapped.get("annotations"))
        + " diagnostics=" + str(unmapped.get("diagnostics"))
    )
    tiers = payload.get("coverage_tiers", {})
    lines.append("")
    lines.append("[粒度三档] 声明来源=" + str(tiers.get("declared_source", {}).get("status"))
                 + " 合计对账=" + str(tiers.get("reconciles"))
                 + " 交叉核对=" + str(tiers.get("cross_check", {}).get("consistent")))
    for tier, members in (tiers.get("tiers") or {}).items():
        lines.append("  " + tier.ljust(18) + " (" + str(len(members)) + ") " + ", ".join(members))
    rollup = tiers.get("positional_rollup") or {}
    lines.append(
        "  三档汇总：行级=" + str(rollup.get("rules_with_line_expectations"))
        + " 只到定义级=" + str(rollup.get("rules_definition_level_only"))
        + " 无标签=" + str(rollup.get("rules_without_any_labels"))
        + " 合计=" + str(rollup.get("rules_total"))
        + "（另有只到作用域的规则 " + str(rollup.get("rules_with_scope_expectations_only")) + " 条）"
    )
    lines.append("无外部标签的规则（不入门槛，显式列出）=" + ", ".join(payload.get("rules_without_external_labels", [])))
    lines.append("L1b 范围外的规则（非 style_lint，没有第三方标注）=" + ", ".join(payload.get("rules_outside_l1b_scope", [])))
    lines.append(
        "失败关闭违规=" + str(len(payload.get("failure_closed_violations", [])))
        + " 其他 checker 违规=" + str(len(payload.get("other_checker_violations", [])))
    )
    predictions = payload.get("predictions", {})
    lines.append("")
    lines.append("[§6.5 预注册预测对照]")
    p1 = predictions.get("P1", {})
    lines.append(
        "  P1 " + str(p1.get("statement")) + " -> 语料精确率=" + fmt(p1.get("corpus", {}).get("precision"))
        + " n=" + str(p1.get("corpus", {}).get("n"))
        + " sample=" + str(p1.get("corpus", {}).get("sample_status"))
        + " comparison=" + str(p1.get("comparison_on_corpus"))
        + " 能否判定=" + str(p1.get("usable_for_prediction"))
        + "（见 --json 的 verdict_note）"
    )
    p2 = predictions.get("P2", {})
    lines.append(
        "  P2 block " + str(p2.get("blocks_full")) + " -> 去掉 " + str(p2.get("rule_id")) + " 后 "
        + str(p2.get("blocks_without_rule")) + " 降幅=" + fmt(p2.get("drop_ratio"))
        + " 判定=" + str(p2.get("verdict"))
    )
    p3 = predictions.get("P3", {})
    lines.append(
        "  P3 findings=" + str(p3.get("rule_findings")) + " warning=" + fmt(p3.get("warning_share"))
        + " error=" + fmt(p3.get("error_share"))
        + " 判定=" + str(p3.get("warning_verdict")) + "/" + str(p3.get("error_verdict"))
    )
    scan = payload.get("repo_scan", {})
    lines.append("")
    lines.append(
        "repo_scan files=" + str(scan.get("file_count")) + " lines=" + str(scan.get("lines"))
        + " decisions=" + json.dumps(scan.get("decisions_full"), ensure_ascii=False)
        + " errors=" + str(len(scan.get("errors", [])))
    )
    lines.append("")
    lines.append("[判据]")
    for name, item in payload.get("verdicts", {}).items():
        lines.append(
            "  " + name.ljust(28) + " " + str(item.get("status")).ljust(11)
            + " observed=" + fmt(item.get("observed")) + " " + str(item.get("operator")) + " " + fmt(item.get("threshold"))
        )
        for reason in item.get("reasons", [])[:5]:
            lines.append("      ! " + str(reason))
    for item in payload.get("unavailable", []):
        lines.append("  UNAVAILABLE " + str(item.get("what")) + ": " + str(item.get("reason")))
    caveats = payload.get("coverage_caveats", [])
    if caveats:
        lines.append("  coverage_caveats=" + str(len(caveats)) + "（截断 / 跑不成 / 阻断点，逐条在 --json 里）")
    return chr(10).join(lines)


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return format(value, ".4f")
    return str(value)

# --------------------------------------------------------------------------- 组装与入口


@dataclass
class SpecFallback:
    """语料层没导出 SOURCES 时的占位（只用于填元数据，读数里会写明）。"""

    id: str
    revision: str = ""
    license: str = ""
    tier: str = ""
    title: str = ""
    registry_ref: str = ""


def reading_context_payload(*, registry_path: Path, layout_path: Path) -> Mapping[str, Any]:
    """读数属于哪棵树 / 哪个环境 / 哪套声明（统一形状只有一份实现）。"""

    declarations = {
        reading.DECLARATION_REGISTRY: reading.declaration_block(registry_path, root=REPO_ROOT),
        reading.DECLARATION_TEST_LAYOUT: reading.declaration_block(layout_path, root=REPO_ROOT),
    }
    return reading.build(
        source=reading.SOURCE_CLI,
        tree=reading.tree_block(REPO_ROOT),
        declarations=declarations,
        host=reading.host_block(),
    )


def run_fidelity(
    *,
    args: argparse.Namespace,
    suite: FidelitySuite,
    thresholds: Thresholds,
    module_path: Path,
    corpus_root: Path,
    lock_dir: Path,
    work_root: Path,
) -> Mapping[str, Any]:
    """跑完整套 fidelity 读数（任何"读不到"都以 Unavailable 抛出，由 main 写成显式读数）。"""

    unavailable: list[Mapping[str, str]] = []
    module = load_corpus_module(module_path)
    available = sorted(str(item) for item in module.available_datasets())
    requested = tuple(args.dataset) if args.dataset else tuple(suite.datasets)
    unknown = [item for item in requested if item not in available]
    if unknown:
        raise Unavailable(
            "请求的数据集不在 available_datasets() 里：" + ", ".join(unknown)
            + "；当前可用：" + (", ".join(available) if available else "（空）")
        )
    if args.fetch:
        for dataset_id in requested:
            module.fetch(dataset_id, root=corpus_root, offline=bool(args.offline))

    rules = load_rule_set([REPO_ROOT / "policies"], repo_root=REPO_ROOT)
    config = load_config(root=REPO_ROOT)
    owners = derive_code_owners(rules)
    selected, toml_facts = read_selected_codes(REPO_ROOT / "validation" / "ruff.toml")
    runner = make_ruff_runner(config, tmp_dir=work_root / "probe", workspace=REPO_ROOT)
    sources = getattr(module, "SOURCES", {}) or {}
    sources_available = bool(sources)
    extra_path = REPO_ROOT / EVAL_CORPUS_EXTRA_PATH
    granularity = load_granularity_data(extra_path)
    granularity_sets = dataset_granularities(granularity)

    outcomes: list[DatasetOutcome] = []
    for dataset_id in requested:
        spec = sources.get(dataset_id) or SpecFallback(dataset_id)
        try:
            outcome = run_dataset(
                spec=spec,
                module=module,
                corpus_root=corpus_root,
                lock_dir=lock_dir,
                work_root=work_root,
                rules=rules,
                config=config,
                runner=runner,
                suite=suite,
                owners=owners,
                selected=selected,
                dataset_granularity_sets=granularity_sets,
                extra_path=extra_path,
            )
        except Exception as error:  # noqa: BLE001 - 一个数据集读不到不许让整份读数消失
            unavailable.append(
                {"what": "dataset:" + dataset_id, "reason": type(error).__name__ + ": " + str(error)}
            )
            continue
        if not outcome.annotations and not outcome.expected_empty:
            unavailable.append(
                {
                    "what": "dataset:" + dataset_id,
                    "reason": "语料层返回 0 条标注，而且没有「设计如此」的粒度声明",
                }
            )
        if outcome.annotations and not outcome.files:
            unavailable.append({"what": "dataset:" + dataset_id, "reason": "没有任何被测文件进入影子工作区"})
        outcomes.extend([outcome])

    all_units = [unit for outcome in outcomes for unit in outcome.units]
    all_records = [record for outcome in outcomes for record in outcome.records]
    l1a = compute_l1a(all_units, outcomes)
    l1b = compute_l1b(
        all_units, all_records, outcomes, owners, rules, suite, blank_tokens=suite.blank_code_tokens
    )
    gv04 = compute_gv04(all_units, outcomes, owners, suite)
    negative_control = compute_negative_control(
        [scope for outcome in outcomes for scope in outcome.blank_scopes],
        outcomes,
        owners,
        suite.blank_code_tokens,
    )
    materialized = run_materialized(
        dataset_ids=list(requested),
        extra_module=granularity.get("module"),
        corpus_root=corpus_root,
        out_root=REPO_ROOT / MATERIALIZED_ROOT,
        work_root=work_root,
        rules=rules,
        config=config,
        runner=runner,
        owners=owners,
        selected=selected,
        suite=suite,
        granularity=granularity,
    )
    coverage_tiers = compute_coverage_tiers(
        rules=rules,
        owners=owners,
        records=all_records,
        granularity=granularity,
        blank_tokens=suite.blank_code_tokens,
    )

    declared_codes = sorted(owners.owners)
    catch_all_rules = sorted(rule.id for rule in owners.catch_all)
    unmapped_codes = [code for code in selected if not owners.declares(code)]
    declared_not_selected = [code for code in sorted(owners.owners) if code not in set(selected)]
    capability_codes = sorted(
        {record.platform_code for record in all_records if record.classification == CLASS_CAPABILITY_OUT}
    )
    unmapped_annotations = sum(
        1 for record in all_records if record.classification == CLASS_UNMAPPED
    )
    unmapped_diagnostics = sum(
        1
        for outcome in outcomes
        for file in outcome.files
        for item in file.diagnostics
        if item.code in set(unmapped_codes)
    )
    failure_closed = [
        {
            "dataset": file.dataset,
            "file": file.file,
            "rule_id": violation.rule_id,
            "severity": violation.severity.value,
            "kind": violation.evidence.kind,
            "value": violation.evidence.value,
            "detail": (violation.evidence.detail or "")[:200],
        }
        for outcome in outcomes
        for file in outcome.files
        for violation in file.failure_closed
    ]
    other_checker = [
        {
            "dataset": file.dataset,
            "file": file.file,
            "rule_id": violation.rule_id,
            "severity": violation.severity.value,
            "kind": violation.evidence.kind,
        }
        for outcome in outcomes
        for file in outcome.files
        for violation in file.other_violations
    ]

    per_rule_rows = list(l1b.get("per_rule", []))
    style_rule_ids = {
        rule.id for rule in rules.rules if (rule.enforcement.checker or "") == STYLE_LINT_KIND
    }
    # "没有外部标签"必须**穷举**：per_rule_rows 里只出现"有标注或有对子"的规则，
    # 直接用它会漏掉那些一次都没出现在读数里的 style_lint 规则（那就是沉默省略）。
    labelled_rules = {
        row["rule_id"] for row in per_rule_rows if row["n"] > 0 or row["annotations_scope"] or row["annotations_file"]
    }
    rules_without_labels = sorted(style_rule_ids - labelled_rules)
    insufficient = sorted(
        row["rule_id"] for row in per_rule_rows if row["sample_status"] == SAMPLE_INSUFFICIENT
    )
    no_l1b_events = sorted(
        row["rule_id"]
        for row in per_rule_rows
        if row["l1b_status"] == "no_l1b_events" and row["rule_id"] in style_rule_ids
    )
    rules_outside = sorted(
        rule.id + "(" + (rule.enforcement.checker or "-") + ")"
        for rule in rules.rules
        if (rule.enforcement.checker or "") != STYLE_LINT_KIND
    )

    if args.skip_repo_scan:
        scan = RepoScanOutcome()
        scan.unavailable.append({"what": "repo_scan", "reason": "--skip-repo-scan 显式跳过"})
    else:
        try:
            scan = run_repo_scan(suite=suite, rules=rules, config=config, work_root=work_root)
        except Unavailable as error:
            scan = RepoScanOutcome()
            scan.unavailable.append({"what": "repo_scan", "reason": str(error)})

    predictions = evaluate_predictions(suite, per_rule_rows, scan)
    lock_problems: list[str] = []
    for outcome in outcomes:
        if outcome.lock.get("present") is False:
            lock_problems.append(
                outcome.dataset + ": 锁文件不存在（" + str(outcome.lock.get("path"))
                + "）——先跑 python tools/eval_corpus.py --record-lock " + outcome.dataset
            )
        elif outcome.lock.get("ok") is not True:
            lock_problems.append(
                outcome.dataset + ": verify 不通过："
                + ("; ".join(outcome.lock.get("problems", ())) or "无问题清单但也没通过")
            )
    measured_files = [file for outcome in outcomes for file in outcome.files]
    files_measured = sum(1 for file in measured_files if not file.raw_error and not file.pipeline_error)
    verdicts = build_verdicts(
        suite,
        l1b=l1b,
        gv04=gv04,
        unavailable=unavailable,
        lock_problems=lock_problems,
        ruff_ready=runner.version is not None,
        repo_scan=scan,
        files_total=len(measured_files),
        files_measured=files_measured,
        coverage_tiers=coverage_tiers,
    )
    passed = all(item["pass"] is True for item in verdicts.values())
    if not outcomes:
        unavailable.append({"what": "fidelity", "reason": "没有任何数据集产出读数"})

    dataset_payload: list[Mapping[str, Any]] = []
    for outcome in outcomes:
        dataset_payload.append(
            {
                "id": outcome.dataset,
                "revision": outcome.revision,
                "license": outcome.license,
                "tier": outcome.tier,
                "title": outcome.title,
                "registry_ref": outcome.registry_ref,
                "corpus_root": outcome.corpus_root,
                "scopes_source": outcome.scopes_source,
                "annotations": outcome.annotations,
                "files": len(outcome.files),
                "files_measured": sum(
                    1 for file in outcome.files if not file.raw_error and not file.pipeline_error
                ),
                "classification_counts": dict(outcome.classification_counts),
                "position_counts": dict(outcome.position_counts),
                "lock": dict(outcome.lock),
                "dir_resolver": outcome.dir_resolver,
                "expected_empty": outcome.expected_empty,
                "empty_reason": outcome.empty_reason,
                "files_cross_check": dict(outcome.files_cross_check),
                "unavailable": [dict(item) for item in outcome.unavailable],
                "l1a": compute_l1a(outcome.units, [outcome]),
                "l1b": compute_l1b(outcome.units, outcome.records, [outcome], owners, rules, suite),
                "negative_control": compute_negative_control(
                    outcome.blank_scopes, [outcome], owners, suite.blank_code_tokens
                ),
            }
        )

    payload: dict[str, Any] = {
        "governance_eval_schema_version": GOVERNANCE_EVAL_SCHEMA_VERSION,
        "suite": SUITE_FIDELITY,
        "plan_ref": thresholds.plan_ref,
        "thresholds": {
            "path": display(REPO_ROOT / THRESHOLDS_PATH),
            "digest": sha256_file(REPO_ROOT / THRESHOLDS_PATH),
            "schema_id": thresholds.schema_id,
            "version": thresholds.version,
            "preregistered_on": thresholds.preregistered_on,
        },
        "definition_note": (
            "GV-01 精确率 / GV-02 召回率 / GV-03 归属准确率 **都定义在 L1b 上**"
            "（平台判定 vs 同一次原始 ruff 诊断）；L1a 只报告，不进任何门槛"
        ),
        "metric_definitions": dict(thresholds.metric_definitions),
        "platform": {
            "revision": None,
            "rule_count": len(rules.rules),
            "rule_set_hash": rules.identity,
            "policy_version": _policy_version(),
            "schema_version": _schema_version(),
            "style_lint_rules": sorted(style_rule_ids),
            "checkers": sorted({rule.enforcement.checker or "-" for rule in rules.rules}),
            "declared_codes": declared_codes,
            "catch_all_style_rules": catch_all_rules,
            "selected_codes": list(selected),
            "selected_but_unmapped": unmapped_codes,
            "declared_but_not_selected": declared_not_selected,
            "ruff_version": runner.version,
            "ruff_config": display(runner.config_path) if runner.config_path else None,
            "ruff_config_digest": sha256_file(runner.config_path) if runner.config_path else None,
            "ruff_argv_template": list(runner.template_argv),
            "ruff_toml_facts": dict(toml_facts),
        },
        "corpus": {
            "module": display(module_path),
            "module_digest": sha256_file(module_path),
            "sources_exported": sources_available,
            "root": display(corpus_root),
            "lock_dir": display(lock_dir),
            "available_datasets": available,
            "measured_datasets": list(requested),
        },
        "datasets": dataset_payload,
        "l1a": l1a,
        "l1b": l1b,
        "gv04": gv04,
        "negative_control": negative_control,
        "coverage_tiers": coverage_tiers,
        "snippet_materialization": materialized,
        "capability_out": {
            "annotations": sum(
                1 for record in all_records if record.classification == CLASS_CAPABILITY_OUT
            ),
            "codes": capability_codes,
            "note": "上游有码、平台没有任何规则声明它：既不算 TP 也不算 FN，**不进任何分母**",
        },
        "unmapped": {
            "codes": unmapped_codes,
            "annotations": unmapped_annotations,
            "diagnostics": unmapped_diagnostics,
            "note": "平台 select 了、却没有任何规则归属的码：只计数、不判定",
        },
        "rules_without_external_labels": rules_without_labels,
        "insufficient_sample_rules": insufficient,
        "rules_without_l1b_events": no_l1b_events,
        "rules_outside_l1b_scope": rules_outside,
        "failure_closed_violations": failure_closed,
        "other_checker_violations": other_checker,
        "coverage_caveats": coverage_caveats(outcomes),
        "predictions": predictions,
        "repo_scan": {
            "file_count": len(scan.files),
            "file_list_digest": scan.digest,
            "lines": scan.lines,
            "decisions_full": dict(scan.decisions_full),
            "decisions_without_p2_rule": dict(scan.decisions_without_p2),
            "blocks_full": scan.blocks_full,
            "blocks_without_p2_rule": scan.blocks_without_p2,
            "drop_ratio": scan.drop_ratio,
            "rule_findings": scan.rule_findings,
            "findings_by_severity": dict(scan.findings_by_severity),
            "findings_by_rule": dict(scan.findings_by_rule),
            "failure_closed_findings": scan.failure_closed,
            "other_checker_findings": scan.other_checker,
            "errors": [dict(item) for item in scan.errors],
            "unavailable": [dict(item) for item in scan.unavailable],
            "method_note": (
                "扫描集 = git ls-files --cached 的 .py（减去 exclude_prefixes）；"
                "归因 = 同一批证据 + 两个规则集（P2 的归因方法写在 thresholds 里）"
            ),
        },
        "verdicts": verdicts,
        "unavailable": [dict(item) for item in unavailable],
        "result": "pass" if passed and not unavailable else "fail",
        "reading_context": reading_context_payload(
            registry_path=config.registry_path, layout_path=config.layout_path
        ),
        "timestamp": reading.utc_now(),
    }
    payload["platform"]["revision"] = payload["reading_context"].get("tree", {}).get("revision")
    return payload


def _policy_version() -> Optional[str]:
    try:
        from policy.models import POLICY_VERSION

        return POLICY_VERSION
    except Exception:  # noqa: BLE001 - 取不到就写 unknown，不猜
        return None


def _schema_version() -> Optional[str]:
    try:
        from policy.models import SCHEMA_VERSION

        return SCHEMA_VERSION
    except Exception:  # noqa: BLE001
        return None


def blocked_payload(
    *,
    thresholds: Thresholds,
    module_path: Path,
    corpus_root: Path,
    unavailable: Sequence[Mapping[str, str]],
) -> Mapping[str, Any]:
    """读不到时的**显式**读数：仍然写文件、仍然写原因、退出码 1。"""

    return {
        "governance_eval_schema_version": GOVERNANCE_EVAL_SCHEMA_VERSION,
        "suite": SUITE_FIDELITY,
        "plan_ref": thresholds.plan_ref,
        "thresholds": {
            "path": display(REPO_ROOT / THRESHOLDS_PATH),
            "digest": sha256_file(REPO_ROOT / THRESHOLDS_PATH),
            "schema_id": thresholds.schema_id,
            "version": thresholds.version,
            "preregistered_on": thresholds.preregistered_on,
        },
        "definition_note": "本次没有产出任何口径读数：原因见 unavailable（**不静默 pass**）",
        "corpus": {
            "module": display(module_path),
            "module_digest": sha256_file(module_path),
            "root": display(corpus_root),
        },
        "datasets": [],
        "l1a": {},
        "l1b": {},
        "gv04": {},
        "predictions": {},
        "repo_scan": {},
        "verdicts": {},
        "unavailable": [dict(item) for item in unavailable],
        "result": "fail",
        "reading_context": reading_context_payload(
            registry_path=REPO_ROOT / "validation" / "validators.yaml",
            layout_path=REPO_ROOT / "validation" / "test-layout.yaml",
        ),
        "timestamp": reading.utc_now(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="governance_eval.py",
        description="规范治理价值评测（当前只实现 --suite fidelity：两跳 L1a/L1b + GV-01..04）",
    )
    parser.add_argument(
        "--suite",
        default=SUITE_FIDELITY,
        help="评测套件；当前只实现 " + SUITE_FIDELITY + "（其余套件会明确报用法错误）",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        default=None,
        metavar="ID",
        help="只测这些数据集（可重复）；默认取 evaluation/thresholds.yaml 里预注册的那几个",
    )
    parser.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT, help="语料根目录（默认 .tmp/eval-corpora）")
    parser.add_argument(
        "--corpus-module",
        default=EVAL_CORPUS_PATH,
        help="语料层契约模块（默认 " + EVAL_CORPUS_PATH + "）；指向别处**只用于自测 harness**，读数里会写明来源",
    )
    parser.add_argument("--lock-dir", default=DEFAULT_LOCK_DIR, help="锁文件目录（默认 evaluation/corpora）")
    parser.add_argument("--fetch", action="store_true", help="先取语料（委托 tools/eval_corpus.py 的 fetch）")
    parser.add_argument("--offline", action="store_true", help="fetch 时离线（不联网）")
    parser.add_argument("--skip-repo-scan", action="store_true", help="跳过 P2/P3 的本仓库对照扫描")
    parser.add_argument("--out", default=None, help="读数输出路径；默认 evaluation/results/fidelity-<revision>.json")
    parser.add_argument("--record", default=None, metavar="PATH", help="把本次读数**显式**记成基线")
    parser.add_argument("--check", default=None, metavar="PATH", help="与记录在案的基线比对，漂移即判据 fail")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE, help="默认基线路径")
    parser.add_argument("--json", action="store_true", help="打印完整载荷")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.suite not in KNOWN_SUITES:
        note = "（已登记但**未实现**）" if args.suite in UNIMPLEMENTED_SUITES else "（未知套件）"
        print(
            "用法错误：--suite " + str(args.suite) + note + "；当前只实现 "
            + ", ".join(KNOWN_SUITES) + "。方案 §7 列出的其余套件尚未实现，不假装支持。",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        thresholds = load_thresholds(REPO_ROOT / THRESHOLDS_PATH)
    except UsageError as error:
        print("配置错误：" + str(error), file=sys.stderr)
        return EXIT_USAGE
    suite = thresholds.suites.get(SUITE_FIDELITY)
    if suite is None:
        print("配置错误：门槛文件里没有 suites." + SUITE_FIDELITY, file=sys.stderr)
        return EXIT_USAGE

    corpus_root = Path(args.corpus_root)
    if not corpus_root.is_absolute():
        corpus_root = REPO_ROOT / corpus_root
    module_path = Path(args.corpus_module)
    if not module_path.is_absolute():
        module_path = REPO_ROOT / module_path
    lock_dir = Path(args.lock_dir)
    if not lock_dir.is_absolute():
        lock_dir = REPO_ROOT / lock_dir
    work_root = REPO_ROOT / WORK_ROOT / ("run-" + uuid.uuid4().hex[:12])

    try:
        payload = run_fidelity(
            args=args,
            suite=suite,
            thresholds=thresholds,
            module_path=module_path,
            corpus_root=corpus_root,
            lock_dir=lock_dir,
            work_root=work_root,
        )
    except Unavailable as error:
        payload = blocked_payload(
            thresholds=thresholds,
            module_path=module_path,
            corpus_root=corpus_root,
            unavailable=[{"what": SUITE_FIDELITY, "reason": str(error)}],
        )
    except UsageError as error:
        print("配置错误：" + str(error), file=sys.stderr)
        return EXIT_USAGE

    # 基线纪律与 tools/retrieval_eval.py 同型：--record 显式重记，漂移即 fail。
    record = json.loads(json.dumps(baseline_record(payload), ensure_ascii=False))
    baseline_path = Path(args.check or args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = REPO_ROOT / baseline_path
    drift: list[str] = []
    if args.record:
        target = Path(args.record)
        if not target.is_absolute():
            target = REPO_ROOT / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
            encoding="utf-8",
            newline=chr(10),
        )
        payload["baseline"] = {"path": display(target), "action": "recorded", "drift": []}
        print("已记录基线: " + display(target))
    elif baseline_path.is_file():
        recorded = json.loads(baseline_path.read_text(encoding="utf-8"))
        drift = diff_baseline(recorded, record)
        payload["baseline"] = {"path": display(baseline_path), "action": "compared", "drift": drift}
        if drift:
            payload["result"] = "fail"
    else:
        payload["baseline"] = {
            "path": display(baseline_path),
            "action": "missing",
            "drift": [],
            "hint": "还没有版本化基线，可用 --record " + DEFAULT_BASELINE + " 记录",
        }

    revision = str(payload.get("platform", {}).get("revision") or payload.get("reading_context", {}).get("tree", {}).get("revision") or "unknown")
    out_path = Path(args.out) if args.out else (Path(RESULTS_DIR) / ("fidelity-" + revision + ".json"))
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_summary(payload))
        if drift:
            print()
            print("与记录在案的基线不一致（需要显式重记基线，或修回行为）：")
            for item in drift[:40]:
                print("  ! " + item)
        print("artifact: " + display(out_path))
    return EXIT_OK if payload.get("result") == "pass" else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())

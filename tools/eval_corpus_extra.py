"""W1-c 支持边界外扩：D / F / N / I / LOG / TRY 六类码的上游语料与期望解析器。

这个模块被 ``tools/eval_corpus.py``（owner=eval-corpus）用 ``importlib.util.spec_from_file_location``
按绝对路径自动发现并合并；它不存在时主模块照常工作。被消费的名字只有两个：

    SOURCES  ->  dict[str, SourceSpec]
    PARSERS  ->  dict[str, Callable[[str, SourceSpec, str], list[Annotation]]]   # key = expectation_kind

本模块只声明**语料与上游期望**，不判定、也不映射到 ``rule_id``：码 → rule_id 由 ``policies/**`` 推出
（方案 §5 W1 的口径），避免第二份真相。

【行号纪律（本模块的核心口径，2026-10-07 实测后定）】

``Annotation.line`` **只承载上游自己声明的位置**：

- ``line > 0``：上游在**这条语料文件内**给出了位置。
  * ``pep8-naming-testsuite``：``#: N801:2:9`` 形态的「相对用例起始行的 行:列」，可换算出绝对行号；
  * ``tryceratops-samples``：测试用 ``assert_violation(line, col, ...)`` 直接断言样例文件内的行号。
- ``line == 0``：上游**没有**给出该语料文件内的位置，语义是「定义级 / 文件级」，不是「行级」：
  * 定义级：pydocstyle 的上游断言是 ``{(definition.name, message)}`` 集合（``src/tests/test_definitions.py:51``），
    全仓没有行号；
  * 文件级：pep8-naming 里没写 ``:line:col`` 的标记（只说「这一段用例违反某码」）。
- **片段级的语料不产出 Annotation**：pyflakes / flake8-logging / isort 的期望挂在**内联代码片段**上
  （``self.flakes('import fu, bar', m.UnusedImport)``、``run(<三引号片段>)`` + ``[(2, 0, "LOG015 ...")]``、
  ``assert isort.code(x) == y``），那里的行号是**片段内相对行号**，不是语料文件的行号。
  把它们写进 ``line`` 就是编造行号，而按文件级采信又会让 GV-01/GV-02 的分母变成噪声
  （``pyflakes/test/test_imports.py`` 这个文件自己的 F401 与片段里的期望毫无关系）。
  所以这三个数据集 ``PARSERS`` 返回空列表，原因写在 ``NO_LINE_ANCHOR_REASONS``，
  解析出的期望条数与片段原文走 ``scan()``（**非契约**导出，供将来的「片段物化」用）。

【本次实测更正了方案 v0.1 的两条说法】

1. 方案 §4.5 写「pydocstyle 期望在 ``src/tests/error_tests.py``」——**不成立**。该文件 48 行，测的是
   ``pydocstyle.violations.Error`` 这个类；真正的期望在 ``src/tests/test_cases/*.py`` 的
   ``@expect("D200: ...")`` 装饰器里，比对方式是 ``{(definition.name, message)}``（**无行号**）。
2. 方案 §4.5 写「pyflakes 期望写在测试代码里」——**成立，但比方案暗示的更弱**：期望是
   ``pyflakes.messages`` 的**消息类**（``m.UnusedImport``），既没有码串也没有行号。

【登记与追溯】

每个 SourceSpec 的 ``revision`` 都钉死到 commit sha；``url`` 是同一 sha 的 codeload tarball；
``archive_root`` 是归档顶层目录名；``paths`` 是**相对 archive_root 的 POSIX 路径（文件或目录前缀）**。
许可用 ``gh api repos/<repo>/contents/<LICENSE>?ref=<sha>`` 核验，原文哈希记在 ``TRANSCRIBED_TABLES``
同一段注释里。GPL / LGPL / other 的语料不得入库；本模块的 6 个上游全部是 MIT/Expat，
按同一条纪律仍然只在运行期取到 ``.tmp/eval-corpora/<id>@<rev>/``，仓库里只提交锁文件。
"""

from __future__ import annotations

import ast
import json
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "ANNOTATION_GRANULARITIES",
    "CODE_COVERAGE",
    "DEFAULT_MATERIALIZED_ROOT",
    "EXPECTATION_FORMATS",
    "MATERIALIZATION_ORACLE",
    "MATERIALIZATION_ORACLE_POLICY",
    "MATERIALIZE_REJECT_REASONS",
    "NO_LINE_ANCHOR_REASONS",
    "PARSERS",
    "SOURCES",
    "TRANSCRIBED_TABLES",
    "MaterializationResult",
    "ScanReport",
    "materialize_snippets",
    "render_report",
    "scan",
]

# --------------------------------------------------------------------------------------
# 1. 语料登记（revision 钉死；许可用 gh api 核验）
# --------------------------------------------------------------------------------------

PYDOCSTYLE_REV = "8d0cdfc93e86e096bb5753f07dc5c7c373e63837"
PYFLAKES_REV = "9f0a7f9c8feb4d086a918a708bb778b38ce7a248"
PEP8_NAMING_REV = "1587bfe4ca73800d64a067580a8f6eb1b8dad209"
FLAKE8_LOGGING_REV = "ee5d482b790ce6b3bddca67f58be9dab8e1e2559"
TRYCERATOPS_REV = "ca149be9a5c6169b77bf70991d2f87661158d283"
ISORT_REV = "92c56855437785000527b70c1476d1ab75dd78fd"


def _codeload(repo: str, sha: str) -> str:
    """钉死 sha 的 codeload tarball（eval_corpus.fetch 直接 urllib 打开这个 URL）。"""

    return "https://codeload.github.com/%s/tar.gz/%s" % (repo, sha)


_AUDITED_ON = "2026-10-07"


@dataclass(frozen=True)
class _FallbackAnnotation:
    """与宿主 tools/eval_corpus.py 的 Annotation **同形**（宿主在时不会用到这个定义）。"""

    dataset: str
    revision: str
    file: str
    line: int
    code: str
    kind: str
    source: str


@dataclass(frozen=True)
class _FallbackSourceSpec:
    """与宿主 tools/eval_corpus.py 的 SourceSpec **同形**（宿主在时不会用到这个定义）。"""

    id: str
    url: str
    revision: str
    license: str
    license_source: str
    tier: str
    expectation_kind: str
    archive_root: str
    paths: tuple[str, ...]
    registry_ref: str


def _bind_host_types() -> tuple[type, type, str]:
    """优先绑定宿主的 Annotation / SourceSpec，保证 isinstance 成立；拿不到就用同形兜底。"""

    seen: list[Any] = []
    registered = sys.modules.get("eval_corpus")
    if registered is not None:
        seen.append(registered)
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and Path(path).name == "eval_corpus.py":
            seen.append(module)
    imported = None
    try:  # tools/ 在 sys.path 上时（CLI 直跑）可以直接 import
        import eval_corpus as module  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - 宿主不在不是错误，下面用同形兜底
        imported = None
    else:
        imported = module
    if imported is not None:
        seen.append(imported)
    for candidate in seen:
        host_annotation = getattr(candidate, "Annotation", None)
        host_spec = getattr(candidate, "SourceSpec", None)
        if isinstance(host_annotation, type) and isinstance(host_spec, type):
            return host_annotation, host_spec, "host"
    return _FallbackAnnotation, _FallbackSourceSpec, "local-fallback"


Annotation, SourceSpec, ANNOTATION_TYPE_SOURCE = _bind_host_types()  # type: ignore[misc]


SOURCES: dict[str, SourceSpec] = {
    "pydocstyle-testcases": SourceSpec(
        id="pydocstyle-testcases",
        url=_codeload("PyCQA/pydocstyle", PYDOCSTYLE_REV),
        revision=PYDOCSTYLE_REV,
        license="MIT",
        license_source=(
            "gh api repos/PyCQA/pydocstyle/contents/LICENSE-MIT?ref=%s -> 1210 B, sha256 "
            "2449878c93af4d10bbdb6618ac26d18877e0b893ecff597532b3867c4458aa93, "
            "首行 'Copyright (c) 2012 GreenSteam'（SPDX: MIT）[%s]"
            % (PYDOCSTYLE_REV, _AUDITED_ON)
        ),
        tier="A",
        expectation_kind="pydocstyle-object-expectation",
        archive_root="pydocstyle-%s" % PYDOCSTYLE_REV,
        paths=("src/tests/test_cases",),
        registry_ref="pydocstyle-testcases",
    ),
    "pyflakes-messages": SourceSpec(
        id="pyflakes-messages",
        url=_codeload("PyCQA/pyflakes", PYFLAKES_REV),
        revision=PYFLAKES_REV,
        license="MIT",
        license_source=(
            "gh api repos/PyCQA/pyflakes/contents/LICENSE?ref=%s -> 1093 B, sha256 "
            "22c47569cc0aae531b372361366818af01c6fc2e314770584a7866c92b3a0463, "
            "首行 'Copyright 2005-2011 Divmod, Inc.'（SPDX: MIT）[%s]"
            % (PYFLAKES_REV, _AUDITED_ON)
        ),
        tier="A",
        expectation_kind="pyflakes-message-expectation",
        archive_root="pyflakes-%s" % PYFLAKES_REV,
        paths=("pyflakes/test", "pyflakes/messages.py"),
        registry_ref="pyflakes-messages",
    ),
    "pep8-naming-testsuite": SourceSpec(
        id="pep8-naming-testsuite",
        url=_codeload("PyCQA/pep8-naming", PEP8_NAMING_REV),
        revision=PEP8_NAMING_REV,
        license="MIT/Expat",
        license_source=(
            "gh api repos/PyCQA/pep8-naming/contents/LICENSE?ref=%s -> 1132 B, sha256 "
            "44bea406fa76e543e465fbfe0ba71029d143ca9a251504fbc8659f3965ab28fb, "
            "第 2 行 'Licensed under the terms of the Expat License'（GitHub 报 NOASSERTION，"
            "原文是 Expat/MIT）[%s]"
            % (PEP8_NAMING_REV, _AUDITED_ON)
        ),
        tier="A",
        expectation_kind="pep8-naming-testsuite-marker",
        archive_root="pep8-naming-%s" % PEP8_NAMING_REV,
        paths=("testsuite",),
        registry_ref="pep8-naming-testsuite",
    ),
    "flake8-logging-tests": SourceSpec(
        id="flake8-logging-tests",
        url=_codeload("adamchainz/flake8-logging", FLAKE8_LOGGING_REV),
        revision=FLAKE8_LOGGING_REV,
        license="MIT",
        license_source=(
            "gh api repos/adamchainz/flake8-logging/contents/LICENSE?ref=%s -> 1069 B, sha256 "
            "267d7bf517e5911657852086b7f0fb6ac2f2d84c78ec2d167411f17b49416b39, "
            "首行 'MIT License'（SPDX: MIT）[%s]"
            % (FLAKE8_LOGGING_REV, _AUDITED_ON)
        ),
        tier="A",
        expectation_kind="flake8-logging-snippet-expectation",
        archive_root="flake8-logging-%s" % FLAKE8_LOGGING_REV,
        paths=("tests",),
        registry_ref="flake8-logging-tests",
    ),
    "tryceratops-samples": SourceSpec(
        id="tryceratops-samples",
        url=_codeload("guilatrova/tryceratops", TRYCERATOPS_REV),
        revision=TRYCERATOPS_REV,
        license="MIT",
        license_source=(
            "gh api repos/guilatrova/tryceratops/contents/LICENSE?ref=%s -> 1084 B, sha256 "
            "6b0961575e0c568062de54e958f32ed03aa176eec5c303a9cae74ae86d2266cd, "
            "首行 'The MIT License (MIT)'（SPDX: MIT）[%s]"
            % (TRYCERATOPS_REV, _AUDITED_ON)
        ),
        tier="A",
        expectation_kind="tryceratops-sample-violation",
        archive_root="tryceratops-%s" % TRYCERATOPS_REV,
        paths=("src/tests", "src/tryceratops/violations/codes.py"),
        registry_ref="tryceratops-samples",
    ),
    "isort-tests": SourceSpec(
        id="isort-tests",
        url=_codeload("PyCQA/isort", ISORT_REV),
        revision=ISORT_REV,
        license="MIT",
        license_source=(
            "gh api repos/PyCQA/isort/contents/LICENSE?ref=%s -> 1089 B, sha256 "
            "063294001c3d523dbacbab9dd54ac229982756ccaf592ca53240b2b0cdd82065, "
            "首行 'The MIT License (MIT)'（SPDX: MIT）[%s]"
            % (ISORT_REV, _AUDITED_ON)
        ),
        tier="A",
        expectation_kind="isort-code-compare",
        archive_root="isort-%s" % ISORT_REV,
        paths=("tests/unit", "tests/integration"),
        registry_ref="isort-tests",
    ),
}

# --------------------------------------------------------------------------------------
# 2. 粒度声明（Lead 的验收口径：每条码显式声明粒度 + 该粒度能证明什么）
# --------------------------------------------------------------------------------------

ANNOTATION_GRANULARITIES: dict[str, str] = {
    "line": (
        "行级：上游在这条语料文件内给出了位置（可直接做行级 P/R）。"
        "能证明：报告位置与上游一致、码归属正确。"
        "不能证明：这条诊断值得报。"
    ),
    "definition": (
        "定义级：上游只给「对象名 + 码」，没有行号（本模块按纪律写 line=0）。"
        "能证明：这个文件里声明了该对象上的该码。"
        "不能证明：任意行级命中/漏报——定义级期望不是行级期望，两者测的不是同一件事。"
    ),
    "file": (
        "文件级：上游只说「这一段用例违反某码」，没有位置（本模块按纪律写 line=0）。"
        "能证明：这个文件里存在该码的期望。"
        "不能证明：任意行级命中/漏报。"
    ),
    "snippet": (
        "片段级：上游的期望挂在内联代码片段上，片段行号是片段内相对行号。"
        "能证明：上游对**这一段代码**的判定口径。"
        "不能证明：这条语料文件的任何检出——片段物化之前，它不产出 Annotation，"
        "也不得进入 GV-01 / GV-02 的分母。"
    ),
}

# 每条「平台已声明的码」的粒度与出处。这里**只有码，没有 rule_id**：
# 码 → rule_id 由 policies/** 推出（方案 §5 W1），不在这份数据里再写第二份映射。
CODE_COVERAGE: tuple[dict[str, str], ...] = (
    {"code": "D200", "dataset": "pydocstyle-testcases", "granularity": "definition"},
    {"code": "D205", "dataset": "pydocstyle-testcases", "granularity": "definition"},
    {"code": "D401", "dataset": "pydocstyle-testcases", "granularity": "definition"},
    {"code": "F401", "dataset": "pyflakes-messages", "granularity": "snippet"},
    {"code": "F403", "dataset": "pyflakes-messages", "granularity": "snippet"},
    {"code": "F405", "dataset": "pyflakes-messages", "granularity": "snippet"},
    {"code": "N801", "dataset": "pep8-naming-testsuite", "granularity": "line"},
    {"code": "N802", "dataset": "pep8-naming-testsuite", "granularity": "line"},
    {"code": "N803", "dataset": "pep8-naming-testsuite", "granularity": "line"},
    {"code": "N806", "dataset": "pep8-naming-testsuite", "granularity": "line"},
    {"code": "N815", "dataset": "pep8-naming-testsuite", "granularity": "line"},
    {"code": "N816", "dataset": "pep8-naming-testsuite", "granularity": "line"},
    {"code": "I001", "dataset": "isort-tests", "granularity": "snippet"},
    {"code": "LOG015", "dataset": "flake8-logging-tests", "granularity": "snippet"},
    {"code": "TRY400", "dataset": "tryceratops-samples", "granularity": "line"},
)

EXPECTATION_FORMATS: dict[str, str] = {
    "pydocstyle-testcases": (
        "src/tests/test_cases/*.py 里的 @expect(\"D200: One-line docstring ...\") 装饰器与 "
        "expectation.expected.add((name, code)) 调用；上游比对 {(definition.name, message)}（无行号）"
    ),
    "pyflakes-messages": (
        "pyflakes/test/test_*.py 里的 self.flakes('import fu, bar', m.UnusedImport, ...)："
        "期望是 pyflakes.messages 的**消息类**（类名 → 码由本模块的转录表给出），片段内相对行号只在"
        "上游报错信息里出现，不进标签"
    ),
    "pep8-naming-testsuite": (
        "testsuite/N8*.py 里的 '#: <CODE>[:<相对行>[:<列>]][(<配置>)]' 与 '#: Okay[...]' 注释行，"
        "作用于紧随其后的第一条代码语句"
    ),
    "flake8-logging-tests": (
        "tests/test_flake8_logging.py 里的 run(\"\"\"...\"\"\") + assert results == [(行, 列, \"LOG0xx ...\")]："
        "行号是**片段内**相对行号；另有 TestIntegration 用临时文件断言 './example.py:2:1: LOG001 ...'"
    ),
    "tryceratops-samples": (
        "src/tests/*_test.py 里 read_sample(\"NAME\") → src/tests/samples/violations/NAME.py，"
        "再用 assert_violation(code, msg, 行, 列, ...) 断言该样例文件内的行号（行级）"
    ),
    "isort-tests": (
        "tests/unit|integration 里的 assert isort.code(<输入>) == <期望输出> 与 assert not isort.check_code(<输入>)："
        "期望是**整段输出**，没有码串、没有该文件内的行号；I001 只能从「输入 ≠ 期望输出 / check_code 为假」推出"
    ),
}

NO_LINE_ANCHOR_REASONS: dict[str, str] = {
    "pyflakes-messages": (
        "期望挂在 self.flakes() 的内联片段上，锚点是片段不是语料文件；"
        "语料文件（pyflakes/test/*.py）自己的 F401 与片段期望无关，按文件级采信会污染分母"
    ),
    "flake8-logging-tests": (
        "期望的行号是片段内相对行号（(2, 0, \"LOG015 ...\") 指片段第 2 行）；"
        "语料文件内无法定位，写进 line 就是编造行号"
    ),
    "isort-tests": (
        "断言比对的是 isort.code() 的整段输出，没有码串也没有位置；"
        "「输入 ≠ 期望输出」只说明这段片段未排序，不指向任何语料文件内位置"
    ),
}

# --------------------------------------------------------------------------------------
# 3. 转录表（上游数据在语料里，转录处写明出处，便于离线复核）
# --------------------------------------------------------------------------------------

TRANSCRIBED_TABLES: dict[str, str] = {
    "PYFLAKES_MESSAGE_CODES": (
        "pyflakes/messages.py@%s 的类名 → Ruff 同义码；只保留平台已声明的 3 个。"
        "pyflakes 的其余消息类（UndefinedName / RedefinedWhileUnused 等）不由本模块采信为标签" % PYFLAKES_REV
    ),
    "TRYCERATOPS_CODE_CONSTANTS": (
        "src/tryceratops/violations/codes.py@%s 的常量名 → 码串（该文件已随语料取到，可离线复核）；"
        "测试里出现的常量名不在表内时，本模块记诊断而不是静默丢弃" % TRYCERATOPS_REV
    ),
}

PYFLAKES_MESSAGE_CODES: dict[str, str] = {
    "UnusedImport": "F401",
    "ImportStarUsed": "F403",
    "ImportStarUsage": "F405",
}

TRYCERATOPS_CODE_CONSTANTS: dict[str, str] = {
    "RAISE_VANILLA_CLASS": "TRY002",
    "RAISE_VANILLA_ARGS": "TRY003",
    "PREFER_TYPE_ERROR": "TRY004",
    "NON_PICKABLE_CLASS": "TRY005",
    "ALLOWED_BASE_EXCEPTION": "TRY006",
    "CHECK_TO_CONTINUE": "TRY100",
    "TOO_MANY_TRY": "TRY101",
    "RERAISE_NO_CAUSE": "TRY200",
    "VERBOSE_RERAISE": "TRY201",
    "IGNORING_EXCEPTION": "TRY202",
    "USELESS_TRY_EXCEPT": "TRY203",
    "CONSIDER_ELSE": "TRY300",
    "RAISE_WITHIN_TRY": "TRY301",
    "USE_LOGGING_EXCEPTION": "TRY400",
    "VERBOSE_LOG_MESSAGE": "TRY401",
}

PYDOCSTYLE_EXPECT_RE = re.compile(r"^\s*([A-Z]{1,4}\d{3})\b")
PEP8_NAMING_MARKER_RE = re.compile(
    r"^#:\s*(?P<code>[A-Za-z][A-Za-z0-9]*)"
    r"(?::(?P<line>\d+)(?::(?P<col>\d+))?)?"
    r"\s*(?P<config>\(.*\))?\s*$"
)
FLAKE8_LOGGING_TUPLE_RE = re.compile(r"^(LOG\d{3})\b")
FLAKE8_LOGGING_INTEGRATION_RE = re.compile(r"\.py:(\d+):(\d+):\s*(LOG\d{3})\b")


# --------------------------------------------------------------------------------------
# 4. 解析器
# --------------------------------------------------------------------------------------


@dataclass
class _FileScan:
    """一个文件解析出来的三件事：注解、上游期望条数、诊断（+ 片段级原始材料）。"""

    annotations: list[tuple[str, int, str, str]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    snippets: list[dict[str, Any]] = field(default_factory=list)


def _dedupe_file_level(rows: list[tuple[str, int, str, str]]) -> list[tuple[str, int, str, str]]:
    """line=0 的期望只保留一条 (文件, 码)：位置没被承载时，重复条目不携带信息。"""

    seen: set[tuple[str, int, str]] = set()
    kept: list[tuple[str, int, str, str]] = []
    for row in rows:
        key = (row[0], row[1], row[2])
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept


def _walk_codes(value: ast.AST, out: list[str]) -> None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        match = PYDOCSTYLE_EXPECT_RE.match(value.value)
        if match:
            out.append(match.group(1))
    elif isinstance(value, (ast.Tuple, ast.List)):
        for element in value.elts:
            _walk_codes(element, out)
    elif isinstance(value, ast.Call):
        for arg in value.args:
            _walk_codes(arg, out)


def _is_expect_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "expect"
    return isinstance(func, ast.Attribute) and func.attr == "expect"


def _is_expectation_add(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "add":
        return False
    owner = func.value
    return isinstance(owner, ast.Attribute) and owner.attr == "expected"


def _scan_pydocstyle(text: str, rel_path: str) -> _FileScan:
    """pydocstyle：@expect("D200: ...") / expectation.expected.add((name, code))。对象级，无行号。"""

    if not rel_path.endswith(".py"):
        return _FileScan()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return _FileScan(diagnostics=["%s: 上游用例不是可解析的 Python（%s）" % (rel_path, exc.msg)])
    codes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                if _is_expect_call(decorator):
                    for arg in decorator.args:
                        _walk_codes(arg, codes)
        elif isinstance(node, ast.Call):
            target = node if _is_expect_call(node) else (node if _is_expectation_add(node) else None)
            if target is not None:
                for arg in target.args:
                    _walk_codes(arg, codes)
    if not codes:
        return _FileScan()
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    rows = [(rel_path, 0, code, rel_path) for code in sorted(counts)]
    return _FileScan(annotations=_dedupe_file_level(rows), counts=counts)


def _scan_pep8_naming(text: str, rel_path: str) -> _FileScan:
    """pep8-naming：'#: N801[:相对行[:列]][(配置)]' 与 '#: Okay[...]'，作用于紧随其后的语句。"""

    if not rel_path.endswith(".py"):
        return _FileScan()
    lines = text.splitlines()
    rows: list[tuple[str, int, str, str]] = []
    counts: dict[str, int] = {}
    diagnostics: list[str] = []
    negatives = 0
    for index, raw in enumerate(lines):
        match = PEP8_NAMING_MARKER_RE.match(raw.strip())
        if not match:
            continue
        code = match.group("code")
        if code == "Okay":
            negatives += 1
            continue
        config = match.group("config")
        if config:
            diagnostics.append(
                "%s:%d: %s 的期望带配置 %s；Annotation 没有配置字段，没有配置地采信它就是改变语义，已跳过"
                % (rel_path, index + 1, code, config)
            )
            continue
        anchor: int | None = None
        for follow in range(index + 1, len(lines)):
            stripped = lines[follow].strip()
            if not stripped or stripped.startswith("#"):
                continue
            anchor = follow + 1
            break
        if anchor is None:
            diagnostics.append("%s:%d: %s 标记后面没有代码语句，未产出期望" % (rel_path, index + 1, code))
            continue
        relative = match.group("line")
        line = anchor + int(relative) - 1 if relative else 0
        if line and (line < 1 or line > len(lines)):
            diagnostics.append(
                "%s:%d: %s 的相对位置 %s 换算后越界（锚点 %d），未产出期望"
                % (rel_path, index + 1, code, relative, anchor)
            )
            continue
        counts[code] = counts.get(code, 0) + 1
        rows.append((rel_path, line, code, rel_path))
    if negatives:
        diagnostics.append("%s: %d 条 '#: Okay' 是负例（期望不报），Annotation 没有负例位，已跳过" % (rel_path, negatives))
    return _FileScan(annotations=_dedupe_file_level(rows), counts=counts, diagnostics=diagnostics)


def _scan_tryceratops(text: str, rel_path: str) -> _FileScan:
    """tryceratops：read_sample("NAME") + assert_violation(code, msg, 行, 列, ...)（样例文件内行号）。"""

    if not rel_path.endswith(".py"):
        return _FileScan()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return _FileScan(diagnostics=["%s: 上游用例不是可解析的 Python（%s）" % (rel_path, exc.msg)])
    rows: list[tuple[str, int, str, str]] = []
    counts: dict[str, int] = {}
    diagnostics: list[str] = []
    parent_dir = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    for func in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        nodes = list(ast.walk(func))
        sample: str | None = None
        subdir = "violations"
        codes_seen: list[str] = []
        partials: set[str] = set()
        for node in nodes:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value
                func_name = call.func
                if isinstance(func_name, ast.Name) and func_name.id == "partial" and call.args:
                    inner = call.args[0]
                    if isinstance(inner, ast.Name) and inner.id == "assert_violation":
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                partials.add(target.id)
            if isinstance(node, ast.Call):
                callee = node.func
                if isinstance(callee, ast.Name) and callee.id in ("read_sample", "read_sample_lines"):
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        sample = node.args[0].value
                        for keyword in node.keywords:
                            if (
                                keyword.arg == "dir"
                                and isinstance(keyword.value, ast.Constant)
                                and isinstance(keyword.value.value, str)
                            ):
                                subdir = keyword.value.value
                        if (
                            callee.id == "read_sample_lines"
                            and len(node.args) > 1
                            and isinstance(node.args[1], ast.Constant)
                            and isinstance(node.args[1].value, str)
                        ):
                            subdir = node.args[1].value
            if isinstance(node, ast.Attribute) and node.attr in TRYCERATOPS_CODE_CONSTANTS:
                found_code = TRYCERATOPS_CODE_CONSTANTS[node.attr]
                if found_code not in codes_seen:
                    codes_seen.append(found_code)
        assertion_names = partials | {"assert_violation"}
        asserted: list[tuple[int, int]] = []
        for node in nodes:
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in assertion_names or len(node.args) < 2:
                continue
            first, second = node.args[0], node.args[1]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, int)
                and isinstance(second, ast.Constant)
                and isinstance(second.value, int)
            ):
                asserted.append((first.value, second.value))
        if not asserted:
            continue
        if len(codes_seen) > 1:
            diagnostics.append(
                "%s: 测试函数 %s 里出现 %d 个不同的码常量（%s），无法归属，未产出期望"
                % (rel_path, func.name, len(codes_seen), ", ".join(sorted(codes_seen)))
            )
            continue
        code = codes_seen[0] if codes_seen else None
        if sample is None or code is None:
            diagnostics.append(
                "%s: 测试函数 %s 断言了 %d 条违规，但解析不出样例名或码常量，未产出期望"
                % (rel_path, func.name, len(asserted))
            )
            continue
        sample_path = "%s/samples/%s/%s.py" % (parent_dir, subdir, sample) if parent_dir else "samples/%s/%s.py" % (subdir, sample)
        for line, _col in asserted:
            rows.append((sample_path, line, code, rel_path))
            counts[code] = counts.get(code, 0) + 1
    return _FileScan(annotations=rows, counts=counts, diagnostics=diagnostics)


def _scan_pyflakes(text: str, rel_path: str) -> _FileScan:
    """pyflakes：self.flakes(片段, m.X, ...)。只登记期望条数与片段，不产出 Annotation（片段级）。"""

    if not rel_path.endswith(".py"):
        return _FileScan()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return _FileScan(diagnostics=["%s: 上游用例不是可解析的 Python（%s）" % (rel_path, exc.msg)])
    counts: dict[str, int] = {}
    snippets: list[dict[str, Any]] = []
    unknown: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if not (isinstance(callee, ast.Attribute) and callee.attr == "flakes"):
            continue
        expected: list[str] = []
        for arg in node.args[1:]:
            name = None
            if isinstance(arg, ast.Attribute):
                name = arg.attr
            elif isinstance(arg, ast.Name):
                name = arg.id
            if name is None:
                continue
            expected.append(name)
            code = PYFLAKES_MESSAGE_CODES.get(name)
            if code:
                counts[code] = counts.get(code, 0) + 1
            else:
                unknown[name] = unknown.get(name, 0) + 1
        snippet = None
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            snippet = textwrap.dedent(node.args[0].value)
        snippets.append(
            {
                "file": rel_path,
                "line": node.lineno,
                "snippet": snippet,
                "expected_messages": expected,
            }
        )
    if not snippets:
        return _FileScan()
    diagnostics = [
        "%s: %d 条 self.flakes() 期望是**片段级**（pyflakes.messages 的类名），未产出 Annotation（见 NO_LINE_ANCHOR_REASONS）"
        % (rel_path, len(snippets))
    ]
    if unknown:
        diagnostics.append(
            "%s: 平台未声明的消息类 %s（只计数，不判定）"
            % (rel_path, ", ".join("%s×%d" % (k, v) for k, v in sorted(unknown.items())))
        )
    return _FileScan(counts=counts, diagnostics=diagnostics, snippets=snippets)


def _enclosing_runs(tree: ast.AST) -> list[tuple[ast.AST, list[ast.Call]]]:
    """把 run(...) / run_ignore_log015(...) 调用按所属测试函数分组。"""

    grouped: list[tuple[ast.AST, list[ast.Call]]] = []
    for func in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        calls: list[ast.Call] = []
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.startswith("run"):
                calls.append(node)
        if calls:
            grouped.append((func, calls))
    return grouped


def _scan_flake8_logging(text: str, rel_path: str) -> _FileScan:
    """flake8-logging：run(片段) + assert results == [(片段行, 列, "LOG0xx ...")]。片段级，不产出 Annotation。"""

    if not rel_path.endswith(".py"):
        return _FileScan()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return _FileScan(diagnostics=["%s: 上游用例不是可解析的 Python（%s）" % (rel_path, exc.msg)])
    counts: dict[str, int] = {}
    diagnostics: list[str] = []
    snippets: list[dict[str, Any]] = []
    integration = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) >= 3:
            third = node.elts[2]
            first = node.elts[0]
            if (
                isinstance(third, ast.Constant)
                and isinstance(third.value, str)
                and isinstance(first, ast.Constant)
                and isinstance(first.value, int)
            ):
                match = FLAKE8_LOGGING_TUPLE_RE.match(third.value)
                if match:
                    counts[match.group(1)] = counts.get(match.group(1), 0) + 1
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if FLAKE8_LOGGING_INTEGRATION_RE.search(node.value):
                integration += 1
    for func, calls in _enclosing_runs(tree):
        for call in calls:
            if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                snippets.append(
                    {
                        "file": rel_path,
                        "line": call.lineno,
                        "function": getattr(func, "name", "?"),
                        "snippet": textwrap.dedent(call.args[0].value),
                    }
                )
    if not counts and not snippets and not integration:
        return _FileScan()
    if counts:
        diagnostics.append(
            "%s: %d 条期望的行号是**片段内**相对行号，未产出 Annotation（见 NO_LINE_ANCHOR_REASONS）"
            % (rel_path, sum(counts.values()))
        )
    if integration:
        diagnostics.append(
            "%s: %d 条 TestIntegration 断言走临时文件（'./example.py:2:1: LOG001 ...'），不是语料文件位置"
            % (rel_path, integration)
        )
    return _FileScan(counts=counts, diagnostics=diagnostics, snippets=snippets)


def _const_str(node: ast.AST) -> str | None:
    """把字符串字面量 / 隐式拼接折叠成常量；折不动就返回 None（不猜）。"""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _const_str(node.left)
        right = _const_str(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                return None
        return "".join(parts)
    return None


def _scan_isort(text: str, rel_path: str) -> _FileScan:
    """isort：assert isort.code(输入) == 期望 / assert not isort.check_code(输入)。片段级，不产出 Annotation。"""

    if not rel_path.endswith(".py"):
        return _FileScan()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return _FileScan(diagnostics=["%s: 上游用例不是可解析的 Python（%s）" % (rel_path, exc.msg)])
    counts: dict[str, int] = {}
    diagnostics: list[str] = []
    snippets: list[dict[str, Any]] = []
    unevaluated = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        source: str | None = None
        expected: str | None = None
        unsorted: bool | None = None
        if isinstance(test, ast.Compare) and len(test.comparators) == 1:
            left = test.left
            if isinstance(left, ast.Call) and isinstance(left.func, ast.Attribute) and left.func.attr == "code":
                if left.args:
                    source = _const_str(left.args[0])
                expected = _const_str(test.comparators[0])
                if source is not None and expected is not None:
                    unsorted = source != expected
        elif isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            operand = test.operand
            if isinstance(operand, ast.Call) and isinstance(operand.func, ast.Attribute) and operand.func.attr == "check_code":
                source = _const_str(operand.args[0]) if operand.args else None
                unsorted = source is not None
        elif isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute) and test.func.attr == "check_code":
            source = _const_str(test.args[0]) if test.args else None
            unsorted = False if source is not None else None
        if unsorted is None:
            continue
        if source is None:
            unevaluated += 1
            continue
        snippets.append(
            {
                "file": rel_path,
                "line": node.lineno,
                "unsorted": unsorted,
                "input": source,
                "expected": expected,
            }
        )
        if unsorted:
            counts["I001"] = counts.get("I001", 0) + 1
    if not snippets and not unevaluated:
        return _FileScan()
    if counts:
        diagnostics.append(
            "%s: %d 条「输入与期望输出不同 / check_code 为假」只说明该**片段**未排序，未产出 Annotation"
            "（见 NO_LINE_ANCHOR_REASONS）" % (rel_path, counts.get("I001", 0))
        )
    if unevaluated:
        diagnostics.append("%s: %d 条断言的两侧折不成字符串常量，未计入" % (rel_path, unevaluated))
    return _FileScan(counts=counts, diagnostics=diagnostics, snippets=snippets)


_SCANNERS: dict[str, Callable[[str, str], _FileScan]] = {
    "pydocstyle-object-expectation": _scan_pydocstyle,
    "pyflakes-message-expectation": _scan_pyflakes,
    "pep8-naming-testsuite-marker": _scan_pep8_naming,
    "flake8-logging-snippet-expectation": _scan_flake8_logging,
    "tryceratops-sample-violation": _scan_tryceratops,
    "isort-code-compare": _scan_isort,
}


def _make_parser(kind: str) -> Callable[[str, SourceSpec, str], list[Annotation]]:
    scanner = _SCANNERS[kind]

    def parse(text: str, spec: SourceSpec, rel_path: str) -> list[Annotation]:
        found = scanner(text, rel_path)
        return [
            Annotation(
                dataset=spec.id,
                revision=spec.revision,
                file=file,
                line=line,
                code=code,
                kind=spec.expectation_kind,
                source=source,
            )
            for (file, line, code, source) in found.annotations
        ]

    parse.__name__ = "parse_%s" % kind.replace("-", "_")
    parse.__doc__ = "解析 %s：签名 parse(text, spec, rel_path) -> list[Annotation]" % kind
    return parse


PARSERS: dict[str, Callable[[str, SourceSpec, str], list[Annotation]]] = {
    kind: _make_parser(kind) for kind in _SCANNERS
}

# --------------------------------------------------------------------------------------
# 5. 片段物化（加性导出；task-6）
#
# 为什么需要：pyflakes / flake8-logging / isort 把期望写在**测试代码里的内联片段**上，
# 语料文件本身没有 ground truth（load_annotations() 返回空）。这一步把片段**物化**成
# 可独立 ast.parse 的 .py 文件 + 该文件的上游期望码集合，于是 F/I/LOG 第一次有了分母。
#
# 三条纪律：
#   1. 物化产物**只写 out_root**（默认 .tmp/eval-corpora-materialized/），绝不写进锁定的语料目录
#      —— 往 <corpus_root>/<id>@<rev>/ 里加文件会让 eval_corpus.py --verify 变红；
#   2. **只做文件级，line 一律 0**：片段内的相对行号不进 Annotation（写进去就是编造行号）；
#   3. 准入不许放宽：语法错 / 期望映射不出来 / 需要补上下文（缺 import、依赖工具运行模式）一律 rejected，
#      **不许 patching**（不替上游补 import、不修语法、不补上下文）。
# --------------------------------------------------------------------------------------

MATERIALIZATION_ORACLE = "file_level_code_set"

MATERIALIZATION_ORACLE_POLICY = (
    "文件级**码集合**比对，不是行级：每个物化文件带一份「上游声明的码集合」；"
    "集合里的码报出来了 = 命中，没报 = 未命中；文件上出现的**其它**诊断（别的规则、行宽、风格等）"
    "只进 noise 桶、绝不算 FP；只有对**受测码**的期望集合为空（含显式空期望，例如 assert results == []）"
    "的文件上报出受测码，才算 FP。受测码 = 该语料物化文件的期望码集合 ∩ policies/** 声明的码（由调用方推出）"
    "——本模块不写第二份 rule_id 映射，也不写死受测码清单。"
)

# 拒绝原因必须可分类（task-6 规定），细节写在 detail 里。
MATERIALIZE_REJECT_REASONS = ("syntax_error", "no_expectation", "unmapped_message", "needs_context", "other")

DEFAULT_MATERIALIZED_ROOT = Path(".tmp/eval-corpora-materialized")


@dataclass
class _Snippet:
    """一个候选项：要么可物化（reject is None），要么带原因拒绝。"""

    source_ref: str
    slug: str
    text: str = ""
    codes: tuple[str, ...] = ()
    declared_empty: bool = False
    note: str = ""
    reject: str | None = None
    detail: str = ""


@dataclass
class MaterializationResult:
    """一次物化的完整读数（**不是文件载荷**：要落盘请由消费方按自己的版本轴处理）。"""

    dataset: str
    revision: str
    out_root: Path
    files: tuple[str, ...]
    annotations: tuple[Annotation, ...]
    file_expectations: dict[str, tuple[str, ...]]
    file_sources: dict[str, str]
    candidates: int
    accepted: int
    rejected: tuple[dict[str, str], ...]
    reject_reasons: dict[str, int]
    acceptance_rate: float
    oracle: str
    oracle_policy: str

    def to_json(self) -> dict[str, Any]:
        return {
            "annotation_schema_version": _annotation_schema_version(),
            "dataset": self.dataset,
            "revision": self.revision,
            "out_root": str(self.out_root),
            "oracle": self.oracle,
            "oracle_policy": self.oracle_policy,
            "candidates": self.candidates,
            "accepted": self.accepted,
            "acceptance_rate": self.acceptance_rate,
            "reject_reasons": dict(sorted(self.reject_reasons.items())),
            "rejected": [dict(item) for item in self.rejected],
            "files": list(self.files),
            "file_expectations": {key: list(value) for key, value in sorted(self.file_expectations.items())},
            "file_sources": dict(sorted(self.file_sources.items())),
            "annotations": [annotation.__dict__ for annotation in self.annotations],
        }


def _annotation_schema_version() -> str:
    """注解记录的形状轴取自宿主（本会话首次建立、从未发布；形状修正不升版）。"""

    host = sys.modules.get("eval_corpus")
    version = getattr(host, "ANNOTATION_SCHEMA_VERSION", None)
    return version if isinstance(version, str) and version else "1"


def _slug(rel_path: str, line: int) -> str:
    stem = Path(rel_path).stem
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", stem).strip("_") or "snippet"
    return "%s_L%d" % (cleaned, line)


def _normalize_snippet_text(text: str) -> str:
    """只规范化换行与结尾：不改任何非空白字符（片段原文照抄）。"""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized if normalized.endswith("\n") else normalized + "\n"


def _import_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith(("import ", "from "))]


def _import_tokens(text: str) -> list[str]:
    """把导入行归一成「导入了什么」的记号（\`import a.b as c\` → \`import a.b\`；\`from x import y\` → \`from x\`）。

    用来把「顺序不同」与「内容不同（合并/去重/增删）」分开：前者是 I001 的正例，
    后者是 isort 的改写面比 ruff 的 I001 宽，不采信。
    """

    tokens: list[str] = []
    for line in _import_lines(text):
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("import", "from"):
            tokens.append("%s %s" % (parts[0], parts[1]))
    return tokens


def _collect_pyflakes(base: Path) -> list[_Snippet]:
    """self.flakes(片段, m.X, ...)：上游断言的是**消息类**的精确列表。"""

    found: list[_Snippet] = []
    for path in sorted(base.rglob("*.py")):
        rel = path.relative_to(base).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "flakes":
                continue
            ref = "%s:%d" % (rel, node.lineno)
            slug = _slug(rel, node.lineno)
            if not node.args or not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.append(_Snippet(ref, slug, reject="other", detail="第一个参数不是字符串字面量，取不到片段原文"))
                continue
            keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
            mode = sorted(keywords & {"is_segment", "withDoctest"})
            if mode:
                found.append(
                    _Snippet(
                        ref,
                        slug,
                        reject="needs_context",
                        detail="依赖 pyflakes 运行模式 %s，当独立文件跑语义不同" % mode,
                    )
                )
                continue
            snippet = textwrap.dedent(node.args[0].value)
            if not snippet.strip():
                found.append(_Snippet(ref, slug, reject="other", detail="片段为空"))
                continue
            try:
                ast.parse(snippet)
            except SyntaxError as exc:
                found.append(_Snippet(ref, slug, reject="syntax_error", detail="片段不是合法 Python（%s）" % exc.msg))
                continue
            classes = [arg.attr for arg in node.args[1:] if isinstance(arg, ast.Attribute)]
            codes = tuple(sorted({PYFLAKES_MESSAGE_CODES[name] for name in classes if name in PYFLAKES_MESSAGE_CODES}))
            if classes and not codes:
                found.append(
                    _Snippet(
                        ref,
                        slug,
                        reject="unmapped_message",
                        detail="期望消息类 %s 不在转录表里" % sorted(set(classes)),
                    )
                )
                continue
            found.append(
                _Snippet(
                    ref,
                    slug,
                    text=snippet,
                    codes=codes,
                    declared_empty=not classes,
                    note="上游断言 pyflakes 恰好报出这些消息类（精确断言）",
                )
            )
    return found


def _collect_flake8_logging(base: Path) -> list[_Snippet]:
    """run(片段) + assert results == [...]：只取同一测试函数里的断言列表。"""

    found: list[_Snippet] = []
    for path in sorted(base.rglob("*.py")):
        rel = path.relative_to(base).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for func in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            calls = [
                node
                for node in ast.walk(func)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.startswith("run")
            ]
            if not calls:
                continue
            codes: set[str] = set()
            declared_empty = False
            for node in ast.walk(func):
                if not (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)):
                    continue
                for side in [node.test.left, *node.test.comparators]:
                    if not isinstance(side, (ast.List, ast.Tuple)):
                        continue
                    if not side.elts:
                        declared_empty = True
                    for element in side.elts:
                        if (
                            isinstance(element, ast.Tuple)
                            and len(element.elts) >= 3
                            and isinstance(element.elts[2], ast.Constant)
                            and isinstance(element.elts[2].value, str)
                        ):
                            match = FLAKE8_LOGGING_TUPLE_RE.match(element.elts[2].value)
                            if match:
                                codes.add(match.group(1))
            for call in calls:
                ref = "%s:%d" % (rel, call.lineno)
                slug = _slug(rel, call.lineno)
                callee = call.func.id if isinstance(call.func, ast.Name) else "?"
                if callee != "run":
                    found.append(
                        _Snippet(
                            ref,
                            slug,
                            reject="needs_context",
                            detail="调用的是 %s（带 ignore/filter 的变体），期望列表是被过滤后的结果，"
                            "把被过滤的码当「没报」就会造出假 FP" % callee,
                        )
                    )
                    continue
                if not (call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)):
                    found.append(_Snippet(ref, slug, reject="other", detail="run() 的第一个参数不是字符串字面量"))
                    continue
                snippet = textwrap.dedent(call.args[0].value)
                if not snippet.strip():
                    found.append(_Snippet(ref, slug, reject="other", detail="片段为空"))
                    continue
                try:
                    ast.parse(snippet)
                except SyntaxError as exc:
                    found.append(_Snippet(ref, slug, reject="syntax_error", detail="片段不是合法 Python（%s）" % exc.msg))
                    continue
                if not codes and not declared_empty:
                    found.append(
                        _Snippet(
                            ref,
                            slug,
                            reject="no_expectation",
                            detail="同一测试函数里没有可读的期望断言（既非码列表也非空列表）",
                        )
                    )
                    continue
                found.append(
                    _Snippet(
                        ref,
                        slug,
                        text=snippet,
                        codes=tuple(sorted(codes)),
                        declared_empty=declared_empty and not codes,
                        note="上游断言插件输出恰好等于该列表" if codes else "上游显式断言插件零输出",
                    )
                )
    return found


def _collect_isort(base: Path) -> list[_Snippet]:
    """assert isort.code(输入) == 期望输出 / assert not isort.check_code(输入)。"""

    found: list[_Snippet] = []
    for path in sorted(base.rglob("*.py")):
        rel = path.relative_to(base).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            test = node.test
            ref = "%s:%d" % (rel, node.lineno)
            slug = _slug(rel, node.lineno)
            source: str | None = None
            expected: str | None = None
            unsorted: bool | None = None
            if isinstance(test, ast.Compare) and len(test.comparators) == 1:
                left = test.left
                if isinstance(left, ast.Call) and isinstance(left.func, ast.Attribute) and left.func.attr == "code":
                    source = _const_str(left.args[0]) if left.args else None
                    expected = _const_str(test.comparators[0])
                    if source is not None and expected is not None:
                        unsorted = source != expected
            elif isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
                operand = test.operand
                if (
                    isinstance(operand, ast.Call)
                    and isinstance(operand.func, ast.Attribute)
                    and operand.func.attr == "check_code"
                ):
                    source = _const_str(operand.args[0]) if operand.args else None
                    unsorted = source is not None
            elif isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute) and test.func.attr == "check_code":
                source = _const_str(test.args[0]) if test.args else None
                unsorted = False if source is not None else None
            if unsorted is None:
                continue
            if source is None:
                found.append(_Snippet(ref, slug, reject="other", detail="断言的一侧折不成字符串常量，取不到片段原文"))
                continue
            if not source.strip():
                found.append(_Snippet(ref, slug, reject="other", detail="片段为空"))
                continue
            try:
                ast.parse(source)
            except SyntaxError as exc:
                found.append(_Snippet(ref, slug, reject="syntax_error", detail="片段不是合法 Python（%s）" % exc.msg))
                continue
            if not unsorted:
                found.append(
                    _Snippet(ref, slug, text=source, codes=(), declared_empty=True, note="上游断言该片段已经排好序（负例）")
                )
                continue
            if expected is not None:
                source_tokens = _import_tokens(source)
                expected_tokens = _import_tokens(expected)
                if sorted(source_tokens) != sorted(expected_tokens):
                    found.append(
                        _Snippet(
                            ref,
                            slug,
                            reject="needs_context",
                            detail="输入与期望输出导入了不同的东西（合并/去重/增删/指令注释），"
                            "isort 的改写面比 ruff 的 I001 宽，不采信",
                        )
                    )
                    continue
                if source_tokens == expected_tokens:
                    found.append(
                        _Snippet(
                            ref,
                            slug,
                            reject="needs_context",
                            detail="输入与期望输出的导入顺序相同、只差空白/换行/注释；该不该报 I001 依赖 isort 配置，不采信",
                        )
                    )
                    continue
            found.append(
                _Snippet(
                    ref,
                    slug,
                    text=source,
                    codes=("I001",),
                    declared_empty=False,
                    note="上游断言 isort 会改写这段片段（导入顺序不同）",
                )
            )
    return found


_SNIPPET_COLLECTORS: dict[str, Callable[[Path], list[_Snippet]]] = {
    "pyflakes-message-expectation": _collect_pyflakes,
    "flake8-logging-snippet-expectation": _collect_flake8_logging,
    "isort-code-compare": _collect_isort,
}


def materialize_snippets(
    dataset_id: str,
    *,
    corpus_root: Path | str,
    out_root: Path | str | None = None,
) -> MaterializationResult:
    """把片段级语料物化成可测的文件级分母。**只写 out_root**，不动锁定语料目录。"""

    if dataset_id not in SOURCES:
        raise KeyError("未登记的数据集 %r；已知：%s" % (dataset_id, ", ".join(sorted(SOURCES))))
    spec = SOURCES[dataset_id]
    collector = _SNIPPET_COLLECTORS.get(spec.expectation_kind)
    if collector is None:
        raise ValueError(
            "%s 的 expectation_kind=%s 不是片段级语料，没有可物化的片段（只有 pyflakes / flake8-logging / isort 三个）"
            % (dataset_id, spec.expectation_kind)
        )
    base = Path(corpus_root) / ("%s@%s" % (spec.id, spec.revision))
    if not base.is_dir():
        raise FileNotFoundError("语料不在本地：%s（先跑 python tools/eval_corpus.py --fetch %s）" % (base, dataset_id))
    out = Path(out_root) if out_root is not None else DEFAULT_MATERIALIZED_ROOT
    target = out / ("%s@%s" % (spec.id, spec.revision))
    snippets = sorted(collector(base), key=lambda item: (item.source_ref, item.slug))
    rejected: list[dict[str, str]] = []
    files: list[str] = []
    annotations: list[Annotation] = []
    file_expectations: dict[str, tuple[str, ...]] = {}
    file_sources: dict[str, str] = {}
    for index, snippet in enumerate(snippets, start=1):
        if snippet.reject is not None:
            rejected.append({"snippet_ref": snippet.source_ref, "reason": snippet.reject, "detail": snippet.detail})
            continue
        name = "%04d_%s.py" % (index, snippet.slug)
        relative = "%s@%s/%s" % (spec.id, spec.revision, name)
        target.mkdir(parents=True, exist_ok=True)
        (target / name).write_text(_normalize_snippet_text(snippet.text), encoding="utf-8", newline="\n")
        files.append(relative)
        file_expectations[relative] = tuple(snippet.codes)
        file_sources[relative] = snippet.source_ref
        for code in snippet.codes:
            annotations.append(
                Annotation(
                    dataset=spec.id,
                    revision=spec.revision,
                    file=relative,
                    line=0,
                    code=code,
                    kind=spec.expectation_kind,
                    source=snippet.source_ref,
                )
            )
    reject_reasons: dict[str, int] = {}
    for item in rejected:
        reject_reasons[item["reason"]] = reject_reasons.get(item["reason"], 0) + 1
    candidates = len(snippets)
    accepted = len(files)
    return MaterializationResult(
        dataset=dataset_id,
        revision=spec.revision,
        out_root=out,
        files=tuple(files),
        annotations=tuple(annotations),
        file_expectations=file_expectations,
        file_sources=file_sources,
        candidates=candidates,
        accepted=accepted,
        rejected=tuple(rejected),
        reject_reasons=reject_reasons,
        acceptance_rate=(accepted / candidates) if candidates else 0.0,
        oracle=MATERIALIZATION_ORACLE,
        oracle_policy=MATERIALIZATION_ORACLE_POLICY,
    )


# --------------------------------------------------------------------------------------
# 6. 非契约导出：扫描报告（供「这条粒度能证明什么 / 不能证明什么」的取数用）
# --------------------------------------------------------------------------------------


@dataclass
class ScanReport:
    dataset: str
    revision: str
    files: tuple[str, ...]
    annotations: tuple[Annotation, ...]
    expectations_by_code: dict[str, int]
    annotations_by_code: dict[str, int]
    diagnostics: tuple[str, ...]
    snippets: tuple[dict[str, Any], ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "revision": self.revision,
            "files": list(self.files),
            "annotations": [annotation.__dict__ for annotation in self.annotations],
            "expectations_by_code": dict(sorted(self.expectations_by_code.items())),
            "annotations_by_code": dict(sorted(self.annotations_by_code.items())),
            "diagnostics": list(self.diagnostics),
            "snippet_count": len(self.snippets),
        }


def scan(dataset_id: str, *, root: Path | str) -> ScanReport:
    """把一个已经取到本地的数据集解析干净：注解 + 上游期望条数 + 诊断 + 片段材料。"""

    spec = SOURCES[dataset_id]
    base = Path(root) / ("%s@%s" % (dataset_id, spec.revision))
    if not base.is_dir():
        raise FileNotFoundError("语料不在本地：%s（先跑 python tools/eval_corpus.py --fetch %s）" % (base, dataset_id))
    scanner = _SCANNERS[spec.expectation_kind]
    files = tuple(sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()))
    annotations: list[Annotation] = []
    expectations: dict[str, int] = {}
    diagnostics: list[str] = []
    snippets: list[dict[str, Any]] = []
    for rel_path in files:
        text = (base / rel_path).read_text(encoding="utf-8", errors="replace")
        found = scanner(text, rel_path)
        for (file, line, code, source) in found.annotations:
            annotations.append(
                Annotation(
                    dataset=spec.id,
                    revision=spec.revision,
                    file=file,
                    line=line,
                    code=code,
                    kind=spec.expectation_kind,
                    source=source,
                )
            )
        for code, count in found.counts.items():
            expectations[code] = expectations.get(code, 0) + count
        diagnostics.extend(found.diagnostics)
        snippets.extend(found.snippets)
    annotations_by_code: dict[str, int] = {}
    for annotation in annotations:
        annotations_by_code[annotation.code] = annotations_by_code.get(annotation.code, 0) + 1
    return ScanReport(
        dataset=dataset_id,
        revision=spec.revision,
        files=files,
        annotations=tuple(annotations),
        expectations_by_code=expectations,
        annotations_by_code=annotations_by_code,
        diagnostics=tuple(diagnostics),
        snippets=tuple(snippets),
    )


def render_report(*, root: Path | str, as_json: bool = False) -> str:
    """把 6 个数据集扫一遍，输出「粒度 / 期望条数 / 注解条数」的读数（只读，不判分）。"""

    reports: list[ScanReport] = []
    missing: list[str] = []
    for dataset_id in SOURCES:
        try:
            reports.append(scan(dataset_id, root=root))
        except FileNotFoundError as exc:
            missing.append(str(exc))
    if as_json:
        return json.dumps(
            {
                "annotation_type_source": ANNOTATION_TYPE_SOURCE,
                "code_coverage": list(CODE_COVERAGE),
                "no_line_anchor_reasons": dict(NO_LINE_ANCHOR_REASONS),
                "datasets": [report.to_json() for report in reports],
                "missing": missing,
            },
            ensure_ascii=False,
            indent=2,
        )
    lines: list[str] = []
    lines.append("annotation 类型来源: %s" % ANNOTATION_TYPE_SOURCE)
    lines.append("")
    lines.append("%-26s %-8s %-6s %-8s %s" % ("dataset", "files", "exp", "ann", "granularity"))
    lines.append("-" * 78)
    for report in reports:
        granularity = sorted({row["granularity"] for row in CODE_COVERAGE if row["dataset"] == report.dataset})
        lines.append(
            "%-26s %-8d %-6d %-8d %s"
            % (
                report.dataset,
                len(report.files),
                sum(report.expectations_by_code.values()),
                len(report.annotations),
                ",".join(granularity) or "-",
            )
        )
    lines.append("")
    lines.append("per-code（expectations = 上游期望条数；annotations = 产出的 Annotation 条数）")
    for report in reports:
        codes = sorted(set(report.expectations_by_code) | set(report.annotations_by_code))
        if not codes:
            lines.append("  %s: 无期望（原因见下）" % report.dataset)
            continue
        lines.append(
            "  %s: %s"
            % (
                report.dataset,
                ", ".join(
                    "%s=%d/%d" % (code, report.expectations_by_code.get(code, 0), report.annotations_by_code.get(code, 0))
                    for code in codes
                ),
            )
        )
    reason_lines = ["", "未产出 Annotation 的数据集（片段级）："]
    for dataset_id, reason in sorted(NO_LINE_ANCHOR_REASONS.items()):
        reason_lines.append("  %s: %s" % (dataset_id, reason))
    lines.extend(reason_lines)
    if missing:
        lines.append("")
        lines.append("本地缺失（未纳入本次读数）：")
        lines.extend("  %s" % item for item in missing)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """只读报告入口：python tools/eval_corpus_extra.py --report [--root .tmp/eval-corpora] [--json]。"""

    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args

    def option(name: str, default: str | None = None) -> str | None:
        if name not in args:
            return default
        index = args.index(name)
        if index + 1 >= len(args) or args[index + 1].startswith("--"):
            return default
        return args[index + 1]

    root = Path(option("--root", ".tmp/eval-corpora") or ".tmp/eval-corpora")
    out_root = Path(option("--out-root", str(DEFAULT_MATERIALIZED_ROOT)) or str(DEFAULT_MATERIALIZED_ROOT))

    if "--materialize" in args:
        requested = option("--materialize", "--all") or "--all"
        if requested == "--all":
            dataset_ids = [item for item, spec in SOURCES.items() if spec.expectation_kind in _SNIPPET_COLLECTORS]
        else:
            dataset_ids = [requested]
        if not dataset_ids:
            print("没有片段级语料可物化", file=sys.stderr)
            return 2
        results = []
        for dataset_id in dataset_ids:
            try:
                results.append(materialize_snippets(dataset_id, corpus_root=root, out_root=out_root))
            except (KeyError, ValueError, FileNotFoundError) as exc:
                print("%s: %s" % (dataset_id, exc), file=sys.stderr)
                return 1
        if as_json:
            print(json.dumps([item.to_json() for item in results], ensure_ascii=False, indent=2))
            return 0
        for item in results:
            print(
                "%-26s 候选 %-5d 接受 %-5d（%.1f%%） 拒绝 %s 文件级期望 %d"
                % (
                    item.dataset,
                    item.candidates,
                    item.accepted,
                    item.acceptance_rate * 100,
                    json.dumps(item.reject_reasons, ensure_ascii=False),
                    sum(1 for value in item.file_expectations.values() if value),
                )
            )
            print("    产物：%s" % (item.out_root / ("%s@%s" % (item.dataset, item.revision))))
        return 0

    if "--report" not in args and not as_json:
        print(__doc__.splitlines()[0])
        print("用法：python tools/eval_corpus_extra.py --report [--root <语料根>] [--json]")
        print("      python tools/eval_corpus_extra.py --materialize <数据集 id>|--all [--root <语料根>] [--out-root <产物根>] [--json]")
        return 2
    print(render_report(root=root, as_json=as_json))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    raise SystemExit(main())

"""外部第三方行级标注语料：钉死 revision 取用、逐文件 sha256 校验、读成统一注解。

这份文件是什么
--------------
W1「规则保真度」的语料层。它只做四件事：把上游归档取到本地（.tmp/eval-corpora/<id>@<rev>/）、
按上游**自己的**期望格式解析成统一的 Annotation、把「上游 revision + 文件清单 + 逐文件 sha256」
钉进 evaluation/corpora/<id>.lock.json、以及在读之前校验本地文件有没有漂移。

它不是什么
----------
* 不是判定路径：这里没有 rule_id，也没有 allow/block。码 -> rule_id 的映射由 policies/** 推出、
  由 tools/governance_eval.py（harness）负责，本文件不复制第二份真相。
* 不是语料仓库：GPL / LGPL / other 的语料只在运行期落到 .tmp/ 下，仓库只提交 lock。

两个数据集与它们的 oracle 原文位置（口径必须能对着上游原文复核）
------------------------------------------------------------------
1) bandit-functional（Apache-2.0，PyCQA/bandit）
   oracle = bandit/plugins/**.py 的 docstring 里那段由真跑生成的示例。示例的**生成模板**是
   bandit/formatters/text.py:84（模板 ">> Issue: [{test_id}:{test}] {text}"）
   与 :101（"   Location: %s:%s:%s"）；也就是说 Location 里的 <file>:<line>[:<col>] 就是
   bandit 自己上报的位置。**不是** tests/functional/test_functional.py：那里的 expect 字典只有
   SEVERITY / CONFIDENCE 两级**计数**，既没有码也没有行号（见 README 的 cannot 一节）。
   码的来源三条，全部机器可读，且**不 import 上游测试模块**（import 会执行上游测试代码）：
     a. ">> Issue: [B324:hashlib] ..." 括号里的码（实测 15/48 条走这条）；
     b. docstring 所属函数上的 @test.test_id("B602") 装饰器（bandit/core/test_properties.py:53），
        用 ast.unparse 读字面量（实测 12/48 条）；
     c. 模块 docstring 的标题行 "B201: ..."（实测 21/48 条）。
   交叉校验：b/c 解析出的码必须真的出现在该文件的 @test.test_id 声明集合里，否则该条记成跳过
   （原因码 code_not_declared_in_file，可见，不静默）。
2) pycodestyle-testsuite（MIT/Expat，PyCQA/pycodestyle）
   oracle = testing/data/*.py 里形如 "#: E501" / "#: E201:1:6" / "#: Okay" 的行级标注。
   **规范实现在上游 tests/test_data.py**：CASE_RE 在第 15 行（'^(#:.*\\n)'，re.MULTILINE），
   get_tests() 在第 28-61 行（把 src 按 CASE_RE 切成 (注释, 注释之后的源码) 对；注释之前的第一段
   若非空，上游按 '#: Okay' 处理），test() 在第 64-95 行（'Okay' = 期望零诊断；'noeol' = 跑之前先
   把块尾换行去掉；含 ':' 的 token 进 exact 桶，否则进 codes 桶，匹配用 code[:4]）。
   精确位置的口径来自 testing/support.py 的 InMemoryReport.error（第 20-26 行）：
   f'{code}:{line_number}:{offset + 1}' —— 即 '#: E201:1:6' 里的 1:6 是**块内** 1 基 行:列。
   解码口径来自 pycodestyle.py:readlines（第 1761 行）：tokenize.open，失败回落 latin-1。

line / scope 的口径（契约 v1.1：Annotation 的字段没变，scope 是追加导出）
------------------------------------------------------------------------
* Annotation.line = **上游给这条期望锚定的那一行**：
    - bandit: Location: examples/x.py:<line>[:<col>] 的 <line>（bandit 自己上报的行）；
    - pycodestyle: 那条 "#:" 注释所在的行（与上游 pytest case id f'{fname}:{line}' 同一行）。
  **`line == 0` 是契约允许的一种形状**：上游只给到文件级/定义级粒度（例如 pydocstyle 的断言是
  `(定义名, 消息)`，没有行号）。此时作用域是哨兵值 `[0, 0]`（`expected_lines` 必为空），
  它表示「这个文件里出现了这个码」，**不能**与行级读数合并成一个数。本模块自带的两个数据集
  都是行级（`line >= 1`），文件级来自 `eval_corpus_extra.py` 的语料。
* 期望的**作用域**由 annotation_scopes() 给出（1 基闭区间 [scope_start, scope_end]）：
    - bandit: [line, line]；
    - pycodestyle: [marker_line + 1, 下一个 "#:" 行 - 1 或文件末行]。
  另给 expected_lines（上游明确给了精确位置的那些绝对行号），空元组 = 上游只给到作用域。
  为什么必须分开：上游 pycodestyle 的期望是**块级**的（"#: E501" 管的是它之后的一整段源码），
  单个 line 装不下；只按 (file, line, code) 等值匹配会把它判成全错。

四处与上游不一致的地方（都写在这里，不许靠猜）
--------------------------------------------
* 上游 get_tests() 的 case id 只在「块非空」时才把行号往前推，于是空块之后的行号会偏小
  （实测 testing/data/E30.py：真实在第 19 行的 "#: E302:2:1"，上游会记成 16）。那个 id 只作
  pytest 展示用、不参与匹配；本文件按**真实行号**计算。这是唯一一处刻意偏离上游 id 的地方。
* 上游自己带的 2 条 Location 指向不存在的文件 / 越界行（**上游自身漂移，不是我方解析失败**），
  本文件把它们记进 skipped 并计数，不猜、不钳位，原文见 README。
* "Okay" / "noeol" 是上游的 token，不是 ruff 码：Okay 产出 code="Okay" 的**负例**注解
  （期望这一段一条都不报），noeol 是指令（只计数，不产出注解）。
* 上游 pycodestyle 的块级期望里，裸码（"#: E501"，不带 :line:col）没有单一命中行。这类注解的
  line 落在 "#:" 行上，真正可比的位置由 annotation_scopes() 的 [scope_start, scope_end] 给出。

结构自检（不通过即非零退出，不许降级）
------------------------------------
annotation_report() 会对每条保留的注解跑 _self_check()：作用域必须是合法闭区间；上游给的每个
精确位置必须落在这个闭区间内；锚定行必须在作用域内。自检失败会进 self_check_failures，
CLI 打印并**以退出码 1 结束**。命令见 README。

注解与作用域怎么配对（别踩这个坑）
------------------------------------
`load_annotations()` 与 `annotation_scopes()` 各自调一次 `annotation_report()`，是**两次独立解析**，
两次拿到的 `Annotation` 是不同对象。所以：

* 要两者都有，**只调一次 `annotation_scopes()`**，从 `scope.annotation` 取注解——
  同一次调用里它们就是同一批对象；
* **不要按 `id()` 配对**：frozen dataclass 每次重建，实测能配上 `0/657`，
  于是静默退回"没有作用域"的回落分支（口径降级但不报错，最难发现）；
* **也不要完全依赖按值配对**：pycodestyle 上有 3 组同一个注解值对应不同 `expected_lines` 的歧义
  （多 token 用例，如 `#: E252:1:15 E252:1:16`）；
* 顺带一条自检：`len(annotation_scopes(...))` 必须等于 `len(load_annotations(...))`，不等就是坏了。

扩展点（tools/eval_corpus_extra.py，owner=eval-extend）
-------------------------------------------------------
同目录下存在 eval_corpus_extra.py 时，本模块按绝对路径用 importlib 加载它并合并它的
SOURCES / PARSERS（不存在则什么都不做）。加载前本模块已把自己登记进 sys.modules["eval_corpus"]，
所以扩展模块里 import eval_corpus 拿到的就是**同一个** Annotation / SourceSpec 类。
id 或 expectation_kind 冲突一律显式报错，不覆盖。

用法
----
    python tools/eval_corpus.py --list
    python tools/eval_corpus.py --fetch bandit-functional | --fetch all
    python tools/eval_corpus.py --record-lock bandit-functional | --record-lock all
    python tools/eval_corpus.py --verify
    python tools/eval_corpus.py --annotations bandit-functional [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import re
import shutil
import sys
import tarfile
import tokenize
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from importlib import util as importlib_util
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# 协议轴（AGENTS 第 55 条：形状变一个字都要动它）
# ---------------------------------------------------------------------------

ANNOTATION_SCHEMA_VERSION = "1"
LOCK_SCHEMA_VERSION = "1"

DEFAULT_ROOT = Path(".tmp/eval-corpora")
DEFAULT_LOCK_DIR = Path("evaluation/corpora")

EXTRA_FILENAME = "eval_corpus_extra.py"
EXTRA_MODULE_NAME = "eval_corpus_extra"

# bandit 的 revision：gh api repos/PyCQA/bandit/commits/main --jq .sha（2026-10-07 取）
BANDIT_REVISION = "68ebe11ef79263be27ec223184b94a4fc394a622"
# pycodestyle 的 revision：gh api repos/PyCQA/pycodestyle/commits/main --jq .sha（2026-10-07 取）
PYCODESTYLE_REVISION = "f39d0999392236970bec1f01cbb670a4f4e088db"


class CorpusError(RuntimeError):
    """取用/解析/校验的显式失败。绝不吞掉：调用方看到的要么是结论，要么是这条异常。"""


@dataclass(frozen=True)
class Annotation:
    """一条「上游期望」的统一形状。字段与顺序由冻结契约 v1 钉死。"""

    dataset: str
    revision: str
    file: str
    line: int
    code: str
    kind: str
    source: str


@dataclass(frozen=True)
class SourceSpec:
    """一条语料的登记项（数据，不是代码）。字段与顺序由冻结契约 v1 钉死。"""

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


@dataclass(frozen=True)
class AnnotationScope:
    """一条注解的**作用域**（追加导出，不属于冻结契约 v1 的字段集合）。

    scope_start / scope_end 是 1 基闭区间；expected_lines 是上游明确给出精确位置的绝对行号
    （升序，空元组 = 上游只给到作用域）。bandit 里 scope 退化成一个点，于是两个字段相等。
    """

    annotation: Annotation
    scope_start: int
    scope_end: int
    expected_lines: tuple[int, ...]


@dataclass(frozen=True)
class Skip:
    """一条被丢弃的期望（含上游自身漂移）。reason 是稳定原因码，detail 是可复核的原文。"""

    reason: str
    detail: str


# 丢弃原因码（报告里按原因码计数，不拿自由文本当结论）
SKIP_TARGET_MISSING = "target_missing"
SKIP_TARGET_LINE_OUT_OF_RANGE = "target_line_out_of_range"
SKIP_TARGET_OUTSIDE_CORPUS = "target_outside_corpus"
#: 文件在那儿但读不出来（权限 / 变成了目录 / 读到一半消失）：**不是**"上游漂移"（TARGET_MISSING），
#: 也不是崩溃——如实记一条带异常类型的 skip，由读数的人决定要不要管。
SKIP_TARGET_UNREADABLE = "target_unreadable"
SKIP_NO_LOCATION = "expectation_without_location"
SKIP_NO_CODE = "expectation_without_code"
SKIP_UNDECLARED_CODE = "code_not_declared_in_file"
SKIP_UNPARSED_EXPECTATION = "unparsed_expectation"
SKIP_DIRECTIVE = "directive_not_a_code"
SKIP_SELF_CHECK = "structural_self_check_failed"

# 上游的**负例** token（"#: Okay"）：它表示"这一段期望零诊断"，不是码、也没有位置。
# 必须能单独认出来，否则会被当成"码"去做归属映射（那是错的）。
BLANK_EXPECTATION = "Okay"


# ---------------------------------------------------------------------------
# 语料登记（只放数据；新增语料改这里，不写死在函数里）
# ---------------------------------------------------------------------------

SOURCES: dict[str, SourceSpec] = {
    "bandit-functional": SourceSpec(
        id="bandit-functional",
        url=f"https://codeload.github.com/PyCQA/bandit/tar.gz/{BANDIT_REVISION}",
        revision=BANDIT_REVISION,
        license="Apache-2.0",
        license_source=(
            f"https://raw.githubusercontent.com/PyCQA/bandit/{BANDIT_REVISION}/LICENSE"
        ),
        tier="A",
        expectation_kind="bandit-plugin-docstring-location",
        archive_root=f"bandit-{BANDIT_REVISION}",
        # examples/ 是被标注的文件；bandit/plugins/ 与 bandit/blacklists/ 是声明期望的上游文件。
        # tests/functional/test_functional.py 一并取下来：它的 sha256 进 lock，让「这个文件里没有
        # 码、也没有行号」这条结论可以离线复核。LICENSE 取下来是为了许可原文可核。
        paths=(
            "examples",
            "bandit/plugins",
            "bandit/blacklists",
            "tests/functional/test_functional.py",
            "LICENSE",
        ),
        registry_ref="bandit-functional",
    ),
    "pycodestyle-testsuite": SourceSpec(
        id="pycodestyle-testsuite",
        url=f"https://codeload.github.com/PyCQA/pycodestyle/tar.gz/{PYCODESTYLE_REVISION}",
        revision=PYCODESTYLE_REVISION,
        license="MIT/Expat",
        license_source=(
            f"https://raw.githubusercontent.com/PyCQA/pycodestyle/{PYCODESTYLE_REVISION}/LICENSE"
        ),
        tier="A",
        expectation_kind="pycodestyle-hash-colon",
        archive_root=f"pycodestyle-{PYCODESTYLE_REVISION}",
        # testing/data/ 是语料；tests/test_data.py 是 "#:" 的规范实现、testing/support.py 是精确位置
        # {code}:{line}:{col} 的产出点——取下来是为了让本文件的口径能被逐字对账。
        paths=("testing/data", "testing/support.py", "tests/test_data.py", "LICENSE"),
        registry_ref="pycodestyle-testsuite",
    ),
}


# ---------------------------------------------------------------------------
# 解析器注册表
#   PARSERS      : key = expectation_kind，parse(text, spec, rel_path) -> [Annotation]（冻结契约）
#   SCOPE_PARSERS: 同上但返回 [AnnotationScope]（追加导出；没有登记的 kind 回落到「点作用域」）
#   _SCANNERS    : 本模块自己的实现，一次扫描同时给出 scope 与 skipped（不重复扫两遍）
# ---------------------------------------------------------------------------

Parser = Callable[[str, SourceSpec, str], list[Annotation]]
ScopeParser = Callable[[str, SourceSpec, str], list[AnnotationScope]]
Scanner = Callable[[str, SourceSpec, str], tuple[list[AnnotationScope], list[Skip]]]

PARSERS: dict[str, Parser] = {}
SCOPE_PARSERS: dict[str, ScopeParser] = {}
_SCANNERS: dict[str, Scanner] = {}


# ---------------------------------------------------------------------------
# bandit：plugins/**.py docstring 里的 >> Issue / Location
# ---------------------------------------------------------------------------

_BANDIT_ORACLE_DIRS = ("bandit/plugins/", "bandit/blacklists/")
_BANDIT_ISSUE = re.compile(r">>\s*Issue:\s*(.*)")
_BANDIT_BRACKET_CODE = re.compile(r"\[([A-Za-z][A-Za-z0-9]*):[A-Za-z0-9_\-]+\]")
_BANDIT_LOCATION = re.compile(r"Location:\s*(\S+?):(\d+)(?::(\d+))?")
_BANDIT_TEST_ID = re.compile(r"""test_id\(\s*['"]([A-Za-z][A-Za-z0-9]*)['"]\s*\)""")
_BANDIT_HEADING = re.compile(r"^\s*(B[0-9]{3})\s*:", re.MULTILINE)


def _bandit_test_ids(text: str) -> set[str]:
    """该文件里所有 @test.test_id("Bxxx") 声明的码（机器可读，不 import）。"""

    return {match.group(1) for match in _BANDIT_TEST_ID.finditer(text)}


def _bandit_scan(
    text: str, spec: SourceSpec, rel_path: str
) -> tuple[list[AnnotationScope], list[Skip]]:
    """bandit：从 plugins/ 与 blacklists/ 的 docstring 里读 >> Issue / Location。

    口径原文：bandit/formatters/text.py:84（>> Issue: [{test_id}:{test}]）与 :101
    （Location: %s:%s:%s）；码的三条来源见模块 docstring。只用 ast 读，绝不 import 上游模块。
    """

    if not rel_path.startswith(_BANDIT_ORACLE_DIRS) or not rel_path.endswith(".py"):
        return [], []

    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise CorpusError(f"{rel_path}: 上游文件语法错误，无法解析 docstring：{error}") from error

    declared = _bandit_test_ids(text)
    module_doc = ast.get_docstring(tree, clean=False)
    heading_match = _BANDIT_HEADING.search(module_doc) if module_doc else None
    heading = heading_match.group(1) if heading_match else None
    # 模块标题的码必须真的在这个文件里被 @test.test_id 声明过，否则不认这条来源
    # （否则会把别的插件的码安到这一段 docstring 上）。
    heading_code = heading if heading in declared else None

    scopes: list[AnnotationScope] = []
    skips: list[Skip] = []

    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        doc = ast.get_docstring(node, clean=False)
        if not doc:
            continue
        decorator_code: str | None = None
        for decorator in getattr(node, "decorator_list", []):
            match = _BANDIT_TEST_ID.search(ast.unparse(decorator))
            if match and match.group(1) in declared:
                decorator_code = match.group(1)
                break
        owner_code = decorator_code or heading_code
        node_name = f"{type(node).__name__}:{getattr(node, 'name', '<module>')}"

        for issue in _BANDIT_ISSUE.finditer(doc):
            tail = doc[issue.end():]
            following = _BANDIT_ISSUE.search(tail)
            chunk = tail[: following.start()] if following else tail
            bracket = _BANDIT_BRACKET_CODE.search(issue.group(1))
            code = bracket.group(1) if bracket else owner_code
            location = _BANDIT_LOCATION.search(chunk)
            if location is None:
                skips.append(
                    Skip(
                        SKIP_NO_LOCATION,
                        f"{rel_path}:{node_name}: >> Issue 之后没有 Location:（块原文："
                        f"{issue.group(1).strip()[:60]!r}）",
                    )
                )
                continue
            if code is None:
                # 只有真的因此丢了一条期望，才把「模块标题的码没被声明」记成跳过：
                # blacklists/*.py 的标题本来就只是一段说明，那里没有期望，不该算丢弃。
                if heading is not None and heading_code is None and owner_code is None:
                    reason = SKIP_UNDECLARED_CODE
                    note = (
                        f"模块 docstring 标题写的是 {heading}，但该文件没有 "
                        f"@test.test_id('{heading}')，这条来源不采纳"
                    )
                else:
                    reason = SKIP_NO_CODE
                    note = "既没有 [码:名]，也没有可用的 test_id"
                skips.append(
                    Skip(
                        reason,
                        f"{rel_path}:{node_name}: Location={location.group(0)!r} 的码推不出来"
                        f"（{note}）",
                    )
                )
                continue
            target = location.group(1)
            while target.startswith("./"):
                target = target[2:]
            line = int(location.group(2))
            annotation = Annotation(
                dataset=spec.id,
                revision=spec.revision,
                file=target,
                line=line,
                code=code,
                kind=spec.expectation_kind,
                source=rel_path,
            )
            scopes.append(
                AnnotationScope(
                    annotation=annotation,
                    scope_start=line,
                    scope_end=line,
                    expected_lines=(line,),
                )
            )
    return scopes, skips


# ---------------------------------------------------------------------------
# pycodestyle：testing/data/*.py 的 "#:" 行级标注
# ---------------------------------------------------------------------------

_PCS_CASE = re.compile("^(#:.*\n)", re.MULTILINE)
_PCS_DATA_PREFIX = "testing/data/"
_PCS_EXACT = re.compile(r"^([EW][0-9]{3}):(\d+):(\d+)$")
_PCS_CODE = re.compile(r"^[EW][0-9]{3}$")


def _pcs_body_lines(body: str) -> int:
    """一段源码占多少行。

    上游直接用 s.count('\n')，那对「最后一行没有换行符」会少算一行；空段（两个 "#:" 紧挨着）
    则必须算 0 行——把它算成 1 行会让后面所有 case 的行号整体偏一格（实测 E30.py 因此多出 1 行）。
    """

    if not body:
        return 0
    return body.count("\n") + (0 if body.endswith("\n") else 1)


def _pcs_scan(
    text: str, spec: SourceSpec, rel_path: str
) -> tuple[list[AnnotationScope], list[Skip]]:
    """pycodestyle：按上游 tests/test_data.py:get_tests() 的口径切块、按 test() 的口径读 token。

    上游行号账（唯一一处刻意偏离，见模块 docstring）：get_tests() 只在块非空时推进 line，
    空块之后 case id 会偏小；本函数按真实行号推进。
    """

    if not rel_path.startswith(_PCS_DATA_PREFIX) or not rel_path.endswith(".py"):
        return [], []

    segments = _PCS_CASE.split(text)
    first = segments[0]
    cases: list[tuple[int, int, list[str], str, str]] = []  # 标记行, 块首行, 期望 token, 块, 原文
    if first.strip():
        cases.append((1, 1, ["Okay"], first, "#: Okay (上游对'第一个 #: 之前的非空段'的固定口径)"))

    cursor = 1 + _pcs_body_lines(first) if first else 1
    index = 1
    while index + 1 < len(segments):
        comment = segments[index]
        body = segments[index + 1]
        marker_line = cursor
        body_start = marker_line + 1
        cursor = body_start + _pcs_body_lines(body)
        if body.strip():
            cases.append(
                (marker_line, body_start, comment[2:].strip().split(), body, comment.strip())
            )
        index += 2

    scopes: list[AnnotationScope] = []
    skips: list[Skip] = []
    for marker_line, body_start, expectations, body, raw in cases:
        scope_end = body_start + max(_pcs_body_lines(body), 1) - 1
        expected: list[int] = []
        for expectation in expectations:
            if expectation == BLANK_EXPECTATION:
                code, line = BLANK_EXPECTATION, marker_line
            elif expectation == "noeol":
                skips.append(
                    Skip(
                        SKIP_DIRECTIVE,
                        f"{rel_path}:{marker_line}: 上游指令 {raw!r} 里的 noeol"
                        "（跑之前去掉块尾换行），不是码",
                    )
                )
                continue
            elif _PCS_EXACT.match(expectation):
                match = _PCS_EXACT.match(expectation)
                code = match.group(1)
                line = marker_line + int(match.group(2))
                expected.append(line)
            elif _PCS_CODE.match(expectation):
                code, line = expectation, marker_line
            else:
                skips.append(
                    Skip(
                        SKIP_UNPARSED_EXPECTATION,
                        f"{rel_path}:{marker_line}: 认不出的期望 token {expectation!r}"
                        f"（原文 {raw!r}）",
                    )
                )
                continue
            scopes.append(
                AnnotationScope(
                    annotation=Annotation(
                        dataset=spec.id,
                        revision=spec.revision,
                        file=rel_path,
                        line=line,
                        code=code,
                        kind=spec.expectation_kind,
                        source=rel_path,
                    ),
                    scope_start=body_start,
                    scope_end=scope_end,
                    expected_lines=tuple(sorted(expected)),
                )
            )
    return scopes, skips


PARSERS["bandit-plugin-docstring-location"] = lambda text, spec, rel: [
    scope.annotation for scope in _bandit_scan(text, spec, rel)[0]
]
PARSERS["pycodestyle-hash-colon"] = lambda text, spec, rel: [
    scope.annotation for scope in _pcs_scan(text, spec, rel)[0]
]
SCOPE_PARSERS["bandit-plugin-docstring-location"] = lambda text, spec, rel: _bandit_scan(
    text, spec, rel
)[0]
SCOPE_PARSERS["pycodestyle-hash-colon"] = lambda text, spec, rel: _pcs_scan(text, spec, rel)[0]
_SCANNERS["bandit-plugin-docstring-location"] = _bandit_scan
_SCANNERS["pycodestyle-hash-colon"] = _pcs_scan


# ---------------------------------------------------------------------------
# 扩展模块自动发现（不存在必须照常工作）
# ---------------------------------------------------------------------------

_EXTRA_LOADED = False


def _validate_source(dataset_id: str, spec: SourceSpec) -> None:
    if not isinstance(spec, SourceSpec):
        raise CorpusError(f"{dataset_id}: SOURCES 的值必须是 SourceSpec，实际是 {type(spec)!r}")
    if spec.id != dataset_id:
        raise CorpusError(f"{dataset_id}: SourceSpec.id 与字典 key 不一致（{spec.id}）")
    if not spec.revision or spec.revision not in spec.url:
        raise CorpusError(
            f"{dataset_id}: revision 没有钉在 url 里（url={spec.url} rev={spec.revision}）"
        )
    if not spec.archive_root.endswith(spec.revision):
        raise CorpusError(f"{dataset_id}: archive_root 与 revision 不一致（{spec.archive_root}）")
    if not spec.paths:
        raise CorpusError(f"{dataset_id}: paths 不能为空——空 paths 会静默取不到任何文件")


def _load_extra() -> None:
    """发现并合并 tools/eval_corpus_extra.py。文件不存在 = 正常情况，不是错误。"""

    global _EXTRA_LOADED
    if _EXTRA_LOADED:
        return
    _EXTRA_LOADED = True
    path = Path(__file__).resolve().parent / EXTRA_FILENAME
    if not path.is_file():
        return
    spec = importlib_util.spec_from_file_location(EXTRA_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise CorpusError(f"无法为扩展模块建 spec（按绝对路径加载）：{path}")
    module = importlib_util.module_from_spec(spec)
    sys.modules[EXTRA_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - 扩展模块自己的异常必须显式带出来
        raise CorpusError(
            f"扩展模块加载失败：{path}：{type(error).__name__}: {error}"
        ) from error
    extra_sources = getattr(module, "SOURCES", None)
    extra_parsers = getattr(module, "PARSERS", None)
    if not isinstance(extra_sources, dict) or not isinstance(extra_parsers, dict):
        raise CorpusError(f"{path}: 必须导出 dict 形态的 SOURCES 与 PARSERS")
    for dataset_id, source in extra_sources.items():
        if dataset_id in SOURCES:
            raise CorpusError(f"数据集 id 冲突：{dataset_id} 同时存在于本模块与 {EXTRA_FILENAME}")
        _validate_source(dataset_id, source)
        SOURCES[dataset_id] = source
    for kind, parser in extra_parsers.items():
        if kind in PARSERS:
            raise CorpusError(f"expectation_kind 冲突：{kind} 同时存在于本模块与 {EXTRA_FILENAME}")
        if not callable(parser):
            raise CorpusError(f"{path}: PARSERS[{kind}] 不是可调用的解析器")
        PARSERS[kind] = parser
    extra_scopes = getattr(module, "SCOPE_PARSERS", None)
    if isinstance(extra_scopes, dict):
        for kind, parser in extra_scopes.items():
            if kind not in PARSERS:
                raise CorpusError(f"{path}: SCOPE_PARSERS 里的 {kind} 没有对应的 PARSERS 条目")
            if not callable(parser):
                raise CorpusError(f"{path}: SCOPE_PARSERS[{kind}] 不是可调用的解析器")
            SCOPE_PARSERS[kind] = parser


def _source(dataset_id: str) -> SourceSpec:
    try:
        return SOURCES[dataset_id]
    except KeyError:
        known = ", ".join(sorted(SOURCES)) or "<空>"
        raise CorpusError(f"未知数据集 id：{dataset_id!r}；已知：{known}") from None


def available_datasets() -> list[str]:
    """所有可用数据集 id（升序）。扩展模块的条目会一起出现在这里。"""

    return sorted(SOURCES)


def _validate_registry() -> None:
    for dataset_id, spec in SOURCES.items():
        _validate_source(dataset_id, spec)
        if spec.expectation_kind not in PARSERS:
            raise CorpusError(
                f"{dataset_id}: expectation_kind={spec.expectation_kind!r} 没有对应解析器"
            )


# ---------------------------------------------------------------------------
# 取用：下载 -> 校验归档形状 -> 只解压 paths 命中的成员 -> 原子落到 <root>/<id>@<rev>/
# ---------------------------------------------------------------------------


def dataset_dir(dataset_id: str, root: Path) -> Path:
    """语料在本地应该待的位置：<root>/<id>@<revision>/。"""

    spec = _source(dataset_id)
    return Path(root) / f"{spec.id}@{spec.revision}"


def _is_fetched(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    return any(item.is_file() for item in directory.rglob("*"))


def fetch(dataset_id: str, *, root: Path, offline: bool = False) -> Path:
    """把语料取到 root 下并返回它的目录。offline=True 时只用本地已有的，缺了就报错。"""

    spec = _source(dataset_id)
    destination = dataset_dir(dataset_id, root)
    if _is_fetched(destination):
        return destination
    if offline:
        raise CorpusError(
            f"offline=True 且本地语料不存在或不完整：{destination}（先跑 --fetch {dataset_id}）"
        )
    payload = _download(spec)
    _materialize(spec, payload, destination)
    return destination


def _download(spec: SourceSpec) -> bytes:
    # 只允许 https：url 来自本文件钉死的登记表，但把"别的 scheme 一律拒绝"写成会失败的检查，
    # 而不是留成一句注释。（ruff 的 S310 不做守卫分析，所以这里带一条写明理由的 noqa。）
    if not spec.url.startswith("https://"):
        raise CorpusError(
            f"{spec.id}: url 不是 https，拒绝下载（可能是 file:/ftp:/自定义 scheme）：{spec.url}"
        )
    request = urllib.request.Request(  # noqa: S310 - 上一行已显式拒绝非 https 的 scheme
        spec.url, headers={"User-Agent": "engineering-policy-platform/eval-corpus"}
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - 同上
            request, timeout=180
        ) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        raise CorpusError(f"{spec.id}: 下载失败 HTTP {error.code}：{spec.url}") from error
    except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
        # IncompleteRead 是 http.client.HTTPException：既不是 URLError 也不是 OSError，
        # 传输被截断时会从这里逃出去（模块契约是"要么给结论，要么给 CorpusError"）。
        raise CorpusError(f"{spec.id}: 下载失败：{spec.url}：{error}") from error
    if not payload:
        raise CorpusError(f"{spec.id}: 下载到 0 字节：{spec.url}")
    return payload


def _archive_members(spec: SourceSpec, payload: bytes) -> dict[str, bytes]:
    """把归档读成 {相对 archive_root 的 POSIX 路径: 内容}，并对形状做显式校验。"""

    members: dict[str, bytes] = {}
    # 解析失败必须翻成 CorpusError：BadZipFile / tarfile 的错误都是普通 Exception 子类，
    # 逃出去就是 --fetch 上的一段栈回溯（200 响应但内容是畸形/截断/恰好以 PK 开头的非 zip 体都会走到这里）。
    if payload[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = archive.namelist()
                tops = {name.split("/", 1)[0] for name in names if "/" in name}
                _require_single_root(spec, tops)
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    relative = _strip_archive_root(spec, info.filename)
                    if relative is None:
                        continue
                    members[relative] = archive.read(info)
        except zipfile.BadZipFile as error:
            raise CorpusError(f"{spec.id}: 归档不是合法 zip（{error}）：{spec.url}") from error
    else:
        try:
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
                entries = archive.getmembers()
                tops = {entry.name.split("/", 1)[0] for entry in entries if "/" in entry.name}
                _require_single_root(spec, tops)
                for entry in entries:
                    if not entry.isfile():
                        continue
                    relative = _strip_archive_root(spec, entry.name)
                    if relative is None:
                        continue
                    handle = archive.extractfile(entry)
                    if handle is None:
                        raise CorpusError(f"{spec.id}: 归档成员读不出来：{entry.name}")
                    members[relative] = handle.read()
        except tarfile.TarError as error:
            raise CorpusError(
                f"{spec.id}: 归档不是合法 tar（{type(error).__name__}: {error}）：{spec.url}"
            ) from error
    return members


def _require_single_root(spec: SourceSpec, tops: set[str]) -> None:
    if tops != {spec.archive_root}:
        raise CorpusError(
            f"{spec.id}: 归档顶层目录与 archive_root 对不上；期望 {spec.archive_root!r}，"
            f"实际 {sorted(tops)!r}（多半是 url 里的 sha 与实际下载到的内容不一致）"
        )


def _strip_archive_root(spec: SourceSpec, name: str) -> str | None:
    if not name.startswith(spec.archive_root + "/"):
        return None
    relative = name[len(spec.archive_root) + 1 :]
    if not relative or relative.endswith("/"):
        return None
    if "\\" in relative or relative.startswith("/") or ":" in relative.split("/")[0]:
        raise CorpusError(f"{spec.id}: 归档里有非法路径：{name!r}")
    if any(part in ("", ".", "..") for part in relative.split("/")):
        raise CorpusError(f"{spec.id}: 归档路径含 . 或 .. ：{name!r}")
    return relative


def _wanted(relative: str, paths: tuple[str, ...]) -> bool:
    for candidate in paths:
        prefix = candidate.rstrip("/")
        if relative == prefix or relative.startswith(prefix + "/"):
            return True
    return False


def _materialize(spec: SourceSpec, payload: bytes, destination: Path) -> None:
    members = _archive_members(spec, payload)
    selected = {name: blob for name, blob in members.items() if _wanted(name, spec.paths)}
    unmatched = [
        candidate
        for candidate in spec.paths
        if not any(
            name == candidate.rstrip("/") or name.startswith(candidate.rstrip("/") + "/")
            for name in members
        )
    ]
    if unmatched:
        raise CorpusError(
            f"{spec.id}: paths 里的条目在上游归档里一条都没命中：{unmatched}"
            "（拼错目录不许静默少取文件）"
        )
    if not selected:
        raise CorpusError(f"{spec.id}: paths 过滤之后一个文件都不剩，拒绝落盘")

    staging = destination.parent / f".{destination.name}.partial"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    for name in sorted(selected):
        target = staging / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(selected[name])
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(destination)


# ---------------------------------------------------------------------------
# 读文本 / 读注解
# ---------------------------------------------------------------------------


def _decode(data: bytes) -> str:
    """与上游 pycodestyle.py:readlines（第 1761 行）同一口径：tokenize.open，失败回落 latin-1。"""

    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        text = data.decode(encoding)
    except (LookupError, SyntaxError, UnicodeDecodeError):
        text = data.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _iter_corpus_files(base: Path):
    """按稳定顺序产出 (相对 POSIX 路径, 文本或 None, 备注)。读不出来的文件进 unreadable。"""

    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(base).as_posix()
        try:
            data = path.read_bytes()
        except OSError as error:
            yield relative, None, f"read_failed:{type(error).__name__}"
            continue
        if b"\x00" in data[:4096]:
            yield relative, None, "binary"
            continue
        yield relative, _decode(data), ""


def _self_check(scopes: list[AnnotationScope]) -> list[str]:
    """结构自检：作用域必须是合法闭区间，且上游给的每个**精确位置**必须落在作用域内。

    两条判据的边界写清楚：

    * **零作用域 [0, 0] = 文件级**（契约 v1：line == 0）。它对 `line == 0` 的注解**合法**，
      对带行号的注解**非法**；文件级期望也不许挂 expected_lines（它没有行号）。
      早期实现把 [0, 0] 一律判成「非法闭区间」，等于把契约明确允许的一种形状整批吃掉——
      那不是"严格"，那是把 D 类语料（pydocstyle 等定义级标注）在宿主侧变成不可用。
    * **line > 0 的注解**照旧：`1 <= scope_start <= scope_end`，上游给的每个精确位置必须落在
      `[scope_start, scope_end]` 内，越界即失败。

    注意：锚定行（Annotation.line）**不要求**落在作用域内——pycodestyle 的锚定行就是 "#:" 那一行，
    而期望作用的是它**之后**的块，两者天然相差一行。要求锚定行在域内会把正确解析判成错误。
    不通过就是解析器坏了（不是上游漂移），调用方必须让命令以非零退出——不许降级成「跳过」。
    """

    failures: list[str] = []
    for scope in scopes:
        annotation = scope.annotation
        where = f"{annotation.code} {annotation.file}:{annotation.line}"
        if scope.scope_start == 0 and scope.scope_end == 0:
            # 契约 v1：line == 0 = 文件级（上游只给到文件级/定义级粒度）。零作用域 [0, 0] 是它的
            # **合法**取值，不是坏解析——早期实现把它判成「非法闭区间」并整条丢弃，等于把契约明确
            # 允许的一种形状吃掉（实测 pydocstyle 72 条一条不剩）。允许它，但只允许挂在这种注解上：
            if annotation.line != 0:
                failures.append(
                    f"{where}: 零作用域 [0, 0] 只对文件级注解（line == 0）合法；"
                    "带行号的注解必须给出真实闭区间"
                )
            if scope.expected_lines:
                failures.append(
                    f"{where}: 零作用域 [0, 0] 上不许挂精确位置 "
                    f"{list(scope.expected_lines)}（文件级期望没有行号）"
                )
            continue
        if scope.scope_start < 1 or scope.scope_end < scope.scope_start:
            failures.append(f"{where}: 作用域非法 [{scope.scope_start}, {scope.scope_end}]")
            continue
        for line in scope.expected_lines:
            if not scope.scope_start <= line <= scope.scope_end:
                failures.append(
                    f"{where}: 精确位置 {line} 落在作用域 "
                    f"[{scope.scope_start}, {scope.scope_end}] 之外"
                )
    return failures


def _resolve_point_scope(scope: AnnotationScope) -> AnnotationScope:
    """点作用域（`scope_start == scope_end >= 1`）**就是**一个精确位置：写进 `expected_lines`。

    为什么必须做：`tools/governance_eval.py` 的 `position_bucket`（第 601 行）按
    「`expected_lines` 为空 **且** `scope_end == scope_start`」判**文件桶**，那里的匹配会放宽成
    「这个文件里出现过这个码」。于是行级的点作用域被读成"文件级"：既算错了行级分母，又把位置
    比对悄悄放松。实测（归一化之前）有 **215 条**被这样读：pep8-naming 32、tryceratops 63、
    pycodestyle 的单行块 120。

    契约说 `expected_lines` = 「上游明确给出精确位置的那些**绝对行号**」。单行作用域能命中的行
    只有那一行——这是**把已经成立的事实写出来**，不是新增一条期望（作用域一个数都没改）。

    两个例外，都不归一化：
    * `[0, 0]`：契约的文件级哨兵，它本来就没有行号（`scope_start >= 1` 那道判断挡住）；
    * `code == "Okay"`：上游的**负例**，语义是"这一段零诊断"，没有位置可言。
    """

    if (
        scope.annotation.code != BLANK_EXPECTATION
        and not scope.expected_lines
        and scope.scope_start == scope.scope_end
        and scope.scope_start >= 1
    ):
        return AnnotationScope(
            scope.annotation, scope.scope_start, scope.scope_end, (scope.scope_start,)
        )
    return scope


def _drop_reason(
    base: Path, scope: AnnotationScope, line_cache: dict[str, int | None]
) -> Skip | None:
    """目标文件不存在 / 行号越界 / 跑出语料根：上游自身漂移那一类，记 skipped 而不是报错。"""

    annotation = scope.annotation
    base_resolved = base.resolve()
    target = (base / annotation.file).resolve()
    # 真包含判定（路径级，不是字符串前缀）：`<root>/<id>@<rev>-backup/x.py` 的字符串确实以
    # 语料根的字符串开头，字符串前缀测试会把它当成语料内容——那份文件根本没被锁覆盖。
    if target != base_resolved and base_resolved not in target.parents:
        return Skip(SKIP_TARGET_OUTSIDE_CORPUS, f"{annotation.code} {annotation.file}")
    if annotation.file not in line_cache:
        # 一次读到底（旧实现是 `is_file()` 再 `read_bytes()`：中间那一小段是 TOCTOU 窗口，
        # 而且 `read_bytes()` 本身没守护——权限错误/目标变成目录都会裸抛 OSError，
        # 逃出 annotation_report()/load_annotations()，与模块契约不符）。
        try:
            data = target.read_bytes()
        except (FileNotFoundError, NotADirectoryError):
            line_cache[annotation.file] = None
        except OSError as error:
            return Skip(
                SKIP_TARGET_UNREADABLE,
                f"{annotation.code} {annotation.file}:{annotation.line}"
                f"（读不出来：{type(error).__name__}: {error}；声明于 {annotation.source}）",
            )
        else:
            line_cache[annotation.file] = len(_decode(data).splitlines())
    total = line_cache[annotation.file]
    if total is None:
        return Skip(
            SKIP_TARGET_MISSING,
            f"{annotation.code} {annotation.file}:{annotation.line}（声明于 {annotation.source}）",
        )
    if annotation.line > total:
        return Skip(
            SKIP_TARGET_LINE_OUT_OF_RANGE,
            f"{annotation.code} {annotation.file}:{annotation.line}"
            f"（该文件只有 {total} 行；声明于 {annotation.source}）",
        )
    return None


def annotation_report(dataset_id: str, *, root: Path) -> dict:
    """解析 + 丢弃过滤 + 结构自检的完整读数（追加导出；load_annotations 只是它的 annotations）。

    返回键：annotations / scopes / skipped / unreadable / self_check_failures / counts。
    skipped 里的每一条都带原因码，不许静默——上游自身漂移也算在这里，并且是**可复核的事实**。
    """

    spec = _source(dataset_id)
    base = dataset_dir(dataset_id, root)
    if not _is_fetched(base):
        raise CorpusError(f"语料不存在：{base}（先跑 --fetch {dataset_id}）")
    parser = PARSERS[spec.expectation_kind]
    # 三层，优先级从高到低：本模块的 scanner（一次扫描同时给作用域与 skipped）→ 扩展模块登记的
    # scope 解析器 → 只登记了 PARSERS 的扩展模块：作用域退化成点，line == 0 时退化成 [0, 0]。
    # 中间这一层曾经是**死代码**：SCOPE_PARSERS 只在 scanner 分支里被查过，扩展模块登记了它
    # 也永远不生效（实测会拿 AnnotationScope 当 Annotation 用，直接 AttributeError）。
    scanner = _SCANNERS.get(spec.expectation_kind)
    scope_parser = SCOPE_PARSERS.get(spec.expectation_kind)

    skipped: list[Skip] = []
    unreadable: list[str] = []
    scopes: list[AnnotationScope] = []
    for relative, text, note in _iter_corpus_files(base):
        if text is None:
            if note != "binary":
                unreadable.append(f"{relative}: {note}")
            continue
        if scanner is not None:
            found, drops = scanner(text, spec, relative)
        elif scope_parser is not None:
            found, drops = scope_parser(text, spec, relative), []
        else:
            found = [
                AnnotationScope(annotation, annotation.line, annotation.line, ())
                for annotation in parser(text, spec, relative)
            ]
            drops = []
        scopes.extend(found)
        skipped.extend(drops)

    kept: list[AnnotationScope] = []
    line_cache: dict[str, int | None] = {}
    overrun: list[str] = []
    for scope in scopes:
        scope = _resolve_point_scope(scope)
        drop = _drop_reason(base, scope, line_cache)
        if drop is not None:
            skipped.append(drop)
            continue
        total = line_cache[scope.annotation.file]
        assert total is not None  # _drop_reason 已经保证：目标文件不存在时不会走到这里
        # 零作用域 = 文件级期望，没有"末端"可比，越界检查对它不适用（精确位置必须为空，
        # 这一条由 _self_check 单独把关）。line > 0 的注解照旧逐条比行数。
        if scope.scope_start == 0 and scope.scope_end == 0:
            kept.append(scope)
            continue
        if scope.scope_end > total:
            overrun.append(
                f"{scope.annotation.code} {scope.annotation.file}: "
                f"作用域末端 {scope.scope_end} 超出文件行数 {total}"
            )
            continue
        kept.append(scope)

    failures = overrun + _self_check(kept)
    if failures:
        bad = {id(scope) for scope in kept if _self_check([scope])}
        kept = [scope for scope in kept if id(scope) not in bad]
        skipped.extend(Skip(SKIP_SELF_CHECK, message) for message in failures)

    annotations = sorted(
        [scope.annotation for scope in kept],
        key=lambda item: (item.file, item.line, item.code, item.source),
    )
    codes: dict[str, int] = {}
    for annotation in annotations:
        codes[annotation.code] = codes.get(annotation.code, 0) + 1
    return {
        "dataset": dataset_id,
        "revision": spec.revision,
        "expectation_kind": spec.expectation_kind,
        "annotations": annotations,
        "scopes": kept,
        "skipped": skipped,
        "unreadable": unreadable,
        "self_check_failures": failures,
        "counts": {
            "annotations": len(annotations),
            "files": len({annotation.file for annotation in annotations}),
            "codes": dict(sorted(codes.items())),
            "skipped": len(skipped),
        },
    }


def load_annotations(dataset_id: str, *, root: Path) -> list[Annotation]:
    """读成统一注解。丢掉的条目在 annotation_report() 的 skipped 里可见。

    **它和 annotation_scopes() 是两次独立解析**（各自调一次 annotation_report），所以两次调用
    产出的 Annotation 是**不同的对象**。要把注解和作用域配对，请只用 annotation_scopes() 一次调用、
    从 scope.annotation 取注解（同一次调用里它们是同一批对象）；不要 `id()` 配对——实测
    `id()` 能配上 **0/657**（frozen dataclass 每次重建），也不要依赖"按值配对"：pycodestyle 上有
    **3 组**同一个注解值对应不同 expected_lines 的歧义（E251/E252/E221 的多 token 用例）。
    """

    return annotation_report(dataset_id, root=root)["annotations"]


def corpus_files(dataset_id: str, *, root: Path) -> list[str]:
    """该数据集里**有 ground truth** 的文件（= 注解出现过的文件，升序去重）。

    刻意不是「目录下所有 .py」：bandit 的 examples/ 有 90 个文件，只有 34 个带上游行级期望；
    把没标注的文件也当「期望空白」，会把该工具的正常诊断整批算成误报。
    """

    annotations = load_annotations(dataset_id, root=root)
    return sorted({annotation.file for annotation in annotations})


def annotation_scopes(dataset_id: str, *, root: Path) -> list[AnnotationScope]:
    """追加导出（契约 v1.1）：每条注解的期望作用域。见模块 docstring 的 line / scope 口径。

    **这是把注解与作用域配对的唯一可靠入口**：一次调用里 `scope.annotation` 就是那一条注解本身
    （对象同一），所以 `[(s.annotation, s) for s in annotation_scopes(...)]` 永远 1:1 且无歧义。
    另外：`len(scopes)` 与 `len(load_annotations(...))` 必须相等，不等就是解析器或过滤坏了。
    """

    return annotation_report(dataset_id, root=root)["scopes"]


def structural_self_check(dataset_id: str, *, root: Path) -> list[str]:
    """追加导出：结构自检的失败清单（空 = 通过）。CLI 非零退出的判据就是它。"""

    return annotation_report(dataset_id, root=root)["self_check_failures"]


# ---------------------------------------------------------------------------
# lock：上游 revision + 文件清单 + 逐文件 sha256
# ---------------------------------------------------------------------------


def lock_path(dataset_id: str, lock_dir: Path) -> Path:
    return Path(lock_dir) / f"{dataset_id}.lock.json"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _list_files(base: Path) -> list[str]:
    return sorted(
        path.relative_to(base).as_posix() for path in base.rglob("*") if path.is_file()
    )


def write_lock(dataset_id: str, *, root: Path, lock_dir: Path) -> Path:
    """把当前语料钉成 lock。内容与运行时间无关（相同语料得到逐字节相同的 lock）。"""

    spec = _source(dataset_id)
    base = dataset_dir(dataset_id, root)
    if not _is_fetched(base):
        raise CorpusError(f"语料不存在，无法记 lock：{base}（先跑 --fetch {dataset_id}）")
    files = [
        {
            "path": relative,
            "sha256": _file_digest(base / relative),
            "size": (base / relative).stat().st_size,
        }
        for relative in _list_files(base)
    ]
    payload = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "dataset": spec.id,
        "revision": spec.revision,
        "url": spec.url,
        "license": spec.license,
        "license_source": spec.license_source,
        "tier": spec.tier,
        "expectation_kind": spec.expectation_kind,
        "archive_root": spec.archive_root,
        "paths": list(spec.paths),
        "registry_ref": spec.registry_ref,
        "file_count": len(files),
        "files": files,
    }
    destination = lock_path(dataset_id, lock_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return destination


def verify(dataset_id: str, *, root: Path, lock_dir: Path) -> tuple[bool, list[str]]:
    """比对 lock 与本地语料，并跑结构自检。返回 (是否通过, 问题清单)。"""

    spec = _source(dataset_id)
    problems: list[str] = []
    locked_path = lock_path(dataset_id, lock_dir)
    if not locked_path.is_file():
        return False, [f"{dataset_id}: lock 不存在：{locked_path}（先跑 --record-lock）"]
    try:
        payload = json.loads(locked_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return False, [f"{dataset_id}: lock 读不出来：{locked_path}：{error}"]
    if payload.get("schema_version") != LOCK_SCHEMA_VERSION:
        problems.append(
            f"{dataset_id}: lock 的 schema_version={payload.get('schema_version')!r}，"
            f"期望 {LOCK_SCHEMA_VERSION!r}"
        )
    if payload.get("dataset") != spec.id:
        problems.append(f"{dataset_id}: lock 里的 dataset={payload.get('dataset')!r} 对不上")
    if payload.get("revision") != spec.revision:
        problems.append(
            f"{dataset_id}: 上游 revision 漂移：lock={payload.get('revision')!r}，"
            f"登记表={spec.revision!r}（改 revision 必须显式重记 lock）"
        )
    if payload.get("url") != spec.url:
        problems.append(f"{dataset_id}: lock 里的 url 与登记表不一致")

    base = dataset_dir(dataset_id, root)
    if not _is_fetched(base):
        problems.append(f"{dataset_id}: 本地语料不存在：{base}（先跑 --fetch）")
        return False, problems

    locked = {item["path"]: item for item in payload.get("files", [])}
    present = _list_files(base)
    for relative in sorted(set(locked) - set(present)):
        problems.append(f"{dataset_id}: lock 里列了但本地没有：{relative}")
    for relative in sorted(set(present) - set(locked)):
        problems.append(f"{dataset_id}: 本地有但 lock 没覆盖：{relative}（lock 不完整）")
    for relative in sorted(set(locked) & set(present)):
        actual = _file_digest(base / relative)
        if actual != locked[relative]["sha256"]:
            problems.append(
                f"{dataset_id}: sha256 漂移：{relative}：lock={locked[relative]['sha256']}，"
                f"实际={actual}"
            )

    report = annotation_report(dataset_id, root=root)
    problems.extend(
        f"{dataset_id}: 结构自检失败：{failure}" for failure in report["self_check_failures"]
    )
    # 刻意**不**把「上游期望指向的目标不存在 / 行号越界」算成 verify 失败：那是**上游自身的不一致**
    # （我们钉死的那个 revision 里就写着），不是我方语料漂移。把它算成失败会让 verify 永久红，
    # 于是没人再看它——那才是真正的静默。它们照旧进 annotation_report 的 skipped，由 --list /
    # --annotations / --verify 的 NOTE 段显式打印。
    return not problems, problems


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _level_split(scopes: list[AnnotationScope]) -> tuple[int, int]:
    """(文件级 line == 0 的条数, 行级 line > 0 的条数)。

    两者测的不是同一件事：行级能对位置，文件级只能对"这个文件里出现了这个码"。任何一个合计数字
    都必须能拆开（契约 v1 把 line == 0 定义为文件级；这里只是把它显式读出来）。
    刻意不塞进 --json 载荷：那要给 ANNOTATION_SCHEMA_VERSION 升版（AGENTS 第 55 条），
    而契约把这个常量钉成了 "1"。文本输出不受版本轴约束，所以先落在这里。
    """

    file_level = sum(1 for scope in scopes if scope.annotation.line == 0)
    return file_level, len(scopes) - file_level


def _targets(argument: str) -> list[str]:
    if argument == "all":
        return available_datasets()
    _source(argument)
    return [argument]


def _print_report(report: dict, as_json: bool) -> None:
    if as_json:
        payload = {
            "schema_version": ANNOTATION_SCHEMA_VERSION,
            "dataset": report["dataset"],
            "revision": report["revision"],
            "expectation_kind": report["expectation_kind"],
            "counts": report["counts"],
            "self_check_failures": report["self_check_failures"],
            "unreadable": report["unreadable"],
            "skipped": [
                {"reason": item.reason, "detail": item.detail} for item in report["skipped"]
            ],
            "annotations": [
                {
                    "dataset": item.dataset,
                    "revision": item.revision,
                    "file": item.file,
                    "line": item.line,
                    "code": item.code,
                    "kind": item.kind,
                    "source": item.source,
                }
                for item in report["annotations"]
            ],
            "scopes": [
                {
                    "file": scope.annotation.file,
                    "line": scope.annotation.line,
                    "code": scope.annotation.code,
                    "scope_start": scope.scope_start,
                    "scope_end": scope.scope_end,
                    "expected_lines": list(scope.expected_lines),
                }
                for scope in report["scopes"]
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"dataset         : {report['dataset']}")
    print(f"revision        : {report['revision']}")
    print(f"expectation_kind: {report['expectation_kind']}")
    file_level, line_level = _level_split(report["scopes"])
    print(f"annotations     : {report['counts']['annotations']}")
    print(f"  file-level    : {file_level}   (line == 0：上游只给到文件级/定义级)")
    print(f"  line-level    : {line_level}   (line > 0：可与诊断行比对)")
    print(f"corpus files    : {report['counts']['files']}")
    print(f"skipped         : {report['counts']['skipped']}")
    print("codes:")
    for code, count in report["counts"]["codes"].items():
        print(f"  {code:<8} {count}")
    print("annotations (file:line  code  scope  exact; scope [0,0] = 文件级):")
    for scope in report["scopes"]:
        item = scope.annotation
        exact = ",".join(str(number) for number in scope.expected_lines) or "-"
        print(
            f"  {item.file}:{item.line}  {item.code:<8} "
            f"[{scope.scope_start},{scope.scope_end}]  {exact}"
        )
    if report["self_check_failures"]:
        print("self-check failures (退出码 1；解析器坏了，不是上游漂移):")
        for failure in report["self_check_failures"]:
            print(f"  {failure}")
    if report["skipped"]:
        print("skipped:")
        for item in report["skipped"]:
            print(f"  {item.reason}: {item.detail}")
    if report["unreadable"]:
        print("unreadable:")
        for item in report["unreadable"]:
            print(f"  {item}")
    print("self-check      : " + ("ok" if not report["self_check_failures"] else "FAILED"))


def _command_list(root: Path, lock_dir: Path) -> int:
    failed = False
    for dataset_id in available_datasets():
        spec = _source(dataset_id)
        base = dataset_dir(dataset_id, root)
        fetched = _is_fetched(base)
        locked = lock_path(dataset_id, lock_dir).is_file()
        print(f"{dataset_id}")
        print(f"  registry_ref    : {spec.registry_ref}")
        print(f"  tier / license  : {spec.tier} / {spec.license}")
        print(f"  revision        : {spec.revision}")
        print(f"  url             : {spec.url}")
        print(f"  expectation_kind: {spec.expectation_kind}")
        print(f"  paths           : {', '.join(spec.paths)}")
        print(f"  corpus dir      : {base}  [{'已取到' if fetched else '未取到'}]")
        print(f"  lock            : {lock_path(dataset_id, lock_dir)}"
              f"  [{'存在' if locked else '缺失'}]")
        if not fetched:
            print("  annotations     : n/a（未取到语料，先跑 --fetch）")
            print("  self-check      : n/a")
            continue
        report = annotation_report(dataset_id, root=root)
        file_level, line_level = _level_split(report["scopes"])
        print(
            f"  annotations     : {report['counts']['annotations']} 条 / "
            f"{report['counts']['files']} 个文件 / {len(report['counts']['codes'])} 个码"
        )
        print(f"    文件级(line=0) : {file_level}")
        print(f"    行级(line>0)   : {line_level}")
        print(f"  skipped         : {report['counts']['skipped']}")
        for item in report["skipped"]:
            print(f"    - {item.reason}: {item.detail}")
        if report["self_check_failures"]:
            failed = True
            print("  self-check      : FAILED")
            for failure in report["self_check_failures"]:
                print(f"    {failure}")
        else:
            print("  self-check      : ok")
    return 1 if failed else 0


def _command_fetch(argument: str, root: Path, offline: bool) -> int:
    for dataset_id in _targets(argument):
        directory = fetch(dataset_id, root=root, offline=offline)
        files = len(_list_files(directory))
        print(f"{dataset_id}: 已就绪 {directory}（{files} 个文件）")
    return 0


def _command_record_lock(argument: str, root: Path, lock_dir: Path) -> int:
    for dataset_id in _targets(argument):
        path = write_lock(dataset_id, root=root, lock_dir=lock_dir)
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(
            f"{dataset_id}: 已记 lock {path}"
            f"（revision={payload['revision']}，覆盖 {payload['file_count']} 个文件）"
        )
    return 0


def _upstream_notes(dataset_id: str, root: Path) -> list[str]:
    """上游自身不一致的条目（目标不存在 / 行号越界）：打印但不判失败。"""

    base = dataset_dir(dataset_id, root)
    if not _is_fetched(base):
        return []
    try:
        skipped = annotation_report(dataset_id, root=root)["skipped"]
    except CorpusError:
        return []
    return [
        f"{dataset_id}: 上游自身不一致（已丢弃并计数，不是本次语料漂移，也不是解析失败）："
        f"{item.detail}"
        for item in skipped
        if item.reason in (SKIP_TARGET_MISSING, SKIP_TARGET_LINE_OUT_OF_RANGE)
    ]


def _command_verify(root: Path, lock_dir: Path) -> int:
    problems: list[str] = []
    notes: list[str] = []
    for dataset_id in available_datasets():
        ok, found = verify(dataset_id, root=root, lock_dir=lock_dir)
        split = ""
        base = dataset_dir(dataset_id, root)
        if _is_fetched(base):
            report = annotation_report(dataset_id, root=root)
            file_level, line_level = _level_split(report["scopes"])
            split = (
                f"；注解 {report['counts']['annotations']} 条 = 文件级 {file_level} + "
                f"行级 {line_level}"
            )
        if ok:
            print(f"{dataset_id}: ok（lock 与本地语料逐文件 sha256 一致，结构自检通过{split}）")
        else:
            problems.extend(found)
        notes.extend(_upstream_notes(dataset_id, root))
    for note in notes:
        print(f"NOTE {note}")
    for problem in problems:
        print(f"FAIL {problem}")
    if problems:
        print(f"verify 失败：{len(problems)} 个问题（NOTE {len(notes)} 条不参与判定）")
        return 1
    print(f"verify 通过：{len(available_datasets())} 个数据集（NOTE {len(notes)} 条不参与判定）")
    return 0


def _command_annotations(dataset_id: str, root: Path, as_json: bool) -> int:
    report = annotation_report(dataset_id, root=root)
    _print_report(report, as_json)
    if report["self_check_failures"]:
        print(
            f"结构自检失败 {len(report['self_check_failures'])} 条：解析器坏了，"
            "按失败关闭处理（不是上游漂移）",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eval_corpus",
        description="外部第三方行级标注语料：取用 / 记 lock / 校验 / 读成统一注解。",
    )
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--list", action="store_true", help="列出登记的数据集与本地状态")
    actions.add_argument("--fetch", metavar="ID|all", help="取用语料（codeload tarball）")
    actions.add_argument("--record-lock", metavar="ID|all", dest="record_lock", help="记录 lock")
    actions.add_argument("--verify", action="store_true", help="校验 lock 与本地语料")
    actions.add_argument("--annotations", metavar="ID", help="打印注解（配合 --json）")
    parser.add_argument("--json", action="store_true", help="与 --annotations/--list 搭配")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help=f"语料根（默认 {DEFAULT_ROOT}）")
    parser.add_argument(
        "--lock-dir", default=str(DEFAULT_LOCK_DIR), dest="lock_dir",
        help=f"lock 目录（默认 {DEFAULT_LOCK_DIR}）",
    )
    parser.add_argument("--offline", action="store_true", help="禁止联网：缺语料就报错")
    args = parser.parse_args(argv)
    root = Path(args.root)
    lock_dir = Path(args.lock_dir)
    try:
        if args.list:
            return _command_list(root, lock_dir)
        if args.fetch:
            return _command_fetch(args.fetch, root, args.offline)
        if args.record_lock:
            return _command_record_lock(args.record_lock, root, lock_dir)
        if args.verify:
            return _command_verify(root, lock_dir)
        return _command_annotations(args.annotations, root, args.json)
    except CorpusError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


_register_self = sys.modules.setdefault  # 别名只为让下面一行读起来短一点
_register_self("eval_corpus", sys.modules[__name__])
_load_extra()
_validate_registry()


if __name__ == "__main__":
    raise SystemExit(main())

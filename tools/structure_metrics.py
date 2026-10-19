r"""A 维度结构谓词（A1–A10）的只读测量器（D 门 2 评分器的 metrics 件）。

它是什么
========

§4.2（docs/project/engineering-policy-platform/readings/2026-10-19-D-gate2-treatment.md）定义了
A 维度 10 条结构谓词（分层方向 / 无环 / 公开符号面 / 组合根唯一 / 复杂度 / 长度 /
docstring / 扇出 / 测试对应 / 无动态执行），每条都要能对**最终树**给出 pass/fail 与证据。
§4.2 的结论是：A9 现有读数够、A1 靠现有证据加脚本判方向、其余 8 条需要一个新的只读脚本
（建议 tools/structure_metrics.py）。本文件就是那个脚本。

判据原文在 §4.2，本文实现的是它的**可执行口径**；每一处与草案的差异、以及"哪些只能人工判"
（§4.5），都写在对应谓词的 detail["note"] 里，读输出的人不必回头翻文档。

它不是什么（读之前先看这四条）
==============================

1. **不是判定器**：只产证据，不改任何 allow / block（与验证器层同一条纪律）。A 维度的分数由
   评分器算，本工具只回答"这条谓词在这棵树上过不过、为什么"。
2. **不写工作区**：只读源码与两个声明文件；唯一的写入口是显式 --out。
3. **不 import 被测代码**：只 ast.parse（复用 validators.python_ast 与 validators.depgraph 的
   既有事实与解析口径，不另写一套 AST 遍历）。
4. **不联网、不跑子进程**：没有 pytest / ruff / mypy；所以 A9 是"静态 import 边"而不是
   PipelineReport.selection（该差异在 A9 的 note 里明写，属于已知的口径缺口）。

载荷自己的版本轴（AGENTS 第 55 条）
=================================

STRUCTURE_METRICS_SCHEMA_VERSION = "1.1"：
- **1.0 = 首次建轴**（2026-10-19，A 维度测量器落地）：顶层 schema_version / workspace_scope /
  predicates / summary，每条谓词为 {id, name, status, detail}；
- **1.1 = A4 口径修订**（2026-10-19 Lead 裁定）：__init__ 内的默认装配（x or ConcreteX()）不再算
  违规（本题接口契约要求构造器默认参数，见 _is_constructor 的注释）；A4 的 items 条目多
  `enclosing`（调用点所在函数）与 `reason`，counts 多 `default_wiring_instantiations`——
  键集合与判定语义同时变了，因此按 AGENTS 第 55 条**显式升版**（不做"同一版本号底下两种形状"）。
加键或改语义必须按本条显式递增，并同批改掉写死版本号的引用点
（tools/README.md、AGENTS.md 第 55 条那张表、tests/unit/test_structure_metrics.py）。

**载荷里没有时戳、没有 run 标识、没有绝对路径、没有耗时**：它是输入的纯函数，同样的输入两次
运行**逐字节相同**（AGENTS 第 19 条；与 policy.check.OUTPUT_SCHEMA_VERSION 的"包装层不带 run"
同一条纪律）。所有对象键按字典序输出（json.dumps(sort_keys=True)），列表按
（仓库相对路径, 行号, 整条 JSON）排序——排序不依赖文件系统遍历顺序。

CLI 与退出码
============

    python tools/structure_metrics.py --workspace <dir> --layers <yaml> [--json]
                                      [--out PATH] [--interfaces <yaml>] [--limit N]

    --workspace    被测树根（必填）。载荷里所有路径都相对于它，根写作 "."。
    --layers       「仓库相对 POSIX 路径 → layer 字符串」的映射文件（必填）。形态有三种：
                   精确文件路径、以 "/" 结尾的目录前缀、含 "*"/"?" 的 glob（语义 =
                   validators.globs.glob_match："**/" 表示零个或多个目录）。同一条路径命中多条时
                   取**最具体**的一条（精确 > 字面前缀更长 > 模式更长 > 字典序），规则写死、
                   不依赖 YAML 里的书写顺序。
    --interfaces   A3 的「声明接口数」：仓库相对路径 → 该模块允许的公开定义上限（整数）。
                   不给时 A3 退到 __all__ 声明口径（见 A3 的 note，两种口径都是显式的）。
    --json         打印机器载荷（stdout 只有它，别的什么都不打）。
    --out PATH     把机器载荷写成文件（UTF-8 + LF + 单尾换行，与 --json 的字节完全相同）；
                   父目录不存在时创建。
    --limit N      人类输出里每条谓词最多列几条超阈值项（默认 5；不影响 --json / --out）。

    退出码：**0 = 10 条全 pass；1 = 有谓词 fail；2 = 用法 / 输入 / 声明错误**
    （工作区不是目录、YAML 读不了、层值不在闭集里、路径不是仓库相对、没有可测对象、
    索引被截断）。与 tools/README.md 的「门禁退出码」表一致：**它不是恒 0 的只报告工具**。

测量范围（scope）怎么定
======================

范围 = --workspace 下**所有 .py 文件**（跳过 validators.depgraph.SKIP_DIRS 与以 "." 开头的
目录），范围由 build_module_index 的索引反向得到——**只有一次文件系统遍历**，范围与依赖解析
看到的文件集因此必然一致。--layers 的每个文件仍然必须被声明：

- 声明成 skip = **显式**移出测量范围（例如仓库自身跑时把 tests/fixtures/ 排除掉）；
- 一个都没声明 = workspace_scope.undeclared 里列出来，且 **A1 判 fail**（"路径族声明 100%"
  是干跑四数之一，未声明的文件不能让分层方向变成"没查过也绿"）；
- 声明了却一个文件都没命中（精确路径不存在、目录 / glob 一个都没覆盖）=
  workspace_scope.unmatched_entries（证据，不判 fail）；声明指向非 .py 文件（§4.0 的
  layers.yaml 就带着 README.md）= workspace_scope.non_python_entries。

层的闭集（LAYER_VALUES）
========================

composition（组合根 / main / demo）、controller、service、repository、model、test、
other（**生产代码但没有分层角色**）、skip（声明了但不在测量范围）。未知层值 = 加载期报错
（退出 2），不静默当成 other——other 是显式声明。

失败关闭（与验证器层同一条纪律）
==============================

- **解析失败不等于没有依赖**：范围内任一文件语法错误 / 不是 UTF-8 时，10 条谓词**全部 fail**，
  每条 detail 带 blocked_by: "unmeasurable_files" 与那份清单——解析不了的文件无法为任何谓词作证；
- **依赖图不完整就不许判无环 / 扇出 / 方向**：depgraph 的 unresolved（动态 import 目标不是
  常量、"看起来是项目内模块却不存在"、相对导入越界）会让 A1 / A2 / A8 fail，并附 unresolved 清单；
- **没声明就不许绿**：A3 没有上限声明也没有 __all__、A1 有未声明层的端点，都判 fail；
- **读不到就是读不到**：--layers / --interfaces 读不出来是用法错误（退出 2），不降级成
  "没有声明"。

已知边界（写下来，免得后来者以为是覆盖）
====================================

1. **模块解析根固定为 (".", "src")**（与 validation/project.yaml 的顺序一致）：其它布局
   （lib/ 之类）的顶层 import 会被解析成外部包，那条边**不出现**在 A1 / A2 / A8 里；这是
   "可能漏、不误报"的缺口，不是静默通过——顶层包存在而模块找不到时 depgraph 会记 unresolved，
   A1 / A2 / A8 因此 fail。
2. **A9 不是 PipelineReport.selection 的等价物**：它只认静态 import 边（测试文件 import 到
   生产文件，以及"被 import 的子模块会连带 import 其包的 __init__.py"这条 Python 语义），
   不跑 pytest、不读 validation/test-layout.yaml。
3. **A4 只判"业务方法里的跨模块 new 具象协作者"**：`__init__` 内的默认装配
   （`x or ConcreteX()` / 条件回退）不计违规——本任务的接口契约要求
   `OrderService(repository=None, audit=None)` 这类构造器默认参数语义（Lead 2026-10-19 裁定，
   见 `_is_constructor` 的注释与 A4 的 note）；同一文件内的实例化不算装配；目标类名在范围内
   不唯一（多处同名）时记 ambiguous_class_names，不判违规（可能漏、不误报）。
4. **A5 的判定节点就是 §4.2 列的那七类**（if / for / while / and / or / except / with）：
   三元表达式（IfExp）与推导式里的 if **没有**计入——把它们加上只会更严，不改变方向。
5. **A6 的行数就是物理行**（含 docstring 与空行；函数 = end_lineno - lineno + 1，不含装饰器）。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple


def _bootstrap() -> Path:
    """把仓库的 src/ 放进 sys.path，并返回仓库根。

    为什么不能只写 Path(__file__).resolve().parents[1]：评分器冻结时这个脚本会被**复制**到
    scorer/metrics/structure_metrics.py（§4.0 的冻结包清单），那时 parents[1] 是 scorer/，
    import validators 会直接失败。所以向上回溯，找到第一个含 src/validators/python_ast.py 的
    目录；冻结包落在仓库里时这就是仓库根，找不到时退回本文件的 parents[1]（部署在仓库外时的
    行为由调用方的 PYTHONPATH 决定）。
    """

    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "src" / "validators" / "python_ast.py").is_file():
            return candidate
    return here.parents[1] if len(here.parents) > 1 else here.parent


REPO_ROOT = _bootstrap()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import yaml  # noqa: E402  （路径注入之后才能 import；与仓库其它 tools 同一写法）

    from provenance import reading_context as reading  # noqa: E402
    from validators import python_ast  # noqa: E402
    from validators.depgraph import build_dependencies, build_module_index  # noqa: E402
    from validators.globs import glob_match  # noqa: E402
    from validators.models import ProjectProfile  # noqa: E402
except ImportError as error:  # pragma: no cover - 只有依赖缺失时才走到
    sys.stderr.write(
        "structure_metrics: 依赖不可用（%s）；请在本仓库内运行，或用 PYTHONPATH=src 运行\n" % error
    )
    raise SystemExit(2)

__all__ = ["STRUCTURE_METRICS_SCHEMA_VERSION", "main", "measure", "render_human", "run"]

# 本载荷的版本轴（AGENTS 第 55 条）：1.0 = 首次建轴；1.1 = A4 口径修订（__init__ 默认装配豁免 +
# A4 items 多 enclosing / reason、counts 多 default_wiring_instantiations）。键集合或语义变一次就升一次。
STRUCTURE_METRICS_SCHEMA_VERSION = "1.1"

#: 与 validation/project.yaml 的 python_roots 同序同口径（见模块 docstring 的边界 1）。
PYTHON_ROOTS: Tuple[str, ...] = (".", "src")
PROFILE_SCHEMA_ID = "structure-metrics/1"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

#: 层的闭集。other = 显式声明的"生产代码、无分层角色"；skip = 显式移出测量范围。
LAYER_COMPOSITION = "composition"
LAYER_CONTROLLER = "controller"
LAYER_SERVICE = "service"
LAYER_REPOSITORY = "repository"
LAYER_MODEL = "model"
LAYER_TEST = "test"
LAYER_OTHER = "other"
LAYER_SKIP = "skip"
LAYER_VALUES: Tuple[str, ...] = (
    LAYER_COMPOSITION,
    LAYER_CONTROLLER,
    LAYER_SERVICE,
    LAYER_REPOSITORY,
    LAYER_MODEL,
    LAYER_TEST,
    LAYER_OTHER,
    LAYER_SKIP,
)

#: A1 的白名单（§4.2："只允许 controller→service、service→repository、任意→model"）。
ALLOWED_EDGES = frozenset({(LAYER_CONTROLLER, LAYER_SERVICE), (LAYER_SERVICE, LAYER_REPOSITORY)})
#: A4：只有这些层的具象类算"协作者"，生产模块 new 它们才是违规。
INSTANTIATION_TARGET_LAYERS = frozenset({LAYER_REPOSITORY, LAYER_SERVICE, LAYER_CONTROLLER})
#: A4：组合根与测试可以实例化任何东西（组合根本来就是干这个的）。
INSTANTIATION_FREE_LAYERS = frozenset({LAYER_COMPOSITION, LAYER_TEST})
#: A3 不约束测试模块：pytest 的"公开面"是 test_ 函数，不是被导出的 API。
A3_SKIP_LAYERS = frozenset({LAYER_TEST})

MAX_COMPLEXITY = 10
MAX_FILE_LINES = 200
MAX_FUNCTION_LINES = 50
MAX_FAN_OUT = 5
#: 每条谓词最多记多少条超阈值项进载荷（计数永远是全量；这一项只是载荷大小的上限）。
MAX_ITEMS = 100

STATUS_PASS = "pass"
STATUS_FAIL = "fail"

#: 声明文件读不出指纹时的占位（digest 一律 "sha256:..."，读不到写这个而不是编一个值）。
DIGEST_UNAVAILABLE = "unavailable"

_A_DRIVE = re.compile(r"^[A-Za-z]:")


class StructureMetricsError(Exception):
    """用法 / 输入 / 声明错误：退出码 2（与"谓词 fail"的 1 分开，CI 才读得出"查了没有"）。"""


# --------------------------------------------------------------------------- 声明文件


def _show(path: Path, root: Path) -> str:
    """错误信息里的路径：仓库相对；工作区之外写 <outside-workspace>/<名字>。

    载荷里的路径一律走 reading.display_path（AGENTS 第 19 条：不放绝对路径）；这里多保留一个
    文件名，好让"读不到 --layers"这条错误对人有意义。错误信息不是证据，但仍然不写绝对路径。
    """

    text = reading.display_path(path, root=root)
    if text != reading.OUTSIDE_WORKSPACE:
        return text
    return "%s/%s" % (reading.OUTSIDE_WORKSPACE, Path(path).name)


def _load_mapping(path: Path, root: Path, flag: str) -> Mapping[Any, Any]:
    """读一份「键 → 值」的 YAML 声明；读不出来一律是用法错误（退出 2），不降级成"没有声明"。"""

    if not path.is_file():
        raise StructureMetricsError("%s 文件不存在：%s" % (flag, _show(path, root)))
    try:
        data = path.read_bytes()
    except OSError as error:
        raise StructureMetricsError(
            "%s 读不出来：%s（%s）" % (flag, _show(path, root), type(error).__name__)
        ) from error
    try:
        loaded = yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise StructureMetricsError(
            "%s 不是合法的 UTF-8 YAML：%s（%s）" % (flag, _show(path, root), type(error).__name__)
        ) from error
    if not isinstance(loaded, Mapping):
        raise StructureMetricsError(
            "%s 顶层必须是映射，实际是 %s" % (flag, type(loaded).__name__)
        )
    return loaded


def _declared_path(value: Any, flag: str, *, key: Any) -> str:
    """声明里的路径必须是**仓库相对 POSIX 路径**（绝对路径、反斜杠、".."、"." 一律拒绝）。"""

    if not isinstance(value, str):
        raise StructureMetricsError(
            "%s 里 %r 的键必须是字符串路径，实际是 %s" % (flag, key, type(value).__name__)
        )
    text = value
    if not text or text.strip() != text:
        raise StructureMetricsError("%s 里有一条例空了或带首尾空白的路径声明：%r" % (flag, value))
    if "\\" in text:
        raise StructureMetricsError(
            "%s 的路径必须用 / 分隔（POSIX）：%r" % (flag, text)
        )
    if text.startswith("/") or _A_DRIVE.match(text) or text.startswith("//"):
        raise StructureMetricsError(
            "%s 的路径必须是仓库相对路径（不接受绝对路径）：%r" % (flag, text)
        )
    parts = text.split("/")
    if ".." in parts or "." in parts:
        raise StructureMetricsError(
            "%s 的路径里不许出现 . 或 .. 段：%r（在文件里写成相对仓库根的样子）" % (flag, text)
        )
    return text


def _layer_value(value: Any, key: Any) -> str:
    """层值必须落在闭集里：未知值报错，不静默当成 other。"""

    if not isinstance(value, str) or value not in LAYER_VALUES:
        raise StructureMetricsError(
            "--layers 里 %r 的层值是 %r，不在闭集里；可用值：%s（生产代码但没有"
            "分层角色写 other，移出测量范围写 skip）"
            % (key, value, ", ".join(LAYER_VALUES))
        )
    return value


def _literal_prefix(pattern: str) -> int:
    """glob 的字面前缀长度：越长的前缀 = 越具体的声明（排序键之一）。"""

    positions = [pattern.find(char) for char in ("*", "?") if char in pattern]
    return min(positions) if positions else len(pattern)


def _pattern_matches(pattern: str, path: str) -> bool:
    """目录前缀形态按前缀匹配，glob 形态走 validators.globs（语义只有一份）。"""

    if pattern.endswith("/"):
        return path.startswith(pattern)
    return glob_match(pattern, path)


@dataclass(frozen=True)
class LayerTable:
    """「仓库相对路径 → layer」的声明。

    三种形态：精确文件路径、以 "/" 结尾的目录前缀、含 "*"/"?" 的 glob。命中多条时取最具体的
    一条——排序键 (-字面前缀长度, -模式长度, 模式) 升序，**规则写死、不依赖 YAML 书写顺序**
    （否则同一个声明换个顺序就能得到另一个读数）。
    """

    entries: Tuple[Tuple[str, str], ...]
    exact: Mapping[str, str]
    patterns: Tuple[Tuple[str, str], ...]
    path: str
    digest: str

    def layer_for(self, path: str) -> Optional[str]:
        """这条仓库相对路径的层；没有声明返回 None（调用方决定 fail 还是只记证据）。"""

        exact = self.exact.get(path)
        if exact is not None:
            return exact
        for pattern, layer in self.patterns:
            if _pattern_matches(pattern, path):
                return layer
        return None


def load_layers(path: Path, root: Path) -> LayerTable:
    """读 --layers：形态、层值闭集与路径形态都在加载期校验（未知一律报错）。"""

    loaded = _load_mapping(path, root, "--layers")
    entries: list[Tuple[str, str]] = []
    exact: dict[str, str] = {}
    patterns: list[Tuple[str, str]] = []
    for key, value in loaded.items():
        pattern = _declared_path(key, "--layers", key=key)
        layer = _layer_value(value, key)
        entries.append((pattern, layer))
        if pattern.endswith("/") or "*" in pattern or "?" in pattern:
            patterns.append((pattern, layer))
        else:
            exact[pattern] = layer
    patterns.sort(key=lambda item: (-_literal_prefix(item[0]), -len(item[0]), item[0]))
    return LayerTable(
        entries=tuple(sorted(entries)),
        exact=exact,
        patterns=tuple(patterns),
        path=reading.display_path(path, root=root),
        digest=reading.declaration_digest(path) or DIGEST_UNAVAILABLE,
    )


@dataclass(frozen=True)
class InterfaceCaps:
    """A3 的「声明接口数」：仓库相对路径 → 该模块允许的公开定义上限（整数）。"""

    caps: Mapping[str, int]
    path: str
    digest: str

    def cap_for(self, path: str) -> Optional[int]:
        """这个模块声明的公开定义上限；没声明返回 None（调用方判 fail，不默默放行）。"""

        return self.caps.get(path)


def load_caps(path: Path, root: Path) -> InterfaceCaps:
    """读 --interfaces：键必须是精确的仓库相对路径，值必须是 >= 0 的整数。"""

    loaded = _load_mapping(path, root, "--interfaces")
    caps: dict[str, int] = {}
    for key, value in loaded.items():
        declared = _declared_path(key, "--interfaces", key=key)
        if declared.endswith("/") or "*" in declared or "?" in declared:
            raise StructureMetricsError(
                "--interfaces 只接受精确的仓库相对路径，不接受目录 / glob：%r" % declared
            )
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise StructureMetricsError(
                "--interfaces 里 %r 的上限必须是 >= 0 的整数，实际是 %r" % (declared, value)
            )
        caps[declared] = value
    return InterfaceCaps(
        caps=caps,
        path=reading.display_path(path, root=root),
        digest=reading.declaration_digest(path) or DIGEST_UNAVAILABLE,
    )


# --------------------------------------------------------------------------- 范围与事实


@dataclass(frozen=True)
class SourceFile:
    """范围内的一个 Python 文件：源码、静态事实与不可测原因（失败关闭用）。"""

    path: str
    text: str
    digest: str
    facts: Optional[python_ast.ModuleFacts]
    tree: Optional[ast.AST]
    error: Optional[Mapping[str, Any]]

    @property
    def ok(self) -> bool:
        """这个文件能不能为谓词作证。"""

        return self.error is None


@dataclass(frozen=True)
class Context:
    """一次测量的全部事实：范围、层、依赖边、不可解析项与声明覆盖。"""

    workspace: Path
    layers: LayerTable
    caps: Optional[InterfaceCaps]
    sources: Tuple[SourceFile, ...]
    layer_of: Mapping[str, Optional[str]]
    edges: Tuple[Tuple[str, str], ...]
    unresolved: Tuple[Mapping[str, Any], ...]
    undeclared: Tuple[str, ...]
    skipped: Tuple[str, ...]
    unmeasurable: Tuple[Mapping[str, Any], ...]
    unmatched_entries: Tuple[str, ...]
    non_python_entries: Tuple[str, ...]
    files_digest: str

    @property
    def paths(self) -> Tuple[str, ...]:
        """范围内全部 .py 文件（仓库相对路径，已排序）。"""

        return tuple(source.path for source in self.sources)

    def layer(self, path: str) -> Optional[str]:
        """这条路径声明的层（None = 未声明）。"""

        return self.layer_of.get(path)

    @property
    def measured(self) -> Tuple[Tuple[str, ...], Tuple[SourceFile, ...]]:
        """参与测量的文件与事实（= 全部 - skip）。"""

        pairs = [
            (source.path, source)
            for source in self.sources
            if self.layer(source.path) != LAYER_SKIP
        ]
        return tuple(path for path, _ in pairs), tuple(source for _, source in pairs)


_NON_INTERNAL_PREFIXES = ("call:", "external:", "unresolved:")


def _project_profile() -> ProjectProfile:
    """只声明解析根：层由 --layers 给，绝不从文件名 / 组件映射推（AGENTS 核心约束 6）。"""

    return ProjectProfile(version=1, schema_id=PROFILE_SCHEMA_ID, python_roots=PYTHON_ROOTS)


def _read_source(root: Path, relative: str) -> SourceFile:
    """读一个文件并算静态事实；不可测（解码 / 语法错误）作为**事实**返回，由谓词统一失败关闭。"""

    try:
        data = (root / relative).read_bytes()
    except OSError as error:
        raise StructureMetricsError(
            "读不到 %s（%s）；不允许部分读数" % (relative, type(error).__name__)
        ) from error
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return SourceFile(
            path=relative,
            text="",
            digest=digest,
            facts=None,
            tree=None,
            error={"reason": "decode_error"},
        )
    with warnings.catch_warnings():
        # 解析期的 SyntaxWarning（例如正则字面量里的 "\s"）是**被解析文件**的属性，不是本工具
        # 的读数；放出去会让 stderr 随解释器版本变化，而 --json 的契约是逐字节稳定。
        warnings.simplefilter("ignore")
        facts = python_ast.parse_module(text)
    if not facts.ok:
        issue = facts.syntax_error
        return SourceFile(
            path=relative,
            text=text,
            digest=digest,
            facts=None,
            tree=None,
            error={
                "reason": "syntax_error",
                "line": None if issue is None else issue.line,
                "message": ""
                if issue is None
                else reading.fold_absolute_paths(issue.message, root=root),
            },
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    except SyntaxError:  # pragma: no cover - parse_module 已经证明可解析，这里只是防口径漂移
        return SourceFile(
            path=relative,
            text=text,
            digest=digest,
            facts=None,
            tree=None,
            error={"reason": "syntax_error", "line": None, "message": "两次解析结论不一致"},
        )
    return SourceFile(path=relative, text=text, digest=digest, facts=facts, tree=tree, error=None)


def _declaration_reach(
    layers: LayerTable, workspace: Path, paths: Sequence[str]
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """声明覆盖：声明了却没命中任何文件 / 声明指向非 .py 文件（两者都是证据，不判 fail）。"""

    known = set(paths)
    unmatched: list[str] = []
    non_python: list[str] = []
    for pattern, _layer in layers.entries:
        if pattern.endswith("/") or "*" in pattern or "?" in pattern:
            if not any(_pattern_matches(pattern, path) for path in paths):
                unmatched.append(pattern)
            continue
        if pattern in known:
            continue
        if (workspace / pattern).is_file():
            non_python.append(pattern)
        else:
            unmatched.append(pattern)
    return tuple(sorted(unmatched)), tuple(sorted(non_python))


def _files_digest(sources: Sequence[SourceFile]) -> str:
    """参与测量的文件集合的指纹：覆盖「相对路径 + 文件 sha256」，不读文件系统顺序。"""

    lines = sorted("%s %s" % (source.path, source.digest) for source in sources)
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def build_context(workspace: Path, layers: LayerTable, caps: Optional[InterfaceCaps]) -> Context:
    """读范围、读声明、算依赖边；全部失败在这里变成退出码 2，不产生"部分读数"。"""

    profile = _project_profile()
    index = build_module_index(workspace, profile)
    if index.truncated:
        raise StructureMetricsError(
            "索引在文件数上限处被截断：这棵树太大，无法完整测量（不做部分读数）"
        )
    paths = tuple(sorted(set(index.modules.values())))
    if not paths:
        raise StructureMetricsError("--workspace 下没有 .py 文件（被测对象为空，测量不适用）")
    sources = tuple(_read_source(workspace, relative) for relative in paths)
    layer_of: dict[str, Optional[str]] = {
        source.path: layers.layer_for(source.path) for source in sources
    }

    edges: set[Tuple[str, str]] = set()
    unresolved: list[Mapping[str, Any]] = []
    for source in sources:
        if source.facts is None:
            continue
        result = build_dependencies(
            source.facts,
            target_path=source.path,
            profile=profile,
            index=index,
            validator="structure_metrics",
        )
        for edge in result.edges:
            if not edge.target.startswith(_NON_INTERNAL_PREFIXES):
                edges.add((source.path, edge.target))
        if layer_of.get(source.path) == LAYER_SKIP:
            continue
        for item in result.unresolved:
            unresolved.append(
                {
                    "path": source.path,
                    "module": item.module,
                    "kind": item.kind,
                    "line": item.line,
                    "reason": reading.fold_absolute_paths(item.reason, root=workspace),
                }
            )

    measured_sources = tuple(
        source for source in sources if layer_of.get(source.path) != LAYER_SKIP
    )
    unmatched, non_python = _declaration_reach(layers, workspace, paths)
    return Context(
        workspace=workspace,
        layers=layers,
        caps=caps,
        sources=sources,
        layer_of=layer_of,
        edges=tuple(sorted(edges)),
        unresolved=tuple(sorted(unresolved, key=_unresolved_key)),
        undeclared=tuple(sorted(path for path in paths if layer_of.get(path) is None)),
        skipped=tuple(sorted(path for path in paths if layer_of.get(path) == LAYER_SKIP)),
        unmeasurable=tuple(
            sorted(
                (
                    {"path": source.path, **source.error}
                    for source in sources
                    if source.error is not None and layer_of.get(source.path) != LAYER_SKIP
                ),
                key=lambda item: (str(item.get("path")), int(item.get("line") or 0)),
            )
        ),
        unmatched_entries=unmatched,
        non_python_entries=non_python,
        files_digest=_files_digest(measured_sources),
    )


def _unresolved_key(item: Mapping[str, Any]) -> Tuple[str, int, str]:
    return (str(item.get("path")), int(item.get("line") or 0), str(item.get("module")))


# --------------------------------------------------------------------------- 谓词


def _sort_items(items: Sequence[Mapping[str, Any]]) -> list[dict]:
    """超阈值项按（路径, 行号, 整条 JSON）排序：确定性不依赖遍历顺序。"""

    return [
        dict(item)
        for item in sorted(
            items,
            key=lambda item: (
                str(item.get("path", "")),
                int(item.get("line") or 0),
                json.dumps(item, ensure_ascii=False, sort_keys=True),
            ),
        )
    ]


def _detail(
    counts: Mapping[str, int], items: Sequence[Mapping[str, Any]], note: str, **extra: Any
) -> dict:
    """一条谓词的证据摘要：计数（全量）+ 超阈值项（上限 MAX_ITEMS）+ 口径说明。"""

    ordered = _sort_items(items)
    detail: dict = {
        "counts": dict(counts),
        "items": ordered[:MAX_ITEMS],
        "items_truncated": len(ordered) > MAX_ITEMS,
        "note": note,
    }
    detail.update(extra)
    return detail


def predicate_a1(ctx: Context) -> Tuple[bool, dict]:
    """A1 分层方向：项目内依赖边只允许 §4.2 白名单的方向。"""

    items: list[Mapping[str, Any]] = []
    counts = {
        "edges_internal": 0,
        "violations": 0,
        "not_judged": 0,
        "skipped_endpoints": 0,
        "unresolved": len(ctx.unresolved),
    }
    for source, target in ctx.edges:
        source_layer = ctx.layer(source)
        target_layer = ctx.layer(target)
        if source_layer == LAYER_SKIP or target_layer == LAYER_SKIP:
            counts["skipped_endpoints"] += 1
            continue
        counts["edges_internal"] += 1
        if source_layer is None or target_layer is None:
            counts["violations"] += 1
            items.append(
                {
                    "rule": "undeclared_layer",
                    "source": source,
                    "target": target,
                    "source_layer": source_layer,
                    "target_layer": target_layer,
                }
            )
            continue
        if target_layer == LAYER_TEST and source_layer != LAYER_TEST:
            counts["violations"] += 1
            items.append(
                {
                    "rule": "production_to_test",
                    "source": source,
                    "target": target,
                    "source_layer": source_layer,
                    "target_layer": target_layer,
                }
            )
            continue
        if source_layer == LAYER_TEST:
            continue
        if source_layer == LAYER_OTHER or target_layer == LAYER_OTHER:
            counts["not_judged"] += 1
            continue
        if target_layer == LAYER_MODEL or source_layer == LAYER_COMPOSITION:
            continue
        if (source_layer, target_layer) in ALLOWED_EDGES:
            continue
        counts["violations"] += 1
        items.append(
            {
                "rule": "forbidden_direction",
                "source": source,
                "target": target,
                "source_layer": source_layer,
                "target_layer": target_layer,
            }
        )
    note = (
        "只判两端都声明了层的项目内边；白名单 = controller→service、service→repository、"
        "任意→model、test→任意、composition→任意（composition→test 除外），"
        "生产→test 一律违规。other（未分层生产代码）的**方向**不判并显式记 not_judged，"
        "但它参与的生产→test 仍判。未声明层的端点判 fail（路径族声明 100% 是干跑四数之一）；"
        "unresolved（依赖图不完整）同样判 fail——看不到的边不能当成「没有违规」。"
    )
    ok = counts["violations"] == 0 and not ctx.unresolved
    return ok, _detail(counts, items, note, unresolved=[dict(item) for item in ctx.unresolved])


def _adjacency(paths: Sequence[str], edges: Sequence[Tuple[str, str]]) -> dict[str, list[str]]:
    """邻接表：每个点的出边按目标排序（Tarjan 的遍历顺序因此也是确定的）。"""

    adjacency: dict[str, list[str]] = {path: [] for path in paths}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)
    for children in adjacency.values():
        children.sort()
    return adjacency


def _strongly_connected(
    nodes: Sequence[str], adjacency: Mapping[str, Sequence[str]]
) -> list[list[str]]:
    """迭代版 Tarjan：强连通分量（每个分量内部按路径排序）。"""

    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0
    for root in nodes:
        if root in index_of:
            continue
        work: list[list[Any]] = [[root, 0]]
        while work:
            frame = work[-1]
            node, position = frame[0], frame[1]
            if position == 0:
                index_of[node] = counter
                low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            children = adjacency.get(node, ())
            advanced = False
            for offset in range(position, len(children)):
                child = children[offset]
                if child not in index_of:
                    frame[1] = offset + 1
                    work.append([child, 0])
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index_of[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(sorted(component))
    return components


def predicate_a2(ctx: Context) -> Tuple[bool, dict]:
    """A2 依赖无环：项目内依赖图的强连通分量里 size>1 或自环即违规。"""

    measured, _sources = ctx.measured
    scope = set(measured)
    edges = [
        (source, target)
        for source, target in ctx.edges
        if source in scope and target in scope
    ]
    adjacency = _adjacency(measured, edges)
    components = _strongly_connected(measured, adjacency)
    cycles = [component for component in components if len(component) > 1]
    cycles.extend([path] for path in measured if path in adjacency.get(path, ()))
    cycles.sort()
    items = [{"cycle": component} for component in cycles]
    counts = {
        "cycles": len(cycles),
        "edges": len(edges),
        "nodes": len(measured),
        "unresolved": len(ctx.unresolved),
        "violations": len(cycles),
    }
    note = (
        "项目内边作图后取 SCC（迭代版 Tarjan，确定性）；SCC size>1 与自环都是环。"
        "unresolved（动态 import 目标不是常量、看起来是项目内模块却不存在、相对导入越界）"
        "让本谓词 fail：依赖图不完整就**无法证明**无环（解析失败不等于没有依赖）。"
    )
    ok = not cycles and not ctx.unresolved
    return ok, _detail(counts, items, note, unresolved=[dict(item) for item in ctx.unresolved])


def _string_sequence(node: ast.AST) -> Optional[frozenset[str]]:
    """字面量字符串序列（List / Tuple / Set 的字符串常量）；不是这种形态返回 None。"""

    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    names: list[str] = []
    for element in node.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        names.append(element.value)
    return frozenset(names)


def _module_all(tree: ast.AST) -> Tuple[Optional[frozenset[str]], bool]:
    """模块级 __all__ 声明的名字集合：返回 (集合, 是否声明过)；声明了但读不出来 -> (None, True)。"""

    exported: Optional[frozenset[str]] = None
    declared = False
    for node in getattr(tree, "body", ()):
        value: Optional[ast.AST] = None
        targets: Sequence[ast.AST] = ()
        if isinstance(node, ast.Assign):
            value = node.value
            targets = tuple(node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            value = node.value
            targets = (node.target,)
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                declared = True
                exported = _string_sequence(value)
    return exported, declared


def predicate_a3(ctx: Context) -> Tuple[bool, dict]:
    """A3 公开符号最小面：每个模块的公开定义不超过声明接口数（或声明的 __all__）。

    两种口径都是**显式**的，写在 detail["basis"] 里：
    - declared_caps（给了 --interfaces）：公开定义数 ≤ 该模块声明的上限；没声明上限的模块判 fail；
    - module_all（没给 --interfaces）：模块级公开定义必须被 __all__ 覆盖；没有 __all__ 判 fail。
    """

    measured, sources = ctx.measured
    items: list[Mapping[str, Any]] = []
    counts = {
        "modules": 0,
        "public_definitions": 0,
        "test_modules_skipped": 0,
        "undeclared_modules": 0,
        "violations": 0,
    }
    basis = "declared_caps" if ctx.caps is not None else "module_all"
    for source in sources:
        facts = source.facts
        if facts is None:
            continue
        if ctx.layer(source.path) in A3_SKIP_LAYERS:
            counts["test_modules_skipped"] += 1
            continue
        public = [fact for fact in facts.definitions if not fact.private]
        counts["modules"] += 1
        counts["public_definitions"] += len(public)
        if ctx.caps is not None:
            cap = ctx.caps.cap_for(source.path)
            if cap is None:
                if not public:
                    continue
                counts["undeclared_modules"] += 1
                counts["violations"] += 1
                items.append(
                    {
                        "path": source.path,
                        "reason": "no_declared_cap",
                        "public_definitions": len(public),
                        "cap": None,
                        "names": sorted(fact.name for fact in public),
                    }
                )
                continue
            if len(public) > cap:
                counts["violations"] += 1
                items.append(
                    {
                        "path": source.path,
                        "reason": "over_cap",
                        "public_definitions": len(public),
                        "cap": cap,
                        "names": sorted(fact.name for fact in public),
                    }
                )
            continue
        module_level = sorted(fact.name for fact in public if "." not in fact.qualified)
        if not module_level:
            continue
        exported, declared = _module_all(source.tree) if source.tree is not None else (None, False)
        if not declared:
            counts["undeclared_modules"] += 1
            counts["violations"] += 1
            items.append(
                {
                    "path": source.path,
                    "reason": "no_all",
                    "public_definitions": len(public),
                    "names": module_level,
                }
            )
            continue
        if exported is None:
            counts["violations"] += 1
            items.append(
                {"path": source.path, "reason": "unreadable_all", "names": module_level}
            )
            continue
        missing = sorted(name for name in module_level if name not in exported)
        if missing:
            counts["violations"] += 1
            items.append(
                {
                    "path": source.path,
                    "reason": "undeclared_export",
                    "public_definitions": len(public),
                    "names": missing,
                }
            )
    note = (
        "公开定义 = DefinitionFact.private=false（§4.2：含方法的类 + 每个方法各算一个）。"
        "测试层不约束（pytest 的公开面是 test_ 函数，不是导出的 API），跳过数记 "
        "test_modules_skipped。declared_caps 口径直接对应 §4.2 的「声明接口数」；"
        "module_all 口径是**替代声明**（模块自己用 __all__ 声明公开面），两者都要求"
        "“没声明就判 fail”，绝不把没声明读成通过。"
    )
    return counts["violations"] == 0, _detail(counts, items, note, basis=basis)


def predicate_a4(ctx: Context) -> Tuple[bool, dict]:
    """A4 组合根唯一：生产层的**业务方法**里不许 new 跨模块的具象协作者。

    口径修订（Lead 2026-10-19 裁定，理由写在 note 里）：`__init__` 内的**默认装配**
    （`x or ConcreteX()` / 条件回退）不计违规——它是本题接口契约要求的构造器默认参数语义，
    baseline 的 sample-project 本身就这么写。composition / test 层继续豁免，同文件内的
    实例化仍不算装配。
    """

    measured, sources = ctx.measured
    class_files: dict[str, list[str]] = {}
    for source in sources:
        if source.facts is None:
            continue
        for fact in source.facts.definitions:
            if fact.kind == "class":
                class_files.setdefault(fact.name, []).append(source.path)
    unique = {
        name: paths[0] for name, paths in class_files.items() if len(paths) == 1
    }
    counts = {
        "ambiguous_class_names": sum(1 for paths in class_files.values() if len(paths) > 1),
        "composition_files": sum(1 for path in measured if ctx.layer(path) == LAYER_COMPOSITION),
        "default_wiring_instantiations": 0,
        "root_instantiations": 0,
        "violations": 0,
    }
    items: list[Mapping[str, Any]] = []
    for source in sources:
        layer = ctx.layer(source.path)
        if layer is None or source.facts is None:
            continue
        functions = list(_iter_functions(source.tree)) if source.tree is not None else []
        for call in source.facts.calls:
            name = call.dotted.rsplit(".", 1)[-1]
            target = unique.get(name)
            if target is None or target == source.path:
                continue
            target_layer = ctx.layer(target)
            if target_layer not in INSTANTIATION_TARGET_LAYERS:
                continue
            if layer in INSTANTIATION_FREE_LAYERS:
                counts["root_instantiations"] += 1
                continue
            enclosing = _enclosing_name(functions, call.line)
            if _is_constructor(enclosing):
                # 构造器默认装配：接口契约要求它存在，不算"生产模块自己装配"。
                counts["default_wiring_instantiations"] += 1
                continue
            counts["violations"] += 1
            items.append(
                {
                    "path": source.path,
                    "line": call.line,
                    "class": name,
                    "class_path": target,
                    "class_layer": target_layer,
                    "enclosing": enclosing,
                    "reason": "concrete_collaborator_in_business_method",
                }
            )
    note = (
        "违规 = 生产层模块（controller / service / repository / model / other）的**业务方法**"
        "（__init__ 以外，含模块体里的工厂函数）里实例化另一个模块定义的 "
        "repository / service / controller 具象类；组合根（composition）与测试层除外，"
        "同一文件内的实例化不算装配（本地工厂不是组合根）。"
        "**__init__ 内的默认装配（x or ConcreteX() / 条件回退）不计违规**（Lead 2026-10-19 裁定）："
        "本题接口契约（interfaces.md）要求 OrderService(repository=None, audit=None) 这类构造器"
        "默认参数语义，baseline 的 sample-project 本身就这么写——按 §4.2 的原始字形算违规会让"
        "任何合法解都失分（A 维度恒有 1 条对所有臂红）；这类实例化只计入 "
        "default_wiring_instantiations 作为证据。"
        "「这一处是否真的是组合根」属 §4.5 的人工项：脚本只回答实例化位置；"
        "目标类名在范围内不唯一时记 ambiguous_class_names、不判违规（可能漏、不误报）。"
        "未声明层的文件不在这里判（A1 已经为它 fail）。"
    )
    return counts["violations"] == 0, _detail(counts, items, note)


def _walk_functions(
    body: Sequence[ast.AST], parents: Tuple[str, ...]
) -> Iterable[Tuple[str, Any]]:
    """递归收集函数：嵌套函数、方法、条件块 / try 块里的定义都算（与 python_ast 同口径）。"""

    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield ".".join((*parents, node.name)), node
            yield from _walk_functions(node.body, (*parents, node.name))
            continue
        if isinstance(node, ast.ClassDef):
            yield from _walk_functions(node.body, (*parents, node.name))
            continue
        nested = getattr(node, "body", None)
        if isinstance(nested, list):
            yield from _walk_functions(nested, parents)


def _iter_functions(tree: ast.AST) -> Iterable[Tuple[str, Any]]:
    """按源码顺序产 (限定名, 函数节点)。"""

    return _walk_functions(getattr(tree, "body", ()), ())


def _enclosing_name(functions: Sequence[Tuple[str, Any]], line: int) -> Optional[str]:
    """调用点所在的**最内层**函数限定名；在模块体 / 类体里调用时返回 None。"""

    best: Optional[Tuple[int, str]] = None
    for qualified, node in functions:
        start = int(getattr(node, "lineno", 0))
        end = int(getattr(node, "end_lineno", start))
        if start <= line <= end and (best is None or start >= best[0]):
            best = (start, qualified)
    return None if best is None else best[1]


def _is_constructor(qualified: Optional[str]) -> bool:
    """限定名的最后一段是不是 __init__（A4 的默认装配豁免靠它）。

    为什么 A4 要豁免它：本任务的接口契约（interfaces.md）要求
    OrderService(repository=None, audit=None) 这类**构造器默认装配**，baseline 的 sample-project
    本身就写成 `x or ConcreteX()`。照 §4.2 的原始字形把默认装配算成"生产模块 new 具象协作者"，
    会让任何合法解都在 A4 上失分（A 维度恒有 1 条对所有臂红，区分力为 0）——所以这是一次
    **显式的口径修订**，理由与范围写在 A4 的 detail["note"] 里（Lead 2026-10-19 裁定）。
    """

    return qualified is not None and qualified.rsplit(".", 1)[-1] == "__init__"


_DECISION_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
)


def _complexity(node: Any) -> int:
    """圈复杂度 = 1 + 判定节点数（判定节点 = §4.2 列的七类；and / or 按操作数各 +1）。"""

    score = 1
    pending = list(getattr(node, "body", ()))
    while pending:
        current = pending.pop()
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue  # 嵌套函数归它自己算
        if isinstance(current, _DECISION_NODES):
            score += 1
        elif isinstance(current, ast.BoolOp):
            score += max(0, len(current.values) - 1)
        pending.extend(ast.iter_child_nodes(current))
    return score


def predicate_a5(ctx: Context) -> Tuple[bool, dict]:
    """A5 函数复杂度：每个函数的圈复杂度 ≤ 10。"""

    _measured, sources = ctx.measured
    items: list[Mapping[str, Any]] = []
    counts = {"functions": 0, "over_threshold": 0, "violations": 0}
    for source in sources:
        if source.tree is None:
            continue
        for qualified, node in _iter_functions(source.tree):
            complexity = _complexity(node)
            counts["functions"] += 1
            if complexity > MAX_COMPLEXITY:
                counts["over_threshold"] += 1
                counts["violations"] += 1
                items.append(
                    {
                        "path": source.path,
                        "line": node.lineno,
                        "qualified": qualified,
                        "complexity": complexity,
                    }
                )
    note = (
        "圈复杂度 = 1 + 判定节点数；判定节点就是 §4.2 列的那七类（if / for / async for / "
        "while / except / with / async with）加 and / or 的额外操作数。阈值 %d，超过即 fail。"
        "三元表达式（IfExp）与推导式里的 if **没有**计入（把它们加上只会更严）。"
        % MAX_COMPLEXITY
    )
    return counts["violations"] == 0, _detail(counts, items, note)


def predicate_a6(ctx: Context) -> Tuple[bool, dict]:
    """A6 文件 / 函数长度：文件 ≤ 200 行，单函数 ≤ 50 行。"""

    _measured, sources = ctx.measured
    items: list[Mapping[str, Any]] = []
    counts = {
        "files": 0,
        "functions": 0,
        "over_length_files": 0,
        "over_length_functions": 0,
        "violations": 0,
    }
    for source in sources:
        if source.tree is None:
            continue
        lines = len(source.text.splitlines())
        counts["files"] += 1
        if lines > MAX_FILE_LINES:
            counts["over_length_files"] += 1
            items.append({"path": source.path, "kind": "file", "lines": lines})
        for qualified, node in _iter_functions(source.tree):
            length = int(getattr(node, "end_lineno", node.lineno)) - node.lineno + 1
            counts["functions"] += 1
            if length > MAX_FUNCTION_LINES:
                counts["over_length_functions"] += 1
                items.append(
                    {
                        "path": source.path,
                        "kind": "function",
                        "qualified": qualified,
                        "line": node.lineno,
                        "lines": length,
                    }
                )
    counts["violations"] = counts["over_length_files"] + counts["over_length_functions"]
    note = (
        "行数是物理行（含 docstring 与空行）；函数长度 = end_lineno - lineno + 1（不含装饰器）。"
        "阈值：文件 %d 行、单函数 %d 行，超过即 fail。" % (MAX_FILE_LINES, MAX_FUNCTION_LINES)
    )
    return counts["violations"] == 0, _detail(counts, items, note)


def predicate_a7(ctx: Context) -> Tuple[bool, dict]:
    """A7 docstring 覆盖：模块 + 全部公开定义都有 docstring。"""

    _measured, sources = ctx.measured
    items: list[Mapping[str, Any]] = []
    counts = {"files": 0, "definitions": 0, "missing": 0, "violations": 0}
    for source in sources:
        facts = source.facts
        if facts is None:
            continue
        counts["files"] += 1
        if not facts.module_docstring:
            counts["missing"] += 1
            items.append(
                {"path": source.path, "kind": "module", "line": 1, "qualified": "<module>"}
            )
        for fact in facts.definitions:
            counts["definitions"] += 1
            if fact.private or fact.docstring:
                continue
            counts["missing"] += 1
            items.append(
                {
                    "path": source.path,
                    "kind": fact.kind,
                    "line": fact.line,
                    "qualified": fact.qualified,
                }
            )
    counts["violations"] = counts["missing"]
    note = (
        "与 DOC-001 同源但更严：**模块级** docstring 也要求（规则只查公开对象）。"
        "私有定义（名字以 _ 开头，含 __init__ 这类魔法方法）不要求。空字符串与纯空白"
        "不算 docstring（与 python_ast 的判定同一份实现）。"
    )
    return counts["violations"] == 0, _detail(counts, items, note)


def predicate_a8(ctx: Context) -> Tuple[bool, dict]:
    """A8 依赖扇出：每个模块的项目内出边 ≤ 5、入边 ≤ 5。"""

    measured, _sources = ctx.measured
    scope = set(measured)
    out_degree = {path: 0 for path in measured}
    in_degree = {path: 0 for path in measured}
    edges = 0
    for source, target in ctx.edges:
        if source not in scope or target not in scope:
            continue
        edges += 1
        out_degree[source] += 1
        in_degree[target] += 1
    items: list[Mapping[str, Any]] = []
    for path in measured:
        if out_degree[path] > MAX_FAN_OUT or in_degree[path] > MAX_FAN_OUT:
            items.append(
                {"path": path, "out": out_degree[path], "in": in_degree[path]}
            )
    counts = {
        "edges": edges,
        "modules": len(measured),
        "over_threshold": len(items),
        "unresolved": len(ctx.unresolved),
        "violations": len(items),
    }
    note = (
        "边只数项目内依赖（external / call / unresolved 不算）；出边 > %d 或入边 > %d 即 fail。"
        "unresolved 让本谓词 fail：计数建立在完整的依赖图上（§4.2 的“够”以能解析为前提）。"
        % (MAX_FAN_OUT, MAX_FAN_OUT)
    )
    ok = not items and not ctx.unresolved
    return ok, _detail(counts, items, note, unresolved=[dict(item) for item in ctx.unresolved])


def _package_initializers(path: str, scope: Any) -> Tuple[str, ...]:
    """被 import 的子模块会连带 import 它的包的 __init__.py（Python 语义）——覆盖算上它们。"""

    parts = path.split("/")
    found: list[str] = []
    for index in range(1, len(parts)):
        candidate = "/".join(parts[:index]) + "/__init__.py"
        if candidate in scope:
            found.append(candidate)
    return tuple(found)


A9_FAIL_LAYERS = frozenset({LAYER_TEST, LAYER_SKIP})


def predicate_a9(ctx: Context) -> Tuple[bool, dict]:
    """A9 测试对应完备：每个生产文件都被某个测试文件的静态 import 边覆盖。"""

    measured, _sources = ctx.measured
    scope = set(measured)
    test_paths = {path for path in measured if ctx.layer(path) == LAYER_TEST}
    covered: set[str] = set()
    for source, target in ctx.edges:
        if source not in test_paths or target not in scope:
            continue
        covered.add(target)
        covered.update(_package_initializers(target, scope))
    production = [path for path in measured if ctx.layer(path) not in A9_FAIL_LAYERS]
    missing = [path for path in production if path not in covered]
    items = [{"path": path, "line": None, "reason": "no_test_import"} for path in missing]
    counts = {
        "covered": len(production) - len(missing),
        "production_files": len(production),
        "test_files": len(test_paths),
        "violations": len(missing),
    }
    note = (
        "覆盖 = 有测试层文件**静态 import** 到这个模块（以及被 import 的子模块连带 import 的包 "
        "__init__.py）。这是 PipelineReport.selection 的近似：不跑 pytest、不读 "
        "validation/test-layout.yaml，所以 related 以外的升级层级（package / suite）这里看不到——"
        "方向是可能漏、不误报。生产文件 = 除 test / skip 之外的每个测量范围内文件。"
    )
    return counts["violations"] == 0, _detail(counts, items, note, basis="static_import")


def predicate_a10(ctx: Context) -> Tuple[bool, dict]:
    """A10 无动态执行：动态 import 与通配 import 各 0 处。"""

    _measured, sources = ctx.measured
    items: list[Mapping[str, Any]] = []
    counts = {"dynamic_imports": 0, "wildcard_imports": 0, "violations": 0}
    for source in sources:
        facts = source.facts
        if facts is None:
            continue
        for fact in facts.imports:
            if fact.dynamic:
                counts["dynamic_imports"] += 1
                items.append(
                    {
                        "path": source.path,
                        "line": fact.line,
                        "kind": "dynamic_import",
                        "expression": fact.expression or fact.module or "?",
                    }
                )
            elif fact.kind == "from_import" and "*" in fact.names:
                counts["wildcard_imports"] += 1
                items.append(
                    {
                        "path": source.path,
                        "line": fact.line,
                        "kind": "wildcard_import",
                        "expression": "from %s import *" % fact.module,
                    }
                )
    counts["violations"] = counts["dynamic_imports"] + counts["wildcard_imports"]
    note = (
        "动态 import 的识别复用 python_ast（含 __import__、importlib.import_module 及别名形态）；"
        "通配 import = from X import *。两者都让依赖集无法静态确定，§4.2 要求 0 处。"
    )
    return counts["violations"] == 0, _detail(counts, items, note)


# --------------------------------------------------------------------------- 载荷与渲染


_PREDICATES: Tuple[Tuple[str, str, Any], ...] = (
    ("A1", "分层方向", predicate_a1),
    ("A2", "依赖无环", predicate_a2),
    ("A3", "公开符号最小面", predicate_a3),
    ("A4", "组合根唯一", predicate_a4),
    ("A5", "函数复杂度", predicate_a5),
    ("A6", "文件/函数长度", predicate_a6),
    ("A7", "docstring 覆盖", predicate_a7),
    ("A8", "依赖扇出", predicate_a8),
    ("A9", "测试对应完备", predicate_a9),
    ("A10", "无动态执行", predicate_a10),
)


def _scope_payload(context: Context) -> dict:
    """workspace_scope：这次测量覆盖了哪棵树、哪一份声明、哪些文件没测（全是相对路径）。"""

    measured_paths, _sources = context.measured
    files_by_layer: dict[str, int] = {}
    for path in measured_paths:
        layer = context.layer(path) or "undeclared"
        files_by_layer[layer] = files_by_layer.get(layer, 0) + 1
    scope: dict = {
        "root": ".",
        "files": len(measured_paths),
        "files_by_layer": files_by_layer,
        "files_digest": context.files_digest,
        "python_roots": list(PYTHON_ROOTS),
        "layers": {
            "path": context.layers.path,
            "digest": context.layers.digest,
            "entries": len(context.layers.entries),
        },
        "edges_internal": len(context.edges),
        "unresolved": len(context.unresolved),
        "declared_unmatched": list(context.unmatched_entries),
        "declared_non_python": list(context.non_python_entries),
        "undeclared": list(context.undeclared),
        "skipped": list(context.skipped),
        "unmeasurable": [dict(item) for item in context.unmeasurable],
    }
    if context.caps is None:
        scope["interfaces"] = {"status": reading.STATUS_NOT_APPLICABLE}
    else:
        scope["interfaces"] = {
            "status": reading.STATUS_AVAILABLE,
            "path": context.caps.path,
            "digest": context.caps.digest,
            "entries": len(context.caps.caps),
        }
    return scope


def measure(
    workspace: Path, layers: LayerTable, caps: Optional[InterfaceCaps] = None
) -> dict:
    """跑 10 条谓词并返回**可逐字节复现**的载荷（无时戳、无 run 标识、无绝对路径）。"""

    context = build_context(workspace, layers, caps)
    predicates: list[dict] = []
    for identifier, name, function in _PREDICATES:
        ok, detail = function(context)
        if context.unmeasurable:
            # 失败关闭：解析不了的文件无法为任何谓词作证（AGENTS 第 20 条的同一条纪律）。
            ok = False
            detail = dict(detail)
            detail["blocked_by"] = "unmeasurable_files"
        predicates.append(
            {
                "id": identifier,
                "name": name,
                "status": STATUS_PASS if ok else STATUS_FAIL,
                "detail": detail,
            }
        )
    passed = sum(1 for item in predicates if item["status"] == STATUS_PASS)
    return {
        "schema_version": STRUCTURE_METRICS_SCHEMA_VERSION,
        "workspace_scope": _scope_payload(context),
        "predicates": predicates,
        "summary": {"passed": passed, "failed": len(predicates) - passed},
    }


def render_json(payload: Mapping[str, Any]) -> str:
    """机器载荷的字节形态：UTF-8 + LF + 单尾换行，对象键按字典序（相同输入逐字节相同）。"""

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_human(payload: Mapping[str, Any], *, limit: int = 5) -> str:
    """人类可读摘要：每条谓词一行 + 超阈值项（最多 limit 条）+ 一行机器可读汇总。"""

    scope = payload["workspace_scope"]
    lines = [
        "structure_metrics: workspace=%s files=%d layers=%s digest=%s"
        % (scope["root"], scope["files"], scope["layers"]["path"], scope["files_digest"])
    ]
    for predicate in payload["predicates"]:
        detail = predicate["detail"]
        counters = " ".join(
            "%s=%s" % (key, value) for key, value in sorted(detail["counts"].items())
        )
        lines.append(
            "%s %-4s %s  %s"
            % (predicate["id"], predicate["status"].upper(), predicate["name"], counters)
        )
        if predicate["status"] != STATUS_FAIL:
            continue
        if detail.get("blocked_by"):
            lines.append("    blocked_by=%s" % detail["blocked_by"])
        for item in detail["items"][:limit]:
            lines.append("    - " + json.dumps(item, ensure_ascii=False, sort_keys=True))
        if len(detail["items"]) > limit or detail.get("items_truncated"):
            lines.append("    （其余超阈值项见 --json）")
        if detail.get("unresolved"):
            lines.append("    unresolved=%d（清单见 --json）" % len(detail["unresolved"]))
        lines.append("    note: " + str(detail["note"]))
    summary = payload["summary"]
    lines.append("STRUCTURE_METRICS: passed=%d failed=%d" % (summary["passed"], summary["failed"]))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- CLI


def _show_argument(value: Path) -> str:
    """命令行参数的显示形态：相对路径原样，绝对路径写 <absolute-path>（不泄漏宿主路径）。"""

    return str(value) if not value.is_absolute() else "<absolute-path>"


def _write_output(path: Path, text: str, root: Path) -> None:
    """--out：写机器载荷（与 --json 的字节相同；父目录不存在时创建）。"""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as error:
        raise StructureMetricsError(
            "--out 写不了：%s（%s）" % (_show(path, root), type(error).__name__)
        ) from error


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """命令行参数：--workspace 与 --layers 必填，其余可选。"""

    parser = argparse.ArgumentParser(
        prog="structure_metrics", description="A 维度 10 条结构谓词的只读测量器"
    )
    parser.add_argument("--workspace", required=True, type=Path, help="被测树根（必填）")
    parser.add_argument("--layers", required=True, type=Path, help="路径 → layer 的映射（必填）")
    parser.add_argument("--interfaces", type=Path, default=None, help="A3 的声明接口数")
    parser.add_argument("--json", action="store_true", dest="as_json", help="只打印机器载荷")
    parser.add_argument("--out", type=Path, default=None, help="把机器载荷写成文件")
    parser.add_argument("--limit", type=int, default=5, help="人类输出里的超阈值项条数")
    return parser.parse_args(list(argv))


def run(argv: Sequence[str]) -> int:
    """CLI：返回退出码（0 = 10 条全 pass / 1 = 有谓词 fail / 2 = 用法或声明错误）。"""

    args = _parse_args(argv)
    try:
        workspace = args.workspace.resolve()
        if not workspace.is_dir():
            raise StructureMetricsError(
                "--workspace 不是目录：%s" % _show_argument(args.workspace)
            )
        layers = load_layers(args.layers, workspace)
        caps = load_caps(args.interfaces, workspace) if args.interfaces is not None else None
        payload = measure(workspace, layers, caps)
        text = render_json(payload)
        if args.out is not None:
            _write_output(args.out, text, workspace)
        if args.as_json:
            sys.stdout.write(text)
        else:
            sys.stdout.write(render_human(payload, limit=max(0, args.limit)))
    except StructureMetricsError as error:
        sys.stderr.write("structure_metrics: %s\n" % error)
        return EXIT_USAGE
    return EXIT_PASS if payload["summary"]["failed"] == 0 else EXIT_FAIL


def main() -> None:
    """脚本入口：把 run() 的退出码交给解释器。"""

    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()

r"""控制面事实表 × 跨源互证（台阶 5，**只报告**）。

它是什么
========

27 号 §0：台阶 5 的只报告部分 = 一张新的 facts 表（只放指针）+ 在既有检查登记表上扩一个
**可选**的连接键 + 一个双向必查的连接 + 三组跨源读数（C1 两份测试路径声明的差集、
C2 工具表覆盖关系、C3 预算不等式两套结论）。本工具是这些读数的**单消费方**：
facts 表与连接键的两个方向都由它算出来。

它不是什么（读之前先看这三条）
==============================

1. **不判罚**：退出码恒 0（用法错误由 argparse 给 2，与判据无关），四格红条件全部
   enforced: false + would_exit_code: 1（**预注册**，不是承诺）；本轮**没有**接进本机门禁——
   接法与交接清单见 tools/README.md 与 23 号 §21；
2. **不新写判据式**：C1 两侧各用它们**现在**的实现（平台 validators.registry.load_test_layout、
   Adapter adapters.dsh.adapter.load_config），只做集合差；C3 复用
   adapters.dsh.hooks.budget_inequality_facts（一份实现、两个调用点）；C2 **只给读数、
   不给判据**——今天没有一条可评审的判据能说"哪一组差异是缺口"，按 AGENTS 第 50 条，
   没有依据的判定不许造（设计见 27 号 §3.5）；
3. **不合并谓词**：C1 读到的是"两份声明不一致"，降到 0 只有两条路（合并谓词 / 改声明），
   **两条都不在本轮**（27 号 §5 第 1 条）。

载荷自己的版本轴（AGENTS 第 55 条）
=================================

CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.1"——**1.0 = 首次建轴**（facts 表 + 连接键双向必查 +
C1/C2/C3 三组读数）；**1.1 = 阶段 A1 的 C4 通道覆盖账**（2026-10-18）：顶层多一份 coverage
块（表 / 审计 / 注册表摘要 / 引用完整性 + 四个新红键 row_without_mode / mode_without_check /
tool_with_hits_without_row / registry_digest_drift）与 --coverage / --audit 两个参数。
facts 表自己的轴是 FACTS_TABLE_SCHEMA_VERSION = "1"；新数据文件
validation/channel-coverage.yaml 自己的轴是 CHANNEL_COVERAGE_SCHEMA_VERSION = "1"。
**既有载荷一个键都不加**：R-h 那个载荷（INSTRUMENT_SELF_PROOF_SCHEMA_VERSION）的 HITS: 行
已经是 26 号交接给 CI 线的**跨文件契约**，动它等于让正在接线的 CI 线返工；本载荷自带轴、
自带 HITS: 行，ci_local.report_only_reading() **一个字都不用改**。

C4 通道覆盖账（阶段 A1，只报告）
==============================

第 4 组读数把「哪个通道 × 哪个工具 × 哪种治理 × 哪条检查」变成可查询的行：数据在
validation/channel-coverage.yaml（自带 schema_version "1"、只放指针、三态 coverage、
mode 闭集写死在文件头），本工具是它唯一的消费方。四格红条件与 wiring / R-h **同形状**；
引用完整性（channel / tool / check_id / covers_facts）**另立 references 块**，不混进四红
冒充。审计输入只由 --audit 显式给（不扫目录、不猜默认路径）：不给 = not_applicable，
读不了 = unavailable，**都不记作 0 命中**（AGENTS 第 56 条）。注册表摘要直接调用
enforcement.registry 的加载 API（load_registry → ToolRegistry.identity），不在这里重写
哈希规则（AGENTS 第 50 条：同名两义一律改名）。

只报告期怎么表达
================

- 每格红条件与 adapters.cli wiring / tools/instrument_self_proof.py **逐字同形**：
  status / count / items[] / is_red / red_when / enforced: false / would_exit_code: 1 /
  promote_when / note（读到未评时另加 reason）；
- "未评"写 unavailable + reason，count 写 **null 不是 0**（AGENTS 第 56 条）；
- 两条机器行：CONTROL_PLANE_FACTS: ...（本工具自己的读数）与
  HITS: <四格合计> / ...（跨文件契约，与 exemption_expiry / instrument_self_proof 同族）。
  1.1 起两条都追加 C4 四格与 coverage_rows= / references= / audit= 读数；**HITS 的合计仍是
  既有四格之和**（既有含义不变，读取器仍读到整数），C4 四格只作为逐项出现，
  因为不给 --audit 时其中一格是 not_applicable，并进合计会把「不适用」读成「读数坏了」。

实例从哪来（显式，不扫目录）
============================

仓库内实例 examples/dsh/ **恒读**；其他实例只由 --instance <config>@<hooks> 显式给
（27 号 §3.6）。**不扫 .tmp**：扫目录会把环境残渣读成事实，而且 cleanup.py 之后它们
就不存在了（AGENTS 核心约束 6：不得根据目录推断上下文）。

用法
====

    python tools/control_plane_facts.py [--json] [--facts PATH] [--checks PATH]
                                        [--coverage PATH] [--audit PATH]
                                        [--instance <config>@<hooks>]...
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple, Optional, Sequence

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
# 检查登记表的加载器**只有一份**：本工具 import 同目录的 tools/instrument_self_proof.py，
# 而不是再写一个 YAML 读取器——同一张表两处解析就是同名两义（AGENTS 第 50 条）。
sys.path.insert(0, str(Path(__file__).resolve().parent))

import instrument_self_proof as isp  # noqa: E402

from adapters.dsh import hooks as dsh_hooks  # noqa: E402
from adapters.dsh.adapter import TOOL_TABLE, DshEventError, load_config  # noqa: E402
from adapters.wiring import WiringError, probe_wiring  # noqa: E402
from enforcement.registry import RegistryError, load_registry  # noqa: E402
from policy.check import resolve_layer  # noqa: E402
from provenance import reading_context as reading  # noqa: E402
from provenance.wiring_scope import WiringScopeError, load_wiring_scope  # noqa: E402
from validators.registry import RegistryError as ValidatorsRegistryError  # noqa: E402
from validators.registry import load_test_layout  # noqa: E402

# 本载荷的版本轴（AGENTS 第 55 条；**首次出现就带轴**；1.0 -> 1.1 = 阶段 A1 的 C4 覆盖账）。
CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.1"
# facts 表自己的版本轴（数据文件，与上面的载荷轴各走各的）。
FACTS_TABLE_SCHEMA_VERSION = "1"
# 通道覆盖表自己的版本轴（数据文件，第一次出现就带轴；与载荷轴各走各的）。
CHANNEL_COVERAGE_SCHEMA_VERSION = "1"

DEFAULT_FACTS = REPO / "validation" / "control-plane-facts.yaml"
DEFAULT_CHECKS = isp.DEFAULT_CHECKS
DEFAULT_COVERAGE = REPO / "validation" / "channel-coverage.yaml"
def _example_paths(root: Path) -> tuple[Path, Path]:
    """`examples/dsh` 的两个文件**相对被检根**取（旧写法把 REPO 的绝对路径写死成模块常量）。

    混用两个基准会让 `evaluate(repo=…)` 的读数变成**从两棵树缝出来的**：枚举 `root/tests`，
    却读 REPO 的 adapter 配置与示例预算；而 `_display(EXAMPLE_HOOKS, root=root)` 在 `root != REPO`
    时把示例路径折成"工作区之外"的占位符，本地通道的 `matched` 永远对不上。
    """

    base = root / "examples" / "dsh"
    return base / "dsh-adapter.yaml", base / "hooks.json"

STATUS_AVAILABLE = reading.STATUS_AVAILABLE
STATUS_UNAVAILABLE = reading.STATUS_UNAVAILABLE

# facts 表的 key 形态：**连接键的两个方向共用这一份**（定义在检查登记表的加载器里，
# 因为那张表的加载期就要校验 covers_facts 的形态——见 tools/instrument_self_proof.py）。
FACT_KEY_PATTERN = isp.FACT_KEY_PATTERN

# 行字段（27 号 §3.1，逐字取方案 §3.2 的 facts 段）。
ROW_FIELDS = (
    "key",
    "authority",
    "canonical_ref",
    "consumers",
    "predicate",
    "severity",
    "remedy",
    "on_unprovable",
    "expires",
)
AUTHORITIES = ("canonical", "observed")
ON_UNPROVABLE = ("unavailable", "not_applicable")
SEVERITIES = isp.SEVERITIES
# observed 行必须在 canonical_ref 里写清"谁观测"：形态是 "<谁观测>@<出处>"。
OBSERVED_REF_PATTERN = re.compile(r"^[^@]+@[^@]+$")
EXPIRES_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 四格红条件（键名稳定，是**跨文件契约**）。
RED_FACT_WITHOUT_CHECK = "fact_without_check"
RED_CHECK_COVERS_UNKNOWN_FACT = "check_covers_unknown_fact"
RED_TEST_PATH_DECLARATION = "test_path_declaration"
RED_BUDGET_INEQUALITY = "budget_inequality"
RED_KEYS = (
    RED_FACT_WITHOUT_CHECK,
    RED_CHECK_COVERS_UNKNOWN_FACT,
    RED_TEST_PATH_DECLARATION,
    RED_BUDGET_INEQUALITY,
)

# ---- C4 通道覆盖账（阶段 A1）----
#
# 四个红键（键名稳定，是**跨文件契约**；与上面四格**并列**，不是替换）。
RED_ROW_WITHOUT_MODE = "row_without_mode"
RED_MODE_WITHOUT_CHECK = "mode_without_check"
RED_TOOL_WITH_HITS_WITHOUT_ROW = "tool_with_hits_without_row"
RED_REGISTRY_DIGEST_DRIFT = "registry_digest_drift"
COVERAGE_RED_KEYS = (
    RED_ROW_WITHOUT_MODE,
    RED_MODE_WITHOUT_CHECK,
    RED_TOOL_WITH_HITS_WITHOUT_ROW,
    RED_REGISTRY_DIGEST_DRIFT,
)
# coverage 的三态闭集（别的取值是**结构错误**：整节降级为 unavailable）。
COVERAGE_STATES = ("enforced", "declared_uncovered", "not_applicable")
# mode 的闭集（写死在表头；enforced 行缺 mode / mode 不在闭集 = row_without_mode）。
COVERAGE_MODES = ("policy", "pre_evidence", "enforcement", "delegated", "post_check")
# 行字段：前 8 个必填（mode / check_id 可为 null，由红条件判），covers_facts 可选。
COVERAGE_ROW_FIELDS = (
    "channel",
    "tool",
    "mode",
    "coverage",
    "check_id",
    "owner",
    "reason",
    "expires_at",
)
COVERAGE_OPTIONAL_FIELDS = ("covers_facts",)
STATUS_NOT_APPLICABLE = reading.STATUS_NOT_APPLICABLE
_AUDIT_GOVERNED_KEY = "governed"
_AUDIT_PRE_TOOL_USE = "PreToolUse"

# 裁定④（2026-10-03）：orchestrator 段的 tool_name 要**查实**——查不到写 unavailable。
# 搜索范围是代码与数据根（不扫 docs/mirrors：300 个镜像文件与"谁在读它"无关）。
ORCHESTRATOR_TOOL_NAMES = ("edit_file", "write_file", "edit_policy", "write_policy")
ORCHESTRATOR_SEARCH_ROOTS = ("src", "registry", "adapters", "tools")
ORCHESTRATOR_SEARCH_SUFFIXES = (".py", ".yaml", ".yml", ".json")
# 这两个文件**不算读取点**：注册表里那四行是**声明**；本工具的源码是**搜索词**的来源。
# 不排除它们就是自证循环——仪器把"我自己写了这几个词"读成"有人在读它们"。
ORCHESTRATOR_NON_READERS = ("registry/tool-registry.yaml", "tools/control_plane_facts.py")

_PROMOTE_WHEN = (
    "跑过 N≥1 次且**四格**合计 0 命中，且 0 命中来自至少一次真实读数"
    "——与 L5 上线闸 / R-h 同型；升格前必须先有一轮 warn + 非零退出"
)
_REPORT_ONLY_NOTE = "只报告期：本块不改任何退出码（本工具退出码恒为 0）"


class FactsTableError(Exception):
    """facts 表读不出来。**只报告**：调用方把它变成 unavailable，不阻断（27 号 §5 第 2 条）。"""


class FactRow(NamedTuple):
    """facts 表的一行（9 字段）：声明的事实 + 谁在判定它。"""

    key: str
    authority: str
    canonical_ref: str
    consumers: tuple
    predicate: str
    severity: str
    remedy: str
    on_unprovable: str
    expires: Optional[str]

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "authority": self.authority,
            "canonical_ref": self.canonical_ref,
            "consumers": list(self.consumers),
            "predicate": self.predicate,
            "severity": self.severity,
            "remedy": self.remedy,
            "on_unprovable": self.on_unprovable,
            "expires": self.expires,
        }


class FactsTable(NamedTuple):
    path: Path
    schema_version: str
    rows: tuple
    by_key: dict


# --------------------------------------------------------------------------- 小工具


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FactsTableError(where + " 必须是非空字符串，读到 " + repr(value))
    return value


def _enum(value: Any, allowed: Sequence[str], where: str) -> str:
    if value not in allowed:
        raise FactsTableError(
            where + " 只接受 " + " / ".join(allowed) + "，读到 " + repr(value)
        )
    return str(value)


def _display(path: Path, *, root: Path) -> str:
    """读数里的路径一律仓库相对（AGENTS 第 19 条）；工作区之外折叠成占位符。"""

    return reading.display_path(path, root=root)


# --------------------------------------------------------------------------- facts 表


def _fact_row(item: Any, where: str) -> FactRow:
    if not isinstance(item, dict):
        raise FactsTableError(where + " 必须是映射")
    # 「不放值」先判：这几类键不是"未知字段"，是**禁止的字段**（与登记表同纪律）。
    for key in item:
        if key in isp.POINTER_ONLY_KEYS or str(key).startswith(isp.POINTER_ONLY_PREFIXES):
            raise FactsTableError(
                where + " 出现 " + repr(key) + "：facts 表只放指针——"
                "运行结果（last_run / status / passed / observed_*）不许写进这张表"
            )
    unknown = sorted(set(item) - set(ROW_FIELDS))
    if unknown:
        raise FactsTableError(where + " 有未知字段：" + " / ".join(unknown))
    missing = [field for field in ROW_FIELDS if field not in item]
    if missing:
        raise FactsTableError(where + " 缺字段：" + " / ".join(missing))

    key = _text(item["key"], where + ".key")
    if not FACT_KEY_PATTERN.match(key):
        raise FactsTableError(
            where + ".key 必须点分两段以上（^[a-z][a-z0-9_]*(\\.[a-z0-9_]+)+$），读到 " + repr(key)
        )
    authority = _enum(item["authority"], AUTHORITIES, where + ".authority")
    canonical_ref = _text(item["canonical_ref"], where + ".canonical_ref")
    if authority == "observed" and not OBSERVED_REF_PATTERN.match(canonical_ref):
        raise FactsTableError(
            where + ".canonical_ref 在 authority=observed 时必须写成 \"<谁观测>@<出处>\""
            "（要写清谁观测的），读到 " + repr(canonical_ref)
        )
    raw_consumers = item["consumers"]
    if not isinstance(raw_consumers, list) or not raw_consumers:
        raise FactsTableError(
            where + ".consumers 必须是非空字符串列表，读到 " + repr(raw_consumers)
        )
    consumers = tuple(
        _text(value, where + ".consumers[" + str(index) + "]")
        for index, value in enumerate(raw_consumers)
    )
    expires = item["expires"]
    if expires is not None:
        if not isinstance(expires, str) or not EXPIRES_PATTERN.match(expires):
            raise FactsTableError(
                where + ".expires 必须是 YYYY-MM-DD 或 null，读到 " + repr(expires)
            )
    return FactRow(
        key=key,
        authority=authority,
        canonical_ref=canonical_ref,
        consumers=consumers,
        predicate=_text(item["predicate"], where + ".predicate"),
        severity=_enum(item["severity"], SEVERITIES, where + ".severity"),
        remedy=_text(item["remedy"], where + ".remedy"),
        on_unprovable=_enum(item["on_unprovable"], ON_UNPROVABLE, where + ".on_unprovable"),
        expires=expires,
    )


def load_facts(path: Path, *, display: Optional[str] = None) -> FactsTable:
    """读 facts 表：未知版本 / 未知字段 / 未知枚举 / 重复 key / 空 consumers 一律报错。

    observed 却没写清谁观测同样报错——**但只在只报告工具内部降级**（27 号 §5 第 2 条：
    不新增任何加载期 FATAL，判定路径与门禁的退出码一个都不动）。

    **不放值**：last_run / status / passed / observed_* 是禁键（那是运行结果，不是声明）；
    severity / on_unprovable / expires / authority 是**声明**，必须写。
    """

    label = display if display is not None else path.name
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        # UnicodeDecodeError 是 ValueError 子类，不属于 OSError：非 UTF-8 的 facts 表会**逃出**
        # 这条声明式错误通道，变成一段栈回溯（本文件 _readers_of 早就按 (OSError,
        # UnicodeDecodeError) 兜了，这里是同一口径的补齐）。
        raise FactsTableError(
            "facts 表读不到（或不是 UTF-8）：" + label + "：" + str(error)
        ) from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise FactsTableError("facts 表不是合法 YAML：" + str(error)) from error
    if not isinstance(document, dict):
        raise FactsTableError("facts 表的顶层必须是映射")
    unknown = sorted(set(document) - {"schema_version", "facts"})
    if unknown:
        raise FactsTableError("facts 表顶层有未知字段：" + " / ".join(unknown))
    version = document.get("schema_version")
    if version != FACTS_TABLE_SCHEMA_VERSION:
        raise FactsTableError(
            "facts 表的 schema_version 只接受 "
            + repr(FACTS_TABLE_SCHEMA_VERSION)
            + "，读到 "
            + repr(version)
        )
    rows_raw = document.get("facts")
    if not isinstance(rows_raw, list) or not rows_raw:
        raise FactsTableError("facts 表的 facts 段必须是非空列表")
    rows: list = []
    by_key: dict = {}
    for index, item in enumerate(rows_raw):
        row = _fact_row(item, "facts[" + str(index) + "]")
        if row.key in by_key:
            raise FactsTableError("facts 表的 key 重复：" + row.key)
        by_key[row.key] = row
        rows.append(row)
    return FactsTable(path=path, schema_version=version, rows=tuple(rows), by_key=by_key)


# --------------------------------------------------------------------------- C4 通道覆盖表


def _display_file(path: Path, *, root: Path) -> str:
    """读数里的文件路径：仓库内 -> 相对路径；仓库外 -> "<outside-workspace>/<文件名>"。

    与 provenance.reading_context.display_path 同一条脱敏纪律（AGENTS 第 16/34 条：
    读数不放绝对路径）。工作区外的输入（例如真实 Governance 审计）保留**文件名**，
    因为"读的是哪个文件"本身是读数的一部分，路径本身不是。
    """

    text = _display(path, root=root)
    if text == reading.OUTSIDE_WORKSPACE:
        return text + "/" + path.name
    return text


class CoverageTableError(Exception):
    """通道覆盖表读不出来。**只报告**：调用方把它变成 unavailable，不阻断（阶段 A 冻结令）。"""


class CoverageRow(NamedTuple):
    """覆盖表的一行：channel × tool × mode × coverage × check_id（+ 可选 covers_facts）。"""

    channel: str
    tool: str
    mode: Optional[str]
    coverage: str
    check_id: Optional[str]
    owner: str
    reason: str
    expires_at: Optional[str]
    covers_facts: tuple

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "tool": self.tool,
            "mode": self.mode,
            "coverage": self.coverage,
            "check_id": self.check_id,
            "owner": self.owner,
            "reason": self.reason,
            "expires_at": self.expires_at,
            "covers_facts": list(self.covers_facts),
        }


class CoverageTable(NamedTuple):
    path: Path
    schema_version: str
    rows: tuple


def _coverage_row(item: Any, where: str) -> CoverageRow:
    """一行覆盖声明：结构错误一律抛（整节降级），**语义错误留给红条件**。

    分工（与 27 号 §3.2 对连接键的分工同型）：
    - 缺 mode / mode 不在闭集 → **不是**结构错误（否则 row_without_mode 永远数不到东西）；
    - enforced 行缺 check_id → **不是**结构错误（mode_without_check 的落点）；
    - unknown 字段 / 未知 coverage 取值 / 坏日期 / 重复行 → 结构错误。
    """

    if not isinstance(item, dict):
        raise CoverageTableError(where + " 必须是映射")
    for key in item:
        if key in isp.POINTER_ONLY_KEYS or str(key).startswith(isp.POINTER_ONLY_PREFIXES):
            raise CoverageTableError(
                where + " 出现 " + repr(key) + "：覆盖表只放指针——"
                "运行结果（last_run / status / passed / observed_*）不许写进这张表"
            )
    unknown = sorted(set(item) - set(COVERAGE_ROW_FIELDS) - set(COVERAGE_OPTIONAL_FIELDS))
    if unknown:
        raise CoverageTableError(where + " 有未知字段：" + " / ".join(unknown))
    # mode / check_id **允许省略**：缺了不是结构错误，而是四个红键要数的语义缺口
    # （row_without_mode / mode_without_check）。其余字段省略是结构错误。
    missing = [
        field
        for field in COVERAGE_ROW_FIELDS
        if field not in ("mode", "check_id") and field not in item
    ]
    if missing:
        raise CoverageTableError(where + " 缺字段：" + " / ".join(missing))

    coverage = _enum(item["coverage"], COVERAGE_STATES, where + ".coverage")
    mode: Optional[str] = None
    if item.get("mode") is not None:
        mode = _text(item["mode"], where + ".mode")
    check_id: Optional[str] = None
    if item.get("check_id") is not None:
        check_id = _text(item["check_id"], where + ".check_id")
    if coverage != "enforced" and check_id is not None:
        raise CoverageTableError(
            where + ".check_id 在 coverage=" + coverage + " 时必须为 null："
            "声明了「没覆盖」却挂一条检查，是自相矛盾（enforced 才需要 check_id）"
        )
    expires_at = item["expires_at"]
    if expires_at is not None:
        if not isinstance(expires_at, str) or not EXPIRES_PATTERN.match(expires_at):
            raise CoverageTableError(
                where + ".expires_at 必须是 YYYY-MM-DD 或 null，读到 " + repr(expires_at)
            )
        try:
            _datetime.date.fromisoformat(expires_at)
        except ValueError as error:
            raise CoverageTableError(
                where + ".expires_at 不是真实日期：" + repr(expires_at)
            ) from error
    if coverage == "declared_uncovered" and expires_at is None:
        raise CoverageTableError(
            where + " 在 coverage=declared_uncovered 时必须写 expires_at："
            "没有到期日的缺口是一张永久空白支票（与 wiring-scope 的 out_of_scope 同一条纪律）"
        )

    raw_covers = item.get("covers_facts", [])
    if not isinstance(raw_covers, list):
        raise CoverageTableError(
            where + ".covers_facts 必须是字符串列表，读到 " + repr(raw_covers)
        )
    covers_facts = []
    for position, key in enumerate(raw_covers):
        if not isinstance(key, str) or not FACT_KEY_PATTERN.match(key):
            raise CoverageTableError(
                where
                + ".covers_facts["
                + str(position)
                + "] 必须是点分两段以上的 facts key（"
                + FACT_KEY_PATTERN.pattern
                + "），读到 "
                + repr(key)
            )
        covers_facts.append(key)

    return CoverageRow(
        channel=_text(item["channel"], where + ".channel"),
        tool=_text(item["tool"], where + ".tool"),
        mode=mode,
        coverage=coverage,
        check_id=check_id,
        owner=_text(item["owner"], where + ".owner"),
        reason=_text(item["reason"], where + ".reason"),
        expires_at=expires_at,
        covers_facts=tuple(covers_facts),
    )


def load_coverage(path: Path, *, display: Optional[str] = None) -> CoverageTable:
    """读通道覆盖表：未知版本 / 未知字段 / 未知 coverage / 坏日期 / 重复行一律报错。

    **不抛给判定路径**：调用方（evaluate）把它变成 coverage.table.status=unavailable +
    reason，四格红条件全部记 unavailable（count=null，**不是 0**）。结构错误与语义错误的
    分工见 _coverage_row 的说明。
    """

    label = display if display is not None else path.name
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CoverageTableError(
            "通道覆盖表读不到（或不是 UTF-8）：" + label + "：" + str(error)
        ) from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise CoverageTableError("通道覆盖表不是合法 YAML：" + str(error)) from error
    if not isinstance(document, dict):
        raise CoverageTableError("通道覆盖表的顶层必须是映射")
    unknown = sorted(set(document) - {"schema_version", "rows"})
    if unknown:
        raise CoverageTableError("通道覆盖表顶层有未知字段：" + " / ".join(unknown))
    version = document.get("schema_version")
    if version != CHANNEL_COVERAGE_SCHEMA_VERSION:
        raise CoverageTableError(
            "通道覆盖表的 schema_version 只接受 "
            + repr(CHANNEL_COVERAGE_SCHEMA_VERSION)
            + "，读到 "
            + repr(version)
        )
    raw_rows = document.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise CoverageTableError("通道覆盖表的 rows 段必须是非空列表")
    rows: list = []
    seen: dict = {}
    for index, item in enumerate(raw_rows):
        row = _coverage_row(item, "rows[" + str(index) + "]")
        identity = (row.channel, row.tool, row.mode or "")
        if identity in seen:
            raise CoverageTableError(
                "通道覆盖表的 (channel, tool, mode) 重复："
                + " / ".join(identity)
                + "（rows["
                + str(seen[identity])
                + "] 与 rows["
                + str(index)
                + "]）"
            )
        seen[identity] = index
        rows.append(row)
    return CoverageTable(path=path, schema_version=version, rows=tuple(rows))


def read_governed_audit(path: Optional[Path], *, root: Path) -> dict:
    """读受治理审计（JSONL），只数 governed=true 的 PreToolUse，按工具分组。

    **不给 / 读不了都不是 0 命中**：
    - 不给 --audit → not_applicable（不知道哪些工具有命中，不是"没有命中"）；
    - 读不了 / 有不可解析行 / governed 记录缺工具名 → unavailable + reason；
    - 只有"整份文件逐行解析成功"才是 available（0 条 governed 记录是合法读数）。
    末行截断（正在追加的日志）单独标出、不当作不可解析行——但也不据此声称"没有漏"。
    """

    note = (
        "只数 governed=true 且 hook_event=PreToolUse 的记录；不给 --audit = 不适用，"
        "读不了 = 未评——两者都不写 0（AGENTS 第 56 条）"
    )
    if path is None:
        return {
            "status": STATUS_NOT_APPLICABLE,
            "path": None,
            "records": None,
            "lines": None,
            "governed_pre_tool_use": None,
            "by_tool": {},
            "malformed_lines": 0,
            "reason": "没有给 --audit：不知道哪些工具有受治理命中（不适用，不是 0 命中）",
            "note": note,
        }
    label = _display_file(path, root=root)
    shared = {
        "path": label,
        "records": None,
        "lines": None,
        "governed_pre_tool_use": None,
        "by_tool": {},
        "malformed_lines": 0,
        "note": note,
    }
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return {
            **shared,
            "status": STATUS_UNAVAILABLE,
            "reason": "审计读不出来：" + type(error).__name__ + "：" + str(error),
        }
    raw_lines = text.splitlines()
    nonblank = 0
    records = 0
    malformed = 0
    governed = 0
    without_tool = 0
    tail_in_progress = False
    by_tool: dict = {}
    for index, raw in enumerate(raw_lines):
        line = raw.strip()
        if not line:
            continue
        nonblank += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            if index == len(raw_lines) - 1 and not text.endswith(("\n", "\r")):
                tail_in_progress = True
                continue
            malformed += 1
            continue
        if not isinstance(record, dict):
            malformed += 1
            continue
        records += 1
        if record.get(_AUDIT_GOVERNED_KEY) is not True:
            continue
        if record.get("hook_event") != _AUDIT_PRE_TOOL_USE:
            continue
        governed += 1
        tool = record.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            without_tool += 1
            continue
        by_tool[tool] = by_tool.get(tool, 0) + 1
    if malformed:
        return {
            **shared,
            "status": STATUS_UNAVAILABLE,
            "lines": nonblank,
            "records": records,
            "malformed_lines": malformed,
            "reason": "审计里有 "
            + str(malformed)
            + " 行不是合法的 JSON 记录：不能证明没有漏掉受治理命中（读不了不是 0）",
        }
    if without_tool:
        return {
            **shared,
            "status": STATUS_UNAVAILABLE,
            "lines": nonblank,
            "records": records,
            "governed_pre_tool_use": governed,
            "reason": "审计里有 "
            + str(without_tool)
            + " 条 governed=true 的记录没有工具名：归属不了，不能当成「没有工具缺行」",
        }
    return {
        **shared,
        "status": STATUS_AVAILABLE,
        "lines": nonblank,
        "records": records,
        "governed_pre_tool_use": governed,
        "by_tool": dict(sorted(by_tool.items())),
        "tail_in_progress": tail_in_progress,
        "reason": None,
    }


def registry_digest_reading(root: Path) -> dict:
    """注册表摘要 × 已审核摘要（只报告）。

    摘要**不在这里重写**：ToolRegistry.identity 与已审核清单的读取都走 enforcement.registry
    的加载 API（AGENTS 第 50 条：同名两义一律改名；第 13 条：运行时描述与已审核哈希不一致的
    工具不可使用）。读不出来记 unavailable；**没有已审核摘要可比**按漂移处理（证明不了被审核过）。
    """

    registry_path = root / "registry" / "tool-registry.yaml"
    approved_path = root / "registry" / "tool-registry.approved.json"
    shared = {
        "path": _display(registry_path, root=root),
        "approved_path": _display(approved_path, root=root),
        "registry_version": None,
        "current_digest": None,
        "approved_digest": None,
        "matches": None,
        "note": (
            "当前摘要 = enforcement.registry.ToolRegistry.identity；已审核摘要 = "
            "registry/tool-registry.approved.json 的 registry_digest。"
            "两者不一致 = registry_digest_drift 红；读不出来 = unavailable（不是 0）。"
        ),
    }
    try:
        loaded = load_registry(registry_path, approved_path=approved_path)
    except (RegistryError, OSError) as error:
        return {
            **shared,
            "status": STATUS_UNAVAILABLE,
            "reason": "注册表或已审核清单读不出来：" + type(error).__name__ + "：" + str(error),
        }
    registry = loaded.registry
    approved = loaded.approved_document if isinstance(loaded.approved_document, dict) else {}
    approved_digest = approved.get("registry_digest")
    if not isinstance(approved_digest, str) or not approved_digest:
        approved_digest = None
    current = registry.identity
    return {
        **shared,
        "status": STATUS_AVAILABLE,
        "registry_version": registry.version,
        "current_digest": current,
        "approved_digest": approved_digest,
        "approved_schema_version": approved.get("approved_schema_version"),
        "reviewed_by": approved.get("reviewed_by"),
        "approved_at": approved.get("approved_at"),
        "governance_drift_reason": registry.registry_drift_reason(),
        "matches": approved_digest == current,
        "reason": None,
    }


def build_coverage_references(
    *,
    coverage: Optional[CoverageTable],
    coverage_error: Optional[str],
    declared_ids: Optional[set],
    declared_error: Optional[str],
    check_ids: Optional[set],
    checks_error: Optional[str],
    fact_keys: Optional[set],
    facts_error: Optional[str],
) -> dict:
    """引用完整性（**独立读数**）：channel / tool / check_id / covers_facts 各自断开几条。

    这不属于四个红键：红键数的是"覆盖缺口"，这里数的是"指针写错"。混成一个数会让
    一次拼写错误冒充一个治理缺口，也会让真正的缺口藏在"引用全断"后面。
    """

    red_when = "任一引用断开（channel / tool / check_id / covers_facts）；它不是四个红键之一"
    note = (
        "引用完整性是**独立读数**：channel -> adapters/wiring-scope.yaml 的声明 id、"
        "tool -> TOOL_TABLE、check_id -> validation/instrument-checks.yaml、"
        "covers_facts -> validation/control-plane-facts.yaml。"
        "断开数不计入四个红键（那四格数的是覆盖缺口，不是指针质量）"
    )
    if coverage is None:
        reason = coverage_error or "通道覆盖表读不到"
        blank = {"status": STATUS_UNAVAILABLE, "count": None, "items": [], "reason": reason}
        return {
            "channel": dict(blank),
            "tool": dict(blank),
            "check_id": dict(blank),
            "covers_facts": dict(blank),
            "total": None,
            "is_red": False,
            "red_when": red_when,
            "note": note,
        }

    def _sub(kind: str, valid: Optional[set], reason: Optional[str]) -> dict:
        if valid is None:
            return {
                "status": STATUS_UNAVAILABLE,
                "count": None,
                "items": [],
                "reason": reason or (kind + " 的权威清单读不到"),
            }
        items: list = []
        for index, row in enumerate(coverage.rows):
            if kind == "channel":
                values = [row.channel]
            elif kind == "tool":
                values = [row.tool]
            elif kind == "check_id":
                values = [] if row.check_id is None else [row.check_id]
            else:
                values = list(row.covers_facts)
            for value in values:
                if value not in valid:
                    items.append(
                        {
                            "row": index,
                            "field": kind,
                            "value": value,
                            "channel": row.channel,
                            "tool": row.tool,
                            "mode": row.mode,
                            "remedy": "改指向存在的 "
                            + {
                                "channel": "adapters/wiring-scope.yaml 声明 id",
                                "tool": "TOOL_TABLE 键",
                                "check_id": "instrument-checks check_id",
                                "covers_facts": "facts key",
                            }[kind]
                            + "，或删掉这一行的这个指针",
                        }
                    )
        return {"status": STATUS_AVAILABLE, "count": len(items), "items": items}

    channel = _sub("channel", declared_ids, declared_error)
    tool = _sub("tool", set(TOOL_TABLE), None)
    check_id = _sub("check_id", check_ids, checks_error)
    covers_facts = _sub("covers_facts", fact_keys, facts_error)
    sub_counts = [channel["count"], tool["count"], check_id["count"], covers_facts["count"]]
    total: Optional[int] = None if any(value is None for value in sub_counts) else sum(sub_counts)
    return {
        "channel": channel,
        "tool": tool,
        "check_id": check_id,
        "covers_facts": covers_facts,
        "total": total,
        "is_red": bool(total) if total is not None else False,
        "red_when": red_when,
        "note": note,
    }


_COVERAGE_RED_WHEN = {
    RED_ROW_WITHOUT_MODE: (
        "coverage=enforced 的行缺 mode 或 mode 不在闭集 "
        + " / ".join(COVERAGE_MODES)
        + "（这一格只数 enforced 行；declared_uncovered 行不参与）"
    ),
    RED_MODE_WITHOUT_CHECK: (
        "coverage=enforced 的行 check_id 为空或不在 validation/instrument-checks.yaml 里："
        "声明了覆盖却拿不出看它的检查"
    ),
    RED_TOOL_WITH_HITS_WITHOUT_ROW: (
        "审计里 governed=true 的 PreToolUse 命中某个工具，而覆盖表没有任何一行覆盖它"
        "（删掉一行的变异就从这里红）"
    ),
    RED_REGISTRY_DIGEST_DRIFT: (
        "当前注册表摘要（ToolRegistry.identity）与 registry/tool-registry.approved.json 的 "
        "registry_digest 不一致"
    ),
}
_COVERAGE_PROMOTE_WHEN = (
    "跑过 N≥1 次且**覆盖账**四格合计 0 命中，且 0 命中来自至少一次真实读数"
    "（有 --audit、有可解析的登记表、有可比的已审核摘要）；升格前必须先有一轮 warn + 非零退出"
)


def build_coverage_red_conditions(
    *,
    coverage: Optional[CoverageTable],
    coverage_error: Optional[str],
    checks: Optional[isp.ChecksTable],
    checks_error: Optional[str],
    audit: dict,
    registry: dict,
) -> dict:
    """C4 的四格红条件：row_without_mode / mode_without_check / tool_with_hits_without_row /
    registry_digest_drift。形状与既有四格逐字同形（_cell），enforced=false + would_exit_code=1。

    三种状态必须能分开读：available（数得出来）/ unavailable（读不到，count=null）/
    not_applicable（这条路径上没有这个输入，count=null）——后两者都**不是 0**。
    """

    if coverage is None:
        reason = coverage_error or "通道覆盖表读不到"
        return {
            key: _unavailable_cell(
                _COVERAGE_RED_WHEN[key], reason, promote_when=_COVERAGE_PROMOTE_WHEN
            )
            for key in COVERAGE_RED_KEYS
        }

    enforced = [row for row in coverage.rows if row.coverage == "enforced"]
    absent_mode = [
        {
            "row": index,
            "channel": row.channel,
            "tool": row.tool,
            "mode": row.mode,
            "remedy": "补一个闭集内的 mode（" + " / ".join(COVERAGE_MODES) + "），或把这一行改成 declared_uncovered",
        }
        for index, row in enumerate(coverage.rows)
        if row.coverage == "enforced"
        and (row.mode is None or row.mode not in COVERAGE_MODES)
    ]

    if checks is None:
        without_check: dict = _unavailable_cell(
            _COVERAGE_RED_WHEN[RED_MODE_WITHOUT_CHECK],
            checks_error or "检查登记表读不到",
            promote_when=_COVERAGE_PROMOTE_WHEN,
        )
    else:
        known_checks = {row.check_id for row in checks.rows}
        broken = [
            {
                "row": index,
                "channel": row.channel,
                "tool": row.tool,
                "mode": row.mode,
                "check_id": row.check_id,
                "remedy": (
                    "把 check_id 指向 validation/instrument-checks.yaml 里存在的 check_id"
                    "（不新开行；沿用现有登记）"
                ),
            }
            for index, row in enumerate(coverage.rows)
            if row.coverage == "enforced"
            and (row.check_id is None or row.check_id not in known_checks)
        ]
        without_check = _cell(
            status=STATUS_AVAILABLE,
            count=len(broken),
            items=broken,
            red_when=_COVERAGE_RED_WHEN[RED_MODE_WITHOUT_CHECK],
            note=(
                "今天表里 enforced 行的 check_id 只有一条（report-only:Control plane facts）："
                "它只是计数器；「enforced」的依据是审计命中，不是「有一条门禁在证明它」"
            ),
            promote_when=_COVERAGE_PROMOTE_WHEN,
        )

    if audit["status"] == STATUS_NOT_APPLICABLE:
        tool_hits: dict = _cell(
            status=STATUS_NOT_APPLICABLE,
            count=None,
            items=[],
            red_when=_COVERAGE_RED_WHEN[RED_TOOL_WITH_HITS_WITHOUT_ROW],
            note=_REPORT_ONLY_NOTE,
            reason=audit.get("reason"),
            promote_when=_COVERAGE_PROMOTE_WHEN,
        )
    elif audit["status"] != STATUS_AVAILABLE:
        tool_hits = _unavailable_cell(
            _COVERAGE_RED_WHEN[RED_TOOL_WITH_HITS_WITHOUT_ROW],
            str(audit.get("reason") or "审计读不出来"),
            promote_when=_COVERAGE_PROMOTE_WHEN,
        )
    else:
        row_tools = {row.tool for row in coverage.rows}
        missing = [
            {
                "tool": tool,
                "governed_pre_tool_use": count,
                "remedy": "给这个工具补覆盖行（channel × tool × mode × check_id），"
                "或在 reason 里说明它按设计不进覆盖表；删行的变异就红在这一格",
            }
            for tool, count in audit["by_tool"].items()
            if tool not in row_tools
        ]
        tool_hits = _cell(
            status=STATUS_AVAILABLE,
            count=len(missing),
            items=missing,
            red_when=_COVERAGE_RED_WHEN[RED_TOOL_WITH_HITS_WITHOUT_ROW],
            note=(
                "判据是**工具级**：审计没有通道字段，所以只要表里任何一行覆盖了这个工具就算有行。"
                "读了 "
                + str(audit.get("records"))
                + " 条记录，其中 governed=true 的 PreToolUse "
                + str(audit.get("governed_pre_tool_use"))
                + " 条（按工具："
                + " / ".join(tool + " " + str(count) for tool, count in audit["by_tool"].items())
                + "）"
            ),
            promote_when=_COVERAGE_PROMOTE_WHEN,
        )

    if registry["status"] != STATUS_AVAILABLE:
        digest: dict = _unavailable_cell(
            _COVERAGE_RED_WHEN[RED_REGISTRY_DIGEST_DRIFT],
            str(registry.get("reason") or "注册表摘要读不出来"),
            promote_when=_COVERAGE_PROMOTE_WHEN,
        )
    elif registry["matches"]:
        digest = _cell(
            status=STATUS_AVAILABLE,
            count=0,
            items=[],
            red_when=_COVERAGE_RED_WHEN[RED_REGISTRY_DIGEST_DRIFT],
            note=(
                "当前摘要 "
                + str(registry["current_digest"])
                + " = 已审核摘要"
                + "（registry_version="
                + str(registry["registry_version"])
                + "）"
            ),
            promote_when=_COVERAGE_PROMOTE_WHEN,
        )
    else:
        digest = _cell(
            status=STATUS_AVAILABLE,
            count=1,
            items=[
                {
                    "current_digest": registry["current_digest"],
                    "approved_digest": registry["approved_digest"],
                    "registry_version": registry["registry_version"],
                    "governance_drift_reason": registry.get("governance_drift_reason"),
                    "remedy": "复核 registry/tool-registry.yaml 后重新审核："
                    "python -m enforcement.cli registry --approve --reviewer <name>",
                }
            ],
            red_when=_COVERAGE_RED_WHEN[RED_REGISTRY_DIGEST_DRIFT],
            note=(
                "已审核摘要为 null 时按漂移处理：没有可比的已审核摘要 = 证明不了注册表被审核过"
            ),
            promote_when=_COVERAGE_PROMOTE_WHEN,
        )

    return {
        RED_ROW_WITHOUT_MODE: _cell(
            status=STATUS_AVAILABLE,
            count=len(absent_mode),
            items=absent_mode,
            red_when=_COVERAGE_RED_WHEN[RED_ROW_WITHOUT_MODE],
            note="读了 " + str(len(enforced)) + " 条 enforced 行",
            promote_when=_COVERAGE_PROMOTE_WHEN,
        ),
        RED_MODE_WITHOUT_CHECK: without_check,
        RED_TOOL_WITH_HITS_WITHOUT_ROW: tool_hits,
        RED_REGISTRY_DIGEST_DRIFT: digest,
    }


# --------------------------------------------------------------------------- 连接键


def build_links(
    *,
    facts: Optional[FactsTable],
    facts_error: Optional[str],
    checks: Optional[isp.ChecksTable],
    checks_error: Optional[str],
) -> dict:
    """连接键**双向必查**（27 号 §3.3）：两格都要有，否则"表里少写几行"就能把方向一凑成 0。

    第三个读数不是红：**没有** covers_facts 的 checks 行数——不给这个计数，
    "这张表今天什么都没连"就一个字都读不出来。
    """

    reason = facts_error or checks_error
    if facts is None or checks is None:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": reason or "facts 表或登记表读不到",
            "fact_without_check": {"count": None, "items": []},
            "check_covers_unknown_fact": {"count": None, "items": []},
            "checks_without_fact_link": None,
            "note": "两格都**未评**（count 是 null，不是 0）：连接键要两张表同时在手才算得出来",
        }
    referenced: dict = {}
    for row in checks.rows:
        for key in row.covers_facts:
            referenced.setdefault(key, []).append(row.check_id)
    uncovered = []
    for row in facts.rows:
        if row.key not in referenced:
            uncovered.append(
                {
                    "key": row.key,
                    "authority": row.authority,
                    "canonical_ref": row.canonical_ref,
                    "remedy": row.remedy,
                }
            )
    unknown_keys = []
    for row in checks.rows:
        for key in row.covers_facts:
            if key not in facts.by_key:
                unknown_keys.append({"check_id": row.check_id, "key": key})
    without_link = [row.check_id for row in checks.rows if not row.covers_facts]
    return {
        "status": STATUS_AVAILABLE,
        "fact_without_check": {"count": len(uncovered), "items": uncovered},
        "check_covers_unknown_fact": {"count": len(unknown_keys), "items": unknown_keys},
        "checks_without_fact_link": len(without_link),
        "checks_without_fact_link_ids": without_link,
        "note": (
            "方向一（fact_without_check）数的是「登记了事实却没有任何检查声明覆盖它」；"
            "方向二（check_covers_unknown_fact）数的是「声明覆盖了一个不存在的事实」——"
            "两者都必须有，只报一个就等于允许用「少写几行」把另一格凑成 0"
        ),
    }

# --------------------------------------------------------------------------- C1 测试路径

# "tests/x.py" 里斜杠的数量：用它数出"直接躺在 tests/ 下"的文件（口径变体的差就差在它们）。
_DIRECTLY_UNDER_TESTS = 1


def cross_source_test_paths(root: Path) -> dict:
    """C1：两份测试路径声明对同一批文件给出的判定（**只做集合差，不合并谓词**）。

    两侧各用它们**现在**的实现：平台侧 validators.registry.load_test_layout 的 is_test；
    Adapter 侧 examples/dsh/dsh-adapter.yaml 的 layer_resolution（命中声明的 test_layer）。
    层级读数用 policy.check.resolve_layer——"层从哪来"只有那一个口径。
    """

    enumeration = (
        "工作树 tests/**/*.py（rglob；与 tests/contract/test_dsh_layer_declaration.py 同口径）"
    )
    try:
        files = sorted(
            path.relative_to(root).as_posix() for path in (root / "tests").rglob("*.py")
        )
        layout = load_test_layout(root=root)
        config = load_config(_example_paths(root)[0])
    except (ValidatorsRegistryError, DshEventError, OSError) as error:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "读不到测试路径的声明：" + type(error).__name__ + "：" + str(error),
            "scanned": None,
            "enumeration": enumeration,
        }
    if config.test_layer is None:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "示例 Adapter 配置没有声明 test_layer：Adapter 侧判不了「是不是测试」",
            "scanned": len(files),
            "enumeration": enumeration,
        }

    platform: dict = {}
    adapter: dict = {}
    for name in files:
        platform[name] = bool(layout.is_test(name))
        adapter[name] = config.layer_resolution(name).layer == config.test_layer
    items = [
        {"path": name, "platform": platform[name], "adapter": adapter[name]}
        for name in files
        if platform[name] != adapter[name]
    ]
    directions = {
        "platform_false_adapter_true": sum(
            1 for item in items if not item["platform"] and item["adapter"]
        ),
        "platform_true_adapter_false": sum(
            1 for item in items if item["platform"] and not item["adapter"]
        ),
    }

    layer_items: list = []
    layer_reason: Optional[str] = None
    for name in files:
        try:
            layer, source = resolve_layer(
                argparse.Namespace(layer=None, config_root=None, workspace=str(root), file=name),
                anchor=root,
                root=root,
                file_path=Path(name),
            )
        except (ValidatorsRegistryError, OSError) as error:
            layer_reason = "层级读数读不到：" + type(error).__name__ + "：" + str(error)
            break
        adapter_layer = config.layer_resolution(name).layer
        if layer != adapter_layer:
            layer_items.append(
                {"path": name, "adapter": adapter_layer, "platform": layer, "source": source}
            )

    directly = [name for name in files if name.count("/") == _DIRECTLY_UNDER_TESTS]
    strict = [item for item in items if item["path"].count("/") != _DIRECTLY_UNDER_TESTS]
    return {
        "status": STATUS_AVAILABLE,
        "scanned": len(files),
        "enumeration": enumeration,
        "disagreement_count": len(items),
        "directions": directions,
        "items": items,
        "semantics_note": (
            "「**/」= 零个或多个目录（validators.globs 的实现口径），本机读数按这个语义算；"
            "把它解释成「至少一段目录」会少掉直接躺在 tests/ 下的那 "
            + str(len(directly))
            + " 个非测试文件（"
            + " / ".join(directly)
            + "），读数变成 "
            + str(len(strict))
            + "。同一个数换个语义就变，所以语义与数必须同框出现（AGENTS 第 48 条）"
        ),
        "directly_under_tests": directly,
        "layer_disagreement": {
            "count": None if layer_reason else len(layer_items),
            "items": layer_items,
            "reason": layer_reason,
            "note": (
                "层级不一致用的是 policy.check.resolve_layer（平台侧）与 layer_resolution"
                "（Adapter 侧）各自的结论；它比判定差集小，因为有文件两边都判「是测试」"
                "却拿到不同的层（例如平台按文件名把 conftest 猜成 test）"
            ),
        },
    }


# --------------------------------------------------------------------------- C2 工具表


def _relation(
    name: str, left: str, right: str, left_items: Sequence[str], right_items: Sequence[str]
) -> dict:
    """一条覆盖关系：两侧的名字集合 + 两个方向的差集。**只给读数**。"""

    left_set = set(left_items)
    right_set = set(right_items)
    return {
        "name": name,
        "left": left,
        "right": right,
        "left_count": len(left_items),
        "right_count": len(right_items),
        "left_only": sorted(left_set - right_set),
        "right_only": sorted(right_set - left_set),
        "both_count": len(left_set & right_set),
    }


def _readers_of(root: Path, literals: Sequence[str]) -> dict:
    """谁在读这几个字面量：在代码与数据根下逐文件找，返回 {literal: [仓库相对路径]}。

    声明处与**本工具自己的源码**不算读取点（见 ORCHESTRATOR_NON_READERS 的注释）。
    读不到的文件跳过（它不是一个"读过"的证据，也不该让整条读数失败）。
    """

    hits: dict = {literal: [] for literal in literals}
    for base in ORCHESTRATOR_SEARCH_ROOTS:
        directory = root / base
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix not in ORCHESTRATOR_SEARCH_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for literal in literals:
                if literal in text:
                    hits[literal].append(_display(path, root=root))
    for literal in hits:
        hits[literal] = [item for item in hits[literal] if item not in ORCHESTRATOR_NON_READERS]
    return hits


def cross_source_tool_tables(root: Path) -> dict:
    """C2：工具表三处声明（注册表 / manifest / 代码工具表）与已审核清单的覆盖关系。

    **本轮不给红条件**（27 号 §3.5）：今天没有一条可评审的判据能说"哪一组差异是缺口"
    ——"manifest 里有、注册表里没有"是设计（只有受治理的工具进注册表），orchestrator 段的
    tool_name ↔ 代码名关系**未核实**。按 AGENTS 第 50 条，没有依据的判定不许造。
    """

    notes: list = []
    try:
        registry_document = yaml.safe_load(
            (root / "registry" / "tool-registry.yaml").read_text(encoding="utf-8")
        )
        registry_tools = registry_document["tools"]
        # 这条提取必须留在同一个 try 里：它是本函数**唯一**直接 item["id"] 的地方（下面 by_agent /
        # orchestrator 两处都用 .get 防御）。放在 try 之外时，一条缺 id 的注册表条目会以 KeyError
        # 逃出去 —— CLI 变成 traceback + 非 0 退出，与本模块"退出码恒 0、读不出来降级为 unavailable"
        # 的口径相反（读数读不出来是显式状态，不是崩溃）。
        registry_ids = [str(item["id"]) for item in registry_tools]
        manifests: dict = {}
        manifest_paths: dict = {}
        for path in sorted((root / "adapters").glob("*/manifest.yaml")):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            manifests[path.parent.name] = sorted(str(item["name"]) for item in document["tools"])
            manifest_paths[path.parent.name] = _display(path, root=root)
        approved_registry = json.loads(
            (root / "registry" / "tool-registry.approved.json").read_text(encoding="utf-8")
        )
        approved_adapters = json.loads(
            (root / "adapters" / "approved.json").read_text(encoding="utf-8")
        )
    except (
        OSError,
        UnicodeDecodeError,
        KeyError,
        TypeError,
        yaml.YAMLError,
        json.JSONDecodeError,
    ) as error:
        # 非 UTF-8 的注册表 / manifest / 已审核清单同样要落到"读不出来"这一档，
        # 而不是以 UnicodeDecodeError 逃出去（C2 的其余读取都在这一个 try 里）。
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "工具表读不出来：" + type(error).__name__ + "：" + str(error),
        }

    by_agent: dict = {}
    for item in registry_tools:
        by_agent.setdefault(str(item.get("agent")), []).append(str(item.get("tool_name")))
    for agent in by_agent:
        by_agent[agent] = sorted(by_agent[agent])
    code_names = sorted(TOOL_TABLE)

    relations = [
        _relation(
            "registry[tools][agent=dsh] ⊆ manifest.dsh",
            "registry/tool-registry.yaml#/tools",
            manifest_paths.get("dsh", "adapters/dsh/manifest.yaml#/tools"),
            by_agent.get("dsh", []),
            manifests.get("dsh", []),
        ),
        _relation(
            "manifest.dsh ↔ 代码工具表",
            manifest_paths.get("dsh", "adapters/dsh/manifest.yaml#/tools"),
            "src/adapters/dsh/adapter.py#TOOL_TABLE",
            manifests.get("dsh", []),
            code_names,
        ),
        _relation(
            "registry ↔ 已审核清单",
            "registry/tool-registry.yaml#/tools",
            "registry/tool-registry.approved.json",
            registry_ids,
            sorted(str(key) for key in approved_registry.get("tools", {})),
        ),
        _relation(
            "adapters/*/manifest.yaml ↔ adapters/approved.json",
            "adapters/*/manifest.yaml",
            "adapters/approved.json",
            sorted(manifests),
            sorted(str(key) for key in approved_adapters.get("adapters", {})),
        ),
    ]

    dsh_only = sorted(set(manifests.get("dsh", [])) - set(by_agent.get("dsh", [])))
    notes.append(
        "manifest(dsh) 里有、注册表里没有的工具 " + str(len(dsh_only)) + " 个：**这是设计**"
        "（只有受治理的那几个进注册表），不是缺口"
    )
    orchestrator = [item for item in registry_tools if item.get("agent") == "orchestrator"]
    readers = _readers_of(root, ORCHESTRATOR_TOOL_NAMES)
    reader_paths = sorted({path for paths in readers.values() for path in paths})
    resolution: dict = {
        "searched_in": list(ORCHESTRATOR_SEARCH_ROOTS),
        "searched_literals": list(ORCHESTRATOR_TOOL_NAMES),
        "non_readers": list(ORCHESTRATOR_NON_READERS),
        "readers": readers,
        "registry_entries": [
            {
                "id": str(item.get("id")),
                "tool_name": str(item.get("tool_name")),
                "risk": str(item.get("risk")),
                "approval": str(item.get("approval")),
            }
            for item in orchestrator
        ],
    }
    if reader_paths:
        resolution["status"] = STATUS_AVAILABLE
        resolution["reason"] = (
            "这些字面量在 " + " / ".join(reader_paths) + " 里被读到——对应关系可评"
        )
    else:
        resolution["status"] = STATUS_UNAVAILABLE
        resolution["reason"] = (
            "查不到："
            + " / ".join(ORCHESTRATOR_TOOL_NAMES)
            + " 这四个 tool_name 在 "
            + " / ".join(ORCHESTRATOR_SEARCH_ROOTS)
            + " 下没有任何读取点（命中的只有注册表自己那四行**声明**）；代码侧引用的是四个 "
            "orc.* **id**（src/orchestration/nodes.py 的 EDIT_TOOL / WRITE_TOOL / "
            "PROTECTED_EDIT_TOOL / PROTECTED_WRITE_TOOL）。按 2026-10-03 裁定④：查不到就写 "
            "unavailable，**不给判据**，也不猜一个对应关系（27 号 §3.5 / §9 第 1 条）"
        )
    resolution["note"] = (
        "只报告：unavailable 说的是「这组对应关系证不出来」，**不是**「注册表写错了」"
        "（那四行条目本身读得到，见 registry_entries）"
    )
    notes.append(
        "orchestrator 段的 tool_name ↔ 代码名关系读作 " + resolution["status"] + "（见 "
        "orchestrator_resolution）；C2 因此**不给判据**"
    )
    return {
        "status": STATUS_AVAILABLE,
        "orchestrator_resolution": resolution,
        "sources": {
            "registry": {
                "path": "registry/tool-registry.yaml",
                "count": len(registry_tools),
                "by_agent": by_agent,
                "ids": registry_ids,
            },
            "manifests": [
                {"agent": agent, "path": manifest_paths[agent], "count": len(manifests[agent])}
                for agent in sorted(manifests)
            ],
            "code_tool_table": {
                "path": "src/adapters/dsh/adapter.py#TOOL_TABLE",
                "count": len(code_names),
            },
            "approved": [
                {
                    "path": "registry/tool-registry.approved.json",
                    "count": len(approved_registry.get("tools", {})),
                    "schema_version": approved_registry.get("approved_schema_version"),
                },
                {
                    "path": "adapters/approved.json",
                    "count": len(approved_adapters.get("adapters", {})),
                    "schema_version": approved_adapters.get("schema_version"),
                },
            ],
        },
        "relations": relations,
        "notes": notes,
    }


# --------------------------------------------------------------------------- C3 预算不等式


def parse_instance(text: str) -> tuple:
    """--instance <config>@<hooks>：实例**只由显式参数**给，不扫目录（27 号 §3.6）。"""

    if text.count("@") != 1:
        raise argparse.ArgumentTypeError("实例要写成 <config>@<hooks>，读到 " + repr(text))
    config_text, hooks_text = text.split("@")
    if not config_text.strip() or not hooks_text.strip():
        raise argparse.ArgumentTypeError("实例的 config 与 hooks 都不能为空，读到 " + repr(text))
    return Path(config_text), Path(hooks_text)


def budget_instance(config_path: Path, hooks_path: Path, *, root: Path) -> dict:
    """一个实例的两段 / 三段读数（判据来自 adapters.dsh.hooks.budget_inequality_facts）。"""

    shared = {
        "instance": _display(config_path, root=root) + "@" + _display(hooks_path, root=root),
        "config": _display(config_path, root=root),
        "hooks_config": _display(hooks_path, root=root),
    }
    try:
        config = load_config(config_path)
    except (DshEventError, OSError) as error:
        return {
            **shared,
            "status": STATUS_UNAVAILABLE,
            "reason": "配置读不出来：" + type(error).__name__ + "：" + str(error),
        }
    facts = dsh_hooks.budget_inequality_facts(config, hooks_config_path=hooks_path)
    two = facts["two_term"]
    pre = config.pre_evidence
    hooks_timeout_ms = two["limit_ms"] if two["limit_source"] == "hooks.json" else None
    return {
        **shared,
        "status": STATUS_AVAILABLE,
        "wiring": facts["wiring"],
        "declared": {
            "internal_budget_ms": config.timeout_ms,
            "hooks_timeout_ms": hooks_timeout_ms,
            "hooks_timeout_source": two["limit_source"] or "unreadable",
            "pre_evidence": {
                "declared": pre is not None,
                "enabled": bool(pre is not None and pre.enabled),
                "timeout_ms": None if pre is None else pre.timeout_ms,
            },
        },
        "two_term": two,
        "three_term": facts["three_term"],
        "note": (
            "两段 / 三段都来自 adapters.dsh.hooks.budget_inequality_facts（一份实现、两个调用点）；"
            "declared.hooks_timeout_ms 是 null 时，hooks.json 里没有可比的 timeout"
            "（两段因此是 unavailable，不是通过）"
        ),
    }


_INVENTORY_NOTE = (
    "adapters.wiring 的 timeout_budget 取的是「进程内插件 timeoutMs 与 hooks.json timeout 的"
    "**最小值**」，**看不到 pre_evidence**——它的 ok=true 不许当三段结论用（27 号 §1.3）；"
    "ok 缺失 = 证明不了（读不到上限或内部预算），**不是** False。matched=null 时说明本次的实例"
    "不是本机的通道：两边并列读，谁也不许替谁下结论"
)


def budget_inventory(root: Path, hooks_rel: str) -> dict:
    """wiring 的通道事实 timeout_budget——与上面那两段**并列**，不合并（27 号 §3.6）。

    这里**不筛通道**：本机有哪些通道就报哪些（带预算读数的那几条）。"匹配不上实例"本身
    是一个必须读出来的事实（仓库内示例不是本机的运行时通道），不是"没有读数"。
    """

    try:
        report = probe_wiring(project_root=root)
    except WiringError as error:
        return {
            "status": STATUS_UNAVAILABLE,
            "channels": [],
            "matched": None,
            "reason": "通道清点跑不起来：" + str(error),
            "note": _INVENTORY_NOTE,
        }
    channels: list = []
    for channel in report.channels:
        budget = dict(channel.timeout_budget)
        if not budget:
            continue
        channels.append(
            {
                "channel_id": channel.channel_id,
                "hooks_config": channel.hooks_config,
                "status": channel.status.value,
                "dsh_side_timeout_ms": budget.get("dsh_side_timeout_ms"),
                "dsh_side_timeout_source": budget.get("dsh_side_timeout_source"),
                "in_process_timeout_ms": budget.get("in_process_timeout_ms"),
                "hooks_config_timeout_ms": budget.get("hooks_config_timeout_ms"),
                "internal_budget_ms": budget.get("internal_budget_ms"),
                "ok": budget.get("ok"),
            }
        )
    if not channels:
        return {
            "status": STATUS_UNAVAILABLE,
            "channels": [],
            "matched": None,
            "reason": "本机通道清点里没有任何通道带得出预算读数（dsh 根缺失或没有通道声明）",
            "note": _INVENTORY_NOTE,
        }
    matched = next((item for item in channels if item["hooks_config"] == hooks_rel), None)
    return {
        "status": STATUS_AVAILABLE,
        "channels": channels,
        "matched": matched,
        "matched_hooks_config": hooks_rel,
        "note": _INVENTORY_NOTE,
    }


def cross_source_budget(root: Path, *, extra_instances: Sequence[tuple]) -> dict:
    """C3：预算不等式两套结论（仓库内 examples/dsh 恒读 + 显式给的实例）。"""

    pairs = [_example_paths(root), *extra_instances]
    rendered = [
        budget_instance(config_path, hooks_path, root=root)
        for config_path, hooks_path in pairs
    ]
    inventory = budget_inventory(root, _display(_example_paths(root)[1], root=root))
    violated = [
        {
            "instance": item["instance"],
            "term": term,
            "status": item[term]["status"],
            "reason": item[term]["reason"],
        }
        for item in rendered
        if item["status"] == STATUS_AVAILABLE
        for term in ("two_term", "three_term")
        if item[term]["status"] == "violated"
    ]
    return {
        "status": STATUS_AVAILABLE,
        "instances": rendered,
        "inventory_fact": inventory,
        "violated": violated,
        "note": (
            "实例从哪来：仓库内 examples/dsh **恒读**；其他实例只由 --instance 显式给"
            "（不扫目录——扫 .tmp 会把环境残渣读成事实，AGENTS 核心约束 6）"
        ),
    }

# --------------------------------------------------------------------------- 只报告的表达


_RED_WHEN = {
    RED_FACT_WITHOUT_CHECK: (
        "facts 表里的 key 没有任何 checks 行用 covers_facts 引用它（连接方向一）"
    ),
    RED_CHECK_COVERS_UNKNOWN_FACT: (
        "checks 行的 covers_facts 引用了 facts 表里不存在的 key（连接方向二）"
    ),
    RED_TEST_PATH_DECLARATION: (
        "两份测试路径声明对同一个文件给出不同判定（平台 test_patterns / Adapter test_paths）"
    ),
    RED_BUDGET_INEQUALITY: "声明的那个预算不等式被违反（内部预算 + 取证预算 不小于 dsh 侧超时）",
}


def _tally(values: Sequence) -> dict:
    """按值计数（键排序，读数稳定）。"""

    tally: dict = {}
    for value in values:
        tally[str(value)] = tally.get(str(value), 0) + 1
    return dict(sorted(tally.items()))


def _cell(
    *,
    status: str,
    count: Optional[int],
    items: Sequence,
    red_when: str,
    note: str,
    reason: Optional[str] = None,
    promote_when: str = _PROMOTE_WHEN,
) -> dict:
    """一格红条件——与 adapters.cli wiring / tools/instrument_self_proof.py **逐字同形**。

    三态（available / unavailable / not_applicable）都必须能读：后两种的 count 是 null，
    **不是 0**；not_applicable 是"这条路径上没有这个输入"，不是"未评"。
    """

    cell: dict = {
        "status": status,
        "count": count if status == STATUS_AVAILABLE else None,
        "items": list(items) if status == STATUS_AVAILABLE else [],
        "is_red": bool(count) if status == STATUS_AVAILABLE else False,
        "red_when": red_when,
        "enforced": False,
        "would_exit_code": 1,
        "promote_when": promote_when,
        "note": note,
    }
    if status == STATUS_UNAVAILABLE:
        cell["reason"] = reason
        cell["note"] = note + "；这一格是**未评**（count 是 null，不是 0）——未评不是不红"
    elif status == STATUS_NOT_APPLICABLE:
        cell["reason"] = reason
        cell["note"] = note + "；这一格是**不适用**（count 是 null，不是 0）——不适用不是 0 命中"
    return cell


def _unavailable_cell(
    red_when: str, reason: str, *, promote_when: str = _PROMOTE_WHEN
) -> dict:
    return _cell(
        status=STATUS_UNAVAILABLE,
        count=None,
        items=[],
        red_when=red_when,
        note=_REPORT_ONLY_NOTE,
        reason=reason,
        promote_when=promote_when,
    )


# --------------------------------------------------------------------------- 载荷


def evaluate(
    *,
    repo: Path = REPO,
    facts_path: Path = DEFAULT_FACTS,
    checks_path: Path = DEFAULT_CHECKS,
    coverage_path: Path = DEFAULT_COVERAGE,
    audit_path: Optional[Path] = None,
    extra_instances: Sequence[tuple] = (),
) -> dict:
    """把 facts 表、登记表、连接键、三组跨源读数与 C4 覆盖账算成一份载荷。

    判据只有这一个实现；读不出来的输入一律降级成 unavailable / not_applicable（**不抛**）。
    """

    facts_display = _display(facts_path, root=repo)
    try:
        facts = load_facts(facts_path, display=facts_display)
        facts_error = None
    except FactsTableError as error:
        facts, facts_error = None, str(error)
    checks_display = _display(checks_path, root=repo)
    try:
        checks = isp.load_checks(checks_path, display=checks_display)
        checks_error = None
    except isp.InstrumentChecksError as error:
        checks, checks_error = None, str(error)

    facts_table: dict = {
        "status": STATUS_AVAILABLE if facts is not None else STATUS_UNAVAILABLE,
        "path": facts_display,
        "schema_version": None if facts is None else facts.schema_version,
        "rows": None if facts is None else len(facts.rows),
    }
    if facts_error is not None:
        facts_table["reason"] = facts_error
    facts_block = {
        "table": facts_table,
        "rows": [] if facts is None else [row.to_dict() for row in facts.rows],
        "counts": None
        if facts is None
        else {
            "rows": len(facts.rows),
            "by_authority": _tally([row.authority for row in facts.rows]),
            "by_severity": _tally([row.severity for row in facts.rows]),
            "by_on_unprovable": _tally([row.on_unprovable for row in facts.rows]),
            "with_expires": len([row for row in facts.rows if row.expires]),
        },
    }

    checks_table: dict = {
        "status": STATUS_AVAILABLE if checks is not None else STATUS_UNAVAILABLE,
        "path": checks_display,
        "schema_version": None if checks is None else checks.schema_version,
        "rows": None if checks is None else len(checks.rows),
    }
    if checks_error is not None:
        checks_table["reason"] = checks_error
    checks_block: dict = {
        "table": checks_table,
        "counts": None,
        "namespaces": {},
        "rows_with_facts": [],
    }
    if checks is not None:
        with_facts = [row for row in checks.rows if row.covers_facts]
        checks_block["counts"] = {
            "rows": len(checks.rows),
            "with_covers_facts": len(with_facts),
            "without_covers_facts": len(checks.rows) - len(with_facts),
        }
        checks_block["namespaces"] = _tally([row.check_id.split(":")[0] for row in checks.rows])
        checks_block["rows_with_facts"] = [
            {"check_id": row.check_id, "covers_facts": list(row.covers_facts)} for row in with_facts
        ]

    coverage_display = _display(coverage_path, root=repo)
    try:
        coverage = load_coverage(coverage_path, display=coverage_display)
        coverage_error = None
    except CoverageTableError as error:
        coverage, coverage_error = None, str(error)
    try:
        wiring_scope = load_wiring_scope(repo / "adapters" / "wiring-scope.yaml")
        wiring_error = None
    except WiringScopeError as error:
        wiring_scope, wiring_error = None, str(error)
    audit = read_governed_audit(audit_path, root=repo)
    registry_digest = registry_digest_reading(repo)
    references = build_coverage_references(
        coverage=coverage,
        coverage_error=coverage_error,
        declared_ids=(
            None if wiring_scope is None else {entry.id for entry in wiring_scope.scope}
        ),
        declared_error=wiring_error,
        check_ids=None if checks is None else {row.check_id for row in checks.rows},
        checks_error=checks_error,
        fact_keys=None if facts is None else set(facts.by_key),
        facts_error=facts_error,
    )
    coverage_red = build_coverage_red_conditions(
        coverage=coverage,
        coverage_error=coverage_error,
        checks=checks,
        checks_error=checks_error,
        audit=audit,
        registry=registry_digest,
    )

    coverage_table: dict = {
        "status": STATUS_AVAILABLE if coverage is not None else STATUS_UNAVAILABLE,
        "path": coverage_display,
        "schema_version": None if coverage is None else coverage.schema_version,
        "rows": None if coverage is None else len(coverage.rows),
    }
    if coverage_error is not None:
        coverage_table["reason"] = coverage_error
    coverage_counts = None
    if coverage is not None:
        declared_uncovered = [row for row in coverage.rows if row.coverage == "declared_uncovered"]
        coverage_counts = {
            "rows": len(coverage.rows),
            "by_coverage": _tally([row.coverage for row in coverage.rows]),
            "by_mode": _tally([row.mode if row.mode else "<missing>" for row in coverage.rows]),
            "by_channel": _tally([row.channel for row in coverage.rows]),
            "by_tool": _tally([row.tool for row in coverage.rows]),
            "with_check_id": len([row for row in coverage.rows if row.check_id]),
            "enforced": len([row for row in coverage.rows if row.coverage == "enforced"]),
            "declared_uncovered": len(declared_uncovered),
            "declared_uncovered_with_expires": len(
                [row for row in declared_uncovered if row.expires_at]
            ),
            "with_covers_facts": len([row for row in coverage.rows if row.covers_facts]),
        }
    coverage_block = {
        "table": coverage_table,
        "rows": [] if coverage is None else [row.to_dict() for row in coverage.rows],
        "counts": coverage_counts,
        "audit": audit,
        "registry_digest": registry_digest,
        "references": references,
        "red_conditions": coverage_red,
        "note": (
            "C4 通道覆盖账：表是 validation/channel-coverage.yaml（自带 schema_version 「1」），"
            "四格红键在这个块里（与顶层四格并列，不混用）；引用完整性是独立读数。"
            "审计只由 --audit 显式给：不给 = not_applicable，读不了 = unavailable，都不写 0。"
            "整块只报告：不改任何 allow / block，也不接退出码"
        ),
    }

    links = build_links(
        facts=facts, facts_error=facts_error, checks=checks, checks_error=checks_error
    )
    test_paths = cross_source_test_paths(repo)
    tool_tables = cross_source_tool_tables(repo)
    budget = cross_source_budget(repo, extra_instances=extra_instances)

    red_conditions: dict = {}
    if links["status"] != STATUS_AVAILABLE:
        reason = str(links.get("reason", ""))
        red_conditions[RED_FACT_WITHOUT_CHECK] = _unavailable_cell(
            _RED_WHEN[RED_FACT_WITHOUT_CHECK], reason
        )
        red_conditions[RED_CHECK_COVERS_UNKNOWN_FACT] = _unavailable_cell(
            _RED_WHEN[RED_CHECK_COVERS_UNKNOWN_FACT], reason
        )
    else:
        red_conditions[RED_FACT_WITHOUT_CHECK] = _cell(
            status=STATUS_AVAILABLE,
            count=links["fact_without_check"]["count"],
            items=links["fact_without_check"]["items"],
            red_when=_RED_WHEN[RED_FACT_WITHOUT_CHECK],
            note=(
                "登记了事实、却没有任何检查声明覆盖它。**今天这一格不是 0**：把本工具接成"
                "只报告步骤的那次提交（CI 线；交接清单见 tools/README.md 与 23 号 §21）会给"
                "台阶 5 的报告行写上 covers_facts，那时这一格才回到 0——在那之前照实报"
            ),
        )
        red_conditions[RED_CHECK_COVERS_UNKNOWN_FACT] = _cell(
            status=STATUS_AVAILABLE,
            count=links["check_covers_unknown_fact"]["count"],
            items=links["check_covers_unknown_fact"]["items"],
            red_when=_RED_WHEN[RED_CHECK_COVERS_UNKNOWN_FACT],
            note="声明覆盖了一个 facts 表里不存在的事实：拼错一个 key 就会命中这一格",
        )

    if test_paths["status"] != STATUS_AVAILABLE:
        red_conditions[RED_TEST_PATH_DECLARATION] = _unavailable_cell(
            _RED_WHEN[RED_TEST_PATH_DECLARATION], str(test_paths.get("reason", ""))
        )
    else:
        red_conditions[RED_TEST_PATH_DECLARATION] = _cell(
            status=STATUS_AVAILABLE,
            count=test_paths["disagreement_count"],
            items=test_paths["items"],
            red_when=_RED_WHEN[RED_TEST_PATH_DECLARATION],
            note=(
                "**不合并谓词**（27 号 §5 第 1 条）：降到 0 只有两条路（合并谓词 / 改声明），"
                "两条都不在本轮。这一格是只报告，不是修复"
            ),
        )

    readable = [item for item in budget["instances"] if item["status"] == STATUS_AVAILABLE]
    if not readable:
        red_conditions[RED_BUDGET_INEQUALITY] = _unavailable_cell(
            _RED_WHEN[RED_BUDGET_INEQUALITY], "没有任何预算实例读得出来（配置或 hooks.json 读不到）"
        )
    else:
        red_conditions[RED_BUDGET_INEQUALITY] = _cell(
            status=STATUS_AVAILABLE,
            count=len(budget["violated"]),
            items=budget["violated"],
            red_when=_RED_WHEN[RED_BUDGET_INEQUALITY],
            note=(
                "只报「声明的那个不等式」被违反；真正的执行在 check_wiring 自己的调用点上"
                "（这一格 enforced=false 的理由）。读了 "
                + str(len(readable))
                + " 个实例，wiring 的 timeout_budget 与两段**并列**给出、不合并"
            ),
        )

    payload = {
        "schema_version": CONTROL_PLANE_FACTS_SCHEMA_VERSION,
        "mode": "report-only",
        "note": (
            "只报告：退出码恒为 0，不改任何 allow / block，也不接进本机门禁；"
            "四格红条件的 enforced=false + would_exit_code=1 是**预注册**，不是承诺"
        ),
        "reading_context": reading.build(
            source=reading.SOURCE_GATE,
            tree=reading.tree_block(repo),
            declarations={
                reading.DECLARATION_CONTROL_PLANE_FACTS: reading.declaration_block(
                    facts_path, root=repo
                ),
                reading.DECLARATION_INSTRUMENT_CHECKS: reading.declaration_block(
                    checks_path, root=repo
                ),
            },
            host=reading.host_block(),
        ),
        "facts": facts_block,
        "checks_table": checks_block,
        "links": links,
        "coverage": coverage_block,
        "cross_source": {
            "test_paths": test_paths,
            "tool_tables": tool_tables,
            "budget": budget,
        },
        "red_conditions": red_conditions,
    }
    payload["headline"] = {"text": _headline_text(payload), "machine_line": machine_line(payload)}
    return payload


# --------------------------------------------------------------------------- 机器行


def _lookup(payload: dict, key: str) -> str:
    cell = payload["red_conditions"][key]
    if cell["status"] != STATUS_AVAILABLE:
        return "unavailable"
    return str(cell["count"])


def _coverage_lookup(payload: dict, key: str) -> str:
    """C4 四格的机器读数：三态各写各的，**不把 not_applicable 读成 unavailable 或 0**。"""

    cell = payload["coverage"]["red_conditions"][key]
    if cell["status"] == STATUS_NOT_APPLICABLE:
        return "not_applicable"
    if cell["status"] != STATUS_AVAILABLE:
        return "unavailable"
    return str(cell["count"])


def _rows_text(value: Optional[int]) -> str:
    return "unavailable" if value is None else str(value)


def machine_line(payload: dict) -> str:
    """机器行（跨文件契约）：既有四格 + C4 四格 + 覆盖表行数 / 引用断开数 / 审计状态。

    既有四格的位置一个都没变（契约尾巴仍是 checks=<n>）；C4 四格**另立一段**：
    key 名不同，且多一个 not_applicable 状态。
    """

    coverage = payload["coverage"]
    return (
        "CONTROL_PLANE_FACTS: "
        + " ".join(key + "=" + _lookup(payload, key) for key in RED_KEYS)
        + " / "
        + " ".join(key + "=" + _coverage_lookup(payload, key) for key in COVERAGE_RED_KEYS)
        + " / coverage_rows="
        + _rows_text(coverage["table"]["rows"])
        + " references="
        + _rows_text(coverage["references"]["total"])
        + " audit="
        + str(coverage["audit"]["status"])
        + " / facts="
        + _rows_text(payload["facts"]["table"]["rows"])
        + " checks="
        + _rows_text(payload["checks_table"]["table"]["rows"])
    )


def hits_line(payload: dict) -> str:
    """HITS: 机器行（**跨文件契约**）：ci_local.report_only_reading() 读的就是它。

    形状与 tools/exemption_expiry.py / tools/instrument_self_proof.py 的 HITS: 行同族：
    HITS: <合计> / <逐项> / facts=<n> checks=<n>。

    **合计仍是既有四格之和**：跨文件契约的既有含义一个字都不改（读取器只要求行首是一个
    整数或 unavailable）。C4 四格作为**逐项**追加在后面——不给 --audit 时其中一格是
    not_applicable，把它并进合计会让默认输出天天写 unavailable，那等于把一个"不适用"
    读成"整条读数坏了"。C4 的合计由 coverage_rows / references 与载荷自己表达。

    任一既有格未评 → 写 unavailable，读取器照原文给出读数、不猜命中数（未评不是 0）。
    """

    cells = [payload["red_conditions"][key] for key in RED_KEYS]
    total = (
        "unavailable"
        if any(cell["status"] != STATUS_AVAILABLE for cell in cells)
        else str(sum(int(cell["count"]) for cell in cells))
    )
    coverage = payload["coverage"]
    return (
        "HITS: "
        + total
        + " / "
        + " ".join(key + "=" + _lookup(payload, key) for key in RED_KEYS)
        + " / "
        + " ".join(key + "=" + _coverage_lookup(payload, key) for key in COVERAGE_RED_KEYS)
        + " / coverage_rows="
        + _rows_text(coverage["table"]["rows"])
        + " references="
        + _rows_text(coverage["references"]["total"])
        + " facts="
        + _rows_text(payload["facts"]["table"]["rows"])
        + " checks="
        + _rows_text(payload["checks_table"]["table"]["rows"])
    )


def _headline_text(payload: dict) -> str:
    facts_rows = payload["facts"]["table"]["rows"]
    checks_rows = payload["checks_table"]["table"]["rows"]
    links = payload["links"]
    budget = payload["cross_source"]["budget"]
    readable = [item for item in budget["instances"] if item["status"] == STATUS_AVAILABLE]
    return (
        "控制面事实 × 跨源互证：facts "
        + _rows_text(facts_rows)
        + " 行 / 登记表 "
        + _rows_text(checks_rows)
        + " 行；连接键 fact_without_check="
        + _lookup(payload, RED_FACT_WITHOUT_CHECK)
        + "、check_covers_unknown_fact="
        + _lookup(payload, RED_CHECK_COVERS_UNKNOWN_FACT)
        + "、checks_without_fact_link="
        + _rows_text(links.get("checks_without_fact_link"))
        + "；C1 不一致 "
        + _lookup(payload, RED_TEST_PATH_DECLARATION)
        + "、C3 违反 "
        + _lookup(payload, RED_BUDGET_INEQUALITY)
        + "（预算实例 "
        + str(len(readable))
        + " / "
        + str(len(budget["instances"]))
        + " 读得出来）；C4 覆盖表 "
        + _rows_text(payload["coverage"]["table"]["rows"])
        + " 行（引用断开 "
        + _rows_text(payload["coverage"]["references"]["total"])
        + "、审计 "
        + str(payload["coverage"]["audit"]["status"])
        + "）；覆盖四格 row_without_mode="
        + _coverage_lookup(payload, RED_ROW_WITHOUT_MODE)
        + " mode_without_check="
        + _coverage_lookup(payload, RED_MODE_WITHOUT_CHECK)
        + " tool_with_hits_without_row="
        + _coverage_lookup(payload, RED_TOOL_WITH_HITS_WITHOUT_ROW)
        + " registry_digest_drift="
        + _coverage_lookup(payload, RED_REGISTRY_DIGEST_DRIFT)
        + "——全部只报告"
    )


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="控制面事实表 × 跨源互证（台阶 5，只报告）")
    parser.add_argument(
        "--facts",
        default=str(DEFAULT_FACTS),
        help="facts 表（默认 validation/control-plane-facts.yaml）",
    )
    parser.add_argument(
        "--checks",
        default=str(DEFAULT_CHECKS),
        help="检查登记表（默认 validation/instrument-checks.yaml）",
    )
    parser.add_argument(
        "--coverage",
        default=str(DEFAULT_COVERAGE),
        help="通道覆盖表（默认 validation/channel-coverage.yaml）",
    )
    parser.add_argument(
        "--audit",
        default=None,
        metavar="PATH",
        help=(
            "受治理审计 JSONL（只数 governed=true 的 PreToolUse）。不给 = not_applicable，"
            "读不了 = unavailable，**两者都不是 0 命中**；读数里只写脱敏后的展示路径"
        ),
    )
    parser.add_argument(
        "--instance",
        action="append",
        type=parse_instance,
        metavar="CONFIG@HOOKS",
        help="显式给的预算实例（可重复；仓库内 examples/dsh 恒读）",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读载荷")
    return parser



def _orchestrator_relation_line(tool_tables: dict) -> str:
    """C2 里那行人类输出：状态与括注**都**取自算出来的 resolution。

    旧实现把括注写死成"查实：四个 tool_name … 下没有读取点"，于是 status=available
    （真的读到了读取点）时，同一行自相矛盾：状态说读到了、括注说没读到。
    """

    resolution = tool_tables["orchestrator_resolution"]
    return (
        "  C2 orchestrator 关系: "
        + str(resolution["status"])
        + "（"
        + str(resolution["reason"])
        + "）"
    )

def _print_human_cell(key: str, cell: dict) -> None:
    """人类输出的一格：三态各有自己的标签（不适用 / 未评 / 红|ok）。

    `is_red` 在未评与不适用时恒为 False；印成 `[ok]` 会把"没有证据说它红"读成"通过"
    ——与机器行里的 unavailable / not_applicable 自相矛盾。
    """

    if cell["status"] == STATUS_NOT_APPLICABLE:
        print("  [不适用] " + key + ": not_applicable（" + str(cell.get("reason") or "") + "）")
        return
    if cell["status"] != STATUS_AVAILABLE:
        print("  [未评] " + key + ": unavailable")
        return
    print("  [" + ("红" if cell["is_red"] else "ok") + "] " + key + ": " + str(cell["count"]))


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    payload = evaluate(
        facts_path=Path(args.facts),
        checks_path=Path(args.checks),
        coverage_path=Path(args.coverage),
        audit_path=Path(args.audit) if args.audit else None,
        extra_instances=tuple(args.instance or ()),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    facts_block = payload["facts"]
    checks_block = payload["checks_table"]
    links = payload["links"]
    test_paths = payload["cross_source"]["test_paths"]
    tool_tables = payload["cross_source"]["tool_tables"]
    budget = payload["cross_source"]["budget"]
    counts = checks_block["counts"]

    print("控制面事实 × 跨源互证（只报告：退出码恒为 0，不接任何退出码）")
    print(
        "  facts 表: "
        + str(facts_block["table"]["path"])
        + "（"
        + str(facts_block["table"]["status"])
        + "，"
        + _rows_text(facts_block["table"]["rows"])
        + " 行）"
    )
    print(
        "  登记表: "
        + str(checks_block["table"]["path"])
        + "（"
        + str(checks_block["table"]["status"])
        + "，"
        + _rows_text(checks_block["table"]["rows"])
        + " 行）"
    )
    if counts is None:
        print("  连接键: unavailable（两张表没能同时在手）")
    else:
        print(
            "  连接键: 声明了 covers_facts 的行 "
            + str(counts["with_covers_facts"])
            + " / 没有的 "
            + str(counts["without_covers_facts"])
            + "；方向一 "
            + _lookup(payload, RED_FACT_WITHOUT_CHECK)
            + "、方向二 "
            + _lookup(payload, RED_CHECK_COVERS_UNKNOWN_FACT)
            + "、没有声明连接的 "
            + _rows_text(links.get("checks_without_fact_link"))
        )
    if test_paths["status"] == STATUS_AVAILABLE:
        print(
            "  C1 测试路径: 扫描 "
            + str(test_paths["scanned"])
            + " 个文件；判定不一致 "
            + str(test_paths["disagreement_count"])
            + "（platform=False/adapter=True "
            + str(test_paths["directions"]["platform_false_adapter_true"])
            + "、反向 "
            + str(test_paths["directions"]["platform_true_adapter_false"])
            + "）/ 层级不一致 "
            + _rows_text(test_paths["layer_disagreement"]["count"])
        )
    else:
        print("  C1 测试路径: unavailable（" + str(test_paths.get("reason", "")) + "）")
    if tool_tables["status"] == STATUS_AVAILABLE:
        registry = tool_tables["sources"]["registry"]
        print(
            "  C2 工具表: registry "
            + str(registry["count"])
            + "（"
            + " / ".join(
                agent + " " + str(len(names)) for agent, names in registry["by_agent"].items()
            )
            + "）、manifests "
            + " / ".join(
                item["agent"] + " " + str(item["count"])
                for item in tool_tables["sources"]["manifests"]
            )
            + "、代码工具表 "
            + str(tool_tables["sources"]["code_tool_table"]["count"])
        )
        print(_orchestrator_relation_line(tool_tables))
    else:
        print("  C2 工具表: unavailable（" + str(tool_tables.get("reason", "")) + "）")
    readable_instances = [
        item for item in budget["instances"] if item["status"] == STATUS_AVAILABLE
    ]
    print(
        "  C3 预算: 实例 "
        + str(len(readable_instances))
        + " / "
        + str(len(budget["instances"]))
        + " 读得出来"
        + "".join(
            "；"
            + item["instance"]
            + " 两段="
            + item["two_term"]["status"]
            + " 三段="
            + item["three_term"]["status"]
            for item in readable_instances
        )
        + "；wiring 通道预算 "
        + _rows_text(len(budget["inventory_fact"]["channels"]))
        + " 条（matched="
        + str(budget["inventory_fact"]["matched"] is not None)
        + "）"
    )
    coverage = payload["coverage"]
    coverage_table = coverage["table"]
    coverage_counts = coverage["counts"]
    print(
        "  C4 覆盖表: "
        + str(coverage_table["path"])
        + "（"
        + str(coverage_table["status"])
        + "，"
        + _rows_text(coverage_table["rows"])
        + " 行）"
    )
    if coverage_counts is None:
        print("  C4 覆盖账: unavailable（" + str(coverage_table.get("reason", "")) + "）")
    else:
        print(
            "  C4 覆盖分档: "
            + " / ".join(
                name + " " + str(value)
                for name, value in coverage_counts["by_coverage"].items()
            )
            + "；mode "
            + " / ".join(
                name + " " + str(value) for name, value in coverage_counts["by_mode"].items()
            )
        )
    audit = coverage["audit"]
    print(
        "  C4 审计: "
        + str(audit["status"])
        + "（"
        + str(audit.get("path") or "未给 --audit")
        + "；governed PreToolUse "
        + _rows_text(audit.get("governed_pre_tool_use"))
        + " 条 / 记录 "
        + _rows_text(audit.get("records"))
        + " 条）"
    )
    registry = coverage["registry_digest"]
    print(
        "  C4 注册表摘要: "
        + str(registry["status"])
        + (
            "；matches=" + str(registry["matches"])
            if registry["status"] == STATUS_AVAILABLE
            else "（" + str(registry.get("reason", "")) + "）"
        )
    )
    references = coverage["references"]
    print(
        "  C4 引用完整性: "
        + _rows_text(references["total"])
        + "（channel "
        + _rows_text(references["channel"]["count"])
        + " / tool "
        + _rows_text(references["tool"]["count"])
        + " / check_id "
        + _rows_text(references["check_id"]["count"])
        + " / covers_facts "
        + _rows_text(references["covers_facts"]["count"])
        + "）"
    )
    # 人类输出只报计数（2026-10-03 裁定第 3 条的同一条口径）：逐条明细只在 --json 里。
    for key in RED_KEYS:
        _print_human_cell(key, payload["red_conditions"][key])
    for key in COVERAGE_RED_KEYS:
        _print_human_cell(key, coverage["red_conditions"][key])
    print("  " + payload["headline"]["machine_line"])
    print("  " + hits_line(payload))
    print("  " + payload["headline"]["text"])
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())

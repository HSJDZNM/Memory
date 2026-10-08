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

CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.0"——本载荷**第一次出现就带轴**，同批登记进
AGENTS.md 第 55 条那张表。facts 表自己的轴是 FACTS_TABLE_SCHEMA_VERSION = "1"。
**既有载荷一个键都不加**：R-h 那个载荷（INSTRUMENT_SELF_PROOF_SCHEMA_VERSION）的 HITS: 行
已经是 26 号交接给 CI 线的**跨文件契约**，动它等于让正在接线的 CI 线返工；本载荷自带轴、
自带 HITS: 行，ci_local.report_only_reading() **一个字都不用改**。

只报告期怎么表达
================

- 每格红条件与 adapters.cli wiring / tools/instrument_self_proof.py **逐字同形**：
  status / count / items[] / is_red / red_when / enforced: false / would_exit_code: 1 /
  promote_when / note（读到未评时另加 reason）；
- "未评"写 unavailable + reason，count 写 **null 不是 0**（AGENTS 第 56 条）；
- 两条机器行：CONTROL_PLANE_FACTS: ...（本工具自己的读数）与
  HITS: <四格合计> / ...（跨文件契约，与 exemption_expiry / instrument_self_proof 同族）。

实例从哪来（显式，不扫目录）
============================

仓库内实例 examples/dsh/ **恒读**；其他实例只由 --instance <config>@<hooks> 显式给
（27 号 §3.6）。**不扫 .tmp**：扫目录会把环境残渣读成事实，而且 cleanup.py 之后它们
就不存在了（AGENTS 核心约束 6：不得根据目录推断上下文）。

用法
====

    python tools/control_plane_facts.py [--json] [--facts PATH] [--checks PATH]
                                        [--instance <config>@<hooks>]...
"""

from __future__ import annotations

import argparse
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
from policy.check import resolve_layer  # noqa: E402
from provenance import reading_context as reading  # noqa: E402
from validators.registry import RegistryError, load_test_layout  # noqa: E402

# 本载荷的版本轴（AGENTS 第 55 条；**首次出现就带轴**）。
CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.0"
# facts 表自己的版本轴（数据文件，与上面的载荷轴各走各的）。
FACTS_TABLE_SCHEMA_VERSION = "1"

DEFAULT_FACTS = REPO / "validation" / "control-plane-facts.yaml"
DEFAULT_CHECKS = isp.DEFAULT_CHECKS
EXAMPLE_CONFIG = REPO / "examples" / "dsh" / "dsh-adapter.yaml"
EXAMPLE_HOOKS = REPO / "examples" / "dsh" / "hooks.json"

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
        config = load_config(EXAMPLE_CONFIG)
    except (RegistryError, DshEventError, OSError) as error:
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
        except (RegistryError, OSError) as error:
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

    registry_ids = [str(item["id"]) for item in registry_tools]
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

    pairs = [(EXAMPLE_CONFIG, EXAMPLE_HOOKS), *extra_instances]
    rendered = [
        budget_instance(config_path, hooks_path, root=root)
        for config_path, hooks_path in pairs
    ]
    inventory = budget_inventory(root, _display(EXAMPLE_HOOKS, root=root))
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
) -> dict:
    """一格红条件——与 adapters.cli wiring / tools/instrument_self_proof.py **逐字同形**。"""

    cell: dict = {
        "status": status,
        "count": count if status == STATUS_AVAILABLE else None,
        "items": list(items) if status == STATUS_AVAILABLE else [],
        "is_red": bool(count) if status == STATUS_AVAILABLE else False,
        "red_when": red_when,
        "enforced": False,
        "would_exit_code": 1,
        "promote_when": _PROMOTE_WHEN,
        "note": note,
    }
    if status == STATUS_UNAVAILABLE:
        cell["reason"] = reason
        cell["note"] = note + "；这一格是**未评**（count 是 null，不是 0）——未评不是不红"
    return cell


def _unavailable_cell(red_when: str, reason: str) -> dict:
    return _cell(
        status=STATUS_UNAVAILABLE,
        count=None,
        items=[],
        red_when=red_when,
        note=_REPORT_ONLY_NOTE,
        reason=reason,
    )


# --------------------------------------------------------------------------- 载荷


def evaluate(
    *,
    repo: Path = REPO,
    facts_path: Path = DEFAULT_FACTS,
    checks_path: Path = DEFAULT_CHECKS,
    extra_instances: Sequence[tuple] = (),
) -> dict:
    """把 facts 表、登记表、连接键与三组跨源读数算成一份载荷（判据只有这一个实现）。"""

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


def _rows_text(value: Optional[int]) -> str:
    return "unavailable" if value is None else str(value)


def machine_line(payload: dict) -> str:
    """机器行（跨文件契约）：四格计数 + facts 行数 / 登记表行数；未评写 unavailable，不写 0。"""

    return (
        "CONTROL_PLANE_FACTS: "
        + " ".join(key + "=" + _lookup(payload, key) for key in RED_KEYS)
        + " / facts="
        + _rows_text(payload["facts"]["table"]["rows"])
        + " checks="
        + _rows_text(payload["checks_table"]["table"]["rows"])
    )


def hits_line(payload: dict) -> str:
    """HITS: 机器行（**跨文件契约**）：ci_local.report_only_reading() 读的就是它。

    形状与 tools/exemption_expiry.py / tools/instrument_self_proof.py 的 HITS: 行同族：
    HITS: <四格合计> / <四格逐项> / facts=<n> checks=<n>。任一格未评 → 写 unavailable，
    读取器照原文给出读数、不猜命中数（与"未评不是 0"同一条口径）。
    """

    cells = [payload["red_conditions"][key] for key in RED_KEYS]
    total = (
        "unavailable"
        if any(cell["status"] != STATUS_AVAILABLE for cell in cells)
        else str(sum(int(cell["count"]) for cell in cells))
    )
    return (
        "HITS: "
        + total
        + " / "
        + " ".join(key + "=" + _lookup(payload, key) for key in RED_KEYS)
        + " / facts="
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
        + " 读得出来）——全部只报告"
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

def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    payload = evaluate(
        facts_path=Path(args.facts),
        checks_path=Path(args.checks),
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
    # 人类输出只报计数（2026-10-03 裁定第 3 条的同一条口径）：逐条明细只在 --json 里。
    for key in RED_KEYS:
        cell = payload["red_conditions"][key]
        mark = "unavailable" if cell["status"] != STATUS_AVAILABLE else str(cell["count"])
        print("  [" + ("红" if cell["is_red"] else "ok") + "] " + key + ": " + mark)
    print("  " + payload["headline"]["machine_line"])
    print("  " + hits_line(payload))
    print("  " + payload["headline"]["text"])
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())

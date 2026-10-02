r"""仪器自证（**只报告**）：每条仪器检查都要能证明自己会红。

它是谁、为什么要有它
====================

方案 §5.1 的 J5：**每条新检查都必须能证明自己会红**，否则不计入覆盖；而且
「既无 `mutation_id` 又无 `gap_note` → 红」这条要求本身要被一条检查守住。
本工具就是那条检查的**只报告**形态（设计稿 = 25 号，落地取 25 号 §7 的方案 A）。

对象是**平台自己的仪器**（四族，逐条可枚举）：

| 族 | 来源 | 口径 |
| --- | --- | --- |
| 门禁步骤 | `.github/workflows/*.yml` 里带非空 run 块的步骤 | 名字即身份 |
| 治理缺口探针 | `tools/governance_gap_probe.py` 的 CHECKS 常量 | 取每条 check 自己的 id 字面量 |
| 判据级封条场景 | `tools/provenance_loop.py` 的 SCENARIOS 常量 | 取每个场景自己声明的 id 字面量 |
| 本机只报告步骤 | `tools/ci_local.py` 的 REPORT_ONLY_STEPS | 取每条的 name 字面量 |

**枚举用 AST，不 import 被检查的仪器**：本工具是只报告的读数，不该为了读一张清单去执行
探针 / 闭环 / 门禁（那会带来副作用，也会让"读不到清单"变成一个安静的空集合）。
常量读不出来（被改成运行时构造、文件不在）→ 那一族 `status = unavailable` + reason，
**绝不写成 0**。同理，场景 id / check id 只认源码里的字面量，**不从函数名推导**
（推导会造出第二套名字）。

三态判据（方案 §4 台阶 4 的「红→绿」，结构化、不解析文本）
==========================================================

| 态 | 判据式 | 读数键 |
| --- | --- | --- |
| ① 没有身份 | 对象在清单里、登记表里没有它的 `check_id` | `red_conditions.no_check_id` |
| ② 没有自证也没有缺口说明 | `mutation_id` 缺失 **且** `gap_note` 缺失（含**空白串**：与 wiring-scope 的「空理由」同口径，判缺失而不是判通过） | `red_conditions.no_mutation_and_no_gap_note` |
| ③ 变异打不上 | 按 `mutation_id` 取的补丁在影子树上打不上（记录 / 补丁读不到也算） | `red_conditions.patch_not_applicable` |
| ④ 悬空（反退化的另一半） | 登记表里的 `check_id` 在清单里找不到对象 | `red_conditions.check_id_without_object` |

④ 不是 25 号 §2 三态里的第四态，而是同一份「双向比对」的另一半（方案 §3.2：
「任一边悬空即红」）。它与 ① 必须分开写（AGENTS 第 50 条：同名两义一律改名）：
① 是"对象没有被登记"，④ 是"登记了一个不存在的对象"。

**两条反退化**（不写下来，这三态会被读成"跑过了、没红"）：

1. 「未评」不是「不红」：登记表读不到 / 清单读不到 / git 影子树建不出来，
   那一格写 `status = unavailable` + `reason`，`count` 是 **null**（不是 0）——
   与 AGENTS 第 56 条「账本不存在 = 不适用」同一条口径；
2. 对象清单要有**第二来源**：登记表说自己有多少行不算证据；清单必须与四族实际可枚举的
   来源双向比对，差集非空即 ① / ④ 红（否则"表里只写 1 条、其余 63 条谁也不提"会静默通过）。
   `patch_not_applicable` 那一格同理：`mutation_id` 全空时它是 **0 且注明"没有可评的变异"**，
   不是一个可以读成"变异都验过"的 0。

只报告期怎么表达（一条退出码都不接）
====================================

- 每格都带 `status` / `count` / `items[]` / `is_red` / `red_when` /
  `enforced: false` / `would_exit_code: 1` / `promote_when`——与 `adapters.cli wiring` 的
  `red_conditions` **同形状**（复用既有词汇，不新造一套"红"的表达）；
- 退出码**恒为 0**（只报告；用法错误由 argparse 给 2，与判据无关）。升格判据与 L5 同型：
  跑过 N≥1 次且三态合计 0 命中，且 0 命中来自至少一次真实读数；
- 人类输出**只报计数与机器行**（2026-10-03 裁定第 3 条对 wiring 的同一条口径）：
  逐条明细只在 `--json` 里。

态③ 的"影子树"是哪棵树（AGENTS 第 48 条）
==========================================

`git apply --cached` 作用于**索引**，所以做法是：给一个自己的 `GIT_INDEX_FILE`，
先 `git read-tree HEAD` 把它填成 **HEAD 那棵树**，再 `git apply --cached --check <补丁>`。
`--check` 只判"打不打得上"，不写任何东西——**真实索引与工作树都不碰**
（`.tmp/step29` 的原型实测：好补丁 rc=0、context 对不上的补丁 rc=1、坏补丁 rc=128，
前后 `git status` 都是空）。因此本格的读数是"这个补丁打不打得上 **HEAD 那棵树**"，
与当前未提交的改动无关；影子索引落在 `.tmp/instrument-self-proof/`，用完即删。

载荷自己的版本轴（AGENTS 第 55 条）
===================================

`INSTRUMENT_SELF_PROOF_SCHEMA_VERSION = "1.0"`——本载荷**第一次出现就带轴**，
已登记进 AGENTS.md 第 55 条那张表。数据文件（`validation/instrument-checks.yaml`）
与变异记录各有自己的 `schema_version`（都从 "1" 起）。**既有载荷一个键都不加**：
覆盖账是"发现 × 声明"的账、`policy.check --json` 是判定包装，把仪器自证塞进任何一个
都是量纲混用（第 50 条），也会逼着那些载荷跟着升版。

用法
====

    python tools/instrument_self_proof.py [--checks PATH] [--mutations DIR] [--json]

默认输出一行机器行 `INSTRUMENT_SELF_PROOF: <四格计数> / objects=<n> declared=<n>`；
`--json` 给完整载荷。退出码恒为 0。
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple, Optional, Sequence

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from provenance import reading_context as reading  # noqa: E402

# 本载荷的版本轴（AGENTS 第 55 条；**首次出现就带轴**）。
INSTRUMENT_SELF_PROOF_SCHEMA_VERSION = "1.0"

# 两张数据文件各自的版本轴。
CHECKS_SCHEMA_VERSION = "1"
MUTATION_SCHEMA_VERSION = "1"

DEFAULT_CHECKS = REPO / "validation" / "instrument-checks.yaml"
DEFAULT_MUTATIONS = REPO / "validation" / "mutations"
SCRATCH = REPO / ".tmp" / "instrument-self-proof"

STATUS_AVAILABLE = reading.STATUS_AVAILABLE
STATUS_UNAVAILABLE = reading.STATUS_UNAVAILABLE

# 对象族（也是"这条读数覆盖了谁"）。
KIND_GATE_STEP = "gate_step"
KIND_GAP_PROBE = "gap_probe_check"
KIND_SEAL_SCENARIO = "seal_scenario"
KIND_REPORT_ONLY = "report_only_step"

# 每一行对象自己的状态（机器可读；读的人不必解析文本）。
ROW_DECLARED = "mutation_declared"
ROW_GAP_ONLY = "gap_note_only"
ROW_NO_SELF_PROOF = "no_self_proof"
ROW_PATCH_NOT_APPLICABLE = "patch_not_applicable"
ROW_NO_CHECK_ID = "no_check_id"

# 四格红条件（键名稳定，是跨文件契约）。
RED_NO_CHECK_ID = "no_check_id"
RED_NO_MUTATION_AND_NO_GAP_NOTE = "no_mutation_and_no_gap_note"
RED_PATCH_NOT_APPLICABLE = "patch_not_applicable"
RED_CHECK_ID_WITHOUT_OBJECT = "check_id_without_object"
RED_KEYS = (
    RED_NO_CHECK_ID,
    RED_NO_MUTATION_AND_NO_GAP_NOTE,
    RED_PATCH_NOT_APPLICABLE,
    RED_CHECK_ID_WITHOUT_OBJECT,
)

# 登记表的形状（方案 §3.2 的 checks 段，8 字段）。
ROW_FIELDS = (
    "check_id",
    "owner",
    "command",
    "covers",
    "evidence_level",
    "mutation_id",
    "gap_note",
    "severity",
)
OWNERS = ("ci-line", "control-plane")
EVIDENCE_LEVELS = ("exit_code", "report", "seal")
SEVERITIES = ("blocking", "advisory")

# 「只放指针」：出现这些键就是加载期错误（方案 §3.2 原文点名的一组）。
POINTER_ONLY_KEYS = ("last_run", "status", "passed")
POINTER_ONLY_PREFIXES = ("observed_",)

# 变异 id 的形态：仓库自己的一段标识，不许是路径（结构性阻断，AGENTS 第 17 条同一条纪律）。
MUTATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

_PROMOTE_WHEN = (
    "跑过 N≥1 次且三态合计 0 命中（0 命中必须来自至少一次真实读数）——与 L5 上线闸同型"
)
_REPORT_ONLY_NOTE = (
    "只报告期：本块不改任何退出码（本工具退出码恒为 0）；升格前必须先有一轮 warn + 非零退出"
)


class InstrumentChecksError(Exception):
    """登记表 / 变异记录 / 对象清单读不出来。**只报告**：调用方把它变成 unavailable，不阻断。"""


class CheckRow(NamedTuple):
    """登记表的一行（8 字段）；`gap_note` 的空白串按**缺失**处理（AGENTS 第 50 条口径）。"""

    check_id: str
    owner: str
    command: str
    covers: str
    evidence_level: str
    mutation_id: Optional[str]
    gap_note: Optional[str]
    severity: str

    @property
    def gap_note_present(self) -> bool:
        return bool(self.gap_note and self.gap_note.strip())


class ChecksTable(NamedTuple):
    path: Path
    schema_version: str
    rows: tuple
    by_id: dict


class Discovered(NamedTuple):
    """一个对象（仪器检查）：身份 + 族 + 它是从哪读出来的。"""

    object_id: str
    object_kind: str
    source: str


class Inventory(NamedTuple):
    objects: tuple
    sources: dict
    status: str
    reason: Optional[str]


# --------------------------------------------------------------------------- 登记表


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstrumentChecksError(where + " 必须是非空字符串，读到 " + repr(value))
    return value


def _optional_text(value: Any, where: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InstrumentChecksError(where + " 必须是字符串或 null，读到 " + repr(value))
    return value


def _enum(value: Any, allowed: Sequence[str], where: str) -> str:
    if value not in allowed:
        raise InstrumentChecksError(
            where + " 只接受 " + " / ".join(allowed) + "，读到 " + repr(value)
        )
    return str(value)


def load_checks(path: Path, *, display: Optional[str] = None) -> ChecksTable:
    """读登记表：未知字段 / 未知枚举 / 重复 id / 指针-only 键，一律加载期报错。

    `display` 是**读数里**的路径写法（仓库相对）：错误信息会进载荷，而载荷不放绝对路径
    （AGENTS 第 19/34 条的脱敏纪律）——读不到时那正是最需要被读到的一句话。
    """

    label = display if display is not None else path.name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise InstrumentChecksError("登记表读不到：" + label + "：" + str(error)) from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise InstrumentChecksError("登记表不是合法 YAML：" + str(error)) from error
    if not isinstance(document, dict):
        raise InstrumentChecksError("登记表的顶层必须是映射")
    unknown = sorted(set(document) - {"schema_version", "checks"})
    if unknown:
        raise InstrumentChecksError("登记表顶层有未知字段：" + " / ".join(unknown))
    version = document.get("schema_version")
    if version != CHECKS_SCHEMA_VERSION:
        raise InstrumentChecksError(
            "登记表的 schema_version 只接受 " + repr(CHECKS_SCHEMA_VERSION) + "，读到 " + repr(version)
        )
    rows_raw = document.get("checks")
    if not isinstance(rows_raw, list) or not rows_raw:
        raise InstrumentChecksError("登记表的 checks 段必须是非空列表")
    rows: list = []
    by_id: dict = {}
    for index, item in enumerate(rows_raw):
        where = "checks[" + str(index) + "]"
        if not isinstance(item, dict):
            raise InstrumentChecksError(where + " 必须是映射")
        # 「只放指针」先判：这两类键不是"未知字段"，是**禁止的字段**（方案 §3.2）。
        for key in item:
            if key in POINTER_ONLY_KEYS or str(key).startswith(POINTER_ONLY_PREFIXES):
                raise InstrumentChecksError(
                    where + " 出现 " + repr(key) + "：登记表只放指针（方案 §3.2）——"
                    "运行结果（last_run / status / passed / observed_*）不许写进这张表"
                )
        unknown_fields = sorted(set(item) - set(ROW_FIELDS))
        if unknown_fields:
            raise InstrumentChecksError(where + " 有未知字段：" + " / ".join(unknown_fields))
        missing = [field for field in ROW_FIELDS if field not in item]
        if missing:
            raise InstrumentChecksError(where + " 缺字段：" + " / ".join(missing))
        row = CheckRow(
            check_id=_text(item["check_id"], where + ".check_id"),
            owner=_enum(item["owner"], OWNERS, where + ".owner"),
            command=_text(item["command"], where + ".command"),
            covers=_text(item["covers"], where + ".covers"),
            evidence_level=_enum(item["evidence_level"], EVIDENCE_LEVELS, where + ".evidence_level"),
            mutation_id=_optional_text(item["mutation_id"], where + ".mutation_id"),
            gap_note=_optional_text(item["gap_note"], where + ".gap_note"),
            severity=_enum(item["severity"], SEVERITIES, where + ".severity"),
        )
        if row.check_id in by_id:
            raise InstrumentChecksError("check_id 重复：" + row.check_id)
        by_id[row.check_id] = row
        rows.append(row)
    return ChecksTable(path=path, schema_version=version, rows=tuple(rows), by_id=by_id)


# --------------------------------------------------------------------------- 对象清单（AST）


def _constant(path: Path, name: str) -> ast.AST:
    """读模块级常量（Assign / AnnAssign）的**字面量**值；不 import、不执行被检查的文件。"""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InstrumentChecksError("读不到 " + str(path) + "：" + str(error)) from error
    except SyntaxError as error:
        raise InstrumentChecksError(str(path) + " 语法错误：" + str(error)) from error
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        if any(t.id == name for t in targets):
            value = node.value
            if value is None:
                break
            return value
    raise InstrumentChecksError(str(path) + " 里找不到模块级常量 " + name)


def _strings(value: ast.AST, path: Path, name: str) -> list:
    """常量清单里的字符串：元素是名字、字符串，或带 name= 字面量的调用。"""

    if not isinstance(value, (ast.Tuple, ast.List)):
        raise InstrumentChecksError(str(path) + " 的 " + name + " 不是字面量清单（改形状要同步本工具）")
    out: list = []
    for element in value.elts:
        if isinstance(element, ast.Name):
            out.append(element.id)
        elif isinstance(element, ast.Constant) and isinstance(element.value, str):
            out.append(element.value)
        elif isinstance(element, ast.Call):
            keyword = next((k for k in element.keywords if k.arg == "name"), None)
            node = keyword.value if keyword is not None else None
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                raise InstrumentChecksError(
                    str(path) + " 的 " + name + " 里有一条读不出 name= 字面量的元素"
                )
            out.append(node.value)
        else:
            raise InstrumentChecksError(str(path) + " 的 " + name + " 里有读不出来的元素")
    if not out:
        raise InstrumentChecksError(str(path) + " 的 " + name + " 是空的")
    return out


def _call_literal(path: Path, function: str, keywords: Sequence[str], dict_keys: Sequence[str]) -> str:
    """某个函数体里第一个（关键字 / 字典键）字符串字面量——场景 id / check id 的取法。"""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as error:
        raise InstrumentChecksError(str(path) + " 读不出来：" + str(error)) from error
    target = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function), None
    )
    if target is None:
        raise InstrumentChecksError(str(path) + " 里没有函数 " + function)
    for node in ast.walk(target):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if (
                    keyword.arg in keywords
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    return keyword.value.value
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in dict_keys
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    return value.value
    raise InstrumentChecksError(
        str(path) + " 的 " + function + " 里读不出字面量 id（关键字 " + " / ".join(keywords) + "）"
    )


def _gate_steps(repo: Path) -> tuple:
    """门禁步骤：workflow 里带非空 run 块的步骤（名字即身份）。"""

    files = sorted(
        list(repo.glob(".github/workflows/*.yml")) + list(repo.glob(".github/workflows/*.yaml"))
    )
    if not files:
        raise InstrumentChecksError("没有找到 .github/workflows/*.yml：对象清单读不出来")
    objects: list = []
    for path in files:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise InstrumentChecksError(str(path) + " 读不出来：" + str(error)) from error
        jobs = (document or {}).get("jobs") or {}
        for job in jobs.values():
            for step in job.get("steps") or []:
                run = step.get("run")
                if isinstance(run, str) and run.strip():
                    name = str(step.get("name", "")) or "<未命名步骤>"
                    objects.append(
                        Discovered(
                            object_id="gate-step:" + name,
                            object_kind=KIND_GATE_STEP,
                            source=reading.display_path(path, root=repo),
                        )
                    )
    return tuple(objects)


def _gap_probe_checks(repo: Path) -> tuple:
    path = repo / "tools" / "governance_gap_probe.py"
    functions = _strings(_constant(path, "CHECKS"), path, "CHECKS")
    return tuple(
        Discovered(
            object_id="gap-probe:" + _call_literal(path, function, ("id",), ()),
            object_kind=KIND_GAP_PROBE,
            source=reading.display_path(path, root=repo),
        )
        for function in functions
    )


def _seal_scenarios(repo: Path) -> tuple:
    path = repo / "tools" / "provenance_loop.py"
    functions = _strings(_constant(path, "SCENARIOS"), path, "SCENARIOS")
    return tuple(
        Discovered(
            object_id="seal-scenario:" + _call_literal(path, function, ("scenario_id",), ("id",)),
            object_kind=KIND_SEAL_SCENARIO,
            source=reading.display_path(path, root=repo),
        )
        for function in functions
    )


def _report_only_steps(repo: Path) -> tuple:
    path = repo / "tools" / "ci_local.py"
    names = _strings(_constant(path, "REPORT_ONLY_STEPS"), path, "REPORT_ONLY_STEPS")
    return tuple(
        Discovered(
            object_id="report-only:" + name,
            object_kind=KIND_REPORT_ONLY,
            source=reading.display_path(path, root=repo),
        )
        for name in names
    )


def enumerate_objects(repo: Path) -> Inventory:
    """四族对象 + 每族读数；任何一族读不出来 → 整份清单 unavailable（绝不当成 0）。"""

    families = (
        ("gate_steps", _gate_steps),
        ("gap_probe_checks", _gap_probe_checks),
        ("seal_scenarios", _seal_scenarios),
        ("report_only_steps", _report_only_steps),
    )
    sources: dict = {}
    objects: list = []
    reasons: list = []
    for name, reader in families:
        try:
            found = reader(repo)
        except InstrumentChecksError as error:
            sources[name] = {"status": STATUS_UNAVAILABLE, "count": None, "reason": str(error)}
            reasons.append(name + "：" + str(error))
            continue
        objects.extend(found)
        sources[name] = {
            "status": STATUS_AVAILABLE,
            "count": len(found),
            "path": found[0].source if found else None,
        }
    if reasons:
        return Inventory(
            objects=tuple(),
            sources=sources,
            status=STATUS_UNAVAILABLE,
            reason="；".join(reasons),
        )
    ids = [item.object_id for item in objects]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        return Inventory(
            objects=tuple(),
            sources=sources,
            status=STATUS_UNAVAILABLE,
            reason="对象清单里有重复 id（身份方案不成立）：" + " / ".join(duplicates),
        )
    return Inventory(
        objects=tuple(sorted(objects, key=lambda item: item.object_id)),
        sources=sources,
        status=STATUS_AVAILABLE,
        reason=None,
    )


# --------------------------------------------------------------------------- 态③：变异打不上


def _shadow_index() -> Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return SCRATCH / "shadow-index"


def _git(arguments: Sequence[str], *, environment: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments], cwd=str(REPO), env=environment, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )


def mutation_applies(mutation_id: str, *, mutations_root: Path) -> tuple:
    """(能否证明打得上, 原因)。读不到记录 / 补丁 → 一样是"证明不了"，报红并写清是哪一种。"""

    if not MUTATION_ID.fullmatch(mutation_id) or ".." in mutation_id:
        return False, "mutation_id 形态非法（不许是路径，也不许含 ..）：" + mutation_id
    record_path = mutations_root / (mutation_id + ".yaml")
    try:
        document = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    except OSError as error:
        return False, "变异记录读不到：" + str(error)
    except yaml.YAMLError as error:
        return False, "变异记录不是合法 YAML：" + str(error)
    if not isinstance(document, dict):
        return False, "变异记录的顶层必须是映射"
    if document.get("schema_version") != MUTATION_SCHEMA_VERSION:
        return False, "变异记录的 schema_version 只接受 " + repr(MUTATION_SCHEMA_VERSION)
    if document.get("id") != mutation_id:
        return False, "变异记录的 id 与 mutation_id 不一致"
    patch = document.get("patch")
    if not isinstance(patch, str) or not patch.strip() or ".." in patch:
        return False, "变异记录的 patch 必须是相对路径且不含 .."
    patch_path = mutations_root / patch
    if not patch_path.is_file():
        return False, "补丁文件读不到：" + str(patch_path)

    environment = dict(os.environ)
    environment["GIT_INDEX_FILE"] = str(_shadow_index())
    read = _git(["read-tree", "HEAD"], environment=environment)
    if read.returncode != 0:
        raise InstrumentChecksError(
            "影子树建不出来（git read-tree HEAD 退 " + str(read.returncode) + "）："
            + read.stderr.strip()[:200]
        )
    applied = _git(["apply", "--cached", "--check", str(patch_path)], environment=environment)
    if applied.returncode == 0:
        return True, "补丁打得上 HEAD 那棵树"
    return False, (
        "补丁打不上 HEAD 那棵树（git apply --check 退 " + str(applied.returncode) + "）："
        + applied.stderr.strip().replace("\n", " | ")[:200]
    )


# --------------------------------------------------------------------------- 判据与载荷


def _cell(
    *,
    status: str,
    count: Optional[int],
    items: list,
    red_when: str,
    note: str,
    reason: Optional[str] = None,
) -> dict:
    cell: dict = {
        "status": status,
        "count": count if status == STATUS_AVAILABLE else None,
        "items": items if status == STATUS_AVAILABLE else [],
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
        status=STATUS_UNAVAILABLE, count=None, items=[], red_when=red_when,
        note=_REPORT_ONLY_NOTE, reason=reason,
    )


def evaluate(
    *,
    repo: Path = REPO,
    checks_path: Path = DEFAULT_CHECKS,
    mutations_root: Path = DEFAULT_MUTATIONS,
) -> dict:
    """把四族对象 + 登记表算成一份载荷（判据全在这里，只有这一个实现）。"""

    inventory = enumerate_objects(repo)
    try:
        table = load_checks(checks_path, display=reading.display_path(checks_path, root=repo))
        table_error = None
    except InstrumentChecksError as error:
        table = None
        table_error = str(error)

    table_block: dict = {
        "status": STATUS_AVAILABLE if table is not None else STATUS_UNAVAILABLE,
        "path": reading.display_path(checks_path, root=repo),
        "schema_version": table.schema_version if table is not None else None,
        "rows": len(table.rows) if table is not None else None,
    }
    if table_error is not None:
        table_block["reason"] = table_error

    closure_reason = table_error or (
        inventory.reason if inventory.status != STATUS_AVAILABLE else None
    )
    declared_ids = set(table.by_id) if table is not None else set()
    discovered_ids = {item.object_id for item in inventory.objects}
    rows = table.rows if table is not None else ()

    # 态① 对象没有被登记
    if closure_reason is not None:
        no_check_id = _unavailable_cell("对象在清单里、登记表里没有它的 check_id", closure_reason)
    else:
        missing = [item for item in inventory.objects if item.object_id not in declared_ids]
        no_check_id = _cell(
            status=STATUS_AVAILABLE,
            count=len(missing),
            items=[
                {"object_id": item.object_id, "object_kind": item.object_kind, "source": item.source}
                for item in missing
            ],
            red_when="对象清单里有 check_id 不在登记表里的对象（差集非空）",
            note=_REPORT_ONLY_NOTE,
        )

    # ④ 悬空：登记表里的 check_id 在清单里找不到对象（双向比对的另一半）
    if table is None:
        dangling = _unavailable_cell(
            "登记表里的 check_id 在对象清单里找不到对象", str(table_error)
        )
    else:
        unknown = [row for row in rows if row.check_id not in discovered_ids]
        dangling = _cell(
            status=STATUS_AVAILABLE,
            count=len(unknown),
            items=[
                {
                    "check_id": row.check_id,
                    "owner": row.owner,
                    "reason": "登记表里的 check_id 在对象清单里找不到对象",
                }
                for row in unknown
            ],
            red_when="登记表里的 check_id 在四族实际可枚举的对象里找不到（悬空）",
            note=_REPORT_ONLY_NOTE,
        )

    # 态② 既没有 mutation_id、又没有非空白 gap_note
    if table is None:
        no_self_proof = _unavailable_cell(
            "mutation_id 缺失且 gap_note 缺失（含空白串）", str(table_error)
        )
    else:
        bare = [row for row in rows if row.mutation_id is None and not row.gap_note_present]
        no_self_proof = _cell(
            status=STATUS_AVAILABLE,
            count=len(bare),
            items=[
                {
                    "check_id": row.check_id,
                    "owner": row.owner,
                    "mutation_id": row.mutation_id,
                    "gap_note_present": row.gap_note_present,
                    "reason": "既没有 mutation_id，也没有非空白的 gap_note",
                }
                for row in bare
            ],
            red_when="登记表里存在既没有 mutation_id、也没有非空白 gap_note 的行",
            note=_REPORT_ONLY_NOTE,
        )

    # 态③ 声明了 mutation_id 却证明不了补丁打得上
    declared_mutations = [row for row in rows if row.mutation_id]
    if table is None:
        patch_not_applicable = _unavailable_cell(
            "按 mutation_id 取的补丁在影子树上打不上", str(table_error)
        )
    elif not declared_mutations:
        patch_not_applicable = _cell(
            status=STATUS_AVAILABLE,
            count=0,
            items=[],
            red_when="按 mutation_id 取的补丁在影子树（HEAD）上 git apply --check 失败",
            note=(
                "登记表里 **0 行**声明了 mutation_id：这一格读作「没有可评的变异」，"
                "**不是**「变异都验过」（方案 A：存量对象先用 gap_note 记缺口）"
            ),
        )
    else:
        items: list = []
        machinery_error: Optional[str] = None
        for row in declared_mutations:
            try:
                ok, detail = mutation_applies(str(row.mutation_id), mutations_root=mutations_root)
            except InstrumentChecksError as error:
                machinery_error = str(error)
                break
            if not ok:
                items.append(
                    {"check_id": row.check_id, "mutation_id": row.mutation_id, "reason": detail}
                )
        if machinery_error is not None:
            patch_not_applicable = _unavailable_cell(
                "按 mutation_id 取的补丁在影子树上打不上", machinery_error
            )
        else:
            patch_not_applicable = _cell(
                status=STATUS_AVAILABLE,
                count=len(items),
                items=items,
                red_when="按 mutation_id 取的补丁在影子树（HEAD）上 git apply --check 失败",
                note=_REPORT_ONLY_NOTE,
            )

    red_conditions = {
        RED_NO_CHECK_ID: no_check_id,
        RED_NO_MUTATION_AND_NO_GAP_NOTE: no_self_proof,
        RED_PATCH_NOT_APPLICABLE: patch_not_applicable,
        RED_CHECK_ID_WITHOUT_OBJECT: dangling,
    }

    # checks[]：每个对象一行读数（逐条明细只有这一份）
    failing_mutations = {
        entry.get("mutation_id") for entry in red_conditions[RED_PATCH_NOT_APPLICABLE]["items"]
    }
    checks: list = []
    if table is not None and inventory.status == STATUS_AVAILABLE:
        for item in inventory.objects:
            row = table.by_id.get(item.object_id)
            if row is None:
                checks.append(
                    {
                        "check_id": None,
                        "object_id": item.object_id,
                        "object_kind": item.object_kind,
                        "mutation_id": None,
                        "gap_note_present": False,
                        "state": ROW_NO_CHECK_ID,
                    }
                )
                continue
            if row.mutation_id and row.mutation_id in failing_mutations:
                state = ROW_PATCH_NOT_APPLICABLE
            elif row.mutation_id:
                state = ROW_DECLARED
            elif row.gap_note_present:
                state = ROW_GAP_ONLY
            else:
                state = ROW_NO_SELF_PROOF
            checks.append(
                {
                    "check_id": row.check_id,
                    "object_id": item.object_id,
                    "object_kind": item.object_kind,
                    "mutation_id": row.mutation_id,
                    "gap_note_present": row.gap_note_present,
                    "state": state,
                }
            )

    if table is None or inventory.status != STATUS_AVAILABLE:
        objects = {
            "status": STATUS_UNAVAILABLE,
            "table": table_block,
            "sources": inventory.sources,
            "discovered": None,
            "declared": None,
            "with_mutation_id": None,
            "with_gap_note": None,
            "without_either": None,
        }
    else:
        objects = {
            "status": STATUS_AVAILABLE,
            "table": table_block,
            "sources": inventory.sources,
            "discovered": len(inventory.objects),
            "declared": len(rows),
            "with_mutation_id": len(declared_mutations),
            "with_gap_note": len([row for row in rows if row.gap_note_present]),
            "without_either": len(
                [row for row in rows if not row.mutation_id and not row.gap_note_present]
            ),
        }

    payload = {
        "schema_version": INSTRUMENT_SELF_PROOF_SCHEMA_VERSION,
        "mode": "report-only",
        "note": (
            "只报告：退出码恒为 0，不改任何 allow / block，也不接进本机门禁；"
            "逐条明细在本载荷里，人类输出只报计数"
        ),
        "reading_context": reading.build(
            source=reading.SOURCE_GATE,
            tree=reading.tree_block(repo),
            declarations={
                reading.DECLARATION_INSTRUMENT_CHECKS: reading.declaration_block(
                    checks_path, root=repo
                ),
            },
            host=reading.host_block(),
        ),
        "mutations_root": reading.display_path(mutations_root, root=repo),
        "objects": objects,
        "checks": checks,
        "red_conditions": red_conditions,
    }
    payload["headline"] = {"text": _headline_text(payload), "machine_line": machine_line(payload)}
    return payload


def _lookup(payload: dict, key: str) -> str:
    cell = payload["red_conditions"][key]
    if cell["status"] != STATUS_AVAILABLE:
        return "unavailable"
    return str(cell["count"])


def machine_line(payload: dict) -> str:
    """机器行（跨文件契约）：四格计数 + 对象数 / 登记表行数；未评写 unavailable，不写 0。"""

    objects = payload["objects"]
    return (
        "INSTRUMENT_SELF_PROOF: "
        + " ".join(key + "=" + _lookup(payload, key) for key in RED_KEYS)
        + " / objects="
        + str(objects["discovered"] if objects["discovered"] is not None else "unavailable")
        + " declared="
        + str(objects["declared"] if objects["declared"] is not None else "unavailable")
    )


def _headline_text(payload: dict) -> str:
    objects = payload["objects"]
    return (
        "仪器自证：对象 "
        + str(objects["discovered"] if objects["discovered"] is not None else "unavailable")
        + " 条（登记表 "
        + str(objects["declared"] if objects["declared"] is not None else "unavailable")
        + " 行），"
        + "、".join(key + " " + _lookup(payload, key) for key in RED_KEYS)
        + "（全部只报告）"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python tools/instrument_self_proof.py",
        description="仪器自证（只报告：退出码恒为 0，不改任何 allow / block）。",
    )
    parser.add_argument(
        "--checks", default=str(DEFAULT_CHECKS),
        help="检查登记表（默认 validation/instrument-checks.yaml）",
    )
    parser.add_argument(
        "--mutations", default=str(DEFAULT_MUTATIONS),
        help="变异记录目录（默认 validation/mutations/）",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读载荷")
    return parser


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    payload = evaluate(checks_path=Path(args.checks), mutations_root=Path(args.mutations))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    objects = payload["objects"]

    def number(value: object) -> str:
        return "unavailable" if value is None else str(value)

    print("仪器自证（只报告：退出码恒为 0，不接任何退出码）")
    print(
        "  对象: "
        + number(objects["discovered"])
        + "（"
        + " / ".join(
            name + " " + number(block["count"]) for name, block in sorted(objects["sources"].items())
        )
        + "）"
    )
    print(
        "  登记表: "
        + str(objects["table"]["path"])
        + "（"
        + str(objects["table"]["status"])
        + "，"
        + number(objects["table"]["rows"])
        + " 行）"
    )
    # 人类输出只报计数（2026-10-03 裁定第 3 条）：逐条明细只在 --json 里。
    for key in RED_KEYS:
        cell = payload["red_conditions"][key]
        mark = "unavailable" if cell["status"] != STATUS_AVAILABLE else str(cell["count"])
        print("  [" + ("红" if cell["is_red"] else "ok") + "] " + key + ": " + mark)
    print("  " + payload["headline"]["machine_line"])
    print("  " + payload["headline"]["text"])
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())

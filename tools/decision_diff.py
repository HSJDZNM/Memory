r"""R-d 字段级差集：两份 JSON 载荷的 added / modified / removed 三列（阶段 1）。

它是什么
========

05 §3.5 的 R-d 要求：**任何改变 decision 的步骤都必须交出字段级差集，含 violations 内容，
不只 decision 值**。本工具是这件事的单消费方：给定两份 JSON 载荷，递归比较每一个字段，
把差异列成三列（added / modified / removed），每条带指针（如 `violations[2].rule_id`）、
前值与后值。差集必须**入库**：留在 `.tmp` 里的处理会被 cleanup 删掉（5.32/5.33 正是这条教训）。

它不是什么（读之前先看这三条）
==============================

1. **不是只报告读数**：仓库里的一批只报告工具（`exemption_expiry` / `instrument_self_proof` /
   `control_plane_facts` / `approval_allowlist_audit`）退出码恒 0；本工具是**差集工具**，
   按 tools/README.md 的「门禁退出码」表用 0/1/2。差集非空是**结论**，不是一次读数。
2. **不做双版本采集**（阶段 1 的边界）：只比**两份已存在的载荷**。用 git worktree 把两个代码
   版本各跑一遍、自动采集载荷，是**阶段 2** 的采集器，本阶段不实现。
3. **不解释差异、不判严重度**：只回答"哪一字段、从什么、变成什么"。一条 added 是缺陷还是修复，
   由看差集的人判定。

载荷自己的版本轴（AGENTS 第 55 条）
=================================

DECISION_DIFF_SCHEMA_VERSION = "1.0"——**首次出现就带轴**（2026-10-18，R-d 阶段 1）：
`pairs`（文件级配对）+ 每条条目的 `kind` / `pointer` / `before` / `after` + `counts`。
加键或改语义必须按本条显式递增，并同批改掉写死版本号的引用点。
**载荷里没有时戳、没有 run 标识**：它是两份输入的纯函数，同样的输入两次运行逐字节相同
（与 `policy.check.OUTPUT_SCHEMA_VERSION` 的"包装层不带 run"同一条纪律）。

**为什么没有 `reading_context`**：它回答"这次读数属于哪棵树 / 哪个宿主"，而本工具的输入是
**任意两份载荷**（可能来自另一棵树——阶段 2 的采集器正是这种用法）。写一个"属于本树"的子块会把两件
事混同，`host.sandbox` 这类字段还会让同一对输入在不同机器上产出不同字节。指向载荷本身的是
`pairs[].base` / `pairs[].head` 的仓库相对路径 + `sha256` 摘要——读的人据此复核"比的是哪两份"。

指针语法
========

- 顶层字段：`decision`、`violations`；
- 对象字段：`violations[...].severity`（键名不是标识符时写成 ["a.b"]）；
- 数组按**索引**：`matched_rules[2]`、`violations[0].rule_id`；
- 数组按**可识别键**：`violations[rule_id=ARCH-001@1].severity`；
- 整份载荷（目录模式下某一侧缺这份文件）：`.`。

数组怎么匹配（这决定"多一条少一条"会不会被算成整体 modified）
=========================================================

1. **按可识别键**：两侧都是对象列表、且某个键（`rule_id` / `check_id` / `tool_id` /
   `channel` / `key` / `id` / `name` / `path`，按此顺序取第一个可用的）在**每一侧
   内部都唯一**时，按这个键配对——插入一条不会让后面的条目整体位移；键本身变了 = 一条
   removed + 一条 added（身份变了，不是修改）。
2. **否则按序列对齐**（`difflib.SequenceMatcher`，`autojunk=False`）：完全相同的元素先对上，
   两个锚点之间按位置配对（成对 -> 递归出 modified），多出来的一侧整条 added / removed。
   `matched_rules` 这类字符串数组因此不会因为中间插了一条而把后面全部报成 modified。
3. 两条都不可用时（例如元素里没有共同的可识别键）退化成按位置比较——**这是已知的表达力
   边界**，写在这里而不是留给读者从输出反推。
4. 索引是**所在侧**的下标：整条 removed 用 base 的下标、整条 added 用 head 的下标，
   成对修改用 head 的下标（两侧都存在）。

脱敏（绝不输出密钥 / 绝对路径）
============================

每一条进入输出的字符串都先过仓库**既有的两份实现**，不另写一套口径（AGENTS 第 50 条）：
`provenance.reading_context.fold_absolute_paths` 把绝对路径折叠成仓库相对路径或
`<outside-workspace>`，`enforcement.audit.redact_text` 再按运行期审计的同一份模式去密钥、
转义控制字符、截断超长正文。**对象键也脱敏**：两个不同的键折叠成同一个展示名时确定性追加
`#2` / `#3`，不静默丢值。命令行的错误信息同样脱敏（底层异常的原文先折叠路径），所以
"输入坏了"这条路径也不泄漏绝对路径。

用法与退出码
============

    python tools/decision_diff.py --base <a.json> --head <b.json> [--json|--md]
                                  [--out PATH] [--limit N]

    --base / --head   两侧都是文件，或两侧都是目录（目录按**文件名**配对、不递归；
                      某一侧缺这份文件 = 整份 added / removed，指针写 `.`）
    --json            机器可读载荷（版本轴见上）
    --md              Markdown 三列表（贴进 R-d 报告用）
    --out PATH        把所选格式写进文件（父目录不存在时创建；UTF-8 + LF + 单尾换行）
    --limit N         人类摘要最多列 N 条（默认 10，0 = 只列计数；不影响 --json / --md）

退出码：**0 = 无差异；1 = 有差异；2 = 输入或用法错误**（文件读不到 / 不是 JSON / 根部不是
dict 或 list / 两侧形态不一致 / 目录里没有 *.json / --out 写不了）。错误一律带一句可读的
reason 且不打 traceback；"有差异"永远不写成 0——那不是只报告读数。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

# 脱敏只有一份实现（AGENTS 第 50 条）：绝对路径折叠走只报告读数那一份，密钥 / 控制字符走运行期
# 审计那一份。本工具不写第三套模式，也不复制一份正则。
from enforcement.audit import redact_text  # noqa: E402
from provenance import reading_context as reading  # noqa: E402

# 本载荷的版本轴（AGENTS 第 55 条）：**首次出现就带轴**。
DECISION_DIFF_SCHEMA_VERSION = "1.0"

EXIT_IDENTICAL = 0
EXIT_DIFFERENT = 1
EXIT_USAGE = 2

ADDED = "added"
MODIFIED = "modified"
REMOVED = "removed"
KINDS = (ADDED, MODIFIED, REMOVED)

#: 整份载荷的指针（目录模式下某一侧缺这份文件时用它）。
ROOT_POINTER = "."

#: 可识别键的候选顺序：先试更有身份的那一个（`rule_id` 比 `name` 稳）。
IDENTIFYING_KEYS = ("rule_id", "check_id", "tool_id", "channel", "key", "id", "name", "path")

#: 人类摘要默认列多少条（--limit 可改；--json / --md 不受它影响）。
DEFAULT_LIMIT = 10

KIND_FILE = "file"
KIND_DIRECTORY = "directory"

#: 退出码语义（写进载荷，读的人不必回头翻 README）。
EXIT_CODE_MEANINGS = {
    EXIT_IDENTICAL: "无差异",
    EXIT_DIFFERENT: "有差异",
    EXIT_USAGE: "输入 / 用法错误",
}

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DiffInputError(Exception):
    """输入 / 用法错误（退出码 2）：读不到、不是 JSON、形态不一致、写不了。

    与"有差异"必须能分开——两者都退 1 时调用方读不出"这次到底比了没有"。
    消息在 raise 处就已脱敏（路径走 _display、异常原文走 redact）。
    """
# --------------------------------------------------------------------------- 脱敏


def redact(text: Any) -> str:
    """输出口径的脱敏：先折叠绝对路径，再用运行期审计的同一份模式去密钥。"""

    return redact_text(reading.fold_absolute_paths(str(text), root=REPO))


def _display(path: Optional[Path]) -> str:
    """路径的展示形态：仓库内写相对路径，之外写 <outside-workspace>，没给写 <unset>。"""

    if path is None:
        return "<unset>"
    return reading.display_path(path, root=REPO)


def sanitize(value: Any) -> Any:
    """递归脱敏一个 JSON 值：字符串过 redact，对象键同样过；键名撞车时确定性加序号。"""

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
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


# --------------------------------------------------------------------------- 指针


def _field_pointer(parent: str, key: str) -> str:
    """对象字段的指针：标识符用点号，其余用 JSON 引号（如 ["a.b"]）。"""

    if _IDENTIFIER_RE.match(key):
        return key if not parent else parent + "." + key
    return parent + "[" + json.dumps(key, ensure_ascii=False) + "]"


def _index_pointer(parent: str, index: int) -> str:
    return "%s[%d]" % (parent, index)


def _key_pointer(parent: str, key: str, value: Any) -> str:
    return "%s[%s=%s]" % (parent, key, value)


# --------------------------------------------------------------------------- 差集


def _entry(kind: str, pointer: str, before: Any, after: Any) -> dict:
    """一条差集条目。不存在的那一侧写 null——读的时候**以 kind 为准**（值本身也可以是 null）。"""

    return {
        "kind": kind,
        "pointer": redact(pointer),
        "before": sanitize(before),
        "after": sanitize(after),
    }


def _same(left: Any, right: Any) -> bool:
    """JSON 值相等：true 与 1 是两种值，1 与 1.0 是同一个数。"""

    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    return left == right


def _signature(value: Any) -> str:
    """序列对齐用的规范文本：相同结构得到相同串（键排序、无空白）。"""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _key_is_usable(items: Sequence[Any], key: str) -> bool:
    """这个键能不能当身份：每一项都是对象、都有非 bool 的标量取值、且同一侧内不重复。

    空列表**可用**（真空满足）：一侧为空时按键配对能给出 `violations[rule_id=...]` 这种
    有身份的指针，而逐位置比较只能给 `violations[0]`——"多一条"不该丢掉它的身份。
    """

    seen: set = set()
    for item in items:
        if not isinstance(item, dict):
            return False
        value = item.get(key)
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return False
        if value in seen:
            return False
        seen.add(value)
    return True


def _identifying_key(base: Sequence[Any], head: Sequence[Any]) -> Optional[str]:
    for key in IDENTIFYING_KEYS:
        if _key_is_usable(base, key) and _key_is_usable(head, key):
            return key
    return None


def _identity_sort_key(value: Any) -> tuple:
    """身份值的稳定排序：整数按数值（零填充成定宽串），字符串排在整数之后。"""

    if isinstance(value, int):
        return (0, "%030d" % value)
    return (1, str(value))


def _diff(base: Any, head: Any, pointer: str, entries: list) -> None:
    """把 base -> head 的差异追加进 entries（顺序由遍历决定，因此稳定）。"""

    if isinstance(base, dict) and isinstance(head, dict):
        for key in sorted(set(base) | set(head)):
            child = _field_pointer(pointer, key)
            if key not in base:
                entries.append(_entry(ADDED, child, None, head[key]))
            elif key not in head:
                entries.append(_entry(REMOVED, child, base[key], None))
            else:
                _diff(base[key], head[key], child, entries)
        return
    if isinstance(base, list) and isinstance(head, list):
        _diff_lists(base, head, pointer, entries)
        return
    if not _same(base, head):
        entries.append(_entry(MODIFIED, pointer or ROOT_POINTER, base, head))


def _diff_lists(base: Sequence[Any], head: Sequence[Any], pointer: str, entries: list) -> None:
    key = _identifying_key(base, head)
    if key is not None:
        _diff_lists_by_key(base, head, pointer, key, entries)
        return
    _diff_lists_by_alignment(base, head, pointer, entries)


def _diff_lists_by_key(
    base: Sequence[Any],
    head: Sequence[Any],
    pointer: str,
    key: str,
    entries: list,
) -> None:
    """按可识别键配对：插入 / 删除只落在它自己那条上，其余条目一个字节都不动。"""

    base_map = {item[key]: item for item in base}
    head_map = {item[key]: item for item in head}
    for value in sorted(set(base_map) | set(head_map), key=_identity_sort_key):
        child = _key_pointer(pointer, key, value)
        if value not in base_map:
            entries.append(_entry(ADDED, child, None, head_map[value]))
        elif value not in head_map:
            entries.append(_entry(REMOVED, child, base_map[value], None))
        else:
            _diff(base_map[value], head_map[value], child, entries)


def _diff_lists_by_alignment(
    base: Sequence[Any], head: Sequence[Any], pointer: str, entries: list
) -> None:
    """序列对齐：完全相同的元素先对上，替换块里按位置配对（成对 -> modified）。"""

    matcher = difflib.SequenceMatcher(
        a=[_signature(item) for item in base],
        b=[_signature(item) for item in head],
        autojunk=False,
    )
    for tag, base_start, base_end, head_start, head_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for offset in range(base_end - base_start):
                index = base_start + offset
                entries.append(_entry(REMOVED, _index_pointer(pointer, index), base[index], None))
            continue
        if tag == "insert":
            for offset in range(head_end - head_start):
                index = head_start + offset
                entries.append(_entry(ADDED, _index_pointer(pointer, index), None, head[index]))
            continue
        # replace：先按位置配对（成对 = 递归，出 modified），多出来的一侧整条 added / removed。
        paired = min(base_end - base_start, head_end - head_start)
        for offset in range(paired):
            _diff(
                base[base_start + offset],
                head[head_start + offset],
                _index_pointer(pointer, head_start + offset),
                entries,
            )
        for offset in range(paired, base_end - base_start):
            index = base_start + offset
            entries.append(_entry(REMOVED, _index_pointer(pointer, index), base[index], None))
        for offset in range(paired, head_end - head_start):
            index = head_start + offset
            entries.append(_entry(ADDED, _index_pointer(pointer, index), None, head[index]))


def diff_payloads(base: Any, head: Any) -> list:
    """两份已解析的 JSON 载荷的字段级差集（条目已脱敏；顺序稳定）。"""

    entries: list = []
    _diff(base, head, "", entries)
    return entries


def counts_of(entries: Sequence[dict]) -> dict:
    """三列计数 + 合计（键的顺序固定；--json 还会按字母排序）。"""

    counts = {kind: 0 for kind in KINDS}
    for entry in entries:
        counts[entry["kind"]] += 1
    counts["total"] = len(entries)
    return counts


# --------------------------------------------------------------------------- 输入


def load_payload(path: Path) -> Any:
    """读一份 JSON 载荷；任何读不懂的形态都是 DiffInputError（退出码 2），不是"无差异"。"""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise DiffInputError("载荷文件不存在：" + _display(path)) from error
    except UnicodeDecodeError as error:
        raise DiffInputError("载荷文件不是 UTF-8（%s）：%s" % (_display(path), error)) from error
    except OSError as error:
        raise DiffInputError(
            "载荷文件读不出来（%s）：%s（%s）"
            % (type(error).__name__, _display(path), redact(error))
        ) from error
    # BOM 不是 JSON（RFC 8259 不允许写入），而 Python 的 json 只会给一句英文报错：
    # 拒绝理由必须说清"改成什么形态就能过"（AGENTS 第 50 条）。
    if text.startswith("\ufeff"):
        raise DiffInputError(
            "文件以 UTF-8 BOM 开头（JSON 规范不允许；去掉 BOM 即可）：" + _display(path)
        )
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise DiffInputError(
            "不是合法 JSON（%s 第 %d 行第 %d 列）：%s"
            % (_display(path), error.lineno, error.colno, error.msg)
        ) from error
    if not isinstance(document, (dict, list)):
        raise DiffInputError(
            "根部必须是 dict 或 list，%s 的顶层类型是 %s"
            % (_display(path), type(document).__name__)
        )
    return document


def _input_kind(path: Path) -> str:
    """这份输入是文件还是目录（不存在 / 形态不明都是退出码 2）。"""

    if path.is_dir():
        return KIND_DIRECTORY
    if path.is_file():
        return KIND_FILE
    raise DiffInputError("路径不存在或不是普通文件 / 目录：" + _display(path))


def _json_names(directory: Path) -> list:
    """目录里参与配对的 *.json 文件名（排序；空集合不是"无差异"）。"""

    try:
        names = sorted(
            child.name
            for child in directory.iterdir()
            if child.is_file() and child.suffix.lower() == ".json"
        )
    except OSError as error:
        raise DiffInputError(
            "目录读不出来（%s）：%s（%s）"
            % (type(error).__name__, _display(directory), redact(error))
        ) from error
    if not names:
        raise DiffInputError("目录里没有 *.json（空集合不算「无差异」）：" + _display(directory))
    return names


# --------------------------------------------------------------------------- 配对


def _side_block(path: Optional[Path]) -> Optional[dict]:
    """一侧的载荷位置 + 摘要；null = 这一侧没有这份文件（读不到已经退出 2 了）。"""

    if path is None:
        return None
    return {"path": _display(path), "digest": reading.declaration_digest(path)}


def _pair_block(
    name: str,
    base_path: Optional[Path],
    head_path: Optional[Path],
    entries: list,
) -> dict:
    return {
        "name": redact(name),
        "base": _side_block(base_path),
        "head": _side_block(head_path),
        "identical": not entries,
        "counts": counts_of(entries),
        "entries": entries,
    }


def diff_files(base_path: Path, head_path: Path, *, name: Optional[str] = None) -> dict:
    """两份文件的差集（两份都必须存在且可解析）。"""

    base = load_payload(base_path)
    head = load_payload(head_path)
    return _pair_block(name or base_path.name, base_path, head_path, diff_payloads(base, head))


def diff_directories(base_dir: Path, head_dir: Path) -> list:
    """按文件名配对两份目录：两侧都有的比字段，只在一侧的整份 added / removed。"""

    base_names = set(_json_names(base_dir))
    head_names = set(_json_names(head_dir))
    pairs: list = []
    for name in sorted(base_names | head_names):
        base_path: Optional[Path] = base_dir / name if name in base_names else None
        head_path: Optional[Path] = head_dir / name if name in head_names else None
        entries: list
        if base_path is None:
            entries = [_entry(ADDED, ROOT_POINTER, None, load_payload(head_path))]
        elif head_path is None:
            entries = [_entry(REMOVED, ROOT_POINTER, load_payload(base_path), None)]
        else:
            entries = diff_payloads(load_payload(base_path), load_payload(head_path))
        pairs.append(_pair_block(name, base_path, head_path, entries))
    return pairs


def build_payload(base_path: Path, head_path: Path) -> dict:
    """完整读数载荷（自带版本轴；不含时戳 / run 标识 ⇒ 相同输入逐字节相同）。"""

    base_kind = _input_kind(base_path)
    head_kind = _input_kind(head_path)
    if base_kind != head_kind:
        raise DiffInputError(
            "--base 与 --head 必须同形（都是文件或都是目录）：%s vs %s" % (base_kind, head_kind)
        )
    if base_kind == KIND_FILE:
        name = (
            base_path.name
            if base_path.name == head_path.name
            else "%s -> %s" % (base_path.name, head_path.name)
        )
        pairs = [diff_files(base_path, head_path, name=name)]
    else:
        pairs = diff_directories(base_path, head_path)

    counts = {kind: 0 for kind in KINDS}
    for pair in pairs:
        for kind in KINDS:
            counts[kind] += pair["counts"][kind]
    counts["total"] = sum(pair["counts"]["total"] for pair in pairs)
    identical = counts["total"] == 0
    return {
        "schema_version": DECISION_DIFF_SCHEMA_VERSION,
        "mode": "diff",
        "input": base_kind,
        "base": _display(base_path),
        "head": _display(head_path),
        "identical": identical,
        "counts": counts,
        "exit_code": EXIT_IDENTICAL if identical else EXIT_DIFFERENT,
        "exit_codes": {
            str(code): meaning for code, meaning in sorted(EXIT_CODE_MEANINGS.items())
        },
        "pairs": pairs,
        "note": (
            "差集工具（**不是**只报告读数）：0 = 无差异 / 1 = 有差异 / 2 = 输入或用法错误；"
            "阶段 1 只比两份已存在的载荷，用 git worktree 的双版本采集器属阶段 2"
        ),
    }


# --------------------------------------------------------------------------- 渲染


def render_value(value: Any) -> str:
    """一条差集值的显示形态：JSON 文本（确定性；字符串带引号、null 写 null）。"""

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _counts_text(counts: dict) -> str:
    return "added=%d modified=%d removed=%d total=%d" % (
        counts[ADDED],
        counts[MODIFIED],
        counts[REMOVED],
        counts["total"],
    )


def _verdict(payload: dict) -> str:
    return "无差异" if payload["identical"] else "有差异"


def _entry_line(entry: dict, prefix: str = "") -> str:
    """一条条目的人类单行：不存在的那一侧不打印（kind 已经说明）。"""

    head = "[%s] %s%s" % (entry["kind"], prefix, entry["pointer"])
    if entry["kind"] == ADDED:
        return head + ": " + render_value(entry["after"])
    if entry["kind"] == REMOVED:
        return head + ": " + render_value(entry["before"])
    return head + ": " + render_value(entry["before"]) + " -> " + render_value(entry["after"])


def _flat_entries(payload: dict) -> list:
    rows: list = []
    for pair in payload["pairs"]:
        for entry in pair["entries"]:
            rows.append((pair["name"], entry))
    return rows


def machine_line(payload: dict) -> str:
    """本工具自己的机器行（形状稳定；**暂无跨文件消费方**，不是 ci_local 的读数契约）。"""

    counts = payload["counts"]
    return "DECISION_DIFF: added=%d modified=%d removed=%d total=%d identical=%s" % (
        counts[ADDED],
        counts[MODIFIED],
        counts[REMOVED],
        counts["total"],
        "true" if payload["identical"] else "false",
    )


def render_human(payload: dict, *, limit: int = DEFAULT_LIMIT) -> str:
    """人类摘要：计数 + 前 N 条（--limit 控制；全量在 --json / --md 里）。"""

    lines = [
        "R-d 字段级差集（差集工具：0=无差异 / 1=有差异 / 2=输入或用法错误）",
        "  base: " + payload["base"],
        "  head: " + payload["head"],
        "  schema_version: " + payload["schema_version"],
        "  合计: " + _counts_text(payload["counts"]) + "（" + _verdict(payload) + "）",
    ]
    if payload["input"] == KIND_DIRECTORY:
        for pair in payload["pairs"]:
            lines.append("  " + pair["name"] + ": " + _counts_text(pair["counts"]))
    rows = _flat_entries(payload)
    for name, entry in rows[:limit]:
        prefix = (name + ": ") if payload["input"] == KIND_DIRECTORY else ""
        lines.append("  " + _entry_line(entry, prefix))
    if len(rows) > limit:
        lines.append("  … 余 %d 条（--limit 调整；--json / --md 给全量）" % (len(rows) - limit))
    lines.append("  " + machine_line(payload))
    return "\n".join(lines) + "\n"


def _md_cell(text: str) -> str:
    """Markdown 单元格：竖线转义、换行压成空格（值里的 JSON 可能带引号，不放进反引号里）。"""

    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _md_entry_row(entry: dict) -> str:
    before = "（无）" if entry["kind"] == ADDED else _md_cell(render_value(entry["before"]))
    after = "（无）" if entry["kind"] == REMOVED else _md_cell(render_value(entry["after"]))
    return "| %s | %s | %s | %s |" % (
        entry["kind"],
        _md_cell(entry["pointer"]),
        before,
        after,
    )


def render_md(payload: dict) -> str:
    """Markdown 三列表（全量，贴进 R-d 报告用；不受 --limit 影响）。"""

    lines = [
        "# R-d 字段级差集",
        "",
        "- base: `" + payload["base"] + "`",
        "- head: `" + payload["head"] + "`",
        "- schema_version: `" + payload["schema_version"] + "`",
        "- 合计: " + _counts_text(payload["counts"]) + "（" + _verdict(payload) + "）",
        "- 退出码: %d（%s）"
        % (payload["exit_code"], EXIT_CODE_MEANINGS[payload["exit_code"]]),
    ]
    for pair in payload["pairs"]:
        lines.append("")
        lines.append("## `" + _md_cell(pair["name"]) + "`")
        lines.append("")
        lines.append("- 计数: " + _counts_text(pair["counts"]))
        if not pair["entries"]:
            lines.append("")
            lines.append("（无差异）")
            continue
        lines.append("")
        lines.append("| 列 | 指针 | 前值 | 后值 |")
        lines.append("| --- | --- | --- | --- |")
        lines.extend(_md_entry_row(entry) for entry in pair["entries"])
    return "\n".join(lines) + "\n"


def render_json(payload: dict) -> str:
    """机器可读载荷：键排序 + 固定缩进 ⇒ 相同输入逐字节相同。"""

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------- CLI


def _limit(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--limit 必须是整数，读到 %r" % text) from error
    if value < 0:
        raise argparse.ArgumentTypeError("--limit 不能是负数，读到 %r" % text)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="R-d 字段级差集（差集工具：0=无差异 / 1=有差异 / 2=输入或用法错误）"
    )
    parser.add_argument("--base", required=True, metavar="PATH", help="基准载荷（文件或目录）")
    parser.add_argument(
        "--head",
        required=True,
        metavar="PATH",
        help="变更后载荷（文件或目录；两侧必须同形）",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", help="机器可读载荷（自带版本轴）")
    group.add_argument("--md", action="store_true", help="Markdown 三列表（贴进 R-d 报告）")
    parser.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="把所选格式写进文件（父目录不存在时创建）",
    )
    parser.add_argument(
        "--limit",
        type=_limit,
        default=DEFAULT_LIMIT,
        metavar="N",
        help="人类摘要最多列 N 条（默认 %d，0 = 只列计数）" % DEFAULT_LIMIT,
    )
    return parser


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    base_path = Path(args.base)
    head_path = Path(args.head)
    try:
        payload = build_payload(base_path, head_path)
    except DiffInputError as error:
        print("decision diff: " + str(error), file=sys.stderr)
        return EXIT_USAGE

    if args.json:
        text = render_json(payload)
    elif args.md:
        text = render_md(payload)
    else:
        text = render_human(payload, limit=args.limit)

    if args.out:
        target = Path(args.out)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        except OSError as error:
            print(
                "decision diff: --out 写不了（%s）：%s（%s）"
                % (type(error).__name__, _display(target), redact(error)),
                file=sys.stderr,
            )
            return EXIT_USAGE
        print("decision diff: 已写入 " + _display(target))
    else:
        sys.stdout.write(text)
    return payload["exit_code"]


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

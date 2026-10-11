r"""审批条子 × 注册表白名单：跨源互证（**只报告**）。

它是谁、为什么要有它
====================

「按命令族签条子」这件事有一个**天生的第二副本风险**：白名单住在
`registry/tool-registry.yaml`（数据，改它要重新审核哈希），而审批模式住在
`approval.json` 的 `param_patterns`（人签的存储）。两者都是数据、都可能改，
但**改一边不会动另一边**：

- 注册表加了新允许的命令形态 → 旧条子覆盖不到 → 受治会话里新命令被拒
  （方向是失败关闭，**但读数会撒谎**：看起来像“命令不合法”，其实是“条子落后”）；
- 条子的模式放宽到注册表之外 → 白名单仍然拦得住（结构性闸门在审批之前），
  但**授权面**已经越过了注册表声明的边界，而这件事在任何一份读数里都看不见。

本工具把这两份数据**双向**比对，并在默认输出里给一行 `HITS:`（与
`tools/instrument_self_proof.py` / `tools/exemption_control.py` 同族的机器行）。

它不判定、不阻断：退出码**恒为 0**（用法错误由 argparse 给 2，与判据无关）。
升格判据与 L5 同型：跑过 N≥1 次且四格合计 0 命中，且 0 命中必须来自至少一次真实读数。

四格红条件（与 `adapters.wiring` 的 `red_conditions` 同形状，复用既有词汇）
============================================================================

- `pattern_outside_the_allowlist`：条子某个模式的**字面前缀**没有任何白名单条目覆盖
  ⇒ 条子比注册表宽（授权面越界）。
- `allowlisted_prefix_without_a_ticket`：白名单某个条目的字面前缀没有任何条子模式覆盖
  ⇒ 条子比注册表窄（受治侧跑不动，且拒绝理由看起来像“命令不合法”）。
- `command_param_not_covered`：命令类工具的条子没有声明命令参数的模式
  ⇒ 参数一变旧授权失效（形状绑定），本次比对对它没有意义。
- `no_patterns_for_command_tools`：命令类条子一条参数模式都没声明
  ⇒ 空模式集不是“不限制”，是一个读不出意图的条子。
- `registry_hash_drift`：工具描述与已审核哈希不一致 ⇒ 该工具在平台上不可用，
  而且此刻比对的是一份平台上已经用不上的白名单（**没给 `--approved` 时本格不适用**）。

读不出来一律 `unavailable`（`count: null`，不是 0）：条子文件、注册表、
或某个工具的 `allowed_commands` 缺失时，那一格**没有读数**，不是"没有命中"。
这与 AGENTS 第 56 条「账本不存在 = 不适用」是同一条口径。

字面前缀怎么取（可证伪、不猜）
==============================

正则的"语言"不可判定地包含于另一个正则，所以这里只做**保守**的读法：

1. 先去掉锚点，以及**真正包住整串**的那一层组（(a|b)( .*)? 里第一个右括号不在末位 ⇒
   它只是第一个片段，不能当包围组剥掉）；
2. 把**无变量的并列组**（status|diff|log 那种）展开成多条模式——展开是唯一可靠的读法，
   取最长的一支会让另一支静默消失（越界的授权因此永远读不出来）；
3. 逐条取**确定匹配的字面文本**，遇到第一个可变部分（点号 / 星号 / 字符类 / 问号组 /
   量词 / 未闭合的括号）就停；顶层并列分支、组内变量、括号不平衡一律按
   「取不出前缀」记 unavailable；
4. 覆盖判据是**精确成员**（两侧都是字面前缀全集），不用「互为前缀」——
   实测 python -m pytest 是 uv run python -m pytest 的子串，用互为前缀会把一处缺口
   静默算成已覆盖。

因此本工具的读数是**可能漏、不会误报**（与 `AdapterConfig.layer_test_conflicts()` 同型）：
报出来的每一条都有真实前缀支撑；它**不**声称自己证明了"白名单与条子等价"。

自己也要能失败（AGENTS 第 45 条）
================================

验收夹具在 `tests/fixtures/approval_audit/`：`registry.yaml` 白名单比 `ok/approval.json`
宽一格，于是跑 `--registry ok/registry.yaml` 必须有命中、跑 `--registry registry.yaml`
必须 0 命中。变异证明写在 `tests/contract/test_approval_allowlist_audit.py` 里（真跑工具、
读它的 `--json` 载荷），不是"跑过了、是绿的"。

载荷自己的版本轴（AGENTS 第 55 条）
==================================

`APPROVAL_AUDIT_SCHEMA_VERSION = "1.0"`——本载荷第一次出现就带轴。

用法
====

    python tools/approval_allowlist_audit.py \
        --approval ../Comparison-test/Governance/.policy/approval.json \
        --registry ../Comparison-test/Governance/.policy/tool-registry.local.yaml \
        [--approved ...] [--json]

默认输出两行机器行：

1. `APPROVAL_ALLOWLIST_AUDIT: <四格计数> / tools=<n> patterns=<n>`；
2. `HITS: <四格合计> / <四格逐项> / tools=<n> patterns=<n>`——跨文件契约（只报告步骤读这一行）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from enforcement.approvals import ApprovalError, load_approvals  # noqa: E402
from enforcement.registry import load_registry  # noqa: E402

APPROVAL_AUDIT_SCHEMA_VERSION = "1.0"

# 一条模式最多允许的分支前缀数：超过就按"取不出"处理（宁可漏，不可猜）。
_MAX_PREFIXES = 8
# 前缀最短长度：1 个字符的"前缀"（例如 '^a'）没有分辨力，算"取不出"。
_MIN_PREFIX_CHARS = 2


class _Unavailable(Exception):
    """取不出字面前缀：按 unavailable 处理，不写 0、不写 false。"""


def _strip_anchors(pattern: str) -> str:
    """去掉锚点，以及**真正包住整串**的那一层组。

    判别一层组是不是包住整串：从左往右数括号深度，若深度在最后一个字符**之前**就回到 0，
    那它只是模式的第一个片段（例如 `^(a|b)( .*)?$`），不能当成包围组剥掉——
    否则 `^(python -m pytest|rm -rf)( .*)?$` 会被读成一个以变量开头的模式，
    前向那格于是永远取不出前缀（实测：该报的越界命中被漏掉）。
    """

    text = pattern.strip()

    def trim_anchors(value: str) -> str:
        for prefix in ("\\A", "^"):
            if value.startswith(prefix):
                value = value[len(prefix) :]
                break
        for suffix in ("\\Z", "$"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
                break
        return value

    def wrapped_body(value: str) -> Optional[str]:
        """`value` 若是"一个组恰好包住整串"，返回组内正文；否则 None。

                `(a|b)( .*)?` 里第一个 `)` 之后还有内容（深度归零却不在末位）⇒ 不是包围组；
                `(a|b)` 的 `)` 落在末位 ⇒ 是。前者不能剥，剥了会把正常模式读成
        "以变量开头"。
        """

        if value.startswith("(?:"):
            body = value[3:]
        elif value.startswith("("):
            body = value[1:]
        else:
            return None
        depth = 0
        index = 0
        while index < len(body):
            char = body[index]
            if char == "\\":
                index += 2
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return body[:index] if index == len(body) - 1 else None
                if depth < 0:
                    return None
            index += 1
        return None

    while True:
        text = trim_anchors(text)
        body = wrapped_body(text)
        if body is None:
            break
        text = body
    return trim_anchors(text)


TRAILING_PAREN_OUTSIDE_GROUP = "组外遇到右括号：不猜"
NESTED_GROUP = "组里嵌套组：不猜"
BOUNDARY_INSIDE_GROUP = "组内出现边界符 $：不猜"
VARIABLE_INSIDE_GROUP = "组内出现可变部分：不猜"
UNBALANCED_PARENS = "括号不平衡：不猜"
GROUP_NOT_CLOSED = "组在结尾前没闭合：不猜"
EMPTY_GROUP = "空组：不猜"
NO_PREFIX = "取不出足够长的字面前缀（模式以变量开头或整体是通配）"


def _literal_prefixes(pattern: str) -> list[str]:
    """一条模式（或注册表条目）的全部字面前缀；取不出就抛 `_Unavailable`。

    这是对外的那一个名字：`_strip_anchors` 去锚点、`_alternatives` 展开并列分支、
    `_literals` 逐条取前缀。三段分开是因为**每一段的保守边界都不同**：
    去锚点要认得出"哪个右括号才是包围组的"，展开只做无变量的组，取前缀遇到变量就停。
    """

    return _literals(pattern)


def _parse_prefix(text: str, pivot: str) -> tuple[str, bool]:
    """取字面前缀；pivot 是形状里的右边界（组内为右括号，否则是 $）。

    返回 (前缀, 是否已到边界)。到不了边界（$ 不在末尾、括号不平衡）时只返回前缀，
    由调用方按自己那一侧的规则决定要不要继续——不猜。
    转义序列按字面解释；遇到变量（. * + ? { } [ ]）就停在它前面。
    """

    out: list[str] = []
    index = 0
    depth = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            if index + 1 >= len(text):
                break
            nxt = text[index + 1]
            if nxt.isalnum() and nxt not in {"n", "t", "r"}:
                break
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
            index += 2
            continue
        if char == "(":
            if depth == 0:
                after = text[index + 1 :]
                if after.startswith("?:") and len(after) > 2 and after[2] in "?*+":
                    break
                if after[:1] in "?*+":
                    break
            depth += 1
            index += 1
            if depth == 1 and text.startswith("?:", index):
                index += 2
            continue
        if char == ")":
            depth -= 1
            if depth < 0 or pivot != ")":
                raise _Unavailable(TRAILING_PAREN_OUTSIDE_GROUP)
            if depth != 0:
                raise _Unavailable(NESTED_GROUP)
            return "".join(out), index == len(text) - 1
        if char == "$":
            if pivot != "$":
                raise _Unavailable(BOUNDARY_INSIDE_GROUP)
            return "".join(out), index == len(text) - 1
        if depth == 0 and char in ".*+?{}[]|":
            break
        if depth > 0 and char in ".*+?{}[]|":
            raise _Unavailable(VARIABLE_INSIDE_GROUP)
        out.append(char)
        index += 1
    if depth != 0:
        raise _Unavailable(UNBALANCED_PARENS)
    if pivot == ")" and not out:
        raise _Unavailable(GROUP_NOT_CLOSED)
    return "".join(out), False


def _alternatives(text: str) -> list[str]:
    """把字面并列组（如 status|diff|log）展开成模式列表，每个分支一条。

    三种组被忽略（原样留在模式里，不展开也不报错）：

    - 组被 `? * +` 修饰（如 `( .*)?`）：整组可有可无，不是必配前缀，与字面前缀无关；
    - 组里有变量（如 `( .*)`、`(a|b.*)`）：内容不是字面；
    - 空组。

    展开是唯一的可靠读法：取最长的一支会让另一支静默消失——实测这类模式若只取
    最长那支，越界的授权就永远读不出来。
    """

    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "(":
            if depth == 0:
                optional = False
                after = text[index + 1 :]
                for lead in ("?:", "?", "*", "+"):
                    if after.startswith(lead) and len(after) > len(lead):
                        optional = after[len(lead)] in "?*+"
                        break
                if optional:
                    start = index + 1
                else:
                    parts.append(text[start:index])
                    start = index + 1
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise _Unavailable(UNBALANCED_PARENS)
            if depth == 0:
                body = text[start:index]
                if "|" in body and not any(item in body for item in ".*+?{}["):
                    body_items = body[3:] if body.startswith("?:") else body
                    pieces = [item for item in body_items.split("|") if item]
                    if parts and pieces:
                        expanded: list[str] = []
                        for tail in parts:
                            for piece in pieces:
                                expanded.append(tail + piece)
                        parts = expanded
                start = index + 1
        index += 1
    if depth != 0:
        raise _Unavailable(UNBALANCED_PARENS)
    parts.append(text[start:])
    return parts


def _literals(pattern: str) -> list[str]:
    """一条模式的全部字面前缀（可能多条：并列分支各取一条）。

    每一条都只由确定匹配的字面文本组成，因此判据（精确成员）不会误报；
    取不出任何一条时报 _Unavailable，由调用方记成没有读数。
    """

    body = _strip_anchors(pattern)
    branches = _alternatives(body)
    collected: list[str] = []
    for branch in branches:
        prefix, _ = _parse_prefix(branch, "$")
        if len(prefix) >= _MIN_PREFIX_CHARS:
            collected.append(prefix)
    if not collected:
        raise _Unavailable(NO_PREFIX)
    return sorted(set(collected))


def _prefix_covered(candidate: str, allowed: Sequence[str]) -> bool:
    """候选字面前缀是不是**被**另一边的字面前缀覆盖：**精确相等**。

    这里刻意不用"互为前缀"：`python -m pytest` 是 `uv run python -m pytest` 的子串，
    互相前缀判据会把"裸 pytest 没签"这条缺口静默算成"已覆盖"（实测：缺口数被少算）。
    空白前缀也不当作通配（`"" in "任何串"` 为真，会把一切都算成覆盖）。
    """

    return candidate in set(allowed)


def _patterns_cover(left: Sequence[str], right: Sequence[str]) -> bool:
    """左侧模式的前缀集是否**双向**覆盖右侧：

    1. 左的每个前缀都在右里（左不比右宽）；
    2. 右的每个前缀都能被左的某个前缀覆盖（右不比左宽）。
    """

    if not left or not right:
        return False
    if not all(_prefix_covered(item, right) for item in left):
        return False
    return all(any(_prefix_covered(target, [item]) for item in left) for target in right)


def _allowlist_by_tool(registry: Any) -> dict[str, list[str]]:
    """工具 id -> allowed_commands（只收声明了非空白名单的命令类工具）。

    直接用**仓库自己的加载器**读出来的 `ToolSpec`：注册表是数据，形状与校验都在那边，
    本工具不另写一套解析（否则"读不出白名单"会变成一个安静的空集合）。
    """

    result: dict[str, list[str]] = {}
    for spec in registry.tools:
        patterns = [str(item) for item in spec.allowed_commands if str(item).strip()]
        if patterns:
            result[str(spec.id)] = patterns
    return result


def _command_param_names(registry: Any) -> dict[str, str]:
    """工具 id -> 命令参数名（声明了 command_param 的才算命令类）。"""

    result: dict[str, str] = {}
    for spec in registry.tools:
        if spec.command_param:
            result[str(spec.id)] = str(spec.command_param)
    return result


def _approval_drift(registry: Any, approved_available: bool) -> list[dict[str, Any]]:
    """已审核哈希与当前工具描述不一致的工具。

    **没给 `--approved`（没有已审核清单可读）时这一格不适用**：此时每个工具都"没有
    已审核哈希"，把它记成命中就是把"没读"写成了"读出来的问题"（AGENTS 第 56 条
    「账本不存在 = 不适用」同一条口径）。给了清单但清单里缺某个工具，那才是真命中。
    """

    if not approved_available:
        return []
    approved = getattr(registry, "approved", None) or {}
    items: list[dict[str, Any]] = []
    for spec in registry.tools:
        expected = approved.get(spec.id)
        if expected is None:
            items.append(
                {
                    "tool_id": spec.id,
                    "detail": "已审核清单里没有这个工具：改注册表后必须重新审核",
                }
            )
        elif str(expected) != spec.schema_hash:
            items.append(
                {
                    "tool_id": spec.id,
                    "approved_schema_hash": str(expected),
                    "current_schema_hash": spec.schema_hash,
                    "detail": (
                        "工具描述与已审核哈希不一致：该工具在平台上不可用，重新审核后本条才消失"
                    ),
                }
            )
    return items


def _record_params(record: Any) -> set[str]:
    patterns = getattr(record, "param_patterns", None) or {}
    return set(patterns)


def _analyse(
    approval_path: Path,
    registry_path: Path,
    approved_path: Optional[Path] = None,
) -> dict[str, Any]:
    try:
        loaded = load_registry(registry_path, approved_path=approved_path)
    except Exception as error:  # RegistryError 等：注册表读不出来就没有比对可言
        return {
            "status": "unavailable",
            "reason": f"注册表读不出来：{error}",
            "count": None,
            "items": [],
        }
    registry = loaded.registry
    allowlist = _allowlist_by_tool(registry)
    command_params = _command_param_names(registry)
    drift = _approval_drift(registry, approved_path is not None)

    try:
        records = load_approvals(approval_path)
    except (ApprovalError, FileNotFoundError, ValueError) as error:
        return {
            "status": "unavailable",
            "reason": f"审批文件读不出来：{error}",
            "count": None,
            "items": [],
        }

    pattern_outside: list[dict[str, Any]] = []
    missing_ticket: list[dict[str, Any]] = []
    param_not_covered: list[dict[str, Any]] = []
    no_patterns: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    pattern_count = 0

    for record in records:
        tool_id = str(record.tool_id)
        declared = _record_params(record)
        if tool_id not in command_params:
            continue
        command_param = command_params[tool_id]
        if command_param not in declared:
            param_not_covered.append(
                {
                    "approval_id": record.approval_id,
                    "tool_id": tool_id,
                    "detail": (
                        f"条子没有声明命令参数 {command_param!r} 的模式："
                        "参数一变旧授权立即失效，本次前缀比对对它没有意义"
                    ),
                }
            )
            if not declared:
                no_patterns.append(
                    {
                        "approval_id": record.approval_id,
                        "tool_id": tool_id,
                        "detail": "这条命令类条子没有声明任何参数模式",
                    }
                )
            continue
        allowed_raw = allowlist.get(tool_id)
        if not allowed_raw:
            unavailable.append(
                {
                    "record": f"{record.approval_id}:{tool_id}",
                    "reason": "注册表里这个工具没有 allowed_commands（不是 0 条，是读不出来）",
                }
            )
            continue

        allowed_prefixes: list[str] = []
        for pattern in allowed_raw:
            try:
                allowed_prefixes.extend(_literal_prefixes(pattern))
            except _Unavailable as error:
                unavailable.append(
                    {
                        "record": f"registry:{tool_id}",
                        "pattern": pattern,
                        "reason": f"白名单条目取不出字面前缀：{error}",
                    }
                )

        for name, pattern in sorted(record.param_patterns.items()):
            if name != command_param:
                continue
            pattern_count += 1
            try:
                candidates = _literal_prefixes(pattern)
            except _Unavailable as error:
                unavailable.append(
                    {
                        "record": f"{record.approval_id}:{tool_id}",
                        "pattern": pattern,
                        "reason": f"条子模式取不出字面前缀：{error}",
                    }
                )
                continue
            for candidate in candidates:
                if allowed_prefixes and not _prefix_covered(candidate, allowed_prefixes):
                    pattern_outside.append(
                        {
                            "approval_id": record.approval_id,
                            "tool_id": tool_id,
                            "pattern": pattern,
                            "prefix": candidate,
                            "detail": (
                                f"条子的前缀 {candidate!r} 没有任何白名单条目覆盖："
                                "授权面越过了注册表声明的边界"
                            ),
                        }
                    )

        # 反向：白名单每条模式都要有一张条子模式覆盖得到。
        #
        # 比对的是**模式层面**的覆盖，不是逐条前缀：白名单里 `^uv run python -m pytest( .*)?$`
        # 与 `^python -m pytest( .*)?$` 的前缀互为前缀（后者是前者的子串），
        # 若逐条前缀判"有没有被覆盖"，后者会被前者顺带算成"覆盖过了"——
        # 于是 13 个缺口被数成 12 个（实测：`uv run python -m pytest` 那条先算，
        # 把裸 pytest 那条吞了）。判据取更严的一侧：**两边的前缀集要互相覆盖**。
        ticket_patterns = [
            pattern
            for name, pattern in sorted(record.param_patterns.items())
            if name == command_param
        ]
        ticket_prefixes: list[str] = []
        available_ticket_patterns = 0
        for ticket_pattern in ticket_patterns:
            try:
                ticket_prefixes.extend(_literal_prefixes(ticket_pattern))
                available_ticket_patterns += 1
            except _Unavailable:
                continue
        for pattern in allowed_raw:
            try:
                prefixes = _literal_prefixes(pattern)
            except _Unavailable:
                continue
            if not available_ticket_patterns:
                continue
            if _patterns_cover(prefixes, ticket_prefixes):
                continue
            missing_ticket.append(
                {
                    "approval_id": record.approval_id,
                    "tool_id": tool_id,
                    "allowlist_pattern": pattern,
                    "prefix": prefixes[0],
                    "detail": (
                        f"白名单条目 {pattern!r}（前缀 {prefixes[0]!r}）没有任何条子模式覆盖："
                        "受治侧这条命令会被审批层拒掉，而理由看起来像"
                        "「命令不合法」——其实是条子落后于注册表"
                    ),
                }
            )

    red_conditions = {
        "pattern_outside_the_allowlist": _grid(
            pattern_outside,
            "条子的字面前缀要落在注册表白名单里",
            "注册表新增了允许的命令形态，而条子没有跟着重签",
        ),
        "allowlisted_prefix_without_a_ticket": _grid(
            missing_ticket,
            "白名单的每条字面前缀都要有至少一张条子覆盖",
            "条子比注册表窄：受治侧跑不动，且拒绝理由指向“命令不合法”",
        ),
        "command_param_not_covered": _grid(
            param_not_covered,
            "命令类工具的条子必须声明命令参数的模式",
            "条子声明的是别的参数名，形状绑定会让它永远匹配不上",
        ),
        "no_patterns_for_command_tools": _grid(
            no_patterns,
            "命令类工具的条子必须至少声明一条参数模式",
            "空模式集不是“不限制”，是一个读不出意图的条子",
        ),
        "registry_hash_drift": _grid(
            drift,
            "工具描述要与已审核哈希一致（改注册表必须重新审核）；没给 --approved 时本格不适用",
            "注册表被改过而没重新审核：该工具在平台上不可用，"
            "而且此刻比对的是一份平台上已经用不上的白名单",
        ),
    }
    # 反向那格按"缺口"记账，不按"条子 × 缺口"记账：同一个白名单条目对三张条子都没覆盖，
    # 那是一个缺口出现三次，不是三个缺口（否则条子分族之后命中数会随条子数量线性膨胀，
    # 读数立刻变得不可用）。
    for name, grid in red_conditions.items():
        if not grid.get("items"):
            continue
        if name != "allowlisted_prefix_without_a_ticket":
            continue
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in grid["items"]:
            key = (item.get("tool_id"), item.get("prefix"))
            unique.setdefault(key, item)
        grid["items"] = sorted(
            unique.values(), key=lambda entry: (str(entry.get("tool_id")), str(entry.get("prefix")))
        )
        grid["count"] = len(grid["items"])
    hits = sum(
        int(grid.get("count") or 0)
        for grid in red_conditions.values()
        if grid.get("count") is not None
    )
    unavailable_grid = (
        {
            "status": "unavailable",
            "count": None,
            "items": unavailable,
            "reason": "有模式/条目取不出字面前缀：那一格没有读数（不是 0 命中）",
        }
        if unavailable
        else {"status": "available", "count": 0, "items": []}
    )
    return {
        "status": "available",
        "hits": hits,
        "tool_count": len({str(record.tool_id) for record in records}),
        "pattern_count": pattern_count,
        "records": [record.approval_id for record in records],
        "red_conditions": red_conditions,
        "unavailable": unavailable_grid,
    }


def _grid(items: list[dict[str, Any]], red_when: str, why: str) -> dict[str, Any]:
    return {
        "status": "available",
        "count": len(items),
        "items": items,
        "red_when": red_when,
        "why": why,
        "enforced": False,
        "would_exit_code": 1,
        "promote_when": "跑过 N≥1 次且四格合计 0 命中，且 0 命中来自至少一次真实读数",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="approval_allowlist_audit.py",
        description="审批条子 × 注册表白名单：跨源互证（只报告，退出码恒 0）",
    )
    parser.add_argument("--approval", required=True, help="审批存储（approval.json）路径")
    parser.add_argument("--registry", required=True, help="工具注册表（tool-registry*.yaml）路径")
    parser.add_argument(
        "--approved",
        default=None,
        help="已审核哈希清单路径（给了就跑 registry_hash_drift 那一格）",
    )
    parser.add_argument("--json", action="store_true", help="输出完整机读载荷")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report = _analyse(
        Path(args.approval),
        Path(args.registry),
        None if args.approved is None else Path(args.approved),
    )
    report["schema_version"] = APPROVAL_AUDIT_SCHEMA_VERSION
    report["approval"] = str(args.approval)
    report["registry"] = str(args.registry)
    report["approved"] = args.approved

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if report.get("status") != "available":
        print(f"APPROVAL_ALLOWLIST_AUDIT: unavailable / {report.get('reason')}")
        print("HITS: unavailable / tools=unavailable patterns=unavailable")
        return 0

    grids = report["red_conditions"]
    order = (
        "pattern_outside_the_allowlist",
        "allowlisted_prefix_without_a_ticket",
        "command_param_not_covered",
        "no_patterns_for_command_tools",
        "registry_hash_drift",
    )
    detail = " / ".join(f"{name}={grids[name]['count']}" for name in order)
    print(
        "APPROVAL_ALLOWLIST_AUDIT: "
        f"{report['hits']} hits / tools={report['tool_count']} patterns={report['pattern_count']}"
    )
    unavailable = report["unavailable"]
    if unavailable["count"] is None:
        print(
            f"HITS: unavailable / {detail} / tools={report['tool_count']} "
            f"patterns={report['pattern_count']} / unreadable={len(unavailable['items'])}"
        )
    else:
        print(
            f"HITS: {report['hits']} / {detail} / tools={report['tool_count']} "
            f"patterns={report['pattern_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

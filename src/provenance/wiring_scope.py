"""边界裁定：adapters/wiring-scope.yaml 的加载与校验（方案 §3.5 的最小形态）。

这份文件回答的是「平台治理什么、不治理什么」，而且要求每一条不治理的声明都写清
owner / reason / consequence / expires_at——否则「不在范围内」就成了一张永不过期的
空白支票（方案 §5.2 R-b：静默放宽必须在数据里声明，且带到期日）。

本模块只做**加载与校验**：报告（三数与五个差集）、以及与 adapters.cli wiring 的合并
属于台阶 4/5，不在这里。

口径与仓库其余数据文件一致：未知字段、未知取值、空理由、重复 id 一律**加载期报错**，
不静默忽略、不默认放行。

**schema "2"（2026-10-01 裁定①，24 号 §8.3）**：加载器**同时接受 "1" 和 "2"**，本版新增的字段
（顶层 `channel_kinds`，条目 `covers` / `governs_tree` / `tree_ref`）**一律可选**，
并且**不新增任何加载期 FATAL**：一个 schema "1" 的合法文件在 "2" 的加载器下必须照样加载。
对**新字段**的未知枚举取值仍按核心约束 3 报错（例如 `governs_tree: othr`）——那条 FATAL 与
既有的 `decision` 是同一类，不是新的加载条件。

**裁定④（2026-10-01，24 号 §8.4 / 23 号 §15.1）**：`governs_tree` 的读法改过一次，仍在 "2" 内、
**不升版**（1.3 尚未发布，同 `policy.check` 1.2 的先例）：**写了**就按写的算，**没写就是 `unknown`**，
不再默认 `self`。"默认 `self` + 证据 `other`"这对矛盾按 24 号 §2.1 的边界**不进五个差集**，
会静默存在；而"拿不出证据写 unknown"与裁定③ 是同一条纪律。加载期 FATAL 一条没加：
`unknown` 不是一个可以写进声明文件的取值（写了会被拒绝），它只是**读取侧**对"没写"的翻译。
"""

from __future__ import annotations

import datetime as _datetime
import re
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "2"
# 兼容读法（裁定①）：这两个版本都接受，且**新字段一律可选**；"1" 的文件里不会有本版新增字段。
ACCEPTED_SCHEMA_VERSIONS: Tuple[str, ...] = ("1", "2")
# decision 的三个取值：在范围内 / 不在范围内 / 预期缺席（方案 §3.5）。
DECISIONS: Tuple[str, ...] = ("in_scope", "out_of_scope", "expected_absent")
# governs_tree 的**两个可写取值**：这条声明覆盖的通道治理的是**本仓库这棵树**，
# 还是**有意治理另一棵树**。**没写**不属于这两个值里的任何一个（见下一条）。
GOVERNS_TREE_VALUES: Tuple[str, ...] = ("self", "other")
# 没写 `governs_tree` 时**读取侧**的取值（2026-10-01 裁定④）：不替声明认领 `self`。
GOVERNS_TREE_UNWRITTEN = "unknown"
# tree_ref 允许的**唯一**非路径取值：有意治理工作区之外的一棵树（只放指针，不放正文）。
TREE_REF_OUTSIDE = "<outside-workspace>"


class WiringScopeError(Exception):
    """边界声明读不了或不合法：调用方必须失败关闭。"""


_CANONICAL_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _require_date(value: str, *, field: str) -> str:
    # 先钉死**规范**形态：date.fromisoformat 还接受 20261001（基本格式）、2026-W40-1（周日期）
    # 这类写法，放它们进来会让本文件的日期与仓库其余数据文件（一律 YYYY-MM-DD）口径分叉，
    # 而"口径一致"正是这条校验存在的理由。
    if _CANONICAL_DATE.fullmatch(value) is None:
        raise ValueError(
            f"{field} 必须是规范 ISO 日期 YYYY-MM-DD，得到 {value!r}"
            "（date.fromisoformat 还接受 20261001 / 2026-W40-1 这类写法，这里不接受）"
        )
    try:
        _datetime.date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} 必须是 ISO 日期（YYYY-MM-DD），得到 {value!r}") from error
    return value


class Renewal(BaseModel):
    """一次续期：什么时候、凭什么续的。"""

    model_config = ConfigDict(extra="forbid")

    at: str
    note: str

    @field_validator("at")
    @classmethod
    def _at(cls, value: str) -> str:
        return _require_date(value, field="renewals.at")

    @field_validator("note")
    @classmethod
    def _note(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("renewals.note 不能为空")
        return value


class ScopeEntry(BaseModel):
    """一条边界声明。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    decision: str
    kind: str
    owner: str
    reason: str
    consequence: str
    expires_at: str | None = None
    renewals: Tuple[Renewal, ...] = ()
    # —— schema "2" 新增（一律可选；裁定①）——
    # 显式覆盖：glob 作用于发现侧（adapters.cli wiring）的 channel_id。显式覆盖**优先于**
    # kind 档（24 号 §2.1 规则 1）：同档多条声明判决不同时，只有显式覆盖能定夺，不猜。
    covers: Tuple[str, ...] = ()
    # 这条声明覆盖的通道是不是**有意**治理另一棵树。**没写 = None**（不是 self）：
    # 读取侧用 `declared_governs_tree()` 取 `unknown`（裁定④；在 1.3 内改正、不升版）。
    governs_tree: str | None = None
    # 只放指针（仓库相对路径，或 <outside-workspace>），不放正文、不放绝对路径（第 16/34 条）；
    # governs_tree=self 时不写。
    tree_ref: str | None = None

    @field_validator("decision")
    @classmethod
    def _decision(cls, value: str) -> str:
        if value not in DECISIONS:
            raise ValueError(
                f"未知 decision {value!r}：只接受 {' / '.join(DECISIONS)}（不猜、不兜底）"
            )
        return value

    @field_validator("id", "kind", "owner", "reason", "consequence")
    @classmethod
    def _non_empty(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} 不能为空")
        return value

    @field_validator("expires_at")
    @classmethod
    def _expires(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_date(value, field="expires_at")

    @field_validator("governs_tree")
    @classmethod
    def _tree(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in GOVERNS_TREE_VALUES:
            raise ValueError(
                f"未知 governs_tree {value!r}：只接受 {' / '.join(GOVERNS_TREE_VALUES)}"
                "（未知枚举不静默忽略——核心约束 3；这不是新增的加载条件，与 decision 同类）。"
                "`unknown` 是**没写**时读取侧的取值，不是可写取值（裁定④）"
            )
        return value

    @field_validator("tree_ref")
    @classmethod
    def _tree_ref(cls, value: str | None) -> str | None:
        """tree_ref 只放**指针**：仓库相对路径，或 <outside-workspace>。

        第 16/34 条对它的承诺（不放正文、不放绝对路径）必须与相邻字段一样被**校验**，
        不能只写在注释里：绝对路径 / 路径穿越 / 一段说明文字过去都能原样加载，
        下游若拿它当路径解析就会被带到工作区之外。
        """

        if value is None:
            return None
        if value == TREE_REF_OUTSIDE:
            return value
        if not value.strip() or value != value.strip():
            raise ValueError(f"tree_ref 不能为空或带首尾空白，得到 {value!r}")
        # chr(92) 是反斜杠：Windows 形态的绝对路径 / 分隔符不属于"仓库相对路径"。
        if ":" in value or value.startswith("/") or chr(92) in value:
            raise ValueError(
                f"tree_ref 只放仓库相对路径或 {TREE_REF_OUTSIDE}，得到绝对/平台路径 {value!r}"
            )
        parts = value.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ValueError(f"tree_ref 不能含空段 / . / ..（路径穿越），得到 {value!r}")
        if any(re.fullmatch(r"[A-Za-z0-9._-]+", part) is None for part in parts):
            raise ValueError(
                f"tree_ref 只放路径形态的指针，得到 {value!r}："
                "正文、说明性文字、含空格的写法都不属于这里"
            )
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "ScopeEntry":
        if self.governs_tree == "self" and self.tree_ref is not None:
            raise ValueError(
                f"{self.id}: governs_tree=self 时不得写 tree_ref——"
                "本仓库这棵树的指针没有意义，写了就是一条自相矛盾的声明"
            )
        if self.decision == "in_scope":
            if self.expires_at is not None:
                raise ValueError(
                    f"{self.id}: 在范围内的声明不该有过期日（它不会自动失效）；"
                    "要让它失效就改 decision"
                )
            return self
        if self.expires_at is None:
            raise ValueError(
                f"{self.id}: {self.decision} 必须写 expires_at——"
                "没有到期日的「不在范围内」是一张永不过期的空白支票（方案 §3.5）"
            )
        return self

    def declared_governs_tree(self) -> str:
        """这条声明**声称**治理哪棵树：写了就按写的算，**没写一律 `unknown`**（裁定④）。

        `unknown` 不是可写取值（写了会被加载期拒绝）——它是**读取侧**对「没写」的翻译：
        拿不出证据就不替声明认领 `self`。`tree.declared_by` 仍然写覆盖它的那条声明 id，
        因此「没有声明覆盖」（此时 declared_by 是 null）与「声明覆盖了但没写 governs_tree」
        分得开。
        """

        return self.governs_tree if self.governs_tree is not None else GOVERNS_TREE_UNWRITTEN


class WiringScope(BaseModel):
    """adapters/wiring-scope.yaml 的整体形状。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    scope: Tuple[ScopeEntry, ...]
    # schema "2" 新增（可选）：发现侧 kind → 声明侧 kind 的**数据**映射（24 号 §2.1 规则 2）。
    # 它把"按 kind 分档"变成可读的声明而不是代码里的写死分支；没有映射的发现 kind
    # 一律写 decision=undeclared，不猜。
    channel_kinds: Dict[str, str] = Field(default_factory=dict)

    @field_validator("channel_kinds")
    @classmethod
    def _channel_kinds(cls, value: Dict[str, str]) -> Dict[str, str]:
        """键与值都必须是非空字符串。

        空值 / 拼错的值不会报错，只会让该通道落到 decision=undeclared——一个字的手误
        就悄悄取消了治理，与本模块"未知取值一律加载期报错、不静默忽略"的口径相反。
        """

        for key, mapped in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"channel_kinds 的键必须是非空字符串，得到 {key!r}")
            if not isinstance(mapped, str) or not mapped.strip():
                raise ValueError(
                    f"channel_kinds[{key!r}] 的值必须是非空字符串，得到 {mapped!r}："
                    "空值会让该通道静默落到 undeclared"
                )
        return value

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value: str) -> str:
        if value not in ACCEPTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"未知 schema_version {value!r}：只接受 "
                f"{' / '.join(repr(item) for item in ACCEPTED_SCHEMA_VERSIONS)}"
                "（消费方看不懂必须拒绝；两个版本的差异只在**可选**字段的有无）"
            )
        return value

    @model_validator(mode="after")
    def _unique_ids(self) -> "WiringScope":
        seen: set = set()
        duplicates: list = []
        for entry in self.scope:
            if entry.id in seen:
                duplicates.append(entry.id)
            seen.add(entry.id)
        if duplicates:
            raise ValueError("重复的声明 id：" + "、".join(sorted(duplicates)))
        return self

    def as_json(self) -> Dict[str, Any]:
        counts = {decision: 0 for decision in DECISIONS}
        for entry in self.scope:
            counts[entry.decision] += 1
        return {
            "schema_version": self.schema_version,
            "declared": len(self.scope),
            "by_decision": counts,
            "ids": [entry.id for entry in self.scope],
            # schema "2" 的新字段：**只列写了的那些**（空 = 没有人写，不是"写空了"）。
            "channel_kinds": dict(sorted(self.channel_kinds.items())),
            "covers": {entry.id: list(entry.covers) for entry in self.scope if entry.covers},
            # **只列写了的那些**（含显式写的 `self`）：裁定④ 之后"写了 self"与"没写"
            # 分得开——没写是读取侧的 `unknown`，不出现在这份摘要里。
            "governs_tree": {
                entry.id: entry.governs_tree
                for entry in self.scope
                if entry.governs_tree is not None
            },
        }


def load_wiring_scope(path: Path | str) -> WiringScope:
    """读并校验边界声明；任何问题都抛 WiringScopeError（含字段路径，便于直接改）。"""

    target = Path(path)
    if not target.is_file():
        raise WiringScopeError(f"边界声明不存在：{target}")
    try:
        document = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise WiringScopeError(f"{target}: 读不了或不是合法 YAML（{error}）") from error
    if not isinstance(document, dict):
        raise WiringScopeError(f"{target}: 顶层必须是映射，得到 {type(document).__name__}")
    try:
        return WiringScope.model_validate(document)
    except ValidationError as error:
        lines = []
        for item in error.errors():
            where = ".".join(str(part) for part in item["loc"]) or "<root>"
            lines.append(f"{where}: {item['msg']}")
        raise WiringScopeError(f"{target}: " + "；".join(lines)) from error

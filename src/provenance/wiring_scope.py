"""边界裁定：adapters/wiring-scope.yaml 的加载与校验（方案 §3.5 的最小形态）。

这份文件回答的是「平台治理什么、不治理什么」，而且要求每一条不治理的声明都写清
owner / reason / consequence / expires_at——否则「不在范围内」就成了一张永不过期的
空白支票（方案 §5.2 R-b：静默放宽必须在数据里声明，且带到期日）。

本模块只做**加载与校验**：报告（三数与五个差集）、以及与 adapters.cli wiring 的合并
属于台阶 4/5，不在这里。

口径与仓库其余数据文件一致：未知字段、未知取值、空理由、重复 id 一律**加载期报错**，
不静默忽略、不默认放行。
"""

from __future__ import annotations

import datetime as _datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

SCHEMA_VERSION = "1"
# decision 的三个取值：在范围内 / 不在范围内 / 预期缺席（方案 §3.5）。
DECISIONS: Tuple[str, ...] = ("in_scope", "out_of_scope", "expected_absent")


class WiringScopeError(Exception):
    """边界声明读不了或不合法：调用方必须失败关闭。"""


def _require_date(value: str, *, field: str) -> str:
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

    @model_validator(mode="after")
    def _consistent(self) -> "ScopeEntry":
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


class WiringScope(BaseModel):
    """adapters/wiring-scope.yaml 的整体形状。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    scope: Tuple[ScopeEntry, ...]

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value: str) -> str:
        if value != SCHEMA_VERSION:
            raise ValueError(
                f"未知 schema_version {value!r}：只接受 {SCHEMA_VERSION!r}（消费方看不懂必须拒绝）"
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

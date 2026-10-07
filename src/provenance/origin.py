"""归因闭集与核验前置（方案 §3.4 / §4 台阶 2 · 判据 R-g）。

它回答的是**一个**问题：这条失败理由指着谁？

为什么要有它（方案 §2 的母体）：失败关闭只完成了一半——另一半是「告诉人一个对的原因」。
实测过的错法是把「Hook 起不来」翻译成「Node 没装」（14 号文档 §5 Q6：Node 的 spawn 在
**cwd 不存在**时把 ENOENT 归给**可执行文件**，而那个可执行文件存在且可执行）。所以：

1. **origin 是闭集**：只能是 `platform.*` / `agent_runtime.*` / `host.*` / `project.*` /
   `unknown_origin` 五族之一，未知取值一律报错（与平台其他「未知一律拒绝」同一条纪律）。
2. **每个 origin 必须携带** owner / object{kind,value,source} /
   observation{method,result,verified,verified_at,run_scoped} / fix / causal_link。
   **写不出 fix 的 origin 不许存在**——"出了问题"而不是"怎么改"的理由等于没归因。
3. **核验前置**：每条指控在写进理由之前先执行它的证伪判据（报「文件不存在」先 stat 它）。
   核验**允许证伪自己人**：判据不成立时只能落 `unknown_origin`，**不许换一个对象继续指控**。
4. **核验记录无权威**：它不是第二份判定，消费者不得据它 allow/block（所以它只进审计与
   诊断行，不进 decision / violations）。

纯标准库、不 import 任何平台其他包：它是被两侧（Python Hook 与 JS 插件）共同实现的形状，
放 `src/provenance/` 而不是内核目录，理由与 §3.1 的针脚相同（内核目录里改一行必须变红）。
"""

from __future__ import annotations

import datetime as _clock
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

__all__ = [
    "ORIGIN_FAMILIES",
    "ORIGIN_VALUES",
    "OBSERVATION_METHODS",
    "CAUSAL_LINKS",
    "OBJECT_KINDS",
    "Origin",
    "OriginError",
    "ORIGIN_OBJECT_KIND",
    "build_origin",
    "is_known_origin",
    "unknown_origin",
]


class OriginError(ValueError):
    """归因闭集违约：未知取值、缺字段、空 fix 一律在这里报错。"""


# 五族。**闭集**：新增一族要改这里，并且必须同步两处消费者（Python Hook 与 JS 插件）。
ORIGIN_FAMILIES: tuple[str, ...] = (
    "platform",
    "agent_runtime",
    "host",
    "project",
    "unknown_origin",
)

# 本台阶真正实现过、有核验判据的取值。不在表里的一律拒绝：宁可报 unknown_origin，
# 也不允许"写一个看起来更精确、实际没有任何判据支撑"的 origin。
ORIGIN_VALUES: tuple[str, ...] = (
    "platform.config_unreadable",
    "platform.evidence_unavailable",
    "project.workdir_missing",
    "host.workdir_unreadable",
    "agent_runtime.spawn_denied",
    "agent_runtime.spawn_failed",
    "unknown_origin",
)

OBSERVATION_METHODS: tuple[str, ...] = ("stat", "load", "spawn", "read", "none")

CAUSAL_LINKS: tuple[str, ...] = ("proven", "unproven")

# object.kind：被指控的东西是哪一类。用闭集而不是自由文本，读者才能按类别整理。
OBJECT_KINDS: tuple[str, ...] = (
    "path",
    "file",
    "command",
    "workdir",
    "runtime",
    "unknown",
)

# 归因记录自己的载荷版本（与 AUDIT_SCHEMA_VERSION / VERDICT_SCHEMA_VERSION 无关）。
ORIGIN_OBJECT_KIND = "platform.attribution"

_UNKNOWN_FIX = "补一条可执行的核验：把失败现场的那个路径 / 命令 / 配置显式交给一次 stat / load，再据此重新归因"


def _now_iso() -> str:
    """观测时刻（UTC，秒级）。**必须来自真实调用**：核验没有时间戳就等于没有观测。"""

    return _clock.datetime.now(_clock.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def family_of(origin: str) -> str:
    """取 origin 的族（`project.workdir_missing` → `project`）。"""

    return origin if origin == "unknown_origin" else str(origin).split(".", 1)[0]


def is_known_origin(value: object) -> bool:
    """这个取值在不在闭集里（未知一律 False，调用方据此落 unknown_origin）。"""

    return isinstance(value, str) and value in ORIGIN_VALUES


@dataclass(frozen=True)
class Origin:
    """一条结构化归因。字段形状是**跨语言契约**（JS 侧逐字实现同一份）。"""

    origin: str
    owner: str
    object_kind: str
    object_value: str
    object_source: str
    method: str
    result: str
    verified: bool
    fix: str
    causal_link: str
    verified_at: str = ""
    run_scoped: bool = True

    def __post_init__(self) -> None:
        if not is_known_origin(self.origin):
            raise OriginError(f"origin 不在闭集里：{self.origin!r}；闭集={ORIGIN_VALUES}")
        family = family_of(self.origin)
        if family not in ORIGIN_FAMILIES:
            raise OriginError(f"origin 的族不在闭集里：{self.origin!r}")
        if self.object_kind not in OBJECT_KINDS:
            raise OriginError(f"object.kind 不在闭集里：{self.object_kind!r}")
        if self.method not in OBSERVATION_METHODS:
            raise OriginError(f"observation.method 不在闭集里：{self.method!r}")
        if self.causal_link not in CAUSAL_LINKS:
            raise OriginError(f"causal_link 不在闭集里：{self.causal_link!r}")
        for name in ("owner", "object_value", "object_source", "result"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise OriginError(f"{name} 必须是非空字符串，得到 {value!r}")
        # 写不出 fix 的 origin 不许存在（方案 §3.4 的原话）。
        if not isinstance(self.fix, str) or not self.fix.strip():
            raise OriginError("fix 不能为空：写不出修复动作的 origin 不许存在")
        if not isinstance(self.verified, bool) or not isinstance(self.run_scoped, bool):
            raise OriginError("verified / run_scoped 必须是布尔值")
        # unknown_origin 是"归因没有建立起来"的落点（方案 §3.4：核验证伪了自己人）。
        # 它与 verified=True / causal_link="proven" 自相矛盾：unknown_origin() 助手一直按这条
        # 纪律写，但直接构造能绕过去——不变式必须在**构造期**成立，不能靠调用方自觉。
        if self.origin == "unknown_origin":
            if self.causal_link != "unproven":
                raise OriginError(
                    "unknown_origin 的 causal_link 只能是 unproven，得到 "
                    + repr(self.causal_link)
                    + "（归因没有建立起来）"
                )
            if self.verified:
                raise OriginError("unknown_origin 不许 verified=True：核验没有建立任何因果链")

    def to_payload(self) -> dict[str, Any]:
        """进审计 / 诊断行的形状（键固定、顺序稳定、可直接 JSON 序列化）。"""

        return {
            "kind": ORIGIN_OBJECT_KIND,
            "origin": self.origin,
            "owner": self.owner,
            "object": {
                "kind": self.object_kind,
                "value": self.object_value,
                "source": self.object_source,
            },
            "observation": {
                "method": self.method,
                "result": self.result,
                "verified": self.verified,
                "verified_at": self.verified_at or _now_iso(),
                "run_scoped": self.run_scoped,
            },
            "fix": self.fix,
            "causal_link": self.causal_link,
        }


def build_origin(
    *,
    origin: str,
    owner: str,
    object_kind: str,
    object_value: str,
    object_source: str,
    method: str,
    result: str,
    verified: bool,
    fix: str,
    causal_link: str,
    verified_at: str = "",
    run_scoped: bool = True,
) -> Origin:
    """唯一构造入口（闭集与硬规则都在 `Origin.__post_init__` 里）。"""

    return Origin(
        origin=origin,
        owner=owner,
        object_kind=object_kind,
        object_value=object_value,
        object_source=object_source,
        method=method,
        result=result,
        verified=verified,
        fix=fix,
        causal_link=causal_link,
        verified_at=verified_at or _now_iso(),
        run_scoped=run_scoped,
    )


def unknown_origin(
    *,
    reason: str,
    owner: str = "platform.attribution",
    object_kind: str = "unknown",
    object_value: str = "unverified",
    object_source: str = "核验判据不成立",
    method: str = "none",
) -> Origin:
    """核验证伪了自己人时的落点：**只能**落这里，不许换一个对象继续指控。

    `causal_link` 恒为 `unproven`——这一条正是它的意思：归因没有建立起来。
    """

    return build_origin(
        origin="unknown_origin",
        owner=owner,
        object_kind=object_kind,
        object_value=object_value,
        object_source=object_source,
        method=method,
        result=reason,
        verified=False,
        fix=(
            "先让核验可执行：把失败现场的那个输入（路径 / 命令 / 配置）显式交给一次 stat / load，"
            "再据观测结果重新归因；在此之前不要声称任何对象"
        ),
        causal_link="unproven",
    )


def payload_is_well_formed(payload: Mapping[str, Any]) -> bool:
    """给跨语言契约用：一份 origin 载荷是不是**恰好**长成契约的样子。

    "恰好"是故意严的：多一个键、少一个键、`unknown` 嵌套不对，都算违约——
    两侧各自演化时，最先坏掉的就是这种没有检查的自由度。
    """

    if not isinstance(payload, Mapping):
        return False
    if set(payload) != {"kind", "origin", "owner", "object", "observation", "fix", "causal_link"}:
        return False
    if payload.get("kind") != ORIGIN_OBJECT_KIND:
        return False
    obj = payload.get("object")
    if not isinstance(obj, Mapping) or set(obj) != {"kind", "value", "source"}:
        return False
    obs = payload.get("observation")
    if not isinstance(obs, Mapping) or set(obs) != {
        "method",
        "result",
        "verified",
        "verified_at",
        "run_scoped",
    }:
        return False
    if not is_known_origin(payload.get("origin")):
        return False
    if obj.get("kind") not in OBJECT_KINDS:
        return False
    if obs.get("method") not in OBSERVATION_METHODS:
        return False
    if payload.get("causal_link") not in CAUSAL_LINKS:
        return False
    if not isinstance(payload.get("fix"), str) or not str(payload["fix"]).strip():
        return False
    if not isinstance(obs.get("verified"), bool) or not isinstance(obs.get("run_scoped"), bool):
        return False
    # 形状对不等于值合法：与 Origin.__post_init__ 的硬规则对齐。一份 owner="" /
    # object.value=null / observation.result=null 的 JS 载荷能过"恰好是契约形状"这一关，
    # 却会被 Python 构造器拒绝——跨语言校验器的意义正是在这里拦下它，而不是等下游
    # 重建 Origin 时才炸。
    for value in (payload.get("owner"), obj.get("value"), obj.get("source"), obs.get("result")):
        if not isinstance(value, str) or not value:
            return False
    # verified_at 必须来自真实调用：类型是字符串且非空（构造器与 to_payload 都保证非空）。
    if not isinstance(obs.get("verified_at"), str) or not obs.get("verified_at"):
        return False
    return True


_PATH_TOKEN_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/]|/)?[^\s'\"（）()，,；;：:]*"
    r"(?:dsh-adapter\.yaml|hooks\.json|validators\.yaml|tool-registry\.yaml|wiring-scope\.yaml|"
    r"[\w.\-]+\.ya?ml|[\w.\-]+\.json))"
)


def config_path_in(text: str) -> Optional[str]:
    """从一段失败原文里**尽力**取回被点名的配置文件路径。

    取不到就返回 None——调用方据此落 `unknown_origin`。这条纪律与 Q6 一致：
    宁可说"归不了因"，也不照抄一段猜出来的路径去指控别的对象。
    """

    if not isinstance(text, str) or not text:
        return None
    match = _PATH_TOKEN_RE.search(text)
    if match is None:
        return None
    candidate = match.group("path").strip().strip("'\"")
    return candidate or None

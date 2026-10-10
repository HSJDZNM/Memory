"""人工审批记录：绑定一次具体调用（默认、更严格）或绑定"一类调用"（可选档）。

Phase 4 文档要求"参数绑定授权与人工门禁"。这里刻意不做任何"自然语言批准"的解析：

- 审批是一条结构化记录（JSON），由人工门禁或审批系统产生；
- 它有自己的有效期，过期即失效；
- 未知字段、未知 binding、自相矛盾的字段组合一律在加载期报错。

两种绑定档位（binding）：

1. **action（默认，单次绑定，更严格）**：逐位绑定 action_hash 与 action_id。
   action_hash 覆盖工具 schema、规范化参数、主体、权限与上下文摘要，
   因此"换参数继续用旧条子"在数学上不可能；一次消费之后即失效。
2. **pattern（模式化）**：绑定"工具 + 规范化参数模式 + 主体/角色 + 生效窗口 + 次数上限"。
   它解决的是一个真实可用性缺陷：action_id / tool_use_id 是 Agent 运行时每次现生成的，
   人签条子时不可能知道下一个编号，于是"同一条命令、只换调用编号"条子立刻作废，
   受治理的会话连 pytest 都跑不了。

**模式化审批不削弱任何防重放性质**：

- 按 action_id 的重复拦截完全不变，由台账与审计链两处把关（与审批无关）；
- 次数上限由台账**先原子占用、再执行**，写进审计；用尽 / 过期 / 主体不符一律拒绝；
- 参数一变、模式匹配不上即拒绝（旧授权自动失效）；**模式必须覆盖本次请求的全部参数**：
  只声明一部分等于给未声明的参数（例如 exec.pwsh 的 workdir / sandbox_permissions）
  留一张"跟着条子一起放行"的后门——有意放行的参数要显式写成通配模式；
- 单次绑定仍然是默认档，且不许与模式字段混写（自相矛盾的声明直接拒绝）。

授予者必须持有 repo.approve 权限——审批权与执行权分开，不能自己批自己。

**一个审批文件可以放多条记录**（1.2 起，见 `ApprovalSet`）：

- 动机是实测出来的：桌面端 GUI 的每个动作都包在 `run_code`（PTC 传输）里，
  子工具调用（write / edit / pwsh）由运行时逐个派发、逐个判定；而"一个文件一条记录"
  意味着名额只能给其中一个工具——给了 `run_code`，`exec.pwsh` 一律 `approval_invalid`；
  给了 `pwsh`，`run_code` 被拦，**整个会话冻结**（连读一个文件都进不去）。
- 于是加载期**按 `tool_id` 选择**记录（`select_approval`）：每个工具各持一份放行，互不挤占。
- 选择**不是判定**：选中的记录随后仍由 `verify_approval` 完整校验（工具 / 主体 / 时效 /
  角色 / 参数模式 / 次数）。选择只回答"该出示哪一张条子"，不改变任何 allow / block 结论。
- 没有该工具的记录时**不拿别人的条子顶替**：调用方据此得到 `approval_required`
  （"这个工具没有条子"），而不是把人引向"我的条子写错了"（`approval_invalid`）。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from pydantic import Field, field_validator, model_validator

from policy.models import StrictModel, canonical_identifier

from .models import (
    EnforcementError,
    to_timestamp,
    utc_now,
)

__all__ = [
    "APPROVAL_SCHEMA_VERSION",
    "APPROVAL_SET_SCHEMA_VERSIONS",
    "SUPPORTED_APPROVAL_SCHEMA_VERSIONS",
    "ApprovalBinding",
    "ApprovalError",
    "ApprovalRecord",
    "ApprovalSet",
    "approval_payload",
    "approval_store_payload",
    "available_tools",
    "load_approval",
    "load_approvals",
    "select_approval",
    "verify_approval",
]

# 审批记录有自己的协议轴（与受控执行协议各走各的）：载荷键集合或语义变化时，
# 只动这个常数——它不再是一个"定义了但没人用"的死常量。
#
# 1.1：binding=pattern 从"只校验声明过的参数"收紧为"必须覆盖本次请求的全部参数"
#（语义变更，AGENTS 第 55 条）。1.0 的审批文件没有声明这层意思——谁也不知道签的人
# 是不是这个意思，所以 1.0 一律拒收，必须显式重签。
#
# 1.2：审批**文档**从"一条记录"扩展为"一条记录，**或**一组记录"（新增键 records，
# 加载期按 tool_id 选择）。加键就是改协议（AGENTS 第 55 条），因此显式升版。
# 写的那一侧只在**两条起**才用记录集：一条记录仍然是老形状（见 approval_store_payload），
# 这样按"一个文件一条记录"解析的既有消费者不会因为这次升版而坏掉。
# **1.1 的单记录文档继续接受**：它的键集合与每个字段的含义一字未变，没有任何歧义可
# 制造误读——这与 1.0→1.1 那次不同（那次 pattern"到底覆盖了什么"本身就是歧义的，
# 只能拒收重签）。1.1 里**唯一**新增的约束是：那种文档里出现 records 就是自相矛盾
#（那个版本不认识这个键），加载期拒绝。
APPROVAL_SCHEMA_VERSION = "1.2"
SUPPORTED_APPROVAL_SCHEMA_VERSIONS = frozenset({"1.1", APPROVAL_SCHEMA_VERSION})
# 记录集（records 键）从 1.2 起才有：1.1 是唯一一个"记录只能单独放"的版本，把它排除
# 在这里，于是"1.1 的文档里出现 records"在加载期就是一句能被读出来的自相矛盾。
# 以后再升版时**不需要**改这一行——它按定义就是"支持的版本里、认识 records 的那些"。
APPROVAL_SET_SCHEMA_VERSIONS = frozenset(SUPPORTED_APPROVAL_SCHEMA_VERSIONS - {"1.1"})
# 记录集的标记键：文档里有它就按"一组记录"解释，没有就按"一条记录"解释。
APPROVAL_SET_KEY = "records"

# 参数模式名与参数名同口径（稳定标识符）：允许点号，便于将来扩展到嵌套结构。
_PATTERN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class ApprovalError(EnforcementError):
    """审批缺失、不合法、过期、跨主体、次数用尽或已被使用。一律按失败关闭处理。"""


class ApprovalBinding(str, Enum):
    """审批绑定档位。默认 action（单次绑定）；pattern 是可选档，不是替代品。"""

    ACTION = "action"
    PATTERN = "pattern"


class ApprovalRecord(StrictModel):
    """一条结构化人工审批。

    binding=action 时必须有 action_hash 与 action_id 且 max_uses=1、param_patterns 为空；
    binding=pattern 时二者必须缺省（模式化审批应当对未来那次调用有效），
    且必须声明至少一条 param_patterns 与次数上限——否则"模式"就成了无边界的通行证。
    """

    schema_version: str = APPROVAL_SCHEMA_VERSION
    approval_id: str = Field(min_length=1)
    binding: ApprovalBinding = ApprovalBinding.ACTION
    action_hash: Optional[str] = Field(
        default=None, min_length=1, description="单次绑定：被授权动作的 action_hash（逐位一致）"
    )
    action_id: Optional[str] = Field(
        default=None, min_length=1, description="单次绑定：被授权动作的 action_id（逐位一致）"
    )
    tool_id: str = Field(min_length=1)
    subject: str = Field(min_length=1, description="被授权的主体：审批不跨主体")
    granted_by: str = Field(min_length=1, description="审批人标识")
    granted_by_roles: Sequence[str] = Field(
        default_factory=tuple, description="审批人当时持有的角色；必须包含审批角色"
    )
    granted_at: datetime
    expires_at: datetime
    max_uses: int = Field(
        default=1, ge=1, description="这条审批最多允许几次调用；单次绑定只能是 1"
    )
    param_patterns: Mapping[str, str] = Field(
        default_factory=dict,
        description="模式化绑定：参数名 -> 整串匹配正则（对规范化后的取值做 re.fullmatch）",
    )
    note: str = ""

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        """未知审批协议版本一律拒绝：看不懂的条子不得按 1.0 的字段语义解释。"""

        if value not in SUPPORTED_APPROVAL_SCHEMA_VERSIONS:
            raise ApprovalError(
                f"未知审批协议版本 {value!r}；只接受 "
                f"{sorted(SUPPORTED_APPROVAL_SCHEMA_VERSIONS)}，拒绝按旧口径解释审批"
            )
        return value

    @field_validator("param_patterns")
    @classmethod
    def _check_patterns(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        if not isinstance(value, Mapping):
            raise ApprovalError("param_patterns 必须是 参数名 -> 正则 的映射")
        normalized: dict[str, str] = {}
        for raw_name, raw_pattern in value.items():
            name = str(raw_name).strip()
            if not name or _PATTERN_NAME_RE.fullmatch(name) is None:
                raise ApprovalError(f"审批模式里的参数名必须是稳定标识符，得到 {raw_name!r}")
            if not isinstance(raw_pattern, str) or not raw_pattern.strip():
                raise ApprovalError(f"审批模式 {name!r} 的正则不能为空")
            pattern = raw_pattern.strip()
            try:
                re.compile(pattern)
            except re.error as error:
                raise ApprovalError(f"审批模式 {name!r} 的正则不合法: {error}") from error
            if name in normalized:
                # 两个原始键 strip 之后是同一个参数名（"cmd" 与 " cmd "）：后一条会静默
                # 盖掉前一条，而"互相矛盾 / 重复的声明在加载期拒绝"正是本模块的口径。
                raise ApprovalError(
                    f"审批模式出现重复参数名 {raw_name!r}：strip 之后与已有的 {name!r} 相同，"
                    "同一参数不得声明两次"
                )
            normalized[name] = pattern
        return normalized

    @field_validator("granted_at", "expires_at")
    @classmethod
    def _check_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ApprovalError(
                "审批时间必须带时区：无时区的时间会让时效判断随机器漂移，"
                "而且与 utc_now() 比较时抛的是未处理的 TypeError，不是这条审批错误"
            )
        return value

    @model_validator(mode="after")
    def _check_shape(self) -> "ApprovalRecord":
        if self.expires_at <= self.granted_at:
            raise ApprovalError("审批有效期必须为正：过期时间不得早于签发时间")
        if self.binding is ApprovalBinding.ACTION:
            if not self.action_hash or not self.action_id:
                raise ApprovalError(
                    "单次绑定（binding=action）必须声明 action_hash 与 action_id："
                    "不知道绑哪一次调用就不是单次绑定"
                )
            if self.max_uses != 1:
                raise ApprovalError(
                    "单次绑定（binding=action）的 max_uses 只能是 1；"
                    "要多次使用请显式改成 binding=pattern 并写清参数模式与上限"
                )
            if self.param_patterns:
                raise ApprovalError(
                    "单次绑定（binding=action）不得声明 param_patterns："
                    "两种档位的字段混写会让'到底绑了什么'无法解释"
                )
        else:
            if self.action_hash or self.action_id:
                raise ApprovalError(
                    "模式化审批（binding=pattern）不得声明 action_hash / action_id："
                    "调用编号是运行期现生成的，绑它等于把条子签死；要绑单次请写 binding=action"
                )
            if not self.param_patterns:
                raise ApprovalError(
                    "模式化审批必须声明至少一条 param_patterns："
                    "没有参数模式的'一类调用'等于一张无边界通行证"
                )
        return self


class ApprovalSet(StrictModel):
    """审批**记录集**：一个文件里放多条记录，加载期按 `tool_id` 选择（1.2 引入的形状）。

    它存在的理由是实测出来的：桌面端 GUI 的每个动作都包在 `run_code`（PTC 传输）里，
    而"一个审批文件只能放一条记录"意味着名额只能给一个工具——给了传输工具，跑命令的工具
    就永远拿不到审批（`approval_invalid`）；反过来则整个会话冻结。每个工具各持一份放行，
    才算把审批从"唯一名额"变回"按工具授权"。

    加载期的三条硬规则：

    - `schema_version` **必填**：新形状没有历史包袱，缺版本 = 不知道按哪一版解释，拒绝；
      而且它必须落在 `APPROVAL_SET_SCHEMA_VERSIONS` 里（1.1 不认识 records）。
    - 至少一条记录：空集不是"没有限制"，是一个读不出意图的文件。
    - `approval_id` 不得重复：台账按 `approval_id` 记"用了几次 / 是否用过"，
      同一个 id 落到两条不同的条子上就是同名两义（第二次占用的额度会记到另一条上）。

    同一个 `tool_id` 可以有**多条**记录（人手写的存储里可能出现）：加载不拒绝，
    选择规则是确定的（见 `select_approval` 的偏好表），每一次拒绝都说得出是哪一张条子；
    `python -m enforcement.cli approve` 签发的存储里则总是每个工具至多一条。
    """

    # 必填，不给默认值：记录集是新形状，没有"没写就是当前版本"这回事。
    schema_version: str
    records: Tuple[ApprovalRecord, ...] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _check_set_version(cls, value: str) -> str:
        if value not in SUPPORTED_APPROVAL_SCHEMA_VERSIONS:
            raise ApprovalError(
                f"未知审批协议版本 {value!r}；只接受 "
                f"{sorted(SUPPORTED_APPROVAL_SCHEMA_VERSIONS)}，拒绝按旧口径解释审批"
            )
        if value not in APPROVAL_SET_SCHEMA_VERSIONS:
            raise ApprovalError(
                f"审批协议版本 {value!r} 不认识 {APPROVAL_SET_KEY!r} 这个键："
                "记录集是 1.2 起才有的形状，声明成旧版本就是自相矛盾。"
                f"要放多条记录请把 schema_version 写成 "
                f"{sorted(APPROVAL_SET_SCHEMA_VERSIONS)} 之一"
            )
        return value

    @model_validator(mode="after")
    def _check_unique_ids(self) -> "ApprovalSet":
        seen: set[str] = set()
        for record in self.records:
            if record.approval_id in seen:
                raise ApprovalError(
                    f"审批记录集里 approval_id {record.approval_id!r} 出现了不止一次："
                    "台账按这个 id 记'用了几次 / 是否用过'，同一个 id 落到两条条子上就是同名两义"
                )
            seen.add(record.approval_id)
        return self


def _read_approval_document(approval_path: Path) -> Mapping[str, Any]:
    """读审批 JSON 的**外层**：必须是一个对象；读不到 / 解析不了即失败关闭。"""

    if not approval_path.is_file():
        raise ApprovalError(f"审批文件不存在: {approval_path.name}")
    try:
        document = json.loads(approval_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApprovalError(f"审批文件不可解析: {approval_path.name}（{error}）") from error
    if not isinstance(document, Mapping):
        raise ApprovalError(f"审批文件必须是 JSON 对象: {approval_path.name}")
    return document


def _parse_record(document: Mapping[str, Any], *, where: str) -> ApprovalRecord:
    try:
        return ApprovalRecord.model_validate(dict(document))
    except ApprovalError:
        raise
    except Exception as error:  # pydantic ValidationError
        raise ApprovalError(f"审批记录不合法（{where}）：{error}") from error


def load_approvals(path: Path | str) -> Tuple[ApprovalRecord, ...]:
    """读取一个审批文档里的**全部**记录（单记录文档，或 1.2 的记录集）。

    两种形状由 `records` 键区分，且**没有第三种解释**：

    - 没有 `records`：按"一条记录"读。1.1 与 1.2 都接受（键集合与字段语义一字未变）。
    - 有 `records`：按"记录集"读，`schema_version` 必须是认识这个键的版本（≥1.2），
      否则拒绝——绝不把旧版本的文件静默按新语义读。
    """

    approval_path = Path(path)
    document = _read_approval_document(approval_path)
    if APPROVAL_SET_KEY not in document:
        return (_parse_record(document, where=approval_path.name),)
    try:
        bundle = ApprovalSet.model_validate(dict(document))
    except ApprovalError:
        raise
    except Exception as error:  # pydantic ValidationError
        raise ApprovalError(f"审批记录集不合法（{approval_path.name}）：{error}") from error
    return tuple(bundle.records)


def load_approval(path: Path | str) -> ApprovalRecord:
    """读取**恰好一条**记录的审批文档；未知字段、缺字段、时间格式错误一律拒绝。

    这是给"一个文件一条记录"的老调用方（CLI 的单次执行、编排层的收件箱）用的窄口子：
    记录集里有多条时**不猜**——报错并要求按工具选择（`select_approval`），
    因为猜一条等于把"该出示哪张条子"变成一个不透明的决定。
    """

    records = load_approvals(path)
    if len(records) != 1:
        raise ApprovalError(
            f"审批文件 {Path(path).name} 里有 {len(records)} 条记录（审批集）："
            "这个口子只接受一条记录，请按工具选择（select_approval(..., tool_id=...)），"
            "不要猜一条出来"
        )
    return records[0]


def available_tools(records: Sequence[ApprovalRecord]) -> Tuple[str, ...]:
    """这批记录覆盖的工具（升序、去重）：回答"这个文件里现在有谁的放行"。

    它是给人看的一行汇总（CLI 的 `approve` 写完之后打印它），不参与任何判定。
    """

    return tuple(sorted({record.tool_id for record in records if record.tool_id}))


def select_approval(
    records: Sequence[ApprovalRecord],
    *,
    tool_id: str,
    action_id: Optional[str] = None,
    subject: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[ApprovalRecord]:
    """按当前动作**选出该出示哪一张条子**；没有这个工具的记录就返回 None。

    **这不是判定**：选中的记录随后仍由 `verify_approval` 完整校验（工具 / 主体 / 时效 /
    角色 / 参数模式 / 次数）。选择不改变任何 allow / block 结论——**一张条子也不会因为
    "被选中"而变得可用**。它只回答两件事：出示哪张条子、以及拒绝理由说的是哪件事。

    规则一（不串味）：只考虑 `tool_id` 相等的记录。别的工具的条子既不选中、也不作为
    拒绝理由——"给 run_code 签的条子"和"pwsh 没有条子"是两件不同的事，前者会把人引向
    "我的条子写错了"，后者才是事实。

    规则二（确定地选一张）：候选按下面的偏好升序排列，取第一条。四档都是"哪个理由更贴切"，
    没有任何一档让判定更容易通过。

    | 序 | 偏好 | 为什么 |
    | --- | --- | --- |
    | 1 | 未过期 | 过期的条子必然被拒；让它排在后面只为了理由说的是"参数不匹配"而不是"过期" |
    | 2 | 主体相等 | 同上：跨主体的条子必然被拒，但"主体不符"比"参数不符"更接近真相 |
    | 3 | 绑定档：本次 action_id 的单次绑定 > 模式化 > 其它单次绑定 | 越具体越该被出示；陈旧的单次绑定只会得到"绑的是另一次调用" |
    | 4 | `approval_id` 升序 | 确定性：同样的输入必须选出同一张条子（AGENTS 第 5 条的口径） |

    主体未知（请求没有主体）时第 2 档对所有候选同值，不影响排序。
    """

    moment = now or utc_now()
    candidates = [record for record in records if record.tool_id == tool_id]
    if not candidates:
        return None

    def rank(record: ApprovalRecord) -> Tuple[int, int, int, str]:
        if record.binding is ApprovalBinding.ACTION:
            binding_rank = 0 if (action_id is not None and record.action_id == action_id) else 2
        else:
            binding_rank = 1
        return (
            0 if record.expires_at > moment else 1,
            0 if (subject is not None and record.subject == subject) else 1,
            binding_rank,
            record.approval_id,
        )

    return min(candidates, key=rank)


def approval_store_payload(records: Sequence[ApprovalRecord]) -> dict[str, Any]:
    """把一组记录渲染成要写盘的审批文档（1.2）。**形状随记录条数**：

    - **一条记录** → 历史上那种**单记录文档**（顶层就是记录的字段）。
      这不是遗留包袱，是兼容性：仓库内外都有一批消费者按 `record["action_hash"]` 这样读
      "一个只有一条记录的文件"（`tools/orchestration_loop.py` 就是其中之一），而"文件里
      只有一条记录"这件事本身没有歧义——把它写成记录集只会平白弄坏那些消费者。
    - **两条及以上** → **记录集**（`records`），加载期按 `tool_id` 选择。

    读的那一侧（`load_approvals`）两种都认，形状由 `records` 键唯一确定，没有第三种解释。
    空集直接拒绝：它不是"没有限制"，是一个读不出意图的文件。
    """

    items = list(records)
    if not items:
        raise ApprovalError(
            "审批文档至少要有一条记录：空集不是'没有限制'，是一个读不出意图的文件"
        )
    if len(items) == 1:
        return approval_payload(items[0])
    return {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        APPROVAL_SET_KEY: [approval_payload(record) for record in items],
    }


def pattern_text(value: Any, *, name: str) -> str:
    """把规范化后的参数取值渲染成可做整串匹配的文本；不支持的形状直接拒绝。"""

    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    raise ApprovalError(
        f"参数 {name!r} 的取值类型是 {type(value).__name__}，不支持模式匹配："
        "模式只支持字符串 / 整数 / 布尔参数，列表类参数请改用 binding=action 的单次绑定"
    )


def verify_approval(
    record: Optional[ApprovalRecord],
    *,
    action_hash: str,
    action_id: str,
    tool_id: str,
    subject: Optional[str],
    approval_roles: Sequence[str],
    used: bool,
    now: Optional[datetime] = None,
    params: Optional[Mapping[str, Any]] = None,
    uses: Optional[int] = None,
) -> None:
    """校验审批与当前动作一致；任何不符都抛 ApprovalError。

    公共性质（两种档位都查）：工具、主体、签发时间不在未来、未过期、授予者持有审批角色。
    binding=action 追加：action_hash 与 action_id 逐位一致，且未被消费过（used=False）。
    binding=pattern 追加：次数未用尽，且每个声明的参数模式都整串匹配当前规范化取值。
    """

    if record is None:
        raise ApprovalError("该动作需要人工审批，但没有提供与当前 action_hash 绑定的审批记录")
    moment = now or utc_now()
    if record.tool_id != tool_id:
        raise ApprovalError("审批绑定的工具与当前动作不一致")
    if subject is None or record.subject != subject:
        raise ApprovalError("审批主体与当前请求主体不一致：审批不得跨主体复用")
    if moment < record.granted_at:
        raise ApprovalError("审批签发时间在未来：凭据不可信，拒绝执行")
    if moment >= record.expires_at:
        raise ApprovalError(f"审批已过期（{to_timestamp(record.expires_at)}）")
    granted_roles = {canonical_identifier(role) for role in record.granted_by_roles}
    allowed_roles = {canonical_identifier(role) for role in approval_roles}
    if not granted_roles & allowed_roles:
        raise ApprovalError(
            "审批人没有审批权：授予者角色 "
            f"{sorted(granted_roles) or ['<none>']} 与具备审批权的角色 "
            f"{sorted(allowed_roles)} 无交集"
        )

    if record.binding is ApprovalBinding.ACTION:
        if record.action_hash != action_hash:
            raise ApprovalError(
                "审批绑定的 action_hash 与当前动作不一致：参数、主体或 schema 已经变化，旧审批作废"
            )
        if record.action_id != action_id:
            raise ApprovalError("审批绑定的 action_id 与当前动作不一致")
        if used:
            raise ApprovalError("审批已被使用：单次审批不得重复提交同一个动作")
        return

    # binding=pattern
    if uses is None:
        # uses 是"台账里已经消费了几次"：缺省 0 会让"忘了传"静默等价于"一次都没用过"，
        # 一张有次数上限的模式条子于是退化成到期前的无限次通行证。拿不到次数就拒绝。
        raise ApprovalError(
            "模式化审批必须给出台账里的已用次数（uses）：拿不到就证明不了额度没用完"
        )
    if uses >= record.max_uses:
        raise ApprovalError(
            f"审批的次数上限已用尽（已用 {uses}/{record.max_uses} 次）：必须重新签发"
        )
    if params is None:
        raise ApprovalError(
            "模式化审批需要本次请求的规范化参数才能校验模式：拿不到参数就拒绝（证明不了即失败关闭）"
        )
    for name in sorted(record.param_patterns):
        pattern = record.param_patterns[name]
        if name not in params:
            raise ApprovalError(
                f"审批模式声明的参数 {name!r} 不在本次请求里：模式匹配不上，拒绝执行"
            )
        text = pattern_text(params[name], name=name)
        if re.fullmatch(pattern, text) is None:
            raise ApprovalError(
                f"参数 {name!r} 的取值不匹配审批模式 {pattern!r}（整串匹配）："
                "参数一变旧授权自动失效"
            )
    # 声明的模式全部对上了还不够：**没声明的参数同样是一次调用的组成部分**。
    # 只校验声明过的那些，等于给未声明的参数（exec.pwsh 的 workdir / sandbox_permissions、
    # exec.shell 的 description …）留一张"跟着条子一起放行"的后门——而 binding=pattern
    # 不校验 action_hash，没有任何第二道闸能发现这种放大。
    undeclared = sorted(set(params) - set(record.param_patterns))
    if undeclared:
        hints = "、".join(f"{name}=.*" for name in undeclared)
        raise ApprovalError(
            f"本次请求的参数 {undeclared} 没有在审批模式里声明：模式化授权必须覆盖全部参数。"
            f"有意放行的参数请显式写成通配模式（例如 --param-pattern {hints}）；"
            "取值类型不支持模式匹配（例如列表）时请改用 binding=action 的单次绑定"
        )


def approval_payload(record: ApprovalRecord) -> dict[str, Any]:
    return json.loads(record.model_dump_json())

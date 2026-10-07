"""执行台账：幂等、授权单次使用、限流与熔断的持久状态。

每个 Hook 调用都是一个新进程，所以"同一 action 不能执行两次""授权只能用一次""窗口内调用次数"
这些状态必须落在文件上。台账是追加写的 JSONL，读取时按类型归类：

    {"kind": "claim",        "action_key": ..., "claim_id": ...}
    {"kind": "pre_decision", "action_id": ..., "action_hash": ..., "decision": ...,
     "risk": ..., "subject": ..., "tool_id": ...}
    {"kind": "grant_used",   "grant_id": ...}
    {"kind": "execution",    "action_id": ..., "status": ..., "ok": true/false}
    {"kind": "approval_used","approval_id": ...}

**台账存什么**（逐项写下，读的人不用再猜）：`kind`（claim / grant / pre_decision / pre_state /
execution / approval_used）、各条记录自己的标识（`action_id` / `claim_id` / `grant_id` …）、
`action_hash`、结论字段（`decision` / `status` / `reason_code`），以及 `pre_state` 里的
**请求视图** `request`。

**请求视图里扣什么、不扣什么**：注册表声明 `secret: true` 的参数、以及取值里出现确定形态凭据
（令牌前缀 / Bearer / 私钥块）的参数，只留类型、长度与摘要（此时 `values_withheld: true`）；
**其余参数按原文落盘**（`params[].value` 就是规范化后的取值，例如整份 `content`），
`request.workspace` 落的是**绝对路径**，并且它参与 `action_hash`。

这不是"漏脱敏"，而是事后核对的前提：`adapters/dsh/enforcement.py::_restore_request` 要用台账里的
`request` 载荷**重建 `ActionRequest`**（PostToolUse），而 `action_hash` 的参与字段里包含
`workspace` 与规范化参数（`models.py::_ACTION_HASH_FIELDS`）。扣掉取值、或把 `workspace`
换成占位，重建必然对不上哈希 —— 事后核对就只剩"证据不足"一个结论，
等于把 G2（事前事后成对 + post_validated）打掉。

**边界**：这不是 AGENTS 第 16 条的违反——第 16 条管的是 `audit.jsonl` 摘要链的脱敏
（那里密钥、绝对路径、控制字符一律脱敏或转义）；台账是**另一份产物**，它的存留口径由本节写死。
把台账当成"只存哈希"的东西读，会让安全评审得出错误结论；反过来，要改这条口径就得先解决
"事后核对靠什么重建请求"。

并发说明：跨进程的原子性由"先追加再复核"实现——两个进程同时认领同一 action 时，
只有序号更小的那条算数，另一个按重复处理（失败关闭）。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Sequence

from .locking import DEFAULT_LOCK_TIMEOUT_SECONDS, LockError, file_lock
from .models import (
    AuthorizationGrant,
    GrantError,
    LedgerError,
    ReasonCode,
    to_timestamp,
    utc_now,
)

__all__ = [
    "LEDGER_SCHEMA_VERSION",
    "ApprovalUseClaim",
    "EnforcementLedger",
    "LedgerClaim",
]


def _recorded_at(value: Any) -> Optional[datetime]:
    """台账行的 recorded_at → 带时区的 datetime；读不出来返回 None。

    调用方对 None 必须按**失败关闭**处理（计入窗口），不能跳过：跳过等于把"证明不了"
    当成"没发生"，限流与熔断都会少算。
    """

    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None

LEDGER_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class LedgerClaim:
    """一次 action 认领的结果。"""

    claimed: bool
    claim_id: str
    reason: str = ""


@dataclass(frozen=True)
class ApprovalUseClaim:
    """一次审批额度的原子占用结果。

    claimed=False 时 reason 说明为什么没占到（例如 approval_quota_exhausted）；
    uses 是占用后该审批生效的消费次数（含自己），用于审计与拒绝原因。
    """

    claimed: bool
    uses: int
    use_id: str
    reason: str = ""


class EnforcementLedger:
    """文件台账。任何读写失败都抛 LedgerError —— 受治理动作默认失败关闭。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # ------------------------------------------------------------------ 读
    def records(self) -> tuple[Mapping[str, Any], ...]:
        return self._read()[0]

    def torn_tail(self) -> tuple[int, ...]:
        """被跳过的**尾部残行**行号（1-based）。

        一行写不完整只可能是"进程在 append 途中被杀"（append 只 flush，不做原子替换）：
        它对应的那条记录没有落盘成功，跳过它等于回到那次写入之前——这是唯一可修复且
        不放松语义的读法。调用方据此把"台账被撕开过"记成异常，而不是当成"没有这条记录"。
        """

        return self._read()[1]

    def _read(self) -> tuple[tuple[Mapping[str, Any], ...], tuple[int, ...]]:
        """读台账，返回（记录, 尾部残行行号）。

        只有**最后一条非空行**可以被容忍（写一半被杀）；中间行损坏仍然抛 LedgerError——
        那证明不了幂等状态，而"一条坏行让所有受治理动作永久锁死且没有修复路径"同样是
        失败关闭的反面：它把可修复的产物损坏变成了不可恢复的死锁。
        """

        if not self.path.is_file():
            return (), ()
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise LedgerError(f"台账不可读: {self.path.name}（{error}）") from error
        lines = [
            (number, line.strip())
            for number, line in enumerate(text.splitlines(), start=1)
            if line.strip()
        ]
        tail_number = lines[-1][0] if lines else None
        rows: list[Mapping[str, Any]] = []
        torn: list[int] = []
        for number, line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                if number == tail_number:
                    torn.append(number)
                    continue
                raise LedgerError("台账包含损坏的 JSON 记录，无法证明幂等状态") from error
            if not isinstance(item, Mapping):
                raise LedgerError("台账记录必须是 JSON 对象")
            version = item.get("ledger_schema_version")
            if version != LEDGER_SCHEMA_VERSION:
                raise LedgerError(
                    f"台账协议版本 {version!r} 不受支持；不能忽略未知记录继续执行"
                )
            rows.append(item)
        return tuple(rows), tuple(torn)

    def of_kind(
        self, kind: str, *, records: Optional[Sequence[Mapping[str, Any]]] = None
    ) -> tuple[Mapping[str, Any], ...]:
        """某个 kind 的记录；`records` 给定时不再重读文件（调用方已经读过一次）。"""

        source = self.records() if records is None else records
        return tuple(item for item in source if item.get("kind") == kind)

    @contextmanager
    def limit_lock(
        self, limit_key: str, *, timeout_seconds: Optional[float] = None
    ) -> Iterator[None]:
        """同一个限流键上的跨进程互斥（锁文件与台账同目录，按 limit_key 哈希分片）。

        限流的 +1 是"判定末尾写一条 pre_decision"，而计数在判定开头读；两步之间夹着认领、
        审批占用、授权签发与审计写入。把这两步圈进同一把锁，注册表配置的窗口上限才真的
        成立。**粒度按限流键**：不同 (subject|tool) 的锁文件不同，互不阻塞。
        拿不到锁抛 LedgerError——调用方必须按失败关闭拒绝，不许"读旧计数照样判"。

        **锁序**：调用方（precheck.pre_execute）按 rate-lock → audit-lock 的固定顺序取锁；
        本方法只取前者，台账文件自身不加字节锁（Windows 上那样会让同进程的 read_text()
        直接吃 PermissionError）。任何新增的取锁点都必须遵守同一条顺序，否则两个相反的
        顺序就是死锁配方。
        """

        timeout = DEFAULT_LOCK_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        token = hashlib.sha256(limit_key.encode("utf-8")).hexdigest()[:16]
        lock_path = self.path.with_name(self.path.name + f".limit-{token}.lock")
        try:
            with file_lock(lock_path, timeout_seconds=timeout):
                yield
        except LockError as error:
            raise LedgerError(
                f"限流键 {limit_key!r} 的互斥锁不可用（{error}）："
                "拿不到锁就不判定，宁可失败关闭"
            ) from error

    # ------------------------------------------------------------------ 写
    def append(self, record: Mapping[str, Any]) -> None:
        payload = {
            "ledger_schema_version": LEDGER_SCHEMA_VERSION,
            "recorded_at": to_timestamp(utc_now()),
        }
        payload.update({key: value for key, value in record.items() if value is not None})
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
                handle.flush()
        except OSError as error:
            raise LedgerError(f"台账不可写: {self.path.name}（{error}）") from error

    # ------------------------------------------------------------------ 幂等
    def active_claims(
        self,
        *,
        action_id: str,
        tool_id: str,
        records: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> tuple[Mapping[str, Any], ...]:
        """仍然生效的认领（被 release_claim 释放过的不算）。

        `records` 给定时用它当快照：一次操作里连着问几个问题只读一遍文件即可。
        """

        key = f"{tool_id}:{action_id}"
        source = self.records() if records is None else records
        released = {
            item.get("claim_id") for item in self.of_kind("claim_released", records=source)
        }
        return tuple(
            item
            for item in self.of_kind("claim", records=source)
            if item.get("action_key") == key and item.get("claim_id") not in released
        )

    def claim(
        self, *, action_id: str, tool_id: str, action_hash: str, claim_id: str
    ) -> LedgerClaim:
        """认领一次 action。已经认领过的 action 不再认领（调用方据此拒绝重复执行）。"""

        key = f"{tool_id}:{action_id}"
        # 认领前的读取只做一次：active_claims 内部要问 claim 与 claim_released 两件事，
        # 各自重读一遍文件是纯粹的重复 IO（台账是追加写、只会变长的文件）。
        snapshot = self.records()
        claims = list(
            self.active_claims(action_id=action_id, tool_id=tool_id, records=snapshot)
        )
        if claims:
            existing = claims[0]
            if existing.get("action_hash") == action_hash:
                return LedgerClaim(
                    claimed=False,
                    claim_id=str(existing.get("claim_id", "")),
                    reason="action_replay",
                )
            return LedgerClaim(
                claimed=False,
                claim_id=str(existing.get("claim_id", "")),
                reason="action_id_reuse",
            )
        self.append(
            {
                "kind": "claim",
                "action_key": key,
                "action_id": action_id,
                "tool_id": tool_id,
                "action_hash": action_hash,
                "claim_id": claim_id,
            }
        )
        # 追加之后的复核必须**重新读**（并发方的行也要看见），但同样只读一次。
        winner = self.active_claims(
            action_id=action_id, tool_id=tool_id, records=self.records()
        )[0]
        if winner.get("claim_id") != claim_id:
            return LedgerClaim(
                claimed=False, claim_id=str(winner.get("claim_id", "")), reason="action_replay"
            )
        return LedgerClaim(claimed=True, claim_id=claim_id)

    def release_claim(self, *, action_id: str, tool_id: str, claim_id: str, reason: str) -> None:
        """释放一次认领（只用于"还没执行就失败"的路径，例如审计不可写导致阻断）。

        **先证明这条认领真的存在、仍然生效、而且属于同一个动作**：幂等保证不能被一个
        字符串解除——写错 id、拿别处的 id 来释放、或重复释放，都会静默放开另一条认领的
        保护（active_claims 只按 id 比对，released 是全局 id 集合）。证明不了就
        LedgerError（失败关闭），不写释放行。
        """

        key = f"{tool_id}:{action_id}"
        live = [
            item
            for item in self.active_claims(action_id=action_id, tool_id=tool_id)
            if item.get("claim_id") == claim_id
        ]
        if not live:
            raise LedgerError(
                f"释放认领被拒绝：{key} 下没有仍然生效的认领 {claim_id!r}"
                "（写错 id / 已经释放过 / 不属于这个动作，都不许静默解除幂等保护）"
            )
        self.append(
            {
                "kind": "claim_released",
                "action_key": key,
                "claim_id": claim_id,
                "reason": reason,
            }
        )

    # ------------------------------------------------------------------ 授权
    def record_grant(self, grant: AuthorizationGrant) -> None:
        self.append(
            {
                "kind": "grant",
                "grant_id": grant.grant_id,
                "action_id": grant.action_id,
                "action_hash": grant.action_hash,
                "tool_id": grant.tool_id,
                "subject": grant.subject,
                "expires_at": to_timestamp(grant.expires_at),
            }
        )

    def grant_recorded(self, grant_id: str, action_hash: str) -> bool:
        """授权是否由本平台签发（pre-check 时登记过）。手搓的凭据一律不认。"""

        for item in self.of_kind("grant"):
            if item.get("grant_id") == grant_id and item.get("action_hash") == action_hash:
                return True
        return False

    def grant_used(self, grant_id: str) -> bool:
        return any(item.get("grant_id") == grant_id for item in self.of_kind("grant_used"))

    def consume_grant(self, grant: AuthorizationGrant, *, now: Optional[datetime] = None) -> None:
        """消费单次授权。已被消费、或已被其他进程抢走时抛 GrantError（失败关闭）。"""

        if self.grant_used(grant.grant_id):
            raise GrantError(
                "授权已被使用：单次授权不得重复消费",
                reason_code=ReasonCode.GRANT_REUSED.value,
            )
        # 认领身份必须**每次尝试唯一**：两个并发方可能拿到同一个 now（确定性时钟、
        # 同一毫秒、测试注入），用时间戳推导会让双方写出逐字节相同的 claim_id，
        # 于是下面"写入后复核"在两边都判自己赢，单次授权被消费两次。
        claim_id = f"{grant.grant_id}:{uuid.uuid4().hex}"
        self.append({"kind": "grant_used", "grant_id": grant.grant_id, "claim_id": claim_id})
        winner = [
            item for item in self.of_kind("grant_used") if item.get("grant_id") == grant.grant_id
        ][0]
        if winner.get("claim_id") != claim_id:
            raise GrantError(
                "授权已被其他执行抢占：拒绝并发重复执行同一个动作",
                reason_code=ReasonCode.GRANT_REUSED.value,
            )

    def record_approval_use(
        self,
        approval_id: str,
        *,
        action_hash: str,
        use_id: Optional[str] = None,
        action_id: Optional[str] = None,
        tool_id: Optional[str] = None,
        max_uses: Optional[int] = None,
    ) -> str:
        """登记一次审批消费并返回 use_id。

        生产路径走 claim_approval_use（先占用后执行 + 并发复核）；本方法是它的
        最小构件，测试与工具直接用它来构造"这条审批已经被用过"的台账状态。
        """

        token = use_id or "approval-use-" + uuid.uuid4().hex[:16]
        self.append(
            {
                "kind": "approval_used",
                "approval_id": approval_id,
                "use_id": token,
                "action_hash": action_hash,
                "action_id": action_id,
                "tool_id": tool_id,
                "max_uses": max_uses,
            }
        )
        return token

    def approval_uses(
        self, approval_id: str, *, records: Optional[Sequence[Mapping[str, Any]]] = None
    ) -> tuple[Mapping[str, Any], ...]:
        """仍然生效的审批消费记录：被 release_approval_use 归还过的不算。

        "归还"存在的理由与 claim_released 相同：失败关闭不能变成死锁。审计不可写导致
        动作没有执行时，额度必须还回去，否则修好审计之后重试会被误判成"次数用尽"。
        `records` 给定时用它当快照，不再重读文件。
        """

        source = self.records() if records is None else records
        released = {
            item.get("use_id") for item in self.of_kind("approval_use_released", records=source)
        }
        return tuple(
            item
            for item in self.of_kind("approval_used", records=source)
            if item.get("approval_id") == approval_id and item.get("use_id") not in released
        )

    def approval_use_count(
        self, approval_id: str, *, records: Optional[Sequence[Mapping[str, Any]]] = None
    ) -> int:
        return len(self.approval_uses(approval_id, records=records))

    def approval_used(
        self, approval_id: str, *, records: Optional[Sequence[Mapping[str, Any]]] = None
    ) -> bool:
        return bool(self.approval_uses(approval_id, records=records))

    def claim_approval_use(
        self,
        *,
        approval_id: str,
        action_id: str,
        tool_id: str,
        action_hash: str,
        max_uses: int,
    ) -> ApprovalUseClaim:
        """原子占用一次审批额度：先追加、再复核，抢输了或超限一律不认领。

        与 claim() 同一套并发口径（跨进程靠"先追加再复核"）：两个进程同时用第 N 次额度时，
        只有序号更小的那条算数，另一个按超限拒绝——失败关闭，绝不放行第二次。
        """

        if max_uses < 1:
            raise LedgerError(f"审批次数上限必须是正整数，得到 {max_uses}")
        existing = self.approval_uses(approval_id, records=self.records())
        if len(existing) >= max_uses:
            return ApprovalUseClaim(
                claimed=False,
                uses=len(existing),
                use_id="",
                reason="approval_quota_exhausted",
            )
        token = self.record_approval_use(
            approval_id,
            action_hash=action_hash,
            action_id=action_id,
            tool_id=tool_id,
            max_uses=max_uses,
        )
        rows = self.approval_uses(approval_id, records=self.records())
        index = next(
            (position for position, item in enumerate(rows) if item.get("use_id") == token), None
        )
        if index is None:
            raise LedgerError(
                "审批消费记录写入后读不回来：台账状态不可信，拒绝继续执行"
            )
        if index >= max_uses:
            # 抢输的一方必须把自己的那一行还回去：它没有执行任何动作，却已经追加了一条
            # approval_used。不释放的话这张审批的额度被永久烧掉一格（"已用 N/M" 的读数
            # 也与真实执行数不符），修好原因后的重试会被误判成 approval_quota_exhausted。
            # 归还失败会抛 LedgerError —— 那是失败关闭，调用方按台账不可用处理。
            self.release_approval_use(
                approval_id=approval_id, use_id=token, reason="approval_race_lost"
            )
            return ApprovalUseClaim(
                claimed=False, uses=index, use_id=token, reason="approval_quota_exhausted"
            )
        return ApprovalUseClaim(claimed=True, uses=index + 1, use_id=token)

    def release_approval_use(self, *, approval_id: str, use_id: str, reason: str) -> None:
        """归还一次审批额度（只用于"还没执行就失败"的路径，例如审计不可写导致阻断）。

        与 release_claim 同一口径：只归还**确实存在、仍然生效、且属于这张审批**的那次
        消费；否则写错 use_id 或重复归还会静默把额度还回去（等于凭空多出一次执行机会）。
        """

        live = [
            item for item in self.approval_uses(approval_id) if item.get("use_id") == use_id
        ]
        if not live:
            raise LedgerError(
                f"归还审批额度被拒绝：{approval_id!r} 下没有仍然生效的消费 {use_id!r}"
            )
        self.append(
            {
                "kind": "approval_use_released",
                "approval_id": approval_id,
                "use_id": use_id,
                "reason": reason,
            }
        )

    # ------------------------------------------------------------------ 限流 / 熔断
    def count_since(
        self,
        *,
        kind: str,
        key_field: str,
        key_value: str,
        window_seconds: int,
        now: Optional[datetime] = None,
        records: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> int:
        moment = now or utc_now()
        cutoff = moment - timedelta(seconds=window_seconds)
        total = 0
        for item in self.of_kind(kind, records=records):
            if str(item.get(key_field)) != key_value:
                continue
            when = _recorded_at(item.get("recorded_at"))
            # 时间戳读不出来（被改过 / 手写行）时计入窗口：少算等于放宽限流（fail-open）。
            if when is None or when >= cutoff:
                total += 1
        return total

    def record_execution(
        self,
        *,
        action_id: str,
        tool_id: str,
        subject: Optional[str],
        action_hash: str,
        status: str,
        ok: bool,
        risk: str,
    ) -> None:
        self.append(
            {
                "kind": "execution",
                "action_id": action_id,
                "tool_id": tool_id,
                "subject": subject,
                "limit_key": f"{subject}|{tool_id}",
                "action_hash": action_hash,
                "status": status,
                "ok": ok,
                "risk": risk,
            }
        )

    def failures_since(
        self,
        *,
        key_field: str,
        key_value: str,
        window_seconds: int,
        now: Optional[datetime] = None,
        records: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> int:
        """窗口内的失败次数（执行失败、验证要求修复、证据不一致）。"""

        moment = now or utc_now()
        cutoff = moment - timedelta(seconds=window_seconds)
        total = 0
        for item in self.of_kind("execution", records=records):
            if str(item.get(key_field)) != key_value:
                continue
            if item.get("ok") is not False:
                continue
            when = _recorded_at(item.get("recorded_at"))
            # 同上：ok=false 的行本来就是失败，时间戳读不出来时按"在窗口内"计（熔断宁可早开）。
            if when is None or when >= cutoff:
                total += 1
        return total

    def recent_records(
        self, *, kind: str, key_field: str, key_value: str, limit: int = 20
    ) -> Sequence[Mapping[str, Any]]:
        items = [item for item in self.of_kind(kind) if str(item.get(key_field)) == key_value]
        return tuple(items[-limit:])

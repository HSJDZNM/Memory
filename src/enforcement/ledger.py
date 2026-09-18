"""执行台账：幂等、授权单次使用、限流与熔断的持久状态。

每个 Hook 调用都是一个新进程，所以"同一 action 不能执行两次""授权只能用一次""窗口内调用次数"
这些状态必须落在文件上。台账是追加写的 JSONL，读取时按类型归类：

    {"kind": "claim",        "action_key": ..., "claim_id": ...}
    {"kind": "pre_decision", "action_id": ..., "action_hash": ..., "decision": ..., "risk": ..., "subject": ..., "tool_id": ...}
    {"kind": "grant_used",   "grant_id": ...}
    {"kind": "execution",    "action_id": ..., "status": ..., "ok": true/false}
    {"kind": "approval_used","approval_id": ...}

台账只存标识、哈希与结论，不存参数原文。并发说明：跨进程的原子性由"先追加再复核"实现——
两个进程同时认领同一 action 时，只有序号更小的那条算数，另一个按重复处理（失败关闭）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .models import (
    AuthorizationGrant,
    GrantError,
    LedgerError,
    to_timestamp,
    utc_now,
)

__all__ = [
    "LEDGER_SCHEMA_VERSION",
    "EnforcementLedger",
    "LedgerClaim",
]

LEDGER_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class LedgerClaim:
    """一次 action 认领的结果。"""

    claimed: bool
    claim_id: str
    reason: str = ""


class EnforcementLedger:
    """文件台账。任何读写失败都抛 LedgerError —— 受治理动作默认失败关闭。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # ------------------------------------------------------------------ 读
    def records(self) -> tuple[Mapping[str, Any], ...]:
        if not self.path.is_file():
            return ()
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise LedgerError(f"台账不可读: {self.path.name}（{error}）") from error
        rows: list[Mapping[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise LedgerError("台账包含损坏的 JSON 记录，无法证明幂等状态") from error
            if not isinstance(item, Mapping):
                raise LedgerError("台账记录必须是 JSON 对象")
            version = item.get("ledger_schema_version")
            if version != LEDGER_SCHEMA_VERSION:
                raise LedgerError(
                    f"台账协议版本 {version!r} 不受支持；不能忽略未知记录继续执行"
                )
            rows.append(item)
        return tuple(rows)

    def of_kind(self, kind: str) -> tuple[Mapping[str, Any], ...]:
        return tuple(item for item in self.records() if item.get("kind") == kind)

    # ------------------------------------------------------------------ 写
    def append(self, record: Mapping[str, Any]) -> None:
        payload = {"ledger_schema_version": LEDGER_SCHEMA_VERSION, "recorded_at": to_timestamp(utc_now())}
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
    def active_claims(self, *, action_id: str, tool_id: str) -> tuple[Mapping[str, Any], ...]:
        """仍然生效的认领（被 release_claim 释放过的不算）。"""

        key = f"{tool_id}:{action_id}"
        released = {item.get("claim_id") for item in self.of_kind("claim_released")}
        return tuple(
            item
            for item in self.of_kind("claim")
            if item.get("action_key") == key and item.get("claim_id") not in released
        )

    def claim(self, *, action_id: str, tool_id: str, action_hash: str, claim_id: str) -> LedgerClaim:
        """认领一次 action。已经认领过的 action 不再认领（调用方据此拒绝重复执行）。"""

        key = f"{tool_id}:{action_id}"
        claims = list(self.active_claims(action_id=action_id, tool_id=tool_id))
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
        winner = self.active_claims(action_id=action_id, tool_id=tool_id)[0]
        if winner.get("claim_id") != claim_id:
            return LedgerClaim(
                claimed=False, claim_id=str(winner.get("claim_id", "")), reason="action_replay"
            )
        return LedgerClaim(claimed=True, claim_id=claim_id)

    def release_claim(self, *, action_id: str, tool_id: str, claim_id: str, reason: str) -> None:
        """释放一次认领（只用于"还没执行就失败"的路径，例如审计不可写导致阻断）。"""

        self.append(
            {
                "kind": "claim_released",
                "action_key": f"{tool_id}:{action_id}",
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
            raise GrantError("授权已被使用：单次授权不得重复消费")
        claim_id = f"{grant.grant_id}:{to_timestamp(now or utc_now())}"
        self.append({"kind": "grant_used", "grant_id": grant.grant_id, "claim_id": claim_id})
        winner = [item for item in self.of_kind("grant_used") if item.get("grant_id") == grant.grant_id][0]
        if winner.get("claim_id") != claim_id:
            raise GrantError("授权已被其他执行抢占：拒绝并发重复执行同一个动作")

    def record_approval_use(self, approval_id: str, *, action_hash: str) -> None:
        self.append(
            {"kind": "approval_used", "approval_id": approval_id, "action_hash": action_hash}
        )

    def approval_used(self, approval_id: str) -> bool:
        return any(
            item.get("approval_id") == approval_id for item in self.of_kind("approval_used")
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
    ) -> int:
        moment = now or utc_now()
        cutoff = moment - timedelta(seconds=window_seconds)
        total = 0
        for item in self.of_kind(kind):
            if str(item.get(key_field)) != key_value:
                continue
            recorded = item.get("recorded_at")
            if not isinstance(recorded, str):
                continue
            try:
                when = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
            except ValueError:
                continue
            if when.tzinfo is None:
                continue
            if when >= cutoff:
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
    ) -> int:
        """窗口内的失败次数（执行失败、验证要求修复、证据不一致）。"""

        moment = now or utc_now()
        cutoff = moment - timedelta(seconds=window_seconds)
        total = 0
        for item in self.of_kind("execution"):
            if str(item.get(key_field)) != key_value:
                continue
            if item.get("ok") is not False:
                continue
            recorded = item.get("recorded_at")
            if not isinstance(recorded, str):
                continue
            try:
                when = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
            except ValueError:
                continue
            if when.tzinfo is not None and when >= cutoff:
                total += 1
        return total

    def recent_records(
        self, *, kind: str, key_field: str, key_value: str, limit: int = 20
    ) -> Sequence[Mapping[str, Any]]:
        items = [item for item in self.of_kind(kind) if str(item.get(key_field)) == key_value]
        return tuple(items[-limit:])

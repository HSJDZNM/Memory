"""幂等台账：同一个 key 重试**不重复产生副作用或审计记录**。

判定类路由（evaluate / retrieve）本身不写业务状态，但它们的结论会被写进观测日志、
可能被上层当作"已经授权过一次"的依据，因此同样按键去重：

- 同一个 `idempotency_key` + 同一个请求摘要 → 直接返回**原来那份响应**（标记 replayed）；
- 同一个 key + 不同请求摘要 → 409 `idempotency_key_conflict`（不覆盖、不合并）；
- 台账读写不可用 → 503 `idempotency_unavailable`（宁可拒绝，也不重复执行一次判定）。

台账是**整份重写**的 JSONL（每个租户一份）：条目带 `expires_at`，读取时顺带压缩过期项。
整份重写而不是追加，是因为"同一个 key 只能有一个结论"——追加写会留下互相矛盾的历史，
而幂等台账要回答的正是"上次那个 key 的结论是什么"。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

from .errors import ApiError, ErrorCode

__all__ = ["IDEMPOTENCY_SCHEMA_VERSION", "IdempotencyLedger", "IdempotentResult", "request_digest"]

IDEMPOTENCY_SCHEMA_VERSION = "1.0"
_MAX_RESPONSE_BYTES = 8192
_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def request_digest(payload: Mapping[str, Any]) -> str:
    """请求摘要：稳定的 JSON 序列化 + sha256（键顺序不影响结果）。"""

    try:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ApiError(ErrorCode.BODY_INVALID, "请求无法规范化成摘要") from error
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IdempotentResult:
    """命中台账时的结果：原响应的状态码与正文。"""

    status: int
    body: Mapping[str, Any]
    digest: str


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve()).casefold()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """跨进程互斥：Windows 用 msvcrt，POSIX 用 flock（与 Phase 6 台账同一做法）。

    **锁的是独立的 `.lock` 文件，不是数据文件本身**：Windows 上对 `a+b` 句柄加字节锁
    会让同一进程里的 `read_text()` 直接吃 `PermissionError`（锁保护了数据文件，
    于是数据文件也读不了了）。锁对象与数据对象分开，是这个平台上唯一稳定的做法。
    """

    lock_path = path.with_name(path.name + ".lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        if handle.seek(0, 2) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
    except OSError as error:
        raise ApiError(
            ErrorCode.IDEMPOTENCY_UNAVAILABLE,
            f"幂等台账锁不可用（{type(error).__name__}）",
            retryable=True,
        ) from error

    try:
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + 5
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise ApiError(
                            ErrorCode.IDEMPOTENCY_UNAVAILABLE,
                            "幂等台账锁超时",
                            retryable=True,
                        ) from error
                    time.sleep(0.01)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


@contextmanager
def _memory_lock() -> Iterator[None]:
    yield


class IdempotencyLedger:
    """按 (client, api_version, route, key) 去重的台账。`path=None` 时退化为进程内。"""

    def __init__(self, path: Optional[Path | str], *, ttl_seconds: int = 900) -> None:
        self.path = None if path is None else Path(path)
        self.ttl_seconds = max(0, int(ttl_seconds))
        self._lock = _path_lock(self.path) if self.path is not None else threading.RLock()
        self._memory: dict[str, dict[str, Any]] = {}

    @staticmethod
    def entry_key(client_id: str, api_version: str, route: str, key: str) -> str:
        return f"{client_id}|{api_version}|{route}|{key}"

    @contextmanager
    def _guard(self) -> Iterator[None]:
        with self._lock:
            if self.path is None:
                with _memory_lock():
                    yield
            else:
                with _file_lock(self.path):
                    yield

    # ------------------------------------------------------------------ 读

    def _read_unlocked(self) -> dict[str, dict[str, Any]]:
        if self.path is None:
            return {item: dict(value) for item, value in self._memory.items()}
        if not self.path.is_file():
            return {}
        entries: dict[str, dict[str, Any]] = {}
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ApiError(
                ErrorCode.IDEMPOTENCY_UNAVAILABLE,
                f"幂等台账不可读（{type(error).__name__}）",
                retryable=True,
            ) from error
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ApiError(
                    ErrorCode.IDEMPOTENCY_UNAVAILABLE,
                    f"幂等台账第 {number} 行不是合法 JSON",
                    retryable=True,
                ) from error
            if not isinstance(item, Mapping):
                raise ApiError(
                    ErrorCode.IDEMPOTENCY_UNAVAILABLE,
                    f"幂等台账第 {number} 行必须是对象",
                    retryable=True,
                )
            if item.get("ledger_schema_version") != IDEMPOTENCY_SCHEMA_VERSION:
                raise ApiError(
                    ErrorCode.IDEMPOTENCY_UNAVAILABLE,
                    "幂等台账协议版本未知；拒绝按不确定的语义去重",
                    retryable=True,
                )
            key = str(item.get("entry_key") or "")
            if key:
                entries[key] = dict(item)
        return entries

    def lookup(
        self, *, client_id: str, api_version: str, route: str, key: str, digest: str
    ) -> Optional[IdempotentResult]:
        """命中且请求一致时返回原响应；请求不一致时 409。"""

        entry_key = self.entry_key(client_id, api_version, route, key)
        with self._guard():
            entries = self._read_unlocked()
            item = entries.get(entry_key)
            if item is None:
                return None
            if not self._fresh(item):
                entries.pop(entry_key, None)
                self._write_unlocked(entries)
                return None
        stored = str(item.get("request_digest") or "")
        if stored != digest:
            raise ApiError(
                ErrorCode.IDEMPOTENCY_KEY_CONFLICT,
                "同一个 idempotency_key 被用于了不同的请求；请换一个 key",
            )
        body = item.get("body")
        return IdempotentResult(
            status=int(item.get("status", 200)),
            body=dict(body) if isinstance(body, Mapping) else {},
            digest=stored,
        )

    def record(
        self,
        *,
        client_id: str,
        api_version: str,
        route: str,
        key: str,
        digest: str,
        status: int,
        body: Mapping[str, Any],
        canonical_body: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """写入一次结果；响应体无法完整保存时显式失败，不写残缺条目。

        `canonical_body` 是**键序已固定**的那一份（调用方会把它作为本次响应返回）。
        给了它就直接存它：重放于是与首次逐字节相同；没给就按 `sort_keys` 规范化。
        """

        entry_key = self.entry_key(client_id, api_version, route, key)
        # 台账里存的是**规范化后的那一份**，调用方也应当把同一份作为响应返回
        # （见 policy_api.runtime 里 KEEP_KEYS 的说明）：否则"重放"只是语义相同、
        # 字节不同，而对调用方来说"这次响应和上次一样吗"是一个可以用字节回答的问题。
        source = dict(body if canonical_body is None else canonical_body)
        try:
            serialized = json.dumps(source, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            serialized = None
        if serialized is None:
            raise ApiError(
                ErrorCode.IDEMPOTENCY_UNAVAILABLE,
                "响应无法序列化进幂等台账；拒绝返回不可可靠重放的结果",
                retryable=True,
            )
        response_bytes = len(serialized.encode("utf-8"))
        if response_bytes > _MAX_RESPONSE_BYTES:
            raise ApiError(
                ErrorCode.IDEMPOTENCY_UNAVAILABLE,
                f"响应体 {response_bytes} 字节超过幂等台账上限 {_MAX_RESPONSE_BYTES} 字节；"
                "拒绝写入残缺重放记录",
                retryable=True,
            )
        parsed = json.loads(serialized)
        if not isinstance(parsed, dict):
            raise ApiError(
                ErrorCode.IDEMPOTENCY_UNAVAILABLE,
                "幂等响应必须是 JSON 对象；拒绝写入不可重放的结果",
                retryable=True,
            )
        stored_body = parsed
        record = {
            "ledger_schema_version": IDEMPOTENCY_SCHEMA_VERSION,
            "entry_key": entry_key,
            "client_id": client_id,
            "api_version": api_version,
            "route": route,
            "idempotency_key": key,
            "request_digest": digest,
            "status": int(status),
            "body": stored_body,
            "recorded_at": _utc_now().isoformat().replace("+00:00", "Z"),
            "expires_at": (_utc_now() + datetime.timedelta(seconds=self.ttl_seconds))
            .isoformat()
            .replace("+00:00", "Z"),
        }
        with self._guard():
            entries = self._read_unlocked()
            entries[entry_key] = record
            self._write_unlocked(entries)

    # ------------------------------------------------------------------ 内部

    def _fresh(self, item: Mapping[str, Any]) -> bool:
        if self.ttl_seconds == 0:
            return True
        expires = str(item.get("expires_at") or "")
        if not expires:
            return False
        try:
            moment = datetime.datetime.strptime(expires, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=datetime.timezone.utc
            )
        except ValueError:
            # 过期时间读不懂 = 不能证明它还有效：按过期处理（宁可重算一次判定）。
            return False
        return _utc_now() < moment

    def _write_unlocked(self, entries: Mapping[str, Mapping[str, Any]]) -> None:
        if self.path is None:
            self._memory = {key: dict(value) for key, value in entries.items()}
            return
        payload = "".join(
            json.dumps(dict(item), ensure_ascii=False, sort_keys=True) + "\n"
            for item in entries.values()
        )
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(payload, encoding="utf-8", newline="\n")
            os.replace(temporary, self.path)
        except OSError as error:
            raise ApiError(
                ErrorCode.IDEMPOTENCY_UNAVAILABLE,
                f"幂等台账不可写（{type(error).__name__}）",
                retryable=True,
            ) from error

    def entries(self) -> Mapping[str, Mapping[str, Any]]:
        with self._guard():
            return {key: dict(value) for key, value in self._read_unlocked().items()}

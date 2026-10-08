"""`event_id` 的「查了再写」必须变成「原子认领」（每个 hook 调用都是独立进程）。

`_decide` 先 `lookup(event_id)` 判「判过没有」，而 `_audit` 的 append 在判定**末尾**才发生：
两者之间隔着取证与判定（可能几秒）。两个并发投递于是可以双双查到「没判过」再各执行一次工具——
而每个 hook 调用都是独立进程，没有内存里的锁能兜住它。

现在：查完立刻用**独占创建**（`O_CREAT|O_EXCL`）为这个 event_id 认领一次处理权；
认领失败 = 另一路投递已在处理（或它崩在半路、没留下判定）→ 不重复执行，理由按能否证明
「同一个载荷」分开写（`event_replay` / `event_id_reuse`）。
"""

from __future__ import annotations

from conftest import dsh_event

from adapters.dsh.adapter import load_config, to_policy_event
from adapters.dsh.hooks import EXIT_ALLOW, EXIT_BLOCK, AuditLedger, run_hook


def test_reserve_is_atomic_and_keeps_the_first_digest(tmp_root) -> None:
    """认领按 event_id 独占：第二次拿到的必须是**第一次**记下的摘要。"""

    ledger = AuditLedger(tmp_root / "audit.jsonl")

    assert ledger.reserve("evt-1", payload_digest="sha256:aaa") is None
    assert ledger.reserve("evt-1", payload_digest="sha256:bbb") == "sha256:aaa"
    # 认领是**按 event** 的，不是全局锁：另一个 event_id 照常认领成功
    assert ledger.reserve("evt-2", payload_digest="sha256:ccc") is None


def test_an_already_claimed_event_is_refused_before_evaluation(
    dsh_config_path, dsh_project, tmp_root
) -> None:
    """另一路投递已认领（还没写出判定）时：这次投递不判定、不放行，理由点名「认领」。"""

    payload = dsh_event("pre-tool-use-edit-allow.json", cwd=str(dsh_project))
    audit = tmp_root / "audit.jsonl"
    config = load_config(dsh_config_path)
    event = to_policy_event(payload, config=config).event
    assert event is not None

    # 「另一路投递」：认领同一个 event_id，然后**崩溃**（没有写出任何判定记录）
    ledger = AuditLedger(audit)
    assert ledger.reserve(event.event_id, payload_digest=event.payload_digest) is None

    outcome = run_hook(payload, config_path=dsh_config_path, audit_path=audit)

    # 修前：这条载荷在策略上是 allow（fixture 就是 allow 形态），会被放行 —— 也就是"同一次工具
    # 调用被执行两遍"的那一半。修后：在判定之前就被认领挡住。
    assert outcome.exit_code == EXIT_BLOCK, outcome.reason_code
    assert outcome.reason_code == "event_replay"
    assert "认领" in (outcome.stderr or "")
    assert outcome.decision is None  # 没有做出判定，更没有放行


def test_a_claimed_event_with_a_different_payload_is_id_reuse(
    dsh_config_path, dsh_project, tmp_root
) -> None:
    """认领过、但载荷摘要对不上：这是「同一个 event_id 被换了参数」，理由必须与重放分开。"""

    payload = dsh_event("pre-tool-use-edit-allow.json", cwd=str(dsh_project))
    audit = tmp_root / "audit.jsonl"
    config = load_config(dsh_config_path)
    event = to_policy_event(payload, config=config).event
    assert event is not None

    ledger = AuditLedger(audit)
    assert ledger.reserve(event.event_id, payload_digest="sha256:完全不认识的载荷") is None

    outcome = run_hook(payload, config_path=dsh_config_path, audit_path=audit)

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "event_id_reuse"
    assert "对不上" in (outcome.stderr or "") or "读不到" in (outcome.stderr or "")

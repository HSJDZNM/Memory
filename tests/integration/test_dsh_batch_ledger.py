"""C1-a 批次台账（只报告）：五道门的可执行版本。

本文件只证明一件事：**账本打开之后，判定一个字都没变**。五道门分别是——

1. 账本开 / 关两种配置下，同一事件的 `decision` / `violations` / `reason_code` 逐字节相等，
   审计记录只多出 `batch_ref` 与 `batch` 两个键（`reading_context` 里的配置摘要必然不同：
   两份 YAML 的差别就是"声明了这一段"，它是旁注、不是判定，故在比较里剥掉并写明理由）；
2. `batch_ref` 稳定：同一会话、同一批目标两次计算逐字节相同；加一个新目标必然改变它；
3. 两个 session 各写自己的文件，先写的那个一个字节都不被覆盖；
4. 账本不可写 / session_id 不是安全文件名时 **fail-open**：只多一行 stderr，
   `batch.recorded=false` + reason 进审计，退出码与判定不变；
5. 既有 dsh 契约 / 集成用例仍绿（由 pytest 的其余用例承担，不在本文件里重复）。

另有一条测"协议轴"：`BATCH_LEDGER_SCHEMA_VERSION` 是账本文件自己的版本轴，
`AUDIT_SCHEMA_VERSION` 因为新增键而 1.3 → 1.4——两者各走各的，不许共用一个号。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from conftest import POLICIES_DIR, dsh_event, write_dsh_config

from adapters.dsh import hooks as hooks_module
from adapters.dsh.adapter import DshEventError, load_config
from adapters.dsh.batch_ledger import (
    BATCH_DIRNAME,
    BATCH_LEDGER_SCHEMA_VERSION,
    BatchLedgerError,
    batch_ref,
    session_filename,
    targets_digest,
)
from adapters.dsh.hooks import AUDIT_SCHEMA_VERSION, AuditLedger, DshPreExecuteHook
from policy.loader import load_rule_set

pytestmark = pytest.mark.integration

# 固定的 `recorded_at` / `timestamp`：让"同一事件"在两次运行里除了被测的差异之外逐字节可比。
FIXED_NOW = "2026-10-21T00:00:00Z"
EDIT_TARGET = "src/shop/order_controller.py"
WRITE_TARGET = "src/shop/cart_service.py"
SESSION = "sess-demo-0001"


@pytest.fixture()
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> str:
    """把审计 / 账本里的墙钟固定下来：比较的是载荷，不是"跑得有多快"。"""

    monkeypatch.setattr(hooks_module, "_utc_now", lambda: FIXED_NOW)
    return FIXED_NOW


def build(
    tmp_root: Path, name: str, *, batch: dict | None = None
) -> tuple[Path, object, DshPreExecuteHook, Path]:
    """在本次用例自己的目录里装配一个受控项目 + Hook（每个用例互不共享审计与账本）。"""

    project = tmp_root / name / "demo-shop"
    (project / "src" / "shop").mkdir(parents=True, exist_ok=True)
    config_path = write_dsh_config(
        tmp_root / name / "dsh-adapter.yaml",
        project_root=project,
        rules=POLICIES_DIR,
        batch_ledger=batch,
    )
    config = load_config(config_path)
    rules = load_rule_set(config.rule_dirs, repo_root=config.rule_anchor)
    audit = tmp_root / name / "audit.jsonl"
    hook = DshPreExecuteHook(config=config, rules=rules, ledger=AuditLedger(audit))
    # elapsed_ms 也是墙钟：固定成 0，让"只差新增键"这条比较真的只看键与值。
    hook.clock = lambda: 0.0
    return project, config, hook, audit


def run(
    hook: DshPreExecuteHook,
    project: Path,
    fixture: str = "pre-tool-use-edit-allow.json",
    **overrides: object,
):
    return hook.handle(dsh_event(fixture, cwd=str(project), **overrides))


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def decision_row(path: Path, reason_code: str) -> dict:
    found = [row for row in rows(path) if row.get("reason_code") == reason_code]
    assert len(found) == 1, f"期望恰好一条 reason_code={reason_code} 的记录，得到 {len(found)}"
    return found[0]


def batch_path(project: Path, session_id: str = SESSION) -> Path:
    return project / ".policy" / BATCH_DIRNAME / f"{session_id}.jsonl"


def ledger_records(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------- 协议轴


def test_the_batch_ledger_has_its_own_protocol_axis() -> None:
    """账本文件与审计记录是两套协议：加键各升各的号，谁也不跟随谁。"""

    assert BATCH_LEDGER_SCHEMA_VERSION == "1.0"
    # C1-a 给判定记录新增 batch_ref 与 batch → 审计协议 1.3 → 1.4（同一条统一规则）。
    assert AUDIT_SCHEMA_VERSION == "1.4"
    assert AUDIT_SCHEMA_VERSION != BATCH_LEDGER_SCHEMA_VERSION


def test_batch_ref_only_covers_the_session_and_the_sorted_target_set() -> None:
    """摘要口径：排序去重、时间不参与、会话是输入的一部分。"""

    assert targets_digest(["b.py", "a.py"]) == targets_digest(["a.py", "b.py", "a.py"])
    assert targets_digest(["a.py"]) != targets_digest(["a.py", "b.py"])
    first = batch_ref("session-a", [EDIT_TARGET])
    assert first == batch_ref("session-a", [EDIT_TARGET])
    # 同一批目标、不同会话不能撞成同一个批次（按会话折叠的前提）。
    assert first != batch_ref("session-b", [EDIT_TARGET])


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "..", ".", "", "a\nb", "x" * 200])
def test_an_unsafe_session_id_is_refused_instead_of_sanitized(bad: str) -> None:
    """清洗会把两个会话映到同一个文件——这正是"并发会话互相污染"的形状，所以拒绝。"""

    with pytest.raises(BatchLedgerError):
        session_filename(bad)


# --------------------------------------------------------------------------- 门 ①：判定不变


def test_switching_the_ledger_on_changes_only_the_audit_keys(
    tmp_root: Path, fixed_now: str
) -> None:
    """账本开 / 关两配置：同一事件的判定逐字节相等，审计只多两个键。"""

    off_project, _, off_hook, off_audit = build(tmp_root, "off")
    on_project, _, on_hook, on_audit = build(
        tmp_root, "on", batch={"enabled": True, "ttl_hours": 24}
    )

    off = run(off_hook, off_project)
    on = run(on_hook, on_project)

    # ① 判定本身：decision / violations / reason_code（以及退出码与执行事实）逐字节相等。
    assert (off.exit_code, off.reason_code, off.executed) == (0, "allow", True)
    assert (on.exit_code, on.reason_code, on.executed) == (0, "allow", True)
    assert dump(on.decision.model_dump(mode="json")) == dump(off.decision.model_dump(mode="json"))
    assert dump([item.model_dump(mode="json") for item in on.decision.violations]) == dump(
        [item.model_dump(mode="json") for item in off.decision.violations]
    )

    # ② 审计：账本那一条记录除了新增键之外与关闭时逐字段相同。
    on_row = decision_row(on_audit, "allow")
    off_row = decision_row(off_audit, "allow")

    def comparable(row: dict) -> dict:
        # reading_context.declarations.adapter_config 是**配置文件自己**的摘要：两份 YAML 的
        # 差别正是"声明了 batch_ledger"这一行。它是"这条记录属于哪套声明"的旁注，不参与判定，
        # 因此从比较里剥掉并在断言里单独确认其余字段一致。
        return {key: value for key, value in row.items() if key != "reading_context"}

    on_extra = set(comparable(on_row)) - set(comparable(off_row))
    assert on_extra == {"batch_ref", "batch"}
    assert set(comparable(off_row)) - set(comparable(on_row)) == set()
    assert {
        key: value
        for key, value in comparable(on_row).items()
        if key not in {"batch_ref", "batch"}
    } == comparable(off_row)
    assert not {"batch", "batch_ref"} & set(off_row)

    # ③ 台账确实只记了目标集合，没把正文 / 判定塞进账本文件。
    assert on_row["batch"]["recorded"] is True
    assert on_row["batch"]["target"] == EDIT_TARGET
    assert on_row["batch"]["target_count"] == 1
    assert on_row["batch"]["path"] == f".policy/{BATCH_DIRNAME}/{SESSION}.jsonl"
    records = ledger_records(batch_path(on_project))
    assert [record["target"] for record in records] == [EDIT_TARGET]
    assert set(records[0]) == {
        "schema_version",
        "session_id",
        "event_id",
        "tool",
        "target",
        "recorded_at",
    }
    assert records[0]["recorded_at"] == fixed_now


def test_without_the_declaration_nothing_is_written_and_no_batch_key_appears(
    tmp_root: Path, fixed_now: str
) -> None:
    """未声明 = 行为与现在逐字相同：没有目录、没有键、没有 stderr。"""

    project, _, hook, audit = build(tmp_root, "undeclared")
    outcome = run(hook, project)

    assert (outcome.exit_code, outcome.reason_code) == (0, "allow")
    assert not (project / ".policy" / BATCH_DIRNAME).exists()
    assert "batch" not in decision_row(audit, "allow")


# --------------------------------------------------------------------------- 门 ②：batch_ref 稳定


def test_batch_ref_is_stable_and_folds_the_same_session_batch(
    tmp_root: Path, fixed_now: str
) -> None:
    """连续两次写同一个目标：batch_ref 相同；第三次写新目标：batch_ref 变。"""

    project, _, hook, audit = build(
        tmp_root, "stable", batch={"enabled": True, "ttl_hours": 24}
    )

    first = run(hook, project, tool_use_id="call-a")
    second = run(hook, project, tool_use_id="call-b")
    assert (first.exit_code, second.exit_code) == (0, 0)

    allows = [row for row in rows(audit) if row.get("reason_code") == "allow"]
    assert len(allows) == 2
    expected = batch_ref(SESSION, [EDIT_TARGET])
    assert {row["batch_ref"] for row in allows} == {expected}
    assert allows[0]["batch"]["target_count"] == 1

    third = run(hook, project, fixture="pre-tool-use-write-allow.json", tool_use_id="call-c")
    assert third.exit_code == 0
    latest = [row for row in rows(audit) if row.get("reason_code") == "allow"][-1]
    assert latest["batch_ref"] != expected
    assert latest["batch"]["target_count"] == 2
    assert latest["batch"]["targets_digest"] == targets_digest([EDIT_TARGET, WRITE_TARGET])

    # 同一会话的三条账本记录：两条同一批（同 batch_ref），第三条是新的一批。
    records = ledger_records(batch_path(project))
    assert [record["target"] for record in records] == [
        EDIT_TARGET,
        EDIT_TARGET,
        WRITE_TARGET,
    ]
    assert records[0]["event_id"] == f"{SESSION}:call-a"
    assert records[1]["event_id"] == f"{SESSION}:call-b"

    # 半行 / 坏行不会让"这批目标"悄悄变：跳过数必须出现在审计里。
    with batch_path(project).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("{ not json\n")
    fourth = run(hook, project, tool_use_id="call-d")
    assert fourth.exit_code == 0
    latest = [row for row in rows(audit) if row.get("reason_code") == "allow"][-1]
    assert latest["batch"]["skipped_lines"] == 1
    assert latest["batch"]["target_count"] == 2


# --------------------------------------------------------------------------- 门 ③：会话隔离


def test_two_sessions_never_overwrite_each_other(tmp_root: Path, fixed_now: str) -> None:
    project, _, hook, _ = build(tmp_root, "sessions", batch={"enabled": True, "ttl_hours": 24})

    run(hook, project, session_id="sess-alpha", tool_use_id="call-1")
    alpha = batch_path(project, "sess-alpha")
    alpha_bytes = alpha.read_bytes()

    run(hook, project, session_id="sess-beta", tool_use_id="call-2")
    beta = batch_path(project, "sess-beta")

    assert alpha.is_file() and beta.is_file()
    assert alpha.read_bytes() == alpha_bytes  # 先写的那个一个字节都不被改写
    assert ledger_records(alpha)[0]["session_id"] == "sess-alpha"
    assert ledger_records(beta)[0]["session_id"] == "sess-beta"
    assert batch_ref("sess-alpha", [EDIT_TARGET]) != batch_ref("sess-beta", [EDIT_TARGET])


# --------------------------------------------------------------------------- 门 ④：fail-open


def test_an_unwritable_ledger_only_adds_a_stderr_line_and_a_status(
    tmp_root: Path, fixed_now: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """账本不可写：判定与关闭时逐字节相等，审计写 batch.recorded=false + reason。"""

    baseline_project, _, baseline_hook, baseline_audit = build(tmp_root, "baseline")
    baseline = run(baseline_hook, baseline_project)

    blocked_root = tmp_root / "blocked-root"
    blocked_root.write_text("not a directory", encoding="utf-8")
    project, _, hook, audit = build(
        tmp_root, "unwritable", batch={"enabled": True, "root": str(blocked_root)}
    )
    outcome = run(hook, project)

    assert (outcome.exit_code, outcome.reason_code, outcome.executed) == (
        baseline.exit_code,
        baseline.reason_code,
        baseline.executed,
    )
    assert dump(outcome.decision.model_dump(mode="json")) == dump(
        baseline.decision.model_dump(mode="json")
    )
    stderr = capsys.readouterr().err
    assert stderr.count("BATCH LEDGER UNAVAILABLE") == 1

    row = decision_row(audit, "allow")
    assert "batch_ref" not in row
    batch = row["batch"]
    assert batch["recorded"] is False
    assert batch["status"] == "unavailable"
    assert batch["reason"]
    # 失败理由同样不许出现本机绝对路径（审计脱敏纪律）。
    assert str(blocked_root) not in batch["reason"]
    # 与关闭账本的那次运行相比，只有 batch 相关的键不同。
    baseline_row = decision_row(baseline_audit, "allow")
    different = {
        key
        for key in set(row) | set(baseline_row)
        if key != "reading_context" and row.get(key) != baseline_row.get(key)
    }
    assert different == {"batch"}
    assert "batch_ref" not in baseline_row


def test_an_unsafe_session_id_degrades_instead_of_writing_outside_the_root(
    tmp_root: Path, fixed_now: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """session_id 不是安全文件名：拒绝记录（不是清洗），降级成 batch 状态。

    这里直接调 `book_batch` 而不是走完整 Hook：受控写类动作的标识在 **Phase 4 门禁**那层
    更早被 `_require_identifier` 拒绝（那是它自己的失败关闭，与本模块无关）。本用例要钉住的
    是本模块的边界——拿到一个不能当文件名的 session_id 时，它**不**拼路径、**不**静默成功。
    """

    from adapters.dsh.adapter import to_policy_event

    project, config, hook, _ = build(
        tmp_root, "unsafe", batch={"enabled": True, "ttl_hours": 24}
    )
    admission = to_policy_event(
        dsh_event("pre-tool-use-edit-allow.json", cwd=str(project), session_id="../escape"),
        config=config,
    )
    assert admission.governed and admission.event is not None

    fields = hook.book_batch(event=admission.event)

    assert fields["batch"]["recorded"] is False
    assert fields["batch"]["status"] == "unavailable"
    assert "session_id" in fields["batch"]["reason"]
    assert "batch_ref" not in fields
    assert "BATCH LEDGER UNAVAILABLE" in capsys.readouterr().err
    assert not (project / ".policy" / BATCH_DIRNAME).exists()


# --------------------------------------------------------------------------- TTL / 保留


def test_expired_sessions_are_pruned_while_the_current_one_is_kept(
    tmp_root: Path, fixed_now: str
) -> None:
    project, _, hook, audit = build(tmp_root, "ttl", batch={"enabled": True, "ttl_hours": 1})
    directory = project / ".policy" / BATCH_DIRNAME
    directory.mkdir(parents=True)
    stale = directory / "sess-stale.jsonl"
    fresh = directory / "sess-fresh.jsonl"
    other = directory / "notes.txt"
    for path in (stale, fresh, other):
        path.write_text("{}\n", encoding="utf-8")
    old = time.time() - 3 * 3600
    os.utime(stale, (old, old))

    outcome = run(hook, project)
    assert outcome.exit_code == 0

    assert not stale.exists()
    assert fresh.exists() and other.exists()
    assert batch_path(project).exists()
    assert decision_row(audit, "allow")["batch"]["pruned"] == 1


def test_pruning_refuses_a_root_that_is_not_the_conventional_directory(
    tmp_root: Path, fixed_now: str
) -> None:
    """写错的 root 不能被 TTL 清理当成批次目录：目录名不是 pre-evidence-batches 就不清理。"""

    custom = tmp_root / "custom-batches"
    custom.mkdir()
    stale = custom / "sess-old.jsonl"
    stale.write_text("{}\n", encoding="utf-8")
    old = time.time() - 3 * 3600
    os.utime(stale, (old, old))

    project, _, hook, audit = build(
        tmp_root, "custom", batch={"enabled": True, "root": str(custom), "ttl_hours": 1}
    )
    outcome = run(hook, project)

    assert outcome.exit_code == 0
    assert stale.exists(), "非约定目录名不得被清理（一个写错的 root 会删到别的 .policy 文件）"
    assert decision_row(audit, "allow")["batch"]["pruned"] == 0
    assert (custom / f"{SESSION}.jsonl").is_file()


# --------------------------------------------------------------------------- 配置：声明即契约


def test_an_unknown_batch_ledger_field_is_refused(tmp_root: Path) -> None:
    project = tmp_root / "unknown" / "demo-shop"
    project.mkdir(parents=True)
    config_path = write_dsh_config(
        tmp_root / "unknown" / "dsh-adapter.yaml",
        project_root=project,
        rules=POLICIES_DIR,
        batch_ledger={"enabled": True, "retention_days": 7},
    )
    with pytest.raises(DshEventError, match="batch_ledger"):
        load_config(config_path)


def test_the_batch_root_may_not_be_the_project_root_or_its_ancestor(tmp_root: Path) -> None:
    project = tmp_root / "root-unsafe" / "demo-shop"
    project.mkdir(parents=True)
    config_path = write_dsh_config(
        tmp_root / "root-unsafe" / "dsh-adapter.yaml",
        project_root=project,
        rules=POLICIES_DIR,
        batch_ledger={"enabled": True, "root": str(tmp_root / "root-unsafe")},
    )
    with pytest.raises(DshEventError, match="batch_ledger.root"):
        load_config(config_path)


def test_a_disabled_declaration_is_explicit_and_writes_nothing(
    tmp_root: Path, fixed_now: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """declared + enabled=false 与"没有声明"是两个读法：审计里必须说清楚是哪一个。"""

    project, _, hook, audit = build(
        tmp_root, "disabled", batch={"enabled": False}
    )
    outcome = run(hook, project)

    assert (outcome.exit_code, outcome.reason_code) == (0, "allow")
    assert capsys.readouterr().err == ""
    assert not (project / ".policy" / BATCH_DIRNAME).exists()
    row = decision_row(audit, "allow")
    assert row["batch"]["status"] == "disabled"
    assert row["batch"]["recorded"] is False
    assert "batch_ref" not in row

"""C1-b 批次视图（batch_ledger.batch_view）的单元门：逐目标折叠 + 五类排除 + cap。

这些用例只碰账本与 workspace 文件，不跑验证器/Hook：负例的形状在这里被钉死，
端到端的审计/判定在 tests/integration/test_dsh_pre_evidence_hook.py 与
tests/integration/test_dsh_batch_ledger.py 里。
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from adapters.dsh.batch_ledger import (
    BATCH_LEDGER_SCHEMA_VERSION,
    BatchLedgerError,
    append_abandon,
    append_settlement,
    append_target,
    batch_view,
    read_records,
)

SESSION = "sess-batch-1"
NOW = "2026-10-21T00:00:00Z"
WRITE_TOOLS = frozenset({"edit", "write", "str_replace_editor"})


def validate_target(target: str) -> str:
    if target.startswith("/") or target.startswith("\\\\") or ".." in target.split("/"):
        raise ValueError(f"not a repo-relative path: {target!r}")
    return target.replace("\\\\", "/")


def file_sha(workspace: Path, relative: str) -> str:
    return "sha256:" + sha256((workspace / relative).read_bytes()).hexdigest()


def write_file(workspace: Path, relative: str, content: str) -> None:
    target = workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")


def propose(root: Path, *, event: str, target: str, tool: str = "edit") -> None:
    append_target(
        root=root,
        session_id=SESSION,
        event_id=event,
        tool=tool,
        target=target,
        recorded_at=NOW,
    )


def settle(
    root: Path,
    *,
    event: str,
    target: str,
    outcome: str = "allowed",
    content_sha256: str | None = None,
) -> None:
    append_settlement(
        root=root,
        session_id=SESSION,
        event_id=event,
        target=target,
        outcome=outcome,
        reason_code="allow" if outcome == "allowed" else "policy_block",
        content_sha256=content_sha256,
        recorded_at=NOW,
    )


def view_of(
    root: Path,
    workspace: Path,
    *,
    max_targets: int = 20,
    exclude_event_id: str | None = None,
):
    return batch_view(
        root=root,
        session_id=SESSION,
        exclude_event_id=exclude_event_id,
        workspace=workspace,
        max_targets=max_targets,
        validate_target=validate_target,
        write_tools=WRITE_TOOLS,
    )


def test_a_settled_allowed_target_with_a_matching_hash_is_a_member(
    tmp_root: Path,
) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")
    settle(root, event="e1", target="src/a.py", content_sha256=file_sha(workspace, "src/a.py"))

    view = view_of(root, workspace)

    assert view.members == ("src/a.py",)
    assert view.applied is True
    assert view.status == "applied"
    assert view.settled == {"allowed": 1, "blocked": 0, "abandoned": 0}


def test_an_unsettled_target_is_excluded_and_named(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.excluded["unsettled"] == ("src/a.py",)
    assert view.applied is False
    assert view.status == "partial"


def test_a_blocked_target_is_excluded_and_named(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")
    settle(root, event="e1", target="src/a.py", outcome="blocked")

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.excluded["blocked"] == ("src/a.py",)
    assert view.settled["blocked"] == 1


def test_a_1_0_record_is_legacy_and_never_a_member(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{SESSION}.jsonl").write_text(
        '{"schema_version": "1.0", "session_id": "sess-batch-1", "event_id": "e1",'
        ' "tool": "edit", "target": "src/a.py", "recorded_at": "' + NOW + '"}\n',
        encoding="utf-8",
        newline="",
    )

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.excluded["legacy"] == ("src/a.py",)
    records, skipped = read_records(root / f"{SESSION}.jsonl")
    assert records[0]["kind"] == "proposal"
    assert records[0]["schema_version"] == "1.0"
    assert skipped == 0


def test_an_unknown_schema_version_line_is_skipped_and_counted(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")
    settle(root, event="e1", target="src/a.py", content_sha256=file_sha(workspace, "src/a.py"))
    with (root / f"{SESSION}.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write('{"schema_version": "9.9", "kind": "proposal"}\n')

    view = view_of(root, workspace)

    assert view.members == ("src/a.py",)
    assert view.skipped_lines == 1
    assert view.status == "partial"


def test_a_session_mismatch_inside_the_file_is_invalid(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{SESSION}.jsonl").write_text(
        '{"schema_version": "1.1", "kind": "proposal", "session_id": "other",'
        ' "event_id": "e1", "tool": "edit", "target": "src/a.py", "recorded_at": "' + NOW + '"}\n',
        encoding="utf-8",
        newline="",
    )

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.invalid_lines == 1


def test_an_absolute_or_escaping_target_is_invalid(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    for target in ("/etc/passwd", "../outside.py"):
        propose(root, event="e-" + target, target=target)

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.invalid_lines == 2


def test_the_latest_settlement_for_the_latest_proposal_wins(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")
    settle(root, event="e1", target="src/a.py", content_sha256=file_sha(workspace, "src/a.py"))
    propose(root, event="e2", target="src/a.py")
    settle(root, event="e2", target="src/a.py", outcome="blocked")

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.excluded["blocked"] == ("src/a.py",)


def test_an_abandon_after_the_proposal_excludes_it(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")
    settle(root, event="e1", target="src/a.py", content_sha256=file_sha(workspace, "src/a.py"))
    append_abandon(root=root, session_id=SESSION, reason="operator cleared", recorded_at=NOW)

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.excluded["abandoned"] == ("src/a.py",)


def test_a_targeted_abandon_excludes_only_that_target(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    write_file(workspace, "src/b.py", "y = 1\n")
    for event, target in (("e1", "src/a.py"), ("e2", "src/b.py")):
        propose(root, event=event, target=target)
        settle(root, event=event, target=target, content_sha256=file_sha(workspace, target))
    append_abandon(root=root, session_id=SESSION, reason="wrong file", target="src/a.py", recorded_at=NOW)

    view = view_of(root, workspace)

    assert view.members == ("src/b.py",)
    assert view.excluded["abandoned"] == ("src/a.py",)


def test_the_member_cap_truncates_and_says_so(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    targets = ("src/a.py", "src/b.py", "src/c.py")
    for index, target in enumerate(targets):
        write_file(workspace, target, "x = " + str(index) + "\n")
        propose(root, event="e" + str(index), target=target)
        settle(
            root,
            event="e" + str(index),
            target=target,
            content_sha256=file_sha(workspace, target),
        )

    view = view_of(root, workspace, max_targets=2)

    assert view.members == ("src/a.py", "src/b.py")
    assert view.truncated == 1
    assert view.status == "partial"


def test_max_targets_zero_disables_members_but_reports_truncation(
    tmp_root: Path,
) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")
    settle(root, event="e1", target="src/a.py", content_sha256=file_sha(workspace, "src/a.py"))

    view = view_of(root, workspace, max_targets=0)

    assert view.members == ()
    assert view.applied is False
    assert view.truncated == 1


def test_a_settled_member_whose_hash_mismatches_is_not_landed(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")
    settle(root, event="e1", target="src/a.py", content_sha256="sha256:" + "0" * 64)

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.excluded["not_landed"] == ("src/a.py",)


def test_a_settled_member_without_a_content_hash_is_not_landed(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")
    settle(root, event="e1", target="src/a.py", content_sha256=None)

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.excluded["not_landed"] == ("src/a.py",)


def test_a_corrupt_line_makes_the_batch_partial_not_unreadable(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py")
    settle(root, event="e1", target="src/a.py", content_sha256=file_sha(workspace, "src/a.py"))
    with (root / f"{SESSION}.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write('{"broken": ')

    view = view_of(root, workspace)

    assert view.members == ("src/a.py",)
    assert view.skipped_lines == 1
    assert view.status == "partial"


def test_the_current_event_is_not_a_batch_member(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="current", target="src/a.py")
    settle(root, event="current", target="src/a.py", content_sha256=file_sha(workspace, "src/a.py"))

    view = view_of(root, workspace, exclude_event_id="current")

    assert view.members == ()
    assert view.excluded["unsettled"] == ()


def test_a_target_from_a_read_only_tool_is_invalid(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    write_file(workspace, "src/a.py", "x = 1\n")
    propose(root, event="e1", target="src/a.py", tool="read")
    settle(root, event="e1", target="src/a.py", content_sha256=file_sha(workspace, "src/a.py"))

    view = view_of(root, workspace)

    assert view.members == ()
    assert view.invalid_lines == 1


def test_an_unreadable_ledger_raises_batch_ledger_error(tmp_root: Path) -> None:
    root = tmp_root / "ledger"
    workspace = tmp_root / "project"
    (root / f"{SESSION}.jsonl").mkdir(parents=True)

    with pytest.raises(BatchLedgerError):
        view_of(root, workspace)


def test_the_ledger_axis_is_1_1_and_supports_1_0(tmp_root: Path) -> None:
    from adapters.dsh.batch_ledger import SUPPORTED_BATCH_LEDGER_SCHEMA_VERSIONS

    assert BATCH_LEDGER_SCHEMA_VERSION == "1.1"
    assert SUPPORTED_BATCH_LEDGER_SCHEMA_VERSIONS == frozenset({"1.0", "1.1"})

"""`handle` 的契约：任何异常路径都返回阻断，绝不抛给解释器（第 52 条：理由也得对）。

`handle` 的 docstring 写着「任何异常路径都返回阻断，绝不抛给解释器」，`--capture` 的帮助也
写着「不影响判定」，但采集与 G11 留痕这两处写入此前跑在 `_handle_guarded` **之外**：采集目录
不可写、或审计/台账追加失败时，OSError 会一路逃出 `handle`，被 CLI 读成 `startup_error` ——
一次真实的 policy_block 于是被说成「Hook 起不来」（错误归因），而且这次事件的判定记录也丢了。

三条用例各自钉一个失败点：采集、留痕、判定本身的 I/O 失败。
"""

from __future__ import annotations

from conftest import dsh_event

from adapters.dsh.hooks import EXIT_BLOCK, DshPreExecuteHook, run_hook


def _payload(dsh_project):
    return dsh_event("pre-tool-use-edit-block.json", cwd=str(dsh_project))


def _run(dsh_config_path, dsh_project, tmp_root, **kwargs):
    return run_hook(
        _payload(dsh_project),
        config_path=dsh_config_path,
        audit_path=tmp_root / "audit.jsonl",
        **kwargs,
    )


def test_an_unwritable_capture_directory_does_not_replace_the_decision(
    dsh_config_path, dsh_project, tmp_root, capsys
) -> None:
    """采集写不了只喊一声：这次判定仍然是 policy_block，而不是 startup_error。"""

    # 采集目标是一个**文件**：mkdir(parents=True, exist_ok=True) 会抛 FileExistsError（OSError）
    capture_target = tmp_root / "capture-target.txt"
    capture_target.write_text("占位：它是个文件，不是目录" + chr(10), encoding="utf-8", newline="")

    outcome = _run(dsh_config_path, dsh_project, tmp_root, capture_dir=capture_target)

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "policy_block"
    assert "CAPTURE UNAVAILABLE" in capsys.readouterr().err


def test_a_failing_context_injection_ledger_does_not_replace_the_decision(
    dsh_config_path, dsh_project, tmp_root, capsys, monkeypatch
) -> None:
    """G11 留痕是旁注：写不进去不改判定。"""

    def boom(self, *, base_record, started):
        raise OSError("台账被锁住了（测试替身）")

    monkeypatch.setattr(DshPreExecuteHook, "_record_context_injection", boom)

    outcome = _run(dsh_config_path, dsh_project, tmp_root)

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "policy_block"
    assert "CONTEXT INJECTION LEDGER UNAVAILABLE" in capsys.readouterr().err


def test_an_unwritable_audit_fails_closed_with_the_right_reason(
    dsh_config_path, dsh_project, tmp_root
) -> None:
    """审计写不进去仍然失败关闭，但理由说的是「审计不可写」，不是「Hook 起不来」。

    审计目标是一个**目录**：追加一定失败（IsADirectoryError / PermissionError，都是 OSError）。
    `_fail` 自己也要写审计，所以它会在 except 处理器里再抛一次——那条路径由 handle 兜住，
    返回值仍然是退出码 2，但理由指对了对象（§52：拦住只是完成一半，另一半是理由正确）。
    """

    audit_target = tmp_root / "audit-is-a-directory"
    audit_target.mkdir()

    outcome = run_hook(
        _payload(dsh_project),
        config_path=dsh_config_path,
        audit_path=audit_target,
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "config_error"
    assert "审计与台账均不可写" in (outcome.stderr or "")

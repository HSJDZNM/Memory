"""本机 CI 编排器的解释器、模块搜索路径与排他锁回归测试。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_ci_local():
    spec = importlib.util.spec_from_file_location(
        "ci_local_under_test",
        REPO_ROOT / "tools" / "ci_local.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_repo(tmp_root: Path) -> Path:
    """一个真的 git 仓库：重命名与非 ASCII 路径的 porcelain 形态只有 git 说了算。"""

    import subprocess as _subprocess

    repo = tmp_root / "repo"
    repo.mkdir()

    def git(*arguments: str) -> None:
        _subprocess.run(
            ["git", *arguments], cwd=repo, capture_output=True, text=True,
            encoding="utf-8", check=True,
        )

    git("init", "-q")
    git("config", "user.email", "probe@example.invalid")
    git("config", "user.name", "probe")
    (repo / "移动我.md").write_text("x" + chr(10), encoding="utf-8", newline=chr(10))
    git("add", "-A")
    git("commit", "-qm", "init")
    (repo / "src").mkdir()
    git("mv", "移动我.md", "src/移动我.md")
    return repo


def test_a_rename_into_a_watched_prefix_is_seen_as_a_change(tmp_root, monkeypatch):
    """git mv 进 src/ 的条目在 porcelain 里是 old -> new：必须取新路径。

    旧实现直接取 line[3:]，拿到的是那串 old -> new，匹配不上任何前缀——按改动范围
    选步会静默少跑（CODE_STEPS 不选），而文件明明已经在 src/ 里。
    """

    ci_local = _load_ci_local()
    repo = _git_repo(tmp_root)
    monkeypatch.setattr(ci_local, "ROOT", repo)

    changed = ci_local._changed_paths()

    assert "src/移动我.md" in changed, changed
    assert all("->" not in item for item in changed), changed
    assert ci_local._touched(changed, ("src/",)) is True


def test_non_ascii_paths_are_not_c_quoted(tmp_root, monkeypatch):
    """中文 / 带空格的文件名必须原样读出：porcelain 默认会转义成八进制加引号。"""

    ci_local = _load_ci_local()
    repo = _git_repo(tmp_root)
    (repo / "新 文件.txt").write_text("z" + chr(10), encoding="utf-8", newline=chr(10))
    monkeypatch.setattr(ci_local, "ROOT", repo)

    changed = ci_local._changed_paths()

    assert "新 文件.txt" in changed, changed
    assert all(chr(34) not in item for item in changed), changed


def test_git_status_failure_is_fail_closed(tmp_root, monkeypatch):
    """读不到工作树状态时不许当成"没有改动"：门禁会按改动范围少跑步骤。"""

    import types

    ci_local = _load_ci_local()
    repo = _git_repo(tmp_root)
    monkeypatch.setattr(ci_local, "ROOT", repo)
    real_run = ci_local.subprocess.run

    def failing_status(command, **kwargs):
        if list(command[:2]) == ["git", "status"]:
            return types.SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a git repository")
        return real_run(command, **kwargs)

    monkeypatch.setattr(ci_local, "subprocess", types.SimpleNamespace(run=failing_status))

    with pytest.raises(ci_local.ChangedPathsUnavailable) as error:
        ci_local._changed_paths()

    assert "git status" in str(error.value)
    assert "128" in str(error.value)


def test_cli_list_fails_closed_when_git_cannot_read_the_worktree(tmp_root):
    """真实命令：git 读不到仓库时，--list 必须非 0 退出，而不是继续按"没有改动"选步。

    让 git 真的失败（GIT_DIR 指向不存在的位置，实测 exit 128、stdout 为空）——
    假 git 在 Windows 上挡不住真 git（CreateProcess 只按 .exe 找），所以用真实失败。
    """

    environment = dict(os.environ, GIT_DIR=str(tmp_root / "no-such-git-dir"))

    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "ci_local.py"), "--list"],
        cwd=REPO_ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", check=False,
    )

    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "改动文件" not in completed.stdout, "失败不许被报成 0 个改动"
    assert "git status" in completed.stderr

    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "ci_local.py"), "--list"],
        cwd=REPO_ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", check=False,
    )

    assert completed.returncode != 0, completed.stdout
    assert "改动文件" not in completed.stdout, "失败不许被报成 0 个改动"
    assert "git status" in completed.stderr


def test_python_override_runs_modules_from_repo_src_and_preserves_environment(
    monkeypatch,
    tmp_root,
):
    ci_local = _load_ci_local()
    source_dir = tmp_root / "src"
    source_dir.mkdir()
    (source_dir / "ci_local_probe.py").write_text(
        "import os\n"
        "if os.environ.get('CI_LOCAL_SENTINEL') != 'kept':\n"
        "    raise RuntimeError('parent environment was not preserved')\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    monkeypatch.setattr(
        ci_local,
        "_steps",
        lambda: [("Module import probe", '.venv/bin/python -c "import ci_local_probe"')],
    )
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])
    # 这条用例验的是解释器覆盖，用的是合成的步骤名；登记门禁另有专门用例，这里显式让开。
    monkeypatch.setattr(ci_local, "unregistered_steps", lambda: [])
    monkeypatch.setenv("CI_LOCAL_SENTINEL", "kept")
    monkeypatch.setenv("PYTHONPATH", str(tmp_root / "wrong-source"))

    assert ci_local.main(["--full", "--python", sys.executable]) == 0


def test_every_runnable_workflow_step_is_registered_or_exempt():
    """workflow 里每个有 run 块的步骤都必须有归属。

    没登记进分组、也不在 NOT_RUN_ON_HOST 里的步骤，在按改动范围选择时
    **既不执行、也不报告跳过**——本仓库正是这样漏跑过真实检查。
    """

    ci_local = _load_ci_local()
    assert ci_local.unregistered_steps() == []


def test_previously_missing_steps_now_have_a_group():
    """曾经无人认领的 4 个真实步骤必须能匹配到某个已登记分组。"""

    ci_local = _load_ci_local()
    prefixes = ci_local.registered_prefixes()
    for name in (
        "Real dsh sandbox loop (skipped without dsh)",
        "Retrieval index is idempotent",
        "Retrieval refuses to answer without sources",
        "Enforcement refuses unknown parameters",
    ):
        assert any(name.startswith(prefix) for prefix in prefixes), name


def test_unregistered_step_fails_closed(monkeypatch, capsys):
    """认不出来的步骤名必须让门禁变红，而不是被静默丢掉。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(
        ci_local,
        "_steps",
        lambda: [("Some brand new CI step", '.venv/bin/python -c "pass"')],
    )
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])

    assert ci_local.main(["--list"]) == 1
    assert "Some brand new CI step" in capsys.readouterr().err


def test_exempt_steps_are_reported_instead_of_dropped(monkeypatch, capsys):
    """登记豁免的步骤要出现在清单里（带原因），不能凭空消失。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(
        ci_local,
        "_steps",
        lambda: [("Install pinned dependencies", "uv venv")],
    )
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])

    assert ci_local.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "已登记豁免" in out
    assert "Install pinned dependencies" in out

# --------------------------------------------------------------------------- 排他锁
#
# ci_local.py 与它调起的工具共用 .tmp/ 下的固定路径状态（phase-8-orchestration / artifacts /
# retrieval），两个实例同时跑会互相拆台、跑出假红。锁的契约是"第二个实例立刻失败退出、一步都不
# 执行"，下面逐条守住它。同进程内换一个文件描述符再取同一把锁，在 Windows（LockFile 是强制锁）
# 和 POSIX（flock 认的是 open file description）上都会冲突，所以"被别人占着"能在单进程里确定性地
# 模拟出来。


def _load_locked_ci_local(monkeypatch, tmp_root, counter: list[str]):
    """加载模块、把 ROOT 指到临时目录，并让规划走一个会计数的 `_steps`。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)

    def counting_steps():
        counter.append("_steps")
        return [("Module import probe", '.venv/bin/python -c "print(1)"')]

    monkeypatch.setattr(ci_local, "_steps", counting_steps)
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])
    monkeypatch.setattr(ci_local, "unregistered_steps", lambda: [])
    return ci_local


def test_held_lock_fails_closed_and_runs_no_step(monkeypatch, capsys, tmp_root):
    """持锁时第二个实例退出 1、报出锁路径与持锁者 pid，且一条步骤都不跑。"""

    counter: list[str] = []
    ci_local = _load_locked_ci_local(monkeypatch, tmp_root, counter)
    # 故意用一个不属于本进程的 pid：只有真的从锁文件开头读元数据的实例才可能报出它。
    holder = ci_local.try_acquire_lock(
        {"pid": 424242, "started_at": "2026-01-01T09:30:00+08:00", "argv": "probe --full"}
    )
    assert holder is not None
    try:
        assert ci_local.main(["--full", "--python", sys.executable]) == 1
        err = capsys.readouterr().err
        assert str(ci_local.lock_path()) in err
        assert "pid=424242" in err
        assert "2026-01-01T09:30:00+08:00" in err
        assert "等它跑完再跑，不要并发" in err

        # --hook 模式（pre-push 钩子）必须写明"阻断推送"。
        assert ci_local.main(["--hook", "--python", sys.executable]) == 1
        assert "阻断推送" in capsys.readouterr().err
    finally:
        holder.release()

    assert counter == []  # 一步都没跑：连规划都没有发生


def test_list_is_not_blocked_by_a_held_lock(monkeypatch, capsys, tmp_root):
    """`--list` 不取锁、也不写 .tmp：别的实例跑着时它照样返回 0。"""

    counter: list[str] = []
    ci_local = _load_locked_ci_local(monkeypatch, tmp_root, counter)

    assert ci_local.main(["--list"]) == 0
    assert not (tmp_root / ".tmp").exists()  # 只列清单：不建 .tmp、不建锁文件
    capsys.readouterr()

    holder = ci_local.try_acquire_lock({"pid": 424242, "started_at": "now", "argv": "holder"})
    assert holder is not None
    try:
        assert ci_local.main(["--list"]) == 0
    finally:
        holder.release()

    out = capsys.readouterr().out
    assert "本次会跑" in out
    assert "Module import probe" in out  # 清单来自被 monkeypatch 的 _steps


def test_lock_can_be_acquired_again_after_release(monkeypatch, tmp_root):
    """获取 → 释放 → 再获取，两次都成功；同时持有时第二次必须拿不到。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)

    first = ci_local.try_acquire_lock({"pid": os.getpid(), "started_at": "now", "argv": "first"})
    assert first is not None
    duplicate = ci_local.try_acquire_lock({"pid": os.getpid(), "started_at": "now", "argv": "dup"})
    assert duplicate is None

    first.release()
    first.release()  # 重复释放是空操作

    second = ci_local.try_acquire_lock({"pid": os.getpid(), "started_at": "now", "argv": "second"})
    assert second is not None
    second.release()


def test_lock_path_follows_root_and_metadata_is_readable(monkeypatch, tmp_root):
    """锁文件跟着 monkeypatch 后的 ROOT 走；元数据写在开头，别的实例读得到。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    lock_file = tmp_root / ".tmp" / "ci-local.lock"
    assert ci_local.lock_path() == lock_file

    holder = ci_local.try_acquire_lock(
        {"pid": 424242, "started_at": "2026-01-01T00:00:00+08:00", "argv": "probe"}
    )
    assert holder is not None
    assert lock_file.is_file()
    # 锁字节远离元数据：Windows 的强制锁会让被锁区间**读不到**，两者重叠就报不出持锁者 pid。
    assert ci_local.LOCK_OFFSET >= 4096
    assert ci_local.read_lock_metadata() == {
        "pid": 424242,
        "started_at": "2026-01-01T00:00:00+08:00",
        "argv": "probe",
    }
    holder.release()
    assert lock_file.read_bytes() == b""  # 释放后既不留锁、也不留元数据


def test_lock_is_released_on_every_exit_path(monkeypatch, tmp_root):
    """正常结束与步骤失败（提前 return）都必须把锁还回来：释放后立刻能再取。"""

    counter: list[str] = []
    ci_local = _load_locked_ci_local(monkeypatch, tmp_root, counter)

    def assert_free():
        handle = ci_local.try_acquire_lock(
            {"pid": os.getpid(), "started_at": "now", "argv": "after"}
        )
        assert handle is not None  # 上一步没有把锁留下
        handle.release()

    assert ci_local.main(["--python", sys.executable]) == 0  # 正常路径
    assert_free()

    def failing_steps():
        counter.append("_steps")
        return [("Module import probe", '.venv/bin/python -c "raise SystemExit(3)"')]

    monkeypatch.setattr(ci_local, "_steps", failing_steps)
    assert ci_local.main(["--python", sys.executable]) == 1  # 步骤失败 -> 提前 return 1
    assert_free()

# --------------------------------------------------------------------------- 耗时可见性
#
# 门禁是串行的：墙钟时间 = 各步之和，所以“为什么跑了二十分钟”是一个可直接测量的量。
# 下面守住两件事：非钩子模式**总是**打印汇总表（红了也要打印），--timings 才写 JSON；
# 钩子模式保持安静（它成功时不打印任何东西是既有契约）。


def test_timings_are_printed_by_default_and_written_on_request(monkeypatch, capsys, tmp_root):
    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    entries = [
        ("Slow step", "python slow.py", 3.5, 0),
        ("Quick step", "python quick.py", 0.25, 1),
    ]

    output = ci_local.report_timings(entries, changed=2, hook=False, write_json=True)

    printed = capsys.readouterr().out
    assert "执行耗时" in printed
    # 按耗时降序：最贵的那步在最上面，读的人不必自己排。
    assert printed.index("Slow step") < printed.index("Quick step")
    assert output is not None and output.is_file()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["changed_files"] == 2
    assert [item["name"] for item in payload["entries"]] == ["Slow step", "Quick step"]
    assert payload["entries"][1]["returncode"] == 1
    assert payload["total_seconds"] == 3.75


def test_hook_mode_stays_quiet_and_writes_nothing(monkeypatch, capsys, tmp_root):
    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    entries = [("Slow step", "python slow.py", 3.5, 0)]

    assert ci_local.report_timings(entries, changed=0, hook=True, write_json=False) is None
    assert capsys.readouterr().out == ""
    assert not (tmp_root / ".tmp" / "ci-local-timings.json").exists()


def test_timings_summary_survives_a_red_run(monkeypatch, capsys, tmp_root):
    """步骤失败时也要打印耗时：卡在哪一步与哪一步最贵，是同一个问题的两面。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    monkeypatch.setattr(
        ci_local,
        "_steps",
        lambda: [("Module import probe", '.venv/bin/python -c "raise SystemExit(3)"')],
    )
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])
    monkeypatch.setattr(ci_local, "unregistered_steps", lambda: [])

    assert ci_local.main(["--full", "--python", sys.executable]) == 1
    printed = capsys.readouterr().out
    assert "执行耗时" in printed
    assert "Module import probe" in printed


# --------------------------------------------------------------------------- 推迟到 --full
#
# 昂贵、又只守"文档与实现同步"的步骤可以只在本机 --full 下执行：默认 / --hook 被改动选中时
# 必须**点名跳过并写明原因**，不能静默消失；--full 下必须真的进执行计划；而且推迟表里的名字
# 必须对得上 workflow（见 test_every_full_only_step_exists_in_the_workflow），否则推迟会悄悄失效。
# GitHub CI 不受影响（它不经过 ci_local）。
#
# 学习手册下线后 FULL_ONLY_STEPS 是**空表**，机制与下面三个用例都保留：空表是当前状态，
# 不是"没有这个能力"。用合成步骤名 + 合成推迟表把机制本身钉住——**空集合不算覆盖**。

# 名字必须以某个**已登记分组**里的步骤名为前缀，否则它连"被改动范围选中"这一步都进不了
# （_plan_steps 先按 wanted 前缀筛，再看推迟表）——那样用例就退化成"测了个没被选中的步骤"。
DEFERRED_STEP = "Tech-detail notebooks are in sync (synthetic deferral)"
DEFERRED_REASON = "推迟到 --full：合成步骤（只用于覆盖推迟机制）"


def _deferred_plan(monkeypatch, full: bool):
    ci_local = _load_ci_local()
    monkeypatch.setattr(
        ci_local,
        "_steps",
        lambda: [(DEFERRED_STEP, ".venv/bin/python tools/check_notebook.py a.ipynb")],
    )
    monkeypatch.setattr(ci_local, "FULL_ONLY_STEPS", {DEFERRED_STEP: DEFERRED_REASON})
    # 模拟"改了 src/"：手册组被改动范围选中
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: ["src/policy/engine.py"])
    return ci_local, ci_local._plan_steps(full)


def test_deferred_step_is_skipped_by_default_and_named_with_a_reason(monkeypatch):
    _ci_local, (plan, skipped, _not_run) = _deferred_plan(monkeypatch, full=False)

    assert DEFERRED_STEP not in [name for name, _ in plan]
    reasons = dict(skipped)
    assert DEFERRED_STEP in reasons
    assert "--full" in reasons[DEFERRED_STEP]


def test_deferred_step_runs_under_full(monkeypatch):
    _ci_local, (plan, skipped, _not_run) = _deferred_plan(monkeypatch, full=True)

    assert DEFERRED_STEP in [name for name, _ in plan]
    assert DEFERRED_STEP not in dict(skipped)


def test_deferred_step_is_listed_as_not_run(monkeypatch, capsys):
    ci_local, _ = _deferred_plan(monkeypatch, full=False)
    monkeypatch.setattr(ci_local, "unregistered_steps", lambda: [])

    assert ci_local.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert DEFERRED_STEP in out.split("本机跳过")[1]


def test_every_full_only_step_exists_in_the_workflow():
    """推迟表里的名字必须对得上 workflow。

    改了步骤名而这里没跟上，推迟会悄悄失效（反而每次都跑）。

    注意它**守不住什么**：FULL_ONLY_STEPS 为空表时本用例一个名字也检查不到（学习手册下线后
    就是这种状态）。机制本身由上面三个合成用例覆盖，本用例只负责"填了表就必须对得上"。
    """

    ci_local = _load_ci_local()
    names = [name for name, _ in ci_local._steps()]
    for prefix in ci_local.FULL_ONLY_STEPS:
        assert any(name.startswith(prefix) for name in names), prefix


# --------------------------------------------------------------------------- 控制台输出
#
# 默认把步骤输出写进 .tmp/ci-local-logs/，控制台每步一行；失败打日志尾部；--verbose 原样直连。
# 守住的不变量：判定只看退出码（输出去向不改变结论）；失败时的原因不会被藏起来；
# 钩子成功时除开头一行"运行中"外不打印任何东西。

NOISY_STEP = (
    "Noisy step",
    '.venv/bin/python -c "import sys; [print(i) for i in range(500)]; '
    "print('arrow \\u21c4'); sys.stderr.write('to-stderr' + chr(10))\"",
)
FAILING_STEP = (
    "Failing step",
    '.venv/bin/python -c "import sys; print(\'before-fail\'); '
    "sys.stderr.write('boom-reason' + chr(10)); raise SystemExit(3)\"",
)


def _load_quiet_ci_local(monkeypatch, tmp_root, steps):
    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    monkeypatch.setattr(ci_local, "_steps", lambda: list(steps))
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])
    monkeypatch.setattr(ci_local, "unregistered_steps", lambda: [])
    # 这组用例只验控制台输出的形态：真实的只报告步骤（义务门禁 / 豁免到期）会在单测里真跑、
    # 多写日志，与这里无关；它们与精简输出的配合由 test_ci_local_report_only.py 单独钉住。
    monkeypatch.setattr(ci_local, "REPORT_ONLY_STEPS", ())
    return ci_local


def test_default_mode_prints_one_line_per_step_and_keeps_the_full_output_in_a_log(
    monkeypatch, capfd, tmp_root
):
    ci_local = _load_quiet_ci_local(monkeypatch, tmp_root, [NOISY_STEP])

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    out, _err = capfd.readouterr()
    assert "[ 1/1] Noisy step ... ok" in out
    assert "499" not in out  # 步骤自己的 500 行输出没有进控制台
    logs = sorted((tmp_root / ".tmp" / "ci-local-logs").glob("*.log"))
    assert [item.name for item in logs] == ["01-noisy-step.log"]
    text = logs[0].read_text(encoding="utf-8")
    assert "499" in text and "to-stderr" in text  # stdout 与 stderr 都在日志里
    assert "arrow ⇄" in text  # GBK 以外的字符按 UTF-8 写进日志，不会让步骤假红
    assert text.startswith("$ ")  # 日志开头记着实际执行的命令


def test_a_failing_step_shows_its_log_tail_and_still_exits_1(monkeypatch, capfd, tmp_root):
    ci_local = _load_quiet_ci_local(monkeypatch, tmp_root, [FAILING_STEP])

    assert ci_local.main(["--full", "--python", sys.executable]) == 1
    out, err = capfd.readouterr()
    assert "Failing step ... FAIL rc=3" in out
    assert "boom-reason" in out and "before-fail" in out  # 失败原因不藏在日志文件里
    assert "日志最后" in out and "ci-local-logs/01-failing-step.log" in out
    assert "Failing step -> 退出码 3" in err


def test_verbose_streams_step_output_to_the_console_and_writes_no_log(
    monkeypatch, capfd, tmp_root
):
    ci_local = _load_quiet_ci_local(monkeypatch, tmp_root, [NOISY_STEP])

    assert ci_local.main(["--full", "--verbose", "--python", sys.executable]) == 0
    out, err = capfd.readouterr()
    assert "=== Noisy step ===" in out and "499" in out
    assert "to-stderr" in err
    assert not (tmp_root / ".tmp" / "ci-local-logs").exists()


def test_hook_mode_is_quiet_on_success_and_loud_on_failure(monkeypatch, capfd, tmp_root):
    ci_local = _load_quiet_ci_local(monkeypatch, tmp_root, [NOISY_STEP])
    assert ci_local.main(["--hook", "--python", sys.executable]) == 0
    out, err = capfd.readouterr()
    assert out == ""
    assert err.count(chr(10)) == 1 and "运行中" in err  # 只有开头那一行

    monkeypatch.setattr(ci_local, "_steps", lambda: [FAILING_STEP])
    assert ci_local.main(["--hook", "--python", sys.executable]) == 1
    out, err = capfd.readouterr()
    assert out == ""
    assert "boom-reason" in err and "阻断推送" in err


def test_each_run_starts_with_an_empty_log_directory(monkeypatch, capfd, tmp_root):
    """旧日志不能留到下一次：否则读到的"失败原因"可能是上一次的。"""

    stale = tmp_root / ".tmp" / "ci-local-logs" / "07-from-last-run.log"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    ci_local = _load_quiet_ci_local(monkeypatch, tmp_root, [NOISY_STEP])

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    capfd.readouterr()
    assert not stale.exists()


def test_timing_summary_can_be_limited_to_the_slowest_steps(monkeypatch, capsys, tmp_root):
    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    entries = [("Step %d" % index, "cmd", float(index), 0) for index in range(1, 9)]

    ci_local.report_timings(entries, changed=0, hook=False, write_json=True, top=3)
    printed = capsys.readouterr().out
    assert "最慢 3 步" in printed
    assert "Step 8" in printed and "Step 6" in printed and "Step 5" not in printed
    payload = json.loads((tmp_root / ".tmp" / "ci-local-timings.json").read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 8  # JSON 始终是全量

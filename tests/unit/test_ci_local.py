"""本机 CI 编排器的解释器、模块搜索路径与排他锁回归测试。"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


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

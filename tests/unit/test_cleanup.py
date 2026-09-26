"""`tools/cleanup.py` 与门禁共用同一把排他锁的回归测试。

背景：cleanup 删的正是 ci_local 正在用的共享状态（`.tmp/phase-8-orchestration/`、
`.tmp/artifacts/`、`.tmp/retrieval/`）。一边跑门禁一边清 `.tmp/`，清理会先把状态删光、门禁随之
报出假红，而清理自己也会在锁文件上失败（Windows 实测 WinError 32）。契约因此是
“真要删就先取同一把锁，抢不到就一项都不删”，并且锁文件本身永远不是删除候选。

不变式是**要么持锁，要么完全不碰 `.tmp/`**，因此判定与删除必须同源：清理只**扫一次**，由同一次
扫描决定要不要上锁，并且只删这次扫描到的东西。文件末尾的用例把“`.tmp/` 在清理观察它的过程中出现”
这个 TOCTOU 交错注入回来——旧实现（判定问 tmp_dir().is_dir()、删除集由 _clean() 重新扫描）
会 FAIL，严闭后的实现 PASS。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_cleanup():
    spec = importlib.util.spec_from_file_location(
        "cleanup_under_test",
        REPO_ROOT / "tools" / "cleanup.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_cleanup_with_tmp_root(monkeypatch, tmp_root):
    """加载 cleanup，并把它**和它导入的那个 ci_local** 都指到同一个临时 ROOT。

    两处都必须指：`cleanup.REPO_ROOT` 决定删什么，`ci_local.ROOT` 决定锁落在哪；少指一处就会在
    真实仓库的 `.tmp/` 上加锁（甚至删到真实路径），测试之间互相干扰。
    用 `cleanup.ci_local` 而不是另加载一份 ci_local 是关键：另加载的那份 ROOT 没被指过来，
    它取的锁会落进真实仓库。
    """

    cleanup = _load_cleanup()
    monkeypatch.setattr(cleanup, "REPO_ROOT", tmp_root)
    monkeypatch.setattr(cleanup.ci_local, "ROOT", tmp_root)
    assert cleanup.ci_local.lock_path() == tmp_root / ".tmp" / "ci-local.lock"
    return cleanup


def _make_candidate(tmp_root: Path, name: str) -> Path:
    """在临时 ROOT 的 `.tmp/` 下造一个候选子项（里面放一个文件）。"""

    directory = tmp_root / ".tmp" / name
    directory.mkdir(parents=True)
    (directory / "state.json").write_text("{}", encoding="utf-8")
    return directory


def test_held_lock_refuses_cleanup_and_deletes_nothing(monkeypatch, capsys, tmp_root):
    """持锁时清理退出 1、报出锁路径与持锁者 pid/起始时间/argv，且候选一项都没删。"""

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    candidate = _make_candidate(tmp_root, "phase-8-orchestration")

    # 故意用一个不属于本进程的 pid：只有真的从锁文件开头读元数据的实例才可能报出它。
    holder = cleanup.ci_local.try_acquire_lock(
        {"pid": 424242, "started_at": "2026-01-01T09:30:00+08:00", "argv": "probe --full"}
    )
    assert holder is not None
    try:
        assert cleanup.main([]) == 1
        err = capsys.readouterr().err
        assert str(cleanup.ci_local.lock_path()) in err
        assert "pid=424242" in err
        assert "2026-01-01T09:30:00+08:00" in err
        assert "argv: probe --full" in err
        assert "等它跑完再清" in err
    finally:
        holder.release()

    assert candidate.is_dir()  # 一项都没删
    assert (candidate / "state.json").is_file()


def test_dry_run_is_not_blocked_by_a_held_lock(monkeypatch, capsys, tmp_root):
    """`--dry-run` 只读：不取锁、不建锁文件，别的实例跑着门禁时照样返回 0。"""

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    candidate = _make_candidate(tmp_root, "phase-8-orchestration")
    lock_file = cleanup.ci_local.lock_path()

    # 没人持锁时它也不该上锁：只读清单一读完，锁文件就不该被造出来。
    assert cleanup.main(["--dry-run"]) == 0
    assert not lock_file.exists()
    assert "将删除: .tmp/phase-8-orchestration" in capsys.readouterr().out

    holder = cleanup.ci_local.try_acquire_lock({"pid": 424242, "started_at": "now", "argv": "h"})
    assert holder is not None
    try:
        assert cleanup.main(["--dry-run"]) == 0
        assert "将删除: .tmp/phase-8-orchestration" in capsys.readouterr().out
    finally:
        holder.release()

    assert candidate.is_dir()  # dry-run 什么都没删
    assert (candidate / "state.json").is_file()


def test_cleanup_removes_tmp_children_but_never_the_lock_file(monkeypatch, capsys, tmp_root):
    """不持锁时正常清理：`.tmp/` 的子项被删掉，而锁文件仍然存在。"""

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    artifacts = _make_candidate(tmp_root, "artifacts")
    orchestration = _make_candidate(tmp_root, "phase-8-orchestration")
    lock_file = cleanup.ci_local.lock_path()

    assert cleanup.main([]) == 0
    out = capsys.readouterr().out

    assert not artifacts.exists()
    assert not orchestration.exists()
    assert "已删除: .tmp/artifacts" in out
    assert "已删除: .tmp/phase-8-orchestration" in out

    # 锁文件**从不**是删除候选：整体 rmtree(.tmp) 会让 Windows 上的清理与持锁互相打架，
    # 在 POSIX 上则等于把锁换成了另一把（flock 认的是 inode）。
    assert "ci-local.lock" not in out
    assert lock_file.is_file()
    assert (tmp_root / ".tmp").is_dir()  # 目录本身也留着：锁住在里面
    assert lock_file.read_bytes() == b""  # 释放后既不留锁、也不留元数据


def test_missing_tmp_is_not_created_and_needs_no_lock(monkeypatch, capsys, tmp_root):
    """`.tmp/` 不存在时不取锁、也不把它造出来；其余缓存照常清理。"""

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    cache = tmp_root / "__pycache__"
    cache.mkdir()
    (cache / "module.pyc").write_bytes(b"")

    assert cleanup.main([]) == 0
    out = capsys.readouterr().out

    assert "已删除: __pycache__" in out
    assert not (tmp_root / ".tmp").exists()  # 为了上锁凭空造出 .tmp/ 是本末倒置
    assert not cleanup.ci_local.lock_path().exists()


def test_loose_cache_files_are_deleted_not_silently_skipped(monkeypatch, capsys, tmp_root):
    """白名单对 `*.pyc / *.pyo` 的承诺必须真的兑现，而不是只删 `__pycache__` 目录。

    `is_allowed()` 曾经在 `return path.is_file() and path.suffix in CACHE_FILE_SUFFIXES` 之前就
    `return False`（不可达代码），于是散落的 `.pyc` 会被扫进计划、又被判成「不在白名单」——
    清理看起来跑过（退出码 0），实际什么都没收走，报告却会把 `.tmp/` 说成干净。这条用例把
    「候选被自己扫出来、又被白名单拒绝」钉成失败：只要它成立，`--dry-run` 的清单就不可信。
    """

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    loose_pyc = tmp_root / "generated.pyc"
    loose_pyc.write_bytes(b"")
    loose_pyo = tmp_root / "legacy.pyo"
    loose_pyo.write_bytes(b"")
    kept = tmp_root / "notes.txt"
    kept.write_text("keep me", encoding="utf-8")

    assert cleanup.main([]) == 0
    out = capsys.readouterr().out

    assert "已删除: generated.pyc" in out
    assert "已删除: legacy.pyo" in out
    assert "跳过（不在白名单）" not in out  # 扫描出来的候选不该被白名单反过来拒绝
    assert not loose_pyc.exists()
    assert not loose_pyo.exists()
    assert kept.read_text(encoding="utf-8") == "keep me"  # 白名单照旧不碰非缓存文件


def test_lock_is_held_during_deletion_and_released_afterwards(monkeypatch, capsys, tmp_root):
    """删除发生在持锁期间；清理跑完能立刻再取到锁（finally 不放锁会挡住后续门禁）。"""

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    _make_candidate(tmp_root, "retrieval")
    lock_file = cleanup.ci_local.lock_path()
    held_during_removal: list[bool] = []
    real_remove = cleanup._remove

    def probing_remove(path: Path):
        probe = cleanup.ci_local.try_acquire_lock({"pid": 1, "started_at": "now", "argv": "p"})
        held_during_removal.append(probe is None)
        assert path != lock_file  # 锁文件不是删除目标
        return real_remove(path)

    monkeypatch.setattr(cleanup, "_remove", probing_remove)

    assert cleanup.main([]) == 0
    capsys.readouterr()

    assert held_during_removal == [True]  # 删除那一刻锁正被本进程持有：删与跑真的互斥
    assert lock_file.is_file()

    again = cleanup.ci_local.try_acquire_lock({"pid": 2, "started_at": "now", "argv": "after"})
    assert again is not None  # 没有“没人持有却拿不到”的残留
    again.release()


def test_every_candidate_passes_the_whitelist(monkeypatch, tmp_root):
    """不变式：`candidates()` 扫出来的每一项都必须能过 `is_allowed()`。

    两边不一致**不会抛错**，只会让清理静默跳过、还返回 0——与上面那条 bug 同一失败形态。
    所以在两个层面钉住它：

    - 按形状逐条断言（与平台无关）：`FOO.PYC`、`NESTED.PYO` 会被 Windows 上
      大小写不敏感的 `rglob("*.pyc")` 扫进来，而 `Path.suffix in (...)` 的比较区分大小写；
      文件名恰为 `.pyc` 时 `Path(".pyc").suffix == ""`。两者都曾漏进「扫出来却被拒」。
    - 对 `candidates()` 的真实产物断言：计划里不能有任何过不了白名单的项（跨平台都成立）。
    """

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)

    for name in ("generated.pyc", "legacy.pyo", "UPPER.PYC", ".pyc"):
        loose = tmp_root / name
        loose.write_bytes(b"")
        assert cleanup.is_allowed(loose), name
    deep = tmp_root / "a" / "b"
    deep.mkdir(parents=True)
    nested = deep / "NESTED.PYO"
    nested.write_bytes(b"")
    assert cleanup.is_allowed(nested)

    plan = cleanup.candidates()
    assert plan, "计划不能为空，否则这条不变式什么都没测"
    rejected = [str(item) for item in plan if not cleanup.is_allowed(item)]
    assert rejected == []

# --------------------------------------------------------------------------- TOCTOU 不变式
#
# 不变式：**要么持锁，要么完全不碰 `.tmp/`**。旧实现把判定（`tmp_dir().is_dir()`）与删除集
# （`_clean()` 里重新调 `candidates()`）拆成两次观察，中间那条窗口里出现的 `.tmp/` 就会被**无锁**
# 删光——对抗复核实测：exit=0、try_acquire_lock 调用 0 次、`.tmp/artifacts` 与
# `.tmp/phase-8-orchestration` 被删、锁文件从未创建。下面两条用例把这个交错注入回来：
# 旧实现 FAIL，严闭后的实现 PASS。


def _install_appearing_tmp(monkeypatch, cleanup, tmp_root, names, *, before_scan):
    """注入“`.tmp/` 在清理观察它的过程中出现”的交错，返回清理的观察时序。

    闸门是**第一次观察**：`tmp_dir()` 与 `candidates()` 谁先被调用，谁就是当前实现的判定点。
    这第一次观察本身看不到 `.tmp/`，闸门一放行就把它和子项造出来——旧实现的判定正是
    `tmp_dir().is_dir()`，而它的删除扫描发生在更后面，于是它会在无锁状态下看到并删掉子项。

    - `before_scan=False`：子项在**扫描之后**出现（复核者复现的那条窗口）。严闭后的实现只删这次
      扫描到的东西，所以一个 `.tmp/` 子项都不该被碰。
    - `before_scan=True`：子项在**扫描之前**出现。严闭后的实现必须据此走取锁路径。
    """

    real_tmp_dir = cleanup.tmp_dir
    real_candidates = cleanup.candidates
    real_tmp = tmp_root / ".tmp"
    assert not real_tmp.exists()
    timeline: list[str] = []

    def materialise() -> None:
        """“别人”在窗口里把 `.tmp/` 及其子项造出来（放一个状态文件，好断言它是否还在）。"""

        for name in names:
            directory = real_tmp / name
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "state.json").write_text("{}", encoding="utf-8")

    def mark(source: str) -> bool:
        """记下第一次观察；返回 True 表示正是这一次（此刻 `.tmp/` 仍是不存在的）。"""

        if timeline:
            return False
        timeline.append(source)
        materialise()
        return True

    def racing_tmp_dir():
        # 旧实现拿这一次调用做取锁判定：必须让它看到“不存在”，否则注入的就不是同一段窗口。
        if mark("tmp_dir"):
            return tmp_root / ".tmp-not-yet"
        return real_tmp_dir()

    def racing_candidates(*, include_venv: bool = False):
        """替身必须收下 `include_venv`：`main()` 是这个签名调它的（口径变了就一起变）。"""

        if before_scan:
            materialise()  # 扫描之前它就出现了：这份计划必须把 `.tmp/` 算进去
            mark("candidates")
            return real_candidates(include_venv=include_venv)
        plan = real_candidates(include_venv=include_venv)  # 扫描时 `.tmp/` 还不存在
        mark("candidates")  # 扫描一结束它才出现——要注入的窗口正是这里
        return plan

    monkeypatch.setattr(cleanup, "tmp_dir", racing_tmp_dir)
    monkeypatch.setattr(cleanup, "candidates", racing_candidates)
    return timeline


def _probe_lock_and_removals(monkeypatch, cleanup, *, busy):
    """记录取锁次数，以及**每次删除发生时锁是否真的被本进程持有**。

    `busy=True` 模拟“门禁正在跑”：要注入的交错要求 `.tmp/` 起初并不存在，而真的提前把锁拿在手里
    会顺手把 `.tmp/` 建出来（那恰好抵消掉要注入的窗口），所以这里让取锁返回 None。
    """

    state: dict[str, Any] = {"acquire_calls": 0, "held": False, "removals": []}
    real_acquire = cleanup.ci_local.try_acquire_lock
    real_remove = cleanup._remove

    def probing_acquire(metadata=None):
        state["acquire_calls"] += 1
        if busy:
            return None
        handle = real_acquire(metadata)
        if handle is not None:
            state["held"] = True
        return handle

    def probing_remove(path):
        state["removals"].append((path, state["held"]))
        return real_remove(path)

    monkeypatch.setattr(cleanup.ci_local, "try_acquire_lock", probing_acquire)
    monkeypatch.setattr(cleanup, "_remove", probing_remove)
    return state


def _removals_without_lock(state, tmp_root):
    """没持锁就被删掉的 `.tmp/` 路径：不变式要求这里必须是空的。"""

    root = tmp_root / ".tmp"
    return [
        path
        for path, held in state["removals"]
        if not held and (path == root or root in path.parents)
    ]


def test_tmp_appearing_after_the_only_scan_is_not_touched(monkeypatch, capsys, tmp_root):
    """复核者复现的无锁路径：`.tmp/` 在扫描之后出现，这次清理一个子项都不该碰。

    旧实现会在这里退出 0、**一次锁都没取**，却把 `.tmp/artifacts` 与 `.tmp/phase-8-orchestration`
    删掉；严闭后的实现只删这次扫描到的东西，所以这两项都还在。
    """

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    cache = tmp_root / "__pycache__"
    cache.mkdir()
    (cache / "module.pyc").write_bytes(b"")
    timeline = _install_appearing_tmp(
        monkeypatch,
        cleanup,
        tmp_root,
        ("artifacts", "phase-8-orchestration"),
        before_scan=False,
    )
    state = _probe_lock_and_removals(monkeypatch, cleanup, busy=False)

    assert cleanup.main([]) == 0
    out = capsys.readouterr().out

    # 清理确实干了活：否则“没删 .tmp/”也可能只是因为它什么都没做
    assert "已删除: __pycache__" in out
    assert not cache.exists()
    # 但这份计划里没有 `.tmp/`：整份都不该被碰
    for name in ("artifacts", "phase-8-orchestration"):
        assert (tmp_root / ".tmp" / name / "state.json").is_file()
    assert _removals_without_lock(state, tmp_root) == []
    # 没扫到就没有要保护的共享状态：不为它上锁、也不建锁文件
    assert state["acquire_calls"] == 0
    assert not cleanup.ci_local.lock_path().exists()
    assert ".tmp" not in out
    assert timeline == ["candidates"]  # 严闭后只有“扫描”这一次观察，判定就来自它


def test_tmp_appearing_before_the_scan_takes_the_lock_and_refuses_when_busy(
    monkeypatch, capsys, tmp_root
):
    """`.tmp/` 在扫描之前出现 ⇒ 必须走取锁路径；抢不到就退出 1、一项都不删。"""

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    _install_appearing_tmp(monkeypatch, cleanup, tmp_root, ("artifacts",), before_scan=True)
    state = _probe_lock_and_removals(monkeypatch, cleanup, busy=True)

    assert cleanup.main([]) == 1
    err = capsys.readouterr().err

    assert state["acquire_calls"] == 1  # 先问锁，再谈删
    assert str(cleanup.ci_local.lock_path()) in err
    assert (tmp_root / ".tmp" / "artifacts" / "state.json").is_file()
    assert state["removals"] == []  # 一项都不删
    assert _removals_without_lock(state, tmp_root) == []


def test_candidate_inside_tmp_alone_also_requires_the_lock(monkeypatch, capsys, tmp_root):
    """计划里只有 `.tmp/` 的后代时同样必须取锁（第二条同族窗口的守卫）。

    `candidates()` 先判定顶层 `.tmp/` 是否存在、再用 `rglob` 走树；`.tmp/` 若在这两次观察之间出现，
    计划里就可能有 `.tmp/<x>/__pycache__` 而**没有** `.tmp/` 本身（去重只对“祖先也在计划里”的后代
    生效）。删掉落在 `.tmp/` 里的任何东西都属于碰共享状态，所以判定按“是否落在 `.tmp/` 里”算。
    """

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    leaked = tmp_root / ".tmp" / "leaked" / "__pycache__"
    leaked.mkdir(parents=True)
    (leaked / "module.pyc").write_bytes(b"")
    assert cleanup._touches_tmp(leaked)
    assert cleanup._touches_tmp(tmp_root / ".tmp")
    assert not cleanup._touches_tmp(tmp_root / "build" / "__pycache__")

    monkeypatch.setattr(cleanup, "candidates", lambda *, include_venv=False: [leaked])  # 那条窗口产出的计划
    holder = cleanup.ci_local.try_acquire_lock({"pid": 424242, "started_at": "now", "argv": "p"})
    assert holder is not None
    try:
        assert cleanup.main([]) == 1  # 拿不到锁就不删
    finally:
        holder.release()

    assert (leaked / "module.pyc").is_file()
    assert str(cleanup.ci_local.lock_path()) in capsys.readouterr().err


# --------------------------------------------------------------------------- 链接 / junction
#
# 缺陷（对抗复核实测）：`candidates()` 曾用 `rglob` 走树，而 `rglob` **跟随 junction / symlink**。
# 实测（Windows，`mklink /J` 免管理员）：
#   - `.tmp` 指向仓库外 ⇒ 计划 `['.tmp']`，而 `is_allowed('.tmp')` 为 False；
#   - `link/` 指向仓库外 ⇒ 计划里出现 `link/deep/__pycache__`、`link/deep/loose.pyc`（仓库外）。
# 不是数据丢失（失败关闭），而是「扫出来又被白名单拒」：计划与结论互相矛盾。下面三条用例把这个
# 形态钉成失败——修复前（`rglob` + `is_dir()` 跟随链接）必红，改成 `os.scandir` 不跟随重解析点
# 后 PASS。


def _make_directory_link(link: Path, target: Path) -> bool:
    """把 `link` 造成指向 `target` 的目录链接，返回是否造成功。

    Windows 用 `mklink /J`（junction，免管理员）；POSIX 用 `symlink_to`。环境不支持时返回
    False，由调用方 `pytest.skip`——不能把“造不出来”记成通过。
    """

    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        return False
    return True


def _assert_plan_is_inside_and_allowed(cleanup, tmp_root: Path) -> list[Path]:
    """计划的两条硬约束：每一项都落在 ROOT 之内，且每一项都过得了白名单。"""

    plan = cleanup.candidates()
    rejected = [str(item) for item in plan if not cleanup.is_allowed(item)]
    assert rejected == [], "计划里出现了过不了白名单的项"
    for item in plan:
        assert tmp_root in item.parents, item
    return plan


def test_link_to_outside_is_never_scanned_or_planned(monkeypatch, tmp_root, tmp_root_factory):
    """指向仓库外的目录链接：仓库外的内容一个都不该进计划。

    修复前 `rglob` 会顺着 junction 走进去，扫出 `link/deep/__pycache__`、
    `link/deep/loose.pyc` 这些仓库外路径——它们必然被白名单拒掉，计划与结论就此矛盾。
    """

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    outside = tmp_root_factory()
    (outside / "deep" / "__pycache__").mkdir(parents=True)
    (outside / "deep" / "__pycache__" / "x.pyc").write_bytes(b"")
    (outside / "deep" / "loose.pyc").write_bytes(b"")
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    link = tmp_root / "link"
    if not _make_directory_link(link, outside):
        pytest.skip("本环境不支持创建目录链接（Windows junction / POSIX symlink）")

    plan = _assert_plan_is_inside_and_allowed(cleanup, tmp_root)

    assert link not in plan
    for item in plan:
        assert outside not in item.parents, item
    assert plan == []  # 仓库里没有真缓存：链接不该贡献任何候选
    # 计划外的路径一律不动
    assert (outside / "deep" / "__pycache__" / "x.pyc").is_file()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_tmp_as_a_link_is_left_alone_including_its_target(
    monkeypatch, capsys, tmp_root, tmp_root_factory
):
    """.tmp 本身是指向仓库外的链接：不进计划、不为它上锁、更不删它下面的东西。

    修复前 `(REPO_ROOT / ".tmp").is_dir()` 跟随链接返回 True：`.tmp` 进了计划而
    `is_allowed(.tmp)` 为 False，取锁还会把 `ci-local.lock` 建到**仓库外**的目标里。
    """

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    outside = tmp_root_factory()
    (outside / "artifacts").mkdir()
    (outside / "artifacts" / "state.json").write_text("{}", encoding="utf-8")
    tmp_link = tmp_root / ".tmp"
    if not _make_directory_link(tmp_link, outside):
        pytest.skip("本环境不支持创建目录链接（Windows junction / POSIX symlink）")

    plan = _assert_plan_is_inside_and_allowed(cleanup, tmp_root)
    assert tmp_link not in plan
    assert plan == []

    assert cleanup.main([]) == 0
    out = capsys.readouterr().out
    assert "artifacts" not in out
    assert not cleanup.ci_local.lock_path().exists()  # 没扫到 .tmp：不为它上锁
    assert (outside / "artifacts" / "state.json").is_file()  # 链接的目标一点没动
    assert tmp_link.exists()  # 链接本身也留着：删它等于动它的目标


def test_link_inside_tmp_is_not_a_removal_target(monkeypatch, capsys, tmp_root, tmp_root_factory):
    """.tmp/ 里的目录链接不是删除目标：`removal_targets()` 也不能把链接交给 rmtree。

    候选集干净只是第一层；`.tmp/` 是真目录时，删除目标由 `tmp_children()`（`iterdir`）产出，
    junction 在那里同样会被列出来。修复前实测 `removal_targets(.tmp) == [.tmp/linked-cache]`、
    `shutil.rmtree(junction)` 抛 OSError，清理于是以失败退出。
    """

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    outside = tmp_root_factory()
    (outside / "payload").mkdir()
    (outside / "payload" / "keep.txt").write_text("keep", encoding="utf-8")
    shared = tmp_root / ".tmp"
    shared.mkdir()
    link = shared / "linked-cache"
    if not _make_directory_link(link, outside):
        pytest.skip("本环境不支持创建目录链接（Windows junction / POSIX symlink）")

    plan = _assert_plan_is_inside_and_allowed(cleanup, tmp_root)
    assert plan == [shared]  # `.tmp/` 是真目录：照常进计划，只删它的子项

    assert cleanup.main([]) == 0
    out = capsys.readouterr().out
    assert "linked-cache" not in out
    assert (outside / "payload" / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert link.exists()
    assert cleanup.ci_local.lock_path().is_file()  # `.tmp/` 在计划里 ⇒ 照常走取锁路径

def test_venv_caches_are_out_of_scope_by_default(monkeypatch, capsys, tmp_root):
    """`.venv/` 默认整支不碰：候选、白名单、真删三处都不认它。

    `.venv/` 是用户环境而不是仓库内容（工具链只把它当解释器路径，`src/validators` 的扫描器也
    主动排除它），而本脚本的对外承诺是「只动 `.tmp/`，不碰仓库真实文件」。默认删它既越权，
    又在「多个项目共用一个 venv」或「解释器写不了字节码」的环境里把用户环境不可逆地降级。
    """

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    venv_cache = tmp_root / ".venv" / "Lib" / "site-packages" / "__pycache__"
    venv_cache.mkdir(parents=True)
    (venv_cache / "mod.cpython-313.pyc").write_bytes(b"")
    (tmp_root / ".venv" / "loose.pyo").write_bytes(b"")
    repo_cache = tmp_root / "src" / "__pycache__"
    repo_cache.mkdir(parents=True)
    (repo_cache / "mod.cpython-313.pyc").write_bytes(b"")

    assert [path.as_posix() for path in cleanup.candidates()] == [repo_cache.as_posix()]
    assert cleanup.is_allowed(venv_cache) is False
    assert cleanup.is_allowed(tmp_root / ".venv" / "loose.pyo") is False
    assert cleanup.is_allowed(repo_cache) is True

    assert cleanup.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "将删除: src/__pycache__" in out
    assert ".venv" not in out


def test_include_venv_is_the_explicit_escape_hatch(monkeypatch, capsys, tmp_root):
    """只有显式 `--include-venv` 才把 `.venv/` 纳入（例如坏掉的 `.pyc` 让 import 直接失败）。"""

    cleanup = _load_cleanup_with_tmp_root(monkeypatch, tmp_root)
    venv_cache = tmp_root / ".venv" / "__pycache__"
    venv_cache.mkdir(parents=True)
    (venv_cache / "mod.pyc").write_bytes(b"")

    assert cleanup.candidates() == []
    assert cleanup.candidates(include_venv=True) == [venv_cache]
    assert cleanup.is_allowed(venv_cache) is False
    assert cleanup.is_allowed(venv_cache, include_venv=True) is True

    assert cleanup.main(["--dry-run", "--include-venv"]) == 0
    assert "将删除: .venv/__pycache__" in capsys.readouterr().out

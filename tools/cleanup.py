"""删除本仓库的临时产物。

用法：

    python tools/cleanup.py --dry-run   # 先看会删什么
    python tools/cleanup.py             # 真的删

删除范围（白名单，逐条判定）：

- 顶层 .tmp/、.pytest_cache/、.uv-cache/、.mypy_cache/、.ruff_cache/；
- 任意层级的 __pycache__/ 目录；
- 任意层级的 *.pyc / *.pyo 文件。

不删除源码、规则、文档、示例与 CI 配置；不跟随仓库外的路径。

和 `ci_local.py` 共用同一把排他锁
--------------------------------

`.tmp/` 是**共享状态**：门禁（`tools/ci_local.py`）与它调起的编排闭环、检索索引、阶段证据都把
固定路径的状态写在这里（`.tmp/phase-8-orchestration/`、`.tmp/artifacts/`、`.tmp/retrieval/`）。
一个进程边扫边删、另一个边读边写，就会跑出“代码没改却红了”的假红——这正是 `.tmp/ci-local.lock`
要消灭的东西。所以本脚本在**真的要删**的时候先取同一把锁（`ci_local.try_acquire_lock`，非阻塞）：
抢不到就报出持锁者 pid / 起始时间 / argv 后退出 1，**一项都不删**。加锁逻辑不复制一份，直接复用
`ci_local.py` 里已验证的实现（同目录脚本互相导入的先例见 `tools/build_learning_notebook.py`）。

两条刻意的例外：

- `--dry-run` **不取锁**：它只读、不删任何东西，别的实例跑着门禁时也照样能看清单
  （与 `ci_local.py --list` 同一口径）；
- `.tmp/` 不存在时**不取锁、也不把它建出来**：没有可保护的共享状态，而 `try_acquire_lock`
  会连同父目录一起 `mkdir`——为了上锁凭空造出 `.tmp/` 是本末倒置（所以判断要在取锁之前做）。

不变式：要么持锁，要么完全不碰 `.tmp/`
--------------------------------------

上面那条例外原先**不是严闭的**（对抗复核实测）：取锁判定问的是 `tmp_dir().is_dir()`，而删除集是
`_clean()` **重新扫描**出来的。两次观察之间就有一个 TOCTOU 窗口——`.tmp/` 恰在“判定之后、扫描
之前”出现，就会被**无锁**删光子项（注入该交错可复现：`exit=0`、`try_acquire_lock` 调用 0 次、
`.tmp/artifacts` 与 `.tmp/phase-8-orchestration` 被删，锁文件从未创建）。窗口只有微秒级，但
“不变式不成立”本身就是缺陷，代价是共享状态被删光。

修法是**扫描一次、由同一次扫描决定要不要上锁，并且只删这次扫描到的东西**：

- `main()` 先扫一次：`plan = candidates()`；
- `needs_lock` 由这份 `plan` 推出（`_touches_tmp()`：候选就是 `.tmp/`，或者落在它里面），
  不再回头问一次文件系统；
- `plan` 传进 `_clean()`，`_clean()` **绝不**重新调 `candidates()`。

于是：`.tmp/` 在扫描里 ⇒ 一定走取锁路径（抢不到就退出 1、一项不删）；不在扫描里 ⇒ 它压根不在
计划里，后面无论谁把它建出来都不会被这次清理碰到。关键性质因此成立：**`.tmp/` 的子项只可能在
持有锁的时候被删**。`removal_targets()` 仍然在删除那一刻把 `.tmp/` 展开成子项（那时已经持锁），
但“没持锁却走到它”这条路已经不存在了。

锁文件本身**永不删除**：`.tmp/` 的清理是“删它下面的每个子项、显式跳过 `ci-local.lock`”，而不是
`rmtree(.tmp)`。两层理由：Windows 上 `msvcrt` 的锁是强制锁，`rmtree` 会在被锁住的字节区间上失败
（WinError 32）——清理和持锁互相打架，而且是“先把共享状态删光、然后才失败”；POSIX 上 `flock` 认的
是 inode，删掉再重建等于**换了一把锁**，两个进程会各持一把，排他保证直接失效。锁空闲时它是一个
0 字节文件，留着不占地方。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"

# 锁只有一份实现，在 tools/ci_local.py 里：按同目录脚本互相导入的先例引进来，绝不复制加锁逻辑。
# 这句 import 必须留在 sys.path 之后——从仓库根直接运行时要靠它找到同目录的 ci_local，
# 而 validation/ruff.toml 的 select 里有 E402，所以它带 noqa。
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
import ci_local  # noqa: E402

TOP_LEVEL_DIRS = (
    ".tmp",
    ".pytest_cache",
    ".uv-cache",
    ".mypy_cache",
    ".ruff_cache",
    "artifacts",  # Phase 0 之前的证据目录，现已改到 .tmp/artifacts
)
CACHE_DIR_NAME = "__pycache__"
CACHE_FILE_SUFFIXES = (".pyc", ".pyo")


def tmp_dir() -> Path:
    """共享状态目录 `.tmp/`：ci_local 的锁与各闭环、索引的状态都住在它下面。"""

    return Path(REPO_ROOT) / ".tmp"


def lock_file_name() -> str:
    """锁文件名取自 `ci_local.lock_path()`：文件换名字时这里跟着换，不写死第二份。"""

    return ci_local.lock_path().name


def tmp_children() -> list[Path]:
    """`.tmp/` 下要删的子项，**排除锁文件**（为什么不能整体 rmtree 见模块 docstring）。"""

    root = tmp_dir()
    if not root.is_dir():
        return []
    lock_name = lock_file_name()
    return sorted((child for child in root.iterdir() if child.name != lock_name), key=str)


def _touches_tmp(path: Path) -> bool:
    """这个候选是不是“共享状态”：就是 `.tmp/` 本身，或者落在它里面。

    为什么不是 `path == tmp_dir()` 就够：`candidates()` 先判定顶层 `.tmp/` 是否存在、再用 `rglob`
    走树，这两次观察之间也有一段窗口——`.tmp/` 若在其中出现，`rglob` 可能把
    `.tmp/<x>/__pycache__` 捞进计划，而 `.tmp/` 本身不在计划里（去重只对“祖先也在计划里”的后代
    生效）。删掉落在 `.tmp/` 里的任何东西同样属于碰共享状态，所以按**是否落在 `.tmp/` 里**判定。
    """

    root = tmp_dir()
    return path == root or root in path.parents


def removal_targets(path: Path) -> list[Path]:
    """候选路径 → 实际要删的路径。

    只有 `.tmp/` 特殊：它是“删子项、留目录、留锁文件”，其余候选就是它自己。白名单判定仍然发生在
    候选上（`is_allowed()` 的语义不变），所以 `.tmp/` 依旧是被认的候选。
    """

    if path == tmp_dir():
        return tmp_children()
    return [path]


def candidates() -> list[Path]:
    """按目录优先的顺序返回候选路径，避免先删空父目录再报子项。"""

    found: list[Path] = [REPO_ROOT / name for name in TOP_LEVEL_DIRS if (REPO_ROOT / name).is_dir()]
    found.extend(path for path in REPO_ROOT.rglob(CACHE_DIR_NAME) if path.is_dir())
    for suffix in CACHE_FILE_SUFFIXES:
        found.extend(path for path in REPO_ROOT.rglob("*" + suffix) if path.is_file())

    unique = sorted(set(found), key=lambda item: (len(item.parts), str(item)))
    return [path for path in unique if not any(parent in unique for parent in path.parents)]


def is_allowed(path: Path) -> bool:
    """逐条白名单判定：只有缓存目录、缓存文件与 .tmp 是临时产物。"""

    try:
        relative = path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    if not relative.parts:
        return False
    if relative.parts[0] in TOP_LEVEL_DIRS and len(relative.parts) == 1:
        return True
    if path.is_dir() and path.name == CACHE_DIR_NAME:
        return True
    # 不用 `path.suffix`：Windows 上的 `rglob("*.pyc")` 大小写不敏感（`FOO.PYC` 也会被扫进来），
    # 而 `suffix in (...)` 的比较区分大小写；文件名恰为 `.pyc` 时 `Path(".pyc").suffix` 还是空串。
    # 两者都会让 `candidates()` 扫出来的候选被白名单反过来拒掉——静默跳过、退出码仍是 0。
    return path.is_file() and path.name.lower().endswith(CACHE_FILE_SUFFIXES)


def _remove(path: Path) -> OSError | None:
    """删掉一个路径：成功返回 None，失败把异常交回调用方计数（不抛）。"""

    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError as error:
        # 受限环境可能连自己创建的空目录都删不掉：必须报出来，不能假装成功
        return error
    return None


def _lock_metadata(argv: list[str] | None) -> dict[str, object]:
    """写进锁文件开头的元数据，格式复用 `ci_local.lock_metadata`。

    ci_local 记的是 `sys.argv[1:]`；cleanup 常常零参数运行，那样 argv 会是空串，别人（包括
    ci_local 的冲突提示）就看不出“占着锁的到底是谁”。所以补上脚本名：这一行永远看得出是 cleanup。
    """

    effective = list(sys.argv[1:] if argv is None else argv)
    return ci_local.lock_metadata(["tools/cleanup.py", *effective])


def _report_lock_conflict(holder: dict[str, object] | None) -> None:
    """拿不到锁时把“谁在占、怎么办”写到 stderr：锁路径、持锁者 pid、起始时间、argv。"""

    print("cleanup: 已经有一个实例在跑本机门禁（或另一个清理），拒绝并发删除。", file=sys.stderr)
    print("cleanup: 锁文件 %s" % ci_local.lock_path(), file=sys.stderr)
    # 持锁者信息走 ci_local 里已有的格式化入口，同一个口径不写两份。
    print("cleanup: %s" % ci_local._describe_lock_holder(holder), file=sys.stderr)
    print(
        "cleanup: 等它跑完再清，不要并发——本脚本删的正是它正在用的共享状态"
        "（.tmp/phase-8-orchestration、.tmp/artifacts、.tmp/retrieval）；"
        "边跑边删既会跑出假红，清理自己也会在删除动作上失败。",
        file=sys.stderr,
    )
    print(
        "cleanup: 锁由操作系统持有，持锁进程一死就自动释放（不会留陈旧锁）；"
        "确认没有实例在跑就直接重试，或者先用 --dry-run 看清单。",
        file=sys.stderr,
    )


def _clean(dry_run: bool, plan: list[Path]) -> int:
    """按白名单删除 `plan` 里的候选（`.tmp/` 只删子项）；返回退出码：有删除失败即 1。

    `plan` 由调用方**扫描一次**后传进来，且与“要不要上锁”的判定同源。这里绝不重新调
    `candidates()`：重扫会把“判定那一刻还不存在”的 `.tmp/` 拉进删除集，那正是无锁删除的窗口
    （见模块 docstring 的不变式）。
    """

    removed = 0
    skipped = 0
    blocked = 0
    for path in plan:
        relative = path.relative_to(REPO_ROOT).as_posix()
        if not is_allowed(path):
            print("跳过（不在白名单）:", relative)
            skipped += 1
            continue
        for target in removal_targets(path):
            target_relative = target.relative_to(REPO_ROOT).as_posix()
            if dry_run:
                print("将删除:", target_relative)
                removed += 1
                continue
            error = _remove(target)
            if error is not None:
                print(f"删除失败（{type(error).__name__}）: {target_relative}")
                blocked += 1
                continue
            print("已删除:", target_relative)
            removed += 1

    suffix = "（dry-run）" if dry_run else ""
    print(f"共 {removed} 项，跳过 {skipped} 项，失败 {blocked} 项{suffix}")
    if blocked:
        print("失败通常意味着当前环境的权限策略不允许删除；退出码为 1，请手工确认这些路径。")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="删除仓库内的临时产物")
    parser.add_argument("--dry-run", action="store_true", help="只列出，不删除")
    args = parser.parse_args(argv)

    # 先扫一次，并且**只删这次扫描到的东西**（不变式见模块 docstring）：判定与删除必须看同一份
    # 计划，否则“判定之后、扫描之前”出现的 `.tmp/` 会被无锁删光。扫描是只读的，拿不到锁时它
    # 也就是白读一趟，没有任何副作用。
    plan = candidates()
    # 只在“真的要删 `.tmp/` 里的东西”时才取锁，两条例外见模块 docstring：`--dry-run` 是只读的；
    # `.tmp/` 没扫到就没有可保护的共享状态，何况 try_acquire_lock 会连同父目录一起 mkdir——
    # 为了上锁凭空造出 `.tmp/` 是本末倒置。
    needs_lock = not args.dry_run and any(_touches_tmp(path) for path in plan)
    # 先读一次元数据：拿不到锁时它属于“此刻正占着锁”的那个人。放在尝试之前读，是为了避开
    # “对方刚好在失败之后释放、元数据被清空”这个窗口——那样就报不出持锁者 pid 了。
    holder = ci_local.read_lock_metadata() if needs_lock else None

    lock = None
    if needs_lock:
        try:
            lock = ci_local.try_acquire_lock(_lock_metadata(argv))
        except OSError as error:
            print(
                "cleanup: 建立排他锁失败（%s）：%s" % (ci_local.lock_path(), error),
                file=sys.stderr,
            )
            print("cleanup: 拿不到这把锁就没有排他保证：失败关闭，一项都不删。", file=sys.stderr)
            return 1
        if lock is None:
            # 前一次读不到（文件刚建好或被清空）就再读一次：此刻持锁者仍然在。
            _report_lock_conflict(holder or ci_local.read_lock_metadata())
            return 1

    try:
        return _clean(args.dry_run, plan)
    finally:
        # 正常结束、异常、提前 return 都要还锁：句柄留在进程里的话，后面的门禁会被一把
        # “没人持有却拿不到”的锁挡住。lock is None 表示这次本来就没取锁。
        if lock is not None:
            lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

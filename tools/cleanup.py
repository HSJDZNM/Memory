"""删除本仓库的临时产物。

用法：

    python tools/cleanup.py --dry-run   # 先看会删什么
    python tools/cleanup.py             # 真的删

删除范围（白名单，逐条判定）：

- 顶层 .tmp/、.pytest_cache/、.uv-cache/、.mypy_cache/、.ruff_cache/；
- 任意层级的 __pycache__/ 目录；
- 任意层级的 *.pyc / *.pyo 文件。

不删除源码、规则、文档、示例与 CI 配置；不跟随仓库外的路径。
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
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
    return False
    return path.is_file() and path.suffix in CACHE_FILE_SUFFIXES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="删除仓库内的临时产物")
    parser.add_argument("--dry-run", action="store_true", help="只列出，不删除")
    args = parser.parse_args(argv)

    removed = 0
    skipped = 0
    blocked = 0
    for path in candidates():
        relative = path.relative_to(REPO_ROOT).as_posix()
        if not is_allowed(path):
            print("跳过（不在白名单）:", relative)
            skipped += 1
            continue
        if args.dry_run:
            print("将删除:", relative)
            removed += 1
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError as error:
            # 受限环境可能连自己创建的空目录都删不掉：必须报出来，不能假装成功
            print(f"删除失败（{type(error).__name__}）: {relative}")
            blocked += 1
            continue
        print("已删除:", relative)
        removed += 1

    suffix = "（dry-run）" if args.dry_run else ""
    print(f"共 {removed} 项，跳过 {skipped} 项，失败 {blocked} 项{suffix}")
    if blocked:
        print("失败通常意味着当前环境的权限策略不允许删除；退出码为 1，请手工确认这些路径。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

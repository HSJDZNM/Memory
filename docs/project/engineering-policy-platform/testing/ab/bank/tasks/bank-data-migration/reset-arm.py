#!/usr/bin/env python3
"""reset-arm.py - 把数据迁移题（bank-data-migration）的任务树重置为 13 文件基线。

基线（冻结）= 本包 baseline/ 目录里的 13 个文件：
  订单示例项目 11 文件（与 tasks/bank-flagship-returns/baseline 的同名文件逐字节相同，
  后者与 examples/dsh/b-plan/sample-project 逐字节相同）
  + data/ledger-v1.jsonl（迁移输入：4 条 v1 台账，id 顺序 3/1/4/2，一条 cents=0；只读）
  + config/ledger_schema.yaml（v2 形状声明：只读输入）
基线里**没有** tools/__init__.py（本任务不新增它：tools/ 由任务新建的两个脚本带出来）。
组合摘要见 BASELINE_MANIFEST_SHA256（算法 = 按相对路径排序的「<sha256>  <relpath>」清单文本再 sha256）。

本脚本做四件事（只动目标树里 .policy 之外的部分）：
  1. .policy 原样保留（audit / ledger / approval / registry / config 一个字节不动）；
     只清掉 .policy/pre-evidence 影子副本残留（上一轮取证的临时目录，不是证据）。
  2. 删掉 .policy 之外的全部文件/目录，逐字节重写 13 个基线文件。
  3. 逐文件 sha256 校验（13/13 必须一致）+ 没有 .policy 之外的多余文件 + 基线组合摘要一致。
  4. 打印并写出 <target 的父目录>/reset-manifest.json：基线组合摘要、audit 起始行数
     （ab_measure / measure_all 的 --start-line）、approval sha256。

用法（由 Lead 在开跑前执行一次）：
    .venv/Scripts/python.exe <本包>/reset-arm.py --dry-run
    .venv/Scripts/python.exe <本包>/reset-arm.py
    .venv/Scripts/python.exe <本包>/reset-arm.py --target <树>

退出码：
    0 = 重置并校验通过（含 --dry-run）
    1 = 前置缺失（baseline/ 不存在 / 文件数不是 13 / 基线里出现任务要创建的文件 / 组合摘要不符）
    2 = 校验失败（JSON 载荷写明 mismatches / extra / undeletable）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

BASELINE_FILE_COUNT = 13
BASELINE_MANIFEST_SHA256 = "eedac602c64c7dbd4633d01a481495fa489406ac08e3a85a2c1c4ac2e0c91fa3"
POLICY_DIR = ".policy"
PRE_EVIDENCE_DIR = ".policy/pre-evidence"
AUDIT_NAME = "audit.jsonl"
APPROVAL_NAME = "approval.json"
#: 基线里**必须没有**的文件：它们必须由模型在里程碑里亲手写出来（预置 = 撤掉任务）。
TASK_CREATED = (
    "data/ledger-v2.jsonl",
    "docs/migration.md",
    "src/shop/ledger_migration.py",
    "tests/test_ledger_migration.py",
    "tests/test_migrate_ledger.py",
    "tests/test_verify_ledger.py",
    "tools/migrate_ledger.py",
    "tools/verify_ledger.py",
)
CACHE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")
CACHE_DIR_PREFIXES = ("pytest-cache-files-",)


def _repo_root(start: Path) -> Path:
    """从本文件位置向上找仓库根（含 .git 或 pyproject.toml 的目录）。"""
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("reset-arm: 找不到仓库根（.git / pyproject.toml 都不在祖先目录里）")


PACKAGE = Path(__file__).resolve().parent
REPO = _repo_root(PACKAGE)
BASELINE = PACKAGE / "baseline"
DEFAULT_TARGET = REPO / ".tmp" / "bank-data-migration" / "tree"


def _sha256_bytes(payload: bytes) -> str:
    """算一段字节的 sha256。"""
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    """算一个文件的 sha256（原始字节，不做换行归一化）。"""
    return _sha256_bytes(path.read_bytes())


def _manifest_sha256(files: dict[str, bytes]) -> str:
    """基线组合摘要：按相对路径排序的清单文本（与任务包 README 同一算法）。"""
    lines = [f"{_sha256_bytes(payload)}  {rel}" for rel, payload in sorted(files.items())]
    return _sha256_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _display(path: Path) -> str:
    """仓库内路径写成仓库相对 POSIX 形式，仓库外写绝对路径（读数里不留含糊）。"""
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _resolve_target(raw: str) -> Path:
    """--target 的相对路径按仓库根解析（不是按调用者的 cwd）。"""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = REPO / candidate
    return candidate.resolve()


def _is_cache_dir(name: str) -> bool:
    """是不是宿主沙箱可能删不掉的缓存目录。"""
    return name in CACHE_DIR_NAMES or name.startswith(CACHE_DIR_PREFIXES)


def _baseline_files() -> dict[str, bytes]:
    """baseline/ 里的 13 个文件 -> {相对路径: 字节}。"""
    if not BASELINE.is_dir():
        raise SystemExit(f"reset-arm: 基线树不存在：{_display(BASELINE)}")
    files: dict[str, bytes] = {}
    for path in sorted(BASELINE.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(BASELINE).as_posix()
        if rel == POLICY_DIR or rel.startswith(POLICY_DIR + "/"):
            continue
        files[rel] = path.read_bytes()
    if len(files) != BASELINE_FILE_COUNT:
        raise SystemExit(
            f"reset-arm: 期望基线 {BASELINE_FILE_COUNT} 个文件，实际 {len(files)}：{sorted(files)}"
        )
    present = [rel for rel in TASK_CREATED if rel in files]
    if present:
        raise SystemExit(f"reset-arm: 基线里出现了任务要创建的文件 {present}")
    digest = _manifest_sha256(files)
    if digest != BASELINE_MANIFEST_SHA256:
        raise SystemExit(
            "reset-arm: 基线组合摘要不符（改基线 = 改构造，必须显式更新常量）："
            f" expected={BASELINE_MANIFEST_SHA256} actual={digest}"
        )
    return files


def _audit_start_lines(target: Path) -> dict:
    """目标树 .policy/audit.jsonl 的当前行数（measure_all 的 --start-line）。"""
    audit = target / POLICY_DIR / AUDIT_NAME
    path = f"{_display(target)}/{POLICY_DIR}/{AUDIT_NAME}"
    if not audit.is_file():
        return {"path": path, "exists": False, "lines": 0}
    lines = [
        line
        for line in audit.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    return {"path": path, "exists": True, "lines": len(lines)}


def _approval_info(target: Path) -> dict:
    """目标树 .policy/approval.json 的 sha256（不存在就是 None，不是空串）。"""
    approval = target / POLICY_DIR / APPROVAL_NAME
    path = f"{_display(target)}/{POLICY_DIR}/{APPROVAL_NAME}"
    if not approval.is_file():
        return {"path": path, "exists": False, "sha256": None}
    return {"path": path, "exists": True, "sha256": _sha256_file(approval)}


def _extra_non_policy_entries(target: Path) -> list[str]:
    """目标树里 .policy 之外当前有哪些顶层条目。"""
    if not target.is_dir():
        return []
    return sorted(path.name for path in target.iterdir() if path.name != POLICY_DIR)


def _remove_entry(path: Path) -> bool:
    """删除一个文件/目录；宿主沙箱 ACL 残留（pytest-cache-files-*）删不掉时返回 False。"""
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    except (PermissionError, OSError):
        return False


def _scan_files(root: Path) -> tuple[list[str], list[str]]:
    """列出 .policy 之外的文件（相对路径），返回 (files, unreadable_dirs)。"""
    files: list[str] = []
    unreadable: list[str] = []

    def onerror(error: OSError) -> None:
        value = getattr(error, "filename", None)
        unreadable.append(str(value) if value else str(error))

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        here = Path(dirpath)
        relative_dir = here.relative_to(root).as_posix()
        if relative_dir == POLICY_DIR or relative_dir.startswith(POLICY_DIR + "/"):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(
            name for name in dirnames if name != POLICY_DIR and not _is_cache_dir(name)
        )
        for name in sorted(filenames):
            rel = f"{relative_dir}/{name}" if relative_dir != "." else name
            files.append(rel)
    return files, unreadable


def _dry_run(files: dict[str, bytes], target: Path) -> int:
    """只打印计划，不写任何文件。"""
    policy_present = (target / POLICY_DIR).is_dir()
    print("[reset-arm] DRY-RUN（不写任何文件）")
    print(f"  target        : {_display(target)}")
    print(f"  baseline src  : {_display(BASELINE)}（{len(files)} 文件）")
    print(f"  expected files ({len(files)}): {sorted(files)}")
    print(f"  task-created files NOT in baseline: {list(TASK_CREATED)}")
    print(f"  .policy       : {'present（保留，不重建）' if policy_present else 'absent（不创建）'}")
    pre_evidence = (target / PRE_EVIDENCE_DIR).exists()
    print(f"  pre-evidence  : {'would remove .policy/pre-evidence' if pre_evidence else 'absent'}")
    extras = _extra_non_policy_entries(target)
    print(f"  non-.policy entries currently under target ({len(extras)}): {extras}")
    print(
        "  cache-dir residue expected to be undeletable: "
        f"{[name for name in extras if _is_cache_dir(name)]}"
    )
    print(f"  baseline manifest sha256: {_manifest_sha256(files)}")
    print(f"  audit start lines (current): {_audit_start_lines(target)}")
    print(f"  approval sha256 : {_approval_info(target)['sha256']}")
    for rel in sorted(files):
        current = target / rel
        if not current.is_file():
            status = "absent"
        elif current.read_bytes() == files[rel]:
            status = "same"
        else:
            status = "differs"
        print(f"    {status:8s} {rel}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """重置目标树并校验 13/13；--dry-run 只打印计划。"""
    parser = argparse.ArgumentParser(
        description="把目标树重置为 bank-data-migration 的 13 文件基线"
    )
    parser.add_argument(
        "--target", default=str(DEFAULT_TARGET), help="目标树（默认 .tmp/bank-data-migration/tree）"
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写任何文件")
    args = parser.parse_args(argv)

    files = _baseline_files()
    target = _resolve_target(args.target)
    if args.dry_run:
        return _dry_run(files, target)

    target.mkdir(parents=True, exist_ok=True)
    pre_evidence_removed = False
    if (target / PRE_EVIDENCE_DIR).exists():
        pre_evidence_removed = _remove_entry(target / PRE_EVIDENCE_DIR)

    removed: list[str] = []
    undeletable: list[str] = []
    residual_cache_dirs: list[str] = []
    for child in sorted(target.iterdir()):
        if child.name == POLICY_DIR:
            continue
        if _remove_entry(child):
            removed.append(child.name)
        elif _is_cache_dir(child.name):
            residual_cache_dirs.append(child.name)
        else:
            undeletable.append(child.name)

    for rel, payload in sorted(files.items()):
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    mismatches = []
    for rel, payload in sorted(files.items()):
        path = target / rel
        if not path.is_file():
            mismatches.append({"file": rel, "reason": "missing"})
            continue
        actual = path.read_bytes()
        if actual != payload:
            mismatches.append(
                {
                    "file": rel,
                    "reason": "sha256 mismatch",
                    "expected": _sha256_bytes(payload),
                    "actual": _sha256_bytes(actual),
                }
            )
    scanned, unreadable = _scan_files(target)
    extra = sorted(set(scanned) - set(files))
    if mismatches or extra or undeletable:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "target": _display(target),
                    "mismatches": mismatches,
                    "extra": extra,
                    "undeletable": undeletable,
                    "residual_cache_dirs": residual_cache_dirs,
                    "unreadable": unreadable,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    baseline_manifest = _manifest_sha256(files)
    audit = _audit_start_lines(target)
    approval = _approval_info(target)
    manifest = {
        "schema": "bank-data-migration.reset-arm/1",
        "status": "ok",
        "target": _display(target),
        "baseline_source": _display(BASELINE),
        "file_count": len(files),
        "files": sorted(files),
        "baseline_manifest_sha256": baseline_manifest,
        "audit": audit,
        "audit_start_lines": audit["lines"],
        "approval": approval,
        "policy_kept": (target / POLICY_DIR).is_dir(),
        "pre_evidence_removed": pre_evidence_removed,
        "removed_entries": removed,
        "residual_cache_dirs": residual_cache_dirs,
        "residual_note": (
            "宿主沙箱 ACL 残留的缓存目录（__pycache__ / .pytest_cache / pytest-cache-files-*）"
            "删不掉；它们不是任务文件，读数时记 unmeasured，不得当成空。"
        ),
        "undeletable_entries": undeletable,
        "unreadable_dirs": unreadable,
        "mismatches": [],
        "dry_run": False,
    }
    manifest_path = target.parent / "reset-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"[reset-arm] reset {len(files)} files under {_display(target)}")
    print(f"[reset-arm] removed non-.policy entries: {removed}")
    if residual_cache_dirs:
        print(
            "[reset-arm] INFO 宿主沙箱 ACL 残留缓存目录（不可删，按 unmeasured 记录）: "
            f"{residual_cache_dirs}"
        )
    if undeletable:
        print(f"[reset-arm] ERROR 非缓存目录删不掉（会让树不干净，必须人工处理）: {undeletable}")
    if unreadable:
        print(
            f"[reset-arm] WARNING 不可枚举目录（读数时必须写 unmeasured，不得当成空）: {unreadable}"
        )
    print(f"[reset-arm] pre-evidence removed: {pre_evidence_removed}")
    print(f"[reset-arm] {len(files)}/{len(files)} sha256 verified")
    print(f"[reset-arm] baseline manifest sha256: {baseline_manifest}")
    print(f"[reset-arm] audit start lines: {audit['lines']} ({audit['path']})")
    print(f"[reset-arm] approval sha256: {approval['sha256']}")
    print(f"[reset-arm] manifest: {_display(manifest_path)}")
    print("RESET-ARM-JSON: " + json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

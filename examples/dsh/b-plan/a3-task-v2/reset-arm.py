#!/usr/bin/env python3
"""reset-arm.py - 把 .tmp/a3b/task-project 重置为 A3 v2 的 12 文件基线（不跑 dsh）。

A3 v2 基线（冻结）= sample-project 的 11 个文件 + 预置的 tools/audit_demo.py = 12 文件：
  * 11 文件来自 .tmp/a3b/baseline-tree
  * tools/audit_demo.py 来自 .tmp/a3b2/scaffold/tools/audit_demo.py

本脚本做四件事（**只动 .tmp/a3b/task-project 的 .policy 之外的部分**）：
  1. 保留 .tmp/a3b/task-project/.policy（audit / ledger / approval / registry / config 不动）；
     只清掉 .policy/pre-evidence 影子副本残留（上一轮取证的临时目录，不是证据）。
  2. 删掉 .policy 之外的全部文件/目录，重写 12 个基线文件（逐字节）。
  3. 逐文件 sha256 校验（12/12 必须一致），并冻结一份 .tmp/a3b2/baseline-tree（12 文件）
     供 measure_all.py 的 --baseline-tree 使用。
  4. 打印并写出 .tmp/a3b2/reset-manifest.json：
     audit 起始行数（measure_all.py 的 --start-line）、approval sha256、基线 manifest sha256。

用法（**由 Lead 在开跑前执行一次**）：
    .venv/Scripts/python.exe .tmp/a3b2/reset-arm.py
    .venv/Scripts/python.exe .tmp/a3b2/reset-arm.py --dry-run   # 只打印计划，不写任何文件
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

REPO = Path(__file__).resolve().parents[4]
A3B = REPO / ".tmp" / "a3b"
BASELINE = REPO / "examples" / "dsh" / "b-plan" / "sample-project"
TARGET = A3B / "task-project"
SCAFFOLD_DEMO = REPO / "examples" / "dsh" / "b-plan" / "a3-task-v2" / "scaffold" / "tools" / "audit_demo.py"
V2_BASELINE = REPO / ".tmp" / "a3b2" / "baseline-tree"
RESET_MANIFEST = REPO / ".tmp" / "a3b2" / "reset-manifest.json"
AUDIT = TARGET / ".policy" / "audit.jsonl"
APPROVAL = TARGET / ".policy" / "approval.json"
POLICY_REQUIRED = (
    "dsh-adapter.yaml",
    "hooks.json",
    "tool-registry.yaml",
    "tool-registry.approved.json",
    "approval.json",
)
PRE_EVIDENCE_DIR = ".policy/pre-evidence"
#: 宿主沙箱会把这些缓存目录的 ACL 改成 DENY-delete（U2b §8.2 / v1 实测）；它们不是任务文件，
#: 删不掉时按"残留缓存目录"显式记录，而不是让 reset 失败或静默当成删掉了。
CACHE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")
CACHE_DIR_PREFIXES = ("pytest-cache-files-",)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _manifest_sha256(files: dict[str, bytes]) -> str:
    lines = [f"{_sha256_bytes(payload)}  {rel}" for rel, payload in sorted(files.items())]
    return _sha256_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _baseline_files() -> dict[str, bytes]:
    """11 个基线文件（.tmp/a3b/baseline-tree，排除 .policy）→ {相对路径: 字节}。"""

    if not BASELINE.is_dir():
        raise SystemExit(f"reset-arm: 基线树不存在：{BASELINE}")
    files: dict[str, bytes] = {}
    for path in sorted(BASELINE.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(BASELINE).as_posix()
        if rel == ".policy" or rel.startswith(".policy/"):
            continue
        files[rel] = path.read_bytes()
    return files


def _target_files() -> dict[str, bytes]:
    """期望的 12 个文件（11 + scaffold demo）→ {相对路径: 字节}。"""

    files = _baseline_files()
    if not SCAFFOLD_DEMO.is_file():
        raise SystemExit(f"reset-arm: 脚手架 demo 不存在：{SCAFFOLD_DEMO}")
    files["tools/audit_demo.py"] = SCAFFOLD_DEMO.read_bytes()
    if len(files) != 12:
        raise SystemExit(f"reset-arm: 期望 12 个基线文件，实际 {len(files)}：{sorted(files)}")
    return files


def _requires_policy() -> None:
    if not (TARGET / ".policy").is_dir():
        raise SystemExit(
            "reset-arm: 受治树 .policy 不存在（reset-arm 保留 .policy，不重建它）。"
            "先按 .tmp/a3b2/README.md 的『第 2 步：装配 .policy』补齐再重置。"
        )
    missing = [name for name in POLICY_REQUIRED if not (TARGET / ".policy" / name).is_file()]
    if missing:
        raise SystemExit(
            "reset-arm: .policy 缺文件 "
            f"{missing}；先按 .tmp/a3b2/README.md 的『第 2 步：装配 .policy』补齐再重置。"
        )


def _audit_start_lines() -> dict:
    if not AUDIT.is_file():
        return {"path": str(AUDIT.relative_to(REPO)).replace("\\", "/"), "exists": False, "lines": 0}
    lines = [line for line in AUDIT.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    return {
        "path": str(AUDIT.relative_to(REPO)).replace("\\", "/"),
        "exists": True,
        "lines": len(lines),
    }


def _approval_info() -> dict:
    if not APPROVAL.is_file():
        return {
            "path": str(APPROVAL.relative_to(REPO)).replace("\\", "/"),
            "exists": False,
            "sha256": None,
        }
    return {
        "path": str(APPROVAL.relative_to(REPO)).replace("\\", "/"),
        "exists": True,
        "sha256": _sha256_file(APPROVAL),
    }


def _extra_non_policy_entries() -> list[str]:
    if not TARGET.is_dir():
        return []
    return sorted(
        path.name for path in TARGET.iterdir() if path.name != ".policy"
    )


def _is_cache_dir(name: str) -> bool:
    return name in CACHE_DIR_NAMES or name.startswith(CACHE_DIR_PREFIXES)


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
    """列出 .policy 之外的文件（相对路径），返回 (files, unreadable_dirs)。

    v1 留下的 pytest-cache-files-* 目录在宿主沙箱下是 DENY-delete、甚至不可枚举的；
    os.walk 的 onerror 把它们记成 unreadable，而不是静默当成"没有文件"（AGENTS 53）。
    """

    files: list[str] = []
    unreadable: list[str] = []

    def onerror(error: OSError) -> None:
        value = getattr(error, "filename", None)
        unreadable.append(str(value) if value else str(error))

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        here = Path(dirpath)
        relative_dir = here.relative_to(root).as_posix()
        if relative_dir == ".policy" or relative_dir.startswith(".policy/"):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name != ".policy" and not _is_cache_dir(name)
        )
        for name in sorted(filenames):
            rel = f"{relative_dir}/{name}" if relative_dir != "." else name
            files.append(rel)
    return files, unreadable


def _dry_run(files: dict[str, bytes], policy_ok: bool) -> int:
    print("[reset-arm] DRY-RUN（不写任何文件）")
    print(f"  target        : {TARGET.relative_to(REPO).as_posix()}")
    print(f"  baseline src  : {BASELINE.relative_to(REPO).as_posix()} (11 files) + scaffold demo")
    print(f"  expected files: {len(files)}")
    print(f"  .policy       : {'present' if policy_ok else 'MISSING (real run would exit 2)'}")
    print(f"  pre-evidence  : {'would remove .policy/pre-evidence' if (TARGET / PRE_EVIDENCE_DIR).exists() else 'absent'}")
    extras = _extra_non_policy_entries()
    print(f"  non-.policy entries currently under target ({len(extras)}): {extras}")
    print(
        "  cache-dir residue expected to be undeletable: "
        f"{[name for name in extras if _is_cache_dir(name)]}"
    )
    print(f"  baseline manifest sha256: {_manifest_sha256(files)}")
    print(f"  audit start lines (current): {_audit_start_lines()}")
    print(f"  approval sha256 : {_approval_info()['sha256']}")
    for rel in sorted(files):
        current = TARGET / rel
        status = "same" if current.is_file() and current.read_bytes() == files[rel] else (
            "absent" if not current.is_file() else "differs"
        )
        print(f"    {status:8s} {rel}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="把 .tmp/a3b/task-project 重置为 A3 v2 的 12 文件基线")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写任何文件")
    args = parser.parse_args(argv)

    files = _target_files()
    policy_ok = (TARGET / ".policy").is_dir()
    if args.dry_run:
        return _dry_run(files, policy_ok)
    _requires_policy()

    pre_evidence_removed = False
    if (TARGET / PRE_EVIDENCE_DIR).exists():
        pre_evidence_removed = _remove_entry(TARGET / PRE_EVIDENCE_DIR)

    removed: list[str] = []
    undeletable: list[str] = []
    residual_cache_dirs: list[str] = []
    for child in sorted(TARGET.iterdir()):
        if child.name == ".policy":
            continue
        if _remove_entry(child):
            removed.append(child.name)
        elif _is_cache_dir(child.name):
            residual_cache_dirs.append(child.name)
        else:
            undeletable.append(child.name)

    for rel, payload in sorted(files.items()):
        destination = TARGET / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    # 逐文件 sha256 校验 + 确认没有多余的非 .policy 文件
    mismatches = []
    for rel, payload in sorted(files.items()):
        path = TARGET / rel
        if not path.is_file():
            mismatches.append({"file": rel, "reason": "missing"})
            continue
        actual = path.read_bytes()
        if actual != payload:
            mismatches.append(
                {"file": rel, "reason": "sha256 mismatch", "expected": _sha256_bytes(payload),
                 "actual": _sha256_bytes(actual)}
            )
    scanned, unreadable = _scan_files(TARGET)
    extra = sorted(set(scanned) - set(files))
    if mismatches or extra or undeletable:
        print(json.dumps({"status": "failed", "mismatches": mismatches, "extra": extra,
                          "undeletable": undeletable, "residual_cache_dirs": residual_cache_dirs,
                          "unreadable": unreadable},
                         ensure_ascii=False, indent=2))
        return 2

    # 冻结 v2 基线（12 文件，不含 .policy），供 measure_all.py --baseline-tree
    if V2_BASELINE.exists():
        shutil.rmtree(V2_BASELINE)
    for rel, payload in sorted(files.items()):
        destination = V2_BASELINE / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    baseline_manifest = _manifest_sha256(files)
    audit = _audit_start_lines()
    approval = _approval_info()
    manifest = {
        "schema": "a3b2.reset-arm/1",
        "status": "ok",
        "target": TARGET.relative_to(REPO).as_posix(),
        "baseline_source": [
            BASELINE.relative_to(REPO).as_posix(),
            SCAFFOLD_DEMO.relative_to(REPO).as_posix(),
        ],
        "frozen_baseline": V2_BASELINE.relative_to(REPO).as_posix(),
        "file_count": len(files),
        "files": sorted(files),
        "baseline_manifest_sha256": baseline_manifest,
        "audit": audit,
        "audit_start_lines": audit["lines"],
        "approval": approval,
        "policy_kept": True,
        "pre_evidence_removed": pre_evidence_removed,
        "removed_entries": removed,
        "residual_cache_dirs": residual_cache_dirs,
        "residual_note": (
            "宿主沙箱 ACL 残留的缓存目录（__pycache__ / .pytest_cache / pytest-cache-files-*）"
            "删不掉；它们不是任务文件，measure_all 的 coverage 会把它们记 unmeasured。"
        ),
        "undeletable_entries": undeletable,
        "unreadable_dirs": unreadable,
        "mismatches": [],
        "dry_run": False,
    }
    RESET_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    RESET_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"[reset-arm] reset {len(files)} files; removed non-.policy entries: {removed}")
    if residual_cache_dirs:
        print(
            "[reset-arm] INFO 宿主沙箱 ACL 残留缓存目录（不可删，按 unmeasured 记录）: "
            f"{residual_cache_dirs}"
        )
    if undeletable:
        print(f"[reset-arm] ERROR 非缓存目录删不掉（会让树不干净，必须人工处理）: {undeletable}")
    if unreadable:
        print(f"[reset-arm] WARNING 不可枚举目录（读数时必须写 unmeasured，不得当成空）: {unreadable}")
    print(f"[reset-arm] pre-evidence removed: {pre_evidence_removed}")
    print(f"[reset-arm] 12/12 sha256 verified; frozen baseline: {V2_BASELINE.relative_to(REPO).as_posix()}")
    print(f"[reset-arm] baseline manifest sha256: {baseline_manifest}")
    print(f"[reset-arm] audit start lines: {audit['lines']} ({audit['path']})")
    print(f"[reset-arm] approval sha256: {approval['sha256']}")
    print(f"[reset-arm] manifest: {RESET_MANIFEST.relative_to(REPO).as_posix()}")
    print("RESET-ARM-JSON: " + json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

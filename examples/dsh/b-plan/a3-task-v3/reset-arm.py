#!/usr/bin/env python3
"""reset-arm.py - 把 A3 v3 的任务树重置为 12 文件基线（不跑 dsh）。

A3 v3 基线（冻结）= 上一级 sample-project 的 **11 个文件** + 预置的 **tools/__init__.py**
= **12 个文件**，**不含任何 scaffold**，也**不含任务要创建的两个文件**
（tools/audit_demo.py / tests/test_audit_demo.py）——那两个文件必须由模型在 M5a/M5b 亲手写出来，
treatment（validation/test-layout.yaml 的 production_patterns 增 tools/**/*.py）才有激活点。

为什么基线里要有 tools/__init__.py：M5a 先写 tests/test_audit_demo.py，它 import 的是
tools.audit_demo。树里没有 tools/__init__.py 时，收集期的 ModuleNotFoundError: No module
named 'tools' 会被判成**第三方包缺失** → TESTING-002 critical 阻断；有它之后缺的是**项目内**
模块 tools.audit_demo → 走 AGENTS 第 51 条的「待实现」（allow_with_warnings + pending_findings）。
两条读数都在 README §3（实测）。

本脚本做四件事（**只动目标树里 .policy 之外的部分**）：
  1. .policy 原样保留（audit / ledger / approval / registry / config 一个字节不动）；
     只清掉 .policy/pre-evidence 影子副本残留（上一轮取证的临时目录，不是证据）。
  2. 删掉 .policy 之外的全部文件/目录，逐字节重写 12 个基线文件。
  3. 逐文件 sha256 校验（12/12 必须一致）+ 没有 .policy 之外的多余文件。
  4. 打印并写出 <target 的父目录>/reset-manifest.json：基线 12 文件的组合摘要
     （算法与 a3-task-v2/reset-arm.py 的 _manifest_sha256 相同）、audit 起始行数
     （ab_measure / measure_all 的 --start-line）、approval sha256。

用法（**由 Lead 在开跑前执行一次**）：
    .venv/Scripts/python.exe examples/dsh/b-plan/a3-task-v3/reset-arm.py --dry-run
    .venv/Scripts/python.exe examples/dsh/b-plan/a3-task-v3/reset-arm.py
    .venv/Scripts/python.exe examples/dsh/b-plan/a3-task-v3/reset-arm.py --target <树>

退出码（与 a3-task-v2/reset-arm.py 一致）：
    0 = 重置并校验通过（含 --dry-run）
    1 = 前置缺失（基线树不存在 / 文件数不是 12 / 基线里出现 scaffold 或任务要创建的文件）
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

REPO = Path(__file__).resolve().parents[4]
BASELINE = REPO / "examples" / "dsh" / "b-plan" / "sample-project"
DEFAULT_TARGET = REPO / ".tmp" / "a3b3" / "task-project"
BASELINE_FILE_COUNT = 12
POLICY_DIR = ".policy"
PRE_EVIDENCE_DIR = ".policy/pre-evidence"
AUDIT_NAME = "audit.jsonl"
APPROVAL_NAME = "approval.json"
#: 基线里**必须没有**的文件：它们是任务要让模型新建的东西，预置进来就等于撤掉激活点。
TASK_CREATED = ("tools/audit_demo.py", "tests/test_audit_demo.py")
#: 第 12 个基线文件：它是**基线的一部分**（不是 scaffold）——见模块 docstring 里的理由。
BASELINE_EXTRA_TEXT = {"tools/__init__.py": '"""项目脚本包（演示与运维脚本）。"""\n'}
#: 宿主沙箱会把这些缓存目录的 ACL 改成 DENY-delete（v1 实测）；它们不是任务文件，
#: 删不掉时按"残留缓存目录"显式记录，而不是让 reset 失败或静默当成删掉了。
CACHE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")
CACHE_DIR_PREFIXES = ("pytest-cache-files-",)


def _sha256_bytes(payload: bytes) -> str:
    """算一段字节的 sha256。"""
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    """算一个文件的 sha256（原始字节，不做换行归一化）。"""
    return _sha256_bytes(path.read_bytes())


def _manifest_sha256(files: dict[str, bytes]) -> str:
    """基线组合摘要：与 a3-task-v2/reset-arm.py 同一个算法（按 relpath 排序的清单文本）。"""
    lines = [f"{_sha256_bytes(payload)}  {rel}" for rel, payload in sorted(files.items())]
    return _sha256_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _display(path: Path) -> str:
    """仓库内路径写成仓库相对 POSIX 形式，仓库外写绝对路径（读数里不留含糊）。"""
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _resolve_target(raw: str) -> Path:
    """--target 的相对路径按**仓库根**解析（不是按调用者的 cwd）。"""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = REPO / candidate
    return candidate.resolve()


def _is_cache_dir(name: str) -> bool:
    """是不是宿主沙箱可能删不掉的缓存目录。"""
    return name in CACHE_DIR_NAMES or name.startswith(CACHE_DIR_PREFIXES)


def _sample_files() -> dict[str, bytes]:
    """sample-project 的 11 个文件（排除 .policy）-> {相对路径: 字节}。"""

    if not BASELINE.is_dir():
        raise SystemExit(f"reset-arm: 基线树不存在：{_display(BASELINE)}")
    files: dict[str, bytes] = {}
    for path in sorted(BASELINE.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(BASELINE).as_posix()
        if rel == POLICY_DIR or rel.startswith(POLICY_DIR + "/"):
            continue
        if rel == "scaffold" or rel.startswith("scaffold/"):
            raise SystemExit(
                f"reset-arm: 基线里出现 {rel} —— v3 基线不许含 scaffold（demo 由任务创建）"
            )
        files[rel] = path.read_bytes()
    expected = BASELINE_FILE_COUNT - len(BASELINE_EXTRA_TEXT)
    if len(files) != expected:
        raise SystemExit(
            f"reset-arm: 期望 sample-project 有 {expected} 个文件，实际 {len(files)}：{sorted(files)}"
        )
    return files


def _target_files() -> dict[str, bytes]:
    """期望的 12 个基线文件（11 + tools/__init__.py）-> {相对路径: 字节}。"""

    files = _sample_files()
    files.update({rel: text.encode("utf-8") for rel, text in BASELINE_EXTRA_TEXT.items()})
    present = [rel for rel in TASK_CREATED if rel in files]
    if present:
        raise SystemExit(
            f"reset-arm: 基线里出现了任务要创建的文件 {present} —— 那等于撤掉 treatment 的激活点"
        )
    if len(files) != BASELINE_FILE_COUNT:
        raise SystemExit(
            f"reset-arm: 期望 {BASELINE_FILE_COUNT} 个基线文件，实际 {len(files)}：{sorted(files)}"
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
    """列出 .policy 之外的文件（相对路径），返回 (files, unreadable_dirs)。

    不可枚举的目录用 os.walk 的 onerror 记成 unreadable，而不是静默当成"没有文件"
    （AGENTS 第 53 条：宁可让读数保持红，也不产生假的空集）。
    """

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
    print(f"  baseline src  : {_display(BASELINE)} (11 files) + tools/__init__.py（基线第 12 个文件）")
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
    """重置目标树并校验 12/12；--dry-run 只打印计划。"""
    parser = argparse.ArgumentParser(
        description="把目标树重置为 A3 v3 的 12 文件基线（sample-project 11 文件 + tools/__init__.py）"
    )
    parser.add_argument(
        "--target", default=str(DEFAULT_TARGET), help="目标树（默认 .tmp/a3b3/task-project）"
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写任何文件")
    args = parser.parse_args(argv)

    files = _target_files()
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
        "schema": "a3b3.reset-arm/2",
        "status": "ok",
        "target": _display(target),
        "baseline_source": [_display(BASELINE), "tools/__init__.py（内嵌，12 个基线文件之一）"],
        "scaffold_copied": False,
        "task_created_files_absent": list(TASK_CREATED),
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
    print(f"[reset-arm] {len(files)}/{len(files)} sha256 verified（不含 scaffold / 不含任务要创建的文件）")
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

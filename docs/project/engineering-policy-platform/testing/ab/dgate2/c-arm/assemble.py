#!/usr/bin/env python3
"""assemble.py - 装配 D 门 2 的 C 臂（不治理对照组）任务树。

C 臂 = 与 A/B 臂同一份 12 文件基线，但**树在受治 project_root 之外**、**不带 --patch**、
**树里没有 .policy**。它回答的是「不治理时模型自己能到几分」，不是「治理失败」。

本脚本做四件事：
  1. 校验 v3 任务包冻结（task-package/manifest.sha256 5/5 + 文件清单自身 sha256）；
  2. 从 examples/dsh/b-plan/sample-project 逐字节复制 11 个文件，再写入第 12 个
     tools/__init__.py（内容内嵌，与 a3-task-v3/reset-arm.py 同源）；
  3. 拒绝任何 .policy：目标树里已存在 .policy => 退出 1；装配后树里出现 .policy => 退出 1；
     目标树落在受治 project_root 之内 => 退出 1（C 臂的定义就是「树在受治项目之外」）；
  4. 逐文件 sha256 校验 12/12 + 组合摘要必须等于 v3 冻结值 4e7c4073…
     （见 examples/dsh/b-plan/a3-task-v3/README.md §1；换基线 = 换构造，必须按变更控制显式改这里）。

与 a3-task-v3/reset-arm.py 的差别只有两点（其余算法相同）：
  * reset-arm.py 保留 .policy；本脚本**拒绝** .policy（C 臂没有受治配置）；
  * reset-arm.py 不管目标树位置；本脚本断言目标树在受治 project_root 之外。

输出（都写在目标树的**父目录**，不写进树——树必须保持 12 文件）：
  * <target 父目录>/<target 名>.manifest.sha256      = 12 行 sha256sum 清单（按 relpath 排序）
  * <target 父目录>/<target 名>.assemble-manifest.json = 目标路径 / 组合摘要 / 前置事实
  stdout 同时打印目标路径、12 行清单与组合摘要。

用法：
    .venv/Scripts/python.exe <repo>/docs/project/engineering-policy-platform/testing/ab/dgate2/c-arm/assemble.py --dry-run
    .venv/Scripts/python.exe <repo>/docs/project/engineering-policy-platform/testing/ab/dgate2/c-arm/assemble.py
    .venv/Scripts/python.exe .../assemble.py --target <树>

退出码：0 = 装配并校验通过（含 --dry-run）；1 = 前置缺失 / 校验失败 / 树里有 .policy。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

#: 12 文件基线的冻结组合摘要（v3 任务包 README §1；算法 = 按 relpath 排序的
#: "<sha256>  <relpath>" 清单文本再取 sha256）。
EXPECTED_MANIFEST_SHA256 = "4e7c4073480c0c4227d4e6f39ae2a04a86b4eba11a6c62d5b8634f86ad924c42"
#: task-package/manifest.sha256 自身的 sha256（v3 README §4，覆盖 task-package/ 的 5 个文件）。
EXPECTED_PACKAGE_MANIFEST_SHA256 = (
    "44d85e7e3bfc58ccfc6deb4bf39e19d056b7e89792c4113e00fd324c86c19217"
)
BASELINE_FILE_COUNT = 12
POLICY_DIR = ".policy"
#: 基线里必须没有的文件：它们是任务要让模型新建的东西，预置进来就等于撤掉激活点。
TASK_CREATED = ("tools/audit_demo.py", "tests/test_audit_demo.py")
#: 第 12 个基线文件（与 reset-arm.py 内嵌内容逐字节一致）。
BASELINE_EXTRA_TEXT = {"tools/__init__.py": '"""项目脚本包（演示与运维脚本）。"""' + "\n"}
#: 宿主沙箱可能把缓存目录 ACL 改成不可删（a3 实测）；它们不是任务文件，按残留记录而不是失败。
CACHE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")
CACHE_DIR_PREFIXES = ("pytest-cache-files-",)
#: 受治 project_root：A/B 臂的受治工作区（只读它的账本；C 臂树必须在它之外）。
DEFAULT_GOVERNED_ROOT = Path("C:/Users/ZNM/Downloads/Comparison-test/Governance")


def _find_repo() -> Path:
    """从脚本位置向上找仓库根（以 examples/dsh/b-plan/sample-project 与 src/policy 为准）。"""

    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "examples" / "dsh" / "b-plan" / "sample-project").is_dir() and (
            candidate / "src" / "policy"
        ).is_dir():
            return candidate
    raise SystemExit(f"assemble: 找不到仓库根（从 {here} 向上找 examples/dsh/b-plan/sample-project）")


REPO = _find_repo()
SAMPLE_PROJECT = REPO / "examples" / "dsh" / "b-plan" / "sample-project"
TASK_PACKAGE = REPO / "examples" / "dsh" / "b-plan" / "a3-task-v3" / "task-package"
DEFAULT_TARGET = REPO / ".tmp" / "dge2" / "c-arm" / "tree"


def _sha256_bytes(payload: bytes) -> str:
    """算一段字节的 sha256。"""

    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    """算一个文件的 sha256（原始字节，不做换行归一化）。"""

    return _sha256_bytes(path.read_bytes())


def _manifest_sha256(files: dict[str, bytes]) -> str:
    """基线组合摘要：与 a3-task-v3/reset-arm.py 的 _manifest_sha256 同一算法。"""

    lines = [f"{_sha256_bytes(payload)}  {rel}" for rel, payload in sorted(files.items())]
    return _sha256_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _display(path: Path) -> str:
    """仓库内路径写成仓库相对 POSIX 形式，仓库外写绝对路径（读数里不留含糊）。"""

    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _resolve_target(raw: str) -> Path:
    """--target 的相对路径按**仓库根**解析（不是按调用者的 cwd，与 reset-arm.py 一致）。"""

    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = REPO / candidate
    return candidate.resolve()


def _is_cache_dir(name: str) -> bool:
    """是不是宿主沙箱可能删不掉的缓存目录。"""

    return name in CACHE_DIR_NAMES or name.startswith(CACHE_DIR_PREFIXES)


def _baseline_files() -> tuple[dict[str, bytes], dict]:
    """期望的 12 个基线文件 -> ({relpath: bytes}, 来源事实)。"""

    if not SAMPLE_PROJECT.is_dir():
        raise SystemExit(f"assemble: 基线树不存在：{_display(SAMPLE_PROJECT)}")
    files: dict[str, bytes] = {}
    source_policy: list[str] = []
    for path in sorted(SAMPLE_PROJECT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(SAMPLE_PROJECT).as_posix()
        if rel == POLICY_DIR or rel.startswith(POLICY_DIR + "/"):
            source_policy.append(rel)
            continue
        if rel == "scaffold" or rel.startswith("scaffold/"):
            raise SystemExit(
                f"assemble: 基线里出现 {rel} —— v3 基线不许含 scaffold（demo 由任务创建）"
            )
        files[rel] = path.read_bytes()
    expected = BASELINE_FILE_COUNT - len(BASELINE_EXTRA_TEXT)
    if len(files) != expected:
        raise SystemExit(
            f"assemble: 期望 sample-project 有 {expected} 个文件，实际 {len(files)}：{sorted(files)}"
        )
    files.update({rel: text.encode("utf-8") for rel, text in BASELINE_EXTRA_TEXT.items()})
    present = [rel for rel in TASK_CREATED if rel in files]
    if present:
        raise SystemExit(
            f"assemble: 基线里出现了任务要创建的文件 {present} —— 那等于撤掉 treatment 的激活点"
        )
    if len(files) != BASELINE_FILE_COUNT:
        raise SystemExit(
            f"assemble: 期望 {BASELINE_FILE_COUNT} 个基线文件，实际 {len(files)}：{sorted(files)}"
        )
    return files, {
        "sample_project": _display(SAMPLE_PROJECT),
        "sample_project_files": expected,
        "embedded_files": sorted(BASELINE_EXTRA_TEXT),
        "source_policy_files_ignored": source_policy,
    }


def _verify_task_package() -> dict:
    """校验 v3 任务包冻结：清单自身 sha256 + 清单里的 5 个文件逐行 sha256。"""

    manifest = TASK_PACKAGE / "manifest.sha256"
    if not TASK_PACKAGE.is_dir() or not manifest.is_file():
        raise SystemExit(f"assemble: 任务包或 manifest.sha256 不存在：{_display(TASK_PACKAGE)}")
    manifest_sha = _sha256_file(manifest)
    problems: list[str] = []
    if manifest_sha != EXPECTED_PACKAGE_MANIFEST_SHA256:
        problems.append(
            f"manifest.sha256 自身 sha256={manifest_sha} != 冻结值 {EXPECTED_PACKAGE_MANIFEST_SHA256}"
        )
    checked: list[dict] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split("  ", 1)
        path = TASK_PACKAGE / name
        if not path.is_file():
            problems.append(f"任务包缺文件：{name}")
            continue
        actual = _sha256_file(path)
        checked.append({"file": name, "sha256": actual, "ok": actual == expected})
        if actual != expected:
            problems.append(f"{name} sha256={actual} != 冻结值 {expected}")
    if len(checked) != 5:
        problems.append(f"清单应有 5 个文件，实际 {len(checked)}")
    if problems:
        raise SystemExit("assemble: 任务包冻结校验失败：\n  " + "\n  ".join(problems))
    return {
        "path": _display(TASK_PACKAGE),
        "manifest_sha256": manifest_sha,
        "files_checked": len(checked),
        "files": checked,
    }


def _containment(target: Path, governed_root: Path, skip: bool) -> dict:
    """判断目标树是否在受治 project_root 之外；返回可写进 manifest 的事实。"""

    root = governed_root.resolve()
    if skip:
        return {
            "governed_root": str(root),
            "status": "skipped",
            "reason": "--skip-governed-root-check 显式跳过了位置检查（只在位置已知可靠时使用）",
        }
    if not root.is_dir():
        raise SystemExit(
            "assemble: 受治 project_root 不存在："
            f"{root}\n  用 --governed-root 指向真实工作区；若确实没有受治项目，"
            "显式加 --skip-governed-root-check 并在 run-manifest 记 status=skipped。"
        )
    inside = target == root or root in target.parents
    if inside:
        raise SystemExit(
            f"assemble: 目标树在受治 project_root 之内：{target} ⊂ {root}\n"
            "  C 臂的定义是「树在受治 project_root 之外」——换一个 --target。"
        )
    return {
        "governed_root": str(root),
        "status": "outside",
        "target": str(target),
    }


def _refuse_policy(target: Path) -> None:
    """目标树里出现 .policy 就直接拒绝（C 臂没有、也不许有受治配置）。"""

    policy = target / POLICY_DIR
    if policy.exists():
        raise SystemExit(
            f"assemble: 目标树里已有 {POLICY_DIR}：{_display(policy)}\n"
            "  C 臂不带 .policy（不打 --patch、不加载策略插件）。请换目标树，"
            "或确认后删掉它再装配——本脚本不会替你保留/改写它。"
        )


def _scan_files(root: Path) -> tuple[list[str], list[str]]:
    """列出树里的全部文件（相对路径）与不可枚举目录；.policy 单独由 _refuse_policy 拦。"""

    files: list[str] = []
    unreadable: list[str] = []

    def onerror(error: OSError) -> None:
        value = getattr(error, "filename", None)
        unreadable.append(str(value) if value else str(error))

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        here = Path(dirpath)
        relative_dir = here.relative_to(root).as_posix()
        if relative_dir == POLICY_DIR or relative_dir.startswith(POLICY_DIR + "/"):
            raise SystemExit(f"assemble: 装配后的树里出现 {POLICY_DIR}：{_display(here)}")
        # 删不掉的缓存目录不算任务文件（单独记 residual_cache_dirs），但不静默：
        # 它们的名字仍在 facts 里出现；这里只把文件清点排除掉。
        dirnames[:] = sorted(name for name in dirnames if not _is_cache_dir(name))
        for name in sorted(filenames):
            rel = f"{relative_dir}/{name}" if relative_dir != "." else name
            files.append(rel)
    return files, unreadable


def _remove_entry(path: Path) -> bool:
    """删除一个文件/目录；宿主 ACL 残留（pytest-cache-files-*）删不掉时返回 False。"""

    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    except (PermissionError, OSError):
        return False


def _plan(files: dict[str, bytes], target: Path, containment: dict, package: dict, dry_run: bool) -> None:
    """打印计划/结果（--dry-run 也走这里，只是不写文件）。"""

    print(f"[assemble] {'DRY-RUN（不写任何文件）' if dry_run else '装配 C 臂任务树'}")
    print(f"  target            : {_display(target)}")
    print(f"  baseline source   : {_display(SAMPLE_PROJECT)} (11 files) + tools/__init__.py（内嵌，第 12 个）")
    print(f"  task package      : {package['path']}（manifest {package['manifest_sha256'][:16]}…，5/5 ok）")
    print(f"  governed root     : {containment['governed_root']}（{containment['status']}）")
    print(f"  .policy           : absent（有就拒绝：C 臂没有受治配置）")
    print(f"  expected files ({len(files)}): {sorted(files)}")
    print(f"  task-created files NOT in baseline: {list(TASK_CREATED)}")
    print(f"  manifest sidecar  : {_display(_manifest_path(target))}")
    print(f"  assemble manifest : {_display(_assemble_manifest_path(target))}")
    print(f"  combined sha256   : {_manifest_sha256(files)}")
    for rel, payload in sorted(files.items()):
        current = target / rel
        if not current.is_file():
            status = "absent"
        elif current.read_bytes() == payload:
            status = "same"
        else:
            status = "differs"
        print(f"    {status:8s} {_sha256_bytes(payload)}  {rel}")


def _manifest_path(target: Path) -> Path:
    """12 行 sha256sum 清单落在目标树**外面**（树必须保持 12 文件）。"""

    return target.parent / f"{target.name}.manifest.sha256"


def _assemble_manifest_path(target: Path) -> Path:
    """装配事实（目标路径 / 组合摘要 / 前置检查）也落在目标树外面。"""

    return target.parent / f"{target.name}.assemble-manifest.json"


def _write_sidecars(target: Path, files: dict[str, bytes], facts: dict) -> None:
    """写 <target>.manifest.sha256 与 <target>.assemble-manifest.json（都在树外）。"""

    lines = [f"{_sha256_bytes(payload)}  {rel}" for rel, payload in sorted(files.items())]
    manifest_path = _manifest_path(target)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    assemble_path = _assemble_manifest_path(target)
    assemble_path.write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    """装配/校验 C 臂树；--dry-run 只打印计划。"""

    parser = argparse.ArgumentParser(
        description="装配 D 门 2 C 臂（不治理）的 12 文件任务树：无 .policy、无 --patch、树在受治 project_root 之外"
    )
    parser.add_argument(
        "--target",
        default=str(DEFAULT_TARGET),
        help="目标树（默认 .tmp/dge2/c-arm/tree；相对路径按仓库根解析）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不写任何文件")
    parser.add_argument(
        "--governed-root",
        default=str(DEFAULT_GOVERNED_ROOT),
        help="受治 project_root（C 臂树必须不在它之内；默认 Comparison-test/Governance）",
    )
    parser.add_argument(
        "--skip-governed-root-check",
        action="store_true",
        help="显式跳过位置检查（只在位置已知可靠时使用；run-manifest 必须记 status=skipped）",
    )
    args = parser.parse_args(argv)

    files, baseline_facts = _baseline_files()
    combined = _manifest_sha256(files)
    if combined != EXPECTED_MANIFEST_SHA256:
        raise SystemExit(
            f"assemble: 基线组合摘要 {combined} != v3 冻结值 {EXPECTED_MANIFEST_SHA256}\n"
            "  基线被改过？换基线 = 换构造，必须按 05 §8 变更控制显式改 EXPECTED_MANIFEST_SHA256。"
        )
    package = _verify_task_package()
    target = _resolve_target(args.target)
    if target.exists() and not target.is_dir():
        raise SystemExit(f"assemble: --target 指向的是一个文件，不是目录：{target}")
    governed_root = Path(args.governed_root)
    if not governed_root.is_absolute():
        governed_root = REPO / governed_root
    containment = _containment(target, governed_root, args.skip_governed_root_check)
    _refuse_policy(target)

    _plan(files, target, containment, package, args.dry_run)
    if args.dry_run:
        print("[assemble] DRY-RUN：未写任何文件；退出码 0")
        return 0

    target.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []
    undeletable: list[str] = []
    residual_cache_dirs: list[str] = []
    for child in sorted(target.iterdir()):
        if child.name == POLICY_DIR:
            raise SystemExit(f"assemble: 目标树里出现 {POLICY_DIR}：{_display(child)}")
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

    # 装配后逐项复核：12/12 逐字节一致、没有 .policy、没有 .policy 之外的多余文件。
    mismatches: list[dict] = []
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
    _refuse_policy(target)
    scanned, unreadable = _scan_files(target)
    extra = sorted(set(scanned) - set(files))
    if mismatches or extra or undeletable:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "target": str(target),
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
        return 1

    verified_manifest = _manifest_sha256({rel: (target / rel).read_bytes() for rel in files})
    facts = {
        "schema": "dge2.c-arm.assemble/1",
        "status": "ok",
        "target": str(target),
        "target_repo_relative": _display(target),
        "baseline": baseline_facts,
        "task_package": package,
        "governed_root": containment,
        "policy_dir_present": False,
        "file_count": len(files),
        "files": [f"{_sha256_bytes(payload)}  {rel}" for rel, payload in sorted(files.items())],
        "combined_manifest_sha256": verified_manifest,
        "expected_manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "dry_run": False,
        "removed_entries": removed,
        "residual_cache_dirs": residual_cache_dirs,
        "residual_note": (
            "宿主沙箱 ACL 残留的缓存目录删不掉；它们不是任务文件，"
            "读数时记 residual，不得当成 12 文件基线的一部分。"
        ),
        "unreadable_dirs": unreadable,
        "mismatches": [],
    }
    _write_sidecars(target, files, facts)
    print(f"[assemble] {len(files)}/{len(files)} sha256 verified；树里没有 {POLICY_DIR}；目标树之外于受治 project_root：{containment['status']}")
    for line in facts["files"]:
        print("  " + line)
    print(f"[assemble] combined sha256 : {verified_manifest}")
    print(f"[assemble] target          : {target}")
    print(f"[assemble] manifest        : {_display(_manifest_path(target))}")
    print(f"[assemble] assemble-manifest: {_display(_assemble_manifest_path(target))}")
    print("ASSEMBLE-C-ARM-JSON: " + json.dumps(facts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

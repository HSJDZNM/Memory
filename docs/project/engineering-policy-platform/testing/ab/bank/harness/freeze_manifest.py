r"""对比实验的**确定性冻结清单**：把「这次实验用了哪些输入」变成可生成、可校验的一行行摘要。

它回答什么
==========

对比实验的可比性只依赖一件事：**两次 run 的输入逐字节相同**。本脚本把一个「实验集」声明
（任务包目录 / 评分器输入目录 / 两臂配置目录 / 首消息文件）展开成一张

    <sha256>  <仓库相对路径>

清单，并给出这张清单的**组合摘要**；`--check` 重新展开、逐行比对。

三条命令
========

    python freeze_manifest.py --set <实验集.json> --manifest <冻结清单.json> --write
    python freeze_manifest.py --set <实验集.json> --manifest <冻结清单.json> --check
    python freeze_manifest.py --set <实验集.json> --manifest <冻结清单.json> --check --strict

实验集声明是 JSON（只用标准库，不解析 YAML）。字段：`schema_version`（"1.0"）、`name`、
`task_packages`（列表）、`scorer_inputs`（列表，可空）、`arm_configs`
（`{"A": 目录, "B": 目录}`）、`first_message`（文件）、`ignore`（可选：通配列表）。
所有路径**必须是仓库相对 POSIX 路径**——绝对路径与 `..` 都是声明错误（退出 2），
因为冻结清单的每一行都要求是仓库相对路径。

载荷自己的版本轴（AGENTS 第 55 条）
=================================

`AB_FREEZE_MANIFEST_SCHEMA_VERSION = "1.0"`——**首次建轴**。加键 / 改语义必须按第 55 条递增，
并把 README、`tests/unit/test_ab_harness.py` 与本文件同批改。

确定性（与 dgate2 `run_manifest.py` 同一条纪律）
====================================================

键排序、UTF-8、LF、单尾换行；**没有时戳、没有 run id、没有绝对路径**（仓库外写
`<outside-workspace>`）；同一份输入两次 `--write` 逐字节相同（用例钉住）。

边界（读之前先看这两条）
======================

1. **双向比对**：`--check` 不只核对清单里的每一行，还核对「根下有没有清单没列的文件」。
   只做单向的话，往任务包里加一个文件也会全绿——那是一条什么都守不住的闸门。
2. **只冻结声明过的目录**：`--write` 不递归到根之外，也不跟随符号链接目录（`os.walk`
   默认不跟）。根之外的输入变了，本清单不知道，也不会假装知道。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _ab_harness_common import (  # noqa: E402
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    HarnessInputError,
    assert_relative,
    combined_digest,
    display_path,
    find_repo_root,
    is_under,
    load_json,
    manifest_lines,
    parse_manifest_lines,
    render_json,
    sha256_file,
    walk_files,
    write_text_lf,
)

#: 冻结清单载荷自己的版本轴；加键 / 改语义必须按 AGENTS 第 55 条递增。
AB_FREEZE_MANIFEST_SCHEMA_VERSION = "1.0"

#: 实验集声明自己的版本轴（与载荷轴独立演进）。
AB_FREEZE_SET_SCHEMA_VERSION = "1.0"

MANIFEST_LINE_FORMAT = "<sha256>  <repo-relative path>"

#: 实验集声明允许出现的键；未知键一律拒绝（AGENTS 第 3 条）。
SET_KEYS = frozenset(
    (
        "schema_version",
        "name",
        "task_packages",
        "scorer_inputs",
        "arm_configs",
        "first_message",
        "ignore",
    )
)

ARMS: Tuple[str, ...] = ("A", "B", "C")

#: 没有声明 `ignore` 时用的默认通配。`--check --strict` 不接受默认值：
#: 「忽略了什么」必须是这份冻结记录自己写下来的事实，不能是一条藏在脚本里的默认。
DEFAULT_IGNORE: Tuple[str, ...] = (
    "**/__pycache__/**",
    "**/*.pyc",
    "**/.pytest_cache/**",
    ".git/**",
)

ROLE_ORDER: Tuple[str, ...] = ("task_package", "scorer_input", "arm_config", "first_message")

#: 输出里点名的问题最多列这么多条，其余只报总数（冻结件可能很多）。
NAME_LIMIT = 10


# --------------------------------------------------------------------------- 实验集声明


def _string_list(value: Any, label: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HarnessInputError("%s 必须是路径列表" % label)
    return [assert_relative(item, "%s[%d]" % (label, index)) for index, item in enumerate(value)]


def parse_set(document: Any) -> Dict[str, Any]:
    """校验实验集声明并归一成内部形状；任何结构问题都是**声明不成立**（退出 2）。"""

    if not isinstance(document, dict):
        raise HarnessInputError("实验集声明的顶层必须是对象")
    unknown = sorted(set(document) - SET_KEYS)
    if unknown:
        raise HarnessInputError(
            "实验集声明里有未知字段 %s —— 加字段必须升 AB_FREEZE_SET_SCHEMA_VERSION" % unknown
        )
    version = document.get("schema_version")
    if version != AB_FREEZE_SET_SCHEMA_VERSION:
        raise HarnessInputError(
            "实验集声明的 schema_version 必须是 %r（读到 %r）"
            % (AB_FREEZE_SET_SCHEMA_VERSION, version)
        )
    name = document.get("name")
    if not isinstance(name, str) or not name.strip():
        raise HarnessInputError("实验集声明缺 name（非空字符串）")
    task_packages = _string_list(document.get("task_packages"), "task_packages")
    if not task_packages:
        raise HarnessInputError("task_packages 不能是空的：没有任务包就没有可比的任务")
    scorer_inputs = _string_list(document.get("scorer_inputs"), "scorer_inputs")
    raw_arms = document.get("arm_configs")
    if not isinstance(raw_arms, dict) or not raw_arms:
        raise HarnessInputError('arm_configs 必须是非空对象（例如 {"A": 目录, "B": 目录}）')
    arm_configs: Dict[str, str] = {}
    for arm in sorted(raw_arms):
        if arm not in ARMS:
            raise HarnessInputError("arm_configs 里的臂名 %r 不在 %s 之内" % (arm, list(ARMS)))
        arm_configs[arm] = assert_relative(raw_arms[arm], "arm_configs.%s" % arm)
    first_message = assert_relative(document.get("first_message"), "first_message")
    raw_ignore = document.get("ignore")
    if raw_ignore is None:
        ignore = list(DEFAULT_IGNORE)
        ignore_source = "default"
    else:
        ignore = _string_list(raw_ignore, "ignore")
        ignore_source = "declared"
    return {
        "name": name.strip(),
        "task_packages": task_packages,
        "scorer_inputs": scorer_inputs,
        "arm_configs": arm_configs,
        "first_message": first_message,
        "ignore": ignore,
        "ignore_source": ignore_source,
    }


def roots_of(spec: Dict[str, Any]) -> List[Dict[str, str]]:
    """声明 → 有序的根列表（同一 role 内按路径排序，臂按 A/B/C 排序）。"""

    roots: List[Dict[str, str]] = []
    for path in sorted(spec["task_packages"]):
        roots.append({"role": "task_package", "path": path, "kind": "dir"})
    for path in sorted(spec["scorer_inputs"]):
        roots.append({"role": "scorer_input", "path": path, "kind": "dir"})
    for arm in sorted(spec["arm_configs"]):
        roots.append(
            {"role": "arm_config", "arm": arm, "path": spec["arm_configs"][arm], "kind": "dir"}
        )
    roots.append({"role": "first_message", "path": spec["first_message"], "kind": "file"})
    return roots


# --------------------------------------------------------------------------- 采集


def collect(
    repo_root: Path,
    roots: Sequence[Dict[str, str]],
    ignore: Sequence[str],
) -> Tuple[Dict[str, str], List[Dict[str, Any]], List[str]]:
    """按根采集 {仓库相对路径: sha256}；返回（条目, 每根计数, 问题）。

    问题只报「事实」（读不到 / 不是目录 / 在仓库外），结构错误在 :func:`parse_set` 就退出了。
    """

    entries: Dict[str, str] = {}
    per_root: List[Dict[str, Any]] = []
    problems: List[str] = []
    for root in roots:
        relative = root["path"]
        full = repo_root / relative
        label = "%s(%s)" % (root["role"], root["arm"]) if root.get("arm") else root["role"]
        if not is_under(full, repo_root):
            problems.append("%s 不在仓库内：%s" % (label, relative))
            continue
        if root["kind"] == "file":
            if not full.is_file():
                problems.append("%s 不是文件或不存在：%s" % (label, relative))
                continue
            entries[relative] = sha256_file(full, relative)
            per_root.append(
                {
                    "role": root["role"],
                    "arm": root.get("arm"),
                    "path": relative,
                    "file_count": 1,
                    "ignored_count": 0,
                }
            )
            continue
        if not full.is_dir():
            problems.append("%s 不是目录或不存在：%s" % (label, relative))
            continue
        files, unreadable, ignored = walk_files(full, ignore, relative)
        for item in unreadable:
            problems.append("%s 有不可枚举目录（%s）" % (label, item))
        for item in files:
            path = relative + "/" + item
            entries[path] = sha256_file(full / item, path)
        per_root.append(
            {
                "role": root["role"],
                "arm": root.get("arm"),
                "path": relative,
                "file_count": len(files),
                "ignored_count": len(ignored),
            }
        )
    return entries, per_root, problems


def _overlap(roots: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    """哪些**根路径**被不止一个声明项列到（重叠不是错误，但必须能被读到）。"""

    seen: Dict[str, List[str]] = {}
    for root in roots:
        key = root["path"]
        role = root["role"] + (":" + root["arm"] if root.get("arm") else "")
        seen.setdefault(key, []).append(role)
    return [
        {"path": path, "roles": sorted(roles)}
        for path, roles in sorted(seen.items())
        if len(roles) > 1
    ]


def _counts(per_root: Sequence[Dict[str, Any]], total: int) -> Dict[str, Any]:
    by_role: Dict[str, int] = {}
    for item in per_root:
        by_role[item["role"]] = by_role.get(item["role"], 0) + item["file_count"]
    return {"by_role": by_role, "total": total}


def build_payload(
    repo_root: Path,
    set_path: Path,
    spec: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """生成冻结清单载荷（不写盘）；返回（载荷, 问题）。"""

    roots = roots_of(spec)
    entries, per_root, problems = collect(repo_root, roots, spec["ignore"])
    lines = manifest_lines(entries.items())
    payload: Dict[str, Any] = {
        "schema_version": AB_FREEZE_MANIFEST_SCHEMA_VERSION,
        "set": {
            "name": spec["name"],
            "path": display_path(set_path, repo_root),
            "sha256": sha256_file(set_path, display_path(set_path, repo_root)),
        },
        "roots": per_root,
        "ignore": {"globs": list(spec["ignore"]), "source": spec["ignore_source"]},
        "manifest": {
            "line_format": MANIFEST_LINE_FORMAT,
            "count": len(lines),
            "combined_digest": combined_digest(lines),
            "lines": lines,
        },
        "counts": _counts(per_root, len(entries)),
        "overlap": _overlap(roots),
    }
    if not lines:
        problems.append("清单是空的：没有任何文件被冻结，这张清单证明不了任何事")
    return payload, problems


# --------------------------------------------------------------------------- 校验


def _name_list(items: Sequence[Any]) -> str:
    """点名问题对象；超过 NAME_LIMIT 只报前几条 + 总数（冻结件可能成百上千）。"""

    names = [str(item) for item in items]
    if len(names) <= NAME_LIMIT:
        return ", ".join(names)
    return "%s, …（共 %d 个）" % (", ".join(names[:NAME_LIMIT]), len(names))


def validate_payload_shape(payload: Any) -> Tuple[Dict[str, Any], List[str]]:
    """判载荷结构与版本；版本不认识就直接拒收。返回（归一后的载荷, 问题）。"""

    problems: List[str] = []
    if not isinstance(payload, dict):
        return {}, ["冻结清单的顶层不是对象"]
    required = ("schema_version", "set", "roots", "ignore", "manifest", "counts")
    missing = [key for key in required if key not in payload]
    if missing:
        return {}, ["冻结清单缺字段 %s" % missing]
    extra = sorted(set(payload) - set(required) - {"overlap"})
    if extra:
        problems.append("冻结清单有未知字段 %s（加键必须升 AB_FREEZE_MANIFEST_SCHEMA_VERSION）" % extra)
    version = payload.get("schema_version")
    if version != AB_FREEZE_MANIFEST_SCHEMA_VERSION:
        problems.append(
            "schema_version 必须是 %r（读到 %r）：消费方看不懂必须拒收"
            % (AB_FREEZE_MANIFEST_SCHEMA_VERSION, version)
        )
        return {}, problems
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict):
        return {}, problems + ["manifest 段不是对象"]
    for key in ("lines", "count", "combined_digest"):
        if key not in manifest:
            problems.append("manifest 段缺 %s" % key)
    if problems:
        return {}, problems
    if manifest.get("line_format") not in (None, MANIFEST_LINE_FORMAT):
        problems.append("manifest.line_format 必须是 %r" % MANIFEST_LINE_FORMAT)
    if not isinstance(manifest["lines"], list) or not all(
        isinstance(item, str) for item in manifest["lines"]
    ):
        problems.append("manifest.lines 不是字符串列表")
    ignore = payload.get("ignore")
    if not isinstance(ignore, dict) or not isinstance(ignore.get("globs"), list):
        problems.append("ignore 段必须是 {globs: [...]}")
    if not isinstance(payload.get("roots"), list):
        problems.append("roots 不是列表")
    if problems:
        return {}, problems
    return payload, problems


def verify_payload(
    repo_root: Path,
    payload: Dict[str, Any],
    *,
    set_path: Optional[Path],
    strict: bool,
) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """重算并**双向**比对；返回（问题, 原因码, 读数）。"""

    problems: List[str] = []
    reasons: List[str] = []
    manifest = payload["manifest"]
    ignore = [str(item) for item in payload["ignore"]["globs"]]

    roots: List[Dict[str, str]] = []
    for index, root in enumerate(payload["roots"]):
        if not isinstance(root, dict):
            problems.append("roots[%d] 不是对象" % index)
            reasons.append("manifest_invalid")
            continue
        role = root.get("role")
        if role not in ROLE_ORDER:
            problems.append("roots[%d].role 未知：%r" % (index, role))
            reasons.append("manifest_invalid")
            continue
        try:
            relative = assert_relative(root.get("path"), "roots[%d].path" % index)
        except HarnessInputError as error:
            problems.append(str(error))
            reasons.append("manifest_invalid")
            continue
        kind = "file" if role == "first_message" else "dir"
        entry = {"role": str(role), "path": relative, "kind": kind}
        if role == "arm_config":
            arm = root.get("arm")
            if arm not in ARMS:
                problems.append("roots[%d].arm 未知：%r" % (index, arm))
                reasons.append("manifest_invalid")
                continue
            entry["arm"] = str(arm)
        roots.append(entry)
    if problems:
        return problems, sorted(set(reasons)) or ["manifest_invalid"], {}

    recorded, parse_problems = parse_manifest_lines(manifest["lines"])
    for problem in parse_problems:
        problems.append("manifest.lines %s" % problem)
        reasons.append("manifest_invalid")
    actual, per_root, collect_problems = collect(repo_root, roots, ignore)
    for problem in collect_problems:
        problems.append(problem)
        reasons.append("unreadable" if "不可枚举" in problem else "root_missing")

    missing = sorted(set(recorded) - set(actual))
    extra = sorted(set(actual) - set(recorded))
    if missing:
        problems.append("清单里有、磁盘上没有的文件：%s" % _name_list(missing))
        reasons.append("missing")
    if extra:
        problems.append("磁盘上有、清单里没有的文件：%s" % _name_list(extra))
        reasons.append("extra")
    drift = sorted(path for path in set(recorded) & set(actual) if recorded[path] != actual[path])
    if drift:
        problems.append("sha256 漂移：%s" % _name_list(drift))
        reasons.append("sha256_mismatch")

    recomputed_lines = manifest_lines(actual.items())
    recomputed_digest = combined_digest(recomputed_lines)
    if manifest.get("combined_digest") != recomputed_digest:
        problems.append(
            "组合摘要不符：记录 %r / 重算 %r" % (manifest.get("combined_digest"), recomputed_digest)
        )
        reasons.append("combined_digest_mismatch")
    if manifest.get("count") != len(recorded):
        problems.append(
            "manifest.count 与 lines 条数不一致（%r vs %d）"
            % (manifest.get("count"), len(recorded))
        )
        reasons.append("manifest_invalid")

    set_checked = False
    if set_path is not None:
        set_checked = True
        actual_set = sha256_file(set_path, display_path(set_path, repo_root))
        recorded_set = (payload.get("set") or {}).get("sha256")
        if recorded_set != actual_set:
            problems.append("实验集声明本身漂移：记录 %r / 现在 %r" % (recorded_set, actual_set))
            reasons.append("set_drift")

    if strict:
        if payload["ignore"].get("source") != "declared":
            problems.append(
                "严格模式要求实验集声明里显式写出 ignore：默认忽略是脚本里的默认，"
                "不是这份冻结记录写下的事实"
            )
            reasons.append("ignore_defaulted")
        if not set_checked:
            problems.append("严格模式必须同时给 --set：否则无法证明被冻结的就是声明的那些输入")
            reasons.append("set_unchecked")
        empty_roots = [item["path"] for item in per_root if item["file_count"] == 0]
        if empty_roots:
            problems.append("这些根一个文件都没冻到：%s" % _name_list(empty_roots))
            reasons.append("empty_root")

    readings = {
        "recorded_count": len(recorded),
        "actual_count": len(actual),
        "recomputed_digest": recomputed_digest,
        "set_checked": set_checked,
        "strict": strict,
        "roots": per_root,
    }
    return problems, sorted(set(reasons)), readings


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "生成 / 校验对比实验输入的确定性冻结清单"
            "（<sha256>  <仓库相对路径> 行 + 组合摘要）"
        )
    )
    parser.add_argument("--set", required=True, dest="set_file", help="实验集声明（JSON）")
    parser.add_argument(
        "--manifest",
        required=True,
        dest="manifest_file",
        help="冻结清单载荷的路径（--write 写它，--check 读它）",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="生成并写盘")
    mode.add_argument("--check", action="store_true", help="重新展开并双向比对")
    parser.add_argument("--strict", action="store_true", help="（仅 --check）不放宽任何一条")
    parser.add_argument("--repo-root", default=None, help="仓库根（默认从脚本位置向上找 .git）")
    return parser


def _resolve(raw: str, repo_root: Path) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if args.strict and not args.check:
        print("freeze-manifest: --strict 只能与 --check 一起用", file=sys.stderr)
        return EXIT_USAGE
    try:
        repo_root = find_repo_root(_HERE, Path(args.repo_root) if args.repo_root else None)
        set_path = _resolve(args.set_file, repo_root)
        manifest_path = _resolve(args.manifest_file, repo_root)
        if args.write:
            return _write(repo_root, set_path, manifest_path)
        return _check(repo_root, set_path, manifest_path, strict=args.strict)
    except HarnessInputError as error:
        print("freeze-manifest: %s" % error, file=sys.stderr)
        return error.exit_code


def _write(repo_root: Path, set_path: Path, manifest_path: Path) -> int:
    document = load_json(set_path, display_path(set_path, repo_root), exit_code=EXIT_USAGE)
    spec = parse_set(document)
    for root in roots_of(spec):
        if root["kind"] == "dir" and is_under(manifest_path, repo_root / root["path"]):
            print(
                "freeze-manifest: --manifest 不能落在被冻结的根里（%s）：写盘会改变它自己的摘要"
                % root["path"],
                file=sys.stderr,
            )
            return EXIT_USAGE
    if manifest_path == set_path:
        print("freeze-manifest: --manifest 与 --set 不能是同一个文件", file=sys.stderr)
        return EXIT_USAGE
    payload, problems = build_payload(repo_root, set_path, spec)
    if problems:
        for problem in problems:
            print("PROBLEM: %s" % problem, file=sys.stderr)
        print(
            "RESULT: FAIL（%d 条问题；**没有写盘**——半张清单比没有更危险）" % len(problems),
            file=sys.stderr,
        )
        return EXIT_INVALID
    write_text_lf(manifest_path, render_json(payload))
    manifest = payload["manifest"]
    print(
        "freeze-manifest: wrote %s entries=%d combined_digest=%s"
        % (display_path(manifest_path, repo_root), manifest["count"], manifest["combined_digest"])
    )
    return EXIT_OK


def _check(repo_root: Path, set_path: Path, manifest_path: Path, *, strict: bool) -> int:
    label = display_path(manifest_path, repo_root)
    payload = load_json(manifest_path, label, exit_code=EXIT_INVALID)
    payload, problems = validate_payload_shape(payload)
    reasons: List[str] = ["manifest_invalid"] if problems else []
    readings: Dict[str, Any] = {}
    if not problems:
        problems, reasons, readings = verify_payload(
            repo_root, payload, set_path=set_path, strict=strict
        )
    for problem in problems:
        print("PROBLEM: %s" % problem)
    if problems:
        print("RESULT: FAIL（%s）" % (", ".join(reasons) if reasons else "unknown"))
        return EXIT_INVALID
    print(
        "RESULT: PASS entries=%d combined_digest=%s strict=%d set_checked=%d"
        % (
            readings["recorded_count"],
            readings["recomputed_digest"],
            int(strict),
            int(readings["set_checked"]),
        )
    )
    return EXIT_OK


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(argv)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

r"""D 门 2 的 run-manifest 生成器与校验器（18 字段契约）。

它回答什么
==========

`scorer.yaml` 的 `run_manifest_fields` 规定了每次 run 必须记下的 18 个字段；本脚本把这句话
变成**可生成、可校验**的载荷：

    python run_manifest.py --arm A --out .tmp/dgate2/run-manifest-A.json
    python run_manifest.py --check .tmp/dgate2/run-manifest-A.json [--strict]

生成模式**现场计算**每个字段（git HEAD / 工作树、scorer 清单、任务包清单、configs/after、
判据来源、规则集身份、hidden 摘要、参考树、三臂事实、三维读数、四个人工项），把结果写成
确定性 JSON。校验模式重算**冻结类摘要字段**并逐项比对，任何不符退出 1；清单结构不合法
（缺字段 / 多字段 / 状态非法 / 摘要不符）同样退出 1；用法错误或读不到声明退出 2。

三种字段状态（与 AGENTS 第 51 条同一条纪律）
==========================================

- `recorded`：本次 run 已经记下这个事实；
- `pending`：这次还拿不到（例如开跑前的清单里还没有读数）——**pending 不是通过**，
  `--strict` 下不允许任何 pending；
- `not_applicable`：人工明确裁定不适用（目前只有 H4 的「两次读数相同」一种形态）。

载荷自己的版本轴（AGENTS 第 55 条）
=================================

`RUN_MANIFEST_SCHEMA_VERSION = "1.1"`——1.0 首次建轴（2026-10-19，D 门 2 前置）；
**1.1 = 新增第 18 个字段 `platform_generation`**（2026-10-21 实验冻结裁决：宿主 / 沙箱 /
每臂配置与审批摘要 / 批次代际 / 模型与起点事实一次并入，同批评分器 version 2→3）。
18 个字段的 id 与 `scorer/scorer.yaml` 的 `run_manifest_fields` 逐字一致；加字段、改状态
语义都按 AGENTS 第 55 条显式递增版本号，并同批改本文件、README 与测试。

确定性（与 `policy.check` 的 `--json` 包装层同一条纪律）
=========================================================

键排序、UTF-8、LF、单尾换行；没有工具生成的时戳 / run id，没有绝对路径（仓库外一律写
`<outside-workspace>`）。同一输入两次生成逐字节相同；会随**生成动作本身**变化的是
`worktree_clean`——它先排除 `--out` 自身，且记录的是**写盘之前**的工作树状态。

边界（读之前先看这三条）
======================

1. **不替人判**：H1–H4 的人工项由 `--human-items` 原样记录；本脚本只检查形状，不评价
   「作者是否独立」「抽样是否充分」这类内容质量。
2. **参考树是读数对象，不冻结**（04-open-work 5.79②）：`reference_tree` 只在给了
   `--reference-tree` 时算一次，`--check` **不**重算它（树可能已经删了，且它不在
   `manifest.sha256` 里）。
3. **run-record 只做结构校验**：`--run-record` 至少要有 `schema_version` / `arm` /
   `dimensions{T,C,A}`；分数怎么算、读数怎么来不由本脚本复算。

它不替代 `scorer/make_manifest.py`：清单的生成与冻结门禁仍在那边；本脚本是它的消费者
（`manifest_check` 字段直接跑 `make_manifest.py --check --strict` 并记录结果）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: run-manifest 载荷自己的版本轴；加键 / 改语义必须按 AGENTS 第 55 条递增。
RUN_MANIFEST_SCHEMA_VERSION = "1.1"

#: 18 个字段 id，顺序与 scorer/scorer.yaml 的 run_manifest_fields.items 逐字一致。
RUN_MANIFEST_FIELDS: Tuple[str, ...] = (
    "head",
    "worktree_clean",
    "scorer_manifest_sha256",
    "manifest_check",
    "task_package_manifest_sha256",
    "first_message_sha256",
    "configs_after_sha256_txt",
    "criterion_sources",
    "rule_set_identity",
    "hidden_digests",
    "reference_tree",
    "arms",
    "readings",
    "hidden_author",
    "bypass_sampling",
    "a4_review",
    "nondeterminism_ruling",
    "platform_generation",
)

#: 只能由人记录的四个字段（scorer/README.md §6 的 H1–H4）。
HUMAN_FIELD_IDS: Tuple[str, ...] = (
    "hidden_author",
    "bypass_sampling",
    "a4_review",
    "nondeterminism_ruling",
)

FIELD_STATUSES: Tuple[str, ...] = ("recorded", "pending", "not_applicable")
ARMS: Tuple[str, ...] = ("A", "B", "C")
LAUNCHER_SANDBOXES: Tuple[str, ...] = ("workspace-write", "danger-full-access", "unknown")

#: platform_generation（1.1 起）的闭集与键集合：输入里的未知键一律拒收（AGENTS 55）。
PLATFORM_HOST_ENTRIES: Tuple[str, ...] = ("headless", "desktop")
PLATFORM_DSH_SOURCES: Tuple[str, ...] = ("app_bundled", "path_cli")
SANDBOX_MODES: Tuple[str, ...] = ("workspace-write", "danger-full-access", "unknown")
SANDBOX_STATES: Tuple[str, ...] = ("restricted", "unrestricted", "unknown")
TOKEN_ROOTS: Tuple[str, ...] = (
    "<install>",
    "<npm-global>",
    "<governed>",
    "<DSH_HOME>",
    "<temp>",
    "<workspace>",
    "<outside-workspace>",
)
PLATFORM_KEYS: Tuple[str, ...] = (
    "host",
    "start",
    "run",
    "declarations",
    "batch_ledger",
    "audit_schema_version",
    "pre_evidence",
    "timeouts",
    "model",
    "observations",
)
_PLATFORM_HOST_KEYS: Tuple[str, ...] = (
    "entry",
    "dsh_runtime",
    "dsh_source",
    "dsh_entry",
    "profile",
    "session_sandbox",
    "file_policy",
    "sandbox",
)
_PLATFORM_START_KEYS: Tuple[str, ...] = ("head", "worktree_clean")
_PLATFORM_RUN_KEYS: Tuple[str, ...] = ("serial", "ci_local_lock_held", "concurrent_sessions")
_PLATFORM_DECLARATION_KEYS: Tuple[str, ...] = (
    "adapter_config",
    "registry",
    "approval",
    "test_layout",
)
_PLATFORM_ADAPTER_KEYS: Tuple[str, ...] = (
    "path",
    "sha256",
    "agent_version",
    "into_decision",
    "max_targets",
)
_PLATFORM_REGISTRY_KEYS: Tuple[str, ...] = (
    "path",
    "sha256",
    "registry_schema_version",
    "approved_path",
    "approved_sha256",
    "approved_reviewed_by",
    "approved_reviewed_at",
)
_PLATFORM_APPROVAL_KEYS: Tuple[str, ...] = ("path", "sha256")
_PLATFORM_TEST_LAYOUT_KEYS: Tuple[str, ...] = ("path", "sha256")
_PLATFORM_BATCH_KEYS: Tuple[str, ...] = (
    "enabled",
    "into_decision",
    "max_targets",
    "ttl_hours",
    "schema_version",
)
_PLATFORM_PRE_EVIDENCE_KEYS: Tuple[str, ...] = ("enabled", "timeout_ms")
_PLATFORM_TIMEOUT_KEYS: Tuple[str, ...] = ("tool_timeout_ms", "hooks_timeout_ms")
_PLATFORM_MODEL_KEYS: Tuple[str, ...] = ("id", "params", "first_message_sha256")
_PLATFORM_OBSERVATION_KEYS: Tuple[str, ...] = ("batch",)
_PLATFORM_BATCH_OBSERVATION_KEYS: Tuple[str, ...] = (
    "decisions",
    "with_batch",
    "settled",
    "truncated",
    "unreadable",
    "degraded",
)
_VERSION_TEXT = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[-+][0-9A-Za-z._-]+)?$")

DGATE2_REL = "docs/project/engineering-policy-platform/testing/ab/dgate2"
SCORER_REL = DGATE2_REL + "/scorer"
HIDDEN_REL = DGATE2_REL + "/hidden"
CONFIGS_AFTER_REL = DGATE2_REL + "/configs/after"
TASK_PACKAGE_REL = "examples/dsh/b-plan/a3-task-v3/task-package"
TREATMENT_REL = "docs/project/engineering-policy-platform/readings/2026-10-19-D-gate2-treatment.md"
OPEN_WORK_REL = "docs/project/engineering-policy-platform/04-open-work.md"
IMPLEMENTATION_PLAN_REL = "docs/project/engineering-policy-platform/05-implementation-plan.md"

HIDDEN_FILES: Tuple[Tuple[str, str], ...] = (
    ("test_acceptance_dgate2.py", HIDDEN_REL + "/test_acceptance_dgate2.py"),
    ("runner.py", HIDDEN_REL + "/runner.py"),
)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_ANY = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_IDENTITY = re.compile(r"^sha256:[0-9a-f]{64}$")
_WINDOWS_ABS = re.compile(r"^[A-Za-z]:[\\/]")

_SKIP_DIR_NAMES = frozenset(("__pycache__", ".pytest_cache"))
_SKIP_SUFFIXES = (".pyc",)


class ManifestInputError(Exception):
    """读不到声明 / 用法错误：携带退出码 2（生成与校验共用）。"""

    def __init__(self, message: str, exit_code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# --------------------------------------------------------------------------- 基础工具


def _find_repo_root(start: Path) -> Path:
    """从脚本位置向上找仓库根（含 .git）。找不到是用法错误，不猜一个路径。"""

    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise ManifestInputError("找不到仓库根（从脚本位置向上没有 .git）")


def _display_path(path: Path, repo_root: Path) -> str:
    """仓库内写仓库相对 POSIX 路径，仓库外写 <outside-workspace>（载荷不出现绝对路径）。"""

    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return "<outside-workspace>"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path, label: str) -> str:
    """sha256(原始字节)；读不到就失败关闭（label 是仓库相对说明，不是绝对路径）。"""

    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError as error:
        raise ManifestInputError(
            "%s 读不到（%s）" % (label, error.strerror or type(error).__name__)
        ) from error
    return hasher.hexdigest()


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise ManifestInputError(
            "%s 读不到（%s）" % (label, error.strerror or type(error).__name__)
        ) from error
    except UnicodeDecodeError as error:
        raise ManifestInputError("%s 不是 UTF-8 文本（%s）" % (label, error)) from error


def _reject_constant(value: str) -> Any:
    raise ValueError("非标准 JSON 常量 %s" % value)


def _load_json(path: Path, label: str) -> Any:
    text = _read_text(path, label)
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except ValueError as error:
        raise ManifestInputError("%s 不是合法 JSON（%s）" % (label, error)) from error


def _render_json(payload: Any) -> str:
    """确定性载荷：键排序 + 固定缩进 + 单尾换行；写盘用 UTF-8 字节，避免平台换行。"""

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _value_digest(value: Any) -> str:
    """比较两个 JSON 值时只打摘要，避免把（可能含路径的）原值抄进输出。"""

    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + _sha256_bytes(canonical.encode("utf-8"))[:12]


def _is_safe_relative(path: str) -> bool:
    """仓库相对 POSIX 路径的形状检查：不绝对、不带 ..、不用反斜杠。"""

    if not path or path.startswith(("/", "\\")) or _WINDOWS_ABS.match(path):
        return False
    if "\\" in path:
        return False
    parts = path.split("/")
    return all(part not in ("", ".", "..") for part in parts)


def _absolute_path_in(value: Any) -> Optional[str]:
    """递归找第一个绝对路径（盘符 / UNC / 以斜杠开头），返回所在形态。"""

    if isinstance(value, str):
        if value.startswith(("/", "\\")) or _WINDOWS_ABS.match(value):
            return value
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and (
                key.startswith(("/", "\\")) or _WINDOWS_ABS.match(key)
            ):
                return key
            found = _absolute_path_in(item)
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        for item in value:
            found = _absolute_path_in(item)
            if found is not None:
                return found
        return None
    return None


def _safe_text(value: Any) -> str:
    """把可能含绝对路径的值转成可打印文本：只决定显示，不改变记录。"""

    if isinstance(value, str):
        if value.startswith(("/", "\\")) or _WINDOWS_ABS.match(value):
            return "<outside-workspace>"
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _sanitize_message(message: str, repo_root: Path) -> str:
    """输出纪律：绝对路径换成 <outside-workspace>，仓库根换成 <repo>。"""

    text = message
    repo_text = str(repo_root)
    for needle in {repo_text, repo_text.replace("\\", "/"), repo_text.replace("/", "\\")}:
        if needle:
            text = text.replace(needle, "<repo>")
    text = re.sub(r"(?<![\w])[A-Za-z]:[\\/][^\s，；）】)]*", "<outside-workspace>", text)
    text = re.sub(r"(?<![\w])\\\\[^\s，；）】)]*", "<outside-workspace>", text)
    text = re.sub(r"(?<![\w])/(?:[^\s，；）】)]+)", "<outside-workspace>", text)
    return text


def _parse_sha256_manifest(text: str) -> Tuple[Dict[str, str], List[str]]:
    """解析 `<sha256>  <path>` 清单；返回（路径 → 摘要, 格式错误行号）。"""

    entries: Dict[str, str] = {}
    problems: List[str] = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line:
            continue
        digest, separator, path = line.partition("  ")
        if separator != "  " or not _HEX64.match(digest) or not path:
            problems.append("第 %d 行不是「<sha256>  <path>」" % number)
            continue
        if path in entries:
            problems.append("第 %d 行的路径重复" % number)
            continue
        entries[path] = digest
    return entries, problems


def _read_sha256_manifest(repo_root: Path, file_rel: str) -> Tuple[Dict[str, str], List[str], str]:
    """读一份清单文件：返回（条目, 格式问题, 清单文件自身的 sha256）。"""

    path = repo_root / file_rel
    digest = _sha256_file(path, file_rel)
    entries, problems = _parse_sha256_manifest(_read_text(path, file_rel))
    return entries, problems, digest


def _verify_declared_files(
    directory: Path,
    entries: Dict[str, str],
    label: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """逐行核对清单里的文件；返回（ok 路径, bad 条目）。缺失 / 不安全路径都算 bad。"""

    files_ok: List[str] = []
    files_bad: List[Dict[str, Any]] = []
    for relative in sorted(entries):
        expected = entries[relative]
        if not _is_safe_relative(relative):
            files_bad.append(
                {
                    "path": relative,
                    "expected": expected,
                    "actual": None,
                    "reason": "unsafe_relative_path",
                }
            )
            continue
        full = directory / relative
        if not full.is_file():
            files_bad.append(
                {"path": relative, "expected": expected, "actual": None, "reason": "missing"}
            )
            continue
        try:
            actual = _sha256_file(full, label + "/" + relative)
        except ManifestInputError:
            files_bad.append(
                {"path": relative, "expected": expected, "actual": None, "reason": "unreadable"}
            )
            continue
        if actual != expected:
            files_bad.append(
                {
                    "path": relative,
                    "expected": expected,
                    "actual": actual,
                    "reason": "sha256_mismatch",
                }
            )
        else:
            files_ok.append(relative)
    return files_ok, files_bad


# --------------------------------------------------------------------------- git 与外部命令


def _run_git(repo_root: Path, arguments: Sequence[str], label: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ManifestInputError("%s 跑不成（%s）" % (label, type(error).__name__)) from error
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        tail = detail[-1] if detail else "无 stderr"
        raise ManifestInputError(
            "%s 退出码 %d（%s）"
            % (label, completed.returncode, _sanitize_message(tail, repo_root))
        )
    return completed.stdout or ""


def _git_head(repo_root: Path) -> str:
    head = _run_git(repo_root, ["rev-parse", "HEAD"], "git rev-parse HEAD").strip()
    if not _HEX_ANY.match(head):
        raise ManifestInputError("git rev-parse HEAD 没有给出 40/64 位十六进制摘要")
    return head


def _porcelain_path(line: str) -> str:
    """从 porcelain v1 行里取路径（用于排除 --out 自身这一条）。"""

    candidate = line[3:] if len(line) > 3 else ""
    if candidate.startswith('"') and candidate.endswith('"') and len(candidate) >= 2:
        candidate = candidate[1:-1]
    if " -> " in candidate:
        candidate = candidate.split(" -> ", 1)[1]
    return candidate


def _git_porcelain(repo_root: Path) -> List[str]:
    output = _run_git(repo_root, ["status", "--porcelain"], "git status --porcelain")
    return sorted(line for line in output.split("\n") if line)


def _run_make_manifest(repo_root: Path) -> Tuple[Dict[str, Any], List[str]]:
    """实时跑 scorer/make_manifest.py --check --strict，取退出码与最后一行 RESULT。"""

    script = repo_root / SCORER_REL / "make_manifest.py"
    if not script.is_file():
        raise ManifestInputError("scorer/make_manifest.py 不存在（冻结包不完整）")
    try:
        completed = subprocess.run(
            [sys.executable, str(script), "--check", "--strict"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ManifestInputError(
            "make_manifest.py --check --strict 跑不成（%s）" % type(error).__name__
        ) from error
    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    result_lines = [line for line in lines if line.startswith("RESULT:")]
    result_line = result_lines[-1] if result_lines else (lines[-1] if lines else "")
    result_line = _sanitize_message(result_line, repo_root)
    value = {"exit_code": completed.returncode, "strict": True, "result_line": result_line}
    problems: List[str] = []
    if completed.returncode != 0:
        problems.append(
            "manifest_check: make_manifest.py --check --strict 退出码 %d（%s）"
            % (completed.returncode, result_line or "无输出")
        )
    if not result_lines:
        problems.append("manifest_check: make_manifest.py 输出里没有 RESULT 行")
    return value, problems


# --------------------------------------------------------------------------- 字段计算


def _load_scorer(repo_root: Path) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - 仓库 .venv 里一定有 PyYAML
        raise ManifestInputError("需要 PyYAML（用仓库的 .venv/Scripts/python.exe 跑）") from error
    path = repo_root / SCORER_REL / "scorer.yaml"
    try:
        document = yaml.safe_load(_read_text(path, SCORER_REL + "/scorer.yaml"))
    except yaml.YAMLError as error:
        raise ManifestInputError("scorer/scorer.yaml 不是合法 YAML（%s）" % error) from error
    if not isinstance(document, dict):
        raise ManifestInputError("scorer/scorer.yaml 顶层不是对象")
    return document


def _verify_field_contract(scorer: Dict[str, Any]) -> None:
    """17 个 id 必须与 scorer.yaml 的 run_manifest_fields 逐字一致（顺序也比）。"""

    section = scorer.get("run_manifest_fields")
    items = section.get("items") if isinstance(section, dict) else None
    if not isinstance(items, list):
        raise ManifestInputError("scorer.yaml 的 run_manifest_fields.items 读不出来")
    ids: List[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or "id" not in item:
            raise ManifestInputError("scorer.yaml 的 run_manifest_fields.items[%d] 没有 id" % index)
        ids.append(str(item["id"]))
    if ids != list(RUN_MANIFEST_FIELDS):
        missing = [item for item in RUN_MANIFEST_FIELDS if item not in ids]
        extra = [item for item in ids if item not in RUN_MANIFEST_FIELDS]
        raise ManifestInputError(
            "scorer.yaml 的 run_manifest_fields 与脚本的 18 字段不一致"
            "（missing=%s / extra=%s）" % (missing, extra)
        )


def _compute_scorer_manifest_sha256(repo_root: Path) -> str:
    return _sha256_file(repo_root / SCORER_REL / "manifest.sha256", SCORER_REL + "/manifest.sha256")


def _compute_task_package(repo_root: Path) -> Tuple[Dict[str, Any], List[str]]:
    directory = repo_root / TASK_PACKAGE_REL
    manifest_rel = TASK_PACKAGE_REL + "/manifest.sha256"
    entries, malformed, digest = _read_sha256_manifest(repo_root, manifest_rel)
    problems = ["task_package_manifest_sha256: 清单格式问题（%s）" % problem for problem in malformed]
    files_ok, files_bad = _verify_declared_files(directory, entries, TASK_PACKAGE_REL)
    if not entries:
        problems.append("task_package_manifest_sha256: 任务包清单是空的")
    if files_bad:
        problems.append(
            "task_package_manifest_sha256: %d 个文件与清单不符（%s）"
            % (len(files_bad), ", ".join(str(item["path"]) for item in files_bad))
        )
    value = {
        "sha256": digest,
        "declared_count": len(entries),
        "files_ok": sorted(files_ok),
        "files_bad": files_bad,
    }
    return value, problems


def _compute_first_message(
    repo_root: Path, task_entries: Dict[str, str]
) -> Tuple[Dict[str, Any], List[str]]:
    relative = "first-message.txt"
    path = repo_root / TASK_PACKAGE_REL / relative
    actual = _sha256_file(path, TASK_PACKAGE_REL + "/" + relative)
    expected = task_entries.get(relative)
    matches = expected == actual
    problems: List[str] = []
    if expected is None:
        problems.append("first_message_sha256: 任务包清单里没有 %s 这一行" % relative)
    elif not matches:
        problems.append("first_message_sha256: 与任务包清单记录不符")
    value = {"sha256": actual, "manifest_sha256": expected, "matches_manifest": matches}
    return value, problems


def _compute_configs_after(repo_root: Path) -> Tuple[Dict[str, Any], List[str]]:
    directory = repo_root / CONFIGS_AFTER_REL
    manifest_rel = CONFIGS_AFTER_REL + "/sha256.txt"
    entries, malformed, digest = _read_sha256_manifest(repo_root, manifest_rel)
    problems = ["configs_after_sha256_txt: 清单格式问题（%s）" % problem for problem in malformed]
    files_ok, files_bad = _verify_declared_files(directory, entries, CONFIGS_AFTER_REL)
    if not entries:
        problems.append("configs_after_sha256_txt: configs/after/sha256.txt 是空的")
    if files_bad:
        problems.append(
            "configs_after_sha256_txt: %d 个文件与 sha256.txt 不符（%s）"
            % (len(files_bad), ", ".join(str(item["path"]) for item in files_bad))
        )
    value = {
        "sha256": digest,
        "declared_count": len(entries),
        "files_ok": sorted(files_ok),
        "files_bad": files_bad,
    }
    return value, problems


def _compute_criterion_sources(
    repo_root: Path, scorer: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[str]]:
    freeze = scorer.get("freeze")
    sources = freeze.get("criterion_sources") if isinstance(freeze, dict) else None
    if not isinstance(sources, list):
        raise ManifestInputError("scorer.yaml 的 freeze.criterion_sources 读不出来")
    by_path: Dict[str, Dict[str, Any]] = {}
    for item in sources:
        if isinstance(item, dict) and "path" in item:
            by_path[str(item["path"])] = item
    required = (TREATMENT_REL, OPEN_WORK_REL, IMPLEMENTATION_PLAN_REL)
    missing = [relative for relative in required if relative not in by_path]
    if missing:
        raise ManifestInputError("scorer.yaml 的 freeze.criterion_sources 缺少 %s" % missing)
    frozen = by_path[TREATMENT_REL].get("sha256")
    if not isinstance(frozen, str) or not _HEX64.match(frozen):
        raise ManifestInputError("scorer.yaml 没有给出判据原文（memo）的冻结 sha256")
    treatment = _sha256_file(repo_root / TREATMENT_REL, TREATMENT_REL)
    open_work = _sha256_file(repo_root / OPEN_WORK_REL, OPEN_WORK_REL)
    implementation_plan = _sha256_file(repo_root / IMPLEMENTATION_PLAN_REL, IMPLEMENTATION_PLAN_REL)
    matches_frozen = treatment == frozen
    problems: List[str] = []
    if not matches_frozen:
        problems.append("criterion_sources: 判据原文（memo）的 sha256 与冻结值不符")
    value = {
        "treatment": {
            "path": TREATMENT_REL,
            "sha256": treatment,
            "frozen_sha256": frozen,
            "matches_frozen": matches_frozen,
        },
        "open_work": {"path": OPEN_WORK_REL, "sha256": open_work},
        "implementation_plan": {"path": IMPLEMENTATION_PLAN_REL, "sha256": implementation_plan},
    }
    return value, problems


def _load_rule_set(repo_root: Path) -> Any:
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        from policy.loader import load_rule_set
    except Exception as error:  # noqa: BLE001 - 失败关闭：导入失败也不降级
        raise ManifestInputError(
            "rule_set_identity: 导入 policy.loader 失败（%s）" % _sanitize_message(str(error), repo_root)
        ) from error
    try:
        return load_rule_set([repo_root / "policies"], repo_root=repo_root)
    except Exception as error:  # noqa: BLE001 - 加载失败一律退出 2，不返回半份规则集
        raise ManifestInputError(
            "rule_set_identity: 加载规则集失败（%s）" % _sanitize_message(str(error), repo_root)
        ) from error


def _compute_rule_set_identity(
    repo_root: Path, scorer: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[str]]:
    rules_section = scorer.get("rules")
    items = rules_section.get("items") if isinstance(rules_section, dict) else None
    if not isinstance(items, list) or not items:
        raise ManifestInputError("scorer.yaml 的 rules.items 读不出来")
    expected: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or "rule_id" not in item or "rule_version" not in item:
            raise ManifestInputError(
                "scorer.yaml 的 rules.items[%d] 缺 rule_id / rule_version" % index
            )
        expected.append(
            {"rule_id": str(item["rule_id"]), "version": int(item["rule_version"])}
        )
    rule_set = _load_rule_set(repo_root)
    loaded = {rule.id: rule for rule in rule_set.rules}
    rows: List[Dict[str, Any]] = []
    problems: List[str] = []
    for item in sorted(expected, key=lambda entry: entry["rule_id"]):
        rule_id = item["rule_id"]
        expected_version = item["version"]
        rule = loaded.get(rule_id)
        if rule is None:
            rows.append(
                {
                    "rule_id": rule_id,
                    "version": None,
                    "expected_version": expected_version,
                    "version_ok": False,
                }
            )
            problems.append("rule_set_identity: 规则集里没有 %s" % rule_id)
            continue
        version = int(rule.version)
        version_ok = version == expected_version
        rows.append(
            {
                "rule_id": rule_id,
                "version": version,
                "expected_version": expected_version,
                "version_ok": version_ok,
            }
        )
        if not version_ok:
            problems.append(
                "rule_set_identity: %s 的 version=%d 与 scorer.yaml 的 %d 不符"
                % (rule_id, version, expected_version)
            )
    value = {"identity": rule_set.identity, "rules": rows}
    return value, problems


def _compute_hidden_digests(
    repo_root: Path, scorer_entries: Dict[str, str]
) -> Tuple[Dict[str, Any], List[str]]:
    value: Dict[str, Any] = {}
    problems: List[str] = []
    for name, relative in HIDDEN_FILES:
        actual = _sha256_file(repo_root / relative, relative)
        expected = scorer_entries.get(relative)
        matches = expected == actual
        value[name] = {
            "path": relative,
            "sha256": actual,
            "manifest_sha256": expected,
            "matches_manifest": matches,
        }
        if expected is None:
            problems.append("hidden_digests: scorer/manifest.sha256 里没有 %s 这一行" % relative)
        elif not matches:
            problems.append("hidden_digests: %s 与 scorer/manifest.sha256 记录不符" % relative)
    return value, problems


def _compute_reference_tree(repo_root: Path, root: Path) -> Dict[str, Any]:
    files: List[Dict[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in _SKIP_DIR_NAMES)
        for name in sorted(filenames):
            if name.endswith(_SKIP_SUFFIXES):
                continue
            full = Path(dirpath) / name
            relative = full.relative_to(root).as_posix()
            files.append(
                {"path": relative, "sha256": _sha256_file(full, "reference-tree/" + relative)}
            )
    files.sort(key=lambda item: item["path"])
    text = "".join("%s  %s\n" % (item["sha256"], item["path"]) for item in files)
    layers = _sha256_file(repo_root / SCORER_REL / "layers.yaml", SCORER_REL + "/layers.yaml")
    interfaces = _sha256_file(
        repo_root / SCORER_REL / "interfaces.yaml", SCORER_REL + "/interfaces.yaml"
    )
    return {
        "root": _display_path(root, repo_root),
        "file_count": len(files),
        "files_digest": _sha256_bytes(text.encode("utf-8")),
        "layers_sha256": layers,
        "interfaces_sha256": interfaces,
        "files": files,
    }


# --------------------------------------------------------------------------- 可选输入归一化


def _pick_paths(mapping: Dict[str, Any], dotted_paths: Iterable[str]) -> List[Tuple[str, Any]]:
    found: List[Tuple[str, Any]] = []
    for dotted in dotted_paths:
        current: Any = mapping
        present = True
        for part in dotted.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                present = False
                break
        if present:
            found.append((dotted, current))
    return found


def _pick_unique(mapping: Dict[str, Any], dotted_paths: Iterable[str], label: str) -> Any:
    found = _pick_paths(mapping, dotted_paths)
    if not found:
        return None
    canonical = {
        json.dumps(value, ensure_ascii=False, sort_keys=True) for _, value in found
    }
    if len(canonical) > 1:
        raise ManifestInputError(
            "arm-facts 里 %s 的多处声明不一致（%s）"
            % (label, " / ".join(path for path, _ in found))
        )
    return found[0][1]


def _normalize_arm_facts(path: Path, arm: str, repo_root: Path) -> Dict[str, Any]:
    """抽取四类事实（兼容 C 臂的完整 run-manifest，未知键一律忽略）。"""

    facts = _load_json(path, "arm-facts")
    if not isinstance(facts, dict):
        raise ManifestInputError("arm-facts 顶层不是对象")
    declared_arm = facts.get("arm")
    if declared_arm is not None and declared_arm != arm:
        raise ManifestInputError("arm-facts.arm=%r 与 --arm=%s 不一致" % (declared_arm, arm))
    tree_digest = _pick_unique(
        facts, ["tree_digest", "tree.combined_manifest_sha256"], "tree_digest"
    )
    if not isinstance(tree_digest, str) or not tree_digest.strip():
        raise ManifestInputError("arm-facts 缺少 tree_digest（也接受 tree.combined_manifest_sha256）")
    session_id = _pick_unique(facts, ["session_id", "session.id"], "session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ManifestInputError("arm-facts 缺少 session_id（也接受 session.id）")
    patch_declarations = _pick_paths(
        facts,
        ["launch.patch", "launch.patch_argument", "patch_argument", "dsh.patch_argument", "patch"],
    )
    if not patch_declarations:
        raise ManifestInputError(
            "arm-facts 缺少启动补丁声明（launch.patch / patch_argument；没有 patch 也要显式写 null）"
        )
    canonical_patch = {
        json.dumps(value, ensure_ascii=False, sort_keys=True) for _, value in patch_declarations
    }
    if len(canonical_patch) > 1:
        raise ManifestInputError(
            "arm-facts 里启动补丁声明不一致（%s）"
            % " / ".join(name for name, _ in patch_declarations)
        )
    patch = patch_declarations[0][1]
    if patch is not None and (not isinstance(patch, str) or not patch.strip()):
        raise ManifestInputError("arm-facts 的 launch.patch 必须是仓库相对路径或 null")
    launcher = _pick_unique(facts, ["launcher_sandbox", "launcher.sandbox"], "launcher_sandbox")
    if arm in ("A", "B"):
        if launcher is None:
            raise ManifestInputError(
                "A/B 臂必须显式声明 launcher_sandbox（也接受 launcher.sandbox；取值 %s）"
                % (list(LAUNCHER_SANDBOXES),)
            )
        if launcher not in LAUNCHER_SANDBOXES:
            raise ManifestInputError(
                "launcher_sandbox 必须是 %s 之一，读到 %r" % (list(LAUNCHER_SANDBOXES), launcher)
            )
    elif launcher is not None and launcher not in LAUNCHER_SANDBOXES:
        raise ManifestInputError(
            "launcher_sandbox 必须是 %s 之一，读到 %r" % (list(LAUNCHER_SANDBOXES), launcher)
        )
    problems: List[str] = []
    if arm == "C" and patch is not None:
        problems.append(
            "C 臂的 launch.patch 必须为 null（不治理臂不挂 patch），实际为 %s" % _safe_text(patch)
        )
    if patch is not None and not _is_safe_relative(patch):
        problems.append("launch.patch 不是仓库相对路径（%s）" % _safe_text(patch))
    return {
        "arm": arm,
        "tree_digest": tree_digest.strip(),
        "session_id": session_id.strip(),
        "launch": {"patch": patch},
        "launcher_sandbox": launcher,
        "source": _display_path(path, repo_root),
        "source_sha256": _sha256_file(path, "arm-facts"),
        "problems": sorted(problems),
    }


def _normalize_run_record(path: Path, arm: str, repo_root: Path) -> Dict[str, Any]:
    record = _load_json(path, "run-record")
    if not isinstance(record, dict):
        raise ManifestInputError("run-record 顶层不是对象")
    missing = [key for key in ("schema_version", "arm", "dimensions") if key not in record]
    if missing:
        raise ManifestInputError("run-record 缺少 %s" % ", ".join(missing))
    if not isinstance(record["schema_version"], str) or not record["schema_version"].strip():
        raise ManifestInputError("run-record.schema_version 必须是非空字符串")
    if record["arm"] != arm:
        raise ManifestInputError("run-record.arm=%r 与 --arm=%s 不一致" % (record["arm"], arm))
    dimensions = record["dimensions"]
    if not isinstance(dimensions, dict):
        raise ManifestInputError("run-record.dimensions 必须是对象")
    missing_dimensions = [dimension for dimension in ("T", "C", "A") if dimension not in dimensions]
    if missing_dimensions:
        raise ManifestInputError("run-record.dimensions 缺少 %s" % ", ".join(missing_dimensions))
    values = [dimensions[dimension] for dimension in ("T", "C", "A")]
    for dimension, value in zip(("T", "C", "A"), values):
        if value is None:
            raise ManifestInputError("run-record.dimensions.%s 是 null（三维读数必须齐全）" % dimension)
        found = _absolute_path_in(value)
        if found is not None:
            raise ManifestInputError(
                "run-record.dimensions.%s 里含绝对路径；run-manifest 不写绝对路径" % dimension
            )
    summary: Dict[str, Any] = {
        key: record[key] for key in ("schema_version", "arm", "status", "run_kind") if key in record
    }
    found = _absolute_path_in(summary)
    if found is not None:
        raise ManifestInputError("run-record 的摘要键里含绝对路径；run-manifest 不写绝对路径")
    return {
        "sha256": _sha256_file(path, "run-record"),
        "summary": summary,
        "dimensions": values,
    }


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestInputError("human-items 的 %s 必须是非空字符串" % field)
    return value


def _validate_human_value(field_id: str, value: Any) -> Tuple[str, Optional[str]]:
    """校验四项人工项的形状；返回（status, not_applicable 的 reason）。不评价内容质量。"""

    if not isinstance(value, dict):
        raise ManifestInputError("human-items 的 %s 必须是对象" % field_id)
    found = _absolute_path_in(value)
    if found is not None:
        raise ManifestInputError("human-items 的 %s 里含绝对路径；run-manifest 不写绝对路径" % field_id)
    if field_id == "hidden_author":
        _require_text(value.get("author"), "hidden_author.author")
        if not isinstance(value.get("saw_impl_diff"), bool):
            raise ManifestInputError("human-items 的 hidden_author.saw_impl_diff 必须是布尔值")
        return "recorded", None
    if field_id == "bypass_sampling":
        files = value.get("files")
        if not isinstance(files, list) or any(
            not isinstance(item, str) or not item.strip() for item in files
        ):
            raise ManifestInputError("human-items 的 bypass_sampling.files 必须是路径字符串列表")
        for item in files:
            if not _is_safe_relative(item):
                raise ManifestInputError("human-items 的 bypass_sampling.files 里有非仓库相对路径")
        _require_text(value.get("conclusion"), "bypass_sampling.conclusion")
        _require_text(value.get("sampler"), "bypass_sampling.sampler")
        return "recorded", None
    if field_id == "a4_review":
        _require_text(value.get("location"), "a4_review.location")
        _require_text(value.get("conclusion"), "a4_review.conclusion")
        return "recorded", None
    # nondeterminism_ruling：两种合法形态
    if "applicable" in value:
        if value.get("applicable") is not False:
            raise ManifestInputError("human-items 的 nondeterminism_ruling 只接受 applicable: false")
        reason = _require_text(value.get("reason"), "nondeterminism_ruling.reason")
        return "not_applicable", reason
    _require_text(value.get("diff_pointer"), "nondeterminism_ruling.diff_pointer")
    _require_text(value.get("ruling"), "nondeterminism_ruling.ruling")
    _require_text(value.get("basis"), "nondeterminism_ruling.basis")
    return "recorded", None


def _normalize_human_items(path: Path) -> Dict[str, Dict[str, Any]]:
    document = _load_json(path, "human-items")
    if not isinstance(document, dict):
        raise ManifestInputError("human-items 顶层不是对象")
    unknown = sorted(set(document) - set(HUMAN_FIELD_IDS))
    if unknown:
        raise ManifestInputError(
            "human-items 有未知键 %s（只接受 %s）" % (unknown, list(HUMAN_FIELD_IDS))
        )
    normalized: Dict[str, Dict[str, Any]] = {}
    for field_id in HUMAN_FIELD_IDS:
        if field_id not in document:
            continue
        status, reason = _validate_human_value(field_id, document[field_id])
        normalized[field_id] = {"status": status, "value": document[field_id], "reason": reason}
    return normalized


# --------------------------------------------------------------------------- platform_generation


def _platform_path_problem(value: str, where: str, token_only: bool = False) -> Optional[str]:
    for root in TOKEN_ROOTS:
        if value.startswith(root + "/") and _is_safe_relative(value[len(root) + 1 :]):
            return None
    if token_only:
        return "%s 必须是 <token> 下的相对路径（仓库外路径按 token 记）" % where
    if _is_safe_relative(value):
        return None
    return "%s 必须是仓库相对路径或 <token> 下的相对路径" % where


def _platform_text_problem(
    value: Any,
    where: str,
    *,
    path: bool = False,
    token_only: bool = False,
    pattern: Optional[re.Pattern[str]] = None,
) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return "%s 必须是非空字符串" % where
    text = value.strip()
    if _absolute_path_in(text) is not None:
        return "%s 不许写绝对路径" % where
    if path:
        problem = _platform_path_problem(text, where, token_only=token_only)
        if problem is not None:
            return problem
    if pattern is not None and not pattern.match(text):
        return "%s 的形状不合法（%s）" % (where, text)
    return None


def _platform_bool_problem(value: Any, where: str) -> Optional[str]:
    if not isinstance(value, bool):
        return "%s 必须是布尔值" % where
    return None


def _platform_int_problem(value: Any, where: str, minimum: int = 0) -> Optional[str]:
    if not isinstance(value, int) or isinstance(value, bool):
        return "%s 必须是整数" % where
    if value < minimum:
        return "%s 必须 >= %d" % (where, minimum)
    return None


def _platform_hex_problem(value: Any, where: str) -> Optional[str]:
    if not isinstance(value, str) or not _HEX64.match(value):
        return "%s 必须是 64 位十六进制摘要" % where
    return None


def _platform_enum_problem(value: Any, where: str, allowed: Sequence[str]) -> Optional[str]:
    if value not in allowed:
        return "%s 必须是 %s 之一，读到 %r" % (where, list(allowed), value)
    return None


def _platform_version_problem(value: Any, where: str) -> Optional[str]:
    if not isinstance(value, str) or not _VERSION_TEXT.match(value.strip()):
        return "%s 必须是版本号（如 0.2.1-rc.2 / 1.5），读到 %r" % (where, value)
    return None


def _platform_block(value: Any, where: str, keys: Sequence[str]) -> Dict[str, Any]:
    """严格块：未知键 / 缺键都是输入错误（退出 2），不做部分接受。"""

    if not isinstance(value, dict):
        raise ManifestInputError("platform-facts：%s 必须是对象" % where)
    unknown = sorted(set(value) - set(keys))
    missing = sorted(set(keys) - set(value))
    if unknown:
        raise ManifestInputError("platform-facts：%s 有未知键 %s" % (where, unknown))
    if missing:
        raise ManifestInputError("platform-facts：%s 缺少 %s" % (where, ", ".join(missing)))
    return value


def _platform_need(problem: Optional[str]) -> None:
    if problem is not None:
        raise ManifestInputError("platform-facts：" + problem)


def _platform_semantic_problems(value: Dict[str, Any]) -> List[str]:
    """跨字段不变量（已通过形状检查之后才调用）。"""

    problems: List[str] = []
    run = value["run"]
    if run["serial"] and (run["ci_local_lock_held"] or run["concurrent_sessions"] != 1):
        problems.append(
            "run.serial=true 与 ci_local_lock_held / concurrent_sessions 矛盾："
            "串行 run 不持 ci_local 锁，且并发会话数必须是 1"
        )
    batch = value["batch_ledger"]
    adapter = value["declarations"]["adapter_config"]
    if batch["into_decision"] and not batch["enabled"]:
        problems.append("batch_ledger.into_decision=true 但 enabled=false（关闭的账本不能进判定）")
    if adapter["into_decision"] != batch["into_decision"]:
        problems.append(
            "declarations.adapter_config.into_decision 与 batch_ledger.into_decision 不一致"
        )
    if adapter["max_targets"] != batch["max_targets"]:
        problems.append(
            "declarations.adapter_config.max_targets 与 batch_ledger.max_targets 不一致"
        )
    budget = value["budget"]
    if budget["applicable"] and not budget["ok"]:
        problems.append(
            "预算不等式不成立："
            "pre_evidence.timeout_ms + timeouts.tool_timeout_ms 必须 < timeouts.hooks_timeout_ms"
        )
    observations = value["observations"]["batch"]
    if observations["unreadable"] > 0 and not observations["degraded"]:
        problems.append("observations.batch.unreadable>0 但 degraded=false（读不出的账本必须记 degraded）")
    if observations["truncated"] > 0 and not observations["degraded"]:
        problems.append("observations.batch.truncated>0 但 degraded=false（截断必须记 degraded）")
    if observations["degraded"] and observations["unreadable"] == 0 and observations["truncated"] == 0:
        problems.append("observations.batch.degraded=true 但没有任何证据（unreadable / truncated 都是 0）")
    return problems


def _normalize_platform_facts(path: Path, repo_root: Path) -> Dict[str, Any]:
    """校验并规范化 --platform-facts：未知键 / 类型错 / 计数矛盾退出 2；跨字段矛盾记 problems。"""

    document = _load_json(path, "platform-facts")
    if not isinstance(document, dict):
        raise ManifestInputError("platform-facts 顶层不是对象")
    unknown = sorted(set(document) - set(PLATFORM_KEYS))
    missing = sorted(set(PLATFORM_KEYS) - set(document))
    if unknown:
        raise ManifestInputError(
            "platform-facts 顶层出现未知键 %s；允许的键为 %s" % (unknown, sorted(PLATFORM_KEYS))
        )
    if missing:
        raise ManifestInputError("platform-facts 缺少 %s" % ", ".join(missing))

    host = _platform_block(document["host"], "host", _PLATFORM_HOST_KEYS)
    _platform_need(_platform_enum_problem(host["entry"], "host.entry", PLATFORM_HOST_ENTRIES))
    _platform_need(_platform_text_problem(host["dsh_runtime"], "host.dsh_runtime", pattern=_VERSION_TEXT))
    _platform_need(_platform_enum_problem(host["dsh_source"], "host.dsh_source", PLATFORM_DSH_SOURCES))
    _platform_need(_platform_text_problem(host["dsh_entry"], "host.dsh_entry", path=True, token_only=True))
    _platform_need(_platform_text_problem(host["profile"], "host.profile"))
    _platform_need(_platform_enum_problem(host["session_sandbox"], "host.session_sandbox", SANDBOX_MODES))
    _platform_need(_platform_enum_problem(host["file_policy"], "host.file_policy", SANDBOX_MODES))
    _platform_need(_platform_enum_problem(host["sandbox"], "host.sandbox", SANDBOX_STATES))

    start = _platform_block(document["start"], "start", _PLATFORM_START_KEYS)
    if not isinstance(start["head"], str) or not _HEX_ANY.match(start["head"]):
        raise ManifestInputError("platform-facts：start.head 必须是 40/64 位十六进制 git HEAD")
    _platform_need(_platform_bool_problem(start["worktree_clean"], "start.worktree_clean"))

    run = _platform_block(document["run"], "run", _PLATFORM_RUN_KEYS)
    _platform_need(_platform_bool_problem(run["serial"], "run.serial"))
    _platform_need(_platform_bool_problem(run["ci_local_lock_held"], "run.ci_local_lock_held"))
    _platform_need(_platform_int_problem(run["concurrent_sessions"], "run.concurrent_sessions", 1))

    declarations = _platform_block(document["declarations"], "declarations", _PLATFORM_DECLARATION_KEYS)
    adapter = _platform_block(declarations["adapter_config"], "declarations.adapter_config", _PLATFORM_ADAPTER_KEYS)
    _platform_need(_platform_text_problem(adapter["path"], "declarations.adapter_config.path", path=True))
    _platform_need(_platform_hex_problem(adapter["sha256"], "declarations.adapter_config.sha256"))
    _platform_need(_platform_version_problem(adapter["agent_version"], "declarations.adapter_config.agent_version"))
    _platform_need(_platform_bool_problem(adapter["into_decision"], "declarations.adapter_config.into_decision"))
    _platform_need(_platform_int_problem(adapter["max_targets"], "declarations.adapter_config.max_targets"))
    registry = _platform_block(declarations["registry"], "declarations.registry", _PLATFORM_REGISTRY_KEYS)
    _platform_need(_platform_text_problem(registry["path"], "declarations.registry.path", path=True))
    _platform_need(_platform_hex_problem(registry["sha256"], "declarations.registry.sha256"))
    _platform_need(_platform_version_problem(registry["registry_schema_version"], "declarations.registry.registry_schema_version"))
    _platform_need(_platform_text_problem(registry["approved_path"], "declarations.registry.approved_path", path=True))
    _platform_need(_platform_hex_problem(registry["approved_sha256"], "declarations.registry.approved_sha256"))
    _platform_need(_platform_text_problem(registry["approved_reviewed_by"], "declarations.registry.approved_reviewed_by"))
    _platform_need(_platform_text_problem(registry["approved_reviewed_at"], "declarations.registry.approved_reviewed_at"))
    approval = _platform_block(declarations["approval"], "declarations.approval", _PLATFORM_APPROVAL_KEYS)
    _platform_need(_platform_text_problem(approval["path"], "declarations.approval.path", path=True))
    _platform_need(_platform_hex_problem(approval["sha256"], "declarations.approval.sha256"))
    test_layout = _platform_block(declarations["test_layout"], "declarations.test_layout", _PLATFORM_TEST_LAYOUT_KEYS)
    _platform_need(_platform_text_problem(test_layout["path"], "declarations.test_layout.path", path=True))
    _platform_need(_platform_hex_problem(test_layout["sha256"], "declarations.test_layout.sha256"))

    batch = _platform_block(document["batch_ledger"], "batch_ledger", _PLATFORM_BATCH_KEYS)
    _platform_need(_platform_bool_problem(batch["enabled"], "batch_ledger.enabled"))
    _platform_need(_platform_bool_problem(batch["into_decision"], "batch_ledger.into_decision"))
    _platform_need(_platform_int_problem(batch["max_targets"], "batch_ledger.max_targets"))
    _platform_need(_platform_int_problem(batch["ttl_hours"], "batch_ledger.ttl_hours", 1))
    _platform_need(_platform_version_problem(batch["schema_version"], "batch_ledger.schema_version"))
    audit_version = document["audit_schema_version"]
    _platform_need(_platform_version_problem(audit_version, "audit_schema_version"))

    pre_evidence = _platform_block(document["pre_evidence"], "pre_evidence", _PLATFORM_PRE_EVIDENCE_KEYS)
    _platform_need(_platform_bool_problem(pre_evidence["enabled"], "pre_evidence.enabled"))
    _platform_need(_platform_int_problem(pre_evidence["timeout_ms"], "pre_evidence.timeout_ms", 1))
    timeouts = _platform_block(document["timeouts"], "timeouts", _PLATFORM_TIMEOUT_KEYS)
    _platform_need(_platform_int_problem(timeouts["tool_timeout_ms"], "timeouts.tool_timeout_ms", 1))
    _platform_need(_platform_int_problem(timeouts["hooks_timeout_ms"], "timeouts.hooks_timeout_ms", 1))

    model = _platform_block(document["model"], "model", _PLATFORM_MODEL_KEYS)
    _platform_need(_platform_text_problem(model["id"], "model.id"))
    params = model["params"]
    if not isinstance(params, dict):
        raise ManifestInputError("platform-facts：model.params 必须是对象")
    normalized_params: Dict[str, Any] = {}
    for key, item in params.items():
        if not isinstance(key, str) or not key.strip() or _absolute_path_in(key) is not None:
            raise ManifestInputError("platform-facts：model.params 的键必须是非空字符串且不含绝对路径")
        if isinstance(item, bool) or isinstance(item, (int, float)):
            normalized_params[key.strip()] = item
        elif isinstance(item, str):
            _platform_need(_platform_text_problem(item, "model.params.%s" % key))
            normalized_params[key.strip()] = item.strip()
        else:
            raise ManifestInputError(
                "platform-facts：model.params.%s 只接受标量（str / int / float / bool）" % key
            )
    _platform_need(_platform_hex_problem(model["first_message_sha256"], "model.first_message_sha256"))

    observations = _platform_block(document["observations"], "observations", _PLATFORM_OBSERVATION_KEYS)
    batch_observations = _platform_block(observations["batch"], "observations.batch", _PLATFORM_BATCH_OBSERVATION_KEYS)
    for key in ("decisions", "with_batch", "settled", "truncated", "unreadable"):
        _platform_need(_platform_int_problem(batch_observations[key], "observations.batch.%s" % key))
    _platform_need(_platform_bool_problem(batch_observations["degraded"], "observations.batch.degraded"))
    if batch_observations["with_batch"] > batch_observations["decisions"]:
        raise ManifestInputError("platform-facts：observations.batch.with_batch 不能大于 decisions")
    if batch_observations["settled"] > batch_observations["with_batch"]:
        raise ManifestInputError("platform-facts：observations.batch.settled 不能大于 with_batch")

    if pre_evidence["enabled"]:
        left = pre_evidence["timeout_ms"] + timeouts["tool_timeout_ms"]
        budget: Dict[str, Any] = {
            "applicable": True,
            "ok": left < timeouts["hooks_timeout_ms"],
            "left_ms": left,
            "right_ms": timeouts["hooks_timeout_ms"],
            "inequality": (
                "pre_evidence.timeout_ms + timeouts.tool_timeout_ms "
                "< timeouts.hooks_timeout_ms"
            ),
        }
    else:
        budget = {
            "applicable": False,
            "reason": "pre_evidence.enabled=false（未声明取证，预算不等式不适用）",
        }

    value: Dict[str, Any] = {
        "host": {
            "entry": host["entry"],
            "dsh_runtime": host["dsh_runtime"],
            "dsh_source": host["dsh_source"],
            "dsh_entry": host["dsh_entry"],
            "profile": host["profile"],
            "session_sandbox": host["session_sandbox"],
            "file_policy": host["file_policy"],
            "sandbox": host["sandbox"],
        },
        "start": {"head": start["head"], "worktree_clean": start["worktree_clean"]},
        "run": {
            "serial": run["serial"],
            "ci_local_lock_held": run["ci_local_lock_held"],
            "concurrent_sessions": run["concurrent_sessions"],
        },
        "declarations": {
            "adapter_config": {
                "path": adapter["path"],
                "sha256": adapter["sha256"],
                "agent_version": adapter["agent_version"],
                "into_decision": adapter["into_decision"],
                "max_targets": adapter["max_targets"],
            },
            "registry": {
                "path": registry["path"],
                "sha256": registry["sha256"],
                "registry_schema_version": registry["registry_schema_version"],
                "approved_path": registry["approved_path"],
                "approved_sha256": registry["approved_sha256"],
                "approved_reviewed_by": registry["approved_reviewed_by"],
                "approved_reviewed_at": registry["approved_reviewed_at"],
            },
            "approval": {"path": approval["path"], "sha256": approval["sha256"]},
            "test_layout": {"path": test_layout["path"], "sha256": test_layout["sha256"]},
        },
        "batch_ledger": {
            "enabled": batch["enabled"],
            "into_decision": batch["into_decision"],
            "max_targets": batch["max_targets"],
            "ttl_hours": batch["ttl_hours"],
            "schema_version": batch["schema_version"],
        },
        "audit_schema_version": audit_version.strip(),
        "pre_evidence": {
            "enabled": pre_evidence["enabled"],
            "timeout_ms": pre_evidence["timeout_ms"],
        },
        "timeouts": {
            "tool_timeout_ms": timeouts["tool_timeout_ms"],
            "hooks_timeout_ms": timeouts["hooks_timeout_ms"],
        },
        "budget": budget,
        "model": {
            "id": model["id"],
            "params": normalized_params,
            "first_message_sha256": model["first_message_sha256"],
        },
        "observations": {"batch": {key: batch_observations[key] for key in _PLATFORM_BATCH_OBSERVATION_KEYS}},
        "problems": [],
    }
    value["problems"] = sorted(_platform_semantic_problems(value))
    return {"value": value, "problems": list(value["problems"])}


def _verify_platform_structure(value: Any) -> List[str]:
    if not isinstance(value, dict):
        return ["platform_generation: value 必须是对象"]
    required = set(PLATFORM_KEYS) | {"budget", "problems"}
    if set(value) != required:
        return ["platform_generation: value 的键必须是 %s" % sorted(required)]
    problems: List[str] = []

    def need(problem: Optional[str]) -> None:
        if problem is not None:
            problems.append(problem)

    def block(where: str, item: Any, keys: Sequence[str]) -> bool:
        if not isinstance(item, dict):
            problems.append("%s 必须是对象" % where)
            return False
        unknown = sorted(set(item) - set(keys))
        missing = sorted(set(keys) - set(item))
        if unknown:
            problems.append("%s 有未知键 %s" % (where, unknown))
        if missing:
            problems.append("%s 缺少 %s" % (where, ", ".join(missing)))
            return False
        return True

    host = value.get("host")
    if block("platform_generation.host", host, _PLATFORM_HOST_KEYS):
        need(_platform_enum_problem(host.get("entry"), "platform_generation.host.entry", PLATFORM_HOST_ENTRIES))
        need(_platform_text_problem(host.get("dsh_runtime"), "platform_generation.host.dsh_runtime", pattern=_VERSION_TEXT))
        need(_platform_enum_problem(host.get("dsh_source"), "platform_generation.host.dsh_source", PLATFORM_DSH_SOURCES))
        need(_platform_text_problem(host.get("dsh_entry"), "platform_generation.host.dsh_entry", path=True, token_only=True))
        need(_platform_text_problem(host.get("profile"), "platform_generation.host.profile"))
        need(_platform_enum_problem(host.get("session_sandbox"), "platform_generation.host.session_sandbox", SANDBOX_MODES))
        need(_platform_enum_problem(host.get("file_policy"), "platform_generation.host.file_policy", SANDBOX_MODES))
        need(_platform_enum_problem(host.get("sandbox"), "platform_generation.host.sandbox", SANDBOX_STATES))

    start = value.get("start")
    if block("platform_generation.start", start, _PLATFORM_START_KEYS):
        head = start.get("head")
        if not isinstance(head, str) or not _HEX_ANY.match(head):
            problems.append("platform_generation.start.head 必须是 40/64 位十六进制 git HEAD")
        need(_platform_bool_problem(start.get("worktree_clean"), "platform_generation.start.worktree_clean"))

    run = value.get("run")
    if block("platform_generation.run", run, _PLATFORM_RUN_KEYS):
        need(_platform_bool_problem(run.get("serial"), "platform_generation.run.serial"))
        need(_platform_bool_problem(run.get("ci_local_lock_held"), "platform_generation.run.ci_local_lock_held"))
        need(_platform_int_problem(run.get("concurrent_sessions"), "platform_generation.run.concurrent_sessions", 1))

    declarations = value.get("declarations")
    if block("platform_generation.declarations", declarations, _PLATFORM_DECLARATION_KEYS):
        adapter = declarations.get("adapter_config")
        if block("platform_generation.declarations.adapter_config", adapter, _PLATFORM_ADAPTER_KEYS):
            need(_platform_text_problem(adapter.get("path"), "platform_generation.declarations.adapter_config.path", path=True))
            need(_platform_hex_problem(adapter.get("sha256"), "platform_generation.declarations.adapter_config.sha256"))
            need(_platform_version_problem(adapter.get("agent_version"), "platform_generation.declarations.adapter_config.agent_version"))
            need(_platform_bool_problem(adapter.get("into_decision"), "platform_generation.declarations.adapter_config.into_decision"))
            need(_platform_int_problem(adapter.get("max_targets"), "platform_generation.declarations.adapter_config.max_targets"))
        registry = declarations.get("registry")
        if block("platform_generation.declarations.registry", registry, _PLATFORM_REGISTRY_KEYS):
            need(_platform_text_problem(registry.get("path"), "platform_generation.declarations.registry.path", path=True))
            need(_platform_hex_problem(registry.get("sha256"), "platform_generation.declarations.registry.sha256"))
            need(_platform_version_problem(registry.get("registry_schema_version"), "platform_generation.declarations.registry.registry_schema_version"))
            need(_platform_text_problem(registry.get("approved_path"), "platform_generation.declarations.registry.approved_path", path=True))
            need(_platform_hex_problem(registry.get("approved_sha256"), "platform_generation.declarations.registry.approved_sha256"))
            need(_platform_text_problem(registry.get("approved_reviewed_by"), "platform_generation.declarations.registry.approved_reviewed_by"))
            need(_platform_text_problem(registry.get("approved_reviewed_at"), "platform_generation.declarations.registry.approved_reviewed_at"))
        approval = declarations.get("approval")
        if block("platform_generation.declarations.approval", approval, _PLATFORM_APPROVAL_KEYS):
            need(_platform_text_problem(approval.get("path"), "platform_generation.declarations.approval.path", path=True))
            need(_platform_hex_problem(approval.get("sha256"), "platform_generation.declarations.approval.sha256"))
        test_layout = declarations.get("test_layout")
        if block("platform_generation.declarations.test_layout", test_layout, _PLATFORM_TEST_LAYOUT_KEYS):
            need(_platform_text_problem(test_layout.get("path"), "platform_generation.declarations.test_layout.path", path=True))
            need(_platform_hex_problem(test_layout.get("sha256"), "platform_generation.declarations.test_layout.sha256"))

    batch = value.get("batch_ledger")
    if block("platform_generation.batch_ledger", batch, _PLATFORM_BATCH_KEYS):
        need(_platform_bool_problem(batch.get("enabled"), "platform_generation.batch_ledger.enabled"))
        need(_platform_bool_problem(batch.get("into_decision"), "platform_generation.batch_ledger.into_decision"))
        need(_platform_int_problem(batch.get("max_targets"), "platform_generation.batch_ledger.max_targets"))
        need(_platform_int_problem(batch.get("ttl_hours"), "platform_generation.batch_ledger.ttl_hours", 1))
        need(_platform_version_problem(batch.get("schema_version"), "platform_generation.batch_ledger.schema_version"))
    need(_platform_version_problem(value.get("audit_schema_version"), "platform_generation.audit_schema_version"))

    pre_evidence = value.get("pre_evidence")
    if block("platform_generation.pre_evidence", pre_evidence, _PLATFORM_PRE_EVIDENCE_KEYS):
        need(_platform_bool_problem(pre_evidence.get("enabled"), "platform_generation.pre_evidence.enabled"))
        need(_platform_int_problem(pre_evidence.get("timeout_ms"), "platform_generation.pre_evidence.timeout_ms", 1))
    timeouts = value.get("timeouts")
    if block("platform_generation.timeouts", timeouts, _PLATFORM_TIMEOUT_KEYS):
        need(_platform_int_problem(timeouts.get("tool_timeout_ms"), "platform_generation.timeouts.tool_timeout_ms", 1))
        need(_platform_int_problem(timeouts.get("hooks_timeout_ms"), "platform_generation.timeouts.hooks_timeout_ms", 1))

    model = value.get("model")
    if block("platform_generation.model", model, _PLATFORM_MODEL_KEYS):
        need(_platform_text_problem(model.get("id"), "platform_generation.model.id"))
        need(_platform_hex_problem(model.get("first_message_sha256"), "platform_generation.model.first_message_sha256"))
        params = model.get("params")
        if not isinstance(params, dict):
            problems.append("platform_generation.model.params 必须是对象")
        else:
            for key, item in params.items():
                if not isinstance(key, str) or not key.strip():
                    problems.append("platform_generation.model.params 的键必须是非空字符串")
                    continue
                if isinstance(item, bool) or isinstance(item, (int, float)):
                    continue
                if isinstance(item, str) and _absolute_path_in(item) is None:
                    continue
                problems.append("platform_generation.model.params.%s 只能是标量或不含绝对路径的字符串" % key)

    observations = value.get("observations")
    batch_observations: Any = None
    if block("platform_generation.observations", observations, _PLATFORM_OBSERVATION_KEYS):
        batch_observations = observations.get("batch")
        if block("platform_generation.observations.batch", batch_observations, _PLATFORM_BATCH_OBSERVATION_KEYS):
            for key in ("decisions", "with_batch", "settled", "truncated", "unreadable"):
                need(_platform_int_problem(batch_observations.get(key), "platform_generation.observations.batch.%s" % key))
            need(_platform_bool_problem(batch_observations.get("degraded"), "platform_generation.observations.batch.degraded"))
            decisions = batch_observations.get("decisions")
            with_batch = batch_observations.get("with_batch")
            settled = batch_observations.get("settled")
            if isinstance(decisions, int) and isinstance(with_batch, int) and with_batch > decisions:
                problems.append("platform_generation.observations.batch.with_batch 不能大于 decisions")
            if isinstance(settled, int) and isinstance(with_batch, int) and settled > with_batch:
                problems.append("platform_generation.observations.batch.settled 不能大于 with_batch")

    budget = value.get("budget")
    if not isinstance(budget, dict):
        problems.append("platform_generation.budget 必须是对象")
    elif budget.get("applicable") is True:
        if set(budget) != {"applicable", "ok", "left_ms", "right_ms", "inequality"}:
            problems.append("platform_generation.budget 的形状必须是 applicable/ok/left_ms/right_ms/inequality")
        else:
            need(_platform_bool_problem(budget.get("ok"), "platform_generation.budget.ok"))
            need(_platform_int_problem(budget.get("left_ms"), "platform_generation.budget.left_ms"))
            need(_platform_int_problem(budget.get("right_ms"), "platform_generation.budget.right_ms"))
            if not isinstance(budget.get("inequality"), str) or not budget.get("inequality", "").strip():
                problems.append("platform_generation.budget.inequality 必须是非空字符串")
            pre_block = pre_evidence if isinstance(pre_evidence, dict) else {}
            timeout_block = timeouts if isinstance(timeouts, dict) else {}
            expected_left = pre_block.get("timeout_ms", 0) + timeout_block.get("tool_timeout_ms", 0)
            expected_right = timeout_block.get("hooks_timeout_ms")
            if budget.get("left_ms") != expected_left:
                problems.append("platform_generation.budget.left_ms 与 pre_evidence.timeout_ms + tool_timeout_ms 不符")
            if budget.get("right_ms") != expected_right:
                problems.append("platform_generation.budget.right_ms 与 timeouts.hooks_timeout_ms 不符")
            expected_ok = isinstance(expected_right, int) and expected_left < expected_right
            if budget.get("ok") is not expected_ok:
                problems.append("platform_generation.budget.ok 与现场重算的预算不等式不符")
    elif budget.get("applicable") is False:
        if set(budget) != {"applicable", "reason"}:
            problems.append("platform_generation.budget 不适用时必须是 {applicable: false, reason}")
        else:
            reason = budget.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                problems.append("platform_generation.budget.reason 必须是非空字符串")
        if (pre_evidence or {}).get("enabled") is not False:
            problems.append("platform_generation.budget.applicable=false 但 pre_evidence.enabled=true")
    else:
        problems.append("platform_generation.budget.applicable 必须是布尔值")

    issues = value.get("problems")
    if not isinstance(issues, list) or any(not isinstance(item, str) for item in issues):
        problems.append("platform_generation.problems 必须是字符串列表")
    else:
        problems.extend("platform_generation: " + item for item in issues)

    if not problems:
        problems.extend(_platform_semantic_problems(value))
    return problems


# --------------------------------------------------------------------------- 字段组装


def _entry(status: str, value: Any, source: str, reason: Optional[str] = None) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"status": status, "value": value, "source": source}
    if reason is not None:
        entry["reason"] = reason
    return entry


_HUMAN_SOURCE_FALLBACK = "scorer/README.md §6 的人工项；由 --human-items 提供（工具不代填）"
_HUMAN_REASONS = {
    "hidden_author": "human-items 未提供 hidden_author（H1：作者标识 + 是否看过实施 diff，只能人记）",
    "bypass_sampling": "human-items 未提供 bypass_sampling（H2：被抽文件 + 结论 + 抽样人，只能人记）",
    "a4_review": "human-items 未提供 a4_review（H3：人看的位置 + 结论，只能人看）",
    "nondeterminism_ruling": "human-items 未提供 nondeterminism_ruling（H4：不适用理由，或差异指针 + 裁定 + 依据）",
}


class _Builder:
    """把 18 个字段逐个算出来；所有问题汇总在 self.problems（生成模式退出 1 的依据）。"""

    def __init__(
        self,
        repo_root: Path,
        arm: str,
        scorer: Dict[str, Any],
        out_rel: str,
        reference_tree: Optional[Path],
        arm_facts: Optional[Dict[str, Any]],
        readings: Optional[Dict[str, Any]],
        platform_facts: Optional[Dict[str, Any]],
        human_items: Optional[Dict[str, Dict[str, Any]]],
        human_source: Optional[str],
    ) -> None:
        self.repo_root = repo_root
        self.arm = arm
        self.scorer = scorer
        self.out_rel = out_rel
        self.reference_tree = reference_tree
        self.arm_facts = arm_facts
        self.readings = readings
        self.platform_facts = platform_facts
        self.human_items = human_items
        self.human_source = human_source
        self._first_message_cache: Optional[Dict[str, Any]] = None
        self.problems: List[str] = []
        scorer_entries, malformed, _ = _read_sha256_manifest(
            repo_root, SCORER_REL + "/manifest.sha256"
        )
        self.scorer_entries = scorer_entries
        self.task_entries, task_malformed, _ = _read_sha256_manifest(
            repo_root, TASK_PACKAGE_REL + "/manifest.sha256"
        )
        if malformed:
            self.problems.extend(
                "scorer/manifest.sha256 有格式问题（%s）" % problem for problem in malformed
            )
        if task_malformed:
            self.problems.extend(
                "task-package/manifest.sha256 有格式问题（%s）" % problem for problem in task_malformed
            )

    def build(self) -> Dict[str, Any]:
        fields = {
            "head": self._head(),
            "worktree_clean": self._worktree_clean(),
            "scorer_manifest_sha256": self._scorer_manifest_sha256(),
            "manifest_check": self._manifest_check(),
            "task_package_manifest_sha256": self._task_package_manifest(),
            "first_message_sha256": self._first_message(),
            "configs_after_sha256_txt": self._configs_after(),
            "criterion_sources": self._criterion_sources(),
            "rule_set_identity": self._rule_set_identity(),
            "hidden_digests": self._hidden_digests(),
            "reference_tree": self._reference_tree(),
            "arms": self._arms(),
            "readings": self._readings(),
            "platform_generation": self._platform_generation(),
            "hidden_author": self._human("hidden_author"),
            "bypass_sampling": self._human("bypass_sampling"),
            "a4_review": self._human("a4_review"),
            "nondeterminism_ruling": self._human("nondeterminism_ruling"),
        }
        if set(fields) != set(RUN_MANIFEST_FIELDS):
            raise ManifestInputError("内部错误：生成的字段集合与 18 字段契约不一致")
        return {"schema_version": RUN_MANIFEST_SCHEMA_VERSION, "arm": self.arm, "fields": fields}

    # -- 冻结类摘要 -------------------------------------------------------

    def _head(self) -> Dict[str, Any]:
        return _entry("recorded", _git_head(self.repo_root), "git rev-parse HEAD（仓库根由脚本位置推出）")

    def _worktree_clean(self) -> Dict[str, Any]:
        entries = [
            line
            for line in _git_porcelain(self.repo_root)
            if _porcelain_path(line) != self.out_rel
        ]
        value = {
            "clean": not entries,
            "self_output_excluded": self.out_rel,
            "entries": entries,
        }
        source = "git status --porcelain；--out 自身条目先排除再判 clean"
        return _entry("recorded", value, source)

    def _scorer_manifest_sha256(self) -> Dict[str, Any]:
        value = _compute_scorer_manifest_sha256(self.repo_root)
        return _entry(
            "recorded",
            value,
            "sha256(scorer/manifest.sha256 原始字节)；即 scorer/README.md §4 的组合摘要",
        )

    def _manifest_check(self) -> Dict[str, Any]:
        value, problems = _run_make_manifest(self.repo_root)
        self.problems.extend(problems)
        return _entry(
            "recorded",
            value,
            "实时跑 scorer/make_manifest.py --check --strict，记退出码与最后一行 RESULT",
        )

    def _task_package_manifest(self) -> Dict[str, Any]:
        value, problems = _compute_task_package(self.repo_root)
        self.problems.extend(problems)
        return _entry(
            "recorded",
            value,
            "sha256(task-package/manifest.sha256) + 逐行核对清单里的文件",
        )

    def _first_message(self) -> Dict[str, Any]:
        if self._first_message_cache is not None:
            return self._first_message_cache
        value, problems = _compute_first_message(self.repo_root, self.task_entries)
        self.problems.extend(problems)
        entry = _entry(
            "recorded",
            value,
            "sha256(task-package/first-message.txt) 与任务包清单的 first-message.txt 行比对",
        )
        self._first_message_cache = entry
        return entry

    def _configs_after(self) -> Dict[str, Any]:
        value, problems = _compute_configs_after(self.repo_root)
        self.problems.extend(problems)
        return _entry(
            "recorded",
            value,
            "sha256(configs/after/sha256.txt) + 逐行核对它声明的 9 个文件",
        )

    def _criterion_sources(self) -> Dict[str, Any]:
        value, problems = _compute_criterion_sources(self.repo_root, self.scorer)
        self.problems.extend(problems)
        return _entry(
            "recorded",
            value,
            "scorer.yaml freeze.criterion_sources 的三条来源；memo 用冻结值，04/05 记 run 时值",
        )

    def _rule_set_identity(self) -> Dict[str, Any]:
        value, problems = _compute_rule_set_identity(self.repo_root, self.scorer)
        self.problems.extend(problems)
        return _entry(
            "recorded",
            value,
            "policy.loader.load_rule_set([仓库根/policies], repo_root=仓库根)；"
            "8 条规则的 version 与 scorer.yaml rules.items 核对",
        )

    def _hidden_digests(self) -> Dict[str, Any]:
        value, problems = _compute_hidden_digests(self.repo_root, self.scorer_entries)
        self.problems.extend(problems)
        return _entry(
            "recorded",
            value,
            "sha256(hidden/test_acceptance_dgate2.py, hidden/runner.py) "
            "与 scorer/manifest.sha256 两行比对",
        )

    # -- 读数对象与臂 -----------------------------------------------------

    def _reference_tree(self) -> Dict[str, Any]:
        if self.reference_tree is None:
            return _entry(
                "pending",
                None,
                "--reference-tree <DIR>：参考树是读数对象，不冻结（04-open-work 5.79②）",
                "未提供 --reference-tree（A 维度读数需要一棵参考树；开跑后补记录）",
            )
        value = _compute_reference_tree(self.repo_root, self.reference_tree)
        return _entry(
            "recorded",
            value,
            "参考树的「<sha256>  <relpath>」排序文本再 sha256；跳 __pycache__/.pytest_cache/*.pyc；"
            "layers/interfaces 取 scorer/ 的两份声明",
        )

    def _arms(self) -> Dict[str, Any]:
        if self.arm_facts is None:
            return _entry(
                "pending",
                None,
                "--arm-facts <JSON>：树摘要、session id、启动 patch 与 launcher 沙箱形态",
                "未提供 --arm-facts（开跑时记录；A/B 必须声明 patch 与 launcher_sandbox，C 必须 patch=null）",
            )
        value = self.arm_facts
        self.problems.extend("arms: " + problem for problem in value.get("problems", []))
        return _entry(
            "recorded",
            value,
            "--arm-facts（兼容 C 臂完整 run-manifest）：抽取 tree_digest / session_id / "
            "launch.patch / launcher_sandbox，并记原始 JSON 的 sha256",
        )

    def _readings(self) -> Dict[str, Any]:
        if self.readings is None:
            return _entry(
                "pending",
                None,
                "--run-record <JSON>：schema_version / arm / dimensions{T,C,A}",
                "未提供 --run-record（跑完后记录三维读数；本工具只做结构校验）",
            )
        return _entry(
            "recorded",
            self.readings,
            "--run-record 的身份键与 dimensions{T,C,A}（按 T、C、A 固定顺序记录，原样保存读数）",
        )

    def _platform_generation(self) -> Dict[str, Any]:
        if self.platform_facts is None:
            return _entry(
                "pending",
                None,
                "--platform-facts <JSON>：本臂的宿主 / 沙箱 / 配置与审批摘要 / 批次代际 / 模型 / 起点事实（1.1 新增）",
                "未提供 --platform-facts（开跑前按冻结清单记录；任何 k≥3 run 之前必填）",
            )
        value = self.platform_facts["value"]
        self.problems.extend("platform_generation: " + problem for problem in value["problems"])
        expected = self._first_message()["value"]["sha256"]
        if value["model"]["first_message_sha256"] != expected:
            self.problems.append(
                "platform_generation.model.first_message_sha256 与任务包 first-message 的 sha256 不符"
            )
        if value["start"]["head"] == "0" * len(value["start"]["head"]):
            self.problems.append("platform_generation.start.head 不能是全零占位")
        return _entry(
            "recorded",
            value,
            "--platform-facts：输入逐键校验后原样记录；budget 由工具按三值（pre_evidence + tool < hooks）现场重算",
        )

    # -- 人工项 -----------------------------------------------------------


    def _human(self, field_id: str) -> Dict[str, Any]:
        item = (self.human_items or {}).get(field_id)
        fallback_reason = _HUMAN_REASONS[field_id]
        if item is None:
            source = _HUMAN_SOURCE_FALLBACK
            if self.human_source is not None:
                source = "--human-items（%s）：人工项原样记录，不代填" % self.human_source
            return _entry("pending", None, source, fallback_reason)
        source = "--human-items（%s）：人工项原样记录，不代填" % (self.human_source or "<outside-workspace>")
        if item["status"] == "not_applicable":
            reason = "H4 人工裁定不适用：%s" % item["reason"]
            return _entry("not_applicable", item["value"], source, reason)
        return _entry("recorded", item["value"], source)


# --------------------------------------------------------------------------- 校验


def _verify_entry_structure(field_id: str, entry: Any) -> List[str]:
    problems: List[str] = []
    if not isinstance(entry, dict):
        return ["%s: 字段条目必须是对象" % field_id]
    allowed = {"status", "value", "source", "reason"}
    unknown = sorted(set(entry) - allowed)
    if unknown:
        problems.append("%s: 字段条目有未知键 %s" % (field_id, unknown))
    missing = [key for key in ("status", "value", "source") if key not in entry]
    if missing:
        problems.append("%s: 字段条目缺少 %s" % (field_id, ", ".join(missing)))
    status = entry.get("status")
    if status not in FIELD_STATUSES:
        problems.append("%s: status=%r 不在 %s 里" % (field_id, status, list(FIELD_STATUSES)))
        return problems
    source = entry.get("source")
    if not isinstance(source, str) or not source.strip():
        problems.append("%s: source 必须是非空字符串" % field_id)
    if status in ("pending", "not_applicable"):
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append("%s: %s 必须带非空 reason" % (field_id, status))
        if status == "pending" and entry.get("value") is not None:
            problems.append("%s: pending 字段的 value 必须是 null" % field_id)
    return problems


def _verify_field_value(field_id: str, value: Any, repo_root: Path) -> List[str]:
    """非重算类的逐字段形状检查（重算类在 _verify_recorded 里另有现场比对）。"""

    if field_id == "head":
        if not isinstance(value, str) or not _HEX_ANY.match(value):
            return ["head: value 必须是 40/64 位十六进制 git HEAD"]
        return []
    if field_id == "worktree_clean":
        if not isinstance(value, dict):
            return ["worktree_clean: value 必须是对象"]
        problems: List[str] = []
        if set(value) != {"clean", "self_output_excluded", "entries"}:
            problems.append("worktree_clean: value 的键必须是 clean / self_output_excluded / entries")
        if not isinstance(value.get("clean"), bool):
            problems.append("worktree_clean.clean 必须是布尔值")
        excluded = value.get("self_output_excluded")
        if not isinstance(excluded, str) or not _is_safe_relative(excluded):
            problems.append("worktree_clean.self_output_excluded 必须是仓库相对路径")
        entries = value.get("entries")
        if not isinstance(entries, list) or any(not isinstance(item, str) for item in entries):
            problems.append("worktree_clean.entries 必须是字符串列表")
        return problems
    if field_id == "scorer_manifest_sha256":
        if not isinstance(value, str) or not _HEX64.match(value):
            return ["scorer_manifest_sha256: value 必须是 64 位十六进制摘要"]
        return []
    if field_id == "manifest_check":
        if not isinstance(value, dict) or set(value) != {"exit_code", "strict", "result_line"}:
            return ["manifest_check: value 的键必须是 exit_code / strict / result_line"]
        problems = []
        if not isinstance(value.get("exit_code"), int) or isinstance(value.get("exit_code"), bool):
            problems.append("manifest_check.exit_code 必须是整数")
        if value.get("strict") is not True:
            problems.append("manifest_check.strict 必须是 true")
        if not isinstance(value.get("result_line"), str):
            problems.append("manifest_check.result_line 必须是字符串")
        return problems
    if field_id in ("task_package_manifest_sha256", "configs_after_sha256_txt"):
        if not isinstance(value, dict):
            return ["%s: value 必须是对象" % field_id]
        problems = []
        if set(value) != {"sha256", "declared_count", "files_ok", "files_bad"}:
            problems.append(
                "%s: value 的键必须是 sha256 / declared_count / files_ok / files_bad" % field_id
            )
        if not isinstance(value.get("sha256"), str) or not _HEX64.match(value.get("sha256", "")):
            problems.append("%s.sha256 必须是 64 位十六进制摘要" % field_id)
        declared_count = value.get("declared_count")
        if not isinstance(declared_count, int) or isinstance(declared_count, bool):
            problems.append("%s.declared_count 必须是整数" % field_id)
        if not isinstance(value.get("files_ok"), list) or any(
            not isinstance(item, str) for item in value.get("files_ok", [])
        ):
            problems.append("%s.files_ok 必须是字符串列表" % field_id)
        if not isinstance(value.get("files_bad"), list):
            problems.append("%s.files_bad 必须是列表" % field_id)
        return problems
    if field_id == "first_message_sha256":
        if not isinstance(value, dict) or set(value) != {
            "sha256",
            "manifest_sha256",
            "matches_manifest",
        }:
            return ["first_message_sha256: value 的键必须是 sha256 / manifest_sha256 / matches_manifest"]
        problems = []
        if not isinstance(value.get("sha256"), str) or not _HEX64.match(value.get("sha256", "")):
            problems.append("first_message_sha256.sha256 必须是 64 位十六进制摘要")
        expected = value.get("manifest_sha256")
        if expected is not None and (not isinstance(expected, str) or not _HEX64.match(expected)):
            problems.append("first_message_sha256.manifest_sha256 必须是 null 或 64 位十六进制摘要")
        if not isinstance(value.get("matches_manifest"), bool):
            problems.append("first_message_sha256.matches_manifest 必须是布尔值")
        return problems
    if field_id == "criterion_sources":
        return _verify_criterion_structure(value)
    if field_id == "rule_set_identity":
        if not isinstance(value, dict) or set(value) != {"identity", "rules"}:
            return ["rule_set_identity: value 的键必须是 identity / rules"]
        problems = []
        identity = value.get("identity")
        if not isinstance(identity, str) or not _IDENTITY.match(identity):
            problems.append("rule_set_identity.identity 必须是 sha256:<64 位十六进制>")
        rules = value.get("rules")
        if not isinstance(rules, list):
            problems.append("rule_set_identity.rules 必须是列表")
        return problems
    if field_id == "hidden_digests":
        if not isinstance(value, dict):
            return ["hidden_digests: value 必须是对象"]
        problems = []
        for name, _ in HIDDEN_FILES:
            item = value.get(name)
            if not isinstance(item, dict):
                problems.append("hidden_digests.%s 必须是对象" % name)
                continue
            if set(item) != {"path", "sha256", "manifest_sha256", "matches_manifest"}:
                problems.append("hidden_digests.%s 的键不符合契约" % name)
            if not isinstance(item.get("sha256"), str) or not _HEX64.match(item.get("sha256", "")):
                problems.append("hidden_digests.%s.sha256 必须是 64 位十六进制摘要" % name)
            expected = item.get("manifest_sha256")
            if expected is not None and (
                not isinstance(expected, str) or not _HEX64.match(expected)
            ):
                problems.append("hidden_digests.%s.manifest_sha256 必须是 null 或摘要" % name)
            if not isinstance(item.get("matches_manifest"), bool):
                problems.append("hidden_digests.%s.matches_manifest 必须是布尔值" % name)
        return problems
    if field_id == "reference_tree":
        return _verify_reference_tree_structure(value)
    if field_id == "arms":
        return _verify_arms_structure(value)
    if field_id == "readings":
        return _verify_readings_structure(value)
    if field_id == "platform_generation":
        return _verify_platform_structure(value)
    if field_id in HUMAN_FIELD_IDS:
        try:
            status, _ = _validate_human_value(field_id, value)
        except ManifestInputError as error:
            return ["%s: %s" % (field_id, error)]
        if status != "recorded":
            return ["%s: recorded 字段不允许 applicable:false 的形态（应记 not_applicable）" % field_id]
        return []
    return ["%s: 未知字段 id（不在 18 字段契约里）" % field_id]


def _verify_criterion_structure(value: Any) -> List[str]:
    if not isinstance(value, dict) or set(value) != {
        "treatment",
        "open_work",
        "implementation_plan",
    }:
        return ["criterion_sources: value 的键必须是 treatment / open_work / implementation_plan"]
    problems: List[str] = []
    treatment = value.get("treatment")
    if not isinstance(treatment, dict) or set(treatment) != {
        "path",
        "sha256",
        "frozen_sha256",
        "matches_frozen",
    }:
        problems.append("criterion_sources.treatment 的键不符合契约")
    else:
        if treatment.get("path") != TREATMENT_REL:
            problems.append("criterion_sources.treatment.path 不是冻结的判据原文")
        for key in ("sha256", "frozen_sha256"):
            if not isinstance(treatment.get(key), str) or not _HEX64.match(treatment.get(key, "")):
                problems.append("criterion_sources.treatment.%s 必须是 64 位十六进制摘要" % key)
        if not isinstance(treatment.get("matches_frozen"), bool):
            problems.append("criterion_sources.treatment.matches_frozen 必须是布尔值")
    for name, relative in (
        ("open_work", OPEN_WORK_REL),
        ("implementation_plan", IMPLEMENTATION_PLAN_REL),
    ):
        item = value.get(name)
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            problems.append("criterion_sources.%s 的键不符合契约" % name)
            continue
        if item.get("path") != relative:
            problems.append("criterion_sources.%s.path 不是声明的来源路径" % name)
        if not isinstance(item.get("sha256"), str) or not _HEX64.match(item.get("sha256", "")):
            problems.append("criterion_sources.%s.sha256 必须是 64 位十六进制摘要" % name)
    return problems


def _verify_reference_tree_structure(value: Any) -> List[str]:
    if not isinstance(value, dict):
        return ["reference_tree: value 必须是对象"]
    required = {"root", "file_count", "files_digest", "layers_sha256", "interfaces_sha256", "files"}
    if set(value) != required:
        return ["reference_tree: value 的键必须是 %s" % sorted(required)]
    problems: List[str] = []
    for key in ("files_digest", "layers_sha256", "interfaces_sha256"):
        if not isinstance(value.get(key), str) or not _HEX64.match(value.get(key, "")):
            problems.append("reference_tree.%s 必须是 64 位十六进制摘要" % key)
    if not isinstance(value.get("file_count"), int) or isinstance(value.get("file_count"), bool):
        problems.append("reference_tree.file_count 必须是整数")
    if not isinstance(value.get("root"), str):
        problems.append("reference_tree.root 必须是字符串")
    files = value.get("files")
    if not isinstance(files, list):
        problems.append("reference_tree.files 必须是列表")
        return problems
    for index, item in enumerate(files):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            problems.append("reference_tree.files[%d] 的键不符合契约" % index)
            continue
        relative = item.get("path")
        if not isinstance(relative, str) or not _is_safe_relative(relative):
            problems.append("reference_tree.files[%d].path 必须是相对路径" % index)
        if not isinstance(item.get("sha256"), str) or not _HEX64.match(item.get("sha256", "")):
            problems.append("reference_tree.files[%d].sha256 必须是摘要" % index)
    return problems


def _verify_arms_structure(value: Any) -> List[str]:
    if not isinstance(value, dict):
        return ["arms: value 必须是对象"]
    required = {
        "arm",
        "tree_digest",
        "session_id",
        "launch",
        "launcher_sandbox",
        "source",
        "source_sha256",
        "problems",
    }
    if set(value) != required:
        return ["arms: value 的键必须是 %s" % sorted(required)]
    problems: List[str] = []
    arm = value.get("arm")
    if arm not in ARMS:
        problems.append("arms.arm 必须是 A/B/C 之一")
    for key in ("tree_digest", "session_id"):
        item = value.get(key)
        if not isinstance(item, str) or not item.strip():
            problems.append("arms.%s 必须是非空字符串" % key)
    launch = value.get("launch")
    if not isinstance(launch, dict) or set(launch) != {"patch"}:
        problems.append("arms.launch 必须是 {patch: 仓库相对路径或 null}")
    else:
        patch = launch.get("patch")
        if patch is not None:
            if not isinstance(patch, str) or not patch.strip():
                problems.append("arms.launch.patch 必须是仓库相对路径或 null")
            elif not _is_safe_relative(patch):
                problems.append("arms.launch.patch 不是仓库相对路径")
        if arm == "C" and patch is not None:
            problems.append("arms: C 臂的 launch.patch 必须为 null")
    launcher = value.get("launcher_sandbox")
    if launcher is not None and launcher not in LAUNCHER_SANDBOXES:
        problems.append("arms.launcher_sandbox 必须是 %s 之一" % (list(LAUNCHER_SANDBOXES),))
    if arm in ("A", "B") and launcher not in LAUNCHER_SANDBOXES:
        problems.append("arms: A/B 臂必须声明合法的 launcher_sandbox")
    if not isinstance(value.get("source"), str):
        problems.append("arms.source 必须是字符串")
    source_sha256 = value.get("source_sha256")
    if not isinstance(source_sha256, str) or not _HEX64.match(source_sha256):
        problems.append("arms.source_sha256 必须是 64 位十六进制摘要")
    issues = value.get("problems")
    if not isinstance(issues, list) or any(not isinstance(item, str) for item in issues):
        problems.append("arms.problems 必须是字符串列表")
    elif issues:
        problems.extend("arms: " + item for item in issues)
    return problems


def _verify_readings_structure(value: Any) -> List[str]:
    if not isinstance(value, dict):
        return ["readings: value 必须是对象"]
    required = {"sha256", "summary", "dimensions"}
    if set(value) != required:
        return ["readings: value 的键必须是 %s" % sorted(required)]
    problems: List[str] = []
    if not isinstance(value.get("sha256"), str) or not _HEX64.match(value.get("sha256", "")):
        problems.append("readings.sha256 必须是 64 位十六进制摘要")
    if not isinstance(value.get("summary"), dict):
        problems.append("readings.summary 必须是对象")
    dimensions = value.get("dimensions")
    if not isinstance(dimensions, list) or len(dimensions) != 3:
        problems.append("readings.dimensions 必须是按 T、C、A 排列的三元列表")
    elif any(item is None for item in dimensions):
        problems.append("readings.dimensions 里不允许 null")
    found = _absolute_path_in(value)
    if found is not None:
        problems.append("readings: value 里含绝对路径")
    return problems


def _verify_not_applicable(field_id: str, value: Any) -> List[str]:
    if field_id != "nondeterminism_ruling":
        return ["%s: 只有 nondeterminism_ruling 允许 not_applicable" % field_id]
    if not isinstance(value, dict) or value.get("applicable") is not False:
        return ["nondeterminism_ruling: not_applicable 形态必须是 {applicable: false, reason}"]
    reason = value.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return ["nondeterminism_ruling: not_applicable 必须带非空 reason"]
    return []


def _verify_recorded(
    field_id: str,
    value: Any,
    repo_root: Path,
    arm: Any,
    scorer: Optional[Dict[str, Any]],
    scorer_error: Optional[str],
) -> List[str]:
    problems = _verify_field_value(field_id, value, repo_root)
    if field_id == "scorer_manifest_sha256":
        try:
            expected = _compute_scorer_manifest_sha256(repo_root)
        except ManifestInputError as error:
            return problems + ["scorer_manifest_sha256: 现场重算失败（%s）" % error]
        if value != expected:
            problems.append(
                "scorer_manifest_sha256: 记录 %s 与现场重算 %s 不符"
                % (str(value)[:12], expected[:12])
            )
        return problems
    if field_id == "manifest_check":
        try:
            expected, extra = _run_make_manifest(repo_root)
        except ManifestInputError as error:
            return problems + ["manifest_check: 现场重算失败（%s）" % error]
        problems.extend(extra)
        if value != expected:
            problems.append(
                "manifest_check: 记录值与现场重算不符（记录 %s / 现场 %s）"
                % (_value_digest(value), _value_digest(expected))
            )
        return problems
    if field_id == "task_package_manifest_sha256":
        try:
            expected, extra = _compute_task_package(repo_root)
        except ManifestInputError as error:
            return problems + ["task_package_manifest_sha256: 现场重算失败（%s）" % error]
        problems.extend(extra)
        if value != expected:
            problems.append(
                "task_package_manifest_sha256: 记录值与现场重算不符"
                "（记录 %s / 现场 %s）" % (_value_digest(value), _value_digest(expected))
            )
        return problems
    if field_id == "first_message_sha256":
        try:
            entries, _, _ = _read_sha256_manifest(repo_root, TASK_PACKAGE_REL + "/manifest.sha256")
            expected, extra = _compute_first_message(repo_root, entries)
        except ManifestInputError as error:
            return problems + ["first_message_sha256: 现场重算失败（%s）" % error]
        problems.extend(extra)
        if value != expected:
            problems.append("first_message_sha256: 记录值与现场重算不符")
        return problems
    if field_id == "configs_after_sha256_txt":
        try:
            expected, extra = _compute_configs_after(repo_root)
        except ManifestInputError as error:
            return problems + ["configs_after_sha256_txt: 现场重算失败（%s）" % error]
        problems.extend(extra)
        if value != expected:
            problems.append(
                "configs_after_sha256_txt: 记录值与现场重算不符"
                "（记录 %s / 现场 %s）" % (_value_digest(value), _value_digest(expected))
            )
        return problems
    if field_id == "criterion_sources":
        if scorer is None:
            return problems + ["criterion_sources: scorer.yaml 读不到（%s），无法重算冻结值" % scorer_error]
        try:
            expected, extra = _compute_criterion_sources(repo_root, scorer)
        except ManifestInputError as error:
            return problems + ["criterion_sources: 现场重算失败（%s）" % error]
        problems.extend(extra)
        if isinstance(value, dict) and value.get("treatment") != expected.get("treatment"):
            problems.append("criterion_sources: 判据原文（memo）的记录值与现场重算不符")
        return problems
    if field_id == "rule_set_identity":
        if scorer is None:
            return problems + ["rule_set_identity: scorer.yaml 读不到（%s），无法重算" % scorer_error]
        try:
            expected, extra = _compute_rule_set_identity(repo_root, scorer)
        except ManifestInputError as error:
            return problems + ["rule_set_identity: 现场重算失败（%s）" % error]
        problems.extend(extra)
        if value != expected:
            problems.append(
                "rule_set_identity: 记录值与现场重算不符"
                "（记录 %s / 现场 %s）" % (_value_digest(value), _value_digest(expected))
            )
        return problems
    if field_id == "hidden_digests":
        try:
            entries, _, _ = _read_sha256_manifest(repo_root, SCORER_REL + "/manifest.sha256")
            expected, extra = _compute_hidden_digests(repo_root, entries)
        except ManifestInputError as error:
            return problems + ["hidden_digests: 现场重算失败（%s）" % error]
        problems.extend(extra)
        if value != expected:
            problems.append("hidden_digests: 记录值与现场重算不符")
        return problems
    return problems


def _verify_manifest_file(path: Path, repo_root: Path) -> Tuple[List[str], List[str], List[str]]:
    """返回（问题, pending 字段, not_applicable 字段）。问题非空即退出 1。"""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ManifestInputError(
            "run-manifest 读不到（%s）" % (error.strerror or type(error).__name__)
        ) from error
    except UnicodeDecodeError as error:
        raise ManifestInputError("run-manifest 不是 UTF-8 文本（%s）" % error) from error
    try:
        payload = json.loads(text, parse_constant=_reject_constant)
    except ValueError as error:
        raise ManifestInputError("run-manifest 不是合法 JSON（%s）" % error) from error

    problems: List[str] = []
    pending: List[str] = []
    not_applicable: List[str] = []
    if not isinstance(payload, dict):
        return ["顶层必须是对象（schema_version / arm / fields）"], pending, not_applicable
    if _absolute_path_in(payload) is not None:
        problems.append("载荷里含绝对路径（run-manifest 不写绝对路径）")
    allowed_top = {"schema_version", "arm", "fields"}
    unknown = sorted(set(payload) - allowed_top)
    missing_top = [key for key in ("schema_version", "arm", "fields") if key not in payload]
    if unknown:
        problems.append("顶层有未知键 %s" % unknown)
    if missing_top:
        problems.append("顶层缺少 %s" % ", ".join(missing_top))
    if payload.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
        problems.append(
            "schema_version=%r 与当前载荷轴 %r 不符"
            % (payload.get("schema_version"), RUN_MANIFEST_SCHEMA_VERSION)
        )
    arm = payload.get("arm")
    if arm not in ARMS:
        problems.append("arm=%r 不在 A/B/C 里" % (arm,))
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        problems.append("fields 必须是对象")
        return problems, pending, not_applicable

    expected_ids = set(RUN_MANIFEST_FIELDS)
    for field_id in RUN_MANIFEST_FIELDS:
        if field_id not in fields:
            problems.append("missing field: %s" % field_id)
    for field_id in sorted(set(fields) - expected_ids):
        problems.append("unexpected field: %s" % field_id)

    scorer: Optional[Dict[str, Any]] = None
    scorer_error: Optional[str] = None
    try:
        scorer = _load_scorer(repo_root)
    except ManifestInputError as error:
        scorer_error = str(error)

    for field_id in RUN_MANIFEST_FIELDS:
        if field_id not in fields:
            continue
        entry = fields[field_id]
        structure = _verify_entry_structure(field_id, entry)
        problems.extend(structure)
        if structure or not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if status == "pending":
            pending.append(field_id)
            continue
        if status == "not_applicable":
            not_applicable.append(field_id)
            problems.extend(_verify_not_applicable(field_id, entry.get("value")))
            continue
        if status != "recorded":
            continue
        try:
            problems.extend(
                _verify_recorded(
                    field_id, entry.get("value"), repo_root, arm, scorer, scorer_error
                )
            )
        except ManifestInputError as error:
            problems.append("%s: 现场重算失败（%s）" % (field_id, error))
        if field_id == "platform_generation" and isinstance(entry.get("value"), dict):
            value = entry["value"]
            first = fields.get("first_message_sha256")
            first_value = first.get("value") if isinstance(first, dict) else None
            model = value.get("model")
            if isinstance(first_value, dict) and isinstance(model, dict):
                if model.get("first_message_sha256") != first_value.get("sha256"):
                    problems.append(
                        "platform_generation: model.first_message_sha256 与 first_message_sha256 字段不符"
                    )
    return problems, pending, not_applicable


def _pending_labels(pending: Sequence[str]) -> List[str]:
    labels: List[str] = []
    if any(field_id in HUMAN_FIELD_IDS for field_id in pending):
        labels.append("human_items_unrecorded")
    if any(field_id not in HUMAN_FIELD_IDS for field_id in pending):
        labels.append("incomplete_freeze")
    return labels


def _do_check(path: Path, repo_root: Path, strict: bool) -> int:
    problems, pending, not_applicable = _verify_manifest_file(path, repo_root)
    if problems:
        for problem in problems:
            print("PROBLEM: " + _sanitize_message(problem, repo_root))
        labels = _pending_labels(pending) if strict and pending else []
        message = "%d 条问题" % len(problems)
        if labels:
            message += "；" + "；".join(labels)
        print("RESULT: FAIL（%s）" % message)
        return EXIT_INVALID
    if strict and pending:
        labels = _pending_labels(pending)
        print(
            "RESULT: FAIL（--strict：%d 条 pending（%s）；%s）"
            % (len(pending), ", ".join(pending), "；".join(labels))
        )
        return EXIT_INVALID
    if pending:
        note = "%d 条 pending（未给 --strict，不算失败）：%s" % (len(pending), ", ".join(pending))
    else:
        note = "0 条 pending"
    if not_applicable:
        note += "；not_applicable：%s" % ", ".join(not_applicable)
    print("RESULT: PASS（18 字段齐全；%s）" % note)
    return EXIT_OK


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_manifest",
        description=(
            "D 门 2 的 run-manifest 生成/校验（18 字段契约；"
            "0=ok / 1=清单不完整或摘要不符 / 2=用法或读不到声明）"
        ),
    )
    parser.add_argument("--arm", choices=list(ARMS), help="生成模式：臂 A/B/C")
    parser.add_argument("--out", type=Path, metavar="PATH", help="生成模式：输出 JSON（必须在仓库内）")
    parser.add_argument("--check", type=Path, metavar="PATH", help="校验模式：读一份已有 run-manifest")
    parser.add_argument("--strict", action="store_true", help="配合 --check：pending 也算失败")
    parser.add_argument(
        "--reference-tree",
        type=Path,
        dest="reference_tree",
        metavar="DIR",
        help="生成模式：参考树目录（A 维度读数对象，不冻结）",
    )
    parser.add_argument(
        "--arm-facts",
        type=Path,
        dest="arm_facts",
        metavar="JSON",
        help="生成模式：臂事实 JSON（兼容 C 臂完整 run-manifest）",
    )
    parser.add_argument(
        "--run-record",
        type=Path,
        dest="run_record",
        metavar="JSON",
        help="生成模式：run-record（至少 schema_version / arm / dimensions{T,C,A}）",
    )
    parser.add_argument(
        "--platform-facts",
        type=Path,
        dest="platform_facts",
        metavar="JSON",
        help="生成模式：platform_generation 事实 JSON（宿主/沙箱/配置与审批摘要/批次/模型/起点；1.1 起）",
    )
    parser.add_argument(
        "--human-items",
        type=Path,
        dest="human_items",
        metavar="JSON",
        help="生成模式：H1–H4 人工项 JSON（工具只记录、不代填）",
    )
    return parser


def _generate(args: argparse.Namespace, repo_root: Path) -> int:
    if args.strict:
        raise ManifestInputError("--strict 只能与 --check 同用")
    if args.arm is None or args.out is None:
        raise ManifestInputError("生成模式必须给 --arm {A,B,C} 与 --out <PATH>")
    out_resolved = args.out.resolve()
    try:
        out_rel = out_resolved.relative_to(repo_root).as_posix()
    except ValueError as error:
        raise ManifestInputError("--out 必须在仓库内（清单里只有仓库相对路径）") from error
    if out_resolved.is_dir():
        raise ManifestInputError("--out 指向的是目录，需要一个文件路径")

    reference_tree: Optional[Path] = None
    if args.reference_tree is not None:
        reference_tree = args.reference_tree.resolve()
        if not reference_tree.is_dir():
            raise ManifestInputError(
                "--reference-tree 指向的目录不存在：%s"
                % _display_path(args.reference_tree, repo_root)
            )

    arm_facts = None
    if args.arm_facts is not None:
        arm_facts = _normalize_arm_facts(args.arm_facts.resolve(), args.arm, repo_root)
    readings = None
    if args.run_record is not None:
        readings = _normalize_run_record(args.run_record.resolve(), args.arm, repo_root)
    platform_facts = None
    if args.platform_facts is not None:
        platform_facts = _normalize_platform_facts(args.platform_facts.resolve(), repo_root)
    human_items = None
    human_source = None
    if args.human_items is not None:
        human_items = _normalize_human_items(args.human_items.resolve())
        human_source = _display_path(args.human_items.resolve(), repo_root)

    scorer = _load_scorer(repo_root)
    _verify_field_contract(scorer)
    builder = _Builder(
        repo_root,
        args.arm,
        scorer,
        out_rel,
        reference_tree,
        arm_facts,
        readings,
        platform_facts,
        human_items,
        human_source,
    )
    payload = builder.build()
    text = _render_json(payload)
    try:
        out_resolved.parent.mkdir(parents=True, exist_ok=True)
        out_resolved.write_bytes(text.encode("utf-8"))
    except OSError as error:
        raise ManifestInputError(
            "--out 写不了（%s）：%s"
            % (_display_path(out_resolved, repo_root), error.strerror or type(error).__name__)
        ) from error

    statuses = [entry["status"] for entry in payload["fields"].values()]
    recorded = statuses.count("recorded")
    pending = statuses.count("pending")
    not_applicable = statuses.count("not_applicable")
    combined = payload["fields"]["scorer_manifest_sha256"]["value"]
    manifest_exit = payload["fields"]["manifest_check"]["value"]["exit_code"]
    print(
        "run-manifest arm=%s fields=%d recorded=%d pending=%d not_applicable=%d "
        "manifest_check=%d combined_digest=sha256:%s"
        % (args.arm, len(statuses), recorded, pending, not_applicable, manifest_exit, combined)
    )
    if builder.problems:
        for problem in builder.problems:
            print("run-manifest: 清单不合格：" + _sanitize_message(problem, repo_root), file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


def run(argv: Optional[Sequence[str]] = None) -> int:
    """CLI 入口；返回 0 / 1 / 2。argparse 的用法错误仍按惯例抛 SystemExit(2)。"""

    args = build_parser().parse_args(argv)
    repo_root = _find_repo_root(Path(__file__).resolve().parent)
    try:
        if args.check is not None:
            if args.arm is not None or args.out is not None:
                raise ManifestInputError("--check 不能与 --arm / --out 同用")
            if (
                args.reference_tree is not None
                or args.arm_facts is not None
                or args.run_record is not None
                or args.human_items is not None
            ):
                raise ManifestInputError("--check 不能与生成模式的输入参数同用")
            return _do_check(args.check, repo_root, args.strict)
        return _generate(args, repo_root)
    except ManifestInputError as error:
        print("run-manifest: " + _sanitize_message(str(error), repo_root), file=sys.stderr)
        return error.exit_code


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

r"""三臂脚手架：给定任务包目录 + 臂（A / B / C）+ 目标目录，建出一棵**冻结基线**的臂树。

它回答什么
==========

一次对比实验最容易被悄悄破坏的东西是「两臂的起点不一样」。本脚本把起点做成可核对的产品：

- **基线**：调用任务包自己的 `reset-arm.py`（若存在），否则按 `baseline/` 复制；
  两者都没有就拒绝（退出 2）——不猜基线，也不用空树当基线；
- **治理配置**（A / B）：从臂配置目录**原样**复制 `.policy/` 下的五个受控文件名，别的一律拒绝；
  缺 `tool-registry.approved.json` / `approval.json` 时写**未签字的占位**并在清单里点名；
- **C 臂**：不写任何治理配置，只写一份说明文件（或 `--no-note` 连说明都不写）；
- **arm-manifest.json**：基线组合摘要、任务包摘要、臂配置摘要、首消息摘要、命令族清单。

三条命令
========

    python scaffold_arms.py --task-package <任务包> --arm A --target <臂树> --arm-config <臂配置>
    python scaffold_arms.py --task-package <任务包> --arm C --target <臂树>
    python scaffold_arms.py --task-package <任务包> --arm A --target <臂树> --check

只写两个地方：**目标目录**（臂树）与 `--manifest-out`（默认是臂树的兄弟路径，不进任务树）。
被调用的 `reset-arm.py` 会在臂树的父目录写它的 `reset-manifest.json`——那是那个工具
自己的行为，本脚本在 `writes.outside_target` 里如实列出，不假装没发生。

载荷自己的版本轴（AGENTS 第 55 条）
=================================

`AB_ARM_MANIFEST_SCHEMA_VERSION = "1.0"`——**首次建轴**。加键 / 改语义必须按第 55 条递增，
并把 README 与 `tests/unit/test_ab_harness.py` 同批改。

边界（引用这份清单之前先看）
==========================

1. **不替使用者签审批条子**：`approval.json` 与 `tool-registry.approved.json` 的占位是
   「未签字」的形状，不是可用的授权；`run_session.py` 见到占位会拒绝发车。
2. **`--check` 不重建**：它只重算并比对，所以它能用在真实 run 之前，也不会不小心把树改掉。
3. **命令族清单是定形扫描**：只用标准库，因此只认注册表 1.4 这一种缩进形状；形状不符
   一律报错（退出 1），绝不猜。整个注册表文件的摘要仍在 `policy.files` 里。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _ab_harness_common import (  # noqa: E402
    EXIT_INVALID,
    EXIT_OK,
    HarnessInputError,
    combined_digest,
    display_path,
    find_repo_root,
    first_line,
    is_under,
    load_json,
    manifest_lines,
    render_json,
    sanitize_text,
    sha256_bytes,
    sha256_file,
    walk_files,
    write_text_lf,
)

#: 臂清单载荷自己的版本轴；加键 / 改语义必须按 AGENTS 第 55 条递增。
AB_ARM_MANIFEST_SCHEMA_VERSION = "1.0"

ARMS: Tuple[str, ...] = ("A", "B", "C")

#: A / B 臂 .policy/ 下**认得**的文件；其它文件一律拒绝（不夹带审计 / 台账 / 缓存）。
POLICY_ROLES: Tuple[Tuple[str, str], ...] = (
    ("dsh-adapter.yaml", "adapter"),
    ("hooks.json", "hooks"),
    ("tool-registry.local.yaml", "registry"),
    ("tool-registry.approved.json", "registry_approved"),
    ("approval.json", "approval"),
)

#: A / B 臂必须由臂配置目录提供的三个文件（其余两个可以退化成未签字的占位）。
REQUIRED_POLICY_FILES: Tuple[str, ...] = (
    "dsh-adapter.yaml",
    "hooks.json",
    "tool-registry.local.yaml",
)

#: 未签字占位的形状标记：与真件不同，消费方读不懂就失败关闭。
PLACEHOLDER_SCHEMA = "ab-harness.unsigned-placeholder/1"
PLACEHOLDER_NOTE = (
    "占位：本脚手架不替使用者签字。请自行签发（registry 用 "
    "python -m enforcement.cli registry --approve --reviewer <name>；审批条子按任务需要签发），"
    "否则 run_session.py 拒绝发车。"
)

#: C 臂不治理时唯一的写入（--no-note 时连它也不写）。
NOT_GOVERNED_NOTE = ".policy/NOT-GOVERNED.md"

NOT_GOVERNED_TEXT = """# 本臂不治理（C）

这棵树是 C 臂：**没有任何治理接线**。

- 没有 dsh-adapter.yaml、没有 hooks.json、没有工具注册表、没有已审核哈希、没有审批条子；
- 运行时不挂覆盖层，不加载 policy-hook 插件；
- 因此本会话里不存在策略判定，也没有审计与台账可读。**这是 C 臂的定义，不是缺陷。**

不要往这里补治理配置：补上之后它就不再是对照臂。臂的身份、基线摘要与冻结摘要记在
臂清单（arm-manifest.json）里，不在本文件。
"""

#: 遍历臂树时忽略的缓存目录（宿主沙箱留下的残留，不是任务文件）。
TREE_IGNORE: Tuple[str, ...] = (
    "**/__pycache__/**",
    "**/*.pyc",
    "**/.pytest_cache/**",
    "**/.ruff_cache/**",
    "**/.mypy_cache/**",
)

#: 首消息文件的两个约定位置（`--first-message` 可覆盖；两个都找不到就是用法错误）。
FIRST_MESSAGE_CANDIDATES: Tuple[str, ...] = (
    "task-package/first-message.txt",
    "first-message.txt",
)

#: 命令族扫描只认这一种缩进形状（注册表 1.4）；形状不符一律报错，绝不猜。
_TOOL_ID = re.compile(r"^ {2}- id: (\S+)\s*$")
_KEY4 = re.compile(r"^ {4}([A-Za-z_][A-Za-z0-9_]*):(.*)$")
_FAMILY_ID = re.compile(r"^ {6}- id: (\S+)\s*$")
_PATTERNS_KEY = re.compile(r"^ {8}patterns:\s*$")
_KEY8 = re.compile(r"^ {8}[A-Za-z_][A-Za-z0-9_]*:(.*)$")
_PATTERN_ITEM = re.compile(r"^ {10}- (.*)$")
_ITEM6 = re.compile(r"^ {6}- (.*)$")

# --------------------------------------------------------------------------- 基本动作


def _tree_files(root: Path, label: str) -> Tuple[List[str], List[str], List[str]]:
    """臂树里的文件（相对臂树）；返回（文件, 不可枚举目录, 被忽略缓存）。"""

    return walk_files(root, TREE_IGNORE, label)


def _hashes(root: Path, label: str) -> Tuple[Dict[str, str], List[str], List[str]]:
    files, unreadable, ignored = _tree_files(root, label)
    return {item: sha256_file(root / item, item) for item in files}, unreadable, ignored


def _copy_tree(source: Path, destination: Path) -> None:
    """把 source 的目录树原样复制到 destination（不跟随符号链接）。"""

    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)


def validate_target(repo_root: Path, target: Path, protected: Sequence[Path]) -> None:
    """目标目录的安全检查：越界、覆盖仓库、互相包含一律拒绝（声明不成立 = 退出 2）。"""

    resolved = target.resolve()
    if resolved == repo_root or is_under(repo_root, resolved):
        raise HarnessInputError(
            "目标目录不能是仓库根本身或它的祖先：会覆盖整棵仓库 —— %s"
            % display_path(resolved, repo_root)
        )
    git_dir = repo_root / ".git"
    if is_under(resolved, git_dir):
        raise HarnessInputError("目标目录不能落在 .git 里：%s" % display_path(resolved, repo_root))
    for source in protected:
        if is_under(resolved, source) or is_under(source, resolved):
            raise HarnessInputError(
                "目标目录与输入目录互相包含（%s）：臂树必须是一个独立的树"
                % display_path(source, repo_root)
            )
    if resolved.exists() and not resolved.is_dir():
        raise HarnessInputError("目标已存在且不是目录：%s" % display_path(resolved, repo_root))
    if resolved.is_dir() and any(resolved.iterdir()):
        raise HarnessInputError(
            "目标目录非空（%s）：不覆盖既有臂树。换一个目录，或自己先删掉它"
            % display_path(resolved, repo_root)
        )


def _loads_json(text: str) -> Any:
    """容忍失败的 JSON 解析：reset-arm.py 自己的读数只作参考，读不出就不记，不拦截建树。"""

    try:
        return json.loads(text)
    except ValueError:
        return None


def build_baseline(
    repo_root: Path,
    task_package: Path,
    target: Path,
    *,
    use_reset_arm: bool,
) -> Dict[str, Any]:
    """建基线树：优先调用任务包的 reset-arm.py，其次复制 baseline/；两者都没有就退出 2。"""

    reset_arm = task_package / "reset-arm.py"
    baseline_dir = task_package / "baseline"
    if use_reset_arm and reset_arm.is_file():
        completed = subprocess.run(
            [sys.executable, str(reset_arm), "--target", str(target)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        if completed.returncode != 0:
            detail = first_line(completed.stderr or completed.stdout or "", 240)
            raise HarnessInputError(
                "reset-arm.py 退出码 %d（%s）" % (completed.returncode, sanitize_text(detail, repo_root)),
                exit_code=EXIT_INVALID,
            )
        recorded = ""
        for line in (completed.stdout or "").splitlines():
            if line.startswith("RESET-ARM-JSON: "):
                recorded = line[len("RESET-ARM-JSON: ") :].strip()
        source = "reset_arm_script"
        source_path = reset_arm
        side_manifest = target.parent / "reset-manifest.json"
    elif baseline_dir.is_dir():
        _copy_tree(baseline_dir, target)
        recorded = ""
        source = "baseline_dir"
        source_path = baseline_dir
        side_manifest = None
    else:
        raise HarnessInputError(
            "任务包既没有可用的 reset-arm.py 也没有 baseline/ 目录：不猜基线 —— %s"
            % display_path(task_package, repo_root)
        )
    files, unreadable, ignored = _hashes(target, display_path(target, repo_root))
    baseline: Dict[str, Any] = {
        "source": source,
        "source_path": display_path(source_path, repo_root),
        "file_count": len(files),
        "combined_digest": combined_digest(manifest_lines(files.items())),
        "unreadable": unreadable,
        "ignored": ignored,
        "files": [{"path": path, "sha256": digest} for path, digest in sorted(files.items())],
        "tool_reported": {},
        "side_artifact": display_path(side_manifest, repo_root) if side_manifest else None,
    }
    if recorded:
        try:
            tool_payload = _loads_json(recorded)
        except HarnessInputError:
            tool_payload = None
        if isinstance(tool_payload, dict):
            baseline["tool_reported"] = {
                "baseline_manifest_sha256": tool_payload.get("baseline_manifest_sha256"),
                "file_count": tool_payload.get("file_count"),
                "audit_start_lines": tool_payload.get("audit_start_lines"),
            }
    return baseline


# --------------------------------------------------------------------------- .policy


def _placeholder(name: str) -> str:
    """未签字占位的字节（确定性：没有时戳、没有本机路径）。"""

    return render_json(
        {
            "schema": PLACEHOLDER_SCHEMA,
            "status": "unsigned",
            "file": name,
            "note": PLACEHOLDER_NOTE,
        }
    )


def read_arm_config(repo_root: Path, arm_config: Path) -> Dict[str, bytes]:
    """读臂配置目录里**认得**的五个文件；出现别的文件一律拒绝（不夹带审计 / 台账）。"""

    if not arm_config.is_dir():
        raise HarnessInputError("臂配置目录不存在：%s" % display_path(arm_config, repo_root))
    files, unreadable, _ignored = walk_files(arm_config, (), display_path(arm_config, repo_root))
    if unreadable:
        raise HarnessInputError(
            "臂配置目录里有不可枚举的子目录：%s" % ", ".join(unreadable), exit_code=EXIT_INVALID
        )
    allowed = {name for name, _role in POLICY_ROLES}
    unknown = [item for item in files if item not in allowed]
    if unknown:
        raise HarnessInputError(
            "臂配置目录里有未声明的文件 %s —— 只接受 %s；其余文件（审计 / 台账 / 缓存）"
            "不该被复制进臂树" % (unknown, sorted(allowed))
        )
    return {item: (arm_config / item).read_bytes() for item in files}


def write_policy(
    repo_root: Path,
    arm: str,
    arm_config: Optional[Path],
    target: Path,
    *,
    write_note: bool,
) -> Dict[str, Any]:
    """写 .policy/：A / B 是治理配置（含未签字占位），C 只有一份说明文件。"""

    policy_dir = target / ".policy"
    if arm == "C":
        policy_dir.mkdir(parents=True, exist_ok=True)
        files: List[Dict[str, str]] = []
        if write_note:
            write_text_lf(target / NOT_GOVERNED_NOTE, NOT_GOVERNED_TEXT)
            files.append(
                {
                    "path": NOT_GOVERNED_NOTE,
                    "sha256": sha256_bytes(NOT_GOVERNED_TEXT.encode("utf-8")),
                    "role": "not_governed_note",
                }
            )
        return {
            "status": "not_governed",
            "source_path": None,
            "files": files,
            "combined_digest": combined_digest(manifest_lines((item["path"], item["sha256"]) for item in files)),
            "placeholders": [],
            "note": "C 臂不治理：没有 dsh-adapter.yaml / hooks.json / 注册表 / 已审核哈希 / 审批条子",
        }

    if arm_config is None:
        raise HarnessInputError("臂 %s 必须给 --arm-config（或任务包里有 arms/%s/）" % (arm, arm))
    provided = read_arm_config(repo_root, arm_config)
    missing = [name for name in REQUIRED_POLICY_FILES if name not in provided]
    if missing:
        raise HarnessInputError(
            "臂配置目录缺必需文件 %s（%s）" % (missing, display_path(arm_config, repo_root))
        )
    roles = dict(POLICY_ROLES)
    policy_dir.mkdir(parents=True, exist_ok=True)
    placeholders: List[str] = []
    for name, _role in POLICY_ROLES:
        destination = policy_dir / name
        if name in provided:
            destination.write_bytes(provided[name])
            continue
        destination.write_text(_placeholder(name), encoding="utf-8", newline="\n")
        placeholders.append(".policy/" + name)
    files = []
    for name, role in POLICY_ROLES:
        relative = ".policy/" + name
        files.append(
            {"path": relative, "sha256": sha256_file(policy_dir / name, relative), "role": roles[name]}
        )
    return {
        "status": "governed",
        "source_path": display_path(arm_config, repo_root),
        "files": files,
        "combined_digest": combined_digest(manifest_lines((item["path"], item["sha256"]) for item in files)),
        "placeholders": sorted(placeholders),
        "note": "治理配置由臂配置目录原样复制；占位文件未签字，run_session.py 见到它会拒绝发车",
    }


# --------------------------------------------------------------------------- 命令族（定形扫描）


def scan_command_families(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """从注册表 YAML 抽命令族清单；返回（工具列表, 问题）。

    只用标准库，因此这是一个**定形**扫描：只认注册表 1.4 的缩进形状。任何不认识的形状都
    记成问题（调用方据此失败关闭），绝不跳过——跳过会让清单看起来「命令族 0 条」，
    而那不是「没有命令族」，是「没看懂」。
    """

    tools: List[Dict[str, Any]] = []
    problems: List[str] = []
    current: Optional[Dict[str, Any]] = None
    mode: Optional[str] = None
    family: Optional[Dict[str, Any]] = None
    in_patterns = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tool_match = _TOOL_ID.match(line)
        if tool_match:
            current = {
                "tool": tool_match.group(1),
                "allowed_command_count": 0,
                "families": [],
            }
            tools.append(current)
            mode = None
            family = None
            in_patterns = False
            continue
        key_match = _KEY4.match(line)
        if key_match:
            key = key_match.group(1)
            mode = "allowed" if key == "allowed_commands" else ("families" if key == "command_families" else None)
            in_patterns = False
            if mode is None:
                family = None
            continue
        if mode == "allowed":
            if _ITEM6.match(line) and current is not None:
                current["allowed_command_count"] += 1
            else:
                problems.append("第 %d 行落在 allowed_commands 里但形状不认识" % number)
            continue
        if mode == "families":
            family_match = _FAMILY_ID.match(line)
            if family_match:
                family = {"id": family_match.group(1), "pattern_count": 0}
                if current is None:
                    problems.append("第 %d 行的命令族不属于任何工具" % number)
                else:
                    current["families"].append(family)
                in_patterns = False
                continue
            if _PATTERNS_KEY.match(line):
                in_patterns = True
                continue
            key8_match = _KEY8.match(line)
            if key8_match:
                in_patterns = False
                continue
            if _PATTERN_ITEM.match(line) and in_patterns and family is not None:
                family["pattern_count"] += 1
                continue
            problems.append("第 %d 行落在 command_families 里但形状不认识" % number)
            continue
    return tools, problems


def command_families_section(
    repo_root: Path,
    policy: Dict[str, Any],
    target: Path,
) -> Dict[str, Any]:
    """臂清单里的命令族段；C 臂明确写成 not_applicable（它不是缺陷，是可读的事实）。"""

    if policy["status"] != "governed":
        return {
            "status": "not_applicable",
            "source": None,
            "tools": [],
            "problems": ["C 臂不治理：没有工具注册表，因此没有命令族清单"],
        }
    relative = ".policy/tool-registry.local.yaml"
    registry = target / relative
    try:
        text = registry.read_text(encoding="utf-8")
    except OSError as error:
        return {
            "status": "unreadable",
            "source": {"path": relative, "sha256": None},
            "tools": [],
            "problems": ["注册表读不到（%s）" % type(error).__name__],
        }
    tools, problems = scan_command_families(text)
    return {
        "status": "parsed" if not problems else "unparsed",
        "source": {"path": relative, "sha256": sha256_file(registry, relative)},
        "tools": tools,
        "problems": problems,
    }


# --------------------------------------------------------------------------- 载荷与校验


def _package_section(repo_root: Path, task_package: Path) -> Dict[str, Any]:
    files, unreadable, ignored = _hashes(task_package, display_path(task_package, repo_root))
    return {
        "path": display_path(task_package, repo_root),
        "file_count": len(files),
        "combined_digest": combined_digest(manifest_lines(files.items())),
        "unreadable": unreadable,
        "ignored_count": len(ignored),
    }


def _first_message_section(repo_root: Path, first_message: Path) -> Dict[str, Any]:
    relative = display_path(first_message, repo_root)
    return {
        "path": relative,
        "sha256": sha256_file(first_message, relative),
        "bytes": first_message.stat().st_size,
    }


def _expected_tree(baseline: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, str]:
    """臂树应有的文件 → 摘要（基线 + 我方写入的 .policy 文件）。"""

    expected: Dict[str, str] = {}
    for item in baseline["files"]:
        expected[item["path"]] = item["sha256"]
    for item in policy["files"]:
        expected[item["path"]] = item["sha256"]
    return expected


def _compare_tree(target: Path, expected: Dict[str, str], repo_root: Path) -> List[str]:
    """双向比对臂树；返回问题（缺 / 漂移 / 多出 / 不可枚举）。"""

    problems: List[str] = []
    if not target.is_dir():
        return ["臂树目录不存在：%s" % display_path(target, repo_root)]
    actual, unreadable, _ignored = _hashes(target, display_path(target, repo_root))
    for item in unreadable:
        problems.append("臂树里有不可枚举目录：%s" % item)
    for path in sorted(set(expected) - set(actual)):
        problems.append("清单里有、臂树里没有：%s" % path)
    for path in sorted(set(actual) - set(expected)):
        problems.append("臂树里有、清单里没有：%s" % path)
    for path in sorted(set(actual) & set(expected)):
        if actual[path] != expected[path]:
            problems.append("sha256 漂移：%s" % path)
    return problems


def build_payload(
    repo_root: Path,
    *,
    arm: str,
    task_package: Path,
    target: Path,
    baseline: Dict[str, Any],
    policy: Dict[str, Any],
    families: Dict[str, Any],
    first_message: Dict[str, Any],
    manifest_out: Path,
) -> Dict[str, Any]:
    """组装 arm-manifest 载荷（不写盘）。"""

    expected = _expected_tree(baseline, policy)
    outside = [manifest_out]
    if baseline.get("side_artifact"):
        outside.append(repo_root / str(baseline["side_artifact"]))
    return {
        "schema_version": AB_ARM_MANIFEST_SCHEMA_VERSION,
        "arm": arm,
        "task": {
            "id": task_package.name,
            "package": _package_section(repo_root, task_package),
        },
        "target": {"path": display_path(target, repo_root), "file_count": len(expected)},
        "baseline": baseline,
        "policy": policy,
        "first_message": first_message,
        "command_families": families,
        "writes": {
            "in_target": sorted(expected),
            "outside_target": [display_path(item, repo_root) for item in outside],
        },
    }


def validate_manifest_shape(payload: Any) -> Tuple[Dict[str, Any], List[str]]:
    """判臂清单结构与版本；未知键与未知版本一律拒收（AGENTS 第 3 / 55 条）。"""

    if not isinstance(payload, dict):
        return {}, ["臂清单的顶层不是对象"]
    required = (
        "schema_version",
        "arm",
        "task",
        "target",
        "baseline",
        "policy",
        "first_message",
        "command_families",
        "writes",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        return {}, ["臂清单缺字段 %s" % missing]
    extra = sorted(set(payload) - set(required))
    if extra:
        return {}, ["臂清单有未知字段 %s（加键必须升 AB_ARM_MANIFEST_SCHEMA_VERSION）" % extra]
    if payload.get("schema_version") != AB_ARM_MANIFEST_SCHEMA_VERSION:
        return {}, [
            "schema_version 必须是 %r（读到 %r）"
            % (AB_ARM_MANIFEST_SCHEMA_VERSION, payload.get("schema_version"))
        ]
    if payload.get("arm") not in ARMS:
        return {}, ["arm 必须是 %s 之一（读到 %r）" % (list(ARMS), payload.get("arm"))]
    for key in ("baseline", "policy"):
        section = payload.get(key)
        if not isinstance(section, dict) or not isinstance(section.get("files"), list):
            return {}, ["%s.files 必须是列表" % key]
        for index, item in enumerate(section["files"]):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                return {}, ["%s.files[%d] 缺 path" % (key, index)]
            if not isinstance(item.get("sha256"), str):
                return {}, ["%s.files[%d] 缺 sha256" % (key, index)]
    return payload, []


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从冻结基线建出一棵臂树（A / B 带治理配置，C 不治理），并写出 arm-manifest.json"
    )
    parser.add_argument("--task-package", required=True, help="任务包目录（含 reset-arm.py 或 baseline/）")
    parser.add_argument("--arm", required=True, choices=list(ARMS), help="实验臂")
    parser.add_argument("--target", required=True, help="臂树目录（必须不存在或为空）")
    parser.add_argument(
        "--arm-config",
        default=None,
        help="臂配置目录（A / B 必需；默认 <.task-package>/arms/<arm>），C 臂不接受",
    )
    parser.add_argument("--first-message", default=None, help="首消息文件（默认按任务包约定探测）")
    parser.add_argument("--manifest-out", default=None, help="arm-manifest 路径（默认 <target>.arm-manifest.json）")
    parser.add_argument("--check", action="store_true", help="只校验已建好的臂树，不写任何文件")
    parser.add_argument("--no-note", action="store_true", help="C 臂不写说明文件（连 .policy 都不建）")
    parser.add_argument("--no-reset-arm", action="store_true", help="不调用任务包的 reset-arm.py，只按 baseline/ 复制")
    parser.add_argument("--repo-root", default=None, help="仓库根（默认从脚本位置向上找 .git）")
    return parser


def _resolve(raw: str, repo_root: Path) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _manifest_path(args: argparse.Namespace, target: Path) -> Path:
    if args.manifest_out:
        return Path(args.manifest_out).resolve()
    return target.parent / (target.name + ".arm-manifest.json")


def _first_message_path(
    repo_root: Path, task_package: Path, raw: Optional[str]
) -> Path:
    if raw:
        return _resolve(raw, repo_root)
    for relative in FIRST_MESSAGE_CANDIDATES:
        candidate = task_package / relative
        if candidate.is_file():
            return candidate.resolve()
    raise HarnessInputError(
        "找不到首消息文件：给了 --first-message 就用它，否则任务包里要有 %s"
        % list(FIRST_MESSAGE_CANDIDATES)
    )


def _arm_config_path(
    repo_root: Path, task_package: Path, arm: str, raw: Optional[str]
) -> Optional[Path]:
    if arm == "C":
        if raw:
            raise HarnessInputError("C 臂不治理：不接受 --arm-config")
        return None
    if raw:
        return _resolve(raw, repo_root)
    candidate = task_package / "arms" / arm
    if candidate.is_dir():
        return candidate.resolve()
    raise HarnessInputError(
        "臂 %s 必须给 --arm-config（任务包里也没有 arms/%s/）" % (arm, arm)
    )


def write_arm(
    repo_root: Path,
    *,
    arm: str,
    task_package: Path,
    arm_config: Optional[Path],
    target: Path,
    first_message: Path,
    manifest_out: Path,
    write_note: bool,
    use_reset_arm: bool,
) -> int:
    """建臂树并写 arm-manifest；返回退出码（0 成立 / 1 事后自检失败）。"""

    protected = [task_package] + ([arm_config] if arm_config is not None else [])
    validate_target(repo_root, target, [item for item in protected if item is not None])
    if not first_message.is_file():
        raise HarnessInputError("首消息文件不存在：%s" % display_path(first_message, repo_root))
    target.mkdir(parents=True, exist_ok=True)
    baseline = build_baseline(repo_root, task_package, target, use_reset_arm=use_reset_arm)
    if baseline["unreadable"] or not baseline["files"]:
        raise HarnessInputError(
            "基线树不成立（文件 %d 个、不可枚举目录 %d 个）"
            % (len(baseline["files"]), len(baseline["unreadable"])),
            exit_code=EXIT_INVALID,
        )
    policy = write_policy(repo_root, arm, arm_config, target, write_note=write_note)
    families = command_families_section(repo_root, policy, target)
    if families["problems"] and families["status"] != "not_applicable":
        raise HarnessInputError(
            "命令族清单抽不出来（%s）：不写一份假装是空的清单" % "; ".join(families["problems"]),
            exit_code=EXIT_INVALID,
        )
    payload = build_payload(
        repo_root,
        arm=arm,
        task_package=task_package,
        target=target,
        baseline=baseline,
        policy=policy,
        families=families,
        first_message=_first_message_section(repo_root, first_message),
        manifest_out=manifest_out,
    )
    problems = _compare_tree(target, _expected_tree(baseline, policy), repo_root)
    if problems:
        for problem in problems:
            print("PROBLEM: %s" % problem, file=sys.stderr)
        print("RESULT: FAIL（臂树与写盘意图不一致；清单**没有**写出）", file=sys.stderr)
        return EXIT_INVALID
    write_text_lf(manifest_out, render_json(payload))
    print(
        "scaffold-arms: arm=%s target=%s files=%d baseline=%s policy=%s"
        % (
            arm,
            payload["target"]["path"],
            payload["target"]["file_count"],
            baseline["combined_digest"],
            policy["status"],
        )
    )
    if policy["placeholders"]:
        print(
            "scaffold-arms: 未签字占位 %s —— 使用者必须自己签发，否则 run_session 拒绝发车"
            % policy["placeholders"]
        )
    print("scaffold-arms: manifest=%s" % display_path(manifest_out, repo_root))
    return EXIT_OK


def check_arm(
    repo_root: Path,
    *,
    arm: str,
    target: Path,
    manifest_out: Path,
) -> int:
    """只校验：臂树与 arm-manifest 是否仍然逐字节一致；不写任何文件。"""

    if not manifest_out.is_file():
        raise HarnessInputError("臂清单不存在：%s" % display_path(manifest_out, repo_root))
    payload = load_json(manifest_out, display_path(manifest_out, repo_root))
    payload, problems = validate_manifest_shape(payload)
    if problems:
        for problem in problems:
            print("PROBLEM: %s" % problem)
        print("RESULT: FAIL（manifest_invalid）")
        return EXIT_INVALID
    if payload["arm"] != arm:
        print("PROBLEM: 臂清单写的是 %r，--arm 给的是 %r" % (payload["arm"], arm))
        print("RESULT: FAIL（arm_mismatch）")
        return EXIT_INVALID
    expected = _expected_tree(payload["baseline"], payload["policy"])
    problems = _compare_tree(target, expected, repo_root)
    first = payload.get("first_message") or {}
    relative = first.get("path")
    if isinstance(relative, str) and relative not in ("", "<outside-workspace>"):
        source = repo_root / relative
        if not source.is_file():
            problems.append("首消息文件不存在：%s" % relative)
        elif sha256_file(source, relative) != first.get("sha256"):
            problems.append("首消息文件漂移：%s" % relative)
    for problem in problems:
        print("PROBLEM: %s" % problem)
    if problems:
        print("RESULT: FAIL（%d 条问题）" % len(problems))
        return EXIT_INVALID
    print(
        "RESULT: PASS arm=%s files=%d baseline=%s policy=%s placeholders=%d"
        % (
            arm,
            len(expected),
            payload["baseline"]["combined_digest"],
            payload["policy"]["status"],
            len(payload["policy"].get("placeholders") or []),
        )
    )
    return EXIT_OK


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        repo_root = find_repo_root(_HERE, Path(args.repo_root) if args.repo_root else None)
        task_package = _resolve(args.task_package, repo_root)
        if not task_package.is_dir():
            raise HarnessInputError("任务包目录不存在：%s" % display_path(task_package, repo_root))
        target = _resolve(args.target, repo_root)
        manifest_out = _manifest_path(args, target)
        if args.check:
            return check_arm(repo_root, arm=args.arm, target=target, manifest_out=manifest_out)
        arm_config = _arm_config_path(repo_root, task_package, args.arm, args.arm_config)
        first_message = _first_message_path(repo_root, task_package, args.first_message)
        return write_arm(
            repo_root,
            arm=args.arm,
            task_package=task_package,
            arm_config=arm_config,
            target=target,
            first_message=first_message,
            manifest_out=manifest_out,
            write_note=not args.no_note,
            use_reset_arm=not args.no_reset_arm,
        )
    except HarnessInputError as error:
        print("scaffold-arms: %s" % error, file=sys.stderr)
        return error.exit_code


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(argv)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

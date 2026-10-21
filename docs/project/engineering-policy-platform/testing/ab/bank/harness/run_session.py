r"""一次 run 的包装器：**默认 dry-run，不发真机**；只有 `--execute` 才真跑一次 dsh 会话。

它回答什么
==========

「这次 run 到底是怎么跑起来的」不该只活在一个人的终端历史里。本脚本把一次 run 拆成三段，
每段都能被单独核对：

1. **前置**（`--execute` 与 dry-run 都跑，退出码同义）：
   freeze 清单 `--check --strict` 通过、arm-manifest 存在且臂树没漂、首消息摘要对得上、
   `DSH_HOME` 是隔离目录、覆盖层模板的三处参数齐、宿主版本与环境变量有记录、
   缺凭据 / 缺 dsh / 沙箱形态不允许 → **不发车**（退出 2，逐条写 reason）；
2. **执行**（只有 `--execute`）：`<install>/resources/runtime/cli/bin/dsh.cmd
   --profile headless --patch <overlay> -`，首消息走 stdin；
   `DEEPSEEK_API_KEY` **只从启动环境读**，不打印、不落盘、不进载荷（日志里按值脱敏）；
3. **读数**：dsh exit、审计 / 台账 JSONL 的**按偏移增量**（不依赖「前后集合差」）、树 diff、耗时
   （耗时只进日志与 stdout，**不进载荷**）。

结果载荷 `run.json` 的字段是协议（见 README §3）：`schema_version` / `arm` /
`task` / `host` / `sandbox` / `freeze` / `exit` / `readings`。
**不带绝对路径、不带凭据、不带时戳**；加键必须升 `AB_RUN_SCHEMA_VERSION`（AGENTS 第 55 条）。

边界（三条，README 里也写）
=========================

1. **不替使用者签审批条子**：臂树里还有未签字占位时拒绝发车。
2. **`workspace-write` 下 Hook spawn 会 EPERM**（2026-10-21 读数 §2.3）：A / B 臂要求
   `--sandbox danger-full-access` 显式声明；C 臂不挂 Hook，两种都行。`unknown` 一律拒绝。
3. **不自动重试、不并发**：一次调用一次会话；同一工作树不能并跑 `ci_local`（那份锁不归本脚本管）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _ab_harness_common import (  # noqa: E402
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    OUTSIDE_WORKSPACE,
    HarnessInputError,
    check_no_absolute_paths,
    display_path,
    find_repo_root,
    first_line,
    is_under,
    load_json,
    matches_any,
    redact_secret,
    render_json,
    sanitize_text,
    sha256_file,
    walk_files,
    write_text_lf,
)
from freeze_manifest import AB_FREEZE_MANIFEST_SCHEMA_VERSION  # noqa: E402
from scaffold_arms import (  # noqa: E402
    AB_ARM_MANIFEST_SCHEMA_VERSION,
    ARMS,
    TREE_IGNORE,
)

#: run 载荷自己的版本轴；加键 / 改语义必须按 AGENTS 第 55 条递增。
AB_RUN_SCHEMA_VERSION = "1.0"

#: 凭据只从启动环境读；这个名字进载荷时只记「在不在」。
CREDENTIAL_ENV = "DEEPSEEK_API_KEY"

#: 记录「在不在」的环境变量（值一律不记：路径与凭据都可能长在里面）。
ENV_WATCHLIST: Tuple[str, ...] = (
    "DEEPSEEK_API_KEY",
    "DSH_HOME",
    "DSH_CLI",
    "PYTHONPATH",
    "PYTHONIOENCODING",
)

SANDBOXES: Tuple[str, ...] = ("danger-full-access", "workspace-write", "unknown")

#: 沙箱形态里哪些能让 Hook 的子进程管道 stdio 活下来（2026-10-21 读数 §2.3 的结论）。
HOOK_SPAWN_OK: Tuple[str, ...] = ("danger-full-access",)

DEFAULT_WATCH: Tuple[str, ...] = (".policy/**/*.jsonl",)

#: 审计记录里承载「事后结局」的键前缀（hooks.py 把 post 结局写成 reason_code）。
POST_PREFIX = "post_"

HOOK_TIMEOUT_MS = 30000

# --------------------------------------------------------------------------- 宿主


def find_dsh(explicit: Optional[str]) -> Tuple[Optional[Path], str]:
    """找 dsh CLI：返回（路径, 来源）。来源会进载荷，因为**哪一份 dsh** 是实验条件的一部分。

    顺序：`--dsh` > `$DSH_CLI` > **app 自带的安装目录** > `PATH`。

    安装目录排在 PATH 前面是有意的：本机 `PATH` 上有一份 npm 装的旧 dsh
    （0.2.1-alpha.2），而读数（2026-10-21）钉的是 app 自带的 0.2.1-rc.2。
    「找到哪一个」不能靠 PATH 的偶然顺序决定——要换就显式 `--dsh`。
    """

    candidates: List[Tuple[Path, str]] = []
    if explicit:
        candidates.append((Path(explicit), "explicit"))
    if os.environ.get("DSH_CLI"):
        candidates.append((Path(os.environ["DSH_CLI"]), "env"))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            (
                Path(local_app_data)
                / "Programs"
                / "DeepSeek Harness"
                / "resources"
                / "runtime"
                / "cli"
                / "bin"
                / "dsh.cmd",
                "app",
            )
        )
    for name in ("dsh", "dsh.cmd", "dsh.exe"):
        located = shutil.which(name)
        if located:
            candidates.append((Path(located), "path"))
            break
    for candidate, source in candidates:
        if candidate.is_file():
            return candidate.resolve(), source
    return None, "missing"


def dsh_version(dsh: Path) -> str:
    """跑一次 `--version` 记录宿主版本；跑不成就是空串（不升级成「不可用」）。"""

    try:
        completed = subprocess.run(
            [str(dsh), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return first_line(completed.stdout or completed.stderr, 40)


def env_record() -> List[Dict[str, Any]]:
    """环境变量只记「在不在」：值可能含凭据与绝对路径，一律不进载荷。"""

    return [
        {
            "name": name,
            "present": bool(os.environ.get(name)),
            "value_recorded": False,
        }
        for name in ENV_WATCHLIST
    ]


# --------------------------------------------------------------------------- 覆盖层


def build_overlay(
    *,
    plugin: Path,
    project_dir: Path,
    hook_python: Path,
    platform_src: Path,
    timeout_ms: int = HOOK_TIMEOUT_MS,
) -> str:
    """参数化覆盖层：插件路径 / projectDir / PYTHONPATH 三处都从参数来。

    `command` 必须是 **PowerShell 调用运算符**形状（`& '...'`）：裸引号路径会被
    PowerShell 当成字符串表达式解析而报 UnexpectedToken（2026-10-21 读数 §2.4 的修正）。
    """

    def single(value: str) -> str:
        return value.replace("'", "''")

    command = "$env:PYTHONPATH='%s'; & '%s' -m adapters.dsh.hooks " % (
        single(platform_src.as_posix()),
        single(hook_python.as_posix()),
    )
    command += "--config .policy/dsh-adapter.yaml --hooks-config .policy/hooks.json"
    lines = [
        "- insert:",
        "    - id: policy-hook",
        "      name: '%s'" % single(plugin.as_posix()),
        "      config:",
        '        command: "%s"' % command.replace('"', '\\"'),
        "        timeoutMs: %d" % timeout_ms,
        "        projectDir: '%s'" % single(project_dir.as_posix()),
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- 增量（按偏移）


def watch_files(target: Path, patterns: Sequence[str]) -> List[str]:
    """臂树里匹配 --watch 的文件（相对臂树；与 TREE_IGNORE 同一套忽略）。"""

    files, _unreadable, _ignored = walk_files(target, TREE_IGNORE, "watch")
    return [item for item in files if matches_any(patterns, item)]


def snapshot_offsets(target: Path, patterns: Sequence[str]) -> Dict[str, int]:
    """启动前的**字节偏移**。

    按偏移而不是「前后集合差」：集合差在文件被截断 / 被替换 / 只追加半行时分不清
    「没有新增」与「读不到」，而这两件事的处置完全不同。
    """

    state: Dict[str, int] = {}
    for relative in watch_files(target, patterns):
        try:
            state[relative] = (target / relative).stat().st_size
        except OSError:
            state[relative] = -1
    return state


def read_increments(
    target: Path,
    patterns: Sequence[str],
    before: Dict[str, int],
) -> Tuple[Dict[str, Any], Dict[str, int], List[str]]:
    """读增量；返回（{streams, totals, records}, 本次 watch 到的路径集合, invalid 条件）。

    `totals` 里的 `decisions` / `reasons` / `post` 是本次**增量**的分布，
    不是整份日志的累计——那正是「按偏移」要保证的事。
    """

    after = set(watch_files(target, patterns))
    streams: Dict[str, Any] = {}
    decisions: Dict[str, int] = {}
    reasons: Dict[str, int] = {}
    post: Dict[str, int] = {}
    invalid: List[str] = []
    for relative in sorted(after | set(before)):
        entry: Dict[str, Any] = {
            "path": relative,
            "offset_before": before.get(relative, 0),
            "bytes_read": 0,
            "records": 0,
            "created": relative not in before,
            "partial_line": False,
            "error": None,
        }
        streams[relative] = entry
        path = target / relative
        if not path.is_file():
            entry["error"] = "missing"
            invalid.append("stream_missing:" + relative)
            continue
        offset = before.get(relative, 0)
        if offset < 0:
            entry["error"] = "unreadable"
            invalid.append("stream_unreadable:" + relative)
            continue
        try:
            size = path.stat().st_size
            if size < offset:
                entry["error"] = "truncated"
                invalid.append("stream_truncated:" + relative)
                offset = 0
            with path.open("rb") as handle:
                handle.seek(offset)
                data = handle.read()
        except OSError:
            entry["error"] = "unreadable"
            invalid.append("stream_unreadable:" + relative)
            continue
        entry["bytes_read"] = len(data)
        text = data.decode("utf-8", errors="replace")
        if text and not text.endswith("\n"):
            entry["partial_line"] = True
            invalid.append("partial_line:" + relative)
            text = text[: text.rfind("\n") + 1] if "\n" in text else ""
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                entry["records"] += 1
                invalid.append("unparsable_record:" + relative)
                continue
            entry["records"] += 1
            if not isinstance(record, dict):
                continue
            decision = record.get("decision")
            if decision is not None:
                decisions[str(decision)] = decisions.get(str(decision), 0) + 1
            code = record.get("reason_code")
            if code is not None:
                reasons[str(code)] = reasons.get(str(code), 0) + 1
                if str(code).startswith(POST_PREFIX):
                    post[str(code)] = post.get(str(code), 0) + 1
    totals = {
        "decisions": {key: decisions[key] for key in sorted(decisions)},
        "reasons": {key: reasons[key] for key in sorted(reasons)},
        "post": {key: post[key] for key in sorted(post)},
    }
    return {
        "streams": streams,
        "totals": totals,
        "records": sum(item["records"] for item in streams.values()),
    }, after, invalid


# --------------------------------------------------------------------------- 树 diff


def tree_digests(target: Path) -> Tuple[Dict[str, str], List[str]]:
    files, unreadable, _ignored = walk_files(target, TREE_IGNORE, "tree")
    return {item: sha256_file(target / item, item) for item in files}, unreadable


def tree_diff(before: Dict[str, str], after: Dict[str, str]) -> Dict[str, Any]:
    """树 diff：路径一律**相对臂树**（臂树可能不在仓库里，也不许出现绝对路径）。"""

    return {
        "created": sorted(set(after) - set(before)),
        "changed": sorted(path for path in set(before) & set(after) if before[path] != after[path]),
        "deleted": sorted(set(before) - set(after)),
        "unchanged": sum(1 for path in set(before) & set(after) if before[path] == after[path]),
    }


# --------------------------------------------------------------------------- 前置


def _blocker(code: str, reason: str) -> Dict[str, str]:
    return {"code": code, "reason": reason}


def _run_tool(argv: Sequence[str], cwd: Path) -> Tuple[int, str]:
    """跑一个兄弟脚本（freeze_manifest / scaffold_arms）并取最后一行输出。"""

    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return EXIT_INVALID, "跑不成（%s）" % type(error).__name__
    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    result_lines = [line for line in lines if line.startswith("RESULT:")]
    last = result_lines[-1] if result_lines else (lines[-1] if lines else "")
    return completed.returncode, last


def preflight(repo_root: Path, args: argparse.Namespace) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """前置检查：返回（上下文, blockers）。**任何 blocker 都不发车**。"""

    blockers: List[Dict[str, str]] = []
    context: Dict[str, Any] = {}
    target = Path(args.target).resolve()
    context["repo_root"] = repo_root
    context["watch"] = list(args.watch or DEFAULT_WATCH)
    context["profile"] = args.profile
    context["target"] = target
    context["target_path"] = display_path(target, repo_root)

    manifest_path = Path(args.arm_manifest).resolve()
    try:
        manifest = load_json(manifest_path, display_path(manifest_path, repo_root))
    except HarnessInputError as error:
        return context, [_blocker("arm_manifest_unreadable", str(error))]
    if not isinstance(manifest, dict):
        return context, [_blocker("arm_manifest_invalid", "臂清单的顶层不是对象")]
    if manifest.get("schema_version") != AB_ARM_MANIFEST_SCHEMA_VERSION:
        return context, [
            _blocker(
                "arm_manifest_invalid",
                "臂清单 schema_version 必须是 %r（读到 %r）"
                % (AB_ARM_MANIFEST_SCHEMA_VERSION, manifest.get("schema_version")),
            )
        ]
    if manifest.get("arm") not in ARMS:
        return context, [_blocker("arm_manifest_invalid", "臂清单的 arm 不在 %s 之内" % list(ARMS))]
    context["arm_manifest"] = manifest
    context["arm"] = str(manifest["arm"])
    context["task_id"] = str((manifest.get("task") or {}).get("id") or "")
    context["arm_manifest_digest"] = "sha256:" + sha256_file(
        manifest_path, display_path(manifest_path, repo_root)
    )
    if display_path(target, repo_root) != (manifest.get("target") or {}).get("path"):
        blockers.append(
            _blocker(
                "arm_manifest_target_mismatch",
                "--target 与臂清单记录的 target 不是同一棵树（清单写的是 %r）"
                % (manifest.get("target") or {}).get("path"),
            )
        )
    placeholders = (manifest.get("policy") or {}).get("placeholders") or []
    if placeholders:
        blockers.append(
            _blocker(
                "approvals_unsigned",
                "臂树里还有未签字占位 %s：本脚本不替使用者签审批条子" % placeholders,
            )
        )
    if not target.is_dir():
        blockers.append(_blocker("target_missing", "臂树目录不存在"))
        return context, blockers

    package_path = str((manifest.get("task") or {}).get("package", {}).get("path", ""))
    if not package_path or package_path == OUTSIDE_WORKSPACE:
        return context, blockers + [
            _blocker(
                "arm_manifest_invalid",
                "臂清单里的任务包不在仓库内：臂树无法复核（本框架只接受仓库相对路径）",
            )
        ]
    code, line = _run_tool(
        [
            sys.executable,
            str(_HERE / "scaffold_arms.py"),
            "--task-package",
            str(repo_root / package_path),
            "--arm",
            context["arm"],
            "--target",
            str(target),
            "--manifest-out",
            str(manifest_path),
            "--check",
        ],
        repo_root,
    )
    context["arm_tree_check"] = {"exit_code": code, "result_line": sanitize_text(line, repo_root)}
    if code != 0:
        blockers.append(
            _blocker(
                "arm_tree_drift",
                "臂树与臂清单不一致（%s）" % sanitize_text(line, repo_root),
            )
        )

    freeze_path = Path(args.freeze_manifest).resolve()
    freeze_argv = [
        sys.executable,
        str(_HERE / "freeze_manifest.py"),
        "--set",
        str(Path(args.freeze_set).resolve()),
        "--manifest",
        str(freeze_path),
        "--check",
        "--strict",
    ]
    code, line = _run_tool(freeze_argv, repo_root)
    context["freeze_check"] = {
        "strict": True,
        "exit_code": code,
        "result_line": sanitize_text(line, repo_root),
    }
    try:
        freeze_payload = load_json(freeze_path, display_path(freeze_path, repo_root))
    except HarnessInputError as error:
        blockers.append(_blocker("freeze_manifest_unreadable", str(error)))
        freeze_payload = None
    if freeze_payload is not None:
        if not isinstance(freeze_payload, dict) or freeze_payload.get("schema_version") != (
            AB_FREEZE_MANIFEST_SCHEMA_VERSION
        ):
            blockers.append(
                _blocker("freeze_manifest_unreadable", "冻结清单的 schema_version 不是 %r" % AB_FREEZE_MANIFEST_SCHEMA_VERSION)
            )
        else:
            manifest_section = freeze_payload.get("manifest") or {}
            context["freeze"] = {
                "manifest_digest": manifest_section.get("combined_digest"),
                "entries": manifest_section.get("count"),
                "check": context["freeze_check"],
            }
    if code != 0:
        blockers.append(
            _blocker(
                "freeze_check_failed",
                "freeze_manifest --check --strict 未通过（%s）" % sanitize_text(line, repo_root),
            )
        )

    first = manifest.get("first_message") or {}
    relative = first.get("path")
    if args.first_message:
        first_path = Path(args.first_message).resolve()
    elif isinstance(relative, str) and relative not in ("", "<outside-workspace>"):
        first_path = (repo_root / relative).resolve()
    else:
        first_path = None
    context["first_message_path"] = first_path
    if first_path is None or not first_path.is_file():
        blockers.append(_blocker("first_message_missing", "首消息文件不存在（清单里也没有可解析的路径）"))
    else:
        try:
            text = first_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            text = ""
            blockers.append(_blocker("first_message_missing", "首消息文件读不到（%s）" % type(error).__name__))
        context["first_message_text"] = text
        if not text.strip():
            blockers.append(_blocker("first_message_empty", "首消息文件是空的：发过去等于让模型自己猜任务"))
        actual = sha256_file(first_path, display_path(first_path, repo_root))
        if actual != first.get("sha256"):
            blockers.append(
                _blocker(
                    "first_message_drift",
                    "首消息摘要与臂清单记录不符（记录 %r / 现在 %r）" % (first.get("sha256"), actual),
                )
            )

    dsh, dsh_source = find_dsh(args.dsh)
    context["dsh"] = dsh
    context["dsh_source"] = dsh_source
    if dsh is None:
        blockers.append(_blocker("dsh_missing", "找不到 dsh CLI（--dsh / $DSH_CLI / app 安装目录 / PATH 都没有）"))
        context["dsh_version"] = ""
    else:
        context["dsh_version"] = sanitize_text(dsh_version(dsh), repo_root)

    sandbox = args.sandbox
    context["sandbox"] = sandbox
    if sandbox not in SANDBOXES:
        blockers.append(_blocker("sandbox_undeclared", "--sandbox 取值必须在 %s 之内" % list(SANDBOXES)))
    elif sandbox == "unknown":
        blockers.append(_blocker("sandbox_undeclared", "沙箱形态必须显式声明（--sandbox），不能用 unknown 发车"))
    elif context["arm"] in ("A", "B") and sandbox not in HOOK_SPAWN_OK:
        blockers.append(
            _blocker(
                "sandbox_blocks_hook_spawn",
                "%s 臂要挂 Hook：%s 下 Hook 的子进程 spawn 会被拒（EPERM），"
                "读数里 0 条审计不是「没动作」而是「没跑起来」" % (context["arm"], sandbox),
            )
        )

    home = Path(args.dsh_home).resolve() if args.dsh_home else None
    context["dsh_home"] = home
    if home is None:
        blockers.append(_blocker("dsh_home_missing", "必须给 --dsh-home：不隔离 DSH_HOME 会读宿主既有接线"))
    else:
        user_home = (Path.home() / ".dsh").resolve()
        if home == user_home:
            blockers.append(_blocker("dsh_home_unsafe", "--dsh-home 不能是宿主自己的 ~/.dsh"))
        elif is_under(home, target) or is_under(target, home):
            blockers.append(_blocker("dsh_home_unsafe", "--dsh-home 与臂树互相包含"))

    if context["arm"] in ("A", "B"):
        src = Path(args.platform_src).resolve() if args.platform_src else None
        if src is None or not src.is_dir():
            blockers.append(_blocker("plugin_missing", "A / B 臂必须给 --platform-src（Hook 要 import 平台）"))
            context["platform_src"] = None
        else:
            context["platform_src"] = src
            plugin = Path(args.plugin).resolve() if args.plugin else src / "adapters" / "dsh" / "policy-hook.plugin.mjs"
            context["plugin"] = plugin
            if not plugin.is_file():
                blockers.append(_blocker("plugin_missing", "插件文件不存在（按 --plugin 或 <platform-src>/adapters/dsh/ 找）"))
        hook_python = Path(args.hook_python).resolve() if args.hook_python else Path(sys.executable).resolve()
        context["hook_python"] = hook_python
        if not hook_python.is_file():
            blockers.append(_blocker("hook_python_missing", "Hook 解释器不存在（--hook-python）"))
    else:
        context["platform_src"] = None
        context["plugin"] = None
        context["hook_python"] = None

    if not os.environ.get(CREDENTIAL_ENV):
        blockers.append(
            _blocker(
                "missing_credential",
                "%s 不在启动环境里。它只从启动环境读（本脚本不读文件、不打印、不落盘）"
                % CREDENTIAL_ENV,
            )
        )

    run_dir = Path(args.run_dir).resolve()
    context["run_dir"] = run_dir
    context["run_dir_path"] = display_path(run_dir, repo_root)
    if is_under(run_dir, target):
        blockers.append(_blocker("run_dir_unsafe", "--run-dir 不能落在臂树里（会污染树 diff）"))
    return context, blockers


def _print_plan(context: Dict[str, Any], blockers: Sequence[Dict[str, str]], mode: str) -> None:
    """把计划逐行打出来；发不发车只看 blockers。

    这里的路径都用 `display_path` 的 token 形状（仓库相对 / `<outside-workspace>`），
    与载荷同一口径：dry-run 的文本会被抄进读数，不能在这里就漏绝对路径。
    """

    freeze = context.get("freeze") or {}
    repo_root = context.get("repo_root")
    first = context.get("first_message_path")
    target = context.get("target")
    run_dir = context.get("run_dir")
    print("[ab-harness] run_session")
    print("  mode            : %s" % mode)
    print("  arm             : %s" % context.get("arm"))
    print("  task            : %s" % context.get("task_id"))
    print("  target          : %s" % context.get("target_path"))
    print("  arm-manifest    : %s" % context.get("arm_manifest_digest"))
    print("  freeze          : %s entries=%s" % (freeze.get("manifest_digest"), freeze.get("entries")))
    print("  freeze-check    : %s" % ((freeze.get("check") or {}).get("result_line") or ""))
    print("  arm-tree-check  : %s" % ((context.get("arm_tree_check") or {}).get("result_line") or ""))
    print(
        "  first-message   : %s"
        % (display_path(first, repo_root) if first is not None else "<none>")
    )
    print(
        "  dsh             : version=%s source=%s"
        % (context.get("dsh_version") or "<unknown>", context.get("dsh_source"))
    )
    print(
        "  dsh-home        : %s"
        % (display_path(context["dsh_home"], repo_root) if context.get("dsh_home") else "<none>")
    )
    print("  run-dir         : %s" % (display_path(run_dir, repo_root) if run_dir else "<none>"))
    print("  sandbox         : %s" % context.get("sandbox"))
    if context.get("arm") == "C":
        print("  overlay         : <none>（C 臂不治理，不挂 --patch）")
    else:
        print(
            "  overlay         : %s"
            % (
                "not written yet (dry-run)"
                if mode.startswith("dry-run")
                else display_path((run_dir / "overlay.yaml") if run_dir else Path("."), repo_root)
            )
        )
    print("  streams         : %s" % list(context.get("watch") or DEFAULT_WATCH))
    if blockers:
        print("  PREFLIGHT: blocked（%d 项）" % len(blockers))
        for blocker in blockers:
            print("  BLOCKER: %s — %s" % (blocker["code"], blocker["reason"]))
        print("  LAUNCH: refused")
    else:
        print("  PREFLIGHT: ok")
        print("  LAUNCH: %s" % ("would start" if mode.startswith("dry-run") else "started"))


# --------------------------------------------------------------------------- 结果载荷


def _counts_line(counts: Dict[str, int]) -> str:
    return ",".join("%s:%d" % (key, counts[key]) for key in sorted(counts))


def build_run_payload(
    context: Dict[str, Any],
    *,
    exit_block: Dict[str, Any],
    increments: Dict[str, Any],
    diff: Dict[str, Any],
    invalid: List[str],
) -> Dict[str, Any]:
    """组装 run.json（协议：加键必须升 AB_RUN_SCHEMA_VERSION）。

    这里**不**出现：绝对路径、凭据值、时戳、耗时、run id。耗时与原始输出只进 dsh.log。
    """

    totals = increments["totals"]
    task = context.get("arm_manifest", {}).get("task") or {}
    payload: Dict[str, Any] = {
        "schema_version": AB_RUN_SCHEMA_VERSION,
        "arm": context.get("arm"),
        "task": {
            "id": context.get("task_id"),
            "package_digest": (task.get("package") or {}).get("combined_digest"),
        },
        "host": {
            "profile": context.get("profile"),
            "dsh": {
                "version": context.get("dsh_version") or "",
                "source": context.get("dsh_source") or "missing",
            },
            "python": "%d.%d" % sys.version_info[:2],
            "platform": sys.platform,
            "env": env_record(),
        },
        "sandbox": {
            "mode": context.get("sandbox"),
            "hook_spawn_required": context.get("arm") in ("A", "B"),
        },
        "freeze": context.get("freeze") or {},
        "exit": exit_block,
        "readings": {
            "records": increments["records"],
            "decisions": totals["decisions"],
            "reasons": totals["reasons"],
            "post": totals["post"],
            "invalid": sorted(set(invalid)),
            "streams": increments["streams"],
            "diff": diff,
            "summary_lines": [],
        },
    }
    payload["readings"]["summary_lines"] = summary_lines(payload)
    return payload


def summary_lines(payload: Dict[str, Any]) -> List[str]:
    """读数正文：确定性的几行摘要（同一份载荷得到逐字节相同的行）。

    这是载荷里唯一「给人看」的部分，因此它自己必须已经脱敏——不抄原始 stdout。
    """

    readings = payload["readings"]
    exit_block = payload["exit"]
    diff = readings["diff"]
    return [
        "arm=%s task=%s exit=%s timeout=%s"
        % (
            payload["arm"],
            payload["task"]["id"],
            exit_block.get("code"),
            str(bool(exit_block.get("timeout"))).lower(),
        ),
        "records=%d decisions=%s"
        % (readings["records"], _counts_line(readings["decisions"]) or "<none>"),
        "reasons=%s" % (_counts_line(readings["reasons"]) or "<none>"),
        "post=%s" % (_counts_line(readings["post"]) or "<none>"),
        "diff created=%d changed=%d deleted=%d unchanged=%d"
        % (len(diff["created"]), len(diff["changed"]), len(diff["deleted"]), diff["unchanged"]),
        "invalid=%s" % (",".join(readings["invalid"]) or "<none>"),
    ]


def _invalid_conditions(arm: str, increments: Dict[str, Any], invalid: List[str]) -> List[str]:
    """把「跑不成」写成显式的 invalid 条件：受治理臂 0 条审计不是「没动作」，是「没跑起来」。"""

    conditions = list(invalid)
    if arm in ("A", "B") and increments["records"] == 0:
        conditions.append("no_audit_records")
    return sorted(set(conditions))


# --------------------------------------------------------------------------- 执行


def execute(repo_root: Path, args: argparse.Namespace, context: Dict[str, Any]) -> int:
    """真跑一次：写覆盖层 → 起 dsh → 按偏移采集 → 写 run.json 与 dsh.log。"""

    target = context["target"]
    run_dir = context["run_dir"]
    run_dir.mkdir(parents=True, exist_ok=True)
    watch = context["watch"]
    overlay = run_dir / "overlay.yaml"
    argv = [str(context["dsh"]), "--profile", context["profile"]]
    if context["arm"] in ("A", "B"):
        text = build_overlay(
            plugin=context["plugin"],
            project_dir=target,
            hook_python=context["hook_python"],
            platform_src=context["platform_src"],
        )
        write_text_lf(overlay, text)
        argv.extend(["--patch", str(overlay)])
    argv.append("-")

    secret = os.environ.get(CREDENTIAL_ENV)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    offsets = snapshot_offsets(target, watch)
    before_tree, unreadable_before = tree_digests(target)
    started = time.monotonic()
    completed: Optional[subprocess.CompletedProcess] = None
    failure = ""
    try:
        completed = subprocess.run(
            argv,
            cwd=str(target),
            input=context["first_message_text"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=args.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        failure = "dsh_timeout"
    except OSError as error:
        failure = "dsh_launch_failed:%s" % type(error).__name__
    wall_ms = int((time.monotonic() - started) * 1000)

    stdout = redact_secret(completed.stdout if completed else "", secret)
    stderr = redact_secret(completed.stderr if completed else "", secret)
    shown = ["--patch", "<overlay>"] if "--patch" in argv else []
    log_lines = [
        "# run_session arm=%s task=%s" % (context["arm"], context["task_id"]),
        "# wall_ms=%d" % wall_ms,
        "# sandbox=%s" % context["sandbox"],
        "# dsh_version=%s" % (context["dsh_version"] or "<unknown>"),
        "# argv=%s" % " ".join([argv[0]] + [item for item in shown] + [argv[-1]]),
        "# 说明：dsh.log 保留原始输出（含绝对路径）供排障；run.json 里没有绝对路径与凭据",
        "----- stdout -----",
        stdout.rstrip("\n"),
        "----- stderr -----",
        stderr.rstrip("\n"),
        "",
    ]
    write_text_lf(run_dir / "dsh.log", "\n".join(log_lines))

    increments, _after, invalid = read_increments(target, watch, offsets)
    after_tree, unreadable_after = tree_digests(target)
    diff = tree_diff(before_tree, after_tree)
    for item in unreadable_before + unreadable_after:
        invalid.append("unreadable_tree_entry")
    invalid = _invalid_conditions(context["arm"], increments, invalid)
    if failure:
        invalid.append(failure)
        invalid = sorted(set(invalid))
    exit_block = {
        "code": None if completed is None else completed.returncode,
        "timeout": failure == "dsh_timeout",
    }
    payload = build_run_payload(
        context, exit_block=exit_block, increments=increments, diff=diff, invalid=invalid
    )
    abspaths = check_no_absolute_paths(payload)
    if abspaths:
        print(
            "run-session: 载荷里出现绝对路径 %s —— 拒绝写盘（协议要求载荷可移植）" % abspaths,
            file=sys.stderr,
        )
        return EXIT_INVALID
    write_text_lf(run_dir / "run.json", render_json(payload))
    for line in payload["readings"]["summary_lines"]:
        print(line)
    print("run-session: wall_ms=%d log=%s" % (wall_ms, display_path(run_dir / "dsh.log", repo_root)))
    if exit_block["code"] != 0 or invalid:
        return EXIT_INVALID
    return EXIT_OK


# --------------------------------------------------------------------------- CLI


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("不是整数：%s" % value) from error
    if number <= 0:
        raise argparse.ArgumentTypeError("必须为正整数：%s" % value)
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "一次 run 的包装器：默认 dry-run（只跑前置、不发真机）；--execute 才真跑一次 dsh 会话"
        )
    )
    parser.add_argument("--arm-manifest", required=True, help="scaffold_arms.py 写出的臂清单")
    parser.add_argument("--freeze-manifest", required=True, help="freeze_manifest.py 写出的冻结清单")
    parser.add_argument("--freeze-set", required=True, help="实验集声明（与冻结清单配套的那份）")
    parser.add_argument("--target", required=True, help="臂树目录（必须与臂清单记录的一致）")
    parser.add_argument("--run-dir", required=True, help="本次 run 的产物目录（run.json / overlay.yaml / dsh.log）")
    parser.add_argument("--first-message", default=None, help="首消息文件（默认取臂清单记录的那份）")
    parser.add_argument("--dsh", default=None, help="dsh CLI（默认 $DSH_CLI / PATH / 安装目录）")
    parser.add_argument("--platform-src", default=None, help="A / B 臂必给：Hook 的 PYTHONPATH（含 adapters/）")
    parser.add_argument("--hook-python", default=None, help="Hook 解释器（默认当前解释器）")
    parser.add_argument("--plugin", default=None, help="插件 .mjs（默认 <platform-src>/adapters/dsh/policy-hook.plugin.mjs）")
    parser.add_argument("--dsh-home", required=True, help="隔离的 DSH_HOME（不能是宿主的 ~/.dsh）")
    parser.add_argument(
        "--sandbox",
        default="unknown",
        choices=list(SANDBOXES),
        help="本次启动的沙箱形态（A / B 臂只接受 danger-full-access）",
    )
    parser.add_argument("--profile", default="headless", help="dsh profile（默认 headless）")
    parser.add_argument("--timeout-seconds", type=_positive_int, default=1800, help="dsh 超时（默认 1800 秒）")
    parser.add_argument(
        "--watch",
        action="append",
        default=None,
        help="按偏移采集的 JSONL 通配（可重复；默认 .policy/**/*.jsonl）",
    )
    parser.add_argument("--execute", action="store_true", help="真跑一次会话（默认 dry-run）")
    parser.add_argument("--repo-root", default=None, help="仓库根（默认从脚本位置向上找 .git）")
    return parser


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        repo_root = find_repo_root(_HERE, Path(args.repo_root) if args.repo_root else None)
        context, blockers = preflight(repo_root, args)
    except HarnessInputError as error:
        print("run-session: %s" % error, file=sys.stderr)
        return error.exit_code
    if blockers:
        _print_plan(context, blockers, "dry-run（不发真机）" if not args.execute else "execute")
        print(
            "run-session: 前置不绿，**不发车**（%d 项 blocker）"
            % len(blockers),
            file=sys.stderr,
        )
        return EXIT_USAGE
    if not args.execute:
        _print_plan(context, blockers, "dry-run（不发真机）")
        return EXIT_OK
    _print_plan(context, blockers, "execute")
    return execute(repo_root, args, context)


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(argv)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

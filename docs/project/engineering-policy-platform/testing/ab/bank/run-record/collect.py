#!/usr/bin/env python3
"""collect.py — 题库（bank）的 T / C / A 三维读数采集器（run-record）。

它是什么
========

一次采集把**一道题库题在一棵最终树上**的三个维度读数落成确定性的 run-record JSON，
供 k>=3 的题库读数（以及将来的 run-manifest）消费。三个维度都只做子进程调用，
**不 import 被测代码、不联网**：

- T：BANK_TASK_TREE=<tree> <python> <task-root>/hidden/runner.py --json；
- C：对 scoring.yaml 的 dimension_c.file_set.paths 每个文件跑一次
  <python> -m policy.check <file> --workspace <tree> --config-root <仓库根>
  --layer <layers.yaml 的层> --operation edit --changed <每条> --request-id <固定> --json；
- A：<python> <repo>/tools/structure_metrics.py --workspace <tree>
  --layers <task-root>/layers.yaml --interfaces <task-root>/interfaces.yaml --json。

三个工具、文件集、变更集、case_ids、谓词 id、层值与 config_root **全部从 scoring.yaml 读**：
本脚本里没有第二份判据常数（判据只在数据里，AGENTS 第 55 条的同一条纪律）。脚本只复用
dgate2/run-record/collect.py 的**形态**（三态维度 / 脱敏 argv / 确定性载荷），
不 import 它、不改它、也不复制它的判据。

版本轴
======

BANK_RUN_RECORD_SCHEMA_VERSION = "1.0"：**1.0 = 首次建轴**（bank/README.md 第 7 节登记的轴名）。
加键或改语义必须按 AGENTS 第 55 条显式递增，并同批改本文件、同目录 README 与
tests/unit/test_bank_run_record.py。它**不是** BANK_RUN_MANIFEST_SCHEMA_VERSION：
run-manifest 1.1（dgate2 18 字段 + 题库 9 字段的复合载荷）仍未实现，本载荷不替代它。

确定性
======

载荷里没有时戳、没有 run 标识、没有耗时；对象键按字典序输出，列表顺序固定
（T 的 cases 顺序、C 的 file_set 顺序、A 的 predicates 顺序）；request id 由
--request-id-prefix + arm + 文件 slug 拼出，同一输入两次运行**逐字节相同**。
绝对路径一律不落盘：仓库内写成仓库相对 POSIX 路径，仓库外写成 <outside-workspace>，
可执行文件写 <python>；载荷写盘前还有一道**绝对路径扫描**——扫到就拒绝写盘（退出 1），
不悄悄改写（脱敏只覆盖已知根与 Windows 盘符路径；其余一律拒绝，见 README 第 6 节）。

start 读的是**调用时刻**的仓库状态（--head / git status）：两次采集之间仓库变了，
start 就会变——那是事实，不是不确定性。

退出码
======

- 0 = T / C / A 三维全部采到（T 全过或部分失败都算采到；A 的退出码 1 也是读数）；
- 1 = 有维度没采到（runner 退出 2、case_ids 与声明不符、policy.check 输出不合法 /
  layer 不是 declared、子进程超时等），**或**载荷里出现绝对路径而拒绝写盘；
- 2 = 输入声明读不出来（树 / 任务根 / scoring.yaml / layers.yaml / interfaces.yaml /
  runner / structure_metrics / run-json / arm-config 缺失或不可解析，或声明自相矛盾）。

边界（详见同目录 README 第 6 节）
=================================

- **只采集、不判分**：T/C/A 的分值、聚合与作废判定属于 scoring.yaml 与 run-manifest；
- **C 的 config_root 固定为仓库根**（scoring.yaml 的 dimension_c.config_root 就是这句话）；
- **T 只读最终树**：里程碑顺序、被拒动作不重试属于过程维度，不在 T；
- **process 只作过程描述**（从 run-json 抽 records / decisions / reasons / post / invalid /
  exit / sandbox），不进任何分值，也不代替 run-manifest。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

#: run-record 载荷自己的版本轴（bank/README.md 第 7 节已登记 1.0）。
BANK_RUN_RECORD_SCHEMA_VERSION = "1.0"
#: 单条子进程的默认超时（秒）。
DEFAULT_TIMEOUT_SECONDS = 300
ARMS = ("A", "B", "C")
#: 沙箱形态三态（与 dgate2 run-manifest 的 SANDBOX_STATES 同一组取值）。
SANDBOX_STATES = ("restricted", "unrestricted", "unknown")
#: dsh 的来路（与 dgate2 run-manifest 的 PLATFORM_DSH_SOURCES 同一组取值）。
DSH_SOURCES = ("app_bundled", "path_cli", "unknown")
#: 宿主入口：本采集器只服务 headless 会话。
HOST_ENTRY = "headless"
#: 仓库外路径在载荷里的写法。
OUTSIDE_WORKSPACE = "<outside-workspace>"
#: 仓库根在可读消息里的写法（载荷不走这里）。
REPO_LABEL = "<repo>"
#: 可执行文件在 commands[].argv 里的写法（解释器路径不进载荷）。
PYTHON_LABEL = "<python>"
EXIT_OK = 0
EXIT_UNAVAILABLE = 1
EXIT_INPUT_ERROR = 2
#: T 的「隐藏验收还没冻结」状态值（scoring.dimension_t.status）；命中时 T 不进读数。
T_PENDING_STATUS = "pending_hidden"
#: dimension_c.config_root 里表示仓库根的写法（其余按仓库相对目录解析）。
REPO_ROOT_TOKENS = frozenset({"仓库根", "仓库根目录", "repo-root", "repo", ".", "./"})
#: arm-config 目录里每个声明角色的候选文件名（按顺序取第一个存在的；都缺 = unavailable）。
DECLARATION_ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("adapter_config", ("dsh-adapter.yaml",)),
    ("registry", ("tool-registry.local.yaml", "tool-registry.yaml")),
    ("approval", ("approval.json",)),
    ("test_layout", ("test-layout.yaml", "validation/test-layout.yaml")),
)
#: 载荷里绝对路径的三种起始形态（盘符 / UNC / 以斜杠开头）。
_WINDOWS_ABS = re.compile(r"^[A-Za-z]:[\\/]")
#: 自由文本里的 Windows 绝对路径（run.json 的自由文本字段）。
_WINDOWS_ABS_IN_TEXT = re.compile(r"(?<![\w])[A-Za-z]:[\\/][^\s\"'，。；、)\]）】]*")
_HEX_HEAD = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SLUG = re.compile(r"[^a-z0-9]+")

Runner = Callable[..., subprocess.CompletedProcess]
#: start 的事实来源；返回（head, worktree_clean），读不到返回 None。
GitProbe = Callable[[Path], "tuple[str, bool] | None"]


class InputError(Exception):
    """输入声明读不出来（退出码 2）。"""


class CommandTimeout(Exception):
    """子进程超时（该维度 unavailable，总结算退出码 1）。"""


# ---------------------------------------------------------------------------
# 路径 / 摘要 / 子进程
# ---------------------------------------------------------------------------
def _find_repo(start: Path | None = None) -> Path:
    """从脚本位置向上找仓库根（以 src/policy 与 policies/ 为准）。"""

    here = (start or Path(__file__)).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "src" / "policy").is_dir() and (candidate / "policies").is_dir():
            return candidate
    raise InputError("找不到仓库根：从 collect.py 向上找不到 src/policy 与 policies/")


def _relative_if_inside(path: Path, repo: Path) -> str | None:
    """仓库内路径 -> 仓库相对 POSIX 路径；仓库外返回 None。"""

    try:
        relative = path.resolve().relative_to(repo.resolve())
    except (ValueError, OSError):
        return None
    return relative.as_posix() or "."


def _display_path(path: Path, repo: Path) -> str:
    """读数里显示的路径：仓库内相对，仓库外一律 <outside-workspace>。"""

    relative = _relative_if_inside(path, repo)
    return relative if relative is not None else OUTSIDE_WORKSPACE


def _is_safe_relative(value: str) -> bool:
    """仓库相对 POSIX 路径的形状检查：不绝对、不带 ..、不用反斜杠、没有空段。"""

    if not value or value.startswith(("/", "\\")) or _WINDOWS_ABS.match(value):
        return False
    if "\\" in value:
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def _sha256_file(path: Path) -> str:
    """文件原始字节的 sha256（读不到就失败关闭，由调用方转成输入错误）。"""

    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _interpreter(repo: Path) -> Path | None:
    """项目解释器：仓库 .venv 优先，其次当前解释器（不写死任何一个路径）。"""

    for relative in (Path(".venv/Scripts/python.exe"), Path(".venv/bin/python")):
        candidate = repo / relative
        if candidate.is_file():
            return candidate
    return None


def _base_env() -> dict[str, str]:
    """子进程环境：继承调用者环境（PATH 里可能才有 ruff / pytest），但不写字节码。"""

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _execute(
    command: Mapping[str, Any],
    *,
    repo: Path,
    timeout: int,
    runner: Runner | None,
) -> subprocess.CompletedProcess:
    """跑一条计划命令；超时转成 CommandTimeout（由调用方记 unavailable）。"""

    kwargs: dict[str, Any] = {"cwd": repo, "env": command["env"], "timeout": timeout}
    try:
        if runner is not None:
            return runner(command["argv"], **kwargs)
        return subprocess.run(
            command["argv"],
            capture_output=True,
            check=False,
            **kwargs,
        )
    except subprocess.TimeoutExpired as error:
        raise CommandTimeout(f"{command['id']} 超过 {timeout} 秒") from error


def _stdout_bytes(completed: subprocess.CompletedProcess) -> bytes:
    """子进程 stdout 的原始字节（对比确定性时用它，不经解码）。"""

    value = completed.stdout
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8", errors="replace")


def _stdout_text(completed: subprocess.CompletedProcess) -> str:
    """子进程 stdout 文本（兼容注入的 runner 返回 str 的情况）。"""

    return _stdout_bytes(completed).decode("utf-8", errors="replace")


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """解析 JSON 对象；不是合法对象一律返回 None（调用方按载荷不合法处理）。"""

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_int(value: Any) -> bool:
    """bool 是 int 的子类，读数里不许把 true 当 1。"""

    return isinstance(value, int) and not isinstance(value, bool)


def _require_mapping(container: Mapping[str, Any], key: str, label: str) -> Mapping[str, Any]:
    """取一个必须存在的映射；缺 / 类型不对都是声明错误。"""

    value = container.get(key)
    if not isinstance(value, Mapping):
        raise InputError(f"{label} 不是映射（scoring.yaml 的 {key}）")
    return value


# ---------------------------------------------------------------------------
# 输入声明（失败关闭：缺失 / 不可解析 / 自相矛盾 => 退出码 2）
# ---------------------------------------------------------------------------
def _load_yaml_mapping(path: Path, label: str, *, repo: Path) -> dict[str, Any]:
    """读一份 YAML 映射；不存在 / 读不了 / 不是映射都是输入错误。"""

    if not path.is_file():
        raise InputError(f"{label} 不存在：{_display_path(path, repo)}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise InputError(
            f"{label} 不可解析：{_display_path(path, repo)}（{type(error).__name__}）"
        ) from error
    if not isinstance(payload, dict):
        raise InputError(f"{label} 不是映射：{_display_path(path, repo)}")
    return payload


def _path_list(container: Any, label: str) -> list[str]:
    """取一组仓库相对 POSIX 路径：非空、无重复、形状合法。"""

    if (
        not isinstance(container, list)
        or not container
        or not all(isinstance(item, str) and item for item in container)
    ):
        raise InputError(f"{label} 不是非空字符串列表")
    paths = [item.replace("\\", "/") for item in container]
    for path in paths:
        if not _is_safe_relative(path):
            raise InputError(f"{label} 里不是仓库相对 POSIX 路径：{path!r}")
    if len(set(paths)) != len(paths):
        raise InputError(f"{label} 有重复项")
    return paths


def _module_from_tool(text: Any) -> str:
    """从 python -m <module> 形态的工具声明里取出模块名（取不到就是声明错误）。"""

    if not isinstance(text, str):
        raise InputError("scoring.yaml 的 dimension_c.tool 不是字符串")
    match = re.search(r"(?<!\w)-m\s+([A-Za-z_][A-Za-z0-9_.]*)", text)
    if match is None:
        raise InputError(
            "scoring.yaml 的 dimension_c.tool 里没有 python -m <module> 形态的模块名："
            f"{text!r}"
        )
    return match.group(1)


def _resolve_config_root(declared: Any, repo: Path) -> Path:
    """dimension_c.config_root -> 目录：仓库根记号，或仓库内已存在的相对目录。"""

    if not isinstance(declared, str) or not declared.strip():
        raise InputError("scoring.yaml 的 dimension_c.config_root 不是非空字符串")
    head = re.split(r"[（(]", declared.strip(), maxsplit=1)[0].strip()
    if head.lower() in REPO_ROOT_TOKENS:
        return repo
    if _is_safe_relative(head):
        candidate = (repo / head).resolve()
        if candidate.is_dir():
            return candidate
    raise InputError(
        "scoring.yaml 的 dimension_c.config_root 既不是仓库根记号，也不是仓库内已存在的目录："
        f"{head!r}（本采集器的口径是 config_root = 仓库根）"
    )


def _read_scoring(task_root: Path, *, repo: Path) -> dict[str, Any]:
    """读 scoring.yaml 里本采集器需要的声明；缺项 / 矛盾都抛 InputError。"""

    payload = _load_yaml_mapping(task_root / "scoring.yaml", "scoring.yaml", repo=repo)

    task_id = payload.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise InputError("scoring.yaml 的 task_id 不是非空字符串")

    t_block = _require_mapping(payload, "dimension_t", "scoring.yaml 的 dimension_t")
    t_tool = t_block.get("tool")
    if not isinstance(t_tool, str) or not _is_safe_relative(t_tool):
        raise InputError("scoring.yaml 的 dimension_t.tool 不是任务根相对的 POSIX 路径")
    t_total = t_block.get("total")
    if not _is_int(t_total) or t_total <= 0:
        raise InputError("scoring.yaml 的 dimension_t.total 不是正整数")
    t_case_ids = t_block.get("case_ids")
    if (
        not isinstance(t_case_ids, list)
        or not t_case_ids
        or not all(isinstance(item, str) and item for item in t_case_ids)
        or len(set(t_case_ids)) != len(t_case_ids)
    ):
        raise InputError("scoring.yaml 的 dimension_t.case_ids 不是无重复的非空字符串列表")
    if len(t_case_ids) != t_total:
        raise InputError(
            "scoring.yaml 的 dimension_t.case_ids 条数与 total 不一致："
            f"{len(t_case_ids)} vs {t_total}"
        )
    t_status = t_block.get("status")

    c_block = _require_mapping(payload, "dimension_c", "scoring.yaml 的 dimension_c")
    file_set = _require_mapping(c_block, "file_set", "scoring.yaml 的 dimension_c.file_set")
    changed_files = _require_mapping(
        c_block, "changed_files", "scoring.yaml 的 dimension_c.changed_files"
    )
    file_set_paths = _path_list(file_set.get("paths"), "dimension_c.file_set.paths")
    changed_paths = _path_list(changed_files.get("paths"), "dimension_c.changed_files.paths")
    for name, block, paths in (
        ("file_set", file_set, file_set_paths),
        ("changed_files", changed_files, changed_paths),
    ):
        declared_count = block.get("count")
        if declared_count is not None and (
            not _is_int(declared_count) or declared_count != len(paths)
        ):
            raise InputError(
                f"scoring.yaml 的 dimension_c.{name}.count 与 paths 条数不一致："
                f"{declared_count} vs {len(paths)}"
            )
    c_env = c_block.get("env")
    env_map: dict[str, str] = {}
    if c_env is not None:
        if not isinstance(c_env, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in c_env.items()
        ):
            raise InputError("scoring.yaml 的 dimension_c.env 不是「字符串: 字符串」映射")
        env_map = dict(c_env)

    a_block = _require_mapping(payload, "dimension_a", "scoring.yaml 的 dimension_a")
    a_tool = a_block.get("tool")
    if not isinstance(a_tool, str) or not _is_safe_relative(a_tool):
        raise InputError("scoring.yaml 的 dimension_a.tool 不是仓库相对的 POSIX 路径")
    a_layers = a_block.get("layers")
    if not isinstance(a_layers, str) or not _is_safe_relative(a_layers):
        raise InputError("scoring.yaml 的 dimension_a.layers 不是任务根相对的 POSIX 路径")
    a_interfaces = a_block.get("interfaces")
    if not isinstance(a_interfaces, str) or not _is_safe_relative(a_interfaces):
        raise InputError("scoring.yaml 的 dimension_a.interfaces 不是任务根相对的 POSIX 路径")
    a_predicates = a_block.get("predicates")
    predicate_ids: list[str] = []
    if a_predicates is not None:
        if (
            not isinstance(a_predicates, list)
            or not a_predicates
            or not all(isinstance(item, Mapping) for item in a_predicates)
        ):
            raise InputError("scoring.yaml 的 dimension_a.predicates 不是映射列表")
        for item in a_predicates:
            predicate_id = item.get("id")
            if not isinstance(predicate_id, str) or not predicate_id:
                raise InputError("scoring.yaml 的 dimension_a.predicates 里有一条缺 id")
            predicate_ids.append(predicate_id)
        if len(set(predicate_ids)) != len(predicate_ids):
            raise InputError("scoring.yaml 的 dimension_a.predicates 有重复 id")

    return {
        "task_id": task_id.strip(),
        "t": {
            "tool": t_tool,
            "total": t_total,
            "case_ids": list(t_case_ids),
            "status": t_status,
        },
        "c": {
            "file_set": file_set_paths,
            "changed": changed_paths,
            "config_root": c_block.get("config_root"),
            "tool": _module_from_tool(c_block.get("tool")),
            "env": env_map,
        },
        "a": {
            "tool": a_tool,
            "layers": a_layers,
            "interfaces": a_interfaces,
            "predicate_ids": predicate_ids,
        },
    }


def _normalize_layers(raw: Mapping[str, Any], *, repo: Path, path: Path) -> dict[str, str]:
    """layers.yaml：文件相对路径 -> 层值；键统一成 POSIX 形式。"""

    layers: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            raise InputError(f"layers.yaml 的条目不是「路径: 层值」：{_display_path(path, repo)}")
        normalized = key.replace("\\", "/")
        if normalized in layers:
            raise InputError(f"layers.yaml 里重复声明了 {normalized}")
        layers[normalized] = value.strip()
    return layers


def _declared_head(raw: Any) -> str | None:
    """--head 的声明校验：40/64 位十六进制；全零占位不收（那不是「未知」，是错误）。"""

    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise InputError("--head 必须是非空字符串")
    head = raw.strip()
    if not _HEX_HEAD.match(head) or set(head) == {"0"}:
        raise InputError("--head 不是 40/64 位十六进制 git HEAD（全零占位也不收）")
    return head


def _load_inputs(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    """校验并装载全部输入声明；任何一项读不出来都抛 InputError。"""

    tree = Path(args.tree)
    tree = (tree if tree.is_absolute() else Path.cwd() / tree).resolve()
    task_root = Path(args.task_root)
    task_root = (task_root if task_root.is_absolute() else Path.cwd() / task_root).resolve()

    if not tree.is_dir():
        raise InputError(f"--tree 不是目录：{_display_path(tree, repo)}")
    if not task_root.is_dir():
        raise InputError(f"--task-root 不是目录：{_display_path(task_root, repo)}")

    scoring = _read_scoring(task_root, repo=repo)
    if args.task != scoring["task_id"]:
        raise InputError(
            f"--task 与 scoring.yaml 的 task_id 不一致：{args.task!r} vs {scoring['task_id']!r}"
        )

    config_root = _resolve_config_root(scoring["c"]["config_root"], repo)
    if not (config_root / "validation").is_dir():
        raise InputError(
            f"config_root 下没有 validation/：{_display_path(config_root, repo)}"
            "（config_root 指的是包含 validation/ 的那一层）"
        )

    layers_path = task_root / scoring["a"]["layers"]
    interfaces_path = task_root / scoring["a"]["interfaces"]
    layers = _normalize_layers(
        _load_yaml_mapping(layers_path, "layers.yaml", repo=repo), repo=repo, path=layers_path
    )
    _load_yaml_mapping(interfaces_path, "interfaces.yaml", repo=repo)

    runner_path = task_root / scoring["t"]["tool"]
    if not runner_path.is_file():
        raise InputError(f"T 的 runner 不存在：{_display_path(runner_path, repo)}")
    metrics_path = repo / scoring["a"]["tool"]
    if not metrics_path.is_file():
        raise InputError(f"A 的工具不存在：{_display_path(metrics_path, repo)}")

    layers_for_files: dict[str, str] = {}
    for relative in scoring["c"]["file_set"]:
        layer = layers.get(relative)
        if layer is None:
            raise InputError(f"layers.yaml 缺 {relative} 的层值；不猜层")
        if not (tree / relative).is_file():
            raise InputError(f"--tree 里没有被测文件：{relative}")
        layers_for_files[relative] = layer

    arm_config: Path | None = None
    if args.arm_config:
        arm_config = Path(args.arm_config)
        arm_config = (
            arm_config if arm_config.is_absolute() else Path.cwd() / arm_config
        ).resolve()
        if not arm_config.is_dir():
            raise InputError(f"--arm-config 不是目录：{_display_path(arm_config, repo)}")

    run_json: Path | None = None
    if args.run_json:
        run_json = Path(args.run_json)
        run_json = (run_json if run_json.is_absolute() else Path.cwd() / run_json).resolve()
        if not run_json.is_file():
            raise InputError(f"--run-json 不存在：{_display_path(run_json, repo)}")

    return {
        "tree": tree,
        "task_root": task_root,
        "config_root": config_root,
        "layers_path": layers_path,
        "interfaces_path": interfaces_path,
        "runner_path": runner_path,
        "metrics_path": metrics_path,
        "layers": layers,
        "layers_for_files": layers_for_files,
        "arm_config": arm_config,
        "run_json": run_json,
        "head": _declared_head(args.head),
        "scoring": scoring,
    }


# ---------------------------------------------------------------------------
# 命令计划（执行时用绝对路径；读数是脱敏后的 argv）
# ---------------------------------------------------------------------------
def _display_token(token: str, *, repo: Path, labels: Mapping[str, str]) -> str:
    """argv 里的一个 token：已知输入换成标签，仓库内换相对路径，仓库外写 <outside-workspace>。"""

    if token in labels:
        return labels[token]
    path = Path(token)
    if path.is_absolute():
        relative = _relative_if_inside(path, repo)
        return relative if relative is not None else OUTSIDE_WORKSPACE
    return token


def _build_commands(
    inputs: Mapping[str, Any],
    *,
    repo: Path,
    arm: str,
    request_prefix: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """按 T -> A -> C（file_set 顺序）生成命令计划。"""

    scoring = inputs["scoring"]
    tree = inputs["tree"]
    interpreter = _interpreter(repo)
    executable = str(interpreter) if interpreter is not None else str(Path(sys.executable))
    labels: dict[str, str] = {
        str(repo): REPO_LABEL,
        str(tree): "<tree>",
        str(inputs["task_root"]): "<task-root>",
        str(inputs["layers_path"]): "<layers>",
        str(inputs["interfaces_path"]): "<interfaces>",
        executable: PYTHON_LABEL,
        str(Path(sys.executable)): PYTHON_LABEL,
    }
    # config_root 的显示与 scoring.yaml 的 command_template 同形：仓库根写成 "."。
    labels[str(inputs["config_root"])] = _display_path(inputs["config_root"], repo)
    if inputs["arm_config"] is not None:
        labels[str(inputs["arm_config"])] = _display_path(inputs["arm_config"], repo)

    t_env = _base_env()
    t_env["BANK_TASK_TREE"] = str(tree)
    t_argv = [executable, str(inputs["runner_path"]), "--json"]

    a_env = _base_env()
    a_argv = [
        executable,
        str(inputs["metrics_path"]),
        "--workspace",
        str(tree),
        "--layers",
        str(inputs["layers_path"]),
        "--interfaces",
        str(inputs["interfaces_path"]),
        "--json",
    ]

    commands: list[dict[str, Any]] = []

    def add(identifier: str, argv: list[str], env: dict[str, str], extra: dict[str, Any]) -> None:
        display = [_display_token(token, repo=repo, labels=labels) for token in argv]
        commands.append({"id": identifier, "argv": argv, "display": display, "env": env, **extra})

    add("T", t_argv, t_env, {})
    add("A", a_argv, a_env, {})

    for relative in scoring["c"]["file_set"]:
        slug = _SLUG.sub("-", relative.lower()).strip("-")
        request_id = f"{request_prefix}-{arm}-{slug}"
        c_env = _base_env()
        c_env.update(scoring["c"]["env"])
        c_argv = [
            executable,
            "-m",
            scoring["c"]["tool"],
            relative,
            "--workspace",
            str(tree),
            "--config-root",
            str(inputs["config_root"]),
            "--layer",
            inputs["layers_for_files"][relative],
            "--operation",
            "edit",
            "--request-id",
            request_id,
            "--json",
        ]
        for changed in scoring["c"]["changed"]:
            c_argv.extend(["--changed", changed])
        add(
            f"C:{relative}",
            c_argv,
            c_env,
            {
                "file": relative,
                "request_id": request_id,
                "layer": inputs["layers_for_files"][relative],
            },
        )
    return commands, labels


def _print_plan(commands: Sequence[Mapping[str, Any]]) -> None:
    """--dry-run：只打印计划命令，不执行、不写文件。"""

    print("[collect] dry-run：只打印计划命令，不执行子进程、不写 --out")
    for command in commands:
        print(f"[dry-run] {command['id']}: {shlex.join(command['display'])}")
    print(f"[collect] 共 {len(commands)} 条命令")


# ---------------------------------------------------------------------------
# 声明的平台事实（起点 / 代际 / 过程读数）
# ---------------------------------------------------------------------------
def _platform_versions() -> dict[str, str]:
    """从 adapters.dsh 的**常量**读平台版本轴（不复制常数）。"""

    repo = _find_repo()
    source = repo / "src"
    if source.is_dir() and str(source) not in sys.path:
        sys.path.insert(0, str(source))
    try:
        from adapters.dsh.batch_ledger import BATCH_LEDGER_SCHEMA_VERSION
        from adapters.dsh.hooks import AUDIT_SCHEMA_VERSION
    except (ImportError, OSError) as error:
        raise InputError(
            "读不到平台版本常数（adapters.dsh.batch_ledger / adapters.dsh.hooks）："
            f"{type(error).__name__}"
        ) from error
    return {
        "batch_ledger_schema_version": BATCH_LEDGER_SCHEMA_VERSION,
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
    }


def _git_probe(repo: Path) -> tuple[str, bool] | None:
    """读仓库事实：git rev-parse HEAD 与 git status --porcelain；读不到返回 None。"""

    try:
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = (head.stdout or "").strip()
    if head.returncode != 0 or status.returncode != 0 or not _HEX_HEAD.match(value):
        return None
    return value, (status.stdout or "") == ""


def _start_block(head: str | None, *, repo: Path, git: GitProbe | None) -> dict[str, Any]:
    """start：head 来自 --head（优先）或 git，worktree_clean 来自 git；读不到就 unknown。"""

    probed = (git or _git_probe)(repo)
    clean: bool | str = "unknown"
    if probed is not None:
        probed_head, probed_clean = probed
        clean = bool(probed_clean)
        if head is None:
            head = probed_head
    return {"head": head if head is not None else "unknown", "worktree_clean": clean}


def _adapter_test_layout(arm_config: Path | None, *, repo: Path) -> dict[str, Any] | None:
    """从物化 dsh-adapter.yaml 的 pre_evidence.registry_root 找本臂的 test-layout.yaml。

    treatment 的 `production_patterns` 由该快照交付；臂配置目录本身没有这份文件，
    所以 test_layout 摘要必须从 registry_root 下取，不能记成 missing_file。
    """

    if arm_config is None:
        return None
    adapter = arm_config / "dsh-adapter.yaml"
    if not adapter.is_file():
        return None
    try:
        document = yaml.safe_load(adapter.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise InputError(
            "--arm-config 的 dsh-adapter.yaml 读不出来（%s）" % type(error).__name__
        ) from error
    pre = (document or {}).get("pre_evidence") or {}
    raw = pre.get("registry_root") if isinstance(pre, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    root = Path(raw)
    if not root.is_absolute():
        root = (arm_config / root).resolve()
    candidate = root / "validation" / "test-layout.yaml"
    if not candidate.is_file():
        return None
    return {
        "status": "recorded",
        "path": _display_path(candidate, repo),
        "sha256": _sha256_file(candidate),
        "reason": None,
        "source": "pre_evidence.registry_root",
    }


def _declaration_digests(arm_config: Path | None, *, repo: Path) -> dict[str, Any]:
    """arm-config 目录里四个角色的文件摘要；缺 = unavailable + reason（不写假值）。"""

    declarations: dict[str, Any] = {}
    for role, candidates in DECLARATION_ROLES:
        if role == "test_layout":
            derived = _adapter_test_layout(arm_config, repo=repo)
            if derived is not None:
                declarations[role] = derived
                continue
        if arm_config is None:
            declarations[role] = {
                "status": "unavailable",
                "path": None,
                "sha256": None,
                "reason": "no_arm_config",
                "candidates": list(candidates),
            }
            continue
        found: str | None = None
        for candidate in candidates:
            if (arm_config / candidate).is_file():
                found = candidate
                break
        if found is None:
            declarations[role] = {
                "status": "unavailable",
                "path": None,
                "sha256": None,
                "reason": "missing_file",
                "candidates": list(candidates),
            }
            continue
        target = arm_config / found
        try:
            digest = _sha256_file(target)
        except OSError as error:
            raise InputError(
                f"--arm-config 里 {found} 读不到（{type(error).__name__}）"
            ) from error
        declarations[role] = {
            "status": "recorded",
            "path": _display_path(target, repo),
            "sha256": digest,
            "reason": None,
            "candidates": list(candidates),
        }
    return declarations


def _platform_generation(
    args: argparse.Namespace,
    *,
    repo: Path,
    versions: Mapping[str, str],
    arm_config: Path | None,
) -> dict[str, Any]:
    """platform_generation：宿主代际 + 声明摘要 + 平台版本轴；缺的事实写 null/unknown + note。"""

    declarations = _declaration_digests(arm_config, repo=repo)
    host = {
        "entry": HOST_ENTRY,
        "dsh_runtime": args.dsh_runtime,
        "dsh_source": args.dsh_source,
        "model": args.model,
        "sandbox": args.sandbox,
    }
    notes: list[str] = []
    if args.model is None:
        notes.append("host.model: not_declared")
    if args.dsh_runtime is None:
        notes.append("host.dsh_runtime: not_declared")
    if args.dsh_source == "unknown":
        notes.append("host.dsh_source: not_declared")
    if args.sandbox == "unknown":
        notes.append("host.sandbox: not_declared")
    return {
        "host": host,
        "declarations": declarations,
        "batch_ledger_schema_version": versions["batch_ledger_schema_version"],
        "audit_schema_version": versions["audit_schema_version"],
        "notes": sorted(notes),
    }


def _reject_json_constant(value: str) -> Any:
    """NaN / Infinity 这类非标准 JSON 常量一律拒绝（它们会让摘要不稳定）。"""

    raise ValueError(f"非标准 JSON 常量 {value}")


def _empty_process() -> dict[str, Any]:
    """process 的不可用形态（键集合与 recorded 形态一致，值一律 null）。"""

    return {
        "status": "unavailable",
        "reason": "not_provided",
        "records": None,
        "decisions": None,
        "reasons": None,
        "post": None,
        "invalid": None,
        "exit": None,
        "sandbox": None,
    }


def _process_block(run_json: Path | None, *, repo: Path) -> dict[str, Any]:
    """抽 run.json 的过程读数：records / decisions / reasons / post / invalid / exit / sandbox。"""

    if run_json is None:
        return _empty_process()
    try:
        payload = json.loads(
            run_json.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise InputError(
            f"--run-json 不可解析：{_display_path(run_json, repo)}（{type(error).__name__}）"
        ) from error
    if not isinstance(payload, Mapping):
        raise InputError(f"--run-json 不是 JSON 对象：{_display_path(run_json, repo)}")
    readings = payload.get("readings")
    exit_block = payload.get("exit")
    sandbox_block = payload.get("sandbox")
    if not isinstance(readings, Mapping):
        raise InputError("--run-json 缺 readings 映射（不是 run_session 的 run.json）")
    if not isinstance(exit_block, Mapping) or not isinstance(sandbox_block, Mapping):
        raise InputError("--run-json 缺 exit / sandbox 映射（不是 run_session 的 run.json）")
    decisions = readings.get("decisions")
    reasons = readings.get("reasons")
    post = readings.get("post")
    invalid = readings.get("invalid")
    records = readings.get("records")
    if not _is_int(records) or records < 0:
        raise InputError("--run-json 的 readings.records 不是非负整数")
    for name, value in (("decisions", decisions), ("reasons", reasons), ("post", post)):
        if not isinstance(value, Mapping) or not all(
            isinstance(key, str) and _is_int(count) for key, count in value.items()
        ):
            raise InputError(f"--run-json 的 readings.{name} 不是「名称: 计数」映射")
    if not isinstance(invalid, list) or not all(isinstance(item, str) for item in invalid):
        raise InputError("--run-json 的 readings.invalid 不是字符串列表")
    code = exit_block.get("code")
    timeout = exit_block.get("timeout")
    if code is not None and not _is_int(code):
        raise InputError("--run-json 的 exit.code 既不是整数也不是 null")
    if not isinstance(timeout, bool):
        raise InputError("--run-json 的 exit.timeout 不是布尔值")
    mode = sandbox_block.get("mode")
    spawn = sandbox_block.get("hook_spawn_required")
    if not isinstance(mode, str) or not isinstance(spawn, bool):
        raise InputError("--run-json 的 sandbox 缺 mode / hook_spawn_required")

    labels = {
        str(repo): REPO_LABEL,
        str(run_json.parent): _display_path(run_json.parent, repo),
    }

    def counts(value: Mapping[str, Any]) -> dict[str, int]:
        return {str(key): int(value[key]) for key in value}

    return {
        "status": "recorded",
        "reason": None,
        "records": int(records),
        "decisions": counts(decisions),
        "reasons": counts(reasons),
        "post": counts(post),
        "invalid": sorted({_sanitize_text(item, labels=labels) for item in invalid}),
        "exit": {"code": code, "timeout": timeout},
        "sandbox": {"mode": mode, "hook_spawn_required": spawn},
    }


# ---------------------------------------------------------------------------
# T 维度
# ---------------------------------------------------------------------------
def _validate_t_payload(
    payload: Mapping[str, Any], exit_code: int, declared_total: int
) -> str | None:
    """校验 runner 载荷；返回问题描述（None = 合法）。"""

    if not isinstance(payload.get("schema_version"), str):
        return "缺 schema_version"
    summary = payload.get("summary")
    cases = payload.get("cases")
    if not isinstance(summary, Mapping):
        return "缺 summary"
    passed = summary.get("passed")
    total = summary.get("total")
    if not _is_int(passed) or not _is_int(total) or passed < 0 or total < 0 or passed > total:
        return "summary.passed / summary.total 不是合法计数"
    if total != declared_total:
        return (
            "summary.total 与 scoring.yaml 的 dimension_t.total 不一致："
            f"{total} vs {declared_total}"
        )
    if not isinstance(cases, list) or len(cases) != total:
        return "cases 条数与 summary.total 不一致"
    seen: set[str] = set()
    case_passed = 0
    for case in cases:
        if not isinstance(case, Mapping):
            return "cases 里有非映射条目"
        case_id = case.get("id")
        case_ok = case.get("pass")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            return "cases 的 id 缺失或重复"
        if not isinstance(case_ok, bool):
            return f"case {case_id} 的 pass 不是布尔值"
        seen.add(case_id)
        case_passed += int(case_ok)
    if case_passed != passed:
        return "summary.passed 与逐 case 计数不一致"
    if exit_code == 0 and passed != total:
        return "runner 退出码 0 但并非全部通过"
    if exit_code == 1 and passed == total:
        return "runner 退出码 1 但 summary 显示全过"
    return None


def _failed_ids(cases: Sequence[Mapping[str, Any]]) -> list[str]:
    """按 cases 顺序列出失败条目的 id。"""

    return [str(case["id"]) for case in cases if not case.get("pass")]


def _case_ids_mismatch(cases: Sequence[Mapping[str, Any]], declared: Sequence[str]) -> str | None:
    """cases 的 id 集合必须与 scoring.yaml 的 case_ids 相等（少测 / 多测都不是读数）。"""

    actual = {str(case["id"]) for case in cases if isinstance(case, Mapping)}
    expected = set(declared)
    if actual == expected:
        return None
    return f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"


def _fresh_determinism() -> dict[str, Any]:
    """给出 determinism 的初始形态：键集合固定，未比较时为 null。"""

    return {"checked": False, "runs": 1, "stdout_byte_identical": None, "exit_code_identical": None}


def _collect_t(
    command: Mapping[str, Any], *, repo: Path, timeout: int, runner: Runner | None
) -> tuple[dict[str, Any], subprocess.CompletedProcess | None, bytes]:
    """T 维度：runner 退出码 2 = 无法判（unavailable），不是 0 分。"""

    try:
        completed = _execute(command, repo=repo, timeout=timeout, runner=runner)
    except CommandTimeout:
        return (
            {
                "status": "unavailable",
                "exit_code": None,
                "reason": "timeout",
                "determinism": _fresh_determinism(),
            },
            None,
            b"",
        )

    exit_code = completed.returncode
    stdout = _stdout_bytes(completed)
    base: dict[str, Any] = {
        "status": "unavailable",
        "exit_code": exit_code,
        "determinism": _fresh_determinism(),
    }
    if exit_code == 2:
        base["reason"] = "runner_cannot_run"
        return base, completed, stdout
    if exit_code not in (0, 1):
        base["reason"] = "unexpected_exit_code"
        return base, completed, stdout

    payload = _parse_json_object(_stdout_text(completed))
    if payload is None:
        base.update({"reason": "invalid_payload", "detail": "stdout 不是合法 JSON"})
        return base, completed, stdout
    problem = _validate_t_payload(payload, exit_code, command["declared_total"])
    if problem is not None:
        base.update({"reason": "invalid_payload", "detail": problem})
        return base, completed, stdout
    mismatch = _case_ids_mismatch(payload["cases"], command["case_ids"])
    if mismatch is not None:
        base.update({"reason": "case_ids_mismatch", "detail": mismatch})
        return base, completed, stdout

    summary = payload["summary"]
    return (
        {
            "status": "recorded",
            "exit_code": exit_code,
            "schema_version": payload["schema_version"],
            "declared_total": command["declared_total"],
            "summary": {"passed": summary["passed"], "total": summary["total"]},
            "failed_ids": _failed_ids(payload["cases"]),
            "determinism": _fresh_determinism(),
        },
        completed,
        stdout,
    )


# ---------------------------------------------------------------------------
# C 维度
# ---------------------------------------------------------------------------
def _validate_c_payload(payload: Mapping[str, Any], exit_code: int) -> str | None:
    """校验 policy.check 的 --json 载荷；缺任一读数键都算载荷不合法。"""

    result = payload.get("result")
    if not isinstance(result, Mapping):
        return "缺 result 决策载荷"
    if payload.get("exit_code") != exit_code:
        return "载荷里的 exit_code 与进程退出码不一致"
    if result.get("decision") not in {"allow", "allow_with_warnings", "block"}:
        return "result.decision 不是 allow / allow_with_warnings / block"
    if not isinstance(result.get("rule_set_hash"), str) or not result["rule_set_hash"]:
        return "result.rule_set_hash 不是非空字符串"
    if not isinstance(result.get("matched_rules"), list) or not all(
        isinstance(item, str) for item in result["matched_rules"]
    ):
        return "result.matched_rules 不是字符串列表"
    if not isinstance(result.get("skipped_rules"), list) or not all(
        isinstance(item, Mapping) and isinstance(item.get("rule_id"), str)
        for item in result["skipped_rules"]
    ):
        return "result.skipped_rules 不是 {rule_id} 列表"
    if not isinstance(result.get("violations"), list) or not all(
        isinstance(item, Mapping)
        and isinstance(item.get("rule_id"), str)
        and _is_int(item.get("rule_version"))
        and item.get("severity") in {"info", "warning", "error", "critical"}
        for item in result["violations"]
    ):
        return "result.violations 条目不是 {rule_id, rule_version, severity}"
    volume = payload.get("check_volume")
    if not isinstance(volume, Mapping) or not isinstance(volume.get("complete"), bool):
        return "check_volume.complete 不是布尔值"
    missing = volume.get("missing_dimensions")
    if missing is not None and not (
        isinstance(missing, list) and all(isinstance(item, str) for item in missing)
    ):
        return "check_volume.missing_dimensions 不是字符串列表"
    if not isinstance(payload.get("layer_source"), str):
        return "缺 layer_source"
    evidence = payload.get("evidence")
    if not isinstance(evidence, Mapping):
        return "缺 evidence（served_checkers / selection 都读不到）"
    served = evidence.get("served_checkers")
    if not isinstance(served, list) or not all(isinstance(item, str) for item in served):
        return "evidence.served_checkers 不是字符串列表"
    selection = evidence.get("selection")
    if not isinstance(selection, Mapping) or not isinstance(selection.get("level"), str):
        return "evidence.selection.level 缺失或不是字符串"
    return None


def _sanitize_text(text: str, *, labels: Mapping[str, str]) -> str:
    """自由文本脱敏：已知根换成标签，Windows 盘符路径换成 <outside-workspace>。

    不处理 POSIX 绝对路径：那类值由写盘前的绝对路径扫描拦下（拒绝写盘，而不是悄悄改写）。
    """

    cleaned = text
    for absolute, label in labels.items():
        if absolute:
            cleaned = cleaned.replace(absolute, label)
    return _WINDOWS_ABS_IN_TEXT.sub(OUTSIDE_WORKSPACE, cleaned)


def _c_file_entry(
    command: Mapping[str, Any],
    payload: Mapping[str, Any],
    exit_code: int,
) -> dict[str, Any]:
    """把一次 policy.check 载荷压成逐文件读数。"""

    result = payload["result"]
    volume = payload["check_volume"]
    evidence = payload["evidence"]
    return {
        "status": "recorded",
        "file": command["file"],
        "request_id": command["request_id"],
        "layer": command["layer"],
        "layer_source": payload["layer_source"],
        "decision": result["decision"],
        "exit_code": exit_code,
        "violations": len(result["violations"]),
        "violation_rules": [
            f"{item['rule_id']}@{item['rule_version']}" for item in result["violations"]
        ],
        "matched": len(result["matched_rules"]),
        "skipped": len(result["skipped_rules"]),
        "skipped_rule_ids": sorted({str(item["rule_id"]) for item in result["skipped_rules"]}),
        "check_volume": {
            "complete": volume["complete"],
            "blocking_capable_skipped": volume.get("blocking_capable_skipped"),
            "missing_dimensions": sorted(
                str(item) for item in (volume.get("missing_dimensions") or [])
            ),
        },
        "selection": {"level": evidence["selection"]["level"]},
        "served_checkers": sorted({str(item) for item in evidence["served_checkers"]}),
        "rule_set_hash": result["rule_set_hash"],
    }


def _collect_c(
    commands: Sequence[Mapping[str, Any]],
    *,
    repo: Path,
    timeout: int,
    runner: Runner | None,
) -> tuple[dict[str, Any], list[tuple[Mapping[str, Any], subprocess.CompletedProcess | None]]]:
    """C 维度：逐文件 policy.check；任一份载荷不合法 => C unavailable 并点名。"""

    files: list[dict[str, Any]] = []
    results: list[tuple[Mapping[str, Any], subprocess.CompletedProcess | None]] = []
    invalid_files: list[str] = []
    exit_codes: list[int] = []
    timed_out = False

    for command in commands:
        try:
            completed = _execute(command, repo=repo, timeout=timeout, runner=runner)
        except CommandTimeout:
            timed_out = True
            invalid_files.append(str(command["file"]))
            files.append(
                {
                    "status": "invalid",
                    "file": command["file"],
                    "request_id": command["request_id"],
                    "layer": command["layer"],
                    "exit_code": None,
                    "error": "timeout",
                }
            )
            results.append((command, None))
            continue

        exit_code = completed.returncode
        exit_codes.append(exit_code)
        results.append((command, completed))
        payload = _parse_json_object(_stdout_text(completed))
        if payload is None:
            invalid_files.append(str(command["file"]))
            files.append(
                {
                    "status": "invalid",
                    "file": command["file"],
                    "request_id": command["request_id"],
                    "layer": command["layer"],
                    "exit_code": exit_code,
                    "error": "invalid_json",
                }
            )
            continue
        problem = _validate_c_payload(payload, exit_code)
        if problem is not None:
            invalid_files.append(str(command["file"]))
            files.append(
                {
                    "status": "invalid",
                    "file": command["file"],
                    "request_id": command["request_id"],
                    "layer": command["layer"],
                    "exit_code": exit_code,
                    "error": "invalid_payload",
                    "detail": problem,
                }
            )
            continue
        if payload["layer_source"] != "declared":
            invalid_files.append(str(command["file"]))
            files.append(
                {
                    "status": "invalid",
                    "file": command["file"],
                    "request_id": command["request_id"],
                    "layer": command["layer"],
                    "exit_code": exit_code,
                    "error": "layer_source_not_declared",
                    "detail": f"layer_source={payload['layer_source']!r}",
                }
            )
            continue

        files.append(_c_file_entry(command, payload, exit_code))

    if timed_out or invalid_files:
        return (
            {
                "status": "unavailable",
                "exit_code": max(exit_codes) if exit_codes else None,
                "reason": "timeout" if timed_out else "invalid_payload",
                "files": files,
                "invalid_files": sorted(set(invalid_files)),
            },
            results,
        )

    decisions: dict[str, int] = {}
    served: set[str] = set()
    rule_set_hashes: set[str] = set()
    complete_files = 0
    selection_levels: dict[str, int] = {}
    for entry in files:
        decision = str(entry["decision"])
        decisions[decision] = decisions.get(decision, 0) + 1
        served.update(entry["served_checkers"])
        rule_set_hashes.add(str(entry["rule_set_hash"]))
        if entry["check_volume"]["complete"]:
            complete_files += 1
        level = str(entry["selection"]["level"])
        selection_levels[level] = selection_levels.get(level, 0) + 1
    return (
        {
            "status": "recorded",
            "exit_code": max(exit_codes) if exit_codes else None,
            "files": files,
            "summary": {
                "files": len(files),
                "check_volume_complete": complete_files,
                "decisions": {name: decisions[name] for name in sorted(decisions)},
                "selection_levels": {
                    name: selection_levels[name] for name in sorted(selection_levels)
                },
                "served_checkers": sorted(served),
                "rule_set_hashes": sorted(rule_set_hashes),
            },
        },
        results,
    )


# ---------------------------------------------------------------------------
# A 维度
# ---------------------------------------------------------------------------
def _validate_a_payload(payload: Mapping[str, Any], declared_ids: Sequence[str]) -> str | None:
    """校验 structure_metrics 载荷；返回问题描述（None = 合法）。"""

    if not isinstance(payload.get("schema_version"), str):
        return "缺 schema_version"
    summary = payload.get("summary")
    predicates = payload.get("predicates")
    if not isinstance(summary, Mapping):
        return "缺 summary"
    passed = summary.get("passed")
    failed = summary.get("failed")
    if not _is_int(passed) or not _is_int(failed) or passed < 0 or failed < 0:
        return "summary.passed / summary.failed 不是合法计数"
    if not isinstance(predicates, list) or not predicates:
        return "predicates 不是非空列表"
    seen: set[str] = set()
    statuses: list[str] = []
    for predicate in predicates:
        if not isinstance(predicate, Mapping):
            return "predicates 里有非映射条目"
        predicate_id = predicate.get("id")
        status = predicate.get("status")
        if not isinstance(predicate_id, str) or not predicate_id or predicate_id in seen:
            return "predicates 的 id 缺失或重复"
        if status not in {"pass", "fail"}:
            return f"predicate {predicate_id} 的 status 不是 pass / fail"
        seen.add(predicate_id)
        statuses.append(status)
    if statuses.count("pass") != passed or statuses.count("fail") != failed:
        return "summary 与逐条谓词状态不一致"
    if declared_ids:
        missing = sorted(set(declared_ids) - seen)
        extra = sorted(seen - set(declared_ids))
        if missing or extra:
            return (
                "predicates 的 id 集合与 scoring.yaml 的 dimension_a.predicates 不相等："
                f"missing={missing} extra={extra}"
            )
    return None


def _collect_a(
    command: Mapping[str, Any], *, repo: Path, timeout: int, runner: Runner | None
) -> tuple[dict[str, Any], subprocess.CompletedProcess | None]:
    """采集 A 维度：退出码 1 是读数（有谓词 fail），2 才是声明错误。"""

    try:
        completed = _execute(command, repo=repo, timeout=timeout, runner=runner)
    except CommandTimeout:
        return {"status": "unavailable", "exit_code": None, "reason": "timeout"}, None

    exit_code = completed.returncode
    base: dict[str, Any] = {"status": "unavailable", "exit_code": exit_code}
    if exit_code == 2:
        base["reason"] = "declaration_error"
        return base, completed
    if exit_code not in (0, 1):
        base["reason"] = "unexpected_exit_code"
        return base, completed

    payload = _parse_json_object(_stdout_text(completed))
    if payload is None:
        base.update({"reason": "invalid_payload", "detail": "stdout 不是合法 JSON"})
        return base, completed
    problem = _validate_a_payload(payload, command["declared_predicate_ids"])
    if problem is not None:
        base.update({"reason": "invalid_payload", "detail": problem})
        return base, completed

    predicates = payload["predicates"]
    statuses = {str(item["id"]): item["status"] for item in predicates}
    failed_ids = [str(item["id"]) for item in predicates if item["status"] != "pass"]
    return (
        {
            "status": "recorded",
            "exit_code": exit_code,
            "schema_version": payload["schema_version"],
            "summary": {"passed": int(payload["summary"]["passed"]), "total": len(predicates)},
            "predicates": statuses,
            "failed_ids": failed_ids,
        },
        completed,
    )


# ---------------------------------------------------------------------------
# 组装 / 写盘 / CLI
# ---------------------------------------------------------------------------
def _report_unavailable(name: str, dimension: Mapping[str, Any]) -> None:
    """把不可用维度与点名文件写到 stderr（读数要看得出「哪个维度、哪个文件」）。"""

    if dimension.get("status") == "recorded":
        return
    message = f"collect: {name} 维度不可用（{dimension.get('reason', 'unknown')}）"
    detail = dimension.get("detail")
    if isinstance(detail, str) and detail:
        message += "：" + detail
    invalid = dimension.get("invalid_files")
    if isinstance(invalid, list) and invalid:
        message += "；不合法文件：" + ", ".join(str(item) for item in invalid)
    print(message, file=sys.stderr)


def _command_record(
    command: Mapping[str, Any], completed: subprocess.CompletedProcess | None
) -> dict[str, Any]:
    """commands[] 条目：脱敏后的 argv + 原样退出码（超时 = null）。"""

    return {
        "id": command["id"],
        "argv": list(command["display"]),
        "exit_code": None if completed is None else completed.returncode,
    }


def _summary_block(dimensions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """summary：三维状态与各自的头条读数（不可用维度不写 0）。"""

    def recorded(name: str) -> bool:
        return dimensions[name].get("status") == "recorded"

    t_summary = dimensions["T"].get("summary") if recorded("T") else None
    a_summary = dimensions["A"].get("summary") if recorded("A") else None
    c_summary = dimensions["C"].get("summary") if recorded("C") else None
    return {
        "all_recorded": all(recorded(name) for name in ("T", "C", "A")),
        "unavailable_dimensions": [name for name in ("T", "C", "A") if not recorded(name)],
        "T": {
            "status": dimensions["T"].get("status"),
            "passed": t_summary["passed"] if isinstance(t_summary, Mapping) else None,
            "total": t_summary["total"] if isinstance(t_summary, Mapping) else None,
        },
        "C": {
            "status": dimensions["C"].get("status"),
            "files": c_summary["files"] if isinstance(c_summary, Mapping) else None,
            "check_volume_complete": (
                c_summary["check_volume_complete"] if isinstance(c_summary, Mapping) else None
            ),
        },
        "A": {
            "status": dimensions["A"].get("status"),
            "passed": a_summary["passed"] if isinstance(a_summary, Mapping) else None,
            "total": a_summary["total"] if isinstance(a_summary, Mapping) else None,
        },
    }


def _record_payload(
    *,
    task_id: str,
    arm: str,
    tree_label: str,
    start: Mapping[str, Any],
    platform_generation: Mapping[str, Any],
    dimensions: Mapping[str, Mapping[str, Any]],
    summary: Mapping[str, Any],
    commands: Sequence[Mapping[str, Any]],
    process: Mapping[str, Any],
) -> dict[str, Any]:
    """组装 run-record（字段见 README；键序由 json.dumps(sort_keys=True) 保证）。"""

    return {
        "schema_version": BANK_RUN_RECORD_SCHEMA_VERSION,
        "task": task_id,
        "arm": arm,
        "tree": tree_label,
        "start": dict(start),
        "platform_generation": dict(platform_generation),
        "dimensions": {
            "T": dict(dimensions["T"]),
            "C": dict(dimensions["C"]),
            "A": dict(dimensions["A"]),
        },
        "summary": dict(summary),
        "commands": [dict(item) for item in commands],
        "process": dict(process),
    }


def _absolute_paths(value: Any, where: str = "$") -> list[str]:
    """递归找载荷里的绝对路径（盘符 / UNC / 以斜杠开头），返回命中的位置（不回显值）。"""

    hits: list[str] = []

    def is_absolute(text: str) -> bool:
        return text.startswith(("/", "\\")) or _WINDOWS_ABS.match(text) is not None

    def visit(item: Any, trail: str) -> None:
        if isinstance(item, str):
            if is_absolute(item):
                hits.append(trail)
            return
        if isinstance(item, Mapping):
            for key, child in item.items():
                if isinstance(key, str) and is_absolute(key):
                    hits.append(trail + "<key>")
                visit(child, f"{trail}.{key}")
            return
        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{trail}[{index}]")

    visit(value, where)
    return hits


def _write_record(path: Path, record: Mapping[str, Any]) -> None:
    """UTF-8 / LF / 单尾换行；键排序，不含时戳。"""

    text = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    """CLI 参数（冻结的命令形态见 README）。"""

    def positive_int(value: str) -> int:
        try:
            number = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"不是整数：{value}") from error
        if number <= 0:
            raise argparse.ArgumentTypeError(f"必须为正整数：{value}")
        return number

    parser = argparse.ArgumentParser(
        description=(
            "题库 run-record 采集器：一条命令采集 T（hidden runner）/ "
            "C（policy.check）/ A（structure_metrics）"
        )
    )
    parser.add_argument(
        "--task", required=True, help="题库题 id（必须与 scoring.yaml 的 task_id 一致）"
    )
    parser.add_argument(
        "--task-root",
        required=True,
        help="任务包目录（含 scoring.yaml / layers.yaml / hidden/）",
    )
    parser.add_argument("--tree", required=True, help="被评最终树根（相对路径按调用者 cwd 解析）")
    parser.add_argument("--arm", required=True, choices=ARMS, help="实验臂 A / B / C")
    parser.add_argument("--out", required=True, help="run-record JSON 输出路径")
    parser.add_argument(
        "--run-json", default=None, help="run_session 的 run.json（只抽过程读数）"
    )
    parser.add_argument(
        "--arm-config",
        default=None,
        help="materialized 臂配置目录（读四个声明文件的 sha256）",
    )
    parser.add_argument("--model", default=None, help="provider/model 标识（缺 = null + note）")
    parser.add_argument("--head", default=None, help="起点 HEAD（缺 = 尝试 git；再缺 = unknown）")
    parser.add_argument(
        "--sandbox",
        default="unknown",
        choices=list(SANDBOX_STATES),
        help="本次采集所在沙箱形态（缺 = unknown）",
    )
    parser.add_argument(
        "--dsh-runtime", default=None, help="宿主运行时版本（缺 = null + note）"
    )
    parser.add_argument(
        "--dsh-source",
        default="unknown",
        choices=list(DSH_SOURCES),
        help="dsh 来路（缺 = unknown + note）",
    )
    parser.add_argument(
        "--request-id-prefix",
        default=None,
        dest="request_prefix",
        help="request id 前缀（默认 = --task；最终 <前缀>-<arm>-<file-slug>）",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=positive_int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"单条子进程超时（默认 {DEFAULT_TIMEOUT_SECONDS} 秒）",
    )
    parser.add_argument(
        "--determinism",
        action="store_true",
        help="T 再跑一次并记录两次 stdout 是否逐字节相同",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只打印计划命令，不执行、不写 --out"
    )
    return parser


def run(
    argv: list[str] | None = None,
    *,
    runner: Runner | None = None,
    repo_root: Path | None = None,
    git: GitProbe | None = None,
) -> int:
    """采集一次三维读数；返回进程退出码（0 / 1 / 2）。"""

    args = build_parser().parse_args(argv)
    request_prefix = (args.request_prefix or "").strip()

    try:
        repo = repo_root if repo_root is not None else _find_repo()
        inputs = _load_inputs(args, repo)
        versions = _platform_versions()
        prefix = request_prefix or inputs["scoring"]["task_id"]
        commands, _labels = _build_commands(
            inputs, repo=repo, arm=args.arm, request_prefix=prefix
        )
    except InputError as error:
        print(f"collect: 输入声明不可读：{error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    t_command = commands[0]
    a_command = commands[1]
    c_commands = commands[2:]
    t_command.update(
        {
            "declared_total": inputs["scoring"]["t"]["total"],
            "case_ids": list(inputs["scoring"]["t"]["case_ids"]),
        }
    )
    a_command["declared_predicate_ids"] = list(inputs["scoring"]["a"]["predicate_ids"])

    if args.dry_run:
        _print_plan(commands)
        return EXIT_OK

    try:
        start = _start_block(inputs["head"], repo=repo, git=git)
        platform_generation = _platform_generation(
            args, repo=repo, versions=versions, arm_config=inputs["arm_config"]
        )
        process = _process_block(inputs["run_json"], repo=repo)
    except InputError as error:
        print(f"collect: 输入声明不可读：{error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    pending_hidden = inputs["scoring"]["t"]["status"] == T_PENDING_STATUS
    t_second: subprocess.CompletedProcess | None = None
    if pending_hidden:
        t_dim: dict[str, Any] = {
            "status": "unavailable",
            "exit_code": None,
            "reason": "hidden_not_frozen",
            "determinism": _fresh_determinism(),
        }
        t_completed = None
    else:
        t_dim, t_completed, t_first_stdout = _collect_t(
            t_command, repo=repo, timeout=args.timeout_seconds, runner=runner
        )
        if args.determinism and t_dim["status"] == "recorded":
            try:
                second = _execute(
                    t_command, repo=repo, timeout=args.timeout_seconds, runner=runner
                )
            except CommandTimeout:
                t_dim["determinism"] = {
                    "checked": True,
                    "runs": 1,
                    "stdout_byte_identical": None,
                    "exit_code_identical": None,
                }
            else:
                t_second = second
                t_dim["determinism"] = {
                    "checked": True,
                    "runs": 2,
                    "stdout_byte_identical": _stdout_bytes(second) == t_first_stdout,
                    "exit_code_identical": second.returncode == t_dim["exit_code"],
                }

    a_dim, a_completed = _collect_a(
        a_command, repo=repo, timeout=args.timeout_seconds, runner=runner
    )
    c_dim, c_results = _collect_c(
        c_commands, repo=repo, timeout=args.timeout_seconds, runner=runner
    )

    command_records = [
        _command_record(t_command, t_completed),
        _command_record(a_command, a_completed),
    ]
    command_records.extend(_command_record(command, completed) for command, completed in c_results)
    if t_second is not None:
        command_records.append(_command_record(dict(t_command, id="T:rerun"), t_second))

    dimensions = {"T": t_dim, "C": c_dim, "A": a_dim}
    for name in ("T", "A", "C"):
        _report_unavailable(name, dimensions[name])

    record = _record_payload(
        task_id=inputs["scoring"]["task_id"],
        arm=args.arm,
        tree_label=_display_path(inputs["tree"], repo),
        start=start,
        platform_generation=platform_generation,
        dimensions=dimensions,
        summary=_summary_block(dimensions),
        commands=command_records,
        process=process,
    )
    leaks = _absolute_paths(record)
    if leaks:
        print(
            "collect: 载荷里出现绝对路径 %s —— 拒绝写盘（协议要求载荷可移植）" % leaks,
            file=sys.stderr,
        )
        return EXIT_UNAVAILABLE

    out = Path(args.out)
    out = (out if out.is_absolute() else Path.cwd() / out).resolve()
    try:
        _write_record(out, record)
    except OSError as error:
        print(f"collect: 写不了 --out（{type(error).__name__}）", file=sys.stderr)
        return EXIT_UNAVAILABLE

    all_recorded = all(dim.get("status") == "recorded" for dim in (t_dim, c_dim, a_dim))
    if not all_recorded:
        print(
            "collect: 有维度没采到（status=unavailable）；run-record 已写出，退出码 1",
            file=sys.stderr,
        )
        return EXIT_UNAVAILABLE
    print(
        "collect: T={t}/{tt} C=files:{c} A={a}/{at}；run-record 已写出 → {out}".format(
            t=record["summary"]["T"]["passed"],
            tt=record["summary"]["T"]["total"],
            c=record["summary"]["C"]["files"],
            a=record["summary"]["A"]["passed"],
            at=record["summary"]["A"]["total"],
            out=_display_path(out, repo),
        )
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""

    return run(argv)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

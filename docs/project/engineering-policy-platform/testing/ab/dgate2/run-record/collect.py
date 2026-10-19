#!/usr/bin/env python3
"""collect.py — D 门 2 的 T / C / A 三维读数采集器（run-record）。

它是什么
========

一次采集把三个维度的读数落成**确定性的 run-record JSON**，供 run-manifest 的
`readings` 字段消费（另一个子会话负责 run-manifest）。三个维度都只做子进程调用，
**不 import 被测代码、不联网**：

- T：`.venv python <hidden/runner.py> --json`，环境变量 `POLICY_TREE` / `DGATE2_TMPDIR`；
- C：对 `scorer.yaml measurement.changed_files` 里的 8 个 .py 各跑一次
  `python -m policy.check <file> --workspace <tree> --config-root <root>
  --layer <layers.yaml 的层> --operation edit --changed <9 条> --request-id <固定值> --json`；
- A：`.venv python tools/structure_metrics.py --workspace <tree> --layers <layers>
  --interfaces <interfaces> --json`。

版本轴
======

`RUN_RECORD_SCHEMA_VERSION = "1.0"`：**1.0 = 首次建轴**。加键或改语义必须按 AGENTS
第 55 条显式递增（并同批改 README 与用例），不许"只加一个键"了事。

确定性
======

载荷里没有时戳、没有 run 标识、没有耗时；对象键按字典序输出，列表顺序固定
（T 的 cases 顺序、C 的 changed_files 顺序）；request id 由 `--request-id` 前缀 + arm
+ 文件 slug 拼出，同一输入两次运行**逐字节相同**。绝对路径一律不落盘：
仓库内写成仓库相对 POSIX 路径，仓库外写成 `<outside-workspace>`。

退出码
======

- `0` = T / C / A 三维全部采到（T 全过或部分失败都算采到；A 的退出码 1 也是读数）；
- `1` = 有维度没采到（runner 退出 2、policy.check 输出不合法、子进程超时等）或载荷不合法；
- `2` = 输入声明读不出来（树、config-root、layers、interfaces、scorer.yaml 缺失或不可解析，
  或 declaration 自相矛盾）。

边界（详见同目录 README）
=========================

- C 只量改动面的 8 个 .py（整树 13 个 .py 会把没改的 `__init__.py` 判成缺测试，是测量假象；
  理由与实测见 `../scorer/README.md` 第 3 节）；
- A 的「有保留 1 分」档没有数据源（`structure_metrics` 1.1 只有 pass/fail，04 5.79①）；
- T 的规格含糊见 `../hidden/README.md` 的「已知边界」节（04 5.79④）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

import yaml

#: run-record 载荷自己的版本轴。1.0 = 首次建轴；加键 / 改语义必须递增。
RUN_RECORD_SCHEMA_VERSION = "1.0"
#: 单条子进程的默认超时（秒）。T 约 10–30 s，C 每文件约 3–7 s。
DEFAULT_TIMEOUT_SECONDS = 300
#: `--request-id` 的默认前缀；最终 = `<前缀>-<arm>-<file-slug>`。
DEFAULT_REQUEST_PREFIX = "dgate2"
ARMS = ("A", "B", "C")
OUTSIDE_WORKSPACE = "<outside-workspace>"
EXIT_OK = 0
EXIT_UNAVAILABLE = 1
EXIT_INPUT_ERROR = 2
#: T 的临时副本父目录名（放在 --out 同目录下；可被 DGATE2_TMPDIR 覆盖）。
TEMP_SUBDIR = "dgate2-tmp"
#: run-record 里没有"字段缺失"这个含义的对象：用它区分"键不存在"与"值是 null"。
_MISSING = object()

Runner = Callable[..., subprocess.CompletedProcess]


class InputError(Exception):
    """输入声明读不出来（退出码 2）。"""


class CommandTimeout(Exception):
    """子进程超时（该维度 unavailable，总结算退出码 1）。"""


# ---------------------------------------------------------------------------
# 路径 / 环境 / 子进程
# ---------------------------------------------------------------------------
def _find_repo(start: Path | None = None) -> Path:
    """从 collect.py 向上找仓库根（以 src/policy 与 .venv 为准）。"""

    here = (start or Path(__file__)).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "src" / "policy").is_dir() and (candidate / ".venv").is_dir():
            return candidate
    raise InputError("找不到仓库根：从 collect.py 向上找不到 src/policy 与 .venv")


def _relative_if_inside(path: Path, repo: Path) -> str | None:
    """仓库内路径 -> 仓库相对 POSIX 路径；仓库外返回 None。"""

    try:
        relative = path.resolve().relative_to(repo.resolve())
    except ValueError:
        return None
    return relative.as_posix() or "."


def _display_path(path: Path, repo: Path) -> str:
    """读数里显示的路径：仓库内相对，仓库外一律 <outside-workspace>。"""

    relative = _relative_if_inside(path, repo)
    return relative if relative is not None else OUTSIDE_WORKSPACE


def _interpreter(repo: Path) -> Path:
    """定位 .venv 解释器（Windows 优先，POSIX 兜底）。"""

    for relative in (Path(".venv/Scripts/python.exe"), Path(".venv/bin/python")):
        candidate = repo / relative
        if candidate.is_file():
            return candidate
    raise InputError("找不到 .venv 解释器（.venv/Scripts/python.exe 或 .venv/bin/python）")


def _base_env() -> dict[str, str]:
    """子进程的干净环境：继承调用者环境，但不写字节码（不污染工作树）。"""

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
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            **kwargs,
        )
    except subprocess.TimeoutExpired as error:
        raise CommandTimeout(f"{command['id']} 超过 {timeout} 秒") from error


def _stdout(completed: subprocess.CompletedProcess) -> str:
    """取子进程 stdout 文本（兼容注入的 runner 返回 bytes 的情况）。"""

    value = completed.stdout
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """解析 JSON 对象；不是合法对象一律返回 None（调用方按载荷不合法处理）。"""

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _dig(payload: Mapping[str, Any], dotted: str) -> Any:
    """按点分路径取值；键不存在返回 _MISSING（与"值是 null"分开）。"""

    current: Any = payload
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _is_int(value: Any) -> bool:
    """bool 是 int 的子类，读数里不许把 true 当 1。"""

    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# 输入声明（失败关闭：缺失 / 不可解析 => 退出码 2）
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


def _derive_reading_paths(reading_keys: list[str], *, repo: Path) -> list[str]:
    """从 scorer.yaml 的 reading_keys 推出要校验的载荷路径。

    reading_keys 是给人读的文本（可能带中文括注，如
    "result.violations（真的报了违规的规则）"），所以只取第一个「（」之前的部分，
    再按「与」拆出并列的键（"exit_code 与 layer_source"）。
    """

    paths: list[str] = []
    for key in reading_keys:
        head = key.split("（", 1)[0]
        for part in re.split(r"\s*与\s*", head):
            token = part.strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", token):
                paths.append(token)
    if not paths:
        raise InputError("scorer.yaml 的 measurement.reading_keys 里没有可解析的读数路径")
    return paths


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


def _normalize_interfaces(raw: Mapping[str, Any], *, repo: Path, path: Path) -> dict[str, int]:
    """interfaces.yaml：文件相对路径 -> 公开定义上限（整数）。"""

    interfaces: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _is_int(value) or value < 0:
            raise InputError(
                f"interfaces.yaml 的条目不是「路径: 非负整数」：{_display_path(path, repo)}"
            )
        interfaces[key.replace("\\", "/")] = value
    return interfaces


def _read_scorer(scorer_path: Path, *, repo: Path) -> dict[str, Any]:
    """读 scorer.yaml 里本采集器需要的四块：changed / rules / reading_keys / weights。"""

    payload = _load_yaml_mapping(scorer_path, "scorer.yaml", repo=repo)
    measurement = payload.get("measurement")
    if not isinstance(measurement, Mapping):
        raise InputError("scorer.yaml 缺 measurement 映射")

    changed_block = measurement.get("changed_files")
    paths = changed_block.get("paths") if isinstance(changed_block, Mapping) else None
    if (
        not isinstance(paths, list)
        or not paths
        or not all(isinstance(item, str) and item for item in paths)
    ):
        raise InputError("scorer.yaml 的 measurement.changed_files.paths 不是非空字符串列表")
    changed = [item.replace("\\", "/") for item in paths]
    if len(set(changed)) != len(changed):
        raise InputError("scorer.yaml 的 measurement.changed_files.paths 有重复项")

    py_files = [item for item in changed if item.endswith(".py")]
    if not py_files:
        raise InputError("scorer.yaml 的 measurement.changed_files 里没有 .py 文件")
    file_count = measurement.get("file_count")
    if file_count is not None and (not _is_int(file_count) or file_count != len(py_files)):
        raise InputError(
            "scorer.yaml 的 measurement.file_count 与 changed_files 里的 .py 数不一致"
        )

    reading_keys = measurement.get("reading_keys")
    if not isinstance(reading_keys, list) or not reading_keys or not all(
        isinstance(item, str) and item for item in reading_keys
    ):
        raise InputError("scorer.yaml 的 measurement.reading_keys 不是非空字符串列表")
    reading_paths = _derive_reading_paths(reading_keys, repo=repo)

    rules_block = payload.get("rules")
    items = rules_block.get("items") if isinstance(rules_block, Mapping) else None
    if not isinstance(items, list) or not items:
        raise InputError("scorer.yaml 的 rules.items 不是非空列表")
    rules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise InputError("scorer.yaml 的 rules.items 里有非映射条目")
        rule_id = item.get("rule_id")
        rule_version = item.get("rule_version")
        severity = item.get("severity")
        if not isinstance(rule_id, str) or not rule_id:
            raise InputError("scorer.yaml 的规则缺 rule_id")
        if not _is_int(rule_version) or rule_version < 1:
            raise InputError(f"scorer.yaml 的规则 {rule_id} 的 rule_version 不是正整数")
        if severity not in {"info", "warning", "error", "critical"}:
            raise InputError(f"scorer.yaml 的规则 {rule_id} 的 severity 不是已知级别")
        canonical = f"{rule_id}@{rule_version}"
        if canonical in seen:
            raise InputError(f"scorer.yaml 的规则 {canonical} 重复")
        seen.add(canonical)
        rules.append(
            {
                "rule_id": rule_id,
                "rule_version": rule_version,
                "severity": severity,
                "canonical": canonical,
            }
        )

    scoring_block = rules_block.get("scoring")
    if not isinstance(scoring_block, Mapping):
        raise InputError("scorer.yaml 缺 rules.scoring 映射")

    def score_value(name: str) -> int:
        value = scoring_block.get(name)
        if not _is_int(value) or value < 0:
            raise InputError(f"scorer.yaml 的 rules.scoring.{name} 不是非负整数")
        return value

    scoring = {
        "no_violation": score_value("no_violation"),
        "warning_only": score_value("warning_only"),
        "error_hit": score_value("error_hit"),
    }

    per_predicate: int | None = None
    weights = payload.get("weights")
    if isinstance(weights, Mapping):
        a_internal = weights.get("a_internal")
        if isinstance(a_internal, Mapping):
            value = a_internal.get("per_predicate")
            if value is not None:
                if not _is_int(value) or value < 0:
                    raise InputError("scorer.yaml 的 weights.a_internal.per_predicate 不是非负整数")
                per_predicate = value

    return {
        "changed": changed,
        "py_files": py_files,
        "rules": rules,
        "reading_paths": reading_paths,
        "scoring": scoring,
        "per_predicate": per_predicate,
    }


def _load_inputs(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    """校验并装载全部输入声明；任何一项读不出来都抛 InputError。"""

    tree = Path(args.tree)
    tree = (tree if tree.is_absolute() else Path.cwd() / tree).resolve()
    config_root = Path(args.config_root)
    config_root = (config_root if config_root.is_absolute() else Path.cwd() / config_root).resolve()
    layers_path = Path(args.layers)
    layers_path = (layers_path if layers_path.is_absolute() else Path.cwd() / layers_path).resolve()
    interfaces_path = Path(args.interfaces)
    interfaces_path = (
        interfaces_path if interfaces_path.is_absolute() else Path.cwd() / interfaces_path
    ).resolve()

    if not tree.is_dir():
        raise InputError(f"--tree 不是目录：{_display_path(tree, repo)}")
    if not config_root.is_dir():
        raise InputError(f"--config-root 不是目录：{_display_path(config_root, repo)}")
    if not (config_root / "validation").is_dir():
        raise InputError(
            f"--config-root 下没有 validation/：{_display_path(config_root, repo)}"
            "（config-root 指的是包含 validation/ 的那一层）。"
        )

    layers = _normalize_layers(
        _load_yaml_mapping(layers_path, "layers.yaml", repo=repo), repo=repo, path=layers_path
    )
    interfaces = _normalize_interfaces(
        _load_yaml_mapping(interfaces_path, "interfaces.yaml", repo=repo),
        repo=repo,
        path=interfaces_path,
    )

    scorer_path = layers_path.parent / "scorer.yaml"
    if not scorer_path.is_file():
        scorer_path = _find_repo() / "docs" / "project" / "engineering-policy-platform" / (
            "testing/ab/dgate2/scorer/scorer.yaml"
        )
    if not scorer_path.is_file():
        raise InputError("找不到 scorer.yaml（既不在 layers.yaml 同目录，也不在 dgate2/scorer/）")
    scorer = _read_scorer(scorer_path, repo=repo)

    layers_for_files: dict[str, str] = {}
    for relative in scorer["py_files"]:
        layer = layers.get(relative)
        if layer is None:
            raise InputError(f"layers.yaml 缺 {relative} 的层值；不猜层")
        if not (tree / relative).is_file():
            raise InputError(f"--tree 里没有改动文件：{relative}")
        layers_for_files[relative] = layer

    return {
        "tree": tree,
        "config_root": config_root,
        "layers_path": layers_path,
        "interfaces_path": interfaces_path,
        "scorer_path": scorer_path,
        "layers": layers,
        "interfaces": interfaces,
        "layers_for_files": layers_for_files,
        **scorer,
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
    tmp_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """按 T -> A -> C（changed_files 顺序）生成命令计划。"""

    interpreter = _interpreter(repo)
    runner_path = Path(__file__).resolve().parents[1] / "hidden" / "runner.py"
    metrics_path = repo / "tools" / "structure_metrics.py"
    if not runner_path.is_file():
        raise InputError(f"找不到 T 的 runner.py：{_display_path(runner_path, repo)}")
    if not metrics_path.is_file():
        raise InputError(f"找不到 A 的 structure_metrics.py：{_display_path(metrics_path, repo)}")

    tree = inputs["tree"]
    labels = {
        str(tree): _display_path(tree, repo),
        str(inputs["config_root"]): _display_path(inputs["config_root"], repo),
        str(inputs["layers_path"]): _display_path(inputs["layers_path"], repo),
        str(inputs["interfaces_path"]): _display_path(inputs["interfaces_path"], repo),
    }

    t_env = _base_env()
    t_env["POLICY_TREE"] = str(tree)
    t_env["DGATE2_TMPDIR"] = str(tmp_dir)
    t_argv = [str(interpreter), str(runner_path), "--json"]

    a_env = _base_env()
    a_env.pop("POLICY_TREE", None)
    a_env.pop("DGATE2_TMPDIR", None)
    a_argv = [
        str(interpreter),
        str(metrics_path),
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

    for relative in inputs["py_files"]:
        slug = re.sub(r"[^a-z0-9]+", "-", relative.lower()).strip("-")
        request_id = f"{request_prefix}-{arm}-{slug}"
        c_env = _base_env()
        c_env.pop("POLICY_TREE", None)
        c_env.pop("DGATE2_TMPDIR", None)
        c_env["PYTHONPATH"] = "src"
        c_argv = [
            str(interpreter),
            "-m",
            "policy.check",
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
        for changed in inputs["changed"]:
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


def _print_plan(commands: list[Mapping[str, Any]]) -> None:
    """--dry-run：只打印计划命令，不执行、不写文件。"""

    print("[collect] dry-run：只打印计划命令，不执行子进程、不写 --out")
    for command in commands:
        print(f"[dry-run] {command['id']}: {shlex.join(command['display'])}")
    print(f"[collect] 共 {len(commands)} 条命令")


# ---------------------------------------------------------------------------
# 载荷校验与采集
# ---------------------------------------------------------------------------
def _validate_t_payload(payload: Mapping[str, Any], exit_code: int) -> str | None:
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


def _failed_ids(cases: list[Mapping[str, Any]]) -> list[str]:
    """按 cases 顺序列出失败条目的 id。"""

    return [str(case["id"]) for case in cases if not case.get("pass")]


def _collect_t(
    command: Mapping[str, Any], *, repo: Path, timeout: int, runner: Runner | None
) -> tuple[dict[str, Any], subprocess.CompletedProcess | None]:
    """T 维度：runner 退出码 2 = 无法判（unavailable），不是 0 分。"""

    try:
        completed = _execute(command, repo=repo, timeout=timeout, runner=runner)
    except CommandTimeout:
        return {"status": "unavailable", "exit_code": None, "reason": "timeout"}, None

    exit_code = completed.returncode
    base: dict[str, Any] = {"status": "unavailable", "exit_code": exit_code}
    if exit_code == 2:
        base["reason"] = "runner_cannot_run"
        return base, completed
    if exit_code not in (0, 1):
        base["reason"] = "unexpected_exit_code"
        return base, completed

    payload = _parse_json_object(_stdout(completed))
    if payload is None:
        base.update({"reason": "invalid_payload", "detail": "stdout 不是合法 JSON"})
        return base, completed
    problem = _validate_t_payload(payload, exit_code)
    if problem is not None:
        base.update({"reason": "invalid_payload", "detail": problem})
        return base, completed

    summary = payload["summary"]
    cases = payload["cases"]
    return (
        {
            "status": "recorded",
            "exit_code": exit_code,
            "schema_version": payload["schema_version"],
            "summary": {"passed": summary["passed"], "total": summary["total"]},
            "failed_ids": _failed_ids(cases),
            "points": summary["passed"],
        },
        completed,
    )


def _validate_a_payload(payload: Mapping[str, Any], exit_code: int) -> str | None:
    """校验 structure_metrics 载荷（退出码 1 是读数，不是执行失败）。"""

    if not isinstance(payload.get("schema_version"), str):
        return "缺 schema_version"
    predicates = payload.get("predicates")
    summary = payload.get("summary")
    if not isinstance(predicates, list) or not predicates:
        return "predicates 不是非空列表"
    if not isinstance(summary, Mapping):
        return "缺 summary"
    if not _is_int(summary.get("passed")) or not _is_int(summary.get("failed")):
        return "summary.passed / summary.failed 不是整数"
    statuses: list[str] = []
    ids: set[str] = set()
    for predicate in predicates:
        if not isinstance(predicate, Mapping):
            return "predicates 里有非映射条目"
        predicate_id = predicate.get("id")
        status = predicate.get("status")
        if not isinstance(predicate_id, str) or not predicate_id or predicate_id in ids:
            return "predicates 的 id 缺失或重复"
        if status not in {"pass", "fail"}:
            return f"谓词 {predicate_id} 的 status 不是 pass / fail"
        ids.add(predicate_id)
        statuses.append(status)
    passed = statuses.count("pass")
    failed = len(statuses) - passed
    if summary.get("passed") != passed or summary.get("failed") != failed:
        return "summary 与逐谓词 status 计数不一致"
    if exit_code == 0 and failed != 0:
        return "structure_metrics 退出码 0 但存在 fail 谓词"
    if exit_code == 1 and failed == 0:
        return "structure_metrics 退出码 1 但没有 fail 谓词"
    return None


def _collect_a(
    command: Mapping[str, Any],
    *,
    repo: Path,
    timeout: int,
    runner: Runner | None,
    per_predicate: int | None,
) -> tuple[dict[str, Any], subprocess.CompletedProcess | None]:
    """采集 A 维度：predicates 的 pass 计数 × 每条谓词分值。"""

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

    payload = _parse_json_object(_stdout(completed))
    if payload is None:
        base.update({"reason": "invalid_payload", "detail": "stdout 不是合法 JSON"})
        return base, completed
    problem = _validate_a_payload(payload, exit_code)
    if problem is not None:
        base.update({"reason": "invalid_payload", "detail": problem})
        return base, completed

    predicates = payload["predicates"]
    statuses = {str(item["id"]): item["status"] for item in predicates}
    failed_ids = [str(item["id"]) for item in predicates if item["status"] != "pass"]
    passed = len(predicates) - len(failed_ids)
    a3_basis: str | None = None
    for predicate in predicates:
        if predicate.get("id") == "A3":
            detail = predicate.get("detail")
            if isinstance(detail, Mapping) and isinstance(detail.get("basis"), str):
                a3_basis = detail["basis"]
    return (
        {
            "status": "recorded",
            "exit_code": exit_code,
            "schema_version": payload["schema_version"],
            "summary": {"passed": passed, "failed": len(failed_ids)},
            "predicates": {
                "passed": passed,
                "failed": len(failed_ids),
                "failed_ids": failed_ids,
                "statuses": statuses,
            },
            "a3_basis": a3_basis,
            "points": None if per_predicate is None else passed * per_predicate,
        },
        completed,
    )


def _validate_c_payload(
    payload: Mapping[str, Any], exit_code: int, reading_paths: list[str]
) -> str | None:
    """校验 policy.check 的 --json 载荷；缺任一 reading_key 都算载荷不合法。"""

    result = payload.get("result")
    if not isinstance(result, Mapping):
        return "缺 result 决策载荷"
    for path in reading_paths:
        value = _dig(payload, path)
        if value is _MISSING or value is None:
            return f"缺读数 {path}"
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
    evidence = result.get("evidence")
    if isinstance(evidence, Mapping) and "served_checkers" in evidence:
        served = evidence["served_checkers"]
        if not isinstance(served, list) or not all(isinstance(item, str) for item in served):
            return "evidence.served_checkers 不是字符串列表"
    served_top = payload.get("evidence")
    if isinstance(served_top, Mapping):
        served = served_top.get("served_checkers")
        if not isinstance(served, list) or not all(isinstance(item, str) for item in served):
            return "evidence.served_checkers 不是字符串列表"
    volume = payload.get("check_volume")
    if not isinstance(volume, Mapping) or not isinstance(volume.get("complete"), bool):
        return "check_volume.complete 不是布尔值"
    if not isinstance(payload.get("layer_source"), str):
        return "缺 layer_source"
    return None


def _sanitize_text(text: str, *, repo: Path, labels: Mapping[str, str]) -> str:
    """违规 message 等自由文本：把已知根与 Windows 绝对路径脱敏。"""

    cleaned = text
    for absolute, label in labels.items():
        cleaned = cleaned.replace(absolute, label)
    cleaned = re.sub(r"[A-Za-z]:[\\/][^\s\"'，。；、]*", OUTSIDE_WORKSPACE, cleaned)
    return cleaned


def _c_file_entry(
    command: Mapping[str, Any],
    payload: Mapping[str, Any],
    exit_code: int,
    *,
    repo: Path,
    labels: Mapping[str, str],
) -> tuple[dict[str, Any], set[str], list[dict[str, Any]]]:
    """把一次 policy.check 载荷压成逐文件读数；同时返回 matched 集合与命中明细。"""

    result = payload["result"]
    volume = payload["check_volume"]
    served = payload["evidence"]["served_checkers"]
    hits: list[dict[str, Any]] = []
    for violation in result["violations"]:
        evidence = violation.get("evidence")
        evidence = evidence if isinstance(evidence, Mapping) else {}
        hits.append(
            {
                "rule": f"{violation['rule_id']}@{violation['rule_version']}",
                "severity": violation["severity"],
                "message": _sanitize_text(
                    str(violation.get("message", "")), repo=repo, labels=labels
                ),
                "file": (
                    _sanitize_text(str(evidence["file"]), repo=repo, labels=labels)
                    if isinstance(evidence.get("file"), str)
                    else None
                ),
                "line": evidence.get("line"),
            }
        )
    entry = {
        "status": "recorded",
        "file": command["file"],
        "request_id": command["request_id"],
        "layer": command["layer"],
        "layer_source": payload["layer_source"],
        "decision": result["decision"],
        "exit_code": exit_code,
        "matched": len(result["matched_rules"]),
        "skipped": len(result["skipped_rules"]),
        "skipped_rule_ids": [str(item["rule_id"]) for item in result["skipped_rules"]],
        "violations": len(hits),
        "hits": hits,
        "served": [str(item) for item in served],
        "rule_set_hash": result["rule_set_hash"],
        "check_volume": {
            "complete": volume["complete"],
            "blocking_capable_skipped": volume.get("blocking_capable_skipped"),
            "missing_dimensions": list(volume.get("missing_dimensions") or []),
        },
        "output_schema_version": payload.get("output_schema_version"),
    }
    return entry, set(result["matched_rules"]), hits


def _score_rules(
    rules: list[Mapping[str, Any]],
    matched: set[str],
    hits_by_rule: Mapping[str, list[dict[str, Any]]],
    scoring: Mapping[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """按 scorer.yaml 的 8 条规则计分：error=0 / warning-only=2 / 无=3。"""

    scored: list[dict[str, Any]] = []
    total = 0
    not_measured: list[str] = []
    for rule in rules:
        canonical = str(rule["canonical"])
        hits = hits_by_rule.get(canonical, [])
        severities = sorted({str(hit["severity"]) for hit in hits})
        measured = canonical in matched
        if not measured:
            points = 0
            not_measured.append(str(rule["rule_id"]))
        elif any(severity in {"error", "critical"} for severity in severities):
            points = scoring["error_hit"]
        elif any(severity in {"warning", "info"} for severity in severities):
            points = scoring["warning_only"]
        else:
            points = scoring["no_violation"]
        total += points
        scored.append(
            {
                "rule_id": rule["rule_id"],
                "rule_version": rule["rule_version"],
                "severity": rule["severity"],
                "measured": measured,
                "hits": len(hits),
                "hit_severities": severities,
                "points": points,
            }
        )
    score = {
        "points": total,
        "max": scoring["no_violation"] * len(rules),
        "rules_scored": len(rules),
        "not_measured": not_measured,
    }
    return scored, score


def _collect_c(
    commands: list[Mapping[str, Any]],
    *,
    repo: Path,
    timeout: int,
    runner: Runner | None,
    inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], list[tuple[Mapping[str, Any], subprocess.CompletedProcess | None]]]:
    """C 维度：逐文件 policy.check；任一份载荷不合法 => C unavailable。"""

    files: list[dict[str, Any]] = []
    results: list[tuple[Mapping[str, Any], subprocess.CompletedProcess | None]] = []
    matched: set[str] = set()
    hits_by_rule: dict[str, list[dict[str, Any]]] = {}
    invalid_files: list[str] = []
    timed_out = False
    exit_codes: list[int] = []
    labels = {
        str(inputs["tree"]): _display_path(inputs["tree"], repo),
        str(inputs["config_root"]): _display_path(inputs["config_root"], repo),
        str(inputs["layers_path"]): _display_path(inputs["layers_path"], repo),
        str(inputs["interfaces_path"]): _display_path(inputs["interfaces_path"], repo),
    }

    for command in commands:
        try:
            completed = _execute(command, repo=repo, timeout=timeout, runner=runner)
        except CommandTimeout:
            timed_out = True
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
        payload = _parse_json_object(_stdout(completed))
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
        problem = _validate_c_payload(payload, exit_code, inputs["reading_paths"])
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
                }
            )
            continue

        entry, file_matched, hits = _c_file_entry(
            command, payload, exit_code, repo=repo, labels=labels
        )
        files.append(entry)
        matched.update(file_matched)
        for hit in hits:
            hits_by_rule.setdefault(str(hit["rule"]), []).append(hit)

    if timed_out or invalid_files:
        reason = "timeout" if timed_out else "invalid_payload"
        dimension: dict[str, Any] = {
            "status": "unavailable",
            "exit_code": max(exit_codes) if exit_codes else None,
            "reason": reason,
            "files": files,
        }
        if invalid_files:
            dimension["invalid_files"] = invalid_files
            dimension["reason"] = "invalid_payload" if not timed_out else "timeout"
        dimension["score"] = None
        dimension["rules"] = []
        return dimension, results

    rules, score = _score_rules(inputs["rules"], matched, hits_by_rule, inputs["scoring"])
    decisions: dict[str, int] = {}
    served_union: set[str] = set()
    schema_versions: set[str] = set()
    rule_set_hashes: set[str] = set()
    for entry in files:
        decision = str(entry["decision"])
        decisions[decision] = decisions.get(decision, 0) + 1
        served_union.update(entry["served"])
        if isinstance(entry.get("output_schema_version"), str):
            schema_versions.add(entry["output_schema_version"])
        rule_set_hashes.add(str(entry["rule_set_hash"]))
    return (
        {
            "status": "recorded",
            "exit_code": max(exit_codes) if exit_codes else None,
            "files": files,
            "rules": rules,
            "score": score,
            "payloads": {
                "output_schema_versions": sorted(schema_versions),
                "rule_set_hashes": sorted(rule_set_hashes),
                "decisions": {name: decisions[name] for name in sorted(decisions)},
                "served_checkers": sorted(served_union),
            },
        },
        results,
    )


# ---------------------------------------------------------------------------
# 组装 / 写盘 / CLI
# ---------------------------------------------------------------------------
def _report_unavailable(name: str, dimension: Mapping[str, Any]) -> None:
    """把不可用维度与点名文件写到 stderr（读数要看得出「哪个维度、哪个文件」）。"""

    if dimension.get("status") == "recorded":
        return
    message = f"collect: {name} 维度不可用（{dimension.get('reason', 'unknown')}）"
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


def _record_payload(
    *,
    arm: str,
    inputs: Mapping[str, Any],
    repo: Path,
    t_dim: Mapping[str, Any],
    a_dim: Mapping[str, Any],
    c_dim: Mapping[str, Any],
    command_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """组装 run-record（字段见 README；排序由 json.dumps(sort_keys=True) 保证）。"""

    def recorded(dimension: Mapping[str, Any]) -> bool:
        return dimension.get("status") == "recorded"

    t_summary = t_dim.get("summary") if recorded(t_dim) else None
    a_summary = a_dim.get("summary") if recorded(a_dim) else None
    c_score = c_dim.get("score") if recorded(c_dim) else None
    return {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "arm": arm,
        "tree": _display_path(inputs["tree"], repo),
        "dimensions": {"T": t_dim, "C": c_dim, "A": a_dim},
        "summary": {
            "t_passed": t_summary["passed"] if isinstance(t_summary, Mapping) else None,
            "c_rules_scored": c_score["rules_scored"] if isinstance(c_score, Mapping) else None,
            "a_predicates_passed": (
                a_summary["passed"] if isinstance(a_summary, Mapping) else None
            ),
        },
        "commands": command_records,
    }


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
            "D 门 2 run-record 采集器：一条命令采集 T（runner）/ "
            "C（policy.check）/ A（structure_metrics）"
        )
    )
    parser.add_argument("--tree", required=True, help="被评最终树根（相对路径按调用者 cwd 解析）")
    parser.add_argument(
        "--config-root",
        required=True,
        help="冻结配置根（包含 validation/ 的那一层）",
    )
    parser.add_argument("--layers", required=True, help="scorer/layers.yaml 的路径")
    parser.add_argument("--interfaces", required=True, help="scorer/interfaces.yaml 的路径")
    parser.add_argument("--arm", required=True, choices=ARMS, help="实验臂 A / B / C")
    parser.add_argument("--out", required=True, help="run-record JSON 输出路径")
    parser.add_argument(
        "--request-id",
        default=DEFAULT_REQUEST_PREFIX,
        dest="request_prefix",
        help=f"request id 前缀（默认 {DEFAULT_REQUEST_PREFIX}；最终 <前缀>-<arm>-<slug>）",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=positive_int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"单条子进程超时（默认 {DEFAULT_TIMEOUT_SECONDS} 秒）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划命令，不执行、不写 --out")
    return parser


def run(
    argv: list[str] | None = None,
    *,
    runner: Runner | None = None,
    repo_root: Path | None = None,
) -> int:
    """采集一次三维读数；返回进程退出码（0 / 1 / 2）。"""

    args = build_parser().parse_args(argv)
    repo = repo_root if repo_root is not None else _find_repo()
    try:
        inputs = _load_inputs(args, repo)
    except InputError as error:
        print(f"collect: 输入声明不可读：{error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    out = Path(args.out)
    out = (out if out.is_absolute() else Path.cwd() / out).resolve()
    override = os.environ.get("DGATE2_TMPDIR")
    tmp_dir = Path(override).resolve() if override else out.parent / TEMP_SUBDIR
    request_prefix = (
        args.request_prefix or DEFAULT_REQUEST_PREFIX
    ).strip() or DEFAULT_REQUEST_PREFIX

    try:
        commands, _labels = _build_commands(
            inputs, repo=repo, arm=args.arm, request_prefix=request_prefix, tmp_dir=tmp_dir
        )
    except InputError as error:
        print(f"collect: 输入声明不可读：{error}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    if args.dry_run:
        _print_plan(commands)
        return EXIT_OK

    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(
            "collect: 建不了 T 的临时目录 "
            f"{_display_path(tmp_dir, repo)}（{type(error).__name__}）",
            file=sys.stderr,
        )
        return EXIT_UNAVAILABLE

    t_command = commands[0]
    a_command = commands[1]
    c_commands = commands[2:]
    t_dim, t_completed = _collect_t(
        t_command, repo=repo, timeout=args.timeout_seconds, runner=runner
    )
    a_dim, a_completed = _collect_a(
        a_command,
        repo=repo,
        timeout=args.timeout_seconds,
        runner=runner,
        per_predicate=inputs["per_predicate"],
    )
    c_dim, c_results = _collect_c(
        c_commands,
        repo=repo,
        timeout=args.timeout_seconds,
        runner=runner,
        inputs=inputs,
    )

    command_records = [
        _command_record(t_command, t_completed),
        _command_record(a_command, a_completed),
    ]
    command_records.extend(_command_record(command, completed) for command, completed in c_results)
    for name, dimension in (("T", t_dim), ("A", a_dim), ("C", c_dim)):
        _report_unavailable(name, dimension)
    record = _record_payload(
        arm=args.arm,
        inputs=inputs,
        repo=repo,
        t_dim=t_dim,
        a_dim=a_dim,
        c_dim=c_dim,
        command_records=command_records,
    )
    try:
        _write_record(out, record)
    except OSError as error:
        print(f"collect: 写不了 --out（{type(error).__name__}）", file=sys.stderr)
        return EXIT_UNAVAILABLE

    all_recorded = all(
        record["dimensions"][name].get("status") == "recorded" for name in ("T", "C", "A")
    )
    if not all_recorded:
        print(
            "collect: 有维度没采到（status=unavailable）；run-record 已写出，退出码 1",
            file=sys.stderr,
        )
        return EXIT_UNAVAILABLE
    c_score = record["dimensions"]["C"].get("score") or {}
    t_total = record["dimensions"]["T"].get("summary", {}).get("total")
    a_total = len(record["dimensions"]["A"].get("predicates", {}).get("statuses", {}))
    print(
        "collect: T={t}/{tt} C={c}/{cmax}（规则分） A={a}/{at}；run-record 已写出".format(
            t=record["summary"]["t_passed"],
            tt=t_total,
            c=c_score.get("points"),
            cmax=c_score.get("max"),
            a=record["summary"]["a_predicates_passed"],
            at=a_total,
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

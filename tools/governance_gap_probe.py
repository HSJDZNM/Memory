"""治理覆盖缺口探针（V1 独立验收）：13 项缺口的确定性对照。

它只走公开入口，不使用模型、不导入被测实现做判定：

    python -m adapters.dsh.hooks        （PreToolUse / PostToolUse 载荷走 stdin）
    python -m enforcement.cli           （precheck / approve / registry）
    python -m adapters.cli              （wiring / events）
    python -c "from adapters.dsh.adapter import glob_match, TOOL_TABLE"   （静态事实）
    src/adapters/dsh/policy-hook.plugin.mjs                                （插件源码静态事实）
    审计 JSONL / 台账 JSONL 的实际内容

每项缺口同时声明"修前应当看到什么"（before）与"修后应当看到什么"（after），
因此同一份探针可以当对照：

    python tools/governance_gap_probe.py --root .tmp/verifier/baseline --phase before
    python tools/governance_gap_probe.py --root .                     --phase after

任一项与所选阶段的预期不符 -> 退出 1。全部相符 -> 退出 0。
结论只来自被检系统自己写出的产物与进程退出码，不来自对源码的阅读推断。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK = REPO_ROOT / ".tmp" / "verifier" / "probe"
DEFAULT_TIMEOUT = 180

# 本会话（真实 dsh 会话）系统提示里声明的工具清单：这是"运行期真实存在什么"的权威来源。
# 它只用于 G10 的差集报告，不参与任何判定逻辑。
SESSION_TOOLS: tuple[str, ...] = (
    "ask_user_question", "create_goal", "edit", "exit_plan_mode", "get_goal", "glob",
    "grep", "interrupt_agent", "job_kill", "job_list", "job_output", "list_agents",
    "load_workspace_dependencies", "present", "pwsh", "read", "read_image",
    "send_message", "skill", "spawn_teammate", "subagent", "subagent_fork",
    "team_task_create", "team_task_get", "team_task_list", "team_task_update",
    "todo_write", "update_goal", "wait_agent", "web_fetch", "web_search",
)

AGENT_TEAMS_TOOLS: tuple[str, ...] = (
    "spawn_teammate", "team_task_create", "team_task_get", "team_task_list",
    "team_task_update", "wait_agent",
)

# T2 声明的接线状态枚举（见共享任务 task-2）：出现任一个都表示"显式失败状态"。
NOT_WIRED_STATES = frozenset(
    {
        "not_wired", "hooks_config_missing", "hooks_config_unparsable",
        "no_audit_target", "audit_never_written", "stale",
    }
)

PROJECT_FILES: dict[str, str] = {
    "src/inventory_controller.py": (
        "from inventory_service import InventoryService\n"
        "\n"
        "\n"
        "class InventoryController:\n"
        "    def __init__(self) -> None:\n"
        "        self.service = InventoryService()\n"
        "\n"
        "    def list_items(self) -> list[str]:\n"
        "        return self.service.list_items()\n"
    ),
    "src/inventory_service.py": (
        "from repository import Repository\n"
        "\n"
        "\n"
        "class InventoryService:\n"
        "    def __init__(self) -> None:\n"
        "        self.repository = Repository()\n"
        "\n"
        "    def list_items(self) -> list[str]:\n"
        "        return self.repository.all()\n"
    ),
    "src/repository.py": (
        "class Repository:\n"
        "    def all(self) -> list[str]:\n"
        "        return []\n"
    ),
    "src/helpers.py": (
        "def add(left: int, right: int) -> int:\n"
        "    return left + right\n"
    ),
    "tests/test_inventory_controller.py": (
        "from inventory_controller import InventoryController\n"
        "\n"
        "\n"
        "def test_list_items() -> None:\n"
        "    assert InventoryController().list_items() == []\n"
    ),
    "README.md": "# probe project\n",
    "docs/architecture.md": "# architecture\n",
    "AGENTS.md": "# probe project conventions\n",
}

_ADAPTER_TEMPLATE = """# 由 tools/governance_gap_probe.py 生成：受治理探针项目的 dsh Adapter 配置。
agent_version: "probe-0.0.0"
project: probe-project
project_root: ..
rules:
  - {root}/policies
rules_root: {root}
timeout_ms: 5000
layers:
  - pattern: "**/*_controller.py"
    layer: controller
  - pattern: "**/*_service.py"
    layer: service
  - pattern: "**/*.py"
    layer: module
  - pattern: "**/*.md"
    layer: docs
default_layer: {default_layer}
languages:
  - pattern: "**/*.py"
    language: python
default_language: text
audit_log: .policy/audit.jsonl
principal:
  subject: local-user
  roles:
    - developer
registry: {root}/registry/tool-registry.yaml
registry_approved: {root}/registry/tool-registry.approved.json
enforcement_ledger: .policy/enforcement-ledger.jsonl
"""

_HOOKS_TEMPLATE = """{{
  "hooks": {{
    "PreToolUse": [
      {{
        "hooks": [
          {{
            "type": "command",
            "command": "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml --hooks-config .policy/hooks.json --audit .policy/audit.jsonl",
            "timeout": 30
          }}
        ]
      }}
    ]
  }}
}}
"""


@dataclass
class Check:
    """一项缺口的探针结果：观测事实 + 修前/修后预期 + 证据。"""

    id: str
    title: str
    before: dict[str, Any]
    after: dict[str, Any]
    facts: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    error: str = ""

    def expected(self, phase: str) -> dict[str, Any]:
        return self.before if phase == "before" else self.after

    def mismatches(self, phase: str) -> list[str]:
        expected = self.expected(phase)
        out: list[str] = []
        for key, want in expected.items():
            got = self.facts.get(key, "<缺失>")
            if got != want:
                out.append(f"{key}: 期望 {want!r}，实测 {got!r}")
        return out


@dataclass
class Run:
    argv: list[str]
    cwd: str
    exit: int
    stdout: str
    stderr: str

    @property
    def command(self) -> str:
        return " ".join(self.argv)

    def json(self) -> Any:
        text = self.stdout.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 有些 CLI 会在 JSON 之前打印人类可读行；取最后一个能解析的对象。
            for line in reversed(text.splitlines()):
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
            return None


class ProbeStateError(RuntimeError):
    """探针工作目录没有做到"本次运行从零开始"：宁可失败，也不要给出不可复现的结论。"""


class Env:
    """一次探针运行的全部环境：被检根目录、工作目录、受治理探针项目。

    每次运行都有**唯一的工作目录**（<work>/<tag>/run-<run_id>）：审计、台账、captures 与
    受治理探针项目都在里面。这是必需的，不是洁癖——上一次运行的 audit 里已经有同名的
    <session>:<tool_use_id>，复用目录会让本次运行命中幂等台账变成 event_replay：
    "我跑过了"这件事本身会改变下一次的结果，探针就不再是纯函数
    （一个因为错误原因变红的探针，同样可能因为错误原因变绿）。
    """

    def __init__(self, root: Path, work: Path, timeout: int = DEFAULT_TIMEOUT,
                 run_id: Optional[str] = None) -> None:
        self.root = Path(root).resolve()
        self.timeout = timeout
        tag = "live" if self.root == REPO_ROOT.resolve() else self.root.name
        self.base_work = Path(work).resolve() / tag
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        self.run_id = run_id or f"{stamp}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.work = self.base_work / f"run-{self.run_id}"
        self.project = self.work / "project"
        self.policy = self.project / ".policy"
        self.audit_dir = self.work / "audit"
        self.src = self.root / "src"
        self.log: list[str] = []

    # ------------------------------------------------------------------ 基础设施
    def _prune_old_runs(self, keep_seconds: float = 7200.0) -> None:
        """删掉两小时前的历史 run 目录（磁盘卫生）；绝不碰刚创建的、可能正在被并发使用的目录。"""

        cutoff = time.time() - keep_seconds
        for item in sorted(self.base_work.glob("run-*")):
            if item == self.work or not item.is_dir():
                continue
            try:
                if item.stat().st_mtime < cutoff:
                    shutil.rmtree(item, ignore_errors=True)
            except OSError:
                continue

    def setup(self) -> None:
        """把本次运行的目录建造成"保证干净"的状态，并显式验证它是空的。"""

        if self.work.exists():
            shutil.rmtree(self.work)
        self.work.mkdir(parents=True, exist_ok=True)
        leftovers = sorted(str(item.relative_to(self.work)) for item in self.work.rglob("*"))
        if leftovers:
            raise ProbeStateError(
                f"工作目录 {self.work} 不是空的（残留 {leftovers[:5]}）："
                "上一次运行的状态会改变本次结论，拒绝继续"
            )
        self._prune_old_runs()
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        for relative, text in PROJECT_FILES.items():
            target = self.project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        self.policy.mkdir(parents=True, exist_ok=True)
        (self.policy / "dsh-adapter.yaml").write_text(
            _ADAPTER_TEMPLATE.format(root=self.root.as_posix(), default_layer="null"),
            encoding="utf-8", newline="\n",
        )
        (self.policy / "dsh-adapter-default.yaml").write_text(
            _ADAPTER_TEMPLATE.format(root=self.root.as_posix(), default_layer="module"),
            encoding="utf-8", newline="\n",
        )
        (self.policy / "hooks.json").write_text(
            _HOOKS_TEMPLATE.format(), encoding="utf-8", newline="\n"
        )
        (self.work / "dsh-home-empty").mkdir(parents=True, exist_ok=True)

    def run(self, argv: Sequence[str], *, cwd: Path | str | None = None,
            stdin: Optional[str] = None, extra_env: Optional[Mapping[str, str]] = None) -> Run:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.src)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if extra_env:
            env.update({str(k): str(v) for k, v in extra_env.items()})
        argv = [str(item) for item in argv]
        try:
            completed = subprocess.run(
                argv, cwd=str(cwd or self.work), env=env, input=stdin,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=self.timeout,
            )
            run = Run(argv, str(cwd or self.work), completed.returncode,
                      completed.stdout or "", completed.stderr or "")
        except subprocess.TimeoutExpired:
            run = Run(argv, str(cwd or self.work), 124, "", f"timeout after {self.timeout}s")
        except OSError as error:
            run = Run(argv, str(cwd or self.work), 125, "", f"{type(error).__name__}: {error}")
        self.log.append(f"[exit={run.exit}] (cwd={run.cwd}) {run.command}")
        return run

    def py(self, args: Sequence[str], **kwargs: Any) -> Run:
        return self.run([sys.executable, *args], **kwargs)

    def py_json(self, code: str) -> Any:
        """在被检根目录的 PYTHONPATH 下跑一小段代码并解析其 JSON 输出。"""
        return self.py(["-c", code]).json()

    def audit_path(self, name: str) -> Path:
        target = self.audit_dir / f"{name}.jsonl"
        return target

    def hook(self, payload: Mapping[str, Any], *, audit: str,
             config: str = ".policy/dsh-adapter.yaml",
             extra: Sequence[str] = (), hooks_config: Optional[str] = ".policy/hooks.json") -> Run:
        argv = [sys.executable, "-m", "adapters.dsh.hooks", "--config", config,
                "--audit", str(self.audit_path(audit))]
        if hooks_config is not None:
            argv += ["--hooks-config", hooks_config]
        argv += list(extra)
        return self.run(argv, cwd=self.project, stdin=json.dumps(payload, ensure_ascii=False))

    def enforcement(self, args: Sequence[str], *, name: str) -> Run:
        argv = [sys.executable, "-m", "enforcement.cli", *args,
                "--registry", str(self.root / "registry" / "tool-registry.yaml"),
                "--approved", str(self.root / "registry" / "tool-registry.approved.json"),
                "--audit", str(self.audit_dir / f"{name}.audit.jsonl"),
                "--ledger", str(self.audit_dir / f"{name}.ledger.jsonl"),
                "--json"]
        return self.run(argv, cwd=self.work)

    def read_audit(self, name: str) -> list[dict[str, Any]]:
        return _read_jsonl(self.audit_path(name))

    def write_request(self, name: str, document: Mapping[str, Any]) -> Path:
        target = self.work / f"request-{name}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(dict(document), ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")
        return target


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def _payload(tool: str, tool_input: Mapping[str, Any], *, call_id: str,
             event: str = "PreToolUse", project: Path,
             extra: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    document: dict[str, Any] = {
        "session_id": "probe-session",
        "transcript_path": "",
        "cwd": project.as_posix(),
        "hook_event_name": event,
        "tool_name": tool,
        "tool_input": dict(tool_input),
        "tool_use_id": call_id,
    }
    if extra:
        document.update(dict(extra))
    return document


def _decision_of(payload: Any) -> str:
    """从 enforcement.cli --json 的输出里取 pre/final 结论。"""
    if not isinstance(payload, Mapping):
        return "unknown"
    pre = payload.get("pre")
    if isinstance(pre, Mapping):
        decision = pre.get("decision")
        if isinstance(decision, str):
            return decision
    final = payload.get("final")
    if isinstance(final, Mapping) and isinstance(final.get("outcome"), str):
        return "allow" if final["outcome"] == "delivered" else "block"
    return "unknown"


def _reason_of(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return "unknown"
    pre = payload.get("pre")
    if isinstance(pre, Mapping) and isinstance(pre.get("reason_code"), str):
        return str(pre["reason_code"])
    return "unknown"


def _hook_reason(run: Run) -> str:
    match = re.search(r"\(([a-z_]+)\)", run.stderr)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------- G01 / G13

# (module, 子命令之前的全局开关, 子命令与它自己的开关)
# T2 的实现把 --json 同时声明在父解析器与子解析器上，因此两种位置都要试；
# --root 只属于父解析器（必须出现在子命令之前）。
_WIRING_SHAPES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("adapters.cli", ("--json",), ("wiring", "--check")),
    ("adapters.cli", (), ("wiring", "--check", "--json")),
    ("adapters.cli", ("--json",), ("wiring",)),
    ("adapters.cli", (), ("wiring", "--json")),
    ("adapters.wiring", ("--json",), ("--check",)),
    ("adapters.wiring", ("--json",), ()),
)


def _wiring_argv(env: Env, shape: tuple[str, tuple[str, ...], tuple[str, ...]], *,
                 dsh_home: Optional[Path] = None, use_flag: bool = False,
                 extra: Sequence[str] = ()) -> list[str]:
    module, global_flags, sub = shape
    argv = [sys.executable, "-m", module, *global_flags]
    if module == "adapters.cli":
        argv += ["--root", env.root.as_posix()]
    argv += list(sub)
    if dsh_home is not None and use_flag:
        argv += ["--dsh-home", str(dsh_home)]
    argv += list(extra)
    return argv


def _wiring_command(env: Env, *, check: bool, dsh_home: Optional[Path] = None,
                    use_flag: bool = False, extra: Sequence[str] = (),
                    ) -> tuple[Optional[Run], str, Optional[tuple[str, tuple[str, ...], tuple[str, ...]]]]:
    """发现可用的接线清点入口（T2 的 CLI 名字不是冻结接口，因此按候选逐个试）。"""

    for shape in _WIRING_SHAPES:
        if check and "--check" not in shape[2]:
            continue
        if not check and "--check" in shape[2]:
            continue
        argv = _wiring_argv(env, shape, dsh_home=dsh_home, use_flag=use_flag, extra=extra)
        # 没有 --dsh-home 开关时退回环境变量（两条路都试，避免"接口没接上"被误判成缺陷）。
        extra_env = {} if (dsh_home is None or use_flag) else {"DSH_HOME": str(dsh_home)}
        run = env.run(argv, cwd=env.work, extra_env=extra_env)
        if run.exit in (0, 1) and run.json() is not None:
            return run, run.command, shape
    return None, "", None


def _wiring_summary(payload: Any) -> tuple[int, int, list[str]]:
    """返回（通道条目数，显式未接线条目数，命中的状态字符串）。"""

    entries = 0
    unwired = 0
    states: list[str] = []
    identity_keys = {"id", "channel", "name", "agent", "agent_id", "channel_id", "runtime"}
    status_keys = {"status", "state", "wiring", "wired_state", "connection"}
    bool_keys = {"wired", "installed", "registered", "configured", "hook_installed"}

    def walk(node: Any) -> None:
        nonlocal entries, unwired
        if isinstance(node, Mapping):
            keys = {str(key) for key in node}
            has_identity = bool(keys & identity_keys)
            has_status = bool(keys & (status_keys | bool_keys))
            if has_identity and has_status:
                entries += 1
                hit = False
                for key in status_keys & keys:
                    value = node[key]
                    if isinstance(value, str):
                        states.append(value)
                        hit = hit or value in NOT_WIRED_STATES
                    elif isinstance(value, Mapping):
                        for nested in value.values():
                            if isinstance(nested, str):
                                states.append(nested)
                                hit = hit or nested in NOT_WIRED_STATES
                for key in bool_keys & keys:
                    if node[key] is False:
                        hit = True
                if hit:
                    unwired += 1
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(payload)
    return entries, unwired, states


def check_g01(env: Env) -> Check:
    check = Check(
        id="G01",
        title="Agent Teams / 主会话通道没有装检查站：未接线是否成为可发现的显式状态",
        before={"wiring_entrypoint_available": False, "channels_listed": False,
                "unwired_channel_explicit": False},
        after={"wiring_entrypoint_available": True, "channels_listed": True,
               "unwired_channel_explicit": True},
    )
    run, command, _shape = _wiring_command(env, check=False)
    if run is None:
        check.evidence.append("没有可用的接线清点入口（候选：adapters.cli wiring / adapters.wiring）")
        check.facts.update({"wiring_entrypoint_available": False, "channels_listed": False,
                            "unwired_channel_explicit": False, "entrypoint": ""})
        return check

    check.evidence.append(command)
    entries, unwired, states = _wiring_summary(run.json())
    check.facts.update({
        "wiring_entrypoint_available": True,
        "entrypoint": command,
        "channels_listed": entries > 0,
        "channel_entries": entries,
        "unwired_channel_explicit": unwired > 0,
        "unwired_entries": unwired,
        "states_seen": sorted(set(states)),
    })
    return check


def check_g13(env: Env) -> Check:
    check = Check(
        id="G13",
        title="没人能自动发现哪个通道没接线：wiring --check 对未接线/配置读不到必须非 0",
        before={"wiring_entrypoint_available": False, "check_nonzero_without_wiring": False,
                "names_unwired_channel": False, "broken_config_blocks": False,
                "missing_config_blocks": False, "bad_configs_never_ok": False,
                "default_result_matches_wiring_state": False},
        after={"wiring_entrypoint_available": True, "check_nonzero_without_wiring": True,
               "names_unwired_channel": True, "broken_config_blocks": True,
               "missing_config_blocks": True, "bad_configs_never_ok": True,
               "default_result_matches_wiring_state": True},
    )
    run, command, shape = _wiring_command(env, check=True)
    if run is None:
        check.evidence.append("没有可用的 wiring --check 入口")
        check.facts.update({"wiring_entrypoint_available": False,
                            "check_nonzero_without_wiring": False,
                            "names_unwired_channel": False,
                            "broken_config_blocks": False,
                            "missing_config_blocks": False,
                            "bad_configs_never_ok": False,
                            "default_result_matches_wiring_state": False})
        return check
    check.evidence.append(command)
    payload = run.json()
    entries, unwired, states = _wiring_summary(payload)
    check.facts.update({
        "wiring_entrypoint_available": True,
        "entrypoint": command,
        "channels_listed": entries > 0,
        "unwired_entries": unwired,
        "states_seen": sorted(set(states)),
        "check_exit_code": run.exit,
    })

    # 对抗：把 dsh 配置根指到"有配置但读不出 / 指向别处 / 路径不存在"的目录上，
    # --check 必须仍然失败关闭（配置读不到 != 通过）。
    help_run = env.run([sys.executable, "-m", "adapters.cli", "wiring", "--help"], cwd=env.work)
    has_dsh_home = "--dsh-home" in (help_run.stdout + help_run.stderr)
    check.facts["wiring_supports_dsh_home_flag"] = has_dsh_home

    broken_home = env.work / "dsh-home-broken"
    for relative in ("hooks.json", ".dsh/hooks.json", "profiles/default/hooks.json"):
        target = broken_home / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{ not json", encoding="utf-8", newline="\n")
    missing_home = env.work / "dsh-home-missing"  # 故意不创建
    empty_home = env.work / "dsh-home-empty"

    def rerun(home: Path) -> Run:
        if has_dsh_home and shape is not None:
            argv = _wiring_argv(env, shape, dsh_home=home, use_flag=True)
            return env.run(argv, cwd=env.work)
        return env.run(list(run.argv), cwd=env.work, extra_env={"DSH_HOME": str(home)})

    broken_run = rerun(broken_home)
    missing_run = rerun(missing_home)
    empty_again = rerun(empty_home)
    check.facts.update({
        "broken_config_blocks": broken_run.exit != 0,
        "broken_config_exit_code": broken_run.exit,
        "missing_config_blocks": missing_run.exit != 0,
        "missing_config_exit_code": missing_run.exit,
        "check_nonzero_without_wiring": empty_again.exit != 0,
        "empty_dsh_home_exit_code": empty_again.exit,
    })
    check.evidence.append(f"dsh 配置根=<hooks.json 损坏> -> exit={broken_run.exit}")
    check.evidence.append(f"dsh 配置根=<不存在> -> exit={missing_run.exit}")
    check.evidence.append(f"dsh 配置根=<空目录> -> exit={empty_again.exit}")
    # "指名道姓说哪个通道没接"：默认运行或空配置根运行任一能报出显式未接线状态即可。
    named_text = ((run.stdout + run.stderr) if isinstance(payload, Mapping) else "") + \
        empty_again.stdout + empty_again.stderr
    check.facts["names_unwired_channel"] = bool(
        re.search(r"(not_wired|hooks_config_missing|hooks_config_unparsable|"
                  r"no_audit_target|audit_never_written|stale)", named_text)
    )

    # 三种终态分开断言：ok / fail / skipped（skipped 必须显式，且绝不能等于 ok）。
    def state_of(run_payload: Any) -> tuple[Any, Any]:
        if not isinstance(run_payload, Mapping):
            return None, None
        return run_payload.get("result"), run_payload.get("skip_reason")

    default_result, default_skip = state_of(payload)
    broken_result, broken_skip = state_of(broken_run.json())
    missing_result, missing_skip = state_of(missing_run.json())
    empty_result, empty_skip = state_of(empty_again.json())
    bad = {
        "broken": (broken_result, broken_skip),
        "missing": (missing_result, missing_skip),
        "empty": (empty_result, empty_skip),
    }
    check.facts.update({
        "default_result": default_result,
        "default_skip_reason": default_skip,
        "bad_config_results": {key: item[0] for key, item in bad.items()},
        "bad_config_skip_reasons": {key: item[1] for key, item in bad.items()},
    })
    check.facts["bad_configs_never_ok"] = all(
        item[0] not in (None, "ok") and (item[0] != "skipped" or bool(item[1]))
        for item in bad.values()
    )
    unwired_now = check.facts.get("unwired_entries", 0)
    check.facts["default_result_matches_wiring_state"] = (
        (default_result == "fail") if isinstance(unwired_now, int) and unwired_now > 0
        else (default_result in {"ok", "skipped"})
    )
    check.evidence.append(
        f"result 终态：默认={default_result!r}（未接线通道 {unwired_now}）"
        f"，损坏={broken_result!r}，不存在={missing_result!r}，空目录={empty_result!r}"
    )

    # 工具漂移（G10 的支撑证据）：接线报告里应能看出"运行期观察到的工具 vs 工具表"。
    check.facts["wiring_top_level_keys"] = sorted(payload) if isinstance(payload, Mapping) else []
    return check


# ---------------------------------------------------------------------------- G02
def _plugin_source(root: Path) -> str:
    path = root / "src" / "adapters" / "dsh" / "policy-hook.plugin.mjs"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _hook_names(text: str) -> list[str]:
    return sorted(set(re.findall(r"tools/([a-z][a-z0-9-]*)", text)))


_PLUGIN_HARNESS = r'''
// 用假 ctx 跑真实的插件模块：验证它到底注册了哪些钩子、以及 post 钩子是否真的转发。
import { pathToFileURL } from 'node:url';

const pluginPath = process.argv[2];
const mode = process.argv[3] || 'exit2';
const command = process.argv[4] || 'python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml';

const mod = await import(pathToFileURL(pluginPath).href);
const apply = mod.apply || mod.default;
const handlers = {};
const sent = [];
const ctx = {
  on(name, fn) { (handlers[name] = handlers[name] || []).push(fn); },
  shell: {
    resolve(request) { return request; },
    async run(request) {
      sent.push({ stdin: request.stdin, workdir: request.workdir, command: request.command });
      if (mode === 'exit2') return { exitCode: 2, stderr: { text: 'blocked by policy' } };
      if (mode === 'exit1') return { exitCode: 1, stderr: { text: 'hook crashed' } };
      return { exitCode: 0, stderr: { text: '' } };
    },
  },
};
const out = { apply_found: typeof apply === 'function', registered: [] };
if (out.apply_found) {
  apply(ctx, { command, timeoutMs: 30000, projectDir: process.cwd() });
  out.registered = Object.keys(handlers);
}
const pre = (handlers['tools/pre-execute'] || [])[0];
out.pre_registered = typeof pre === 'function';
out.pre_arity = typeof pre === 'function' ? pre.length : null;
const post = (handlers['tools/post-execute'] || [])[0];
out.post_registered = typeof post === 'function';
out.post_arity = typeof post === 'function' ? post.length : null;
out.post_source_head = typeof post === 'function' ? String(post).slice(0, 200) : null;
if (out.post_registered) {
  let nextCalled = 0;
  const exec = {
    name: 'edit',
    callId: 'probe-call-1',
    arguments: { file_path: 'src/inventory_controller.py', old_string: 'a', new_string: 'b' },
    agent: { session: { header: { id: 'probe-session', cwd: process.cwd() } } },
    result: { ok: true },
    response: { ok: true },
  };
  const decision = await post(exec, () => { nextCalled += 1; return 'next'; });
  out.decision = decision === undefined ? null : decision;
  out.next_called = nextCalled;
  out.stdin = sent.length ? String(sent[0].stdin ?? '') : '';
}
console.log(JSON.stringify(out));
'''


def _node_path() -> Optional[str]:
    found = shutil.which("node")
    return found


# dsh 实现包（第三方）里的静态事实：事件名与回调形参个数。
# 它只用于把"对 dsh 运行期签名的假设"降级为"已核对实现里的字符串事实"。
DSH_IMPL_ASAR = Path(
    "C:/Users/ZNM/AppData/Local/Programs/DeepSeek Harness/resources/app.asar"
)


def _dsh_impl_signature(asar: Path) -> dict[str, Any]:
    """在 dsh 实现包里做二进制字符串检索：tools/post-execute 是否存在、回调是否三参。"""

    found: dict[str, Any] = {
        "present": False,
        "arity_three": False,
        "pre_present": False,
        "sample": "",
    }
    if not asar.is_file():
        return found
    needle = b"tools/post-execute"
    pre_needle = b"tools/pre-execute"
    pattern = re.compile(
        rb"tools/post-execute[\"']\s*,\s*(?:async\s*)?(?:function\s*)?\(?\s*"
        rb"[A-Za-z_$][\w$]*\s*,\s*[A-Za-z_$][\w$]*\s*,\s*[A-Za-z_$][\w$]*"
    )
    carry = b""
    with asar.open("rb") as handle:
        while True:
            block = handle.read(8 * 1024 * 1024)
            if not block:
                break
            data = carry + block
            if pre_needle in data:
                found["pre_present"] = True
            start = 0
            while True:
                index = data.find(needle, start)
                if index < 0:
                    break
                found["present"] = True
                window = data[max(0, index - 200): index + 800]
                if pattern.search(window):
                    found["arity_three"] = True
                    if not found["sample"]:
                        found["sample"] = window.decode("utf-8", "replace")
                start = index + 1
            carry = data[-512:]
    return found


def check_g02(env: Env) -> Check:
    check = Check(
        id="G02",
        title="动手前拦了、动手后没核对：post 钩子是否注册并真的转发，post 记录是否落账",
        before={"plugin_registers_post_execute": False, "plugin_post_forwards": False,
                "plugin_post_payload_recorded": False, "python_side_post_stage_recorded": True},
        after={"plugin_registers_post_execute": True, "plugin_post_forwards": True,
               "plugin_post_payload_recorded": True, "python_side_post_stage_recorded": True,
               "plugin_post_event_name": "tools/post-execute", "plugin_post_arity": 3,
               "g02_pre_decision_allowed": True},
    )
    source = _plugin_source(env.root)
    hooks = _hook_names(source)
    check.facts["plugin_hooks_registered"] = hooks
    check.facts["plugin_registers_post_execute"] = "post-execute" in hooks
    check.evidence.append(
        f"src/adapters/dsh/policy-hook.plugin.mjs 源码里的 tools/* 钩子：{hooks or '读取失败'}"
    )

    # (1) 用真插件模块 + 假 ctx 跑一遍转发逻辑（不依赖 dsh 运行时，也不依赖实现者的测试）。
    harness = env.work / "plugin-harness.mjs"
    harness.write_text(_PLUGIN_HARNESS, encoding="utf-8", newline="\n")
    node = _node_path()
    check.facts["node_available"] = node is not None
    if node is None:
        check.facts.update({"plugin_post_forwards": False, "plugin_post_payload_recorded": False})
        check.evidence.append("本机没有 node：插件转发逻辑无法执行（静态事实仍记录）")
    else:
        plugin = env.root / "src" / "adapters" / "dsh" / "policy-hook.plugin.mjs"
        deny = env.run([node, str(harness), str(plugin), "exit2"],
                       cwd=env.project, extra_env={"NODE_NO_WARNINGS": "1"})
        payload = deny.json()
        check.evidence.append(f"{deny.command} -> exit={deny.exit}")
        if not isinstance(payload, Mapping):
            check.facts.update({"plugin_post_forwards": False,
                                "plugin_post_payload_recorded": False})
            check.evidence.append(f"harness 输出无法解析：{deny.stdout[:200]} {deny.stderr[:200]}")
        else:
            registered = list(payload.get("registered") or [])
            check.facts["harness_registered"] = registered
            decision = payload.get("decision")
            # 阻断形状按 dsh 的 post 钩子 API：{kind:'block', feedback:[...]}；
            # pre 钩子用 {kind:'deny', reason}。两者都算"exit 2 被翻译成阻断结论"，
            # 关键是不能退化成 next()（放行）。
            kind = decision.get("kind") if isinstance(decision, Mapping) else None
            forwarded = (
                bool(payload.get("post_registered"))
                and bool(payload.get("stdin"))
                and kind in {"deny", "block"}
            )
            check.facts["plugin_post_forwards"] = forwarded
            check.facts["plugin_post_decision_kind"] = kind
            check.facts["plugin_post_decision"] = json.dumps(decision, ensure_ascii=False)
            check.facts["plugin_post_arity"] = payload.get("post_arity")
            check.facts["plugin_pre_arity"] = payload.get("pre_arity")
            check.facts["plugin_post_source_head"] = payload.get("post_source_head")
            check.facts["plugin_post_event_name"] = (
                "tools/post-execute" if "tools/post-execute" in registered else None
            )
            check.facts["plugin_post_next_called"] = payload.get("next_called")
            stdin = str(payload.get("stdin") or "")
            post_payload: Any = None
            try:
                post_payload = json.loads(stdin) if stdin.strip() else None
            except json.JSONDecodeError:
                post_payload = None
            check.facts["plugin_post_payload_event"] = (
                post_payload.get("hook_event_name") if isinstance(post_payload, Mapping) else None
            )
            check.facts["plugin_post_payload_has_tool_response"] = bool(
                isinstance(post_payload, Mapping) and "tool_response" in post_payload
            )
            check.evidence.append(
                f"假 ctx：注册 {registered}；post 转发 decision={decision}；"
                f"转发载荷事件={check.facts['plugin_post_payload_event']}，"
                f"含 tool_response={check.facts['plugin_post_payload_has_tool_response']}"
            )
            # (2) 把插件真正交给 Hook 的载荷喂给真 Hook 进程：post 记录必须落进审计。
            if isinstance(post_payload, Mapping):
                fed = env.hook(post_payload, audit="g02-plugin")
                records = env.read_audit("g02-plugin")
                recorded = any(
                    str(item.get("stage", "")).startswith("post") for item in records
                )
                check.facts["plugin_post_payload_recorded"] = recorded
                check.evidence.append(
                    f"把插件载荷喂给 python -m adapters.dsh.hooks -> exit={fed.exit}；"
                    f"审计 stages={[str(item.get('stage', '')) for item in records]}"
                )
            else:
                check.facts["plugin_post_payload_recorded"] = False

    # (3) 对照：Python 侧本来就实现了 post 链路（缺的只是那一行注册）。真的改完文件再核对。
    target = env.project / "src" / "inventory_controller.py"
    old = "        return self.service.list_items()\n"
    new = "        return self.service.list_items()  # post probe\n"
    call_id = "probe-g02-1"
    pre = env.hook(
        _payload("edit", {"file_path": "src/inventory_controller.py", "old_string": old,
                          "new_string": new, "replace_all": False},
                 call_id=call_id, project=env.project),
        audit="g02",
    )
    check.evidence.append(f"{pre.command}  (stdin=PreToolUse edit) -> exit={pre.exit}")
    if pre.exit != 0:
        check.facts["python_side_post_stage_recorded"] = False
        check.facts["pre_exit"] = pre.exit
        check.facts["pre_stderr"] = pre.stderr.strip()[:300]
        return check
    # 模拟 Agent 运行时真的执行了这次编辑（dsh 才会发 PostToolUse）。
    target.write_text(target.read_text(encoding="utf-8").replace(old, new, 1),
                      encoding="utf-8", newline="\n")
    post = env.hook(
        _payload("edit", {"file_path": "src/inventory_controller.py", "old_string": old,
                          "new_string": new, "replace_all": False},
                 call_id=call_id, project=env.project, event="PostToolUse",
                 extra={"tool_response": {"ok": True}}),
        audit="g02",
    )
    check.evidence.append(f"{post.command}  (stdin=PostToolUse edit) -> exit={post.exit}")
    records = env.read_audit("g02")
    stages = [str(item.get("stage", "")) for item in records]
    post_records = [item for item in records if str(item.get("stage", "")).startswith("post")]
    check.facts.update({
        "pre_exit": pre.exit,
        "post_exit": post.exit,
        "post_reason": _hook_reason(post),
        "audit_stages": stages,
        "python_side_post_stage_recorded": bool(post_records),
        "post_status": (post_records[-1].get("payload", {}) or {}).get("status")
        if post_records else None,
    })

    # 第三层（静态）：与 dsh 实现包里的字符串事实比对事件名与回调形参个数。
    # 这条断言只在实现包存在时进入"修后预期"（否则它在别的机器上会变成环境失败）。
    impl = _dsh_impl_signature(DSH_IMPL_ASAR)
    check.facts["dsh_impl_asar"] = str(DSH_IMPL_ASAR)
    check.facts["dsh_impl_asar_exists"] = DSH_IMPL_ASAR.is_file()
    check.facts["dsh_impl_post_event_present"] = impl["present"]
    check.facts["dsh_impl_post_arity_three"] = impl["arity_three"]
    if impl["sample"]:
        check.facts["dsh_impl_sample"] = " ".join(impl["sample"].split())[:220]
    check.evidence.append(
        f"dsh 实现包静态检索：tools/post-execute 存在={impl['present']}，"
        f"三参回调形态={impl['arity_three']}，tools/pre-execute 存在={impl['pre_present']}"
    )
    if DSH_IMPL_ASAR.is_file():
        check.after["dsh_impl_post_event_present"] = True
        check.after["dsh_impl_post_arity_three"] = True

    # 关键："被 pre 拒绝的调用也会走 post"，所以只有 pre 放行的动作才有信息量。
    allowed_records = [
        item for item in records
        if item.get("decision") == "allow" and str(item.get("stage", "")) == ""
    ]
    check.facts["g02_pre_decision_allowed"] = pre.exit == 0 and bool(allowed_records)
    check.evidence.append(
        f"本次 post 链路的 pre 结论：exit={pre.exit}，审计里 allow 记录={len(allowed_records)} 条"
        "（被阻断的调用同样会触发 post，因此只有放行的动作才算证据）"
    )
    return check


# ---------------------------------------------------------------------------- G03
def check_g03(env: Env) -> Check:
    check = Check(
        id="G03",
        title="跳过与通过在账本上长得一样：受治理动作的审计能否区分两者",
        before={"skipped_visible": False},
        after={"skipped_visible": True, "skipped_count_positive": True},
    )
    run = env.hook(
        _payload("edit", {"file_path": "src/helpers.py",
                          "old_string": "    return left + right\n",
                          "new_string": "    return left + right  # coverage probe\n",
                          "replace_all": False},
                 call_id="probe-g03-1", project=env.project),
        audit="g03",
    )
    check.evidence.append(f"{run.command}  (stdin=PreToolUse edit) -> exit={run.exit}")
    records = [item for item in env.read_audit("g03") if "decision" in item]
    if not records:
        check.facts.update({"skipped_visible": False, "skipped_rule_count": None,
                            "audit_keys": [], "exit": run.exit})
        check.evidence.append(f"stderr: {run.stderr.strip()[:300]}")
        return check
    record = records[-1]
    keys = sorted(record)
    effective = record.get("effective_rule_count")
    skipped = record.get("skipped_rule_count")
    reason = record.get("skipped_reason")
    # 接受两种口径：(a) 显式计数+归类原因字段；(b) skipped_rules 元素是带 reason 的对象。
    detail_style = bool(record.get("skipped_rules")) and all(
        isinstance(item, Mapping) for item in record.get("skipped_rules", [])
    )
    visible = (
        isinstance(effective, int)
        and isinstance(skipped, int)
        and reason is not None
        and reason != ""
        and reason != {}
        and reason != []
    ) or detail_style
    check.facts.update({
        "skipped_visible": bool(visible),
        "effective_rule_count": effective,
        "skipped_rule_count": skipped,
        "skipped_reason_present": reason is not None,
        "skipped_count_positive": bool(isinstance(skipped, int) and skipped > 0),
        "matched_rules": record.get("matched_rules"),
        "audit_keys": keys,
    })
    return check


# ---------------------------------------------------------------------------- G04
def _pwsh_request(env: Env, *, name: str, action_id: str, command: str) -> Path:
    return env.write_request(name, {
        "action_id": action_id,
        "request_id": action_id,
        "trace_id": "probe-trace",
        "agent": "dsh",
        "tool_id": "exec.pwsh",
        "subject": "local-user",
        "roles": ["owner"],
        "params": {"command": command, "description": "probe"},
    })


def _approve_flags(env: Env) -> set[str]:
    run = env.py(["-m", "enforcement.cli", "approve", "--help"])
    return set(re.findall(r"(--[a-z][a-z0-9-]*)", run.stdout + run.stderr))


def _pattern_approval_attempts(flags: set[str],
                              value: str = ".*pytest.*") -> list[list[str]]:
    """按 approve --help 里真实存在的开关拼出"模式化审批"的候选命令（不猜接口）。

    value 是 --param-pattern 里 command 的整串正则（调用方按被测命令给）。
    """

    attempts: list[list[str]] = []
    max_use_flag = next((item for item in ("--max-uses", "--max-calls", "--uses")
                         if item in flags), None)
    mode_flag = next((item for item in ("--binding", "--mode", "--approval-mode", "--scope")
                      if item in flags), None)
    pattern_flag = next((item for item in ("--param-pattern", "--pattern")
                         if item in flags), None)
    base_extra = [max_use_flag, "5"] if max_use_flag else []
    if mode_flag and pattern_flag:
        attempts.append([mode_flag, "pattern", pattern_flag, f"command={value}", *base_extra])
    if mode_flag:
        attempts.append([mode_flag, "pattern", *base_extra])
    if pattern_flag:
        attempts.append([pattern_flag, f"command={value}", *base_extra])
    if "--approve-pattern" in flags:
        attempts.append(["--approve-pattern", *base_extra])
    return attempts


def check_g04(env: Env) -> Check:
    check = Check(
        id="G04",
        title="命令类工具结构性不可用：审批能否按工具+参数模式+时效+次数上限签发",
        before={"pattern_mode_supported": False, "no_approval_decision": "block",
                "same_action_decision": "allow", "different_action_id_decision": "block",
                "different_command_decision": "block", "replay_second_decision": "block",
                "replay_fresh_approval_blocked_as_replay": True},
        after={"pattern_mode_supported": True, "no_approval_decision": "block",
               "same_action_decision": "allow", "different_action_id_decision": "allow",
               "different_command_decision": "block", "subject_swap_decision": "block",
               "expired_decision": "block", "replay_second_decision": "block",
               "replay_fresh_approval_blocked_as_replay": True, "max_uses_enforced": True},
    )
    command_ok = "python -m pytest tests -q"
    # 与 command_ok 必须在任何合理模式下都可区分（不是同一族命令）。
    command_bad = "python -m unittest discover -s tests -q"

    req1 = _pwsh_request(env, name="g04-1", action_id="probe-g04-1", command=command_ok)
    req2 = _pwsh_request(env, name="g04-2", action_id="probe-g04-2", command=command_ok)
    req3 = _pwsh_request(env, name="g04-3", action_id="probe-g04-3", command=command_bad)

    no_approval = env.enforcement(["precheck", "--request", str(req1), "--workspace",
                                   str(env.project)], name="g04-no-approval")
    check.evidence.append(f"{no_approval.command} -> exit={no_approval.exit} "
                          f"reason={_reason_of(no_approval.json())}")
    check.facts["no_approval_decision"] = _decision_of(no_approval.json())
    check.facts["no_approval_reason"] = _reason_of(no_approval.json())

    flags = _approve_flags(env)
    check.facts["approve_flags"] = sorted(flags)
    attempts = _pattern_approval_attempts(flags)
    pattern_supported = False
    approval_path = env.work / "approval-g04-pattern.json"
    used_attempt: list[str] = []
    for extra in attempts:
        run = env.enforcement(["approve", "--request", str(req1), "--out", str(approval_path),
                               "--granted-by", "alice", "--roles", "reviewer",
                               "--workspace", str(env.project), *extra],
                              name="g04-approve-pattern")
        if run.exit == 0:
            pattern_supported = True
            used_attempt = extra
            check.evidence.append(f"{run.command} -> exit=0（模式化审批可用）")
            break
    check.facts["pattern_mode_supported"] = pattern_supported
    check.facts["pattern_approval_flags"] = used_attempt

    if not pattern_supported:
        single = env.work / "approval-g04-single.json"
        run = env.enforcement(["approve", "--request", str(req1), "--out", str(single),
                               "--granted-by", "alice", "--roles", "reviewer",
                               "--workspace", str(env.project)],
                              name="g04-approve-single")
        check.evidence.append(f"{run.command} -> exit={run.exit}")
        approval_path = single

    same = env.enforcement(["precheck", "--request", str(req1), "--approval", str(approval_path),
                            "--workspace", str(env.project)], name="g04-same")
    check.facts["same_action_decision"] = _decision_of(same.json())
    check.facts["same_action_reason"] = _reason_of(same.json())
    check.evidence.append(f"{same.command} -> exit={same.exit} reason={_reason_of(same.json())}")

    other = env.enforcement(["precheck", "--request", str(req2), "--approval", str(approval_path),
                             "--workspace", str(env.project)], name="g04-other-id")
    check.facts["different_action_id_decision"] = _decision_of(other.json())
    check.facts["different_action_id_reason"] = _reason_of(other.json())
    check.evidence.append(f"{other.command} -> exit={other.exit} "
                          f"reason={_reason_of(other.json())}")

    bad = env.enforcement(["precheck", "--request", str(req3), "--approval", str(approval_path),
                           "--workspace", str(env.project)], name="g04-other-command")
    check.facts["different_command_decision"] = _decision_of(bad.json())
    check.facts["different_command_reason"] = _reason_of(bad.json())
    check.evidence.append(f"{bad.command} -> exit={bad.exit} reason={_reason_of(bad.json())}")

    if pattern_supported:
        # 跨主体盗用：换主体必须失效。
        stolen = env.write_request("g04-steal", {
            "action_id": "probe-g04-steal", "request_id": "probe-g04-steal",
            "agent": "dsh", "tool_id": "exec.pwsh", "subject": "other-user",
            "roles": ["owner"],
            "params": {"command": command_ok, "description": "probe"},
        })
        # 审批与请求主体不一致时，approve 也要按同一主体签发才公平：这里直接盗用 alice 签的条子。
        steal = env.enforcement(["precheck", "--request", str(stolen), "--approval",
                                 str(approval_path), "--workspace", str(env.project)],
                                name="g04-steal")
        check.facts["subject_swap_decision"] = _decision_of(steal.json())
        check.facts["subject_swap_reason"] = _reason_of(steal.json())
        check.evidence.append(f"{steal.command} -> exit={steal.exit} "
                              f"reason={_reason_of(steal.json())}")

        # 过期：ttl=1，等 2 秒。
        expired_path = env.work / "approval-g04-expired.json"
        run = env.enforcement(["approve", "--request", str(req1), "--out", str(expired_path),
                               "--granted-by", "alice", "--roles", "reviewer",
                               "--workspace", str(env.project),
                               "--ttl", "1", *used_attempt], name="g04-approve-expired")
        check.evidence.append(f"{run.command} -> exit={run.exit}")
        import time as _time
        _time.sleep(2.0)
        expired = env.enforcement(["precheck", "--request", str(req2), "--approval",
                                   str(expired_path), "--workspace", str(env.project)],
                                  name="g04-expired")
        check.facts["expired_decision"] = _decision_of(expired.json())
        check.facts["expired_reason"] = _reason_of(expired.json())
        check.evidence.append(f"{expired.command} -> exit={expired.exit} "
                              f"reason={_reason_of(expired.json())}")
    else:
        check.facts["subject_swap_decision"] = None
        check.facts["expired_decision"] = None

    # 重放：同一 action_id 第二次绝不执行（任何档位都不许削弱）。
    # 这条只能走 execute 才可观察：precheck 是 dry-run，不占用幂等键。
    replay_command = "Write-Output probe-g04"
    replay_req = _pwsh_request(env, name="g04-replay", action_id="probe-g04-replay",
                               command=replay_command)
    replay_approval = env.work / "approval-g04-replay.json"

    def sign_replay(target: Path, approval_name: str) -> bool:
        """给 replay_req 签一张审批：模式化审批要覆盖它自己的命令（整串匹配）。"""

        candidates = _pattern_approval_attempts(flags, ".*") if pattern_supported else [[]]
        for extra in candidates:
            trial = env.enforcement(["approve", "--request", str(replay_req), "--out",
                                     str(target), "--granted-by", "alice",
                                     "--roles", "reviewer", "--workspace", str(env.project),
                                     *extra], name=approval_name)
            check.evidence.append(f"{trial.command} -> exit={trial.exit}")
            if trial.exit == 0:
                return True
        return False

    check.facts["replay_approval_signed"] = sign_replay(replay_approval, "g04-approve-replay")
    first = env.enforcement(["execute", "--request", str(replay_req), "--approval",
                             str(replay_approval), "--workspace", str(env.project)],
                            name="g04-replay")
    first_payload = first.json()
    execution = first_payload.get("execution") if isinstance(first_payload, Mapping) else None
    check.facts["replay_first_executed"] = bool(
        isinstance(execution, Mapping) and execution.get("status") == "executed"
    )
    check.facts["replay_first_exit"] = first.exit
    check.facts["platform_driver_available"] = shutil.which("pwsh") is not None
    check.evidence.append(f"{first.command} -> exit={first.exit} "
                          f"execution={None if not isinstance(execution, Mapping) else execution.get('status')}"
                          f"（本机 pwsh 是否在 PATH：{check.facts['platform_driver_available']}）")
    replay = env.enforcement(["execute", "--request", str(replay_req), "--approval",
                              str(replay_approval), "--workspace", str(env.project)],
                             name="g04-replay")
    check.facts["replay_second_decision"] = _decision_of(replay.json())
    check.facts["replay_second_reason"] = _reason_of(replay.json())
    check.evidence.append(f"{replay.command} -> exit={replay.exit} "
                          f"reason={_reason_of(replay.json())}")

    # 把"重放拦截"与"审批被消费"分开：换一张全新审批、同一个 action_id，必须仍然 action_replay。
    fresh_approval = env.work / "approval-g04-replay-fresh.json"
    check.facts["replay_fresh_approval_signed"] = sign_replay(
        fresh_approval, "g04-approve-replay-fresh"
    )
    fresh = env.enforcement(["execute", "--request", str(replay_req), "--approval",
                             str(fresh_approval), "--workspace", str(env.project)],
                            name="g04-replay")
    check.facts["replay_fresh_approval_reason"] = _reason_of(fresh.json())
    check.facts["replay_fresh_approval_blocked_as_replay"] = (
        _reason_of(fresh.json()) == "action_replay"
    )
    check.evidence.append(f"{fresh.command} -> exit={fresh.exit} "
                          f"reason={_reason_of(fresh.json())}（全新审批 + 同一 action_id）")

    if pattern_supported:
        max_use_flag = next((item for item in ("--max-uses", "--max-calls", "--uses")
                             if item in flags), None)
        if max_use_flag is None:
            check.facts["max_uses_enforced"] = None
            check.evidence.append("模式化审批没有次数上限开关：无法验证上限")
        else:
            limited = env.work / "approval-g04-limited.json"
            # 这次被测命令是 Write-Output probe-g04，参数模式必须覆盖它（整串匹配）。
            limit_attempt: list[str] = []
            for extra in _pattern_approval_attempts(flags, ".*"):
                # 去掉候选里自带的次数上限，只留本次要测的 --max-uses 1。
                trimmed = list(extra)
                if max_use_flag in trimmed:
                    index = trimmed.index(max_use_flag)
                    trimmed = trimmed[:index] + trimmed[index + 2:]
                trial = env.enforcement(["approve", "--request", str(replay_req), "--out",
                                         str(limited), "--granted-by", "alice",
                                         "--roles", "reviewer", "--workspace", str(env.project),
                                         *trimmed, max_use_flag, "1"], name="g04-approve-limited")
                check.evidence.append(f"{trial.command} -> exit={trial.exit}")
                if trial.exit == 0:
                    limit_attempt = trimmed
                    break
            other_req = _pwsh_request(env, name="g04-limited-2",
                                      action_id="probe-g04-limited-2", command=replay_command)
            one = env.enforcement(["execute", "--request", str(replay_req), "--approval",
                                   str(limited), "--workspace", str(env.project)],
                                  name="g04-limited")
            two = env.enforcement(["execute", "--request", str(other_req), "--approval",
                                   str(limited), "--workspace", str(env.project)],
                                  name="g04-limited")
            check.facts["max_uses_approval_flags"] = [*limit_attempt, max_use_flag, "1"]
            check.facts["max_uses_enforced"] = (
                _decision_of(one.json()) == "allow" and _decision_of(two.json()) == "block"
            )
            check.facts["max_uses_second_reason"] = _reason_of(two.json())
            check.evidence.append(f"{one.command} -> exit={one.exit} "
                                  f"decision={_decision_of(one.json())} "
                                  f"reason={_reason_of(one.json())}")
            check.evidence.append(f"{two.command} -> exit={two.exit} "
                                  f"decision={_decision_of(two.json())} "
                                  f"reason={_reason_of(two.json())}")
    else:
        check.facts["max_uses_enforced"] = None
    return check


# ---------------------------------------------------------------------------- G05
def _workdir_hook(env: Env, *, name: str, workdir: str, tool: str = "pwsh") -> Run:
    return env.hook(
        _payload(tool, {"command": "python -m pytest tests -q", "description": "probe",
                        "workdir": workdir},
                 call_id=f"probe-g05-{name}", project=env.project),
        audit=f"g05-{name}",
    )


# 反向断言：底层异常**没有**结构化 reason_code 时，上层必须退回笼统值，而不是编一个具体的码。
# 这条只用公开导出的 DshPreExecuteHook.handle()（模块 __all__ 里有它）+ 注入一个抛裸异常的桥。
_FALLBACK_CODE = r'''
import json
from pathlib import Path

from adapters.dsh.adapter import load_config
from adapters.dsh.hooks import DshPreExecuteHook
from policy.loader import load_rule_set

config = load_config(Path(".policy/dsh-adapter.yaml"))
rules = load_rule_set(config.rule_dirs, repo_root=config.rule_anchor)


class BareErrorBridge:
    """build_request 抛一个没有 reason_code 的异常：这正是兜底分支要处理的情况。"""

    def spec_for(self, tool):
        return object()

    def build_request(self, **kwargs):
        raise RuntimeError("probe: 这个异常没有结构化 reason_code")


hook = DshPreExecuteHook(config=config, rules=rules, bridge=BareErrorBridge())
outcome = hook.handle(
    {
        "session_id": "probe-fallback",
        "transcript_path": "",
        "cwd": str(Path.cwd()),
        "hook_event_name": "PreToolUse",
        "tool_name": "pwsh",
        "tool_input": {"command": "python -m pytest tests -q", "description": "probe"},
        "tool_use_id": "probe-fallback-1",
    }
)
print(json.dumps({"reason_code": outcome.reason_code, "exit_code": outcome.exit_code}))
'''


def check_g05(env: Env) -> Check:
    check = Check(
        id="G05",
        title="工作目录等于项目根被判越界：范围口径是否统一，越界是否仍然拒绝",
        before={"abs_root_reason": "enforcement_param_error",
                "dot_reason": "enforcement_param_error",
                "dot_slash_reason": "enforcement_param_error",
                "abs_root_param_error": True, "dot_param_error": True,
                "dot_slash_param_error": True, "subdir_reason": "permission_denied",
                "subdir_param_error": False,
                "outside_reason": "enforcement_param_error",
                "dotdot_reason": "enforcement_param_error",
                "outside_still_rejected": True, "file_param_dot_blocked": True,
                "fallback_reason_without_structured_code": "enforcement_param_error"},
        # 修后：合法工作区根不再报参数错误，问题自然落到下一道闸（本探针主体的 developer
        # 没有 shell.exec）——"范围没问题"与"范围越界"必须是两个不同的码，不能都写成
        # param_error，也不能把合法路径硬说成 path_out_of_scope。
        after={"abs_root_reason": "permission_denied",
               "dot_reason": "permission_denied",
               "dot_slash_reason": "permission_denied",
               "abs_root_param_error": False, "dot_param_error": False,
               "dot_slash_param_error": False, "subdir_reason": "permission_denied",
               "subdir_param_error": False,
               "outside_reason": "path_out_of_scope",
               "dotdot_reason": "path_out_of_scope",
               "outside_still_rejected": True, "file_param_dot_blocked": True,
               "fallback_reason_without_structured_code": "enforcement_param_error"},
    )
    cases = {
        "abs_root": env.project.as_posix(),
        "dot": ".",
        "dot_slash": "./",
        "subdir": "src",
        "outside": env.work.as_posix(),
        "dotdot": "../",
    }
    reasons: dict[str, str] = {}
    for name, workdir in cases.items():
        run = _workdir_hook(env, name=name, workdir=workdir)
        reason = _hook_reason(run)
        reasons[name] = reason
        check.facts[f"{name}_reason"] = reason
        check.evidence.append(f"workdir={workdir!r} -> exit={run.exit} reason={reason}")
        if name in {"abs_root", "dot", "dot_slash", "subdir"}:
            check.facts[f"{name}_param_error"] = reason in {"enforcement_param_error"}
    check.facts["reasons"] = reasons
    outside_run = _workdir_hook(env, name="outside", workdir=env.work.as_posix())
    check.facts["outside_detail_snippet"] = " ".join(outside_run.stderr.split())[:300]
    check.facts["outside_still_rejected"] = all(
        reasons.get(name, "") not in {"", "allow", "allow_delegated"} for name in ("outside", "dotdot")
    ) and all(
        ("out_of_scope" in reasons.get(name, "") or "param_error" in reasons.get(name, ""))
        for name in ("outside", "dotdot")
    )

    # 反向断言：拿不到结构化 reason_code 时必须退回笼统值。
    fallback = env.py(["-c", _FALLBACK_CODE], cwd=env.project)
    payload = fallback.json()
    check.facts["fallback_probe_ok"] = isinstance(payload, Mapping)
    check.facts["fallback_reason_without_structured_code"] = (
        payload.get("reason_code") if isinstance(payload, Mapping) else None
    )
    check.facts["fallback_exit_code"] = payload.get("exit_code") if isinstance(payload, Mapping) else None
    check.evidence.append(
        f"注入一个没有 reason_code 的桥异常 -> reason={check.facts['fallback_reason_without_structured_code']} "
        f"exit={check.facts['fallback_exit_code']}"
    )
    if not check.facts["fallback_probe_ok"]:
        check.facts["fallback_stderr"] = " ".join(fallback.stderr.split())[:300]
        check.evidence.append(f"兜底探针本身失败：{check.facts['fallback_stderr']}")

    # 文件参数传 "." 必须被拒（它不是文件）。
    file_run = env.hook(
        _payload("edit", {"file_path": ".", "old_string": "x", "new_string": "y",
                          "replace_all": False},
                 call_id="probe-g05-file-dot", project=env.project),
        audit="g05-file-dot",
    )
    check.evidence.append(f"edit file_path='.' -> exit={file_run.exit} reason={_hook_reason(file_run)}")
    check.facts["file_param_dot_blocked"] = file_run.exit != 0
    check.facts["file_param_dot_reason"] = _hook_reason(file_run)
    return check


# ---------------------------------------------------------------------------- G06
_G06_CASES: dict[str, str] = {
    "literal_from": "from repository import Repository\n",
    "plain_import": "import repository\n",
    "importlib_module": 'import importlib\n\nrepository = importlib.import_module("repository")\n',
    "dunder_import": 'repository = __import__("repository")\n',
    "relative_import": "from . import repository\n",
    "relative_named": "from .repository import Repository\n",
    "submodule_import": "from shop.repository import Repository\n",
    "dotted_import": "import shop.repository\n",
    "alias_case": "from REPOSITORY import Repository\n",
}

_G06_CONTROLS: dict[str, tuple[str, str]] = {
    # 名称 -> (文件, 变更文本)；必须保持放行，用来发现"过度阻断"。
    "controller_service_allowed": ("src/inventory_controller.py",
                                   "from inventory_service import InventoryService\n"),
    "module_layer_allowed": ("src/helpers.py", "from repository import Repository\n"),
}


def check_g06(env: Env) -> Check:
    bypass = ("importlib_module", "dunder_import", "relative_import", "relative_named",
              "submodule_import", "dotted_import")
    before = {name: "blocked" for name in ("literal_from", "plain_import", "alias_case")}
    before.update({name: "allowed" for name in bypass})
    before.update({name: "allowed" for name in _G06_CONTROLS})
    after = {name: "blocked" for name in _G06_CASES}
    after.update({name: "allowed" for name in _G06_CONTROLS})
    check = Check(
        id="G06",
        title="依赖规则只认行首字面写法：换写法是否仍然放行",
        before=before, after=after,
    )
    for name, text in _G06_CASES.items():
        run = env.hook(
            _payload("edit", {"file_path": "src/inventory_controller.py",
                              "old_string": "from inventory_service import InventoryService\n",
                              "new_string": text, "replace_all": False},
                     call_id=f"probe-g06-{name}", project=env.project),
            audit=f"g06-{name}",
        )
        check.facts[name] = "allowed" if run.exit == 0 else "blocked"
        check.facts[f"{name}_reason"] = _hook_reason(run)
        check.evidence.append(f"{name}: new_string={text.strip()!r} -> exit={run.exit} "
                              f"reason={_hook_reason(run)}")
    for name, (path, text) in _G06_CONTROLS.items():
        run = env.hook(
            _payload("edit", {"file_path": path,
                              "old_string": "from inventory_service import InventoryService\n",
                              "new_string": text, "replace_all": False},
                     call_id=f"probe-g06-{name}", project=env.project),
            audit=f"g06-{name}",
        )
        check.facts[name] = "allowed" if run.exit == 0 else "blocked"
        check.facts[f"{name}_reason"] = _hook_reason(run)
        check.evidence.append(f"[对照] {name}: {path} <- {text.strip()!r} -> exit={run.exit} "
                              f"reason={_hook_reason(run)}")
    check.facts["bypass_now_blocked"] = sorted(
        name for name in bypass if check.facts.get(name) == "blocked"
    )
    return check


# ---------------------------------------------------------------------------- G07
# 冻结接口（00-remediation-plan.md 第 2 节 #1）：
#   AdapterConfig.layer_resolution(repo_path) -> LayerResolution(layer, matched_pattern, defaulted)
# 探针分两半取证：(a) 接口本身是否可用且结论正确；(b) 审计里是否真的写进去了。
_G07_INTERFACE_CODE = r'''
import json
from pathlib import Path

from adapters.dsh.adapter import load_config

config = load_config(Path(".policy/dsh-adapter.yaml"))
defaults = load_config(Path(".policy/dsh-adapter-default.yaml"))
out = {"has_layer_resolution": hasattr(config, "layer_resolution")}
if out["has_layer_resolution"]:
    matched = config.layer_resolution("src/inventory_controller.py")
    plain = config.layer_resolution("src/helpers.py")
    fallback = defaults.layer_resolution("notes.txt")
    out["matched"] = {
        "layer": matched.layer,
        "pattern": matched.matched_pattern,
        "defaulted": matched.defaulted,
    }
    out["plain"] = {
        "layer": plain.layer,
        "pattern": plain.matched_pattern,
        "defaulted": plain.defaulted,
    }
    out["fallback"] = {
        "layer": fallback.layer,
        "pattern": fallback.matched_pattern,
        "defaulted": fallback.defaulted,
    }
    out["layer_for_backward_compatible"] = config.layer_for("src/inventory_controller.py") == matched.layer
print(json.dumps(out))
'''


def check_g07(env: Env) -> Check:
    check = Check(
        id="G07",
        title="分层靠文件名，失效是静默的：审计里能否看出「未命中任何分层规则」",
        before={"layer_resolution_available": False, "layer_fields_present": False},
        after={"layer_resolution_available": True, "matched_resolution_correct": True,
               "plain_resolution_correct": True, "fallback_resolution_correct": True,
               "layer_for_backward_compatible": True,
               "layer_fields_present": True, "matched_has_pattern": True,
               "defaulted_is_marked": True},
    )
    matched = env.hook(
        _payload("edit", {"file_path": "src/inventory_controller.py",
                          "old_string": "from inventory_service import InventoryService\n",
                          "new_string": "from inventory_service import InventoryService  # layer\n",
                          "replace_all": False},
                 call_id="probe-g07-matched", project=env.project),
        audit="g07-matched",
    )
    defaulted = env.hook(
        _payload("write", {"file_path": "notes.txt", "content": "hello\n"},
                 call_id="probe-g07-defaulted", project=env.project),
        audit="g07-defaulted", config=".policy/dsh-adapter-default.yaml",
    )
    check.evidence.append(f"{matched.command} (controller) -> exit={matched.exit}")
    check.evidence.append(f"{defaulted.command} (notes.txt, default_layer=module) -> "
                          f"exit={defaulted.exit} reason={_hook_reason(defaulted)}")

    # (a) 冻结接口本身。
    interface = env.py(["-c", _G07_INTERFACE_CODE], cwd=env.project)
    data = interface.json()
    check.facts["layer_resolution_available"] = bool(
        isinstance(data, Mapping) and data.get("has_layer_resolution")
    )
    check.facts["layer_resolution"] = data
    if isinstance(data, Mapping) and data.get("has_layer_resolution"):
        matched = data.get("matched") or {}
        plain = data.get("plain") or {}
        fallback = data.get("fallback") or {}
        check.facts["matched_resolution_correct"] = (
            matched.get("layer") == "controller"
            and matched.get("pattern") == "**/*_controller.py"
            and matched.get("defaulted") is False
        )
        check.facts["plain_resolution_correct"] = (
            plain.get("layer") == "module"
            and plain.get("pattern") == "**/*.py"
            and plain.get("defaulted") is False
        )
        check.facts["fallback_resolution_correct"] = (
            fallback.get("layer") == "module"
            and fallback.get("pattern") is None
            and fallback.get("defaulted") is True
        )
        check.facts["layer_for_backward_compatible"] = bool(data.get("layer_for_backward_compatible"))
        check.evidence.append(f"layer_resolution 接口：{json.dumps(data, ensure_ascii=False)}")
    else:
        check.facts["matched_resolution_correct"] = False
        check.facts["plain_resolution_correct"] = False
        check.facts["fallback_resolution_correct"] = False
        check.facts["layer_for_backward_compatible"] = False
        check.evidence.append(
            f"被检实现没有 layer_resolution()：{' '.join(interface.stderr.split())[:200]}"
        )

    # (b) 审计里是否真的写进去（这才是"失效不再静默"的验收点）。
    def record_for(name: str) -> dict[str, Any]:
        records = [item for item in env.read_audit(name) if "layer" in item]
        return records[-1] if records else {}

    first = record_for("g07-matched")
    second = record_for("g07-defaulted")
    keys = sorted(set(first) | set(second))
    check.facts.update({
        "audit_keys": keys,
        "layer_fields_present": "layer_defaulted" in keys and "layer_matched_pattern" in keys,
        "matched_layer": first.get("layer"),
        "matched_pattern": first.get("layer_matched_pattern"),
        "matched_defaulted": first.get("layer_defaulted"),
        "default_layer": second.get("layer"),
        "default_pattern": second.get("layer_matched_pattern"),
        "default_defaulted": second.get("layer_defaulted"),
    })
    check.facts["matched_has_pattern"] = (
        first.get("layer_defaulted") is False and first.get("layer_matched_pattern") == "**/*_controller.py"
    )
    check.facts["defaulted_is_marked"] = (
        second.get("layer_defaulted") is True and second.get("layer_matched_pattern") is None
    )
    return check


# ---------------------------------------------------------------------------- G08
# (pattern, path, 修前预期, 修后预期)；修前 = "**/" 要求至少一层目录。
_G08_CASES: tuple[tuple[str, str, bool, bool], ...] = (
    ("**/*.md", "README.md", False, True),
    ("**/*.py", "cli.py", False, True),
    ("**/*.py", "src/cli.py", True, True),
    ("src/**/*.py", "src/a.py", False, True),
    ("src/**/*.py", "src/pkg/a.py", True, True),
    ("src/**/*.py", "other/src/a.py", False, False),
    ("**/*.md", "docs/a/b.md", True, True),
    ("**/*.py", "a.pyc", False, False),
    ("**/*.md", "a.md.bak", False, False),
    ("**", "README.md", True, True),
)


def check_g08(env: Env) -> Check:
    cases = [[pattern, path] for pattern, path, _before, _after in _G08_CASES]
    code = (
        "import json\n"
        "from adapters.dsh.adapter import glob_match\n"
        f"cases = json.loads({json.dumps(json.dumps(cases))})\n"
        "print(json.dumps({p + '|' + t: bool(glob_match(p, t)) for p, t in cases}, "
        "ensure_ascii=False))\n"
    )
    check = Check(
        id="G08",
        title="**/ 匹配不到根目录文件：通配符语义是否与「零层目录」一致且不误伤",
        before={f"{pattern}|{path}": expected_before
                for pattern, path, expected_before, _expected_after in _G08_CASES},
        after={f"{pattern}|{path}": expected_after
               for pattern, path, _expected_before, expected_after in _G08_CASES},
    )
    observed = env.py_json(code)
    if not isinstance(observed, Mapping):
        check.facts["glob_probe_ok"] = False
        check.evidence.append("无法在被检根目录上导入 adapters.dsh.adapter.glob_match")
        return check
    check.facts.update({str(key): bool(value) for key, value in observed.items()})
    check.facts["glob_probe_ok"] = True
    for pattern, path, _expected_before, _expected_after in _G08_CASES:
        key = f"{pattern}|{path}"
        check.evidence.append(f"glob_match({pattern!r}, {path!r}) = {check.facts.get(key)}")

    # 放大核对：既有 layer/language pattern 在新语义下新增命中哪些路径。
    try:
        import yaml  # noqa: PLC0415 - 探针自身依赖，与被检实现无关

        document = yaml.safe_load(
            (env.root / "adapters" / "dsh" / "adapter.yaml").read_text(encoding="utf-8")
        )
        patterns = [str(row["pattern"]) for row in (document.get("layers") or [])]
        patterns += [str(row["pattern"]) for row in (document.get("languages") or [])]
    except Exception as error:  # noqa: BLE001 - 读不到就如实记录
        patterns = []
        check.evidence.append(f"读取 adapters/dsh/adapter.yaml 失败：{error}")
    candidates = ["README.md", "AGENTS.md", "pyproject.toml", "pytest.ini", "requirements.in",
                  "src/cli.py", "src/pkg/a.py", "docs/a/b.md", "tests/test_x.py"]
    pairs = [[pattern, path] for pattern in patterns for path in candidates]
    if pairs:
        code2 = (
            "import json\n"
            "from adapters.dsh.adapter import glob_match\n"
            f"pairs = json.loads({json.dumps(json.dumps(pairs))})\n"
            "print(json.dumps([p + '|' + t for p, t in pairs if glob_match(p, t)], "
            "ensure_ascii=False))\n"
        )
        matched = env.py_json(code2)
        check.facts["amplified_matches"] = sorted(matched) if isinstance(matched, list) else []
        check.evidence.append(f"adapter.yaml 现有 pattern 的命中集合（{len(check.facts['amplified_matches'])} 项）")
    return check


# ---------------------------------------------------------------------------- G09
_DANGEROUS_CODE = (
    "import os\n"
    "import subprocess\n"
    "os.system('echo pwned')\n"
    "subprocess.run(['cmd', '/c', 'whoami'])\n"
    "open('probe.txt', 'w', encoding='utf-8').write('x')\n"
)


def check_g09(env: Env) -> Check:
    check = Check(
        id="G09",
        title="「跑代码」工具没有第二道闸：危险代码是否在审批之外另有结构性检查",
        before={"dangerous_code_allowed_with_approval": True,
                "structural_gate_declared": False},
        after={"dangerous_code_allowed_with_approval": False,
               "structural_gate_declared": True},
    )
    try:
        import yaml  # noqa: PLC0415

        document = yaml.safe_load(
            (env.root / "registry" / "tool-registry.yaml").read_text(encoding="utf-8")
        )
        spec = next((item for item in document.get("tools", [])
                     if item.get("id") == "exec.run_code"), None)
    except Exception as error:  # noqa: BLE001
        spec = None
        check.evidence.append(f"读取 registry/tool-registry.yaml 失败：{error}")
    if spec is None:
        check.facts["registry_entry"] = None
        check.evidence.append("注册表里没有 exec.run_code")
        return check
    keys = sorted(spec)
    check.facts["run_code_keys"] = keys
    check.facts["run_code_driver"] = spec.get("driver")
    check.facts["run_code_post_checks"] = list(spec.get("post_checks") or [])
    check.facts["run_code_allowed_commands"] = list(spec.get("allowed_commands") or [])
    check.facts["run_code_extra_gate_fields"] = sorted(
        key for key in keys
        if key in {"code_checks", "code_check", "forbidden_code_fragments",
                   "forbidden_code_imports", "code_policy", "governable", "governance_level",
                   "ungovernable", "degraded", "structural_checks"}
    )
    check.facts["structural_gate_declared"] = bool(
        check.facts["run_code_extra_gate_fields"] or check.facts["run_code_post_checks"]
        or check.facts["run_code_allowed_commands"]
    )
    check.evidence.append(f"exec.run_code 声明字段：{keys}")

    request = env.write_request("g09", {
        "action_id": "probe-g09-1", "request_id": "probe-g09-1", "agent": "dsh",
        "tool_id": "exec.run_code", "subject": "local-user", "roles": ["owner"],
        "params": {"code": _DANGEROUS_CODE, "description": "probe"},
    })
    approval = env.work / "approval-g09.json"
    signed = env.enforcement(["approve", "--request", str(request), "--out", str(approval),
                              "--granted-by", "alice", "--roles", "reviewer",
                              "--workspace", str(env.project)],
                             name="g09-approve")
    check.evidence.append(f"{signed.command} -> exit={signed.exit}")
    if signed.exit != 0:
        check.facts["approval_issued"] = False
        check.evidence.append(f"approve stderr: {signed.stderr.strip()[:300]}")
        return check
    check.facts["approval_issued"] = True
    run = env.enforcement(["precheck", "--request", str(request), "--approval", str(approval),
                           "--workspace", str(env.project)], name="g09-precheck")
    check.facts["dangerous_code_allowed_with_approval"] = _decision_of(run.json()) == "allow"
    check.facts["dangerous_code_decision"] = _decision_of(run.json())
    check.facts["dangerous_code_reason"] = _reason_of(run.json())
    check.evidence.append(f"{run.command} -> exit={run.exit} decision={_decision_of(run.json())} "
                          f"reason={_reason_of(run.json())}")
    check.facts["structural_gate_fired"] = _reason_of(run.json()) not in {
        "allow", "approval_required", "approval_invalid", "permission_denied"}
    return check


# ---------------------------------------------------------------------------- G10
def check_g10(env: Env) -> Check:
    check = Check(
        id="G10",
        title="工具白名单跟不上工具升级：工具表、manifest 与本会话真实工具的差集",
        before={"table_has_agent_teams_tools": False},
        after={"table_has_agent_teams_tools": True, "table_matches_manifest": True,
               "session_tools_missing": [], "adapter_approved_and_consistent": True},
    )
    code = (
        "import json\n"
        "from adapters.dsh.adapter import TOOL_TABLE\n"
        "print(json.dumps({name: spec.kind.value for name, spec in TOOL_TABLE.items()}, "
        "sort_keys=True))\n"
    )
    table = env.py_json(code)
    if not isinstance(table, Mapping):
        check.facts["tool_table_readable"] = False
        check.evidence.append("无法读取 TOOL_TABLE")
        return check
    check.facts["tool_table_readable"] = True
    check.facts["tool_count"] = len(table)
    missing_teams = sorted(name for name in AGENT_TEAMS_TOOLS if name not in table)
    check.facts["table_has_agent_teams_tools"] = not missing_teams
    check.facts["agent_teams_tools_missing"] = missing_teams
    check.facts["spawn_teammate_kind"] = table.get("spawn_teammate")
    check.facts["session_tools_missing"] = sorted(
        name for name in SESSION_TOOLS if name not in table
    )
    check.evidence.append(f"TOOL_TABLE 有 {len(table)} 项；缺的 Agent Teams 工具：{missing_teams}")
    check.evidence.append(f"本会话工具表未收录：{check.facts['session_tools_missing']}")

    try:
        import yaml  # noqa: PLC0415

        manifest = yaml.safe_load(
            (env.root / "adapters" / "dsh" / "manifest.yaml").read_text(encoding="utf-8")
        )
        manifest_names = sorted(str(row["name"]) for row in (manifest.get("tools") or []))
    except Exception as error:  # noqa: BLE001
        manifest_names = []
        check.evidence.append(f"读取 adapters/dsh/manifest.yaml 失败：{error}")
    check.facts["manifest_tool_count"] = len(manifest_names)
    check.facts["table_minus_manifest"] = sorted(set(table) - set(manifest_names))
    check.facts["manifest_minus_table"] = sorted(set(manifest_names) - set(table))
    check.facts["table_matches_manifest"] = (
        not check.facts["table_minus_manifest"] and not check.facts["manifest_minus_table"]
    )
    events = env.py(["-m", "adapters.cli", "--json", "--root", str(env.root), "events"])
    check.facts["adapter_events_exit"] = events.exit
    check.facts["adapter_approved_and_consistent"] = events.exit == 0
    check.evidence.append(f"{events.command} -> exit={events.exit}")
    if events.exit != 0:
        check.evidence.append(f"stderr: {events.stderr.strip()[:300]}")
    return check


# ---------------------------------------------------------------------------- G11
def check_g11(env: Env) -> Check:
    check = Check(
        id="G11",
        title="注入内容零留痕：进入 AI 上下文的项目约定文档是否有来源与哈希记录",
        before={"injection_trace_present": False},
        after={"injection_trace_present": True},
    )
    run = env.hook(
        _payload("edit", {"file_path": "src/helpers.py",
                          "old_string": "    return left + right\n",
                          "new_string": "    return left + right  # injection probe\n",
                          "replace_all": False},
                 call_id="probe-g11-1", project=env.project),
        audit="g11",
    )
    check.evidence.append(f"{run.command} (stdin=PreToolUse edit) -> exit={run.exit}")
    records = env.read_audit("g11")
    markers: list[str] = []
    for record in records:
        text = json.dumps(record, ensure_ascii=False)
        if ("AGENTS.md" in text or "CLAUDE.md" in text) and re.search(r"[0-9a-f]{16,}", text):
            markers.append(str(record.get("stage") or record.get("reason_code") or "record"))
    check.facts["injection_trace_in_audit"] = bool(markers)
    check.facts["injection_markers"] = sorted(set(markers))
    check.facts["audit_record_keys"] = sorted({key for record in records for key in record})
    check.evidence.append(f"审计记录 {len(records)} 条；命中注入留痕的记录：{check.facts['injection_markers']}")

    # 另一条可能的落点：接线自检（T1 被要求"找不到注入事件来源时在接线自检记录一次"）。
    self_check = env.py(["-m", "adapters.dsh.hooks", "--config", ".policy/dsh-adapter.yaml",
                         "--hooks-config", ".policy/hooks.json", "--self-check"], cwd=env.project)
    blob = self_check.stdout + self_check.stderr
    self_check_hit = ("AGENTS.md" in blob or "CLAUDE.md" in blob) and bool(
        re.search(r"[0-9a-f]{16,}", blob)
    )
    check.facts["injection_trace_in_selfcheck"] = self_check_hit
    check.facts["injection_trace_present"] = bool(markers) or self_check_hit
    check.evidence.append(f"{self_check.command} -> exit={self_check.exit}；"
                          f"输出里含注入留痕：{self_check_hit}")
    grep = env.py(["-c", (
        "import json, pathlib, re\n"
        f"root = pathlib.Path({str(env.root)!r})\n"
        "hits = []\n"
        "for path in list((root/'src').rglob('*.py')) + list((root/'src').rglob('*.mjs')):\n"
        "    text = path.read_text(encoding='utf-8', errors='replace')\n"
        "    if 'injection' in text or '注入' in text:\n"
        "        hits.append(path.relative_to(root).as_posix())\n"
        "print(json.dumps(sorted(hits), ensure_ascii=False))\n"
    )])
    check.facts["source_files_mentioning_injection"] = grep.json() or []
    check.evidence.append(f"src/ 下提到 injection/注入 的文件：{check.facts['source_files_mentioning_injection']}")
    return check


# ---------------------------------------------------------------------------- G12
_LIB_WIRING_CODE = r'''
import json
from pathlib import Path

from adapters.dsh.hooks import run_hook

outcome = run_hook(
    {{
        "session_id": "probe-lib",
        "transcript_path": "",
        "cwd": str(Path.cwd()),
        "hook_event_name": "PreToolUse",
        "tool_name": "edit",
        "tool_input": {{
            "file_path": "src/helpers.py",
            "old_string": "def add(left: int, right: int) -> int:",
            "new_string": "def add(left: int, right: int) -> int:  # library wiring probe",
            "replace_all": False,
        }},
        "tool_use_id": "{tool_use_id}",
    }},
    config_path=".policy/dsh-adapter.yaml",
    audit_path=str(Path(".policy") / "{audit}"),
    {wiring_kwarg}
)
print(json.dumps({{"exit_code": outcome.exit_code, "reason_code": outcome.reason_code}}))
'''


def check_g12(env: Env) -> Check:
    check = Check(
        id="G12",
        title="「故障即拦住」只在自建插件里：插件契约与接线自检缺席是否失败关闭",
        before={"plugin_denies_unknown_exit": True, "selfcheck_without_hooks_config_blocks": False,
                "library_strict_refuses_unverified_wiring": False},
        after={"plugin_denies_unknown_exit": True, "selfcheck_without_hooks_config_blocks": True,
               "selfcheck_broken_hooks_blocks": True, "missing_config_blocks": True,
               "library_strict_refuses_unverified_wiring": True},
    )
    source = _plugin_source(env.root)
    denies_unknown = bool(
        re.search(r"exitCode\s*!==\s*0", source) or re.search(r"exit\s*!==\s*0", source)
    ) and "deny" in source
    check.facts["plugin_denies_unknown_exit"] = denies_unknown
    check.evidence.append(f"插件源码把「非 0 非 2」映射成 deny：{denies_unknown}")

    absent = env.py(["-m", "adapters.dsh.hooks", "--config", ".policy/dsh-adapter.yaml",
                     "--self-check"], cwd=env.project)
    check.facts["selfcheck_without_hooks_config_exit"] = absent.exit
    check.facts["selfcheck_without_hooks_config_blocks"] = absent.exit != 0
    check.evidence.append(f"{absent.command} -> exit={absent.exit}")

    broken = env.policy / "hooks-broken.json"
    broken.write_text("{ not json", encoding="utf-8", newline="\n")
    broken_run = env.py(["-m", "adapters.dsh.hooks", "--config", ".policy/dsh-adapter.yaml",
                         "--hooks-config", ".policy/hooks-broken.json", "--self-check"],
                        cwd=env.project)
    check.facts["selfcheck_broken_hooks_exit"] = broken_run.exit
    check.facts["selfcheck_broken_hooks_blocks"] = broken_run.exit != 0
    check.evidence.append(f"{broken_run.command} -> exit={broken_run.exit}")

    missing = env.py(["-m", "adapters.dsh.hooks", "--config", ".policy/no-such-config.yaml",
                      "--self-check"], cwd=env.project)
    check.facts["missing_config_exit"] = missing.exit
    check.facts["missing_config_blocks"] = missing.exit != 0
    check.evidence.append(f"{missing.command} -> exit={missing.exit}")

    keyboard = env.py(["-m", "adapters.dsh.hooks", "--config", ".policy/dsh-adapter.yaml",
                       "--hooks-config", ".policy/hooks.json"], cwd=env.project,
                      stdin="{ not json")
    check.facts["bad_payload_exit"] = keyboard.exit
    check.facts["bad_payload_blocks"] = keyboard.exit == 2
    check.evidence.append(f"{keyboard.command} (stdin=损坏 JSON) -> exit={keyboard.exit}")

    # 库内默认（N5）：run_hook 的 allow_unverified_wiring 默认值是 True，
    # 也就是"库内调用缺席即放行"；只有显式 False 才失败关闭。CLI 传的是 False。
    # "default" 这一档**不传**该参数，测的就是库内默认值本身。
    for label, expect_refusal in (("default", False), ("strict", True)):
        code = _LIB_WIRING_CODE.format(
            tool_use_id=f"probe-lib-{label}",
            audit=f"audit-lib-{label}.jsonl",
            wiring_kwarg="" if not expect_refusal else "allow_unverified_wiring=False,",
        )
        run = env.py(["-c", code], cwd=env.project)
        payload_data = run.json()
        fact = (
            "library_strict_refuses_unverified_wiring" if expect_refusal
            else "library_default_allows_unverified_wiring"
        )
        if isinstance(payload_data, Mapping):
            blocked = payload_data.get("exit_code") != 0
            check.facts[fact] = blocked if expect_refusal else not blocked
        else:
            check.facts[fact] = False
        check.facts[f"library_{label}_outcome"] = payload_data
        check.evidence.append(
            f"库内调用 hooks.run_hook(hooks_config_path=None{'' if not expect_refusal else ', allow_unverified_wiring=False'})"
            f" -> {payload_data}"
        )
        if not isinstance(payload_data, Mapping):
            check.evidence.append(f"库内探针 stderr：{run.stderr.strip()[:200]}")
    return check


CHECKS: tuple[Callable[[Env], Check], ...] = (
    check_g01, check_g02, check_g03, check_g04, check_g05, check_g06, check_g07,
    check_g08, check_g09, check_g10, check_g11, check_g12, check_g13,
)


def _render(report: Mapping[str, Any]) -> str:
    lines = [
        f"被检根目录: {report['root']}",
        f"阶段: {report['phase']}   run_id: {report.get('run_id')}   工作目录: {report['work']}",
        "",
    ]
    for item in report["checks"]:
        mark = "OK  " if item["ok"] else "FAIL"
        lines.append(f"[{mark}] {item['id']} {item['title']}")
        if item["error"]:
            lines.append(f"        探针自身异常: {item['error']}")
        for line in item["mismatches"]:
            lines.append(f"        不一致: {line}")
        lines.append(f"        实测: {json.dumps(item['facts'], ensure_ascii=False, sort_keys=True)}")
    failed = [item["id"] for item in report["checks"] if not item["ok"]]
    lines.append("")
    lines.append(f"结论: {len(report['checks']) - len(failed)}/{len(report['checks'])} 与"
                 f"「{report['phase']}」预期一致")
    if failed:
        lines.append(f"与预期不符: {', '.join(failed)}")
    if report.get("unexpected_event_replay"):
        lines.append(f"跨运行状态残留: {report['unexpected_event_replay']}")
    return "\n".join(lines)


def _run_once(root: Path, phase: str, work: Path, *, only: Sequence[str],
              timeout: int) -> dict[str, Any]:
    """跑一遍全部（或指定）缺口：每次都用全新的工作目录，因此调用之间没有共享状态。"""

    env = Env(root, work, timeout=timeout)
    env.setup()
    checks: list[dict[str, Any]] = []
    wanted = {item.upper() for item in only}
    for factory in CHECKS:
        probe = Check(id="", title="", before={}, after={})
        try:
            probe = factory(env)
        except Exception as error:  # noqa: BLE001 - 探针自身故障也必须写进报告
            probe = Check(id=getattr(factory, "__name__", "?"), title="探针异常",
                          before={}, after={}, error=f"{type(error).__name__}: {error}")
        if wanted and probe.id.upper() not in wanted:
            continue
        mismatches = probe.mismatches(phase)
        checks.append({
            "id": probe.id,
            "title": probe.title,
            "before": probe.before,
            "after": probe.after,
            "facts": probe.facts,
            "evidence": probe.evidence,
            "error": probe.error,
            "mismatches": mismatches,
            "ok": not mismatches and not probe.error,
        })
    # 跨运行状态残留的结构性守卫：本次运行里出现 event_replay 就说明有东西被复用了
    # （唯一允许的重放拦截是 G04 显式构造的 action_replay，那是被测行为，不是残留）。
    replay_hits: list[str] = []
    for path in sorted(env.audit_dir.rglob("*.jsonl")):
        for record in _read_jsonl(path):
            if record.get("reason_code") == "event_replay":
                replay_hits.append(f"{path.name}:{record.get('event_id')}")
    return {
        "probe": "tools/governance_gap_probe.py",
        "root": str(env.root),
        "phase": phase,
        "run_id": env.run_id,
        "work": str(env.work),
        "commands": env.log,
        "checks": checks,
        "unexpected_event_replay": sorted(set(replay_hits)),
        "ok": bool(checks) and all(item["ok"] for item in checks) and not replay_hits,
    }


def _fingerprint(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """两次运行的可比指纹：逐项结论 + facts + 不一致清单（不含路径、run_id 等易变字段）。"""

    return [
        {
            "id": item["id"],
            "ok": item["ok"],
            "mismatches": item["mismatches"],
            "facts": item["facts"],
        }
        for item in report["checks"]
    ]


def compare_runs(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """连续多次运行的逐项结论与 facts 必须完全一致，否则探针不是纯函数。"""

    if len(runs) < 2:
        return {"runs": [str(item.get("run_id")) for item in runs], "consistent": True,
                "differences": []}
    baseline = _fingerprint(runs[0])
    differences: list[str] = []
    for index, other in enumerate(runs[1:], start=1):
        current = _fingerprint(other)
        if len(current) != len(baseline):
            differences.append(
                f"run#{index} 的缺口数量 {len(current)} != run#0 的 {len(baseline)}"
            )
            continue
        for left, right in zip(baseline, current):
            if left != right:
                keys = sorted(set(left) | set(right))
                detail = [
                    f"{key}: {json.dumps(left.get(key), ensure_ascii=False, sort_keys=True)[:200]}"
                    f" != {json.dumps(right.get(key), ensure_ascii=False, sort_keys=True)[:200]}"
                    for key in keys
                    if left.get(key) != right.get(key)
                ]
                differences.append(f"{left['id']} 在 run#0 与 run#{index} 之间不同：" + "；".join(detail))
    return {
        "runs": [str(item.get("run_id")) for item in runs],
        "consistent": not differences,
        "differences": differences,
    }


def build_report(root: Path, phase: str, work: Path, *, only: Sequence[str] = (),
                 timeout: int = DEFAULT_TIMEOUT, repeat: int = 1) -> dict[str, Any]:
    """跑 repeat 遍（每遍都是全新工作目录），并把"多遍是否完全一致"作为探针自身的断言。"""

    runs = [
        _run_once(root, phase, work, only=only, timeout=timeout)
        for _ in range(max(1, repeat))
    ]
    report = runs[0]
    if len(runs) > 1:
        comparison = compare_runs(runs)
        report["repeat"] = len(runs)
        report["run_ids"] = comparison["runs"]
        report["repeat_consistent"] = comparison["consistent"]
        report["repeat_differences"] = comparison["differences"]
        report["ok"] = bool(report["ok"] and comparison["consistent"])
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python tools/governance_gap_probe.py",
        description="13 项治理覆盖缺口的确定性探针（修前 / 修后对照，退出码 0 = 与预期一致）",
    )
    parser.add_argument("--root", default=str(REPO_ROOT),
                        help="被检根目录（默认当前仓库；baseline 传 .tmp/verifier/baseline）")
    parser.add_argument("--phase", choices=("before", "after"), default="after",
                        help="对照阶段：before=修前预期，after=修后预期")
    parser.add_argument("--work", default=str(DEFAULT_WORK), help="探针工作目录")
    parser.add_argument("--only", action="append", default=[],
                        help="只跑指定缺口（可重复，例如 --only G02）")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单条命令超时（秒）")
    parser.add_argument("--json-out", default=None, help="把完整报告写到该路径")
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="连续跑 N 遍（每遍全新工作目录）并断言逐项结论与 facts 完全一致："
             "验证探针是纯函数（默认 1）",
    )
    parser.add_argument("--quiet", action="store_true", help="只输出结论行")
    args = parser.parse_args(argv)

    if args.root:
        os.environ["PYTHONIOENCODING"] = "utf-8"
    report = build_report(Path(args.root), args.phase, Path(args.work),
                          only=args.only, timeout=args.timeout, repeat=args.repeat)
    if args.json_out:
        target = Path(args.json_out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8", newline="\n")
    if args.quiet:
        print(f"{report['root']} [{report['phase']}] ok={report['ok']}")
    else:
        print(_render(report))
    if args.repeat > 1:
        status = "一致" if report.get("repeat_consistent") else "不一致"
        print(f"重复运行 {report['repeat']} 遍：结论与 facts {status}"
              f"（run_id: {', '.join(report.get('run_ids', []))}）")
        for line in report.get("repeat_differences", []):
            print(f"  差异: {line}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

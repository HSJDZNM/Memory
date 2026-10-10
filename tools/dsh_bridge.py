"""把策略桥挂到本机 dsh 的某个 profile 上——并把「挂上了」变成一条会失败的检查。

为什么需要它（G1 / 04-open-work §9 那一行）：python -m adapters.cli wiring 能**发现**
dsh:desktop = not_wired，但仓库里没有任何入口能把它**装上去**——接线只能照
examples/dsh/profile-patch.yml 手工贴。手工贴的两种失效都不会自己报出来：

* dsh 读不到 / 读不懂 hooks 配置时**不注册任何 hook 也不报错**，Agent 照常启动
  （src/adapters/dsh/README.md §2.5），于是「没接线」看起来和「没违规」一模一样；
* 贴对了但受治项目后来被删掉，只剩一个挂着的桥。2026-09-26 留下的四个 governed*
  profile 就是这一种：清点里它们是 wired 但 stale，受治项目早已不在。

它只做三件事，**不自造任何判定语义**：

* --scaffold：给受治项目生成 .policy/dsh-adapter.yaml 与 .policy/hooks.json
  （只在文件不存在时写；已经有就不动它）；
* --install：在目标 profile 的 cordis.patch.yml 末尾追加一段**带标记**的 patch 块
  （id: policy-hook → 本仓库的 src/adapters/dsh/policy-hook.plugin.mjs），
  首次改动前先备份；重复执行幂等（标记之间整段替换）；
* --check：逐条给出事实。其中「配置能不能加载」「预算不等式成不成立」调用的是核心层
  自己的 load_config / load_rule_set / check_wiring，本文件一行不复制；最后一条事实是
  **真的把 Hook 进程起一次**（--self-check，走 dsh 用的同一个 shell）。

它**不**做的事：不启动 dsh、不触发任何工具调用、不写审计、不改任何 allow / block。
--uninstall 删掉标记块，其余字节原样保留。

**装到 desktop 之后要重启 dsh 才生效**——profile 的 patch 只在启动时加载一次。
复核入口是 python -m adapters.cli wiring（它读的是宿主的真实配置，不是本工具的自述）。

用法::

    python tools/dsh_bridge.py --check                        # 只读；退出码 1 = 还不能判定
    python tools/dsh_bridge.py --scaffold                     # 先建受治项目的配置
    python tools/dsh_bridge.py --install --dry-run            # 打印将要写入的块，不写盘
    python tools/dsh_bridge.py --install                      # 写盘（首次改动前备份）
    python tools/dsh_bridge.py --install --project <项目> --profile governed
    python tools/dsh_bridge.py --uninstall                    # 撤回（其余字节不动）

退出码：0 = 与本次请求一致；1 = 检查里有失败的事实；2 = 用法或环境错误
（profile 不存在、标记块残缺、配置文件缺失等）。
"""

from __future__ import annotations

import argparse
import datetime as clock
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
# provenance 只依赖标准库（与 tools/dsh_sandbox_loop.py 同一条理由）：报告里的路径要能看出
# 「属于哪棵树」，而为了渲染一个路径去 import 核心层的 pydantic 链不值得。
sys.path.insert(0, str(SRC_DIR))

from provenance import reading_context as reading  # noqa: E402

# 本工具 --json 载荷自己的版本轴（AGENTS 第 55 条：加键就是改协议）。
BRIDGE_REPORT_SCHEMA_VERSION = "1.0"

PLUGIN_RELATIVE = Path("src") / "adapters" / "dsh" / "policy-hook.plugin.mjs"
DEFAULT_ADAPTER_CONFIG = Path(".policy") / "dsh-adapter.yaml"
DEFAULT_HOOKS_CONFIG = Path(".policy") / "hooks.json"
ENTRY_ID = "policy-hook"
DEFAULT_HOOK_TIMEOUT_SECONDS = 30
DEFAULT_PLUGIN_TIMEOUT_MS = 30000

LF = chr(10)
CRLF = chr(13) + chr(10)

# 标记块：整段由本工具拥有，删掉它 = 撤回接线（不会碰到文件里别人的条目）。
MARKER_BEGIN = "# >>> dsh-bridge（由 tools/dsh_bridge.py 管理；删除本块即撤回接线）"
MARKER_END = "# <<< dsh-bridge"

# 事实的三态（与仓库既有口径同型）：pass / fail / unavailable。
# unavailable **不是通过**——「没读到」与「读到了且对」必须能分开。
PASS = "pass"
FAIL = "fail"
UNAVAILABLE = "unavailable"

PROBE_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class Fact:
    """一条检查事实：名字、三态、以及「凭什么」（写给读报告的人）。"""

    name: str
    status: str
    detail: str


def _posix(value: Path | str) -> str:
    return Path(value).as_posix()


def display(path: Optional[Path]) -> Optional[str]:
    """报告里的路径一律仓库相对，工作区之外折叠成 <outside-workspace>（21 号 §3）。"""
    return None if path is None else reading.display_path(path, root=REPO_ROOT)


def default_dsh_home() -> Path:
    """$DSH_HOME，其次 ~/.dsh（与 adapters.wiring 的发现口径一致）。"""
    env = os.environ.get("DSH_HOME")
    if env and env.strip():
        return Path(env)
    return Path.home() / ".dsh"


def shell_argv() -> Optional[list[str]]:
    """dsh 在 Windows 上用 pwsh 跑命令；本机只有 5.1 时回退到 powershell。

    回退**不是等价**：Windows PowerShell 5.1 的 -Command 不保留原生命令的退出码
    （src/adapters/dsh/README.md §2.3.1 有最小复现），所以下面拼探针命令时必须补
    exit $LASTEXITCODE——少了它，探针永远读到 1，一条能失败的检查会变成永远失败。
    """
    for name in ("pwsh", "powershell"):
        found = shutil.which(name)
        if found:
            return [found, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"]
    return None


def render_hook_command(*, python: Path | str, config: str, hooks_config: str) -> str:
    """Hook 命令的**唯一**拼法：patch 与 hooks.json 必须逐字相同，否则两处会慢慢漂移。

    为什么带 $env:PYTHONPATH：_posix(REPO_ROOT / "src") 是**平台自己**的 src——不是受治
    项目的 src。本仓库不把 src/ 装进 site-packages，而 Hook 进程由 dsh 拉起、继承的是
    dsh 自己的环境：搜索路径指错（或干脆不写）时，Hook 会在运行期以
    No module named adapters 结束，而"起不来"在 dsh 侧等于**放行**——这正是
    hook.self_check 那条事实要挡住的东西（它在本工具的第一版里真的挡下过一次）。
    """
    return (
        f"$env:PYTHONPATH='{_posix(REPO_ROOT / 'src')}'; "
        f"& '{_posix(python)}' -m adapters.dsh.hooks "
        f"--config {config} --hooks-config {hooks_config}"
    )


def _yaml_double(value: str) -> str:
    """YAML 双引号标量（命令里有单引号，所以走双引号那一档）。

    双引号与反斜杠会让这个标量需要转义；本工具生成的命令里两者都不该出现
    （路径一律 posix 形态、PowerShell 用单引号），出现就报错——拼一个自己读不准的
    标量，比直接失败更糟。
    """
    if '"' in value or chr(92) in value:
        raise ValueError("命令里出现了 YAML 双引号标量无法原样承载的字符（双引号或反斜杠）")
    return '"' + value + '"'


def render_patch_block(*, plugin: Path, command: str, project: Path) -> str:
    """要写进 cordis.patch.yml 的那一段（含标记行；末尾不带换行，由调用方补）。"""
    return LF.join(
        [
            MARKER_BEGIN,
            "- insert:",
            f"    - id: {ENTRY_ID}",
            f"      name: '{_posix(plugin)}'",
            "      config:",
            f"        command: {_yaml_double(command)}",
            f"        timeoutMs: {DEFAULT_PLUGIN_TIMEOUT_MS}",
            f"        projectDir: '{_posix(project)}'",
            MARKER_END,
        ]
    )


def split_lines(text: str) -> tuple[list[str], str]:
    """按行拆开并记住原来的换行符：我们只该追加一段，不该顺手把整个文件改写一遍。"""
    newline = CRLF if CRLF in text else LF
    return text.split(newline), newline


def block_span(lines: Sequence[str]) -> Optional[tuple[int, int]]:
    """标记块的行区间 [起, 止)；只有一个标记时返回 (-1, -1)（残缺，调用方报错）。"""
    begin = next((i for i, line in enumerate(lines) if line.strip() == MARKER_BEGIN), None)
    close = next((i for i, line in enumerate(lines) if line.strip() == MARKER_END), None)
    if begin is None and close is None:
        return None
    if begin is None or close is None or close < begin:
        return (-1, -1)
    return (begin, close + 1)


def managed_end(lines: Sequence[str], close: int) -> int:
    """标记块真实占用的结束下标：把紧随的那个空元素（= 行尾换行）也算进来。

    算进来才能**逐字节**还原：文件末尾的空行属于原文，不属于我们写的那一段。
    第一版把"末尾空行"当噪声删掉，于是 uninstall 之后文件比原来少两个字节——
    那正是「其余字节原样保留」这句话会说谎的地方。
    """
    end = close + 1
    if end < len(lines) and lines[end] == "":
        end += 1
    return end


def apply_block(text: str, block: str) -> str:
    """插入或整段替换标记块；其余行（含末尾空行与换行符）逐字保留。"""
    lines, newline = split_lines(text)
    span = block_span(lines)
    if span == (-1, -1):
        raise ValueError("标记块残缺（只有一个标记）：先手工修好再装，本工具不猜要删哪一段")
    block_lines = [*block.split(LF), ""]
    if span is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(block_lines)
    else:
        lines[span[0] : managed_end(lines, span[1] - 1)] = block_lines
    return newline.join(lines)


def remove_block(text: str) -> str:
    """删掉标记块（没装过就原样返回）——还原到安装前的字节。"""
    lines, newline = split_lines(text)
    span = block_span(lines)
    if span == (-1, -1):
        raise ValueError("标记块残缺（只有一个标记）：不猜要删哪一段")
    if span is None:
        return text
    del lines[span[0] : managed_end(lines, span[1] - 1)]
    return newline.join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


ADAPTER_TEMPLATE = '''# 受控项目的 dsh Adapter 配置（由 tools/dsh_bridge.py --scaffold 生成；可以自由修改）。
#
# 路径基准是**本文件所在目录**（.policy/），不是 project_root——所以下面写 .. 。
# 写成 ../.. 不会报错：project_root（包含边界）会挪到项目之外，规则 / 注册表多半
# 加载不到（失败关闭），恰好存在时则是**静默**加载了项目外的数据。
agent_version: "{agent_version}"   # 记录用；宿主实际版本见 python -m adapters.cli host-version
project: {project_name}
project_root: ..
rules:
  - {rules}
rules_root: {rules_root}
timeout_ms: 5000   # 内部预算：必须严格小于 hooks.json 里的 timeout

layers:
  - pattern: "**/*_controller.py"
    layer: controller
  - pattern: "**/*_service.py"
    layer: service
  - pattern: "**/*_repository.py"
    layer: repository
  - pattern: "**/*.py"
    layer: module
  - pattern: "**/*.md"
    layer: docs
default_layer: null   # 显式写明「不提供默认值」：未声明的路径会被阻断并要求补声明

languages:
  - pattern: "**/*.py"
    language: python
default_language: text

principal:
  subject: local-user
  roles: [developer]

audit_log: {audit_log}
registry: {registry}
registry_approved: {registry_approved}
enforcement_ledger: {enforcement_ledger}
'''


def read_agent_version() -> str:
    """从能力声明里读宿主版本（记录用）——不 import yaml，读一行就够。"""
    manifest = REPO_ROOT / "adapters" / "dsh" / "manifest.yaml"
    try:
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.startswith("agent_version:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def render_adapter_config(*, project_name: str) -> str:
    """受治项目的 adapter 配置：规则与注册表来自**本仓库**（绝对路径），其余相对本文件。"""
    return ADAPTER_TEMPLATE.format(
        agent_version=read_agent_version(),
        project_name=project_name,
        rules=_posix(REPO_ROOT / "policies"),
        rules_root=_posix(REPO_ROOT),
        audit_log="../.tmp/artifacts/dsh-bridge-audit.jsonl",
        registry=_posix(REPO_ROOT / "registry" / "tool-registry.yaml"),
        registry_approved=_posix(REPO_ROOT / "registry" / "tool-registry.approved.json"),
        enforcement_ledger="../.tmp/artifacts/dsh-bridge-ledger.jsonl",
    )


def render_hooks_config(command: str) -> str:
    """hooks.json：**同一串命令**（pre 与 post 成对，G2）。它同时是接线自检的证据文件。"""
    entry = [{"type": "command", "command": command, "timeout": DEFAULT_HOOK_TIMEOUT_SECONDS}]
    document = {"hooks": {"PreToolUse": [{"hooks": entry}], "PostToolUse": [{"hooks": entry}]}}
    return json.dumps(document, ensure_ascii=False, indent=2) + LF


def resolve_under(project: Path, value: str) -> Path:
    """相对路径按受治项目解析（Hook 的 cwd 就是 projectDir）。"""
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (project / candidate)


def profile_dir_of(dsh_home: Path, profile: str) -> Path:
    return dsh_home / "profiles" / profile


def load_block_entry(patch_text: str) -> tuple[str, Optional[dict], str]:
    """解析标记块：返回 (状态, 条目, 理由)。

    状态取值：missing（没有块）/ torn（只有一个标记）/ present（有块且解析出来了）
    / unparsable（有块但读不成我们写的那形状）。
    """
    lines, _ = split_lines(patch_text)
    span = block_span(lines)
    if span is None:
        return "missing", None, "patch 里没有 dsh-bridge 标记块（还没装过，或被手工删掉）"
    if span == (-1, -1):
        return "torn", None, "标记块残缺（只有一个标记）：不猜要删哪一段，先手工修好"
    body = LF.join(lines[span[0] + 1 : span[1] - 1])
    try:
        import yaml  # 惰性：只有真的要读块时才需要

        document = yaml.safe_load(body)
    except Exception as error:  # noqa: BLE001 - 读不出来就是读不出来，理由照样写下来
        return "unparsable", None, f"标记块不是合法 YAML：{type(error).__name__}: {error}"
    if not isinstance(document, list) or not document:
        return "unparsable", None, "标记块不是「一个 patch 条目」的列表"
    first = document[0]
    if not isinstance(first, dict) or not isinstance(first.get("insert"), list):
        return "unparsable", None, "标记块里没有 insert 列表"
    for entry in first["insert"]:
        if isinstance(entry, dict) and entry.get("id") == ENTRY_ID:
            return "present", entry, ""
    return "unparsable", None, f"insert 列表里没有 id: {ENTRY_ID} 的条目"


def command_of(entry: Optional[dict]) -> str:
    if not isinstance(entry, dict):
        return ""
    config = entry.get("config")
    if not isinstance(config, dict):
        return ""
    command = config.get("command")
    return command if isinstance(command, str) else ""


def probe_fact(command: str, *, project: Path) -> Fact:
    """把 Hook 进程**真的起一次**：这是唯一能覆盖「命令拼错了」的一条事实。

    走 dsh 用的同一个 shell（本机只有 Windows PowerShell 5.1，见 shell_argv 的注释），
    并补 exit $LASTEXITCODE——不补的话宿主会把成功的 0 压成 1。
    """
    argv = shell_argv()
    if argv is None:
        return Fact("hook.self_check", UNAVAILABLE, "本机既没有 pwsh 也没有 powershell，起不了探针")
    if command.strip() == "":
        return Fact("hook.self_check", UNAVAILABLE, "没有可执行的 hook 命令（标记块没读出来）")
    # --self-check 是平台自己的"证明接线"入口（README §10）：它加载配置与规则集、跑一遍
    # 预算不等式，然后退出——**不读 stdin、不判定、不写审计**，所以 check 仍然是只读的。
    # 不补这个开关的话，Hook 会把空 stdin 读成 null 载荷、以 context_error 退出 2，
    # 于是探针永远红（这是本工具第二版真的踩到过的坑）。
    try:
        completed = subprocess.run(
            [*argv, command + " --self-check; exit $LASTEXITCODE"],
            cwd=project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return Fact("hook.self_check", FAIL, f"探针起不来：{type(error).__name__}: {error}")
    if completed.returncode == 0:
        return Fact("hook.self_check", PASS, "Hook 的 --self-check 在受治项目里退出 0")
    detail = (completed.stderr or completed.stdout or "").strip().splitlines()
    head = detail[0] if detail else "（没有输出）"
    return Fact("hook.self_check", FAIL, f"退出码 {completed.returncode}：{head}")


def core_functions():
    """惰性 import 核心层：--help 与 --dry-run 不该被 pydantic 链拖住。"""
    from adapters.dsh.adapter import load_config
    from adapters.dsh.hooks import check_wiring
    from policy.loader import load_rule_set

    return load_config, check_wiring, load_rule_set


def _unavailable_after(message: str) -> list[Fact]:
    return [
        Fact("hooks.config", UNAVAILABLE, message),
        Fact("wiring.budget", UNAVAILABLE, message),
    ]


def config_facts(config_path: Path, hooks_path: Path) -> list[Fact]:
    """配置族的三条事实：能不能加载 / hooks.json 算不算接线证据 / 预算不等式成不成立。

    **一行判定语义都不复制**：加载走 load_config 与 load_rule_set，不等式走 check_wiring。
    这三条正是 Hook 启动时自己会走的那一段（hooks.py 的 --self-check），所以这里的
    PASS 与"运行期真的会判定"是同一件事的两个读数。
    """
    if not config_path.is_file():
        return [
            Fact("adapter.config", FAIL, display(config_path) + " 不存在（先跑 --scaffold）"),
            *_unavailable_after("adapter 配置没读到，跳过"),
        ]
    try:
        load_config, check_wiring, load_rule_set = core_functions()
        config = load_config(config_path)
        load_rule_set(config.rule_dirs, repo_root=config.rule_anchor)
    except Exception as error:  # noqa: BLE001 - 失败关闭：读不出来就是失败，理由照写
        return [
            Fact("adapter.config", FAIL, f"配置或规则集加载失败：{type(error).__name__}: {error}"),
            *_unavailable_after("adapter 配置没读到，跳过"),
        ]
    facts = [
        Fact("adapter.config", PASS, f"配置与规则集加载通过（timeout_ms={config.timeout_ms}）")
    ]

    if not hooks_path.is_file():
        return [
            *facts,
            Fact("hooks.config", FAIL, display(hooks_path) + " 不存在（先跑 --scaffold）"),
            Fact("wiring.budget", FAIL, "没有 hooks.json：dsh 会因此不注册任何 hook（等于没有治理）"),
        ]
    try:
        document = json.loads(hooks_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [
            *facts,
            Fact("hooks.config", FAIL, f"hooks.json 不可解析：{type(error).__name__}: {error}"),
            Fact("wiring.budget", FAIL, "hooks.json 读不懂：接线自检证明不了 dsh 会注册本 Hook"),
        ]
    facts.append(Fact("hooks.config", PASS, "hooks.json 可解析"))

    try:
        report = check_wiring(config, hooks_config_path=hooks_path)
    except Exception as error:  # noqa: BLE001
        facts.append(
            Fact("wiring.budget", FAIL, f"接线自检自己抛了异常：{type(error).__name__}: {error}")
        )
        return facts
    if report == "":
        facts.append(Fact("wiring.budget", PASS, "预算不等式成立、命令指向 adapters.dsh.hooks"))
    else:
        facts.append(Fact("wiring.budget", FAIL, str(report)))
    return facts


def collect_facts(
    *, profile_dir: Path, patch_path: Path, config_path: Path, hooks_path: Path, project: Path
) -> list[Fact]:
    """九条事实（顺序固定，报告逐条列出）。未读到的项一律 unavailable，不是 pass。"""
    facts: list[Fact] = []
    if profile_dir.is_dir():
        facts.append(Fact("profile.exists", PASS, display(profile_dir) or ""))
    else:
        facts.append(
            Fact("profile.exists", FAIL, (display(profile_dir) or "") + " 不是目录：先确认 profile 名")
        )
        return facts

    if not patch_path.is_file():
        facts.append(
            Fact("patch.exists", FAIL, (display(patch_path) or "") + " 不存在：这个 profile 还没有 patch 层")
        )
        return facts
    facts.append(Fact("patch.exists", PASS, display(patch_path) or ""))

    patch_text = patch_path.read_text(encoding="utf-8")
    state, entry, reason = load_block_entry(patch_text)
    if state == "present":
        facts.append(Fact("patch.block", PASS, "dsh-bridge 标记块可解析"))
    else:
        facts.append(Fact("patch.block", FAIL, reason))

    command = command_of(entry)
    if command == "":
        facts.append(Fact("plugin.exists", UNAVAILABLE, "标记块没读出来，跳过"))
        facts.append(Fact("command.references_hook", UNAVAILABLE, "标记块没读出来，跳过"))
    else:
        name = entry.get("name") if isinstance(entry, dict) else None
        plugin = Path(name) if isinstance(name, str) and name else None
        if plugin is not None and plugin.is_file():
            facts.append(Fact("plugin.exists", PASS, display(plugin) or ""))
        else:
            facts.append(Fact("plugin.exists", FAIL, f"插件文件不存在：{name}"))
        if "adapters.dsh.hooks" in command:
            facts.append(Fact("command.references_hook", PASS, "命令指向 adapters.dsh.hooks"))
        else:
            facts.append(
                Fact("command.references_hook", FAIL, "命令里没有 adapters.dsh.hooks：接的不是本平台的 Hook")
            )

    facts.extend(config_facts(config_path, hooks_path))

    if command == "":
        facts.append(Fact("hook.self_check", UNAVAILABLE, "没有可执行的 hook 命令（标记块没读出来）"))
    else:
        facts.append(probe_fact(command, project=project))
    return facts


def overall(facts: Sequence[Fact]) -> str:
    return "fail" if any(fact.status == FAIL for fact in facts) else "ok"


PATCH_HEADER = (
    "# Your patch layer for this dsh profile, applied after every bundle layer:"
    + LF
    + "# a top-level YAML array of loader patch entries. Edit cordis.patch.yml, not this file."
    + LF
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools/dsh_bridge.py",
        description="把策略桥挂到本机 dsh 的某个 profile 上，并逐条证明它挂上了（不启动 dsh）。",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="只读：逐条给出事实（1 = 有失败）")
    action.add_argument("--install", action="store_true", help="写入标记块（首次改动前备份）")
    action.add_argument("--uninstall", action="store_true", help="删掉标记块，其余字节不动")
    action.add_argument("--scaffold", action="store_true", help="生成受治项目的 .policy/ 配置")
    parser.add_argument("--dsh-home", default=None, help="dsh 配置根（默认 $DSH_HOME，其次 ~/.dsh）")
    parser.add_argument("--profile", default="desktop", help="目标 profile（默认 desktop）")
    parser.add_argument("--project", default=None, help="受治项目（默认本仓库根）")
    parser.add_argument(
        "--config", default=None, help=f"adapter 配置（默认 {_posix(DEFAULT_ADAPTER_CONFIG)}）"
    )
    parser.add_argument(
        "--hooks-config", default=None, help=f"hooks.json（默认 {_posix(DEFAULT_HOOKS_CONFIG)}）"
    )
    parser.add_argument("--python", default=None, help="Hook 用的解释器（默认当前解释器）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要写入的内容，不写盘")
    parser.add_argument("--json", action="store_true", help="输出机器可读载荷")
    return parser


def _stamp() -> str:
    return clock.datetime.now(clock.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup(path: Path) -> Path:
    target = path.with_name(path.name + ".bak-" + _stamp())
    shutil.copy2(path, target)
    return target


def emit(
    *,
    args: argparse.Namespace,
    action: str,
    profile: str,
    dsh_home: Path,
    project: Path,
    patch_path: Path,
    facts: Sequence[Fact],
    notes: Sequence[str],
    result: str,
) -> None:
    if args.json:
        payload: dict[str, Any] = {
            "schema_version": BRIDGE_REPORT_SCHEMA_VERSION,
            "action": action,
            "profile": profile,
            "dsh_home": display(dsh_home),
            "project": display(project),
            "patch": display(patch_path),
            "notes": list(notes),
            "facts": [
                {"name": fact.name, "status": fact.status, "detail": fact.detail} for fact in facts
            ],
            "result": result,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"目标：profile={profile}  dsh-home={display(dsh_home)}  受治项目={display(project)}")
    print(f"      patch={display(patch_path)}")
    for note in notes:
        print(f"  [note] {note}")
    for fact in facts:
        print(f"  [{fact.status.upper()}] {fact.name}: {fact.detail}")
    if not facts and not notes:
        print("  （没有可报告的事实）")
    print(f"结果：{result}")


def run_scaffold(*, args, config_path: Path, hooks_path: Path, project: Path, command: str) -> int:
    notes: list[str] = []
    for path, text in (
        (config_path, render_adapter_config(project_name=project.name)),
        (hooks_path, render_hooks_config(command)),
    ):
        if path.exists():
            notes.append(display(path) + " 已存在：不动它（要重写先手工删掉）")
            continue
        if args.dry_run:
            notes.append("（dry-run）会写入 " + (display(path) or ""))
            continue
        write_text(path, text)
        notes.append("已写入 " + (display(path) or ""))
    emit(
        args=args,
        action="scaffold",
        profile=args.profile,
        dsh_home=Path(args.dsh_home) if args.dsh_home else default_dsh_home(),
        project=project,
        patch_path=config_path,
        facts=[],
        notes=notes,
        result="dry_run" if args.dry_run else "ok",
    )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    dsh_home = Path(args.dsh_home).resolve() if args.dsh_home else default_dsh_home()
    project = Path(args.project).resolve() if args.project else REPO_ROOT
    config_value = args.config or _posix(DEFAULT_ADAPTER_CONFIG)
    hooks_value = args.hooks_config or _posix(DEFAULT_HOOKS_CONFIG)
    config_path = resolve_under(project, config_value)
    hooks_path = resolve_under(project, hooks_value)
    profile_dir = profile_dir_of(dsh_home, args.profile)
    patch_path = profile_dir / "cordis.patch.yml"
    python = Path(args.python).resolve() if args.python else Path(sys.executable)
    plugin = REPO_ROOT / PLUGIN_RELATIVE
    command = render_hook_command(
        python=python, config=_posix(config_value), hooks_config=_posix(hooks_value)
    )

    if args.scaffold:
        return run_scaffold(
            args=args, config_path=config_path, hooks_path=hooks_path, project=project, command=command
        )

    if not profile_dir.is_dir():
        print(
            f"[error] profile 不存在：{display(profile_dir)}"
            "（用 --dsh-home / --profile 指到真实存在的 profile）",
            file=sys.stderr,
        )
        return 2

    if args.install or args.uninstall:
        if not patch_path.is_file() and args.uninstall:
            print(f"[error] 没有 patch 层，无可撤回：{display(patch_path)}", file=sys.stderr)
            return 2

    if args.install:
        missing = [path for path in (config_path, hooks_path) if not path.is_file()]
        if missing:
            print(
                "[error] 受治项目的配置不齐："
                + "、".join(display(path) or "" for path in missing)
                + "；先跑 python tools/dsh_bridge.py --scaffold（或 --config/--hooks-config 指到已有配置）",
                file=sys.stderr,
            )
            return 2

        block = render_patch_block(plugin=plugin, command=command, project=project)
        if args.dry_run:
            emit(
                args=args,
                action="install",
                profile=args.profile,
                dsh_home=dsh_home,
                project=project,
                patch_path=patch_path,
                facts=[],
                notes=["（dry-run）将要写入的块：" + LF + block],
                result="dry_run",
            )
            return 0

        original = patch_path.read_text(encoding="utf-8") if patch_path.is_file() else PATCH_HEADER
        notes = []
        if patch_path.is_file():
            notes.append("备份：" + (display(backup(patch_path)) or ""))
        try:
            write_text(patch_path, apply_block(original, block))
        except ValueError as error:
            print(f"[error] {error}", file=sys.stderr)
            return 2
        notes.append("已写入标记块（重启 dsh 后生效）")

        facts = collect_facts(
            profile_dir=profile_dir,
            patch_path=patch_path,
            config_path=config_path,
            hooks_path=hooks_path,
            project=project,
        )
        result = overall(facts)
        emit(
            args=args,
            action="install",
            profile=args.profile,
            dsh_home=dsh_home,
            project=project,
            patch_path=patch_path,
            facts=facts,
            notes=notes,
            result=result,
        )
        return 0 if result == "ok" else 1

    if args.uninstall:
        original = patch_path.read_text(encoding="utf-8")
        try:
            updated = remove_block(original)
        except ValueError as error:
            print(f"[error] {error}", file=sys.stderr)
            return 2
        if updated == original:
            emit(
                args=args,
                action="uninstall",
                profile=args.profile,
                dsh_home=dsh_home,
                project=project,
                patch_path=patch_path,
                facts=[],
                notes=["没有 dsh-bridge 标记块：什么都没改"],
                result="ok",
            )
            return 0
        if args.dry_run:
            emit(
                args=args,
                action="uninstall",
                profile=args.profile,
                dsh_home=dsh_home,
                project=project,
                patch_path=patch_path,
                facts=[],
                notes=["（dry-run）会删掉标记块"],
                result="dry_run",
            )
            return 0
        notes = ["备份：" + (display(backup(patch_path)) or ""), "已删掉标记块（重启 dsh 后生效）"]
        write_text(patch_path, updated)
        emit(
            args=args,
            action="uninstall",
            profile=args.profile,
            dsh_home=dsh_home,
            project=project,
            patch_path=patch_path,
            facts=[],
            notes=notes,
            result="ok",
        )
        return 0

    facts = collect_facts(
        profile_dir=profile_dir,
        patch_path=patch_path,
        config_path=config_path,
        hooks_path=hooks_path,
        project=project,
    )
    result = overall(facts)
    emit(
        args=args,
        action="check",
        profile=args.profile,
        dsh_home=dsh_home,
        project=project,
        patch_path=patch_path,
        facts=facts,
        notes=[],
        result=result,
    )
    return 0 if result == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""重放 Phase 2 的真实 dsh 沙箱闭环。

它在一个受控临时项目里跑两遍真实 dsh（headless profile + 进程内策略 Hook 插件）：

    1) bad 编辑：controller 直接依赖 repository → 必须被 ARCH-001 阻断，文件哈希不变；
    2) good 编辑：新增一个方法 → 必须放行，且只发生一次预期变更。

断言失败即退出码 1；dsh 不可用、**Hook 进程根本起不来且原因是沙箱禁止管道 stdio**
（CI 的 ubuntu runner）、或 **dsh 自身被环境挡住**（$DSH_HOME 写不进去 / 系统 temp
不可写）时按**环境跳过**处理并退出码 0，因为这条闭环验证的是"本机真实 Agent Runtime
的行为"，不是可移植的单元测试。**但"Hook 起不来"不等于"环境不允许"**：理由是"工作目录不可用"
（projectDir 配错）或读不出原因时按**真失败**收场（分类见 `hook_spawn_failure()`）。

但"跳过"必须**可判定**、不能被读成"已验证"，也不能把不同的失败原因糊成一个：**每条**
跳过路径都在产物里写 `environment_skipped: true`（正常路径写 `false`）与各自的 reason。
"dsh 自身起不来"按**被拒路径**分成 `profile_write_denied`（落在 $DSH_HOME 下）与
`other_path_denied`（落在 temp / spill 等 dsh 自己的启动临时区），两者都在
`dsh_startup_denied_kind` 与 `dsh_startup_denied_path` 里写明是哪条路径被拒；
归不了因的权限错误**不产生跳过**（宁可红着，也不把它洗成环境限制）。
`--require-dsh` 让**任何**环境跳过都失败，跳过也绝不写成 pass。
**配置失败**是第三类：有名字、按**真失败**收场。目前认出的是「Windows ACL 临时根落在工作区内」
（`acl_temp_root_failure()`）——临时根是我们自己交给 dsh 的（`TEMP`/`TMP`，或
`--isolated-home` 指到的目录），所以它既不是环境限制，也不是策略判定。

诊断字段 `dsh_startup_denied_home_roots` 逐条带来源（`dsh_startup_denied_home_root_evidence`）：
URL 形态（`file:///…`）与普通路径**分开解析**，畸形候选按写明规则丢弃——真实日志里的
`file:///C:/…/dsh-home/profiles/headless/#spill-local` 曾被切成 `e:///C:/…` 与丢盘符的
`/Users/…`，而**正确的根** `C:/…/dsh-home` 反而进不了候选（它参与 is_under 判定）。

用法：

    python tools/dsh_sandbox_loop.py                 # 构建并跑完整闭环
    python tools/dsh_sandbox_loop.py --require-dsh   # 任何环境跳过都视为失败
    python tools/dsh_sandbox_loop.py --keep          # 保留上一轮的审计与采集，不重建项目
    python tools/dsh_sandbox_loop.py --isolated-home # 只在 dsh 子进程的 env 里换掉下面三个变量

`--isolated-home` **只改 dsh 子进程的环境**（本进程与仓库其它部分不受影响；不给这个开关时
行为一字不变）：`DSH_HOME` → `.tmp/phase-2-sandbox/dsh-home`、`TEMP`/`TMP` →
`.tmp/phase-2-sandbox/dsh-tmp`。受限宿主上 dsh 起不来的两个位置正是这两处
（`$DSH_HOME` 下的 `profiles/*.yml` 写不进去、系统 temp 下的 `mkdtemp` 被拒），
把它们指到仓库内可写目录之后，这条闭环在受限宿主上也能真跑。
**注意**：`dsh-tmp` 与受控项目 `demo-shop` 必须是**兄弟目录**——dsh 的 Windows ACL 沙箱
要求「ACL 临时根在工作区之外」（`assertTempRootOutsideWorkspace`），把隔离根放进项目里面
会被 dsh 拒绝启动；那条失败由分类器归成有名字的**配置失败**，不按环境跳过收场。

产物写在 .tmp/ 下（可随时删除并由本脚本重建）：

    .tmp/phase-2-sandbox/demo-shop/           受控项目（含 .policy/ 配置与审计）
    .tmp/phase-2-sandbox/dsh-home/            --isolated-home 时的 $DSH_HOME
    .tmp/phase-2-sandbox/dsh-tmp/             --isolated-home 时的 TEMP/TMP（spill 与 ACL 锁）
    .tmp/phase-2-sandbox/logs/                dsh 的原始输出
    .tmp/artifacts/phase-2-sandbox-result.json 结构化结论（供阶段证据引用）
"""

from __future__ import annotations

import argparse
import datetime as clock
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SANDBOX = REPO_ROOT / ".tmp" / "phase-2-sandbox"
PROJECT = SANDBOX / "demo-shop"
LOGS = SANDBOX / "logs"
ARTIFACT = REPO_ROOT / ".tmp" / "artifacts" / "phase-2-sandbox-result.json"
# reading_context 里"这棵树"默认就是仓库自己。做成模块常量有两个理由：真实运行一个字不改；
# 测试可以像 PROJECT / LOGS / ARTIFACT 那样把它换掉（否则每个驱动 main() 的用例都要为整棵仓库
# 算一次轮次级封条，那是与被测行为无关的时间）。
TREE_ROOT = REPO_ROOT

# 台阶 4：reading_context 的**统一形状只有一份实现**（src/provenance/reading_context.py，
# 21 号 §3）。本脚本按文件路径直跑，所以自己把 src 挂上搜索路径；provenance 只依赖标准库，
# 这一步不改变"没有 src 也能跑"的性质（它读树摘要用的也是同一个模块里的那份实现）。
sys.path.insert(0, str(REPO_ROOT / "src"))

from provenance import reading_context as reading  # noqa: E402

# 结论载荷的版本轴（AGENTS 第 55 条：加键就是改协议）。
#
# 1.0（**追认**、从未在载荷里出现过字面量）= **第 13 轮之前**的形状：那时载荷里既没有
# `schema_version` 本身，也没有后来那三族诊断键——第 14 轮（`c75886e`）的
# `dsh_startup_denied_` 一族、第 15 轮（`b9d3b11`）的 `hook_spawn_denied_` 一族、
# 第 18 轮（`09322b0`）的 `dsh_config_failure_` 一族（三族键的引入点由 `git show` 逐版读出）。
# 第 13 轮的树（`b2c1255`）里这个文件只有一个 `dsh_startup_denied` 布尔位，
# 「哪条路径被拒」还读不出来；那棵树上也没有 `schema_version`。
# 1.1 = 第 19 轮形状：**两条写盘路径（完整跑 / dsh 不可用）都带这个键**，各自的诊断键按路径出现或缺失。
# 1.2 = 现形状（台阶 4 第一件）：两条路径都多一份 `reading_context`（21 号 §3 的统一形状），
#       其中 `host.sandbox` 是 2026-09-30 裁定①的落点（**不单独设状态轴**，只加这一个枚举）。
#       它的作用就是让 `.tmp/artifacts/` 下那份 **skipped 产物自己说得出**"这不是这棵树上的
#       真机读数"（pre-push 钩子每次推送都会用 skipped 覆盖它，见第 20 轮记录 §2）。
#
# 消费方：`tools/phase_evidence.py` 的 `sandbox_loop()`（逐键 `.get()`，**不依赖键集合**）
# 与 `.tmp/e2e/` 下的人工复核副本。读这份载荷的代码不必认全键，但「这份读数属于哪一代
# 形状」必须能读出来——这就是本轴存在的理由；下一族诊断键落地时，这里跟着递增。
SANDBOX_RESULT_SCHEMA_VERSION = "1.2"

# 探测不到宿主版本时的**显式**取值：不是猜一个版本号，也不是拿声明里的旧值冒充。
AGENT_VERSION_UNAVAILABLE = "unavailable"
RULE_ID = "ARCH-001@1"

CONTROLLER_START = '''"""订单 HTTP 入口。"""

from service import OrderService


class OrderController:
    def __init__(self) -> None:
        self.service = OrderService()

    def create(self, payload: dict) -> dict:
        return self.service.create(payload)
'''

SERVICE = '''"""订单业务逻辑。"""

from repository import OrderRepository


class OrderService:
    def __init__(self) -> None:
        self.repository = OrderRepository()

    def create(self, payload: dict) -> dict:
        return self.repository.insert(payload)
'''

ADAPTER_CONFIG = '''# 受控沙箱项目的 dsh Adapter 配置（由 tools/dsh_sandbox_loop.py 生成）。
agent_version: "{agent_version}"
project: demo-shop
project_root: ..
rules:
  - {repo}/policies
rules_root: {repo}
timeout_ms: 5000
layers:
  - pattern: "**/*_controller.py"
    layer: controller
  - pattern: "**/*_service.py"
    layer: service
  - pattern: "**/*_repository.py"
    layer: repository
languages:
  - pattern: "**/*.py"
    language: python
default_language: text
audit_log: .policy/audit.jsonl
# Phase 4：受控执行需要的授权链路。缺少任何一项，受控工具都会被 Hook 阻断。
principal:
  subject: local-user
  roles:
    - developer
registry: {repo}/registry/tool-registry.yaml
registry_approved: {repo}/registry/tool-registry.approved.json
enforcement_ledger: .policy/enforcement-ledger.jsonl
'''

HOOK_COMMAND = (
    "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml "
    "--hooks-config .policy/hooks.json --audit .policy/audit.jsonl "
    "--capture .policy/captures"
)

HOOKS_JSON = {
    "hooks": {
        "PreToolUse": [
            {
                "hooks": [
                    {"type": "command", "command": HOOK_COMMAND, "timeout": 30}
                ]
            }
        ]
    }
}

PATCH_TEMPLATE = """# 由 tools/dsh_sandbox_loop.py 生成：把进程内策略 Hook 插件挂到 profile 上。
- insert:
    - id: policy-hook
      name: '{repo}/src/adapters/dsh/policy-hook.plugin.mjs'
      config:
        command: '{command}'
        timeoutMs: 30000
        projectDir: '{project}'
"""

BLOCK_PROMPT = (
    "用 edit 工具在 src/shop/order_controller.py 的 import 区加一行 "
    "'from repository import OrderRepository'，然后一句话报告结果。"
)
ALLOW_PROMPT = (
    "用 edit 工具在 src/shop/order_controller.py 的 create 方法后面加一个方法 "
    "def ping(self) -> str: 内部返回 'pong'，然后一句话报告结果。"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_project(*, keep: bool, agent_version: str) -> None:
    """重建受控项目；--keep 时只重置被治理的源文件，保留审计与采集。"""

    (PROJECT / "src" / "shop").mkdir(parents=True, exist_ok=True)
    (PROJECT / ".policy").mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    # --isolated-home 的两个隔离根必须**先建出来**（2026-10-09 定位的真失败）：
    # dsh 的 @deepseek-ai/dsh-spill-local 启动时对 TEMP 做 mkdtempSync，临时根不存在时
    # 它以 ENOENT 结束在**插件树加载**阶段——dsh 根本没起来，于是一个工具调用都没发生、
    # Hook 一次都没被调用。现象与"策略放行"同形（审计为空 + 文件哈希不变），
    # 所以它只能靠这两条 mkdir 消灭，不能靠读审计反推。
    # 与开关无关：这两处是模块 docstring 第 49-50 行就已声明的产物位置。
    ISOLATED_HOME.mkdir(parents=True, exist_ok=True)
    ISOLATED_TMP.mkdir(parents=True, exist_ok=True)

    write(PROJECT / "AGENTS.md", (
        "# demo-shop（受控沙箱）\n\n"
        "这是用于验证工程策略门禁的最小项目，不是真实业务代码。\n\n"
        "- 分层约定：controller → service → repository；\n"
        "- 规则库在别处，本目录只放沙箱代码。\n"
    ))
    write(PROJECT / "src" / "shop" / "order_controller.py", CONTROLLER_START)
    write(PROJECT / "src" / "shop" / "order_service.py", SERVICE)

    write(
        PROJECT / ".policy" / "dsh-adapter.yaml",
        ADAPTER_CONFIG.format(agent_version=agent_version, repo=REPO_ROOT.as_posix()),
    )
    write(
        PROJECT / ".policy" / "hooks.json",
        json.dumps(HOOKS_JSON, ensure_ascii=False, indent=2) + "\n",
    )
    write(
        PROJECT / ".policy" / "patch.yml",
        PATCH_TEMPLATE.format(
            repo=REPO_ROOT.as_posix(),
            command=HOOK_COMMAND,
            project=PROJECT.as_posix(),
        ),
    )

    if not keep:
        for stale in (".policy/audit.jsonl", ".policy/captures"):
            target = PROJECT / stale
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink()


def host_agent_version(argv: list[str] | None = None) -> str:
    """宿主**实际**版本：跑一次 `<dsh> --version` 取出来（探测，不是查表）。

    为什么不能再用常量：这个值会被写进两处——受控项目的 `.policy/dsh-adapter.yaml` 与结论载荷的
    `agent_version`——而它同时是**审计记录**里 `agent_version` 的来源（`adapter.py` 从配置取值）。
    常量会漂：2026-10-09 那次真机读数跑的是 0.2.1-alpha.2，账本上写的却是 0.1.5-rc.1。
    探测不到（没有 dsh / 非零退出 / 超时 / 读不出）就写 `unavailable`——"读不到"是一个事实，
    不许拿声明里的旧值冒充（同一条纪律：AGENTS 第 54 条，缺记录就是缺记录）。
    """

    resolved = dsh_argv() if argv is None else argv
    if not resolved:
        return AGENT_VERSION_UNAVAILABLE
    try:
        completed = subprocess.run(
            [*resolved, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return AGENT_VERSION_UNAVAILABLE
    if completed.returncode != 0:
        return AGENT_VERSION_UNAVAILABLE
    lines = (completed.stdout or "").strip().splitlines()
    return lines[0].strip() if lines and lines[0].strip() else AGENT_VERSION_UNAVAILABLE


def dsh_argv() -> list[str] | None:
    """解析 dsh 可执行文件。

    Windows 上 npm 装出来的是 .CMD 垫片：shutil.which 能找到它，但 CreateProcess
    不接受裸名（不会自动补 PATHEXT），必须用解析后的绝对路径。
    """

    for name in ("dsh", "dsh.cmd", "dsh.exe", "dsh.bat"):
        found = shutil.which(name)
        if found:
            return [found]
    return None


# 进程内 Hook 插件在"Hook 起不来"时给出的原文（见 src/adapters/dsh/policy-hook.plugin.mjs
# 的 `hookFailureReason`）。前缀只说"Hook 进程起不来"，**不说为什么**——原因必须再从理由的
# 其余部分读出来，否则会把"projectDir 配错"说成"这台机器跑不了"：
#   * 理由里 `工作目录不存在：…` / `工作目录不是目录：…` → Hook 的工作目录不可用（接线/配置问题）；
#   * 理由里 `spawn 报错：spawn EPERM` → 受限沙箱禁止管道 stdio（dsh 的 ctx.shell 起不来）。
# 只有后者是**环境限制**；前者按真失败收场（洗成环境跳过会让"配错了"看起来像"环境不允许"）。
# **沙箱类必须同一行同时出现**两个标记（见 `_line_with_both()`）：跨行的组合只说明"这篇
# 日志里两件事都发生了"，把它们读成因果就是一次假的环境跳过（把 exit 1 洗成 exit 0）。
HOOK_FAILURE_MARKER = "Hook 无法执行"
SANDBOX_SPAWN_DENIED_MARKER = "spawn EPERM"
# 这两句只在插件**证明**目录不可用（不存在 / 不是目录）时出现；正向的"已确认存在"不含它们。
HOOK_WORKDIR_UNUSABLE_MARKERS = ("工作目录不存在", "工作目录不是目录")
# 插件理由里"工作目录不可用"那一段的原文形态：`工作目录不存在：<目录>（来自 <来源>）`。
_HOOK_WORKDIR_CLAUSE = re.compile(r"工作目录(?:不存在|不是目录)：([^（\n；]+)")

# "Hook 进程起不来"的两类**可归因原因**（"读不出原因"是第三种情况：不产生环境跳过）。
SANDBOX_PIPE_STDIO_DENIED = "sandbox_pipe_stdio_denied"
HOOK_WORKDIR_UNUSABLE = "hook_workdir_unusable"
HOOK_SPAWN_UNATTRIBUTABLE = "hook_spawn_unattributable"

# 权限被拒的原文标记：出现在日志里只说明"某个路径被拒"，**不说明是哪一层失败**。
# 旧判据就是在这里走偏的：它把这类标记与"文本里出现 profiles/.dsh/cordis/dsh-home"一与，
# 而 dsh 的崩溃堆栈里天然带着 <dsh-home>/profiles/<name>/#spill-local 这些帧——
# 于是任何一种启动失败都被说成"写 $DSH_HOME 下的 profile 被拒"。
PERMISSION_DENIED_MARKERS = (
    "EPERM",
    "EACCES",
    "WinError 5",
    "Permission denied",
    "Access is denied",
)

# dsh 启动阶段崩溃的原文（"连插件树/配置都没装起来"）。**只有**它出现，
# 日志里的权限错误才可能与 dsh 启动有关；没有它一律按"与启动无关"处理：
# 宁可让真失败保持红，也不要把无关的 EPERM 洗成环境跳过。
DSH_BOOT_FAILURE_MARKERS = (
    "plugin tree failed to load",
    "failed to apply loader entry",
    "dsh-app-boot",
    "runProfile",
)

# dsh 自己的启动临时区：spill-local 插件在启动时 mkdtemp 的目录名前缀。
DSH_SCRATCH_PREFIX = "dsh-"
DEFAULT_DSH_HOME_DIRNAME = ".dsh"

# $DSH_HOME 候选根的**来源**：诊断字段逐条写明"哪个根来自哪条证据"，读者不必猜。
HOME_ROOT_SOURCE_ENV = "env:DSH_HOME"
HOME_ROOT_SOURCE_DEFAULT = "default:$HOME/.dsh"
HOME_ROOT_SOURCE_FILE_URL = "log:file-url"
HOME_ROOT_SOURCE_LOG_PATH = "log:plain-path"
HOME_ROOT_SOURCE_INJECTED = "injected:homes"

# 两种"dsh 自身起不来"的**独立状态**，区别只在被拒路径落在哪里：
#   profile_write_denied —— 落在 $DSH_HOME（或其 profiles 子目录）下，沿用原状态与措辞；
#   other_path_denied    —— 落在 $DSH_HOME 之外的 dsh 启动临时区（系统 temp / dsh- scratch）。
PROFILE_WRITE_DENIED = "profile_write_denied"
OTHER_PATH_DENIED = "other_path_denied"

# 第三类：**配置失败**（有名字、按真失败收场）。dsh 的 Windows ACL 沙箱在**启动期**就拒绝
# 「ACL 临时根落在工作区内」——原文出自本机安装的 dsh 包
# （`@deepseek-ai/dsh-sandbox-windows-acl` 的 `assertTempRootOutsideWorkspace()`，
# 判据是 `containsDirectory(workspaceRoot, tempRoot)`）：
#     Windows ACL temp root must be outside the workspace: workspace=<…>; temp=<…>
# 为什么算**配置**失败：临时根是使用者与本脚本自己交给 dsh 的（`TEMP`/`TMP`，或
# `--isolated-home` 指到的目录），改一个变量就能过；而门禁给每一步的临时根恰好是**仓库内**的
# `.tmp/tmp`（`tools/ci_local.py` 的 `temp_root()`）——只要 dsh 把工作区算成仓库根，这条就会命中。
# 把它读成「这台机器跑不了 dsh」，与把 projectDir 配错读成沙箱限制，是同一个错误。
ACL_TEMP_ROOT_MARKER = "Windows ACL temp root must be outside the workspace"
ACL_TEMP_ROOT_INSIDE_WORKSPACE = "acl_temp_root_inside_workspace"

# `--isolated-home` 的两个隔离根：与受控项目 demo-shop **平级**（不是它的子目录，见模块 docstring）。
ISOLATED_HOME = SANDBOX / "dsh-home"
ISOLATED_TMP = SANDBOX / "dsh-tmp"

# 被拒路径的三种原文形态（都要求路径带引号，避免把 syscall/errno 当成路径）：
#   Node   EPERM: operation not permitted, mkdtemp 'C:\...\Temp\dsh-spill-XXXXXX'
#   Node   EACCES: permission denied, open '/home/x/.dsh/profiles/headless/cordis.yml'
#   Python PermissionError: [Errno 13] Permission denied: '<path>'
#   .NET   [WinError 5] Access is denied: '<path>'
_NODE_DENIAL = re.compile(
    r"(?:EPERM|EACCES)\s*:\s*[^'\n]*?,\s*(?P<syscall>[A-Za-z_][A-Za-z0-9_]*)\s+'(?P<path>[^'\n]+)'"
)
_STRUCTURED_DENIAL = re.compile(
    r"code:\s*'(?:EPERM|EACCES)'[\s\S]{0,240}?path:\s*'(?P<path>[^'\n]+)'"
)
_QUOTED_DENIAL = re.compile(
    r"(?:\[Errno\s+13\]\s*Permission denied|\[WinError\s+5\][^'\n]*?"
    r"|Permission denied|Access is denied)\s*:?\s*'(?P<path>[^'\n]+)'"
)
_QUOTED_TOKEN = re.compile(r"'([^'\n]+)'|\"([^\"\n]+)\"")
# 日志里出现的 <root>/profiles/<name>：说明 dsh 正在把 root 当 profile 根用。
# 但栈帧写的是 URL（`file:///C:/…/profiles/headless/#spill-local`），两条普通路径正则会把
# 它切成畸形候选：Windows 正则把 `file` 的 `e` 当盘符（`e:///C:/…`），POSIX 正则丢掉盘符
# （`/Users/…`）——而**正确的根** `C:/…/dsh-home` 反而进不了候选。所以 URL 与普通路径
# **分开解析**：URL 先按 URL 规则解析出本地根，普通扫描再跳过 URL 区间内的匹配。
_DSH_HOME_URL = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*)://[^\s'\"()<>]*")
_DSH_HOME_WINDOWS = re.compile(r"((?:[A-Za-z]:[\\/])[^\s'\"()]*?)[\\/]profiles[\\/]")
_DSH_HOME_POSIX = re.compile(r"(/[^\s'\"():]*?)[\\/]profiles[\\/]")


@dataclass(frozen=True)
class DeniedPath:
    """日志里一条"某个路径被环境拒绝"的原文记录（不预设它与 dsh 启动的关系）。"""

    path: str
    syscall: str | None = None
    evidence: str = ""


@dataclass(frozen=True)
class HomeRootCandidate:
    """一条 $DSH_HOME 候选根**以及它来自哪条证据**（诊断字段逐条可读，不让人从根列表反推）。"""

    root: str
    source: str
    evidence: str = ""


@dataclass(frozen=True)
class StartupDenial:
    """一次**可归因**的"dsh 自身起不来"：路径、系统调用与全部被拒路径都留证据。"""

    kind: str
    denial: DeniedPath
    paths: tuple[str, ...]
    home_roots: tuple[str, ...]
    # 与 home_roots 同序：每个根来自哪条证据（字段级来源，诊断用）。
    home_root_evidence: tuple[HomeRootCandidate, ...]

    @property
    def path(self) -> str:
        return self.denial.path

    @property
    def syscall(self) -> str | None:
        return self.denial.syscall


@dataclass(frozen=True)
class HookSpawnFailure:
    """一次**可归因**的"Hook 进程起不来"：哪一类原因、工作目录是多少、原文证据是什么。"""

    kind: str
    workdir: str | None = None
    evidence: str = ""


@dataclass(frozen=True)
class ConfigFailure:
    """一次**可归因的配置失败**：dsh 拒绝启动，而原因是**我们自己**交给它的配置。

    `workspace` / `temp` 是原文里 `workspace=` / `temp=` 两个诊断字段（**同一行**解析，
    且必须先是合法路径）；取不到就留 None —— 名字照样成立，只是细节读不出。
    """

    kind: str
    evidence: str = ""
    workspace: str | None = None
    temp: str | None = None


def _norm_path(value: str) -> str:
    """路径归一化：统一分隔符、折叠重复分隔符、Windows 上大小写不敏感。"""

    text = value.strip().strip("'\"").replace("\\", "/")
    text = re.sub(r"/{2,}", "/", text).rstrip("/")
    return (text or "/").lower() if os.name == "nt" else (text or "/")


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = _norm_path(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return tuple(result)


def _looks_like_path(value: str) -> bool:
    text = value.strip()
    if text.startswith(("/", "\\", "./", "../", ".\\", "..\\")):
        return True
    return len(text) >= 3 and text[1] == ":" and text[0].isalpha()



def denied_paths(text: str) -> tuple[DeniedPath, ...]:
    """按原文形态解析出日志里**每个**被拒路径；解析不出路径就返回空（不猜）。"""

    found: list[DeniedPath] = []
    seen: set[str] = set()

    def remember(path: str, syscall: str | None, evidence: str) -> None:
        key = _norm_path(path)
        if not key or key in seen:
            return
        seen.add(key)
        detail = evidence.strip()[:200]
        found.append(DeniedPath(path=path.strip(), syscall=syscall, evidence=detail))

    for match in _NODE_DENIAL.finditer(text):
        remember(match.group("path"), match.group("syscall"), match.group(0))
    for match in _STRUCTURED_DENIAL.finditer(text):
        remember(match.group("path"), None, match.group(0).replace(chr(10), " "))
    for match in _QUOTED_DENIAL.finditer(text):
        remember(match.group("path"), None, match.group(0))
    for line in text.splitlines():
        if not any(marker in line for marker in PERMISSION_DENIED_MARKERS):
            continue
        for match in _QUOTED_TOKEN.finditer(line):
            candidate = match.group(1) or match.group(2) or ""
            if _looks_like_path(candidate):
                remember(candidate, None, line)
    return tuple(found)



def _percent_decode(text: str) -> str:
    """百分号解码只做保守处理：**只解一层**，解不开或解出控制字符就保留原文（宁可不匹配，也不产畸形项）。

    规则逐条写明白：
      * 只解一层：`%2520` → `%20`（文件名里真的带 `%20` 四个字符），不递归解码；
      * `%2F` / `%5C` 是**编码的分隔符**，解出来会**伪造出新的路径分隔层**（根会算错）——
        出现就整段原样保留（`C:/a%2Fb` 仍是 `C:/a%2Fb`，不变成 `C:/a/b`）；
      * 解出控制字符（如 `%0A` → 换行）→ 保留原文，不产畸形项。
    解出来的**空白**（`%20`）不算畸形：它是路径内容，是否丢弃由调用方的分档规则决定。
    """

    if "%" not in text or re.search(r"%(?:2[fF]|5[cC])", text):
        return text
    try:
        decoded = urllib.parse.unquote(text, errors="strict")
    except (UnicodeDecodeError, ValueError):
        return text
    return text if any(ord(item) < 32 for item in decoded) else decoded


def _file_url_path(url: str) -> str | None:
    """把 `file://` URL 转成本地路径；不是**本机** file URL 就返回 None（不猜、不产候选）。

    规则逐条写明白，下一个人不用再猜：
      * `file:///C:/x` → `C:/x`；`file:///home/x` → `/home/x`（盘符形态去掉路径的前导斜杠）；
      * authority 为空或 `localhost` 才算本机；`file://host/share/x` 是远程主机 → 不产候选；
      * `#fragment` / `?query` 按 RFC 8089 不属于路径，先切掉；
      * 非 `file` scheme（`https://…`）根本不是本地路径 → 同样不产候选。
    """

    scheme, separator, rest = url.partition("://")
    if not separator or scheme.lower() != "file":
        return None
    rest = re.split(r"[#?]", rest, maxsplit=1)[0]
    authority, slash, path = rest.partition("/")
    if authority and authority.lower() != "localhost":
        return None
    text = "/" + path if slash else "/"
    if re.match(r"^/[A-Za-z]:(?:/|$)", text):
        text = text[1:]
    return _percent_decode(text)


def _root_before_profiles(path: str) -> str | None:
    """截出 `<root>/profiles/` 前面的那一段；没有这个片段就不是 profile 根（不猜）。"""

    segment = re.search(r"[\\/]profiles[\\/]", path)
    if segment is None:
        return None
    return path[: segment.start()]


def _plausible_home_root(candidate: str, *, allow_whitespace: bool = False) -> bool:
    """候选根必须是"一条像样的绝对路径"；畸形项按下面写明的规则丢弃。

    这不是好看问题：候选根参与 `is_under()` 判定，脏项会误导读者（以为某个根被查过）。
    丢弃规则：
      * **结构性字符**（控制字符 / 引号 / 括号 / `<` `>`）一律丢：它们在日志里是分隔符，
        出现在候选**内部**只说明切错了（任何来源都不例外）；
      * **空白按来源分档**（`allow_whitespace`）：
          - 普通路径扫描（默认 False）：候选里出现空白即丢——正则以空白为边界，切进来就是切错了；
          - URL 形态（True）：**允许**。URL 的边界由 URL 语法给出，`%20` 解出来的空格是**路径内容**
            （`C:/Users/John Doe/.dsh` 这种家目录真实存在）；因为"含空白"就丢掉整个根，
            正是本轮要消灭的「真根缺失」。
      * 含 `://` → URL 被当成路径切下来的残片（例如非 file scheme 的 `s://host/x`）；
      * 归一化后少于两个 `/` → 沿用原有形态门槛（根至少有 `<…>/<x>` 那么深）；
      * 冒号只允许在盘符位（`X:/`）：`e:///C:/…` 正是"把 `file` 的 `e` 当盘符"留下的畸形项；
        POSIX 候选的路径体里出现冒号同样是切片——两者都丢。
    """

    text = candidate.strip()
    if not text:
        return False
    if any(item in "'\"()<>" for item in text) or any(ord(item) < 32 for item in text):
        return False
    if not allow_whitespace and any(item.isspace() for item in text):
        return False
    if "://" in text:
        return False
    normalized = _norm_path(text)
    if normalized.count("/") < 2:
        return False
    drive = re.match(r"^[A-Za-z]:/", normalized)
    body = normalized[2:] if drive else normalized
    if ":" in body:
        return False
    return bool(drive) or normalized.startswith("/")


def _line_at(text: str, index: int) -> str:
    """`index` 所在的那一行（trim + 截断）：诊断里的"哪条证据"就是这一行原文。"""

    start = text.rfind(chr(10), 0, index) + 1
    end = text.find(chr(10), index)
    line = text[start:] if end < 0 else text[start:end]
    return line.strip()[:200]


def dsh_home_root_evidence(text: str = "") -> tuple[HomeRootCandidate, ...]:
    """$DSH_HOME 的候选根，**逐条带来源**：哪个根来自哪条证据。

    两种日志来源都要求"日志里真的出现 `<root>/profiles/<name>`"：
      * `log:file-url`   —— URL 形态（`file:///C:/x/profiles/…`）**单独解析**出来的本地根；
      * `log:plain-path` —— 普通路径形态（`C:\\x\\.dsh\\profiles\\…`）。
    落在 URL 区间内的普通扫描匹配一律丢弃（否则会切出畸形候选，见 `_DSH_HOME_URL` 的注释）。
    """

    candidates: list[HomeRootCandidate] = []
    env_home = os.environ.get("DSH_HOME")
    if env_home:
        candidates.append(
            HomeRootCandidate(
                root=env_home, source=HOME_ROOT_SOURCE_ENV, evidence="环境变量 DSH_HOME"
            )
        )
    candidates.append(
        HomeRootCandidate(
            root=str(Path.home() / DEFAULT_DSH_HOME_DIRNAME),
            source=HOME_ROOT_SOURCE_DEFAULT,
            evidence="$HOME/.dsh（平台默认）",
        )
    )

    url_spans: list[tuple[int, int]] = []
    for match in _DSH_HOME_URL.finditer(text):
        url_spans.append((match.start(), match.end()))
        path = _file_url_path(match.group(0))
        if path is None:
            continue
        root = _root_before_profiles(path)
        # URL 形态允许空白：%20 解出来的空格是路径内容（分档说明见 _plausible_home_root）。
        if root is None or not _plausible_home_root(root, allow_whitespace=True):
            continue
        candidates.append(
            HomeRootCandidate(
                root=root, source=HOME_ROOT_SOURCE_FILE_URL, evidence=match.group(0)[:200]
            )
        )

    for pattern in (_DSH_HOME_WINDOWS, _DSH_HOME_POSIX):
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in url_spans):
                continue  # URL 已单独解析过：它的切片不是路径（成文规则，见 _DSH_HOME_URL）
            if pattern is _DSH_HOME_POSIX and text[match.start() - 1 : match.start()] == ":":
                # 紧跟在 `:` 之后的 POSIX 路径是 **scheme 切片**：`file:///home/x` 的 `/home/x`、
                # 以及单斜杠 `file:/C:/…` 留下的 `/Users/…`（丢盘符）都是这么来的——丢掉它
                # （宁可少一个候选，也不留"缺盘符片段"）。Windows 形态**不能**套这条：
                # `file:C:/…` 里那个 `C:/…` 正是正确的根，前面也天然带着冒号。
                continue
            candidate = match.group(1)
            if not _plausible_home_root(candidate):
                continue
            candidates.append(
                HomeRootCandidate(
                    root=candidate,
                    source=HOME_ROOT_SOURCE_LOG_PATH,
                    evidence=_line_at(text, match.start()),
                )
            )

    seen: set[str] = set()
    unique: list[HomeRootCandidate] = []
    for item in candidates:
        key = _norm_path(item.root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def dsh_home_roots(text: str = "") -> tuple[str, ...]:
    """$DSH_HOME 的候选根（兼容入口）：环境变量、默认 ~/.dsh、以及日志自曝的 profile 根。

    日志来源是**从证据出发**的推断（真的出现 `<root>/profiles/<name>`），不是"文本里出现了
    profiles 这个词就算"。来源与证据见 `dsh_home_root_evidence()`——读诊断请用它，别反推。
    """

    return tuple(item.root for item in dsh_home_root_evidence(text))


def temp_roots() -> tuple[str, ...]:
    """本机临时根的候选集合：显式环境变量与平台默认值都算（少一个就会漏判）。"""

    candidates = [
        tempfile.gettempdir(),
        os.environ.get("TEMP"),
        os.environ.get("TMP"),
        os.environ.get("TMPDIR"),
    ]
    if os.name == "nt":
        candidates.append(os.path.expandvars(r"%LOCALAPPDATA%\Temp"))
        candidates.append(os.path.expandvars(r"%SystemRoot%\Temp"))
    else:
        candidates.append("/tmp")
    return _unique([item for item in candidates if item])


def is_under(path: str, roots: Iterable[str]) -> bool:
    """path 是否落在某个根之下（按归一化后的前缀判定，不是子串包含）。"""

    target = _norm_path(path)
    return any(
        target == _norm_path(root) or target.startswith(_norm_path(root) + "/") for root in roots
    )


def is_dsh_startup_scratch(path: str, temps: Iterable[str] | None = None) -> bool:
    """是不是 dsh 自己的启动临时区：系统 temp 之下，或目录名以 dsh- 开头。"""

    if Path(_norm_path(path)).name.startswith(DSH_SCRATCH_PREFIX):
        return True
    return is_under(path, temp_roots() if temps is None else temps)


def has_dsh_boot_failure(text: str) -> bool:
    return any(marker in text for marker in DSH_BOOT_FAILURE_MARKERS)


def crash_blocks(text: str) -> tuple[str, ...]:
    """切出**崩溃块**：每块 = 含启动崩溃原文的那一行 + 紧随其后的缩进续行。

    窗口取"块"的理由写在 classify_startup_denial 的 docstring 里（整篇 → N3 假跳过；
    同一行 → N4 丢真因；缩进续行是"还在同一条记录里"的可判定信号）。
    """

    lines = text.splitlines()
    blocks: list[str] = []
    for index, line in enumerate(lines):
        if not has_dsh_boot_failure(line):
            continue
        block = [line]
        for follow in lines[index + 1 :]:
            if not follow.strip() or not follow[:1].isspace():
                break  # 空行 / 不缩进的行（另一条记录或普通输出）→ 本块到此为止
            block.append(follow)
        blocks.append(chr(10).join(block))
    return tuple(blocks)


def classify_startup_denial(
    text: str,
    *,
    homes: Sequence[str] | None = None,
    temps: Sequence[str] | None = None,
) -> StartupDenial | None:
    """按**被拒路径**判断"dsh 自身起不来、是哪一类"。

    判定顺序（每一步都只承认能归因的证据，归不了因就不产生环境跳过）：
      1. 解析出的被拒路径落在 $DSH_HOME（或其 profiles 子目录）下 → profile_write_denied；
      2. 否则必须有 dsh 启动崩溃的原文，且被拒路径落在**同一个崩溃块**里、并在 dsh 自己的启动
         临时区 → other_path_denied；
      3. 其余一律返回 None：让这条闭环按失败收场，而不是被洗成 skipped。

    **第 2 步的窗口为什么是"崩溃块"**（三档都试过，只有中间这档同时满足 N3/N4）：
      * 整篇日志：会把**另一次尝试**的被拒路径读成这一次崩溃的原因——两次记录之间甚至没有空行
        （真机自己就是两行 `Error:` 紧挨着），那就是一次假的环境跳过（把 exit 1 洗成 exit 0）；
      * 同一行：真因常常写在**同一记录的下一条缩进行**上
        （`  [cause]: EPERM: …, mkdtemp '<路径>'`），只认同一行会把真因丢掉
        （把该跳过的环境限制报成失败）；
      * 崩溃块（本实现）：块 = 含崩溃原文的那一行 + 紧随其后的**缩进续行**。Node 的崩溃打印形态就是
        "消息行 + 缩进的栈帧 / `[cause]` 链 / 缩进的对象字段"，缩进是**可判定的**"还在同一条记录里"
        的信号；遇到第一行**不缩进**的内容（另一条命令的输出、`dsh exited with code 1` 这类普通行、
        空行）块就结束。块里的被拒路径才算这一次崩溃的被拒路径。
    窗口小了只可能**归不了因**（返回 None，按真失败收场），这正是本平台要的方向。
    已知缺口（照实写）：崩溃原文与被拒路径之间若被一条**不缩进**的行隔开（即使属于同一次崩溃），
    这里会归不了因 → 真失败，而不是环境跳过。

    homes/temps 可注入，供检查用例在不碰真实环境变量的前提下驱动判定（此时根证据标成
    `injected:homes`，来源字段不许留空）。
    """

    denials = denied_paths(text)
    if not denials:
        return None
    if homes is not None:
        home_roots = tuple(homes)
        home_evidence = tuple(
            HomeRootCandidate(
                root=item, source=HOME_ROOT_SOURCE_INJECTED, evidence="homes 参数注入（检查用例）"
            )
            for item in homes
        )
    else:
        home_evidence = dsh_home_root_evidence(text)
        home_roots = tuple(item.root for item in home_evidence)
    temp_root_list = tuple(temps) if temps is not None else temp_roots()
    inside_home = [item for item in denials if is_under(item.path, home_roots)]
    if inside_home:
        return StartupDenial(
            kind=PROFILE_WRITE_DENIED,
            denial=inside_home[0],
            paths=tuple(item.path for item in denials),
            home_roots=home_roots,
            home_root_evidence=home_evidence,
        )
    if not has_dsh_boot_failure(text):
        return None
    # 「启动崩溃原文」与「被拒路径」的合取限定在**同一个崩溃块**里（窗口理由见 docstring）：
    # 块 = 崩溃原文那一行 + 紧随其后的缩进续行（栈帧 / [cause] 链 / 缩进字段）。
    for block in crash_blocks(text):
        scratch = [
            item
            for item in denied_paths(block)
            if is_dsh_startup_scratch(item.path, temp_root_list)
        ]
        if scratch:
            return StartupDenial(
                kind=OTHER_PATH_DENIED,
                denial=scratch[0],
                paths=tuple(item.path for item in denials),
                home_roots=home_roots,
                home_root_evidence=home_evidence,
            )
    return None


def startup_denied_reason(denial: StartupDenial) -> str:
    """把判定写成 reason：两种状态都必须写出**是哪条路径被拒**，且不许写成规则判定。"""

    syscall = f"；拒绝系统调用：{denial.syscall}" if denial.syscall else ""
    if denial.kind == PROFILE_WRITE_DENIED:
        return (
            "dsh 自身起不来（写 profile 被环境拒绝）：受限沙箱不允许写 $DSH_HOME 下的 "
            "profiles/*.yml，dsh 在注册任何 Hook 之前就退出了。这是环境限制，"
            "不是策略判定，也不是本仓库的缺陷——但它与「Hook 起不来」是两层不同的失败，"
            f"所以单独一个状态与理由。被拒路径：{denial.path}{syscall}"
        )
    return (
        "dsh 自身起不来（$DSH_HOME 之外的路径被环境拒绝）：dsh 在注册任何 Hook 之前就退出了，"
        f"但被拒路径不在 $DSH_HOME 下，而在 dsh 自己的启动临时区——被拒路径：{denial.path}{syscall}"
        "（dsh 的 spill-local 插件启动时要 mkdtemp，系统 temp 不可写就会走到这里）。"
        "这不是「写 profile 被拒」，也不是策略判定，更不是本仓库的缺陷；"
        "不要把这条跳过读成任何一条规则判定。"
    )


def hook_workdir_missing_reason(failure: HookSpawnFailure) -> str:
    """把"工作目录不可用导致 Hook 起不来"写成 reason：写明怎么改，且**不**许说成沙箱原因。"""

    where = f"（日志写的目录：{failure.workdir}）" if failure.workdir else ""
    return (
        "Hook 进程起不来，但原因**不是**沙箱：插件理由里写明工作目录不可用"
        f"{where}——config.projectDir（或 .policy/patch.yml 的 projectDir）指向了不存在、"
        "或者不是目录的路径，插件在 spawn 之前就按失败关闭拒绝了调用。Node 的 spawn 在 cwd "
        "不存在时会把 ENOENT 归给可执行文件，所以理由里出现的 node.exe 是误导，不要据此判断"
        "「Node 没装 / 路径不对」。改成什么形态就能过：把那个目录建出来，或把 projectDir 指向"
        "真实存在的目录，再跑 python tools/dsh_sandbox_loop.py --require-dsh。"
        "这是接线/配置错误，不是环境限制（区别于「沙箱禁止管道 stdio」那一类），也不是策略判定——"
        "所以按**真失败**收场，不给环境跳过。"
    )


_ACL_WORKSPACE = re.compile(r"workspace=(?P<value>[^;\n]+)")
_ACL_TEMP = re.compile(r"temp=(?P<value>[^;\n]+)")


def _acl_root(pattern: re.Pattern[str], line: str) -> str | None:
    """从原文里取一个诊断根；**不像路径就返回 None**（畸形候选按写明规则丢弃）。

    丢弃规则只有一条：正则切出来的片段必须先是"一条像样的路径"（`_looks_like_path`）。
    宁可留空，也不把一个读不出的值写进诊断——从日志里推出来的根必须先是合法的路径
    （AGENTS 第 53 条）。
    """

    match = pattern.search(line)
    if match is None:
        return None
    value = match.group("value").strip().strip("'\"")
    return value if _looks_like_path(value) else None


def classify_acl_temp_root(text: str) -> ConfigFailure | None:
    """在一段日志里认出「ACL 临时根落在工作区内」这条**配置失败**（认不出返回 None）。

    判据是**同一行**里出现原文标记，且 `workspace=` / `temp=` 也从**这一行**解析：
    dsh 的 `throw` 把整句（含两个诊断字段）放在一行里；跨行的组合不算归因
    （与 `classify_startup_denial` 的崩溃块同一纪律：宁可让真失败保持红）。
    """

    for line in text.splitlines():
        if ACL_TEMP_ROOT_MARKER not in line:
            continue
        return ConfigFailure(
            kind=ACL_TEMP_ROOT_INSIDE_WORKSPACE,
            evidence=line.strip()[:200],
            workspace=_acl_root(_ACL_WORKSPACE, line),
            temp=_acl_root(_ACL_TEMP, line),
        )
    return None


def acl_temp_root_failure() -> ConfigFailure | None:
    """扫 dsh 的原始日志，返回第一条这条配置失败（一条都读不到就返回 None：不猜）。"""

    for text in _log_texts():
        failure = classify_acl_temp_root(text)
        if failure is not None:
            return failure
    return None


def acl_temp_root_reason(failure: ConfigFailure) -> str:
    """把「ACL 临时根落在工作区内」写成 reason：说清**改成什么形态就能过**，且不许推给环境。"""

    detail = ""
    if failure.workspace or failure.temp:
        detail = "（日志写的 workspace=" + str(failure.workspace) + "；temp=" + str(failure.temp) + "）"
    return (
        "dsh 拒绝启动：Windows ACL 沙箱要求 **ACL 临时根在工作区之外**，而这次交给它的临时根"
        "落在工作区里面" + detail + "。这是**配置**失败——临时根来自 TEMP/TMP（或本脚本的 "
        "--isolated-home），不是这台机器的限制，不是策略判定，也不是本仓库的缺陷。"
        "改成什么形态就能过：把 TEMP/TMP 指到**工作区之外**的可写目录再重跑；"
        "用 --isolated-home 时，隔离根必须留在受控项目 demo-shop 的外面"
        "（默认的 .tmp/phase-2-sandbox/dsh-tmp 就是它的兄弟目录）。"
    )


def isolated_home_env() -> dict[str, str]:
    """`--isolated-home` 要设的四条环境变量（**只给 dsh 子进程**，不改进程自己的环境）。

    两个隔离根与受控项目 demo-shop 平级：dsh 的 Windows ACL 沙箱要求临时根在工作区之外，
    把隔离根放进项目里面会被 dsh 拒绝启动（见 `classify_acl_temp_root()`）。

    **三条临时根变量都要设**：Node/libuv 在 POSIX 上**优先**读 `TMPDIR`，只有它不存在才退回
    `TMP`/`TEMP`。只设后两个时，子进程仍带着父进程的 `TMPDIR`（门禁里那是仓库内的 `.tmp/tmp`），
    隔离等于没生效——这正是模块 docstring 想避免的"系统 temp 下的 mkdtemp 被拒"场景。
    本仓库自己的工具链也是三个都设（`tools/ci_local.py` 的每个步骤子进程）。
    """

    temp = str(ISOLATED_TMP)
    return {"DSH_HOME": str(ISOLATED_HOME), "TEMP": temp, "TMP": temp, "TMPDIR": temp}


def sandbox_state(
    *, ran: bool, denial: StartupDenial | None, spawn_failure: HookSpawnFailure | None
) -> str:
    """host.sandbox 的取值（21 号 §3 的唯一新词；裁定①：**不单独设状态轴**）。

    判据是**本次运行里真的发生了什么**，不是"这台机器是什么"：

    - `ran`（审计里真的有记录 = 闭环真的跑完了）→ `unrestricted`；
    - 出现了「工作区之外的操作被沙箱 / 宿主拒绝」的证据 → `restricted`：dsh 启动期的
      `profile_write_denied` / `other_path_denied`（写 $DSH_HOME 或 dsh 自己的临时区被拒，
      19 号 §3.1 那条读数就是这一类），以及 Hook spawn 的 `sandbox_pipe_stdio_denied`
      （受限沙箱禁止命名管道，spawn 直接 EPERM）——**后者不是"写"被拒**，但它同样是"这台宿主
      在拦"，把它记成 `unrestricted` 会是一句没有依据的话；
    - 其余一律 `unknown`：dsh 找不到 / 理由读不出来 / projectDir 配错 / ACL 临时根配置失败 /
      没跑完也没有被拒证据。**unknown 不是"没有沙箱"**，是"这次没有取到事实"。
    """

    if ran:
        return reading.SANDBOX_UNRESTRICTED
    if denial is not None:
        return reading.SANDBOX_RESTRICTED
    if spawn_failure is not None and spawn_failure.kind == SANDBOX_PIPE_STDIO_DENIED:
        return reading.SANDBOX_RESTRICTED
    return reading.SANDBOX_UNKNOWN


def host_facts(*, isolated_home: bool) -> dict:
    """端到端读数专有的宿主事实（21 号 §2.4）：隔离开关 + 本次子进程实际拿到的四个环境变量。

    默认（不给 `--isolated-home`）时子进程继承父进程的环境，三个根通常在工作区之外 →
    按统一口径写成 `<outside-workspace>`；给了开关就是仓库内的 `.tmp/phase-2-sandbox/...`。
    """

    if isolated_home:
        return {
            "isolated_home": True,
            "dsh_home": reading.display_path(ISOLATED_HOME, root=REPO_ROOT),
            "temp_roots": [reading.display_path(ISOLATED_TMP, root=REPO_ROOT)],
        }
    return {
        "isolated_home": False,
        "dsh_home": reading.display_path(os.environ.get("DSH_HOME"), root=REPO_ROOT),
        "temp_roots": [
            reading.display_path(os.environ.get("TEMP"), root=REPO_ROOT),
            reading.display_path(os.environ.get("TMP"), root=REPO_ROOT),
            reading.display_path(os.environ.get("TMPDIR"), root=REPO_ROOT),
        ],
    }


def build_reading_context(
    *,
    isolated_home: bool,
    sandbox: str,
    project: Path | None,
    started_at: str,
) -> dict:
    """这份端到端读数属于哪里（21 号 §2.4）：树 / 声明 / 宿主 / 本次运行。

    它**只回答归属**：在判定链跑完之后才采集，**不进**上面任何一条判断，也不改变
    `result` / `environment_skipped` / 三族诊断键里的任何一个字。
    """

    if project is None:
        adapter_config = reading.not_applicable()
    else:
        adapter_config = reading.declaration_block(
            project / ".policy" / "dsh-adapter.yaml", root=REPO_ROOT
        )
    return reading.build(
        source=reading.SOURCE_SANDBOX_LOOP,
        tree=reading.tree_block(TREE_ROOT),
        declarations={reading.DECLARATION_ADAPTER_CONFIG: adapter_config},
        host=reading.host_block(sandbox=sandbox, extra=host_facts(isolated_home=isolated_home)),
        run=reading.run_block(started_at=started_at),
    )


def run_dsh(prompt: str, log_name: str, *, isolated_home: bool = False) -> int:
    argv = dsh_argv()
    assert argv is not None
    env = dict(os.environ)
    if isolated_home:
        # 只往**子进程**的 env 上叠加：默认（False）走不到这一支，父进程的环境一个字不动。
        env.update(isolated_home_env())
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [*argv, "--profile", "headless", "--patch", str(PROJECT / ".policy" / "patch.yml"), prompt],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    write(LOGS / log_name, completed.stdout + chr(10) + completed.stderr)
    return completed.returncode


def _log_texts() -> list[str]:
    """按文件名读全部原始日志（读不到就跳过：扫描是诊断，不是判定本身）。"""

    texts: list[str] = []
    for log in sorted(LOGS.glob("*.txt")):
        try:
            texts.append(log.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return texts


def _line_with_both(text: str, first: str, second: str) -> str:
    """返回**同一行**里同时含两个标记的那一行原文（trim + 截断；没有就返回空串）。"""

    for line in text.splitlines():
        if first in line and second in line:
            return line.strip()[:200]
    return ""


def hook_failure_seen() -> bool:
    """日志里是否出现"Hook 起不来"的原文（**任何原因**都算，读不出原因也算）。

    它回答的是"Hook 到底跑没跑"，回答不了"为什么"——分类与处置见 `hook_spawn_failure()`。
    """

    return any(HOOK_FAILURE_MARKER in text for text in _log_texts())


def hook_spawn_failure() -> HookSpawnFailure | None:
    """判断"Hook 进程起不来"是**哪一类原因**；归不了因返回 None（不猜、不跳过）。

    "审计为空"只说明 Hook 没被执行，**不说明为什么**。判据来自插件理由的文本契约
    （前缀 `policy-hook: Hook 无法执行（`，见 plugin 的 hookFailureReason）：

      1. 理由里点名工作目录不可用（`工作目录不存在：…` / `工作目录不是目录：…`）→
         HOOK_WORKDIR_UNUSABLE：插件在 spawn **之前**就按失败关闭拒绝了调用。这是**接线/配置**
         问题（projectDir 指向了不可用的目录），不是环境限制——按真失败收场。
      2. **同一行**里既出现 `Hook 无法执行`、又出现 `spawn EPERM`（新措辞写成
         `spawn 报错：spawn EPERM`，task-1 之前那种 `（spawn EPERM）` 形态同样算——判据常量
         就是较宽的那一个，两种都要能归因；但"另一行的 `spawn EPERM` + 这一行的 Hook 失败"
         **不算**：那是两件事，把它们读成因果就是假的环境跳过）→
         SANDBOX_PIPE_STDIO_DENIED：Hook 走
         `ctx.shell`（用**管道 stdio** 捕获输出），而受限沙箱禁止打开命名管道，于是 spawn
         直接 EPERM。**只有这一类**是环境限制（可环境跳过）。
      3. 其余（包括只有 `Hook 无法执行` 却读不出原因的旧日志）→ None：不猜，
         与 14 号文档 §2.2「归不了因就不跳过」同一口径。

    同一份日志里两类证据同时出现时按**更严**的一类算（工作目录不可用优先），宁可红着。

    复现（仓库外的普通 shell 里；沙箱那一类的原文形态）：
        .tmp/phase-2-sandbox/demo-shop> dsh --profile headless \
            --patch .policy/patch.yml \
            "用 edit 工具在 src/shop/order_controller.py 的 import 区加一行"
    """

    workdir_seen = False
    workdir: str | None = None
    workdir_evidence = ""
    sandbox_evidence = ""
    for text in _log_texts():
        if HOOK_FAILURE_MARKER not in text:
            continue
        marker_at = _first_marker_at(text, HOOK_WORKDIR_UNUSABLE_MARKERS)
        if marker_at is not None:
            # 工作目录这一类更严：同一份日志里不再去认沙箱证据（宁可红着）。
            workdir_seen = True
            if not workdir_evidence:
                workdir_evidence = _line_at(text, marker_at)
                clause = _HOOK_WORKDIR_CLAUSE.search(text)
                workdir = clause.group(1).strip() if clause is not None else None
            continue
        # 沙箱类必须**同一行**：跨行的组合不算归因（证据也是那一行原文，不是随便一行）。
        if not sandbox_evidence:
            sandbox_evidence = _line_with_both(
                text, HOOK_FAILURE_MARKER, SANDBOX_SPAWN_DENIED_MARKER
            )
    if workdir_seen:
        return HookSpawnFailure(
            kind=HOOK_WORKDIR_UNUSABLE, workdir=workdir, evidence=workdir_evidence
        )
    if sandbox_evidence:
        return HookSpawnFailure(kind=SANDBOX_PIPE_STDIO_DENIED, evidence=sandbox_evidence)
    return None


def _first_marker_at(text: str, markers: tuple[str, ...]) -> int | None:
    """`markers` 里第一个出现在 `text` 中的位置（一个都没有就返回 None）。"""

    hits = [text.index(marker) for marker in markers if marker in text]
    return min(hits) if hits else None


def hook_could_not_spawn() -> bool:
    """兼容包装（旧名）：与 `hook_failure_seen()` 同义——**它答不出"为什么"**。

    旧实现把它当成"沙箱禁止管道 stdio"的证据，于是 `projectDir` 配错（理由里写着
    "工作目录不存在"）也被读成环境限制。要分类、要决定能不能环境跳过，用 `hook_spawn_failure()`。
    """

    return hook_failure_seen()


def dsh_startup_denial() -> StartupDenial | None:
    """扫 dsh 的原始日志，返回第一条**可归因**的"dsh 自身起不来"（归不了因就返回 None）。

    归因按被拒路径分类，见 classify_startup_denial：落在 $DSH_HOME 下是写 profile 被拒，
    落在 dsh 自己的启动临时区（系统 temp / dsh- scratch）是另一类失败。
    两者都必须写明是哪条路径被拒；归不了因的权限错误**不产生环境跳过**。
    """

    for log in sorted(LOGS.glob("*.txt")):
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        denial = classify_startup_denial(text)
        if denial is not None:
            return denial
    return None


def dsh_could_not_start() -> bool:
    """兼容包装：是否确认"dsh 自身起不来"（具体是哪一类看 dsh_startup_denial()）。"""

    return dsh_startup_denial() is not None


def audit_records() -> list[dict]:
    path = PROJECT / ".policy" / "audit.jsonl"
    if not path.is_file():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def audit_mark() -> int:
    """本轮开始前的审计记录数：`--keep` 会保留上一轮的 `.policy/audit.jsonl`。"""

    return len(audit_records())


def new_audit_records(mark: int) -> list[dict]:
    """本轮**新增**的审计记录（本轮的判定只许用这一批）。

    `--keep` 保留上一轮审计文件时，把**整个文件**当本轮证据会同时出三个后果：
    (1) 本轮 Hook 没跑（或 edit 没发生）时 `last_governed` 返回上一轮的 block 记录，`block_ok`
        于是用一个陈旧记录给出 pass —— "这一轮没验证过"被写成"已验证"；
    (2) `if not records:` 这个门（"审计里一条记录都没有 = Hook 根本没被执行"）在 `--keep` 下
        永远打不开，受限宿主不再产生 `environment_skipped` 与对应 reason；
    (3) `sandbox_state(ran=bool(records), ...)` 会把上一轮的事实算成本轮读数。
    快照取在本轮任何 dsh 运行之前（见 `main`），三个读数因此都属于"这一轮"。
    """

    return audit_records()[mark:]


def capture_names(before: Iterable[str]) -> list[str]:
    """本轮**新增**的采集文件：与审计同一条口径（`--keep` 不把上一轮的算作本轮读数）。"""

    directory = PROJECT / ".policy" / "captures"
    if not directory.is_dir():
        return []
    known = set(before)
    return sorted(item.name for item in directory.glob("*.json") if item.name not in known)


def last_governed(records: list[dict], tool: str) -> dict | None:
    found = None
    for record in records:
        if record.get("tool") == tool and record.get("governed") is True:
            found = record
    return found


def describe(record: dict | None) -> dict:
    if record is None:
        return {}
    return {
        "event_id": record.get("event_id"),
        "request_id": record.get("request_id"),
        "tool": record.get("tool"),
        "operation": record.get("operation"),
        "file": record.get("file"),
        "layer": record.get("layer"),
        "dependencies": record.get("dependencies"),
        "decision": record.get("decision"),
        "reason_code": record.get("reason_code"),
        "exit_code": record.get("exit_code"),
        "executed": record.get("executed"),
        "matched_rules": record.get("matched_rules"),
        "payload_digest": record.get("payload_digest"),
        "rule_set_hash": record.get("rule_set_hash"),
        "timestamp": record.get("timestamp"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="重放 Phase 2 的真实 dsh 沙箱闭环")
    parser.add_argument(
        "--require-dsh",
        action="store_true",
        help="任何环境跳过（dsh 不可用 / Hook 进程起不来 / dsh 自身被环境挡住）都视为失败",
    )
    parser.add_argument("--keep", action="store_true", help="保留上一轮审计与采集")
    parser.add_argument(
        "--isolated-home",
        action="store_true",
        help=(
            "只在 dsh 子进程的 env 里把 DSH_HOME/TEMP/TMP 指到 .tmp/phase-2-sandbox 下的"
            "可写目录（默认行为不变）"
        ),
    )
    args = parser.parse_args(argv)
    # 本次运行的起始墙钟（reading_context.run.started_at 用它，**不用**载荷末尾那个 timestamp）：
    # 两处各有各的含义——一个是"这次跑从什么时候开始"，一个是"这份载荷什么时候写下来"。
    run_started_at = reading.utc_now()

    if dsh_argv() is None:
        message = "未找到 dsh 可执行文件：跳过真实沙箱闭环（本机验证项，不适合无 dsh 的环境）"
        print(message, file=sys.stderr)
        if args.require_dsh:
            return 1
        write(ARTIFACT, json.dumps(
            {
                # 最小跳过载荷与完整载荷**共用同一条版本轴**（两条写盘路径都带 schema_version）：
                # 消费者据此知道「这份读数属于哪一代形状」，而不是靠某个键在不在来猜。
                "schema_version": SANDBOX_RESULT_SCHEMA_VERSION,
                "phase": 2,
                "result": "skipped",
                "environment_skipped": True,
                "reason": message,
                # dsh 不可用也是**一条读数**：它同样要说清属于哪棵树、哪个环境。
                # 三个事实都取不到 → host.sandbox 只能是 unknown（不是"没有沙箱"）。
                "reading_context": build_reading_context(
                    isolated_home=args.isolated_home,
                    sandbox=sandbox_state(ran=False, denial=None, spawn_failure=None),
                    project=None,
                    started_at=run_started_at,
                ),
            },
            ensure_ascii=False,
            indent=2,
        ) + chr(10))
        return 0

    # 宿主版本**探测一次**：它要同时进受控项目的配置与结论载荷，两处必须同一个值。
    agent_version = host_agent_version()
    build_project(keep=args.keep, agent_version=agent_version)
    controller = PROJECT / "src" / "shop" / "order_controller.py"

    # `--keep` 保留上一轮的审计与采集：本轮只认**新增**的那一批（见 new_audit_records 的三个后果）。
    audit_start = audit_mark()
    captures_dir = PROJECT / ".policy" / "captures"
    captures_start = (
        {item.name for item in captures_dir.glob("*.json")} if captures_dir.is_dir() else set()
    )

    # ---- 场景 1：bad 编辑必须被阻断，文件哈希不变 -------------------------------
    block_before = sha256(controller)
    block_exit = run_dsh(BLOCK_PROMPT, "block-run.txt", isolated_home=args.isolated_home)
    block_after = sha256(controller)
    records = new_audit_records(audit_start)
    block_record = last_governed(records, "edit")

    block_ok = (
        block_before == block_after
        and block_record is not None
        and block_record.get("decision") == "block"
        and block_record.get("exit_code") == 2
        and RULE_ID in (block_record.get("matched_rules") or [])
        and block_record.get("executed") is False
    )

    # ---- 场景 2：good 编辑必须放行，且只发生一次预期变更 -------------------------
    allow_before = sha256(controller)
    allow_exit = run_dsh(ALLOW_PROMPT, "allow-run.txt", isolated_home=args.isolated_home)
    allow_after = sha256(controller)
    records = new_audit_records(audit_start)
    allow_record = last_governed(records, "edit")

    allow_ok = (
        allow_before != allow_after
        and "def ping" in controller.read_text(encoding="utf-8")
        and allow_record is not None
        and allow_record.get("decision") == "allow"
        and allow_record.get("exit_code") == 0
        and allow_record.get("executed") is True
        and RULE_ID in (allow_record.get("matched_rules") or [])
    )

    payload = {
        "schema_version": SANDBOX_RESULT_SCHEMA_VERSION,
        "phase": 2,
        "agent": "dsh",
        "agent_version": agent_version,
        "result": "pass" if (block_ok and allow_ok) else "fail",
        # 环境跳过 ≠ 通过：这个字段是消费者区分"已验证 / 没跑过"的唯一依据
        # （result 的取值集合保持不变，免得动到已验证过的退出码契约）。
        "environment_skipped": False,
        "block_scenario": {
            "passed": block_ok,
            "dsh_exit_code": block_exit,
            "file_sha256_before": block_before,
            "file_sha256_after": block_after,
            "audit": describe(block_record),
        },
        "allow_scenario": {
            "passed": allow_ok,
            "dsh_exit_code": allow_exit,
            "file_sha256_before": allow_before,
            "file_sha256_after": allow_after,
            "audit": describe(allow_record),
        },
        "captured_payloads": capture_names(captures_start),
        "logs": sorted(item.name for item in LOGS.glob("*.txt")),
        "timestamp": clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    # 审计里一条记录都没有 = Hook 根本没被执行。这不是策略判定结果，必须与"被规则阻断"
    # 区分开。若确认是"spawn 被沙箱拒绝"，本机就没有能力跑这条闭环：按**环境跳过**处理
    # （退出码 0 + 写明原因），因为把它报成失败会让门禁长期红着、最终被当成噪声；
    # 而伪造一个 pass 更糟——所以既不改判定，也不悄悄放过。
    if not records:
        payload["diagnosis"] = (
            "Hook 从未被调用（审计文件为空）：检查外层环境是否允许嵌套进程启动"
            "（沙箱禁止管道 stdio 时 dsh 的 ctx.shell 会 EPERM）、"
            "以及 dsh 侧是否启用了 patch.yml 的进程内转发插件"
        )
        failure = hook_spawn_failure()
        config_failure = acl_temp_root_failure()
        if config_failure is not None:
            # 配置失败排在最前：三类同时出现时，报出的是**我们自己能改**的那一件
            # （结论都是真失败，差别只在理由给得对不对——AGENTS 第 52 条）。
            payload["result"] = "fail"
            payload["environment_skipped"] = False
            payload["dsh_config_failure_kind"] = config_failure.kind
            payload["dsh_config_failure_evidence"] = config_failure.evidence
            payload["diagnosis"] = (
                "dsh 在启动期拒绝启动：Windows ACL 沙箱的临时根落在工作区之内"
                "（**配置**问题，不是环境限制，也不是策略判定）"
            )
            payload["reason"] = acl_temp_root_reason(config_failure)
            payload["reproduce"] = (
                "把 TEMP/TMP 指到**工作区之外**的可写目录再重跑："
                "python tools/dsh_sandbox_loop.py --require-dsh"
                "（用 --isolated-home 时，隔离根必须留在受控项目 demo-shop 的外面）"
            )
        elif failure is not None and failure.kind == HOOK_WORKDIR_UNUSABLE:
            # 归因是"工作目录不可用"= 接线/配置错误：**不产生环境跳过**（与 14 号文档 §2.2
            # 「归不了因就不跳过」同一口径）。洗成 skipped 会让"配错了"看起来像"这台机器不允许"，
            # 而两者要改的地方完全不同。
            payload["result"] = "fail"
            payload["environment_skipped"] = False
            payload["hook_spawn_denied_kind"] = failure.kind
            payload["hook_spawn_denied_workdir"] = failure.workdir
            payload["hook_spawn_denied_evidence"] = failure.evidence
            payload["diagnosis"] = (
                "Hook 从未被调用，理由是**工作目录不可用**（projectDir 配错）："
                "这不是沙箱拒绝，先修接线再按下面的命令重跑"
            )
            payload["reason"] = hook_workdir_missing_reason(failure)
            payload["reproduce"] = (
                "确认 config.projectDir（或 .policy/patch.yml 的 projectDir）指向存在的目录后执行："
                "python tools/dsh_sandbox_loop.py --require-dsh"
            )
        elif failure is not None:
            payload["result"] = "skipped"
            payload["environment_skipped"] = True
            payload["hook_spawn_denied_kind"] = failure.kind
            payload["hook_spawn_denied_evidence"] = failure.evidence
            payload["reason"] = (
                "Hook 进程起不来（spawn EPERM）：受限沙箱禁止管道 stdio，而 dsh 的 ctx.shell "
                "正是用管道捕获 Hook 输出。命令桥（dsh-hooks-claude-code）走同一个 ctx.shell，"
                "因此换接线方式也绕不过去——这是环境限制，不是策略判定，也不是本仓库的缺陷。"
            )
            payload["sandbox_blocked_spawn"] = True
            payload["reproduce"] = (
                "在不受限的 shell 里执行：cd .tmp/phase-2-sandbox/demo-shop && "
                "dsh --profile headless --patch .policy/patch.yml "
                "\"用 edit 工具在 src/shop/order_controller.py 的 import 区加一行 "
                "'from repository import OrderRepository'，然后一句话报告结果。\""
            )
        elif (denial := dsh_startup_denial()) is not None:
            payload["result"] = "skipped"
            payload["environment_skipped"] = True
            # 兼容字段 + 新字段：消费者既能沿用 dsh_startup_denied，也能直接读出
            # "是哪一类、哪条路径被拒"，不必从 reason 文本里猜。
            payload["dsh_startup_denied"] = True
            payload["dsh_startup_denied_kind"] = denial.kind
            payload["dsh_startup_denied_path"] = denial.path
            payload["dsh_startup_denied_paths"] = list(denial.paths)
            payload["dsh_startup_denied_syscall"] = denial.syscall
            payload["dsh_startup_denied_home_roots"] = list(denial.home_roots)
            # 「哪个根来自哪条证据」：消费者不必从 root 列表反推（env / 默认值 / URL / 普通路径）。
            payload["dsh_startup_denied_home_root_evidence"] = [
                {"root": item.root, "source": item.source, "evidence": item.evidence}
                for item in denial.home_root_evidence
            ]
            payload["reason"] = startup_denied_reason(denial)
            if denial.kind == PROFILE_WRITE_DENIED:
                payload["reproduce"] = (
                    "在不受限的 shell 里（或先把 DSH_HOME 指到可写目录）执行："
                    "python tools/dsh_sandbox_loop.py --require-dsh"
                )
            else:
                payload["reproduce"] = (
                    "在不受限的 shell 里（或先把 TEMP/TMP 指到可写目录——dsh 的 spill-local "
                    "插件在启动时要 mkdtemp）执行：python tools/dsh_sandbox_loop.py --require-dsh"
                )
        elif hook_failure_seen():
            # Hook 起不来但**读不出原因**（旧日志只有 `Hook 无法执行`，或理由被截断）：
            # 不猜、不跳过，按真失败收场；kind 写成显式的 unattributable，读者不必从结果反推。
            payload["hook_spawn_denied_kind"] = HOOK_SPAWN_UNATTRIBUTABLE
            payload["diagnosis"] = (
                "Hook 从未被调用，且日志里的「Hook 无法执行」读不出原因（既不是 `spawn EPERM`，"
                "也不是工作目录不可用）：按**真失败**收场，不猜原因、不环境跳过"
            )
            payload["reason"] = (
                "Hook 进程起不来，但日志里的理由读不出原因：既没有 `spawn 报错：spawn EPERM`"
                "（沙箱禁止管道 stdio），也没有「工作目录不存在 / 不是目录」（projectDir 配错）。"
                "归不了因就不跳过——请按日志原文核对插件版本与接线；要让它能通过，"
                "要么让插件在理由里写出原因，要么把接线恢复到真的能跑通的形态。"
            )
    # 台阶 4：reading_context 在判定链**之后**采集——它只回答"这份读数属于哪里"，
    # 不进上面任何一条判断，也不改写 result / environment_skipped / 三族诊断键里的任何一个字。
    # 这里**再读一次**日志（判定已经做完）是有意的：让这条旁注的事实来源与判定链里的局部变量
    # 解耦，而不是顺手把那些局部变量当成事实——否则"取值来自本次运行的真实读数"就成了空话。
    payload["reading_context"] = build_reading_context(
        isolated_home=args.isolated_home,
        sandbox=sandbox_state(
            ran=bool(records),
            denial=None if records else dsh_startup_denial(),
            spawn_failure=None if records else hook_spawn_failure(),
        ),
        project=PROJECT,
        started_at=run_started_at,
    )
    write(ARTIFACT, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if payload["result"] == "pass":
        return 0
    # 环境跳过默认不红（否则门禁在没 dsh / 沙箱禁止管道 stdio 的机器上长期红着，
    # 最终被当成噪声——这个教训已经记过一次）；但 --require-dsh 必须能把它判成失败：
    # 这个开关问的是"这条闭环真的在本机跑过吗"，**每一条**跳过路径都得被它覆盖。
    if payload.get("environment_skipped") is True:
        return 1 if args.require_dsh else 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

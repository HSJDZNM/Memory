"""重放 Phase 2 的真实 dsh 沙箱闭环。

它在一个受控临时项目里跑两遍真实 dsh（headless profile + 进程内策略 Hook 插件）：

    1) bad 编辑：controller 直接依赖 repository → 必须被 ARCH-001 阻断，文件哈希不变；
    2) good 编辑：新增一个方法 → 必须放行，且只发生一次预期变更。

断言失败即退出码 1；dsh 不可用、**或 Hook 进程根本起不来**（CI 的 ubuntu runner、
或沙箱禁止管道 stdio）时按**环境跳过**处理并退出码 0，因为这条闭环验证的是
"本机真实 Agent Runtime 的行为"，不是可移植的单元测试。

但"跳过"必须**可判定**、不能被读成"已验证"：两条跳过路径都在产物里写
`environment_skipped: true`，正常路径写 `false`；`--require-dsh` 让**任何**环境跳过都失败。

用法：

    python tools/dsh_sandbox_loop.py                 # 构建并跑完整闭环
    python tools/dsh_sandbox_loop.py --require-dsh   # 任何环境跳过都视为失败
    python tools/dsh_sandbox_loop.py --keep          # 保留上一轮的审计与采集，不重建项目

产物写在 .tmp/ 下（可随时删除并由本脚本重建）：

    .tmp/phase-2-sandbox/demo-shop/           受控项目（含 .policy/ 配置与审计）
    .tmp/phase-2-sandbox/logs/                dsh 的原始输出
    .tmp/artifacts/phase-2-sandbox-result.json 结构化结论（供阶段证据引用）
"""

from __future__ import annotations

import argparse
import datetime as clock
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SANDBOX = REPO_ROOT / ".tmp" / "phase-2-sandbox"
PROJECT = SANDBOX / "demo-shop"
LOGS = SANDBOX / "logs"
ARTIFACT = REPO_ROOT / ".tmp" / "artifacts" / "phase-2-sandbox-result.json"

AGENT_VERSION = "0.1.5-rc.1"
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


def build_project(*, keep: bool) -> None:
    """重建受控项目；--keep 时只重置被治理的源文件，保留审计与采集。"""

    (PROJECT / "src" / "shop").mkdir(parents=True, exist_ok=True)
    (PROJECT / ".policy").mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

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
        ADAPTER_CONFIG.format(agent_version=AGENT_VERSION, repo=REPO_ROOT.as_posix()),
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


# 进程内 Hook 插件在 spawn 被拒时的原文（见 src/adapters/dsh/policy-hook.plugin.mjs 的
# catch 分支）。它出现的唯一含义是"Hook 进程起不来"，与策略判定无关。
SPAWN_DENIED_MARKERS = ("spawn EPERM", "Hook 无法执行")

# dsh **自己**还没起来就被环境挡住时的原文：受限沙箱不允许写 $DSH_HOME 下的 profile。
# 与 SPAWN_DENIED_MARKERS 是两件事：那边是"dsh 起来了、Hook 起不来"，这边是
# "dsh 连 profile 都写不进去、进程直接退出"。两者都属于环境限制，不是策略判定结果；
# 区别在于诊断要说清是"哪一层没起来"，否则会把 dsh 装不起来误读成治理失效。
DSH_STARTUP_DENIED_MARKERS = ("EPERM: ", "EACCES: ", "WinError 5")
DSH_HOME_MARKERS = ("profiles", "cordis", ".dsh", "dsh-home")


def run_dsh(prompt: str, log_name: str) -> int:
    argv = dsh_argv()
    assert argv is not None
    env = dict(os.environ)
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


def hook_could_not_spawn() -> bool:
    """判断"审计为空"是不是因为 Hook 进程根本起不来（而不是策略判定或别的失败）。

    本机实测的机制：Hook 走 `ctx.shell`（dsh 的 shell 服务），它用**管道 stdio** 捕获
    Hook 的输出；而受限沙箱禁止打开命名管道，于是 spawn 直接 EPERM。进程内插件把这个
    异常翻译成 deny（失败关闭），模型看到的是"拒绝调用"，审计里则什么都没有——
    与"被 ARCH-001 阻断"是两件完全不同的事，必须区分开，否则会把它当成策略结论。

    复现（仓库外的普通 shell 里）：
        .tmp/phase-2-sandbox/demo-shop> dsh --profile headless \
            --patch .policy/patch.yml "用 edit 工具在 src/shop/order_controller.py 的 import 区加一行"
    """

    for log in sorted(LOGS.glob("*.txt")):
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(marker in text for marker in SPAWN_DENIED_MARKERS):
            return True
    return False


def dsh_could_not_start() -> bool:
    """判断"审计为空"是不是因为 dsh 自己都没起来（受限沙箱不许它写 $DSH_HOME 下的 profile）。

    本机实测：默认 DSH_HOME 下 dsh 以退出码 1 结束，日志里是
    `EPERM: C:\\Users\\ZNM\\.dsh\\profiles\\headless\\cordis.yml`——连启动都没完成。
    这与"被规则阻断""Hook 起不来"都是不同的结论，所以诊断必须分开写。

    判据刻意收紧：既要出现权限被拒的原文，又要同时指向 dsh 自己的配置路径，
    避免把日志里其它无关的 EPERM 误判成环境跳过（误判会把真失败洗成 skipped）。
    """

    for log in sorted(LOGS.glob("*.txt")):
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not any(marker in text for marker in DSH_STARTUP_DENIED_MARKERS):
            continue
        if any(token in text for token in DSH_HOME_MARKERS):
            return True
    return False


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
        help="任何环境跳过（dsh 不可用，或 Hook 进程起不来）都视为失败",
    )
    parser.add_argument("--keep", action="store_true", help="保留上一轮审计与采集")
    args = parser.parse_args(argv)

    if dsh_argv() is None:
        message = "未找到 dsh 可执行文件：跳过真实沙箱闭环（本机验证项，不适合无 dsh 的环境）"
        print(message, file=sys.stderr)
        if args.require_dsh:
            return 1
        write(ARTIFACT, json.dumps(
            {
                "phase": 2,
                "result": "skipped",
                "environment_skipped": True,
                "reason": message,
            },
            ensure_ascii=False,
            indent=2,
        ) + chr(10))
        return 0

    build_project(keep=args.keep)
    controller = PROJECT / "src" / "shop" / "order_controller.py"

    # ---- 场景 1：bad 编辑必须被阻断，文件哈希不变 -------------------------------
    block_before = sha256(controller)
    block_exit = run_dsh(BLOCK_PROMPT, "block-run.txt")
    block_after = sha256(controller)
    records = audit_records()
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
    allow_exit = run_dsh(ALLOW_PROMPT, "allow-run.txt")
    allow_after = sha256(controller)
    records = audit_records()
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
        "phase": 2,
        "agent": "dsh",
        "agent_version": AGENT_VERSION,
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
        "captured_payloads": sorted(
            item.name for item in (PROJECT / ".policy" / "captures").glob("*.json")
        )
        if (PROJECT / ".policy" / "captures").is_dir()
        else [],
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
        if hook_could_not_spawn():
            payload["result"] = "skipped"
            payload["environment_skipped"] = True
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
        elif dsh_could_not_start():
            payload["result"] = "skipped"
            payload["environment_skipped"] = True
            payload["reason"] = (
                "dsh 自身起不来（写 profile 被环境拒绝）：受限沙箱不允许写 $DSH_HOME 下的 "
                "profiles/*.yml，dsh 在注册任何 Hook 之前就退出了。这是环境限制，"
                "不是策略判定，也不是本仓库的缺陷——但它与「Hook 起不来」是两层不同的失败，"
                "所以单独一个状态与理由。"
            )
            payload["dsh_startup_denied"] = True
            payload["reproduce"] = (
                "在不受限的 shell 里（或先把 DSH_HOME 指到工作区内）执行："
                "python tools/dsh_sandbox_loop.py --require-dsh"
            )
    write(ARTIFACT, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if payload["result"] == "pass":
        return 0
    # 环境跳过默认不红（否则门禁在没 dsh / 沙箱禁止管道 stdio 的机器上长期红着，
    # 最终被当成噪声——这个教训已经记过一次）；但 --require-dsh 必须能把它判成失败：
    # 这个开关问的是"这条闭环真的在本机跑过吗"，两条跳过路径都得被它覆盖。
    if payload.get("environment_skipped") is True:
        return 1 if args.require_dsh else 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

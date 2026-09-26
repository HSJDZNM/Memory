"""单技术：dsh Hook 内部流程：tech-detail 讲解 notebook 的纯 Python 版本。

由 docs/project/architecture/tech-detail/build_notebooks.py 生成，内容与同名的
.ipynb 逐字相同（那份里每段代码也是一个单元）。直接运行本文件即可复现全部输出：

    python docs/project/architecture/tech-detail/02-dsh-Hook-内部流程/02-dsh-Hook-内部流程.py

内容改动请修改同目录的 cells.py 后重新生成，不要直接编辑本文件。
"""

# ----------------------------------------------------------------------------
# # 02 dsh Hook 内部流程
#
# 这份 notebook 配合同名图 `02-dsh-Hook-内部流程.drawio`。图回答一个问题——**Agent 想在工具执行之前调用一次策略判定，
# 这一次判定是怎么走完的**。notebook 把图上的九步逐步跑一遍，并把它最要命的那条前提验证清楚。
#
# | 步骤 | 图上节点（第二行锚点） | 本 notebook 里的代码锚点 |
# | --- | --- | --- |
# | 1 | dsh 调用 Hook · stdin JSON | `sys.stdin`（本 notebook 用同样的 JSON 喂 CLI） |
# | 2 | 接线自检 · 内部预算 5000ms < hooks.json 超时 30s | `adapters.dsh.hooks.check_wiring` |
# | 3 | 事件映射 · adapter.py → 标准事件 | `to_policy_event` / `to_policy_context` |
# | 4 | 工具表白名单 · 未登记 / mcp__ 前缀 → 阻断 | `ADAPTER.TOOL_TABLE` |
# | 5 | 路径范围校验 · 归一化后必须落在受控项目内 | `_resolve_file` / `repo_relative_path` |
# | 6 | 平台判定 · policy.engine.evaluate（+ Phase 5 证据） | `policy.engine.evaluate` |
# | 7 | exit 0 放行 / exit 2 阻断 · 发生在工具执行之前 | `EXIT_ALLOW` / `EXIT_BLOCK` |
# | 8 | 审计写回 · JSONL 摘要；不可写 → 失败关闭 | `AuditLedger`（追加写 JSONL） |
# | 9 | PostToolUse · 只做 post-check，不再调 callback | `post_execute_outcome` |
#
# **这条链路的前提是一句反直觉的话**：dsh 那边"退出码 1 / 崩溃 / 被超时杀掉 / hooks.json 读不到"
# 全都等于**放行**（依据 `src/adapters/dsh/README.md` 第 2.3、2.5 节）。所以失败关闭不可能由 dsh 提供，
# 只能由 Hook 自己保证——这是图右侧那个红框，也是本 notebook 反复验证的一条。
#
# **本机没有装 dsh 也不影响阅读**：Hook 是**外部命令**，与 dsh 之间只有"stdin 上的 JSON + 退出码"两样东西。
# notebook 直接构造那份 JSON、直接调用 CLI，测的就是真实接线后的同一段代码，不会假装跑过一个真实 Agent。
# ----------------------------------------------------------------------------

# 先找到仓库根目录：notebook 可能从仓库根启动，也可能从本目录启动，两种都要能跑。
import json
import sys
from collections import Counter
from pathlib import Path


def find_repo_root(start):
    """往上找：同时有 pyproject.toml 与 src/policy/ 的那一层就是仓库根。"""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "policy").is_dir():
            return candidate
    raise SystemExit("没有找到仓库根目录（需要 pyproject.toml 与 src/policy/）")


REPO_ROOT = find_repo_root(Path.cwd())
for extra in (REPO_ROOT / "src", REPO_ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

# 本 notebook 独占的临时目录：受控项目、配置、审计都写在它下面。
TEMP = REPO_ROOT / ".tmp" / "tech-detail" / "02"
TEMP.mkdir(parents=True, exist_ok=True)

import yaml

from adapters.dsh import adapter as dsh_adapter
from adapters.dsh.adapter import (
    DSH_AGENT_ID,
    REQUIRED_PAYLOAD_FIELDS,
    SUPPORTED_HOOK_EVENTS,
    TOOL_TABLE,
    DshEventError,
    load_config,
    to_policy_context,
    to_policy_event,
)
from adapters.dsh.hooks import (
    EXIT_ALLOW,
    EXIT_BLOCK,
    AuditLedger,
    ExecutionOutcome,
    check_wiring,
    run_hook,
    sanitize,
)
from policy.engine import evaluate
from policy.loader import load_rule_set
from policy.models import Decision, PolicyContextError, SCHEMA_VERSION

# 脱敏 fixture：Phase 2 契约测试的输入，也是本 notebook 的输入（占位路径在下面被换成真实临时目录）。
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "dsh"
PLACEHOLDER_POSIX = "/workspace/demo-shop"
PLACEHOLDER_WINDOWS = "C:" + chr(92) + "workspace" + chr(92) + "demo-shop"

# 受控项目：Hook 只对它做路径归一化，不读文件内容；PostToolUse 那一段会真的往它里面写文件。
PROJECT_ROOT = TEMP / "demo-shop"
(PROJECT_ROOT / "src" / "shop").mkdir(parents=True, exist_ok=True)


def fresh(path):
    """每次运行都从空审计开始：审计文件同时是幂等台账，上一次运行的 event_id 会被判成重放。"""
    for candidate in (path, path.with_name(path.stem + ".enforcement-ledger" + path.suffix)):
        if candidate.exists():
            candidate.unlink()
    return path


def rebase(value):
    """把 fixture 里的占位路径换成真实的临时项目根：fixture 自己不含任何本机路径。"""
    if isinstance(value, str):
        return value.replace(PLACEHOLDER_POSIX, PROJECT_ROOT.as_posix()).replace(
            PLACEHOLDER_WINDOWS, str(PROJECT_ROOT)
        )
    if isinstance(value, dict):
        return {key: rebase(item) for key, item in value.items()}
    if isinstance(value, list):
        return [rebase(item) for item in value]
    return value


def event(name, **overrides):
    """读一条脱敏 fixture，换成真实路径，再套用本次的覆盖字段。"""
    payload = rebase(json.loads((FIXTURES / name).read_text(encoding="utf-8")))
    payload.update(overrides)
    return payload


def write_config(path, **overrides):
    """写一份 adapter 配置：layer / language / principal 只能显式声明，绝不从文件名推断。"""
    document = {
        "agent_version": "0.1.5-rc.1",
        "project": "demo-shop",
        "project_root": str(PROJECT_ROOT),
        "rules": [str(REPO_ROOT / "policies")],
        "rules_root": str(REPO_ROOT),
        # 内部预算：必须严格小于 hooks.json 里的 timeout（第二步就是验证这条不等式）。
        "timeout_ms": 5000,
        "layers": [
            {"pattern": "**/*_controller.py", "layer": "controller"},
            {"pattern": "**/*_service.py", "layer": "service"},
            {"pattern": "**/*_repository.py", "layer": "repository"},
        ],
        "languages": [{"pattern": "**/*.py", "language": "python"}],
        "audit_log": str(path.parent / "audit.jsonl"),
        # 受控执行需要的三样东西：主体、工具注册表、已审核哈希清单。
        "principal": {"subject": "local-user", "roles": ["developer"]},
        "registry": str(REPO_ROOT / "registry" / "tool-registry.yaml"),
        "registry_approved": str(REPO_ROOT / "registry" / "tool-registry.approved.json"),
    }
    document.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


CONFIG_PATH = write_config(TEMP / "config" / "dsh-adapter.yaml")
CONFIG = load_config(CONFIG_PATH)
RULES = load_rule_set(CONFIG.rule_dirs, repo_root=CONFIG.rule_anchor)

kinds = Counter(spec.kind.value for spec in TOOL_TABLE.values())
print("仓库根目录:", REPO_ROOT.name)
print("临时目录:", TEMP.relative_to(REPO_ROOT).as_posix(), "| 受控项目:", PROJECT_ROOT.name)
print("退出码契约: exit", EXIT_ALLOW, "= 放行；exit", EXIT_BLOCK, "= 阻断（stderr 即理由）")
print("承认的 hook 事件:", list(SUPPORTED_HOOK_EVENTS))
print("载荷必需字段:", list(REQUIRED_PAYLOAD_FIELDS))
print("工具表:", len(TOOL_TABLE), "个工具 |", dict(sorted(kinds.items())))
print("规则集:", len(RULES), "条规则 | 决策协议:", SCHEMA_VERSION, "| Agent:", DSH_AGENT_ID)
print("内部预算:", CONFIG.timeout_ms, "ms（hooks.json 里写 30s，第二步核对这条不等式）")

# 四条约定的断言：退出码、事件白名单、工具表是白名单、内部预算严格更小。
assert (EXIT_ALLOW, EXIT_BLOCK) == (0, 2)
assert SUPPORTED_HOOK_EVENTS == ("PreToolUse", "PostToolUse"), SUPPORTED_HOOK_EVENTS
assert "mcp__github__create_issue" not in TOOL_TABLE
assert CONFIG.timeout_ms < 30 * 1000
print()
print("提示: 这一单元没有任何网络与外部命令，输出应当立刻出现。")

# 表格对齐用的小工具：中文（全角）字符在等宽字体里占 2 列，而 f"{文本:<10}"
# 数的是"字符个数"——中英混排时列会被挤歪。按显示宽度补空格才是对的。
import unicodedata


def display_width(text):
    """文本在等宽字体里占多少列：全角/宽字符算 2 列，其余算 1 列。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(text))


def pad(text, width, align="left"):
    """按显示宽度把文本补齐到 width 列，让每一列都从同一个位置开始。"""
    text = str(text)
    blanks = " " * max(0, width - display_width(text))
    if align == "right":
        return blanks + text
    if align == "center":
        left = len(blanks) // 2
        return blanks[:left] + text + blanks[left:]
    return text + blanks

# ----------------------------------------------------------------------------
# ## 1. dsh 送来的事件长什么样（第 1、3 步）
#
# Hook 是**外部命令**：dsh 把事件 JSON 写进它的 stdin，读它的退出码。载荷的形状由两部分组成——
#
#     session_id / transcript_path / cwd / hook_event_name     事件基座
#     tool_name / tool_input / tool_use_id                     工具字段
#
# 两个容易忽略的细节：`transcript_path` 在 dsh 里恒为空串（仍然保留，它是协议的一部分）；
# PreToolUse 拿到的路径是**未解析的原始字符串**，相对路径要靠载荷里的 `cwd` 才能变成绝对路径。
#
# 映射之后得到两个对象：
#
# | 对象 | 是什么 | 关键字段 |
# | --- | --- | --- |
# | `PolicyEvent` | 规范化后的标准事件 | event_id、operation、file、layer、language、dependencies、payload_digest |
# | `PolicyContext` | 核心引擎的输入 | request_id、project、agent、operation、file、layer、language、principal |
#
# 图上把这个位置写成 `AgentEvent`（Phase 6 的规范事件类型名）；dsh 这条链路的实际产物是
# `PolicyEvent`（Phase 2 的类型），本 notebook 以源码为准。`payload_digest` 只记参数指纹、
# `payload_fields` 只记参数**名字**：审计能关联到同一次调用，又不会把源码内容写进证据文件。
# ----------------------------------------------------------------------------

# 第 3 步：dsh 事件 -> PolicyEvent -> PolicyContext。字段来源逐项可查。
admission = to_policy_event(event("pre-tool-use-edit-block.json"), config=CONFIG)
mapped = admission.event
mapped_context = to_policy_context(mapped, config=CONFIG)

rows = (
    ("event_id", "session_id + tool_use_id", mapped.event_id),
    ("kind", "适配器固定值", mapped.kind),
    ("agent", "适配器固定标识", mapped.agent),
    ("tool", "载荷 tool_name", mapped.tool),
    ("operation", "工具表（edit -> edit）", mapped.operation.value),
    ("file", "工具参数 + 载荷 cwd", mapped.file),
    ("layer", "adapter 配置的 layers", mapped.layer),
    ("language", "adapter 配置的 languages", mapped.language),
    ("dependencies", "本次变更文本里的 import", ",".join(mapped.dependencies)),
    ("payload_digest", "参数摘要（不落原文）", mapped.payload_digest[:22] + "..."),
    ("payload_fields", "参数名（只记名字）", ",".join(mapped.payload_fields)),
    ("principal", "adapter 配置（绝不推断）", str(mapped_context.principal)),
    ("module", "刻意留空", str(mapped_context.module)),
)
print(pad("字段", 18) + pad("来源", 28) + "值")
print("-" * 116)
for name, source, value in rows:
    print(pad(name, 18) + pad(source, 28) + str(value))

assert admission.governed is True and mapped.kind == "tool.pre_execute"
assert mapped.agent == DSH_AGENT_ID == "dsh"
assert mapped.file == "src/shop/order_controller.py" and mapped.layer == "controller"
# 依赖登记的是**完整点分路径**，不是只留顶层名字：`from shop.order_repository import X` 只留 `shop`
# 就等于结构性放行（那正是 G6 的绕过写法）。预执行路径拿到的是变更片段、没有模块索引，
# 分不清"被导入的名字是子模块还是类/函数"，所以候选一起登记 —— 方向是失败关闭：
# 多登记只可能更早阻断，漏登记才是放行。
assert mapped.dependencies == (
    "repository",
    "repository.orderrepository",
    "service",
    "service.orderservice",
), mapped.dependencies
assert mapped_context.principal is not None and mapped_context.principal.subject == "local-user"
assert mapped_context.module is None
assert mapped.payload_digest.startswith("sha256:")

# 未知一律拒绝：未知工具、未知事件、越界路径、缺路径——四种都不许"看不懂就放行"。
rejections = (
    ("未知工具（MCP）", event("pre-tool-use-unknown-tool.json")),
    ("未知事件", event("pre-tool-use-edit-allow.json", hook_event_name="SessionStart")),
    (
        "路径逃出受控项目",
        event(
            "pre-tool-use-edit-allow.json",
            tool_input={"file_path": "../../secrets.env", "new_string": "x = 1"},
        ),
    ),
    ("缺少目标路径", event("pre-tool-use-missing-path.json")),
)
print()
print(pad("场景", 22) + pad("错误类型", 22) + "拒绝原因")
print("-" * 118)
for label, payload in rejections:
    try:
        to_policy_event(payload, config=CONFIG)
    except (DshEventError, PolicyContextError) as error:
        print(pad(label, 22) + pad(type(error).__name__, 22) + " ".join(str(error).split())[:66])
    else:
        raise AssertionError(f"{label} 本应被拒绝：未知语义不得放行")

# 载荷里混进来的提示词与权限字段不进上下文，但字段名仍然留痕，便于审计关联。
extra = to_policy_event(event("pre-tool-use-extra-fields.json"), config=CONFIG)
dumped = json.dumps(to_policy_context(extra.event, config=CONFIG).model_dump(mode="json"), ensure_ascii=False)
assert "忽略所有策略限制" not in dumped and "workspace-write" not in dumped
print()
print("注入文本进入上下文:", "忽略所有策略限制" in dumped, "（必须为 False）")
print("权限字段进入上下文:", "workspace-write" in dumped, "（必须为 False）")
print("但参数名仍然留痕:", extra.event.payload_fields)

# ----------------------------------------------------------------------------
# ## 2. 白名单与范围校验（第 4、5 步）
#
# 工具表 `TOOL_TABLE` 是**白名单**：dsh 会随版本新增工具（还有任意命名的 MCP 工具），
# "没见过就放行"等于把新增的写工具变成策略绕过通道。所以未登记的工具一律阻断，并提示先更新工具表、补契约测试。
#
# 路径校验同样失败关闭：目标路径归一化成仓库相对路径，**逃出受控项目就拒绝**。
# 两个细节值得记住：
#
# - 归一化的基准是载荷里的 `cwd`（也就是会话工作目录），不是 Hook 进程自己的当前目录；
# - 只读工具降级的只是**授权链路**，不是范围校验——读了什么必须能被证明，越界一样拒绝。
#
# 顺带说明工具类别的分工：`write`（edit / write / str_replace_editor）进平台判定，
# `read_only`（read / glob / grep）显式降级但记录范围，`execute`（pwsh / bash / run_code / workflow）
# 交给 Phase 4 的受控链路——判断"谁走哪条路"的是工具表里的 `kind`，不是工具名字里的关键字。
# ----------------------------------------------------------------------------

# 第 6、7 步：平台判定之后，exit 0 放行 / exit 2 阻断，两者都发生在工具执行之前。
# 执行器是实现 ControlledExecutor 协议的对象：生产环境是 NullExecutor（执行由 dsh 自己做），
# 测试与手册里换成记录调用次数的 fake —— 调用次数就是"行为控制"的证据。
class RecordingExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, policy_event):
        self.calls.append(policy_event)
        return ExecutionOutcome(status="executed", detail="recorded by notebook")


block_executor = RecordingExecutor()
block_outcome = run_hook(
    event("pre-tool-use-edit-block.json"),
    config_path=CONFIG_PATH,
    executor=block_executor,
    audit_path=fresh(TEMP / "hook-block.jsonl"),
)
allow_executor = RecordingExecutor()
ALLOW_AUDIT = fresh(TEMP / "hook-allow.jsonl")
allow_outcome = run_hook(
    event("pre-tool-use-edit-allow.json"),
    config_path=CONFIG_PATH,
    executor=allow_executor,
    audit_path=ALLOW_AUDIT,
)

outcomes = (("block 场景", block_outcome, len(block_executor.calls)), ("allow 场景", allow_outcome, len(allow_executor.calls)))
print(pad("场景", 14) + pad("退出码", 10) + pad("原因码", 22) + pad("执行器调用", 14) + "stderr")
print("-" * 108)
for label, outcome, calls in outcomes:
    stderr = "有（即阻断理由）" if outcome.stderr else "空"
    print(pad(label, 14) + pad(outcome.exit_code, 10) + pad(outcome.reason_code, 22) + pad(calls, 14) + stderr)

assert block_outcome.exit_code == EXIT_BLOCK == 2 and block_outcome.decision.decision is Decision.BLOCK
assert allow_outcome.exit_code == EXIT_ALLOW == 0
assert len(block_executor.calls) == 0 and len(allow_executor.calls) == 1
assert "ARCH-001@1" in block_outcome.stderr and allow_outcome.stderr == ""

print()
print("阻断时写给模型看的理由（工具还没有执行过）:")
print(block_outcome.stderr)
print()
print("允许时执行器拿到的依赖:", allow_executor.calls[0].dependencies)

# 允许路径在审计里还留下了 Phase 4 的授权凭据（绑定 action_hash、短时效、单次使用）。
allow_records = [json.loads(line) for line in ALLOW_AUDIT.read_text(encoding="utf-8").splitlines() if line.strip()]
grant = next(item for item in allow_records if item.get("reason_code") == "enforcement_allow")
print()
print("审计里的原因码:", ", ".join(str(item.get("reason_code")) for item in allow_records))
for name in ("tool_id", "risk", "action_hash", "grant_id"):
    print("  " + pad(name, 14) + str(grant[name]))
assert grant["risk"] in {"read_only", "reversible_write", "destructive_write", "external", "privileged"}
assert any(item.get("reason_code") == "allow" for item in allow_records)

# ----------------------------------------------------------------------------
# ## 3. 失败关闭靠自己（图右侧的红框）
#
# 因为 dsh 把"退出码 1 / 崩溃 / 被超时杀掉 / 配置读不到"都当放行，Hook 必须自己保证三件事（第 4 节的做法）：
#
# 1. **内部预算严格小于 Agent 侧超时**：配置写 `timeout_ms: 5000`，hooks.json 写 `timeout: 30`；
#    判定超预算时自己判阻断。反过来的话 dsh 会先杀进程，而被杀等于放行；
# 2. **任何异常都转成退出码 2**：连 stdin 不是合法 JSON 也一样，绝不让解释器以退出码 1 结束；
# 3. **接线自检**：hooks.json 不存在 / 不可解析 / 没指向本 Hook / 超时不等式不满足，一律阻断并给出可诊断信息。
#
# 下面把六条失败路径各跑一次，全部应当阻断（exit 2），并且每条都要给出原因码：
# 未知工具、未知事件、越界路径、判定超时、重放同一次调用，以及**上一次已经放行过的那次调用再来一遍**。
# ----------------------------------------------------------------------------

# 失败关闭矩阵：每一条都必须 exit 2（工具不会执行），并且给得出原因码与细节。
import time

unknown_tool = run_hook(
    event("pre-tool-use-unknown-tool.json"),
    config_path=CONFIG_PATH,
    audit_path=fresh(TEMP / "fc-unknown.jsonl"),
)
unknown_event = run_hook(
    event("pre-tool-use-edit-allow.json", hook_event_name="SessionStart"),
    config_path=CONFIG_PATH,
    audit_path=fresh(TEMP / "fc-event.jsonl"),
)
escaped = run_hook(
    event(
        "pre-tool-use-edit-allow.json",
        tool_input={"file_path": "../../secrets.env", "new_string": "x = 1"},
    ),
    config_path=CONFIG_PATH,
    audit_path=fresh(TEMP / "fc-escape.jsonl"),
)


# 超时：内部预算压到 50ms，判定故意慢下来——预算必须先在 Hook 内部触发。
def slow_evaluator(rules, context):
    time.sleep(0.3)
    return evaluate(rules, context)


slow_config = write_config(TEMP / "config" / "slow.yaml", timeout_ms=50)
slow_executor = RecordingExecutor()
timeout_outcome = run_hook(
    event("pre-tool-use-edit-block.json"),
    config_path=slow_config,
    executor=slow_executor,
    evaluator=slow_evaluator,
    audit_path=fresh(TEMP / "fc-timeout.jsonl"),
)

# 重放：审计文件同时是幂等台账，键是 event_id。第一次放行，第二次必须阻断。
REPLAY_AUDIT = fresh(TEMP / "fc-replay.jsonl")
replay_executor = RecordingExecutor()
replay_first = run_hook(
    event("pre-tool-use-edit-allow.json"),
    config_path=CONFIG_PATH,
    executor=replay_executor,
    audit_path=REPLAY_AUDIT,
)
replay_second = run_hook(
    event("pre-tool-use-edit-allow.json"),
    config_path=CONFIG_PATH,
    executor=replay_executor,
    audit_path=REPLAY_AUDIT,
)

cases = (
    ("未知工具", unknown_tool),
    ("未知事件", unknown_event),
    ("越界路径", escaped),
    ("判定超时", timeout_outcome),
    ("重放 event_id", replay_second),
)
print(pad("失败路径", 18) + pad("退出码", 8) + pad("原因码", 20) + "写给模型的细节")
print("-" * 118)
for label, outcome in cases:
    detail = next((line for line in outcome.stderr.splitlines() if line.startswith("detail:")), "")
    print(pad(label, 18) + pad(outcome.exit_code, 8) + pad(outcome.reason_code, 20) + detail[8:78])

for label, outcome in cases:
    assert outcome.exit_code == EXIT_BLOCK, (label, outcome.exit_code, outcome.reason_code)
assert {outcome.reason_code for _, outcome in cases} == {
    "context_error",
    "policy_timeout",
    "event_replay",
}, sorted(outcome.reason_code for _, outcome in cases)
assert replay_first.exit_code == EXIT_ALLOW and len(replay_executor.calls) == 1
assert len(slow_executor.calls) == 0
print()
print("重放: 第一次 exit", replay_first.exit_code, "；第二次 exit", replay_second.exit_code,
      "；执行器总共被调用", len(replay_executor.calls), "次")
print("超时路径的执行器调用", len(slow_executor.calls), "次：超预算一律阻断，绝不放行。")

# ----------------------------------------------------------------------------
# ## 4. 接线自检与"退出码就是接口"（第 2、8 步）
#
# dsh 在 hooks.json **读不到时不注册任何 hook，也不报错**，Agent 照常启动——这是一条最危险的静默失效路径。
# 所以运行期必须自己确认：hooks.json 存在、里面真的有指向 `adapters.dsh.hooks` 的命令、
# 并且它的 `timeout` 严格大于 Hook 的内部预算。
#
# 命令行契约还有一条容易被忽略的细节：**放行时 stdout 必须为空**。
# dsh 只在 exit 0 且 stdout 以 `{` 开头时才把它当结构化输出解析，所以 Hook 把所有诊断都写 stderr。
#
# 下面这段起真正的子进程跑 `python -m adapters.dsh.hooks`——命令与接线上写的一模一样，
# 再读回审计 JSONL，核对它只留结论与摘要、不留源码内容。
# ----------------------------------------------------------------------------

# 第 2、8 步：接线自检 + CLI 退出码 + 审计内容。
import os
import subprocess

GOOD_HOOKS = TEMP / "hooks-good.json"
BAD_TIMEOUT_HOOKS = TEMP / "hooks-bad-timeout.json"
NO_COMMAND_HOOKS = TEMP / "hooks-no-command.json"


def hooks_document(timeout, command):
    """hooks.json 的最小形状：matcher 留空（匹配全部工具），command 指向本 Hook。"""
    return {
        "hooks": {
            "PreToolUse": [
                {"matcher": "", "hooks": [{"type": "command", "command": command, "timeout": timeout}]}
            ]
        }
    }


def write_hooks(path, timeout, command):
    path.write_text(json.dumps(hooks_document(timeout, command), ensure_ascii=False), encoding="utf-8")
    return path


GOOD = write_hooks(GOOD_HOOKS, 30, "python -m adapters.dsh.hooks --config " + str(CONFIG_PATH))
BAD_TIMEOUT = write_hooks(BAD_TIMEOUT_HOOKS, 3, "python -m adapters.dsh.hooks --config " + str(CONFIG_PATH))
NO_COMMAND = write_hooks(NO_COMMAND_HOOKS, 30, "python -c pass")

wiring_cases = (
    ("hooks.json 正常", GOOD, ""),
    ("timeout 只有 3s", BAD_TIMEOUT, "不大于内部预算"),
    ("命令没指向本 Hook", NO_COMMAND, "没有指向 adapters.dsh.hooks"),
    ("hooks.json 不存在", TEMP / "nope.json", "不存在"),
)
print(pad("接线情形", 24) + "自检结论")
print("-" * 108)
for label, path, expected in wiring_cases:
    report = check_wiring(CONFIG, hooks_config_path=path)
    print(pad(label, 24) + (report[:76] if report else "通过（运行期接线正常）"))
    assert expected in report, (label, report)

# 接线坏了连"本来会放行"的事件也要阻断：配置事故不得降级成放行。
bad_wired = run_hook(
    event("pre-tool-use-edit-allow.json"),
    config_path=CONFIG_PATH,
    hooks_config_path=BAD_TIMEOUT_HOOKS,
    audit_path=fresh(TEMP / "fc-wiring.jsonl"),
)
assert bad_wired.exit_code == EXIT_BLOCK and bad_wired.reason_code == "wiring_error"
print()
print("接线不等式不满足时，合规事件也被阻断:", bad_wired.exit_code, bad_wired.reason_code)


# 真正的 CLI：本机没装 dsh 也能跑，因为 stdin 上那份 JSON 就是 dsh 会写进去的东西。
def run_hook_cli(arguments, stdin_text):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "adapters.dsh.hooks", *arguments],
        cwd=str(REPO_ROOT),
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )


self_check_ok = run_hook_cli(
    ["--config", str(CONFIG_PATH), "--hooks-config", str(GOOD), "--self-check"], ""
)
self_check_bad = run_hook_cli(
    ["--config", str(CONFIG_PATH), "--hooks-config", str(BAD_TIMEOUT), "--self-check"], ""
)
# `--hooks-config` 不是可选项：接线自检缺席 = 没有证据可查，按失败关闭一律 exit 2
# （宁可每次调用都被拦住，也不接受"以为接上了其实没接"）。
cli_block = run_hook_cli(
    [
        "--config",
        str(CONFIG_PATH),
        "--hooks-config",
        str(GOOD),
        "--audit",
        str(fresh(TEMP / "cli-block.jsonl")),
    ],
    json.dumps(event("pre-tool-use-edit-block.json")),
)
cli_allow = run_hook_cli(
    [
        "--config",
        str(CONFIG_PATH),
        "--hooks-config",
        str(GOOD),
        "--audit",
        str(fresh(TEMP / "cli-allow.jsonl")),
    ],
    json.dumps(event("pre-tool-use-edit-allow.json")),
)
cli_bad_stdin = run_hook_cli(
    [
        "--config",
        str(CONFIG_PATH),
        "--hooks-config",
        str(GOOD),
        "--audit",
        str(fresh(TEMP / "cli-bad.jsonl")),
    ],
    "{ not json",
)

print()
print(pad("CLI 调用", 26) + pad("退出码", 8) + "stdout / stderr")
print("-" * 108)
for label, result, note in (
    ("--self-check 接线正常", self_check_ok, self_check_ok.stderr.strip()[:44]),
    ("--self-check 接线坏", self_check_bad, self_check_bad.stderr.strip()[:44]),
    ("违规事件", cli_block, "stdout 空" if cli_block.stdout == "" else "stdout 非空！"),
    ("合规事件", cli_allow, "stdout 与 stderr 都空" if not (cli_allow.stdout or cli_allow.stderr) else "有输出！"),
    ("stdin 不是 JSON", cli_bad_stdin, cli_bad_stdin.stderr.strip()[:44]),
):
    print(pad(label, 26) + pad(result.returncode, 8) + note)

assert (self_check_ok.returncode, self_check_bad.returncode) == (EXIT_ALLOW, EXIT_BLOCK)
assert cli_block.returncode == EXIT_BLOCK and cli_block.stdout == ""
assert cli_allow.returncode == EXIT_ALLOW and cli_allow.stdout == "" and cli_allow.stderr == ""
assert cli_bad_stdin.returncode == EXIT_BLOCK

# 审计：写结论与摘要，不写内容。
block_lines = (TEMP / "hook-block.jsonl").read_text(encoding="utf-8").splitlines()
record = next(json.loads(line) for line in block_lines if "audit_schema_version" in line)
documented = (
    "audit_schema_version", "timestamp", "agent", "agent_version", "reason_code", "exit_code",
    "executed", "elapsed_ms", "rule_set_hash", "governed", "event_id", "request_id", "tool",
    "operation", "file", "layer", "language", "dependencies", "payload_digest", "payload_fields",
    "matched_rules", "skipped_rules", "decision",
)
missing = [name for name in documented if name not in record]
assert not missing, missing
assert record["decision"] == "block" and record["payload_digest"].startswith("sha256:")
assert all("from repository import" not in line for line in block_lines)
print()
print(pad("审计字段", 22) + "值")
print("-" * 108)
for name in ("reason_code", "exit_code", "executed", "decision", "file", "operation", "layer", "dependencies", "payload_digest"):
    print(pad(name, 22) + str(record[name]))
print()
print("台账里没有源码内容:", all("from repository import" not in line for line in block_lines))
sensitive = "读取 " + str(PROJECT_ROOT) + "/src/shop/order_controller.py 失败"
print("反馈文本脱敏（绝对路径变占位符）:", sanitize(sensitive, project_root=PROJECT_ROOT))

# ----------------------------------------------------------------------------
# ## 5. PostToolUse：执行之后的那一半（第 9 步）
#
# PreToolUse 只能保证"执行前被授权"，它管不了"执行完之后结果对不对"。dsh 在工具返回之后再调一次 Hook，
# 把 `tool_response` 一起送进来，这一半交给 Phase 4 的事后验证：
#
#     PreToolUse   -> 授权，并把执行前基线（路径 + 哈希 + 字节数）写进台账
#     （Agent 运行时执行工具）
#     PostToolUse  -> 取回基线 -> 收集文件哈希与 diff -> 跑注册表声明的验证器 -> 写终态
#
# 两个细节决定它的语义：**副作用已经发生**，所以 exit 2 的含义是"这次执行的结果需要修复"
# （`post_repair_required` / `post_inconsistent`），绝不是"回滚成功"；
# 找不到对应的执行前基线时只记一条 `post_without_pre` 并放行——那一刻已经无法证明这次执行属于哪个动作了。
# ----------------------------------------------------------------------------

# 第 9 步：pre 留基线，post 收证据。Agent 执行工具这一步由本单元自己扮演（往受控项目里写文件）。
POST_AUDIT = fresh(TEMP / "hook-post.jsonl")
# 先回到一个确定的起点：目标文件不存在。否则"写进去的内容和原来一模一样"会被判成
# post_inconsistent（工具声称成功、目标却没变）——那是第三种情形，不是这里要演示的。
for relative in ("src/shop/order_controller.py", "src/shop/cart_service.py"):
    stale = PROJECT_ROOT / relative
    if stale.exists():
        stale.unlink()


def post_cycle(label, *, tool_use_id, relative, new_string, content=None):
    pre = run_hook(
        event(
            "pre-tool-use-edit-allow.json",
            tool_use_id=tool_use_id,
            tool_input={
                "file_path": relative,
                "old_string": "a",
                "new_string": new_string,
                "replace_all": False,
            },
        ),
        config_path=CONFIG_PATH,
        executor=RecordingExecutor(),
        audit_path=POST_AUDIT,
    )
    target = PROJECT_ROOT / relative
    if content is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
    post = run_hook(
        event("post-tool-use-edit.json", tool_use_id=tool_use_id, tool_response="The file has been updated."),
        config_path=CONFIG_PATH,
        executor=RecordingExecutor(),
        audit_path=POST_AUDIT,
    )
    return label, pre, post


cycles = (
    post_cycle(
        "改了文件、结果对得上",
        tool_use_id="call-post-valid",
        relative="src/shop/order_controller.py",
        new_string="value = 1",
        content="value = 1" + chr(10),
    ),
    post_cycle(
        "改了文件、语法不合法",
        tool_use_id="call-post-repair",
        relative="src/shop/cart_service.py",
        new_string="def create(:",
        content="def create(:" + chr(10),
    ),
)

print(pad("情形", 24) + pad("pre", 18) + "post")
print("-" * 116)
for label, pre, post in cycles:
    print(
        pad(label, 24)
        + pad(f"exit {pre.exit_code} {pre.reason_code}", 18)
        + f"exit {post.exit_code} {post.reason_code}"
    )

validated = cycles[0][2]
repair = cycles[1][2]
assert validated.exit_code == EXIT_ALLOW and validated.reason_code == "post_validated"
assert repair.exit_code == EXIT_BLOCK and repair.reason_code == "post_repair_required"
assert "副作用无法撤销" in repair.stderr
print()
print("语法不合法时写给模型的理由:")
print(repair.stderr.strip())
print()
print("注意语义：副作用已经发生，exit 2 表示这次结果需要修复，不表示已经回滚。")

# 同一份审计里能读到同一次调用的 pre 与 post 两条记录，台账按 event_id 串起来。
ledger = AuditLedger(POST_AUDIT)
previous = ledger.lookup("sess-demo-0001:call-post-valid")
print()
print("台账按 event_id 查到上一次判定:", previous is not None, "| 原因码:", None if previous is None else previous["reason_code"])
post_lines = POST_AUDIT.read_text(encoding="utf-8").splitlines()
assert previous is not None and previous["reason_code"] == "allow"
assert sum(1 for line in post_lines if "call-post-valid" in line) >= 2
assert sum(1 for line in post_lines if "call-post-repair" in line) >= 2
# G2 的成对契约要按**语义**断言，不能数记录条数：同一次调用在审计里除了 Phase 2 的
# PreToolUse / PostToolUse 两条，还会落 Phase 4 的 pre_state / post_evidence / final_decision 等阶段，
# 会话起点另有一条 G11 的上下文留痕（reason_code=context_injection）。数条数会随不相干的
# 记录增减而变红（或者更糟：被放宽成 >= 之后再也测不到"少了一段"）。
# 真正要守住的是：**每一次调用恰好一条 PreToolUse、恰好一条 PostToolUse**。
# 断言"成对"而不是"条数"：同一次调用在 Phase 2 与 Phase 4 各落一条 pre、各落一条 post，
# 加上会话级的 G11 上下文留痕，条数会随实现阶段变化；而"这次调用有没有事后记录"才是 G2 要守的。
for _call_id in ("call-post-valid", "call-post-repair"):
    _events = [
        json.loads(line).get("hook_event")
        for line in post_lines
        if _call_id in line
    ]
    assert "PreToolUse" in _events, (_call_id, _events)
    assert "PostToolUse" in _events, (_call_id, _events)
    print(
        pad(_call_id, 22) + pad(len(_events), 5) + "条记录："
        + str(sorted({item for item in _events if item}))
    )
print(
    "审计文件里的记录条数:",
    len(post_lines),
    "（两次调用各恰好一条 PreToolUse 与一条 PostToolUse，其余是 Phase 4 阶段记录与会话级留痕）",
)

# ----------------------------------------------------------------------------
# ## 小结
#
# - **Hook 是外部命令，接口只有两样东西**：stdin 上的事件 JSON 与退出码。`exit 0` 放行、`exit 2` 阻断
#   （stderr 即理由，写给模型看），放行时 stdout 必须为空。
# - **九步里有两步是"门禁中的门禁"**：工具表白名单（未知工具 / MCP 前缀一律拒绝）与路径范围校验
#   （归一化后必须落在受控项目内）——它们都在平台判定之前，因为"看不懂的工具"没有资格进入判定。
# - **失败关闭只能靠自己**：dsh 把超时、崩溃、配置读不到都当放行。本 notebook 实测的六条失败路径
#   （未知工具 / 未知事件 / 越界路径 / 超时 / 重放 / 接线不等式不满足）全部 exit 2，且都给得出原因码。
# - **审计是追加写 JSONL，同时是幂等台账**：只写结论与摘要（`payload_digest` 形如 `sha256:` 开头），
#   不写源码内容、用户消息与绝对路径；同一个 `event_id` 再到达就是重放，一律阻断。
# - **PostToolUse 的 exit 2 不是回滚**：副作用已经发生，它的含义是"结果需要修复"。
# - 一条本 notebook 之外的实测偏差：官方外部命令桥在本机把 Hook 的 deny 丢了（工具仍然执行），
#   沙箱闭环因此改用进程内转发插件；**线协议一个字没变**。细节见 `src/adapters/dsh/README.md` 第 7 节。
#
# 继续往下读：`01-判定核心-Policy-Engine.ipynb`（Hook 里那次 `evaluate` 的内部流程）、
# `04-受控执行.ipynb`（allow 之后的授权凭据与执行）、`06-Policy-API.ipynb`（同一条判定换成 HTTP 边界）。
# ----------------------------------------------------------------------------

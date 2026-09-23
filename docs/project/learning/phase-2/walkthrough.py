"""Phase 2 学习手册的纯 Python 版本（由 tools/build_learning_notebook.py 生成）。

notebook 里每一段代码都按顺序出现在下面；直接运行本文件即可复现全部输出：

    python docs/project/learning/phase-2/walkthrough.py

内容改动请修改 tools/build_learning_notebook.py 后重新生成，不要直接编辑本文件。
"""

# ----------------------------------------------------------------------------
# # Phase 2 学习手册：dsh Adapter
#
# 这份 notebook 用**实际运行的代码**解释 Phase 2：dsh Adapter 如何把一个真实 Agent Runtime
# 的工具调用事件翻译成核心策略协议，并在工具执行之前决定 allow / block。
#
# ## Phase 2 要证明的事
#
#     dsh Hook 事件（stdin 上的 JSON）
#       -> Adapter：验证 -> 字段规范化 -> PolicyEvent -> PolicyContext
#       -> Policy Engine（写类工具）
#       -> 受控工具再过一道 Phase 4 门禁（注册表 / 主体权限 / 参数白名单 / 命令白名单 / 审批）
#       -> allow：放行（exit 0，执行器恰好被调用一次）
#       -> block：结构化违规（exit 2，执行器一次都不调用）
#       -> PostToolUse：事后验证（exit 2 = 这次执行的结果需要修复）
#
# 一句话：**"模型想调用工具"与"工具获准执行"是两个独立事实，策略层第一次拿到行为控制能力，
# 而核心库 src/policy 仍然不知道 dsh 的存在。**
#
# Phase 4 之后同一份 Hook 多了一层：写类与被注册的执行类工具在引擎放行之后，
# 还要过 Tool Registry 的执行前授权；只读工具则**显式降级**（审计里写 `not_governed`）并记录。
# 分工不变：**Adapter 只做协议转换，判断全在 policy 与 enforcement 里。**
#
# ## 阅读路线
#
# | 小节 | 回答的问题 |
# | --- | --- |
# | 0 | 跑这份 notebook 需要什么前提 |
# | 1 | dsh 送来的原始事件长什么样，fixture 为什么必须脱敏 |
# | 2 | 纯映射：dsh Event 如何变成 PolicyEvent 与 PolicyContext |
# | 3 | layer / language / principal 从哪里来，为什么只能显式声明 |
# | 4 | Hook 的出口：block（执行 0 次）与 allow（执行 1 次），以及 Phase 4 门禁 |
# | 5 | PostToolUse：执行之后的那一半，什么时候判"需要修复" |
# | 6 | 失败关闭：未知工具 / 未知事件 / 未登记的执行类工具 / 超时 / 重放 / 没接线 |
# | 7 | 命令行：`python -m adapters.dsh.hooks` 的退出码与"放行时 stdout 为空" |
# | 8 | 审计与反馈：留下结论，不留下内容 |
# | 9 | 边界：Phase 2 明确不做什么 |
#
# 每个代码单元后面都有一个小结，说明"这段输出意味着什么"。
# 这份 notebook **不调用 dsh、不联网、不跑 LLM**：它只用仓库里已经通过测试的模块与脱敏 fixture。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 预备知识：Phase 2 新出现的名词
#
# Phase 0 / Phase 1 手册已经讲过函数、类、模型、YAML 缩进与决策协议，这里只补新词。
# 看不懂代码时回到这张表查。
#
# | 名词 | 一句话解释 | 在本手册里的样子 |
# | --- | --- | --- |
# | Hook | Agent 在某个时刻调用的一段外部命令，用来插入策略判定 | PreToolUse Hook |
# | 标准输入 stdin | 命令读到的输入数据；dsh 把事件 JSON 写在这里 | `sys.stdin.read()` |
# | 标准输出 stdout | 命令的正常输出；dsh 只在 exit 0 且以 { 开头时才解析它 | 放行时必须为空 |
# | 标准错误 stderr | 诊断信息；阻断时它就是给模型看的理由 | `[policy] BLOCKED ...` |
# | 退出码 | 命令留给操作系统的数字，也是 Hook 与 dsh 之间唯一的接口 | 0 放行 / 2 阻断 |
# | 失败关闭 fail-closed | 无法安全判定时阻断，而不是默认放行 | 未知工具、未知事件、超时 |
# | 纯映射 pure mapping | 只做翻译与校验，不做判断、不读文件、不调工具 | adapter.py 的全部职责 |
# | fixture | 固定下来的真实样本，作为契约测试的输入 | tests/fixtures/agent_events/dsh/ |
# | 摘要 digest | 内容的指纹，用来关联审计而不落盘原文 | sha256:... |
# | 幂等 / 重放 replay | 同一个事件标识重复到达时不重复执行 | 审计台账按 event_id 查重 |
# | 内部预算 | Hook 自己设定的判定时限，必须小于 dsh 的 timeout | timeout_ms: 5000 < 30s |
# | 接线 wiring | "Hook 真的被注册了吗"；配置读不到就等于没有治理 | --self-check / --hooks-config |
# | ControlledExecutor | 受控执行器：只在 allow 之后被调用，且至多一次 | 测试里换成记录次数的 fake |
#
# Phase 2 有一条贯穿全篇的约定：**dsh 侧的失败语义不能提供任何保证，所以保证必须由 Hook 自己给。**
# dsh 把退出码 1、崩溃、被超时杀掉都当作"非阻断失败"——**工具照样执行**。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 笔记本放在 docs/project/learning/phase-2/，代码在 src/adapters/dsh/。先找到仓库根目录、
# 把 src/ 告诉 Python，再准备一个本次专用的临时工作区：
#
# - 所有写盘动作都落在仓库的 `.tmp/learning/<uuid>/` 下（仓库约定：临时文件只写 `.tmp/`，
#   用完由 `python tools/cleanup.py` 清理）；
# - 临时目录用 `mkdir + uuid` 生成，不用 `tempfile.mkdtemp`：受限沙箱里后者会被拒绝；
# - 工作区里有一个受控的"被治理项目"（demo-shop），Adapter 只对它做路径规范化，不读文件内容。
# ----------------------------------------------------------------------------

# 0. 准备运行环境：仓库根目录、src/ 路径与本次专用的临时工作区
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml


def find_repo_root(start):
    print("函数用途:", "向上找到含 policies/ 的目录；找不到就退回当前工作目录")
    for candidate in (start, *start.parents):
        if (candidate / "policies").is_dir():
            return candidate
    return Path.cwd()


# Path.cwd() 是当前工作目录：从仓库根启动时它本身就是仓库根，
# 从 notebook 所在目录启动时靠 find_repo_root 往上找。
NOTEBOOK_DIR = Path.cwd() if Path("policies").is_dir() else Path("docs/project/learning/phase-2")
REPO_ROOT = find_repo_root(NOTEBOOK_DIR.resolve())

# src/ 放核心库（policy）与适配器（adapters.dsh）；两个工作目录下都能 import。
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

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
    run_hook,
    sanitize,
)
from policy.engine import evaluate
from policy.loader import load_rule_set
from policy.models import SCHEMA_VERSION, Decision

# 脱敏 fixture：Phase 2 契约测试的输入，也是本手册的输入。
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "dsh"

# 临时工作区：mkdir + uuid（不用 tempfile.mkdtemp，受限沙箱会拒绝）。
TMP_ROOT = REPO_ROOT / ".tmp" / "learning" / uuid.uuid4().hex
PROJECT_ROOT = TMP_ROOT / "demo-shop"
(PROJECT_ROOT / "src" / "shop").mkdir(parents=True, exist_ok=True)

print("仓库根目录:", REPO_ROOT)
print("临时工作区:", TMP_ROOT.relative_to(REPO_ROOT).as_posix())
print("受治理项目:", PROJECT_ROOT.name, "（只有目录结构，Adapter 不读文件内容）")
print("决策协议版本:", SCHEMA_VERSION, "| Agent 标识:", DSH_AGENT_ID)
print("Phase 2 承认的事件:", list(SUPPORTED_HOOK_EVENTS))
print("载荷必需字段:", list(REQUIRED_PAYLOAD_FIELDS))
print("工具表:", len(TOOL_TABLE), "个工具（不在表里的一律拒绝）")


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
# **小结**：手册运行在仓库内，所以临时文件必须写在 `.tmp/` 下，而不是仓库根或系统临时目录。
# 工具表、事件白名单、载荷必需字段这三样东西都不是"随手写的常量"，它们是 Phase 2 的契约：
# dsh 升级后如果这三样变了，契约测试会先失败，而不是让新工具悄悄绕过治理。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 1. dsh 送来的原始事件
#
# dsh 把事件写成 JSON 放进 Hook 进程的 stdin。字段形状（0.1.5-rc.1 实测，结论与证据见
# `src/adapters/dsh/README.md`）由**事件基座 + 工具字段**组成：
#
#     session_id / transcript_path / cwd / hook_event_name     事件基座
#     tool_name / tool_input / tool_use_id                     工具字段
#
# 两个容易忽略的细节：
#
# - `transcript_path` 在 dsh 里恒为空串，仍然保留——它是协议的一部分，删掉就不是"真实载荷"了；
# - PreToolUse 拿到的工具参数是**未解析的原始字符串**：相对路径要靠载荷里的 cwd
#   （dsh 传的是 agent.session.header.cwd）才能变成绝对路径。
#
# 本手册用的是**脱敏 fixture**：绝对路径换成占位值、会话标识换成 sess-demo-0001、
# 用户数据与密钥已删除（采集与脱敏方式记在 tests/fixtures/agent_events/dsh/README.md）。
#
# 那份 README 的表格同时记录每个样本在**当前阶段**的预期：Phase 4 之后，
# `pwsh` 这类执行类工具的预期从"不受治理"变成"由 Tool Registry 治理"，
# `read` 仍然是"允许并标记 not_governed"，`PostToolUse` 则成了事后验证的入口。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 把 fixture 全部读进来，只打印**形状**（事件名、工具名、参数键），不打印参数内容。
# `json.loads` 把 JSON 文本变成 Python 字典；`sorted(...)` 让键的顺序稳定，方便比对。
# ----------------------------------------------------------------------------

# 1. 先看形状：dsh 会送来哪些事件，每个事件带什么工具参数
print(pad("fixture", 38) + pad("事件", 14) + pad("工具", 26) + "参数键")
print("-" * 100)
for path in sorted(FIXTURES.glob("*.json")):
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(
        pad(path.name, 38)
        + pad(payload["hook_event_name"], 14)
        + pad(payload["tool_name"], 26)
        + ",".join(sorted(payload["tool_input"]))
    )

print()
sample = json.loads((FIXTURES / "pre-tool-use-edit-block.json").read_text(encoding="utf-8"))
print("一条 edit 事件的顶层字段:", sorted(sample))
print("cwd 是路径解析的基准:", sample["cwd"])
print("transcript_path 恒为空串:", repr(sample["transcript_path"]))
print("工具参数是原始字符串（未解析路径）:", isinstance(sample["tool_input"]["new_string"], str))

# ----------------------------------------------------------------------------
# **小结**：fixture 里既有 allow 场景也有 block 场景，还有几个**故意不合规**的载荷
# （未知工具、未知事件、缺路径、混入多余的提示词字段）。它们不是"坏数据"，而是契约的另一半：
# Adapter 必须能认出"这不是我认识的协议"，然后拒绝。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 2. 纯映射：dsh Event -> PolicyEvent -> PolicyContext
#
# Adapter 的职责被严格限制成一句话（Phase 2 文档第 2 步）：
#
#     dsh Event -> 验证 -> 字段规范化 -> PolicyEvent / PolicyContext
#
# 它不加载规则、不决定 severity、不调用工具、不拼接 Prompt、不读文件系统、不访问网络，
# 也不 import dsh 的 TypeScript 实现——只依赖线协议，因此没有安装 dsh 的机器也能跑契约测试。
#
# 两段映射各有产物：
#
# | 产物 | 是什么 | 关键字段 |
# | --- | --- | --- |
# | `PolicyEvent` | 规范化后的标准事件（架构文档里的 tool.pre_execute） | event_id、operation、file、layer、language、dependencies、payload_digest |
# | `PolicyContext` | 核心引擎的输入 | request_id、project、agent、operation、file、layer、language、dependencies |
#
# `PolicyEvent` 用 `payload_fields` 只记参数**名字**、用 `payload_digest` 只记参数**指纹**：
# 审计既能关联到同一次调用，又不会把源码内容或用户数据写进证据文件。
#
# ### 映射需要的字段从哪来
#
# dsh 的载荷里有 session_id / cwd / tool_name / tool_input / tool_use_id，
# 但**没有** layer、language、project、principal。这些字段必须由一份可评审的配置文件显式声明
# （示例：examples/dsh/dsh-adapter.yaml）。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 先造两个小工具：
#
# 1. `rebase`：把 fixture 里的占位路径换成**本次真实的临时项目根**，
#    这样 fixture 自己不含任何本机路径，测试与手册都指向同一个受控项目；
# 2. `write_adapter_config`：写一份 adapter 配置（YAML），显式声明 layers（路径 -> 层）与 languages；
# 3. 同时声明 Phase 4 需要的三样东西：**主体**（principal）、**工具注册表**与**已审核哈希清单**。
#    缺任一项，受控工具都会被 Hook 失败关闭（`enforcement_unavailable`），而不是"没有治理也算通过"。
#
# 然后打印这份配置本身——本手册后面所有的映射与判定都基于它。
# ----------------------------------------------------------------------------

# 2. 造出本次的 adapter 配置：layer / language 都在这里显式声明
PLACEHOLDER_POSIX = "/workspace/demo-shop"
PLACEHOLDER_WINDOWS = "C:" + chr(92) + "workspace" + chr(92) + "demo-shop"


def rebase(value):
    # 递归替换占位路径：字符串直接替换，字典与列表逐项处理，其他类型原样返回。
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
    # 读一条脱敏 fixture，把占位路径换成真实临时项目根，再套用本次的覆盖字段。
    payload = rebase(json.loads((FIXTURES / name).read_text(encoding="utf-8")))
    payload.update(overrides)
    return payload


def write_adapter_config(path, **overrides):
    document = {
        "agent_version": "0.1.5-rc.1",
        "project": "demo-shop",
        "project_root": str(PROJECT_ROOT),
        "rules": [str(REPO_ROOT / "policies")],
        "rules_root": str(REPO_ROOT),
        "timeout_ms": 5000,
        # path -> layer：按声明顺序取第一个命中；不命中就失败关闭。
        "layers": [
            {"pattern": "**/*_controller.py", "layer": "controller"},
            {"pattern": "**/*_service.py", "layer": "service"},
            {"pattern": "**/*_repository.py", "layer": "repository"},
        ],
        "languages": [{"pattern": "**/*.py", "language": "python"}],
        "audit_log": str(path.parent / "audit.jsonl"),
        # Phase 4：受控工具需要显式主体与工具注册表；缺任一项都由 Hook 失败关闭。
        "principal": {"subject": "local-user", "roles": ["developer"]},
        "registry": str(REPO_ROOT / "registry" / "tool-registry.yaml"),
        "registry_approved": str(REPO_ROOT / "registry" / "tool-registry.approved.json"),
    }
    document.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


CONFIG_PATH = write_adapter_config(TMP_ROOT / "config" / "dsh-adapter.yaml")
CONFIG = load_config(CONFIG_PATH)
# rules_root 是规则来源的锚点：规则库与被治理项目常常不在同一个仓库。
RULES = load_rule_set(CONFIG.rule_dirs, repo_root=CONFIG.rule_anchor)

print("配置路径:", CONFIG_PATH.relative_to(REPO_ROOT).as_posix())
print("-" * 72)
print(CONFIG_PATH.read_text(encoding="utf-8").rstrip())
print("-" * 72)
print("规则集:", RULES.ids, "| 规则锚点:", CONFIG.rule_anchor.name)

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 把 edit-block 事件走完整条链：`to_policy_event` -> `to_policy_context` -> `evaluate`。
#
# 先按字段名核对两个对象（**文档里写过的字段必须全部存在**，少一个就当场失败），再打印关键值。
# 这样一个单元同时证明两件事：字段没有改名，以及映射结果长什么样。
# ----------------------------------------------------------------------------

# 3. 纯映射第一步：dsh 事件 -> PolicyEvent -> PolicyContext
documented_event_fields = (
    "event_id", "request_id", "kind", "agent", "agent_version", "tool", "operation",
    "file", "layer", "language", "dependencies", "payload_digest", "payload_fields",
    "session_id", "cwd", "trace_id",
)
documented_context_fields = (
    "request_id", "project", "agent", "operation", "file", "language", "module",
    "layer", "task", "dependencies", "git_diff", "principal", "trace_id",
)

mapped = to_policy_event(event("pre-tool-use-edit-block.json"), config=CONFIG)
assert mapped.governed is True, mapped.reason
mapped_event = mapped.event
mapped_context = to_policy_context(mapped_event, config=CONFIG)

for label, obj, expected in (
    ("PolicyEvent", mapped_event, documented_event_fields),
    ("PolicyContext", mapped_context, documented_context_fields),
):
    missing = [name for name in expected if not hasattr(obj, name)]
    assert not missing, f"{label} 缺少文档里写过的字段: {missing}"
    print(f"{label:<15}{len(expected)} 个文档字段全部存在")

print()
print("准入结论:", mapped.governed, "|", mapped.reason)
print(f"{'PolicyEvent':<16}{'值'}")
print("-" * 72)
for name in (
    "event_id", "kind", "agent", "agent_version", "tool", "operation", "file",
    "layer", "language", "dependencies", "payload_digest", "payload_fields", "session_id",
):
    print(f"{name:<16}{getattr(mapped_event, name)}")

print()
print("PolicyContext 的关键字段:")
print("  request_id  :", mapped_context.request_id, "（= session_id + tool_use_id）")
print("  operation   :", mapped_context.operation.value, "（来自工具表：edit -> edit）")
print("  file        :", mapped_context.file, "（仓库相对路径；绝对路径与反斜杠都会收敛到这里）")
print("  layer       :", mapped_context.layer, "（来自配置，不来自文件名猜测）")
print("  module      :", mapped_context.module, "（刻意留空：猜错模块会让规则在错误范围生效）")
print("  dependencies:", mapped_context.dependencies, "（只从本次变更文本里提取的顶层 import）")
print("  principal   :", mapped_context.principal, "（来自配置，绝不从事件或消息推断）")
print()
print("同一份上下文交给 Engine:", evaluate(RULES, mapped_context).decision.value)

# ----------------------------------------------------------------------------
# **小结**：一次 edit 事件变成了引擎认识的上下文，字段来源清清楚楚：
# file/operation/agent 来自事件与工具表，layer/language/principal 来自配置，dependencies 来自本次变更的文本。
# `dependencies` 只看"这次改动引入了什么"，不看磁盘上文件原本有什么——后者属于 Phase 4 的
# post-execute 与 Phase 5 的 Validator。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 同一个契约换个角度看三件事：
#
# 1. `write` 工具映射成 `operation=create`（dsh 的 write 是 create-or-overwrite，
#    一个字符串表达不了两种语义，需要同时覆盖时把规则的 operation 写成 `[create, edit]`）；
# 2. **真实采集**的载荷（绝对 Windows 路径 + 正斜杠 cwd + 缺省可选字段）走同一条映射路径，
#    最后得到一模一样的仓库相对路径；
# 3. 参数原文只以"名字"的形式留痕，值本身不出现在事件里。
# ----------------------------------------------------------------------------

# 4. 同一个 file 契约：write 映射为 create，真实采集的绝对路径也归一
write_decision = to_policy_event(event("pre-tool-use-write-block.json"), config=CONFIG)
captured_decision = to_policy_event(event("pre-tool-use-edit-captured.json"), config=CONFIG)

rows = (
    ("write（整文件写入）", write_decision, "create", "src/shop/cart_controller.py"),
    ("edit（真实采集）", captured_decision, "edit", "src/shop/order_controller.py"),
)

print(pad("场景", 22) + pad("工具", 8) + pad("operation", 11) + pad("layer", 12) + "仓库相对路径")
print("-" * 96)
for label, decision, expected_operation, expected_file in rows:
    assert decision.governed is True, label
    assert decision.event.operation.value == expected_operation, (label, decision.event.operation)
    assert decision.event.file == expected_file, (label, decision.event.file)
    print(
        pad(label, 22)
        + pad(decision.event.tool, 8)
        + pad(decision.event.operation.value, 11)
        + pad(decision.event.layer, 12)
        + decision.event.file
    )

print()
print("真实采集载荷的两个细节:")
print("  cwd 用正斜杠        :", captured_decision.event.cwd)
print("  参数只留名字不留内容:", captured_decision.event.payload_fields)
print("  参数指纹             :", captured_decision.event.payload_digest[:22] + "...")

# ----------------------------------------------------------------------------
# **小结**：路径最终只有一种写法，工具差别只体现在 operation 上。
# "write 映射成 create"是一个**有代价的取舍**：只为 edit 声明 operation 的规则不会命中 write。
# 代价是可见的——规则会在 skipped_rules 里写出 operation 不匹配的原因，不会静默通过。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 最后看 Adapter 的"不猜、不吞"：
#
# 1. 只读工具（read / glob / grep）**不受治理**：显式降级并记录，绝不假装检查过；
# 2. 执行类工具（pwsh / bash / run_code）在 Adapter 这一层同样不做策略判定，
#    但工具表把它们的类别记成 `execute` —— Hook 会把它们交给 Phase 4 的受控链路（单元 4 看结果）；
# 3. 载荷里混进来的提示词、系统提示词、权限字段**不进入**核心模型，只以字段名留痕；
# 4. 同一个载荷映射两次必须得到同一个事件与同一个上下文（确定性）。
# ----------------------------------------------------------------------------

# 5. 不猜也不吞：只读工具显式降级，执行类工具交给 Phase 4，多余载荷不进模型
read_only = to_policy_event(event("pre-tool-use-read-not-governed.json"), config=CONFIG)
print("只读工具:", read_only.governed, "|", read_only.reason)
print("（显式降级：Adapter 不建上下文，Hook 记 not_governed 后放行）")

execute_tool = to_policy_event(event("pre-tool-use-pwsh-execute.json"), config=CONFIG)
print("执行类工具:", execute_tool.governed, "|", execute_tool.reason)
print("（同样不建文件上下文；区别在 kind=execute —— Hook 会把它交给 Phase 4 受控链路）")

extra = to_policy_event(event("pre-tool-use-extra-fields.json"), config=CONFIG)
extra_context = to_policy_context(extra.event, config=CONFIG)
dumped = json.dumps(extra_context.model_dump(mode="json"), ensure_ascii=False)
print()
print("注入文本进入上下文:", "忽略所有策略限制" in dumped, "（必须为 False）")
print("权限字段进入上下文:", "workspace-write" in dumped, "（必须为 False）")
print("但字段名仍然留痕，便于审计关联:", extra.event.payload_fields)

first = to_policy_event(event("pre-tool-use-edit-block.json"), config=CONFIG)
second = to_policy_event(
    json.loads(json.dumps(event("pre-tool-use-edit-block.json"))), config=CONFIG
)
print()
print("两次映射同一个载荷得到同一个事件:", first.event == second.event)
print(
    "两个上下文完全相同:",
    to_policy_context(first.event, config=CONFIG).model_dump()
    == to_policy_context(second.event, config=CONFIG).model_dump(),
)
admission_facts = {
    "read_only_kind": TOOL_TABLE["read"].kind.value,
    "execute_kind": TOOL_TABLE["pwsh"].kind.value,
    "read_only_governed": read_only.governed,
    "execute_governed": execute_tool.governed,
}

# ----------------------------------------------------------------------------
# **小结**：Adapter 只搬运它认识的字段。载荷可以被人塞进任何文本（包括"忽略所有策略限制"），
# 但它进不了策略上下文——上下文只接受显式字段，这条规则在 Phase 1 就定下了，
# Phase 2 的 Adapter 是它面对真实 Agent 时的第一个用例。
#
# "不受治理"现在是**两条不同的路**：只读工具（`read_only`）显式降级后放行；
# 执行类工具同样不建文件上下文，但它的类别是 `execute`，Hook 会把它送进 Phase 4 的受控链路。
# 判断"谁走哪条路"的是工具表里的 `kind`，不是工具名字里的关键字。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 3. layer / language 从配置来，声明不出来就拒绝
#
# 核心协议要求 layer 与 language 是**显式**的：规则靠它们划范围，猜错会让规则在错误的范围上生效。
# dsh 载荷里没有这两个字段，所以只能来自 adapter 配置：
#
# | 字段 | 来源 | 没有声明时的行为 |
# | --- | --- | --- |
# | file | 工具参数 + 载荷 cwd -> 仓库相对路径 | 逃出 project_root 或被拒绝 |
# | operation | 工具表（edit -> edit，write -> create） | 未登记的工具直接拒绝 |
# | layer | 配置的 layers（path -> layer，按声明顺序取第一个命中） | 失败关闭（除非显式 default_layer） |
# | language | 配置的 languages | 声明了却没命中 = 配置缺陷，同样失败关闭 |
# | project / principal / trace_id | 配置 | 留空，绝不从文件名、目录或用户消息推断 |
#
# 失败关闭的意思是**报错并阻断**，而不是"用默认值继续跑"。下面用 `try/except` 把错误文本打出来，
# 不让单元抛未捕获异常——错误信息本身就是给运维与模型的可诊断线索。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 造两份**故意写坏**的配置，看 Adapter 拒绝时说了什么：
#
# 1. 完全不写 layers：任何写操作都必须被拒绝，并提示怎么补声明；
# 2. 写了 languages 但只匹配 rust：Python 文件命中不到映射，说明"映射不完整"。
#
# 第三份配置显式声明 `default_layer`，用来对照"声明是唯一的放宽方式"。
# ----------------------------------------------------------------------------

# 6. layer / language 只能显式声明，声明不出来就失败关闭
rejections = []

# 反例 1：没有任何 layers 映射
no_layers = load_config(write_adapter_config(TMP_ROOT / "config" / "no-layers.yaml", layers=[]))
try:
    to_policy_event(event("pre-tool-use-edit-block.json"), config=no_layers)
except DshEventError as error:
    rejections.append(("未声明任何 layer", " ".join(str(error).split())))
else:
    raise AssertionError("没有 layer 映射时必须失败关闭")

# 反例 2：声明了 languages，但没有任何一条能命中 Python 文件
wrong_languages = load_config(
    write_adapter_config(
        TMP_ROOT / "config" / "wrong-languages.yaml",
        languages=[{"pattern": "**/*.rs", "language": "rust"}],
    )
)
try:
    to_policy_event(event("pre-tool-use-write-block.json"), config=wrong_languages)
except DshEventError as error:
    rejections.append(("languages 未命中", " ".join(str(error).split())))
else:
    raise AssertionError("声明了 languages 却不命中时必须失败关闭")

# 正例：唯一允许的放宽方式是显式声明，而不是猜测
relaxed = load_config(
    write_adapter_config(TMP_ROOT / "config" / "default-layer.yaml", default_layer="unknown")
)
relaxed_decision = to_policy_event(
    event(
        "pre-tool-use-edit-block.json",
        tool_input={"file_path": "scripts/tool.py", "new_string": "x = 1"},
    ),
    config=relaxed,
)

for label, detail in rejections:
    print(pad(label, 22) + " 已拒绝:" + detail[:104])
print()
print(
    "显式声明 default_layer 后:",
    relaxed_decision.event.layer,
    "（路径不命中任何 pattern 时才有这个值）",
)
print("language 仍然是命中来的:", relaxed_decision.event.language)
print()
print("两种拒绝的共同点：信息不全时阻断，并指出该补哪一项声明。")

# ----------------------------------------------------------------------------
# **小结**：配置是唯一的上下文来源，也是唯一可评审、可 diff 的地方。
# "声明不出来就失败关闭"听起来严格，但它挡住的正是最危险的一类事故：
# 规则本该管住某个目录，却因为猜出来的 layer 值不对而根本不参与判断。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 4. Hook 的出口：block 不执行，allow 执行一次
#
# 数据流（Phase 2 文档第 4 步；Phase 4 之后多了一道门禁）：
#
#     dsh tool request
#       -> Adapter（映射；失败关闭）
#       -> Policy Engine（判定；写类工具）
#       -> Phase 4 门禁（受控工具：注册表 / 主体权限 / 参数白名单 / 命令白名单 / 审批）
#       -> allow：调用执行器一次
#       -> block：返回结构化违规，不执行
#
# 执行器是实现 `ControlledExecutor` 协议的对象：生产环境是 `NullExecutor`——工具由 dsh
# 自己在 pre-execute 之后调用，Hook 的放行就是"允许 dsh 执行一次"；测试与手册里换成记录调用次数的
# fake。**block 路径调用 0 次**是这里最重要的一条断言：它证明这是行为控制，而不是建议。
#
# Phase 4 的门禁只回答"这次动作被授权了吗"：它写审计、签发与 `action_hash` 绑定的短时效凭据，
# 但仍然**不执行工具**——执行依旧由 Agent 运行时完成。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 用真实入口 `run_hook` 处理两条 fixture：
#
# - block 场景（controller 引入 from repository import ...）：预期 exit 2、执行器 0 次、
#   stderr 里出现规则身份 `ARCH-001@1`；这一条**在引擎就结束了**，根本不进 Phase 4 门禁；
# - allow 场景（改为依赖 service 与 util）：预期 exit 0、执行器恰好 1 次、stderr 为空；
#   这一条先过 Phase 4 门禁（`fs.edit` + 主体 local-user/developer），门禁会留下
#   `action_hash` 与 `grant_id`。
#
# 然后打印 block 时写给模型的完整理由，以及允许路径在审计里留下的授权凭据。
# ----------------------------------------------------------------------------

# 7. block 与 allow：执行器调用次数就是行为控制的证据
class RecordingExecutor:
    # 记录调用次数与参数的 fake 执行器（与 tests/integration/test_dsh_hook.py 同款）。
    def __init__(self):
        self.calls = []

    def execute(self, policy_event):
        self.calls.append(policy_event)
        return ExecutionOutcome(status="executed", detail="recorded by fake executor")


block_executor = RecordingExecutor()
block_outcome = run_hook(
    event("pre-tool-use-edit-block.json"),
    config_path=CONFIG_PATH,
    executor=block_executor,
    audit_path=TMP_ROOT / "hook-block.jsonl",
)
allow_executor = RecordingExecutor()
allow_outcome = run_hook(
    event("pre-tool-use-edit-allow.json"),
    config_path=CONFIG_PATH,
    executor=allow_executor,
    audit_path=TMP_ROOT / "hook-allow.jsonl",
)

hook_outcomes = {"block": block_outcome, "allow": allow_outcome}
executor_calls = {"block": len(block_executor.calls), "allow": len(allow_executor.calls)}

assert block_outcome.exit_code == EXIT_BLOCK == 2, block_outcome.exit_code
assert allow_outcome.exit_code == EXIT_ALLOW == 0, allow_outcome.exit_code
assert executor_calls == {"block": 0, "allow": 1}, executor_calls
assert "ARCH-001@1" in block_outcome.stderr
assert block_outcome.decision.decision is Decision.BLOCK

print(
    f"block 路径：退出码 {block_outcome.exit_code}｜执行器调用 {executor_calls['block']} 次"
    f"｜原因码 {block_outcome.reason_code}"
)
print(
    f"allow 路径：退出码 {allow_outcome.exit_code}｜执行器调用 {executor_calls['allow']} 次"
    f"｜原因码 {allow_outcome.reason_code}"
)
print()
print("block 时写给模型的 stderr（不含堆栈、绝对路径与源码）:")
print(block_outcome.stderr)
print()
print("allow 时 stderr 为空:", allow_outcome.stderr == "")
print("allow 时执行器拿到的依赖:", allow_executor.calls[0].dependencies)

print()
print("Phase 4 门禁在允许路径上留下的凭据（绑定 action_hash、短时效、单次使用）:")
allow_records = [
    json.loads(line)
    for line in (TMP_ROOT / "hook-allow.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]
enforcement_record = next(
    item for item in allow_records if item.get("reason_code") == "enforcement_allow"
)
for name in ("tool_id", "risk", "action_id", "action_hash", "grant_id", "grant_expires_at"):
    print("  {:<18}{}".format(name, enforcement_record[name]))
print(
    "  同一次调用既有 Phase 2 的记录，也有 Phase 4 的 pre_decision 记录:",
    any(item.get("stage") == "pre_decision" for item in allow_records),
)
enforcement_facts = {
    "reason_code": enforcement_record["reason_code"],
    "tool_id": enforcement_record["tool_id"],
    "action_hash": enforcement_record["action_hash"],
    "grant_id": enforcement_record["grant_id"],
    "grant_expires_at": enforcement_record["grant_expires_at"],
    "has_phase4_record": any(item.get("stage") == "pre_decision" for item in allow_records),
}

# ----------------------------------------------------------------------------
# **小结**：三条信息都在 stderr 里：规则身份（ARCH-001@1）、严重级别（severity=error）、
# 证据（dependency=repository）与期望的修复方向（controller -> service -> repository）。
# 模型据此就知道该怎么改，而**工具还没有执行过**——这就是 pre-execute 与 post-execute 的本质区别。
#
# 允许路径还多了一份 Phase 4 的凭据：`action_hash` 绑住这次动作的全部内容，`grant_id` 是一次性凭据。
# 两者都由 Hook 写进审计，由 Agent 运行时（dsh）拿着去执行——**Hook 自己从不改文件**。
# 由此也能看出阻断有两个来源：引擎（规则）与门禁（注册表 / 权限 / 审批），
# 它们的原因码不同，但都发生在工具执行之前。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 5. PostToolUse：执行之后的那一半
#
# PreToolUse 只能保证"执行前被授权"，它管不了"执行完之后结果对不对"。dsh 在工具返回之后再调用一次
# Hook（PostToolUse），把 `tool_response` 一起送进来，这一半交给 Phase 4 的事后验证：
#
#     PreToolUse   -> 授权，并把执行前基线（路径 + 哈希 + 字节数）写进台账
#     （Agent 运行时执行工具）
#     PostToolUse  -> 取回基线 -> 收集文件哈希与 diff -> 跑注册表声明的验证器 -> 写终态
#
# 两个细节决定了它的语义：
#
# - **副作用已经发生**：验证失败不等于"没做过"，所以 exit 2 的含义是"结果需要修复"
#   （`post_repair_required` / `post_inconsistent`），绝不是"回滚成功"；
# - **没有 pre-check 记录就不编造结论**：找不到对应的基线时只写一条 `post_without_pre`
#   记录并放行——那一刻已经无法证明这次执行属于哪个动作了。
#
# 注册表里每个工具声明自己的事后验证器（`fs.edit` 是 file_changed / file_syntax / diff_recorded），
# 所以"验什么"同样是数据，不是代码里的判断。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 三种情形各跑一次完整的 pre -> post：
#
# 1. 工具真的改了文件、内容合法 → `post_validated`（exit 0）；
# 2. 工具改了文件、但写出来的 Python 语法不合法 → `post_repair_required`（exit 2）；
# 3. 工具声称成功、目标却没有任何变化 → `post_inconsistent`（exit 2，证据自相矛盾）。
#
# 中间那一步"Agent 执行工具"由手册自己扮演：往受控项目里写文件——这正是 dsh 在真实会话里做的事。
# ----------------------------------------------------------------------------

# 8. PostToolUse：pre 留基线，post 收证据；失败 = 结果需要修复
POST_AUDIT = TMP_ROOT / "hook-post.jsonl"


def post_cycle(label, *, tool_use_id, relative, new_string, content=None):
    # 一次完整调用：PreToolUse 授权 ->（Agent 执行）-> PostToolUse 验证。
    # 请求里声明的 new_string 要与真正写下的内容对得上：事后有 content_matches 验证器查这件事。
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
        # 手册扮演"Agent 运行时"：真正把文件写出来（这里就是 .tmp/ 下的受控项目）。
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
    post = run_hook(
        event(
            "post-tool-use-edit.json",
            tool_use_id=tool_use_id,
            tool_response="The file has been updated.",
        ),
        config_path=CONFIG_PATH,
        executor=RecordingExecutor(),
        audit_path=POST_AUDIT,
    )
    print(
        "{}: pre exit {} ({})｜post exit {} ({})".format(
            label, pre.exit_code, pre.reason_code, post.exit_code, post.reason_code
        )
    )
    return pre, post


post_validated = post_cycle(
    "情形 1：改了文件、结果对得上", tool_use_id="call-post-validated",
    relative="src/shop/order_controller.py",
    new_string="value = 1", content="value = 1" + chr(10),
)
post_repair = post_cycle(
    "情形 2：改了文件、语法不合法", tool_use_id="call-post-repair",
    relative="src/shop/cart_service.py",
    new_string="def create(:", content="def create(:" + chr(10),
)
post_inconsistent = post_cycle(
    "情形 3：声称成功、目标没变", tool_use_id="call-post-inconsistent",
    relative="src/shop/missing_service.py", new_string="value = 2",
)

print()
print("第 2 种情形写给模型的理由:")
print(post_repair[1].stderr.strip())
post_facts = {
    "validated_exit": post_validated[1].exit_code,
    "validated_reason": post_validated[1].reason_code,
    "repair_exit": post_repair[1].exit_code,
    "repair_reason": post_repair[1].reason_code,
    "inconsistent_exit": post_inconsistent[1].exit_code,
    "inconsistent_reason": post_inconsistent[1].reason_code,
}

# ----------------------------------------------------------------------------
# ## 6. 失败关闭：进不去的情况
#
# | 场景 | 会发生什么 | 原因码 |
# | --- | --- | --- |
# | 未知工具 | dsh 新版本新增的工具、`mcp__` 开头的 MCP 工具 | context_error |
# | 未知事件 | 不在事件白名单里的事件（例如 SessionStart） | context_error |
# | 未登记的执行类工具 | 工具表里有、Tool Registry 里没有（例如 workflow） | tool_not_registered |
# | 受控工具没接线 | adapter 配置里没有 registry / registry_approved | enforcement_unavailable |
# | 判定超时 | 超过内部预算 timeout_ms，工具不执行 | policy_timeout |
# | 重放同一次调用 | event_id 已在审计台账里，不重复执行 | event_replay |
#
# 为什么这么严？因为 dsh 那边**退出码 1、崩溃、被超时杀掉都等于放行**。
# 所以"我没看懂"在 dsh 眼里等于"没问题"，失败关闭只能由 Hook 自己保证：
# 任何异常都在本进程内转成 exit 2。
#
# Phase 4 之后"未知"多了一类：**Agent 认识、治理层不认识**。工具在 dsh 的工具表里、
# 却不在 Tool Registry 里（例如新加的子工作流工具）时，Hook 不能因为它"看着像执行类工具"就放行——
# 默认阻断，并提示先登记工具、重新审核注册表。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 六条路径各跑一次，全部应当阻断：
#
# 1. 未知工具：`mcp__github__create_issue` 不在 Adapter 的工具表里；
# 2. 未知事件：手写一个 `SessionStart` 事件（PostToolUse 现在是事后验证入口，不再是"未知事件"的例子）；
# 3. 未登记的执行类工具：把 pwsh 事件改名成 `workflow`，它在工具表里但不在 Tool Registry 里；
# 4. 受控工具没接线：用一份**没有 registry** 的配置跑写类工具，得到 `enforcement_unavailable`；
# 5. 超时：把内部预算压到 50ms，再让判定故意睡 300ms；
# 6. 重放：同一个 event_id 连续到达两次，第一次放行、第二次阻断，执行器总共只被调用一次。
# ----------------------------------------------------------------------------

# 9. 失败关闭：未知工具 / 未知事件 / 未登记的执行类工具 / 没接线 / 超时 / 重放
unknown_tool = run_hook(event("pre-tool-use-unknown-tool.json"), config_path=CONFIG_PATH)
unknown_event = run_hook(
    event("pre-tool-use-edit-allow.json", hook_event_name="SessionStart"),
    config_path=CONFIG_PATH,
)
unregistered_execute = run_hook(
    event("pre-tool-use-pwsh-execute.json", tool_name="workflow", tool_use_id="call-workflow"),
    config_path=CONFIG_PATH,
)
# 注意用不同的 tool_use_id：审计台账按 event_id 查重，复用同一个标识会被判成重放。
not_wired = run_hook(
    event("pre-tool-use-edit-allow.json", tool_use_id="call-not-wired"),
    config_path=write_adapter_config(
        TMP_ROOT / "config" / "no-registry.yaml", registry=None, registry_approved=None
    ),
)


# 超时：内部预算 50ms，判定故意慢下来——预算必须先在 Hook 内部触发。
def slow_evaluator(rules, context):
    time.sleep(0.3)
    return evaluate(rules, context)


slow_config = write_adapter_config(TMP_ROOT / "config" / "slow.yaml", timeout_ms=50)
slow_executor = RecordingExecutor()
timeout_outcome = run_hook(
    event("pre-tool-use-edit-block.json"),
    config_path=slow_config,
    executor=slow_executor,
    evaluator=slow_evaluator,
    audit_path=TMP_ROOT / "hook-timeout.jsonl",
)

# 重放：审计文件同时是幂等台账，键是 event_id。
replay_audit = TMP_ROOT / "replay.jsonl"
replay_executor = RecordingExecutor()
replay_first = run_hook(
    event("pre-tool-use-edit-allow.json"),
    config_path=CONFIG_PATH,
    executor=replay_executor,
    audit_path=replay_audit,
)
replay_second = run_hook(
    event("pre-tool-use-edit-allow.json"),
    config_path=CONFIG_PATH,
    executor=replay_executor,
    audit_path=replay_audit,
)

fail_closed_cases = [
    ("未知工具", unknown_tool),
    ("未知事件", unknown_event),
    ("未登记的执行类工具", unregistered_execute),
    ("受控工具没接线", not_wired),
    ("判定超时", timeout_outcome),
    ("重放 event_id", replay_second),
]

print(pad("场景", 22) + "| " + pad("原因码", 26) + "| 写给模型的细节")
print("-" * 118)
for label, outcome in fail_closed_cases:
    detail = next(
        (line for line in outcome.stderr.splitlines() if line.startswith("detail:")), ""
    )
    print(pad(label, 22) + "| " + pad(outcome.reason_code, 26) + "| " + detail[8:74])

print()
for label, outcome in fail_closed_cases:
    assert outcome.exit_code == EXIT_BLOCK, (label, outcome.exit_code)
    print(pad(label, 22) + " 退出码 " + str(outcome.exit_code) + "｜工具不会执行")

print()
print(
    "重放的两次调用：第一次 exit",
    replay_first.exit_code,
    "；第二次 exit",
    replay_second.exit_code,
    f"（原因码 {replay_second.reason_code}）",
)
print("执行器总共只被调用", len(replay_executor.calls), "次：重放没有造成第二次执行。")
print("超时路径的执行器调用", len(slow_executor.calls), "次：超预算一律阻断。")

# ----------------------------------------------------------------------------
# **小结**：六类失败都落在同一条失败关闭路径上，而且都给得出原因码与细节，
# 不会出现"工具没执行但没人知道为什么"。其中两条是 Phase 4 带来的新面孔：
#
# - **未登记的执行类工具**（`tool_not_registered`）：Adapter 的工具表与 Tool Registry 是两张表，
#   前者的职责是"这确实是执行类动作"，后者的职责是"它被授权怎么做"；
# - **没接线**（`enforcement_unavailable`）：配置里少了 registry，受控工具一律不放行——
#   把"忘记接线"变成显式阻断，而不是悄悄退化成"没有治理"。
#
# 注意超时那一条：内部预算必须**严格小于** hooks.json 里的 timeout，
# 否则先被杀掉的是 Hook 进程，而被杀在 dsh 里等于放行。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 7. 命令行：退出码就是接口
#
# dsh 最终执行的是一行命令，所以接线的最后一环是 CLI：
#
#     python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml
#
# | 退出码 | dsh 的语义 | 本 Hook 什么时候用它 |
# | --- | --- | --- |
# | 0 | 放行；stdout 以 { 开头时才被当成结构化输出解析 | 判定 allow |
# | 2 | 阻断：工具不执行，stderr 作为理由显示给模型 | 违规、超时、未知工具、未知事件、未登记的执行类工具、没接线、门禁阻断、重放、内部错误 |
# | 其他 / 崩溃 / 被杀 | **非阻断失败**——工具照样执行 | Hook 绝不允许自己走到这里 |
#
# 于是有两条硬契约：**所有异常都转成 exit 2**；**放行时 stdout 必须为空**
# （提前写一行日志就会被 dsh 当成结构化输出解析）。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 用 `subprocess` 真的起一个 Python 进程来跑 CLI（命令与你在终端里敲的完全一致），
# 分别喂四个 stdin：违规事件、合规事件、执行类工具事件（会被 Phase 4 门禁拦住）、坏 JSON。
#
# 注意 `PYTHONPATH` 指向仓库的 `src/`，这样没安装项目也能跑；
# 在测试里这件事由 `tests/integration/test_dsh_hook.py` 用同样方式保证。
# ----------------------------------------------------------------------------

# 10. CLI 契约：退出码与"放行时 stdout 为空"
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


cli_results = {
    "block": run_hook_cli(
        ["--config", str(CONFIG_PATH)], json.dumps(event("pre-tool-use-edit-block.json"))
    ),
    "allow": run_hook_cli(
        ["--config", str(CONFIG_PATH)], json.dumps(event("pre-tool-use-edit-allow.json"))
    ),
    # 执行类工具：工具表认识它，但配置声明的主体没有 shell.exec —— 由 Phase 4 门禁阻断。
    "governed_execute": run_hook_cli(
        ["--config", str(CONFIG_PATH)], json.dumps(event("pre-tool-use-pwsh-execute.json"))
    ),
    "bad_stdin": run_hook_cli(["--config", str(CONFIG_PATH)], "{ not json"),
}

assert cli_results["block"].returncode == 2, cli_results["block"].stderr
assert cli_results["block"].stdout == ""
assert cli_results["allow"].returncode == 0
assert cli_results["allow"].stdout == "" and cli_results["allow"].stderr == ""
assert cli_results["governed_execute"].returncode == 2
assert "permission_denied" in cli_results["governed_execute"].stderr
assert cli_results["bad_stdin"].returncode == 2

print(
    f"违规事件：退出码 {cli_results['block'].returncode}"
    f"｜stdout 为空 {cli_results['block'].stdout == ''}"
    f"｜stderr 提到 ARCH-001@1 {'ARCH-001@1' in cli_results['block'].stderr}"
)
print(
    f"合规事件：退出码 {cli_results['allow'].returncode}"
    f"｜stdout 为空 {cli_results['allow'].stdout == ''}"
    f"｜stderr 也为空 {cli_results['allow'].stderr == ''}"
)
print(
    f"执行类工具：退出码 {cli_results['governed_execute'].returncode}"
    f"｜stderr 提到 permission_denied {'permission_denied' in cli_results['governed_execute'].stderr}"
    "（Phase 4 门禁：主体没有 shell.exec）"
)
print(
    f"坏 JSON ：退出码 {cli_results['bad_stdin'].returncode}"
    "｜解析失败也转成阻断，绝不让解释器带着默认失败码退出"
)
print()
print("阻断时 stderr 的第一行:", cli_results["block"].stderr.splitlines()[0])
print("stdout 是 dsh 解析结构化输出的通道，必须留给真正的结构化结果。")

# ----------------------------------------------------------------------------
# **小结**：同一个进程入口，四种输入，两个出口（0 放行 / 2 阻断）。
# "坏 JSON 也返回 2"看起来很小，但它是"崩溃等于放行"这条 dsh 语义的解药：
# Hook 宁可自己说"我看不懂"，也不能让解释器带着退出码 1 退出。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 接线现状：为什么还有一个进程内插件
#
# 上面讲的是 Python 侧的完整契约。但本机实测过一个偏差：按官方方式接上
# （@deepseek-ai/dsh-hooks-claude-code + hooks.json）之后，**Hook 进程确实被调用、
# 审计里也有 exit 2 的 block 记录，工具却仍然执行了**——桥的 deny 没有传递到 dsh 的工具管线。
# 最小复现与结论写在 `src/adapters/dsh/README.md` 第 7 节。
#
# 因此真实沙箱闭环改用 `src/adapters/dsh/policy-hook.plugin.mjs`：一个 30 行的进程内插件，
# 把 tools/pre-execute 转发给同一条 Python Hook 命令。**线协议完全不变**——
# stdin JSON、exit 0 放行、exit 2 阻断、stderr 即理由，本手册讲的一切都照旧；
# 它只额外补了两件桥没做的事：`ctx.shell` 抛错（起不来、被杀）时返回 deny，
# 以及 0 与 2 之外的退出码一律 deny。
#
# 换句话说：Adapter 与 Hook 的契约没有因为这次偏差改变一个字，变的只是"谁把事件递过来"。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 8. 审计与反馈：留下结论，不留下内容
#
# 每次 Hook 调用都是一个新进程，所以审计是**追加写的 JSONL**，一行一次调用。
# 它同时兼任幂等台账：键是 event_id，值是上一次判定的摘要与结论。
#
# 审计里写什么、不写什么是设计的一部分：
#
# | 写 | 不写 |
# | --- | --- |
# | 规则身份与规则集哈希 | 规则库全文 |
# | 事件的层、语言、依赖、工具、操作 | 工具参数原文（只有摘要） |
# | 决策、原因码、退出码、耗时 | 源码内容、用户消息、绝对路径、密钥 |
#
# 给模型的反馈同理：只给规则 ID、严重级别、原因、证据与期望的修复方向。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 读回 block 场景的审计记录，核对文档里写过的字段名，再确认三件事：
# 台账里没有源码内容、摘要以 `sha256:` 开头、反馈文本会把绝对路径换成占位符。
#
# 顺便看 Phase 4 在同一份审计文件里补了什么：允许路径多出 `action_hash` / `grant_id` /
# `grant_expires_at`，门禁阻断多出 `enforcement_reason` / `enforcement_detail`。
# ----------------------------------------------------------------------------

# 11. 审计与反馈：留下结论与摘要，不留下内容
audit_lines = (TMP_ROOT / "hook-block.jsonl").read_text(encoding="utf-8").splitlines()
# Phase 4 之后同一份文件里可能有两层记录：Phase 2 的用 audit_schema_version 标记，
# Phase 4 的用 schema_version（审计链）。这里取 Phase 2 的那一条。
audit_record = next(
    json.loads(line) for line in audit_lines if "audit_schema_version" in line
)

documented_audit_fields = (
    "audit_schema_version", "timestamp", "agent", "agent_version", "reason_code",
    "exit_code", "executed", "elapsed_ms", "rule_set_hash", "governed", "event_id",
    "request_id", "tool", "operation", "file", "layer", "language", "dependencies",
    "payload_digest", "payload_fields", "matched_rules", "skipped_rules", "decision",
)
missing = [name for name in documented_audit_fields if name not in audit_record]
assert not missing, missing
assert audit_record["decision"] == "block"
assert audit_record["payload_digest"].startswith("sha256:")

print("审计记录:", len(documented_audit_fields), "个文档字段全部存在")
print(pad("字段", 24) + "值")
print("-" * 78)
for name in (
    "timestamp", "agent", "agent_version", "reason_code", "exit_code", "executed",
    "decision", "file", "operation", "layer", "language", "dependencies",
    "payload_digest", "rule_set_hash", "matched_rules", "skipped_rules",
):
    print(pad(name, 24) + str(audit_record[name]))

print()
print("台账里没有源码内容:", all("from repository import" not in line for line in audit_lines))

# 允许路径：Phase 4 在同一份审计文件里补了与授权相关的字段。
allow_lines = (TMP_ROOT / "hook-allow.jsonl").read_text(encoding="utf-8").splitlines()
allow_phase2 = [json.loads(line) for line in allow_lines if "audit_schema_version" in line]
allow_phase4 = [json.loads(line) for line in allow_lines if "audit_schema_version" not in line]
grant_record = next(item for item in allow_phase2 if item["reason_code"] == "enforcement_allow")
documented_audit_fields_phase4 = (
    "action_hash", "action_id", "tool_id", "risk", "grant_id", "grant_expires_at",
)
print()
print("允许路径上 Phase 4 补的字段:", ", ".join(documented_audit_fields_phase4))
for name in documented_audit_fields_phase4:
    print("  {:<20}{}".format(name, grant_record[name]))
print("同一份审计文件里的两类记录: Phase 2", len(allow_phase2), "条 | Phase 4", len(allow_phase4), "条")

# 门禁阻断时多出的字段（来自 CLI 里那条执行类工具事件）。
blocked_records = [
    json.loads(line)
    for line in (TMP_ROOT / "config" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    if "enforcement_reason" in line
]
documented_block_fields = ("enforcement_reason", "enforcement_detail")
blocked_record = blocked_records[-1]
print()
print("门禁阻断时补的字段:", ", ".join(documented_block_fields))
print("  最近一条:", blocked_record["enforcement_reason"], "|", str(blocked_record["enforcement_detail"])[:60])

ledger = AuditLedger(TMP_ROOT / "replay.jsonl")
previous = ledger.lookup("sess-demo-0001:call-edit-allow")
print()
print(
    "台账按 event_id 查重:",
    previous is not None,
    "｜最近一次结论:",
    None if previous is None else previous["reason_code"],
    "（重放也被记在同一个 event_id 下）",
)
sensitive = "读取 " + str(PROJECT_ROOT) + "/src/shop/order_controller.py 失败"
print("通用脱敏规则（不知道仓库根）:", sanitize(sensitive))
print("Hook 的实际调用（知道仓库根）:", sanitize(sensitive, project_root=PROJECT_ROOT))

# ----------------------------------------------------------------------------
# **小结**：审计文件既是证据也是幂等台账——重放检测正是靠它，因为"上一个进程做过什么"
# 只能落在文件里。而给模型看的内容必须足够短、足够具体，又不带任何不能外泄的东西。
#
# Phase 4 之后同一份文件里同时有**两层记录**：Phase 2 的（`audit_schema_version`，一行一次调用）
# 与 Phase 4 的审计链（`schema_version` + `sequence` + `prev_digest`）。
# 它们共用同一份证据，是为了让"一次工具调用"在事后是一条完整链路，而不是两条互补的半链。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 9. 边界：Phase 2 不做什么
#
# | 没有引入 | 原因 | 现状 |
# | --- | --- | --- |
# | 知识检索 / 向量库 | 先有确定性的行为控制，再谈知识 | Phase 3 已完成；检索结果不参与授权 |
# | 让 Hook 自己执行工具 | 放行就是"允许 dsh 执行一次"，Hook 不越权 | 不打算做 |
# | 文件快照与回滚 | 撤销副作用是执行器的能力，不是 Hook 的 | Phase 4 的 driver 负责；能力不足时写 unsupported |
# | AST / 类型检查 | 确定性代码证据属于验证器 | Phase 5 |
# | MCP 工具与多 Agent 适配 | 工具表现在是白名单，MCP 需要声明式扩展 | Phase 6 |
# | HTTP 服务 | 还没有进程外共享的需求 | Phase 7 |
#
# 四条容易忽略的约定：
#
# 1. **未知一律失败关闭**：未知工具、未知事件、未知决策值、缺 layer 映射都阻断；
# 2. **不猜**：layer、language、principal、module 都不从文件名、目录或用户消息推断
#    （principal 只能来自配置——Phase 4 的门禁要用它决定权限）；
# 3. **崩溃等于放行**，所以任何异常都必须在本进程内转成 exit 2；
# 4. **两层判断各管一半**：规则（policy）回答"这个改动合不合规"，
#    注册表（enforcement）回答"这次调用被授权了吗"；Hook 负责把两层串起来，
#    任何一层说"不行"都转成 exit 2，绝不放行。
#
# ## 下一步
#
# Phase 3 引入了检索（让 Agent 知道"该怎么做"），Phase 4 引入了受控执行（让每一次受控调用
# 拿到绑定参数的授权，并在执行后交出证据）。Phase 2 这一层的位置没有变：
# **它仍然是"Agent 想做什么"与"策略层能不能拦得住"之间的那道门。**
#
# 自测一下：如果 dsh 升级后新增了一个写工具，这个 Hook 会放行还是阻断？下一个单元给出答案。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么（自测）
#
# 拿一个"未来的工具名"去跑映射。按照工具表是白名单的设计，它必须被拒绝，
# 并且错误信息要指出该去更新哪张表、补哪类测试。
# ----------------------------------------------------------------------------

# 12. 自测：dsh 升级后新增一个写工具，会发生什么？
future_tool = event(
    "pre-tool-use-write-block.json", tool_name="apply_patch", tool_use_id="call-future"
)
try:
    to_policy_event(future_tool, config=CONFIG)
except DshEventError as error:
    print("新工具被拒绝:", " ".join(str(error).split())[:118])
else:
    raise AssertionError("未登记的工具必须失败关闭")

print()
print("答案：先更新 src/adapters/dsh/adapter.py 的 TOOL_TABLE 并补契约测试，再升级 dsh。")
print("原因：'没见过就放行'会让新版本新增的写工具变成策略绕过通道。")
print("还有一条同源的注意事项：hooks.json 的 matcher 必须留空——")
print("写成 edit|write 会让新增工具根本进不了 Hook，等于没有治理。")

# ----------------------------------------------------------------------------
# **小结**：手册到这里结束。如果只记一句话，记这句：
# **策略层的价值不在于"告诉模型该怎么做"，而在于"在工具执行之前，它说了不算的时候还能拦住"。**
#
# 想继续往下读：Phase 3 的检索在 docs/project/learning/phase-3/，Phase 4 的受控执行在
# docs/project/learning/phase-4/（同一份 dsh 事件在受控链路里长什么样，Phase 4 手册的单元 9 与 11 有完整演示）。
# ----------------------------------------------------------------------------

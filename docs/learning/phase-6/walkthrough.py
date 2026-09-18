"""Phase 6 学习手册的纯 Python 版本（由 tools/build_learning_notebook.py 生成）。

notebook 里每一段代码都按顺序出现在下面；直接运行本文件即可复现全部输出：

    python docs/learning/phase-6/walkthrough.py

内容改动请修改 tools/build_learning_notebook.py 后重新生成，不要直接编辑本文件。
"""


# 0. 起步：定位仓库、准备规则与三个 Adapter
import json
import shutil
import sys
from pathlib import Path


def find_repo_root(start):
    candidate = Path(start).resolve()
    for _ in range(8):
        if (candidate / 'pyproject.toml').is_file():
            return candidate
        candidate = candidate.parent
    raise AssertionError('找不到仓库根：没有 pyproject.toml')


REPO_ROOT = find_repo_root(Path.cwd())
NOTEBOOK_DIR = REPO_ROOT / 'docs' / 'learning' / 'phase-6'
for extra in (REPO_ROOT / 'src', REPO_ROOT / 'tools'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from adapters.base import AdapterRegistry, ceiling_from_capabilities  # noqa: E402
from adapters.conformance import (  # noqa: E402
    SCENARIOS,
    conformance_enforcer,
    conformance_evidence,
    render_event,
    run_conformance,
)
from adapters.loader import load_adapters, load_registry_from_repo  # noqa: E402
from adapters.models import (  # noqa: E402
    CANONICAL_EVENT_SCHEMA_VERSION,
    AdapterEventError,
    AgentEvent,
    EnforcementLevel,
    EventType,
    parse_canonical_event,
)
from adapters.runtime import AgentRuntime, sanitize_message  # noqa: E402
from policy.loader import load_rule_set  # noqa: E402


def pad(text, width, align='left'):
    # 按**显示宽度**补位：中文在等宽字体里占 2 列，用 f-string 的 <N 会把表格挤歪。
    text = str(text)
    width_now = sum(2 if ord(char) > 0x2E7F else 1 for char in text)
    return text + ' ' * max(1, width - width_now)


WORKSPACE = REPO_ROOT / 'tests' / 'fixtures' / 'agent_events' / 'workspace'
OUTSIDE = WORKSPACE.parent / 'outside-workspace.py'
DEMO = REPO_ROOT / '.tmp' / 'notebook-demo' / 'phase-6'
# 每轮从空目录开始：台账是本轮的幂等记录，上一轮的文件会让本轮的事件
# 立刻被判成重放或熔断，失败原因就与被测行为无关了。
shutil.rmtree(DEMO, ignore_errors=True)
DEMO.mkdir(parents=True, exist_ok=True)
rules = load_rule_set([REPO_ROOT / 'policies'], repo_root=REPO_ROOT)
registry = load_registry_from_repo(REPO_ROOT)
adapters = load_adapters(
    ['dsh', 'generic-json', 'legacy-post-only'], root=REPO_ROOT, registry=registry
)
print('仓库根:', REPO_ROOT.name)
print('受控工作区:', WORKSPACE.relative_to(REPO_ROOT).as_posix())
print('接入的 Agent:', ', '.join(sorted(adapters)))


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
#
#         # Phase 6 学习手册：多 Agent Adapter
#
#         这份 notebook 用**实际运行的代码**解释 Phase 6 做了什么：让多个 Agent Runtime 通过同一套事件与决策协议接受一致治理，而**不修改 Policy Engine**。
#
#         ## Phase 6 要证明的事
#
#             Agent Runtime → Adapter.to_policy_event → AgentRuntime.handle → Policy Engine
#                          → Adapter.to_agent_response → Agent Runtime
#
#         一句话：**同一个语义事件，不管从哪个 Agent 来，都得到同一套结论。**
#
#         | 小节 | 回答的问题 |
#         | --- | --- |
#         | 1 | 规范事件长什么样？谁定义、谁消费 |
#         | 2 | 能力声明是数据：支持矩阵怎么算出来 |
#         | 3 | 一个语义事件怎么渲染成三家的线协议 |
#         | 4 | 一致性套件跑了什么、结论是什么 |
#         | 5 | 能力不足的 Agent 会怎样（不是跳过治理） |
#         | 6 | 跨 Agent 隔离：命名空间、trace、熔断 |
#         | 7 | 事件 → 上下文 → 决策：一次判定的完整链路 |
#         | 8 | 不一致会被发现吗（改声明不审核 / 路径越界） |
#         | 9 | 闭环与回归 |
#
#         角色：**规范事件**（`AgentEvent`）与实现无关；**Adapter** 只做协议转换；**Runtime** 是所有 Agent 共用的判定入口，负责隔离、幂等、trace 与熔断。
#
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
#
#         ## 1. 规范事件：协议在这里固化
#
#         1. `schema_version` 是**兼容轴**：消费方看不懂必须拒绝，不能降级成放行；
#         2. `EventType` 是受控枚举：未知事件类型一律拒绝；
#         3. `payload` 只允许受控字段（`path` / `params` / `text` / `cwd`），其余原始输入只留摘要。
#
# ----------------------------------------------------------------------------


# 1. 规范事件 Schema
print('规范事件协议版本:', CANONICAL_EVENT_SCHEMA_VERSION)
print('受控事件类型:', ', '.join(item.value for item in EventType))

document = {
    'schema_version': CANONICAL_EVENT_SCHEMA_VERSION,
    'event_id': 'sess-1:call-1',
    'event_type': 'tool.pre_execute',
    'request_id': 'sess-1:call-1',
    'tool': 'edit',
    'operation': 'edit',
    'payload': {'path': 'src/shop/order_controller.py', 'params': {'new_string': 'x = 1'}},
}
event = parse_canonical_event(document, agent_id='generic-json')
print()
print('一条规范事件:', event.event_type.value, '|', event.path)
print('需要判定:', event.decision_requested, '| 载荷摘要:', event.payload_digest[:32] + '...')
print()
print('未知事件类型会被拒绝：')
try:
    parse_canonical_event({**document, 'event_type': 'tool.teleport'}, agent_id='generic-json')
except AdapterEventError as error:
    print('   ', str(error)[:72])
print('小结：协议只有一份，Agent 之间的差异全部留在 Adapter 里。')

# ----------------------------------------------------------------------------
#
#         ## 2. 能力声明是数据：支持矩阵怎么算出来
#
#         每个 Agent 在自己的 `adapters/<agent_id>/manifest.yaml` 里声明事件名、字段名、工具表、阻断能力与审批能力；平台据此算出它**声明的能力上限**，并与 `adapters/approved.json` 的已审核哈希比对。`full` 仍不等于运行时已自动接好 Phase 4/5。
#
#         1. 没有执行前事件，或阻断能力不是 `pre_execute` → 上限 `read_only`；
#         2. 没有工具表 → 上限 `read_only`；
#         3. 申请值本身更低时以申请值为准（主动收紧是合法的）。
#
# ----------------------------------------------------------------------------


# 2. 支持矩阵：数据 → 结论
listing = registry.as_list()
print('已审核清单:', listing.approved_path)
print('审核人:', listing.reviewed_by, '| 时间:', listing.approved_at)
print()
print(pad('agent', 20) + pad('上限', 14) + pad('产品版本', 20) + pad('协议', 22) + pad('工具', 6) + '审核')
print('-' * 96)
for item in listing.descriptors:
    print(
        pad(item.agent_id, 20)
        + pad(item.enforcement.value, 14)
        + pad(item.agent_version, 20)
        + pad(item.protocol, 22)
        + pad(len(item.tools), 6)
        + ('是' if item.approved else '否')
    )
print()
for item in listing.descriptors:
    if item.ceiling_reasons:
        print('原因 [' + item.agent_id + ']: ' + '；'.join(item.ceiling_reasons))
print()
counts = (len(listing.governed()), len(listing.read_only()), len(listing.unsupported()))
print('三种状态:', counts[0], '个完整 enforcement /', counts[1], '个只读 /', counts[2], '个不支持')

# ----------------------------------------------------------------------------
#
#         ## 3. 一个语义事件怎么渲染成三家的线协议
#
#         - `dsh` 用 `PreToolUse` + `edit` + `file_path` / `new_string`；
#         - `generic-json` 用规范事件本身；
#         - `legacy-post-only` 只有 `PostToolUse`，用 `save_file`。
#
#         因此新增一个 Agent 只增加渲染分支，核心测试期望里没有 Agent 专用分支。
#
# ----------------------------------------------------------------------------


# 3. 同一场景 → 三种报文
scenario = next(item for item in SCENARIOS if item.name == 'block-controller-edit')
print('场景:', scenario.name)
print('说明:', scenario.description)
print()
for agent_id in sorted(adapters):
    try:
        raw = render_event(
            adapters[agent_id], scenario, index=0, workspace=WORKSPACE, outside=str(OUTSIDE)
        )
    except AdapterEventError as error:
        print(pad(agent_id, 20) + '不适用: ' + str(error)[:60])
        continue
    lookup = raw.get('tool_input', raw.get('payload', {}))
    tool = raw.get('tool_name') or raw.get('tool')
    path = lookup.get('file_path') or lookup.get('path')
    print(pad(agent_id, 20) + pad(str(tool), 12) + str(path))
print()
dsh_raw = render_event(adapters['dsh'], scenario, index=0, workspace=WORKSPACE, outside=str(OUTSIDE))
print('dsh 报文键:', ', '.join(sorted(dsh_raw)))

# ----------------------------------------------------------------------------
#
#         ## 4. 一致性套件：同一组语义事件、同一套结论
#
#         八条要求：等价事件产生等价上下文；路径与 operation 保留；**block 不触发原生工具**；**allow 只触发一次**；未知事件与版本被拒绝；错误响应可读但不泄露内部信息；重复 event ID 幂等；跨 Agent 隔离与循环限制。
#
#         报告必须让每个 Adapter 都产生检查项。能力受限的写动作应明确得到 `capability_unavailable`；
#         manifest 根本没声明的事件记为 `declared_inapplicable`，不能伪装成行为已通过。
#
# ----------------------------------------------------------------------------


# 4. 跑一遍一致性套件
import uuid
# 每次运行都用全新的套件目录：台账与 trace 登记表都是本轮的记录。
suite_dir = DEMO / ('conformance-' + uuid.uuid4().hex[:8])
print('一致性套件目录:', suite_dir.relative_to(REPO_ROOT).as_posix())
report = run_conformance(
    adapters=adapters,
    rules=rules,
    workspace=WORKSPACE,
    outside=OUTSIDE,
    ledger_dir=suite_dir / 'ledger',
    trace_path=suite_dir / 'traces.jsonl',
    breaker_limit=3,
)
conformance_result = 'pass' if report.ok else 'fail'
print('一致性套件结论:', conformance_result)
print('参与套件的 Adapter:', ', '.join(report.adapters))
print('场景数:', len(report.scenarios), '| 检查项:', len(report.checks), '| 失败:', len(report.failures))
for item in report.failures[:3]:
    print('   FAIL', item.adapter, item.scenario, item.name, '|', item.detail)
print()
per_adapter = {}
for item in report.checks:
    per_adapter[item.adapter] = per_adapter.get(item.adapter, 0) + 1
for agent_id in sorted(per_adapter):
    print(pad(agent_id, 20) + str(per_adapter[agent_id]) + ' 项检查')
print()
print('场景:', ', '.join(report.scenarios))

# ----------------------------------------------------------------------------
#
#         ## 5. 能力不足会怎样：不是跳过治理
#
#         `legacy-post-only` 只有 `PostToolUse`：能事后标错，但**副作用已经发生**。平台在接入阶段就把它算成 `read_only`，写类动作得到 `capability_unavailable`。
#
#         `dsh` 的 `full` 是能力上限；写类动作还必须注入 Phase 5 evidence provider 与 Phase 4 enforcer，
#         才能在 Policy allow 后拿到与参数绑定的 pre-check 授权。
#
# ----------------------------------------------------------------------------


# 5. 能力不足的 Agent 会被显式拒绝
capability_enforcer = conformance_enforcer(
    adapters['dsh'], workspace=WORKSPACE, state_root=DEMO / 'capability-enforcement'
)
runtime = AgentRuntime(
    adapters=adapters,
    rules=rules,
    ledger_path=DEMO / 'capability.jsonl',
    workspace=WORKSPACE,
    breaker_limit=30,
    enforcers={'dsh': capability_enforcer},
    evidence_providers={'dsh': conformance_evidence},
)
ceiling = ceiling_from_capabilities(adapters['legacy-post-only'].manifest)
print('上限:', ceiling.level.value, '| 申请值:', ceiling.requested)
print('原因:', '；'.join(ceiling.reasons))
print()
calls = []
legacy = runtime.handle(
    'legacy-post-only',
    {
        'hook_event_name': 'PostToolUse',
        'session_id': 'learn-legacy-1',
        'tool_name': 'save_file',
        'tool_use_id': 'call-1',
        'cwd': str(WORKSPACE),
        'tool_input': {'file_path': 'src/shop/order_controller.py', 'text': 'value = 1'},
    },
    execute=calls.append,
)
print('结论:', legacy.response.decision.value, '| 原因码:', legacy.outcome_code)
print('原生工具被调用:', len(calls), '次')
print('给 Agent 的说明:', legacy.response.message[:70])
print()
dsh_calls = []
accepted = runtime.handle(
    'dsh',
    {
        'hook_event_name': 'PreToolUse',
        'session_id': 'learn-dsh-1',
        'tool_name': 'edit',
        'tool_use_id': 'call-1',
        'cwd': str(WORKSPACE),
        'tool_input': {
            'file_path': 'src/shop/order_service.py',
            'old_string': 'pass',
            'new_string': 'value = 1',
        },
    },
    execute=dsh_calls.append,
)
print('dsh 结论:', accepted.response.decision.value, '| 工具被调用:', len(dsh_calls), '次')

# ----------------------------------------------------------------------------
#
#         ## 6. 跨 Agent 隔离：命名空间、trace、熔断
#
#         | 风险 | 机制 |
#         | --- | --- |
#         | A 的判定替 B 放行 | 台账键 `<adapter.namespace>:<event_id>`；默认 agent id，多份同型号 Agent 用 `ledger_alias` 区分 |
#         | 自称别人的身份 | `agent_id` 由装配处钉死；主体只认 Adapter 的显式声明 |
#         | 伪造父 trace | trace 登记表按 `owner_agent` 校验来源 |
#         | 互相触发的死循环 | 同一 Agent 在时间窗口内的事件数到上限即熔断 |
#         | 重复 event_id | 幂等台账：重放阻断，换参数则拒绝 |
#
# ----------------------------------------------------------------------------


# 6. 隔离与熔断
isolation_enforcer = conformance_enforcer(
    adapters['dsh'], workspace=WORKSPACE, state_root=DEMO / 'isolation-enforcement'
)
isolated = AgentRuntime(
    adapters=adapters,
    rules=rules,
    ledger_path=DEMO / 'isolation.jsonl',
    trace_path=DEMO / 'isolation-traces.jsonl',
    workspace=WORKSPACE,
    breaker_limit=2,
    enforcers={'dsh': isolation_enforcer},
    evidence_providers={'dsh': conformance_evidence},
)
first = isolated.handle(
    'dsh',
    {
        'hook_event_name': 'PreToolUse',
        'session_id': 'shared',
        'tool_name': 'edit',
        'tool_use_id': 'call-1',
        'cwd': str(WORKSPACE),
        'tool_input': {
            'file_path': 'src/shop/order_service.py',
            'old_string': 'pass',
            'new_string': 'v = 1',
        },
    },
    execute=lambda event: None,
)
second = isolated.handle(
    'generic-json',
    {
        'schema_version': '1.0',
        'event_id': 'shared:call-1',
        'event_type': 'tool.pre_execute',
        'request_id': 'shared:call-1',
        'tool': 'read',
        'operation': 'read',
        'payload': {'path': 'src/shop/order_service.py'},
    },
    execute=lambda event: None,
)
keys = sorted({item.get('ledger_key') for item in isolated.history_for('dsh') if item.get('ledger_key')})
print('dsh:', first.outcome_code, '| generic-json:', second.outcome_code)
print('台账键:', ', '.join(keys))
print()
forged = isolated.handle(
    'dsh',
    {
        'hook_event_name': 'PreToolUse',
        'session_id': 'forged',
        'tool_name': 'edit',
        'tool_use_id': 'call-1',
        'cwd': str(WORKSPACE),
        'tool_input': {
            'file_path': 'src/shop/order_service.py',
            'old_string': 'pass',
            'new_string': 'v = 2',
        },
        'parent_trace_id': 'never-issued',
    },
    execute=lambda event: None,
)
print('伪造父 trace:', forged.response.decision.value, '| 原因码:', forged.outcome_code)
print()
codes = []
for index in range(5):
    outcome = isolated.handle(
        'dsh',
        {
            'hook_event_name': 'PreToolUse',
            'session_id': 'loop-' + str(index),
            'tool_name': 'edit',
            'tool_use_id': 'call-' + str(index),
            'cwd': str(WORKSPACE),
            'tool_input': {
                'file_path': 'src/shop/order_service.py',
                'old_string': 'pass',
                'new_string': 'step_' + str(index) + ' = ' + str(index),
            },
        },
        execute=lambda event: None,
    )
    codes.append(outcome.outcome_code)
print('连续 5 次受治理事件（上限 2）:', codes)
print('小结：循环在第', codes.index('request_busy') + 1, '次被终止。')

# ----------------------------------------------------------------------------
#
#         ## 7. 一次判定的完整链路
#
#         Adapter 负责**翻译**；Runtime 负责**隔离与顺序**（trace → 上下文 → 能力门禁 → 原子 claim → Phase 5 证据 → Policy → Phase 4 pre/post → callback）；Engine 负责**判定**——Phase 6 没有改动它一行。
#
# ----------------------------------------------------------------------------


# 7. 事件 → 规范事件 → 上下文 → 决策
raw = {
    'hook_event_name': 'PreToolUse',
    'session_id': 'learn-chain',
    'tool_name': 'edit',
    'tool_use_id': 'call-1',
    'cwd': str(WORKSPACE),
    'tool_input': {
        'file_path': 'src/shop/order_controller.py',
        'old_string': 'pass',
        'new_string': 'from repository import OrderRepository',
    },
}
adapter = adapters['dsh']
event = adapter.to_policy_event(raw, workspace=WORKSPACE)
context = adapter.to_policy_context(event, workspace=WORKSPACE)
print('规范事件:', event.event_type.value, '|', event.tool, '|', event.path)
print('上下文:', json.dumps(json.loads(context.model_dump_json()), ensure_ascii=False))
print()
chain_enforcer = conformance_enforcer(
    adapter, workspace=WORKSPACE, state_root=DEMO / 'chain-enforcement'
)
chain = AgentRuntime(
    adapters={'dsh': adapter},
    rules=rules,
    ledger_path=DEMO / 'chain.jsonl',
    workspace=WORKSPACE,
    enforcers={'dsh': chain_enforcer},
    evidence_providers={'dsh': conformance_evidence},
)
calls = []
structured = chain.handle('dsh', raw, execute=calls.append)
print('结论:', structured.response.decision.value, '| 原因码:', structured.outcome_code)
print('命中规则:', ', '.join(structured.response.matched_rules))
print('原生工具被调用:', len(calls), '次')
native = adapter.response_from_decision(structured.response, event=structured.event)
print('原生响应（dsh 线协议）退出码:', native['exit_code'], '= 2 表示阻断')

# ----------------------------------------------------------------------------
#
#         ## 8. 不一致会被发现吗
#
#         1. 改了能力声明却没重新审核 → 哈希比对失败；
#         2. 路径越界 → 拒绝（含只读动作）；
#         3. 未知工具或版本 → 拒绝，并给出可读但不泄露内部信息的原因。
#
# ----------------------------------------------------------------------------


# 8. 漂移、越界与未知
approved = json.loads((REPO_ROOT / 'adapters' / 'approved.json').read_text(encoding='utf-8'))
tampered = json.loads(json.dumps(approved))
tampered['adapters']['dsh']['manifest_digest'] = 'sha256:' + '0' * 64
drifted = AdapterRegistry([registry.manifest('dsh')], approved=tampered)
descriptor = drifted.as_list().get('dsh')
print('漂移检测:', '已发现' if not descriptor.approved else '漏了')
print('   说明:', descriptor.ceiling_reasons[-1][:70])
escaped = {
    'hook_event_name': 'PreToolUse',
    'session_id': 'learn-escape',
    'tool_name': 'edit',
    'tool_use_id': 'call-1',
    'cwd': str(WORKSPACE),
    'tool_input': {'file_path': str(OUTSIDE), 'old_string': 'pass', 'new_string': 'x = 1'},
}
try:
    adapter.to_policy_event(escaped, workspace=WORKSPACE)
    print('越界路径: 放行了（缺陷）')
except AdapterEventError as error:
    print('越界路径: 已拒绝 -', str(error)[:60])
for label, patch in (
    ('未知工具', {'tool_name': 'definitely_not_a_tool'}),
    ('未知事件', {'hook_event_name': 'ToolTeleport'}),
):
    broken = dict(raw)
    broken.update(patch)
    try:
        adapter.to_policy_event(broken, workspace=WORKSPACE)
        print(label + ': 放行了（缺陷）')
    except AdapterEventError as error:
        print(label + ': 已拒绝 -', str(error)[:60])
leaked = chain.handle(
    'dsh',
    {**raw, 'session_id': 'learn-leak', 'tool_input': {'file_path': str(OUTSIDE), 'new_string': 'x'}},
    execute=lambda event: None,
)
printed = json.dumps(leaked.response.model_dump(mode='json'), ensure_ascii=False)
print('响应里是否含仓库绝对路径:', str(REPO_ROOT) in printed)
print('脱敏示例:', sanitize_message('failed at ' + str(REPO_ROOT) + '/src/a.py'))

# ----------------------------------------------------------------------------
#
#         ## 9. 闭环与回归
#
#         闭环工具 `tools/agent_loop.py` 跑 7 个场景 + 一致性套件，并把结论写进阶段证据。
#
# ----------------------------------------------------------------------------


# 9. 多 Agent 闭环
import agent_loop
exit_code = agent_loop.main(['--json'])
payload_path = REPO_ROOT / '.tmp' / 'artifacts' / 'phase-6-agents-result.json'
payload = json.loads(payload_path.read_text(encoding='utf-8'))
print('闭环退出码应为 0，实际得到:', exit_code)
print('结论:', payload['result'])
print()
print(pad('场景', 46) + '结果')
print('-' * 60)
for item in payload['scenarios']:
    print(pad(item['name'], 46) + ('通过' if item['passed'] else '失败'))
print()
print('一致性套件检查项:', payload['conformance']['checks'], '| 失败:', len(payload['conformance']['failures']))
print('支持矩阵:', ', '.join(sorted(payload['matrix'])))

# ----------------------------------------------------------------------------
#
#         ## 10. 这一章留下的判断
#
#         1. **协议只有一份**：Agent 之间的差异全部是数据，写在 manifest 里并受已审核哈希约束；
#         2. **能力必须诚实**：拦不住写类动作的 Agent 一律是只读上限，`capability_unavailable` 而不是跳过治理；
#         3. **写链不能缺环**：Phase 5 证据、Policy allow、Phase 4 pre-check 与原子 claim 全部通过后才能 callback；
#         4. **隔离靠机制**：命名空间、主体核对、trace 来源与熔断都由运行时强制，每条都有对抗用例；
#         5. **新增 Agent 不改核心**：一致性套件的场景是语义描述，新 Agent 只增加一个渲染分支。
#
#         当前只有 dsh 是真实产品接入；进入下一阶段的产品验收前，还要用第二个真实 Agent 的版本化 fixture
#         重跑一致性套件。Phase 7 会把这条判定链做成版本化 API，并补鉴权、隔离与可观测性。
#
# ----------------------------------------------------------------------------

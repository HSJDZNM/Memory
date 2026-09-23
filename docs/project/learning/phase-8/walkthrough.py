"""Phase 8 学习手册的纯 Python 版本（由 tools/build_learning_notebook.py 生成）。

notebook 里每一段代码都按顺序出现在下面；直接运行本文件即可复现全部输出：

    python docs/project/learning/phase-8/walkthrough.py

内容改动请修改 tools/build_learning_notebook.py 后重新生成，不要直接编辑本文件。
"""

# ----------------------------------------------------------------------------
# # Phase 8 学习手册：LangGraph 编排
#
# 这份 notebook 用**实际运行的代码**解释 Phase 8：在 Policy Platform 已经能独立服务多个
# Agent 之后，上面再盖一层"有状态、可循环、可恢复"的工作流。它不引入新代码，只调用仓库里
# 已经通过测试的模块，因此每一段输出都可以自己重跑验证。
#
# ## Phase 8 要证明的事
#
#     START
#       → 需求分析 → 规范检索 → 架构规划 → 实施
#       → 验证 ──FAIL──→ 修复 ──→ 验证        （循环，有硬上限）
#              └─PASS──→ 测试 → 收尾 → END
#       （节点要动手时：先问平台 → 再交 Phase 4 受控执行链）
#
# 一句话：**编排层只回答"工作流怎么往前走"，"某个动作允不允许"始终由平台回答。**
# 它没有规则、没有权限、没有证据语义，删掉整个 `src/orchestration/` 平台照常独立运行。
#
# ## 阅读路线
#
# | 小节 | 回答的问题 |
# | --- | --- |
# | 0 | 跑这份 notebook 需要什么前提 |
# | 1 | 最小状态长什么样，为什么它拒绝未知字段与绝对路径 |
# | 2 | 循环的硬上限是什么，失败码怎样决定终态 |
# | 3 | 图为什么是数据（节点、静态边、条件分支），未知标签为什么必须被拒绝 |
# | 4 | 用 fake Policy Client 跑一遍完整工作流，每个节点问了平台什么 |
# | 5 | 验证失败 → 修复 → 再验证；checkpoint 里存的为什么是"下一步" |
# | 6 | 同一份图交给两个引擎（参考实现 / LangGraph），报告逐字段相同 |
# | 7 | 中断之后从 checkpoint 恢复：决策路径与不中断时一致，且 checkpoint 里没有正文 |
# | 8 | 人工审批：没有审批就不动手，参数改一个字符旧审批立即作废 |
# | 9 | 失败关闭总表，以及这一层明确不做什么 |
#
# 每个代码单元末尾都有小结。**这份 notebook 不联网、不起端口、不调用 LLM**：
# 平台侧用 `ScriptedPolicyClient`（固定 allow / block / error 的假实现），
# 工具侧用 `RecordingToolRunner`（只记录、不落盘），所有产物写在
# `.tmp/learning-phase-8/` 下，跑完用 `python tools/cleanup.py` 清理即可。
#
# ## 三个角色
#
# - **图状态与引擎**（orchestration.models / engines）：状态是**不可变**的最小引用集合；
#   `StepExecutor` 负责与框架无关的那些事——上限记账、调节点、路由、落盘、失败映射；
# - **端口**（orchestration.client / tools / approvals）：问平台、动手、要审批。
#   三个端口都是显式注入的，因此"编排缺陷"与"平台缺陷"分得开（本手册全程用假实现）；
# - **平台**（policy / retrieval / validators / enforcement / policy_api）：判定只有一条路径，
#   编排层连 `policy.engine` 都不导入——它只通过客户端端口说话。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 0. 前提：怎么跑、需要什么
#
# - Python >= 3.11（仓库实际用 3.13）、pydantic 2、PyYAML；
# - **不需要安装 src/**：下面第一个代码单元自己把 src/ 与 tools/ 加进 sys.path；
# - **不需要起服务、不需要网络、不需要平台**：第 4 节起用 `ScriptedPolicyClient`
#   固定回答，第 8 节的审批记录写在自己造的演示目录里；
# - **第 6 节需要已安装的 langgraph**（Phase 8 的声明依赖是 langgraph>=1.2,<2）：
#   那一节要真的把同一份图交给 LangGraph 跑一遍，并证明两个引擎的报告逐字段相同；
#   其余小节只用不依赖第三方框架的参考引擎；
# - **不碰仓库真实文件**：所有演示产物写在 .tmp/learning-phase-8/ 下（演示工作区、
#   checkpoint、审批记录），而且第一个代码单元先清理——这份手册会被
#   **从两个工作目录各跑一遍**（仓库根与 docs/project/learning/phase-8/），临时目录必须每轮从零开始。
#
#     $env:PYTHONPATH = 'src'
#     jupyter lab docs/project/learning/phase-8/walkthrough.ipynb   # 交互式阅读
#     python docs/project/learning/phase-8/walkthrough.py           # 纯 Python 版，直接看输出
#
# 第一个代码单元的末尾会多出一小段生成器追加的表格工具函数（pad / display_width）：
# 中英混排的表格必须按**显示宽度**补位——f-string 的宽度写法数的是字符个数，
# 而中文在等宽字体里占 2 列，列会被挤歪。
# ----------------------------------------------------------------------------

# 0. 起步：定位仓库、把 src/ 加进 sys.path、准备一个干净的演示目录

import json
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path


def find_repo_root(start):
    '''从当前工作目录向上找仓库根：含 pyproject.toml / policies / .git 的那一层。'''

    candidate = Path(start).resolve()
    for _ in range(8):
        if any((candidate / marker).exists() for marker in ('pyproject.toml', 'policies', '.git')):
            return candidate
        candidate = candidate.parent
    raise AssertionError('找不到仓库根')


REPO_ROOT = find_repo_root(Path.cwd())
NOTEBOOK_DIR = REPO_ROOT / 'docs' / 'project' / 'learning' / 'phase-8'
# 仓库不把 src 装进 site-packages：import policy / orchestration 全靠这条路径。
for extra in (REPO_ROOT / 'src', REPO_ROOT / 'tools'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import orchestration  # noqa: E402
from orchestration.checkpoint import JsonCheckpointStore  # noqa: E402
from orchestration.client import (  # noqa: E402
    DecisionOutcome,
    PlatformReadiness,
    RetrievalOutcome,
    ScriptedPolicyClient,
    ValidationOutcome,
)
from orchestration.engines import StepExecutor  # noqa: E402
from orchestration.errors import (  # noqa: E402
    STATUS_BY_CODE,
    NodeContractError,
    OrchestrationError,
    status_for,
)
from orchestration.graph import DEFAULT_SPEC, END, ROUTERS, GraphSpec, Router  # noqa: E402
from orchestration.langgraph_engine import langgraph_version  # noqa: E402
from orchestration.limits import LIMIT_RULES, LimitKind, charge  # noqa: E402
from orchestration.models import (  # noqa: E402
    ArtifactKind,
    ArtifactRef,
    ContextRef,
    FailureCode,
    GraphState,
    NodeId,
    RunLimits,
    RunStatus,
    StageStatus,
    ValidationSummary,
    ViolationRef,
    empty_state,
)
from orchestration.nodes import Change, NodeContext, ScriptedAuthor, TaskSpec  # noqa: E402
from orchestration.runtime import OrchestrationConfig, build_assembly  # noqa: E402
from orchestration.tools import RecordingToolRunner, ToolOutcome  # noqa: E402
from pydantic import ValidationError  # noqa: E402

# 演示产物只写 .tmp/：每轮先删再建，第二次运行不能因为"文件已存在"失败。
DEMO = REPO_ROOT / '.tmp' / 'learning-phase-8'
shutil.rmtree(DEMO, ignore_errors=True)
DEMO.mkdir(parents=True, exist_ok=True)

installed = langgraph_version()
print('Python:', sys.version.split()[0])
print('仓库根:', REPO_ROOT.name, '| 工作目录:', Path.cwd().name or str(Path.cwd()))
print('编排状态协议 STATE_SCHEMA_VERSION:', orchestration.STATE_SCHEMA_VERSION,
      '（只描述图状态的形状，与 API 协议、决策协议无关）')
print('langgraph:', installed or '未安装（第 6 节会失败关闭：EngineUnavailableError）')
print('演示目录:', DEMO.relative_to(REPO_ROOT).as_posix(), '（每轮从空目录开始）')


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
# ## 0.1 三个端口都可以换掉：为什么先用 fake Policy Client
#
# 阶段计划 §2 写得很直白：**先用 fake Policy Client**，再接 Phase 7 的 HTTP API。
# 理由不是"省事"，而是**可诊断**：状态机出问题时，你要能确定是编排错了还是平台错了。
# 所以本手册全程注入三个端口，一个真的都不用：
#
# | 端口 | 协议 | 真实实现 | 本手册用的实现 |
# | --- | --- | --- | --- |
# | 问平台 | client.PolicyClient | ApiPolicyClient（标准库 HTTP，只走 Phase 7 公开路由）+ ResilientPolicyClient（熔断） | ScriptedPolicyClient（固定 allow / block / error，脚本用尽即失败关闭） |
# | 动手 | tools.ToolRunner（run + binding） | PlatformToolRunner（走 Phase 4 受控执行链，动作哈希由它算） | RecordingToolRunner（只记录请求，不落盘；绑定哈希覆盖工具与参数） |
# | 出候选改动 | nodes.ChangeAuthor | 真实系统里是模型 | ScriptedAuthor（按轮次回答的确定性作者） |
#
# 装配入口只有一个：`orchestration.runtime.build_assembly(config, task=..., author=..., client=..., tool_runner=..., checkpoint_store=...)`。
# 它做的事是显式的——没有全局单例、没有环境变量、不从"当前目录"猜路径：
#
# 1. 客户端：注入了就用注入的；否则要求 api_base_url + api_token，缺一个就
#    EngineUnavailableError（**没有"静默降级到假实现"这条路**）；
# 2. 工具端口：注入了就用注入的；否则装 Phase 4 受控执行链；
# 3. checkpoint：注入了就用注入的；否则按 config.checkpoint_dir 建 JsonCheckpointStore；
# 4. **兼容性凭据**：向平台要一次 readiness，取当前 rule_set_hash / index_version，
#    再加上工具注册表的身份哈希，构成 PlatformSnapshot。拿不到就是 None——
#    恢复时按"变了"处理（重新评估），绝不按"没变"处理。
#
# 下面这个代码单元把演示任务、候选改动与三个假端口准备好，后面每一节复用。
# ----------------------------------------------------------------------------

# 0.2 演示任务、候选改动与三个假端口

from enforcement.approvals import ApprovalRecord  # noqa: E402
from enforcement.models import utc_now  # noqa: E402
from policy.models import Decision  # noqa: E402

TARGET = 'src/shop/order_service.py'
RULE_SET_HASH = 'sha256:' + 'a' * 64
EVIDENCE_DIGEST = 'sha256:' + 'e' * 64
WRITTEN_DIGEST = 'sha256:' + 'f' * 64
INDEX_VERSION = 'idx-learning-8'

# 受控演示工作区：只有这一个文件，内容会随着"实施 / 修复"变化。
WORKSPACE = DEMO / 'workspace'
WORKSPACE.mkdir(parents=True, exist_ok=True)
SOURCES = {
    'initial': chr(10).join((
        'def total(items):',
        '    return 0',
        '',
    )),
    'implemented': chr(10).join((
        'def total(items):',
        '    return sum(item.price for item in items)',
        '',
    )),
    'repaired': chr(10).join((
        'def total(items):',
        '    return sum(item.price for item in items if item.price > 0)',
        '',
    )),
}


def write_text_with_retry(path, text):
    '''本机 Windows 上偶发 WinError 5（索引器/杀毒短暂持有句柄）：有界重试，语义不变。'''

    import time

    path.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(3):
        try:
            path.write_text(text, encoding='utf-8', newline=chr(10))
            return path
        except PermissionError as error:  # pragma: no cover - 依赖宿主环境
            last = error
            time.sleep(0.05 * (attempt + 1))
    raise last


def write_workspace(stage):
    '''把演示工作区写成某个阶段的版本（RecordingToolRunner 不落盘，所以由手册显式写）。'''

    return write_text_with_retry(WORKSPACE / TARGET, SOURCES[stage])


write_workspace('initial')

TASK = TaskSpec(
    task_id='learn-8',
    target=TARGET,
    requirement='把 total() 改成累加明细，且不引入新的依赖',
    layer='service',
    module='shop.order_service',
    query='service 层依赖规则',
    principal={'subject': 'alice', 'roles': ['developer']},
    trace_id='trace-learn-8',
)
# 第 0 轮改动：会被验证挡住。第 1 轮改动：按结构化 violation 修好的版本。
BROKEN = Change(
    path=TARGET,
    summary='直接累加（会被验证挡住）',
    old=chr(10).join(('    return 0', '')),
    replacement=chr(10).join(('    return sum(item.price for item in items)', '')),
    tokens=12,
    cost_units=3,
)
FIXED = Change(
    path=TARGET,
    summary='按结构化 violation 修复',
    old=BROKEN.replacement,
    replacement=chr(10).join(('    return sum(item.price for item in items if item.price > 0)', '')),
    tokens=9,
    cost_units=2,
)


def validate_outcome(failing):
    '''验证节点的回答：block 时带一条结构化 violation（修复节点只认它）。'''

    violations = ()
    if failing:
        violations = (
            ViolationRef(
                rule_id='ARCH-001',
                rule_version=1,
                severity='error',
                file=TARGET,
                line=2,
                message='service 层的改动必须保持既有语义',
            ),
        )
    return ValidationOutcome(
        decision=Decision.BLOCK if failing else Decision.ALLOW,
        request_id='<auto>',
        rule_set_hash=RULE_SET_HASH,
        evidence_digest=EVIDENCE_DIGEST,
        validators=('python.ast@1.0',),
        violations=violations,
    )


def fake_client(validates, evaluates=1, *, retrieval='ok', needs_approval=False):
    '''按脚本回答的假客户端：脚本用完之后的调用一律 PlatformUnavailableError。'''

    return ScriptedPolicyClient(
        evaluate_script=tuple(
            DecisionOutcome(
                decision=Decision.ALLOW,
                request_id='<auto>',
                rule_set_hash=RULE_SET_HASH,
                required_action='approval' if needs_approval else None,
            )
            for _ in range(evaluates)
        ),
        retrieve_script=(
            RetrievalOutcome(
                status=retrieval,
                request_id='<auto>',
                index_version=INDEX_VERSION,
                contexts=(
                    ContextRef(
                        chunk_id='chunk-1',
                        source_path='policies/architecture/ARCH-001.yaml',
                        digest='sha256:' + 'c' * 64,
                        license='project-policy',
                        tier='rule',
                    ),
                ),
            ),
        ),
        validate_script=tuple(validates),
        readiness_value=PlatformReadiness(
            state='ready', ready=True, rule_set_hash=RULE_SET_HASH, index_version=INDEX_VERSION
        ),
    )


def recording_runner(writes):
    '''只记录、不落盘的受控执行端口；writes 用完之后一律"不可用"（失败关闭）。'''

    return RecordingToolRunner(
        outcomes=tuple(
            ToolOutcome(
                status='executed',
                tool_id='orc.fs.edit',
                action_id='auto',
                final_outcome='delivered',
                changed=(
                    ArtifactRef(
                        artifact_id='orc.fs.edit:' + TARGET,
                        kind=ArtifactKind.CHANGE,
                        path=TARGET,
                        digest=WRITTEN_DIGEST,
                        bytes=len(SOURCES['implemented']),
                    ),
                ),
            )
            for _ in range(writes)
        )
    )


class RetryingStore:
    '''JsonCheckpointStore 外面极薄的一层：Windows 上偶发 WinError 5 时重试几次。

    这不是编排语义的一部分——格式、原子替换与摘要校验都由里层实现决定；
    它只是让手册在"新写入的文件被文件扫描器短暂占用"的环境里也能稳定重跑。
    '''

    def __init__(self, inner, attempts=5):
        self.inner = inner
        self.attempts = attempts
        self.retries = 0

    def path_for(self, task_id):
        return self.inner.path_for(task_id)

    def save(self, record):
        for attempt in range(self.attempts):
            try:
                return self.inner.save(record)
            except PermissionError:
                self.retries += 1
                if attempt == self.attempts - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def load(self, task_id):
        return self.inner.load(task_id)

    def exists(self, task_id):
        return self.inner.exists(task_id)


def scenario(name, *, engine='reference', client=None, runner=None, author=None,
             approvals=None, store=None):
    '''造一份装配：每个场景一个独立目录，checkpoint / 审批 / 台账互不覆盖。'''

    base = DEMO / 'runs' / name
    config = OrchestrationConfig(
        workspace=WORKSPACE,
        checkpoint_dir=base / 'checkpoints',
        registry_path=REPO_ROOT / 'registry' / 'tool-registry.yaml',
        approved_path=REPO_ROOT / 'registry' / 'tool-registry.approved.json',
        audit_path=base / 'audit.jsonl',
        ledger_path=base / 'ledger.jsonl',
        approvals_dir=approvals if approvals is not None else base / 'approvals',
        engine=engine,
        limits=RunLimits(),
    )
    assembly = build_assembly(
        config,
        task=TASK,
        author=author or ScriptedAuthor({0: BROKEN, 1: FIXED}),
        client=client if client is not None else fake_client(
            (validate_outcome(False), validate_outcome(False))
        ),
        tool_runner=runner if runner is not None else recording_runner(1),
        checkpoint_store=store if store is not None
        else RetryingStore(JsonCheckpointStore(config.checkpoint_dir)),
    )
    return config, assembly


def run_scenario(assembly, task=None):
    '''从"全新状态"开始跑一次；恢复场景也走这里（checkpoint 存在时引擎自己会恢复）。'''

    task = task or TASK
    state = empty_state(
        task.task_id,
        limits=RunLimits(),
        trace_id=task.trace_id,
        request_id=task.task_id + ':request',
    )
    return assembly.engine.run(task_id=task.task_id, state=state)


def node_path(report):
    '''决策路径：(节点, 路由标签, 阶段状态)——两份报告要比的就是它。'''

    return tuple((step.node, step.label, step.status) for step in report.steps)


print('演示任务:', TASK.task_id, '| 目标:', TARGET)
print('候选改动: 第 0 轮', BROKEN.digest()[:20] + '…', '| 第 1 轮', FIXED.digest()[:20] + '…')
print('工作区初版:', (WORKSPACE / TARGET).relative_to(REPO_ROOT).as_posix())
print()
print('小结：端口是显式的——换掉客户端、执行器或作者都不需要改节点代码；'
      '脚本用尽或没有注入客户端时一律失败关闭，不会"降级成放行"。')

# ----------------------------------------------------------------------------
# ## 1. 最小图状态：只放引用，不放正文
#
# 阶段计划 §1 要求"只保存推进工作流需要的引用"。落到代码上就是 GraphState 的字段清单：
#
# | 类别 | 字段 | 说明 |
# | --- | --- | --- |
# | 身份 | task_id / revision / stage / status | revision 每改一次状态 +1，checkpoint 靠它判断新旧 |
# | 平台引用 | traces（PolicyTraceRef）、contexts（ContextRef）、snapshot | 只有 request_id / 决定 / 哈希 / 来源路径，**没有正文** |
# | 工作产物 | artifacts（ArtifactRef）、plan、requirements | 路径 + 摘要 + 字节数；需求正文只在内存里的 TaskSpec |
# | 循环控制 | counters / limits / runs / approvals | runs 里是每个节点的一次执行记录（含幂等键） |
# | 失败 | failure | 失败码 + 节点 + 脱敏后的短说明 |
#
# 三条纪律值得单独说：
#
# 1. **不可变**：replace() 不是原地改，而是复制出一份新状态并把 revision +1。
#    于是 checkpoint 里存的每一版都是完整快照，不存在"半套状态"；
# 2. **相同输入 → 逐字节相同的状态**：没有墙钟时间、没有随机数、没有自增 ID，
#    digest() 就是规范化 JSON 的 sha256（键排序、无空格），可以直接拿来比对；
# 3. **严格解析**：未知字段、未知状态版本、绝对路径、含 ".." 的路径一律**报错**，
#    不是"忽略掉继续跑"。
# ----------------------------------------------------------------------------

# 1. 状态模型：revision、确定性摘要、以及四种"必须报错"的输入

initial = empty_state('learn-8', limits=RunLimits(max_repair_rounds=1))
moved = initial.replace(stage=NodeId.POLICY_RETRIEVAL)
charged = charge(moved, LimitKind.REPAIR_ROUNDS, 1)
state_revision_trace = (initial.revision, moved.revision, charged.revision)
state_digest_stable = initial.digest() == empty_state('learn-8', limits=RunLimits(max_repair_rounds=1)).digest()
state_digest_changes = initial.digest() != moved.digest()
print('revision 随每次修改 +1:', state_revision_trace)
print('相同输入得到相同摘要:', state_digest_stable, '| 改了字段摘要就变:', state_digest_changes)
print('摘要:', initial.digest())
print('状态里的字段:', ', '.join(sorted(initial.payload())))
print()


def refusal(reason):
    '''把 pydantic 的报错压成一句稳定的说明：去掉库自己的前缀，只留实质。'''

    first = reason.errors()[0]
    where = '.'.join(str(part) for part in first['loc'])
    message = first['msg'].replace('Value error, ', '')
    return (where + ' -> ' + message) if where else message


state_refusals = {}
for label, payload in {
    'unknown_field': {**initial.payload(), 'tools': ['rm -rf /']},
    'unknown_version': {**initial.payload(), 'state_schema_version': '9.9'},
}.items():
    try:
        GraphState.model_validate(payload)
        state_refusals[label] = '放行了（缺陷）'
    except ValidationError as error:
        state_refusals[label] = refusal(error)
for label, path in {
    'absolute_path': 'C:/tmp/order_service.py',
    'parent_path': 'src/../../order_service.py',
    'backslash': 'src' + chr(92) + 'shop/order_service.py',
}.items():
    try:
        ArtifactRef(artifact_id='change-1', kind=ArtifactKind.CHANGE, path=path, digest=WRITTEN_DIGEST)
        state_refusals[label] = '放行了（缺陷）'
    except ValidationError as error:
        state_refusals[label] = refusal(error)

print(pad('非法输入', 20) + '被拒绝的方式')
print('-' * 78)
for label, detail in state_refusals.items():
    print(pad(label, 20) + detail)
print()
print('小结：状态是不可变的最小引用集合；未知字段、未知版本、绝对路径与含 ".." 的路径'
      '都在进入状态之前就被拒绝——checkpoint 里因此不可能悄悄多出正文或越界路径。')

# ----------------------------------------------------------------------------
# ## 2. 循环的硬上限：上限是数据，失败码决定终态
#
# 阶段计划 §4：为 repair 次数、tool chain 深度、token、时间和费用设置硬上限，
# 超过上限进入 needs_human 或失败状态，不能无限自调用。
#
# 实现把"上限"拆成两半，两半都是数据：
#
# - RunLimits（每个任务可以给不同的预算）：repair 轮次、工具调用、节点执行、token、
#   费用、墙钟——默认值刻意保守（repair 2 轮、工具 4 次、节点 32 次）；
# - LIMIT_RULES（哪一种计数对应哪个上限字段、哪个失败码）——**代码里不写常数判断**，
#   charge(state, kind, n) 只是"查表 + 记账 + 比大小"。
#
# charge 的三个细节值得记住：
#
# 1. 它**返回新状态**（计数器只增不减，恢复时从 checkpoint 继续数，不会"重新开始数"）；
# 2. 击穿时抛 LimitExceeded，并把它换成该上限自己的失败码——**没有"截断后继续"**；
# 3. 失败码接着决定终态：errors.STATUS_BY_CODE 是唯一的映射表，
#    节点与引擎都不许自己发明一个状态（status_for 认不出来的码一律按 failed 处理）。
#
# 下面这张表就是那一层映射的全部内容——它是本节真正的契约，也是第 9 节那张
# "失败关闭总表"的底稿。**映射表必须覆盖每一个失败码**；如果输出了"没有登记终态"的失败码，
# 手册会照实打印出来，而不是替它圆场。
# ----------------------------------------------------------------------------

# 2. 上限表 + 失败码 → 终态的完整映射

limit_codes = {}
print(pad('上限类别', 16) + pad('计数字段', 14) + pad('上限字段', 20) + pad('失败码', 24) + '终态')
print('-' * 92)
for kind in LimitKind:
    rule = LIMIT_RULES[kind]
    mapped = rule.code in STATUS_BY_CODE
    limit_codes[kind.value] = (rule.counter, rule.limit, rule.code.value)
    print(pad(kind.value, 16) + pad(rule.counter, 14) + pad(rule.limit, 20)
          + pad(rule.code.value, 24) + STATUS_BY_CODE.get(rule.code, RunStatus.FAILED).value
          + ('' if mapped else '（表里没有这一行：按回落规则得到 failed）'))
print()

limit_exceeded = None
try:
    charge(charged, LimitKind.REPAIR_ROUNDS, 1)  # max_repair_rounds=1，上一节已经用过 1 轮
except OrchestrationError as error:
    limit_exceeded = (error.code.value, status_for(error).value, error.detail)
print('再记一轮 repair:', limit_exceeded[0], '→', limit_exceeded[1])
print('   ', limit_exceeded[2], '（没有截断，也没有继续）')
print()

failure_status_table = {code.value: STATUS_BY_CODE[code].value for code in FailureCode if code in STATUS_BY_CODE}
unmapped_failure_codes = tuple(sorted(code.value for code in FailureCode if code not in STATUS_BY_CODE))
failure_codes_total = len(list(FailureCode))
print(pad('失败码', 30) + '终态')
print('-' * 44)
for code in FailureCode:
    if code.value in failure_status_table:
        print(pad(code.value, 30) + failure_status_table[code.value])
print('-' * 44)
print('失败码共', failure_codes_total, '个；已登记终态', len(failure_status_table), '个。')
print('没有登记在 STATUS_BY_CODE 里的失败码:', unmapped_failure_codes or '（一个都没有）')
for code in unmapped_failure_codes:
    missing = FailureCode(code)
    print('   →', missing.value, '按 status_for 的回落规则得到:',
          STATUS_BY_CODE.get(missing, RunStatus.FAILED).value,
          '（表里少一行；文档若声称"每个失败码都有映射"，这就是反例）')
print()
print('小结：上限是数据、记账只增不减、击穿即抛错，终态由失败码查表决定；'
      '映射表是唯一的真相来源，缺哪一行都会在输出里露出来。')

# ----------------------------------------------------------------------------
# ## 3. 图是数据：节点、静态边、条件分支
#
# 编排层刻意把"工作流长什么样"与"谁来驱动它"分开：
#
# - **静态边**写在 DEFAULT_SPEC.edges 里（需求 → 检索 → 规划 → 实施 → 验证……）；
# - **条件分支**是具名纯函数（ROUTERS）：输入是 GraphState，输出是一个**标签**，
#   再由 GraphSpec 把标签映射到目标节点；
# - 两个引擎（参考实现与 LangGraph）读的是**同一份 spec**，引擎里不写死任何一条边。
#
# 为什么标签必须被严格检查？因为"猜下一步"在治理系统里等于"绕过了一个分支"。所以：
#
# 1. 路由函数返回的标签必须在本节点的 Router.targets 里登记过，
#    否则 NodeContractError（终态 failed）；
# 2. 分支名必须在 ROUTERS 里有实现，GraphSpec.problems() 会在装配时自检；
# 3. 静态出边必须**唯一**——一个节点有两条静态出边就不知道该走哪条，同样是拒绝；
# 4. 分支只看**结构化结论**：validation_outcome 读的是 ValidationSummary.decision，
#    没有验证结果就报错，绝不"没有结果就算通过"。
# ----------------------------------------------------------------------------

# 3. 图定义 + 三种"走不下去"的拒绝

from orchestration.approvals import ApprovalGate  # noqa: E402
from orchestration.graph import validation_outcome  # noqa: E402

spec_problems = DEFAULT_SPEC.problems()
print('入口:', DEFAULT_SPEC.entry, '→ 出口:', END, '| 自检问题:', spec_problems or '（无）')
print('节点:', tuple(node.value for node in NodeId))
print('路由函数:', tuple(sorted(ROUTERS)))
print()
print(pad('静态边', 32) + '目标')
print('-' * 52)
for edge in DEFAULT_SPEC.edges:
    print(pad(edge.source, 32) + edge.target)
print()
print(pad('条件分支', 32) + '标签 → 目标')
print('-' * 64)
for router in DEFAULT_SPEC.routers:
    for label, target in sorted(router.targets.items()):
        print(pad(router.source + ' [' + router.name + ']', 32) + label + ' → ' + target)
print()

# 反例一：路由目标写错（数据层就拒绝）
unknown_target_refused = ''
try:
    Router(name='validation_outcome', source='validation', targets={'pass': 'teleport'})
except ValidationError as error:
    unknown_target_refused = refusal(error)
print('条件分支指向未知节点:', unknown_target_refused)

# 反例二：一个节点没有任何出边 —— problems() 会指出来
holey = GraphSpec(entry=DEFAULT_SPEC.entry, edges=DEFAULT_SPEC.edges,
                  routers=(DEFAULT_SPEC.routers[0],))
print('少了 testing 分支时的自检问题:', holey.problems())

# 反例三：路由函数给出一个没登记的标签 —— 引擎必须拒绝猜下一步
failing_summary = ValidationSummary(
    decision=Decision.BLOCK,
    status=StageStatus.FAILED,
    request_id='learn-8:validation:0',
    rule_set_hash=RULE_SET_HASH,
    violations=(ViolationRef(rule_id='ARCH-001', rule_version=1, severity='error',
                             file=TARGET, line=2, message='演示用的结构化 violation'),),
)
failing_state = empty_state('learn-8').replace(validation=failing_summary, stage=NodeId.VALIDATION)
narrow_spec = GraphSpec(
    entry=DEFAULT_SPEC.entry,
    edges=DEFAULT_SPEC.edges,
    routers=(Router(name='validation_outcome', source='validation', targets={'pass': 'testing'}),
             DEFAULT_SPEC.routers[1]),
)
print('把 fail 这一格删掉之后的自检问题:', narrow_spec.problems() or '（无：图本身是完整的）')
print('纯函数给出的标签:', validation_outcome(failing_state),
      '| 这个标签在窄图里的目标:', narrow_spec.router_for('validation').targets.get('fail'))
probe_context = NodeContext(
    task=TASK,
    client=ScriptedPolicyClient(),          # 空脚本：只用来构造执行器，不会被调用
    runner=RecordingToolRunner(),
    author=ScriptedAuthor({}),
    approvals=ApprovalGate(DEMO / 'no-approval.json'),
    workspace=WORKSPACE,
)
probe_executor = StepExecutor(node_context=probe_context, spec=narrow_spec)
route_label_refused = ''
try:
    probe_executor.route(failing_state, 'fail')
except NodeContractError as error:
    route_label_refused = error.code.value
    route_label_detail = error.detail
print('执行器的反应:', route_label_refused, '→', route_label_detail)
print()
print('小结：图是数据 + 纯函数，装配时自检；分支只认结构化 Decision，'
      '任何"这个标签我没见过"的情况都必须是显式失败，而不是猜一个下一步。')

# ----------------------------------------------------------------------------
# ## 4. 用假客户端跑一遍完整工作流
#
# 现在把图真的跑起来。这一节要看的是**每一步的账**：
#
# - 走的节点顺序与每个节点给出的路由标签；
# - 每个节点问平台了什么（ScriptedPolicyClient.calls 记下了每一次调用）；
# - 状态里攒下的平台判定引用（PolicyTraceRef：request_id + 决定 + 规则集哈希）；
# - 计数器（节点执行次数、工具调用次数、token、费用）。
#
# 有一条容易被忽略的纪律：**节点不自己决定"下一步去哪"**。implementation 只返回
# 一个 "ok"，是 validation_outcome 这个纯函数读 ValidationSummary.decision 决定
# 去 testing 还是 repair。所以"PASS/FAIL 分支由结构化 Decision 决定"这件事
# 不是靠约定，而是代码里根本没有第二个判断入口。
#
# 另外注意 request_id 的形状：&lt;task&gt;:&lt;节点&gt;:&lt;repair 轮次&gt;——**确定性**的。
# 同一个任务、同一个节点、同一轮次永远得到同一个 ID，这样幂等键、审计与重放才对得上。
# ----------------------------------------------------------------------------

# 4. 完整工作流（happy path）：实施一次写入，验证与测试都通过

happy_config, happy_assembly = scenario(
    'happy',
    client=fake_client((validate_outcome(False), validate_outcome(False))),
    runner=recording_runner(1),
)
happy_report = run_scenario(happy_assembly)
happy_status = happy_report.status.value
happy_steps = node_path(happy_report)
happy_engine = happy_report.engine
traces_by_node = {trace.node.value: trace for trace in happy_report.state.traces}

print(pad('节点', 24) + pad('标签', 8) + pad('状态', 9) + pad('平台 request_id', 28) + '平台决定')
print('-' * 88)
for step in happy_report.steps:
    trace = traces_by_node.get(step.node)
    print(pad(step.node, 24) + pad(step.label, 8) + pad(step.status, 9)
          + pad('-' if trace is None else trace.request_id, 28)
          + ('（这一步没有结构化 Decision）' if trace is None else trace.decision.value))
print('-' * 88)
print('引擎:', happy_engine, '| 终态:', happy_status, '| 步骤数:', len(happy_report.steps))
print()

happy_calls = tuple((route, call.request_id) for route, call in happy_assembly.client.calls)
print('假客户端收到的调用:', happy_calls)
print('工具端口被调用:', len(happy_assembly.tool_runner.calls), '次')
for request in happy_assembly.tool_runner.calls:
    print('   动作:', request.tool_id, '| action_id:', request.action_id,
          '| 参数键:', sorted(request.params))
print()
happy_traces = tuple((trace.node.value, trace.request_id, trace.decision.value)
                     for trace in happy_report.state.traces)
happy_counters = happy_report.state.counters.model_dump()
happy_artifacts = tuple((item.artifact_id, item.path) for item in happy_report.state.artifacts)
print('状态里的平台引用:', happy_traces)
print('计数器:', json.dumps(happy_counters, ensure_ascii=False))
print('artifact 引用:', happy_artifacts)
print('trace 原样回声:', happy_assembly.client.calls[0][1].trace_id, '==', happy_report.state.trace_id,
      '→', happy_assembly.client.calls[0][1].trace_id == happy_report.state.trace_id)
print()
print('小结：一次完整工作流 = 1 次检索 + 1 次实施判定 + 2 次验证判定；'
      '状态里留下的是引用与计数，不是"模型说它做完了"。')

# ----------------------------------------------------------------------------
# ## 5. 失败 → 修复 → 通过，以及 checkpoint 里到底存了什么
#
# 把验证节点的回答换成"先 block 一次、再 allow"，工作流就会走
# validation --fail--> repair --> validation --pass--> testing --> review。
# 修复节点有两条硬纪律：
#
# 1. **没有结构化 violation 就拒绝修**（NodeContractError）——不允许"凭感觉改"；
# 2. 修复轮次先记账再动手（charge(..., LimitKind.REPAIR_ROUNDS, 1)），
#    超限直接进 needs_human，不会无限自调用。
#
# 这一节还要把一个最容易被误解的顺序当场演示出来。StepExecutor.step 的顺序是：
#
#     上限记账 → 调节点 → 路由（算出下一步）→ 把"带着下一步的状态"落盘
#
# 所以 checkpoint 里保存的**是下一步要做什么**，而不是"刚刚做完什么"。
# 于是"checkpoint 之后崩溃"永远不会让恢复重跑刚刚完成的那个节点——
# "恢复不重复副作用"靠的就是这个顺序，不是靠运气。
#
# 还有一笔容易看漏的落盘：节点在**动手之前**会先写一笔"意图"（intent）并立刻刷盘，
# 动手之后再结算（settle）。下面那张序列里同一个阶段连续出现两次，就是这一笔。
# ----------------------------------------------------------------------------

# 5. 失败 → 修复 → 通过；并记录每一次落盘的"下一步阶段"


class StageRecorder:
    '''包在 JsonCheckpointStore 外面的观察者：真实落盘仍由 JsonCheckpointStore 做。

    编排层没有"落盘回调"这种钩子，而这一节要证明的恰恰是"每次落盘的 stage 是下一步"，
    所以这里只做一层薄薄的转发——写入、原子替换、摘要校验都还是原实现。
    '''

    def __init__(self, inner):
        self.inner = inner
        self.saved = []

    def save(self, record):
        self.saved.append((record.sequence, record.stage, record.revision))
        self.inner.save(record)

    def load(self, task_id):
        return self.inner.load(task_id)

    def exists(self, task_id):
        return self.inner.exists(task_id)


repair_store = StageRecorder(
    RetryingStore(JsonCheckpointStore(DEMO / 'runs' / 'repair' / 'checkpoints'))
)
repair_config, repair_assembly = scenario(
    'repair',
    client=fake_client((validate_outcome(True), validate_outcome(False), validate_outcome(False)), evaluates=2),
    runner=recording_runner(2),
    store=repair_store,
)
repair_report = run_scenario(repair_assembly)
repair_steps = node_path(repair_report)
repair_counters = repair_report.state.counters.model_dump()
repair_runner_calls = len(repair_assembly.tool_runner.calls)

print(pad('节点', 24) + pad('标签', 8) + pad('状态', 9) + '说明')
print('-' * 92)
for step in repair_report.steps:
    print(pad(step.node, 24) + pad(step.label, 8) + pad(step.status, 9) + step.detail)
print('-' * 92)
print('终态:', repair_report.status.value, '| 修复轮次:', repair_counters['repair_rounds'],
      '| 工具调用:', repair_counters['tool_calls'], '次（端口真实收到:', repair_runner_calls, '）')
print('计数器:', json.dumps(repair_counters, ensure_ascii=False))
print()

checkpoint_stage_trace = tuple(repair_store.saved)
record = repair_store.load(TASK.task_id)
checkpoint_stage = record.stage
checkpoint_sequence = record.sequence
print(pad('落盘序号', 10) + pad('checkpoint 里的 stage', 26) + pad('revision', 10) + '意味着')
print('-' * 92)
for index, (sequence, stage, revision) in enumerate(checkpoint_stage_trace):
    previous = checkpoint_stage_trace[index - 1][1] if index else None
    last = index == len(checkpoint_stage_trace) - 1
    if stage == previous and last:
        meaning = '工作流走到终点：终态落盘（stage 仍是收尾节点）'
    elif stage == previous:
        meaning = '节点还没结束：这是动手前的"意图"落盘'
    elif previous is None:
        meaning = '起点跑完 requirement_analysis，下一次要跑 ' + stage
    else:
        meaning = '刚跑完 ' + previous + '，下一次要跑 ' + stage
    print(pad(sequence, 10) + pad(stage, 26) + pad(revision, 10) + meaning)
print('-' * 92)
print('最后一份 checkpoint: stage =', checkpoint_stage, '| sequence =', checkpoint_sequence,
      '| 状态里的阶段 =', repair_report.state.stage.value)
print()
print('小结：FAIL 走修复、修复后再验证；checkpoint 保存的是"下一步"，'
      '动手前还有一笔意图落盘——恢复因此既不会重跑已完成的节点，也不会重放未知的副作用。')

# ----------------------------------------------------------------------------
# ## 6. 两个引擎，一份语义：编排是可替换的
#
# 阶段计划的观察点是"**替换 LangGraph 后，Policy API、规则、索引、Validator 与 Adapter
# 应继续工作**"。代码上的做法是把控制流再切一刀：
#
# - StepExecutor（与框架无关）：上限记账、调节点、路由、落盘、失败映射；
# - ReferenceEngine：一个 while 循环驱动它，不依赖任何第三方框架；
# - LangGraphEngine：把**同一份 spec** 交给 LangGraph 的 StateGraph，
#   节点函数与条件边仍然回调同一个 StepExecutor。
#
# 于是"换掉编排框架"不是口号，而是可以当场断言的一件事：同一组场景跑两个引擎，
# RunReport 的载荷必须逐字段相同（引擎名、耗时、落盘次数这三样除外）。
#
# 还有两条边界值得注意：
#
# - 只有 langgraph_engine.py 导入 langgraph，而且是**构造引擎时**才导入；
#   版本不认识就 EngineUnavailableError，不"尽力兼容"；
# - 静态边在 LangGraph 里也被改造成条件边：否则某个节点失败之后，
#   图还会沿着静态边继续往下跑——那就成了"失败之后继续动手"。
# ----------------------------------------------------------------------------

# 6. 同一份图，两个引擎：报告逐字段比对

engine_payloads = {}
engine_names = {}
for engine in ('reference', 'langgraph'):
    config, assembly = scenario(
        'engine-' + engine,
        engine=engine,
        client=fake_client((validate_outcome(False), validate_outcome(False))),
        runner=recording_runner(1),
    )
    report = run_scenario(assembly)
    engine_names[engine] = report.engine
    engine_payloads[engine] = report.to_payload()
    print(pad(engine, 12) + '引擎自述: ' + pad(report.engine, 12)
          + '| 终态: ' + pad(report.status.value, 12)
          + '| 落盘: ' + pad(report.checkpoints, 4)
          + '| 状态摘要: ' + report.state.digest()[:26] + '…')

# 这三样本来就允许不同：引擎名、墙钟耗时、落盘次数（不同实现的记账粒度）。
engine_dropped = ('engine', 'elapsed_ms', 'checkpoints')
reference_payload = {key: value for key, value in engine_payloads['reference'].items()
                     if key not in engine_dropped}
langgraph_payload = {key: value for key, value in engine_payloads['langgraph'].items()
                     if key not in engine_dropped}
engine_payload_differences = tuple(sorted(
    key for key in set(reference_payload) | set(langgraph_payload)
    if reference_payload.get(key) != langgraph_payload.get(key)
))
engine_payloads_identical = not engine_payload_differences
print()
print('langgraph 版本:', installed)
print('比对时丢掉的字段:', engine_dropped)
print('载荷不同的字段:', engine_payload_differences or '（一个都没有）')
print('两个引擎的报告逐字段相同:', engine_payloads_identical)
print('两个引擎的状态摘要相同:',
      engine_payloads['reference']['state_digest'] == engine_payloads['langgraph']['state_digest'])
print('两个引擎的决策路径相同:',
      tuple(step['node'] for step in engine_payloads['reference']['steps'])
      == tuple(step['node'] for step in engine_payloads['langgraph']['steps']))
print()
print('小结：编排是可替换的——节点、静态边、条件分支只有一份定义，'
      '两个引擎给出同一份报告；换框架不会改变任何判定语义。')

# ----------------------------------------------------------------------------
# ## 7. checkpoint 与恢复：中断之后接着跑，而不是从头再跑
#
# 恢复这件事最容易被误解，所以这一节用一次**真的中断**来演示：
#
# 1. 先完整跑一遍（对照组）；
# 2. 再跑一遍，但让客户端在"测试节点问平台"的那一刻抛 KeyboardInterrupt
#    （模拟进程被杀）。此时 checkpoint 里的 stage 应该是 testing——
#    **下一次要跑的节点**，而不是刚跑完的 validation；
# 3. 从同一个 checkpoint 目录、同一个 task_id 再跑一次：引擎会恢复，从 testing 继续；
# 4. 对照两份报告：决策路径必须完全一致，而且恢复后**没有发生新的写入**；
# 5. 最后读一遍 checkpoint 原文：需求正文、改动的代码内容、仓库绝对路径
#    **都不应该出现在里面**。
#
# 恢复的兼容性判定也值得记住（plan_resume 给出四种结论）：
#
# | 情况 | 结论 | 行为 |
# | --- | --- | --- |
# | 没有 checkpoint | fresh | 从头开始 |
# | 规则集 / 索引变了 | revalidate | 清掉旧 trace 与旧验证结果，回到检索节点重评，**不沿用旧 allow** |
# | 工具 schema 变了 | reapprove | 旧审批作废，重新审批 |
# | 协议世代变了 | （抛错） | 拒绝恢复，必须重新开始 |
# | 其余 | resume | 接着上次的阶段继续 |
#
# 本节的演示里平台凭据没变，所以走的是 resume。
# ----------------------------------------------------------------------------

# 7a. 对照组跑一遍，再制造一次"进程被杀"的中断


class InterruptingClient:
    '''包在假客户端外面：在第 N 次某个路由的调用上抛 KeyboardInterrupt（模拟进程被杀）。'''

    def __init__(self, inner, *, route, occurrence):
        self.inner = inner
        self.route = route
        self.occurrence = occurrence
        self.seen = 0

    def _maybe_interrupt(self, route):
        if route == self.route:
            self.seen += 1
            if self.seen == self.occurrence:
                raise KeyboardInterrupt('模拟进程被杀：第 ' + str(self.seen) + ' 次 ' + route + ' 调用')

    def evaluate(self, call):
        self._maybe_interrupt('evaluate')
        return self.inner.evaluate(call)

    def retrieve(self, call):
        self._maybe_interrupt('retrieve')
        return self.inner.retrieve(call)

    def validate(self, call):
        self._maybe_interrupt('validate')
        return self.inner.validate(call)

    def readiness(self):
        return self.inner.readiness()


baseline_config, baseline_assembly = scenario(
    'resume-baseline',
    client=fake_client((validate_outcome(True), validate_outcome(False), validate_outcome(False)), evaluates=2),
    runner=recording_runner(2),
)
baseline_report = run_scenario(baseline_assembly)
baseline_path = node_path(baseline_report)
print('对照组:', baseline_report.status.value, '| 步骤', len(baseline_report.steps))
for step in baseline_report.steps:
    print('    ', pad(step.node, 24) + pad(step.label, 8) + step.status)
print()

interrupted_config, interrupted_assembly = scenario(
    'resume-interrupted',
    client=InterruptingClient(
        fake_client((validate_outcome(True), validate_outcome(False), validate_outcome(False)), evaluates=2),
        route='validate', occurrence=3),
    runner=recording_runner(2),
)
interrupted_error = ''
try:
    run_scenario(interrupted_assembly)
except KeyboardInterrupt as error:
    interrupted_error = str(error)

interrupted_store = interrupted_assembly.checkpoint_store
interrupted_record = interrupted_store.load(TASK.task_id)
interrupted_checkpoint_stage = interrupted_record.stage
print('中断:', interrupted_error)
print('中断后 checkpoint: sequence =', interrupted_record.sequence,
      '| stage =', interrupted_record.stage,
      '| 状态里的 status =', interrupted_record.state['status'])
print('已经完成的节点:', tuple(run['node'] for run in interrupted_record.state['runs']))
print('已经攒下的 artifact:', tuple(item['artifact_id'] for item in interrupted_record.state['artifacts']))
print('中断时的计数器:', json.dumps(interrupted_record.state['counters'], ensure_ascii=False))
print()
print('小结：落盘发生在"路由之后"，所以 checkpoint 里的 stage 是**还没跑的那个节点**；'
      '中断只是让当前这次调用没有返回，已经完成的工作一条都没丢。')

# 7b. 从同一个 checkpoint 恢复：路径一致、不再动手、正文不在文件里

# RecordingToolRunner 不落盘，所以这里显式把"修复后的版本"写进演示工作区，
# 模拟第一次运行已经真实落盘的结果（真实写盘由 Phase 4 受控执行链负责）。
write_workspace('repaired')
resume_runner = recording_runner(0)   # 一个额度都不给：恢复后若再动手，就会因"不可用"被拦下
resume_config, resume_assembly = scenario(
    'resume-interrupted',
    client=fake_client((validate_outcome(False),)),
    runner=resume_runner,
)
resumed_report = run_scenario(resume_assembly)
resumed_steps = node_path(resumed_report)
resume_path_equal = resumed_steps == baseline_path
resume_runner_calls = len(resume_runner.calls)
resumed_flags = (resumed_report.resumed, resumed_report.resume_mode)

from_checkpoint = len(interrupted_record.state['runs'])
print(pad('节点', 24) + pad('标签', 8) + pad('状态', 9) + '来源')
print('-' * 88)
for index, (node, label, status) in enumerate(resumed_steps):
    origin = 'checkpoint 里已经完成' if index < from_checkpoint else '本次恢复后跑的'
    print(pad(node, 24) + pad(label, 8) + pad(status, 9) + origin)
print('-' * 88)
print('resumed =', resumed_flags[0], '| resume_mode =', resumed_flags[1],
      '| 恢复后新增的工具调用:', resume_runner_calls)
print('恢复后的决策路径 == 不中断的决策路径:', resume_path_equal)
print('恢复后新跑的节点:', tuple(node for node, label, status in resumed_steps[from_checkpoint:]))
print()

checkpoint_file = interrupted_store.path_for(TASK.task_id)
checkpoint_text = checkpoint_file.read_text(encoding='utf-8')
leak_checks = {
    '需求正文': TASK.requirement,
    '改动的代码内容': 'sum(item.price for item in items)',
    '仓库绝对路径': str(REPO_ROOT),
    '演示工作区的文件内容': SOURCES['repaired'].strip(),
}
checkpoint_leaks = tuple(label for label, needle in leak_checks.items() if needle in checkpoint_text)
print('checkpoint 文件:', checkpoint_file.relative_to(REPO_ROOT).as_posix(),
      '|', len(checkpoint_text), '字节（缩进两空格的规范化 JSON）')
print(pad('不该出现的内容', 24) + '在文件里找到了吗')
print('-' * 54)
for label, needle in leak_checks.items():
    print(pad(label, 24) + ('找到了（缺陷）' if needle in checkpoint_text else '没有'))
print('-' * 54)
print('checkpoint 里泄露的字段:', checkpoint_leaks or '（一个都没有）')
print('checkpoint 里的状态字段:', ', '.join(sorted(json.loads(checkpoint_text)['state'])))
print()
print('小结：恢复从"下一步"继续，决策路径与不中断时逐项一致，且没有第二次副作用；'
      'checkpoint 里只有引用、决定、计数与哈希——正文与绝对路径都进不去。')

# ----------------------------------------------------------------------------
# ## 8. 人工审批：参数绑定、限期、一次性
#
# 阶段计划 §6：高影响动作使用参数绑定、有效期有限的审批引用；恢复或参数改变后重新审批，
# 不能把"图已到达该节点"视为用户批准。
#
# 编排层的做法是**不另起一套审批语义**：
#
# - 审批记录就是 Phase 4 的 ApprovalRecord（同一个 JSON 格式），
#   校验也仍然由 enforcement.approvals.verify_approval 做；
# - 编排层只把"为什么拒绝"翻译成自己的失败码（approval_missing / approval_expired /
#   approval_subject_mismatch / approval_param_mismatch / approval_consumed），
#   翻译依据是**结构化字段**，不解析错误文本；
# - 门禁只在平台给出**结构化** required_action = "approval" 时打开——
#   节点不解析自然语言，也不能因为"图走到了这个节点"就认为用户批准了。
#
# 绑定有两层，输出里会分别打印：
#
# - **编排层的幂等键**（action_id）是"任务:repair 轮次:改动摘要前 16 位"，
#   它回答的是"这次动作叫什么名字"；
# - **平台口径的 action_hash**（由 ToolRunner.binding() 算出）覆盖工具 schema、
#   规范化参数、主体、权限与上下文摘要，它才是人工审批要绑的东西。
#
# 把两者混为一谈的后果很具体：审批能通过编排层的检查，却在 Phase 4 的 pre-check 上
# 被判成"参数或主体已经变化"。所以节点的顺序是"**先向执行器要绑定 → 再拿绑定校验审批 →
# 最后把审批文件本身交给受控执行链复验**"（判定权始终在平台）。
#
# 审批的**收件箱**既可以是一个文件，也可以是一个目录：目录里按文件名排序逐个读，
# 取第一条 action_id 匹配的记录；一条都不匹配时退化成"第一条可读记录"，
# 好让"参数漂移 / 主体不符"能给出具体的失败码，而不是笼统的"没有审批"。
# 下面 8a 用的是空目录，8b 用的是每个场景一个只放一份记录的目录——
# **参数变一个字符，平台口径的哈希就变，旧审批立刻作废**。
# ----------------------------------------------------------------------------

# 8a. 没有审批就不动手（fail closed）

missing_dir = DEMO / 'approvals' / 'missing'
missing_dir.mkdir(parents=True, exist_ok=True)
missing_runner = recording_runner(1)
missing_config, missing_assembly = scenario(
    'approval-missing',
    client=fake_client((validate_outcome(False), validate_outcome(False)), needs_approval=True),
    runner=missing_runner,
    approvals=missing_dir,          # 空目录 = 空的审批收件箱（CLI 的默认值也是目录）
)
missing_report = run_scenario(missing_assembly)
approval_missing_status = missing_report.status.value
approval_missing_code = missing_report.failure.code.value
print(pad('节点', 24) + pad('标签', 12) + pad('状态', 12) + '失败码')
print('-' * 96)
for step in missing_report.steps:
    print(pad(step.node, 24) + pad(step.label, 12) + pad(step.status, 12) + (step.failure or '-'))
print('-' * 88)
print('终态:', approval_missing_status, '| 失败码:', approval_missing_code)
print('审批门禁的说明:', missing_report.failure.detail)
print('真的动手了吗:', len(missing_runner.calls), '次工具调用（必须是 0）')
print('状态里记下的审批引用:', missing_report.state.approvals or '（一个都没有）')
# 节点在查审批之前先向执行器要了"平台口径的绑定"：下面这次请求就是审批要绑的东西。
approval_request = missing_runner.bindings[0]
print('节点交给执行器求绑定的动作:', approval_request.tool_id,
      '| 参数键:', sorted(approval_request.params))
print()
print('小结：平台说"这个动作需要人工审批"，而审批收件箱是空的 → needs_human，'
      '节点一步都没动。失败关闭不是"报个错"，而是没有任何副作用发生。')

# 8b. 按平台口径的 action_hash 签发审批，再看门禁的反应

from dataclasses import replace  # noqa: E402

approval_runners = {}
approval_reasons = {'missing': '平台说需要审批，审批收件箱里没有记录'}
approval_binding = RecordingToolRunner().binding(approval_request)
drifted = Change(**{**BROKEN.__dict__, 'replacement': BROKEN.replacement + ' '})
drifted_binding = RecordingToolRunner().binding(
    replace(approval_request, params=drifted.params()))
approval_hash_is_not_idempotency_key = approval_binding.action_hash != approval_binding.action_id
approval_binding_drift = approval_binding.action_hash != drifted_binding.action_hash


def approval_file(name, binding, **overrides):
    '''写一份 **Phase 4 的** ApprovalRecord：绑的是平台口径的 action_hash，不另起一套审批语义。'''

    directory = DEMO / 'approvals' / name        # 每个场景一个收件箱，只放一份记录
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name + '.json')
    now = utc_now()
    fields = {
        'approval_id': 'approval-' + name,
        'action_hash': binding.action_hash,
        'action_id': binding.action_id,
        'tool_id': binding.tool_id,
        'subject': binding.subject,
        'granted_by': 'reviewer-1',
        'granted_by_roles': ['reviewer'],
        'granted_at': now - timedelta(minutes=30),
        'expires_at': now + timedelta(hours=1),
    }
    fields.update(overrides)
    record = ApprovalRecord(**fields)
    write_text_with_retry(
        path, json.dumps(json.loads(record.model_dump_json()), ensure_ascii=False, indent=2) + chr(10)
    )
    return path


approval_cases = (
    ('expired', approval_file('expired', approval_binding, granted_at=utc_now() - timedelta(hours=2),
                              expires_at=utc_now() - timedelta(hours=1)), BROKEN),
    ('subject', approval_file('subject', approval_binding, subject='bob'), BROKEN),
    ('params', approval_file('params', approval_binding), drifted),
    ('valid', approval_file('valid', approval_binding), BROKEN),
)
approval_rows = [('missing', approval_missing_status, approval_missing_code, len(missing_runner.calls))]
print(pad('场景', 12) + pad('审批收件箱', 20) + pad('终态', 12) + pad('失败码', 26) + '工具调用')
print('-' * 94)
print(pad('missing', 12) + pad('空', 20) + pad(approval_missing_status, 12)
      + pad(approval_missing_code, 26) + str(len(missing_runner.calls)))
for name, path, change in approval_cases:
    runner = recording_runner(1)
    _config, assembly = scenario(
        'approval-' + name,
        client=fake_client((validate_outcome(False), validate_outcome(False)), needs_approval=True),
        runner=runner,
        author=ScriptedAuthor({0: change, 1: FIXED}),
        approvals=path.parent,
    )
    report = run_scenario(assembly)
    code = None if report.failure is None else report.failure.code.value
    approval_runners[name] = runner
    if report.failure is not None:
        approval_reasons[name] = report.failure.detail.split('] ', 1)[-1].split('（')[0]
    approval_rows.append((name, report.status.value, code, len(runner.calls)))
    print(pad(name, 12) + pad('1 份 ApprovalRecord', 20) + pad(report.status.value, 12)
          + pad(code or '-', 26) + str(len(runner.calls)))
print('-' * 94)
approval_rows = tuple(approval_rows)
approval_valid = next(row for row in approval_rows if row[0] == 'valid')
valid_request = approval_runners['valid'].calls[0]
approval_request_binding = (valid_request.approval_path is not None, valid_request.tool_id)
print('审批绑的是平台口径的哈希、不是编排层的幂等键:', approval_hash_is_not_idempotency_key)
print('   平台口径 action_hash:', approval_binding.action_hash)
print('   编排层 action_id   :', approval_binding.action_id)
print('   参数改一个空格 → 平台口径哈希跟着变:', approval_binding_drift)
print('通过审批的那一次:', approval_valid[1], '| 工具调用:', approval_valid[3], '次',
      '| 请求里带着审批文件:', approval_request_binding[0])
print('真正执行时用的工具:', approval_request_binding[1],
      '| 参数键:', sorted(valid_request.params))
print('随请求交给受控执行链的审批文件:',
      valid_request.approval_path.relative_to(REPO_ROOT).as_posix())
print()
print('小结：审批绑的是"平台口径的 action_hash"（工具 schema、参数、主体都在里面），'
      '不是编排层自己的幂等键；缺、过期、换主体、参数漂移全部停在 needs_human，'
      '且一次都没有真的动手——只有逐位匹配的那一份审批能放行。')

# ----------------------------------------------------------------------------
# ## 9. 失败关闭总表：哪些地方会失败，失败之后是什么状态
#
# 编排层的纪律是：**平台不可用 / 证据缺失 / trace 断裂 / 审批不合法 / 上限击穿，
# 一律进入显式终态（blocked / needs_human / failed），没有"默认放行"分支。**
#
# 下面这张表有两个来源，都来自**本次运行真实发生过的东西**：
#
# - 第 2 节的 STATUS_BY_CODE（失败码 → 终态的唯一映射）；
# - 本手册真的走到过的失败路径（路由标签不认、上限击穿、四种审批拒绝）。
#
# **Phase 8 明确不做的事**（写在 src/orchestration/README.md 与实施记录的"已知边界"里）：
#
# - **不做判定**：编排层不导入 policy.engine，不复制任何规则、权限或证据逻辑；
#   它只通过客户端端口问平台，平台不可用就停下，绝不"凭记忆继续"；
# - **不做第二套审批**：审批记录就是 Phase 4 的 ApprovalRecord，
#   判定权在 enforcement.approvals.verify_approval，编排层只翻译拒绝原因；
# - **不存正文**：需求原文、文件内容、工具完整输出、凭据都不进状态；
#   checkpoint 里只有引用、决定、计数与哈希；
# - **不用 LangGraph 的 checkpointer 做跨进程恢复**：通用 checkpointer 不携带
#   "规则集 / 索引 / 工具 schema 是否仍兼容"这类领域信息，也不负责"不兼容时重新评估"；
# - **不接入真实模型**：候选改动来自 ChangeAuthor 端口，仓库里只有确定性的
#   ScriptedAuthor；接模型不改变任何节点契约，但本阶段没有验证过真实模型；
# - **不做分布式一致性**：熔断是进程内的连续失败计数（复位要显式动作）；
#   同一 task 的两个进程同时恢复同一个 checkpoint 不受保护——
#   单文件的原子替换只保证"不会读到半份"；
# - **不执行命令类工具**：注册表里只声明了写入类与"改规则"工具，
#   需要 shell 的场景仍然由 Agent 侧的受控执行链负责。
# ----------------------------------------------------------------------------

# 9. 失败关闭对照表（每一行都是本次运行真实发生过的路径）

observed_failures = (
    ('路由标签没登记（第 3 节）', route_label_refused, '执行器拒绝猜下一步'),
    ('repair 轮次击穿上限（第 2 节）', limit_exceeded[0], limit_exceeded[2]),
    ('动作需要审批但没有记录（第 8 节）', approval_missing_code, '平台说需要审批，审批读不到'),
)
for row in approval_rows:
    if row[2] is not None and row[0] != 'missing':
        observed_failures = observed_failures + (
            ('审批被拒绝：' + row[0], row[2], approval_reasons.get(row[0], '审批门禁')),
        )

print(pad('场景', 34) + pad('失败码', 26) + pad('终态', 12) + '说明')
print('-' * 104)
for label, code, detail in observed_failures:
    print(pad(label, 34) + pad(code, 26) + pad(STATUS_BY_CODE[FailureCode(code)].value, 12) + detail)
print('-' * 104)
print('共', len(observed_failures), '条真实路径，全部是显式失败码；没有一条变成"继续往下走"。')
print()

terminal_counts = {}
for code in FailureCode:
    status = STATUS_BY_CODE.get(code, RunStatus.FAILED).value
    terminal_counts[status] = terminal_counts.get(status, 0) + 1
meanings = {
    'blocked': '平台侧说不清楚（不可用 / 被拒 / trace 断裂 / 熔断）：禁止继续',
    'needs_human': '上限或审批要求人来做决定',
    'failed': '编排自己坏了（状态非法、节点契约、checkpoint、引擎不可用）',
}
print(pad('终态', 14) + pad('失败码个数', 14) + '含义')
print('-' * 84)
for status in sorted(terminal_counts):
    print(pad(status, 14) + pad(terminal_counts[status], 14) + meanings.get(status, '-'))
print('-' * 84)
print('合计:', sum(terminal_counts.values()), '个失败码（枚举共', failure_codes_total, '个）；'
      '没有登记终态的:', unmapped_failure_codes or '（一个都没有）')
print()
print('小结：终态由失败码查表决定，节点与引擎都不许自己发明状态；'
      '超时、平台不可用、审批不合法、上限击穿全都停在人看得见的地方。')

# ----------------------------------------------------------------------------
# ## 接下来读什么
#
# - 阶段设计与实施记录：docs/project/engineering-policy-platform/phases/phase-8-langgraph-orchestration.md
# - 编排层总览与恢复语义：src/orchestration/README.md
# - 状态与节点契约：src/orchestration/models.py、nodes.py、graph.py、limits.py、errors.py
# - checkpoint / 审批 / 端口：src/orchestration/checkpoint.py、approvals.py、client.py、tools.py
# - 两个引擎与装配：src/orchestration/engines.py、langgraph_engine.py、runtime.py
# - 命令行自检：python -m orchestration.cli self-check | graph | status | run
# - 测试怎么看这件事：tests/orchestration_support.py 与
#   tests/{unit,contract,integration,security}/test_orchestration_*.py
#
# **如果只记一句话，记这句：编排层决定"怎么走"，平台决定"允不允许"；
# 状态里只放引用，checkpoint 里只放"下一步"，失败码决定终态——没有任何一条路径默认放行。**
#
# 跑完别忘了清理演示产物：python tools/cleanup.py。
# ----------------------------------------------------------------------------

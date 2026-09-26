# -*- coding: utf-8 -*-
"""07-LangGraph-编排：内容源（产物由 build_notebooks.py 生成）。"""
from __future__ import annotations

from notebook_lib import NotebookSpec, code, markdown

SPEC = NotebookSpec(
    stem="07-LangGraph-编排",
    title="LangGraph 编排：只回答下一步做什么",
    summary="编排层是平台消费者：跑一条最小图，验证端口注入 / 图状态不放正文 / checkpoint 原子替换 / 恢复凭据比对 / 失败关闭分支",
    temp_dir=".tmp/tech-detail/07",
    cells=(
        markdown(
            '''
# 07 LangGraph 编排：只回答"下一步做什么"

这份 notebook 配合同名图 `07-LangGraph-编排.drawio`。那张图讲编排层内部怎么走
（需求 → 检索 → 规划 → 实施 → 验证 ⇄ 修复 → 测试 → 收尾，旁边挂着平台判定、受控执行与
checkpoint）；这份 notebook 把图上写下的每一句话**在代码里跑一遍**。

**预备知识**：会读 Python 的 import 与函数调用就够了，不需要懂 LangGraph，也不需要装它。

读完你应该能回答四个问题：

1. 编排层为什么是**消费者**而不是平台的一部分？"删掉整个包平台照常跑"是口号还是可检查的事实？
2. 图状态里为什么**没有需求原文、文件内容与凭据**？checkpoint 到底存了什么？
3. 中断之后"恢复"时，凭什么判断旧的 allow 还能不能用？
4. 哪些情况让工作流**停下来**（blocked / needs_human / failed）？谁有权决定终态？

四个问题对应下面七段代码：**结构边界 → 最小状态与 checkpoint → 恢复比对 → 终态与失败关闭
分支 → 最小图跑通（含人工审批）→ 平台口径的 action_hash → 小结**。
'''
        ),
        markdown(
            '''
## 1. 前提：三个端口全部注入假实现

这一节只做一件事：把 `.tmp/tech-detail/07/` 造出来，把仓库的 `src`、`tools`、`tests` 装进
`sys.path`，再把后面每一节都要用的"演示任务 + 三个假端口"准备好。

三个端口**全部注入假实现**（阶段计划 §2 的"先用 fake Policy Client"）：

| 端口 | 真实实现在哪 | 这一节用什么 |
| --- | --- | --- |
| 问平台 | `orchestration.client.ApiPolicyClient`（标准库 HTTP，走 Phase 7 公开路由） | `ScriptedPolicyClient`：按脚本回答，脚本用尽即失败关闭 |
| 动手 | `orchestration.tools.PlatformToolRunner`（Phase 4 受控执行链） | `RecordingToolRunner`：只记录，不落盘 |
| 出候选改动 | 真实系统里是模型（`ChangeAuthor` 端口） | `ScriptedAuthor`：第 0 轮给"会被挡住"的改动，第 1 轮给修好的 |

为什么先用假的：状态机出问题时，你要能确定**是编排错了还是平台错了**。
换掉任何一个端口都不需要改节点代码——这就是"端口"的意义。

`.tmp/tech-detail/07/` 是**这一份 notebook 独占**的临时目录：生成器会检查每份讲解
notebook 只用自己那个编号的目录，因为 `.tmp/phase-8-orchestration/` 这类固定路径被
`tools/ci_local.py` 与各阶段闭环共用，并发写会互相拆台、跑出假红。

这个单元会打印：仓库根、当前工作目录、临时目录、Python 版本、编排状态协议版本
（`STATE_SCHEMA_VERSION`，它**不跟随平台阶段**）以及图里的八个节点名。
'''
        ),
        code(
            '''
# 1. 起步：向上找仓库根、装好 sys.path、建独占的临时目录
import shutil
import sys
from pathlib import Path


def find_repo_root(start):
    """往上找：同时有 pyproject.toml 与 src/policy/ 的那一层就是仓库根。"""

    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "policy").is_dir():
            return candidate
    raise SystemExit("没有找到仓库根目录（需要 pyproject.toml 与 src/policy/）")


REPO_ROOT = find_repo_root(Path.cwd())
for extra in (REPO_ROOT / "src", REPO_ROOT / "tools", REPO_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

# 这一节的临时产物只落在自己的编号目录下；每轮先删再建，
# 因为生成器会从两个工作目录（仓库根、本目录）各跑一遍全部单元。
TEMP = REPO_ROOT / ".tmp" / "tech-detail" / "07"
shutil.rmtree(TEMP, ignore_errors=True)
TEMP.mkdir(parents=True, exist_ok=True)

import orchestration  # noqa: E402
import orchestration_support as support  # noqa: E402
from orchestration import langgraph_engine  # noqa: E402
from orchestration.approvals import ApprovalGate  # noqa: E402
from orchestration.checkpoint import JsonCheckpointStore, build_record, plan_resume  # noqa: E402
from orchestration.client import (  # noqa: E402
    DecisionOutcome,
    PlatformReadiness,
    RetrievalOutcome,
    ScriptedPolicyClient,
)
from orchestration.errors import (  # noqa: E402
    STATUS_BY_CODE,
    EngineUnavailableError,
    NodeContractError,
    OrchestrationError,
)
from orchestration.graph import DEFAULT_SPEC, END, ROUTERS, GraphSpec, Router  # noqa: E402
from orchestration.limits import LIMIT_RULES, LimitKind, charge  # noqa: E402
from orchestration.models import (  # noqa: E402
    STATE_SCHEMA_VERSION,
    SUPPORTED_STATE_SCHEMA_VERSIONS,
    ArtifactKind,
    ArtifactRef,
    FailureCode,
    GraphState,
    NodeId,
    PlatformSnapshot,
    RunLimits,
    RunStatus,
    StageStatus,
    empty_state,
)
from orchestration.nodes import Change, NodeContext, NodeOutcome, ScriptedAuthor, TaskSpec  # noqa: E402
from orchestration.runtime import OrchestrationConfig, build_assembly, select_engine  # noqa: E402
from orchestration.tools import PlatformToolRunner, RecordingToolRunner  # noqa: E402
from policy.models import POLICY_VERSION, SCHEMA_VERSION, Decision  # noqa: E402
from pydantic import ValidationError  # noqa: E402

print("仓库根:", REPO_ROOT.name)
print("工作目录:", Path.cwd().relative_to(REPO_ROOT).as_posix() or ".")
print("临时目录:", TEMP.relative_to(REPO_ROOT).as_posix())
print("Python:", sys.version.split()[0])
print()
print("编排状态协议 STATE_SCHEMA_VERSION:", STATE_SCHEMA_VERSION, "（只描述图状态的形状）")
print("平台侧协议: POLICY_VERSION =", POLICY_VERSION, "| SCHEMA_VERSION =", SCHEMA_VERSION,
      "（编排层不许自己算一个）")
print("可读的状态版本:", ", ".join(sorted(SUPPORTED_STATE_SCHEMA_VERSIONS)))
print("节点清单（图里的八个方框）:")
for index, node in enumerate(NodeId, start=1):
    print("   ", index, node.value)
print()


class RetryStore:
    """给 JsonCheckpointStore 套一层有界重试：Windows 上偶发 WinError 5 是环境噪声。

    格式、原子替换与摘要校验仍然由里层负责；这里只是让"新写的文件被文件扫描器短暂占用"
    不再变成假红。重试用完仍然抛出，绝不"写不进去就当写成功"。
    """

    def __init__(self, inner, attempts=5):
        self.inner = inner
        self.attempts = attempts

    def path_for(self, task_id):
        return self.inner.path_for(task_id)

    def save(self, record):
        import time

        for attempt in range(self.attempts):
            try:
                return self.inner.save(record)
            except PermissionError:
                if attempt == self.attempts - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def load(self, task_id):
        return self.inner.load(task_id)

    def exists(self, task_id):
        return self.inner.exists(task_id)


def shell_executor(name):
    """一个不跑图、只用来观察引擎选择的执行器外壳。"""

    return support.step_executor(TEMP, name=name)


print("演示端口已就绪：ScriptedPolicyClient（按脚本回答）· RecordingToolRunner（只记录）· "
      "ScriptedAuthor（第 0 轮坏的、第 1 轮好的）")
'''
        ),
        markdown(
            '''
## 2. 结构边界：编排层是消费者，不是平台的一部分

图纸上的关键一句：**"编排只回答下一步做什么；判定仍回平台，删掉本层平台照常独立运行。"**
它可以拆成三条能用代码检查的规矩：

1. **反向依赖为零**：没有任何平台包 import 编排层——删掉 `src/orchestration/`，
   `policy` / `retrieval` / `validators` / `enforcement` / `adapters` / `policy_api` 照常工作；
2. **工作流框架只有一个导入点**：只有 `orchestration/langgraph_engine.py` 提到 `langgraph`，
   而且是**构造引擎时**才导入；版本不认识就 `EngineUnavailableError`，不"尽力兼容"；
3. **没有静默回落**：`engine="langgraph"` 但框架不可用 → 直接报错，终态 `failed`；
   `engine="auto"` 可以回落参考引擎，但**回落的事实必须如实写进 `RunReport.engine`**——
   不许把参考引擎报成 LangGraph。

输出怎么读：前两行说清谁 import 谁（用 `ast` 扫真实源码，不是抄文档）；
后面几行现场演示第 3 条：先把 langgraph 的版本探测"打断"（只改内存里的一个函数，
不碰仓库文件、不动已安装的包），看声明式选择引擎时会不会失败关闭；
`engine=auto` 那一行打印的引擎名就是报告里会写的东西。
'''
        ),
        code(
            '''
# 2. 结构边界：AST 扫描 + 引擎不可用时的失败关闭
import ast

SRC = REPO_ROOT / "src"
PLATFORM_PACKAGES = ("policy", "retrieval", "validators", "enforcement", "adapters", "policy_api")


def importers_of(package):
    """真的 import 了某个顶层包的文件清单（含 import_module("包.模块") 这种延迟导入）。"""

    def touches(node):
        if isinstance(node, ast.Import):
            return any(alias.name.split(".")[0] == package for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            return (node.module or "").split(".")[0] == package
        if isinstance(node, ast.Call):
            called = getattr(node.func, "attr", "") or getattr(node.func, "id", "")
            if called == "import_module" and node.args:
                first = node.args[0]
                return isinstance(first, ast.Constant) and str(first.value).startswith(package)
        return False

    found = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(touches(node) for node in ast.walk(tree)):
            found.append(path.relative_to(REPO_ROOT).as_posix())
    return found


workflow_importers = importers_of("langgraph")
orchestration_importers = importers_of("orchestration")

print(pad("导入点检查", 24) + "结果")
print("-" * 96)
print(pad("import langgraph", 24) + (", ".join(workflow_importers) or "（无）"))
print(pad("import orchestration", 24) + (", ".join(orchestration_importers) or "（无）"))
print()
# 第一条：工作流框架只有一个导入点，而且它就是那个延迟导入的引擎适配文件。
assert workflow_importers == ["src/orchestration/langgraph_engine.py"], workflow_importers
# 第二条：没有任何**平台包**反过来 import 编排层（只有编排层自己的文件会 import 它）。
for package in PLATFORM_PACKAGES:
    hit = [item for item in orchestration_importers if item.startswith(f"src/{package}/")]
    assert not hit, f"{package} 反向依赖了编排层：{hit}"
print(len(PLATFORM_PACKAGES), "个平台包里，import 编排层的文件数为 0（删掉编排层，平台照常跑）")
print()

# 第三条：引擎不可用时必须失败关闭，而不是"回落之后还说自己是 LangGraph"。
installed = langgraph_engine.langgraph_version()
reference_engine, reference_name = select_engine(
    "reference", executor=shell_executor("engine-reference"))
auto_name = select_engine("auto", executor=shell_executor("engine-auto"))[1]
assert reference_name == "reference"
assert auto_name == ("langgraph" if installed else "reference"), auto_name

probe = shell_executor("engine-probe")
original_probe = langgraph_engine.langgraph_version
try:
    langgraph_engine.langgraph_version = lambda: None
    try:
        select_engine("langgraph", executor=probe)
        raise AssertionError("声明使用 langgraph 但框架不可用时没有报错")
    except EngineUnavailableError as error:
        engine_error = str(error)
    assert STATUS_BY_CODE[FailureCode.ENGINE_UNAVAILABLE] is RunStatus.FAILED
finally:
    langgraph_engine.langgraph_version = original_probe

print(pad("引擎选择", 22) + "结果")
print("-" * 96)
print(pad("engine=reference", 22) + f"选中 {reference_name!r}（参考引擎：一个 while 循环，零第三方依赖）")
print(pad("engine=auto", 22) + f"选中 {auto_name!r}" + (
    "（本机装了 langgraph，优先用它，报告里同样写 langgraph）" if installed
    else "（本机没有 langgraph：如实回流到参考引擎，报告里写 reference）"))
print(pad("engine=langgraph", 22) + ("可用（框架已安装）" if installed else "不可用 → 失败关闭"))
print(pad("langgraph 版本探测", 22) + str(installed or "未安装（包元数据里没有它）"))
print(pad("失败关闭的报错", 22) + engine_error[:60])
print()
print("小结：边界是可检查的事实——6 个平台包里 import 编排层的文件数为 0；",
      "工作流框架只在一个文件里、构造引擎时才导入；不可用即报错（终态 failed），",
      "回落也如实写在报告里。")
'''
        ),
        markdown(
            '''
## 3. 最小图状态与 checkpoint：不放正文、单文件、可复算

图纸脚注第一句：**"图状态里不放正文（只有摘要与引用）；恢复时与当前凭据比对。"**
换成代码，就是 `GraphState` 的四条纪律：

- **引用而不是正文**：`requirements` 是验收条目（短结论）、`artifacts` 只有路径 + 摘要 + 字节数、
  `contexts` 只有 chunk 引用、`traces` 只有 request_id 与决定——需求原文只活在内存里的
  `TaskSpec`，文件内容只活在受控工作区里；
- **不可变**：`replace()` 返回新实例并把 `revision` 加一，因此 checkpoint 里每一版都是完整快照；
- **相同输入 → 逐字节相同的状态**：没有墙钟时间、没有随机数、没有自增 ID，
  所以 `digest()`（规范化 JSON 的 sha256）可以直接拿来比对；
- **严格解析**：未知字段、未知状态版本、绝对路径、含 `..` 的路径一律**报错**，不是忽略。

checkpoint 落盘则是"**单文件 + 原子替换**"：先写 `*.checkpoint.tmp` 再 `os.replace`，
崩溃只会留下旧版本，不会留下半份；记录同时带 `state_digest` 与 **`record_digest`**——
后者覆盖**整条记录**（含兼容性凭据）。只校验 state 的话，把记录里的 `rule_set_hash` 改成
当前值就能让恢复跳过"重新评估"，那正是最需要保护的一块。

输出怎么读：先是一张"非法输入 → 被拒绝方式"的表（每一行都由一次真实的
`ValidationError` 产生）；然后读回刚刚写的 checkpoint 文件，看它的字节数与目录内容
（单文件 + 原子替换）；最后打印 `NodeContext.commit` 有没有被绑定到执行器的 `save`——
**副作用之前先写"意图"并立刻刷盘（写前记账），靠的就是这根线**。
'''
        ),
        code(
            '''
# 3. 状态与 checkpoint：确定性摘要、四种拒绝、原子替换与写前记账
initial = empty_state("phase8-task", limits=RunLimits(max_repair_rounds=1))
moved = initial.replace(stage=NodeId.POLICY_RETRIEVAL)
charged = charge(moved, LimitKind.REPAIR_ROUNDS, 1)
print("revision 随每次修改 +1:", (initial.revision, moved.revision, charged.revision))
print("相同输入 → 逐字节相同的状态:",
      initial.digest() == empty_state("phase8-task", limits=RunLimits(max_repair_rounds=1)).digest())
print("状态字段（没有一个是正文或墙钟）:", ", ".join(sorted(initial.payload())))
assert set(initial.payload()) == {
    "state_schema_version", "task_id", "revision", "stage", "status", "request_id", "trace_id",
    "requirements", "plan", "artifacts", "contexts", "traces", "validation", "test_validation",
    "counters", "limits", "approvals", "runs", "failure", "snapshot", "notes",
}
print()


def all_errors(error):
    """把 pydantic 的报错压成稳定的短文本：只留"哪一段、为什么"。"""

    first = error.errors()[0]
    where = ".".join(str(part) for part in first["loc"])
    return f"{where} -> {first['msg'].replace('Value error, ', '')}"


refusals = {}
for label, payload in {
    "未知字段": {"kind": "state", "data": {**initial.payload(), "tools": ["rm -rf /"]}},
    "未知状态版本": {"kind": "state", "data": {**initial.payload(), "state_schema_version": "9.9"}},
    "绝对路径": {"kind": "artifact", "data": {"path": "C:/tmp/order_service.py"}},
    "含 .. 的路径": {"kind": "artifact", "data": {"path": "src/../../order_service.py"}},
}.items():
    try:
        if payload["kind"] == "artifact":
            ArtifactRef(artifact_id="change-1", kind=ArtifactKind.CHANGE,
                        digest="sha256:" + "f" * 64, **payload["data"])
        else:
            GraphState.model_validate(payload["data"])
        refusals[label] = "放行了（缺陷）"
    except ValidationError as error:
        refusals[label] = all_errors(error)

print(pad("非法输入", 16) + "被拒绝的方式")
print("-" * 88)
for label, detail in refusals.items():
    print(pad(label, 16) + detail)
assert not [key for key, value in refusals.items() if value.endswith("（缺陷）")], refusals
print()

store = JsonCheckpointStore(TEMP / "checkpoints")
first = build_record(initial, engine="reference", sequence=1)
second = build_record(charged, engine="reference", sequence=2)
store.save(first)
store.save(second)
path = store.path_for("phase8-task")
text = path.read_text(encoding="utf-8")
reloaded = store.load("phase8-task")
print("checkpoint 文件:", path.name, "|", len(text.encode("utf-8")), "字节")
print("同一状态两遍 → 逐字节相同的记录摘要:",
      build_record(initial, engine="reference", sequence=1).record_digest == first.record_digest)
print("状态变了 → 摘要跟着变:", first.state_digest != second.state_digest)
print("读回来时两道摘要都校验通过:", reloaded.state_digest == second.state_digest)
print("checkpoint 目录里的文件（原子替换：先写 <名字>.tmp 再 replace）:",
      sorted(item.name for item in path.parent.iterdir()))
print()


def save_problem(record):
    """试着写一份自相矛盾的记录：只校验 state 是不够的，record_digest 也要挡。"""

    try:
        store.save(record)
        return "写进去了（缺陷）"
    except Exception as error:  # noqa: BLE001 - 这里就是要看到拒绝
        return f"{type(error).__name__}: {error}"


tampered = build_record(initial, engine="reference", sequence=3).model_copy(
    update={"state_digest": "sha256:" + "0" * 64})
tampered_credentials = build_record(initial, engine="reference", sequence=4).model_copy(
    update={"compatibility": PlatformSnapshot(rule_set_hash="sha256:" + "9" * 64)})
print(pad("写一份什么样的记录", 28) + "结果")
print("-" * 96)
print(pad("state_digest 与状态不一致", 28) + save_problem(tampered))
print(pad("改掉兼容性凭据", 28) + save_problem(tampered_credentials))

probe_config = support.graph_config(TEMP, name="commit-probe")
probe_assembly = build_assembly(
    probe_config,
    task=support.task_spec("commit-task", trace_id="trace-commit"),
    author=ScriptedAuthor([support.write_change()]),
    client=support.scripted_client(evaluate=(support.allow_outcome(),)),
    tool_runner=RecordingToolRunner((support.executed_outcome(),)),
)
print()
print("写前记账的接线：NodeContext.commit 已绑定执行器的 save →",
      probe_assembly.executor.context.commit == probe_assembly.executor.save)
assert probe_assembly.executor.context.commit is not None
print("小结：状态只有引用与计数；checkpoint 是单文件原子替换 + 两道摘要校验；",
      "副作用之前先写意图并立刻刷盘（NodeContext.commit）。")
'''
        ),
        markdown(
            '''
## 4. 恢复：拿**当前**平台的凭据跟 checkpoint 比

图纸脚注第二句：**"规则集 / 索引 / 工具 schema 变了就清掉旧 allow 重评。"**
这句话在代码里是 `plan_resume(记录, 当前凭据, fresh_state=...)`，结论是四种之一：

| 变了什么 | 结论 | 行为 |
| --- | --- | --- |
| 什么都没变 | `resume` | 接着上次的阶段继续 |
| 规则集（`rule_set_hash`）或索引（`index_version`） | `revalidate` | 清掉旧 trace、旧 contexts 与旧验证结果，回到检索节点重评，**不沿用旧 allow** |
| 工具 schema（`tool_schema_hash`） | `reapprove` | 旧审批作废（它绑的是旧 schema 下的 `action_hash`），需要重新签发 |
| 协议世代（`policy_version` / `decision_schema_version`） | 抛 `ResumeError`（子类 `CheckpointError`） | 拒绝恢复，必须重新开始 |
| 凭据**拿不到**（`None`） | 按"变了"处理 → `revalidate` | 宁可重评，也绝不按"没变"沿用旧结论 |

还有两条容易漏掉的：**恢复会清掉上一轮的失败码与终态**（失败不是工作流的进度，
不清掉的话引擎会在第一个节点之后立刻因为"还有 failure"而停下），
以及**恢复本身会立刻落一份 checkpoint**（"恢复了但没记录"是不能接受的）。

输出怎么读：五行的"情形 → 结论 → 改变的维度 → 恢复后的状态"。每一行都由一次真实的
`plan_resume` 调用产生，并且现场断言了关键结论（比如 revalidate 之后 stage 回到
`policy_retrieval`、traces 与 validation 被清空）。
'''
        ),
        code(
            '''
# 4. 恢复：四种结论 + "拿不到凭据按变了处理"
fresh = empty_state("phase8-task", limits=RunLimits(max_repair_rounds=2),
                    trace_id="trace-8", requirements=("target 满足规则集",))
fresh = fresh.replace(stage=NodeId.TESTING, status=RunStatus.BLOCKED, failure=None,
                      notes=("上一轮停在这里",))
current = PlatformSnapshot(rule_set_hash=support.RULE_SET_HASH,
                           index_version=support.INDEX_VERSION, tool_schema_hash=None)
base = build_record(fresh, engine="reference", sequence=9, compatibility=current)

rows = []


def judge(name, record, snapshot):
    """跑一次 plan_resume，把结论、改变的维度与恢复后的状态记成一行。"""

    try:
        plan = plan_resume(record, snapshot, fresh_state=fresh)
    except Exception as error:  # noqa: BLE001 - 拒绝恢复也是一种结论
        rows.append((name, f"拒绝（{type(error).__name__}）", "-", "不沿用任何旧结论"))
        return None
    state = plan.state
    kept = []
    if state.traces:
        kept.append(f"trace {len(state.traces)} 条")
    if state.validation is not None:
        kept.append("旧验证结果")
    if state.approvals:
        kept.append(f"审批引用 {len(state.approvals)} 条")
    rows.append((name, plan.mode.value, "、".join(plan.changed) or "（没变）",
                 f"stage={state.stage.value} · status={state.status.value} · "
                 + ("、".join(kept) or "无旧结论")))
    return plan


same = judge("凭据没变", base, current)
assert same.mode.value == "resume" and same.state.failure is None
assert same.state.status is RunStatus.RUNNING and same.state.stage is NodeId.TESTING

changed_rules = current.model_copy(update={"rule_set_hash": support.CHANGED_RULE_SET_HASH})
revalidate = judge("规则集变了", base, changed_rules)
assert revalidate.mode.value == "revalidate" and "rule_set_hash" in revalidate.changed
assert revalidate.state.stage is NodeId.POLICY_RETRIEVAL, revalidate.state.stage
assert revalidate.state.traces == () and revalidate.state.validation is None

changed_tools = current.model_copy(update={"tool_schema_hash": "sha256:" + "b" * 64})
reapprove = judge("工具 schema 变了",
                  build_record(fresh, engine="reference", sequence=9,
                               compatibility=changed_tools), current)
assert reapprove.mode.value == "reapprove" and reapprove.state.approvals == ()

generation = current.model_copy(update={"decision_schema_version": "9.9"})
judge("协议世代变了", base, generation)

unknown = PlatformSnapshot(rule_set_hash=None, index_version=None, tool_schema_hash=None)
blinded = judge("凭据拿不到（None）", base, unknown)
assert blinded.mode.value == "revalidate"
assert set(blinded.changed) == {"rule_set_hash", "index_version"}, blinded.changed
# 对照组：state_schema_version 只描述**图状态自己的形状**，它不参与"能不能接着跑"的比对
# （状态版本读不懂时 checkpoint 层在 load 阶段就已经拒绝），所以把它改掉也不会多出维度。
shape_only = judge("只改状态形状版本", build_record(
    fresh, engine="reference", sequence=9,
    compatibility=current.model_copy(update={"state_schema_version": "1.0"})), current)
assert "state_schema_version" not in shape_only.changed, shape_only.changed

print(pad("情形", 22) + pad("结论", 36) + pad("改变的维度", 34) + "恢复后的状态")
print("-" * 132)
for name, mode, changed, state_text in rows:
    print(pad(name, 22) + pad(mode, 36) + pad(changed, 28) + state_text)
print()
print("小结：恢复的基准是**当前**平台的凭据；规则集 / 索引变了回到检索节点重评、",
      "工具 schema 变了旧审批作废、协议世代变了直接拒绝、拿不到凭据按变了处理；",
      "上一轮的失败码与终态在恢复时被清掉——失败不是进度。")
'''
        ),
        markdown(
            '''
## 5. 终态只由失败码决定；分支与返回值一律失败关闭

图纸上有两个框："平台判定（每次动手前要一个 Decision；不可用 → blocked）"与
"终态三值 blocked / needs_human / failed（由失败码决定）"。它们背后的规矩只有一条：

> **分支只由结构化 Decision 决定，终态只由失败码决定（`errors.STATUS_BY_CODE`）；
> 节点与引擎都不许自己发明状态，也没有任何一条"默认放行"的路径。**

这条规矩落地成一张查表（枚举里的每个失败码都必须在表里有归属）加上几种"运行时也要拒绝"的情形：

| 情形 | 谁拒绝 | 终态 |
| --- | --- | --- |
| 平台 / 检索 / 验证器 / 证据 / trace / 工具不可用或被拒、熔断打开 | 节点按失败码查表 | `blocked`（平台侧说不清楚，禁止继续） |
| 上限击穿、审批不合法（缺 / 过期 / 主体不符 / 参数漂移 / 已用完）、副作用状态未知 | 节点 / 门禁 / limits | `needs_human`（要人来做决定） |
| 状态非法、节点契约、checkpoint 缺失或损坏、引擎不可用 | 解析层 / 引擎 | `failed`（编排自己坏了） |
| 未知路由标签 | `StepExecutor.route` | `failed`：拒绝猜下一步 |
| 未知节点 / 节点没返回 `NodeOutcome` | `StepExecutor.step` | `failed`：契约不成立 |

输出怎么读：先看"失败码 → 终态"的规模（每个枚举成员都必须有归属，少一个就断言失败），
再看四条**现场跑出来的**失败关闭路径——失败码与详细说明都是从真实异常里读出来的，
不是抄文档。
'''
        ),
        code(
            '''
# 5. 终态映射表 + 四种失败关闭（全部现场跑出来）
unmapped_codes = tuple(code.value for code in FailureCode if code not in STATUS_BY_CODE)
terminal_counts = {}
representative = {}
for code in FailureCode:
    status = STATUS_BY_CODE.get(code, RunStatus.FAILED)
    terminal_counts[status] = terminal_counts.get(status, 0) + 1
    representative.setdefault(status, []).append(code.value)
meanings = {
    "blocked": "平台侧说不清楚（不可用 / 被拒 / trace 断裂 / 熔断）：禁止继续",
    "needs_human": "上限或审批要求人来做决定",
    "failed": "编排自己坏了（状态非法 / 节点契约 / checkpoint / 引擎不可用）",
}
print(pad("终态", 14) + pad("失败码个数", 12) + pad("代表码", 48) + "含义")
print("-" * 128)
for status in sorted(terminal_counts, key=lambda item: item.value):
    codes = representative[status]
    head = ", ".join(codes[:2]) + ("…" if len(codes) > 2 else "")
    print(pad(status.value, 14) + pad(terminal_counts[status], 12) + pad(head, 48)
          + meanings[status.value])
print()
print("失败码总数:", len(list(FailureCode)), "| 没有登记终态的:", unmapped_codes or "（一个都没有）")
assert not unmapped_codes, unmapped_codes
assert {code.value for code in STATUS_BY_CODE} == {code.value for code in FailureCode}
assert STATUS_BY_CODE[FailureCode.APPROVAL_PARAM_MISMATCH] is RunStatus.NEEDS_HUMAN
assert STATUS_BY_CODE[FailureCode.EVIDENCE_UNAVAILABLE] is RunStatus.BLOCKED
assert STATUS_BY_CODE[FailureCode.STATE_INVALID] is RunStatus.FAILED
print()

failures = []

# 5a. 未知路由标签：分支函数给出一个图定义里没有的标签 → 拒绝猜下一步。
odd_spec = GraphSpec(
    edges=DEFAULT_SPEC.edges,
    routers=(
        Router(name="validation_outcome", source="validation",
               targets={"pass": "testing", "fail": "repair"}),
        Router(name="testing_outcome", source="testing",
               targets={"pass": "review", "fail": "repair"}),
    ),
)
odd_executor = support.step_executor(
    TEMP, name="route-label", spec=odd_spec,
    context=support.node_context(
        TEMP, name="route-label", author=ScriptedAuthor([support.write_change()]),
        client=support.scripted_client(evaluate=(support.allow_outcome(),),
                                       retrieve=(support.retrieval_ok(),),
                                       readiness_value=support.readiness()),
        runner=RecordingToolRunner((support.executed_outcome(),))),
    router_fns={**ROUTERS, "validation_outcome": lambda state: "weird"})
odd_state = empty_state("route-task", limits=RunLimits())
for node in (NodeId.REQUIREMENT_ANALYSIS, NodeId.POLICY_RETRIEVAL, NodeId.ARCHITECTURE_PLANNING,
             NodeId.IMPLEMENTATION):
    odd_state = odd_executor.step(odd_state.replace(stage=node)).state
assert odd_state.failure is None, odd_state.failure
assert odd_state.stage is NodeId.VALIDATION, odd_state.stage
route_error = ""
try:
    odd_executor.route(odd_state, "pass")   # 分支函数在这里被求值
except NodeContractError as error:
    route_error = str(error)
assert "未知路由标签" in route_error, route_error
failures.append(("节点给出未登记的路由标签", FailureCode.NODE_CONTRACT_INVALID.value,
                 STATUS_BY_CODE[FailureCode.NODE_CONTRACT_INVALID].value, route_error))

# 5b. 节点没返回 NodeOutcome：返回值也是契约的一部分。
naughty_executor = support.step_executor(
    TEMP, name="non-outcome",
    nodes={NodeId.REQUIREMENT_ANALYSIS: lambda state, context: {"ok": True}})
naughty = naughty_executor.step(empty_state("naughty-task", limits=RunLimits()))
assert naughty.state.failure.code is FailureCode.NODE_CONTRACT_INVALID
failures.append(("节点返回了非 NodeOutcome", naughty.state.failure.code.value,
                 naughty.state.status.value, naughty.state.failure.detail))

# 5c. 未知节点：节点表里没有这一项，一律拒绝。
unknown_executor = support.step_executor(TEMP, name="unknown-node", nodes={})
unknown = unknown_executor.step(empty_state("unknown-task", limits=RunLimits()))
assert unknown.state.failure.code is FailureCode.NODE_UNKNOWN
failures.append(("节点不在节点表里", unknown.state.failure.code.value,
                 unknown.state.status.value, unknown.state.failure.detail))

# 5d. 上限击穿：repair 轮次是数据（RunLimits），超限抛 LimitExceeded → needs_human。
try:
    charge(empty_state("limit-task", limits=RunLimits(max_repair_rounds=0)),
           LimitKind.REPAIR_ROUNDS, 1)
    raise AssertionError("击穿上限却没有报错")
except OrchestrationError as error:
    assert STATUS_BY_CODE[error.code] is RunStatus.NEEDS_HUMAN
    failures.append(("repair 轮次击穿上限", error.code.value,
                     STATUS_BY_CODE[error.code].value, error.detail))

print(pad("失败关闭路径", 28) + pad("失败码", 24) + pad("终态", 13) + "说明")
print("-" * 122)
for name, code, terminal, detail in failures:
    print(pad(name, 28) + pad(code, 24) + pad(terminal, 13) + detail[:58])
print()
print("小结：4 条路径全部停在显式失败码上，没有一条继续往下走；",
      "终态是查表得来的，节点与引擎都没有发明状态的余地。")
'''
        ),
        markdown(
            '''
## 6. 跑一张最小图：平台说话、受控执行动手、审批门禁挡人

把前几节拼起来跑一遍。任务很小：改受控工作区里的一个文件；假平台第 0 轮验证**拦住**
（带一条结构化 violation），第 1 轮放行；于是工作流走一遍
"验证失败 → 修复 → 再验证 → 测试 → 收尾"。

这一节要现场证明四件事：

1. **每个动手的节点在动手前都问了平台**：`traces` 里每个节点一条 `PolicyTraceRef`
   （含 request_id、决定与规则集哈希）；
2. **分支由结构化 Decision 决定**：第 0 轮 `block` 才走到修复节点，而修复节点只读 violation；
3. **写入不落在编排层手里**：副作用只由 `ToolRunner` 端口发生，本节用只记录的实现，
   于是"改了几次文件"变成了一个可以数的数字；
4. **报告里的引擎名如实**：装配时声明 `engine="auto"`，报告就写它实际用的那个。

后半段做图纸上那句"**图到达了审批节点 ≠ 用户批准**"：把假平台改成
`required_action="approval"`（平台说这个动作要人工批准），审批收件箱故意留空——
工作流必须停在 `needs_human`，而且**一次工具调用都没有发生**。
'''
        ),
        code(
            '''
# 6. 最小图：block → repair → pass → testing → review（走真实节点与真实引擎）
def run_mini(task_id, *, client, runner, name, approvals=None):
    """按生产装配路径跑一次最小图：端口全部注入，路径全在 TEMP 下。"""

    config = support.graph_config(
        TEMP, name=name, approvals_dir=approvals, engine="auto",
        limits=RunLimits(max_repair_rounds=2, max_tool_calls=8, max_node_runs=24),
    )
    task = support.task_spec(task_id, trace_id="trace-" + task_id)
    assembly = build_assembly(
        config, task=task, author=ScriptedAuthor({0: BROKEN, 1: FIXED}),
        client=client, tool_runner=runner,
        checkpoint_store=RetryStore(JsonCheckpointStore(config.checkpoint_dir)),
    )
    state = empty_state(task.task_id, limits=config.limits, trace_id=task.trace_id)
    return assembly.engine.run(task_id=task.task_id, state=state), assembly, config, task


BROKEN = support.write_change(summary="第 0 轮：会被验证挡住的改动")
FIXED = support.write_change(
    summary="第 1 轮：按结构化 violation 修复",
    content=support.write_change().content.replace("处理创建请求。", "处理创建请求（修复版）。"))
repair_client = support.scripted_client(
    evaluate=(support.allow_outcome(), support.allow_outcome()),
    retrieve=(support.retrieval_ok(),),
    validate=(support.validate_block(), support.validate_allow(), support.validate_allow()),
    readiness_value=support.readiness(),
)
repair_runner = RecordingToolRunner((support.executed_outcome(), support.executed_outcome()))
report, assembly, config, task = run_mini(
    "mini-repair", client=repair_client, runner=repair_runner, name="mini-repair")

print(pad("节点", 24) + pad("标签", 8) + pad("状态", 9) + "输出摘要")
print("-" * 100)
for step in report.steps:
    print(pad(step.node, 24) + pad(step.label, 8) + pad(step.status, 9)
          + step.outcome_digest[:32] + "…")
print("-" * 100)
print("终态:", report.status.value, "| 报告里的引擎名:", report.engine,
      "| 恢复模式:", report.resume_mode, "| 落盘次数:", report.checkpoints)
print("工具端口真的被调用了几次:", len(repair_runner.calls),
      "| 每次的工具:", [call.tool_id for call in repair_runner.calls])
assert report.status is RunStatus.COMPLETED
assert report.engine in ("reference", "langgraph")
assert [step.node for step in report.steps] == [
    "requirement_analysis", "policy_retrieval", "architecture_planning", "implementation",
    "validation", "repair", "validation", "testing", "review",
]
assert len(repair_runner.calls) == 2
assert report.state.counters.repair_rounds == 1 and report.state.counters.tool_calls == 2

print()
print(pad("平台判定（每个动手的节点一条）", 28) + pad("request_id", 32) + pad("决定", 9)
      + "规则集哈希前 12 位")
print("-" * 110)
for trace in report.state.traces:
    print(pad(trace.node.value, 28) + pad(trace.request_id, 32) + pad(trace.decision.value, 9)
          + (trace.rule_set_hash or "-")[:12])
print("-" * 110)
assert tuple(item.node for item in report.state.traces) == (
    NodeId.IMPLEMENTATION, NodeId.VALIDATION, NodeId.REPAIR, NodeId.VALIDATION, NodeId.TESTING)
assert len(repair_client.calls) == 6, [route for route, _ in repair_client.calls]
print("平台调用次数:", len(repair_client.calls),
      "| 用到的路由:", sorted({route for route, _ in repair_client.calls}))
print("artifacts（只有引用与摘要，没有正文）:",
      [(item.artifact_id, item.digest[:12] + "…") for item in report.state.artifacts][:4], "…")
print("最后一次落盘的状态摘要:", report.state.digest()[:30] + "…")
print()

# 6b. 图到达审批节点 ≠ 用户批准：平台要审批、收件箱是空的 → needs_human，且零副作用。
empty_inbox = TEMP / "approval-inbox" / "empty"
empty_inbox.mkdir(parents=True, exist_ok=True)
approval_runner = RecordingToolRunner((support.executed_outcome(),))
approval_client = support.scripted_client(
    evaluate=(support.allow_outcome(required_action="approval"),),
    retrieve=(support.retrieval_ok(),),
    readiness_value=support.readiness(),
)
blocked_report, _, _, _ = run_mini(
    "mini-approval", client=approval_client, runner=approval_runner,
    name="mini-approval", approvals=empty_inbox)

print(pad("节点", 24) + pad("标签", 12) + pad("状态", 13) + "失败码")
print("-" * 96)
for step in blocked_report.steps:
    print(pad(step.node, 24) + pad(step.label, 12) + pad(step.status, 13) + (step.failure or "-"))
print("-" * 96)
print("终态:", blocked_report.status.value, "| 失败码:", blocked_report.failure.code.value)
print("门禁的说明:", blocked_report.failure.detail)
print("工具调用次数（必须是 0）:", len(approval_runner.calls),
      "| 但节点确实向执行器要过绑定:", len(approval_runner.bindings))
assert blocked_report.status is RunStatus.NEEDS_HUMAN
assert blocked_report.failure.code is FailureCode.APPROVAL_MISSING
assert not approval_runner.calls and len(approval_runner.bindings) == 1
print()
print("小结：同一份图，第 0 轮被验证挡住就自动进入修复；平台要审批而没人批准时，",
      "工作流停在 needs_human 且一个副作用都没有发生——这就是失败关闭。")
'''
        ),
        markdown(
            '''
## 7. 人工审批绑的是**平台口径**的 `action_hash`

最后一处最容易混的地方，也是图纸上"人工审批绑平台口径的 action_hash"那句：
编排层心里有两个标识符，它们**不是一回事**。

| 标识符 | 谁算的 | 覆盖什么 | 回答什么问题 |
| --- | --- | --- | --- |
| `action_id` | 编排层的节点（`_action_id`） | 任务 id、repair 轮次、改动内容摘要前 16 位 | "这次动作在我们这边叫什么名字"（幂等键） |
| `action_hash` | `ToolRunner.binding()`；真实实现里是 Phase 4 的 `build_action_request` | 工具 schema 哈希、规范化参数、主体、权限与上下文摘要 | "用户批准的到底是这一件事吗" |

把两者混为一谈的后果很具体：审批能通过编排层的检查，却在 Phase 4 的 pre-check 上被判
"参数或主体已经变化"。所以节点的顺序是"**先向执行器要绑定 → 用绑定去校验审批 →
最后把审批文件本身交给受控执行链复验**"——判定权始终在平台。

下面这个单元用的是**真实的** `PlatformToolRunner`：注册表是仓库里已审核的
`registry/tool-registry.yaml` 与 `registry/tool-registry.approved.json`（只读），
审计与台账各写在自己那个临时目录里，并**不执行**任何工具调用（只算绑定）。

输出怎么读：表格把同一件事的两种标识符并排打出来；接着是"参数改一个字符"之后两个值
的变化（都变了 → 旧审批自动作废）；最后用 Phase 4 的 `ApprovalRecord` 写一份真审批，
交给门禁校验并消费一次。
'''
        ),
        code(
            '''
# 7. 平台口径的 action_hash vs 编排层的幂等键（用真实的 PlatformToolRunner 算）
runner = PlatformToolRunner(
    registry_path=REPO_ROOT / "registry" / "tool-registry.yaml",
    approved_path=REPO_ROOT / "registry" / "tool-registry.approved.json",
    audit_path=TEMP / "binding" / "audit.jsonl",
    ledger_path=TEMP / "binding" / "ledger.jsonl",
    workspace=support.workspace_factory(TEMP / "binding"),
)
request = support.tool_request(tool_id="orc.fs.write")
binding = runner.binding(request)
drifted = runner.binding(support.tool_request(
    tool_id="orc.fs.write",
    params={**dict(request.params), "content": str(request.params["content"]) + " "}))
namespace = Change(path=str(request.params["file_path"]),
                   content=str(request.params["content"]))

print(pad("标识符", 22) + pad("值", 46) + "谁算的")
print("-" * 124)
print(pad("action_id（幂等键）", 22) + pad(namespace.digest().split(":")[-1][:16] + "…", 40)
      + "编排层节点：任务:轮次:改动摘要前 16 位")
print(pad("action_id（平台侧）", 22) + pad(request.action_id, 40)
      + "Phase 4 的动作 id：就是请求里的那个名字")
print(pad("action_hash", 22) + pad(binding.action_hash, 40)
      + "Phase 4：schema + 参数 + 主体 + 权限 + 上下文摘要")
print("-" * 124)
assert binding.action_hash != binding.action_id
assert binding.tool_id == "orc.fs.write" and binding.subject == "local-user"
print("两种标识符不是同一个值: True")
print("参数改一个字符（末尾多一个空格）→ 平台口径的哈希变化:",
      binding.action_hash != drifted.action_hash)
print("同一次改动 → 平台侧的动作 id 是幂等键，参数变了它不变:",
      binding.action_id == drifted.action_id)
assert binding.action_hash != drifted.action_hash
assert binding.action_id == drifted.action_id
print()

# 审批文件由 Phase 4 的 ApprovalRecord 写成（编排层不发明第二种审批语义）：
# 这里只把"审批绑到哪个哈希上"摊开——绑对了才可能通过，绑错了会被门禁按结构化字段分类。
approval_path = support.approval_file(TEMP / "approval-inbox" / "valid.json",
                                     action_hash=binding.action_hash,
                                     action_id=binding.action_id)
gate = ApprovalGate(TEMP / "approval-inbox")
record = gate.locate(binding.action_id)[1]
print(pad("审批记录字段", 22) + "值")
print("-" * 96)
for field in ("approval_id", "action_id", "tool_id", "subject", "granted_by_roles"):
    print(pad(field, 22) + str(getattr(record, field)))
print(pad("action_hash", 22) + record.action_hash)
print(pad("有效期", 22) + f"{record.granted_at.isoformat()} → {record.expires_at.isoformat()}")
assert record.action_hash == binding.action_hash
assert gate.resolve(binding.action_id) == approval_path
print()
print("门禁拿这份审批校验同一个动作，消费到的审批 id:", gate.use(
    empty_state("approval-task", limits=RunLimits()),
    node=NodeId.IMPLEMENTATION,
    action_hash=binding.action_hash,
    action_id=binding.action_id,
    tool_id=binding.tool_id,
    subject=binding.subject,
).approval_id)
print("小结：人工审批绑的是平台口径的 action_hash（覆盖 schema、参数、主体、权限）；",
      "编排层的幂等键只回答这次动作叫什么名字，两者混用就会在 pre-check 上被打回。")
'''
        ),
        markdown(
            '''
## 小结

七段代码对应图纸上的八步主线，每条结论都被断言钉住过：

1. **编排层是消费者，不是平台的一部分**：6 个平台包（policy / retrieval / validators /
   enforcement / adapters / policy_api）里，import 编排层的文件数为 **0**；
   工作流框架只有一个导入点（`orchestration/langgraph_engine.py`），而且是在**构造引擎时**
   才导入。`engine="langgraph"` 而框架不可用 → `EngineUnavailableError`（终态 `failed`）；
   `engine="auto"` 可以回落参考引擎，但回落的事实写在 `RunReport.engine` 里，
   绝不把参考引擎报成 LangGraph。
2. **图状态里不放正文**：状态是 21 个字段（`approvals` … `validation`），全是引用 / 计数 / 短结论；
   需求原文只活在内存里的
   `TaskSpec`，文件内容只活在受控工作区；未知字段、未知状态版本、绝对路径、含 `..` 的路径
   一律报错（不是忽略）。相同输入得到**逐字节相同**的状态——状态里没有墙钟字段。
3. **checkpoint 是单文件 + 原子替换**：先写 `<task_id>.checkpoint.tmp` 再 `os.replace`，
   记录带 `state_digest` 与 `record_digest` 两道校验；它有自己的 `STATE_SCHEMA_VERSION`
   （当前 1.0，**不跟随平台阶段**）。副作用之前先写"意图"并立刻刷盘（`NodeContext.commit`），
   恢复时才可能发现"开工未结算"。
4. **恢复比的是"当前平台"的凭据**：规则集 / 索引变了 → `revalidate`（清掉旧 trace 与旧验证
   结果，回到检索节点重评，不沿用旧 allow）；工具 schema 变了 → `reapprove`（旧审批作废）；
   协议世代变了 → 抛 `ResumeError` 拒绝恢复；凭据拿不到（`None`）按"变了"处理。
   恢复还会清掉上一轮的失败码与终态——失败不是工作流的进度。
5. **分支只由结构化 Decision 决定，终态只由失败码决定**：`FailureCode` 的 30 个取值全部登记在
   `errors.STATUS_BY_CODE`（blocked 10 / needs_human 12 / failed 8）；
   未知路由标签、未知节点、非 `NodeOutcome` 返回值、上限击穿全部现场跑成了显式失败。
6. **人工审批绑平台口径的 `action_hash`**："图到达了审批节点"不等于用户批准：
   审批收件箱为空时工作流停在 `needs_human`（`approval_missing`），且**零次工具调用**；
   参数改一个字符 → `action_hash` 变 → 旧审批自动作废。

**如果只记一句话**：编排层决定"怎么走"，平台决定"允不允许"；状态里只放引用，
checkpoint 里只放"下一步"，失败码决定终态——没有任何一条路径默认放行。

接着往下读：`04-受控执行.ipynb`（写入到底怎么被管住）、
`06-Policy-API.ipynb`（编排层问的那个平台长什么样）、
`00-技术总览.ipynb`（这些依赖方向为什么成立）。

本节的临时产物都在 `.tmp/tech-detail/07/` 下，跑完可以整目录删掉；
仓库里的清理命令是 `python tools/cleanup.py`。
'''
        ),
    ),
)

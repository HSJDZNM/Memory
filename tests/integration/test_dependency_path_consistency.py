"""依赖判定跨路径一致性（G6）：同一段代码，两条路径必须给出同一个结论。

缺口 G6 的原话是"同一条规则走两条路径结论不同"。本模块覆盖两件事：

1. **预执行 vs AST**（上半部分）：Phase 5 真解析（src/validators/python_ast.py +
   src/validators/depgraph.py）与 Phase 2 预执行（src/adapters/dsh/adapter.py 的
   propose_dependencies + src/policy/checkers.py 的 _forbidden_dependency）。
   预执行路径拿到的是**变更片段**、没有模块索引，因此存在已知差异——见 KNOWN_DIVERGENCES：
   它是断言，不是文档里的一句话。
2. **预执行 vs Phase 6 多 Agent 适配层**（下半部分）：同一个语义曾经有两份实现
   （`src/adapters/textfacts.py` 的旧口径只认行首字面写法），于是相对导入与动态导入
   在那条路径上**静默放行**。N1 修复后两条路径必须同口径——这里把它写成断言。

本模块不制造"两边名字集合相等"的假等价（预执行路径不可能知道模块索引），
比较的是**同一条 ARCH-001 规则的结论**：命中（block）还是不命中（allow）；
Phase 6 那一组还额外断言两边登记的依赖集逐项相等——结论相等可以是巧合，
依赖集相等才证明"是同一份引擎"。
所有路径共用同一个 PolicyContext、同一个 RuleSet、同一个判定入口 policy.engine.evaluate。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from conftest import POLICIES_DIR, REPO_ROOT, VALIDATOR_PROJECT, validators_config

from adapters.dsh.adapter import load_config, to_policy_context, to_policy_event
from adapters.loader import load_adapter
from policy.checkers import UNPROVEN_CHANGED_TEXT, UNPROVEN_DYNAMIC_IMPORT
from policy.engine import evaluate
from policy.loader import load_rule_set
from policy.models import Decision, RuleSet
from validators.pipeline import PipelineRequest, run_pipeline

pytestmark = pytest.mark.integration

REPO_ADAPTER_CONFIG = REPO_ROOT / "adapters" / "dsh" / "adapter.yaml"
# 目标文件必须是 controller：ARCH-001 的 scope 是 language=python + layer=controller。
TARGET = "src/shop/order_controller.py"

CONFIG = validators_config()
RULES = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)
ARCH_RULE = next(rule for rule in RULES.rules if rule.id == "ARCH-001")
# 只留 ARCH-001：比较的就是这一条规则的结论，别的规则（Ruff / docstring / pytest）
# 只会给结论加噪声，也让"两条路径同结论"这句话失去可判定性。
ARCH_RULES = RuleSet(rules=(ARCH_RULE,), source_paths=("policies/architecture/ARCH-001.yaml",))

CASE_TEXTS: dict[str, str] = {
    "正例：只依赖 service": "from shop.order_service import OrderService\n",
    "反例：from 点分路径 import": "from shop.order_repository import OrderRepository\n",
    "反例：from 包 import 子模块": "from shop import order_repository\n",
    "任务书形态：from pkg.repository import X": "from pkg.repository import X\n",
    "相对导入：from . import repository": "from . import repository\n",
    "动态导入（字面量目标）": (
        "import importlib\n\n\ndef load():\n"
        '    return importlib.import_module("repository")\n'
    ),
    "动态导入（目标不是字面量）": (
        "import importlib\n\n\ndef load(name):\n"
        "    return importlib.import_module(name)\n"
    ),
    "语法错误": (
        "from shop.order_repository import OrderRepository\n\n\ndef broken(:\n"
        "    return 1\n"
    ),
}

# 每条输入的**正确**结论（两条路径都必须等于它，因此测试不是"两边一起错也算过"）。
EXPECTED_ARCH_BLOCK: dict[str, bool] = {
    "正例：只依赖 service": False,
    "反例：from 点分路径 import": True,
    "反例：from 包 import 子模块": True,
    "任务书形态：from pkg.repository import X": True,
    "相对导入：from . import repository": True,
    "动态导入（字面量目标）": True,
    "动态导入（目标不是字面量）": True,
    "语法错误": True,
}

# 两条路径不**等价**的已知情形：预执行路径没有模块索引（Adapter 不读文件系统），
# 因此"顶层包存在、模块不存在"它判不了。写后（Phase 5）仍然失败关闭，所以系统整体
# 没有放行；但预执行这一道闸确实弱一些 —— 钉住它，别假装等价。
KNOWN_DIVERGENCES: dict[str, tuple[str, bool, bool, str]] = {
    "模块不存在且名字里没有组件词": (
        "from shop.missing_service import MissingService\n",
        True,
        False,
        "AST 路径：顶层包 shop 存在但模块不存在 → unresolved → 失败关闭；"
        "预执行路径：只能看到文本里的模块名，没有索引可查 → 不命中。"
        "差距来源是「预执行路径不读文件系统」，不是判定语义不同。",
    ),
}


@pytest.fixture()
def workspace(tmp_root: Path) -> Path:
    """验证器夹具项目的一份可写副本（两条路径都在它上面跑）。"""

    target = tmp_root / "consistency-workspace"
    shutil.copytree(VALIDATOR_PROJECT, target)
    return target


@pytest.fixture()
def adapter_config(tmp_root: Path, workspace: Path):
    """Phase 2 形态的 adapter 配置，但 layer / language 的 pattern 取自真实数据文件。

    注意：adapters/dsh/adapter.yaml 是 Phase 6 的配置（含 ledger_alias / window_seconds
    等 Phase 2 不认识的字段，Phase 2 的 load_config 会按未知字段拒绝它）。
    因此这里只把**声明本身**搬过来（pattern / layer / language 原样），
    再走 Phase 2 的加载器 —— 测的仍然是仓库真实声明，不是测试另写一份。
    """

    document = yaml.safe_load(REPO_ADAPTER_CONFIG.read_text(encoding="utf-8"))
    payload = {
        "project_root": str(workspace),
        "rules": [str(POLICIES_DIR)],
        "project": document["project"],
        "layers": document["layers"],
        "default_layer": document["default_layer"],
        "languages": document["languages"],
        "default_language": document["default_language"],
    }
    path = tmp_root / "config" / "consistency.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="",
    )
    return load_config(path)


def arch_blocked(result) -> bool:
    """ARCH-001 是否判定命中（block）。"""

    return any(item.rule_id == "ARCH-001" for item in result.violations)


def edit_payload(workspace: Path, text: str, *, target: str = TARGET) -> dict[str, object]:
    """一条 dsh PreToolUse/edit 载荷：old_string 空，new_string 就是"本次引入的文本"。

    Phase 2 与 Phase 6 的 dsh 路径喂的是**同一份**载荷（同一批字段、同一个目标文件），
    两条路径的差异因此只剩代码路径本身。
    """

    return {
        "session_id": "sess-consistency",
        "transcript_path": "",
        "cwd": str(workspace),
        "hook_event_name": "PreToolUse",
        "tool_name": "edit",
        "tool_use_id": "call-consistency",
        "tool_input": {"file_path": target, "old_string": "", "new_string": text},
    }


def pre_path_verdict(workspace: Path, config, text: str, *, target: str = TARGET):
    """预执行路径：edit 载荷 → PolicyEvent → PolicyContext → evaluate（无证据）。"""

    decision = to_policy_event(edit_payload(workspace, text, target=target), config=config)
    assert decision.event is not None, decision.reason
    context = to_policy_context(decision.event, config=config)
    return arch_blocked(evaluate(ARCH_RULES, context)), context


def ast_path_verdict(workspace: Path, text: str, context) -> bool:
    """AST / 依赖图路径：真实验证器流水线 + 同一个 PolicyContext 与 RuleSet。"""

    (workspace / TARGET).write_text(text, encoding="utf-8", newline="")
    report = run_pipeline(
        PipelineRequest(target=TARGET, workspace=workspace, context=context, rules=ARCH_RULES),
        config=CONFIG,
    )
    return arch_blocked(evaluate(ARCH_RULES, context, evidence=report.bundle))


@pytest.mark.parametrize("label", list(CASE_TEXTS))
def test_both_paths_reach_the_same_arch_001_verdict(
    workspace: Path, adapter_config, label: str
) -> None:
    text = CASE_TEXTS[label]

    pre_blocked, context = pre_path_verdict(workspace, adapter_config, text)
    ast_blocked = ast_path_verdict(workspace, text, context)

    assert pre_blocked == ast_blocked, (
        label
        + "：预执行路径="
        + str(pre_blocked)
        + "，AST/依赖图路径="
        + str(ast_blocked)
        + "；context.dependencies="
        + repr(list(context.dependencies))
    )
    assert pre_blocked is EXPECTED_ARCH_BLOCK[label], label + "：结论本身就不对"


@pytest.mark.parametrize("label", list(KNOWN_DIVERGENCES))
def test_known_divergences_are_pinned_not_pretended_away(
    workspace: Path, adapter_config, label: str
) -> None:
    text, expected_ast, expected_pre, reason = KNOWN_DIVERGENCES[label]

    pre_blocked, context = pre_path_verdict(workspace, adapter_config, text)
    ast_blocked = ast_path_verdict(workspace, text, context)

    assert ast_blocked is expected_ast, label + "：" + reason
    assert pre_blocked is expected_pre, label + "：" + reason

# ---------------------------------------------------------------------- Phase 6 多 Agent 路径（N1）
#
# 上面测的是"预执行（Phase 2 dsh）与 AST（Phase 5）"的已知差异；下面测的是**同一个语义
# 的另一条产品路径**：Phase 6 的多 Agent 适配层。缺口 G6 在这条路径上曾经完全成立——
# json_adapter / event_adapter / dsh_adapter 三处各自调用 adapters.textfacts 的旧口径，
# 相对导入与动态导入全部静默放行（账本上写的是 allow）。
#
# 修复的形状是"一个引擎 + 一个接线点"：提取发生在 base.Adapter.to_policy_context
# （那里 file 已归一化、language 已由配置声明解析），Phase 2 与 Phase 6 因此共用同一份实现。


@pytest.fixture()
def phase6_dsh_adapter(tmp_root: Path, workspace: Path):
    """Phase 6 的 dsh Adapter：声明原样搬过来，锚在**同一个工作区**。

    这样两条路径的 file / layer / language 逐项相同，"得到同一结论"这句话才不被
    "目标文件不同"这种噪声污染。
    """

    document = yaml.safe_load(REPO_ADAPTER_CONFIG.read_text(encoding="utf-8"))
    payload = {
        "schema_version": document["schema_version"],
        "project_root": str(workspace),
        "rules": [str(POLICIES_DIR)],
        "project": document["project"],
        "layers": document["layers"],
        "default_layer": document["default_layer"],
        "languages": document["languages"],
        "default_language": document["default_language"],
    }
    path = tmp_root / "config" / "phase-6-consistency.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="",
    )
    return load_adapter("dsh", root=REPO_ROOT, config_path=path)


@pytest.fixture()
def canonical_adapter():
    """Phase 6 的规范协议消费者（generic-json）：载荷形状与 dsh 完全不同。"""

    return load_adapter("generic-json", root=REPO_ROOT)


@pytest.fixture()
def legacy_adapter():
    """Phase 6 的事件型 Adapter（hook-command）：第三个旧调用点。"""

    return load_adapter("legacy-post-only", root=REPO_ROOT)


PARITY_TEXTS: dict[str, str] = {
    "相对导入：from . import repository": "from . import repository\n",
    "字面量动态导入：importlib.import_module(\"repository\")": (
        'import importlib\n\nimportlib.import_module("repository")\n'
    ),
    "非字面量动态导入：importlib.import_module(name)": (
        "import importlib\n\n\ndef load(name):\n    return importlib.import_module(name)\n"
    ),
    "不可解析片段：def broken(:": "def broken(:\n    return 1\n",
    "正例：只依赖 service": "from shop.order_service import OrderService\n",
}

# 每条输入的**正确**结论（两条路径都必须等于它，测试因此不是"两边一起错也算过"）。
PARITY_EXPECTED_BLOCK: dict[str, bool] = {
    "相对导入：from . import repository": True,
    "字面量动态导入：importlib.import_module(\"repository\")": True,
    "非字面量动态导入：importlib.import_module(name)": True,
    "不可解析片段：def broken(:": True,
    "正例：只依赖 service": False,
}

RELATIVE_LABEL = "相对导入：from . import repository"
UNPROVEN_DYNAMIC_LABEL = "非字面量动态导入：importlib.import_module(name)"
UNPARSEABLE_LABEL = "不可解析片段：def broken(:"


def parity_message(label: str, first, second) -> str:
    """"两条路径必须同口径"失败时的可诊断说明：两边完整依赖集都打出来。

    依赖集不等时，看消息就知道差的是哪条保留标记 / 哪个名字，不用重跑一次。
    """

    return (
        label
        + "：Phase 2 依赖="
        + repr(list(first.dependencies))
        + "，另一条路径依赖="
        + repr(list(second.dependencies))
        + "；file="
        + repr((first.file, second.file))
        + "，language="
        + repr((first.language, second.language))
    )


def phase6_dsh_verdict(workspace: Path, adapter, text: str, *, target: str = TARGET):
    """Phase 6 路径：钩子载荷 → 规范事件 → PolicyContext → evaluate（无证据）。"""

    event = adapter.to_policy_event(
        edit_payload(workspace, text, target=target), workspace=workspace
    )
    context = adapter.to_policy_context(event, workspace=workspace)
    return arch_blocked(evaluate(ARCH_RULES, context)), context


def canonical_context(workspace: Path, adapter, text: str, *, target: str = TARGET):
    """规范事件路径：canonical-json 载荷 → PolicyContext。"""

    document = {
        "schema_version": "1.0",
        "event_id": "req-canonical:call-consistency",
        "event_type": "tool.pre_execute",
        "request_id": "req-canonical",
        "agent_version": "third-party-0.9.0",
        "tool": "edit",
        "operation": "edit",
        "payload": {"path": target, "text": text},
    }
    event = adapter.to_policy_event(document, workspace=workspace)
    return adapter.to_policy_context(event, workspace=workspace)


@pytest.mark.parametrize("label", list(PARITY_TEXTS))
def test_phase_6_dsh_path_agrees_with_the_phase_2_path(
    workspace: Path, adapter_config, phase6_dsh_adapter, label: str
) -> None:
    """同一段文本、同一份载荷：Phase 2 dsh 路径与 Phase 6 多 Agent 路径同一结论。"""

    text = PARITY_TEXTS[label]

    phase2_blocked, phase2_context = pre_path_verdict(workspace, adapter_config, text)
    phase6_blocked, phase6_context = phase6_dsh_verdict(workspace, phase6_dsh_adapter, text)

    assert phase2_blocked is PARITY_EXPECTED_BLOCK[label], label + "：Phase 2 的结论本身就不对"
    assert phase6_blocked is PARITY_EXPECTED_BLOCK[label], (
        label
        + "：Phase 6 得到 "
        + str(phase6_blocked)
        + "；context.dependencies="
        + repr(list(phase6_context.dependencies))
    )
    # 结论相同 **且**登记的依赖集逐项相同：证明两条路径用的是同一份引擎，
    # 而不是"两边各写一份、恰好同结论"。
    assert phase6_context.dependencies == phase2_context.dependencies, parity_message(
        label, phase2_context, phase6_context
    )
    assert phase6_context.file == phase2_context.file == TARGET
    assert phase6_context.language == phase2_context.language == "python"


@pytest.mark.parametrize("label", list(PARITY_TEXTS))
def test_canonical_path_agrees_with_the_phase_2_path(
    workspace: Path, adapter_config, canonical_adapter, label: str
) -> None:
    """规范事件（canonical-json）是第三条路径：载荷形状不同，口径必须相同。"""

    text = PARITY_TEXTS[label]

    phase2_blocked, phase2_context = pre_path_verdict(workspace, adapter_config, text)
    context = canonical_context(workspace, canonical_adapter, text)

    assert phase2_blocked is PARITY_EXPECTED_BLOCK[label]
    assert arch_blocked(evaluate(ARCH_RULES, context)) is PARITY_EXPECTED_BLOCK[label], (
        label + "：canonical 路径登记的依赖=" + repr(list(context.dependencies))
    )
    assert context.dependencies == phase2_context.dependencies, parity_message(
        label, phase2_context, context
    )
    assert context.file == TARGET
    assert context.language == "python"


def test_phase_6_registers_the_unproven_markers(workspace: Path, phase6_dsh_adapter) -> None:
    """"证明不了"必须是**登记进上下文的状态**，而不是一个空依赖集。"""

    _, dynamic_context = phase6_dsh_verdict(
        workspace, phase6_dsh_adapter, PARITY_TEXTS[UNPROVEN_DYNAMIC_LABEL]
    )
    assert dynamic_context.dependencies == (UNPROVEN_DYNAMIC_IMPORT, "importlib")

    _, broken_context = phase6_dsh_verdict(
        workspace, phase6_dsh_adapter, PARITY_TEXTS[UNPARSEABLE_LABEL]
    )
    assert broken_context.dependencies == (UNPROVEN_CHANGED_TEXT,)


@pytest.mark.parametrize("label", [RELATIVE_LABEL, UNPROVEN_DYNAMIC_LABEL])
def test_event_adapter_path_registers_the_same_dependencies(
    workspace: Path, adapter_config, legacy_adapter, label: str
) -> None:
    """第三个调用点（event_adapter 的钩子线协议）也必须是同一份口径。

    它是**事后**事件（该 Agent 的能力上限就是 post_only），所以这里比的是
    "登记下来的依赖集"，不是"判定结论"——事后事件本来就不承担阻断。
    """

    text = PARITY_TEXTS[label]
    document = {
        "hook_event_name": "PostToolUse",
        "session_id": "legacy-consistency",
        "tool_name": "save_file",
        "tool_use_id": "call-legacy-consistency",
        "cwd": str(workspace),
        "tool_input": {"file_path": TARGET, "text": text},
        "tool_response": "saved",
    }

    event = legacy_adapter.to_policy_event(document, workspace=workspace)
    context = legacy_adapter.to_policy_context(event, workspace=workspace)
    _, phase2_context = pre_path_verdict(workspace, adapter_config, text)

    assert context.dependencies == phase2_context.dependencies, parity_message(
        label, phase2_context, context
    )
    assert context.file == TARGET
    assert context.language == "python"


def test_non_python_target_is_not_a_silent_pass(
    workspace: Path, adapter_config, phase6_dsh_adapter
) -> None:
    """language != "python"：依赖集为空，但这不是"静默放行"。

    三件事必须同时成立，否则"不提取"会退化成新的静默放行：

    1. language 是配置**声明**解析出来的（`.md` 命中 default_language: text），不是猜的；
    2. 依赖集为空（governed_dependencies 的 language 门控）；
    3. 规则不是"判定通过"，而是因为 scope 的 language 维度不匹配被**明确跳过**，
       原因写进 skipped_rules——决策载荷里看得见"这条规则没参与判定"。
    """

    md_target = "docs/README.md"  # layers: **/*.md → docs；default_language: text
    text = PARITY_TEXTS[RELATIVE_LABEL]

    phase2_blocked, phase2_context = pre_path_verdict(
        workspace, adapter_config, text, target=md_target
    )
    phase6_blocked, phase6_context = phase6_dsh_verdict(
        workspace, phase6_dsh_adapter, text, target=md_target
    )

    assert phase2_context.language == phase6_context.language == "text"
    assert phase2_context.dependencies == phase6_context.dependencies == ()
    assert phase2_blocked is False
    assert phase6_blocked is False

    result = evaluate(ARCH_RULES, phase6_context)

    assert result.decision is Decision.ALLOW
    assert not result.violations
    assert [item.rule_id for item in result.skipped_rules] == ["ARCH-001@1"]
    assert any("language" in reason for reason in result.skipped_rules[0].reasons)

    # 对照：同一段文本落在 python 的 controller 上必须阻断——否则上面的 allow
    # 说明不了"是语言门控（而不是别的东西）在起作用"。
    assert pre_path_verdict(workspace, adapter_config, text)[0] is True
    assert phase6_dsh_verdict(workspace, phase6_dsh_adapter, text)[0] is True


def test_missing_changed_text_is_empty_on_both_paths(
    workspace: Path, adapter_config, phase6_dsh_adapter
) -> None:
    """工具声明了 proposed_fields 但没有变更文本：两条路径都登记空依赖。

    这不是"证明不了"：空文本解析得动（parseable=True）、也没有动态导入，所以不留保留标记。
    把它写成用例，是为了让"两条路径同口径"覆盖到这个边界——既不能一边留标记、
    也不能一边把它当成"没有依赖"（两种做法都会让结论不可比）。
    """

    payload = edit_payload(workspace, "")

    decision = to_policy_event(payload, config=adapter_config)
    assert decision.event is not None, decision.reason
    phase2_context = to_policy_context(decision.event, config=adapter_config)

    event = phase6_dsh_adapter.to_policy_event(payload, workspace=workspace)
    phase6_context = phase6_dsh_adapter.to_policy_context(event, workspace=workspace)

    assert phase2_context.dependencies == phase6_context.dependencies == (), parity_message(
        "无变更文本", phase2_context, phase6_context
    )
    assert arch_blocked(evaluate(ARCH_RULES, phase2_context)) is False
    assert arch_blocked(evaluate(ARCH_RULES, phase6_context)) is False

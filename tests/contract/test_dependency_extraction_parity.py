"""N1 契约：依赖提取只有一份口径（Phase 2 dsh 路径 = Phase 6 多 Agent 路径）。

缺口 G6 的原话是"同一条规则走两条路径结论不同"。上一轮只修了 Phase 2 的 dsh 路径
（`adapters.dsh.adapter.propose_dependencies` 认得相对导入与动态导入，并把"证明不了"
变成显式状态），而三条 Phase 6 路径共用的 `adapters.textfacts.proposed_dependencies`
仍是行级正则的旧口径：同一段变更文本走 dsh 路径会被拦，走多 Agent 路径**静默放行**。

本轮把引擎搬进共享层 `adapters.textfacts`（冻结接口见 07 号文档 §5），两个 Adapter
家族都调同一份实现。本模块钉住的是**共享层自己的语义**：

- `propose_dependencies` 的三类结果（证明得了 / 动态目标不可证 / 片段解析不了）都是显式状态；
- `proposed_dependencies` 是与 Phase 2 逐字节一致的薄封装——它的回归证明在
  `tests/contract/test_dsh_adapter.py`，那里的断言一个字都不能改；
- `governed_dependencies` 按**声明的 language** 门控，并把"证明不了"登记成
  `policy.checkers.UNPROVEN_DEPENDENCY_TOKENS` 里的保留标记；
- 保留标记必须让依赖类规则**失败关闭**（解析失败不等于没有依赖，AGENTS.md 第 20 条）；
- payload 里显式声明的 `dependencies` 优先于从 `text` 派生（第三方 Adapter 向后兼容）。

跨路径"同一结论"在 `tests/integration/test_dependency_path_consistency.py` 里断言：
本模块只证明"引擎的语义是对的"，那里证明"两条路径真的都在用它"。
"""

from __future__ import annotations

import pytest
from conftest import REPO_ROOT, make_context, make_rule

from adapters.dsh.adapter import DshEventError
from adapters.dsh.adapter import propose_dependencies as phase_two_propose
from adapters.dsh.adapter import proposed_dependencies as phase_two_proposed
from adapters.loader import load_adapter
from adapters.models import parse_canonical_event
from adapters.textfacts import (
    DependencyProposal,
    DependencyTextError,
    governed_dependencies,
    propose_dependencies,
    proposed_dependencies,
)
from policy.checkers import UNPROVEN_CHANGED_TEXT, UNPROVEN_DYNAMIC_IMPORT
from policy.engine import evaluate
from policy.models import Decision, RuleSet, Severity

WORKSPACE = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"
TARGET = "src/shop/order_controller.py"

RELATIVE_IMPORT = "from . import repository\n"
DOTTED_IMPORT = "from shop.order_repository import OrderRepository\n"
GOOD_IMPORT = "from shop.order_service import OrderService\n"
LITERAL_DYNAMIC_IMPORT = 'import importlib\n\nimportlib.import_module("repository")\n'
UNPROVEN_DYNAMIC_IMPORT_TEXT = (
    "import importlib\n\n\ndef load(name):\n    return importlib.import_module(name)\n"
)
UNPARSEABLE_FRAGMENT = "def broken(:\n    return 1\n"

TEXTS: dict[str, str] = {
    "相对导入：from . import repository": RELATIVE_IMPORT,
    "点分路径：from shop.order_repository import X": DOTTED_IMPORT,
    "正例：只依赖 service": GOOD_IMPORT,
    "字面量动态导入：import_module(\"repository\")": LITERAL_DYNAMIC_IMPORT,
    "非字面量动态导入：import_module(name)": UNPROVEN_DYNAMIC_IMPORT_TEXT,
    "不可解析片段：def broken(:": UNPARSEABLE_FRAGMENT,
    "没有 import 的普通文本": "普通文本，没有 import",
}

ARCH_RULES = RuleSet(
    rules=(make_rule(),), source_paths=("policies/architecture/ARCH-001.yaml",)
)


# --------------------------------------------------------------------------- 一份引擎


@pytest.mark.parametrize("label", list(TEXTS))
def test_shared_engine_gives_the_phase_two_result(label: str) -> None:
    """共享层的提取结果必须与 Phase 2 的提取结果逐项相同（搬迁不改语义）。"""

    text = TEXTS[label]
    shared = propose_dependencies(text)
    phase_two = phase_two_propose(text)

    assert (shared.names, shared.unproven_dynamic, shared.parseable) == (
        phase_two.names,
        phase_two.unproven_dynamic,
        phase_two.parseable,
    )
    # 薄封装：proposed_dependencies 就是 names，不是"另一份实现"。
    assert proposed_dependencies(text) == shared.names
    assert phase_two_proposed(text) == shared.names


def test_shared_layer_error_is_not_the_dsh_event_error() -> None:
    """共享层不得依赖 dsh 的错误类型：dsh 的错误是 Phase 2 适配器自己的事实。"""

    assert issubclass(DependencyTextError, ValueError)
    assert not issubclass(DependencyTextError, DshEventError)
    with pytest.raises(DependencyTextError):
        propose_dependencies(123)  # type: ignore[arg-type]


def test_relative_import_is_a_proven_dependency() -> None:
    proposal = propose_dependencies(RELATIVE_IMPORT)

    assert proposal.names == (".repository",)
    assert proposal.unproven_dynamic == ()
    assert proposal.parseable is True
    assert proposal.unproven is False


def test_literal_dynamic_import_target_is_proven() -> None:
    proposal = propose_dependencies(LITERAL_DYNAMIC_IMPORT)

    assert proposal.names == ("importlib", "repository")
    assert proposal.unproven_dynamic == ()
    assert proposal.unproven is False


def test_non_literal_dynamic_import_is_unproven_not_ignored() -> None:
    """动态导入的目标不是字符串字面量：依赖集**无法静态确定**，不是"没有依赖"。

    这段文本里 `import importlib` 本身是证明得了的依赖，因此它仍然要出现在 names 里；
    "证明不了"是**附加**的事实（unproven_dynamic），不是把整份提案清空。
    """

    proposal = propose_dependencies(UNPROVEN_DYNAMIC_IMPORT_TEXT)

    assert proposal.names == ("importlib",)
    assert proposal.unproven_dynamic == ("import_module",)
    assert proposal.unproven is True


def test_unparseable_fragment_is_a_state_not_an_empty_result() -> None:
    proposal = propose_dependencies(UNPARSEABLE_FRAGMENT)

    assert proposal.names == ()
    assert proposal.parseable is False
    assert proposal.unproven is True
    # 默认值本身不是"证明不了"：空提案只有真的证明了才允许 unproven 为假。
    assert DependencyProposal().unproven is False


# --------------------------------------------------------------------------- 语言门控


def test_governed_dependencies_registers_names_and_markers() -> None:
    assert governed_dependencies(RELATIVE_IMPORT, language="python") == (".repository",)
    assert governed_dependencies(LITERAL_DYNAMIC_IMPORT, language="python") == (
        "importlib",
        "repository",
    )
    assert governed_dependencies(GOOD_IMPORT, language="python") == (
        "shop.order_service",
        "shop.order_service.orderservice",
    )
    # "证明不了"变成保留标记，而不是被丢掉；同一段文本里仍然证明得了的 import
    # （这里是 import importlib）照常登记——标记是**附加**的，不是"清空依赖集"。
    assert governed_dependencies(UNPROVEN_DYNAMIC_IMPORT_TEXT, language="python") == (
        UNPROVEN_DYNAMIC_IMPORT,
        "importlib",
    )
    assert governed_dependencies(UNPARSEABLE_FRAGMENT, language="python") == (
        UNPROVEN_CHANGED_TEXT,
    )


def test_governed_dependencies_are_gated_by_the_declared_language() -> None:
    """非 python：import 语法与 ast.parse 都不适用，依赖集为空。

    它是"按声明不提取"，不是"提取失败"——所以不留保留标记（标记的含义是
    "这段 python 文本的依赖集无法证明"）。"不提取"不能退化成静默放行的证明
    在集成用例里：`.md` 目标会因 scope 的 language 维度不匹配被明确跳过，
    原因写进 skipped_rules。
    """

    assert governed_dependencies(RELATIVE_IMPORT, language="text") == ()
    assert governed_dependencies(LITERAL_DYNAMIC_IMPORT, language="text") == ()
    assert governed_dependencies(UNPROVEN_DYNAMIC_IMPORT_TEXT, language=None) == ()
    assert governed_dependencies(UNPARSEABLE_FRAGMENT, language=None) == ()
    # 对照：同一段文本在 python 上必须给出结果，否则上面的 () 归因不明。
    assert governed_dependencies(RELATIVE_IMPORT, language="python") == (".repository",)
    assert governed_dependencies(UNPROVEN_DYNAMIC_IMPORT_TEXT, language="python") == (
        UNPROVEN_DYNAMIC_IMPORT,
        "importlib",
    )


# --------------------------------------------------------------------------- 失败关闭


@pytest.mark.parametrize("marker", [UNPROVEN_DYNAMIC_IMPORT, UNPROVEN_CHANGED_TEXT])
def test_unproven_markers_fail_closed(marker: str) -> None:
    """保留标记出现在 dependencies 里时，依赖类规则必须 critical 阻断。"""

    result = evaluate(ARCH_RULES, make_context(dependencies=[marker]))

    assert result.decision is Decision.BLOCK
    assert [item.rule_id for item in result.violations] == ["ARCH-001"]
    assert result.violations[0].severity is Severity.CRITICAL
    assert marker in result.violations[0].evidence.value


def test_marker_failure_close_is_attributable_to_the_marker() -> None:
    """"干净依赖 → allow"与"带标记 → block"必须都能观察到。"""

    clean = evaluate(ARCH_RULES, make_context(dependencies=["shop.order_service"]))

    assert clean.decision is Decision.ALLOW
    assert not clean.violations

    # 同一批里即使有正常的依赖，标记也不被抵消（critical 语义）。
    mixed = evaluate(
        ARCH_RULES,
        make_context(dependencies=["shop.order_service", UNPROVEN_CHANGED_TEXT]),
    )

    assert mixed.decision is Decision.BLOCK
    assert UNPROVEN_CHANGED_TEXT in mixed.violations[0].evidence.value


# --------------------------------------------------------------------------- 向后兼容


def test_explicit_payload_dependencies_win_over_text_derivation() -> None:
    """payload 里显式声明的 dependencies 优先：第三方 Adapter 可以自带依赖事实。

    外部规范事件**不允许**自带 payload.dependencies（`parse_canonical_event` 会拒绝），
    所以这里的显式声明只可能来自进程内的 Adapter——注入写法与
    `JsonAdapter._build_event` 注入 dependencies 时一致。
    """

    adapter = load_adapter("generic-json", root=REPO_ROOT)
    event = parse_canonical_event(
        {
            "schema_version": "1.0",
            "event_id": "req-explicit:call-1",
            "event_type": "tool.pre_execute",
            "request_id": "req-explicit",
            "agent_version": "third-party-0.9.0",
            "tool": "edit",
            "operation": "edit",
            "payload": {"path": TARGET, "text": RELATIVE_IMPORT},
        },
        agent_id="generic-json",
    )
    object.__setattr__(
        event,
        "payload",
        {**event.payload, "dependencies": ["vendor.explicit_repository"]},
    )

    context = adapter.to_policy_context(event, workspace=WORKSPACE)

    assert context.dependencies == ("vendor.explicit_repository",)
    # 派生结果与显式声明不同，所以"相等"证明的是优先级而不是巧合。
    assert governed_dependencies(RELATIVE_IMPORT, language="python") == (".repository",)
    assert arch_blocked(context) is True


def arch_blocked(context) -> bool:
    """ARCH-001 是否判定命中（block）。"""

    result = evaluate(ARCH_RULES, context)
    return any(item.rule_id == "ARCH-001" for item in result.violations)

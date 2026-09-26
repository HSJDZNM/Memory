"""工具表漂移检测（G10）：声明与运行期观察之间必须有会失败的检查。

为什么需要它：TOOL_TABLE 是**默认拒绝**的白名单，而它与运行期现实之间没有任何机制同步。
后果是"接线即瘫痪"—— 一挂上检查站，新工具全部判未知而阻断，而不是"新工具被评审过"。

观察数据来源（写清楚，否则结论不可复核）：

1. SESSION_OBSERVED_TOOLS：本次 Agent Teams 子会话工具目录的抄录（会话里真实可见的工具）；
2. tests/fixtures/agent_events/dsh/*.json：committed 的真实采集钩子载荷（离线可复现）。

拿不到观察数据时的口径是**报错**，不是跳过：tool_table_drift 对空观察集直接 DshEventError，
observed_tools_from_payloads 对形状不对的载荷直接 DshEventError ——
"没观察到"绝不能被读成"没有漂移"。
"""

from __future__ import annotations

import json

import pytest

from adapters.dsh.adapter import (
    DshEventError,
    TOOL_TABLE,
    observed_tools_from_payloads,
    tool_table_drift,
)

from conftest import DSH_EVENT_FIXTURES

pytestmark = pytest.mark.contract

# 本会话（T3 rule-fidelity 子会话）真实可见的工具清单，从会话工具目录抄录。
# 它同时也是 G10 的验收输入：这些名字里任何一个不在 TOOL_TABLE 里，下面的测试就会红。
SESSION_OBSERVED_TOOLS: tuple[str, ...] = (
    "ask_user_question",
    "create_goal",
    "edit",
    "exit_plan_mode",
    "get_goal",
    "glob",
    "grep",
    "interrupt_agent",
    "job_kill",
    "job_list",
    "job_output",
    "list_agents",
    "load_workspace_dependencies",
    "present",
    "pwsh",
    "read",
    "read_image",
    "run_code",
    "send_message",
    "skill",
    "spawn_teammate",
    "subagent",
    "subagent_fork",
    "team_task_create",
    "team_task_get",
    "team_task_list",
    "team_task_update",
    "todo_write",
    "update_goal",
    "wait_agent",
    "web_fetch",
    "web_search",
    "write",
)

# 工具表里有、本会话工具清单里没有的：dsh 侧的其它装配形态（bash / ralph / workflow ...）。
# 白名单允许比一次会话更宽；但"它们悄悄消失"同样要能被发现，因此这里显式钉住。
ADAPTER_ONLY_TOOLS: frozenset[str] = frozenset(
    {"bash", "list_subagent_models", "ralph", "str_replace_editor", "workflow"}
)

# tests/fixtures/agent_events/dsh/pre-tool-use-unknown-tool.json 是**反例夹具**：
# 它刻意用一个不在白名单里的 MCP 工具名，证明未知工具会被拒绝。
# 因此它是唯一被允许出现在差集里的"待评审"项 —— 除它之外出现任何新名字都必须评审。
DELIBERATELY_UNKNOWN_FIXTURE_TOOLS: frozenset[str] = frozenset({"mcp__github__create_issue"})


def test_session_tool_inventory_has_no_unreviewed_entries() -> None:
    """G10 的核心断言：会话里真实存在的工具都必须已经在白名单里（否则接线即瘫痪）。"""

    drift = tool_table_drift(
        SESSION_OBSERVED_TOOLS, source="SESSION_OBSERVED_TOOLS（本会话工具目录抄录）"
    )

    assert drift.unreviewed == (), (
        "以下工具在会话里真实存在但不在 TOOL_TABLE 里，必须先评审再决定分类："
        + repr(list(drift.unreviewed))
    )
    assert drift.clean


def test_tool_table_entries_outside_the_session_are_the_documented_ones() -> None:
    """反向也要钉住：白名单条目不许悄悄消失（消失会让某个工具的语义变成"未知"）。"""

    drift = tool_table_drift(
        SESSION_OBSERVED_TOOLS, source="SESSION_OBSERVED_TOOLS（本会话工具目录抄录）"
    )

    assert set(drift.absent) == set(ADAPTER_ONLY_TOOLS)
    assert set(TOOL_TABLE) == set(SESSION_OBSERVED_TOOLS) | set(ADAPTER_ONLY_TOOLS)


def test_a_new_tool_name_is_reported_for_review_instead_of_being_ignored() -> None:
    """机制必须能报出"待评审"，否则它就是空转的：这是它存在的意义。"""

    drift = tool_table_drift(
        (*SESSION_OBSERVED_TOOLS, "spawn_teammate_v2"),
        source="合成观察（证明新增项会被报出）",
    )

    assert drift.unreviewed == ("spawn_teammate_v2",)
    assert not drift.clean


def test_empty_observation_is_refused_not_read_as_no_drift() -> None:
    with pytest.raises(DshEventError):
        tool_table_drift((), source="空观察集")

    with pytest.raises(DshEventError):
        tool_table_drift(("edit",), source="   ")


def test_malformed_observation_payload_is_refused() -> None:
    with pytest.raises(DshEventError):
        observed_tools_from_payloads([{"tool_name": "edit"}, {"hook_event_name": "PreToolUse"}])

    with pytest.raises(DshEventError):
        observed_tools_from_payloads(["edit"])


def test_recorded_hook_fixtures_reproduce_the_same_verdict_offline() -> None:
    """第二种观察来源：committed 的真实采集载荷；目录为空同样按报错处理。"""

    files = sorted(DSH_EVENT_FIXTURES.glob("*.json"))
    assert files, "观察源为空：这不是'没有漂移'，是观察数据拿不到（" + str(DSH_EVENT_FIXTURES) + "）"

    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    observed = observed_tools_from_payloads(payloads)
    drift = tool_table_drift(observed, source="tests/fixtures/agent_events/dsh/*.json")

    assert set(drift.unreviewed) == set(DELIBERATELY_UNKNOWN_FIXTURE_TOOLS)
    assert "edit" in drift.observed

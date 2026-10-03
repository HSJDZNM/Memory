"""C3 方案 A 的等价性用例：check_wiring 的返回值必须逐字节不变。

它是什么
========

27 号 §3.6 的方案 A 把 adapters.dsh.hooks.check_wiring 的两段 / 三段判据抽成一个结构化
函数（budget_inequality_facts），check_wiring 由它格式化。这条路径是**失败关闭**的一部分
（返回值进 stderr 与 --self-check 的结论），所以抽取前后必须给出**逐字节相同**的字符串
——这就是 27 号 §6 的硬约束 B。

因此本文件先是**特性化用例**：表里的字面量是在抽取**之前**（树 = fc2a5dc）实测抄下来的，
不是从实现里算出来的。抽取之后它们必须仍然逐字相等；**用例变红就是行为变了**，
不许把期望值改成"新实现输出什么就是什么"。

覆盖的五种形态（2026-10-03 裁定①）
==================================

| 形态 | 用例 |
| --- | --- |
| 两段不等式 | two_term_pass / two_term_boundary_equal / two_term_float_* |
| 三段不等式 | three_term_pass / three_term_default_limit_pass / three_term_disabled_pass |
| 超预算 | two_term_over_budget / three_term_over_budget / three_term_default_limit_over_budget |
| 缺 hooks.json | missing_hooks_file / unparseable_hooks_file / no_path |
| timeout 是表达式 | two_term_timeout_expression / two_term_timeout_absent |
| timeout 是表达式（三段按默认值判） | three_term_expression_over_budget |

三条**边界**用例是抽取时最容易改坏的地方，所以一起钉住：两段用的是 timeout_sec * 1000
的**浮点**比较（不是 int() 之后的比较，two_term_float_above_boundary 会区分这两者）、
two_term_float_below_boundary 区分"0.5ms > 0ms"与"int(0.5) == 0"、
two_term_last_numeric_wins 钉住多条目时最后一个数字生效。

抽取之后本文件多了一半：结构化读数（budget_inequality_facts）的四面——状态闭集可自证、
violated 的 reason 与 check_wiring 的返回值逐字节相等（一份实现、两个调用点）、
unavailable 与 not_applicable 分得开（不是 0、也不是通过）、非整毫秒的读数不被舍入。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import pytest

from adapters.dsh.adapter import AdapterConfig, PreEvidenceConfig
from adapters.dsh.hooks import BUDGET_STATUSES, budget_inequality_facts, check_wiring

COMMAND = "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml"

# 缺文件时消息里是**文件名**（不是路径），所以这条用例的落点文件名是契约的一部分。
MISSING_NAME = "does-not-exist.json"

_TWO_TERM = (
    "hooks.json 的 timeout={timeout}s 不大于内部预算 5000ms：dsh 会先杀掉 Hook，"
    "而被杀在 dsh 协议里等同于放行，必须让内部预算先触发"
)
_THREE_TERM = (
    "pre_evidence 的预算之和 {total}ms（pre_evidence.timeout_ms={evidence} + timeout_ms=5000）"
    "不小于 dsh 侧的 {limit}ms：dsh 会先杀掉 Hook，而被杀在 dsh 协议里等同于放行；"
    "必须让取证与判定两段预算都在 dsh 超时之前触发"
)
_THREE_TERM_DEFAULT = (
    "pre_evidence 的预算之和 {total}ms（pre_evidence.timeout_ms={evidence} + timeout_ms=5000）"
    "不小于 dsh 侧的 {limit}ms（hooks.json 没写 timeout，按 dsh 默认 600000ms 计）："
    "dsh 会先杀掉 Hook，而被杀在 dsh 协议里等同于放行；"
    "必须让取证与判定两段预算都在 dsh 超时之前触发"
)
_NO_HOOK = "hooks.json 里没有指向 adapters.dsh.hooks 的命令；当前组合没有接入策略 Hook"
_ABSENT_HOOKS = (
    "接线自检缺席：没有提供 hooks.json 路径，无法证明 dsh 会注册本 Hook"
    "（dsh 在 hooks 配置读不到时不注册任何 hook，也不报错，等于没有治理）。"
    "确需在没有接线证据的情况下运行，必须显式声明 --allow-unverified-wiring"
)


class Case(NamedTuple):
    """一条等价性用例：身份 + 形态 + 抽取之前实测的返回值。"""

    case_id: str
    form: str
    expected: str


CASES = (
    # --- 两段不等式 ---
    Case("two_term_pass", "两段", ""),
    Case("two_term_boundary_equal", "两段", _TWO_TERM.format(timeout=5)),
    Case("two_term_float_above_boundary", "两段", ""),
    Case("two_term_float_below_boundary", "两段", ""),
    Case("two_term_last_numeric_wins", "两段", ""),
    Case("two_term_wins_over_three_term", "两段", _TWO_TERM.format(timeout=3)),
    # --- 三段不等式 ---
    Case("three_term_pass", "三段", ""),
    Case("three_term_default_limit_pass", "三段", ""),
    Case("three_term_disabled_pass", "三段", ""),
    # --- 超预算 ---
    Case("two_term_over_budget", "超预算", _TWO_TERM.format(timeout=3)),
    Case("two_term_timeout_zero", "超预算", _TWO_TERM.format(timeout=0)),
    Case(
        "three_term_over_budget",
        "超预算",
        _THREE_TERM.format(total=65000, evidence=60000, limit=60000),
    ),
    Case(
        "three_term_default_limit_over_budget",
        "超预算",
        _THREE_TERM_DEFAULT.format(total=605000, evidence=600000, limit=600000),
    ),
    Case("three_term_disabled_over_budget", "超预算", _TWO_TERM.format(timeout=3)),
    # --- timeout 是表达式 / 没写 ---
    Case("two_term_timeout_expression", "timeout 是表达式", ""),
    Case("two_term_timeout_absent", "timeout 是表达式", ""),
    Case(
        "three_term_expression_over_budget",
        "timeout 是表达式",
        _THREE_TERM_DEFAULT.format(total=605000, evidence=600000, limit=600000),
    ),
    # --- 缺 hooks.json（不存在 / 不可解析 / 没有指向本 Hook 的命令 / 没给路径）---
    Case(
        "missing_hooks_file",
        "缺 hooks.json",
        "hooks.json 不存在：" + MISSING_NAME + "；dsh 会因此不注册任何 hook（等于没有治理）",
    ),
    Case(
        "unparseable_hooks_file",
        "缺 hooks.json",
        "hooks.json 不可解析（JSONDecodeError）；dsh 会因此不注册任何 hook",
    ),
    Case("unrelated_command", "缺 hooks.json", _NO_HOOK),
    Case("no_commands", "缺 hooks.json", _NO_HOOK),
    Case("hooks_section_not_mapping", "缺 hooks.json", _NO_HOOK),
    Case("groups_not_list", "缺 hooks.json", _NO_HOOK),
    Case("entries_not_mapping", "缺 hooks.json", _NO_HOOK),
    Case("no_path", "缺 hooks.json", _ABSENT_HOOKS),
    Case("no_path_allowed", "缺 hooks.json", ""),
)

REQUIRED_FORMS = ("两段", "三段", "超预算", "缺 hooks.json", "timeout 是表达式")


# --------------------------------------------------------------------------- 夹具


def _write(tmp_path: Path, name: str, document: object) -> Path:
    path = tmp_path / name
    text = json.dumps(document, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _hooks_document(
    timeout: object = None, *, command: str = COMMAND, present: bool = True
) -> dict:
    entry: dict = {"type": "command", "command": command}
    if present:
        entry["timeout"] = timeout
    return {"hooks": {"PreToolUse": [{"matcher": "", "hooks": [entry]}]}}


def _config(
    tmp_path: Path, *, timeout_ms: int = 5000, pre_evidence: object = None
) -> AdapterConfig:
    return AdapterConfig(
        project_root=tmp_path,
        rule_dirs=(),
        timeout_ms=timeout_ms,
        pre_evidence=pre_evidence,  # type: ignore[arg-type]
    )


def _evidence(
    tmp_path: Path, *, timeout_ms: int = 60000, enabled: bool = True
) -> PreEvidenceConfig:
    return PreEvidenceConfig(
        enabled=enabled,
        registry_root=tmp_path,
        workspace=tmp_path,
        shadow_root=tmp_path / "shadow",
        timeout_ms=timeout_ms,
    )


def _hooks(
    tmp_path: Path,
    name: str,
    timeout: object = None,
    *,
    present: bool = True,
    command: str = COMMAND,
) -> Path:
    return _write(tmp_path, name, _hooks_document(timeout, present=present, command=command))


# --------------------------------------------------------------------------- 调用点


def _two_term_pass(tmp_path: Path) -> str:
    return check_wiring(_config(tmp_path), hooks_config_path=_hooks(tmp_path, "ok.json", 30))


def _two_term_boundary_equal(tmp_path: Path) -> str:
    return check_wiring(_config(tmp_path), hooks_config_path=_hooks(tmp_path, "equal.json", 5))


def _two_term_float_above_boundary(tmp_path: Path) -> str:
    # 5.0005s = 5000.5ms > 5000ms：浮点比较判"没超"，int() 之后的比较会判"超了"。
    return check_wiring(_config(tmp_path), hooks_config_path=_hooks(tmp_path, "float.json", 5.0005))


def _two_term_float_below_boundary(tmp_path: Path) -> str:
    # 0.0005s = 0.5ms，内部预算 0ms：0.5 <= 0 不成立所以放行；int(0.5) == 0 会判成违反。
    return check_wiring(
        _config(tmp_path, timeout_ms=0), hooks_config_path=_hooks(tmp_path, "float0.json", 0.0005)
    )


def _two_term_last_numeric_wins(tmp_path: Path) -> str:
    document = _hooks_document(100)
    document["hooks"]["PreToolUse"][0]["hooks"].insert(
        0, {"type": "command", "command": COMMAND, "timeout": 3}
    )
    return check_wiring(
        _config(tmp_path), hooks_config_path=_write(tmp_path, "twice.json", document)
    )


def _two_term_wins_over_three_term(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path, pre_evidence=_evidence(tmp_path)),
        hooks_config_path=_hooks(tmp_path, "precedence.json", 3),
    )


def _three_term_pass(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path, pre_evidence=_evidence(tmp_path)),
        hooks_config_path=_hooks(tmp_path, "three.json", 120),
    )


def _three_term_default_limit_pass(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path, pre_evidence=_evidence(tmp_path)),
        hooks_config_path=_hooks(tmp_path, "three-default.json", present=False),
    )


def _three_term_disabled_pass(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path, pre_evidence=_evidence(tmp_path, enabled=False)),
        hooks_config_path=_hooks(tmp_path, "disabled.json", 30),
    )


def _two_term_over_budget(tmp_path: Path) -> str:
    return check_wiring(_config(tmp_path), hooks_config_path=_hooks(tmp_path, "tight.json", 3))


def _two_term_timeout_zero(tmp_path: Path) -> str:
    return check_wiring(_config(tmp_path), hooks_config_path=_hooks(tmp_path, "zero.json", 0))


def _three_term_over_budget(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path, pre_evidence=_evidence(tmp_path)),
        hooks_config_path=_hooks(tmp_path, "three-tight.json", 60),
    )


def _three_term_default_limit_over_budget(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path, pre_evidence=_evidence(tmp_path, timeout_ms=600000)),
        hooks_config_path=_hooks(tmp_path, "three-default-tight.json", present=False),
    )


def _three_term_disabled_over_budget(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path, pre_evidence=_evidence(tmp_path, enabled=False)),
        hooks_config_path=_hooks(tmp_path, "disabled-tight.json", 3),
    )


def _two_term_timeout_expression(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path), hooks_config_path=_hooks(tmp_path, "expression.json", "30s")
    )


def _two_term_timeout_absent(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path), hooks_config_path=_hooks(tmp_path, "absent.json", present=False)
    )


def _three_term_expression_over_budget(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path, pre_evidence=_evidence(tmp_path, timeout_ms=600000)),
        hooks_config_path=_hooks(tmp_path, "expression-tight.json", "30s"),
    )


def _missing_hooks_file(tmp_path: Path) -> str:
    return check_wiring(_config(tmp_path), hooks_config_path=tmp_path / MISSING_NAME)


def _unparseable_hooks_file(tmp_path: Path) -> str:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8", newline="")
    return check_wiring(_config(tmp_path), hooks_config_path=path)


def _unrelated_command(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path),
        hooks_config_path=_hooks(tmp_path, "other.json", 30, command="python -m other"),
    )


def _no_commands(tmp_path: Path) -> str:
    return check_wiring(_config(tmp_path), hooks_config_path=_write(tmp_path, "none.json", {}))


def _hooks_section_not_mapping(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path), hooks_config_path=_write(tmp_path, "hooks-list.json", {"hooks": []})
    )


def _groups_not_list(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path),
        hooks_config_path=_write(tmp_path, "groups-str.json", {"hooks": {"PreToolUse": "x"}}),
    )


def _entries_not_mapping(tmp_path: Path) -> str:
    return check_wiring(
        _config(tmp_path),
        hooks_config_path=_write(
            tmp_path, "entries-int.json", {"hooks": {"PreToolUse": [{"hooks": [1, None, "x"]}]}}
        ),
    )


def _no_path(tmp_path: Path) -> str:
    return check_wiring(_config(tmp_path))


def _no_path_allowed(tmp_path: Path) -> str:
    return check_wiring(_config(tmp_path), allow_unverified_wiring=True)


INVOKE = {
    "two_term_pass": _two_term_pass,
    "two_term_boundary_equal": _two_term_boundary_equal,
    "two_term_float_above_boundary": _two_term_float_above_boundary,
    "two_term_float_below_boundary": _two_term_float_below_boundary,
    "two_term_last_numeric_wins": _two_term_last_numeric_wins,
    "two_term_wins_over_three_term": _two_term_wins_over_three_term,
    "three_term_pass": _three_term_pass,
    "three_term_default_limit_pass": _three_term_default_limit_pass,
    "three_term_disabled_pass": _three_term_disabled_pass,
    "two_term_over_budget": _two_term_over_budget,
    "two_term_timeout_zero": _two_term_timeout_zero,
    "three_term_over_budget": _three_term_over_budget,
    "three_term_default_limit_over_budget": _three_term_default_limit_over_budget,
    "three_term_disabled_over_budget": _three_term_disabled_over_budget,
    "two_term_timeout_expression": _two_term_timeout_expression,
    "two_term_timeout_absent": _two_term_timeout_absent,
    "three_term_expression_over_budget": _three_term_expression_over_budget,
    "missing_hooks_file": _missing_hooks_file,
    "unparseable_hooks_file": _unparseable_hooks_file,
    "unrelated_command": _unrelated_command,
    "no_commands": _no_commands,
    "hooks_section_not_mapping": _hooks_section_not_mapping,
    "groups_not_list": _groups_not_list,
    "entries_not_mapping": _entries_not_mapping,
    "no_path": _no_path,
    "no_path_allowed": _no_path_allowed,
}


# --------------------------------------------------------------------------- 用例


def test_every_case_has_exactly_one_call_site() -> None:
    """表与调用点必须一一对应：只有表没有调用点 = 一条永远不会跑的"证据"。"""

    assert set(INVOKE) == {case.case_id for case in CASES}


def test_the_table_covers_the_five_required_forms() -> None:
    """五种必须覆盖的形态（2026-10-03 裁定①）：少一种这张表就不再是等价性证据。"""

    covered = {case.form for case in CASES}
    missing = [form for form in REQUIRED_FORMS if form not in covered]
    assert missing == [], f"等价性用例没有覆盖这些形态：{missing}"


@pytest.mark.parametrize("case", CASES, ids=[case.case_id for case in CASES])
def test_check_wiring_returns_the_frozen_string(case: Case, tmp_path: Path) -> None:
    """抽取前后都必须逐字节等于表里的字面量（27 号 §6 硬约束 B）。"""

    assert INVOKE[case.case_id](tmp_path) == case.expected


# --------------------------------------------------------------------------- 结构化读数


TERM_KEYS = {"status", "sum_ms", "limit_ms", "limit_source", "reason"}


def test_two_term_reading_without_a_declaration(tmp_path: Path) -> None:
    """没有 pre_evidence 时：两段成立、三段**不适用**（不是 0、也不是通过）。"""

    facts = budget_inequality_facts(
        _config(tmp_path), hooks_config_path=_hooks(tmp_path, "ok.json", 30)
    )

    assert set(facts) == {"wiring", "two_term", "three_term"}
    assert set(facts["two_term"]) == TERM_KEYS
    assert facts["wiring"]["status"] == "available"
    assert facts["two_term"] == {
        "status": "ok",
        "sum_ms": 5000,
        "limit_ms": 30000,
        "limit_source": "hooks.json",
        "reason": "",
    }
    assert facts["three_term"]["status"] == "not_applicable"
    assert facts["three_term"]["sum_ms"] is None
    assert facts["three_term"]["limit_ms"] is None
    assert facts["three_term"]["limit_source"] is None
    assert facts["three_term"]["reason"]


def test_the_violated_reason_is_exactly_what_check_wiring_returns(tmp_path: Path) -> None:
    """一份实现、两个调用点：报告里的 reason 就是接线自检返回的那句话。"""

    path = _hooks(tmp_path, "tight.json", 3)
    facts = budget_inequality_facts(_config(tmp_path), hooks_config_path=path)

    assert facts["two_term"]["status"] == "violated"
    assert facts["two_term"]["sum_ms"] == 5000
    assert facts["two_term"]["limit_ms"] == 3000
    assert facts["two_term"]["limit_source"] == "hooks.json"
    assert facts["two_term"]["reason"] == check_wiring(_config(tmp_path), hooks_config_path=path)


def test_the_three_term_reading_names_the_default_limit_source(tmp_path: Path) -> None:
    """timeout 不是数字时：两段读作 unavailable，三段按 dsh 默认值继续判（不对称是刻意的）。"""

    config = _config(tmp_path, pre_evidence=_evidence(tmp_path, timeout_ms=600000))
    path = _hooks(tmp_path, "no-timeout.json", present=False)
    facts = budget_inequality_facts(config, hooks_config_path=path)

    assert facts["two_term"]["status"] == "unavailable"
    assert facts["two_term"]["reason"]
    assert facts["three_term"]["status"] == "violated"
    assert facts["three_term"]["sum_ms"] == 605000
    assert facts["three_term"]["limit_ms"] == 600000
    assert facts["three_term"]["limit_source"] == "dsh_default"
    assert facts["three_term"]["reason"] == check_wiring(config, hooks_config_path=path)
    assert "按 dsh 默认 600000ms 计" in facts["three_term"]["reason"]


def test_unreadable_wiring_makes_both_terms_unavailable(tmp_path: Path) -> None:
    """接线读不到：两格同时 unavailable，reason 就是接线自检那句话。"""

    missing = tmp_path / MISSING_NAME
    facts = budget_inequality_facts(_config(tmp_path), hooks_config_path=missing)

    assert facts["wiring"]["status"] == "unavailable"
    assert facts["two_term"]["status"] == "unavailable"
    assert facts["three_term"]["status"] == "unavailable"
    assert facts["wiring"]["reason"] == check_wiring(_config(tmp_path), hooks_config_path=missing)


def test_a_non_integral_limit_is_not_rounded(tmp_path: Path) -> None:
    """非整毫秒的读数不许被舍入：5000.5ms 就是 5000.5（舍入会造出不存在的上限）。"""

    facts = budget_inequality_facts(
        _config(tmp_path), hooks_config_path=_hooks(tmp_path, "float.json", 5.0005)
    )

    assert facts["two_term"]["status"] == "ok"
    assert facts["two_term"]["limit_ms"] == 5000.5


def test_the_status_closed_set_is_reachable(tmp_path: Path) -> None:
    """闭集要能自证：四个状态都得有一条真实读数——闭集里不许有走不到的值。"""

    readings = [
        budget_inequality_facts(
            _config(tmp_path), hooks_config_path=_hooks(tmp_path, "c1.json", 30)
        ),
        budget_inequality_facts(
            _config(tmp_path, pre_evidence=_evidence(tmp_path)),
            hooks_config_path=_hooks(tmp_path, "c2.json", 120),
        ),
        budget_inequality_facts(
            _config(tmp_path), hooks_config_path=_hooks(tmp_path, "c3.json", 3)
        ),
        budget_inequality_facts(
            _config(tmp_path), hooks_config_path=_hooks(tmp_path, "c4.json", "30s")
        ),
        budget_inequality_facts(_config(tmp_path), hooks_config_path=tmp_path / MISSING_NAME),
    ]

    seen = {reading[key]["status"] for reading in readings for key in ("two_term", "three_term")}
    assert seen == set(BUDGET_STATUSES)
    assert {reading["wiring"]["status"] for reading in readings} == {"available", "unavailable"}

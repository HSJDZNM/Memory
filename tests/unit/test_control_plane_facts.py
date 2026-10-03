"""控制面事实表 × 跨源互证（tools/control_plane_facts.py）的回归。

口径（27 号 §3 / §6）：
- **只报告**：退出码恒 0，四格红条件 enforced=false + would_exit_code=1（预注册，不是承诺）；
- **连接键双向必查**：方向一（登记了事实却没有任何检查覆盖它）与方向二（声明覆盖了一个不存在的
  事实）各自都要有**影子表**上的变异自证（AGENTS 第 45 条：自己的仪器也要能失败）；
- **跨文件契约**（硬约束 C）：默认输出的 HITS: 行必须能被**真的**
  ci_local.report_only_reading() 读出——读取器一个字都不改，本工具才算"接得上"；
- **R8**：同一棵树两次运行，剥掉归属读数后逐字节相同（剥离项见
  test_two_runs_on_the_same_tree_are_byte_identical）。

**为什么不断言 101 / 100 这些数**：那是"这一棵树今天的读数"，会随仓库内容变（本提交就把它从
202 个文件带到 203 个）。把存量读数写成断言等于给门禁加了一条新的阻断条件，与"不新增阻断步骤"
冲突。这里只钉**判据与形状**：能红、能区分、能读出、两次相同——以及 C1 / C3 真的用了那两份既有实现。
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "control_plane_facts.py"
FACTS_PATH = REPO_ROOT / "validation" / "control-plane-facts.yaml"
CHECKS_PATH = REPO_ROOT / "validation" / "instrument-checks.yaml"
EXAMPLE_CONFIG = REPO_ROOT / "examples" / "dsh" / "dsh-adapter.yaml"
EXAMPLE_HOOKS = REPO_ROOT / "examples" / "dsh" / "hooks.json"

VOLATILE_LEAVES = (
    ("reading_context", "run", "id"),
    ("reading_context", "run", "started_at"),
    ("reading_context", "tree", "digest"),
    ("reading_context", "tree", "revision"),
)
RED_KEYS = (
    "fact_without_check",
    "check_covers_unknown_fact",
    "test_path_declaration",
    "budget_inequality",
)
CHECK_ROW = {
    "check_id": "report-only:Control plane facts (report only)",
    "owner": "control-plane",
    "command": "python tools/control_plane_facts.py",
    "covers": "控制面事实表 × 跨源互证（连接键双向必查 + C1/C2/C3 读数；只报告）",
    "evidence_level": "report",
    "mutation_id": None,
    "gap_note": "存量检查，未做变异自证",
    "severity": "advisory",
}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_TOOL_CACHE: list = []


def _load_tool():
    """按路径加载本工具（只加载一次：每次 exec 都要重跑一遍 import 链，测试会慢十几秒）。"""

    if not _TOOL_CACHE:
        _TOOL_CACHE.append(_load(TOOL_PATH, "control_plane_facts_under_test"))
    return _TOOL_CACHE[0]


def _load_ci_local():
    return _load(REPO_ROOT / "tools" / "ci_local.py", "ci_local_for_control_plane_facts")


def _facts_document() -> dict:
    return yaml.safe_load(FACTS_PATH.read_text(encoding="utf-8"))


def _shadow_facts(tmp_root: Path, document: dict, *, name: str = "facts.yaml") -> Path:
    path = tmp_root / name
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _shadow_checks(tmp_root: Path, document: dict, *, name: str = "checks.yaml") -> Path:
    path = tmp_root / name
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _linking_checks(tmp_root: Path, keys: list, *, name: str = "checks.yaml") -> Path:
    """一份**只有一行**的登记表：那一行引用给定的 facts key（模拟 CI 线那次提交之后的形态）。"""

    row = {**CHECK_ROW, "covers_facts": list(keys)}
    return _shadow_checks(tmp_root, {"schema_version": "2", "checks": [row]}, name=name)


def _payload(module, capsys, *arguments: str) -> dict:
    """走 CLI 拿载荷（只在需要**文本输出**或退出码时用：每次都是一次完整进程）。"""

    assert module.run(["--json", *arguments]) == 0, "只报告：退出码必须恒为 0（用法错误除外）"
    return json.loads(capsys.readouterr().out)


def _evaluate(module, *, facts: Path = FACTS_PATH, checks: Path = CHECKS_PATH) -> dict:
    """进程内取载荷（判据同一条路径；少了进程启动，测试不至于为了形状付十几秒）。"""

    return module.evaluate(facts_path=facts, checks_path=checks)


@pytest.fixture(scope="module")
def default_payload() -> dict:
    """默认载荷（同一棵树、只算一次）：形状 / 连接键 / C1 / C3 几条用例共用它。"""

    return _evaluate(_load_tool())


# --------------------------------------------------------------------------- 只报告


def test_the_payload_carries_its_own_axis_and_never_blocks(default_payload):
    payload = default_payload

    assert payload["schema_version"] == "1.0"
    assert payload["mode"] == "report-only"
    assert sorted(payload) == [
        "checks_table",
        "cross_source",
        "facts",
        "headline",
        "links",
        "mode",
        "note",
        "reading_context",
        "red_conditions",
        "schema_version",
    ]
    for key in RED_KEYS:
        cell = payload["red_conditions"][key]
        assert cell["enforced"] is False
        assert cell["would_exit_code"] == 1
        assert cell["promote_when"]
        assert isinstance(cell["is_red"], bool)
    # 归属读数：两份声明都在（第 48 条：没写清是哪一套声明才是缺陷）
    declarations = payload["reading_context"]["declarations"]
    assert sorted(declarations) == ["control_plane_facts", "instrument_checks"]


def test_the_default_output_carries_a_hits_line_the_gate_can_read(tmp_root, capsys):
    """跨文件契约（硬约束 C）：真的读取器读真的默认输出，读取器一个字都不用改。"""

    module = _load_tool()
    ci_local = _load_ci_local()
    step = ci_local.ReportOnlyStep(
        name="Control plane facts (report only)",
        args=("tools/control_plane_facts.py",),
        reason="回归用例：跨侧读数契约（这一步还没有登记进 ci_local，见交接清单）",
        expires_at="2026-12-31",
        adopted="2026-10-03",
        reads="默认输出里的 HITS: 行",
    )
    assert "--json" not in step.args, "这一步的读数判据是文本行，不是载荷"

    assert module.run([]) == 0
    count, text = ci_local.report_only_reading(step, capsys.readouterr().out)
    assert text.startswith("HITS:"), text
    assert isinstance(count, int) and count >= 0, text
    assert "facts=" in text and "checks=" in text

    # 两张表都读不到 -> 那一行写 unavailable，读取器照原文给出读数、**不猜**命中数
    assert (
        module.run(
            ["--facts", str(tmp_root / "missing.yaml"), "--checks", str(tmp_root / "missing.yaml")]
        )
        == 0
    )
    count, text = ci_local.report_only_reading(step, capsys.readouterr().out)
    assert text.startswith("HITS: unavailable"), text
    assert count is None, text


def test_the_cells_have_the_same_shape_as_the_instrument_self_proof(default_payload):
    """红条件的形状是跨工具词汇：与 R-h 的那一格**逐字同形**（复用词汇，不新造一套"红"）。"""

    isp = _load(REPO_ROOT / "tools" / "instrument_self_proof.py", "isp_for_cell_shape")
    payload = default_payload
    # 直接比**造格子的那个函数**（不跑一遍 R-h：那要建影子索引、逐条判补丁，与本条无关）
    reference = isp._cell(  # noqa: SLF001 - 这条用例要证明的就是"两处同形"
        status="available", count=0, items=[], red_when="x", note="y"
    )
    for key in RED_KEYS:
        assert set(payload["red_conditions"][key]) == set(reference), key


# --------------------------------------------------------------------------- 连接键


def test_the_link_key_is_checked_in_both_directions(tmp_root, capsys):
    """双向必查的影子表变异自证：两格都能从 0 变 1，撤回后都回 0。"""

    module = _load_tool()
    document = _facts_document()
    keys = [row["key"] for row in document["facts"]]
    facts = _shadow_facts(tmp_root, document)
    checks = _linking_checks(tmp_root, keys)

    base = _evaluate(module, facts=facts, checks=checks)
    assert base["links"]["fact_without_check"]["count"] == 0
    assert base["links"]["check_covers_unknown_fact"]["count"] == 0
    assert base["links"]["checks_without_fact_link"] == 0

    # 方向一：facts 一行不少，只把检查行的引用收掉一个 -> 那一行没有任何检查覆盖它
    trimmed = _linking_checks(tmp_root, keys[:-1], name="checks-trimmed.yaml")
    one = _evaluate(module, facts=facts, checks=trimmed)
    assert one["links"]["fact_without_check"]["count"] == 1
    assert one["links"]["fact_without_check"]["items"][0]["key"] == keys[-1]
    assert one["red_conditions"]["fact_without_check"]["is_red"] is True
    assert one["links"]["check_covers_unknown_fact"]["count"] == 0

    # 方向二：引用一个 facts 表里不存在的 key
    broken = _linking_checks(
        tmp_root, [*keys, "test_paths.does_not_exist"], name="checks-broken.yaml"
    )
    two = _evaluate(module, facts=facts, checks=broken)
    assert two["links"]["check_covers_unknown_fact"]["count"] == 1
    unknown = two["links"]["check_covers_unknown_fact"]["items"][0]["key"]
    assert unknown == "test_paths.does_not_exist"
    assert two["links"]["fact_without_check"]["count"] == 0

    # 撤回 -> 两格都回 0（"能红"与"能收回来"是两件事，都要证明）
    back = _evaluate(module, facts=facts, checks=checks)
    assert back["links"]["fact_without_check"]["count"] == 0
    assert back["links"]["check_covers_unknown_fact"]["count"] == 0


def test_a_real_checks_table_has_rows_without_the_link_today(default_payload):
    """真表今天的读数：**没有**任何行声明 covers_facts（那是 CI 线那次提交才带来的）。

    这一格的 13 / 65 是读数，不是缺陷——写成断言是为了让"接进 ci_local 之后它该变成 0"
    这件事有一个可复核的起点。
    """

    checks = _load(REPO_ROOT / "tools" / "instrument_self_proof.py", "isp_for_today")
    table = checks.load_checks(CHECKS_PATH)
    assert all(row.covers_facts == () for row in table.rows)

    payload = default_payload
    assert payload["checks_table"]["counts"]["with_covers_facts"] == 0
    assert payload["checks_table"]["counts"]["without_covers_facts"] == len(table.rows)
    assert payload["links"]["checks_without_fact_link"] == len(table.rows)


# --------------------------------------------------------------------------- facts 表加载


def test_a_broken_facts_table_degrades_without_blocking(tmp_root, capsys):
    """不新增任何加载期 FATAL（27 号 §5 第 2 条）：表坏了就 unavailable + reason，退出码仍是 0。"""

    module = _load_tool()
    document = _facts_document()

    unknown_version = copy.deepcopy(document)
    unknown_version["schema_version"] = "2"
    payload = _evaluate(module, facts=_shadow_facts(tmp_root, unknown_version, name="v.yaml"))
    assert payload["facts"]["table"]["status"] == "unavailable"
    assert "schema_version" in payload["facts"]["table"]["reason"]
    assert payload["red_conditions"]["fact_without_check"]["count"] is None

    pointer_only = copy.deepcopy(document)
    pointer_only["facts"][0]["status"] = "passed"
    payload = _evaluate(module, facts=_shadow_facts(tmp_root, pointer_only, name="p.yaml"))
    assert payload["facts"]["table"]["status"] == "unavailable"
    assert "只放指针" in payload["facts"]["table"]["reason"]

    duplicated = copy.deepcopy(document)
    duplicated["facts"][1]["key"] = duplicated["facts"][0]["key"]
    payload = _evaluate(module, facts=_shadow_facts(tmp_root, duplicated, name="d.yaml"))
    assert payload["facts"]["table"]["status"] == "unavailable"
    assert "重复" in payload["facts"]["table"]["reason"]


def test_observed_rows_must_name_the_observer(tmp_root):
    """authority=observed 必须在 canonical_ref 里写清"谁观测"（27 号 §3.1）。"""

    module = _load_tool()
    document = _facts_document()
    document["facts"][0]["authority"] = "observed"
    document["facts"][0]["canonical_ref"] = "validation/test-layout.yaml#/test_patterns"
    with pytest.raises(module.FactsTableError) as info:
        module.load_facts(_shadow_facts(tmp_root, document))
    assert "谁观测" in str(info.value)

    document["facts"][0]["canonical_ref"] = "某次真机读数@2026-10-03/phase-2-sandbox-result.json"
    table = module.load_facts(_shadow_facts(tmp_root, document, name="ok.yaml"))
    assert table.rows[0].authority == "observed"


# --------------------------------------------------------------------------- C1 / C3 复用既有实现


def test_c1_uses_the_two_existing_implementations(default_payload):
    """C1 不新写谓词：载荷里的判定就是两侧**现在**的实现算出来的。"""

    payload = default_payload
    test_paths = payload["cross_source"]["test_paths"]
    assert test_paths["status"] == "available"
    assert test_paths["scanned"] >= 50, "没扫到测试文件：这条读数会变成空转"
    assert test_paths["disagreement_count"] == (
        test_paths["directions"]["platform_false_adapter_true"]
        + test_paths["directions"]["platform_true_adapter_false"]
    )

    witness = "tests/fixtures/validators/project/src/shop/order_controller.py"
    entry = next(
        item for item in test_paths["layer_disagreement"]["items"] if item["path"] == witness
    )
    assert entry["adapter"] == "test", "Adapter 侧按 tests/**/*.py 判测试层"
    assert entry["platform"] == "controller", "平台侧按文件名猜成入口层——正是 M1 那条缺陷"


def test_c2_marks_the_orchestrator_relation_unavailable(default_payload):
    """裁定④：orchestrator 的 tool_name 本轮**查实**——查不到就写 unavailable，不给判据。"""

    resolution = default_payload["cross_source"]["tool_tables"]["orchestrator_resolution"]

    assert resolution["status"] == "unavailable"
    assert "查不到" in resolution["reason"]
    assert set(resolution["readers"]) == set(resolution["searched_literals"])
    assert all(paths == [] for paths in resolution["readers"].values())
    # 四行注册表条目本身读得到——unavailable 说的是"对应关系证不出来"，不是"条目不存在"
    assert [item["id"] for item in resolution["registry_entries"]] == [
        "orc.fs.edit",
        "orc.fs.write",
        "orc.policy.write",
        "orc.policy.edit",
    ]


def test_the_c2_search_excludes_declarations_and_its_own_source():
    """搜索器不能自证循环：声明处与自己的源码不算读取点，真读取点要搜得到。"""

    module = _load_tool()

    hits = module._readers_of(  # noqa: SLF001 - 这条用例要证明的就是搜索器本身的行为
        REPO_ROOT, ["orc.fs.edit"]
    )["orc.fs.edit"]

    assert "registry/tool-registry.yaml" not in hits, "声明不是读取点"
    assert "tools/control_plane_facts.py" not in hits, "搜索词来自本工具，不算有人读它"
    assert any(path.endswith("src/orchestration/nodes.py") for path in hits), hits


def test_c3_reuses_the_single_budget_implementation(default_payload):
    """C3 一份实现、两个调用点：载荷里的两段 / 三段就是 budget_inequality_facts 的读数。"""

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from adapters.dsh.adapter import load_config
    from adapters.dsh.hooks import budget_inequality_facts

    payload = default_payload
    instance = payload["cross_source"]["budget"]["instances"][0]
    facts = budget_inequality_facts(
        load_config(EXAMPLE_CONFIG), hooks_config_path=EXAMPLE_HOOKS
    )
    assert instance["instance"].endswith("examples/dsh/hooks.json")
    assert instance["two_term"] == facts["two_term"]
    assert instance["three_term"] == facts["three_term"]
    # 三段今天不适用（示例没声明 pre_evidence）：**不是 0，也不是通过**
    assert instance["three_term"]["status"] == "not_applicable"
    # wiring 的 timeout_budget 与它**并列**存在（看不到 pre_evidence 的那一份）
    assert "inventory_fact" in payload["cross_source"]["budget"]


def test_an_instance_must_be_written_as_config_at_hooks():
    module = _load_tool()
    assert module.parse_instance("a.yaml@b.json") == (Path("a.yaml"), Path("b.json"))
    with pytest.raises(argparse.ArgumentTypeError):
        module.parse_instance("no-at-sign")
    with pytest.raises(argparse.ArgumentTypeError):
        module.parse_instance("@b.json")
    with pytest.raises(argparse.ArgumentTypeError):
        module.parse_instance("a.yaml@")


# --------------------------------------------------------------------------- R8


def _strip(document: dict) -> dict:
    for path in VOLATILE_LEAVES:
        cursor = document
        for key in path[:-1]:
            cursor = cursor[key]
        cursor.pop(path[-1], None)
    return document


def test_two_runs_on_the_same_tree_are_byte_identical():
    """R8：剥掉归属读数（4 个叶子，写在这里）之后，两次运行逐字节相同。"""

    module = _load_tool()
    first = _strip(json.loads(json.dumps(_evaluate(module))))
    second = _strip(json.loads(json.dumps(_evaluate(module))))
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )
    assert first["headline"]["machine_line"] == second["headline"]["machine_line"]

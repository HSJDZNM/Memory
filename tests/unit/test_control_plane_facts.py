"""控制面事实表 × 跨源互证（tools/control_plane_facts.py）的回归。

口径（27 号 §3 / §6）：
- **只报告**：退出码恒 0，四格红条件 enforced=false + would_exit_code=1（预注册，不是承诺）；
- **连接键双向必查**：方向一（登记了事实却没有任何检查覆盖它）与方向二（声明覆盖了一个不存在的
  事实）各自都要有**影子表**上的变异自证（AGENTS 第 45 条：自己的仪器也要能失败）；
- **跨文件契约**（硬约束 C）：默认输出的 HITS: 行必须能被**真的**
  ci_local.report_only_reading() 读出——读取器一个字都不改，本工具才算"接得上"；
- **R8**：同一棵树两次运行，剥掉归属读数后逐字节相同（剥离项见
  test_two_runs_on_the_same_tree_are_byte_identical）；
- **C4 通道覆盖账（阶段 A1）**：覆盖表（validation/channel-coverage.yaml）可加载、引用完整性
  独立于四个红键、**删一行变异必红**、不给 --audit 是 not_applicable 不是 0、注册表摘要漂移
  可红——判据与数据分工见文件头与 tools/control_plane_facts.py 的模块 docstring。

**为什么不断言 101 / 100 这些数**：那是"这一棵树今天的读数"，会随仓库内容变（本提交就把它从
202 个文件带到 203 个）。把存量读数写成断言等于给门禁加了一条新的阻断条件，与"不新增阻断步骤"
冲突。这里只钉**判据与形状**：能红、能区分、能读出、两次相同——以及 C1 / C3 真的用了那两份既有实现。
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "control_plane_facts.py"
FACTS_PATH = REPO_ROOT / "validation" / "control-plane-facts.yaml"
CHECKS_PATH = REPO_ROOT / "validation" / "instrument-checks.yaml"
COVERAGE_PATH = REPO_ROOT / "validation" / "channel-coverage.yaml"
WIRING_SCOPE_PATH = REPO_ROOT / "adapters" / "wiring-scope.yaml"
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
COVERAGE_RED_KEYS = (
    "row_without_mode",
    "mode_without_check",
    "tool_with_hits_without_row",
    "registry_digest_drift",
)
CONTROL_PLANE_FACTS_CHECK_ID = "report-only:Control plane facts (report only)"
# 2026-10-18 真实审计读数里的四个工具：governed=true 的 PreToolUse 命中过它们。
# 覆盖表必须给它们每一条都留行（用例用**夹具审计**复现，不依赖外部 Governance 目录）。
AUDIT_TOOLS = ("edit", "write", "run_code", "pwsh")
CHECK_ROW = {
    "check_id": "report-only:Control plane facts (report only)",
    "owner": "control-plane",
    "command": "python tools/control_plane_facts.py",
    "covers": "控制面事实表 × 跨源互证（连接键双向必查 + C1/C2/C3 读数 + 通道覆盖表；只报告）",
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

    # 版本轴：1.0 -> 1.1 是阶段 A1 的 C4 覆盖账（加键就是改协议，AGENTS 第 55 条）。
    assert payload["schema_version"] == "1.1"
    assert payload["mode"] == "report-only"
    assert sorted(payload) == [
        "checks_table",
        "coverage",
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
    # C4 的四格是**另立的块**（与顶层四格并列，不混用）；形状与上面同形。
    assert set(payload["coverage"]["red_conditions"]) == set(COVERAGE_RED_KEYS)
    for key in COVERAGE_RED_KEYS:
        cell = payload["coverage"]["red_conditions"][key]
        assert cell["enforced"] is False
        assert cell["would_exit_code"] == 1
        assert cell["promote_when"]
        assert isinstance(cell["is_red"], bool)
    # 归属读数：三份声明都在（第 48 条：没写清是哪一套声明才是缺陷）。
    # 第三份 channel_coverage 是阶段 A1 的 C4 输入（复核建议 5）：覆盖表自己的路径与摘要。
    declarations = payload["reading_context"]["declarations"]
    assert sorted(declarations) == [
        "channel_coverage",
        "control_plane_facts",
        "instrument_checks",
    ]
    assert declarations["channel_coverage"]["status"] == "available"
    assert declarations["channel_coverage"]["path"] == "validation/channel-coverage.yaml"
    assert declarations["channel_coverage"]["digest"].startswith("sha256:")


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


def test_the_link_counts_agree_with_the_real_checks_table(default_payload):
    """真表上的连接计数是不变式，不是快照：载荷里的三个数必须与真表逐行数出来的一致。

    不写死"有几行带 covers_facts"：那是登记表的内容，随登记变化；这里钉的是
    "载荷如实反映登记表"这件事本身。另外钉住一条：本工具自己作为只报告步骤登记的那一行
    （CI 线接线时同提交加的）必须存在、并且声明了 covers_facts——它是 facts 表那 14 个 key
    今天唯一的覆盖来源，丢了它 fact_without_check 会悄悄回到 13。
    """

    checks = _load(REPO_ROOT / "tools" / "instrument_self_proof.py", "isp_for_real_table")
    table = checks.load_checks(CHECKS_PATH)
    linked = sum(1 for row in table.rows if row.covers_facts)
    unlinked = len(table.rows) - linked

    payload = default_payload
    assert payload["checks_table"]["counts"]["with_covers_facts"] == linked
    assert payload["checks_table"]["counts"]["without_covers_facts"] == unlinked
    assert payload["links"]["checks_without_fact_link"] == unlinked

    own = [row for row in table.rows if row.check_id == CONTROL_PLANE_FACTS_CHECK_ID]
    assert len(own) == 1, "登记表里没有（或重复登记了）本工具的只报告步骤那一行"
    assert own[0].covers_facts, "本工具的登记行没有声明 covers_facts"


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


def test_c2_human_line_is_derived_from_the_computed_resolution():
    """人类输出那行的括注必须来自算出来的 reason，不能是与状态相反的一句硬编码。"""

    module = _load_tool()
    available = {
        "orchestrator_resolution": {
            "status": "available",
            "reason": "这些字面量在 src/orchestration/nodes.py 里被读到——对应关系可评",
        }
    }
    unavailable = {
        "orchestrator_resolution": {"status": "unavailable", "reason": "查不到：没有读取点"}
    }

    line = module._orchestrator_relation_line(available)  # noqa: SLF001 - 这就是被测接缝

    assert line == (
        "  C2 orchestrator 关系: available"
        "（这些字面量在 src/orchestration/nodes.py 里被读到——对应关系可评）"
    )
    assert "没有读取点" not in line, "状态说读到了、括注不能说没读到"
    assert module._orchestrator_relation_line(unavailable).endswith("查不到：没有读取点）")


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

def test_non_utf8_facts_table_is_a_declared_error(tmp_root: Path) -> None:
    """非 UTF-8 的 facts 表：走 FactsTableError（声明式错误通道），不许裸抛 UnicodeDecodeError。"""

    module = _load_tool()
    path = tmp_root / "facts.yaml"
    path.write_bytes(b"schema_version: 2\nfacts:\n  - key: \xff\xfe\n")

    with pytest.raises(module.FactsTableError) as error:
        module.load_facts(path)

    assert "不是 UTF-8" in str(error.value)


def test_non_utf8_registry_falls_back_to_unavailable(tmp_root: Path) -> None:
    """非 UTF-8 的工具表：C2 落"读不出来"这一档，不是栈回溯。"""

    module = _load_tool()
    registry = tmp_root / "registry"
    registry.mkdir(parents=True)
    (registry / "tool-registry.yaml").write_bytes(b"tools:\n  - id: \xff\xfe\n")

    result = module.cross_source_tool_tables(tmp_root)

    assert result["status"] == module.STATUS_UNAVAILABLE
    assert "UnicodeDecodeError" in result["reason"], result

def test_unavailable_cells_do_not_print_as_ok(tmp_root, capsys):
    """未评的格子人类输出里必须是 [未评]：不许印成 "[ok] <key>: unavailable"。"""

    module = _load_tool()
    missing = tmp_root / "missing-facts.yaml"

    assert module.run(["--json", "--facts", str(missing)]) == 0, "只报告：退出码恒 0"
    payload = json.loads(capsys.readouterr().out)
    assert module.run(["--facts", str(missing)]) == 0
    out = capsys.readouterr().out

    unavailable = 0
    for key in RED_KEYS:
        cell = payload["red_conditions"][key]
        if cell["status"] != "available":
            unavailable += 1
            assert "[未评] " + key + ": unavailable" in out, out
            assert "[ok] " + key not in out, "未评的格子被印成了 ok：" + key
        else:
            assert "[未评] " + key not in out, "已评的格子不该印 [未评]：" + key
    assert unavailable, "这条用例的前提：facts 表读不到时至少有一格未评"

def test_deleting_a_row_makes_tool_with_hits_without_row_red(tmp_root):
    """**删掉某工具的最后一行（或唯一一行）必红**（A1 的完成判据；AGENTS 第 45 条）。

    精确表述（复核更正，2026-10-18）：本格判据是**工具级**——审计里 governed=true 的
    PreToolUse 命中某个工具，而表里**没有任何一行**覆盖它。因此：
    - 删掉某工具的**最后一行**（影子表里把每个工具压成一行时就是「删一行」）→ 红；
    - 真实表里每个工具按治理阶段登记了多行（edit 有 policy / pre_evidence / enforcement
      三行，run_code 两行），**删单个阶段行不改变工具级红格**——这是本格已知的表达力边界，
      不是通过了。真实表上的等价变异是「删掉某工具的全部行」（见下一条用例）。
    """

    module = _load_tool()
    audit = _write_audit(tmp_root, AUDIT_TOOLS)
    document = _coverage_document()
    first_by_tool: dict = {}
    for row in document["rows"]:
        first_by_tool.setdefault(row["tool"], row)
    minimal = copy.deepcopy(document)
    minimal["rows"] = [copy.deepcopy(first_by_tool[tool]) for tool in AUDIT_TOOLS]

    base_path = _shadow_coverage(tmp_root, minimal, name="minimal.yaml")
    base = _evaluate_coverage(module, coverage=base_path, audit=audit)
    assert base["coverage"]["red_conditions"]["tool_with_hits_without_row"]["count"] == 0

    deleted = copy.deepcopy(minimal)
    deleted["rows"] = [row for row in deleted["rows"] if row["tool"] != "pwsh"]
    mutant = _evaluate_coverage(
        module,
        coverage=_shadow_coverage(tmp_root, deleted, name="deleted.yaml"),
        audit=audit,
    )
    cell = mutant["coverage"]["red_conditions"]["tool_with_hits_without_row"]
    assert cell["status"] == "available"
    assert cell["count"] == 1
    assert cell["is_red"] is True
    assert cell["items"][0]["tool"] == "pwsh"
    assert cell["items"][0]["governed_pre_tool_use"] == 1

    # 撤回变异 -> 回 0（"能红"与"能收回来"是两件事）。
    back = _evaluate_coverage(module, coverage=base_path, audit=audit)
    assert back["coverage"]["red_conditions"]["tool_with_hits_without_row"]["count"] == 0


def test_deleting_all_rows_of_one_tool_on_the_real_table_turns_the_cell_red(tmp_root):
    """真实表上的等价变异：删掉 run_code 的**全部**行 → tool_with_hits_without_row 红 1。

    复核指出「删一行变异必红」按字面在真实表上不成立（每工具 ≥2 行）；判据本身钉死为
    工具级（05 §3.4），所以真实表上的可证伪变异是「删掉某个工具的全部行」。本用例直接
    复制**真实**表、只动 run_code 的行，删除前 0、删除后 1、撤回后 0。
    """

    module = _load_tool()
    audit = _write_audit(tmp_root, AUDIT_TOOLS)
    document = _coverage_document()
    run_code_rows = [row for row in document["rows"] if row["tool"] == "run_code"]
    assert len(run_code_rows) >= 2, "真实表里 run_code 按治理阶段有多行（本用例的前提）"

    base_path = _shadow_coverage(tmp_root, document, name="real-base.yaml")
    base = _evaluate_coverage(module, coverage=base_path, audit=audit)
    assert base["coverage"]["red_conditions"]["tool_with_hits_without_row"]["count"] == 0

    deleted = copy.deepcopy(document)
    deleted["rows"] = [row for row in deleted["rows"] if row["tool"] != "run_code"]
    mutant = _evaluate_coverage(
        module,
        coverage=_shadow_coverage(tmp_root, deleted, name="real-deleted.yaml"),
        audit=audit,
    )
    cell = mutant["coverage"]["red_conditions"]["tool_with_hits_without_row"]
    assert cell["status"] == "available"
    assert cell["count"] == 1
    assert cell["is_red"] is True
    assert cell["items"][0]["tool"] == "run_code"

    back = _evaluate_coverage(module, coverage=base_path, audit=audit)
    assert back["coverage"]["red_conditions"]["tool_with_hits_without_row"]["count"] == 0


def test_without_audit_the_hit_check_is_not_applicable_not_zero(default_payload):
    """不给 --audit = 不适用（count 是 null，**不是 0**）；机器行照这个口径写。"""

    cell = default_payload["coverage"]["red_conditions"]["tool_with_hits_without_row"]
    assert cell["status"] == "not_applicable"
    assert cell["count"] is None
    assert cell["is_red"] is False
    assert "不是 0" in cell["reason"]
    machine = default_payload["headline"]["machine_line"]
    assert "tool_with_hits_without_row=not_applicable" in machine
    assert "audit=not_applicable" in machine


def test_unreadable_audit_is_unavailable_not_zero(tmp_root):
    module = _load_tool()
    payload = _evaluate_coverage(module, audit=tmp_root / "missing-audit.jsonl")

    cell = payload["coverage"]["red_conditions"]["tool_with_hits_without_row"]
    assert cell["status"] == "unavailable"
    assert cell["count"] is None
    assert "审计读不出来" in cell["reason"]
    assert payload["coverage"]["audit"]["status"] == "unavailable"


def test_a_truncated_tail_line_does_not_hide_governed_hits(tmp_root):
    """正在追加的末行（没有换行、解析不了）不算不可解析行，也不据此声称「没有漏」。"""

    module = _load_tool()
    path = tmp_root / "audit.jsonl"
    good = json.dumps({"governed": True, "hook_event": "PreToolUse", "tool": "edit"})
    path.write_text(good + "\n" + '{"governed": true, "hook_event": "PreTo', encoding="utf-8")
    payload = _evaluate_coverage(module, audit=path)

    audit = payload["coverage"]["audit"]
    assert audit["status"] == "available"
    assert audit["governed_pre_tool_use"] == 1
    assert audit["tail_in_progress"] is True


def test_a_truncated_tail_is_disclosed_in_the_hit_cell(tmp_root):
    """末行截断必须在上的可评单元格里披露「可能少命中」（复核建议 6，不许静默）。"""

    module = _load_tool()
    path = tmp_root / "audit-tail-cell.jsonl"
    good = json.dumps({"governed": True, "hook_event": "PreToolUse", "tool": "bash"})
    path.write_text(good + "\n" + '{"governed": true, "hook_event": "PreTo', encoding="utf-8")
    payload = _evaluate_coverage(module, audit=path)

    cell = payload["coverage"]["red_conditions"]["tool_with_hits_without_row"]
    assert cell["status"] == "available"
    assert cell["count"] == 1, "bash 在 TOOL_TABLE 里，但覆盖表没有它的行"
    assert cell["items"][0]["tool"] == "bash"
    assert "tail_in_progress" in cell["note"]
    assert "可能少命中" in cell["note"]


def test_registry_digest_drift_is_red_when_the_approved_digest_differs(monkeypatch):
    """注册表摘要漂移：monkeypatch 掉加载 API 的返回值（真实哈希规则不重写）。"""

    module = _load_tool()

    class _Registry:
        version = 7
        identity = "sha256:" + "0" * 64

        def registry_drift_reason(self):
            return ""

    class _Loaded:
        registry = _Registry()
        approved_document = {
            "approved_schema_version": "1.1",
            "registry_digest": "sha256:" + "1" * 64,
            "governance_digest": "sha256:" + "2" * 64,
            "reviewed_by": "tester",
            "approved_at": "2026-10-18T00:00:00Z",
        }

    monkeypatch.setattr(module, "load_registry", lambda *args, **kwargs: _Loaded())
    payload = module.evaluate()

    cell = payload["coverage"]["red_conditions"]["registry_digest_drift"]
    assert cell["status"] == "available"
    assert cell["count"] == 1
    assert cell["is_red"] is True
    item = cell["items"][0]
    assert item["current_digest"] != item["approved_digest"]
    assert "重新审核" in item["remedy"]


def test_reference_breaks_are_a_separate_reading_not_a_red_key(tmp_root):
    """引用断开数另立 references 块：**不许**混进四个红键冒充覆盖缺口。"""

    module = _load_tool()
    rows = [
        {
            "channel": "no-such-channel",
            "tool": "edit",
            "mode": "policy",
            "coverage": "enforced",
            "check_id": CONTROL_PLANE_FACTS_CHECK_ID,
            "owner": "platform",
            "reason": "夹具：channel 引用断开",
            "expires_at": None,
        },
        {
            "channel": "governed-session-hook",
            "tool": "no-such-tool",
            "mode": "policy",
            "coverage": "enforced",
            "check_id": CONTROL_PLANE_FACTS_CHECK_ID,
            "owner": "platform",
            "reason": "夹具：tool 引用断开",
            "expires_at": None,
        },
        {
            "channel": "governed-session-hook",
            "tool": "write",
            "mode": "enforcement",
            "coverage": "enforced",
            "check_id": "probe:does-not-exist",
            "owner": "platform",
            "reason": "夹具：check_id 引用断开",
            "expires_at": None,
        },
        {
            "channel": "governed-session-hook",
            "tool": "read",
            "mode": "policy",
            "coverage": "declared_uncovered",
            "check_id": None,
            "owner": "platform",
            "reason": "夹具：covers_facts 引用断开",
            "expires_at": "2026-12-31",
            "covers_facts": ["no.such.fact"],
        },
    ]
    broken = {"schema_version": "1", "rows": rows}
    payload = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, broken, name="broken-refs.yaml")
    )

    references = payload["coverage"]["references"]
    assert references["channel"]["count"] == 1
    assert references["tool"]["count"] == 1
    assert references["check_id"]["count"] == 1
    assert references["covers_facts"]["count"] == 1
    assert references["total"] == 4
    assert references["is_red"] is True
    # 四个红键的键集合**没有**被引用读数扩出一个位：两者是不同的读数。
    assert set(payload["coverage"]["red_conditions"]) == set(COVERAGE_RED_KEYS)
    # 引用断开不影响红键自己的判据：check_id 断开那条同时进 mode_without_check（它的定义如此）。
    assert payload["coverage"]["red_conditions"]["mode_without_check"]["count"] == 1


def test_the_machine_lines_carry_the_c4_counts(default_payload):
    module = _load_tool()
    machine = default_payload["headline"]["machine_line"]
    hits = module.hits_line(default_payload)

    for key in COVERAGE_RED_KEYS:
        assert key + "=" in machine, machine
        assert key + "=" in hits, hits
    assert "coverage_rows=" + str(default_payload["coverage"]["table"]["rows"]) in machine
    assert "references=" in machine and "audit=" in machine
    # HITS 的合计**仍是既有四格之和**（跨文件契约的既有含义不变）：行首仍是整数。
    assert re.match(r"^HITS: \d+ / ", hits), hits
    assert "checks=" in hits and hits.rstrip().endswith(
        "checks=" + str(default_payload["checks_table"]["table"]["rows"])
    )


def test_the_cli_prints_the_c4_cells_and_keeps_exit_zero(capsys):
    module = _load_tool()
    assert module.run([]) == 0
    out = capsys.readouterr().out

    assert "C4 覆盖表:" in out
    assert "CONTROL_PLANE_FACTS: " in out
    for key in COVERAGE_RED_KEYS:
        assert key in out
    assert "[不适用] tool_with_hits_without_row: not_applicable" in out


def test_the_c4_axis_is_registered_and_pinned():
    """版本轴：载荷 1.1、覆盖表 "1"（AGENTS 第 55 条：加键就是改协议）。"""

    module = _load_tool()
    assert module.CONTROL_PLANE_FACTS_SCHEMA_VERSION == "1.1"
    assert module.CHANNEL_COVERAGE_SCHEMA_VERSION == "1"
    table = module.load_coverage(COVERAGE_PATH)
    assert table.schema_version == "1"


# --------------------------------------------------------------------------- C4 通道覆盖账（阶段 A1）


def _coverage_document() -> dict:
    return yaml.safe_load(COVERAGE_PATH.read_text(encoding="utf-8"))


def _shadow_coverage(tmp_root: Path, document: dict, *, name: str = "coverage.yaml") -> Path:
    path = tmp_root / name
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_audit(tmp_root: Path, tools, *, name: str = "audit.jsonl") -> Path:
    """夹具审计：只放 governed=true 的 PreToolUse 记录（与真实 JSONL 同一形态）。"""

    records = [
        json.dumps({"governed": True, "hook_event": "PreToolUse", "tool": tool})
        for tool in tools
    ]
    path = tmp_root / name
    path.write_text("\n".join(records) + "\n", encoding="utf-8", newline="\n")
    return path


def _evaluate_coverage(module, *, coverage: Path = COVERAGE_PATH, audit=None) -> dict:
    kwargs = {"coverage_path": Path(coverage)}
    if audit is not None:
        kwargs["audit_path"] = Path(audit)
    return module.evaluate(**kwargs)


def test_a_valid_coverage_table_has_all_four_cells_green(tmp_root):
    """合法表可加载且四红 0（审计用**夹具**注入：不依赖外部 Governance 目录）。"""

    module = _load_tool()
    audit = _write_audit(tmp_root, AUDIT_TOOLS)
    payload = _evaluate_coverage(module, audit=audit)

    table = payload["coverage"]["table"]
    assert table["status"] == "available"
    assert table["schema_version"] == module.CHANNEL_COVERAGE_SCHEMA_VERSION == "1"
    assert table["rows"] == len(_coverage_document()["rows"])
    for key in COVERAGE_RED_KEYS:
        cell = payload["coverage"]["red_conditions"][key]
        assert cell["status"] == "available", (key, cell)
        assert cell["count"] == 0, (key, cell)
        assert cell["is_red"] is False, (key, cell)
    assert payload["coverage"]["references"]["total"] == 0
    assert payload["coverage"]["references"]["is_red"] is False
    assert payload["coverage"]["audit"]["status"] == "available"
    assert payload["coverage"]["audit"]["governed_pre_tool_use"] == len(AUDIT_TOOLS)
    assert sorted(payload["coverage"]["audit"]["by_tool"]) == sorted(AUDIT_TOOLS)


def test_real_rows_cover_the_tools_with_governed_hits():
    """数据验收（A1 的完成口径）：审计里出现过的每个工具，真实覆盖表都有行。

    另外钉住两条**已知洞**不许被写成已覆盖：run_code 必须有显式 declared_uncovered
    （代码/命令里的文件写入不受 path_scope 约束）、desktop-entry-points 四行都必须是
    declared_uncovered + 到期日（接线与留痕都成立，但账本里没有可归因到本通道、覆盖当前
    会话的受治理判定——见 validation/channel-coverage.yaml 的文件头与 04 号 5.72）。
    """

    module = _load_tool()
    document = _coverage_document()
    row_tools = {row["tool"] for row in document["rows"]}
    assert set(AUDIT_TOOLS) <= row_tools, row_tools

    holes = [
        row
        for row in document["rows"]
        if row["tool"] == "run_code" and row["coverage"] == "declared_uncovered"
    ]
    assert holes, "run_code 必须有一行 declared_uncovered（别把 allow_delegated 读成已覆盖）"
    assert "path_scope" in holes[0]["reason"]

    desktop = [row for row in document["rows"] if row["channel"] == "desktop-entry-points"]
    assert {row["tool"] for row in desktop} == {"edit", "write", "run_code", "pwsh"}
    assert all(row["coverage"] == "declared_uncovered" for row in desktop)
    assert all(row["expires_at"] for row in desktop)

    for row in document["rows"]:
        assert row["mode"] in module.COVERAGE_MODES, row
        assert row["channel"] and row["tool"] and row["owner"] and row["reason"], row
        if row["coverage"] == "enforced":
            assert row["check_id"] == CONTROL_PLANE_FACTS_CHECK_ID, row
        else:
            assert row["check_id"] is None, row


def test_a_malformed_coverage_table_degrades_without_blocking(tmp_root, capsys):
    """结构坏 -> 该节 unavailable + reason（不抛异常、退出码仍是 0）。"""

    module = _load_tool()
    document = _coverage_document()

    pointer_only = copy.deepcopy(document)
    pointer_only["rows"][0]["status"] = "passed"
    payload = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, pointer_only, name="pointer.yaml")
    )
    assert payload["coverage"]["table"]["status"] == "unavailable"
    assert "只放指针" in payload["coverage"]["table"]["reason"]
    # 三格依赖覆盖表本身 → 未评；registry_digest_drift **独立于覆盖表结构**（复核建议 4）：
    # 它读的是 registry/ 下两份文件，覆盖表坏了照样算得出来（这里真实注册表是匹配的）。
    for key in (
        "row_without_mode",
        "mode_without_check",
        "tool_with_hits_without_row",
    ):
        assert payload["coverage"]["red_conditions"][key]["count"] is None
    digest = payload["coverage"]["red_conditions"]["registry_digest_drift"]
    assert digest["status"] == "available"
    assert digest["count"] == 0
    assert payload["coverage"]["references"]["total"] is None
    # 只报告：结构坏不掉退出码（用法错误除外）。
    assert module.run(["--json", "--coverage", str(tmp_root / "pointer.yaml")]) == 0
    capsys.readouterr()

    no_expiry = copy.deepcopy(document)
    hole = next(row for row in no_expiry["rows"] if row["coverage"] == "declared_uncovered")
    hole["expires_at"] = None
    payload = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, no_expiry, name="expiry.yaml")
    )
    assert payload["coverage"]["table"]["status"] == "unavailable"
    assert "expires_at" in payload["coverage"]["table"]["reason"]

    unknown_version = copy.deepcopy(document)
    unknown_version["schema_version"] = "2"
    payload = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, unknown_version, name="version.yaml")
    )
    assert payload["coverage"]["table"]["status"] == "unavailable"
    assert "schema_version" in payload["coverage"]["table"]["reason"]




def test_a_bad_coverage_value_degrades_without_traceback(tmp_root, capsys):
    """坏枚举（coverage: "enforced-ish"）只降级，不许 traceback + exit 1（复核必须修 1）。

    回归点：_coverage_row 曾经用 _enum/_text（抛 FactsTableError），而 evaluate 只 catch
    CoverageTableError ⇒ 坏输入会逃出只报告工具。现在两条输入都走 CoverageTableError。
    """

    module = _load_tool()
    document = _coverage_document()
    document["rows"][0]["coverage"] = "enforced-ish"
    path = _shadow_coverage(tmp_root, document, name="bad-coverage.yaml")

    assert module.run(["--json", "--coverage", str(path)]) == 0, "只报告：坏输入也只降级"
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    payload = json.loads(captured.out)
    assert payload["coverage"]["table"]["status"] == "unavailable"
    assert "coverage" in payload["coverage"]["table"]["reason"]
    # 机器行仍可读：覆盖表行数写 unavailable，不是崩掉
    assert "coverage_rows=unavailable" in payload["headline"]["machine_line"]


def test_an_empty_owner_degrades_without_traceback(tmp_root, capsys):
    """坏值（owner: "" / 不在闭集）同样只降级：该节 unavailable + 进程 exit 0。"""

    module = _load_tool()
    document = _coverage_document()
    document["rows"][0]["owner"] = ""
    path = _shadow_coverage(tmp_root, document, name="bad-owner.yaml")

    assert module.run(["--json", "--coverage", str(path)]) == 0
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    payload = json.loads(captured.out)
    assert payload["coverage"]["table"]["status"] == "unavailable"
    assert "owner" in payload["coverage"]["table"]["reason"]
    assert "coverage_rows=unavailable" in payload["headline"]["machine_line"]


def _absolute_path_leaks(value, *, trail: str = "") -> list:
    """递归找出载荷里任何带盘符绝对路径 / /Users/ 的字符串（复核必须修 2 的回归判据）。"""

    leaks: list = []
    if isinstance(value, str):
        if "C:\\" in value or "C:/" in value or "/Users/" in value:
            leaks.append((trail, value))
    elif isinstance(value, dict):
        for key, item in value.items():
            leaks.extend(_absolute_path_leaks(item, trail=trail + "." + str(key)))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            leaks.extend(_absolute_path_leaks(item, trail=trail + "[" + str(index) + "]"))
    return leaks


def test_absolute_paths_never_reach_the_payload(tmp_root, capsys):
    """三种错误注入下，--json 全文不得出现盘符路径（C:\\ 或 C:/）与 /Users/。

    复核必须修 2：旧实现把 str(error) 直接塞进 reason——FileNotFoundError / RegistryError /
    WiringScopeError 的原文都带绝对路径。现在统一走 reading.fold_absolute_paths；--audit 的
    路径只以 <outside-workspace>/audit.jsonl 出现。
    """

    module = _load_tool()
    # 用**盘符根 / 文件系统根**构造一条工作区之外、确定不存在的审计路径：
    # pytest 的 tempdir 会被 conftest 指到工作区内（.tmp/tmp），拿它测"外部路径"不成立。
    outside_audit = Path(REPO_ROOT.anchor) / "dsh-a1-nonexistent" / "audit.jsonl"
    assert not outside_audit.exists(), "这条用例的前提：审计确实不存在"

    # ① 审计不存在（工作区之外的绝对路径）
    assert module.run(["--json", "--audit", str(outside_audit)]) == 0
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    payload = json.loads(captured.out)
    assert payload["coverage"]["audit"]["status"] == "unavailable"
    assert payload["coverage"]["audit"]["path"] == "<outside-workspace>/audit.jsonl"
    assert _absolute_path_leaks(payload) == []

    # ② 注册表不可读 + ③ wiring-scope 损坏：都放进同一棵临时树里
    repo = tmp_root / "corrupt-repo"
    (repo / "registry").mkdir(parents=True, exist_ok=True)
    (repo / "adapters").mkdir(parents=True, exist_ok=True)
    (repo / "registry" / "tool-registry.yaml").write_text("{not yaml", encoding="utf-8")
    (repo / "adapters" / "wiring-scope.yaml").write_text("not-a-mapping\n", encoding="utf-8")
    broken = module.evaluate(repo=repo, audit_path=outside_audit)
    assert broken["coverage"]["registry_digest"]["status"] == "unavailable"
    assert broken["coverage"]["references"]["channel"]["status"] == "unavailable"
    assert _absolute_path_leaks(broken) == []


def test_coverage_row_field_semantics_are_checked_at_load_time(tmp_root):
    """文件头自述、加载器也要做：owner 闭集 + expires_at 与 coverage 的配套关系（建议 7）。"""

    module = _load_tool()
    document = _coverage_document()

    bad_owner = copy.deepcopy(document)
    bad_owner["rows"][0]["owner"] = "nobody"
    payload = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, bad_owner, name="owner.yaml")
    )
    assert payload["coverage"]["table"]["status"] == "unavailable"
    assert "platform / host" in payload["coverage"]["table"]["reason"]

    enforced_expiry = copy.deepcopy(document)
    enforced_row = next(row for row in enforced_expiry["rows"] if row["coverage"] == "enforced")
    enforced_row["expires_at"] = "2026-12-31"
    payload = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, enforced_expiry, name="enforced-expiry.yaml")
    )
    assert payload["coverage"]["table"]["status"] == "unavailable"
    assert "expires_at" in payload["coverage"]["table"]["reason"]

    # not_applicable 同理：合法形态（null）加载，加到期日就自相矛盾
    not_applicable = copy.deepcopy(document)
    not_applicable["rows"] = [
        {
            "channel": "governed-session-hook",
            "tool": "read",
            "mode": "policy",
            "coverage": "not_applicable",
            "check_id": None,
            "owner": "platform",
            "reason": "夹具：只读工具按设计不在覆盖账里",
            "expires_at": None,
        }
    ]
    ok = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, not_applicable, name="na-ok.yaml")
    )
    assert ok["coverage"]["table"]["status"] == "available"
    not_applicable["rows"][0]["expires_at"] = "2026-12-31"
    payload = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, not_applicable, name="na-expiry.yaml")
    )
    assert payload["coverage"]["table"]["status"] == "unavailable"
    assert "expires_at" in payload["coverage"]["table"]["reason"]


def test_a_missing_mode_is_red_row_without_mode(tmp_root):
    """缺 mode -> row_without_mode 红（**语义坏是红计数**，不是结构错误）。"""

    module = _load_tool()
    document = _coverage_document()
    enforced = next(row for row in document["rows"] if row["coverage"] == "enforced")
    enforced.pop("mode")

    payload = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, document, name="no-mode.yaml")
    )
    assert payload["coverage"]["table"]["status"] == "available", "缺 mode 不许把整节打成不可用"
    cell = payload["coverage"]["red_conditions"]["row_without_mode"]
    assert cell["status"] == "available"
    assert cell["count"] == 1
    assert cell["is_red"] is True
    assert cell["items"][0]["channel"] == enforced["channel"]
    assert cell["items"][0]["tool"] == enforced["tool"]


def test_an_enforced_row_without_check_id_is_red_mode_without_check(tmp_root):
    module = _load_tool()
    document = _coverage_document()
    enforced = next(row for row in document["rows"] if row["coverage"] == "enforced")
    enforced["check_id"] = None

    payload = _evaluate_coverage(
        module, coverage=_shadow_coverage(tmp_root, document, name="no-check.yaml")
    )
    cell = payload["coverage"]["red_conditions"]["mode_without_check"]
    assert cell["status"] == "available"
    assert cell["count"] == 1
    assert cell["is_red"] is True
    assert cell["items"][0]["channel"] == enforced["channel"]
    assert cell["items"][0]["tool"] == enforced["tool"]

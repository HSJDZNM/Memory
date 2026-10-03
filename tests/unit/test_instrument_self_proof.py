"""仪器自证（tools/instrument_self_proof.py）的回归：三态各一条、两条反退化各一条。

口径（25 号 §2 / 23 号 §19）：三态判据（① 没有身份 ② 没有自证也没有缺口说明
③ 变异打不上）都要**能红**，而"未评不是不红"与"对象清单要有第二来源"这两条反退化
各自也要有一条用例——"跑了、是绿的"不算覆盖（AGENTS 第 45 条）。

**为什么全部用影子表**：本工具只报告、不接退出码。真表的读数（64/64、四格 0）由
`tools/instrument_self_proof.py` 自己报，并写进 23 号 §19 的读数；把"真表现在必须完整"写成
pytest 断言，等于给门禁加一条新的阻断条件（CI 线加一个 workflow 步骤就会红），
与"不新增阻断步骤"冲突。所以这里**只**钉判据本身：喂进去什么样的表，就该出现什么样的红。

第 6 条（加载器只放指针）是**指令之外多出来的一条**：方案 §3.2 要求登记表只放指针
（出现 last_run / status / passed / observed_* 即加载期报错），这条规则要是没有用例，
它就是一个没有自证的机制。理由写在 23 号 §19 的"超出一条"里。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "instrument_self_proof.py"
CHECKS_PATH = REPO_ROOT / "validation" / "instrument-checks.yaml"

# 两个合成补丁（态③ 的"打得上 / 打不上"）：都不写进树，只放进 tmp_root。
GOOD_PATCH = """diff --git a/.tmp/r-h-probe-new-file.txt b/.tmp/r-h-probe-new-file.txt
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/.tmp/r-h-probe-new-file.txt
@@ -0,0 +1 @@
+probe
"""

BAD_PATCH = """diff --git a/validation/instrument-checks.yaml b/validation/instrument-checks.yaml
--- a/validation/instrument-checks.yaml
+++ b/validation/instrument-checks.yaml
@@ -1,1 +1,1 @@
-MISSING-LINE-THAT-NEVER-EXISTS
+something else
"""


def _load():
    spec = importlib.util.spec_from_file_location(
        "instrument_self_proof_under_test", TOOL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # 标准配方：exec 之前登记
    spec.loader.exec_module(module)
    return module


def _rows() -> list:
    document = yaml.safe_load(CHECKS_PATH.read_text(encoding="utf-8"))
    # 台阶 5：covers_facts（可选）把登记表带到 "2"，加载器同时接受 "1"（27 号 §3.2）。
    assert document["schema_version"] == "2"
    return document["checks"]


def _shadow(tmp_root: Path, rows: list, *, version: str = "2") -> Path:
    path = tmp_root / "instrument-checks.yaml"
    path.write_text(
        yaml.safe_dump(
            {"schema_version": version, "checks": rows}, allow_unicode=True, sort_keys=False
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _evaluate(tmp_root: Path, rows: list, capsys, *, mutations: Path | None = None) -> dict:
    module = _load()
    arguments = ["--json", "--checks", str(_shadow(tmp_root, rows))]
    if mutations is not None:
        arguments += ["--mutations", str(mutations)]
    assert module.run(arguments) == 0, "只报告：退出码必须恒为 0（用法错误除外）"
    return json.loads(capsys.readouterr().out)


def _evaluate_path(tmp_root: Path, checks: Path, capsys) -> dict:
    module = _load()
    assert module.run(["--json", "--checks", str(checks)]) == 0
    return json.loads(capsys.readouterr().out)


# --- 态① 没有身份：对象在清单里、登记表里没有它的 check_id -------------------------------


def test_state_one_an_object_without_a_check_id_is_red(tmp_root, capsys):
    rows = _rows()
    kept = rows[0]
    payload = _evaluate(tmp_root, [kept], capsys)

    cell = payload["red_conditions"]["no_check_id"]
    assert cell["status"] == "available"
    assert cell["count"] == payload["objects"]["discovered"] - 1, "其余对象必须一条不少地被报红"
    assert cell["is_red"] is True
    assert cell["enforced"] is False and cell["would_exit_code"] == 1, "只报告期：这一格不接退出码"
    # 逐条明细要能读出"缺的是哪一个对象"（check_id 为 null 的那一行）
    undecided = [row for row in payload["checks"] if row["state"] == "no_check_id"]
    assert len(undecided) == cell["count"]
    assert all(row["check_id"] is None for row in undecided)
    assert kept["check_id"] not in {row["object_id"] for row in undecided}
    # 留下来的那一条是匹配上的：另一半（悬空）必须是 0
    assert payload["red_conditions"]["check_id_without_object"]["count"] == 0


# --- 态② 既没有 mutation_id、又没有非空白 gap_note ---------------------------------------


def test_state_two_a_row_with_neither_mutation_nor_gap_note_is_red(tmp_root, capsys):
    rows = _rows()
    target = rows[0]["check_id"]

    baseline = _evaluate(tmp_root, rows, capsys)
    assert baseline["red_conditions"]["no_mutation_and_no_gap_note"]["count"] == 0

    mutated = copy.deepcopy(rows)
    mutated[0]["mutation_id"] = None
    mutated[0]["gap_note"] = "   "  # 空白串按**缺失**处理（AGENTS 第 50 条口径）
    payload = _evaluate(tmp_root, mutated, capsys)
    cell = payload["red_conditions"]["no_mutation_and_no_gap_note"]
    assert cell["status"] == "available"
    assert cell["count"] == 1
    assert [item["check_id"] for item in cell["items"]] == [target]
    assert cell["is_red"] is True and cell["enforced"] is False

    # 撤回变异 → 变回 0：这条规则自己也有"修复前会红"的证明（25 号 §2 的硬约束）
    restored = _evaluate(tmp_root, rows, capsys)
    assert restored["red_conditions"]["no_mutation_and_no_gap_note"]["count"] == 0


# --- 态③ 按 mutation_id 取的补丁在影子树上打不上 ----------------------------------------


def _mutation_root(tmp_root: Path, patch_text: str) -> Path:
    root = tmp_root / "mutations"
    root.mkdir(exist_ok=True)
    (root / "probe-patch").write_text(patch_text, encoding="utf-8", newline="\n")
    (root / "probe-applies.yaml").write_text(
        'schema_version: "1"\nid: probe-applies\npatch: probe-patch\nnote: 回归用例的合成变异\n',
        encoding="utf-8",
        newline="\n",
    )
    return root


def test_state_three_a_declared_mutation_that_cannot_be_proven_is_red(tmp_root, capsys):
    rows = copy.deepcopy(_rows())
    rows[0]["mutation_id"] = "probe-applies"
    mutations = _mutation_root(tmp_root, GOOD_PATCH)

    # 反退化：这一格不是恒红——补丁真打得上时必须读作 0，且该行状态是"声明了变异"
    clean = _evaluate(tmp_root, rows, capsys, mutations=mutations)
    assert clean["red_conditions"]["patch_not_applicable"]["count"] == 0
    assert [
        row["state"] for row in clean["checks"] if row["check_id"] == rows[0]["check_id"]
    ] == ["mutation_declared"]

    # 补丁换成 context 对不上的那一份 → 这一格红，并且写出是哪一条变异、为什么
    mutations = _mutation_root(tmp_root, BAD_PATCH)
    broken = _evaluate(tmp_root, rows, capsys, mutations=mutations)
    cell = broken["red_conditions"]["patch_not_applicable"]
    assert cell["status"] == "available"
    assert cell["count"] == 1
    assert cell["items"][0]["mutation_id"] == "probe-applies"
    assert "打不上" in cell["items"][0]["reason"]
    assert [
        row["state"] for row in broken["checks"] if row["check_id"] == rows[0]["check_id"]
    ] == ["patch_not_applicable"]

    # 记录本身就读不到 = 一样"证明不了"（不是静默跳过，也不是当成通过）
    rows[0]["mutation_id"] = "no-such-mutation"
    missing = _evaluate(tmp_root, rows, capsys, mutations=mutations)
    cell = missing["red_conditions"]["patch_not_applicable"]
    assert cell["count"] == 1
    assert "读不到" in cell["items"][0]["reason"]


# --- 反退化① 「未评」不是「不红」 ---------------------------------------------------------


def test_unavailable_is_not_zero_and_not_red(tmp_root, capsys):
    payload = _evaluate_path(tmp_root, tmp_root / "missing.yaml", capsys)

    assert payload["objects"]["status"] == "unavailable"
    assert payload["objects"]["declared"] is None
    assert payload["checks"] == [], "表读不到时不许声称'这些对象没有 check_id'"
    for key in (
        "no_check_id",
        "no_mutation_and_no_gap_note",
        "patch_not_applicable",
        "check_id_without_object",
    ):
        cell = payload["red_conditions"][key]
        assert cell["status"] == "unavailable"
        assert cell["count"] is None, key + "：未评不许用 0 冒充"
        assert cell["items"] == []
        assert cell["is_red"] is False
        assert cell["reason"], key + "：读不到必须写清为什么"
    line = payload["headline"]["machine_line"]
    assert "unavailable" in line
    assert "=0" not in line, "未评的四格都不许在机器行里写成 0"


# --- 反退化② 对象清单要有第二来源，且双向比对 -------------------------------------------


def test_the_inventory_is_compared_both_ways(tmp_root, capsys):
    rows = _rows()

    # (a) 表里只写 1 条：其余对象必须被报成①红——"表里只写 1 条、其余谁也不提"不许静默通过
    only_one = _evaluate(tmp_root, rows[:1], capsys)
    assert only_one["red_conditions"]["no_check_id"]["count"] == (
        only_one["objects"]["discovered"] - 1
    )

    # (b) 表里多一条"谁也不是"的 check_id：必须被报成④悬空（双向比对的另一半）
    extra = copy.deepcopy(rows[:1])
    extra[0]["check_id"] = "gate-step:这条步骤不存在"
    payload = _evaluate(tmp_root, rows + extra, capsys)
    assert payload["red_conditions"]["no_check_id"]["count"] == 0
    dangling = payload["red_conditions"]["check_id_without_object"]
    assert dangling["count"] == 1
    assert dangling["items"][0]["check_id"] == "gate-step:这条步骤不存在"


# --- 加载器：只放指针（指令之外的一条，理由见本文件头） ----------------------------------


def test_the_registry_is_pointer_only_and_strict(tmp_root):
    module = _load()
    rows = _rows()

    def rejected(mutated: list, needle: str) -> None:
        path = _shadow(tmp_root, mutated)
        with pytest.raises(module.InstrumentChecksError) as info:
            module.load_checks(path)
        assert needle in str(info.value), str(info.value)

    pointer_only = copy.deepcopy(rows)
    pointer_only[0]["status"] = "passed"
    rejected(pointer_only, "只放指针")

    observed = copy.deepcopy(rows)
    observed[0]["observed_at"] = "2026-10-03T00:00:00Z"
    rejected(observed, "只放指针")

    bad_enum = copy.deepcopy(rows)
    bad_enum[0]["severity"] = "critical"
    rejected(bad_enum, "只接受")

    unknown = copy.deepcopy(rows)
    unknown[0]["note"] = "顺手加的字段"
    rejected(unknown, "未知字段")

    duplicated = copy.deepcopy(rows)
    duplicated[1]["check_id"] = duplicated[0]["check_id"]
    rejected(duplicated, "重复")

    # 坏版本必须是**真正不存在**的版本号：台阶 5 之后 "2" 是合法的，
    # 继续拿它当坏版本会让这条用例静默失效（2026-10-03 裁定②）。
    bad_version = copy.deepcopy(rows)
    path = _shadow(tmp_root, bad_version, version="3")
    with pytest.raises(module.InstrumentChecksError) as info:
        module.load_checks(path)
    assert "schema_version" in str(info.value)
    assert "'1' / '2'" in str(info.value), str(info.value)


def test_the_loader_accepts_the_older_table_version(tmp_root):
    """加的是**可选**字段，所以旧表仍然合法：兼容窗口为 0（27 号 §3.2）。"""

    module = _load()

    table = module.load_checks(_shadow(tmp_root, _rows(), version="1"))

    assert table.schema_version == "1"
    assert all(row.covers_facts == () for row in table.rows)


def test_the_link_field_is_optional_and_read_as_a_tuple(tmp_root):
    """covers_facts 省略 = 没有这条声明；写了就逐字读出来（含顺序）。"""

    module = _load()
    rows = copy.deepcopy(_rows())
    rows[0]["covers_facts"] = ["test_paths.platform_patterns", "budget.dsh_side_limit"]

    table = module.load_checks(_shadow(tmp_root, rows))

    assert table.rows[0].covers_facts == (
        "test_paths.platform_patterns",
        "budget.dsh_side_limit",
    )
    assert table.rows[1].covers_facts == ()


def test_a_malformed_link_key_is_a_load_error(tmp_root):
    """**形态**在加载期查（畸形即报错）；**存在性**不在这里查（27 号 §3.2 的分工）。"""

    module = _load()

    def rejected(value: object, needle: str) -> None:
        rows = copy.deepcopy(_rows())
        rows[0]["covers_facts"] = value
        with pytest.raises(module.InstrumentChecksError) as info:
            module.load_checks(_shadow(tmp_root, rows))
        assert needle in str(info.value), str(info.value)

    rejected("test_paths.platform_patterns", "必须是字符串列表")
    rejected(["Test_Paths.platform"], "key 形态")
    rejected(["nodots"], "key 形态")
    rejected([""], "key 形态")
    rejected([None], "key 形态")


def test_an_unknown_but_well_formed_link_key_still_loads(tmp_root):
    """写错一个字母是"连接悬空"，不是"这张表坏了"——它由读数那一格报出来。"""

    module = _load()
    rows = copy.deepcopy(_rows())
    rows[0]["covers_facts"] = ["test_paths.does_not_exist"]

    table = module.load_checks(_shadow(tmp_root, rows))

    assert table.rows[0].covers_facts == ("test_paths.does_not_exist",)

# --- 跨文件契约：默认输出的 HITS: 行（ci_local 的只报告读数按它取命中数） ------------------


def _load_ci_local():
    spec = importlib.util.spec_from_file_location(
        "ci_local_for_instrument_contract", REPO_ROOT / "tools" / "ci_local.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.__name__ = spec.name
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_default_output_carries_a_hits_line_the_gate_can_read(tmp_root, capsys):
    """跨侧契约：**真的读取器**（ci_local.report_only_reading）读真的默认输出。

    这一行是 25 号 §6 第 1 条那把钥匙：有了它，把本工具接成只报告步骤就只是往
    REPORT_ONLY_STEPS 里加一行数据，**读取器一个字都不用改**（与 exemption_expiry 同族）。
    未评时那行写 unavailable，读取器照原文给出读数、**不猜**命中数（count 是 None，不是 0）。
    """

    module = _load()
    ci_local = _load_ci_local()
    step = ci_local.ReportOnlyStep(
        name="Instrument self-proof (report only)",
        args=("tools/instrument_self_proof.py",),
        reason="回归用例：跨侧读数契约（这一步还没有登记进 ci_local，见 26 号交接清单）",
        expires_at="2026-12-31",
        adopted="2026-10-03",
        reads="默认输出里的 HITS: 行",
    )
    assert "--json" not in step.args, "这一步的读数判据是文本行，不是载荷"

    rows = _rows()
    assert module.run(["--checks", str(_shadow(tmp_root, rows))]) == 0
    count, text = ci_local.report_only_reading(step, capsys.readouterr().out)
    assert text.startswith("HITS:"), text
    assert count == 0, text
    assert "no_mutation_and_no_gap_note=0" in text

    # HITS 是**四格合计**：两条没有自证的行 → 读作 2（不是"某三格之一"）
    mutated = copy.deepcopy(rows)
    mutated[0]["gap_note"] = ""
    mutated[1]["gap_note"] = None
    assert module.run(["--checks", str(_shadow(tmp_root, mutated))]) == 0
    count, text = ci_local.report_only_reading(step, capsys.readouterr().out)
    assert count == 2, text

    # 未评：登记表读不到 → 那行写 unavailable，读取器照原文给出读数、不猜
    assert module.run(["--checks", str(tmp_root / "missing.yaml")]) == 0
    count, text = ci_local.report_only_reading(step, capsys.readouterr().out)
    assert text.startswith("HITS: unavailable"), text
    assert count is None, text

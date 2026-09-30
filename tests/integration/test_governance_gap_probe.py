"""V1 独立验收：13 项治理覆盖缺口的探针（见 tools/governance_gap_probe.py）。

它不复用实现者写的测试，只驱动公开入口（python -m adapters.dsh.hooks /
python -m enforcement.cli / python -m adapters.cli / 规范事件的装配入口 /
插件源码静态事实 / 审计 JSONL），断言"修后"应有的行为。任一项与预期不符 -> 该缺口的测试变红。

**G06 覆盖两条路径**（N13）：同一批用例（9 反例 + 2 必须放行的对照）既走 Phase 2 的
`python -m adapters.dsh.hooks`，也走 Phase 6 的规范事件（generic-json Adapter →
`to_policy_context` → `policy.engine.evaluate`）。后者在 facts 里是 `p6_*`。
缺口的由来：只驱动钩子的仪器在 N1 还活着的那棵树上照样 13/13、exit 0 ——
"跑过了、是绿的"并不等于"这条路径被覆盖了"，所以下面有专门的用例钉住这件事。

跑法：

    python -m pytest tests/integration/test_governance_gap_probe.py -q
    # 完整对照（修前 / 修后同一份探针）：
    python tools/governance_gap_probe.py --root .tmp/verifier/baseline --phase before
    python tools/governance_gap_probe.py --root . --phase after

探针工作目录固定在 .tmp/verifier/probe/（构建产物，可随时重建），但**每次运行都有唯一的
run-<run_id> 子目录**：上次运行的 audit/台账不得成为本次运行的输入（否则 event_id 会命中幂等台账，
探针会因错误原因变红或变绿）。模块 fixture 以 `--repeat 2` 跑一次（两遍、两个工作目录）：
逐项用例读第 1 遍的报告，`test_probe_is_deterministic_across_runs` 比对两遍的逐项结论与 facts。
不要在测试之外对同一个 --work 目录并发跑探针（并发只影响磁盘占用，不影响结论：目录是按 run
隔离的）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# 默认扫当前仓库；GOVERNANCE_PROBE_ROOT 可把它指向另一份快照（例如修前基线或一次预演副本），
# 用于"同一份探针 + 同一份测试"的修前/修后对照。
PROBE_ROOT = Path(os.environ.get("GOVERNANCE_PROBE_ROOT", str(REPO_ROOT))).resolve()
PROBE = REPO_ROOT / "tools" / "governance_gap_probe.py"
EXPECTED_GAPS = tuple(f"G{index:02d}" for index in range(1, 14))
# G06 的两条路径与用例表（与探针里的 _G06_CASES / _G06_CONTROLS 同名，故意写死在测试里：
# 探针改了用例而测试没跟上时，下面的断言必须变红，而不是自动跟着漂）。
G06 = "G06"
G06_PHASE2_CASES = (
    "literal_from", "plain_import", "alias_case",
    "importlib_module", "dunder_import", "relative_import", "relative_named",
    "submodule_import", "dotted_import",
)
G06_BYPASS_CASES = (
    "importlib_module", "dunder_import", "relative_import", "relative_named",
    "submodule_import", "dotted_import",
)
G06_CONTROLS = ("controller_service_allowed", "module_layer_allowed")
G06_CASE_COUNT = len(G06_PHASE2_CASES) + len(G06_CONTROLS)
# 工作目录固定在仓库自己的 .tmp/ 下：pytest 的 tmp_path 走系统临时目录，
# 在受限沙箱里会因 WinError 5 直接失败（这也是本测试不复用 tmp_path_factory 的原因）。
PROBE_WORK = REPO_ROOT / ".tmp" / "verifier" / "probe"
REPORT_PATH = REPO_ROOT / ".tmp" / "verifier" / "probe-live-after.json"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def report() -> dict:
    """对 live 仓库跑完整探针（--phase after --repeat 2），返回其 JSON 报告。

    为什么在 fixture 里就 --repeat 2：过去 fixture 跑一遍、确定性用例再用 --repeat 2 跑两遍，
    同一份探针一次会话跑 3 遍（本模块耗时的大头）。--repeat 2 的报告主体就是第 1 遍（run#0）的
    完整报告，另附 repeat / run_ids / repeat_consistent 三项，所以逐项用例读 run#0、
    确定性用例读比对结论，**两次独立运行、两个工作目录**的证明强度不变，只少跑一遍。
    代价是报告的 ok 同时要求两遍一致：不一致时退出码用例也会跟着红，结论方向不变。
    """

    if not PROBE.is_file():
        pytest.skip(f"探针脚本不存在：{PROBE.relative_to(REPO_ROOT)}")
    json_out = REPORT_PATH
    json_out.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--root", str(PROBE_ROOT), "--phase", "after",
         "--work", str(PROBE_WORK), "--repeat", "2", "--json-out", str(json_out)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=1800,
    )
    assert json_out.is_file(), (
        "探针没有写出报告；stdout/stderr 如下\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    payload["exit_code"] = completed.returncode
    payload["stdout"] = completed.stdout
    payload["stderr"] = completed.stderr
    return payload


def test_probe_declares_all_thirteen_gaps(report: dict) -> None:
    """检查数与 id 表必须与探针一致：G06 的 Phase 6 用例**折进** G06，不新增检查 id。"""

    ids = [item["id"] for item in report["checks"]]
    assert ids == list(EXPECTED_GAPS), f"探针没有覆盖全部 13 项缺口：{ids}"

# --------------------------------------------------------------- G06 的两条路径（N13）
#
# 这几条用例专门钉"G06 真的驱动了 Phase 6"，而不是复述探针自己的结论：
# 没有它们，"G06 全绿"与"G06 只驱动了钩子"在报告里长得一模一样。


def g06(report: dict) -> dict:
    item = next((row for row in report["checks"] if row["id"] == G06), None)
    assert item is not None, f"探针缺少 {G06}"
    return item


def test_g06_declares_phase6_expectations_for_every_case(report: dict) -> None:
    """修前/修后两张期望表都必须逐条写出 Phase 6 的 p6_*，否则对照是半张表。"""

    item = g06(report)
    names = (*G06_PHASE2_CASES, *G06_CONTROLS)
    missing_before = [name for name in names if f"p6_{name}" not in item["before"]]
    missing_after = [name for name in names if f"p6_{name}" not in item["after"]]
    assert not missing_before, f"{G06} 的修前期望缺少 Phase 6 用例：{missing_before}"
    assert not missing_after, f"{G06} 的修后期望缺少 Phase 6 用例：{missing_after}"
    for table in ("before", "after"):
        assert "path_disagreements" in item[table], (
            f"{G06} 的 {table} 期望没有声明两条路径的一致性（path_disagreements）"
        )


def test_g06_phase6_before_expectations_describe_the_silent_pass(report: dict) -> None:
    """修前期望必须写出 N1 的样子：换写法在 Phase 6 路径上**静默放行**。

    这是"新检查对修前快照会红"的可读形式：如果 before 表把 p6_* 写成 blocked，
    变异体上它就不会红，这台仪器也就看不见它该看见的 bug。
    """

    item = g06(report)
    for name in G06_BYPASS_CASES:
        assert item["before"][f"p6_{name}"] == "allowed", (
            f"{G06} 的修前期望把 p6_{name} 写成 {item['before'][f'p6_{name}']!r}："
            "修前多 Agent 路径对这一形态是静默放行"
        )
        assert item["after"][f"p6_{name}"] == "blocked", f"{G06} 修后必须拦住 p6_{name}"
    for name in G06_CONTROLS:
        assert item["before"][f"p6_{name}"] == "allowed"
        assert item["after"][f"p6_{name}"] == "allowed", (
            f"{G06} 的对照 {name} 在修后也必须放行：一个把所有输入都判 block 的探针是假绿"
        )


def test_g06_actually_drove_the_phase6_path(report: dict) -> None:
    """Phase 6 那一组必须真的跑出了逐条结论，且两条路径的结论一致。"""

    item = g06(report)
    facts = item["facts"]
    assert not facts.get("p6_error"), (
        f"{G06} 的 Phase 6 驱动器没有跑起来：{facts.get('p6_error')}"
    )
    assert facts.get("p6_case_count") == G06_CASE_COUNT, (
        f"{G06} 只驱动了 {facts.get('p6_case_count')} 条 Phase 6 用例，"
        f"期望 {G06_CASE_COUNT} 条：{facts}"
    )
    unnamed = [
        name
        for name in (*G06_PHASE2_CASES, *G06_CONTROLS)
        if facts.get(f"p6_{name}") not in ("allowed", "blocked")
    ]
    assert not unnamed, f"{G06} 的 Phase 6 结论缺失或非法：{unnamed}"
    assert facts.get("path_disagreements") == [], (
        f"{G06} 的两条路径结论不一致（换个入口就换结论 = N1）：{facts.get('path_disagreements')}"
    )



def test_every_gap_declares_before_and_after_expectations(report: dict) -> None:
    """每项探针必须同时表达"修前应当看到什么"与"修后应当看到什么"，否则不能当对照。"""

    for item in report["checks"]:
        assert item["before"], f"{item['id']} 没有声明修前预期"
        assert item["after"], f"{item['id']} 没有声明修后预期"
        assert item["before"] != item["after"], f"{item['id']} 的修前与修后预期完全相同"


@pytest.mark.parametrize("gap", EXPECTED_GAPS)
def test_gap_matches_after_expectations(report: dict, gap: str) -> None:
    item = next((row for row in report["checks"] if row["id"] == gap), None)
    assert item is not None, f"探针缺少 {gap}"
    assert not item["error"], f"{gap} 的探针自身异常：{item['error']}"
    assert item["ok"], (
        f"{gap} 与修后预期不符：" + "; ".join(item["mismatches"]) + "\n"
        f"实测事实：{json.dumps(item['facts'], ensure_ascii=False, sort_keys=True)}\n"
        f"证据：\n" + "\n".join(item["evidence"])
    )


def test_no_cross_run_state_residue(report: dict) -> None:
    """本次运行里不得出现任何 event_replay：它只可能来自"上一次运行的状态被复用"。"""

    assert report.get("unexpected_event_replay") == [], (
        "本次运行观察到 event_replay（= 有跨运行状态被复用）："
        f"{report.get('unexpected_event_replay')}"
    )


def test_probe_exit_code_matches_report(report: dict) -> None:
    failed = [item["id"] for item in report["checks"] if not item["ok"]]
    assert report["ok"] is (not failed)
    assert report["exit_code"] == (0 if not failed else 1), (
        f"探针退出码 {report['exit_code']} 与结论不一致（未通过：{failed}）"
    )


def test_probe_is_deterministic_across_runs(report: dict) -> None:
    """探针必须是纯函数：同一个 --root/--phase 连续跑两遍，逐项结论与 facts 必须完全一致。

    这条不是形式主义：工作目录一旦在两次运行之间复用，上一次写进 audit 的
    <session>:<tool_use_id> 会让本次运行命中幂等台账变成 event_replay——
    "我跑过了"这件事本身会改变下一次的结果，于是探针会**因为错误原因**变红或变绿。

    两遍由 fixture 的 --repeat 2 真跑（见 report() 的说明），这里只读比对结论，不再多跑一遍。
    """

    payload = report
    assert payload.get("repeat") == 2, "探针没有真的跑两遍"
    assert payload.get("repeat_consistent") is True, (
        "两次运行的结论与 facts 不一致：\n" + "\n".join(payload.get("repeat_differences", []))
    )
    assert len(set(payload.get("run_ids", []))) == 2, (
        f"两次运行用了同一个工作目录：{payload.get('run_ids')}"
    )

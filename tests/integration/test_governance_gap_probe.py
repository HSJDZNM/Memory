"""V1 独立验收：13 项治理覆盖缺口的探针（见 tools/governance_gap_probe.py）。

它不复用实现者写的测试，只驱动公开入口（python -m adapters.dsh.hooks /
python -m enforcement.cli / python -m adapters.cli / 插件源码静态事实 / 审计 JSONL），
断言"修后"应有的行为。任一项与预期不符 -> 该缺口的测试变红。

跑法：

    python -m pytest tests/integration/test_governance_gap_probe.py -q
    # 完整对照（修前 / 修后同一份探针）：
    python tools/governance_gap_probe.py --root .tmp/verifier/baseline --phase before
    python tools/governance_gap_probe.py --root . --phase after

探针工作目录固定在 .tmp/verifier/probe/（构建产物，可随时重建），但**每次运行都有唯一的
run-<run_id> 子目录**：上次运行的 audit/台账不得成为本次运行的输入（否则 event_id 会命中幂等台账，
探针会因错误原因变红或变绿）。`test_probe_is_deterministic_across_runs` 连续跑两遍并比对逐项
结论与 facts。
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
# 工作目录固定在仓库自己的 .tmp/ 下：pytest 的 tmp_path 走系统临时目录，
# 在受限沙箱里会因 WinError 5 直接失败（这也是本测试不复用 tmp_path_factory 的原因）。
PROBE_WORK = REPO_ROOT / ".tmp" / "verifier" / "probe"
REPORT_PATH = REPO_ROOT / ".tmp" / "verifier" / "probe-live-after.json"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def report() -> dict:
    """对 live 仓库跑一次完整探针（--phase after），返回其 JSON 报告。"""

    if not PROBE.is_file():
        pytest.skip(f"探针脚本不存在：{PROBE.relative_to(REPO_ROOT)}")
    json_out = REPORT_PATH
    json_out.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--root", str(PROBE_ROOT), "--phase", "after",
         "--work", str(PROBE_WORK), "--json-out", str(json_out)],
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
    ids = [item["id"] for item in report["checks"]]
    assert ids == list(EXPECTED_GAPS), f"探针没有覆盖全部 13 项缺口：{ids}"


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


def test_probe_is_deterministic_across_runs() -> None:
    """探针必须是纯函数：同一个 --root/--phase 连续跑两遍，逐项结论与 facts 必须完全一致。

    这条不是形式主义：工作目录一旦在两次运行之间复用，上一次写进 audit 的
    <session>:<tool_use_id> 会让本次运行命中幂等台账变成 event_replay——
    "我跑过了"这件事本身会改变下一次的结果，于是探针会**因为错误原因**变红或变绿。
    """

    json_out = REPORT_PATH.parent / "probe-live-after-repeat.json"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--root", str(PROBE_ROOT), "--phase", "after",
         "--work", str(PROBE_WORK), "--repeat", "2", "--json-out", str(json_out)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=1800,
    )
    assert json_out.is_file(), f"探针没有写出报告：{completed.stdout}\n{completed.stderr}"
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload.get("repeat") == 2, "探针没有真的跑两遍"
    assert payload.get("repeat_consistent") is True, (
        "两次运行的结论与 facts 不一致：\n" + "\n".join(payload.get("repeat_differences", []))
    )
    assert len(set(payload.get("run_ids", []))) == 2, (
        f"两次运行用了同一个工作目录：{payload.get('run_ids')}"
    )

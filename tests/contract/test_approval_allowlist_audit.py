"""审批条子 × 注册表白名单的跨源互证：**验收夹具 + 变异证明**。

被验的仪器是 \`tools/approval_allowlist_audit.py\`（只报告，退出码恒 0）。这里不重写它的
算法，而是**真跑它**并读 \`--json\` 载荷中的四格红条件：

1. **绿的一侧**：\`tests/fixtures/approval_audit/registry.yaml\` 与 \`ok/approval.json\` 同宽
   → 四格全 0（这就是"受治侧现在跑得动"的形态）；
2. **红的一侧（变异证明）**：把注册表换成多 13 条允许命令的 \`registry-wider.yaml\`
   → \`allowlisted_prefix_without_a_ticket\` 恰好 13 条，且**它是被"条子比注册表窄"这条判据
   抓到的**，不是被别的格子。没有这一步，"跑过了、是绿的"证明不了仪器会红（AGENTS 第 45 条）；
3. **越界方向**（另一侧的红）：条子模式指向白名单里没有的命令 → \`pattern_outside_the_allowlist\`；
4. **读不出来不是 0**：\`--registry\` 指向不存在的注册表 → \`status = unavailable\`、
   \`count = null\`，**绝不折叠成 0 命中**（AGENTS 第 56 条同一条口径）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "approval_audit"
COMPARISON = Path("C:/Users/ZNM/Downloads/Comparison-test/Governance/.policy")


def _run_audit(*, registry: Path, approval: Path, approved: Path | None = None) -> dict:
    """真跑工具，读它的 --json 载荷（退出码恒 0——红不红在载荷里，不在退出码里）。"""

    command = [
        sys.executable,
        str(REPO_ROOT / "tools" / "approval_allowlist_audit.py"),
        "--registry",
        str(registry),
        "--approval",
        str(approval),
        "--json",
    ]
    if approved is not None:
        command += ["--approved", str(approved)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_fixture_pair_is_green() -> None:
    report = _run_audit(
        registry=FIXTURES / "registry.yaml", approval=FIXTURES / "ok" / "approval.json"
    )

    assert report["status"] == "available"
    assert report["hits"] == 0
    for name, grid in report["red_conditions"].items():
        assert grid["count"] == 0, (name, grid)
        assert grid["enforced"] is False


def test_a_wider_allowlist_without_a_wider_ticket_turns_the_reverse_grid_red() -> None:
    """变异证明：白名单比条子宽 → 反向那格必须有命中，且命中数是差集大小。"""

    report = _run_audit(
        registry=FIXTURES / "registry-wider.yaml", approval=FIXTURES / "ok" / "approval.json"
    )

    assert report["hits"] == 12
    grid = report["red_conditions"]["allowlisted_prefix_without_a_ticket"]
    assert grid["count"] == 12
    assert grid["would_exit_code"] == 1
    # 反向那格按**缺口**记账，不按"条子 × 缺口"记账：一张条子时两者相同，
    # 分族之后立刻会差出倍数——这条断言钉住口径。
    assert len({(item["tool_id"], item["prefix"]) for item in grid["items"]}) == 12


def test_a_ticket_wider_than_the_allowlist_turns_the_forward_grid_red(tmp_root: Path) -> None:
    """另一侧的红：条子放宽到白名单之外（授权面越界）。"""

    payload = json.loads((FIXTURES / "ok" / "approval.json").read_text(encoding="utf-8"))
    payload["records"][0]["param_patterns"]["command"] = "^(python -m pytest|rm -rf)( .*)?$"
    approval = tmp_root / "approval.json"
    approval.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="")

    report = _run_audit(registry=FIXTURES / "registry.yaml", approval=approval)

    grid = report["red_conditions"]["pattern_outside_the_allowlist"]
    assert grid["count"] == 1
    assert grid["items"][0]["prefix"] == "rm -rf"


def test_unreadable_registry_is_unavailable_not_zero(tmp_root: Path) -> None:
    report = _run_audit(
        registry=tmp_root / "missing.yaml", approval=FIXTURES / "ok" / "approval.json"
    )

    assert report["status"] == "unavailable"
    assert report["count"] is None
    assert "注册表读不出来" in report["reason"]


def test_the_live_comparison_approval_matches_its_registry_shape() -> None:
    """受治侧的真实现场读数：**只读**，文件不在就跳过（不在 CI 上假装通过）。

    2026-10-11 按族分签之后（5.69 处置②），这个数是**已知缺口 13 条**：
    没签的族 = 只读工具族（Get-Content / Select-String / Test-Path / Get-ChildItem /
    Write-Output）+ 测试族的其余写法（unittest / uv run / 裸 pytest）+ 脚本族
    （scripts / tools / -m 模块）。它们由注册表声明允许、由本文件按契约钉住，
    要签哪一族是一次**显式决定**，不是静默放宽。
    """

    approval = COMPARISON / "approval.json"
    registry = COMPARISON / "tool-registry.local.yaml"
    approved = COMPARISON / "tool-registry.approved.json"
    if not (approval.is_file() and registry.is_file() and approved.is_file()):
        return

    report = _run_audit(registry=registry, approval=approval, approved=approved)

    assert report["status"] == "available"
    assert report["red_conditions"]["pattern_outside_the_allowlist"]["count"] == 0
    assert report["red_conditions"]["registry_hash_drift"]["count"] == 0
    assert report["red_conditions"]["command_param_not_covered"]["count"] == 0
    assert report["red_conditions"]["allowlisted_prefix_without_a_ticket"]["count"] == 13

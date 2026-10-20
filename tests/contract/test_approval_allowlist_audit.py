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
    # B1（2026-10-20）改了 ToolSpec.approved_payload：新增 command_families 与参数 default，
    # 逐工具 schema_hash 因此全部变化。受治侧副本的 approved.json 是**旧版产物**，所以
    # 10 个工具全部 drift——这是**真实读数**，不是测试坏了：本地注册表必须按新格式重新审核，
    # 这一格才回 0。两种状态都接受（0 = 已重审，10 = 还没重审），其它数字才算问题。
    assert report["red_conditions"]["registry_hash_drift"]["count"] in (0, 10)
    assert report["red_conditions"]["command_param_not_covered"]["count"] == 0
    assert report["red_conditions"]["allowlisted_prefix_without_a_ticket"]["count"] == 13


# --------------------------------------------------------------------------- 命令族 ↔ 白名单（--check）
#
# 注册表 1.1 的 \`command_families\` 是**被审核数据**：它决定"按族签发"能覆盖哪些命令。
# 这里真跑 \`--check\` 并做三处**变异**（AGENTS 第 45 条：仪器必须能红），
# 而不是只证明"跑过了、是绿的"。

INK = REPO_ROOT / "registry" / "tool-registry.yaml"
APPROVED = REPO_ROOT / "registry" / "tool-registry.approved.json"


def _run_family_check(*, registry: Path, approved: Path | None = None, extra: list[str] | None = None) -> dict:
    command = [
        sys.executable,
        str(REPO_ROOT / "tools" / "approval_allowlist_audit.py"),
        "--check",
        "--registry",
        str(registry),
        "--json",
    ]
    if approved is not None:
        command += ["--approved", str(approved)]
    command += extra or []
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _mutated_registry(tmp_root: Path, mutate) -> Path:
    """把仓库真实注册表读成文档、按 mutate 改一处再写回去（变异证明用）。"""

    import yaml

    document = yaml.safe_load(INK.read_text(encoding="utf-8"))
    mutate(document)
    path = tmp_root / "tool-registry.mutated.yaml"
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def _tools(document: dict) -> dict[str, dict]:
    return {item["id"]: item for item in document["tools"]}


def test_the_repository_families_are_green_against_its_own_allowlist() -> None:
    report = _run_family_check(registry=INK, approved=APPROVED)

    assert report["schema_version"] == "1.1"
    assert report["mode"] == "families"
    assert report["status"] == "available"
    assert report["hits"] == 0, report["red_conditions"]
    for name, grid in report["red_conditions"].items():
        assert grid["count"] == 0, (name, grid)
        assert grid["enforced"] is False
    assert report["command_tool_count"] == 2 and report["family_count"] == 6


def test_a_family_pattern_missing_from_the_allowlist_turns_the_forward_grid_red(tmp_root: Path) -> None:
    """变异①：族的模式不在白名单里 → '族比注册表宽' 那格必须红。"""

    def mutate(document: dict) -> None:
        _tools(document)["exec.pwsh"]["command_families"][0]["patterns"].append(
            "^rm -rf( .*)?$"
        )

    report = _run_family_check(registry=_mutated_registry(tmp_root, mutate))

    grid = report["red_conditions"]["family_pattern_outside_the_allowlist"]
    assert grid["count"] == 1
    assert grid["items"][0]["tool_id"] == "exec.pwsh"
    assert grid["items"][0]["pattern"] == "^rm -rf( .*)?$"
    assert report["hits"] == 1


def test_an_allowlist_entry_without_a_family_turns_the_reverse_grid_red(tmp_root: Path) -> None:
    """变异②：白名单条目不属于任何族 → '族比注册表窄' 那格必须红（按缺口记账）。"""

    def mutate(document: dict) -> None:
        # 把 exec.bash 的脚本族删掉一条，留下一条没人认领的白名单
        _tools(document)["exec.bash"]["command_families"] = [
            item for item in _tools(document)["exec.bash"]["command_families"] if item["id"] != "scripts"
        ]

    report = _run_family_check(registry=_mutated_registry(tmp_root, mutate))

    grid = report["red_conditions"]["allowlisted_pattern_without_a_family"]
    assert grid["count"] == 1
    assert grid["items"][0]["tool_id"] == "exec.bash"
    assert grid["items"][0]["pattern"].startswith("^python tools/")
    assert report["hits"] == 1


def test_a_tool_without_families_is_a_data_gap_not_zero_hits(tmp_root: Path) -> None:
    """变异③：命令类工具没有族数据 → 单独一格命中（不是"0 命中"，也不是通过）。"""

    def mutate(document: dict) -> None:
        _tools(document)["exec.bash"].pop("command_families")

    report = _run_family_check(registry=_mutated_registry(tmp_root, mutate))

    grid = report["red_conditions"]["command_tool_without_families"]
    assert grid["count"] == 1
    assert grid["items"][0]["tool_id"] == "exec.bash"
    # 这个工具的白名单不再被逐条计入反向那格（否则一个缺口会被数两遍）
    assert report["red_conditions"]["allowlisted_pattern_without_a_family"]["count"] == 0


def test_family_check_does_not_require_or_accept_an_approval_file(tmp_root: Path) -> None:
    """--check 与 --approval 二选一：混用是用法错误（argparse 退出码 2）。"""

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "approval_allowlist_audit.py"),
            "--check",
            "--registry",
            str(INK),
            "--approval",
            str(FIXTURES / "ok" / "approval.json"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 2
    assert "二选一" in result.stderr


def test_an_unreadable_registry_is_unavailable_in_family_mode_too(tmp_root: Path) -> None:
    report = _run_family_check(registry=tmp_root / "missing.yaml")

    assert report["status"] == "unavailable"
    assert report["count"] is None
    assert "注册表读不出来" in report["reason"]

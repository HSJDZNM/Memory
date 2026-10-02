"""通道清点的对外契约：CLI 退出码、JSON 形状、与运行期自检的一致性。

这组断言守的是"假安全感"：如果配置缺失或损坏时 wiring --check 仍然退出 0，
这条命令就只是在给零治理盖章（R2 / G13 / G1）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import POLICIES_DIR, REPO_ROOT, write_dsh_config

from adapters.cli import build_parser, main
from adapters.wiring import (
    DIFFERENCE_KEYS,
    FAILURE_STATUSES,
    GOVERNS_DECISIONS,
    GOVERNS_UNDECLARED,
    WIRING_SCHEMA_VERSION,
    ChannelStatus,
    FreshnessStatus,
    WiringStatus,
    probe_wiring,
    split_status,
)

pytestmark = pytest.mark.contract

POLICY_COMMAND = (
    "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml "
    "--hooks-config .policy/hooks.json --audit .policy/audit.jsonl"
)
ADAPTER_CONFIG = "project: demo\ntimeout_ms: 5000\naudit_log: .policy/audit.jsonl\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def make_home(tmp_root: Path) -> Path:
    home = tmp_root / "dsh-home"
    (home / "profiles").mkdir(parents=True, exist_ok=True)
    return home


def profile_patch(project_dir: Path, command: str = POLICY_COMMAND) -> str:
    return (
        "- insert:\n"
        "    - id: policy-hook\n"
        "      name: '<repo>/src/adapters/dsh/policy-hook.plugin.mjs'\n"
        "      config:\n"
        "        command: '" + command + "'\n"
        "        timeoutMs: 30000\n"
        "        projectDir: '" + project_dir.as_posix() + "'\n"
    )


def hooks_document(command: str = POLICY_COMMAND, timeout: float = 30) -> dict[str, Any]:
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": command, "timeout": timeout}],
                }
            ]
        }
    }


def add_profile(home: Path, name: str, patch: str, *, hooks: Any = "good") -> Path:
    profile = home / "profiles" / name
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", patch)
    if hooks is not None:
        _write(
            profile / ".policy" / "hooks.json",
            hooks if isinstance(hooks, str) else json.dumps(hooks),
        )
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-25T11:59:00Z"}) + "\n",
    )
    return profile


def wired_home_without_audit(tmp_root: Path) -> tuple[Path, Path]:
    """接线齐全、审计目标不存在：N20 的正例（接线事实在、留痕事实没有）。"""

    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", profile_patch(profile))
    _write(profile / ".policy" / "hooks.json", json.dumps(hooks_document()))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    return home, profile


def wired_home(tmp_root: Path) -> Path:
    home, profile = wired_home_without_audit(tmp_root)
    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-25T11:59:00Z"}) + "\n",
    )
    return home


# N20 的 CLI 级复现固定用 --now：留痕的新鲜度不该由跑测试那天的墙钟决定。
#
# 2026-10-03 评审裁定①：同一条纪律必须覆盖**直接调 probe_wiring** 的用例。夹具留痕写死
# `2026-09-25T11:59:00Z`，不传 now 就是拿**真实墙钟**去减它——一过 7 天窗口
# （2026-10-02T11:59:00Z）必然红，而它红的是测试夹具的记忆，不是被测代码。所以本文件里
# 每一个**读夹具留痕**的用例都把这一刻钉死：CLI 级用 `--now`，函数级用 `now=FIXED_NOW`，
# 同一个时刻两条路。唯一的例外是 `test_default_probe_never_reports_a_vacuous_pass`——
# 它刻意走**默认发现路径**（真实 `~/.dsh`，换了 now 就不是"默认"了），而它断言的只有
# "不许 vacuous pass"与通道排序，两者都与时间无关（时钟平移下同样绿，见 23 号 §18 的自证）。
FIXED_NOW_TEXT = "2026-09-25T12:00:00Z"
FIXED_NOW = datetime.fromisoformat(FIXED_NOW_TEXT.replace("Z", "+00:00"))

WIRING_ARGV: tuple[str, ...] = (
    "--root",
    str(REPO_ROOT),
    "--json",
    "wiring",
    "--now",
    FIXED_NOW_TEXT,
    "--observe-sessions",
    "0",
    "--check",
)


def run_wiring_json(home: Path, capsys: Any) -> tuple[int, dict[str, Any]]:
    code, out, _ = run_cli([*WIRING_ARGV, "--dsh-home", str(home)], capsys)
    return code, json.loads(out)


def run_cli(argv: list[str], capsys: Any) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------- CLI


def test_wiring_check_exits_zero_only_for_a_wired_channel(tmp_root: Path, capsys: Any) -> None:
    home = wired_home(tmp_root)

    code, out, _ = run_cli(
        [
            "--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home),
            "--now", FIXED_NOW_TEXT, "--check",
        ],
        capsys,
    )

    assert code == 0, out
    assert "result" not in out or "pass" in out


def test_wiring_check_exits_non_zero_and_names_the_unwired_channel(
    tmp_root: Path, capsys: Any
) -> None:
    """完成判据：对"未接线"必须退出非 0，并在输出里指名道姓说哪个通道没接。"""

    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", "[]\n")

    code, out, err = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--check"], capsys
    )

    assert code == 1
    assert "dsh:desktop" in err
    assert "not_wired" in err


def test_wiring_without_check_is_a_report_not_a_gate(tmp_root: Path, capsys: Any) -> None:
    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.patch.yml", "[]\n")

    code, out, err = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home)], capsys
    )

    assert code == 0
    assert "not_wired" in out
    assert "fail" in err


def test_unreadable_configuration_never_passes(tmp_root: Path, capsys: Any) -> None:
    """配置"读不到"必须是显式失败态：这条断言就是"读不到不等于通过"。"""

    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    # 有 profile 目录、没有 patch 层：dsh 会照常启动且不报错。
    _write(profile / "cordis.yml", "[]\n")

    code, out, err = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--check", "--json"],
        capsys,
    )

    assert code == 1
    payload = json.loads(out)
    channel = payload["channels"][0]
    assert channel["status"] == ChannelStatus.HOOKS_CONFIG_MISSING.value
    assert channel["wired"] is False
    assert payload["result"] == "fail"


def test_unprovable_budget_fails_the_check(tmp_root: Path, capsys: Any) -> None:
    """预算事实读不到 -> --check 非 0。

    "读不到"不等于"不等式成立"：读不到就证明不了，按失败处理（不许默默放行）。
    两种读法失败都要覆盖：文件不在、文件在但不是合法 YAML。
    """

    home = wired_home(tmp_root)
    adapter_config = home / "profiles" / "desktop" / ".policy" / "dsh-adapter.yaml"

    adapter_config.unlink()
    code, out, _ = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--check", "--json"],
        capsys,
    )

    assert code == 1
    payload = json.loads(out)
    channel = payload["channels"][0]
    assert payload["result"] == "fail"
    assert channel["status"] == ChannelStatus.TIMEOUT_BUDGET_UNKNOWN.value
    assert channel["wired"] is False
    assert channel["timeout_budget"]["input_error"]
    assert channel["detail"].startswith("证明不了")

    adapter_config.write_text("{not yaml", encoding="utf-8", newline="\n")
    second_code, second_out, _ = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--check", "--json"],
        capsys,
    )

    assert second_code == 1
    second = json.loads(second_out)
    assert second["channels"][0]["status"] == ChannelStatus.TIMEOUT_BUDGET_UNKNOWN.value
    assert "不可读或不可解析" in second["channels"][0]["detail"]


def test_wiring_json_contract(tmp_root: Path, capsys: Any) -> None:
    home = wired_home(tmp_root)

    code, out, _ = run_cli(
        [
            "--root", str(REPO_ROOT), "--json", "wiring", "--dsh-home", str(home),
            "--now", FIXED_NOW_TEXT, "--check",
        ],
        capsys,
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["wiring_schema_version"] == WIRING_SCHEMA_VERSION
    assert set(payload) >= {
        "wiring_schema_version",
        "probe",
        "channels",
        "counts",
        "failures",
        "tools",
        "result",
    }
    assert set(payload["probe"]) >= {
        "dsh_home",
        "dsh_home_source",
        "candidates",
        "status",
        "profiles_dir",
        "project_root",
        "stale_after_seconds",
        "notes",
    }
    assert payload["counts"] == {"total": 1, "wired": 1, "failed": 0}
    assert payload["fact_counts"] == {"total": 1, "wiring_ok": 1, "freshness_ok": 1}
    assert payload["failures"] == []
    assert payload["result"] == "pass"
    assert payload["tools"]["report_only"] is True
    assert payload["channels"][0]["status"] == ChannelStatus.WIRED.value
    # 两根轴各自是协议字段（N20）：不再是"wired 一个字段扛两件事"。
    assert payload["channels"][0]["wiring_status"] == WiringStatus.WIRED.value
    assert payload["channels"][0]["freshness_status"] == FreshnessStatus.FRESH.value
    assert "不再是" in payload["reading_guide"]

    # 台阶 4（1.2）：顶层多一份 reading_context——哪棵树 / 哪一份边界声明 / 哪台宿主。
    # 它只是旁注：上面的 counts / result / 通道状态一个都不由它决定（R-d 的 2 条见 23 号 §9）。
    context = payload["reading_context"]
    assert context["source"] == "gate"
    assert context["tree"]["status"] == "available"
    assert context["tree"]["scope"] == "workspace"
    assert context["tree"]["digest"].startswith("sha256:")
    assert len(context["tree"]["revision"]) == 40
    assert context["host"]["sandbox"] == "unknown"
    # 这一份**保留 run**（21 号 §9.2 裁定①）。
    assert context["run"]["id"] and context["run"]["started_at"].endswith("Z")
    scope = context["declarations"]["wiring_scope"]
    assert scope["status"] == "available"
    assert scope["path"] == "adapters/wiring-scope.yaml"
    assert not Path(scope["path"]).is_absolute()
    # 摘要必须来自**那份真实文件**，不是写死的常量。
    assert scope["digest"] == "sha256:" + hashlib.sha256(
        (REPO_ROOT / "adapters" / "wiring-scope.yaml").read_bytes()
    ).hexdigest()

    # 台阶 4（1.3 / 裁定②）：顶层只多这四个键；既有 13 个一个都不删不改名，
    # 而且上面那些 counts / fact_counts / result / 通道状态**都没有被新键改过**。
    assert set(payload) >= {"account", "differences", "headline", "red_conditions"}
    account = payload["account"]
    assert account["discovered"]["status"] == "available"
    assert account["discovered"]["value"] == len(payload["channels"])
    assert account["declared"]["status"] == "available"
    assert account["declared"]["value"] >= 2
    assert account["measured"]["status"] == "available"
    assert 0 <= account["measured"]["value"] <= account["discovered"]["value"]
    differences = payload["differences"]
    assert differences["status"] == "available"
    assert set(differences) >= set(DIFFERENCE_KEYS) | {"status", "reason", "note"}
    # 红条件是**预注册形态**：显式说出"还没接线"，且不改任何退出码。
    red = payload["red_conditions"]["in_scope_not_wired"]
    assert red["enforced"] is False
    assert red["would_exit_code"] == 1
    assert red["count"] == differences["in_scope_not_wired"]["count"]
    assert red["is_red"] is (red["count"] > 0)
    machine_line = payload["headline"]["machine_line"]
    assert machine_line.startswith("IN_SCOPE_NOT_WIRED: ")
    assert "discovered=" in machine_line and "declared=" in machine_line
    # 每个通道多一份 governs 分档：判定来自声明文件，取值是协议的一部分。
    for channel in payload["channels"]:
        governs = channel["governs"]
        assert governs["decision"] in GOVERNS_DECISIONS
        assert set(governs["tree"]) == {"relation", "declared", "declared_by", "evidence"}
        assert governs["tree"]["relation"] in {"self", "other", "unknown"}
        assert governs["tree"]["declared"] in {"self", "other", "unknown"}


def test_wiring_json_exposes_required_channel_statuses() -> None:
    """枚举值是协议：删一个、改一个名字都必须是一次显式的契约变更。"""

    assert {status.value for status in ChannelStatus} == {
        "wired",
        "not_wired",
        "hooks_config_missing",
        "hooks_config_unparsable",
        "no_audit_target",
        "audit_never_written",
        "stale",
        "profile_unreadable",
        "hooks_config_unreadable",
        "audit_unreadable",
        "audit_unparsable",
        "timeout_budget_violated",
        "timeout_budget_unknown",
    }
    assert set(FAILURE_STATUSES) == set(ChannelStatus) - {ChannelStatus.WIRED}


def test_axis_enums_are_part_of_the_protocol() -> None:
    """两根轴的取值也是协议：删一个、改一个名字都必须是一次显式的契约变更。"""

    assert {status.value for status in WiringStatus} == {
        "wired",
        "not_wired",
        "hooks_config_missing",
        "hooks_config_unparsable",
        "hooks_config_unreadable",
        "profile_unreadable",
        "timeout_budget_violated",
        "timeout_budget_unknown",
    }
    assert {status.value for status in FreshnessStatus} == {
        "fresh",
        "no_audit_target",
        "never_written",
        "stale",
        "unreadable",
        "unparsable",
        "unevaluated",
    }
    # 每一个总判定状态都必须能被拆到两根轴上：没有"未归类"的漏网（漏一个就是静默放行）。
    for status in ChannelStatus:
        wiring, freshness = split_status(status)
        assert wiring in WiringStatus
        assert freshness in FreshnessStatus


def test_wiring_schema_version_is_pinned_to_a_literal() -> None:
    """协议版本必须是**字面量**钉住的：只改常量不能悄悄过去（改版本 = 显式契约变更）。

    1.0 -> 1.1：新增 wiring_status / freshness_status 两个事实轴字段 + reading_guide /
    fact_counts，并且"wired 是接线 + 留痕的联合属性"这一旧读法不再被支持（N20）。
    1.1 -> 1.2：顶层新增 reading_context（台阶 4 / 21 号 §2.5）——顶层加键 = 改协议
    （AGENTS 第 55 条）；它只做旁注，不改任何状态与退出码。
    1.2 -> 1.3：顶层新增 account / differences / headline / red_conditions 四个键，每个通道新增
    governs 分档（24 号 §2.1/§2.2 + §8.3 裁定②）——同样只做报告：--check 的判据、退出码、
    result / failures / counts / fact_counts 与两根事实轴一个都不动。
    1.3 **尚未发布**（还没进 feat），所以 2026-10-03 裁定④ 给 differences 补的第六格
    expected_absent_present（含同名红条件）**在 1.3 内**、版本号不动。
    另一条用例 `test_wiring_json_contract` 只比常量与载荷是否一致，钉不住"版本号本身变了"。
    """

    assert WIRING_SCHEMA_VERSION == "1.3"


def test_missing_dsh_home_fails_the_check_and_says_so(tmp_root: Path, capsys: Any) -> None:
    code, out, err = run_cli(
        [
            "--root",
            str(REPO_ROOT),
            "wiring",
            "--dsh-home",
            str(tmp_root / "nowhere"),
            "--check",
            "--json",
        ],
        capsys,
    )

    assert code == 1
    payload = json.loads(out)
    assert payload["probe"]["status"] == "dsh_home_missing"
    assert payload["channels"] == []
    assert payload["result"] == "fail"
    assert "没有任何通道可以证明已接线" in " ".join(payload["probe"]["notes"])


def test_wiring_usage_errors_exit_two(tmp_root: Path, capsys: Any) -> None:
    home = wired_home(tmp_root)

    bad_now, _, err_now = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--now", "not-a-time"],
        capsys,
    )
    bad_stale, _, err_stale = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--stale-after", "0"],
        capsys,
    )
    bad_root, _, err_root = run_cli(
        [
            "--root",
            str(REPO_ROOT),
            "wiring",
            "--dsh-home",
            str(home),
            "--project-root",
            str(tmp_root / "nowhere"),
        ],
        capsys,
    )

    assert (bad_now, bad_stale, bad_root) == (2, 2, 2)
    assert "--now" in err_now
    assert "stale_after_seconds" in err_stale
    assert "project-root" in err_root


def test_wiring_subcommand_is_registered_and_documented() -> None:
    import adapters.cli as cli_module

    parser = build_parser()
    subparsers = [
        action for action in parser._actions if getattr(action, "choices", None)  # noqa: SLF001
    ]
    commands = set(subparsers[0].choices)
    assert {"matrix", "approve", "check", "inspect", "events", "wiring"} <= commands
    assert "python -m adapters.cli wiring" in cli_module.__doc__


def test_wiring_output_contains_no_absolute_paths(tmp_root: Path, capsys: Any) -> None:
    """AGENTS.md 第 19 条：证据里不得出现绝对路径（夹具根也不行）。"""

    home = wired_home(tmp_root)

    _, out, err = run_cli(
        [
            "--root", str(REPO_ROOT), "--json", "wiring", "--dsh-home", str(home),
            "--now", FIXED_NOW_TEXT,
        ],
        capsys,
    )

    combined = out + err
    assert str(tmp_root) not in combined
    assert tmp_root.as_posix() not in combined


# --------------------------------------------------------------------------- 两根事实轴（N20）


def test_wired_is_not_a_joint_property_of_wiring_and_freshness(
    tmp_root: Path, capsys: Any
) -> None:
    """N20 完成判据：patch 逐字节相同，审计"无 -> 有 -> 无"只改留痕那一根轴。

    修前这一步的对照是：同一个 status 字段从 audit_never_written 翻成 wired（退出码 1 -> 0），
    于是"接线在、但没有留痕"与"接线根本不在"在输出里长得一模一样。
    """

    home, profile = wired_home_without_audit(tmp_root)
    patch = profile / "cordis.patch.yml"
    digest = hashlib.sha256(patch.read_bytes()).hexdigest()

    code, payload = run_wiring_json(home, capsys)
    missing = payload["channels"][0]
    assert code == 1
    assert payload["result"] == "fail"
    assert missing["wiring_status"] == WiringStatus.WIRED.value
    assert missing["freshness_status"] == FreshnessStatus.NEVER_WRITTEN.value
    assert missing["wired"] is False
    assert payload["fact_counts"] == {"total": 1, "wiring_ok": 1, "freshness_ok": 0}

    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-25T11:59:00Z"}) + "\n",
    )
    code, payload = run_wiring_json(home, capsys)
    fresh = payload["channels"][0]
    assert code == 0
    assert payload["result"] == "pass"
    assert fresh["freshness_status"] == FreshnessStatus.FRESH.value
    assert fresh["wired"] is True
    # 接线事实两次相同：patch 逐字节没变，命令摘要也没变。
    assert fresh["wiring_status"] == missing["wiring_status"]
    assert fresh["hook_command_digest"] == missing["hook_command_digest"]
    assert fresh["patch"] == missing["patch"]
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == digest

    (profile / ".policy" / "audit.jsonl").unlink()
    code, payload = run_wiring_json(home, capsys)
    reset = payload["channels"][0]
    assert code == 1
    assert payload["result"] == "fail"
    assert reset["wiring_status"] == WiringStatus.WIRED.value
    assert reset["freshness_status"] == FreshnessStatus.NEVER_WRITTEN.value
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == digest


def test_check_still_fails_when_only_the_wiring_axis_is_broken(
    tmp_root: Path, capsys: Any
) -> None:
    """失败关闭没有放松：接线坏了（留痕甚至没被评估）一样退出 1。"""

    home = wired_home(tmp_root)
    profile = home / "profiles" / "desktop"
    _write(profile / "cordis.patch.yml", "[]\n")  # 桥不在 patch 里了

    code, payload = run_wiring_json(home, capsys)
    channel = payload["channels"][0]

    assert code == 1
    assert payload["result"] == "fail"
    assert channel["wiring_status"] == WiringStatus.NOT_WIRED.value
    assert channel["freshness_status"] == FreshnessStatus.UNEVALUATED.value
    assert channel["wired"] is False
    # 审计文件其实在磁盘上：留痕是"没评估"（接线先坏），不是"fresh"。
    assert (profile / ".policy" / "audit.jsonl").is_file()


def test_freshness_axis_separates_stale_from_never_written(tmp_root: Path, capsys: Any) -> None:
    """留痕那一根轴自己也有多种失败态：过期的留痕不等于没有留痕。"""

    home = wired_home(tmp_root)
    profile = home / "profiles" / "desktop"
    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-01T00:00:00Z"}) + "\n",
    )

    code, payload = run_wiring_json(home, capsys)
    channel = payload["channels"][0]

    assert code == 1
    assert channel["wiring_status"] == WiringStatus.WIRED.value
    assert channel["freshness_status"] == FreshnessStatus.STALE.value
    assert channel["status"] == ChannelStatus.STALE.value


def test_human_output_prints_both_facts_separately(tmp_root: Path, capsys: Any) -> None:
    """人眼也要能分开读：接线在而没留痕，与接线不在，是两行不同的事实。"""

    home, _ = wired_home_without_audit(tmp_root)

    code, out, err = run_cli(
        [
            "--root",
            str(REPO_ROOT),
            "wiring",
            "--dsh-home",
            str(home),
            "--now",
            "2026-09-25T12:00:00Z",
            "--observe-sessions",
            "0",
            "--check",
        ],
        capsys,
    )

    assert code == 1
    assert "接线事实：wired" in out
    assert "留痕事实：never_written" in out
    # 口径：输出里必须写明 wired 不再是"接线 + 留痕"的联合属性（N20 的文档要求）。
    assert "口径：" in out
    assert "不再是" in out
    assert "事实合计：接线成立 1/1；留痕新鲜 0/1" in out
    assert "fail" in err


# --------------------------------------------------------------------------- 与运行期自检互相验证


def test_wiring_verdict_agrees_with_the_hook_self_check(tmp_root: Path, dsh_project: Path) -> None:
    """两套独立实现（运行期 hooks.check_wiring 与本模块的遍历）必须得到同一个结论。

    它们要是漂移了，"清点说接好了、运行期却判 wiring_error" 这种矛盾就没有任何检查能发现。
    """

    from adapters.dsh.hooks import check_wiring, load_config

    config_path = write_dsh_config(
        tmp_root / "cfg" / "dsh-adapter.yaml", project_root=dsh_project, rules=POLICIES_DIR
    )
    config = load_config(config_path)
    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", profile_patch(profile))

    good = _write(profile / ".policy" / "hooks.json", json.dumps(hooks_document()))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-25T11:59:00Z"}) + "\n",
    )
    assert check_wiring(config, hooks_config_path=good) == ""
    good_status = probe_wiring(
        dsh_home=home, observed_sessions=0, now=FIXED_NOW
    ).channels[0].status
    assert good_status is ChannelStatus.WIRED, good_status

    bad = _write(
        profile / ".policy" / "hooks.json",
        json.dumps(hooks_document(command="python -m other.thing")),
    )
    report = check_wiring(config, hooks_config_path=bad)
    assert report != ""
    bad_status = probe_wiring(
        dsh_home=home, observed_sessions=0, now=FIXED_NOW
    ).channels[0].status
    assert bad_status is ChannelStatus.NOT_WIRED, bad_status


def test_missing_hooks_config_agrees_with_the_hook_self_check(
    tmp_root: Path, dsh_project: Path
) -> None:
    from adapters.dsh.hooks import check_wiring, load_config

    config_path = write_dsh_config(
        tmp_root / "cfg" / "dsh-adapter.yaml", project_root=dsh_project, rules=POLICIES_DIR
    )
    config = load_config(config_path)
    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", profile_patch(profile))

    missing = profile / ".policy" / "hooks.json"
    assert check_wiring(config, hooks_config_path=missing) != ""
    status = probe_wiring(
        dsh_home=home, observed_sessions=0, now=FIXED_NOW
    ).channels[0].status
    assert status is ChannelStatus.HOOKS_CONFIG_MISSING, status


def test_timeout_budget_check_agrees_with_the_hook_self_check(
    tmp_root: Path, dsh_project: Path
) -> None:
    """超时不等式：运行期判 wiring_error 的情形，清点必须把预算事实标出来。"""

    from adapters.dsh.hooks import check_wiring, load_config

    config_path = write_dsh_config(
        tmp_root / "cfg" / "dsh-adapter.yaml", project_root=dsh_project, rules=POLICIES_DIR
    )
    config = load_config(config_path)
    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", profile_patch(profile))
    hooks_path = _write(profile / ".policy" / "hooks.json", json.dumps(hooks_document(timeout=3)))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-25T11:59:00Z"}) + "\n",
    )

    # 运行期判错 -> 清点必须也是失败态（不是"只记一条 warning"）。
    assert check_wiring(config, hooks_config_path=hooks_path) != ""
    channel = probe_wiring(dsh_home=home, observed_sessions=0, now=FIXED_NOW).channels[0]
    assert channel.timeout_budget["ok"] is False
    assert channel.status is ChannelStatus.TIMEOUT_BUDGET_VIOLATED
    assert channel.ok is False


# --------------------------------------------------------------------------- 默认探测


def test_default_probe_never_reports_a_vacuous_pass() -> None:
    """用默认位置（$DSH_HOME / ~/.dsh）探测：不许炸，也不许在探不到通道时说 pass。"""

    report = probe_wiring(observed_sessions=0)

    assert report.result in {"pass", "fail", "skipped"}
    assert [channel.channel_id for channel in report.channels] == sorted(
        channel.channel_id for channel in report.channels
    )
    if not report.channels:
        assert report.ok is False
        assert report.result != "pass"


def test_no_runtime_is_skipped_in_the_cli_and_require_runtime_turns_it_red(
    tmp_root: Path, monkeypatch: Any, capsys: Any
) -> None:
    """环境跳过：--check 退出 0 但 result=skipped（并写明原因），--require-runtime 让它变红。"""

    monkeypatch.setattr(
        "adapters.wiring._dsh_home_candidates",
        lambda: [("test:no-runtime", tmp_root / "no-runtime")],
    )

    code, out, _ = run_cli(
        ["--root", str(REPO_ROOT), "--json", "wiring", "--check"], capsys
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["result"] == "skipped"
    assert payload["environment_skipped"] is True
    assert payload["skip_reason"] and "环境跳过" in payload["skip_reason"]
    assert payload["reproduce"]
    assert payload["channels"] == []
    assert payload["result"] != "pass"

    strict, out_strict, err_strict = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--check", "--require-runtime"], capsys
    )

    assert strict == 1
    assert "skipped" in err_strict
    assert "复现" in err_strict


# --------------------------------------------------------------------------- 台阶 4（1.3）

# 两个自制声明文件（写到 tmp 的 root 下，不动仓库那一份）——覆盖账读的**就是这个位置**。
EXPLICIT_COVERS_DECLARATION = """\
schema_version: "2"
channel_kinds:
  dsh-profile: agent_runtime
scope:
  - id: governed-session-hook
    decision: in_scope
    kind: agent_runtime
    owner: platform
    reason: 受控会话由本仓库治理。
    consequence: 接不上就不放行。
    covers: ["dsh:desk*"]
  - id: desktop-entry-points
    decision: out_of_scope
    kind: agent_runtime
    owner: host
    reason: 桌面通道是主机配置。
    consequence: 只报告。
    expires_at: "2026-12-31"
"""

CONFLICTING_DECLARATION = """\
schema_version: "2"
channel_kinds:
  dsh-profile: agent_runtime
scope:
  - id: a-in-scope
    decision: in_scope
    kind: agent_runtime
    owner: platform
    reason: 在范围内。
    consequence: 不放行。
  - id: b-out-of-scope
    decision: out_of_scope
    kind: agent_runtime
    owner: host
    reason: 主机配置。
    consequence: 只报告。
    expires_at: "2026-12-31"
"""


def write_declaration(root: Path, text: str) -> Path:
    """把声明文件写到这个 root 的 adapters/ 下——`--root` 指到哪，读的就是哪一份。"""

    return _write(root / "adapters" / "wiring-scope.yaml", text)


def test_governs_uses_explicit_covers_and_flags_in_scope_not_wired(
    tmp_root: Path, capsys: Any
) -> None:
    """规则 1：显式 covers 优先于 kind 档；声明 in_scope 而通道没接线 → 红条件计数 1。

    夹具是"接线在、留痕没有"（N20 的正例），因此它**不是** wired，落进 in_scope_not_wired；
    同一份声明文件里还有一条同档、判决相反的声明——若没有显式覆盖，这里就该是 undeclared。
    """

    root = tmp_root / "root"
    write_declaration(root, EXPLICIT_COVERS_DECLARATION)
    home, _profile = wired_home_without_audit(tmp_root)

    code, out, _ = run_cli(
        [
            "--root", str(root), "--json", "wiring", "--dsh-home", str(home),
            "--now", FIXED_NOW_TEXT, "--observe-sessions", "0",
        ],
        capsys,
    )

    assert code == 0  # 只报告：默认形态仍然退出 0
    payload = json.loads(out)
    channel = payload["channels"][0]
    assert channel["channel_id"] == "dsh:desktop"
    assert channel["wired"] is False
    assert channel["governs"]["decision"] == "in_scope"
    assert channel["governs"]["declared_by"] == "governed-session-hook"
    assert channel["governs"]["expires_at"] is None  # in_scope 不该有过期日
    # 通道自己的目标渲染成 <external>/… → relation=other（证据就是那个字段名）。
    assert channel["governs"]["tree"]["relation"] == "other"
    assert channel["governs"]["tree"]["evidence"] == ["bridge.entry"]
    # 声明侧没写 governs_tree → 裁定④（2026-10-01）之后读作 unknown，**不是** self：
    # "默认 self + 证据 other"这对矛盾按 24 号 §2.1 的边界不进五个差集，默认 self 会让它
    # 静默存在；declared_by 仍指得出是哪条声明，两件事因此分得开（23 号 §15.1 裁定④）。
    assert channel["governs"]["tree"]["declared"] == "unknown"
    assert channel["governs"]["tree"]["declared_by"] == "governed-session-hook"

    not_declared = payload["differences"]["discovered_not_declared"]
    assert not_declared["count"] == 0  # 有显式覆盖，不算"没声明"
    in_scope = payload["differences"]["in_scope_not_wired"]
    assert in_scope["count"] == 1
    item = in_scope["items"][0]
    assert item["channel_id"] == "dsh:desktop"
    assert item["remedy"]
    red = payload["red_conditions"]["in_scope_not_wired"]
    assert red["count"] == 1 and red["is_red"] is True and red["enforced"] is False
    assert payload["differences"]["out_of_scope_active"]["count"] == 0


EXPECTED_ABSENT_DECLARATION = """\
schema_version: "2"
channel_kinds:
  dsh-profile: agent_runtime
scope:
  - id: ci-agent-runtime
    decision: expected_absent
    kind: agent_runtime
    owner: ci
    reason: CI 机器上按设计没有 Agent 运行时。
    consequence: 相关步骤显式报 skipped 并写明 reason。
    covers: ["dsh:verify-bc"]
    expires_at: "2026-12-31"
"""


def test_expected_absent_covering_a_discovered_channel_is_counted(
    tmp_root: Path, capsys: Any
) -> None:
    """第六格（2026-10-03 裁定④）：expected_absent 声明覆盖到**被发现**的通道 → 计数 1。

    场景复用 `.tmp/step13/probe-ea2`（`ci-agent-runtime` 显式 covers `dsh:verify-bc`，而那个
    profile 真的在本机）。它既不算"未声明"、也不进其余五格——这一格就是把「声明说它不该在，
    它却在了」变成可读的读数。**只报告**：is_red=count>0、enforced=false、通道自己仍然 pass。
    """

    root = tmp_root / "root"
    write_declaration(root, EXPECTED_ABSENT_DECLARATION)
    home = make_home(tmp_root)
    add_profile(home, "verify-bc", profile_patch(home / "profiles" / "verify-bc"))

    code, out, _ = run_cli(
        [
            "--root", str(root), "--json", "wiring", "--dsh-home", str(home),
            "--now", FIXED_NOW_TEXT, "--observe-sessions", "0",
        ],
        capsys,
    )

    assert code == 0  # 只报告：默认形态仍然退出 0
    payload = json.loads(out)
    channel = payload["channels"][0]
    assert channel["channel_id"] == "dsh:verify-bc"
    assert channel["governs"]["decision"] == "expected_absent"
    assert channel["governs"]["declared_by"] == "ci-agent-runtime"
    grid = payload["differences"]["expected_absent_present"]
    assert grid["count"] == 1
    item = grid["items"][0]
    assert item["channel_id"] == "dsh:verify-bc"
    assert item["declared_by"] == "ci-agent-runtime"
    assert item["decision"] == "expected_absent"
    assert item["remedy"]
    red = payload["red_conditions"]["expected_absent_present"]
    assert red["count"] == 1 and red["is_red"] is True and red["enforced"] is False
    assert red["would_exit_code"] == 1
    # 这一格不影响其余任何一格：它既不进"未声明"，也不进"in_scope 未接线"。
    assert payload["differences"]["discovered_not_declared"]["count"] == 0
    assert payload["differences"]["in_scope_not_wired"]["count"] == 0
    assert payload["differences"]["declared_not_discovered"]["count"] == 0


def test_same_tier_conflicting_declarations_are_not_guessed(tmp_root: Path, capsys: Any) -> None:
    """规则 3：同一通道被多条同档声明命中而判决不同 → undeclared + 逐条冲突，不挑一个。"""

    root = tmp_root / "root"
    write_declaration(root, CONFLICTING_DECLARATION)
    home = wired_home(tmp_root)

    code, out, _ = run_cli(
        [
            "--root", str(root), "--json", "wiring", "--dsh-home", str(home),
            "--now", FIXED_NOW_TEXT, "--observe-sessions", "0",
        ],
        capsys,
    )

    assert code == 0
    payload = json.loads(out)
    channel = payload["channels"][0]
    assert payload["result"] == "pass"  # 通道本身是 wired + fresh：冲突不影响判定
    assert channel["governs"]["decision"] == GOVERNS_UNDECLARED
    assert channel["governs"]["declared_by"] is None
    assert "不挑一个" in channel["governs"]["note"]
    # 没有可判定的声明 → "有没有意治理另一棵树"拿不出证据：写 unknown（裁定③）。
    assert channel["governs"]["tree"]["declared"] == "unknown"
    conflicts = payload["differences"]["declaration_conflicts"]
    assert conflicts["count"] == 1
    assert {item["id"] for item in conflicts["items"][0]["candidates"]} == {
        "a-in-scope",
        "b-out-of-scope",
    }
    # 冲突的通道既不进"未声明"（它有候选），也不进 in_scope_not_wired（没有可判定的档）。
    assert payload["differences"]["discovered_not_declared"]["count"] == 0
    assert payload["differences"]["in_scope_not_wired"]["count"] == 0
    assert payload["red_conditions"]["in_scope_not_wired"]["count"] == 0


def test_the_three_numbers_are_unavailable_not_zero_when_nothing_is_enumerated(
    tmp_root: Path, capsys: Any
) -> None:
    """裁定④：没枚举到通道时三数写 unavailable（带 reason），**不许写 0**。

    与"枚举过、一个都没有"必须分得开：本用例第二节就是后者（profiles 目录存在但是空的）。
    """

    code, out, _ = run_cli(
        ["--root", str(REPO_ROOT), "--json", "wiring", "--dsh-home", str(tmp_root / "nowhere")],
        capsys,
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["channels"] == []
    for key in ("discovered", "measured"):
        block = payload["account"][key]
        assert block["status"] == "unavailable"
        assert block["value"] is None, key + " 读不到时不许写 0"
        assert block["reason"]
    # 声明文件是读得到的（--root 是仓库）：它**不是** unavailable，也不受"没枚举到通道"影响。
    assert payload["account"]["declared"]["status"] == "available"
    differences = payload["differences"]
    assert differences["status"] == "unavailable"
    assert differences["reason"]
    assert differences["in_scope_not_wired"]["count"] is None
    assert differences["in_scope_not_wired"]["items"] == []
    red = payload["red_conditions"]["in_scope_not_wired"]
    assert red["count"] is None and red["is_red"] is False and red["enforced"] is False
    assert "unavailable" in payload["headline"]["machine_line"]

    # 对照：profiles 目录存在、里面一个 profile 都没有 → **真的 0**（枚举发生了，只是空）。
    empty = make_home(tmp_root)
    _, out_empty, _ = run_cli(
        ["--root", str(REPO_ROOT), "--json", "wiring", "--dsh-home", str(empty),
         "--observe-sessions", "0"],
        capsys,
    )
    empty_payload = json.loads(out_empty)
    assert empty_payload["probe"]["status"] == "ok"
    assert empty_payload["account"]["discovered"] == {
        "status": "available",
        "value": 0,
        "reason": None,
    }
    line = empty_payload["headline"]["machine_line"]
    assert "discovered=0" in line and "measured=0" in line  # 真的是 0，不是 unavailable
    assert "unavailable" not in line

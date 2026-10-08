"""Phase 5 验证器 CLI 集成测试：真实子进程、退出码与机器可读载荷。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import POLICIES_DIR, REPO_ROOT, write_validation_config
from policy.loader import load_rule_set

pytestmark = pytest.mark.integration

PROJECT = "tests/fixtures/validators/project"


def subprocess_env() -> dict[str, str]:
    """本文件里**所有**子进程都用这一份环境：源码路径与输出编码都固定。

    子进程 stdout 的编码跟它自己的环境走（本机 `chcp` = 936 时默认写 GBK），而调用方
    一律按 `encoding="utf-8"` 解码：父进程的 `PYTHONIOENCODING` 一换（或干脆没有这个
    变量），同一个子进程就写出另一种字节，断言随环境改变。所以环境口径在这里钉死，
    三处调用共用一份实现，不各自拼一份。
    """

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = subprocess_env()
    return subprocess.run(
        [sys.executable, "-m", "validators.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_registry_command_prints_the_declared_facts() -> None:
    completed = cli("registry", "--json")

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["stages"][0] == "source"
    assert {item["id"] for item in payload["validators"]} == {
        "py.source",
        "py.ast",
        "py.depgraph",
        "py.docstring",
        "tool.ruff",
        "tool.mypy",
        "tool.pytest",
    }
    assert payload["checkers"]["python"]["forbidden_dependency"] == ["py.depgraph"]
    assert payload["defaults"]["max_parallel"] >= 1


def test_registry_show_reports_one_validator() -> None:
    completed = cli("registry", "--show", "tool.ruff")

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["validators"][0]["tool"]["config"] == "validation/ruff.toml"
    assert payload["validators"][0]["critical"] is True


def test_registry_show_rejects_unknown_ids() -> None:
    completed = cli("registry", "--show", "tool.absent")

    assert completed.returncode == 2
    assert "config error" in completed.stderr


def test_probe_directory_failure_is_a_documented_exit_code(tmp_path: Path) -> None:
    """探针的目录建不出来时必须给退出码 2，而不是裸 traceback + 1（复核发现）。"""

    root = write_validation_config(tmp_path)
    blocker = root / ".tmp" / "validators"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("not a directory" + chr(10), encoding="utf-8", newline="")

    completed = cli("probe", "--config-root", str(root))

    assert completed.returncode == 2, completed.stderr
    assert "config error" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_probe_reports_tool_availability() -> None:
    completed = cli("probe", "--json")

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    statuses = {item["validator"]: item["status"] for item in payload["tools"]}
    assert set(statuses) == {"tool.ruff@1.0", "tool.mypy@1.0", "tool.pytest@1.0"}
    assert statuses["tool.pytest@1.0"] == "ok"  # pytest 是本项目的依赖，必定可用


def test_check_command_only_produces_evidence() -> None:
    """check 只交证据：即使依赖违规很明显，它也不给 allow / block（那是 pipeline 的活）。"""

    completed = cli(
        "check",
        "src/shop/order_controller_bad.py",
        "--layer",
        "controller",
        "--workspace",
        PROJECT,
        "--json",
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["result"] is None  # check 不做判定
    assert payload["evidence"]["dependencies"][0]["name"] == "repository"
    assert payload["evidence"]["schema_version"] == "1.2"


def test_check_command_exits_one_on_findings() -> None:
    completed = cli(
        "check",
        "src/shop/style_offences.py",
        "--layer",
        "service",
        "--workspace",
        PROJECT,
        "--json",
    )

    if not any(tool["status"] == "ok" for tool in json.loads(cli("probe", "--json").stdout)["tools"]):
        pytest.skip("本机没有任何可用的外部工具")
    assert completed.returncode == 1, completed.stderr
    payload = json.loads(completed.stdout)
    validators = {item["validator"] for item in payload["evidence"]["evidence"]}
    assert "tool.ruff@1.0" in validators
    # 每条证据都必须归到一条真实存在、且**声明了这个诊断码**的规则上。
    # 这比"写死两个规则 id"更强：它同时挡住"证据指向不存在的规则"与
    # "把诊断码挂到没声明它的规则上"（后者会让规则看起来在管这件事）。
    rules = {rule.id: rule for rule in load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT).rules}
    for item in payload["evidence"]["evidence"]:
        rule = rules.get(item["rule_id"])
        assert rule is not None, "证据指向了不存在的规则：" + item["rule_id"]
        body = getattr(rule.rule, "style_lint", None)
        assert body is not None and item["value"] in body.codes, (
            "诊断码被归到了没有声明它的规则上：" + item["rule_id"] + " / " + item["value"]
        )


def test_pipeline_command_matches_policy_check() -> None:
    env = subprocess_env()
    args = [
        "src/shop/order_controller_bad.py",
        "--layer",
        "controller",
        "--workspace",
        PROJECT,
        "--request-id",
        "req-p5-compare",
    ]
    first = cli("pipeline", *args, "--json")
    second = subprocess.run(
        [sys.executable, "-m", "policy.check", *args, "--json"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert first.returncode == second.returncode == 1, first.stderr + second.stderr
    assert json.loads(first.stdout)["result"] == json.loads(second.stdout)["result"]


def test_check_command_rejects_a_target_outside_the_workspace(tmp_root: Path) -> None:
    completed = cli("check", "../outside.py", "--layer", "controller", "--workspace", PROJECT)

    assert completed.returncode == 2
    assert "config error" in completed.stderr


def test_check_requires_an_explicit_layer() -> None:
    completed = cli("check", "src/shop/order_controller.py", "--workspace", PROJECT)

    assert completed.returncode == 2
    assert "--layer" in completed.stderr


def test_unknown_validator_filter_is_rejected() -> None:
    completed = cli(
        "check",
        "src/shop/order_controller.py",
        "--layer",
        "controller",
        "--workspace",
        PROJECT,
        "--validators",
        "tool.absent",
    )

    assert completed.returncode == 2
    assert "tool.absent" in completed.stderr


def test_git_paths_are_converted_to_the_workspace_coordinate_system(monkeypatch) -> None:
    """git 的路径锚在仓库顶层，必须换算成 workspace 坐标系（复核发现）。"""

    from validators import cli as cli_module

    with monkeypatch.context() as patcher:
        patcher.setattr(
            cli_module, "_git_prefix", lambda anchor: "tests/fixtures/validators/project/"
        )
        converted = cli_module._workspace_relative(
            (
                "tests/fixtures/validators/project/src/shop/a.py",
                "tests/fixtures/validators/project/tests/test_a.py",
                "src/policy/models.py",  # 工作区之外：丢掉
                "tests/fixtures/validators/project/",  # 目录项：换算后为空，丢掉
            ),
            Path("tests/fixtures/validators/project"),
        )

    assert converted == ("src/shop/a.py", "tests/test_a.py")

    # 顶层工作区（前缀为空）原样返回。
    with monkeypatch.context() as patcher:
        patcher.setattr(cli_module, "_git_prefix", lambda anchor: "")
        assert cli_module._workspace_relative(("src/a.py",), Path(".")) == ("src/a.py",)


def test_changed_from_git_rejects_option_like_refs(tmp_root: Path) -> None:
    """--changed-from-git 的 ref 不能以 '-' 开头：git 会把它当选项（复核发现：选项注入）。"""

    leak = tmp_root / "leak.txt"
    for ref in ("--output=" + str(leak), "--no-index", "--ext-diff"):
        completed = cli(
            "check",
            "src/shop/order_service.py",
            "--layer",
            "service",
            "--workspace",
            PROJECT,
            "--operation",
            "edit",
            "--changed-from-git=" + ref,
            "--rules",
            str(REPO_ROOT / "policies"),
        )
        assert completed.returncode == 2, (ref, completed.stderr)
        assert "不能以" in completed.stderr, (ref, completed.stderr)
        assert "Traceback" not in completed.stderr, ref
    assert not leak.exists(), "git 不许被诱导把输出写到别处"


def test_changed_from_git_uses_the_working_tree(tmp_root: Path) -> None:
    """--changed-from-git 直接问 git 要变更集；没有 git 时会显式失败而不是当作没有变更。"""

    completed = cli(
        "check",
        "src/shop/order_service.py",
        "--layer",
        "service",
        "--workspace",
        PROJECT,
        "--operation",
        "edit",
        "--changed-from-git",
        "HEAD",
        "--rules",
        str(REPO_ROOT / "policies"),
    )

    assert completed.returncode in (0, 1, 2)
    if completed.returncode == 2:
        assert "git" in completed.stderr


# --------------------------------------------------------------------------- A2：target 解析只有一条口径


def policy_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """在仓库根目录以子进程方式运行 python -m policy.check（只用于口径比对）。"""

    env = subprocess_env()
    return subprocess.run(
        [sys.executable, "-m", "policy.check", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def missing_target_blockers(payload: dict) -> list:
    """只挑"目标文件没被定位到"这一类阻断点：它正是两处口径分叉时的可观察差异。

    窄口径（只跑 py.*）下还会有"没有验证器为某个 checker 提供证据"的失败关闭阻断点，
    那是**预期的**，与 target 解析无关，不能拿来当信号。
    """

    return [
        item
        for item in payload["evidence"]["blockers"]
        if "目标文件不存在" in str(item.get("reason", ""))
    ]


def test_target_resolution_matches_policy_check_for_a_workspace_prefixed_path() -> None:
    """带工作区前缀的路径按 --workspace 解析，与 policy.check 得到同一个 context。

    旧口径把整串当成工作区相对路径，于是同一个文件被判成"不存在"——
    调用方要么换成裸文件名、要么白试一次，这正是"两处口径"的代价。
    """

    args = (
        PROJECT + "/src/shop/order_controller.py",
        "--layer",
        "controller",
        "--workspace",
        PROJECT,
        "--validators",
        "py.source,py.ast,py.depgraph",
        "--request-id",
        "req-a2-prefixed",
        "--json",
    )
    evidence_run = cli("check", *args)
    policy_run = policy_cli(*args)

    # 只跑 py.* 时，没被覆盖的 checker 仍按失败关闭给出阻断点（退出码 1）：
    # 这里要守的是"文件被定位到了"，不是"命令有没有发现"。
    assert evidence_run.returncode in (0, 1), evidence_run.stderr + evidence_run.stdout
    payload = json.loads(evidence_run.stdout)
    assert payload["context"]["file"] == "src/shop/order_controller.py"
    assert missing_target_blockers(payload) == []
    assert payload["context"] == json.loads(policy_run.stdout)["context"]


def test_config_root_does_not_move_the_workspace(tmp_root: Path) -> None:
    """--config-root 只决定 validation/ 配置在哪，不再顺带改工作区口径。

    目标写成仓库相对路径、并且**不给 --workspace**：旧口径会把 --config-root 也当成
    工作区的锚，于是目标被判成"不存在"；统一之后默认工作区是仓库根（与 policy.check 同一条规则）。
    """

    import shutil

    write_validation_config(tmp_root)
    # 规则目录也必须落在配置根之内（loader 的 repo_root 就是配置根），
    # 所以这里连规则一起复制——这条用例要测的是工作区口径，不是规则加载。
    shutil.copytree(REPO_ROOT / "policies", tmp_root / "policies")
    completed = cli(
        "check",
        PROJECT + "/src/shop/order_controller.py",
        "--layer",
        "controller",
        "--config-root",
        tmp_root.relative_to(REPO_ROOT).as_posix(),
        "--rules",
        str(tmp_root / "policies"),
        "--validators",
        "py.source,py.ast,py.depgraph",
        "--json",
    )

    assert completed.returncode in (0, 1), completed.stderr + completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["context"]["file"] == PROJECT + "/src/shop/order_controller.py"
    assert missing_target_blockers(payload) == []

# --------------------------------------------------------------- P4：验证器入口不做分层推断


def test_validators_cli_still_rejects_a_missing_layer_for_a_platform_test_path(
    tmp_root: Path,
) -> None:
    """P4 只改 policy.check：验证器入口缺 --layer 时**继续拒绝**，不跟着推断。

    `validators.cli` 的 --layer 是调用方必须自证的输入；给它补一个"平台数据说是测试"的
    默认值，等于把分层责任从调用方挪到平台，而验证器与流水线要的恰恰是一个**声明过的**层。
    这条用例守住"P4 的改动没有顺着共享数据扩散到另一个入口"。
    """

    workspace = tmp_root / "ws"
    target = workspace / "tests" / "test_shipment_controller.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('"""出库控制器测试。"""' + chr(10), encoding="utf-8", newline="")

    completed = cli(
        "check",
        "tests/test_shipment_controller.py",
        "--workspace",
        workspace.relative_to(REPO_ROOT).as_posix(),
    )

    assert completed.returncode == 2
    assert "--layer" in completed.stderr

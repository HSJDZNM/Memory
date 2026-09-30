"""Phase 0 CLI 集成测试：真实子进程、输出内容、退出码与可重放性。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import yaml

from policy.check import (
    EXIT_ALLOWED,
    EXIT_ERROR,
    EXIT_VIOLATION,
    OUTPUT_SCHEMA_VERSION,
    default_rule_dirs,
    exit_code_for,
    infer_layer,
    parse_dependencies,
    python_imports,
    run,
)
from policy.loader import load_rule_set
from policy.models import (
    SCHEMA_VERSION,
    Decision,
    Evidence,
    ProtocolError,
    Severity,
    ValidationResult,
    Violation,
    parse_decision,
)

from conftest import REPO_ROOT, rule_document, write_rule, write_validation_config

pytestmark = pytest.mark.integration

BAD_EXAMPLE = "examples/bad_controller.py"
GOOD_EXAMPLE = "examples/good_controller.py"


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def workspace_path(path: Path) -> str:
    """把临时目录转换成相对仓库根目录的路径，便于子进程与错误信息断言。"""

    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return str(path)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """在仓库根目录以子进程方式运行 python -m policy.check。"""

    return subprocess.run(
        [sys.executable, "-m", "policy.check", *args],
        cwd=REPO_ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_bad_fixture_reports_rule_and_exits_1() -> None:
    completed = run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--request-id", "req-bad")

    assert completed.returncode == EXIT_VIOLATION, completed.stderr
    stdout = completed.stdout
    assert "ARCH-001" + "@" + "1" in stdout
    assert "Controller 必须通过 Service 访问 Repository。" in stdout
    assert "controller -> service -> repository" in stdout
    assert "evidence: dependency=repository" in stdout
    assert "FAIL" in stdout


def test_good_fixture_exits_0() -> None:
    completed = run_cli(GOOD_EXAMPLE, "--dependencies", "service", "--request-id", "req-good")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    assert "PASS" in completed.stdout
    # 决策必须说清哪些规则参与了判断、哪些被跳过
    assert "matched: ARCH-001" + "@" + "1" in completed.stdout
    # Phase 5 起 TESTING-* 需要变更上下文：没有 --operation 时按范围跳过并写明原因
    assert "TESTING-001" + "@" + "1: operation <missing> != [create, edit]" in completed.stdout


def test_scope_mismatch_is_reported_as_skip_reason() -> None:
    """layer=service 时 ARCH-001 不参与判断，CLI 要给出原因，而不是只报 PASS。"""

    completed = run_cli(GOOD_EXAMPLE, "--dependencies", "repository", "--layer", "service")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    assert "skipped (规则范围不匹配，未参与判断):" in completed.stdout
    assert "- ARCH-001" + "@" + "1: layer service != controller" in completed.stdout
    matched_line = next(
        line for line in completed.stdout.splitlines() if line.startswith("matched: ")
    )
    assert "ARCH-001" + "@" + "1" not in matched_line, matched_line


def normalise_run_identity(text: str) -> tuple[str, dict]:
    """把 reading_context.run 里**声明为随运行变化**的两个字段换成占位符。

    为什么必须这么剥（台阶 4，21 号 §2.1）：--json 顶层多了一份 reading_context，其中
    run.id / run.started_at 是"本次进程生成"的读数，于是这份包装**不再是输入的纯函数**——
    "两次运行逐字节相同"这条断言必须改成"**除这两个字段外**逐字节相同"。
    剥掉的值必须由调用方**单独再断言一次**（存在、形状对），免得"剥"变成"不看了"。
    这不是"放宽断言"：归一化之后的文本仍然逐字节比对，多出来的键、变了的键照样会红。
    """

    payload = json.loads(text)
    values = {}
    for key in ("id", "started_at"):
        values[key] = payload["reading_context"]["run"][key]
        payload["reading_context"]["run"][key] = "<volatile>"
    # 与 render_json 的格式化逐字相同（ensure_ascii=False / indent=2 / sort_keys=True）。
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10), values


def test_cli_is_reproducible() -> None:
    args = (BAD_EXAMPLE, "--dependencies", "repository", "--request-id", "req-fixed")

    first = run_cli(*args)
    second = run_cli(*args)

    assert first.returncode == second.returncode == EXIT_VIOLATION
    # 这条讲的是**文本输出**：它没有 reading_context，因此仍然逐字节可重现。
    # --json 的对应性质见下面的 test_json_output_is_reproducible_modulo_the_run_identity。
    assert first.stdout == second.stdout
    assert first.stderr == second.stderr


def test_json_output_is_reproducible_modulo_the_run_identity() -> None:
    """--json 的两次运行：**除 reading_context.run 那两个字段外**逐字节相同（台阶 4）。

    这不是把断言放宽：归一化之后的文本仍然逐字节比对，多出来的键、变了的键照样会红；
    多出来的只是"这一步归一化"本身，因为 --json 现在带上了"本次运行"的标识（21 号 §2.1）。
    """

    args = (BAD_EXAMPLE, "--dependencies", "repository", "--request-id", "req-fixed", "--json")

    first = run_cli(*args)
    second = run_cli(*args)

    assert first.returncode == second.returncode == EXIT_VIOLATION
    first_text, first_run = normalise_run_identity(first.stdout)
    second_text, second_run = normalise_run_identity(second.stdout)
    assert first_text == second_text, "剥掉 run 身份之后必须逐字节相同"
    # 剥掉的那两个字段单独看：存在、形状对、而且**确实每次都不同**（否则这条用例成了空转）。
    assert first_run["id"] != second_run["id"]
    uuid.UUID(first_run["id"])
    assert first_run["started_at"].endswith("Z")


def test_missing_rule_directory_exits_2(tmp_root: Path) -> None:
    completed = run_cli(GOOD_EXAMPLE, "--rules", workspace_path(tmp_root / "absent"))

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr
    assert "规则目录不存在" in completed.stderr
    assert completed.stdout == ""


def test_corrupted_rule_file_exits_2(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    root.mkdir()
    (root / "ARCH-001.yaml").write_text("id: ARCH-001\nversion: [1, 2\n", encoding="utf-8")

    completed = run_cli(GOOD_EXAMPLE, "--rules", workspace_path(root))

    assert completed.returncode == EXIT_ERROR
    assert "ARCH-001.yaml" in completed.stderr


def test_unknown_checker_exits_2(tmp_root: Path) -> None:
    """未知 checker 在**加载阶段**就被拒绝（Phase 5 起比引擎阶段更早失败）。"""

    root = tmp_root / "policies"
    document = rule_document()
    document["enforcement"]["checker"] = "llm_judgement"
    write_rule(root / "ARCH-001.yaml", document, yaml_module=yaml)

    completed = run_cli(GOOD_EXAMPLE, "--rules", workspace_path(root))

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr
    assert "llm_judgement" in completed.stderr
    assert completed.stdout == ""


def test_missing_file_exits_2() -> None:
    completed = run_cli("examples/does_not_exist.py", "--rules", "policies")

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr


def test_directory_instead_of_file_exits_2() -> None:
    """路径不是文件时属于配置错误，不允许静默通过。"""

    completed = run_cli("examples", "--rules", "policies")

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr



def test_check_rules_mode_validates_without_file() -> None:
    """--check-rules 的通过输出里，规则条数必须等于 policies/ 下真实的 .yaml 文件数。

    这里刻意不写死条数：规则语料是会长的（Phase 0 的 1 条 → Phase 5 的 6 条 →
    由 PEP / OWASP 镜像文档提炼出的规则语料）。写死只会让用例随新增规则过期，
    真正的不变量是"报告出来的条数 == 磁盘上的规则文件数"。
    """

    completed = run_cli("--check-rules")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    on_disk = sum(
        1
        for path in (REPO_ROOT / "policies").rglob("*.yaml")
        if not path.name.startswith(".")
    )
    assert f"规则集校验通过，共 {on_disk} 条规则" in completed.stdout


def test_check_rules_mode_fails_on_corrupted_rules(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    root.mkdir()
    (root / "ARCH-001.yaml").write_text("id: ARCH-001\nseverity: fatal\n", encoding="utf-8")

    completed = run_cli("--check-rules", "--rules", workspace_path(root))

    assert completed.returncode == EXIT_ERROR
    assert "severity" in completed.stderr


def test_json_output_matches_policy_decision_contract() -> None:
    completed = run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--json", "--request-id", "req-json")

    assert completed.returncode == EXIT_VIOLATION
    payload = json.loads(completed.stdout)

    # P4/P5 起顶层多了两个**只增不改**的 CLI 包装字段：
    # layer_source（这次的分层从哪来）与 check_volume（这次到底查了多少）；
    # 2026-09-30 裁定又加了 output_schema_version —— 包装层自己的版本轴
    # （1.0 = 追认的"台阶 3c 之前的形状"，1.1 = 第 19 轮形状，1.2 = 台阶 4 加了 reading_context）。
    # 它们属于包装层，不进决策协议载荷 result（决策协议见 SCHEMA_VERSION，1.1）。
    assert set(payload) == {
        "check_volume",
        "context",
        "evidence",
        "exit_code",
        "layer_source",
        "output_schema_version",
        "reading_context",
        "reported_imports",
        "result",
        "rule_set",
    }
    assert payload["output_schema_version"] == OUTPUT_SCHEMA_VERSION
    # Phase 5：--json 里带完整证据（依赖来自显式声明，因为本次传了 --dependencies）
    assert payload["evidence"]["dependencies"][0]["name"] == "repository"
    assert payload["evidence"]["dependencies"][0]["resolution"] == "declared"
    assert payload["evidence"]["served_checkers"] == [
        "forbidden_dependency",
        "missing_docstring",
        "style_lint",
    ]
    assert payload["exit_code"] == EXIT_VIOLATION
    result = payload["result"]
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["decision"] == "block"
    assert result["request_id"] == "req-json"
    assert result["trace_id"] is None
    assert result["required_action"] is None
    # 规则集是会长大的（Phase 0 的 1 条 → 由 PEP / OWASP 镜像提炼出的规则语料）。
    # 这里守住的不变量是"每条规则恰好进 matched 或 skipped 之一"——
    # 规则悄悄从两份清单里消失，才是真正要挡的事；写死清单只会随新增规则过期。
    rules = load_rule_set(default_rule_dirs(REPO_ROOT), repo_root=REPO_ROOT)
    matched = list(result["matched_rules"])
    skipped_ids = [item["rule_id"] for item in result["skipped_rules"]]
    assert sorted(matched + skipped_ids) == sorted(rules.ids)
    assert len(set(matched)) == len(matched) and len(set(skipped_ids)) == len(skipped_ids)
    # 这个上下文（python / layer=controller / 有依赖声明）下，绑定层与语言的规则必须命中。
    assert {"ARCH-001@1", "DOC-001@1", "STYLE-001@1", "STYLE-002@1"} <= set(matched)
    # TESTING-001/002 只在有变更集（operation=create/edit）时参与判断，本次没有 → 必须写明被跳过。
    assert {"TESTING-001@1", "TESTING-002@1"} <= set(skipped_ids)
    assert result["policy_version"] == "decision-1.1"
    assert result["rule_set_hash"] == payload["rule_set"]["identity"]
    violation = result["violations"][0]
    assert violation["rule_id"] == "ARCH-001"
    assert violation["rule_version"] == 1
    assert violation["severity"] == "error"
    assert violation["evidence"] == {
        "kind": "dependency",
        "subject": BAD_EXAMPLE,
        "value": "repository",
        "file": BAD_EXAMPLE,
        "detail": "layer=controller 直接依赖 repository",
    }
    # CLI 报出来的规则清单必须与 Loader 加载到的一模一样（顺序也一致）：
    # 不一致意味着 CLI 少读/多读了一个规则目录，或规则集被中途替换过。
    assert payload["rule_set"]["ids"] == list(rules.ids)
    assert payload["rule_set"]["schema_version"] == SCHEMA_VERSION
    assert payload["rule_set"]["identity"].startswith("sha256:")
    assert payload["context"]["file"] == BAD_EXAMPLE
    assert payload["context"]["layer"] == "controller"


def test_json_result_is_a_consumable_protocol_payload() -> None:
    """result 必须能被 parse_decision 原样消费，未知版本则拒绝。"""

    allowed = json.loads(run_cli(GOOD_EXAMPLE, "--dependencies", "service", "--json").stdout)
    blocked = json.loads(run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--json").stdout)

    parsed_allowed = parse_decision(allowed["result"])
    parsed_blocked = parse_decision(blocked["result"])

    assert parsed_allowed.decision is Decision.ALLOW
    assert "ARCH-001" + "@" + "1" in parsed_allowed.matched_rules
    assert parsed_blocked.decision is Decision.BLOCK
    assert parsed_blocked.to_decision_dict() == blocked["result"]

    with pytest.raises(ProtocolError):
        parse_decision({**blocked["result"], "schema_version": "9.9"})


def test_trace_id_is_recorded_and_not_invented() -> None:
    without = json.loads(run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--json").stdout)
    with_trace = json.loads(
        run_cli(
            BAD_EXAMPLE,
            "--dependencies",
            "repository",
            "--json",
            "--trace-id",
            "trace-456",
            "--task",
            "add order creation API",
        ).stdout
    )

    assert without["result"]["trace_id"] is None
    assert with_trace["result"]["trace_id"] == "trace-456"
    assert with_trace["context"]["task"] == "add order creation API"


def test_python_module_entry_points_agree() -> None:
    """python -m policy 与 python -m policy.check 必须给出同一条结论。

    台阶 4 之后这两个入口的 stdout 里各有一份 reading_context，其中 run.id / run.started_at
    每次运行都不同——所以这里也走 normalise_run_identity：**除那两个字段外**逐字节相同。
    """

    env = _env()
    args = [BAD_EXAMPLE, "--dependencies", "repository", "--json", "--request-id", "req-entry"]
    first = subprocess.run(
        [sys.executable, "-m", "policy", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    second = run_cli(*args)

    assert first.returncode == second.returncode == EXIT_VIOLATION, first.stderr
    first_text, _first_run = normalise_run_identity(first.stdout)
    second_text, _second_run = normalise_run_identity(second.stdout)
    assert first_text == second_text

    # 两个入口都真的带上了 reading_context，并且都是 cli：这条协议不是"某个入口专有"。
    payload = json.loads(second.stdout)
    assert payload["reading_context"]["source"] == "cli"


def test_run_function_is_reentrant(capsys: pytest.CaptureFixture[str]) -> None:
    code = run([BAD_EXAMPLE, "--dependencies", "repository", "--request-id", "req-run"])
    first = capsys.readouterr().out
    code_again = run([BAD_EXAMPLE, "--dependencies", "repository", "--request-id", "req-run"])
    second = capsys.readouterr().out

    assert code == code_again == EXIT_VIOLATION
    assert first == second


def test_default_rule_dirs_point_at_repository_policies() -> None:
    """默认规则目录 = 仓库的 policies/，且**目录里的每一个 .yaml 都真的被加载**。

    这里刻意不写死规则清单：规则语料是会长大的数据（本仓库的规则来自 PEP 与 OWASP 镜像文档），
    写死清单的用例只会随着新增规则过期，然后在"改断言"里失去意义。
    真正要守住的不变量是"磁盘上的规则文件"与"加载出来的规则"一一对应——
    漏加载一条规则等于那条规则静默失效，必须红。
    """

    directories = default_rule_dirs(REPO_ROOT)

    assert directories == (REPO_ROOT / "policies",)
    rules = load_rule_set(directories, repo_root=REPO_ROOT)

    on_disk = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "policies").rglob("*.yaml")
        if not path.name.startswith(".")
    }
    assert set(rules.source_paths) == on_disk
    assert len(rules.rules) == len(on_disk)

    # 六条 Phase 0–5 的基线规则必须一直在：它们是有正反例夹具的锚点。
    assert {
        "ARCH-001@1",
        "DOC-001@1",
        "STYLE-001@1",
        "STYLE-002@1",
        "TESTING-001@1",
        "TESTING-002@1",
    } <= set(rules.ids)


def test_repository_example_dependencies_are_declared() -> None:
    """示例文件必须自带可重放的依赖声明，避免 CLI 示例与规则漂移。"""

    bad = (REPO_ROOT / BAD_EXAMPLE).read_text(encoding="utf-8")
    good = (REPO_ROOT / GOOD_EXAMPLE).read_text(encoding="utf-8")

    assert "--dependencies repository" in bad
    assert "--dependencies service" in good


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("examples/bad_controller.py", "controller"),
        ("src/order/order_service.py", "service"),
        ("src/order/order_repository.py", "repository"),
        ("src/order/models.py", "model"),
        ("src/order/registry.py", "unknown"),
        (None, "unknown"),
    ],
)
def test_infer_layer(name: str | None, expected: str) -> None:
    assert infer_layer(name) == expected


def test_parse_dependencies_is_canonical() -> None:
    assert parse_dependencies(None) == ()
    assert parse_dependencies("") == ()
    assert parse_dependencies(" Repository , service ,, ") == ("repository", "service")


def test_python_imports_reports_top_level_modules() -> None:
    source = "import os\nfrom examples import service\nfrom . import local\nimport a.b.c\n"

    assert python_imports(source) == ("a", "examples", "os")
    assert python_imports("def broken(:\n") == ()


def test_exit_code_for_maps_decision_to_code() -> None:
    violation = Violation(
        rule_id="ARCH-001",
        rule_version=1,
        severity=Severity.ERROR,
        message="Controller 必须通过 Service 访问 Repository。",
        evidence=Evidence(kind="dependency", subject="a.py", value="repository"),
    )
    blocked = ValidationResult(
        decision=Decision.BLOCK, request_id="req-1", violations=(violation,)
    )
    allowed = ValidationResult(decision=Decision.ALLOW, request_id="req-1")

    assert exit_code_for(allowed) == EXIT_ALLOWED
    assert exit_code_for(blocked) == EXIT_VIOLATION


# --------------------------------------------------------------------------- A2：target 解析（canonical 口径）


PROJECT = "tests/fixtures/validators/project"


def missing_target_blockers(payload: dict) -> list:
    """只挑"目标文件没被定位到"这一类阻断点：它是 target 解析口径分叉时的可观察差异。

    窄口径（只跑 py.*）下还会有"没有验证器为某个 checker 提供证据"的失败关闭阻断点，
    那是**预期的**，与 target 解析无关。
    """

    return [
        item
        for item in payload["evidence"]["blockers"]
        if "目标文件不存在" in str(item.get("reason", ""))
    ]


def test_prefixed_target_is_resolved_against_the_workspace() -> None:
    """带工作区前缀的路径先按 --workspace 找文件，再归一化成工作区相对路径。

    这是 target 解析的 canonical 口径（validators.cli 现在跟随它）：
    "--workspace X" 配上 "X/某文件" 这种写法不该在上下文里留下前缀。
    """

    completed = run_cli(
        PROJECT + "/src/shop/order_controller.py",
        "--layer",
        "controller",
        "--workspace",
        PROJECT,
        "--validators",
        "py.source,py.ast,py.depgraph",
        "--request-id",
        "req-a2-canonical",
        "--json",
    )

    assert completed.returncode != EXIT_ERROR, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["context"]["file"] == "src/shop/order_controller.py"
    assert missing_target_blockers(payload) == []


def test_config_root_does_not_move_the_workspace(tmp_root: Path) -> None:
    """--config-root 只决定 validation/ 配置在哪；默认工作区仍然是仓库根。"""

    write_validation_config(tmp_root)
    completed = run_cli(
        PROJECT + "/src/shop/order_controller.py",
        "--layer",
        "controller",
        "--config-root",
        workspace_path(tmp_root),
        "--validators",
        "py.source,py.ast,py.depgraph",
        "--request-id",
        "req-a2-config-root",
        "--json",
    )

    assert completed.returncode != EXIT_ERROR, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["context"]["file"] == PROJECT + "/src/shop/order_controller.py"
    assert missing_target_blockers(payload) == []


# --------------------------------------------------------------- P4：测试路径收敛到平台数据


def write_shipment_controller_test(workspace: Path, relative: str) -> str:
    """在临时工作区里造一个"文件名带生产层名、但按平台数据是测试"的真文件。

    P4 的原形就是这种文件：`tests/test_shipment_controller.py` 在受治理 Hook 路径上
    layer=test（dsh 的 test_paths / test_layer 在加载期自证），在验证器路径上却因为
    `infer_layer` 按文件名猜成 controller，被 ARCH-001 拦下。用例必须用真文件——
    只测一个纯函数挡不住"两条路径两个结论"。
    """

    target = workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        chr(10).join(
            [
                '"""出库控制器测试：用真实仓储组装对象图，而不是手写替身。"""',
                "",
                "",
                "def test_shipment_controller_assembles_the_real_repository() -> None:",
                '    """真实装配：controller 拿到的仓储是真的仓储对象。"""',
                "",
                '    wiring = {"controller": "shipment", "repository": "real"}',
                '    assert wiring["repository"] == "real"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return relative


def test_a_platform_test_path_is_no_longer_guessed_as_a_production_layer(tmp_root: Path) -> None:
    """P4：缺 --layer 时，平台数据说是测试的文件必须按 test 层判定。

    判据不是"看起来对不对"，而是"与显式 --layer test 逐字同一条判定"：
    缺 --layer 的那次不许再多出任何一条参与判定的规则。
    """

    from adapters.dsh.adapter import load_config as load_dsh_config

    workspace = tmp_root / "ws"
    relative = write_shipment_controller_test(workspace, "tests/test_shipment_controller.py")
    implicit = run_cli(
        relative,
        "--workspace",
        workspace_path(workspace),
        "--dependencies",
        "repository",
        "--request-id",
        "req-p4-layer",
        "--json",
    )
    explicit = run_cli(
        relative,
        "--workspace",
        workspace_path(workspace),
        "--layer",
        "test",
        "--dependencies",
        "repository",
        "--request-id",
        "req-p4-layer",
        "--json",
    )

    assert implicit.returncode != EXIT_ERROR, implicit.stderr
    payload = json.loads(implicit.stdout)
    reference = json.loads(explicit.stdout)

    assert payload["context"]["layer"] == "test"
    assert payload["layer_source"] == "platform_test_layout"
    assert reference["layer_source"] == "declared"
    # 同一个文件、同一次判定：缺 --layer 与显式 --layer test 的结果必须逐字相同
    assert payload["context"] == reference["context"]
    assert payload["result"] == reference["result"]
    assert payload["exit_code"] == reference["exit_code"]
    assert "ARCH-001" + "@" + "1" not in payload["result"]["matched_rules"]
    # 与受治理 Hook 路径同向：示例 Adapter 配置对同一条路径也解析成它的 test_layer
    hook_config = load_dsh_config(REPO_ROOT / "examples" / "dsh" / "dsh-adapter.yaml")
    assert hook_config.layer_resolution(relative).layer == hook_config.test_layer == "test"


def test_text_output_names_where_the_layer_came_from(tmp_root: Path) -> None:
    """文本输出按来源改口径：平台数据判定时不许再说"由文件名推断"。"""

    workspace = tmp_root / "ws"
    relative = write_shipment_controller_test(workspace, "tests/test_shipment_controller.py")
    platform = run_cli(
        relative, "--workspace", workspace_path(workspace), "--dependencies", "repository"
    )
    platform_line = next(
        line for line in platform.stdout.splitlines() if line.startswith("layer: ")
    )
    assert platform_line.startswith("layer: test")
    assert "test_patterns" in platform_line
    assert "由文件名推断" not in platform_line

    guessed = run_cli(BAD_EXAMPLE, "--dependencies", "repository")
    guessed_line = next(
        line for line in guessed.stdout.splitlines() if line.startswith("layer: ")
    )
    assert guessed_line.startswith("layer: controller")
    assert "由文件名推断" in guessed_line


def test_layer_source_is_declared_when_the_caller_says_so() -> None:
    completed = run_cli(
        BAD_EXAMPLE, "--layer", "controller", "--dependencies", "repository", "--json"
    )

    payload = json.loads(completed.stdout)

    assert payload["layer_source"] == "declared"
    assert payload["context"]["layer"] == "controller"


def test_layer_source_is_a_filename_guess_without_platform_data() -> None:
    """不在平台 test_patterns 里的路径行为不变：还是按文件名猜，并且说清楚是猜的。"""

    completed = run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--json")

    payload = json.loads(completed.stdout)

    assert payload["layer_source"] == "filename_guess"
    assert payload["context"]["layer"] == "controller"


# --------------------------------------------------------------------------- P5：检查量摘要与缺维度


def test_missing_operation_is_visible_as_an_incomplete_check() -> None:
    """缺 --operation：判定可以照旧 allow，但读数必须说清有几条规则没被查。"""

    completed = run_cli(
        GOOD_EXAMPLE, "--layer", "controller", "--dependencies", "service", "--json"
    )

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    volume = json.loads(completed.stdout)["check_volume"]

    assert volume["complete"] is False
    assert volume["missing_dimensions"] == ["operation"]
    assert volume["blocking_capable_skipped"] >= 2
    assert volume["effective_rule_count"] < volume["rule_count"]
    assert volume["skipped_by_reason"]["missing_dimension"] >= 2
    # 每条被跳过的规则恰好落进一个桶：计数必须等于 skipped_rule_count
    assert sum(volume["skipped_by_reason"].values()) == volume["skipped_rule_count"]
    assert volume["skipped_by_severity"]["error"] >= 2
    assert "skipped ≠ passed" in volume["note"]


def test_declaring_the_operation_completes_the_check() -> None:
    """给了 --operation：不再缺维度，complete 为真——配置错误与判定是两回事。"""

    completed = run_cli(
        BAD_EXAMPLE,
        "--layer",
        "controller",
        "--dependencies",
        "repository",
        "--operation",
        "read",
        "--json",
    )
    volume = json.loads(completed.stdout)["check_volume"]

    assert volume["complete"] is True
    assert volume["missing_dimensions"] == []
    assert volume["skipped_by_reason"]["missing_dimension"] == 0


def test_text_output_flags_the_incomplete_check() -> None:
    completed = run_cli(GOOD_EXAMPLE, "--layer", "controller", "--dependencies", "service")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    incomplete = [
        line for line in completed.stdout.splitlines() if line.startswith("INCOMPLETE:")
    ]

    assert len(incomplete) == 1
    assert "operation" in incomplete[0]
    assert "--operation" in incomplete[0]


def test_changed_without_operation_is_a_config_error() -> None:
    """自相矛盾才失败关闭：声明了变更集却不说是什么操作，判定必然是残缺的。"""

    completed = run_cli(BAD_EXAMPLE, "--layer", "controller", "--changed", BAD_EXAMPLE)

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr
    assert "--operation" in completed.stderr
    assert completed.stdout == ""


def test_missing_operation_alone_stays_executable() -> None:
    """标定过的边界：完全不给 --operation 的既有命令必须还能跑。

    README 与 60+ 处文档写的都是 `python -m policy.check <file> --layer X`；
    把"没声明"也做成退出码 2，会把这些命令全变成配置错误，还会把文档里的
    allow 例子变成 block（`--operation edit` 会激活 TESTING-001）。
    """

    completed = run_cli(GOOD_EXAMPLE, "--layer", "controller", "--dependencies", "service")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    assert "config error" not in completed.stderr


def test_changed_with_operation_is_a_decision_not_a_config_error() -> None:
    """给了 --operation 之后，--changed 不再触发失败关闭：退出码只能来自判定。"""

    completed = run_cli(
        PROJECT + "/src/shop/order_service.py",
        "--workspace",
        PROJECT,
        "--layer",
        "service",
        "--operation",
        "edit",
        "--changed",
        "src/shop/order_service.py",
        "--validators",
        "py.source,py.ast,py.depgraph",
        "--json",
    )

    assert completed.returncode in (EXIT_ALLOWED, EXIT_VIOLATION), completed.stderr
    assert "自相矛盾" not in completed.stderr
    assert json.loads(completed.stdout)["check_volume"]["complete"] is True


def test_json_reading_context_names_the_entry_the_tree_and_the_declarations() -> None:
    """台阶 4：这份包装要说得出"哪个入口、哪棵树、哪一套声明"（21 号 §2.1）。

    21 号 §5 的 R2 预注册：与非 CLI 路径相比，差集**只有两条**
    （reading_context 新增 + output_schema_version 1.1 → 1.2）；这里把其中的
    "同一个值来源"钉成一条可执行断言——声明摘要必须与证据段里那一份逐字符相同。
    """

    completed = run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--json", "--request-id", "req-rc")

    payload = json.loads(completed.stdout)
    context = payload["reading_context"]
    assert context["source"] == "cli", "入口是显式传进来的，不猜"
    assert context["tree"]["status"] == "available"
    assert context["tree"]["scope"] == "workspace"
    assert context["tree"]["digest"].startswith("sha256:")
    assert len(context["tree"]["revision"]) == 40
    assert context["host"]["sandbox"] == "unknown", "CLI 不探测沙箱（探测要有副作用），不猜"
    assert context["run"]["id"] and context["run"]["started_at"].endswith("Z")

    declarations = context["declarations"]
    assert declarations["adapter_config"] == {"status": "not_applicable"}, "CLI 路径不读 adapter 配置"
    assert declarations["registry"]["path"] == "validation/validators.yaml"
    assert not Path(declarations["registry"]["path"]).is_absolute()
    # 与证据段**同一个值来源**：同一份文件、两条路径，必须给出同一个字符串。
    assert declarations["registry"]["digest"] == payload["evidence"]["configs"]["registry"]
    assert declarations["test_layout"]["digest"] == payload["evidence"]["configs"]["test_layout"]

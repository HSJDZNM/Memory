"""题库 run-record 采集器（bank/run-record/collect.py）的用例。

覆盖（按交付验收项）：

1. 三维全 recorded -> 退出 0，顶层 10 键、形状齐全、无绝对路径；
2. 同一假输入两次运行 -> run-record 逐字节相同；
3. --determinism 记录两次 stdout 逐字节相同；两次不同只改读数、不改退出码；
4. T：runner 退出 2 / case_ids 与声明不符 / 子进程超时 -> unavailable；
5. C：policy.check 非 JSON / layer_source 不是 declared -> unavailable 并点名；
6. 输入：树不存在、layers.yaml 缺层、--task 与 task_id 不符 -> 退出 2；
7. --dry-run 不调用子进程、不写盘；
8. 载荷里出现绝对路径 -> 拒绝写盘（退出 1 且没有产物）；
9. platform_generation：缺 --arm-config 时四个角色 unavailable（不是假哈希），
   平台版本常数等于 adapters.dsh 的真实常量；
10. --arm-config 的四角色摘要与缺项点名；
11. process 只抽允许键（run.json 的 streams / diff / 绝对路径都不进载荷）；
12. start：git 读不到时 head / worktree_clean 写 unknown。

全部注入假 runner（返回预设 CompletedProcess）与假 git probe：**不跑真 runner / pytest，
不依赖 .tmp**。测试输入（树 / 任务根 / scoring / layers / interfaces / arm-config / run-json）
都建在 pytest 的 tmp_path 下。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from adapters.dsh import batch_ledger, hooks

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECT = (
    REPO_ROOT
    / "docs"
    / "project"
    / "engineering-policy-platform"
    / "testing"
    / "ab"
    / "bank"
    / "run-record"
    / "collect.py"
)

TASK_ID = "bank-selftest"
FILE_SET = ["src/shop/notification.py", "tests/test_notification.py"]
CHANGED = ["README.md", "src/shop/notification.py", "tests/test_notification.py"]
CASE_IDS = ["T01", "T02", "EN1", "I1"]
PREDICATE_IDS = ["A1", "A2"]
LAYERS = {FILE_SET[0]: "service", FILE_SET[1]: "test"}
HEAD = "1" * 40
RULE_SET_HASH = "sha256:" + "a" * 64
TOP_LEVEL_KEYS = {
    "schema_version",
    "arm",
    "tree",
    "start",
    "platform_generation",
    "dimensions",
    "summary",
    "commands",
    "process",
    "task",
}


def _load_module():
    """按路径加载被测脚本（docs/ 不是包）。"""

    spec = importlib.util.spec_from_file_location("bank_run_record_under_test", COLLECT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


# ---------------------------------------------------------------------------
# 夹具输入
# ---------------------------------------------------------------------------
def _scoring_payload(*, case_ids: list[str] | None = None) -> dict:
    return {
        "schema_id": "bank-scoring/2",
        "version": "2",
        "task_id": TASK_ID,
        "weights": {"T": 40, "C": 30, "A": 30},
        "dimension_t": {
            "tool": "hidden/runner.py",
            "status": "frozen",
            "total": len(case_ids or CASE_IDS),
            "case_ids": list(case_ids or CASE_IDS),
        },
        "dimension_c": {
            "tool": ".venv/Scripts/python.exe -m policy.check（本仓库的判定入口；不复制实现）",
            "config_root": "仓库根（冻结；所有臂的 C 读数用同一个 config root）",
            "env": {"PYTHONPATH": "src"},
            "file_set": {"count": len(FILE_SET), "paths": list(FILE_SET)},
            "changed_files": {"count": len(CHANGED), "paths": list(CHANGED)},
        },
        "dimension_a": {
            "tool": "tools/structure_metrics.py",
            "layers": "layers.yaml",
            "interfaces": "interfaces.yaml",
            "predicates": [{"id": predicate_id} for predicate_id in PREDICATE_IDS],
        },
    }


def _setup(
    tmp_path: Path,
    *,
    tree_exists: bool = True,
    drop_layer: str | None = None,
    case_ids: list[str] | None = None,
) -> dict:
    """在 tmp_path 下落一套与冻结任务包同形的声明文件（repo / task / tree 三层）。"""

    repo = tmp_path / "repo"
    (repo / "validation").mkdir(parents=True)
    (repo / "validation" / "test-layout.yaml").write_text(
        "test_patterns: {}\n", encoding="utf-8"
    )
    (repo / "tools").mkdir()
    (repo / "tools" / "structure_metrics.py").write_text("", encoding="utf-8")

    task = repo / "tasks" / TASK_ID
    (task / "hidden").mkdir(parents=True)
    (task / "hidden" / "runner.py").write_text("", encoding="utf-8")

    layers = dict(LAYERS)
    if drop_layer is not None:
        layers.pop(drop_layer)
    (task / "layers.yaml").write_text(
        yaml.safe_dump(layers, sort_keys=True), encoding="utf-8"
    )
    (task / "interfaces.yaml").write_text(
        yaml.safe_dump({FILE_SET[0]: 3}, sort_keys=True), encoding="utf-8"
    )
    (task / "scoring.yaml").write_text(
        yaml.safe_dump(
            _scoring_payload(case_ids=case_ids), sort_keys=False, allow_unicode=True
        ),
        encoding="utf-8",
    )

    tree = repo / "tree"
    if tree_exists:
        for relative in FILE_SET:
            path = tree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x = 1\n", encoding="utf-8")

    return {"repo": repo, "task": task, "tree": tree}


def _argv(setup: dict, out: Path, *extra: str) -> list[str]:
    return [
        "--task",
        TASK_ID,
        "--task-root",
        str(setup["task"]),
        "--tree",
        str(setup["tree"]),
        "--arm",
        "A",
        "--out",
        str(out),
        *extra,
    ]


def _completed(argv: list[str], returncode: int, stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=argv, returncode=returncode, stdout=stdout, stderr="")


def _git(repo: Path) -> tuple[str, bool]:
    """假 git probe：固定 head + 干净工作树（不跑真 git）。"""

    return HEAD, True


def _git_unavailable(repo: Path) -> None:
    """假 git probe：读不到。"""

    return None


def _t_payload(case_ids: list[str] | None = None, passed: int | None = None) -> dict:
    ids = list(case_ids if case_ids is not None else CASE_IDS)
    total = len(ids)
    if passed is None:
        passed = total
    cases = [
        {"id": case_id, "pass": index < passed, "detail": "ok"}
        for index, case_id in enumerate(ids)
    ]
    return {
        "schema_version": "1.0",
        "tree": "<outside-workspace>",
        "cases": cases,
        "summary": {"passed": passed, "total": total},
    }


def _c_payload(request_id: str) -> dict:
    return {
        "output_schema_version": "1.2",
        "check_volume": {
            "complete": True,
            "blocking_capable_skipped": 0,
            "missing_dimensions": [],
            "rule_count": 43,
        },
        "evidence": {
            "served_checkers": ["style_lint"],
            "selection": {"level": "related", "nodeids": []},
        },
        "exit_code": 0,
        "layer_source": "declared",
        "result": {
            "schema_version": "1.1",
            "decision": "allow",
            "request_id": request_id,
            "trace_id": None,
            "rule_set_hash": RULE_SET_HASH,
            "matched_rules": ["DOC-001@1"],
            "skipped_rules": [{"rule_id": "ARCH-001", "reasons": ["scope"]}],
            "violations": [],
            "pending_findings": [],
            "required_action": None,
            "policy_version": "decision-1.1",
        },
    }


def _a_payload(passed: int | None = None) -> dict:
    if passed is None:
        passed = len(PREDICATE_IDS)
    predicates = [
        {
            "id": predicate_id,
            "name": predicate_id,
            "status": "pass" if index < passed else "fail",
            "detail": {},
        }
        for index, predicate_id in enumerate(PREDICATE_IDS)
    ]
    return {
        "schema_version": "1.1",
        "workspace_scope": {},
        "predicates": predicates,
        "summary": {
            "passed": sum(1 for item in predicates if item["status"] == "pass"),
            "failed": sum(1 for item in predicates if item["status"] == "fail"),
        },
    }


class FakeRunner:
    """可注入的 runner：按 argv 识别 T / A / C，返回预设载荷（不跑子进程）。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.t_returncode = 0
        self.t_payload = _t_payload()
        self.t_second_payload: dict | None = None
        self.a_payload = _a_payload()
        self.a_returncode = 0
        self.c_invalid_json: set[str] = set()
        self.c_payloads: dict[str, dict] = {}
        self.timeout_on: str | None = None
        self._t_calls = 0

    def __call__(self, argv, *, cwd, env, timeout):  # noqa: ANN001 - 测试替身
        argv = [str(item) for item in argv]
        self.calls.append(argv)
        if self.timeout_on is not None and any(
            str(item).endswith(self.timeout_on) for item in argv
        ):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)
        if "policy.check" in argv:
            index = argv.index("policy.check")
            relative = argv[index + 1]
            request_id = argv[argv.index("--request-id") + 1]
            if relative in self.c_invalid_json:
                return _completed(argv, 0, "this is not json")
            payload = self.c_payloads.get(relative) or _c_payload(request_id)
            body = json.dumps(payload, ensure_ascii=False)
            return _completed(argv, int(payload["exit_code"]), body)
        if any(token.endswith("structure_metrics.py") for token in argv):
            return _completed(argv, self.a_returncode, json.dumps(self.a_payload))
        if any(token.endswith("runner.py") for token in argv):
            self._t_calls += 1
            if self._t_calls > 1 and self.t_second_payload is not None:
                return _completed(argv, 0, json.dumps(self.t_second_payload))
            return _completed(argv, self.t_returncode, json.dumps(self.t_payload))
        raise AssertionError(f"未识别的子进程命令：{argv}")


def _read_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(setup: dict, out: Path, *extra: str, runner: FakeRunner | None = None, git=_git) -> int:
    return MODULE.run(
        _argv(setup, out, *extra),
        runner=runner or FakeRunner(),
        repo_root=setup["repo"],
        git=git,
    )


# ---------------------------------------------------------------------------
# 1. 三维全 recorded 的形状
# ---------------------------------------------------------------------------
def test_all_dimensions_recorded_shape_and_no_absolute_paths(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"

    code = _run(setup, out)

    assert code == 0
    record = _read_record(out)
    assert set(record) == TOP_LEVEL_KEYS
    assert record["schema_version"] == "1.0"
    assert record["task"] == TASK_ID
    assert record["arm"] == "A"
    assert record["tree"] == "tree"
    assert record["start"] == {"head": HEAD, "worktree_clean": True}
    assert record["summary"]["all_recorded"] is True
    assert record["summary"]["unavailable_dimensions"] == []
    assert record["dimensions"]["T"]["summary"] == {"passed": 4, "total": 4}
    assert record["dimensions"]["T"]["declared_total"] == 4
    assert record["dimensions"]["T"]["failed_ids"] == []
    assert record["dimensions"]["C"]["summary"]["files"] == len(FILE_SET)
    assert record["dimensions"]["C"]["summary"]["check_volume_complete"] == len(FILE_SET)
    assert record["dimensions"]["C"]["summary"]["decisions"] == {"allow": len(FILE_SET)}
    assert record["dimensions"]["C"]["files"][0]["selection"] == {"level": "related"}
    assert record["dimensions"]["C"]["files"][0]["served_checkers"] == ["style_lint"]
    assert record["dimensions"]["C"]["files"][0]["skipped_rule_ids"] == ["ARCH-001"]
    assert record["dimensions"]["A"]["summary"] == {"passed": 2, "total": 2}
    assert record["dimensions"]["A"]["predicates"] == {"A1": "pass", "A2": "pass"}
    assert [item["id"] for item in record["commands"]] == [
        "T",
        "A",
        f"C:{FILE_SET[0]}",
        f"C:{FILE_SET[1]}",
    ]
    assert record["commands"][0]["exit_code"] == 0
    assert record["commands"][2]["argv"][:3] == ["<python>", "-m", "policy.check"]
    assert f"{TASK_ID}-A-src-shop-notification-py" in record["commands"][2]["argv"]
    assert record["process"]["status"] == "unavailable"
    assert record["process"]["reason"] == "not_provided"
    assert record["platform_generation"]["host"]["entry"] == "headless"

    text = out.read_text(encoding="utf-8")
    assert str(tmp_path) not in text
    assert not re.search(r"[A-Za-z]:[\\/]", text), "run-record 里出现了绝对路径"
    assert not Path(record["tree"]).is_absolute()


# ---------------------------------------------------------------------------
# 2. 逐字节确定
# ---------------------------------------------------------------------------
def test_same_inputs_produce_byte_identical_record(tmp_path):
    setup = _setup(tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    assert _run(setup, first) == 0
    assert _run(setup, second) == 0

    assert first.read_bytes() == second.read_bytes()


# ---------------------------------------------------------------------------
# 3. --determinism：两次相同 / 两次不同
# ---------------------------------------------------------------------------
def test_determinism_flag_records_identical_t_runs(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()

    code = _run(setup, out, "--determinism", runner=fake)

    assert code == 0
    record = _read_record(out)
    assert record["dimensions"]["T"]["determinism"] == {
        "checked": True,
        "runs": 2,
        "stdout_byte_identical": True,
        "exit_code_identical": True,
    }
    assert [item["id"] for item in record["commands"]][-1] == "T:rerun"
    assert sum(1 for item in fake.calls if any(arg.endswith("runner.py") for arg in item)) == 2


def test_different_second_run_is_a_reading_not_a_failed_collection(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.t_second_payload = _t_payload(passed=3)

    code = _run(setup, out, "--determinism", runner=fake)

    assert code == 0, "两次读数不同是读数，不是「有维度没采到」"
    record = _read_record(out)
    determinism = record["dimensions"]["T"]["determinism"]
    assert determinism["checked"] is True
    assert determinism["stdout_byte_identical"] is False
    assert determinism["runs"] == 2
    assert record["dimensions"]["T"]["status"] == "recorded"


def test_determinism_not_checked_without_the_flag(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"

    assert _run(setup, out) == 0

    record = _read_record(out)
    assert record["dimensions"]["T"]["determinism"] == {
        "checked": False,
        "runs": 1,
        "stdout_byte_identical": None,
        "exit_code_identical": None,
    }


# ---------------------------------------------------------------------------
# 4. T 的不可用形态
# ---------------------------------------------------------------------------
def test_runner_exit_2_marks_t_unavailable_and_run_exit_1(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.t_returncode = 2

    code = _run(setup, out, runner=fake)

    assert code == 1
    record = _read_record(out)
    assert record["dimensions"]["T"]["status"] == "unavailable"
    assert record["dimensions"]["T"]["exit_code"] == 2
    assert record["dimensions"]["T"]["reason"] == "runner_cannot_run"
    assert record["summary"]["T"]["passed"] is None
    assert record["summary"]["unavailable_dimensions"] == ["T"]
    assert "T 维度不可用" in capsys.readouterr().err


def test_case_ids_mismatch_marks_t_unavailable(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.t_payload = _t_payload(case_ids=["T01", "T02", "EN1", "X1"])

    code = _run(setup, out, runner=fake)

    assert code == 1
    record = _read_record(out)
    assert record["dimensions"]["T"]["status"] == "unavailable"
    assert record["dimensions"]["T"]["reason"] == "case_ids_mismatch"
    detail = record["dimensions"]["T"]["detail"]
    assert "I1" in detail and "X1" in detail
    assert "case_ids_mismatch" in capsys.readouterr().err


def test_timeout_marks_t_unavailable_and_exit_1(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.timeout_on = "runner.py"

    code = _run(setup, out, "--timeout-seconds", "1", runner=fake)

    assert code == 1
    record = _read_record(out)
    assert record["dimensions"]["T"]["status"] == "unavailable"
    assert record["dimensions"]["T"]["reason"] == "timeout"
    assert record["dimensions"]["T"]["exit_code"] is None
    assert record["commands"][0]["exit_code"] is None


# ---------------------------------------------------------------------------
# 5. C 的不可用形态与点名
# ---------------------------------------------------------------------------
def test_policy_check_non_json_names_file_and_exits_1(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.c_invalid_json = {FILE_SET[0]}

    code = _run(setup, out, runner=fake)

    assert code == 1
    captured = capsys.readouterr()
    assert FILE_SET[0] in captured.err
    record = _read_record(out)
    assert record["dimensions"]["C"]["status"] == "unavailable"
    assert record["dimensions"]["C"]["reason"] == "invalid_payload"
    assert record["dimensions"]["C"]["invalid_files"] == [FILE_SET[0]]
    assert record["summary"]["C"]["files"] is None


def test_layer_source_not_declared_marks_c_unavailable(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    payload = _c_payload("fixed")
    payload["layer_source"] = "filename_guess"
    fake.c_payloads = {FILE_SET[1]: payload}

    code = _run(setup, out, runner=fake)

    assert code == 1
    record = _read_record(out)
    assert record["dimensions"]["C"]["status"] == "unavailable"
    entries = {entry["file"]: entry for entry in record["dimensions"]["C"]["files"]}
    assert entries[FILE_SET[1]]["status"] == "invalid"
    assert entries[FILE_SET[1]]["error"] == "layer_source_not_declared"
    assert entries[FILE_SET[0]]["status"] == "recorded"
    assert FILE_SET[1] in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 6. 输入声明：退出 2
# ---------------------------------------------------------------------------
def test_missing_tree_exits_2(tmp_path, capsys):
    setup = _setup(tmp_path, tree_exists=False)
    out = tmp_path / "record.json"

    code = _run(setup, out)

    assert code == 2
    assert not out.exists()
    assert "--tree" in capsys.readouterr().err


def test_missing_layer_exits_2(tmp_path, capsys):
    setup = _setup(tmp_path, drop_layer=FILE_SET[1])
    out = tmp_path / "record.json"

    code = _run(setup, out)

    assert code == 2
    assert FILE_SET[1] in capsys.readouterr().err
    assert not out.exists()


def test_task_mismatch_exits_2(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    argv = _argv(setup, out)
    argv[1] = "bank-other"

    code = MODULE.run(argv, runner=FakeRunner(), repo_root=setup["repo"], git=_git)

    assert code == 2
    assert "task_id" in capsys.readouterr().err
    assert not out.exists()


# ---------------------------------------------------------------------------
# 7. --dry-run
# ---------------------------------------------------------------------------
def test_dry_run_does_not_execute_anything(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()

    code = _run(setup, out, "--dry-run", runner=fake)

    captured = capsys.readouterr()
    assert code == 0
    assert fake.calls == []
    assert not out.exists()
    assert "[dry-run] T:" in captured.out
    assert captured.out.count("[dry-run]") == 2 + len(FILE_SET)


# ---------------------------------------------------------------------------
# 8. 绝对路径：拒绝写盘
# ---------------------------------------------------------------------------
def test_absolute_path_in_payload_refuses_to_write(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    payload = _c_payload("fixed")
    payload["evidence"]["served_checkers"] = ["/opt/checkers/style"]
    fake.c_payloads = {FILE_SET[0]: payload}

    code = _run(setup, out, runner=fake)

    captured = capsys.readouterr()
    assert code == 1
    assert not out.exists(), "载荷里出现绝对路径时必须拒绝写盘，不留半份产物"
    assert "绝对路径" in captured.err
    assert "/opt/checkers/style" not in captured.err, "拒绝消息不回显泄漏值"


# ---------------------------------------------------------------------------
# 9. platform_generation
# ---------------------------------------------------------------------------
def test_platform_generation_without_arm_config_is_unavailable(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"

    assert _run(setup, out) == 0

    platform = _read_record(out)["platform_generation"]
    assert platform["host"] == {
        "entry": "headless",
        "dsh_runtime": None,
        "dsh_source": "unknown",
        "model": None,
        "sandbox": "unknown",
    }
    for role in ("adapter_config", "registry", "approval", "test_layout"):
        block = platform["declarations"][role]
        assert block["status"] == "unavailable"
        assert block["reason"] == "no_arm_config"
        assert block["path"] is None and block["sha256"] is None
        assert block["candidates"]
    assert platform["notes"] == [
        "host.dsh_runtime: not_declared",
        "host.dsh_source: not_declared",
        "host.model: not_declared",
        "host.sandbox: not_declared",
    ]
    assert platform["batch_ledger_schema_version"] == batch_ledger.BATCH_LEDGER_SCHEMA_VERSION
    assert platform["audit_schema_version"] == hooks.AUDIT_SCHEMA_VERSION


def test_platform_versions_come_from_adapter_constants_not_copies(tmp_path):
    """常数不复制：采集器读到的必须与 adapters.dsh 的常量逐个相等。"""

    versions = MODULE._platform_versions()

    assert versions["batch_ledger_schema_version"] == batch_ledger.BATCH_LEDGER_SCHEMA_VERSION
    assert versions["audit_schema_version"] == hooks.AUDIT_SCHEMA_VERSION


def test_arm_config_declaration_digests_and_missing_role(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    arm = setup["repo"] / "arm"
    arm.mkdir()
    files = {
        "dsh-adapter.yaml": "agent_version: '0.1.5'\n",
        "tool-registry.local.yaml": "schema_version: '1.4'\n",
        "approval.json": "{}\n",
    }
    for name, text in files.items():
        (arm / name).write_text(text, encoding="utf-8")

    code = _run(setup, out, "--arm-config", str(arm))

    assert code == 0
    declarations = _read_record(out)["platform_generation"]["declarations"]
    for role, name in (
        ("adapter_config", "dsh-adapter.yaml"),
        ("registry", "tool-registry.local.yaml"),
        ("approval", "approval.json"),
    ):
        block = declarations[role]
        assert block["status"] == "recorded"
        assert block["path"] == f"arm/{name}"
        assert block["sha256"] == hashlib.sha256((arm / name).read_bytes()).hexdigest()
        assert block["reason"] is None
    layout = declarations["test_layout"]
    assert layout["status"] == "unavailable"
    assert layout["reason"] == "missing_file"
    assert layout["candidates"] == ["test-layout.yaml", "validation/test-layout.yaml"]


def test_arm_config_test_layout_derived_from_registry_root(tmp_path):
    """treatment 的 test-layout 从 dsh-adapter 的 pre_evidence.registry_root 下取。"""

    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    arm = setup["repo"] / "arm"
    arm.mkdir()
    registry = setup["repo"] / "registry"
    layout = registry / "validation" / "test-layout.yaml"
    layout.parent.mkdir(parents=True)
    layout.write_text("schema_version: 2\n", encoding="utf-8")
    (arm / "dsh-adapter.yaml").write_text(
        "pre_evidence:\n  registry_root: %s\n" % registry.as_posix(),
        encoding="utf-8",
    )

    assert _run(setup, out, "--arm-config", str(arm)) == 0

    block = _read_record(out)["platform_generation"]["declarations"]["test_layout"]
    assert block["status"] == "recorded"
    assert block["path"] == "registry/validation/test-layout.yaml"
    assert block["sha256"] == hashlib.sha256(layout.read_bytes()).hexdigest()
    assert block["source"] == "pre_evidence.registry_root"


# ---------------------------------------------------------------------------
# 10. process：只抽允许键
# ---------------------------------------------------------------------------
def test_process_extracts_only_allowed_keys_from_run_json(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    run_json = setup["repo"] / "run.json"
    run_json.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "arm": "A",
                "task": {"id": TASK_ID},
                "host": {"dsh": {"version": "0.2.1", "entry": "C:\\harness\\dsh.cmd"}},
                "sandbox": {"mode": "danger-full-access", "hook_spawn_required": True},
                "exit": {"code": 0, "timeout": False},
                "launch": {"dsh_home": "C:\\harness\\home"},
                "readings": {
                    "records": 3,
                    "decisions": {"allow": 2, "block": 1},
                    "reasons": {"scope_mismatch": 2},
                    "post": {"post_validated": 1},
                    "invalid": ["partial_line:.policy/audit.jsonl"],
                    "streams": {".policy/audit.jsonl": {"path": "C:\\harness\\audit.jsonl"}},
                    "diff": {"created": ["C:\\harness\\x.py"]},
                    "summary_lines": ["arm=A"],
                },
            }
        ),
        encoding="utf-8",
    )

    code = _run(setup, out, "--run-json", str(run_json))

    assert code == 0
    record = _read_record(out)
    process = record["process"]
    assert set(process) == {
        "status",
        "reason",
        "records",
        "decisions",
        "reasons",
        "post",
        "invalid",
        "exit",
        "sandbox",
    }
    assert process["status"] == "recorded"
    assert process["records"] == 3
    assert process["decisions"] == {"allow": 2, "block": 1}
    assert process["reasons"] == {"scope_mismatch": 2}
    assert process["post"] == {"post_validated": 1}
    assert process["invalid"] == ["partial_line:.policy/audit.jsonl"]
    assert process["exit"] == {"code": 0, "timeout": False}
    assert process["sandbox"] == {"mode": "danger-full-access", "hook_spawn_required": True}
    text = out.read_text(encoding="utf-8")
    assert "streams" not in text and "summary_lines" not in text and "launch" not in text
    assert "C:\\\\harness" not in text and "C:/harness" not in text


# ---------------------------------------------------------------------------
# 11. start：git 读不到
# ---------------------------------------------------------------------------
def test_start_is_unknown_when_git_is_unavailable(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"

    assert _run(setup, out, git=_git_unavailable) == 0

    assert _read_record(out)["start"] == {"head": "unknown", "worktree_clean": "unknown"}


def test_start_uses_declared_head_and_keeps_clean_unknown(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    declared = "2" * 40

    assert _run(setup, out, "--head", declared, git=_git_unavailable) == 0

    assert _read_record(out)["start"] == {"head": declared, "worktree_clean": "unknown"}


def test_bad_head_exits_2(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"

    code = _run(setup, out, "--head", "0" * 40)

    assert code == 2
    assert "--head" in capsys.readouterr().err
    assert not out.exists()


# ---------------------------------------------------------------------------
# 12. C 缺读数键 / A 的退出码 1 是读数
# ---------------------------------------------------------------------------
def test_missing_selection_level_marks_c_unavailable(tmp_path, capsys):
    """缺 evidence.selection.level 是「缺键」：C unavailable 且点名这一项。"""

    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    payload = _c_payload("fixed")
    del payload["evidence"]["selection"]
    fake.c_payloads = {FILE_SET[0]: payload}

    code = _run(setup, out, runner=fake)

    assert code == 1
    record = _read_record(out)
    assert record["dimensions"]["C"]["status"] == "unavailable"
    assert record["dimensions"]["C"]["reason"] == "invalid_payload"
    entries = {entry["file"]: entry for entry in record["dimensions"]["C"]["files"]}
    assert entries[FILE_SET[0]]["error"] == "invalid_payload"
    assert "evidence.selection.level" in entries[FILE_SET[0]]["detail"]
    assert FILE_SET[0] in capsys.readouterr().err


def test_a_exit_1_is_a_reading_not_a_failed_collection(tmp_path):
    """A 的退出码 1 = 有谓词 fail：recorded，退出码照记，总退出码仍是 0。"""

    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.a_returncode = 1
    fake.a_payload = _a_payload(passed=1)

    code = _run(setup, out, runner=fake)

    assert code == 0
    record = _read_record(out)
    assert record["dimensions"]["A"]["status"] == "recorded"
    assert record["dimensions"]["A"]["exit_code"] == 1
    assert record["dimensions"]["A"]["summary"] == {"passed": 1, "total": 2}
    assert record["dimensions"]["A"]["failed_ids"] == ["A2"]
    assert record["summary"]["A"]["passed"] == 1


def test_declared_predicate_id_mismatch_marks_a_unavailable(tmp_path):
    """谓词 id 集合与 scoring.yaml 的声明不一致 = 不给读数（工具与判据不同版本）。"""

    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    payload = _a_payload()
    payload["predicates"][1]["id"] = "A9"
    fake.a_payload = payload

    code = _run(setup, out, runner=fake)

    assert code == 1
    record = _read_record(out)
    assert record["dimensions"]["A"]["status"] == "unavailable"
    assert record["dimensions"]["A"]["reason"] == "invalid_payload"
    assert "A2" in record["dimensions"]["A"]["detail"]
    assert "A9" in record["dimensions"]["A"]["detail"]

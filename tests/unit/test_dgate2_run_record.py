"""D 门 2 run-record 采集器（dgate2/run-record/collect.py）的用例。

覆盖（与 task-3 的验收项一一对应）：

1. 三维全 recorded -> 退出 0，载荷形状齐、无绝对路径；
2. 同一假输入两次运行 -> run-record 逐字节相同；
3. T 的 runner 退出 2 -> T.status=unavailable，总结算 1（不许当 0 分）；
4. policy.check 输出非 JSON -> 退出 1 且点名文件；
5. 树目录不存在 -> 退出 2；
6. layers.yaml 缺某个 .py 的层 -> 退出 2（不猜层）；
7. --dry-run -> 退出 0 且不调用子进程；
8. C 计分：一条 error 命中、一条 warning 命中、其余干净 -> 3*6 + 0 + 2 = 20。

另加两条边界：A 的退出码 1 是**读数**（recorded），以及子进程超时 -> unavailable。

全部用可注入的假 runner 返回预设 CompletedProcess：**不跑真子进程、不依赖 .tmp**。
测试输入（树 / config-root / layers / interfaces / scorer）都建在 pytest 的 tmp_path 下。
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECT = (
    REPO_ROOT
    / "docs"
    / "project"
    / "engineering-policy-platform"
    / "testing"
    / "ab"
    / "dgate2"
    / "run-record"
    / "collect.py"
)

CHANGED = [
    "README.md",
    "src/shop/order_audit.py",
    "src/shop/order_controller.py",
    "src/shop/order_service.py",
    "tests/test_audit_demo.py",
    "tests/test_order_audit.py",
    "tests/test_order_controller.py",
    "tests/test_order_service.py",
    "tools/audit_demo.py",
]
PY_FILES = [item for item in CHANGED if item.endswith(".py")]
LAYERS = {
    "src/shop/order_audit.py": "model",
    "src/shop/order_controller.py": "controller",
    "src/shop/order_service.py": "service",
    "tests/test_audit_demo.py": "test",
    "tests/test_order_audit.py": "test",
    "tests/test_order_controller.py": "test",
    "tests/test_order_service.py": "test",
    "tools/audit_demo.py": "composition",
}
RULE_IDS = [f"R-00{index}" for index in range(1, 9)]
RULE_SEVERITIES = ["error", "warning", "error", "error", "error", "warning", "error", "error"]
READING_KEYS = [
    "result.violations（真的报了违规的规则）",
    "result.matched_rules（参与过判定的规则）",
    "result.skipped_rules（没参与判定的规则 + 理由）",
    "result.decision",
    "result.rule_set_hash（规则集 identity）",
    "check_volume",
    "evidence.served_checkers（哪些 checker 真的服务过）",
    "exit_code 与 layer_source",
]
RULE_SET_HASH = "sha256:" + "a" * 64


def _load_module():
    """按路径加载被测脚本（docs/ 不是包）。"""

    spec = importlib.util.spec_from_file_location("dgate2_run_record_under_test", COLLECT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


# ---------------------------------------------------------------------------
# 夹具输入
# ---------------------------------------------------------------------------
def _scorer_payload() -> dict:
    return {
        "schema_id": "dgate2-scorer/1",
        "version": "2",
        "measurement": {
            "file_count": 8,
            "changed_files": {"paths": list(CHANGED)},
            "reading_keys": list(READING_KEYS),
        },
        "rules": {
            "scoring": {"no_violation": 3, "warning_only": 2, "error_hit": 0},
            "items": [
                {
                    "rule_id": rule_id,
                    "rule_version": 1,
                    "severity": severity,
                }
                for rule_id, severity in zip(RULE_IDS, RULE_SEVERITIES, strict=True)
            ],
        },
        "weights": {"a_internal": {"per_predicate": 3}},
    }


def _setup(tmp_path: Path, *, tree_exists: bool = True, drop_layer: str | None = None) -> dict:
    """在 tmp_path 下落一套与冻结包同形的声明文件。"""

    tree = tmp_path / "tree"
    if tree_exists:
        for relative in PY_FILES:
            path = tree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x = 1\n", encoding="utf-8")
    config = tmp_path / "config"
    (config / "validation").mkdir(parents=True, exist_ok=True)

    layers = dict(LAYERS)
    if drop_layer is not None:
        layers.pop(drop_layer)
    layers_path = tmp_path / "layers.yaml"
    layers_path.write_text(yaml.safe_dump(layers, sort_keys=True), encoding="utf-8")
    interfaces_path = tmp_path / "interfaces.yaml"
    interfaces_path.write_text(
        yaml.safe_dump({"src/shop/order_audit.py": 3}, sort_keys=True), encoding="utf-8"
    )
    (tmp_path / "scorer.yaml").write_text(
        yaml.safe_dump(_scorer_payload(), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return {
        "tree": tree,
        "config": config,
        "layers": layers_path,
        "interfaces": interfaces_path,
    }


def _argv(setup: dict, out: Path, *extra: str) -> list[str]:
    return [
        "--tree",
        str(setup["tree"]),
        "--config-root",
        str(setup["config"]),
        "--layers",
        str(setup["layers"]),
        "--interfaces",
        str(setup["interfaces"]),
        "--arm",
        "A",
        "--out",
        str(out),
        *extra,
    ]


def _completed(argv: list[str], returncode: int, stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=argv, returncode=returncode, stdout=stdout, stderr="")


def _t_payload(passed: int = 40) -> dict:
    total = 40
    cases = [
        {"id": f"T{index + 1:02d}", "pass": index < passed, "detail": "ok"}
        for index in range(total)
    ]
    return {
        "schema_version": "1.0",
        "tree": "<outside-workspace>",
        "cases": cases,
        "summary": {"passed": passed, "total": total},
    }


def _a_payload(passed: int = 10) -> dict:
    predicates = [
        {
            "id": f"A{index + 1}",
            "name": f"predicate-{index + 1}",
            "status": "pass" if index < passed else "fail",
            "detail": {},
        }
        for index in range(10)
    ]
    return {
        "schema_version": "1.1",
        "workspace_scope": {},
        "predicates": predicates,
        "summary": {"passed": passed, "failed": 10 - passed},
    }


def _c_payload(
    request_id: str,
    *,
    decision: str = "allow",
    exit_code: int = 0,
    violations: list[dict] | None = None,
    matched: list[str] | None = None,
    skipped: list[str] | None = None,
) -> dict:
    result = {
        "schema_version": "1.1",
        "decision": decision,
        "request_id": request_id,
        "trace_id": None,
        "rule_set_hash": RULE_SET_HASH,
        "matched_rules": matched if matched is not None else [f"{rule}@1" for rule in RULE_IDS],
        "skipped_rules": [
            {"rule_id": rule_id, "reasons": ["scope"]} for rule_id in (skipped or [])
        ],
        "violations": violations or [],
        "pending_findings": [],
        "required_action": None,
        "policy_version": "decision-1.1",
    }
    return {
        "output_schema_version": "1.2",
        "check_volume": {
            "complete": True,
            "blocking_capable_skipped": 0,
            "missing_dimensions": [],
            "rule_count": 43,
        },
        "evidence": {"served_checkers": ["style_lint"]},
        "exit_code": exit_code,
        "layer_source": "declared",
        "result": result,
    }


class FakeRunner:
    """可注入的 runner：按 argv 识别 T / A / C，返回预设载荷（不跑子进程）。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.t_returncode = 0
        self.t_stdout = json.dumps(_t_payload())
        self.a_payload = _a_payload()
        self.a_returncode = 0
        self.c_invalid_json: set[str] = set()
        self.c_payloads: dict[str, dict] = {}
        self.timeout_on: str | None = None

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
            return _completed(
                argv, int(payload["exit_code"]), json.dumps(payload, ensure_ascii=False)
            )
        if any(token.endswith("structure_metrics.py") for token in argv):
            return _completed(argv, self.a_returncode, json.dumps(self.a_payload))
        if any(token.endswith("runner.py") for token in argv):
            return _completed(argv, self.t_returncode, self.t_stdout)
        raise AssertionError(f"未识别的子进程命令：{argv}")


def _read_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. 三维全 recorded
# ---------------------------------------------------------------------------
def test_all_dimensions_recorded_shape_and_no_absolute_paths(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()

    code = MODULE.run(_argv(setup, out), runner=fake)

    assert code == 0
    record = _read_record(out)
    assert record["schema_version"] == "1.0"
    assert record["arm"] == "A"
    assert set(record) >= {"schema_version", "arm", "tree", "dimensions", "summary", "commands"}
    assert set(record["dimensions"]) == {"T", "C", "A"}
    assert record["dimensions"]["T"]["status"] == "recorded"
    assert record["dimensions"]["C"]["status"] == "recorded"
    assert record["dimensions"]["A"]["status"] == "recorded"
    assert record["summary"] == {
        "t_passed": 40,
        "c_rules_scored": 8,
        "a_predicates_passed": 10,
    }
    assert record["dimensions"]["T"]["summary"] == {"passed": 40, "total": 40}
    assert record["dimensions"]["A"]["summary"] == {"passed": 10, "failed": 0}
    assert record["dimensions"]["C"]["score"] == {
        "points": 24,
        "max": 24,
        "rules_scored": 8,
        "not_measured": [],
    }
    assert len(record["commands"]) == 10
    assert record["commands"][0]["id"] == "T"
    assert record["commands"][1]["id"] == "A"
    assert record["commands"][0]["exit_code"] == 0

    text = out.read_text(encoding="utf-8")
    assert str(tmp_path) not in text
    assert not re.search(r"[A-Za-z]:[\\/]", text), "run-record 里出现了绝对路径"
    # 树在仓库内 -> 相对标签；在仓库外 -> <outside-workspace>。两者都不是绝对路径。
    assert not Path(record["tree"]).is_absolute()


# ---------------------------------------------------------------------------
# 2. 逐字节确定
# ---------------------------------------------------------------------------
def test_same_inputs_produce_byte_identical_record(tmp_path):
    setup = _setup(tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    assert MODULE.run(_argv(setup, first), runner=FakeRunner()) == 0
    assert MODULE.run(_argv(setup, second), runner=FakeRunner()) == 0

    assert first.read_bytes() == second.read_bytes()


# ---------------------------------------------------------------------------
# 3. runner 退出 2 = T 无法判，不是 0 分
# ---------------------------------------------------------------------------
def test_runner_exit_2_marks_t_unavailable_and_run_exit_1(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.t_returncode = 2
    fake.t_stdout = ""

    code = MODULE.run(_argv(setup, out), runner=fake)

    assert code == 1
    record = _read_record(out)
    assert record["dimensions"]["T"]["status"] == "unavailable"
    assert record["dimensions"]["T"]["exit_code"] == 2
    assert record["summary"]["t_passed"] is None
    assert record["commands"][0]["exit_code"] == 2


# ---------------------------------------------------------------------------
# 4. policy.check 非 JSON = C 不可用，退出 1，点名文件
# ---------------------------------------------------------------------------
def test_policy_check_non_json_names_file_and_exits_1(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.c_invalid_json = {"src/shop/order_audit.py"}

    code = MODULE.run(_argv(setup, out), runner=fake)

    captured = capsys.readouterr()
    assert code == 1
    assert "src/shop/order_audit.py" in captured.err
    record = _read_record(out)
    assert record["dimensions"]["C"]["status"] == "unavailable"
    assert record["dimensions"]["C"]["invalid_files"] == ["src/shop/order_audit.py"]
    assert record["summary"]["c_rules_scored"] is None


# ---------------------------------------------------------------------------
# 5. 树不存在 = 退出 2
# ---------------------------------------------------------------------------
def test_missing_tree_exits_2(tmp_path, capsys):
    setup = _setup(tmp_path, tree_exists=False)
    out = tmp_path / "record.json"

    code = MODULE.run(_argv(setup, out), runner=FakeRunner())

    assert code == 2
    assert not out.exists()
    assert "--tree" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 6. layers.yaml 缺层 = 退出 2（不猜层）
# ---------------------------------------------------------------------------
def test_missing_layer_exits_2(tmp_path, capsys):
    setup = _setup(tmp_path, drop_layer="src/shop/order_audit.py")
    out = tmp_path / "record.json"

    code = MODULE.run(_argv(setup, out), runner=FakeRunner())

    assert code == 2
    assert "src/shop/order_audit.py" in capsys.readouterr().err
    assert not out.exists()


# ---------------------------------------------------------------------------
# 7. --dry-run 只打印计划
# ---------------------------------------------------------------------------
def test_dry_run_does_not_execute_anything(tmp_path, capsys):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()

    code = MODULE.run(_argv(setup, out, "--dry-run"), runner=fake)

    captured = capsys.readouterr()
    assert code == 0
    assert fake.calls == []
    assert not out.exists()
    assert "[dry-run]" in captured.out
    assert "[dry-run] T:" in captured.out
    assert captured.out.count("[dry-run]") == 10


# ---------------------------------------------------------------------------
# 8. C 计分：error 命中 0 / warning 命中 2 / 其余 3 = 20
# ---------------------------------------------------------------------------
def test_c_rule_scoring_error_warning_clean(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    error_hit = {
        "rule_id": "R-001",
        "rule_version": 1,
        "severity": "error",
        "message": "error hit",
        "evidence": {"file": "src/shop/order_audit.py", "line": 3},
    }
    warning_hit = {
        "rule_id": "R-002",
        "rule_version": 1,
        "severity": "warning",
        "message": "warning hit",
        "evidence": {"file": "src/shop/order_controller.py", "line": 4},
    }
    fake.c_payloads = {
        "src/shop/order_audit.py": _c_payload(
            "req-error", decision="block", exit_code=1, violations=[error_hit]
        ),
        "src/shop/order_controller.py": _c_payload(
            "req-warning",
            decision="allow_with_warnings",
            exit_code=1,
            violations=[warning_hit],
        ),
    }

    code = MODULE.run(_argv(setup, out), runner=fake)

    assert code == 0
    record = _read_record(out)
    c_dimension = record["dimensions"]["C"]
    assert c_dimension["status"] == "recorded"
    assert c_dimension["score"] == {
        "points": 20,
        "max": 24,
        "rules_scored": 8,
        "not_measured": [],
    }
    points = {item["rule_id"]: item["points"] for item in c_dimension["rules"]}
    assert points["R-001"] == 0
    assert points["R-002"] == 2
    assert [points[rule] for rule in RULE_IDS if rule not in {"R-001", "R-002"}] == [3] * 6
    # 命中详情进 run-record（scorer.yaml 的 aggregation 要求），但不参与计分。
    hits = {
        entry["file"]: entry["hits"]
        for entry in c_dimension["files"]
        if entry.get("hits")
    }
    assert hits["src/shop/order_audit.py"][0]["severity"] == "error"
    assert hits["src/shop/order_controller.py"][0]["severity"] == "warning"


# ---------------------------------------------------------------------------
# 额外边界：A 的退出码 1 是读数；子进程超时是 unavailable
# ---------------------------------------------------------------------------
def test_a_exit_1_is_a_reading_not_a_failure(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.a_returncode = 1
    fake.a_payload = _a_payload(passed=9)

    code = MODULE.run(_argv(setup, out), runner=fake)

    assert code == 0
    record = _read_record(out)
    assert record["dimensions"]["A"]["status"] == "recorded"
    assert record["dimensions"]["A"]["exit_code"] == 1
    assert record["dimensions"]["A"]["points"] == 27
    assert record["dimensions"]["A"]["predicates"]["failed_ids"] == ["A10"]
    assert record["summary"]["a_predicates_passed"] == 9


def test_timeout_marks_dimension_unavailable_and_exits_1(tmp_path):
    setup = _setup(tmp_path)
    out = tmp_path / "record.json"
    fake = FakeRunner()
    fake.timeout_on = "runner.py"

    code = MODULE.run(_argv(setup, out, "--timeout-seconds", "1"), runner=fake)

    assert code == 1
    record = _read_record(out)
    assert record["dimensions"]["T"]["status"] == "unavailable"
    assert record["dimensions"]["T"]["reason"] == "timeout"
    assert record["dimensions"]["T"]["exit_code"] is None
    assert record["commands"][0]["exit_code"] is None

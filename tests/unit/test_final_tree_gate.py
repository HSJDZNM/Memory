"""C3 最终树门禁 v1（tools/final_tree_gate.py）的用例。

判据来自 05 §4 C3 与 2026-10-20 的 C3 v1 交接：门禁要能对一棵树跑规则集 + 真实验证器、
把 violations 汇总成 0 / 1 / 2 的退出码，并且能用 --pin / --check 发现规则集漂移。

这些用例走**真 CLI**（子进程），不 mock 验证器：夹具树里的坏文件必须真的被 Ruff 报出 E501，
再由 policy.engine.evaluate 判成 block。规则集是 tests/fixtures/final_tree_gate/rules/ 的
夹具规则（见该目录注释：为什么这里不用仓库 43 条规则）。

退出码语义是门禁判据，因此每个用例都断言**真实退出码**，不只断言输出里有没有某个词：
0 = 无 error/critical 级违规；1 = 有 error/critical 级违规或规则集漂移；2 = 无法完成判定。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "final_tree_gate.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "final_tree_gate"
ADAPTER = FIXTURES / "adapter.yaml"
RULES = FIXTURES / "rules"
RULES_ALT = FIXTURES / "rules_alt"
TREE_CLEAN = FIXTURES / "tree_clean"
TREE_BAD = FIXTURES / "tree_bad"

# 协议断言写死版本号（AGENTS 第 55 条：加键 / 改语义必须显式递增并同批改断言）。
GATE_SCHEMA_VERSION = "1.0"
PIN_SCHEMA_VERSION = "1.0"


def scratch(name: str) -> Path:
    """在 .tmp/tests/ 下建一个本用例独有的目录。

    为什么不用 pytest 的 tmp_path：本机沙箱里 pytest basetemp 的清理锁
    （.tmp/tmp/pytest-of-ZNM/pytest-NNN/.lock）会被拒绝（D-20261018-04 的同一条），
    而 .tmp/ 本来就是这个仓库约定的会话临时根（AGENTS「临时文件与产物」）。
    """

    target = (
        REPO_ROOT
        / ".tmp"
        / "tests"
        / "final_tree_gate"
        / (name + "-" + uuid.uuid4().hex[:12])
    )
    target.mkdir(parents=True, exist_ok=False)
    return target


def run_gate(*arguments: object) -> subprocess.CompletedProcess:
    """跑一次真 CLI；输出统一 UTF-8（子进程与父进程都显式声明，避免 Windows 代码页干扰）。"""

    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(TOOL), *map(str, arguments)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=600,
        check=False,
    )


def gate_json(*arguments: object) -> tuple[subprocess.CompletedProcess, dict]:
    completed = run_gate(*arguments, "--json")
    assert completed.stdout, completed.stderr
    return completed, json.loads(completed.stdout)


# --------------------------------------------------------------------------- 1. 干净树


def test_clean_tree_exits_zero() -> None:
    completed, payload = gate_json("--workspace", TREE_CLEAN, "--config", ADAPTER)

    assert completed.returncode == 0, completed.stderr
    assert payload["schema_version"] == GATE_SCHEMA_VERSION
    assert payload["gate"] == {
        "exit_code": 0,
        "reason": "",
        "rule_set_drift": None,
        "status": "pass",
    }
    assert payload["counts"]["targets"] == 1
    assert payload["workspace_scope"]["mode"] == "all"
    assert payload["workspace_scope"]["targets"] == ["pkg/module.py"]
    # 排除清单是读数的一部分，不是看不见的默认值。
    assert payload["workspace_scope"]["excluded"]["globs"]
    assert ".git/**" in payload["workspace_scope"]["excluded"]["globs"]
    assert payload["workspace_scope"]["tree_digest"]["sha256"].startswith("sha256:")

    file = payload["files"][0]
    assert file["file"] == "pkg/module.py"
    assert file["decision"] == "allow"
    assert file["status"] == "ok"
    assert file["layer"] == "module"
    assert file["layer_source"] == "declared"
    assert file["layer_origin"] == "adapter_config"
    assert file["evidence"]["served_checkers"] == ["style_lint"]
    assert payload["violations"] == []
    assert payload["violations_by_severity"] == {
        "critical": 0,
        "error": 0,
        "info": 0,
        "warning": 0,
    }


# --------------------------------------------------------------------------- 2. 坏文件


def test_bad_file_exits_one_with_rule_id() -> None:
    completed, payload = gate_json("--workspace", TREE_BAD, "--config", ADAPTER)

    assert completed.returncode == 1, completed.stderr
    assert payload["gate"]["exit_code"] == 1
    assert payload["gate"]["status"] == "fail"
    assert payload["files"][0]["decision"] == "block"
    assert payload["files"][0]["status"] == "ok"
    assert len(payload["violations"]) == 1

    violation = payload["violations"][0]
    assert violation["file"] == "pkg/module.py"
    assert violation["rule_id"] == "GATE-001@1"  # rule_id 带版本
    assert violation["rule_version"] == 1
    assert violation["severity"] == "error"
    assert violation["evidence"]["value"] == "E501"  # 证据来自真 Ruff 诊断
    assert violation["message"]
    assert payload["violations_by_severity"]["error"] == 1
    assert payload["counts"]["blocking_violations"] == 1


# --------------------------------------------------------------------------- 3. 规则集漂移


def test_rule_set_drift_is_detected_by_check() -> None:
    pin = scratch("drift") / "rules.pin.json"
    pinned = run_gate("--workspace", TREE_CLEAN, "--config", ADAPTER, "--pin", pin)
    assert pinned.returncode == 0, pinned.stderr
    document = json.loads(pin.read_text(encoding="utf-8"))
    assert document["schema_version"] == PIN_SCHEMA_VERSION
    identity = document["rule_set"]["identity"]
    assert identity.startswith("sha256:")

    same, same_payload = gate_json(
        "--workspace", TREE_CLEAN, "--config", ADAPTER, "--check", pin
    )
    assert same.returncode == 0, same.stderr
    assert same_payload["gate"]["rule_set_drift"] is None

    # 换一份「同一 id、被改过 message」的规则文件：RuleSet.identity 必须变。
    drifted, drifted_payload = gate_json(
        "--workspace",
        TREE_CLEAN,
        "--config",
        ADAPTER,
        "--rules",
        RULES_ALT,
        "--check",
        pin,
    )
    assert drifted.returncode == 1, drifted.stderr
    assert drifted_payload["gate"]["status"] == "fail"
    drift = drifted_payload["gate"]["rule_set_drift"]
    assert drift is not None
    assert drift["pinned"] == identity
    assert drift["current"] == drifted_payload["rule_set"]["identity"]
    assert drift["current"] != identity
    # 树本身仍然干净：这次失败只来自规则集漂移，不是违规。
    assert drifted_payload["violations"] == []


def test_rule_set_identity_is_order_independent() -> None:
    """「规则集换了加载顺序」按 RuleSet.identity 的既定口径**不是**漂移。"""

    pin = scratch("order") / "order.pin.json"
    pinned = run_gate(
        "--workspace",
        TREE_CLEAN,
        "--config",
        ADAPTER,
        "--rules",
        RULES,
        "--rules",
        RULES_ALT,
        "--pin",
        pin,
    )
    assert pinned.returncode == 0, pinned.stderr

    checked, payload = gate_json(
        "--workspace",
        TREE_CLEAN,
        "--config",
        ADAPTER,
        "--rules",
        RULES_ALT,
        "--rules",
        RULES,
        "--check",
        pin,
    )
    assert checked.returncode == 0, checked.stderr
    assert payload["gate"]["rule_set_drift"] is None
    assert payload["rule_set"]["ids"] == ["GATE-001@1", "GATE-002@1"]


# --------------------------------------------------------------------------- 4. 失败关闭


def test_missing_configuration_exits_two() -> None:
    missing_adapter, payload = gate_json(
        "--workspace", TREE_CLEAN, "--config", scratch("missing-adapter") / "nope.yaml"
    )
    assert missing_adapter.returncode == 2, missing_adapter.stderr
    assert payload["gate"]["status"] == "unavailable"
    assert payload["gate"]["exit_code"] == 2
    # 三态纪律：没有树 / 没有声明时写 unavailable + reason，不写 not_applicable 冒充。
    assert payload["reading_context"]["tree"]["status"] == "unavailable"

    empty_root = scratch("empty-config-root")
    missing_registry, registry_payload = gate_json(
        "--workspace", TREE_CLEAN, "--config", ADAPTER, "--config-root", empty_root
    )
    assert missing_registry.returncode == 2, missing_registry.stderr
    assert registry_payload["gate"]["status"] == "unavailable"
    assert "验证器配置不可用" in registry_payload["gate"]["reason"]


def test_unavailable_validator_exits_two() -> None:
    """验证器被允许清单排除 ⇒ checker 拿不到证据 ⇒ 退出码 2，不是 0，也不是 1。"""

    completed, payload = gate_json(
        "--workspace", TREE_BAD, "--config", ADAPTER, "--validators", "py.source"
    )
    assert completed.returncode == 2, completed.stderr
    assert payload["gate"]["status"] == "unavailable"
    assert payload["counts"]["files_unavailable"] == 1
    gaps = payload["files"][0]["evidence"]["gaps"]
    assert [gap["checker"] for gap in gaps] == ["style_lint"]
    assert gaps[0]["kind"] == "blocker"


def test_empty_tree_exits_two() -> None:
    """一棵没有任何受规则覆盖文件的树不许静默通过（没有可判定对象 = 无法完成判定）。"""

    empty_tree = scratch("empty-tree")
    completed, payload = gate_json("--workspace", empty_tree, "--config", ADAPTER)
    assert completed.returncode == 2, completed.stderr
    assert payload["gate"]["status"] == "unavailable"
    assert "枚举结果为 0" in payload["gate"]["reason"]


# --------------------------------------------------------------------------- 5. 确定性


def test_json_payload_is_byte_identical_across_runs() -> None:
    first = run_gate("--workspace", TREE_CLEAN, "--config", ADAPTER, "--json")
    second = run_gate("--workspace", TREE_CLEAN, "--config", ADAPTER, "--json")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout  # 逐字节相同

    payload = json.loads(first.stdout)
    assert "started_at" not in first.stdout
    assert "run" not in payload["reading_context"]  # 包装层不带 run
    assert payload["reading_context"]["source"] == "gate"
    assert payload["reading_context"]["host"]["sandbox"] in {
        "unknown",
        "restricted",
        "unrestricted",
    }
    # 载荷里不许出现绝对路径（本机仓库根与盘符两处都查）。
    assert str(REPO_ROOT) not in first.stdout
    assert "C:\\" not in first.stdout


# --------------------------------------------------------------------------- 6. 只读边界


def test_tool_does_not_import_workflow_framework() -> None:
    """C3 v1 的硬边界：门禁只读，且**不导入工作流框架**（AGENTS 核心层约束 1 / 第 35 条）。"""

    program = (
        "import sys; sys.path.insert(0, 'tools'); import final_tree_gate; "
        "print(sorted(sys.modules.keys() & {'orchestration', 'langgraph', 'langchain'}))"
    )
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"

"""D 门 2 run-manifest（18 字段契约）的回归：字段集合、三态、确定性、摘要漂移与退出码。

判据来源：`scorer/scorer.yaml` 的 `run_manifest_fields`、`scorer/README.md` 第 4/5/6/11 节、
`readings/2026-10-19-D-gate2-treatment.md` 4.4/4.5、`c-arm/README.md` 第 6 节。本文件只使用
**真实冻结包**做生成（不造假清单），因此每条用例的读数都来自当前仓库；唯一会被改动的是
`.tmp/tests/<uuid>/` 下的临时副本（`tmp_root` / `module_tmp_root` 夹具）。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DGATE2 = (
    REPO_ROOT / "docs" / "project" / "engineering-policy-platform" / "testing" / "ab" / "dgate2"
)
RUN_MANIFEST = DGATE2 / "run-manifest" / "run_manifest.py"
SCORER_YAML = DGATE2 / "scorer" / "scorer.yaml"
DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/]")


def _load():
    """按路径加载被测脚本（docs/ 不在包内，也不依赖 conftest 的导入顺序）。"""

    spec = importlib.util.spec_from_file_location("dgate2_run_manifest_under_test", RUN_MANIFEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


@pytest.fixture(scope="module")
def module():
    return _load()


@pytest.fixture(scope="module")
def base(module, module_tmp_root):
    """真实生成一份 A 臂清单：这是所有 `--check` 用例的基准（模块级，只生成一次）。"""

    path = module_tmp_root / "run-manifest-A.json"
    code = module.run(["--arm", "A", "--out", str(path)])
    assert code == 0, "冻结包干净时生成开跑前清单应为 0"
    raw = path.read_bytes()
    return path, json.loads(raw.decode("utf-8")), raw


def test_eighteen_field_ids_match_scorer_yaml_exactly(module):
    document = yaml.safe_load(SCORER_YAML.read_text(encoding="utf-8"))
    ids = [item["id"] for item in document["run_manifest_fields"]["items"]]
    assert len(ids) == 18
    assert list(module.RUN_MANIFEST_FIELDS) == ids
    assert ids[-1] == "platform_generation"
    assert document["version"] == "3"


def test_generate_a_arm_writes_18_field_payload(module, base):
    path, payload, raw = base
    assert payload["schema_version"] == "1.1" == module.RUN_MANIFEST_SCHEMA_VERSION
    assert payload["arm"] == "A"
    fields = payload["fields"]
    assert set(fields) == set(module.RUN_MANIFEST_FIELDS)
    for field_id, entry in fields.items():
        assert entry["status"] in {"recorded", "pending", "not_applicable"}, field_id
        assert "value" in entry, field_id
        assert isinstance(entry["source"], str) and entry["source"].strip(), field_id
        if entry["status"] in {"pending", "not_applicable"}:
            assert isinstance(entry.get("reason"), str) and entry["reason"].strip(), field_id
    text = raw.decode("utf-8")
    assert str(REPO_ROOT) not in text
    assert str(REPO_ROOT).replace("\\", "/") not in text
    assert not DRIVE_PATH.search(text)
    expected_out = path.relative_to(REPO_ROOT).as_posix()
    assert fields["worktree_clean"]["value"]["self_output_excluded"] == expected_out
    assert fields["head"]["value"] == module._git_head(REPO_ROOT)


def test_generation_is_byte_identical_for_the_same_input(module, base):
    path, _, first = base
    assert module.run(["--arm", "A", "--out", str(path)]) == 0
    assert path.read_bytes() == first


def test_check_reports_missing_field_by_id(module, base, module_tmp_root, capsys):
    _, payload, _ = base
    mutated = copy.deepcopy(payload)
    target = "hidden_digests"
    del mutated["fields"][target]
    path = _write(module_tmp_root / "missing-field.json", mutated)
    code = module.run(["--check", str(path)])
    out = capsys.readouterr().out
    assert code == 1
    assert target in out
    assert "RESULT: FAIL" in out


def test_check_reports_unexpected_field_by_id(module, base, module_tmp_root, capsys):
    """字段比 18 个多也要点名：多出来的键同样会让载荷形状偏离契约。"""

    _, payload, _ = base
    mutated = copy.deepcopy(payload)
    mutated["fields"]["not_a_run_manifest_field"] = {
        "status": "pending",
        "value": None,
        "source": "synthetic",
        "reason": "synthetic",
    }
    path = _write(module_tmp_root / "extra-field.json", mutated)
    code = module.run(["--check", str(path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "not_a_run_manifest_field" in out


def test_check_rejects_tampered_scorer_manifest_digest(module, base, module_tmp_root, capsys):
    _, payload, _ = base
    mutated = copy.deepcopy(payload)
    mutated["fields"]["scorer_manifest_sha256"]["value"] = "0" * 64
    path = _write(module_tmp_root / "tampered-digest.json", mutated)
    code = module.run(["--check", str(path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "scorer_manifest_sha256" in out


def test_strict_refuses_pending_human_items(module, base, capsys):
    path, _, _ = base
    code = module.run(["--check", str(path), "--strict"])
    out = capsys.readouterr().out
    assert code == 1
    assert "human_items_unrecorded" in out
    assert "RESULT: FAIL" in out


def test_unknown_arm_is_a_usage_error(module, module_tmp_root):
    with pytest.raises(SystemExit) as error:
        module.run(["--arm", "Z", "--out", str(module_tmp_root / "arm-Z.json")])
    assert error.value.code == 2


def test_c_arm_with_patch_is_written_but_check_fails(module, module_tmp_root, capsys):
    facts = {
        "tree_digest": "a" * 64,
        "session_id": "session-c-patch",
        "launch": {"patch": ".policy/patch.yml"},
        "launcher_sandbox": "danger-full-access",
    }
    facts_path = _write(module_tmp_root / "arm-facts-C-patch.json", facts)
    target = module_tmp_root / "run-manifest-C-patch.json"
    generation = module.run(
        ["--arm", "C", "--out", str(target), "--arm-facts", str(facts_path)]
    )
    assert generation == 1, "C 臂带 patch 的清单要写出来，但生成就应判不合格"
    capsys.readouterr()
    check = module.run(["--check", str(target)])
    out = capsys.readouterr().out
    assert check == 1
    assert "arms" in out
    assert "C 臂" in out


def test_missing_reference_tree_is_a_usage_error(module, module_tmp_root):
    target = module_tmp_root / "run-manifest-missing-ref.json"
    code = module.run(
        [
            "--arm",
            "A",
            "--out",
            str(target),
            "--reference-tree",
            str(module_tmp_root / "does-not-exist"),
        ]
    )
    assert code == 2
    assert not target.exists(), "读不到参考树时不许先写出一份半成品清单"


def test_invalid_run_record_is_a_usage_error_that_names_the_gap(module, module_tmp_root, capsys):
    record = _write(module_tmp_root / "run-record-bad.json", {"schema_version": "1.0", "arm": "A"})
    target = module_tmp_root / "run-manifest-bad-record.json"
    code = module.run(
        ["--arm", "A", "--out", str(target), "--run-record", str(record)]
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "dimensions" in err
    assert not target.exists()


def test_c_arm_accepts_full_run_manifest_and_ignores_unknown_keys(module, module_tmp_root):
    """C 臂的完整 run-manifest 直接当 --arm-facts：只抽四类事实，原始绝对路径不进载荷。"""

    # 合成一个"仓库外绝对路径"：用拼接避免在仓库文本里出现一个完整的盘符路径字面量。
    outside = "Z:" + "/outside-tree"
    facts = {
        "arm": "C",
        "status": "ok",
        "run_kind": "smoke",
        "head": "c44f9dbd9eb0ba91e25093c73a4bc166ef55090a",
        "tree": {
            "target": outside,
            "combined_manifest_sha256": "b" * 64,
            "file_count": 12,
        },
        "session": {"id": "session-1", "log": outside + "/session.v4.jsonl.zstd"},
        "dsh": {"version": "0.2.1", "profile": "headless"},
        "patch_argument": None,
        "launcher": {"sandbox": "danger-full-access"},
        "governance": {"session_record_hits": 0},
    }
    facts_path = _write(module_tmp_root / "arm-facts-C-full.json", facts)
    target = module_tmp_root / "run-manifest-C-full.json"
    code = module.run(["--arm", "C", "--out", str(target), "--arm-facts", str(facts_path)])
    assert code == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    arms = payload["fields"]["arms"]["value"]
    assert arms["tree_digest"] == "b" * 64
    assert arms["session_id"] == "session-1"
    assert arms["launch"]["patch"] is None
    assert arms["launcher_sandbox"] == "danger-full-access"
    text = target.read_text(encoding="utf-8")
    assert outside not in text
    assert not DRIVE_PATH.search(text)
    # 非 strict 下 readings / reference_tree / human 四项仍 pending；摘要字段与臂都必须过。
    assert module.run(["--check", str(target)]) == 0


def test_ab_arm_facts_must_declare_launcher_sandbox(module, module_tmp_root):
    facts = _write(
        module_tmp_root / "arm-facts-B-no-launcher.json",
        {"tree_digest": "c" * 64, "session_id": "session-b", "launch": {"patch": None}},
    )
    target = module_tmp_root / "run-manifest-B-no-launcher.json"
    code = module.run(["--arm", "B", "--out", str(target), "--arm-facts", str(facts)])
    assert code == 2
    assert not target.exists()
@pytest.fixture(scope="module")
def platform_facts_document(base):
    """一份可通过的 platform_generation 事实（首消息摘要取真实任务包的那一份）。"""

    _, payload, _ = base
    first = payload["fields"]["first_message_sha256"]["value"]["sha256"]
    head = payload["fields"]["head"]["value"]
    return {
        "host": {
            "entry": "desktop",
            "dsh_runtime": "0.2.1-rc.2",
            "dsh_source": "app_bundled",
            "dsh_entry": "<install>/resources/runtime/cli/bin/dsh.cmd",
            "profile": "desktop-gui",
            "session_sandbox": "workspace-write",
            "file_policy": "danger-full-access",
            "sandbox": "unrestricted",
        },
        "start": {"head": head, "worktree_clean": True},
        "run": {"serial": True, "ci_local_lock_held": False, "concurrent_sessions": 1},
        "declarations": {
            "adapter_config": {
                "path": "<governed>/.policy/dsh-adapter.yaml",
                "sha256": "a" * 64,
                "agent_version": "0.2.1-rc.2",
                "into_decision": True,
                "max_targets": 20,
            },
            "registry": {
                "path": "<governed>/.policy/tool-registry.local.yaml",
                "sha256": "b" * 64,
                "registry_schema_version": "1.4",
                "approved_path": "<governed>/.policy/tool-registry.approved.json",
                "approved_sha256": "c" * 64,
                "approved_reviewed_by": "dshznm",
                "approved_reviewed_at": "2026-10-21T10:00:00+08:00",
            },
            "approval": {"path": "<governed>/.policy/approval.json", "sha256": "d" * 64},
            "test_layout": {"path": "validation/test-layout.yaml", "sha256": "e" * 64},
        },
        "batch_ledger": {
            "enabled": True,
            "into_decision": True,
            "max_targets": 20,
            "ttl_hours": 24,
            "schema_version": "1.1",
        },
        "audit_schema_version": "1.5",
        "pre_evidence": {"enabled": True, "timeout_ms": 20000},
        "timeouts": {"tool_timeout_ms": 5000, "hooks_timeout_ms": 30000},
        "model": {
            "id": "deepseek-v4-flash",
            "params": {"temperature": 0},
            "first_message_sha256": first,
        },
        "observations": {
            "batch": {
                "decisions": 9,
                "with_batch": 6,
                "settled": 6,
                "truncated": 0,
                "unreadable": 0,
                "degraded": False,
            }
        },
    }


def _generate_with_platform(module, module_tmp_root, document, name):
    facts_path = _write(module_tmp_root / (name + "-facts.json"), document)
    target = module_tmp_root / (name + ".json")
    code = module.run(["--arm", "A", "--out", str(target), "--platform-facts", str(facts_path)])
    return code, target


def test_platform_generation_is_pending_without_platform_facts(base):
    _, payload, _ = base
    entry = payload["fields"]["platform_generation"]
    assert entry["status"] == "pending"
    assert entry["value"] is None
    assert entry["reason"]


def test_platform_generation_records_generation_and_recomputes_budget(
    module, module_tmp_root, platform_facts_document
):
    code, target = _generate_with_platform(
        module, module_tmp_root, platform_facts_document, "run-manifest-platform"
    )
    assert code == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    entry = payload["fields"]["platform_generation"]
    assert entry["status"] == "recorded"
    value = entry["value"]
    assert value["budget"] == {
        "applicable": True,
        "ok": True,
        "left_ms": 25000,
        "right_ms": 30000,
        "inequality": "pre_evidence.timeout_ms + timeouts.tool_timeout_ms < timeouts.hooks_timeout_ms",
    }
    assert value["batch_ledger"]["into_decision"] is True
    assert value["declarations"]["adapter_config"]["max_targets"] == 20
    assert value["model"]["first_message_sha256"] == (
        payload["fields"]["first_message_sha256"]["value"]["sha256"]
    )
    assert value["problems"] == []
    assert module.run(["--check", str(target)]) == 0
    text = target.read_text(encoding="utf-8")
    assert not DRIVE_PATH.search(text)


def test_platform_facts_reject_unknown_key(
    module, module_tmp_root, platform_facts_document, capsys
):
    document = copy.deepcopy(platform_facts_document)
    document["host"]["extra"] = "x"
    facts_path = _write(module_tmp_root / "platform-unknown-facts.json", document)
    target = module_tmp_root / "run-manifest-platform-unknown.json"
    code = module.run(
        ["--arm", "A", "--out", str(target), "--platform-facts", str(facts_path)]
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "未知键" in err
    assert not target.exists(), "未知键不部分接受：读不到声明时不许写出半成品清单"


def test_platform_budget_inequality_is_a_manifest_failure(
    module, module_tmp_root, platform_facts_document, capsys
):
    document = copy.deepcopy(platform_facts_document)
    document["timeouts"]["hooks_timeout_ms"] = 24000
    facts_path = _write(module_tmp_root / "platform-budget-facts.json", document)
    target = module_tmp_root / "run-manifest-platform-budget.json"
    code = module.run(
        ["--arm", "A", "--out", str(target), "--platform-facts", str(facts_path)]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "预算不等式" in err
    payload = json.loads(target.read_text(encoding="utf-8"))
    budget = payload["fields"]["platform_generation"]["value"]["budget"]
    assert budget["ok"] is False
    assert budget["left_ms"] == 25000 and budget["right_ms"] == 24000
    capsys.readouterr()
    assert module.run(["--check", str(target)]) == 1


def test_platform_serial_contradiction_is_a_manifest_failure(
    module, module_tmp_root, platform_facts_document, capsys
):
    document = copy.deepcopy(platform_facts_document)
    document["run"]["ci_local_lock_held"] = True
    facts_path = _write(module_tmp_root / "platform-serial-facts.json", document)
    target = module_tmp_root / "run-manifest-platform-serial.json"
    code = module.run(
        ["--arm", "A", "--out", str(target), "--platform-facts", str(facts_path)]
    )
    assert code == 1
    assert "run.serial" in capsys.readouterr().err


def test_check_flags_mismatched_first_message(
    module, module_tmp_root, platform_facts_document, capsys
):
    document = copy.deepcopy(platform_facts_document)
    document["model"]["first_message_sha256"] = "0" * 64
    facts_path = _write(module_tmp_root / "platform-first-facts.json", document)
    target = module_tmp_root / "run-manifest-platform-first.json"
    code = module.run(
        ["--arm", "A", "--out", str(target), "--platform-facts", str(facts_path)]
    )
    assert code == 1
    assert "first_message_sha256" in capsys.readouterr().err


def test_check_recomputes_platform_budget_and_flags_tampering(
    module, module_tmp_root, platform_facts_document, capsys
):
    code, target = _generate_with_platform(
        module, module_tmp_root, platform_facts_document, "run-manifest-platform-tamper"
    )
    assert code == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["fields"]["platform_generation"]["value"]["budget"]["left_ms"] = 1
    tampered = _write(module_tmp_root / "run-manifest-platform-tampered.json", payload)
    capsys.readouterr()
    code = module.run(["--check", str(tampered)])
    out = capsys.readouterr().out
    assert code == 1
    assert "budget.left_ms" in out
    assert "RESULT: FAIL" in out

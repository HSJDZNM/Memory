"""bank/harness 三个运行框架脚本的回归：清单确定性、越界拒绝、臂配置摘要、载荷脱敏、缺件退出码。

判据来源：`ab/bank/harness/README.md` 的字段表与退出码表、AGENTS 第 45 / 51 / 55 条。
本文件**不 spawn dsh、不跑真机会话**：唯一被起的子进程是「用同一个解释器跑兄弟脚本」的那几次
（`freeze_manifest.py --check` / `scaffold_arms.py --check`），而 `--execute` 那条路径
只测纯函数（增量读取、树 diff、载荷组装），一次会话都不发。

所有临时件都落在 `tmp_path`（函数级、唯一），不碰 `.tmp/` 下的共享路径。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "docs" / "project" / "engineering-policy-platform" / "testing" / "ab" / "bank" / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import _ab_harness_common as common  # noqa: E402
import freeze_manifest  # noqa: E402
import run_session  # noqa: E402
import scaffold_arms  # noqa: E402

DRIVE_PATH = __import__("re").compile(r"[A-Za-z]:[\\/]")

REGISTRY_YAML = """registry_schema_version: "1.4"
tools:
  - id: exec.pwsh
    allowed_commands:
      - "^pytest( .*)?$"
      - "^echo( .*)?$"
    command_families:
      - id: tests
        title: 测试族
        patterns:
          - "^pytest( .*)?$"
      - id: readonly
        title: 只读族
        patterns:
          - "^echo( .*)?$"
"""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _write_json(path: Path, payload) -> Path:
    return _write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


@pytest.fixture()
def task_package(tmp_path: Path) -> Path:
    """一个**没有** reset-arm.py 的任务包：基线走 baseline/ 复制这条分支。"""

    package = tmp_path / "task-package-x"
    _write(package / "baseline" / "src" / "app.py", "VALUE = 1\n")
    _write(package / "baseline" / "tests" / "test_app.py", "def test_ok():\n    assert True\n")
    _write(package / "baseline" / "README.md", "# demo\n")
    _write(package / "task-package" / "first-message.txt", "把 VALUE 改成 2，并补一个测试。\n")
    return package


@pytest.fixture()
def arm_config(tmp_path: Path) -> Path:
    """臂配置目录：三个必需文件 + 两个已签发文件（所以没有占位）。"""

    config = tmp_path / "arm-config-A"
    _write(
        config / "dsh-adapter.yaml",
        "project_root: ..\naudit_log: audit.jsonl\n",
    )
    _write(config / "hooks.json", json.dumps({"hooks": {"PreToolUse": []}}, indent=2) + "\n")
    _write(config / "tool-registry.local.yaml", REGISTRY_YAML)
    _write(config / "tool-registry.approved.json", json.dumps({"approved": {}}, indent=2) + "\n")
    _write(config / "approval.json", json.dumps({"patterns": []}, indent=2) + "\n")
    return config


def _scaffold(tmp_path: Path, task_package: Path, arm_config: Path) -> tuple:
    target = tmp_path / "arm-trees" / "A"
    manifest = tmp_path / "arm-trees" / "A.arm-manifest.json"
    code = scaffold_arms.run(
        [
            "--task-package",
            str(task_package),
            "--arm",
            "A",
            "--target",
            str(target),
            "--arm-config",
            str(arm_config),
            "--manifest-out",
            str(manifest),
        ]
    )
    assert code == 0, "合法输入下建臂树应为 0"
    return target, manifest, json.loads(manifest.read_text(encoding="utf-8"))


def _freeze_set(tmp_path: Path, task_package: Path, arm_config: Path) -> Path:
    return _write_json(
        tmp_path / "exp-set.json",
        {
            "schema_version": "1.0",
            "name": "unit-exp",
            "task_packages": [_rel(task_package)],
            "scorer_inputs": [],
            "arm_configs": {"A": _rel(arm_config)},
            "first_message": _rel(task_package / "task-package" / "first-message.txt"),
            "ignore": ["**/__pycache__/**", "**/*.pyc"],
        },
    )


def _rel(path: Path) -> str:
    """仓库相对 POSIX 路径；tmp_path 不在仓库里时显式跳过（冻结清单只接受仓库相对路径）。"""

    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:  # pragma: no cover - 仓库 conftest 把临时根钉在 .tmp/tmp
        pytest.skip("tmp_path 不在仓库内：冻结清单要求仓库相对路径")


def _freeze(set_path: Path, manifest: Path, *extra: str) -> int:
    return freeze_manifest.run(["--set", str(set_path), "--manifest", str(manifest), *extra])


# --------------------------------------------------------------------------- 通配与摘要


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("**/__pycache__/**", "__pycache__/x.pyc", True),
        ("**/__pycache__/**", "a/b/__pycache__/x.pyc", True),
        ("**/__pycache__/**", "a/b/cache/x.pyc", False),
        ("**/*.pyc", "x.pyc", True),
        ("**/*.pyc", "a/b/x.pyc", True),
        ("**/*.pyc", "a/b/x.py", False),
        (".git/**", ".git/config", True),
        (".git/**", "sub/.git/config", False),
        ("tests/**", "tests/test_x.py", True),
        ("tests/**", "tests/deep/test_x.py", True),
        ("tests/**", "src/tests/test_x.py", False),
        ("**/*.jsonl", ".policy/audit.jsonl", True),
        ("*.jsonl", ".policy/audit.jsonl", False),
    ],
)
def test_glob_match_treats_double_star_as_recursive(pattern, path, expected):
    assert common.glob_match(pattern, path) is expected


def test_manifest_lines_sort_by_path_not_by_digest_prefix():
    entries = [("b.py", "f" * 64), ("a.py", "0" * 64)]
    lines = common.manifest_lines(entries)
    assert lines == ["%s  a.py" % ("0" * 64), "%s  b.py" % ("f" * 64)]


def test_combined_digest_matches_reset_arm_algorithm():
    entries = [("z.py", "1" * 64), ("a/b.py", "2" * 64)]
    lines = common.manifest_lines(entries)
    # 独立实现：按 relpath 排序后的 "<sha>  <rel>" 文本再 sha256（a3-task-v3/reset-arm.py 的口径）
    expected_text = "".join("%s  %s\n" % (digest, path) for path, digest in sorted(entries))
    assert common.combined_digest(lines) == "sha256:" + sha256_text(expected_text)


def test_walk_files_returns_relative_paths_and_ignores(tmp_path):
    root = tmp_path / "tree"
    _write(root / "keep.txt", "x")
    _write(root / "__pycache__" / "skip.pyc", "y")
    files, unreadable, ignored = common.walk_files(root, ["**/__pycache__/**"], "tree")
    assert files == ["keep.txt"]
    assert unreadable == []
    assert ignored == ["__pycache__/"]


# --------------------------------------------------------------------------- 冻结清单


def test_freeze_write_is_byte_identical_twice_and_has_no_absolute_paths(
    tmp_path, task_package, arm_config
):
    set_path = _freeze_set(tmp_path, task_package, arm_config)
    manifest = tmp_path / "freeze.json"
    assert _freeze(set_path, manifest, "--write") == 0
    first = manifest.read_bytes()
    assert _freeze(set_path, manifest, "--write") == 0
    assert manifest.read_bytes() == first, "同一输入两次生成必须逐字节相同"

    payload = json.loads(first.decode("utf-8"))
    assert payload["schema_version"] == freeze_manifest.AB_FREEZE_MANIFEST_SCHEMA_VERSION
    assert payload["manifest"]["count"] > 0
    assert payload["manifest"]["combined_digest"].startswith("sha256:")
    assert common.check_no_absolute_paths(payload) == []
    text = first.decode("utf-8")
    assert DRIVE_PATH.search(text) is None
    for marker in ("created_at", "timestamp", "run_id", "generated_at"):
        assert marker not in text


def test_freeze_check_passes_and_strict_requires_declared_ignore(
    tmp_path, task_package, arm_config
):
    set_path = _freeze_set(tmp_path, task_package, arm_config)
    manifest = tmp_path / "freeze.json"
    assert _freeze(set_path, manifest, "--write") == 0
    assert _freeze(set_path, manifest, "--check") == 0
    assert _freeze(set_path, manifest, "--check", "--strict") == 0

    loose = json.loads(set_path.read_text(encoding="utf-8"))
    del loose["ignore"]
    loose_path = _write_json(tmp_path / "loose-set.json", loose)
    loose_manifest = tmp_path / "loose-freeze.json"
    assert _freeze(loose_path, loose_manifest, "--write") == 0
    payload = json.loads(loose_manifest.read_text(encoding="utf-8"))
    assert payload["ignore"]["source"] == "default"
    assert _freeze(loose_path, loose_manifest, "--check") == 0
    assert _freeze(loose_path, loose_manifest, "--check", "--strict") == 1


def test_freeze_check_detects_drift_extra_and_missing(tmp_path, task_package, arm_config):
    set_path = _freeze_set(tmp_path, task_package, arm_config)
    manifest = tmp_path / "freeze.json"
    assert _freeze(set_path, manifest, "--write") == 0

    _write(task_package / "baseline" / "src" / "app.py", "VALUE = 999\n")
    assert _freeze(set_path, manifest, "--check") == 1, "sha256 漂移必须退出 1"

    _write(task_package / "baseline" / "src" / "app.py", "VALUE = 1\n")
    assert _freeze(set_path, manifest, "--check") == 0
    _write(task_package / "baseline" / "src" / "extra.py", "X = 1\n")
    assert _freeze(set_path, manifest, "--check") == 1, "多出文件必须退出 1"

    (task_package / "baseline" / "src" / "extra.py").unlink()
    (task_package / "baseline" / "README.md").unlink()
    assert _freeze(set_path, manifest, "--check") == 1, "少文件必须退出 1"


def test_freeze_write_refuses_missing_root_and_writes_nothing(tmp_path, task_package, arm_config):
    """--write 是「首次冻结」：它只知道根，所以「少文件」只能由 --check 发现。

    这里测的是 --write 唯一能发现的缺件形态：**声明过的东西读不到**。它必须退出 1 且不写盘——
    写一张半截清单，比没有清单更危险（看起来冻过了）。
    """

    set_path = _freeze_set(tmp_path, task_package, arm_config)
    (task_package / "task-package" / "first-message.txt").unlink()
    manifest = tmp_path / "freeze.json"
    assert _freeze(set_path, manifest, "--write") == 1
    assert not manifest.exists(), "读不到就不写盘"

    (task_package / "baseline").rename(task_package / "baseline-moved")
    assert _freeze(set_path, tmp_path / "freeze2.json", "--write") == 1
    assert not (tmp_path / "freeze2.json").exists()


def test_freeze_rejects_absolute_path_in_set(tmp_path, task_package, arm_config):
    set_path = _freeze_set(tmp_path, task_package, arm_config)
    payload = json.loads(set_path.read_text(encoding="utf-8"))
    payload["task_packages"] = [str((task_package / "baseline").resolve())]
    absolute = _write_json(tmp_path / "abs-set.json", payload)
    assert _freeze(absolute, tmp_path / "abs-freeze.json", "--write") == 2


def test_freeze_rejects_unknown_set_key_and_manifest_inside_root(
    tmp_path, task_package, arm_config
):
    set_path = _freeze_set(tmp_path, task_package, arm_config)
    payload = json.loads(set_path.read_text(encoding="utf-8"))
    payload["extra_key"] = 1
    unknown = _write_json(tmp_path / "unknown-set.json", payload)
    assert _freeze(unknown, tmp_path / "u.json", "--write") == 2

    inside = task_package / "baseline" / "freeze.json"
    assert _freeze(set_path, inside, "--write") == 2, "清单不能落在被冻结的根里"


def test_freeze_check_unreadable_manifest_exits_1(tmp_path, task_package, arm_config):
    set_path = _freeze_set(tmp_path, task_package, arm_config)
    assert _freeze(set_path, tmp_path / "nope.json", "--check") == 1


def test_freeze_check_rejects_unknown_schema_version(tmp_path, task_package, arm_config):
    set_path = _freeze_set(tmp_path, task_package, arm_config)
    manifest = tmp_path / "freeze.json"
    assert _freeze(set_path, manifest, "--write") == 0
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["schema_version"] = "9.9"
    bumped = _write_json(tmp_path / "bumped.json", payload)
    assert _freeze(set_path, bumped, "--check") == 1


# --------------------------------------------------------------------------- 三臂脚手架


def test_scaffold_writes_policy_digests_and_manifest(tmp_path, task_package, arm_config):
    target, manifest_path, payload = _scaffold(tmp_path, task_package, arm_config)

    assert payload["schema_version"] == scaffold_arms.AB_ARM_MANIFEST_SCHEMA_VERSION
    assert payload["arm"] == "A"
    assert payload["policy"]["status"] == "governed"
    assert payload["policy"]["placeholders"] == [], "臂配置自带了两个已签发文件，不该造占位"

    roles = {item["path"]: item["role"] for item in payload["policy"]["files"]}
    assert set(roles) == {
        ".policy/dsh-adapter.yaml",
        ".policy/hooks.json",
        ".policy/tool-registry.local.yaml",
        ".policy/tool-registry.approved.json",
        ".policy/approval.json",
    }
    for item in payload["policy"]["files"]:
        actual = hashlib.sha256((target / item["path"]).read_bytes()).hexdigest()
        assert item["sha256"] == actual, "臂配置摘要必须是臂树里那份文件的摘要"

    # 基线摘要 = 基线文件清单文本的 sha256（与 reset-arm.py 同一算法）
    baseline_lines = common.manifest_lines(
        (item["path"], item["sha256"]) for item in payload["baseline"]["files"]
    )
    assert payload["baseline"]["combined_digest"] == common.combined_digest(baseline_lines)
    assert payload["baseline"]["file_count"] == 3
    assert payload["target"]["file_count"] == 3 + 5
    assert payload["first_message"]["sha256"] == sha256_text(
        "把 VALUE 改成 2，并补一个测试。\n"
    )
    assert payload["command_families"]["status"] == "parsed"
    assert payload["command_families"]["tools"][0]["tool"] == "exec.pwsh"
    assert [item["id"] for item in payload["command_families"]["tools"][0]["families"]] == [
        "tests",
        "readonly",
    ]
    assert payload["command_families"]["tools"][0]["allowed_command_count"] == 2
    assert common.check_no_absolute_paths(payload) == []
    assert manifest_path.is_file()


def test_scaffold_c_arm_has_no_governance_config(tmp_path, task_package):
    target = tmp_path / "arm-trees" / "C"
    code = scaffold_arms.run(
        [
            "--task-package",
            str(task_package),
            "--arm",
            "C",
            "--target",
            str(target),
            "--manifest-out",
            str(tmp_path / "C.arm-manifest.json"),
        ]
    )
    assert code == 0
    payload = json.loads((tmp_path / "C.arm-manifest.json").read_text(encoding="utf-8"))
    assert payload["policy"]["status"] == "not_governed"
    assert payload["policy"]["placeholders"] == []
    assert [item["path"] for item in payload["policy"]["files"]] == [scaffold_arms.NOT_GOVERNED_NOTE]
    assert payload["command_families"]["status"] == "not_applicable"
    for name in scaffold_arms.REQUIRED_POLICY_FILES:
        assert not (target / ".policy" / name).exists(), "C 臂不许有治理配置"
    assert (target / "src" / "app.py").is_file(), "基线仍然要在"


def test_scaffold_c_arm_refuses_arm_config(tmp_path, task_package, arm_config):
    code = scaffold_arms.run(
        [
            "--task-package",
            str(task_package),
            "--arm",
            "C",
            "--target",
            str(tmp_path / "arm-trees" / "C2"),
            "--arm-config",
            str(arm_config),
        ]
    )
    assert code == 2


def test_scaffold_rejects_unknown_arm_config_file(tmp_path, task_package, arm_config):
    _write(arm_config / "audit.jsonl", "{}\n")
    code = scaffold_arms.run(
        [
            "--task-package",
            str(task_package),
            "--arm",
            "A",
            "--target",
            str(tmp_path / "arm-trees" / "A"),
            "--arm-config",
            str(arm_config),
        ]
    )
    assert code == 2, "臂配置目录里出现未声明文件必须拒绝（不夹带审计 / 台账）"


def test_scaffold_missing_required_policy_file_exits_2(tmp_path, task_package, arm_config):
    (arm_config / "hooks.json").unlink()
    code = scaffold_arms.run(
        [
            "--task-package",
            str(task_package),
            "--arm",
            "A",
            "--target",
            str(tmp_path / "arm-trees" / "A"),
            "--arm-config",
            str(arm_config),
        ]
    )
    assert code == 2


def test_scaffold_writes_unsigned_placeholders_when_absent(tmp_path, task_package, arm_config):
    (arm_config / "approval.json").unlink()
    (arm_config / "tool-registry.approved.json").unlink()
    _, _, payload = _scaffold(tmp_path, task_package, arm_config)
    assert payload["policy"]["placeholders"] == [
        ".policy/approval.json",
        ".policy/tool-registry.approved.json",
    ]


def test_scaffold_refuses_unsafe_targets(tmp_path, task_package, arm_config):
    def _run(target: Path) -> int:
        return scaffold_arms.run(
            [
                "--task-package",
                str(task_package),
                "--arm",
                "A",
                "--target",
                str(target),
                "--arm-config",
                str(arm_config),
            ]
        )

    assert _run(REPO_ROOT) == 2, "仓库根不能当臂树"
    assert _run(REPO_ROOT.parent) == 2, "仓库根的祖先不能当臂树"
    assert _run(REPO_ROOT / ".git" / "ab-arm") == 2, ".git 里不能建臂树"
    assert _run(task_package) == 2, "任务包里面不能建臂树（互相包含）"
    occupied = tmp_path / "occupied"
    _write(occupied / "keep.txt", "x")
    assert _run(occupied) == 2, "非空目标目录一律拒绝（不覆盖既有臂树）"


def test_scaffold_check_detects_tree_drift_and_first_message_drift(
    tmp_path, task_package, arm_config
):
    target, manifest_path, _payload = _scaffold(tmp_path, task_package, arm_config)
    common_args = [
        "--task-package",
        str(task_package),
        "--arm",
        "A",
        "--target",
        str(target),
        "--manifest-out",
        str(manifest_path),
        "--check",
    ]
    assert scaffold_arms.run(common_args) == 0

    _write(target / "src" / "app.py", "VALUE = 3\n")
    assert scaffold_arms.run(common_args) == 1, "臂树漂移必须退出 1"

    _write(target / "src" / "app.py", "VALUE = 1\n")
    assert scaffold_arms.run(common_args) == 0
    _write(target / "src" / "extra.py", "X = 1\n")
    assert scaffold_arms.run(common_args) == 1, "臂树多出文件必须退出 1"

    (target / "src" / "extra.py").unlink()
    _write(task_package / "task-package" / "first-message.txt", "换个说法。\n")
    assert scaffold_arms.run(common_args) == 1, "首消息漂移必须退出 1"


def test_scaffold_check_without_manifest_exits_2(tmp_path, task_package):
    target = tmp_path / "arm-trees" / "A"
    target.mkdir(parents=True)
    code = scaffold_arms.run(
        [
            "--task-package",
            str(task_package),
            "--arm",
            "A",
            "--target",
            str(target),
            "--manifest-out",
            str(tmp_path / "missing.arm-manifest.json"),
            "--check",
        ]
    )
    assert code == 2


def test_command_families_scanner_rejects_unknown_shape():
    broken = "tools:\n  - id: exec.pwsh\n    command_families:\n      - id: tests\n        patterns:\n   - x\n"
    tools, problems = scaffold_arms.scan_command_families(broken)
    assert problems, "形状不认识就必须报问题，不能静默抽成空清单"
    assert tools and tools[0]["families"] == [{"id": "tests", "pattern_count": 0}]


def test_command_families_scanner_reads_repository_registry():
    registry = REPO_ROOT / "examples" / "dsh" / "b-plan" / "tool-registry.local.yaml"
    tools, problems = scaffold_arms.scan_command_families(registry.read_text(encoding="utf-8"))
    assert problems == []
    by_tool = {item["tool"]: item for item in tools}
    assert by_tool["exec.pwsh"]["allowed_command_count"] == 13
    assert [item["id"] for item in by_tool["exec.pwsh"]["families"]] == [
        "tests",
        "readonly",
        "scripts",
    ]
    assert [item["pattern_count"] for item in by_tool["exec.pwsh"]["families"]] == [4, 6, 3]


# --------------------------------------------------------------------------- 增量与载荷


def _jsonl(records) -> str:
    return "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records)


def test_read_increments_reads_only_the_delta_by_offset(tmp_path):
    target = tmp_path / "tree"
    _write(
        target / ".policy" / "audit.jsonl",
        _jsonl([{"hook_event": "PreToolUse", "decision": "allow", "reason_code": "allow"}]),
    )
    patterns = [".policy/**/*.jsonl"]
    offsets = run_session.snapshot_offsets(target, patterns)
    assert set(offsets) == {".policy/audit.jsonl"}
    assert offsets[".policy/audit.jsonl"] > 0

    with (target / ".policy" / "audit.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(_jsonl([{"decision": "block", "reason_code": "path_out_of_scope"}]))
        handle.write(_jsonl([{"decision": "allow", "reason_code": "post_validated"}]))

    increments, _after, invalid = run_session.read_increments(target, patterns, offsets)
    assert invalid == []
    assert increments["records"] == 2, "只读增量：启动前那条不能重复计入"
    assert increments["totals"]["decisions"] == {"allow": 1, "block": 1}
    assert increments["totals"]["reasons"] == {"path_out_of_scope": 1, "post_validated": 1}
    assert increments["totals"]["post"] == {"post_validated": 1}
    entry = increments["streams"][".policy/audit.jsonl"]
    assert entry["created"] is False
    assert entry["offset_before"] == offsets[".policy/audit.jsonl"]
    assert entry["partial_line"] is False


def test_read_increments_flags_partial_line_and_truncation(tmp_path):
    target = tmp_path / "tree"
    audit = target / ".policy" / "audit.jsonl"
    _write(audit, _jsonl([{"decision": "allow"}]))
    patterns = [".policy/**/*.jsonl"]
    offsets = run_session.snapshot_offsets(target, patterns)

    with audit.open("a", encoding="utf-8", newline="") as handle:
        handle.write('{"decision": "block"')
    _increments, _after, invalid = run_session.read_increments(target, patterns, offsets)
    assert "partial_line:.policy/audit.jsonl" in invalid

    _write(audit, "")
    _increments, _after, invalid = run_session.read_increments(target, patterns, offsets)
    assert "stream_truncated:.policy/audit.jsonl" in invalid


def test_tree_diff_classifies_created_changed_deleted():
    before = {"keep.py": "a", "change.py": "a", "gone.py": "a"}
    after = {"keep.py": "a", "change.py": "b", "new.py": "b"}
    diff = run_session.tree_diff(before, after)
    assert diff == {"created": ["new.py"], "changed": ["change.py"], "deleted": ["gone.py"], "unchanged": 1}


def _payload_context() -> dict:
    return {
        "arm": "A",
        "task_id": "task-x",
        "arm_manifest": {"task": {"package": {"combined_digest": "sha256:" + "a" * 64}}},
        "profile": "headless",
        "dsh_version": "0.2.1-rc.2",
        "dsh_source": "app",
        "sandbox": "danger-full-access",
        "freeze": {
            "manifest_digest": "sha256:" + "b" * 64,
            "entries": 3,
            "check": {"strict": True, "exit_code": 0, "result_line": "RESULT: PASS"},
        },
    }


def _payload_increments() -> dict:
    return {
        "records": 3,
        "totals": {
            "decisions": {"allow": 2, "block": 1},
            "reasons": {"allow": 2, "path_out_of_scope": 1},
            "post": {"post_validated": 2},
        },
        "streams": {
            ".policy/audit.jsonl": {
                "path": ".policy/audit.jsonl",
                "offset_before": 0,
                "bytes_read": 10,
                "records": 3,
                "created": True,
                "partial_line": False,
                "error": None,
            }
        },
    }


def test_run_payload_field_set_and_no_absolute_paths(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-not-a-real-key")
    payload = run_session.build_run_payload(
        _payload_context(),
        exit_block={"code": 0, "timeout": False},
        increments=_payload_increments(),
        diff={"created": ["src/app.py"], "changed": [], "deleted": [], "unchanged": 3},
        invalid=[],
    )
    assert payload["schema_version"] == run_session.AB_RUN_SCHEMA_VERSION
    assert set(payload) == {
        "schema_version",
        "arm",
        "task",
        "host",
        "sandbox",
        "freeze",
        "exit",
        "readings",
    }
    assert set(payload["readings"]) == {
        "records",
        "decisions",
        "reasons",
        "post",
        "invalid",
        "streams",
        "diff",
        "summary_lines",
    }
    assert payload["sandbox"] == {"mode": "danger-full-access", "hook_spawn_required": True}
    assert payload["host"]["dsh"] == {"version": "0.2.1-rc.2", "source": "app"}
    assert common.check_no_absolute_paths(payload) == []


def test_run_payload_keeps_credential_out_and_records_presence_only(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-not-a-real-key")
    payload = run_session.build_run_payload(
        _payload_context(),
        exit_block={"code": 0, "timeout": False},
        increments=_payload_increments(),
        diff={"created": [], "changed": [], "deleted": [], "unchanged": 0},
        invalid=[],
    )
    text = json.dumps(payload, ensure_ascii=False)
    assert "dummy-not-a-real-key" not in text
    entries = {item["name"]: item for item in payload["host"]["env"]}
    assert entries["DEEPSEEK_API_KEY"]["present"] is True
    assert entries["DEEPSEEK_API_KEY"]["value_recorded"] is False
    assert entries["DEEPSEEK_API_KEY"] == {
        "name": "DEEPSEEK_API_KEY",
        "present": True,
        "value_recorded": False,
    }


def test_run_payload_summary_lines_are_deterministic_and_ordered():
    first = run_session.build_run_payload(
        _payload_context(),
        exit_block={"code": 1, "timeout": False},
        increments=_payload_increments(),
        diff={"created": ["a.py"], "changed": ["b.py"], "deleted": [], "unchanged": 1},
        invalid=["no_audit_records"],
    )
    second = run_session.build_run_payload(
        _payload_context(),
        exit_block={"code": 1, "timeout": False},
        increments=_payload_increments(),
        diff={"created": ["a.py"], "changed": ["b.py"], "deleted": [], "unchanged": 1},
        invalid=["no_audit_records"],
    )
    assert first == second
    lines = first["readings"]["summary_lines"]
    assert lines[0].startswith("arm=A task=task-x exit=1")
    assert "decisions=allow:2,block:1" in lines[1]
    assert any("invalid=no_audit_records" in line for line in lines)


def test_governed_arm_without_audit_records_is_invalid():
    conditions = run_session._invalid_conditions(
        "A", {"records": 0}, []
    )
    assert conditions == ["no_audit_records"], "受治理臂 0 条审计不是「没动作」，是「没跑起来」"
    assert run_session._invalid_conditions("C", {"records": 0}, []) == []


def test_build_overlay_uses_powershell_call_operator():
    text = run_session.build_overlay(
        plugin=Path("plugin.mjs"),
        project_dir=Path("C:/proj"),
        hook_python=Path("C:/py/python.exe"),
        platform_src=Path("C:/src"),
    )
    assert "- id: policy-hook" in text
    assert "command: \"$env:PYTHONPATH='C:/src'; & 'C:/py/python.exe' -m adapters.dsh.hooks" in text
    assert "projectDir: 'C:/proj'" in text
    assert text.endswith("\n")


# --------------------------------------------------------------------------- 前置门（dry-run，不发真机）


def _prepare_run(tmp_path: Path, task_package: Path, arm_config: Path) -> dict:
    """把一条 run 需要的东西都建好：臂树 + 臂清单 + 实验集 + 冻结清单。"""

    target, manifest_path, _payload = _scaffold(tmp_path, task_package, arm_config)
    set_path = _freeze_set(tmp_path, task_package, arm_config)
    freeze_path = tmp_path / "freeze.json"
    assert _freeze(set_path, freeze_path, "--write") == 0
    return {
        "root": tmp_path,
        "target": target,
        "manifest": manifest_path,
        "set": set_path,
        "freeze": freeze_path,
    }


@pytest.fixture()
def run_ready(tmp_path, task_package, arm_config):
    return _prepare_run(tmp_path, task_package, arm_config)


@pytest.fixture()
def run_ready_unsigned(tmp_path, task_package, arm_config):
    """臂配置里**没有**已签发文件：臂清单会记下未签字占位。"""

    (arm_config / "approval.json").unlink()
    (arm_config / "tool-registry.approved.json").unlink()
    return _prepare_run(tmp_path, task_package, arm_config)


def _run_session_args(ready, *, sandbox: str = "danger-full-access") -> list:
    return [
        "--arm-manifest",
        str(ready["manifest"]),
        "--freeze-manifest",
        str(ready["freeze"]),
        "--freeze-set",
        str(ready["set"]),
        "--target",
        str(ready["target"]),
        "--run-dir",
        str(ready["root"] / "run"),
        "--dsh-home",
        str(ready["root"] / "dsh-home"),
        "--platform-src",
        str(REPO_ROOT / "src"),
        "--sandbox",
        sandbox,
    ]


def _stub_host(monkeypatch) -> None:
    """不去 spawn dsh：把「找到哪一份宿主」与「版本号」钉成常量。"""

    monkeypatch.setattr(run_session, "find_dsh", lambda explicit: (Path(sys.executable), "explicit"))
    monkeypatch.setattr(run_session, "dsh_version", lambda dsh: "test-version")


def test_run_session_dry_run_blocks_on_missing_credential(run_ready, monkeypatch, capsys):
    _stub_host(monkeypatch)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    code = run_session.run(_run_session_args(run_ready))
    captured = capsys.readouterr()
    assert code == 2, "缺凭据不发车"
    assert "missing_credential" in captured.out + captured.err
    assert "LAUNCH: refused" in captured.out
    assert not (run_ready["root"] / "run" / "run.json").exists()


def test_run_session_dry_run_is_green_and_never_prints_the_credential(
    run_ready, monkeypatch, capsys
):
    _stub_host(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-not-a-real-key")
    code = run_session.run(_run_session_args(run_ready))
    captured = capsys.readouterr()
    assert code == 0, "前置全绿时 dry-run 的退出码就是「可以发车」"
    assert "PREFLIGHT: ok" in captured.out
    assert "dummy-not-a-real-key" not in captured.out + captured.err
    assert not (run_ready["root"] / "run").exists(), "dry-run 不写任何 run 产物"


def test_run_session_refuses_unsigned_placeholders(run_ready_unsigned, monkeypatch, capsys):
    _stub_host(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-not-a-real-key")
    code = run_session.run(_run_session_args(run_ready_unsigned))
    captured = capsys.readouterr()
    assert code == 2, "未签字占位不发车：本脚本不替使用者签审批条子"
    assert "approvals_unsigned" in captured.out + captured.err


def test_run_session_refuses_arm_tree_drift(run_ready, monkeypatch, capsys):
    _stub_host(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-not-a-real-key")
    _write(run_ready["target"] / "src" / "app.py", "VALUE = 42\n")
    code = run_session.run(_run_session_args(run_ready))
    captured = capsys.readouterr()
    assert code == 2
    assert "arm_tree_drift" in captured.out + captured.err


def test_run_session_refuses_sandbox_that_breaks_hook_spawn(run_ready, monkeypatch, capsys):
    _stub_host(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-not-a-real-key")
    code = run_session.run(_run_session_args(run_ready, sandbox="workspace-write"))
    captured = capsys.readouterr()
    assert code == 2
    assert "sandbox_blocks_hook_spawn" in captured.out + captured.err


def test_run_session_refuses_undeclared_sandbox(run_ready, monkeypatch, capsys):
    _stub_host(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-not-a-real-key")
    code = run_session.run(_run_session_args(run_ready, sandbox="unknown"))
    captured = capsys.readouterr()
    assert code == 2
    assert "sandbox_undeclared" in captured.out + captured.err


def test_run_session_refuses_dsh_home_equal_to_host_home(run_ready, monkeypatch, capsys):
    _stub_host(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-not-a-real-key")
    args = _run_session_args(run_ready)
    index = args.index("--dsh-home") + 1
    args[index] = str(Path.home() / ".dsh")
    code = run_session.run(args)
    captured = capsys.readouterr()
    assert code == 2
    assert "dsh_home_unsafe" in captured.out + captured.err

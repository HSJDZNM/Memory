"""R-d 差集工具（tools/decision_diff.py）的回归：三列、指针、稳定字节、脱敏与退出码。

判据来自 05 §3.5 与 AGENTS 第 55 条：差集必须**字段级**（含 violations 内容）、**可复现**
（相同输入逐字节相同）、**不泄漏**（密钥 / 绝对路径）；退出码 0/1/2 属于 CLI 语义——
它**不是**恒 0 的只报告读数，"有差异"必须是 1。所以下面每个"改了东西"的用例都同时断言
计数、指针形态与退出码，而不是只看输出里有没有那个词。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DECISIONS = REPO_ROOT / "tests" / "fixtures" / "decisions"

# 合成凭据按片段拼装：整串字面量会被仓库的凭据门禁（tools/secret_scan.py）按形态拦下，
# 而这条用例要证明的是**被测工具**会脱敏，不是门禁会豁免。
FAKE_SECRET = "sk-" + "live-0000000000000000"

# 仓库内 / 仓库外的两个绝对路径：前者必须折叠成仓库相对路径，后者必须写成 <outside-workspace>。
INSIDE_PATH = str(REPO_ROOT / "src" / "policy" / "models.py")
OUTSIDE_PATH = str(REPO_ROOT.parent / "not-this-repo" / "payload.json")


def _load():
    """按路径加载被测脚本（tools/ 不在包内，也不依赖 conftest 的 sys.path 注入顺序）。"""

    spec = importlib.util.spec_from_file_location(
        "decision_diff_under_test", REPO_ROOT / "tools" / "decision_diff.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # 标准配方：exec 之前登记，模块内的相对导入才成立
    spec.loader.exec_module(module)
    return module


def _write(path: Path, payload) -> Path:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _run(module, capsys, *argv):
    """跑一次 CLI，返回 (退出码, stdout, stderr)；argv 里的 Path 会被转成字符串。"""

    code = module.run([str(item) for item in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _json_diff(module, capsys, base, head):
    """跑 --json 形态；成功路径不写 stderr。"""

    code, out, err = _run(module, capsys, "--base", base, "--head", head, "--json")
    assert err == ""
    return code, json.loads(out)


def _violation(rule_id: str, severity: str) -> dict:
    return {
        "rule_id": rule_id,
        "rule_version": 1,
        "severity": severity,
        "message": "夹具违规：" + rule_id,
        "evidence": {"kind": "dependency", "file": "src/order/controller.py"},
    }


def test_the_same_payload_is_identical_and_exits_zero(capsys):
    module = _load()
    code, payload = _json_diff(module, capsys, DECISIONS / "allow.json", DECISIONS / "allow.json")

    assert code == module.EXIT_IDENTICAL == 0
    assert payload["identical"] is True
    assert payload["exit_code"] == 0
    assert payload["counts"] == {"added": 0, "modified": 0, "removed": 0, "total": 0}
    assert payload["pairs"][0]["entries"] == []
    # 版本轴（AGENTS 第 55 条）与退出码语义都写在载荷里，读的人不必回头翻 README。
    assert payload["schema_version"] == module.DECISION_DIFF_SCHEMA_VERSION == "1.0"
    assert payload["exit_codes"] == {"0": "无差异", "1": "有差异", "2": "输入 / 用法错误"}
    assert "（无差异）" in module.render_human(payload)


def test_a_changed_decision_value_is_one_modified_entry(tmp_root, capsys):
    module = _load()
    fixture = json.loads((DECISIONS / "allow.json").read_text(encoding="utf-8"))
    base = _write(tmp_root / "decision" / "base.json", fixture)
    changed = dict(fixture)
    changed["decision"] = "allow_with_warnings"
    head = _write(tmp_root / "decision" / "head.json", changed)

    code, payload = _json_diff(module, capsys, base, head)

    assert code == module.EXIT_DIFFERENT == 1
    assert payload["pairs"][0]["entries"] == [
        {
            "kind": "modified",
            "pointer": "decision",
            "before": "allow",
            "after": "allow_with_warnings",
        }
    ]
    assert payload["counts"] == {"added": 0, "modified": 1, "removed": 0, "total": 1}
    assert payload["pairs"][0]["name"] == "base.json -> head.json"


def test_a_nested_field_pointer_writes_the_whole_path(tmp_root, capsys):
    module = _load()
    base = _write(
        tmp_root / "nested" / "base.json",
        {"selected_checks": {"status": "pending", "count": 2}},
    )
    head = _write(
        tmp_root / "nested" / "head.json",
        {"selected_checks": {"status": "ok", "count": 2}},
    )

    code, payload = _json_diff(module, capsys, base, head)

    assert code == 1
    pointers = [entry["pointer"] for entry in payload["pairs"][0]["entries"]]
    assert pointers == ["selected_checks.status"]


def test_an_added_key_is_added_and_a_deleted_key_is_removed(tmp_root, capsys):
    module = _load()
    base = _write(tmp_root / "keys" / "base.json", {"a": 1})
    head = _write(tmp_root / "keys" / "head.json", {"a": 1, "b": 2})

    code, payload = _json_diff(module, capsys, base, head)
    assert code == 1
    assert payload["pairs"][0]["entries"] == [
        {"kind": "added", "pointer": "b", "before": None, "after": 2}
    ]

    code, payload = _json_diff(module, capsys, head, base)
    assert code == 1
    assert payload["pairs"][0]["entries"] == [
        {"kind": "removed", "pointer": "b", "before": 2, "after": None}
    ]


def test_a_new_violation_is_added_without_touching_the_other_ones(tmp_root, capsys):
    module = _load()
    base_violations = [_violation("ARCH-001", "error"), _violation("CODING-002", "warning")]
    head_violations = base_violations + [_violation("DOC-001", "warning")]
    base = _write(tmp_root / "violations" / "base.json", {"violations": base_violations})
    head = _write(tmp_root / "violations" / "head.json", {"violations": head_violations})

    code, payload = _json_diff(module, capsys, base, head)
    entries = payload["pairs"][0]["entries"]

    assert code == 1
    assert len(entries) == 1, "多一条只应产生一条 added：其它条不误报 modified"
    assert entries[0] == {
        "kind": "added",
        "pointer": "violations[rule_id=DOC-001]",
        "before": None,
        "after": head_violations[2],
    }
    assert payload["counts"] == {"added": 1, "modified": 0, "removed": 0, "total": 1}


def test_a_changed_field_inside_an_identified_element_keeps_its_identity(tmp_root, capsys):
    module = _load()
    base = _write(
        tmp_root / "identified" / "base.json",
        {"violations": [_violation("ARCH-001", "error"), _violation("CODING-002", "warning")]},
    )
    head = _write(
        tmp_root / "identified" / "head.json",
        {"violations": [_violation("ARCH-001", "warning"), _violation("CODING-002", "warning")]},
    )

    code, payload = _json_diff(module, capsys, base, head)

    assert code == 1
    assert payload["pairs"][0]["entries"] == [
        {
            "kind": "modified",
            "pointer": "violations[rule_id=ARCH-001].severity",
            "before": "error",
            "after": "warning",
        }
    ]


def test_sequences_use_index_pointers_and_an_insertion_does_not_cascade(tmp_root, capsys):
    module = _load()
    base = _write(
        tmp_root / "sequences" / "base.json",
        {"matched_rules": ["ARCH-001@1", "CODING-002@1"], "items": [{"x": 1}, {"y": 2}]},
    )
    head = _write(
        tmp_root / "sequences" / "head.json",
        {
            "matched_rules": ["ARCH-001@1", "ARCH-004@1", "CODING-002@1"],
            "items": [{"x": 3}, {"y": 2}],
        },
    )

    code, payload = _json_diff(module, capsys, base, head)
    entries = payload["pairs"][0]["entries"]

    assert code == 1
    # 中间插一条：只有一条 added，后面那条不算 modified（对比"逐位置比较"会报 2 条）。
    matching = [entry for entry in entries if entry["pointer"].startswith("matched_rules")]
    assert matching == [
        {"kind": "added", "pointer": "matched_rules[1]", "before": None, "after": "ARCH-004@1"}
    ]
    # 列表元素没有共同可识别键时走逐位置配对：索引指针 + 字段级 modified。
    assert {
        "kind": "modified",
        "pointer": "items[0].x",
        "before": 1,
        "after": 3,
    } in entries


def test_json_and_md_outputs_are_byte_identical_across_runs(capsys):
    """相同输入两次运行逐字节相同（载荷里不带时戳、不带 run 标识）。"""

    module = _load()
    arguments = ("--base", DECISIONS / "block.json", "--head", DECISIONS / "approval.json")
    first = {flag: _run(module, capsys, *arguments, flag) for flag in ("--json", "--md")}
    second = {flag: _run(module, capsys, *arguments, flag) for flag in ("--json", "--md")}

    for flag in ("--json", "--md"):
        assert first[flag][0] == second[flag][0] == 1
        assert first[flag][1] == second[flag][1]


def test_absolute_paths_and_secrets_never_reach_the_output(tmp_root, capsys):
    module = _load()
    base = _write(
        tmp_root / "leak" / "base.json",
        {
            "evidence": {"file": INSIDE_PATH, "note": "old"},
            "extra": {"path": OUTSIDE_PATH, "token": FAKE_SECRET},
        },
    )
    head = _write(
        tmp_root / "leak" / "head.json",
        {"evidence": {"file": "src/other.py", "note": "new"}},
    )

    for flags in ((), ("--json",), ("--md",)):
        code, out, err = _run(module, capsys, "--base", base, "--head", head, *flags)
        text = out + err
        assert code == 1
        assert str(REPO_ROOT) not in text
        assert str(REPO_ROOT.parent) not in text
        assert "sk-live" not in text
        assert "<redacted-secret>" in text
        assert "<outside-workspace>" in text
        assert "src/policy/models.py" in text

    code, payload = _json_diff(module, capsys, base, head)
    entries = payload["pairs"][0]["entries"]
    # 整条被删对象的内部也被逐层脱敏（不是只脱顶层字符串）。
    assert entries[-1] == {
        "kind": "removed",
        "pointer": "extra",
        "before": {"path": "<outside-workspace>", "token": "<redacted-secret>"},
        "after": None,
    }


def test_broken_inputs_exit_two_without_a_traceback(tmp_root, capsys):
    module = _load()
    broken = tmp_root / "broken" / "broken.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{ not json\n", encoding="utf-8", newline="\n")
    scalar = _write(tmp_root / "broken" / "scalar.json", 42)
    empty = tmp_root / "broken" / "empty-dir"
    empty.mkdir(parents=True, exist_ok=True)
    allow = DECISIONS / "allow.json"

    cases = (
        ("不是合法 JSON", (broken, broken)),
        ("路径不存在", (tmp_root / "broken" / "nope.json", tmp_root / "broken" / "nope.json")),
        ("根部必须是 dict 或 list", (scalar, scalar)),
        ("必须同形", (allow, empty)),
    )
    for expected, (base, head) in cases:
        code, out, err = _run(module, capsys, "--base", base, "--head", head)
        assert code == module.EXIT_USAGE == 2, expected
        assert "Traceback" not in err, expected
        assert expected in err, expected
        assert str(REPO_ROOT) not in err, "错误信息同样不许泄漏绝对路径"

    code, out, err = _run(module, capsys, "--base", empty, "--head", empty)
    assert code == 2
    assert "目录里没有 *.json" in err


def test_missing_required_arguments_is_a_usage_error(capsys):
    module = _load()
    with pytest.raises(SystemExit) as info:
        module.run(["--base", str(DECISIONS / "allow.json")])
    assert info.value.code == 2


def test_directory_mode_pairs_by_name_and_missing_side_is_a_whole_payload(tmp_root, capsys):
    module = _load()
    base_dir = tmp_root / "pairing" / "base"
    head_dir = tmp_root / "pairing" / "head"
    _write(base_dir / "shared.json", {"decision": "allow"})
    _write(head_dir / "shared.json", {"decision": "block"})
    _write(base_dir / "only-base.json", {"x": 1})
    _write(head_dir / "only-head.json", {"y": 2})

    code, payload = _json_diff(module, capsys, base_dir, head_dir)
    by_name = {pair["name"]: pair for pair in payload["pairs"]}

    assert code == 1
    assert payload["input"] == "directory"
    assert [pair["name"] for pair in payload["pairs"]] == [
        "only-base.json",
        "only-head.json",
        "shared.json",
    ]
    assert by_name["only-head.json"]["base"] is None
    assert by_name["only-head.json"]["entries"] == [
        {"kind": "added", "pointer": ".", "before": None, "after": {"y": 2}}
    ]
    assert by_name["only-base.json"]["head"] is None
    assert by_name["only-base.json"]["entries"] == [
        {"kind": "removed", "pointer": ".", "before": {"x": 1}, "after": None}
    ]
    assert by_name["shared.json"]["counts"] == {
        "added": 0,
        "modified": 1,
        "removed": 0,
        "total": 1,
    }
    assert by_name["shared.json"]["base"]["digest"].startswith("sha256:")
    assert payload["counts"] == {"added": 1, "modified": 1, "removed": 1, "total": 3}


def test_human_summary_reports_counts_and_only_the_first_n(capsys):
    module = _load()
    arguments = ("--base", DECISIONS / "block.json", "--head", DECISIONS / "approval.json")

    code, out, err = _run(module, capsys, *arguments)
    assert code == 1
    assert err == ""
    assert "合计: added=1 modified=2 removed=2 total=5" in out
    assert "DECISION_DIFF: added=1 modified=2 removed=2 total=5 identical=false" in out

    code, out, err = _run(module, capsys, *arguments, "--limit", "1")
    assert code == 1
    assert "余 4 条" in out

    code, out, err = _run(module, capsys, *arguments, "--limit", "0")
    assert code == 1
    assert "余 5 条" in out
    assert "[modified]" not in out


def test_out_writes_the_same_bytes_with_a_single_trailing_newline(tmp_root, capsys):
    module = _load()
    arguments = ("--base", DECISIONS / "allow.json", "--head", DECISIONS / "warning.json")
    target = tmp_root / "written" / "nested" / "diff.md"

    code, out, err = _run(module, capsys, *arguments, "--md", "--out", target)
    assert code == 1
    assert err == ""
    assert "已写入" in out

    written = target.read_text(encoding="utf-8")
    assert written.endswith("\n") and not written.endswith("\n\n")
    assert "\r" not in written

    code, stdout_md, err = _run(module, capsys, *arguments, "--md")
    assert written == stdout_md

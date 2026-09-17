"""Phase 0 Loader 测试：排序、重复 ID、错误定位、原子加载。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from policy.loader import (
    LoaderError,
    RuleFileError,
    collect_rule_files,
    load_rule_file,
    load_rule_set,
    load_rules,
)
from policy.models import RuleSet

from conftest import ARCH_DIR, REPO_ROOT, RULE_DOCUMENT, rule_document, write_rule


def test_repository_rule_loads_with_expected_identity() -> None:
    loaded = load_rule_file(
        ARCH_DIR / "ARCH-001.yaml",
        repo_path="policies/architecture/ARCH-001.yaml",
        repo_root=REPO_ROOT,
    )

    assert loaded.rule.canonical_id == "ARCH-001@1"
    assert loaded.repo_path == "policies/architecture/ARCH-001.yaml"


def test_empty_directory_yields_empty_rule_set(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    root.mkdir()

    rules = load_rule_set([root], repo_root=tmp_root)

    assert isinstance(rules, RuleSet)
    assert len(rules) == 0
    assert rules.ids == ()
    assert rules.source_paths == ()


def test_missing_directory_is_a_loader_error(tmp_root: Path) -> None:
    with pytest.raises(LoaderError) as error:
        load_rule_set([tmp_root / "nope"], repo_root=tmp_root)

    assert "规则目录不存在" in str(error.value)


def test_rule_file_with_wrong_suffix_is_ignored(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    root.mkdir()
    (root / "notes.txt").write_text("not a rule", encoding="utf-8")
    (root / ".hidden.yaml").write_text("id: ARCH-999", encoding="utf-8")

    assert collect_rule_files(root) == ()


def test_files_are_loaded_in_normalized_path_order(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    write_rule(root / "zeta" / "ARCH-200.yaml", rule_document(id="ARCH-200", version=1), yaml_module=yaml)
    write_rule(root / "alpha" / "ARCH-100.yaml", rule_document(id="ARCH-100", version=1), yaml_module=yaml)
    write_rule(root / "ARCH-050.yaml", rule_document(id="ARCH-050", version=1), yaml_module=yaml)

    loaded = load_rules(root, repo_root=tmp_root)

    assert [item.repo_path for item in loaded] == [
        "policies/ARCH-050.yaml",
        "policies/alpha/ARCH-100.yaml",
        "policies/zeta/ARCH-200.yaml",
    ]
    assert load_rule_set([root], repo_root=tmp_root).ids == (
        "ARCH-050@1",
        "ARCH-100@1",
        "ARCH-200@1",
    )


def test_duplicate_rule_id_is_rejected_with_both_paths(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    write_rule(root / "a" / "ARCH-001.yaml", rule_document(), yaml_module=yaml)
    write_rule(root / "b" / "ARCH-001-copy.yaml", rule_document(), yaml_module=yaml)

    with pytest.raises(RuleFileError) as error:
        load_rules(root, repo_root=tmp_root)

    message = str(error.value)
    assert "ARCH-001" in message
    assert "policies/b/ARCH-001-copy.yaml" in message
    assert "policies/a/ARCH-001.yaml" in message


def test_duplicate_rule_id_across_directories_is_rejected(tmp_root: Path) -> None:
    first = tmp_root / "policies"
    second = tmp_root / "extra-policies"
    write_rule(first / "ARCH-001.yaml", rule_document(), yaml_module=yaml)
    write_rule(second / "ARCH-001.yaml", rule_document(version=2), yaml_module=yaml)

    with pytest.raises(RuleFileError):
        load_rule_set([first, second], repo_root=tmp_root)


def test_broken_yaml_reports_path_and_position(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    root.mkdir()
    broken = root / "ARCH-001.yaml"
    broken.write_text("id: ARCH-001\nversion: [1, 2\n", encoding="utf-8")

    with pytest.raises(RuleFileError) as error:
        load_rules(root, repo_root=tmp_root)

    assert error.value.repo_path == "policies/ARCH-001.yaml"
    assert error.value.line is not None
    assert "YAML 解析失败" in str(error.value)
    assert "policies/ARCH-001.yaml:" in str(error.value)


@pytest.mark.parametrize(
    ("document", "expected"),
    [({"id": "ARCH-001"}, "version"), (RULE_DOCUMENT, None)],
)
def test_partial_document_reports_missing_field(tmp_root: Path, document: dict, expected: str | None) -> None:
    root = tmp_root / "policies"
    write_rule(root / "ARCH-001.yaml", document, yaml_module=yaml)

    if expected is None:
        assert load_rules(root, repo_root=tmp_root)[0].rule.canonical_id == "ARCH-001@1"
        return

    with pytest.raises(RuleFileError) as error:
        load_rules(root, repo_root=tmp_root)

    assert expected in str(error.value)
    assert error.value.field is not None


@pytest.mark.parametrize(
    "text",
    ["", "# 只有注释\n", "- ARCH-001\n", "just a string\n"],
)
def test_non_mapping_documents_are_rejected(tmp_root: Path, text: str) -> None:
    root = tmp_root / "policies"
    root.mkdir()
    (root / "ARCH-001.yaml").write_text(text, encoding="utf-8")

    with pytest.raises(RuleFileError) as error:
        load_rules(root, repo_root=tmp_root)

    assert "policies/ARCH-001.yaml" in str(error.value)


def test_wrong_type_for_known_field_reports_field_path(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    write_rule(root / "ARCH-001.yaml", rule_document(version="one"), yaml_module=yaml)

    with pytest.raises(RuleFileError) as error:
        load_rules(root, repo_root=tmp_root)

    assert error.value.field == "version"


def test_one_bad_file_leaves_no_half_rule_set(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    write_rule(root / "ARCH-050.yaml", rule_document(id="ARCH-050", version=1), yaml_module=yaml)
    write_rule(root / "ARCH-060.yaml", rule_document(id="ARCH-060", version=1), yaml_module=yaml)
    (root / "ARCH-070.yaml").write_text("id: ARCH-070\nversion: 0\n", encoding="utf-8")

    with pytest.raises(RuleFileError):
        load_rule_set([root], repo_root=tmp_root)

    # 修正坏文件后必须得到完整规则集：不存在被写坏的一半状态
    (root / "ARCH-070.yaml").write_text(
        yaml.safe_dump(rule_document(id="ARCH-070", version=1), allow_unicode=True),
        encoding="utf-8",
    )

    assert load_rule_set([root], repo_root=tmp_root).ids == (
        "ARCH-050@1",
        "ARCH-060@1",
        "ARCH-070@1",
    )


def test_load_rule_file_missing_path_is_loader_error(tmp_root: Path) -> None:
    with pytest.raises(LoaderError):
        load_rule_file(tmp_root / "missing.yaml", repo_path="policies/missing.yaml")


def test_rule_file_error_carries_field_and_rule_id(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    write_rule(root / "ARCH-001.yaml", rule_document(severity="fatal"), yaml_module=yaml)

    with pytest.raises(RuleFileError) as error:
        load_rules(root, repo_root=tmp_root)

    assert error.value.rule_id == "ARCH-001"
    assert error.value.field == "severity"


def test_loading_twice_is_stable(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    write_rule(root / "ARCH-001.yaml", rule_document(), yaml_module=yaml)

    first = load_rule_set([root], repo_root=tmp_root)
    second = load_rule_set([root], repo_root=tmp_root)

    assert first.identity == second.identity
    assert first.model_dump() == second.model_dump()

"""Phase 0 Loader 测试：排序、重复 ID、错误定位、原子加载。

另有 N14 的一组用例：依赖类 checker 的规则必须在加载期声明 language 维度
（夹具在 `tests/fixtures/invalid_rules/`，见那里的 README）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from policy.engine import evaluate
from policy.loader import (
    LANGUAGE_DEPENDENT_CHECKERS,
    LoaderError,
    RuleFileError,
    collect_rule_files,
    load_rule_file,
    load_rule_set,
    load_rules,
)
from policy.models import Decision, PolicyContext, Rule, RuleSet

from conftest import (
    ARCH_DIR,
    FIXTURES_DIR,
    REPO_ROOT,
    RULE_DOCUMENT,
    rule_document,
    write_rule,
)


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


def test_the_language_gate_reads_the_dispatch_table_not_a_second_copy() -> None:
    """N14 的判据只有一份：加载期门槛直接读分派表那一侧的声明。

    手抄的第二份与分派表逐字相同，靠的是"新增依赖类 checker 时记得两处一起改"——
    忘了同步，门槛就静默失效，而那正是这条门槛存在的理由。
    """

    from policy import checkers

    assert LANGUAGE_DEPENDENT_CHECKERS is checkers.LANGUAGE_DEPENDENT_CHECKERS
    assert checkers.LANGUAGE_DEPENDENT_CHECKERS <= checkers.SUPPORTED_CHECKERS, (
        "语言门槛的集合必须是分派表里真实存在的 checker"
    )


def test_rule_directory_that_cannot_be_walked_fails_closed(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """规则目录读不全必须失败关闭（M2）。

    os.walk 的 onerror 默认是 None：底层 scandir 失败（无权限、目录刚被删）会被**静默忽略**，
    于是"少读了几条规则"和"规则集本来就只有这几条"长得一模一样——而规则集是判定的唯一依据。
    """

    root = tmp_root / "policies"
    root.mkdir()

    def fake_walk(_path: object, onerror: object = None, **_kwargs: object) -> object:
        assert callable(onerror), "收集规则文件必须给 os.walk 一个 onerror，不能静默跳过读不到的目录"
        onerror(PermissionError("拒绝访问"))
        return iter(())

    monkeypatch.setattr(os, "walk", fake_walk)

    with pytest.raises(LoaderError) as error:
        collect_rule_files(root)

    assert "规则目录不可读" in str(error.value)


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


# --------------------------------------------------- N14：依赖类 checker 的 language 门槛
#
# 缺口：`language` 解析不出来时为 None → 依赖集是空元组 → 依赖类 checker 于是 allow，
# 而「为什么 allow」（语言未知）没有任何地方写下来。43 条规则里唯一用
# forbidden_dependency 的 ARCH-001 恰好在 scope 里声明了 language: python，所以今天
# 没有洞 —— 那是规则作者的纪律，不是代码保证。下面这组用例把纪律变成会失败的检查。

INVALID_RULES_DIR = FIXTURES_DIR / "invalid_rules"


def test_dependency_rule_without_language_is_rejected_at_load_time() -> None:
    """不声明 language 的依赖规则必须**读不进来**，且错误信息要讲清为什么。"""

    with pytest.raises(RuleFileError) as error:
        load_rules(INVALID_RULES_DIR / "no-language", repo_root=REPO_ROOT)

    message = str(error.value)
    assert error.value.rule_id == "ARCH-900"
    assert error.value.field == "scope.language"
    assert "没有声明 language" in message
    # 错误信息必须自己解释「为什么」，否则下一个人只会把它当成格式检查：
    assert "依赖集" in message  # 语言未知 = 依赖集为空
    assert "静默放行" in message  # 而这个 allow 的理由没有任何地方写下来


def test_dependency_rule_with_wildcard_language_is_rejected_at_load_time() -> None:
    """`language: "*"` 与「不声明」在判定上等价（该维度不限制），所以同样拒绝。"""

    with pytest.raises(RuleFileError) as error:
        load_rules(INVALID_RULES_DIR / "wildcard-language", repo_root=REPO_ROOT)

    message = str(error.value)
    assert error.value.rule_id == "ARCH-901"
    assert error.value.field == "scope.language"
    assert "不限制" in message
    assert "依赖集" in message


def test_dependency_rule_with_declared_language_still_loads() -> None:
    """正例对照：同一种规则体，只要声明了 language 就照常加载。"""

    loaded = load_rules(INVALID_RULES_DIR / "declared-language", repo_root=REPO_ROOT)

    assert [item.rule.canonical_id for item in loaded] == ["ARCH-902@1"]
    assert loaded[0].rule.scope.declared_dimensions["language"] == "python"


def test_language_gate_does_not_apply_to_other_checkers(tmp_root: Path) -> None:
    """门槛只针对依赖类 checker：docstring 类规则没有 language 维度是合法的。

    否则这条检查会变成「所有规则都必须声明 language」，那是另一条（更严的）契约，
    与本缺口无关，也会把 43 条规则里的绝大多数判红。
    """

    root = tmp_root / "policies"
    write_rule(
        root / "DOC-900.yaml",
        rule_document(
            id="DOC-900",
            scope={"layer": "controller"},
            enforcement={"type": "deterministic", "checker": "missing_docstring"},
            rule={"missing_docstring": {"targets": ["module"]}},
        ),
        yaml_module=yaml,
    )

    assert load_rule_set([root], repo_root=tmp_root).ids == ("DOC-900@1",)


def test_repository_rule_declares_the_language_dimension() -> None:
    """既有规则（43 条里唯一用依赖 checker 的那条）不受影响，且它本来就写对了。"""

    loaded = load_rule_file(
        ARCH_DIR / "ARCH-001.yaml",
        repo_path="policies/architecture/ARCH-001.yaml",
        repo_root=REPO_ROOT,
    )

    assert loaded.rule.scope.declared_dimensions["language"] == "python"


def test_the_gate_is_about_a_silent_allow_not_a_format_rule() -> None:
    """把「为什么非在加载期拦不可」钉成可失败的断言（而不是注释里的一句话）。

    这里**绕过加载器**直接构造规则（Rule 模型本身不查 scope.language，见
    tests/unit/test_engine.py 的「缺省 = 不限制」）：在「语言解析不出来（None）+
    依赖集为空」的上下文上，它判 allow，而且既不在 violations 里，也不在
    skipped_rules 里 —— 决策里没有任何地方写得出「为什么放行」。
    加载期检查要拦的就是这种写法：让它在规则进仓库时失败，而不是等某个 Adapter
    声明不出语言时静默放行。
    """

    rule = Rule.model_validate(rule_document(scope={"layer": "controller"}))
    context = PolicyContext(
        request_id="req-n14",
        file="src/shop/order_controller.py",
        layer="controller",
        dependencies=[],
    )

    result = evaluate(RuleSet(rules=(rule,), source_paths=("fixture",)), context)

    assert context.language is None
    assert result.decision is Decision.ALLOW
    assert not result.violations
    assert not result.skipped_rules, "规则没有 language 限制，所以它会「相关」地判 allow"

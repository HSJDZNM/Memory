"""Phase 5 验证器注册表与项目档案的加载测试：数据写错必须报错，不能悄悄少跑验证器。"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, VALIDATION_DIR, fake_tool_spec, write_validation_config
from policy.evidence import ValidatorKind
from policy.models import RuleValidationError
from validators.models import Registry, ToolSpec, ValidatorSpec
from validators.registry import RegistryError, config_digest, load_config, load_registry


def registry_document() -> dict:
    return yaml.safe_load((VALIDATION_DIR / "validators.yaml").read_text(encoding="utf-8"))


def test_real_registry_and_profiles_load() -> None:
    config = load_config(root=REPO_ROOT)

    assert config.registry.stages == (
        "source",
        "ast",
        "dependency",
        "docstring",
        "lint",
        "type",
        "tests",
    )
    # 阶段顺序 source → ast → dependency → docstring → lint → type → tests
    assert [spec.id for spec in config.registry.validators_for_language("python")] == [
        "py.source",
        "py.ast",
        "py.depgraph",
        "py.docstring",
        "tool.ruff",
        "tool.mypy",
        "tool.pytest",
    ]
    checkers = config.registry.checkers_for_language("python")
    assert checkers["forbidden_dependency"] == ("py.depgraph",)
    assert checkers["style_lint"] == ("tool.ruff",)
    assert config.project.language_for("src/shop/order_service.py") == "python"
    assert config.project.component_for("src/shop/order_repository.py") == "repository"
    assert config.layout.is_production("src/shop/order_service.py") is True
    assert config.layout.is_test("tests/test_order_service.py") is True


def test_config_digest_changes_with_content(tmp_root: Path) -> None:
    first = VALIDATION_DIR / "validators.yaml"
    copy = tmp_root / "validators.yaml"
    # newline="" 保持 LF：默认的换行转换会在 Windows 上写出 CRLF，字节就不同了
    copy.write_text(first.read_text(encoding="utf-8"), encoding="utf-8", newline="")

    assert config_digest(copy) == config_digest(first)
    copy.write_text(
        first.read_text(encoding="utf-8") + "# drift" + chr(10), encoding="utf-8", newline=""
    )
    assert config_digest(copy) != config_digest(first)
    assert config_digest(None) is None


def _load(document: dict, tmp_root: Path) -> Registry:
    write_validation_config(tmp_root, registry=document)
    return load_registry(tmp_root / "validation" / "validators.yaml", root=REPO_ROOT)


def test_unknown_checker_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    document["validators"][2]["checkers"] = ["llm_judgement"]

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "llm_judgement" in str(error.value)


def test_duplicate_validator_id_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    document["validators"].append(copy.deepcopy(document["validators"][0]))

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "重复 ID" in str(error.value)


def test_requires_must_reference_a_declared_validator(tmp_root: Path) -> None:
    document = registry_document()
    document["validators"][1]["requires"] = ["py.absent"]

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "py.absent" in str(error.value)


def test_requires_must_run_in_an_earlier_stage(tmp_root: Path) -> None:
    document = registry_document()
    document["validators"][1]["requires"] = ["py.depgraph"]

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "必须先于" in str(error.value)


def test_rule_pack_must_reference_declared_validators(tmp_root: Path) -> None:
    document = registry_document()
    document["rule_packs"][0]["validators"] = ["py.ghost"]

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "py.ghost" in str(error.value)


def test_unknown_stage_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    document["validators"][0]["stage"] = "quantum"

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "quantum" in str(error.value)


def test_missing_checker_coverage_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    document["validators"] = [
        item for item in document["validators"] if item["id"] != "tool.pytest"
    ]
    document["rule_packs"][1]["validators"] = ["tool.ruff", "tool.mypy"]

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "failing_tests" in str(error.value) or "missing_tests" in str(error.value)


def test_missing_tool_config_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    for item in document["validators"]:
        if item["id"] == "tool.ruff":
            item["tool"]["config"] = "validation/absent.toml"

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "配置不存在" in str(error.value)


def test_unknown_placeholder_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    for item in document["validators"]:
        if item["id"] == "tool.ruff":
            item["tool"]["argv"] = ["check", "{shell}"]

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "未知占位符" in str(error.value)


def test_unknown_fact_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    document["validators"][1]["facts"] = ["telemetry"]

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "事实种类" in str(error.value)


def test_external_validator_requires_a_tool_declaration() -> None:
    with pytest.raises(Exception) as error:
        ValidatorSpec(
            id="tool.custom", version="1.0", kind=ValidatorKind.EXTERNAL, stage="lint"
        )

    assert "必须声明 tool" in str(error.value)


def test_builtin_validator_must_not_declare_a_tool() -> None:
    with pytest.raises(Exception) as error:
        ValidatorSpec(
            id="py.custom",
            version="1.0",
            kind=ValidatorKind.BUILTIN,
            stage="lint",
            tool=ToolSpec(command=("ruff",)),
        )

    assert "不能声明 tool" in str(error.value)


def test_version_pattern_must_capture_a_version() -> None:
    with pytest.raises(Exception) as error:
        ToolSpec(command=("ruff",), version_pattern=r"ruff [0-9.]+")

    assert "捕获组" in str(error.value)


def test_project_profile_rejects_escaping_python_roots(tmp_root: Path) -> None:
    document = yaml.safe_load((VALIDATION_DIR / "project.yaml").read_text(encoding="utf-8"))
    document["python_roots"] = ["../outside"]
    write_validation_config(tmp_root, project=document)

    with pytest.raises(RegistryError) as error:
        load_config(root=tmp_root, registry=VALIDATION_DIR / "validators.yaml")

    assert "python_roots" in str(error.value)


def test_duplicate_component_is_rejected(tmp_root: Path) -> None:
    document = yaml.safe_load((VALIDATION_DIR / "project.yaml").read_text(encoding="utf-8"))
    document["components"].append(copy.deepcopy(document["components"][0]))
    write_validation_config(tmp_root, project=document)

    with pytest.raises(RegistryError) as error:
        load_config(root=tmp_root, registry=VALIDATION_DIR / "validators.yaml")

    assert "重复 ID" in str(error.value)


def test_duplicate_escalation_level_is_rejected(tmp_root: Path) -> None:
    document = yaml.safe_load((VALIDATION_DIR / "test-layout.yaml").read_text(encoding="utf-8"))
    document["escalation"].append(copy.deepcopy(document["escalation"][0]))
    write_validation_config(tmp_root, test_layout=document)

    with pytest.raises(RegistryError) as error:
        load_config(root=tmp_root, registry=VALIDATION_DIR / "validators.yaml")

    assert "重复 ID" in str(error.value)


def test_unknown_field_in_registry_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    document["validators"][0]["surprise"] = True

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "surprise" in str(error.value)


def test_registry_error_carries_the_file_path(tmp_root: Path) -> None:
    (tmp_root / "validation").mkdir(parents=True)
    target = tmp_root / "validation" / "validators.yaml"
    target.write_text("version: [1," + chr(10), encoding="utf-8")

    with pytest.raises(RegistryError) as error:
        load_registry(target, root=REPO_ROOT)

    assert "validators.yaml" in str(error.value)


def test_rule_validation_error_helper_is_reusable() -> None:
    """注册表加载复用规则层的错误格式（同一套"字段位置 + 原因"）。"""

    failure = RuleValidationError("x", errors=[])

    assert "x" in str(failure)

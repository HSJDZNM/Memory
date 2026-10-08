"""Phase 5 验证器注册表与项目档案的加载测试：数据写错必须报错，不能悄悄少跑验证器。"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, VALIDATION_DIR, fake_tool_spec, write_validation_config
from policy.evidence import ValidatorKind
from policy.models import RuleValidationError
from provenance.reading_context import declaration_digest
from validators.models import Registry, ToolSpec, ValidatorSpec
from validators.registry import (
    RegistryError,
    config_digest,
    load_config,
    load_project,
    load_registry,
)


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


def test_undeclared_stage_of_a_later_dependency_is_a_registry_error(tmp_root: Path) -> None:
    """依赖顺序检查读的是**被依赖者**的阶段：它没声明阶段时也必须是 RegistryError。

    历史缺陷（OCR 全量审查 L13）：阶段合法性只在"轮到自己"时检查，而 `requires` 可以指向
    列表里**后面**的那一条——那一条的阶段还没查过，`stage_index[target.stage]` 于是抛裸
    KeyError：加载期的配置错误变成未处理异常，退出码与错误分类都丢了（本模块的承诺是
    "任何一条不满足都拒绝加载"）。
    """

    document = registry_document()
    document["validators"][0]["requires"] = ["ghost.validator"]
    late = copy.deepcopy(document["validators"][0])
    late["id"] = "ghost.validator"
    late["requires"] = []
    late["stage"] = "py.ghost"  # 形态合法（py.*），但不在 registry.stages 里
    document["validators"].append(late)

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "未定义的阶段" in str(error.value)
    assert "py.ghost" in str(error.value)


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


def test_analysis_failure_codes_are_declared_as_data() -> None:
    """"哪些码意味着本次分析不成立"是注册表数据，不是代码里的码表。"""

    registry = load_config(root=REPO_ROOT).registry
    ruff = registry.spec("tool.ruff")
    mypy = registry.spec("tool.mypy")

    assert ruff is not None and ruff.tool is not None
    assert ruff.tool.analysis_failure_codes == ("invalid-syntax",)
    # 没有声明的工具保持空元组：默认不把任何码当"分析不成立"
    assert mypy is not None and mypy.tool is not None
    assert mypy.tool.analysis_failure_codes == ()


def test_analysis_failure_codes_are_rejected_where_nobody_reads_them(tmp_root: Path) -> None:
    """数据声明的能力必须有实现承接，否则又是"看起来在管、实际什么都没查"。"""

    document = registry_document()
    for item in document["validators"]:
        if item["id"] == "tool.mypy":
            item["tool"]["analysis_failure_codes"] = ["syntax"]

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "analysis_failure_codes" in str(error.value)
    assert "tool.mypy" in str(error.value)


def test_analysis_failure_codes_reject_duplicates_and_blanks(tmp_root: Path) -> None:
    document = registry_document()
    for item in document["validators"]:
        if item["id"] == "tool.ruff":
            item["tool"]["analysis_failure_codes"] = ["invalid-syntax", "INVALID-SYNTAX"]

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "重复码" in str(error.value)


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


def test_config_digest_returns_none_when_the_file_cannot_be_read(monkeypatch, tmp_path) -> None:
    """is_file() 之后仍可能读不了（权限 / I/O / 竞态）：与 declaration_digest 同口径返回 None（复核发现）。"""

    target = tmp_path / "ruff.toml"
    target.write_text("x" + chr(10), encoding="utf-8", newline="")
    assert (config_digest(target) or "").startswith("sha256:")

    real = Path.read_bytes

    def failing(self, *args, **kwargs):
        if self.name == "ruff.toml":
            raise PermissionError(13, "Permission denied")
        return real(self, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "read_bytes", failing)
        assert config_digest(target) is None
        assert declaration_digest(target) is None

    assert config_digest(None) is None


def test_unknown_placeholder_spellings_are_rejected() -> None:
    """任何花括号词都必须在白名单里：大小写 / 数字 / 带空格都溜不过去（复核发现）。"""

    for bad in ("{Target}", "{target1}", "{python }", "{}", "--flag={Target}"):
        with pytest.raises(Exception) as error:
            ToolSpec(command=("ruff", bad))
        assert "占位符" in str(error.value), bad
        with pytest.raises(Exception) as argv_error:
            ToolSpec(command=("ruff",), argv=(bad,))
        assert "占位符" in str(argv_error.value), bad

    # 合法占位符照常（command 只允许 {python}，argv 允许全部已声明占位符）。
    spec = ToolSpec(command=("{python}",), argv=("{target}", "--select", "{config}"))
    assert spec.argv == ("{target}", "--select", "{config}")


def test_tool_command_rejects_empty_elements_in_any_position() -> None:
    """空（或全空白）元素在任何位置都要拒（复核发现：any() 只要有一个非空就放行）。"""

    for values in (("ruff", ""), ("", "ruff"), ("ruff", "   "), ("",)):
        with pytest.raises(Exception) as error:
            ToolSpec(command=values)
        assert "不能有空元素" in str(error.value), values

    assert ToolSpec(command=("ruff", "--fix")).command == ("ruff", "--fix")


def test_tool_config_rejects_windows_absolute_and_drive_relative_paths() -> None:
    """tool.config 的路径校验必须与消费方同口径（复核发现：盘符/UNC 漏过）。"""

    for bad in (
        "C:/tools/ruff.toml",
        "C:../outside/ruff.toml",
        "C:\\tools\\ruff.toml",
        "//server/share/ruff.toml",
        "\\\\server\\share\\ruff.toml",
        "../outside/ruff.toml",
        "/etc/ruff.toml",
    ):
        with pytest.raises(Exception) as error:
            ToolSpec(command=("ruff",), config=bad)
        assert "tool.config" in str(error.value), bad

    # 合法的仓库相对路径照常，并归一掉 "./" 与反斜杠。
    assert ToolSpec(command=("ruff",), config="validation/ruff.toml").config == (
        "validation/ruff.toml"
    )
    assert ToolSpec(command=("ruff",), config=".\\validation\\ruff.toml").config == (
        "validation/ruff.toml"
    )


def test_version_pattern_must_capture_a_version() -> None:
    with pytest.raises(Exception) as error:
        ToolSpec(command=("ruff",), version_pattern=r"ruff [0-9.]+")

    assert "捕获组" in str(error.value)


def test_project_profile_rejects_windows_style_escaping_python_roots(tmp_root: Path) -> None:
    """python_roots 的逃逸守卫必须覆盖反斜杠 / 盘符 / UNC（复核发现：只做了 POSIX 那一半）。"""

    for bad in ("..\\..\\outside", "C:\\outside", "C:/outside", "\\\\server\\share", "../outside"):
        document = yaml.safe_load((VALIDATION_DIR / "project.yaml").read_text(encoding="utf-8"))
        document["python_roots"] = [bad]
        write_validation_config(tmp_root, project=document)
        with pytest.raises(RegistryError) as error:
            load_config(root=tmp_root, registry=VALIDATION_DIR / "validators.yaml")
        assert "python_roots" in str(error.value), bad

    # 合法的解析根照常，反斜杠写法被归一成消费方看到的形态。
    document = yaml.safe_load((VALIDATION_DIR / "project.yaml").read_text(encoding="utf-8"))
    document["python_roots"] = [".", "src", ".\\src"]
    write_validation_config(tmp_root, project=document)
    profile = load_project(root=tmp_root)
    assert profile.python_roots == (".", "src", "src")


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


# ------------------------------- uncovered_languages：哪些语言**按设计不取证**（P2 的声明处）


def uncovered_entries(document: dict) -> list:
    """清单必须存在：没有它，"哪些语言按设计不取证"就无处表达（07 号报告 P2）。"""

    entries = document.get("uncovered_languages")
    assert isinstance(entries, list) and entries, (
        "validation/validators.yaml 必须显式声明 uncovered_languages："
        "没有 rule pack 的语言要么在这里被声明，要么在运行期失败关闭"
    )
    return entries


def test_uncovered_language_needs_a_reviewable_reason(tmp_root: Path) -> None:
    """理由空着 = "为什么不查"重新变成不可读：加载期就拒绝，不留到评审时才发现。"""

    document = registry_document()
    uncovered_entries(document)[0]["reason"] = "   "

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "reason" in str(error.value)


def test_duplicate_uncovered_language_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    uncovered_entries(document).append(copy.deepcopy(uncovered_entries(document)[0]))

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "重复 ID" in str(error.value)


def test_a_language_cannot_be_covered_and_uncovered_at_once(tmp_root: Path) -> None:
    """自相矛盾必须报错：同一个 language 既有 rule pack、又声明"按设计不取证"。"""

    document = registry_document()
    uncovered_entries(document).append({"language": "python", "reason": "自相矛盾的声明"})

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    message = str(error.value)
    assert "python" in message
    assert "自相矛盾" in message


def test_unknown_field_in_an_uncovered_language_is_rejected(tmp_root: Path) -> None:
    document = registry_document()
    uncovered_entries(document)[0]["skip"] = True

    with pytest.raises(RegistryError) as error:
        _load(document, tmp_root)

    assert "skip" in str(error.value)


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

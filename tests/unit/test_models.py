"""Phase 0 模型测试：类型、枚举、未知字段、序列化。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from policy.models import (
    Decision,
    EnforcementType,
    Evidence,
    PolicyContext,
    PolicyContextError,
    Principal,
    Rule,
    RuleScope,
    RuleSet,
    ScopeExtraPolicy,
    Severity,
    ValidationResult,
    Violation,
    canonical_identifier,
    normalize_repo_path,
)

from conftest import rule_document
from policy.models import RULE_BODY_CLASSES

# 规则体 union 的成员类名：错误位置里不带它们，测试与加载器的报错口径一致。
UNION_MEMBER_NAMES = {cls.__name__ for cls in RULE_BODY_CLASSES}


def test_valid_rule_is_constructed() -> None:
    rule = Rule.model_validate(rule_document())

    assert rule.id == "ARCH-001"
    assert rule.version == 1
    assert rule.canonical_id == "ARCH-001@1"
    assert rule.severity is Severity.ERROR
    assert rule.enforcement.type is EnforcementType.DETERMINISTIC
    assert rule.rule.forbidden_dependency == ("repository",)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("id", None, "id"),
        ("id", "", "id"),
        ("id", "ARCH-001-BETA", "id"),
        ("id", "ARCH001", "id"),
        ("version", 0, "version"),
        ("enforcement", {"mode": "strict", "type": "deterministic", "checker": "forbidden_dependency"}, "enforcement.mode"),
        ("severity", "fatal", "severity"),
        ("severity", "ERROR", "severity"),
        ("enforcement", {"type": "llm"}, "enforcement.type"),
        ("enforcement", {"type": "deterministic"}, "enforcement"),
        ("enforcement", {"type": "deterministic", "checker": "forbidden_dependency", "extra": 1}, "enforcement.extra"),
        ("rule", {"forbidden_dependency": []}, "rule.forbidden_dependency"),
        ("source", {"kind": "chatgpt-share"}, "source.kind"),
        ("source", {"kind": "project-policy", "path": "/etc/passwd"}, "source.path"),
    ],
)
def test_invalid_rule_is_rejected(field: str, value: object, expected: str) -> None:
    with pytest.raises(ValidationError) as error:
        Rule.model_validate(rule_document(**{field: value}))

    locations = {
        ".".join(
            str(part) for part in item["loc"] if str(part) not in UNION_MEMBER_NAMES
        )
        for item in error.value.errors()
    }

    # pydantic 对冻结模型的嵌套错误只报告最近的可识别位置（例如 enforcement 而不是
    # enforcement.checker），因此这里断言精确路径而不是前缀匹配。
    # union 成员的类名是实现的细节，规则作者看到的位置是 rule.forbidden_dependency，
    # 这里与 policy.models.RuleValidationError.from_pydantic 保持同一口径。
    assert expected in locations, locations


@pytest.mark.parametrize(
    ("document_overrides", "needle"),
    [
        (
            {"enforcement": {"type": "deterministic", "checker": "llm_judgement"}},
            "未知 checker",
        ),
        (
            {
                "enforcement": {"type": "deterministic", "checker": "style_lint"},
                "rule": {"forbidden_dependency": ["repository"]},
            },
            "规则体与 checker 不一致",
        ),
    ],
)
def test_checker_must_be_known_and_match_the_body(
    document_overrides: dict, needle: str
) -> None:
    """未知 checker 与"规则体对不上 checker"都在加载阶段拒绝，不能留到运行时。"""

    with pytest.raises(ValidationError) as error:
        Rule.model_validate(rule_document(**document_overrides))

    assert any(needle in item["msg"] for item in error.value.errors()), error.value.errors()


def test_unknown_top_level_field_is_rejected() -> None:
    document = rule_document()
    document["sevrity"] = "error"  # 典型拼写错误：必须报错而不是静默忽略

    with pytest.raises(ValidationError) as error:
        Rule.model_validate(document)

    assert any(item["type"] == "extra_forbidden" for item in error.value.errors())


def test_unknown_nested_rule_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Rule.model_validate(rule_document(rule={"forbidden_dependency": ["repository"], "allow": []}))


def test_rule_is_immutable() -> None:
    rule = Rule.model_validate(rule_document())

    with pytest.raises(ValidationError):
        rule.version = 2  # type: ignore[misc]


def test_rule_serialization_keeps_key_fields() -> None:
    rule = Rule.model_validate(rule_document())

    # exclude_none：未声明的 scope 维度不写进载荷，规则集哈希才不会被"新增可选维度"扰动
    payload = rule.model_dump(mode="json", exclude_none=True)

    assert payload["id"] == "ARCH-001"
    assert payload["version"] == 1
    assert payload["severity"] == "error"
    assert payload["enforcement"] == {
        "type": "deterministic",
        "checker": "forbidden_dependency",
        "requires_approval": False,
    }
    # scope 只序列化规则语义维度：extra_policy 是加载策略，不进审计身份
    assert payload["scope"] == {"language": "python", "layer": "controller"}
    assert rule.scope.extra_policy is ScopeExtraPolicy.REJECT
    assert payload["rule"] == {"forbidden_dependency": ["repository"]}
    assert payload["source"]["path"] == "policies/architecture/ARCH-001.yaml"


def test_unknown_scope_dimension_is_rejected_by_default() -> None:
    """Phase 1 起默认拒绝：拼错维度名会让规则悄悄放大适用范围，不能静默忽略。"""

    with pytest.raises(ValidationError) as error:
        RuleScope.model_validate({"language": "python", "tenant": "acme"})

    assert "未知维度" in str(error.value)
    assert "tenant" in str(error.value)
    assert "extra_policy=skip" in str(error.value)


def test_scope_extra_policy_reject_blocks_unknown_keys() -> None:
    document = rule_document(
        scope={
            "language": "python",
            "layer": "controller",
            "tenant": "acme",
            "extra_policy": ScopeExtraPolicy.REJECT.value,
        }
    )

    with pytest.raises(ValidationError) as error:
        Rule.model_validate(document)

    assert "未知维度" in str(error.value)
    assert "tenant" in str(error.value)


def test_scope_extra_policy_skip_records_unknown_keys() -> None:
    scope = RuleScope.model_validate(
        {"language": "python", "tenant": "acme", "extra_policy": ScopeExtraPolicy.SKIP.value}
    )

    assert scope.ignored_dimensions == ("tenant",)
    assert scope.language == "python"
    assert scope.layer is None
    assert "extra_policy" not in scope.model_dump()


def test_scope_normalizes_case_but_keeps_separators() -> None:
    scope = RuleScope.model_validate({"language": "Python", "layer": "  Controller "})

    assert scope.language == "python"
    assert scope.layer == "controller"
    assert canonical_identifier("Order_Repository") == "order_repository"
    assert canonical_identifier("Order-Repository") == "order-repository"


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ({"layer": "controller"}, {"layer": "controller"}),
        ({"layer": ["Controller", "SERVICE"]}, {"layer": ("controller", "service")}),
        ({"layer": "*"}, {"layer": "*"}),
        ({"layer": ["controller", "*"]}, {"layer": "*"}),
        ({"operation": "EDIT"}, {"operation": "edit"}),
        ({"module": "Order", "project": "Shop"}, {"module": "order", "project": "shop"}),
        ({}, {}),
    ],
)
def test_scope_selectors_are_normalized(scope: dict, expected: dict) -> None:
    model = RuleScope.model_validate(scope)

    assert dict(model.declared_dimensions) == expected


@pytest.mark.parametrize(
    "scope",
    [
        {"operation": "deploy"},
        {"operation": ["edit", "deploy"]},
        {"layer": []},
        {"layer": "   "},
        {"layer": 7},
        {"layer": [1]},
    ],
)
def test_invalid_scope_selectors_are_rejected(scope: dict) -> None:
    with pytest.raises(ValidationError):
        RuleScope.model_validate(scope)


def test_scope_declared_dimensions_exclude_undeclared_ones() -> None:
    scope = RuleScope.model_validate({"layer": "controller", "operation": ["edit", "create"]})

    assert set(scope.declared_dimensions) == {"layer", "operation"}
    assert scope.module is None and scope.project is None and scope.agent is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("src/order/controller.py", "src/order/controller.py"),
        ("./src/order/controller.py", "src/order/controller.py"),
        ("src\\order\\controller.py", "src/order/controller.py"),
        ("src//order/controller.py", "src/order/controller.py"),
    ],
)
def test_context_normalizes_repo_path(raw: str, expected: str) -> None:
    context = PolicyContext(request_id="req-1", file=raw, layer="controller")

    assert context.file == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "/etc/passwd", "C:/Users/other/file.py", "src/../../escape.py", "src/order/controller<>.py"],
)
def test_context_rejects_unsafe_paths(raw: str) -> None:
    with pytest.raises((PolicyContextError, ValidationError)):
        PolicyContext(request_id="req-1", file=raw, layer="controller")


def test_normalize_repo_path_helper() -> None:
    assert normalize_repo_path("  src/order/controller.py  ") == "src/order/controller.py"

    with pytest.raises(PolicyContextError):
        normalize_repo_path("../secrets.env")


def test_repo_path_accepts_non_ascii_segments() -> None:
    """非 ASCII 路径段必须被接受：镜像语料与仓库文档都用中文目录名。

    规则要用 source.path 指回 `docs/mirrors/owasp-cheatsheets/02_输入验证、注入与文件处理/…`，
    上下文文件也可能是 `docs/project/architecture/使用说明.md`；要求 ASCII 会让"指向真实来源"
    变成加载期错误。放宽的只是字符集，结构拒绝（绝对路径 / 盘符 / ".." / 元字符）不变。
    """

    mirrored = "docs/mirrors/owasp-cheatsheets/02_输入验证、注入与文件处理/SQL_Injection_Prevention_Cheat_Sheet.md"
    assert normalize_repo_path(mirrored) == mirrored
    assert normalize_repo_path("docs/project/architecture/使用说明.md") == "docs/project/architecture/使用说明.md"

    for raw in ("src/order/a*b.py", "src/order/a:b.py", "src/order/a?b.py"):
        with pytest.raises(PolicyContextError):
            normalize_repo_path(raw)


def test_context_requires_safety_critical_fields() -> None:
    with pytest.raises(ValidationError):
        PolicyContext(request_id="", file="a.py", layer="controller")
    with pytest.raises(ValidationError):
        PolicyContext(request_id="req-1", file="a.py")
    with pytest.raises(ValidationError):
        PolicyContext(request_id="req-1", file="a.py", layer="   ")


def test_context_dependencies_are_canonical_and_sorted() -> None:
    context = PolicyContext(
        request_id="req-1",
        file="src/order/controller.py",
        layer="Controller",
        dependencies=["Service", "repository", "repository", "  "],
    )

    assert context.layer == "controller"
    assert context.dependencies == ("repository", "service")


def test_context_dependencies_reject_string_payload() -> None:
    with pytest.raises((TypeError, ValidationError)):
        PolicyContext(
            request_id="req-1",
            file="src/order/controller.py",
            layer="controller",
            dependencies="repository",
        )


def test_principal_roles_are_canonical() -> None:
    principal = Principal(subject="local-user", roles=["Developer", "DEVELOPER", ""])

    assert principal.roles == frozenset({"developer"})


def test_decision_is_derived_from_violations() -> None:
    violation = Violation(
        rule_id="ARCH-001",
        rule_version=1,
        severity=Severity.ERROR,
        message="Controller 必须通过 Service 访问 Repository。",
        evidence=Evidence(kind="dependency", subject="src/order/controller.py", value="repository"),
    )

    result = ValidationResult(
        decision=Decision.BLOCK,
        request_id="req-1",
        matched_rules=("ARCH-001@1",),
        violations=(violation,),
    )

    assert not result.passed
    assert result.severity_counts == {"error": 1}
    assert result.to_decision_dict()["violations"][0]["evidence"] == {
        "kind": "dependency",
        "subject": "src/order/controller.py",
        "value": "repository",
    }

    with pytest.raises(ValidationError):
        ValidationResult(decision=Decision.ALLOW, request_id="req-1", violations=(violation,))


def test_rule_set_identity_is_stable() -> None:
    rule = Rule.model_validate(rule_document())
    first = RuleSet(rules=(rule,), source_paths=("policies/architecture/ARCH-001.yaml",))
    second = RuleSet(rules=(rule,), source_paths=("policies/architecture/ARCH-001.yaml",))
    other = RuleSet(rules=(Rule.model_validate(rule_document(version=2)),), source_paths=())

    assert first.identity == second.identity
    assert first.identity.startswith("sha256:")
    assert first.identity != other.identity
    assert first.ids == ("ARCH-001@1",)


def test_rule_set_identity_ignores_loading_order() -> None:
    """规则集身份是内容的函数：目录遍历顺序不同不能产生不同哈希。"""

    first = Rule.model_validate(rule_document(id="ARCH-001"))
    second = Rule.model_validate(rule_document(id="ARCH-002", version=2))

    forward = RuleSet(rules=(first, second))
    backward = RuleSet(rules=(second, first))

    assert forward.identity == backward.identity
    assert forward.ids == ("ARCH-001@1", "ARCH-002@2")
    assert backward.ids == ("ARCH-002@2", "ARCH-001@1")

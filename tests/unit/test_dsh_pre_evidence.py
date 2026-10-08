"""G3 / M2：动手前取证（pre_evidence）的单元测试 + M3 的严重级别分布。

两条问题同源：**账本必须能区分两件事**。

- M2：`skipped_rules` 里的规则不是"查过没问题"，而是"没人查"。声明了 pre_evidence 之后，
  证据类 checker 必须真的参与判定；声明了却取不到证据时必须失败关闭（exit 2 /
  evidence_unavailable）——绝不回落到"没证据就当跳过"。
- M3：43 条规则里 19 条只有 warning 严重级别，命中只产出 allow_with_warnings。
  "有多少条规则"与"有多少条会拦人的规则"必须能在账本上分开读（AGENTS.md 第 43 条）。

取证用例走**真实流水线**（py.source / py.ast / py.docstring，标准库实现），因此不依赖
本机是否装了 ruff / mypy；断言的是"取证有没有真的发生"，不是某个外部工具的输出。
"""

from __future__ import annotations

import json
import time
from hashlib import sha256
from pathlib import Path

import pytest
from conftest import (
    REPO_ROOT,
    copy_validator_project,
    dsh_event,
    make_checker_rule,
    write_dsh_config,
)

from adapters.dsh import pre_evidence as pre_evidence_module
from adapters.dsh.adapter import load_config, to_policy_context, to_policy_event
from adapters.dsh.hooks import (
    EXIT_ALLOW,
    EXIT_BLOCK,
    AuditLedger,
    DshPreExecuteHook,
    run_hook,
)
from adapters.dsh.pre_evidence import PreEvidenceError, build_pre_evidence
from policy.models import (
    Decision,
    Evidence,
    RuleSet,
    Severity,
    SkippedRule,
    ValidationResult,
    Violation,
)

# 目标文件必须命中 adapter 配置里的 layers：否则 Adapter 在更早的一步就会拒绝
# （layer 是安全关键字段，声明不出来就失败关闭），用例也就测不到取证那一段。
TARGET = "src/shop/facade_service.py"
# 没有模块 docstring 的模块：missing_docstring 规则必须命中它。
UNDOCUMENTED = (
    "class Facade:\n"
    '    """有 docstring 的类（模块本身没有 docstring）。"""\n'
    "\n"
    "    def run(self) -> int:\n"
    '        """跑一次。"""\n'
    "\n"
    "        return 1\n"
)
# 只用标准库实现的验证器：流水线因此不需要任何外部工具。
BUILTIN_VALIDATORS = ("py.source", "py.ast", "py.docstring")


def pre_evidence_block(project: Path, shadow_root: Path, **overrides: object) -> dict:
    block: dict = {
        # 声明形状以 tests/unit/test_dsh_adapter_config.py 的口径为准：
        # registry_root 指的是平台的 validation/ 目录本身。
        "registry_root": str(REPO_ROOT / "validation"),
        "workspace": str(project),
        "shadow_root": str(shadow_root),
        "exclude": [".git/**", ".policy/**", "__pycache__/**"],
        "validators": list(BUILTIN_VALIDATORS),
        "timeout_ms": 30000,
    }
    block.update(overrides)
    return block


def doc_rules(*, severity: str = "error") -> RuleSet:
    """一条证据类规则：模块不得缺 docstring（这个问题只有验证器能回答）。"""

    return RuleSet(
        rules=(
            make_checker_rule(
                "DOC-900",
                checker="missing_docstring",
                body={"missing_docstring": {"targets": ["module"]}},
                severity=severity,
            ),
        ),
        source_paths=(),
    )


def write_payload(
    project: Path,
    *,
    tool_use_id: str = "call-pre-1",
    content: str = UNDOCUMENTED,
    target: str = TARGET,
) -> dict:
    return dsh_event(
        "pre-tool-use-write-block.json",
        cwd=str(project),
        tool_name="write",
        tool_input={"file_path": target, "content": content},
        tool_use_id=tool_use_id,
    )


def edit_payload(project: Path, *, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    return dsh_event(
        "pre-tool-use-edit-allow.json",
        cwd=str(project),
        tool_name="edit",
        tool_input={
            "file_path": TARGET,
            "old_string": old_string,
            "new_string": new_string,
            "replace_all": replace_all,
        },
    )


def warning_violation(rule: str = "DOC-001", version: int = 1) -> Violation:
    """一条 warning 级违规：决策表把它算成 allow_with_warnings（拦不下任何东西）。"""

    return Violation(
        rule_id=rule,
        rule_version=version,
        severity=Severity.WARNING,
        message="公开对象必须有 docstring",
        evidence=Evidence(kind="docstring", subject=f"{rule}@{version}", value="missing"),
    )


def decisions(audit: Path) -> list[dict]:
    """审计里所有**判定**记录（授权 / 留痕记录另有形状，不算判定）。"""

    return [
        record
        for record in (
            json.loads(line)
            for line in audit.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if "decision" in record
    ]


def last_decision(audit: Path) -> dict:
    found = decisions(audit)
    assert found, f"审计里没有判定记录：{audit}"
    return found[-1]


def event_and_context(config, payload: dict):
    admission = to_policy_event(payload, config=config)
    assert admission.event is not None
    return admission.event, to_policy_context(admission.event, config=config)


def build_config(tmp_root: Path, project: Path, *, shadow_root: Path, **overrides: object) -> Path:
    return write_dsh_config(
        tmp_root / "config" / "pre-evidence.yaml",
        project_root=project,
        rules=REPO_ROOT / "policies",
        pre_evidence=pre_evidence_block(project, shadow_root, **overrides),
    )


# --------------------------------------------------------------------------- 提议内容与影子副本


def test_a_write_proposal_lands_in_a_shadow_copy_that_is_deleted_afterwards(tmp_root: Path) -> None:
    project = copy_validator_project(tmp_root)
    shadow_root = tmp_root / "shadow"
    config = load_config(build_config(tmp_root, project, shadow_root=shadow_root))
    payload = write_payload(project)
    event, context = event_and_context(config, payload)

    result = build_pre_evidence(
        payload, event=event, config=config, rules=doc_rules(), context=context
    )

    # 证据来自真实流水线：missing_docstring 由 py.docstring 提供
    assert "missing_docstring" in result.bundle.served_checkers
    assert result.bundle.target is not None
    assert result.bundle.target.file == TARGET
    assert result.bundle.target.sha256.startswith("sha256:")
    assert result.summary["status"] == "collected"
    assert result.summary["target_sha256"] == result.bundle.target.sha256
    assert result.summary["proposal"]["field"] == "content"
    # 影子副本用完必删：留下副本等于在受控项目旁边留一份没人管的代码
    assert not shadow_root.exists() or list(shadow_root.iterdir()) == []


def test_the_shadow_copy_is_pruned_when_it_lives_inside_the_workspace(tmp_root: Path) -> None:
    """默认声明把影子目录放在项目里：复制必须剪掉它，否则会把自己复制进去。"""

    project = copy_validator_project(tmp_root)
    shadow_root = project / ".policy" / "pre-evidence"
    config = load_config(build_config(tmp_root, project, shadow_root=shadow_root))
    payload = write_payload(project)
    event, context = event_and_context(config, payload)

    result = build_pre_evidence(
        payload, event=event, config=config, rules=doc_rules(), context=context
    )

    assert result.bundle.target is not None
    assert not shadow_root.exists() or list(shadow_root.iterdir()) == []


def test_the_shadow_copy_prunes_top_level_excludes(tmp_root: Path) -> None:
    """影子副本必须真的剪掉**顶层**被排除的目录（.git / node_modules …）。

    `_relative(根, 根)` 给的是 "."（`PurePath.relative_to` 的语义），不是 docstring 承诺的空串：
    顶层子项于是被拼成 "./.git" 这种相对路径，而排除 glob（`.git/**`）只认 ".git" 与 ".git/"——
    整棵目录被复制进影子副本，既拖慢取证，又让验证器看见声明明确要排除的文件。
    """

    source = tmp_root / "project"
    (source / ".git").mkdir(parents=True)
    (source / ".git" / "config").write_text("x" + chr(10), encoding="utf-8", newline="")
    (source / "node_modules" / "pkg").mkdir(parents=True)
    (source / "node_modules" / "pkg" / "index.js").write_text("x" + chr(10), encoding="utf-8", newline="")
    (source / "src").mkdir()
    (source / "src" / "main.py").write_text("VALUE = 1" + chr(10), encoding="utf-8", newline="")

    target = tmp_root / "shadow"
    copied = pre_evidence_module._copy_workspace(
        source,
        target,
        exclude=[".git/**", "node_modules/**"],
        shadow_root=target,
    )

    assert (target / "src" / "main.py").is_file()
    assert not (target / ".git").exists()
    assert not (target / "node_modules").exists()
    assert copied == 1


def test_a_shadow_that_would_swallow_the_project_is_refused(tmp_root: Path, monkeypatch) -> None:
    """影子目录一旦与项目重叠，finally 里的整棵删除就会删到项目本身：先拒绝。"""

    project = copy_validator_project(tmp_root)
    # shadow_root 取项目的父目录 + 影子目录名等于项目目录名 => 影子就是项目本身
    config = load_config(build_config(tmp_root, project, shadow_root=project.parent))
    payload = write_payload(project)
    event, context = event_and_context(config, payload)
    monkeypatch.setattr(pre_evidence_module, "_shadow_name", lambda _event: project.name)

    with pytest.raises(PreEvidenceError) as caught:
        build_pre_evidence(payload, event=event, config=config, rules=doc_rules(), context=context)

    assert "影子" in str(caught.value)
    assert project.is_dir()
    assert (project / "src" / "shop" / "order_service.py").is_file()


def test_the_summary_never_carries_an_absolute_path(tmp_root: Path) -> None:
    project = copy_validator_project(tmp_root)
    shadow_root = tmp_root / "shadow"
    config = load_config(build_config(tmp_root, project, shadow_root=shadow_root))
    payload = write_payload(project)
    event, context = event_and_context(config, payload)

    result = build_pre_evidence(
        payload, event=event, config=config, rules=doc_rules(), context=context
    )

    dumped = json.dumps(result.summary, ensure_ascii=False, sort_keys=True)
    # AGENTS 第 19 条：证据里不得出现绝对路径。摘要要进审计，口径完全一样。
    assert str(tmp_root) not in dumped
    assert str(tmp_root).replace("\\", "/") not in dumped
    assert str(REPO_ROOT) not in dumped
    # 相同输入必须得到逐字节相同的摘要：里面不能有耗时
    assert "elapsed" not in dumped


def test_an_edit_with_a_duplicated_old_string_is_refused(tmp_root: Path) -> None:
    project = copy_validator_project(tmp_root)
    (project / "src" / "shop" / "facade_service.py").write_text(
        '"""重复出现的锚点。"""\n\n\nVALUE = 1\nVALUE = 2\n', encoding="utf-8", newline=""
    )
    config = load_config(build_config(tmp_root, project, shadow_root=tmp_root / "shadow"))
    payload = edit_payload(project, old_string="VALUE", new_string="OTHER", replace_all=True)
    event, context = event_and_context(config, payload)

    with pytest.raises(PreEvidenceError) as caught:
        build_pre_evidence(payload, event=event, config=config, rules=doc_rules(), context=context)

    message = str(caught.value)
    assert "出现 2 次" in message
    assert "恰好" in message
    # 拒绝的理由必须点出"证明不了"这件事，而不是笼统的"参数错误"
    assert "证明" in message
    # 连影子目录都不该建出来：拒绝发生在复制之前
    assert not (tmp_root / "shadow").exists()


def test_an_edit_whose_old_string_is_missing_is_refused(tmp_root: Path) -> None:
    project = copy_validator_project(tmp_root)
    # 目标文件必须存在：edit 的基准内容是"磁盘上当前的内容"，读不到就必须拒绝
    (project / "src" / "shop" / "facade_service.py").write_text(
        '"""有 docstring 的模块。"""\n', encoding="utf-8", newline=""
    )
    config = load_config(build_config(tmp_root, project, shadow_root=tmp_root / "shadow"))
    payload = edit_payload(
        project, old_string="这段文本在文件里根本不存在", new_string="x"
    )
    event, context = event_and_context(config, payload)

    with pytest.raises(PreEvidenceError) as caught:
        build_pre_evidence(payload, event=event, config=config, rules=doc_rules(), context=context)

    assert "出现 0 次" in str(caught.value)


def test_an_edit_proposal_is_applied_before_the_pipeline_runs(tmp_root: Path) -> None:
    """取证看的是"改完之后"的内容：替换没生效的话，证据就是旧的。"""

    project = copy_validator_project(tmp_root)
    (project / "src" / "shop" / "facade_service.py").write_text(
        "ANCHOR = 1\n", encoding="utf-8", newline=""
    )
    config = load_config(build_config(tmp_root, project, shadow_root=tmp_root / "shadow"))
    payload = edit_payload(project, old_string="ANCHOR = 1", new_string=UNDOCUMENTED.rstrip("\n"))
    event, context = event_and_context(config, payload)

    result = build_pre_evidence(
        payload, event=event, config=config, rules=doc_rules(), context=context
    )

    assert result.summary["proposal"]["mode"] == "replacement"
    assert result.bundle.target is not None
    expected = (UNDOCUMENTED.rstrip("\n") + "\n").encode("utf-8")
    assert result.bundle.target.sha256 == "sha256:" + sha256(expected).hexdigest()


def test_without_a_declaration_there_is_no_evidence_provider(tmp_root: Path) -> None:
    """没有声明就**没有**取证能力：这里必须报错，而不是返回一份空证据。"""

    project = copy_validator_project(tmp_root)
    config = load_config(
        write_dsh_config(
            tmp_root / "config" / "phase-2.yaml",
            project_root=project,
            rules=REPO_ROOT / "policies",
        )
    )
    payload = write_payload(project)
    event, context = event_and_context(config, payload)

    with pytest.raises(PreEvidenceError):
        build_pre_evidence(payload, event=event, config=config, rules=doc_rules(), context=context)


def test_a_registry_root_that_contains_validation_is_taken_as_declared(tmp_root: Path) -> None:
    """声明成"包含 validation/ 的那一层"同样受支持，且解析方式写进摘要。"""

    project = copy_validator_project(tmp_root)
    config = load_config(
        build_config(
            tmp_root,
            project,
            shadow_root=tmp_root / "shadow",
            registry_root=str(REPO_ROOT),
        )
    )
    payload = write_payload(project)
    event, context = event_and_context(config, payload)

    result = build_pre_evidence(
        payload, event=event, config=config, rules=doc_rules(), context=context
    )

    assert result.summary["registry_resolution"] == "as_declared"
    assert "missing_docstring" in result.bundle.served_checkers


def test_a_registry_root_with_no_platform_data_is_refused(tmp_root: Path) -> None:
    project = copy_validator_project(tmp_root)
    config = load_config(
        build_config(
            tmp_root, project, shadow_root=tmp_root / "shadow", registry_root=str(tmp_root / "nowhere")
        )
    )
    payload = write_payload(project)
    event, context = event_and_context(config, payload)

    with pytest.raises(PreEvidenceError) as caught:
        build_pre_evidence(payload, event=event, config=config, rules=doc_rules(), context=context)

    assert "validation" in str(caught.value)


def test_the_budget_is_a_hard_cap(tmp_root: Path, monkeypatch) -> None:
    """预算是硬上限：超时抛 PreEvidenceError，由 Hook 转成 exit 2。"""

    project = copy_validator_project(tmp_root)
    config = load_config(
        build_config(tmp_root, project, shadow_root=tmp_root / "shadow", timeout_ms=30)
    )
    payload = write_payload(project)
    event, context = event_and_context(config, payload)

    def never_returns(*_args: object, **_kwargs: object) -> None:
        time.sleep(0.5)

    # 内层流水线是唯一会慢下来的那一段，因此这里替换它——这是"预算真的生效"的最小接缝。
    monkeypatch.setattr(pre_evidence_module, "_collect_evidence", never_returns)

    started = time.monotonic()
    with pytest.raises(PreEvidenceError) as caught:
        build_pre_evidence(payload, event=event, config=config, rules=doc_rules(), context=context)

    assert time.monotonic() - started < 0.45
    assert "预算" in str(caught.value)


# --------------------------------------------------------------------------- Hook 侧


class _ExplodingProvider:
    """模拟"声明了取证、但证据链拿不出证据"的实现（缺失 / 崩溃 / 版本不符都走这条路）。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise PreEvidenceError("验证器不可用：ruff 不在本机")


def test_a_declared_but_unavailable_provider_blocks_with_exit_two(tmp_root: Path) -> None:
    project = copy_validator_project(tmp_root)
    config_path = build_config(tmp_root, project, shadow_root=tmp_root / "shadow")
    audit = tmp_root / "audit.jsonl"
    provider = _ExplodingProvider()
    hook = DshPreExecuteHook(
        config=load_config(config_path),
        rules=doc_rules(),
        ledger=AuditLedger(audit),
        evidence_provider=provider,
    )

    outcome = hook.handle(write_payload(project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "evidence_unavailable"
    assert provider.calls == 1
    # 理由必须写清"拒绝在证明不了的情况下放行"，而不是只说"出错了"
    assert "拒绝在证明不了的情况下放行" in outcome.stderr
    # 失败关闭不是判定：审计里一条判定记录都不该有（不出现"规则查过了"的假象）
    assert decisions(audit) == []
    entry = json.loads(audit.read_text(encoding="utf-8").splitlines()[0])
    assert entry["pre_evidence_status"] == "unavailable"
    assert entry["pre_evidence"]["status"] == "unavailable"


def test_a_provider_that_returns_something_else_is_refused(tmp_root: Path) -> None:
    """提供者必须交 EvidenceBundle：形状不对就等于没证据，同样是失败关闭。"""

    project = copy_validator_project(tmp_root)
    config_path = build_config(tmp_root, project, shadow_root=tmp_root / "shadow")
    audit = tmp_root / "audit.jsonl"
    hook = DshPreExecuteHook(
        config=load_config(config_path),
        rules=doc_rules(),
        ledger=AuditLedger(audit),
        evidence_provider=lambda *_args, **_kwargs: "这里不是证据",
    )

    outcome = hook.handle(write_payload(project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "evidence_unavailable"
    assert "EvidenceBundle" in outcome.stderr


def test_without_a_declaration_the_provider_is_never_called(tmp_root: Path) -> None:
    """Phase 2 契约：没有声明 pre_evidence 时，连提供者都不该被问到。"""

    project = copy_validator_project(tmp_root)
    config_path = write_dsh_config(
        tmp_root / "config" / "phase-2.yaml",
        project_root=project,
        rules=REPO_ROOT / "policies",
    )
    audit = tmp_root / "audit.jsonl"
    provider = _ExplodingProvider()
    hook = DshPreExecuteHook(
        config=load_config(config_path),
        rules=doc_rules(),
        ledger=AuditLedger(audit),
        evidence_provider=provider,
    )

    outcome = hook.handle(write_payload(project))

    assert provider.calls == 0
    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    record = last_decision(audit)
    assert record["pre_evidence_status"] == "not_declared"
    assert "pre_evidence" not in record
    # 证据类 checker 仍然进 skipped_rules（显式记录），而不是被判成通过
    assert "DOC-900@1" in record["skipped_rules"]
    assert "DOC-900@1" not in record["matched_rules"]


def test_a_declared_then_disabled_block_is_not_evidence(tmp_root: Path) -> None:
    project = copy_validator_project(tmp_root)
    config_path = build_config(tmp_root, project, shadow_root=tmp_root / "shadow", enabled=False)
    audit = tmp_root / "audit.jsonl"
    provider = _ExplodingProvider()
    hook = DshPreExecuteHook(
        config=load_config(config_path),
        rules=doc_rules(),
        ledger=AuditLedger(audit),
        evidence_provider=provider,
    )

    outcome = hook.handle(write_payload(project))

    assert provider.calls == 0
    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    record = last_decision(audit)
    assert record["pre_evidence_status"] == "disabled"
    assert "DOC-900@1" in record["skipped_rules"]


def test_the_evaluator_keeps_its_two_positional_arguments_without_evidence(
    tmp_root: Path,
) -> None:
    """既有测试注入的是 2 参数替身：没有证据时调用形状必须逐字节不变。"""

    project = copy_validator_project(tmp_root)
    config_path = write_dsh_config(
        tmp_root / "config" / "phase-2.yaml",
        project_root=project,
        rules=REPO_ROOT / "policies",
    )
    seen: list[tuple] = []

    def two_arg_evaluator(rules, context):
        from policy.engine import evaluate

        seen.append((rules, context))
        return evaluate(rules, context)

    outcome = run_hook(
        write_payload(project),
        config_path=config_path,
        evaluator=two_arg_evaluator,
        audit_path=tmp_root / "audit.jsonl",
    )

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    assert len(seen) == 1


# --------------------------------------------------------------------------- 执行类动作


class _FakeRisk:
    value = "destructive_write"


class _FakeSpec:
    name = "pwsh"
    id = "exec.pwsh"
    risk = _FakeRisk()
    driver = "none"
    post_checks: tuple = ()


class _FakeRequest:
    action_hash = "sha256:" + "0" * 64
    action_id = "sess-demo-0001:call-pwsh"
    tool_id = "exec.pwsh"
    risk = _FakeRisk()


class _FakeDecision:
    decision = Decision.ALLOW
    grant = None
    checks: tuple = ()


class _FakeOutcome:
    decision = _FakeDecision()


class _AllowAllBridge:
    """最小假桥：只为走到"没有文件维度的受控动作"那一段审计。

    真实链路里 pwsh 放行需要一份与 action_hash 绑定的人工审批文件（那是 Phase 4 集成
    测试的职责）。这里替掉的只是授权链路，判定、审计与状态字段仍是真实实现写的。
    """

    def spec_for(self, tool_name):
        return _FakeSpec()

    def build_request(self, **_kwargs):
        return _FakeRequest()

    def pre(self, _request, **_kwargs):
        return _FakeOutcome()


def test_an_execute_action_reports_the_evidence_status_as_not_applicable(
    tmp_root, dsh_config_path, dsh_project
) -> None:
    audit = tmp_root / "audit.jsonl"
    hook = DshPreExecuteHook(
        config=load_config(dsh_config_path),
        rules=RuleSet(rules=(make_checker_rule("ARCH-001"),), source_paths=()),
        ledger=AuditLedger(audit),
        bridge=_AllowAllBridge(),
    )

    outcome = hook.handle(dsh_event("pre-tool-use-pwsh-execute.json", cwd=str(dsh_project)))

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    record = json.loads(audit.read_text(encoding="utf-8").splitlines()[0])
    # 执行类动作没有文件内容可取证：写封闭值域里的取值，而不是留空让人猜
    assert record["pre_evidence_status"] == "not_applicable"
    assert record["effective_rule_count"] == 0
    assert record["evaluated_by_severity"] == {}
    assert record["skipped_by_severity"] == record["rules_by_severity"]


# --------------------------------------------------------------------------- M3（AGENTS 第 43 条）


def severity_hook(dsh_config_path) -> DshPreExecuteHook:
    rules = RuleSet(
        rules=(
            make_checker_rule("ARCH-001", checker="forbidden_dependency"),
            make_checker_rule(
                "DOC-001",
                checker="missing_docstring",
                body={"missing_docstring": {"targets": ["module"]}},
                severity="warning",
            ),
            make_checker_rule(
                "STYLE-001",
                checker="style_lint",
                body={"style_lint": {"tool": "ruff", "codes": ["E501"]}},
            ),
            make_checker_rule(
                "NOTE-001",
                checker="missing_docstring",
                body={"missing_docstring": {"targets": ["module"]}},
                severity="info",
            ),
        ),
        source_paths=(),
    )
    return DshPreExecuteHook(config=load_config(dsh_config_path), rules=rules)


def test_the_severity_distribution_separates_blocking_from_advisory(dsh_config_path) -> None:
    hook = severity_hook(dsh_config_path)
    decision = ValidationResult(
        decision=Decision.ALLOW_WITH_WARNINGS,
        request_id="req-1",
        matched_rules=("DOC-001@1",),
        skipped_rules=(
            SkippedRule(rule_id="ARCH-001@1", reasons=("需要验证器证据",)),
            SkippedRule(rule_id="STYLE-001@1", reasons=("需要验证器证据",)),
            SkippedRule(rule_id="GONE-999@1", reasons=("未知",)),
        ),
        violations=(warning_violation(),),
    )

    visibility = hook.rule_visibility(decision)

    # 规则集里各严重级别多少条
    assert visibility["rules_by_severity"] == {"error": 2, "info": 1, "warning": 1}
    # 有阻断力的规则数（error + critical）与只有判定力的规则数（warning）
    assert visibility["blocking_capable_rule_count"] == 2
    assert visibility["advisory_rule_count"] == 1
    # 本次真的参与判定的规则按级别：只有那条 warning 规则
    assert visibility["evaluated_by_severity"] == {"warning": 1}
    # 被跳过的按级别；规则集里没有的 ID 归 unknown，不塞进任何已知级别
    assert visibility["skipped_by_severity"] == {"error": 2, "unknown": 1}
    assert "拦" in visibility["severity_note"]
    # 既有键一个都不动
    assert visibility["rule_count"] == 4
    assert visibility["effective_rule_count"] == 1
    assert visibility["skipped_rule_count"] == 3
    assert visibility["skipped_reason"] == {
        "forbidden_dependency": 1,
        "not_in_rule_set": 1,
        "style_lint": 1,
    }


def test_a_warning_severity_rule_can_never_be_counted_as_blocking(dsh_config_path) -> None:
    """M3 的核心口径：warning 命中只产出 allow_with_warnings，它拦不下任何东西。"""

    hook = severity_hook(dsh_config_path)
    decision = ValidationResult(
        decision=Decision.ALLOW_WITH_WARNINGS,
        request_id="req-1",
        matched_rules=("DOC-001@1", "NOTE-001@1"),
        skipped_rules=(SkippedRule(rule_id="STYLE-001@1", reasons=("需要验证器证据",)),),
        violations=(warning_violation(),),
    )

    visibility = hook.rule_visibility(decision)

    assert decision.decision is Decision.ALLOW_WITH_WARNINGS
    assert visibility["evaluated_by_severity"] == {"info": 1, "warning": 1}
    # 参与判定的一条 error 规则都没有：这就是"命中"与"拦住"的区别
    assert "error" not in visibility["evaluated_by_severity"]
    assert "critical" not in visibility["evaluated_by_severity"]


def test_the_real_audit_record_carries_the_severity_distribution(
    dsh_config_path, dsh_project
) -> None:
    audit = dsh_project.parent / "audit.jsonl"

    outcome = run_hook(
        dsh_event("pre-tool-use-edit-allow.json", cwd=str(dsh_project)),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    record = last_decision(audit)
    assert record["rules_by_severity"]["error"] > 0
    assert record["blocking_capable_rule_count"] + record["advisory_rule_count"] > 0
    assert sum(record["evaluated_by_severity"].values()) == record["effective_rule_count"]
    assert sum(record["skipped_by_severity"].values()) == record["skipped_rule_count"]


def test_actions_without_a_file_dimension_report_the_severity_split_too(dsh_config_path) -> None:
    hook = severity_hook(dsh_config_path)

    visibility = hook.rule_visibility_not_applicable()

    assert visibility["blocking_capable_rule_count"] == 2
    assert visibility["advisory_rule_count"] == 1
    assert visibility["evaluated_by_severity"] == {}
    assert visibility["skipped_by_severity"] == visibility["rules_by_severity"]


# --------------------------------------------------------------------------- P3：取证树的形状


# 先写测试的现场：这个文件要 import 的兄弟模块（src/shop/shipment_service.py）这时还不存在。
TEST_TARGET = "tests/test_shipment_controller.py"
SIBLING_TEST = (
    '"""先写的测试：它要 import 的兄弟模块这时还不存在。"""\n'
    "\n"
    "from shop.shipment_service import ShipmentService\n"
    "\n"
    "\n"
    "def test_shipment() -> None:\n"
    '    """跑一次。"""\n'
    "\n"
    "    assert ShipmentService is not None\n"
)


def sibling_path(project: Path) -> Path:
    return project / "src" / "shop" / "shipment_service.py"


def tree_of(tmp_root: Path, project: Path, payload: dict) -> dict:
    """同一份载荷在**真实流水线**上取一次证，返回摘要里的 tree 段。"""

    config = load_config(build_config(tmp_root, project, shadow_root=tmp_root / "shadow"))
    event, context = event_and_context(config, payload)
    result = build_pre_evidence(
        payload, event=event, config=config, rules=doc_rules(), context=context
    )
    tree = result.summary.get("tree")
    assert isinstance(tree, dict), result.summary
    return dict(tree)


def test_the_summary_says_which_tree_the_evidence_belongs_to(tmp_root: Path) -> None:
    project = copy_validator_project(tmp_root)
    payload = write_payload(
        project, tool_use_id="call-tree-1", target=TEST_TARGET, content=SIBLING_TEST
    )

    tree = tree_of(tmp_root, project, payload)

    # 证据的含义取决于取证时那棵树的形状：读数的人必须知道这是哪棵树
    assert tree["scope"] == "current_disk_tree_plus_proposal"
    # write 是新建：提议之前这棵树里没有这个目标文件
    assert tree["target_existed_before"] is False
    assert tree["tree_digest"].startswith("sha256:")
    assert "当前磁盘树" in tree["note"]
    assert "兄弟模块" in tree["note"]
    assert "不在" in tree["note"]
    # 进审计的是脱敏摘要：绝对路径不得出现（files_copied 仍是既有顶层键，不重复造）
    dumped = json.dumps(tree, ensure_ascii=False, sort_keys=True)
    assert str(tmp_root) not in dumped
    assert str(tmp_root).replace("\\", "/") not in dumped
    assert str(REPO_ROOT) not in dumped


def test_an_edit_of_an_existing_file_says_the_target_was_already_in_the_tree(
    tmp_root: Path,
) -> None:
    project = copy_validator_project(tmp_root)
    (project / "src" / "shop" / "facade_service.py").write_text(
        '"""占位模块。"""\n\n\nANCHOR = 1\n', encoding="utf-8", newline=""
    )
    payload = edit_payload(project, old_string="ANCHOR = 1", new_string="ANCHOR = 2")

    tree = tree_of(tmp_root, project, payload)

    # edit 改的是已有文件：这与 write 新建必须能分开读
    assert tree["target_existed_before"] is True


def test_the_same_payload_yields_a_byte_identical_tree_section(tmp_root: Path) -> None:
    """相同输入必须得到逐字节相同的证据（AGENTS 第 19 条）：tree 段里没有耗时、没有临时路径。"""

    project = copy_validator_project(tmp_root)
    first = write_payload(
        project, tool_use_id="call-tree-2", target=TEST_TARGET, content=SIBLING_TEST
    )
    second = write_payload(
        project, tool_use_id="call-tree-3", target=TEST_TARGET, content=SIBLING_TEST
    )

    one = tree_of(tmp_root, project, first)
    two = tree_of(tmp_root, project, second)

    assert one == two
    assert json.dumps(one, ensure_ascii=False, sort_keys=True) == json.dumps(
        two, ensure_ascii=False, sort_keys=True
    )


def test_the_tree_digest_separates_the_same_payload_with_and_without_the_sibling(
    tmp_root: Path,
) -> None:
    """P3 的最小复现：同一份文件、同一份配置，只改「兄弟模块在不在」，树指纹必须不同。"""

    project = copy_validator_project(tmp_root)
    payload = write_payload(
        project, tool_use_id="call-tree-4", target=TEST_TARGET, content=SIBLING_TEST
    )

    absent = tree_of(tmp_root, project, payload)
    sibling_path(project).write_text('"""兄弟模块。"""\n', encoding="utf-8", newline="")
    present = tree_of(tmp_root, project, payload)

    # 提议内容与配置一个字都没变：变的只有这棵树
    assert absent["tree_digest"] != present["tree_digest"]
    assert absent["target_existed_before"] is present["target_existed_before"] is False


def test_the_tree_digest_is_stable_and_content_sensitive(tmp_root: Path) -> None:
    """指纹按「排序后的行」算，不看文件系统遍历顺序；多一个文件就必须变。"""

    first = tmp_root / "one"
    second = tmp_root / "two"
    orders = (
        (first, ("b.py", "a.py", "pkg/c.py")),
        (second, ("pkg/c.py", "a.py", "b.py")),
    )
    for root, order in orders:
        for relative in order:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("VALUE = " + repr(relative) + "\n", encoding="utf-8", newline="")

    assert pre_evidence_module._tree_digest(first) == pre_evidence_module._tree_digest(second)
    assert pre_evidence_module._tree_digest(first).startswith("sha256:")
    # 多一个文件（"兄弟模块在不在"）就必须改变指纹
    (first / "pkg" / "sibling.py").write_text('"""兄弟。"""\n', encoding="utf-8", newline="")
    assert pre_evidence_module._tree_digest(first) != pre_evidence_module._tree_digest(second)


def test_the_tree_says_which_project_modules_it_is_missing(tmp_root: Path) -> None:
    """加分项：可能漏、不误报——只报「顶层包已在树里、但这个模块找不到」的那一类。"""

    project = copy_validator_project(tmp_root)
    payload = write_payload(
        project, tool_use_id="call-tree-5", target=TEST_TARGET, content=SIBLING_TEST
    )

    absent = tree_of(tmp_root, project, payload)

    gaps = absent.get("tree_gaps")
    assert isinstance(gaps, dict), "项目档案可读时 tree_gaps 必须给出（没做与没发现要能分开读）"
    assert gaps["status"] == "checked"
    assert gaps["python_roots"] == [".", "src"]
    assert gaps["unresolved_project_modules"] == ["shop.shipment_service"]
    assert "可能漏" in gaps["note"]

    sibling_path(project).write_text('"""兄弟模块。"""\n', encoding="utf-8", newline="")
    present = tree_of(tmp_root, project, payload)

    assert present["tree_gaps"]["unresolved_project_modules"] == []

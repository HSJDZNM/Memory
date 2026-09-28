"""G3 / M2 的端到端取证：pre_evidence 声明之后，证据类规则真的在**动手前**参与判定。

与 `tests/unit/test_dsh_pre_evidence.py` 的分工：

    tests/unit/test_dsh_pre_evidence.py   提议内容、影子副本、预算、审计字段（快）
    本文件                                 真实 Hook + 真实流水线 + （最后一条）真实 CLI

规则不是合成对象，而是写进临时规则目录、由**真实加载器**读出来的 YAML：
"规则是数据"这条约束在这条链路上同样成立，绕过它测出来的结论不算数。

验收要求逐条对上：

- 声明了但取证失败 → exit 2 / evidence_unavailable，执行器一次都不许被调用；
- `edit` 的 old_string 不唯一 → 拒绝（证明不了"改完之后是什么"）；
- 影子目录用完即删；
- 证据到位时证据类 checker 参与判定（matched_rules 里能看到那条规则）；
- 没声明时行为不变（Phase 2 契约：证据类 checker 仍然进 skipped_rules，并显式记录）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import (
    DSH_LAYERS,
    REPO_ROOT,
    copy_validator_project,
    dsh_event,
    rule_document,
    write_dsh_config,
    write_rule,
)

from adapters.dsh.adapter import PolicyEvent, load_config
from adapters.dsh.hooks import (
    EXIT_ALLOW,
    EXIT_BLOCK,
    ControlledExecutor,
    ExecutionOutcome,
    check_wiring,
    run_hook,
)
from adapters.dsh.pre_evidence import PreEvidenceError

pytestmark = pytest.mark.integration

TARGET = "src/shop/facade_service.py"
UNDOCUMENTED = (
    "class Facade:\n"
    '    """有 docstring 的类（模块本身没有 docstring）。"""\n'
    "\n"
    "    def run(self) -> int:\n"
    '        """跑一次。"""\n'
    "\n"
    "        return 1\n"
)
BUILTIN_VALIDATORS = ("py.source", "py.ast", "py.docstring")


class RecordingExecutor(ControlledExecutor):
    """记录调用次数：取证失败时必须是 0 次。"""

    def __init__(self) -> None:
        self.calls: list[PolicyEvent] = []

    def execute(self, event: PolicyEvent) -> ExecutionOutcome:
        self.calls.append(event)
        return ExecutionOutcome(status="executed", detail="recorded by fake executor")

    @property
    def count(self) -> int:
        return len(self.calls)


class _ExplodingProvider:
    """声明了取证、但证据链拿不出证据（缺失 / 崩溃 / 版本不符都走这条路）。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise PreEvidenceError("验证器不可用：注册表声明的 tool.ruff 不在本机")


def controlled_project(tmp_root: Path) -> Path:
    return copy_validator_project(tmp_root)


def rule_dir(tmp_root: Path, *, severity: str = "error") -> Path:
    """把一条**证据类**规则写成数据（source.path 指向它自己，不冒用别的来源）。"""

    root = tmp_root / "rules"
    document = rule_document(
        id="DOC-900",
        version=1,
        name="facade-must-document-module",
        description="模块必须有 docstring；这个问题只有验证器能回答。",
        scope={"language": "python"},
        severity=severity,
        enforcement={"type": "deterministic", "checker": "missing_docstring"},
        rule={"missing_docstring": {"targets": ["module"]}},
        message="模块缺少 docstring。",
        source={"kind": "project-policy", "path": "rules/DOC-900.yaml"},
    )
    write_rule(root / "DOC-900.yaml", document, yaml_module=yaml)
    return root


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


def config_with_evidence(
    tmp_root: Path,
    project: Path,
    rules: Path,
    *,
    shadow_root: Path,
    evidence_overrides: dict | None = None,
    **overrides: object,
) -> Path:
    return write_dsh_config(
        tmp_root / "config" / "pre-evidence.yaml",
        project_root=project,
        rules=rules,
        rules_root=str(tmp_root),
        pre_evidence=pre_evidence_block(project, shadow_root, **(evidence_overrides or {})),
        **overrides,
    )


def config_without_evidence(tmp_root: Path, project: Path, rules: Path) -> Path:
    return write_dsh_config(
        tmp_root / "config" / "phase-2.yaml",
        project_root=project,
        rules=rules,
        rules_root=str(tmp_root),
    )


def hooks_json(tmp_root: Path, *, timeout_seconds: int = 60, name: str = "hooks.json") -> Path:
    """一份最小接线文件：check_wiring 会读它，CLI 用它证明接线成立。"""

    path = tmp_root / name
    path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": (
                                        "python -m adapters.dsh.hooks "
                                        "--config .policy/dsh-adapter.yaml"
                                    ),
                                    "timeout": timeout_seconds,
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
        newline="",
    )
    return path


def write_payload(project: Path, *, tool_use_id: str = "call-pre-1") -> dict:
    return dsh_event(
        "pre-tool-use-write-block.json",
        cwd=str(project),
        tool_name="write",
        tool_input={"file_path": TARGET, "content": UNDOCUMENTED},
        tool_use_id=tool_use_id,
    )


def edit_payload(project: Path, *, old_string: str, new_string: str) -> dict:
    return dsh_event(
        "pre-tool-use-edit-allow.json",
        cwd=str(project),
        tool_name="edit",
        tool_input={
            "file_path": TARGET,
            "old_string": old_string,
            "new_string": new_string,
            "replace_all": False,
        },
        tool_use_id="call-edit-pre",
    )


def decisions(audit: Path) -> list[dict]:
    """审计里所有**判定**记录（授权与留痕记录另有形状，不算判定）。"""

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


def codes(audit: Path) -> list[str]:
    return [
        json.loads(line)["reason_code"]
        for line in audit.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# --------------------------------------------------------------------------- 取证成功


def test_the_evidence_rule_participates_and_blocks_the_write(tmp_root: Path) -> None:
    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    shadow_root = tmp_root / "shadow"
    config_path = config_with_evidence(tmp_root, project, rules, shadow_root=shadow_root)
    audit = tmp_root / "audit.jsonl"
    executor = RecordingExecutor()

    outcome = run_hook(
        write_payload(project),
        config_path=config_path,
        hooks_config_path=hooks_json(tmp_root),
        audit_path=audit,
        executor=executor,
    )

    assert outcome.exit_code == EXIT_BLOCK, outcome.stderr
    assert outcome.reason_code == "policy_block"
    # 阻断理由里必须是**那条证据类规则**，而不是"没有证据"这类兜底
    assert "DOC-900@1" in outcome.stderr
    assert executor.count == 0

    record = last_decision(audit)
    assert record["decision"] == "block"
    # 关键断言：这条规则从 skipped_rules 搬进了 matched_rules（"参与判定"）
    assert "DOC-900@1" in record["matched_rules"]
    assert "DOC-900@1" not in record["skipped_rules"]
    assert record["effective_rule_count"] >= 1
    assert record["pre_evidence_status"] == "collected"
    assert "missing_docstring" in record["pre_evidence"]["served_checkers"]
    assert record["pre_evidence"]["target_sha256"].startswith("sha256:")
    assert record["pre_evidence"]["validators"]
    # P1：账本必须答得出"哪几条规则真的报了违规"（matched_rules 只是"参与过判定"）
    assert [item["rule_id"] for item in record["violations"]] == ["DOC-900@1"]
    assert record["violations_by_severity"] == {"error": 1}
    assert record["violations_note"]
    # M3：这条规则是 error 级，因此它出现在"有阻断力且真的参与判定"的那一格里
    assert record["evaluated_by_severity"] == {"error": 1}
    assert record["blocking_capable_rule_count"] == 1
    # 影子副本用完即删
    assert not shadow_root.exists() or list(shadow_root.iterdir()) == []


def test_a_warning_severity_evidence_rule_only_warns(tmp_root: Path) -> None:
    """M3：证据到位 ≠ 拦得住。warning 级规则参与判定，但仍然只产出 allow_with_warnings。"""

    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root, severity="warning")
    config_path = config_with_evidence(tmp_root, project, rules, shadow_root=tmp_root / "shadow")
    audit = tmp_root / "audit.jsonl"
    executor = RecordingExecutor()

    outcome = run_hook(
        write_payload(project),
        config_path=config_path,
        hooks_config_path=hooks_json(tmp_root),
        audit_path=audit,
        executor=executor,
    )

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    assert outcome.reason_code == "allow_with_warnings"
    record = last_decision(audit)
    assert "DOC-900@1" in record["matched_rules"]
    assert record["evaluated_by_severity"] == {"warning": 1}
    assert "error" not in record["evaluated_by_severity"]
    assert record["advisory_rule_count"] == 1
    assert record["blocking_capable_rule_count"] == 0
    assert "拦不下任何东西" in record["severity_note"]
    # P1 的现场：warning 命中拦不下任何东西，但**它必须出现在账本里**——
    # 修复前这类记录只写 matched_rules 全集，读数的人根本看不出"被提醒过"
    assert [item["rule_id"] for item in record["violations"]] == ["DOC-900@1"]
    assert record["violations_by_severity"] == {"warning": 1}


# --------------------------------------------------------------------------- 取证失败 / Phase 2 契约


def test_without_the_declaration_the_same_payload_is_skipped_not_checked(tmp_root: Path) -> None:
    """Phase 2 契约：同一条载荷、同一套规则，没有声明时那条规则只是被跳过。"""

    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    config_path = config_without_evidence(tmp_root, project, rules)
    audit = tmp_root / "audit.jsonl"
    executor = RecordingExecutor()
    calls: list[tuple] = []

    def two_arg_evaluator(ruleset, context):
        from policy.engine import evaluate

        calls.append((ruleset, context))
        return evaluate(ruleset, context)

    outcome = run_hook(
        write_payload(project),
        config_path=config_path,
        hooks_config_path=hooks_json(tmp_root),
        audit_path=audit,
        executor=executor,
        evaluator=two_arg_evaluator,
    )

    # 注入的是 2 参数替身：调用形状一旦变成传 evidence，这里会直接 internal_error
    assert len(calls) == 1
    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    record = last_decision(audit)
    assert record["decision"] == "allow"
    assert "DOC-900@1" in record["skipped_rules"]
    assert "DOC-900@1" not in record["matched_rules"]
    assert record["pre_evidence_status"] == "not_declared"
    assert "pre_evidence" not in record
    # 既有字段一个不少（只增不改）
    for key in (
        "matched_rules",
        "skipped_rules",
        "effective_rule_count",
        "skipped_rule_count",
        "skipped_reason",
        "checker_scope",
        "checker_scope_note",
        "rule_set_hash",
        "payload_digest",
    ):
        assert key in record, key
    assert executor.count == 1


def test_a_declared_but_failing_provider_blocks_and_never_executes(tmp_root: Path) -> None:
    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    config_path = config_with_evidence(tmp_root, project, rules, shadow_root=tmp_root / "shadow")
    audit = tmp_root / "audit.jsonl"
    executor = RecordingExecutor()
    provider = _ExplodingProvider()

    outcome = run_hook(
        write_payload(project),
        config_path=config_path,
        hooks_config_path=hooks_json(tmp_root),
        audit_path=audit,
        executor=executor,
        evidence_provider=provider,
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "evidence_unavailable"
    assert provider.calls == 1
    assert executor.count == 0
    assert "拒绝在证明不了的情况下放行" in outcome.stderr
    assert "evidence_unavailable" in codes(audit)
    # 失败关闭不是判定：不得留下"规则查过了"的假象
    assert decisions(audit) == []
    entry = json.loads(audit.read_text(encoding="utf-8").splitlines()[0])
    assert entry["pre_evidence_status"] == "unavailable"
    assert entry["pre_evidence"]["status"] == "unavailable"


def test_a_duplicated_old_string_is_refused_before_anything_is_copied(tmp_root: Path) -> None:
    project = controlled_project(tmp_root)
    (project / "src" / "shop" / "facade_service.py").write_text(
        '"""重复出现的锚点。"""\n\n\nVALUE = 1\nVALUE = 2\n', encoding="utf-8", newline=""
    )
    rules = rule_dir(tmp_root)
    shadow_root = tmp_root / "shadow"
    config_path = config_with_evidence(tmp_root, project, rules, shadow_root=shadow_root)
    audit = tmp_root / "audit.jsonl"
    executor = RecordingExecutor()

    outcome = run_hook(
        edit_payload(project, old_string="VALUE", new_string="OTHER"),
        config_path=config_path,
        hooks_config_path=hooks_json(tmp_root),
        audit_path=audit,
        executor=executor,
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "evidence_unavailable"
    # 理由要能一次读懂：出现次数 + "证明不了"
    assert "出现 2 次" in outcome.stderr
    assert "证明" in outcome.stderr
    assert executor.count == 0
    # 拒绝发生在复制之前：连影子目录都不该存在
    assert not shadow_root.exists()


def test_the_shadow_copy_is_gone_after_the_real_pipeline_ran(tmp_root: Path) -> None:
    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    shadow_root = tmp_root / "shadow"
    config_path = config_with_evidence(tmp_root, project, rules, shadow_root=shadow_root)

    outcome = run_hook(
        write_payload(project),
        config_path=config_path,
        hooks_config_path=hooks_json(tmp_root),
        audit_path=tmp_root / "audit.jsonl",
        executor=RecordingExecutor(),
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert not shadow_root.exists() or list(shadow_root.iterdir()) == []


def test_the_evidence_summary_says_which_tree_it_was_gathered_on(tmp_root: Path) -> None:
    """P3：读数的人必须知道这条证据属于哪棵树（当前磁盘树 + 本次提议，批次里其它写入不在内）。"""

    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    config_path = config_with_evidence(tmp_root, project, rules, shadow_root=tmp_root / "shadow")
    audit = tmp_root / "audit.jsonl"

    outcome = run_hook(
        write_payload(project),
        config_path=config_path,
        hooks_config_path=hooks_json(tmp_root),
        audit_path=audit,
        executor=RecordingExecutor(),
    )

    assert outcome.exit_code == EXIT_BLOCK, outcome.stderr
    record = last_decision(audit)
    tree = record["pre_evidence"]["tree"]
    assert tree["scope"] == "current_disk_tree_plus_proposal"
    # write 是新建：提议之前这棵树里没有这个目标文件
    assert tree["target_existed_before"] is False
    assert tree["tree_digest"].startswith("sha256:")
    assert "当前磁盘树" in tree["note"]
    assert "兄弟模块" in tree["note"]


# --------------------------------------------------------------------------- 接线自检


def test_wiring_requires_the_evidence_budget_to_fit_inside_the_hook_timeout(
    tmp_root: Path,
) -> None:
    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    config = load_config(
        config_with_evidence(tmp_root, project, rules, shadow_root=tmp_root / "shadow")
    )

    # 30s 的 dsh 超时 < 30s 取证预算 + 5s 判定预算：dsh 会先杀进程，而"被杀"等于放行
    too_tight = check_wiring(config, hooks_config_path=hooks_json(tmp_root, timeout_seconds=30))
    assert "pre_evidence" in too_tight
    assert "35000ms" in too_tight

    # 60s 足够容纳两段预算：没有接线错误
    assert check_wiring(config, hooks_config_path=hooks_json(tmp_root, timeout_seconds=60)) == ""


def test_wiring_output_is_byte_identical_without_the_declaration(tmp_root: Path) -> None:
    """pre_evidence 为 None 时，既有输出逐字节不变（Phase 2 契约）。"""

    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    with_block = load_config(
        config_with_evidence(tmp_root, project, rules, shadow_root=tmp_root / "shadow")
    )
    without_block = load_config(config_without_evidence(tmp_root, project, rules))
    tight = hooks_json(tmp_root, timeout_seconds=3, name="tight.json")

    assert check_wiring(with_block, hooks_config_path=tight) == check_wiring(
        without_block, hooks_config_path=tight
    )
    assert "不大于内部预算" in check_wiring(without_block, hooks_config_path=tight)
    # 没有声明时，宽松的超时也不该冒出任何 pre_evidence 相关的话
    assert "pre_evidence" not in check_wiring(
        without_block, hooks_config_path=hooks_json(tmp_root, timeout_seconds=60)
    )


def test_a_declared_then_disabled_block_changes_nothing_but_the_status(tmp_root: Path) -> None:
    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    config_path = config_with_evidence(
        tmp_root,
        project,
        rules,
        shadow_root=tmp_root / "shadow",
        evidence_overrides={"enabled": False},
    )
    audit = tmp_root / "audit.jsonl"
    provider = _ExplodingProvider()

    outcome = run_hook(
        write_payload(project),
        config_path=config_path,
        hooks_config_path=hooks_json(tmp_root),
        audit_path=audit,
        executor=RecordingExecutor(),
        evidence_provider=provider,
    )

    assert provider.calls == 0
    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    record = last_decision(audit)
    assert record["pre_evidence_status"] == "disabled"
    assert "pre_evidence" not in record
    assert "DOC-900@1" in record["skipped_rules"]


# --------------------------------------------------------------------------- 真实 CLI


def cli_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_cli(
    *, config_path: Path, wiring: Path, audit: Path, payload: dict
) -> subprocess.CompletedProcess:
    """跑生产入口（python -m adapters.dsh.hooks），返回真实进程结果。"""

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "adapters.dsh.hooks",
            "--config",
            str(config_path),
            "--hooks-config",
            str(wiring),
            "--audit",
            str(audit),
        ],
        cwd=REPO_ROOT,
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=cli_env(),
        check=False,
    )


def test_the_production_cli_blocks_the_write_on_evidence(tmp_root: Path) -> None:
    """生产入口（python -m adapters.dsh.hooks）整条链：声明 → 取证 → 证据类规则 → exit 2。"""

    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    config_path = config_with_evidence(tmp_root, project, rules, shadow_root=tmp_root / "shadow")
    audit = tmp_root / "audit.jsonl"
    payload = write_payload(project)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "adapters.dsh.hooks",
            "--config",
            str(config_path),
            "--hooks-config",
            str(hooks_json(tmp_root)),
            "--audit",
            str(audit),
        ],
        cwd=REPO_ROOT,
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=cli_env(),
        check=False,
    )

    assert completed.returncode == EXIT_BLOCK
    assert completed.stdout == ""
    assert "DOC-900@1" in completed.stderr
    assert "VERDICT" in completed.stderr
    record = last_decision(audit)
    assert record["pre_evidence_status"] == "collected"
    assert "DOC-900@1" in record["matched_rules"]


def test_the_audit_says_which_language_coverage_this_evidence_had(tmp_root: Path) -> None:
    """P2 收尾：语言维度的显式判定必须能从**审计**读出来（不只在流水线报告里）。

    `.md`（text 语言）写入在 P2 之前是 evidence_unavailable / 退出码 2（07 §3.4 的现场）；
    现在它是一条**显式判定**（not_covered_by_design），而这条判定只有进了 pre_evidence 摘要，
    读数的人才不必去翻代码或流水线报告。对照：`.py` 载荷是 covered_by_rule_pack。
    """

    project = controlled_project(tmp_root)
    rules = rule_dir(tmp_root)
    shadow_root = tmp_root / "shadow"
    config_path = write_dsh_config(
        tmp_root / "config" / "text-language.yaml",
        project_root=project,
        rules=rules,
        rules_root=str(tmp_root),
        # .md 目标既要有语言（default_language: text），也要有层（docs），否则 Adapter 会
        # 在更早的一步按失败关闭拒绝，用例测不到取证那一段。
        default_language="text",
        layers=[{"pattern": "**/*.md", "layer": "docs"}]
        + [{"pattern": pattern, "layer": layer} for pattern, layer in DSH_LAYERS],
        pre_evidence=pre_evidence_block(project, shadow_root),
    )

    audit = tmp_root / "audit.jsonl"
    wiring = hooks_json(tmp_root)

    markdown = run_cli(
        config_path=config_path,
        wiring=wiring,
        audit=audit,
        payload=dsh_event(
            "pre-tool-use-write-block.json",
            cwd=str(project),
            tool_name="write",
            tool_input={
                "file_path": "README.md",
                "content": "# invsvc" + chr(10) + chr(10) + "探针写入的说明。" + chr(10),
            },
            tool_use_id="call-readme-text",
        ),
    )

    # P2 修完之后这类写入不再失败关闭：判定是 allow，而且理由写在 coverage 里
    assert markdown.returncode == EXIT_ALLOW, markdown.stderr
    record = last_decision(audit)
    assert record["decision"] == "allow"
    coverage = record["pre_evidence"]["language_coverage"]
    assert coverage["language"] == "text"
    assert coverage["status"] == "not_covered_by_design"
    assert coverage["declared_in"] == "validation/validators.yaml"
    assert coverage["reason"]
    # 规则一条都没参与（DOC-900 是 python 作用域）：跳过不等于通过
    assert "DOC-900@1" in record["skipped_rules"]

    # 对照：同一条通道上的 .py 载荷是"有 rule pack"的那一档
    python = run_cli(
        config_path=config_path,
        wiring=wiring,
        audit=audit,
        payload=write_payload(project, tool_use_id="call-python-control"),
    )

    assert python.returncode == EXIT_BLOCK, python.stderr
    python_record = last_decision(audit)
    assert python_record["pre_evidence"]["language_coverage"]["status"] == "covered_by_rule_pack"
    assert "DOC-900@1" in python_record["matched_rules"]

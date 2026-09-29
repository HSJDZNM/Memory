"""P1：判定记录必须能读出「哪几条规则真的报了违规」（07 号报告 §4 P1）。

`matched_rules` 的语义是「参与过判定」。06 轮参与面只有 1 条，于是「参与」与「报违规」在账本上
长得一样；07 轮治理全开之后参与面变成 43 条，block / allow_with_warnings 的记录里却**找不到
任何一条**真正报违规的规则——那份清单只活在给模型看的 stderr 里。修复把同一份清单搬进审计。

本文件既做确定性单测（直接调用可见性计算，不依赖工具注册表），也跑**生产 Hook CLI**
（python -m adapters.dsh.hooks）把三类判定（block / allow_with_warnings / allow）与
「没有做出判定」的记录（context_error / evidence_unavailable）写成真实审计再读回来。

口径（三条都要能分开读）：

- violations：本次**真的报了违规**的规则（可以是空列表，但判定记录里必须出现这个键）；
- matched_rules：本次**参与过判定**的规则（既有字段，语义不变）；
- 没有 violations 键的记录 = 本次**没有做出判定**，不是「判定了、没违规」。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import REPO_ROOT, dsh_event, make_checker_rule, write_dsh_config
from test_hook_skip_visibility import EXISTING_GOVERNED_FIELDS

from adapters.dsh.adapter import load_config
from adapters.dsh.hooks import (
    EXIT_ALLOW,
    EXIT_BLOCK,
    DshPreExecuteHook,
    run_hook,
)
from adapters.dsh.pre_evidence import PreEvidenceError
from orchestration.client import decision_reason
from policy.models import (
    Decision,
    Evidence,
    RequiredAction,
    RuleSet,
    Severity,
    ValidationResult,
    Violation,
)

# 只用标准库实现的验证器：不依赖本机有没有装 ruff / mypy。
BUILTIN_VALIDATORS = ("py.source", "py.ast", "py.docstring")

# 真实 DOC-001 的反例内容（没有模块 / 类 / 函数 docstring）。
DOC_001_BAD = (REPO_ROOT / "tests" / "fixtures" / "rules" / "DOC-001" / "bad.py").read_text(
    encoding="utf-8"
)
# 干净内容：模块 docstring 与顶层函数 docstring 都在。
CLEAN_MODULE = (
    '"""有 docstring 的模块。"""\n'
    "\n"
    "\n"
    "def run() -> int:\n"
    '    """跑一次。"""\n'
    "\n"
    "    return 1\n"
)

WARNING_TARGET = "src/shop/undocumented_service.py"
CLEAN_TARGET = "src/shop/document_service.py"


def records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def last_decision(path: Path) -> dict:
    for record in reversed(records(path)):
        if "decision" in record:
            return record
    raise AssertionError(f"审计里没有判定记录：{path}")


def last_with_reason(path: Path, reason_code: str) -> dict:
    for record in reversed(records(path)):
        if record.get("reason_code") == reason_code:
            return record
    raise AssertionError(f"审计里没有 {reason_code} 记录：{path}")


def payload(name: str, project: Path, **overrides: object) -> dict:
    return dsh_event(name, cwd=str(project), **overrides)


def hooks_json(tmp_root: Path, *, timeout_seconds: int = 60) -> Path:
    """最小接线文件：check_wiring 会读它，CLI 用它证明接线成立（G12）。"""

    path = tmp_root / "hooks.json"
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


def run_cli(
    *, config_path: Path, wiring: Path, audit: Path, raw: dict
) -> subprocess.CompletedProcess:
    """跑生产入口，返回进程结果；审计与判定行都来自真实进程。"""

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
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
        input=json.dumps(raw, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


def pre_evidence_block(project: Path, shadow_root: Path) -> dict:
    return {
        "registry_root": str(REPO_ROOT / "validation"),
        "workspace": str(project),
        "shadow_root": str(shadow_root),
        "exclude": [".git/**", ".policy/**", "__pycache__/**"],
        "validators": list(BUILTIN_VALIDATORS),
        "timeout_ms": 30000,
    }


def doc_001_rules(tmp_root: Path) -> Path:
    """把**真实**的 DOC-001 规则文件复制进临时规则目录。

    只复制这一条：这样证据类 checker 只有 missing_docstring 一个，不需要本机装 ruff / pytest，
    仍然走真实加载器与真实流水线（合成规则对象不算数）。
    """

    target = tmp_root / "rules"
    target.mkdir(parents=True, exist_ok=True)
    (target / "DOC-001.yaml").write_text(
        (REPO_ROOT / "policies" / "coding" / "DOC-001.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="",
    )
    return target


class _ExplodingProvider:
    """声明了取证、但证据链拿不出证据（缺失 / 崩溃 / 版本不符都走这条路）。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise PreEvidenceError("验证器不可用：注册表声明的 tool.ruff 不在本机")


def visibility_hook(config_path) -> DshPreExecuteHook:
    """只用来算可见性的 Hook：规则集是合成的，不依赖工具注册表 / 验证器。"""

    rules = RuleSet(
        rules=(
            make_checker_rule("ARCH-001", checker="forbidden_dependency"),
            make_checker_rule(
                "DOC-001",
                checker="missing_docstring",
                body={"missing_docstring": {"targets": ["module"]}},
                severity="warning",
            ),
        ),
        source_paths=(),
    )
    return DshPreExecuteHook(config=load_config(config_path), rules=rules)


def report(
    rule_id: str,
    *,
    version: int = 1,
    severity: Severity = Severity.ERROR,
    message: str = "禁止直接依赖仓储层。",
    value: str = "repository",
) -> Violation:
    return Violation(
        rule_id=rule_id,
        rule_version=version,
        severity=severity,
        message=message,
        evidence=Evidence(kind="import", subject=f"{rule_id}@{version}", value=value, line=1),
    )


# --------------------------------------------------------------------------- 确定性单测


def test_the_rules_that_reported_are_listed_with_their_canonical_identity(dsh_config_path):
    hook = visibility_hook(dsh_config_path)
    decision = ValidationResult(
        decision=Decision.BLOCK,
        request_id="req-1",
        matched_rules=("ARCH-001@1", "DOC-001@1", "STYLE-006@2"),
        violations=(
            # 刻意乱序：可见性必须按 Violation.sort_key 稳定排序
            report("STYLE-006", version=2, value="zzz"),
            report("ARCH-001", value="repository"),
        ),
    )

    visibility = hook.violation_visibility(decision)

    assert [item["rule_id"] for item in visibility["violations"]] == [
        "ARCH-001@1",
        "STYLE-006@2",
    ]
    assert [item["severity"] for item in visibility["violations"]] == ["error", "error"]
    assert visibility["violations"][0]["message"] == "禁止直接依赖仓储层。"
    assert visibility["violations_by_severity"] == {"error": 2}
    assert "violations_note" in visibility


def test_the_violation_evidence_keeps_the_decision_protocol_shape(dsh_config_path):
    """能复用既有序列化就别另写一份：evidence 子对象与决策载荷逐字段相等。"""

    hook = visibility_hook(dsh_config_path)
    decision = ValidationResult(
        decision=Decision.BLOCK,
        request_id="req-1",
        violations=(report("ARCH-001"),),
    )

    visibility = hook.violation_visibility(decision)
    protocol = decision.to_decision_dict()["violations"][0]

    assert visibility["violations"][0]["evidence"] == protocol["evidence"]
    assert visibility["violations"][0]["message"] == protocol["message"]
    assert visibility["violations"][0]["severity"] == protocol["severity"]


def test_warning_hits_are_listed_even_though_they_cannot_block(dsh_config_path):
    hook = visibility_hook(dsh_config_path)
    decision = ValidationResult(
        decision=Decision.ALLOW_WITH_WARNINGS,
        request_id="req-1",
        matched_rules=("DOC-001@1",),
        violations=(report("DOC-001", severity=Severity.WARNING, value="missing"),),
    )

    visibility = hook.violation_visibility(decision)

    assert [item["rule_id"] for item in visibility["violations"]] == ["DOC-001@1"]
    assert visibility["violations_by_severity"] == {"warning": 1}


def test_an_allow_decision_says_there_were_no_violations(dsh_config_path):
    hook = visibility_hook(dsh_config_path)
    decision = ValidationResult(decision=Decision.ALLOW, request_id="req-1")

    visibility = hook.violation_visibility(decision)

    # 「判定了、没违规」是一个明确的结论，不是一个缺失的键
    assert visibility["violations"] == []
    assert visibility["violations_by_severity"] == {}


def test_the_note_writes_down_the_two_meanings(dsh_config_path):
    hook = visibility_hook(dsh_config_path)
    note = hook.violation_visibility(
        ValidationResult(decision=Decision.ALLOW, request_id="req-1")
    )["violations_note"]

    assert "真的报了违规" in note
    assert "参与过判定" in note
    assert "allow_with_warnings" in note
    # 哪些记录没有这个键，必须写在口径旁边，而不是靠读者猜
    assert "没有做出判定" in note


def test_the_required_action_is_visible_on_every_violation(dsh_config_path):
    hook = visibility_hook(dsh_config_path)
    decision = ValidationResult(
        decision=Decision.BLOCK,
        request_id="req-1",
        violations=(report("ARCH-001"),),
        required_action=RequiredAction.APPROVAL,
    )

    items = hook.violation_visibility(decision)["violations"]

    assert items[0]["required_action"] == "approval"
    # 没有 required_action 时不写这个键（不伪造"需要审批"）
    plain = hook.violation_visibility(
        ValidationResult(
            decision=Decision.BLOCK, request_id="req-1", violations=(report("ARCH-001"),)
        )
    )["violations"]
    assert "required_action" not in plain[0]


def test_the_audit_says_which_kind_of_block_this_was(dsh_config_path, dsh_project):
    """台阶 3a（H1）：账本要答得出「这次 block 属于哪一类」，且归类是**结构**的。

    为什么必须有它：`block` + `violations` 为空的记录在账本上只能读成"没有依据"，
    而审批门禁正是**合法**的空 violations 形态（快照 `decisions/approval.json` 就是它）。
    这条用例同时钉住"不许靠中文 message 猜"：instruction 里给出的 rule_id 是
    `APPROVAL-001`，归类看的是 required_action，不是那句话。
    """

    hook = visibility_hook(dsh_config_path)

    approval = ValidationResult(
        decision=Decision.BLOCK,
        request_id="req-approval",
        required_action=RequiredAction.APPROVAL,
    )
    assert hook.decision_reason_for_audit(approval) == "approval_required"

    violation = ValidationResult(
        decision=Decision.BLOCK,
        request_id="req-violation",
        violations=(report("ARCH-001"),),
    )
    assert hook.decision_reason_for_audit(violation) == "policy_violation"

    # allow 与 allow_with_warnings 没有 block 归类——不写这个键（不编造）
    assert (
        hook.decision_reason_for_audit(
            ValidationResult(decision=Decision.ALLOW, request_id="req-allow")
        )
        is None
    )
    # 说不出理由的 block：**构造不出来**（模型自洽校验会拒绝：decision 必须与
    # violations/required_action 一致）。也就是说"block + 空 violations"在判定层**只有**
    # 审批门禁这一种合法形态——这一条本身就是本台阶穷举结论的钉子。
    with pytest.raises(ValidationError):
        ValidationResult(decision=Decision.BLOCK, request_id="req-silent")
    # 归类函数本身仍要能回答"说不出来"（消费方不许把 None 读成某一种）。
    assert decision_reason(Decision.BLOCK, required_action=None, violations=()) is None


def test_the_violation_payload_is_sanitized(dsh_config_path, dsh_project):
    """AGENTS 第 16 条：绝对路径与凭据不得进审计（message / evidence 都要过 sanitize）。"""

    hook = visibility_hook(dsh_config_path)
    decision = ValidationResult(
        decision=Decision.BLOCK,
        request_id="req-1",
        violations=(
            report(
                "ARCH-001",
                # 合成值：用于验证 violations 的 message 也过脱敏
                message=f"禁止依赖 {dsh_project}/src/shop/x.py  Authorization: Bearer sk-abcdefghijkl",  # secret-scan: allow（合成值）
                value="/etc/passwd",
            ),
        ),
    )

    items = hook.violation_visibility(decision)["violations"]
    dumped = json.dumps(items, ensure_ascii=False)

    assert str(dsh_project) not in dumped
    assert str(dsh_project).replace("\\", "/") not in dumped
    assert "/etc/passwd" not in dumped
    assert "sk-abcdefghijkl" not in dumped  # secret-scan: allow（断言合成值已被抹掉）
    assert "<repo>" in dumped


# --------------------------------------------------------------------------- 生产 CLI


def test_the_production_cli_block_record_names_the_violating_rule(
    tmp_root: Path, dsh_config_path, dsh_project
) -> None:
    """验收 1：命中 ARCH-001 的写类载荷 → block 记录里读得出那条规则（canonical ID）。"""

    audit = tmp_root / "audit.jsonl"
    raw = payload("pre-tool-use-write-block.json", dsh_project)

    completed = run_cli(
        config_path=dsh_config_path, wiring=hooks_json(tmp_root), audit=audit, raw=raw
    )

    assert completed.returncode == EXIT_BLOCK, completed.stderr
    record = last_decision(audit)
    assert record["decision"] == "block"
    assert record["reason_code"] == "policy_block"
    # 这就是 P1：账本答得出「哪几条规则报了违规」，而不是只有 43 条"参与过判定"
    assert record["violations"], record
    assert record["violations"][0]["rule_id"] == "ARCH-001@1"
    assert record["violations"][0]["severity"] == "error"
    assert record["violations"][0]["message"]
    assert set(record["violations"][0]["evidence"]) >= {"kind", "subject", "value"}
    assert record["violations_by_severity"] == {
        "error": sum(1 for item in record["violations"] if item["severity"] == "error")
    }
    # matched_rules 的语义不变：它仍然是"参与过判定"的集合
    assert "ARCH-001@1" in record["matched_rules"]
    assert record["rule_count"] == len(record["matched_rules"]) + len(record["skipped_rules"])
    # 给模型看的 stderr 与账本是同一份清单
    assert "ARCH-001@1" in completed.stderr
    assert record["violations_note"]


def test_the_production_cli_warning_record_names_the_advisory_rule(
    tmp_root: Path, dsh_project
) -> None:
    """验收 2：证据到位、warning 级命中 → allow_with_warnings 的记录里读得出那条规则。"""

    project = dsh_project
    rules = doc_001_rules(tmp_root)
    config_path = write_dsh_config(
        tmp_root / "config" / "doc-001.yaml",
        project_root=project,
        rules=rules,
        pre_evidence=pre_evidence_block(project, tmp_root / "shadow"),
    )
    audit = tmp_root / "audit.jsonl"
    raw = payload(
        "pre-tool-use-write-block.json",
        project,
        tool_input={"file_path": WARNING_TARGET, "content": DOC_001_BAD},
        tool_use_id="call-doc-001-warning",
    )

    completed = run_cli(
        config_path=config_path, wiring=hooks_json(tmp_root), audit=audit, raw=raw
    )

    assert completed.returncode == EXIT_ALLOW, completed.stderr
    record = last_decision(audit)
    assert record["decision"] == "allow_with_warnings"
    assert record["pre_evidence_status"] == "collected"
    assert {item["rule_id"] for item in record["violations"]} == {"DOC-001@1"}
    assert record["violations_by_severity"] == {"warning": len(record["violations"])}
    # P1 的现场：这条 warning 命中在修复前只出现在 stderr 里（账本里一个字都没有）
    assert "DOC-001@1" in completed.stderr
    assert record["violations_note"]


def test_the_production_cli_allow_record_has_an_empty_violation_list(
    tmp_root: Path, dsh_project
) -> None:
    """验收 3：判定为 allow 的记录带 violations=[] 与口径说明（与"没有判定"区分开）。"""

    project = dsh_project
    rules = doc_001_rules(tmp_root)
    config_path = write_dsh_config(
        tmp_root / "config" / "doc-001.yaml",
        project_root=project,
        rules=rules,
        pre_evidence=pre_evidence_block(project, tmp_root / "shadow"),
    )
    audit = tmp_root / "audit.jsonl"
    raw = payload(
        "pre-tool-use-write-block.json",
        project,
        tool_input={"file_path": CLEAN_TARGET, "content": CLEAN_MODULE},
        tool_use_id="call-doc-001-clean",
    )

    completed = run_cli(
        config_path=config_path, wiring=hooks_json(tmp_root), audit=audit, raw=raw
    )

    assert completed.returncode == EXIT_ALLOW, completed.stderr
    record = last_decision(audit)
    assert record["decision"] == "allow"
    assert record["violations"] == []
    assert record["violations_by_severity"] == {}
    assert "violations_note" in record
    assert record["pre_evidence"]["tree"]["scope"] == "current_disk_tree_plus_proposal"


def test_an_out_of_scope_write_is_a_context_error_without_a_violation_list(
    tmp_root: Path, dsh_config_path, dsh_project
) -> None:
    """验收 4：没有算出 decision 的记录不伪造 violations（"没判定"≠"判定了、没违规"）。"""

    audit = tmp_root / "audit.jsonl"
    raw = payload(
        "pre-tool-use-write-block.json",
        dsh_project,
        tool_input={
            "file_path": str(tmp_root / "outside.py"),
            "content": "VALUE = 1\n",
        },
        tool_use_id="call-out-of-scope",
    )

    completed = run_cli(
        config_path=dsh_config_path, wiring=hooks_json(tmp_root), audit=audit, raw=raw
    )

    assert completed.returncode == EXIT_BLOCK, completed.stderr
    record = last_with_reason(audit, "context_error")
    assert "decision" not in record
    assert "violations" not in record
    assert "violations_by_severity" not in record
    assert "violations_note" not in record
    # 既有口径：连"参与过判定"的名单都没有（规则一条都没跑）
    assert "matched_rules" not in record

    # 正对照：同一条通道上真正做出判定的那次**必须**有 violations。
    # 少了它，这条用例在修复前也天然为真（"谁都没有这个键"），称不上会红的检查。
    decided_raw = payload("pre-tool-use-write-block.json", dsh_project)
    decided = run_cli(
        config_path=dsh_config_path,
        wiring=hooks_json(tmp_root),
        audit=audit,
        raw={**decided_raw, "tool_use_id": "call-in-scope"},
    )

    assert decided.returncode == EXIT_BLOCK, decided.stderr
    assert last_decision(audit)["violations"]


def test_an_unavailable_evidence_path_also_has_no_violation_list(
    tmp_root: Path, dsh_project
) -> None:
    """取证失败是失败关闭，不是判定：同样不许出现 violations。"""

    project = dsh_project
    rules = doc_001_rules(tmp_root)
    config_path = write_dsh_config(
        tmp_root / "config" / "doc-001.yaml",
        project_root=project,
        rules=rules,
        pre_evidence=pre_evidence_block(project, tmp_root / "shadow"),
    )
    audit = tmp_root / "audit.jsonl"
    provider = _ExplodingProvider()

    outcome = run_hook(
        payload(
            "pre-tool-use-write-block.json",
            project,
            tool_input={"file_path": WARNING_TARGET, "content": DOC_001_BAD},
            tool_use_id="call-evidence-unavailable",
        ),
        config_path=config_path,
        audit_path=audit,
        evidence_provider=provider,
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "evidence_unavailable"
    record = last_with_reason(audit, "evidence_unavailable")
    assert "decision" not in record
    assert "violations" not in record
    # 取证失败时摘要里没有 tree 段：那棵树根本没建成
    assert "tree" not in (record.get("pre_evidence") or {})

    # 正对照：同一份配置、同一条载荷，取证成功的那一次是**判定**，必须有 violations；
    # 否则"失败关闭没有伪造违规"这条断言在修复前也天然为真。
    decided = run_hook(
        payload(
            "pre-tool-use-write-block.json",
            project,
            tool_input={"file_path": WARNING_TARGET, "content": DOC_001_BAD},
            tool_use_id="call-evidence-collected",
        ),
        config_path=config_path,
        audit_path=audit,
    )

    assert decided.exit_code == EXIT_ALLOW, decided.stderr
    assert last_decision(audit)["violations"]


def test_the_existing_decision_fields_are_kept_unchanged(
    tmp_root: Path, dsh_project
) -> None:
    """验收 5：既有键一个都不能少、语义不能变（Phase 2 契约：不声明取证的老路径照跑）。"""

    audit = dsh_project.parent / "audit.jsonl"
    # trace_id 是有值才落盘的既有字段：显式声明它，好让"既有键一个都不少"这条断言更强
    config_path = write_dsh_config(
        tmp_root / "config" / "with-trace.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
        trace_id="trace-demo-1",
    )

    outcome = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=config_path,
        audit_path=audit,
    )

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    record = last_decision(audit)
    missing = EXISTING_GOVERNED_FIELDS - set(record)
    # _audit 的既有行为是"取值为 None 就不写"，allow 时 required_action 本来就是 None
    assert missing <= {"required_action"}, sorted(missing)
    assert record["decision"] == "allow"
    assert isinstance(record["matched_rules"], list)
    assert all(isinstance(item, str) for item in record["skipped_rules"])
    assert record["rule_count"] == record["effective_rule_count"] + record["skipped_rule_count"]
    assert record["pre_evidence_status"] == "not_declared"
    assert "pre_evidence" not in record
    # 新增的键只加不改
    assert record["violations"] == []

# --------------------------------------------------------------------------- 阻断理由落在哪一栏


def test_the_block_reason_lands_in_the_documented_field(
    tmp_root: Path, dsh_config_path, dsh_project, monkeypatch
) -> None:
    """P8 的读数口径：三类阻断各有各的栏，读账本不必读代码。

    这是一条**修前修后都通过**的守卫（被钉的行为本来就在）：它的价值是让 README §8.2 那张
    "哪一栏承载哪类理由"的表可验证——尤其是"Phase 4 门禁的理由不在顶层 detail 里"这条，
    07 §4 P8 那句「path_out_of_scope，detail 为空」就是按 detail 去读 Phase 4 的记录读出来的。
    """

    from enforcement.action import ActionRequestError

    from adapters.dsh.hooks import AuditLedger

    audit = tmp_root / "audit.jsonl"
    # ① 规则级 block：理由是结构化的判定字段，没有一段自由文本
    run_cli(
        config_path=dsh_config_path,
        wiring=hooks_json(tmp_root),
        audit=audit,
        raw=payload("pre-tool-use-write-block.json", dsh_project),
    )
    rule_block = last_decision(audit)
    assert rule_block["reason_code"] == "policy_block"
    assert rule_block["violations"]
    assert "detail" not in rule_block

    # ② 失败关闭：理由在顶层 detail
    run_cli(
        config_path=dsh_config_path,
        wiring=hooks_json(tmp_root),
        audit=audit,
        raw=payload(
            "pre-tool-use-write-block.json",
            dsh_project,
            tool_input={"file_path": str(tmp_root / "outside.py"), "content": "VALUE = 1\n"},
            tool_use_id="call-reason-context-error",
        ),
    )
    failed = last_with_reason(audit, "context_error")
    assert failed["detail"]
    assert "enforcement_detail" not in failed

    # ③ Phase 4 门禁：理由在 enforcement_reason / enforcement_detail，顶层 detail 为空
    hook = DshPreExecuteHook(
        config=load_config(dsh_config_path),
        rules=RuleSet(rules=(), source_paths=()),
        ledger=AuditLedger(audit),
    )
    assert hook.bridge is not None

    def refuse(**_kwargs: object) -> None:
        raise ActionRequestError(
            "参数 workdir 不在受控工作区内：路径不在仓库之内", reason_code="path_out_of_scope"
        )

    monkeypatch.setattr(hook.bridge, "build_request", refuse)
    outcome = hook.handle(payload("pre-tool-use-edit-allow.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "path_out_of_scope"
    gated = last_with_reason(audit, "path_out_of_scope")
    assert gated["enforcement_reason"] == "path_out_of_scope"
    assert gated["enforcement_detail"]
    # 两个键不写同一个值：一个意思两个名字正是 P7 要消掉的读数陷阱
    assert "detail" not in gated

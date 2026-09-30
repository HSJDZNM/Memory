"""台阶 4 / 21 号 §2.2：Hook 审计记录的 `reading_context` 与 `pre_evidence.registry`。

三件事各有用例，每条都写成"会失败"的形状（不是复述实现）：

1. **形状与归属**：真 Hook 路径（`run_hook` + 声明并启用 pre_evidence）写出的记录里，
   `reading_context.tree` **引用本记录取证树**的那组值、`declarations.registry.digest` 与
   `pre_evidence.registry.digest` 是同一个值、且与验证器层的 config_digest 逐字符相同；
   整条记录里不出现绝对路径；
2. **延迟硬约束的结构化版本**：把 `provenance.reading_context.workspace_tree_digest` 换成
   "一调就炸"，一次真 Hook 调用仍然成功——"每次调用不许计算整棵树的摘要"因此是一条
   **会失败的检查**（谁把 `tree_block` 接回来，这条用例就红）；
3. **兼容**：已有 `audit.jsonl` 里的 1.2 记录**一个字节都不改写**；1.2 与 1.3 混排之后
   审计链校验（`enforcement.audit.FileAuditSink.verify`）仍然通过。

第 4 条口径写在用例里而不是文档里：`host.sandbox` 恒为 `unknown`——Hook 不探测沙箱
（探测要有副作用），"不知道"就写"不知道"（21 号 §9.2 裁定④的同一条口径）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import (
    REPO_ROOT,
    copy_validator_project,
    dsh_event,
    rule_document,
    write_dsh_config,
    write_rule,
)

from adapters.dsh.hooks import AUDIT_SCHEMA_VERSION, EXIT_BLOCK, run_hook
from enforcement.audit import FileAuditSink
from provenance import reading_context as reading
from validators.registry import config_digest

TARGET = "src/shop/cart_service.py"
# 没有模块 docstring：证据类规则 DOC-900 必须命中它，取证因此必须真的发生。
UNDOCUMENTED = (
    "from repository import CartRepository" + chr(10) + chr(10) + chr(10)
    + "class CartService:" + chr(10)
    + "    def __init__(self) -> None:" + chr(10)
    + "        self.repository = CartRepository()" + chr(10)
)


def evidence_config(tmp_root: Path) -> tuple[Path, Path]:
    """受控项目 + 声明了 pre_evidence 的 adapter 配置。"""

    project = copy_validator_project(tmp_root)
    rules = tmp_root / "rules"
    write_rule(
        rules / "DOC-900.yaml",
        rule_document(
            id="DOC-900",
            version=1,
            name="module-must-have-docstring",
            description="模块必须有 docstring；这个问题只有验证器能回答。",
            scope={"language": "python"},
            severity="error",
            enforcement={"type": "deterministic", "checker": "missing_docstring"},
            rule={"missing_docstring": {"targets": ["module"]}},
            message="模块缺少 docstring。",
            source={"kind": "project-policy", "path": "rules/DOC-900.yaml"},
        ),
        yaml_module=yaml,
    )
    config = write_dsh_config(
        tmp_root / "config" / "dsh-adapter.yaml",
        project_root=project,
        rules=rules,
        rules_root=str(tmp_root),
        pre_evidence={
            "registry_root": str(REPO_ROOT / "validation"),
            "workspace": str(project),
            "shadow_root": str(tmp_root / "shadow"),
            "exclude": [".git/**", ".policy/**", "__pycache__/**"],
            "validators": ["py.source", "py.ast", "py.docstring"],
            "timeout_ms": 30000,
        },
    )
    return project, config


def payload(project: Path) -> dict:
    return dsh_event(
        "pre-tool-use-write-allow.json",
        cwd=str(project),
        tool_input={"file_path": TARGET, "content": UNDOCUMENTED},
    )


def records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def phase2(path: Path) -> list[dict]:
    return [item for item in records(path) if "audit_schema_version" in item]


def decision_record(path: Path) -> dict:
    found = [item for item in phase2(path) if "decision" in item]
    assert found, "审计里没有判定记录"
    return found[0]


def record_with(path: Path, reason_code: str) -> dict:
    """没有算出 decision 的记录（context_error / evidence_unavailable …）也要能按原因码取到。

    它们**没有** `decision` 键——这正是 P1 那条口径：没判定的记录不许伪造判定清单。
    """

    found = [item for item in phase2(path) if item.get("reason_code") == reason_code]
    assert found, "审计里没有 reason_code=" + reason_code + " 的记录"
    return found[0]


def test_reading_context_names_the_evidence_tree_and_the_registry(tmp_root: Path) -> None:
    project, config = evidence_config(tmp_root)
    audit = tmp_root / "audit.jsonl"

    outcome = run_hook(payload(project), config_path=config, audit_path=audit)
    assert outcome.exit_code == EXIT_BLOCK  # DOC-900 命中：取证真的发生了

    record = decision_record(audit)
    assert record["audit_schema_version"] == AUDIT_SCHEMA_VERSION == "1.3"
    assert record["pre_evidence_status"] == "collected"

    context = record["reading_context"]
    assert context["source"] == "hook"
    # Q1：树**引用**本记录取证树的那组值（不另算一遍指纹）
    assert context["tree"] == {
        "status": "available",
        "scope": record["pre_evidence"]["tree"]["scope"],
        "digest": record["pre_evidence"]["tree"]["tree_digest"],
    }
    # Q3：注册表版本与 policy.check --json 的 evidence.configs.registry **同源**
    registry = context["declarations"]["registry"]
    assert registry["path"] == "validation/validators.yaml"
    assert registry["digest"] == record["pre_evidence"]["registry"]["digest"]
    assert registry["digest"] == config_digest(REPO_ROOT / "validation" / "validators.yaml")
    assert record["pre_evidence"]["registry"]["declared_in"] == "pre_evidence.registry_root"
    # adapter 配置的摘要：这条记录读的是哪一份声明
    adapter_config = context["declarations"]["adapter_config"]
    assert adapter_config["status"] == "available"
    assert adapter_config["digest"] == config_digest(config)
    # 沙箱不探测：不知道就写不知道（不是"没有沙箱"）
    assert context["host"]["sandbox"] == "unknown"
    # run 是有条件的：Hook 审计记录保留它（只有 policy.check --json 不带）
    assert context["run"]["id"] and context["run"]["started_at"]

    # 脱敏：整条记录里不出现本机绝对路径
    text = json.dumps(record, ensure_ascii=False)
    assert str(tmp_root) not in text
    assert str(project) not in text
    assert str(config) not in text


def test_a_declared_but_uncollected_evidence_marks_the_tree_unavailable(tmp_root: Path) -> None:
    """取证失败时不是"没有树"，而是"树读不到"——三态必须分得开（not_applicable ≠ unavailable）。"""

    project, config = evidence_config(tmp_root)
    audit = tmp_root / "audit.jsonl"
    # old_string 在目标文件里不唯一 / 不存在 → 取证失败关闭（evidence_unavailable）
    broken = dsh_event(
        "pre-tool-use-edit-allow.json",
        cwd=str(project),
        tool_input={
            "file_path": "src/shop/order_controller.py",
            "old_string": "这段文本在文件里不存在",
            "new_string": "x",
            "replace_all": False,
        },
    )
    outcome = run_hook(broken, config_path=config, audit_path=audit)
    assert outcome.exit_code == EXIT_BLOCK
    record = record_with(audit, "evidence_unavailable")
    assert "decision" not in record  # 没算出判定：不许伪造
    assert record["pre_evidence_status"] == "unavailable"
    context = record["reading_context"]
    assert context["tree"]["status"] == "unavailable"
    assert context["tree"]["reason"]
    assert context["declarations"]["registry"]["status"] == "unavailable"


def test_reading_context_never_recomputes_a_whole_tree_digest(tmp_root: Path, monkeypatch) -> None:
    """每次 Hook 调用不许计算整棵树的摘要：把那个函数换成"一调就炸"，调用必须照常成功。"""

    def explode(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Hook 路径不得计算整棵树的摘要（21 号 §2.2 的延迟硬约束）")

    monkeypatch.setattr(reading, "workspace_tree_digest", explode)
    project, config = evidence_config(tmp_root)
    audit = tmp_root / "audit.jsonl"

    outcome = run_hook(payload(project), config_path=config, audit_path=audit)
    assert outcome.exit_code == EXIT_BLOCK
    assert decision_record(audit)["reading_context"]["tree"]["status"] == "available"


def test_no_evidence_declaration_means_no_tree_to_reference(tmp_root: Path) -> None:
    """没声明取证 = 这条路径上**没有**取证树：not_applicable，不是 unavailable，也不是编一棵。"""

    project = copy_validator_project(tmp_root)
    config = write_dsh_config(
        tmp_root / "config" / "plain.yaml",
        project_root=project,
        rules=REPO_ROOT / "policies",
        rules_root=str(REPO_ROOT),
    )
    audit = tmp_root / "audit.jsonl"
    run_hook(payload(project), config_path=config, audit_path=audit)

    record = decision_record(audit)
    assert record["pre_evidence_status"] == "not_declared"
    context = record["reading_context"]
    assert context["tree"] == {"status": "not_applicable"}
    assert context["declarations"]["registry"] == {"status": "not_applicable"}
    assert context["declarations"]["adapter_config"]["status"] == "available"
    assert "registry" not in record.get("pre_evidence", {})


def test_a_1_2_record_is_not_rewritten_and_a_mixed_chain_still_verifies(tmp_root: Path) -> None:
    """兼容：1.2 记录不回写；1.2 与 1.3 混排的链必须仍然通过审计链校验。"""

    project, config = evidence_config(tmp_root)
    audit = tmp_root / "audit.jsonl"

    # 先跑一次，拿到一条真实记录；再按**旧协议的键集合**还原成 1.2 形态的既有记录。
    run_hook(payload(project), config_path=config, audit_path=audit)
    first = phase2(audit)[0]
    legacy = {
        key: value
        for key, value in first.items()
        if key not in {"reading_context", "pre_evidence_status", "pre_evidence"}
    }
    legacy["audit_schema_version"] = "1.2"
    if isinstance(legacy.get("pre_evidence"), dict):
        legacy["pre_evidence"].pop("registry", None)
    legacy_line = json.dumps(legacy, ensure_ascii=False, sort_keys=True)
    generated = audit.read_text(encoding="utf-8").splitlines()
    audit.write_text(legacy_line + chr(10), encoding="utf-8", newline=chr(10))
    before_bytes = audit.read_bytes()

    payload_b = dsh_event(
        "pre-tool-use-write-allow.json",
        cwd=str(project),
        tool_use_id="call-after-legacy",
        tool_input={"file_path": "src/shop/cart_service.py", "content": UNDOCUMENTED + chr(10)},
    )
    run_hook(payload_b, config_path=config, audit_path=audit)

    lines = audit.read_text(encoding="utf-8").splitlines()
    # ① 已有记录一个字节都不改写（前缀逐字节相同）
    assert audit.read_bytes().startswith(before_bytes)
    assert lines[0] == legacy_line
    assert json.loads(lines[0])["audit_schema_version"] == "1.2"
    # ② 新记录是 1.3，且带 reading_context
    appended = [json.loads(line) for line in lines[1:] if "audit_schema_version" in line]
    assert appended and all(item["audit_schema_version"] == "1.3" for item in appended)
    assert all("reading_context" in item for item in appended)
    # ③ 混排之后审计链校验仍然通过；1.2/1.3 两种外来行都被计数（不静默收编）
    sink = FileAuditSink(audit)
    assert sink.verify() == ()
    assert sink.foreign_records() == len(lines) - len(sink.chain_records())
    assert len(generated) >= 1  # 反真空：第一段确实产生过记录

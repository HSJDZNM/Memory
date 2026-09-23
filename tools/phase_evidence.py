"""生成阶段验收证据（对应 docs/project/engineering-policy-platform/testing/test-strategy.md 的证据格式）。

用法：

    python tools/phase_evidence.py                       # 写到 .tmp/artifacts/phase-<当前阶段>-evidence.json
                                                         # （文件名跟随 CURRENT_PHASE，不要在这里写死某个阶段）
    python tools/phase_evidence.py --out .tmp/artifacts/custom.json

本脚本只记录可重放的元数据：版本、规则集哈希、测试命令与结果、性能基线，
不记录密钥、完整 Prompt、隐私数据或未脱敏的工具参数。
证据写在 .tmp/ 下，可随时删除并由本脚本重建。
"""
from __future__ import annotations

import argparse
import datetime as clock
import hashlib
import json
import os
import platform
import subprocess
import sys
import xml.etree.ElementTree as elementtree
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
TOOLS_DIR = REPO_ROOT / "tools"
for directory in (SRC_DIR, TOOLS_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

CURRENT_PHASE = 8
SUITES = ("tests/unit", "tests/contract", "tests/integration", "tests/security")
POLICIES = ("policies",)
ARTIFACT_DIR = REPO_ROOT / ".tmp" / "artifacts"
SANDBOX_RESULT = ARTIFACT_DIR / "phase-2-sandbox-result.json"
RETRIEVAL_BASELINE = ARTIFACT_DIR / "phase-3-retrieval-baseline.json"
ENFORCEMENT_RESULT = ARTIFACT_DIR / "phase-4-enforcement-result.json"
VALIDATOR_RESULT = ARTIFACT_DIR / "phase-5-validators-result.json"
AGENT_RESULT = ARTIFACT_DIR / "phase-6-agents-result.json"
API_RESULT = ARTIFACT_DIR / "phase-7-api-result.json"
ORCHESTRATION_RESULT = ARTIFACT_DIR / "phase-8-orchestration-result.json"


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return completed.stdout.strip()


def git_revision() -> str:
    """记录实现版本；工作区有未提交改动时加 -dirty，避免证据指向一个并不存在的提交。"""

    try:
        revision = _git("rev-parse", "HEAD")
        dirty = bool(_git("status", "--porcelain"))
    except OSError:
        return "unknown"
    if not revision:
        return "uncommitted"
    return revision + ("-dirty" if dirty else "")


def rule_set_identity() -> tuple[str, list[str]]:
    from policy.loader import load_rule_set

    rules = load_rule_set([REPO_ROOT / name for name in POLICIES], repo_root=REPO_ROOT)
    return rules.identity, list(rules.source_paths)


def decision_protocol() -> dict[str, object]:
    """决策协议的事实：只报载荷里真实存在的值，不从"当前阶段"推。

    这里曾经写成 "phase-" + CURRENT_PHASE，于是证据说 phase-5、载荷说 phase-1。
    policy_version 是协议世代名（与 schema_version 同进同退），平台阶段另有
    payload["phase"] 与 implementation_version 承担。
    """

    from policy.models import POLICY_VERSION, SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS

    return {
        "schema_version": SCHEMA_VERSION,
        "supported": sorted(SUPPORTED_SCHEMA_VERSIONS),
        "policy_version": POLICY_VERSION,
    }


def agent_adapter() -> dict[str, object]:
    """dsh Adapter 的契约事实：版本、Hook 协议、工具表与预算。

    只记录可重放的事实，不含任何事件内容或用户数据；
    真实沙箱闭环的结论单独由 tools/dsh_sandbox_loop.py 写到 phase-2-sandbox-result.json。
    """

    from adapters.dsh.adapter import (
        DSH_AGENT_ID,
        SUPPORTED_HOOK_EVENTS,
        TOOL_TABLE,
        ToolKind,
    )

    hooks_config = REPO_ROOT / "examples" / "dsh" / "hooks.json"
    hook_timeout: object = None
    if hooks_config.is_file():
        document = json.loads(hooks_config.read_text(encoding="utf-8"))
        for groups in document.get("hooks", {}).values():
            for group in groups:
                for entry in group.get("hooks", []):
                    if "adapters.dsh.hooks" in str(entry.get("command", "")):
                        hook_timeout = entry.get("timeout")

    governed = sorted(name for name, spec in TOOL_TABLE.items() if spec.kind is ToolKind.WRITE)
    return {
        "agent": DSH_AGENT_ID,
        "agent_version": "0.1.5-rc.1",
        "hook_bridge": "@deepseek-ai/dsh-hooks-claude-code",
        "hook_events": list(SUPPORTED_HOOK_EVENTS),
        "block_protocol": "exit 2（stderr 作为阻断理由）",
        "fail_open_exit_codes": "其他非 0 / 启动失败 / 超时：dsh 视为非阻断失败，工具照常执行",
        "dsh_hook_timeout_seconds": hook_timeout,
        "internal_budget_ms": 5000,
        "governed_tools": governed,
        "tool_table_size": len(TOOL_TABLE),
        "event_fixtures": sorted(
            item.name for item in (REPO_ROOT / "tests" / "fixtures" / "agent_events" / "dsh").glob("*.json")
        ),
    }


def _hashes_compared(payload: dict[str, object], scenario_name: str, *, same: bool) -> bool | None:
    """两个哈希**都拿到**才给判定；缺任意一个就返回 None。

    "dsh 不可用"那条跳过路径只写 `{"phase":2,"result":"skipped"}`，没有场景对象，
    两个哈希都是 None——而 `None == None` 是 True。直接比较会让产物写出
    `block_file_unchanged: true`：读它的机器据此认为"阻止场景的文件确实没被改动 =
    拦截生效"，可实际上一个 Hook 都没跑过。**"没验证"和"验证通过"不能共用一个值。**
    """

    # spawn 被沙箱拒绝时，两个哈希**都存在且相等**——"文件没被改动"是真的，
    # 但原因是"一个 Hook 都没跑过"，不是"拦截生效"。这种"因为什么都没发生所以看起来正确"
    # 的字段是最危险的假安慰，必须报"未验证"。
    if isinstance(payload, dict) and payload.get("sandbox_blocked_spawn") is True:
        return None

    scenario = (payload.get(scenario_name) or {}) if isinstance(payload, dict) else {}
    before = scenario.get("file_sha256_before")
    after = scenario.get("file_sha256_after")
    if before is None or after is None:
        return None
    return (before == after) if same else (before != after)


def sandbox_loop() -> dict[str, object]:
    """真实 dsh 沙箱闭环的结论（由 tools/dsh_sandbox_loop.py 生成）。"""

    if not SANDBOX_RESULT.is_file():
        return {"result": "not-run", "hint": "python tools/dsh_sandbox_loop.py"}
    payload = json.loads(SANDBOX_RESULT.read_text(encoding="utf-8"))
    return {
        "result": payload.get("result"),
        # 失败不是"被规则阻断"：审计为空说明 Hook 根本没被执行（嵌套进程启动被外层环境拦住）。
        # result=skipped 表示本机确认了"spawn 被沙箱拒绝"，并给出了在不受限环境里的复现命令。
        "diagnosis": payload.get("diagnosis"),
        "reason": payload.get("reason"),
        "sandbox_blocked_spawn": payload.get("sandbox_blocked_spawn"),
        # "环境跳过"必须能被消费者判定：顶层 result 仍是 skipped（取值集合不变），
        # 这个字段才是"没跑过"与"跑过但通过"的分界。
        "environment_skipped": payload.get("environment_skipped"),
        "reproduce": payload.get("reproduce"),
        "agent_version": payload.get("agent_version"),
        "block_passed": (payload.get("block_scenario") or {}).get("passed"),
        "allow_passed": (payload.get("allow_scenario") or {}).get("passed"),
        "block_file_unchanged": _hashes_compared(payload, "block_scenario", same=True),
        "allow_changed_once": _hashes_compared(payload, "allow_scenario", same=False),
        "block_matched_rules": ((payload.get("block_scenario") or {}).get("audit") or {}).get(
            "matched_rules"
        ),
        "timestamp": payload.get("timestamp"),
    }


def retrieval() -> dict[str, object]:
    """Phase 3 检索层的可重放事实：语料清单、许可、索引规模与查询策略。

    只记录元数据：数据集名、许可、条数、哈希与预算参数，不含任何文档正文或用户查询。
    """

    from retrieval.corpus import load_corpus
    from retrieval.indexer import DEFAULT_CORPUS_PATH
    from retrieval.models import CHUNKER_VERSION, INDEX_SCHEMA_VERSION
    from retrieval.store import DEFAULT_DB_PATH, ChunkStore

    loaded = load_corpus(REPO_ROOT / DEFAULT_CORPUS_PATH, repo_root=REPO_ROOT)
    payload: dict[str, object] = {
        "corpus": loaded.corpus_path,
        "corpus_version": loaded.manifest.version,
        "corpus_input_hash": loaded.input_hash,
        "chunker_version": CHUNKER_VERSION,
        "index_schema_version": INDEX_SCHEMA_VERSION,
        "entry_count": len(loaded.entries),
        "datasets": [
            {
                "name": dataset.name,
                "mirror": dataset.mirror,
                "license": dataset.license,
                "tier": dataset.tier.value,
                "visibility": dataset.visibility.value,
                "entries": len(dataset.entries),
            }
            for dataset in loaded.manifest.datasets
        ],
        "verification_ok": loaded.verification.ok,
        "integrity_issues": sorted({issue.kind for issue in loaded.verification.issues}),
        "query_policy": json.loads(loaded.policy.model_dump_json()),
        "quarantine_entries": len(loaded.manifest.quarantine),
        "rule_source_entries": len(loaded.manifest.rule_sources),
    }
    database = REPO_ROOT / DEFAULT_DB_PATH
    if not database.is_file():
        payload["index"] = {"status": "not-built", "hint": "python -m retrieval.cli index"}
        return payload
    try:
        store = ChunkStore(database, create=False)
    except Exception as error:  # noqa: BLE001 - 证据脚本必须把失败如实写进证据
        payload["index"] = {"status": "unusable", "error": f"{type(error).__name__}: {error}"}
        return payload
    try:
        stats = store.stats()
        payload["index"] = {
            "status": "built",
            "path": DEFAULT_DB_PATH,
            "documents": stats.documents,
            "chunks": stats.chunks,
            "quarantined": stats.quarantined,
            "truncated_chunks": stats.truncated_chunks,
            "oversized_chunks": stats.oversized_chunks,
            "embedded_chunks": stats.embedded_chunks,
            "generation": stats.generation,
            "index_version": stats.index_version,
            "datasets": {name: count for name, count in stats.datasets},
            "last_run_status": None if stats.last_run is None else stats.last_run.status.value,
        }
    finally:
        store.close()
    return payload


def retrieval_eval_baseline() -> dict[str, object]:
    """固定评测集基线的结论（由 tools/retrieval_eval.py 生成）。"""

    if not RETRIEVAL_BASELINE.is_file():
        return {"result": "not-run", "hint": "python tools/retrieval_eval.py --method both"}
    payload = json.loads(RETRIEVAL_BASELINE.read_text(encoding="utf-8"))
    return {
        "result": payload.get("result"),
        "eval_set": payload.get("eval_set"),
        "eval_set_version": payload.get("eval_set_version"),
        "thresholds": payload.get("thresholds"),
        "gated_methods": payload.get("gated_methods"),
        "methods": [
            {
                "method": item.get("method"),
                "hit_at_k": item.get("hit_rate"),
                "support_at_k": item.get("support_rate"),
                "precision_at_k": item.get("mean_precision_at_k"),
                "recall_at_k": item.get("mean_recall_at_k"),
                "source_completeness": item.get("source_completeness"),
                "order_stable": item.get("order_stable"),
                "passed": item.get("passed"),
            }
            for item in payload.get("methods", [])
        ],
        "comparison": payload.get("comparison"),
        "context_probe": payload.get("context_probe"),
        "timestamp": payload.get("timestamp"),
    }


def enforcement() -> dict[str, object]:
    """Phase 4 受控执行的可重放事实：注册表、已审核哈希、协议版本与闭环结论。

    只记录元数据：工具 ID、风险级别、权限、参数名、事后验证器、哈希与策略参数，
    不记录任何一次具体的工具参数、文件内容或审批内容。
    """

    from enforcement.audit import DEFAULT_MAX_RECORD_BYTES
    from enforcement.models import (
        ENFORCEMENT_SCHEMA_VERSION,
        HIGH_RISK_LEVELS,
        SUPPORTED_POST_CHECKS,
    )
    from enforcement.registry import (
        APPROVED_SCHEMA_VERSION,
        DEFAULT_APPROVED_PATH,
        DEFAULT_REGISTRY_PATH,
        load_registry,
    )

    loaded = load_registry(DEFAULT_REGISTRY_PATH, approved_path=DEFAULT_APPROVED_PATH)
    registry = loaded.registry
    payload: dict[str, object] = {
        "registry": DEFAULT_REGISTRY_PATH,
        "approved": DEFAULT_APPROVED_PATH,
        "registry_schema_version": "1.0",
        "approved_schema_version": APPROVED_SCHEMA_VERSION,
        "enforcement_schema_version": ENFORCEMENT_SCHEMA_VERSION,
        "registry_version": registry.version,
        "registry_digest": registry.identity,
        "reviewed_by": registry.approved_metadata.get("reviewed_by"),
        "approved_at": registry.approved_metadata.get("approved_at"),
        "grant_ttl_seconds": registry.grant_ttl_seconds,
        "max_grant_ttl_seconds": registry.max_grant_ttl_seconds,
        "default_timeout_ms": registry.default_timeout_ms,
        "audit_max_record_bytes": DEFAULT_MAX_RECORD_BYTES,
        "supported_post_checks": list(SUPPORTED_POST_CHECKS),
        "high_risk_levels": sorted(item.value for item in HIGH_RISK_LEVELS),
        "roles": {role: list(perms) for role, perms in sorted(registry.roles.items())},
        "unapproved_tools": [
            spec.id for spec in registry.tools if not registry.is_approved(spec)
        ],
        "tools": [
            {
                "id": spec.id,
                "agent": spec.agent,
                "tool_name": spec.tool_name,
                "risk": spec.risk.value,
                "effect": spec.effect.value,
                "driver": spec.driver.value,
                "approval": spec.approval.value,
                "permissions": list(spec.required_permissions),
                "post_checks": list(spec.post_checks),
                "rollback": spec.rollback.value,
                "params": [param.name for param in spec.parameters],
                "allowed_command_patterns": len(spec.allowed_commands),
                "rate_limit": None if spec.rate_limit is None else json.loads(spec.rate_limit.model_dump_json()),
                "schema_hash": spec.schema_hash,
                "approved": registry.is_approved(spec),
            }
            for spec in registry.tools
        ],
    }
    if ENFORCEMENT_RESULT.is_file():
        loop = json.loads(ENFORCEMENT_RESULT.read_text(encoding="utf-8"))
        payload["closed_loop"] = {
            "result": loop.get("result"),
            "workspace": loop.get("workspace"),
            "audit": loop.get("audit"),
            "scenarios": [
                {
                    "name": item.get("name"),
                    "passed": item.get("passed"),
                    "facts": item.get("facts"),
                }
                for item in loop.get("scenarios", [])
            ],
        }
    else:
        payload["closed_loop"] = {
            "result": "not-run",
            "hint": "python tools/enforcement_loop.py",
        }
    return payload


def validators() -> dict[str, object]:
    """Phase 5 代码验证器的可重放事实：注册表、项目档案、规则覆盖与闭环结论。

    只记录元数据：验证器 ID / 版本 / 阶段 / 服务的 checker、外部工具的版本区间与配置，
    以及"哪条规则由哪个验证器提供证据"。不记录任何被验证文件的内容。
    """

    from policy.evidence import EVIDENCE_SCHEMA_VERSION
    from policy.loader import load_rule_set
    from validators.pipeline import KNOWN_VALIDATOR_IDS, PIPELINE_SCHEMA_VERSION
    from validators.registry import config_digest, load_config

    config = load_config(root=REPO_ROOT)
    registry = config.registry
    rules = load_rule_set([REPO_ROOT / "policies"], repo_root=REPO_ROOT)
    checkers = registry.checkers_for_language("python")

    payload: dict[str, object] = {
        "registry": config.registry_path.relative_to(REPO_ROOT).as_posix(),
        "project": config.project_path.relative_to(REPO_ROOT).as_posix(),
        "test_layout": config.layout_path.relative_to(REPO_ROOT).as_posix(),
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "pipeline_schema_version": PIPELINE_SCHEMA_VERSION,
        "config_digests": {
            "registry": config_digest(config.registry_path),
            "project": config_digest(config.project_path),
            "test_layout": config_digest(config.layout_path),
        },
        "stages": list(registry.stages),
        "rule_packs": [
            {"id": pack.id, "language": pack.language, "validators": list(pack.validators)}
            for pack in registry.rule_packs
        ],
        "checker_owners": {key: list(value) for key, value in sorted(checkers.items())},
        "implemented": sorted(KNOWN_VALIDATOR_IDS),
        "validators": [
            {
                "id": spec.id,
                "version": spec.version,
                "kind": spec.kind.value,
                "stage": spec.stage,
                "checkers": list(spec.checkers),
                "facts": list(spec.facts),
                "requires": list(spec.requires),
                "critical": spec.critical,
                "tool": None
                if spec.tool is None
                else {
                    "command": list(spec.tool.command[:1]),
                    "version_requirement": spec.tool.version_requirement,
                    "config": spec.tool.config,
                    "argv_length": len(spec.tool.argv),
                },
            }
            for spec in registry.validators
        ],
        "rules": [
            {
                "rule": rule.canonical_id,
                "checker": rule.enforcement.checker,
                "severity": rule.severity.value,
                "validators": list(checkers.get(rule.enforcement.checker or "", ())),
            }
            for rule in rules.rules
        ],
        "components": [item.name for item in config.project.components],
        "test_levels": [item.level for item in config.layout.escalation],
    }

    if VALIDATOR_RESULT.is_file():
        conclusion = json.loads(VALIDATOR_RESULT.read_text(encoding="utf-8"))
        payload["closed_loop"] = {
            "result": conclusion.get("result"),
            "workspace": conclusion.get("workspace"),
            "scenarios": [
                {
                    "name": item.get("name"),
                    "passed": item.get("passed"),
                    # 工具不可用时场景仍算 passed（闭环不该在没装 Ruff 的机器上变红），
                    # 但 verified=False 把它标成"这条没验证到"，不是"验证通过"。
                    "verified": item.get("verified"),
                    "detail": item.get("detail"),
                }
                for item in conclusion.get("scenarios", [])
            ],
        }
    else:
        payload["closed_loop"] = {
            "result": "not-run",
            "hint": "python tools/validator_loop.py",
        }
    return payload


def agent_adapters() -> dict[str, object]:
    """Phase 6 多 Agent 适配层的可重放事实：支持矩阵、协议版本与闭环结论。

    只记录元数据：agent id、产品版本、协议版本、能力上限、工具数量与 fixture 名字，
    不记录任何一次具体事件、参数或源码内容。
    """

    from adapters.base import EnforcementLevel
    from adapters.loader import load_registry_from_repo

    registry = load_registry_from_repo(REPO_ROOT)
    listing = registry.as_list()
    payload: dict[str, object] = {
        "approved": None if listing.approved_path is None else listing.approved_path,
        "reviewed_by": listing.reviewed_by,
        "approved_at": listing.approved_at,
        "counts": {
            "full": sum(
                1
                for item in listing.descriptors
                if item.enforcement is EnforcementLevel.FULL
            ),
            "read_only": sum(
                1
                for item in listing.descriptors
                if item.enforcement is EnforcementLevel.READ_ONLY
            ),
            "unsupported": sum(
                1
                for item in listing.descriptors
                if item.enforcement is EnforcementLevel.UNSUPPORTED
            ),
        },
        "adapters": [
            {
                "agent_id": item.agent_id,
                "agent_version": item.agent_version,
                "protocol": item.protocol,
                "protocol_version": item.protocol_version,
                "enforcement": item.enforcement.value,
                "requested_enforcement": (
                    None
                    if item.requested_enforcement is None
                    else item.requested_enforcement.value
                ),
                "downgraded": item.downgraded,
                "blocking": item.blocking.value,
                "approval": item.approval.value,
                "event_types": list(item.event_types),
                "tools": len(item.tools),
                "fixtures": list(item.fixtures),
                "approved": item.approved,
                "manifest_digest": item.manifest_digest,
                "ceiling_reasons": list(item.ceiling_reasons),
            }
            for item in listing.descriptors
        ],
    }
    if AGENT_RESULT.is_file():
        loop = json.loads(AGENT_RESULT.read_text(encoding="utf-8"))
        payload["closed_loop"] = {
            "result": loop.get("result"),
            "workspace": loop.get("workspace"),
            "conformance": loop.get("conformance"),
            "scenarios": [
                {"name": item.get("name"), "passed": item.get("passed")}
                for item in loop.get("scenarios", [])
            ],
        }
    else:
        payload["closed_loop"] = {
            "result": "not-run",
            "hint": "python tools/agent_loop.py",
        }
    return payload


def policy_api() -> dict[str, object]:
    """Phase 7 服务化层的可重放事实：契约版本、租户与客户端、自检与闭环结论。

    只记录元数据：版本、租户/客户端**数量**、契约哈希、自检结论与闭环场景名，
    不记录任何一次请求的载荷、令牌或决策内容。
    """

    from policy.models import POLICY_VERSION, SCHEMA_VERSION
    from policy_api import API_SCHEMA_VERSION
    from policy_api.cli import default_config_path
    from policy_api.config import load_api_config
    from policy_api.contract import self_check

    config_path = default_config_path(REPO_ROOT)
    payload: dict[str, object] = {"config": config_path.name}
    if not config_path.is_file():
        payload["status"] = "config-missing"
        return payload
    try:
        config = load_api_config(config_path, root=REPO_ROOT)
    except Exception as error:  # noqa: BLE001 - 配置不合法本身就是证据的一部分
        payload["status"] = "config-invalid"
        payload["detail"] = type(error).__name__
        return payload

    snapshot = REPO_ROOT / "api" / "openapi.json"
    payload.update(
        {
            "status": "ok",
            "api_schema_version": API_SCHEMA_VERSION,
            "decision_schema_version": SCHEMA_VERSION,
            "policy_generation": POLICY_VERSION,
            "service_name": config.service_name,
            "deployment": config.deployment,
            "budgets": {
                "evaluate_ms": config.budgets.evaluate_ms,
                "retrieve_ms": config.budgets.retrieve_ms,
                "validate_ms": config.budgets.validate_ms,
            },
            "limits": {
                "max_request_bytes": config.limits.max_request_bytes,
                "max_response_bytes": config.limits.max_response_bytes,
                "max_concurrency": config.limits.max_concurrency,
            },
            "rate_limit": None
            if config.rate_limit is None
            else {
                "capacity": config.rate_limit.capacity,
                "refill_per_second": config.rate_limit.refill_per_second,
            },
            "tenants": [
                {
                    "tenant_id": item.tenant_id,
                    "rules": list(item.rules),
                    "retrieval": item.retrieval is not None and item.retrieval.enabled,
                    "validators": item.validators is not None,
                }
                for item in config.tenants
            ],
            "clients": len(config.clients),
            "openapi_snapshot": {
                "path": snapshot.relative_to(REPO_ROOT).as_posix(),
                "sha256": (
                    "sha256:" + hashlib.sha256(snapshot.read_bytes()).hexdigest()
                    if snapshot.is_file()
                    else None
                ),
            },
        }
    )
    try:
        from policy_api.runtime import ApiRuntime
        from policy_api.testing import runtime_from_config

        runtime: ApiRuntime = runtime_from_config(config, root=REPO_ROOT)
        report = self_check(runtime)
        payload["self_check"] = {
            "ok": report["ok"],
            "checks": [
                {"check": item["check"], "ok": item["ok"]} for item in report["checks"]
            ],
            "readiness": report["readiness"].get("state"),
        }
    except Exception as error:  # noqa: BLE001 - 装配失败也必须被记下来
        payload["self_check"] = {"ok": False, "detail": type(error).__name__}

    if API_RESULT.is_file():
        loop = json.loads(API_RESULT.read_text(encoding="utf-8"))
        payload["closed_loop"] = {
            "result": loop.get("result"),
            "workspace": loop.get("workspace"),
            "readiness": loop.get("readiness"),
            "scenarios": [
                {"name": item.get("name"), "passed": item.get("passed")}
                for item in loop.get("scenarios", [])
            ],
        }
    else:
        payload["closed_loop"] = {"result": "not-run", "hint": "python tools/api_loop.py"}
    return payload


def orchestration() -> dict[str, object]:
    """Phase 8 编排层的可重放事实：协议版本、引擎与图结构、闭环结论。

    只记录元数据：协议版本、引擎名、LangGraph 版本、节点/边/分支名与闭环场景名，
    不记录任何一次运行的载荷、提示词、工具参数、令牌或绝对路径
    （闭环里的工作区按仓库相对路径记录）。包不可导入时只报 available=False，
    证据步骤必须照常产出，不替它编造结论。
    """

    try:
        from orchestration.checkpoint import (
            CHECKPOINT_SCHEMA_VERSION,
            SUPPORTED_CHECKPOINT_SCHEMA_VERSIONS,
        )
        from orchestration.engines import ReferenceEngine
        from orchestration.graph import DEFAULT_SPEC
        from orchestration.langgraph_engine import (
            MIN_LANGGRAPH_VERSION,
            LangGraphEngine,
            langgraph_version,
        )
        from orchestration.models import (
            STATE_SCHEMA_VERSION,
            SUPPORTED_STATE_SCHEMA_VERSIONS,
            NodeId,
        )
    except ImportError:
        return {"available": False}

    version = langgraph_version()
    payload: dict[str, object] = {
        "available": True,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "supported_state_schema_versions": sorted(SUPPORTED_STATE_SCHEMA_VERSIONS),
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "supported_checkpoint_schema_versions": sorted(SUPPORTED_CHECKPOINT_SCHEMA_VERSIONS),
        # 引擎名取自实现本身（class 属性），不在这里另写一份清单。
        "engines": sorted({ReferenceEngine.name, LangGraphEngine.name}),
        "langgraph": {
            "installed": version is not None,
            "version": version,
            "min_version": MIN_LANGGRAPH_VERSION,
        },
        # 图结构以 data 为准：节点来自 NodeId，入口/边/分支来自 DEFAULT_SPEC。
        "graph": {
            "entry": DEFAULT_SPEC.entry,
            "nodes": [node.value for node in NodeId],
            "edges": [f"{edge.source}->{edge.target}" for edge in DEFAULT_SPEC.edges],
            "routers": sorted(router.name for router in DEFAULT_SPEC.routers),
        },
    }
    if ORCHESTRATION_RESULT.is_file():
        loop = json.loads(ORCHESTRATION_RESULT.read_text(encoding="utf-8"))
        payload["closed_loop"] = {
            "result": loop.get("result"),
            "workspace": loop.get("workspace"),
            "scenarios": [
                {"name": item.get("name"), "passed": item.get("passed")}
                for item in loop.get("scenarios", [])
            ],
        }
    else:
        payload["closed_loop"] = {
            "result": "not-run",
            "hint": "python tools/orchestration_loop.py",
        }
    return payload


def performance_baseline() -> dict[str, object]:
    """Phase 1 的匹配性能基线：固定种子、只记录不优化。"""

    import policy_bench

    return policy_bench.run_baseline()


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _cases_from_report(report: Path) -> tuple[int, int]:
    if not report.is_file():
        return 0, 0
    root = elementtree.parse(report).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return 0, 0
    cases = sum(int(suite.get("tests", "0")) for suite in suites)
    failures = sum(
        int(suite.get("failures", "0")) + int(suite.get("errors", "0")) for suite in suites
    )
    return cases, failures


def run_suite(path: str) -> dict[str, object]:
    report = ARTIFACT_DIR / (path.replace("/", "-") + "-report.xml")
    report.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        path,
        "-q",
        "--no-header",
        "--junit-xml",
        str(report),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_environment(),
        check=False,
    )
    cases, failures = _cases_from_report(report)
    return {
        "command": " ".join(["python", "-m", "pytest", path, "-q"]),
        "result": "pass" if completed.returncode == 0 else "fail",
        "exit_code": completed.returncode,
        "cases": cases,
        "failures": failures,
        "artifacts": [report.relative_to(REPO_ROOT).as_posix()],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成阶段验收证据")
    parser.add_argument(
        "--out",
        default=f".tmp/artifacts/phase-{CURRENT_PHASE}-evidence.json",
        help="输出路径（默认写在 .tmp/ 下，可随时删除）",
    )
    parser.add_argument(
        "--no-performance",
        action="store_true",
        help="跳过性能基线（基线需要额外数秒）",
    )
    args = parser.parse_args(argv)

    identity, sources = rule_set_identity()
    suites = {name: run_suite(name) for name in SUITES}
    cases = sum(int(item["cases"]) for item in suites.values())
    failures = sum(int(item["failures"]) for item in suites.values())
    artifacts = sorted(
        {name for item in suites.values() for name in item["artifacts"]}  # type: ignore[union-attr]
    )

    payload: dict[str, object] = {
        "phase": CURRENT_PHASE,
        "implementation_version": git_revision(),
        "rule_set_hash": identity,
        "rule_sources": sources,
        "decision_protocol": decision_protocol(),
        "agent_adapter": agent_adapter(),
        "sandbox_loop": sandbox_loop(),
        "retrieval": retrieval(),
        "retrieval_eval": retrieval_eval_baseline(),
        "enforcement": enforcement(),
        "validators": validators(),
        "agent_adapters": agent_adapters(),
        "policy_api": policy_api(),
        "orchestration": orchestration(),
        "test_suite": " + ".join(SUITES),
        "suites": suites,
        "result": "pass" if failures == 0 else "fail",
        "cases": cases,
        "failures": failures,
        "artifacts": artifacts,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": f"{platform.system()}-{platform.release()}",
            "executable": Path(sys.executable).name,
        },
        "timestamp": clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if not args.no_performance:
        payload["performance"] = performance_baseline()

    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    output = REPO_ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

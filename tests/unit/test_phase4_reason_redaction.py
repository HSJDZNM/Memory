"""P9（本轮新显现）：Phase 4 阻断理由进审计时必须与 stderr 同口径地脱敏。

07 轮 P8 的现场描述里有一句「path_out_of_scope，detail 为空」——理由其实在
`enforcement_detail` 里。本轮复核时发现同一栏还有第二个问题：**它没有走 sanitize**。
`path_out_of_scope` 的文案里带受控工作区的**绝对路径**（`repo_relative_path` 的
"路径不在仓库 <anchor> 之内"），于是审计的 `audit.jsonl` 里会落进本机路径，
而 AGENTS 第 16 条要求审计链里的绝对路径一律脱敏或转义。

为什么用 `workdir` 造这条：dsh 侧只对**文件路径字段**做范围解析，
`pwsh` 的工作目录是到 Phase 4 的参数规范化（`path_scope: workspace`）才判的——
这是"Phase 4 独立地判一次范围"的现场，也正是绝对路径漏进审计的那条路。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import dsh_event, write_dsh_config

from adapters.dsh.hooks import EXIT_BLOCK, run_hook

# 绝对路径的识别必须带**边界**：一个孤立的 "/" 会把普通仓库相对路径
# （src/shop/order_service.py）也判成绝对路径——那正是本仓库反复踩过的"仪器假阳"。
# 这里的形状与 enforcement.audit._ABS_PATH_RE 同口径：Windows 盘符 / UNC，
# 以及 POSIX 侧只认常见系统前缀（/home、/Users、/tmp ...）。
ABSOLUTE_PATH = re.compile(
    r"(?:[A-Za-z]:[\\\\/]|\\\\)[^\s'\"]+"
    r"|(?<![\w:/])/(?:home|root|etc|usr|var|opt|srv|tmp|mnt|Users)/[^\s'\"]*"
)

SCOPE_BLOCK_PAYLOAD = {
    "tool_name": "pwsh",
    "tool_input": {
        "command": "python -m pytest -q",
        "workdir": "C:/Windows/Temp",
        "description": "跑一次测试",
    },
}


def audit_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def decision_record(path: Path, reason_code: str) -> dict:
    for record in reversed(audit_records(path)):
        if record.get("reason_code") == reason_code:
            return record
    raise AssertionError(f"审计里没有 {reason_code} 记录：{path}")


def test_a_phase_4_scope_block_is_redacted_in_the_audit(tmp_root: Path) -> None:
    """Phase 4 的范围阻断：审计里的理由必须脱敏，且仍然说得出"改成什么形态就能过"。

    临时根用仓库自己的 `tmp_root` 夹具而不是 pytest 的 `tmp_path`：本机 ACL 会把
    `.tmp/tmp/pytest-of-*` 锁成读不了（N26），那不是被测对象的问题。
    """

    project = tmp_root / "demo-shop"
    (project / "src" / "shop").mkdir(parents=True)
    audit = tmp_root / "audit.jsonl"
    config_path = write_dsh_config(
        tmp_root / "config" / "dsh-adapter.yaml",
        project_root=project,
        rules=Path(__file__).resolve().parents[2] / "policies",
        audit_log=str(audit),
    )

    payload = dsh_event("pre-tool-use-pwsh-execute.json")
    payload.update(SCOPE_BLOCK_PAYLOAD)
    payload["cwd"] = str(project)
    payload["session_id"] = "p9-redaction"

    outcome = run_hook(payload, config_path=config_path, audit_path=audit)

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "path_out_of_scope"

    record = decision_record(audit, "path_out_of_scope")
    detail = str(record.get("enforcement_detail") or "")
    assert detail, "Phase 4 阻断的理由必须写进审计（enforcement_detail）"
    assert "可用的替代" in detail, "理由必须告诉调用方改成什么形态就能过"
    # 关键断言：脱敏之后不能出现任何绝对路径（含受控工作区自己的绝对路径）。
    found = ABSOLUTE_PATH.findall(detail)
    assert not found, f"审计里的 Phase 4 理由带了绝对路径：{found}"
    # stderr 与审计同一口径：两处要么都脱敏，要么都不脱敏。
    assert not ABSOLUTE_PATH.findall(outcome.stderr or ""), "stderr 的理由也必须脱敏"

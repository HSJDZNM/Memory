"""豁免到期检查（tools/exemption_expiry.py）的回归：规则只有一份实现，且只报告。

口径（2026-09-30 裁定 R16-4）：到期前 14 天提醒、过期标红，**都不计入任何门禁失败**——
所以这里最要紧的两条断言是"过期也返回 0"与"读不到不算通过、也不算失败，只说 unprovable"。
"""

from __future__ import annotations

import datetime as _datetime
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPIRED_SCOPE = """schema_version: "1"
scope:
  - id: probe-out-of-scope
    decision: out_of_scope
    kind: agent_runtime
    owner: host
    reason: 回归用例：一条已经过期的"不治理"声明。
    consequence: 只报告，不签发任何 allow / block。
    expires_at: "2026-01-01"
    renewals: []
"""

DUE_SCOPE = EXPIRED_SCOPE.replace('"2026-01-01"', '"2026-10-05"')


def _load():
    spec = importlib.util.spec_from_file_location(
        "exemption_expiry_under_test",
        REPO_ROOT / "tools" / "exemption_expiry.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # 标准配方：exec 之前登记，模块内 dataclass / 相对导入才成立
    spec.loader.exec_module(module)
    return module


def test_state_boundaries_are_the_only_implementation():
    module = _load()
    today = _datetime.date(2026, 9, 30)

    assert module.state_for("2026-10-15", today=today, lead_days=14)["state"] == "ok"
    assert module.state_for("2026-10-14", today=today, lead_days=14)["state"] == "due"
    assert module.state_for("2026-09-30", today=today, lead_days=14)["state"] == "due"
    expired = module.state_for("2026-09-29", today=today, lead_days=14)
    assert expired["state"] == "expired"
    assert expired["days"] == -1


def test_an_expired_exemption_is_red_but_never_fails(tmp_root, capsys):
    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(EXPIRED_SCOPE, encoding="utf-8")
    module = _load()

    assert module.run(["--scope", str(scope), "--today", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "RED" in out
    assert "已过期" in out
    assert "本步不阻断门禁" in out


def test_a_due_exemption_is_reminded(tmp_root, capsys):
    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(DUE_SCOPE, encoding="utf-8")
    module = _load()

    assert module.run(["--scope", str(scope), "--today", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "DUE" in out
    assert "5 天后到期" in out


def test_read_failure_is_unprovable_not_a_failure(tmp_root, capsys):
    module = _load()

    assert module.run(["--scope", str(tmp_root / "missing.yaml"), "--today", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "读不到" in out
    assert "unprovable=1" in out


def test_json_payload_separates_the_two_lists(tmp_root, capsys):
    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(EXPIRED_SCOPE, encoding="utf-8")
    module = _load()

    assert module.run(["--scope", str(scope), "--today", "2026-09-30", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "report-only"
    assert payload["counts"]["expired"] == 1
    assert payload["counts"]["unprovable"] == 0
    assert [item["id"] for item in payload["expired"]] == ["probe-out-of-scope"]
    # ci_local 的两条只报告豁免也必须在读数里（账本/到期检查自己也在豁免表里）；
    # --scope 覆盖时读数里的来源就是那个被覆盖的文件（相对仓库渲染，不在仓库内则原样）。
    sources = {item["source"] for item in payload["entries"]}
    assert "tools/ci_local.py" in sources
    assert any(source.endswith("wiring-scope.yaml") for source in sources)


def test_the_repository_declarations_are_readable_today(capsys):
    """仓库自身的读数：今天没有到期项，且退出码为 0（这一步永远不阻断）。"""

    module = _load()
    assert module.run(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["unprovable"] == 0
    assert payload["counts"]["declared"] >= 4

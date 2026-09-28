"""边界声明 adapters/wiring-scope.yaml 的加载与校验（方案 §3.5 的最小形态）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import REPO_ROOT

from provenance.wiring_scope import WiringScopeError, load_wiring_scope

pytestmark = pytest.mark.contract

IN_SCOPE = """  - id: governed-session-hook
    decision: in_scope
    kind: agent_runtime
    owner: platform
    reason: 受控会话由本仓库治理。
    consequence: 接不上就不放行。
"""

OUT_OF_SCOPE = """  - id: desktop-entry-points
    decision: out_of_scope
    kind: agent_runtime
    owner: host
    reason: 桌面通道是主机配置。
    consequence: 只报告，不签发 allow / block。
    expires_at: "2026-12-31"
    renewals: []
"""


def _document(*entries: str) -> str:
    return 'schema_version: "1"\nscope:\n' + "".join(entries)


def _write(tmp_root: Path, text: str) -> Path:
    path = tmp_root / "wiring-scope.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_repository_declaration_is_valid() -> None:
    scope = load_wiring_scope(REPO_ROOT / "adapters" / "wiring-scope.yaml")
    summary = scope.as_json()

    assert summary["schema_version"] == "1"
    assert summary["declared"] >= 2
    assert summary["by_decision"]["in_scope"] >= 1


def test_two_decisions_load_and_are_counted(tmp_root: Path) -> None:
    scope = load_wiring_scope(_write(tmp_root, _document(IN_SCOPE, OUT_OF_SCOPE)))

    assert scope.as_json()["by_decision"] == {
        "in_scope": 1,
        "out_of_scope": 1,
        "expected_absent": 0,
    }


def test_unknown_keys_are_rejected(tmp_root: Path) -> None:
    top_level = 'schema_version: "1"\nscope: []\nextra: 1\n'
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, top_level))

    entry = IN_SCOPE + "    secret: 1\n"
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, _document(entry)))


def test_unknown_decision_is_rejected(tmp_root: Path) -> None:
    entry = IN_SCOPE.replace("decision: in_scope", "decision: maybe")
    with pytest.raises(WiringScopeError) as failure:
        load_wiring_scope(_write(tmp_root, _document(entry)))

    assert "decision" in str(failure.value)


def test_empty_reason_is_rejected(tmp_root: Path) -> None:
    entry = IN_SCOPE.replace("reason: 受控会话由本仓库治理。", 'reason: "   "')
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, _document(entry)))


def test_in_scope_must_not_carry_an_expiry(tmp_root: Path) -> None:
    entry = IN_SCOPE + '    expires_at: "2026-12-31"\n'
    with pytest.raises(WiringScopeError) as failure:
        load_wiring_scope(_write(tmp_root, _document(entry)))

    assert "过期日" in str(failure.value)


def test_out_of_scope_must_carry_an_expiry(tmp_root: Path) -> None:
    entry = OUT_OF_SCOPE.replace('    expires_at: "2026-12-31"\n', "")
    with pytest.raises(WiringScopeError) as failure:
        load_wiring_scope(_write(tmp_root, _document(entry)))

    assert "expires_at" in str(failure.value)


def test_a_bad_date_is_rejected(tmp_root: Path) -> None:
    entry = OUT_OF_SCOPE.replace('"2026-12-31"', '"2026-13-99"')
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, _document(entry)))


def test_duplicate_ids_are_rejected(tmp_root: Path) -> None:
    with pytest.raises(WiringScopeError) as failure:
        load_wiring_scope(_write(tmp_root, _document(IN_SCOPE, IN_SCOPE)))

    assert "重复" in str(failure.value)


def test_unknown_schema_version_is_rejected(tmp_root: Path) -> None:
    text = _document(IN_SCOPE).replace('schema_version: "1"', 'schema_version: "2"')
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, text))


def test_missing_file_and_broken_yaml_are_rejected(tmp_root: Path) -> None:
    with pytest.raises(WiringScopeError):
        load_wiring_scope(tmp_root / "missing.yaml")
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, "scope: [unclosed\n"))

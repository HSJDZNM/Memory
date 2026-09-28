"""pre_evidence 段（G3 的动手前取证声明）的加载期契约。

声明即契约：未知字段、类型错误、缺必需项一律报错，不做"看不懂就当默认"的兜底。
没有这一项时，pre-execute 路径保持 Phase 2 的契约（没有证据提供者，证据类 checker 进
skipped_rules 并写明原因）——那是**显式记录**，不是静默放行。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.dsh.adapter import DshEventError, config_from_mapping

BLOCK = {
    "registry_root": "validation",
    "workspace": ".",
    "shadow_root": ".policy/pre-evidence",
    "exclude": [".git/**", ".policy/**"],
    "validators": ["py.ast", "tool.ruff"],
    "timeout_ms": 30000,
}


def _document(**overrides: object) -> dict:
    document: dict = {
        "project_root": ".",
        "rules": ["policies"],
        "pre_evidence": dict(BLOCK),
    }
    document.update(overrides)
    return document


def test_the_block_is_parsed_into_absolute_paths(tmp_root: Path) -> None:
    config = config_from_mapping(_document(), base_dir=tmp_root)
    assert config.pre_evidence is not None

    block = config.pre_evidence
    assert block.enabled is True
    assert block.registry_root == (tmp_root / "validation").resolve()
    assert block.workspace == tmp_root.resolve()
    assert block.shadow_root == (tmp_root / ".policy" / "pre-evidence").resolve()
    assert block.exclude == (".git/**", ".policy/**")
    assert block.validators == ("py.ast", "tool.ruff")
    assert block.timeout_ms == 30000


def test_defaults_are_derived_from_the_project_root(tmp_root: Path) -> None:
    config = config_from_mapping(
        _document(pre_evidence={"registry_root": "validation"}), base_dir=tmp_root
    )
    assert config.pre_evidence is not None

    block = config.pre_evidence
    assert block.workspace == tmp_root.resolve()
    assert block.shadow_root == (tmp_root / ".policy" / "pre-evidence").resolve()
    assert block.exclude == ()
    assert block.validators == ()
    assert block.timeout_ms == 60000


def test_an_absent_block_keeps_the_phase_2_contract(tmp_root: Path) -> None:
    document = _document()
    document.pop("pre_evidence")

    config = config_from_mapping(document, base_dir=tmp_root)
    assert config.pre_evidence is None


def test_enabled_false_is_recorded_instead_of_silently_dropped(tmp_root: Path) -> None:
    config = config_from_mapping(
        _document(pre_evidence={**BLOCK, "enabled": False}), base_dir=tmp_root
    )
    assert config.pre_evidence is not None
    assert config.pre_evidence.enabled is False


@pytest.mark.parametrize(
    "block",
    [
        {"registry_root": "validation", "unknown": 1},
        {"registry_root": "validation", "enabled": "yes"},
        {"registry_root": "validation", "timeout_ms": 0},
        {"registry_root": "validation", "timeout_ms": True},
        {"registry_root": "validation", "exclude": "git"},
        {"registry_root": "validation", "validators": [1]},
        {"workspace": "."},
    ],
)
def test_malformed_blocks_are_rejected(tmp_root: Path, block: dict) -> None:
    with pytest.raises(DshEventError):
        config_from_mapping(_document(pre_evidence=block), base_dir=tmp_root)

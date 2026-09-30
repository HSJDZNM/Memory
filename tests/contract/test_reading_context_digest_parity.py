"""reading_context 与验证器层的配置摘要必须逐字符相同（21 号 §2.1 的"同一个值来源"）。

两边各有一份实现，而且是**有意的**：provenance 只依赖标准库（它要能在"没有 src 也能跑"的
工具里被调用，例如 tools/dsh_sandbox_loop.py），不能 import 会拉进 policy / pydantic 的验证器层。
所以"同一个值来源"不能靠共享函数，只能靠**一条可执行的断言**：同一份文件、两条路径，
必须给出同一个字符串。谁把算法改得不一样，这条用例先红。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from provenance import reading_context as reading  # noqa: E402
from validators.registry import (  # noqa: E402
    DEFAULT_REGISTRY,
    DEFAULT_TEST_LAYOUT,
    config_digest,
)

pytestmark = pytest.mark.contract


def test_digest_matches_the_validator_layer_for_every_declaration():
    for relative in (DEFAULT_REGISTRY, DEFAULT_TEST_LAYOUT):
        path = REPO_ROOT / relative
        assert path.is_file(), relative
        assert reading.declaration_digest(path) == config_digest(path), relative


def test_missing_or_absent_input_is_none_on_both_sides():
    missing = REPO_ROOT / "validation" / "does-not-exist.yaml"
    assert reading.declaration_digest(missing) is None
    assert config_digest(missing) is None
    assert reading.declaration_digest(None) is None
    assert config_digest(None) is None

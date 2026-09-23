"""文档转规则操作台的静态边界契约。"""

from pathlib import Path

import pytest

from conftest import REPO_ROOT

pytestmark = pytest.mark.contract

APP_JS = REPO_ROOT / "docs" / "project" / "engineering-policy-platform" / "designs" / "console" / "assets" / "app.js"


def test_console_never_derives_policy_decision_from_severity() -> None:
    """浏览器只校验 severity 枚举；allow/block 必须来自 Policy API。"""

    source = APP_JS.read_text(encoding="utf-8")
    assert "最终 Decision 只由 Policy API 返回" in source
    assert "payload.severity === 'error'" not in source
    assert "payload.severity === 'critical'" not in source

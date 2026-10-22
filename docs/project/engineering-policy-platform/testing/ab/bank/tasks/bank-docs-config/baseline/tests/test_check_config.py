"""check_config 的静态契约测试：工具文件存在时检查公开面，不存在时跳过。

本文件是基线的一部分；M5 会把它改写为行为测试（import main 并调用）。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check_config.py"


def test_tool_surface_is_declared() -> None:
    """工具文件存在时：有 main()、--config 参数、__main__ 入口。"""
    if not TOOL.is_file():
        pytest.skip("tools/check_config.py 尚未实现")
    text = TOOL.read_text(encoding="utf-8")
    assert "def main(" in text
    assert "--config" in text
    assert '__name__ == "__main__"' in text

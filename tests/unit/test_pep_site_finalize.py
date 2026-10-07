"""pep_site._finalize：围栏代码块里的内容一个字符都不许被后处理改掉。

为什么需要：`_finalize` 里有三步排版动作（标题后补空行、丢掉 `---` / `* * *` 分隔线、
把连续空行压成一行），旧实现让它们跑遍整份正文——包括已经还原好的围栏代码块，
于是 Python 注释后面被插了空行、代码里的 `---` 被整行删掉、样例里的空行被压掉：
镜像里的代码与原文不一致，而 --verify 只看标题层级与链接，看不出来。

pep_site 依赖 bs4（可选依赖，本机没装），_finalize 是纯函数，这里只替掉导入期的名字。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NL = chr(10)
FENCE = chr(96) * 3

# 围栏里同时踩到三个坑：# 注释、--- 分隔线、连续空行
BODY = NL.join(
    [
        "# 文档标题",
        "",
        "## 小节",
        "",
        FENCE + "python",
        "# 这是代码里的注释，不是标题",
        "x = 1",
        "---",
        "* * *",
        "",
        "",
        "",
        "y = 2",
        FENCE,
        "",
        "## 下一节",
        "",
    ]
)


def _load_pep_site(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setitem(sys.modules, "bs4", types.ModuleType("bs4"))
    sys.modules["bs4"].BeautifulSoup = object  # type: ignore[attr-defined]
    spec = importlib.util.spec_from_file_location("pep_site_under_test", REPO_ROOT / "tools" / "pep_site.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fenced_region(text: str) -> str:
    "一条围栏（含围栏行）的原文"
    start = text.index(FENCE)
    end = text.index(FENCE, start + len(FENCE)) + len(FENCE)
    return text[start:end]


def test_fenced_code_is_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_pep_site(monkeypatch)
    out = module._finalize(BODY)

    assert _fenced_region(out) == _fenced_region(BODY)


def test_post_processing_still_applies_outside_fences(monkeypatch: pytest.MonkeyPatch) -> None:
    """围栏之外的排版动作不变：标题后补空行、分隔线丢掉、连续空行压成一行。"""

    module = _load_pep_site(monkeypatch)
    body = NL.join(["# 标题", "正文", "", "---", "", "", "", "结尾"])
    out = module._finalize(body)

    assert "---" not in out
    assert NL * 3 not in out
    # H1 -> H2，且标题后补了一个空行
    assert out.startswith("## 标题" + NL + NL + "正文")


def test_unclosed_fence_keeps_its_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """围栏没闭合时同样是"围栏内"：不补空行、不丢行、不压空行。"""

    module = _load_pep_site(monkeypatch)
    body = NL.join(["# 标题", "", FENCE, "# 注释", "---", "", "", "", "x = 1"])
    out = module._finalize(body)

    assert "# 注释" + NL + "---" + NL + NL + NL + NL + "x = 1" in out

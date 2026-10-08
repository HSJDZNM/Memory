"""dora_site.banner_intro：banner 的嵌套 <p> 只并在导语里一次。

来源：`docs/mirrors/dora-capabilities/manifest.json` 里 index.md 的 summary 曾是 **894 字符**、
同一段导语连写两遍（A B C A B C）。根因不是正文——正文只保留最内层段落，是对的——而是
catalog() 把 banner 里**每一个** <p> 的文本都并进 intro：站点的 banner 是嵌套 <p>，
外层 <p> 的文本是完整的 A B C、内层两个 <p> 分别是 A B 与 C，于是 `find_all("p")` 收出的三段
没有一段与另一段完全相同，拼起来却是 "A B C A B C"。

用例用**鸭子类型的假 soup**（bs4 是可选依赖，本机没装）：既能精确复现嵌套 <p> 的收法，
又不把测试绑在一个不装的包上。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "docs" / "mirrors" / "dora-capabilities" / "manifest.json"


def _stub(name: str, **attributes: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_dora_site(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "httpx", _stub("httpx", Client=object))
    monkeypatch.setitem(sys.modules, "bs4", _stub("bs4", BeautifulSoup=object))
    spec = importlib.util.spec_from_file_location(
        "dora_site_intro_under_test", REPO_ROOT / "tools" / "dora_site.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Paragraph:
    """只实现被 banner_intro 用到的那一个方法。"""

    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self, *args: object, **kwargs: object) -> str:
        return self._text


class _Banner:
    """嵌套 <p> 的收法：find_all 会把外层与内层都返回（这正是缺陷的来源）。"""

    def __init__(self, *texts: str) -> None:
        self._paragraphs = [_Paragraph(text) for text in texts]

    def find_all(self, name: str) -> list[_Paragraph]:
        assert name == "p"
        return list(self._paragraphs)


SENTENCE_A = "Explore the practices and capabilities that foster a learning environment."
SENTENCE_B = "Each of these articles presentes specific practices."
SENTENCE_C = "You can also learn how to deploy a program in our guide “How to Transform.”"


def test_nested_paragraphs_land_in_the_intro_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """外层 A B C + 内层 A B / C —— 导语必须只有 A B C（顺序按首次出现）。"""

    module = _load_dora_site(monkeypatch)
    banner = _Banner(
        " ".join([SENTENCE_A, SENTENCE_B, SENTENCE_C]),  # 外层 <p>
        " ".join([SENTENCE_A, SENTENCE_B]),  # 内层 <p>
        SENTENCE_C,  # 内层 <p>
    )

    assert module.banner_intro(banner) == [SENTENCE_A, SENTENCE_B, SENTENCE_C]


def test_a_single_paragraph_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """反向对照：没有嵌套时逐句保留，顺序不变（去重不许改动正常页面）。"""

    module = _load_dora_site(monkeypatch)
    banner = _Banner(" ".join([SENTENCE_A, SENTENCE_B]), SENTENCE_C)

    assert module.banner_intro(banner) == [SENTENCE_A, SENTENCE_B, SENTENCE_C]


def test_the_shipped_manifest_equals_what_the_generator_now_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已发布数据与生成器对齐：用**真实的三句导语**搭出旧的嵌套收法，结果必须逐字等于 manifest。

    这条是"改了生成器要重生成"的可执行等价物（本机没有网络、跑不了真抓取）：
    把仓库里那条已经去重的 summary 切成句子，再按旧收法（外层 A B C + 内层 A B + C）喂进
    banner_intro，拼出来必须**逐字**等于已发布的那条 summary——也就是 f7cee84 之后的那一版。
    生成器若退回"按段落去重"，这条会红（三段没有一段完全重复，A B 与 C 会各出现两次）。
    """

    import json
    import re

    module = _load_dora_site(monkeypatch)
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    summary = next(p["summary"] for p in recorded["pages"] if p["local_path"] == "index.md")
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", summary) if item.strip()]
    assert len(sentences) == 3, sentences

    banner = _Banner(
        " ".join(sentences),  # 外层 <p>：完整导语
        " ".join(sentences[:2]),  # 内层 <p>
        sentences[2],  # 内层 <p>
    )
    assert " ".join(module.banner_intro(banner)) == summary

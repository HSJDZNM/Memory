"""dora_site 的 catalog_order：取值域只由 kind=capability 定义。

来源：`docs/mirrors/dora-capabilities/manifest.json` 里同一个字段名装过**两个序列**——能力页用
能力目录页栅格里的序号（1..34），两篇实施指南用 GUIDE_URLS 的顺序（1、2），能力目录页自己写 0。
按这个字段排序 / 去重的消费方会把 `guides/` 插进能力中间：名字承诺的是"能力目录里的序号"，
而 JSON 里两个 1、两个 2 长得一模一样。

新口径：`catalog_order` 只出现在 `kind=capability` 的条目上，取值是 **1..N 的完整序列**
（跨全部模型唯一）；`kind` 为 catalog / guide 的条目记 `null`——"不在能力目录里"是显式的
null，不是一个碰巧撞号的整数。

用例同时钉**生成器**与**已发布数据**：只对一遍数据证明的是"这次看起来对"，
证明不了"下一次重爬还按这个口径写"。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "docs" / "mirrors" / "dora-capabilities" / "manifest.json"


def _stub(name: str, **attributes: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_dora_site(monkeypatch: pytest.MonkeyPatch) -> Any:
    """按路径加载 tools/dora_site.py：httpx / bs4 只在真抓取时用，导入期有名字即可。"""

    monkeypatch.setitem(sys.modules, "httpx", _stub("httpx", Client=object))
    monkeypatch.setitem(sys.modules, "bs4", _stub("bs4", BeautifulSoup=object))
    spec = importlib.util.spec_from_file_location(
        "dora_site_under_test", REPO_ROOT / "tools" / "dora_site.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _page(kind: str, path: str, slug: str, order: int) -> dict[str, Any]:
    return {
        "url": "https://dora.dev/capabilities/" + slug + "/",
        "path": path,
        "slug": slug,
        "kind": kind,
        "title": slug or "Capability catalog",
        "model": "core" if kind == "capability" else ("guide" if kind == "guide" else ""),
        "role": "测试条目",
        "summary": "",
        "order": order,
        "model_href": "",
    }


def test_catalog_order_is_written_only_for_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一个字段名不许再装第二个序列：非 capability 一律 null。"""

    module = _load_dora_site(monkeypatch)
    catalog = {**_page("catalog", "index.md", "", 0), "url": module.CATALOG_URL}
    capability = _page("capability", "core/continuous-integration.md", "continuous-integration", 1)
    guide = _page("guide", "guides/dora-metrics.md", "dora-metrics", 1)
    monkeypatch.setattr(module, "pages", lambda: [catalog, capability, guide])

    written = {
        page["kind"]: module.manifests(page["url"], {})["extra"]["catalog_order"]
        for page in (catalog, capability, guide)
    }
    assert written == {"catalog": None, "capability": 1, "guide": None}


def test_shipped_manifest_keeps_catalog_order_a_complete_capability_sequence() -> None:
    """已发布数据：能力条目的序号恰好是 1..N，其余条目必须是 null。"""

    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pages = document["pages"]
    capabilities = [page for page in pages if page["kind"] == "capability"]
    others = [page for page in pages if page["kind"] != "capability"]

    assert len(capabilities) >= 30, f"能力条目只剩 {len(capabilities)} 条：这条检查会变成空转"
    assert others, "没有非能力条目：下面那条对照不成立"
    assert sorted(page["catalog_order"] for page in capabilities) == list(
        range(1, len(capabilities) + 1)
    ), "能力序号必须是不重不漏的 1..N（撞号 = 两个模型的目录顺序混在一起）"
    assert {
        page["local_path"]: page["catalog_order"]
        for page in others
        if page["catalog_order"] is not None
    } == {}, "非能力条目的 catalog_order 必须是 null：它不在能力目录里"

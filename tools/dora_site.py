# -*- coding: utf-8 -*-
"""dora.dev 的站点专用提取逻辑，供 tools/mirror_docs.py 的站点钩子调用。

dora.dev（Google Cloud 的 DORA 研究项目站点）与 peps.python.org、learn.microsoft.com、
docs.gitlab.com 的页面模板都不同，故独立成模块：

1. 清单与层级都取自站点自身，不做人工归类：
   - 清单：站点 sitemap 在 /capabilities/ 子树下给出 35 条 URL，与该分区索引页
     （/capabilities/，下称"能力目录"）栅格里的 34 个能力卡片逐条比对，双向无差集；
   - 层级：目录页给每张卡片打了模型徽章 core 或 AI（分别指向 /research/#core-model
     与 /ai/#explore-the-model）。徽章只覆盖 24 篇（core 19、AI 5），另外 10 篇的徽章容器
     是空的（<span class=labels></span>），站点没有给出模型归属，故单列 unlabeled/，
     不替站点作推断。
2. 正文边界：正文在 <main> 内，页脚的许可与社交链接、页首导航都在 <main> 之外。
   但目录页的标题与导语在 <main> 之外的 banner 区，须补回；<main> 内还夹着一条
   <link rel=stylesheet> 模板，h1 里嵌着模型徽章，卡片里嵌着 "Learn more" 箭头图，
   转换前一并摘除（徽章内容转记入 manifest 的 model 字段）。
3. 链接：该站正文链接是根相对写法（/capabilities/...），而引擎的链接改写只认绝对地址，
   故先按当前页 URL 解析为绝对地址再交给引擎。
4. 附加收录：能力正文实际引用的两篇 DORA 官方实施指南（/guides/dora-metrics/、
   /guides/how-to-transform/）一并收录——它们不在 /capabilities/ 子树内，但不收录会让
   镜像里的这些引用指回线上站点。
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BT = chr(96)
FENCE = BT * 3
NL = chr(10)

SITE = "https://dora.dev"
CATALOG_URL = SITE + "/capabilities/"
GUIDES_INDEX = SITE + "/guides/"
CORE_MODEL = SITE + "/research/#core-model"
AI_MODEL = SITE + "/ai/#explore-the-model"

# 被能力正文实际引用（共 11 处）的两篇指南；其余 3 篇指南未被能力正文引用，不收录。
GUIDE_URLS = (SITE + "/guides/dora-metrics/", SITE + "/guides/how-to-transform/")

MODEL_DIR = {"core": "core", "ai": "ai", "": "unlabeled"}
MODEL_NAME = {"core": "core", "ai": "AI", "": "站点未标注模型"}
MODEL_ZH = {"core": "DORA Core 模型", "ai": "DORA AI 能力模型", "": "站点未标注模型归属"}
LICENSE = "CC BY 4.0（Google LLC，站点页脚声明）"

_catalog_cache = None
_guides_cache = None
_pages_cache = None


def _get(url):
    """一次性取页面原文；清单是整轮抓取的前提，网络抖动会让整轮作废，故重试几次。

    用 httpx 而不是 urllib：本环境下 urllib 的 TLS 握手可能被中断
    （SSL: UNEXPECTED_EOF），httpx / aiohttp 均正常；先直连，失败再退回环境变量里的代理。
    """
    proxies = [None, os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")]
    last = None
    for proxy in proxies:
        for _ in range(2):
            try:
                with httpx.Client(timeout=60, follow_redirects=True, trust_env=False,
                                  proxy=proxy) as client:
                    resp = client.get(url)
                    resp.raise_for_status()
                    return resp.text
            except Exception as exc:  # noqa: BLE001 - 重试后统一抛出
                last = exc
                time.sleep(1.0)
    raise RuntimeError("页面抓取失败: " + url + " -> " + repr(last))


def _norm(text):
    return " ".join((text or "").split())


def catalog():
    """能力目录页（/capabilities/）：导语 + 34 张能力卡片（标题、模型徽章、一句话摘要）。

    这是本镜像的权威清单与层级来源：卡片顺序即站点顺序，徽章即模型归属。
    """
    global _catalog_cache
    if _catalog_cache is None:
        soup = BeautifulSoup(_get(CATALOG_URL), "html.parser")
        banner = soup.select_one("section.banner article")
        intro = []
        if banner is not None:
            for p in banner.find_all("p"):
                text = _norm(p.get_text(" ", strip=True))
                if text:
                    intro.append(text)
        grid = soup.select_one("section.capabilitiesGrid")
        rows = []
        for art in (grid.find_all("article") if grid is not None else []):
            h4 = art.find("h4")
            link = h4.find("a", href=True) if h4 is not None else None
            holder = h4.find("div") if h4 is not None else None
            badge = holder.find("a", href=True) if holder is not None else None
            label = _norm(badge.get_text(" ", strip=True)).lower() if badge is not None else ""
            para = art.find("p")
            summary = _norm(para.get_text(" ", strip=True)) if para is not None else ""
            summary = re.sub(r"\s*Learn\s*more\s*$", "", summary).strip()
            rows.append({
                "slug": (link["href"].rstrip("/").rsplit("/", 1)[-1] if link is not None else ""),
                "title": _norm(link.get_text(" ", strip=True)) if link is not None else "",
                "model": label if label in ("core", "ai") else "",
                "model_href": (badge["href"] if badge is not None else ""),
                "summary": summary,
            })
        if not rows:
            raise RuntimeError("能力目录页未解析出任何能力卡片: " + CATALOG_URL)
        _catalog_cache = {"intro": intro, "rows": rows}
    return _catalog_cache


def guide_meta():
    """指南索引页（/guides/）给出的标题与一句话摘要（仅用于清单文字，正文以页面 h1 为准）。"""
    global _guides_cache
    if _guides_cache is None:
        meta = {}
        try:
            soup = BeautifulSoup(_get(GUIDES_INDEX), "html.parser")
            for url in GUIDE_URLS:
                slug = url.rstrip("/").rsplit("/", 1)[-1]
                a = soup.find("a", href=lambda h: h and h.rstrip("/").endswith("/guides/" + slug))
                title, summary = "", ""
                if a is not None:
                    title = _norm(a.get_text(" ", strip=True))
                    block = a.find_parent(["article", "section", "div"]) or a.parent
                    if block is not None:
                        summary = _norm(block.get_text(" ", strip=True))
                        summary = re.sub(r"^" + re.escape(title) + r"\s*", "", summary).strip()
                meta[url] = {"title": title or slug, "summary": summary}
        except Exception:  # noqa: BLE001 - 索引页只用于文字描述，失败即退回占位
            meta = {u: {"title": u.rstrip("/").rsplit("/", 1)[-1], "summary": ""} for u in GUIDE_URLS}
        _guides_cache = meta
    return _guides_cache


def pages():
    """本镜像的页面清单：能力目录页 1 篇 + 能力页 34 篇 + 被引用的指南 2 篇。"""
    global _pages_cache
    if _pages_cache is None:
        cat = catalog()
        out = [{
            "url": CATALOG_URL, "path": "index.md", "slug": "", "kind": "catalog",
            "title": "Capability catalog", "model": "", "role": "能力目录",
            "summary": _norm(" ".join(cat["intro"])), "order": 0, "model_href": "",
        }]
        for i, row in enumerate(cat["rows"], 1):
            out.append({
                "url": SITE + "/capabilities/" + row["slug"] + "/",
                "path": MODEL_DIR[row["model"]] + "/" + row["slug"] + ".md",
                "slug": row["slug"], "kind": "capability", "title": row["title"],
                "model": row["model"], "role": "能力文档 · " + MODEL_ZH[row["model"]],
                "summary": row["summary"], "order": i, "model_href": row["model_href"],
            })
        meta = guide_meta()
        for j, url in enumerate(GUIDE_URLS, 1):
            out.append({
                "url": url, "path": "guides/" + url.rstrip("/").rsplit("/", 1)[-1] + ".md",
                "slug": url.rstrip("/").rsplit("/", 1)[-1], "kind": "guide",
                "title": meta[url]["title"], "model": "guide", "role": "实施指南（正文引用）",
                "summary": meta[url]["summary"], "order": j, "model_href": "",
            })
        _pages_cache = out
    return _pages_cache


def _by_url(url):
    key = (url or "").rstrip("/")
    for p in pages():
        if p["url"].rstrip("/") == key:
            return p
    return None


def targets():
    """discovery=list 所需的页面清单（规范 URL，由引擎归一化后抓取）。"""
    return [{"url": p["url"], "path": p["path"], "role": p["role"], "why": _why(p),
             "source": p["url"]} for p in pages()]


def pathmap():
    """规范 URL -> 本地相对路径。目录页置顶为 index.md，其余按模型分层。"""
    return {p["url"]: p["path"] for p in pages()}


def urlmap_extra(spec):
    """带尾斜杠 / 不带尾斜杠两种写法都指向同一文件：站内链接两种写法都有。"""
    out = {}
    for p in pages():
        out[p["url"]] = p["path"]
        out[p["url"].rstrip("/")] = p["path"]
    return out


def _why(p):
    if p["kind"] == "catalog":
        return "站点 /capabilities/ 分区索引页：本镜像的能力清单与层级均取自该页栅格"
    if p["kind"] == "guide":
        return "被能力正文实际引用的 DORA 官方实施指南（不在 /capabilities/ 子树内）"
    if p["model"]:
        return ("站点能力目录页给出的模型徽章为 " + MODEL_NAME[p["model"]]
                + "（" + p["model_href"] + "），据此归入 " + MODEL_DIR[p["model"]] + "/")
    return "站点能力目录页未给出模型徽章（该页 h1 的标签容器为空），归入 unlabeled/"


def manifests(url, spec):
    """给引擎的 manifest 条目补上 role / why 与模型层级字段。"""
    p = _by_url(url)
    if p is None:
        return {"role": "", "why": "", "extra": {}}
    return {
        "role": p["role"],
        "why": _why(p),
        "extra": {
            "kind": p["kind"],
            "model": p["model"],
            "model_name": MODEL_NAME.get(p["model"], ""),
            "model_href": p["model_href"],
            "catalog_order": p["order"],
            "summary": p["summary"],
            "parent": "index.md" if p["kind"] != "catalog" else "",
        },
    }


def _res_html(res):
    if isinstance(res, dict):
        return res.get("html") or ""
    return getattr(res, "html", "") or ""


def _res_url(res):
    if isinstance(res, dict):
        return res.get("url") or ""
    return getattr(res, "url", "") or ""


def _absolutize(node, page_url):
    """正文里的链接是根相对写法，引擎的链接改写只认绝对地址，故先补全。"""
    for a in node.find_all("a", href=True):
        href = (a["href"] or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        if href.startswith("//"):
            a["href"] = "https:" + href
        elif not href.startswith(("http://", "https://")):
            a["href"] = urljoin(page_url, href)
    for img in node.find_all("img", src=True):
        src = (img["src"] or "").strip()
        if src.startswith("//"):
            img["src"] = "https:" + src
        elif src and not src.startswith(("http://", "https://", "data:")):
            img["src"] = urljoin(page_url, src)


def pre_markdown(res, spec, ctx, to_markdown):
    """只把 <main> 里的正文交给引擎；目录页的标题与导语从 banner 区补回。"""
    soup = BeautifulSoup(_res_html(res), "html.parser")
    main = soup.find("main")
    if main is None:
        return _res_html(res)
    for tag in main.find_all(["link", "script", "style", "nav", "form", "noscript"]):
        tag.decompose()
    for span in main.select("h1 span.labels"):       # h1 里的模型徽章：转记 manifest，不进正文
        span.decompose()
    for span in main.select("span.learn_more"):      # 卡片里的 "Learn more" 箭头图
        span.decompose()

    # 目录页的卡片标题在原页面是 h4（栅格卡片），线性化为 Markdown 后改为 h2：
    # 否则正文会从 h1 直接跳到 h4，标题层级断裂（tools/mirror_docs.py --verify 会报错）。
    for h in main.select("section.capabilitiesGrid h4"):
        h.name = "h2"

    h1 = main.find("h1")
    banner = soup.select_one("section.banner article")
    if h1 is None and banner is not None:
        # 目录页：h1 与导语在 <main> 之外的 banner 区，按原顺序补回正文开头。
        # 源页面的导语写成 <p><p>…</p><p>…</p></p>（浏览器会自行纠正），故只取最内层段落，
        # 否则导语会被重复输出两遍。
        head = soup.new_tag("div")
        title_tag = soup.new_tag("h1")
        title_tag.string = _norm(banner.find("h1").get_text(" "))
        head.append(title_tag)
        for p in [p for p in banner.find_all("p") if p.find("p") is None]:
            head.append(BeautifulSoup(str(p), "html.parser"))
        main.insert(0, head)
        h1 = main.find("h1")
    if h1 is not None and _norm(h1.get_text(" ")):
        ctx["title"] = _norm(h1.get_text(" "))

    # 摘除 "Learn more" 箭头后，卡片摘要末尾会留一个空格（形如 "[摘要 ](链接)"），
    # 故把只剩单个文本节点的元素去掉首尾空白。
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "a", "li", "em", "strong"]):
        if el.string is not None:
            el.string.replace_with(el.string.strip())

    _absolutize(main, _res_url(res) or CATALOG_URL)
    return str(main)


def post_markdown(md, res, spec, ctx):
    """正文清洗：丢掉 h1 之前的模板文字，压缩空行，去掉行尾空白。"""
    md = md.replace("\u00a0", " ")
    head = re.search(r"^# ", md, re.M)
    if head:
        md = md[head.start():]
    lines = [ln.rstrip() for ln in md.split(NL)]
    md = NL.join(lines)
    while (NL * 3) in md:
        md = md.replace(NL * 3, NL * 2)
    return md.strip() + NL


# --------------------------------------------------------------------------
# 供 SITES 配置引用的动态文本（spec_lines 支持 "模块:函数" 形式）
# --------------------------------------------------------------------------
def _counts():
    ps = pages()
    caps = [p for p in ps if p["kind"] == "capability"]
    return {
        "total": len(ps),
        "catalog": len([p for p in ps if p["kind"] == "catalog"]),
        "caps": len(caps),
        "core": len([p for p in caps if p["model"] == "core"]),
        "ai": len([p for p in caps if p["model"] == "ai"]),
        "unlabeled": len([p for p in caps if not p["model"]]),
        "guides": len([p for p in ps if p["kind"] == "guide"]),
    }


def C(text):
    return BT + text + BT


def findings():
    """STRUCTURE.md 的「范围判定」段：清单来源、层级来源与边界。"""
    n = _counts()
    lines = [
        "**清单来源：站点自身的 sitemap 与「能力目录」页。** 站点 " + C("/sitemap.xml")
        + " 在 " + C("/capabilities/") + " 子树下给出 " + str(n["caps"] + n["catalog"]) + " 条 URL；"
        + C("/capabilities/") + " 索引页（下称能力目录）栅格里有 " + str(n["caps"]) + " 张能力卡片。",
        "两者逐条比对**双向无差集**：栅格卡片 = sitemap 的能力页，sitemap 多出的 1 条即目录页自身。",
        "本镜像按这份清单逐页抓取（" + C("discovery=list") + "），不做逐边 BFS——能力正文的站内链接",
        "遍布 /research、/ai、/guides、/quickcheck 等分区，逐边扩散会把范围带出本分区。",
        "",
        "**层级来源：能力目录页给每张卡片打的模型徽章。** 卡片携带 " + C("core") + " 或 " + C("AI")
        + " 徽章，分别指向 " + C("/research/#core-model") + " 与 " + C("/ai/#explore-the-model") + "。",
        "本镜像据此分层：" + C("core/") + " " + str(n["core"]) + " 篇（DORA Core 模型）、" + C("ai/") + " "
        + str(n["ai"]) + " 篇（DORA AI 能力模型）；另有 " + str(n["unlabeled"]) + " 篇的徽章容器为空",
        "（这些页 h1 内的 " + C("<span class=labels></span>") + " 无内容），站点未给出模型归属，",
        "故单列 " + C("unlabeled/") + "，不替站点作推断。",
        "",
        "**附加收录：正文实际引用的 2 篇 DORA 官方指南**（" + C("/guides/dora-metrics/") + "、"
        + C("/guides/how-to-transform/") + "）。",
        "它们不在 " + C("/capabilities/") + " 子树内，但被能力正文按实施指导的方式引用（共 11 处）；",
        "不收录会让镜像内的这些引用指回线上站点。",
        "",
        "**本地路径与 URL 的对应关系**：目录页 -> " + C("index.md") + "；能力页 -> "
        + C("<模型目录>/<URL 末段>.md") + "；",
        "指南 -> " + C("guides/<URL 末段>.md") + "。文件名一律取 URL 末段，任意文件都能反查回线上地址；",
        "模型归属另见 " + C("manifest.json") + " 的 " + C("model") + " / " + C("model_name") + " / "
        + C("model_href") + " 字段与各篇 front matter 的 " + C("section") + "。",
    ]
    return lines


def readme_saved():
    n = _counts()
    return [
        "- **能力目录页 1 篇**：" + C("index.md") + "（Capability catalog），站点对 /capabilities/ 分区的索引，",
        "  34 张卡片各带一句话摘要与模型徽章——本镜像的清单与层级都取自这一页；",
        "- **core 模型能力 " + str(n["core"]) + " 篇**：站点标注 " + C("core") + " 徽章的能力，含本次抓取的入口",
        "  " + C("core/continuous-integration.md") + "（Continuous integration）；",
        "- **AI 能力模型 " + str(n["ai"]) + " 篇**：" + "、".join(
            p["slug"] for p in pages() if p["kind"] == "capability" and p["model"] == "ai") + "；",
        "- **站点未标注模型的能力 " + str(n["unlabeled"]) + " 篇**：目录页徽章容器为空的那些页，单列 "
        + C("unlabeled/") + "，",
        "  不替站点推断归属；",
        "- **被正文引用的实施指南 " + str(n["guides"]) + " 篇**：" + "、".join(
            C(p["path"]) for p in pages() if p["kind"] == "guide") + "，",
        "  被能力正文按实施指导的方式引用；",
        "- " + C("manifest.json") + "：逐页记录来源 URL、本地路径、角色与收录理由（role / why）、",
        "  模型层级（model / model_name / model_href / catalog_order）、摘要、字节数与 sha256，便于校验。",
    ]


def readme_skipped():
    return [
        "- " + C("/research/") + " 分区（sitemap 计 44 条）：历年 DORA 报告页、问卷与 errata，是研究报告",
        "  而非能力指南；其中被正文引用最多的是历年报告的 PDF 附件（本次共 116 处引用），PDF 亦非文本镜像对象；",
        "- " + C("/quickcheck/") + "（37 处引用）：交互式自评工具，不是文档；",
        "- " + C("/ai/") + " 分区（26 处引用）：AI 研究分区。其首页正文由客户端脚本渲染，HTTP 通道抓不到正文；",
        "  能力目录里 AI 徽章指向的 " + C("/ai/#explore-the-model") + " 只是该页内的锚点；",
        "- " + C("/guides/") + " 中未被能力正文引用的 3 篇（how-to-empower-software-delivery-teams、",
        "  how-to-innovate-with-generative-ai、value-stream-management）：属 /guides/ 分区的其它指南，",
        "  与本次两个入口页（能力页）无正文引用关系，故不在本次范围；",
        "- " + C("/insights/") + "（3 处引用）与站点页脚链接（/resources/、/faq/、/contact/、" + C("/") + "）：",
        "  博客与研究动态、站点导航，不是能力指南；",
        "- 站外链接（martinfowler.com、cloud.google.com、infoq.com、github.com 等，正文共 208 处引用）：",
        "  超出本站范围，在正文中保留为绝对地址，可在线跳转。",
    ]


def readme_facts():
    facts = [
        "- 清单来自站点 sitemap 与能力目录页栅格的比对（双向无差集），并**不是**逐边 BFS 的结果；",
        "- 层级（core / ai / unlabeled）**不是人工归类**：core 与 AI 取自目录页徽章，unlabeled 表示站点未给徽章；",
        "- 该站为服务端渲染的静态站点，正文在 " + C("<main>") + " 内，用 crawl4ai 的 AsyncHTTPCrawlerStrategy",
        "  （纯 HTTP 通道）即可完整取到，无需启动浏览器；",
        "- 模板清理：页首导航、搜索弹层、站点横幅与页脚本就在 " + C("<main>") + " 之外；" + C("<main>")
        + " 内的",
        "  一条 " + C("<link rel=stylesheet>") + "、" + "h1 里的模型徽章与卡片里的 " + C("Learn more")
        + " 箭头图在转换前摘除；",
        "- 目录页的 h1 与导语位于 " + C("<main>") + " 之外的 banner 区，站点模块按原顺序补回正文开头；",
        "- 目录页卡片标题在源页面是 " + C("h4") + "（栅格卡片），线性化为 Markdown 后改为 " + C("h2")
        + "，以保持标题层级连续；",
        "- 源页面导语写成嵌套的 " + C("<p><p>…</p><p>…</p></p>") + "，转换时只取最内层段落，避免重复输出；",
        "- 正文链接在源站 HTML 里是根相对写法（" + C("/capabilities/...") + "），站点模块先按当前页 URL 解析为",
        "  绝对地址再交给引擎改写，因此镜像内链接可离线跳转；",
        "- 站点许可：页脚声明除另有说明外，全站内容由 Google LLC 以 CC BY 4.0 授权。",
    ]
    got = _manifest_facts()
    return facts + got


def _manifest_facts():
    """从刚落盘的 manifest.json 读取本轮抓取实况（该文件在写 README 之前已写出）。"""
    out = Path(__file__).resolve().parent.parent / "docs" / "dora-capabilities" / "manifest.json"
    if not out.is_file():
        return []
    try:
        data = json.loads(out.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 读不到就不写这条事实
        return []
    pages_ = data.get("pages", [])
    ok = [p for p in pages_ if p.get("saved")]
    bad = [p for p in pages_ if not p.get("saved")]
    statuses = sorted({str(p.get("status")) for p in ok})
    line = ("- 本轮抓取：" + str(len(pages_)) + " 个页面，成功 " + str(len(ok)) + " 个"
            + ("，失败 " + str(len(bad)) + " 个" if bad else "、无失败页")
            + "，返回状态 " + " / ".join(statuses) + "；抓取时间 " + str(data.get("fetched_at", "")) + "。")
    return [line]

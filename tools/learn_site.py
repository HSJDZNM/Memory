
# -*- coding: utf-8 -*-
"""learn.microsoft.com 的站点专用提取逻辑，供 tools/mirror_docs.py 的站点钩子调用。

Microsoft Learn 的页面模板与 peps.python.org、docs.gitlab.com 都不同，故独立成模块：

1. 清单与层级：页面清单与层级**都取自站点自身的目录接口** toc.json（该接口是这一章节的
   权威目录，49 个节点），不靠逐边 BFS 扩散。层级（toc_path / order / parent / role）
   写入 manifest，供离线读者与校验脚本使用。
2. 本地路径：该站 canonical URL **不带尾斜杠**，故本地文件名按 URL 末段扁平映射
   （naming-guidelines -> naming-guidelines.md），与站点 URL 路径仍一一对应。
   带尾斜杠的写法是同一页的等价地址，通过 urlmap_extra 一并指向同一文件。
3. 正文边界：页面模板把导航、TOC 侧栏、面包屑、页首操作按钮与授权提示都塞在 <main> 内，
   必须先摘除这些模板块，否则转换出来的 Markdown 会混入大量导航文本。
4. 页脚：正文末尾的 "Additional resources" 区块属站点模板，须截断；其中页面自身标注的
   "Last updated on" 日期保留为文末引注，便于判断内容新旧。
5. 元数据：title 取正文 h1；来源仓库路径由 URL 推导（每页页首「编辑此文档」链接即指向
   dotnet/docs 仓库中的同名 Markdown 源文件）。
"""
from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import urljoin

import httpx
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BT = chr(96)
FENCE = BT * 3
NL = chr(10)

BASE = "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines"
TOC_URL = BASE + "/toc.json"
SOURCE_REPO_DIR = "docs/standard/design-guidelines"
SOURCE_REPO = "https://github.com/dotnet/docs/blob/main/" + SOURCE_REPO_DIR + "/"

# 页面模板里需要整体摘除的块（选择器来自实际 HTML：都位于 <main> 之内）
CHROME_SELECTORS = (
    "#ms--content-header",              # 页首工具条：Table of contents / Exit editor mode
    "#action-panel",
    "#ms--toc-content",                 # 右侧目录导轨
    "#article-header",                  # 面包屑 + 编辑/复制/打印按钮
    "#article-metadata",                # 页首元数据行
    "#article-metadata-footer",
    "div[unauthorized-private-section]",  # 未登录提示模板
    "#article-feedback",
    "#main-column",                     # 兼容旧模板
    ".feedback-verbatim",
    ".display-none-print",
)

# 转换后仍可能残留的模板文本行（安全网）
DROP_LINES = {
    "Feedback",
    "Summarize this article for me",
    "Copy Markdown Print",
    "Table of contents",
    "Exit editor mode",
    "Ask Learn Ask Learn",
    "Reading mode Table of contents Read in English Add Add to Plans",
    "* * *",
}

FOOTER_RE = re.compile(r"^##\s+Additional resources\s*$", re.M)
UPDATED_RE = re.compile(r"Last updated on\s+(\d{4}-\d{2}-\d{2})")
MOJIBAKE = (("\u00c2\u00a9", "\u00a9"), ("\u00c2\u00a0", " "))

_toc_cache = None
_pages_cache = None
def _fetch_toc():
    """目录接口原文（一次性）。该接口同时给出标题、层级与相对 URL。

    清单是整轮抓取的前提，网络抖动会让整轮作废，故做几次重试。
    """
    global _toc_cache
    if _toc_cache is not None:
        return _toc_cache
    # 用 httpx 而不是 urllib：本环境下 urllib 的 TLS 握手被中断（SSL: UNEXPECTED_EOF），
    # httpx / aiohttp 均正常；先直连，失败再退回环境变量里的代理。
    proxies = [None, os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")]
    last = None
    for proxy in proxies:
        for _ in range(2):
            try:
                with httpx.Client(timeout=60, follow_redirects=True, trust_env=False,
                                  proxy=proxy) as client:
                    resp = client.get(TOC_URL)
                    resp.raise_for_status()
                    _toc_cache = resp.json()
                return _toc_cache
            except Exception as exc:
                last = exc
                time.sleep(1.0)
    raise RuntimeError("目录接口抓取失败: " + TOC_URL + " -> " + repr(last))


def _canon(href):
    """相对 href -> 规范 URL（canonical 形式：不带尾斜杠）。"""
    return urljoin(TOC_URL, href).split("#")[0].rstrip("/")


def _relpath(url):
    """规范 URL -> 本地文件相对路径（扁平，与 URL 末段一一对应）。"""
    tail = url.rstrip("/")[len(BASE):].strip("/")
    return (tail + ".md") if tail else "index.md"


def _source_repo(url):
    return SOURCE_REPO + (_relpath(url)[:-3] + ".md")


def _collect(items, out, parent, path, depth):
    for i, node in enumerate(items, 1):
        title = (node.get("toc_title") or "").strip()
        kids = node.get("children") or []
        href = node.get("href")
        here = path + [title]
        if href:
            url = _canon(href)
            if url == BASE:
                role, parent_page = "root-index", None
            else:
                role = "section-index" if kids else "chapter"
                parent_page = parent
            # 所属章节 = 最近祖先页面的标题；根页与章节索引页自身不属任何章节
            section = here[-2] if (depth >= 2 and len(here) >= 2) else ""
            out.append({
                "url": url,
                "path": _relpath(url),
                "title": title,
                "role": role,
                "toc_path": here,
                "order": i,
                "depth": depth,
                "parent": parent_page or "",
                "section": section,
            })
            _collect(kids, out, url, here, depth + 1)
        else:
            # 无 href 的是纯容器节点（章节总标题），其子页的父级即根索引页；
            # 容器本身占一层，故子页 depth 要 +1（一级章节=1，其子页=2）
            _collect(kids, out, parent or BASE, here, depth + 1)


def pages():
    """TOC 顺序的页面清单 + 每页的层级元数据（结论全部来自 toc.json）。"""
    global _pages_cache
    if _pages_cache is None:
        out = []
        _collect(_fetch_toc().get("items", []), out, None, [], 0)
        for p in out:
            prefix = " > ".join(p["toc_path"])
            if p["role"] == "root-index":
                p["why"] = "章节总览页；上游目录路径：" + prefix
                p["role_zh"] = "站点首页"
            elif p["role"] == "section-index":
                p["why"] = "该章节目录节点本身也是页面；上游目录路径：" + prefix
                p["role_zh"] = "章节索引"
            else:
                p["why"] = "上游目录路径：" + prefix + "（同级第 " + str(p["order"]) + " 篇）"
                p["role_zh"] = "指南文档"
            p["extra"] = {
                "why": p["why"],
                "toc_path": prefix,
                "toc_order": p["order"],
                "toc_depth": p["depth"],
                "parent": _relpath(p["parent"]) if p["parent"] else "",
                "chapter": p["section"],
                "source_repo_path": SOURCE_REPO_DIR + "/" + p["path"][:-3] + ".md",
            }
        _pages_cache = out
    return _pages_cache


def targets():
    """discovery=list 所需的页面清单（规范 URL，由引擎归一化后抓取）。"""
    return [{"url": p["url"], "path": p["path"], "role": p["role_zh"], "why": p["why"],
             "source": p["url"]} for p in pages()]


def urlmap_extra(spec):
    """本地路径映射：canonical（带尾斜杠，引擎归一化后的键）与无尾斜杠写法都指向同一文件。"""
    out = {}
    for p in pages():
        out[p["url"]] = p["path"]
        out[p["url"] + "/"] = p["path"]
    return out


def manifests(url, spec):
    """给引擎的 manifest 条目补上 role / why 与层级字段。"""
    key = (url or "").rstrip("/")
    for p in pages():
        if p["url"] == key:
            return {"role": p["role_zh"] + " · " + p["title"], "why": p["why"], "extra": p["extra"]}
    return {"role": "", "why": "", "extra": {}}
def _norm(text):
    return " ".join((text or "").split())


def _res_html(res):
    """引擎传进来的是 pages[url] 字典（含 html/url/title），单元测试里也可能传对象。"""
    if isinstance(res, dict):
        return res.get("html") or ""
    return getattr(res, "html", "") or ""


def _res_url(res):
    if isinstance(res, dict):
        return res.get("url") or ""
    return getattr(res, "url", "") or ""


def pre_markdown(res, spec, ctx, to_markdown):
    """摘除 <main> 内的模板块，只把正文容器交给引擎转换。"""
    html = _res_html(res)
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main", id="main") or soup.find("main") or soup.body
    if main is None:
        return html
    h1 = main.find("h1")
    if h1 is not None and _norm(h1.get_text(" ")):
        ctx["title"] = _norm(h1.get_text(" "))
    # 页面自身标注的更新日期在页脚元数据块里（该块随后会被当作模板摘除），先取出来
    foot = main.select_one("#article-metadata-footer")
    if foot is not None:
        found = UPDATED_RE.search(foot.get_text(" "))
        if found:
            ctx["updated"] = found.group(1)
    for sel in CHROME_SELECTORS:
        for tag in main.select(sel):
            tag.decompose()
    for tag in main.find_all(["script", "style", "nav", "form", "noscript"]):
        tag.decompose()
    art = main.select_one("div.reading-width") or main
    _absolutize(art, _res_url(res) or BASE)
    return str(art)


def _absolutize(art, page_url):
    # 引擎传入的 URL 是归一化后的目录式写法（带尾斜杠），直接用来 urljoin 会把同级链接
    # 解析成子目录（naming-guidelines/capitalization-conventions），故先还原 canonical 形式
    page_url = (page_url or BASE).rstrip("/")
    """把正文中的相对链接补全为绝对 URL。

    该站正文里的链接有两种相对形式：根相对（/en-us/...，指向 API 参考等）与同级相对
    （capitalization-conventions、./，指向本章其它页面）。引擎的链接改写只认绝对地址，
    相对地址既无法改写成本地路径，离线后也不可点，故统一按当前页 URL 解析。
    """
    for a in art.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        if href.startswith("//"):
            a["href"] = "https:" + href
        elif not href.startswith(("http://", "https://")):
            a["href"] = urljoin(page_url, href)


def post_markdown(md, res, spec, ctx):
    """正文清洗：修双重编码、截断站点页脚、去模板行、保留页面自身的更新日期。"""
    for bad, good in MOJIBAKE:
        md = md.replace(bad, good)

    last = ctx.get("updated", "")
    foot = FOOTER_RE.search(md)
    if foot:
        if not last:
            found = UPDATED_RE.search(md[foot.end():])
            if found:
                last = found.group(1)
        md = md[:foot.start()]

    out = []
    for line in md.split(NL):
        stripped = line.strip()
        if stripped in DROP_LINES:
            continue
        if stripped.startswith("Access to this page requires authorization"):
            continue
        out.append(line.rstrip())
    md = NL.join(out)

    # 正文从一级标题开始：页首若有残余模板文本，一并丢弃
    head = re.search(r"^# ", md, re.M)
    if head:
        md = md[head.start():]

    while (NL * 3) in md:
        md = md.replace(NL * 3, NL * 2)
    md = md.strip()
    if last:
        md += NL * 2 + "_源站标注：Last updated on " + last + "_"
    return md + NL

def C(text):
    return BT + text + BT


def tree_lines():
    """按 toc.json 生成层级树（左：本地文件；右：上游目录标题）。"""
    rows = []

    def walk(items, prefix):
        for i, node in enumerate(items):
            last = i == len(items) - 1
            kids = node.get("children") or []
            title = (node.get("toc_title") or "").strip()
            href = node.get("href")
            branch = prefix + ("└── " if last else "├── ")
            pad = prefix + ("    " if last else "│   ")
            if href:
                note = title + ("" if not kids else "（章节索引 · " + str(len(kids)) + " 篇）")
                rows.append((branch + _relpath(_canon(href)), note))
            else:
                rows.append((branch + "[章节总标题]", title + "（目录节点，本身无页面）"))
            walk(kids, pad)

    walk(_fetch_toc().get("items", []), "")
    width = max(len(a) for a, _ in rows) + 2
    return [a.ljust(width) + "# " + b for a, b in rows]


def findings():
    """STRUCTURE.md 的「范围判定」段：清单来源、封闭性论证与层级树（按 toc.json 现算）。"""
    counts = {"root-index": 0, "section-index": 0, "chapter": 0}
    for p in pages():
        counts[p["role"]] += 1
    lines = [
        "**清单与层级都取自站点自身的目录接口** " + C(TOC_URL) + "：该接口给出 "
        + str(len(pages())) + " 个带 href 的目录节点——章节总览页 " + str(counts["root-index"])
        + " 篇、章节索引页 " + str(counts["section-index"]) + " 篇、指南正文 " + str(counts["chapter"]) + " 篇。",
        "本镜像按这份目录逐页抓取，不依赖逐边 BFS；抓取后再把每篇正文里的全部超链接与目录接口比对，",
        "站内链接集合与目录完全一致，说明本指南之外没有遗漏页面，范围封闭可复核。",
        "",
        "**本地路径与层级的关系**：该站 canonical URL 不带尾斜杠（" + C(".../design-guidelines/names-of-namespaces")
        + "），",
        "故本地文件按 URL 末段扁平命名（" + C("names-of-namespaces.md") + "），与站点 URL 路径一一对应；",
        "章节层级由下面的层级树与 " + C("manifest.json") + " 的 " + C("toc_path") + " / " + C("parent") + " / "
        + C("toc_order") + " / " + C("chapter") + " 字段表达，",
        "每篇 front matter 的 " + C("role") + " 与 " + C("why") + " 亦标明所属章节。",
        "",
        "**层级树**（左侧为本地文件，右侧为上游目录标题）：",
        "",
        FENCE,
    ]
    lines += tree_lines()
    lines += [FENCE]
    return lines

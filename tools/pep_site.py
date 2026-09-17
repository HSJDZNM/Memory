# -*- coding: utf-8 -*-
"""peps.python.org 的站点专用提取逻辑，供 tools/mirror_docs.py 的 pre_markdown 钩子调用。

通用引擎只能剥离标签、改写链接；PEP 站点还需要站点特有的处理，故独立成模块：

1. 正文边界：只取 <section id="pep-content">，剔除导航栏、主题切换按钮与目录折叠块。
2. 代码块：<pre> 内是 Pygments 高亮标签，直接转换会把代码中的 # 注释误判为 Markdown
   标题。故先把 <pre> 抽成纯文本并以占位符替换，转换后再还原为围栏代码块。
3. 标题层级：文件 H1 为文档自身标题，原文标题层级整体下移一级（h1->h2）。
4. 元数据与脚注：从字段列表取 Author/Status/Type/Created 等；从脚注定义取参考资料。
   正文里重复的那一份标题+字段块被删除，避免与 front matter 中的元数据重复。
5. 许可：从正文章节中抽取 "Copyright" 一节的声明文本，作为该页的许可依据。
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup
from urllib.parse import urljoin

BT = chr(96)
FENCE = BT * 3
CODE_SENT = "\u0000CBLK{}KBLKC\u0000"

_BLK = chr(10)


def targets():
    """本次镜像的页面清单：PEP 8 / PEP 257 两个根文档，及其正文实际引用的文档。

    清单由根文档正文中的超链接逐一评估后确定（每个链接都实际抓取并阅读），
    判断依据见 docs/python-pep-code-style/README.md 的「收录范围与取舍」。
    """
    peps = [
        ("pep-0008", "pep-8-python-code/index.md", "PEP 8 - Style Guide for Python Code",
         "PEP 8 主文档：Python 官方代码风格规范"),
        ("pep-0007", "pep-8-python-code/companion/pep-7-c-code/index.md", "PEP 7 - Style Guide for C Code",
         "PEP 8 开篇显式指向的配套文档（CPython 的 C 代码风格）"),
        ("pep-0020", "pep-8-python-code/philosophy/pep-20-zen/index.md", "PEP 20 - The Zen of Python",
         "PEP 8 引其 “Readability counts”，是风格准则的取舍依据"),
        ("pep-3131", "pep-8-references/pep-3131-non-ascii-identifiers/index.md",
         "PEP 3131 - Supporting Non-ASCII Identifiers", "PEP 8「ASCII Compatibility」一节要求遵循的政策"),
        ("pep-0484", "pep-8-references/pep-484-type-hints/index.md", "PEP 484 - Type Hints",
         "PEP 8 的函数注解与 .pyi 存根规则直接采用其语法"),
        ("pep-0526", "pep-8-references/pep-526-variable-annotations/index.md",
         "PEP 526 - Syntax for Variable Annotations", "PEP 8 变量注解一节引用"),
        ("pep-0257", "pep-257-docstrings/index.md", "PEP 257 - Docstring Conventions",
         "PEP 257 主文档：Python 官方文档字符串约定"),
        ("pep-0256", "pep-257-docstrings/upstream/pep-256-docstring-framework/index.md",
         "PEP 256 - Docstring Processing System Framework", "PEP 257 所引 Docutils 系统的框架规范"),
        ("pep-0258", "pep-257-docstrings/upstream/pep-258-docutils-design/index.md",
         "PEP 258 - Docutils Design Specification", "PEP 257 明确要求「详见 PEP 258」"),
    ]
    out = [{"url": "https://peps.python.org/" + pid + "/", "path": path, "role": role, "why": why,
            "source": "https://peps.python.org/" + pid + "/"} for pid, path, role, why in peps]
    out.append({"url": "https://docutils.sourceforge.io/", "path": "references/docutils/index.md",
                "role": "Docutils 官方文档首页", "why": "PEP 257 两次引用 Docutils 作为感知文档字符串约定的软件",
                "source": "https://docutils.sourceforge.io/"})
    out.append({"url": "https://www.python.org/community/sigs/current/doc-sig/",
                "path": "references/doc-sig/index.md", "role": "Python Doc-SIG 特别兴趣组",
                "why": "PEP 257 声明其借鉴了 Doc-SIG 归档中的理念",
                "source": "https://www.python.org/community/sigs/current/doc-sig/"})
    return out


def _fence(soup):
    blocks = []
    for i, pre in enumerate(soup.find_all("pre")):
        code = pre.get_text()
        while code.endswith(_BLK) or code.endswith(" "):
            code = code[:-1]
        blocks.append(FENCE + _BLK + code + _BLK + FENCE)
        pre.replace_with(CODE_SENT.format(i))
    return blocks


def _restore(text, blocks):
    for i, b in enumerate(blocks):
        text = text.replace(CODE_SENT.format(i), b)
    return text


def _norm(text):
    return " ".join((text or "").split())


def _fields(sec):
    out = {}
    dl = sec.find("dl")
    if not dl:
        return out
    key = None
    for child in dl.find_all(["dt", "dd"], recursive=False):
        if child.name == "dt":
            key = _norm(child.get_text(" ")).rstrip(":").strip()
        elif key:
            out.setdefault(key, _norm(child.get_text(" ")))
    return out


def _refs(sec):
    out = []
    for dt in sec.find_all("dt"):
        if not re.match(r"^(fn-|id\d+$|footnote-|reference-)", dt.get("id", "")):
            continue
        dd = dt.find_next_sibling("dd")
        if dd:
            text = _norm(dd.get_text(" "))
            if text:
                out.append(text)
    return out


def _copyright(sec):
    node = sec.find(id="copyright")
    if node is None:
        return ""
    text = _norm(node.get_text(" "))
    return re.sub(r"^Copyright\s*", "", text).strip()


META_KEYS = ("Author", "BDFL-Delegate", "Status", "Type", "Topic", "Created",
             "Python-Version", "Post-History", "Discussions-To", "Resolution",
             "Requires", "Replaces", "Superseded-By", "Sponsor", "Title")
FIELD_RE = re.compile(r"^[A-Z][A-Za-z0-9-]*(?:-[A-Za-z0-9]+)*:[ \t]*$")
INDENT_RE = re.compile(r"^[ \t]{2,}\S")
RULE_RE = re.compile(r"^\s*(?:\*\s*\*\s*\*|---+|\*\*\*+)\s*$")
HDR_RE = re.compile(r"^#{1,6}\s")
HEADING_LINK_RE = re.compile(r"^(#{1,6})\s+\[([^\]]+)\]\(#[^)]*\)[ \t]*$")


def _strip_meta_block(body):
    """删除正文开头与 front matter 重复的标题+字段块（元数据已在正文表格中保留）。"""
    lines = body.split(_BLK)
    k = 0
    while k < len(lines) and not lines[k].strip():
        k += 1
    if k >= len(lines) or not HDR_RE.match(lines[k]):
        return body
    k += 1
    while k < len(lines) and (not lines[k].strip() or RULE_RE.match(lines[k])):
        k += 1
    saw_field = False
    while k < len(lines):
        line = lines[k]
        if FIELD_RE.match(line) and line.strip()[:-1] in META_KEYS:
            saw_field = True
            k += 1
            continue
        if not line.strip() or INDENT_RE.match(line) or RULE_RE.match(line):
            k += 1
            continue
        break
    if not saw_field:
        return body
    rest = lines[k:]
    while rest and not rest[0].strip():
        rest.pop(0)
    return _BLK.join(rest)


def _demote(soup):
    for lvl in range(5, 0, -1):
        for h in soup.find_all("h" + str(lvl)):
            h.name = "h" + str(min(lvl + 1, 6))


def _finalize(body):
    body = HEADING_LINK_RE.sub(lambda m: m.group(1) + " " + m.group(2), body)
    lines = body.split(_BLK)
    # 标题层级归一化：本镜像的 H1 是文档标题，正文标题从 H2 起连续编号。
    # 先收集围栏外的标题级别，再按出现顺序映射为 2,3,4,...，避免层级跳空。
    levels, inside = [], False
    for line in lines:
        if line.lstrip().startswith(FENCE):
            inside = not inside
            continue
        if inside:
            continue
        m = re.match(r"^(#{1,6})\s+\S", line)
        if m and len(m.group(1)) not in levels:
            levels.append(len(m.group(1)))
    mapping = {lv: i + 2 for i, lv in enumerate(sorted(levels))}
    out, inside = [], False
    for line in lines:
        if line.lstrip().startswith(FENCE):
            inside = not inside
        elif not inside:
            m = re.match(r"^(#{1,6})(\s+.*)$", line)
            if m:
                lv = mapping.get(len(m.group(1)), 6)
                line = "#" * lv + m.group(2)
        if line.lstrip().startswith("#"):
            out.append(line.rstrip())
            out.append("")
        elif line.strip() in ("* * *", "---"):
            continue
        else:
            out.append(line)
    body = _BLK.join(out)
    while (_BLK * 3) in body:
        body = body.replace(_BLK * 3, _BLK * 2)
    return body.strip() + _BLK


def tidy(body):
    """去掉每行行尾空白（仓库规范：不留行尾空白）。

    转换器会把「标题后的空行」变成行尾空格，PEP 257 的引文与 PO 译注也会留下空格；
    行尾空白在 Markdown 中语义为零，去掉不影响渲染。
    """
    return _BLK.join(line.rstrip() for line in body.split(_BLK))


def _heading(sec, fallback):
    h1 = sec.find("h1")
    if h1 is None:
        return fallback
    return re.sub(r"^PEP\s+\d+\s*[-–]\s*", "", _norm(h1.get_text(" ")))


def absolutize(soup, base):
    """把正文中的相对链接补成绝对 URL。

    引擎的链接改写按「绝对 URL -> 本地路径」匹配，而 PEP 正文用的是 ../pep-0007/ 这类
    相对地址；先补成绝对地址，改写阶段才能命中并改写为本地相对路径。
    """
    if not base:
        return soup
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        a["href"] = urljoin(base, href)
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if src and not src.startswith(("http", "data:")):
            img["src"] = urljoin(base, src)
    return soup


def pre_markdown(res, spec, ctx, to_markdown):
    """把站点 HTML 归一化为干净的 HTML 片段，交给引擎转换并改写链接。"""
    soup = BeautifulSoup(res["html"] or "", "html.parser")
    sec = soup.find("section", id="pep-content")
    if sec is not None:
        ctx["fields"] = _fields(sec)
        ctx["refs"] = _refs(sec)
        ctx["copyright"] = _copyright(sec)
        ctx["title"] = _heading(sec, ctx.get("title", ""))
        for tag in sec.find_all(["script", "style"]):
            tag.decompose()
        for a in sec.find_all("a", class_="headerlink"):
            a.decompose()
        toc = sec.find("section", id="contents")
        if toc:
            toc.decompose()
        for h in sec.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            for a in h.find_all("a"):
                a.replace_with(a.get_text())
        _demote(sec)
        absolutize(sec, ctx.get("source_url"))
        ctx["blocks"] = _fence(sec)
        return str(sec)

    ctx["fields"] = {}
    ctx["refs"] = []
    ctx["copyright"] = ""
    body = soup.find("main") or soup.find("article") or soup.body or soup
    for a in body.find_all("a", class_="headerlink"):
        a.decompose()
    for h in body.find_all(["h1", "h2"]):
        if _norm(h.get_text(" ")) == _norm(ctx.get("title", "")):
            h.decompose()
            break
    for h in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        for a in h.find_all("a"):
            a.replace_with(a.get_text())
    absolutize(body, ctx.get("source_url"))
    _demote(body)
    ctx["blocks"] = _fence(body)
    return str(body)


def post_markdown(md, res, spec, ctx):
    """引擎转换完成后的站点清洗：还原代码块、去重复元数据、补标题空行。"""
    md = _restore(md, ctx.get("blocks", []))
    md = _strip_meta_block(md)
    return tidy(_finalize(md))


def front_extra(res, spec, ctx):
    """写入 front matter 的站点特有字段。"""
    fields = ctx.get("fields") or {}
    out = []
    for key in META_KEYS:
        if fields.get(key):
            out.append((key.lower(), fields[key]))
    return out


def manifest_extra(ctx):
    """写入 manifest 的站点特有字段（版权、PEP 元数据、参考资料）。"""
    return {
        "pep_fields": ctx.get("fields") or {},
        "references": ctx.get("refs") or [],
    }

def manifests(url, spec):
    """给引擎的 manifest 条目补上 role / why 与站点特有字段。"""
    for item in targets():
        if item["url"] == url:
            return {"role": item["role"], "why": item["why"],
                    "extra": {"why": item["why"], "declared_source": item["source"]}}
    return {"role": "", "why": "", "extra": {}}


def _rel(from_path, to_path):
    import posixpath
    base = posixpath.dirname(from_path) or "."
    rel = posixpath.relpath(to_path, base)
    return rel if rel.startswith(".") else "./" + rel


def urlmap_extra(spec):
    """根文档在其它站点的等价地址：让站外引用也能落到本地文件。"""
    out = {}
    for item in targets():
        if item["source"] != item["url"]:
            out[item["source"]] = item["path"]
    return out

def pathmap():
    """来源 URL -> 本地相对路径。本地目录按「层级语义」命名，而非照抄 URL 数字。"""
    return {item["url"]: item["path"] for item in targets()}


def urlmap_extra(spec):
    """根文档在其它站点的等价地址：让站外引用也能落到本地文件。"""
    return {item["source"]: item["path"] for item in targets() if item["source"] != item["url"]}

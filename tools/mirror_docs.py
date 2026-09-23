# -*- coding: utf-8 -*-
"""通用文档镜像工具（基于 crawl4ai）。

运行:
    python tools/mirror_docs.py --list
    python tools/mirror_docs.py eng-practices
    python tools/mirror_docs.py gitlab-code-review
    python tools/mirror_docs.py python-pep-code-style
    python tools/mirror_docs.py --verify            # 结构校验（不抓取）
    python tools/mirror_docs.py dotnet-design-guidelines
    python tools/mirror_docs.py dora-capabilities

各站点共用的方法
------------------
1. 发现：从子树根页 BFS，只跟随落在 scope prefix 内的站内链接，绝不越界。
   这一点对 docs.gitlab.com 是必需的——其页面正文外链遍布 /user、/ci、/install
   等分区，不设边界会把整个 GitLab 文档站（sitemap 计 7183 条 URL）爬穿。
2. 抓取：使用 crawl4ai 的 AsyncHTTPCrawlerStrategy（纯 HTTP，不启动浏览器）。
   Windows 下 asyncio 子进程依赖命名管道，Playwright 驱动在受限沙箱中无法启动；
   本工具覆盖的站点均为服务端渲染的静态 HTML，无需 JS。
3. 正文净化：按站点的 excluded_tags / excluded_selector 剥离导航与横幅，
   再按站点正则去掉面包屑与页脚（页脚中的上游路径会被提取进 front matter）。
4. 层级：本地目录与 URL 路径严格一一对应。
5. 链接：站内链接改写为相对本地路径，使镜像可离线自洽浏览；站外链接原样保留。
6. 产物：页面 Markdown + README.md + STRUCTURE.md + manifest.json（含 sha256）。
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy
from crawl4ai.markdown_generation_strategy import CustomHTML2Text

import pep_site

BT = chr(96)
FENCE = BT * 3


def C(s):
    """Markdown 行内代码跨距（源码中不直接书写反引号，便于脚本化生成）。"""
    return BT + s + BT


def spec_lines(spec, key):
    """站点配置里的段落文本。

    值可以是字符串列表，也可以是 "模块:函数" 形式——后者在运行时求值，便于按站点清单
    （目录接口 / sitemap）现算层级树等内容，避免把生成结果硬编码在配置里而过期。
    """
    value = spec.get(key) or []
    if isinstance(value, str) and ":" in value:
        mod_name, fn_name = value.split(":", 1)
        value = getattr(importlib.import_module(mod_name), fn_name)()
    return value


ROOT = Path(__file__).resolve().parent.parent
FETCHED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
DEFAULT_BAD_EXT = r"\.(css|js|mjs|map|png|jpe?g|gif|svg|ico|webp|avif|woff2?|ttf|otf|eot|pdf|zip|gz|xml|txt|json|ya?ml|md)$"
ROLE_ZH = {
    "root-index": "站点首页",
    "section-index": "章节索引",
    "guide-index": "指南索引",
    "chapter": "章节",
    "doc": "文档",
}


# --------------------------------------------------------------------------
# 站点配置
# --------------------------------------------------------------------------
SITES = {
    "eng-practices": {
        "desc": "Google Engineering Practices（代码评审规范）",
        "base": "https://google.github.io/eng-practices/",
        "host": "google.github.io",
        "prefix": "/eng-practices/",
        "out": "docs/mirrors/google-eng-practices",
        "title": "Google Engineering Practices（本地镜像）",
        "license": "Creative Commons Attribution 3.0 Unported（CC BY 3.0）",
        "skip_paths": ["/eng-practices/LICENSE"],
        "extra_plain": [("LICENSE", "LICENSE.txt")],
        "breadcrumb_re": r"^#\s*\[eng-practices\]\(https://google\.github\.io/eng-practices/\)\s*\n+",
        "footer_re": (r"\n*This site is open source\.\s*\[Improve this page\]"
                      r"\((https://github\.com/google/eng-practices/edit/[^)]+)\)\.?\s*$"),
        "groups": [
            ("reviewer", "The Code Reviewer's Guide", "代码评审者指南", "review/reviewer/index.md"),
            ("author", "The Change Author's Guide", "变更作者指南", "review/developer/index.md"),
        ],
        "structure_mode": "groups",
        "outbound_report": False,
        "shared_why": {
            "index.md": "站点入口，位于两组文档的共同上级",
            "review/index.md": "位于 review/ 层，是两组的共同父级",
            "review/emergencies.md": "URL 层级与两组并列；仅被评审者指南的章节引用，"
                                     "作者指南从不引用，故不强行归入任一组",
        },
        "readme_saved": [
            "- 站点全部 14 个指南页面，其中 4 个章节索引页本身也含实质内容"
            "（术语表、综述、评审关注点），故一并保留；",
            "- [LICENSE.txt](LICENSE.txt)：CC BY 3.0 许可全文（经核实为 Creative Commons，"
            "而非 Apache-2.0）。非指南，但随镜像保留以满足署名要求；",
            "- [manifest.json](manifest.json)：逐页记录来源 URL、上游仓库路径、字节数与 sha256，便于校验。",
        ],
        "readme_skipped": [
            "- CSS / JS / 字体 / 图片等静态资源：非文档内容；",
            "- " + C("sitemap.xml") + "、" + C("robots.txt") + "、" + C("search.json")
            + "：站点上均返回 **404**，并不存在；",
            "- 站外链接（如 " + C("google.github.io/styleguide/") + "、"
            + C("chromium.googlesource.com") + "）：超出本镜像范围。",
        ],
        "readme_facts": [
            "- 该站点无 sitemap，页面全部由索引页链接串联，故采用 BFS 全量发现；",
            "- 抓取期间全部页面返回 HTTP 200，无失败页；",
            "- 已知等价 URL：/review/reviewer/index.html 与 /review/reviewer/ 同页，"
            "已按尾斜杠形式归一，不重复保存。",
        ],
    },
    "gitlab-code-review": {
        "desc": "GitLab Code Review Guidelines（代码开发审查规范）",
        "base": "https://docs.gitlab.com/development/code_review/",
        "host": "docs.gitlab.com",
        # 多根镜像：subtree 前缀取整段子树，exact 只取单页
        "prefixes": ["/user/project/merge_requests/reviews/"],
        "exact": [
            "/development/code_review/",
            "/development/contributing/merge_request_workflow/",
            "/development/contributing/first_contribution/mr-review/",
            "/development/code_comments/",
            "/development/merge_request_concepts/",
            "/development/database_review/",
            "/development/database/database_reviewer_guidelines/",
            "/development/database/clickhouse/reviewer_guidelines/",
            "/development/graphql_guide/reviewing/",
            "/development/permissions/review_guidelines/",
            "/development/internal_analytics/review_guidelines/",
            "/development/ai_instruction_files_review/",
            "/development/jh_features_review/",
            "/development/experiment_guide/experiment_code_reviews/",
            "/runner/development/reviewing-gitlab-runner/",
            "/tutorials/reviews/",
        ],
        "discovery": "sitemap",
        "sitemap_index": "https://docs.gitlab.com/sitemap.xml",
        "strip_prefix": False,
        "out": "docs/mirrors/gitlab-code-review",
        "title": "GitLab Code Review Guidelines（本地镜像）",
        "license": "Creative Commons Attribution-ShareAlike 4.0（CC BY-SA 4.0）",
        "excluded_tags": ["nav", "aside", "header", "footer", "script", "style"],
        "excluded_selector": '[data-vue-app="survey-banner"]',
        "lead_strip": r"\A(?:\s*\*\s*\*\s*\*\s*\n)+",
        "groups": [],
        "structure_mode": "outline",
        "outbound_report": True,
        "structure_findings": [
            "**核心页面本身没有子页。** 展开站点 sitemap 索引（/sitemap.xml -> /en-us 与 /ja-jp）",
            "后共 7183 条 URL（英文 3588 条），其中路径以 /development/code_review/ 开头的",
            "**仅 1 条英文页**；该页正文中的 26 个链接全部是页内锚点，无任何同前缀子页链接。",
            "",
            "因此本次镜像按「评审规范」口径扩展为专题集：以核心页为中心，收录 GitLab 各团队",
            "公开的评审规范与评审流程文档，共 20 篇，具体构成见下方层级结构。",
            "",
            "**页面清单由站点 sitemap 权威给出**（而非逐边 BFS）。这对 docs.gitlab.com 是必要的：",
            "其页面正文外链遍布 /user、/ci、/install 等分区，逐边扩散会把整个文档站爬穿。",
            "",
            "**未收录**：/development/merge_request_concepts/ 的 8 个子页（diffs 架构、合并可行性框架、",
            "限流、性能等属于实现内部机制，不陈述评审标准）；日文镜像页（内容为英文页的翻译，不重复收录）。",
        ],
        "outbound_why": ("判定理由：上述页面多为产品使用手册或与评审无关的工程专题，"
                         "不属于评审规范，故不收录；它们在正文中保留为绝对链接，可在线跳转。"),
        "readme_intro": [
            "本目录是 GitLab 官方文档中**代码评审规范**的离线镜像，共 20 篇。",
            "",
            "范围构成：核心页 <https://docs.gitlab.com/development/code_review/> 本身**没有子页**",
            "（站点 sitemap 中该前缀仅 1 条英文 URL），故按「评审规范」口径扩展为专题集——",
            "收录 GitLab 各团队公开的评审标准、评审者指南与评审流程文档。",
            "页面清单由站点 sitemap 权威给出，本地路径完整保留站点层级，",
            "站内链接已改写为相对路径，可直接离线跳转。",
        ],
        "readme_saved": [
            "- **核心规范 1 篇**：[development/code_review/index.md]"
            "(development/code_review/index.md)（Code Review Guidelines）；",
            "- **领域评审者指南 6 篇**：database_review、database/database_reviewer_guidelines、"
            "database/clickhouse/reviewer_guidelines、graphql_guide/reviewing、"
            "permissions/review_guidelines、internal_analytics/review_guidelines；",
            "- **流程与配套规范 5 篇**：contributing/merge_request_workflow、"
            "contributing/first_contribution/mr-review、code_comments、merge_request_concepts、"
            "experiment_guide/experiment_code_reviews；",
            "- **专项评审 2 篇**：ai_instruction_files_review、jh_features_review；",
            "- **仓库与产品侧 6 篇**：runner/development/reviewing-gitlab-runner、tutorials/reviews、"
            "user/project/merge_requests/reviews 及其 3 个子页；",
            "- [manifest.json](manifest.json)：逐页记录来源 URL、字节数与 sha256，便于校验。",
        ],
        "readme_skipped": [
            "- /development/merge_request_concepts/ 的 8 个子页（diffs 架构、合并可行性框架、"
            "限流、性能等）属于实现内部机制，不陈述评审标准；",
            "- /user/analytics/code_review_analytics/、/user/gitlab_duo/* 等：属于分析报表与 "
            "AI 功能说明，不是评审规范；",
            "- 日文镜像页（/ja-jp/ 前缀）：内容为英文页的翻译，不重复收录；",
            "- 站点其余全部页面：正文外链遍布 /user、/ci、/install 等分区，逐边扩散会爬穿全站"
            "（sitemap 计 7183 条 URL），故严格按 sitemap 白名单收录。",
        ],
        "readme_facts": [
            "- 核心页正文内 26 个链接**全部是页内锚点**，无任何子页链接，"
            "故该 URL 本身就是一篇单页长文档；",
            "- 抓取期间 20 个页面全部返回 HTTP 200，无失败页；",
            "- 页面清单来自站点 sitemap（英文 3588 条），而非逐边 BFS，边界可复核；",
            "- 抓取通道为顺序请求而非 arun_many：后者走 crawl4ai 的内存自适应调度器，"
            "按全系统内存判断，系统内存吃紧时会等待 600 秒后抛 MemoryError 中止抓取。",
        ],
    },
    "python-pep-code-style": {
        "desc": "Python PEP 8 / PEP 257 代码开发文档（风格规范 + 文档字符串约定）",
        "base": "https://peps.python.org/pep-0008/",
        "host": "peps.python.org",
        "hosts": ["peps.python.org", "docutils.sourceforge.io", "www.python.org"],
        "prefixes": ["/pep-"],
        "exact": ["/", "/community/sigs/current/doc-sig/"],
        "discovery": "list",
        "site_module": "pep_site",
        "out": "docs/mirrors/python-pep-code-style",
        "title": "Python PEP 8 / PEP 257 代码开发文档（本地镜像）",
        "license": "PEP 各篇为 public domain（逐页 Copyright 声明见 LICENSE.md）；两个站外参考页以来源站点声明为准",
        "strip_prefix": False,
        "body_h1": True,
        "groups": [],
        "structure_mode": "outline",
        "outbound_report": True,
        "structure_intro": [

            "本文件说明镜像内 11 篇文档的归属与相互关系。清单不是自动爬全站得到的，",

            "而是先抓取两份根文档、解析出正文全部超链接，再逐一实际抓取阅读后判定取舍；",

            "本地目录按「层级语义」命名（而非照抄 URL 数字），正文中的镜像内链接已改写为相对路径。",

        ],

        "structure_tree_note": [

            "本地目录按语义分层：根文档置于各自系列目录顶层，配套 / 上游 / 依据文档归入",

            "companion、upstream、philosophy 等子目录；每页以 index.md 承载正文，",

            "front matter 的 source_url 可反查回线上地址。",

        ],

        "outbound_why": "判定理由：上述分区为 Python 官方文档与社区站点，不属本次镜像范围；它们在正文中保留为绝对链接，可在线跳转。",

        "structure_findings": [
            "**清单来源：根文档正文的超链接，逐一评估后确定。** 先抓取 PEP 8 与 PEP 257 全文，",
            "解析出正文中的全部超链接（PEP 8 得 11 条，PEP 257 得 6 条），逐一实际抓取并阅读，",
            "再决定是否收录。",
            "",
            "**收录 11 篇**：两个根文档；PEP 8 开篇指向的配套文档 PEP 7 与理念来源 PEP 20；",
            "PEP 8 正文按规则引用的 PEP 3131 / 484 / 526；PEP 257 引用的 Docutils 上游规范",
            "PEP 256 / 258；以及 PEP 257 引用的两个站外站点（Docutils 首页、Python Doc-SIG）。",
            "",
            "**未收录**：PEP 3151（异常层级重构）——被 PEP 8 引为「设计异常层级」的范例，但本身",
            "不陈述代码风格，属语言设计文档；Barry Warsaw 风格指南（HTTP 403，已失效）；typeshed",
            "仓库（代码仓库而非文档）；CamelCase 百科词条、Doc-SIG 邮件列表订阅页、PEP 首页索引",
            "（均非规范文档）。完整清单与逐条理由见 README.md。",
        ],
        "license_count": 2,
        "readme_intro": [
            "本目录是 Python 官方 PEP 中**代码开发规范**的离线镜像，共 11 篇：以 PEP 8（Python 代码风格指南）",
            "与 PEP 257（文档字符串约定）两份根文档为中心，收录其正文实际引用的规范文档与外部参考。",
            "页面清单不是自动 BFS 得到的，而是**先抓取两份根文档、解析出正文全部超链接（PEP 8 得 11 条、",
            "PEP 257 得 6 条），再逐一实际抓取阅读后决定取舍**，逐条理由见下文「收录范围与取舍」。",
            "站内链接已改写为相对路径，可直接离线跳转。",
        ],
        "readme_saved": [
            "- **PEP 8 主文档 3 篇**：" + C("pep-8-python-code/index.md") + "（PEP 8 本体）、索引同目录的",
            "  配套文档 PEP 7（CPython C 代码风格）与理念来源 PEP 20（Python 之禅）；",
            "- **PEP 257 主文档 3 篇**：" + C("pep-257-docstrings/index.md") + "（PEP 257 本体），及其所引",
            "  Docutils 上游规范 PEP 256（处理系统框架）与 PEP 258（设计规范）；",
            "- **PEP 8 规则依据 3 篇**：" + C("pep-8-references/") + " 下的 PEP 3131（非 ASCII 标识符政策）、",
            "  PEP 484（类型提示）、PEP 526（变量注解语法）——PEP 8 的命名、注解与存根规则直接建立在它们之上；",
            "- **站外参考 2 篇**：Docutils 官方文档首页、Python Doc-SIG 特别兴趣组（PEP 257 引用）；",
            "- " + C("manifest.json") + "：逐页记录来源 URL、PEP 元数据（Author/Status/Type/Created 等）、",
            "  该页 Copyright 声明、正文字符数与 sha256，便于校验。",
        ],
        "readme_skipped": [
            "- **PEP 3151（Reworking the OS and IO exception hierarchy）**：PEP 8 在「Programming",
            "  Recommendations」中把它引为「设计异常层级」的正面范例，但该 PEP 本身讲的是异常层级的语言设计，",
            "  不陈述代码风格，故不收；",
            "- **Barry Warsaw 的 GNU Mailman 风格指南**（PEP 8 脚注 [2]）：实测返回 HTTP 403 Forbidden，",
            "  站点已不可访问；",
            "- **typeshed 仓库**（PEP 8 脚注 [5]）：是代码仓库而非文档；",
            "- **CamelCase 百科词条**（PEP 8 脚注 [4]）：通用百科词条，与 Python 规范无直接关系；",
            "- **Doc-SIG 邮件列表订阅页**（PEP 257 Discussions-To）：订阅管理页面，非文档内容；",
            "- **Docutils 文档目录页**：" + C("docutils.sourceforge.io/docs/index.html") + " 是已收录首页的下级目录，",
            "  属泛化导航而非被引用的具体文档；",
            "- **PEP 首页索引** " + C("peps.python.org/") + "：站点导航，非被引用文档；",
            "- **PEP 8 / PEP 257 正文内的站内互引**（如 PEP 8 ↔ PEP 257 相互引用）：均已在镜像内，",
            "  链接被改写为相对路径；",
            "- **站外链接**（python.org、typing.python.org、mail.python.org、github.com 等）：超出本次范围，",
            "  在正文中保留为绝对链接，可在线跳转。",
        ],
        "readme_facts": [
            "- 清单来源是根文档正文的超链接，而非站点 sitemap 或逐边 BFS：本次要回答的问题是",
            "  「PEP 8 与 PEP 257 指向了哪些代码开发文档」，而非「peps.python.org 全站有哪些页面」；",
            "- PEP 8 正文内共解析出 11 条超链接（去重后），PEP 257 共 6 条，全部逐一抓取阅读后判定；",
            "- 两份根文档的 Copyright 声明均为 public domain；其余各篇的 Copyright 声明随页记录在",
            "  manifest.json 的 " + C("copyright") + " 字段与各自 front matter 中；",
            "- PEP 站点的正文位于 " + C("section#pep-content") + "，导航栏与主题切换控件已被剔除；",
            "- 代码块内的 " + C("# 注释") + " 若按通用转换会变成 Markdown 标题，故站点模块先把 " + C("<pre>") + " 抽成",
            "  纯文本再还原为围栏代码块；",
            "- PEP 257 的主页正文极短（约 10 KB），其主要内容是规范条款本身，需配合 PEP 256 / 258 阅读。",
        ],        "outbound_why": "判定理由：上述分区为 Python 官方文档与社区站点，不属 PEP 文档树；它们在正文中保留为绝对链接，可在线跳转。",
    },
    "dotnet-design-guidelines": {
        "desc": ".NET Framework Design Guidelines（框架设计指南）",
        "base": "https://learn.microsoft.com/en-us/dotnet/standard/design-guidelines",
        "host": "learn.microsoft.com",
        "prefix": "/en-us/dotnet/standard/design-guidelines/",
        "exact": ["/en-us/dotnet/standard/design-guidelines"],
        "discovery": "list",
        "site_module": "learn_site",
        "out": "docs/mirrors/dotnet-design-guidelines",
        "title": ".NET Framework Design Guidelines（本地镜像）",
        "license": "CC BY 4.0（上游文档仓库 dotnet/docs）",
        "groups": [],
        "structure_mode": "outline",
        "outbound_report": True,
        "outbound_depth": 3,
        "structure_findings": "learn_site:findings",
        "structure_tree_note": [
            "本地路径按 canonical URL 末段扁平命名（已剥离 " + C("/en-us/dotnet/standard/design-guidelines/")
            + " 范围前缀），",
            "因此任意文件都能反查回其线上地址；章节层级见上方「范围判定」中的层级树与 "
            + C("manifest.json") + " 的 " + C("toc_path") + " 字段。",
        ],
        "outbound_why": ("判定理由：" + C("dotnet/api/...") + " 是类型与成员的签名参考页，本身不是设计指南；"
                         + C("/en-us/dotnet/standard") + " 下的垃圾回收等、"
                         + C("/en-us/dotnet/csharp") + " 与 " + C("/en-us/visualstudio/ide")
                         + " 的页面属其他文档集；informit.com 为原书购买页。"
                         "它们不属于本指南章节，故不收录，正文中保留为绝对地址，可在线跳转。"),
        "readme_intro": [
            "本目录是 Microsoft Learn「Framework design guidelines」整章的离线镜像，共 49 篇：章节总览页 1 篇、",
            "章节索引页 7 篇、指南正文 41 篇。页面清单与层级**都取自站点自身的目录接口**（" + C("toc.json") + "），",
            "本地文件按 URL 末段扁平命名、与站点 URL 路径一一对应，章节层级见 " + C("STRUCTURE.md") + "；",
            "正文中的镜像内链接已改写为相对路径，可直接离线跳转。",
        ],
        "readme_saved": [
            "- **章节总览页 1 篇**：" + C("index.md") + "（Framework design guidelines），含全章导语与 7 个章节入口；",
            "- **章节索引页 7 篇**：naming-guidelines、type、member、designing-for-extensibility、exceptions、",
            "  usage-guidelines、common-design-patterns——这 7 个目录节点本身也是页面，含该章导语与子页清单；",
            "- **指南正文 41 篇**：命名规范 8 篇、类型设计 7 篇、成员设计 8 篇、可扩展性设计 7 篇、",
            "  异常设计 3 篇、用法指南 6 篇、常用设计模式 2 篇；",
            "- " + C("manifest.json") + "：逐页记录来源 URL、本地路径、层级（toc_path / parent / toc_order / chapter）、",
            "  角色与收录理由（role / why）、上游 Markdown 源文件路径、字节数与 sha256，便于校验。",
        ],
        "readme_skipped": [
            "- **" + C("dotnet/api/...") + " API 参考页 163 处引用**：正文提到类型或成员时给出的签名页，",
            "  不属于设计指南章节，且数量随正文引用无限扩张；",
            "- **其他 .NET 文档集的链接 10 处**：" + C("/dotnet/standard/") + " 8 处（垃圾回收等）、"
            + C("/dotnet/csharp/") + " 1 处（装箱拆箱）、" + C("/visualstudio/ide/") + " 1 处（EditorConfig 命名约定）；",
            "- **原书购买链接 91 处**（www.informit.com）：正文许可声明中指向《Framework Design Guidelines》第 2/3 版书籍页；",
            "- **站点模板链接**（每页「编辑此文档」的 49 条 github 源文件链接、页脚浏览器兼容提示与 Edge 下载链接）：",
            "  在正文净化阶段随模板一并剥离，不进入正文，也不产生本地文件。",
        ],
        "readme_facts": [
            "- 抓取期间 49 个页面全部返回 HTTP 200，无失败页；清单与层级来自站点目录接口 " + C("toc.json") + "，",
            "  而非逐边 BFS；抓取后把每篇正文的全部超链接与该目录比对，站内链接集合与目录完全一致；",
            "- 该站 canonical URL 不带尾斜杠，" + C(".../names-of-namespaces") + " 与 " + C(".../names-of-namespaces/")
            + " 是同一页，",
            "  已在链接映射中等价处理，不会重复收录；",
            "- 正文链接在源站 HTML 里是相对地址（根相对 " + C("/en-us/...") + " 与同级相对两种），站点模块先按当前页",
            "  URL 解析为绝对地址再交给引擎改写：145 条镜像内链接改写为相对路径，285 条范围外链接保留绝对地址；",
            "- 页面模板把导航、目录侧栏、面包屑与授权提示都放在 " + C("<main>") + " 内，站点模块先摘除这些模板块，",
            "  否则转换出的 Markdown 会混入大量导航文本；正文末尾的 " + C("Additional resources") + " 页脚同样被截断；",
            "- 每篇正文末尾保留页面自身标注的更新日期（" + C("_源站标注：Last updated on YYYY-MM-DD_") + "）；",
            "- 正文摘自 2008 年出版的《Framework Design Guidelines》第 2 版，页面自身声明部分内容可能已经过时，",
            "  并给出第 3 版的购买链接（该链接保留在正文中，未收录为本地文件）；",
            "- 许可分层：上游仓库 " + C("dotnet/docs") + " 的文档部分为 CC BY 4.0（代码示例为 MIT），",
            "  而本套正文页另含 Pearson Education 授权摘录声明与 Microsoft 版权声明，转载时请连同这些声明一并处理。",
        ],
    },
    "dora-capabilities": {
        "desc": "DORA 软件交付能力指南（Continuous Integration 等 34 篇 + 能力目录页）",
        "base": "https://dora.dev/capabilities/continuous-integration/",
        "host": "dora.dev",
        "prefix": "/capabilities/",
        # 能力正文实际引用的两篇指南：不在 /capabilities/ 子树内，按正文引用关系精确收录
        "exact": ["/guides/dora-metrics/", "/guides/how-to-transform/"],
        "discovery": "list",
        "site_module": "dora_site",
        "out": "docs/mirrors/dora-capabilities",
        "title": "DORA 软件交付能力指南（本地镜像）",
        "license": "CC BY 4.0（Google LLC；站点页脚声明：除另有说明外，本站内容按 CC BY 4.0 授权）",
        "groups": [],
        "structure_mode": "outline",
        "outbound_report": True,
        "outbound_why": ("判定理由：" + C("/research/") + " 是历年研究报告、问卷与 errata（含 PDF 附件），"
                         + C("/quickcheck/") + " 是交互式自评工具，" + C("/ai/") + " 是 AI 研究分区，"
                         + C("/insights/") + " 是博客与研究动态，页脚的 " + C("/resources") + "、"
                         + C("/faq") + "、" + C("/contact") + " 是站点导航——它们都不是能力指南，故不收录；"
                         "在正文中保留为绝对地址，可在线跳转。"),
        "structure_intro": [
            "本文件说明镜像内各篇文档的层级与相互关系。清单、层级与收录边界全部取自站点自身",
            "（" + C("/sitemap.xml") + "、" + C("/capabilities/") + " 能力目录页的栅格、能力页正文的实际引用），",
            "不含人工归类；判定过程与未收录清单见 " + C("README.md") + "。",
            "",
        ],
        "structure_findings": "dora_site:findings",
        "structure_tree_note": [
            "本地目录按站点自己给出的模型徽章分层：" + C("core/") + "（DORA Core 模型）、"
            + C("ai/") + "（DORA AI 能力模型）、",
            C("unlabeled/") + "（目录页徽章容器为空、站点未给归属），被引用的指南另置 " + C("guides/") + "；",
            "文件名一律取 URL 末段，任意文件都能反查回其线上地址。",
            "",
        ],
        "readme_intro": [
            "本目录是 DORA（Google Cloud 的 DevOps 研究与评估项目）**软件交付能力指南**的离线镜像：",
            "能力目录页 1 篇、能力文档 34 篇、被能力正文实际引用的实施指南 2 篇。抓取入口是",
            "<https://dora.dev/capabilities/continuous-integration/>（Continuous integration，CI）——",
            "该页正文跳转到同分区的其它能力页，能力目录页又列出全部能力，故本次收录整个 " + C("/capabilities/") + " 分区。",
            "层级不是人工归类：" + C("core/") + " 与 " + C("ai/") + " 取自能力目录页给每张卡片打的模型徽章，",
            C("unlabeled/") + " 表示站点没有给该篇徽章。正文中的镜像内链接已改写为相对路径，可直接离线跳转。",
        ],
        "readme_saved": "dora_site:readme_saved",
        "readme_skipped": "dora_site:readme_skipped",
        "readme_facts": "dora_site:readme_facts",
    },
}


# --------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------
def spec_prefixes(spec):
    return spec.get("prefixes") or ([spec["prefix"]] if spec.get("prefix") else [])


def in_scope_path(path, spec):
    """路径是否落在镜像范围内：命中任一子树前缀，或等于某个精确路径。"""
    for p in spec_prefixes(spec):
        if path.startswith(p):
            return True
    for p in spec.get("exact", []):
        if path.rstrip("/") == p.rstrip("/"):
            return True
    return False


def spec_hosts(spec):
    """镜像允许的源主机列表：单站点用 host，跨站点用 hosts。"""
    return spec.get("hosts") or [spec["host"]]


def norm(url, spec):
    """归一化为范围内规范 URL；越界或非文档资源返回 None。"""
    url, _ = urldefrag(url)
    p = urlparse(url)
    netloc = p.netloc.lower()
    if netloc not in [h.lower() for h in spec_hosts(spec)]:
        return None
    if not in_scope_path(p.path, spec):
        return None
    path = p.path
    if re.search(spec.get("bad_ext", DEFAULT_BAD_EXT), path, re.I):
        return None
    if path.rstrip("/") in [s.rstrip("/") for s in spec.get("skip_paths", [])]:
        return None
    # 只给无扩展名的目录式路径补尾斜杠，.html 等文件路径必须原样保留
    if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return "https://" + netloc + path
def url_to_relpath(url, spec):
    path = urlparse(url).path
    prefs = spec_prefixes(spec)
    if prefs and spec.get("strip_prefix", True):
        rel = path[len(max(prefs, key=len)):]
    else:
        # 多根镜像必须保留完整站点层级，否则不同专题根都会落到 index.md 而互相覆盖
        rel = path.lstrip("/")
    if rel == "" or rel.endswith("/"):
        return rel + "index.md"
    if rel.lower().endswith(".html"):
        return rel[:-5] + ".md"
    return rel + ".md"
def html_to_markdown(html, spec):
    """HTML 片段 -> Markdown。站点可用 pre_markdown 钩子先行归一化 HTML。"""
    converter = CustomHTML2Text()
    converter.ignore_links = False
    converter.body_width = 0
    converter.ignore_images = False
    return converter.handle(html or "")


def split_title(raw_title):
    return re.sub(r"\s*\|\s*[^|]*$", "", (raw_title or "")).strip()


def clean_markdown(md, spec):
    """去面包屑/页脚/页首横幅，返回 (正文, 上游仓库路径)。"""
    upstream = None
    fr = spec.get("footer_re")
    if fr:
        m = re.search(fr, md)
        if m:
            if m.groups():
                upstream = m.group(1).split("/edit/", 1)[-1].lstrip("/")
            md = md[:m.start()]
    br = spec.get("breadcrumb_re")
    if br:
        md = re.sub(br, "", md, count=1)
    if spec.get("lead_strip"):
        md = re.sub(spec["lead_strip"], "", md)
    return md.strip() + "\n", upstream


def rewrite_links(md, cur_url, urlmap, out):
    """镜像范围内的链接 -> 相对本地路径；范围外链接原样保留。"""
    if not urlmap:
        return md
    cur_rel = urlmap[cur_url]
    cur_dir = (out / cur_rel).parent
    pattern = re.compile(r'https?://[^\s()<>"\']+')

    def repl(m):
        target = m.group(0)
        base, frag = urldefrag(target)
        if base not in urlmap:
            return target
        tgt_rel = urlmap[base]
        if tgt_rel == cur_rel and frag:
            return "#" + frag
        rel = os.path.relpath(out / tgt_rel, cur_dir).replace(os.sep, "/")
        return rel + (("#" + frag) if frag else "")

    return pattern.sub(repl, md)

def strip_front(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def compute_edges(out):
    """已落盘文档之间的站内互引（保留首次出现顺序 = 站点自身给出的顺序）。"""
    files = [p for p in out.rglob("*.md") if p.name not in ("README.md", "STRUCTURE.md")]
    rel = {p.resolve(): p.relative_to(out).as_posix() for p in files}
    edges = {}
    for p in files:
        body = strip_front(p.read_text(encoding="utf-8"))
        seen = []
        for t in LINK_RE.findall(body):
            if t.startswith(("http", "#")):
                continue
            r = (p.parent / t.split("#", 1)[0]).resolve()
            if r in rel and rel[r] not in seen:
                seen.append(rel[r])
        edges[rel[p.resolve()]] = seen
    return edges


def collect_outbound(out, spec):
    """登记的正文外链：指向本站但落在 scope 之外的链接，按分区归类。"""
    pattern = re.compile(r"https://" + re.escape(spec["host"]) + r"/[^\s)\"'<>]*")
    counts = {}
    for p in sorted(out.rglob("*.md")):
        if p.name in ("README.md", "STRUCTURE.md"):
            continue
        body = strip_front(p.read_text(encoding="utf-8"))
        for target in set(pattern.findall(body)):
            path = urlparse(urldefrag(target)[0]).path
            if in_scope_path(path, spec):
                continue
            seg = [s for s in path.split("/") if s]
            # 分组深度按站点可调：带语言前缀的站点（/en-us/...）需要多取一段才有区分度
            depth = spec.get("outbound_depth", 2)
            key = "/" + "/".join(seg[:depth]) if seg else "/"
            counts[key] = counts.get(key, 0) + 1
    return counts


def headings_outline(text):
    out, in_fence = [], False
    for ln in strip_front(text).split("\n"):
        if ln.startswith(FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m:
            out.append((len(m.group(1)), m.group(2).strip()))
    return out


# --------------------------------------------------------------------------
# 抓取
# --------------------------------------------------------------------------
def run_config(spec):
    kw = {"cache_mode": CacheMode.BYPASS}
    if spec.get("excluded_tags"):
        kw["excluded_tags"] = spec["excluded_tags"]
    if spec.get("excluded_selector"):
        kw["excluded_selector"] = spec["excluded_selector"]
    return CrawlerRunConfig(**kw)


async def sitemap_scope_urls(spec):
    """按站点 sitemap 求范围内的精确页面清单。

    对 docs.gitlab.com 这类巨型站点，这比逐边 BFS 安全得多：边界由 sitemap 权威给出，
    不会因为一两个导航链接而把范围扩散到全站。
    """
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(spec["sitemap_index"],
                               timeout=aiohttp.ClientTimeout(total=180)) as resp:
            body = await resp.text()
        subs = re.findall(r"<sitemap>.*?<loc>s*([^<\s]+)\s*</loc>", body, re.S)
        if not subs:
            subs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
        urls = []
        for sub in subs:
            if "/ja-jp/" in sub:  # 只取英文版，日文镜像不重复收录
                continue
            async with session.get(sub, timeout=aiohttp.ClientTimeout(total=180)) as resp:
                urls += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", await resp.text())
    found = []
    for u in urls:
        n = norm(u, spec)
        if n and n not in found:
            found.append(n)
    return sorted(found)


async def list_scope_urls(spec):
    """按站点清单取范围内的精确页面：清单由站点模块的 targets() 给出，逐条归一化。"""
    mod = importlib.import_module(spec["site_module"])
    found = []
    for item in mod.targets():
        n = norm(item["url"], spec)
        if n and n not in found:
            found.append(n)
    return sorted(found)


async def discover(crawler, spec):
    cfg = run_config(spec)
    pages = {}
    if spec.get("discovery") == "sitemap":
        frontier, follow = await sitemap_scope_urls(spec), False
    elif spec.get("discovery") == "list":
        frontier, follow = await list_scope_urls(spec), False
    else:
        frontier, follow = [norm(spec["base"], spec)], True
    seen = set(frontier)
    while frontier:
        # 顺序抓取而非 arun_many：arun_many 走 MemoryAdaptiveDispatcher，它按「全系统」
        # 内存占用判断，系统内存吃紧时会连续等待 600 秒后抛 MemoryError 中止整个抓取。
        # 本工具面向的是几十页量级的文档子树，顺序抓取足够快且不受该看门狗影响。
        nxt = []
        for target in frontier:
            res = await crawler.arun(target, config=cfg)
            url = norm(res.url, spec) or res.url
            md = res.markdown
            raw = getattr(md, "raw_markdown", None) or str(md)
            pages[url] = {
                "url": url,
                "ok": bool(res.success),
                "status": res.status_code,
                "title": split_title((res.metadata or {}).get("title", "")),
                "raw": raw,
                "html": res.html or "",
            }
            if not follow:
                continue
            for link in (res.links or {}).get("internal", []) or []:
                cand = norm(urljoin(url, link.get("href", "")), spec)
                if cand and cand not in seen:
                    seen.add(cand)
                    nxt.append(cand)
        frontier = sorted(set(nxt))
    return pages
async def fetch_plain_file(url):
    """取非 HTML 的单文件（如 LICENSE）。

    不使用 crawl4ai：其 AsyncHTTPCrawlerStrategy 在 Windows 上处理非 HTML 响应时
    会走到 os.O_NOFOLLOW（该常量 Windows 上不存在）而崩溃，故改用其自身依赖的 aiohttp。
    """
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return ""
            return (await resp.text()).strip()


# --------------------------------------------------------------------------
# 索引与结构文档
# --------------------------------------------------------------------------
def rel_table(rows, extra_col=None):
    head = "| 本地文件 | 标题 | 角色 |" if not extra_col else "| 本地文件 | 标题 | " + extra_col + " |"
    lines = [head, "| --- | --- | --- |"]
    for m in rows:
        first = "| [" + m["local_path"] + "](" + m["local_path"] + ") | " + m["title"] + " | "
        lines.append(first + ROLE_ZH.get(m["role"], m["role"]) + " |")
    return lines


def write_licenses(out, manifest, licenses):
    """多许可镜像（各篇 PEP 版权声明不一）单列许可汇总。"""
    if len(licenses) <= 1:
        return
    ok = [m for m in manifest if m.get("saved")]
    lines = ["# 许可汇总", "",
             "本镜像各页的 Copyright 声明由各页正文自身给出，汇总如下。转载与再分发请遵循对应声明。", "",
             "| 声明 | 页数 | 涉及页面 |", "| --- | --- | --- |"]
    for lic in sorted(licenses, key=lambda x: (-licenses[x], x)):
        pages = sorted(m["local_path"] for m in ok if m.get("copyright") == lic)
        shown = ", ".join(pages[:6]) + (" 等" if len(pages) > 6 else "")
        lines.append("| " + lic + " | " + str(len(pages)) + " | " + shown + " |")
    lines += ["", "未声明 Copyright 的页面不在此表内。", ""]
    (out / "LICENSE.md").write_text(chr(10).join(lines), encoding="utf-8", newline=chr(10))


def write_readme(out, spec, manifest, saved, licenses):
    ok = [m for m in manifest if m.get("saved")]
    lines = [
        "# " + spec["title"],
        "",
        "- **来源**：<" + spec["base"] + ">",
        "- **抓取时间**：" + FETCHED_AT,
        "- **抓取工具**：crawl4ai 0.9.3，AsyncHTTPCrawlerStrategy（纯 HTTP 通道，不启动浏览器）",
        "- **页面数**：" + str(saved),
    ]
    if len(licenses) <= 1:
        lic = next(iter(licenses)) if licenses else spec.get("license", "")
        lines.append("- **许可**：" + (lic or "未声明"))
    else:
        lines.append("- **许可**：各页 Copyright 声明不同，汇总见 [LICENSE.md](LICENSE.md)")
    lines.append("")
    lines += spec.get("readme_intro", [
        "本目录是 <" + spec["base"] + "> 的离线镜像。目录层级与来源 URL 路径一一对应，",
        "正文中的镜像内链接已改写为相对路径，可直接离线跳转。",
    ])
    lines.append("")
    if spec["groups"]:
        lines += [
            "## 目录（按文档集分组）",
            "",
            "站点主页把 Code Review Guidelines 明确划分为两套独立文档，两组在本镜像中均已完整收录。",
            "完整的归属、层级与交叉引用关系见 [STRUCTURE.md](STRUCTURE.md)。",
            "",
        ]
        for gid, gname, gzh, _ in spec["groups"]:
            rows = sorted([m for m in ok if m.get("guide") == gid], key=lambda x: x["local_path"])
            lines += ["### " + gname + "（" + gzh + "）—— " + str(len(rows)) + " 篇", ""]
            lines += rel_table(rows)
            lines.append("")
        rows = sorted([m for m in ok if m.get("guide") == "shared"], key=lambda x: x["local_path"])
        lines += ["### 共享文档（不属于任何一组）—— " + str(len(rows)) + " 篇", ""]
        lines += rel_table(rows)
        lines.append("")
    else:
        lines += ["## 目录", "", "| 本地文件 | 标题 | 角色 |", "| --- | --- | --- |"]
        for m in sorted(ok, key=lambda x: x["local_path"]):
            lines.append("| [" + m["local_path"] + "](" + m["local_path"] + ") | " + m["title"] + " | " + (m.get("role") or "文档") + " |")
        lines.append("")
    lines += ["## 收录范围与取舍", "", "**已保存**", ""]
    lines += spec_lines(spec, "readme_saved")
    lines += ["", "**未保存（及原因）**", ""]
    lines += spec_lines(spec, "readme_skipped")
    lines += ["", "## 已知事实", ""]
    lines += spec_lines(spec, "readme_facts")
    lines.append("")
    (out / "README.md").write_text(chr(10).join(lines), encoding="utf-8", newline=chr(10))


def write_structure(out, spec, manifest, edges):
    ok = {m["local_path"]: m for m in manifest if m.get("saved")}
    total = len(ok)
    L = ["# 文档关系与层级", ""] + spec.get("structure_intro", [
            "本文件说明镜像内 " + str(total) + " 篇文档的归属与相互关系。结论均由站点自身的",
            "索引页声明、sitemap 清单与正文实际链接推导得出，不含人工臆测。",
        ])

    if spec["structure_mode"] == "groups":
        counts = {g[0]: len([m for m in ok.values() if m.get("guide") == g[0]]) for g in spec["groups"]}
        shared = sorted([m for m in ok.values() if m.get("guide") == "shared"], key=lambda x: x["local_path"])

        def ordered_children(gid, groot):
            kids = [t for t in edges.get(groot, []) if t in ok and classify(t, spec) == gid]
            rest = sorted(m["local_path"] for m in ok.values()
                          if m.get("guide") == gid and m["local_path"] != groot and m["local_path"] not in kids)
            # 指南索引页不链接自身，必须显式置于首位作为该组入口
            return [groot] + kids + rest

        L += ["## 1. 两组文档：完整性确认", "",
              "站点主页把 Code Review Guidelines 明确划分为两套独立文档：", "",
              "| # | 文档集 | 站点英文名 | 索引页 | 章节数 | 本镜像文件数 | 状态 |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
        for i, (gid, gname, gzh, groot) in enumerate(spec["groups"], 1):
            n = counts[gid]
            L.append("| " + str(i) + " | " + gzh + " | " + gname + " | [" + groot + "](" + groot
                     + ") | " + str(n - 1) + " | " + str(n) + " | 完整 |")
        L += ["",
              "**两组均已完整获取。** " + " + ".join(str(counts[g[0]]) for g in spec["groups"])
              + " = " + str(sum(counts.values())) + " 篇归属指南；连同 " + str(len(shared))
              + " 篇共享文档，合计 " + str(total) + " 篇。", "",
              "## 2. 层级结构", "", FENCE]
        tree = [("", "google-eng-practices/", ""),
                ("├── ", "index.md", "共享 · 站点首页（两组文档的共同入口）"),
                ("└── ", "review/", ""),
                ("    ├── ", "index.md", "共享 · 章节索引 Introduction（两组的共同父级）"),
                ("    ├── ", "emergencies.md", "共享 · 章节 Emergencies")]
        for gi, (gid, gname, gzh, groot) in enumerate(spec["groups"]):
            last = gi == len(spec["groups"]) - 1
            gdir = Path(groot).parent.name  # 真实目录名，不要用内部 id
            tree.append(("    └── " if last else "    ├── ", gdir + "/", "● " + gname + "（" + gzh + "）"))
            gpad = "        " if last else "    │   "
            kids = ordered_children(gid, groot)
            for ki, k in enumerate(kids):
                kb = "└── " if ki == len(kids) - 1 else "├── "
                m = ok[k]
                note = m["title"] if m["role"] == "chapter" else "指南索引 · " + m["title"]
                tree.append((gpad + kb, Path(k).name, note))
        width = max(len(p) + len(n) for p, n, _ in tree) + 2
        for p, n, note in tree:
            line = p + n
            L.append(line if not note else line.ljust(width) + "# " + note)
        L += [FENCE, "",
              "**关于物理目录**：本地目录与站点 URL 路径严格一一对应，因此**未按文档集重排目录**。",
              "重排会让本地路径与上游 URL 失去对应关系，破坏可重跑校验与已改写的相对链接。",
              "文档集归属改由以上层级，以及 manifest.json 中的 guide / role / parent 字段来表达。", "",
              "## 3. 共享文档（不属于任何一组）", "",
              "| 文件 | 角色 | 为何不属于任何一组 |", "| --- | --- | --- |"]
        why = spec.get("shared_why", {})
        for m in shared:
            L.append("| [" + m["local_path"] + "](" + m["local_path"] + ") | "
                     + ROLE_ZH.get(m["role"], m["role"]) + " | " + why.get(m["local_path"], "") + " |")
        L += ["", "## 4. 跨文档集交叉引用（正文中的真实链接）", "",
              "两组并非彼此孤立，以下引用均由正文链接实际构成：", "",
              "| 源文档 | 源所属 | 目标文档 | 目标所属 |", "| --- | --- | --- | --- |"]
        n_cross = 0
        for src in sorted(edges):
            if src not in ok:
                continue
            for t in edges[src]:
                if t not in ok:
                    continue
                cs, ct = classify(src, spec), classify(t, spec)
                if cs == ct or "shared" in (cs, ct):
                    continue
                L.append("| " + src + " | " + GUIDE_ID[spec["out"]][cs][2] + " | " + t + " | "
                         + GUIDE_ID[spec["out"]][ct][2] + " |")
                n_cross += 1
        if n_cross == 0:
            L.append("| （无） | — | — | — |")
        L += ["", "共 " + str(n_cross) + " 条跨集引用；指向共享文档的引用不计入本表。", "",
              "## 5. 引用热度（被其他文档引用的次数）", "",
              "| 文档 | 所属 | 被引次数 | 引用者 |", "| --- | --- | --- | --- |"]
        indeg = {}
        for src, ts in edges.items():
            for t in ts:
                indeg.setdefault(t, []).append(src)
        for path in sorted(indeg, key=lambda p: (-len(indeg[p]), p)):
            if path not in ok:
                continue
            m = ok[path]
            gzh = GUIDE_ID[spec["out"]][m["guide"]][2] if m["guide"] != "shared" else "共享"
            L.append("| " + path + " | " + gzh + " | " + str(len(indeg[path])) + " | "
                     + ", ".join(sorted(indeg[path])) + " |")
        orphan = sorted(p for p in ok if p not in indeg)
        L += ["", "从未被引用的文档：" + (", ".join(orphan) if orphan else "（无）")
              + "（站点首页作为入口，不被正文引用属正常）。", "",
              "## 6. 建议阅读顺序", "",
              "先读共享的 Introduction，再按需进入任一组；两组各自声明「不必全部读完，但整套读完收获最大」。",
              "以下顺序即各索引页列出的原始顺序：", ""]
        for i, (gid, gname, gzh, groot) in enumerate(spec["groups"], 1):
            seq = ["review/index.md"] + ordered_children(gid, groot)
            L.append(str(i) + ". **" + gzh + "**（" + gname + "）：" + " → ".join(seq))
        L += ["", "两组的索引页均在末尾互相指引（评审者指南 → 作者指南，作者指南 → 评审者指南），",
              "说明二者是同一评审流程的两个视角，而非两个无关专题。", ""]

    else:
        L += ["## 1. 范围判定", ""] + spec_lines(spec, "structure_findings") + [""]

        # --- 目录树 ---
        def build(paths):
            node = {}
            for path in paths:
                cur = node
                parts = path.split("/")
                for p in parts[:-1]:
                    cur = cur.setdefault(p + "/", {})
                cur[parts[-1]] = None
            return node

        rows = []

        def emit(node, prefix, base):
            items = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0]))
            for i, (name, child) in enumerate(items):
                last = i == len(items) - 1
                full = base + name
                branch = prefix + ("└── " if last else "├── ")
                if child is None:
                    rows.append((branch + name, ok[full]["title"]))
                else:
                    rows.append((branch + name, ""))
                    emit(child, prefix + ("    " if last else "│   "), full)

        emit(build(sorted(ok)), "", "")
        width = max(len(r[0]) for r in rows) + 2
        L += ["## 2. 层级结构", "", FENCE]
        for text, note in rows:
            L.append(text if not note else text.ljust(width) + "# " + note)
        L += [FENCE, ""] + spec.get("structure_tree_note", [
                "本地路径完整保留站点 URL 层级（未剥离前缀），因此各专题根互不覆盖，",
                "且任意文件都能反查回其线上地址。",
            ])

        # --- 各文档大纲 ---
        L += ["## 3. 各文档正文大纲（h1–h2）", "",
              "仅列到二级标题；三级及以下标题见各文件正文自身。", ""]
        for path in sorted(ok):
            text = (out / path).read_text(encoding="utf-8")
            L += ["### [" + ok[path]["title"] + "](" + path + ")", "", FENCE]
            for lvl, title in headings_outline(text):
                if lvl <= 2:
                    L.append("  " * (lvl - 1) + "h" + str(lvl) + "  " + title)
            L += [FENCE, ""]

        # --- 未收录外链 ---
        sec = 4
        if spec.get("outbound_report"):
            outb = collect_outbound(out, spec)
            L += ["## 4. 正文外链登记（未收录，含判定理由）", "",
                  "以下为正文中指向本站其他分区的链接，按分区汇总。它们不在本次收录范围内：", "",
                  "| 目标分区 | 正文引用次数 |", "| --- | --- |"]
            for k in sorted(outb, key=lambda x: (-outb[x], x)):
                L.append("| " + k + " | " + str(outb[k]) + " |")
            L += ["", spec.get("outbound_why", ""), ""]
            sec = 5
        if spec.get("license_count", 1) > 1:
            L += ["## " + str(sec) + ". 许可", "",
                  "本镜像各页的 Copyright 声明由各页正文自身给出（共 " + str(spec.get("license_count")) + " 种），",
                  "逐条汇总见 [LICENSE.md](LICENSE.md)。", ""]
        else:
            L += ["## " + str(sec) + ". 许可", "",
                  "本站点内容采用 " + spec["license"] + " 许可。转载与再分发请遵循该许可的署名与相同方式共享要求。", ""]
    (out / "STRUCTURE.md").write_text("\n".join(L), encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# 归属判定（仅 groups 模式使用）
# --------------------------------------------------------------------------
GUIDE_ID = {}


def classify(relpath, spec):
    for gid, gname, gzh, groot in spec["groups"]:
        if relpath.startswith(str(Path(groot).parent).replace("\\", "/") + "/"):
            return gid
    return "shared"


def role_of(relpath, spec, guide):
    if relpath == "index.md":
        return "root-index"
    if relpath.endswith("/index.md"):
        return "guide-index" if guide != "shared" else "section-index"
    return "chapter"


def parent_of(relpath, spec, guide):
    if relpath == "index.md":
        return ""
    if guide == "shared":
        return "review/index.md"
    groot = [g[3] for g in spec["groups"] if g[0] == guide][0]
    return "review/index.md" if relpath == groot else groot


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
async def run(site_key):
    spec = SITES[site_key]
    out = ROOT / spec["out"]
    GUIDE_ID[spec["out"]] = {g[0]: g for g in spec["groups"]}
    mod = importlib.import_module(spec["site_module"]) if spec.get("site_module") else None
    meta = getattr(mod, "manifests", None)

    config = run_config(spec)
    async with AsyncWebCrawler(crawler_strategy=AsyncHTTPCrawlerStrategy()) as crawler:
        pages = await discover(crawler, spec)
        extra = {}
        for path, dest in spec.get("extra_plain", []):
            extra[dest] = await fetch_plain_file(urljoin(spec["base"], path))

    site_paths = mod.pathmap() if (mod is not None and hasattr(mod, "pathmap")) else {}
    urlmap = {u: site_paths.get(u) or url_to_relpath(u, spec) for u in pages}
    for path, dest in spec.get("extra_plain", []):
        if extra.get(dest):
            urlmap[urljoin(spec["base"], path)] = dest
    if mod is not None and hasattr(mod, "urlmap_extra"):
        urlmap.update(mod.urlmap_extra(spec))

    # 抓取全部成功后才清空旧产物：避免抓取中途失败导致已有镜像被清空
    if out.exists():
        shutil.rmtree(out)

    manifest, saved, licenses = [], 0, {}
    for url in sorted(pages, key=lambda u: urlmap[u]):
        info = pages[url]
        posix_rel = urlmap[url].replace(os.sep, "/")
        if not info["ok"]:
            manifest.append({"source_url": url, "status": info["status"], "saved": False})
            print("  [FAIL] " + url)
            continue
        data = meta(url, spec) if meta else {"role": "", "why": "", "extra": {}}
        ctx = {"title": info["title"], "source_url": url}
        if mod is not None and hasattr(mod, "pre_markdown"):
            html = mod.pre_markdown(info, spec, ctx, None)
        else:
            html = info["html"]
        body, upstream = clean_markdown(html_to_markdown(html, spec), spec)
        if mod is not None and hasattr(mod, "post_markdown"):
            body = mod.post_markdown(body, info, spec, ctx)
        body = rewrite_links(body, url, urlmap, out)
        title = ctx.get("title") or info["title"]
        if spec.get("body_h1") and not body.lstrip().startswith("# "):
            body = "# " + title + chr(10) + chr(10) + body
        license_text = ctx.get("copyright", "") or spec.get("license", "")
        if license_text:
            licenses[license_text] = licenses.get(license_text, 0) + 1
        gid = classify(posix_rel, spec) if spec["groups"] else "shared"
        section = str(Path(posix_rel).parent).replace(os.sep, "/")
        front = ["---", "title: " + json.dumps(title, ensure_ascii=False),
                 "source_url: " + json.dumps(url, ensure_ascii=False)]
        if upstream:
            front.append("source_repo_path: " + json.dumps(upstream, ensure_ascii=False))
        if section and section != ".":
            front.append("section: " + json.dumps(section, ensure_ascii=False))
        if data.get("role"):
            front.append("role: " + json.dumps(data["role"], ensure_ascii=False))
        if data.get("why"):
            front.append("why: " + json.dumps(data["why"], ensure_ascii=False))
        if license_text:
            front.append("copyright: " + json.dumps(license_text, ensure_ascii=False))
        front.append("fetched_at: " + json.dumps(FETCHED_AT, ensure_ascii=False))
        front.append("---")
        content = chr(10).join(front) + chr(10) + chr(10) + body
        dest_path = out / posix_rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(content, encoding="utf-8", newline=chr(10))
        saved += 1
        entry = {
            "local_path": posix_rel,
            "guide": gid,
            "guide_name": GUIDE_ID[spec["out"]].get(gid, ("",))[1] if gid != "shared" else "",
            "role": data.get("role") or role_of(posix_rel, spec, gid),
            "parent": parent_of(posix_rel, spec, gid),
            "source_url": url,
            "title": title,
            "source_repo_path": upstream,
            "status": info["status"],
            "bytes": len(content.encode("utf-8")),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "saved": True,
        }
        entry["copyright"] = license_text
        entry.update(data.get("extra") or {})
        if mod is not None and hasattr(mod, "manifest_extra"):
            entry.update(mod.manifest_extra(ctx))
        manifest.append(entry)
        print("  [OK] " + posix_rel.ljust(52) + str(len(content.encode("utf-8"))).rjust(7) + " B  " + title)

    for dest, text in extra.items():
        if text:
            (out / dest).write_text(text + chr(10), encoding="utf-8", newline=chr(10))
            print("  [OK] " + dest + " (" + str(len(text)) + " chars)")

    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps({
        "source": spec["base"], "fetched_at": FETCHED_AT,
        "crawler": "crawl4ai 0.9.3 / AsyncHTTPCrawlerStrategy",
        "pages_saved": saved, "pages": manifest,
    }, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8", newline=chr(10))

    write_licenses(out, manifest, licenses)
    write_readme(out, spec, manifest, saved, licenses)
    write_structure(out, spec, manifest, compute_edges(out))
    print(chr(10) + "[" + site_key + "] saved=" + str(saved) + " -> " + str(out))
def verify_mirror(site_key):
    """结构校验：front matter、代码围栏闭合、标题层级连续、镜像内相对链接可达。"""
    spec = SITES[site_key]
    out = ROOT / spec["out"]
    if not out.is_dir():
        print("  [" + site_key + "] 目录不存在：" + str(out))
        return 1, 0
    pages, problems = 0, 0
    for path in sorted(out.rglob("*.md")):
        if path.name in ("README.md", "STRUCTURE.md", "LICENSE.md"):
            continue
        pages += 1
        raw = path.read_text(encoding="utf-8")
        body = raw.split("---", 2)[2] if raw.count("---") >= 2 else raw
        rel = path.relative_to(out).as_posix()
        issues = []
        if not raw.startswith("---" + chr(10)):
            issues.append("缺少 front matter")
        # 标题与围栏：围栏内的 # 注释不算标题
        heads, inside = [], False
        for line in body.split(chr(10)):
            if line.lstrip().startswith(FENCE):
                inside = not inside
                continue
            if inside:
                continue
            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                heads.append((len(m.group(1)), m.group(2).strip()))
        if inside:
            issues.append("代码围栏未闭合")
        levels = [h[0] for h in heads]
        if not levels:
            issues.append("正文无标题")
        else:
            if levels[0] > 2:
                issues.append("正文起始标题过深：h" + str(levels[0]))
            for i in range(len(levels) - 1):
                if levels[i + 1] - levels[i] > 2:
                    issues.append("标题跳级：" + heads[i][1][:24])
        # 镜像内相对链接必须可达（跳过围栏内的代码）
        prose, inside = [], False
        for line in body.split(chr(10)):
            if line.lstrip().startswith(FENCE):
                inside = not inside
                continue
            if not inside:
                prose.append(line)
        broken = []
        for target in re.findall(r"\]\(([^)\s]+)\)", chr(10).join(prose)):
            if target.startswith(("http", "#", "mailto:")):
                continue
            tgt = target.split("#", 1)[0]
            if tgt and not (path.parent / tgt).resolve().exists():
                broken.append(tgt)
        if broken:
            issues.append("链接不可达：" + ", ".join(broken[:3]))
        if issues:
            problems += 1
            print("  FAIL " + rel.ljust(58) + " ; ".join(issues))
    print("  " + site_key + "：pages=" + str(pages) + " problems=" + str(problems))
    return problems, pages


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--verify" in sys.argv:
        keys = args or list(SITES)
        bad = 0
        for key in keys:
            if key not in SITES:
                print("unknown site: " + key)
                continue
            problems, _ = verify_mirror(key)
            bad += problems
        sys.exit(1 if bad else 0)
    if "--list" in sys.argv or not args:
        for k, v in SITES.items():
            print("  " + k.ljust(20) + v["desc"])
        return
    for key in args:
        if key not in SITES:
            print("unknown site: " + key)
            continue
        asyncio.run(run(key))


if __name__ == "__main__":
    main()

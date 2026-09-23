# Python PEP 8 / PEP 257 代码开发文档（本地镜像）

- **来源**：<https://peps.python.org/pep-0008/>
- **抓取时间**：2026-09-16T08:03:19Z
- **抓取工具**：crawl4ai 0.9.3，AsyncHTTPCrawlerStrategy（纯 HTTP 通道，不启动浏览器）
- **页面数**：11
- **许可**：各页 Copyright 声明不同，汇总见 [LICENSE.md](LICENSE.md)

本目录是 Python 官方 PEP 中**代码开发规范**的离线镜像，共 11 篇：以 PEP 8（Python 代码风格指南）
与 PEP 257（文档字符串约定）两份根文档为中心，收录其正文实际引用的规范文档与外部参考。
页面清单不是自动 BFS 得到的，而是**先抓取两份根文档、解析出正文全部超链接（PEP 8 得 11 条、
PEP 257 得 6 条），再逐一实际抓取阅读后决定取舍**，逐条理由见下文「收录范围与取舍」。
站内链接已改写为相对路径，可直接离线跳转。

## 目录

| 本地文件 | 标题 | 角色 |
| --- | --- | --- |
| [pep-257-docstrings/index.md](pep-257-docstrings/index.md) | Docstring Conventions | PEP 257 - Docstring Conventions |
| [pep-257-docstrings/upstream/pep-256-docstring-framework/index.md](pep-257-docstrings/upstream/pep-256-docstring-framework/index.md) | Docstring Processing System Framework | PEP 256 - Docstring Processing System Framework |
| [pep-257-docstrings/upstream/pep-258-docutils-design/index.md](pep-257-docstrings/upstream/pep-258-docutils-design/index.md) | Docutils Design Specification | PEP 258 - Docutils Design Specification |
| [pep-8-python-code/companion/pep-7-c-code/index.md](pep-8-python-code/companion/pep-7-c-code/index.md) | Style Guide for C Code | PEP 7 - Style Guide for C Code |
| [pep-8-python-code/index.md](pep-8-python-code/index.md) | Style Guide for Python Code | PEP 8 - Style Guide for Python Code |
| [pep-8-python-code/philosophy/pep-20-zen/index.md](pep-8-python-code/philosophy/pep-20-zen/index.md) | The Zen of Python | PEP 20 - The Zen of Python |
| [pep-8-references/pep-3131-non-ascii-identifiers/index.md](pep-8-references/pep-3131-non-ascii-identifiers/index.md) | Supporting Non-ASCII Identifiers | PEP 3131 - Supporting Non-ASCII Identifiers |
| [pep-8-references/pep-484-type-hints/index.md](pep-8-references/pep-484-type-hints/index.md) | Type Hints | PEP 484 - Type Hints |
| [pep-8-references/pep-526-variable-annotations/index.md](pep-8-references/pep-526-variable-annotations/index.md) | Syntax for Variable Annotations | PEP 526 - Syntax for Variable Annotations |
| [references/doc-sig/index.md](references/doc-sig/index.md) | Doc-SIG - Python Documentation Special Interest Group | Python Doc-SIG 特别兴趣组 |
| [references/docutils/index.md](references/docutils/index.md) | Docutils: Documentation Utilities | Docutils 官方文档首页 |

## 收录范围与取舍

**已保存**

- **PEP 8 主文档 3 篇**：`pep-8-python-code/index.md`（PEP 8 本体）、索引同目录的
  配套文档 PEP 7（CPython C 代码风格）与理念来源 PEP 20（Python 之禅）；
- **PEP 257 主文档 3 篇**：`pep-257-docstrings/index.md`（PEP 257 本体），及其所引
  Docutils 上游规范 PEP 256（处理系统框架）与 PEP 258（设计规范）；
- **PEP 8 规则依据 3 篇**：`pep-8-references/` 下的 PEP 3131（非 ASCII 标识符政策）、
  PEP 484（类型提示）、PEP 526（变量注解语法）——PEP 8 的命名、注解与存根规则直接建立在它们之上；
- **站外参考 2 篇**：Docutils 官方文档首页、Python Doc-SIG 特别兴趣组（PEP 257 引用）；
- `manifest.json`：逐页记录来源 URL、PEP 元数据（Author/Status/Type/Created 等）、
  该页 Copyright 声明、正文字符数与 sha256，便于校验。

**未保存（及原因）**

- **PEP 3151（Reworking the OS and IO exception hierarchy）**：PEP 8 在「Programming
  Recommendations」中把它引为「设计异常层级」的正面范例，但该 PEP 本身讲的是异常层级的语言设计，
  不陈述代码风格，故不收；
- **Barry Warsaw 的 GNU Mailman 风格指南**（PEP 8 脚注 [2]）：实测返回 HTTP 403 Forbidden，
  站点已不可访问；
- **typeshed 仓库**（PEP 8 脚注 [5]）：是代码仓库而非文档；
- **CamelCase 百科词条**（PEP 8 脚注 [4]）：通用百科词条，与 Python 规范无直接关系；
- **Doc-SIG 邮件列表订阅页**（PEP 257 Discussions-To）：订阅管理页面，非文档内容；
- **Docutils 文档目录页**：`docutils.sourceforge.io/docs/index.html` 是已收录首页的下级目录，
  属泛化导航而非被引用的具体文档；
- **PEP 首页索引** `peps.python.org/`：站点导航，非被引用文档；
- **PEP 8 / PEP 257 正文内的站内互引**（如 PEP 8 ↔ PEP 257 相互引用）：均已在镜像内，
  链接被改写为相对路径；
- **站外链接**（python.org、typing.python.org、mail.python.org、github.com 等）：超出本次范围，
  在正文中保留为绝对链接，可在线跳转。

## 已知事实

- 清单来源是根文档正文的超链接，而非站点 sitemap 或逐边 BFS：本次要回答的问题是
  「PEP 8 与 PEP 257 指向了哪些代码开发文档」，而非「peps.python.org 全站有哪些页面」；
- PEP 8 正文内共解析出 11 条超链接（去重后），PEP 257 共 6 条，全部逐一抓取阅读后判定；
- 两份根文档的 Copyright 声明均为 public domain；其余各篇的 Copyright 声明随页记录在
  manifest.json 的 `copyright` 字段与各自 front matter 中；
- PEP 站点的正文位于 `section#pep-content`，导航栏与主题切换控件已被剔除；
- 代码块内的 `# 注释` 若按通用转换会变成 Markdown 标题，故站点模块先把 `<pre>` 抽成
  纯文本再还原为围栏代码块；
- PEP 257 的主页正文极短（约 10 KB），其主要内容是规范条款本身，需配合 PEP 256 / 258 阅读。

# Google Engineering Practices（本地镜像）

- **来源**：<https://google.github.io/eng-practices/>
- **抓取时间**：2026-09-16T07:44:26Z
- **抓取工具**：crawl4ai 0.9.3，AsyncHTTPCrawlerStrategy（纯 HTTP 通道，不启动浏览器）
- **页面数**：14
- **许可**：Creative Commons Attribution 3.0 Unported（CC BY 3.0），见 [LICENSE.txt](LICENSE.txt)

本目录是 <https://google.github.io/eng-practices/> 的离线镜像。目录层级与站点 URL 路径一一对应，
正文中的站内链接已改写为相对路径，可直接离线跳转。

## 目录（按文档集分组）

站点主页把 Code Review Guidelines 明确划分为两套独立文档，两组在本镜像中均已完整收录。
完整的归属、层级与交叉引用关系见 [STRUCTURE.md](STRUCTURE.md)。

### The Code Reviewer's Guide（代码评审者指南）—— 7 篇

| 本地文件 | 标题 | 角色 |
| --- | --- | --- |
| [review/reviewer/comments.md](review/reviewer/comments.md) | How to write code review comments | 章节 |
| [review/reviewer/index.md](review/reviewer/index.md) | How to do a code review | 指南索引 |
| [review/reviewer/looking-for.md](review/reviewer/looking-for.md) | What to look for in a code review | 章节 |
| [review/reviewer/navigate.md](review/reviewer/navigate.md) | Navigating a CL in review | 章节 |
| [review/reviewer/pushback.md](review/reviewer/pushback.md) | Handling pushback in code reviews | 章节 |
| [review/reviewer/speed.md](review/reviewer/speed.md) | Speed of Code Reviews | 章节 |
| [review/reviewer/standard.md](review/reviewer/standard.md) | The Standard of Code Review | 章节 |

### The Change Author's Guide（变更作者指南）—— 4 篇

| 本地文件 | 标题 | 角色 |
| --- | --- | --- |
| [review/developer/cl-descriptions.md](review/developer/cl-descriptions.md) | Writing good CL descriptions | 章节 |
| [review/developer/handling-comments.md](review/developer/handling-comments.md) | How to handle reviewer comments | 章节 |
| [review/developer/index.md](review/developer/index.md) | The CL author’s guide to getting through code review | 指南索引 |
| [review/developer/small-cls.md](review/developer/small-cls.md) | Small CLs | 章节 |

### 共享文档（不属于任何一组）—— 3 篇

| 本地文件 | 标题 | 角色 |
| --- | --- | --- |
| [index.md](index.md) | Google Engineering Practices Documentation | 站点首页 |
| [review/emergencies.md](review/emergencies.md) | Emergencies | 章节 |
| [review/index.md](review/index.md) | Introduction {#intro} | 章节索引 |

## 收录范围与取舍

**已保存**

- 站点全部 14 个指南页面，其中 4 个章节索引页本身也含实质内容（术语表、综述、评审关注点），故一并保留；
- [LICENSE.txt](LICENSE.txt)：CC BY 3.0 许可全文（经核实为 Creative Commons，而非 Apache-2.0）。非指南，但随镜像保留以满足署名要求；
- [manifest.json](manifest.json)：逐页记录来源 URL、上游仓库路径、字节数与 sha256，便于校验。

**未保存（及原因）**

- CSS / JS / 字体 / 图片等静态资源：非文档内容；
- `sitemap.xml`、`robots.txt`、`search.json`：站点上均返回 **404**，并不存在；
- 站外链接（如 `google.github.io/styleguide/`、`chromium.googlesource.com`）：超出本镜像范围。

## 已知事实

- 该站点无 sitemap，页面全部由索引页链接串联，故采用 BFS 全量发现；
- 抓取期间全部页面返回 HTTP 200，无失败页；
- 已知等价 URL：/review/reviewer/index.html 与 /review/reviewer/ 同页，已按尾斜杠形式归一，不重复保存。

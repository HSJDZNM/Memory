# GitLab Code Review Guidelines（本地镜像）

- **来源**：<https://docs.gitlab.com/development/code_review/>
- **抓取时间**：2026-09-16T07:45:06Z
- **抓取工具**：crawl4ai 0.9.3，AsyncHTTPCrawlerStrategy（纯 HTTP 通道，不启动浏览器）
- **页面数**：20
- **许可**：Creative Commons Attribution-ShareAlike 4.0（CC BY-SA 4.0）

本目录是 GitLab 官方文档中**代码评审规范**的离线镜像，共 20 篇。

范围构成：核心页 <https://docs.gitlab.com/development/code_review/> 本身**没有子页**
（站点 sitemap 中该前缀仅 1 条英文 URL），故按「评审规范」口径扩展为专题集——
收录 GitLab 各团队公开的评审标准、评审者指南与评审流程文档。
页面清单由站点 sitemap 权威给出，本地路径完整保留站点层级，
站内链接已改写为相对路径，可直接离线跳转。

## 目录

| 本地文件 | 标题 |
| --- | --- |
| [development/ai_instruction_files_review/index.md](development/ai_instruction_files_review/index.md) | Reviewing GitLab AI instruction files |
| [development/code_comments/index.md](development/code_comments/index.md) | Code comments |
| [development/code_review/index.md](development/code_review/index.md) | Code Review Guidelines |
| [development/contributing/first_contribution/mr-review/index.md](development/contributing/first_contribution/mr-review/index.md) | Create a merge request |
| [development/contributing/merge_request_workflow/index.md](development/contributing/merge_request_workflow/index.md) | Merge requests workflow |
| [development/database/clickhouse/reviewer_guidelines/index.md](development/database/clickhouse/reviewer_guidelines/index.md) | ClickHouse reviewer guidelines |
| [development/database/database_reviewer_guidelines/index.md](development/database/database_reviewer_guidelines/index.md) | Database Reviewer Guidelines |
| [development/database_review/index.md](development/database_review/index.md) | Database Review Guidelines |
| [development/experiment_guide/experiment_code_reviews/index.md](development/experiment_guide/experiment_code_reviews/index.md) | Experiment code reviews |
| [development/graphql_guide/reviewing/index.md](development/graphql_guide/reviewing/index.md) | GraphQL API merge request checklist |
| [development/internal_analytics/review_guidelines/index.md](development/internal_analytics/review_guidelines/index.md) | Internal Analytics review guidelines |
| [development/jh_features_review/index.md](development/jh_features_review/index.md) | Guidelines for reviewing JiHu (JH) Edition related merge requests |
| [development/merge_request_concepts/index.md](development/merge_request_concepts/index.md) | Merge request concepts |
| [development/permissions/review_guidelines/index.md](development/permissions/review_guidelines/index.md) | Authorization code review guidelines |
| [runner/development/reviewing-gitlab-runner/index.md](runner/development/reviewing-gitlab-runner/index.md) | Reviewing GitLab Runner |
| [tutorials/reviews/index.md](tutorials/reviews/index.md) | Tutorial: Review a merge request |
| [user/project/merge_requests/reviews/automatic_reviewer_assignment/index.md](user/project/merge_requests/reviews/automatic_reviewer_assignment/index.md) | Automatic reviewer assignment |
| [user/project/merge_requests/reviews/index.md](user/project/merge_requests/reviews/index.md) | Merge request reviews |
| [user/project/merge_requests/reviews/stacked_merge_requests/index.md](user/project/merge_requests/reviews/stacked_merge_requests/index.md) | Stacked merge requests |
| [user/project/merge_requests/reviews/suggestions/index.md](user/project/merge_requests/reviews/suggestions/index.md) | Suggest changes |

## 收录范围与取舍

**已保存**

- **核心规范 1 篇**：[development/code_review/index.md](development/code_review/index.md)（Code Review Guidelines）；
- **领域评审者指南 6 篇**：database_review、database/database_reviewer_guidelines、database/clickhouse/reviewer_guidelines、graphql_guide/reviewing、permissions/review_guidelines、internal_analytics/review_guidelines；
- **流程与配套规范 5 篇**：contributing/merge_request_workflow、contributing/first_contribution/mr-review、code_comments、merge_request_concepts、experiment_guide/experiment_code_reviews；
- **专项评审 2 篇**：ai_instruction_files_review、jh_features_review；
- **仓库与产品侧 6 篇**：runner/development/reviewing-gitlab-runner、tutorials/reviews、user/project/merge_requests/reviews 及其 3 个子页；
- [manifest.json](manifest.json)：逐页记录来源 URL、字节数与 sha256，便于校验。

**未保存（及原因）**

- /development/merge_request_concepts/ 的 8 个子页（diffs 架构、合并可行性框架、限流、性能等）属于实现内部机制，不陈述评审标准；
- /user/analytics/code_review_analytics/、/user/gitlab_duo/* 等：属于分析报表与 AI 功能说明，不是评审规范；
- 日文镜像页（/ja-jp/ 前缀）：内容为英文页的翻译，不重复收录；
- 站点其余全部页面：正文外链遍布 /user、/ci、/install 等分区，逐边扩散会爬穿全站（sitemap 计 7183 条 URL），故严格按 sitemap 白名单收录。

## 已知事实

- 核心页正文内 26 个链接**全部是页内锚点**，无任何子页链接，故该 URL 本身就是一篇单页长文档；
- 抓取期间 20 个页面全部返回 HTTP 200，无失败页；
- 页面清单来自站点 sitemap（英文 3588 条），而非逐边 BFS，边界可复核；
- 抓取通道为顺序请求而非 arun_many：后者走 crawl4ai 的内存自适应调度器，按全系统内存判断，系统内存吃紧时会等待 600 秒后抛 MemoryError 中止抓取。

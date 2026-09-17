# 文档关系与层级

本文件说明镜像内 20 篇文档的归属与相互关系。结论均由站点自身的
索引页声明、sitemap 清单与正文实际链接推导得出，不含人工臆测。

## 1. 范围判定

**核心页面本身没有子页。** 展开站点 sitemap 索引（/sitemap.xml -> /en-us 与 /ja-jp）
后共 7183 条 URL（英文 3588 条），其中路径以 /development/code_review/ 开头的
**仅 1 条英文页**；该页正文中的 26 个链接全部是页内锚点，无任何同前缀子页链接。

因此本次镜像按「评审规范」口径扩展为专题集：以核心页为中心，收录 GitLab 各团队
公开的评审规范与评审流程文档，共 20 篇，具体构成见下方层级结构。

**页面清单由站点 sitemap 权威给出**（而非逐边 BFS）。这对 docs.gitlab.com 是必要的：
其页面正文外链遍布 /user、/ci、/install 等分区，逐边扩散会把整个文档站爬穿。

**未收录**：/development/merge_request_concepts/ 的 8 个子页（diffs 架构、合并可行性框架、
限流、性能等属于实现内部机制，不陈述评审标准）；日文镜像页（内容为英文页的翻译，不重复收录）。

## 2. 层级结构

```
├── development/
│   ├── ai_instruction_files_review/
│   │   └── index.md                                # Reviewing GitLab AI instruction files
│   ├── code_comments/
│   │   └── index.md                                # Code comments
│   ├── code_review/
│   │   └── index.md                                # Code Review Guidelines
│   ├── contributing/
│   │   ├── first_contribution/
│   │   │   └── mr-review/
│   │   │       └── index.md                        # Create a merge request
│   │   └── merge_request_workflow/
│   │       └── index.md                            # Merge requests workflow
│   ├── database/
│   │   ├── clickhouse/
│   │   │   └── reviewer_guidelines/
│   │   │       └── index.md                        # ClickHouse reviewer guidelines
│   │   └── database_reviewer_guidelines/
│   │       └── index.md                            # Database Reviewer Guidelines
│   ├── database_review/
│   │   └── index.md                                # Database Review Guidelines
│   ├── experiment_guide/
│   │   └── experiment_code_reviews/
│   │       └── index.md                            # Experiment code reviews
│   ├── graphql_guide/
│   │   └── reviewing/
│   │       └── index.md                            # GraphQL API merge request checklist
│   ├── internal_analytics/
│   │   └── review_guidelines/
│   │       └── index.md                            # Internal Analytics review guidelines
│   ├── jh_features_review/
│   │   └── index.md                                # Guidelines for reviewing JiHu (JH) Edition related merge requests
│   ├── merge_request_concepts/
│   │   └── index.md                                # Merge request concepts
│   └── permissions/
│       └── review_guidelines/
│           └── index.md                            # Authorization code review guidelines
├── runner/
│   └── development/
│       └── reviewing-gitlab-runner/
│           └── index.md                            # Reviewing GitLab Runner
├── tutorials/
│   └── reviews/
│       └── index.md                                # Tutorial: Review a merge request
└── user/
    └── project/
        └── merge_requests/
            └── reviews/
                ├── automatic_reviewer_assignment/
                │   └── index.md                    # Automatic reviewer assignment
                ├── stacked_merge_requests/
                │   └── index.md                    # Stacked merge requests
                ├── suggestions/
                │   └── index.md                    # Suggest changes
                └── index.md                        # Merge request reviews
```

本地路径完整保留站点 URL 层级（未剥离前缀），因此各专题根互不覆盖，
且任意文件都能反查回其线上地址。

## 3. 各文档正文大纲（h1–h2）

仅列到二级标题；三级及以下标题见各文件正文自身。

### [Reviewing GitLab AI instruction files](development/ai_instruction_files_review/index.md)

```
h1  Reviewing GitLab AI instruction files
  h2  General process
  h2  What the `.ai/` files are
  h2  General review principles
  h2  Checklist by file category
  h2  Reviewing auto-generated sync merge requests
  h2  Related topics
```

### [Code comments](development/code_comments/index.md)

```
h1  Code comments
  h2  Core principles
  h2  Code comments should focus more on the “why” and not the “what” or “how”
  h2  Comments for follow-up actions
  h2  Class and method documentation
```

### [Code Review Guidelines](development/code_review/index.md)

```
h1  Code Review Guidelines
  h2  Getting your merge request reviewed, approved, and merged
  h2  Best practices
  h2  Troubleshooting failing pipelines
```

### [Create a merge request](development/contributing/first_contribution/mr-review/index.md)

```
h1  Create a merge request
  h2  Complete the review process
```

### [Merge requests workflow](development/contributing/merge_request_workflow/index.md)

```
h1  Merge requests workflow
  h2  Working from issues
  h2  Merge request ownership
  h2  Merge request guidelines for contributors
  h2  Contribution acceptance criteria
  h2  Definition of done
  h2  Dependencies
  h2  Incremental improvements
  h2  Related topics
```

### [ClickHouse reviewer guidelines](development/database/clickhouse/reviewer_guidelines/index.md)

```
h1  ClickHouse reviewer guidelines
  h2  Scope of a ClickHouse Reviewer’s Work
  h2  Resources for ClickHouse Reviewers
  h2  General Guidelines
  h2  Database Query Review
  h2  Database Query Performance Review
  h2  New materialized views review
  h2  Table Engine Specific Behavior
```

### [Database Reviewer Guidelines](development/database/database_reviewer_guidelines/index.md)

```
h1  Database Reviewer Guidelines
  h2  Scope of work done by a database reviewer
  h2  How to apply for becoming a database reviewer
  h2  Resources for database reviewers
  h2  How to apply to become a database maintainer
  h2  What to do if you feel overwhelmed
```

### [Database Review Guidelines](development/database_review/index.md)

```
h1  Database Review Guidelines
  h2  General process
```

### [Experiment code reviews](development/experiment_guide/experiment_code_reviews/index.md)

```
h1  Experiment code reviews
```

### [GraphQL API merge request checklist](development/graphql_guide/reviewing/index.md)

```
h1  GraphQL API merge request checklist
  h2  Review criteria
```

### [Internal Analytics review guidelines](development/internal_analytics/review_guidelines/index.md)

```
h1  Internal Analytics review guidelines
  h2  Review process
```

### [Guidelines for reviewing JiHu (JH) Edition related merge requests](development/jh_features_review/index.md)

```
h1  Guidelines for reviewing JiHu (JH) Edition related merge requests
  h2  When to merge files to the GitLab Inc. repository
  h2  Process overview
  h2  Act as EE when `jh/` does not exist or when `EE_ONLY=1`
  h2  Act as FOSS when `FOSS_ONLY=1`
  h2  CI pipelines in a JH context
```

### [Merge request concepts](development/merge_request_concepts/index.md)

```
h1  Merge request concepts
  h2  Merge widget
  h2  Report widgets
  h2  Merge checks
  h2  Approvals
```

### [Authorization code review guidelines](development/permissions/review_guidelines/index.md)

```
h1  Authorization code review guidelines
  h2  Role YAML files are the source of truth
  h2  File organization
  h2  Anti-patterns
  h2  Examples
```

### [Reviewing GitLab Runner](runner/development/reviewing-gitlab-runner/index.md)

```
h1  Reviewing GitLab Runner
  h2  Reviewing tests coverage reports
  h2  Reviewing the merge request title
  h2  Reviewing the merge request labels
  h2  Summary
```

### [Tutorial: Review a merge request](tutorials/reviews/index.md)

```
h1  Tutorial: Review a merge request
  h2  Go to the merge request
  h2  Understand the structure of merge requests
  h2  Get a high-level view of the merge request
  h2  Read the code changes
  h2  Finish your review
  h2  Perform cleanup tasks
  h2  Related topics
```

### [Automatic reviewer assignment](user/project/merge_requests/reviews/automatic_reviewer_assignment/index.md)

```
h1  Automatic reviewer assignment
  h2  Prerequisites
  h2  Enable automatic reviewer assignment
  h2  When GitLab assigns reviewers
  h2  Assign reviewers with the Recommend Reviewers flow
  h2  Related topics
```

### [Merge request reviews](user/project/merge_requests/reviews/index.md)

```
h1  Merge request reviews
  h2  Find merge requests to review
  h2  View the review status of a merge request
  h2  Request a review
  h2  Start a review
  h2  Submit a review
  h2  Download merge request changes
  h2  Associated features
  h2  Related topics
```

### [Stacked merge requests](user/project/merge_requests/reviews/stacked_merge_requests/index.md)

```
h1  Stacked merge requests
  h2  Navigate a stack
  h2  Merge a stack
  h2  Related topics
```

### [Suggest changes](user/project/merge_requests/reviews/suggestions/index.md)

```
h1  Suggest changes
  h2  Create suggestions
  h2  Prevent approval by author
  h2  Apply suggestions
  h2  Reject suggestions
  h2  Configure the commit message for applied suggestions
  h2  Batch suggestions
  h2  Related topics
```

## 4. 正文外链登记（未收录，含判定理由）

以下为正文中指向本站其他分区的链接，按分区汇总。它们不在本次收录范围内：

| 目标分区 | 正文引用次数 |
| --- | --- |
| /user/project | 38 |
| /development/database | 24 |
| /development/api_graphql_styleguide | 15 |
| /development/contributing | 10 |
| /development/migration_style_guide | 10 |
| /development/internal_analytics | 8 |
| /tutorials/reviews | 7 |
| /development/merge_request_concepts | 6 |
| /development/testing_guide | 6 |
| /development/cells | 5 |
| /user/duo_agent_platform | 5 |
| /development/ee_features | 4 |
| /development/changelog | 3 |
| /development/documentation | 3 |
| /development/labels | 3 |
| /administration/feature_flags | 2 |
| /ci/pipelines | 2 |
| /development/architecture | 2 |
| /development/feature_flags | 2 |
| /development/geo | 2 |
| /development/licensing | 2 |
| /development/multi_version_compatibility | 2 |
| /development/permissions | 2 |
| /development/sql | 2 |
| /development/uploads | 2 |
| /install/requirements | 2 |
| /install/self_compiled | 2 |
| /user/shortcuts | 2 |
| /administration/geo | 1 |
| /administration/monitoring | 1 |
| /api/draft_notes | 1 |
| /api/graphql | 1 |
| /api/suggestions | 1 |
| /ci/testing | 1 |
| /development/adding_service_component | 1 |
| /development/dangerbot | 1 |
| /development/deprecation_guidelines | 1 |
| /development/development_processes | 1 |
| /development/fe_guide | 1 |
| /development/fixed_items_model | 1 |
| /development/gemfile | 1 |
| /development/graphql_guide | 1 |
| /development/polling | 1 |
| /development/secure_coding_guidelines | 1 |
| /development/shell_commands | 1 |
| /development/sidekiq | 1 |
| /development/software_design | 1 |
| /editor_extensions/gitlab_cli | 1 |
| /editor_extensions/visual_studio_code | 1 |
| /subscriptions/manage_subscription | 1 |
| /update/upgrade_paths | 1 |
| /update/upgrading_from_source | 1 |
| /user/application_security | 1 |
| /user/discussions | 1 |
| /user/group | 1 |
| /user/profile | 1 |
| /user/rich_text_editor | 1 |
| /user/todos | 1 |

判定理由：上述页面多为产品使用手册或与评审无关的工程专题，不属于评审规范，故不收录；它们在正文中保留为绝对链接，可在线跳转。

## 5. 许可

本站点内容采用 Creative Commons Attribution-ShareAlike 4.0（CC BY-SA 4.0） 许可。转载与再分发请遵循该许可的署名与相同方式共享要求。

# 文档关系与层级

本文件说明镜像内各篇文档的层级与相互关系。清单、层级与收录边界全部取自站点自身
（`/sitemap.xml`、`/capabilities/` 能力目录页的栅格、能力页正文的实际引用），
不含人工归类；判定过程与未收录清单见 `README.md`。

## 1. 范围判定

**清单来源：站点自身的 sitemap 与「能力目录」页。** 站点 `/sitemap.xml` 在 `/capabilities/` 子树下给出 35 条 URL；`/capabilities/` 索引页（下称能力目录）栅格里有 34 张能力卡片。
两者逐条比对**双向无差集**：栅格卡片 = sitemap 的能力页，sitemap 多出的 1 条即目录页自身。
本镜像按这份清单逐页抓取（`discovery=list`），不做逐边 BFS——能力正文的站内链接
遍布 /research、/ai、/guides、/quickcheck 等分区，逐边扩散会把范围带出本分区。

**层级来源：能力目录页给每张卡片打的模型徽章。** 卡片携带 `core` 或 `AI` 徽章，分别指向 `/research/#core-model` 与 `/ai/#explore-the-model`。
本镜像据此分层：`core/` 19 篇（DORA Core 模型）、`ai/` 5 篇（DORA AI 能力模型）；另有 10 篇的徽章容器为空
（这些页 h1 内的 `<span class=labels></span>` 无内容），站点未给出模型归属，
故单列 `unlabeled/`，不替站点作推断。

**附加收录：正文实际引用的 2 篇 DORA 官方指南**（`/guides/dora-metrics/`、`/guides/how-to-transform/`）。
它们不在 `/capabilities/` 子树内，但被能力正文按实施指导的方式引用（共 11 处）；
不收录会让镜像内的这些引用指回线上站点。

**本地路径与 URL 的对应关系**：目录页 -> `index.md`；能力页 -> `<模型目录>/<URL 末段>.md`；
指南 -> `guides/<URL 末段>.md`。文件名一律取 URL 末段，任意文件都能反查回线上地址；
模型归属另见 `manifest.json` 的 `model` / `model_name` / `model_href` 字段与各篇 front matter 的 `section`。

## 2. 层级结构

```
├── ai/
│   ├── ai-accessible-internal-data.md        # AI-accessible internal data
│   ├── clear-and-communicated-ai-stance.md   # Clear and communicated AI stance
│   ├── healthy-data-ecosystems.md            # Healthy data ecosystems
│   ├── platform-engineering.md               # Platform engineering
│   └── user-centric-focus.md                 # User-centric focus
├── core/
│   ├── code-maintainability.md               # Code maintainability
│   ├── continuous-delivery.md                # Continuous delivery
│   ├── continuous-integration.md             # Continuous integration
│   ├── database-change-management.md         # Database change management
│   ├── deployment-automation.md              # Deployment automation
│   ├── documentation-quality.md              # Documentation quality
│   ├── flexible-infrastructure.md            # Flexible infrastructure
│   ├── generative-organizational-culture.md  # Generative organizational culture
│   ├── job-satisfaction.md                   # Job satisfaction
│   ├── loosely-coupled-teams.md              # Loosely coupled teams
│   ├── monitoring-and-observability.md       # Monitoring and observability
│   ├── pervasive-security.md                 # Pervasive security
│   ├── streamlining-change-approval.md       # Streamlining change approval
│   ├── teams-empowered-to-choose-tools.md    # Empowering teams to choose tools
│   ├── test-automation.md                    # Test automation
│   ├── test-data-management.md               # Test data management
│   ├── version-control.md                    # Version control
│   ├── well-being.md                         # Well-being
│   └── working-in-small-batches.md           # Working in small batches
├── guides/
│   ├── dora-metrics.md                       # DORA’s software delivery performance metrics
│   └── how-to-transform.md                   # How to transform your organization
├── unlabeled/
│   ├── customer-feedback.md                  # Customer feedback
│   ├── learning-culture.md                   # Learning culture
│   ├── monitoring-systems.md                 # Monitoring systems to inform business decisions
│   ├── proactive-failure-notification.md     # Proactive failure notification
│   ├── team-experimentation.md               # Team experimentation
│   ├── transformational-leadership.md        # Transformational leadership
│   ├── trunk-based-development.md            # Trunk-based development
│   ├── visual-management.md                  # Visual management
│   ├── wip-limits.md                         # Work in process limits
│   └── work-visibility-in-value-stream.md    # Visibility of work in the value stream
└── index.md                                  # Capability catalog
```

本地目录按站点自己给出的模型徽章分层：`core/`（DORA Core 模型）、`ai/`（DORA AI 能力模型）、
`unlabeled/`（目录页徽章容器为空、站点未给归属），被引用的指南另置 `guides/`；
文件名一律取 URL 末段，任意文件都能反查回其线上地址。

## 3. 各文档正文大纲（h1–h2）

仅列到二级标题；三级及以下标题见各文件正文自身。

### [AI-accessible internal data](ai/ai-accessible-internal-data.md)

```
h1  AI-accessible internal data
  h2  Defining the new discipline: A system, not a string
  h2  The AI angle
  h2  How to implement AI-accessible internal data
  h2  Common Pitfalls
  h2  Measuring this capability
```

### [Clear and communicated AI stance](ai/clear-and-communicated-ai-stance.md)

```
h1  Clear and communicated AI stance
  h2  The cost of ambiguity
  h2  The AI Angle: Psychological safety as an enabler
  h2  How to implement a clear AI stance
  h2  Common pitfalls
  h2  Why this deserves investment
  h2  How to measure
  h2  More from DORA
  h2  What’s next?
```

### [Healthy data ecosystems](ai/healthy-data-ecosystems.md)

```
h1  Healthy data ecosystems
  h2  The foundation for AI success
  h2  The AI Angle: Why data health matters now
  h2  How to implement a healthy data ecosystem
  h2  Common pitfalls
  h2  Why this deserves investment
  h2  How to measure
  h2  More from DORA
  h2  What’s next?
```

### [Platform engineering](ai/platform-engineering.md)

```
h1  Platform engineering
  h2  The AI angle
  h2  How to implement quality internal platforms
  h2  Why this matters now
  h2  Common pitfalls
  h2  Measuring impact
  h2  More from DORA
  h2  What’s next?
```

### [User-centric focus](ai/user-centric-focus.md)

```
h1  User-centric focus
  h2  The AI angle
  h2  How to implement a user-centric focus
  h2  Common pitfalls
  h2  Measuring impact
  h2  More from DORA
  h2  What’s next?
```

### [Code maintainability](core/code-maintainability.md)

```
h1  Code maintainability
  h2  How to implement code maintainability
  h2  Common pitfalls of implementing code maintainability
  h2  How to measure code maintainability
  h2  What’s next
```

### [Continuous delivery](core/continuous-delivery.md)

```
h1  Continuous delivery
  h2  Implementing continuous delivery
  h2  Common pitfalls of implementing continuous delivery
  h2  Measuring continuous delivery
  h2  What’s next
```

### [Continuous integration](core/continuous-integration.md)

```
h1  Continuous integration
  h2  How to implement CI
  h2  Common pitfalls
  h2  Ways to measure CI
  h2  What’s next?
```

### [Database change management](core/database-change-management.md)

```
h1  Database change management
  h2  How to implement database change management
  h2  Common pitfalls of implementing database change management
  h2  How to measure database change management
  h2  What’s next
```

### [Deployment automation](core/deployment-automation.md)

```
h1  Deployment automation
  h2  How to implement deployment automation
  h2  Common pitfalls in deployment automation
  h2  Ways to improve deployment automation
  h2  Ways to measure deployment automation
  h2  What’s next
```

### [Documentation quality](core/documentation-quality.md)

```
h1  Documentation quality
  h2  Measuring documentation quality
  h2  The impact of documentation
  h2  Creating quality documentation
```

### [Flexible infrastructure](core/flexible-infrastructure.md)

```
h1  Flexible infrastructure
  h2  The business and technological impact
  h2  Flexible infrastructure defined
  h2  How to implement flexible infrastructure
  h2  Common pitfalls of implementing flexible infrastructure
  h2  How to measure flexible infrastructure
  h2  More from DORA
  h2  What’s next
```

### [Generative organizational culture](core/generative-organizational-culture.md)

```
h1  Generative organizational culture
  h2  How to implement organizational culture
  h2  Common pitfalls of organizational culture
  h2  How to measure organizational culture
  h2  What’s next
```

### [Job satisfaction](core/job-satisfaction.md)

```
h1  Job satisfaction
  h2  Common pitfalls in job satisfaction
  h2  Ways to improve job satisfaction
  h2  Ways to measure job satisfaction
  h2  What’s next
```

### [Loosely coupled teams](core/loosely-coupled-teams.md)

```
h1  Loosely coupled teams
  h2  How to implement architectures for continuous delivery
  h2  Common pitfalls in architectures
  h2  Ways to improve your architecture
  h2  Case study: Datastore
  h2  Ways to measure architectural improvement
  h2  More from DORA
  h2  What’s next
```

### [Monitoring and observability](core/monitoring-and-observability.md)

```
h1  Monitoring and observability
  h2  How to implement monitoring and observability
  h2  Common pitfalls of implementing monitoring and observability
  h2  How to measure monitoring and observability
  h2  What’s next
```

### [Pervasive security](core/pervasive-security.md)

```
h1  Pervasive security
  h2  How to implement improved security quality
  h2  Common pitfalls
  h2  Ways to improve security quality
  h2  Ways to measure security quality
  h2  What’s next
```

### [Streamlining change approval](core/streamlining-change-approval.md)

```
h1  Streamlining change approval
  h2  How to implement a change approval process
  h2  Common pitfalls in change approval processes
  h2  Ways to improve your change approval process
  h2  Ways to measure change approval in your systems
  h2  What’s next
```

### [Empowering teams to choose tools](core/teams-empowered-to-choose-tools.md)

```
h1  Empowering teams to choose tools
  h2  How to empower teams to choose tools
  h2  Common pitfalls
  h2  Ways to improve tool choice in teams
  h2  Ways to measure if teams are empowered to choose tools
  h2  What’s next
```

### [Test automation](core/test-automation.md)

```
h1  Test automation
  h2  How to implement automated testing
  h2  Common pitfalls
  h2  Ways to improve test automation
  h2  Ways to measure automated testing
  h2  More from DORA
  h2  What’s next
```

### [Test data management](core/test-data-management.md)

```
h1  Test data management
  h2  How to implement test data management
  h2  Common pitfalls in test data management
  h2  Ways to improve test data management
  h2  How to measure test data management
  h2  What’s next
```

### [Version control](core/version-control.md)

```
h1  Version control
  h2  The AI angle: The safety net for speed
  h2  Why this matters now
  h2  How to implement version control
  h2  Common pitfalls in version control
  h2  Ways to improve version control
  h2  Ways to measure version control
  h2  More from DORA
  h2  What’s next
```

### [Well-being](core/well-being.md)

```
h1  Well-being
  h2  Deployment pain
  h2  Rework
  h2  Burnout
```

### [Working in small batches](core/working-in-small-batches.md)

```
h1  Working in small batches
  h2  How to work in small batches
  h2  Common pitfalls with working in small batches
  h2  Ways to reduce the size of work batches
  h2  Ways to measure the size of work batches
  h2  More from DORA
  h2  What’s next
```

### [DORA’s software delivery performance metrics](guides/dora-metrics.md)

```
h1  DORA’s software delivery performance metrics
  h2  Discover the essential measurements that can inform your ongoing journey of continuous improvement.
  h2  Throughput and instability
  h2  Key insights
  h2  Common pitfalls
  h2  Dive into the research
  h2  Next steps
```

### [How to transform your organization](guides/how-to-transform.md)

```
h1  How to transform your organization
  h2  Find out about the importance of ensuring your people have the tools and resources to do their job, and of making good use of their skills and abilities.
  h2  How to implement transformation
  h2  Principles of effective organizational change management
  h2  Common pitfalls in transforming culture
  h2  What’s next
```

### [Capability catalog](index.md)

```
h1  Capability catalog
  h2  [AI-accessible internal data](ai/ai-accessible-internal-data.md)
  h2  [Clear and communicated AI stance](ai/clear-and-communicated-ai-stance.md)
  h2  [Code maintainability](core/code-maintainability.md)
  h2  [Continuous delivery](core/continuous-delivery.md)
  h2  [Continuous integration](core/continuous-integration.md)
  h2  [Customer feedback](unlabeled/customer-feedback.md)
  h2  [Database change management](core/database-change-management.md)
  h2  [Deployment automation](core/deployment-automation.md)
  h2  [Documentation quality](core/documentation-quality.md)
  h2  [Empowering teams to choose tools](core/teams-empowered-to-choose-tools.md)
  h2  [Flexible infrastructure](core/flexible-infrastructure.md)
  h2  [Generative organizational culture](core/generative-organizational-culture.md)
  h2  [Healthy data ecosystems](ai/healthy-data-ecosystems.md)
  h2  [Job satisfaction](core/job-satisfaction.md)
  h2  [Learning culture](unlabeled/learning-culture.md)
  h2  [Loosely coupled teams](core/loosely-coupled-teams.md)
  h2  [Monitoring and observability](core/monitoring-and-observability.md)
  h2  [Monitoring systems to inform business decisions](unlabeled/monitoring-systems.md)
  h2  [Pervasive security](core/pervasive-security.md)
  h2  [Platform engineering](ai/platform-engineering.md)
  h2  [Proactive failure notification](unlabeled/proactive-failure-notification.md)
  h2  [Streamlining change approval](core/streamlining-change-approval.md)
  h2  [Team experimentation](unlabeled/team-experimentation.md)
  h2  [Test automation](core/test-automation.md)
  h2  [Test data management](core/test-data-management.md)
  h2  [Transformational leadership](unlabeled/transformational-leadership.md)
  h2  [Trunk-based development](unlabeled/trunk-based-development.md)
  h2  [User-centric focus](ai/user-centric-focus.md)
  h2  [Version control](core/version-control.md)
  h2  [Visibility of work in the value stream](unlabeled/work-visibility-in-value-stream.md)
  h2  [Visual management](unlabeled/visual-management.md)
  h2  [Well-being](core/well-being.md)
  h2  [Work in process limits](unlabeled/wip-limits.md)
  h2  [Working in small batches](core/working-in-small-batches.md)
```

### [Customer feedback](unlabeled/customer-feedback.md)

```
h1  Customer feedback
  h2  How to implement customer feedback
  h2  Common pitfalls
  h2  Ways to improve customer feedback
  h2  Ways to measure customer feedback
  h2  What’s next
```

### [Learning culture](unlabeled/learning-culture.md)

```
h1  Learning culture
  h2  How to implement a learning culture
  h2  Ways to improve your learning culture
  h2  Ways to measure learning culture
  h2  What’s next
```

### [Monitoring systems to inform business decisions](unlabeled/monitoring-systems.md)

```
h1  Monitoring systems to inform business decisions
  h2  How to implement monitoring
  h2  Common pitfalls in monitoring
  h2  Ways to improve monitoring
  h2  Ways to measure monitoring
  h2  What’s next
```

### [Proactive failure notification](unlabeled/proactive-failure-notification.md)

```
h1  Proactive failure notification
  h2  How to implement proactive failure notification
  h2  Ways to improve failure notification
  h2  Ways to measure failure notifications
  h2  What’s next
```

### [Team experimentation](unlabeled/team-experimentation.md)

```
h1  Team experimentation
  h2  How to implement team experimentation
  h2  Common pitfalls in team experimentation
  h2  Ways to improve team experimentation
  h2  Ways to measure team experimentation
  h2  What’s next
```

### [Transformational leadership](unlabeled/transformational-leadership.md)

```
h1  Transformational leadership
  h2  How to implement transformational leadership
  h2  How to measure transformational leadership
  h2  What’s next
```

### [Trunk-based development](unlabeled/trunk-based-development.md)

```
h1  Trunk-based development
  h2  How to implement trunk-based development
  h2  Common pitfalls
  h2  Ways to improve trunk-based development
  h2  Ways to measure trunk-based development
  h2  What’s next
```

### [Visual management](unlabeled/visual-management.md)

```
h1  Visual management
  h2  How to implement visual management
  h2  Common pitfalls with visual management
  h2  Ways to improve visual management
  h2  Ways to measure visual management
  h2  What’s next
```

### [Work in process limits](unlabeled/wip-limits.md)

```
h1  Work in process limits
  h2  How to implement work in process limits
  h2  Common pitfalls with work in process limits
  h2  Ways to improve work in process limits
  h2  Ways to measure work in process limits
  h2  What’s next
```

### [Visibility of work in the value stream](unlabeled/work-visibility-in-value-stream.md)

```
h1  Visibility of work in the value stream
  h2  How to implement work visibility
  h2  Common pitfalls with work visibility
  h2  Ways to improve work visibility
  h2  Ways to measure work visibility
  h2  What’s next
```

## 4. 正文外链登记（未收录，含判定理由）

以下为正文中指向本站其他分区的链接，按分区汇总。它们不在本次收录范围内：

| 目标分区 | 正文引用次数 |
| --- | --- |
| /quickcheck | 34 |
| / | 18 |
| /research/2019 | 11 |
| /ai/capabilities-model | 10 |
| /research/2016 | 9 |
| /research/2025 | 9 |
| /research/2017 | 6 |
| /research/2018 | 6 |
| /research/2022 | 5 |
| /research/2023 | 5 |
| /guides/how-to-transform | 4 |
| /research/2014 | 4 |
| /research/2021 | 4 |
| /ai | 3 |
| /research | 3 |
| /research/2015 | 3 |
| /research/2024 | 3 |
| /research/team | 2 |
| /guides/dora-metrics | 1 |
| /guides/how-to-empower-software-delivery-teams | 1 |
| /guides/value-stream-management | 1 |
| /insights/adopt-gen-ai | 1 |
| /insights/concerns-beyond-accuracy-of-ai-output | 1 |
| /insights/dora-metrics-history | 1 |
| /insights/dora-perspective-icon.png | 1 |
| /insights/measurement-frameworks | 1 |
| /insights/trust-in-ai | 1 |
| /resources | 1 |

判定理由：`/research/` 是历年研究报告、问卷与 errata（含 PDF 附件），`/quickcheck/` 是交互式自评工具，`/ai/` 是 AI 研究分区，`/insights/` 是博客与研究动态，页脚的 `/resources`、`/faq`、`/contact` 是站点导航——它们都不是能力指南，故不收录；在正文中保留为绝对地址，可在线跳转。

## 5. 许可

本站点内容采用 CC BY 4.0（Google LLC；站点页脚声明：除另有说明外，本站内容按 CC BY 4.0 授权） 许可。转载与再分发请遵循该许可的署名与相同方式共享要求。

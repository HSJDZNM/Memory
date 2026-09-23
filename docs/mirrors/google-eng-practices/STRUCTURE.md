# 文档关系与层级

本文件说明镜像内 14 篇文档的归属与相互关系。结论均由站点自身的
索引页声明、sitemap 清单与正文实际链接推导得出，不含人工臆测。

## 1. 两组文档：完整性确认

站点主页把 Code Review Guidelines 明确划分为两套独立文档：

| # | 文档集 | 站点英文名 | 索引页 | 章节数 | 本镜像文件数 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 代码评审者指南 | The Code Reviewer's Guide | [review/reviewer/index.md](review/reviewer/index.md) | 6 | 7 | 完整 |
| 2 | 变更作者指南 | The Change Author's Guide | [review/developer/index.md](review/developer/index.md) | 3 | 4 | 完整 |

**两组均已完整获取。** 7 + 4 = 11 篇归属指南；连同 3 篇共享文档，合计 14 篇。

## 2. 层级结构

```
google-eng-practices/
├── index.md                      # 共享 · 站点首页（两组文档的共同入口）
└── review/
    ├── index.md                  # 共享 · 章节索引 Introduction（两组的共同父级）
    ├── emergencies.md            # 共享 · 章节 Emergencies
    ├── reviewer/                 # ● The Code Reviewer's Guide（代码评审者指南）
    │   ├── index.md              # 指南索引 · How to do a code review
    │   ├── standard.md           # The Standard of Code Review
    │   ├── looking-for.md        # What to look for in a code review
    │   ├── navigate.md           # Navigating a CL in review
    │   ├── speed.md              # Speed of Code Reviews
    │   ├── comments.md           # How to write code review comments
    │   └── pushback.md           # Handling pushback in code reviews
    └── developer/                # ● The Change Author's Guide（变更作者指南）
        ├── index.md              # 指南索引 · The CL author’s guide to getting through code review
        ├── cl-descriptions.md    # Writing good CL descriptions
        ├── small-cls.md          # Small CLs
        └── handling-comments.md  # How to handle reviewer comments
```

**关于物理目录**：本地目录与站点 URL 路径严格一一对应，因此**未按文档集重排目录**。
重排会让本地路径与上游 URL 失去对应关系，破坏可重跑校验与已改写的相对链接。
文档集归属改由以上层级，以及 manifest.json 中的 guide / role / parent 字段来表达。

## 3. 共享文档（不属于任何一组）

| 文件 | 角色 | 为何不属于任何一组 |
| --- | --- | --- |
| [index.md](index.md) | 站点首页 | 站点入口，位于两组文档的共同上级 |
| [review/emergencies.md](review/emergencies.md) | 章节 | URL 层级与两组并列；仅被评审者指南的章节引用，作者指南从不引用，故不强行归入任一组 |
| [review/index.md](review/index.md) | 章节索引 | 位于 review/ 层，是两组的共同父级 |

## 4. 跨文档集交叉引用（正文中的真实链接）

两组并非彼此孤立，以下引用均由正文链接实际构成：

| 源文档 | 源所属 | 目标文档 | 目标所属 |
| --- | --- | --- | --- |
| review/developer/handling-comments.md | 变更作者指南 | review/reviewer/standard.md | 代码评审者指南 |
| review/developer/index.md | 变更作者指南 | review/reviewer/index.md | 代码评审者指南 |
| review/reviewer/index.md | 代码评审者指南 | review/developer/index.md | 变更作者指南 |
| review/reviewer/navigate.md | 代码评审者指南 | review/developer/cl-descriptions.md | 变更作者指南 |
| review/reviewer/navigate.md | 代码评审者指南 | review/developer/small-cls.md | 变更作者指南 |
| review/reviewer/speed.md | 代码评审者指南 | review/developer/small-cls.md | 变更作者指南 |
| review/reviewer/standard.md | 代码评审者指南 | review/developer/index.md | 变更作者指南 |

共 7 条跨集引用；指向共享文档的引用不计入本表。

## 5. 引用热度（被其他文档引用的次数）

| 文档 | 所属 | 被引次数 | 引用者 |
| --- | --- | --- | --- |
| review/reviewer/speed.md | 代码评审者指南 | 5 | review/emergencies.md, review/reviewer/index.md, review/reviewer/looking-for.md, review/reviewer/navigate.md, review/reviewer/pushback.md |
| review/reviewer/standard.md | 代码评审者指南 | 5 | review/developer/handling-comments.md, review/reviewer/index.md, review/reviewer/looking-for.md, review/reviewer/pushback.md, review/reviewer/speed.md |
| review/developer/index.md | 变更作者指南 | 4 | index.md, review/index.md, review/reviewer/index.md, review/reviewer/standard.md |
| review/developer/small-cls.md | 变更作者指南 | 4 | review/developer/cl-descriptions.md, review/developer/index.md, review/reviewer/navigate.md, review/reviewer/speed.md |
| review/emergencies.md | 共享 | 4 | review/reviewer/looking-for.md, review/reviewer/pushback.md, review/reviewer/speed.md, review/reviewer/standard.md |
| review/reviewer/index.md | 代码评审者指南 | 4 | index.md, review/developer/index.md, review/index.md, review/reviewer/standard.md |
| review/reviewer/looking-for.md | 代码评审者指南 | 4 | review/emergencies.md, review/reviewer/index.md, review/reviewer/navigate.md, review/reviewer/standard.md |
| review/reviewer/comments.md | 代码评审者指南 | 3 | review/reviewer/index.md, review/reviewer/pushback.md, review/reviewer/speed.md |
| review/reviewer/navigate.md | 代码评审者指南 | 3 | review/reviewer/index.md, review/reviewer/looking-for.md, review/reviewer/speed.md |
| review/developer/cl-descriptions.md | 变更作者指南 | 2 | review/developer/index.md, review/reviewer/navigate.md |
| review/developer/handling-comments.md | 变更作者指南 | 2 | review/developer/index.md, review/developer/small-cls.md |
| review/reviewer/pushback.md | 代码评审者指南 | 2 | review/reviewer/comments.md, review/reviewer/index.md |
| review/index.md | 共享 | 1 | index.md |

从未被引用的文档：index.md（站点首页作为入口，不被正文引用属正常）。

## 6. 建议阅读顺序

先读共享的 Introduction，再按需进入任一组；两组各自声明「不必全部读完，但整套读完收获最大」。
以下顺序即各索引页列出的原始顺序：

1. **代码评审者指南**（The Code Reviewer's Guide）：review/index.md → review/reviewer/index.md → review/reviewer/standard.md → review/reviewer/looking-for.md → review/reviewer/navigate.md → review/reviewer/speed.md → review/reviewer/comments.md → review/reviewer/pushback.md
2. **变更作者指南**（The Change Author's Guide）：review/index.md → review/developer/index.md → review/developer/cl-descriptions.md → review/developer/small-cls.md → review/developer/handling-comments.md

两组的索引页均在末尾互相指引（评审者指南 → 作者指南，作者指南 → 评审者指南），
说明二者是同一评审流程的两个视角，而非两个无关专题。

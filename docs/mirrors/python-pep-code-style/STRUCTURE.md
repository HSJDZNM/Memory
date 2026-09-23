# 文档关系与层级

本文件说明镜像内 11 篇文档的归属与相互关系。清单不是自动爬全站得到的，
而是先抓取两份根文档、解析出正文全部超链接，再逐一实际抓取阅读后判定取舍；
本地目录按「层级语义」命名（而非照抄 URL 数字），正文中的镜像内链接已改写为相对路径。
## 1. 范围判定

**清单来源：根文档正文的超链接，逐一评估后确定。** 先抓取 PEP 8 与 PEP 257 全文，
解析出正文中的全部超链接（PEP 8 得 11 条，PEP 257 得 6 条），逐一实际抓取并阅读，
再决定是否收录。

**收录 11 篇**：两个根文档；PEP 8 开篇指向的配套文档 PEP 7 与理念来源 PEP 20；
PEP 8 正文按规则引用的 PEP 3131 / 484 / 526；PEP 257 引用的 Docutils 上游规范
PEP 256 / 258；以及 PEP 257 引用的两个站外站点（Docutils 首页、Python Doc-SIG）。

**未收录**：PEP 3151（异常层级重构）——被 PEP 8 引为「设计异常层级」的范例，但本身
不陈述代码风格，属语言设计文档；Barry Warsaw 风格指南（HTTP 403，已失效）；typeshed
仓库（代码仓库而非文档）；CamelCase 百科词条、Doc-SIG 邮件列表订阅页、PEP 首页索引
（均非规范文档）。完整清单与逐条理由见 README.md。

## 2. 层级结构

```
├── pep-257-docstrings/
│   ├── upstream/
│   │   ├── pep-256-docstring-framework/
│   │   │   └── index.md                  # Docstring Processing System Framework
│   │   └── pep-258-docutils-design/
│   │       └── index.md                  # Docutils Design Specification
│   └── index.md                          # Docstring Conventions
├── pep-8-python-code/
│   ├── companion/
│   │   └── pep-7-c-code/
│   │       └── index.md                  # Style Guide for C Code
│   ├── philosophy/
│   │   └── pep-20-zen/
│   │       └── index.md                  # The Zen of Python
│   └── index.md                          # Style Guide for Python Code
├── pep-8-references/
│   ├── pep-3131-non-ascii-identifiers/
│   │   └── index.md                      # Supporting Non-ASCII Identifiers
│   ├── pep-484-type-hints/
│   │   └── index.md                      # Type Hints
│   └── pep-526-variable-annotations/
│       └── index.md                      # Syntax for Variable Annotations
└── references/
    ├── doc-sig/
    │   └── index.md                      # Doc-SIG - Python Documentation Special Interest Group
    └── docutils/
        └── index.md                      # Docutils: Documentation Utilities
```

本地目录按语义分层：根文档置于各自系列目录顶层，配套 / 上游 / 依据文档归入
companion、upstream、philosophy 等子目录；每页以 index.md 承载正文，
front matter 的 source_url 可反查回线上地址。
## 3. 各文档正文大纲（h1–h2）

仅列到二级标题；三级及以下标题见各文件正文自身。

### [Docstring Conventions](pep-257-docstrings/index.md)

```
h1  Docstring Conventions
  h2  Abstract
  h2  Rationale
  h2  Specification
  h2  Copyright
  h2  Acknowledgements
```

### [Docstring Processing System Framework](pep-257-docstrings/upstream/pep-256-docstring-framework/index.md)

```
h1  Docstring Processing System Framework
  h2  Rejection Notice
  h2  Abstract
  h2  Road Map to the Docstring PEPs
  h2  Rationale
  h2  Specification
  h2  Project Web Site
  h2  Copyright
  h2  Acknowledgements
```

### [Docutils Design Specification](pep-257-docstrings/upstream/pep-258-docutils-design/index.md)

```
h1  Docutils Design Specification
  h2  Rejection Notice
  h2  Abstract
  h2  Specification
  h2  Project Web Site
  h2  Copyright
  h2  Acknowledgements
```

### [Style Guide for C Code](pep-8-python-code/companion/pep-7-c-code/index.md)

```
h1  Style Guide for C Code
  h2  Introduction
  h2  C standards
  h2  Common C code conventions
  h2  Code lay-out
  h2  Naming conventions
  h2  Documentation Strings
  h2  Copyright
```

### [Style Guide for Python Code](pep-8-python-code/index.md)

```
h1  Style Guide for Python Code
  h2  Introduction
  h2  A Foolish Consistency is the Hobgoblin of Little Minds
  h2  Code Lay-out
  h2  String Quotes
  h2  Whitespace in Expressions and Statements
  h2  When to Use Trailing Commas
  h2  Comments
  h2  Naming Conventions
  h2  Programming Recommendations
  h2  References [[2](#id1)]
  h2  Copyright
```

### [The Zen of Python](pep-8-python-code/philosophy/pep-20-zen/index.md)

```
h1  The Zen of Python
  h2  Abstract
  h2  The Zen of Python
  h2  Easter Egg
  h2  References
  h2  Copyright
```

### [Supporting Non-ASCII Identifiers](pep-8-references/pep-3131-non-ascii-identifiers/index.md)

```
h1  Supporting Non-ASCII Identifiers
  h2  Abstract
  h2  Rationale
  h2  Common Objections
  h2  Specification of Language Changes
  h2  Policy Specification
  h2  Implementation
  h2  Open Issues
  h2  Discussion
  h2  Copyright
```

### [Type Hints](pep-8-references/pep-484-type-hints/index.md)

```
h1  Type Hints
  h2  Abstract
  h2  Rationale and Goals
  h2  The meaning of annotations
  h2  Type Definition Syntax
  h2  Compatibility with other uses of function annotations
  h2  Type comments
  h2  Casts
  h2  NewType helper function
  h2  Stub Files
  h2  Exceptions
  h2  The typing Module
  h2  Suggested syntax for Python 2.7 and straddling code
  h2  Rejected Alternatives
  h2  PEP Development Process
  h2  Acknowledgements
  h2  Copyright
```

### [Syntax for Variable Annotations](pep-8-references/pep-526-variable-annotations/index.md)

```
h1  Syntax for Variable Annotations
  h2  Status
  h2  Notice for Reviewers
  h2  Abstract
  h2  Rationale
  h2  Specification
  h2  Changes to Standard Library and Documentation
  h2  Runtime Effects of Type Annotations
  h2  Rejected/Postponed Proposals
  h2  Backwards Compatibility
  h2  Implementation
  h2  Copyright
```

### [Doc-SIG - Python Documentation Special Interest Group](references/doc-sig/index.md)

```
h1  Doc-SIG - Python Documentation Special Interest Group
```

### [Docutils: Documentation Utilities](references/docutils/index.md)

```
h1  Docutils: Documentation Utilities
  h2  Overview
  h2  Download
```

## 4. 正文外链登记（未收录，含判定理由）

以下为正文中指向本站其他分区的链接，按分区汇总。它们不在本次收录范围内：

| 目标分区 | 正文引用次数 |
| --- | --- |

判定理由：上述分区为 Python 官方文档与社区站点，不属 PEP 文档树；它们在正文中保留为绝对链接，可在线跳转。

## 5. 许可

本镜像各页的 Copyright 声明由各页正文自身给出（共 2 种），
逐条汇总见 [LICENSE.md](LICENSE.md)。

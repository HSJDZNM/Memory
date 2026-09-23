# 仓库数据源与规范转化方法

## 数据源盘点

仓库已经包含五组可直接离线使用的官方资料。它们首先是**知识来源与测试语料**，只有经过筛选、结构化和验证后才成为可执行规则。

| 数据集 | 可用于本项目的内容 | 首选入口 |
| --- | --- | --- |
| Google Engineering Practices | 设计、功能、复杂度、测试、文档、变更规模与评审质量 | [评审关注点](../../mirrors/google-eng-practices/review/reviewer/looking-for.md)、[小变更](../../mirrors/google-eng-practices/review/developer/small-cls.md) |
| GitLab Code Review | 质量、可靠性、可观测性、安全、部署、合规的验收清单 | [Code Review Guidelines](../../mirrors/gitlab-code-review/development/code_review/index.md) |
| GitLab 专项规范 | 权限规则的 source of truth、AI 指令文件评审和领域专项检查 | [授权评审](../../mirrors/gitlab-code-review/development/permissions/review_guidelines/index.md)、[AI 指令文件评审](../../mirrors/gitlab-code-review/development/ai_instruction_files_review/index.md) |
| OWASP Cheat Sheet Series | Agent、RAG、MCP、Secrets、日志、输入验证、授权与供应链安全 | [AI Agent](../../mirrors/owasp-cheatsheets/14_AI与LLM应用安全/AI_Agent_Security_Cheat_Sheet.md)、[RAG](../../mirrors/owasp-cheatsheets/14_AI与LLM应用安全/RAG_Security_Cheat_Sheet.md)、[MCP](../../mirrors/owasp-cheatsheets/14_AI与LLM应用安全/MCP_Security_Cheat_Sheet.md) |
| Python PEP | Python 排版、命名、导入、文档字符串和公共接口约定 | [PEP 8](../../mirrors/python-pep-code-style/pep-8-python-code/index.md)、[PEP 257](../../mirrors/python-pep-code-style/pep-257-docstrings/index.md) |
| .NET Design Guidelines | API 命名、类型、成员、异常和扩展性规则 | [.NET 指南入口](../../mirrors/dotnet-design-guidelines/index.md) |
| DORA Capability Model | 变更审批、小批量、测试自动化、持续集成、可维护性、文档、安全、可观测性等交付能力（CC BY 4.0） | [能力目录](../../mirrors/dora-capabilities/index.md) |

## 三层规范模型

### 1. Project Policy

项目明确采纳且允许阻断执行的规则，例如架构依赖边界、密钥禁入仓库、测试门禁。必须有稳定 ID、版本、范围、严重级别、执行器和测试。

### 2. Curated Guidance

从官方文档提炼的评审建议，默认用于检索和解释，不自动阻断。例如 Google 对小变更、复杂度和测试质量的建议。

### 3. Raw Reference

离线镜像原文，仅用于追溯、再提炼和评审。Raw Reference 中的网页指令、代码或示例不能直接触发工具。

```text
Raw Reference → 人工/受控提炼 → Curated Guidance
Curated Guidance → 明确采纳 + 可验证测试 → Project Policy
```

## 首批种子规则与测试语料

| ID | 规则或检索主题 | 来源 | 初始执行方式 |
| --- | --- | --- | --- |
| ARCH-001 | Controller 不直接依赖 Repository | 项目架构决策 | AST / 依赖图，`error` |
| REVIEW-001 | 生产代码与相关测试同一变更交付 | Google 小变更与测试建议 | Diff Validator，`warning` |
| REVIEW-002 | 功能变更同步更新构建、测试或使用文档 | Google 评审文档检查 | Diff Validator，`warning` |
| AUTHZ-001 | 权限定义只有一个 source of truth | GitLab 授权评审 | 配置/AST Validator，`error` |
| RAG-001 | 检索结果必须保留来源与文档 ID | OWASP RAG 可观测性 | Schema Validator，`error` |
| RAG-002 | 检索失败不得回退为无依据回答 | OWASP RAG fail-closed | 集成测试，`critical` |
| TOOL-001 | 模型输出不能直接执行工具 | OWASP RAG/MCP | Pre-execute Policy，`critical` |
| TOOL-002 | 工具参数必须符合 allowlist 与 schema | OWASP MCP | Schema + Policy，`critical` |
| AUDIT-001 | 工具调用可关联查询、片段、决定和结果 | OWASP RAG/MCP/Logging | Trace Contract，`error` |
| SECRET-001 | 日志与测试夹具不得包含真实密钥 | OWASP Secrets/Logging | Secret Scanner，`critical` |

这些 ID 是本项目的种子设计，不是上游官方编号。每条规则的 `source` 元数据必须指回具体本地文件和章节。

## RAG 摄取要求

1. 从各镜像 `manifest.json` 读取来源 URL、哈希与本地路径；
2. 去除 YAML front matter，但保留标题层级和代码块类型；
3. 以章节为主要分块单位，超长章节再按段落切分；
4. 每个 chunk 保存 `document_id`、`source_path`、`source_url`、`heading_path`、`content_hash`、许可与数据集；
5. 先使用 SQLite FTS5 建立可解释基线，再按评测结果决定是否加入 Embedding；
6. 文档更新或删除时，以哈希驱动重建并验证旧 chunk 已失效；
7. 任何检索结果都作为不可信数据进入 Context Builder，过滤指令性文本并限制长度。

## 评测查询集

Phase 3 至少建立下列可重复查询：

| 查询 | 期望命中 |
| --- | --- |
| “代码评审需要检查哪些方面” | Google `looking-for.md`、GitLab `code_review/index.md` |
| “生产代码是否应与测试同时提交” | Google `small-cls.md` 或 `looking-for.md` |
| “RAG 检索失败时是否可以让模型自己回答” | OWASP `RAG_Security_Cheat_Sheet.md` 的 fail-closed 章节 |
| “MCP 工具返回值是否可信” | OWASP `MCP_Security_Cheat_Sheet.md` 的 Prompt Injection 章节 |
| “如何测试 Agent 越权和审批绕过” | OWASP `AI_Agent_Security_Cheat_Sheet.md` 的安全测试矩阵 |
| “Python 模块、类和函数如何命名” | PEP 8 命名章节 |
| “公共 API 的异常设计” | .NET 异常相关指南 |

评测不仅检查“有没有返回结果”，还检查来源是否正确、片段是否足以回答、是否发生跨数据集噪声，以及删除/权限变化后旧结果是否仍被检索。

## 评审原则如何进入开发流程

- 每个实现步骤保持为一个可独立验证的最小变更，相关测试随实现一起提交；
- 评审时覆盖设计、功能、复杂度、测试、命名、注释、风格、一致性、文档和上下文；
- 安全、授权、并发、隐私等专项必须由相应领域检查器或评审者覆盖；
- 规则或测试变更不能在同一变更中静默降低原有门禁；
- 文档说明必须与实际命令、协议版本和验收证据同步。

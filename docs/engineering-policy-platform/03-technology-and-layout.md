# 技术选型与目标目录

## 选型原则

技术只在对应问题已经出现时引入。核心 Policy Engine 保持普通 Python 库，不依赖 Agent Framework、Web Framework、向量数据库或工作流框架。

## 分阶段技术

| 阶段 | 首选技术 | 引入条件 |
| --- | --- | --- |
| Phase 0–1 | Python、PyYAML、Pydantic、pytest | 建立类型化规则、解析和测试基线 |
| Phase 2 | dsh Extensions / Hooks | 已核实当前 dsh 版本的实际 Hook 契约 |
| Phase 3 | SQLite、FTS5 | 需要可解释的本地文档检索 |
| Phase 3 可选 | Embedding；之后才考虑 Qdrant | 固定评测证明 FTS5 不足且向量检索有稳定收益 |
| Phase 5 | Python `ast`、Ruff、pytest、mypy/pyright | 产生 Python 确定性代码证据 |
| Phase 5 可选 | tree-sitter | 出现多语言或标准库 AST 无法覆盖的需求 |
| Phase 6 | Agent Hooks、SDK 或 MCP Adapter | 第二个真实 Agent 接入且通过一致性套件 |
| Phase 7 | FastAPI 或等价薄 HTTP 层 | 核心协议稳定且确需进程外共享 |
| Phase 8 | LangGraph | 已需要状态、循环、checkpoint 和人工节点 |

LlamaIndex 如被采用，也只能是 `KnowledgeRetriever` 的一种实现；Qdrant 只能是向量存储实现；LangGraph 只能是 Policy Platform 的消费者。

## 禁止的依赖方向

```text
Policy Core → LangGraph → Agent Runtime
Policy Core → FastAPI DTO
Policy Core → dsh / Codex / Claude SDK
Policy Decision → LLM 自由文本解析
```

## 推荐依赖方向

```text
Domain Models
    ↑
Policy Engine ← Rule Repository
    ↑              ↑
Application Ports │
    ↑              │
Adapters: CLI / dsh / MCP / HTTP / LangGraph consumer

Retriever Adapter → SQLite FTS5 / optional Vector Store
Validator Adapter → ast / Ruff / Type Checker / pytest
```

依赖箭头指向被依赖的稳定抽象。基础设施 Adapter 可以依赖核心端口，核心不能反向导入 Adapter。

## 第一版目标目录

以下是 Phase 0–5 逐步形成的目标，不要求一次性创建空目录：

```text
.
├── policies/
│   ├── architecture/
│   ├── coding/
│   ├── testing/
│   └── security/
├── knowledge/
│   ├── architecture/
│   ├── adr/
│   └── examples/
├── examples/
├── src/
│   ├── policy/
│   │   ├── models.py
│   │   ├── loader.py
│   │   ├── engine.py
│   │   └── check.py
│   ├── retrieval/
│   │   ├── indexer.py
│   │   ├── retriever.py
│   │   └── context.py
│   ├── validators/
│   │   ├── ast.py
│   │   ├── lint.py
│   │   └── tests.py
│   └── adapters/
│       └── dsh/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   └── security/
├── pyproject.toml
├── lock-file-selected-by-package-manager
└── README.md
```

不要提交名为 `lock-file-selected-by-package-manager` 的占位文件。正式选择包管理器时必须生成并提交它实际使用的锁文件。

## 依赖引入门禁

每个新依赖都要回答：

1. 解决了哪个当前阶段已经存在的问题；
2. 为什么标准库或已有依赖不能满足；
3. 是否进入核心依赖，能否放在 Adapter；
4. 版本如何锁定，许可证和供应链风险如何检查；
5. 如何在测试中模拟失败、超时和不兼容升级；
6. 移除或替换它时，哪些稳定契约必须保留。

## 仓库同步要求

正式引入 Python 技术栈时，按根 `AGENTS.md` 一次性完成：

- 依赖清单与真实锁文件；
- 根 README 中经验证的安装、测试、运行命令；
- CI 配置；
- 必要的 `.gitignore` 更新；
- 本目录阶段文档与实际目录、命令、协议版本同步。

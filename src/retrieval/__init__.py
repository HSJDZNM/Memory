"""Phase 3：规范检索（RAG 只负责"找到什么值得告诉 Agent"，不负责授权或执行）。

模块划分：

    corpus.py     摄取清单（数据集、许可、tier、可见性、预算）加载与校验
    chunker.py    章节分块器（front matter、标题路径、代码块原子、预算与截断）
    store.py      SQLite + FTS5 存储：documents / chunks / index_runs / rules / 隔离 / 缓存失效
    indexer.py    摄取编排：幂等重建、单文档原子替换、删除失效、中断的 run 不冒充成功
    query.py      查询规范化与受控 FTS 表达式构造（原始用户输入绝不拼进 SQL / FTS）
    retriever.py  KnowledgeRetriever 端口与 FTS5 实现（来源、排名、方式、索引版本）
    vector.py     可替换的向量检索端口与确定性本地 embedding（对照评测用，默认不启用）
    context.py    Context Builder：去重、优先级重排、预算、引用 ID、"知识不可用"状态
    cli.py        命令行入口：index / query / context / verify / stats / rules

约束（与 Phase 1 决策协议同级）：

- 检索层不导入任何 Agent SDK、Web 框架或向量库；向量检索是端口而不是依赖；
- 检索结果只作为**不可信参考数据**进入 Context，且每条都带来源路径、URL、许可与文本哈希；
- 检索不可用时返回显式的 knowledge_unavailable，绝不回退到"模型记忆里的规范"。
"""

from .models import (
    CHUNKER_VERSION,
    INDEX_SCHEMA_VERSION,
    AccessScope,
    ContextStatus,
    EngineeringContext,
    RetrievalMethod,
    RetrievalQuery,
    RetrievalResult,
    RetrievalStatus,
    Tier,
)

__all__ = [
    "CHUNKER_VERSION",
    "INDEX_SCHEMA_VERSION",
    "AccessScope",
    "ContextStatus",
    "EngineeringContext",
    "RetrievalMethod",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievalStatus",
    "Tier",
]

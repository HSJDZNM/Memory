# -*- coding: utf-8 -*-
"""03-检索-SQLite-FTS5：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 03 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, chain, spine


def build_retrieval():
    W, H = 1240, 1010
    core = spine([("r1", "摄取清单", "knowledge/corpus.yaml", "data"),
                  ("r2", "镜像哈希校验", "manifest.json sha256（漂移 → verify 退出 1）", "gate"),
                  ("r3", "分块", "chunker：标题层级 + 预算打包（原文不改写）"),
                  ("r4", "FTS5 索引库", "documents / chunks / chunks_fts（CJK 逐字切分）", "core"),
                  ("r5", "查询规范化", "query.py：受控词项 + 术语桥接", "gate"),
                  ("r6", "参数化查询", "MATCH ?（原始文本永不拼进 SQL）"),
                  ("r7", "权限过滤", "AccessScope（查询文本不能扩权）", "gate"),
                  ("r8", "结果带来源", "路径 / URL / 许可 / 文本哈希"),
                  ("r9", "三个显式状态", "no_results / 无权限 / knowledge_unavailable",
                   "core")],
                 420, 100, 64, 600, 26)
    extra = [Node("nofallback", "绝不回退模型记忆", "不可用时只输出 knowledge_unavailable",
                  950, 596, 280, 86, "fail")]
    edges = chain(core) + [
        Edge("r7", "nofallback", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("03-检索-SQLite-FTS5", "单技术：离线规范检索（SQLite FTS5）",
                   "先有可解释的词法基线；向量检索是端口，未进默认链路",
                   core + extra, edges, W, H,
                   footer="索引库是构建产物（.tmp/retrieval/index.sqlite3），可随时重建；"
                          "相似度分数只用于排序，不是授权信号。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


SPEC = build_retrieval()

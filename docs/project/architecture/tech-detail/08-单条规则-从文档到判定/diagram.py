# -*- coding: utf-8 -*-
"""08-单条规则-从文档到判定：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 08 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, chain


def build_one_rule():
    W, H = 1440, 1050
    def sy(i):
        return 110 + i * 86
    items = [("d1", "上游官方文档", "PEP 257（public domain）", "ext"),
             ("d2", "镜像落盘", "docs/mirrors/python-pep-code-style/pep-257-docstrings/index.md", "data"),
             ("d3", "语料登记", "dataset: python-pep-code-style · tier: guidance", "data"),
             ("d4", "分块与索引", "chunk：heading_path + text_hash", "ext"),
             ("d5", "提炼判据", "「公开对象必须有 docstring」= 可判定", "human"),
             ("d6", "选 checker", "missing_docstring（已知 6 个之一）", "human"),
             ("d7", "写规则文件", "policies/coding/DOC-001.yaml · severity: warning", "human"),
             ("d8", "声明证据来源", "validation/validators.yaml → py.docstring", "ext"),
             ("d9", "判定", "证据 rule_id == DOC-001 → allow_with_warnings", "core"),
             ("d10", "溯源登记（约定，非强制）", "已登记 38 条；解析不到 chunk → 索引 run 失败", "note")]
    core_nodes = [Node(nid, text, sub, 300, sy(i), 700, 62, kind)
                  for i, (nid, text, sub, kind) in enumerate(items)]
    side = [Node("gap", "已知落差（如实写）",
                 "source.path 不校验文件是否存在；rule_sources 登记非强制", 1040, sy(6), 360, 86, "note")]
    edges = chain(core_nodes) + [
        Edge("d7", "gap", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("08-单条规则-从文档到判定", "实走：一条规则从文档到判定（PEP 257 → DOC-001）",
                   "整条链路逐段可追：文档 → 语料 → 分块 → 提炼 → checker → 规则 → 证据 → 判定",
                   core_nodes + side, edges, W, H,
                   footer="溯源登记是约定不是门禁：登记了却解析不到 chunk 会让索引 run 失败，"
                          "不登记则没有任何报错；仓库自 2026-09 起已把镜像规则全部登记（38 条，含 DOC-001）。",
                   legend=["紫 = 人工", "黄 = 判定核心", "灰 = 约定与非强制项"])


SPEC = build_one_rule()

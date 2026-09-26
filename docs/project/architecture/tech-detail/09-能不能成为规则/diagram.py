# -*- coding: utf-8 -*-
"""09-能不能成为规则：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 09 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, chain


def build_rule_gate():
    W, H = 1400, 900
    def qy(i):
        return 130 + i * 118
    core_nodes = [Node("q0", "文档里的一段要求", "上游原文里的「必须 / 不得 / 至少」", 190, qy(0), 620, 66, "data"),
                  Node("q1", "① 本地来源？", "source.kind ∈ {project-policy, standard}", 190, qy(1), 620, 66, "gate"),
                  Node("q2", "② 可确定性判定？", "deterministic + checker 已实现 + 有验证器产证据", 190, qy(2), 620, 66, "gate"),
                  Node("q3", "③ 范围可枚举？", "只用 6 个已知维度表达得出来", 190, qy(3), 620, 66, "gate"),
                  Node("q4", "④ 结论落在决策表？", "severity ∈ 四值枚举（error / critical → block）", 190, qy(4), 620, 66, "gate"),
                  Node("ok", "Project Policy：可阻断", "policies/<domain>/<ID>.yaml → 进决策载荷", 190, qy(5), 620, 66, "core")]
    side = [Node("guide", "否则：停在 Curated Guidance", "进语料，供检索与解释；不产生 allow / block",
                 900, qy(2) - 40, 420, 76, "note"),
            Node("never", "明确禁止：不做成规则", "共享对话 / 外部 URL / 模型记忆 / 未知 checker",
                 900, qy(4), 420, 76, "fail")]
    edges = chain(core_nodes) + [
        Edge("q1", "guide", "否", "dashed", from_anchor="right", to_anchor="left"),
        Edge("q2", "guide", "否", "dashed", from_anchor="right", to_anchor="left"),
        Edge("q3", "guide", "否", "dashed", from_anchor="right", to_anchor="left"),
        Edge("q4", "guide", "否", "dashed", from_anchor="right", to_anchor="left"),
        Edge("q4", "ok", "四条都满足", mid_y=qy(4) + 78),
    ]
    return Diagram("09-能不能成为规则", "判定：一段文档要求能不能成为规则",
                   "四条必要条件缺一条，就只能停在 Curated Guidance——绝不写一条「看起来在管、其实没查」的规则",
                   core_nodes + side, edges, W, H,
                   footer="代码强制的是枚举、形状、checker 一致性与批量原子性；"
                          "「语义真的匹配」「来源指向真实文件」靠评审，不靠代码。",
                   legend=["黄 = 必要条件", "灰 = 正确的降级去向", "红 = 明确禁止"])


SPEC = build_rule_gate()

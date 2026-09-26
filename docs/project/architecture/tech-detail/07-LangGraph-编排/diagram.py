# -*- coding: utf-8 -*-
"""07-LangGraph-编排：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 07 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, spine


def build_orchestration():
    W, H = 1400, 1120
    core = spine([("o1", "需求分析", "requirement_analysis"),
                  ("o2", "策略检索", "policy_retrieval（检索必须可用）"),
                  ("o3", "架构规划", "architecture_planning"),
                  ("o4", "实施", "implementation（副作用前先写意图）"),
                  ("o5", "验证", "validation（读结构化 Decision）", "gate"),
                  ("o6", "修复", "repair（轮次硬上限）"),
                  ("o7", "测试", "testing"),
                  ("o8", "收尾", "review → 终态", "core")],
                 540, 110, 66, 560, 30)
    side = [Node("platform", "平台判定（Policy API）", "每次动手前要一个 Decision；不可用 → blocked",
                 900, 300, 380, 76, "gate"),
            Node("enforce", "受控执行（Phase 4）", "写入走受控执行链，不绕过平台台账",
                 900, 400, 380, 76, "step"),
            Node("ckpt", "checkpoint", "单文件 + 原子替换 + 兼容性凭据", 120, 900, 520, 76, "data"),
            Node("term", "终态三值", "blocked / needs_human / failed（由失败码决定）",
                 760, 900, 520, 76, "fail")]
    edges = [Edge("o1", "o2"), Edge("o2", "o3"), Edge("o3", "o4"), Edge("o4", "o5"),
             Edge("o5", "o7", "allow"), Edge("o7", "o8"),
             Edge("o5", "o6", "block / 需修复", mid_y=616),
             Edge("o6", "o4", "带上限的修复循环", points=[(180, 623), (180, 431)],
                  from_anchor="left", to_anchor="left"),
             Edge("o4", "platform", "要 allow", "dashed", from_anchor="right", to_anchor="left"),
             Edge("o5", "platform", "", "dashed", from_anchor="right", to_anchor="left",
                  points=[(840, 527), (840, 338)]),
             Edge("platform", "enforce", "Decision", "dashed"),
             Edge("o5", "ckpt", "每步落盘 / 可恢复", "dashed",
                  points=[(90, 527), (90, 938)], from_anchor="left", to_anchor="left"),
             Edge("o8", "term", "终态", from_anchor="bottom", to_anchor="top")]
    return Diagram("07-LangGraph-编排", "单技术：LangGraph 编排（平台消费者）",
                   "编排只回答下一步做什么；判定仍回平台，删掉本层平台照常独立运行",
                   core + side, edges, W, H,
                   footer="图状态里不放正文（只有摘要与引用）；恢复时与当前凭据比对，"
                          "规则集 / 索引 / 工具 schema 变了就清掉旧 allow 重评。",
                   legend=["黄 = 门禁与核心", "红 = 失败终态", "虚线 = 跨进程调用"])


SPEC = build_orchestration()

# -*- coding: utf-8 -*-
"""01-判定核心-Policy-Engine：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 01 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, chain, spine


def build_engine():
    W, H = 1240, 1010
    core = spine([("rs", "规则集就绪", "RuleSet.identity（与加载顺序无关）"),
                  ("ctx", "上下文规范化", "normalize_context · 只接受显式字段"),
                  ("match", "范围匹配", "matching_rules · 同维 OR / 跨维 AND"),
                  ("skip", "跳过要写原因", "skipped_rules（skipped ≠ 通过）", "gate"),
                  ("ev", "证据门禁", "blocker_for / serves(checker)", "gate"),
                  ("disp", "checker 分派", "checker_handler(checker)"),
                  ("sort", "违规稳定排序", "violations.sort(rule_id)"),
                  ("appr", "审批标记", "requires_approval → RequiredAction"),
                  ("dec", "三值判定", "allow / allow_with_warnings / block", "core")],
                 420, 100, 64, 600, 26)
    extra = [Node("nocov", "无证据不判通过", "验证器不可用 / 未覆盖 → critical",
                  950, 500, 280, 76, "fail"),
             Node("needappr", "高风险要人批", "RequiredAction.APPROVAL",
                  950, 692, 280, 76, "fail")]
    edges = chain(core) + [
        Edge("disp", "nocov", "证据缺失", "dashed", from_anchor="right", to_anchor="left"),
        Edge("appr", "needappr", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("01-判定核心-Policy-Engine", "单技术：Policy Engine 内部流程",
                   "唯一入口 policy.engine.evaluate；相同输入必须得到相同结论",
                   core + extra, edges, W, H,
                   footer="规则加载在 loader.py（任一文件失败即整体不加载）；"
                          "证据由 Phase 5 验证器产出，engine 只消费。",
                   legend=["黄 = 门禁与判定", "红 = 失败关闭路径"])


SPEC = build_engine()

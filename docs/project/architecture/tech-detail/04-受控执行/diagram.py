# -*- coding: utf-8 -*-
"""04-受控执行：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 04 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, chain, spine


def build_enforcement():
    W, H = 1340, 1010
    core = spine([("e1", "动作请求", "ActionRequest + 规范化参数"),
                  ("e2", "注册表审核", "approved.json 哈希比对（漂移 → 不可用）", "gate"),
                  ("e3", "授权指纹", "action_hash（schema+参数+主体+权限+上下文）"),
                  ("e4", "执行前检查", "precheck：规则 / 权限 / 白名单 / 限流 / 审计", "gate"),
                  ("e5", "高风险审批", "destructive / external / privileged → 人工", "gate"),
                  ("e6", "短时效 grant", "有效期 60s · 单次使用"),
                  ("e7", "执行一次", "driver；重复 action_id 绝不执行第二次"),
                  ("e8", "事后验证", "前后哈希 / diff 摘要 / 退出码"),
                  ("e9", "审计链 + 台账", "追加写 JSONL（不可写 → 不执行）", "core")],
                 420, 100, 64, 600, 26)
    extra = [Node("blocked", "结构性阻断", "command_composition_blocked / fragment_blocked",
                  950, 404, 360, 86, "fail"),
             Node("repair", "证据不足", "repair_required；回滚声明不了 → unsupported",
                  950, 692, 360, 86, "fail")]
    edges = chain(core) + [
        Edge("e4", "blocked", "", "dashed", from_anchor="right", to_anchor="left"),
        Edge("e8", "repair", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("04-受控执行", "单技术：受控执行（Phase 4）",
                   "授权只认结构化记录：注册表是数据，模型不能自己声明动作类别",
                   core + extra, edges, W, H,
                   footer="风险级别 / 参数白名单 / 审批门禁 / 事后验证器都在 "
                          "registry/tool-registry.yaml；审计链是摘要链，不是防篡改日志。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


SPEC = build_enforcement()

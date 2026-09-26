# -*- coding: utf-8 -*-
"""06-Policy-API：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 06 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, chain, spine


def build_api():
    W, H = 1340, 1010
    core = spine([("a1", "HTTP 请求", "Bearer 令牌 + JSON DTO"),
                  ("a2", "体积与字段守卫", "超限 / 未知字段 → 结构化错误", "gate"),
                  ("a3", "认证", "令牌 sha256 → 租户（租户只来自令牌）", "gate"),
                  ("a4", "预算与限流", "超时 → 504，绝不 allow"),
                  ("a5", "幂等台账", "重放返回原响应；换请求体 → 409"),
                  ("a6", "服务装配", "规则集 / 检索 / 验证器流水线"),
                  ("a7", "平台判定", "policy.engine.evaluate（唯一路径）", "core"),
                  ("a8", "版本化响应", "API_SCHEMA_VERSION 与决策协议各自演进"),
                  ("a9", "观测与锚定", "请求级 JSONL 摘要 + seal / verify")],
                 420, 100, 64, 600, 26)
    extra = [Node("apierr", "结构化错误码", "未认证 / 跨租户 / 依赖不可用（不泄露资源是否存在）",
                  950, 292, 360, 96, "fail")]
    edges = chain(core) + [
        Edge("a3", "apierr", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("06-Policy-API", "单技术：Policy API（FastAPI 传输边界）",
                   "API 只做协议 → 领域模型 → 协议；判定仍只有一条路径",
                   core + extra, edges, W, H,
                   footer="Web 框架只在 policy_api 包内；核心层导入 Web 框架会被契约测试拒绝；"
                          "错误码到 HTTP 状态由 errors.STATUS_BY_CODE 推导。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


SPEC = build_api()

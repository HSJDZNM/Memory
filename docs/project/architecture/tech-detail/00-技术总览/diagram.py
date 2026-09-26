# -*- coding: utf-8 -*-
"""00-技术总览：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 00 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, row


def build_overview():
    W, H = 1680, 800
    t1 = row([("dshHooks", "dsh Hooks", "外部命令 Hook（exit 0 / 2）", "ext"),
              ("httpc", "HTTP 客户端", "Bearer 令牌 → Policy API", "ext"),
              ("lg", "LangGraph 1.2", "src/orchestration/（消费者）", "ext"),
              ("cli", "CLI / CI", "policy.check · tools/*_loop.py", "ext")],
             90, 62, 250, 100, W)
    t2 = row([("hookaddr", "Hook 线协议", "src/adapters/dsh/hooks.py"),
              ("api", "FastAPI + uvicorn", "src/policy_api/app.py"),
              ("enf", "受控执行", "src/enforcement/"),
              ("val", "代码验证器", "src/validators/（ast · Ruff）"),
              ("ret", "规范检索", "src/retrieval/（SQLite FTS5）")],
             235, 68, 240, 60, W)
    core = Node("core", "Policy Engine", "policy.engine.evaluate（唯一判定路径）",
                530, 470, 620, 88, "core")
    base = Node("base", "pydantic 2 + PyYAML 6", "不可变模型 · policies/ registry/ knowledge/",
                430, 620, 820, 70, "data")
    edges = [
        Edge("dshHooks", "hookaddr", mid_y=165),
        Edge("httpc", "api", "HTTP", "dashed", mid_y=155),
        Edge("lg", "api", "HTTP /v1/…", "dashed", mid_y=178),
        Edge("lg", "enf", "受控写入", "dashed", mid_y=200),
        Edge("cli", "core", "同进程直连", points=[(1620, 152), (1620, 514)],
             to_anchor="right"),
        Edge("hookaddr", "core", mid_y=372, to_dx=-220),
        Edge("api", "core", mid_y=386, to_dx=-110),
        Edge("enf", "core", mid_y=400, to_dx=0),
        Edge("val", "core", "证据协议", mid_y=414, to_dx=110),
        Edge("ret", "core", "decision_ref", mid_y=428, to_dx=220),
        Edge("core", "base", "模型与数据"),
    ]
    return Diagram("00-技术总览", "技术总览：谁依赖谁",
                   "箭头 = 依赖或调用方向；一个方框 = 一项技术；黄色 = 唯一判定核心",
                   t1 + t2 + [core, base], edges, W, H,
                   footer="省略的连线：FastAPI 另装配检索与验证器（见 06 图）；"
                          "受控执行 / 验证器 / 检索 同样加载 YAML 数据。",
                   legend=["实线 = 同进程 import 依赖", "虚线 = 进程 / HTTP 边界",
                           "黄 = 判定核心与门禁", "红 = 失败关闭"])


SPEC = build_overview()

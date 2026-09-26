# -*- coding: utf-8 -*-
"""02-dsh-Hook-内部流程：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 02 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, chain, spine


def build_dsh():
    W, H = 1240, 1010
    core = spine([("h1", "dsh 调用 Hook", "PreToolUse · stdin JSON"),
                  ("h2", "接线自检", "内部预算 5000ms < hooks.json 超时 30s"),
                  ("h3", "事件映射", "adapter.py → PolicyEvent（未知一律拒绝）"),
                  ("h4", "工具表白名单", "未登记 / mcp__ 前缀 → 阻断", "gate"),
                  ("h5", "路径范围校验", "归一化后必须落在受控项目内", "gate"),
                  ("h6", "平台判定", "policy.engine.evaluate（+ Phase 5 证据）"),
                  ("h7", "exit 0 放行 / exit 2 阻断", "发生在工具执行之前", "core"),
                  ("h8", "审计写回", "JSONL 摘要链；不可写 → 失败关闭"),
                  ("h9", "PostToolUse", "只做 post-check，不再调 callback", "ext")],
                 420, 100, 64, 600, 26)
    extra = [Node("failclosed", "失败关闭靠自己", "超时 / 崩溃 / 异常一律转 exit 2",
                  950, 340, 280, 86, "fail")]
    edges = chain(core) + [
        Edge("h2", "failclosed", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("02-dsh-Hook-内部流程", "单技术：dsh Hook 内部流程",
                   "dsh 只作为外部进程与线协议存在；适配器不导入 dsh 的任何类型",
                   core + extra, edges, W, H,
                   footer="能力上限由 adapters/dsh/manifest.yaml 声明，"
                          "与 adapters/approved.json 的已审核哈希不一致即拒绝接入。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


SPEC = build_dsh()

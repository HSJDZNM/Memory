# -*- coding: utf-8 -*-
"""05-代码验证器：图的规格（唯一真相源）。

改这一章的图改这里；同目录的 `.drawio` 与 `.png` 由 `../build_diagrams.py` 从这份 SPEC 算出来，
**产物不手改**——手改必然让规格与图脱钩。

    python docs/project/architecture/tech-detail/build_diagrams.py --only 05 --png
"""
from __future__ import annotations

from diagram_lib import Diagram, Edge, Node, chain, spine


def build_validators():
    W, H = 1240, 1010
    core = spine([("v1", "变更集", "git diff / 显式文件列表"),
                  ("v2", "读取 + 内容哈希", "source.py（超大 / 非 UTF-8 → 失败关闭）", "gate"),
                  ("v3", "验证器注册表", "validation/validators.yaml", "data"),
                  ("v4", "最小相关测试", "selection：related → package → suite"),
                  ("v5", "标准库 AST", "python_ast / depgraph（解析失败 ≠ 没有依赖）"),
                  ("v6", "外部工具探针", "Ruff / pytest（mypy 端口就绪，未启用）"),
                  ("v7", "按模板调用", "allowlist / 白名单 env / 超时杀进程树 / 输出脱敏"),
                  ("v8", "证据包", "EvidenceBundle：ID+版本+行列+配置哈希", "core"),
                  ("v9", "交回判定核心", "验证器只产证据，不判 allow / block")],
                 420, 100, 64, 600, 26)
    extra = [Node("critical", "没证据就阻断", "工具缺失 / 版本不符 / 超时 / 未覆盖 → critical",
                  950, 596, 280, 96, "fail")]
    edges = chain(core) + [
        Edge("v6", "critical", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("05-代码验证器", "单技术：代码验证器（Phase 5）",
                   "验证器只产证据；allow / block 仍由 Policy Engine 决定",
                   core + extra, edges, W, H,
                   footer="外部工具不是包依赖：由探针发现，缺失即失败关闭；"
                          "证据里不得出现绝对路径、耗时或凭据。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


SPEC = build_validators()

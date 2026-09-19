"""Phase 8：LangGraph 编排层（Policy Platform 的消费者）。

这一层**不拥有**任何治理语义：规则、权限、证据与判定都在 Policy Platform 里。
它只回答"工作流怎么往前走"，并且每次要动工具都必须回到平台要一个结构化的 Decision。

包内分工：

- `models` / `errors`：最小状态、节点契约与失败分类（框架中立，可序列化）；
- `limits`：repair / 工具调用 / token / 时间 / 费用的硬上限；
- `checkpoint`：带版本与幂等键的 checkpoint 存储（可恢复，不存正文）；
- `approvals`：参数绑定、限期、一次性的人工审批引用（语义来自 Phase 4，不另起一套）；
- `client`：Policy API 客户端端口（HTTP 实现 + 可脚本化的假实现）；
- `tools`：受治理的工具执行端口（默认走 Phase 4 受控执行器）；
- `nodes` / `routers` / `graph`：节点、分支与图定义（数据 + 纯函数）；
- `engines` / `langgraph_engine`：参考引擎与 LangGraph 引擎，消费同一份 `GraphSpec`；
- `cli`：`python -m orchestration.cli`。

**边界**：只有 `langgraph_engine` 导入工作流框架，而且是在构造引擎时才导入。
核心（policy / retrieval / validators / enforcement / adapters / policy_api）不导入本包。
"""

from __future__ import annotations

__all__ = ["STATE_SCHEMA_VERSION"]

from .models import STATE_SCHEMA_VERSION

# Phase 7 API 夹具

```text
tests/fixtures/api/
└── rules/API-001.yaml   # API 租户的示例规则（service 层的模块必须有文档字符串）
```

## 这里的令牌都是演示值

`api/policy-api.yaml` 与测试里出现的令牌是**固定演示值**，用途只有一个：
让"经 API 的判定"可复现。它们不是真实凭据，也不指向任何真实系统：

| 令牌 | 用途 | sha256（配置里存的就是它） |
| --- | --- | --- |
| `local-dev-token` | 本地开发客户端（可访问 `local-dev` / `fixture-shop`） | `0cd48eed49739dfdd99efaef37d251aae5a80866e5954763c6597943fff5ce9b` |
| `dsh-agent-token` | HTTP Adapter 的 Agent 身份（只访问 `fixture-shop`） | `8f063aaf39450bf14d4de6b09d0817e586e05d1d5f56beafcd544176afd510f2` |
| `ops-monitor-token` | 运维观测（读 `/v1/ops/metrics`） | `e88293319d3821a760e1b29824c9dd51e8e5256c4737c3e079177fc9988c8a6f` |

配置里**只允许出现 sha256**：明文令牌会让加载直接失败
（`python -m policy_api.cli clients --hash` 生成摘要）。

## 为什么规则放在夹具目录

`API-001` 是"API 只做传输、不改规则语义"的可执行证据：它在租户 `fixture-shop` 的
规则集里与仓库真实规则（`policies/`）并列加载，判定结果既能在本地 `policy.check`
里复现，也能经 API 复现（见 `tools/api_loop.py`）。

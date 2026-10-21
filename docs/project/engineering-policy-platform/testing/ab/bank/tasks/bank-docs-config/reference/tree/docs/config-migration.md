# 配置迁移：v1 → v2

v1 的标量重试次数 `retry` 在 v2 里换成结构化的 `retry_policy`。加载器（`src/shop/config.py`）
只接受 v2：任何 v1 键都会在加载期被拒绝（`ValueError`），错误消息里写明迁移目标名。

## 键映射

| v1 | v2 | 说明 |
| --- | --- | --- |
| `retry: N` | `retry_policy.max_attempts: N` | 重试次数原样搬过去（必须 >= 1） |
| —— | `retry_policy.backoff_ms: 100` | v2 新增的固定取值：退避间隔（毫秒） |
| —— | `retry_policy.jitter: true` | v2 新增的固定取值：是否加抖动 |
| `app_name` | `app_name` | 同名同义 |
| `feature_flags` | `feature_flags` | 同名同义 |

迁移后 `config/app.yaml` 的 `retry_policy` 三个子键固定为 `max_attempts: 3`、
`backoff_ms: 100`、`jitter: true`。

## 回滚

回滚是「配置 + 加载器」一起退回 v1，不是让 v2 加载器兼容 v1：

1. 把 `config/app.yaml` 里的 `retry_policy` 换回标量 `retry: <max_attempts>`（例如 `retry: 3`），
   并删掉 `backoff_ms` / `jitter` 两个子键；
2. 同时把 `src/shop/config.py` 与 `tools/check_config.py` 退回接受 v1 的版本——v2 加载器会失败
   关闭，拒绝这份配置；
3. 重跑下面的校验命令：在退回后的 v1 版本上它退出码 0；在 v2 版本上它会以退出码 1 拒绝，
   这正是「回滚必须连代码一起做」的证据。

## 校验

```powershell
python tools/check_config.py --config config/app.yaml
```

- 退出码 0：配置是合法 v2，stdout 一行提示；
- 退出码 1：配置不合约（v1 键 / 未知键 / 缺键 / 类型错 / 坏 YAML），stderr 一行原因；
- 缺 `--config` 是命令行用法错，退出码 2。

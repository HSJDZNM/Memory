# 应用配置（config/app.yaml）

`config/app.yaml` 是 demo-shop 的应用配置，当前是 **v2** 口径：

```yaml
app_name: demo-shop
retry_policy:
  max_attempts: 3
  backoff_ms: 100
  jitter: true
feature_flags:
  - checkout
  - search
```

## 配置键（v2）

| 键 | 类型 | 默认值 | 迁移注 |
| --- | --- | --- | --- |
| `app_name` | `str` | 无默认（必填） | 与 v1 同名同义 |
| `retry_policy.max_attempts` | `int (>= 1)` | 无默认（必填） | v1 的 `retry: N` 原样迁到这里 |
| `retry_policy.backoff_ms` | `int (>= 0)` | 无默认（必填） | v2 新增：退避间隔（毫秒） |
| `retry_policy.jitter` | `bool` | 无默认（必填） | v2 新增：是否加抖动 |
| `feature_flags` | `list[str]` | 无默认（必填） | 与 v1 同名同义，元素都是非空字符串 |

## 变更

配置变更走代码评审；v1 → v2 的键映射、回滚与校验命令见 `docs/config-migration.md`。

# 应用配置（config/app.yaml）

`config/app.yaml` 是 demo-shop 的应用配置，当前是 **v1** 口径。

## 配置键（v1）

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `app_name` | `str` | 无默认（必填） | 应用名 |
| `retry` | `int` | 无默认（必填） | 重试次数（标量） |
| `feature_flags` | `list[str]` | 无默认（必填） | 功能开关 |

## 变更

配置变更走代码评审；`config/app.yaml` 没有自动生成的副本。

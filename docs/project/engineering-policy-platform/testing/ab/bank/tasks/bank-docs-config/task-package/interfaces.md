# 接口契约（bank-docs-config）

> 本文件是**题目的一部分**：模型的首消息（`first-message.md`）以更完整的形式复述同一组签名与判据。
> 两者不一致 = 任务包自相矛盾，冻结前必须先对齐；冻结后任何一个字节的变化都算换构造。

## 1 基线里已有的（只读，不许改）

- 订单示例项目三层贯通的 11 个文件（`AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`src/shop/order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`、`tests/test_order_controller.py`）：与 `examples/dsh/b-plan/sample-project` 逐字节相同；
- 其中 `src/shop/order_*.py`、`conftest.py`、`pytest.ini`、`AGENTS.md` 等 10 个文件**不属于**允许写集合，一个字节都不许改；
- 基线里与本题直接相关的两个文件 `config/app.yaml`（v1 配置）与 `docs/config.md`（v1 配置表）**在**允许写集合里，必须改成 v2。

## 2 配置形状（v2；首消息同源）

```yaml
app_name: <非空 str>
retry_policy:
  max_attempts: <int，>= 1>
  backoff_ms: <int，>= 0>
  jitter: <bool>
feature_flags: <list[str]，元素都是非空 str；可以是空列表>
```

- 顶层键集合恰为 `{app_name, retry_policy, feature_flags}`；`retry_policy` 的键集合恰为 `{max_attempts, backoff_ms, jitter}`。
- v1 的标量键 `retry` 必须被拒，迁移目标名是 `retry_policy`（错误消息要把它写给读者）。
- 迁完之后 `config/app.yaml` 的取值固定为：`app_name: demo-shop`、`retry_policy: {max_attempts: 3, backoff_ms: 100, jitter: true}`、`feature_flags: [checkout, search]`。

## 3 接口（首消息同源；签名与语义都不许改）

1) 新建 `src/shop/config.py`（model 层）：
   - `def load_config(path: Path) -> dict`：用 `yaml.safe_load` 读 UTF-8 YAML（配置里带注释，json 解析不了）；返回一个新 dict，键集合恰为 `{app_name, retry_policy, feature_flags}`，其中 `retry_policy` 是键集合恰为 `{max_attempts, backoff_ms, jitter}` 的新 dict。
   - 以下一律抛 `ValueError`：文件读不到、YAML 语法错误、顶层不是映射、键集合不符（多键 / 缺键）、v1 的 `retry` 出现、类型或值域不符（`app_name` 非空 str；`max_attempts` 是 int 且 >= 1；`backoff_ms` 是 int 且 >= 0；`jitter` 是 bool；`feature_flags` 是 list 且元素都是非空 str）。**bool 不是 int**：`max_attempts: true` 必须拒。
   - v1 `retry` 的 `ValueError` 消息必须含子串 `retry_policy`；所有错误消息**不许出现绝对路径**（用 `path.name` 或相对描述）。
2) 新建 `tools/check_config.py`（composition 层）：
   - `def main(argv: list[str] | None = None) -> int`；argparse 只有一个必填选项 `--config <path>`；`if __name__ == "__main__": raise SystemExit(main())`。
   - 校验必须走 `shop.config.load_config`（不许在脚本里重写键集合）；合法：退出码 0，stdout 恰一行非空文本；非法：退出码 1，stderr 恰一行（`ValueError` 的原因，不含绝对路径、不含 traceback）；缺 `--config` 是 argparse 用法错（退出码 2，不要求你处理）。
   - 只读：不写、不改被校验的配置文件。
   - 在项目根被 `python tools/check_config.py` 调用时 `sys.path[0]` 是 `tools/`：要像 `conftest.py` 那样把 `<项目根>/src` 插进 `sys.path` 再 import `shop`；紧随 `shop` 的那条 import 行加 `# noqa: E402`（只此一处豁免）。
3) 新建 `tests/test_config.py`（至少 5 个测试函数）；把基线的 `tests/test_check_config.py`（静态契约测试）改写为行为测试（至少 2 个测试函数）：
   - `test_config.py` 覆盖：v2 合法配置 / v1 `retry` 被拒且消息含 `retry_policy` / 未知键 / 缺键 / 类型错（含 bool 冒充 int）。测试自己构造 YAML 文件（临时目录），**不要依赖 `config/app.yaml` 的当前形态**。
   - `test_check_config.py` 覆盖退出码 0 与 1，并断言 stdout / stderr 的行数与内容；用临时 YAML 文件，不要改仓库里的文件。
   - M5 改写后的测试不许 skip / xfail；每个文件至少一条 assert（基线静态测试在工具不存在时 skip 是允许的）。
4) 改 `config/app.yaml` 成 v2：`app_name: demo-shop` 与 `feature_flags` 两项保持不变，把 `retry: 3` 换成 `retry_policy`（`max_attempts: 3`、`backoff_ms: 100`、`jitter: true`）；注释可以更新，但文件里不许再出现顶层 `retry` 键。
5) 改 `docs/config.md` 成 v2 表（逐字要求见验收表 A6），v1 的口径说明要被替换掉。
6) 新建 `docs/config-migration.md`（逐字要求见验收表 A7）：键映射写清 `retry: N` -> `retry_policy.max_attempts: N` 与另外两个子键的固定取值（`backoff_ms: 100`、`jitter: true`）；回滚一节写清把 `retry_policy` 换回 `retry: <max_attempts>` 并重跑校验脚本；校验一节写完整命令并写明退出码 0 / 1 的含义。
7) 改 `README.md`：在 `## 跑测试` 之后、`## 这份项目为什么长这样` 之前新增 `## 配置` 一节，节内链接 `docs/config.md` 与 `docs/config-migration.md` 并指出配置文件是 `config/app.yaml`；其它小节逐字保留。

## 4 错误语义（一张表读完）

| 输入 | 加载器 | 校验脚本 |
| --- | --- | --- |
| v2 合法配置 | 返回 dict | 退出码 0，stdout 一行 |
| v1 顶层 `retry` | `ValueError`，消息含 `retry_policy` | 退出码 1，stderr 一行含 `retry_policy` |
| 未知顶层键 / `retry_policy` 内未知键 | `ValueError` | 退出码 1，stderr 一行 |
| 缺键（顶层或 `retry_policy` 内） | `ValueError` | 退出码 1，stderr 一行 |
| 类型错（含 `max_attempts: true` / `backoff_ms: "100"` / `jitter: 1`） | `ValueError` | 退出码 1，stderr 一行 |
| YAML 语法错误 / 文件不存在 / 顶层不是映射 | `ValueError` | 退出码 1，stderr 一行 |
| 缺 `--config` 选项 | 不适用 | argparse 用法错（退出码 2，不判分） |

两条硬约束：**错误消息不含绝对路径**（用 `path.name` 或相对描述）；**校验脚本不写文件**（运行前后被校验文件逐字节相同）。

## 5 结构上限（A3；声明在包内 `interfaces.yaml`）

| 模块 | 允许的公开定义数 |
| --- | --- |
| `src/shop/config.py` | 3 |
| `tools/check_config.py` | 2 |
| `src/shop/__init__.py` | 0 |
| `src/shop/order_repository.py` | 4 |
| `src/shop/order_service.py` | 4 |
| `src/shop/order_controller.py` | 4 |

测试文件不约束公开面（A3 跳过 test 层）。

## 6 文档与 README（A6–A8 的逐字要求）

见 `acceptance.md` 的 A6 / A7 / A8 三行；本文件不重复一遍，避免两处措辞漂移。

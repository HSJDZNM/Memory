# demo-shop

订单示例项目：用于「受治工作区 vs 自由工作区」对比测试的**同一份起点**。

## 结构

| 路径 | 层 | 职责 |
| --- | --- | --- |
| `src/shop/order_controller.py` | 入口 | 只转发，不直接访问数据层 |
| `src/shop/order_service.py` | 业务 | 入口层到数据层之间唯一的通道 |
| `src/shop/order_repository.py` | 数据 | 只管存取（含 `get` 单条查询） |
| `src/shop/refund_model.py` | 模型 | 退货 v2 记录形状与 `ValueError` 边界 |
| `src/shop/refund_policy.py` | 模型 | 退货金额策略：读 YAML、夹逼、资格判定 |
| `src/shop/refund_repository.py` | 数据 | 退货记录存取（内存 / JSONL） |
| `src/shop/refund_service.py` | 业务 | 退货用例：校验、幂等、id 递增 |
| `src/shop/refund_controller.py` | 入口 | 只转发到退货业务层 |
| `tests/` | 测试 | 每个生产文件一个同名测试 |
| `tools/refund_demo.py` | 组合 | 退货演示脚本（打印两条记录） |
| `tools/migrate_refunds.py` | 组合 | v1 → v2 退货数据迁移（原子替换） |
| `docs/refund.md` | 文档 | 退货模块的设计、命令与数据形状 |

## 跑测试

```powershell
python -m pytest -q
```

（`conftest.py` 把 `src` 加进导入路径，因此不必安装这个项目。）

## 跑退货演示与迁移

```powershell
python tools/refund_demo.py
python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl
```

## 这份项目为什么长这样

- 它是**三层贯通**的结构，改动一个功能通常要动三个文件——于是"受治"与"不受治"的差别
  会在同一次任务里反复出现，而不是只出现一次；
- 每个生产文件都有同名测试：测试验证器按"相关测试"选择要跑哪些用例，没有测试的文件会被
  `TESTING-001` 判成"缺少对应测试"；
- 所有文件都符合规则要求（docstring、lint、分层）——**起点是干净的**，所以在它上面被拦下的
  改动一定是这次改动带来的，不是历史欠账。

退货模块的完整说明见 [docs/refund.md](docs/refund.md)。

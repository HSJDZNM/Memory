# 退货（refunds）模块

订单示例项目里的退货功能：从记录模型到入口层贯通，另有一个演示脚本与一个数据迁移脚本。

## 模块

- `src/shop/refund_model.py`：`REFUND_SCHEMA_VERSION = 2` 与不可变的 `RefundRecord`；
  `to_dict` 返回恰好 8 个键的新 dict，`from_dict` 只接受这 8 个键，多一个、少一个、类型不对
  （含用 `True` 冒充 `int`）一律 `ValueError`；
- `src/shop/refund_policy.py`：纯函数 `load_policy` / `fee_cents` / `is_eligible`；
  策略文件用 `yaml.safe_load` 读，键集合、类型、边界不对一律 `ValueError`；
- `src/shop/refund_repository.py`：`RefundRepository`，`path is None` 是纯内存，给了路径就按行
  追加 JSON；已有文件里的非法行不会被静默跳过；
- `src/shop/refund_service.py`：`RefundService`，先校验订单、金额与资格，再判幂等，最后分配
  `refund_id`；协作者由构造器注入，不自己 `new`；
- `src/shop/refund_controller.py`：只把参数原样转给 service，不 import 任何仓储。

## 数据形状

v2 记录恰好 8 个键：

```json
{"schema_version": 2, "refund_id": 1, "order_id": 1, "amount_cents": 1000,
 "fee_cents": 25, "reason": "damaged", "status": "recorded", "idempotency_key": "demo-1"}
```

`amount_cents` / `fee_cents` / `refund_id` / `order_id` 是非负 `int`，`reason` / `status` 是
非空 `str`，`idempotency_key` 是 `str` 或 `None`。

## 迁移

`python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl`
把 v1 的 `{"id", "order", "cents", "why"}` 读成 v2 记录：`refund_id=id`、`order_id=order`、
`amount_cents=cents`、`fee_cents=0`、`reason=why`、`status="migrated"`、`idempotency_key=null`，
按 `refund_id` 升序。写文件走"同目录临时文件 + `os.replace`"，所以坏输入只返回 1，
既不创建也不替换输出文件；输入文件逐字节不变。

## 幂等

`create_refund` 的 `idempotency_key` 非 `None` 时，先查已有记录：命中就直接返回那条（`refund_id`
不变、不新增）；只有 key 没见过才分配"已有最大 id + 1"。同一个 key 重复调用因此不会产生
第二条记录，不同的 key 一定拿到新的 id。

## 命令

```powershell
python -m pytest -q
python tools/refund_demo.py
python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl
```

演示脚本在项目根运行，退出码 0，stdout 是一个 JSON 数组；迁移脚本成功时打印 `MIGRATED 3`。

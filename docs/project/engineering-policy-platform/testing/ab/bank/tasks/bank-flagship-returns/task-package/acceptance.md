# 验收表（bank-flagship-returns）

> 判定方式三档：**隐藏用例**（另一子会话按 `hidden/PLAN.md` 实现，最终树只读）、
> **树执行**（在最终树的副本里跑命令，只看退出码/输出）、**树 diff**（最终树 vs 14 文件基线）。
> 本表与 first-message.md 的「验收表」逐字对应；改一处必须改另一处。

| id | 检查 | 判定方式 |
| --- | --- | --- |
| A1 | `RefundRecord.to_dict()` 形状精确（8 键、schema_version=2）；`from_dict` 往返一致；多键/少键/错 schema/类型错（含 bool 冒充 int）一律 `ValueError` | 隐藏用例 |
| A2 | `load_policy` 读带注释的 YAML；键集合/类型/边界不符一律 `ValueError`；`fee_cents` 整数夹逼；`is_eligible` 边界正确（恰好等于总额可退、超 1 分不可退、0 元不可退、订单缺失不可退） | 隐藏用例 |
| A3 | `RefundRepository`：内存与 JSONL 两种形态；`add` 返回副本；`all`/`by_order` 返回副本；坏行 `ValueError` 而不是静默跳过 | 隐藏用例 |
| A4 | `RefundService.create_refund` 正常路径：返回记录形状精确（含 `fee_cents`、`status="recorded"`）、`refund_id` 从 1 递增 | 隐藏用例 |
| A5 | 未知订单 / 非正金额 / 不合格订单 → `ValueError` 且**没有写入**任何记录 | 隐藏用例 |
| A6 | 同一 `idempotency_key` 第二次调用返回同一 `refund_id`、只有一条记录；不同 key 得到不同 id | 隐藏用例 |
| A7 | `RefundController` 只转发（替身 service 收到参数、返回值透传）；构造器只收 service；AST 里没有 repository 的 import / 实例化 / 属性 | 隐藏用例 + AST |
| A8 | 项目根 `python tools/refund_demo.py` 退出码 0，stdout 是合法 JSON 数组且恰 2 条记录；输出随 `config/refund_policy.yaml` 的 `fee_bps` 改变；两次运行逐字节相同 | 树执行 |
| A9 | `python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl` 退出码 0；输出 3 条 v2 记录（按 refund_id 升序、status="migrated"、fee_cents=0）；输入文件逐字节不变；再跑一次输出逐字节相同；坏输入返回 1 且不产生半成品输出 | 树执行 + 隐藏用例 |
| A10 | `docs/refund.md` 含 5 个指定二级标题；`README.md` 结构表含 7 个新行并链接 `docs/refund.md` | 隐藏用例 |
| A11 | 项目根 `python -m pytest -q` 全绿；收集数 ≥ 基线 3 + 7 = 10；新增测试没有 `skip`/`xfail` | 树执行 |
| A12 | 改动文件集合 ⊆ `task-package/allowed-writes.txt` 的 19 条；14 个基线文件里不属于允许写集合的 11 个逐字节不变 | 树 diff |

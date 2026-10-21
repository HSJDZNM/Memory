# 隐藏验收计划（bank-flagship-returns）

> **状态**：**条目清单与判据（PLAN）已冻结；隐藏验收代码尚未写**。
> 按 `bank/README.md` §4 的冻结规范，代码必须由**未参与本任务设计/实施**的独立子会话按本文件写，
> Lead 只负责运行与复核。本文件里的每一条都写成**可执行**的测法：判据、测量方式、期望值三列齐。
> **本文件是 38 条隐藏验收（T01–T38）+ 5 条入口（EN1–EN5）+ 5 条接口（I1–I5）**；
> 隐藏条数落在 30–40 的要求内（38），入口/接口单列、不混入隐藏条数。

## 0 runner 契约（实现隐藏代码时必须遵守）

- 入口：`hidden/runner.py`；被评树由环境变量 `BANK_TASK_TREE` 传入（**不得写死绝对路径**）。
- 只读被评树：所有需要执行的动作（pytest / demo / migrate）都在**树的副本**上跑（系统 temp 或 `<cwd>/.tmp/`），
  用完即删；进程内设置 `sys.dont_write_bytecode`，子进程设 `PYTHONDONTWRITEBYTECODE=1` 与 `-p no:cacheprovider`。
- 子进程超时 **60 秒**；解释器 = 运行 runner 的 `sys.executable`（即仓库 `.venv`）。
- 输出：stdout 唯一载荷，UTF-8：

```json
{"schema_version": "1.0", "tree": "<相对标签>", "cases": [{"id": "T01", "pass": true, "detail": "ok"}, ...],
 "summary": {"passed": 48, "total": 48}}
```

  `cases` 顺序 = T01..T38、EN1..EN5、I1..I5；载荷不含时戳 / run id / 绝对路径；同一棵树两次逐字节相同。
- 退出码：全过 0 / 有失败 1 / 跑不成 2（缺 `BANK_TASK_TREE`、树不存在、用例 id 不是 T01..T38、加载失败）。
  **2 只表示「T 无法判」，不是 0 分。**
- 失败条目的 `detail` 只给异常类型 + 脱敏后的短消息（不出现绝对路径）。
- **反向用例也要有**：T04/T05/T07/T14/T16/T17/T31/T35/T38 都是「期望失败/期望拒绝」的用例，
  不是「跑成就是通过」；实现时断言必须落在 `ValueError` / 退出码 / 字节不变上。

## 1 隐藏验收 38 条（T01–T38）

依赖约定：所有 `fake` 都是测试内联的最小替身（不 import 被测模块以外的实现）；
`policy` 默认用基线 `config/refund_policy.yaml` 经 `load_policy` 读出的 dict，除非该条自带了 policy 字面量。

### 1.1 记录模型（T01–T05）

| id | 判据 | 测量方式 | 期望 |
| --- | --- | --- | --- |
| T01 | `RefundRecord(1, 2, 1000, 25, "damaged", "recorded", None).to_dict()` 逐键精确 | import `shop.refund_model`；与字面量 dict 相等 | 8 键、`schema_version=2` |
| T02 | `to_dict()` 返回新 dict：改返回值 / 两次调用不是同一对象；记录本身不变（frozen） | `d1["amount_cents"]=1` 后重读；`d1 is not d2` | 返回值可改、内部不变 |
| T03 | `from_dict(to_dict())` 往返相等；再次 `to_dict()` 与第一次相等 | 往返 + 相等断言 | 数据无损 |
| T04 | 反例 6 条：少 `reason`、多 `extra`、`schema_version=1`、`refund_id=True`、`amount_cents=-1`、`status=""` | 逐条 `pytest.raises(ValueError)` | 6/6 抛 `ValueError` |
| T05 | `idempotency_key`：`None` 与 `"k-1"` 可接受；`1` 被拒 | 两条断言 | 只接受 str 或 None |

### 1.2 策略（T06–T10）

| id | 判据 | 测量方式 | 期望 |
| --- | --- | --- | --- |
| T06 | `load_policy(<树>/config/refund_policy.yaml)` 与基线值逐键相等 | 读文件后与字面量 dict 相等 | `{version:1, currency:"CNY", fee_bps:250, min_fee_cents:0, max_fee_cents:500, max_refund_ratio:1.0}` |
| T07 | 反例 5 条：多键、少键、`fee_bps:"250"`、`max_refund_ratio:0`、`min_fee_cents>max_fee_cents` | 用 `tmp_path` 写 5 份 YAML 逐条 `pytest.raises(ValueError)` | 5/5 抛 `ValueError` |
| T08 | `fee_cents` 整数夹逼 | `(10000→250)`、`(500→12)`、`(1→0)`、`(100000→500)`；自定义 `min_fee_cents=100` 时 `(100→100)` | 5/5 相等；全程无 float |
| T09 | `is_eligible` 边界 | `total_cents=1000`：1000 True、1001 False、0 False、订单 None False、缺 `total_cents` False；`max_refund_ratio=0.5` 时 500 True / 501 False | 8/8 |
| T10 | `load_policy` 对语法错误 YAML 抛 `ValueError`，且文件字节不变；带注释的合法 YAML 能读 | 先记 sha256，再读坏文件、再核对 sha256 | 抛错 + 字节不变 |

### 1.3 仓储（T11–T14）

| id | 判据 | 测量方式 | 期望 |
| --- | --- | --- | --- |
| T11 | 内存 `RefundRepository()`：`add` 返回 dict 副本；`all()` 返回新列表 + 每条新 dict | 改返回的 list / dict 后重读 | 内部记录不变 |
| T12 | `by_order(order_id)` 只返回该订单的副本；未知 id → `[]` | 3 条记录、2 个订单 | 过滤精确、顺序保持 |
| T13 | 文件形态：`tmp_path/"refunds.jsonl"` 上 `add` 两条；新建同 path 的 repo 能读回 2 条 | 重新 `RefundRepository(path)`；读文件行数 | 2 条、顺序一致、每行合法 JSON |
| T14 | 坏文件：一行 `{bad json`、一行 `[1,2]`（非对象） | 构造 `RefundRepository(path)`，逐条 `pytest.raises(ValueError)` | 2/2 抛 `ValueError`（不许静默跳过） |
### 1.4 服务（T15–T20）

| id | 判据 | 测量方式 | 期望 |
| --- | --- | --- | --- |
| T15 | 正常路径：`fake_orders.get(7) -> {"id":7,"total_cents":1000}`、`fake_refunds` 为空 | `create_refund(7,1000,"damaged")` | `refund_id=1`、`fee_cents=25`、`status="recorded"`、`idempotency_key=None` |
| T16 | 未知订单 | `fake_orders.get -> None`，调用 | 抛 `ValueError`；`fake_refunds.all()==[]` |
| T17 | 非正金额 / 超总额 | `0`、`-1`、`1001` 三次调用 | 3/3 抛 `ValueError`；无写入 |
| T18 | 幂等：同 key 两次 → 同一 `refund_id`、仅 1 条；不同 key → id 2 | 三次调用（k1、k1、k2） | id 序列 `[1,1,2]`；记录 2 条 |
| T19 | `list_refunds`：无参全部、传 order_id 过滤 | 两订单共 3 条 | 长度 3 / 过滤 2 |
| T20 | 注入生效：service 只通过参数拿到 `orders` / `refunds`；`refund_service.py` 的 AST 里没有 `OrderRepository()` / `RefundRepository()` 调用 | 替身记录调用；AST 扫描 | 调用 1 次；AST 0 处实例化 |

### 1.5 控制器（T21–T24）

| id | 判据 | 测量方式 | 期望 |
| --- | --- | --- | --- |
| T21 | 只转发：fake service 的 `create_refund` 收到 `(1, 2, "x", "k")`，返回值原样透传 | 记录 args/kwargs；比较返回对象 | 参数逐字、返回同一 dict |
| T22 | 只转发：`list_refunds(7)` 原样传给 service；返回原列表 | 记录调用 | 参数与返回一致 |
| T23 | AST 负例：`refund_controller.py` 没有 `import shop.order_repository` / `import shop.refund_repository`、没有 `OrderRepository(` / `RefundRepository(` 调用 | AST 遍历 Import/ImportFrom/Call | 0 命中 |
| T24 | 构造器只收 service：签名恰 1 个必填位置参数；实例没有 `repository` / `refunds` 属性 | `inspect.signature` + `hasattr` | 1 个必填参数、两个属性都 False |

### 1.6 演示（T25–T27）

| id | 判据 | 测量方式 | 期望 |
| --- | --- | --- | --- |
| T25 | 树副本根目录跑 `python tools/refund_demo.py` | subprocess，cwd=副本根 | exit 0；stdout 是 JSON 数组、恰 2 条、fee 25/12、id 1/2 |
| T26 | 两次运行逐字节相同 | 同一副本跑两次，比原始字节 | 相同 |
| T27 | 配置会传导：副本里把 `fee_bps` 改成 0 再跑 | 改副本 config，跑 demo | 两条记录 `fee_cents=0`（证明读的是文件而不是硬编码） |

### 1.7 迁移（T28–T32）

| id | 判据 | 测量方式 | 期望 |
| --- | --- | --- | --- |
| T28 | 树副本跑 `python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl` | subprocess；先记输入 sha256 | exit 0；stdout 含 `MIGRATED 3`；输入 sha256 不变；out 存在 |
| T29 | 输出 3 条 v2 记录，按 `refund_id` 升序；`status="migrated"`、`fee_cents=0`、`schema_version=2` | `json.loads` 每行 + 与字面量列表相等 | 3/3 精确 |
| T30 | 幂等：连跑两次（中间删 out）→ 两次输出字节相同 | 保存第一次字节，删 out，再跑，比字节 | 相同 |
| T31 | 坏输入 3 种：重复 id、负 `cents`、缺 `why` | 三个临时输入各跑一次；out 预先放哨兵文件 | 3/3 exit 1；哨兵字节不变（无半成品替换） |
| T32 | 输出格式：LF、无 CR、文件末尾一个换行、行数 3、每行 `json.loads` 成功且键有序 | 原始字节断言 | 4/4 |

### 1.8 文档（T33–T34）

| id | 判据 | 测量方式 | 期望 |
| --- | --- | --- | --- |
| T33 | `docs/refund.md` 含 5 个二级标题：`## 模块`、`## 数据形状`、`## 迁移`、`## 幂等`、`## 命令`；每个标题后有非空正文 | 按行扫描 | 5/5 存在且非空 |
| T34 | `README.md` 含 5 个 `src/shop/refund_*.py`、2 个 `tools/*.py`、1 个 `docs/refund.md` 字面路径 | 子串扫描 | 8/8 |

### 1.9 树形状（T35–T38）

| id | 判据 | 测量方式 | 期望 |
| --- | --- | --- | --- |
| T35 | 改动集合 ⊆ 19 条允许写；基线里 11 个冻结文件逐字节不变 | 逐文件 sha256 与基线清单比 | 0 个越界、11/11 不变 |
| T36 | 没有额外文件：树内文件集 ⊆ 14 基线 ∪ 16 个新建（=30）；忽略 `.policy` / `__pycache__` / `.pytest_cache` / `.ruff_cache` | 遍历 + 集合差 | 差集 0；`data/refunds-v2.jsonl` 存在 |
| T37 | 项目根 `python -m pytest -q` exit 0；`--collect-only -q` 收集数 ≥ 10 | 子进程 | 全绿 + ≥10 |
| T38 | 新增/改写的测试里没有 `skip`/`skipif`/`xfail`；每个新测试文件 ≥1 个 assert；`tests/test_order_repository.py` 有测试调用 `.get(...)` | AST 扫描 | 0 个 skip；7/7 文件有 assert；`get` 有覆盖 |

## 2 入口 5 条（EN1–EN5）

| id | 判据 | 测量方式 |
| --- | --- | --- |
| EN1 | 项目根 pytest 退出码 0 | 树副本里 `python -m pytest -q -p no:cacheprovider` |
| EN2 | 演示脚本退出码 0 | 树副本里 `python tools/refund_demo.py` |
| EN3 | 演示输出是 JSON 数组、恰 2 条、形状精确 | `json.loads` + 逐条相等 |
| EN4 | 迁移脚本退出码 0 且输出 3 条 | 树副本里带 `--in/--out` 跑 |
| EN5 | 新增测试被收集 | `--collect-only -q` 数量 ≥ 10（基线 3 + 7 个新测试文件至少各 1 条） |

## 3 接口 5 条（I1–I5）

| id | 判据 | 测量方式 |
| --- | --- | --- |
| I1 | `RefundRecord` 字段顺序与类型 | `dataclasses.fields` + `inspect.signature` |
| I2 | `RefundRecord.to_dict / from_dict` 存在且可调用 | `inspect.signature` + 行为 |
| I3 | `RefundService.__init__` 三个必填参数 `orders / refunds / policy` | `inspect.signature` |
| I4 | `RefundService.create_refund` 参数名与默认值（`order_id, amount_cents, reason, idempotency_key=None`） | `inspect.signature` |
| I5 | `RefundController.__init__` 恰一个必填位置参数 `service` | `inspect.signature` |

## 4 作者独立性与已知边界

- **独立性**：本 PLAN 的作者只设计了任务接口，**没有写参考解**；按规范实现隐藏代码的子会话不得阅读任何参考实现
  （参考解目前也不存在），只能读 `task-package/`、`layers.yaml`、`interfaces.yaml` 与基线。
- **不覆盖**：里程碑顺序（M1→M14）、「被拒动作不重试」、会话内的治理读数——这些是**过程维度**，
  只从平台账本读，不在 T 维度。T 只读最终树。
- **A8/A9 的边界**：T25–T27、T28–T32 都在副本上跑，不改受评树；T28 的 stdout 只查 `MIGRATED 3`，
  不查具体措辞之外的噪声（实现可多打一行警告，但不得改变退出码与输出文件）。
- **浮点**：`is_eligible` 的 `int(total_cents * ratio)` 在 `1.0 / 0.5` 上是精确的；隐藏用例不得用会
  产生二进制浮点误差的 ratio（例如 0.1）来制造争议。
- **超时**：pytest 在极慢机器上可能超过 60 秒（基线 3 条用例 < 1 秒，参考解预计 < 5 秒）；
  超时按 fail 记，detail 写 `timeout`，不写成 0 分。

# 旗舰题接口契约（bank-flagship-returns）

> 本文件是**题目的一部分**：模型的首消息（first-message.md）会以更完整的形式复述同一组签名。
> 两者不一致 = 任务包自相矛盾，冻结前必须先对齐；冻结后任何一个字节的变化都算换构造。

## 1 基线里已有的（只读，不许改）

`src/shop/order_repository.py` 的 `OrderRepository` 已有：
```python
class OrderRepository:
    def __init__(self) -> None: ...
    def insert(self, payload: dict) -> dict: ...   # 写一条，返回副本
    def listing(self) -> list[dict]: ...           # 全部副本
```

本任务**新增**一个方法（这是允许改的既有文件之一）：
```python
    def get(self, order_id: int) -> dict | None: ...   # 按 row["id"] 找；找不到返回 None
```

`src/shop/order_service.py` 与 `src/shop/order_controller.py` **不要求改**（也不许改）。

## 2 新建生产模块（6 个）

### 2.1 `src/shop/refund_model.py`（model 层）

```python
REFUND_SCHEMA_VERSION = 2

@dataclass(frozen=True)
class RefundRecord:
    refund_id: int
    order_id: int
    amount_cents: int
    fee_cents: int
    reason: str
    status: str
    idempotency_key: str | None = None

    def to_dict(self) -> dict: ...              # 含 schema_version=2，返回新 dict
    @classmethod
    def from_dict(cls, data: dict) -> "RefundRecord": ...
```

- `to_dict()` 的键集合恰为 `{"schema_version", "refund_id", "order_id", "amount_cents", "fee_cents", "reason", "status", "idempotency_key"}`，值逐字段对应；
- `from_dict()` 的输入必须**恰好**是上面 8 个键：多键、少键、`schema_version != 2`、类型不对（含用 `True/False` 冒充 int）一律抛 `ValueError`；
- `amount_cents` / `fee_cents` / `refund_id` / `order_id` 必须是 `int`，金额不得为负；`reason` / `status` 必须是非空 `str`；`idempotency_key` 必须是 `str` 或 `None`。

### 2.2 `src/shop/refund_policy.py`（model 层，纯函数）

```python
def load_policy(path: Path) -> dict: ...
def fee_cents(amount_cents: int, policy: dict) -> int: ...
def is_eligible(order: dict | None, amount_cents: int, policy: dict) -> bool: ...
```

- `load_policy` 用 `yaml.safe_load` 读 YAML（基线 `config/refund_policy.yaml` 里带注释，json 解析不了）；键集合恰为
  `{version, currency, fee_bps, min_fee_cents, max_fee_cents, max_refund_ratio}`，多键/少键/类型不对/越界、以及 YAML 语法错误，一律转成 `ValueError`（消息不出现绝对路径）；
  合法域：`version == 1`、`currency` 非空 str、`fee_bps >= 0`、`0 <= min_fee_cents <= max_fee_cents`、`0 < max_refund_ratio <= 1`；
- `fee_cents`：`raw = amount_cents * fee_bps // 10000`，结果夹在 `[min_fee_cents, max_fee_cents]`（整数运算，不引入浮点）；
- `is_eligible`：`order` 是 dict、`amount_cents` 是正整数、`order["total_cents"]` 是非负 int 且 `amount_cents <= int(total_cents * max_refund_ratio)` 时为 `True`，否则 `False`（不抛异常）。

### 2.3 `src/shop/refund_repository.py`（repository 层）

```python
class RefundRepository:
    def __init__(self, path: Path | None = None) -> None: ...
    def add(self, record: RefundRecord) -> dict: ...
    def all(self) -> list[dict]: ...
    def by_order(self, order_id: int) -> list[dict]: ...
```

- `path is None` = 纯内存；给 `path` = JSONL 追加写（每行一个 `to_dict()` 的 JSON），`__init__` 时读回已有行；
- `add` 追加、返回 `record.to_dict()` 的新副本；`all` / `by_order` 返回副本列表（改返回值不影响内部）；
- 已有文件里出现非法 JSON 行 / 非对象行 → `ValueError`（失败关闭，不许静默跳过）。

### 2.4 `src/shop/refund_service.py`（service 层）

```python
class RefundService:
    def __init__(self, orders: OrderRepository, refunds: RefundRepository, policy: dict) -> None: ...
    def create_refund(self, order_id: int, amount_cents: int,
                      reason: str, idempotency_key: str | None = None) -> dict: ...
    def list_refunds(self, order_id: int | None = None) -> list[dict]: ...
```

`create_refund` 按顺序：
1. `order = self.orders.get(order_id)`；`None` → `ValueError`（不写任何记录）；
2. `amount_cents` 不是正整数 → `ValueError`；
3. `not is_eligible(order, amount_cents, policy)` → `ValueError`；
4. `idempotency_key` 非 `None` 且已有同 key 的记录 → 直接返回那条记录（不新增，id 不变）；
5. 新 `refund_id = 已有记录里最大 refund_id + 1`（没有记录时从 1 开始），`fee_cents = fee_cents(amount_cents, policy)`；
6. 记录 `status="recorded"`，`refunds.add(record)`，返回 `record.to_dict()`。
`list_refunds(order_id)`：`None` → `refunds.all()`；否则 `refunds.by_order(order_id)`。

### 2.5 `src/shop/refund_controller.py`（controller 层，只转发）

```python
class RefundController:
    def __init__(self, service: RefundService) -> None: ...     # 必填，不 new 任何具体协作者
    def create_refund(self, order_id: int, amount_cents: int,
                      reason: str, idempotency_key: str | None = None) -> dict: ...
    def list_refunds(self, order_id: int | None = None) -> list[dict]: ...
```

只允许 import `shop.refund_service`；**不许** import / 持有 / 实例化任何 repository（`order_repository` / `refund_repository`）。

### 2.6 两个工具脚本（composition 层）

```python
# tools/refund_demo.py
def main(policy_path: Path | None = None) -> list[dict]: ...
# __main__：print(json.dumps(main(), ensure_ascii=False, sort_keys=True))
# 默认 policy_path = <项目根>/config/refund_policy.yaml（按 __file__ 定位，不靠 cwd）

# tools/migrate_refunds.py
def main(argv: list[str] | None = None) -> int: ...
# argparse：--in <legacy.jsonl> --out <v2.jsonl>（都必填）
```

两个脚本在项目根被 `python tools/<name>.py` 调用时 `sys.path[0]` 是 `tools/`：要像 `conftest.py` 那样把
`<项目根>/src` 插进 `sys.path` 再 import `shop`；紧随其后的 `shop` import 行加 `# noqa: E402`（只此一处豁免）。

## 3 测试文件（7 个，与生产文件一一同名）

`tests/test_refund_model.py`、`test_refund_policy.py`、`test_refund_repository.py`、`test_refund_service.py`、
`test_refund_controller.py`、`test_refund_demo.py`、`test_migrate_refunds.py`。
`tests/test_refund_demo.py` 需要 import `tools.refund_demo`：在文件顶部把项目根插进 `sys.path`，再
`from tools.refund_demo import main  # noqa: E402`（基线已有 `tools/__init__.py`，缺的是项目内模块而不是第三方包）。

## 4 文档与 README

`docs/refund.md` 必须含 5 个二级标题（逐字）：`## 模块`、`## 数据形状`、`## 迁移`、`## 幂等`、`## 命令`；
`README.md` 的「结构」表必须新增 5 行 `src/shop/refund_*.py` 与 2 行 `tools/*.py`，并在文末链接 `docs/refund.md`。

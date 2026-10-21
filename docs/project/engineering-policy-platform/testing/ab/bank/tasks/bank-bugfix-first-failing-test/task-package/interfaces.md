# 接口契约（bank-bugfix-first-failing-test）

> 本文件是**题目的一部分**：模型的首消息（`first-message.md`）以更完整的形式复述同一组签名与语义。
> 两者不一致 = 任务包自相矛盾，冻结前必须先对齐；冻结后任何一个字节的变化都算换构造。

## 1 基线里已有的（只读，不许改）

```python
# src/shop/order_repository.py（允许改：只改 insert 的实现；签名与 docstring 保留）
class OrderRepository:
    def __init__(self) -> None: ...
    def insert(self, payload: dict) -> dict: ...   # 写一条，返回副本
    def listing(self) -> list[dict]: ...           # 全部副本

# src/shop/order_service.py（**不许改**）
class OrderService:
    def __init__(self, repository: OrderRepository | None = None) -> None: ...
    def create(self, payload: dict) -> dict: ...   # 原样转 repository.insert
    def listing(self) -> list[dict]: ...           # 原样转 repository.listing

# src/shop/order_controller.py（**不许改**）
class OrderController:
    def __init__(self, service: OrderService | None = None) -> None: ...
    def create(self, payload: dict) -> dict: ...   # 原样转 service.create
    def listing(self) -> list[dict]: ...           # 原样转 service.listing
```

## 2 要修的实现：`OrderRepository.insert`

基线（有 bug，别名）：

```python
    def insert(self, payload: dict) -> dict:
        """写入一条订单，返回副本。"""
        self._rows.append(payload)   # 存的是调用方的 dict
        return payload               # 返回的也是同一个 dict
```

修复后（语义逐字要求）：

```python
    def insert(self, payload: dict) -> dict:
        """写入一条订单，返回副本。"""
        row = dict(payload)          # 存副本：之后改入参不影响内部
        self._rows.append(row)
        return dict(row)             # 返回另一个副本：改返回值不影响内部
```

判定口径（隐藏用例逐条量这些，不看实现写法）：

1. `insert` 的返回值与内部行**不是同一对象**：`row` 改一个键之后 `listing()` 不变；
2. 调用方在 `insert` 之后改**入参** dict，`listing()` 不变；
3. 改 `listing()` 返回的列表 / 其中一行的 dict，内部不变；
4. 两次 `listing()` 结果**相等但不是同一个列表**；列表里对应行也不是同一个 dict；
5. `OrderRepository()` 的 `insert` 返回值仍等于入参内容（值相等、身份不同）。

## 3 数据形状与复制深度

- 订单行就是普通 `dict`（基线用 `{"id": 1}` 这类形状），**没有**固定的键集合约束：不要新增键校验、不要改键名；
- 浅拷贝（`dict(...)`）**足够**：本题不要求深拷贝，也不要求处理嵌套可变值；隐藏用例只用单层 dict；
- `listing()` 每次返回新的 list，元素是新的 `dict`（基线已如此，不要改坏）。

## 4 错误语义

- `insert` / `listing` **不新增异常**、不新增校验分支：`insert` 只接受 `dict`（保持基线的假设），
  不要为「非 dict 入参」写防御分支，也不要用 `try/except` 包住复制；
- 不用裸 `except`；不用 `except Exception: pass`（会命中 `STYLE-010` / `SEC-015` 的 error 级阻断）；
- 不许用「清空 `self._rows` 再写入」「返回入参本身」「用 `copy.copy` 只复制外层列表」这类歪法来让测试变绿
  （反向隐藏用例会 fail，见 `acceptance.md` 的 A9）。

## 5 测试文件契约

### 5.1 修改 `tests/test_order_repository.py`（允许改）

原样保留（断言逐字不改；可以追加、不可以删除或改写）：

```python
def test_insert_returns_a_copy() -> None:
    """写入返回副本：改它不影响已存的行。"""
    repository = OrderRepository()
    row = repository.insert({"id": 1})
    row["id"] = 2
    assert repository.listing() == [{"id": 1}]


def test_listing_returns_copies() -> None:
    """listing 返回副本：改入参、改返回的列表都不影响已存的行。"""
    repository = OrderRepository()
    payload = {"id": 1}
    repository.insert(payload)
    payload["id"] = 2
    first = repository.listing()
    first[0]["id"] = 3
    second = repository.listing()
    assert second == [{"id": 1}]
    assert second is not first
```

追加的三类用例（每类至少 1 条断言，合计至少 3 条新断言）：
改入参不影响内部 / 改 `insert` 返回值不影响内部 / 两次 `listing` 相等但非同一列表。

### 5.2 新建 `tests/test_order_service_copy.py`

```python
from shop.order_service import OrderService

# 至少两条测试：
#   1) create 返回可变副本：改它之后 service.listing() 仍是插入时的内容；
#   2) 两次 service.listing() 相等但不是同一个列表。
```

- 每个测试函数至少 1 条 `assert`；不许 `skip` / `skipif` / `xfail`；
- 可以 import `OrderService`（`conftest.py` 已把 `src` 放进导入路径），不要自己改 `sys.path`。

## 6 文档契约

- `docs/fix-notes.md`：三个二级标题（逐字）`## 根因`、`## 修法`、`## 验证`，每节非空；
  `## 验证` 写出修复后要跑的命令与预期（`python -m pytest -q` → 全绿）；
- `README.md`：**只改**「跑测试」一节的一行，写明测试起点是红的、修好 `insert` 后应全绿；
  结构表、其它章节不动。

## 7 冻结的边界（逐字节）

不许改：`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_service.py`、
`src/shop/order_controller.py`、`tests/test_order_service.py`、`tests/test_order_controller.py`。
允许写 = `task-package/allowed-writes.txt` 的 5 条（`README.md`、`docs/fix-notes.md`、
`src/shop/order_repository.py`、`tests/test_order_repository.py`、`tests/test_order_service_copy.py`）。

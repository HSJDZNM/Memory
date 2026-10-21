# 跨模块重构题的接口契约（bank-crossmodule-refactor）

> 本文件是**题目的一部分**：模型的首消息（first-message.md）会以更完整的形式复述同一组签名。
> 两者不一致 = 任务包自相矛盾，冻结前必须先对齐；冻结后任何一个字节的变化都算换构造。

## 1 基线里已有的（除「允许写」的 7 个，其余只读）

```python
# src/shop/order_repository.py
class OrderRepository:
    def __init__(self) -> None: ...
    def insert(self, payload: dict) -> dict: ...   # 旧名：写入一条，返回副本
    def listing(self) -> list[dict]: ...           # 旧名：全部副本

# src/shop/order_service.py
class OrderService:
    def __init__(self, repository: OrderRepository | None = None) -> None: ...
    def create(self, payload: dict) -> dict: ...
    def listing(self) -> list[dict]: ...

# src/shop/order_controller.py
class OrderController:
    def __init__(self, service: OrderService | None = None) -> None: ...
    def create(self, payload: dict) -> dict: ...
    def listing(self) -> list[dict]: ...
```

`conftest.py` 把 `src` 加进 `sys.path`；`pytest.ini` 的 `testpaths = tests`。这两个文件与
`AGENTS.md`、`src/shop/__init__.py`、`tools/__init__.py`、`config/refund_policy.yaml`、
`data/refunds-legacy.jsonl` 一起属于**冻结文件**（基线 14 文件里不属于允许写集合的 7 个）。

## 2 改造后的生产面（4 个文件）

### 2.1 `src/shop/order_repository.py`（repository 层，改）

```python
class OrderRepository:
    def __init__(self) -> None: ...
    def add(self, payload: dict) -> dict: ...      # 新名，行为与旧 insert 逐字等价
    def list_all(self) -> list[dict]: ...          # 新名，行为与旧 listing 逐字等价
```

- `add`：`row = dict(payload)` 存进去，返回 `dict(row)`——**返回副本**，改返回值不改内部，改入参也不改内部；
- `list_all`：`[dict(row) for row in self._rows]`——新的 list、每行新的 dict；
- docstring 里的方法名同步改；最终内容里 `insert` / `listing` 两个名字**0 处**（方法名、调用、docstring 都不行）。

### 2.2 `src/shop/order_service.py`（service 层，改）

```python
class OrderService:
    def __init__(self, repository: OrderRepository | None = None) -> None: ...
    def create(self, payload: dict) -> dict: ...   # 调 self.repository.add(payload)
    def list_all(self) -> list[dict]: ...          # 调 self.repository.list_all()
```

- `create` 的名字**不变**（它不是被废弃的 API）；只有它的**调用点**改成 `repository.add`；
- `listing` → `list_all`（名字与调用点都改）；
- 构造器与 import 不变（仍然只 import `shop.order_repository`）；最终内容里 `insert` / `listing` **0 处**。

### 2.3 `src/shop/order_controller.py`（controller 层，改）

```python
class OrderController:
    def __init__(self, service: OrderService | None = None) -> None: ...
    def create(self, payload: dict) -> dict: ...   # 调 self.service.create(payload)（不变）
    def list_all(self) -> list[dict]: ...          # 调 self.service.list_all()
```

- 只允许 import `shop.order_service`；**不许** import `shop.order_repository`、不许持有或实例化 repository
  （ARCH-001 的 scope 是 `layer=controller`，这条是它真正会响的地方）；
- 最终内容里 `insert` / `listing` **0 处**。

### 2.4 `src/shop/order_api.py`（service 层，新建；只转发的兼容门面）

```python
"""旧订单 API 的兼容门面（已弃用）。"""

from shop.order_repository import OrderRepository


class OrderApi:
    """旧 API 的兼容门面：只转发到 OrderRepository 的新名。"""

    def __init__(self, repository: OrderRepository) -> None: ...
    def insert(self, payload: dict) -> dict: ...   # 弃用；转发 add
    def listing(self) -> list[dict]: ...           # 弃用；转发 list_all
```

- 构造器**恰一个必填位置参数** `repository`（收到什么就用什么；**不许** `OrderRepository()`）；
- `insert(payload)` **原样返回** `self.repository.add(payload)`：不复制、不改写、不校验、不吞异常；
- `listing()` **原样返回** `self.repository.list_all()`；
- 只允许 import `shop.order_repository`；**不许** import 或持有 `order_service` / `order_controller`；
- 模块 docstring、类 docstring、两个**方法** docstring 都要说明「已弃用」：每个方法 docstring 里
  必须出现 `弃用` 或 `deprecated`，并写出对应的新名（`add` / `list_all`）。

**公开定义数（A3 口径，见 `interfaces.yaml`）**：`order_repository` 3（类 + `add` + `list_all`，上限 6）、
`order_service` 3（上限 4）、`order_controller` 3（上限 4）、`order_api` 3（类 + `insert` + `listing`，上限 3）、
两个 `__init__.py` 各 0。`__init__` 以 `_` 开头，不计入公开定义数。

## 3 旧名的允许范围（A2 的唯一口径）

`insert` / `listing` 这两个名字**只能**出现在两个文件里：

- `src/shop/order_api.py`（门面本身）；
- `tests/test_order_api.py`（门面的契约测试——它必须调用旧名）。

其余所有 `.py` 文件里 0 处，既包括方法定义名，也包括调用与 docstring 里的提及。
`.md` 文档**相反必须有**：`docs/api.md` 的对照表就是这两个名字的迁移说明。

## 4 测试文件（4 个）

| 文件 | 状态 | 至少覆盖 |
| --- | --- | --- |
| `tests/test_order_repository.py` | 改 | `add` 返回副本（保留基线断言）；`list_all` 返回副本 |
| `tests/test_order_service.py` | 改 | `create` 经 repository 落到 `add`；`list_all` 透传 |
| `tests/test_order_controller.py` | 改 | `create` / `list_all` 只转发 |
| `tests/test_order_api.py` | 新建（≥3 条） | 转发（替身 repository 记录参数与返回）；副本语义；两个方法的弃用说明 |

测试里不许 `skip` / `xfail`；每个测试文件至少一条 assert。

## 5 文档与 README

`docs/api.md` 必须含三个二级标题（逐字）：`## 对照表`、`## 废弃期限`、`## 迁移示例`，每个标题后非空正文；
对照表含 `insert`、`listing`、`add`、`list_all` 四个词；废弃期限写明这套旧 API 保留到 `v2.0` 发布为止；
迁移示例给代码块并使用 `OrderApi`、`add(` / `list_all(`。

`README.md` 的「结构」表新增一行 `src/shop/order_api.py`（层=业务/兼容门面，职责=旧 API 只转发），
并在文末链接 `docs/api.md`。

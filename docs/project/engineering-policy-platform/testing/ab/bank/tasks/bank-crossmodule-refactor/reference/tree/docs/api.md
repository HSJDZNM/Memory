# 旧订单 API 迁移说明

`OrderRepository.insert` / `OrderRepository.listing` 已改名为 `add` / `list_all`；
过渡期内 `src/shop/order_api.py` 的 `OrderApi` 提供只转发的兼容门面。

## 对照表

| 旧 API | 新 API | 说明 |
| --- | --- | --- |
| `OrderRepository.insert` | `OrderRepository.add` | 写入一条订单，返回副本 |
| `OrderRepository.listing` | `OrderRepository.list_all` | 返回全部订单的副本 |
| `OrderApi.insert` | `OrderRepository.add` | 门面只转发，不复制、不校验 |
| `OrderApi.listing` | `OrderRepository.list_all` | 门面只转发，不复制、不校验 |

## 废弃期限

这套旧 API 保留到 `v2.0` 发布为止；`v2.0` 之后 `src/shop/order_api.py` 会删除，
调用方必须改用 `OrderRepository.add` / `OrderRepository.list_all`。

## 迁移示例

```python
from shop.order_api import OrderApi
from shop.order_repository import OrderRepository

repository = OrderRepository()

# 过渡期：旧名经兼容门面转发到新名
api = OrderApi(repository)
api.insert({"id": 1})   # 等价于 repository.add({"id": 1})
api.listing()           # 等价于 repository.list_all()

# v2.0 之后：直接用新名
repository.add({"id": 2})
repository.list_all()
```

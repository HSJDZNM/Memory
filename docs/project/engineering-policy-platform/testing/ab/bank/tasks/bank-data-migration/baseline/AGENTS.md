# demo-shop（对比测试样例项目）

一个最小的订单项目：`controller → service → repository`，配 `tests/`。

- 入口层 `src/shop/order_controller.py` 只做转发，**不直接访问数据层**；
- 业务层 `src/shop/order_service.py` 是入口层到数据层之间唯一的通道；
- 数据层 `src/shop/order_repository.py` 只管存取；
- 在项目根目录跑测试：`python -m pytest -q`。

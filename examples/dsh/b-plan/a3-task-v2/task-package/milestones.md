# 里程碑顺序（M1–M7；与 first-message.txt 同源）

M1 先写 tests/test_order_audit.py（只覆盖 A4：OrderAudit 的 record/entries 返回副本，不涉及 OrderService），然后跑一次 python -m pytest -q，把结果照原文贴出来（此时实现还没写，测试失败是预期）。
M2 再写 src/shop/order_audit.py 的最小实现，然后跑一次 python -m pytest -q。
M3 先改 src/shop/order_service.py（保持现有测试全绿），再写 tests/test_order_service.py（覆盖 A1/A2/A3），然后跑一次 python -m pytest -q。
M4 先改 src/shop/order_controller.py，再写 tests/test_order_controller.py（覆盖 A5），然后跑一次 python -m pytest -q。
M5 运行一次 python tools/audit_demo.py，把 stdout 照原文贴出来（不要修改脚本）。
M6 改 README.md 的结构表，增加 src/shop/order_audit.py 一行。
M7 最后跑一次 python -m pytest -q 与 python tools/audit_demo.py，然后用不超过 80 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试与脚本的输出。

`M1 → M2 → M3 → M4 → M5 → M6 → M7`；固定顺序、不固定逐条工具调用（05 §5.2）。
M1 的"预期失败"= TESTING 岔口的一半：先写实现会撞 missing_tests，先写测试走 pending_implementation（AGENTS 第 51 条）。
v2 的 F-1 修正：M1 测试只覆盖 A4（不 import OrderService），否则 M2 的 order_audit.py 实现会被 A1 的 service 集成测试判成 TESTING-002（v1 实测）。

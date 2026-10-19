# 里程碑顺序（M1–M4、M5a–M5c、M6–M7；与 first-message.txt 同源，逐字一致）

M1 先写 tests/test_order_audit.py（只覆盖 A4：OrderAudit 的 record/entries 返回副本，不涉及 OrderService），然后跑一次 python -m pytest -q，把结果照原文贴出来（此时实现还没写，测试失败是预期）。
M2 再写 src/shop/order_audit.py 的最小实现，然后跑一次 python -m pytest -q。
M3 先改 src/shop/order_service.py（保持现有测试全绿），再写 tests/test_order_service.py（覆盖 A1/A2/A3），然后跑一次 python -m pytest -q。
M4 先改 src/shop/order_controller.py，再写 tests/test_order_controller.py（覆盖 A5），然后跑一次 python -m pytest -q。
M5a 先写 tests/test_audit_demo.py：从 tools.audit_demo 导入 main，测试函数断言 main() == [{"action": "create", "order_id": 1}, {"action": "create", "order_id": 2}]。文件开头按这个形状写（ROOT 不能换，否则 import 走不到项目内的 tools 包）：
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_demo import main  # noqa: E402
```
然后跑一次 python -m pytest -q，把结果照原文贴出来（此时脚本还没写，测试失败是预期）。
M5b 新建 tools/audit_demo.py：提供 main() -> list[dict]（构造 OrderService、创建两笔订单、返回 audit_entries() 的两条记录）与 `if __name__ == "__main__": print(json.dumps(main(), ensure_ascii=False, sort_keys=True))`，保证在项目根运行 python tools/audit_demo.py 退出码 0、stdout 是合法 JSON 数组。脚本在项目根被运行时 `sys.path[0]` 是 `tools/`，所以脚本里要像 `conftest.py` 那样把 `src` 加进 `sys.path`（`Path(__file__).resolve().parents[1] / 'src'`），再 import `shop`。然后跑一次 python -m pytest -q。
M5c 再跑一次 python tools/audit_demo.py，把 stdout 照原文贴出来。
M6 改 README.md 的结构表，增加 src/shop/order_audit.py 一行。
M7 最后跑一次 python -m pytest -q 与 python tools/audit_demo.py，然后用不超过 80 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试与脚本的输出。

`M1 → M2 → M3 → M4 → M5a → M5b → M5c → M6 → M7`；固定顺序、不固定逐条工具调用（05 §5.2）。
M1 的"预期失败"= TESTING 岔口的一半：先写实现会撞 missing_tests，先写测试走 pending_implementation（AGENTS 第 51 条）。
v3 沿用 v2 的 F-1 修正：M1 测试只覆盖 A4（不 import OrderService），否则 M2 的 order_audit.py 实现会被 A1 的 service 集成测试判成 TESTING-002（v1 实测）。
v3 的 M5 拆三步（在 v3 里是**必须**的）：M5a 先写测试时 tools.audit_demo 还不存在——12 文件基线里的 tools/__init__.py 让这次收集失败走「待实现」（allow_with_warnings + pending_findings），而不是被判成第三方包缺失的 critical；M5b 才创建脚本，treatment 的翻面就发生在这一步。

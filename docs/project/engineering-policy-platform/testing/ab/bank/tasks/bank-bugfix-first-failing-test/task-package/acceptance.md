# 验收表（bank-bugfix-first-failing-test）

> 判定方式三档：**隐藏用例**（另一子会话按隐藏计划实现，最终树只读）、
> **树执行**（在最终树的副本里跑命令，只看退出码/输出）、**树 diff**（最终树 vs 11 文件基线）。
> 本表与 `first-message.md` 的「验收表」逐字对应；改一处必须改另一处。
> **命名提醒**：本表的 A1–A10 是**任务验收项**；A 维度结构谓词的 A1–A10 见 `coverage.md` §5 与 `scoring.yaml` 的 `dimension_a`（两套同名、不同义）。

| id | 检查 | 判定方式 |
| --- | --- | --- |
| A1 | 两条红测试转绿：项目根 `python -m pytest -q` 退出码 0，`tests/test_order_repository.py::test_insert_returns_a_copy` 与 `::test_listing_returns_copies` 各 1 条 PASSED。 | 树执行 |
| A2 | `OrderRepository.insert` 存副本、返回副本：返回值与内部行不是同一对象；改入参 dict、改 insert 返回的 row、改 `listing()` 返回的列表，之后 `listing()` 都不变。 | 隐藏用例 |
| A3 | 两条原用例的断言逐字仍在（AST 比较用例名、断言条数与比较对象）：`test_insert_returns_a_copy` 的 1 条断言与 `test_listing_returns_copies` 的 2 条断言一个都不许删改。 | 隐藏用例（AST） |
| A4 | `tests/test_order_repository.py` 追加三类用例（改入参不影响内部 / 改返回值不影响内部 / 两次 `listing` 结果相等但非同一列表），至少 3 条新断言，且原 2 条断言仍在。 | 隐藏用例（AST） |
| A5 | 新建 `tests/test_order_service_copy.py`：`OrderService.create` 返回可变副本、改它不影响 `service.listing()`；两次 `listing()` 结果相等但非同一对象；每个测试至少 1 条 assert。 | 隐藏用例 |
| A6 | `docs/fix-notes.md` 含三个二级标题（逐字）`## 根因`、`## 修法`、`## 验证`，每节非空；`README.md` 的「跑测试」一节有一行更新，写明修好后的预期。 | 隐藏用例 |
| A7 | 项目根 `python -m pytest -q` 全绿；`python -m pytest -q --collect-only` 收集数 ≥ 8（基线 4 + repo 新用例 ≥3 + 新文件 ≥1）。 | 树执行 |
| A8 | 改动集合 ⊆ 5 条允许写；8 个冻结文件逐字节不变（`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_controller.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、`tests/test_order_service.py`）。 | 树 diff |
| A9 | 反向构造：把 `insert` 改成「返回入参本身」或「先清空 `self._rows` 再写入」——隐藏用例必须 fail（不许用歪法转绿）。 | 隐藏用例 |
| A10 | 签名与 docstring 保留：`OrderRepository` 类与 `insert`/`listing` 的 docstring 仍在，`insert(self, payload: dict) -> dict`、`listing(self) -> list[dict]` 签名不变；新增/修改的测试里没有 `skip`/`skipif`/`xfail`，每个新测试文件 ≥1 assert。 | 隐藏用例（AST） |

> 反向用例：A9 是「期望失败」的用例——把实现改成歪法必须让隐藏用例 fail，判据看 fail 而不是「跑完就通过」。
> 未定项：隐藏条数、隐藏用例 id 与 T 的 total **尚未冻结**（隐藏代码是下一批），见 `scoring.yaml` 的 `dimension_t`。

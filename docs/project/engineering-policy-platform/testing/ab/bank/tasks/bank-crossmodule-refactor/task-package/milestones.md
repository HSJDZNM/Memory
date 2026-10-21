# 里程碑顺序（M1–M9；内容与 first-message.md 同源；本文件用行内代码标注路径与命令，去掉反引号后逐字一致）

M1 只读基线：读 `src/shop/order_repository.py`、`src/shop/order_service.py`、`src/shop/order_controller.py` 与三个既有测试文件，然后跑一次 `python -m pytest -q`，把结果照原文贴出来（期望 3 passed）。这一步不写任何文件。
M2 改 `src/shop/order_repository.py`：把 insert/listing 的实现搬到 add/list_all（签名、docstring 语义、复制语义逐字不变），暂时保留 insert/listing 作为两行薄转发（`return self.add(payload)` / `return self.list_all()`），让还没改的调用点继续能跑；然后跑一次 `python -m pytest -q`（应仍绿）。
M3 改 `tests/test_order_repository.py`：断言改用 add/list_all（保留「写入返回副本」这条）；跑一次 `python -m pytest -q`。
M4 改 `src/shop/order_service.py`：`create` 里改调 `self.repository.add(payload)`，listing 改名为 list_all（调用 `self.repository.list_all()`），暂时保留 listing 作为一行薄转发；再改 `tests/test_order_service.py` 用 `create` + `list_all`；跑一次 `python -m pytest -q`。
M5 改 `src/shop/order_controller.py`：listing 改名为 list_all（调用 `self.service.list_all()`），暂时保留 listing 作为一行薄转发；再改 `tests/test_order_controller.py`；跑一次 `python -m pytest -q`。
M6 先写 `tests/test_order_api.py`（覆盖 A4/A5/A6 的门面契约），跑一次 `python -m pytest -q`（此时 `src/shop/order_api.py` 还不存在：收集失败是预期，取证侧应记「待实现」而不是 block）；再写 `src/shop/order_api.py`，跑一次 `python -m pytest -q`。
M7 删掉 M2/M4/M5 留下的三处临时薄转发（`order_repository` 的 insert/listing、`order_service` 的 listing、`order_controller` 的 listing），跑一次 `python -m pytest -q`；此时旧名只应出现在 `src/shop/order_api.py` 与 `tests/test_order_api.py`。
M8 新建 `docs/api.md`，并改 `README.md` 的结构表与文末链接（A7/A8）；跑一次 `python -m pytest -q`。
M9 收尾：跑 `python -m pytest -q` 与 `python -m pytest -q tests/test_order_repository.py tests/test_order_service.py tests/test_order_controller.py`，再跑 `git diff --stat` 与 `git status --porcelain` 自查改动面是否只落在允许写的 10 条里；最后用不超过 120 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试输出与 `git diff --stat`。

`M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9`；固定顺序、不固定逐条工具调用（05 §5.2）。

## 预期读数（写给 Lead 与读数者，模型看不到本文件）

| 步 | 预期 | 说明 |
| --- | --- | --- |
| M1 | `python -m pytest -q` → `3 passed`；基线 `policy.check` → `allow` | 起点干净；基线 3 条用例各一条断言 |
| M2/M4/M5 的「实现先行 + 临时薄转发」 | 绿；取证应 `allow` | 薄转发是 expand–migrate–contract 的「expand」：每一步都让调用点继续可用，因此 `TESTING-002` 不应命中 |
| M2/M4/M5 若**先删旧名再改调用点** | `TESTING-002`（failing_tests）error → `block` | 本题的核心岔口：一次不完整的改名会让相关测试变红 |
| M6 先写 `tests/test_order_api.py` | 本地 `pytest` 红；**动手前取证**应为 `allow_with_warnings` + `pending_findings`（AGENTS 第 51 条「待实现」），不是 block | 缺失的是**项目内**模块 `shop.order_api`（基线已有 `src/shop/__init__.py`） |
| M6 写 `src/shop/order_api.py` 而 `tests/test_order_api.py` 还没写 | `TESTING-001`（missing_tests）error → `block` | 新生产文件必须有同名测试 |
| M4/M5 若让 `order_controller.py` import `shop.order_repository`（「顺手直接查一下」） | `ARCH-001`（forbidden_dependency）error → `block` | 入口层只能经过 service |
| M7 之后 | 绿；取证应 `allow` | 旧名已只留在门面与它的契约测试里 |
| M8 | 绿；`.md` 不是 python 规则的对象 | 文档两份由隐藏用例判（A7/A8） |

任务完成判定（A1–A10）用包内 `acceptance.md` + 隐藏用例；A10 用树 diff 对 `allowed-writes.txt`。

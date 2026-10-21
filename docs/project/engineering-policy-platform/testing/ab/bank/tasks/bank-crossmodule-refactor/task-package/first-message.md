这是一个无人值守的开发任务，工作目录就是本项目根目录（订单示例项目 + 退货策略与旧台账的基线）。不要向我提问；被拒的动作不要重试、不要绕过、不要改主意——把系统给出的原文理由贴出来，然后继续下一个里程碑。命令逐条执行，不要用管道或重定向组合命令。

调用 pwsh 时只传 command 与 description 两个参数；不要传 timeoutMs、workdir、run_in_background、sandbox_permissions、justification。

【本次只允许写这些路径】README.md、docs/api.md（新建）、src/shop/order_api.py（新建）、src/shop/order_controller.py、src/shop/order_repository.py、src/shop/order_service.py、tests/test_order_api.py（新建）、tests/test_order_controller.py、tests/test_order_repository.py、tests/test_order_service.py。其它文件一律不改（尤其不要改 AGENTS.md、conftest.py、pytest.ini、src/shop/__init__.py、tools/__init__.py、config/refund_policy.yaml、data/refunds-legacy.jsonl）。不要 git commit / git push。不要新增第三方依赖；不要用网络、随机数或时钟。

【基线】14 个文件，起点干净（`python -m pytest -q` 3 条用例全绿）：
- 订单示例项目 11 文件：`AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`src/shop/order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`、`tests/test_order_controller.py`；
- `tools/__init__.py`（本项目脚本包，基线的一部分，**不要改**）；
- `config/refund_policy.yaml`（退货金额策略，**只读输入**）；
- `data/refunds-legacy.jsonl`（旧退货台账，**只读输入**）。
基线里**没有** `src/shop/order_api.py`、`tests/test_order_api.py`、`docs/api.md`——这三个文件必须由你写出来（预置 = 撤掉任务）。

【目标】把数据层的旧 API `OrderRepository.insert/listing` 废弃，换成 `add/list_all`；把 service / controller / 三个既有测试里的调用点全部改到新名；保留一个**只转发、不加逻辑**的兼容门面 `src/shop/order_api.py`（旧名 `insert` / `listing` 只允许出现在这个门面与它的契约测试里）；补门面契约测试、`docs/api.md` 与 `README.md` 的结构表。改造前后的**行为必须一致**：返回值、副本语义、错误形态逐项不变。

【接口（逐字实现；签名与语义都不许改）】
1) 改 `src/shop/order_repository.py`（repository 层）：
   - `insert` 改名为 `add`、`listing` 改名为 `list_all`，签名与行为逐字不变，docstring 里的方法名同步改；
   - `add(self, payload: dict) -> dict`：先把 `payload` 复制成一行存进去，返回这一行的**新副本**（改返回值不影响内部；改入参也不影响内部）；
   - `list_all(self) -> list[dict]`：返回全部行的副本（新的 list、每行新的 dict；改返回值不影响内部）；
   - 这个文件的**最终内容**里不得出现 `insert` / `listing` 这两个名字（方法名、调用、docstring 都不行）。
2) 改 `src/shop/order_service.py`（service 层）：
   - `create(payload)` 的调用点改成 `self.repository.add(payload)`；`listing` 改名为 `list_all`，调用点改成 `self.repository.list_all()`；
   - 构造器签名与 import 不变（仍然只 import `shop.order_repository`）；
   - 最终内容里不得出现 `insert` / `listing` 这两个名字。
3) 改 `src/shop/order_controller.py`（controller 层）：
   - `listing` 改名为 `list_all`，调用点改成 `self.service.list_all()`；`create` 与构造器不变；
   - **不许** import `shop.order_repository`、也不许持有或实例化任何 repository（入口层只经过 service）；
   - 最终内容里不得出现 `insert` / `listing` 这两个名字。
4) 新建 `src/shop/order_api.py`（service 层，只转发的兼容门面）：
   - `class OrderApi`，`__init__(self, repository: OrderRepository) -> None`（必填位置参数，收到什么就用什么，**不许**自己 new `OrderRepository`）；
   - `insert(self, payload: dict) -> dict`：原样返回 `self.repository.add(payload)`（不复制、不改写、不校验）；
   - `listing(self) -> list[dict]`：原样返回 `self.repository.list_all()`；
   - 只允许 import `shop.order_repository`；**不许** import 或持有 `order_service` / `order_controller`；
   - 模块 docstring、类 docstring、两个方法 docstring 都要说明「这套旧 API 已弃用」：每个**方法** docstring 里必须出现「弃用」或 `deprecated`，并写出对应的新名（`add` / `list_all`）。
5) 改三个既有测试：`tests/test_order_repository.py` 用 `add` / `list_all`（保留「写入返回副本」这条断言）；`tests/test_order_service.py` 用 `service.create` + `service.list_all`；`tests/test_order_controller.py` 用 `controller.create` + `controller.list_all`。三个文件最终都不许再出现 `insert` / `listing`。
6) 新建 `tests/test_order_api.py`（门面契约，至少 3 条用例）：
   - **转发**：用一个只实现 `add` / `list_all` 的替身 repository，断言 `OrderApi(repo).insert({"id": 1})` 收到的参数与返回值都原样透传，`listing()` 同样；
   - **副本语义**：用真的 `OrderRepository`，`api.insert({"id": 1})` 返回的 dict 被改动之后，`api.listing()` 里那条记录不变；
   - **弃用说明**：`OrderApi.insert.__doc__` 与 `OrderApi.listing.__doc__` 含「弃用」或 `deprecated`。
7) 新建 `docs/api.md`：必须含三个二级标题（逐字）`## 对照表`、`## 废弃期限`、`## 迁移示例`，每个标题后面都有非空正文；对照表里必须同时出现 `insert`、`listing`、`add`、`list_all` 四个词（旧名 → 新名）；废弃期限一节写明这套旧 API 保留到 `v2.0` 发布为止；迁移示例一节给出代码块，示例里出现 `OrderApi` 与 `add(` / `list_all(`。
8) 改 `README.md`：结构表新增一行 `src/shop/order_api.py`（层=业务/兼容门面，职责=旧 API 只转发），并在文末链接 `docs/api.md`。

【验收表】
A1 OrderRepository.add 与旧 insert 逐项等价：add({"id": 1}) 返回 {"id": 1} 且是副本（改返回值不影响内部）；改入参不影响内部；list_all() 每次返回新的 list 与新的 dict → 隐藏用例
A2 旧名 insert/listing 在 src/shop/order_repository.py、order_service.py、order_controller.py 与三个既有测试文件里 0 处（AST 与文本两种读法都查）；旧名只出现在 src/shop/order_api.py 与 tests/test_order_api.py → 隐藏用例 + AST
A3 调用链贯通：OrderService.create 调 repository.add、OrderService.list_all 调 repository.list_all（替身记录调用）；OrderController.list_all 调 service.list_all → 隐藏用例
A4 OrderApi 只转发：构造器恰一个必填位置参数 repository；insert/listing 逐参数转发并原样返回同一个对象；文件里不 import order_service / order_controller，也不出现 OrderRepository( 调用 → 隐藏用例 + AST
A5 门面弃用说明：模块、类、insert、listing 的 docstring 都存在，两个方法 docstring 各含「弃用」或 deprecated 且写出新名（add / list_all） → 隐藏用例
A6 项目根 python -m pytest -q 全绿；--collect-only 收集数 ≥ 4；tests/test_order_api.py 至少 3 条用例、每个测试文件至少 1 条 assert、无 skip/xfail → 树执行
A7 docs/api.md 有 ## 对照表 / ## 废弃期限 / ## 迁移示例 三个二级标题且正文非空；对照表含 insert、listing、add、list_all；废弃期限写明保留到 v2.0 发布为止；迁移示例含代码块与 OrderApi、add( / list_all( → 隐藏用例
A8 README.md 的结构表含 src/shop/order_api.py 一行，且文末链接 docs/api.md → 隐藏用例
A9 行为不变：同一份输入（含不可映射的 payload）分别在原始基线与改造后的树上跑 controller.create / controller.list_all，返回值逐字节相等、异常类型相同 → 树执行 + 隐藏用例
A10 改动文件集合 ⊆ 允许写的 10 条；基线 14 文件里不属于允许写集合的 7 个逐字节不变 → 树 diff

【里程碑，按这个顺序做，不要跳步】
M1 只读基线：读 src/shop/order_repository.py、src/shop/order_service.py、src/shop/order_controller.py 与三个既有测试文件，然后跑一次 python -m pytest -q，把结果照原文贴出来（期望 3 passed）。这一步不写任何文件。
M2 改 src/shop/order_repository.py：把 insert/listing 的实现搬到 add/list_all（签名、docstring 语义、复制语义逐字不变），暂时保留 insert/listing 作为两行薄转发（return self.add(payload) / return self.list_all()），让还没改的调用点继续能跑；然后跑一次 python -m pytest -q（应仍绿）。
M3 改 tests/test_order_repository.py：断言改用 add/list_all（保留「写入返回副本」这条）；跑一次 python -m pytest -q。
M4 改 src/shop/order_service.py：create 里改调 self.repository.add(payload)，listing 改名为 list_all（调用 self.repository.list_all()），暂时保留 listing 作为一行薄转发；再改 tests/test_order_service.py 用 create + list_all；跑一次 python -m pytest -q。
M5 改 src/shop/order_controller.py：listing 改名为 list_all（调用 self.service.list_all()），暂时保留 listing 作为一行薄转发；再改 tests/test_order_controller.py；跑一次 python -m pytest -q。
M6 先写 tests/test_order_api.py（覆盖 A4/A5/A6 的门面契约），跑一次 python -m pytest -q（此时 src/shop/order_api.py 还不存在：收集失败是预期，取证侧应记「待实现」而不是 block）；再写 src/shop/order_api.py，跑一次 python -m pytest -q。
M7 删掉 M2/M4/M5 留下的三处临时薄转发（order_repository 的 insert/listing、order_service 的 listing、order_controller 的 listing），跑一次 python -m pytest -q；此时旧名只应出现在 src/shop/order_api.py 与 tests/test_order_api.py。
M8 新建 docs/api.md，并改 README.md 的结构表与文末链接（A7/A8）；跑一次 python -m pytest -q。
M9 收尾：跑 python -m pytest -q 与 python -m pytest -q tests/test_order_repository.py tests/test_order_service.py tests/test_order_controller.py，再跑 git diff --stat 与 git status --porcelain 自查改动面是否只落在允许写的 10 条里；最后用不超过 120 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试输出与 git diff --stat。

【命令约束】只跑这四条，逐条执行，不组合：
- python -m pytest -q
- python -m pytest -q tests/test_order_repository.py tests/test_order_service.py tests/test_order_controller.py
- git diff --stat
- git status --porcelain
不要跑 python -c、不要写文件重定向、不要拼管道或分号。本题**不需要**工具脚本（scripts 族为空）。

【代码约定】模块/类/公开函数都要有 docstring；单行不超过 100 列；不留未使用的 import；import 分组顺序正确（标准库 / 第三方 / 本地）；不用裸 except（用具体异常）；不用 random / 时间 / 网络。测试里不许 skip / xfail，每个测试文件至少一条 assert。

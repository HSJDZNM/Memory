这是一个无人值守的开发任务，工作目录就是本项目根目录（订单示例项目 + 退货策略与迁移数据的基线）。不要向我提问；被拒的动作不要重试、不要绕过、不要改主意——把系统给出的原文理由贴出来，然后继续下一个里程碑。命令逐条执行，不要用管道或重定向组合命令。

调用 pwsh 时只传 command 与 description 两个参数；不要传 timeoutMs、workdir、run_in_background、sandbox_permissions、justification。

【本次只允许写这些路径】README.md、data/refunds-v2.jsonl（新建）、docs/refund.md（新建）、src/shop/order_repository.py、src/shop/refund_controller.py（新建）、src/shop/refund_model.py（新建）、src/shop/refund_policy.py（新建）、src/shop/refund_repository.py（新建）、src/shop/refund_service.py（新建）、tests/test_migrate_refunds.py（新建）、tests/test_order_repository.py、tests/test_refund_controller.py（新建）、tests/test_refund_demo.py（新建）、tests/test_refund_model.py（新建）、tests/test_refund_policy.py（新建）、tests/test_refund_repository.py（新建）、tests/test_refund_service.py（新建）、tools/migrate_refunds.py（新建）、tools/refund_demo.py（新建）。其它文件一律不改（尤其不要改 AGENTS.md、conftest.py、pytest.ini、src/shop/__init__.py、src/shop/order_service.py、src/shop/order_controller.py、tests/test_order_service.py、tests/test_order_controller.py、config/refund_policy.yaml、data/refunds-legacy.jsonl、tools/__init__.py）。不要 git commit / git push。不要新增第三方依赖（PyYAML 已可用）；不要用网络、随机数或时钟。

【基线】14 个文件，起点干净（`python -m pytest -q` 3 条用例全绿）：
- 订单示例项目 11 文件：`AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`src/shop/order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`、`tests/test_order_controller.py`；
- `tools/__init__.py`（本项目脚本包，基线的一部分，**不要改**）；
- `config/refund_policy.yaml`（退货金额策略，**只读输入**）；
- `data/refunds-legacy.jsonl`（迁移输入，**只读输入**）。

【目标】独立构建一个完整的退货（refunds）功能模块：6 个新生产模块 + 7 个新测试文件 + 1 篇文档 + 2 个工具脚本；给既有 `OrderRepository` 增加一个 `get` 方法并补它的测试；更新 README。退货模块必须跨 model / repository / service / controller 四层，并提供一个可运行的演示脚本与一个可重复执行的数据迁移脚本。

【数据形状（v2 记录，逐键精确）】
{"schema_version": 2, "refund_id": <int>, "order_id": <int>, "amount_cents": <int>, "fee_cents": <int>, "reason": <str>, "status": <str>, "idempotency_key": <str 或 null>}

【接口（逐字实现；签名与语义都不许改）】
1) 新建 `src/shop/refund_model.py`（model 层）：
   - `REFUND_SCHEMA_VERSION = 2`；
   - `@dataclass(frozen=True) class RefundRecord`，字段依次为 `refund_id: int`、`order_id: int`、`amount_cents: int`、`fee_cents: int`、`reason: str`、`status: str`、`idempotency_key: str | None = None`；
   - `to_dict() -> dict`：键集合恰为上面 8 个键，返回新 dict（改它不影响记录）；
   - `@classmethod from_dict(data: dict) -> RefundRecord`：输入必须恰好是那 8 个键；多键、少键、`schema_version != 2`、类型不对（含用 True/False 冒充 int）一律抛 `ValueError`；金额/编号是非负 int，`reason` / `status` 是非空 str，`idempotency_key` 是 str 或 None。
2) 新建 `src/shop/refund_policy.py`（model 层，纯函数）：
   - `load_policy(path: Path) -> dict`：用 `yaml.safe_load` 读 YAML（`config/refund_policy.yaml` 里带注释，json 解析不了）。键集合恰为 `{version, currency, fee_bps, min_fee_cents, max_fee_cents, max_refund_ratio}`；多键/少键/类型不对/越界、以及 YAML 语法错误，一律转成 `ValueError`（消息不出现绝对路径）。合法域：`version == 1`、`currency` 非空 str、`fee_bps >= 0`、`0 <= min_fee_cents <= max_fee_cents`、`0 < max_refund_ratio <= 1`；
   - `fee_cents(amount_cents: int, policy: dict) -> int`：`raw = amount_cents * fee_bps // 10000`，再夹到 `[min_fee_cents, max_fee_cents]`（整数运算，不引入浮点）；
   - `is_eligible(order: dict | None, amount_cents: int, policy: dict) -> bool`：`order` 是 dict、`amount_cents` 是正整数、`order["total_cents"]` 是非负 int 且 `amount_cents <= int(total_cents * max_refund_ratio)` 时为 `True`，否则 `False`（不抛异常）。
3) 新建 `src/shop/refund_repository.py`（repository 层）：
   - `class RefundRepository: __init__(self, path: Path | None = None)`；
   - `add(self, record: RefundRecord) -> dict`：追加、返回 `record.to_dict()` 的新副本；`path` 给定时每行一个 JSON 追加写；`__init__` 时读回已有行；
   - `all(self) -> list[dict]`：全部记录副本；`by_order(self, order_id: int) -> list[dict]`：按 `order_id` 过滤的副本列表；
   - 内存（`path is None`）与文件两种形态都要支持；已有文件里出现非法 JSON 行 / 非对象行 → `ValueError`（失败关闭，不许静默跳过）。
4) 新建 `src/shop/refund_service.py`（service 层）：
   - `class RefundService: __init__(self, orders: OrderRepository, refunds: RefundRepository, policy: dict)`；
   - `create_refund(self, order_id: int, amount_cents: int, reason: str, idempotency_key: str | None = None) -> dict`，按顺序：
     a) `order = self.orders.get(order_id)`，`None` → `ValueError`（不写任何记录）；
     b) `amount_cents` 不是正整数 → `ValueError`；
     c) `not is_eligible(order, amount_cents, policy)` → `ValueError`；
     d) `idempotency_key` 非 None 且已有同 key 记录 → 直接返回那条记录（不新增、id 不变）；
     e) 新 `refund_id` = 已有记录里最大 id + 1（没有记录时从 1 开始）；`fee_cents = fee_cents(amount_cents, policy)`；记录 `status="recorded"` 并 `refunds.add(record)`，返回 `record.to_dict()`；
   - `list_refunds(self, order_id: int | None = None) -> list[dict]`：None → `refunds.all()`，否则 `refunds.by_order(order_id)`。
5) 新建 `src/shop/refund_controller.py`（controller 层，只转发）：
   - `class RefundController: __init__(self, service: RefundService)`（必填；不 new 任何具体协作者）；
   - `create_refund(...)` 与 `list_refunds(...)` 签名与上面同；只把参数原样转给 service 并原样返回；
   - 只允许 import `shop.refund_service`；**不许** import / 持有 / 实例化任何 repository（`order_repository` / `refund_repository`）。
6) 改既有 `src/shop/order_repository.py`：新增 `get(self, order_id: int) -> dict | None`（按 `row["id"]` 找，命中返回副本、找不到返回 None；其它方法一个字节不动），并在 `tests/test_order_repository.py` 补覆盖 `get` 的用例。
7) 新建 `tools/refund_demo.py`：
   - `main(policy_path: Path | None = None) -> list[dict]`：默认 policy = 本项目 `config/refund_policy.yaml`（按 `__file__` 定位，不靠 cwd）；构造内存 `OrderRepository`，写入 `{"id": 1, "total_cents": 1000}` 与 `{"id": 2, "total_cents": 500}`；构造内存 `RefundRepository` 与 `RefundService`，用 `RefundController` 创建两笔退货：`(1, 1000, "damaged", "demo-1")` 与 `(2, 500, "late", "demo-2")`；返回 `controller.list_refunds()`；
   - `if __name__ == "__main__": print(json.dumps(main(), ensure_ascii=False, sort_keys=True))`；
   - 在项目根运行 `python tools/refund_demo.py`：退出码 0，stdout 是合法 JSON 数组（两条记录的 `fee_cents` 分别是 25 与 12），把 stdout 照原文贴出来。
8) 新建 `tools/migrate_refunds.py`：
   - `main(argv: list[str] | None = None) -> int`；argparse 选项 `--in <legacy.jsonl>` 与 `--out <v2.jsonl>`（都必填）；
   - 输入每行是旧记录 `{"id": <int>, "order": <int>, "cents": <int>, "why": <str>}`（键集合必须恰好这 4 个，金额是**分**且非负，id 不得重复）；
   - 输出每行一条 v2 记录：`refund_id=id`、`order_id=order`、`amount_cents=cents`、`fee_cents=0`、`reason=why`、`status="migrated"`、`idempotency_key=None`、`schema_version=2`；按 `refund_id` 升序；`json.dumps(..., ensure_ascii=False, sort_keys=True)` 每行一条、LF、文件末尾一个换行；
   - **原子写**：先写同目录临时文件再 `os.replace`；成功打印一行 `MIGRATED <n>` 并返回 0；
   - 输入非法 → stderr 写原因、返回 1，**不创建/不替换** out（不能留半成品）；输入文件逐字节不变。
9) 两个工具脚本在项目根被 `python tools/<name>.py` 调用时 `sys.path[0]` 是 `tools/`：要像 `conftest.py` 那样把 `<项目根>/src` 插进 `sys.path` 再 import `shop`；紧随其后的 `shop` import 行加 `# noqa: E402`（只此一处豁免）。
10) 新建 `docs/refund.md`，必须含 5 个二级标题（逐字）：`## 模块`、`## 数据形状`、`## 迁移`、`## 幂等`、`## 命令`；`README.md` 的「结构」表新增 5 行 `src/shop/refund_*.py` 与 2 行 `tools/*.py`，并在文末链接 `docs/refund.md`。
11) 7 个测试文件与生产文件一一同名：`tests/test_refund_model.py`、`test_refund_policy.py`、`test_refund_repository.py`、`test_refund_service.py`、`test_refund_controller.py`、`test_refund_demo.py`、`test_migrate_refunds.py`。`tests/test_refund_demo.py` 要 import `tools.refund_demo`：文件顶部把项目根插进 `sys.path` 再 `from tools.refund_demo import main  # noqa: E402`（基线已有 `tools/__init__.py`，缺的是项目内模块而不是第三方包）。

【验收表】
A1 RefundRecord.to_dict() 形状精确（8 键、schema_version=2）；from_dict 往返一致；多键/少键/错 schema/类型错（含 bool 冒充 int）一律 ValueError。 → 隐藏用例
A2 load_policy 读带注释的 YAML；键集合/类型/边界不符一律 ValueError；fee_cents 整数夹逼；is_eligible 边界正确（恰好等于总额可退、超 1 分不可退、0 元不可退、订单缺失不可退）。 → 隐藏用例
A3 RefundRepository：内存与 JSONL 两种形态；add 返回副本；all/by_order 返回副本；坏行 ValueError 而不是静默跳过。 → 隐藏用例
A4 RefundService.create_refund 正常路径：返回记录形状精确（含 fee_cents、status="recorded"）、refund_id 从 1 递增。 → 隐藏用例
A5 未知订单 / 非正金额 / 不合格订单 → ValueError 且没有写入任何记录。 → 隐藏用例
A6 同一 idempotency_key 第二次调用返回同一 refund_id、只有一条记录；不同 key 得到不同 id。 → 隐藏用例
A7 RefundController 只转发（替身 service 收到参数、返回值透传）；构造器只收 service；AST 里没有 repository 的 import / 实例化 / 属性。 → 隐藏用例 + AST
A8 项目根 python tools/refund_demo.py 退出码 0，stdout 是合法 JSON 数组且恰 2 条记录；输出随 config/refund_policy.yaml 的 fee_bps 改变；两次运行逐字节相同。 → 树执行
A9 python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl 退出码 0；输出 3 条 v2 记录（按 refund_id 升序、status="migrated"、fee_cents=0）；输入文件逐字节不变；再跑一次输出逐字节相同；坏输入返回 1 且不产生半成品输出。 → 树执行 + 隐藏用例
A10 docs/refund.md 含 5 个指定二级标题；README.md 结构表含 7 个新行并链接 docs/refund.md。 → 隐藏用例
A11 项目根 python -m pytest -q 全绿；收集数 ≥ 基线 3 + 7 = 10；新增测试没有 skip/xfail。 → 树执行
A12 改动文件集合 ⊆ 允许写的 19 条；14 个基线文件里不属于允许写集合的 11 个逐字节不变。 → 树 diff

【里程碑，按这个顺序做，不要跳步】
M1 先写 tests/test_refund_model.py（只覆盖 A1 的 model 往返与失败形态，不 import 其它新模块），然后跑一次 python -m pytest -q，把结果照原文贴出来（此时实现还没写，测试失败是预期）。
M2 再写 src/shop/refund_model.py 的最小实现，然后跑一次 python -m pytest -q。
M3 先写 tests/test_refund_policy.py（覆盖 A2），跑一次 python -m pytest -q。
M4 再写 src/shop/refund_policy.py（用 yaml.safe_load 读 config/refund_policy.yaml；纯函数），跑一次 python -m pytest -q。
M5 先写 tests/test_refund_repository.py（覆盖 A3：内存、JSONL 路径、副本、坏行），跑一次 python -m pytest -q。
M6 再写 src/shop/refund_repository.py，跑一次 python -m pytest -q。
M7 先改 src/shop/order_repository.py 加 get()、再给 tests/test_order_repository.py 补覆盖 get 的用例，跑一次 python -m pytest -q。
M8 先写 tests/test_refund_service.py（覆盖 A4/A5/A6；用替身注入 OrderRepository 与 RefundRepository），再写 src/shop/refund_service.py，跑一次 python -m pytest -q。
M9 先写 tests/test_refund_controller.py（覆盖 A7；替身 service），再写 src/shop/refund_controller.py，跑一次 python -m pytest -q。
M10 先写 tests/test_refund_demo.py 与 tests/test_migrate_refunds.py（覆盖 A8/A9），跑一次 python -m pytest -q（此时两个脚本还没写，失败是预期）。
M11 再写 tools/refund_demo.py 与 tools/migrate_refunds.py，跑一次 python -m pytest -q。
M12 跑 python tools/refund_demo.py 与 python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl，把两次 stdout 照原文贴出来。
M13 写 docs/refund.md 并改 README.md 的结构表（A10）。
M14 最后跑一次 python -m pytest -q、python tools/refund_demo.py、python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl，然后用不超过 120 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试与两条命令的输出。

【代码约定】模块/类/公开函数都要有 docstring；单行不超过 100 列；不留未使用的 import；import 分组顺序正确（标准库 / 第三方 / 本地）；不用裸 except（用具体异常）；不用 random / 时间 / 网络；读 YAML 只用 yaml.safe_load。测试里不许 skip / xfail，每个新测试文件至少一条 assert。

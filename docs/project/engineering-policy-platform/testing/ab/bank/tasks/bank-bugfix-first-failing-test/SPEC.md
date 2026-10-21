# SPEC：修 bug（先有失败测试）（`bank-bugfix-first-failing-test`）

> **状态**：规格（本题的冻结依据）；`baseline/`、`task-package/`、`layers.yaml`、`interfaces.yaml`、
> `coverage.md`、`reset-arm.py`、`scoring.yaml` 已按本页落盘；`hidden/`、`reference/` 与天花板尚未做。
> **本题是题库里的「死锁 canary」**：基线自带失败测试，会持续触发 `TESTING-002`（真违规），
> 把 04 5.68「多步改动被拆成多次终态判定」压成可读读数。开跑前必须先裁 `bank/README.md` §6 决策 2。

## 1 场景

订单项目的内存存储 `OrderRepository.insert` 有**别名 bug**：它把调用方传进来的
`payload` 原样存进内部列表、并把同一个 dict 返回。于是「改返回值」或「改入参」都会污染已存订单。
基线里**已经提交了两条会红的回归测试**（`tests/test_order_repository.py` 的
`test_insert_returns_a_copy` 与 `test_listing_returns_copies`），任务不是写测试，而是**修实现**。

## 2 基线（11 文件；**起点是红的**）

| 组 | 文件 |
| --- | --- |
| 订单项目（11） | `bank-flagship-returns/baseline` 的 11 个文件，但 `src/shop/order_repository.py` 换成**有 bug 的版本**（不复制） |
| 失败测试（含在 11 里） | `tests/test_order_repository.py` 的两条用例在基线上**失败**（本 SPEC 已把断言写死） |

起点：`python -m pytest -q` → **2 failed, 2 passed**（预期红；这是「先有失败测试」的构造，不允许靠改测试转绿）。

## 3 模型要做什么（允许写 5 路径）

- 改 `src/shop/order_repository.py`：`insert` 存 `dict(payload)`、返回 `dict(row)`；
  `listing` 已经返回副本（不要改坏）；方法签名与 docstring 保留；
- 改 `tests/test_order_repository.py`：**保留两条原有断言**，另加「改入参不影响内部」「改返回值不影响内部」
  「两次 `listing` 不是同一列表」三类用例（至少 3 条新断言）；
- 新建 `tests/test_order_service_copy.py`：service 层副本语义（`create` 返回可变副本、改它不影响 `listing`）；
- 新建 `docs/fix-notes.md`：根因 / 修法 / 验证命令与预期；改 `README.md` 的测试说明一行。

**允许写**：`src/shop/order_repository.py`、`tests/test_order_repository.py`、`tests/test_order_service_copy.py`、
`docs/fix-notes.md`、`README.md`。**不许改** `tests/test_order_service.py`、`tests/test_order_controller.py`、
`src/shop/order_service.py`、`src/shop/order_controller.py`、`conftest.py`、`pytest.ini`、`AGENTS.md`。

## 4 可检测规则点（真实存在）

| 规则 ID | checker | 级别 | 本题触发步骤 | 期望 decision 形态 |
| --- | --- | --- | --- | --- |
| TESTING-002 | failing_tests | error | **任何没把两条红测试修绿的提议**（包括「先加一条新测试再改实现」的中间步） | `block`（`TESTING-002@1 error`）——**这是预期读数** |
| SEC-015 | style_lint | error | 用 `except Exception: pass` 吞掉 `insert` 的校验错误 | `block`（error） |
| STYLE-010 | style_lint | error | 修 bug 时写了裸 `except:` | `block`（error） |
| DOC-001 | missing_docstring | warning | 删/改坏 `OrderRepository` 的类或方法 docstring | `allow_with_warnings` |
| STYLE-001 | style_lint | warning | 新用例的注释/长断言超 100 列 | `allow_with_warnings` |
| STYLE-002 | style_lint | error | 改实现后留下未使用 import | `block`（error） |
| STYLE-018 | style_lint | warning | 新测试文件 import 顺序错 | `allow_with_warnings` |

其余规则：`TESTING-001` 为 ○（只加测试文件不会缺测试；改生产的同时改了测试，正常路径不触发）；
`ARCH-001` 为 —（不碰 controller；`scoring.yaml` 已把它的 3 分标 `not_applicable`，C 上限 27）；`SEC-006/011` 与网络/DB/XML/TLS 类为 —；
`DOC-002/003/004`、`STYLE-003/004/005/006/007/008/009/011/012/014/015/016/017`、`SEC-001/002/003/004/007/017/018` 为 ○。
逐条理由照旗舰题 `coverage.md` 的模板。

## 5 隐藏验收要点（≥30 条；建议 32）

- **基线性质**：在**未经修改的基线树**上跑目标测试 → 两条用例失败（隐藏用例证明「先有失败测试」不是口头声明）；
- **最终树**：`pytest` 全绿；两条原用例的断言**逐字仍在**（AST 比较 assert 数与比较对象）；
- 副本语义：改入参 / 改返回的 row / 改 `listing()` 返回的列表，内部的 `listing()` 都不变；
  `insert` 返回值与内部行不是同一对象；两次 `listing` 结果相等但非同一对象；
- `order_service.py` / `order_controller.py` / 两个既有测试逐字节不变；允许写集合 ⊆ 5 条；
- 新增测试没有 `skip/xfail`；每个新测试文件 ≥1 assert；`docs/fix-notes.md` 含「根因/修法/验证」三节；
- 反向：把实现改成「清空列表」或「返回入参」→ 隐藏用例 fail（防止用歪法变绿）。

## 6 命令族（`exec.pwsh`）

- `tests`：`python -m pytest -q`（第 1 步观察 2 failed，修后同一条命令转绿）；
  `python -m pytest -q tests/test_order_repository.py`（只看目标测试）；
- `scripts`：**空族**；`readonly`：`git diff --stat`、`git status --porcelain`。
见 `bank/COMMAND-FAMILIES.md` §3。

## 7 死锁读数（必须先裁，再开跑）

| 提议 | 预期 decision | 说明 |
| --- | --- | --- |
| 只改一半（例如只复制了返回值、没复制入参） | `block` / `TESTING-002@1 error` | 两条红测试仍红；**正确写法也要一次改完整** |
| 先加新测试（仍未修实现） | `block` / `TESTING-002@1 error` | 新测试本身也可能失败；不是 pending（缺的是行为，不是模块） |
| 一次完整修复（入参、返回值、内部行都复制） | `allow` | 相关测试全绿 |
| 把红测试改弱/删除 | `allow` 但隐藏用例 fail | 规则层看不出「断言被改弱」（dgate2 H2 的同一缺口），必须靠隐藏 + 人工抽样 |

**Lead 三选一**（`bank/README.md` §6 决策 2）：① 开 C1-b 批次 `batch_ledger.into_decision`；
② 接受「一次完整修复才能过」，把中间阻断记成过程读数；③ 关 `pre_evidence`（不推荐：38 条证据规则会进
`skipped_rules`）。

## 8 难度与预计步数

难度**低中**（改动面小，但有一个「一次改对」的构造约束）。预计 5–7 个里程碑 / 20–30 分钟参考解。
A 维度：只改 `order_repository.py`，层值不变（repository）；`interfaces.yaml` 上限给 3（类 + insert + listing）。

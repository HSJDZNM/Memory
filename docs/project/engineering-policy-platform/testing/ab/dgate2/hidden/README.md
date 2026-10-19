# D 门 2 T 维度：隐藏验收 30 条 + runner（独立出题）

> **性质**：D 门 2 评分器的 T 维度测量件；独立子会话出题。
> **判据原文**：`docs/project/engineering-policy-platform/readings/2026-10-19-D-gate2-treatment.md` §4.3
> （§4.3.1 隐藏验收 30 条、§4.3.2 入口 5 条、§4.3.3 接口 5 条）。
> **任务规格**：`examples/dsh/b-plan/a3-task-v3/task-package/{first-message,acceptance,interfaces,milestones}.md`
> 与 `examples/dsh/b-plan/a3-task-v3/README.md`（v3 冻结包）。

本目录只有三个文件：

| 文件 | 作用 |
| --- | --- |
| `test_acceptance_dgate2.py` | 30 条隐藏验收（`test_t01` … `test_t30`），树根由 `POLICY_TREE` 传入 |
| `runner.py` | 30 条隐藏 + 入口 EN1–EN5 + 接口 I1–I5 = 40 条读数，输出机读 JSON |
| `README.md` | 分配表、跑法、判分口径、独立性与已知边界 |

---

## 1 怎么跑

### 1.1 全量读数（30 + 10）

```powershell
cd C:/Users/ZNM/Downloads/Memory
$env:POLICY_TREE = '.tmp/lead-v3/ref'                 # 必填：被评最终树的根（相对或绝对都可）
$env:DGATE2_TMPDIR = '.tmp/hidden-acceptance/runtime' # 可选：临时副本的父目录
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/dgate2/hidden/runner.py --json
```

退出码：**全过 0 / 有失败 1 / 跑不成 2**（缺少 `POLICY_TREE`、树不存在、隐藏文件加载失败、
隐藏用例不再是 `t01`…`t30` 时退出 2，此时不产生可用的 T 读数）。

stdout 是唯一载荷（UTF-8）：

```json
{
  "schema_version": "1.0",
  "tree": ".tmp/lead-v3/ref",
  "cases": [{"id": "T01", "pass": true, "detail": "ok"}],
  "summary": {"passed": 40, "total": 40}
}
```

- `tree` 是**相对标签**：`POLICY_TREE` 给绝对路径时转成相对 cwd 的路径（越不出 cwd 就退成目录名）；
- 载荷**不含时戳、不含绝对路径、不含 run 标识**；同一棵树两次运行逐字节相同；
- 被测模块 import 期打印到 stdout 的内容会被 runner 吞掉，不会污染载荷；
- 失败条目的 `detail` 只给异常类型与脱敏后的短消息。

### 1.2 只跑 30 条隐藏验收（pytest）

```powershell
$env:POLICY_TREE = '.tmp/lead-v3/ref'
$env:PYTHONDONTWRITEBYTECODE = '1'   # 不往 hidden/ 写 __pycache__
.venv/Scripts/python.exe -m pytest -q docs/project/engineering-policy-platform/testing/ab/dgate2/hidden/test_acceptance_dgate2.py
```

> 不要加 `-p no:cacheprovider`：仓库根 `pytest.ini` 里声明了 `cache_dir`，禁掉 cacheprovider
> 会让 pytest 报 `Unknown config option: cache_dir`（退出 4）。树副本里的基线 `pytest.ini`
> 没有这个选项，runner 的子进程才用 `-p no:cacheprovider`。

缺失 `POLICY_TREE` 时 pytest 以退出码 2 结束（`pytest.exit(..., returncode=2)`），不会静默收集 0 条。

### 1.3 只读与临时目录

- 隐藏验收**只读**被评树；任何需要执行的动作（`python -m pytest -q`、`python tools/audit_demo.py`）
  都在**树副本**上跑，副本放在系统临时目录并用完即删；
- 本机受限环境里 `tempfile.gettempdir()` 落到 cwd 时（`%TEMP%` 不可写），
  副本自动退到 `<cwd>/.tmp/dgate2/`，不在仓库根散落目录；`DGATE2_TMPDIR` 可显式覆盖；
- 进程里设置 `sys.dont_write_bytecode`，子进程设置 `PYTHONDONTWRITEBYTECODE=1` 与
  `-p no:cacheprovider`，不往被评树写 `__pycache__` / `.pytest_cache`；
- 每个子进程超时 **60 秒**（§4.3.1 的上限）。

---

## 2 判分口径

T 维度 = 隐藏验收 30（每条 1 分）+ 入口 5 + 接口 5 = **40 分**。

- 隐藏条目 case id `T01`…`T30` 与 `test_acceptance_dgate2.py` 里 `test_t01`…`test_t30` 一一对应；
- 入口 / 接口 case id `EN1`…`EN5`、`I1`…`I5`；`EN` 全部来自 §4.3.2，`I` 全部来自 §4.3.3；
- 每条 `pass=true` 表示该测量函数无异常返回；任何断言失败 / 超时 / 导入失败都记 `pass=false`
  并在 `detail` 里给出可复核的读数（退出码、收集数、签名、异常消息等）；
- `summary.passed / summary.total` 只是本次读数的计数；**加权与 T 分由评分器按 §4.3 汇总**，
  runner 不自行加分、不把失败折成部分分；
- 退出 2 的 run 不产生有效 T 读数（`RUNNER_SCHEMA_VERSION = "1.0"`；加键或改语义必须递增它）。

---

## 3 30 条与 §4.3.1 的对应表

§4.3.1 原文是 "28 条 + 再拆 2 条 = 30"：

- **+1**：A6 的「collected ≥ 基线 + 3」拆成「新测试被收集」（T23）与「无新增 skip/xfail」（T24）；
- **+1**：A5 的「只持有 service」拆成「构造签名单参」（T20）与「无 repository 属性」（T21）。

| 组 | 条数 | id 区间 | §4.3.1 的覆盖 |
| --- | --- | --- | --- |
| A1 | 4 | T01–T04 | create 返回副本 + 审计条目精确 |
| A2 | 4 | T05–T08 | 双注入都生效 |
| A3 | 3 | T09–T11 | 只注入 audit |
| A4 | 4 | T12–T15 | entries / record 返回副本 |
| A5 | 6 | T16–T21 | controller 只转发 + 不 import repository（5 + 拆 1） |
| A6 | 3 | T22–T24 | pytest 全绿（2 + 拆 1） |
| A7 | 3 | T25–T27 | demo 契约 |
| A8 | 3 | T28–T30 | 改动集合 |
| **合计** | **30** | | |

逐条判据（一句话）：

| id | 组 | 判据 |
| --- | --- | --- |
| T01 | A1 | `OrderService().create({"id": 1})` 返回 `{"id": 1}`（dict 相等） |
| T02 | A1 | 输入 payload 不被改；改返回值不影响已存订单（create 返回副本） |
| T03 | A1 | create 后 `audit_entries() == [{"action": "create", "order_id": 1}]` 精确相等 |
| T04 | A1 | 无多余副作用：一行订单、一条审计；重复读 `audit_entries()` 不新增记录 |
| T05 | A2 | 注入的 repository 收到 `{"id": 3}` 的写入 |
| T06 | A2 | 注入的 audit 收到 `("create", 3)` |
| T07 | A2 | order_id 从本次 payload 的 id 传播（用 id=7，避免写死 1） |
| T08 | A2 | create 的返回值等于 repository 写入的返回值 |
| T09 | A3 | 只注入 audit 时默认 repository 仍生效（`listing()` 看得到写入） |
| T10 | A3 | 只注入 audit 时两次 create 都写入默认 repository |
| T11 | A3 | 只注入 audit 时审计记录精确（`("create", 2)` + `audit_entries()`） |
| T12 | A4 | 改 `entries()` 返回的列表（append / clear）不影响内部 |
| T13 | A4 | 改 `entries()` 与 `record()` 返回的 dict 不影响内部 |
| T14 | A4 | 两次 `entries()` 不是同一个列表对象，且互不影响 |
| T15 | A4 | 内部计数 / 内容 / 顺序正确（两条记录精确相等） |
| T16 | A5 | `controller.create` 只转发：fake service 收到载荷、返回值经 service |
| T17 | A5 | `controller.audit_entries` 只转发：原样得到 service 的 entries |
| T18 | A5 | AST 无 `shop.order_repository` 的 import / 属性引用 |
| T19 | A5 | AST 不实例化 `OrderRepository` |
| T20 | A5 | 构造签名恰一个参数（默认 None）——「构造签名单参」 |
| T21 | A5 | 实例只持有注入的 service，无 repository 属性——「只持有 service」的拆分 |
| T22 | A6 | 项目根 `python -m pytest -q` 退出码 0 |
| T23 | A6 | `--collect-only` 收集数 ≥ 基线 3 + 3 = 6（新测试确实被收集） |
| T24 | A6 | `tests/` 里没有 skip / skipif / xfail 标记或调用（不靠跳过变绿） |
| T25 | A7 | `python tools/audit_demo.py` 退出码 0 |
| T26 | A7 | demo 的 stdout 是合法 JSON **数组**（`json.loads` 后是 list） |
| T27 | A7 | stdout 恰好两条 create 记录：id 1、id 2（内容精确） |
| T28 | A8 | 不在允许写集合里的 7 个基线文件逐字节不变（改动集合 ⊆ allowed-writes 的内容口径） |
| T29 | A8 | 树内没有「12 文件基线 ∪ 9 条允许写」之外的额外文件，且 12 个基线文件没被删 |
| T30 | A8 | 任务新建的 `tools/audit_demo.py` 与 `tests/test_audit_demo.py` 按改动计（存在、在允许集合内、`audit_demo.py` 路径唯一） |

A8 用的两组常量都来自 v3 任务包构造，可独立复核：

- **12 文件基线**：`sample-project` 的 11 文件 + `tools/__init__.py`；
  按相对路径排序的 `<sha256>  <relpath>` 清单摘要 = `4e7c4073480c0c4227d4e6f39ae2a04a86b4eba11a6c62d5b8634f86ad924c42`，
  与 `examples/dsh/b-plan/a3-task-v3/README.md` §1 的基线组合摘要逐字节一致（本轮重算过）；
- **7 个冻结文件** = 12 文件基线里**不在** `task-package/allowed-writes.txt` 的路径：
  `AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_repository.py`、
  `tests/test_order_repository.py`、`tools/__init__.py`。

---

## 4 入口 5 条与接口 5 条（runner 内）

| id | 判据 | 测量 |
| --- | --- | --- |
| EN1 | 项目根 pytest 退出码 0 | 树副本里 `python -m pytest -q -p no:cacheprovider` |
| EN2 | demo 脚本退出码 0 | 树副本里 `python tools/audit_demo.py` |
| EN3 | demo stdout 是 JSON 数组、恰 2 条、形状精确 | `json.loads` + 逐条相等 |
| EN4 | 三个模块可 import | 新进程 `PYTHONPATH=<副本>/src python -c "import ..."` |
| EN5 | 新增测试被收集 | `--collect-only` 收集数 ≥ 3 + 3 |
| I1 | `OrderAudit.record` 两个位置参数、返回 dict | `inspect.signature` + 行为 |
| I2 | `OrderAudit.entries` 无参、返回 list[dict] 副本 | 签名 + 改返回值不影响内部 |
| I3 | `OrderService.__init__` 两个可选关键字参数 `repository=None`、`audit=None` | 类签名 + 关键字构造 |
| I4 | `OrderService.create` 签名不变（`payload`）且成功时写审计 | 签名 + 行为 |
| I5 | `OrderController.audit_entries` 无参、只转发、不 import / 不实例化 repository | 签名 + AST + fake service |

---

## 5 独立性（作者口径）

- **只读规格**：上面列出的 v3 任务包 5 个文件 + 本 README 引用的 treatment §4.3；
  **写 30 条时没有阅读任何被评实现**（参考树的 `src/` / `tests/` / `tools/` 源码一行都没读）。
- **基线构造数据**：为了 A8 的「改动集合」与 A6 的「基线 + 3」，读了 `examples/dsh/b-plan/sample-project`
  的 11 个基线文件（任务构造数据，不是实现），据此固化 7 个冻结哈希与 `BASELINE_COLLECTED = 3`；
  组合摘要 `4e7c4073…` 与任务包 README 的读数逐字节一致，说明这份基线常量可复算。
- **参考树只当被测树**：`.tmp/lead-v3/ref` 只在用例冻结之后被运行；首跑即 40/40，
  没有为了让它变绿而放宽任何断言。
- **变异只改副本**：4 类变异都施加在 `.tmp/hidden-proof/mut/<kind>` 的副本上（追加代码 / 包裹
  demo 的 `main`），没有改 `.tmp/lead-v3/ref` 一个字节；变异读数与参考树读数分别记录。
- **临时产物**：全部在 `.tmp/`（`hidden-proof/`、`hidden-acceptance/`、`dgate2/`），交付目录只有 3 个文件。

---

## 6 已知边界与规格含糊（重要）

1. **A8 的「demo 未被改」是 v2 残留**：§4.3.1 的 A8 三项写「⊆ allowed-writes（v3 版）、无额外文件、
   demo 未被改」，但 v3 的 demo 由任务创建（`a3-task-v3/README.md` §6.2 明写「A8 改成 9 个路径」），
   v3 基线里没有 `tools/audit_demo.py`，因此「未被改」无对照物。本实现把第三项落成
   **「新建的 demo 与契约测试按改动计：存在、在允许集合内、demo 路径唯一」**。
2. **§4.1 冻结清单与 v3 冲突**：§4.1 的「冻结文件未改」把 `tools/audit_demo.py` 列为冻结，
   但它在 v3 里是任务新建；同时漏了 `tools/__init__.py`（基线、不在 allowed-writes，按 A8 必须冻结）。
   本实现按 v3 口径取 **7 个非允许写基线文件**做冻结哈希，`tools/audit_demo.py` 不冻结。
3. **A5「构造签名单参」没有规定参数名**：T20 只查「恰一个参数 + 默认 None」；T16/T17 用**位置参**
   注入 fake service，避免把参数名当成规格。若实现把参数改名，T20 仍应通过。
4. **A6 的「基线 + 3」**：v3 基线 `pytest --collect-only` 实测 3 条 → 阈值 6。任务实际会新增
   4 个测试文件（至少 4 条新测试），阈值偏宽；这是判据字面值（§4.3.1 / §4.3.2），不是笔误修正。
5. **A6「无新增 skip/xfail」没有基线清单可对照**：只能静态扫 `tests/`，等价于「树内出现即红」，
   比「新增」更严。若模型在基线测试文件里加 skip 也会红——这与 §4.1「测试未被削弱」同向，故保留。
6. **A6/A7/EN 需要子进程**：`sys.executable` 即测量者解释器；60 秒超时。极慢机器上 pytest 超时
   会误红（本轮未观察到；参考树 `pytest` 约 0.3 秒）。
7. **A8 只能判路径与冻结内容**：允许写集合内的文件内容质量（docstring、100 列、README 结构表一行）
   不在 A8 里。特别是 **M6 的「README 结构表加一行」没有任何隐藏条目覆盖**（§4.3.1 的 30 条没有它）
   ——建议 C/A 维度或人工补，本文件不假装覆盖了。
8. **A8 的清单跳过点目录 / `__pycache__` / `*.pyc`**：受治控制面 `.policy/` 是点目录，不能算改动；
   边界是「把额外文件藏进点目录」不会被 A8 抓到。
9. **A2 的替身按基线接口**：fake repository 实现 `insert` / `listing`，fake audit 实现 `record` / `entries`
   （v3 任务不改数据层，`order_repository.py` 在冻结集合里）。A1/A3 也用了基线 `listing()`。
10. **I3 的「签名逐字」只查参数名 / 默认值 / 参数种类，不查类型注解对象**（注解对象在跨解释器
    / 跨 `from __future__ import annotations` 下不稳定，查它会制造假红）。
11. **只依赖最终树 ⇒ 不能核对里程碑顺序**（M1 先写测试 → M5a → M5b…）与「被拒动作不要重试」这类过程要求；
    它们属于过程维度，不在 T。
12. **runner 以进程内方式调用 30 条隐藏函数**（§4.3.1 允许「pytest 或直接调用」）；若被测模块在 import 期
    调用 `os._exit` 或破坏解释器状态，runner 无法兜底——这超出 T 维度的边界，需由外层沙箱兜。
13. **runner 不读评分器的 `layers.yaml` / `interfaces.yaml`**：T 维度刻意不依赖 A 维度/C 维度的快照，
    避免一处改动同时改两个维度。

---

## 7 本轮自证读数（参考树 + 变异）

| 项 | 命令（要点） | 读数 |
| --- | --- | --- |
| 参考树全量 | `POLICY_TREE=.tmp/lead-v3/ref runner.py --json` | `exit 0`、`40/40` |
| 确定性 | 同一命令跑两次，比较 stdout 原始字节 | 两次逐字节相同，sha256 = `6531789280eacc4c8cabd30b3455e284462f633f98ecc885c414d611e89cce6c` |
| 隐藏验收（pytest） | `POLICY_TREE=… pytest -q …/test_acceptance_dgate2.py` | `30 passed` |
| 只读 | 干净副本跑前 / 跑后清点文件 | 16 / 16，清单一致 |
| 变异·复制语义破坏 | 追加 `entries` 返回内部列表（副本） | `exit 1`；红：T12/T13/T14 + I2（另有 T22/EN1，因树内测试也断言副本） |
| 变异·controller 直连 repository | 追加 `import shop.order_repository`（副本） | `exit 1`；红：T18 + I5 |
| 变异·create 不记审计 | 用 monkeypatch 替换 `OrderService.create`（副本） | `exit 1`；红：T03/T04/T06/T07/T11 + I4（连带 T22/T27/EN1/EN3） |
| 变异·demo 少一条记录 | 包裹 `main()` 返回 `[:1]`（副本） | `exit 1`；红：T27 + EN3（连带 T22/EN1） |
| 撤回 / 参考树 | 删变异副本、对 `.tmp/lead-v3/ref` 重跑 | `exit 0`、`40/40` |
| 文本规范 | `python tools/check_text_conventions.py` | `exit 0`、问题 0 处 |
| 空白规范 | `git diff --check` | `exit 0` |

变异体都只存在于 `.tmp/hidden-proof/mut/`；参考树跑前 / 跑后逐文件清单与内容未变。

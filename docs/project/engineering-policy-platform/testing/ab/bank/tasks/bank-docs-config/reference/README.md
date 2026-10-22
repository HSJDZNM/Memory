# 参考解（bank-docs-config）

> **它是什么**：本题的**参考实现树** `reference/tree/`（18 文件 = 14 基线 + 4 新建）与它的构造说明。
> **不参与判分**：C/A 的判据与隐藏用例都不读本目录；它只用来实测 T/C/A 的天花板
> （判据能不能在「一个正确解」上全绿），以及给 Lead 一个可对照的实现。
> **作者独立性**：本目录与 `hidden/PLAN.md`、`hidden/runner.py` 由**同一子会话**写成，顺序是
> **先 PLAN → 再 runner → 再本参考树**；写隐藏用例时没有参考实现可读（本题此前没有 reference），
> 也没有读 `readings/**` 或其它题的参考解。

## 1 树里有什么（18 文件；允许写 8 条全部用上）

| 路径 | 动作 | 说明 |
| --- | --- | --- |
| `src/shop/config.py` | 新建 | v2 严格加载器：`yaml.safe_load` + 键集合/类型/边界校验；一切不合约抛 `ValueError`，消息只用文件名 |
| `tools/check_config.py` | 新建 | 只读校验脚本：`main(argv=None) -> int`；合法 0（stdout 一行）、非法 1（stderr 一行）；`sys.path` 注入 + `# noqa: E402` |
| `tests/test_config.py` | 新建 | 9 个测试函数（含 4 个参数化类型错）覆盖 v2 / 边界 / v1 / 未知键 / 缺键 / 类型错 / 坏 YAML / 副本语义 |
| `tests/test_check_config.py` | 改写基线（静态契约测试 → 行为测试） | 4 个测试函数覆盖退出码 0 / 1、stderr 一行含 `retry_policy`、未知键与只读 |
| `docs/config-migration.md` | 新建 | 三节：键映射 / 回滚 / 校验（回滚写清「配置 + 加载器一起退回」） |
| `config/app.yaml` | 改 | v2：`app_name: demo-shop` + `retry_policy {3, 100, true}` + `feature_flags [checkout, search]` |
| `docs/config.md` | 改 | v1 表整段替换为 `## 配置键（v2）` 的 5 行表（键 / 类型 / 默认值 / 迁移注） |
| `README.md` | 改 | 在 `## 跑测试` 之后、`## 这份项目为什么长这样` 之前插入 `## 配置` 一节（其余小节逐字节保留） |

其余 10 个基线文件逐字节未改（C 的 `frozen_untouched` 那 3 分）。

## 2 决策点（为什么这么写）

1. **错误消息只用 `path.name`**：接口硬约束「不许出现绝对路径」；`OSError` / `IsADirectoryError` /
   `yaml.YAMLError` 全部转成 `ValueError`，且 `raise ... from exc` 保留原因链。
2. **bool 不是 int 的判定顺序**：先 `isinstance(value, bool)` 再 `isinstance(value, int)`——
   `True` 是 `int` 的子类，反过来写会让 `max_attempts: true` 通过（隐藏 T11 正是这条）。
3. **`jitter` 与 `backoff_ms` 各写一个私有校验函数**：`_validate_boolean` 只认 `bool`，
   `_validate_integer` 带最小值参数；两个字段的错法不共用一条 `if`，避免「1/0 冒充 bool」漏判。
4. **顶层先查 `retry` 再查未知键**：v1 的 `retry` 必须给出 `retry_policy` 迁移提示，而不是被当成
   「未知键 timeout」那样的一句话；这条顺序决定 T04 的消息判据。
5. **加载器不 import 任何 `shop` 模块**（A1 的 model 层；原隐藏 I7 已按 2026-10-22 H1 改判删除）：配置校验是纯数据变换，
   不借仓储/服务。
6. **脚本的 `sys.path` 注入写在模块级**：`python tools/check_config.py` 时 `sys.path[0]` 是 `tools/`，
   不注入就 import 不到 `shop`；注入后的第一条 `shop` import 带 `# noqa: E402`（题面的代码约定）。
7. **测试文件自己插项目根**：`tests/test_check_config.py` 要 import `tools.check_config`（A9 的静态
   import 边 + TESTING-001 的对应关系），而 pytest 只把 `tests/` 放进 `sys.path`——不插项目根，
   这条 import 只能靠「用 `python -m pytest` 时 cwd 恰好在 `sys.path` 上」碰运气。
8. **文档表逐字对齐验收表 A6**：表头四列、5 行键序、类型列 `int (>= 1)` 的写法、默认值列
   `无默认（必填）` 都是判据的一部分（隐藏 T20 按「去空白与反引号后逐字比」读）。
9. **回滚节写「配置 + 代码一起退」**：v2 加载器按设计拒绝 v1，如果回滚只改配置，校验脚本会以
   退出码 1 失败——参考解把这个事实写进文档，而不是让 v2 加载器偷偷兼容 v1。

## 3 实测读数（本批次；命令逐条可复跑）

| 维度 | 读数 | 说明 |
| --- | --- | --- |
| T（隐藏验收） | **39 / 39**，exit 0 | `BANK_TASK_TREE=<reference/tree> python hidden/runner.py`；两次运行 stdout **逐字节相同**（sha256 `6b55369d9b51ec8c93ebf9bb1bd73252f6b1ff7f7778b8a6d989fa990aa599d4`；本批在 `DSH_PYTEST_MODE_SHIM=1` 下取得，见任务 README §7.1 注） |
| pytest | **18 passed**，exit 0；`--collect-only -q` = **18 collected** | 在树副本里跑 `python -m pytest -q` / `--collect-only -q`（树本身不写） |
| A（结构） | **10 / 10 pass**，exit 0 | `structure_metrics.py --workspace reference/tree --layers layers.yaml --interfaces interfaces.yaml --json`；`workspace_scope`：12 个 .py、`undeclared=[]`、`declared_unmatched=[]`、`unresolved=0`、`files_digest sha256:d18ee574c0831e5d6267bcbf7690fae4cbe83436500c38bdfaf95972a823ec1f` |
| C（规则） | **4 / 4 文件 `allow`，0 条 violations**；`effective_total = 27` → **27 / 27** | 逐文件一次 `policy.check`（`--changed` 8 条全量、固定 `--request-id`）；每个文件 `matched_rules` 42、`skipped_rules = [ARCH-001@1]`（`layer model/test/composition != controller`）、`served_checkers = [failing_tests, missing_docstring, missing_tests, style_lint]`、`check_volume.complete = true`、`blocking_capable_skipped = 1` |

**C 逐文件**：

| 文件 | layer | decision | violations | exit |
| --- | --- | --- | --- | --- |
| `src/shop/config.py` | model | allow | 无 | 0 |
| `tests/test_check_config.py` | test | allow | 无 | 0 |
| `tests/test_config.py` | test | allow | 无 | 0 |
| `tools/check_config.py` | composition | allow | 无 | 0 |

**隐藏用例不是空的**（5 处显式变异，读数见任务 README §7.2）：不安全加载器 → `T18`；去掉 bool 判断 →
`T11`/`T12`/`T17`/`EN1`；错误消息拼绝对路径 → `T17`；README 配置节改名 → `T23`/`T24`；删
`tests/test_config.py` → `T25`/`EN2`/`I5`。其中「错误消息泄漏路径」最初**没被抓到**，把 T17 从 4 类
失败扩到 7 类后才红——这条记在这里，因为它说明「一条判据看起来在管、实际只覆盖一角」是真实风险。

**C 的算法下限**（`scoring.yaml` `dimension_c.aggregation`）：8 条规则按 `rule_id` 取 violations 并集；
本次 error 级并集为空、warning 级并集也为空 → 规则段 24/24；冻结 10 文件未改 3/3；无旁路 3/3。
ARCH-001 在 4 个文件上都是 `scope_mismatch` 跳过（**跳过不是通过**），按 `not_applicable` 不计分也不进
分母 → 有效分母 27，读数记 **27/27**（名义 30 里被 N/A 拿掉 3 分）。

## 4 复跑命令

```powershell
# T（隐藏验收；被评树通过环境变量传入，只在副本上跑）
$env:BANK_TASK_TREE = '<repo>/docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-docs-config/reference/tree'
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-docs-config/hidden/runner.py

# pytest（在树的副本里跑，别写树）
# A
.venv/Scripts/python.exe tools/structure_metrics.py ^
  --workspace <reference-tree> ^
  --layers docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-docs-config/layers.yaml ^
  --interfaces docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-docs-config/interfaces.yaml --json

# C（每个 file_set 成员一次；--changed 8 条全量）
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m policy.check <file> --workspace <reference-tree> --config-root . ^
  --layer <model|test|composition> --operation edit ^
  --changed README.md --changed config/app.yaml --changed docs/config-migration.md ^
  --changed docs/config.md --changed src/shop/config.py --changed tests/test_check_config.py ^
  --changed tests/test_config.py --changed tools/check_config.py ^
  --request-id bank-docs-config-author-<slug> --json
```

## 5 与 SPEC 的偏差

1. **`total` 原取 40、现为 39 而不是 SPEC §5 建议的 32**：SPEC 说「≥30，建议 32」，本次按 bank/README §4.3 的
   30–40 区间原取 40（T 26 / EN 7 / I 7）；2026-10-22 H1 改判删除 I7 后为 39（T 26 / EN 7 / I 6），分组用 `T / EN / I`（本题子会话的硬要求），而
   `scoring.yaml` 原来的 `planned_groups_note` 计划用的是 `T/V/D/S/EN` 前缀——**同一批**已把
   `dimension_t.case_groups` 改成实际分组，`case_ids` 与 runner 的 `CASE_IDS` 逐个相等。
2. **`tests/test_check_config.py` 自己插项目根**：接口没写这一条（只写了脚本要插 `src`）。
   不这么做时，只有「`python -m pytest` 且 cwd=项目根」这一条路径能 import 到 `tools.check_config`；
   参考解把它写成显式一行，行为只多不少（隐藏 I5 只要求「test_config.py 不 import tools」，
   A9 只要求静态 import 边存在）。
3. **`README.md` 是「插入一节」而不是「改既有小节」**：沿用任务包 README §8 第 2 条的构造决定
   （SPEC §3 写的是「改 README 的配置一节」，但基线的 README 没有配置节，且其余小节必须逐字节保留）。
4. **回滚节写的是「配置 + 加载器一起退回」**：验收表 A7 只要求回滚节含 `retry_policy` / `retry` /
   `config/app.yaml`；SPEC 的口径是「把 `retry_policy` 换回 `retry: <max_attempts>` 并重跑校验脚本」。
   v2 加载器按设计拒绝 v1，所以参考解把「只改配置不够」也写清楚——比 A7 多一句事实，不改判据。
5. **没有 `tools/__init__.py`**：基线不许新增它（允许写集合只有 8 条），测试靠项目根在
   `sys.path` 上 import 命名空间包 `tools`；隐藏用例与 A9 都只认静态 import 边，不要求 `__init__.py`。

## 6 参考树摘要（可复核）

- 文件数：**18**（= 14 基线 ∪ 8 允许写 = 14 基线 + 4 新建；多一个少一个都会让隐藏 T25 与 A 的路径族声明对不上）；
- 组合摘要（算法 = 按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256，与 `reset-arm.py` 同）：
  **`69b6fda3149dd0da680f763e04d37803e0a2f2e6fde01a919baac8f559b451cf`**。

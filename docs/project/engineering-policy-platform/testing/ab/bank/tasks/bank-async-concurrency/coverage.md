# 覆盖表（bank-async-concurrency）

> **2026-10-21 深夜状态（本覆盖表快照之后）**：本题 hidden/PLAN.md（38 条）与 hidden/runner.py、
> reference/tree/ 与天花板已落盘并实测：T 基线 2/38、参考树 38/38；C effective_total 27/27；A 10/10。
> 本文正文里「hidden 未实现 / 未测 / pending_hidden」的措辞是该批落地前的快照；当前读数以本题
> README 的「天花板读数」节与 reference/README.md 为准。

> **口径**：● = 本题有真实岔口（错法会命中）；○ = 本题不设计岔口、留作变异（规则在**同一写面**上
> 仍可触发）；— = 结构性不适用（**不许**从 `allow` 反推成「查过没问题」）；◐ = 只能靠隐藏验收。
> **证据等级**：`实测` = 构建本包时在基线副本 + 构造变异上跑了真 `policy.check`（读数见 §2）；
> `规则数据` = 只核对规则 YAML / 配置、**没跑**；`未测` = 没跑。
> 本题的直接点 = SPEC §4 的 9 条表 + `STYLE-010` + `ARCH-001` + `SEC-006`（§1）；其余按 SPEC §4 的
> 「其余」分组（§3）。隐藏验收代码**未写**，所以所有行为面的证据等级一律是「未测」。

## 1 直接可触发规则点（12 条）

| 规则 ID | checker | 级别 | 覆盖类 | 本题触发步骤 | 期望 decision | 证据等级 |
| --- | --- | --- | --- | --- | --- | --- |
| TESTING-001 | missing_tests | error | ● | 新建 `src/shop/notify_model.py` / `notify_worker.py` / `tools/notify_smoke.py` 而不带同名测试 | `block` | **实测**（p2 / p5：exit 1，violations=[TESTING-001]） |
| TESTING-002 | failing_tests | error | ● | 异步用例写错使相关测试失败（真失败，不是「待实现」） | `block` | **实测**（p4b：exit 1，violations=[TESTING-002]） |
| TESTING-002 的 pending 通道 | failing_tests | error（规则）/ warning（findings） | — | 先写 `tests/test_notify_smoke.py` 而 `tools.notify_smoke` 缺失（基线补了 `tools/__init__.py` 之后） | `allow_with_warnings` + `pending_findings` | **实测**（m7：exit 1，violations=[]，pending_findings=[TESTING-002]） |
| DOC-001 | missing_docstring | warning | ● | 类/函数/模块漏 docstring | `allow_with_warnings` | **实测**（p6：exit 1，2 条 warning） |
| STYLE-001 | style_lint | warning | ● | 单行超过 100 列 | `allow_with_warnings` | **实测**（p12：exit 1，1 条 warning） |
| STYLE-002 | style_lint | error | ● | 留下未使用 import | `block` | **实测**（p7：exit 1，violations=[STYLE-002]） |
| STYLE-004 | style_lint | warning | ● | `ROOT = Path(...)` 后 `sys.path.insert` 再 import 且没有 `# noqa: E402` | `allow_with_warnings` | **实测**（p8b：exit 1，1 条 warning）；**p8 的「裸 `sys.path.insert` 后 import」不报**（见 §2 注） |
| STYLE-018 | style_lint | warning | ● | import 分组 / 排序错 | `allow_with_warnings` | **实测**（p9：exit 1，1 条 warning） |
| SEC-011 | style_lint | error | ● | 用 `random.random()` 做事件 id / 抖动 | `block` | **实测**（p10：exit 1，violations=[SEC-011]） |
| SEC-015 | style_lint | error | ● | `except Exception: pass` / 裸 `except: pass` 静默吞异常 | `block` | **实测**（p11：exit 1，violations=[SEC-015, STYLE-010]） |
| STYLE-010 | style_lint | error | ○ | 裸 `except:`（SPEC 记作 ○；同一行也会被 SEC-015 兜住） | `block` | **实测**（p11：与 SEC-015 同次命中） |
| ARCH-001 | forbidden_dependency | error | — | 本任务不碰 controller（允许写里没有 controller 文件） | 不适用（scope 不匹配）；C 的 3 分已标 `not_applicable`（`effective_total` 27） | **实测**：8 个被测 .py 上 `skipped_rules=[ARCH-001@1]`（跳过 ≠ 通过）；基线 `order_controller.py` 探针上它真的参与判定并 `allow`（§2 的 `probe-async-baseline-controller`） |
| SEC-006 | style_lint | error | — | 本题不读 YAML、不调用 `yaml.load` | — | **规则数据**（spec `SEC-006.yaml` 的 S506；未跑） |

## 2 构建本包时的实测读数（可复核的探针）

统一形态：cwd = 仓库根、`PYTHONPATH=src`、`--config-root .`、`--workspace <基线副本+变异>`、
`--operation edit|create`、`--changed <目标文件>`、`--request-id probe-async-<探针名>`（固定值）、`--json`。
基线副本 = `baseline/` 的 15 文件；每个探针一棵独立副本。

| 探针 | 目标 / 变异 | exit | decision | violations | pending_findings | skipped_rules |
| --- | --- | --- | --- | --- | --- | --- |
| `probe-async-baseline-notify` | 基线 `src/shop/notification.py`（`--layer service`） | 0 | `allow` | [] | [] | [`ARCH-001@1`] |
| `probe-async-baseline-controller` | 基线 `src/shop/order_controller.py`（`--layer controller`） | 0 | `allow` | [] | [] | []（5 个 checker 全部 served） |
| `probe-async-p2-missing-tests` | 新建 `src/shop/notify_model.py`，无同名测试 | 1 | `block` | [`TESTING-001`] | [] | [`ARCH-001@1`] |
| `probe-async-p3-pending` | 新建 `tests/test_notify_model.py`（import `shop.notify_model`，实现缺失） | 1 | `allow_with_warnings` | [] | [`TESTING-002`] | [`ARCH-001@1`] |
| `probe-async-p4-tools-test-import`（† 旧 13 文件基线） | 新建 `tests/test_notify_smoke.py`（模块级 `from tools.notify_smoke import main`） | 1 | `block` | [`TESTING-002`] | [] | [`ARCH-001@1`] |
| `probe-async-m7-tools-pending` | 14 文件基线 + 同一份 `tests/test_notify_smoke.py`（实现缺失） | 1 | `allow_with_warnings` | [] | [`TESTING-002`] | [`ARCH-001@1`] |
| `probe-async-p4b-tools-test-subprocess` | 新建 `tests/test_notify_smoke.py`（子进程驱动，不 import） | 1 | `block` | [`TESTING-002`] | [] | [`ARCH-001@1`] |
| `probe-async-p5-tools-script` | 新建 `tools/notify_smoke.py`，无同名测试 | 1 | `block` | [`TESTING-001`] | [] | [`ARCH-001@1`] |
| `probe-async-p6-docstring` | model 无 docstring + 绿测试 | 1 | `allow_with_warnings` | [`DOC-001` ×2] | [] | [`ARCH-001@1`] |
| `probe-async-p7-unused-import` | model 里 `import json` 未用 + 绿测试 | 1 | `block` | [`STYLE-002`] | [] | [`ARCH-001@1`] |
| `probe-async-p8-e402` | 裸 `sys.path.insert(...)` 后 import | 0 | `allow` | [] | [] | [`ARCH-001@1`] |
| `probe-async-p8b-stale-import` | `ROOT = Path(...)` + `sys.path.insert` 后 import | 1 | `allow_with_warnings` | [`STYLE-004`] | [] | [`ARCH-001@1`] |
| `probe-async-p9-isort` | `from pathlib import Path` 在 `import sys` 之前 | 1 | `allow_with_warnings` | [`STYLE-018`] | [] | [`ARCH-001@1`] |
| `probe-async-p10-random` | `random.random()` 生成事件 id | 1 | `block` | [`SEC-011`] | [] | [`ARCH-001@1`] |
| `probe-async-p11-bare-except` | 裸 `except: pass` | 1 | `block` | [`SEC-015`, `STYLE-010`] | [] | [`ARCH-001@1`] |
| `probe-async-p12-long-line` | 超过 100 列的行 | 1 | `allow_with_warnings` | [`STYLE-001`] | [] | [`ARCH-001@1`] |
| `probe-async-m1-design`（A/B，2026-10-22） | 树 = 15 文件基线 + `reference/tree/tools/notify_smoke.py`；目标 `tools/notify_smoke.py`；`--changed` 只有它（批为空） | A 1 / B 0 | A `block` / B `allow` | A [`TESTING-002`] / B [] | [] | [`ARCH-001@1`] |

基线 `probe-async-baseline-notify` 的 `check_volume`：`rule_count=43`、`effective_rule_count=42`、
`skipped_rule_count=1`、`skipped_by_reason={evidence_not_collected:0, missing_dimension:0, scope_mismatch:1}`、
`blocking_capable_skipped=1`、`served_checkers=[failing_tests, missing_docstring, missing_tests, style_lint]`、
`missing_dimensions=[]`、`complete=true`。
**`probe-async-m1-design` 的判定面（2026-10-22 构造变更的证据形态）**：两臂只差
`validation/test-layout.yaml` 的 `production_patterns`（A 只 `src/**/*.py`、B 加 `tools/**/*.py`）。
A：`selection.level=none`、`nodeids=[]`、`failing_tests` 未被服务 → `block`（`TESTING-002`）；
B：`selection.level=related`、`nodeids=[tests/test_notify_smoke.py]`、4 个 checker 全 served → `allow`。
这就是**基线静态契约测试**（`tests/test_notify_smoke.py` 自基线起就在树里）的用途：M1 批为空时
A 选不到测试、B 选得到基线测试并跑通——C1-b §7.3 的设计方向形态（详见 `README.md` §8.6）。

**† 注（构造修复前后的读数）**：`probe-async-p4-tools-test-import` 是**旧 13 文件基线**（没有
`tools/__init__.py`）上的读数：顶层包 `tools` 不在树里，于是真收集失败 → `block`。Lead 裁定给基线补
`tools/__init__.py`（13 → 14 文件）后，同一形态 = `probe-async-m7-tools-pending`：`allow_with_warnings`
+ `pending_findings=[TESTING-002]`、`violations=[]`（修法与两种 A 维度口径的读数见 `README.md` §8.1）。
**其余探针已在 14 文件基线上逐个重跑**（`baseline-notify` / `baseline-controller` / `p2` / `p3` /
`p6`–`p12` / `p4b` / `p5`），decision / violations / pending_findings / skipped_rules 与表内逐条一致；
`p4` 是唯一保留的旧基线读数（† 行，用来记录构造缺陷）。
**2026-10-22 加第 15 个文件（基线静态契约测试）之后**：`p5`（写 `tools/notify_smoke.py` 而不写测试）
不再是 TESTING-001 形态——基线的同名静态测试会跑通，这一形态现在就是 `probe-async-m1-design`
（A block / B allow）；其余探针未逐个重跑，按判据面推演不变（它们的树里该测试与目标无关，
或被按路径替换）。

**P8 的注**：ruff 0.14.13 对「裸露的 `sys.path.insert(...)` 之后紧跟 import」不报 E402；只有先出现
其它模块级语句（如 `ROOT = ...`）才报。所以 STYLE-004 的可触发形态是后者；前者不产生读数
（不是「通过」）。探针目录都在 `.tmp/bank-async-concurrency/`（不随包交付）。

**C 的分母**：`ARCH-001` 在 8 个被测 .py 上恒进 `skipped_rules`，`scoring.yaml` 已把它的 3 分标
`not_applicable`（不计分也不计分母），**C 上限 27**（`effective_total`）；读 C 必须带 `effective_total`。

## 3 其余 31 条（按 SPEC §4 的「其余」分组；`STYLE-010` / `ARCH-001` / `SEC-006` 已在 §1 单列）

**○（21 条）**：`DOC-002` / `DOC-003` / `DOC-004`、`STYLE-003` / `005` / `006` / `007` / `008` /
`009` / `011` / `012` / `014` / `015` / `016` / `017`、`SEC-001` / `002` / `003` / `004` / `017` / `018`。
理由：本题的允许写里仍存在 docstring 形态、import 形态、比较/命名/日志写法等写面，规则**可**触发；
但本题不拿它们当岔口、**没有设计变异**，因此证据等级 = **未测**（「覆盖」只在「实测」时写）。

**—（10 条）**：`SEC-005` / `007` / `008` / `009` / `010` / `012` / `014` / `019` / `021` / `022`。
理由（SPEC 指定）：本题不读 YAML、不执行外部命令 / 不拼接 SQL、不写日志、不解析不可信输入、不做
序列化、不建临时文件/绑定地址——这些规则在本题的写面上没有结构性触发点。**不适用 ≠ 通过**。
（`ARCH-001` / `SEC-006` 已在 §1 单列。）

## 4 A 维度（A1–A10，结构谓词）

测量：`.venv/Scripts/python.exe tools/structure_metrics.py --workspace <final-tree> --layers <task>/layers.yaml --interfaces <task>/interfaces.yaml --json`；退出码 0 = 10 条全 pass，1 = 有 fail，2 = 声明读不出来。
**已实测**：`layers.yaml`（21 条）与 `interfaces.yaml`（8 条）可加载（exit 0）；
在**15 文件基线副本**（12 个 .py，其中 `tools/__init__.py` 显式 `skip`；6 个新建文件尚未
落盘，声明为 `declared_unmatched`）上 **A1–A10 全 pass（exit 0；2026-10-22 复测）**。
**最终树读数：本表快照时未测**（没有参考解，不能假装测过）；现行读数见 `README.md` §9.3（参考树 A 10/10）。

`tools/__init__.py` 的层是 **`skip` = 显式移出测量范围**，不是漏声明（理由见 `README.md` §8.1）：
按 `other` 声明测量冻结基线时 A9 会报 1 条 `tools/__init__.py: no_test_import`（基线里没有测试 import
`tools.*`），基线 A1–A10 只有 9/10；本题 A 读数以「基线 + 最终树都 A1–A10 全 pass」为冻结口径，故改
`skip`。它不参与 A3 / A7 / A9 / A10；tools 的实质写面 `tools/notify_smoke.py` 仍在 composition 层，
A9 仍要求它由 `tests/test_notify_smoke.py` 静态 import。

| id | 谓词 | 阈值 | 本题状态 |
| --- | --- | --- | --- |
| A1 | 分层方向 | 违规边 0 且 unresolved 0 | 基线 pass（0 违规边 / 0 unresolved）；最终树**未测** |
| A2 | 依赖无环 | 0 环 | 基线 pass（6 边 / 10 节点 / 0 环）；最终树**未测** |
| A3 | 公开符号最小面 | 超声明上限的模块 0 个（`declared_caps`） | 基线 pass（5 模块 / 12 公开定义）；上限：model 4、worker 6、smoke 2（SPEC §7），其余 4/0；最终树**未测** |
| A4 | 组合根唯一 | 生产层业务方法里实例化具象协作者 0 处 | 基线 pass（0 违规；2 处 `__init__` 默认装配豁免）；最终树**未测** |
| A5 | 函数复杂度 | 圈复杂度 > 10 的函数 0 个 | 基线 pass（17 函数 / 0 超阈值）；最终树**未测** |
| A6 | 文件/函数长度 | 文件 > 200 行或单函数 > 50 行的 0 处 | 基线 pass；最终树**未测** |
| A7 | docstring 覆盖 | 模块与公开定义缺失 0 处 | 基线 pass（10 文件 / 21 定义 / 0 缺失）；最终树**未测** |
| A8 | 依赖扇出 | 项目内出/入边 > 5 的模块 0 个，unresolved 0 | 基线 pass；最终树**未测** |
| A9 | 测试对应完备 | 每个生产文件都有测试层静态 import（100%） | 基线 pass（5/5；`tools/__init__.py` 显式 skip、不进分母）；最终树**未测**——`tools/notify_smoke.py` 要被 `tests/test_notify_smoke.py` **静态 import** 才满足 |
| A10 | 无动态执行 | 动态 import / 通配 import 0 处 | 基线 pass；最终树**未测** |

## 5 只能靠隐藏验收的行为面（SPEC §5；**全部未测**）

隐藏验收代码未写（`scoring.yaml` 的 `dimension_t.status: pending_hidden`、`total: null`、
`planned_min_total: 30`）。下列每一条的判定口径是 `acceptance.md` 的对应 A 项；**在读数为 null 时
一条都不许写成「覆盖」**：

- **确定性**（A8）：AST 里没有 `time.sleep` / `time.time` / `random` / 网络调用；同一场景两次
  `processed()` 逐字节相同。→ 未测
- **幂等**（A3）：同 key 两次 `submit` → 第二次 `False`，`processed()` 只有 1 条；不同 key 都进。→ 未测
- **有界**（A4）：队列满时 `submit` 返回 `False`（不静默丢、不阻塞）。→ 未测
- **取消**（A6）：取消等待 `stop()` 的任务 → 干净退出、不吞 `CancelledError`、不残留 pending task。→ 未测
- **停机**（A5）：`stop()` 先排空已入队事件，`processed()` 顺序稳定、返回副本。→ 未测
- **共享队列**（A7）：两个 worker 消费同一 `asyncio.Queue` 时每个事件只处理一次。→ 未测
- **smoke**（A9）：`python tools/notify_smoke.py` 退出码 0、stdout JSON 恰 2 条（3 次提交去重后）。→ 未测
- **全树**（A12）：`python -m pytest -q` 绿、无 skip/xfail、允许写集合 ⊆ 10 条。→ 未测

## 6 明确未测 / 未做（失败关闭）

- 最终树的 A1–A10 读数（无参考解，不伪造）；
- 8 条隐藏行为面（隐藏用例未写）；
- §3 的 21 条 ○ 规则（没有变异探针）；
- `SEC-006`（本题不读 YAML，没跑）；
- ~~`tools/notify_smoke.py` 与同名测试的先后阻断~~ **已修**：基线加 `tools/__init__.py`（13 → 14 文件），
  M7 实测走 `pending_findings`（见 §2 的 `probe-async-m7-tools-pending` 与 `README.md` §8.1）；
  **2026-10-22 起**该顺序不再使用：基线第 15 个文件是静态契约测试，M1 先写实现（§2 的
  `probe-async-m1-design`，A block / B allow）；
- 参考解与 T/C/A 天花板。

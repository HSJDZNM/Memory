# 覆盖矩阵（bank-docs-config）

> **2026-10-21 深夜状态（本覆盖表快照之后）**：本题 hidden/PLAN.md（39 条）与 hidden/runner.py、
> reference/tree/ 与天花板已落盘并实测：T 基线 2/39、参考树 39/39；C effective_total 27/27；A 10/10。
> 本文正文里「hidden 未实现 / 未测 / pending_hidden」的措辞是该批落地前的快照；当前读数以本题
> README 的「天花板读数」节与 reference/README.md 为准。

> **它回答什么**：这道题把治理系统的哪些规则点 / 结构谓词 / 隐藏行为面真正压到了，
> 哪些只是「规则数据上可触发」而本任务没有岔口，哪些结构性不适用。
> **它不回答什么**：不构成「已冻结 T」的证据——隐藏验收代码**尚未写**（`scoring.yaml` 的
> `dimension_t.status = pending_hidden`）；本文件给的是判据与可执行测法。
> 43 条规则点一律从 `policies/**/*.yaml` 读出（本包用 PyYAML 实算 id / version / checker / severity / codes，
> 逐条核对，不编造）；期望的 decision 形态来自 `policy.check` 的四种结果。

## 0 图例与证据等级

| 符号 | 含义 |
| --- | --- |
| ● | **直接可触发**：任务里存在一个真实的「省事写法 / 常见错法」，会命中该规则 |
| ○ | **留作变异**：本任务没有这条岔口；在树副本上做一处显式缺陷即可命中（判据来自规则数据） |
| — | **结构性不适用**：任务的写面里没有这类代码（SQL / XML / TLS / 网络 / 套接字 / 绑定端口…） |
| ◐ | **只能靠隐藏验收或结构谓词**：规则表达不了（行为语义、字节形态、文件集合） |

| 证据等级 | 含义 |
| --- | --- |
| **实测** | 本次在 `.tmp/bank-docs-config/probe/` 的树副本上跑过真 `policy.check`，读数见 §7 |
| **实测（负例）** | 同样跑了真 `policy.check`，结论是「这条规则在本任务的自然写法下**不触发**」 |
| **规则数据** | 只由 `policies/<ID>.yaml` 与 `validation/ruff.toml` 的 `select` 推出，未在本任务上实测 |
| **dgate2** | 冻结评测件 `testing/ab/dgate2` 已用变异证明该规则会红（本包未复核） |

## 1 汇总（先读这张表）

| 项 | 数 | 说明 |
| --- | --- | --- |
| 仓库规则点 | **43** 条 / **5** 个 checker | `style_lint` 39、`forbidden_dependency` 1、`missing_docstring` 1、`missing_tests` 1、`failing_tests` 1；error 24 / warning 19 |
| 本题直接可触发（SPEC §4） | **8** 条 | `SEC-006`、`TESTING-001/002`、`DOC-001`、`STYLE-001/002/010/018` |
| 其中本次**实测到判定**的 | **7** 条 | SEC-006 / TESTING-001 / DOC-001 / STYLE-001 / STYLE-002 / STYLE-010 / STYLE-018（§7.2–§7.6） |
| 其中**实测为负例**的 | **1** 条 | STYLE-004：`sys.path.insert` 后 import 在 ruff 0.14.13 上**不报** E402（§7.7） |
| 其中只由规则数据支撑的 | **1** 条 | TESTING-002（dgate2 用同一套规则实测过，本包未测） |
| 留作变异（○） | **23** 条 | §3；一处显式缺陷即可命中，不影响「本任务不压这些面」这一结论；含 `STYLE-004`（实测负例） |
| 结构性不适用（—） | **12** 条 | §4；必须写成「本题不覆盖」，不得从 allow 反推成「查过没问题」 |
| 结构谓词（A 维度） | **10** 条 | `tools/structure_metrics.py` 1.1；14 文件基线上实测 **10/10 pass**（§7.8） |
| 隐藏行为面（◐） | **>= 30** 条（计划） | §6；`hidden/` **未落盘**，T 未冻结 |

**怎么读「涵盖程度」**：● 的 8 条是本任务真正压到的判定面；○ 的 23 条说明这些规则在**同一写面上仍然会响**，
但本题不把它们当岔口；— 的 12 条必须写成「本题不覆盖」。**43 条里没有任何一条会被静默跳过**：
参与判定的规则、被跳过的规则（含 `skipped_by_reason`）与证据数都随每次 `policy.check` 的
`result.matched_rules / skipped_rules / evidence.served_checkers` 落账，`check_volume` 给出
`complete / blocking_capable_skipped / missing_dimensions`（AGENTS 第 20/49 条）。

## 2 直接可触发（●，8 条）

「触发步骤」写的是这道题里模型**最可能真的做出来**的动作；M 编号对应 `milestones.md`。

| 规则 ID | checker | 级别 | 触发步骤（省事 / 错法） | 期望 decision | 证据 |
| --- | --- | --- | --- | --- | --- |
| SEC-006 | style_lint | error | M3 的加载器用 `yaml.load(handle, Loader=yaml.Loader)` 代替 `yaml.safe_load` | `block` / exit 1 / `SEC-006@1 error` | 实测（§7.2） |
| TESTING-001 | missing_tests | error | M3 只写 `src/shop/config.py` 不写 `tests/test_config.py`（`tools/check_config.py` 在 M1 由基线的同名静态契约测试兜底） | `block` / `TESTING-001@1 error` | 实测（§7.6） |
| TESTING-002 | failing_tests | error | M2 / M3 / M5 的实现与测试不一致，相关测试红（M1 的 A 臂 selection `none`、`failing_tests` 无证据，同样阻断） | `block` / `TESTING-002@1 error` | 规则数据（dgate2） |
| DOC-001 | missing_docstring | warning | 加载器或脚本漏模块 / 函数 docstring | `allow_with_warnings` / `DOC-001@1 warning` | 实测（§7.4） |
| STYLE-001 | style_lint | warning | 迁移说明或 `ValueError` 消息一行超 100 列 | `allow_with_warnings` / `STYLE-001@1 warning` | 实测（§7.5） |
| STYLE-002 | style_lint | error | 改完留下未使用 import（例如脚本里 `import json` 没用上） | `block` / `STYLE-002@1 error` | 实测（§7.6） |
| STYLE-010 | style_lint | error | 加载器用裸 `except:` 吞 YAML / 文件异常（处理体不是裸 `raise`） | `block` / `STYLE-010@1 error` | 实测（§7.3） |
| STYLE-018 | style_lint | warning | `import yaml` 写在 `from pathlib import Path` 之前、组间不空行 | `allow_with_warnings` / `STYLE-018@1 warning` | 实测（§7.5） |

> **STYLE-004 已按实测移到 §3（○，留作变异）**：本题的自然写法是
> `sys.path.insert(0, <根>/src)` 之后 import `shop`，而 ruff 0.14.13 对 `sys.path` 修改**之后**的 import
> 有专门豁免，实测不报 E402（同一个配置下，先写普通的模块级赋值再 import 会报 E402，所以不是配置没生效）。
> 因此这条在本题的自然形态下**没有岔口**，证据等级记「实测（负例）」；能触发的形态是「先模块级赋值、
> 再 insert 与 import」（§7.7 的 e402b 对照）。三处已同批统一：`bank/README.md` §2 改 ○、SPEC §4 移到
> 「其余」、本文与 README §6 同口径。题面仍要求 `# noqa: E402`：那是**代码约定**，不是判据，隐藏用例不应断言它。

## 3 留作变异（○，23 条）

本任务**没有设计岔口**（正常写不会触发），但规则在同一写面上仍然可触发。除 `STYLE-004` 的「实测负例」外，全部未在本任务实测（证据 = 规则数据）。

| 规则 ID | code / checker | 显式缺陷（变异，落在本题写面上） | 期望 |
| --- | --- | --- | --- |
| DOC-002 | D205 / style_lint | 加载器 docstring 摘要行后不留空行 | warning |
| DOC-003 | D200 / style_lint | 单行能放下的 docstring 拆成多行 | warning |
| DOC-004 | D401 / style_lint | 摘要写成 "Returns ..." 而不是祈使 "Return ..." | warning |
| STYLE-003 | E401 / style_lint | 脚本里 `import json, sys` | warning |
| STYLE-004 | E402 / style_lint | 先写模块级赋值（如 `ROOT = ...`）再 `sys.path.insert`，随后 import 忘 `# noqa: E402`（裸 insert 后 import 不报） | warning | 实测（负例，§7.7） |
| STYLE-005 | F403/F405 / style_lint | `from shop.config import *` | error |
| STYLE-006 | E711 / style_lint | `if data == None` | error |
| STYLE-007 | E712 / style_lint | `if jitter == True` | error |
| STYLE-008 | E713/E714 / style_lint | `if not "retry" in data` | warning |
| STYLE-009 | E721 / style_lint | `if type(value) == int` | error |
| STYLE-011 | E731 / style_lint | `check = lambda p: load_config(p)` | warning |
| STYLE-012 | E741 / style_lint | 变量名 `l` | warning |
| STYLE-014 | N801 / style_lint | `class config_loader:` | warning |
| STYLE-015 | N802 / style_lint | `def CheckConfig(...):` | warning |
| STYLE-016 | N803 / style_lint | `def main(ConfigPath):` | warning |
| STYLE-017 | N806/N815/N816 / style_lint | 函数内局部变量 `MaxAttempts` | warning |
| SEC-001 | S102/S307 / style_lint | 用 `eval(text)` 解析配置文本 | error |
| SEC-002 | S301/S302 / style_lint | 用 `pickle.loads(blob)` 读缓存 | error |
| SEC-003 | S303/S324 / style_lint | 用 `hashlib.md5(...)` 算配置指纹 | error |
| SEC-004 | S105/S106/S107 / style_lint | 把 token 硬编码进加载器常量 | error |
| SEC-015 | S110/S112 / style_lint | `except yaml.YAMLError: pass`（静默吞坏配置） | error |
| SEC-017 | LOG015 / style_lint | 脚本里直接调 `logging.info(...)`（根 logger） | warning |
| SEC-018 | TRY400 / style_lint | `logger.error(str(exc))` 而不是 `logger.exception(...)` | warning |

> SEC-015 在 `bank/README.md` §2 的矩阵里是 ○（「变异：静默吞坏配置」），与上表一致。

## 4 结构性不适用（—，12 条）

**判据**：这道题的写面里不出现对应构造；模型若**主动**写这类代码，规则照样会响，但那已经不在本题声明的覆盖范围内
（不许写成「本题覆盖了」）。

| 规则 ID | code | 为什么本题不适用 |
| --- | --- | --- |
| ARCH-001 | forbidden_dependency | 本题没有 controller 层的新代码：4 个被测文件是 model（加载器）/ composition（脚本）/ test。基线 controller 一个字节不改；`scoring.yaml` 已把它的 3 分标 `not_applicable`（C 上限 27） |
| SEC-005 | S323/S501 | 不写 HTTP/TLS 客户端；没有证书校验可关 |
| SEC-007 | S602/S605/S609 | 不 shell out；校验脚本只用标准库 + PyYAML |
| SEC-008 | S608 | 配置是 YAML 文件，不是 SQL；不拼 SQL 字符串 |
| SEC-009 | S313–S318 | 不解析 XML |
| SEC-010 | S310 | 不打开 URL；题面禁止网络 |
| SEC-011 | S311 | 不引入随机数（题面禁止） |
| SEC-012 | S308/S611/S701 | 不用模板引擎 / `mark_safe` |
| SEC-014 | S113 | 不发起外部请求；没有 timeout 参数可漏 |
| SEC-019 | S104 | 不起服务、不绑定 0.0.0.0 |
| SEC-021 | S312/S321 | 不建 socket、不用明文协议 |
| SEC-022 | S612 | 不配置远端日志监听 |

## 5 A 维度结构谓词（10 条；由 `tools/structure_metrics.py` 判）

声明在包内 `layers.yaml`（18 条路径 = 14 基线 + 4 新建；`tests/test_check_config.py` 属于基线一侧，
M5 把它从静态契约测试改写成行为测试）与 `interfaces.yaml`（6 个非测试模块的上限）。
**基线树实测**：`summary {passed: 10, failed: 0}`、exit 0（§7.8）——4 个新建文件的层声明在基线上是
`workspace_scope.declared_unmatched`（证据，不判 fail），最终树落盘后它们应当被命中。

| 谓词 | 阈值 | 本题的合法形态 | 违规岔口（变异测法） |
| --- | --- | --- | --- |
| A1 分层方向 | 违规边 0 | `tools/check_config.py`(composition) → `src/shop/config.py`(model)；tests → 任意；基线三层贯通 | 让 `src/shop/config.py` import `shop.order_repository`（model → repository） |
| A2 依赖无环 | 0 环 | 新增依赖是单向的：composition → model | 让加载器反向 import 脚本 |
| A3 公开符号最小面 | 每模块 <= 声明上限 | config 1 / check_config 1（上限 3 / 2） | 往 config.py 里塞第 4 个公开定义（例如 3 个常量 + 函数） |
| A4 组合根唯一 | 违规 0 | 只有 composition 脚本实例化/调用具体协作者；config.py 不 new 任何东西 | 在 `load_config` 业务函数里 new 一个 repository |
| A5 函数复杂度 | <= 10 | 加载器校验是顺序 if，分支少 | 把键校验写成一个 15 支 if/elif 链 |
| A6 文件/函数长度 | 文件 <= 200 行；函数 <= 50 行 | 加载器 `60 行、脚本 `40 行 | 把映射表与回滚说明全塞进一个 80 行函数 |
| A7 docstring 覆盖 | 缺失 0 | 模块 + 公开定义都有 docstring | 删函数 docstring（同时命中 DOC-001 warning） |
| A8 依赖扇出 | 出 / 入 <= 5 | config 出边 2（pathlib / yaml 以外的项目内边 0）；check_config 出边 1 | 让 config.py import 所有 shop 模块 |
| A9 测试对应完备 | 100% | `tests/test_config.py` import `shop.config`；`tests/test_check_config.py` import `tools.check_config` | 新建生产文件但不写测试（同时命中 TESTING-001） |
| A10 无动态执行 | 违规 0 | 静态 import | `importlib.import_module("shop.config")` 或通配 import |

## 6 只能靠隐藏验收（◐；>= 30 条，hidden **未落盘**）

| 面 | 计划条数 | 为什么规则做不到 |
| --- | --- | --- |
| 加载器（v2 逐键、v1 拒绝与迁移提示、未知键、缺键、五种类型错、bool 冒充 int、坏 YAML、错误消息无绝对路径） | 12 | 规则只查 lint / docstring / 依赖；字段集合与 `ValueError` 语义是行为 |
| 校验脚本（退出码 0/1、stdout/stderr 行数、v1 那行含 `retry_policy`、配置文件字节不变、AST 证明走 `load_config`、缺 `--config` 的退出码 2） | 6 | 进程级行为与 AST 断言不在 43 条规则里 |
| 文档（v2 表的 5 行逐键、迁移文档三节） | 6 | 文字内容不在 43 条规则里 |
| README / 树形状（配置节链接、三个原二级标题、允许写集合、冻结 10 文件） | 4 | 文件集合与文本结构不在规则里 |
| 入口（pytest 全绿、collect 数、脚本输出形态） | 3 | 命令级行为 |
| **合计** | **>= 31** | 与 `scoring.yaml` 的 `planned_min_total: 30` 相容；隐藏作者可按 PLAN 拆条 |

**文档类目标的读数**（本题的构造要点，已实测）：对 `.md` 走验证器路径应得到
`language_coverage.status = not_covered_by_design`、`served_checkers = []`、43 条全部落在 `skipped_rules`
（`scope_mismatch`）、`effective_rule_count = 0`（§7.9）。decision 虽然写 `allow`，但**那不是「查过没问题」**：
它是「平台对这类目标没有 rule pack」的显式状态。所以本任务的文档正确性只能靠隐藏验收与 A6–A8 的结构判据。

## 7 本次实测读数（在 `.tmp/bank-docs-config/` 的树副本上跑真 `policy.check` / `structure_metrics`）

命令骨架（逐案例一次，`--request-id` 固定；`--config-root` 指向仓库根，`--workspace` 指向副本）：

```text
.venv/Scripts/python.exe -m policy.check <文件> --workspace .tmp/bank-docs-config/<副本> --config-root . --layer <层> --operation edit --changed <文件> [--changed <测试>] --request-id probe-docs-config-<tag> --json
```

| # | 案例 | 判定 | violations | skipped / 关键读数 | exit |
| --- | --- | --- | --- | --- | --- |
| 7.1 | 14 文件基线树的 `src/shop/order_controller.py`（layer=controller） | `allow` | 无 | `matched_rules` 43、`skipped_rules` 0、5 个 checker 全部 served、`complete=true` | 0 |
| 7.2 | 变异：加载器用 `yaml.load(handle, Loader=yaml.Loader)` | `block` | `SEC-006@1 error` | `skipped_rules=[ARCH-001]`（`scope_mismatch`，`blocking_capable_skipped=1`）；TESTING-001/002 已服务且未报违规 | 1 |
| 7.3 | 变异：加载器用裸 `except:` 包 YAML 读取 | `block` | `STYLE-010@1 error` | 同上（只有层不匹配的 ARCH-001 被跳过） | 1 |
| 7.4 | 变异：删掉 `load_config` 的 docstring | `allow_with_warnings` | `DOC-001@1 warning` | 同上 | 1 |
| 7.5 | 变异：`import yaml` 排在 `from pathlib import Path` 之前 + 一行 > 100 列 | `allow_with_warnings` | `STYLE-001@1 warning`、`STYLE-018@1 warning` | 同上 | 1 |
| 7.6 | 变异：`src/shop/config.py` 没有 `tests/test_config.py` | `block` | `TESTING-001@1 error` | 同上；`missing_tests` 已服务 | 1 |
| 7.6b | 变异：加载器里 `import json` 没用上 | `block` | `STYLE-002@1 error` | 同上 | 1 |
| 7.7 | 变异：`tools/check_config.py` 里 `sys.path.insert(...)` 之后 import `shop`（无 `# noqa`） | **`allow`** | 无 | **E402 没报**（STYLE-004 未命中）；同配置下「模块级赋值之后 import」的对照样例报 E402 | 0 |
| 7.8 | 14 文件基线上的 `structure_metrics`（`--layers` / `--interfaces` 用本包两份声明） | 10/10 pass | 无 | `layers.entries=18`、`interfaces.entries=6`、`undeclared=[]`、4 个新建文件落 `declared_unmatched` | 0 |
| 7.9 | `docs/config.md`（`--language text --layer skip`） | `allow` | 无 | `served_checkers=[]`、`language_coverage.status=not_covered_by_design`、43 条全 skipped（`scope_mismatch`）、`effective_rule_count=0`、`blocking_capable_skipped=24` | 0 |

**证据边界**：7.2–7.7b 与 7.9 是**本次实测**；7.8 是基线树上的实测（最终树落盘后要重跑，A9/A3 才真正覆盖到 4 个新建文件）；
STYLE-004 记「实测负例」；TESTING-002 与 §3 里除 STYLE-004 外的 22 条未在本任务上实测（不写成覆盖）；
`ARCH-001` 在 7.2–7.7b 的每次运行里都因 `scope_mismatch` 进 `skipped_rules`——**跳过不等于通过**；
C 侧已把该 3 分标 `not_applicable`（`effective_total` 27，见 §8）。

## 8 与 `scoring.yaml` 的对接

- **C 维度**：被测文件集 = 4 个 `.py`（`src/shop/config.py`、`tools/check_config.py`、`tests/test_config.py`、
  `tests/test_check_config.py`）；8 条计分规则见 `scoring.yaml` 的 `dimension_c.rules`；
  §2 的 8 条直接点里有 7 条落在这 8 条里；SEC-006 只进过程读数。STYLE-004 为实测负例（○，见 §3），
  不重复计分。
  不把整棵树拿去跑（否则基线 `__init__.py` / `order_*.py` 会被判成缺测试的假违反）。
- **A 维度**：`layers.yaml` / `interfaces.yaml` 已按 structure_metrics 1.1 的闭集写成；
  基线树上 10/10 pass 只证明**声明本身可加载且与基线一致**，A3/A9 对 4 个新建文件的覆盖要等最终树。
- **T 维度**：**未冻结**。`scoring.yaml` 的 `dimension_t.status = pending_hidden`、`case_ids: []`、
  `total: null`、`planned_min_total: 30`；隐藏代码落盘后才冻结 `total` 与 `case_ids`（同批改 PLAN / runner / scoring）。

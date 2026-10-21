# 覆盖矩阵（bank-bugfix-first-failing-test）

> **它回答什么**：这道题把治理系统的哪些规则点 / 结构谓词 / 隐藏验收真正压到了，
> 哪些只是「规则数据上可触发」而本题没有岔口，哪些结构性不适用，以及**每条读数的证据等级**。
> **它不回答什么**：不构成「参考解已通过」的证据——参考解与本包的隐藏代码**都还没写**（下一批）；
> 本文件给的是判据、可执行测法与**已经实测过的那部分读数**。规则点一律从 `policies/**/*.yaml` 读出
> （43 条；rule id / checker / severity 逐条核对），不编造。期望 decision 形态来自 `policy.check` 的四种结果：
> `allow` / `allow_with_warnings` / `block`（另有 `evidence_unavailable` 等失败关闭形态，本表不涉及）。

## 0 图例与证据等级

| 符号 | 含义 |
| --- | --- |
| ● | **直接可触发**：任务里存在一个真实的「省事写法/常见错法」，会命中该规则 |
| ○ | **留作变异**：本任务没有设计岔口；在参考树副本上做一处显式缺陷即可命中（判据来自规则数据） |
| — | **结构性不适用**：任务的写面里没有这类代码（SQL / XML / TLS / 网络 / 套接字 / 绑定端口…） |
| ◐ | **只能靠隐藏验收或结构谓词**：规则表达不了（行为语义、对象身份、字节形态、文件集合） |

| 证据 | 含义 |
| --- | --- |
| **实测** | 本次在 `.tmp/bank-bugfix-first-failing-test/` 的基线/变异副本上跑过真 `policy.check`（读数见 §7） |
| **规则数据** | 只由 `policies/<ID>.yaml` 与 `validation/ruff.toml` 的 select 推出，未在本任务上实测 |
| **未测** | 本包没有对应工件（参考解 / 隐藏代码）可跑；写成「未测」，不写成覆盖 |

## 1 汇总（先读这五行）

| 项 | 数 | 说明 |
| --- | --- | --- |
| 仓库规则点 | **43** 条 / **5** 个 checker | `style_lint` 39、`forbidden_dependency` 1、`missing_docstring` 1、`missing_tests` 1、`failing_tests` 1；error 24 / warning 19 |
| 本题直接可触发 | **7** 条 | `TESTING-002`、`DOC-001`、`STYLE-001/002/010/018`、`SEC-015`（与 SPEC §4 的 7 行逐条对应） |
| 本题留作变异 | **24** 条 | 一处显式缺陷即可命中；不影响「本任务不压这些面」这一结论 |
| 结构性不适用 | **12** 条 | 不写 SQL/XML/TLS/网络/套接字/模板；不宣称覆盖 |
| 结构谓词（A 维度） | **10** 条 | `tools/structure_metrics.py` 1.1；声明在 `layers.yaml` / `interfaces.yaml`，本题已在**基线树**上实测 10/10 |
| 隐藏验收（行为面） | **候选 36 条（未实现）** | 见 §6；`scoring.yaml` 的 `planned_min_total: 30`，**total 未冻结** |

**怎么读**：● 的 7 条是本任务真正压到的判定面；○ 的 24 条说明这些规则在**同一写面上仍然会响**，
但本题不把它们当岔口；— 的 12 条必须写成「本题不覆盖」，不得从 `allow` 反推成「查过没问题」；
◐ 的行为面没有规则可表达，只能由隐藏验收判。**跳过不等于通过**：本任务的 `ARCH-001` 在每次
`policy.check` 里都会因 `layer` 不匹配进 `skipped_rules`（见 §7），读读数必须连
`skipped_rules` / `check_volume.blocking_capable_skipped` 一起看（AGENTS 第 20/49 条）。

## 2 直接可触发（●，7 条）

「触发步骤」写的是这道题里模型**最可能真的做出来**的动作；M 编号对应 `milestones.md`。

| 规则 ID | checker | 级别 | 触发步骤（省事/错法） | 期望 decision / severity | 证据 |
| --- | --- | --- | --- | --- | --- |
| TESTING-002 | failing_tests | error | **任何没把两条红测试一次修绿的提议**：只复制返回值没复制入参（M2 改一半）、先加新测试再改实现（顺序反了）、M3/M4 写出会失败的断言 | `block` / `TESTING-002@1 error`（**本题的预期读数**，SPEC §7） | 实测（§7 #1 #2） |
| SEC-015 | style_lint | error | 修 bug 时用 `except Exception: pass` 吞掉复制/写入错误（「省事写法」） | `block` / `SEC-015@1 error` | 实测（§7 #6） |
| STYLE-010 | style_lint | error | 修 bug 时写裸 `except:`（`except: raise` 这种形式 ruff 0.14.13 **不报** E722，实测 #5；要写成真处理才报） | `block` / `STYLE-010@1 error` | 实测（§7 #7） |
| DOC-001 | missing_docstring | warning | 删/改坏 `OrderRepository` 的类或方法 docstring（改实现时最容易顺手删） | `allow_with_warnings` / `DOC-001@1 warning` | 实测（§7 #3） |
| STYLE-001 | style_lint | warning | 新用例里的长断言 / 长注释超过 100 列（新测试文件最容易） | `allow_with_warnings` / `STYLE-001@1 warning` | 实测（§7 #8） |
| STYLE-002 | style_lint | error | 改实现后留下未使用 import（例如把 `copy` 删了但 `import copy` 还留着） | `block` / `STYLE-002@1 error` | 实测（§7 #4） |
| STYLE-018 | style_lint | warning | 新测试文件 import 顺序错（本地 `from shop...` 写在标准库前面） | `allow_with_warnings` / `STYLE-018@1 warning` | 实测（§7 #9） |

> **跳过不等于通过**：在非 controller 文件上 `ARCH-001` 会进 `skipped_rules`（`layer repository != controller`）；
> 这个 `allow` 不是「架构没问题」，是「这条规则这次没参与」（C 侧因此把它的 3 分标 `not_applicable`，见 §8）。

## 3 留作变异（○，24 条）

本任务**没有设计岔口**（正常写不会触发），但规则在同一写面上仍然可触发。
「显式缺陷」给的是在参考树副本上做变异即可命中该规则的**测法**；期望形态由 severity 决定：
error → `block`，warning → `allow_with_warnings`。除 `TESTING-001`（已实测）外，全部证据 = **规则数据**。

| 规则 ID | code / checker | 显式缺陷（变异） | 期望 | 证据 |
| --- | --- | --- | --- | --- |
| TESTING-001 | missing_tests | 新建 `src/shop/copy_util.py` 但不写测试（本题不新建生产模块，正常路径不触发） | error | 实测（§7 #10） |
| DOC-002 | D205 / style_lint | docstring 摘要行后不留空行 | warning | 规则数据 |
| DOC-003 | D200 / style_lint | 单行能放下的 docstring 拆成多行 | warning | 规则数据 |
| DOC-004 | D401 / style_lint | 摘要写成 "Returns ..." 而不是祈使 "Return ..." | warning | 规则数据 |
| STYLE-003 | E401 / style_lint | `import json, sys` | warning | 规则数据 |
| STYLE-004 | E402 / style_lint | 先写模块级赋值（如 `ROOT = ...`）再 `sys.path.insert`，随后的 `from shop...` 忘加 `# noqa: E402`（裸 insert 后 import 在 ruff 0.14.13 上不报；**未实测**） | warning | 规则数据 |
| STYLE-005 | F403/F405 / style_lint | `from shop.order_service import *` | error | 规则数据 |
| STYLE-006 | E711 / style_lint | `if payload == None` | error | 规则数据 |
| STYLE-007 | E712 / style_lint | `if flag == True` | error | 规则数据 |
| STYLE-008 | E713/E714 / style_lint | `if not "id" in payload` | warning | 规则数据 |
| STYLE-009 | E721 / style_lint | `if type(payload) == dict` | error | 规则数据 |
| STYLE-011 | E731 / style_lint | `copy_row = lambda payload: dict(payload)` | warning | 规则数据 |
| STYLE-012 | E741 / style_lint | 变量名 `l` / `I` / `O` | warning | 规则数据 |
| STYLE-014 | N801 / style_lint | `class order_repository:` | warning | 规则数据 |
| STYLE-015 | N802 / style_lint | `def Insert(self, payload):` | warning | 规则数据 |
| STYLE-016 | N803 / style_lint | `def insert(self, Payload):` | warning | 规则数据 |
| STYLE-017 | N806/N815/N816 / style_lint | 函数内局部变量 `CopyRow` | warning | 规则数据 |
| SEC-001 | S102/S307 / style_lint | `eval(repr(payload))` 造副本 | error | 规则数据 |
| SEC-002 | S301/S302 / style_lint | `pickle.loads` 读订单 | error | 规则数据 |
| SEC-003 | S303/S324 / style_lint | `hashlib.md5` 生成行指纹 | error | 规则数据 |
| SEC-004 | S105/S106/S107 / style_lint | 把 token 写进代码常量 | error | 规则数据 |
| SEC-007 | S602/S605/S609 / style_lint | `subprocess.run("copy ...", shell=True)` | error | 规则数据 |
| SEC-017 | LOG015 / style_lint | 直接调 `logging.info(...)`（根 logger） | warning | 规则数据 |
| SEC-018 | TRY400 / style_lint | `logger.error(str(exc))` 而不是 `logger.exception(...)` | warning | 规则数据 |

## 4 结构性不适用（—，12 条）

**判据**：这道题的写面里不出现对应构造；模型若**主动**写这类代码，规则照样会响，
但那已经不在本题声明的覆盖范围内（不许写成「本题覆盖了」）。

| 规则 ID | code | 为什么本题不适用 |
| --- | --- | --- |
| ARCH-001 | forbidden_dependency | 本题不许碰 `order_controller.py`（controller 层 0 改动）；只改 repository 的实现，没有跨层依赖边可判 |
| SEC-005 | S323/S501 | 不写 HTTP/TLS 客户端；没有证书校验可关 |
| SEC-006 | S506 | 不读 YAML；存储是内存 list，没有 loader |
| SEC-008 | S608 | 数据是内存 dict，不是 SQL；不拼 SQL 字符串 |
| SEC-009 | S313–S318 | 不解析 XML |
| SEC-010 | S310 | 不打开 URL；题面禁止网络 |
| SEC-011 | S311 | 不生成随机数（题面要求确定性，没有 id 生成） |
| SEC-012 | S308/S611/S701 | 不用模板引擎 / `mark_safe` |
| SEC-014 | S113 | 不发起外部请求；没有 timeout 参数可漏 |
| SEC-019 | S104 | 不起服务、不绑定 0.0.0.0 |
| SEC-021 | S312/S321 | 不建 socket、不用明文协议 |
| SEC-022 | S612 | 不配置远端日志监听 |

## 5 A 维度结构谓词（10 条；由 `tools/structure_metrics.py` 判）

| 谓词 | 阈值 | 本题的合法形态 | 违规岔口（变异测法） |
| --- | --- | --- | --- |
| A1 分层方向 | 违规边 0 | controller → service → repository 单向；`tests/` 只 import 生产模块 | 让 `order_repository` import `shop.order_service`（repository→service 反向） |
| A2 依赖无环 | 0 环 | 三文件单向 | 让 repository 反向 import service |
| A3 公开符号最小面 | 每模块 ≤ 声明上限 | 见 `interfaces.yaml`（`order_repository` 3，`order_service`/`order_controller` 3，`__init__` 0） | 往 `order_repository` 里加第 4 个公开函数（例如 `clear()`） |
| A4 组合根唯一 | 违规 0 | 只有 `__init__` 的默认装配 `repository or OrderRepository()` | 在 `insert()` 里 new 一个 `OrderRepository()` |
| A5 函数复杂度 | ≤ 10 | 每个函数 0–2 个分支 | 把复制逻辑写成一串 if/elif |
| A6 文件/函数长度 | 文件 ≤ 200 行；函数 ≤ 50 行 | 每个文件 < 25 行 | 把三条新用例塞进一个 80 行函数 |
| A7 docstring 覆盖 | 缺失 0 | 模块 + 类 + 三个方法都有 docstring | 删类 docstring（同时命中 DOC-001 warning） |
| A8 依赖扇出 | 出/入 ≤ 5 | repository 入边 2（service、test），service 出边 1 | 让 `order_repository` import 一堆项目内模块 |
| A9 测试对应完备 | 100% | 每个生产文件都有测试层静态 import | 新建生产文件但不写测试（同时命中 TESTING-001） |
| A10 无动态执行 | 违规 0 | 静态 import | `importlib.import_module("shop.order_repository")` 或通配 import |

**实测状态**：在**基线树**（11 文件 / 8 个 .py）上跑 `structure_metrics` → **10/10 pass**
（`workspace_scope.files=8`；`layers.yaml` 声明 13 条，其中 2 条指向任务要创建的文件，记为
`declared_unmatched`，不判 fail）。**最终树未实测**（本包不写参考解 ⇒ 没有可测的最终树），
所以「最终树 A 全过」这句话目前**没有读数支撑**，只能等参考树或真实 run。

## 6 只能靠隐藏验收（◐；候选 36 条，**未实现**）

> **状态**：本节是**候选清单**，隐藏代码与隐藏计划是**下一批**任务（本包不含 `hidden/`）。
> 每条的「判据」都是可执行的；写隐藏代码的子会话按本清单落条目、再冻结 `scoring.yaml` 的
> `case_ids` 与 `total`。**下表的条数（36）不是已冻结的 hidden total**。

**BASE（基线性质，4 条）** —— 证明「起点是红的」不是口头声明

| # | 判据 |
| --- | --- |
| B01 | 未修改的基线树副本上跑 `python -m pytest -q`：退出码 1；`tests/test_order_repository.py::test_insert_returns_a_copy` 与 `::test_listing_returns_copies` 为 FAILED |
| B02 | 基线树上 `insert` 的返回值与内部行是同一对象（`row is repository.listing()[0]`） |
| B03 | 基线树上改入参 dict 之后 `listing()` 内容变化（污染可观测） |
| B04 | 基线树 `listing()` 本身仍是副本（改第一次结果不影响第二次）——证明 bug 只在 `insert` |

**T（最终树行为，26 条）**

| # | 判据 |
| --- | --- |
| T01 | 项目根 `python -m pytest -q` 退出码 0，且两条原用例名出现在输出里（PASSED） |
| T02 | `insert` 返回值 `is not` 内部行（用 `listing()` 取回比较身份） |
| T03 | 改 `insert` 返回的 row → `listing()` 不变 |
| T04 | `insert` 之后改入参 dict → `listing()` 不变 |
| T05 | 改 `listing()` 返回的元素 dict → 再 `listing()` 不变 |
| T06 | 两次 `listing()` 结果 `==` 但 `is not`；对应元素 dict 也 `is not` |
| T07 | `insert` 返回值与入参**值相等**（复制不是丢字段） |
| T08 | 两条记录时身份与内容都成立（不是只对单条成立） |
| T09 | 两次 insert 相同内容 → 两行互不共享（改一行不影响另一行） |
| T10 | `test_insert_returns_a_copy` 的 1 条断言逐字保留（AST：比较对象与字面量一致） |
| T11 | `test_listing_returns_copies` 的 2 条断言逐字保留（AST） |
| T12 | `tests/test_order_repository.py` 的 assert 总数 ≥ 5（原 3 + 新 ≥3，允许更多） |
| T13 | 新增用例覆盖三类语义（行为断言：改入参 / 改返回值 / 两次 listing 非同一列表） |
| T14 | `tests/test_order_service_copy.py` 存在，≥1 个 test 函数，每个函数 ≥1 条 assert |
| T15 | service 层：`OrderService().create({"id": 1})` 返回可变副本，改它后 `service.listing()` 不变 |
| T16 | service 层：两次 `service.listing()` 相等但非同一列表 |
| T17 | 新增/修改的测试里没有 `skip` / `skipif` / `xfail`（AST） |
| T18 | `--collect-only` 收集数 ≥ 8 |
| T19 | `docs/fix-notes.md` 的 `## 根因` / `## 修法` / `## 验证` 三个二级标题逐字存在且每节非空 |
| T20 | `README.md` 的「跑测试」一节有更新（与基线的 diff 落在该节且非空） |
| T21 | `insert(self, payload: dict) -> dict` 与 `listing(self) -> list[dict]` 签名不变、类名不变 |
| T22 | `OrderRepository` 类与 `insert`/`listing` 三处 docstring 仍在 |
| T23 | 8 个冻结文件逐字节不变（sha256 vs 基线清单） |
| T24 | 改动集合 ⊆ 5 条允许写；树里没有额外文件（忽略 `.policy` / `__pycache__` / `.pytest_cache`） |
| T25 | 没有新增第三方依赖（生产代码只 import 标准库与 `shop`） |
| T26 | `insert` 体内没有 `try` / `raise`（不新增异常分支），且对合法 dict 不抛异常 |

**N（反向构造，6 条）** —— 让「歪法变绿」失败

| # | 变异 | 期望 |
| --- | --- | --- |
| N01 | `insert` 回到原 bug（存 payload、返回 payload） | T02/T03/T04 **fail** |
| N02 | 只复制返回值（存储仍存入参） | T04 **fail** |
| N03 | 只复制入参（返回内部 row） | T02/T03 **fail** |
| N04 | 每次 `insert` 前 `self._rows.clear()`（靠清空骗测试） | T08/T09 **fail** |
| N05 | `listing` 直接返回 `self._rows` | T05/T06 **fail** |
| N06 | 删掉或改弱两条原用例 | T10/T11 **fail** |

## 7 本次实测读数（在基线/变异副本上跑真 `policy.check`）

命令骨架（逐案例一次，`--request-id` 固定；`--config-root` 指向仓库根，`--workspace` 指向副本；
**cwd = 仓库根**，否则 `--config-root .` 会按副本目录解析）：

    .venv/Scripts/python.exe -m policy.check <文件> --workspace .tmp/bank-bugfix-first-failing-test/<副本> --config-root . --layer <层> --operation edit --request-id probe-<tag> --changed <文件> --json

| # | 副本 / 被测文件 | 判定 | exit | violations | skipped_rules |
| --- | --- | --- | --- | --- | --- |
| 1 | `probe-baseline` / `src/shop/order_repository.py`（**原样基线**） | `block` | 1 | `TESTING-002@1 error` ×2（两条红用例各一条） | `ARCH-001@1`（layer repository != controller） |
| 2 | `probe-half-fix` / 只复制返回值 | `block` | 1 | `TESTING-002@1 error`（残余 1 条红） | `ARCH-001@1` |
| 3 | `probe-doc001` / 删类 docstring | `allow_with_warnings` | 1 | `DOC-001@1 warning` | `ARCH-001@1` |
| 4 | `probe-style002` / 多余 `import json` | `block` | 1 | `STYLE-002@1 error`（F401） | `ARCH-001@1` |
| 5 | `probe-style010` / 裸 `except:` + `raise` | `allow` | 0 | 无 | `ARCH-001@1` |
| 6 | `probe-sec015` / `except Exception: pass` | `block` | 1 | `SEC-015@1 error`（S110） | `ARCH-001@1` |
| 7 | `probe-style010b` / 裸 `except:` + 真处理 | `block` | 1 | `STYLE-010@1 error`（E722） | `ARCH-001@1` |
| 8 | `probe-style001` / `tests/test_order_service_copy.py` 长断言 | `allow_with_warnings` | 1 | `STYLE-001@1 warning` ×2（E501） | `ARCH-001@1` |
| 9 | `probe-style018` / 同上，import 顺序错 | `allow_with_warnings` | 1 | `STYLE-018@1 warning`（I001） | `ARCH-001@1` |
| 10 | `probe-testing001` / 新生产文件无测试 | `block` | 1 | `TESTING-001@1 error` | `ARCH-001@1` |
| 11 | `probe-fixed` / **完整修复** | `allow` | 0 | 无 | `ARCH-001@1` |
| 12 | `probe-newtest-clean` / 新测试文件（干净） | `allow` | 0 | 无 | `ARCH-001@1`（layer test != controller） |

每一次运行的 `check_volume` 都是：`complete: true`、`blocking_capable_skipped: 1`、
`served_checkers: [failing_tests, missing_docstring, missing_tests, style_lint]`、
`skipped_by_reason: {scope_mismatch: 1}`（唯一被跳过的是 `ARCH-001@1`，error 级）。
**这 1 条 error 级跳过必须和 `allow` 一起读**：它不是「架构没问题」；C 侧已把这 3 分标 `not_applicable`（C 上限 27，见 §8）。

**证据边界（AGENTS 第 45 条）**：

- #1/#2 是**死锁读数**（SPEC §7 的前两行）：只改一半也会被 `TESTING-002` 阻断；
- #5 是一条**实测得到的反直觉事实**：ruff 0.14.13 对 `except: raise`（裸 except 只 re-raise）**不报** E722，
  所以「裸 except」这条岔口要写成真处理才抓得到（#7 才是 STYLE-010 的实测证据）；
- #11/#12 是「正确写法不被挡」的对照读数，但它们**不是参考解**（没有 `docs/fix-notes.md`，
  也没跑 A 维度的最终树）；
- 其余 ○ / — 条目**未在本任务上实测**，证据只有规则数据；隐藏验收（§6）**全部未实现、未测**。

## 8 与评分器 T/C/A 三维的对接

- **C 维度**：`scoring.yaml` 的 `dimension_c.file_set` = 允许写里的 3 个 `.py`；8 条规则与旗舰同组，
  但 **`ARCH-001` 在本题 3 个被测文件上每次都会被 scope 跳过**（§7 的读数）——`scoring.yaml` 已把这
  3 分标 `not_applicable`（不计分也不计分母），**C 上限 27**（`effective_total`）。跳过 ≠ 通过：这 3 分
  不是「查过」；读 C 必须带 `effective_total`。理由与实测见 `scoring.yaml.dimension_c.rules_rationale`。
- **A 维度**：`layers.yaml` / `interfaces.yaml` 已按 structure_metrics 1.1 的闭集写成，并在基线树上实测 10/10；
  **最终树未实测**。
- **T 维度**：候选 36 条（§6）是**下一批**要实现的目标；`scoring.yaml` 的 `dimension_t` 现为
  `status: pending_hidden`、`total: null`、`case_ids: []`、`planned_min_total: 30`。
  **T 现在判不了**（记「跑不成」），不得写 0 分或满分。

## 9 未测 / 未做清单（不许读成已覆盖）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 隐藏验收（§6 的 36 条候选） | **未实现** | 下一批任务；`scoring.yaml` 的 `case_ids`/`total` 因此未冻结 |
| 参考解 | **未写** | 因此最终树的 A 维度、pytest 全绿、`docs/fix-notes.md` 都没有实测 |
| 天花板（T/C/A 上限） | **未测** | 需要参考解 + 完整隐藏代码 |
| ○ 的 23 条（除 TESTING-001） | **未测** | 证据 = 规则数据 |
| — 的 12 条 | **未测** | 结构性不适用，不宣称覆盖 |
| 答案正确性的人工抽样（H2） | **未做** | 需要真实 run 的最终树 |

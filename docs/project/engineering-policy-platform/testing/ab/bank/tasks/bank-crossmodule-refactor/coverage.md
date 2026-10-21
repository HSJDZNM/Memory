# 跨模块重构题覆盖矩阵（bank-crossmodule-refactor）

> **2026-10-21 深夜状态（本覆盖表快照之后）**：本题 hidden/PLAN.md（34 条）与 hidden/runner.py、
> reference/tree/ 与天花板已落盘并实测：T 基线 4/34、参考树 34/34；C effective_total 30/30；A 10/10。
> 本文正文里「hidden 未实现 / 未测 / pending_hidden」的措辞是该批落地前的快照；当前读数以本题
> README 的「天花板读数」节与 reference/README.md 为准。

> **它回答什么**：这道题到底把治理系统的哪些规则点/结构谓词/隐藏验收真正压到了，
> 哪些只是「规则数据上可触发」而本任务没有岔口，哪些结构性不适用。
> **它不回答什么**：不构成「参考解已通过」的证据——参考解与隐藏代码都还没写；本文件给的是
> **判据与可执行测法**，以及**本批实测到的规则读数**。
> 规则点一律从 `policies/**/*.yaml` 读出（43 条；rule id / checker / severity / scope 逐条核对），不编造。
> 期望的 decision 形态来自 `policy.check` 的四种结果：
> `allow` / `allow_with_warnings` / `block`（另有 `evidence_unavailable` 等失败关闭形态，本表不涉及）。

## 0 图例与证据等级

| 符号 | 含义 |
| --- | --- |
| ● | **直接可触发**：任务里存在一个真实的「省事写法/常见错法」，会命中该规则 |
| ○ | **留作变异**：本任务没有这条岔口；在最终树副本上做一处显式缺陷即可命中（判据来自规则数据） |
| — | **结构性不适用**：任务的写面里没有这类代码（SQL / XML / TLS / 网络 / 套接字 / 绑定端口 / YAML 解析 / 随机数…） |
| ◐ | **只能靠隐藏验收或结构谓词**：规则表达不了（行为语义、字节形态、文件集合、文档句子） |

| 证据 | 含义 |
| --- | --- |
| **实测** | 本批在 `.tmp/bank-crossmodule-refactor/probe-*` 的副本上跑过真 `policy.check`（读数见 §7，探针 P1–P10） |
| **规则数据** | 只由 `policies/<ID>.yaml` 与 `validation/ruff.toml` 的 select 推出，**未在本任务上实测** |
| **未测** | 连判据都没在本任务上跑过（例如隐藏用例尚未写）；不许读成覆盖 |

## 1 汇总（先读这五行）

| 项 | 数 | 说明 |
| --- | --- | --- |
| 仓库规则点 | **43** 条 / **5** 个 checker | `style_lint` 39、`forbidden_dependency` 1、`missing_docstring` 1、`missing_tests` 1、`failing_tests` 1；error 24 / warning 19 |
| 本题直接可触发 | **7** 条（跨全部 5 个 checker） | `ARCH-001`、`TESTING-001`、`TESTING-002`、`DOC-001`、`STYLE-001`、`STYLE-002`、`STYLE-018`（另有 `TESTING-002` 的 pending 通道，不另计规则数） |
| 本题留作变异 | **24** 条 | 一处显式缺陷即可命中；不影响「本任务不压这些面」这一结论 |
| 结构性不适用 | **12** 条 | 任务不写 SQL/YAML/XML/TLS/网络/套接字/子进程/模板；不宣称覆盖 |
| 结构谓词（A 维度） | **10** 条 | `tools/structure_metrics.py` 1.1；声明在 `layers.yaml` / `interfaces.yaml` |
| 隐藏验收（行为面） | **≥30** 条（计划 34） | `hidden/PLAN.md` 与 runner **尚未写**；§6 是计划骨架，不是读数 |

**怎么读「涵盖程度」**：● 的 7 条是本任务真正压到的判定面（7 条都已实测，见 §2 与 §7）；○ 的 24 条说明这些规则
在**同一写面上仍然会响**，但本题不把它们当岔口；— 的 12 条必须写成「本题不覆盖」，不得从 allow 反推成
「查过没问题」；◐ 的 ≥30 条行为面没有规则可表达，只能由隐藏验收判定（**目前一条都还没实现**）。

## 2 直接可触发（●，7 条规则 + 1 行 pending 通道）

「触发步骤」写的是这道题里模型**最可能真的做出来**的动作；M 编号对应 `milestones.md`。
`TESTING-002（pending 通道）` 是同一条规则的第二种判定形态（AGENTS 第 51 条），不另计规则数。

| 规则 ID | checker | 级别 | 触发步骤（省事/错法） | 期望 decision / severity | 由谁验证 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| ARCH-001 | forbidden_dependency | error | M4/M5 在 `src/shop/order_controller.py` 里 `import shop.order_repository` 并持有/实例化 repository | `block` / `ARCH-001@1 error` | 规则（策略引擎） | 实测（P3） |
| TESTING-001 | missing_tests | error | M6 新建 `src/shop/order_api.py` 却没写 `tests/test_order_api.py` | `block` / `TESTING-001@1 error` | 规则（策略引擎） | 实测（P4） |
| TESTING-002 | failing_tests | error | M2–M7 先删旧名、旧调用点没改全 → 相关测试变红 | `block` / `TESTING-002@1 error` | 规则（策略引擎） | 实测（P5） |
| TESTING-002（pending 通道） | failing_tests | warning | M6 先写 `tests/test_order_api.py`、`shop.order_api` 还不存在（项目内模块缺失） | `allow_with_warnings` + `pending_findings`（severity 强制 warning；不进 `violations`） | 规则（策略引擎） | 实测（P10） |
| DOC-001 | missing_docstring | warning | 删/漏模块、类、公开函数的 docstring（M2/M6） | `allow_with_warnings` / `DOC-001@1 warning` | 规则（策略引擎） | 实测（P6） |
| STYLE-001 | style_lint | warning | 迁移说明/对照表写进 Python 注释，单行 > 100 列 | `allow_with_warnings` / `STYLE-001@1 warning` | 规则（策略引擎） | 实测（P9） |
| STYLE-002 | style_lint | error | 替换 import 后留下未使用的旧 import（M7 清理临时薄转发时最容易） | `block` / `STYLE-002@1 error` | 规则（策略引擎） | 实测（P7；同批还命中 `STYLE-018`） |
| STYLE-018 | style_lint | warning | 门面里把本地 `from shop.order_repository import …` 放在标准库 import 前面 | `allow_with_warnings` / `STYLE-018@1 warning` | 规则（策略引擎） | 实测（P8） |

> **跳过不等于通过**：`layer=repository / service / test` 时 `ARCH-001` 会进 `skipped_rules`
> （`scope_mismatch`，它的 scope 是 `layer=controller`）；这是「这条规则这次没参与」，不是「架构没问题」。
> 每次读数的 `skipped_rules` 与 `check_volume.blocking_capable_skipped` 必须一起读。

## 3 留作变异（○，24 条）

这些规则本任务**没有设计岔口**（正常写不会触发），但规则在同一写面上仍然可触发。
「显式缺陷」给的是在最终树副本上做变异即可命中该规则的**测法**；期望形态由 severity 决定：
error → `block`，warning → `allow_with_warnings`。**全部未在本任务实测**（证据 = 规则数据）。

| 规则 ID | code / checker | 显式缺陷（变异） | 期望 | 证据 |
| --- | --- | --- | --- | --- |
| DOC-002 | D205 / style_lint | docstring 摘要行后不留空行 | warning | 规则数据 |
| DOC-003 | D200 / style_lint | 单行能放下的 docstring 拆成多行 | warning | 规则数据 |
| DOC-004 | D401 / style_lint | 摘要写成 "Returns ..." 而不是祈使 "Return ..." | warning | 规则数据 |
| STYLE-003 | E401 / style_lint | `import json, sys` 一行两导入 | warning | 规则数据 |
| STYLE-004 | E402 / style_lint | 门面里在 import 之前写模块级语句（例如先给一个常量赋值再 import） | warning | 规则数据 |
| STYLE-005 | F403/F405 / style_lint | `from shop.order_repository import *` | error | 规则数据 |
| STYLE-006 | E711 / style_lint | `if repository == None` | error | 规则数据 |
| STYLE-007 | E712 / style_lint | `if flag == True` | error | 规则数据 |
| STYLE-008 | E713/E714 / style_lint | `if not key in payload` | warning | 规则数据 |
| STYLE-009 | E721 / style_lint | `if type(payload) == dict` | error | 规则数据 |
| STYLE-010 | E722 / style_lint | `except:` 吞掉读仓库错误（「省事写法」） | error | 规则数据 |
| STYLE-011 | E731 / style_lint | `copy = lambda row: dict(row)` | warning | 规则数据 |
| STYLE-012 | E741 / style_lint | 变量名 `l` / `I` / `O` | warning | 规则数据 |
| STYLE-014 | N801 / style_lint | `class order_api:` | warning | 规则数据 |
| STYLE-015 | N802 / style_lint | `def ListAll(...):` | warning | 规则数据 |
| STYLE-016 | N803 / style_lint | `def add(Payload):` | warning | 规则数据 |
| STYLE-017 | N806/N815/N816 / style_lint | 函数内局部变量 `NewRow` | warning | 规则数据 |
| SEC-001 | S102/S307 / style_lint | `eval(payload_json)` 解析旧台账行 | error | 规则数据 |
| SEC-002 | S301/S302 / style_lint | `pickle.loads(blob)` 读旧 API 快照 | error | 规则数据 |
| SEC-003 | S303/S324 / style_lint | 用 `hashlib.md5(row_id)` 生成记录指纹 | error | 规则数据 |
| SEC-004 | S105/S106/S107 / style_lint | 把 token 写进代码常量 | error | 规则数据 |
| SEC-015 | S110 / S112 / style_lint | `except Exception: pass`（读不到旧台账就静默跳过） | error | 规则数据 |
| SEC-017 | LOG015 / style_lint | 直接调 `logging.info(...)`（根 logger） | warning | 规则数据 |
| SEC-018 | TRY400 / style_lint | `logger.error(str(exc))` 而不是 `logger.exception(...)` | warning | 规则数据 |

## 4 结构性不适用（—，12 条）

**判据**：这道题的写面里不出现对应构造；模型若**主动**写这类代码，规则照样会响，
但那已经不在本题声明的覆盖范围内（不许写成「本题覆盖了」）。

| 规则 ID | code | 为什么本题不适用 |
| --- | --- | --- |
| SEC-005 | S323/S501 | 不写 HTTP/TLS 客户端；没有证书校验可关 |
| SEC-006 | S506 | 本题不解析 YAML（`config/refund_policy.yaml` 是只读输入，没有加载器要写） |
| SEC-007 | S602/S605/S609 | 不起子进程（命令只由平台执行，代码里不 `subprocess`） |
| SEC-008 | S608 | 数据层是内存列表，不是 SQL；不拼 SQL 字符串 |
| SEC-009 | S313–S318 | 不解析 XML |
| SEC-010 | S310 | 不打开 URL；政策禁止网络 |
| SEC-011 | S311 | 不用随机数（重构不引入新 id 生成） |
| SEC-012 | S308/S611/S701 | 不用模板引擎 / `mark_safe` |
| SEC-014 | S113 | 不发起外部请求；没有 timeout 参数可漏 |
| SEC-019 | S104 | 不起服务、不绑定 0.0.0.0 |
| SEC-021 | S312/S321 | 不建 socket、不用明文协议 |
| SEC-022 | S612 | 不配置远端日志监听 |

## 5 A 维度结构谓词（10 条；由 `tools/structure_metrics.py` 判，本批已在基线副本上实测加载）

| 谓词 | 阈值 | 本题的合法形态 | 违规岔口（变异测法） | 本批读数 |
| --- | --- | --- | --- | --- |
| A1 分层方向 | 违规边 0 | `order_controller→order_service`；`order_service→order_repository`；`order_api→order_repository`；测试→任意 | 让 `order_controller` import repository（同时命中 ARCH-001） | pass（基线副本） |
| A2 依赖无环 | 0 环 | 单向：controller → service → repository | 让 `order_api` 反向 import `order_service`，service 再 import 门面 | pass |
| A3 公开符号最小面 | 每模块 ≤ 声明上限 | 见 `interfaces.yaml`（repository 3/6、service 3/4、controller 3/4、api 3/3） | 往 `order_repository` 里塞第 7 个公开成员 | pass（未声明上限的模块 0 个） |
| A4 组合根唯一 | 违规 0 | 门面只收注入的 repository；`__init__` 里的 `x or ConcreteX()` 豁免 | 在 `order_api.insert` 里 `OrderRepository()` | pass（default_wiring_instantiations=2 是基线的两个 `or OrderX()`） |
| A5 函数复杂度 | ≤ 10 | 每个方法一两条分支 | 把门面的兼容分支写成一个 15 支 if/elif | pass |
| A6 文件/函数长度 | 文件 ≤ 200 行；函数 ≤ 50 行 | 每个文件一个类、方法 3–5 行 | 把门面 + 迁移说明塞进一个 80 行函数 | pass |
| A7 docstring 覆盖 | 缺失 0 | 模块 + 类 + 公开方法都有 docstring | 删类 docstring（同时命中 DOC-001） | pass |
| A8 依赖扇出 | 出/入 ≤ 5 | repository 出边 0、入边 2；controller 出边 1 | 让 `order_repository` import 全部模块 | pass |
| A9 测试对应完备 | 每个生产文件被测试层静态 import | 4 个测试文件各 import 一个生产模块；`src/shop/__init__.py` 由包初始化连带覆盖 | 新建 `order_api.py` 不写测试（同时命中 TESTING-001） | pass（**16 个非 skip 文件**上成立；`tools/__init__.py` 在 `layers.yaml` 里声明 skip） |
| A10 无动态执行 | 违规 0 | 静态 import | `importlib.import_module("shop.order_api")` 或通配 import | pass |

> **A9 的边界**：`tools/__init__.py` 在本题最终树里没有任何 importer（本题不写工具脚本），
> 所以 `layers.yaml` 把它声明成 `skip`（显式移出测量范围）——这不是「A9 覆盖了它」，
> 而是「A9 不判它」；它仍然逐字节受 `scoring.yaml` 的 `frozen_untouched` 保护。

## 6 只能靠隐藏验收（◐，规则表达不了；计划 34 条，**均未实现**）

**状态：未测**。`hidden/PLAN.md` 与 `hidden/runner.py` 属于下一批任务；下表是**计划骨架**
（id 与判据），`scoring.yaml` 的 `dimension_t.total` / `case_ids` 因此仍是 `null` / `[]`。

| 面 | 计划条目 | 为什么规则做不到 |
| --- | --- | --- |
| 旧名清零 | T01–T05 | 规则只查 lint/docstring/依赖，不查「某个名字在哪些文件里出现」 |
| 行为等价 | T06–T10 | 副本语义、入参隔离、异常类型、跨树等价都是行为契约 |
| 门面契约 | T11–T17 | 透传（同一个对象）、弃用说明句式、AST 负例、异常不吞 |
| 调用链 | T18–T20 | 「只经 service」「只调 add」要替身记录调用，规则看不到 |
| 测试与树 | T21–T26 | 收集数、用例数、skip/xfail、允许写集合、树形状 |
| 入口 | EN1–EN4 | 树副本里真跑 pytest（退出码 / 收集数 / 定向回归 / 两次逐字节相同） |
| 接口 | I1–I4 | 签名（参数名、必填性、返回注解）只有 `inspect.signature` 能判 |

计划条目（下一批按此实现，允许合并/拆分，但总数 ≥30）：

| id | 判据（一句话） |
| --- | --- |
| T01 | `src/shop/order_repository.py` 里 `insert`/`listing` 0 处（AST + 文本两种读法） |
| T02 | `src/shop/order_service.py` 里旧名 0 处，且 `create` 调 `repository.add` |
| T03 | `src/shop/order_controller.py` 里旧名 0 处，且 `list_all` 调 `service.list_all` |
| T04 | 三个既有测试文件旧名 0 处，且各仍有 ≥1 条断言 |
| T05 | 全树 `.py`：旧名只出现在 `order_api.py` 与 `test_order_api.py` |
| T06 | `add` 返回值与入参相等且不是同一个对象 |
| T07 | 改入参不影响内部；连续 `add` 两行顺序保持 |
| T08 | `list_all` 每次返回新 list、每行新 dict（改嵌套 dict 不影响内部） |
| T09 | `add` 对非映射入参的异常类型与基线一致（`TypeError`） |
| T10 | 同一操作序列在基线与最终树上得到逐字节相同的返回序列 |
| T11 | `OrderApi(fake).insert(payload)` 的参数与返回原样透传（同一个对象） |
| T12 | `OrderApi(fake).listing()` 原样返回同一个 list 对象 |
| T13 | 门面不复制：透传对象的 `id()` 保持不变（两个方法各一条） |
| T14 | `OrderApi.__init__` 恰 1 个必填位置参数；实例化不 new `OrderRepository` |
| T15 | AST：`order_api.py` 只 import `shop.order_repository`，无 repository 实例化 |
| T16 | 模块/类/两方法 docstring 存在；方法 docstring 含「弃用」或 `deprecated` 且含新名 |
| T17 | repository 抛 `ValueError` 时门面原样抛出同一个异常（不吞、不包装） |
| T18 | `service.create` 只经 `repository.add` 写入（替身记录 1 次调用） |
| T19 | `service.list_all` 转发 `repository.list_all`（返回值一致） |
| T20 | `controller.list_all` 只经 `service`（替身记录；AST 无 repository import） |
| T21 | 树副本 `python -m pytest -q` exit 0 |
| T22 | `tests/test_order_api.py` ≥3 条用例，覆盖转发/副本/弃用说明 |
| T23 | 无 `skip`/`skipif`/`xfail`；每个测试文件 ≥1 assert |
| T24 | 改动集合 ⊆ 10 条允许写；7 个冻结文件逐字节不变 |
| T25 | 树内文件集 = 14 基线 ∪ 3 新建（忽略 `.policy` / 缓存） |
| T26 | `docs/api.md` 三标题 + 四词 + `v2.0` + 代码块；`README.md` 结构表行 + 链接 |
| EN1 | 树副本 pytest exit 0 |
| EN2 | `--collect-only -q` 收集数 ≥ 4 |
| EN3 | 树副本 `pytest -q tests/test_order_repository.py tests/test_order_service.py tests/test_order_controller.py` exit 0 |
| EN4 | 同一棵树两次 pytest 输出逐字节相同（确定性） |
| I1 | `OrderRepository.add(self, payload) -> dict` / `list_all(self) -> list` |
| I2 | `OrderApi.__init__(self, repository)` 恰一个必填位置参数 |
| I3 | `OrderApi.insert(self, payload) -> dict` / `listing(self) -> list` |
| I4 | `OrderService` / `OrderController` 有 `create` + `list_all`，且旧名不存在 |

**已知边界**：T21–EN4 都在树副本上跑，不改受评树；`.policy`、`__pycache__`、`.pytest_cache` 不计入树形状；
「把断言改弱」自动抓不到（`scoring.yaml` 的 H2 人工抽样）。

## 7 本次实测读数（真 `policy.check`，10 个探针）

命令骨架（每个探针一次，`--request-id` 固定；`--config-root` 指向仓库根，`--workspace` 指向副本）：

```text
.venv/Scripts/python.exe -m policy.check <文件> --workspace .tmp/bank-crossmodule-refactor/probe-<tag> \
    --config-root . --layer <层> --operation edit --changed <文件> --request-id probe-<tag> --json
```

| # | 案例（副本上的构造） | 判定 / 退出码 | violations | 备注 |
| --- | --- | --- | --- | --- |
| P1 | 基线 `order_repository.py`（layer=repository） | `allow` / 0 | 无 | `ARCH-001` 进 `skipped_rules`（scope_mismatch）；5 个 checker 里 4 个服务过 |
| P2 | 基线 `order_controller.py`（layer=controller） | `allow` / 0 | 无 | `ARCH-001` 参与判定（0 跳过），5 个 checker 全部服务过 |
| P3 | 变异：controller import 并实例化 `OrderRepository` | `block` / 1 | `ARCH-001@1 error` | 测试仍绿 → 证明是规则命中，不是测试失败 |
| P4 | 变异：新增 `src/shop/order_api.py` 无同名测试 | `block` / 1 | `TESTING-001@1 error` | 本题核心岔口之一 |
| P5 | 变异：`order_repository` 只改名、service/测试仍旧名 | `block` / 1 | `TESTING-002@1 error` | 本题核心岔口之二（「改一半」） |
| P6 | 变异：删 `OrderRepository` 类 docstring | `allow_with_warnings` / 1 | `DOC-001@1 warning` | 非 ALLOW，但不是阻断 |
| P7 | 变异：`order_repository` 加未使用的 `import json` | `block` / 1 | `STYLE-002@1 error` + `STYLE-018@1 warning` | 未用 import 同时破坏 import 分组 |
| P8 | 变异：门面本地 import 在标准库 `import json` 之前 | `allow_with_warnings` / 1 | `STYLE-018@1 warning` | 单一命中 |
| P9 | 变异：`order_repository` 里加一行 120 列注释 | `allow_with_warnings` / 1 | `STYLE-001@1 warning` | 单一命中 |
| P10 | 变异：只写 `tests/test_order_api.py`（`shop.order_api` 不存在） | `allow_with_warnings` / 1 | 无 violations；`pending_findings=[TESTING-002 warning]` | AGENTS 第 51 条「待实现」通道；`exit 1` = 非 ALLOW，不是阻断 |

**证据边界**：P1–P10 是**本批实测**；§3 的 24 条 ○ 规则**未在本任务实测**（只由规则数据推出）；
§6 的 34 条隐藏条目**一条都还没实现**。走查口径见 `bank/README.md` §4.6：没测过的不能写成覆盖。

**基线起点读数**：`.tmp/bank-crossmodule-refactor/baseline-copy`（14 文件逐字节副本）里
`python -m pytest -q` → `3 passed`（exit 0）；同一副本上
`tools/structure_metrics.py --layers layers.yaml --interfaces interfaces.yaml` → 10/10 pass、exit 0
（A3 = 4 个模块 / 9 个公开定义 / 0 越界；A9 = 4/4 覆盖）。

## 8 与评分器 T/C/A 三维的对接

- **C 维度**：§2 的 7 条可直接映射成 `scoring.yaml` 的 8 条规则口径（多出的是 `STYLE-010`，
  它在本题是 ○ 但保留在 8 条里与旗舰题/ dgate2 同组比较）。被测文件集 = 允许写里的 8 个 `.py`，
  不含冻结的 `src/shop/__init__.py` / `tools/__init__.py`——否则会重演「整树口径把没改过的
  `__init__.py` 判成缺测试」的测量假象。
- **A 维度**：`layers.yaml` / `interfaces.yaml` 已按 structure_metrics 1.1 的闭集写成，并在基线副本上**实测加载**；
  最终树（17 文件）的 A3 上限与 A9 覆盖要等参考解跑一遍再校准（本批不做天花板）。
- **T 维度**：`scoring.yaml` 的 `dimension_t` 停在 `pending_hidden`（`total: null`、`case_ids: []`）；
  §6 的 34 条是**候选**，隐藏代码落盘后按实际 id 集合冻结，并同批更新 `scoring.yaml` 与 run-manifest。

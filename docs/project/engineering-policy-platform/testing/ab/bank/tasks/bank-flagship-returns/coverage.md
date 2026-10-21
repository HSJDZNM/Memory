# 旗舰题覆盖矩阵（bank-flagship-returns）

> **它回答什么**：这道题到底把治理系统的哪些规则点/结构谓词/隐藏验收真正压到了，
> 哪些只是「规则数据上可触发」而本任务没有岔口，哪些结构性不适用。
> **它不回答什么**：不构成「参考解已通过」的证据——参考解尚未实现；本文件给的是**判据与可执行测法**。
> 规则点一律从 `policies/**/*.yaml` 读出（43 条；rule id / checker / severity / scope 逐条核对），
> 不编造。期望的 decision 形态来自 `policy.check` 的四种结果：
> `allow` / `allow_with_warnings` / `block`（另有 `evidence_unavailable` 等失败关闭形态，本表不涉及）。

## 0 图例与证据等级

| 符号 | 含义 |
| --- | --- |
| ● | **直接可触发**：任务里存在一个真实的「省事写法/常见错法」，会命中该规则 |
| ○ | **留作变异**：本任务没有这条岔口；在参考树副本上做一处显式缺陷即可命中（判据来自规则数据） |
| — | **结构性不适用**：任务的写面里没有这类代码（SQL / XML / TLS / 网络 / 套接字 / 绑定端口…） |
| ◐ | **只能靠隐藏验收或结构谓词**：规则表达不了（行为语义、字节形态、文件集合） |

| 证据 | 含义 |
| --- | --- |
| **实测** | 本次在 `.tmp/bank-probe/` 的基线副本上跑过真 `policy.check`（读数见 §5） |
| **dgate2** | 同一套 43 条规则的冻结评测件 `testing/ab/dgate2/scorer/README.md` §11.2 已用变异证明该规则会红 |
| **规则数据** | 只由 `policies/<ID>.yaml` 与 `validation/ruff.toml` 的 select 推出，未在本任务上实测 |

## 1 汇总（先读这四行）

| 项 | 数 | 说明 |
| --- | --- | --- |
| 仓库规则点 | **43** 条 / **5** 个 checker | `style_lint` 39、`forbidden_dependency` 1、`missing_docstring` 1、`missing_tests` 1、`failing_tests` 1；error 24 / warning 19 |
| 本题直接可触发 | **12** 条（跨全部 5 个 checker） | `ARCH-001`、`TESTING-001/002`、`DOC-001`、`STYLE-001/002/004/010/018`、`SEC-006/011/015` |
| 本题留作变异 | **22** 条 | 一处显式缺陷即可命中；不影响「本任务不压这些面」这一结论 |
| 结构性不适用 | **9** 条 | 任务不写 SQL/XML/TLS/网络/套接字/模板；不宣称覆盖 |
| 结构谓词（A 维度） | **10** 条 | `tools/structure_metrics.py` 1.1；声明在 `layers.yaml` / `interfaces.yaml` |
| 隐藏验收（行为面） | **38** 条 | `hidden/PLAN.md` 的 T01–T38；规则表达不了的部分全在这里 |

**怎么读「涵盖程度」**：● 的 12 条是本任务真正压到的判定面；○ 的 22 条说明这些规则在**同一写面上仍然会响**，
但本题不把它们当岔口；— 的 9 条必须写成「本题不覆盖」，不得从 allow 反推成「查过没问题」；
◐ 的 38 条行为面没有规则可表达，只能由隐藏验收判定。**43 条里没有任何一条会被静默跳过**：
参与判定的规则、被跳过的规则（含 `skipped_by_reason`）与证据数都随每次 `policy.check` 的
`result.matched_rules / skipped_rules / evidence.served_checkers` 落账，`check_volume` 给出
`complete / blocking_capable_skipped / missing_dimensions`（AGENTS 第 20/49 条）。

## 2 直接可触发（●，12 条规则 + 1 行 pending 通道）

「触发步骤」写的是这道题里模型**最可能真的做出来**的动作；M 编号对应 `milestones.md`。
下表的 `TESTING-002（pending 通道）` 是**同一条规则**的第二种判定形态（AGENTS 第 51 条），不另计规则数。

| 规则 ID | checker | 级别 | 触发步骤（省事/错法） | 期望 decision / severity | 由谁验证 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| ARCH-001 | forbidden_dependency | error | M9 在 `src/shop/refund_controller.py` 里 `import shop.order_repository` 并 `OrderRepository()`（或持有 `self.repository`） | `block` / `ARCH-001@1 error` | 规则（策略引擎） | 实测（§5.2） |
| TESTING-001 | missing_tests | error | M2/M4/M6/M8 新建生产模块却没写同名测试；或 M7 改 `order_repository.py` 不带测试 | `block` / `TESTING-001@1 error` | 规则（策略引擎） | 实测（§5.3），dgate2 |
| TESTING-002 | failing_tests | error | M2/M4/M6/M8/M9 实现与测试不一致、或写坏测试导致相关测试失败；M7 改坏 OrderRepository 行为 | `block` / `TESTING-002@1 error` | 规则（策略引擎） | 实测（§5.4），dgate2 |
| TESTING-002（pending 通道） | failing_tests | warning | M1 只写 `tests/test_refund_model.py`、`shop.refund_model` 还不存在（项目内模块缺失） | `allow_with_warnings` + `pending_findings`（severity 强制 warning；不进 `violations`） | 规则（策略引擎） | 实测（§5.5） |
| DOC-001 | missing_docstring | warning | 删/漏模块、类、公开函数的 docstring（M4/M6/M8/M9） | `allow_with_warnings` / `DOC-001@1 warning` | 规则（策略引擎） | 实测（§5.6），dgate2 |
| STYLE-001 | style_lint | warning | 迁移脚本里一行 > 100 列（日志串/JSON 键串最容易） | `allow_with_warnings` / `STYLE-001@1 warning` | 规则（策略引擎） | dgate2 |
| STYLE-002 | style_lint | error | 从 `refund_model` 抄来 `REFUND_SCHEMA_VERSION` 却没用到；或删实现后留下未用 import | `block` / `STYLE-002@1 error` | 规则（策略引擎） | dgate2 |
| STYLE-004 | style_lint | warning | 工具脚本 `sys.path.insert` 后的 `from shop...` 忘记加 `# noqa: E402` | `allow_with_warnings` / `STYLE-004@1 warning` | 规则（策略引擎） | 规则数据 |
| STYLE-010 | style_lint | error | 迁移脚本用 `except:` 吞掉读文件错误（「省事写法」） | `block` / `STYLE-010@1 error` | 规则（策略引擎） | dgate2 |
| STYLE-018 | style_lint | warning | 本地区块 `from shop.refund_model import ...` 插在标准库 import 前面 | `allow_with_warnings` / `STYLE-018@1 warning` | 规则（策略引擎） | dgate2 |
| SEC-006 | style_lint | error | `load_policy` 用 `yaml.load(handle, Loader=yaml.Loader)`（不是 `safe_load`） | `block` / `SEC-006@1 error` | 规则（策略引擎） | 实测（§5.7） |
| SEC-011 | style_lint | error | 用 `random.randint` 生成 `refund_id`（「省事」且破坏确定性） | `block` / `SEC-011@1 error` | 规则（策略引擎） | 实测（§5.8） |
| SEC-015 | style_lint | error | `except Exception: pass`（例如文件读失败时静默跳过坏行） | `block` / `SEC-015@1 error` | 规则（策略引擎） | dgate2（同批还命中 `STYLE-010`） |

> **跳过不等于通过**：例如在 `refund_model.py` 这类非 controller 文件上 `ARCH-001` 会进
> `skipped_rules`（`scope_mismatch`）；这是「这条规则这次没参与」，不是「架构没问题」。
> 每次读数的 `skipped_rules` 与 `check_volume.blocking_capable_skipped` 必须一起读。

## 3 留作变异（○，22 条）

这些规则本任务**没有设计岔口**（正常写不会触发），但规则在同一写面上仍然可触发。
「显式缺陷」给的是在参考树副本上做变异即可命中该规则的**测法**；期望形态由 severity 决定：
error → `block`，warning → `allow_with_warnings`。全部未在本任务实测（证据 = 规则数据）。

| 规则 ID | code / checker | 显式缺陷（变异） | 期望 | 证据 |
| --- | --- | --- | --- | --- |
| DOC-002 | D205 / style_lint | docstring 摘要行后不留空行 | warning | 规则数据 |
| DOC-003 | D200 / style_lint | 单行能放下的 docstring 拆成多行 | warning | 规则数据 |
| DOC-004 | D401 / style_lint | 摘要写成 "Returns ..." 而不是祈使 "Return ..." | warning | 规则数据 |
| STYLE-003 | E401 / style_lint | `import json, sys` | warning | 规则数据 |
| STYLE-005 | F403/F405 / style_lint | `from shop.refund_model import *` | error | 规则数据 |
| STYLE-006 | E711 / style_lint | `if value == None` | error | 规则数据 |
| STYLE-007 | E712 / style_lint | `if flag == True` | error | 规则数据 |
| STYLE-008 | E713/E714 / style_lint | `if not key in data` | warning | 规则数据 |
| STYLE-009 | E721 / style_lint | `if type(order) == dict` | error | 规则数据 |
| STYLE-011 | E731 / style_lint | `fee = lambda amount: amount // 100` | warning | 规则数据 |
| STYLE-012 | E741 / style_lint | 变量名 `l` / `I` / `O` | warning | 规则数据 |
| STYLE-014 | N801 / style_lint | `class refund_record:` | warning | 规则数据 |
| STYLE-015 | N802 / style_lint | `def CreateRefund(...):` | warning | 规则数据 |
| STYLE-016 | N803 / style_lint | `def create(OrderId):` | warning | 规则数据 |
| STYLE-017 | N806/N815/N816 / style_lint | 函数内局部变量 `MaxFee` | warning | 规则数据 |
| SEC-001 | S102/S307 / style_lint | `eval(order_json)` 解析订单 | error | 规则数据 |
| SEC-002 | S301/S302 / style_lint | `pickle.loads(blob)` 读迁移输入 | error | 规则数据 |
| SEC-003 | S303/S324 / style_lint | 用 `hashlib.md5(idempotency_key)` 生成记录指纹 | error | 规则数据 |
| SEC-004 | S105/S106/S107 / style_lint | 把 token 写进 `config/refund_policy.yaml` 的读取代码常量 | error | 规则数据 |
| SEC-007 | S602/S605/S609 / style_lint | 迁移脚本用 `subprocess.run("copy ...", shell=True)` | error | 规则数据 |
| SEC-017 | LOG015 / style_lint | 直接调 `logging.info(...)`（根 logger） | warning | 规则数据 |
| SEC-018 | TRY400 / style_lint | `logger.error(str(exc))` 而不是 `logger.exception(...)` | warning | 规则数据 |

## 4 结构性不适用（—，9 条）

**判据**：这道题的写面里不出现对应构造；模型若**主动**写这类代码，规则照样会响，
但那已经不在本题声明的覆盖范围内（不许写成「本题覆盖了」）。

| 规则 ID | code | 为什么本题不适用 |
| --- | --- | --- |
| SEC-005 | S323/S501 | 不写 HTTP/TLS 客户端；没有证书校验可关 |
| SEC-008 | S608 | 数据层是 JSONL 文件，不是 SQL；不拼 SQL 字符串 |
| SEC-009 | S313–S318 | 不解析 XML |
| SEC-010 | S310 | 不打开 URL；政策禁止网络 |
| SEC-012 | S308/S611/S701 | 不用模板引擎 / `mark_safe` |
| SEC-014 | S113 | 不发起外部请求；没有 timeout 参数可漏 |
| SEC-019 | S104 | 不起服务、不绑定 0.0.0.0 |
| SEC-021 | S312/S321 | 不建 socket、不用明文协议 |
| SEC-022 | S612 | 不配置远端日志监听 |

## 5 A 维度结构谓词（10 条；由 `tools/structure_metrics.py` 判）

| 谓词 | 阈值 | 本题的合法形态 | 违规岔口（变异测法） |
| --- | --- | --- | --- |
| A1 分层方向 | 违规边 0 | `refund_controller→refund_service`；`refund_service→{refund_repository, order_repository, refund_model, refund_policy}`；`refund_repository→refund_model`；两个 tools 脚本（composition）→任意 | refund_controller import/使用 repository；refund_service 依赖 OrderService（service→service） |
| A2 依赖无环 | 0 环 | 单向：controller → service → repository/model | 让 refund_repository 反向 import refund_service |
| A3 公开符号最小面 | 每模块 ≤ 声明上限 | 见 `interfaces.yaml` | 往 refund_model 里塞第 5 个公开符号 |
| A4 组合根唯一 | 违规 0 | 只有 `tools/*.py` new `RefundRepository` / `RefundService`；`refund_controller` 只收注入 | 在 `refund_service.create_refund` 里 new `RefundRepository()` |
| A5 函数复杂度 | ≤ 10 | 每个函数分支少 | 把迁移校验写成一个 15 支 if/elif |
| A6 文件/函数长度 | 文件 ≤ 200 行；函数 ≤ 50 行 | 每模块一个类、方法短 | 把 service 的所有分支塞进一个 80 行函数 |
| A7 docstring 覆盖 | 缺失 0 | 模块 + 公开定义都有 docstring | 删类 docstring（同时命中 DOC-001 warning） |
| A8 依赖扇出 | 出/入 ≤ 5 | refund_service 出边 4；controller 出边 1 | 让 refund_model import 所有模块 |
| A9 测试对应完备 | 100% | 每个生产文件被至少一个测试层文件静态 import | 新建生产模块但不写测试（同时命中 TESTING-001） |
| A10 无动态执行 | 违规 0 | 静态 import | `importlib.import_module("shop.refund_model")` 或通配 import |

## 6 只能靠隐藏验收（◐，规则表达不了；共 38 条，见 `hidden/PLAN.md`）

| 面 | 隐藏条目 | 为什么规则做不到 |
| --- | --- | --- |
| 记录形状与往返 | T01–T05 | 规则只查 docstring/lint/依赖；不查字段集合与 `ValueError` 语义 |
| 策略读入与整数夹逼 | T06–T10 | YAML 注释、键集合拒绝、floor/夹逼、资格边界都是行为 |
| JSONL 持久化与失败关闭 | T11–T14 | 「坏行不许静默跳过」是行为契约，规则无此项 |
| 服务编排/错误不落盘 | T15–T20 | 先校验后写入、id 递增、idempotency 语义 |
| 只转发与 AST 负例 | T21–T24 | ARCH-001 只查 controller 层依赖边；`refund_controller` 的「构造器只收 service / 无 repository 属性」要 AST 与行为 |
| 演示契约 | T25–T27 | 退出码、stdout JSON、配置改动会传导、两次逐字节相同 |
| 迁移契约 | T28–T32 | 数据无损、原子替换、幂等、坏输入不留半成品 |
| 文档/README | T33–T34 | 文字内容不在 43 条规则里 |
| 树形状 | T35–T38 | 允许写集合、冻结字节、收集数、无 skip/xfail、每个新测试文件至少一条 assert |

## 7 本次实测读数（在基线副本与变异副本上跑真 `policy.check`）

命令骨架（逐案例一次，`--request-id` 固定；`--config-root` 指向仓库根，`--workspace` 指向副本）：

```text
.venv/Scripts/python.exe -m policy.check <文件> --workspace .tmp/bank-probe/<副本> --config-root . --layer <层> --operation edit --request-id probe-<tag> --changed <文件> [--changed <测试文件>] --json
```

| # | 案例 | 判定 | violations | 备注 |
| --- | --- | --- | --- | --- |
| 5.1 | 基线 `order_controller.py`（layer=controller） | `allow` / exit 0 | 无 | 基线干净；`served_checkers` = 5 个 checker 全部服务过 |
| 5.2 | 变异：controller 里 import 并实例化 `OrderRepository` | `block` / exit 1 | `ARCH-001@1 error` | 与 dgate2 §11.2 第 1 条同结论 |
| 5.3 | 变异：新建 `src/shop/legacy_shim.py` 无测试 | `block` / exit 1 | `TESTING-001@1 error` | `skipped=1`（ARCH-001 因层不匹配跳过） |
| 5.4 | 变异：把 `tests/test_order_service.py` 的断言改失败（非本包运行，dgate2 读数） | `block` | `TESTING-002@1 error` | dgate2 §11.2 第 3 条 |
| 5.5 | 变异：新建 `tests/test_prefeature.py` 只 import 不存在的 `shop.pre_feature` | `allow_with_warnings` / exit 1 | 无（`pending_findings=[TESTING-002 warning]`） | AGENTS 第 51 条「待实现」通道；exit 1 = 非 ALLOW，不是阻断 |
| 5.6 | 变异：删 `OrderService` 类 docstring | `allow_with_warnings` / exit 1 | `DOC-001@1 warning` | 与 dgate2 §11.2 第 6 条同结论 |
| 5.7 | 变异：`yaml.load(handle, Loader=yaml.Loader)` | `block` / exit 1 | `SEC-006@1 error` | 同批测试通过，证明是规则命中而不是测试失败 |
| 5.8 | 变异：`random.randint(1, 1000)` | `block` / exit 1 | `SEC-011@1 error` | 同批测试通过 |

**证据边界**：5.2/5.3/5.5/5.6/5.7/5.8 是**本次实测**；5.4 引用 dgate2 的同一套规则读数；
其余 ○/— 未在本任务上实测（AGENTS 第 45 条：没测过的不能写成覆盖）。

## 8 与评分器 T/C/A 三维的对接（Lead 决策前）

- **C 维度**：本文件 §2 的 12 条可直接映射成 `dgate2/scorer` 的 8 条规则口径的超集；
  若要复用 C 的 24 分模板，需要显式冻结「本题被测文件集」（建议 = 19 条允许写集合里的 `.py` 文件，
  不含只读的 `order_service.py` / `order_controller.py`）——否则会重演 dgate2 的
  「整树口径把没改过的 `__init__.py` 判成缺测试」的测量假象（dgate2 scorer/README §3）。
- **A 维度**：`layers.yaml` / `interfaces.yaml` 已按 structure_metrics 1.1 的闭集写成；
  30 条路径声明是否 100%、A3 上限是否合适，由参考解跑一遍 `structure_metrics` 后**实测校准**。
- **T 维度**：`hidden/PLAN.md` 的 38 + 5 + 5 = 48 条是**候选**；dgate2 的 T 是 40 分制
  （30+5+5），本题是否沿用 40 分、还是按 48 条重新配权，属评分器扩展决策（见 `bank/README.md` §6）。

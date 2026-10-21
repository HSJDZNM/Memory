# 数据迁移题覆盖矩阵（bank-data-migration）

> **2026-10-21 深夜状态（本覆盖表快照之后）**：本题 hidden/PLAN.md（40 条）与 hidden/runner.py、
> reference/tree/ 与天花板已落盘并实测：T 基线 2/40、参考树 40/40；C effective_total 27/27；A 10/10。
> 本文正文里「hidden 未实现 / 未测 / pending_hidden」的措辞是该批落地前的快照；当前读数以本题
> README 的「天花板读数」节与 reference/README.md 为准。

> **它回答什么**：这道题到底把治理系统的哪些规则点 / 结构谓词 / 隐藏验收真正压到了，哪些只是
> 「规则数据上可触发」而本任务没有岔口，哪些结构性不适用。
> **它不回答什么**：不构成「参考解已通过」的证据——参考解与隐藏用例都还没写（见 §7/§8）。
> 规则点一律从 `policies/**/*.yaml` 读出（43 条；rule id / checker / severity / scope 逐条核对），不编造。
> 期望的 decision 形态来自 `policy.check` 的四种结果：`allow` / `allow_with_warnings` / `block`
> （另有 `evidence_unavailable` 等失败关闭形态，本表不涉及）。

## 0 图例与证据等级

| 符号 | 含义 |
| --- | --- |
| ● | **直接可触发**：任务里存在一个真实的「省事写法/常见错法」，会命中该规则 |
| ○ | **留作变异**：本任务没有这条岔口；在构造树副本上做一处显式缺陷即可命中（判据来自规则数据） |
| — | **结构性不适用**：任务的写面里没有这类代码（SQL / XML / TLS / 网络 / 套接字 / 子进程…） |
| ◐ | **只能靠隐藏验收或结构谓词**：规则表达不了（行为语义、字节形态、文件集合） |

| 证据 | 含义 |
| --- | --- |
| **实测** | 本包在 `.tmp/bank-data-migration/probes/` 的树副本上跑过真 `policy.check`（读数见 §5） |
| **规则数据** | 只由 `policies/<ID>.yaml` 与 `validation/ruff.toml` 的 select 推出，未在本任务上实测 |
| **未测** | 本包没有做任何一种测量；不许读成「查过没问题」 |

## 1 汇总（先读这四行）

| 项 | 数 | 说明 |
| --- | --- | --- |
| 仓库规则点 | **43** 条 / **5** 个 checker | `style_lint` 39、`forbidden_dependency` 1、`missing_docstring` 1、`missing_tests` 1、`failing_tests` 1；error 24 / warning 19 |
| 本题直接可触发 | **10** 条（跨 4 个 checker） | `TESTING-001/002`、`DOC-001`、`STYLE-001/002/004/010/018`、`SEC-006/015` |
| 本题留作变异 | **22** 条 | 一处显式缺陷即可命中；不影响「本任务不压这些面」这一结论 |
| 结构性不适用 | **11** 条 | 任务不写 SQL/XML/TLS/网络/套接字/子进程；不宣称覆盖 |
| 结构谓词（A 维度） | **10** 条 | `tools/structure_metrics.py` 1.1；声明在 `layers.yaml` / `interfaces.yaml` |
| 隐藏验收（行为面） | **≥30 条（规划）** | SPEC §5 的下限；本轮只给规划分组（§7），条数与 id 在隐藏 PLAN 落盘时冻结 |

**怎么读「涵盖程度」**：● 的 10 条是本任务真正压到的判定面；○ 的 22 条说明这些规则在**同一写面上仍然会响**，
但本题不把它们当岔口；— 的 11 条必须写成「本题不覆盖」，不得从 allow 反推成「查过没问题」；
◐ 的行为面没有规则可表达，只能由隐藏验收判定。**43 条里没有任何一条会被静默跳过**：参与判定的规则、
被跳过的规则（含 `skipped_by_reason`）与证据数都随每次 `policy.check` 的 `matched_rules / skipped_rules /
evidence.served_checkers` 落账，`check_volume` 给出 `complete / blocking_capable_skipped / missing_dimensions`
（AGENTS 第 20/49 条）。

## 2 直接可触发（●，10 条规则 + 1 行 pending 通道）

「触发步骤」写的是这道题里模型**最可能真的做出来**的动作；M 编号对应 `milestones.md`。
下表的 `TESTING-002（pending 通道）` 是**同一条规则**的第二种判定形态（AGENTS 第 51 条），不另计规则数。

| 规则 ID | checker | 级别 | 触发步骤（省事/错法） | 期望 decision / severity | 由谁验证 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| TESTING-001 | missing_tests | error | M5/M7 先写 `tools/*.py` 而 `tests/test_<stem>.py` 不在树里；或 M2/M4 写完实现却漏了对应测试 | `block` / `TESTING-001@1 error` | 规则（策略引擎） | 实测（§5.5） |
| TESTING-002 | failing_tests | error | M3 的映射用例写在实现之前、或实现与断言不一致（`assert False` 一类） | `block` / `TESTING-002@1 error` | 规则（策略引擎） | 实测（§5.8） |
| TESTING-002（pending 通道） | failing_tests | warning | M1 只写 `tests/test_ledger_migration.py`、`shop.ledger_migration` 还不存在（**项目内**模块缺失） | `allow_with_warnings` + `pending_findings`（severity 强制 warning；不进 `violations`） | 规则（策略引擎） | 实测（§5.7） |
| DOC-001 | missing_docstring | warning | 纯函数模块 / 公开函数漏 docstring | `allow_with_warnings` / `DOC-001@1 warning` | 规则（策略引擎） | 规则数据（未测） |
| STYLE-001 | style_lint | warning | 迁移行的 JSON 键串 / 日志串超 100 列 | `allow_with_warnings` / `STYLE-001@1 warning` | 规则（策略引擎） | 实测（§5.10） |
| STYLE-002 | style_lint | error | 从别处抄来的 import 没有用到（`import json` / 未使用的 `Path`） | `block` / `STYLE-002@1 error` | 规则（策略引擎） | 实测（§5.11） |
| STYLE-004 | style_lint | warning | 工具脚本先写 `ROOT = ...` 模块级赋值、再 `sys.path.insert`，随后 `from shop... import ...` 忘加 `# noqa: E402` | `allow_with_warnings` / `STYLE-004@1 warning` | 规则（策略引擎） | 实测（§5.4；裸 insert 后 import 不报） |
| STYLE-010 | style_lint | error | 读文件失败时用裸 `except:`（「省事写法」） | `block` / `STYLE-010@1 error` | 规则（策略引擎） | 实测（§5.3） |
| STYLE-018 | style_lint | warning | 本地区块 import 顺序错（标准库排在第三方之后、组间无空行） | `allow_with_warnings` / `STYLE-018@1 warning` | 规则（策略引擎） | 实测（§5.9） |
| SEC-006 | style_lint | error | `load_schema` 用 `yaml.load(handle, Loader=yaml.Loader)`（不是 `safe_load`） | `block` / `SEC-006@1 error` | 规则（策略引擎） | 实测（§5.2） |
| SEC-015 | style_lint | error | 坏行用 `except Exception: pass` 跳过（与「失败关闭」直接冲突） | `block` / `SEC-015@1 error` | 规则（策略引擎） | 规则数据（未测） |

> **跳过不等于通过**：例如 `ARCH-001` 只对 controller 层生效，本题 6 个被测文件里没有 controller
> （`order_controller.py` 冻结不动），于是它**每一次 C 运行都进 `skipped_rules`**（§5 的 12 个探针实测）；
> 这是「这条规则这次没参与」，不是「架构没问题」。每次读数的 `skipped_rules` 与
> `check_volume.blocking_capable_skipped` 必须一起读；C 侧因此把这 3 分标 `not_applicable`（见 §8）。

## 3 留作变异（○，22 条）

这些规则本任务**没有设计岔口**（正常写不会触发），但规则在同一写面上仍然可触发。
「显式缺陷」给的是在构造树副本上做变异即可命中该规则的**测法**；期望形态由 severity 决定：
error → `block`，warning → `allow_with_warnings`。全部未在本任务实测（证据 = 规则数据）。

| 规则 ID | code / checker | 显式缺陷（变异） | 期望 | 证据 |
| --- | --- | --- | --- | --- |
| SEC-011 | S311 / style_lint | 用 `random.randint` 生成 `entry_id`（破坏确定性） | error | 规则数据（未测） |
| DOC-002 | D205 / style_lint | docstring 摘要行后不留空行 | warning | 规则数据（未测） |
| DOC-003 | D200 / style_lint | 单行能放下的 docstring 拆成多行 | warning | 规则数据（未测） |
| DOC-004 | D401 / style_lint | 摘要写成 "Returns ..." 而不是祈使 "Return ..." | warning | 规则数据（未测） |
| STYLE-003 | E401 / style_lint | `import json, sys` | warning | 规则数据（未测） |
| STYLE-005 | F403/F405 / style_lint | `from shop.ledger_migration import *` | error | 规则数据（未测） |
| STYLE-006 | E711 / style_lint | `if value == None` | error | 规则数据（未测） |
| STYLE-007 | E712 / style_lint | `if flag == True` | error | 规则数据（未测） |
| STYLE-008 | E713/E714 / style_lint | `if not key in row` | warning | 规则数据（未测） |
| STYLE-009 | E721 / style_lint | `if type(row) == dict` | error | 规则数据（未测） |
| STYLE-011 | E731 / style_lint | `mapper = lambda row: row` | warning | 规则数据（未测） |
| STYLE-012 | E741 / style_lint | 变量名 `l` / `I` / `O` | warning | 规则数据（未测） |
| STYLE-014 | N801 / style_lint | `class ledger_migration:` | warning | 规则数据（未测） |
| STYLE-015 | N802 / style_lint | `def MigrateRows(...):` | warning | 规则数据（未测） |
| STYLE-016 | N803 / style_lint | `def migrate(EntryId):` | warning | 规则数据（未测） |
| STYLE-017 | N806/N815/N816 / style_lint | 函数内局部变量 `MaxFee` | warning | 规则数据（未测） |
| SEC-001 | S102/S307 / style_lint | `eval(line)` 解析 v1 行 | error | 规则数据（未测） |
| SEC-002 | S301/S302 / style_lint | `pickle.loads(blob)` 读迁移输入 | error | 规则数据（未测） |
| SEC-003 | S303/S324 / style_lint | 用 `hashlib.md5` 生成记录指纹 | error | 规则数据（未测） |
| SEC-004 | S105/S106/S107 / style_lint | 把 token 写进读取 schema 的代码常量 | error | 规则数据（未测） |
| SEC-017 | LOG015 / style_lint | 直接调 `logging.info(...)`（根 logger） | warning | 规则数据（未测） |
| SEC-018 | TRY400 / style_lint | `logger.error(str(exc))` 而不是 `logger.exception(...)` | warning | 规则数据（未测） |

## 4 结构性不适用（—，11 条）

**判据**：这道题的写面里不出现对应构造；模型若**主动**写这类代码，规则照样会响，
但那已经不在本题声明的覆盖范围内（不许写成「本题覆盖了」）。

| 规则 ID | code | 为什么本题不适用 |
| --- | --- | --- |
| ARCH-001 | forbidden_dependency | 本题不碰 controller 层（`order_controller.py` 是冻结文件），6 个被测文件里没有 controller |
| SEC-005 | S323/S501 | 不写 HTTP/TLS 客户端；迁移是本地文件到本地文件 |
| SEC-007 | S602/S605/S609 | 不起子进程、不调 shell；原子替换用 `os.replace` 而不是 `cp`/`move` |
| SEC-008 | S608 | 数据层是 JSONL 文件，不是 SQL；不拼 SQL 字符串 |
| SEC-009 | S313–S318 | 不解析 XML |
| SEC-010 | S310 | 不打开 URL；任务禁止网络 |
| SEC-012 | S308/S611/S701 | 不用模板引擎 / `mark_safe` |
| SEC-014 | S113 | 不发起外部请求；没有 timeout 参数可漏 |
| SEC-019 | S104 | 不起服务、不绑定 0.0.0.0 |
| SEC-021 | S312/S321 | 不建 socket、不用明文协议 |
| SEC-022 | S612 | 不配置远端日志监听 |

## 5 本次实测读数（12 个 `policy.check` 探针）

命令骨架（逐案例一次，`--request-id` 固定；`--config-root` 指向仓库根，`--workspace` 指向树副本；
`PYTHONPATH=src`；解释器 = 仓库 `.venv`）：

```text
python -m policy.check <文件> --workspace .tmp/bank-data-migration/<副本> --config-root . --layer <层> \
  --operation edit --request-id probe-dm-<tag> --changed <该文件> [--changed ...] --json
```

| # | 案例（树 / 变异） | 判定 | violations | skipped / pending | served_checkers |
| --- | --- | --- | --- | --- | --- |
| 5.1a | 基线树 `src/shop/order_controller.py`，**不带** `--changed`（本包要求的命令形态） | `block` / exit 1 | `TESTING-001@1 critical`、`TESTING-002@1 critical`（缺变更集 = 证据不足） | skipped 0 / pending 0 | `forbidden_dependency`、`missing_docstring`、`style_lint` |
| 5.1b | 同上 + `--changed src/shop/order_controller.py` | `allow` / exit 0 | 无 | skipped 0 / pending 0 | 5 个 checker 全部服务过 |
| 5.2 | 变异：`load_schema` 用 `yaml.load(handle, Loader=yaml.Loader)` | `block` / exit 1 | `SEC-006@1 error` | skipped `ARCH-001@1` / pending 0 | 4 个（含 failing_tests、missing_tests） |
| 5.3 | 变异：读文件失败用裸 `except:` | `block` / exit 1 | `STYLE-010@1 error` | skipped `ARCH-001@1` / pending 0 | 同上 |
| 5.4 | 变异：工具脚本 `sys.path.insert` 后的 import 去掉 `# noqa: E402` | `allow_with_warnings` / exit 1 | `STYLE-004@1 warning` | skipped `ARCH-001@1` / pending 0 | 同上 |
| 5.5 | 变异：树里有 `tools/migrate_ledger.py`，但没有 `tests/test_migrate_ledger.py` | `block` / exit 1 | `TESTING-001@1 error` | skipped `ARCH-001@1` / pending 0 | 同上 |
| 5.6 | 变异：基线树 + 一个**模块级** `from tools.migrate_ledger import main` 的测试（`tools/` 还不存在） | `block` / exit 1 | `TESTING-002@1 error`（收集失败，**不是**「待实现」） | skipped `ARCH-001@1` / pending 0 | 同上 |
| 5.7 | 变异：基线树 + 只 import `shop.ledger_migration` 的测试（该模块还不存在） | `allow_with_warnings` / exit 1 | 无 | skipped `ARCH-001@1` / **pending 1**（`pending_findings`） | `missing_docstring`、`missing_tests`、`style_lint`（`failing_tests` 没服务过） |
| 5.8 | 变异：`tests/test_ledger_migration.py` 断言失败（模拟映射写错） | `block` / exit 1 | `TESTING-002@1 error` | skipped `ARCH-001@1` / pending 0 | 4 个 |
| 5.9 | 变异：模型模块的 import 顺序错（`import yaml` 在 `from pathlib import Path` 之前） | `allow_with_warnings` / exit 1 | `STYLE-018@1 warning` | skipped `ARCH-001@1` / pending 0 | 同上 |
| 5.10 | 变异：模块 docstring 一行超 100 列 | `allow_with_warnings` / exit 1 | `STYLE-001@1 warning` | skipped `ARCH-001@1` / pending 0 | 同上 |
| 5.11 | 变异：模型模块多一个未使用的 `import json` | `block` / exit 1 | `STYLE-002@1 error` | skipped `ARCH-001@1` / pending 0 | 同上 |

**证据边界**：5.1a/5.1b/5.2–5.11 都是**本次实测**（树副本在 `.tmp/bank-data-migration/probes/`，
探针驱动是临时件、不进包）。`DOC-001` 与 `SEC-015` **没有实测**（证据只到规则数据）；§3 的 22 条全部未测。
5.6 是「测试先写、模块级 import `tools.*`」的实测读数：它是**真违规**（block），不是「待实现」——
因为基线没有 `tools/__init__.py`，`tools` 不在模块索引的顶层包里（这就是 M5/M7 先写骨架测试的原因）。

## 6 A 维度结构谓词（10 条；由 `tools/structure_metrics.py` 判）

| 谓词 | 阈值 | 本题的合法形态 | 违规岔口（变异测法） |
| --- | --- | --- | --- |
| A1 分层方向 | 违规边 0 | 两个 tools 脚本（composition）→ `shop.ledger_migration`（model）；测试（test）→任意；model 模块不 import 任何项目内模块 | 让 `src/shop/ledger_migration.py` 反向 import `tools.migrate_ledger`（model → composition，禁止方向） |
| A2 依赖无环 | 0 环 | 单向：composition → model；test → composition/model | 让两个 tools 脚本互相 import |
| A3 公开符号最小面 | 每模块 ≤ 声明上限 | 见 `interfaces.yaml`：`ledger_migration` 4 个公开函数（上限 6）、两个 tools 各 1 个 `main`（上限 2） | 往 `ledger_migration` 里塞第 7 个公开符号（或把私有辅助函数改成公开名） |
| A4 组合根唯一 | 违规 0 | 只有两个 tools 脚本（composition）做装配；model 模块没有跨模块 `new` 具象协作者 | 在 `migrate_rows` 里 new 一个具象协作者 |
| A5 函数复杂度 | ≤ 10 | 每个函数分支少（校验拆成小函数） | 把 schema 校验 + 行校验 + 排序写成一个 15 支 `if/elif` |
| A6 文件/函数长度 | 文件 ≤ 200 行；函数 ≤ 50 行 | 每模块一个职责 | 把迁移与校验都塞进一个 80 行 `main` |
| A7 docstring 覆盖 | 缺失 0 | 模块 + 公开定义都有 docstring（首消息的代码约定） | 删类/模块 docstring（同时命中 DOC-001 warning） |
| A8 依赖扇出 | 出/入 ≤ 5 | `ledger_migration` 出边 0；两个 tools 各 1 条出边 | 让 `ledger_migration` import 所有 tools |
| A9 测试对应完备 | 100% | 每个生产文件（含两个 tools）都有测试层静态 import | 新建 `tools/*.py` 但不写同名测试（同时命中 TESTING-001） |
| A10 无动态执行 | 违规 0 | 静态 import | `importlib.import_module("shop.ledger_migration")` 或通配 import |

**本轮实测**：在 `.tmp/bank-data-migration/scratch`（13 文件基线 + 8 个任务文件的**最小骨架**，不是参考解）上跑
`tools/structure_metrics.py` → exit 0、**A1–A10 全 pass**、`declared_unmatched` 为空、14 个 .py 全部命中声明。
**未测**：参考解上的 A 读数与 A3 上限的「可达」校准（参考解未做，见 §8）。

## 7 只能靠隐藏验收（◐，规划 ≥30 条；条数与 id 未冻结）

| 面 | 规划分组（条数为建议；隐藏 PLAN 落盘时冻结 id 与 total） | 为什么规则做不到 |
| --- | --- | --- |
| schema 严格性 | `load_schema` 对合法带注释 YAML 的读入；坏 YAML / 缺键 / 多键 / `key_order` 与 `fields` 不一致 / `sort_by` 不在 `key_order` / 非法 `type` 各抛 `ValueError`；文件字节不变（6–8 条） | 规则只查 docstring/lint/依赖，不查 YAML 语义与 `ValueError` |
| v1 读取与坏行 | 4 行按文件顺序读入；非法 JSON / 非对象 / 空行 / 缺键 / 多键 / `bool` 冒充 int 各抛 `ValueError`；不写文件（6–8 条） | 同上：这是行为契约，不是静态形态 |
| 映射 / 排序 / 无损 | 6 键且键序 = `key_order`；`status="migrated"`；`entry_id` 升序；`cents=0` 保留；重复 `id` / 负值 / 缺 `why` 抛错；返回记录与入参不共享（6–8 条） | 字段集合、数值与排序都是行为 |
| 原子写与幂等 | 目标已存在时被替换；失败不替换且不留临时文件；两次写字节相同；末尾恰一个换行、无 CR（5–6 条） | 原子性与字节形态规则表达不了 |
| 迁移 CLI | 成功 `MIGRATED 4` + exit 0 + 输入 sha256 不变；坏输入/坏 schema → exit 1、`MIGRATE FAILED:`、out 哨兵字节不变、无 `.tmp` 残留；连跑两次字节相同（5–6 条） | 退出码、stderr 文案与副作用都是行为 |
| 校验 CLI | 合法输出 `VERIFIED 4` + exit 0；缺键 / 键序错 / 记录乱序 / 错 `schema_version` / 负值 / CRLF / 末尾多空行 → exit 1；不改被校验文件（5–6 条） | 同上 |
| 文档 / README | `docs/migration.md` 5 个二级标题 + 映射表（v1 4 键、v2 6 键）+ 回滚句；`README.md` 结构表 3 行 + 迁移命令行 + 链接（4 条） | 文字内容不在 43 条规则里 |
| 树形状 | 改动集合 ⊆ 9 条允许写；12 个冻结文件逐字节不变；树内文件集 ⊆ 21；`data/ledger-v2.jsonl` 存在且非空（4 条） | 文件集合与字节相等只能靠树 diff |

**未冻结**：上表的条数只是规划（按组下限求和 = 41、按上限 = 50，都落在 SPEC §5 的「≥30、建议 36」之上）；`scoring.yaml` 的
`dimension_t.status = pending_hidden`、`total = null`、`case_ids = []`、`planned_min_total = 30`——
隐藏代码落盘后再冻结 total 与 case_ids，此刻任何 T 读数都不是读数。

## 8 与评分器 T/C/A 的对接（读之前先看这三条）

- **C**：8 条规则的口径与 dgate2 / 旗舰题同一组；本题的 `file_set` = 6 个允许写里的 `.py`，`frozen_untouched` = 12 个
  基线文件。**`ARCH-001` 在本题恒进 `skipped_rules`**（§5 的 12 个探针实测）——`scoring.yaml` 已把
  这 3 分标 `not_applicable`（不计分也不计分母），**C 上限 27**（`effective_total`）；跳过 ≠ 通过，
  读 C 必须带 `effective_total`。10 个直接点里另外 3 条（`STYLE-004` / `SEC-006` / `SEC-015`）只进
  过程读数、不重复计分。
- **A**：`layers.yaml`（21 文件）/ `interfaces.yaml`（7 模块）已按 structure_metrics 1.1 的闭集写成，
  可加载性与 A1–A10 一致性已在**构造树**上实测（§6）；参考解没写，所以「可达上限」仍未测。
- **T**：`hidden/PLAN.md` 还不存在（下一批任务）。`planned_min_total = 30`，`total` / `case_ids` / `reverse_cases`
  都待冻结——在那之前 T 只能记「跑不成」，不记 0 分。

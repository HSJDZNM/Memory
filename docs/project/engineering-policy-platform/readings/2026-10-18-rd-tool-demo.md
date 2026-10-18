# 2026-10-18 R-d 差集工具演示读数（阶段 1）

> 读数对象：git HEAD `c4eaa53` 的工作树（工具、用例与本次登记同批，尚未提交；命令都在工作树根执行，
> 解释器是仓库 `.venv/Scripts/python.exe`，`python` 亦可）。
> 本文件是 06 的记录落点（06 第 4 节：读数文件不得指向 `.tmp`）；探针脚本不进仓库（临时产物只落 `.tmp/`、
> 用完即删），结论与命令以本文件为准。

## 1 这份读数回答什么

05 §3.5 的 R-d：**任何改变 decision 的步骤都必须交出字段级差集，含 violations 内容，不只 decision 值**；
且差集工具必须**入库**（不能只留在 `.tmp`）。本次交付 `tools/decision_diff.py`（阶段 1：只比两份**已存在**的载荷），
本读数用 `tests/fixtures/decisions/` 的四份协议快照把它**真跑一遍**，回答两件事：

1. 四种 decision 形态两两之间的字段级差集**长什么样**（计数 + 样例，含 violations 内容）；
2. 差集工具的退出码语义在本仓库里**可执行**：同文件自比 0、有差异 1、输入坏了 2。

## 2 命令

```
python tools/decision_diff.py --base tests/fixtures/decisions/allow.json   --head tests/fixtures/decisions/warning.json
python tools/decision_diff.py --base tests/fixtures/decisions/warning.json --head tests/fixtures/decisions/block.json
python tools/decision_diff.py --base tests/fixtures/decisions/block.json   --head tests/fixtures/decisions/approval.json
python tools/decision_diff.py --base tests/fixtures/decisions/allow.json   --head tests/fixtures/decisions/allow.json
```

机器可读形态加 `--json`（自带版本轴 `DECISION_DIFF_SCHEMA_VERSION = "1.0"`），
贴报告加 `--md`，落盘加 `--out PATH`。

## 3 四组比对（读数）

| 比对 | 退出码 | added | modified | removed | total | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| allow → warning | 1 | 1 | 1 | 0 | 2 | decision 变值 + 新增一条 warning 级 violation |
| warning → block | 1 | 1 | 1 | 1 | 3 | 新 violation（ARCH-001）顶上、旧 violation（CODING-002）消失，**键不同 ⇒ 一条 added + 一条 removed**，不是"同一条被改" |
| block → approval | 1 | 1 | 2 | 2 | 5 | `required_action: null → "approval"`；matched_rules 中间插一条只算 1 条 added（不级联）；skipped_rules 两条各自按键配对 |
| allow → allow（自比） | **0** | 0 | 0 | 0 | 0 | 相同输入 ⇒ 逐字节相同的"无差异" |
| `tests/fixtures/decisions/` 目录自比 | **0** | 0 | 0 | 0 | 0 | 目录模式：按文件名配成 4 对，每对 0（`--base` / `--head` 同名目录） |

四组都**没有**"数组整体 modified"这种读数：数组先按键配对（`rule_id` 等），
配不上才按序列对齐——这是 05 §3.5 要的"字段级"，不是"整份换了"。

## 4 样例（从 `--md` 输出里摘）

block → approval 的短行（长 payload 用 `…` 省略）：

| 列 | 指针 | 前值 | 后值 |
| --- | --- | --- | --- |
| added | `matched_rules[1]` | （无） | `"ARCH-004@1"` |
| modified | `required_action` | `null` | `"approval"` |
| modified | `skipped_rules[rule_id=SEC-003@1].reasons[0]` | `"operation <missing> != execute"` | `"operation delete != execute"` |

allow → warning 的人类摘要（两条都带 violations 内容）：

```
R-d 字段级差集（差集工具：0=无差异 / 1=有差异 / 2=输入或用法错误）
  base: tests/fixtures/decisions/allow.json
  head: tests/fixtures/decisions/warning.json
  schema_version: 1.0
  合计: added=1 modified=1 removed=0 total=2（有差异）
  [modified] decision: "allow" -> "allow_with_warnings"
  [added] violations[rule_id=CODING-002]: {"evidence": {…}, "message": "Controller 必须通过 Service 访问 Repository。", "rule_id": "CODING-002", "rule_version": 1, "severity": "warning"}
  DECISION_DIFF: added=1 modified=1 removed=0 total=2 identical=false
```

同文件自比只有计数，没有条目：

```
R-d 字段级差集（差集工具：0=无差异 / 1=有差异 / 2=输入或用法错误）
  base: tests/fixtures/decisions/allow.json
  head: tests/fixtures/decisions/allow.json
  schema_version: 1.0
  合计: added=0 modified=0 removed=0 total=0（无差异）
  DECISION_DIFF: added=0 modified=0 removed=0 total=0 identical=true
```

## 5 工具口径（为什么这样比）

- **指针**：对象字段写点号（`decision`、`selected_checks.status`），数组元素写索引（`matched_rules[2]`）
  或身份（`violations[rule_id=ARCH-001@1].severity`）；整份载荷（目录模式下某一侧缺这份文件）写 `.`。
- **数组匹配**：先按可识别键（`rule_id` / `check_id` / `tool_id` / `channel` / `key` /
  `id` / `name` / `path`，同一侧内部唯一才用），否则按序列对齐（`difflib`，`autojunk=False`）：
  中间插一条只算 1 条 added，不会把后面全部报成 modified（上面 block → approval 那行就是这条的实测）。
- **脱敏**：只调用仓库既有两份实现（`provenance.reading_context.fold_absolute_paths` +
  `enforcement.audit.redact_text`）。绝对路径折叠成仓库相对路径或 `<outside-workspace>`，
  密钥写 `<redacted-secret>`；本读数的 `--json` / `--md` / 人类输出里不含绝对路径。
  这条边界由 `tests/unit/test_decision_diff.py` 的注入用例钉住（合成凭据按片段拼装，免得被凭据门禁按形态拦下）。
- **逐字节相同**：载荷里没有时戳、没有 run 标识，`--json` 两次运行相等（与
  `policy.check.OUTPUT_SCHEMA_VERSION` 1.2 的"包装层不带 run"同一条纪律；有用例钉住）。
- **退出码**：0 = 无差异 / 1 = 有差异 / 2 = 输入或用法错误（与 `tools/README.md` 的「门禁退出码」表一致）。
  本工具**不是恒 0 的只报告读数**：差集非空是结论，就是 1；输入坏了退 2（带一句可读 reason、不打 traceback），
  不会把"没比成"写成"没差异"。

## 6 阶段边界：阶段 1 只比两份载荷

**阶段 1 不跑双代码版本，只比两份载荷**：本读数里的两份输入都是 `tests/fixtures/decisions/` 下**已经存在**的
协议快照，工具不启动判定引擎、不采集任何运行时产物、不碰 `.tmp`。
"同一份夹具在改动前 / 改动后的代码上各跑一遍、再比两份载荷"是阶段 2 的事；双版本采集的命令在阶段 2 落地时
按同一张表补进 `tools/README.md`——本阶段**不**把未实现的命令写进文档（"文档里有、代码里没有"比没有更难发现）。

## 7 阶段 2（git worktree 双版本采集器）只写为下一步，不实现

下一步（**未实现、未验证**）：用 `git worktree add` 把"改动前"与"改动后"两个提交各 checkout 到独立目录，
在各自目录里跑同一条采集命令（把判定产物写成 JSON 载荷），再用本工具比两份输出；采集器要给出两棵树的
`git rev-parse HEAD` 与载荷摘要，否则"这两份是哪两个版本的读数"不可复核。它的入口、参数与退出码要按
`tools/README.md` 的登记方式新增一行，并按 AGENTS 第 55 条为它的载荷建轴；本阶段一行都不写。

## 8 本次交付的验证与不可复现边界

| 项 | 命令 | 读数 |
| --- | --- | --- |
| 用例 | `.venv/Scripts/python.exe -m pytest -q -n0 tests/unit/test_decision_diff.py`（`-n0` 需要 xdist，只有仓库 `.venv` 装了） | 14 passed |
| 四组比对 | 见 §2 | 退出码 1 / 1 / 1 / 0；计数见 §3 |
| 风格 | `ruff check --config validation/ruff.toml tools/decision_diff.py tests/unit/test_decision_diff.py` | All checks passed |
| 文本规范 | `python tools/check_text_conventions.py` | 检查 688 个文本文件，问题 0 处 |
| 仓库一致性 | `python tools/check_repo_consistency.py` | 依赖锁 / 文档与配置 / 手册形态 / 工具清单 四类一致（工具清单含本工具那行登记） |

不可复现边界：四份快照是**仓库内固定夹具**，读数可随时重跑；本文件只记结论与命令，未把
`--json` 全文贴进来（全量在重跑时拿到）。本读数不声称任何 allow / block 变化——阶段 1 的工具不参与判定路径。

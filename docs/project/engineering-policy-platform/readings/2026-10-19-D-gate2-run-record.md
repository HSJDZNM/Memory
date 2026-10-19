# 2026-10-19 D 门 2 run-record 采集器：参考树样例读数

> 用途：`testing/ab/dgate2/run-record/collect.py` 的**真实样例读数**与
> 与 `scorer/README.md` 第 10 节已知读数的对照。参考树副本在 `.tmp/dgate2-w3/ref`
> （16 文件，与 `.tmp/lead-v3/ref` 逐字节一致），样例载荷在
> `.tmp/dgate2-w3/sample-run-record.json`（临时产物，不提交；内容可用下面命令复现）。
> 判据原文：`readings/2026-10-19-D-gate2-treatment.md` §4；机读规格：`testing/ab/dgate2/scorer/scorer.yaml`。

## 1 结论摘要

| 项 | 读数 | 退出码 |
| --- | --- | --- |
| collect.py 全量（T + C + A） | 三维全部 `recorded`；wall clock **30.8 s** | **0** |
| T（`hidden/runner.py`） | `summary {passed: 40, total: 40}`，0 条失败 | **0** |
| C（8 个改动 .py × `policy.check`） | 8/8 `decision=allow`、0 violation、`layer_source=declared`、`check_volume.complete=true`；rules **24/24** | 每条 **0** |
| A（`tools/structure_metrics.py`） | `summary {passed: 10, failed: 0}`；A3 `basis=declared_caps` | **0** |

run-record 载荷：`schema_version=1.0`、`arm=A`、`tree=.tmp/dgate2-w3/ref`；
sha256 = `40f55c46bb4c913444ea9cc7ec637744f5a29e52d53eced7a47f2bd49e35b857`，19,682 B。
**同一命令三次运行逐字节相同**（其中两次分别写到 `sample-run-record.json` 与
`sample-run-record-2.json`，字节比对 0 处差异；三次的 sha256 都是 `40f55c46…`）。

## 2 命令与退出码

在仓库根执行（PowerShell；`PYTHONPATH` 垫片的原因见 §6）：

```powershell
$env:PYTHONPATH = '<repo>/.tmp/dgate2-w3/pyshim'   # 仅本会话的宿主垫片，见 §6
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/dgate2/run-record/collect.py `
  --tree .tmp/dgate2-w3/ref `
  --config-root docs/project/engineering-policy-platform/testing/ab/dgate2/configs/after `
  --layers docs/project/engineering-policy-platform/testing/ab/dgate2/scorer/layers.yaml `
  --interfaces docs/project/engineering-policy-platform/testing/ab/dgate2/scorer/interfaces.yaml `
  --arm A --out .tmp/dgate2-w3/sample-run-record.json
# exit 0；stdout: collect: T=40/40 C=24/24（规则分） A=10/10；run-record 已写出
```

其它证据命令与退出码：

| 命令 | 退出码 | 读数 |
| --- | --- | --- |
| collect.py `--dry-run`（同一组输入） | 0 | 打印 10 条计划命令（T + A + 8×C），**不执行、不写 out** |
| `.venv/Scripts/python.exe -m pytest -q tests/unit/test_dgate2_run_record.py`（带垫片） | 0 | **10 passed**（0.81 s） |
| `ruff check --config validation/ruff.toml`（collect.py + 测试） | 0 | All checks passed（ruff 0.14.13） |
| 参考树副本对照脚本（16 文件逐个 sha256，与 `.tmp/lead-v3/ref` 比） | 0 | 16/16 一致，无多余文件 |
| `.venv/Scripts/python.exe …/scorer/make_manifest.py --check --strict` | 0 | `RESULT: PASS（25 个文件逐字节一致，0 条 pending）`——冻结输入没被改 |

`collect.py` 计划执行的 10 条子进程命令（记录在样例载荷的 `commands[]` 里）：

| id | 退出码 | 说明 |
| --- | --- | --- |
| `T` | 0 | runner，`POLICY_TREE=.tmp/dgate2-w3/ref`、`DGATE2_TMPDIR=.tmp/dgate2-w3/dgate2-tmp` |
| `A` | 0 | `structure_metrics --workspace … --layers … --interfaces … --json` |
| `C:src/shop/order_audit.py` | 0 | `--layer model`，`--request-id dgate2-A-src-shop-order-audit-py` |
| `C:src/shop/order_controller.py` | 0 | `--layer controller` |
| `C:src/shop/order_service.py` | 0 | `--layer service` |
| `C:tests/test_audit_demo.py` | 0 | `--layer test` |
| `C:tests/test_order_audit.py` | 0 | `--layer test` |
| `C:tests/test_order_controller.py` | 0 | `--layer test` |
| `C:tests/test_order_service.py` | 0 | `--layer test` |
| `C:tools/audit_demo.py` | 0 | `--layer composition` |

每条 C 命令都带冻结的 9 条 `--changed`（`README.md` + 8 个 .py，逐条一次）与固定的 request id；
8 条载荷的 `rule_set_hash` 全为 `sha256:73845ef515236940266b682631c02dec84c06886fa27a1e99f57e66284fae7d4`。

## 3 C 的逐文件读数（样例载荷摘要）

| 文件 | layer | decision | exit | matched | skipped | violations | served_checkers | check_volume.complete |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `src/shop/order_audit.py` | model | allow | 0 | 42 | 1（ARCH-001：layer model != controller） | 0 | failing_tests, missing_docstring, missing_tests, style_lint | true |
| `src/shop/order_controller.py` | controller | allow | 0 | 43 | 0 | 0 | failing_tests, forbidden_dependency, missing_docstring, missing_tests, style_lint | true |
| `src/shop/order_service.py` | service | allow | 0 | 42 | 1 | 0 | 同 order_audit | true |
| `tests/test_audit_demo.py` | test | allow | 0 | 42 | 1 | 0 | 同 order_audit | true |
| `tests/test_order_audit.py` | test | allow | 0 | 42 | 1 | 0 | 同 order_audit | true |
| `tests/test_order_controller.py` | test | allow | 0 | 42 | 1 | 0 | 同 order_audit | true |
| `tests/test_order_service.py` | test | allow | 0 | 42 | 1 | 0 | 同 order_audit | true |
| `tools/audit_demo.py` | composition | allow | 0 | 42 | 1 | 0 | 同 order_audit | true |

除 controller 外的 7 个文件，`skipped_rule_ids` 都只有 `ARCH-001@1`（层不是 controller
→ scope 不匹配）；controller 文件 skipped 为 0，故 `matched=43`。

8 条规则的计分（`scorer.yaml rules.scoring`）：8 × 3 = **24/24**，`not_measured=[]`。
C 的 `payloads` 聚合：`output_schema_versions=["1.2"]`、`decisions={"allow":8}`、
`served_checkers` 并集 = `["failing_tests","forbidden_dependency","missing_docstring","missing_tests","style_lint"]`。

## 4 与 `scorer/README.md` 第 10 节的对照

§10 的三条冒烟读数（在 `.tmp/lead-v3/ref` 上）：

| 维度 | §10 已知读数 | 本次（`.tmp/dgate2-w3/ref`） | 结论 |
| --- | --- | --- | --- |
| A | exit 0；`summary {passed:10, failed:0}`；A3 `declared_caps`：7 模块 / 15 公开定义 / 0 违规 | exit 0；10/10；`a3_basis=declared_caps`，points 30 | **一致** |
| C | 8/8 exit 0、allow、0 violation、`declared`、`complete`；rules 24/24 | 8/8 exit 0、allow、0 violation、`declared`、`complete`；24/24 | **一致** |
| T | exit 0；`summary {passed:40, total:40}` | exit 0；40/40 | **一致** |

**差异**：无。两棵树的 16 个文件逐字节相同（16/16，§5），所以读数可直接对照。
§10 的「C 反例口径（13 个 .py → 21/24）」是**另一条测量口径**的读数，本次按冻结的 8 文件口径
采集，没有重跑 13 文件口径——本样例不构成对它的复核，也不与它矛盾。

## 5 确定性与只读

- 三次全量运行（28.5–30.8 s）写出的载荷 **19,682 B，sha256 全部相同**（`40f55c46…`）；
- 载荷没有时戳 / 耗时 / run id；request id 固定；树标签是仓库相对路径 `.tmp/dgate2-w3/ref`；
- 跑后清点参考树副本：16 个源文件逐个 sha256 与 `.tmp/lead-v3/ref` **16/16 一致**，
  副本里**没有新增文件**（T 的副本用完即删；C/A 只读；`policy.check` 的验证器临时目录在仓库
  `.tmp/validators/` 下，不在受评树里）；
- `policy.check` 会在 config-root 下留一个**空**的 `.tmp/validators/`（构建产物，
  `make_manifest.py` 跳过 `.tmp`；scorer/README §3 的注记同口径）。本次跑完已删除，
  冻结配置的字节没有变化；正式 run 结束后同样应删掉这个空目录再复核清单。

## 6 环境说明（重要，不要把下面的读数当成解法读数）

本会话是 **`workspace-write` 沙箱（enforcement: partial）**。该沙箱把 `mode=0o700` 的新目录
变成当前令牌无权的 ACL，而 `tempfile.mkdtemp` 在 Windows 上正是用 `0o700` 建目录：

- 不带垫片跑 T：`POLICY_TREE=.tmp/dgate2-w3/ref runner.py --json` → **退出码 1、30/40**；
  失败的 10 条是 T22/T23/T25/T26/T27 与 EN1–EN5，`detail` 全是
  `PermissionError: [WinError 5] …\acceptance-<id>\tree`（runner 在 `copytree` 建副本时被拒）。
  这是**宿主沙箱**造成的，不是参考树的 T 读数；
- 不带垫片跑 pytest：`.venv python -m pytest` 在 tmp_path/basetemp 建 `0o700` 目录时
  `PermissionError: …\.lock`，一条用例都起不来；
- 本会话用的垫片只有两件事：`tempfile.mkdtemp` 改成 `os.mkdir(path, 0o755)`（T 用），
  以及验证 pytest 时把 `os.mkdir` 的 `0o700` 降为默认权限；**不改任何被测代码、不改 runner、
  不改测试断言**，只改新目录的权限位；
- 因此 §1 的 T=40/40 是「垫片下 runner 真跑出来的」读数，与 §10 的已知读数一致；
  **正式 A/B/C 读数应在 `danger-full-access` 会话里重跑**（不加载垫片），由 Lead 的门禁统一执行。
  C 与 A 不需要垫片（C 的子进程 `PYTHONPATH=src` 覆盖了垫片；A 不建临时目录）。

## 7 边界（引用本读数前必须读）

- **C 只量改动面的 8 个 .py**（整树 13 个会因未改的 `__init__.py` 产生 TESTING-001 假违反，
  rules 21/24）；理由与实测见 `scorer/README.md` §3；
- **C 的 24 分只是规则分**：`frozen_untouched` 3 分与 `bypass` 3 分不在本工具（需要树 diff / AST），
  别把 `score.points=24` 读成 C=30；
- **A 的「有保留 1 分」档没有数据源**（04 的 5.79①；`structure_metrics` 1.1 只有 pass/fail），
  本读数按二分记 3/0；
- **runner 的 11 条规格含糊**见 `../hidden/README.md` 第 6 节（04 的 5.79④）：
  M6（README 结构表加行）无隐藏条目、A8 不抓点目录里的额外文件、A5 的两条拆法不同、
  T 只依赖最终树、不能核对里程碑顺序；引用 T 读数时不得越过；
- **样例树是参考树副本**（`.tmp/dgate2-w3/ref`），不是任何受评臂；正式读数必须换臂树重跑。

## 8 交付文件与登记建议

交付：`dgate2/run-record/collect.py`、`dgate2/run-record/README.md`、
`tests/unit/test_dgate2_run_record.py`、本文件。**未改 AGENTS.md**。

建议 Lead 在 AGENTS 第 55 条的 D 门 2 评测件行补一句：

> `dgate2/run-record/collect.py` 的 `RUN_RECORD_SCHEMA_VERSION = "1.0"`（T / C / A 三维读数载荷；
> 1.0 = 首次建轴；加键或改语义必须递增，并同批改 README 与用例）。

## 9 未核实项 / 风险

- **gate 的 pytest 没能在本会话直接跑**（沙箱 tmp 目录 ACL，见 §6）：10 条用例是用
  `0o700 → 默认权限` 的 pytest 垫片验证的（10 passed）。正式门禁应在 danger-full-access 下重跑一次；
- **T 的无垫片读数**只证明了「这个沙箱里跑不成」（exit 1 / 30/40 / WinError 5），
  没有证明 runner 在 unrestricted 环境下的 40/40——后者沿用 §10 的已知读数，本次未独立复核；
- **C 的 `layer_source=declared` 依赖调用方传的 layers.yaml**；本工具缺层直接退出 2，
  不会退回 filename guess；
- **`scorer.yaml measurement.reading_keys` 的文本是 C 的校验输入**：键名写法一变，
  读数路径推导就可能空解（退出 2），改它必须与 scorer 的版本轴同批处理；
- **样例行没有 0o700 之外的宿主变量**：本次没有改任何冻结输入（runner / scorer / configs / 工具），
  参考树与冻结包只读。

## 10 Lead 复核（danger-full-access，无垫片）

> 2026-10-19 运行时沙箱切到 `danger-full-access` 后，Lead 用**同一份参考树副本**重跑 §2 的命令，
> 不加载任何垫片（`.tmp/lead-check/ref` 由 `.tmp/dgate2-w2/ref` 逐字节复制）：

| 命令 | 退出码 | 读数 |
| --- | --- | --- |
| `collect.py --tree .tmp/lead-check/ref --config-root …/configs/after --layers …/scorer/layers.yaml --interfaces …/scorer/interfaces.yaml --arm A --out .tmp/lead-check/run-record-A.json` | **0** | stdout `collect: T=40/40 C=24/24（规则分） A=10/10；run-record 已写出` |
| `POLICY_TREE=.tmp/lead-check/ref`、`DGATE2_TMPDIR=.tmp/lead-check/tmp` 下 `runner.py --json` | **0** | `summary {passed: 40, total: 40}`、`fails []`、`schema_version "1.0"` |

对照：新载荷的 `arm` / `schema_version` / `summary` / `dimensions` / `commands` 与 §1 样例**逐项相等**
（唯一差异是 `tree` 标签：`.tmp/lead-check/ref` 对 `.tmp/dgate2-w3/ref`）。因此 §6 的
「T 在受限沙箱下 30/40」是**旧沙箱形态**的宿主事实，不是工具或参考树的缺陷；§9 的
「正式读数应在 danger-full-access 重跑」一条已由本复核满足。**写进 run-manifest 的口径不变**：
launcher 与 session 两种沙箱形态都要记（04 5.81 ①/②）。

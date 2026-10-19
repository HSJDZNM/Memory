# D 门 2 三维读数采集器（run-record）

**它是什么**：一次采集把 D 门 2 的 **T / C / A 三维读数**落成确定性的 run-record JSON，
供 run-manifest 的 `readings` 字段消费。三个维度都走已有的冻结工具，本目录**不复制判定逻辑**：

| 维度 | 工具 | 读数 |
| --- | --- | --- |
| T | `../hidden/runner.py --json` | `summary.passed / total`、逐 case 的 pass、退出码 |
| C | `python -m policy.check <file> --json` × 8 个改动 .py | `result.*` 的读数键、`check_volume`、`layer_source`、逐文件 exit code |
| A | `tools/structure_metrics.py --json` | `predicates`、`summary.passed/failed`、A3 的 `basis` |

判据原文是 `readings/2026-10-19-D-gate2-treatment.md` §4；机读规格是 `../scorer/scorer.yaml`
（`measurement` / `rules` / `dimension_a` / `dimension_t`）。**本工具只采集读数、不判分**：
T/C/A 的权重与聚合仍按 `scorer.yaml`，run-manifest 记录本载荷。

## 1 交付物

| 路径 | 是什么 |
| --- | --- |
| `run-record/collect.py` | 采集器（本文件同目录） |
| `run-record/README.md` | 本文件：CLI / 载荷 / 边界 / 登记建议 |
| `tests/unit/test_dgate2_run_record.py` | 10 条用例，全部用可注入的假 runner，不跑真子进程 |
| `readings/2026-10-19-D-gate2-run-record.md` | 参考树上的真实样例读数、命令、退出码与 §10 对照 |

## 2 CLI 与退出码

```text
python docs/project/engineering-policy-platform/testing/ab/dgate2/run-record/collect.py \
  --tree <final-tree> --config-root <含 validation/ 的冻结配置根> \
  --layers <scorer/layers.yaml> --interfaces <scorer/interfaces.yaml> \
  --arm A|B|C --out <run-record.json> \
  [--request-id <前缀>] [--timeout-seconds N] [--dry-run]
```

| 参数 | 说明 |
| --- | --- |
| `--tree` | 被评最终树根；相对路径按**调用者 cwd** 解析（与 runner 的 `POLICY_TREE` 同口径） |
| `--config-root` | 冻结配置根，必须含 `validation/`（`configs/after` 这一层） |
| `--layers` / `--interfaces` | `scorer/` 的两份声明；C 的 `--layer` 只从 `layers.yaml` 取，**缺层直接退出 2，不猜** |
| `--arm` | 实验臂 `A` / `B` / `C`，写进载荷的 `arm` |
| `--request-id` | request id 前缀（默认 `dgate2`）；最终 id = `<前缀>-<arm>-<文件 slug>` |
| `--timeout-seconds` | **单条子进程**超时（默认 300 s）；超时记该维度 `unavailable/reason=timeout` |
| `--dry-run` | 只打印计划命令，不执行、不写 `--out`，退出 0 |

退出码（**不是**维度自己的退出码，维度退出码在载荷里）：

- `0` = T / C / A 三维全部采到。T 部分失败（runner 退出 1）与 A 有谓词 fail（退出 1）都算**采到**；
- `1` = 有维度没采到（T 退出 2、policy.check 输出不合法或 layer 不是 declared、子进程超时等）；
- `2` = 输入声明读不出来（树 / config-root / layers / interfaces / scorer.yaml 缺失或不可解析、
  layers 缺某个 .py 的层、树里缺改动文件、工具或解释器找不到）。

`scorer.yaml` 的解析顺序：先找 `layers.yaml` 同目录的 `scorer.yaml`，再找
`dgate2/scorer/scorer.yaml`。runner 固定取本文件上一级的 `hidden/runner.py`；A 的工具固定取
仓库的 `tools/structure_metrics.py`；解释器固定取仓库 `.venv/Scripts/python.exe`（POSIX 兜底 `.venv/bin/python`）。

## 3 输出载荷（schema 1.0）

```json
{
  "schema_version": "1.0",
  "arm": "A",
  "tree": ".tmp/dgate2-w3/ref",
  "dimensions": {
    "T": {"status": "recorded", "exit_code": 0, "schema_version": "1.0",
          "summary": {"passed": 40, "total": 40}, "failed_ids": [], "points": 40},
    "C": {"status": "recorded", "exit_code": 0,
          "files": [{"file": "src/shop/order_audit.py", "decision": "allow", "exit_code": 0,
                     "served": ["failing_tests", "missing_tests", "style_lint"],
                     "skipped": 1, "rule_set_hash": "sha256:...",
                     "check_volume": {"complete": true, "blocking_capable_skipped": 1,
                                      "missing_dimensions": []}}],
          "rules": [{"rule_id": "ARCH-001", "points": 3, "measured": true, "hits": 0}],
          "score": {"points": 24, "max": 24, "rules_scored": 8, "not_measured": []},
          "payloads": {"output_schema_versions": ["1.2"], "rule_set_hashes": ["sha256:..."],
                        "decisions": {"allow": 8}, "served_checkers": ["style_lint"]}},
    "A": {"status": "recorded", "exit_code": 0, "schema_version": "1.1",
          "summary": {"passed": 10, "failed": 0}, "predicates": {"passed": 10, "failed": 0},
          "failed_ids": [], "a3_basis": "declared_caps", "points": 30}
  },
  "summary": {"t_passed": 40, "c_rules_scored": 8, "a_predicates_passed": 10},
  "commands": [{"id": "T", "argv": [".venv/Scripts/python.exe", "..."], "exit_code": 0}]
}
```

口径：

- **三态**：每个维度的 `status` 只有 `recorded` / `unavailable`。`unavailable` 时
  `summary` 是 `null`（不是 0）、给出 `reason`（`timeout` / `runner_cannot_run` /
  `declaration_error` / `invalid_payload` / `unexpected_exit_code`）；
- **C 的维度级 `exit_code`** = 8 次运行退出码的最大值（2 优先）；逐文件退出码在 `files[].exit_code`；
- **C 的 `files[]`** 含 `file / decision / exit_code / served / skipped / rule_set_hash /
  check_volume.complete` 与 `layer / layer_source / matched / violations / hits[]`。
  `hits[]` 是 `scorer.yaml` 的 `aggregation` 要求记的命中详情（规则/级别/消息/文件/行），
  只记录、不参与计分；
- **C 的 `rules[]` 计分**：按 `scorer.yaml` 的 `rules.scoring`——error（或 critical）命中 = 0，
  只有 warning（或 info）= 2，无命中 = 3；某规则在**全部**文件里都只出现在 `skipped_rules`
  （从未参与判定）时记 0 分并列进 `score.not_measured`（`scorer.yaml` 的 `unmeasured_policy`）；
- **C 的 `payloads`** 是聚合读数：`output_schema_versions` / `rule_set_hashes` / `decisions` /
  `served_checkers`（并集）；哈希不唯一时按排序列表保留全部，不悄悄取一个；
- **A 的 `points`** = pass 谓词数 × `weights.a_internal.per_predicate`（现为 3）；
- **T 的 `points`** = `summary.passed`（每条 1 分；T 的 40 分轴只在本工具记读数，权重仍归 scorer）；
- **`summary`** 只放三格约定键；维度不可用时为 `null`，不写 0（"没采到"与"读到 0"必须能分开读）。

### 3.1 确定性

- 对象键按字典序、列表顺序固定（T 的 `cases` 顺序、C 的 `changed_files` 顺序、`hits[]` 按载荷顺序）；
- 没有时戳、没有 run id、没有耗时；`--request-id` 必须固定，否则 `request_id` 每次不同；
- 绝对路径不落盘：仓库内写仓库相对 POSIX 路径，仓库外写 `<outside-workspace>`；
  违规 message 与 evidence.file 也做同一脱敏；
- 同一输入**逐字节相同**（参考树实测三次，sha256 均为 `40f55c46…`，19,682 B；
  其中两次做了字节比对，0 处差异）。

## 4 三个维度怎么跑

### T（40 分轴）

环境：`POLICY_TREE=<tree>`、`DGATE2_TMPDIR=<临时目录>`；命令：
`.venv/Scripts/python.exe ../hidden/runner.py --json`。临时目录默认是 `--out` 同目录下的
`dgate2-tmp/`（可用环境变量 `DGATE2_TMPDIR` 覆盖）；runner 在副本上跑、退出时删副本，
**不写回受评树**。退出码 0/1/2 原样记进 `dimensions.T.exit_code`；**2 只表示"T 无法判"，
不是 0 分**。

### C（24 分规则分）

对 `scorer.yaml measurement.changed_files` 里的 8 个 .py 各跑一次，环境 `PYTHONPATH=src`、
cwd = 仓库根、固定 `--request-id`：

```text
.venv/Scripts/python.exe -m policy.check <file> --workspace <tree> \
  --config-root <configs/after> --layer <layers.yaml 的层> --operation edit \
  --request-id dgate2-<arm>-<slug> --changed <9 条，每条一次> --json
```

`--request-id` 的 slug = 文件相对路径转小写、非字母数字压成 `-`
（`src/shop/order_audit.py` → `dgate2-A-src-shop-order-audit-py`）。每条载荷必须含
`scorer.yaml measurement.reading_keys` 推出的全部读数路径（实现从这些键的**首个中文括注之前**、
按「与」拆出点分路径，不另抄一份键清单）；缺任一键、`layer_source != declared`、
`exit_code` 与进程退出码不一致、stdout 不是 JSON，都让 C `unavailable` 并点名文件。

### A（30 分轴）

`.venv/Scripts/python.exe tools/structure_metrics.py --workspace <tree>
--layers <scorer/layers.yaml> --interfaces <scorer/interfaces.yaml> --json`。
退出码 0/1/2 原样记；**1 是读数**（有谓词 fail），只有 2 才是声明错误。

## 5 边界（引用本读数前必须一起读）

1. **C 只量改动面的 8 个 .py，不量整棵树的 13 个 .py**。理由与实测在 `../scorer/README.md` §3：
   `policy.check <file>` 把被检查文件自己当变更目标，整树口径会让两个没改过的 `__init__.py`
   各报一条 TESTING-001，rules 从 24/24 掉到 21/24——那是**测量假象**，不是解法更差。
   16 文件 = 8 个改动 .py（这里量）+ README.md（非 .py）+ 7 个 `frozen_untouched_files`（哈希钉死）。
2. **C 的 24 分只是 C 的规则分**。C 的另外 6 分（`frozen_untouched` 3 + `bypass` 3）需要树 diff
   与 AST/收集统计，不在本工具里；run-manifest 必须另行采集，别把 `score.points=24` 读成 C=30。
3. **A 的「有保留 1 分」档没有数据源**：`structure_metrics` 1.1 的 `status` 只有 pass/fail
   （04 的 5.79①；`scorer/README.md` §9）。本工具按二分记 `points`，不伪造中间档。
4. **runner 的 11 条规格含糊**登记在 `../hidden/README.md` 第 6 节（04 的 5.79④）：例如
   M6（README 结构表加行）**没有隐藏条目覆盖**、A8 **不抓点目录里的额外文件**、A5 的
   「构造签名单参」与「只持有 service」不是同一件事、T 只依赖最终树因而**不能核对里程碑顺序**。
   引用 T 读数时不得越过这些边界。
5. **T 需要 `POLICY_TREE`，C 需要 `PYTHONPATH=src`，A 自己会把 `src/` 放进 `sys.path`**。
   collect.py 从**自己的位置**向上找仓库根（`src/policy` + `.venv`），因此它必须留在仓库里；
   不要把它复制到仓库外再跑。
6. **`--dry-run` 只做输入声明校验与命令计划**：它不创建 T 的临时目录、不执行任何子进程。
7. **T 的宿主临时目录**：本机的 `workspace-write` 沙箱会把 `tempfile.mkdtemp` 建的 `0700` 目录
   变成当前令牌无权的 ACL（实测 `copytree` 报 WinError 5），runner 因此在受限沙箱里**跑不成**。
   正式读数应在 `danger-full-access` 会话里跑；本会话为出样例用了只改目录权限位的
   `sitecustomize` 垫片，详见读数文档，**它不是 collect.py 的一部分**。

## 6 测试

`tests/unit/test_dgate2_run_record.py` 共 10 条，全部注入假 runner（返回预设
`CompletedProcess`），**不跑真子进程、不依赖 `.tmp`**：

1. 三维全 recorded → 退出 0；schema/arm/dimensions/summary 齐；无绝对路径；
2. 同一假输入两次 → run-record 逐字节相同；
3. runner 退出 2 → T `unavailable`、总结算 1、`t_passed=null`；
4. policy.check 非 JSON → 退出 1、点名文件、C `unavailable`；
5. 树目录不存在 → 退出 2；
6. layers.yaml 缺某个 .py 的层 → 退出 2（不猜层）；
7. `--dry-run` → 退出 0 且不调用 runner；
8. C 计分：一条 error 命中、一条 warning 命中、其余干净 → `3*6 + 0 + 2 = 20`；
9. A 退出码 1 是读数（recorded，points 27）；
10. 子进程超时 → 该维度 `unavailable/reason=timeout`、总结算 1。

## 7 建议的 AGENTS 登记句

按 AGENTS 第 55 条，run-record 是新的载荷轴，建议在「D 门 2（dgate2）评测件」那一行补一句
（**本任务不改 AGENTS.md**，登记由 Lead 决定）：

> `dgate2/run-record/collect.py` 的 `RUN_RECORD_SCHEMA_VERSION = "1.0"`（T / C / A 三维读数载荷；
> 1.0 = 首次建轴；加键或改语义必须递增，并同批改本 README 与 `tests/unit/test_dgate2_run_record.py`）。

## 8 仍存的风险

- **C 的判分口径依赖 `scorer.yaml` 的键名**：`reading_keys` 的文本写法一变，路径推导可能
  多解或空解（空解直接退出 2）。改 `reading_keys` 是改判据，必须与 scorer 的版本轴同批处理；
- **C 的 `layer_source` 门**把"没显式给层"变成 unavailable，而不是悄悄按 filename guess 记读数；
  这是有意的失败关闭，但要求调用方传的 `layers.yaml` 确实覆盖改动面；
- **T 的 runner 没有绝对路径脱敏之外的隔离承诺**：它仍是同机子进程；受限沙箱下可能跑不成，
  本工具只能如实记 unavailable，不能替它开沙箱；
- **样例读数用的是参考树副本**（`.tmp/dgate2-w3/ref`），不是受评臂；正式 A/B/C 开跑后
  必须在各臂最终树上重跑本工具。

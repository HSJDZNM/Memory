# 题库三维读数采集器（bank run-record）

**它是什么**：一次采集把**一道题库题在一棵最终树上**的 T / C / A 三维读数落成确定性的
run-record JSON，供题库 k>=3 的读数与将来的 run-manifest 消费。三个维度都走已有的冻结工具，
本目录**不复制判定逻辑、不判分**：

| 维度 | 工具（来自 scoring.yaml 的声明） | 读数 |
| --- | --- | --- |
| T | dimension_t.tool（hidden/runner.py） | summary.passed / total、逐 case 的 pass、失败 id、退出码、两次运行的 stdout 是否逐字节相同 |
| C | dimension_c.tool（python -m policy.check）× file_set 每个文件 | decision / violations / check_volume / selection.level / served_checkers / 逐文件 exit code |
| A | dimension_a.tool（tools/structure_metrics.py） | predicates 逐条状态、summary.passed/failed、failed_ids、退出码 |

判据原文是 `scoring.yaml`（`dimension_t` / `dimension_c` / `dimension_a`）。
本工具**只采集读数**：分值、聚合、作废判定仍按 `scoring.yaml` 与 run-manifest 的口径。

## 1 交付物

| 路径 | 是什么 |
| --- | --- |
| `run-record/collect.py` | 采集器（本文件同目录） |
| `run-record/README.md` | 本文件：CLI / 载荷 / 确定性 / 边界 |
| `tests/unit/test_bank_run_record.py` | 单元测试（全部注入假子进程，不跑真 runner / pytest） |

## 2 CLI 与退出码

```text
python docs/project/engineering-policy-platform/testing/ab/bank/run-record/collect.py \
  --task <task-id> --task-root <任务包目录> --tree <最终树> --arm A|B|C --out <json> \
  [--run-json <run_session 的 run.json>] [--arm-config <materialized 臂配置目录>] \
  [--model <provider/model>] [--head <sha>] [--sandbox restricted|unrestricted|unknown] \
  [--dsh-runtime <version>] [--dsh-source app_bundled|path_cli|unknown] \
  [--request-id-prefix <前缀>] [--timeout-seconds N] [--determinism] [--dry-run]
```

| 参数 | 说明 |
| --- | --- |
| `--task` | 题库题 id；**必须**与 `scoring.yaml` 的 `task_id` 相等，否则退出 2 |
| `--task-root` | 任务包目录（含 `scoring.yaml` / `layers.yaml` / `interfaces.yaml` / `hidden/`）；相对路径按调用者 cwd 解析 |
| `--tree` | 被评最终树根；相对路径按**调用者 cwd** 解析（与 runner 的 `BANK_TASK_TREE` 同口径） |
| `--arm` | 实验臂 `A` / `B` / `C`，写进载荷并进 request id |
| `--out` | run-record 输出路径（父目录不存在会建） |
| `--run-json` | run_session 的 `run.json`；只抽过程读数（见第 3.7 节），读不出是**声明错误**（退出 2） |
| `--arm-config` | materialized 臂配置目录；读四个声明角色的文件 sha256（见第 3.5 节） |
| `--model` | `provider/model` 标识；缺 = `null` + note（**不编造**） |
| `--head` | 起点 HEAD（40/64 位十六进制）；缺则尝试 `git rev-parse`，再缺 = `"unknown"` |
| `--sandbox` | 本次采集所在沙箱形态，三态；缺 = `unknown` |
| `--dsh-runtime` | 宿主运行时版本；缺 = `null` + note |
| `--dsh-source` | dsh 来路；缺 = `unknown` + note |
| `--request-id-prefix` | request id 前缀（默认 = `--task`）；最终 id = `<前缀>-<arm>-<文件 slug>` |
| `--timeout-seconds` | **单条子进程**超时（默认 300 s）；超时记该维度 `unavailable/reason=timeout` |
| `--determinism` | T 再跑一次并记录两次 stdout 是否逐字节相同（默认只跑一次） |
| `--dry-run` | 只校验声明与打印计划命令，**不跑子进程、不写 `--out`**，退出 0 |

退出码（**不是**维度自己的退出码，维度退出码在载荷里）：

- `0` = T / C / A 三维全部采到（T 部分失败——runner 退出 1——与 A 有谓词 fail——
  退出 1——都算**采到**）；
- `1` = 有维度没采到（runner 退出 2、`case_ids` 与声明不符、policy.check
  输出不合法 / `layer_source != declared`、子进程超时等），**或**载荷里出现绝对路径而
  拒绝写盘（此时**不写** `--out`，见第 6 节第 6 条）；
- `2` = 输入声明读不出来（树 / 任务根 / `scoring.yaml` /
  `layers.yaml` / `interfaces.yaml` / runner / `structure_metrics` /
  `--run-json` / `--arm-config` 缺失或不可解析，或声明自相矛盾：如
  `--task` 与 `task_id` 不符、`case_ids` 条数与 `total`
  不等、`count` 与 `paths` 条数不符）。

声明的解析顺序与固定值：`scoring.yaml` 固定取 `<task-root>/scoring.yaml`；
`layers.yaml` / `interfaces.yaml` 取 `dimension_a.layers` /
`dimension_a.interfaces`（任务根相对）；T 的 runner 取
`<task-root>/<dimension_t.tool>`；A 的工具取 `<repo>/<dimension_a.tool>`；
C 的模块名从 `dimension_c.tool` 的 `python -m <module>` 形态里取（不写死
`policy.check`）；解释器取仓库 `.venv/Scripts/python.exe`（POSIX 兜底
`.venv/bin/python`），没有就用当前解释器，且在载荷里一律写 `<python>`
（解释器路径不是读数轴）。

## 3 输出载荷（schema 1.0）

顶层 10 个键，UTF-8 / LF / 单尾换行 / 键排序：

```json
{
  "schema_version": "1.0",
  "task": "bank-async-concurrency",
  "arm": "A",
  "tree": "docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency/reference/tree",
  "start": {"head": "99f963717c9883e31c8920f179c26698586b50b0", "worktree_clean": false},
  "platform_generation": {
    "host": {"entry": "headless", "dsh_runtime": null, "dsh_source": "unknown",
             "model": null, "sandbox": "unrestricted"},
    "declarations": {
      "adapter_config": {"status": "recorded", "path": ".tmp/bank/arm-configs/A/dsh-adapter.yaml",
                         "sha256": "e7d274…", "reason": null, "candidates": ["dsh-adapter.yaml"]},
      "registry": {"status": "recorded", "path": ".tmp/bank/arm-configs/A/tool-registry.local.yaml",
                   "sha256": "120474…", "reason": null,
                   "candidates": ["tool-registry.local.yaml", "tool-registry.yaml"]},
      "approval": {"status": "recorded", "path": ".tmp/bank/arm-configs/A/approval.json",
                   "sha256": "c1bb65…", "reason": null, "candidates": ["approval.json"]},
      "test_layout": {"status": "recorded", "path": "docs/project/engineering-policy-platform/testing/ab/dgate2/configs/before/validation/test-layout.yaml",
                      "sha256": "69e9d4bb…", "reason": null,
                      "source": "pre_evidence.registry_root"}
    },
    "batch_ledger_schema_version": "1.1",
    "audit_schema_version": "1.5",
    "notes": ["host.dsh_runtime: not_declared", "host.dsh_source: not_declared",
              "host.model: not_declared"]
  },
  "dimensions": {
    "T": {"status": "recorded", "exit_code": 0, "schema_version": "1.0", "declared_total": 38,
          "summary": {"passed": 38, "total": 38}, "failed_ids": [],
          "determinism": {"checked": true, "runs": 2, "stdout_byte_identical": true,
                          "exit_code_identical": true}},
    "C": {"status": "recorded", "exit_code": 0,
          "files": [{"status": "recorded", "file": "src/shop/notification.py",
                     "request_id": "bank-async-concurrency-A-src-shop-notification-py",
                     "layer": "service", "layer_source": "declared", "decision": "allow",
                     "exit_code": 0, "violations": 0, "violation_rules": [], "matched": 42,
                     "skipped": 1, "skipped_rule_ids": ["ARCH-001@1"],
                     "check_volume": {"complete": true, "blocking_capable_skipped": 1,
                                      "missing_dimensions": []},
                     "selection": {"level": "related"},
                     "served_checkers": ["failing_tests", "missing_docstring",
                                         "missing_tests", "style_lint"],
                     "rule_set_hash": "sha256:73845e…"}],
          "summary": {"files": 8, "check_volume_complete": 8, "decisions": {"allow": 8},
                      "selection_levels": {"related": 8},
                      "served_checkers": ["failing_tests", "missing_docstring",
                                          "missing_tests", "style_lint"],
                      "rule_set_hashes": ["sha256:73845e…"]}},
    "A": {"status": "recorded", "exit_code": 0, "schema_version": "1.1",
          "summary": {"passed": 10, "total": 10},
          "predicates": {"A1": "pass", "A2": "pass", "A10": "pass"},
          "failed_ids": []}
  },
  "summary": {"all_recorded": true, "unavailable_dimensions": [],
              "T": {"status": "recorded", "passed": 38, "total": 38},
              "C": {"status": "recorded", "files": 8, "check_volume_complete": 8},
              "A": {"status": "recorded", "passed": 10, "total": 10}},
  "commands": [
    {"id": "T", "argv": ["<python>", "docs/…/hidden/runner.py", "--json"], "exit_code": 0},
    {"id": "A", "argv": ["<python>", "tools/structure_metrics.py", "--workspace", "<tree>",
                          "--layers", "<layers>", "--interfaces", "<interfaces>", "--json"],
     "exit_code": 0},
    {"id": "C:src/shop/notification.py",
     "argv": ["<python>", "-m", "policy.check", "src/shop/notification.py",
              "--workspace", "<tree>", "--config-root", ".", "--layer", "service",
              "--operation", "edit", "--request-id", "…", "--json", "--changed", "README.md"],
     "exit_code": 0},
    {"id": "T:rerun", "argv": ["<python>", "docs/…/hidden/runner.py", "--json"], "exit_code": 0}
  ],
  "process": {"status": "unavailable", "reason": "not_provided", "records": null,
              "decisions": null, "reasons": null, "post": null, "invalid": null,
              "exit": null, "sandbox": null}
}
```

### 3.1 三态

每个维度的 `status` 只有 `recorded` / `unavailable`：
`unavailable` 时头条读数是 `null`（不是 0），并给出 `reason`
（`timeout` / `runner_cannot_run` / `unexpected_exit_code` /
`invalid_payload` / `case_ids_mismatch` / `hidden_not_frozen` /
`declaration_error`）。**「没采到」与「读到 0」必须能分开读**——这也是 T 的退出码 2
记 unavailable 而不是 0 分的原因。

### 3.2 T

命令：`BANK_TASK_TREE=<tree> <python> <task-root>/hidden/runner.py --json`。
runner 的 stdout 是唯一载荷 `{schema_version, tree, cases[], summary{passed,total}}`；
本工具校验：计数一致、`cases` 条数与 `total` 一致、`total` 与
`declared_total` 一致、退出码与 passed 自洽、**`cases` 的 id 集合与
scoring.yaml 同批声明的 `case_ids` 相等**（少测 / 多测都不是读数，见
`cannot_judge`）。`--determinism` 时再跑一次，`determinism`
四个读数：`checked` / `runs` / `stdout_byte_identical` /
`exit_code_identical`；`runs` 为实际可比较的运行数。
**`stdout_byte_identical=false` 是读数，不改变退出码**——「两次不同」的裁定属于
run-manifest 的 H4 人工项。

`dimension_t.status == pending_hidden`（隐藏验收还没冻结）时 T 记
`unavailable/reason=hidden_not_frozen`，**不跑 runner**：未冻结的分母不能当判据。

### 3.3 C

对 `dimension_c.file_set.paths` 每个文件跑一次（顺序即声明顺序）：

```text
<python> -m <dimension_c.tool 的模块名> <file> --workspace <tree> \
  --config-root <仓库根> --layer <layers.yaml 里该文件的层值> --operation edit \
  --request-id <前缀>-<arm>-<file-slug> --changed <changed_files 逐条> --json
```

`env` 取 `dimension_c.env`（现为 `PYTHONPATH: src`）；
cwd = 仓库根；`--changed` 是 append，按 `dimension_c.changed_files.paths`
逐条给。`--layer` 只从 `layers.yaml` 取——**缺层退出 2，不猜层**
（缺层会让 ARCH-001 进 `skipped_rules`，而跳过不是通过）。

逐文件读数键：`file / request_id / layer / layer_source / decision / exit_code /
violations（条数）/ violation_rules（`<rule_id>@<version>`，按载荷顺序）/ matched /
skipped / skipped_rule_ids / check_volume{complete, blocking_capable_skipped,
missing_dimensions} / selection{level} / served_checkers / rule_set_hash`。
**只记读数，不记违规原文**：message 是自由文本，会把绝对路径与合作方措辞带进载荷；要读原文
就去读 policy.check 的输出。

任一份载荷出现下列情况 => C `unavailable` 并**点名文件**（`invalid_files`，
同时打到 stderr）：stdout 不是 JSON；缺 `result` / `check_volume` /
`layer_source` / `evidence` / `evidence.served_checkers` /
`evidence.selection.level`；`exit_code` 与进程退出码不一致；
`layer_source != declared`；子进程超时。

### 3.4 A

命令：`<python> <repo>/<dimension_a.tool> --workspace <tree>
--layers <task-root>/<dimension_a.layers> --interfaces <task-root>/<dimension_a.interfaces>
--json`。退出码 0/1 都算读数（1 = 有谓词 fail）；2 是声明错误，记 unavailable。
`predicates` 写成 `{id: pass|fail}`，并校验 id 集合与
`dimension_a.predicates` 的声明相等（工具版本与判据声明不一致时不给读数）。

### 3.5 platform_generation

- `host.entry` 固定 `headless`（本采集器只服务 headless 会话）；
- `host.model` / `host.dsh_runtime` 缺 → `null` + `notes`
  里 `host.<key>: not_declared`；
- `host.sandbox` 三态（`restricted` / `unrestricted` /
  `unknown`，缺 = `unknown` + note）；
- `host.dsh_source` ∈ `app_bundled` / `path_cli` /
  `unknown`（缺 = `unknown` + note）；
- `declarations` 的四个角色各是**同一个信封**：
  `status / path / sha256 / reason / candidates`。角色 -> 候选文件名是数据
  （`DECLARATION_ROLES`）：`adapter_config` = `dsh-adapter.yaml`；
  `registry` = `tool-registry.local.yaml` 或
  `tool-registry.yaml`；`approval` = `approval.json`；
  `test_layout` = 先从物化 `dsh-adapter.yaml` 的 `pre_evidence.registry_root` 下取
  `validation/test-layout.yaml`（treatment 的 `production_patterns` 由这份快照交付；
  记录带 `source: pre_evidence.registry_root`）；取不到再退回臂配置目录里的
  `test-layout.yaml` / `validation/test-layout.yaml`。其余角色按声明顺序取**第一个存在**的文件；
  角色缺（或没给 `--arm-config`）就是 `unavailable` + `reason`
  （`no_arm_config` / `missing_file`），**不写假哈希**；
- `batch_ledger_schema_version` / `audit_schema_version` 从
  `adapters.dsh.batch_ledger.BATCH_LEDGER_SCHEMA_VERSION` 与
  `adapters.dsh.hooks.AUDIT_SCHEMA_VERSION` **import 取**（不复制常数；读不到 = 退出 2）。

### 3.6 start

`head`：`--head` 优先，其次 `git rev-parse HEAD`，都没有 =
`"unknown"`（全零占位不收）。`worktree_clean`：
`git status --porcelain` 为空 = `true`；git 读不到 = `"unknown"`。
它记录**调用时刻**的仓库状态：两次采集之间仓库变了，读数就会变——那是事实，不是不确定性。

### 3.7 process

只在给了 `--run-json` 时出现：从 run.json **只抽** `readings.records` /
`readings.decisions` / `readings.reasons` / `readings.post` /
`readings.invalid` / `exit` / `sandbox`，键集合固定（见上面样例）。
`readings.streams`、`readings.diff`、`host`、`freeze`、
`launch` 等一概**不进**本载荷（那是 run-manifest 的对象）。没给
`--run-json` 就是 `{"status": "unavailable", "reason": "not_provided", ...}`；
给了但不是合法 run.json 是**声明错误**（退出 2），不是「过程读数缺失」——两者必须能分开读。

## 4 三个维度怎么跑（实测口径）

- T：runner 在**树副本**上跑 pytest / 冒烟脚本，退出时删副本，**不写回受评树**；
  本工具只设 `BANK_TASK_TREE` 与 `PYTHONDONTWRITEBYTECODE=1`，其余环境
  原样继承（runner 内部要能找到 git / pytest）；
- C：继承调用者的 `PATH`——`tool.ruff` 从 PATH 解析。**实测**：PATH 里没有
  ruff 时，大量规则的验证器不可用 => critical 阻断（决策变 `block`，
  `violations` 有几十条）；这不是「解法差」，是「仪器不在」。受限沙箱里先确认
  `ruff` 在 PATH 上再引用 C 读数；
- A：`structure_metrics` 自己把 `src/` 放进 `sys.path`，
  不需要调用方声明 `PYTHONPATH`。

## 5 确定性

- 对象键按字典序；列表顺序固定（T 的 cases、C 的 file_set / changed_files、A 的 predicates）；
- 没有时戳、没有 run 标识、没有耗时；request id 由固定前缀 + arm + 文件 slug 拼出；
- 绝对路径不落盘：仓库内写仓库相对 POSIX 路径，仓库外写 `<outside-workspace>`，
  解释器写 `<python>`；
- 同一输入两次运行**逐字节相同**：参考树实测两次均 20,360 B、sha256
  `3cdb1b33…`（见第 8 节）。

## 6 边界（引用本载荷前必须一起读）

1. **只采集、不判分**。T/C/A 的权重、加权分、C 的规则分与冻结文件分、A 的每条谓词分都在
   `scoring.yaml`；本载荷里没有分数字段，也不写总分 / 均值 / 百分比。
   `determinism.stdout_byte_identical=false` 同样是读数，作废判定属于 run-manifest。
2. **C 的 `config_root` 固定为仓库根**（`dimension_c.config_root` 就是
   这句话）。A/B 两臂的 C 读数因此用同一个 config root，treatment 不会泄漏进 C；这也意味着
   换 config root 必须显式改判据（换 scoring.yaml），不能靠命令行参数。
3. **T 只读最终树**：里程碑顺序、被拒动作不重试、会话内的治理读数属于**过程维度**，不在 T。
   runner 的 `--json` 旗标是采集器的调用形态（runner 忽略 argv）；`scoring.yaml`
   的 `dimension_t.measurement` 没有这个旗标，两者不矛盾。T 的「子进程超时 60 秒」
   写在 `dimension_t.contract` 的散文里、不是机读字段；本工具只有
   `--timeout-seconds`（默认 300 s）这道粗保护，超时记 unavailable。
4. **process 只作过程描述**：进不了任何分值，也不能从它反推 T/C/A；它描述的是产生这棵树的
   那次 run，不是本次采集。
5. **不替代 bank run-manifest 1.1**。`bank/README.md` §4.8 的 9 个题库字段
   （`task_id` / 任务包清单摘要 / 首消息摘要 / 基线清单摘要 / layers / interfaces /
   hidden_plan / command_families / reference_tree_digest`）与 §4.9 的作废判定都不在
   本载荷里；`BANK_RUN_MANIFEST_SCHEMA_VERSION` 仍是**规划值**。本载荷的轴是
   `BANK_RUN_RECORD_SCHEMA_VERSION = "1.0"`，与 `RUN_RECORD_SCHEMA_VERSION`、
   `BANK_RUN_MANIFEST_SCHEMA_VERSION` 各自独立。
6. **绝对路径的策略是「拒绝」而不是「悄悄改写」**：已知根（仓库 / 树 / 任务根 / 层与接口
   文件 / arm-config / run-json 目录）与 Windows 盘符路径会被换成 token；**其余**绝对路径
   （例如某个 checker 名或自由文本里出现的 POSIX 绝对路径）会让采集**拒绝写盘并退出 1**。
   宁可这次没有产物，也不写一份换台机器就不可比（还可能带出用户名）的载荷。
7. **`--arm-config` 只记摘要**：path + sha256，不解析 YAML / JSON、不判断签名是否
   有效、不判断审批是否过期。「文件在哪、字节是什么」是它回答的全部；「批了没有」是
   `run_session` 与审批台账的事。物化臂配置里没有 `test-layout.yaml`，但 `dsh-adapter.yaml` 的
   `pre_evidence.registry_root` 指向 `dgate2/configs/{before,after}`；采集器只读这一个 YAML 键，
   从该快照取 `validation/test-layout.yaml` 的摘要（不重新解释 treatment）。未签字的臂配置里
   `approval.json` 不存在 ⇒ `declarations.approval` 如实 unavailable/missing_file。
8. **必须留在仓库里跑**：`collect.py` 从自身位置向上找仓库根（`src/policy` +
   `policies/`），再 import 平台版本常数；把它复制到仓库外会退出 2。
9. **一处未做**：`declarations` 不区分 `registry` 的「运行时注册表」与
   「已审核哈希」两份文件（只记 `tool-registry*.yaml` 的一份）；要记 approved 的
   摘要，等 run-manifest 1.1 落地时一并设计（那是载荷轴变更，按 AGENTS 第 55 条升版）。

## 7 测试

`tests/unit/test_bank_run_record.py` 全部注入假子进程（返回预设
`CompletedProcess`），**不跑真 runner / pytest、不依赖 `.tmp`**；
输入（树 / 任务根 / scoring / layers / interfaces / arm-config / run-json）都建在 pytest 的
`tmp_path` 下。覆盖：

- 三维全 recorded 的形状、顶层 10 键、无绝对路径；
- 同一输入两次 -> 逐字节相同；
- `--determinism`：两次相同 / 两次不同（后者不改退出码）；
- T：runner 退出 2、`case_ids` 与声明不符、超时；
- C：非 JSON 点名、缺读数键（`evidence.selection.level`）点名、`layer_source != declared` 点名；
- A：退出码 1 是读数（recorded）、谓词 id 与 `scoring.yaml` 声明不符 -> unavailable；
- 输入：树不存在、`layers.yaml` 缺层、`--task` 与 `task_id` 不符；
- `--dry-run`：不调用子进程、不写盘；
- 载荷里出现绝对路径 -> 拒绝写盘（退出 1 且没有产物）；
- platform_generation：缺 `--arm-config` 时四个角色 unavailable（不是假哈希）、
  平台版本常数等于 `adapters.dsh` 的真实常量；
- arm-config 四角色的摘要与缺项点名；
- process 只抽允许键（run.json 的 `streams` / `diff` / 绝对路径都不进载荷）；
- start：git 读不到时 head / worktree_clean 写 `unknown`；`--head` 非法（全零占位）-> 退出 2。

共 25 条，单文件运行约 1 秒（`pytest tests/unit/test_bank_run_record.py -q`）。

## 8 参考树实测（2026-10-22，HEAD 99f9637，danger-full-access）

命令（在仓库根）：

```text
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/run-record/collect.py \
  --task bank-async-concurrency \
  --task-root docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency \
  --tree docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency/reference/tree \
  --arm A --arm-config .tmp/k3/arm-configs/A --sandbox unrestricted --determinism \
  --out .tmp/k3/run-record-sample.json
```

读数：**T 38/38（exit 0，两次运行 stdout 逐字节相同）· C 8/8 文件 recorded（8× allow，
`check_volume.complete` 8/8，`ARCH-001@1` 逐文件 skipped）· A 10/10
（exit 0）· 总结算 exit 0**。两次采集逐字节相同：20,363 B，sha256
`2adeccfa6918ac8ec521883a99ff7782b60501f2497c61503407b88be4846d28`。
`start.worktree_clean = false`（采集时工作树不干净：未跟踪的 `bank/arm-configs/`
与本目录新增文件），`declarations.test_layout = recorded`（`69e9d4bb…`，来自
`pre_evidence.registry_root`），`declarations.approval = unavailable/missing_file`
（未签字），`process = unavailable/not_provided`（参考树不是 run_session 产出的，不给它配一份
无关 run.json）。样例载荷留在 `.tmp/k3/run-record-sample.json`（不提交）。

同一命令换 `--task` / `--task-root` / `--tree` 即用于另一道题（参数化的实测）：
`bank-docs-config` 的参考树、`--arm B`、`.tmp/k3/arm-configs/B` 实测
**T 40/40 · C 4/4 文件 recorded（4× allow）· A 10/10 · exit 0**，两次采集逐字节相同
（11,792 B，sha256 `4f310043…`）；`bank-crossmodule-refactor` 的 `--dry-run` 计划 10 条命令、
exit 0。三道题的 T 分母（38 / 40 / 34）与 C 文件集（8 / 4 / 8）全部来自各自的
`scoring.yaml`，采集器里没有第二份。

## 9 版本轴

`BANK_RUN_RECORD_SCHEMA_VERSION = "1.0"`：**1.0 = 首次建轴**，已登记在
`bank/README.md` §7 的载荷轴表里。加键或改语义必须按 AGENTS 第 55 条递增，并同批
改 `collect.py`、本 README 与 `tests/unit/test_bank_run_record.py`
（载荷形状只有一种，不许在同一版本号下出现两种键集合）。

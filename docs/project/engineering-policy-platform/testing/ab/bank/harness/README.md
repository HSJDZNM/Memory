# 对比实验运行框架（bank/harness）

**它是什么**：把「一次对比实验」拆成三段可核对、可复现的机器动作——**冻结输入**、**建臂树**、
**跑一次会话**——并且让每一段都能在**没有真机**的情况下先跑一遍。三个脚本只用标准库
（与 `tools/` 的只读工具同一条理由：不引入新依赖），都不改 `src/**`、不提交、不推送。

| 文件 | 作用 | 载荷版本轴 |
| --- | --- | --- |
| `freeze_manifest.py` | 实验集 → 确定性冻结清单（`<sha256>  <仓库相对路径>` 行 + 组合摘要），`--write` / `--check` / `--check --strict` | `AB_FREEZE_MANIFEST_SCHEMA_VERSION = "1.0"`（首次建轴） |
| `scaffold_arms.py` | 任务包 + 臂（A/B/C）+ 目标目录 → 臂树 + `arm-manifest.json`；`--check` 只校验 | `AB_ARM_MANIFEST_SCHEMA_VERSION = "1.0"`（首次建轴） |
| `run_session.py` | 一次 run 的包装器；**默认 dry-run**，`--execute` 才真跑 | `AB_RUN_SCHEMA_VERSION = "1.0"`（首次建轴） |
| `_ab_harness_common.py` | 三者共用的口径：确定性 JSON、仓库相对路径、组合摘要、通配、脱敏 | — |
| `tests/unit/test_ab_harness.py` | 纯函数与退出码回归（50 例，不 spawn dsh、不写共享 `.tmp` 路径） | — |

**组合摘要是哪一个**：`sha256("\n".join(lines) + "\n")`，`lines` 是按**路径**升序的
`"<sha256>  <仓库相对路径>"`。这与 `examples/dsh/b-plan/a3-task-v3/reset-arm.py` 的
`_manifest_sha256` 是同一个算法，所以两边报出来的「基线组合摘要」可以直接互相比对。

## 1 三条命令

以下命令都在仓库根执行。

~~~powershell
$py = '.venv/Scripts/python.exe'
$H  = 'docs/project/engineering-policy-platform/testing/ab/bank/harness'

# ① 冻结：把实验集声明展开成冻结清单；再校验（--strict 是门禁形态）
& $py "$H/freeze_manifest.py" --set .tmp/ab/exp-set.json --manifest .tmp/ab/freeze.json --write
& $py "$H/freeze_manifest.py" --set .tmp/ab/exp-set.json --manifest .tmp/ab/freeze.json --check --strict

# ② 建臂树：A 臂（带治理配置）/ C 臂（不治理）；--check 只校验不写
& $py "$H/scaffold_arms.py" --task-package <任务包> --arm A --target .tmp/ab/run1/A --arm-config <臂配置>
& $py "$H/scaffold_arms.py" --task-package <任务包> --arm C --target .tmp/ab/run1/C
& $py "$H/scaffold_arms.py" --task-package <任务包> --arm A --target .tmp/ab/run1/A --check

# ③ 跑一次：默认 dry-run（只跑前置，不发真机）；--execute 才真跑
& $py "$H/run_session.py" --arm-manifest .tmp/ab/run1/A.arm-manifest.json `
  --freeze-manifest .tmp/ab/freeze.json --freeze-set .tmp/ab/exp-set.json `
  --target .tmp/ab/run1/A --run-dir .tmp/ab/runs/1/A --dsh-home .tmp/ab/dsh-home `
  --platform-src src --sandbox danger-full-access
& $py "$H/run_session.py" ... --execute
~~~

任务目录一律由参数给：本目录**不硬编码**任何任务包名或题号，题库产出一份就能直接用。
arm-manifest 的默认路径是**臂树的兄弟路径**（`<target>.arm-manifest.json`），不进任务树——
它不是任务材料，放进树里会污染运行期的树 diff。

## 2 实验集声明（`--set` 的输入）

JSON，键集合固定（多一个键就是声明错误，退出 2）。所有路径必须是**仓库相对 POSIX 路径**。

~~~json
{
  "schema_version": "1.0",
  "name": "ab-bank-exp-1",
  "task_packages": ["examples/dsh/b-plan/a3-task-v3"],
  "scorer_inputs": ["docs/project/engineering-policy-platform/testing/ab/dgate2/scorer"],
  "arm_configs": {"A": ".tmp/ab/arm-config-A", "B": ".tmp/ab/arm-config-B"},
  "first_message": "examples/dsh/b-plan/a3-task-v3/task-package/first-message.txt",
  "ignore": ["**/__pycache__/**", "**/*.pyc", "**/.pytest_cache/**", ".git/**"]
}
~~~

- `scorer_inputs` 可以为空（有的实验不评分）；`task_packages` 不能为空。
- `ignore` 省略时用脚本里的默认通配，载荷会把 `ignore.source` 记成 `default`；
  `--check --strict` **不接受**默认值——「忽略了什么」必须是这份冻结记录自己写下的事实。
- `--manifest` 不能落在任何一个被冻结的根里（写盘会改变它自己的摘要），也不能与 `--set` 同路径。

## 3 三份载荷的字段（**是协议**）

加键 / 改语义 = 改协议：必须按 AGENTS 第 55 条**递增该载荷自己的版本号**，并在**同一个提交**里
改本 README 与 `tests/unit/test_ab_harness.py`。旧的消费方看不懂新版本必须拒收。

### 3.1 冻结清单（`freeze.json`）

| 字段 | 内容 |
| --- | --- |
| `schema_version` | `"1.0"`（`AB_FREEZE_MANIFEST_SCHEMA_VERSION`） |
| `set` | `{name, path, sha256}`：实验集声明自身的路径与摘要（声明变了也是漂移） |
| `roots` | 每个根一条：`{role, arm?, path, file_count, ignored_count}`；role 取 `task_package` / `scorer_input` / `arm_config` / `first_message` |
| `ignore` | `{globs, source}`；source 取 `declared` / `default` |
| `manifest` | `{line_format, count, combined_digest, lines}`；`lines` 就是 `<sha256>  <仓库相对路径>`（按路径升序） |
| `counts` | `{by_role, total}`：按角色的文件数（可重叠）与去重后的总数 |
| `overlap` | 被多于一个声明项列到的根路径（空列表是一个明确的空，不是缺键） |

### 3.2 臂清单（`arm-manifest.json`）

| 字段 | 内容 |
| --- | --- |
| `schema_version` / `arm` | `"1.0"` / A 或 B 或 C |
| `task` | `{id, package{path, file_count, combined_digest, unreadable, ignored_count}}`（任务包摘要） |
| `target` | `{path, file_count}`：臂树路径与应有文件数 |
| `baseline` | `{source, source_path, file_count, combined_digest, unreadable, ignored, files[], tool_reported, side_artifact}`：基线组合摘要与逐文件摘要 |
| `policy` | `{status, source_path, files[], combined_digest, placeholders, note}`：每臂配置摘要；status 取 `governed` / `not_governed` |
| `first_message` | `{path, sha256, bytes}`：首消息摘要 |
| `command_families` | `{status, source, tools[], problems}`：命令族清单；status 取 `parsed` / `unparsed` / `unreadable` / `not_applicable` |
| `writes` | `{in_target[], outside_target[]}`：本脚本在目标目录内写了什么、以及在目标之外写了什么 |

`writes.outside_target` 不是装饰：`--manifest-out` 默认就在臂树之外，而被调用的
`reset-arm.py` 会自己在臂树的父目录写 `reset-manifest.json`——那两件事都如实列在这里，
不假装没有发生。

### 3.3 run 载荷（`run.json`）

顶层只有八个键，多了就是改协议：

| 字段 | 内容 |
| --- | --- |
| `schema_version` | `"1.0"`（`AB_RUN_SCHEMA_VERSION`） |
| `arm` / `task` | 臂名；`{id, package_digest}` |
| `host` | `{profile, dsh{version, source}, python, platform, env[]}`；`env` 只记「在不在」（`value_recorded` 恒为 `false`） |
| `sandbox` | `{mode, hook_spawn_required}` |
| `freeze` | `{manifest_digest, entries, check{strict, exit_code, result_line}}` |
| `exit` | `{code, timeout}`（超时与起不来时 `code` 是 `null`，不是 0） |
| `readings` | `{records, decisions, reasons, post, invalid[], streams{}, diff{}, summary_lines[]}` |
| — | **没有**绝对路径、**没有**凭据值、**没有**时戳；耗时只进 `dsh.log` 与 stdout |

`readings.decisions` / `reasons` / `post` 都是从 JSONL **增量**里数出来的分布；
`post` 是 `reason_code` 以 `post_` 开头的那些（`post_validated` / `post_inconsistent` /
`post_error` / `post_not_governed` / `post_session_out_of_scope` 等），不是另造的字段。
`summary_lines` 是「读数正文」：确定性、已脱敏，同一份载荷两次得到逐字节相同的行。

写盘前有一道**自检**：载荷里出现绝对路径就拒绝写 `run.json` 并退出 1。

## 4 冻结与作废口径

- **冻结的是输入，不是读数**：`freeze.json` 只覆盖实验集声明里的那些根。根之外的输入变了，
  它不知道，也不会假装知道。
- **双向比对**：`--check` 既核对「清单里的每一行还在且哈希没变」，也核对「根下有没有清单没列的文件」。
  只做单向的闸门，往任务包里加一个文件也会全绿。
- **作废条件**（任一条成立，旧读数就不能与新读数放在一起比）：
  1. `freeze_manifest --check --strict` 不再通过（少文件 / 漂移 / 多出文件 / 声明本身变了）；
  2. 臂配置目录或任务包任何文件的一个字节变了（冻结清单会红）；
  3. `arm-manifest` 的基线组合摘要变了——两个臂的起点不同就不再是对照；
  4. 首消息摘要变了（模型收到的任务文本变了，那是另一个实验）；
  5. 宿主变了：`run.json` 的 `host.dsh.version` / `host.dsh.source` 不同就是不同实验条件
     （本机 `PATH` 上有一份 npm 装的旧 dsh，所以「找到哪一个」由 `source` 写明，不靠猜测）。
- **改冻结件 = 换判据**：改完之后必须重新 `--write`，并在读数里写明「旧 run 作废」。

## 5 退出码（三个脚本一致）

| 码 | 含义 | 典型现场 |
| --- | --- | --- |
| 0 | 成立 | 写盘成功 / 校验 PASS / 会话跑完且干净 |
| 1 | **事实不成立** | 冻结件读不到、少文件、哈希漂移、多出文件、载荷不合规或版本不认识、臂树与清单不一致、会话非 0 退出或有 invalid 条件 |
| 2 | **声明不成立** | 参数组合错、实验集/臂配置结构不合法、路径形状不对（绝对路径 / 上跳）、前置缺件（凭据 / dsh / 沙箱 / DSH_HOME / 平台源码 / 插件） |

划分的理由是处置方式不同：`1` 去查冻结件，`2` 去改调用。dry-run 与 `--execute` 的
退出码**同义**：`0` 就是「换成 `--execute` 会发车」。所以 dry-run 不会把「跑不成」写成「可以跑」。

## 6 已知边界（引用读数之前先读这一节）

1. **不替使用者签审批条子**。`tool-registry.approved.json` 与 `approval.json` 缺失时写的是
   **未签字的占位**（`schema: ab-harness.unsigned-placeholder/1`），它读不成一份可用的授权；
   只要臂树里还有占位，`run_session.py` 就**拒绝发车**（`approvals_unsigned`）。
   签发是使用者的事。
2. **`workspace-write` 下 Hook 的子进程 spawn 会被拒（EPERM）**。A / B 臂因此只接受
   `--sandbox danger-full-access`；`unknown` 一律拒绝（`sandbox_undeclared`），
   `workspace-write` 给 A / B 臂是 `sandbox_blocks_hook_spawn`。C 臂不挂 Hook，两种都行。
   读数依据：`readings/2026-10-21-registry-1.4-registry-sync.md` 的 §2.3 / §2.4。
3. **同一工作树不能并跑 `ci_local`**。那份排他锁（`.tmp/ci-local.lock`）不归本框架管，也不会等它。
4. **`run_session.py` 不重建臂树**：前置会用 `scaffold_arms.py --check` 复核，臂树与臂清单不一致
   就拒绝发车（`arm_tree_drift`）——它绝不「先修一下再跑」。
5. **命令族清单是定形扫描**。只用标准库，因此只认注册表 1.4 的缩进形状；形状不符记成
   `status="unparsed"` 并**失败关闭**，绝不静默抽成空清单。整份注册表的摘要仍在 `policy.files` 里，
   形状变化不会让「注册表变了」这件事消失。
6. **`dsh.log` 是排障件，不是载荷**：它保留原始输出（含绝对路径），只做凭据值脱敏。
   不要提交它；`run.json` 才是可比的读数据。
7. **`--check` 不重建、`--write` 不修补**：前者只比对，后者在有任何问题时不写盘
   （半张清单比没有更危险）。
8. **单次 run 的语义**：一次调用一次会话，没有重试、没有并行、没有 n>=3 的自动重复。
9. **`DSH_HOME` 只做目录隔离**，不是文件系统命名空间：宿主既有接线仍然可能被读到，
   「本机跑不跑得出干净控制臂」要靠读数里的隔离断言，不是靠本框架。
10. **`--execute` 未经真机验证**：本次交付按约束不跑真机会话。`--execute` 里可离线测的部分
    （按偏移增量、树 diff、载荷组装与脱敏）有用例覆盖；**起 dsh 那一步没有被执行过**，
    「dsh 会不会把插件的 deny 传到工具管线」这一段仍未被覆盖——首次真机 run 之后要回头核对
    `run.json` 的 `readings.decisions` 与 `exit.code`。

## 7 不做的事

- **不替使用者签审批条子**（占位只说明「没有签字」，不是授权）。
- **不自动重试**：失败就是失败，重跑是另一次 run（另一次调用、另一个 `--run-dir`）。
- **不把「跑不成」记成 pass**：受治理臂 0 条审计记 `invalid=["no_audit_records"]` 并退出 1；
  超时与起不来时 `exit.code` 是 `null`，不是 0；dry-run 的退出码等于「会不会发车」。
- **不并发跑同一工作树**（包括 `ci_local` 的那把锁）。
- **不改 `src/**`、不提交、不推送**；本目录只产载荷与树，不产判定逻辑。
- **不解析 YAML**（注册表只做定形扫描）、**不引入新依赖**（只用标准库）。

## 8 需要登记的新版本轴（由 Lead 落 AGENTS 第 55 条的登记表）

> `ab/bank/harness/freeze_manifest.py` 的 `AB_FREEZE_MANIFEST_SCHEMA_VERSION = "1.0"`（冻结清单载荷，**1.0 = 首次建轴**：声明 + 根 + `<sha256>  <仓库相对路径>` 行 + 组合摘要；加键或改语义必须按第 55 条递增，并同批改 README 与测试）。
>
> `ab/bank/harness/scaffold_arms.py` 的 `AB_ARM_MANIFEST_SCHEMA_VERSION = "1.0"`（臂清单载荷，**1.0 = 首次建轴**：基线 / 任务包 / 臂配置 / 首消息四类摘要 + 命令族 + 写入面；同上）。
>
> `ab/bank/harness/run_session.py` 的 `AB_RUN_SCHEMA_VERSION = "1.0"`（一次 run 的结果载荷，**1.0 = 首次建轴**：八键顶层 + 按偏移增量读数；同上）。
>
> 实验集声明自己的轴 `AB_FREEZE_SET_SCHEMA_VERSION = "1.0"` 也一并登记（它与冻结清单轴**独立演进**：
> 声明加了字段不会自动改变清单的形状，反之亦然）。

## 9 与 dgate2 既有工具的关系（**不改它们**）

`dgate2/run-manifest/run_manifest.py`（18 字段 run-manifest；2026-10-21 由 Lead 按实验冻结裁决升到 1.1，
**不是本目录改的**）与 `dgate2/run-record/collect.py`
（T/C/A 三维读数）是**上一代**的冻结 / 读数工具，本目录不修改、也不替代它们：

| 关心的事 | 谁回答 |
| --- | --- |
| 这次实验的输入逐字节相同吗 | `freeze_manifest.py`（本目录） |
| 两臂的起点是同一棵树吗、治理配置是哪五份文件 | `scaffold_arms.py`（本目录） |
| 这一次会话发生了什么（判定 / 原因 / 事后结局 / 树的变化） | `run_session.py`（本目录） |
| 一次 run 的 18 个字段（含 `platform_generation`）与三维分数 | `dgate2/run-manifest/` 与 `dgate2/run-record/`（既有；载荷由 Lead 维护） |

## 10 复现

~~~powershell
& '.venv/Scripts/python.exe' -m pytest -n0 tests/unit/test_ab_harness.py -q
& '.venv/Scripts/python.exe' tools/check_text_conventions.py
~~~

第二条命令不带路径参数：它会用 `git ls-files` 清点**全部**会被提交的文本文件（含本目录的
四个 `.py` 与本 README）。传目录参数会报「工作树里不存在」——它只认文件。

用例覆盖的判据与它钉住的东西：

| 用例组 | 钉住的事 |
| --- | --- |
| `test_glob_match_*` | 忽略规则用段级通配（`**` 递归），不是 :func:`fnmatch` 的「星号吃分隔符」 |
| `test_manifest_lines_*` / `test_combined_digest_*` | 清单按**路径**排序；组合摘要与 `reset-arm.py` 同算法 |
| `test_freeze_*` | 两次生成逐字节相同、无绝对路径 / 时戳；漂移 / 多出 / 少文件 / 版本不认识一律退出 1；日志式声明错误退出 2 |
| `test_scaffold_*` | 臂配置摘要 = 树里那份文件的摘要；未签字占位被点名；越界目标与非空目标被拒；`--check` 抓树漂移与首消息漂移 |
| `test_read_increments_*` | 按**字节偏移**读增量（不依赖前后集合差）；半行与截断各自记成 invalid |
| `test_run_payload_*` | 顶层八键、读数八键；凭据值不进载荷、只记「在不在」；摘要行确定性 |
| `test_run_session_*` | 缺凭据 / 未签字占位 / 臂树漂移 / 沙箱形态 / `DSH_HOME` 各发一个 blocker 且退出 2；全绿时 dry-run 退出 0 且不写任何 run 产物 |

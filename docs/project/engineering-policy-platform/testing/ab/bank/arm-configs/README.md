# A/B 臂配置模板（arm-configs）

**它是什么**：A / B 两臂受治工作区 `.policy/` 的**可提交来源**。此前这两份配置只存在于
`.tmp/bank/arm-configs/{A,B}/`——一次性现场目录、不受跟踪、写着本机绝对路径；换台机器或清掉 `.tmp/`
就没了，冻结清单里那两行摘要也无从重算。这里把配置变成**模板 + 确定性物化**：

- **模板**（本目录的 `A/`、`B/`）受 git 跟踪，每臂**恰好四个文件**，机器中立（路径写成 `${REPO_ROOT}`）；
- **物化副本**（`.tmp/k3/arm-configs/{A,B}/`，构建产物、不提交）由 `../harness/materialize_arm_config.py`
  生成，交给 `../harness/scaffold_arms.py --arm-config` 建臂树。

| 文件 | `scaffold_arms.py` 里的角色 | 有占位符 | 来源 |
| --- | --- | --- | --- |
| `dsh-adapter.yaml` | `adapter` | 有（3 处） | 由 `.tmp` 现场件复制后把绝对路径换成 `${REPO_ROOT}` |
| `hooks.json` | `hooks` | 无 | 原字节复用（本来就没有绝对路径） |
| `tool-registry.local.yaml` | `registry` | 无 | 原字节复用（已审核的那一份） |
| `tool-registry.approved.json` | `registry_approved` | 无 | 原字节复用（与上一行配对的已审核哈希） |

**`approval.json` 故意不在这里**：审批条子有到期时间、绑主体与工具，必须由使用者**按 run 签发**。
模板里放一份签好的条子，等于把一次授权复制成"每次 run 都带着一张迟早过期的条子"。缺它时
`scaffold_arms.py` 写**未签字占位**，`run_session.py` 见到占位就拒绝发车（`approvals_unsigned`）——
这正是想要的失败关闭。

## 1 为什么 README 在上一层

`materialize_arm_config.py` 复制模板目录里的**每一个文件**，而 `scaffold_arms.py` 的
`read_arm_config()` **只接受五个已知文件名**、出现别的文件就拒绝建臂树。所以本 README 放在
`arm-configs/` 而不是 `arm-configs/A/`：放进臂目录它会原样跑进物化副本，`--arm-config` 立刻失败。
四文件契约由 `tests/unit/test_ab_arm_config.py` 钉住。

## 2 占位符与逐字保留

模板里**只认**一个占位符 `${REPO_ROOT}`；未知的 `${...}`、替换后残留的 `${`、模板里出现的绝对路径
（`C:/`、`C:\`、`/Users/`、`/home/`）都按**模板非法**拒绝（退出 1），不猜、不静默保留。

`dsh-adapter.yaml` 的 3 处占位（其余字段与注释**逐字节保留**）：

| 位置 | 模板 | 物化后 |
| --- | --- | --- |
| `rules[0]` | `${REPO_ROOT}/policies` | `<repo-root>/policies` |
| `rules_root` | `${REPO_ROOT}` | `<repo-root>` |
| `pre_evidence.registry_root` | `${REPO_ROOT}/docs/project/engineering-policy-platform/testing/ab/dgate2/configs/` + 臂 | 同路径的绝对写法 |

A 臂用 `configs/before`、B 臂用 `configs/after`——这是两臂唯一的差别，`--repo-root` 之外不写任何
机器相关的东西。`project_root: ..`、`registry: tool-registry.local.yaml`、`batch_ledger` 这类字段都
原样保留：它们的基准是**物化副本所在目录**（臂树的 `.policy/`），不是仓库根。

`tool-registry.local.yaml` / `tool-registry.approved.json` 是**已审核的配对**：注册表本地增量的
`schema_hash` 与这份 approved 哈希一一对应。仓库根 `registry/**` 一个字节都不动，这里也不重新审核；
要改注册表，请走 `python -m enforcement.cli registry --approve --reviewer <name>` 那条路。

## 3 物化（生成物化副本）

以下命令在仓库根执行（`.tmp/k3/` 是构建产物，可随时重建）：

~~~powershell
$py = ".venv/Scripts/python.exe"
$H  = "docs/project/engineering-policy-platform/testing/ab/bank/harness"
$T  = "docs/project/engineering-policy-platform/testing/ab/bank/arm-configs"

& $py "$H/materialize_arm_config.py" --template "$T/A" --target .tmp/k3/arm-configs/A --repo-root .
& $py "$H/materialize_arm_config.py" --template "$T/B" --target .tmp/k3/arm-configs/B --repo-root .
~~~

`--target` 建议是**新建/空**目录：同名文件覆盖，多出来的文件不会被删除（脚本只在 stderr 点名）。
尤其不要把**已签的 `approval.json`** 留在目标目录里——它不是物化产物，却会被 `scaffold_arms.py`
当成有效签字复制进臂树。

### 3.1 物化记录 `materialized.json`

| 字段 | 内容 |
| --- | --- |
| `schema_version` | `"1.0"`（`AB_ARM_CONFIG_MATERIALIZATION_SCHEMA_VERSION`） |
| `template` | `{path, file_count, combined_digest}`：模板的仓库相对路径与组合摘要 |
| `target` | `{path, file_count, combined_digest}`：副本同上（仓库外写 `<outside-workspace>`） |
| `tokens` | `{"${REPO_ROOT}": n}`：本次替换的占位符总数（键恒在，0 也写） |
| `files` | 每文件 `{path, template_sha256, target_sha256, tokens_replaced}`，按路径升序 |

- **组合摘要** = `sha256("\n".join(按路径升序的 "<sha256>  <相对路径>") + "\n")`，与
  `freeze_manifest.py` / `reset-arm.py` 同一个算法（同算法的摘要在不同工具之间可直接核对）；
  模板与副本的摘要**必然不同**——它们本来就不是同一批字节；
- **记录自身不在摘要里**：它是这次物化的读数，不是被物化的输入；算进去就会自己引用自己；
- **确定性**：同一命令两次逐字节相同（没有时戳、没有 run id、没有绝对路径），由测试钉住；
- **载荷自检**：写盘前再查一遍载荷里有没有绝对路径，有就拒绝写并退出 1。

## 4 不要手改物化副本

物化副本是**构建产物**：手改会在下一次物化时被覆盖，还会让冻结清单的摘要与模板对不上。
要改配置就改模板（本目录）→ 重新物化 → 重新 `freeze_manifest.py --write`（如果那份实验集已经冻结）。

## 5 拒绝条件与退出码

| 码 | 含义 | 典型现场 |
| --- | --- | --- |
| 0 | 成立 | 副本与 `materialized.json` 都写好了 |
| 1 | 模板非法 / 事实不成立 | 缺 `dsh-adapter.yaml` 或 `hooks.json`、未知 / 残留占位符、模板含绝对路径、非 UTF-8、不可枚举子目录（**一个字节都不写**） |
| 2 | 参数 / 前置错 | `--repo-root` 下没有 `.git`、`--template` 不是目录、`--target` 是已有文件、`--target` 就是模板或落在模板里 |

## 6 验证（只读）

~~~powershell
$A = ".tmp/k3/arm-configs/A"

# 已审核哈希与本地注册表是否配对（不动 registry/**，不 --approve）
$env:PYTHONPATH = "src"
& .venv/Scripts/python.exe -m enforcement.cli registry --verify `
    --registry "$A/tool-registry.local.yaml" --approved "$A/tool-registry.approved.json"

# 命令族 × 白名单双向互证（0 命中才是干净）
& .venv/Scripts/python.exe tools/approval_allowlist_audit.py --check `
    --registry "$A/tool-registry.local.yaml" --approved "$A/tool-registry.approved.json"

# 本目录契约：模板机器中立、物化四文件、确定性、载荷无绝对路径
& .venv/Scripts/python.exe -m pytest -n0 tests/unit/test_ab_arm_config.py -q
~~~

## 7 已知边界

- **不签审批**：`approval.json` 由使用者按 run 签发；本目录与物化脚本都不生成它；
- **不解析 YAML、不校验 `${REPO_ROOT}/...` 指向的路径是否存在**：物化只做字节替换；
- **不删陈旧文件**：目标目录多出来的文件原样保留，只在 stderr 点名；
- **不跟随符号链接目录**；模板文件必须是 UTF-8 文本；
- **版本轴**：`AB_ARM_CONFIG_MATERIALIZATION_SCHEMA_VERSION = "1.0"` 是**首次建轴**。加键或改语义
  必须按 AGENTS 第 55 条递增，并在**同一次改动**里改本 README 与
  `tests/unit/test_ab_arm_config.py`；轴登记表见 `docs/project/architecture/版本轴登记表.md`
  （由 Lead 落表）。

## 8 相关文件

| 关心的事 | 看哪里 |
| --- | --- |
| 物化脚本与退出码 | `../harness/materialize_arm_config.py` 模块 docstring |
| 臂树怎么建、臂清单字段 | `../harness/README.md`（`scaffold_arms.py`） |
| 冻结清单与作废口径 | `../harness/README.md`（`freeze_manifest.py`） |
| 本目录的回归用例 | `tests/unit/test_ab_arm_config.py` |

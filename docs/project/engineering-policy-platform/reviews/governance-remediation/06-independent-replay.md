# 06 · 独立复跑与对差（第二重验收）

> 角色：V2 independent-replay。**不是修改者**：本轮没有改动仓库里的任何源码 / 测试 / 注册表 / 配置。
> 仪器：**原缺口实验自己写的 harness**（`docs/project/engineering-policy-platform/reviews/governance-coverage-gaps.md` §5 承诺可复现的那一套），
> 不是 V1 自建的 `tools/governance_gap_probe.py`。我按身份约束**没有读** V1 的探针与 `05-verification.md`，
> 所以本报告的每一条结论都只由"原仪器 + 我构造的最小补跑"得出。
>
> 复跑窗口：2026-09-26 01:12–01:19（本地）。基准目录 `.tmp/governance-observation/` 全程只读，收尾时与开工时的副本逐字节相同。

## 0. 这次复跑怎么做（可核对的实验设置）

### 0.1 先复制基准，再在自己的目录里跑

| 项 | 值 |
| --- | --- |
| 只读基准 | `.tmp/regression-replay/original/`（= 开工时 `.tmp/governance-observation/` 的整目录副本，224 个文件） |
| 工作副本 | `.tmp/regression-replay/after/`（与基准同构，所有复跑只写这里） |
| 对差基准 1 | `original/evidence/probe-matrix.json` sha256 `a4ee1cb39fa6467018de7d941a8e6b2c6e7a8cecba18833e21871be6435c628f`（20 656 B） |
| 对差基准 2 | `original/evidence/approval-binding.json` sha256 `9d871c6e956d178ca862eb8c594badbd9676bb51f419627ddbadb48cb15d4edb`（2 259 B） |
| 收尾核对 | `.tmp/governance-observation/` 与 `original/` 逐文件 sha256 比对：**224/224 相同，0 处差异**（我没有碰基准，也没有别人在此期间改它） |

### 0.2 仪器本体没有被我改过

复跑全部使用基准目录里的原脚本（`after/harness/` 是它的字节副本）：

| 脚本 | sha256（前 16 位） | 用途 |
| --- | --- | --- |
| `harness/probe_matrix.py` | `3bc3a30cad10f60d` | 28 条 Hook 级确定性探针 |
| `harness/approval_probe.py` | `8506f4e1f6a17872` | 4 个审批用例（不用模型） |
| `harness/make_policy.py` | `ea5e8a73f20d6fc3` | 生成 `.policy` 三件套 |
| `harness/semantics_check.py` | `d411c57d52020619` | G6/G8 的确定性语义检查（原实验用过的那两条） |

唯一一处**必须**的改动在 `approval_probe.py`（见 §5-O1）：它调 Hook 时不传 `--hooks-config`，
修复后这是失败关闭。我在**自己目录**里留了一份最小补丁副本 `scripts/approval_probe_replay.py`（只加 `--hooks-config .policy/hooks.json`，其余一字未改），
并同时保留"原样跑会怎样"的证据。基准目录里的原件没有被改。

### 0.3 两个目标目录各跑一遍（互为稳健性检验）

`probe_matrix.py` 的 `--project` 原本是个可变量：原始证据实际产自 `probe-target`（用探针 `tool_use_id` 里的 nonce `20260925T153243` 反查确认），
而缺口文档 §5 第 4 条写的是 `--project .`（= `project`）。两个目录的 `src/`、`tests/`、`docs/` **逐字节相同**，只有 `.policy/dsh-adapter.yaml` 的 `project:` 字段名不同。因此我：
- **A 组（与原始证据同口径）**：`--project after/probe-target`；
- **B 组（按文档字面）**：`--project after/project`。

两组的 28 条结论**逐条相同**（见 §2 表最后一列），说明这一变量不影响任何判定。

### 0.4 冻结核验（复跑期间代码没有变）

对 `src/ tests/ tools/ policies/ registry/ adapters/ validation/ knowledge/ api/` 共 **412 个文件**做 sha256：
- 复跑中途快照 `code-hashes.during-replay.txt` 与结束时快照 `code-hashes.end-of-replay.txt` **完全一致**；
- 412 个文件里 **0 个**的 mtime 晚于复跑开始时间。

**结论：代码在复跑窗口内是冻结的，对差结论成立**（若期间有人改代码，本报告作废）。

### 0.5 我没有做的事

- 没有运行 `python tools/ci_local.py`（Lead 独占排他锁）；
- 没有运行 `harness/run_session.py`（需要模型、会起真实会话，任务禁止）；
- 没有读 V1 的 `tools/governance_gap_probe.py`、`tests/integration/test_governance_gap_probe.py`、`05-verification.md`；
- 没有修任何缺陷（发现问题只报告 + 给最小复现）。

## 1. 结论摘要

| 分类 | 计数 | 说明 |
| --- | --- | --- |
| **EXPECTED_FIX** | **5** | 全部落在 28 条探针表里，逐条可指到某个 G 号：G6×2（探针 8/9）、G5×2（探针 15/16）、G12×1（探针 27） |
| 无变化 | 23 | 不需要分类；其中 20 条受判探针与原始记录逐字段一致 |
| **UNEXPECTED_REGRESSION** | **0** | 没有任何"原来正常、现在不对"的行为 |
| **ENVIRONMENT** | **0** | 探针表里没有一行差异可归因于环境；环境事实单列在 §5-O5 |

一句话：**原仪器在修复后的代码上跑出的 28 条结论，与原始记录同口径可比——20 条受判探针 0 条不符（`mismatched=[]`），
5 条观察项按预期改变，其余 23 条逐字段（含 audit 子对象）完全一致。没有发现回归。**
表外另有三项复跑（G2 成对 pre+post、G4 模式化审批、G8 glob 同口径）也全部是预期修复方向——它们不在探针表里，单列在 §3。

同时有 4 件事必须让 Lead 看见，它们**不是**探针表里的行，但会影响"复现/验收"本身：

1. **缺口文档 §5 的 5 条复现命令，今天**没有一条**能照抄跑通**（相对路径上限 off-by-one；第 5 条还多一个失败关闭导致的失效）——§4；
2. **原审批仪器在修复后的代码上跑不动**（G12 的预期副作用，但仪器需要一行最小补丁）——§5-O1；
3. **G2 的原始度量口径（"台账里 post_* = 0"）今天仍然是 0**，因为台账根本没有 post_* 这种 kind；事后核对的证据写在**审计**里——§3.1；
4. 缺口文档里几个关键数字与它自己的产物对不上（104/26 vs 108/27，52 vs 55）——§5-O3。

## 2. 探针矩阵逐条对差（28 行）

分类口径：只有**发生变化**的行才需要三分类（EXPECTED_FIX / UNEXPECTED_REGRESSION / ENVIRONMENT）；
没有变化的行标"无变化"（不需要分类，也不存在"未分类"）。判据列同时给出两个目标目录是否一致。

| # | 探针 | 原始（exit / decision / reason_code） | 现在（exit / decision / reason_code） | 变化分类 | 判据 |
| --- | --- | --- | --- | --- | --- |
| 1 | `allow_write_module` | 0 / allow / allow | 0 / allow / allow | 无变化 | 逐字段一致（含 audit 子对象） |
| 2 | `allow_write_controller_clean` | 0 / allow / allow | 0 / allow / allow | 无变化 | 同上（两边都记 `matched_rules=[ARCH-001@1]` 但结论 allow） |
| 3 | `block_arch_violation_write` | 2 / block / policy_block | 2 / block / policy_block | 无变化 | 同上 |
| 4 | `block_arch_violation_edit` | 2 / block / policy_block | 2 / block / policy_block | 无变化 | 同上 |
| 5 | `block_path_escape_relative` | 2 / — / context_error | 2 / — / context_error | 无变化 | 同上 |
| 6 | `block_path_escape_absolute` | 2 / — / context_error | 2 / — / context_error | 无变化 | 同上 |
| 7 | `block_unknown_tool`（MCP） | 2 / — / context_error | 2 / — / context_error | 无变化 | 同上 |
| 8 | `observe_bypass_dynamic_import` | 0 / allow / allow | **2 / block / policy_block** | **EXPECTED_FIX** | G6/R3：`importlib.import_module("repository")` 现在解析出 `repository`，命中 ARCH-001@1，`executed=false`；两侧目录一致 |
| 9 | `observe_bypass_relative_import` | 0 / allow / allow | **2 / block / policy_block** | **EXPECTED_FIX** | G6/R3：`from . import repository` 解析成 `.repository` 并命中；两侧目录一致 |
| 10 | `allow_read_inside` | 0 / — / — | 0 / — / — | 无变化 | 逐字段一致 |
| 11 | `block_read_outside` | 2 / — / context_error | 2 / — / context_error | 无变化 | 同上 |
| 12 | `block_exec_pwsh_without_approval` | 2 / — / permission_denied | 2 / — / permission_denied | 无变化 | 同上 |
| 13 | `block_exec_composition` | 2 / — / permission_denied | 2 / — / permission_denied | 无变化 | 同上（分号组合命令仍被拦） |
| 14 | `block_exec_run_code` | 2 / — / permission_denied | 2 / — / permission_denied | 无变化 | 同上 |
| 15 | `observe_pwsh_workdir_root_absolute` | 2 / — / **enforcement_param_error** | 2 / — / **permission_denied** | **EXPECTED_FIX** | G5/R4：等于项目根的 `workdir` 通过范围校验，落到下一道闸（缺 `shell.exec` + 无审批）；两侧目录一致 |
| 16 | `observe_pwsh_workdir_dot` | 2 / — / **enforcement_param_error** | 2 / — / **permission_denied** | **EXPECTED_FIX** | G5/R4：`workdir='.'` 归一化为项目根，同上 |
| 17 | `observe_pwsh_workdir_subdir` | 2 / — / permission_denied | 2 / — / permission_denied | 无变化 | 逐字段一致 |
| 18 | `block_undeclared_layer` | 2 / — / context_error | 2 / — / context_error | 无变化 | 同上 |
| 19 | `block_unknown_event` | 2 / — / context_error | 2 / — / context_error | 无变化 | 同上 |
| 20 | `observe_replay_first` | 0 / — / event_replay | 0 / — / event_replay | 无变化 | exit 0 表示第一次放行；`audit` 子对象里显示 event_replay 是仪器取数口径（第 20/21 行共用同一个 `tool_use_id`，索引取到后一次记录），两侧一致 |
| 21 | `observe_replay_second` | 2 / — / event_replay | 2 / — / event_replay | 无变化 | 幂等护栏未被放宽 |
| 22 | `observe_post_tool_use`（孤立 Post） | 0 / — / — | 0 / — / — | 无变化 | 两侧审计里都有且仅有 1 条 `stage=post_evidence` / `stage_note=post_without_pre`（"没有 pre 基线就只记录、不编造结论"） |
| 23 | `fail_closed_missing_config` | 2 / — / startup_error | 2 / — / startup_error | 无变化 | 逐字段一致 |
| 24 | `fail_closed_broken_config` | 2 / — / startup_error | 2 / — / startup_error | 无变化 | 同上 |
| 25 | `fail_closed_timeout_inequality` | 2 / — / wiring_error | 2 / — / wiring_error | 无变化 | 同上 |
| 26 | `fail_closed_audit_unwritable` | 2 / — / startup_error | 2 / — / startup_error | 无变化 | 同上 |
| 27 | `observe_no_hooks_config` | 0 / allow / allow | **2 / — / wiring_error** | **EXPECTED_FIX** | G12/R2："接线自检缺席即通过"被改掉；现在明说"没有提供 hooks.json 路径，无法证明 dsh 会注册本 Hook" |
| 28 | `observe_missing_pythonpath` | 1 / — / — | 1 / — / — | 无变化 | 模块导入失败仍是 exit 1（由插件负责翻译成失败关闭），两侧一致 |

**仪器自判**：两次复跑的 `mismatched` 都是 `[]`（20 条受判探针全部符合脚本自己的预期），
退出口 `[harness] mismatched=[]`，脚本退出码 0。原始记录同样是 `mismatched=[]`——**受判面没有出现任何松动**。

**审计记录条数的一个附带变化（不是回归）**：同一批探针写出的审计记录 40 → 38 行，
但带 `action_id` 的记录 21 → 36 行（空 `action_id` 的 19 → 2）。
即拒绝路径现在也能给出动作身份，属于 R3"跳过/拒绝要可追溯"的可见性收益；逐条对差已确认结论未变。

## 3. 四条关键原始证据的复跑（缺口文档的数字来源）

### 3.1 G2 · "动手后核对从未执行"——**台账口径没变，现象已修，但要看审计**

原始数字（我从产物里重新数出来的，不是复述文档）：

| 度量 | 原始 | 现在 | 判读 |
| --- | --- | --- | --- |
| `project/.policy/audit.enforcement-ledger.jsonl`（真实会话台账） | 108 行 = claim/grant/pre_decision/pre_state 各 27，**post\* = 0** | 未重跑真实会话（禁止），台账 **仍然没有** post\* 这种 kind | 口径本身失效：台账 schema 里从来没有 post\* |
| `probe-target/.policy/audit-probes.enforcement-ledger.jsonl` | 24 行（6×4），post\* = 0 | 36 行（新增 12 = 3×4），**post\* = 0** | 同上 |
| 探针审计 `stage` 分布 | `{pre_decision:10, undefined:29, post_evidence:1}` | `{pre_decision:9, undefined:28, post_evidence:1}` | 那 1 条 `post_evidence` 在两边都是 `post_without_pre`（探针 22 没有 pre 基线） |

**所以照原口径回答"现在还有吗"：还有 0 条。** 但这不是"没修"——事后核对的证据写在**审计**里（`stage=post_evidence` / `final_decision`），
台账里没有这类记录是设计，不是缺口。要证明 G2 真的修好，必须换一个有 pre 基线的量。我构造了成对复跑（`scripts/g2_post_pair.py`，输出 `after/replay-output/g2-post-pair.json`）：

| 用例 | 输入 | 结果 |
| --- | --- | --- |
| A 组（pre 放行 → 运行时**真的**写了文件 → post） | 同一 `tool_use_id` | Pre exit 0；Post **exit 0**；审计出现 `stage=post_evidence`，`status=validated`，四个验证器全过（`content_matches` / `target_exists` / `file_syntax` / `diff_recorded`），`files[0].changed=true`；随后 `stage=final_decision`：`outcome=delivered`、`post_status=validated` |
| B 组（pre 放行 → 运行时**没写**文件 → post） | 同一 `tool_use_id` | Pre exit 0；Post **exit 2** `[policy] POST-CHECK repair_required (post_check_failed)`，detail：`content_matches: src/probe_g2_missing.py 在执行后不存在：动作没有产生它声称的结果` |
| C 组（只有 post、没有 pre） | 孤立 `tool_use_id` | exit 0，审计 `post_evidence` + `stage_note=post_without_pre`（与原始探针 22 完全同形） |

即：**"动手后核对"现在真的会跑，而且能抓到"声称成功其实没写"**；台账 kinds 是 `{claim, grant, pre_decision, pre_state, execution}`，不含 post\*。
另一半（真实会话里会不会被触发）是静态事实：`src/adapters/dsh/policy-hook.plugin.mjs:141` 已注册 `ctx.on('tools/post-execute', …)`，
与 pre 成对出现，文件头 15–19 行写明这就是 G2 的修法。**但我不能跑真实 dsh 会话**（任务禁止 `run_session.py`），
所以"生产路径上 PostToolUse 真的被转发"这一环，我这一侧只有静态证据 + Python 侧行为证据，没有端到端证据——这是本次复跑最大的证据缺口，如实列出。

### 3.2 G4 · 审批绑定——原仪器**看不见**修复，修复本身**可用**

先给两个必须分清的结论：

**(a) 冻结的原仪器对 4 个用例的结论：与原始记录逐条相同（无变化）**

| 用例 | 原始 | 现在（打了 §5-O1 那一行最小补丁后复跑） |
| --- | --- | --- |
| 首次无审批 | exit 2 `approval_required` | exit 2 `approval_required` |
| A 审批与调用逐字一致 | exit 0 | exit 0 |
| **B 换调用编号、同命令** | exit 2 `approval_invalid` | **exit 2 `approval_invalid`（没变）** |
| C 同编号、换命令 | exit 2 `approval_invalid` | exit 2 `approval_invalid` |
| D 主体角色不足 | exit 2 `permission_denied` | exit 2 `permission_denied` |

**B 没通过 ≠ 回归**：原仪器签的是 `binding=action` 的**单次**审批（`action_hash` + `action_id` 逐位绑定），
修复后的规则明确要求"单次绑定必须逐位一致"（`src/enforcement/approvals.py:238-247`），这是**保留**的严格档，不是被放松。
所以这一行**不是 UNEXPECTED_REGRESSION**，而是"原仪器的可观测面上没有第二种审批档位"。

**(b) 换平台自己的模式化审批档位后，G4 的修复确实可用**（我的补充复跑 `scripts/g4_pattern_approval.py`，输出 `after/replay-output/g4-pattern-approval.json`）

用平台自己的模型签发一条 `binding=pattern`、`param_patterns={"command": "python -m pytest tests -q"}`、`max_uses=3` 的审批：

| 用例 | 结果 | 说明 |
| --- | --- | --- |
| 无审批 | exit 2 `approval_required` | 门禁仍在 |
| A 第一次调用 | **exit 0** | 模式化审批可直接用于真实调用 |
| F 同一个 `tool_use_id` 再来一次 | exit 2 `action_replay` | **重放护栏没有被放宽**（修复计划要求的"按 action_id 的重放拦截保持不变"） |
| **B 换调用编号、同命令** | **exit 0** | ← **G4 的核心修复：调用编号不再让条子作废** |
| C 换命令、同编号空间 | exit 2 `approval_invalid`（"参数 'command' 的取值不匹配审批模式…整段匹配"） | 模式边界有效 |
| E 第三次调用（同命令、新编号） | exit 0 | 额度内可重复 |
| G 第四次调用 | exit 2 `approval_invalid`（"次数上限已用尽（已用 3/3 次）"） | 次数上限有效 |
| D 主体只有 developer 角色 | exit 2 `permission_denied` | 权限分离未被模式审批绕过 |

台账里对应 `approval_used ×3`，与 `max_uses=3` 一致。

**判读**：G4 的修复**存在、可用、且没有把单次绑定/重放/权限三件事一起放松**。
原仪器之所以看不到，是因为它只签单次绑定——这是"仪器覆盖面"问题，不是"修复缺失"。

### 3.3 G5 · 工作目录等于项目根——**修好了**

| 用例 | 原始 | 现在 |
| --- | --- | --- |
| `workdir` = 项目根绝对路径 | exit 2 `enforcement_param_error`，detail `[path_out_of_scope] …路径不在仓库 <repo> 之内，拒绝处理: '<repo>'` | exit 2 `permission_denied`，detail 变为 `check permissions: 缺少权限 ['shell.exec']` + `check approval: approval_required` |
| `workdir` = `.` | exit 2 `enforcement_param_error`，detail `路径必须指向仓库内的文件: '.'` | 同上 |
| `workdir` = `src`（对照） | exit 2 `permission_denied` | exit 2 `permission_denied`（未变） |

**验收口径达成**：不再出现笼统的 `enforcement_param_error`；路径校验放行后落到下一道闸（缺 `shell.exec` + 无审批）。
注意后一道闸仍然拦着——**"参数对了"不等于"能跑命令"**，这一点没有被混淆。

### 3.4 G8 · `**/` 零层匹配——**修好了，且两个实现现在同口径**

用**原仪器自带的** `harness/semantics_check.py`（当前代码上运行）：

```text
glob_match('**/*.md', 'README.md')             = True      # 原始：False
glob_match('**/*.md', 'docs/architecture.md')  = True
glob_match('**/*.py', 'cli.py')                = True      # 原始：False
glob_match('**/*_controller.py', 'inventory_controller.py') = True
```

我另外把"同一语义两处实现"并排跑（`scripts/g8_glob.py` → `after/replay-output/g8-glob.json`）：
`adapters.dsh.adapter.glob_match` 与 `validators.globs.glob_match` 在 7 组输入上**结论全部相同**（原始记录里两者是刻意分歧的）。

同一脚本还给出了 G6 的原始度量（`proposed_dependencies`）现在的取值：

| 写法 | 原始记录 | 现在 |
| --- | --- | --- |
| `from repository import InventoryRepository` | `('repository',)` | `('repository', 'repository.inventoryrepository')` |
| `importlib.import_module("repository")` | `('importlib',)` | `('importlib', 'repository')` |
| `__import__("repository")` | `()` | `('repository',)` |
| `from . import repository` | `()` | `('.repository',)` |
| `from mypkg.repository import R` | `('pkg',)`（原记录示例） | `('mypkg.repository', 'mypkg.repository.r')` |

## 4. 缺口文档 §5 的 5 条复现命令，今天还能不能跑

文档承诺"全部命令在工作区根执行"，第 2 步之后 `cd .tmp/governance-observation/project`。我逐条核验（不改基准目录：第 1 条在 `after/` 上用同一命令跑）：

| 步骤 | 文档命令（要点） | 能不能跑 | 退出码 / 卡在哪 | 原因 |
| --- | --- | --- | --- | --- |
| 0 | `python tools/dsh_sandbox_loop.py --require-dsh` | **我没有跑** | — | Lead 的 `ci_local.py --full`（pid 41560，01:11:43 起）仍持有 `.tmp/ci-local.lock`；AGENTS.md 明确同一工作树并发跑会争 `.tmp/` 固定路径并跑出假红，我只报告不抢跑 |
| 1 | `make_policy.py --project .tmp/governance-observation/project --repo .` | **能**（等价改道 `after/`） | exit 0 | 照抄会覆写基准目录的 `.policy/`，我在基准副本上跑：生成的 `dsh-adapter.yaml`/`hooks.json` 与原始**逐字节相同**，`patch.yml` 只差 `projectDir` 一行（因为项目目录换了位置） |
| 2 | 接线自检 `--self-check`（`PYTHONPATH=<仓库>\src`） | **能** | exit 0，stderr `[policy] self-check ok` | 与文档一致；顺带核验：自检**不写审计**（前后都是 169 行） |
| 3 | `run_session.py --project . --repo ..\..\..\..` | **不跑** | 相对路径也不成立：`..\..\harness\run_session.py` 解析到 `.tmp/harness/`（不存在）；`--repo ..\..\..\..` 解析到 `C:\Users\ZNM\Downloads`（仓库的**上一层**） | ① 需要模型且会起真实会话（任务禁止）；② 路径 off-by-one |
| 4 | `probe_matrix.py --project . --repo ..\..\..\..` | **照抄跑不通** | 退出码 2：`can't open file '…\.tmp\regression-replay\harness\probe_matrix.py': [Errno 2] No such file or directory` | 同样的 off-by-one：harness 实际在 `.tmp/<实验目录>/harness/`，命令写成了上一级 |
| 5 | `approval_probe.py --source . --repo ..\..\..\..` | **照抄跑不通（三个独立原因）** | ① 同上路径问题；② 修好路径后仍然 exit 2：首次调用被 `wiring_error` 拦下，脚本报 `拿不到 action_hash，实验无法继续` | ① 路径 off-by-one；② G12 修复后"不传 `--hooks-config`"不再放行（§5-O1）；③ **危险**：若只把 `--repo` 改成 `.` 而不加 `--target`，脚本会 `shutil.rmtree` 默认 target = `.tmp/governance-observation/approval-probe`，把本次对差的原始证据删掉重建（`approval_probe.py:81,86-89`） |

**对"可复现"承诺的判断**：文档 §5 给出的命令**今天不能照抄复现**；其中 1、2 条可跑通，4、5 条需要把
`..\..\harness\` 改成 `..\harness\`、`--repo ..\..\..\..` 改成 `--repo ..\..\..`，第 5 条还要补 `--hooks-config` 与显式 `--target`。
我把正确的等价命令与产物都留在 `.tmp/regression-replay/` 里，并用它完成了本次对差。

## 5. 额外观察（不改本轮范围，但必须留档）

### O1 · 原审批仪器在修复后的代码上跑不动（G12 的预期副作用）

- 现象：`approval_probe.py` 的 `run_hook` 调 Hook 时只传 `--config` 与 `--audit`（`approval_probe.py:37-47`）。
  修复前 `check_wiring()` 在没有 hooks 配置时直接返回通过；现在这是 `wiring_error`（exit 2）→ 仪器拿不到 `action_hash`，整场实验中止（总退出码 2）。
- 最小复现（**必须显式 `--target`**，否则会删原始证据目录）：
  ```powershell
  python .tmp/governance-observation/harness/approval_probe.py `
      --source .tmp/regression-replay/after/project --repo . `
      --target .tmp/regression-replay/after/approval-probe `
      --out .tmp/regression-replay/after/replay-output/approval-binding.after.json
  # => exit 2；stderr: [probe] 拿不到 action_hash，实验无法继续；首次调用结果={'exit_code': 2,
  #    'reason': '[policy] BLOCKED (wiring_error)', ...}
  ```
- 判读：这是 **G12 修复的正确后果**（"接线自检不接受缺席"），不是产品回归；但**它让"原始仪器原样可复跑"这件事不再成立**。
  需要 Lead 决定：是把这条记进缺口文档的复现节（注明需要一行补丁），还是把 `--hooks-config` 作为 `.policy` 模板的一部分写进 harness 的调用约定。
- 我的处置：在自己目录里留了最小补丁副本并在报告里公开差异；基准目录里的原件未动。

### O2 · G2 的度量口径选错了仪器

"台账里 post\* 记录 0 条"是缺口文档 G2 的核心证据。复跑证明：**修复后这个数还是 0**，因为
`src/enforcement/ledger.py` 的 kind 集合是 `claim / claim_released / grant / grant_used / pre_state / pre_decision / approval_used / approval_use_released / execution`，
**根本没有 post\* 这种 kind**；事后核对的证据进的是**审计**（`AuditStage.POST_EVIDENCE` / `FINAL_DECISION`，见 `src/enforcement/models.py:304`）。
如果只按原口径验收，会得出"G2 没修"的错误结论；正确的量是"成对 pre+post 时的 `stage=post_evidence` 及其 `status`"（§3.1）。

### O3 · 缺口文档的数字与它自己的产物对不上（不影响结论方向）

| 文档里的数字 | 我在原始产物里数出来的 | 差异 |
| --- | --- | --- |
| "受控执行台账 104 条记录" | `original/project/.policy/audit.enforcement-ledger.jsonl` = **108** 行 | +4 |
| "26 次受治理动作" | 108/4 = **27** 个 claim（27 次动作） | +1 |
| "52 条受治理审计记录" | `original/project/.policy/audit.jsonl` 中 `governed=true` = **55** 行 | +3 |
| "42 条的 matched_rules 为空" | matched 为空的是 **44** 行（另有 11 行 matched=`[ARCH-001@1]`） | +2 |

最可能的解释是文档写于实验进行中途的快照（例如 26 次动作时 104 行）。**方向不受影响**（这些数字都支持"只有 1 条规则在查、事后从未核对"），
但"缺口文档的数字必须能由产物重算"这条纪律在这里没有做到，建议 Lead 在收口时用产物重算一遍并注明取数时点。

### O4 · 修复带来的新审计字段（可见性 / 留痕），在原产物里是 0

| 字段 | 原始 `project/audit.jsonl`（169 行） | 原始 `probe-target/audit-probes.jsonl`（40 行） | 复跑 `after/project/audit-probes.jsonl`（38 行） |
| --- | --- | --- | --- |
| `checker_scope_note`（"跳过不等于通过"） | 0 | 0 | 10 |
| `skipped_rule_count` | 0 | 0 | 10 |
| `skipped_reason`（按 checker 计数） | 0 | 0 | 10 |
| `context_injection`（注入来源 + sha256 + bytes） | 0 | 0 | 1（AGENTS.md，1 574 B，带 sha256） |

这与 R3（跳过要可见）和 G11（注入留痕）的修复方向一致，且**没有改变任何一条判定结论**（§2）。

### O5 · 环境事实（与代码无关，但限制了我能证到什么）

- 本机 `shutil.which("pwsh")` 为 `None`、`bash` 走 WSL 被拒（N6 已记录）：所以**"受治理会话能不能真的跑测试"这件事本次仍然没有被证明**，
  §3.2(b) 证明的只是"审批链路的绑定不再因运行时编号失效"。
- 第 0 条命令（真实 dsh 沙箱闭环）本次**未跑**：`ci_local.py --full` 的排他锁全程被持有（pid 41560）。
- 探针表里**没有**任何一行差异可归因为环境：28 行中有 20 行受判、全部命中脚本自己的预期。

## 6. 两个独立仪器是否一致：我能给的和不能给的

**能给的明确判断**（我这一侧，仪器 = 原缺口实验自带的 harness）：

1. 28 条探针的结论集与原始记录**同口径可比**：受判 20 条**零不符**，观察 8 条中 5 条按预期变化、3 条一致（合计 5 条 EXPECTED_FIX、23 条无变化）；
2. 5 处变化**全部**能指到具体 G 号（G6×2、G5×2、G12×1），**0 处"本来正常的现在不对了"**；表外的 G2/G4/G8 复跑同样是修复方向，且各自给了最小复现；
3. G2/G4/G5/G8 四条原始证据，按**新的正确口径**全部显示修复生效（§3）；
4. 我没有发现任何证据表明本轮修复放松了失败关闭（5 条故障注入探针逐字段不变）、放宽了重放护栏（探针 21 + 我的 F 用例）、
   或把"跳过"当成"通过"（新审计字段显式标注）。

**不能给的**：**"与 V1 逐条结论一致"这个判断我给不了**——按身份约束我没有读 V1 的探针与 `05-verification.md`，
读了就不叫独立仪器了。这是独立性换来的代价，不是遗漏。为了让 Lead 能用一次机械比对完成这件事，我把对差做成了可比对的结构：

- 行键：探针 `id`（28 个，与 `probe_matrix.py` 里的 `PROBES[].id` 同名）；
- 列：`exit_code` / `audit.decision` / `audit.reason_code` / `audit.matched_rules` / `audit.executed`；
- 数据：`after/replay-output/probe-matrix.after-probe-target.json`（我）与 `original/evidence/probe-matrix.json`（原始）；
- 结论键：G 号 + 一句话结论（§3 四张表）。

只要 V1 的报告里每条结论都能落到"G 号 + 探针 id/用例名"，两边的差异就只是数据结构比对，不再需要判断。
**如果 Lead 要我在本报告冻结之后再做一次逐条对差（允许我事后读 V1 结论），我可以新增一节并明确标注"事后追加、不回溯污染本报告结论"。**

## 7. 我没做成的事（及原因）

| # | 没做成的事 | 原因 | 影响 |
| --- | --- | --- | --- |
| 1 | 没跑 `harness/run_session.py`（真实受治理子会话） | 任务明令禁止：需要模型、会起真实会话 | G1/G7/G11 的**真会话**路径本次没有复跑；PostToolUse 在生产路径上"真的会被转发"只有静态证据（§3.1） |
| 2 | 没跑 §5 第 0 条（`dsh_sandbox_loop.py --require-dsh`） | Lead 的 `ci_local --full` 全程持锁；并发会争 `.tmp/` 固定路径（AGENTS.md） | "基线闭环今天还绿不绿"这一条只能由 Lead 在 `ci_local` 里顺带证明 |
| 3 | 原仪器 `approval_probe.py` 无法原样跑 | §5-O1（G12 的正确副作用） | 我用最小补丁副本拿到了 4 个用例的结论；补丁已公开 |
| 4 | 没能给出"与 V1 逐条一致"的判断 | 独立性约束（不读 V1 结论） | 已给出机械比对的方法与数据（§6） |
| 5 | 没有验证"dsh 真实运行时确实会调用 post-execute 钩子" | 同 #1 | 这是本次复跑最大的证据缺口，明确列为未证事项 |

## 附：证据清单（全部在 `.tmp/` 下，构建产物不提交）

| 路径 | 内容 | sha256（前 16 位） |
| --- | --- | --- |
| `regression-replay/original/` | 基准只读副本（224 文件） | 逐文件与 `.tmp/governance-observation/` 比对 0 差异 |
| `regression-replay/after/replay-output/probe-matrix.after-probe-target.json` | 复跑 A 组（与原始证据同口径） | `af1c98ec02d68b09` |
| `regression-replay/after/replay-output/probe-matrix.after-project.json` | 复跑 B 组（按文档 `--project .`） | `c3b79649109e0b25` |
| `regression-replay/after/replay-output/approval-binding.after.json` | 原仪器 4 用例（最小补丁后） | `fecf0a9a48b3e322` |
| `regression-replay/after/replay-output/g2-post-pair.json` | G2 成对 pre+post 实验原始输出 | `7f9224a77f42644e` |
| `regression-replay/after/replay-output/g4-pattern-approval.json` | G4 模式化审批实验原始输出 | `7462eae9389013b2` |
| `regression-replay/after/replay-output/g8-glob.json` | G8 两处 glob 实现并排结果 | `45d7ae858a7c582f` |
| `regression-replay/after/replay-output/diff-table.md` | §2 对差表（可再生成） | `6d4c8822896f76d6` |
| `regression-replay/scripts/approval_probe_replay.py` | 审批仪器的最小补丁副本 | `439a39b4354ae920` |
| `regression-replay/scripts/{g2_post_pair,g4_pattern_approval,g8_glob,lock_probe}.py` | 我写的补跑脚本（只写 `.tmp/`） | 见目录 |
| `regression-replay/code-hashes.{during,end-of}-replay.txt` | 412 个源码/测试/配置文件的哈希快照（冻结证据） | 两次完全相同 |

生成命令（可重跑）：`after/harness/` 里的脚本 + `after/replay-output/diff-table.md` 的生成逻辑在 `scripts/` 与本节表中均已给出；
全流程只依赖系统 python 3.13，不写仓库、不碰 `.venv`。

# 治理覆盖缺口 · 独立验收报告（V1）

> 对象：`docs/project/engineering-policy-platform/reviews/governance-coverage-gaps.md` 的 13 项缺口
> 与 `00-remediation-plan.md` 第 3 节的验收口径。
> 本报告的判定只来自被测系统自己写出的产物：进程退出码、审计 / 台账 JSONL 的实际内容、
> 插件源码的静态事实、CLI 的 JSON 输出。**不复用实现者写的测试作为唯一证据**。
>
> 状态：**已完成**。修前基线（13/13 与 before 预期一致）与修后验收（12/13 与 after 预期一致、
> 连续两遍完全一致）都已跑完，逐项判定见 §4，残留见 §6。
> 判定口径与证据都写在正文里：只报亲眼看过的输出，不做“应该/大概/已修复”这类陈述。

## 1. 验收对象与状态快照

| 项 | 值 |
| --- | --- |
| 修前快照 | `.tmp/governance-baseline.zip`（= `git archive HEAD`），sha256 `ffc1612a72a02749eb3da3ada2c454cbedd091c6f25fc371906b2ebb8ad32a22`，11371895 字节 |
| 修前快照的 commit | `4f9f2e15731ccfbf6615dfb90d31cd2982ffc5c1`（2026-09-24T22:22:03+08:00） |
| 修前快照解压位置 | `.tmp/verifier/baseline/`（只读证据，全程未改） |
| 修后快照（被检对象，第 3 轮） | 工作树：HEAD `4f9f2e15731ccfbf6615dfb90d31cd2982ffc5c1`（与修前快照同一 commit，本轮全部改动都未提交）、`git diff HEAD \| git hash-object --stdin` = `30053031c3987ecaa996f21d6728c09e3b4120a7`；44 个已跟踪文件被修改（3417 增 / 215 删）、18 个新文件未跟踪 |
| 探针工作目录 | `.tmp/verifier/probe/<live\|baseline>/run-<run_id>/`（构建产物，可随时重建；**每次运行一个唯一子目录**，见 §2.1） |

**多轮快照、多份结论（留痕，不覆盖）**：本报告自己立的方法论要求"快照身份变了必须留痕"，
所以每一轮都写下来：

| 轮次 | 快照身份（`git diff HEAD \| git hash-object --stdin`） | 改动规模 | 探针结果 | G07 判定 |
| --- | --- | --- | --- | --- |
| 第 1 轮（首次冻结） | `1bf25c1779827cf86ffdd2b7d7597606b7488d93` | 38 个已跟踪文件改动（3258 增 / 204 删） | 12/13（唯一红项 G07） | **PARTIAL** |
| 第 2 轮 | `e13673c3c1fee143e3df445e35f073d16657f4e3` | 39 个已跟踪文件改动（3270 增 / 205 删） | **13/13** | **FIXED** |
| 第 3 轮（**本报告最终结论**） | `30053031c3987ecaa996f21d6728c09e3b4120a7` | 44 个已跟踪文件改动（3417 增 / 215 删） | **13/13**（与第 2 轮逐项相同） | **FIXED**（未变） |

证据文件（都可复跑）：第 1 轮 `.tmp/verifier/probe-live-after-repeat2.json`；第 2 轮
`.tmp/verifier/probe-live-after-round2.json`；第 3 轮 `.tmp/verifier/probe-live-after-round3.json`；
反向对照 `.tmp/verifier/probe-g07-revert.json`（第 2 轮）与 `.tmp/verifier/probe-g07-revert-round3.json`（第 3 轮重做）；
修前基线 `.tmp/verifier/probe-baseline-before.json`。

**第 1 轮 → 第 2 轮**之间只有两处变化（用 `git diff --no-index` 逐文件对照确认）：

1. `src/adapters/dsh/hooks.py` +10 行：受治理动作的审计记录新增 `layer_defaulted` 与
   `layer_matched_pattern`（取自冻结接口 `config.layer_resolution(event.file)`）；
   与第 1 轮的同名文件相比差异就是 `1 file changed, 10 insertions(+)`。
2. `tools/README.md` +2/-1 行：登记 `governance_gap_probe.py`；并更新 `dsh_sandbox_loop.py`
   那一行的环境跳过说明（仓库一致性门禁的漂移项）。

第 1 轮的判定与证据**没有被覆盖**：除 G07 外的 12 项在两轮里结论与 facts 完全相同（同一份探针、同一套
before/after 预期）；G07 的变化原因与反向对照见 §4。

**第 3 轮的变化范围（不是修 G 缺口，是 ci_local 全量门禁找出的连带修复）**：
6 个已跟踪文件新进入"已修改"列表，另有 1 个退出该列表（下表）；这轮**没有触碰任何被测行为**，
13 项判定与 facts 逐项不变（见 §4）。

| 文件 | 第 3 轮的变化 |
| --- | --- |
| `tools/build_learning_notebook.py` | 新增 `write_hooks_config()` / `HOOKS_CONFIG_PATH`，3 处 CLI 调用补 `--hooks-config`；Phase 2 的 markdown 命令行示例同步 |
| `docs/project/architecture/tech-detail/notebooks/nb_cells/nb02.py` | 同样补 `--hooks-config`；依赖断言改成含点分路径的新值（G6 语义变更）；cell 11 从"数记录条数"改成**语义断言**（每次调用有没有 pre 与 post） |
| `docs/project/learning/phase-2/walkthrough.{ipynb,py}`、`docs/project/architecture/tech-detail/notebooks/02-dsh-Hook-内部流程.{ipynb,py}` | 手册产物按内容源重新生成 |
| `docs/project/architecture/tech-detail/notebooks/04-受控执行.ipynb` | **退出**"已修改"列表：重新生成后与 HEAD 一致（此前带着 Jupyter 运行痕迹，会话开始前就在工作树里） |
| `tools/README.md` / `README.md` / `.github/workflows/phase-8.yml` / `tools/ci_local.py` | 登记探针与 `wiring` 子命令、把 wiring 报告接进 CI 与本地门禁 |

**hooks.py 在第 2、3 轮之间逐字节未变（Lead 特别要求核对）**：`git hash-object src/adapters/dsh/hooks.py`
= `cee405ad47d0d311f00cc4949b87bc803be38314`（56176 字节）；这个 blob 摘要的前 7 位 `cee405a`
在第 2 轮与第 3 轮的 `git diff --no-index .tmp/verifier/rehearsal/src/adapters/dsh/hooks.py src/adapters/dsh/hooks.py`
输出里**完全相同**（两轮都是 `index 879cd60..cee405a 100644`、都是 `1 file changed, 10 insertions(+)`）。
git 的 index 行是**内容寻址**的 blob 摘要，所以这就是"两轮之间该文件没被改过"的字节级证据。
因此第 2 轮的 G07 反向对照结论对第 3 轮仍然成立；除此之外我又用**第 3 轮的树**重建了一次对照副本
（只把 `hooks.py` 换回第 1 轮那份，其余文件取自第 3 轮），重跑仍然 `[FAIL] G07`（§4）。

**被检快照的边界（Lead 要求写明）**：工作树里有一批**与本轮无关**的既有改动
（`docs/project/engineering-policy-platform/designs/**`、`docs/project/architecture/**`、
`docs/project/engineering-policy-platform/README.md`）。判据不是"我觉得"，而是**会话开始时的证据**：
本轮任何写者落地代码之前，`git status --short` 里就已经只有这些文档，`src/ registry/ adapters/ tests/` 一条都没有；
现在这些文档的修改量与那次完全一致。因此"被检快照"限定为**本轮的改动集**：

| 工作流 | 本轮改动 |
| --- | --- |
| T1 hook-chain | `src/adapters/dsh/policy-hook.plugin.mjs`、`src/adapters/dsh/hooks.py`、`src/adapters/dsh/README.md`、`tests/contract/test_policy_hook_chain.py`(新)、`tests/unit/test_hook_skip_visibility.py`(新) |
| T2 channel-inventory | `src/adapters/wiring.py`(新)、`src/adapters/cli.py`、`tests/contract/test_wiring_inventory.py`(新)、`tests/unit/test_wiring.py`(新) |
| T3 rule-fidelity | `src/adapters/dsh/adapter.py`、`src/policy/checkers.py`、`adapters/dsh/manifest.yaml`、`adapters/approved.json`、`tests/contract/test_tool_table_drift.py`(新)、`tests/contract/test_dsh_adapter.py`、`tests/integration/test_dependency_path_consistency.py`(新)、`src/validators/globs.py` |
| T4 enforcement-availability | `src/enforcement/*.py`（含新 `codecheck.py`）、`src/policy/context.py`、`src/policy/models.py`、`registry/tool-registry.yaml`、`registry/tool-registry.approved.json`、`tests/contract/test_approval_binding_modes.py` 等 4 个新测试、`tests/integration/test_enforcement_cli.py`、`tests/enforcement_support.py` |
| Lead（冻结前收口） | `tools/ci_local.py`、`tools/dsh_sandbox_loop.py`、`README.md`、`.github/workflows/phase-8.yml`、`src/adapters/dsh/hooks.py` 的 G5 错误码透传（§5.1）、`tests/integration/test_dsh_hook.py` |
| V1 verifier（本报告） | `tools/governance_gap_probe.py`(新)、`tests/integration/test_governance_gap_probe.py`(新)、`docs/project/engineering-policy-platform/reviews/governance-remediation/` |

其余修改（`docs/**`）是先前就存在的，不在任何本轮写域内，也不参与本报告的判定。

**方法论声明（Lead 要求写进报告）**：验收对象是**停止写入后的稳定快照**。
修后扫描的身份记录方式：`git status --porcelain`（含未跟踪文件）+ `git diff HEAD | git hash-object --stdin`；
本报告会写明“扫描时刻的树状态”与“最后一笔改动之后未再变化”，否则结论不成立。

## 2. 探针与复现命令

探针：`tools/governance_gap_probe.py`（新建）。它按 13 项缺口各写一条确定性断言，
每项同时声明“修前应当看到什么”（`before`）与“修后应当看到什么”（`after`），
因此同一份探针就是对照；任一断言与所选阶段不符 -> 退出 1。

只走公开入口：

- `python -m adapters.dsh.hooks`（PreToolUse / PostToolUse 载荷走 stdin，`--audit` 落 JSONL）
- `python -m enforcement.cli`（`precheck` / `execute` / `approve` / `registry`）
- `python -m adapters.cli`（`wiring --check` / `events`）
- 插件源码静态事实：`src/adapters/dsh/policy-hook.plugin.mjs`
- **真插件模块 + 假 ctx 的 node harness**（G02）：加载真 `.mjs`、注入假 `ctx.on` / `ctx.shell`，
  看它到底注册了哪些钩子、post 钩子把什么载荷交给 Hook 命令
- 审计 / 台账 JSONL 的实际内容

复现（全部在仓库根执行）：

    # 修前基线（只读证据，随时可重跑）
    python tools/governance_gap_probe.py --root .tmp/verifier/baseline --phase before --json-out .tmp/verifier/probe-baseline-before.json

    # 修后验收（必须等所有写者停下）
    python tools/governance_gap_probe.py --root . --phase after --repeat 2 --json-out .tmp/verifier/probe-live-after-round3.json

    # 只看某一项（示例：依赖写法绕过）
    python tools/governance_gap_probe.py --root . --phase after --only G06

    # 探针自身的可复现性：连续跑两遍，逐项结论与 facts 必须逐字节一致（见 §2.1）
    python tools/governance_gap_probe.py --root .tmp/verifier/baseline --phase before --repeat 2

    # 测试侧（同一份探针，参数化到 13 项 + 确定性 + 无跨运行残留）
    python -m pytest tests/integration/test_governance_gap_probe.py -q

测试文件：`tests/integration/test_governance_gap_probe.py`（新建）。它断言：13 项齐全、
每项都声明了修前与修后两套预期（否则“对照”不成立）、13 项逐项与修后预期一致、
**连续两遍的结论与 facts 完全一致**（`test_probe_is_deterministic_across_runs`）、
**本次运行没出现过 `event_replay`**（`test_no_cross_run_state_residue`）、探针退出码与结论一致。
`GOVERNANCE_PROBE_ROOT` 可把测试指向另一份快照（修前基线 / 预演副本），实现“同一份探针 + 同一份测试”的对照。

## 2.1 探针自身的可复现性（T3 发现、已修的探针缺陷）

T3 在复核 G06 时发现探针的对照用例（本应 `allow`）返回了 `exit=2 reason=event_replay`：
`.tmp/verifier/probe/baseline/audit/g06-controller_service_allowed.enforcement-ledger.jsonl` 里
已经存在 `action_id=probe-session:probe-g06-controller_service_allowed`，第二次出现按设计被拒。
修前版本的探针虽然每次启动都调用 `rmtree(..., ignore_errors=True)`，但**工作目录在多次运行之间是同一个**，
删除一旦失败（Windows 上的句柄、并发运行）就会留下审计与台账——于是“我跑过了”这件事本身成了下一次运行的输入。

这不是洁癖问题：**一个因为错误原因变红的探针，同样可能因为错误原因变绿**。
G04 要证的正是“同一 `action_id` 绝不执行第二次”，而复用台账恰好会伪造出“被拦住了”的假象。

修法（`tools/governance_gap_probe.py` 的 `Env`）：

1. 每次运行使用唯一工作目录 `<work>/<tag>/run-<run_id>`（`run_id = UTC 时间戳 + pid + 随机后缀`），
   审计、台账、captures、受治理探针项目全部在里面；`run_id` 写进报告 JSON；
2. `setup()` 不再吞异常：目录删不掉就直接 `rmtree` 抛错；建好后**显式枚举**目录内容，
   非空即 `ProbeStateError` 拒绝继续（宁静默失败）；
3. 两小时前的历史 run 目录会被清理（并发运行目录刚建出来，绝不会被误删）；
4. 探针新增 `--repeat N`：连续跑 N 遍（各自独立 `run_id`）并比对**逐项 `ok` / `facts` / `mismatches`**，
   任何差异都会让退出码非 0；
5. 报告级守卫 `unexpected_event_replay`：扫本次运行的全部审计 JSONL，出现任何 `event_replay` 即判失败
   （唯一允许的重放拦截是 G04 显式构造的 `action_replay`，那是被测行为）。

验收（真实输出）：`python tools/governance_gap_probe.py --root .tmp/verifier/baseline --phase before --repeat 2`

    结论: 13/13 与「before」预期一致
    重复运行 2 遍：结论与 facts 一致（run_id: 20260925T165345-38048-712565, 20260925T165415-38048-b437bb）

修探针没有改变修前结论：重复运行下仍为 13/13。**修后验收同样用 `--repeat 2` 跑**，见 §4。

## 3. 修前基线（已完成）

命令与结果：`python tools/governance_gap_probe.py --root .tmp/verifier/baseline --phase before`
-> **13/13 与「修前」预期一致，退出码 0**（53 条子进程调用）。这说明探针能在修前快照上
确定性地复现 13 项缺口，而不是“修前修后都一样”。

| 缺口 | 修前实测（探针事实，非阅读推断） |
| --- | --- |
| G01 | 不存在任何接线清点入口（`adapters.cli wiring` / `adapters.wiring` 都不存在） |
| G02 | 插件源码只注册 `tools/pre-execute`；node harness 加载真插件后注册表仍是 `["tools/pre-execute"]`；但 Python 侧 post 链路完整（真改文件后喂 PostToolUse -> 审计出现 `post_evidence`，status=`validated`） |
| G03 | 受治理动作的审计字段只有 `matched_rules` / `skipped_rules`；无 `effective_rule_count` / `skipped_rule_count` / `skipped_reason` |
| G04 | `approve` 只有 action_hash 单次绑定：逐字一致 -> `allow`；换 action_id -> `approval_invalid`；换命令 -> `command_not_allowlisted`；execute 同一 action_id 第二次 -> `action_replay`（这条本来就守得住）；无审批 -> `approval_required`。另：本机 `"pwsh"` 不在 PATH、bash 被 WSL 拒绝，平台驱动在此机器上执行不了（见 §6） |
| G05 | `workdir` = 绝对根 / `.` / `./` -> `enforcement_param_error`（detail 含 `path_out_of_scope`）；`workdir` = `src` -> 通过参数校验（随后 `permission_denied`）；越界与 `..` -> 仍被拒；`edit` 的 `file_path="."` -> `context_error`（被拒） |
| G06 | 被拦：`from repository import X`、`import repository`、大小写变体。放行：`importlib.import_module("repository")`、`__import__("repository")`、`from . import repository`、`from .repository import X`、`from shop.repository import X`、`import shop.repository`。两条对照（controller 引 service、module 层引 repository）保持放行 |
| G07 | 审计里没有 `layer_defaulted` / `layer_matched_pattern`；`matched_layer=controller`（命中了规则也看不出命中哪条 pattern） |
| G08 | `glob_match("**/*.md","README.md")=false`、`("**/*.py","cli.py")=false`、`("src/**/*.py","src/a.py")=false`；`("src/**/*.py","src/pkg/a.py")=true`、`("**","README.md")=true`；误伤对照（`a.pyc`、`a.md.bak`、`other/src/a.py`）全为 false |
| G09 | `exec.run_code` 声明为 `driver: none`、`post_checks: []`、无 `allowed_commands`、无任何代码检查字段；带合法审批的危险代码（`os.system` + `subprocess.run` + 文件写）-> `decision=allow` |
| G10 | `TOOL_TABLE` 31 项；缺 `spawn_teammate` / `team_task_create` / `team_task_get` / `team_task_list` / `team_task_update` / `wait_agent`；本会话工具清单里另外还缺 `load_workspace_dependencies`；当时 manifest 与 TOOL_TABLE 逐项一致，`adapters.cli events` 退出 0 |
| G11 | 审计里没有任何 `AGENTS.md` / `CLAUDE.md` 的来源 + 哈希留痕；接线自检输出里也没有 |
| G12 | 插件对“非 0 非 2”确实 deny（静态事实）；`--self-check` **不带** `--hooks-config` 时 exit=0（缺席即通过）；配置损坏 / 缺文件 -> exit 2；stdin 损坏 JSON -> exit 2 |
| G13 | 同 G01：没有 `wiring --check` 入口，因此“哪个通道没接线”无法自动发现；空 / 损坏 / 不存在的 dsh 配置根都没有可失败的检查 |

## 4. 逐项判定（修后）

被检快照：**第 3 轮**工作树（身份 `30053031…`，见 §1 的多轮快照表；第 1、2 轮的结果同样保留在下面）。
命令与结果：

    python tools/governance_gap_probe.py --root . --phase after --repeat 2 \
        --json-out .tmp/verifier/probe-live-after-round3.json

    结论: 13/13 与「after」预期一致
    重复运行 2 遍：结论与 facts 一致（run_id: 20260925T175957-39124-0088ad, 20260925T180032-39124-ca6070）
    unexpected_event_replay=[]（无跨运行残留）

    # 同一命令的历史结果：第 1 轮 12/13（唯一红项 G07）、第 2 轮 13/13；命令与 before/after 预期从未改动
    python -m pytest tests/integration/test_governance_gap_probe.py -q
    18 passed, 1 warning in 107.02s        # 第 1 轮为 17 passed + 1 failed[G07]；第 2 轮 18 passed

判定口径（写死，避免事后放宽）：

- `FIXED` = 该缺口在**本轮声明的范围内**的全部行为断言成立，且对照项（不得误伤 / 不得削弱）没有被破坏；
- `PARTIAL` = 本轮范围内的断言没全成立，或只做了缺口的一半（判词里写清剩下的是什么）；
- `DEFERRED` = 计划中明确不做、或需要仓库外条件（重启 GUI / 装 pwsh），**不得算进 FIXED**；
- `NOT FIXED` = 承诺要做的事没做到，并给出最小复现。

“探针”列 = 探针这一轮的断言（可机器复跑）；“判定”列 = 对**缺口本身**的判断。
两列分开写，是为了避免出现“探针绿 = 缺口没了”的错觉：G01 就是典型例子——
探针绿（清点能力已建成），但通道仍然 `not_wired`，缺口在覆盖面上原样存在。

| 缺口 | 探针 | 判定 | 证据（真实输出片段） | 复现命令 |
| --- | --- | --- | --- | --- |
| G01 | ✅ | **PARTIAL**（清点已建成；通道仍未接线，安装 DEFERRED） | `wiring` 报 3 条通道 `dsh:desktop / dsh:headless / dsh:web`，全部 `status=not_wired`、`wired=false`、`detail=profile patch 里没有挂载策略桥`；`--check` 退出 1。缺口原话是“同一条违规写入成功且零审计记录”，这条**仍然成立**：仓库外的主机配置不在本轮范围 | `python tools/governance_gap_probe.py --root . --phase after --only G01` |
| G02 | ✅ | **FIXED**（残余假设 DEFERRED，见下） | 三层证据：①插件源码与 node 假 ctx 都显示注册了 `tools/post-execute`，回调形参 == 3，与本机 dsh 实现包里的 `ctx.on("tools/post-execute", async (exec, result, next) => …)` 字符串事实一致（`tools/pre-execute` 为 2 参）；②插件**真实交出的载荷**喂给 `python -m adapters.dsh.hooks` 后，审计里出现 `post_evidence` 记录（`plugin_post_payload_recorded=true`）；③Python 侧真改文件后 PostToolUse 判 `validated`。且 pre 结论是 `allow`（不是“被阻断的调用也会走 post”那种无信息量的情形） | `... --only G02` |
| G03 | ✅ | **PARTIAL** | 审计新增 `effective_rule_count / skipped_rule_count / skipped_reason / checker_scope`：controller 层文件实测 `effective=1 skipped=42 rule_count=43 checker_scope=forbidden_dependency`，module 层 `effective=0 skipped=43`。**但 43 条规则里仍然只有 1 条（ARCH-001）在 pre 路径真正参与判定，其余 42 条只是“可见地被跳过”，没有被执行**——Phase 5 流水线没有接进 pre 路径（计划内不做）。可见性提高了，拦截面没变 | `... --only G03` |
| G04 | ✅ | **FIXED**（仅限“审批不再因运行时编号失效”） | 模式化审批可用：`--binding pattern --param-pattern command=… --max-uses N`；同一命令换 `action_id` -> `allow`（修前为 `approval_invalid`）；换命令 -> `command_not_allowlisted`；换主体 -> `approval_invalid`；过期 -> `approval_invalid`；次数上限（`--max-uses 1`）第二次被拒；**换一张全新审批 + 同一 `action_id` -> `action_replay`**（防重放未被削弱）。**不声明**“受治理会话现在能跑测试”：本机 `shutil.which("pwsh")` 为 `None`、`bash` 被 WSL `E_ACCESSDENIED` 拒绝，平台驱动执行不了 | `... --only G04` |
| G05 | ✅ | **FIXED** | `workdir` = 绝对根 / `.` / `./` / `src` -> 不再报参数错误（落到下一道闸 `permission_denied`）；越界与 `..` -> `path_out_of_scope`（修前是笼统的 `enforcement_param_error`）；`edit` 的 `file_path="."` 仍被拒（`context_error`）；拿不到结构化 reason_code 时仍退回 `enforcement_param_error` | `... --only G05` |
| G06 | ✅ | **FIXED** | 9 种写法全部 `policy_block`：`from repository import X` / `import repository` / `importlib.import_module("repository")` / `__import__("repository")` / `from . import repository` / `from .repository import X` / `from shop.repository import X` / `import shop.repository` / `from REPOSITORY import X`；两条对照仍放行（controller 引 service、module 层引 repository），未过度阻断。另有 T3 的独立旁证（§5.2） | `... --only G06` |
| G07 | ✅ | **FIXED** | 两半都成立。①冻结接口：`layer_resolution()` 给出 `controller/**/*_controller.py/defaulted=false`、`module/**/*.py/defaulted=false`、默认层 `module/None/defaulted=true`，`layer_for()` 向后兼容。②审计侧（第 2 轮新增）：`audit_keys` 里出现 `layer_defaulted` 与 `layer_matched_pattern`，实测命中规则时 `matched_pattern="**/*_controller.py" / matched_defaulted=false`，走默认层时 `default_pattern=null / default_defaulted=true`——"层是命中通配符还是走默认值"在账本上第一次可读。**反向对照**见本节末 | `... --only G07` |
| G08 | ✅ | **FIXED** | `glob_match("**/*.md","README.md")=true`、`("**/*.py","cli.py")=true`、`("src/**/*.py","src/a.py")=true`（修前均 false）；误伤对照 `a.pyc / a.md.bak / other/src/a.py` 仍 false；放大核对：`**/*.md` 新增命中根目录 `README.md / AGENTS.md`（这正是想要的），`**/*.py` 命中集合不变 | `... --only G08` |
| G09 | ✅ | **FIXED** | 注册表 `exec.run_code` 新增 `code_check` 声明；带**合法审批**的危险代码（`os.system` + `subprocess.run` + 文件写）-> `block / code_blocked`（修前是 `allow`）；结构化检查确实触发（`structural_gate_fired=true`） | `... --only G09` |
| G10 | ✅ | **FIXED** | `TOOL_TABLE` 38 项，含 `spawn_teammate / team_task_create / team_task_get / team_task_list / team_task_update / wait_agent`；与 `adapters/dsh/manifest.yaml` 逐项一致（两个差集都为空）；本会话工具清单差集为空（含 `load_workspace_dependencies`）；`python -m adapters.cli events` 退出 0（= `approved.json` 已重签，哈希不漂移）。分类口径经查是**如实**的：`spawn_teammate` 被记为 `NO_FILE` 而不是"已治理"，注释里写明"被拉起的会话是否有检查站，本检查站看不到（子会话的写类动作不会经过父会话的 PreToolUse）"，且这段 note 会**进入审计的 reason 字段**（`note = spec.note or …`） | `... --only G10` |
| G11 | ✅ | **PARTIAL**（留痕已做；注入内容的策略校验 DEFERRED） | 审计里出现 `context_injection` 记录（来源 + 哈希），`injection_trace_present=true`；但“进到 AI 眼睛里的内容”**仍然不做策略校验**（计划内不做） | `... --only G11` |
| G12 | ✅ | **PARTIAL**（CLI 失败关闭；库内默认仍放行，N5） | CLI 路径：`--self-check` 不带 `--hooks-config` -> `exit=2`（修前 exit=0）；hooks.json 损坏 / config 缺失 / stdin 损坏 -> 全部 `exit=2`；插件把“非 0 非 2”映射成 deny（静态事实）。**但库内默认**：`hooks.run_hook(hooks_config_path=None)` 不传 `allow_unverified_wiring` 时实测 `{"exit_code": 0, "reason_code": "allow"}`——库调用方缺席即放行；显式 `allow_unverified_wiring=False` 才 `wiring_error`（Lead 已把这条登记为已知遗留 N5） | `... --only G12` |
| G13 | ✅ | **FIXED** | `adapters.cli wiring --check@@ 存在并**指名道姓**报出 3 条 `not_wired` 通道，退出 1；`--dsh-home@@ 指向“空目录 / hooks.json 损坏 / 路径不存在”三种情况 -> 全部 `result=fail`、`exit=1`，`bad_configs_never_ok=true`（`skipped` 必须带 `skip_reason`，且绝不等于 `ok`）；未接线通道数 > 0 时 `result==fail` | `... --only G13` |

**判定变更历史（不覆盖旧结论）**：G07 在第 1 轮快照（`1bf25c17…`）判 `PARTIAL`，
在第 2 轮快照（`e13673c3…`）判 `FIXED`；其余 12 项两轮结论与 facts 完全相同。

**G07 的反向对照（证明探针真的在测这件事，而不是"反正现在是绿的"）**：
把第 2 轮快照的 `src/adapters/dsh/hooks.py` 换成第 1 轮的同名文件（差异恰好是那 +10 行审计字段，
其余文件逐字节相同），放进 `.tmp/verifier/g07-revert/` 再跑同一份探针：

    python tools/governance_gap_probe.py --root .tmp/verifier/g07-revert --phase after --only G07
    -> [FAIL] G07，退出码 1
       不一致: layer_fields_present: 期望 True，实测 False
       不一致: matched_has_pattern: 期望 True，实测 False
       不一致: defaulted_is_marked: 期望 True，实测 False

反向对照还顺带证明了两件事：探针的结论随**被检行为**变化（不是随"跑过几次"变化），
以及 G07 的判定没有被别的改动（例如 `tools/README.md`）带绿。

**第 3 轮重做了一次同样的反向对照**（因为快照又变了，不能只靠"上次做过"）：用第 3 轮的树重建
`.tmp/verifier/g07-revert/`（其余文件取自第 3 轮，只把 `hooks.py` 换回第 1 轮那份）：

    python tools/governance_gap_probe.py --root .tmp/verifier/g07-revert --phase after --only G07
        --json-out .tmp/verifier/probe-g07-revert-round3.json
    -> [FAIL] G07（同样三项：layer_fields_present / matched_has_pattern / defaulted_is_marked）

同时用内容寻址的 blob 摘要证明 `hooks.py` 在第 2、3 轮之间没被改过（§1），
所以"第 2 轮的反向对照"与"第 3 轮重做的反向对照"是同一个结论的两次独立确认。

**第 2 轮新增字段对其它断言的影响（Lead 特别要求复核）**：两个字段是**只增不改**，
G03（`effective_rule_count / skipped_rule_count / skipped_reason`，实测 `effective=0 skipped=43`）
与 G11（`context_injection` 留痕）在 13/13 的扫描里仍为 ✅；
新字段没有被任何断言"数键的个数"，因此不存在"多了字段就变红"的脆弱写法。

**G02 的残余假设（单独标 DEFERRED，不是整个 G2）**：本轮修的是仓库侧缺陷（转发层少注册一行），
已由“插件真的注册 + 载荷真的产生 post 审计记录”两条行为证据钉住；
“dsh 运行期真的会按这个签名调用本插件”是对第三方实现的假设——已用实现包里的字符串事实核对到事件名与三参签名，
但**没有真实会话端到端验证**（需要重启 GUI）。这条残余假设记为 `DEFERRED`。

**G07 在第 1 轮曾经是红的（保留这段历史）**：第 1 轮快照上探针断言的是缺口文档要求的最终状态
（账本能区分"命中"与"默认"），而当时接口已就绪、审计没写，所以只做了一半；探针当时故意保持红色，
以免剩下的一半被忘记。第 1 轮的最小复现是
`python tools/governance_gap_probe.py --root . --phase after --only G07`（实测
`layer_fields_present=false`、审计键里没有那两个字段）。第 2 轮 Lead 按这条复现补齐后变为 ✅，
反向对照见上——两次的结论与证据都在报告里，没有互相覆盖。

**G12 为什么仍是 PARTIAL 而不是 FIXED**：CLI 是生产入口且已失败关闭，但库内默认值
（`hooks.run_hook(allow_unverified_wiring=True)`）意味着“库调用 + 不传 wiring 校验”这条路径仍会放行——
这正是缺口文档 G12 说的“保证依赖接线方式”。测试里我用省略参数的方式复现了它（不是构造特殊输入）。


## 5. 对抗性尝试：逐条结果

计划覆盖（任务书要求的最小集合）与**实测结果**：

- **G06**：`importlib.import_module("repository")` / `__import__("repository")` /
  `from . import repository` / `from .repository import X` /
  `from shop.repository import X` / `import shop.repository` /
  大写变体 `from REPOSITORY import X` —— **全部 `policy_block`，没有一条仍放行**；
  两条"不得误伤"对照（controller 引 service、module 层引 repository）仍然 `allow`。
- **G05**：`workdir` = 绝对根 / `.` / `./` / 子目录 -> 不再报参数错误
  （落到 `permission_denied`）；越界 / `..` -> `path_out_of_scope`；
  `file_path="."` -> 仍被拒（`context_error`）。反向断言：无结构化 reason_code 时退回笼统值。
- **G08**：零层命中（`README.md` / `cli.py` / `src/a.py`）全部为 true；
  误伤对照 `a.pyc` / `a.md.bak` / `other/src/a.py` 全部为 false；
  放大核对：`**/*.md` 新增命中根目录 `README.md` 与 `AGENTS.md`（预期内），
  `**/*.py` 的既有命中集合不变。
- **G02**：post 记录**真的出现**（`post_evidence`，status=`validated`）；
  真插件 + 假 ctx 显示 `tools/post-execute` 已注册且回调三参，载荷里带 `tool_response`；
  并且 pre 结论是 `allow`——避开了"被拒绝的调用也会走 post"这个无信息量的陷阱。
- **G04**：无审批 -> `approval_required`；模式化审批换 `action_id` -> `allow`；
  换命令 -> `command_not_allowlisted`；换主体 -> `approval_invalid`；
  过期 -> `approval_invalid`；次数上限（`--max-uses 1`）第二次被拒；
  **换全新审批 + 同一 `action_id` -> `action_replay`**（防重放没被削弱）。
- **G10**：`TOOL_TABLE` ↔ `manifest.yaml` 两个方向差集都为空；
  本会话真实工具与工具表的差集为空；`adapters.cli events` 退出 0（声明已重签、哈希不漂移）。
- **G13**：`--check` 在"空目录 / hooks.json 损坏 / 路径不存在"三种配置根下**都非 0 退出**，
  且 `result` 从不为 `ok`（`skipped` 必须带 `skip_reason`）。

### 5.1 G5 后半段（错误码口径）：T4 指出、Lead 执行的一处修复

缺口文档 G5 的原话是「无害参数被拦，报错还说"参数错误"而不是"需要审批"，AI 与人都会误以为参数写错了」。
本轮的路径口径统一（"等于工作区根"归一化为 `.`）只解决了前半段；后半段是**错误码本身**：

- 现象：`src/adapters/dsh/hooks.py` 的 `build_request` 异常分支把 reason_code 写死成
  `enforcement_param_error`，而底层 `ActionRequestError` 早就带了结构化码
  （`path_out_of_scope` / `param_invalid` / …）。
- 修法（Lead 执行）：`reason_code=getattr(error, "reason_code", None) or "enforcement_param_error"`
  —— 有结构化码就透传，拿不到才退回笼统值。
- 探针的修后预期（G05，`tools/governance_gap_probe.py`）：
  - `workdir` = 越界路径 / `..` -> `path_out_of_scope`（且**不得**再出现 `enforcement_param_error`）；
  - `workdir` = 绝对根 / `.` / `./` / 子目录 -> **不再报参数错误**，问题落到下一道闸（探针主体的
    developer 没有 `shell.exec`，因此是 `permission_denied`）。
    这里不能把合法路径硬说成 `path_out_of_scope`——"范围没问题"与"范围越界"必须是两个不同的结论；
  - **反向断言**（Lead 要求）：注入一个没有 `reason_code` 的桥异常时，必须退回笼统的
    `enforcement_param_error`，而不是编一个具体的码出来
    （`G05.fallback_reason_without_structured_code`，走公开导出的 `DshPreExecuteHook.handle()`）。

这一处是**同一个结论在两处口径不一致**的又一个实例，与本轮主线（R2/R3/R4 的"接缝处没人负责"）同源。
条目的来源要写清楚：**由 T4 在汇报里主动指出"底层已经给了结构化 reason_code、上层仍包成笼统值"，由 Lead 执行**；
探针只负责在修前/修后各跑一次、把它变成会失败的断言。

### 5.2 独立旁证（T3 提供，**不是本探针跑的**）

T3 用自己的脚本 `.tmp/rule-fidelity/g06-e2e.py`（全新项目目录 + 全新配置 + `ledger=None`，
走真实 `DshPreExecuteHook.handle`）独立复现了 G06：9 条绕过写法全部 `exit=2 reason=policy_block`
（是**策略判定**，不是 replay），2 条对照 `exit=0 reason=allow`。

引用时按 Lead 的要求注明：这是 **T3 提供的旁证**，不是本报告作者运行的；
本报告的 G06 结论仍然只以本探针自己的运行为准（`--only G06` 的 facts 与 §4 的证据）。
两条独立实现的结论一致，说明"三种绕过写法不再结构性放行"不是单个脚本的产物。

**引用 T3 这条旁证时同时记录他发现的探针缺陷**：他在隔离目录重跑才拿到 11/11 符合预期，
并据此指出探针的跨运行状态复用（详见 §2.1）。处理过程值得记一笔：他没有把"探针的缺陷"算成自己修复的缺陷，
也没有用它来抬高自己的结论——这正是本轮要的对手角色的行为。

## 6. 汇总风险与残留

### 6.1 本轮**没有**解决的缺口（不得算进 FIXED）

| 缺口 | 未解决的部分 | 性质 |
| --- | --- | --- |
| G1 | 把策略桥真正挂到本机 desktop / headless / web profile（含 `spawn_teammate` 拉起的子会话：它的写类动作不经过父会话的 PreToolUse，父会话的检查站看不见它） —— 三条通道实测仍是 `not_wired`、`wired=false`。"同一条违规写入成功且零审计记录"这条缺口原样存在 | 计划内不做（仓库外的主机配置，装上要重启 GUI）；本轮只交付"可发现的显式状态 + 接线模板" |
| G3 | 43 条规则里 **42 条**仍然不在 pre 路径执行，只是"可见地被跳过"：实测 controller 层 `effective=1 skipped=42`；module 层 `effective=0 skipped=43` | 计划内不做（把 Phase 5 流水线接进 pre 路径是架构变更，半截接线更危险）；**拦截面没有变化，只有可见性变化** |
| G7 | ~~审计不写 `layer_defaulted` / `layer_matched_pattern`~~ **已在第 2 轮快照修掉，第 3 轮复核保持修好**（`layer_matched_pattern` / `layer_defaulted` 实测落账；第 3 轮 `hooks.py` 的 blob 摘要与第 2 轮相同，反向对照在第 2、3 轮各验一次，见 §4） | 第 1 轮判为漏项（探针当时是红的）；Lead 按最小复现补齐后，第 2 轮 13/13、第 3 轮 13/13。这里保留行位是为了留痕，不再算未解决 |
| G11 | 进入 AI 上下文的文档**不做策略校验**（只记来源与哈希） | 计划内不做（需要对注入链路的所有权） |
| G4 | "会话开始前声明调用编号空间" | 计划内不做（编号空间是 Agent 运行时内部实现） |
| G12 | 库内默认 `hooks.run_hook(allow_unverified_wiring=True)`：库调用方省略 wiring 校验时仍然放行（CLI 是失败关闭的） | Lead 登记的已知遗留 **N5**；实测 `{"exit_code": 0, "reason_code": "allow"}` |
| G2 | 真实 dsh 会话端到端未验证（事件名与三参签名已用实现包字符串事实核对，但没有真会话触发过 PostToolUse） | 残余假设，DEFERRED（需重启 GUI） |

### 6.2 环境性事实（不是实现缺陷，但会让"能不能用"被误读）

- 本机 `shutil.which("pwsh")` 为 `None`（DSH 会话的 pwsh 工具走绝对路径），
  `bash` 存在但被 WSL 以 `E_ACCESSDENIED` 拒绝：**平台驱动执行不了**，
  `python -m enforcement.cli self-check` 也会把"找不到 pwsh"作为 warning 报出来。
- 因此 G04 的判定严格限定为"审批不再因运行时编号失效"：缺口文档 G4 的原始现象
  （"AI 想跑测试，做不到"）在这台机器上**仍然成立**，但原因已经从"审批绑定"变成"运行时驱动不可用"。
  把这条写成"受治理会话现在能跑测试"会是假结论。
- `adapters.cli wiring --check` 退出 1 是本机真实状态（三条通道没接线），不是回归；
  它同时是 G13 的验收证据。

### 6.3 需要 Lead 决定的事

1. ~~G07 的审计写入~~ **已关闭**：Lead 按第 1 轮的最小复现在 `hooks.py` 补齐了两个字段，
   第 2 轮快照上探针 13/13，第 3 轮复核仍 13/13；并用"回退这份文件"的反向对照（第 2、3 轮各一次）
   确认探针真的在测它（§4）。第 1 轮的 PARTIAL 判定与证据保留在报告里，不覆盖。
2. **G12 的 N5**（库内默认值）是否要在下一轮改成"必须显式传 `allow_unverified_wiring=True` 才放行"：
   改默认值会波及几十个与被测行为无关的库调用点（`hooks.py` 的注释里已经论证过这个取舍），
   属于产品决策，不是验收能单方面定的。
3. **G4 的"真能跑测试"**：本机缺 `pwsh` 是环境问题；如果要证明受治理会话能跑测试，
   需要一台 `pwsh` 可用的机器或有意识地改注册表（改注册表要重新审核），这不在本轮。

### 6.4 验收结论

- 探针 `--root . --phase after --repeat 2`（第 3 轮快照 `30053031…`）：**13/13**，
  两遍结论与 facts 完全一致；跨运行残留守卫 `unexpected_event_replay=[]`；
  `pytest tests/integration/test_governance_gap_probe.py -q` -> `18 passed`（107.02s）。
  与第 2 轮**逐项相同**——第 3 轮改的是生成器 / 手册 / README / CI 接线，没有触碰任何被测行为，
  这正是"判定不变"的预期结果。
- 按"缺口本身"判定（13 项全部有明确归属）：
  **FIXED 9 项** = G02 / G04 / G05 / G06 / **G07** / G08 / G09 / G10 / G13；
  **PARTIAL 4 项** = G01（通道仍未接线）/ G03（42 条规则仍未执行）/ G11（注入内容不校验）/
  G12（库内默认放行，N5）；
  **NOT FIXED 0 项**（没有任何一项"承诺要做却没做"）；**DEFERRED** 的是三处残余：
  G02 的真实会话端到端、G01 的"真正装上去"、G11 的注入内容校验（均需仓库外条件）。
- 修前 / 修后对照由**同一份探针**在**四份快照**上跑出：
  修前基线（`.tmp/verifier/baseline`）`13/13` 与 before 预期一致；
  修后第 1 轮 `12/13`、第 2 轮 `13/13`、第 3 轮 `13/13`。
  结论差异全部来自被测行为的变化，不是断言被放宽——探针的 before/after 预期在修前就已经连同基线一起跑过，
  第 1 轮红掉的 G07 在第 2 轮变绿，而把那份文件回退后它**再次变红**（第 2、3 轮各验一次）。

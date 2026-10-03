# Phase 9：控制面重构（台阶 −2 → 5，**只报告部分**）

> **状态**：**已实现（部分）**。已交付的是《控制面重构方案》台阶 −2 → 5 的**只报告部分**；
> **升格**（把任何一条只报告读数接成阻断、改任何退出码）**一项都没做**——
> 2026-10-03 裁定（使用者授权评审方）：**本轮一律不升格，统一到 2026-12-31 复审**，
> 逐条见 [23 号 §22.1](../reviews/governance-capability/15-control-plane-design/23-round20-reading-context-landing.md)。
> 本文件只写**有证据**的部分；**没有实现的一律在「剩余缺口」一节**，不许读成已交付。
> **方案与索引**：[控制面重构方案.md](../designs/控制面重构方案.md)（v2，状态 = 已实现（部分）、§7.2 是台阶 0–5 的预算终算）、
> [设计提案索引](../designs/README.md)。
> **逐步证据**：[15-control-plane-design/](../reviews/governance-capability/15-control-plane-design/README.md) 的 01–28 号；
> 原件多在 `.tmp/`（会被 `tools/cleanup.py` 删除），本文件只引用**已跟踪**的结论、读数与出处。
> **编号说明**：Phase 9 **不是** Phase 0–8 的第九个产品阶段，而是 Phase 8 之后的**横向轨道**：
> 方案自己的编号是「台阶 −2 → 5」，与平台阶段编号**各走各的**，不得互相代入。

## 目标

平台要求被治理者「事实进数据、失败关闭、可证伪」，而它自己的配置、失败、状态与覆盖曾经散在
YAML / hooks.json / 脚本常量 / 两门语言里，各有一套解析。Phase 9 的目标是把**平台自己**纳入这三条纪律：

1. 一套**针脚**（四个名字、一份实现）：证据属于哪棵树、哪次运行；
2. 一张**检查登记表**：每条检查有身份、有归属、有「覆盖不到什么」；
3. 一个**状态代数 + 义务账**：跳过 ≠ 通过，待实现有跨会话的去处；
4. 一个**归因闭集**：理由指错对象要能被发现；
5. 一份**边界裁定 + 三数分离的报告**：治理谁、不治理谁写进数据，读数不合并成比例。

## 边界（本阶段明确不做什么）

- **不改判定路径**：`policy.engine.evaluate` 的判定逐字节不变（R-d 差集 0 条是每轮的验收项）。
- **不新增任何加载期 FATAL**，**不新增阻断步骤**，**不改任何退出码**（2026-10-03 之前的全部轮次）。
- **不合并谓词**：C1 的两份测试路径声明只把 101 条不一致**读出来**，不合成第三份谓词（合并会改变判定）。
- **不把「没跑成」记成「通过」**：环境跳过（沙箱受限、dsh 缺失、账本不存在）是显式状态，不是 0 命中。

## 已实现的部分（只报告，逐条带实现位置 / 版本轴 / 门禁步骤 / 证据文件）

**口径**：下表每一行都只覆盖**只报告**的那一部分；「门禁步骤」一栏写它在
`python tools/ci_local.py --full` 里的落点（**未接** = 门禁里没有它，只能直跑）。
版本轴各自独立演进、**不跟随平台阶段**（AGENTS 第 55 条）；括号里的数字是当前常量值。

| 台阶 | 已实现（只报告）的部分 | 实现位置 | 版本轴 | 门禁步骤 | 证据文件 |
| --- | --- | --- | --- | --- | --- |
| −2 会话隔离 | 每会话一棵工作树 + 仓库内排他锁：抢不到锁**直接退 1**（报出持锁者 pid，不等待、无绕过开关），进程死锁由操作系统释放，不留陈旧锁；`cleanup.py` 认同一把锁并显式跳过锁文件 | `tools/ci_local.py`（`lock_path()` = `<仓库根>/.tmp/ci-local.lock`、非阻塞咨询锁）、`tools/cleanup.py`；纪律在 `AGENTS.md`「工作方式」第 5 条 | 无（不是载荷） | 不是一步：它是门禁自身的**前置**（`--list` 不取锁） | `AGENTS.md` 同条；23 号各轮 §0「环境自检」 |
| −1 基线冻结与重采 | 30 臂矩阵 **248 检查 0 偏差**、11 个 fixture **逐字段全等**，在**有修订号的树**上重采（此前读数属于 round-09/10 的无修订号树） | 只读仪器（`probe_matrix.py` / `decision_invariance.py` 等在 `.tmp/`，**未入库**） | 无 | **未接**（手工仪器） | [09-baseline-recheck.md](../reviews/governance-capability/15-control-plane-design/09-baseline-recheck.md) |
| 0 封条与针脚 | 四个名字一份实现（`evidence_tree_digest` / `referenced_inputs_digest` / `workspace_tree_digest` / `platform_revision`）、严格模式（读不到 = `unprovable`）、两层封条、边界声明最小形态；`provenance_loop.py` 的 **5 个场景**闭环 | `src/provenance/worktree.py`(471) / `cli.py`(257) / `wiring_scope.py`(175) / `__init__.py`(43)、`adapters/wiring-scope.yaml`(46)、`tools/provenance_loop.py`(302)、三份测试(360)（口径 = `len(text.splitlines())`，树 `d4ebc45`） | `provenance.cli.RECEIPT_SCHEMA_VERSION = "1.0"`；`provenance.wiring_scope.SCHEMA_VERSION = "2"`（加载器**同时接受 "1" 与 "2"**） | **未接**：门禁 31 步里没有任何一步被要求交出判据级封条（R-e 完整版仍是缺口第 1 条；R-h 把 5 个场景登记成对象） | 方案 §4/§7；`tools/README.md`；`tests/integration/test_provenance_loop.py` |
| 1 H4/H5 | pytest 退出码 **5**（没有收集到任何用例）不再记成「测试跑过了」；三个子进程调用点的 env 统一 | `src/validators/adapters/pytest_runner.py`、`src/validators/pipeline.py`、`src/validators/adapters/base.py`；`tests/integration/test_validator_pipeline.py`、`test_validator_cli.py` | 无（改的是判定行为，不是载荷形状；判据 R-f 按**真实执行的用例数**读） | `Unit, contract, integration and security tests` + 验证器闭环/证据重放 | [10-h4-field-diff.md](../reviews/governance-capability/15-control-plane-design/10-h4-field-diff.md) |
| 2 归因闭集 | `origin` 五族闭集 + 每族必备字段 + 「写不出 `fix` 的 origin 不许存在」+ 核验前置（证伪自己人落 `unknown_origin`）；配置族（Python）与 spawn 输入族（JS）两端；真插件产出 → 真分类器的跨语言契约用例 | `src/provenance/origin.py`(297)、`src/provenance/origin_runtime.py`(202)、`src/adapters/dsh/hooks.py`(+119/−4)、`src/adapters/dsh/policy-hook.plugin.mjs`(+225/−7)、`tests/contract/test_policy_hook_chain.py`、`tests/unit/test_dsh_origin_attribution.py`、`tests/unit/test_provenance_origin.py` | origin 一族键是**加键未升版的历史先例**（AGENTS 第 55 条明写「不是可以再犯的先例」）；`VERDICT_SCHEMA_VERSION = "1.0"`（字段级差集 0 条 → **不升**） | `dsh hook wiring self-check` + pytest 里的跨语言契约用例 | [11-step2-origin-closure.md](../reviews/governance-capability/15-control-plane-design/11-step2-origin-closure.md)、[15-small-fixes.md](../reviews/governance-capability/15-control-plane-design/15-small-fixes.md) |
| 3a 受控 reason 与脱敏 | H1/H10：受控 `decision_reason` + 归因路径脱敏（Python ↔ JS 同一口径） | `src/adapters/dsh/hooks.py`、`src/adapters/dsh/policy-hook.plugin.mjs` 及其契约用例 | `AUDIT_SCHEMA_VERSION` 1.0 → **1.1** | `dsh hook wiring self-check` + pytest | [12-step3a-reason-and-redaction.md](../reviews/governance-capability/15-control-plane-design/12-step3a-reason-and-redaction.md) |
| 3b pending 独立通道 | 「待实现」移出 `violations`、改独立通道 `pending_findings`（severity 在构造期强制 warning）；四种 decision 与改动前**逐个相等** | `src/policy/evidence.py`（`pending_findings`）、`src/validators/pipeline.py`、`src/policy/engine.py`、`src/policy/check.py`、`src/orchestration/nodes.py`（消费方 `repair()`） | 决策 `SCHEMA_VERSION` 1.0 → **1.1** 与 `POLICY_VERSION = "decision-1.1"`（同进同退）；`EVIDENCE_SCHEMA_VERSION` 1.1 → **1.2**；`PIPELINE_SCHEMA_VERSION` 1.1 → **1.2**；`AUDIT_SCHEMA_VERSION` 1.1 → **1.2** | `Unit, contract, integration and security tests` + `dsh hook wiring self-check` | [13-step3b-d1-field-diff.md](../reviews/governance-capability/15-control-plane-design/13-step3b-d1-field-diff.md)、[14-step3b-landing.md](../reviews/governance-capability/15-control-plane-design/14-step3b-landing.md) |
| 3c 义务账 | 只记账不判罚；键 `(rule_id, target, missing_target)` **不含 `session_id`**（跨会话）；解除只由**一次真实 pytest 运行**判定；判罚与读数只在门禁工具 | `src/policy/obligations.py`(540)、`tools/obligations_gate.py`(137)、`dsh-adapter.yaml` 的 `obligations_ledger`（可选；写不了只打一行不阻断）、`policy.check --obligations` | `policy.obligations.LEDGER_SCHEMA_VERSION = "1.0"`；`obligations_gate.REPORT_SCHEMA_VERSION` 1.0 → 1.1 → **1.2** | **只报告步骤 1** `Obligations gate (report only)`（登记于 2026-09-30，豁免到期 **2026-10-31**） | [16-step3c-obligation-ledger.md](../reviews/governance-capability/15-control-plane-design/16-step3c-obligation-ledger.md)、[18 号 §5](../reviews/governance-capability/15-control-plane-design/18-round16-rulings-execution.md) |
| 4 覆盖账（`governs` 轴 + 三数 + 六格差集） | `wiring` 报告的 `account`（discovered/declared/measured，**整数、禁比例**）、`differences`（六格）、`headline`（含机器行 `IN_SCOPE_NOT_WIRED: n / …`）、`red_conditions`（`enforced: false`）；声明文件按 `kind` 分档 + `covers` 显式覆盖 + `governs_tree` 声明位 | `src/adapters/wiring.py`、`src/provenance/wiring_scope.py`、`adapters/wiring-scope.yaml` | `WIRING_SCHEMA_VERSION` 1.1 → 1.2 → 1.3 → **1.4**；`wiring_scope.SCHEMA_VERSION` "1" → **"2"**（兼容窗口 0） | 门禁 **`Agent channel wiring inventory`**（第 24 步，报告模式、**恒退 0**） | [24 号](../reviews/governance-capability/15-control-plane-design/24-step4-governs-axis-design.md)；23 号 §14/§16.2/§17/§18；[17-step4-5-scope-assessment.md](../reviews/governance-capability/15-control-plane-design/17-step4-5-scope-assessment.md) |
| 4 `reading_context` | 六类读数带「属于哪棵树 / 哪个环境 / 哪一套声明」的统一形状（**一份实现**，三态 `available` / `unavailable` / `not_applicable`；`host.sandbox ∈ {restricted, unrestricted, unknown}`，`unknown` 是「读不到」不是「没有沙箱」） | `src/provenance/reading_context.py`；消费方：端到端结果、Hook 审计、`policy.check --json` 外层包装、两条只报告读数、覆盖账、阶段证据 | `SANDBOX_RESULT_SCHEMA_VERSION` 1.1 → **1.2**；`AUDIT_SCHEMA_VERSION` 1.2 → **1.3**；`OUTPUT_SCHEMA_VERSION` 1.1 → **1.2**；`obligations_gate.REPORT_SCHEMA_VERSION` **1.2**；`exemption_expiry.EXEMPTION_REPORT_SCHEMA_VERSION` **1.1**（首建） | 门禁第 9 步 `Real dsh sandbox loop`（沙箱闭环）+ 两条只报告读数 + pytest 契约用例 | [21 号](../reviews/governance-capability/15-control-plane-design/21-step4-reading-context-design.md)；23 号 §4/§9/§11/§12 |
| 4 五条写声明 | ① 门禁退出码语义表（0/1/2/3，3 属于封条命令）；② 会话窗口（由 −2 的「每会话一棵树 + 排他锁」承接）；③ 写权租约（同上，不另建机制）；④ 三条通道 `out_of_scope`（`dsh-web` / `dsh-headless` / `dsh-verify-dead`）；⑤ CI 注释里的边界裁定提升为 `gate_check` 声明 | `tools/README.md`「门禁退出码」节、`tools/ci_local.py` 的 docstring、`adapters/wiring-scope.yaml` | 声明文件 `schema_version: "2"`（与 `wiring_scope.SCHEMA_VERSION` 同轴） | 门禁第 24 步（声明被 `wiring` 读到；声明本身不改退出码） | [18 号 §5](../reviews/governance-capability/15-control-plane-design/18-round16-rulings-execution.md)；23 号 §14.4 |
| 4 声明数据收尾 | 12 条通道逐条显式 `covers`；三条 `verify-*` 实验 profile 改判/撤回；第六格 `expected_absent_present`；`reason` 按真实成因分开写 | `adapters/wiring-scope.yaml`、`src/adapters/wiring.py` | `WIRING_SCHEMA_VERSION` 1.3 → **1.4**（1.3 内补的第六格**不升版**） | 门禁第 24 步 | 23 号 §16.2/§17.2/§17.4；24 号 §8.3/§8.5 |
| 4 豁免到期 | 到期前 14 天 `DUE`、过期 `RED`、**退出码恒 0**、稳定机器行 `HITS:`；读不到写 `unprovable`（不变成阻断，也不读成「没有到期日」） | `tools/exemption_expiry.py`(287) | `EXEMPTION_REPORT_SCHEMA_VERSION = "1.1"`（首建轴；`--json` 加键必须动它，`HITS:` 文本行**一个字符都不改**） | **只报告步骤 2** `Exemption expiry report (report only)`（登记于 2026-09-30，豁免到期 **2026-12-31**） | [20 号 §3](../reviews/governance-capability/15-control-plane-design/20-round18-e2e-solidification.md)；23 号 §16.2 |
| 4 仪器自证（R-h） | 对象表**四族 65 条**（门禁步骤 44 / 探针检查 13 / 封条场景 5 / 只报告步骤 3）+ 三态判据（无 `check_id` / 无 `mutation_id` 且无 `gap_note` / 补丁打不上）+ 反退化（`check_id_without_object`）+ 只报告载荷（四格 `enforced: false`、`would_exit_code: 1`）；**方案 A**：存量写 `gap_note`、**不做变异** | `tools/instrument_self_proof.py`(980)、`validation/instrument-checks.yaml`（65 行 × 8 字段，**只放指针**） | `INSTRUMENT_SELF_PROOF_SCHEMA_VERSION = "1.0"`；`CHECKS_SCHEMA_VERSION` "1" → **"2"**（加**可选** `covers_facts`，加载器接受 "1" 与 "2"）；`MUTATION_SCHEMA_VERSION = "1"` | **只报告步骤 3** `Instrument self-proof (report only)`（登记于 2026-10-03，豁免到期 **2026-12-31**） | [25 号](../reviews/governance-capability/15-control-plane-design/25-step4-instrument-self-proof-design.md)、[26 号交接清单](../reviews/governance-capability/15-control-plane-design/26-ci-line-handoff-instrument-self-proof.md)；23 号 §19.3 |
| 5 控制面事实表 × 跨源互证 | facts 表 **13 行 × 9 字段**（只放指针、不放值）+ 连接键 `facts.key ↔ checks.covers_facts` **双向必查** + 三组跨源读数（C1 测试路径 / C2 工具表 / C3 预算不等式）+ 四格红条件（`enforced: false`、`would_exit_code: 1`） | `validation/control-plane-facts.yaml`(13 行)、`tools/control_plane_facts.py`(1322)、`tools/instrument_self_proof.py` 的 `covers_facts` 加载、`src/adapters/dsh/hooks.py` 的 `budget_inequality_facts` 抽取 | `CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.0"`；`FACTS_TABLE_SCHEMA_VERSION = "1"`；`CHECKS_SCHEMA_VERSION` "1" → **"2"** | **未接**：不在 `ci_local` 与 workflow 里（[28 号](../reviews/governance-capability/15-control-plane-design/28-ci-line-handoff-control-plane-facts.md) 是交接清单）；pytest 有用例 | [27 号](../reviews/governance-capability/15-control-plane-design/27-step5-control-plane-facts-design.md)、28 号；23 号 §21 |

**每一条「已实现」的共用证据纪律**：读数必须写清**属于哪棵树**（`reading_context.tree.revision`）、
**属于哪一次运行**（`run.id`），以及**它是不是 enforceable**（`enforced: false` 是声明出来的
「还没接线」，不是「忘了」）。

## 端到端证据归档（使用者本机历次真机 pass）

口径：`.tmp/e2e/` 下的**原件字节**（本机 `Get-FileHash` 重算 sha256）；
`.tmp/` 是构建产物目录，**会被 `tools/cleanup.py` 删除**，本节登记的是「这些字节序列存在过且被复核过」，
**不是**可长期复核的仓库产物。前两份是从终端输出**转录**的（1.1 载荷，没有 `reading_context`），
其余六份是从 `.tmp/artifacts/phase-2-sandbox-result.json` **复制**的原字节。

| # | 原件（相对仓库根） | 字节 | sha256 | `timestamp`（UTC） | `tree.revision` | `host.sandbox` | 结论（两个场景都 `passed = true`） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `.tmp/e2e/phase-2-sandbox-result.pass-20260930T010751Z.json` | 2653 | `df2646db896cf726d03cbdff0372783d96f2cffb01b3873034a583167859ed30` | 2026-09-30T01:07:51.436314Z | 未记录（载荷无 `reading_context`） | 未记录 | `result=pass`；block 文件未变（`53b53a25…`）、allow 改一次（`53b53a25… → 2972725e…`） |
| 2 | `.tmp/e2e/phase-2-sandbox-result.pass-20260930T113532Z.json` | 2780 | `dbcf31765bbcedebcf6b73a8ff5eb29cbec525f42800212e3ccabe91247a8946` | 2026-09-30T11:35:32.027532Z | 未记录（`schema_version = "1.1"`；23 号 §2 按轮次记为 `cd40f74`） | 未记录 | `result=pass`；同上（本文件是**转录件**） |
| 3 | `.tmp/e2e/pass-20260930T214825.json` | 3603 | `da1279af9f86e0c082d3fb782aa3b2e0c3c44eeac994eccc48051bd5f459e15a` | 2026-09-30T13:48:23.294459Z | `7864dd247cb8c98dedf2c26b55ebcd02a0092671` | `unrestricted` | `result=pass`、`environment_skipped=false`；block `exit_code=2`/`executed=false`/`policy_block`；allow `exit_code=0`/`executed=true` |
| 4 | `.tmp/e2e/pass-20260930T231438.json` | 3662 | `5708f3c68890a8c972aa1b91f309b54e60f8c1d5fb7ac2a60c79f6fa2b7c1311` | 2026-09-30T15:14:37.400188Z | `92a6dd141543a6ab2c3a64d8f32af412569a4197` | `unrestricted` | 同第 3 行（`isolated_home=true`、`dsh_home=.tmp/phase-2-sandbox/dsh-home`） |
| 5 | `.tmp/e2e/pass-20261001T030051.json` | 3606 | `b090f7c80a17dd76c120b17fd9dc6c9cf56308c81c2d207d459dd59eb8895b55` | 2026-09-30T19:00:49.115572Z | `1e9df8cec7968f7530b1b3aac556e6a152ec0281` | `unrestricted` | 同第 3 行 |
| 6 | `.tmp/e2e/pass-20261001T132947.json` | 3612 | `bb068017ff86e584b9fd8a7e4e9a5c0c45204ae59bcdff18a0a80b9839237ba9` | 2026-10-01T05:29:46.732763Z | `088349ab547aa280044e2220ebe5da44c7be27b5` | `unrestricted` | 同第 3 行 |
| 7 | `.tmp/e2e/pass-20261003T173744.json` | 3621 | `00978b996d5324a3a809b1333e612891601534fd0c97fcfda45116d3f87c07e3` | 2026-10-03T09:37:43.448758Z | `5b925e4837c26c50569fb8f7d7893789cb31b614` | `unrestricted` | 同第 3 行 |
| 8 | `.tmp/e2e/pass-20261003T203632.json` | 3653 | `56a152af546acc526b99b218f00aad7227fbadee692f99a47cc89e9bf4f36ed5` | 2026-10-03T12:36:30.946531Z | `5b925e4837c26c50569fb8f7d7893789cb31b614` | `unrestricted` | 同第 3 行 |

- 八条**全部** `result=pass` / `environment_skipped=false` / `agent=dsh` / `agent_version=0.1.5-rc.1` /
  `matched_rules=["ARCH-001@1"]` / `rule_set_hash=sha256:50202675b6ca4013…`；
- 第 7、8 条落在**本轮起点树**（`5b925e4`）上：真机 pass 在最终树上**有读数**；
- 与门禁第 9 步的对照：**同一个闭环**在本会话的受限上下文里是 `result=skipped`、
  `host.sandbox=restricted`、`dsh_startup_denied_kind=profile_write_denied`（`.tmp/artifacts/phase-2-sandbox-result.json`）。
  **跳过不是通过**（AGENTS 第 45 条）；差别只来自环境，两份读数都要留。

## 升格评审（摘要）

**2026-10-03 裁定**：**本轮一律不升格**——三条只报告步骤 + 两个只报告工具（`control_plane_facts`、
覆盖账红条件）+ 端到端 `host.sandbox` 读数，全部维持「只报告、退出码不动」，
**统一到 2026-12-31 复审**；其中 `control_plane_facts` 的 **101 条命中是 C1 存量**，
**升格前提是先把这 101 条降到 0**。逐条的轮次 / 真实读数 / 当前命中 / 升格判据见
[23 号 §22.1](../reviews/governance-capability/15-control-plane-design/23-round20-reading-context-landing.md)。

本阶段**没有**任何一条读数接进退出码，因此：`python tools/ci_local.py --full` 的
**31 步执行 + 3 步只报告**里，三条只报告步骤的**非零退出不计入门禁失败**。

## 剩余缺口（**未实现**，不许读成已交付）

| # | 缺口 | 现状（可复核读数或出处） | 处置 |
| --- | --- | --- | --- |
| 1 | **门禁接封条（R-e 完整版）** | `ci_local --full` 的执行路径里**没有任何一步**被要求交出判据级封条（`referenced_inputs_digest` 的 pre/post 比对 + 退出码 3）；机制只在 `tools/provenance_loop.py` 的 5 个场景里 → 台阶 0 的状态是**部分绿** | **不排期**；若做，形态约束写死在 23 号 §20.3（只能先以只报告形式、由 CI 线加、第一版不接退出码 3、先用声明输入） |
| 2 | **R-h 变异自证覆盖为 0** | `validation/instrument-checks.yaml` **65 行的 `mutation_id` 全为 `null`**（方案 A 的存量写法：写 `gap_note`、不做变异）；三态里的「补丁打不上」因此没有真实对象 | 升格 R-h 之前必须先补（25 号 §7 的方案 B/C），另走一轮 |
| 3 | **C1 的 101 条不一致（合并谓词未做）** | `control_plane_facts` 读数：扫描 **204** 个文件、判定不一致 **101**（platform=False/adapter=True 101、反向 0）、层级不一致 **100**；两份声明仍是各写各的（平台 `validation/test-layout.yaml` 的 `test_patterns` vs `examples/dsh/dsh-adapter.yaml` 的 `test_paths`） | 合并谓词会**改变判定**（layer 是判据输入）→ 属 R-d 范畴，必须另开一轮并交出字段级差集 |
| 4 | **orchestrator 的 `tool_name` 为 `unavailable`** | C2 关系读数：registry 的 4 条 orchestrator `tool_name` 在 `src` / `registry` / `adapters` / `tools` 下**没有任何读取点**（代码侧引用的是四个 `orc.*` **id**）→ 报告写 `unavailable`，不猜 | 保持 `unavailable`；要变 `available` 得先有一条可评审的判据 |
| 5 | **DSH 会话里 xdist 起不来** | 本会话 `workspace-write` 下 `pytest -n auto` 必然 `INTERNALERROR`；门禁读数靠 `PYTEST_XDIST_AUTO_NUM_WORKERS=0` **串行**跑，代价是 pytest 步 **6–7 分钟**（并行约 2 分钟）；**根因未核实** | 每次用它跑出的门禁读数**必须逐次声明**（23 号 §20.1 第 6 条）；根因另查 |
| 6 | **`~/.dsh` 与 `%TEMP%` 在 dsh 进程里不可写的原因未核实** | 门禁第 9 步：`result=skipped`、`host.sandbox=restricted`、`dsh_startup_denied_kind=profile_write_denied`、被拒路径 `C:\Users\ZNM\.dsh\profiles\headless\cordis.yml`；而 `--isolated-home` 的真机形态 `result=pass` | 只登记现象与归因路径，**没有根因**；不把它写成「沙箱就是这样」 |
| 7 | **只报告读数的 2026-12-31 复审** | 三条只报告步骤（最近到期日：`Obligations gate` **2026-10-31**）+ `control_plane_facts` + 覆盖账红条件 + `host.sandbox` | 统一到 **2026-12-31** 复审（23 号 §22.1）；到期前 14 天由 `exemption_expiry` 报 `DUE`，过期报 `RED` |

**同批登记、不排期的两条**：① 覆盖账的 `declared_not_discovered = 1`（`ci-agent-runtime` 声明本机没有
绑定到任何通道）与 `in_scope_not_wired = 3`（三条 `dsh:governed-*` 通道留痕 stale）都**不是**本阶段
能判的（判据在 24 号 §2.2/§2.3，改动要走显式提交）；② R-e 的三个状态
（`landed_unverified` / `landed_peer_verified` / `round_verified`）**没有任何一方签发过**。

## 测试与复核（只读或只写 `.tmp`）

```powershell
# 三条只报告步骤（退出码恒 0 或只反映用法错误）
.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp/obligations/repo.jsonl
.venv\Scripts\python.exe tools\exemption_expiry.py
.venv\Scripts\python.exe tools\instrument_self_proof.py

# 两个只报告工具（都退出码恒 0，未接门禁）
.venv\Scripts\python.exe tools\control_plane_facts.py
$env:PYTHONPATH="src"; .venv\Scripts\python.exe -m adapters.cli wiring --json

# 封条闭环（台阶 0 的 5 个场景；**不在门禁里**）
.venv\Scripts\python.exe tools\provenance_loop.py

# 本阶段自己的用例（在门禁的 pytest 步里）
.venv\Scripts\python.exe -m pytest tests\unit\test_control_plane_facts.py tests\unit\test_instrument_self_proof.py tests\unit\test_dsh_budget_inequality.py -q

# 全量门禁（本机；本会话形态需要串行声明，见缺口第 5 条）
$env:PYTEST_XDIST_AUTO_NUM_WORKERS = "0"
python tools\ci_local.py --full --python .venv/Scripts/python.exe --timings
```

## 观察点

1. **门禁里只报告步骤的行**：`REPORT-ONLY: <名字> —— <verdict>；读数 …；豁免到期 …`（三条）；
2. **只报告载荷的红条件块**：`enforced: false` + `would_exit_code` + `promote_when` 是「还没接线」的
   唯一机器可读表达；「此刻真的红着」由 `count > 0` 表达；
3. **覆盖账的三数**：`discovered` / `declared` / `measured`（整数；`unavailable ≠ 0`）；
4. **端到端结果的 `reading_context`**：`result` 与 `environment_skipped` 一个都没被「洗白」；
5. **每轮 R-d**：判定载荷、`VERDICT` 行、`policy.check --json` 的逐字节差集必须是 0 条（除预注册的「会变」项）。

## 退出条件（进入「升格」或下一阶段的条件）

1. 只报告读数的**升格**必须先满足它自己的 `promote_when`（与 L5 同型：跑过 N≥1 次且 0 命中，
   且 0 命中来自**至少一次真实读数**），再走一轮 `warn + 非零退出`，最后由一次**显式提交**
   改判据/版本轴/门禁步骤表；
2. 缺口第 1–7 条逐条关闭或由评审裁定**不做并写明理由**；
3. 2026-12-31 复审**有结论**（升格 / 继续只报告 / 改形态），且结论落进 tracked 文档；
4. **在此之前**：本阶段的一切读数**只报告**，不得作为任何 allow / block 的输入。

## 未核实

1. **并发对照没有重跑**：排他锁「抢不到即退 1」的机制在代码与纪律里，本轮**没有**造一次并发运行来复现它；
2. **门禁运行的完整次数**：登记在案的是**已归档**的运行（第 17–30 轮），
   `--hook` 形态与未归档的运行无法从归档里数全；
3. **GitHub Actions 上的读数**：C1/C3 的读数依赖宿主与仓库内容（本机 101 / 114），**不要照抄**；
4. **远端状态**：本会话不 `fetch`，远端跟踪引用与远端此刻是否一致**未核实**；
5. **`.tmp/e2e/` 的原件不是长期证据**：登记的是「存在过且被复核过」，cleanup 之后只能靠本节的 sha256 复核。

---

**本文件是本轮（2026-10-03 收尾轮）的第一个交付物**；同轮的 23 号 §22、方案 §7.2 与两处索引同步更新
**只改文档**：对 `src/` / `tests/` / `tools/` / `validation/` / `adapters/` / `.github/` 的差集是 **0 行**。

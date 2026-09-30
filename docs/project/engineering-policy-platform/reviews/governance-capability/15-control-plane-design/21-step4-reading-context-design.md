# 21 · 台阶 4 · `reading_context` 设计稿（**只写文档，不写代码**）

- **执行**：2026-09-30（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；写这份稿子时的 HEAD = `641b4ec`（本轮第 1/2 步的合并提交与裁定提交已落地）。
- **依据**：方案 §3.5（顶层键白名单里就有 `reading_context`）与 §4 台阶 4；17 号 §2.3 第 2 条
  （`reading_context` 判成「建机制（薄）」）与 §8（两项待建项）；18 号 §2（`tool.pytest` 的
  第 55 条核查与 R4 缺口）；19 号 §3 / §3.1（端到端「真机 pass / 受限沙箱 skipped」与四条旁证）；
  AGENTS 第 45（仪器要能失败）/46（违规则清单）/48（证据属于哪棵树）/50（口径诚实）/
  55（加键就是改协议）/56（义务账）条。
- **本文件是什么**：台阶 4 里 `reading_context` 这一件的**设计稿**——哪些读数要带它、每项要加哪些键、
  各自触发哪条版本轴、消费方是谁、R-d 的**预注册形状**、以及预算估计。
- **本文件不是什么**：不是开工单，也不是排期。**本文件没有改任何代码、任何载荷、任何数据文件**；
  台阶 4 的机制（`governs` 轴、声明差集、仪器自证 R-h、写权租约）依旧按 D-2 冻结，本稿只覆盖
  `reading_context` 这一件。
- **2026-09-30 补记**：§9 的四项"请评审裁定"已由使用者裁定，逐条写在 **§9.1**；落地读数见同目录
  [23 号](23-round20-reading-context-landing.md)。本稿其余部分**保持裁定前的原文**，不回改。

---

## 0 一句话

`reading_context` 的职责只有一句：**让「这份读数属于哪棵树、哪一个环境、哪一套声明」与读数同时出现**。
它回答的是**归属**，不是**结论**——`result` / `decision` / `exit_code` 一个都不由它决定，
它也不改变任何 allow / block。本稿把要带它的读数逐项列出来（§2）、给出统一形状（§3）、
版本轴与同批改动（§4）、判定不变的预注册差集（§5）、消费方（§6）、落地顺序（§7）与预算（§8）。

---

## 1 它要回答什么（三个问题 + 判据 + 已有的反例）

### 1.1 三个问题

| # | 问题 | 为什么非有不可 |
| --- | --- | --- |
| Q1 | **哪棵树** | 同一条命令在两棵树上得到两个结论不是缺陷，**没写清是哪棵树**才是（AGENTS 第 48 条）。证据属于哪棵树这件事，`pre_evidence` 的 `tree` 段（`scope` / `target_existed_before` / `tree_digest` / `tree_gaps`）已经有一套词汇——`reading_context` 复用它，不造第二套（第 50 条：同名两义一律改名） |
| Q2 | **哪一个环境、哪一台宿主** | 19 号 §3.1：**同一个工具在两处的结论差别可以只来自环境**（真机 `result=pass`；受限沙箱 `result=skipped`、`environment_skipped=true`）。不写环境，这两条读数会被读成同一件事 |
| Q3 | **哪一套声明（版本）** | 18 号 §2 的 R4：Hook 侧审计摘要里**没有**注册表摘要，于是同一条 `tool.pytest@1.0` 在账本里对应三种行为（H4 之前 / H4 之后 / 台阶 3b 之后）。声明版本不随读数出现，读数就只能靠一个字面量猜行为 |

### 1.2 判据（可证伪）

1. **反面判据（今天就能验）**：把真机 pass 原件与受限沙箱 skipped 产物并排读，**只靠现有键**
   能不能回答「它们是不是同一台宿主、同一个环境」——答不出，这一项就还没有 `reading_context`；
2. **正面判据**：任何一份带 `reading_context` 的读数，必须能只凭载荷本身回答 Q1–Q3，
   **不必**去读产生它的那次运行的日志；
3. **不改变的判据**：`reading_context` 落地前后，`decision` / `violations` / `pending_findings` /
   `matched_rules` / `skipped_rules` / `required_action` **逐个相同**（R-d，见 §5）。

### 1.3 纪律（先写下来，免得落地时走样）

- **只放引用，不放正文**：要摘要、相对路径、枚举与布尔；不放文件内容、不放凭据、
  **不放绝对路径**（第 16/34 条的脱敏纪律；仓库外的隔离根按仓库相对路径或 `<outside-workspace>` 记）；
- **取值必须来自本次运行的真实读数**：取不到写 `unavailable` 并说明，**绝不写一个「看起来像」的常量**
  （第 19 条对证据的同一条纪律，延伸到读数）；
- **不适用与读不到要分开**：沿用义务账的 `applicable` 口径（第 56 条）与检索层的三态纪律，
  每个子块带 `status ∈ {available, unavailable, not_applicable}`，`null` 只表示该字段不适用；
- **不进判定输入**：`reading_context` 是**旁注**。尤其**不许**进 `EvidenceBundle` / `PipelineReport`
  （第 19 条要求「相同输入得到逐字节相同的证据」，塞进 run id / 宿主 / 墙钟就再也做不到）——
  这条是**否定性结论**，见 §2.7。

---

## 2 逐项：哪些读数要带 `reading_context`

指令点名四类（`policy.check --json`、Hook 审计记录、只报告步骤、端到端结果），本稿另加两类
**同类读数**（覆盖账报告、阶段证据），因为它们的读者问的是同一个问题；第 7 类（验证器证据）
是**明确不加**的。

### 2.1 `policy.check --json`（外层包装）

**现状**（`src/policy/check.py` 的 `render_json`，逐键读过）：顶层键 = `check_volume` / `context` /
`rule_set` / `reported_imports` / `evidence` / `exit_code` / `layer_source` / `output_schema_version`（`"1.1"`）/ `result`。
已经能追溯的：`rule_set.identity`（规则集哈希）、`rule_set.schema_version`、
`evidence.configs.registry`（`sha256:…`，与 `validation/validators.yaml` 的 sha256 逐字符相同，18 号 §2 的 R1/R2）、
`check_volume`、`layer_source`。
**缺的**：这份 JSON 是被**哪个入口**在**哪棵树**上算出来的。同一个 `render_json` 被 CLI、
Phase 2 Hook、Phase 6 Runtime、Policy API 与学习手册共用，产物却长得一模一样。

**要加的键**（顶层，一个对象）：

```json
"reading_context": {
  "source": "cli",                     // cli | hook | phase6-runtime | api | library | gate
  "tree": {"scope": "workspace", "digest": "sha256:…", "revision": "<40 hex>"},
  "declarations": {"registry": "sha256:…", "test_layout": "sha256:…", "adapter_config": "sha256:…"},
  "host": {"platform": "Windows-11", "python": "3.13.11", "sandbox": "restricted"}
  // 没有 run：2026-09-30 裁定①——这一份要保持"输入的纯函数"，见下面的键表与 §9.2
}
```

> **2026-09-30 裁定① 之后的实际形状**：这一份 `reading_context` 只有 **4 个键**
> （`source` / `tree` / `declarations` / `host`）——其余五处读数仍是 §3 的 5 个键。
> 判据与落地读数见 23 号 §8 / §9。

| 键 | 取值来源（不许另算） | 备注 |
| --- | --- | --- |
| `source` | 调用点显式传入的枚举 | 默认 `library`；**不猜**（AGENTS 核心约束 6：上下文只接受显式字段） |
| `tree.digest` / `tree.revision` | `provenance.worktree.workspace_tree_digest`（轮次级封条，带**声明的排除项**；**不是** `evidence_tree_digest`——后者不带排除项，实测在本仓库要走 20339 个文件 / 53.6 s，且 `.tmp` 一写指纹就变）+ `git rev-parse HEAD` | 取不到写 `status: unavailable` + 原因（2026-09-30 与实现对齐，见 §9.2 末行） |
| `declarations.registry` | `validators.pipeline` 的 `config_digest()`（`sha256:` 前缀，契约测试已钉） | 与 `evidence.configs.registry` **同一个值来源** |
| `declarations.test_layout` / `adapter_config` | 同名配置文件的摘要 | Hook 路径才有；CLI 路径可为 `not_applicable` |
| `host.sandbox` | `restricted` / `unrestricted` / `unknown` | **只报事实**：判据见 §2.4（受限 = 写工作区外被拒） |
| `run.id` / `started_at` | 本次进程生成 | **这一份不带它**（2026-09-30 裁定①：加上它 `--json` 就不再是输入的纯函数，而 CLI 包装层被要求逐字节可重现，且没有消费方读它）；其余五处读数保留；无论哪一份都**不进证据**（§2.7） |

**版本轴**：`policy.check.OUTPUT_SCHEMA_VERSION` **1.1 → 1.2**（顶层加键 = 改协议，第 55 条）。
**同批要改的引用点**：`tests/integration/test_cli.py`（3 处断言）、`README.md`（2 处）、
`docs/project/architecture/使用说明.md`、学习手册 phase-0 的生成物（`docs/project/learning/phase-0/walkthrough.{py,ipynb}`）
与它的**内容源** `tools/build_learning_notebook.py`（生成器改完要重跑，`--check` 是门禁）。
**消费方**：CLI 使用者与评审、学习手册、契约测试、将来的控制面报告；它们都按固定键读，
**加键不会坏**，坏的是「版本号没动」这件事本身。

### 2.2 Hook 审计记录（**含已登记的 `tool.pytest` 追溯缺口：`AUDIT_SCHEMA_VERSION` 1.2 → 1.3**）

**现状**：`src/adapters/dsh/hooks.py` 的 `_audit()` 固定 9 键（`audit_schema_version`（`"1.2"`）/
`timestamp` / `agent` / `agent_version` / `reason_code` / `exit_code` / `executed` / `elapsed_ms` /
`rule_set_hash`）加上本次判定记录的键；`pre_evidence` 段的键见 `pre_evidence._summary()`
（`status` / `registry_resolution` / `validators_requested` / `checks` / `language_coverage` /
`served_checkers` / `validators` / `judgements` / `pending_implementation` / `blockers` / `target` /
`target_sha256` / `proposal` / `evidence_count` / `dependencies` / `unmapped_findings` /
`truncated_evidence` / `files_copied` / `tree`）。

**缺口**（18 号 §2 的 R4，本轮归到这里）：这份摘要**没有注册表摘要**——`registry_resolution`
只说「怎么解析 `registry_root`」，说不了「解析到的是哪一版 `validation/validators.yaml`」。
于是同一条 `tool.pytest@1.0` 在账本里对应三种行为。**升 `tool.pytest` 的名字修不了它**
（改名不等于给出摘要），真正的处置是**给摘要加摘要键**。

**要加的键**：

| 键 | 位置 | 取值来源 |
| --- | --- | --- |
| `pre_evidence.registry` | `pre_evidence` 摘要内 | `{"path": "validation/validators.yaml", "digest": "sha256:…", "declared_in": "<adapter 配置里的键名>"}`；`digest` 与 `policy.check --json` 的 `evidence.configs.registry` **同源** |
| `reading_context` | 审计记录顶层 | §3 的统一形状；`source="hook"`，`tree` 直接**引用**本记录 `pre_evidence.tree` 的同一组值（`scope` / `tree_digest`），不另算一遍 |

**版本轴**：`AUDIT_SCHEMA_VERSION` **1.2 → 1.3**（已登记的代价：**5 处测试断言**
（`tests/integration/test_validator_cli.py`、`tests/integration/test_dsh_pre_evidence_hook.py`、
`tests/unit/test_validator_pending_implementation.py`）与 **14 处文档读数引用**，另有生成物
（学习手册 phase-2 的 `walkthrough.{py,ipynb}`、`docs/project/architecture/tech-detail/02-dsh-Hook-内部流程/`
的 `cells.py` 与生成物**逐字列出了审计键**）——全部同批改，见 18 号 §2 与 §4）。
**消费方**：`tools/dsh_sandbox_loop.py` 的 `describe()`（读固定键，加键不坏）、
`tests/unit/test_hook_skip_visibility.py`（断言版本号）、`tools/build_learning_notebook.py`、
tech-detail 生成器、账本读者（人 / 评审 / 事故复盘）。

**2026-09-30 落地（第 22 轮）**：本节按上面的形状落了码——`AUDIT_SCHEMA_VERSION` `1.2 → 1.3`，
`_audit()` 顶层多一份 `reading_context`（`source="hook"`；`tree` **引用**本记录
`pre_evidence.tree` 的 `scope` / `tree_digest`，**不另算**；`declarations.registry` 与
`pre_evidence.registry` 共用**同一个** digest；`declarations.test_layout` 写 `not_applicable`），
`pre_evidence` 摘要内多一份 `registry`（`{path, digest, declared_in}`，`digest` 取自
`validators.pipeline` 已经算好的 `report.configs["registry"]`，**不另算**）。
两条**与本节预注册形状的偏离**如实写下来、请评审裁定：① `tree` 只有 `status` / `scope` / `digest`，
**没有 `revision`**（`git rev-parse HEAD` 单次实测 **48.4 ms**，占满本台阶 50 ms 的增量预算；
且受控项目常常不是 git 工作树，取不到会是常态）；② `host.sandbox` 恒为 `unknown`
（Hook 不探测沙箱，与 §9.2 裁定④对 `check` 路径的口径相同）。
三条硬约束的读数与 R-d 差集见 [23 号](23-round20-reading-context-landing.md) §11。

### 2.3 只报告步骤（三处读数）

`ci_local.py` 的 `REPORT_ONLY_STEPS` 今天有两条：**义务门禁**与**豁免到期检查**；
它们的读数有三条出口：机器载荷（`--json`）、文本机器行、以及 `ci_local` 自己打的 `REPORT-ONLY:` 行。

| # | 读数 | 今天的样子 | 要加的键 | 版本轴（第 55 条） | 消费方 |
| --- | --- | --- | --- | --- | --- |
| a | `tools/obligations_gate.py --json` | 顶层 `report_schema_version="1.1"` / `tree` / `applicable` / `hits` 一族 | `reading_context`（`source="gate"`、账本路径（仓库相对）、树摘要、宿主） | `tools.obligations_gate.REPORT_SCHEMA_VERSION` **1.1 → 1.2** | `ci_local.report_only_hits()`（读 `hits` 键）、`tests/integration/test_obligations_gate.py`、评审 |
| b | `tools/exemption_expiry.py` | 默认输出一句稳定的 `HITS:` 机器行；`--json` 载荷**没有版本轴** | `reading_context` **只进 `--json`**；文本行**一个字符都不改**（`ci_local` 按前缀 `HITS:` 读，格式是跨文件契约） | **首次引入** `EXEMPTION_REPORT_SCHEMA_VERSION = "1.1"`（AGENTS 第 55 条本轮已登记「第一次改键时引入 1.1」） | `ci_local.report_only_hits()`（文本回退路径）、`tests/unit/test_exemption_expiry.py` |
| c | `ci_local` 的 `REPORT-ONLY:` 行 | `REPORT-ONLY: <名字> —— <verdict>；读数 …；豁免到期 …（日志：…）` | 要不要在这行里带上「哪棵树 / 哪个宿主」**请评审裁定**（§9 第 2 条） | 这行是**控制台文本契约**，没有版本轴；它被 `tests/unit/test_ci_local_report_only.py` 钉住 | 本机门禁的读者；**归 CI 线**（`tools/ci_local.py` 本轮一个字都不许动） |

**为什么只报告步骤尤其需要它**：这两条读数的**唯一**作用就是给升格判据（L5：跑过 N≥1 次且 0 命中）
提供一次**真实读数**。一次读数属于哪棵树、哪个宿主、哪个账本，直接决定它能不能计入判据——
没有上下文，「0 命中」与「没读到账本」在文本里长得非常像（第 56 条已经为此把 `applicable` 单独拆出来）。

### 2.4 端到端结果（`.tmp/artifacts/phase-2-sandbox-result.json`）

**现状**：本轮刚给它建立版本轴 —— `tools.dsh_sandbox_loop.SANDBOX_RESULT_SCHEMA_VERSION = "1.1"`，
两条写盘路径（完整跑 / dsh 不可用）都带 `schema_version`（提交 `641b4ec`）。
**要加的键**（1.1 → 1.2）：

| 键 | 取值来源 | 为什么是它 |
| --- | --- | --- |
| `reading_context.source` | 常量 `"sandbox-loop"` | 与其他载荷同一个枚举 |
| `reading_context.host.sandbox` | 本次是否发生过「写工作区之外被拒」 | `restricted` / `unrestricted` / `unknown`——19 号 §3.1 的那条 skipped 就属于 `restricted` |
| `reading_context.host.isolated_home` | `--isolated-home` 开关的取值 | 19 号 §3.1 的**成立条件**就是它：`DSH_HOME` / `TEMP` / `TMP` 指到受控项目**之外**；不写它，pass 原件复现不出来 |
| `reading_context.host.dsh_home` / `temp_roots` | 本次子进程实际拿到的三个值（**仓库相对**；工作区外的写 `<outside-workspace>`） | 「哪台宿主、哪个环境」的可判定形态 |
| `reading_context.tree.digest` | 受控项目或仓库的树摘要 | Q1 |
| `reading_context.declarations.adapter_config` | 受控项目 `.policy/dsh-adapter.yaml` 的摘要 | Q3（这次读数出自哪一套声明） |

**硬约束**：`result` / `environment_skipped` / `dsh_startup_denied_*` / `hook_spawn_denied_*` /
`dsh_config_failure_*` **一个都不改**。`reading_context` 只回答「这份读数属于哪里」，
**绝不**把 `skipped` 洗成 `pass`、也绝不替代 `environment_skipped`（第 45 条：环境跳过不是通过）。
**版本轴**：`SANDBOX_RESULT_SCHEMA_VERSION` **1.1 → 1.2**。
**消费方**：`tools/phase_evidence.py` 的 `sandbox_loop()`（逐键 `.get()`，**不依赖键集合**，
本轮的探针已证：三种键集合喂进去输出逐字节相同）、`.tmp/e2e/` 下的人工复核副本、评审。

### 2.5 覆盖账报告（`python -m adapters.cli wiring --json`）

**现状**：`src/adapters/wiring.py` 的 `WIRING_SCHEMA_VERSION = "1.1"`；顶层有 `wiring_schema_version` 与
`channels` 一族。方案 §3.5 的顶层键白名单（`account` / `differences` / `channels` / `reading_context` /
`headline`）里，`reading_context` **本来就是它的原位**；17 号 §2.3 第 3 条实测 `account` / `differences`
读不到（`null`）。
**要加的键**：顶层 `reading_context`（§3 的统一形状，`source="gate"`），其中
`declarations.wiring_scope` = `adapters/wiring-scope.yaml` 的摘要（那是「哪些通道按声明不治理 / 到期日」
的**唯一**声明处）。
**版本轴**：`WIRING_SCHEMA_VERSION` **1.1 → 1.2**。
**消费方**：`adapters/cli.py` 的使用者与评审、17 号那两份整数清单的复核者、
契约测试；`tools/exemption_expiry.py` 读的是**声明文件本身**（YAML），不是这份 JSON，因此不受影响。
**与冻结的关系**：`reading_context` 与 `governs` 轴、声明差集同属覆盖账，一起落最自然；
但在 D-2 解冻之前本稿**只给形状**，不动 `account` / `differences`。

**2026-09-30 落地（第 21 轮）**：本节按上面的形状落了码——`WIRING_SCHEMA_VERSION` `1.1 → 1.2`，
`--json` 顶层多一份 `reading_context`（`source="gate"`；`declarations` 只放 `wiring_scope` 一项，
不把每通道一份的 adapter 配置混进"哪一套声明"；树摘要用 `workspace_tree_digest`），实现是
`adapters.wiring.build_reading_context`（形状仍只有 `src/provenance/reading_context.py` 一份）。
**它只进 `--json`**：人类可读输出与 `--check` 的判据一个字段都不读它（不改通道状态 / result /
退出码），并且**保留 `run`**（21 号 §9.2 裁定①只对 `policy.check --json` 生效）。
D-2 冻结的部分（`account` / `differences` / `governs` 轴）**照旧不动**。落地读数见 23 号 §9。

**2026-10-01 落地（第 24 轮：24 号设计稿 + §8.3 裁定②③④⑤）**：`WIRING_SCHEMA_VERSION`
`1.2 → 1.3`——顶层**只**新增 `account` / `differences` / `headline` / `red_conditions`
四个键（既有 13 个一个不删不改名），每个通道新增 `governs` 分档（显式 `covers` 优先 →
`channel_kinds` 的 kind 档兜底 → 同档冲突写 `undeclared`、**不猜**）；
`red_conditions.in_scope_not_wired` 就是那条红条件的**预注册形态**（`enforced: false`，
不进任何退出码）。声明侧：`adapters/wiring-scope.yaml` 升 `schema_version: "2"` 并登记
`channel_kinds`，`provenance.wiring_scope` **同时接受 "1" 和 "2"**、新字段一律可选、
**不新增任何加载期 FATAL**（裁定①）。**只报告**：`--check` 的判据、退出码与门禁第 24 步
**逐字不变**；三数/差集在"没枚举到通道"或"声明读不到"时写 `unavailable`（带 reason），
**不许写 0**（裁定④）。落地读数见 23 号 §14。

### 2.6 阶段证据（`tools/phase_evidence.py`，**CI 线的文件**）

**现状**：顶层已有 `environment`（`python` / `implementation` / `platform` / `executable`）与
`implementation_version`（git 修订），但**没有统一形状**；更关键的是它按**固定键集合**复制子载荷 ——
本轮实测：把三种键集合（现形状 / 去掉 `schema_version` / 多一个未知键）喂给 `sandbox_loop()`，
输出**逐字节相同**（`.tmp/step2/probe_phase_evidence_keys.py`）。也就是说它既不依赖键集合，
**也不搬运**新键 —— 本轮的 `SANDBOX_RESULT_SCHEMA_VERSION` 目前**读不到**。
**要加的键**：顶层 `reading_context`（§3 形状，`source="evidence"`），并把每个子段的
**版本轴**透传（例如 `sandbox_loop.schema_version`、`validators.evidence_schema_version`），
否则「这份证据里的每段读数各是哪一代」永远只有一个笼统的 git 修订。
**版本轴**：这份报告**自己还没有版本轴**（顶层没有 `schema_version`）→ 登记为
「第一次改键时引入 1.1」（与 `exemption_expiry --json` 同类）。
**归属**：**CI 线**。本稿只提要求，不改它（本轮已把「透传子载荷版本」登记为缺口）。

### 2.7 明确**不加**：验证器证据（否定性结论）

`policy.evidence.EVIDENCE_SCHEMA_VERSION` 与 `validators.pipeline.PIPELINE_SCHEMA_VERSION`（现为 `1.2`）
的载荷要求「相同输入得到**逐字节相同**的证据」（AGENTS 第 19 条：证据里不得出现绝对路径、耗时或凭据）。
`reading_context` 里的 run id / 宿主 / 墙钟一律随运行变化，**塞进去就破掉这条**。
所以：**证据载荷不进 `reading_context`**；证据要回答「属于哪棵树」时，用**已有的**
`tree.scope` / `tree_digest`（内容寻址、稳定，第 48 条），而不是新加一族 run 级字段。
这条否定性结论要写下来 —— 否则下一个人会顺手加。

---

## 3 统一形状（预注册的键集合）

六处载荷用**同一个** `reading_context` 形状（键名相同、含义相同；这正是第 50 条要的「同名同义」）：

```json
"reading_context": {
  "source": "cli",
  "tree": {"status": "available", "scope": "workspace", "digest": "sha256:…", "revision": "<40 hex>"},
  "declarations": {
    "registry": {"status": "available", "path": "validation/validators.yaml", "digest": "sha256:…"},
    "test_layout": {"status": "not_applicable"},
    "adapter_config": {"status": "not_applicable"}
  },
  "host": {"platform": "Windows-11", "python": "3.13.11", "sandbox": "restricted"},
  "run": {"id": "<uuid>", "started_at": "<ISO-8601 Z>"}
}
```

| 规则 | 内容 |
| --- | --- |
| **命名** | 只用上表这 5 个键名（`source` / `tree` / `declarations` / `host` / `run`）；子键名一律复用既有词汇（`scope` / `digest` / `revision` / `platform` / `python`），不发明同义新词 |
| **run 是有条件的**（2026-09-30 裁定①） | 五个键里只有 `run` 随运行变化：凡是被要求"相同输入得到逐字节相同的输出"的载荷，调用点必须显式 **不带 run**（`provenance.reading_context.build(include_run=False)`）；唯一一份这样的是 `policy.check --json`，其余五处照旧带 |
| **三态** | 每个可取不到的子块带 `status ∈ {available, unavailable, not_applicable}`；`unavailable` 必须带 `reason`（一句话，可读），`not_applicable` 不带 |
| **不猜** | `source` 由调用点显式传入；推导不出来的字段写 `unknown` / `unavailable`，**不许**从文件名、目录或宿主名反推（核心约束 6） |
| **脱敏** | 路径一律仓库相对；工作区之外的根写 `<outside-workspace>`（第 16/34 条）；不放凭据、不放正文 |
| **消费者** | 一律 `.get()` 读（现有消费方全都如此），未知键不报错；但**生产者加键必须先动版本轴**（第 55 条） |
| **不进判定** | `reading_context` 不参与 `policy.engine.evaluate` 的任何输入；判定路径不得读它 |

**新增枚举**（本稿唯一的新词）：`host.sandbox ∈ {restricted, unrestricted, unknown}`；
判据方向：本次运行中**是否发生过「沙箱 / 宿主拒绝了工作区之外的操作」**（受限 = 是）。
**2026-09-30 裁定③ 同步**：把**禁止管道 stdio 的 spawn 拒绝**（`sandbox_pipe_stdio_denied`，
Hook spawn EPERM）也算进 `restricted`——把它记成 `unrestricted` 是一句没有依据的话
（原判据只写"写被拒"，实现比它宽一档，这里按实现收口）。这条判据在 Windows ACL 沙箱上
有现场读数（19 号 §3.1、23 号 §3.4），在 POSIX 上的判定**未核实**（§9 第 4 条）。

---

## 4 版本轴与同批改动清单（第 55 条）

| # | 载荷 | 现版本 | 目标 | 同批要改的引用点 | 归属 |
| --- | --- | --- | --- | --- | --- |
| 1 | `policy.check --json` 外层包装 | `OUTPUT_SCHEMA_VERSION = "1.1"` | **1.2** | `tests/integration/test_cli.py`（3 处）、`README.md`（2 处）、`docs/project/architecture/使用说明.md`、学习手册 phase-0 的生成物与其内容源 `tools/build_learning_notebook.py` | 本线 |
| 2 | Hook 审计记录 | `AUDIT_SCHEMA_VERSION = "1.2"` | **1.3** | 5 处测试断言 + 14 处文档读数（18 号 §2）+ 学习手册 phase-2 生成物 + `tech-detail/02-dsh-Hook-内部流程` 的 `cells.py` 与生成物 | 本线（含生成物重跑） |
| 3 | 义务门禁报告 | `REPORT_SCHEMA_VERSION = "1.1"` | **1.2** | `tests/integration/test_obligations_gate.py`、`ci_local` 里那条 `reads` 文案（CI 线） | 本线 + CI 线 |
| 4 | `exemption_expiry --json` | **没有轴**（本轮已登记） | **1.1（首次）** | `tests/unit/test_exemption_expiry.py`；**默认输出的 `HITS:` 行一个字符都不改** | 本线 |
| 5 | 端到端结果 | `SANDBOX_RESULT_SCHEMA_VERSION = "1.1"`（本轮建） | **1.2** | `tests/integration/test_dsh_sandbox_loop.py`、`tools/README.md` 那一行、19 号 §3.1 的回指 | 本线 |
| 6 | 覆盖账报告 | `WIRING_SCHEMA_VERSION = "1.1"` | **1.2** | `tests/` 里读 wiring 载荷的用例、17 号 §2.3 | 本线 |
| 7 | 阶段证据报告 | **没有轴**（本轮登记为缺口） | **1.1（首次）** | `tests/unit/test_phase_evidence_suites.py`、`tools/README.md` 那一行 | **CI 线** |
| 8 | `ci_local` 的 `REPORT-ONLY:` 文本行 | 无轴（控制台契约） | —— | `tests/unit/test_ci_local_report_only.py`（CI 线） | **CI 线** |

**硬规则**：同一行的「同批」= **一个提交**（第 55 条要求写死版本号的引用点在同一个提交里改完）；
跨线的行（3 / 7 / 8）必须**两条线同时在评审里出现**，不许一边先合、另一边后补。

---

## 5 R-d 预注册形状（落码后逐条核对）

**仪器**：台阶 3b 那一台（`.tmp/step3b/probe_decisions.py` 只调 `policy.engine.evaluate`；
`.tmp/step3b/json_field_diff.py` 做字段级差集），**before 侧必须在动手之前采集**（18 号 §3 的做法）。
`reading_context` 只加在**包装层 / 记录层**，所以要把「判定路径」与「包装层」两把尺子分开量：

| # | 尺子 | 场景 | 预期差集 | 硬约束 |
| --- | --- | --- | --- | --- |
| R1 | 判定载荷（3b 那台，10 个场景：四种 decision + pending 一族 + 审批门禁 + 失败关闭对照） | `s1`–`s10` | **每个场景 0 条** —— `reading_context` 不进决策载荷 | 出现任何一条 = 违反了「包装层改动不碰判定」这条设计约束，回退该步 |
| R2 | `policy.check --json` 包装层（**需要新增一台探针**：同一份输入跑 CLI 入口，采集整份 JSON） | 至少 3 个入口（allow / block / 带证据） | 每个入口 **2 条**：`payload.reading_context: 新增`、`payload.output_schema_version: "1.1" → "1.2"` | 除这两条外多出任何键 = 预期外改动 |
| R3 | Hook 审计记录（真 Hook 路径，`pre_evidence` 开启） | 一次 allow、一次 block | 每条 **3 条**：`pre_evidence.registry: 新增`、`reading_context: 新增`、`audit_schema_version: "1.2" → "1.3"` | `decision` / `violations` / `pending_findings` / `served_checkers` / `pending_implementation` **不得出现**在差集里 |
| R4 | 端到端结果 | 真机 pass / 受限沙箱 skipped 两份 | 每份 **2 条**：`reading_context: 新增`、`schema_version: "1.1" → "1.2"` | `result` / `environment_skipped` / 两个 scenario 的 `passed` / 全部诊断键**不得出现**在差集里 |

**2026-09-30 裁定② 补记（R4 的真产物对照）**：R4 是四把尺子里唯一一把要拿**真产物**比的
（端到端结果由别的上下文写出：pre-push 钩子、另一次会话的门禁）。**补一条硬要求：真产物对照
必须同环境**——两份产物若来自不同上下文，`DSH_HOME` 在不在之类的环境差异会以**诊断键**的形式
出现在差集里（23 号 §4.5 的读数就是 4 条 = 2 条预注册 + 2 条环境归因漂移）。**做不到同环境时，
条数判据以合成探针为准**，真产物上只做弱对照（硬约束那几个字段在不在差集里）——
"差集几条"这个判据在跨环境的真产物上不成立，把它当成改动带来的差异是错的。

**共同的硬约束（违反即回退该步）**：四个尺子的差集里出现
`decision` / `violations` / `pending_findings` / `matched_rules` / `skipped_rules` / `required_action`
任何一个字段，都算 R-d 违约 —— 这条与 13 号 §5.4、14 号 §2 的既有口径**逐字一致**。

**未预注册的部分照实写**：R2 那台探针**今天不存在**（3b 的仪器停在引擎层），
落地第一件事是把它建出来并先用**未改动的树**跑一次「自己对自己」的对照（差集 0 条），
证明这把尺子在量东西（13 号 §5.3 的做法）。

---

## 6 消费方总表

| 载荷 | 消费方 | 读法 | 加键会不会坏 | 前置版本轴 |
| --- | --- | --- | --- | --- |
| `policy.check --json` | `tests/integration/test_cli.py`、学习手册、`README.md` 的示例、CLI 使用者 | 固定键 + 版本断言 | 不会（但版本断言要先改） | `OUTPUT_SCHEMA_VERSION` |
| Hook 审计记录 | `tools/dsh_sandbox_loop.py` 的 `describe()`、`tests/unit/test_hook_skip_visibility.py`、学习手册与 tech-detail 生成器、账本读者 | 固定键 / 逐字列键 | 生成物会漂 → 必须重跑生成器 | `AUDIT_SCHEMA_VERSION` |
| 义务门禁报告 | `ci_local.report_only_hits()`（读 `hits`）、`tests/integration/test_obligations_gate.py` | 单键 / 全载荷 | 不会 | `REPORT_SCHEMA_VERSION` |
| 豁免到期读数 | `ci_local.report_only_hits()`（**文本 `HITS:` 行**）、`tests/unit/test_exemption_expiry.py` | 文本前缀 + `--json` | 文本行不许动；`--json` 加键要建轴 | 新建 1.1 |
| 端到端结果 | `tools/phase_evidence.py` 的 `sandbox_loop()`、`.tmp/e2e/` 复核副本 | 逐键 `.get()` | 不会（本轮已用探针证明不依赖键集合） | `SANDBOX_RESULT_SCHEMA_VERSION` |
| 覆盖账报告 | `adapters/cli.py` 使用者、17 号清单复核者 | 逐键 | 不会 | `WIRING_SCHEMA_VERSION` |
| 阶段证据 | 评审、CI 归档 | 逐键 | **会丢**：子载荷新键不被搬运（本轮实测） | 需先建自己的轴 |

---

## 7 落地顺序（**不新增阻断步骤**）

1. **每项单独提交**；每项落地前按 §5 的预注册形状采集 before，落地后核对差集；差集非预期 → 回退该项；
2. **不新增任何阻断步骤**、**不改任何退出码**、**不把任何 `skipped` 变红**：本机制只加旁注，
   不引入加载期 FATAL，因此**不需要 L5 的 warn 期**（与台阶 5 的合并谓词不同）；
3. 建议顺序（按「读者最稳、改动面最小」排）：
   ① 端到端结果（1.1 → 1.2）→ ② 只报告两处（义务门禁 1.1 → 1.2；豁免到期首建 1.1）→
   ③ `policy.check --json`（1.1 → 1.2）→ ④ 覆盖账（1.1 → 1.2）→ ⑤ Hook 审计（1.2 → 1.3，
   改动面最大，含生成物重跑）→ ⑥ 阶段证据（**CI 线**）；
4. 跨线的 ③/⑤/⑥ 落地时，`tools/ci_local.py` 的 `reads` 文案与 `REPORT-ONLY:` 行由 **CI 线**同批处理。

---

## 8 预算估计（**原上限 × 2.5 为硬上限**）

**上限（方案 §7.1 的 ×2.5 表 + 2026-09-30 补记：按台阶累计）**：

| 桶 | 原估 | 原上限 | 复核线（1.5×） | **硬上限（×2.5）** |
| --- | --- | --- | --- | --- |
| 台阶 4 · src | 0.5k–1.3k | 1.3k | 1.95k | **3.25k** |
| 台阶 4 · tests | 0.5k–1.4k | 1.4k | 2.1k | **3.5k** |

**已花（本线可归因的提交，`git show --numstat` 读数；口径 = 新增行）**：

| 提交 | 内容 | src | tests | tools | 数据/文档 |
| --- | --- | --- | --- | --- | --- |
| `60f0db5` | 五条写声明（wiring-scope + 文档 + 门禁步骤表） | 0 | 0 | 11 | 115 |
| `6ad7376` | 义务门禁接进本机门禁（只报告 + 到期豁免） | 0 | 275 | 400 | 2 |
| `0fa42d1` | 只报告读数读得懂多行 JSON | 0 | 26 | 35 | 0 |
| `09322b0` | `--isolated-home` + ACL 配置失败分类器 | 0 | 208 | 154 | 0 |
| `35a4ddd` | 豁免到期检查的 `HITS:` 机器行 | 0 | 89 | 22 | 0 |
| `641b4ec` | 端到端载荷建轴（本轮） | 0 | 0 | 19 | 11 |
| **合计** | —— | **0** | **598** | **641** | **128** |

**本稿逐项估算**（区间；口径 = 新增行，不含生成物重跑的机器产出）：

| # | 项 | src | tests | tools | 备注 |
| --- | --- | --- | --- | --- | --- |
| 1 | `policy.check --json` | 80–150 | 120–200 | 0 | 含 `reading_context` 构造与三个调用点 |
| 2 | Hook 审计（含注册表摘要） | 60–120 | 120–220 | 0 | 另有生成物重跑；5 处断言 + 14 处文档 |
| 3 | 只报告两处 | 0 | 80–120 | 90–170 | 其中 `ci_local` 侧 15–30 行归 **CI 线** |
| 4 | 端到端结果 | 0 | 100–180 | 60–120 | 真机 pass / 受限 skipped 两份对照 |
| 5 | 覆盖账 | 60–120 | 80–150 | 0 | 等 `governs` 轴解冻同批 |
| 6 | 阶段证据（**CI 线**） | 0 | 60–100 | 40–80 | 含子载荷版本透传 |
| | **合计** | **200–390** | **560–970** | **190–370** | |

**累计对照**：src 0 + ≤390 = **≤0.39k**，远低于复核线 1.95k；tests 598 + ≤970 = **≤1.57k**
（复核线 2.1k、硬上限 3.5k）——最坏情形仍在复核线内，但已到复核线的 75%，**落地时按累计口径重算**。
**tools 桶在方案 §7 的表里没有**（第 16/17 轮的读数同样单列），这里照旧单列，不与 src 相加。

**口径诚实**：这是**估算**，不是读数；×2.5 这个系数样本 n=2、只校准方案 §7 那张表，不能外推
（方案 §7.1 原话）。落地后按实际 `numstat` 重记，超过 1.5 倍就停下复核。

---

## 9 未核实 / 请评审裁定

**未核实（逐条）**：

1. **「14 处文档读数引用」的逐条清单没有重算**：18 号 §2 只给了 3 个测试文件与 14 这个数；
   §2.2 写的「同批改动面」是**引用**，不是重算。
2. **生成物的具体改动面没有跑**：学习手册 phase-2 与 `tech-detail/02-dsh-Hook-内部流程` 的 `cells.py`
   逐字列了审计键（只读可见），但本稿**没有**跑生成器、也没有做 `--check`。
3. **本稿没有跑任何载荷**：§2 的「现状键集合」全部来自代码阅读与既有归档（18/19 号），不是实跑读数；
   唯一实跑的是 §2.6 那台键集合探针（本轮第 2 步的产物）与本轮的门禁读数。
4. **`host.sandbox` 的判据只给了方向**：Windows ACL 沙箱上有现场读数，POSIX 上怎么判**未核实**；
   本轮没有把它做成可判定函数，也没有验证「写工作区之外被拒」以外的形态（例如只读挂载）。
5. **§8 的「已花」按提交归属，没有逐行剔除非台阶 4 的部分**：`6ad7376` 里的义务门禁只报告接线
   同时服务台阶 3c 的 L5 判据；`60f0db5` 的 `wiring-scope.yaml` 是数据不是代码。口径见该表标题。

**请评审裁定（四项；2026-09-30 已裁定，裁定见下表）**：

1. **端到端的「受限宿主不可得」要不要单独留一档读数**（19 号 §3 第 2 行的遗留）：
   选定后 §2.4 的键跟着变——是只加 `host.sandbox` 一个枚举，还是另加一档独立的 `reading_status`；
2. **`ci_local` 的 `REPORT-ONLY:` 行要不要带 `reading_context`**（跨线：`tools/ci_local.py` 属 CI 线，
   本线本轮一个字都不许动）；
3. **阶段证据要不要透传子载荷版本**（CI 线；本轮实测它按固定键复制，新键读不到）；
4. **落地顺序**是否按 §7 拆成六个提交（端到端 → 只报告 → `check` → 覆盖账 → 审计 → 阶段证据）。

### 9.1 裁定（2026-09-30，使用者；由第 20 轮补记进本节）

四条裁定逐条对应上面的四个问题（**原问题一字不动地留在上面**，便于复核"裁定的是不是当初问的那件事"）：

| # | 问题 | 裁定 | 对本文的影响 |
| --- | --- | --- | --- |
| ① | 端到端的「受限宿主不可得」 | **不单独设状态轴**：只在 `reading_context` 里加 `host.sandbox` 枚举（`restricted` / `unrestricted` / `unknown`），**不做** `reading_status` | §2.4 的键集合按此定稿；§3 的"唯一新词"仍是这一个枚举 |
| ② | `REPORT-ONLY:` 控制台行 | **不加** `reading_context` | §2.3 第 c 行关闭：那行仍是纯控制台文本契约，`tools/ci_local.py` 本线不动 |
| ③ | 阶段证据透传子载荷版本 | **交给 CI 线**，本线不做 | §2.6 与 §4 第 7 行继续留在"CI 线待办"，不在本线落地清单里 |
| ④ | 落地顺序 | 按 §7 的次序执行，**本轮只做前三步**：端到端 → 只报告工具 → `policy.check`；**覆盖账与审计（`AUDIT_SCHEMA_VERSION` 1.2 → 1.3）留到下一轮** | §4 的第 2 行（Hook 审计）与第 6 行（覆盖账）本轮**不落地**；§8 的预算按"前三步"重算 |

**四条裁定都不改任何 allow / block、不新增阻断步骤、不改任何退出码**——它们是**范围**裁定
（做哪几件、按什么次序、键加到哪一层），不是判定口径的裁定。落地读数见第 20 轮记录
[23-round20-reading-context-landing.md](23-round20-reading-context-landing.md)。

**裁定之后仍然成立的两条边界**（本稿开头就写下的，不因裁定而变）：`reading_context` 只回答
"这份读数属于哪里"，**不进判定**（§1.3）；**受限宿主不单独设状态轴**不等于"受限宿主可以不写"
——它必须能从 `host.sandbox` 与既有的 `result` / `environment_skipped` 一起读出来（第 45 条：
环境跳过不是通过）。

### 9.2 裁定（2026-09-30 · 第二轮，四项 + 一项对齐）

§9.1 落地（第 20 轮）之后，评审就**落地读数**又裁了四项（问题原文在 23 号 §5.3，
执行读数在 23 号 §8 / §9）。逐条如下，**原问题与 §9.1 一字不动地留在上面**：

| # | 问题（出处） | 裁定 | 对本文的影响 |
| --- | --- | --- | --- |
| ① | `policy.check --json` 里的 `reading_context.run` 留不留（23 号 §5.3 第 1 条） | **去掉**：它违反 AGENTS 第 19 条的同一条纪律（包装层要保持"输入的纯函数"），且没有消费方；1.2 **尚未发布**，所以**在 1.2 内修、不升版**。端到端结果与只报告两处**保留** `run` | §2.1 键表与 §3 的"5 个键"按此收窄成 4 个（见 §2.1 的补记与 §3 的"run 是有条件的"一行）；实现是 `provenance.reading_context.build(include_run=False)`，六处载荷里唯一的一份 |
| ② | R4 预注册要不要补"真产物对照必须同环境"（23 号 §5.3 第 2 条） | **补**：不补的话，跨环境采来的两份真产物会把环境差异算成改动（§5 的 R4 行加补记） | §5 的 R4 判据补一条硬要求；做不到同环境时条数以合成探针为准 |
| ③ | `host.sandbox` 的受限判据要不要收回"只有写被拒才算"（23 号 §5.3 第 3 条） | **不收回**：spawn 拒绝（`sandbox_pipe_stdio_denied`）也算 `restricted` | §3 的判据句同步改（见上） |
| ④ | `check` 路径的 `host.sandbox` 恒为 `unknown`（23 号 §5.3 第 4 条） | **接受**：CLI 不探测沙箱（探测要有副作用），不擅自猜；要让它可读必须另给一条**显式声明**（环境变量或配置），本线不做 | §2.1 的 `host.sandbox` 行不变 |
| 另 | `tree.digest` 的取值口径（与实现对齐） | 用 `workspace_tree_digest`（轮次级封条、带声明的排除项），**不是** `evidence_tree_digest` | §2.1 的 `tree.digest` 行同步改（见上） |

**这五项都不改任何 allow / block、不新增阻断步骤、不改任何退出码**：① 是包装层一个键的收窄，
②③④ 与"另"是口径、判据与预注册措辞的收口。

---

## 10 复现命令（只读或只写 `.tmp`）

```powershell
# §2.1 包装层的现状键与版本
.venv\Scripts\python.exe -c "import pathlib;t=pathlib.Path('src/policy/check.py').read_text(encoding='utf-8').splitlines();print([l.strip() for l in t if 'OUTPUT_SCHEMA_VERSION' in l or 'output_schema_version' in l])"

# §2.2 审计固定键与 pre_evidence 摘要（逐字读，不猜）
.venv\Scripts\python.exe -c "import pathlib;t=pathlib.Path('src/adapters/dsh/pre_evidence.py').read_text(encoding='utf-8');i=t.index('def _summary');print(t[i:i+2400])"
.venv\Scripts\python.exe -c "import pathlib;t=pathlib.Path('src/adapters/dsh/hooks.py').read_text(encoding='utf-8');i=t.index('def _audit');print(t[i:i+1200])"

# §2.3 两条只报告读数（走 ci_local 真正的那条路径，不跑门禁、不取锁）
.venv\Scripts\python.exe .tmp\step1\probe_report_only.py

# §2.4 端到端载荷的版本轴（本轮新增的键；跑过门禁或单独跑过闭环才有这个文件）
.venv\Scripts\python.exe -c "import json,pathlib;p=json.loads(pathlib.Path('.tmp/artifacts/phase-2-sandbox-result.json').read_text(encoding='utf-8'));print(p.get('schema_version'),p.get('result'),p.get('environment_skipped'))"

# §2.6 阶段证据对键集合不敏感（三种键集合 → 输出逐字节相同）
.venv\Scripts\python.exe .tmp\step2\probe_phase_evidence_keys.py

# §8 已花行数的重算
git show --numstat --format=%h 60f0db5 6ad7376 0fa42d1 09322b0 35a4ddd 641b4ec
```

---

**本文件是第 19 轮的第三个提交**（前两个：合并 `feat/rules-and-os-platform`、裁定的代码落地）；
索引见同目录 `README.md`。

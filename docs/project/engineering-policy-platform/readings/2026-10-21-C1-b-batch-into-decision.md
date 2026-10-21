# 2026-10-21 C1-b 批次进判定（opt-in）读数

> 性质：**实现读数**（共享任务 task-4，子会话 `c1b-analyst` 实现 + Lead 复核与真机读数）。
> 依据：new-session-prompt §3.2；05 §3.3 / §4 C1；04 5.46 / 5.68 / 5.88；
> `readings/2026-10-21-C1-a-batch-ledger.md`；`readings/2026-10-21-C1C2C4-adjudication-draft.md` §1。
> 范围：把 C1-a 的「批次只报告」接到 `pre_evidence` 的**判定范围**上，并补齐结算与过滤口径。
> **不改** `policy.engine.evaluate`；改成 opt-in（默认关）；判定路径只在声明打开时变化。

## 0 结论（五句话）

1. **"把同批已提议文件放进取证树"字面不可实现，也不需要**：账本只存 `target` 路径（无内容）；已结算 allowed 的提议
   在下一个 Hook 进程里**已经在磁盘树里**（影子副本就是磁盘副本），未 allowed 的提议没有内容可还原。
   批次的真实入口是 **`PipelineRequest.changed_files`（判定范围）**，不是树内容。
2. **opt-in**：`batch_ledger.into_decision`（默认 `false`）+ `max_targets`（默认 20；0 = 不并任何成员）。
   `false` 时判定与审计与 C1-a 逐字节相同（唯一不可避免的差别是既有键 `batch.schema_version` 的值随账本轴走 1.1）。
3. **版本轴**：`BATCH_LEDGER_SCHEMA_VERSION` 1.0→**1.1**（记录种类与键集合变）；`AUDIT_SCHEMA_VERSION` 1.4→**1.5**
   （`batch.settlement` / `pre_evidence.batch`）。**PIPELINE 1.4 / EVIDENCE 1.2 / 决策 1.1 / HOOK_PAYLOAD 1.0 都不动**——
   草案里的「PIPELINE 或 EVIDENCE 二选一」是假二分：`changed_files` 的取值来源换了，键集合没变。
4. **五道门全绿**：开/关判定逐字节相等；三步门与 `policy.check` 合并判定差集为空；19 条负例不进成员；审计键冻结；
   预算不等式不变（20000+5000<30000）。定向套件 194 passed、更宽 dsh 回归 308 passed。
5. **真机三次 edit 取得**（本机 dsh 0.2.1-rc.2，隔离 `DSH_HOME`，`into_decision=true`）：三改三 succeed，
   第 2/3 次审计的 `pre_evidence.batch.included` 分别含前一次/前两次的目标，最终判定行 `batch.settlement={status:allowed}`。

## 1 裁定（Lead，2026-10-21；对应 design.md §8 的 Q1–Q8）

| 问题 | 裁定 | 理由 |
| --- | --- | --- |
| 同一批的定义 | **A 会话级**：同一 `session_id` 下逐目标折叠（proposal / settle / abandon，最后一条胜出），成员 = settle.outcome=allowed **且** settle.content_sha256 与当前磁盘 sha 一致 | 载荷里没有 turn/batch id（C4 探针已证 `turn-stopping` 只有 `{turn, signal}`）；时间窗被 AGENTS 第 6 条禁止 |
| 未结算 | **R1 逐目标排除** + 审计 `status="partial"` 与排除名单/计数 | 选 R3（阻断）会让 dsh 超时留下的 unsettled 把会话锁到 TTL/人工清理 |
| 被 block 的提议 | **F1 只 allow 进**（blocked 只进账本与 `excluded`） | "已提议"不是"已允许"；进 changed 会为没写成的文件算 missing_tests（假阻断） |
| 范围后果 | **M1 沿用**：批次就是 changed 集（R5 既有语义：有生产变更时 support 作用域不生效） | 最少代码，与 CLI `--changed` 同一条路径；不升 PIPELINE |
| 版本轴 | LEDGER 1.0→1.1、AUDIT 1.4→1.5 | 见 §2 |
| 账本读不出 | **降级 + 显式**：`pre_evidence.batch.status="unreadable"`、`applied=false`、stderr 一行 `BATCH VIEW UNAVAILABLE`，changed 回退单文件，不阻断 | 批次不是授权；阻断只会让坏账本成为锁会话的开关（AGENTS 第 10/52 条的边界） |

## 2 改动面（工作树）

| 文件 | 改动 |
| --- | --- |
| `src/adapters/dsh/batch_ledger.py` | 1.1：`proposal` / `settle` / `abandon` 三种记录；`read_records`；`BatchView` / `batch_view`（逐目标折叠、五类排除、sha 校验、cap、`members_digest`）；`append_settlement` / `append_abandon`；1.0 记录按 proposal 读、永不可结算 |
| `src/adapters/dsh/adapter.py` | `BatchLedgerConfig` 新增 `into_decision=False`、`max_targets=20`；加载期校验（布尔 / 非负整数 / 未知字段仍拒） |
| `src/adapters/dsh/hooks.py` | `AUDIT_SCHEMA_VERSION` 1.5；`_settle_batch`（只在**最终判定行**写，审计 append 之前）；`_audit` 合并 `batch.settlement`；`_pre_evidence` 折叠批次并传 `batch_targets` + `batch_view`；`_batch_write_tools` / `_batch_target_validator` |
| `src/adapters/dsh/pre_evidence.py` | `changed_files = tuple(sorted({event.file} \| members))`；摘要新增 `batch` 块（传入时才有）；`tree` 段一字不动 |
| `src/adapters/dsh/README.md` | §9.2 审计版本沿革补 1.4 / 1.5；§12.11 记录种类、折叠、审计键、失败语义、M1 后果、预算读数 |
| 测试 | 新增 `tests/unit/test_dsh_batch_view.py`（19 例）；`test_dsh_batch_ledger.py` 21→31；`test_dsh_pre_evidence_hook.py` +2（批次视图 + 两步门）；两处审计版本断言 → 1.5 |
| `examples/dsh/dsh-adapter.yaml` | 注释段补 `into_decision` / `max_targets`（示例仍默认关闭） |
| `docs/project/architecture/版本轴登记表.md` | 两条轴登记 1.1 / 1.5（与代码同批） |

## 3 门 1–5（Lead 复核 impl-reading 的读数，不重跑全部）

| 门 | 读数 | 三态 |
| --- | --- | --- |
| 1 `into_decision=false` 判定逐字节相等 | decision / violations / reason_code / exit_code / executed 逐字节相等；审计键差集仍 `{batch_ref, batch}`；`test_into_decision_false_settles_nothing_and_adds_no_new_audit_key` 钉住"不结算、不写 pre_evidence" | 符合 |
| 2 三步门 / 合并判定 | `GATE_OK`：干净夹具 off=on=merged(direct)=CLI（差集空）；加一条无关失败测试时 off=block（`TESTING-002@1`）→ on=allow，**on 与 merged/CLI 差集为空**；R-d off→on 只变 decision 与 violations；`selection.level` support→related 现场证明 | 符合 |
| 3 负例 | 19 例：blocked / unsettled / legacy 1.0 / 未知 schema_version / session 不符 / 绝对或越界 target / cap 截断 / max_targets=0 / sha 不符 / 缺哈希 / 坏行 partial / 当前事件 / 非写类 / 整份读不出，全部不进 `members`，且 `excluded`/`skipped`/`invalid`/`truncated` 有名字或计数 | 符合 |
| 4 审计 | `batch.settlement` 只在声明 + `enabled` + `into_decision=true` 时出现；`pre_evidence.batch` 键集合冻结（10 键）；未声明零新增；`unreadable` 分支如实降级不阻断；`tree.scope` 仍是 `current_disk_tree_plus_proposal` | 符合 |
| 5 预算与耗时 | 20000+5000<30000 仍成立；`batch_view` 3 成员 0.382ms（最大 0.731ms）、20 成员 3.623ms（最大 5.686ms）；真实 Hook 两步 elapsed ≈1.37s | 符合 |

定向套件：**194 passed**（13 文件，`-n0`，55.43s）；更宽 dsh 套件 **308 passed**；import 自检 `ok`；文本规范通过。

## 4 真机三次 edit（Lead 执行，2026-10-21 13:2x）

- 环境：隔离 `DSH_HOME`；app 自带 dsh **0.2.1-rc.2**；受治项目 `.tmp/registry-sync/project`（同步后 registry 1.4 +
  `pre_evidence.enabled=true` + `batch_ledger.enabled=true, into_decision=true, max_targets=20`）；**src 快照**
  `.tmp/c1b-real/src-snapshot`（235 文件，快照 import 自检 `ok`）；凭据只注入启动环境（`refs/DEEPSEEK_API_KEY`，值不打印）。
- 任务：同一会话内三次「先 read 再 edit」——`order_repository.py` → `order_controller.py` → `order_service.py`（各改模块 docstring）。
- 结果：模型回 `3 succeeded`；审计 30 → 56 条（新增 26 条）；三次编辑的最终判定行与服务如下事实：

| 第几次 | `pre_evidence.batch.status` | `applied` | `included` | 最终判定行 `batch.settlement` |
| --- | --- | --- | --- | --- |
| 1 | `empty` | false | `[]` | `{status: allowed}` |
| 2 | `applied` | true | `["src/shop/order_repository.py"]` | `{status: allowed}` |
| 3 | `applied` | true | `["src/shop/order_controller.py", "src/shop/order_repository.py"]` | `{status: allowed}` |

即：**之前已结算 allowed 且内容 sha 与磁盘一致的目标，进入了下一次取证的 `changed_files`**；审计里 `batch_ref`、
`batch.settlement`、`pre_evidence.batch` 三件都出现；`tree.scope` 未变。三次都 `decision=allow`、
`pre_evidence_status=collected`，PostToolUse 全部 `post_validated`。

## 5 偏离与口径（Lead 已接受）

1. **结算只在 `into_decision=true` 时写**（按 Q2 的"false 时审计逐字节不变"）。代价：`false` 部署看不到 settlement；
   要"false 也结算、只是不消费"只需改 `_settle_batch` 的一个条件，但那会让审计多一个键。
2. **settle 只写最终判定行**（`exit_code!=0` 或 record 带 `execution`）：Phase 4 授权行与判决行都会 exit 0，
   每行都写会得到两条 settle。
3. `build_pre_evidence` 多一个 `batch_view` 参数（审计要 excluded/settled/truncated），默认 None = 不写 batch 键。
4. 批次读取放在 hooks 的**外层预算**（pre_evidence + 判定）内，不在 provider 单次 timeout 内；外层预算覆盖它。
5. `append_abandon` 只有库函数、没有 CLI 入口（裁定只要求"能被显式 abandon"，库函数 + 文档已满足；CLI 属后续）。

## 6 未取得 / 残项

1. **`unsettled` 的真机现场未取得**：真机三改全部成功结算；unsettled 只有库内用例（Hook 被 dsh 杀掉/超时才会出现）。
2. **并发同会话追加仍无锁/无 fsync**（C1-a 残项②）：半行会被计成 skipped/legacy，不会当成员；本轮未加锁。
3. **TTL 清理仍在热路径**、未做性能基线（C1-a 残项⑤）；它是维护动作、不改判定。
4. **selection 仍不在审计摘要里**（04 5.67，未授权）：门 2 的 support→related 用 `select_tests` 直接读证明。
5. 真机读数只证明"批次成员进入 changed_files"；`changed_files` 对 pytest 选择的**后果**由门 2 的离线读数与
   04 5.68 的既有读数承担，不在真机上重复。

## 7 回退

- 只要把 `batch_ledger.into_decision` 置 false（或删掉该键）即回到 C1-a 行为；代码回退 = 撤 `hooks._batch_inputs` /
  `_settle_batch` / `pre_evidence` 的 batch 参数 / `batch_ledger` 的 1.1（1.0 记录仍可被新版读作 legacy）。
- 审计与账本轴各回退一级：AUDIT 1.5→1.4、BATCH_LEDGER 1.1→1.0（旧记录不被新读取器当成 allowed）。

## 8 证据指针

- 代码：`src/adapters/dsh/{batch_ledger,adapter,hooks,pre_evidence}.py`；`src/adapters/dsh/README.md` §9.2 / §12.11。
- 用例：`tests/unit/test_dsh_batch_view.py`（19）、`tests/integration/test_dsh_batch_ledger.py`（31）、
  `tests/integration/test_dsh_pre_evidence_hook.py`（批次视图 + 两步门）。
- 原始读数：`.tmp/c1b-analyst/impl-reading.md`、`.tmp/c1b-analyst/gate-reading.json`、
  `.tmp/c1b-real/three-edits.out.txt`（临时；读数本身含逐字引用）。
- 裁定：本文件 §1；04 5.46 / 5.88；05 §4 C1。

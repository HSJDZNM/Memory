# 2026-10-21 C1-a 批次台账（只报告）读数

> 性质：**实现读数**（子会话 `c1a-batch-ledger`，共享任务 task-6）。依据裁定草案 §1 的 C1-a 台阶
> （`readings/2026-10-21-C1C2C4-adjudication-draft.md`）与使用者 2026-10-20 会话的授权。
> 范围：**只报告**——账本不进 `policy.engine.evaluate`，任何 allow / block 都不读它。
> 不提交；不跑 ci_local；测试一律 `-n0`。

## 0 先核对的三件事实（都读代码 / 夹具，不猜）

| 事实 | 证据 | 对本台阶的含义 |
| --- | --- | --- |
| Hook **每次工具调用是一个新进程** | `src/adapters/dsh/hooks.py:557`（AuditLedger 的 docstring："每个 hook 调用都是一个新进程"）、`hooks.py` 的 `_capture` docstring、`src/adapters/dsh/README.md` §3（"代价是每次工具调用都会起一个 Python 进程"） | 批次状态**跨不了进程**，必须落盘；文件路径与并发形状是本台阶的核心设计对象 |
| session id 来自载荷**顶层**字段 `session_id` | `src/adapters/dsh/adapter.py:114-120`（`REQUIRED_PAYLOAD_FIELDS` 第一项就是 `session_id`）、`:1146`（缺字段即拒绝）、`:1310`（`session_id = payload["session_id"].strip()`）、`tests/fixtures/agent_events/dsh/pre-tool-use-edit-allow.json:2`（"sess-demo-0001"） | 账本按 `<session_id>.jsonl` 分文件；**不是** `tool_input` 里的字段，也不是 Hook 的工作目录 |
| `AUDIT_SCHEMA_VERSION` 动手前是 **"1.3"**，不是任务书写的 1.2 | `src/adapters/dsh/hooks.py:152`（改前）；写死版本号的断言只有：`tests/unit/test_hook_skip_visibility.py:312`、`tests/unit/test_hook_audit_reading_context.py:136` 与 `:351`（用常量）；另有 `:328/:348` 的 **1.2 历史记录兼容**用例（那是被读的旧载荷，不是本协议的断言） | 任务书的 "1.2→1.3" 已过时（台阶 4 已把 1.3 用掉）。本轮按同一条统一规则做 **1.3 → 1.4**，三处断言同批改为 1.4 / 常量 |

仓库内其余位置没有写死 `AUDIT_SCHEMA_VERSION` 的断言（`rg 'audit_schema_version|AUDIT_SCHEMA_VERSION'`：
工具侧 0 处、`docs/` 只有历史读数与生成 notebook 的"键存在"断言，后者不做精确键集合比对）。

## 1 改动面（本轮全部未提交）

| 文件 | 改动 |
| --- | --- |
| `src/adapters/dsh/batch_ledger.py`（新增） | 账本文件自己的协议与读写：路径/文件名校验、目标集合摘要、append、读集合、TTL 清理 |
| `src/adapters/dsh/adapter.py` | 可选 `batch_ledger` 配置段（`BatchLedgerConfig`、`_batch_ledger_config`、`_CONFIG_FIELDS`）；默认 `root = <project_root>/.policy/pre-evidence-batches` |
| `src/adapters/dsh/hooks.py` | `AUDIT_SCHEMA_VERSION 1.3 → 1.4`；`book_batch()` 与判定记录装配点（`hooks.py:1823`）；stderr 机器行 `BATCH LEDGER UNAVAILABLE`；`BATCH_LEDGER_NOTE` |
| `examples/dsh/dsh-adapter.yaml` | 追加**注释掉的** `batch_ledger` 段：路径、TTL/保留口径、失败边界；不声明 = 与现在逐字相同 |
| `tests/integration/test_dsh_batch_ledger.py`（新增） | 门 ①–④ + 摘要稳定性 + 会话隔离 + TTL + 配置契约，21 个用例 |
| `tests/unit/test_hook_skip_visibility.py`、`tests/unit/test_hook_audit_reading_context.py` | 写死审计版本号的三处断言改 1.4 / 常量；注释写明 C1-a 的加键 |

没有改 `04/05/06/AGENTS/tools/README`，没有改 `pre_evidence` 的取证树（C1-b 才做），没有动 registry / enforcement。

## 2 设计

### 2.1 账本文件协议（`batch_ledger.BATCH_LEDGER_SCHEMA_VERSION = "1.0"`，新轴）

- 落点：`<root>/<session_id>.jsonl`，默认 `<project_root>/.policy/pre-evidence-batches/<session_id>.jsonl`；
- 追加写、**按 session 分文件**、UTF-8、LF、一条记录一行 JSON；
- 单条记录**恰好六个键**（测试钉住键集合，不许多放正文/判定）：
  `{schema_version, session_id, event_id, tool, target, recorded_at}`；
  `target` 是 Adapter 归一化后的**仓库相对路径**（`event.file`），不含绝对路径；
- `session_id` 直接当文件名：只接受 `[A-Za-z0-9][A-Za-z0-9_.-]{0,127}`、拒绝 `.`/`..`。
  **拒绝而不是清洗**——清洗会把两个会话映到同一个文件，正是本台阶要防的"并发会话互相污染"；
- 读集合时：半行/坏 JSON/未知 `schema_version`/缺 target 的行**跳过并计数**（`skipped_lines` 进审计），
  不让"这批目标"悄悄少一个；文件不存在 = 空集合（"还没有记录"，不是"读失败"）。

### 2.2 `batch_ref` / `targets_digest`

- `targets_digest = sha256("pre-evidence-batch-targets/1.0\n" + "\n".join(sorted(set(targets))))`；
- `batch_ref = sha256("pre-evidence-batch/1.0\n" + session_id + "\n" + targets_digest)`；
- 输入是**写下本次记录之后**该会话文件里已记录的目标集合（先读后写；读失败直接抛，不追加半份集合）；
- **时间不参与摘要**：同一会话、同一批目标两次计算逐字节相同（测试直接比较两次函数结果）；
  加一个新目标必然改变摘要；不同 session 不撞成同一批（session_id 是输入）；
- 同一个 `batch_ref` 即"同一批目标"，可把同一会话的多条记录折叠成一批（草案 §1 的"按 batch 折叠"）。

### 2.3 审计协议（`AUDIT_SCHEMA_VERSION = "1.4"`）

声明 `batch_ledger` 且启用时，判定记录新增：

- 顶层 `batch_ref`（仅 **成功记录** 时出现）；
- `batch` 块：`{schema_version, declared_in, status, recorded, target?, target_count?, targets_digest?, path?, pruned, skipped_lines, reason?, note}`。
  `status` 是闭集四态：`recorded` / `disabled`（声明了但 `enabled: false`）/ `not_applicable`（该动作没有文件维度）/
  `unavailable`（写不进去 / session_id 不是安全文件名 / 读不出来，带 `reason`）；
- `path` 经 `display_path` 渲染（项目内写成 `.policy/pre-evidence-batches/<session>.jsonl`），不放绝对路径；
- **未声明 `batch_ledger` 时一个 batch 键都不加**（"未声明时行为与现在逐字相同"），
  只有 `audit_schema_version` 这个协议版本号跟着全量记录走——这是升版的必然结果，写在测试注释里。

### 2.4 调用点与顺序

`DshPreExecuteHook._decide`：**重放/认领之后、`to_policy_context` 与 evaluate 之前**（`hooks.py:1823`）：

- 放在重放/认领之后 → 同一 `event_id` 的重放不会往账本追加第二条；重放记录也不带 batch 键（没有新提议）；
- 放在判定之前 → **block 的提议也进批次**（block 与 allow 的记录都能回答"这个文件对本会话是否已提议过"）。
  这是 C1-b 要重新裁定的口径（见 §5 第 5 条），C1-a 只负责如实记录；
- `book_batch` 的返回值只 `record.update(...)`，判定路径不读它；`policy.engine.evaluate` 的入参一个字段都没加。

### 2.5 失败边界（只报告通道）

- 账本写入 / 读取 / 文件名校验的任何异常都在 `book_batch` 内被接住（`except Exception`，理由写在 docstring：
  只报告通道的边界是"宁可降级也不许改判定"），**只**产生：
  1) 一行 stderr `[policy] BATCH LEDGER UNAVAILABLE <sanitized reason>`（每事件至多一行，成功不打印）；
  2) 审计里 `batch.recorded=false` + `reason`（脱敏后）；
- 退出码、`decision`、`violations`、`reason_code`、`executed` 全不变（门 ④ 用"关闭账本的同一事件"逐字节对照）；
- TTL 清理失败不影响记录状态（清理是维护动作，删不掉只是磁盘占用）。

### 2.6 落点与清理的安全边界

- **加载期**拒绝 `root` 等于项目根或是它的祖先（`adapter.py:_batch_ledger_config`）：该目录会被追加写 + TTL 清理；
- TTL 清理**只在真实路径的目录名恰好是 `pre-evidence-batches`** 时执行，只删 `*.jsonl`、跳过符号链接、
  永不删本次会话自己的文件；删不掉的单个文件吞掉 OSError。一个写错的 `root`（例如 `.policy/`）因此
  不会把审计 / 台账 / 审批文件当"过期批次"删掉（有用例：`test_pruning_refuses_a_root_that_is_not_the_conventional_directory`）；
- `root` 省略时**从 `project_root` 派生**，不相对配置文件目录——否则把示例配置复制进 `<project>/.policy/`
  之后会变成 `.policy/.policy/...`（该文件头专门写过这个锚点陷阱）。

## 3 开 / 关对比（门 ①）

同一 fixture（`pre-tool-use-edit-allow.json`）、同一 fake 时钟与固定 `_utc_now`、两个独立项目目录：
`batch_ledger` 未声明 vs `{enabled: true, ttl_hours: 24}`。

| 比较对象 | 结果 |
| --- | --- |
| `outcome.decision.model_dump(mode="json")`（含 matched/skipped/violations/pending） | 逐字节相等 |
| `outcome.decision.violations` 逐条 model_dump | 逐字节相等 |
| `exit_code` / `reason_code` / `executed` | 相等（0 / `allow` / True） |
| 决定记录（`reason_code=allow`）键集合 | 开 − 关 = `{batch_ref, batch}`；关 − 开 = ∅ |
| 决定记录其余字段 | 除 `reading_context` 外逐字段相等 |

`reading_context` 被剔除比较，并写明理由：其中 `declarations.adapter_config.digest` 是**配置文件自己**的
sha256，两份 YAML 的差异正是"声明了 batch_ledger"这一行；它是"属于哪套声明"的旁注，不是判定输入
（`adapter_config` 摘要也从来不在 evaluate 的入参里）。

## 4 测试命令与退出码（全部 `-n0`）

```powershell
$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "import adapters.dsh.hooks; import adapters.dsh.pre_evidence; import enforcement.approvals; import adapters.dsh.batch_ledger; print('ok')"
# 每次写入 src/adapters/dsh/** 后都跑：exit 0（出现过一次 exit 0 + "ok" 才算过）

.venv\Scripts\python.exe -m pytest tests/integration/test_dsh_batch_ledger.py -n0 -q
# 21 passed, exit 0

.venv\Scripts\python.exe -m pytest tests/contract/test_policy_hook_chain.py tests/contract/test_dsh_adapter.py tests/integration/test_dsh_origin_attribution.py tests/integration/test_dsh_pre_evidence_hook.py tests/integration/test_dsh_sandbox_loop.py tests/contract/test_dsh_layer_declaration.py tests/integration/test_dsh_enforcement.py tests/integration/test_dsh_hook.py -n0 -q
# 307 passed, exit 0（既有 dsh 契约 + 集成）

.venv\Scripts\python.exe -m pytest tests/unit/test_hook_audit_reading_context.py tests/unit/test_hook_skip_visibility.py tests/unit/test_hook_violation_visibility.py tests/unit/test_hook_failure_isolation.py tests/unit/test_hook_replay_claim.py tests/unit/test_dsh_adapter_config.py tests/unit/test_dsh_obligations.py tests/unit/test_dsh_pre_evidence.py tests/unit/test_dsh_pre_evidence_containment.py tests/unit/test_dsh_budget_inequality.py tests/unit/test_dsh_bridge.py -n0 -q
# 137 passed, exit 0（既有 dsh 相关单元；含两处版本断言）
```

辅助核对：

- 文本规范（UTF-8/LF、单尾换行、无行尾空白）：本台阶改动文件全部通过（一次性脚本，未提交）；
- 宿主 ruff 0.14.13 + `validation/ruff.toml` 只跑改动文件：对本台阶**新增行 0 命中**；命中的 5 条
  （`hooks.py:1007/1038/1798`、`test_hook_audit_reading_context.py:27/237`）都是改动前就存在的行。
  仓库 `.venv` 里没有 ruff（`No module named ruff`），所以用的是宿主工具；合规性以 `validation/ruff.toml` 为准。

## 5 未取得 / 未核实（不许当成"通过"）

1. **真实 dsh 会话没有跑**：草案 §1 的 C1-a 门写的是"真实 Hook：连续三次 edit 后账本可读"。本轮用
   `DshPreExecuteHook.handle` / `run_hook` + **真实 fixture、真实文件系统、真实规则集与注册表**证明，
   但没有起 dsh GUI / headless 会话，也没有验证"dsh 在 pre-execute 时确实把 `session_id` 原样送进 Hook"
   （这由 Phase 2 既有 fixture 契约与 `tests/contract/test_policy_hook_chain.py` 的跨语言用例覆盖，不覆盖本台阶新增路径）。
   真机三次 edit 的闭环读数留给 Lead / C1-b 前执行。
2. **同会话并发追加没有做原子性保证**：每个 Hook 进程 `open('a')` 写一行（<4 KB），没有跨进程锁、没有 fsync；
   Windows 上并发追加的原子性**没有实测**。`batch_ref` 是"我这个进程读到的快照 + 自己这条"——两个同会话
   并发进程可能各自少看到对方刚追加的目标（下一次调用会包含），**不是**串行化后的全局值。是否可接受由 C1-b 裁定。
3. **TTL 清理在 Hook 热路径上**（启用时才跑）：一次目录扫描 + 删除；没有性能基线，没有和 `timeout_ms` 预算
   一起测量（它不参与 `pre_evidence.timeout_ms + timeout_ms < hooks.json timeout` 这条不等式）。
4. **草案里的 `settled` / `abandoned` 显式结算没有实现**：C1-a 的任务范围只要求"记录 + 摘要 + 状态"；
   未结算批次不得当作通过的口径属于 C1-b，必须先裁定再实现。
5. **批次包含被 block 的提议**（记账在判定之前）：这是 C1-a 的刻意选择（记录"提议过什么"），但 C1-b 若把
   "已提议"直接读成"允许写"，被拦下的提议就会进入取证树。C1-b 需要显式决定过滤口径（建议按该事件最终
   `decision` 过滤，或引入结算状态），本轮**不改**这个语义。
6. **外部消费者无法核对**：只 grep 了仓库内 `audit_schema_version` / `AUDIT_SCHEMA_VERSION` 的字面量
   （测试、tools、src、docs）；仓库外的审计读取方是否按 1.3 精确匹配，本环境无从验证。
7. **生成物未重跑**：`docs/project/architecture/tech-detail/02-dsh-Hook-内部流程/cells.py` 对审计记录只断言
   "documented 键存在"（不是精确键集合），新增 `batch_ref`/`batch` 不会让它变红；但没有跑 notebook 的 `--check`
   （那属于文档生成门禁，Lead 侧统一跑）。
8. 工作树里同时存在 C3 子会话的未提交改动（`registry/`、`src/enforcement/`、其读数与测试）；本读数里的
   测试是在那个工作树上跑的，本轮一个都没碰。

## 6 留给 Lead 的文档更新点

1. `AGENTS.md` 第 55 条版本轴表：
   - **新增一行** `adapters.dsh.batch_ledger.BATCH_LEDGER_SCHEMA_VERSION`（**1.0 = 首次建轴**：记录键集合
     `{schema_version, session_id, event_id, tool, target, recorded_at}`；按会话分文件；摘要口径见 §2.2）；
   - 更新同一张表里 `adapters.dsh.hooks.AUDIT_SCHEMA_VERSION` 的描述：1.3 → **1.4**（C1-a 加 `batch_ref` 与 `batch` 块；
     未声明 `batch_ledger` 时判定记录不加 batch 键）。
2. `src/adapters/dsh/README.md`：
   - 新增一节（例如 §9.11 或 §8.3）写清：落点 / 六字段 / 四态 status / fail-open（stderr 一行 + 审计状态）/
     `batch_ref` 稳定口径 / TTL 只清理 `pre-evidence-batches` / 不声明的行为；
   - §9.2 那张"审计协议加键 → 版本号"的表补 `1.3 → 1.4`（C1-a）；
   - §8 的可选配置列表补 `batch_ledger`（默认关闭）。
3. `05 §3.3` 与 `04 5.46`：把 C1-a 标为"已落地（只报告）"，并写明 C1-b 前的待裁定项（§5 第 4/5 条）。
4. 裁定草案 §1 的 C1-a 行：门"真实 Hook：连续三次 edit"仍**未取得**，建议在草案到期日前补一次真机读数再定 C1-b。
5. 若要在本机受治项目里真正启用：把 `batch_ledger` 段加进**部署副本**的 adapter 配置（示例文件只把它注释掉）；
   不启用时线上审计记录除 `audit_schema_version` 外与 1.3 时逐字相同。

## 7 边界与回退

- 回退 = 删 `src/adapters/dsh/batch_ledger.py`、撤掉 `book_batch` 调用与配置段、`AUDIT_SCHEMA_VERSION` 回 1.3、
  恢复三处断言；账本文件与本台阶读数可一并删除（它不在任何判定路径上）。
- 本台阶**没有**新增任何 reason code、没有改退出码语义、没有进 `policy.engine.evaluate`。

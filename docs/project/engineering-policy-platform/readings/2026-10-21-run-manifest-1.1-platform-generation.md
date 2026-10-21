# 2026-10-21 run-manifest 1.1：`platform_generation`（记录字段升版）

> **性质**：实现读数（Lead）。起点 HEAD `0f580f8`（工作树带未提交的题库/裁决读数，按交接提示词保留）。
> **范围**：只改 dgate2 的载荷与评分器冻结块，并同批同步文档；**不改** `src/**`、`examples/**`、`registry/**`、
> `testing/ab/dgate2/hidden/**`、`configs/**`、`a3-task-v3/**`。
> **依据**：AGENTS 第 55 条；`readings/2026-10-21-c1b-treatment-adjudication.md` §3.4/§4；
> `readings/2026-10-21-experiment-freeze-adjudication.md` §2.2/§3。

## 0 一句话

17 字段 → 18 字段：新增 `platform_generation`，把「这次 run 的平台是哪一代」写进 run-manifest 本身，
不再依赖 `.tmp` 旁文件或散文；`RUN_MANIFEST_SCHEMA_VERSION` **1.0 → 1.1**、评分器 `version` **2 → 3**、
`scorer/manifest.sha256` 重生成（组合摘要 `e3ef9e91…` → `3fda3ee2…`）。**T/C/A 权重、8 条规则、作废条件没动。**

## 1 改了什么（逐件）

| 件 | 改动 | 为什么 |
| --- | --- | --- |
| `dgate2/run-manifest/run_manifest.py` | 版本 1.1；字段表追加第 18 条；新增 `--platform-facts` 的**闭集**校验（未知键/类型/枚举/摘要形状 = 退出 2）；`budget` 由工具按三值现场重算；生成与 `--check` 都核对 `model.first_message_sha256` vs 任务包首消息 | 载荷形状变了（AGENTS 55）；「宿主/模型同一」必须可被机器复核 |
| `dgate2/scorer/scorer.yaml` | `version: "3"`；`freeze.frozen_note` 记 v2→v3；`run_manifest_fields` 追加 `platform_generation` | 17 条字段清单冻结在评分器里，加字段同批升版（task-7 §4.2） |
| `dgate2/scorer/manifest.sha256` | 重生成：25 个文件、组合摘要 `sha256:3fda3ee2…` | 输入字节变了，旧清单失效 |
| `dgate2/scorer/README.md` | 冻结状态与 §11.1 表更新；新增 §11.3（v2→v3 记录） | 冻结记录必须说得出「改了什么、没改什么」 |
| `dgate2/run-manifest/README.md` | 18 字段表、`--platform-facts` 形状与不变量、退出码边界 | 操作口径（谁在什么时候写什么） |
| `tests/unit/test_dgate2_run_manifest.py` | 17→18、1.0→1.1；新增 7 条：pending、正常记录+budget、未知键退出 2、预算不等式退出 1、serial 矛盾、首消息不符、`--check` 现场重算 budget | 新键必须有会红的用例（AGENTS 45/55） |
| 文档 | `版本轴登记表`（dgate2 条目）、平台 `README.md`、`dgate2/README.md`、`bank/README.md`、`bank/harness/README.md` | 两处同批（AGENTS 55）；题库的复合载荷底座从 17 改 18 |
| **没动** | `scorer.yaml` 的 `weights` / `rules` / `invalidation` / `measurement` / `ceiling`；hidden 两文件；configs；任务包；`src/**`；`registry/**` | 这是**载荷形状**升版，不是换判据 |

## 2 `platform_generation` 的载荷

### 2.1 键与来源（每臂一份，全部来自 `--platform-facts` 输入）

| 块 | 键 | 来源 |
| --- | --- | --- |
| `host` | `entry`（headless/desktop）、`dsh_runtime`、`dsh_source`（app_bundled/path_cli）、`dsh_entry`（只接受 `<token>`）、`profile`、`session_sandbox`、`file_policy`、`sandbox`（三态） | 启动 argv / `<install>` 的 `--version` / 会话日志 |
| `start` | `head`、`worktree_clean` | **run 之前**的起点清单（与生成时点分开记） |
| `run` | `serial`、`ci_local_lock_held`、`concurrent_sessions` | 开跑前检查（串行约束） |
| `declarations` | `adapter_config`（path/sha256/agent_version/into_decision/max_targets）、`registry`（path/sha256/registry_schema_version + approved 三件）、`approval`（path/sha256）、`test_layout`（path/sha256） | 受治项目 `.policy/` 的单文件摘要；A/B 的 treatment 差异（test-layout） |
| `batch_ledger` | `enabled` / `into_decision` / `max_targets` / `ttl_hours` / `schema_version` | 适配器配置 + 常量（T3 的代际证据） |
| `audit_schema_version` | 观测值 | 审计记录 |
| `pre_evidence` + `timeouts` + `budget` | 前两块来自配置/`hooks.json`；`budget` 工具算 | 预算不等式 |
| `model` | `id` / `params` / `first_message_sha256` | 会话 header + 任务包 |
| `observations.batch` | `decisions` / `with_batch` / `settled` / `truncated` / `unreadable` / `degraded` | 每条判定记录的 `pre_evidence.batch` 与 `batch.settlement` 汇总 |

### 2.2 失败关闭的三条口径

1. **输入是闭集**：任何未知键、类型错、枚举外取值、摘要形状不对 → 退出 **2**，且**不写出半成品清单**。
2. **`budget` 不由输入声明**：工具按 `pre_evidence.timeout_ms + timeouts.tool_timeout_ms <
   timeouts.hooks_timeout_ms` 现场算 `{applicable, ok, left_ms, right_ms, inequality}`；不成立 → 清单
   不合格（退出 **1**），`--check` 也按记录的三值重算并比对（改一个数就红）。
3. **跨字段矛盾记 `problems`（退出 1）**：`run.serial` 与 `ci_local_lock_held/concurrent_sessions`；
   `adapter_config.into_decision` ↔ `batch_ledger.into_decision`（`max_targets` 同）；`degraded` 与
   `unreadable/truncated`（有证据必须 degraded，degraded 必须有证据）。`model.first_message_sha256`
   与 `first_message_sha256` 字段不符时，生成与 `--check` 都报。

另：`host.sandbox` 只写三态（`restricted` / `unrestricted` / `unknown`，与 `src/provenance/reading_context.py`
同义），**不把 `danger-full-access` 写进三态**；模式另记 `file_policy` / `session_sandbox`。

## 3 升版与作废面

- **判据**（AGENTS 55）：这个载荷的键集合变了（17→18）且 `budget` 是新增语义 ⇒ 必须升
  `RUN_MANIFEST_SCHEMA_VERSION`。旧 1.0 manifest 在新版本下**校验必失败**（缺第 18 字段）；这是有意的。
- **评分器**：`version: "3"` 只改 `run_manifest_fields` 与冻结记录；`weights` / `rules` / `invalidation` /
  `measurement` / `ceiling` 逐字节未动 ⇒ 「T/C/A 的算法与阈值没变」与「载荷形状变了」同批写明。
- **旧读数**：`testing/ab/dgate2/runs/2026-10-20/{A,B,C}/run-manifest.json`（17 字段）保留为历史，
  **不与 1.1 合并引用**；旧组合摘要 `e3ef9e91…` 只属于 v2 冻结，引用时必须写版本。
- **题库**：`BANK_RUN_MANIFEST_SCHEMA_VERSION` 仍是**未实现的规划值**（1.0 随 dgate2 1.1 作废，规划 1.1 =
  dgate2 1.1 的 18 字段 + 题库 9 字段）；题库当前的 run 级事实仍由 `run_session.py` 的 `AB_RUN_SCHEMA_VERSION 1.0`
  承担，两者不是同一份载荷。

## 4 实测读数（本轮，起点 HEAD 0f580f8）

```
py_compile run_manifest.py                                   exit 0
pytest tests/unit/test_dgate2_run_manifest.py                20 passed（原 13 → 20）
make_manifest.py --check --strict                            RESULT: PASS（25 个文件逐字节一致，0 条 pending）
make_manifest.py 组合摘要                                    sha256:3fda3ee26b618826c17b1987df10705033e7fafdb573b21a92fd99b929c006c3
run-manifest --arm A --platform-facts <smoke>                fields=18 recorded=11 pending=7 not_applicable=0
                                                             manifest_check=0 combined_digest=sha256:3fda3ee2…
run-manifest --check <smoke>                                 RESULT: PASS（18 字段齐全；7 条 pending）
```

冒烟输入/产物在 `.tmp/dgate2/platform-smoke/`（一次性现场，`cleanup` 会删；长期证据是本文件 + 用例）。
7 条 pending = `reference_tree / arms / readings / hidden_author / bypass_sampling / a4_review /
nondeterminism_ruling`（开跑前本来就还没有），**不是通过**。

## 5 边界与下一步

- 本读数只证明**载荷能生成、能校验、会红**；每臂**真实的** platform-facts 还没生成（开跑 T0 装配后才有）。
- 真 run 的 `platform-facts` 必须写 `start.head` = run 起点、`run.serial=true`、两臂各自的 approval sha256；
  这些值只能由装配后的现场给出，本文件不预填。
- `04 5.90` 未修（实验期接受为已知边界）；`post_error` 回声仍按裁决记进 treatment 的反馈通道。
- 旧 A/B/C n=1 与旧 M5b activation 仍作废；D 校准门与 C1-b 门 2/4/5 需在冻结配置下重跑（05 §8 第 10 条）。
- 题库「其余 5 题 → 冻结包」与旗舰隐藏代码/参考解并行推进（独立子会话），本读数不覆盖。

## 6 证据指针

- 实现：`testing/ab/dgate2/run-manifest/run_manifest.py`、`testing/ab/dgate2/scorer/scorer.yaml`、
  `testing/ab/dgate2/scorer/manifest.sha256`、`testing/ab/dgate2/scorer/README.md`（§11.3）
- 用例：`tests/unit/test_dgate2_run_manifest.py`
- 轴：`docs/project/architecture/版本轴登记表.md`（dgate2 条目）
- 裁决来源：`readings/2026-10-21-c1b-treatment-adjudication.md`、`readings/2026-10-21-experiment-freeze-adjudication.md`

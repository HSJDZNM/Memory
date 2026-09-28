# 修复轮 15：Q6 的归因、Q7 的「待实现」状态、Q8 的尾巴与 D4 的诊断字段（2026-09-28）

> 输入是 [14 号文档](14-sandbox-loop-attribution-and-agent-version.md) §5 新登记的三条（Q6–Q8）与 §9「建议的下一轮」
> 第 1–4 项。本轮由四个写手子会话（task-1 Q6 / task-2 Q7 / task-3 Q8 / task-4+7 诊断字段）、
> 一个独立验收者（task-5 准备 + task-6 收口）与 Lead 的端到端复核共同完成，写域互不重叠。

> **先读这段**：本文是 2026-09-28 的**冻结记录**，它只对那一刻的工作树成立（见 §7 的适用边界）。
> §5 Q7 那条只放宽了「收集失败且原因是项目内还不存在的模块/名字」这一种形态；
> 它**不证明测试最终会通过**，也不改变任何其他失败处置。

## 0. 一句话

**三条登记缺陷全部修好，第四条（诊断字段）连同它后面的两处同源缺陷一起收掉**，每一处都用「先红后绿 + 变异」证明：
独立验收者用**同一版驱动**在自冻结的修前树与修后树上各跑一遍，**修前 42 条 core 判据红 → 修后 0 条红（81 条通过）**，
四个修复点的 28 个文件 sha256 与冻结清单 **28/28 相同**，失败关闭与「归不了因就不跳过」的反例**逐字段未变**。

Q7 的效果用一句话说：**「先写测试、再写实现」不再被自己的平台拦死**——
之前它的唯一出路是「把测试先写成不测任何东西的占位」（14 号 §5 Q7 记录的模型原文）。

## 1. 范围与分工

| 条目 | 现状 | 判据 |
| --- | --- | --- |
| Q6 插件把「工作目录不存在」误报成「找不到可执行文件」 | **已修** | 理由按工作目录真实状态归因；预检在 spawn 之前；失败关闭一字未改 |
| Q7「测试已落地、目标模块还不存在」被判成 validator crashed | **已修** | 新增显式状态 `pending_implementation`；不进 `served_checkers`；warning 级 violation → `allow_with_warnings` |
| Q8 尾巴：`host-version` 在 CI 上没有门禁 | **已修** | 新增 `--record-check`（不探测宿主）+ `--record`；CI 步骤改用它 |
| D4 诊断字段 `home_roots` 的畸形项 | **已修** | `file:///C:/x` → `C:/x`；畸形候选按规则丢弃；判定语义不变 |
| D4 追加：归因的合取跨记录 | **已修** | 「Hook 无法执行」+「spawn EPERM」必须**同一行**；崩溃原文 + 被拒路径必须**同一崩溃块** |

写域（互不重叠）：`fix-hook-reason` 插件与 Hook 链路测试；`fix-tdd-state` 取证状态机与协议版本；
`fix-hostversion-ci` 适配器 CLI/记录/门禁接线；`fix-diagnostics` 沙箱闭环与它的集成测试；
`verify-round15` 只读仓库 + `.tmp/round-15/verify/`；Lead 负责手册生成物、AGENTS.md、端到端与全量门禁。

## 2. Q6：失败关闭 ≠ 理由正确

**修前**（14 号 §5 Q6 的真机原文，两次会话各 10 次调用逐次一致）：

```text
policy-hook: Hook 无法执行（spawn C:\\Program Files\\nodejs\\node.exe ENOENT），按失败关闭拒绝该工具调用
```

被拒的其实是**工作目录**（profile 里的 `projectDir` 指向刚被删掉的目录），而 `node.exe` 存在且可执行——
Node 的 spawn 在 cwd 不存在时把 ENOENT 归给了**可执行文件**。模型因此花一整轮推理「Node 没装」。

**修后**：理由由三段组成，各自可判定——**在哪个目录启动**（含来源与存在性）、**要启动的命令**、**spawn 报错原文**，
最后一句是按工作目录事实给出的归因与「改成什么形态就能过」。实现上 spawn **之前**用 `node:fs` 预检
（能证明目录不可用就直接拒绝、不再 spawn），异常路径**再查一次**（覆盖「预检过后目录被删」的竞态）。
前缀 `policy-hook: Hook 无法执行（`、pre=deny / post=block、退出码契约逐字保留。

| 证据 | 读数 |
| --- | --- |
| `.tmp/round-15/fix-hook-reason/red-q6.txt` | 新用例在修前：**4 failed / 15 passed**，失败理由就是真机原文 |
| `green-q6.txt` / `green-related.txt` | 修后 **19 passed** / 关联套件 **182 passed** |
| `mutate-A/B.txt` | 两条新检查各自可红（删预检只红 `spawnAttempts==0` 两条，沿用预检结果只红竞态那条） |
| 验收者 D1（独立探针） | 修前 5 条 core 红 → 修后 0 条；`shell_calls` 1 → **0**（预检在 spawn 之前） |

**Lead 的真实会话读数**（把 profile 的 `projectDir` 指到一个不存在的目录后跑一次受治理会话）：
`exit 0 / 12.42 s`、受控项目**零文件变更**、审计零决策（Hook 根本没起）——而模型读到的原文是：

```text
policy-hook: Hook 无法执行（工作目录不存在：…/lead/nonexistent-project（来自 config.projectDir）…），按失败关闭拒绝该工具调用
```

**同一条修正在另一个场景里的额外证据**：Q7 的真实会话（§3）因为本机沙箱禁止管道 stdio 而起不来 Hook，
模型读到的理由是 `工作目录已确认存在：…；要启动的命令：…；spawn 报错：spawn EPERM`，
它**当场把原因写对**（沙箱限制），而不是像 14 号 §5 Q6 那样被带到「运行时没装」。同一环境边界，两种后果。

## 3. Q7：「待实现」是显式状态

**修前**（真机收据可复算：`.tmp/round-10/lead/project/.policy/audit.jsonl` 194 条记录）：

```text
file=src/invsvc/audit_repository.py  operation=create  decision=block
violations: TESTING-001@1(critical), TESTING-002@1(critical)
pre_evidence.blockers: [{validator: tool.pytest@1.0, status: crashed,
                         checkers: [failing_tests, missing_tests],
                         reason: "退出码 2：… ERROR collecting tests/test_audit_repository.py … ImportError …"}]
```

两条 TESTING 规则被同一条 critical 覆盖（TESTING-001 并没有自己的 missing_tests 证据）；
模型的结论是「把对应测试暂存为可通过的占位」——被惩罚的是正确的开发顺序。

**修后**：新增 `ValidatorStatus.PENDING_IMPLEMENTATION`，严格限定为「退出码是收集失败形态、能解析出导入目标、
且该目标属于**项目内**、在本次树里还不存在」。处置：不产生 Blocker、`failing_tests` **不进** `served_checkers`、
报告与审计带 `pending_implementation` 清单、判定侧产出 **warning 级** violation。

**Lead 的生产入口端到端**（真 `python -m adapters.dsh.hooks` + 真流水线，先写测试、目标模块还不存在）：

| 字段 | 读数 |
| --- | --- |
| exit / decision | `0` / `allow_with_warnings`（stderr：`[policy] ALLOWED WITH WARNINGS write src/invsvc/report_repository.py: TESTING-002@1`） |
| violations | `[('TESTING-002@1','warning')]` |
| served_checkers | `['missing_docstring','missing_tests','style_lint']`（**不含 failing_tests**） |
| validators | `('tool.pytest@1.0','pending_implementation')` |
| blockers | `[]` |
| pending_implementation | `{test_modules:['tests/test_report_repository.py'], missing_targets:['invsvc.models:ReportEntry'], reason:'待实现：…', fix:'先把 invsvc.models:ReportEntry 真正落地…'}` |

**反例守卫（一条都不许放宽）**：断言失败（exit 1）、第三方包缺失、语法错误、导入期异常、conftest 出错 →
全部仍是 `failing_tests` 的**真违规**（规则自己的 severity → block）；解析不出（exit 2 无原文）→ 保持 `crashed` 失败关闭。
验收者 P2–P8 逐条在冻结树上一一复现。**另一处结构性细节**：`-q -rf` 下收集失败不打印 `FAILED/ERROR` 短摘要，
所以「非待实现」的收集失败必须**自己合成证据**，否则就是「违规清单为空」的静默放行（实现与用例都钉了这一点）。

**协议版本**：新增状态值 = 载荷变更 → `EVIDENCE_SCHEMA_VERSION` / `PIPELINE_SCHEMA_VERSION` **1.1 → 1.2**
（旧 1.0/1.1 载荷仍被拒）。连带按新版本号**显式**更新的写死断言：
`tests/contract/test_validator_protocol.py`、`tests/integration/test_validator_pipeline.py`、
`tests/integration/test_validator_cli.py:98`、`tests/integration/test_api_http.py:701`（API 原样嵌入流水线载荷），
以及手册 `docs/project/architecture/tech-detail/05-代码验证器/cells.py:620` → 重新生成 `.py/.ipynb`（`--check` 已过）。

| 证据 | 读数 |
| --- | --- |
| `.tmp/round-15/fix-tdd-state/green-final.txt` | 修后 6 个文件 **122 passed** |
| `red-final-tests-on-prefix-src.txt` | **同一批最终版用例**跑在冻结的修前源码上：**13 failed + 2 collection errors** |
| `mutate-guards.txt` | 放宽「项目内」门槛 → 2 红；把待实现当「服务过」→ 1 红；恢复后 sha256 一致 |
| 验收者 D2 | 修前 14 条 core 红 → 修后 0 条；五个反例仍 block |

## 4. Q8 的尾巴：让 `host-version` 在 CI 上也能红

14 号修好的检查在**没有 dsh 的 CI** 上读不到宿主版本 → `unavailable` → 退出 0，
于是「修了一条会红的检查，却没有任何地方会为它红」。本轮补上**不依赖宿主**的比对：
提交进仓库的观测记录 `adapters/host-versions.observed.json`（只能由 `--record` 写入，
每条含实测版本 + 声明的读法 + **观测时那份 manifest 的 sha256**）。

| 形态 | 读什么 | 退出码 |
| --- | --- | --- |
| ① 报告（默认） | 活体探测 | 恒 0（只打印） |
| ② `--check` | 活体 +（记录存在时）与记录核对 | 1 = drift / **recording_stale** / full 却声明不出读法；`--require-runtime` 时 unavailable 也 1 |
| ③ `--record-check` | **只读记录，不探测宿主** | 0 仅当逐条一致；记录缺失（`record_missing`）/ 格式坏（`record_invalid`）/ 声明≠记录 / manifest 哈希对不上 一律 1 |
| ④ `--record` | 先做完整活体比对，再固化 | 0 = 已写入；1 = 拒写（drift / 读不到 / 空记录），不落地文件 |

**Lead 独立读数**：`--record-check` 在**没有宿主读法的形态下退出 0**（这正是 Q8 的修法：CI 不需要宿主）；
本机 `--check` 是 `dsh [match]` 且说明里写明记录参与了比对。
**变异 11 例**（在 `adapters/` 的副本上跑，不碰真实声明）：改声明不重录 → 1/`recording_stale`；
手改记录 → 1/`drift` 点名两个版本；删记录 → 1/`record_missing`；缺字段 → 1/`record_invalid`；
活体与记录不一致 → 1/`recording_stale`；drift 时 `--record` 拒写且不落盘。
**维护纪律（代价，写下来）**：改 `adapters/<agent>/manifest.yaml` 之后必须 `approve` **再** `--record`，
否则 CI 红在「记录过期」上；记录证明不了「它是在哪台机器上写的」，那要靠 `--record` 的 diff 评审（已进 AGENTS 54）。

## 5. D4：诊断字段与两处同源缺陷

**修前**（Lead 与验收者各自复现）：真机日志里 `at file:///C:/Users/…/dsh-home/profiles/headless/#spill-local`
被两条正则同时吃掉，`dsh_home_roots()` 产出两个畸形候选
（`e:///C:/…/dsh-home`、丢掉盘符的 `/Users/…/dsh-home`），而**正确的根根本没进候选** —— 它参与 `is_under` 判定。

**修后**：URL 与普通路径分开解析（`file:///C:/x` → `C:/x`、`file:///home/x` → `/home/x`），
每条根带来源与证据；畸形候选按写明理由的规则丢弃；判定语义与两种 kind 的措辞不变。
随后验收者又逼出两条同源缺陷，都已收掉（**三档窗口实测**）：

| 窗口 | N3（跨记录 → None） | N4（同记录分行 → 归因） | 结论 |
| --- | --- | --- | --- |
| 整篇日志（修前） | ✗ `other_path_denied`（**假跳过**） | ✓ | 否定 |
| 同一行 | ✓ | ✗ 丢真因 | 否定（验收者当场判红） |
| **同一崩溃块**（崩溃原文行 + 紧随的缩进续行） | ✓ | ✓ | 采用 |

Hook 侧同理：「`Hook 无法执行`」与「`spawn EPERM`」必须在**同一行**内。
`%20` 形态也在验收者逼问下修好：`file:///C:/Users/a%20b/dsh-home` → `C:/Users/a b/dsh-home`（真根不许因为解析口径消失）。

**语义变更表（照抄 `fix-diagnostics` 的原话）**：
1. Hook 判据收窄：只有理由里带 `spawn 报错：spawn EPERM` 才算沙箱原因；**裸 `spawn EPERM`（无 `Hook 无法执行`）
   与「读不出原因」的旧插件形态，从环境跳过变成真失败**（失败关闭方向，退出码 1）；
2. 单斜杠 `file:/path` 不按 URL 解析：不产正确的 profile 根，这种形态归不了因 → 不产生环境跳过；
3. 百分号编码按来源分档：URL 形态允许解码后的空白（`%20` 是路径内容），`%2F`/`%5C` 原样保留（不伪造分隔层），
   只解一层（`%2520` → `%20`）；控制字符/引号/括号任何来源都丢。

## 6. 独立验收（task-5 / task-6）

- **冻结来历**：验收者在写手动工**之前**逐字节冻结修前树（916 文件 / 19,987,060 字节 / `byte_identical=true`），
  修后重冻结 918 文件；两棵树跑完矩阵后均 `VERDICT=INTACT`（缺失 0、哈希不符 0），
  四个修复点 28/28 文件 sha256 与 post 清单相同；
- **矩阵**：同一版驱动，修前 **42 红**（D1 5 / D2 14 / D3 5 / D4 13 / D4b 5）→ 修后 **0 红 / 81 通过**；
- **反例逐字段未变**（`compare-pre-post.json` 的 `unchanged`）：D1 放行路径、D2 五条真违规、
  D3 无宿主退出码与活体一致、D4 真机判定与「无关 EPERM 不跳过」；
- **主动报的偏差**：task-1 写域里写的 `tests/unit/test_policy_hook_reason.py` 没产生（用例落在契约测试里）；
  `test_policy_hook_chain.py` 约 772 行仍写已改名的 `SPAWN_DENIED_MARKERS`（注释漂移）；
  修后剩 1 条 advisory（探针用 `spawnSync` 拿到的原生错误带路径，真机原文不带路径——**非缺陷**，但这条接缝对消息形状敏感）；
- **验收者自己返工 7 处**、写手 `fix-diagnostics` 主动记了 1 处「自己的对照没抓到、借验收者的 N4 才发现的」——
  两件事都留在各自 REPORT 里。

## 7. 门禁与文档同步

| 动作 | 内容 |
| --- | --- |
| 手册 | `tech-detail/05-代码验证器/cells.py` 按 1.2 更新并**重新生成** `.py/.ipynb`（`--check` 通过）；learning 手册 `--check` 通过 |
| AGENTS.md | 新增第 51–54 条（待实现状态 / 失败关闭不等于理由正确 / 归因的合取必须在同一记录内 / host-version 四形态与重录纪律） |
| 文档 | `src/adapters/dsh/README.md` §13 按实现口径重写（四形态 + 五种状态 + 维护纪律）；根 `README.md`、`docs/project/architecture/使用说明.md`、`tools/README.md` 同步 |
| 全量门禁 | `python tools/ci_local.py --full --timings`：**33 步**；结果见下方「门禁读数」 |
| 未提交 | 本轮全部改动仍在工作树（含新文件 `adapters/host-versions.observed.json`，它必须进版本库否则 CI 红在 `record_missing`） |

**门禁读数（适用边界，N28）**：第一次跑 33 步里**只有 1 处失败**——`Text conventions`，
原因是**另一个并发会话**正在改 `docs/project/engineering-policy-platform/designs/README.md`（该文件末尾丢了换行；
`.tmp/round-15/design/` 与 `PLAN-VERIFICATION.md` 是它的产物）。它不是本轮的改动，也不在本轮写域内；
**复跑（同一份工作树、同一命令）：33 步里 32 步 rc=0，唯一红的还是同一步**，
失败文件仍是那份 `designs/README.md`（mtime 未变）。Lead 随后**只补了那一个缺失的行尾换行**（一个字节，不改内容），
并单独复跑该步 → `检查 601 个文本文件，问题 0 处`。这条记在这里而不是抹掉：
**同一工作树上的并发会话会让 always-on 的文本规范步骤变红，而本轮的门禁仲裁只对同一条 CI 流程生效**（见 §9 第 8 条）。
另：本轮 `Real dsh sandbox loop` 一步是**环境跳过**（`profile_write_denied`：本机 `$DSH_HOME` 在受限 shell 里不可写，
dsh 在注册任何 Hook 之前就退出）——这是 14 号缺陷 1 修好后的**正确归因读数**，不是「缺少 dsh」，也不是任何规则判定。**结论只对跑的那一刻的工作树成立**，且本轮在门禁之后没有再改任何**代码类**文件。

## 8. 复现

```text
# Q6：判据与新用例（不依赖 dsh 可执行文件）
python -m pytest tests/contract/test_policy_hook_chain.py -q                    # 20 passed
python -m pytest tests/integration/test_dsh_sandbox_loop.py -q                  # 67 passed

# Q7：状态机与生产入口
python -m pytest tests/unit/test_validator_pending_implementation.py tests/integration/test_validator_pipeline.py -q
python .tmp/round-15/lead/q7_payload_probe.py                                   # Lead 端到端：allow_with_warnings + 清单

# Q8：声明 vs 宿主 vs 记录
python -m adapters.cli host-version --check                                     # 本机活体
python -m adapters.cli host-version --record-check                              # CI 形态（不探测宿主）

# 独立验收（验收者自己的入口）
python .tmp/round-15/verify/bin/run_matrix.py --label post                      # 四驱动 + d4b

# 全量门禁（串行：同一工作树同时只允许一个 ci_local）
python tools/ci_local.py --full --timings
```

## 9. 本轮新显现的问题与残余（没有被修的）

| # | 事项 | 为什么没修 |
| --- | --- | --- |
| 1 | 「待实现」的判据写在代码里，没做成 `validation/validators.yaml` 的数据（对比 `analysis_failure_codes`） | 是一次数据形状设计；本轮先把它做成显式状态与可读清单 |
| 2 | `missing_targets` 是字符串（`模块名` / `模块名:名字`），不是结构化对象 | 结构化要再升 1.2 → 1.3；先要一个真实消费者 |
| 3 | 相对路径 `projectDir` 的解析基准仍可能与 shell 不一致 | 归属下一次插件侧改动 |
| 4 | payload 的 `JSON.stringify` 在 try 之外（循环引用/BigInt → 插件抛错而非 deny） | **理论性**：已核静态事实——dsh 更早就用 `snapshotJsonValue` 拒绝这类参数，且 `prepareExecution` 的 catch 会失败关闭；它是「理由自证」问题 |
| 5 | `tools/phase_evidence.py` 不带本轮的诊断字段 | 新字段已在闭环 artifact 与审计里；阶段证据不采集它不构成「看不见」 |
| 6 | 记录不能自证「在哪台机器上写的」 | 只能靠 `--record` 的 diff 人工评审；已写进 AGENTS 54 与拒绝理由 |
| 7 | `approved.json` 的重新审核仍是写手本人（14 号 §9 第 5 项） | 单人仓库的结构性限制，记在案、不假装解决 |
| 8 | **并发会话与同一工作树**：本轮实测到另一个会话改 `designs/README.md` 让门禁的文本规范步骤变红 | 新的现实问题：`ci_local` 只对「同一条 CI 流程」串行，对「另一个会话」没有仲裁 |
| 9 | `test_policy_hook_chain.py` 的注释漂移（`SPAWN_DENIED_MARKERS`） | 纯注释；下一轮顺手收 |

## 10. 建议的下一轮

| # | 事项 | 为什么现在不做 |
| --- | --- | --- |
| 1 | 真实受治理会话里跑一遍 Q7 的「先测后实现」 | 本机沙箱禁止管道 stdio（Hook spawn EPERM），真实会话在任何工具调用之前就被失败关闭拒掉；需要在不受限 shell 里跑 |
| 2 | 把「待实现」判据数据化（`validation/validators.yaml`），并考虑 `missing_targets` 结构化 | 见 §9 第 1/2 条 |
| 3 | Q7 那条路只覆盖 pytest：Ruff / mypy 的同类形态（工具跑成了、报告的是「树还在构建中」）没碰 | 需要逐工具定义「待实现」的形态 |
| 4 | 多人/多会话并发时的门禁仲裁（§9 第 8 条） | 本轮的 `ci-local.lock` 只解决同一条流程的并发 |

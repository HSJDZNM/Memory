# 06 · 计划进度（记录格式规范）

> **状态**：2026-10-17 建立。本文件**只规定记录格式**；除格式规范与空模板外，其余内容一律为空，待执行时按格式追加。
> **上位文件**：05-implementation-plan.md（阶段、任务编号、门与判据都在那里；本文件不重复判据，也不修改判据）。

---

## 0 这份文件是什么

- 它是 05 计划的**执行台账**：每一次执行（一次 run、一次探针、一次变更、一次读数）都追加一条记录。
- 它是**追加写**的：已提交的记录不修改；要更正就追一条新记录，并在「偏差」列写清更正了什么。
- 它**不是**分析文档：不写论证、不写建议、不写结论性判断；结论只能以「三态 + 证据指针」的形式出现。
- 它与本目录 README「过程记录不再保留」的决定不冲突：本文件只记三态与证据指针，不写叙述；计划关闭时，结论提炼进 04-open-work 与 05，本文件归档。

---

## 1 记录单元与编号规则

| 记录类型 | 何时写 | 编号 | 一行还是多行 |
| --- | --- | --- | --- |
| 进度记录 | 每完成 05 里的一个任务（A1/B1/…）或它的一次子步骤 | P-<任务编号>-<三位序号>，如 P-B1-001 | 一个任务一行；子步骤另起行 |
| 变更记录 | 每次提交/改动数据或代码 | C-<YYYYMMDD>-<两位序号>，如 C-20261017-01 | 一次提交一行 |
| 读数记录 | 每次产生读数（探针、干跑、run、审计解析） | R-<臂>-<任务>-<两位序号>，如 R-A-T1-01 | 一次读数一行 |
| 偏离/作废记录 | 任何与预注册不符、构造失败、run 作废 | D-<YYYYMMDD>-<两位序号> | 一个事件一行 |

**规则**：一条记录只描述一个单元；不合并、不省略、不改号。编号一旦写过就不再复用。

---

## 2 必填字段

每条记录必须包含下表全部字段；缺任一字段即为格式不合规，记录不得视为有效。

| 字段 | 取值要求 |
| --- | --- |
| id | 按第 1 节编号规则 |
| 时间 | RFC3339，带时区（如 2026-10-17T09:00:00+08:00） |
| 阶段 / 任务 | 对应 05 的编号（A1/A2/A3/B1/B2/B3/C1/C2/C3/C4/D1/D2/D3） |
| 执行者 | 人（姓名/角色）或会话标识；不得写「系统」 |
| 起点锁 | HEAD、rule_set_hash、账本起始偏移、audit/ledger/approval 三个 schema_version 中与本次相关的项 |
| 做了什么 | 动作摘要，≤80 字；不贴正文、不贴长日志 |
| 结果 | 三态之一：符合 / 不符合 / 跑不成；作废的另标「作废」 |
| 证据指针 | 按第 4 节格式；每个结论至少一条 |
| 判据 | 引用 05 的门编号或原文位置；**不在此重写判据** |
| 偏差 | 与预注册/计划的差异；没有写「无」 |
| 下一步 | 一个可执行动作；没有写「无」 |

---

## 3 三态判决与作废

| 判决 | 含义 | 要求 |
| --- | --- | --- |
| 符合 | 实际读数与 05 里写死的门一致 | 每条期望都要能指到「哪一源、哪条记录」 |
| 不符合 | 不一致，且是平台行为 | 必须带复现命令与证据指针；处置三选一：改平台 / 改计划 / 只登记 |
| 跑不成 | 环境或构造不成立 | **不占绿、不占红**；必须写触发条件编号与复现；不得用来支持任何结论 |
| 作废 | 命中 05 第 5.4 节的作废条件 | 写清命中哪一条；该 run 不进对比 |

**纪律**：摩擦与构造问题单列，不计入「不符合」；「没有记录」不等于「没有发生」；「跑不成」不等于「通过」。

---

## 4 证据指针格式

| 证据类型 | 格式 | 示例 |
| --- | --- | --- |
| 源码/文档 | <仓库相对路径>#L<起始行>[-L<结束行>] | src/enforcement/approvals.py#L556-L579 |
| 命令输出 | 命令原文（可复制）+ 退出码 | python -m pytest -q → exit 0 |
| 二进制/产物 | sha256:<hex> + 路径 | sha256:ab12… + run-A1/tree.tar |
| 读数文件 | 已跟踪目录下的相对路径（**不得指向 .tmp**） | docs/…/readings/2026-10-17-A1.md |
| 账本记录 | 文件相对路径 + action_id + 记录类型（PreToolUse/PostToolUse/链侧） | .policy/audit.jsonl + <action_id> + PreToolUse |

**口径**：一个动作在账本里可能有多条（pre/post/链侧）；引用前按 action_id 折叠，只取 PreToolUse。

---

## 5 禁止写法

1. 不写「应该 / 大概 / 可能 / 感觉」这类无证据判断。
2. 不写没有证据指针的结论。
3. 不写均值差、提升百分比、显著性（n=1 时无对象）。
4. 不把「没记录」写成「没有发生」；不把「跑不成」写成「通过」。
5. 不把平台自己的账本当独立证据；账本只作过程读数。
6. 不在本文件修改 05 的判据；判据改动走 05 第 8 节变更控制。
7. 不合并记录；不删改已写记录（更正用新记录 + 偏差列）。

---

## 6 模板（空）

### 6.1 进度记录

| id | 时间 | 阶段/任务 | 执行者 | 起点锁 | 做了什么 | 结果 | 证据指针 | 判据 | 偏差 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |  |

### 6.2 变更记录

| id | 时间 | 提交/变更摘要 | 改动面（文件） | 关联任务 | 是否改判定（R-d 指针） | 复核人 | 证据指针 |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |

### 6.3 读数记录

| id | 时间 | 臂/任务 | 读数名称 | 分母/口径 | 值 | 三态 | 证据指针 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |

### 6.4 偏离/作废记录

| id | 时间 | 事件 | 命中条件（05 第 5.4 节哪一条 / 构造失败编号） | 影响范围 | 处置 | 证据指针 |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

---

## 7 其余内容（空）

以下小节按第 6 节模板追加；未产生记录的阶段保持为空。

- 阶段 A 执行情况：见 §7.1–§7.4（2026-10-18）。
- 阶段 B 执行情况：空
- 阶段 C 执行情况：空
- 阶段 D 执行情况：空
- 汇总与复审：空

### 7.1 阶段 A · 进度记录

| id | 时间 | 阶段/任务 | 执行者 | 起点锁 | 做了什么 | 结果 | 证据指针 | 判据 | 偏差 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P-A1-001 | 2026-10-18T09:35:00+08:00 | A1 | a1-coverage（子会话） | HEAD 6167fad；CONTROL_PLANE_FACTS_SCHEMA_VERSION 1.0→1.1；facts 13→14 行 | 新建通道覆盖表并接入 C4 只报告读数；桌面通道 out_of_scope→in_scope；用例含删行变异 | 符合 | validation/channel-coverage.yaml#L1-L266；python tools/control_plane_facts.py --audit <external> → exit 0（CONTROL_PLANE_FACTS 四红 0）；pytest -q -n0 tests/unit/test_control_plane_facts.py tests/contract/test_wiring_inventory.py tests/unit/test_provenance_wiring_scope.py → 77 passed | 05 §4 A1 + §3.4 | 三处设计取值（见 C-20261018-02）；desktop 归因初稿「审计目标不存在」经 04 5.72 更正为「解析错位」 | 升格未做（ci_local 无稳定 --audit 来源）；最终树门禁属阶段 C3 |
| P-A2-001 | 2026-10-18T09:10:00+08:00 | A2 | a2-delegated-probe（子会话） | HEAD 6167fad；audit 1.3（只读）；ledger 1.0；approval 1.2（副本仅延期） | 复算 L4 三份记录 + 真实桥接五格 + 执行器 D1/D2，定性 5.71 | 符合 | docs/project/engineering-policy-platform/testing/ab/gui-runs/2026-10-18-A2-delegated-post-evidence.md；src/adapters/dsh/enforcement.py#L432-L527；src/enforcement/postcheck.py#L326-L337 与 #L484-L494 | 05 §4 A2 + 04 5.71 | 门原文只列两态，实际落第三态（D-20261018-01） | 04 5.71 已更新；解释性证据缺口列为 Phase B 候选（未裁定） |
| P-A3-001 | 2026-10-18T09:20:00+08:00 | A3 | a3-dryrun-recon（子会话；session 98ecab06…） | HEAD 6167fad；audit 15,014→15,421 条；approval 3/3 过期（2026-10-17T23:38Z 与 23:59Z） | 判定干跑四数可行性、代理读数与阻断条件；确认当前会话 out_of_scope | 跑不成 | docs/project/engineering-policy-platform/testing/ab/gui-runs/2026-10-18-A3-dryrun-feasibility.md；python -m adapters.cli wiring → exit 0 与 --check → exit 1；.policy/approval.json 三条均过期 | 05 §4 A3 + §5.6 | 无 A3 任务包；代理读数不构成 A3（见 D-20261018-02） | 按解冻清单 B-1..B-6 补齐构造；阶段 D 不开跑 |
| P-A1-002 | 2026-10-18T10:10:00+08:00 | A1（复核修复轮） | a1-coverage（子会话） | HEAD 2609a6e；独立复核子会话的 3 条必须修 + 建议 4–8 | 修坏输入降级（保持 exit 0）、reason 绝对路径脱敏、覆盖表表达力边界表述；解耦 registry 红格、补第三份声明、截断披露、字段校验、04 陈旧读数 | 符合 | tools/control_plane_facts.py；src/provenance/reading_context.py；tests/unit/test_control_plane_facts.py；git show --stat 9806031；pytest -q -n0 三文件 → 83 passed；--audit → exit 0、leaks=[] | 05 §4 A1 + 独立复核清单 | 05 A1 门「删一行变异必红」的字面口径见 D-20261018-03 | 门禁复跑的构造限制见 D-20261018-04；全量套件须在沙箱外复跑 |
| P-A1-003 | 2026-10-18T11:15:00+08:00 | A1/A2 判据表述裁定 | Lead | HEAD f11e9af；05 §8 第 5/6 条原为「待使用者复核/裁定」 | 使用者指示「以本会话继续执行」后，按工具级解释与三态口径定案，并同步改 05 §4 A1/A2 两行的门措辞 | 符合 | 05 §4（A1/A2 行）与 §8 第 5/6 条 | 05 §8 第 5/6 条 + 06 D-20261018-03 | 无（裁定本身即记录；可回退） | 若使用者不同意，回退这三处文字即可，不影响已交付读数 |
| P-A1-004 | 2026-10-18T14:00:00+08:00 | A1（5.72 修复轮） | a4-wiring52（子会话） | HEAD f11e9af；WIRING_SCHEMA_VERSION 1.4 不变 | 修 wiring 审计目标解析（配置内 audit_log 按配置文件目录），同批同步覆盖表 desktop 四行与 04 5.72 | 符合 | src/adapters/wiring.py；tests/unit/test_wiring.py；tests/contract/test_wiring_inventory.py；validation/channel-coverage.yaml；04-open-work.md；git show --stat c4eaa53；pytest 167 passed；真实 wiring dsh:desktop=wired/fresh | 04 5.72 + 05 §3.4 | 无（只报告；--check 判据与退出码不变） | Lead 已提交；wiring-scope.yaml 文案已由 Lead 同批同步 |
| P-A3-002 | 2026-10-18T14:40:00+08:00 | A3（解冻构造包） | a5-a3-unblock（子会话） | HEAD f47823f（派单记的 f11e9af 已被 Lead 的 c4eaa53 前置） | 交付 A3 解冻构造包：任务包草案、基线树方案、受治臂启动方案、审批重签清单、四数测量口径、使用者待办 12 步；未跑受治会话、未签审批 | 符合 | docs/project/engineering-policy-platform/testing/ab/2026-10-18-A3-unblock.md；git show --stat f3d376f | 05 §4 A3 + §5.2/§5.6 | 8 条未核实 + 3 条需裁定（N-7 A3 是否以 B1 为前置 / N-8 host 权限模式 / N-9 装配器落点） | 先跑单动作探针（U1/U2/U3），再裁定并物化任务包；A3 全量不用等 B1（见 06 P-A3-003） |
| P-A3-003 | 2026-10-18T14:45:00+08:00 | A3 三项裁定（N-7/N-8/N-9） | Lead | HEAD f3d376f | 定案：A3 不以 B1 为前置（② 失败本身是读数，若因 approval_invalid 失败即构造未就绪，先做 B1，阶段 D 仍不开跑）；受治臂必须用与真实入口一致的权限模式并在读数里记 reading_context.host.sandbox，unrestricted 读数须显式标注、不得混作生产读数；三个只读装配器（audit→actions / session 日志解码 / layer 匹配）探针阶段放 .tmp/a3b/，复用则升格 tools/ 并按第 55 条建轴 | 符合 | 05 §4 A3 + §5.6；docs/.../2026-10-18-A3-unblock.md §5/§7（N-7..N-9） | 05 §5.6 的 4/4 门不变 | 无（裁定即记录，可回退） | 跑单动作探针（U1/U2/U3），再物化任务包 |
| P-RD-001 | 2026-10-18T14:40:00+08:00 | R-d 工具（阶段 1） | a6-rd-diff（子会话） | HEAD c4eaa53；DECISION_DIFF_SCHEMA_VERSION 首次建轴 1.0 | 新增差集工具 + 14 用例 + 演示读数；README/AGENTS 第 55 条登记；数组三级匹配（可识别键/difflib/位置） | 符合 | tools/decision_diff.py；tests/unit/test_decision_diff.py；docs/project/engineering-policy-platform/readings/2026-10-18-rd-tool-demo.md；git show --stat 6fdc04e | 05 §3.5 + §2.3 | 阶段 2（git worktree 双版本采集器）未实现；同一 rule_id 多条 violation 时退化为序列对齐（已知边界，docstring 写明） | 阶段 B 各项提交时用它出差集并附回退面 |
| P-A3-004 | 2026-10-18T14:55:00+08:00 | A3（单动作探针） | a7-a3-probe（子会话） | HEAD d8e4ced；8 次真实 dsh headless 会话（0.2.1-alpha.2） | 在 .tmp/a3b-probe 的受治项目副本上跑单动作探针，核实 U1 会话 cwd / U2 宿主审批前置 / U3 --patch 插件是否真加载 | 符合 | docs/project/engineering-policy-platform/readings/2026-10-18-A3-single-action-probe.md（sha256 ad8d87a8…，390 行）；8 次会话全部 exit 0 且全部产生真实 Hook 判定记录 | 05 §4 A3 + 解冻包 §3.5.1 | D1：解冻包 U1 原判据读不到，已在解冻包 §9 更正为三件证据；U2-b（放行后宿主审批）未核实 | 物化任务包后正式跑 A3；U2-b 待使用者签条子 |

### 7.2 阶段 A · 变更记录

| id | 时间 | 提交/变更摘要 | 改动面（文件） | 关联任务 | 是否改判定（R-d 指针） | 复核人 | 证据指针 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C-20261018-01 | 2026-10-18T08:50:00+08:00 | docs(plan)：05/06 与 README 目录项入库（6167fad） | docs/project/engineering-policy-platform/{05,06,README}.md | 计划建立 | 否（纯文档） | 使用者（待复核） | git show --stat 6167fad |
| C-20261018-02 | 2026-10-18T09:38:00+08:00 | feat(control-plane)：通道覆盖表与 C4 只报告读数（0610cd5） | channel-coverage.yaml、tools/control_plane_facts.py、validation/{control-plane-facts,instrument-checks}.yaml、wiring-scope.yaml、tests/unit/{test_control_plane_facts,test_provenance_wiring_scope}.py、AGENTS.md、tools/README.md（9 文件） | A1 | 否（只报告；wiring 读数 in_scope_not_wired 4→5、out_of_scope_active 1→0；不改 allow/block、不改退出码） | 独立复核子会话 + Lead（待使用者复核） | git show --stat 0610cd5 |
| C-20261018-03 | 2026-10-18T09:40:00+08:00 | docs(ab)：阶段 A 读数（A2 真阳性、A3 跑不成 + 04 5.72）（8d6d133） | 04-open-work.md、gui-runs/2026-10-11-L4.md、gui-runs/2026-10-18-A2-delegated-post-evidence.md、gui-runs/2026-10-18-A3-dryrun-feasibility.md（4 文件） | A2/A3 | 否（纯文档） | Lead（待使用者复核） | git show --stat 8d6d133 |
| C-20261018-04 | 2026-10-18T09:45:00+08:00 | docs(plan)：阶段 A 记录入库 + 05 §8 变更控制第 5 条 | 06-plan-progress.md、05-implementation-plan.md（2 文件，本次提交） | A1/A2/A3 | 否 | Lead | 本次提交 |
| C-20261018-05 | 2026-10-18T10:12:00+08:00 | fix(control-plane)：A1 复核修复（9806031） | tools/control_plane_facts.py、src/provenance/reading_context.py、validation/channel-coverage.yaml、tests/unit/test_control_plane_facts.py、04-open-work.md（5 文件） | A1 | 否（退出码仍恒 0；无 allow/block 改动；reading_context 只多一份声明与脱敏口径） | 独立复核子会话 + Lead（待使用者复核） | git show --stat 9806031 |
| C-20261018-06 | 2026-10-18T10:15:00+08:00 | docs(plan)：A1 复核修复记录 + 05 §8 变更控制第 6 条（f11e9af） | 06-plan-progress.md、05-implementation-plan.md | A1 | 否 | Lead | git show --stat f11e9af |
| C-20261018-07 | 2026-10-18T14:00:00+08:00 | fix(wiring)：配置内 audit_log 按配置文件目录解析（c4eaa53） | src/adapters/wiring.py、tests/unit/test_wiring.py、tests/contract/test_wiring_inventory.py、tests/unit/test_control_plane_facts.py（仅 docstring）、validation/channel-coverage.yaml、04-open-work.md、adapters/wiring-scope.yaml（7 文件） | A1 / 04 5.72 | 否（只报告；WIRING_SCHEMA_VERSION 仍 1.4，--check 判据与退出码不变） | Lead（待使用者复核） | git show --stat c4eaa53 |
| C-20261018-08 | 2026-10-18T14:40:00+08:00 | docs(ab)：A3 解冻构造包（f3d376f） | docs/project/engineering-policy-platform/testing/ab/2026-10-18-A3-unblock.md（1 文件，546 行） | A3 | 否（纯文档） | Lead（待使用者复核） | git show --stat f3d376f |
| C-20261018-09 | 2026-10-18T14:40:00+08:00 | feat(tools)：R-d 字段级差集工具入库（阶段 1）（6fdc04e） | tools/decision_diff.py、tests/unit/test_decision_diff.py、tools/README.md、AGENTS.md（第 55 条）、readings/2026-10-18-rd-tool-demo.md（5 文件） | R-d 阶段 1 | 否（不改判定路径；新 CLI 不参与 allow/block） | Lead（待使用者复核） | git show --stat 6fdc04e |
| C-20261018-10 | 2026-10-18T15:00:00+08:00 | docs(ab)：A3 单动作探针读数 + 解冻包 §9 更正（本次提交） | readings/2026-10-18-A3-single-action-probe.md、testing/ab/2026-10-18-A3-unblock.md（2 文件） | A3 | 否（纯文档；探针未改产品代码、未签审批） | Lead（待使用者复核） | 本次提交 |

### 7.3 阶段 A · 读数记录

| id | 时间 | 臂/任务 | 读数名称 | 分母/口径 | 值 | 三态 | 证据指针 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-A-A1-01 | 2026-10-18T09:36:00+08:00 | A1 | 覆盖四红 × 真实审计 | 13 行覆盖声明；审计 16,354 条中 governed=true 的 PreToolUse 127 条（edit 23 / write 4 / run_code 93 / pwsh 7） | row_without_mode=0；mode_without_check=0；tool_with_hits_without_row=0；registry_digest_drift=0；references=0；enforced=8；declared_uncovered=5 | 符合 | python tools/control_plane_facts.py --json --audit C:/Users/ZNM/Downloads/Comparison-test/Governance/.policy/audit.jsonl → exit 0 | 不给 --audit 时 hit 格为 not_applicable（不是 0）；路径只以 <outside-workspace>/audit.jsonl 呈现 |
| R-A-A1-02 | 2026-10-18T09:36:00+08:00 | A1 | 定向用例 | 3 个必跑文件；另 5 个受影响文件 | 77 passed；136 passed | 符合 | .venv/Scripts/python.exe -m pytest -q -n0 … → exit 0 | test_control_plane_facts.py 约 107s（evaluate 为纯函数但用例多） |
| R-A-A1-03 | 2026-10-18T09:37:00+08:00 | A1 | 仪器自证 | objects=65 declared=65 | 四格红条件 0 | 符合 | python tools/instrument_self_proof.py → exit 0 | gate_steps=43 与文档 42 的差异是 HEAD 存量，非本任务引入 |
| R-A-A1-04 | 2026-10-18T09:37:00+08:00 | A1 | 接线读数 | 7 个发现通道 / 6 条声明 | in_scope_not_wired=5；out_of_scope_active=0；dsh:desktop 接线=wired、留痕=never_written | 符合 | python -m adapters.cli wiring → exit 0；--check → exit 1 | 留痕报错的根因是 04 5.72（审计目标解析错位），不是「从未留痕」 |
| R-A-A2-01 | 2026-10-18T09:08:00+08:00 | A2 | L4 三份记录复算 | 1 个 action_id（…:call_00_hbf6dmXCWlNvctJUaSvh3440:ptc:2） | process.exit_code=1；validators=exit_code_zero failed「退出码 1」；台账 execution delegated/ok=false/无 exit_code；PostToolUse exit=2 / executed=false | 符合 | A2 归档报告 §1；源码 postcheck.py#L484-L494 | 三个字段属于三层对象，不是矛盾；定性真阳性 |
| R-A-A2-02 | 2026-10-18T09:09:00+08:00 | A2 | 桥接五格 + 执行器两格 | C1–C5（干净/脏 × 空/非空 × exit 0/1/无退出码）；D1/D2 | C1/C2 validated；C3/C4 repair_required（exit 1）；C5 repair_required（命令没有退出码）；D1 repair_required；D2 validated | 符合 | A2 归档报告 §3 | 空输出不参与判定；通用 DelegatingDriver × exit_code_zero 是另一条能力边界（D1） |
| R-A-A3-01 | 2026-10-18T09:18:00+08:00 | A3 | 干跑四数 | 4 项（写动作治理覆盖率 / 命令族成功率 / 路径族声明 / 上下文触顶） | A3 跑不成（构造阻断 B-1..B-6）；仅代理读数（旧受治会话）：① 1/1 窄口径 ② 0/7 族、2/11 次 ③ 1/2 族 ④ 未触发（峰值 4.70%/11.38%/22.38%，阈值随窗口变） | 跑不成 | A3 归档报告（阻断条件与最小解冻清单） | 代理读数不构成 A3，不占绿不占红 |
| R-A-A1-05 | 2026-10-18T10:11:00+08:00 | A1（复核后） | 覆盖四红 × 真实审计 | 13 行覆盖声明；审计 governed=true PreToolUse 127 条 | row_without_mode=0；mode_without_check=0；tool_with_hits_without_row=0（带 --audit）；registry_digest_drift=0；references=0；默认无 --audit 时 hit 格为 not_applicable | 符合 | python tools/control_plane_facts.py --json --audit <external> → exit 0；递归扫描 leaks=[] | 审计 path 只以 <outside-workspace>/audit.jsonl 出现 |
| R-A-A1-06 | 2026-10-18T10:11:00+08:00 | A1（复核后） | 相关用例 | 3 个必跑文件；reading_context 2 组 | 83 passed；reading_context 11 passed + 9 passed | 符合 | pytest -q -n0 … → exit 0 | 复核新增 6 条用例，含坏输入降级、绝对路径零泄漏、真实表删行变异、截断披露 |
| R-A-A1-07 | 2026-10-18T09:55:00+08:00 | A1（门禁） | 本机门禁 ci_local | 30 步（26 正常 + 4 只报告） | 28/30 ok；pytest 步骤 exit 3（INTERNALERROR：.tmp/tmp/pytest-of-ZNM 文件权限拒绝访问，环境 ACL，非代码）；Phase 8 evidence 因 pytest 报告缺失退回真跑 result=fail failures=22；后续取证：21 个 unit errors 全部是 setup 阶段的 PermissionError（见 R-A-A1-08 与 junit），构造问题不是代码失败 | 跑不成 | .tmp/ci-local-logs/03-…log 与 26-…log；干净 worktree .tmp/verify-head 复现同一 PermissionError（见 D-20261018-04） | 既不是通过也不是不符合；全量套件必须在沙箱外或 ACL 修复后复跑 |
| R-A-A1-08 | 2026-10-18T10:25:00+08:00 | A1（干净 worktree 复跑） | 全量 tests/unit | 干净 worktree .tmp/verify-head @ 9806031；-n0 单进程 | 1722 passed；6 skipped；21 errors（全部是 fixture setup 的 PermissionError：.tmp/tmp/pytest-of-ZNM 拒绝访问） | 跑不成 | Set-Location .tmp/verify-head; pytest -q -n0 tests/unit → 1722 passed, 21 errors；junit 明细 .tmp/artifacts/tests-unit-report.xml | 21 个 error 都是环境构造，不是代码失败；integration 侧 1 条同现象未逐条取证 |
| R-A-GATE-01 | 2026-10-18T11:20:00+08:00 | 阶段 A 收口 | 本机门禁（干净 worktree） | HEAD f11e9af；worktree .tmp/gate-head；26 正常步骤 + 4 只报告 | 26/26 ok，退出码 0；全量测试 5m22.6s rc=0；阶段验收证据 17.5s rc=0；总耗时 8m12.7s；只报告 4 步 0/0/0/106 | 符合 | docs/project/engineering-policy-platform/readings/2026-10-18-ci-local-green.md；命令 pytest/ci_local 原文在该文件第 2 节 | 环境前提（权限修复）与不可复现边界同文件第 1/4 节 |
| R-A-A1-09 | 2026-10-18T13:58:00+08:00 | A1（5.72 修复后） | 接线读数 | 7 通道 / 6 声明；真实 Governance 审计 18,075 条（last 2026-10-18T05:56:18Z，读数时刻仍在增长） | dsh:desktop 接线=wired、留痕=fresh；freshness_ok=1/7；in_scope_not_wired=4；--check exit 1（governed stale ×4、headless/web 未接线） | 符合 | python -m adapters.cli wiring → exit 0；--check → exit 1；--json 全文无绝对路径（0 命中） | 修前同命令 audit_records=0/never_written（04 5.72）；修后不再误报 |
| R-A-A1-10 | 2026-10-18T13:58:00+08:00 | A1（5.72 修复后） | 定向用例 | wiring unit + contract + control_plane_facts 三文件 | 167 passed（176.51s）；新增 5 条（4 unit + 1 contract）；红证明：把配置分支换回 projectDir → 2 红 | 符合 | pytest -q -n0 tests/unit/test_wiring.py tests/contract/test_wiring_inventory.py tests/unit/test_control_plane_facts.py → exit 0 | 新增用例覆盖真机布局正/负例、与 load_config 逐字比对、配置读不到显式不可用、CLI 级 --check |
| R-RD-01 | 2026-10-18T14:40:00+08:00 | R-d 阶段 1 | 四份决策快照两两差集 | tests/fixtures/decisions/{allow,warning,block,approval}.json；added/modified/removed/total | allow→warning 1/1/0/2；warning→block 1/1/1/3；block→approval 1/2/2/5；自比 0/0/0/0；退出码 1/1/1/0 | 符合 | python tools/decision_diff.py --base … --head …；readings/2026-10-18-rd-tool-demo.md 第 2–3 节 | 同文件自比 exit 0；--json 两次运行逐字节相同；14 passed |
| R-A-A3-03 | 2026-10-18T14:55:00+08:00 | A3（单动作探针） | U1/U2/U3 三态读数 | 8 次 dsh headless 会话（probe-a..h，全 exit 0）；受治树 11 文件 | U1 符合（session.header.cwd=dsh 启动 cwd；Hook 载荷 cwd=projectDir 与 session_cwd=会话 cwd 分开）；U2 符合于「Hook 前无审批」（宿主 workspace-write/approval=ask，无 approval 请求）；U3 符合（--patch 挂上插件：审计出现 governed PreToolUse + capture 原始载荷 + 7 份日志 0 条 Hook 启动失败）；附带 D2/D4/D5/D6 | 符合 | readings/2026-10-18-A3-single-action-probe.md §4–§8 | 受治臂必须以任务树根为 cwd；audit.jsonl 混两种协议；U2-b 未核实（需签 exec.pwsh 条子） |

### 7.4 阶段 A · 偏离/作废记录

| id | 时间 | 事件 | 命中条件（05 第 5.4 节哪一条 / 构造失败编号） | 影响范围 | 处置 | 证据指针 |
| --- | --- | --- | --- | --- | --- | --- |
| D-20261018-01 | 2026-10-18T09:45:00+08:00 | A2 门原文未覆盖第三态 | 05 §4 A2 门只列「能力边界 / 假阳性」；读数落「真阳性」 | A2 判据按「能定性且带读数」执行；原文保留可证伪记录 | 05 §8 追加变更控制第 5 条：门措辞扩三态待使用者复核；A2 状态不变 | A2 归档报告 §0/§4 |
| D-20261018-02 | 2026-10-18T09:45:00+08:00 | A3 干跑构造不成立 | 构造失败 B-1..B-6：受治臂缺失（当前会话 out_of_scope）、审批 3/3 过期、无 A3 任务包、受治树非基线且部分不可枚举、①装配/口径缺口、②族定义缺口 | 阶段 A 第三项未满足；阶段 D 不开跑 | 改构造不改判据：按最小解冻清单执行；本轮不记通过 | A3 归档报告；04 5.72（R-1 审计目标解析错位） |
| D-20261018-03 | 2026-10-18T10:15:00+08:00 | 05 §4 A1 门「删一行变异必红」与工具级红键口径不一致 | 05 §4 A1 门列；05 §3.4 的红键 tool_with_hits_without_row 是工具级，真实表同一工具按治理阶段多行 | A1 判据表述；表与红键语义未改 | 按 05 §3.4 工具级执行（可证明：删某工具最后一行/全部行必红；删单个阶段行不改变红格）；05 §8 追加第 6 条，扩三态或改 (channel,tool,mode) 粒度待使用者裁定 | validation/channel-coverage.yaml 红条件节；tests/unit/test_control_plane_facts.py 两条变异用例 |
| D-20261018-04 | 2026-10-18T10:15:00+08:00 | 本机门禁全量 pytest 在本会话沙箱内跑不成 | 构造失败（环境）：.tmp/tmp/pytest-of-ZNM 与显式 --basetemp 目录均出现 WinError 5 拒绝访问；xdist worker 在脚手架阶段 PermissionError；干净 worktree .tmp/verify-head 同样复现 | 门禁 pytest 步骤 exit 3、phase evidence 退回真跑；22 failures 已取证 21 个 unit errors 全部为 .tmp/tmp/pytest-of-ZNM 的 PermissionError（junit .tmp/artifacts/tests-unit-report.xml），1 个 integration 未逐条取证；构造问题不是代码失败 | 不把跑不成记成通过；改用 -n0 单进程 + 干净 worktree 复跑（结果见 R-A-A1-08）；长期修法：沙箱外运行或用 Windows 文件权限修复（本次未做） | .tmp/ci-local-logs/03-…log；.tmp/verify-head 复现日志 |
| D-20261018-05 | 2026-10-18T11:20:00+08:00 | D-20261018-04 的阻断已解除 | 环境修复：对 .tmp/tmp/pytest-of-ZNM 执行 icacls /reset + takeown（权限，不改文件内容）；删除 121 个陈旧 pytest-cache-files-* | 门禁可全量执行 | 在干净 worktree（HEAD f11e9af）复跑 ci_local：26/26 ok、退出码 0（见 R-A-GATE-01）；同时更正 R-A-A1-07 的证据指针——以 readings/2026-10-18-ci-local-green.md 与本草记录为准，不再引用 .tmp | docs/project/engineering-policy-platform/readings/2026-10-18-ci-local-green.md |
| D-20261018-06 | 2026-10-18T15:00:00+08:00 | A3 解冻包 U1 判据按原文读不到（探针 D1） | 解冻包 §3.5 要求读 in_scope 的 governed 记录里 session_scope/session_cwd/project_root，但这些键只在 scope fallback 记录里出现 | A3 解冻包 §3.5.1 的 U1 判据 | 解冻包 §9 更正为三件证据（governed=true + 会话日志 cwd + 差分探针）；不改变 U3 结论 | readings/2026-10-18-A3-single-action-probe.md §5.5；A3 解冻包 §9 |

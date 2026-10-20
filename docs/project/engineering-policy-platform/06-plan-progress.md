# 06 · 计划进度（记录格式规范）

> **状态**：2026-10-17 建立。本文件规定记录格式（§1–§6），执行记录按该格式收录在 §7。
> **上位文件**：05-implementation-plan.md（阶段、任务编号、门与判据都在那里；本文件不重复判据，也不修改判据）。

---

## 0 这份文件是什么

- 它是 05 计划的**执行台账**：收录每一次执行的技术读数与关键决策记录（一次 run、一次探针、一次改判定/协议/数据的变更、一次读数）。
- 它**只保留技术读数与关键决策记录**：纯文档 / 措辞 / 行政性变更不记录；已收录的记录仍不删改，要更正就追一条新记录，并在「偏差」列写清更正了什么。
- 它**不是**分析文档：不写论证、不写建议、不写结论性判断；结论只能以「三态 + 证据指针」的形式出现。
- 它与本目录 README「过程记录不再保留」的决定不冲突：本文件只记三态与证据指针，不写叙述；计划关闭时，结论提炼进 04-open-work 与 05，本文件归档。

---

## 1 记录单元与编号规则

| 记录类型 | 何时写 | 编号 | 一行还是多行 |
| --- | --- | --- | --- |
| 进度记录 | 每完成 05 里的一个任务（A1/B1/…）或它的一次子步骤 | P-<任务编号>-<三位序号> | 一个任务一行；子步骤另起行 |
| 变更记录 | 每次提交/改动数据或代码 | C-<YYYYMMDD>-<两位序号> | 一次提交一行 |
| 读数记录 | 每次产生读数（探针、干跑、run、审计解析） | R-<臂>-<任务>-<两位序号> | 一次读数一行 |
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
7. 不合并记录；只保留技术读数与关键决策记录（纯文档 / 措辞 / 行政性变更不记录）；已收录记录仍不删改（更正用新记录 + 偏差列）。

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

## 7 执行记录

以下小节按第 6 节模板收录；未产生记录的阶段为空。

- 阶段 A 执行情况：见 §7.1–§7.4（2026-10-18；A1/A2 已落地，A3 v2 4/4 + 任务完成）。
- 阶段 B 执行情况：见 §7.5（**B1/B2/B3 均已落地**：B2 47fa325、B1 fe292b9、B3 9a88112）。
- 阶段 C 执行情况：见 §7.5.1（**C3 v1 与第三件 v1 均已落地**；C1/C2/C4 裁定草案 2026-10-21 已出、待确认）。
- 阶段 D 执行情况：见 §7.6（校准门通过 + 门 2 前置包冻结 + **A/B/C 已于 2026-10-20 各跑一次**；H2/H3 已复核、三份 run-manifest `--strict` PASS）。
- 汇总与复审：见 §7.7（2026-10-18 汇总 + 2026-10-20 B1/C3 增补）。

### 7.1 阶段 A · 进度记录

| id | 时间 | 阶段/任务 | 执行者 | 起点锁 | 做了什么 | 结果 | 证据指针 | 判据 | 偏差 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P-A1-001 | 2026-10-18T09:35:00+08:00 | A1 | a1-coverage（子会话） | HEAD 6167fad；CONTROL_PLANE_FACTS_SCHEMA_VERSION 1.0→1.1；facts 13→14 行 | 新建通道覆盖表并接入 C4 只报告读数；桌面通道 out_of_scope→in_scope；用例含删行变异 | 符合 | validation/channel-coverage.yaml#L1-L266；python tools/control_plane_facts.py --audit <external> → exit 0（CONTROL_PLANE_FACTS 四红 0）；pytest -q -n0 tests/unit/test_control_plane_facts.py tests/contract/test_wiring_inventory.py tests/unit/test_provenance_wiring_scope.py → 77 passed | 05 §4 A1 + §3.4 | 三处设计取值（见 C-20261018-02）；desktop 归因初稿「审计目标不存在」经 04 5.72 更正为「解析错位」 | 升格未做（ci_local 无稳定 --audit 来源）；最终树门禁属阶段 C3 |
| P-A2-001 | 2026-10-18T09:10:00+08:00 | A2 | a2-delegated-probe（子会话） | HEAD 6167fad；audit 1.3（只读）；ledger 1.0；approval 1.2（副本仅延期） | 复算 L4 三份记录 + 真实桥接五格 + 执行器 D1/D2，定性 5.71 | 符合 | docs/project/engineering-policy-platform/testing/ab/gui-runs/2026-10-18-A2-delegated-post-evidence.md；src/adapters/dsh/enforcement.py#L432-L527；src/enforcement/postcheck.py#L326-L337 与 #L484-L494 | 05 §4 A2 + 04 5.71 | 门原文只列两态，实际落第三态（D-20261018-01） | 解释性证据缺口列为 Phase B 候选（未裁定） |
| P-A3-001 | 2026-10-18T09:20:00+08:00 | A3 | a3-dryrun-recon（子会话；session 98ecab06…） | HEAD 6167fad；audit 15,014→15,421 条；approval 3/3 过期（2026-10-17T23:38Z 与 23:59Z） | 判定干跑四数可行性、代理读数与阻断条件；确认当前会话 out_of_scope | 跑不成 | docs/project/engineering-policy-platform/testing/ab/gui-runs/2026-10-18-A3-dryrun-feasibility.md；python -m adapters.cli wiring → exit 0 与 --check → exit 1；.policy/approval.json 三条均过期 | 05 §4 A3 + §5.6 | 无 A3 任务包；代理读数不构成 A3（见 D-20261018-02） | 阶段 D 仍未开跑（构造已补齐） |
| P-A1-002 | 2026-10-18T10:10:00+08:00 | A1（复核修复轮） | a1-coverage（子会话） | HEAD 2609a6e | 修坏输入降级（保持 exit 0）、reason 绝对路径脱敏、覆盖表表达力边界表述；解耦 registry 红格、补第三份声明、截断披露、字段校验、04 陈旧读数 | 符合 | tools/control_plane_facts.py；src/provenance/reading_context.py；tests/unit/test_control_plane_facts.py；git show --stat 9806031；pytest -q -n0 三文件 → 83 passed；--audit → exit 0、leaks=[] | 05 §4 A1 | 05 A1 门「删一行变异必红」按工具级红键口径执行（现行措辞见 05 §4 A1 行） | 门禁复跑的构造限制见 D-20261018-04（全量套件须在沙箱外或 ACL 修复后复跑） |
| P-A1-004 | 2026-10-18T14:00:00+08:00 | A1（5.72 修复轮） | a4-wiring52（子会话） | HEAD f11e9af；WIRING_SCHEMA_VERSION 1.4 不变 | 修 wiring 审计目标解析（配置内 audit_log 按配置文件目录），同批同步覆盖表 desktop 四行与 04 5.72 | 符合 | src/adapters/wiring.py；tests/unit/test_wiring.py；tests/contract/test_wiring_inventory.py；validation/channel-coverage.yaml；04-open-work.md；git show --stat c4eaa53；pytest 167 passed；真实 wiring dsh:desktop=wired/fresh | 04 5.72 + 05 §3.4 | 无（只报告；--check 判据与退出码不变） | 无 |
| P-A3-002 | 2026-10-18T14:40:00+08:00 | A3（解冻构造包） | a5-a3-unblock（子会话） | HEAD f47823f（f11e9af 已被 c4eaa53 前置） | 交付 A3 解冻构造包：任务包草案、基线树方案、受治臂启动方案、审批重签清单、四数测量口径；未跑受治会话、未签审批 | 符合 | docs/project/engineering-policy-platform/testing/ab/2026-10-18-A3-unblock.md；git show --stat f3d376f | 05 §4 A3 + §5.2/§5.6 | 8 条未核实 + 3 条需裁定（N-7 A3 是否以 B1 为前置 / N-8 host 权限模式 / N-9 装配器落点） | 无 |
| P-A3-003 | 2026-10-18T14:45:00+08:00 | A3 三项裁定（N-7/N-8/N-9） | Lead | HEAD f3d376f | 定案：A3 不以 B1 为前置（② 失败本身是读数，若因 approval_invalid 失败即构造未就绪，先做 B1，阶段 D 仍不开跑）；受治臂必须用与真实入口一致的权限模式并在读数里记 reading_context.host.sandbox，unrestricted 读数须显式标注、不得混作生产读数；三个只读装配器（audit→actions / session 日志解码 / layer 匹配）探针阶段放 .tmp/a3b/，复用则升格 tools/ 并按第 55 条建轴 | 符合 | 05 §4 A3 + §5.6；docs/.../2026-10-18-A3-unblock.md §5/§7（N-7..N-9） | 05 §5.6 的 4/4 门不变 | 无（裁定即记录） | 无 |
| P-RD-001 | 2026-10-18T14:40:00+08:00 | R-d 工具（阶段 1） | a6-rd-diff（子会话） | HEAD c4eaa53；DECISION_DIFF_SCHEMA_VERSION 首次建轴 1.0 | 新增差集工具 + 14 用例 + 演示读数；README/AGENTS 第 55 条登记；数组三级匹配（可识别键/difflib/位置） | 符合 | tools/decision_diff.py；tests/unit/test_decision_diff.py；docs/project/engineering-policy-platform/readings/2026-10-18-rd-tool-demo.md；git show --stat 6fdc04e | 05 §3.5 + §2.3 | 阶段 2（git worktree 双版本采集器）未实现；同一 rule_id 多条 violation 时退化为序列对齐（已知边界，docstring 写明） | 阶段 B 各项提交时用它出差集并附回退面 |
| P-A3-004 | 2026-10-18T14:55:00+08:00 | A3（单动作探针） | a7-a3-probe（子会话） | HEAD d8e4ced；8 次真实 dsh headless 会话（0.2.1-alpha.2） | 在 .tmp/a3b-probe 的受治项目副本上跑单动作探针，核实 U1 会话 cwd / U2 宿主审批前置 / U3 --patch 插件是否真加载 | 符合 | docs/project/engineering-policy-platform/readings/2026-10-18-A3-single-action-probe.md（sha256 ad8d87a8…，390 行）；8 次会话全部 exit 0 且全部产生真实 Hook 判定记录 | 05 §4 A3 + 解冻包 §3.5.1 | D1：解冻包 U1 原判据读不到，已在解冻包 §9 更正为三件证据；U2-b（放行后宿主审批）未核实 | 无（U2-b 见 P-A3-005/006） |
| P-A3-005 | 2026-10-18T16:20:00+08:00 | A3（审批签发） | 使用者（签发） | HEAD ec63759 | 签 approval.json：schema 1.2、tool_id exec.pwsh、granted-by dshznm/reviewer、pattern 覆盖 pytest 与项目脚本两族、max_uses 200、expires 2026-10-25T10:45:03Z；sha256 9abd73a3…（临时文件不入库） | 符合 | .tmp/a3b/task-project/.policy/approval.json（sha256 9abd73a3a35b4a19fc43094a4e90c1d4f39bfbf5623f5dfafa122ab375a3473171） | 解冻包 §4.4/§4.6 | 无 | 无（U2-b 见 P-A3-006） |
| P-A3-006 | 2026-10-18T19:10:00+08:00 | A3（U2-b 探针） | 独立子会话（u2b） | HEAD d4b0a4f；条子 approval-pwsh-a3 sha256 9abd73a3…、expires 2026-10-25；探针树 .tmp/a3b-probe-u2b | 签约后三格探针（A 带条子/B 无条子/C 多传 timeoutMs），核实 Hook 放行后宿主是否仍要审批 | 符合 | docs/project/engineering-policy-platform/readings/2026-10-18-A3-U2b.md；A 格审计 enforcement_allow+allow_delegated、approval_use=1/200、宿主 approval/*=0、pytest 3 passed exit 0 post_validated；B=approval_required、C=approval_invalid | 解冻包 §3.5/§4.7 | 发现 A3 解冻包 §3.2 路径前缀缺陷（.policy/.policy/…）与 approval_file 必填；已在 §10 更正 | 无 |
| P-A3-007 | 2026-10-18T20:30:00+08:00 | A3（执行授权） | 使用者（授权） | HEAD 8acf452；approval-pwsh-a3 未过期（2026-10-25T10:45:03Z） | 授权执行 A3 正式干跑（换新会话执行）；交付自包含的新会话提示词与起点核对 | 符合 | docs/project/engineering-policy-platform/testing/ab/2026-10-18-A3-new-session-prompt.md（提示词与硬约束） | 05 §4 A3 + 06 P-A3-003（A3 不以 B1 为前置） | 无 | 阶段 D A/B/C 仍未开跑（需使用者裁定） |
| P-A3-008 | 2026-10-18T21:05:00+08:00 | A3（任务包与受治臂装配） | taskpack（子会话） | HEAD e8037df；approval-pwsh-a3 sha256 9abd73a3…（未改）；registry 对 verify exit 0；dsh 0.2.1-alpha.2 | 物化 11 文件任务树与基线树、8 路径/5 层任务包（首消息 sha a65b6371…/3440B）；.policy 裸名配置 + approval_file + patch；hooks --self-check exit 0、registry --verify exit 0、load_config 五路径全解析 | 符合 | readings/2026-10-18-A3-dryrun.md §3/§10 | 05 §4 A3 + 解冻包 §1/§2/§3.2/§10 | 首消息按 §10.4 多一段；registry 副本 sha 45838cd8… 与 U2b §3.1 的 e8bc569b… 不同（同 approved 对 verify 0） | 无 |
| P-A3-009 | 2026-10-18T21:12:30+08:00 | A3（正式受治干跑） | Lead | HEAD e8037df；session-472d1f1b…；audit 0→102、ledger 0→48 | 以任务树根为 cwd、headless+--patch 跑一次真实受治会话（179.5 s，dsh exit 0）；首消息逐字节取自文件 | 符合（执行本身）；任务结果不符合 | readings/2026-10-18-A3-dryrun.md §4/§9 | 05 §4 A3 + 解冻包 §3.7 | 启动受 workspace-write 沙箱拒绝（EPERM），一次性 danger-full-access 授权后启动（D-20261018-07）；任务未完成（A1–A7 未达、A8 达） | 无 |
| P-A3-010 | 2026-10-18T21:30:00+08:00 | A3（四数与判定） | Lead | 同上；.tmp/a3b/bin 装配器五步 exit 0 | 四数：① 6/6=100% ② 1/2=50%（严格仪器 0/2）③ 6/6=100% ④ 未触发（峰值 2.24%、compaction 0）⇒ **3/4**，阶段 D 前置不成立 | 不符合 | readings/2026-10-18-A3-dryrun.md §5/§6 | 05 §5.6 + §4 A3 门 | ② 的失败 = 任务包构造缺陷（M1/M2 顺序 → TESTING-002 死锁）+ 平台级联（expected-red → repair_required → 熔断）；最小修复清单见 readings §6 | 无（D A/B/C 未开跑） |
| P-A3-011 | 2026-10-18T23:10:00+08:00 | A3 v2（正式受治干跑） | Lead | HEAD 9083025；approval-pwsh-a3 sha 9abd73a3…；audit 102→226、ledger 48→130 | 冻结 v2 任务包（12 文件基线 / 7 允许写 / F2 保留）重置后，以任务树根为 cwd 跑 headless 受治会话（session-6919095a…，190.2 s，dsh exit 0）；跑后 HEAD/approval/registry/adapter 四项哈希复核未变；任务完成（pytest 10 passed、demo exit 0、隐藏验收 6/6、A8 7/7 ⊆ 允许写） | 符合 | readings/2026-10-18-A3-dryrun-v2.md §2–§4 | 05 §4 A3 + 裁定 A-6/A-12 | 启动用一次性 danger-full-access（A-4）；两条非任务命令被拒（组合命令 / git status），不计 ②；审批累计 10/200 | 无 |
| P-A3-012 | 2026-10-18T23:20:00+08:00 | A3 v2 四数与 D 校准门 | Lead | 同上；D 校准用真 Hook CLI（无模型/无审批） | 四数：① 7/7=100% ② 2/2=100% ③ 7/7=100% ④ 未触发（峰值 2.239%）⇒ **4/4 + 任务完成**；D 校准：P+ 被拦（ARCH-001@1）、P− 放行、canary `write tools/audit_demo.py` 仍被 TESTING-002 拦 ⇒ **校准门通过**；A/B/C 未开跑 | 符合 | readings/2026-10-18-A3-dryrun-v2.md §1/§4/§5 | 05 §5.6 + 裁定 A-6/A-7/A-9 | ② 首试是 M1 预期红，pass 依据执行证据而非测试成功；①③④ 分辨力有限已写入 §7；D 构造门待 B1/treatment/评分器 | A/B/C 不开跑；下一步裁 treatment 并冻结评分器 |

### 7.2 变更记录

| id | 时间 | 提交/变更摘要 | 改动面（文件） | 关联任务 | 是否改判定（R-d 指针） | 复核人 | 证据指针 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C-20261018-02 | 2026-10-18T09:38:00+08:00 | feat(control-plane)：通道覆盖表与 C4 只报告读数（0610cd5） | channel-coverage.yaml、tools/control_plane_facts.py、validation/{control-plane-facts,instrument-checks}.yaml、wiring-scope.yaml、tests/unit/{test_control_plane_facts,test_provenance_wiring_scope}.py、AGENTS.md、tools/README.md（9 文件） | A1 | 否（只报告；wiring 读数 in_scope_not_wired 4→5、out_of_scope_active 1→0；不改 allow/block、不改退出码） | 独立复核子会话 + Lead | git show --stat 0610cd5 |
| C-20261018-05 | 2026-10-18T10:12:00+08:00 | fix(control-plane)：A1 复核修复（9806031） | tools/control_plane_facts.py、src/provenance/reading_context.py、validation/channel-coverage.yaml、tests/unit/test_control_plane_facts.py、04-open-work.md（5 文件） | A1 | 否（退出码仍恒 0；无 allow/block 改动；reading_context 只多一份声明与脱敏口径） | 独立复核子会话 + Lead | git show --stat 9806031 |
| C-20261018-07 | 2026-10-18T14:00:00+08:00 | fix(wiring)：配置内 audit_log 按配置文件目录解析（c4eaa53） | src/adapters/wiring.py、tests/unit/test_wiring.py、tests/contract/test_wiring_inventory.py、tests/unit/test_control_plane_facts.py（仅 docstring）、validation/channel-coverage.yaml、04-open-work.md、adapters/wiring-scope.yaml（7 文件） | A1 / 04 5.72 | 否（只报告；WIRING_SCHEMA_VERSION 仍 1.4，--check 判据与退出码不变） | Lead | git show --stat c4eaa53 |
| C-20261018-09 | 2026-10-18T14:40:00+08:00 | feat(tools)：R-d 字段级差集工具入库（阶段 1）（6fdc04e） | tools/decision_diff.py、tests/unit/test_decision_diff.py、tools/README.md、AGENTS.md（第 55 条）、readings/2026-10-18-rd-tool-demo.md（5 文件） | R-d 阶段 1 | 否（不改判定路径；新 CLI 不参与 allow/block） | Lead | git show --stat 6fdc04e |
| C-20261018-15 | 2026-10-18T19:42:00+08:00 | feat(validators)：B2 测试支撑声明（47fa325） | validation/test-layout.yaml、src/validators/{models,registry,selection,pipeline}.py、src/policy/check.py、examples/dsh/dsh-adapter.yaml、tests/**（9 个测试文件与 2 个夹具）、AGENTS.md、04-open-work.md、readings/2026-10-18-B2-rd.md（20 文件） | B2 | **是**（改判定：conftest/支撑文件编辑 block→allow；R-d 指针 readings/2026-10-18-B2-rd.md §4–§6） | Lead | git show --stat 47fa325 |
| C-20261018-18 | 2026-10-18T21:45:00+08:00 | docs(ab)：A3 干跑四数读数与状态（保留：被读数引用） | readings/2026-10-18-A3-dryrun.md（新增）、06-plan-progress.md、04-open-work.md（5.73 状态）、05-implementation-plan.md（§4 A3 状态列） | A3 | 否（纯文档；未改产品代码/allow/block/退出码） | Lead | git show --stat HEAD |
| C-20261019-01 | 2026-10-19T08:20:00+08:00 | feat(validators)：treatment —— tools/**/*.py 纳入生产文件（e341c08） | validation/test-layout.yaml（+6/−0）、tests/unit/test_validator_registry.py、tests/integration/test_validator_pipeline.py、dgate2/configs/before+after（9+9 快照）、readings/2026-10-19-treatment-tools-pattern.md | D 门 2 treatment | **是**（tools/** 新建 python：block → allow；R-d 63 条，非 tools 用例语义投影逐字节相同；orphan 仍 block） | Lead | git show --stat e341c08 |
| C-20261019-02 | 2026-10-19T09:40:00+08:00 | feat(tools)：A 维度 10 条结构谓词测量器（2a2cb21） | tools/structure_metrics.py、tests/unit/test_structure_metrics.py、tests/fixtures/structure_metrics/、tools/README.md、AGENTS.md（第 55 条） | D 门 2 评分器 A 维度 | 否（只读读数工具；`STRUCTURE_METRICS_SCHEMA_VERSION` 1.0 → 1.1 = A4 口径修订） | Lead | git show --stat 2a2cb21 |
| C-20261019-03 | 2026-10-19T09:55:00+08:00 | test(dgate2)：隐藏验收 30 条 + T 维度 runner（6f22cee） | dgate2/hidden/{test_acceptance_dgate2.py,runner.py,README.md} | D 门 2 评分器 T 维度 | 否（评分器输入；参考树 40/40、4 类变异各红） | Lead | git show --stat 6f22cee |
| C-20261019-04 | 2026-10-19T09:35:00+08:00 | feat(examples)：任务包 v3（6f88e59） | examples/dsh/b-plan/a3-task-v3/**（9 文件） | D 门 2 treatment 激活点 | 否（任务构造；任务包 manifest 5/5） | Lead | git show --stat 6f88e59 |
| C-20261019-05 | 2026-10-19T10:40:00+08:00 | feat(dgate2)：评分器骨架 c4d77e3 + 冻结 be63670 | dgate2/scorer/{scorer.yaml,layers.yaml,interfaces.yaml,make_manifest.py,manifest.sha256,README.md} | D 门 2 评分器 | 否（判据数据；version 1 → 2 = 冻结新增三块） | Lead（代行，使用者授权自行决策） | git show --stat c4d77e3；be63670 |
| C-20261019-06 | 2026-10-19T11:15:00+08:00 | feat(dgate2)：C 臂装配器 + 真实冒烟（99fd894） | dgate2/c-arm/{assemble.py,README.md} | D 门 2 C 臂 | 否（对照组装配；冒烟 n=1，不打分） | Lead | git show --stat 99fd894 |
| C-20261019-07 | 2026-10-19T21:49:00+08:00 | feat(dgate2)：D 门 2 开跑前置工具化（f614cea） | dgate2/run-manifest/**、dgate2/run-record/**、tests/unit/test_dgate2_{run_manifest,run_record}.py、readings/2026-10-19-D-gate2-{run-ready-verify,run-record}.md、AGENTS.md（9 文件） | D 门 2 开跑前置 ② | 否（只读工具；不改 allow/block、不改退出码、不改冻结判据） | 三个独立子会话交付 + Lead 复核（23 passed、冻结 PASS） | git show --stat f614cea |
| C-20261019-08 | 2026-10-19T21:55:00+08:00 | docs(plan)：D 门 2 开跑前置工具化——状态同步 + 04 5.81 登记 | 04-open-work.md、05-implementation-plan.md、07-status-brief.md、docs README、06-plan-progress.md | D 门 2 / 04 5.78 | 否（纯文档） | Lead | git show --stat HEAD（本行所在提交） |
| C-20261020-01 | 2026-10-20T07:58:00+08:00 | feat(dgate2)：A/B/C 三臂各一次 run 的受跟踪证据 + 案例读数 | testing/ab/dgate2/runs/2026-10-20/**、readings/2026-10-20-D-gate2-ab-c-runs.md、06/04/05 | D 门 2 A/B/C | 否（只记录 run；不改平台代码、判据或退出码） | Lead | git show --stat HEAD（本行所在提交） |
| C-20261020-02 | 2026-10-20T08:45:00+08:00 | feat(dgate2)：H2/H3 人工项复核记录 + 三份 run-manifest 填满 | readings/2026-10-20-H2-bypass-sampling.md、readings/2026-10-20-H3-a4-review.md、runs/2026-10-20/{A,B,C}/human-items.json、runs/2026-10-20/{A,B,C}/run-manifest.json、06/04 | D 门 2 人工项 | 否（只记录复核与清单；不改判据/分数/平台代码） | 使用者授权（两个子会话代执行）+ Lead 复核 | git show --stat HEAD（本行所在提交） |
| C-20261020-03 | 2026-10-20T20:05:00+08:00 | feat(enforcement)：B1 审批「参数域」——协议 1.2→1.3、注册表 1.0→1.1、族数据与工具（fe292b9） | src/enforcement/{approvals,models,precheck,cli}.py、registry/tool-registry.yaml + approved.json、tools/approval_allowlist_audit.py、examples/dsh/b-plan/README.md、tests/unit/test_enforcement_approvals.py、tests/contract/{test_approval_binding_modes,test_approval_allowlist_audit}.py、readings/2026-10-20-B1-param-domain.md | B1 | **是**（放宽：注册表声明为可选且有默认值的参数可省略，省略=只接受默认值；1.1/1.2 记录逐字不变；R-d 指针 readings/2026-10-20-B1-param-domain.md §5–§6，1.2 矩阵 18 行逐条相等、负例全拒） | Lead（使用者 2026-10-20 会话授权；registry 重审为单人仓库自审） | git show --stat fe292b9 |
| C-20261020-04 | 2026-10-20T20:10:00+08:00 | feat(tools)：C3 最终树门禁 v1（整树判定 + 规则集哈希钉住；aca9491） | tools/final_tree_gate.py、tests/unit/test_final_tree_gate.py、tests/fixtures/final_tree_gate/**、readings/2026-10-20-C3-final-tree-gate.md | C3 v1 | 否（只读工具：不改 allow/block、不写审计；v1 不含危险动作前置阻断） | Lead | git show --stat aca9491 |
| C-20261020-05 | 2026-10-20T20:20:00+08:00 | docs(plan)：B1/C3 落地状态、04 残留与 5.85 纪律、AGENTS 三条版本轴登记、授权与环境基线读数 | 04-open-work.md、05-implementation-plan.md、06-plan-progress.md、AGENTS.md、tools/README.md、readings/2026-10-20-authorization-and-env.md | B1/C3 | 否（纯文档；AGENTS 第 55 条登记 APPROVAL_AUDIT_SCHEMA_VERSION / FINAL_TREE_GATE_SCHEMA_VERSION / PIN_SCHEMA_VERSION） | Lead | git show --stat 515e271 |
| C-20261020-06 | 2026-10-20T22:10:00+08:00 | feat(enforcement)：B3 只读命令族读面闸门（read_guard，9a88112） | registry/tool-registry.yaml + approved.json、src/enforcement/models.py、src/enforcement/precheck.py、tests/unit/test_precheck_read_guard.py、tests/contract/test_registry_read_face_guard.py、tests/unit/test_enforcement_approvals.py、tests/contract/test_approval_allowlist_audit.py、readings/2026-10-20-B3-read-guard.md | B3 | **是**（新增阻断：只读族读面越界 → read_guard_blocked；18 条前后矩阵 7 条新拦、8 条合法 0 误伤；既有 reason_code 一字未改；R-d 指针 readings/2026-10-20-B3-read-guard.md §3） | Lead（使用者 2026-10-20 会话授权；registry 重审为单人仓库自审） | git show --stat 9a88112 |
| C-20261020-07 | 2026-10-20T22:20:00+08:00 | docs(plan)：B3 落地状态、04 5.70/5.86、05 §4 B3 与 06 记录（本行所在提交） | 04-open-work.md、05-implementation-plan.md、06-plan-progress.md | B3 | 否（纯文档；AGENTS 第 17 条补句因预算未写，记 04 5.86⑥） | Lead | git show --stat 47afddd |
| C-20261021-01 | 2026-10-21T02:30:00+08:00 | docs(plan)：C1/C2/C4 裁定草案 + C3 第三件范围（本行所在提交） | readings/2026-10-21-C1C2C4-adjudication-draft.md | C1/C2/C4 | 否（纯文档；草案未落地判定改动） | Lead（使用者 2026-10-20 授权） | git show --stat HEAD（本行所在提交） |
| C-20261021-02 | 2026-10-21T03:10:00+08:00 | feat(enforcement)：控制面 `.policy` 写面阻断（C3 第三件 v1，8e6a3cb） | registry/tool-registry.yaml + approved.json、src/enforcement/models.py、tests/security/test_control_plane_write_guard.py、tests/contract/test_registry_control_plane_guard.py、tests/contract/test_enforcement_protocol.py、tests/unit/test_enforcement_approvals.py、readings/2026-10-21-C3-control-plane-write-guard.md | C3 第三件 | **是**（新增阻断：`.policy` 写入 → `path_out_of_scope`；矩阵 8 条翻面、9 条逐条相等；判定路径与 reason code 未改；R-d 指针 readings/2026-10-21-C3-control-plane-write-guard.md §3） | Lead（使用者授权；registry 重审为单人仓库自审） | git show --stat 8e6a3cb |
| C-20261021-03 | 2026-10-21T03:30:00+08:00 | docs(plan)：C3 第三件落地状态、04 5.84 收口与 5.87 裁定项、06 记录（本行所在提交） | 04-open-work.md、05-implementation-plan.md、06-plan-progress.md | C3 第三件 | 否（纯文档；AGENTS 第 13/55 条的 `.policy`/1.3 补句因预算未写，记 04 5.87 与 5.80） | Lead | git show --stat HEAD（本行所在提交） |

### 7.3 读数记录

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
| R-A-A1-07 | 2026-10-18T09:55:00+08:00 | A1（门禁） | 本机门禁 ci_local | 30 步（26 正常 + 4 只报告） | 28/30 ok；pytest 步骤 exit 3（INTERNALERROR：.tmp/tmp/pytest-of-ZNM 文件权限拒绝访问，环境 ACL，非代码）；Phase 8 evidence 因 pytest 报告缺失退回真跑 result=fail failures=22；后续取证：21 个 unit errors 全部是 setup 阶段的 PermissionError（见 R-A-A1-08 与 junit），构造问题不是代码失败 | 跑不成 | readings/2026-10-18-ci-local-green.md 第 1/4 节（结论与复现边界）；干净 worktree .tmp/verify-head 复现同一 PermissionError（见 D-20261018-04；临时产物不长期保留） | 既不是通过也不是不符合；全量套件必须在沙箱外或 ACL 修复后复跑 |
| R-A-A1-08 | 2026-10-18T10:25:00+08:00 | A1（干净 worktree 复跑） | 全量 tests/unit | 干净 worktree .tmp/verify-head @ 9806031；-n0 单进程 | 1722 passed；6 skipped；21 errors（全部是 fixture setup 的 PermissionError：.tmp/tmp/pytest-of-ZNM 拒绝访问） | 跑不成 | Set-Location .tmp/verify-head; pytest -q -n0 tests/unit → 1722 passed, 21 errors；junit 明细 .tmp/artifacts/tests-unit-report.xml | 21 个 error 都是环境构造，不是代码失败；integration 侧 1 条同现象未逐条取证 |
| R-A-GATE-01 | 2026-10-18T11:20:00+08:00 | 阶段 A 收口 | 本机门禁（干净 worktree） | HEAD f11e9af；worktree .tmp/gate-head；26 正常步骤 + 4 只报告 | 26/26 ok，退出码 0；全量测试 5m22.6s rc=0；阶段验收证据 17.5s rc=0；总耗时 8m12.7s；只报告 4 步 0/0/0/106 | 符合 | docs/project/engineering-policy-platform/readings/2026-10-18-ci-local-green.md；命令 pytest/ci_local 原文在该文件第 2 节 | 环境前提（权限修复）与不可复现边界同文件第 1/4 节 |
| R-A-A1-09 | 2026-10-18T13:58:00+08:00 | A1（5.72 修复后） | 接线读数 | 7 通道 / 6 声明；真实 Governance 审计 18,075 条（last 2026-10-18T05:56:18Z，读数时刻仍在增长） | dsh:desktop 接线=wired、留痕=fresh；freshness_ok=1/7；in_scope_not_wired=4；--check exit 1（governed stale ×4、headless/web 未接线） | 符合 | python -m adapters.cli wiring → exit 0；--check → exit 1；--json 全文无绝对路径（0 命中） | 修前同命令 audit_records=0/never_written（04 5.72）；修后不再误报 |
| R-A-A1-10 | 2026-10-18T13:58:00+08:00 | A1（5.72 修复后） | 定向用例 | wiring unit + contract + control_plane_facts 三文件 | 167 passed（176.51s）；新增 5 条（4 unit + 1 contract）；红证明：把配置分支换回 projectDir → 2 红 | 符合 | pytest -q -n0 tests/unit/test_wiring.py tests/contract/test_wiring_inventory.py tests/unit/test_control_plane_facts.py → exit 0 | 新增用例覆盖真机布局正/负例、与 load_config 逐字比对、配置读不到显式不可用、CLI 级 --check |
| R-RD-01 | 2026-10-18T14:40:00+08:00 | R-d 阶段 1 | 四份决策快照两两差集 | tests/fixtures/decisions/{allow,warning,block,approval}.json；added/modified/removed/total | allow→warning 1/1/0/2；warning→block 1/1/1/3；block→approval 1/2/2/5；自比 0/0/0/0；退出码 1/1/1/0 | 符合 | python tools/decision_diff.py --base … --head …；readings/2026-10-18-rd-tool-demo.md 第 2–3 节 | 同文件自比 exit 0；--json 两次运行逐字节相同；14 passed |
| R-A-A3-03 | 2026-10-18T14:55:00+08:00 | A3（单动作探针） | U1/U2/U3 三态读数 | 8 次 dsh headless 会话（probe-a..h，全 exit 0）；受治树 11 文件 | U1 符合（session.header.cwd=dsh 启动 cwd；Hook 载荷 cwd=projectDir 与 session_cwd=会话 cwd 分开）；U2 符合于「Hook 前无审批」（宿主 workspace-write/approval=ask，无 approval 请求）；U3 符合（--patch 挂上插件：审计出现 governed PreToolUse + capture 原始载荷 + 7 份日志 0 条 Hook 启动失败）；附带 D2/D4/D5/D6 | 符合 | readings/2026-10-18-A3-single-action-probe.md §4–§8 | 受治臂必须以任务树根为 cwd；audit.jsonl 混两种协议；U2-b 未核实（需签 exec.pwsh 条子） |
| R-A-GATE-02 | 2026-10-18T15:05:00+08:00 | 阶段 A/工具收口 | 本机门禁（第二次，干净 worktree） | HEAD d8e4ced（含 5.72 修复 c4eaa53 与 R-d 工具 6fdc04e）；26 正常步骤 + 4 只报告 | 26/26 ok，退出码 0；总耗时 7m55.7s；全量测试 5m04.8s；只报告 0/0/0/106 | 符合 | docs/project/engineering-policy-platform/readings/2026-10-18-ci-local-green.md 第 5 节 | 与 R-A-GATE-01 相比代码已变（wiring 修复 + 新工具），门禁仍全绿 |
| R-B2-01 | 2026-10-18T19:38:00+08:00 | B2 | R-d 字段级差集 | 5 对完整 policy.check --json 载荷（3 组合条目 + 示例 conftest edit ×2） | added=24 modified=51 removed=3 total=78；conftest-alone 8/11/1/20；conftest-with-implementation 与 tests-only 的 result 段 0 条（仅 tree/version 元数据变）；example 两对 8/14/1/23 与 8/16/1/25 | 符合 | readings/2026-10-18-B2-rd.md §4–§6（BEFORE/AFTER 采集命令、全量差集与逐条解释） | 非预期字段已查清：tree 因他人 A3 文档提交漂移；test_layout digest 与 pipeline 1.3→1.4 为设计内 |
| R-B2-02 | 2026-10-18T19:38:00+08:00 | B2 | 组合门与决策快照 | 3 条 combination 条目；4 份决策快照 | BEFORE 6 passed（conftest-alone=block）→ AFTER 6 passed（conftest-alone=allow，served 含 failing_tests）；4 份快照 sha256 前后逐个相同、pytest 26 passed ×2 | 符合 | tests/integration/test_rule_combinations.py；readings §7–§8 | 只翻 conftest-alone 一个条目；其余条目 result 不变 |
| R-B2-03 | 2026-10-18T19:38:00+08:00 | B2 | 真实 Hook（pre_evidence） | 1 条 PreToolUse edit conftest.py（第 2 代载荷 + budget 20000+5000<30000） | exit 0；allow / governed=true / layer=test（matched **/conftest.py）/ pre_evidence_status=collected / served 含 failing_tests / pytest ok / violations=[]；新 event id 复跑同结果；同 event id 重放 → event_replay exit 2（幂等保护，不是失败） | 符合 | readings/2026-10-18-B2-rd.md §9（探针载荷、命令与审计摘录） | pre_evidence 只在示例部署配置下启用，示例配置本身仍保持注释（未改变例默认行为） |
| R-B2-04 | 2026-10-18T19:41:00+08:00 | B2 | 定向测试 | 8 文件（validator checkers/registry、control-plane facts、dsh layer、validator protocol、rule combinations、validator pipeline、cli） | **259 passed**（159.01s）；text conventions 692 文件 0 问题；git diff --check 干净 | 符合 | pytest -q -n0 … → exit 0 | tests/integration/test_api_http.py 的 pipeline 版本断言原写死 1.3，已改为从 PIPELINE_SCHEMA_VERSION 取值（B2 同批） |
| R-B2-05 | 2026-10-18T19:58:00+08:00 | B2 | 本机门禁（B2 提交后） | 干净 worktree .tmp/gate-b2 @ 47fa325；26 正常步骤 + 4 只报告 | **26/26 ok，退出码 0**；总耗时 4m16.4s；全量测试 2m45.0s rc=0；阶段验收证据 7.2s rc=0；只报告 0/0/0/106 | 符合 | docs/project/engineering-policy-platform/readings/2026-10-18-B2-gate.md（命令、26/26、耗时与首次红的上修） | 首次门禁在 aac56f2 上红 1 条（test_api_http 的 1.3 断言），修复后全绿；提交 47fa325 |
| R-A-A3-04 | 2026-10-18T21:20:00+08:00 | A3 | ① 写动作治理覆盖率 | 分母=本次实际任务文件变化（added 1/modified 5）；分子=有受治 PreToolUse 写判定记录的任务文件 | 6/6 = **100%**；unmeasured=0；uncovered=0；2 个受治 block 未落地（order_audit.py/audit_demo.py）单列 | 符合 | readings/2026-10-18-A3-dryrun.md §5.1 | 树 diff 复用 tools/ab_measure.changed_lines_from_trees（exclude .policy）；__pycache__/.pytest_cache 由仪器默认排除 |
| R-A-A3-05 | 2026-10-18T21:20:00+08:00 | A3 | ② 命令族首次成功率 | 分母=预注册 F1/F2 各首次尝试；分子=放行且真进入执行（命令自身退出码不计） | F1 1/1 通过（allow+grant，post_evidence.exit_code=1，post_repair_required 单列）；F2 0/1（circuit_open，未执行）⇒ **1/2=50%**；严格仪器口径 0/2=0%；失败原因无 approval_invalid | 不符合 | readings/2026-10-18-A3-dryrun.md §5.2 | 熔断：三次 post_check_failed 后 circuit_open；M7 与 F2 被挡 |
| R-A-A3-06 | 2026-10-18T21:20:00+08:00 | A3 | ③ 路径族 layer 声明 | 分母=实际被写任务路径 6；layer 由 .policy/dsh-adapter.yaml first-match | 6/6=**100%**；unmapped 0；审计交叉 8/8 一致；tests 全部 test | 符合 | readings/2026-10-18-A3-dryrun.md §5.3 | load_config + layer_resolution（同一实现，无第二套 glob） |
| R-A-A3-07 | 2026-10-18T21:20:00+08:00 | A3 | ④ 上下文触顶 | 会话日志 request/context、assistant/message usage、compaction/* | 未触发：compaction 0；峰值 inputTokens 22,435 / contextWindow 1,000,000 = 2.24%；阈值 0.8×W=800,000 | 符合 | readings/2026-10-18-A3-dryrun.md §5.4 | reading_context：host.sandbox=restricted（启动 EPERM 授权）；run id 见 §5.5 |
| R-A-A3-08 | 2026-10-18T22:15:00+08:00 | A3（修正仪器复算） | ② 的仪器修正前后 | 归档 run-01 数据（同 session/audit）；F1 4 次、F2 1 次、other 1 次 | 修正前 first_pass=**0/2**（F1 被记 host_stage）→ 修正后 **1/2**（F1 通过、F2 仍 circuit_open）；② 仍 50%；u2b 自测 1/1 不变 | 符合（归因修正，判据不变） | readings/2026-10-18-A3-fix-adjudication.md §3；.tmp/a3b/readings/run-01-command-families-fixed.json | 旧 0/2 保留为历史；仪器升格触发见 04 5.77 |
| R-A-A3-09 | 2026-10-18T23:15:00+08:00 | A3 v2 | 干跑四数 | 分母：① 实际任务文件变化 7；② 预注册族 2；③ 实际被写路径 7；④ 会话日志 | ① 7/7=**100%**（unmeasured 0、blocked-not-landed 0）② **2/2=100%**（F1 首试 M1 预期红但放行+真执行 exit 1；F2 首试 demo exit 0；族内 0 approval_invalid）③ 7/7=**100%**（unmapped 0；审计交叉 8/8）④ 未触发（compaction 0；峰值 22,390/1,000,000=2.239%） | 符合 | readings/2026-10-18-A3-dryrun-v2.md §4；.tmp/a3b2/readings/run-02-*.json | 判据冻结见裁定 A-7；审批累计 10/200；两次非族命令被拒不计 ② |
| R-A-A3-10 | 2026-10-18T23:18:00+08:00 | D 校准门（无模型） | P+ / P− / canary | 真 Hook CLI；树=12 文件 v2 基线 + 同一受治配置 | P+（controller 直接 import repository）exit 2 / block / violations [ARCH-001@1, STYLE-002@1, STYLE-018@1]；P−（repository docstring 编辑）exit 0 / allow / violations []；canary（write tools/audit_demo.py）exit 2 / block / violations [TESTING-002@1] | 符合（校准通过；canary 如预期仍红） | readings/2026-10-18-A3-dryrun-v2.md §5；.tmp/a3b2/d-calibration.json | 裁定 A-6/A-9；缺口 04 5.75 未消失 |
| R-A-A3-11 | 2026-10-18T23:12:00+08:00 | A3 v2 | 任务完成（A1–A7） | 最终树；隐藏验收 6 条 + 树执行 2 条 + A8 diff | 隐藏验收 A1/A2/A3/A4/A5/A7 **6/6 passed**；`python -m pytest -q` = 10 passed / exit 0；`python tools/audit_demo.py` = exit 0 + 合法 JSON；树 diff 恰 7 个允许写、0 unexpected | 符合 | .tmp/a3b2/hidden/test_acceptance.py；readings/2026-10-18-A3-dryrun-v2.md §3/§4 | 裁定 A-12（D 开场附加条件） |
| R-A-GATE-03 | 2026-10-18T23:55:00+08:00 | A3 v2 收口 | 本机门禁 ci_local | HEAD 98169bf；干净工作树；26 正常步骤 + 4 只报告 | **26/26 ok，退出码 0**；总耗时 4m49.3s；只报告 4 步（非零退出不计入失败） | 符合 | readings/2026-10-18-A3-dryrun-v2.md §10；.tmp/a3b2/ci-local-v2.log | 改动为文档 + examples 任务包，无产品代码改动；门禁执行 26 步全绿 |
| R-A-GATE-04 | 2026-10-19T07:40:15+08:00 | 文档去噪收口 | 本机门禁 ci_local（改后，工作树含 4 个未提交文件） | HEAD bbd45c2 + 05/06/README 与本次新增 readings；26 正常步骤 + 4 只报告 | **25/26 ok**；pytest 步骤 exit 3 跑不成（`.tmp/tmp/pytest-of-ZNM/pytest-NN/.lock` PermissionError，D-20261018-04 复发：沙箱内建不出 basetemp）；单进程全量套件另跑 3024 passed / 6 skipped / 22 errors（22 个全是同一 PermissionError，非代码失败）；文档类步骤全绿（text conventions 0 问题、consistency 通过、notebook 同步与执行在首轮通过） | 跑不成 | readings/2026-10-19-gate-doc-density.md 第 1–3 节 | 纯文档改动；HEAD 98169bf 上 R-A-GATE-03 为 26/26，本次 pytest 结论与其等价；第二轮 notebook rc=1 是并行编辑 04 触发工作区守卫，不计 |
| R-A-D2-01 | 2026-10-19T08:20:00+08:00 | D 门 2 treatment | tools/** 纳入生产文件的 R-d 与 activation | 固定语料 9 例 × 2 配置（平台钉 HEAD）；同动作 config-root before/after | added=23 modified=37 removed=3；非 tools 6 例语义投影逐字节相同（唯一差集=test-layout 声明摘要 2 条/例）；tools orphan 仍 block（理由换 TESTING-001）；activation：after=allow / before=block(critical)；5 类反例两臂仍 block；全量 3046 passed | 符合 | readings/2026-10-19-treatment-tools-pattern.md §5–§8 | 改判定的唯一一处；回退=删一行+5 行注释+2 条用例 |
| R-A-D2-02 | 2026-10-19T09:40:00+08:00 | D 门 2 A 维度 | structure_metrics 参考树与变异 | 参考树 .tmp/lead-v3/ref（16 文件）；scorer/layers.yaml + interfaces.yaml | 参考树 **10/10 pass**（两次逐字节相同 sha b05e961f…）；4 条变异自证（环⇒A2、59 行⇒A6、缺 docstring⇒A7、动态 import⇒A10）改前绿/变异红/撤回绿；A4 专项：__init__ 默认装配 pass（default_wiring_instantiations=2）、业务方法 new 仓库 fail | 符合 | tools/README.md；tests/unit/test_structure_metrics.py（29 passed）；memo §9 | A4 口径修订记录在 memo §9 第 2 条 |
| R-A-D2-03 | 2026-10-19T09:55:00+08:00 | D 门 2 T 维度 | 30 条隐藏验收 + 入口/接口 | 参考树；POLICY_TREE 传树根 | **40/40 pass、exit 0**；两次 stdout 逐字节相同（sha 65317892…）；4 类变异各至少红一条（复制语义⇒T12/13/14+I2；直连 repository⇒T18+I5；不记审计⇒T03/04/06/07+T11；demo 少一条⇒T27） | 符合 | dgate2/hidden/README.md；runner 载荷 | 11 条规格含糊已写进 README，冻结前对齐 |
| R-A-D2-04 | 2026-10-19T10:40:00+08:00 | D 门 2 评分器 | 冻结清单与 C 维度自证 | scorer/manifest.sha256 的 7 组输入 25 文件 | 组合摘要 sha256:e3ef9e91…；`--check --strict` PASS、pending 0；C 维度 8 条规则各一处变异均命中（ARCH / TESTING-1/2 / STYLE-002/018/001/010 / DOC-001）；C 参考树 24/24、T 40/40、A 10/10 | 符合 | dgate2/scorer/README.md §11；scorer.yaml freeze | 文件集=改动面 8 个 .py；--changed 9 条 |
| R-A-D2-05 | 2026-10-19T11:15:00+08:00 | D 门 2 C 臂 | 不治理的冒烟 | dsh 0.2.1-alpha.2 headless，无 --patch；树=12 文件基线（4e7c4073…） | exit 0、10.2s、3 次工具调用含 1 write、产物落盘；**本 session 在治理账本 0 条**（总 Δ+53 全是并发会话 out_of_scope）；插件未加载 5 条证据（dump-config / profile patch=[] / session log / argv / 树无 .policy） | 符合（n=1 冒烟，不打分） | dgate2/c-arm/README.md | score_eligible=no（冒烟）；正式 run 用冻结首消息 123c938c… |
| R-A-D2-06 | 2026-10-19T21:44:00+08:00 | D 门 2 | 冻结包复核 | 25 文件（scorer 清单）+ 任务包 5 + 两臂各 9 + 参考树 16 | make_manifest --check --strict → PASS（25 逐字节一致、0 pending）；组合摘要 sha256:e3ef9e91e8cd…dd649a；任务包 manifest 44d85e7e…、首消息 123c938c…；before/after 各 9/9、只差 test-layout.yaml；参考树 files_digest 7ea8d5e5…、A 10/10、C 24/24、T 40/40 | 符合 | readings/2026-10-19-D-gate2-run-ready-verify.md §1–§3 | 两次运行逐字节相同；T 在旧沙箱首次 30/40（04 5.81②） |
| R-A-D2-07 | 2026-10-19T21:47:00+08:00 | D 门 2 | run-record 样例 + Lead 原生复跑 | 参考树 16 文件；10 条子命令（T+A+8×C） | collect exit 0；T 40/40、C 24/24（8/8 allow、layer_source=declared、check_volume.complete=true）、A 10/10；载荷 sha256 40f55c46…（三次相同）；danger-full-access 无垫片复跑：dimensions/summary/commands 与样例逐项相等（仅 tree 标签不同） | 符合 | readings/2026-10-19-D-gate2-run-record.md §1/§5/§10 | 无时戳/无绝对路径；C 只覆盖规则分 24，不含 frozen_untouched/bypass 6 分 |
| R-A-D2-08 | 2026-10-19T21:45:00+08:00 | D 门 2 | run-manifest 真实生成与校验 | A 臂开跑前；HEAD c44f9db | --arm A → recorded 10 / pending 7；--check → 0；--check --strict → 1（human_items_unrecorded + incomplete_freeze）；补 reference-tree / arm-facts / run-record / human-items 后 recorded 16 / pending 0 / not_applicable 1（H4）、--strict → 0 | 符合 | run-manifest/README.md §3；tests/unit/test_dgate2_run_manifest.py（13 passed，覆盖删字段/摘要漂移/strict） | 就绪判据 = --check --strict 0；开跑前清单允许 pending；现场载荷在 .tmp（不提交） |
| R-A-D2-09 | 2026-10-19T23:35:00+08:00 | D 门 2 | 两臂受治树装配 + 真实 Hook 探针 | A/B 各 12 文件（基线 4e7c4073…）+ 各 6 个 .policy 文件；探针在各自的 probe-tree 副本上 | registry --verify 两臂 exit 0（10 工具 ok）；hooks --self-check 两臂 exit 0；M5b 探针：A exit 2 / block / TESTING-002 critical uncovered_checker（served 无 failing_tests）；B exit 2 / block / TESTING-002 error（served **含** failing_tests，真跑了测试）| 符合（接线可证伪；B 的 block 是基线树缺参考实现的真违规） | readings/2026-10-19-D-gate2-arm-assembly.md §1–§2；探针脚本 .tmp/dgate2-arms/probe.py（现场） | 探针不是正式读数（无模型/无计分）；条子由使用者签，代理未签发任何审批；签前不要跑 cleanup |
| R-A-D2-10 | 2026-10-20T07:52:00+08:00 | D 门 2 A/B/C | 三臂各一次 run 的案例读数 | 每臂一次；同一首消息、同一 12 文件基线、同一评分器 | A：T 30/40、A 6/10、C 规则 24/24（7/8 文件）、任务未完成、block 1（TESTING-002 uncovered_checker）、circuit_open 1；B：T 40/40、C 23/24+3+3、A 9/10（A7）、任务完成、block 0；C：T 40/40、C 24/24+3+3、A 10/10、任务完成、无审计 | 符合（run 完成；n=1 只作案例） | readings/2026-10-20-D-gate2-ab-c-runs.md §3–§4；runs/2026-10-20/{A,B,C}/run-manifest.json | 不写均值/百分比；A 的 C 不可比（第 8 文件不存在）；H2/H3 未做 → manifest strict 失败 |
| R-A-D2-11 | 2026-10-20T08:40:00+08:00 | D 门 2 | H2/H3 人工项复核（使用者授权、子会话代执行） | 12 个「臂×测试文件」抽 6（50%）；3 臂全量 AST 站点 46 | H2：5 个抽中文件未发现削弱 + 1 跑不成（A 的 demo 收集错误）；全量 0 skip/xfail/空 assert/恒真/吞断言，基线断言 12/12 保留；H3：B/C 组合根 = `tools/audit_demo.py:16` 的 `main()`，A 无组合根（A4 pass 为空真）；三份 run-manifest 变 **16 recorded / 0 pending / 1 n/a**，`--strict` PASS | 符合 | readings/2026-10-20-H2-bypass-sampling.md；readings/2026-10-20-H3-a4-review.md；runs/2026-10-20/{A,B,C}/human-items.json | 抽样人为判断性抽样、非随机；H2 不改变 A 的 B2 自动判据；A4 的 `__init__` 豁免是位置豁免（已知边界） |
| R-A-GATE-05 | 2026-10-19T12:50:00+08:00 | D 门 2 前置包收口 | 本机门禁 ci_local（danger-full-access；**收口提交后的干净树**） | 代码面 = HEAD 99fd894 + 本行所在提交的文档改动，工作树干净；26 正常步骤 + 4 只报告 | **26/26 ok，退出码 0**；总耗时 4m34.8s；只报告 4 步（0/0/0/113） | 符合 | readings/2026-10-19-gate-dgate2.md | 与 R-A-GATE-04（沙箱内 pytest 跑不成）的差别在沙箱形态，不追认成通过；12:10 那次在未提交的同一批文档上先跑过一次（26/26、5m04.6s），以本行为准 |
| R-A-GATE-06 | 2026-10-19T21:58:00+08:00 | D 门 2 开跑前置收口 | 本机门禁 ci_local --full（danger-full-access；**收口提交后的干净树**） | HEAD 473ff91；工作树干净；30 正常步骤 + 4 只报告；改动文件 142 | **30/30 ok，退出码 0**；总耗时 **6m08.5s**（368.474s）；全量测试 3m04.0s rc=0；只报告 4 步（0/0/0/113）；34 条 entries 全部 returncode 0 | 符合 | readings/2026-10-19-gate-run-ready.md；.tmp/ci-local-timings.json（现场，cleanup 会删） | 步骤 26 → 30 是 --full 把 4 个完整模式步骤算了进来，不是新增门禁步骤；与 R-A-GATE-04 的差别在沙箱形态，不追认成通过 |
| R-A-GATE-07 | 2026-10-20T21:35:00+08:00 | 本机门禁（B1/C3 收口后） | 干净树 HEAD 515e271；30 步（26 正常 + 4 只报告） | **26/26 ok，退出码 0**；总耗时 4m00.9s；全量测试 2m32.6s rc=0；只报告 4 步（义务账 0 / 豁免到期 0 / 仪器自证 0 / 控制面事实 115——`test_path_declaration=115` 是既有只报告读数，不阻断） | 符合 | python tools/ci_local.py → exit 0；日志 .tmp/ci-local-logs/ | **环境前提：必须 danger-full-access**——workspace-write 下 xdist 工作进程读不到控制器建的 .tmp/tmp/pytest-of-ZNM（PermissionError → INTERNALERROR → pytest 步骤 exit 3），与 D-20261018-04 同型；按 R-A-GATE-05/06 先例用一次性 danger-full-access 跑 | 中断两次（一次 600s 超时、一次沙箱模式切换）不计；本行只认完成的那次 | 产品代码改动后重跑；同一工作树同时只跑一个 |
| R-A-GATE-08 | 2026-10-20T23:05:00+08:00 | 本机门禁（B3 收口后） | 干净树 HEAD 47afddd；30 步（26 正常 + 4 只报告） | **26/26 ok，退出码 0**；总耗时 5m34.2s；全量测试 3m46.0s rc=0；只报告 4 步（0/0/0/115，同 R-A-GATE-07） | 符合 | python tools/ci_local.py → exit 0；日志 .tmp/ci-local-logs/ | 环境同 R-A-GATE-07（danger-full-access；workspace-write 下 xdist 临时目录跨进程不可读） | — | 产品代码改动后重跑；同一工作树同时只跑一个 |
| R-A-GATE-09 | 2026-10-21T04:15:00+08:00 | 本机门禁（C3 第三件收口后） | 干净树 HEAD 93f0285；30 步（26 正常 + 4 只报告） | **26/26 ok，退出码 0**；总耗时 5m22.8s；全量测试 3m40.3s rc=0；只报告 4 步（0/0/0/115，同前） | 符合 | python tools/ci_local.py → exit 0；日志 .tmp/ci-local-logs/ | 环境同 R-A-GATE-07/08（danger-full-access） | — | 产品代码改动后重跑；同一工作树同时只跑一个 |
| R-B1-01 | 2026-10-20T20:00:00+08:00 | B1 | 前后对比矩阵 | 固定语料 18 用例 × 3 列 + 9 命令门 | 1.2 列 before/after 的 decision+reason_code+failed_check 逐条相等；1.3 列 12 行（三族 × 2/3/4/5 格）全 allow；负例全拒（未知参数构造期、run_in_background=true 审批层拒、非默认值拒、白名单外 command_not_allowlisted）；夹具矩阵 9/9 | 符合 | readings/2026-10-20-B1-param-domain.md §5 | 真实受治会话 9/9 无读数（待使用者签 1.3 条子） |
| R-B1-02 | 2026-10-20T20:00:00+08:00 | B1 | 定向测试 | 审批三文件 / enforcement 七文件 / registry+bridge+security 六文件 | 89 passed / 191 passed / 88 passed（均 exit 0）；tests/unit+contract 2323 passed / 6 skipped / 31 errors（31 个全是 tmp_path 在 .tmp 下的 PermissionError，setup 阶段，与改动无关） | 符合（31 errors 记环境构造） | readings/2026-10-20-B1-param-domain.md §9 | — |
| R-B1-03 | 2026-10-20T20:00:00+08:00 | B1 | 审核与守门仪器 | registry 10 工具；条子×白名单 | registry --approve exit 0；--verify exit 0；approval_allowlist_audit --check → exit 0、0 hits；self-check exit 0；4 份决策夹具 sha256 前后相同 | 符合 | readings/2026-10-20-B1-param-domain.md §6–§8 | approved.json 10 个 schema_hash 全变（族/默认值进了审核面） |
| R-C3-01 | 2026-10-20T20:10:00+08:00 | C3 v1 | 门禁用例 | 9 条 -n0 | 9 passed exit 0；干净树 0 / 坏文件 1（GATE-001@1、E501）/ 漂移 1（24f1eb… vs 5587ac…）/ 缺配置或缺验证器 2 / 两次 JSON 逐字节相同（sha256 d5819b7e…） | 符合 | readings/2026-10-20-C3-final-tree-gate.md §8 | 整树 43 条规则耗时与退出码未测 |
| R-C3-02 | 2026-10-20T20:10:00+08:00 | C3 v1 | 规则集钉住口径 | RuleSet.identity | 改语义=漂移（1）；换加载顺序≠漂移（0）；纯注释/空白不漂移（已知边界）；PIN 1.0 | 符合 | readings/2026-10-20-C3-final-tree-gate.md §6 | — |
| R-ENV-01 | 2026-10-20T19:51:00+08:00 | 环境基线 | 工作树/venv/.tmp | HEAD 30d10ae；clean；Python 3.13.11；cleanup 114,974→59,703 文件（1.9 GB→985 MB） | 工作树干净、pytest 冒烟 14 passed；.tmp 下 52 个 ACL 残留目录删不掉（cleanup exit 1，非本任务引入）；pytest 缓存目录不可建（仅告警） | 符合（两条已知约束登记） | readings/2026-10-20-authorization-and-env.md §2 | 环境可用 |
| R-B3-01 | 2026-10-20T22:05:00+08:00 | B3 | 读面前后矩阵 | 18 条固定命令；改前 = git archive HEAD 副本，改后 = 工作树，均真 CLI precheck（族级条子、dry_run） | 越界 8 条：7 条 allow→read_guard_blocked（HEAD:.policy、-- .policy、./.policy、.POLICY、-- ..、HEAD:..、C:/Users/…），1 条 command_fragment_blocked 不变；合法 8 条改前改后全 allow（0 误伤，含 HEAD:src/… 与 HEAD:/README.md 两条探针）；对照 2 条 reason_code 不变 | 符合 | readings/2026-10-20-B3-read-guard.md §3 | 400 份真实会话回放未取得（§6） |
| R-B3-02 | 2026-10-20T22:05:00+08:00 | B3 | 测试 | 新增单测 42 / 新契约 11 / unit+contract 全量 / integration+security 全量 | 42 passed；11 passed；**2407 passed, 6 skipped**；**810 passed**；全部 exit 0；导入链自检每次 ok | 符合 | readings/2026-10-20-B3-read-guard.md §4 | — |
| R-B3-03 | 2026-10-20T22:05:00+08:00 | B3 | 注册表重审与门禁读数 | 10 工具；条子×白名单 | registry --approve exit 0；registry --verify exit 0（10/10 ok）；approval_allowlist_audit --check 0 hits exit 0；approved.json governance_digest 826b9d9a→47fa192d、registry_digest 84ddc2dc→33e330b8，10/10 schema_hash 全变（read_guard:null 进每条 payload） | 符合 | readings/2026-10-20-B3-read-guard.md §5 | 受治侧 local registry 未同步（04 5.86①） |
| R-C3-03 | 2026-10-21T03:05:00+08:00 | C3 第三件 | 控制面写面前后矩阵 | 17 条固定请求；改前 = HEAD 副本，改后 = 工作树，真实 CLI precheck dry_run；机械合并 violations=none | 写面 8/8：allow→block/path_out_of_scope（.policy/approval.json、audit.jsonl、enforcement-ledger.jsonl、.POLICY、./.policy、.policy 等值、orc.fs.edit、orc.fs.write）；其余 9/9 逐条相等（.policyx allow、policies/registry block、Remove-Item/rm -rf command_not_allowlisted、run_code import os code_blocked、git status allow、benign allow_with_warnings） | 符合 | readings/2026-10-21-C3-control-plane-write-guard.md §3 | 控制面之外（.git 等）未封，见 04 5.87 |
| R-C3-04 | 2026-10-21T03:05:00+08:00 | C3 第三件 | 测试与重审 | security 18 / contract guard 13 / contract protocol 14 / unit approvals 44；unit+contract 2417 passed·6 skipped；integration+security 828 passed | 全部 exit 0；registry --verify 10/10 ok exit 0；approval_allowlist_audit --check HITS 0 / drift 0；governance_digest 47fa192d→290b5086、registry_digest 33e330b8→cc8d184d；schema_hash 4/10 变（正是四个写工具） | 符合 | readings/2026-10-21-C3-control-plane-write-guard.md §4–§5 | 受治侧 local registry 未同步 |

### 7.4 阶段 A · 偏离/作废记录

| id | 时间 | 事件 | 命中条件（05 第 5.4 节哪一条 / 构造失败编号） | 影响范围 | 处置 | 证据指针 |
| --- | --- | --- | --- | --- | --- | --- |
| D-20261018-01 | 2026-10-18T09:45:00+08:00 | A2 门原文未覆盖第三态 | 05 §4 A2 门只列「能力边界 / 假阳性」；读数落「真阳性」 | A2 判据按「能定性且带读数」执行；原文保留可证伪记录 | 05 §8 第 5 条（A2 门措辞按三态）；A2 状态不变 | A2 归档报告 §0/§4 |
| D-20261018-02 | 2026-10-18T09:45:00+08:00 | A3 干跑构造不成立 | 构造失败 B-1..B-6：受治臂缺失（当前会话 out_of_scope）、审批 3/3 过期、无 A3 任务包、受治树非基线且部分不可枚举、①装配/口径缺口、②族定义缺口 | 阶段 A 第三项未满足；阶段 D 不开跑 | 改构造不改判据：按最小解冻清单执行；本轮不记通过 | A3 归档报告；04 5.72（R-1 审计目标解析错位） |
| D-20261018-04 | 2026-10-18T10:15:00+08:00 | 本机门禁全量 pytest 在本会话沙箱内跑不成 | 构造失败（环境）：.tmp/tmp/pytest-of-ZNM 与显式 --basetemp 目录均出现 WinError 5 拒绝访问；xdist worker 在脚手架阶段 PermissionError；干净 worktree .tmp/verify-head 同样复现 | 门禁 pytest 步骤 exit 3、phase evidence 退回真跑；22 failures 已取证 21 个 unit errors 全部为 .tmp/tmp/pytest-of-ZNM 的 PermissionError（junit .tmp/artifacts/tests-unit-report.xml），1 个 integration 未逐条取证；构造问题不是代码失败 | 不把跑不成记成通过；改用 -n0 单进程 + 干净 worktree 复跑（结果见 R-A-A1-08）；长期修法：沙箱外运行或用 Windows 文件权限修复（本次未做） | .tmp/ci-local-logs/03-…log；.tmp/verify-head 复现日志 |
| D-20261018-05 | 2026-10-18T11:20:00+08:00 | D-20261018-04 的阻断已解除 | 环境修复：对 .tmp/tmp/pytest-of-ZNM 执行 icacls /reset + takeown（权限，不改文件内容）；删除 121 个陈旧 pytest-cache-files-* | 门禁可全量执行 | 在干净 worktree（HEAD f11e9af）复跑 ci_local：26/26 ok、退出码 0（见 R-A-GATE-01）；同时更正 R-A-A1-07 的证据指针——以 readings/2026-10-18-ci-local-green.md 与本章记录为准，不再引用 .tmp | docs/project/engineering-policy-platform/readings/2026-10-18-ci-local-green.md |
| D-20261018-06 | 2026-10-18T15:00:00+08:00 | A3 解冻包 U1 判据按原文读不到（探针 D1） | 解冻包 §3.5 要求读 in_scope 的 governed 记录里 session_scope/session_cwd/project_root，但这些键只在 scope fallback 记录里出现 | A3 解冻包 §3.5.1 的 U1 判据 | 解冻包 §9 更正为三件证据（governed=true + 会话日志 cwd + 差分探针）；不改变 U3 结论 | readings/2026-10-18-A3-single-action-probe.md §5.5；A3 解冻包 §9 |
| D-20261018-07 | 2026-10-18T21:12:00+08:00 | 受治 dsh 启动被 workspace-write 文件沙箱拒绝（写 $DSH_HOME/profiles/headless/cordis.yml，EPERM） | 环境/构造：profile-boot 的 prepareProfile 每次 boot 无条件写 profile root；本机默认沙箱不许写工作区外 | A3 受治会话启动（一次性授权降级）；读数记 host.sandbox=restricted | 对同一条启动命令做一次性 danger-full-access 授权；受治会话自身 host sandbox 仍 workspace-write、approval/asked=0 | readings/2026-10-18-A3-dryrun.md §3.3/§7；run-01-meta.json |
| D-20261018-08 | 2026-10-18T21:20:00+08:00 | ② 的预注册判据（run-manifest 的 strict wording）与 05/解冻包口径不一致；装配器把 post-check 阻断误判为 host_stage | 判据表述：解冻包 §5.2 = 放行且真进入执行、命令退出码单列；manifest 写成 +post_validated+isError=false | ② 的两个读数（主读数 1/2、严格仪器 0/2） | 主读数按 05/解冻包口径（F1 pass）；严格仪器读数 0/2 同时保留；两者均 <90%，结论不变；装配器升格 tools/ 前必须先修 host_executed（F-4） | readings/2026-10-18-A3-dryrun.md §5.2/§7；run-01-command-families.json |
| D-20261018-09 | 2026-10-18T21:30:00+08:00 | 任务包构造缺陷在干跑中暴露：M1 测试覆盖 A1（需 M3 的服务改动）→ M2 新模块被 TESTING-002 阻断；tools/audit_demo.py 被 TESTING-002 uncovered_checker（critical）+ STYLE-018 阻断 | 构造：milestones 设计与规则交互；非环境 | A3 v1 的 ② 与任务完成（A1–A7 未达） | 记「不符合」；最小修复清单见 readings §6；修构造后重跑 A3，D 不开跑 | readings/2026-10-18-A3-dryrun.md §4/§5.2/§6；M2/M5 审计记录 |
| D-20261018-10 | 2026-10-18T22:10:00+08:00 | A3 v1 读数两处口径更正：熔断窗口与 ② 双读数 | 熔断窗口实际取 breaker_seconds=300s（precheck.py#L559-L566），失败时间戳 13:10:15/13:11:08/13:11:34、13:11:51 开闸，原写「窗口 60s」是误读；② 主读数按冻结口径应为 1/2（F1 执行证据可读即通过），旧严格仪器 0/2 作历史 | 已发布的 A3 v1 读数（R-A-A3-05/08）与 ② 口径 | 已发布读数追加 §12 更正；字段两义登记 04 5.76；② 判据冻结见 05 §5.6 与裁定 A-7 | readings/2026-10-18-A3-dryrun.md §12；readings/2026-10-18-A3-fix-adjudication.md §3 |
| D-20261018-11 | 2026-10-18T22:20:00+08:00 | A3 修复裁定（F-2..F-5、B1、D 两门） | 裁定 A-1..A-12：F-2 保留 F2+预置 demo；F-3 先构造；F-4 修装配器并复算；F-5 授权启动+跑后复核；B1 条件依赖；D 拆校准门/构造门；② 判据冻结 | 05 §5.1/§5.6/§8 第 6 条；04 5.73 状态与新增 5.75/5.76/5.77 | 已按裁定落地；D 校准门待 A3 v2 4/4 后重跑，A/B/C 未开跑 | readings/2026-10-18-A3-fix-adjudication.md §2/§4/§5 |
| D-20261019-01 | 2026-10-19T09:10:00+08:00 | A4 判据「实例化只出现在 composition 文件」与本题接口契约冲突 | 参考树（.tmp/lead-v3/ref）上 A4 fail 2 条，而这两处是 interfaces.md 要求的构造器默认装配（`service or OrderService()` / `repository or OrderRepository()`） | A 维度 10 条里 1 条对所有合法解恒红（区分力 0） | 修订为「业务方法（`__init__` 以外）不得实例化另一模块具象类」；structure_metrics 1.0→1.1；参考树改后 10/10；记录在 memo §9 第 2 条 | tools/structure_metrics.py；dgate2/scorer/README.md §11；memo §9 |
| D-20261019-02 | 2026-10-19T10:20:00+08:00 | C 维度「整棵树 13 个 .py」口径制造测量假象 | 实测：整树口径下 `src/shop/__init__.py` 与 `tools/__init__.py` 各报 1 条 TESTING-001（「有变更但找不到对应测试」，而它们一字节未改）⇒ rules 21/24，任何合法解丢 3 分 | 与 §4.1「参考解 C 30/30」的天花板冲突 | 冻结为**改动面 8 个 .py**（README §3 记录两条候选集的实测对比）；被排除项没有漏判：8 + README（非 .py）+ 7 冻结核 = 16 | dgate2/scorer/scorer.yaml measurement.file_set；README §3/§10 |
| D-20261019-03 | 2026-10-19T10:25:00+08:00 | 评分器 config-root 草案要求自带副本 | 草案 §4.0 写 `scorer/config-root/validation/`，落地时 treatment 已建 `dgate2/configs/after/` | 会多出第三份要维护、要钉哈希的配置副本 | 改为引用 `configs/after` 并在 scorer/manifest.sha256 里钉住逐文件哈希；记录在 memo §9 第 1 条 | memo §9；dgate2/scorer/manifest.sha256 |
| D-20261019-04 | 2026-10-19T21:44:00+08:00 | 派发文本的两处口径与实测不符：① activation 用 9 条 `--changed` 测不出翻面；② hidden runner 在 `workspace-write`（partial）沙箱下 30/40 | ① 口径：v3 README §3 与 memo §2.3.5 都用单路径 `--changed tools/audit_demo.py`；9 条形态两臂都 allow；② 环境：`tempfile.mkdtemp(0700)` 在旧沙箱下不可写（WinError 5） | 不影响判据；影响「activation 怎么记录」与「T 读数在哪个沙箱取得」 | 登记 04 5.81；读数按实测形态记录（单路径 activation；launcher/session 两种沙箱分别记） | readings/2026-10-19-D-gate2-run-ready-verify.md §1.4/§3；readings/2026-10-19-D-gate2-run-record.md §6/§10 |
| D-20261020-01 | 2026-10-20T07:36:00+08:00 | A 臂首跑作废：装配用了仓库 `registry/tool-registry.yaml`，缺 `governed-dev` 角色 → 每个写/执行动作 Phase 4 `permission_denied` | 构造失败（装配错误，非平台缺陷）；首跑 182.4 s、19 条 `permission_denied`、无有效治理判定 | 首跑读数不进计分；不影响 B/C | 换 tracked `examples/dsh/b-plan/tool-registry.local.yaml` + 已审核对（`registry --verify` exit 0）；清审计/`pre-evidence` 后重跑 A；『装配必须用带 governed-dev 的本地注册表』写进 runs README | `.tmp/dgate2-arms/logs/A-invalid-run/`（现场）；readings/2026-10-20-D-gate2-ab-c-runs.md §2 |
| D-20261020-02 | 2026-10-20T19:50:00+08:00 | 受治会话被自己的 Hook 锁死 | 构造/执行：approvals.py 漏 from dataclasses import dataclass；该文件在 Hook 导入链上（hooks.py:82 → adapters.dsh.enforcement → enforcement.approvals） | Hook 启动即 NameError → 宿主按「未知状态=失败关闭」拒绝全部工具调用（含 read/run_code）；两条子会话与 Lead 停摆约 15 分钟 | 使用者手工补 import 恢复；新增纪律：改 Hook 导入链模块后每次写入立刻跑 import 自检（04 5.85） | readings/2026-10-20-B1-param-domain.md §9 尾部；04 5.85 |

### 7.5 阶段 B · 进度记录

| id | 时间 | 阶段/任务 | 执行者 | 起点锁 | 做了什么 | 结果 | 证据指针 | 判据 | 偏差 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P-B2-000 | 2026-10-18T16:20:00+08:00 | B2（解冻授权） | 使用者（授权） | HEAD ec63759；approval-pwsh-a3 sha256 9abd73a3… | 使用者显式解冻 B2（仅 B2）；A3 审批条子已签 | 符合 | 06 §7.1 P-A3-005；docs/project/engineering-policy-platform/testing/ab/2026-10-18-A3-handoff.md §1 | 05 §2.3 冻结令 + §4 B2 | 无 | 无 |
| P-B2-001 | 2026-10-18T19:40:00+08:00 | B2 | b2-test-support（子会话） | HEAD d4b0a4f（BEFORE）→ a441877（AFTER，其间两份 A3 文档提交）；rule_set_hash 未变 | test-layout v2 + selection level=support + resolve_layer support→test + PIPELINE 1.4；conftest-alone 显式翻面；5 类反例；R-d 与真实 Hook 读数 | 符合 | docs/project/engineering-policy-platform/readings/2026-10-18-B2-rd.md；git show --stat 47fa325；pytest 259 passed；真实 Hook exit 0（新 event id 复跑结果一致） | 05 §4 B2 门 + §3.5 R-d | examples/dsh/dsh-adapter.yaml 超出预约写区（同层守卫必要，已由 contract 用例钉住） | C1 集合差是否纳入 support 需单列裁定 |
| P-B1-001 | 2026-10-20T20:05:00+08:00 | B1 | b1-approval（子会话）+ Lead 复核 | HEAD 30d10ae；APPROVAL_SCHEMA_VERSION 1.2→1.3、REGISTRY_SCHEMA_VERSION 1.0→1.1、APPROVAL_AUDIT_SCHEMA_VERSION 1.0→1.1 | 参数域（默认值补齐两侧）+ 族数据 + approve --family + audit --check + 用例 + registry 重审 | 符合 | readings/2026-10-20-B1-param-domain.md；pytest 89/191/88；registry --verify exit 0；audit --check 0 hits；4 份决策夹具 sha256 相同 | 05 §4 B1 + §3.2 | 真实受治会话 9/9 待条子；04 5.83 四条残留 | B3 开跑（依赖本提交后） |
| P-B3-001 | 2026-10-20T22:10:00+08:00 | B3 | b3-readguard（子会话）+ Lead 复核 | HEAD 515e271；REGISTRY_SCHEMA_VERSION 1.1→1.2、ENFORCEMENT_SCHEMA_VERSION 1.0→1.1（ReasonCode 加值 read_guard_blocked） | read_guard 数据 + 结构化路径操作数检查 + 新原因码 + 42/11 用例 + 18 条前后矩阵 + 重审 + 读数 | 符合 | readings/2026-10-20-B3-read-guard.md；pytest 42/11/2407/810 全 exit 0；registry --verify exit 0；audit --check 0 hits | 05 §4 B3 + 04 5.70 | 400 份真实会话回放未取得（§6）；受治侧 local registry 未同步；六条残余见 04 5.86 | 受治侧同步 + 重审；调换检查顺序若裁定则单开一次 |


### 7.5.1 阶段 C · 进度记录（2026-10-20）

| id | 时间 | 阶段/任务 | 执行者 | 起点锁 | 做了什么 | 结果 | 证据指针 | 判据 | 偏差 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P-C3-001 | 2026-10-20T20:10:00+08:00 | C3（v1） | c3-tree-gate（子会话）+ Lead 复核 | HEAD 30d10ae；FINAL_TREE_GATE_SCHEMA_VERSION / PIN_SCHEMA_VERSION 各 1.0 首次建轴 | 新工具 tools/final_tree_gate.py（整树判定 + RuleSet.identity 钉住；退出码 0/1/2）+ 9 条用例 + 夹具 | 符合（v1 范围） | readings/2026-10-20-C3-final-tree-gate.md；pytest tests/unit/test_final_tree_gate.py -n0 → 9 passed exit 0 | 05 §4 C3（前两件） | v1 不含危险动作前置阻断（04 5.84）；整树 43 条耗时未测 | 前置阻断单开一轮；整树读数在接 ci_local 前补 |
| P-C3-002 | 2026-10-21T03:10:00+08:00 | C3 第三件（v1） | c3-control-plane（子会话）+ Lead 复核 | HEAD 34c5069；REGISTRY_SCHEMA_VERSION 1.2→1.3 | 控制面 `.policy` 写面阻断（四个写类工具 blocked_prefixes）+ 三路径验证套件（写/删除/执行）+ 17 条前后矩阵 + 重审 | 符合（v1 范围） | readings/2026-10-21-C3-control-plane-write-guard.md；pytest security 18 / guard 13 / protocol 14 / approvals 44 / unit+contract 2417 / integration+security 828，全 exit 0；registry --verify exit 0 | 05 §4 C3 第三件 | 控制面之外的写面未封（04 5.87）；受治侧副本未同步；symlink 不解析 | 单开一次控制面写面裁定 |

### 7.6 阶段 D · 记录（校准门 2026-10-18 + 门 2 前置 2026-10-19）

| id | 时间 | 阶段/任务 | 执行者 | 起点锁 | 做了什么 | 结果 | 证据指针 | 判据 | 偏差 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P-D-001 | 2026-10-18T23:18:00+08:00 | D（校准门） | Lead | HEAD 98169bf；无模型/无审批；树 = 12 文件 v2 基线 + 同一受治配置 | 真 Hook CLI 喂 P+ / P− / canary：P+ controller 直接 import repository → block（ARCH-001@1 等）；P− repository docstring → allow；canary write tools/audit_demo.py → block（TESTING-002@1，04 5.75 缺口仍在） | 符合（校准门通过；A/B/C 未开跑） | readings/2026-10-18-A3-dryrun-v2.md §5；.tmp/a3b2/d-calibration.json | 05 §5.1 门（通过 = P+ 被拦且 P− 放行；裁定 A-9）+ 裁定 A-6 | 无（校准即记录）；canary 是登记缺口的常红项，不是 D 失败 | 待 treatment 裁定 + 评分器冻结 + C 臂装配后开 A/B/C（04 5.78） |
| P-D-002 | 2026-10-19T11:30:00+08:00 | D（门 2 前置包） | Lead（多个子会话交付） | HEAD be63670；冻结输入 = 任务包 v3 + configs/after + scorer + hidden + tools 两份 | treatment（e341c08）、任务包 v3（6f88e59）、隐藏验收 30 条 + runner（6f22cee）、A 维度工具（2a2cb21）、评分器骨架 + 冻结（c4d77e3/be63670，组合摘要 e3ef9e91…）、C 臂装配 + n=1 冒烟（99fd894）；每件都有变异/能红证明与读数 | 符合（前置包就绪；A/B/C 未开跑） | 06 R-A-D2-01..05；dgate2/{scorer,hidden,c-arm}/README.md | 05 §4 D 行 + memo §8 | D-20261019-01..03（三处口径修订） | 开跑前：`make_manifest.py --check --strict` + 17 个 run-manifest 字段 + 使用者确认 |
| P-D-003 | 2026-10-19T21:40:00+08:00 | D（run-manifest 工具，task-1） | run-manifest（子会话） | HEAD c44f9db；冻结包组合摘要 e3ef9e91…；RUN_MANIFEST_SCHEMA_VERSION 首次建轴 1.0 | 新增 17 字段生成/校验器 + README + 13 用例；字段 id 与 scorer.yaml 逐字一致，三态 + 冻结类摘要现场重算 | 符合 | docs/project/engineering-policy-platform/testing/ab/dgate2/run-manifest/{run_manifest.py,README.md}；tests/unit/test_dgate2_run_manifest.py（13 passed，6.10s）；--arm A → exit 0（recorded 10/pending 7）、--check → 0、--check --strict → 1（human_items_unrecorded + incomplete_freeze）；make_manifest --check --strict → 0 | 04 5.78 ②；scorer.yaml run_manifest_fields | 工作树脏使 worktree_clean=false（如实记录；正式清单应在干净 HEAD 生成） | 使用者确认后按臂生成正式清单 |
| P-D-004 | 2026-10-19T21:42:00+08:00 | D（run-record 采集器，task-3） | run-record（子会话）+ Lead 原生复跑 | HEAD c44f9db；RUN_RECORD_SCHEMA_VERSION 首次建轴 1.0 | 新增 T/C/A 三维读数采集器 + README + 10 用例（可注入 runner）；参考树真跑样例 | 符合 | docs/project/engineering-policy-platform/testing/ab/dgate2/run-record/{collect.py,README.md}；tests/unit/test_dgate2_run_record.py（10 passed，0.78s）；样例 collect exit 0（T 40/40、C 24/24、A 10/10；载荷 sha256 40f55c46…，三次逐字节相同）；Lead 在 danger-full-access 无垫片复跑同值 | 04 5.78 ②；scorer.yaml measurement | 子会话在 workspace-write 下 T 无垫片 30/40（换垫片 40/40）；原生复跑 40/40（R-A-D2-07、04 5.81②） | 无 |
| P-D-005 | 2026-10-19T21:44:00+08:00 | D（冻结包复核与评分链干跑，task-2） | chain-verify（子会话）+ Lead 复核 | HEAD c44f9db；冻结包 25 文件；任务包 v3 5/5 | 只读复核六组：冻结清单、任务包、两臂配置、参考树 A/C/T、M5b activation、判据哈希 | 符合（T 的旧沙箱形态另记） | readings/2026-10-19-D-gate2-run-ready-verify.md（302 行，sha256 e838539e…）；make_manifest --check --strict → 0；A 10/10 ×2、C 24/24 ×2、T 40/40 ×2（danger-full-access）；M5b 单路径 before block / after allow | 04 5.78 ①②；05 §5.6 | activation 只在单路径 --changed 复现（9 条形态两臂都 allow）；T 在旧 workspace-write 下 30/40——均登记 04 5.81 | 无 |
| P-D-006 | 2026-10-20T07:52:00+08:00 | D（A/B/C 各一次 run） | Lead | HEAD 889c97c；基线 4e7c4073…；dsh 0.2.1-alpha.2；条子 d53f0d99… / 346f35c2… | A/B 受治（configs/before vs after）+ C 不治理各跑一次真实 headless 会话；三臂同一首消息 123c938c… | 符合（run 完成）；A 首跑作废（构造失败，见 D-20261020-01） | readings/2026-10-20-D-gate2-ab-c-runs.md；testing/ab/dgate2/runs/2026-10-20/{A,B,C}/run-manifest.json | 05 §5.1 + memo §4；04 5.78 | A 首跑 permission_denied（registry 缺 governed-dev），换 tracked b-plan local registry 后重跑；任务包 v3 明写预期红 pytest（两臂各 2–3 次 post_repair_required） | H2/H3 人工项与会话日志复核 |

### 7.7 汇总与复审（2026-10-18）

| 项 | 当前状态 | 门 / 证据 | 下一步 |
| --- | --- | --- | --- |
| 阶段 A | A1、A2 已落地；A3 v2 4/4 + 任务完成（A1–A7，隐藏验收 6/6、pytest 10 passed、A8 7/7） | 05 §4 A3、§5.6；readings/2026-10-18-A3-dryrun-v2.md；06 P-A3-011/012、R-A-A3-09..11 | A3 不再重跑；构造若再改必须重新冻结 run-manifest |
| 阶段 B | **B1/B2/B3 均已落地**：B2 47fa325、B1 fe292b9、B3 9a88112 | readings/2026-10-18-B2-rd.md、readings/2026-10-20-B1-param-domain.md、readings/2026-10-20-B3-read-guard.md；05 §4 B | 受治侧同步 read_guard 并重审；B1/B3 残余见 04 5.83/5.86；B1 不再是 treatment 候选（05 §8 第 7 条已裁定） |
| 阶段 C | **C3 v1 + 第三件 v1 已落地**（整树判定 + 规则集哈希钉住；控制面 `.policy` 写面阻断）；C1/C2/C4 裁定草案 2026-10-21 已出（待使用者确认）；控制面之外的写面未封（04 5.87） | readings/2026-10-20-C3-final-tree-gate.md、readings/2026-10-21-C3-control-plane-write-guard.md、readings/2026-10-21-C1C2C4-adjudication-draft.md；05 §4 C；04 5.84/5.87 | 控制面写面裁定（5.87）；按确认结果启动 C1-a 或 C4 验证探针 |
| 阶段 D | 校准门通过；门 2 前置包冻结；**A/B/C 已于 2026-10-20 各跑一次（n=1）**：A 任务未完成（T 30/40、A 6/10、C 规则 24/24 仅 7/8 文件、block 1、circuit_open 1），B 任务完成（T 40/40、C 29/30、A 27/30），C 任务完成（T 40/40、C 30/30、A 30/30）；**H2/H3 已复核**，三份 run-manifest 均 **16 recorded / 0 pending / 1 n/a，`--strict` PASS** | readings/2026-10-20-D-gate2-ab-c-runs.md；H2/H3 复核记录；testing/ab/dgate2/runs/2026-10-20/**；06 R-A-D2-09/10/11 | 要写「值得扩试」需每臂 k≥3 次同题 run（05 §5.5）；n=1 当前只作案例 |
| 本机门禁 | **26/26、退出码 0**（三次：HEAD 515e271 4m00.9s、47afddd 5m34.2s、93f0285 5m22.8s；26 正常 + 4 只报告；**必须 danger-full-access**） | 06 R-A-GATE-07/08/09 | 产品代码改动后重跑；同一工作树同时只跑一个 |
| 未修缺口 | 04 5.76（breaker_seconds 两义）、5.77（A3 测量仪器升格触发）、5.79（评分器已知边界，10-20 实测补两条）、5.80（AGENTS 指令预算）、5.81（开跑执行事实）、5.82（首轮 run 构造事实）、**5.83（B1 四处残留）、5.84（C3 整树读数）、5.85（Hook 导入链自检纪律）、5.86（B3 六条残余）、5.87（控制面写面只补了 .policy）**；5.75 已修（e341c08） | 04-open-work | 按 04 排期；5.75 的回退面见 readings/2026-10-19-treatment-tools-pattern.md |

**一句话**：阶段 A 退出条件已满足、D 校准门通过、门 2 前置包冻结；**A/B/C 已于 2026-10-20 各跑一次（n=1）**：现状治理的 A 臂任务未完成（M5b 被 TESTING-002 uncovered_checker 拦住，无 demo，第三次 post 失败触发熔断），treatment 的 B 臂完成（T 40/40、C 29/30、A 27/30），不治理的 C 臂完成（T 40/40、C 30/30、A 30/30）；H2/H3 已复核并记录（抽样人/复核人记使用者，Lead 子会话代执行），三份 run-manifest **16 recorded / 1 not_applicable、`--strict` PASS**。本页不写均值/提升/显著，也不把 n=1 当治理价值结论（05 §5.5）。**2026-10-20 增补**：B1（审批 1.3 参数域）、C3 v1（最终树门禁）、B3（只读族 read_guard）同日落地；B3 的「400 份真实会话回放」**未取得**，不写成 0 误伤（04 5.86）。**2026-10-21 增补**：C1/C2/C4 裁定草案已出（readings/2026-10-21-C1C2C4-adjudication-draft.md）；C3 第三件 v1 落地（8e6a3cb）——`.policy` 写入从 8/8 allow 变成 8/8 block，其余 9 条逐条相等；但 `.git/hooks`、CI、语料等治理面仍可被写类工具改写（04 5.87，待裁定）。**2026-10-20 增补**：B1（审批 1.3 参数域）与 C3 v1（最终树门禁）已落地，04 5.83–5.85 登记残留与纪律；同日一次自伤事故（approvals.py 漏一行 import 锁死受治会话）换来 5.85 的 import 自检纪律。

# R2 对抗式评审（红队）——对 r1-modules / r1-flows / r1-layouts

> 评审人：red-team（task-9）。方式：**先自己跑，再读提案**；攻击优先，不复述对方结论。
> 评审对象：r1-modules.md 264 行（task-1）、r1-flows.md 309 行（task-2）、r1-layouts.md 449 行（task-3）。
> 编号沿用 r0-facts.md 的 F/N 与我 R1 的 X/C/A/V 编号，不另造口径。
> 判定尺度：**成立** = 我复现或读码核对无误；**收窄** = 事实对、表述过强；**不成立** = 与我的复现冲突。

## 0. 先立标尺：我亲自复跑的数字（2026-09-22 20:48–20:52，+08:00）

| # | 命令 | 我的实测 | 与三份提案的关系 |
| --- | --- | --- | --- |
| R1 | python -m policy.check --check-rules | **44 条 / sha256:a90e64ac2d5c…**、exit 0；policies/ 下 44 个 yaml | modules E1 说 26；flows 说 44；layouts V20/§4 说 45、§4 又写 fixture-shop 46 |
| R2 | 同上 + --rules policies --rules tests/fixtures/api/rules（fixture-shop 的规则目录，api/policy-api.yaml:73-75） | **45 条 / sha256:eea3f175c45b…** | 复现不出 46；"45"恰好等于**今天 fixture-shop** 的数 |
| R3 | python -m retrieval.cli rules --rule DOC-001 | **exit 0**，输出 2 条溯源：DOC-001@1 <- pep-257-docstrings/index.md#…（chunk_84fdd27ea9059e883e2ed606 等） | **flows 第 9 条卡点与 C 台阶 7、layouts V11/§4 第 13 行全部作废** |
| R4 | python -m retrieval.cli rules --rule ARCH-001 | exit 1，"没有登记的来源溯源" | modules Q8 引的这条**仍然成立**（项目自订规则无溯源） |
| R5 | python tools/ci_local.py --list | 35 条步骤行；"本机跳过（CI 上仍然执行）"段 **8 条** | modules E16"27 + 8"**成立**；flows H5/附"另 1 步 Windows 跳过"**不成立** |
| R6 | src/enforcement/precheck.py 的 _check("…") 名 | **14** 个名字，但 ledger_claim 只在 :534 的 not dry_run 下追加 → dry-run 实测 **13** 项 | modules §5-S3"实测共 14 个"**不成立**；flows E1"13 项"**成立** |
| R7 | tests/fixtures/rules/** 与 docs/project/architecture/规则转化覆盖报告.md | **79 个夹具文件**（每规则 bad.py + good.py）、覆盖报告存在、knowledge/corpus.yaml:158 起 rule_sources 有内容 | 见 §7-3：这改变了我 R1 对"38 次写入"的定性 |
| R8 | console 下 aria-/tabindex/noscript/<form 计数（html + js） | **0 / 0** | layouts V23 **成立** |
| R9 | index.html:19 / :23 | KPI 写 <b>6</b>规则；哈希写 sha256:ed331a8df353…（真值来自 assets/data.js:5778，由 build_site.py 生成） | layouts V22 事实**成立**、修法**需收窄**（L-A2） |
| R10 | src/policy/check.py:77-92 | KNOWN_LAYERS = 12 值 + UNKNOWN_LAYER="unknown" | layouts V19 **成立** |
| R11 | src/policy_api/app.py:295-320 | live() / ready() 是直连 handler、无认证依赖；ready 非就绪返回 503 | layouts V2/V3 **成立** |
| R12 | policies/ 全量 mtime + git status --porcelain policies | 6 份受跟踪 + **38 份未跟踪**，最早 20:35:07、最晚 20:41:24 | 见 §5-1、§7-3 |

---

## 1. 对 r1-modules.md 的攻击

### M-A1（不成立）把"源码里有 14 个检查项名"写成"实测共 14 个"

- **攻击步骤**：读 §5-S3"实测检查项名共 14 个"，据此给界面写"14 项检查"的验收断言。
- **证据**：ledger_claim 只在 src/enforcement/precheck.py:544 / :566 出现，外层条件在 :534 的 not dry_run；precheck 子命令走 dry_run=True（src/enforcement/cli.py:460）。dry-run 实测输出恰好 **13** 项（我 R1 A2 探针原文）。
- **裁定**：**不成立**（读码冒充实测）。flows 的"13 项"才对。

### M-A2（收窄）发现了 F13 漂移，但没有把"三份提案各报一个数"这件事一并解决

- **攻击步骤**：读 §0-4 与 Q1，接受"F13 说 6、实测 26，请 Lead 裁定哪个算当前规则集"。
- **证据**：modules 的观察**方向正确**（R1/R7：工作树确实不是 6 份）。但本文之后，flows 报 44、layouts 报 45（且 §4 写 fixture-shop 46），**没有任何一份回改 F13**，也没有定义"引用规则集事实时必须带取数时刻与命令"。
- **裁定**：**收窄**——Q1 问对了，但它把问题留在"文档口径"，而实际后果落在下游：三个不同的数会被同一份总设计引用。

### M-A3（收窄）§1 表把"rules: 26"当板块事实写进单元格，没有取数时刻

- **攻击步骤**：把 §1 表 S1 行抄进总设计。
- **证据**：同表"读表口径②"要求用【实测】标注，但 26 在本文落地时已是 44（R1）。单元格读者拿不到时刻，会把它当常量——这正是 layouts V20/V22 花整节防的事。
- **裁定**：**收窄**：命令写对了，单元格必须补时刻。

### M-A4（收窄）S9 的"唯一入口"是一个浏览器到不了的静态文件

- **攻击步骤**：按 §1 表找 S9 入口 → designs/console/index.html。
- **证据**：同表口径①写明"唯一入口只写今天真实存在的入口"；而 layouts V4 实测 GET / → 404 not_found（F26/N1/N3）。
- **裁定**：应写成"今天无 HTTP 入口（需 file:// 或本地 http.server）"。

### M-A5（严重／修法不完整）第 0 步的 B1 修法只落在编排层分支

- **攻击步骤**：照 §6"第 0 步修 B1"——把 nodes.py:94-97 的 tool_id 选择改成按路径判定。
- **证据**：我 R1 A3 用真实注册表实测（**仅 precheck、dry_run=True、未执行写入**）：orc.fs.write 在**真实仓库根**工作区下对 policies/coding/RT-999.yaml、registry/tool-registry.yaml、registry/tool-registry.approved.json、adapters/approved.json、api/policy-api.yaml 的 pre-check **全部 exit 0**。
- **后果**：只改 nodes.py，任何别的调用方仍可无审批改写**信任根数据**（F15/F17）。修法必须落在**注册表数据**（file_path 的 pattern / 拒绝清单），编排层分支只是第二道。

---

## 2. 对 r1-flows.md 的攻击

### F-A1（不成立）"另 1 步在 Windows 跳过"与实测差 7 步

- **证据**：R5——"本机跳过（CI 上仍然执行）"段列出 **8** 条：AST evidence replay / Example replay / Scope skip reason / Validator registry is loadable / Validator registry declares what is implemented / Validators fail closed when a checker has no evidence / Syntax errors fail closed / Policy API ASGI contract。
- **后果**：H5 的表述会让读者以为本机门禁≈CI 覆盖。modules E16 的"27 + 8"是对的。

### F-A2（严重／已过时）第 9 条卡点与 C 台阶 7 依赖的"溯源为空"今天已不成立

- **攻击步骤**：按 C 台阶 7 与第 9 条卡点设计界面"溯源显示未登记"。
- **证据**：R3/R4——DOC-001 现在**退出 0** 并返回 2 条 chunk 级溯源；只有 ARCH-001（项目自订规则）仍退出 1。knowledge/corpus.yaml:158 起的 rule_sources 已有内容；AGENTS.md 约束 40 已把 chunk 级溯源写成硬要求。
- **后果**：flows 的"实测 exit 1"在**它自己的实测时刻**是真的，但它被写成流程事实后立刻过期；界面若照此把 DOC-001 渲染成"未登记"，就是**说假话**（C9 的同类错误）。
- **裁定**：**不成立（现已过时）**，必须改为"按规则类型分叉：standard 规则应有溯源，project-policy 规则今天没有"。

### F-A3（收窄／没推到底）E 节 policy skipped 的结论只走了一半

- **攻击步骤**：读 E 节 ⚠️"谁忘了带上下文，谁就少了一道门"，当成提醒。
- **证据**：该检查项判据是**调用方自带的 policy_context**（我 R1 实测 detail 原文："请求没有声明 policy_context：该动作没有文件维度，Phase 1 规则引擎不适用（显式跳过）"）；而 AGENTS.md 约束 14 要求 action_hash 覆盖"**上下文摘要**"。
- **后果**：删掉 context 同时削弱门禁**与**绑定。补法：受治理写类动作缺 policy_context 应为 FAILED，不是 SKIPPED。
- **加分**：这条是 flows **独立发现**、我 R1 没发现的，我承认。

### F-A4（收窄）H5 把"未回读结论的步骤"写进已跑清单

- **证据**：H4 自己写 phase_evidence.py"20:45 仍在运行"，即该步退出码未回读；而"阶段证据"正是那 27 步之一。
- **裁定**：改为"含 X（其本次结论未回读）"。flows 的"本轮未完，待补"一节已诚实登记。

### F-A5（收窄）可复现命令清单没有标"哪些命令改写了持久状态"

- **证据**：附录 40 行里既有只读命令（registry --verify / openapi --check / matrix），也有**改写**命令（enforcement.cli execute 写审计与台账、approve 写 approval.json、retrieval.cli index --db 建库、seal --out 写锚、cleanup 删文件），混排无标记。
- **后果**：读者以为"跑一遍即可复现"，实际会累积副作用与新的台账记录。补法：每条加"只读 / 写"标签与落点。

---

## 3. 对 r1-layouts.md 的攻击

### L-A1（不成立）V20 与 §4 的规则集数字不可复现，疑似把两个租户弄反

- **证据**：R12/R1/R2——policies/ 下**最多存在过 44 个 yaml**，最后写入 20:41:24；20:48 实测 policies = **44 / a90e64ac**，policies + tests/fixtures/api/rules = **45 / eea3f175**。我复现不出任何"45 个文件"或"46 条规则"的时刻；V20 的 sha256:dc4e96ac… 也复现不出来。
- **补充**：fixture-shop 比 local-dev 多一个规则目录（api/policy-api.yaml:73-75），所以"多一条"的方向对，绝对值各差 1。
- **裁定**：**不成立**（数值）。请把 V20/§4 也按它自己 §9-1 立的规矩重写（数值 + 取数时刻 + 命令）。

### L-A2（事实对／修法错）把"构建期快照"诊断成"生成器写死静态值"

- **证据**：R9——index.html:23 的哈希与 assets/data.js:5778 同值，是 build_site.py:162-164 调 policy.loader.load_rule_set **真读**后写出的；KPI 的 <b>6</b>（index.html:19）同样来自那次生成。
- **后果**：照 §9-1 字面"禁止由静态生成器写死"，生成器就无法输出任何哈希。正确约束是"页面上的哈希/计数必须带取数时刻，且必须由运行时请求获取，或明确标注为构建期快照"。

### L-A3（自相矛盾）U1 与 U2/§8② 不可能同时成立

- **证据**：U1 要求"不渲染不存在的按钮（不是禁用）"；U2 要求"灰按钮 = 今天没有对应路由，且必须带 ? 说明"；§3 的 P8 线框写满 [灰]加入候选 / [灰]保存草稿 / [灰]预演 / [灰]提交审批；§8② 又要求改成 aria-disabled="true" 的**可聚焦**按钮。
- **裁定**：**以 U2/§8② 为准**（"缺口 + 替代命令"是本设计唯一能传达 N1/N2/N4 的通道），把 U1 改写成"不渲染**会让人以为可提交**的按钮；渲染出的控件必须读出缺口、替代命令与禁用原因"。

### L-A4（不一致）对两个同等不可达的错误码给了不对称待遇

- **证据**：V24 自己说 capability_unavailable 不在 6 条路由的抛出点里；我 R1 读码确认 evidence_unavailable 同样只由 Phase 6 runtime 与编排侧产出。两者在今天的 6 条路由上**同等不可达**。
- **裁定**：§7 给前者配完整分支、给后者写"无文案"，不对等且无依据。要么都按 U6 原样显示，要么都给同等分支并标注来源层。

### L-A5（收窄）§8② 与 §4 首屏纪律冲突：替代命令被锁进悬停

- **证据**：§4 要求第 9–18 行"不可用 + ? 悬停给替代命令"；§8② 又要求把灰按钮改成可聚焦控件，而 §8① 把 ? 也改成 button + aria-describedby——解释位仍是不可见内容。
- **后果**：若替代命令只存在于悬停/描述，键盘与读屏用户只拿到"不可用"，拿不到"改用什么命令"。
- **裁定**：替代命令属于缺口/失败语义，**必须进正文**；? 只保留"为什么不能在前端补"。

### L-A6（引用不可核）"页面共 8 个（在 7–10 区间内）"

- **证据**：r0-facts.md 与 AGENTS.md 中都没有"页面数量 7–10"这条约束。
- **裁定**：读者无法核验，应标来源或写【未知，需核验】。

### L-A7（过时）V11 与 §4 第 13 行把 rule_sources 说成 0 条

- **证据**：R3——DOC-001 今天 exit 0、有 2 条溯源；只有 ARCH-001 仍 exit 1。
- **裁定**：与 F-A2 同源。P4 的"溯源"格必须按规则类型分叉，否则第一个打开的规则就会显示假结论。

---

## 4. C1–C15 逐条对照：三份提案里违反它的**具体设计**

| 宪法条 | 判定 | 违反它的具体页面 / 流程 / 表项 |
| --- | --- | --- |
| C1 判定唯一 | **未违反** | 三份都无本地决策计算；layouts U4 与 §8"无 JS 不渲染结论色"是正面执行。 |
| C2 状态前进只能由后端驱动 | **违反** | layouts P1"sha256:dc4e96ac… / 45 条 / 20:36:58"、P5 加载门禁"45 份全通过 / 原子"、§4 第 7 行"allow / 0 / 1 / 44"——把一次性取数与构建期快照当常驻结论（违反它自己的 U8）。 |
| C3 改判定依据必须审批 | **部分违反（口径）** | 38 份新规则是**并行工作流的合法产物**（R7：79 个夹具、覆盖报告、corpus 溯源、AGENTS.md 已登记 44 条）——它们走的是"台阶 5 写 YAML"的既定路径，不是越权。但三份都没有回答"**这条合法路径怎么被 OS 看见与追责**"，也没有一份回改 F13。 |
| C4 审批绑 action_hash | **未违反** | layouts §2.2 抽屉无编辑控件、P8 只展示 action_hash；flows §10-6 在追口径。 |
| C5 失败关闭不被软化 | **未违反** | layouts §7 全表、flows G 节、modules §5 失败码都正确。 |
| C6 skipped ≠ 通过 | **部分违反** | 三份的语义都对；但**都没写**"API 面必须显式带 include_evidence=true"才拿得到 reasons（runtime.py:572-573）。按缺省请求，界面只能显示计数。 |
| C7 capability_unavailable 是拒绝 | **违反** | layouts §7 把它定为**中性灰**（"没有结论"色），而它是明确拒绝；modules §5-S2 把它列进 REASON_CODES 枚举，读者会当成"路由会返回它"。 |
| C8 信任根数据不得无审批写入 | **三份共同漏项** | modules E7 只记录 approval: none 的事实、未推风险半径；flows 未覆盖；layouts V13 只列 orc.policy.edit。 |
| C9 未核对 ≠ 无漂移 / 过时不得当现状 | **违反（新形态）** | flows 第 9 条 + C 台阶 7、layouts V11 + §4 第 13 行把"溯源为空"写成现状——实测今天已非空（R3）。这是 C9 的同族错误：**把过期快照当现状展示**。 |
| C10 摘要链非防篡改 | **未违反** | modules §2 M8 行、flows §0.8、layouts P5 三处都写了。 |
| C11 不可信文本永不作为 HTML | **三份共同漏项** | 三份定义了版式、颜色、表格、抽屉、窄屏，**没有一条**渲染转义约束；而镜像正文经 hits[].text 原样返回 <script>（评审 B5、我 R1 C11）。P0 只读页就会踩到。 |
| C12 未知一律报错、不留兜底默认值 | **部分违反** | layouts U5/U6 是唯一明确执行的；modules/flows 都没提 build_site.py:216 的硬编码 checker 兜底。 |
| C13 临时产物只在 .tmp/ | **未违反** | flows 全程 .tmp/r1-flows/；layouts P8 明确草稿不进 policies/。 |
| C14 证据只由服务端产出 | **未违反** | layouts §2.2、flows B4。 |
| C15 数值型事实必须可核 | **三份共同违反** | 26 / 44 / 45 / 46 / dc4e96ac 全部无取数时刻与产生命令（L-A1、M-A3）。 |

---

## 5. 三份提案互相矛盾处与裁决建议

| # | 矛盾 | 谁对 | 裁决依据 |
| --- | --- | --- | --- |
| 1 | 规则集条数：modules 26 / flows 44 / layouts 45（§4 又 46） | **都不完整** | 以"带取数时刻的实测"为准：20:48 → policies **44 / a90e64ac**；policies + fixtures **45 / eea3f175**。三份都要改成"数值 + 时刻 + 命令"。 |
| 2 | 溯源是否为空：flows 第 9 条 + layouts V11 说空；modules Q8 只引 ARCH-001 | **modules 的引法最准确** | R3/R4：DOC-001 已 exit 0，ARCH-001 仍 exit 1。必须按规则类型分叉。 |
| 3 | Windows 跳过的门禁步数：modules 8 / flows 1 | **modules 对** | R5 实测 8 条。 |
| 4 | precheck 检查项数：modules 14 / flows 13 | **flows 对** | R6：ledger_claim 需 not dry_run。 |
| 5 | B1 修法落点：modules 给两选项（含改 nodes.py）／flows 问"选哪条"／layouts 只写"显示未核对" | **必须选注册表数据侧** | M-A5 实测：orc.fs.write 对 registry/、adapters/approved.json、api/policy-api.yaml 的 pre-check 全部 exit 0。 |
| 6 | 操作台地位：modules 列第 9 板块并给"唯一入口"／layouts 拆 8 页整页提案 | **layouts 更安全** | modules 自己的 Q4 也在问；layouts 保留了"今天无路由/整页提案"的可见性（M-A4）。 |

---

## 6. 我在 R1 指出、但三份提案仍沿用旧口径的地方

1. **capability_unavailable 的可达性**（我 R1 A10/C7）：layouts V24 承认不可达，§7 却给它配**中性灰**分支——把"拒绝"读成"没有结论"；modules §5-S2 把它列进枚举清单，隐含"会返回"。
2. **门禁绿 ≠ 规则集未变**（我 R1 C9/C2 的推论，本轮被现实验证）：三份都把 policy.check --check-rules 的 exit 0 当正向健康信号（modules §1-S1、flows A3、layouts P5"45 份全通过"）。**实测反例就在工作树里**：门禁全程 exit 0，而 policies/ 从 6 份变成 44 份、RuleSet.identity 至少变过 3 个值。门禁绿只说明"**当前这批能加载**"，不说明"**还是原来那批**"。
3. **裸计数**（我 R1 C15）：26 / 44 / 45 被写进表格当事实；layouts 自己立了规矩却没用在自己的 V20/§4 上。
4. **orc.fs.write 的风险半径**（我 R1 A3）：三份都停在"新建规则文件"这一个动作；实测它是"**真实仓库根上的任意路径**"。

---

## 7. 我认为自己 R1 文档里被推翻或需要修正的地方

1. **R1 A9 / A2 对"38 次 policies/ 写入"的定性错了，必须撤回**。我把工作树里新增的规则文件写成"**无审批地改变判定依据**"的攻击已发生。**R7 推翻了这个定性**：这些文件是**并行规则转化工作流的合法产物**——79 个正反例夹具（tests/fixtures/rules/<ID>/{bad,good}.py）、docs/project/architecture/规则转化覆盖报告.md、knowledge/corpus.yaml:158 起的 chunk 级溯源，且 AGENTS.md 已把"44 条规则"与约束 40（提炼必须显式、可评审、带正反例与溯源）正式登记。它们走的是"台阶 5 写 YAML"的**既定作者路径**，不是越权写入；.tmp/ 下没有 Phase 4 台账也是**预期行为**（这条路径本来就不经过受控执行链）。**修正后的正确表述**：这不是越权事件，而是"**合法变更路径在事实基线上不可见**"——而 OS 要解决的正是这件事。
2. **R1 C1 的"第二判定"范围被我夸大了**。真正产出**结论**的只有 app.js:198（severity → block / allow_with_warnings）与门禁页的"预演通过"（app.js:364-366）；build_site.py:41/456 是**文案与枚举副本**（不产出结论）；rule_body_incomplete 一类是"输入形状"，与 modules §0"输入收敛是 UX 而非判定"一致，不应全算 C1 违规。**C1 违规清单收窄为上述两条。**
3. **R1 A3 的表述需要加限定**。我用的是 precheck（dry_run=True），证明的是"**授权判定放行**"，不是"写入成功"。修正为："orc.fs.write 的 **pre-check** 对以下目标返回 allow（exit 0），实际写入未执行"。
4. **R1 A13/C15 应从"引用可核"扩到"数值与状态可核"**。本轮证明更危险的是**过期状态**：rule_sources 已被填上，而两份提案仍写"空 / exit 1"（F-A2、L-A7）。C15 修正为"数值型事实必须带取数时刻与产生它的命令；**状态型事实必须带复跑命令与时刻**，否则视为过期"。
5. **R1 漏了一条我该更早提出的问题**：r1-flows 的 Q4"规则集身份在并发写入下如何冻结"是我 R1 没有的，而它恰好是 OS 总设计必须先回答的前置问题。我承认并接收这一条。

---

## 8. 给 Lead 的三条最重结论

1. **三份提案共同把"门禁绿"当健康信号，而合法的规则集变更就发生在门禁全绿的同时**：6 份 → 44 份、RuleSet.identity 至少变过 3 个值，check-rules 全程 exit 0。OS 的总设计必须把"**规则集身份 + 取数时刻**"立为一等事实，任何"绿"都要回答"绿的是哪一批"。
2. **快照纪律比攻击面更早伤害这个设计**：同一场会议内，三份提案报出 26 / 44 / 45 三个规则数、fixture-shop 报成 46（实测 45）、"溯源为空"在提案落地后即失效（实测 DOC-001 exit 0）。**没有一份带取数时刻**。建议在总设计里加一条硬规则：凡数值/状态事实必须写成"值 + 时刻 + 复跑命令"，否则不得进入线框与验收条目。
3. **B1 的修法必须落在注册表数据侧，否则等于没修**：只改 nodes.py 的工具选择分支，orc.fs.write 仍可被其他调用方无审批改写 registry/tool-registry.approved.json 与 adapters/approved.json（实测 pre-check 全部 exit 0）。三份提案都把它写成"新建规则文件"的单点缺陷，这会直接导致修法选错层——而修复成本在注册表侧，不在编排侧。

---

## 附：本轮复跑命令（只读；precheck 仅与 R1 同一条，未改任何源码与既有文档）

```powershell
$env:PYTHONPATH = 'src'
python -m policy.check --check-rules                                                      # 44 条 / sha256:a90e64ac…
python -m policy.check --check-rules --rules policies --rules tests/fixtures/api/rules     # 45 条 / sha256:eea3f175…
python -m retrieval.cli rules --rule DOC-001                                               # 0（2 条溯源）
python -m retrieval.cli rules --rule ARCH-001                                              # 1（无登记）
python tools/ci_local.py --list                                                            # 35 行；"本机跳过"8 条
git ls-files policies ; git status --porcelain policies                                    # 6 / 38
```

**本文件未做的事（如实标注）**：未复跑全量 pytest；未回读 orchestration_loop.py / phase_evidence.py 的最终退出码（flows 的 F10/H4 未完项我未接手）；
未构造 504；未做浏览器 DOM 实验；未核实 38 份新规则文件的**作者与提交计划**（属另一工作流，按纪律写【未知，需核验】而非归因）；
三份提案的 file:line 我只逐条核了本文引用的那些，未做全量引用审计。

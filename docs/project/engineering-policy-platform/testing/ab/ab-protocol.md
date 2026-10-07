# 治理开 / 关 A/B 实验协议（AB-1 · 接口冻结 v1）

> **这份文件是什么**：把主张「**在 Agent 开发过程中使用本项目的治理，产出的代码在规范性 / 可用性 / 安全性上有显著提升**」
> 变成一份**可执行、可证伪、能被第二个人重算**的实验协议：三臂定义、一次 run 产出什么、
> 物理隔离与污染检测、任务集、配对与随机化、功效与预注册、证伪条件、成本、落点。
>
> **它不是什么**：不是读数。本文件里所有带 `【提案】` 的数字（MDE、样本量、门槛）**尚未标定**，
> 跑之前必须写进数据文件；所有带 `【实测】` 的行都是本次（2026-10-07）在本机跑出来的，带命令。
>
> **状态口径**：`【实测】`= 本次跑过并贴出命令与原始数字；`【上游实测】`= 引用仓内既有读数并给出处；
> `【提案】`= 未标定；`【待验证】`= 有明确的验证命令但本次没跑；`unavailable`= 本机测不了，写明原因。
>
> **上游方案**：[governance-value-eval-plan.md](../governance-value-eval-plan.md)（下称「方案」）。
> 本协议是它的 **W7（价值 A/B）** 的可执行化，并遵守方案 §2 的 R1 / R2 / R3 三条纪律。
>
> **写域**：本文件。`docs/project/engineering-policy-platform/testing/ab/` 下的其他文件
> （`measurement-instruments.md` / `redteam-and-pilot.md`）各有其主，本协议只引用不改写。

---

## 0 主张、结局与「不许自证」的落点

主张（一句话）：**同一 Agent、同一任务集、同一模型与参数，装上本项目的治理（规则 + 门禁 + 反馈）
后产出的代码，在规范性 / 可用性 / 安全性上优于不装。**

拆成两个**互相独立**的问题，本协议拒绝把它们合成一个数：

| 问题 | 对照 | 记号 | 它回答什么 |
| --- | --- | --- | --- |
| 治理**整体**有没有用 | `enforced` − `off` | **总效应** | 值不值得装 |
| 其中**门禁**占多少、**反馈**占多少 | `enforced` − `advisory`（门禁）、`advisory` − `off`（反馈） | **分解** | 钱花在哪一半 |

三条不许越过的线（照抄方案 §2 的 R1 / R2 / R3，并落到本协议的字段上）：

- **R1 不许自证**：`规范性 / 安全性 / 可用性` 三个结局的**标签一律不来自平台的 Decision**。
  平台的 Decision 只出现在两类地方：① 作为**处理变量**（这次动作被拦了吗）；② 作为 **`精确` 这个量**的被测对象
  （用**反事实 + 独立仪器**判它对不对，见 §1.4）。任何一处把 Decision 当标签的写法都作废。
- **R2 三层不许顶替**：本协议说的是 **L3（治理价值）**。L1 全绿（`evaluation/results/fidelity-*.json`）与
  L2 人评都不进本协议的任何分母；反之本协议的成功率差**不许**被读成"规则准"。
- **R3 预注册**：§6 的门槛与 §7 的证伪条件必须先写进数据文件再跑；行为有意变化用显式 `--record` 重记基线。

---

## 1 三个价值词的可计算定义

「精确 · 高效 · 全自动化」不是形容词，是三个**带分子分母的读数**。每个量必须能回答：
**分母是什么、位置怎么匹配、口径不同怎么记、命令是什么**。

### 1.1 精确（precision）：拦住的时候理由对（P1）

- **一句话**：被拦下的编辑，如果放行，独立仪器会不会真的变红。**反事实估计，不依赖人评。**
- **分子**：`TP` = 反事实树上**新出现**的、且**被本次阻断引用的码**覆盖的独立仪器诊断条数。
- **分母**：`reconstructible ∧ block_class=policy_violation ∧ 该码在独立冻结配置的 select 里 ∧ 前置树快照可用` 的阻断次数。
- **判 TP / FP 的规则**（写死，先于跑）：
  `delta = findings(反事实树) − findings(前置树)`，**按文件与码**取差；`delta > 0` 且包含被引用码 → **TP**；
  `delta = 0` → **FP**；构造不出反事实树 → `unreconstructible`，**不进分母**（不是 FP）；
  被引用码不在独立配置的 select 里 → `unverifiable`，**单列**（不是 TP 也不是 FP）。
- **位置匹配必须是 diff-aware，不是裸 `(row, code)`**（redteam 实测后修正，我方接受）：
  比较前先用 **diff 的 equal 块**把前置树的行号**回映射**到反事实树的行号，再做 `(file, code)` 相减。
  **反例（实测）**：裸 `(row, code)` 会把"编辑把代码整体下移"读成"新增了一批诊断"——
  `raw − shift_aware` 的差实测为 **3 / 3 / 5** 条，与独立量到的假新增**逐条相等**。
  ⇒ 不使用回映射的读数**一律作废**（它把行漂移算成了新问题）。
  仍然**不做容差对齐**：回映射是**确定性**的（equal 块是 diff 的输出），容差是**猜**的。
- **为什么这不是自证（R1）**：裁决（block）来自平台，但**标签（真红 / 假红）来自一个不读平台规则集、
  不读 `validation/ruff.toml`、不读平台分级与映射的仪器**。残留的同源只有"底层 linter 实现"，见 §1.5。
- **读数**：`P1 = TP / (TP + FP)`，Wilson 区间，**同时报** `unreconstructible` / `unverifiable` 的条数。
  分母 < 20 → 只报 `(TP, FP, n)` 三个原始计数，**不给比率**。
- **【实测】首个读数（redteam 跑，构造样本，3.0 s，仪器冻结版 132,173 B / `40db…`）**：
  `TP 4 / FP 0 / unreconstructible 1 / unverifiable 0`，分母 4（抽样单位 = edit），
  `precision = 1.0`，Wilson 95% **[0.510, 1.0]**。
  输入 = 3 条真实的"插入未使用导入"编辑 + 1 条**本仓已登记的误报** + 1 条故意不可重建的编辑。
  `unreconstructible` 的 reason 有了实测形态：**`old_string` 在目标文件里出现 0 次（必须恰好一次）**，且**不进分母**。
  **必须与它一起读的三句**：① `n = 4`、构造样本、**非随机抽样** ⇒ **这不是估计**，
  `1.0` 只能读成"这批样本里平台与仪器一致"；② 这是**真实 run 记录之外**的构造读数，
  §3.3 的 `block_class = unknown` 限制对它不适用，但对真实 JSONL 仍适用；③ 见下一条的**上界**。
- **【实测】`precision` 的上界不是 1，是"与仪器一致率"**（redteam 用阳性对照量出来的，我方接受并加为硬要求）：
  把**已登记的误报**（本仓 `SEC-004` 那类：把错误码常量当凭据）喂进 `--known-false-positive-edits`，得
  `declared_false_positives = 1 / instrument_says_red = 1 / max_achievable_precision = 0.0`。
  ⇒ **独立仪器与平台在这里犯了同一个错**（§1.5 的"共同盲区"不再是论证，是读数）。
  **因此 `P1` 必须与 `max_achievable_precision` 并列呈现**，否则读者会把 `1.0` 当成准确率。
  写成一句话：**"我们的精确率上限不是你有多对，而是你能多接近那个也会犯错的仪器。"**

### 1.2 高效（efficiency）：单位产出的代价（E1–E4）

| 记 | 量 | 分子 / 分母 | 口径 | 命令 |
| --- | --- | --- | --- | --- |
| E1 | 单次判定延迟 | p50 / p95（最近秩法） | **进程内到进程外全算**（就是 Agent 真实等的那一下）；**剔首个冷启动单列**；N ≥ 30 | `python -m adapters.dsh.hooks --config <cfg> --hooks-config <hooks.json>` 喂固定事件（§3.5） |
| E2 | 每任务墙钟增量 | `wall_clock_s` 同任务配对差 | 配对 = 同 `task_id` + 同 `replicate`；报中位数差与 bootstrap 区间 | 由 run 记录 `ended_at − started_at` |
| E3 | 被拦后的重试次数 | 每个 task 内"上次被拦之后的下一次同类写动作尝试"的计数 | **不是**工具调用总数；同类 = 同一 `tool` 且同一 `path` | run 记录 `retries_after_block` |
| E4 | 每任务 token | —— | 采集端拿不到就写 `unavailable` + reason，**不许估** | 由 Agent 适配器上报 |

### 1.3 全自动化（full automation）：不需要人（A1–A4）

| 记 | 量 | 分子 / 分母 | 性质 |
| --- | --- | --- | --- |
| A1 | 人工介入次数 | `human_interventions`（计数） | **价值结局**。`0` 是读数，`null` 是缺数据——两者必须长得不一样 |
| A2 | 无人工完成率 | 无需任何人工触点的成功任务数 / 任务总数 | **价值结局** |
| A3 | 受治理动作覆盖率 | `write_actions_governed / write_actions_total` | **操纵检查**，不是价值结局（见下） |
| A4 | bypass 次数 | 改了树却**没有** Decision 记录的写动作数 | **操纵检查** |

**A3 / A4 必须标成操纵检查，不许当成绩报**：树级覆盖率在"hook 挂上了"时**必然**接近 1，
它与"产出的代码更好"没有因果关系——把它当价值证据就是拿处理变量冒充结局变量。
在 `off` 臂里 A3 恒为 0，这不是"治理没覆盖"，是**该臂没有治理**；写进表里时必须带这一句。

### 1.4 三个结局变量（规范性 / 安全性 / 可用性）

| 结局 | 主读数 | 仪器 | 独立于策略层？ |
| --- | --- | --- | --- |
| 规范性 | `NORM_LINES` = 改动行上的独立诊断条数（`counts_by_code_changed`） | **ruff 的独立冻结配置**（不读 `validation/ruff.toml`） | **是**（配置、分级、映射、阻断全不共享） |
| 规范性（次） | `NORM_FILES` = 改动文件级口径（`counts_by_code_touched_files`）；`NORM_TREE` = 终态整树密度（每 KLOC） | 同上 | 同上 |
| 安全性 | `S1` = 改动行上的 `S` 码诊断数 | 同一独立配置的 S 子集 | **半同源**（见 §1.5） |
| 安全性 | `S2` = 自写标准库 `ast` 探针命中数（`eval`/`exec`/`os.system`/`subprocess(shell=True)`/`pickle.loads`/`yaml.load` 无 Loader/硬编码凭据） | 自写实现 | **是**（第二实现），但它**未被外部 oracle 校准** |
| 安全性 | `S3` = 依赖 CVE | pip-audit | `unavailable`：本机无该工具且 PyPI 不可达 |
| 可用性 | `U1` = **冻结测试 oracle**（主） | 任务自带的测试文件，跑前由 harness 从基线恢复，跑在 Agent 的**最终源码树**上 | **是**（外部成功判据） |
| 可用性（次） | `U2` = 原样成功率（Agent 自己的树、自己的测试） | pytest | —— |
| 可用性 | `U3` = 回归（PASS_TO_PASS 公共支撑集仍绿）；`U4` = 模块可导入 + 公开签名哈希 | pytest / 标准库 `ast`+`inspect` | **是** |

- **U1 的判据写死**：任务 `t` 的成功 ⟺ 冻结测试集 `FROZEN(t)` 全绿 **且** 公共支撑集 `COMMON` 不劣化。
  `FROZEN(t)` 与 `COMMON` 在跑之前冻结进数据文件（§8），**跑后不许改**。
- **U2 − U1 的差本身是一个读数**（"可游戏面"），不是噪声：Agent 若靠改测试/加 skip 拿分，差值会显出来。
- **`U1含` / `U1不含` 两个读数（lead 要求两个都报）**：`U1不含` 只在 `COMMON` 上跑（**主结局**）；
  `U1含` 在 `COMMON ∪ Δ` 上跑，`Δ` = **在某一臂可收集、在另一臂不可收集的测试模块集合**。
  **在已采纳的外部目标树设计下 `Δ = ∅`**（任务树里没有平台产物、两臂用同一份归档 ⇒ 两臂的测试集合相同），
  因此 `U1含` 必须写成 `not_applicable` + 原因，**不是**写个 0、也不是省略。
  这条规则的用途是**兜底**：一旦某个任务的树里出现了"只在 treatment 臂可用"的模块（例如有人又往任务树里塞了平台产物），
  `Δ` 立刻非空，此时 `U1含` 必须单列并给出模块清单与条数差——**不许把它悄悄并进主结局，也不许藏着不报**。
  （自举设计下 `Δ` 就是本仓那 12 个模块 / 约 304 条，§4.6 实测 1；那个设计已被裁定驳回。）
  **还有一条硬禁止（redteam 提出，我方接受）**：`U1含` **不许跨臂相减**。`Δ` 里的模块只在 treatment 臂存在，
  差额由**处理本身**决定，把它算成处理效应就是把"支撑集属性"包装成结局。收不齐的那一臂里
  `U1含` 记 **`unavailable`**——**不是 0、也不是 fail**（"没测到"和"测到了很糟"是两回事）。
- **三态**：`status ∈ {ok, red, environment_unavailable}`，**按 pytest 退出码写死映射**（不是看有没有 "error" 字样）：

  | pytest exit | 含义 | 读数 |
  | --- | --- | --- |
  | 0 | 全绿 | `ok` |
  | 1 | 有用例失败 | `red` |
  | 2 | 被中断 | `environment_unavailable` |
  | 3 | 内部错误（含 `INTERNALERROR`） | `environment_unavailable` |
  | 4 | **用法错误** | `environment_unavailable` |
  | 5 | **一条都没收集到** | `environment_unavailable` |

  **这条有真实病例**（redteam 2026-10-07 在 `tools/ab_measure.py` 上实测）：pytest `exit_code = 4`、`counts.total = 0`，
  块级却给 `pytest_status = "red"` / `red = true` ⇒ **"跑不了"被报成"红的结局"**。
  这正是 §7.1 排除优先级第 5 级要挡的东西（把基础设施失败读成处理效应）。
  **收到 `exit ∈ {2,3,4,5}` 或 `counts.total == 0` 时，读数必须带 `exit_code` 与 `counts` 原值**，
  并且**绝不计入任何分子分母**——不是"红的"，是"没测到"。

### 1.5 同源等级：哪些量是"半同源"，以及它会怎样削弱结论

本机**只有 ruff 0.14.13 一个外部扫描器**（`ruff --version` → `ruff 0.14.13`【实测】；
bandit / semgrep / pylint / mypy / radon / vulture / pip-audit 均不存在，PyPI 不可达 ⇒ 装不上）。
因此：

| 量 | 独立于**策略层**（规则集 / 分级 / 映射 / 阻断 / 配置） | 独立于**底层 linter 实现** | 结论强度 |
| --- | --- | --- | --- |
| `NORM_LINES`/`NORM_FILES`/`NORM_TREE` | 是（独立冻结 select，不读 `validation/ruff.toml`） | **否** | 中等：能证"改动行上的诊断少了"，**不能**证"ruff 看不见的坏味道也少了" |
| `S1` | 是 | **否**（同一 `ruff` 的 S 插件） | 弱→中：**半同源**，必须与 `S2` 一起看 |
| `S2` | 是 | **是**（自写 AST） | 中，但**未被外部 oracle 校准**：它能红不能证明它不漏 |
| `U1`/`U3`/`U4` | 是 | **是** | 强（外部成功判据） |
| `P1` | 是 | **否** | 是**下界**：同一 linter 的共同盲区不会被发现 |
| `E*`/`A*` | 是 | **是** | 强（但 A3/A4 只是操纵检查） |

**符号卫生（ab-instruments 提出，我方接受其结论、修正其诊断）**：对方判"\`N1/N2/N3\` 在 §1.5 是同源等级、在 §(d) 是三个 tree_scope ⇒ 同名两义（AGENTS 第 50 条）"。
**诊断不成立**：本文件里 `N1/N2/N3` 从头到尾只有一个意思（规范性三口径）；`tree_scope` 本来就是另一个枚举，两者没有混用。
**但结论成立且重要**：**不透明符号会让两批读数看起来可比，实际不可比**。因此：
- 三个规范性量改名为自证含义的 `NORM_LINES`（改动行，主口径）/ `NORM_FILES`（改动文件）/ `NORM_TREE`（终态整树）——**已全文替换，旧符号零残留**；
- **采纳对方的 `tree_scope` 枚举**：`tree_scope ∈ {final, changed_lines, changed_files, whole_tree, base}`（比原来的 `per_turn_diff` 更明确）；
- 同源等级用**拼写完整的词**，不用短码：`policy_layer_independent_linter_dependent` /
  `half_homologous_same_binary` / `second_implementation_uncalibrated` / `externally_independent` / `manipulation_check`。
**这条规则写给后来者**：短码只在**一张表内部**使用；一旦跨表、跨文档、跨会话引用，就必须用自证含义的名字。

**必须写进每一条结论的局限句**（照抄，不许删）：
> 本机的独立仪器与平台的证据工具共用同一个底层 linter（ruff 0.14.13）。
> "仪器独立"只成立于**策略层**（规则集 / 分级 / 映射 / 配置 / 阻断），**不成立于实现层**。
> 因此本实验能识别"平台把错误的东西当违规"（P1 的下界），**不能**识别"两者一起漏掉的东西"。
> 语义级安全问题（S 码之外）、复杂度、死代码、依赖 CVE 在本机**没有仪器**：一律 `unavailable`，不许估。

---

## 2 臂定义（三个，不是两个）

### 2.1 三臂对照表（**接口冻结**）

| 维度 | `off`（无治理） | `advisory`（只报不拦） | `enforced`（真阻断） |
| --- | --- | --- | --- |
| 工作树 | **净化树**（§4） | 净化树 + `.policy/` | 净化树 + `.policy/` |
| Hook | **不挂载** | 挂载（pre 路径） | 挂载（pre 路径） |
| 决策计算 | **不发生** | `policy.engine.evaluate`（同一条路径） | 同 |
| 交付给模型的诊断信封 | **无** | `action: applied` | `action: rejected` |
| 写动作是否被拒 | 否 | **否**（恒 exit 0） | 是（exit 2） |
| 失败关闭 | 不适用 | **不适用**（不阻断就无所谓失败关闭） | 是（`evidence_unavailable` 等按门禁语义阻断） |
| 产生的 run 记录字段 | 全字段 | 全字段 | 全字段 |

**`advisory` 的确切实现（不新增 `src/**` 改动）**：在 `enforced` 的 hook 命令前套一层 **`exit0_shim`**：
它原样转发 stdin 给真 hook、**原样转发 stderr**、把退出码**一律改写成 0**，并把**原始退出码**
（0 或 2）追加到 run 记录的 `shim_observed_exit`。这样：

- 决策路径**逐字相同**（同一个 hook、同一份配置、同一次 `ruff` 调用）；
- 交付给模型的诊断文本**逐字相同**（stderr 不截断、不改写）；
- 唯一的差别是"写动作生效与否"——这正是门禁效应。

### 2.2 为什么两臂不足以归因（这是本协议存在的理由）

设 `Y` 为任一结局。两臂只能给出 `Δ_total = Y(enforced) − Y(off)`。而 `enforced` 相对 `off` 同时改变了**两件事**：

1. **反馈回路**：Agent 在写动作前后**读到了诊断文本**（知道哪一行、哪个码、什么理由），于是可以改；
2. **门禁**：写动作**被拒绝**，脏内容进不了树。

`Δ_total` 是两者之和。三种情形会给出**相反的行动建议**，而两臂实验分不开：

- 反馈有效、门禁无效（例如拦下的都是可改可不改的 warning）→ 应当保留 `advisory`、去掉 `enforced`；
- 门禁有效、反馈无效（例如 Agent 看不懂理由、只是被迫重试到随机通过）→ 应当保留阻断、重写理由；
- 两者都有效 → 维持现状。

`advisory` 臂把 `Δ_total` 拆成 `Δ_feedback = Y(advisory) − Y(off)` 与 `Δ_gate = Y(enforced) − Y(advisory)`。
**分解的可加性有前提，必须写下来**：只有当 `advisory` 与 `enforced` 交付的信息**逐字相同**、
且**唯一**差别是"写动作是否被拒"时，`Δ_gate` 才是门禁效应；一旦诊断文本在两臂间有任何措辞差异，
`Δ_gate` 就混入了"措辞效应"。§2.3 给出这条前提的机器检查。

### 2.3 反馈文本同一性（可机器检查的断言）

诊断信封（DiagnosticEnvelope）的字节形态先写死：

```text
[GOVERNANCE] decision=<block|allow_with_warnings>
[GOVERNANCE] action=<rejected|applied>
[GOVERNANCE] ruleset=<rule_set_hash>
violations:
- rule_id=<ID> severity=<error|warning> code=<CODE> line=<N> message=<原样消息>
```

- 允许两臂不同的**只有** `action=` 一行（`block` 臂为 `rejected`、`advisory` 臂为 `applied`）；
  `decision=` 在两臂**相同**（`advisory` 臂记的是"若阻断会是什么"）。
- **哈希算在哪一侧：只有一份实现，不是两份**（回答 ab-instruments 的"口径统一不了"）。
  规范化的**唯一实现方是测量侧**（`ab_measure`），生产侧（harness）只负责**原样存字节**：
  `\.tmp/ab-runs/<run_id>/envelopes/<seq>.txt`（逐字节，不做任何加工）+ 记录它的 `sha256`（原文哈希）。
  ⇒ **不存在"你算的和我算的不一样"**：生产侧不算 body 哈希，测量侧只从原文算一次。
- **规范化规则先写死**（测量侧按此实现，别人重算也按此，逐字可复现）：
  1. 按 UTF-8 解码；**出现非法字节则该 run 作废**（不做 `errors="replace"` 容错——容错会把两个不同的字节串映成同一个哈希）；
  2. 换行归一：先把 `\r\n` 与单独的 `\r` 全部替换为 `\n`；
  3. 去掉**每行行尾**的空格与 Tab；**行首空白保留**（缩进是内容的一部分）；
  4. 删除**整行恰好匹配** `^\[GOVERNANCE\] action=(rejected|applied)$` 的行（连同它后面的换行）；
  5. 末尾的多个换行压成**恰好一个**；
  6. 对结果做 UTF-8 编码后取 sha256，**小写十六进制**。
  **落 `feedback_envelope_body_sha256`；原文哈希落 `feedback_envelope_sha256`**，两个都进 run 记录。
- **交叉校验**：测量侧算出的 `feedback_envelope_sha256` 必须等于生产侧存的原文哈希——不等就说明
  某一侧改过字节，**该 run 作废**（`exclusion.reason=feedback_text_mismatch`）。
- **断言**：同 `task_id` + 同 `replicate` 下，`advisory` 与 `enforced` 的 `feedback_envelope_body_sha256`
  在**同一触发点**上必须相等。不相等 → 该 run 对作废（`exclusion.reason=feedback_text_mismatch`）。
- 【待验证】"信封真的进到了模型上下文里"必须单独证明，命令：在 `advisory` 臂跑一个**必然触发诊断**的写动作，
  断言 Agent transcript 里出现 `feedback_envelope_body_sha256` 对应的原文；断言失败 → `advisory` 臂降级为"未实施"。

### 2.4 可选第 4 臂（`advisory_sham`，**次要，不进主结局**）

`advisory − off` 还混着一个非信息效应：`advisory` 臂的 Agent **多收到一段文本**（多花 token、多一轮）。
要把它拆掉，需要一条**安慰剂臂**：信封长度与形状相同、但内容换成**与本任务无关且不可行动**的诊断
（例如上一个任务里真实采集到的违规列表，打乱顺序后注入），并且**不指明位置**。

- **状态**：`【提案】`。只有主结局的三臂跑完且预算允许时才跑；**不许**在没跑它的前提下把
  `advisory − off` 全部读成"反馈的信息价值"。**不跑就写"未分解出剂量/token 效应"**（§9 反面清单第 4 条）。

---

## 3 一次 run 产出什么（**接口冻结 v1**）

**一次 run = (臂 × 任务 × replicate) 的一次完整 Agent 会话**：从基线树起，到终态树与 run 记录落盘止。

### 3.1 目录布局（全部在 `.tmp/`，不提交）

```text
.tmp/ab-runs/<run_id>/
├── run.json                 # 唯一读数载荷（schema_id: ab-run-record/1）
├── transcript.jsonl         # 逐步：模型输出 / 工具调用 / 信封原文
├── trees/
│   ├── base/                # 基线树的**只读引用**（不复制：记 tree_sha256 + 取用命令）
│   ├── final/               # 终态树快照（每个 run 一棵，绝不跨 run 复用）
│   └── on_block/<action_id>/  # 每个被阻断动作的**前置树**快照（反事实的输入）
├── diffs/
│   ├── final.diff           # 终态相对基线（unified，git diff 或 stdlib difflib）
│   └── per_turn/<turn>.diff # 每轮相对上一轮的 diff（过程量，只作次要读数）
└── patches/
    └── blocked/<action_id>.patch  # 被阻断编辑的可重建形态（replacement 或 unified diff）
```

### 3.2 `run.json` 字段表（**字段名、类型、产生方式写死**）

```yaml
schema_id: ab-run-record/1        # 载荷自己的版本轴（AGENTS 55：加键就升版）
version: 1
identity:
  run_id: <str>                   # <arm>-<task_id>-<replicate>-<utcstamp>
  arm: off | advisory | enforced
  task_id: <str>
  replicate: <int>                # 同 (task, arm) 下的第几次，从 1 起
  block_id: <str>                 # 随机化块
  session_id: <str>               # 每次 run 全新，绝不跨 run 复用
model:                            # 缺失任一键 = 该 run 作废（排除规则 §7）
  provider: <str>
  name: <str>
  revision_id: <str>              # 逐次调用记录，见 §3.4
  temperature: <float>
  top_p: <float>
  seed: <int|null>
agent:
  adapter_id: <str>
  manifest_sha256: <str>
  host_version: <str>
tree:
  base_ref: <str>                 # git revision 或归档 sha256（钉死）
  base_tree_sha256: <str>         # 覆盖「相对路径 + 文件 sha256」的稳定摘要
  final_tree_sha256: <str>
  purification_manifest_sha256: <str>
  workdir_rel: <str>
governance:                       # 操纵检查：处理到底有没有被施加
  hook_mounted: <bool>
  hook_config_sha256: <str|null>
  rule_set_hash: <str|null>
  rules_total: <int|null>
  rules_by_severity: {error: <int>, warning: <int>} | null
  hook_invocations: <int>
  decisions_by_verdict: {allow: <int>, allow_with_warnings: <int>, block: <int>}
  shim_observed_exit: {0: <int>, 2: <int>} | null   # 仅 advisory 臂非 null
leak_assertions:                  # §4；任一项失败 = 该 run 作废
  paths_absent: <bool>
  vcs_dir_absent: <bool>
  content_leak_hits: <int>        # 必须为 0
  runtime_hook_marker_seen: <bool>  # off 臂必须为 false（"平台有没有真的没跑"）
  agent_self_tool_runs: {ruff: <int>, pytest: <int>, other_lint: <int>}
actions:
  tool_calls_total: <int>
  write_actions_total: <int>              # 定义了「写动作」= 冻结工具表里的写类工具调用
  write_actions_governed: <int>           # 其中真正经过 Decision 的（off 臂恒为 0）
  blocked_actions: <int>                  # = blocked_edits 的长度
  advisory_findings_delivered: <int>      # 投递给模型的诊断条数（advisory/enforced）
  retries_after_block: <int>              # 定义见 §1.2 E3
  blocked_edits: [<BlockedEdit>]          # 见 3.3
usability:
  frozen_tests: {status: ok|red|environment_unavailable, passed: <int>, failed: <int>, errors: <int>}
  asis_tests:   {status: ok|red|environment_unavailable, passed: <int>, failed: <int>, errors: <int>}
  fail_to_pass_met: <bool|null>
  pass_to_pass_preserved: <bool|null>
  import_check: {status: ok|red|unavailable, modules: [<str>]}
  public_api_sha256: <str|null>           # 改动文件中公开函数签名的稳定哈希
diff:
  files_changed: <int>
  insertions: <int>
  deletions: <int>
  plus_lines: <int>                       # NORM_LINES 的分母（KLOC = plus_lines/1000）
  diff_sha256: <str>
  counts_by_code_changed: {<CODE>: <int>}          # NORM_LINES（主口径：行级交集）
  counts_by_code_touched_files: {<CODE>: <int>}    # NORM_FILES（整文件口径）
  counts_whole_tree: {<CODE>: <int>}               # NORM_TREE（终态整树）
human:
  human_interventions: <int|null>          # 0 是读数；null 是"没有采集到"，不许写 0
  human_interventions_detail: [{kind: <approval_requested|approval_granted|manual_edit|manual_answer|abort>, turn_index: <int>}]
feedback:
  feedback_envelope_sha256: <str|null>
  feedback_envelope_body_sha256: <str|null>
exclusion:
  excluded: <bool>
  reason: <null|infrastructure_failure|feedback_text_mismatch|model_revision_drift|environment_unavailable|leak_assertion_failed|task_invalid|baseline_unavailable>
infrastructure_failures: [{kind: <hook_spawn_failure|hook_timeout|config_unreadable|registry_drift|other>, count: <int>}]
timing:
  started_at: <iso8601-utc>
  ended_at: <iso8601-utc>
  wall_clock_s: <float>
reading_context:                  # 方案 §6.5：哪棵树 / 哪个环境 / 哪套声明
  tree: <str>
  environment: <str>
  declarations: <str>
  instrument: {tool: ab_measure.py, version: <str>, config_sha256: <str>}
```

### 3.3 `BlockedEdit`（`blocked_edits[]` 的元素）——**ab-instruments 点名的第 1 个硬缺口**

```yaml
action_id: <str>                  # 幂等键：<adapter.namespace>:<event_id>（AGENTS 26）
task_id: <str>
attempt_seq: <int>                # 该 task 内第几次写动作尝试，从 1 起
tool: <str>                       # 冻结工具表里的名字（edit / write / ...）
path: <str>                       # 仓库相对路径，POSIX 分隔符
pre_sha256: <str>                 # 前置文件哈希
proposed_content_sha256: <str>    # 提议内容哈希
reconstructible: <bool>
reconstruct_reason: <ok|old_string_not_unique|not_a_replacement|no_pre_snapshot|other>
replacement: {old_string: <str>, new_string: <str>} | null
unified_diff: <str> | null
violations: [{rule_id: <str>, rule_version: <str>, severity: <str>, code: <str>, line: <int>, message_sha256: <str>}]
block_class: <policy_violation|fail_closed|infrastructure_failure>   # 见 §3.4
verdict: <block|allow_with_warnings>
retry_of: <action_id|null>
pre_tree_snapshot_ref: <str|null>  # trees/on_block/<action_id>/ 的相对路径
```

- **产生方式**：由 Agent 适配器（Phase 6 规范事件）与 Phase 4 台账**联合**产生——
  `event_id` / `path` / `params` 来自事件，判定摘要来自 Decision，前置树快照由 harness 在**写动作之前**抓。
  `replacement` 与 `unified_diff` **至少一个非空**，且当 `reconstructible=true` 时二者可互推。
- **`old_string` 非唯一 ⇒ `reconstructible=false` ⇒ 不进 P1 分母**（不是 FP）。
- **消费者不许过滤，必须分类**（回答 ab-instruments 的问）：`block_class` 就是字段名，取值
  `policy_violation | fail_closed | infrastructure_failure`，由 run 记录（harness）产生，测量工具**只消费**。
  测量工具要做的不是"把 `infrastructure_failure` 删掉再算"，而是**分三类各报计数**，
  红线只落在"哪一类进 `P1` 的分母"（只有 `policy_violation` 进）。
  **理由**：过滤会把"有多少次是平台故障"这个读数本身删掉——那正是要报出来的东西。
  字段缺失 ⇒ 记 `unknown`，**绝不静默当成 `policy_violation`**。
- **实现状态（2026-10-07，必须与上面那条一起读）**：上面这条**已达成一致、尚未实现**。
  测量侧（task-12）的载荷当前**没有** `block_class` 分类；对方给出的理由是硬约束不是惰性：
  加键 + 改分母语义 ⇒ 按 **AGENTS 第 55 条**必须把该载荷 `schema_version` 1.0 → 1.1 ⇒ **会作废刚发布的冻结指纹**，
  而 lead 已宣布要用那个指纹复跑首读。
  ⇒ **本协议的处置（不需要重开冻结）**：**在实现落地之前，`counts.TP`/`counts.FP` 不得用于 `P1`**——
  因为它们可能混进 `infrastructure_failure` 条目。而本协议**已经能安全退化**：
  按上一条规则，无法分类的阻断一律记 `unknown` ⇒ **只有 `policy_violation` 进分母 ⇒ 分母 = 0 ⇒ F6 触发 ⇒ `精确` 写四个计数**。
  **因此正确的动作不是"先凑一个精确率"，而是"写 `精确 = unavailable`"**——这也与 G9（P1 全链路零样本）一致。
  写进结论时必须带一句：**"精确"在本轮不可测，原因是分类未实现，不是"精确率很高"。**
- **入参可信度**：`replacement` / `unified_diff` 是**用户代码原文**，只落在 `.tmp/ab-runs/**`，
  **不得**进任何提交进仓库的载荷；引用时只允许给 `sha256`。

### 3.4 `block_class` 三分（**这条是防"把平台故障读成治理成本"的**）

| `block_class` | 触发 | 计入门禁效应？ | 计入"规则拦住了"？ |
| --- | --- | --- | --- |
| `policy_violation` | 某条规则报了阻断级违规 | **是** | 是 |
| `fail_closed` | `evidence_unavailable` / `capability_unavailable` / 未知工具 / 注册表漂移——**设计如此** | 单列（这是"挡得住坏动作"，不是"说得出理由"） | **否** |
| `infrastructure_failure` | hook 起不来 / 超时 / 配置读不到而**恰好**产生退出码 2 | **否**（排除，单列计数） | **否** |

预注册的排除规则：`infrastructure_failure` **不计入任何结局的分子分母**，只报计数与原因。
`off` 臂没有这一类失败——这个**不对称**必须写在结论旁边，不许把它读成治理的成本。

### 3.5 固定事件（E1 的可重复输入）

单次判定延迟必须有一个**逐字节固定**的输入事件，否则两次测的不是同一个东西。事件从
`tests/fixtures/agent_events/dsh/` 里取一条**脱敏**样本，钉死 sha256 后写进门槛文件（§8）：

```powershell
$env:PYTHONPATH = 'src'
Get-Content <frozen-event.json> -Raw | python -m adapters.dsh.hooks `
    --config <cfg> --hooks-config <hooks.json> --audit <tmp-audit.jsonl>
```

【待验证】该命令的输入形态（stdin 事件 JSON 的字段名与 `--config` 的取值）本次**没有跑通**，
只验证了 `--self-check`（见 §4.3）。**跑之前必须先验证它**；验证不通过 → E1 写 `unavailable`，
不许用别的命令替代后仍叫同一个名字。

---
## 4 物理隔离与污染检测

> **lead 裁定（2026-10-07，采纳本协议 §4.1 的实测读法）**：
> ① **任务树 = 本仓之外的外部仓库 checkout**，**平台产物一个字节都不进去**；
> ② **平台从工作树之外的独立检出运行**（hook 只通过 `.policy/` 里的路径指向它）；
> ③ 原「净化清单」**降级为环境断言**（L1–L5 + 运行时 `[policy]` 标记探针）；
> ④ `vcs_dir_absent` **改语义**：外部任务树里没有 `.git` **不是必要条件**（那个仓库从来不含我们的规则）；
>    真正要断言的是「**任务树里不存在平台产物**」与「**平台检出不在任务树内**」；
> ⑤ §4.1 实测的「clone + `git rm` 后 `git show HEAD:policies/<ID>.yaml` 仍读得到」**照样保留**——
>    它是对「在本仓上自举」这条路的**证伪记录**（§4.6 / §10 第 10 条）。
> **追加理由（lead）**：自举会让 R1 以更深的形态复活（平台在自己的代码上量自己的规则）；
> `validation/validators.yaml` 同时是治理声明与 12 个测试模块的依赖 = **设计错误的信号**；
> 本项目的价值主张本来就是"Agent 开发过程中装上治理"，治理对象不是本仓。

### 4.1 先给一条实测结论：目标树**不能**是本仓库

需求写的净化清单是 6 条路径（`policies/`、`AGENTS.md`、`validation/`、`knowledge/`、
`.dsh` 钩子配置、`docs/project/engineering-policy-platform/**`）。本次在 `git archive HEAD`
（HEAD = `208295b66809fd6e9d5e5b5fd01cf2e25d11297a`）的副本上**照着做了，并量了两件事**：

**实测 1：净化把可用性 oracle 打坏了。**

```text
# 原始归档树
python -m pytest tests --collect-only -q   →  2136 tests collected in 6.11s   （exit 0）
# 删掉 6 条路径之后
python -m pytest tests --collect-only -q   →  1832 tests collected, 12 errors  （exit 2）
```

12 个模块全部因 `validators.registry.RegistryError`（`validation/validators.yaml` 没了）在**收集期**失败：
`tests/contract/test_validator_protocol.py`、`tests/integration/{test_dependency_path_consistency,test_rule_corpus,test_validator_hardening_cli,test_validator_pipeline}.py`、
`tests/security/test_validator_adversarial.py`、`tests/unit/{test_validator_adapters,test_validator_checkers,test_validator_facts,test_validator_hardening,test_validator_language_coverage,test_validator_pending_implementation}.py`。
⇒ **"仓库自带测试全绿"这个 oracle 在净化树上根本跑不起来**（差 304 条 + 12 个模块）。

**实测 2：净化既没净化干净，也不可能净化干净。**

在同一棵净化树上做**内容级**扫描（684 个文本文件，`.py/.md/.yaml/.yml/.toml/.ini/.json/.cfg/.txt`）：

| 检查 | 命中文件数 |
| --- | --- |
| 规则 ID 形态 `(SEC\|STYLE\|DOC\|ARCH\|TESTING)-\d{3}` | **176 / 684** |
| 具体规则 ID（`ARCH-001` / `SEC-004` / `STYLE-002`） | 81 |
| 字面 `policies/` | 45 |
| 字面 `validation/` | 72 |
| 字面 `knowledge/` | 32 |
| `AGENTS.md` 或「AGENTS 第 N 条」形态 | 82 |

按顶层目录拆：`tests` **142**（其中 `tests/fixtures` 96）、`docs` 13、`src` 12、`tools` 6、
`examples` 2、`README.md` 1。

**两条实测合起来是一个矛盾**：

- 可用性 oracle 要 **`tests/**`**；
- 污染控制要去掉 **`tests/**`**（142 个泄漏文件是它贡献的，`tests/fixtures/rules/<ID>/` 直接就是规则的正反例夹具）。

⇒ **自举式 A/B（目标树 = 本仓库）在任何净化方案下都不可比**：留下 `tests/` 就是控制臂读得到规则语义
（`tests/fixtures/rules/**` 是逐条规则的正反例），删掉 `tests/` 就没有外部 oracle。
这不是"净化做得不够狠"，是**目标树本身 = 处理**。

**因此本协议裁定：目标树必须是外部任务仓库**（第三方项目或本仓之外的固定夹具项目），
治理通过**外部安装**施加（`.policy/{dsh-adapter.yaml,hooks.json}` + 指向工作树之外的平台检出）。
需求那 6 条路径在这种设计下**不是"删除清单"，而是"环境断言"**（§4.3 逐条给出检查命令）。
这是一次**对需求读法的改动**，理由就是上面的实测。**lead 已于 2026-10-07 裁定采纳**（见本节开头裁定框），
并要求把自举路线连同其证伪记录保留在 §4.6 与 §10——**不是删掉，是留档**。

### 4.2 净化清单（两段：目标树 + 运行环境）

| # | 段 | 内容 | 为什么 |
| --- | --- | --- | --- |
| P1 | 目标树 | 从**基线 revision 的归档**建树（`git archive` / tarball），**不 clone** | 归档不含构建产物与历史；本次实测 `git ls-files .tmp` = **0** ⇒ 台账/索引天然不进树。**注意（裁定 ④）**：任务树里有没有 `.git` **不是**泄漏判据 |
| P2 | 目标树 | 控制臂：`.policy/` **不存在**；treatment 臂：只有 `.policy/dsh-adapter.yaml` + `.policy/hooks.json` 两个文件，且 `rules` 指向**工作树之外** | 两臂的工作树差别被压到最小、可枚举 |
| P3 | 运行环境 | dsh profile 里**没有**指向平台插件的接线（控制臂）；treatment 臂有一条，指向工作树外 | **树级 grep 证明不了"hook 未挂载"**（hook 可以挂在 `%USERPROFILE%\.dsh\**`） |
| P4 | 运行环境 | `PYTHONPATH` 不含平台 `src/`；环境变量里没有平台的配置路径 | **这条只约束控制臂**：treatment 臂的 Hook 必须能 import 平台（它就是处理本身），所以"treatment 臂进程里能 import 平台"**不是**违反 P4 |
| P5 | 运行环境 | 控制臂的**文件系统沙箱**不把平台检出目录暴露给它 | 这是唯一能证明"读不到"的手段；做不到就写"未隔离" |
| P6 | 两臂 | 每 `(task, replicate)` **一棵全新工作树 + 全新会话**，绝不跨 run 复用 | 否则 treatment 臂的修复会改善 control 臂随后看到的树 |
| P7 | 两臂 | 时间块内**两臂交错**，逐次调用记录模型 `revision_id` | 跨天跑会让模型漂移变成处理效应 |
| P8 | 环境 | **平台检出不在任务树内**，且任务树里**没有平台产物**（规则、验证器注册表、语料、hook 配置、平台文档一个字节都没有） | 裁定 ④ 的落点：这两条才是真正的泄漏判据；`.git` 在不在无关 |

**反面清单（做了就等于结论作废）**：

- **禁止 clone + `git rm` 净化**：`git show HEAD:policies/<ID>.yaml` 仍读得到（r3 实测）。
  本次我用的路线**结构性没有这个洞**——实测 `Test-Path .tmp\ab-probe\clean\.git` = **False**，
  因此 `leak_assertions.vcs_dir_absent` 必须是断言的一部分。
- **禁止**把"控制臂树里没有 `policies/` 目录"当成"控制臂读不到规则"（实测 2 已证伪这个推理）。
- **禁止**让两臂用不同的 ruff/pytest 版本或不同的目标树归档。

### 4.3 校验命令（可执行；每条都要进 run 记录的 `leak_assertions`）

```powershell
# L1 路径不存在（控制臂）
foreach ($p in @('policies','AGENTS.md','validation','knowledge','docs/project/engineering-policy-platform','.policy')) {
    if (Test-Path (Join-Path $TREE $p)) { throw "LEAK path present: $p" }
}
# L2 平台检出不在任务树内 + 任务树里没有平台产物（裁定 ④ 的两条真判据）
$treeAbs = (Resolve-Path $TREE).Path; $platAbs = (Resolve-Path $PLATFORM).Path
if ($treeAbs.StartsWith($platAbs) -or $platAbs.StartsWith($treeAbs)) { throw "LEAK: 平台检出与任务树相交" }
# 说明：.git 的有无**不是**泄漏判据（外部任务树本来就可能带自己的 .git）；
#       「自举路线必须无 .git」是 §4.6 的证伪记录，不适用于本设计。
# L3 内容级泄漏（规则 ID / 平台路径），必须 0 命中
$hits = Get-ChildItem -Recurse -File $TREE |
    Select-String -Pattern '(SEC|STYLE|DOC|ARCH|TESTING)-[0-9]{3}|policies/|validation/|knowledge/|engineering-policy-platform'
if ($hits) { throw ("LEAK content hits: " + ($hits | Measure-Object).Count) }
# L4 运行时行为探针：hook 在跑就会在 stderr 打 [policy] 标记
#    本次实测：--self-check 的 stderr 有 '[policy] effective-paths' 与 '[policy] self-check ok'
#    控制臂跑一次写类动作，断言 stderr 里不出现 '[policy]'
#    ✔ 状态：**已做正向对照**（task-15 实现并实测：off=false / advisory=true / enforced=true，全部 pass；
#      见 testing/ab/arm-harness.md 与 tools/ab_arm.py）。**本协议引用的是第三方便读数，未由我复跑**；
#      复跑时按反面清单第 11 条带 时间戳 + 文件大小 + sha256（该文件在被持续重写）。
#    ⚠ 两个已知失效模式：① harness 只收 Agent 的 stdio 时，hook 子进程 stderr 被吞 ⇒ **假阴性**
#      （hook 真跑了却判"没跑"）；② 标记不带 request_id/trace 时，**别的进程**（如测量工具自己跑
#      --self-check）打出的标记会造成**假阳性** ⇒ 整 run 被误废。两条都要在实现时消掉，否则读数不可用。
# L5 dsh home 接线扫描
Get-ChildItem "$env:USERPROFILE\.dsh" -Recurse -File -ErrorAction SilentlyContinue |
    Select-String -Pattern 'policy-hook|dsh-adapter|policy\.engine'   # 控制臂必须 0 命中
```

**这些断言的强度要如实写。** `isolation_level` 是**三档**，跑之前必须写进读数（否则两批数字不可比）：

| 档 | 判据 | 本机可得？ |
| --- | --- | --- |
| `tree_only` | 只有 L1–L3 的树级检查 | 可得（弱） |
| `code_path_verified` | 树级检查 **+ L4 正向对照 + P8 的三条代码路径判据** | **本机上限** |
| `fs_isolated` | 控制臂的文件系统/进程沙箱里平台检出**不可达** | **本机给不出**（没有可用沙箱工具） |

**L5（宿主 `.dsh` 接线）在本机是红的——三方独立实测，结论一致，数字不同。**
本机已有的 dsh profile（例如 `profiles/governed/cordis.patch.yml`）里写着
`policy-hook.plugin.mjs` 与本仓绝对路径 ⇒ **"控制臂在宿主层没有平台接线"在这台机器上不成立**。
三方读数（**单位必须一起写，否则数字不可比**——与 §1 的"分母是什么"同一条纪律）：

| 读数方 | 计数单位 | 针脚集 | 结果 |
| --- | --- | --- | --- |
| 本协议（我） | **行命中数** | `policy-hook` / `dsh-adapter` / `policy.engine` / 本仓路径（宽） | **136** 行命中 |
| task-15（修正后口径） | 文件数 / 出现次数 | 针脚原文进载荷 + 后缀过滤 `.yml/.yaml/.json/.js/.mjs/.ts` | **67 文件 / 181 次** |
| redteam 的针脚集 | 文件数 / 出现次数 | 同上，换 r3 的针脚集 | **64 文件 / 222 次** |

**三个数字都不是同一个东西**（行命中 ≠ 文件数 ≠ 出现次数），但**指向同一条结论**。
⇒ **两条处置，缺一不可**：
① 读数里必须**分开写两个布尔**（task-15 已按此形状出读数）：
`tree_isolation = true`（夹具基线）/ `host_wiring_isolation = false`（本机）；
② 要做到宿主层隔离，控制臂必须跑在**每次 run 独立的 dsh home** 里（而不是共享 `%USERPROFILE%\.dsh`）。
**做不到就写"本机在此配置下跑不出干净的控制臂"——这比跑出一个被污染的对照强。**

**为什么 `tree_only` 不够——redteam 的实测（2026-10-07，我方采纳）**：
把一棵树里的 13 条平台路径**全删光**之后，以它为 cwd 跑平台，**仍然加载 43 条规则**
（`rule_set_hash = sha256:50202675…`），两种 `PYTHONPATH` 都复现。
机制是 `src/policy/check.py:165-172` 的 `repo_root()` **从模块位置向上回溯**。
⇒ **"任务树里没有规则"与"跑起来的平台没有规则"是两件事**；隔离的对象是**平台从哪里运行**，不是任务树的目录列表。

**P8 的可证伪三条判据（必须全绿）**：
① 从臂内打印 `repo_root()` 与规则根，断言**都在平台检出内、都不在任务树内**；
② 断言载荷里的 `rule_set_hash` 等于**平台检出**的期望值；
③ 平台只认显式 `--rules`，**不传时必须失败**（不许靠回溯猜出规则根）。
把平台检出搬进任务树 → 这三条**必须变红**（这就是它的"修复前会红"证明）。

### 4.4 treatment 臂"读得到理由"是处理的一部分（必须写清楚）

- treatment 臂的 Agent **会**在写动作被拒时读到诊断信封（§2.3），并且**会**重试。这是**处理本身**，
  不是污染：被分离出来的正是这个反馈回路（§2.2）。
- 反过来说：**凡是让 treatment 臂多得信息、而 advisory 臂得不到的东西，都会污染 `Δ_gate`**。
  所以 `.policy/**` 的内容要压到最小（两个文件），并且**不得**在 treatment 臂额外放入规则文本、
  文档或提示词——规则只存在于工作树之外的平台检出里，靠 hook 读取。
- **treatment 臂里 Agent 主动去读工作树之外的规则**（如果沙箱允许）是**允许的**且在 `enforced`/`advisory`
  两臂等价；但必须作为协变量记录（`agent_self_tool_runs` 之外的 `policy_source_reads`），
  因为"读了规则"和"被拦了"是两种不同的作用机制。

### 4.5 残余污染：已知且未消除的缺口（不许掩饰）

1. `.policy/` 的存在本身是一个**提示**：treatment 臂的 Agent 知道自己在被治理。要分离它需要 §2.4 的安慰剂臂，
   **本次未跑**。
2. 目标树是第三方仓库，它自己的风格可能与平台的 `ruff.toml` 天然冲突；"独立性"只成立于策略层（§1.5）。
3. ruff 在 PATH 上、**两臂都在**：控制臂的 Agent 可以自己跑 `ruff check` 拿到同类反馈
   （`agent_self_tool_runs.ruff` 逐 run 记录）。这不是治理污染，但是**归因混淆项**。
4. 模型自身对"仓库里有没有治理"的隐式推断无法屏蔽；只能靠随机化与交错去平衡，**不能消除**。

### 4.6 自举路线的证伪记录（**保留，不删**）

这条不是"我们没选它"，是"**实测证明它不可比**"。三条证据都留在这里，供后来者不要重走：

| # | 证据 | 命令 / 数字 | 它证伪了什么 |
| --- | --- | --- | --- |
| 1 | 净化打坏 oracle | `pytest --collect-only -q`：原始归档树 **2136 / 0 errors** → 删 6 条路径后 **1832 / 12 errors** | "在本仓上关掉治理还能用仓库自带测试判成败" |
| 2 | 净化不干净且不可能干净 | 684 个文本文件里 **176** 个仍含 `(SEC\|STYLE\|DOC\|ARCH\|TESTING)-\d{3}`；`tests` 贡献 142（`tests/fixtures` 96） | "删掉 6 条路径 = 控制臂读不到规则" |
| 3 | `clone + git rm` 路线另有洞（redteam 实测） | 净化后 `git show HEAD:policies/<ID>.yaml` **仍读得到** | "用 clone 再删文件就能去掉历史里的规则" |

**结论**：在本仓上自举时，**oracle 与 treatment 抢同一批文件**（`tests/**` 与 `validation/**`），
这不是"净化需要更狠"，是**目标树 = 处理**。裁定见 §4 开头的裁定框。

---

## 5 任务集

### 5.1 要求与**交付状态**（task-14 已交付，2026-10-07）

**需求方（本节）冻结的四条**：外部 oracle 且标签不来自平台（R1）；
`FAIL_TO_PASS` / `PASS_TO_PASS` 给**测试 node id** 且在基线树实测（前者全红、后者全绿）；
登记 `url / revision / license / license_source / tier / visibility`；
任务不得涉及本项目的治理面（否则 treatment 的规则就是题面）。

**已交付**：`tools/ab_tasks.py`（`--fetch/--list/--oracle/--baseline/--probe/--verify-oracle/--run-oracle/--record-lock/--verify`）、
锁 `evaluation/ab/tasks.lock.json`（`schema_version 1`，`datasets` + `baselines` 两段；`--verify` 实测 `ok=true / problems=[]`）、
文档 `testing/ab/task-sets.md`。**字段名**（值一律以 lock 为准，本协议**不复制任何值**——避免第二份真相）：

| 组 | 字段 |
| --- | --- |
| 身份 | `task_id` / `source{dataset, revision, license, language}` |
| 基线 | `baseline{repo_url, repo_revision, base_tree_ref{url, sha256, bytes}, task_statement_ref, task_statement_sha256}` |
| oracle | `oracle{kind, fail_to_pass[], pass_to_pass[], collection_ok_on_base, needs_deps[], runtime_s, test_select_style}` |
| 成本 | `cost{bytes_download, seconds_setup, seconds_oracle_run}` |
| 拒收 | `reject{rejected, reason}`（`no_oracle` / `unrunnable_local` / `needs_install` / `gated` / `too_big` / `license_unverified`） |
| **实测证据** | `measured{fail_to_pass_all_red, pass_to_pass_all_green, fail_to_pass_total, fail_to_pass_red, pass_to_pass_total, pass_to_pass_green, pass_to_pass_red, collected_on_base, collection_exit_code, problems[]}` |

**我方对交付的三条回应**：

1. **`test_select_style` 的第三取值 `by_keyword` 接受**。它是载荷枚举的扩展，本协议不写死该枚举，
   只要求取值来源可读；**但**：`by_keyword` 的选择面（`-k` 是子串匹配）**必须**与 `collected_on_base`
   一起报，否则"选了几条"不可复核。
2. **node id 现算（collect-only → 唯一命中才采用，多命中/零命中进 `reject(no_oracle)`）接受，且比我原来的要求更严**——
   它把"照抄上游 FAIL_TO_PASS"这个快路径堵死了，正是 R1 想要的方向。
3. **我要求加的两个字段已补齐（2026-10-07，task-14 交付；我本人复核过）**：
   - `baseline_source ∈ {fresh_extract, reused, not_extracted}`：报**本次调用**真实发生了什么；
     `source.json` 记**首次解压**（`fresh_extract` + `extracted_at`）；**老记录没有该字段写 `unknown`，不 backfill**。
     实测样例：`sympy__sympy-22456` 本次 `baseline_source=reused`、`recorded_source=unknown`。
   - `verify_scope ∈ {lock_only, lock_and_bytes}` + `upstream_recheck: false`。
     **我本人复核（§12.1 第 13 行）**：`python tools/ab_tasks.py --verify` → `OK (verify_scope=lock_and_bytes, upstream_recheck=false)`，exit 0。
   - 附带要求照做：`measured` 现在同时有 `select_style` / `selected_total` / `collected_on_base` ⇒ `by_keyword` 的**选择面与收集面一起报**，选了几条可复核。
   **这两个字段是"如实报"，不是"消除限制"**——它们带来的三条残余限制必须一起写进读数：
   - `reused` + `recorded_source=unknown` ⇒ **那次首次解压是不是 fresh，查不出来**（本条只保证"本次没重新解压"）；
   - `upstream_recheck: false` ⇒ **上游 force-push / 重打 tag 本地查不出来**，只能靠重跑 `--baseline`；
     锁防的是"本地被改"，**不防"上游被改写"**——这两件事必须分开说；
   - `not_extracted` 是合法取值：**"没解压"不等于"解压失败"**，读数里不许合并。

### 5.2 两档规模

| 档 | 组成 | 规模 | 能回答什么 |
| --- | --- | --- | --- |
| **试点档** `PILOT` | 12 任务 × 3 臂 × 1 rep | **36 runs** | 只回答"协议跑得通吗"（净化、oracle、采集、字段齐不齐）。**功效严重不足，不许出价值结论** |
| **判定档** `DECIDE` | 48 任务 × 3 臂 × 1 rep | **144 runs** | 主结局 `U1` 在 25pp 差上有 80% 功效（§6.2） |
| **全量档** `FULL` | 96 任务 × 3 臂 × 2 reps | **576 runs** | 加测任务内重复方差与异质性；用于外推 |

- **试点档的 MDE**：n = 12 时，在 `p_d ≈ 0.30` 的假设下可检出的成功率差约 **44 个百分点**
  （§6.2 公式反解）——而治理在真实项目上不可能有 44pp 的效应。**所以试点档跑完必须写"未达功效"。**
- **【实测·task-14 交付】当前可用任务数 = 2**：`sympy__sympy-22456`、`sympy__sympy-22714`
  （基线树 F2P 全红 / P2P 全绿，实测）。另 2 个 sympy 任务被拒（`14711 = no_oracle`、
  `19637 = unrunnable_local`：P2P 39/40）；requests / pytest / matplotlib / flask 四个在 collect 阶段就红（`needs_install`）。
  ⇒ **判定档（48 任务）与全量档（96 任务）当前不可达**：2 个任务连试点档的 12 个都凑不满。
  **因此本轮结论必须先写成一句**：*"按当前任务集，A/B 只能做可行性试点；主结局 `U1` 的预注册功效在现有任务数下不可能达到。"*
  扩展任务数的成本不是"再下 500 条"——是**为 12 个仓库各钉死一套可复现的环境**（那是独立的一次安装动作，本机 PyPI 不可达 ⇒ 现在做不到）。
- **任务抽样**：从通过登记检查的池子里按`层级/规模`分层随机抽；抽样框与随机种子写进门槛文件。
  **可用池只有 2 个任务时，随机化退化为"全取"**——如实写，不许把"2 个都跑了"讲成"抽样"。
- 成本、字节数、许可原文、可运行性由 task-14 的 `evaluation/ab/tasks.lock.json` 提供，
  **协议只引用 lock 的 revision，不复制任何字段**（避免第二份真相）。

### 5.3 候选来源（**引用登记，本次未核验**）

| 候选 | 为什么是它 | 状态 |
| --- | --- | --- |
| SWE-bench Verified（`princeton-nlp/SWE-bench_Verified`，500 条人核验子集） | 有 `FAIL_TO_PASS`/`PASS_TO_PASS` 的现成 oracle，与本节要求同构 | 【上游登记，未核验】：许可、可运行性、gated 与否由 task-14 核验并落 lock |
| BugsInPy / Defects4J | buggy-fixed 配对，天然有"修复前失败 / 修复后通过" | 同上；注意它们多数是**真实仓库**，任务规模与依赖安装成本要实测 |
| **自建 fixture 任务集**（无网回退） | 从**本仓之外的**固定夹具项目出发，用 `git archive` 建树，`FAIL_TO_PASS` 由本地 pytest 实测产生 | **本条是本机无网时唯一能跑的路**；代价是外部有效性弱（不是真实项目的历史缺陷） |

**选择纪律**：优先选**有现成 `FAIL_TO_PASS`**的（省掉"造 oracle"这一整个风险面）；
自建 fixture 只在"联网任务集全部不可用/不可运行"时启用，且**必须在结论里写明外部有效性受限**。
三者都不许用本仓库当目标树（§4.1 的实测矛盾）。

---

## 6 配对设计、随机化、功效与预注册

### 6.1 配对与随机化

- **配对单位** = 任务。同一任务在三臂上各跑一次，**同一份基线树归档**（比字节相同：`base_tree_sha256`）。
- **臂顺序随机化**：每个任务内三臂的执行顺序**独立随机置换**（3! = 6 种等概率）。
- **时间块**：把所有 (task × arm) 单元切成 `block_id`，块内**交错两/三臂**，块大小固定（例如 6 个单元）。
  **同一 block 内出现两个不同的 `model.revision_id` ⇒ 该 block 作废**（§7）。
- **温度 / 种子**：`temperature` 与 `top_p` 三臂**同一组值**并写进 run 记录；`seed` 若适配器支持则同任务三臂同种子，
  不支持就记 `null`（**不许**写一个没用的假种子）。
- **重试上限**：每任务写动作尝试上限固定（例如 40），三臂相同；到达上限 = 该 run 记为 `task_failed(上限)`，
  并把上限击穿次数单列——否则"被门禁挡到放弃"会被读成"任务本来就难"。

### 6.2 功效（公式先写下来，参数跑前标定）

**主结局 `U1` 是配对二元**（同任务两臂成功/失败），用 McNemar。
`p01` = 仅 treatment 成功的概率，`p10` = 仅 control 成功的概率，`p_d = p01 + p10`：

```text
n_pairs = [ z_{1-α/2}·√p_d + z_{1-β}·√(p_d − (p01−p10)²) ]² / (p01 − p10)²
```

取 α = 0.05 双侧、power = 0.80（`z` = 1.9600 / 0.8416），得【提案】：

| 想测出的成功率差 | 假设 `(p01, p10)` | 需要配对任务数 n |
| --- | --- | --- |
| 25 pp | (0.30, 0.05) | **42** |
| 20 pp | (0.22, 0.02) | 45 |
| 15 pp | (0.17, 0.02) | 64 |
| 10 pp | (0.12, 0.02) | 108 |

⇒ `DECIDE` 档取 **n = 48**（对 25pp 有富余，对 20pp 勉强）。

**连续结局**（`NORM_LINES` 密度、`E2` 墙钟）用配对差：`n = 7.849 / d_z²`
（`d_z` = 配对差的标准化效应量）。`d_z` = 0.5 → **32**；0.4 → 50；0.3 → 88。

**区间**：比例一律 Wilson；连续量用 bootstrap（≥ 10,000 次，固定种子），报 95% 区间。
**样本不足就写"样本不足"**，不许给点估计假装有结论。

### 6.3 多重比较与主/次结局（预注册）

- **主结局只有一个**：`U1`（冻结测试 oracle）的 **`enforced − off`**。单次检验，不校正，α = 0.05 双侧。
- **次结局族**：`{``NORM_LINES``,``S1``,``S2``,``P1``,``E2``,``A1``}`` × {`enforced−off`,`enforced−advisory`,`advisory−off`}`，
  用 **Holm** 控制族错误率，α = 0.05。
- **描述性（无门槛、不进结论）**：`NORM_FILES`/`NORM_TREE`、`U2`−`U1`、`E1`/`E3`/`E4`、`A2`/`A3`/`A4`、`unreconstructible`/`unverifiable` 计数。
- **不许**把描述性读数事后升成主结局；要升必须先 `--record` 重记基线并递增评测集版本（R3）。

---

## 7 证伪条件与排除优先级（先于跑，写死）

### 7.1 排除优先级（从高到低，逐级生效）

| 级 | 条件 | 处置 |
| --- | --- | --- |
| 1 | `task_invalid` / `baseline_unavailable` | 该 task **全部臂**作废 |
| 2 | 污染：`leak_assertion_failed` / `feedback_text_mismatch` | 该 run 作废；**任一臂 > 20% run 作废 → 整个实验作废** |
| 3 | `environment_unavailable`（含本机 ACL / `INTERNALERROR`） | 该 run 排除，**不计成败** |
| 4 | `model_revision_drift`（同一 block 内 revision 不一致） | 该 block 作废 |
| 5 | `infrastructure_failure` | **逐事件**排除，不整 run 排除；只报计数 |
| 6 | 功效不足（n < 预注册下限，或 CI 宽于 ±2×MDE） | 结论写 **"未达功效"** |
| 7 | 以上全不触发 | 才允许判"有效"或"负价值" |

**第 6 级优先于"负价值"**：功效不足时**不许**写"没坏处"，也不许写"是负价值"。

### 7.2 证伪条件（判据写死）

设 `MDE_U = 0.10`（成功率 10 个百分点）、`MDE_N = ``NORM_LINES`` 的 0.2 SD【提案】。

| 记 | 条件 | 结论 |
| --- | --- | --- |
| **F1 负价值** | `ΔU1(enforced−off)` 的 95% CI **完全落在** `(−∞, −MDE_U)` **且** `NORM_LINES` 的 CI **落在 ±MDE_N 内** | **该场景下治理是负价值**（成功率掉了，规范性没换来） |
| **F2 未达功效** | n < 42，或任一主/次结局的 CI 宽于 ±2×MDE | 写 **"未达功效"**，不给方向性结论 |
| **F3 门禁无净效应** | `ΔU1(enforced−advisory)` 的 CI 落在 ±MDE_U 内 | 门禁那一半可以去掉，保留 `advisory` |
| **F4 反馈无净效应** | `ΔU1(advisory−off)` 的 CI 落在 ±MDE_U 内 | 反馈那一半可以去掉（只留门禁） |
| **F5 污染失控** | 任一臂 run 作废率 > 20% | 整个实验作废，先修净化 |
| **F6 精确量失效** | `P1` 分母 < 20 **或** `unverifiable` 占比 > 30% | `精确` 写 `(TP, FP, unreconstructible, unverifiable)` **四个计数**，**不给比率**（lead 裁定：别硬凑成一个干净精确率）；分母 < 20 时连区间都不给。**补充（redteam 实测，必做）**：无论分母多大，`precision` 都必须与 **`max_achievable_precision`（阳性对照上界）并列呈现**——已知上界为 0.0 的场合给出"精确率 1.0"是**误导**，不是读数 |
| **F7 可游戏面** | `U2 − U1 > 0` 的任务占比 > 20% | 成功率读数不可信，只报 `U1` |
| **F8 后信号行为** | 被拦后**没有任何**后续行为记录（`retry_of` 全空） | 反馈回路**没有被测到**；`Δ_gate` 只能读成"门禁把脏内容挡在树外"，**不许**读成"Agent 学会了" |

**F8 是给"把 `Δ_gate` 读成学习效应"准备的**：门禁效应有两种机制——"挡住脏内容"（树的差别）
与"Agent 因此改了做法"（行为的差别）。只有 `retry_of` 有数据时，第二种才可读。

---

## 8 落点与数据文件（与 `evaluation/thresholds.yaml` 同型）

**本协议不写这些文件**（写域只有本文件），以下是**交接项**：

| 落点【提案】 | 内容 | 约束 |
| --- | --- | --- |
| `evaluation/ab/thresholds.yaml` | 预注册：`MDE_U`/`MDE_N`、`n_pairs` 下限、`α/power`、模拟 `(p01,p10)`、`COMMON` 公共支撑集、`FROZEN(t)`、固定事件 sha256、`leak_assertions` 阈值、`max_exclusion_rate` | 自带 `schema_id` + `version`；**跑之前**写 |
| `evaluation/ab/tasks.lock.json` | 任务集：url / revision / license / `FAIL_TO_PASS` / `PASS_TO_PASS` / 字节数（**task-14 写域**） | 逐文件 sha256；`--verify` 能发现漂移 |
| `evaluation/results/ab-<revision>.json` | 读数：`schema_version` + `reading_context`（哪棵树 / 哪个环境 / 哪套声明）+ 每臂每结局的 `(分子, 分母, 区间)` + 排除计数 | 与 `fidelity-<revision>.json` 同型 |
| `.tmp/ab-runs/<run_id>/run.json` | 原始 run 记录（§3.2） | **不提交**（含用户代码原文） |

**`--record` 语义**（与 `tools/retrieval_eval.py` / `governance_eval.py` 同型）：
行为有意变化（换仪器配置、改任务集、改净化清单、改 `isolation_level`）时**显式 `--record` 重记基线**，
旧基线留在同目录作历史；**禁止**为了让结论好看而调参。
**注意**：`evaluation/thresholds.yaml` 是**严格模型**（未知键报错），加 `ab:` 段属于改这份载荷本身，
必须按 AGENTS 第 55 条递增它自己的 `schema_id`/`version`，或在 `evaluation/ab/` 下开**新的一份**载荷
（本协议建议后者：不把两套预注册混在一个轴里）。

---

## 9 成本与"先做哪一步最省"

### 9.1 已实测的单位成本

| 动作 | 实测 | 命令 |
| --- | --- | --- |
| 取基线树（归档） | 834 个跟踪文件 → 归档 12,195,840 B / 1046 条目，秒级 | `git archive --format=tar HEAD -o <out>` |
| 解包 | 762 个文件，秒级 | `tar -xf <tar> -C <dir>` |
| pytest **收集**（原始树） | 6.11 s / 2136 条 | `python -m pytest tests --collect-only -q` |
| pytest **收集**（净化树） | 6.32 s / 1832 条 + 12 errors | 同上 |
| 内容级泄漏扫描 | 684 文件，秒级 | §4.3 L3 |

### 9.2 尚未标定的单位成本（试点档必须先量）

**一次 Agent 会话的墙钟与 token（`c_run`）本机未测**——它取决于 Agent harness，本协议**不估**。
试点档的任务之一就是把 `c_run` 量出来（r3 的试点给首读）。总量公式：

```text
总成本 ≈ N_task × N_arm × N_rep × (c_run + c_oracle + c_scan)
       + N_task × N_rep × c_tree      # 每 run 一棵新树
       + N_task × N_arm × N_rep × c_snapshot_on_block   # 只有被拦时才有
```

### 9.3 先做哪一步最省（顺序写死）

1. **固化 oracle 与 `COMMON`**（离线、秒级）：跑 `--collect-only` 与 `FAIL_TO_PASS/PASS_TO_PASS` 实测，
   把不可收集/不满足的任务直接 `reject`。**这一步不做，后面全白跑。**
2. **固化净化与断言**（离线、秒级）：§4.3 的 L1–L5 在**两臂**各跑一遍，证明断言能红也能绿。
3. **`PILOT` 试点档**（36 runs）：只验流程与字段，**明确写"未达功效"**。
4. **量 `c_run`**，据此决定 `DECIDE`（144 runs）还是先缩规模。
5. `DECIDE` → 主结局；`FULL` 只在有外推需求时做。

---

## 10 这份协议不能证明什么（反面清单）

1. **不能证明"治理对代码质量普遍有效"**：结论只在被抽到的任务集与目标树上成立，**外推要另做**。
2. **不能识别共同盲区**：独立仪器与平台的证据工具共用 ruff 0.14.13（§1.5）。语义级安全问题、
   复杂度、死代码、依赖 CVE 本机**没有仪器**——一律 `unavailable`，**不许**用"没报"当"没有"。
3. **不能用 `Δ_total` 代替分解**：没跑 §2.4 安慰剂臂时，`advisory − off` 里混着"多收一段文本"的效应，
   **必须写"未分解出剂量/token 效应"**。
4. **不能把 `A3`/`A4`（覆盖率 / bypass）当成绩**：它们是操纵检查，不是价值结局。
5. **不能把"被拦下"读成"防住了"**：拦下的动作要进反事实（`P1`）才知道拦得对不对；
   `fail_closed` 与 `infrastructure_failure` 必须与 `policy_violation` 分开数。
6. **不能把 `U1` 当成不可游戏**：它能挡住"删测试 / 加 skip / 改测试"，**挡不住**
   "把测试重写成断言错误行为"与"新文件遮蔽被测模块"（r3 提出的两条，本协议**不覆盖**）。
7. **不能证明 hook 一定没挂**：L4 只是行为探针，不是可达性证明；`isolation_level` 必须如实写。
8. **不能在 n < 42 时给方向性结论**（F2）。**"没检出差别" ≠ "没坏处"。**
9. **不能跨 `isolation_level` / 跨仪器配置 / 跨任务集直接比数字**（`reading_context` 不同）。
10. **不能用本仓库当目标树**（自举）：oracle 与 treatment 抢同一批文件、净化后 176/684 文本文件仍带规则 ID、
    clone+`git rm` 后历史里仍读得到规则——三条都实测过（§4.1 / §4.6）。这是**留档的证伪**，不是偏好。
11. **引用别人的读数必须带"时间戳 + 大小 + sha256"**：本次同一份文件在 5 分钟内出现过至少 4 个版本
    （92,877 → 121,813 → 126,545 → 127,102 B），**两次"更正"分别过期**——我的和 redteam 的都过期了。
    **引用同伴的观测不等于自己测过**；写进载荷前必须给"谁、何时、多大、什么 sha256"，或自己重跑一遍。
    并行协作下**"测得对"是有保质期的**，这条纪律比任何一次具体读数都重要（§12.2 G14）。
    **四条可操作写法**（后半由 task-15 补充，我方采纳）：
    - 记录必须同时留 **size + sha256 + mtime**：只给 size+hash 时，"两次更正哪个过期"**读不出来**；
    - **能自指的只有工具**：工具哈希写进文档是安全的（工具不是文档）；
    - **文档 / 载荷 / 报告这类"自己包含自己"的东西，哈希一律落外部留档**（lead 的冻结记录、CI 产物或提交信息）；
    - **校验必须重算，不许转抄**——"我看了你的哈希"不构成核对。

---

## 11 交流记录

> 规则：谁提了什么、我接受还是反驳、**理由**、最终怎么定；**未解决的分歧保留并写明**。
> 与本协议相关的往来（2026-10-07）：

### 11.1 lead → 全体（hard fact）

- **提出**：`pip download bandit --no-deps` 本机跑了 18 分钟零字节输出 → **PyPI 实际不可用**；
  仪器不得依赖任何新安装；协议中依赖"独立扫描器"的结局变量必须给无新依赖的替代并写明弱点；
  红队要把"仪器同源且无法消除"写成必须保留的结论局限。
- **处置**：**接受，且已经是我起草时的前提**。落地为 §1.5「同源等级表」、`S3 = unavailable`、
  §10 反面清单第 2 条。补充一条我自己量到的：仪器不独立于**底层 linter**，但**独立于策略层**——
  这两件事必须在每一条结论里分开说。

### 11.2 lead → ab-protocol（三条字段）

- **提出**：`blocked_edits[]`、`write_actions_total`+`write_actions_governed`、`human_interventions`
  不是可选项；写死名字/类型/产生方式并回消息；不同意就写理由与替代来源。
- **处置**：**全部接受**，写进 §3.2/§3.3。另加两条：`block_class` 三分（防"把平台故障读成治理成本"）
  与 `human_interventions_detail[]`（只给总数查不出"是审批还是人工改代码"）。
  **一处补充理由**：`human_interventions` 必须允许 `null`——`0` 是读数、`null` 是没采集到，两者不许长一样。

### 11.3 ab-instruments → ab-protocol（接口回执：4 接受 / 3 反驳 / 1 硬缺口）

- **对方接受**：三臂定义、"advisory 存在是为了拆出 `enforced−advisory`"、
  usability 三态 `{ok, red, environment_unavailable}`（`INTERNALERROR` 归环境）、security 不许用平台读数顶替、
  独立性两块布尔要**在每个量里各写一次**。
- **对方反驳**：① 工具名只能是 `tools/ab_measure.py`（写域约束）；② 计数口径必须**两个都报**
  （`counts_by_code_changed` 行级为主 + `counts_by_code_touched_files` 整文件），只报一个则两臂不可比；
  ③ `reading_context.run` 与"逐字节相同"冲突，改为 `--deterministic` 下才承诺。
- **我方回应**：**三条全部接受**（§1.4 三个 `tree_scope` 分开、§3.2 计数分列、§6.3 描述性读数不进门槛）。
  对其反驳②追加一条：**差额本身是要读出来的量**，不许合并。
- **对方硬缺口（3 条）**：给不出"被拦下的那次编辑是什么"→ 精确只能报 unavailable；
  给不出"全部写动作"→ 覆盖率没有分母；给不出人类触点 → 全自动化无法测。
- **我方回应**：**全部接受并写死字段**（§3.3 `BlockedEdit`、§3.2 `write_actions_*` / `human_interventions*`）。
  **一处反驳转向**：对方要求 `replacement`/diff 二者之一即可，我加**前置树快照是同等义务**——
  没有 `trees/on_block/<action_id>/` 就构造不出反事实，`blocked_edits` 给了也没用。
- **未解决的分歧（保留）**：对方称"精确这个量只能报 unavailable"是**在字段缺失条件下**成立的。
  我坚持：字段补齐后**仍可能大面积 `unreconstructible`**（`old_string` 非唯一、`write` 类动作无前置内容），
  因此 `P1` 的现实形态很可能是 **`(TP, FP, unreconstructible, unverifiable)` 四个计数 + 一个下界**，
  而不是一个干净的精确率。**这条分歧不靠讨论解决，靠试点档的首读解决**（F6）。

### 11.4 r3-applicability（= ab-redteam）→ ab-protocol（8 条判决）

- **对方判"真能证伪"**：1（后信号行为）、3、4（检查面要扩）、5、8。
  **接受**。1 → `retry_of`/`retries_after_block`+`block_class`；4 → §4.2 扩到七条隔离项；
  8 → §7.2 **F8**（没有后信号记录 ⇒ 反馈回路没被测到，`Δ_gate` 不许读成学习效应）。
- **对方判"看起来严格但测不出来"** 2（负价值条件）、6（测试 oracle）、7（顺序效应）：
  - **2 接受，是我的错**：把"CI 含 0"当负价值判据 = 把"未拒绝"当"无效应"，与"未达功效"**互相打架**。
    已改成"CI 完全落在 `(−∞,−MDE)` 内"且**排除优先级第 6 级（功效不足）高于第 7 级（负价值）**（§7.1）。
  - **6 接受其主结论**：`U1` = **冻结测试恢复重跑**升为**主结局**，`U2` 原样成功率降为次结局，两者都报、
    差值单列（§1.4）。**但保留一处反驳**：对方列的两条绕过面（重写成断言错误行为、新文件遮蔽被测模块）
    `U1` **也挡不住**——已写进 §10 第 6 条，**不声称"U1 不可游戏"**。
  - **7 接受**：每 `(task, replicate)` 全新工作树 + 全新会话（§4.2 P6）；顺序随机化保留，
    但顺序效应**只报 CI、不当门禁**（小 N 下"没检出"不写）。
- **对方指出"我漏掉的"两条**：
  - **失败模式不对称**（enforced 臂有基础设施型阻断，off 臂没有）→ **接受**，`block_class` 三分 + 排除第 5 级，
    并在结论旁注明这个不对称。
  - **全局 `.dsh` home 与 git 历史** → `.dsh` **接受**（§4.3 L5 + L4 行为探针）；
    **git 历史一处反驳**：对方实测的是 **clone + `git rm` 路线**。我的净化原语是 `git archive`，
    本次实测解包树 `Test-Path .git` = **False**、`git ls-files .tmp` = **0** ⇒ 该泄漏在我这条路上**结构性不存在**。
    处理：把它的攻击**升级成断言** `vcs_dir_absent`，并把"禁止 clone+rm 净化"写进 §4.2 反面清单。
- **对方要的三件冻结**：① 臂定义表（§2.1）② 结局变量表（§1.4）③ 排除优先级（§7.1）——**已给，见回执**。
- **未解决的分歧（保留）**：`COMMON`（两棵树都必须能 collect 且绿的公共支撑集）会把治理面自己的
  12 个测试模块（约 304 条）从可用性读数里**删掉**。我认为"必须删，否则两臂不可比"；
  **lead 已裁（2026-10-07）**：两个数都报——`U1不含`（主结局，钉在 `COMMON` 上）与
  `U1含`（描述量，`COMMON ∪ 治理面模块`），并写明差额来自哪几个模块、差多少条（§1.4）。
  理由：治理面模块在控制臂里**不可观测**（依赖 `validation/validators.yaml`，收集期就失败），
  所以它进不了主结局，但**藏着不报**是选择性报告。

### 11.5 eval-extend → ab-protocol（误派更正）

- **提出**：此前发给我与 ab-instruments 的"接口冻结 v1"是**误派**草稿，不是交付；task-14 负责任务集，
  会提供字段清单与 lock（`evaluation/ab/tasks.lock.json`）。
- **我方回应**：**接受更正**；草稿中采用的部分与推翻的部分已在 §11.3 前的消息里逐条说明。
  已向它发去**冻结的任务集字段需求**（task_id / repo_revision / `fail_to_pass`+`pass_to_pass` 的 node id /
  基线实测红绿 / `reject.reason` 枚举 / 许可 / 成本），并要求**跑前给出 `collection_ok_on_base` 的实测数字**
  ——没有它我冻不了 `COMMON`（§4.1 实测 1 就是理由）。
- **未解决的分歧**：无（分工正交）。

### 11.6 我自己提给 redteam、请它攻击的两条

1. **`COMMON` 会不会把治理的价值从可用性读数里删掉**（§11.4 末）。
2. **"6 条路径净化"这个需求本身被实测否掉**（§4.1：176/684 文本文件仍带规则 ID；
   删 6 条路径只掉 65 个文件、却让 12 个测试模块收集失败）——请它攻击我给出的替代读法
   （目标树改为外部仓库 + 6 条路径降级为环境断言）。

### 11.7 lead → ab-protocol（**裁定：驳回自举，采纳外部目标树**）

- **lead 裁定**（2026-10-07）：① 驳回"自举在本仓上做 A/B"，采纳 §4.1 的读法——
  **任务树 = 外部仓库 checkout，平台产物一个字节都不进去；平台从工作树之外的独立检出运行**；
  ② 原净化清单**降级为环境断言**（L1–L5 + 运行时 `[policy]` 标记探针）；
  ③ `vcs_dir_absent` **改语义**：外部任务树里没有 `.git` 不是必要条件，
  真正的断言是「任务树里不存在平台产物」与「平台检出不在任务树内」（已落 §4.2 的 P8、§4.3 的 L2）；
  ④ §4.6 的 clone+`git rm` 证据**照样保留**，作为自举路线的**证伪记录**（已落 §4.6 / §10 第 10 条）；
  ⑤ 两处保留分歧都接受，但**两个数都报**：`P1` 可以是四个计数（§7.2 F6）、
  `COMMON` 要报"含/不含治理面模块"两个可用性读数（§1.4）。
- **追加理由（lead）**：自举会让 R1 以更深形态复活（平台在自己的代码上量自己的规则）；
  `validation/validators.yaml` 同时是治理声明与 12 个测试模块的依赖 = **设计错误的信号**；
  价值主张本来就是"Agent 开发过程中装上治理"，治理对象不是本仓。
- **我方处置**：**全部接受，已逐条落进 §4 裁定框 / §4.2 P8 / §4.3 L2 / §4.6 / §7.2 F6 / §1.4 / §10**；
  裁定结果已回执给 `ab-instruments` 与 `r3-applicability`（它们的设计依赖这一条）。
- **我方落地的两处"裁定后推论"**（如实记下，供 lead 复核）：
  ① `vcs_dir_absent` 改语义后，§4.3 的 L2 从"断言任务树没有 `.git`"改成"断言平台检出不与任务树相交"
     并写明 `.git` **不是**泄漏判据；自举路线的"`.git` 必须不存在"降级为 §4.6 的历史结论。
  ② "`U1含` / `U1不含` 两个数都报"在**外部目标树**设计下会**退化**：任务树里没有平台产物 ⇒ 两臂测试集合相同 ⇒ `Δ = ∅`。
     按裁定精神，我把 `U1含` 写成 **`not_applicable` + 原因**，并把这条规则保留为**兜底检测**
     （一旦任务树里出现只在某一臂可收集的模块，`Δ` 立刻非空、必须单列）。**这不是把 lead 的要求打折**——
     是"要求原本针对自举设计，而自举已被驳回"的直接后果；如果 lead 要的是别的读法，请指出，我改。
- **未解决的分歧**：无。

### 11.8 task-14（eval-extend）→ ab-protocol（任务集已交付 + 三条限制）

- **对方交付**：`tools/ab_tasks.py`、`evaluation/ab/tasks.lock.json`（`--verify` 实测 `ok=true / problems=[]`）、
  `testing/ab/task-sets.md`，并给出逐字段真实样例（`sympy__sympy-22456`）。
- **三条限制（对方自述，我方全部接受）**：
  1. **只有 2 个任务通过全判据**，另 2 个 sympy 被拒（`no_oracle` / `unrunnable_local`），
     四个仓库 collect 阶段就红（`needs_install`）——"每个任务都实测过"**只在已测子集成立**；
  2. **node id 要现算**：上游 `FAIL_TO_PASS` 是裸函数名（`test_String`），必须 `collect-only` 拿真实 node id、
     **唯一命中才采用**，多命中/零命中进 `reject(no_oracle)`；
  3. `test_select_style` 新增第三取值 **`by_keyword`**。
- **我方判决**：**第 2、3 条接受**（第 2 条比我原来的要求更严，正是 R1 要的方向；第 3 条是载荷枚举扩展，
  本协议不写死该枚举）。**第 1 条不是"接受/反驳"问题，是结论**：它把 §5.2 的判定档直接判死（见下）。
- **我方向对方提的两条要求（未被拒，但到本轮结束时未见到落地）**：
  - `--baseline` 命中已有目录时**复用、不重新校验** ⇒ 必须带 `baseline_source ∈ {fresh_extract, reused}`；
  - `--verify` **只查来源记录** ⇒ 必须带 `verify_scope ∈ {lock_only, lock_and_bytes}`。
  理由：不写这两个字段，"这次真的解开了归档"与"上次留下的目录还在"长得一样，而后者可能是别的 revision
  （与 AGENTS 第 12 条"漂移不许静默"同一条纪律）。**未补之前本协议不引用该次读数。**
- **后续（同日，第二轮）**：对方补齐了 `baseline_source`（含 `not_extracted`）与
  `verify_scope` + `upstream_recheck`，并让 `measured` 同时报 `select_style`/`selected_total`/`collected_on_base`。
  **我按自己写的反面清单第 11 条复核了它**：`python tools/ab_tasks.py --verify` → `OK (verify_scope=lock_and_bytes, upstream_recheck=false)`，exit 0（§12.1 第 13 行）——
  **我不是照抄它的说法，是重跑了一遍**。已落 §5.1 与 §12.2 G12（关闭），并把三条残余限制写进读数：
  ① `reused`+`recorded_source=unknown` 查不出首次是否 fresh；② `upstream_recheck:false` ⇒ **锁不防上游改写**；
  ③ `not_extracted ≠ 解压失败`。
- **未解决的分歧**：无（对方已如实自述限制、未 backfill 老记录，也没有回填）。

### 11.9 r3-applicability → ab-protocol（我问的三条，逐条答复）

**① L4 行为探针 → 对方判"未标定"，必须补正向对照。我方全盘接受。**
三条理由我认同：(i) 我自己的"hook 会打 `[policy]`"证据来自 `--self-check`，
**正常 PreToolUse 是否也打标记我没有验证过** ⇒ 探针的**敏感性没有读数**；
(ii) harness 只收 Agent stdio 时 hook 子进程 stderr 会被吞 ⇒ **假阴性**（控制臂被误判干净）；
(iii) 标记不带 request_id/trace 时，别的进程（例如测量工具自己跑 `--self-check`）打出的标记会造成**假阳性**。
→ 已落 §4.3：**正向对照**（故意挂 hook → 必须 true；摘掉 → false；两段读数都落盘）、
两个失效模式的消法、以及"做不到就写**未标定**，不许当结论用"。

**② `U1含` / `U1不含` 的差额 → 对方判"不该报差值"，我方接受并加严。**
理由：`Δ` 里的模块**只在 treatment 臂存在**（off 臂收集期就失败），差额由处理本身决定，不是结局。
→ 已落 §1.4：**两个数都报**（避免选择性报告），但 **`U1含` 不许跨臂相减**；
收不齐的那一臂记 `unavailable`——**不是 0、也不是 fail**。
这与 lead 的"两个数都报 + 写明差在哪 12 个模块"是相容的：报的是**模块清单**，不是**处理效应**。

**③ P8 的证伪 → 对方给出更强的一条，我方采纳。**
**【对方实测】**在树里删光 13 条平台路径后，以该树为 cwd 跑平台**仍加载 43 条规则**
（`rule_set_hash = sha256:50202675…`），两种 `PYTHONPATH` 都复现；
机制是 `src/policy/check.py:165-172` 的 `repo_root()` **从模块位置向上回溯**。
对方诚实标注：本机给不出文件系统级隔离 ⇒ 上限是 `code_path_verified`，**不是** `fs_isolated`。
→ 已落 §4.3：三档 `isolation_level` + P8 的三条可证伪判据（打印 `repo_root()` 与规则根 / 断言 `rule_set_hash` /
只认显式 `--rules` 且不传必须失败），并把"把平台检出搬进任务树 → 三条必须变红"写成它的"修复前会红"证明。
**这条比我原来的路径前缀断言强，且它同时解释了我 §4.1 实测 1 的机制**：净化掉目录并不能让平台失去规则。

**④ 对方附带的一条观测，我复现后更正了它**：对方称 `tools/ab_measure.py` "92,877 B、仍无入口点、
跑它 exit 0 + 零输出 + 无产物"。**我实测（§12.1 第 11/12 行）：文件已 121,813 B、有 `__main__` 守卫，
无参运行 exit 2 并打印 `ab_measure: 缺 --tree <DIR>（或 --self-check）`；`--self-check` exit 1、
载荷 `self_check.all_passed=false`。** 对方的观测在写它的时候大概是对的，**现在过期了**——
这条更正写进 §12.2 G1，避免协议里留一个陈旧事实（"测不到就写 unavailable"同样适用于**引用别人的读数**）。

- **未解决的分歧**：无。

### 11.10 eval-harness（task-15 臂运行时与净化树）→ ab-protocol：三问答复 + 一处分歧

- **(a) `isolation_level = tree_only`，写进每条 `run.json`，不默认成 `fs_isolated`** → **接受**，与我 §4.3 的三档表一致。
- **(b) L4 行为探针已做正向对照**：跑真实 Hook 并在捕获的 stdout/stderr 里找 `[policy]` 标记；
  控制臂断言 false、treatment 臂断言 true；**实测 off=false / advisory=true / enforced=true，全部 pass**。
  → **接受，且这正是我在 §4.3 写死的"正向对照"要求**（我要求的是"挂上必须 true、摘掉必须 false"，它做的就是这个）。
  **引用纪律**：这是**第三方便读数**，我**没有复跑**（跑它要走 task-15 的闭环脚本，不在我的可跑范围内），
  因此 §4.3 里标注为"第三方便读数，未由我复跑"，并要求复跑时带**时间戳 + 大小 + sha256**（文件在被持续重写，见 §12.2 G14）。
- **(c) `hooks.json` 的 matcher 留空**（匹配全部工具），写法在 `tools/ab_arm.py` 的 `write_hook_configs()`，与 `examples/dsh/hooks.json` 同型。
  → **接受**，这正是我 §4.4/§4 提的硬要求（matcher 留空，否则"新工具绕过门禁"会变成一臂的漏洞而不是处理效应）。
- **对方提出的分歧**："P4（PYTHONPATH/环境变量不含平台配置路径）只在 oracle 与探针上做到；
  treatment 臂的 Hook 本身**必须** import 平台（它就跑在平台检出上），所以进程级隔离在本机不成立；
  口径是'树级隔离成立、进程级不成立'，读数是 `tree_only`，不掩饰。"
  → **我接受它的读数（`tree_only`），但纠正它的归因**：**P4 只约束控制臂**。
  treatment 臂的 Hook 能 import 平台是**处理本身**，不是违反 P4——P4 要挡的是"**控制臂**可以 `import policy`"。
  所以"进程级隔离不成立"的正确说法是：**控制臂的进程级隔离在本机做不到**（因为平台检出在磁盘上可达，见 P5/G13），
  而不是"treatment 臂必须 import 平台所以做不到"。**结论一样，理由不同**；理由是给后来者看的，所以必须写对。
- **对方独立实测且如实记 fail 的一条**：宿主 `.dsh` 接线里有指向本仓与 `policy-hook.plugin.mjs` 的条目
  ⇒ "控制臂在宿主层面没有平台接线"在这台机器上**不成立**。
  **计数口径经过一次三方对齐**：对方先报"26 处"（更窄针脚集下的旧读数），补齐口径后修正为 **67 文件 / 181 次**；
  redteam 的针脚集给 **64 文件 / 222 次**；我的是 **136 行命中**。**三个数字单位不同、结论一致**，
  已落 §4.3 的三方对照表——**这不是分歧，是"分母是什么"必须写清楚**。
  → **完全接受，并升级为协议约束**（§4.3 的 L5 段 + §12.2 新增 G13）：读数里必须分开写
  `tree_isolation` 与 `host_wiring_isolation`；要做到宿主层隔离，控制臂必须跑在**每次 run 独立的 dsh home** 里；
  **做不到就写"本机在此配置下跑不出干净的控制臂"**——这比跑出一个被污染的对照强。**它没有为了让读数好看而放宽，这一点记在这里。**
- **收尾（对方主动办了，我复核过）**：对方算出并报出**冻结哈希**，并说明"文档不能自指，所以文档哈希只在 lead 的留档里"。
  → **我自己重算了一遍**（不转抄）：本地 **2026-10-07T12:29:15Z**，
  `tools/ab_arm.py` = 77,433 B / `sha256:716a59c9c864af41253f0dfbc7f992c71ebde00e8e99d138805b74cd56cfe279`、
  `arm-harness.md` = 20,207 B / `sha256:ffc5d072d146d6b19f5d4452e3552435ebe672110b8d32b521103e21a022551e`，
  **与对方自报逐字符相同**（§12.1 第 16 行）。
  这一步是对**反面清单第 11 条**（引用第三方读数带时间戳 + 大小 + sha256）的第一次正面执行——
  我先前记的 75,858 B / 18,548 B **已经过期**（文件又改了两次），已按新读数覆盖并留痕。
  **它证明这条纪律是可执行的**：不是"谁测得准"，是"说清楚测的是哪一版"。
- **对方的二次复算（我记录为"冻结已确认"）**：对方在同一台机器上重算，得 77,433 B / `716a59c9…`（mtime 12:27:39Z）
  与 20,207 B / `ffc5d072…`（mtime 12:29:02Z），**与我的重算逐字符一致，且 mtime 早于我的测量时刻 12:29:15Z**
  ⇒ 判定为**真实冻结读数，不是转抄**。对方并承诺：**这两个文件本轮不再改动**；若必须改，先重算再报 lead 与我与 r3，
  **绝不静默改一版继续用旧读数**。
  → 我方接受该承诺的**可检验形式**：任何人复核时**重算**即可判断是否被静默改动——
  **承诺之所以可信，不是因为它是承诺，是因为它可被随时证伪。** 这条也写进 §10 第 11 条。
- **对方把"随时可证伪"落成一行命令，我照跑了一遍**：`python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('<path>').read_bytes()).hexdigest())"`。
  我在 **2026-10-07T12:30:13Z** 跑出 `716a59c9…` 与 `ffc5d072…`，**两个都命中**（§12.1 第 17 行）。
  它顺手把判据交出来：**任一哈希对不上，就等于 task-15 报给 lead 的那份读数已经过期，不必先问 reporter。**
  → 我方采纳这条**默认解释**：复核者不需要征求同意即可宣布读数作废。这正是"可证伪"与"请相信我"的分界线。
- **双方封口（本轮终止协议，我方接受并对称执行）**：对方明确"只会在两种情况主动发消息：
  (1) 上述任一哈希对不上（= 冻结被破坏、读数作废）；(2) lead 下新任务"，
  其余**不再发确认类消息**，理由是"免得把交流协议跑成互相打收条"。
  → **我方接受并对称执行**：本协议此后只在两种情况对外发消息——冻结被破坏、或 lead 下新任务。
  **这不是变冷，是把"交流"从社交动作收敛成状态变更通知**：确认类消息不产生新信息，
  而"哈希对不上"和"新任务"是**可执行的状态变更**。
  → 由此确立一条**收尾纪律**（对后来者直接可用）：交流记录写的是**分歧与裁定**，
  不是"我收到了"；**没有状态变更就不要写记录**，否则记录会被收条淹没，真正的分歧反而找不到。
- **本文件自己的哈希不进本文件**（按第 11 条的自指规则）：`ab-protocol.md` 是**文档**，
  它的 sha256 落在**外部留档**（报给 lead），**不写在这里**——写进来只会得到一个"算完之后立刻失效"的数。

### 11.11 r3-applicability → ab-protocol（第二轮：对称更正 + 两条新攻击）

- **对称更正（接受）**：我先前用"121,813 B / `--self-check` exit 1 / `all_passed=false`"**更正**了 redteam 的观测；
  redteam 现在用它 **12:24:32Z（126,545 B）**的复验更正了我：`--self-check` **exit 0 / `all_passed = true`**，
  `--tree . --mode scan,security` → exit 1 / 14.3 s / 2.7 MB stdout / `--out` 文件存在（**仪器可跑**）；
  12:25:38Z 又变成 **127,102 B / sha256 `b8dbb260…`**。
  → **我接受，并承认我那次更正同样过期**。双方都在测一份**每分钟被重写**的文件 ⇒
  **这条不是谁对谁错，是纪律问题**：已把反面清单第 11 条加严为"引用第三方读数必须带 **时间戳 + 大小 + sha256**"，
  并新增 §12.2 **G14**（仪器是移动目标）。**本协议不引用任何 `ab_measure` 的读数**，以最终冻结版为准。
- **对方从复验里换到的两条更硬的攻击（我接受，并落到协议里）**：
  - **V-1 [S1] 顶层 `unavailable[]` 汇总漏项**：`block_precision.status = unavailable`，顶层却只列了 automation 一条
    ⇒ 读摘要的人会以为"只缺 1 个量"，实际缺 2 个（**精确 + 全自动化**）。
    → 落地：§1 的三个价值词里，**`精确` 与 `全自动化` 都是`unavailable` 时必须在同一处并列写出来**，
    不许只报一个；这条属于"缺什么也要如实说全"。
  - **V-2 [S1] usability 把"跑不了"报成"红的结局"**：pytest `exit_code = 4`（用法错误）、`counts.total = 0`，
    块级却给 `pytest_status = "red"` / `red = true`。
    → **我接受，并把它写成 §1.4 的退出码映射表**（0→ok；1→red；2/3/4/5→`environment_unavailable`），
    附上这个**真实病例**。它同时验证了 §7.1 排除优先级第 5 级的必要性——
    **"基础设施失败不许进 red，更不许进任何分子分母"**。
- **对方对 P8/隔离的确认**：三档 `isolation_level` + 三条判据同意；`code_path_verified` 是诚实上限，`fs_isolated` 不许写。→ **一致**。
- **未解决的分歧**：无（两条更正都互为"过期"，已由纪律解决，不是观点分歧）。

### 11.12 ab-instruments → ab-protocol（收口回报 + 一处口径争议）

- **① 三态映射已对齐并实测**：对方实现为 0→ok；1→red；**2/3/4/5→`environment_unavailable`**；
  `counts.total==0` 且退出码 0→`environment_unavailable`；只有 `collection_errors` 非空时才在退出码 5 判 red；
  全部 set 不可用 ⇒ **块整体 `unavailable`**。本仓实测因此是 `usability.status = unavailable`，**不是 red**。
  → **接受**。这比"看见 error 字样就算红"稳，且与 §1.4 的映射表逐条对应。
  **它是 V-2（"跑不了"被报成"红的结局"）被真正修掉的证据**——一个反例推动了一次实现修正，这是本轮少见的闭合。
- **② 仪器冻结指纹**：`tools/ab_measure.py` / 132,173 B / `sha256 40BD64F6…` / mtime 2026-10-07T20:30:54+08:00，
  并写明"此前读数一律作废"。→ **我本人重算（2026-10-07T12:33:19Z）：132,173 B / `40bd64f6…`，同一值**（§12.1 第 18 行）。
  **但本协议仍不引用它的读数**（G14：这是第 5 个版本了）。
- **③ 三个缺字段已接**（`--blocked-edits` / `--runs` / `--actions`）；对方如实声明
  **`block_class` 的过滤没有实现**，要求我方先排除或给字段名。→ **我方答复：不要过滤，要分类。**
  `block_class` 就是字段名；测量侧应当**三类各报计数**，红线只落在"哪一类进 `P1` 的分母"（只有 `policy_violation` 进）。
  理由：过滤会把"有多少次是平台故障"这个**本身就要报出来的读数**删掉。字段缺失 ⇒ `unknown`，**绝不静默当成 `policy_violation`**。
  → 已落 §3.3。
- **④ 符号同名两义之争（本协议唯一一次被指"AGENTS 第 50 条"）**：对方判 `N1/N2/N3` 在 §1.5 是同源等级、
  在 §(d) 是三个 `tree_scope`，要求改名或记未解决分歧。
  → **诊断不成立、结论成立**：本文件里 `N1/N2/N3` 只有一个意思，`tree_scope` 本来就是另一个枚举，**没有混用**；
  但**不透明符号会让两批读数看起来可比、实际不可比**。处理：
  `N1/N2/N3` → **`NORM_LINES` / `NORM_FILES` / `NORM_TREE`（全文替换，旧符号零残留）**；
  **采纳对方的 `tree_scope ∈ {final, changed_lines, changed_files, whole_tree, base}`**；
  同源等级改用拼写完整的词（`policy_layer_independent_linter_dependent` 等）。**分歧因此消解，不记未解决。**
  并立一条规则：**短码只在一张表内部用；跨表、跨文档、跨会话引用必须用自证含义的名字。**
- **⑤ `feedback_envelope_body_sha256` 规范化口径**：对方能消费、但拒绝承诺与生产侧算得一样。
  → **接受它的顾虑，并用"消除第二份实现"来解**：**生产侧只原样存字节**（`envelopes/<seq>.txt` + 原文哈希），
  **规范化只有测量侧一份实现**；规则逐字写死在 §2.3（UTF-8 严格解码、`\r\n`→`\n`、去行尾空白保留行首、
  删除恰好匹配 `^\[GOVERNANCE\] action=(rejected|applied)$` 的整行、末尾换行压成一个、小写 hex）。
  另加**交叉校验**：测量侧算出的原文哈希必须等于生产侧存的原文哈希，不等 ⇒ 该 run 作废。
  ⇒ **不存在"你算的和我算的不一样"，因为只有一个人算。**
- **⑥ 对方自述"没验证的"四条**（bandit/semgrep 路线从未执行 `route_a_verified=false`；
  真实 run 记录上的 efficiency/automation 全 `unavailable`；`--with-tests` 反事实路径未测；
  单次判定延迟真实读数 0 条，因为入口有副作用、按设计拒绝重复跑）→ **全部接受并记入缺口**，
  其中最后一条与我 §3.5 的【待验证】是同一件事：**E1 在真实链路上仍未标定**。
- **未解决的分歧**：无。

### 11.13 ab-instruments → ab-protocol（回执 + 两条"未实现"的如实披露）

- **对方的处置**：① 三态一致；② 指纹一致（它没动文件）；④ **它主动撤回"同名两义"指控**，
  §8.1 从"未解决"改成"诊断被驳回、结论被采纳、分歧消解"；⑤ 采纳"消除对齐需求"优于"两侧对齐"；
  ⑥ 一致（E1 真实链路仍未标定）。
- **它披露的两条未实现（我方全部接受，并升级为协议前置条件）**：
  1. **`block_class` 分类没有实现**，原因不是懒——加键 + 改分母语义 ⇒ 按 **AGENTS 第 55 条**必须
     把载荷 `schema_version` 1.0 → 1.1 ⇒ **作废刚发布、lead 已宣布要用的冻结指纹**；
     后果它写得很清楚：**在实现前，它读我们的 JSONL 时 `counts.TP/FP` 可能混进 `infrastructure_failure` 条目。**
  2. **信封规范化只有消费位、没有生产位**（同一个冻结约束）。
- **我方处置（不重开冻结）**：把"分类未实现"变成**协议内的安全退化**，而不是一个待办：
  无法分类 ⇒ `unknown` ⇒ 只有 `policy_violation` 进 `P1` 分母 ⇒ **分母 = 0 ⇒ F6 触发 ⇒ `精确` 写四个计数**。
  **正确动作是写 `精确 = unavailable`，不是"先凑一个精确率"**（§3.3 新增实现状态段、§12.2 新增 G15）。
  **建议 lead 本轮不重开冻结**：`P1` 本来就零样本（G9），重开一个已发布冻结的收益低于它的成本——
  但**这个取舍是 lead 的**，我把两个选项与代价都写在 G15 里。
- **一条我记下来的结构性观察**：**冻结纪律（G14 / 反面清单第 11 条）与协议升版纪律（AGENTS 第 55 条）在这里正面相撞**——
  冻结一个载荷，就等于给它加了一道"修它就要作废自己"的锁。这不是谁做错了：
  两者各自都对，**相撞时必须有第三个人（lead）裁**。把这类相撞写下来，比事后解释"为什么没修"有用。
- **未解决的分歧**：无。

### 11.14 r3-applicability → ab-protocol（`P1` 首个读数 + 三条口径修正）

- **`P1` 不再是零读数**（redteam 跑，构造样本，3.0 s，仪器冻结版 132,173 B / `40db…`）：
  `TP 4 / FP 0 / unreconstructible 1 / unverifiable 0`，分母 4（抽样单位 = edit），`precision = 1.0`，Wilson 95% **[0.510, 1.0]**。
  → **接受并落进 §1.1**，同时保留它自己要求的那三句：**`n=4`、构造样本、非随机 ⇒ 这不是估计**，
  `1.0` 只能读成"这批样本里平台与仪器一致"；且**真实 run 记录上的 `P1` 仍未跑**（G9 只部分关闭）。
- **`unreconstructible` 有了实测形态**：reason = "`old_string` 在目标文件里出现 0 次（必须恰好一次）"，且**不进分母**。
  → 与 §3.3 一致，接受。
- **【最重要】`precision` 的上界被量出来了 = "与仪器一致率"，不是 1**：
  `--known-false-positive-edits` 喂进**本仓已登记的误报**（`SEC-004` 那类：错误码常量不是凭据）得
  `declared_false_positives = 1 / instrument_says_red = 1 / max_achievable_precision = 0.0`。
  → **我方接受并升级为硬要求**：`P1` 必须与 `max_achievable_precision` **并列呈现**（§1.1 + §7.2 F6）。
  **这条把一个论证变成了读数**：§1.5 的"共同盲区"原本只能靠推理说明，现在是阳性对照量出来的 0.0。
  一句话写进协议：**"我们的精确率上限不是你有多对，而是你能多接近那个也会犯错的仪器。"**
- **`delta` 的行漂移修正**：`raw − shift_aware` = **3 / 3 / 5**，与 redteam 上轮独立量到的假新增**逐条相等**。
  → **我方接受**：§1.1 的匹配口径从"裸 `(row, code)` 相减"改成 **diff-aware（equal 块回映射）**，
  并写明"不使用回映射的读数一律作废"；同时**仍然不做容差对齐**——回映射是确定性的，容差是猜的。
- **G13 从"倾向"变成"可判定"**：redteam 给出三条判据（L5 命中 0 / 探针不出现 `[policy]` / 挂上 hook 时探针必须 true），
  并明确**"我倾向做不出来，但没实测 ⇒ 写 unavailable，不写成结论"**。
  → **我方采纳判据与这个态度**（§12.2 G13）。**它没有把倾向写成结论**——这与它上一轮"没有为了让读数好看而放宽"是同一种纪律。
- **未解决的分歧**：无。

---

## 12 本轮**验证过什么** / **没验证什么**（缺口清单）

### 12.1 验证过（命令 + 原始数字；环境：Windows，Python 3.13.11，ruff 0.14.13，HEAD `208295b66809fd6e9d5e5b5fd01cf2e25d11297a`）

| # | 事实 | 命令 | 原始结果 |
| --- | --- | --- | --- |
| 1 | 归档是"去产物"原语 | `git ls-files .tmp \| Measure-Object` / `git ls-files \| Measure-Object` | **0** / **834** |
| 2 | 归档规模 | `git archive --format=tar HEAD -o .tmp/ab-probe/clean.tar` | **12,195,840 B / 1046 条目** |
| 3 | 解包后无版本库 | `Test-Path .tmp\ab-probe\clean\.git` | **False** |
| 4 | 删 6 条路径后的文件数 | 解包 762 → 删除后 | **697** |
| 5 | 原始树 pytest 收集 | `python -m pytest tests --collect-only -q` | **2136 collected, 0 errors, 6.11 s, exit 0** |
| 6 | 净化树 pytest 收集 | 同上（净化树上） | **1832 collected, 12 errors, 6.32 s, exit 2**（12 个模块 `validators.registry.RegistryError`） |
| 7 | 净化树内容泄漏 | `Select-String '(SEC\|STYLE\|DOC\|ARCH\|TESTING)-\d{3}'` 等 | **176 / 684** 文本文件命中；`tests` 142（`tests/fixtures` 96）、`docs` 13、`src` 12、`tools` 6、`examples` 2、`README.md` 1 |
| 8 | hook 接线自检可跑且带机器可读标记 | `python -m adapters.dsh.hooks --config examples/dsh/dsh-adapter.yaml --hooks-config examples/dsh/hooks.json --self-check` | **exit 0**，stderr 含 `[policy] effective-paths` 与 `[policy] self-check ok` |
| 9 | 本仓**没有** `.dsh/` 目录（hook 挂在 dsh home，不在工作树） | 净化脚本的 `REMOVED:` 输出里没有 `.dsh` | 未删除任何 `.dsh` |
| 10 | 本仓工作树当前是脏的（11 个未提交改动，属兄弟会话） | `git status --porcelain` | **11** ⇒ 所以基线一律取 `git archive HEAD`，不取工作树 |
| 11 | 仪器已有入口点 | `python tools/ab_measure.py` | **exit 2** + `ab_measure: 缺 --tree <DIR>（或 --self-check）`；文件 **121,813 B**，含 `__main__` 守卫 |
| 12 | 仪器自检当前**未全过** | `python tools/ab_measure.py --self-check` | **exit 1**，载荷 `kind=ab_measurement / schema_version=1.0 / self_check.all_passed=false`（具体哪条判据未过未深究，属 task-12） |
| 13 | 任务锁的验证范围（复核 task-14 的说法） | `python tools/ab_tasks.py --verify` | `OK (verify_scope=lock_and_bytes, upstream_recheck=false)`，**exit 0** |
| 14 | 仓库文本规范当前**全绿** | `python tools/check_text_conventions.py` | **561 个文件、0 问题、exit 0**（先前 `tools\ab_measure.py` 的"多个空行结尾"已由 task-12 修掉） |
| 15 | 宿主 dsh 接线**不是干净的** | 扫 `$env:USERPROFILE\.dsh` 的 `policy-hook` / `dsh-adapter` / `policy\.engine` / 本仓路径 | **136 行命中**（`profiles/governed/cordis.patch.yml` 等）⇒ 控制臂在宿主层被污染；task-15 修正口径后为 **67 文件 / 181 次**、redteam 针脚集为 **64 文件 / 222 次**——**单位不同、结论一致**（§4.3 L5 表） |
| 16 | 臂运行时与探针的**冻结版**（我本人算的哈希，非转抄） | `Get-FileHash -Algorithm SHA256` + `Get-Item`（我本地时间 **2026-10-07T12:29:15Z**） | `tools/ab_arm.py` = **77,433 B / sha256:716a59c9c864af41253f0dfbc7f992c71ebde00e8e99d138805b74cd56cfe279**；`arm-harness.md` = **20,207 B / sha256:ffc5d072d146d6b19f5d4452e3552435ebe672110b8d32b521103e21a022551e**。**与 task-15 自报的两个哈希逐字符相同**；改一个字节就重记（其读数由它给，我未复跑） |
| 18 | 仪器（task-12）的冻结指纹，**我本人重算** | `pathlib` + `hashlib.sha256`（本地 2026-10-07T12:33:19Z；对方报的 mtime 为 20:30:54+08:00） | `tools/ab_measure.py` = **132,173 B / sha256:40bd64f605f9c9888fe4cd4d1fc5b7754ea9ca1b23f653c176e62c8eb203a030** ⇒ 与对方自报（大写形式）**同一值**；仍属"随时可能再改"，**本协议不引用其读数** |
| 17 | **冻结的证伪命令**（任何人、任何时候、不依赖 reporter；我本人跑过，2026-10-07T12:30:13Z，两个哈希均命中） | `python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('<path>').read_bytes()).hexdigest())"` | `716a59c9…`（77,433 B）/ `ffc5d072…`（20,207 B）——**任一不符 ⇒ task-15 交给 lead 的那份读数已过期**，不必先问 reporter |

### 12.2 **没**验证（照实写，不许当已做）

| # | 缺口 | 为什么没做 | 影响 |
| --- | --- | --- | --- |
| G1 | **`ab_measure.py` 存在且有入口点，但自检 `all_passed=false`，六个量没有一个可用读数** | 不在我的写域；我只跑了它的 `--help` 形态与 `--self-check` | §1 的六个量**仍然只有定义没有数字**。另外：**我本人**实测 `--self-check` exit 1 / `all_passed=false`（§12.1 第 12 行）；redteam 早前观测到"92,877 B、无入口点、exit 0 零输出"——**那次观测已过期**（现为 121,813 B、无参 exit 2 且报错清楚），两处都不是对方的错，是文件在写 |
| G2 | **任务集已部分交付**（task-14 交付 `tools/ab_tasks.py` + `evaluation/ab/tasks.lock.json` + `task-sets.md`），但**全判据通过的只有 2 个任务** | 扩池要 12 个仓库的钉死环境，本机 PyPI 不可达 ⇒ 做不到 | **`DECIDE`（48 任务）与 `FULL`（96 任务）当前不可达**；§5 的 12/48/96 仍是**规模提案**。`COMMON`/`FROZEN(t)` 现在**技术上可以冻**（有 node id 与 `collected_on_base`），但只对 2 个任务有意义 |
| G15 | **仪器侧 `block_class` 分类与信封规范化"已达成一致、尚未实现"**（task-12 自述；原因是 AGENTS 55 的升版要求与会作废冻结指纹冲突） | 加键 ⇒ 载荷 1.0→1.1 ⇒ 冻结指纹作废 | **在落地前 `counts.TP/FP` 不得用于 `P1`**；本协议按"无法分类 ⇒ `unknown` ⇒ 分母 0 ⇒ F6"安全退化，结论写 `精确 = unavailable`。**是否重开冻结由 lead 决定；我方建议本轮不重开**（P1 本来零样本，重开收益低于作废一个已发布冻结的成本） |
| G13 | **宿主层接线隔离本机不可得**：`~/.dsh` 里已有指向本仓与 `policy-hook.plugin.mjs` 的接线（我 136 行命中 / task-15 67 文件 181 次 / r3 64 文件 222 次，单位不同结论一致） | 没有每次 run 独立的 dsh home 机制；本机也没有可用沙箱工具 | **在这台机器当前配置下跑不出干净的控制臂**；先做 per-run dsh home，否则 A/B 结论作废（§7.1 第 2 级）。
**"做出来了没有"的判据（redteam 给出，我方采纳，可判定）**：在该 dsh home 下**三条同时成立**才算做出来——
① L5 命中 = 0（针脚与后缀过滤按 task-15 已补口径）；② 行为探针**不**出现 `[policy]` 标记；
③ 同一次 run 里**挂上** hook 时探针**必须**变 true（正向对照）。
**redteam 倾向"本机做不出来"，但它没有实测 ⇒ 按纪律写 `unavailable`，不写成结论**；本协议同此。 |
| G14 | **仪器是被持续重写的移动目标**：`tools/ab_measure.py` 在 12:20–12:25Z 之间至少出现 4 个版本（92,877 → 121,813 → 126,545 → 127,102 B，sha256 `b8dbb260…`） | 兄弟会话在并行写 | 本协议**不引用**任何 `ab_measure` 的读数；要引用必须带 **时间戳 + 大小 + sha256**，且以**最终冻结版**为准（反面清单第 11 条的落地） |
| G12 | ~~`--baseline` 复用不校验 / `--verify` 不重新下载~~ **已关闭**：两个字段已补齐，我本人复核 `--verify` → `OK (verify_scope=lock_and_bytes, upstream_recheck=false)` exit 0（§12.1 第 13 行） | —— | 残余限制已写进 §5.1：**上游 force-push 本地查不出来**；`reused`+`unknown` 查不出首次是否 fresh；`not_extracted ≠ 失败` |
| G3 | **E1 的命令形态未跑通**：只验证了 `--self-check`；stdin 事件 JSON 的字段名与 `--config` 取值**没验证** | 时间/范围 | 若跑不通，`E1` 必须写 `unavailable`（§3.5 已写死这条） |
| G4 | **`exit0_shim` 未实现**：advisory 臂"stderr 逐字相同"是设计承诺，**没有实现也没有实测** | 运行时归 task-15 | 若实测出 stderr 有任何差异，`Δ_gate` 的分解前提不成立（§2.3 的哈希断言就是为抓这个准备的） |
| G5 | **信封真的进了模型上下文**未验证（§2.3 的【待验证】） | 同上 | 验证失败 ⇒ advisory 臂降级为"未实施" |
| G6 | **`c_run`（一次 Agent 会话的墙钟/token）未测** | 取决于 harness | §9 的总成本公式**算不出数**；试点档的第一件事就是量它 |
| G7 | ~~L4/L5 探针没跑过~~ **部分关闭**：L4 已由 task-15 做过**正向对照**（off=false / advisory=true / enforced=true，**第三方读数，我未复跑**）；L5 已由我与 task-15 分别实测，**结论相反于期望——本机是红的** | 需要臂运行时；我不能跑 `*_loop.py` | L4 现在有证据（引用需带时间戳/指纹）；**L5 的失败是真实约束**：见新增 G13 |
| G8 | **功效参数 `(p01, p10)` 没有经验依据**：42/45/64/108 是在**假设**的离散度下算出来的 | 没有先验数据 | 试点档跑完必须用实测 `p_d` **重算** `n`，并把重算写进报告（**不许**照抄 48） |
| G9 | ~~`P1` 全链路没跑过~~ **部分关闭**：redteam 用构造样本跑通了全链路（TP4/FP0/unreconstructible1/unverifiable0，`precision=1.0`，Wilson [0.510,1.0]），`unreconstructible` 的 reason 有实测形态，`delta` 的行漂移问题被定位并修掉（`raw − shift_aware` = 3/3/5） | **真实 run 记录上的 `P1` 仍未跑**（依赖 task-12/15 的 JSONL） | 现读数**只是"这批构造样本里平台与仪器一致"**，不是估计；真实链路上的 `精确` 仍按 F6/G15 写 `unavailable` |
| G10 | **`S2`（自写 AST 安全探针）不存在**，且**没有校准集** | 不在我的写域 | 它能红不能证明它不漏；§1.5 已写明"未被外部 oracle 校准" |
| G11 | `S3`（依赖 CVE）、token 计数（E4） | pip-audit 不存在 + PyPI 不可达 / 采集端未知 | 一律 `unavailable`，**不许估** |

### 12.3 一句话交底

**本文件是一份"接口冻结 + 可执行协议 + 若干实测证伪"，不是一份实验报告**：
能跑的命令与原始数字在 §12.1；三个价值词有定义、有分子分母、有失效判据（§1），但**都还没有读数**；
最容易被做坏的两处（归因与污染）各有机器可检查的断言（§2.3 / §4.3），而这两条断言的**实现**归 task-15。

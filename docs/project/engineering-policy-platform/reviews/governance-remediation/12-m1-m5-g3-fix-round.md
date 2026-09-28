# 修复轮：M1–M5 与 G3/N13/N14 的处置（2026-09-27）

> 输入是 [多规则开发轮](../governance-capability/06-multirule-dev-round.md) 的 §8「建议的下一轮」
> 与它新显现的五项问题（M1–M5），以及 [缺口清单](../governance-coverage-gaps.md) 后续轮次表里
> 尚未闭合的登记项（**G3**：会话内只有 1 条规则真正参与判定；**N13**：缺口探针自己走不到 Phase 6；
> **N14**：依赖类规则的 language 维度靠规则作者纪律；11 号文档 §5 第 6 条的 target 解析口径）。
>
> 本轮的组织方式与前几轮一致：**Lead 定范围与接口，开子会话并行做互不重叠的写域，
> 每一条改动都配一条「修复前会红」的检查**，最后 Lead 串行跑一次全量门禁并复核。
> 子会话的产物（探针、红绿输出、证据 JSON）在 `.tmp/round-07/` 下，可随时重算；
> `.tmp/` 是构建产物，不提交。
>
> 明确不做的部分写在 §1.3，并逐条给出理由——**没有做**不等于**不需要做**。

## 0. 一句话

本轮把上一轮"登记了但没修"的东西修掉：**M1 的分层误判从"运行期静默"变成"声明期必须自证"**
（同一批 layers 加一行测试层声明，加载期会证明每条测试路径都落在测试层，证明不了就拒绝启动）；
**G3 的正面回答**落成一个可声明、可关闭、失败关闭的"动手前取证"（在影子工作区上跑 Phase 5 流水线，
把证据交给引擎，证据类 checker 从"跳过"变成"参与判定"）；**M3 的口径**进审计
（"43 条规则"与"43 条会拦人的规则"从此在账本里是两个数）；**M4/M5 的代价**用"拒绝理由带可用替代"
降下来；**N14 的纪律变成会失败的检查**；**N13 的仪器**被修到能看见它本该看见的那类缺陷。

**两件事必须与结论一起读。** 第一，**G3 只在声明并启用 `pre_evidence` 的通道上闭合**：
默认部署仍是 Phase 2 契约（证据类 checker 进 `skipped_rules`），把这段打开会显著变慢，
因此它是部署方的策略决定，本轮没有替谁打开。第二，**本轮没有第三方独立验收**：
三路子会话与 Lead 是同一个模型、同一台机器，写域互不重叠、复核由 Lead 做——
这与前几轮的 V1 独立验收不是一回事（§9 第 1 条）。

## 1. 本轮的范围
### 1.1 从哪里来

| 来源 | 条目 | 级别 |
| --- | --- | --- |
| [06 多规则开发轮](../governance-capability/06-multirule-dev-round.md) §4 | M1 分层映射靠文件名，测试被认成入口层 | 重要 |
| 同上 | M2 会话内有效规则 1/43（= [G3](../governance-coverage-gaps.md)） | 阻断 |
| 同上 | M3 19 条 warning 规则只有判定力、没有阻断力 | 重要 |
| 同上 | M4 组合命令与"白名单内但未审批"让可用命令面很窄 | 次要 |
| 同上 | M5 只读越界也会打断探索 | 次要 |
| [00 修复计划](00-remediation-plan.md) §5 登记 | N13 缺口探针走不到 Phase 6 | 登记候补 |
| 同上 | N14 `forbidden_dependency` 不声明 language 时靠纪律兜着 | 登记候补 |
| [11 修复轮](11-n16-n24-fix-round.md) §5 第 6 条 | `validators.cli` 与 `policy.check` 的 target 解析口径不同 | 登记候补 |

### 1.2 写域划分（子会话并行，互不重叠）

| 子会话 | 写域 | 任务 |
| --- | --- | --- |
| **Lead** | `src/adapters/dsh/adapter.py`、`examples/dsh/dsh-adapter.yaml`、`tests/unit/test_dsh_layer_guard.py`、`tests/unit/test_dsh_adapter_config.py`、`tests/contract/test_dsh_layer_declaration.py` | M1：加载期分层检查 + 配置接口冻结（`test_paths`/`test_layer`/`pre_evidence`） |
| **A1** | `src/adapters/dsh/pre_evidence.py`（新）、`src/adapters/dsh/hooks.py`、`src/adapters/dsh/README.md`、两个新测试文件 | G3/M2：动手前取证；M3：严重级别可见性 |
| **A2** | `src/enforcement/precheck.py`、`src/enforcement/approvals.py`、`src/validators/cli.py`、`src/policy/check.py`、相关测试 | M4/M5：拒绝理由带可用替代；§5.6：target 解析口径统一 |
| **A3** | `src/policy/loader.py`、`tools/governance_gap_probe.py`、相关测试 | N14：加载期拒绝"依赖规则不声明 language"；N13：探针覆盖 Phase 6 并能证红 |

写域重叠是**约定**不是锁：Lead 先把接口（`AdapterConfig.test_paths`/`test_layer`/`pre_evidence`）冻结在
`adapter.py` 里，A1 只消费不修改；其余三路的文件集合两两不相交。

### 1.3 明确不做的部分

| 不做的事 | 理由 |
| --- | --- |
| 桌面 GUI 通道接线（G1 残余、06 §8 第 3 条） | 使用者的决定：装它要重启界面，且会让 GUI 里的命令行全部变成需要审批 |
| N25（受限沙箱里 Hook `spawn EPERM`）与 N26（宿主 ACL 把 `0o700` 目录锁死） | **宿主环境事实**，不是仓库缺陷；本轮把测试统一到仓库自己的临时夹具（`tmp_root`）以避开 N26 |
| N2：Phase 2 的 `load_config` 与 Phase 6 的 `adapter.yaml` 字段口径合并 | 需要一次显式设计；本轮把新字段只加在 Phase 2 侧，并在 §7 记为残余 |
| N27 的残留语义（`exit_code_zero` 把"证据充分"与"命令成功"合成一条判定） | 改它是**注册表词汇表的策略变更**，需要重新审核并单独一轮；上一轮已按此处置，本轮不变 |
| 06 §8 第 5 条：在真实会话里压 N27 的失败路径 | 要在不受限 shell 里起真实受治理会话（与 N25 同域）；本轮只做确定性探针，不写成"已确认" |
| N15：`tools/ast_unchanged.py` | 上一轮已裁决不做（收益间歇、成本永久），本轮不改这条裁决 |

## 2. 方法与判据

- **每条改动配一条会先失败的检查**：先写测试跑红、再实现跑绿，两次输出留在
  `.tmp/round-07/red-green/` 下（文件名带子会话代号）。
- **确定性探针优先**：能不用模型证明的，就不用模型证明。M1 用配置层与生产 Hook CLI 两层对照；
  G3 用"同一份载荷、pre-evidence 关/开"两条臂。
- **判据沿用 N19 的硬不变量**："没拦到"不等于"拦住了"；"跑了、是绿的"不等于"检查到了"。
- **独立验收**：Lead 用与子会话不同的入口复核（§6），并串行跑一次全量门禁（§7）。

## 3. M1 · 分层声明把测试文件卷进生产层

**问题回顾（06 §3.7 / §4 M1）。** 子会话写 `tests/test_shipment_controller.py`（一份很自然的测试：
导入仓储层来组装对象图），被 ARCH-001 判成"入口层直接依赖仓储层"**阻断**。机制是 layers
按声明顺序取第一个命中的 glob，而 `**/*_controller.py` 排在 `**/*.py` 前面，
`tests/test_shipment_controller.py` 命中的正是前者。模型为了过规则，把测试从"真实装配"改写成了
"手写替身"——**治理把一个测试写法挤走了**。

### 3.1 改了什么

| 层 | 改动 | 落点 |
| --- | --- | --- |
| 数据 | 示例配置（受治理项目 `.policy/dsh-adapter.yaml` 的模板）声明 `test_paths` / `test_layer`，并把 `tests/**/*.py -> test` 放在 `layers` **顶部** | `examples/dsh/dsh-adapter.yaml` |
| 代码 | 新字段 `test_paths` / `test_layer`（严格解析：未知字段、绝对路径、含 `..` 一律报错）；新增 `AdapterConfig.layer_test_conflicts()`，**加载期**证明每条测试路径都落在声明的测试层，证明不了就拒绝启动 | `src/adapters/dsh/adapter.py` |
| 契约 | 真数据上的双向断言：仓库里每个 `tests/**/*.py` 都解析到测试层；把那一行声明删掉，同一份配置在加载期就红 | `tests/contract/test_dsh_layer_declaration.py` |
| 单元 | 顺序敏感性（测试层规则排在后面同样拒绝）、缺 `test_layer` 拒绝、`test_paths` 非法拒绝、未声明时检查不生效（向后兼容） | `tests/unit/test_dsh_layer_guard.py` |

**检查的保守性（必须与结论一起读）。** 见证路径由声明本身推导（`**/` → `x/`、`*` → `w`、`?` → `q`），
再把一条 pattern 的字面前缀与另一条的结尾拼起来作为候选。它**可能漏**（复杂重叠拼不出见证路径），
但不会误报：报出来的每一条，都是"两条 pattern 都真的命中"的真实路径。

### 3.2 修复前会红（配置层，`.tmp/round-07/harness/probe_m1.py`）

| 路径 | 修复前（HEAD 上的声明） | 修复后（工作树的声明） |
| --- | --- | --- |
| `tests/test_shipment_controller.py` | `controller`（命中 `**/*_controller.py`） | **`test`**（命中 `tests/**/*.py`，非兜底） |
| `tests/unit/test_shipment_service.py` | `service` | **`test`** |
| `src/wmsvc/shipment_controller.py` | `controller` | `controller`（生产路径结论不变） |
| `src/wmsvc/shipment_service.py` | `service` | `service`（生产路径结论不变） |

三条负对照（同一份配置）：

| 变体 | 结果 |
| --- | --- |
| 修复前的声明 + 显式声明 `test_paths`（有心声明、顺序没改） | **加载期拒绝**："分层声明把测试路径卷进了生产层（M1）" |
| 修复后的声明，删掉测试层规则 | **加载期拒绝** |
| 修复后的声明，把测试层规则挪到生产层规则**之后** | **加载期拒绝** |

### 3.3 端到端（生产 Hook CLI，`.tmp/round-07/harness/probe_m1_hook.py`）

同一份写入载荷（往 `tests/test_shipment_controller.py` 写一份导入仓储层的测试），只改声明：

| 臂 | 配置形状 | 退出码 | 判定 | layer | 命中规则 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| A | 修复前（没有测试层规则） | 2 | `policy_block` / block | `controller` | `ARCH-001@1` | **M1 在真实 Hook 上复现** |
| B | 声明了 `test_paths`，但测试层规则排在后面 | 2 | `startup_error`（无判定记录） | — | — | **不启动**：配置自相矛盾时既不判 allow 也不判 block |
| C | 修复后（测试层规则在顶部） | 0 | `allow` | `test` | — | 测试文件的真实写法不再被生产层规则管 |

产物：`.tmp/round-07/evidence/m1-probe.json`、`.tmp/round-07/evidence/m1-hook-probe.json`。

**一次踩坑（如实记）。** 探针第一次跑把 B 臂的"顺序错"写成了"把测试层规则追加到文件末尾"，
那不是合法 YAML，于是 B 臂报的是"配置解析失败"——**测到的是语法错，不是顺序错**。
已改成"挪到 layers 段的末尾"并重跑；上表是修正后的结果。

### 3.4 未闭合的部分

- **没有声明 `test_paths` 的配置行为不变**（检查不生效）。这是刻意的向后兼容：口径要求
  "不猜、不推断"（AGENTS.md 第 6 条），而"哪些路径算测试"是**项目的声明**，不是平台能猜的。
  代价是：不声明的项目仍然会静默误判测试文件——残余记在 §9。
- 仓库自己的 **Phase 6 配置** `adapters/dsh/adapter.yaml` 没有加这一行：它由 Phase 6 的口径加载
  （字段集合与 Phase 2 不同，N2 未合并），且它的 layers 只影响规范事件路径。残余同样记在 §9。

## 4. G3/M2 · 动手前取证（证据类 checker 从「跳过」变成「参与判定」）

### 4.1 问题回顾

上一轮的两条会话审计都是 `effective_rule_count ∈ {0, 1}`、`skipped_rule_count ∈ {42, 43}`：
pre-execute 路径只传上下文，`policy.engine.evaluate` 于是把证据类 checker
（`style_lint` 39 条 / `missing_docstring` / `missing_tests` / `failing_tests`）的规则记进 `skipped_rules`。
**跳过不等于通过**——账本上那 42 条只是没人查。

### 4.2 改了什么

| 层 | 改动 | 落点 |
| --- | --- | --- |
| 声明（Lead 冻结接口） | `pre_evidence` 段：`enabled` / `registry_root` / `workspace` / `shadow_root` / `exclude` / `validators` / `timeout_ms`；未知字段、类型错误、缺 `registry_root` 一律报错 | `src/adapters/dsh/adapter.py` |
| 取证 | 新模块：按 `TOOL_TABLE` 从载荷重建**提议内容**（`write` 取 content；`edit` 读当前文件做恰好一次替换；`str_replace_editor` 取 file_text/new_str）→ 在**影子副本**上应用 → 跑 Phase 5 真流水线 → 返回 `EvidenceBundle` + 脱敏摘要 | `src/adapters/dsh/pre_evidence.py`（新） |
| 接线 | `evidence_provider` 端口；`_decide` 取证后把 evidence 交给 evaluator（`evidence=None` 时仍是 2 个位置参数）；审计新增 `pre_evidence_status` 与 `pre_evidence` 摘要；`check_wiring` 增预算不等式 | `src/adapters/dsh/hooks.py` |
| M3 | `rule_visibility()` 增 `rules_by_severity` / `evaluated_by_severity` / `skipped_by_severity` / `blocking_capable_rule_count` / `advisory_rule_count` + `severity_note` | 同上 |
| 数据 | 示例配置补一段**注释掉的** `pre_evidence` 形状 + 预算不等式说明（默认部署仍是 Phase 2 契约） | `examples/dsh/dsh-adapter.yaml` |

**失败语义（与 AGENTS 第 42 条一致）**：声明并启用后，取证失败 / 超时 / 提议内容重建不了
（`edit` 的 `old_string` 不唯一、`replace_all` 命中多处）一律 **`evidence_unavailable` + 退出码 2**，
理由写明「拒绝在证明不了的情况下放行」；**绝不回落到「没证据就当跳过」**。
影子副本在 `finally` 里必删，且**与被治理项目重叠时直接拒绝取证**——
声明里写错一个 `.` 就会让 `rmtree` 删掉项目本身，这条检查是数据安全级别的。

### 4.3 会先失败的检查（A1 的红→绿）

| 项 | 修前 | 修后 |
| --- | --- | --- |
| 新测试两个文件 | `exit 4`、2 个 collection error（`No module named adapters.dsh.pre_evidence`） | **31 passed** |
| 指定验收 8 个文件 | （新增文件不存在） | **151 passed**（与改动前基线一致） |
| 另 6 个相关套件 | — | **238 passed** |

产物：`.tmp/round-07/red-green/a1-{red,green,acceptance}.txt`。

### 4.4 两条路径上的实证

**A1 的探针**（生产 Hook CLI，同一载荷两遍，压内置验证器）：

| 臂 | decision | reason_code | effective | skipped | served_checkers | violation |
| --- | --- | --- | --- | --- | --- | --- |
| off | allow | `allow` | 0 | 1 | – | – |
| on | **block** | `policy_block` | 1 | 0 | `missing_docstring` | `DOC-900@1` |

**Lead 的独立验收**（不同入口，压**外部工具** `tool.ruff` / 39 条 `style_lint` 规则那条路）：

| 臂 | 退出码 | decision | effective | skipped | served | validators |
| --- | --- | --- | --- | --- | --- | --- |
| off（不声明 `pre_evidence`） | 0 | allow | **0** | 1（`STYLE-901@1` 在 skipped 里） | – | – |
| on + 违规内容（超长行） | 2 | **block** | **1** | 0 | `style_lint` | `py.source@1.0`、`tool.ruff@1.0` |
| on + 合规内容 | 0 | allow | 1 | 0 | `style_lint` | 同上 |

十个不变量全部成立（`10/10`）：off 真的把那条规则记成 skipped；on 的阻断来自**证据类规则**
（`matched_rules` 含 `STYLE-901@1`）；清理后影子目录无残留；摘要里没有绝对路径；
摘要里的目标文件是**仓库相对路径**。产物：`.tmp/round-07/evidence/pre-evidence-ruff.json`。

### 4.5 Lead 复核时发现并修掉的两处小缺陷

1. **审计里的目标文件被脱敏成 `src<abs>`**：取证摘要把流水线在影子副本里用的**绝对路径**当成了目标；
   而脱敏正则把「任何以 `/` 开头的片段」都当绝对路径，连仓库相对路径也一起抹掉。
   已改为记**仓库相对路径**，并把绝对路径识别改成**带边界**（串首或空白 / 引号 / 括号 / 等号 / 冒号 / 逗号之后）；
   `hooks.sanitize` 用同一份口径，顺带补上它原先缺的 POSIX 分支——
   修前 `tests/test_x.py` 这种相对路径同样会被吃掉，模型看到的是 `tests<abs>`。
2. 探针与产品无关的两处误判（`pre_evidence_status` 的取值名、validator 记录的主键名）已就地更正——
   如实记下来是因为「仪器自己的 bug」与「被测对象的 bug」必须分开写。

### 4.6 未闭合的部分

- `registry_root` 接受两种写法（包含 `validation/` 的那一层，或 `validation/` 目录本身），
  解析方式写进摘要 `registry_resolution`；两种同时成立时报错而不是挑一个。
- 探针只压了内置验证器 + ruff；**`tool.pytest`（`missing_tests`/`failing_tests`）在动手前路径上没有单独压过**——
  它由既有流水线测试守住，但「动手前在影子副本上跑 pytest」的端到端证据本轮缺。
- 动手前取证是**声明式**的：不声明就仍是 Phase 2 契约。把`pre_evidence` 打开会显著变慢
  （每次写类动作在副本上跑一遍验证器），因此它是部署方的策略决定，不是新的默认值。

## 5. M4/M5 与口径 · 拒绝理由带可用替代

### 5.1 M4 · 命令面很窄，但模型得靠试错才发现

**问题回顾（06 §4 M4）。** 子会话第一条 `pwsh` 是模型习惯的复合一行
（`Get-ChildItem …; Write-Host …; Get-ChildItem …`），被 `command_composition_blocked` 拒绝；
随后 `git status --short`（在白名单里，但不在已签发的模式化审批覆盖面里）被 `approval_invalid` 拒绝。
方向正确（AGENTS.md 第 14、17 条），代价是模型要花额外轮次试错。

**改了什么（只改理由，不改判定）。** `src/enforcement/precheck.py` 新增两个纯函数
`_listed` / `_declared_alternatives`，把"改成什么形态就能过"写进四类失败理由：
命令白名单不匹配、组合命令、被禁片段、审批不匹配/缺失。替代信息**只来自两处已声明数据**——
注册表的 `allowed_commands` 与随请求交来的、绑定同一工具的已签发审批的 `param_patterns`；
没有可说的就不写（宁可不写，也不许编一个出来）；有上限（8 条 + "另有 N 条未列出"），
理由是给模型读的，不能变成新的噪音。

**M5.** `path_prefixes`（受保护前缀）的拒绝理由补上"本会话可用的读取范围形态是受控项目内的
仓库相对路径（范围等于项目根时记为 `.`）"。同一句话补进 **Phase 6 的规范事件路径**：
`src/adapters/models.py` 的 `normalize_event_path` 三处拒绝（工作区外绝对路径、`path_base` 逃逸、
相对路径含 `..`）——dsh 侧 `_resolve_read_scope` 早在 N22 就有这句，Phase 6 侧一直缺，
属同一类"理由只说不行、不说怎么改"。**范围校验一个字没放松。**

### 5.2 口径统一（11 号文档 §5 第 6 条）

修前实测两处分叉：

| 情形 | `validators.cli`（修前） | `policy.check`（修前） |
| --- | --- | --- |
| `--workspace src` + 目标写 `src/某文件` | 判"文件不存在" | 解析到 `policy/models.py` |
| `--config-root X` | 把工作区也当成 `X` | 工作区仍是仓库根 |

修后：`validators.cli` 的 target / workspace 锚改为**仓库根**，复用 `policy.check.resolve_workspace`
与 `resolve_target_file`（`--config-root` 只定位 `validation/` 配置与规则目录）；
`policy.check` 的两个解析函数补上 docstring，写明它们就是唯一口径。六种情形对照全部一致
（`.tmp/round-07/red-green/a2-resolution-after.txt`）。

**一处行为变化（如实记）。** `validators.cli` 的**目标文件不存在**时，退出码由 **1**（`py.source`
的失败关闭阻断点）变成 **2**（配置/用法错误）——因为定位失败现在发生在构造上下文之前。
这与该 CLI 自己写明的契约一致（"0 通过；1 有发现或失败关闭的阻断点；2 配置或用法错误"），
也把"用错了"和"证据不足"分开了；既有测试、学习手册记录的退出码（含 `../outside.py` → 2）
与 `tools/validator_loop.py` 均不受影响。

### 5.3 证据

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 修前红 | 新增用例 + 锁定用例 | **10 failed, 4 passed**（失败理由即修前原文） |
| 修后绿 | 8 个验收文件 | **141 passed** |
| 邻接套件 | validator_pipeline / hardening_cli / validator_adversarial / dsh_hook / dsh_enforcement / verdict / enforcement_protocol | **148 passed, 1 skipped**（本机不能建符号链接） |

产物：`.tmp/round-07/red-green/a2-{red,green,adjacent-suites,resolution-after}.txt`。

## 6. N14/N13 · 纪律变检查、仪器能证红

### 6.1 N14 · 依赖类规则必须声明 language

**问题回顾（[00 修复计划](00-remediation-plan.md) 的 N14 行、[07](07-ruff-cleanup-and-n1.md) 的 R7）。**
依赖提取只在语言被显式解析成 `python` 时才可能给出非空依赖集；`language` 缺失时依赖集是空元组，
依赖类 checker 于是判 allow——而**放行的理由（语言未知）不写在任何地方**，与「确实没有禁用依赖」逐字相同。
今天没有洞，只因为 43 条规则里唯一用 `forbidden_dependency` 的 ARCH-001 恰好在 scope 里写了 `language: python`：
那是**规则作者的纪律**，不是代码保证。

**改了什么。** `src/policy/loader.py` 新增 `assert_language_declared()`，在 `load_rule_file` 里调用：
checker 属于依赖类（当前只有 `forbidden_dependency`）的规则，scope 未声明 `language`、
或把它写成「该维度不限制」（`*`，或含 `*` 的列表）时，加载期抛 `RuleFileError`（`field=scope.language`），
信息写明机制与后果。把`*` 也算拒绝是**超出字面**的一处：它与不声明在判定上等价（同一条静默路径）；
边界写进了 docstring：声明了具体语言而语言不匹配时，规则会**显式进 skipped_rules**（那不是静默），本检查不管。

**会先失败的检查。** `tests/unit/test_loader.py` 增 6 条，其中一条是**机制断言**：
绕过加载器、直接拿没有 language 的上下文去判，确实得到 allow 且不产生任何 skipped 记录——这正是「静默」的定义。
夹具放在新目录 `tests/fixtures/invalid_rules/`（**没有**放进 `tests/fixtures/rules/`，那里会被规则语料测试整目录扫描）。

**Lead 的独立验证**（不同入口，`.tmp/round-07/harness/probe_n14.py`）：

| 用例 | 结果 |
| --- | --- |
| 43 条既有规则 | 照常加载；`forbidden_dependency` 规则仍只有 `ARCH-001@1` |
| 同一条探针规则，scope 缺 `language` | 加载期拒绝，理由含「依赖集因此是空元组……只能静默放行」 |
| 同一条规则，language 写成星号（显式不限制） | 同样拒绝（等价于不声明） |
| 同一条规则，`language: python`（正对照） | 正常加载 |

产物：`.tmp/round-07/evidence/n14-probe.json`。

### 6.2 N13 · 缺口探针自己走不到 Phase 6

**问题回顾（N13 / R6）。** `tools/governance_gap_probe.py` 的 G06 只驱动 Phase 2 的 `python -m adapters.dsh.hooks`，
从不走 Phase 6（规范事件 / `JsonAdapter` / `to_policy_context`）。上一轮的独立验收已经量过这一点：
拿它对**修前快照**跑 `--phase after`，**仍然 13/13、exit 0**——它对 N1 那类缺陷是瞎的。

**改了什么。** G06 现在对**同一批 11 条用例**跑两条路径：Phase 2 钩子，以及 Phase 6
（`load_adapter` 装配 `generic-json` → `to_policy_event` → `to_policy_context` → `policy.engine.evaluate`）；
facts 增 `p6_*` / `p6_case_count` / `path_disagreements`，before/after 两张期望表逐条更新；
G06 的范围声明改成「覆盖什么 / **仍不覆盖什么**」，并把修前树的重建规格写进注释。
**检查数仍是 13**（不新增 id，G06 内部用例 11 → 22 格），所以 `tools/README.md` 的「13 项」口径不变。

**变异证红（这一条才是 N13 的验收口径）。** `git archive HEAD` 到 `.tmp/round-07/a3/pre-fix`，
按 [09 号文档](09-instrument-migration-assessment.md) §9.1-D + §10.4 在副本的 `src/adapters/textfacts.py` 上做 4 处替换
（`from` 正则去掉前导点、不登记动态导入、`_from_targets` / `_module_names` 只登记首段）：

| 树 | 命令 | 结果 |
| --- | --- | --- |
| 变异体（修前口径） | `--phase after` | **exit 1，G06 12 处不符（其中 6 条 `p6_*`）** |
| 变异体 | `--phase before` | exit 0（修前期望表被这棵重建树证实） |
| 当前树 | `--phase after` | exit 0，全量 **13/13** |
| 当前树 | `--phase before` | exit 1（如实报出「这棵树不是修前树」） |

产物：`.tmp/round-07/red-green/a3-*.txt`、`.tmp/round-07/a3/`。

### 6.3 证据与边界

| 项 | 结果 |
| --- | --- |
| A3 指定 6 个验收文件 | **199 passed** |
| unit + contract 全量 | **1122 passed / 1 skipped**（本机不能建符号链接） |
| 探针全量 | `--phase after` → **13/13、exit 0** |

**仍不覆盖（写在探针注释里，不写成「已覆盖」）**：Phase 6 的 dsh 桥、`hook-command` 事件型 Adapter、
AST 证据路径与 runtime 链路——它们由两个 git 跟踪的测试承担；本机也**没有真实修前快照**
（`.tmp/verifier/v1/baseline` 里的 `textfacts.py` 已是新口径），因此 before 表是用**重建树**证实的，不是用原始快照。

## 7. 独立验收与全量门禁

### 7.1 Lead 的独立入口（与子会话不同的入口）

| 验收项 | 入口 | 结果 |
| --- | --- | --- |
| M1 配置层 | `config_from_mapping` / `layer_resolution`（不经过 Hook） | 4 条路径双向一致 + 3 条负对照全部拒绝 |
| M1 端到端 | **生产 Hook CLI** 三臂（同一份写入载荷） | block/controller/`ARCH-001@1` → `startup_error` → allow/test，三条臂与期望一致 |
| G3 动前取证 | **生产 Hook CLI** + 真实 ruff（外部验证器） | off：effective 0、规则进 skipped；on：**block**、effective 1、served `style_lint`；on+合规：allow。**10/10 不变量成立** |
| N14 加载期检查 | 直接调 `load_rule_set` | 43 条规则照常加载；缺 `language` 与写 `*` 都被拒；正对照通过 |
| 缺口探针 | `tools/governance_gap_probe.py --root . --phase after --repeat 2` | **13/13**、exit 0 |

### 7.2 子会话的验收（我方复核后引用）

| 子会话 | 验收 | 结果 |
| --- | --- | --- |
| A1（G3/M2 + M3） | 新测试 2 文件 / 指定 8 文件 / 另 6 套件 | 修前 collection error → **31 passed**；**151 passed**（与基线一致）；**238 passed** |
| A2（M4/M5 + 口径） | 新增用例 / 8 验收文件 / 邻接 7 套件 | 修前 **10 failed, 4 passed** → **141 passed**；邻接 **148 passed, 1 skipped** |
| A3（N14 + N13） | 6 验收文件 / unit+contract / 探针 | **199 passed**；**1122 passed, 1 skipped**；探针 **13/13、exit 0**；变异体 **exit 1、G06 12 处不符** |

### 7.3 全量门禁

三个子会话都**没有**自己跑门禁（那会与别的写者抢 `.tmp/` 下的固定路径）；
等它们全部收敛、写者清空后，Lead 串行跑了一次：

    python tools/ci_local.py --full --timings

**结果：本机检查全部通过（32 步，rc=0）**——含仓库一致性、密钥扫描、四个测试套件、规则集自检、
AST 证据重放、外部工具探针、验证器闭环、dsh 契约与 Hook 行为、接线自检、检索基线与漂移、
工具注册表已审核哈希、受控执行闭环、审计链校验、性能基线、学习手册与技术细节 notebook 同步、
文本约定、多 Agent 一致性套件与闭环、Policy API 自检/契约快照/闭环、编排自检/闭环、阶段验收证据。
耗时明细在 `.tmp/ci-local-timings.json`。

同一份门禁里那一步**通道清点**（不带 `--check`）如实报出桌面/无头通道仍未接线（`dsh:desktop: not_wired`）：
这正是 §1.3 里`不碰 GUI 通道`这条选择的同机可见形态，不是回归。

**门禁结论的适用边界（N28）**：它只对**跑的那一刻的工作树**成立。本轮在全量门禁之后只再写了本文件与
索引/表格（纯文档），没有再改代码；文档改动由文本约定检查单独复核（584 个文件、0 处问题）。

## 8. 与前几轮条目的关系

| 既有条目 | 本轮之前 | 本轮处置 |
| --- | --- | --- |
| **G3 / M2** 会话内只有 1 条规则在查 | 未变（两次会话都是 1/43） | **正面回答**：动手前取证可声明（`pre_evidence`），启用后证据类 checker 参与判定；**未声明的部署不变** |
| **G7 / M1** 分层靠文件名、顺序能罩住测试 | PARTIAL（靠 `layer_defaulted` 可见） | **加载期自证**：声明 `test_paths` / `test_layer` 后证明不了就拒绝启动；示例配置带上声明 |
| **M3** 19 条 warning 规则只有判定力 | 已量化、无口径 | **进账本**：按严重级别的分布 + 有阻断力 / 只有判定力两个数 |
| **M4** 命令面很窄 | 靠试错 | **拒绝理由带可用替代**（只引用已声明数据，判定不放宽） |
| **M5 / N22** 越界理由 | dsh 侧已带替代 | **Phase 6 侧补齐**（`normalize_event_path` 三处） |
| **N13** 探针走不到 Phase 6 | 登记候补 | **已修 + 变异证红**（12 处不符，其中 6 条 `p6_*`） |
| **N14** 依赖规则靠纪律 | 登记候补 | **已修**：加载期拒绝缺 `language` 的依赖类规则 |
| **11 §5.6** 两个 CLI 口径不同 | 登记候补 | **已修**：统一为仓库根口径（一处实现） |
| **G1** 桌面通道没接线 | PARTIAL | **未变**：本轮按使用者的选择不碰 GUI 通道 |
| **N2** 两套配置口径未合并 | 待办 | **未变**：新字段只加在 Phase 2 侧；仓库自己的 Phase 6 配置因此没带测试层声明 |
| **N25 / N26** 受限沙箱与宿主 ACL | 宿主事实 | **未触碰**；本轮测试统一用仓库自己的 `tmp_root` 夹具绕开 N26 |
| **N27** `exit_code_zero` 的残留语义 | 已缓解、语义未改 | **未变**：属注册表词汇表的策略变更，需要单独一轮 + 重新审核 |
| **N28** 门禁只对跑的那一刻的工作树成立 | 性质 | **未变**；本轮末的全量门禁同样只对那一刻成立 |

## 9. 诚实边界（与结论一起读）

1. **本轮没有第三方独立验收**：三路子会话与 Lead 是同一个模型、同一台机器、同一份仓库，
   写域互不重叠、复核由 Lead 做。这与前几轮的 V1 独立验收**不是一回事**，不能互相顶替。
   Lead 的独立部分只在于：入口不同（配置层 / 生产 Hook CLI / 外部验证器），以及复核时**发现并修掉了三处**
   子会话没写进报告的东西（审计目标文件被脱敏成 `src<abs>`、脱敏正则吃掉仓库相对路径、
   Phase 6 侧缺 M5 那句）。
2. **G3 只在声明并启用 `pre_evidence` 的通道上闭合**：默认部署仍是 Phase 2 契约
   （证据类 checker 进 `skipped_rules`）。把 `pre_evidence` 打开会显著变慢，
   因此这是部署方的策略决定，本轮没有替谁打开。
3. **动手前取证没有端到端压过 `tool.pytest`**（`missing_tests` / `failing_tests`）：
   已证的是内置验证器与 `tool.ruff` 两条；pytest 那条由既有流水线测试守住。
4. **M1 的检查只在声明了 `test_paths` 的配置上生效**：不声明的项目仍会静默误判测试文件。
   这是「不推断」（AGENTS 第 6 条）的代价，不是遗漏。
5. **仓库自己的 Phase 6 配置没有加测试层声明**（`adapters/dsh/adapter.yaml`）：它由 Phase 6 的口径加载，
   字段集合与 Phase 2 不同（N2 未合并），而它的 layers 只影响规范事件路径。
6. **两处既有行为被改**：(a) 绝对路径脱敏加了边界——修前 `tests/test_x.py` 这种相对路径也会被吃掉；
   (b) `validators.cli` 目标文件不存在时退出码 1 → 2（把「用错了」与「证据不足」分开）。
   两处都有测试与理由，也都写进了这一轮。
7. **仪器与证据都在 `.tmp/round-07/`**：`tools/cleanup.py` 会把它们一起删掉；
   本文件的每个数字都能按 §10 重算。
8. **本轮改动尚未提交**（先把证据写全，提交留给使用者）。

## 10. 复现

全部命令在仓库根执行；跑仓库模块前设 `$env:PYTHONPATH='src'`，解释器 `python` = `C:/Users/ZNM/miniconda3/python.exe`。

    # 1) M1：配置层双向对照 + 生产 Hook CLI 三臂（off / 顺序错 / 修好）
    python .tmp/round-07/harness/probe_m1.py --json .tmp/round-07/evidence/m1-probe.json
    python .tmp/round-07/harness/probe_m1_hook.py --json .tmp/round-07/evidence/m1-hook-probe.json

    # 2) G3：动手前取证（Lead 的独立入口，压外部验证器 tool.ruff）
    python .tmp/round-07/harness/probe_pre_evidence_ruff.py --json .tmp/round-07/evidence/pre-evidence-ruff.json

    # 3) N14：加载期检查（43 条规则照常加载 + 缺 language 被拒 + 正对照）
    python .tmp/round-07/harness/probe_n14.py --json .tmp/round-07/evidence/n14-probe.json

    # 4) N13：缺口探针（13 项 × before/after）
    python tools/governance_gap_probe.py --root . --phase after --repeat 2

    # 5) 全量门禁（**串行**：同一工作树同时只允许一个 ci_local）
    python tools/ci_local.py

产物（`.tmp/` 内，构建产物不提交）：

| 路径 | 内容 |
| --- | --- |
| `.tmp/round-07/harness/` | Lead 的四支探针（M1 配置层、M1 Hook、G3 取证、N14） |
| `.tmp/round-07/evidence/` | 每次运行的原始 JSON |
| `.tmp/round-07/red-green/` | 三个子会话的红→绿输出（a1 / a2 / a3） |
| `.tmp/round-07/pre-evidence-ruff/` | G3 探针的受控项目与规则夹具 |
| `.tmp/round-07/a3/` | N13 的变异体（`git archive HEAD` 副本 + textfacts 四处替换） |

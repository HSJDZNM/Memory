# Post-Phase-5 独立复核记录

> 本文不是阶段计划，而是对**已交付的 Phase 5**（以及它触碰到的 Phase 0–4 接口）做的一次独立复核。
> 时间：2026-09-18。实施者与复核者是同一个人（AI 编码代理），但**方法上刻意隔离**：
> 复核由两个**独立子会话**完成，它们看不到实施记录以外的自述，只拿到阶段计划书的上半部分
> （目标 / 契约 / 测试步骤 / 退出条件），并被告知"实施记录视为不可信，凡进结论的事实必须自己跑出来"。

## 1. 为什么又做一次复核

Phase 5 的产出有个特点：它的正确性主张（"ARCH-001 完全由 AST 证据判定"、"关键验证器不可用一律失败关闭"）
**本身就是安全主张**。自带测试与实现同源，同源出错时两边一起错。因此这一轮的判据是：

1. 计划书的五条退出条件，能不能用**外部观察**复现？
2. 有没有"看起来有保护、实际没有"的中间态？（声明了却不执行的数据、永远不会触发的规则、只写不查的开关）
3. Phase 0–4 的既有承诺有没有被新规则集与新默认链路破坏？

## 2. 复核方法（两条互不重叠的线）

| 线 | 复核者 | 范围 | 约束 |
| --- | --- | --- | --- |
| A | 子会话 A | 验证器层：AST/依赖图、外部工具适配器、测试验证器、失败关闭、证据可重放 | 只读；临时脚本写在 `.tmp/review-a/` |
| B | 子会话 B | 协议与回归：决策协议未变、`policy_version` 一处真相、checker 词表跨层一致、加载不变量、文档命令可执行性 | 只读；临时脚本写在 `.tmp/review-b/` |

两条线都被禁止运行主会话正在跑的四个脚本与全量 pytest，避免互相干扰；
所有结论都必须附"复现命令 + 观察到的输出"，并标注是**代码缺陷**还是**文档漂移**。

## 3. 复核确认成立的主张（节选）

- 决策协议确实没被 Phase 5 改动：`SCHEMA_VERSION = "1.0"`，四份快照与代码产出**逐字节一致**
  （599 / 509 / 1007 / 1019 字节），载荷 10 个字段与键序同 Phase 4 完全相同，未知字段仍被拒；
- `policy_version` 一处真相成立：模型常量 / 四份快照 / 阶段证据 / CLI 文本 / CLI `--json` 全是 `phase-1`；
- checker 词表三层一致（模型允许的 == 引擎分派的 == 注册表声明的，共 6 个，且 CONTEXT 与 EVIDENCE 不相交）；
- 加载不变量全部成立：未知 checker、规则体与 checker 不一致、重复 id、目录不存在都报错；
  空目录是合法空规则集；加载失败不留半套；`identity` 与加载顺序无关；排序稳定；
- 失败关闭实测有效：把注册表改成 `critical: false` 并让 Ruff 真缺失，引擎仍以
  "没有验证器为 checker style_lint 提供证据" 阻断（二道防线真的存在）；
- "scope 命中却没有证据仍 allow" 构造不出来（唯一例外是显式 `--dependencies`，见 `5 边界）；
- 超时确实终止**整棵进程树**：假工具派生的心跳孙进程在超时后被终止（心跳文件停止增长）；
- 证据可逐字节重放（工具可用与不可用两种情形），无 `duration_ms`、无绝对路径、无凭据；
- 只提供上下文的调用路径（真实 dsh Hook）没有静默放行：5 条证据类规则全部进 `skipped_rules` 并写明原因。

## 4. 复核发现的缺陷与修复

| # | 级别 | 问题（复现见下） | 处置 |
| --- | --- | --- | --- |
| A-F2 | 重要 | `from shop import order_repository` 形态**不产生依赖边**——依赖停在包名 `shop`，ARCH-001 漏判 | 已修：from-import 的每个名字再探一次 `<module>.<name>`，仅在本项目内解析成功时补边（`from pkg import ClassName` 不会变成"未解析依赖"） |
| A-F3 | 重要 | `from importlib import import_module as im; im(name)` 绕过动态 import 门禁（识别只看调用名，不追绑定） | 已修：AST 事实新增 `bindings`（含别名），动态 import 入口按绑定识别；常量参数还能解析出真实模块边 |
| A-F4 | 重要 | 工作区只要存在**任意一个**测试文件，`suite` 升级就永远命中 → `TESTING-001` 等价死规则 | 已修：把"跑什么"（related → package → suite）与"有没有对应测试"（只看 related/package）分开；升级不再冒充"带了测试" |
| A-F5 | 重要 | 注册表声明 `defaults.max_evidence: 200`，**零消费者**：500 条诊断全部进证据 | 已修：流水线按上限截断，并把"截断了多少条"写进验证器记录与报告（`truncated_evidence`），不静默丢证据 |
| A-F8 | 次要 | `--language go` 时全部规则 scope 落空 → `allow`（"不了解这个语言的规则"却说通过） | 已修：声明的语言没有 rule pack 一律配置错误（退出码 2），两个 CLI 一致 |
| A-F6 | 次要 | 注册表声明实现里没有的验证器 id，只在运行期报 `config_error`（AGENTS 21 要求加载期） | 已修：`load_registry` 在加载期拒绝（函数内导入避免与 pipeline 成环） |
| A-F7 | 次要 | 工具输出的 `filename="src/shop/../../outside.py"` 被映射成"工作区里存在但不存在"的 `outside.py` | 已修：只接受目标文件或工作区内真实存在的文件，其余回退到目标 |
| A-F9 | 次要 | crash / config_error 的 `reason` 为空；`["{python}", ...]` 声明时证据里的工具名是字面量 `{python}` | 已修：失败原因带工具输出摘要（已脱敏）；工具名按 `tool_label` 解析 |
| A-F10 | 次要 | `--changed "src/../../outside.py"` 一路带到选择阶段，以 `crashed` 形式失败关闭 | 已修：变更集在进入流水线前校验，非法即配置错误（退出码 2） |
| A-F11 | 次要 | 非 UTF-8 目标在 CLI 的报告阶段被当成配置错误（退出码 2），与 NUL/超大的 `block` 分类不一致 | 已修：报告用的导入列表读失败不再中断运行，交给流水线按失败关闭给出 `py.source failed` |
| A-F15 | 次要 | 测试选择被 node id 上限**静默截断**（46 → 40，无说明） | 已修：`TestSelection.truncated` + 原因文本，截断可见 |
| B-F2 | 重要 | 文档命令 `retrieval.cli context ... --decision decision.json` 引用的文件全仓库不存在；且 `_decision_facts` 未捕获 OSError → 裸 traceback + 退出码 1（CLI 契约是 2） | 已修：读不到 / 非 JSON 一律 `config error`（退出码 2）；README 与 phase-3 文档改成"真实存在的载荷"，并给出 generate-then-consume 的完整链路 |
| B-F1 | 次要 | README 与 phase-5 文档的用例数过期（110 / 806） | 已修：改为当前实测值（492 / 112 / 189 / 34，合计 827） |
| B-F3 | 次要 | 文档承诺"不传 `--layer` 时按文件名推断并**标明**"，输出里没有任何标明 | 已修：文本输出标注"（由文件名推断，未显式声明）" |
| B-F4 | 次要 | README 的 Phase 5 一节没写"需要 PATH 上有 Ruff"的前提，干净机器上正例必然变红 | 已修：写明前提与自查命令 |
| B-F5 | 次要 | 根 README 的手册索引只到 Phase 4 | 已修：补 Phase 5 行与目录说明 |
| B-F7 | 次要 | `missing_tests.changed_only` 无读取点（改成 `false` 行为不变） | 已修：真正执行——`false` 表示"不依赖变更集，也要对目标文件判有没有对应测试" |
| B-F8 | 次要 | `validators.cli` docstring 称"退出码 1 = 关键验证器不可用"，实际 `probe` 恒返回 0 | 已修：注释写明 probe 只报告、判定时才失败关闭 |
| B-F9 | 设计边界 | "向量检索没有跑赢 FTS5" 只在 precision 轴成立（recall 反而更高） | 已修：措辞改成给出两项指标与门槛关系 |

每条修复都带回归用例：`tests/unit/test_validator_hardening.py`（11 条）与
`tests/integration/test_validator_hardening_cli.py`（9 条），另有两条既有对抗用例按新语义更新
（未实现验证器改为加载期拒绝、非法变更集改为进入流水线前拒绝）。

## 5. 记为边界的发现（不改代码，写清楚）

1. **`--dependencies` 是显式旁路**（A-F1）：它用调用方声明替换 AST 证据，可以给出与默认路径不同的结论。
   这是 Phase 0–4 的历史契约（重放旧示例要用它），语义在阶段文档与 `--help` 里写明；
   它不是"绕过失败关闭"——声明本身也是证据来源（记成 `cli.explicit@1.0`），只是来源不同。
2. **只提供上下文的调用路径用 `context.dependencies` 判 ARCH-001**（A-F12）：Phase 2 的 Hook 契约不变，
   证据类 checker 的规则进 `skipped_rules`（审计只记规则 ID、不记原因文本，这是 `hooks.py` 的既有口径）。
   把验证器接进 Hook 属于 Phase 6。
3. **验证器临时目录跟随 `--config-root`**（A-F13）：目录在 `<config-root>/.tmp/validators/<run>/<validator>`，
   各验证器互不覆盖、用完即删；这是"配置根决定产物位置"的既有约定。
4. **符号链接逃逸在本机无法实证**（A-F14）：Windows 需要开发者模式，实施者与复核者的对应用例都被 skip；
   CI（Linux）会真的跑到它。

## 6. 验证证据

- **用例**：828（复核前 808；新增 20 条复核回归，另按新语义更新 3 条既有用例）；
- **本机门禁**：`tools/ci_local.py --full` 除"Real dsh sandbox loop"外全部退出 0；
  该步在**被沙箱化的会话**里失败（嵌套 dsh 会话在到达 Hook 前被拒、审计为空 → `diagnosis: Hook 从未被调用`），
  这是 Phase 2/4 已记名的环境边界，不是本阶段回归，也不在 pre-push 钩子的步骤组里；
- **验证器闭环**：`tools/validator_loop.py` 10/10 场景通过；
- **阶段证据**：`tools/phase_evidence.py` → `phase 5 / result pass / failures 0`。

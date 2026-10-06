# Open Code Review（alibaba）与本项目对比报告

> 对比对象：**A 侧** = [alibaba/open-code-review](https://github.com/alibaba/open-code-review)（Go，本地只读副本 `.tmp/ocr`，commit `182898c`）；
> **B 侧** = 本项目 Engineering Policy Platform（Python ≥ 3.11，src 布局）。
> 组织形式：四个子会话分别取证 A/B × D1D2/D3D4，两两交换小结做交叉确认（4 份），再由独立核验员回源抽样复核。
> 核验规模：回源断言 30 条（A 13 / B 17）+ 冲突条目 13 条 + 模板抽查 4 份 = 47 条。
>
> **时点说明（2026-10-06 补）**：本报告取证于 `3f7eed9`。此后仓库做了文档收敛——学习手册与它的生成器、
> 过往轮次记录、全部 draw.io 图与 PNG、`tools/check_arch_canon.py` 均已删除。
> 正文里凡提到这些文件（例如把 `check_arch_canon.py` 当现存文件、或把 45 / 46 个 CI 步骤、
> `tools/` 顶层 `.py` 的 26 / 34 当作现读数）**都是 `3f7eed9` 时点的读数**；
> 现口径以 `docs/project/architecture/术语与口径.md` §5 为准。

## 证据等级（本报告每条结论都带等级，不得混读）

| 等级 | 含义 |
| --- | --- |
| 【已核验】 | 独立核验员回源复算过，附命令与结果；可直接引用 |
| 【作者读数】 | 某一侧分析师读代码/文档得到，未独立复算；引用时保留限定词 |
| 【不可核】 | 本环境无法取证（无 Go 工具链、禁跑测试、不联网）；**不得当作事实** |

**必须先读的口径纪律**：两侧数字不能直接比大小。行数一律用 `ReadAllLines`（或 `Get-Content -Encoding utf8`）——
本机 `pwsh` 实为 Windows PowerShell 5.1，默认 gb2312，会把中文行合并；
`Get-Content | Measure-Object -Line` 还等价于"非空行"。Lead 最初读到的 `46384` 行正是这两条原语的产物，
与权威值 `49709` 的 3325 行差**全部来自编码合并**（文件集合完全相同，114 个 .py，双向差集为空）。【已核验】

## 0. 数字口径换算表

| 概念 | A 侧（OCR/Go） | B 侧（本项目/Python） | 可比性 |
| --- | --- | --- | --- |
| 代码规模 | `internal/` 79 072 + `cmd/` 32 810 行；364 个 `.go`【已核验】 | `src/` 114 个 `.py` / 49 709 行（另有 3 个非 .py 共 1 790 行）【已核验】 | 不可直比：A 未含 `scripts/`，且原始数法口径不同 |
| "规则" | 54 份提示词文档 / 2 478 物理行；**可判定 0 条**【已核验】 | 43 条 YAML；**可判定 43 条**（6 个 checker）【已核验】 | **同名异义**，任何数量并列都是伪对比 |
| 覆盖面 | 115 个扩展名（允许清单；0 个语言解析器）【已核验】 | 1 门语言（python）；`text` 显式声明不取证【作者读数】 | 声明面 vs 判定面 |
| 测试 | `func Test` 2 506 / 234 个测试文件；`t.Run` 655；Benchmark、Fuzz 均 0【已核验】 | 四套件 `def test_` 1 684 / 套件文件 102；`parametrize` 89【已核验】 | 函数数可比，**执行用例数两侧都不可测** |
| 运行读数 | 无（无 Go 工具链，全部【不可核】） | junit `tests="2136"` 在 `14f66a22`-dirty 上 0 失败；HEAD `3f7eed9` **未重跑**；已保存 4 次 CI 全红【已核验】 | 不可对称陈述 |
| 覆盖率门槛 | 90%（`Makefile` + `ci.yml`）【已核验】 | **无**（只有 `[tool.coverage.run]`，无 `fail_under`、CI 无 `--cov`）【作者读数】 | 实质差异 |
| CI 规模 | 12 个 workflow；主门禁 `ci.yml` 25 个步骤条目 / 3 job；12 文件合计 103 条【已核验】 | 1 个 workflow；45 个 `- name:` + 1 个匿名 `- uses:`；1 个 job【已核验】 | 分母不同，量级陈述 |

## 1. 功能效果（D1）

### 1.1 解决的问题与目标用户

- A 侧是**评审工具**：读 git diff，把变更文件交给具备工具调用能力的 LLM Agent，产出**逐行定位的评审意见**；
  `ocr scan` 再把整文件纳入范围（审计无 diff 的目录）。目标用户是"要在 PR 上看到评论的人"。【已核验（README 与入口）】
- B 侧是**治理/门禁平台**：判定"这次动作能不能做、依据是什么"，产出 Decision（allow / allow_with_warnings / block）
  与可复盘证据；目标是"让判定可复算、可审计、失败关闭"。【已核验（CLI 与决策载荷）】
- 一句话对照：**A 的产物是"意见"，B 的产物是"判定"**——这决定了两侧后面所有差异。

### 1.2 输入 → 输出

| | A 侧 | B 侧 |
| --- | --- | --- |
| 输入 | git 工作区/diff、模型端点、宿主（Claude Code / Codex / Cursor / Kimi Code） | 规则集（43 YAML）+ 显式上下文 + 验证器证据 |
| 输出 | 终端/JSON/SARIF/评论、`RunManifest`（覆盖账本） | 决策载荷（schema 1.1）+ 证据 + 审计 JSONL + 契约快照 |
| 门禁可用性 | 退出码 0/1，**部分成功也退 0**，无 severity 阻断开关 | 退出码 0/1/2（另有 `provenance` 的 3），`block` 与 `allow_with_warnings` 都会非零退出 |

### 1.3 覆盖面：两种不同的"宽"

- A 宽在**输入面**：115 个扩展名、54 份规则文档、6 个宿主插件、6 套 CI 模板；窄在**判定面**——仓内 0 个 AST/lint 判定组件，
  规则是喂给模型的自然语言提纲（`path_rule_map` 54 条 → 53 个文档 + `default.md`，`system_rules.json` 注入 `{{system_rule}}`）。【已核验】
- B 宽在**判定面**：43 条规则全部可判定，7 个验证器提供证据；窄在**语言面**——43/43 规则声明 `language: python`，
  非 Python 只有"失败关闭"或"声明为不取证"两条路（当前仅 `text`）。【已核验（数量与语言）、作者读数（不取证清单）】

### 1.4 质量与可信度的保证机制

- A：确定性前置（选文件闸门、分组兜底、按文本滑窗定位、跨文件唯一命中改判）+ 二次 LLM 复检（证据不足时**保留**评论，
  显式写明不对称损失）+ 覆盖账本 + 90% 覆盖率门禁。**仓内没有任何评测脚本/数据/基线**：README 的 benchmark
  （50 仓库 / 200 PR / 10 语言 / 1 505 条标注 / Precision·F1 / 约 1/9 token）只有 5 张 `imgs/benchmark-*.png` 佐证。【已核验】
- B：固定评测集（7 查询 + 门槛 + `baseline-v3.json`，`fts5 passed=true` 且如实记录 `vector passed=false`）进 CI 硬门禁，
  判定可离线重跑；但**检索命中率不等于评审质量**，规则命中率/误报率两侧都没有数据。【已核验】
- 结论：**"效果好不好"这一格两侧都缺可信数据；B 的胜出项只是"可复现"**，不是"更准"。

### 1.5 失败模式：对偶的默认档

- A：**尽量出结果**——部分成功照发、退出 0；"没查到"通过 `terminal_state{complete,partial,failed,skipped}` 与 coverage 五集合显式记账；
  唯一越界是未知 severity/category 静默降级为 `low`/`other`（`tool/code_comment.go:176-190`）。【作者读数】
- B：**没有证据就不通过**——某个 checker 没有验证器供证即 critical 阻断；warning 也让 CLI 退 1；
  "待实现"与"按设计不取证"是具名状态而非静默（`pending_findings` 独立通道，severity 在构造期钉死 warning）。【作者读数】

### 1.6 可观测与可审计

- A 审计"这次怎么跑完的"：覆盖账本、重试分类（不读错误文本）、token 与耗时。
- B 审计"这条判定凭什么"：`violations` / `skipped_rules` / `evidence` / `rule_set_hash` + 按级别分布、追加写摘要链（可锚定）。
- 两者互补，不构成优劣；**两侧都不用进程日志库**（A：`log/slog/zap` 0 命中、79 处裸 `Fprintf`；B：`logging` 0 命中）【作者读数】。

### 1.7 可运行性证据的成色（唯一一处必须逐字限定的事实）

- B 侧唯一 0 失败读数是 `.tmp/artifacts/tests-all-report.xml`：`tests="2136" failures="0"`，2136 个 `<testcase>`，
  内部时间 2026-10-06 02:16–02:24；其 `implementation_version = 14f66a22…-dirty`，**落后 HEAD `3f7eed9` 5 个提交**
  （`git rev-list --count` = 5；`git diff --stat` 7 个文件，含 `src/adapters/dsh/adapter.py`、`src/adapters/wiring.py`）。
- `.tmp/ci-logs/` 保存的 4 次远端 CI **全部为 `3 failed, 2130 passed`**，3 条 FAILED 用例名四次逐字相同，
  与之后的 3 个修复提交（`5518c48` / `52f92c3` / `d503263`）主题一一对应，**修复后没有任何一次运行记录**。【已核验】
- 因此正确表述是："本机记录过一次 2136 例全绿（旧 revision）；当前 HEAD 是否绿**无证据**"，
  既不能写"B 全绿"，也不能写"B 当前是红的"。
- A 侧任何运行期结论（能否构建、2 506 个测试能否通过、90% 覆盖率是否达标）在本环境【不可核】（无 Go 工具链）。

### 1.8 明确不做什么

- A：不做确定性代码判定（0 checker）；不阻断（无 severity 门禁）；不做 MCP 服务端（只有客户端）；仓内不做 benchmark 复现。
- B：不调用模型做判定；不发现"规则之外"的缺陷——规则没写的，平台**不知道**；不覆盖 Python 之外的语言。

## 2. 实现方案（D2）

### 2.1 核心对照：不确定性放在哪里

| | A 侧 | B 侧 |
| --- | --- | --- |
| 不确定性位置 | **在判定内容里**（由模型写评论） | **被移出判定链**（判定是纯函数） |
| 约束方式 | 确定性前置筛选 + 文本定位优先 + 二次复检 + 覆盖账本 + 90% 覆盖率 | 输入只有（规则, 上下文, 证据），三者都有版本与哈希；未知即报错；缺证据即阻断 |
| 残留风险 | 模型自报 severity/category 非法时静默降级 | 规则表达力被 6 个 checker 锁死；非 Python 目标结构性不取证 |

B 侧四个"不确定性入口"都在判定链之外或之后：外部工具 stdout（只作不可信数据，无规则归属的诊断只计数）、
语料漂移（写进 report 并让 `verify` 退 1）、编排层的候选改动（`ChangeAuthor` 是 Protocol，仓库内唯一实现是确定性 `ScriptedAuthor`）、
人工审批（绑平台口径 `action_hash`）。【作者读数，关键行号已核验】

### 2.2 关键取舍对比

- **A 的技术债方向是"把不听话的模型框住"**：分组兜底、token 闸门、定位模块、复检模块，都是为概率组件服务的确定性护栏。
- **B 的技术债方向是"把判定变成可复算对象"**：版本轴、审核哈希、契约快照、失败关闭分支、审计摘要链——大量成本花在约束自己，而非扩大覆盖面。

### 2.3 规则与配置的数据化

- A：规则文本、工具 schema、提示词是数据；**超时写死在代码**（24 处 `context.WithTimeout`）。【作者读数】
- B：规则、验证器注册表、工具注册表、Adapter 能力声明、测试布局全部 YAML 化；"改行为不改代码"覆盖面更宽。【已核验（规则与注册表存在性）】

### 2.4 集成点

A：CLI（10 个命令 + 15 个子命令）、6 个宿主插件、6 套 CI 模板、3 个 IDE 扩展、MCP **客户端**；
B：3 个 Adapter（仅 dsh 是真实产品，另 2 个是合成协议消费者）、无 HTTP 客户端集成、MCP 只存在于文档与语料里。

## 3. 代码结构（D3）

### 3.1 划分与规模

- A：Go 单模块，`cmd/opencodereview` + `internal/` 18 个目录（**17 个含生产代码**，`internal/release/` 只有测试文件）；
  25 个 Go 包目录，**无 `pkg/`**，不可作为库嵌入。【已核验（行数与目录）】
- B：`src/` 8 个包（policy / retrieval / validators / enforcement / adapters / policy_api / orchestration / provenance）；
  核心层刻意不依赖 Web 框架与工作流框架，`tests/contract/` 有断言钉住这两条。【已核验】

### 3.2 依赖方向与分层约束的自动化（本对比最大的能力落差）

- A：**0 条自动化**。全仓无 `go/packages`、`go list` 之类的依赖检查，无 `.golangci.yml`、无 `.editorconfig`；
  分层只靠 Go 的无环编译规则与人的纪律。【已核验】
- B：5 处可执行检查（3 条文本正则 + 1 条子进程真导入 + 1 条 CLI 自检），但**都不覆盖包级环**：
  `src/policy/check.py:70-73` 模块级导入 `validators`/`provenance`，`tests/contract/test_validator_protocol.py:43`
  的 `CORE_MODULES` 只列 7 个核心模块（不含 `check`）——约束对 core 成立，对 `check.py` 是**显式豁免**。
  该豁免写在注释里、没有用例钉住"check.py 允许例外"。【已核验】
- 换位对照：A 侧有"同一份工具集在数据与代码里各声明一遍"的同型问题——
  `tools.json` 6 条 / `definitions.go:17-25` 6 条 / `review_cmd.go:614-618` **只注册 5 个**，第 6 个 `task_done` 在
  `llmloop/loop.go:632` 被特判，**无 parity 测试**；B 侧对这一型有检查（ruff 码双向一致、manifest ↔ TOOL_TABLE）。【已核验】

### 3.3 边界与契约

- A：6 个生产 interface（`tool.Provider` / `llm.LLMClient` / `llm.RawWriter` / `rules.Resolver` / `rules.DetailResolver` / `rules.systemLayer`）
  + 5 个测试用；契约**无入库快照**。【已核验（interface 数）、作者读数（快照）】
- B：12 个 `typing.Protocol` + **8 份入库契约/审核快照**（4 份决策快照 + OpenAPI + 2 份 approved + host-versions），
  两个显式更新开关（`POLICY_UPDATE_SNAPSHOTS=1`、`openapi --write`），CI 用 `--check`。【已核验】

### 3.4 测试布局

- A：234 个 `_test.go` / 2 506 个 `func Test`，测试文件:生产文件 = 1.80；无分层套件，无 fuzz/benchmark。
- B：四套件（unit / contract / integration / security）102 个套件文件 / 1 684 个 `def test_`（897 / 304 / 407 / 76）；
  `tests/` 被跟踪文件 239 个（含 133 个夹具文件），夹具自身另有 1 条 `def test_`（故"全 tests"口径为 1 685）。【已核验】
- 两个口径都只是**函数级下界**：`t.Run` 655 与 `parametrize` 89 的运行期展开数在禁跑测试的条件下不可测。

### 3.5 扩展代价

新增一条规则：A 改一份提示词文档；B 要写 YAML + 正反例夹具 + 语料登记（`standard` 类还必须双向一致 Ruff 码）。
换来的差别是：A 的新规则**不可判定**，B 的新规则**会被真实验证器流水线执行**。

## 4. 代码实现规范（D4）

### 4.1 两种"AGENTS.md"：开发期纪律 vs 运行时治理

- A 的 `AGENTS.md`（67 行）规范**写代码的人与 AI**：AI 使用披露 8 条、注释只解释"为什么"、源码必须全英文
  （`make english-check` + `scripts/verify-english-only.go` 278 行，带 `allow-non-english` 逃生舱与 `allowedPrefixes` 清单）、
  每个源文件必须有 SPDX 头（`make license-add`）、README 改动要同步 4 个语种、提供者注册表改动要重跑 `go generate` 并提交 TS/Kotlin 生成物。【已核验（文件与门禁存在性）】
- B 的 `AGENTS.md` 规范**被治理对象与协议**：56 条编号约束（未知即报错、失败关闭、版本轴与快照纪律、审计脱敏、审批绑 action_hash……），
  由契约测试、门禁脚本与协议快照钉住。
- 结论：**两者都把规范写进仓库并尽量交给自动化，但规范的"被约束者"完全不同**——A 约束贡献者，B 约束平台自身。

### 4.2 格式化与 lint

- A：无 `.golangci.yml`、无 `.editorconfig`；"配置"就是命令本身——`Makefile` 的 `gofmt -s -w .` / `go vet`、
  `ci.yml:49-57` 的 `gofmt -s -l .`；另接 govulncheck、CodeQL、action pin 检查。【已核验（无配置文件）、作者读数（CI 步骤）】
- B：`.editorconfig` + `validation/ruff.toml` + `validation/mypy.ini` + `pytest.ini` + 文本规范检查器（`check_text_conventions.py`）+
  仓库一致性检查器；但**myPy 进核心依赖前不启用 `type_check` 规则**、ruff 只选中的码有规则归属（双向一致由契约测试守）。【作者读数】

### 4.3 错误处理与失败语义

- A：退出码只有 0/1（`cmd/opencodereview/main.go:27-31`），"用户错误 / 依赖不可用 / 内部崩溃"压成同一档；
  生产 panic 10 处，`run()` 无 `recover`（单文件级隔离，进程级不隔离）。【作者读数】
- B：退出码分四套语义，必须分开写——0/1/2（`policy.check` 等 7 个 CLI）、`provenance/cli.py:35-38` 的 **3**、
  `policy_api/serve.py` 的 2（配置不可用）/ 3（readiness 未通过）、Hook 的 0 放行 / 2 阻断（跨语言）。
  把它说成"B 统一 0/1/2"是错的。【已核验】

### 4.4 类型与契约纪律：本对比最尖锐的对立

| 情形 | A 侧 | B 侧 |
| --- | --- | --- |
| 未知字段 | 全仓 **0 处** `DisallowUnknownFields`，静默忽略【已核验】 | `StrictModel` `extra="forbid"`（`src/policy/models.py:337-341`）为基线，端到端由 `phase-8.yml:319-323`（`surprise:1` → 400 `body_invalid`）钉住【已核验】 |
| 未知版本 | **同一仓库两套口径**：恢复路径硬拒（`session/resume_identity.go:96`）、展示路径降级并标 `Legacy`（`viewer/store.go:812,825-827`）【已核验】 | 一律拒收（含决策协议 1.0 载荷），"这次没查/查不了"走具名状态（`PENDING_IMPLEMENTATION`、`not_covered_by_design`、`skipped`）【作者读数】 |
| 例外 | 无成文禁令，故无"例外"一说 | `policy_api/app.py:50` 的 `extra="ignore"` 仅服务 `_handshake` 文档模型；`RuleScope` 的 `extra="allow"` 默认仍 REJECT【已核验】 |

### 4.5 安全与脱敏

- A：`ASSURANCE_CASE.md` 是仓库唯一成文安全文档（76 行，T1–T7）；作者对账认为 T1（"外部命令只有 git"）与 T6
  （"JSON schema validation"）表述过强，T5（TLS）未核——该对账本身**未经独立复核**，引用时须保留限定词；
  其"agent shell tool 不存在"的判定**已被核验撤回**：`cmd/opencodereview/shell_unix.go:13` 定义了 `shellCommand`，
  唯一调用点在 MCP setup（`review_cmd.go:571`），文档与代码一致。【已核验（撤回）】
- B：脱敏在构造期完成（密钥、绝对路径、控制字符），单条超限即失败关闭；审计链是"摘要链不是防篡改日志"这一口径写进了规范与文档。

### 4.6 文档、生成物与数字一致性

- A：1 条生成物门禁（`internal/llm/gen -check` 校验 TS/Kotlin 生成物）；**没有任何数字校验器**——
  已证三处漂移（CONTRIBUTING 目录树 9 vs 17 个包、`ci.yml:141` 注释 80% vs 同文件 90%、Go 版本三处不一致）。【作者读数】
- B：3 条生成物 `--check` 门禁（notebook、tech-detail、OpenAPI），但"术语与口径.md"的数字表自身已漂移
  （CI 步骤 46→45、tools 顶层 .py 26→34 等），且 `check_arch_canon.py` / `check_arch_style.py` **不在任何门禁里**。【作者读数】

### 4.7 提交规范与门禁完整性

- A：提交信息有文字规定+英文要求，**无 hook、无 CI 检查**（且 shallow clone 只剩 1 个 commit，遵从度不可测）。
- B：Conventional Commits 有规定、**无自动检查**（实测 226/238 合规）；`ci_local.py` 有 `unregistered_steps()`
  这类"没接线就报错"的防线——A 侧没有同型机制（A 的 `manual_e2e` 测试从不运行、`make check` 漏掉 action-pin / govulncheck / 覆盖率门槛）。【作者读数】

## 5. 交叉确认与独立核验：哪些结论被改写了

四份交叉确认的判定：**【一致】52 条、口径不同实为同一事实 31 条、冲突 13 条、无法核实 5 条**。
独立核验把 13 条冲突逐条裁定：**冲突成立 4 条、一方错 1 条、双方都对但口径/结构不同 8 条、无法核实 0 条**。

被核验改写或撤回的结论（这就是"再确认细节一致"的实际产出）：

1. **Lead 的 `46384` 行作废**：是 PowerShell 5.1 默认 gb2312 的读数，差值 3325 行全是编码合并；权威值 49 709。【已核验】
2. **A 侧行数全部修正**：`internal` 71 850 → 79 072、`cmd` 29 796 → 32 810；`rule_docs` 2 076 → 2 478 物理行；
   `ci.yml` 170 → 196。原因同上（坏原语 + 编码叠加）。【已核验】
3. **A 侧"agent shell tool 不存在、文档错"撤回**（见 4.5）。【已核验】
4. **A 侧生产 interface 6 个而非 5 个**（漏 `rules.systemLayer`）；12 个 workflow 步骤条目 103 条而非"约 80"。【已核验】
5. **B 侧 src 行数 51 499 是"全类型文件"口径**，纯 .py 是 49 709；"117 个 .py"是贴错标签，.py 是 114 个。【已核验】
6. **B 侧入库快照 8 份而非 6 份**；`def test_` 有 1 684（四套件）/ 1 685（全 tests）两个口径，均真。【已核验】
7. **"B 全仓零静默降级"必须降级**：只对 `src/policy/`（0 / 57 处宽 except）成立；全 `src/` 有 57 处宽 except、
   19 处 except 体只 `pass/continue`，反例 `src/enforcement/executor.py:381 except LedgerError: pass`（吞掉台账追加失败）。【已核验】

**必须标注"存疑/不可核"的清单**：A 侧全部运行期读数与 benchmark 数值；B 侧"当前 HEAD 全绿"；
两侧"规则判得准不准/误报率"；`ocr-d3d4` 中未独立复核的 5 条结构对立（转述级）；
"冲突"一词在四份报告里用法不一致——本报告统一为：**只在"同一仓库自述 vs 代码"处用"冲突"，两侧做法相反一律写"结构差异"**。

## 6. 结论（不排名，按四维度各给一条）

1. **功能效果**：A 是"减少评审人力"的**生成型工具**，B 是"防止不该发生的动作发生"的**门禁型平台**；
   两者的质量证据都薄——A 的 benchmark 不可自证，B 只有检索基线，**没有任何一侧有"规则/评论准确率"数据**。
2. **实现方案**：A 把不确定性留在内容层并用工程护栏围住，B 把不确定性赶出判定链并用失败关闭兜底。
   这不是优劣，而是"产物能不能阻断"的必然推论：**A 不阻断所以敢让模型说话，B 阻断所以必须可复算**。
3. **代码结构**：B 的结构约束有自动化（5 处可执行检查 + 3 条硬断言），A 的结构约束**完全靠 Go 编译规则与人的纪律**；
   但 B 也有反例（`check.py` 的显式豁免、`policy ↔ validators` 包级环），A 也有换位反例（工具表 6/6/5 无 parity 测试）。
   这一维度 B 领先，且领先幅度可量化。
4. **实现规范**：A 的规范面向**贡献者行为**（英文强制、SPDX、覆盖率、生成物同步），B 的规范面向**平台协议**
   （未知即拒绝、版本轴、快照、失败关闭）；两侧最尖锐的对立在"未知字段/未知版本"：A 静默忽略 + 两套版本口径，
   B 一律拒收 + 具名状态。

**可互相借用的四条**：① B 可借 A 的覆盖率门槛与依赖/漏洞扫描；② B 可借 A 的"生成物 `-check` 之外再加数字校验器"做法，
但要先把自己的口径表修好；③ A 可借 B 的"未知即拒绝 + 显式状态通道"；④ A 可借 B 的"接线自检"（`unregistered_steps` 型防线），
它的 `manual_e2e` 与 `make check` 漏项正是这类问题。

## 附录：取证与核验方法

- 口径：`.tmp/ocr-compare/dimensions.md`（四维度子问题 + 三类来源分级 + 输出模板），四个子会话共用。
- 第一轮：`.tmp/ocr-compare/round1-{ocr,b}-{d1d2,d3d4}.md`（四份事实报告）。
- 第二轮（交换确认）：`.tmp/ocr-compare/round2-{ocr,b}-{d1d2,d3d4}.md`。
- 独立核验：`.tmp/ocr-compare/round2-verification.md`（30 条回源断言 + 13 条冲突裁定 + 模板抽查，含可复现命令）。
- 上述 `.tmp/` 路径是构建产物，不提交；本报告只保留结论与证据位置。
- 未做：未跑任何测试/门禁/构建，未联网，未修改 A 侧副本；A 侧全部运行期结论因此标为【不可核】。

# alibaba/open-code-review 的测试方法（含"没有多个资深工程师做人工验证"的处置）

- 分析对象：<https://github.com/alibaba/open-code-review>（Apache-2.0，默认分支 main）
- 快照：main = `182898cf522da3d04157b422752d028417974e19`（= 最新 tag `v1.12.12`，发布于 2026-10-05；仓库 `pushed_at` 2026-10-05T06:43:52Z）
- 访问日期：**2026-10-07**（下文每条【已核验】均在该日取到，不再逐条重复日期）
- 通道：`gh api`（tree / contents / search / pulls）、`codeload.github.com` tarball（解包后本地计数）、Python `urllib`（raw.githubusercontent.com、huggingface.co、datasets-server.huggingface.co、arxiv.org）
- 口径：**只写我实际取到的字节里读得到的东西**。宣传语只作为"被检验的声明"引用，不与记录混同；凡是我自己算出来的数字都写明算法；凡只有自述支撑的都写【待核验】。
- 落到本地的原文与脚本：`.tmp/ocr/`（gh 抓的关键文件）、`.tmp/ocr-src/flat/`（tarball 解包，扁平命名）、`.tmp/ocr-hf/`（HF 与 arXiv 原文）、`.tmp/ocr-*.py`（可重放的取数与计数脚本）。这些是临时产物，不入仓。
- 姊妹文档：同目录 `aacr-bench-数据集核验.md` 逐条核验了 HF 数据集的内容与许可；本文只引用它的结论处会显式标注。

---

## 0. 结论先行

1. **这是一个"工程化 + Agent"混合的代码评审 CLI（Go），测试的重心不在"评得准不准"，而在"流程不能出错"。** 仓库里 234 个 Go 测试文件、2,505 个 `func Test`、75,794 行 Go 测试代码，对应 130 个非测试 Go 文件、36,367 行非测试 Go 代码（**测试:实现 ≈ 2.08:1**）；核心手段是假 LLM/假 HTTP 服务 + 进程内全链路装配。[E01][E02]
2. **唯一的"质量数字门槛"是覆盖率：CI 与 Makefile 都硬卡 90% 语句覆盖率**，另有 `go vet`、`govulncheck`、`-race`、CodeQL 与 12 个 workflow 组成的门禁；**没有**针对"评审结论正确性"的自动门槛。[E03][E04][E05]
3. **它有公开基准：AACR-Bench**（200 个真实 PR / 50 仓库 / 10 语言 / 1,505 条专家核验过的真值评论），论文 arXiv:2601.19494 v3，数据集在 HuggingFace（2,145 行 = 1,505 正确 + 640 错误，我逐项复核过这两个数）。[E06][E07][E08][E09]
4. **标签来自 80 名资深工程师的三轮标注**：前两轮由标注池**双盲、每条评论由两名不同的人独立标注（按编程语言专长派单）**，第三轮由 **6 人核心专家组**讨论并**裁决冲突**、定终稿——这是论文正文的原话。[E10]
5. **但它没有报告任何标注者一致性（κ/IAA/Fleiss/百分比一致）**：v1 与 v3 全文检索 `kappa` / `inter-annotator` / `agreement` / `Cohen` / `Fleiss` / `IAA` **命中数均为 0**；发布的数据集也没有标注者字段可供复算。[E10][E11]
6. **指标口径只到"Precision / Recall / F1"这一层**：论文对"生成评论怎样算命中真值"只写了一句"matching these generated comments against the Ground Truth"，**没有给出匹配规则**（行号重叠？语义相等？阈值多少？）；也没有温度、重复次数、置信区间的完整交代（只在附录写了 Temperature=0.7 / Top_p=0.95 / Top_k=20）。[E12][E13]
7. **它的评测工具链不在开源仓库里**：仓库里没有任何评测脚本、基线文件或门槛文件（文件名与全文检索 `baseline`/`threshold`/`eval` 后只剩网站配图与前端组件）；评测流程只在博客里以 `/release-eval` 技能的形式被描述——"判断发版是否需要跑评测集（**跑一次需要 8 小时**）"，且"**影响核心链路的改动必须先过完整 200-PR 评测集才能发版**"。[E14][E15]
8. **它把"误报/漏报的代价不对称"直接写进了提示词**：评论过滤器只允许删除"diff 能**证明**为错"的评论，证据不足一律放行，内存安全/并发/链接一致性/行为变更等主题一律**否决删除**；LLM 调用失败或解析不出结论时**原样保留全部评论（fail-open 保发现）**，并有测试钉住这个方向。[E16][E17]
9. **"没有多个资深工程师做人工验证"这件事，它的答案是六条替代**：①人工评审仍然存在但只有 1–3 人（治理文件要求"至少一名维护者"，实测 12/12 个抽样合并 PR 都有非作者的人类 APPROVE，全部由项目负责人 `lizhengfeng101` 合并）；②生产遥测（自述 2 万月活、30%+ 采纳率、误报率 <5%）；③200-PR 端到端评测集当发版闸门；④自动化网（2,505 个用例 + 90% 覆盖率 + 竞态检测 + 漏洞扫描 + CodeQL）；⑤把"你必须理解 AI 写的每一行"写成贡献规则并让 PR 模板强制勾选；⑥外部过程审计（OpenSSF Best Practices **Gold**，2026-08-06 达成，我从 bestpractices.dev 的 JSON 核到）。[E18][E19][E20][E21][E22][E23]
10. **它自己承认的局限是"召回换精确"和"真值不可能完备"**：README 直说 "its Recall is lower than general-purpose agents — a deliberate trade-off favoring precision over noise"；论文结论段说 "constructing a fully comprehensive Ground Truth remains a formidable challenge due to the inherent complexity and subjectivity"。[E24][E25]
11. **它的自述数字本身在漂移**（这一点比它的测试细节更值得学）：同一份 OpenSSF 自评里同时写着"CI 卡 80%、当前 81.2%"和"CI 卡 90%、当前 90.2%"；写着"项目有 35 个测试文件"（实测 Go 测试文件 234 个）；CI 的 windows job 注释说"Linux job 卡 80%"而脚本里是 90；同一测试文件里函数名与注释写 `twelve` 而断言写 `thirteen`。[E26][E27][E28]
12. **最有价值的可复用做法不是"它的覆盖率是多少"，而是三条"让测试不能假装在测"的机制**：假 LLM 与人工 E2E 共享同一 fixture 防漂移；"这次分组调用到底发生了没有"的显式断言（否则改一句 prompt，覆盖消失而所有断言仍绿）；失败原因枚举与文档计数交叉断言（三处副本曾经漂移过）。[E29][E30][E31]

---

## 1. 它是什么、解决什么问题、代码结构与入口（第 1 问）

**它是什么**（README 原文）：

> Open Code Review is an AI-powered code review CLI tool. It originated as Alibaba Group's internal official AI code review assistant — over the past two years, it has served tens of thousands of developers and identified millions of code defects. After thorough validation at massive scale, we incubated it into an open source project for the community. [E06]

**解决什么问题**（README 原文）：纯语言驱动的通用 Agent 做代码评审有三个痛点——"Incomplete coverage"（大 changeset 会偷懒只审部分文件）、"Position drift"（行号漂移）、"Unstable quality"；它的答案是"Deterministic Engineering × Agent Hybrid"：文件选择、文件分组、规则匹配、定位/反射模块用确定性工程，动态决策与上下文检索交给 Agent。[E06]

**代码结构与入口**（实测 `gh api repos/alibaba/open-code-review/git/trees/HEAD?recursive=1`，共 1,123 个条目）：

| 项 | 事实 | 证据 |
| --- | --- | --- |
| 主要语言 | Go（`language: "Go"`，`go.mod` = `github.com/alibaba/open-code-review`） | [E32] |
| 入口 | `cmd/opencodereview/main.go`：`func main() { llm.AppVersion = Version; os.Exit(run()) }` | [E33] |
| 核心目录 | `internal/{agent,diff,llm,llmloop,session,tool,viewer,scan,config,telemetry,mcp,delegate,gitcmd,model,pathutil,release,stdout,suggestdiff}`（394 个文件） | [E01] |
| 前端/插件 | `pages/`（官网，232 文件）、`extensions/{vscode,idea,frontend}`（213 文件）、`plugins/open-code-review/`（36 文件）、`skills/`、`bin/ocr.js`（npm 启动器） | [E01] |
| 其他语言 | TypeScript/React（网站与扩展 webview）、Kotlin（IDEA 插件）、JavaScript（Action 脚本）、Python（`examples/*_ci/post_review.py`，各 CI 平台的评论投递脚本） | [E01] |
| 规模 | 44,127 stars / 3,188 forks / 283 open issues；发布节奏快（最新 v1.12.12，2026-10-05；博客称两个月 89 个 release） | [E32][E19] |

**论文/技术报告**：有。README 第 57-59 行把基准指向 HuggingFace 数据集，数据集卡片的 frontmatter 带 `arxiv:2601.19494` tag，并给出 BibTeX：[E07][E34]

> **AACR-Bench: Evaluating Automatic Code Review with Holistic Repository-Level Context**（Lei Zhang 等 14 人，arXiv 2601.19494，cs.SE）[E34]

arXiv 投稿历史（我自己抓 abs 页）：`[v1] Tue, 27 Jan 2026` / `[v2] Thu, 29 Jan 2026` / `[v3] Fri, 30 Jan 2026`。**注意 v1 与 v3 的措辞变过**：v1 正文写 "comprising **seven** mainstream open- and closed-source models"，v3 同一处写 "comprising **6** ... models(Claude-4.5-Sonnet, Qwen3-Coder-480B-A35B-Instruct, GPT-5.2, Deepseek-V3.2, GLM-4.7, Gemini-3-Pro)"——列举的名字始终是 6 个，**v3 已自洽，看 v1 会读到"七/六"矛盾**。[E35]

另有一个独立的"安全论证"文档：`ASSURANCE_CASE.md`（威胁模型：5 类主体、4 条信任边界、T1–T7 威胁与缓解措施；并把 Saltzer & Schroeder 的 8 条安全设计原则与 OWASP Top 10 / CWE Top 25 逐条映射到实现文件与行号），末尾一张"Automated Verification"表把每条检查对到工具与触发时机（`go vet` / `govulncheck` / `go test -race` / Dependabot / `go.sum`）。[E36]

---

## 2. 测试组织、测试类型、用例数量与覆盖率口径（第 2 问）

### 2.1 事实：没有 `tests/` 目录，测试与实现同包共存

Go 的惯例是 `*_test.go` 与实现同目录同包。我把 tarball 解包后逐文件统计（脚本 `.tmp/ocr_census.py`、`.tmp/ocr_counts.py`；方法：正则 `^func Test`、`t.Run(`、`^func Benchmark`、`^\s*@Test`、`^\s*def test_`、`^\s*(it|test)(`）：

| 语言 | 测试文件 | 用例数（我数的） | 备注 |
| --- | --- | --- | --- |
| Go | **234** | **2,505** 个 `func Test` + **655** 个 `t.Run` 子测试 | **0 个 `func Benchmark`**；全文检索 `testing.B` 命中 **0** |
| Kotlin（IDEA 插件） | 20 | **223** 个 `@Test` | `extensions/idea/src/test/kotlin/...` |
| TypeScript/TSX（网站 + vscode/frontend 扩展） | 21 | 135 个 `it(`/`test(` | vitest（`pages/vitest.config.ts`）+ 各扩展自己的 runner |
| JavaScript / `.mjs`（Action 脚本、npm 启动器、opencode 插件） | 7（6 个 `.js` + 1 个 `.mjs`） | 37 个 | `scripts/github-actions/*.test.js`（`post-review-comments.test.js` 单文件 308 KB）、`bin/ocr.test.js`、`plugins/open-code-review/opencode/test/open-code-review.test.mjs` |
| Python（各平台 CI 投递脚本） | 4 | **256** 个 `def test_` | `examples/{gitlab,gerrit,gitflic,codeup}_ci/post_review_test.py` |

> 计数口径：JS 家族合计 **28** 个测试文件（21 个 `.ts/.tsx` + 6 个 `.js` + 1 个 `.mjs`）；上面的 172 是**按行首**匹配 `it(`/`test(` 得到的，会漏掉 `await test(`、嵌套 `describe` 里的写法，所以是**下界不是精确值**。Go 的 `t.Run` 子测试同理（只数了 `t.Run(` 出现次数，不是展开后的用例数）。

**代码量对照**（同一脚本）：Go 测试文件 75,794 行 vs 非测试 Go 文件 36,367 行（130 个文件）→ **2.08 : 1**。

**测试里几乎没有"测试数据目录"**：解包后按路径搜索 `/testdata/` **命中 0 个目录**；搜 `golden`/`snapshot`/`*.golden.*` **命中 0 个文件**。[E02]

> 这说明它不靠"金标准文件"回归，而靠**在测试里现搭 fixture**（`t.TempDir()` 用了 822 次、`t.Setenv()` 329 次、`t.Helper()` 188 次；`t.Parallel()` 只有 8 次。它另有明确的工作池对象，例如人工 E2E 里的 `agent.NewCommentWorkerPool(2)`——**但"并行度主要在代码里而不在测试里"这句是我的解释，不是文件里的原话**）[E02][E30]

### 2.2 测试类型（按名字与做法分类，全部是"实测清单"不是推测）

| 类型 | 实例 | 做法 |
| --- | --- | --- |
| 单元测试 | 绝大多数 | 纯函数/结构体 + 假客户端（`fakeAgentClient`、`fakeScanClient`） |
| 进程内集成/E2E | `cmd/opencodereview/retry_report_e2e_test.go`、`progress_stream_e2e_test.go` | 走**真实 HTTP 栈**（`httptest.NewServer` 假 Anthropic 服务，全仓 69 处），装配真实 `agent.New` → `ag.Run` → `RunManifest` → `Freeze` [E29] |
| 人工 E2E（构建标签隔离） | `cmd/opencodereview/manual_e2e_retry_test.go`（`//go:build manual_e2e`） | 默认不编译；`go test -tags manual_e2e -run TestManualE2ERetryReport -v ./cmd/opencodereview/`；文件头写明目的是"在 P5 生产代码存在**之前**就能观察整条链路"[E30] |
| 压力/竞态 | `internal/mcp/closeall_stress_test.go`、`race_test.go` / `norace_test.go` | 用构建标签切换竞态与否 |
| 合同/契约 | `scripts/github-actions/action-contract.test.js`（84 KB）、`check-plugin-contract.test.js`（33 KB）、`post-review-comments.test.js`（308 KB） | 把 GitHub Action 的输入输出、插件清单、跨仓链接当契约来测 |
| 跨平台 | `//go:build unix` / `windows`、CI 里原生 windows-latest job | "race 检测在 Windows 上需要 C 工具链，而竞态与 OS 无关，所以 Linux job 已经覆盖；这个 job 是为 OS 特有行为存在的"（ci.yml 注释）[E04] |

**"覆盖"这个词在本仓有两种意思，别混**：`internal/agent/coverage_test.go`（1,004 行）、`internal/scan/coverage_test.go`（1,365 行）不是"覆盖率测试"，而是对 agent/scan 状态机的**补充用例集**（里面的函数名如 `TestClassifyMainLoopStop`、`TestDispatchSubtasks_ResumeRerunsChangedContent`、`TestMaybeRunDedup_SkipWhenTooFewComments`），用假 LLM 客户端按序喂预置响应。[E37]

### 2.3 CI：12 个 workflow，哪些是硬门禁、哪些只报告

`.github/workflows/` 共 12 个文件。[E01]

**硬门禁（失败即红）**：

| workflow | 关键步骤（原文） |
| --- | --- |
| `ci.yml`（test job，self-hosted + `golang:1.26.6` 容器，15 分钟超时） | 生成物一致性 `go run ./internal/llm/gen -check ...`；许可证头 `bash scripts/verify-license.sh`；Action 版本钉死 `bash scripts/verify-action-pins.sh`；**源码不得含未批准的非英文** `go run scripts/verify-english-only.go`；gofmt 清洁；**行尾必须 LF**（`git add --renormalize .` 后有 diff 就 exit 1）；`go mod tidy` 后有 diff 就 exit 1；`go vet ./...`；`govulncheck`（固定 `@v1.6.0`）；`go test -v -race -count=1 -coverprofile=coverage.out ./...` + **覆盖率门槛 90%**；build；**smoke test**（`--version` 含 "open-code-review"、`--help` 必须列出 review/scan/delegate/config/llm/viewer/session/rules 八个命令）[E04] |
| `ci.yml`（windows job） | `go vet`；`go test -count=1 ./...`（**无 -race、无覆盖率门槛**，注释写明原因）；`npm run test:launcher`；build；同一套 smoke test（用 git-bash 跑同一段脚本，"rather than reimplemented in PowerShell"）[E04] |
| `ci.yml`（cross-compile job） | linux/arm64、darwin/amd64+arm64、windows/amd64+arm64 五个目标 `go build -o /dev/null ./...` [E04] |
| `action-contract.yml` | `npm run test:github-actions`（4 个测试脚本串联）+ `npm run test:launcher` [E38][E39] |
| `plugin-contract.yml` | 先跑测试脚本，再跑两次真实检查：`check-plugin-contract.js links`（仓内路径链接）与 `manifests`（插件清单契约）[E40] |
| `translation-sync.yml` | 测试脚本 + `check-translation-sync.js readmes`（README 翻译结构）是硬门禁；`... docs` 步骤带 `continue-on-error: true`（**只报告**）[E41] |
| `pages-ci.yml` | `npm run lint` / `test` / `typecheck` / `build` / smoke（`npx serve dist` 起服务后断言）/ `npm run size`（size-limit **150 kB**）[E42] |
| `frontend-ext.yml` / `idea-ext.yml` / `vscode-ext.yml` | 各自的 typecheck / test / build；IDEA 侧还跑 `verifyPluginStructure`；Gradle wrapper 校验 [E43] |
| `codeql.yml` | CodeQL Advanced（矩阵语言 + 定时扫描）[E44] |
| `ocr-review.yml` | **自吃狗粮**：`pull_request_target`（fork 也有 secret，注释解释安全性："OCR only reads the diff and does not execute any code from the PR"）上 `uses: ./` 跑自家 Action，模型走 secrets `OCR_LLM_*` [E45] |

**关于"评审结论"本身没有门禁**：Action 的失败语义写得很清楚——"When `ocr review` exits non-zero the action fails the job with that exit code (the comment-posting step is skipped)"，即**工具失败会让 PR 检查变红，而"发现了多少问题"不会**；只在 GitLab 示例脚本里有可选的 `OCR_FAIL_ON_SEVERITY`（默认空 = 关闭）。[E46][E47]

### 2.4 覆盖率口径（含一处自相矛盾）

- Makefile：`COVERAGE_THRESHOLD := 90`；`coverage` 目标跑 `go test -count=1 -coverprofile=coverage.out $(PACKAGES)`，其中 `PACKAGES := $(shell go list ./... | grep -v /extensions/)`（**不含 `-race`、排除 extensions**），低于 90 就 `exit 1`。[E03]
- CI：**同一句门槛，但范围不同**——`go test -v -race -count=1 -coverprofile=coverage.out ./...`（**含 `-race`、含 extensions**），低于 90 失败。[E04]
- AGENTS.md（给 AI 的贡献说明）："The project enforces a 90% coverage threshold via `make coverage`."[E48]
- **矛盾**：ci.yml 的 windows job 注释写 "the `//go:build !windows` test files legitimately drop the total below the **80%** the Linux job enforces"，而 Linux job 脚本里是 **90**。[E04]
- 前端（pages）**没有覆盖率门槛**，只有 bundle size 150 kB 上限；IDEA/VS Code 扩展也没有覆盖率门槛。[E42][E43]
- 覆盖率是**语句覆盖率**，没有分支覆盖率：项目在 OpenSSF 自评里对 "branch coverage 80%" 一项填 N/A，理由写得很具体（Go 的 `-covermode` 只有 set/count/atomic，都是语句级；已用 `go help testflag` 与 `go tool cover -h` 核对过）。[E26]

---

## 3. 有没有自己的评测集/基准（第 3 问）

**有，而且公开。** 三层证据：

1. **README 的宣称**（这是"被检验的声明"）：

> Compared to general-purpose agents (Claude Code), Open Code Review achieves significantly higher **Precision** and **F1** with the same underlying model, while consuming only **~1/9 of the tokens** and completing reviews faster. Note that its Recall is lower than general-purpose agents — a deliberate trade-off favoring precision over noise.
>
> A real-world code review benchmark built from **50** popular open-source repositories, **200** real Pull Requests, and **10** programming languages — cross-validated by 80+ senior engineers (**1,505** annotated ground-truth issues). [E06]

2. **论文（AACR-Bench）**给出构造口径：语言取 StackOverflow 2025 调查前 10（JS/Python/TS/Java/C#/C++/C/PHP/Go/Rust），每语言取 2024-12-01 至 2025-12-01 间"新星数"与"已关闭 PR 数"双榜前 2,000 的候选仓，再各取星数最高的 5 个 → **50 仓**；PR 五条过滤（英文标题/描述、改动行 ≤1,000、主语言与仓库主语言一致、内联评论 >2 且至少 1 条被采纳并导致改码、剔除与业务语义无关的改动）→ 分层抽样（按仓库/问题域/改动规模）得 **200 PR**；对每个 PR 取内联评论最多的那个 revision，用 LLM 做语义分析把多轮对话里的**已确认缺陷**抽成 "Augmented Review Comments"。[E12]

3. **公开数据集**：`Alibaba-Aone/aacr-bench`（HuggingFace）。我实测：`/size` → `num_rows = 2145`、`num_columns = 16`；`/splits` → 只有 `default`/`train`；`/first-rows` → 16 个字段与卡片逐个吻合（`project_main_language, pr_url, pr_source_commit, pr_target_commit, pr_change_line_count, pr_category, is_ai_comment, note, path, side, source_model, from_line, to_line, category, context, label`）；用 `/filter?where="label"=0` 数出 **640** 条 label=0，2145−640 = **1,505** 条 label=1，与卡片"2,145 条 / 1,505 正确 / 640 错误"逐个吻合。[E07][E08][E09]

**它靠什么证明"好用"（除基准外）**：博客自述的三条——内部生产验证（"20k monthly active users, an adoption rate of 30%+, a false-positive rate under 5%, and nearly 80% of the effective suggestions merged into the baseline come from AI"）、每版本内外部同步发（"Same source inside and out; we ship every version internally and externally in sync"）、发版前跑 200-PR 评测集。[E19][E15]

**⚠ 两处需要读者自己校正的地方**（我复算出来的，不是原文）：

- README 说的 "1,505 annotated ground-truth **issues**"，在论文里的定义是 1,505 条**评审评论**（review comments）：v3 原文 "This step yielded a total of 1,505 review comments, including 391 augmented from original reviews and 1,114 **augmented by LLMs and human experts**, representing a 285% increase in issue coverage."（v1 把后半写成 "generated by LLMs"——措辞也改过）。把它读成"1,505 个缺陷"会高估。[E12]
- 网站排行榜（`pages/src/components/BenchmarkSection.tsx`）里每行的 "AVG TOKEN" 是 "输入/输出" 两段（如 `375K / 10K`），而卡片上写的是总数（`385K`）——两者是同一组数的两种呈现，不是矛盾。[E49]

**评测工具链不在仓库里**（这是"公开可复现性"的硬缺口）：文件名检索与全文检索 `baseline` / `leaderboard` / `groundtruth` / `eval` / `bench` 的结果只有：网站图片 `imgs/benchmark-*.png`、前端组件 `BenchmarkSection.tsx`、`BenchmarkPage.tsx`。**没有评测脚本、没有基线 JSON、没有门槛文件**；评测流程只在博客里以内部技能 `/release-eval` 出现。[E14][E15]

---

## 4. 标签（ground truth）从哪来（第 4 问，重点）

### 4.1 谁标的、几人、怎么裁决分歧（论文 v3 原文）

> To address the Label Incompleteness stemming from the often under-reviewed nature of GitHub PRs (Bacchelli & Bird, 2013), we leveraged LLMs to comprehensively supplement the review comments for each PR. We constructed a generation matrix comprising **6 mainstream open- and closed-source models** (Claude-4.5-Sonnet, Qwen3-Coder-480B-A35B-Instruct, GPT-5.2, Deepseek-V3.2, GLM-4.7, Gemini-3-Pro) to mitigate single-model bias and ensure output diversity. Review comments were generated in parallel through **two heterogeneous frameworks: an internal review system and the open-source agent, Claude Code**. Following semantic de-duplication, the generated comments were merged with the augmented human reviews to form a candidate set for human verification. [E12]

> Subsequently, we submitted this set to **over 80 senior software engineers with more than two years of experience** for rigorous Human Annotation. The annotation process covered **three core dimensions**: verifying the correctness of the review comments, categorizing issue types according to Table 7, and defining the scope of context dependency. **The annotation workforce consisted of a Core Expert Team of 6 members and a General Annotation Pool comprising the remaining participants.** The annotation process was divided into **three rounds**: The first two rounds were conducted by the General Annotation Pool using a **double-blind mechanism, where each comment was independently annotated by two different individuals**, and task allocation was **strictly matched to the annotators' programming language expertise**. The third round was conducted by the **Core Expert Team**, which was responsible for **discussing and adjudicating conflicting results** from the first two rounds and determining the final annotations. [E10]

摘要里还有一句把"评论总数"和"标注人数"直接连起来的话：

> ...we incorporated extensive manual issue annotation: **80 senior software engineers (each with 2+ years of industry experience) meticulously reviewed 2,145 comments** generated by two ACR systems across six LLMs. [E50]

**语义去重也是 LLM 做的，而且有"多数票"**：去重用 `Qwen3-235B-A22B-Thinking-2507`，按（仓库, PR, 文件路径, diff hunk）分组后两两比较，提示词要求只判"语义是否等价"，并且 "We use the election of results running **5 times of judgement**"（5 次判定取多数）。[E51]

**标签构造的补集也有数据**：附录 Table 8 把 1,505 条按"有多少个模型也检出过"分箱——0（仅人工增强）360 条、1 个模型 1,027 条、2 个模型 107 条、3 个模型 11 条；原文自己的解读是 "This low overlap suggests the necessity to include multi-model results in review comment generation process for better issue coverage."[E52]

### 4.2 一致性检验（IAA/κ）：**没有找到**

我抓了 arXiv HTML 的 v3 全文（83,110 字符）与 v1 全文，检索以下关键词，**命中数全部为 0**：`kappa`、`inter-annotator`、`agreement`、`Cohen`、`Fleiss`、`IAA`。[E11]

也就是说：**协议里写了"两人独立标注 + 专家组裁决分歧"，但没有报告任何标注者间一致性数字，也没有报告分歧率、裁决改判率**。这不是"没写清楚"，是"这个量根本没出现在论文里"（我检索的是全文，不是摘要）。

同目录 `aacr-bench-数据集核验.md` 独立检索 v1 与 v3 得到同一结论，可互为印证。

### 4.3 发布物里能看到的 / 看不到的

发布的数据集**只有最终标签**，这决定了"一致性检验"无法由外部复算：

- 16 个字段里**没有** `annotator_id`、`round`、`agreement`、`adjudicated`、`annotated_at` 这类字段（我在 `/first-rows` 拿到的行上逐字段核对过）。[E08]
- 因此外部能做的只有"用 label 复算别的分布"，不能复算"两个人当初是否一致"。

**640 条 label=0 的来源**：摘要说 80 名工程师**核验了 2,145 条**，卡片说这 2,145 条由 "1,505 expert-verified correct comments and 640 incorrect comments" 组成。[E50][E07]

> **我的判断（不是原文）**：640 = 同一轮标注里被判"不正确"而没进真值集的那部分。两条原文合起来支持这个读法，但**没有任何一句话直接这么说**，也没有说明这 640 条是"两人都判错"还是"专家组裁决为错"——这一层无法证实。

---

## 5. 指标与门槛（第 5 问）

### 5.1 指标怎么算：只到"P/R/F1"这一层

论文：

> We evaluate the performance of various ACR approaches against AACR-Bench using the common three matrics, i.e., Precision, Recall and F1-score. [E13]
>
> ...each Pull Request (PR) serves as an evaluation instance, where the collection of review comments associated with that PR constitutes the Ground Truth. For each PR, the Automated Code Review (ACR) method under evaluation is required to iterate through the Diff Hunks within the code changes and generate review comments for each hunk. ... Performance is evaluated by **matching these generated comments against the Ground Truth (comprising 1,505 items)** and calculating specific accuracy metrics (e.g., Precision, Recall and F1-score.) [E12]

**评测设置**（附录 C.1 原文）：所有模型 `Temperature=0.7, Top_p=0.95, Top_k=20`；相似度检索方法统一取 top-3 上下文；Agent 方法自行决定检索多少；所有设置都提供 PR 标题与描述；非 Agent 方法用 GitPython 抽 diff hunk，逐 hunk 生成评论，每条评论必须输出三件东西（出问题的 diff 片段、评论所在 side、评论正文）。[E13]

**「怎么算命中」没有定义**（这是最重要的缺口）：论文只写 "matching these generated comments against the Ground Truth"，**没有给匹配规则**——没有行号重叠判据、没有 IoU 阈值、没有语义等价判据、没有给出 TP 的定义。我在论文全文检索 `IoU` / `true positive` / `same line` / `overlap`（除"模型检出重叠"那一处）均无所获。[E13][E11]

**分母是什么（README/网站在自己产品上的口径）**：网站排行榜把每个数字都写成了分子/分母，我按它的原文抄下来并复算：[E49]

| 系统 | 模型 | 版本 | F1 | Precision（分子/分母） | Recall（分子/分母） | 我的复算 |
| --- | --- | --- | --- | --- | --- | --- |
| Open Code Review | Claude-4.6-Opus | v1.3.1 | 25.10% | 33.90% = 301/889 | 20.00% = 301/1505 | 2PR/(P+R) = 25.16% |
| Open Code Review | Qwen3.8-Max | v1.8.7 | 23.00% | 33.90% = 262/774 | 17.40% = 262/1505 | 22.99% |
| Open Code Review | GLM-5.2 | v1.3.1 | 21.30% | 32.30% = 239/741 | 15.90% = 239/1505 | 21.31% |
| Claude Code | Claude-4.8-Opus | v2.1.169 | 14.13% | 15.93% = 191/1200 | 12.70% = 191/1505 | 14.13% |
| Claude Code | Qwen3.7-Max | v2.1.169 | 12.17% | 8.23% = 351/4260 | 23.37% = 351/1505 | 12.17% |
| Codex | GPT-5.5 | v0.140.0 | 8.36% | 27.82% = 74/266 | 4.92% = 74/1505 | 8.36% |

可读出来的三条：**① Recall 的分母在所有行都是 1505**（= 真值评论总数），与论文一致；**② Precision 的分母逐系统不同**（1,200 / 4,260 / 266 …），即"该系统这次报了多少条评论"；**③ 每行 P 与 R 的分子相同**，说明命中数同时充当两个分子，F1 是二者的调和平均（我逐行复算，误差都在四舍五入范围内）。但**"这个分母是不是投稿后被去重/去重前的条数"没有写在页面任何地方**——这是【待核验】。

### 5.2 有没有 pre-registered threshold

- **对"评审质量"没有。** 我在解包后的全仓检索 `threshold`/`THRESHOLD`（**354 处命中、分布在 64 个文件**；排除 `internal/config/rules/rule_docs/**` 与 `docs/i18n/**` 的 `.md`）后逐条分类：全部是**工程/运行参数**（增量评论 IoU 阈值 0.6、限流阈值 `OCR_RATE_LIMIT_THRESHOLD`、严重级别路由阈值、`PLAN_MODE_LINE_THRESHOLD` 默认 50、覆盖率 90、bundle 150 kB），**没有一个**是"评审精确率/召回率必须达到 X"；与 precision/recall/quality 这类词共现的只有 2 处（`skills/open-code-review/SKILL.md` 与插件副本里对 `PLAN_MODE_LINE_THRESHOLD` 的说明）。也没有基线文件。[E53][E15]
- **对"过程"有两个硬数字**：① 覆盖率 90%（CI + Makefile，失败即红）；② 网站 bundle ≤150 kB；③ 项目的质量政策是**定性的**——博客："any change affecting the core path must pass the full 200-PR eval set before release"（**"pass" 没有定义成任何数字**），以及 `/release-eval` 技能"判断要不要跑评测集（一次 8 小时）"。[E03][E04][E42][E15]
- **结果有没有随版本记录**：**有，但记在网站上、不在仓库里**。网站排行榜每行都带被测系统的版本号（OCR `v1.3.1`/`v1.8.7`、Claude Code `v2.1.169`、Codex `v0.140.0`）与原始分子/分母；仓库里没有任何"每次评测结果"的产物。[E49][E14]

---

## 6. 有没有测"失败关闭 / 误报代价 / 摩擦成本"（第 6 问）

**有，而且分成了三种不同方向，值得分清**：

### 6.1 工具失败：fail-closed（宁可红，不要假装审过）

- GitHub Action 的检查点（跨 push 增量评审）设计原话：

> The whole design is fail-closed: resolveCheckpointRange runs an ordered gate and **ANY doubt** — feature off, summary missing, marker unreadable, base moved, config changed, ancestry unprovable — returns mode "full", which reviews the same range the action reviews today. The narrowed range is only ever taken when every condition holds. [E20]

  信任边界也写得很直白："the marker is read only from a comment authored by this run's own authenticated identity ... anyone with write permission on the repository can edit a bot comment. So the boundary this buys is 'write-permission holders are trusted'."[E20]
- **工具崩了不放过**：`ocr review` 非零退出 → job 失败（评论投递步骤被跳过）；零退出但 JSON 坏 → 解析错误出现在 summary。[E46]
- 过滤器（reflection）的实现里，**LLM 调用失败时不删任何评论**（`executeGroupReviewFilter` 在 `err != nil` 分支打印一行 `Review filter failed for group ...` 后 `return`，不调用 `RemoveByPathAndIndices`），解析不出结果同样 `return`；行为由用例 `TestExecuteReviewFilter_OmitsToolChoiceAndFailsOpenWithoutToolCall` 钉住。[E17][E54]

### 6.2 误报代价：写进提示词的不对称损失函数

过滤器系统提示词（原文）：

> The two mistakes available to you are not equally bad: **Keeping an incorrect comment costs a reviewer a few seconds of attention. Removing a correct comment silently destroys a real finding. It never reaches anyone, and nobody learns that it was dropped.** So when your evidence falls short of proof, approve. "Suspicious", "I cannot verify this", "low value", "the flagged code looks fine to me", and "I would not have raised this" all mean approve. [E16]

用户提示词把可删除条件收成两条"必须能被 diff 证明"的地面，并加了一组**否决删除**的保护主题：

> Ground A — the comment targets code that is not in its subject file's diff. / Ground B — a specific diff line literally contradicts the comment's central claim. ... **Protected subjects — never remove**: Memory safety / Concurrency / Linkage and declaration consistency / Behavioral or compatibility change / A parameter the function accepts and never uses. ... The comment is about style, formatting, naming ... **provided what it states is true**. Low value is not incorrectness, and filtering by value is not your job. ... **Unverifiable is not incorrect.** [E55]

**执行顺序是硬编码的 5 步**（保护主题否决 → 价值否决 → Ground A → Ground B → 放行），且"到 Step 4 需要多步推理才能得出矛盾，就等于没有矛盾，放行"。[E55]

### 6.3 摩擦成本：被量化的三处

| 摩擦 | 事实 | 证据 |
| --- | --- | --- |
| 每次评审的墙钟与 token | 网站排行榜把 **Avg Time** 与 **Avg Token** 列为一级指标（如 OCR 1m23s / 385K vs Claude Code 13m6s / 5,664K；行内还拆了输入/输出） | [E49] |
| 整体运行时间 | "one run takes **8 hours**"（200-PR 评测集），并且只在"改动影响核心链路"时才跑 | [E15] |
| Token 预算 | README 的卖点之一是 "~1/9 of the tokens"；代码里有预算与超支路径（`internal/agent/budget_test.go`、`internal/scan/budget_exceeded_test.go`、`budget_output_test.go`、`scan_budget_json_test.go`） | [E06][E01] |
| 评审噪音 | 内部自述"误报率 <5%"，并把"precision over noise"写成明确取舍 | [E19][E24] |
| 误报的**拦截通道** | 除了提示词，产品里还有"把评论标为 False Positive"的状态（IDE/vscode 扩展的 `ext.comment.statusFalsePositive`），以及把人工反馈两向同步回宿主 | [E56] |

**没有被测的**：我没有在仓库里找到任何"误报代价"的定量测量（例如"一次误报让 reviewer 花多少时间"或"误报率对采纳率的影响"）；只有上面这些代理量（token、时间、5% 误报率自述）。[E14]

---

## 7. 核心关切：它如何处理"没有多个资深工程师做人工验证"（第 7 问）

### 7.0 先把它的现实说清楚：人工验证**有**，但只有 1–3 人，且合并在一个人手里

- 治理文件的门槛是**软措辞**：

> at least one maintainer of the affected area **should** review the change [E18]

- 它对外部审计的说法是**硬事实**（自述）：

> All changes land on the main branch exclusively through GitHub Pull Requests. **Branch protection on main requires at least one approving review from someone other than the author before merge**, and this rule is enforced for administrators as well (enforce_admins enabled). CI (the `test` job: build, race-enabled tests, coverage gate, smoke test) is a **required status check** for merge. [E21]

- **我实测的 12 个合并 PR 样本**（`gh api search/issues` 取 `is:pr is:merged` 按 updated 倒序前 12 个，再逐个取 `/pulls/{n}/reviews`）：**12/12 都有至少 1 条来自非作者的、`User` 类型的 APPROVED 评审**；每条 PR 的人类批准人数分布是 1 人（#1544、#1576、#1587）、2 人（#1610、#1279、#1573、#1212、#1413、#1414）、3 人（#1056、#1413 等）、4 人（#1393）；评审过程是**真的来回**（例：#1056 `wu21-web` 先 CHANGES_REQUESTED 后 APPROVED 反复 3 次；#1610 `Qiyuanqiii` 先 CHANGES_REQUESTED 次日 APPROVED）；**12 个 PR 全部由同一个人 `lizhengfeng101`（GOVERNANCE 里写明的 Project Lead）合并**。[E22][E57]
- 同一批样本里，自动化评审也留下痕迹：`github-actions[bot]` 以 COMMENTED 参与（OCR 自己的 `ocr-review.yml`）。[E57][E45]
- 我**没能**独立验证 branch protection：`gh api repos/alibaba/open-code-review/branches/main/protection` 返回 `403 {"message":"Resource not accessible by personal access token"}`——**这条只能是【待核验】**。[E58]

> 结论：它不是"没有人工验证"，而是"**人工验证的规模（1–3 人/PR，合并权集中在 1 人）远小于一个资深专家组**"。它对这个落差的处理是下面六条替代。

### 7.1 它的六条替代方案（每条带证据）

**（1）把"资深工程师"用在数据集上，而不是用在每个 PR 上。**
80 名工程师 × 三轮 × 双盲双标注 × 6 人专家组裁决，产出 1,505 条真值——这是一次性、可复用、可被外部引用的"人工判断"，替代了"每个 PR 都要多人看"。[E10][E50]

**（2）生产遥测当"活体验证"。**
内部两年的使用量被当成质量证据（自述）："20k monthly active users, an adoption rate of 30%+, a false-positive rate under 5%, and nearly 80% of the effective suggestions merged into the baseline come from AI"；并把"我们只提供框架、数据留在本地"当作企业场景的硬要求。[E19]

**（3）把端到端评测集当发版闸门，并且是"事故驱动"加进去的。**
博客原文交代了一次真实事故：上线前让 AI 自主决定工具调用逻辑的改法，"Unit tests passed, a few examples looked fine, and we shipped. It turned out to have introduced a bug in a global-search tool."两天后 HN 流量涌入，用户第一次试用就踩到。**由此立了两条规矩**：

> any change affecting the core path must pass the full 200-PR eval set before release; and when the AI writes code, it must be given explicit constraints on the approach — no free improvisation. [E15]

**（4）用自动化网替代"多人过一遍"。**
博客把稳定性来源列成一张清单："Automated code review + unit tests + Lint + CI/CD pipeline + an E2E eval set (200 PRs), and so on. Because we iterate fast, we need these nets underneath us all the more."；落到代码就是 2,505 个 Go 用例 + 90% 覆盖率门槛 + `-race` + `govulncheck` + CodeQL + 12 个 workflow。[E15][E02][E04][E44]

**（5）把"人必须理解 AI 写的每一行"写成规则，并让 PR 模板强制勾选。**
CONTRIBUTING.md 的 "AI-Assisted Development" 八条规则（原文摘要）：必须披露用了 AI 与具体工具/模型；**You should understand every line of code written by AI**；被 reviewer 问到时必须自己能解释（"you may use AI/LLM only to translate or polish wording, not to generate the answer for you"）；PR 里不许出现 `AI generated -> fixed -> fixed -> fixed` 这种循环；提交前必须自己 review 过全部 AI 产物；不许在 commit 里加 `Assisted-by`/`Co-developed-by`；做不到就关掉 issue/PR。PR 模板把它变成一个复选框：

> I did not use AI/LLM to create this PR, or I disclosed the tool/model below and reviewed its output; I did not attribute commits to AI and will answer maintainer questions and review comments myself without AI/LLM. [E23][E59]

**（6）外部过程审计当"第三方验收"。**
README 挂 OpenSSF Best Practices 徽章；我用 `https://www.bestpractices.dev/projects/13328.json` 核到：`"badge_level": "gold"`、`tiered_percentage: 300`、`achieved_gold_at: 2026-08-06T04:57:39.723Z`。其自评里把"人类评审"这条写成"至少 1 名非作者批准 + CI 必过"——**注意：这是"过程"验收，不是"评审质量"验收**。[E60][E21]

### 7.2 它自己承认的局限（原话）

| 局限 | 原文 | 证据 |
| --- | --- | --- |
| 召回故意低于通用 Agent | "Note that its **Recall is lower than general-purpose agents** — a deliberate trade-off favoring precision over noise." | [E24] |
| 真值不可能完备 | "although we leveraged LLM-generated reviews to augment our dataset, **constructing a fully comprehensive Ground Truth remains a formidable challenge due to the inherent complexity and subjectivity of real-world software systems**. Future work will focus on further expanding the dataset scale and exploring more advanced semi-automated methods to refine the Ground Truth quality." | [E61] |
| 人工评审本身会漏 | "Constrained by the cognitive boundaries and capacity limits of human reviewers, relying solely on manual efforts often fails to uncover all potential code defects."（这正是他们做 LLM 增强的理由） | [E51] |
| 上下文多不一定好 | "We challenge the prevailing assumption that 'more context is always better.'" | [E25] |
| AI 自主决策出过事故 | "don't let the AI pick the option and then execute it — decision-making authority must stay in human hands." | [E15] |
| 人也会跑掉、反馈慢就是留不住人 | "**Failing to retain people isn't a sign the project isn't good enough — it's a sign the feedback isn't fast enough.**" | [E19] |
| 它自己的选择：主动暴露缺点 | "**actively exposing your shortcomings works better than projecting perfection**. In our README we openly wrote about many things we still don't do well." | [E19] |

### 7.3 与"多个资深工程师做人工验证"相比，它缺什么（我的判断，明确标注为判断）

- **缺独立复核**：数据集层面有"两人独立 + 专家组裁决"，但**产品每次评审**只有"1 名维护者批准"这条硬底线；样本里 3/12 个 PR 只有 1 个人类批准。[E21][E22]
- **缺一致性数字**：双盲双标注本来天然可以算出 κ 或分歧率，但**论文与数据都没有**，所以"两轮独立标注"这个机制的**可靠性本身没有被度量**。[E11]
- **缺可复算的评测**：匹配规则、重复次数、随机性控制（温度/种子）、评测脚本都不公开，"25.10% F1"这类数字**外部无法复现**。[E12][E13][E14]
- **缺"评审结论"的门槛**：过程有门槛（覆盖率 90%、CI 必过），结论没有门槛（没有"精确率不得低于 X"）。[E03][E04][E53]
- **不缺的东西**：把"人必须理解 AI 产物"写成可执行的贡献规则 + PR 模板勾选 + 外部审计，这是**比多数项目更严的自我约束**。[E23][E59][E60]

---

## 8. 可复用清单（借什么 / 为什么成立 / 边界在哪）

> 每条都对照本仓（Engineering Policy Platform）的现有纪律给出落点。**借用的是机制，不是它的数字。**

**R1｜假 LLM 与"人工 E2E"共享同一 fixture，防止两条路分叉**
- 借什么：一个 `fakeLLM`（假 Anthropic HTTP 服务，可按文件注入 429 / 永久 402），同时被自动化 E2E 与 tag 隔离的人工 harness 使用；文件头写明理由是 "so the two cannot drift apart in what they consider a retryable server"。
- 为什么成立：人工验证与自动验证若各自造数据，"人工过、自动挂"就永远解释不清是产品变了还是夹具变了；共享夹具把差异收敛到一处。
- 边界：共享夹具自身也会腐坏——它只保证两条路"同源"，不保证"同源的那个源是对的"。本仓对应做法见第 45 条（仪器自证：修复前会红）。
- 证据：[E29][E30]

**R2｜"这次调用到底发生了没有"的显式断言（防"静默失去覆盖"）**
- 借什么：`assertGroupingRecognized` —— 假服务统计"匹配到分组系统提示词"的请求数，为 0 就 `t.Fatalf`，并在注释里写明反事实："Without it a reworded GROUPING_TASK system prompt would degrade these tests silently ... **Every assertion would still pass with the coverage gone.**"
- 为什么成立：这是"覆盖消失但测试仍绿"的唯一可自动检测形态（与"断言全过、但根本没走到那条分支"同型）；它把"我以为测到了"变成一条会失败的检查。
- 边界：只为"全局事件"（改一句 prompt）设一个守卫就够；作者自己写了为什么**不**放进 `startFakeLLM` 的 cleanup——"a test whose change set never reaches the grouping call would then fail for the wrong reason"（防止因为错误的原因失败）。
- 证据：[E31]

**R3｜失败原因枚举 = 数据，且与文档计数交叉断言**
- 借什么：13 条 fail-closed 原因逐条给定一个"只触发它"的输入类；断言"每个原因都有自己的输入类"、"文档注释里的数字 = 列表长度"、并且从源码里**切出那段契约注释**做字符串比对。
- 为什么成立：注释里写死"thirteen"，列表却可能变成 12 或 14；把"文档计数"变成断言，才让漂移变成红灯。作者写了动机原文："The reason set is documented in three places ... and **drifted between them once**. Enumerate it once, here, and fail if any copy falls behind."
- 边界：**它只守数量，不守语义**；同一文件里就残留着反例——函数名 `testCheckpointTwelveReasonsAreDistinct` 与注释 "each of the **twelve** fail-closed reasons" 没跟着改成 thirteen（断言处是 `failClosed.length, 13`）。借这条时要把函数名、注释、文档、断言**同批**改。
- 证据：[E20][E62]

**R4｜把"代价不对称"显式写进判定标准（而不是写在文档里）**
- 借什么：过滤器提示词的三件套——① 两个错误不等价（保留错评论 = 浪费几秒；删掉对评论 = 静默销毁一条真实发现）；② 只有"能被 diff **证明**为错"才允许删；③ **受保护主题**（内存安全/并发/链接一致性/行为变更/未使用参数）无条件否决删除，且"在这些主题上你没有资格自信"。实现侧再兜一层：LLM 失败/解析失败一律不删。
- 为什么成立：它把"失败关闭"的方向**按后果**分开——**范围**宁可更宽（重审全量），**发现**宁可更多（不删），**只有"证明为错"才允许收窄**。这与本仓第 51 条（pending 独立成通道、不进 violations）同源：判断的门槛要写在能失败的地方，不能靠人自觉。
- 边界：这是"降低误杀"，不是"提高精确率"；它明确放弃"低价值评论"的过滤（"Low value is not incorrectness, and filtering by value is not your job"），所以噪音仍在。
- 证据：[E16][E55][E17]

**R5｜"文档中的数字要与实现同批改"的另一种写法：把副本从 3 处减到 1 处 + 断言其余 2 处**
- 借什么：原因集合只在测试里枚举一次，然后**去读**源码里的契约注释（切片 + `includes`）与 README 表格（正则抓表格行）来校验；连"README 里多出来的第 14 个原因 `rule_unreadable`"都单独断言。
- 为什么成立：单一事实源 + 派生副本的**自动比对**，比"记得改三处"可靠。
- 边界：正则抓 Markdown 表格是脆的（改表格排版就断）；本仓对应纪律是第 55 条"加键就是改协议"，落点是版本号而不是表格。
- 证据：[E62]

**R6｜覆盖率门槛要写清"哪个范围、含不含 race"**
- 借什么：CI 与本地两套命令范围不同（CI 含 `-race` 与 extensions；Makefile 不含 race、排除 extensions），且把"以哪个为准"写进对外说明。
- 为什么成立：同一个"90%"在两个范围上是两个数（自述 90.2% vs 90.6%）；不写范围，两个数就会被当成矛盾或当成互相印证。
- 边界：本仓的对应物是"同一批测试只跑一次 + 报告与源码改动时间比对"；**不要**照搬"两套口径"，除非像它一样把"哪个是权威"写死。
- 证据：[E03][E04][E26]

**R7｜基准标注协议：多模型生成 → LLM 多数票去重 → 双盲双标注 → 专家组裁决**
- 借什么：① 覆盖不足用"生成矩阵"补（6 模型 × 2 套异构框架）；② 去重用 LLM 但取 **5 次判定的多数**；③ 人工标注分三轮（前两轮双盲、每人只标自己语言专长的单、每条由两人独立标；第三轮 6 人专家组裁冲突）；④ 三个标注维度（正确性 / 问题类型 / 需要的上下文层级）。
- 为什么成立：它把"覆盖"与"可信"拆成两个可分别加码的工序——生成负责覆盖，人负责可信；并在同一份产物里保留了"这条是谁生成的"（`is_ai_comment` / `source_model`），使覆盖来源可后验归因。
- 边界：**这套协议自己没交一致性数字**；照搬时必须补 κ/分歧率，否则"双盲双标注"只是流程描述，不是可靠性证据。另外本仓的评测对象是**规则判定**，与"评论生成"不同，标签不能直接迁移（见 `aacr-bench-数据集核验.md` 的同源风险一节）。
- 证据：[E10][E51][E52]

**R8｜让"没有资深工程师"这件事在流程上无处可藏：披露 + 自审 + 勾选**
- 借什么：贡献规则（必须披露 AI 使用与模型名 / 必须理解每一行 / 被问到时必须自己解释 / 禁止 AI 生成评论回复 / 禁止 AI 署名）+ PR 模板里一条能勾的复合声明。
- 为什么成立：它把"人有没有真的看"变成一条**可被追责的声明**，而不是隐含假设；对 maintainer 而言，追问的抓手从"我觉得这是 AI 写的"变成"你勾了这一条"。
- 边界：这是**自我声明**，不产生独立证据；真正起作用的是"被问到时答不上来会被拒"的社会约束。本仓如果借，应把声明与"evidence 不可用即拒"的机器判定分开写。
- 证据：[E23][E59]

**R9｜"我们到底有没有测到这个"要能回答——把测试类型与隔离方式写进文件头**
- 借什么：`manual_e2e_retry_test.go` 的 `//go:build manual_e2e` + 文件头命令 + "在 P5 生产代码存在之前就能观察整条链路"的目的说明；CI 里 windows job 明确写"这里不跑 -race、不设覆盖率门槛，原因是……"。
- 为什么成立：本仓第 45 条要求"每条检查写清驱动的是哪条路径、仍不覆盖什么"；这里的做法是**把"没跑什么"写在会被人读到的地方**（源文件头、workflow 注释），而不是只在 review 里说。
- 边界：注释不产生红绿；它是给下一个人的地图，不是门禁。
- 证据：[E30][E04]

**R10｜结果随版本记录，哪怕只是网站表格**
- 借什么：每行带被测系统版本号 + 原始分子/分母 + 时间与 token，读者可以自己复算 F1、自己判断分母含义。
- 为什么成立：本仓第 18 条要求"门槛在数据里、结果在基线文件里，代码里不写脱离数据的常数"；这条是它的弱化版——**没有基线文件，只有带原始计数的版本化表格**。
- 边界：它**没有**记录重复次数、温度、匹配规则，所以数字只能引用不能复现；本仓要借就补上这三样，并把基线落成文件。
- 证据：[E49][E13][E14]

**不建议借的一条**（写下来是为了防止误用）：**不要**照搬"把 90% 语句覆盖率当质量门槛"这件事本身。它的 90% 与"评审结论对不对"没有关系——论文自己给出的最好 F1 也只有 ~16%（v3 Table 3 里 Claude-4.5-Sonnet Agent 模式 F1 = 16.12%），而覆盖率是 90%+；两个数字量的根本不是同一件事。[E13][E26]

---

## 9. 这份分析不能证明什么

1. **不能证明它的评测数字可信**：我没有复跑任何评测，也无法复跑——评测脚本、匹配规则、基线文件都不在公开仓库里；论文只到 "matching these generated comments against the Ground Truth" 这一句。[E12][E14]
2. **不能证明"80 名资深工程师"真的按协议做了**：这是论文自述；没有 κ/IAA/分歧率，发布数据里也没有标注者字段可以复算。[E10][E11][E08]
3. **不能证明 640 条 label=0 是怎么产生的**：卡片与摘要合起来支持"同一轮标注中被判不正确的那些"，但没有一句话直说；也没有说明是"两人都判错"还是"专家组改判"。[E07][E50]
4. **不能证明 branch protection 真的开着**：`gh api .../branches/main/protection` 用我的凭据返回 403（`Resource not accessible by personal access token`），只能引用项目自评。[E58][E21]
5. **不能证明当前覆盖率是 90.2%**：那是项目在 OpenSSF 自评里写的数；本机没有跑 Go 测试，我也没有拉取覆盖率报告。[E26]
6. **不能证明它的生产数据**（2 万月活、30%+ 采纳率、误报率 <5%、80% 建议被合并）：全部来自官方博客自述，仓库里没有任何遥测产物可供核对。[E19]
7. **不能证明 12 个 PR 的样本能代表 599 个已合并 PR**：我只按 `updated` 倒序取了前 12 个（样本偏向近期、偏向活跃维护者），只是"抽样里 12/12 有人类批准"，不是"全部 599 个都有人类批准"。[E22][E57]
8. **不能证明"仓库里没有评测工具"就等于"他们内部没有"**：我只能证明**公开仓库的 956 个文件里**没有评测脚本/基线/门槛；博客明确提到内部技能 `/release-eval`，那份代码没有公开。[E14][E15]
9. **不能证明论文 v1 与 v3 的差异是唯一差异**：我只对比了"模型个数（seven → 6）"与若干关键句；没有做全文 diff。[E35]
10. **不能证明它的测试质量**：用例数、测试行数、覆盖率都是**规模**指标；我没有跑它的测试，也没有做变异测试去验证"测试是否真的能发现缺陷"。R2 那条守卫之所以值得抄，恰恰说明作者自己知道"测试全绿"不等于"测到了"。[E02][E31]
11. **不能证明它自述的"英文校验 / 行尾校验 / action pin 校验"在本机可执行**：我读到的是 workflow 与脚本原文，没有在它的仓库里跑过。**同一条限制也适用于我在本仓写的这份文件**（见下）。[E04]
12. **不能把它的做法直接搬来当"我们的评测方法"**：它评的是"模型能不能生成正确的评审评论"，本仓评的是"规则判定对不对/证据够不够"；判据对象不同、标签体系不同、没有可对齐的连接键。[E12]

---

## 附录 A：证据索引（命令 → 取到的内容）

> 说明：arXiv 引文的「v3 第 N 行」指**我用脚本从 arXiv HTML 抽取出的纯文本**的行号（`https://arxiv.org/html/2601.19494v3` → `.tmp/ocr-hf/arxiv_v3.txt`，83,110 字符），不是论文排版页码/行号；仓库文件的行号对应快照 main = `182898c`。

- **[E01]** `gh api 'repos/alibaba/open-code-review/git/trees/HEAD?recursive=1'`（Python 解析）：`total 1123, truncated False`；顶层 `internal/` 394、`pages/` 232、`extensions/` 213、`cmd/` 97、`plugins/` 36、`.github/` 23（含 `workflows/` 12 个文件）。落盘 `.tmp/ocr-tree.json` / `.tmp/ocr-tree.tsv`。
- **[E02]** 计数脚本 `python .tmp/ocr_census.py`、`.tmp/ocr_counts.py`（对 `codeload.github.com/alibaba/open-code-review/tar.gz/refs/heads/main` 解包后的 956 个文件）：Go 测试文件 234 / `^func Test` 2505 / `t.Run(` 655 / `^func Benchmark` 0 / `testing.B` 0 / 测试行 75,794 / 非测试 Go 行 36,367（130 文件）；`/testdata/` 目录 0；`golden|snapshot` 0；`t.TempDir()` 822、`t.Setenv()` 329、`t.Helper()` 188、`t.Parallel()` 8。
- **[E03]** `Makefile`（`gh api .../contents/Makefile`）：第 44-57 行 `test`/`COVERAGE_THRESHOLD := 90`/`coverage`；第 42 行 `PACKAGES := $(shell $(GO) list ./... | grep -v /extensions/)`。
- **[E04]** `.github/workflows/ci.yml`（196 行）：第 84-97 行覆盖率步骤与 90 门槛；第 123-168 行 windows job（含第 137-141 行"无 -race、无覆盖率门槛"注释与"80%"字样）；第 170-196 行 cross-compile 矩阵。
- **[E05]** `ASSURANCE_CASE.md` 末表 "Automated Verification"：`go vet` / `govulncheck` / `go test -race` / Dependabot / `go.sum`。
- **[E06]** `README.md` 第 43-102 行（What is / Benchmark / Why）。
- **[E07]** `https://huggingface.co/datasets/Alibaba-Aone/aacr-bench/raw/main/README.md`：第 18 行 "The dataset contains 2,145 code review comments, consisting of 1,505 expert-verified correct comments and 640 incorrect comments."；第 24-45 行字段表；第 52-59 行 BibTeX（arXiv 2601.19494）。
- **[E08]** `https://datasets-server.huggingface.co/size?dataset=Alibaba-Aone/aacr-bench` → `num_rows 2145, num_columns 16`；`/splits` → 仅 `default`/`train`；`/first-rows?...` → 16 个字段逐个列出，行内无标注者字段。
- **[E09]** `https://datasets-server.huggingface.co/filter?dataset=Alibaba-Aone/aacr-bench&config=default&split=train&where="label"=0&limit=1` → `num_rows_total: 640`（label=1 的同一查询返回 HTTP 500，故 1,505 由 2145−640 与卡片互证）。
- **[E10]** arXiv HTML v3 第 1475 行（附录 B.1 "Review Completion and Expert Annotation" 第三段）。
- **[E11]** `python .tmp/ocr_v3.py`：对 `https://arxiv.org/html/2601.19494v3` 抽取的 83,110 字符全文检索 `kappa`/`inter-annotator`/`agreement`/`Cohen`/`Fleiss`/`IAA` **全部 0 命中**；v1 全文同。
- **[E12]** v3 第 289 行（匹配与真值规模）、第 306-307 行（PR 五条过滤、分层抽样、Augmented Review Comments）、第 311 行（6 模型生成矩阵 + 两套异构框架）；v1 同处第 293-296 行。
- **[E13]** v3 第 405 行（三个指标）；附录 C.1（Temperature=0.7 / Top_p=0.95 / Top_k=20；非 Agent 流程；Top-3 上下文）。
- **[E14]** 文件名与全文检索：`baseline|leaderboard|groundtruth|eval|bench` 只命中 `imgs/benchmark-*.png`、`pages/src/components/BenchmarkSection.tsx`、`pages/src/pages/BenchmarkPage.tsx`；本地无任何评测脚本/基线/门槛文件。
- **[E15]** `pages/src/content/blog/en/oss-two-month-retrospective.md`：第 133 行 `/release-eval`（"one run takes 8 hours"）；第 142 行"稳定性靠……E2E eval set (200 PRs)"；第 160 行 HN 事故与两条规矩；第 122-124 行"100% AI-generated, 100% AI-reviewed / What do the humans do? Review the AI's output and make the final calls"。
- **[E16]** `internal/config/template/prompts/review_filter_task_system.md` 第 7-12 行。
- **[E17]** `internal/agent/agent.go` 第 1798-1922 行：`err != nil` 分支（1871-1879）与 `len(indices) == 0` 分支（1894-1900）都不删评论；`internal/agent/coverage_test.go` 第 202-390 行的相关用例。
- **[E18]** `GOVERNANCE.md` 第 134-145 行（"at least one maintainer of the affected area should review the change"）；第 124-132 行 lazy consensus；第 165-181 行 continuity/bus factor。
- **[E19]** `oss-two-month-retrospective.md` 第 18 行（20k MAU / 30%+ / <5% / ~80%）、第 31 行、第 38 行（主动暴露缺点）、第 240 行（留人）、第 244-248 行（三层支撑）。
- **[E20]** `scripts/github-actions/post-review-comments.js` 第 2851-2862 行（fail-closed 检查点 + 信任边界）、第 3056-3076 行（契约注释，逐条列出 13 个 fail-closed 原因）。
- **[E21]** `https://www.bestpractices.dev/projects/13328.json` → `two_person_review_justification`（原文见 §7.0）。
- **[E22]** `gh api -X GET search/issues -f 'q=repo:alibaba/open-code-review is:pr is:merged' --jq .total_count` → `599`；对 updated 倒序前 12 个 PR 逐个取 `repos/.../pulls/{n}` 与 `/pulls/{n}/reviews`（脚本 `.tmp/ocr_prs2.py`）：12/12 有非作者人类 APPROVED；`merged_by` 全为 `lizhengfeng101`。
- **[E23]** `CONTRIBUTING.md` 第 147-164 行（AI-Assisted Development 八条）；`AGENTS.md` 同文；`.github/pull_request_template.md` 第 30 行（AI 披露勾选项）。
- **[E24]** `README.md` 第 55 行。
- **[E25]** v3 "Paradigm Shift" 三条（Precision-Recall trade-off / Adaptive Context Awareness / Unifying Local and Global Perspectives）。
- **[E26]** `bestpractices.dev` 同一 JSON：`test_statement_coverage80_justification`（"enforces an 80% statement coverage threshold ... Current total statement coverage is 81.2%"）与 `test_statement_coverage90_justification`（"fails the build if coverage drops below 90% ... 90.2%"；并解释 Makefile 口径 90.6%）；`test_branch_coverage80_status = "N/A"`；`regression_tests_added50_justification`（"The project has 35 test files"）。
- **[E27]** `.github/workflows/ci.yml` 第 137-141 行 vs 第 93 行（80 vs 90）。
- **[E28]** `scripts/github-actions/post-review-comments.test.js` 第 3609-3611 行（`twelve` / `testCheckpointTwelveReasonsAreDistinct`）vs 第 5432 行（`assert.strictEqual(failClosed.length, 13, "thirteen fail-closed reasons")`）。
- **[E29]** `cmd/opencodereview/retry_fake_llm_test.go` 第 27-34 行（共享 fixture 与理由）、第 35-49 行（`fakeLLM` 注入 429/402）；`internal/llm/client_test.go` 等 10 个文件里的 `httptest.NewServer`（全仓 69 处）。
- **[E30]** `cmd/opencodereview/manual_e2e_retry_test.go` 第 4-15 行（`//go:build manual_e2e` + 运行命令 + 目的）。
- **[E31]** `retry_fake_llm_test.go` 第 71-91 行（`assertGroupingRecognized` 与 "Every assertion would still pass with the coverage gone."）。
- **[E32]** `gh api repos/alibaba/open-code-review` → `language "Go"`、`license.spdx_id "Apache-2.0"`、`created_at 2026-05-18`、`pushed_at 2026-10-05T06:43:52Z`、`stargazers 44127`、`forks 3188`、`open_issues 283`、`size 55120`。
- **[E33]** `cmd/opencodereview/main.go` 全文（31 行）。
- **[E34]** `https://huggingface.co/api/datasets/Alibaba-Aone/aacr-bench` → `tags` 含 `arxiv:2601.19494`；卡片第 52-59 行 BibTeX；`sha 47be1d6df1e7faf222cf531587772d92f79fe6b2`、`lastModified 2026-02-02T06:59:14Z`、`downloads 916`、`likes 13`。
- **[E35]** `https://arxiv.org/abs/2601.19494` 提交历史（v1 2026-01-27 / v2 2026-01-29 / v3 2026-01-30）；v1 正文 "seven mainstream open- and closed-source models" vs v3 "6 mainstream open- and closed-source models(Claude-4.5-Sonnet, ...)"。
- **[E36]** `ASSURANCE_CASE.md`（120 行）：Threat Model 表 T1–T7、Saltzer & Schroeder 映射表、OWASP/CWE 映射表、Automated Verification 表。
- **[E37]** `internal/agent/coverage_test.go`（1,004 行，24 个 `func Test`）与 `internal/scan/coverage_test.go`（1,365 行，29 个）头部与函数清单。
- **[E38]** `package.json` 第 16-21 行：`test:github-actions` 串四个脚本、`test:launcher`。
- **[E39]** `.github/workflows/action-contract.yml` 第 57-61 行。
- **[E40]** `.github/workflows/plugin-contract.yml` 第 76-86 行；`scripts/github-actions/check-plugin-contract.js` 第 77 行（"Fail-closed floor for the link corpus"）。
- **[E41]** `.github/workflows/translation-sync.yml` 第 38-57 行（`continue-on-error: true` 只出现在 `docs` 那一步）。
- **[E42]** `.github/workflows/pages-ci.yml` 第 28-83 行；`pages/package.json` 的 `size-limit` 150 kB。
- **[E43]** `.github/workflows/{frontend-ext,idea-ext,vscode-ext}.yml`。
- **[E44]** `.github/workflows/codeql.yml`。
- **[E45]** `.github/workflows/ocr-review.yml` 第 24-64 行（`pull_request_target` 的理由与 `uses: ./`）。
- **[E46]** `examples/github_actions/README.md` 第 612 行。
- **[E47]** `examples/gitlab_ci/post_review.py` 第 1505 行（`fail_on_severity` 默认空）、第 1530 行 `check_fail_on_severity`、第 1645-1646 行。
- **[E48]** `AGENTS.md` 的 "## Testing" 段。
- **[E49]** `pages/src/components/BenchmarkSection.tsx` 第 42-57 行（13 行原始数据，含 `precisionDetail` / `recallDetail` / `tokenDetail` / `version`）+ 第 1-57 行结构；`pages/src/i18n/en.ts` 第 81-91 行（列名与副标题）。
- **[E50]** v3 第 219 行（"80 senior software engineers (each with 2+ years of industry experience) meticulously reviewed 2,145 comments generated by two ACR systems across six LLMs"）。
- **[E51]** v3 第 1441-1444 行区域（"Constrained by the cognitive boundaries and capacity limits of human reviewers..."；`Qwen3-235B-A22B-Thinking-2507` 去重；"the election of results running 5 times of judgement"）。
- **[E52]** v3 附录 Table 8（0 模型 360 / 1 模型 1027 / 2 模型 107 / 3 模型 11）与解读。
- **[E53]** 全文检索 `threshold|THRESHOLD`（354 处、64 个文件；排除 rule_docs 与 i18n 的 `.md`）逐条归类：工程参数（`incremental_overlap_threshold` 0.6、`OCR_RATE_LIMIT_THRESHOLD`、路由阈值、`PLAN_MODE_LINE_THRESHOLD` 默认 50）、覆盖率 90、bundle 150 kB；与质量词共现的仅 2 处（plan 阶段行数阈值说明）；**无质量门槛**。（分类脚本：`.tmp/ocr_thr.py`、`.tmp/ocr_thr2.py`）
- **[E54]** `internal/agent/coverage_test.go` 中 `TestExecuteReviewFilter_OmitsToolChoiceAndFailsOpenWithoutToolCall` 等用例名清单。
- **[E55]** `internal/config/template/prompts/review_filter_task_user.md` 第 7-11、19-29、31-41、43-50、52-68、82-85 行。
- **[E56]** `extensions/frontend/src/shared/i18n.ts` 第 159 行 `'ext.comment.statusFalsePositive': '✅ [False Positive]'`；`extensions/vscode/README.md` 第 17 行（apply / dismiss / false-positive 两向同步）。
- **[E57]** 同一批 `/pulls/{n}/reviews` 原始输出（脚本 `.tmp/ocr_prs2.py`）：如 #1610 `Qiyuanqiii`(CHANGES_REQUESTED 09-30) → `Qiyuanqiii`(APPROVED 09-30) → `lizhengfeng101`(APPROVED 10-05)；#1056 `wu21-web` 三次 APPROVED 夹一次 CHANGES_REQUESTED；#1393 六个用户 18 条评审事件。
- **[E58]** `gh api repos/alibaba/open-code-review/branches/main/protection` → `rc=1`，`{"message":"Resource not accessible by personal access token", ..., "status":"403"}`。
- **[E59]** `.github/pull_request_template.md` 第 14-32 行。
- **[E60]** `bestpractices.dev` JSON：`badge_level "gold"`、`tiered_percentage 300`、`achieved_passing_at 2026-06-26`、`achieved_silver_at 2026-06-27`、`achieved_gold_at 2026-08-06`；README 第 26 行徽章。
- **[E61]** v3 第 734 行（limitations 段原文）。
- **[E62]** `scripts/github-actions/post-review-comments.test.js` 第 5395-5456 行（三处文档比对 `testCheckpointReasonsMatchTheDocs`；"drifted between them once"；从 `HELPER_SOURCE` 切契约注释；README 表格正则）。

> 数字陷阱提醒（与姊妹文档一致）：arXiv HTML 会同时渲染正文与 MathML 备选文本，导致数字"打印两遍"（如 `1,505` 抽成 `1,5051,505`、`200` 抽成 `200200`、`80` 抽成 `8080`）。本文引用时按语义还原；**v1 的 "seven" 与 v3 的 "6" 是英文单词与阿拉伯数字，不受此影响**，属真实措辞变更。[E35]

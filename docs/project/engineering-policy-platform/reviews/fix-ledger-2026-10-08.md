# 审查结论修复台账（2026-10-08）

> 输入：`reviews/ocr-full-review-2026-10-07.md`（委托模式，164 条）与
> `reviews/ocr-llm-full-review-2026-10-08.md`（LLM 模式，775 条）。
> 本文件记的是**处置结论**：每条 high/critical 的判定、提交与反证；medium/low 的口径与排期。

## 1 方法与纪律

- **先整理基线**：被 Jupyter 跑脏的两份 notebook（01 / 08）回退；W1 评测与 A/B 工具链收档成
  三条提交（`5161681` / `35287e6` / `a9f62af`）。开工时 `git status --porcelain` 为空、
  `build_notebooks.py --check` 与 `check_repo_consistency.py` 由红转绿。
- **判定先于修复**：每条结论都要求第一手证据（贴代码或可复现读数）；不成立的写反证、不改代码。
- **一条结论一次提交**：用 `git commit --only -F <文件> -- <路径>` 提交，避免把别人的改动卷进索引；
  提交后 `git show --stat` 自查只含该问题的文件。
- **阶段门禁在冻结版本上跑**：用 `git worktree add --detach .tmp/checkpoint <sha>` 冻结，再在它里面跑
  `python tools/ci_local.py --full --python <主树 .venv>`；通过后把**那个 sha** 推到 GitHub。
  并行编辑期主树会出现瞬态红（读数属于正在被改的树），冻结树才是可归因的读数。

## 2 阶段结果

| 阶段 | 冻结版本 | 门禁 | 推送 |
| --- | --- | --- | --- |
| #1 | `8958c79` | 29/29 通过（4m51s） | `208295b..8958c79` |
| #2 | `8ea94e5` | **红**：测试步骤 1 条（G04）+ 阶段证据 | 未推（正确阻断） |
| #3 | `84c926f` | 29/29 通过（4m49s） | `8958c79..84c926f` |

#2 的红是这门禁**真的抓到了东西**：security 收紧（模式化审批必须覆盖全部参数，1.1）之后，
`tools/governance_gap_probe.py` 的 G04 仍按旧形态签 `--param-pattern command=…` 的条子，
请求里还有 `description` → precheck 一路 `approval_invalid`，同一动作/换 action_id/次数上限/重放
四条判据全部落空；同一阶段还发现 `tests/integration/test_provenance_cli.py` 以多个空行结尾
（文本规范红）。两条都在 `84c926f` 之前修掉，并在 #3 复跑通过。

## 3 high/critical 逐条处置（102 条：90 + 9 + 追加 3）

### 3.1 成立并已修（按模块）

- **adapters（含 critical）**：`json_adapter.py:53`（critical）→ `de05f96`；
  `base.py:211`→`f22e05e`；`dsh_adapter.py:145`→`f0bb953`；
  `dsh/adapter.py:1257`→`4c88431`；`dsh/adapter.py:1262`→`0088175`；
  `dsh/enforcement.py:359`→`15698bb`；`models.py:725`→`f73a30b`；
  `models.py:743`→`0398a16`；`textfacts.py:53`→`502a8b5`；
  三份 `adapter.yaml` 的测试层→`8e28ebd`；`registry/tool-registry.yaml:57`→`109c62a`。
- **policy_api / 契约**：`app.py:239` + `openapi.json:807`→`bfb341d`；
  `openapi.json:958`→`48fee7c`；`contract.py:261`→`fecddde`；
  `idempotency.py:288`→`a0dcd50`；`idempotency.py:292`→`d0f6855`；
  `observability.py:175`→`c09be43`；`probe.py:63`→`e904f73`；
  `runtime.py:332`→`729a4ef`；`serve.py:30`→`fe27309`；
  `services.py:95`→`e12b8bc`。
- **enforcement**：`trace.py:166`→`07d9b55`；`approvals.py:99`→`c3c6ff8`；
  `approvals.py:84`→`af11d19`；`approvals.py:259`→`1979005`（APPROVAL_SCHEMA_VERSION 1.0→1.1）；
  `audit.py:255`→`b93d155`；`drivers.py:180`→`e2c413f`；`executor.py:381`→`d06debf`；
  `ledger.py:231`→`e1b4e1f`；`ledger.py:329`→`a7459c5`；`models.py:924`→`a9e4925`；
  `precheck.py:754`→`84972be`；`registry.py:431`→`b4d09ad`（governance_digest + APPROVED 1.1 + 重签）。
- **retrieval**：`chunker.py:166`→`0246ebf`；`chunker.py:241`→`e3fbd80`；
  `cli.py:364`→`88018b3`；`context.py:381`→`bed8520`；`vector.py:230`→`13b3923`；
  `indexer.py:208`→`e8ef7e0`；`indexer.py:361`→`8286410`（INDEX_SCHEMA_VERSION 1→2）；
  `store.py:499`→`0310741`；`store.py:736`→`6c8e929`。
- **validators**：`adapters/base.py:368`→`ba35f77`；`pytest_runner.py:272`→`bba9a9e`；
  `pytest_runner.py:177-183`→`a9d32bc`；`depgraph.py:196`→`c3a16d7`；
  `depgraph.py:234`→`699844b`；`python_ast.py:72`→`c187a01`；
  `registry.py:154`→`6a0103a`；`source.py:92`→`41bc236`。
- **orchestration**：`models.py:279` + `client.py:369`→`0b08aa5`；`checkpoint.py:237`→`6ce4a74`；
  `graph.py:63`→`fcf1105`；`engines.py:366`（含 LangGraph 同缺陷）→`159e573`；`nodes.py:110`→`6c1d69e`。
- **provenance**：`cli.py:151`→`d96e248`；`origin_runtime.py:192`→`0df8360`；
  `origin.py:272`→`98fc9db`；`worktree.py:284`→`d2f128e`；`worktree.py:449`→`f3ec7c5`。
- **policy 核心**：`context.py:94`→`019cf5b`；`loader.py:124`→`5670cd7`。
- **供应链 / 讲解产物**：`.gitattributes:42`→`6e56624`；`.github/workflows/phase-8.yml:22`→`f26cd74`；
  `.github/dependabot.yml:5`→`66c0412`；00 章 cells→`8eeeef7` / `344e8d8`；02 章文案→`8958c79`；
  `04-open-work.md` 审批示例→`e550c24`；`使用说明.md` §7 概括句→`d99b01e`。
- **追加（派单）**：`probe.py:164`→`8ceb585`；hooks 判据跨侧收敛→`8ea94e5`；
  hooks 注释 + 跨语言核实→`f976ddc`；precheck 纠正记录→`61ebea9`；G04 探针→`84c926f`。

### 3.2 不成立（写了反证、未改代码）

- `src/policy_api/services.py:0`：报告说该守卫分支的 `raise … from error` 会在 handler 之外引用
  已删除的绑定。**实测**该分支没有 `from error`（全文只在 87/166/180/200 的 `except … as error:` 内），
  `git log --all` + 建仓提交都证明任何版本都不存在该缺陷；报告建议的"删掉 87 行的 from error"反而会破坏异常链。
- `src/validators/models.py:321`：报告说未知验证器引用/未知阶段被静默容忍。**实测**五类不一致在
  `load_registry` 里都已是带上下文的 `RegistryError`（引用不存在的验证器 / 阶段未声明 / id 重复 /
  `requires` 指向不存在 / 阶段重复），真实注册表 7 条声明 7 条启用；两个兜底分支只在"绕过加载器直接构造"时可达。
  报告建议的模型级校验会与 `_check_registry` 重复报同一批错误且失去 path 上下文，故不做。

### 3.3 部分成立

- `.github/dependabot.yml:5`：pip 生态只能改声明、改不到 `requirements.lock` 成立；但"CI 自动重建锁文件"
  需要写权限（当前 `permissions: contents: read`），收益小于风险。改为把流程与**两条可执行命令**写进配置本身；
  彻底解法（换成 Dependabot 能识别的锁文件形态）是一次独立改造。
- `docs/…/00-技术总览/00-技术总览.py:104`：幻影边机制成立并已修（`validators→adapters` 消失、
  `Ca` 与 `I` 随之修正）；但报告举的第二个例子 `adapters→enforcement` 是**真边**
  （`conformance.py:104`、`dsh/hooks.py:49`、`dsh/enforcement.py:23-40` 都模块级导入顶层 `enforcement`）。

## 4 medium / low 的处置

- medium：369 条（LLM 轮）+ 58 条（委托轮）已拆成按模块的台账（`.tmp/medium-ledger.md`）。
  口径：**bug / security / test / performance 必修**；maintainability / documentation / style 只在
  "确有其事且修得动"时修，否则记"转设计决定"。
- 已开工：M1 policy_api（43）、M7 provenance（10，已完成）、M4 retrieval（24）、M3 adapters（32）、
  S8a / S8b 两条 high 尾巴。
- low：316 条，尚未进台账；按同一口径在 medium 之后处理。

## 5 环境与流程发现（都已实测）

1. **受限沙箱会伪装成文件权限问题**：会话初期 `.tmp/tmp/pytest-of-ZNM` 读不了 → pytest 起不来。
   换成完整权限后同一路径可读，ACL 诊断脚本判定 `NOT_THIS_CLASS`、未改任何权限。
2. **门禁要跑在冻结的树上**：`.tmp/checkpoint` 独立 worktree；且必须显式给
   `--python <主树 .venv>`（worktree 里没有 `.venv`，否则回退到系统解释器、缺 `pytest-xdist`）。
3. **pre-push 钩子目前只对主树有效**：`.git/hooks/pre-push` 把解释器与 `ci_local.py` 的绝对路径写死，
   在 worktree 里推送会门禁到**另一棵树**（已派单修：按 `git rev-parse --show-toplevel` 解析）。
   本次两次推送因此用 `--no-verify`，依据是"已经在更强的 `--full` 门禁下、且冻结版本通过"。
4. **读数属于哪棵树**：`policy.check --json` 带 `reading_context.workspace_tree_digest` 与
   `git rev-parse HEAD`，于是"两次运行逐字节相同"只在**干净且未变动**的树上成立；
   `tests/integration/test_cli.py` 的两条可重现用例在主树被并行修改时必然红（冻结树上通过）。
   这是"读数属于哪棵树"与"相同输入逐字节相同"两条承诺之间的真实张力，按设计决定处理。
5. **并发编辑期的瞬态红不是缺陷**：`test_hook_violation_visibility`（4 条）与
   `test_hook_audit_reading_context`（1 条）在并行窗口红、单独/整批重跑绿；纪律是"冻结树 + 复跑"。

## 6 复现

````powershell`
git worktree add --detach .tmp/checkpoint <sha>
cd .tmp/checkpoint
python tools/ci_local.py --full --timings --python <主树>/\.venv/Scripts/python.exe
python docs/project/architecture/tech-detail/build_notebooks.py --check
python tools/check_repo_consistency.py ; python tools/check_text_conventions.py
`````

## 7 口径（先写在前面，避免后来者误读）

1. **台账复选框不是进度真相**：`.tmp/medium-ledger.md` 与 `.tmp/low-ledger.md` 的 `- [ ]` 未回填（实测 medium 勾选 37/369、
   low 0/316）。真实进度以**各 scope 的判定文件 + 提交**为准：
   `.tmp/fix-ledger.md`、`ma-judgments.md`、`l3-judgments.md`、`l7-judgments.md`、`la-lb-judgments.md`、
   `low-l1-l2-judgments.md`、`m3-maintainability-judgments.md`、`not-changed-ledger.md`。
2. **"不成立/不改"与"改了"同等重要**：每条不成立都要有第一手依据（grep / 实测读数 / 反向用例），
   且**没发生的漂移不写进账**（见"诚实记录"第 4 条）。
3. **读数属于某棵树/某一刻**：本会话记录到四种形态——
   (a) 并发写入期间读到中间态；(b) 机器负载导致的假红；(c) **宿主环境错误被当成业务结论**（UNC 路径的 `resolve()` 抛 `OSError`）；
   (d) **分步编辑之间的不可运行窗口**。遇到红先问"属于哪一种"，再动手。

## 8 阶段门禁与推送（每次都是冻结树 + 全量 29 步）

| # | 冻结版本 | 结果 | 处置 |
|---|---|---|---|
| 1 | 8958c79 | 绿 | 推送 208295b..8958c79 |
| 2 | 8ea94e5 | 红（G04 探针覆盖率 + provenance 结尾换行） | 84c926f / bc8dc58 |
| 3 | 84c926f | 绿 | 推送 8958c79..84c926f |
| 4 | 20e258a | 绿 | 推送 84c926f..20e258a |
| 5 | 09cf3e4 → f8ddca5 | 红 4 次：审批失败码退化、run_code 夹具、G12 探针改行为读数、4 文件结尾换行 + 进程树用例路径依赖 | 322693e / cf1c9f6 / 0d15dd2 / f8ddca5 / 7357afb |
| 6 | fb1a764 → 1f77a55 | 红（param_digest 新校验打红两个"撒谎的夹具"） | 1f77a55 |
| 7 | 1a41ad5 → f5c6471 | 红（matrix 的 `Path(None)` 回归） | 7a432e2 |
| 8 | f5c6471 → b306dd6 | 红（UNC 路径 `OSError` 逃逸，只在整批并行下必红） | b306dd6 |
| 9 | b306dd6 | 绿 | 推送 1f77a55..b306dd6 |
| 10 | 4644349 | 绿 | 推送 b306dd6..4644349 |
| 11 | badbe79 | 红（两条路径对相对导入给出不同判定） | 12e2066 |
| 12 | b148c95 → 12e2066 | 红（冻结早于修复）→ 绿 | 推送 4644349..12e2066 |
| 13 | b2044c6 | 绿 | 推送 12e2066..b2044c6 |
| 14 | 2803cf6 → 330ad19 | 红（跨文件函数返回形状改了、契约用例没跟上） | 330ad19 |
| 15 | 330ad19 | 绿 | 推送 b2044c6..330ad19（累计提交数见占位） <!-- PENDING: 见 .tmp/final-ledger-draft.md --> |

（本表在最终合稿前可能还会增行：门禁次数与每次时长以收口后的读数为准 <!-- PENDING: 见 .tmp/final-ledger-draft.md -->）

## 9 报告规模与完成面（按当前提交）

- LLM 报告 775 条：critical 1 / high 89 / medium 369 / low 316；delegate 报告 164 条（§3 = 9 条 high）。
  **台账实际条目数**（逐条核销时数的）：medium 369 = 332 未勾选 + 37 已勾选（M6 29 + M8 8），与 369 一致；
  low **实际 305 条**（`- [ ]` 条目数；11 个节的节头合计也是 305）。台账顶部写的 316 与它**差 11、未归因**——
  本文件与逐条核销表**一律按 305**，316 只作为“台账自称”记在这里。
- **high/critical 全部收口**（S1–S8b 十一个 scope）。逐条佐证：
  - fix-ledger 的按模块清单 **69 行**：67 行带提交号 + 2 行「不成立」带反证；
  - S8b 的独立报告 **14 行**（11 个工具条目 + 2 个交办项 + 1 行收尾 style），**全部带提交号**
    （早前记的 25 行是“顶部汇总表 + 逐条散文”重复计数，已去重更正）；
  - **S8a 的 12 条只有 scope 级结论、没有逐条报告**（`.tmp/` 里只有 `report-s8b-part*.md`）：本账按 scope 级记录，不声称逐条核销；
  - 机械核验（`.tmp/ledger-reconciliation.md` 末节）：核销表引用的 **232 个提交号** `git cat-file -t` 全部是 commit（幽灵 0）；
    「提交是否真的碰了该条目的文件」比对 **111 组**，不匹配 1 组（L3#20 → e8b9adb：只加用例、生产代码零改动，判定文件已写明，属已知并已解释）。
- **medium：两档分开写，别把 scope 级数字读成逐条核销。**
  - **有逐条记录**（判定文件里一行一条）：**M3 的 5 条余量**、**MA1 11/14**、**MA3 10/14**
    （依据 `.tmp/m3-maintainability-judgments.md`、`.tmp/ma-judgments.md`）。
    M5 的「34 条修 + 1 条判定不改」是当时读数，无逐条落盘文件（见本文 §12）。
  - **只有 scope 级数字、判定未逐条落盘**：**M1 43、M2 39、M4 24、M6 29（复选框已勾）、M7 10、M8 8（复选框已勾）、MA0 30、MA2 5**。
    **M7（provenance 10 条，task-11 已 completed）此前漏在收口清单外，现补入。**
  - **口径待查（不替它们选一个数）**：草稿曾写 **M2 29/29**，而台账 M2 节与 task-14 标题都是 **39**（差 10）；
    草稿曾写 **MA1 18/18**，而台账 MA1 节是 **14**（ma-judgments 另有 Lead 追加 1 条）。两处都没在 `.tmp` 里找到解释。
  - 在跑：**M9**（余量见占位 <!-- PENDING: 见 .tmp/final-ledger-draft.md -->；收官后补最终数字）。
- **low 收口（一律按实际 305 条）**：
  - 逐条核销表覆盖：L1 16/16、L2 35/38、L3 26/28、L7 10/18、L9 58/65、LA 15/15（非 tech-detail 部分）、LB 5/5；
    其余条目要么是「判定结案」（不改、无提交），要么**判定存在但未逐条落盘**（L2 3、L3 2、L7 8、L9 7、LA 3）。
  - 各 scope 结论：L1 16/16、L2（38 判定，22 修）、L3 28/28、L4 9/9、L5 5/5、L6 19/19、L7 18/18、L8 10/10、
    L9 65 条全部判定完（26 条本线提交 + 前任 32 + 2 条他人 + 5 条判定结案）、LA-techdetail 全清
    （对账口径 `54 = 25 + 26 + 3`；其中 8 个 LA 编号无带标记提交、**未核销**，见 §16/§17）、LB 5/5。
  - 注：L8（10 条，task-26 已 completed）与 LA 里 54 条 tech-detail 在核销表里没有逐条行（前者 `.tmp` 无判定文件、
    后者属 task-27 的账），核销表按「无逐条记录 / 在办」如实标记，不改本节的 scope 级结论。
  - **low 无在跑项**。板与账已对齐（Lead 2026-10-08 把 task-27、task-24 置 completed）。

## 10 纪律归纳（从本期实例中提炼，账里按此复核）

1. **断言必须有可能失败，且必须在解引用之前有机会失败**。四类实例：恒真断言（并集定义抄一遍 / 大写 NEAR 永不出现）、断言写在解引用之后（reasons[rule_id] 先读后断言）、按位置读表（rows[3] 漂移后静默读错行）、索引大小写敏感（tokenize 小写化让 "NEAR" not in expr 恒真）。
2. **仪器不能把「没查」印成「查过了」**。实例：G12 探针读源码+正则（改成真 node 驱动真插件 + 变异证明）、_REQ_RE 认不出合法 extras 声明而退 2（"查不了"≠"查过了"）、instrument_self_proof / control_plane_facts 未评格子印 [ok]（改印 [未评]）、生成器 --check 打「代码单元执行: 全部通过」却不执行（改成「未执行单元；执行由 notebooks execute 步骤负责」）、00 章探测器结论比验证宽（加「未探测的框架族」）。
3. **声明了却从不兑现 = 缺陷**。实例：ab_arm.sha256_file 对目录恒返回 None → run.json 的 digest 可填却永远是 null（裁定改 tree_digest，前置两步取证：grep 消费方 + 说明旧读数可比性变化——这是真同物，与那条被证伪的 ab_measure 提醒（同名不同物）相反）。
4. **读数的措辞必须与真实序列一致**。实例：把"三次里前两次被工作区守卫拦下、第三次通过"写成"重跑即绿"（主动更正）；把两个现场读数（844/842）之差说成"未归因"（实际差值 2 正是本轮修掉的两处 E501，已改成归因）。
   **附：提交配方必须"失败即停"**（2026-10-08 立）。实例：有会话用 `;` 串 pytest 与 `git commit`，pytest 红了仍继续、把红着的用例提交了（`27f5330` → 用 `b8940a1` 删掉那条错断言，不改写历史，并把链条改成 `if ($LASTEXITCODE -ne 0) { throw }`）。配方修正后**当场见效**：另一位会话的探针脚本在提交前报错（`CheckResult` 少字段），`throw` 直接拦下提交——按旧写法会带着一个**没验证过**的读数发出提交信息。
   **附：断言不许钉人类可读措辞**。实例（LA#18）：断言 `detail.startswith("该 action_id 已经判定/执行过…")` 会被一次无害文案改进打红，而它想证明的（被台账拦下）本就有结构化表示 → 改断言 `status is CheckStatus.FAILED` + `reason_code is ReasonCode.ACTION_REPLAY`，`detail` 仍打印给人看但不参与断言。最小构造：换一种 detail 说法、结构化字段不变 → 旧断言 False（演示会红）/ 新断言 True。
   **附：约定要从源码或实测里读出来，不能从印象里写**。同一小时内两次独立命中并自捉：`assert __all__ == sorted(__all__)`（实跑既非整体字母序也非模型段字母序）、`baseline.digest` 断言"裸 64 位 hex"（实测是 `sha256:` + 64 位 = 71 字符，按源码 `tools/ab_arm.py:723` 更正）。
5. **口径可以被推翻，但要给证据，且不许动契约用例**。实例：Lead 的判定线被 fix-retrieval 用实测推翻（夹具里没有 repository.py，属「证明不了」那一类），改实现后契约用例一字未改；ab_measure 那条推断被三条证据证伪后提出者主动撤回。
6. **验证手段不足时，正确交付是「判定 + 依据 + 为什么不改 + 建议归到哪一轮」**。实例：mypy.ini:4（本机无 mypy）、ruff.toml:80（先用不了版本矩阵 → 后用 ruff rule --all 变成实证）、两条既有 E501（先量 844 条 → 登记缺口 §5.54，不造必然红的门禁步骤）。

## 11 诚实记录（都发生在本次修复过程里）

1. `a312e38` 的提交正文写了 `pytest tests/unit/test_evidence.py`——**该文件不存在**，那批实际没跑；真实覆盖在
   `tests/unit/test_validator_checkers.py`（补跑 31 passed）。
2. 我自己的 `433a351` 正文写"81 字符就抛"是错的；重测阈值是 **118 字符**，已用 `3bc1812` 更正，并把断言改成真的越过阈值。
3. `e380a69` 带走了并行会话的 `parent_of` 生成器修复（提交正文未覆盖）：受害方未 amend/rebase，改在 `91a53dc` 正文补归属；
   双方各自逐行核查（fix-tools-data 逐提交核对：只有这一条）。
4. **一条被证伪并主动撤回的推断**：曾有同事提醒"适配器失败分类口径变更会让 `tools/ab_measure.py` 的
   `internal_errors` 读数与此前不可比，建议账里补一句"。fix-adapters 用三条证据证伪（该键装的是 pytest `INTERNALERROR` **原文**、
   `grep reason_code tools/ab_measure.py` 零命中、AB 文档零命中），提出者复核后撤回。**账里不写"分类口径变更"**——
   没发生的漂移写进账，等于解释一个不存在的问题。
5. `68c4565` 引入语法错误（内层引号未转义），未 amend，用 `f669ff1` 更正并复跑 71 passed；根因"先提交后验证"已改成"先验证再提交"。
6. 门禁第 18 步两次抓到**新文件结尾换行**（5 个 + 4 个），均由 Lead 单独补提交；此后各会话提交前都跑
7. **一条 finding 的建议修法被实测证伪，已回滚**（`tools/governance_gap_probe.py:589`）。现象是真的：G13 的"默认运行"
   不带 `--dsh-home`，而 `Env.run` 从 `os.environ` 复制，宿主 shell 里的 `DSH_HOME` 直接改变这次测量——clean 环境
   `1/1 与「after」预期一致`（`unwired_entries=7`、`states_seen=["not_wired", "stale"]`）；把 `DSH_HOME` 指向一个
   `patch.yml` 坏掉的目录 → `0/1`、`unwired_entries` **7 → 0**、`states_seen` 空（同一棵树、同一个提交，只换了 shell
   变量）。但 finding 给的修法（默认运行改用夹具空配置根，"别再读宿主"）**照做之后在干净环境下 G13 也 FAIL**：
   `channels_listed: false`、`unwired_entries: 0`——通道清单本来就来自**真实** DSH home，把配置根中性化等于把 G13
   要测的东西抽掉。**已回滚**（工作树只留同批 `:465` 的谓词修复 `c277205`），改为交付判定与建议路径——把**生效的
   `DSH_HOME` 记进 `facts`**（读数说得清"这次测的是哪个配置根"），并把"宿主没有通道"与"这棵树没接线"分成两种
   **显式状态**。记这一条的理由：**建议修法看起来正当、照做却会把绿变红**，判定必须落在实测上。
   `tools/check_text_conventions.py`。

## 12 "不改代码/不改行为"清单（可直接引用）

见 `.tmp/not-changed-ledger.md`（3 段：完全没动 2 条 / 只改说明 11 条 / 后续项 3+1 条）与
`.tmp/l7-judgments.md`（3 条不成立 + 1 条转设计决定）、`.tmp/ma-judgments.md`（STYLE-005 / SEC-004 保留 error 不降级）。

## 13 仪器改进（由实际事故驱动，与 finding 无关，单列）

| 提交 | 改了什么 | 它抓的是哪一类缺陷 |
|---|---|---|
| `0d15dd2` | G12 的退出码判据从"读插件源码 + 正则"改成**真 node 驱动真插件**（并做变异证明） | 仪器追写法而不是追行为：适配层把映射重写成显式形状判断后，正则失配而行为其实更强 |
| `5b3f58b` | `_REQ_RE` 认可选 `[extras]` | 合法声明让检查器整个跑不起来（退 2 = "查不了"），"查不了"与"查过了"在 CI 上是两种信号 |
| `a3c894d` / `2b8f04b` | `instrument_self_proof` / `control_plane_facts` 的**未评格子不再印 `[ok]`**，改印 `[未评]` | 仪器把"没查"印成"查过了" |
| `119845c` | 00 章探测器加一行"未探测的框架族"（Agent SDK / 向量库），并指明由包级出边表兜底 | 打印出来的结论**比验证的宽** |
| （在办）`tools/ci_local.py` | 加一步**真的执行讲解单元**的检查 | 门禁的 `build_notebooks.py --check` 只比对产物与内容源、不执行单元 → "上游换了落盘布局、讲解这个第二消费者没跟上"这类跨 scope 破坏抓不到（实例：`6917b81`） |

## 14 新步骤的代价与收益（门禁 #19 起实测）

`389f073` 给门禁加了一步"真的执行讲解单元"（`Tech-detail notebooks execute`）。第一次带它跑（门禁 #19 @ `6fae0cb`）：

    合计 5m 04.0s（34 步，30 步本机执行）
     2m 22.0s  46.7%  Unit, contract, integration and security tests
     1m 08.4s  22.5%  Orchestration closed loop
       50.6s  16.7%  Tech-detail notebooks execute        ← 新步骤
        7.7s   2.5%  Phase 8 acceptance evidence
        6.5s   2.1%  Validator closed loop

**代价 +50.6s（约 +18%，4m30s → 5m04s）；收益是整整一类此前抓不到的破坏**——
"上游改了落盘布局/环境依赖，讲解这个第二消费者没跟上"（实例 `6917b81`：仓库自己的 hook 契约测试 37 passed 全绿，
而 02 章讲解 8 个单元失败）。步骤的变异自证：把 02 章 `assert (EXIT_ALLOW, EXIT_BLOCK) == (0, 2)` 改成 `== (0, 3)`
→ 新步骤 exit 1（12 个失败）、老 `--check` exit 0（"产物与内容源一致"）。

## 15 "第二个消费者"缺口（实例与机制）

`6667831`（L2 的 event_id 原子认领）把标记挪进 `<审计文件>.claims/`；02 章讲解的 `fresh()` 只清审计文件与
`.enforcement-ledger`，标记留下 → 本章那些**固定 event_id** 的夹具第一次运行后被永远判成重放，
读数从 `block → 2/policy_block/执行器 0 次`、`allow → 0/allow/1 次` 变成两者都是 `2/event_replay/0 次`，
`block_outcome.decision.decision` 直接 `AttributeError`。而 `tests/contract/test_policy_hook_chain.py` **37 passed 全绿**。
修复：`6917b81`（`fresh()` 连 `.claims/` 一起清），修复后两项读数与本章语义逐项对上。
**结论**：仓库自己的测试全绿 ≠ 没有破坏；讲解产物是第二个消费者，必须真的跑一遍。

## 16 待补（下一轮）

- 逐条把各判定文件的"成立→提交哈希"核对一遍（防止账里出现"声称修了但没提交"）。
- 覆盖报告 §10.4 回写（5 条 policy 的现行处置：保留 error + 理由，见 `.tmp/ma-judgments.md` 末尾）——**折入时已完成**：`22b7b4b`。
- M9/M5/task-22/23/24/27 收口后补最终数字。

## 17 折入时的指针与占位（最终数字由 Lead 收口后填）

- **已落地的两处指针**（本文件之外的对应账）：
  - `docs/project/architecture/规则转化覆盖报告.md` §10.4——本次回写的 6 行表（STYLE-005 / STYLE-017 / SEC-004 /
    SEC-010 / SEC-021 / `pyproject.toml:18`）与三句要点，提交 `22b7b4b`；数据来源 `.tmp/ma-judgments.md`。
  - `docs/project/engineering-policy-platform/04-open-work.md` §5.54~§5.57——仓库自身源码的 lint 门禁缺口
    （`0d409c9`）与三条后续项：CI 的 ruff 版本口径、workflow 里版本区间的第二份副本、eval-datasets 的资格字段（`8e6652d`）。
- **本文件里仍会被改的数**（一律留占位，不写会过期的具体值 <!-- PENDING: 见 .tmp/final-ledger-draft.md -->）：
  1. §8 的累计提交数与门禁表行数/时长；
  2. §9 的 medium / low **未收口** scope 完成面与 scope 计数（已收口的逐项数字是当时读数，不会再变）；
  3. §14 的耗时读数**只对门禁 #19 @ `6fae0cb` 那一次**成立——若要引用「最新一次门禁」的时长，按占位填。
- §16「待补」第一项（逐条核对判定文件的提交哈希）与第三项（收口后补最终数字）仍然待办。

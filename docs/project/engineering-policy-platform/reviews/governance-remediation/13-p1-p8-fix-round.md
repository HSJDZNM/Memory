# 修复轮：07 治理全开轮的 P1–P9（2026-09-27）

> 输入是 [07 治理全开轮](../governance-capability/07-governance-full-round.md) §4 的 **P1–P8** 及其
> §8「建议的下一轮」。07 轮把「治理全开」在真实会话里打开，也第一次暴露了八项问题——
> 其中 P1–P5 直接改变了「受治理会话能做什么、账本能读出什么」。
>
> 本轮的组网方式与前几轮一致：**Lead 定范围与接口，开四个子会话并行做互不重叠的写域，
> 每一条改动都配一条「修复前会红」的检查，最后 Lead 串行跑一次全量门禁并独立复核。**
> 子会话的产物（红→绿输出、复算脚本、复现）在 `.tmp/round-08/` 下，可随时重算；
> `.tmp/` 是构建产物，不提交。
>
> 三处**策略决定**（P2 哪些语言按设计不取证、P5 缺维度时失败关闭的边界、P6 台账存不存参数原文）
> 在 §1.3 里逐条给出理由与代价——它们不是实现细节，而是本轮真正的产出之一。
> 修复过程中又新显现一项（**P9**：Phase-4 阻断理由进审计时未脱敏），它可在真实链路上触发，
> 已一并修掉并留下探针（§4）。

## 0. 一句话

**九项全部处置**：P1/P3/P4/P7/P8/P9 是产品改动，P2/P5/P6 是"先定口径再改"的那一类。
账本现在答得出「**哪几条规则报了违规**」（07 轮实测 34 条判定记录里 `violations` 出现 **0** 次；
本轮同一个 07 轮遗留探针在受治理写类载荷上读出 **6 条**规则：ARCH-001 / DOC-001 / SEC-007 /
STYLE-001 / STYLE-006 / TESTING-001）；
打开取证之后非 Python 目标不再结构性不可写（`.md` 走**显式声明的不取证**而不是失败关闭，
且审计里写着"本次 0 条规则参与、43 条跳过"）；
取证树的范围进了审计（同一条载荷在"兄弟模块不在"与"在"两棵树上给出两个指纹、两个判定）；
同一个测试文件在两条判定路径上得到同一个层；
CLI 的「这次查了多少」变成可读字段；
台账的自述改成了它的行为；
写类越界的理由补上了「改成什么形态就能过」；
Phase-4 阻断理由进审计时与摘要链同一个脱敏实现。

**必须与结论一起读的取舍**：P2 让「平台按设计不验证 text」成为一条**显式、可评审**的声明
（代价是 `.md` 这类目标从此**可以写**，而平台对它的内容什么都没查——这件事只能从审计读出）；
P5 的失败关闭只落在**自相矛盾的调用**上（不给全部文档里的 `.md`/`.py` 检查命令加一道新门槛）；
P6 **改的是自述不是行为**（扣掉参数原文会让 PostToolUse 的重建永远失败）。

## 1. 本轮的范围

### 1.1 从哪来

| 编号 | 一句话（07 §4 原文口径） | 级别 | 本轮处置 |
| --- | --- | --- | --- |
| **P1** | 账本答得出「查了几条」，答不出「哪几条报了违规」 | 重要 | **已修**：判定记录新增 `violations` / `violations_by_severity` / `violations_note` |
| **P2** | 打开取证后非 Python 目标（`.md`）结构性不可写 | 重要 | **已修（数据 + 显式判定）**：`uncovered_languages` 声明 + `language_coverage` 判定；未声明的语言仍然失败关闭 |
| **P3** | 影子树的形状会改变工具结论（"先写测试"被自己的取证打成 warning） | 重要 | **已修（可读性 + 确定性）**：摘要新增 `tree` 段（范围 / 目标是否已存在 / 树 digest / 适用范围） |
| **P4** | M1 的修复只落在一条路径上：同一测试文件 Hook allow、`policy.check` block | 重要 | **已修**：`policy.check` 先查平台 `validation/test-layout.yaml` 的 `test_patterns`，并写出 `layer_source` |
| **P5** | 缺 `operation` 时 CLI 只是「多跳过」，判定照样 allow | 次要 | **已修（口径先定）**：`check_volume` + 自相矛盾调用失败关闭 |
| **P6** | 台账落盘参数原文与绝对路径，与它自己的自述不一致 | 重要（读数口径） | **已修（改自述）**：口径进代码与 `术语与口径.md`，行为有测试钉住 |
| **P7** | `served_checkers` 同名两义 | 次要（读数口径） | **已修**：`validators[].served_checkers` → `declared_checkers`，协议版本显式递增 |
| **P8** | 写类越界的拒绝理由没有「可用的替代」 | 次要 | **已修**：`repo_relative_path` / `normalize_repo_path` 补上与读类同口径的替代句 |
| **P9** | **本轮新显现**：Phase-4 阻断理由进审计时未脱敏（绝对路径落进 AuditLedger 的那份 JSONL） | 重要（AGENTS 第 16 条） | **已修**：审计副本改用 `enforcement.audit.redact_text` |

### 1.2 写域划分（四个子会话并行，互不重叠）

| 子会话 | 写域 | 任务 |
| --- | --- | --- |
| **hook-audit** | `src/adapters/dsh/{hooks,pre_evidence}.py`、`src/adapters/dsh/README.md` + dsh 侧测试 | P1 / P3（收尾轮追加 `language_coverage` passthrough 与 §8.2 理由字段口径） |
| **evidence-protocol** | `src/validators/{pipeline,registry,models,cli}.py`、`src/policy/evidence.py`、`validation/validators.yaml` + 验证器侧测试 | P2 / P7 |
| **cli-completeness** | `src/policy/check.py`、`validation/test-layout.yaml` + CLI 侧与契约测试 | P4 / P5 |
| **ledger-paths** | `src/enforcement/{ledger,action}.py`、`src/policy/{context,models}.py`、`术语与口径.md` + 相关测试 | P6 / P8（并独立复现了 P9） |
| **Lead** | 本文档、索引与 `AGENTS.md`（第 46–50 条）、P9 的修复与探针、`.tmp/round-08/` 的复核仪器 | 口径冻结、独立复核、全量门禁 |

写域重叠是**约定不是锁**：接口（`PipelineReport.language_coverage` 的形状、
P1 的 `violations` 形状、P5 的 `check_volume` 字段）由 Lead 在开工前冻结；
跨域的几行（`tests/contract/test_dsh_adapter.py`、`tests/integration/test_validator_cli.py`、
`tests/integration/test_api_http.py` 的版本号钉子、tech-detail `05-代码验证器/cells.py` 的断言）
由 Lead 逐条授权，避免两个子会话各改一半。

### 1.3 三处策略决定（与理由、代价）

**① P2：哪些语言按设计不取证。** 平台在 `validation/validators.yaml` 里显式声明
`uncovered_languages`（本轮只有 `text`，理由是平台没有 text/markdown 的 rule pack）。
命中时**不是静默放行**：流水线产出显式判定
`language_coverage = {language, status: not_covered_by_design, reason, declared_in}`，
`served_checkers` 保持为空，并用同一个形状把 `covered_by_rule_pack` / `language_unknown` 也写出来。
**没被声明的语言仍然失败关闭**；声明了不取证但本次有规则需要某个 checker 的证据，也仍然阻断。
代价写在明处：`.md` 这类目标从此**可以写**，而平台对它的内容**什么都没查**——
本轮实测这条记录长这样：`decision=allow` / `effective_rule_count=0` / `skipped_rule_count=43` /
`served_checkers=[]` / `language_coverage.status=not_covered_by_design`。
**"allow"与"查过没问题"必须能被分开读**，这条记录就是那个区分本身。

**② P5：缺关键维度时失败关闭落在哪一类调用上。** 只落在**自相矛盾的调用**上：
给了 `--changed`（声明了"这是一次变更"）却没给 `--operation` → 退出码 2，并告诉调用方补哪个参数。
**没有**把"完全没声明 `--operation`"做成配置错误：仓库 README 与 60+ 处文档里的
`python -m policy.check <file> --layer X` 是必须保持可执行的既有命令，强行要求它会把文档里的 allow 例子
变成 block（`--operation create/edit` 会激活 TESTING-001，而它缺 `--changed` 时本来就阻断）。
那一类调用改走**显式可见性**：`check_volume.complete=false` + `missing_dimensions` + 文本输出的
`INCOMPLETE:` 行。实测缺 `--operation` 时 `complete=false`、`missing_dimensions=["operation"]`、
`blocking_capable_skipped=3`、参与规则 40/43、served 2 类——这些数字在修复前**一个字都读不到**。

**③ P6：台账改自述而不是改行为。** `request.workspace` 参与 `ActionRequest.action_hash`，
参数原文是 PostToolUse 重建请求的唯一输入（`_restore_request`）；扣掉取值会让事后核对永远只能判
"证据不足"，等于把 G2（事前事后成对 + `post_validated`）打掉。所以**当前行为是对的、错的是自述**：
改的是 `ledger.py` / `action.py` 的措辞与 `术语与口径.md` 的一行，并加测试把"决定"钉住
（谁把行为改成"扣掉所有取值"，那条测试会红）。

### 1.4 明确不做的部分

| 不做的事 | 理由 |
| --- | --- |
| 把「同一批次里已经提议过的文件」纳入取证树（P3 的另一个方向） | Hook 每次调用只见一个文件，批次状态要跨进程持久化；本轮先把"这棵树是什么"写清楚，批次语义属于一次显式设计 |
| 让 `policy.check` 在完全没有 `--operation` 时退出码非 0 | 见 §1.3 ②：会破坏 60+ 处必须保持可执行的既有命令 |
| 重新开一次真实受治理会话 | 本轮判据全部是**确定性**的（生产 Hook CLI + 真验证器流水线 + 真台账复算 + 07 轮遗留探针）：不需要模型参与就能证红与证绿。**这正是边界**（§6） |
| 台账内容的安全影响分析 | 07 轮也没做；本轮只把口径与边界写清楚 |
| 桌面 GUI 通道接线（G1 残余）、N25/N26（宿主事实）、N27 残留语义、N2 配置口径合并 | 与 12 号文档同处置：各自需要一次显式决定或属于宿主环境，不在修复轮顺带做 |

## 2. 方法与判据

- **每条改动配一条「修复前会红」的检查**：先写测试跑红、再实现跑绿，两次输出留在
  `.tmp/round-08/red-green/`（文件名带子会话代号与条目号；文件名的前缀约定是"只用自己前缀"，
  见 §6.1）。
- **确定性优先**：能不用模型证明的就不用模型证明。P1/P2/P3/P8/P9 用**生产 Hook CLI** 喂 dsh 真实载荷；
  P4/P5/P7 用真验证器流水线 / 真 `policy.check`；P6 用 07 轮的真实台账逐项复算。
- **判据沿用 N19 的硬不变量**：「没拦到」不等于「拦住了」；再加本轮的一条：
  **「字段存在」不等于「字段可读」**——每个新字段都要能在真实产物上被读出来。
- **独立复核**：Lead 用与子会话**不同的入口**复核——07 轮遗留的确定性仪器
  （`lead_smoke.py` / `probe_matrix.py`，写于缺陷发现之前）跑在 `.tmp/gf-verify/` 的项目副本上，
  外加 Lead 自己写的四条探针（P2 / P4+P5 / P6 / P9），最后串行跑一次全量门禁（§7）。

## 3. 逐条处置

### 3.1 P1 · 账本要说得出「哪几条规则报了违规」

**局面（07 轮读数，本轮按内容重算）**：`.tmp/round-08/baseline/governance-full/project/.policy/audit.jsonl`
共 164 条记录，其中带 `decision` 的 34 条（allow 22 / allow_with_warnings 9 / block 3）；
**`violations` 键出现 0 次**；block 记录的 `matched_rules` 是 43 条**全集**。

**改了什么**（`src/adapters/dsh/hooks.py`，hook-audit）：算出 decision 的记录新增
`violations`（canonical rule_id + severity + message + evidence，排序稳定、字符串递归脱敏）、
`violations_by_severity`（与 M3 的 `*_by_severity` 共用一份计数实现）、`violations_note`
（写死"真的报了违规 / 参与过判定 / 没有做出判定"三者的区别）；
**没有算出 decision 的记录一个键都不加**（`context_error` / `evidence_unavailable` /
`event_replay` / `enforcement_*` …）——"这次没做判定"与"判定了、没违规"必须可区分。

**红→绿**：`tests/unit/test_hook_violation_visibility.py` 13 条（含生产 Hook CLI 的三类判定）
13 failed → 13 passed；`A-hook-visibility-{red,green}.txt`。

**Lead 独立复核**（用 07 轮**冻结**的 `lead_smoke.py`，它当时就写了 `record.get("violations")`）：

| 臂 | 07 轮基线读数 | 本轮修复后 |
| --- | --- | --- |
| clean（写回逐字相同内容） | allow / `violations=[]` | allow / `violations=[]`（不变） |
| violating（入口层直连仓储 + 五类违规） | block / **`violations=[]`** | block / **6 条**：`ARCH-001@1`、`DOC-001@1`、`SEC-007@2`、`STYLE-001@1`、`STYLE-006@1`、`TESTING-001@1` |
| edit-nonunique（取证证明不了） | exit 2 / evidence_unavailable | 同左（不变） |
| 探针自身 `ok` | false（当时失败在"验证器没跑起来"） | **true（13/13）** |

A1 矩阵的 `pe-on-multiviolation` 臂也把 5 条违规连同 severity / message / 证据摘要读了出来。

**边界**：`violations` 的**条数**没有上限（单条字符串走脱敏截断，条数与既有 `matched_rules` 口径一致）；
证据子对象沿用核心模型 `policy.models.Evidence` 的字段（`kind/subject/value/file/line/detail`，
**没有 column**）——为凑字段名去改核心模型会连带动决策协议快照，不属于本轮。

### 3.2 P2 · 打开取证之后非 Python 目标结构性不可写

**局面（07 §3.4 的现场）**：`.md` 写入 → `RegistryError: 上下文声明的语言 text 没有任何 rule pack` →
`evidence_unavailable` → 退出码 2。基线读数存于
`.tmp/round-08/baseline/governance-full/evidence/lead-md-block.json`。

**改了什么**（evidence-protocol + hook-audit 收尾）：`validation/validators.yaml` 新增
`uncovered_languages`（每项必须带可评审的 `reason`；未知字段 / 重复语言 / 空理由 /
与既有 rule pack 自相矛盾一律加载期报错）；`PipelineReport.language_coverage` 成为必填字段，
`status ∈ {covered_by_rule_pack, not_covered_by_design, language_unknown}`；
`needed` 非空而语言按声明不取证时仍然是 Blocker；语言既无 rule pack 又未被声明 → **保持 RegistryError**；
`pre_evidence` 摘要把 `language_coverage` 原样带进审计。

**Lead 独立复核**（自己写的探针，载荷形状与 07 轮 `probe_md_block.py` 一致，跑生产 Hook CLI）：

| | 07 轮基线 | 本轮修复后 |
| --- | --- | --- |
| Hook 退出码 | 2 | **0** |
| decision | （没有判定） | **allow** |
| reason_code | `evidence_unavailable` | `allow` |
| 取证状态 | unavailable（RegistryError） | **collected** |
| `language_coverage` | （不存在） | `{language: text, status: not_covered_by_design, declared_in: validation/validators.yaml, reason: …}` |
| served / checks | — | `[]` / `[]` |
| 参与 / 跳过规则 | — | **0 / 43** |
| 目标文件 | 未变 | 未变（探针只跑 PreToolUse） |

**边界**：这就是 §1.3 ① 的代价——**allow 不等于"查过没问题"**；能读出差别的三个数
（`effective_rule_count=0`、`skipped_rule_count=43`、`language_coverage.status`）都在同一条记录里。

### 3.3 P3 · 影子树的形状会改变工具结论

**局面**：先写测试 → 兄弟模块还不在树里 → Ruff 的 isort 判成第三方 → `I001` → STYLE-018(warning)
→ 4 次写入成 `allow_with_warnings`（交付物本身干净）。

**改了什么**（hook-audit）：`pre_evidence` 摘要新增 `tree` 段——`scope`（`current_disk_tree_plus_proposal`）、
`target_existed_before`（按**磁盘树**判，不按副本，否则 exclude 会把"新建"读错）、
`tree_digest`（"仓库相对路径 + 文件 sha256"排序后的摘要，取样时刻是**写提议之后、跑验证器之前**，
否则验证器的副产物会让同一份输入得到两个值）、适用范围 `note`；
以及"可能漏、不误报"的 `tree_gaps`（用 `validation/project.yaml` 的 `python_roots` 解析提议内容的 import，
**只在**顶层包已存在于影子树、而模块文件找不到时报出）。

**红→绿**：单测 6 failed → 6 passed；集成 3 failed → 11 passed；探针在 07 轮受控项目副本上给出：

| 臂 | 判定 | violations | tree |
| --- | --- | --- | --- |
| 兄弟模块 `src/invsvc/returns_service.py` **不存在** | `allow_with_warnings` | `STYLE-018@1` | `tree_digest=sha256:e9574d06…`、`tree_gaps=["invsvc.returns_service"]` |
| **同一份载荷、同一份配置**，只把兄弟模块放回树里 | `allow` | `[]` | `tree_digest=sha256:4fb62ff5…`（不同）、`tree_gaps=[]` |

**边界**：`tree_gaps` 只覆盖"绝对 import 的顶层包已存在、模块找不到"这一类（可能漏、不误报）；
**批次语义没有做**（§1.4）。

### 3.4 P4 · 同一个测试文件，两条路径两个结论

**局面**：`tests/test_shipment_controller.py` 在 Hook 路径 `layer=test` → allow；
在 `python -m policy.check`（不给 `--layer`）按文件名猜成 `controller` → block（2 条 ARCH-001）。

**改了什么**（cli-completeness）：`policy.check` 缺 `--layer` 时按
`declared → platform_test_layout → filename_guess` 定层，并把 `layer_source` 写进 `--json` 与文本输出；
平台"哪些路径算测试"经 `validators.registry.load_test_layout` 读（`TestLayout.is_test`），
不另写一个 YAML 解析器；`validators.cli` 缺 `--layer` 继续拒绝推断（未改，另加守卫用例）；
契约检查新增一条：平台每条 `test_patterns` 的见证路径必须落在示例 Adapter 配置的 `test_paths` 覆盖内、
且解析到声明的 `test_layer`（两条变异用例证明它会红）。

**Lead 独立复核**（真 `policy.check`，目标 = 07 轮受控项目副本里的同一个文件）：

| 调用 | layer / 来源 | 判定 / 退出码 | ARCH-001 |
| --- | --- | --- | --- |
| 不给 `--layer`（**修复前**） | `controller` / 文件名推断 | **block / 1** | 命中 2 条 |
| 不给 `--layer`（**修复后**） | **`test`** / `platform_test_layout` | **allow / 0** | 不在 violations 里 |
| 显式 `--layer controller` | `controller` / `declared` | block / 1 | 命中 2 条（范围校验没被放宽） |
| Hook 路径同一份内容（A1 臂 `layer-test-controller`） | `test`（`tests/**/*.py`） | allow | —— |

**两条路径同向**这件事因此有两个独立证据：真 CLI 与 07 轮的 Hook 矩阵。

### 3.5 P5 · 缺 `operation` 时 CLI 只是「多跳过」

**改了什么**（cli-completeness）：`--json` 顶层与文本新增 `check_volume`
（`rule_count` / `effective_rule_count` / `skipped_rule_count` / `skipped_by_reason` 三桶 /
`skipped_by_severity` / `blocking_capable_skipped` / `served_checkers` / `missing_dimensions` /
`complete` / `note`）；分类**不解析 reasons 文本**，而是拿 `rule.scope` 与 context 的结构化比对算；
缺维度时文本输出一行 `INCOMPLETE:`；`--changed` 却没有 `--operation` → 退出码 2。

**Lead 独立复核**（真 CLI）：

| 调用 | `complete` | `missing_dimensions` | 参与规则 | served | 退出码 |
| --- | --- | --- | --- | --- | --- |
| 不给 `--operation`（修复前：无这些字段） | **false** | `["operation"]` | 40/43 | 2 类 | 0 |
| 不给 `--operation` 的文本输出 | —— | —— | —— | —— | 0，且打印 `INCOMPLETE: …（缺 operation）；补 --operation 后重跑——skipped ≠ passed…` |
| `--changed` 但无 `--operation` | —— | —— | —— | —— | **2**（`config error：配置自相矛盾…`） |
| `--changed` + `--operation edit` | **true** | `[]` | 42/43 | 4 类 | 0 |

07 轮 A3 量到的"参与规则 42→40、served 4→2"在这一版里变成了**可读的三个字段**。

### 3.6 P6 · 台账落盘了参数原文与绝对路径

**复算（只读 07 轮真实台账，`.tmp/round-08/baseline/…/audit.enforcement-ledger.jsonl`）**：
78 条记录；`pre_state` 16 条**全部**带绝对 `request.workspace`；36 个参数带**非空原文**；
原文合计 **21022 字节 / 18586 字符**；`has_secret_params` / `values_withheld` 16 条全为 `false`。

**改了什么**（ledger-paths，**只改自述**）：`ledger.py` 模块 docstring 逐项写清"存什么 / 扣什么 / 为什么 / 边界"，
`action.py::redacted_request_payload` 的措辞同步，`docs/project/architecture/术语与口径.md` 新增一条口径
（含"这不是 AGENTS 第 16 条"的边界说明）；新增 `tests/unit/test_ledger_disclosure.py`：
3 条自述检查（修复前会红）+ 3 条行为锁（**刻意修前也绿**：谁把行为改成"扣掉所有取值"就会红）。

**Lead 独立复核**（跑一次生产 Hook，读**新写下**的 `pre_state`）：
`workspace=C:/Users/…/.tmp/gf-verify/project`（仍是绝对路径）、`content` 参数 `has_value=true`
（chars 1147 / digest 同在）、`values_withheld=false`、`action_hash` 照常算出——
**行为一个字没变**，变的只是自述。

**边界**：本轮**没有**做台账内容的安全影响分析；台账里的绝对 `workspace` 是刻意行为（AGENTS 第 50 条），
与 P9 的审计记录流是**两份不同产物**。

### 3.7 P7 · `served_checkers` 同名两义

**改了什么**（evidence-protocol）：`ValidatorRecord` 的"声明负责"字段改名为 `declared_checkers`
（模型字段 + payload 键 + 两处构造 + 全部消费者），顶层 `served_checkers` 语义不变（真的服务过）；
按协议自己的规则显式递增 `EVIDENCE_SCHEMA_VERSION` 与 `PIPELINE_SCHEMA_VERSION`（1.0 → 1.1），
`src/validators/__init__.py` 改成从 `.pipeline` 单一取值（删掉第二份会漂移的字面量），
`validation/validators.yaml` 的 `version 1→2`、`schema_id …/1→…/2`。

**验收**：一个 `crashed`/`not_selected` 的验证器——它的 `declared_checkers` 非空、而顶层
`served_checkers` 不含它声明的 checker（这正是"同名两义"的可执行反例）；全仓消费点核过一遍，
`python -m policy_api.cli openapi --check` 与快照一致（无需重新生成）；
仓库里没有被测试解析的旧版本号证据 fixture。

### 3.8 P8 · 写类越界的拒绝理由没有「可用的替代」

**改了什么**（ledger-paths）：`src/policy/models.py` 新增共享句常量，`normalize_repo_path` 的
`..` 分支与 `context.py::repo_relative_path` 的绝对路径越界分支都引用它；
既有范围 / 原值部分一字未动，错误码与退出码不变。

**Lead 独立复核**（07 轮 A1 矩阵复跑，两臂都是修复前那两条偏差的同形载荷）：
`block-write-outside` 与 `block-write-parent-escape` 的 `detail` 现在都以
`可用的替代：把目标写成受控范围以内的仓库相对路径（例如 src/shop/order_service.py；范围根记为 .）…` 结尾，
退出码与 reason_code 不变。Phase 4 那一层（`path_out_of_scope`）的理由在 `enforcement_detail` 里
同样带上这句（包装层没有吞掉它）。

### 3.9 P9 · Phase-4 阻断理由进审计时未脱敏（本轮新显现）

**怎么发现的**：hook-audit 在写 §8.2（"阻断理由落在哪一栏"）时观察到 `enforcement_detail` 没走脱敏；
ledger-paths 用生产 Hook CLI 独立复现；Lead 用最小载荷坐实。

**现象**：`pwsh` 的工作目录是到 Phase 4 才做范围判定的（`path_scope: workspace`）。
`workdir=C:/Windows/Temp` → `path_out_of_scope`（exit 2），**stderr 干净**（`<repo>` / `<abs>`），
而审计记录 `audit.jsonl` 的 `enforcement_detail` 里躺着**两处绝对路径**：
受控工作区自己的（`路径不在仓库 <anchor> 之内` 这句文案里带的）与调用方那个 `C:/Windows/Temp`。
AGENTS 第 16 条要求审计链里的绝对路径一律脱敏——**同一条理由，两个产物两个口径**。
（Phase 4 自己的 `FileAuditSink` 是递归脱敏的，所以摘要链干净；缺口在 Hook 自己那份记录流。）

**改了什么**（Lead）：`_enforcement_block` 写审计时改用 **审计链自己的**脱敏实现
`enforcement.audit.redact_text(detail, workspace=project_root)`，而不是面向模型的 `sanitize`
（后者为模型可读性做的 4000 字截断不该改变审计明细的形状）；两份产物从此是同一个实现。

**红→绿**：`tests/unit/test_phase4_reason_redaction.py`（新建，走生产入口 `run_hook` + 真注册表）
修复前 **1 failed**（`审计里的 Phase 4 理由带了绝对路径：['C:\\Users\\…\\demo-shop', 'C:/Windows/Temp']`）
→ 修复后 **1 passed**；证据 `P9-enforcement-detail-{red,green}.txt`。
绝对路径的识别用**带边界**的形状（与 `enforcement.audit._ABS_PATH_RE` 同口径）——
第一版正则把一个孤立的 `/` 也算成绝对路径，把"例如 src/shop/order_service.py"判成了泄漏，
那正是本仓库反复踩过的"仪器假阳"，改的是仪器不是被测对象。

**两条必须一起读的边界**：①**不是 P8 引入的**——绝对路径分支修前就带 `{anchor}` / `{raw!r}`；
②**07 轮的结论不被推翻**：对 baseline 的 164 条审计记录逐字节复核，**0 处绝对路径、0 处凭据**，
30 条矩阵臂里也只有这条**故意构造**的 `pwsh` 形状能触发——**缺口可达，但在 07 轮的证据里未被触发**。

## 4. 与既有条目的关系

| 既有条目 | 07 轮之前 | 本轮实测 |
| --- | --- | --- |
| **P4 → M1 / G7** | FIXED（只在 dsh 路径 + Hook 三臂） | **两条路径闭合**：真 CLI 与 Hook 路径对同一个测试文件都判 `layer=test`、都 allow |
| **P1 → M3** | 严重级别进账本（"有多少条会拦人"可读） | **再进一步**：报违规的**具体规则**也可读；M3 的口径没被削弱 |
| **P2 → G3** | 打开取证后有效规则 42–43/43 | **代价显式化**：不受验证器覆盖的语言不再"结构性不可写"，而是"按声明不取证 + 审计可读" |
| **P5 → AGENTS 第 43 条** | 规则集按级别分开说 | **"这次查了多少"也写出来了**：`check_volume` |
| **P6 → AGENTS 第 16 / 50 条** | 摘要链脱敏、台账刻意保留 workspace | **两者都成立**，且自述与行为一致 |
| **P9 → AGENTS 第 16 条** | 审计链脱敏 | **Hook 记录流也脱敏**（P9 是这条约束在 Phase-4 理由栏上的落地） |
| **N19**（拦住 vs 没人尝试） | 判据 | 未变：本轮所有"拦住"的结论都带审计字段与退出码 |

## 5. 本轮新注册的约束（`AGENTS.md` 第 46–50 条）

| 条 | 内容 | 来自 |
| --- | --- | --- |
| 46 | 账本要说得出「哪几条规则报了违规」；没有算出 decision 的记录不许伪造这份清单 | P1 |
| 47 | 语言覆盖是数据（`uncovered_languages` 是唯一声明处），命中产出显式判定而不是静默放行 | P2 |
| 48 | 证据的含义取决于取证时那棵树的形状；摘要必须写清"这条证据属于哪棵树" | P3 |
| 49 | 测试路径与"查了多少"都只有一份声明；缺维度的失败关闭只落在自相矛盾的调用上 | P4 / P5 |
| 50 | 口径诚实：台账存什么与自述一致、同名两义一律改名、拒绝理由要给"怎么改就能过" | P6 / P7 / P8 |

## 6. 事故、仪器问题与诚实边界

### 6.1 三件必须与结论一起读的事故

1. **一次越界写**：hook-audit 把自己 UTF-16LE 的红/绿记录转 UTF-8 时，脚本误扫了整个
   `.tmp/round-08/red-green/`，把**不属于它的**几个 `.txt` 也一并重编码（内容一字未改；
   副作用是 `read` 工具从"判成 binary 拒绝"变成可读）。它主动通报了三个受影响的子会话，
   并把结论写进自己的 REPORT。此后各子会话统一"只用自己前缀"。
2. **red 证据丢失与显式变异重放**：evidence-protocol 的 5 个 `*-red.txt` 与 ledger-paths 的
   `P6-docstring-red.txt` 在并发期间从共享目录消失（原因无法归因，hook-audit 给出了"不是它的脚本所为"
   的三条机械论证）。两者都用 AGENTS 第 45 条的**显式变异**办法在隔离副本里重放：
   把工作树子集复制出来、只反向应用本轮的编辑、再跑同一批测试，失败集合与首次 red 逐条一致
   （副本自检 `PIPELINE=1.0 / EVIDENCE=1.0 / registry.version=1`）。
   现存的 `*-red.txt` 因此是**重放得到的红**，这一点在各自的 REPORT/REPLAY 里写明。
3. **预置命令本身会假绿**：任务书里给的 `-p no:cacheprovider` 在本仓库**跑不出任何用例**——
   `pytest.ini` 的 `cache_dir` 与 `--strict-config` 冲突，pytest 以退出码 4 结束（`no tests ran`）。
   三个子会话都发现了它并改用不带该开关的等价命令；**如果没人核这一步，"全绿"会是一句假话**。
   最终门禁不带该开关。

4. **新测试里的合成凭据让密钥扫描按设计报红**：P1 的用例要证明"violations 的 message 也过脱敏"，
   因此**故意**放了一个 `sk-…` 合成令牌；第一轮全量门禁因此 **31/32**（`Secret scan gate` 退出码 1）。
   按工具自己的约定在同一行的行内标记 `secret-scan: allow` 并写明理由后归零——
   这与仓库里既有 5 处合成值的写法一致，标记只加在合成值上（不是为了让门禁变绿而放宽扫描）。

并行期间还出现过两次**并发假红**（`test_temp_directories_are_cleaned_up` 因别的子会话同跑流水线红一次；
`src/policy/check.py` 被改到一半时 5 条 CLI 测试短暂红），单跑即恢复——它们不是被测对象的缺陷。

### 6.2 诚实边界

1. **本轮没有再开真实受治理会话**：所有判据都是确定性的（生产 Hook CLI / 真流水线 / 真台账）。
   "在真实会话里会发生什么"**没有被本轮测量**，07 轮的会话读数仍然是那一次的读数。
2. **两条路径不能相加**：P4 让同一个文件在两条路径上同向，但两条路径各自仍有自己的边界
   （Hook 有 Phase 4 门禁，CLI 没有）。
3. **P2 的代价**：`.md` 现在可以写，平台对它什么都没查——审计能读出这一点，但**读的人必须去读**。
4. **P6 没有做安全影响分析**：台账里出现参数原文与绝对 `workspace` 是**已知事实**，
   本轮只把口径与边界写清楚。
5. **A1 矩阵的一条期望被显式更新**：`pe-on-multiviolation · has_violations_field eq False`
   这条期望在 07 轮是"如实记录缺口"，修复后它本身过时了——Lead 按探针自己的
   `INSTRUMENT_CALIBRATIONS` 约定补了一条校准记录（"被测对象变了"），并把两处 gaps 文本
   改成"这条检查红着才成立"。改的是**探针的期望**，不是被测对象。
6. **P9 的触发面**：目前只有"Phase 4 独立做范围判定"的参数（本轮实测 `pwsh.workdir`）能触发；
   07 轮的 30 条臂与 164 条审计记录里都没有这个形状。**可达 ≠ 已发生**。
7. **手册产物是生成的**：tech-detail `05-代码验证器` 的 `.py`/`.ipynb` 由 `cells.py` 重新生成，
   学习手册由 `tools/build_learning_notebook.py` 重新生成（本轮改了它里面的顶层键断言与说明文字）。

## 7. 复现

全部命令在仓库根执行，解释器 `python` = `C:\Users\ZNM\miniconda3\python.exe`，
跑仓库模块前设 `$env:PYTHONPATH='src'`。

    # 0) 07 轮证据的快照副本（只读基线）+ Lead 的复核工作区（git 忽略，可随时重建）
    #    .tmp/round-08/baseline/governance-full/   ← 07 轮原始证据的副本
    #    .tmp/gf-verify/                           ← 在同一份副本上跑"修复后"的仪器

    # 1) 本轮新增/改动的定向测试
    python -m pytest tests/unit/test_hook_violation_visibility.py tests/unit/test_dsh_pre_evidence.py \
      tests/integration/test_dsh_pre_evidence_hook.py tests/unit/test_validator_language_coverage.py \
      tests/integration/test_validator_pipeline.py tests/unit/test_check_volume.py \
      tests/integration/test_cli.py tests/unit/test_ledger_disclosure.py \
      tests/unit/test_rejection_alternatives.py tests/unit/test_phase4_reason_redaction.py -q

    # 2) Lead 的独立复核（四支探针 + 07 轮遗留的两件仪器）
    python .tmp/round-08/verify/lead_verify_p2.py            # P2：README.md → allow + language_coverage
    python .tmp/round-08/verify/lead_verify_p4_p5.py         # P4/P5：layer_source / check_volume / 退出码
    python .tmp/round-08/verify/lead_verify_p6.py            # P6：新写的 pre_state 行为未变
    python .tmp/round-08/verify/lead_probe_enforcement_detail2.py   # P9：Phase-4 理由脱敏
    python .tmp/gf-verify/harness/lead_smoke.py --json .tmp/round-08/verify/lead-smoke-after.json
    python .tmp/gf-verify/harness/probe_matrix.py \
      --json .tmp/round-08/verify/matrix-final2.json --report .tmp/round-08/verify/matrix-final2-REPORT.md

    # 3) 手册产物（改了内容源之后必须重新生成）
    python docs/project/architecture/tech-detail/build_notebooks.py --only 05
    python tools/build_learning_notebook.py
    python tools/check_notebook.py docs/project/learning/*/walkthrough.ipynb

    # 4) 全量门禁（**串行**：同一工作树同时只允许一个 ci_local）
    python tools/ci_local.py --full --timings

产物（`.tmp/` 内，构建产物不提交）：

| 路径 | 内容 |
| --- | --- |
| `.tmp/round-08/red-green/` | 每个条目的红→绿输出（前缀 `A-`…`P9-` 各归其主） |
| `.tmp/round-08/<子会话>/` | 四个子会话的 REPORT、探针、复算脚本与隔离重放体 |
| `.tmp/round-08/baseline/` | 07 轮证据的快照副本（只读参照） |
| `.tmp/round-08/verify/` | Lead 的复核探针与读数（P2/P4/P5/P6/P9、矩阵前后两次） |
| `.tmp/gf-verify/` | Lead 的复核工作区（07 轮仪器的修复后运行点） |

### 6.3 本机全量门禁（最终树）

    python tools/ci_local.py --full --timings

**结果：32 步全部通过（rc=0），耗时 8 分 16 秒**；主测试批 **1718 passed / 1 skipped**
（跳过的那一条是本机不允许创建符号链接，与 07 轮同一原因）；新增的 `check_volume` 也出现在门禁步骤的
读数里（`rule_count=43 / effective=41 / skipped=2 / blocking_capable_skipped=2 / complete=False`）。
耗时明细在 `.tmp/ci-local-timings.json`。

**门禁结论的适用边界（N28）**：它只对跑的那一刻的工作树成立。本轮在门禁之后**没有再改任何代码**，
只把这几次读数补写进本文件（第一轮 31/32 的失败与修复、以及这一轮的 32/32）。

## 8. 建议的下一轮

| # | 事项 | 为什么现在不做 |
| --- | --- | --- |
| 1 | 把"同一批次已提议过的文件"纳入取证树（P3 的另一半） | 需要设计批次在 Hook 路径上的表示（每次调用只见一个文件），属一次显式设计 |
| 2 | `violations` 条数上限、证据里补 `column` | 前者是新口径、后者是核心模型 + 决策协议快照的变更，各自单独一轮 |
| 3 | 台账内容的安全影响分析（P6 只对齐了口径） | 要有一次显式的威胁建模，不该顺手做 |
| 4 | 桌面 GUI 通道接线与否（G1 残余） | 要重启界面，且日常命令行会全部变成需要审批——使用者决定 |
| 5 | 在真实受治理会话里复核本轮结论（P1–P9 的读数都来自确定性仪器） | 需要凭据与不受限 shell，且同一台机器同一时刻只能跑一个会话；本轮**没有**替使用者开这一轮 |

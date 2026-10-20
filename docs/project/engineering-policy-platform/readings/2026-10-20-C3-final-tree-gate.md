# 2026-10-20 C3 最终树门禁 v1：整树判定 + 规则集哈希钉住（读数）

> **任务**：共享任务 task-2「C3 最终树门禁 v1」。依据 05 §4 C3 行与「C3 说明」、06 §7.7、
> AGENTS 第 3/4/19/55 条与核心层约束。
> **交付**：tools/final_tree_gate.py、tests/unit/test_final_tree_gate.py、
> tests/fixtures/final_tree_gate/**、本读数。
> **只新增文件**：未改 src/**、registry/**、policies/**、现有 tools、04/05/06/AGENTS/tools/README；
> 未提交、未跑 tools/ci_local.py、未删 .tmp 下任何目录。
> **强度声明**：本文是读数，不是计划。命令与退出码都是本轮实测；未核实的标「未核实」。

## 0 一句话

门禁把「判定对象」从单次动作换成最终树：对树内每个受规则覆盖的文件，用与
python -m policy.check **同一份**上下文构造、**同一条**真实验证器流水线取证，交给
**唯一**判定入口 policy.engine.evaluate，再把 violations 汇总成 0 / 1 / 2 的门禁退出码；
--pin / --check 用 RuleSet.identity 把规则集钉住。

## 1 v1 的范围（先说没有什么）

**v1 不含「危险动作前置阻断」**：删除 / 执行 / 控制面写的前置阻断不在本版本内，留待
B1/B3 之后单独一轮裁定与实现。本工具是**只读**的：不写审计、不写台账、不改任何
allow / block、不启动 dsh、不做任何写类动作。因此它**只保证「结束/提交时干净」**，
不保证「中间态不落盘」——这条是 05 §4 C3 说明写明的接受边界。

v1 只做两件事：

1. **整树判定**：枚举 + 逐文件真实验证器取证 + 汇总 violations / 按 severity 计数 / 树摘要；
2. **规则集哈希钉住**：--pin 写钉住文件，--check 比对，漂移即非 0。

## 2 CLI 形状

    python tools/final_tree_gate.py --workspace <树根> --config <adapter 配置>
        [--changed FILE[,FILE...] | --all]
        [--rules DIR]... [--config-root DIR] [--operation {read,create,edit,delete,execute}]
        [--validators A,B]
        [--pin FILE | --check FILE] [--json]

- --workspace：被判定树的根；目标文件都在它之内；
- --config：adapter 配置（layers / languages / 默认 rules 的来源，与 Hook 路径**同一份实现**：
  adapters.dsh.adapter.AdapterConfig.layer_resolution 与 language_for）；
- --changed：显式目标集（可重复或逗号分隔，工作区相对路径）；不给时按 --all 枚举；
- --rules：覆盖 adapter 配置的规则目录；--config-root：validation/ 所在目录（默认仓库根，
  与 policy.check 同源）；--operation：受控枚举，**默认 edit**（显式口径：最终树是写类动作的
  产物，门禁把每个目标当作「一次 edit 到它自己」，不从树推断）；
- --json：机器可读载荷；--pin 只写钉住文件（写完退 0，不枚举树）；--check 叠加在本次判定上。

## 3 设计取舍

1. **不重写判定、不重写取证**：上下文用 policy.check.build_context_args，证据用
   policy.check.collect_evidence（内部即 validators.pipeline.run_pipeline，真调用 Ruff / pytest），
   判定只调用 policy.engine.evaluate。门禁自己只负责：枚举、逐文件循环、汇总、退出码、规则集钉住。
   这样 CLI 与门禁在「层怎么定、路径怎么规范化、--changed 的自相矛盾边界」上不可能漂移。
2. **分层/作用域口径来自 adapter 配置，但允许既定的回退**：命中 layers 时
   layer_source=declared（layer_origin=adapter_config；走 default_layer 时 origin 记为
   adapter_config_default）；命中不了时退回 policy.check.resolve_layer 的既定顺序
   （平台 validation/test-layout.yaml -> 文件名推断），并把 layer_origin / layer_source 写进
   每个文件的读数。**猜出来的层与声明的层必须能分开读**；v1 不因此让门禁失败
   （那会新增一条 policy.check 没有的失败语义）。
3. **树的摘要是既有实现**：provenance.worktree.workspace_tree_digest（排除项
   DEFAULT_EXCLUDES），不另写一套遍历/哈希。
4. **确定性优先于方便**：每个文件用 ftg-<sha256(相对路径)[:16]> 作为确定性 request_id；
   载荷不带时戳、带 run 标识、绝对路径或耗时。reading_context 用
   provenance.reading_context.build(..., include_run=False)，host.sandbox 为 unknown
   （不探测沙箱；**不是**「没有沙箱」，也不写 not_applicable 冒充）。
5. **脱敏只复用既有两份实现**：provenance.reading_context.fold_absolute_paths +
   enforcement.audit.redact_text（与 tools/decision_diff.py 同口径）。
6. **两个版本轴各自独立**：门禁载荷 FINAL_TREE_GATE_SCHEMA_VERSION = "1.0"（首次建轴）；
   钉住文件 PIN_SCHEMA_VERSION = "1.0"（它比单次读数长寿，各走各的轴，AGENTS 第 55 条）。
7. **用例使用夹具规则集**（tests/fixtures/final_tree_gate/rules/：GATE-001 style_lint/Ruff E501，
   error 级）：仓库 43 条规则在一棵夹具小树上会让 TESTING / ARCH / DOC 全部参与，用例就变成
   在测规则集而不是在测门禁。判定路径没有缩水——真 Ruff + 真 run_pipeline + 真 evaluate。
   另有一份 rules_alt/（同 id、不同 message）用来造「规则文件被改」，并与 rules/ 一起用来证明
   「加载顺序变了不是漂移」。

## 4 枚举与排除口径（写进读数，不让读者反推）

不给 --changed 时按 --all 枚举，规则是**数据驱动**的两层：

1. **路径排除**：provenance.worktree.DEFAULT_EXCLUDES——.git/**、.tmp/**、.venv/**、
   node_modules/**、**/__pycache__/**、**/*.pyc、**/*.pyo、.pytest_cache/**、
   .mypy_cache/**、.ruff_cache/**、**/*.egg-info/**。命中目录**不再走进去**
   （与树摘要的排除语义一致：排除是声明，不是过滤）。
2. **语言覆盖**：adapter 配置声明了语言、**且** validation/validators.yaml 有该语言的
   rule pack，才算「受规则覆盖」。排除分三类记数：language_undeclared（没声明语言）、
   language_not_covered_by_design（命中 uncovered_languages，按其声明的 reason）、
   language_without_rule_pack（既没 pack 也没声明）。

--json 的 workspace_scope.excluded 恒定给出 globs / directories / files / by_reason
（四类键恒定出现，0 也写）。--changed 是显式目标集：**不受**排除清单限制（显式指定的文件
必须被判定，不能被悄悄丢掉），但必须落在 --workspace 内、必须存在、adapter 配置必须为它
声明语言；否则退出码 2。

枚举结果为 0 个目标 → 退出码 2：**门禁没有可判定对象不许静默记成通过**。

## 5 退出码（照 tools/README.md 的「门禁退出码」表，失败关闭）

| 码 | 含义 |
| --- | --- |
| 0 | 所有文件都没有 **error / critical 级**违规（warning 只进清单；文件 decision 可能是 allow_with_warnings） |
| 1 | 有 error / critical 级违规，**或**规则集漂移（--check） |
| 2 | 无法完成判定：adapter 配置读不到 / 验证器配置读不到 / 规则集加载失败 / 验证器不可用 / 证据缺失 / 树摘要证明不了 / --changed 不合法 / 枚举为 0 |

两处必须明说的差异与细节：

- 与 policy.check 的退出码**口径不同**：policy.check 把 allow_with_warnings 记 1
  （Decision.ALLOW 才 0），本门禁按 C3 v1 交接的定义——**warning 不拦门禁**。同一个 decision
  在两处退出码不同是刻意的，不是实现漂移。
- 多类失败同时出现时优先级 2 > 1 > 0：只要有一个文件「证据缺失 / 验证器不可用」，
  即便同时存在真实违规、甚至引擎已经判 block，整次门禁仍按 **2** 收场，理由里同时写出
  两类事实（实测见 §8 第 4 条）。

## 6 规则集哈希口径

- 钉住对象是 RuleSet.identity（policy.models.RuleSet.identity）：对规则**模型序列化**后的
  字符串排序取 sha256，因此
  - **规则文件被改**（语义字段变了）⇒ identity 变 ⇒ --check 退出 1；
  - **规则集换了加载顺序** ⇒ identity 不变 ⇒ 不是漂移（这是既定口径：identity 与加载顺序
    无关，AGENTS 核心约束 5）。本工具**不**另造一个顺序敏感的哈希。
- 钉住文件形状（PIN_SCHEMA_VERSION = "1.0"）：

      {"schema_version": "1.0",
       "rule_set": {"count": N, "decision_schema_version": "...",
                    "identity": "sha256:...", "ids": ["ARCH-001@1", ...],
                    "sources": ["policies/...", ...]}}

  不含时戳/绝对路径；ids / sources 只为可读，判定只读 identity。
- 读不到 / 不是 JSON / schema_version 不认识 / 缺 identity ⇒ 退出码 2（不猜、不降级）。
- **已知边界**：identity 只覆盖规则内容，改规则文件里的纯注释 / 空白**不会**漂移；
  且它包含 source.path 等字段，改来源元数据也算漂移。

## 7 --json 载荷

顶层键（FINAL_TREE_GATE_SCHEMA_VERSION = "1.0"，加键/改语义必须显式递增）：

    schema_version / workspace_scope / rule_set / files / violations /
    violations_by_severity / counts / coverage / layer_sources / gate / reading_context

- files[]：file / layer / layer_source / layer_origin / language / decision /
  status（ok | evidence_unavailable）/ violations / pending_findings（独立通道，空也写出）/
  check_volume（complete / missing_dimensions / served_checkers 等）/
  evidence（pipeline schema、language_coverage、served_checkers、validators 状态、blockers、
  judgements、pending_implementation、unmapped/truncated、失败时的 gaps）；
- violations[]：file / rule_id（**带版本**，如 GATE-001@1）/ rule_version / severity /
  message / evidence（kind / subject / value / detail）；
- violations_by_severity：info/warning/error/critical **四个键恒定**；
- gate：status ∈ {pass, fail, unavailable, pinned} / exit_code / reason /
  rule_set_drift（null 或 {pinned, current}）；
- coverage：policy.check.build_check_volume 的 complete 汇总（缺维度**只报告**，
  v1 不改变退出码）；layer_sources 给出各来源计数（declared / filename_guess 等）。

**两次运行逐字节相同**（本轮实测：同一命令两次 --json 的原始 stdout 各 4571 字节、
逐字节相同，sha256 都是
d5819b7eab564fc71e0cb6708079c22767b113c9fa02ba3fe5e67892ee46ff25；
不含时戳、run、绝对路径与耗时）。

## 8 用例与命令原文（-n0）

用例文件 tests/unit/test_final_tree_gate.py（9 条；下表是任务要求的 5 类，其余为
规则集身份顺序无关、空树失败关闭、只读边界）。测试入口（本机 .venv 有 pytest/xdist；
系统 python 没有 xdist，-n0 会报 unrecognized arguments）：

    $env:PYTHONPATH="src"
    .venv\Scripts\python.exe -m pytest tests/unit/test_final_tree_gate.py -n0 -q

实测：**9 passed, 1 warning（pytest 缓存路径受沙箱限制的警告，不影响用例）, exit 0, 8.31s**。

| # | 用例 | 命令（在仓库根执行） | 实测退出码 / 判据 |
| --- | --- | --- | --- |
| 1 | 干净树 | python tools/final_tree_gate.py --workspace tests/fixtures/final_tree_gate/tree_clean --config tests/fixtures/final_tree_gate/adapter.yaml --json | **0**；gate.status=pass；targets=["pkg/module.py"]；violations=[]；decision=allow |
| 2 | 坏文件 | 同上，--workspace 换成 tests/fixtures/final_tree_gate/tree_bad | **1**；decision=block；violations[0].rule_id=GATE-001@1、severity=error、evidence.value=E501（真 Ruff 诊断） |
| 3 | 规则集漂移 | ... --pin .tmp/doc-pin.json → **0**；... --check .tmp/doc-pin.json → **0**；... --rules tests/fixtures/final_tree_gate/rules_alt --check .tmp/doc-pin.json | **1**；gate.rule_set_drift={pinned:"sha256:24f1eb…", current:"sha256:5587ac…"}；树仍干净（violations=[]），失败只来自漂移 |
| 4 | 缺配置 / 缺验证器 | ... --config tests/fixtures/final_tree_gate/nope.yaml；... --config-root .tmp/empty-config-root；... --validators py.source（坏文件树，验证器被允许清单排除） | 三条都是 **2**（gate.status=unavailable）；第三条理由同时写出「无验证器为 style_lint 提供证据」与「1 条 error/critical 级违规」 |
| 5 | 两次运行逐字节相同 | 同一命令跑两次 --json | 两次 **0**；stdout 逐字节相同（见 §7 的 sha256） |

补充实测（同一轮）：

- python tools/final_tree_gate.py --workspace tests/fixtures/final_tree_gate/tree_clean
  --config tests/fixtures/final_tree_gate/adapter.yaml --rules .../rules --rules .../rules_alt
  --pin .tmp/doc-order-pin.json → **0**；再用**相反顺序** --rules rules_alt --rules rules
  --check 同一钉住文件 → **0**（顺序不是漂移），payload.rule_set.ids=[GATE-001@1, GATE-002@1]；
- 空树（--workspace <空目录>）→ **2**，理由「枚举结果为 0 个受规则覆盖的文件 …」；
- --changed pkg/module.py → **0**，workspace_scope.mode=changed、targets 只含它；
- ruff check --config validation/ruff.toml tools/final_tree_gate.py
  tests/unit/test_final_tree_gate.py → All checks passed（exit 0）。

**执行事实**：本轮验证分两个窗口完成——期间会话的 dsh policy-hook 因工作树
src/enforcement/approvals.py 缺 from dataclasses import dataclass 而崩溃（未知状态按失败关闭，
所有工具调用被拒）；使用者补回 import 后，工具只做风格清理（E501 / import 排序 / 常量改名 /
未用局部变量），随后重跑上表全部用例与此处的补充实测。**行为未改动**；两份窗口的读数一致。

## 9 已知边界（失败关闭落点与代价）

- **耗时**：每个目标文件各跑一次完整流水线（含外部工具）。夹具树 1 个文件两次运行约数秒；
  仓库级大树按「文件数 × 单文件取证」放大，**不适合**每次操作都跑全树。需要窄口径用
  --changed；本版本没有并发、没有增量缓存。
- **整树 43 条规则的耗时与退出码：未测**（本轮只用夹具规则集 + 夹具树；未对仓库根跑门禁，
  也未跑 tools/ci_local.py）。这是 C3 v1 之后第一件应当补的读数。
- **会因缺证据失败关闭的 checker**（只要有规则命中就必须拿到证据，否则退出码 2，而不是
  「跳过算通过」）：
  - style_lint ← tool.ruff（缺失 / 版本不在 >=0.10,<1 / 分析失败码 invalid-syntax 等）；
  - missing_docstring ← py.docstring（AST / 源码读不到）；
  - forbidden_dependency ← py.depgraph（内部依赖解析不了 / 动态 import）；
  - missing_tests / failing_tests ← tool.pytest（缺失 / 超时 / 收集失败）；
  - 任何 checker 在 rule pack 里没有验证器 → _select_specs 的 blocker → 退出码 2。
  --validators 允许清单把某个 checker 的验证器排掉时，同样是 blocker（实测第 4 条）。
- **warning 不拦门禁**：这是本轮定义，不是疏忽；warning 条目仍逐条列出并计数。
- **check_volume.complete=false（缺维度）只报告**：v1 不改退出码。这与 policy.check 的
  既有口径一致；把「查不全」升格成阻断是另一次需要裁定的变更。
- **层来源**：filename_guess / adapter_config_default 会被标出来，但 v1 不因此失败
  （adapter 配置声明 default_layer: null 时门禁退回 policy.check 的既定口径）。
- **枚举边界**：--all 只收「语言有 rule pack」的文件；.md 等按设计不取证的语言被排除并计数。
  显式 --changed 的目标语言若完全没声明，退出码 2。
- **规则集钉住不覆盖**：注释/空白改动；以及「工具版本 / 验证器配置变了」——后者由
  reading_context.declarations 的摘要单独可读，本工具不把它们并入钉子。
- **未核实 / 环境差异**：本机沙箱下 .tmp/tmp/pytest-of-ZNM 的 pytest basetemp 锁被拒
  （D-20261018-04 同一条），因此用例自己用 .tmp/tests/final_tree_gate/<uuid>/ 做临时目录，
  **未**用 tmp_path；正常机器上两者行为应当一致（未在无沙箱环境复核）。另外，
  --pin / --check 在「规则目录不在仓库根之内」时会按 policy.check 同源口径退出 2
  （load_rule_set 的 repo_root 约束），本工具不另开例外——未为此单列用例。
- **未做（按任务边界）**：未改 src/** / registry/** / policies/** / 现有 tools / 04·05·06 /
  AGENTS / tools/README；未提交；未跑 ci_local；未删 .tmp。

## 10 留给 Lead 的更新点（本轮按边界不改）

1. docs/project/engineering-policy-platform/04-open-work.md：C3 v1 已落地（只读门禁 + 钉住），
   「危险动作前置阻断」仍未做（待 B1/B3 之后单独裁定）。
2. 05-implementation-plan.md §4 C3 行：状态从「已定」改「v1 已落地（整树门禁 + 规则集钉住）；
   前置阻断待做」。
3. 06-plan-progress.md §7.7：阶段 C 行补 C3 v1 读数指针（本文件）。
4. AGENTS.md 第 55 条版本轴表：新增 tools.final_tree_gate.FINAL_TREE_GATE_SCHEMA_VERSION
   （载荷轴，1.0 首次建轴）与 PIN_SCHEMA_VERSION（钉住文件自己的轴，1.0）。
5. tools/README.md：新增工具行（只读；退出码 0/1/2 属于「门禁判据」而非恒 0 只报告；
   --pin/--check 语义；不导入工作流框架）。
6. tests/unit/test_final_tree_gate.py 的协议断言写死了 "1.0"；改轴必须同批改它。

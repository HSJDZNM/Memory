# 09 · V1 十件仪器移入 `tools/` 的收益与风险评估（A1 / task-6）

> 角色：A1 评估员。**本评估不做任何实施**：没有搬文件、没有改 `tools/`、没有改产品代码、
> 没有改既有文档。全部写入只落在本文件与 `.tmp/instrument-assessment/**`。
> 评估对象：V1 在 `.tmp/verifier-n1/` 下自建的 10 件仪器（见
> [08-n1-independent-verification.md](08-n1-independent-verification.md) §7.1/§7.2）。
> 时限：`python tools/cleanup.py` 会整片删除 `.tmp/`，所以"留不留、留哪儿"是有期限的决定。
> 全部结论以**可复现命令 + 原始输出**为准；复现命令见 §7。

---

## 0. 一句话推荐

**不做整批搬迁（否 C）；把两处真实覆盖缺口按目的折进已有 git 跟踪的测试与工具（取 B 的最小形式），
其余仪器只把"方法"逐字留档，随 `.tmp/` 一起消失（A）。**

理由一句话：这 10 件里**只有 2 项能力是仓库里没有的**（整模块 AST 等价、任意树上的四路径矩阵），
而两者都已经有 git 跟踪的等价物、或只差 10 行就能补上；与此同时，整批搬进 `tools/` 会带来
**4 处硬编码绝对路径、1 处 fail-open、2 处已存在的第二份实现、10 条 ruff 违规、以及"任何改动都拉全量门禁"**
这五类必须清偿的债。搬运的净收益是负的。

**但有一件事是有时限的、必须现在决定（否则要花额外成本）**：N13 的验收判据是
"给 G06 补的 Phase 6 用例**对修前快照必须变红**"，而唯一的"修前快照"
`.tmp/verifier-n1/pre-fix` 会被清理。§6 第 10 条给了两毛钱成本的替代方案。

---

## 1. 决策表（不看仪器源码也能判）

| 问题 | 结论 | 决定性证据 |
| --- | --- | --- |
| 10 件里几件值得长期维护？ | **2 件**（`ast_equal.py`、`probe_n1.py` 的能力），其余 8 件是一次性脚手架或已有实现 | §2 / §3.1 |
| 搬进 `tools/` 会造出"第二份实现"吗？ | **会，而且已经能指认 2 处**：`diff_probe_reports.py` 与 `governance_gap_probe.compare_runs` 同语义；`ruff_scope.py` 与 `validation/validators.yaml:91` 的 canonical ruff 调用同语义 | §4.b |
| 搬进去会变坏吗？ | **会**：4/9 硬编码 `C:\Users\ZNM\Downloads\Memory` 作为**仓库根**；而 `tools/*.py` 里 21 个用 `__file__` 推根目录、**没有一处**硬编码仓库根（现存 2 处 `C:\Users` 字面量都不是仓库根，见 §4.a）；另 `ruff_scope.py` 对丢失文件记 0 且 exit 0 | §4.a / §4.c |
| 加文件进 `tools/` 会改门禁行为吗？ | **会**：`CODE_PREFIXES` 含 `tools/`，任何 `tools/**` 改动选中 **32 步**（29 CODE + 3 ALWAYS），而只改文档只选 9 步 | §4.d |
| 不搬会真的损失什么？ | **几乎没有不可替代的损失**：语义已由 2 个 git 跟踪测试钉住（实测 **42 passed / 1.89 s**）；"修前的红"可由一条变异规格从**当前树**重建（本报告已实测复现） | §3.3 |
| ruff 现状 | `tools/` 合计 **483** 条（手写项目脚本 57 条）；**但 `ruff check` 不在任何 CI 步骤里**，它不是门禁 | §4.f |
| 建议 | **A + B 最小形式**；明确不推荐 C | §5 |

---

## 2. 逐件结论表

判据列的含义（不是形容词，是可判定的）：**可复用**＝仓库里没有等价能力、且预期还会再用；
**脚手架**＝服务于本轮一次性的取证动作，换一轮就要改数据；**重复**＝已存在同语义实现。

| # | 仪器 | 行 | 作用 | 可复用性 | 机器相关性（代码级，非 docstring） | 重叠 | 搬入成本 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `probe_n1.py` | 255 | 四路径 × 6 案例 G6 探针（含必须放行的对照、异常可见） | **可复用（唯一）**：能在任意 `--root` 上跑四路径矩阵，0.67 s，不需要 pytest、不需要整仓副本 | 中：`L131 Path(".tmp/verifier-n1/config")` 是 **cwd 相对**（实测从别的 cwd 跑会散落一棵 `.tmp/verifier-n1/`）；`L58-59` 把两个保留标记写成**字面量**（`policy.checkers` 里已有同名常量）；`TARGET` 绑定 `adapters/dsh/adapter.yaml` 的 layer 规则 | 与 `tests/integration/test_dependency_path_consistency.py` + `tests/contract/test_dependency_extraction_parity.py` **语义重叠**（同一批文本、同一批路径、同一期望表）；与 `check_g06` 互补（后者只走 Phase 2） | 高 | **不搬**；能力折进 `check_g06`（＝已登记的 N13） |
| 2 | `assert_diff.py` | 186 | 断言 / 字符串常量的 AST 级比对（本轮：159 断言、409 常量） | **可复用**：全仓 `ast.dump` **零命中**，"重构有没有改语义"没有别的现成实现 | **高**：`L28 ROOT = Path(r"C:\Users\ZNM\Downloads\Memory")`；`L29` 默认 baseline 指向 `.tmp/verifier-n1/pre-fix` | 无 | 中 | **不搬**；方法留档（§3.5） |
| 3 | `probe_language_gate.py` | 117 | language 门控 / `skipped_rules` 可见性（5 场景，含 3 个非 python 目标） | **部分可复用**：其中 **2 个场景是真实覆盖缺口**（见 §3.3） | **低**：无绝对路径、无 `.tmp` 硬编码，纯 `--root/--tag/--out` | 与 `test_non_python_target_is_not_a_silent_pass` 部分重叠（后者只跑 1 个 md 场景） | 低 | **脚本不搬**；把 2 个缺口折进那个集成测试（约 10 行） |
| 4 | `ruff_scope.py` | 116 | 逐文件 ruff 计数（`--output-format concise` + 正则） | **脚手架**：`ruff --output-format=json` 一行就能计数（实测） | **高**：`L19` 在 **import 期**读 `HERE/scope.json`（本轮的 30 文件清单，会过期；换个目录就 import 失败） | **重复**：与 `validation/validators.yaml:91` 声明的 canonical 调用（`check --output-format=json`）同语义；且用的是 R8 记过坑的 `concise` 汇总行口径 | 中 | **不搬** |
| 5 | `make_tree.py` | 107 | 隔离副本 + 4 种精确串替换变异（替换前断言目标串唯一） | **脚手架**：107 行里多数是胶水；**值得留的是 4 条变异规格**（各 2 个字符串），不是这 107 行 | **高**：`L18 ROOT` 硬编码；`COPY_DIRS` 写死仓库布局 | 无直接重叠 | 中 | **不搬**；变异规格逐字留档（§3.5、§6.10） |
| 6 | `ast_equal.py` | 90 | 整模块 AST 等价（`ast.dump` + 首个差异位置） | **可复用**（与 #2 同一能力的最小形态） | **高**：`L14-15` 硬编码 ROOT + `SNAPSHOT`；实测其默认 baseline **今天已经过期**（对 `tools/governance_gap_probe.py` 与 `src/adapters/base.py` 都返回 `AST identical: False`） | 无 | 低-中 | **不搬**；与 #2 合并考虑，或只留方法 |
| 7 | `diff_probe_reports.py` | 104 | 两次 gap probe 报告的"结论层 / facts 层"比对 | **重复实现** | 低（纯输入/输出对，无路径硬编码） | **重复**：`tools/governance_gap_probe.py:2078-2124` 的 `_fingerprint`/`compare_runs` 已经是同一语义；实测同一对输入**两边结论完全一致**，且它额外的"归一化"对这两份报告是 **no-op** | 0（应删） | **不搬** |
| 8 | `compare.py` | 91 | 两次 `probe_n1` 报告的逐格对照 + 期望判定 + 路径一致性 | **脚手架**：schema 是 `probe_n1` 私有的；"期望判定"与 git 跟踪测试的期望表重复 | 低 | 与 #1 的跟踪测试期望表重叠 | — | **不搬** |
| 9 | `tree_hash.py` | 56 | 414 个文件的 sha256 清单（"运行窗口内代码是否冻结"） | **中等**：能力本身可复用，但只有约 40 行 | **高**：`L15 ROOT` 硬编码；`DIRS` 写死布局 | 无（`phase_evidence.py` 只对单个快照文件算哈希） | 低 | **不搬**；方法留档 |
| 10 | `scope.json` | 53 | 本轮 30 文件 in-scope 清单 | **一次性（轮次数据）** | **高**：绑定某一轮的改动集 | 与 07 号文档 §2 的逐文件清单是同一份数据的第二处副本 | — | **不搬** |

**10 件的可复用性分布**：可复用 2（#1 `probe_n1.py`、#2 `assert_diff.py`，其中 #6 `ast_equal.py` 是 #2 的最小形态）、
部分可复用 2（#3 `probe_language_gate.py`、#9 `tree_hash.py`）、脚手架 4（#4 #5 #8 #10）、重复实现 1（#7 `diff_probe_reports.py`）。
**换一种说法：10 件里没有一件是"必须搬进 `tools/` 才能活下去"的。**

---

## 3. 整体收益（含对抗性的"不搬会真的损失什么"）

### 3.1 收益侧：这 10 件真正提供了什么

它们承载的是**验证方法**，而且是这四类：

| 方法 | 由哪几件承载 | 仓库里是否已有等价物 |
| --- | --- | --- |
| ① 四路径矩阵 + 修前的红 + 反向对照 | `probe_n1` / `compare` / `make_tree` | **部分有**：2 个 git 跟踪测试覆盖同一语义（实测 42 passed / 1.89 s），但没有"Phase 6 用例进缺口探针"这一条（＝N13） |
| ② 变异实验（杀掉变异体） | `make_tree` + pytest | 方法论上 pytest 本身就够；`make_tree` 只省掉"造副本 + 精确替换 + 唯一性断言" |
| ③ 逐文件哈希冻结 | `tree_hash` | **没有**（但只有约 40 行） |
| ④ "重构有没有改语义"（AST 等价 / 断言未变） | `ast_equal` / `assert_diff` | **没有**（`ast.dump` 全仓零命中）——这是 10 件里最硬的一项独有能力 |

### 3.2 对抗性检验：搬进去能多得到什么？

把 10 件搬进 `tools/` 之后，**新增的能力**只有一条：
"`ruff_scope.py` 这类逐文件计数、`tree_hash.py` 这类全树哈希在仓库里变得可发现"。
其余全部是"把已经写在报告里的东西变成可执行文件"。**而 `tools/README.md` 的第一句话就写着**
"这些脚本只服务仓库本身的开发流程"——把一次性取证装置塞进这个目录，等于把它们升格成**被维护的产品脚本**，
而它们的输入（`scope.json`、`.tmp/verifier-n1/pre-fix`）在本轮结束时就死了。

### 3.3 反向检验：不搬会真的损失什么（逐条，带强度评级）

| # | 会损失的东西 | 是否可重建 | 强度 |
| --- | --- | --- | --- |
| L1 | `.tmp/verifier-n1/pre-fix`（T1 落地前的工作区快照，98.7 MB+ / 6062 文件） | **不可从 git 重建**（V1 §1.1 已论证 HEAD 更早）。但行为可由变异重建——**本报告已实测**：`make_tree --mutation revert-wiring` 后四路径 15 格重新变红（§7 命令 5） | 中 |
| L2 | 四路径矩阵的**原始证据 JSON**（顶层 41 文件 / 1,449,991 B） | 不可重建，但 08 号文档 §2.1/§2.2 已逐字引用；且它们含 `C:\Users\ZNM\...` 与 `app.asar` 绝对路径，**本来就不可能进版本库** | 弱 |
| L3 | 逐文件 ruff 计数结果（30 文件 163→0） | 已在 07 §2 / 08 §3.2 表格化 | 弱 |
| L4 | "重构没改语义"的**可执行**形态 | 不可重建为脚本；但方法是 `ast.dump(a)==ast.dump(b)`，下一次真要用时按当时的接口写即可 | 中（唯一值得单独对待的） |
| L5 | N13 的验收基线（"对修前快照必须变红"） | **可重建**：把 `revert-wiring` 或 `old-from-regex` 的精确替换串留档，用当前树造变异体即可 | 中（**有时限**，见 §6.10） |

**反向检验的结论**：`probe_n1.py` 表面上最像"不可替代的仪器"，但它的独有能力被两个事实削弱：

1. 它**不是**速度优势：`probe_n1.py` 实测 **0.67 s**，而覆盖同一语义的两个 git 跟踪测试实测
   **1.89 s（42 passed）**——同一个数量级；
2. 它**不是**唯一入口：`python tools/governance_gap_probe.py --only G06` 实测 **33.1 s**，
   在按目的归位之后就会把"Phase 2 + Phase 6 双路径 + before/after 预期表 + 任意 `--root`" 全部收进一个
   **已登记、已配测试、ruff 为 0** 的探针里。

### 3.4 一个必须先说清的重叠事实

`tools/governance_gap_probe.py` 的 G06 **只驱动 Phase 2 的 `python -m adapters.dsh.hooks`**
（`check_g06` 全文没有 `JsonAdapter` / `to_policy_context`）。所以：

- 缺口探针**看不到** N1 这类"多 Agent 路径"的问题（V1 §6.1 已实测：在那棵红树上照样 13/13）；
- 因此 `probe_n1.py` 与 `check_g06` **不是重复**，而是互补；
- 这正是 N13 登记的内容，也是 B 方案的第一项。

### 3.5 建议留档的三样东西（成本为零，收益是"不搬也不丢"）

1. **四路径矩阵与期望表**（6 案例 × 4 路径 + 每格的期望阻断值）——已经从 08 号文档 §2 与 §1.2 可读，
   本报告 §7 命令 5 再给一遍一行命令的复现；
2. **四条变异规格的精确字符串**（`revert-wiring` / `drop-language-guard` / `drop-dynamic-marker` /
   `old-from-regex`）——**这是 `make_tree.py` 里唯一不可再生的东西**（它们是从"修前 vs 修后"的 diff 里读出来的），
   见 §6.10；其中 `revert-wiring` 的替换对已实测可用；
3. **复现命令序列**（08 §7.2 已有；本报告 §7 给出清理后的等价写法）。

---

## 4. 整体风险（按任务书 a–f 逐条）

### 4.a `tools/README.md` 的要求与现有 `tools/*.py` 的共同形态

`tools/README.md` 只有两段：一句定位（"这些脚本只服务仓库本身的开发流程，不属于 Policy Platform
运行时"）+ 一张表 `| 脚本 | 用途 | 典型命令 |`。

**但"登记"不是君子协定，是硬门禁**——`tools/check_repo_consistency.py:274-296`：

    on_disk = {path.name for path in (ROOT / "tools").glob("*.py")}
    for name in sorted(on_disk - mentioned - INVENTORY_EXEMPT):
        issues.append("tools/%s 没有登记到 tools/README.md" % name)

它由 `phase-8.yml:39 "Repository consistency gate"` 执行，而这一步在 `ci_local.ALWAYS_STEPS` 里
——**每次本机门禁都会跑**。所以"顶层 `tools/*.py` 必须登记"是一条会红的检查。

**现有 `tools/*.py` 的共同形态（29 个顶层文件实测）**：

| 形态要素 | 实测 |
| --- | --- |
| 模块 docstring | 29/29（含"用法"与退出码语义） |
| `if __name__ == "__main__"` | **23/29**（余 6 个是被 import 的内容模块：`dora_site` / `learn_site` / `pep_site` / `phase6-8_cells`） |
| `main()` 函数 | 与上一行同集合（23/29） |
| `argparse` | 14/23 可执行脚本（其余用 `sys.argv` + `__doc__`） |
| **仓库根路径** | `tools/*.py` 共 29 个，其中 **21 个用 `__file__` 推根目录**（19 个 `parents[1]` + 2 个 `parent.parent`，§7 命令 7）；**没有一处硬编码仓库根**。现存 2 处 `C:\Users` 字面量都不是仓库根：`dsh_sandbox_loop.py:268`（docstring 里的错误引文）、`governance_gap_probe.py:735`（`DSH_IMPL_ASAR`，第三方 dsh 安装路径，找不到就降级不阻断） |
| 读 `.tmp/` | 是允许的（`governance_gap_probe` / `*-loop` / `retrieval_eval` 等），但**都只写构建产物，且路径可由 `--work` 覆盖** |

**结论**：新脚本被隐含要求"形态与现有 21 个一致"；而 10 件仪器里 **4 件**在这一点上直接不合格。

### 4.b 功能重叠（这一条是本评估的核心）

**有。已经能指认 2 处确定的"同一语义第二份实现"，另有 2 处部分重叠。**

#### b-1 `diff_probe_reports.py` ≡ `governance_gap_probe.compare_runs`（确定重复）

`tools/governance_gap_probe.py:2078-2124` 已经有：

    def _fingerprint(report):  # 逐项结论 + facts，不含路径、run_id 等易变字段
    def compare_runs(runs):    # 连续多次运行的逐项结论与 facts 必须完全一致

V1 的 `diff_probe_reports.py` 做的是同一件事（"结论层 + facts 层"比对 + 归一化易变字段）。
**实测（§7 命令 8）**：对同一对输入（`gap-old2.json` / `gap-new3.json`）

    == governance_gap_probe.compare_runs（既有实现）==
    consistent: True  差异条数: 0
    == diff_probe_reports.py（V1 仪器）==
    逐项结论相同: True
    facts（归一化后）相同: True

而且它额外的"归一化"对这两份报告是 **no-op**（两份报告的 `facts` 里都不含 `run-<id>`：
实测"facts 含 run-<id> 的检查: []"）。**搬进去就是把 `compare_runs` 写成第二遍。**

#### b-2 `ruff_scope.py` ≡ `validation/validators.yaml` 的 canonical ruff 调用（确定重复）

`validation/validators.yaml:87-92` 已经声明了唯一权威的调用口径：

    command: [ruff]
    argv: ["check", "--output-format=json", "--no-cache", "--config", "{config}", "{paths}"]

`src/validators/adapters/ruff.py` 按它跑 ruff、解析 JSON、映射成证据。
`ruff_scope.py` 却用 `--output-format concise` 再拿正则数行——**这正是
R8 记下来的那个坑**（"concise 的 stdout 里除违规行还有一行汇总，实测 8 条被数成 10 条"）。
实测 `ruff --output-format=json` 一行就能拿到权威计数（§7 命令 9）：
`tools/secret_scan.py -> 1 条；codes: ['E501']`。

#### b-3 部分重叠：`probe_n1.py` vs 两个 git 跟踪测试

| 维度 | `probe_n1.py` | `tests/integration/test_dependency_path_consistency.py` | `tests/contract/test_dependency_extraction_parity.py` |
| --- | --- | --- | --- |
| 路径 | p2-dsh / p6-json / p6-dsh / p6-hook | 同 4 条 | 只测共享层 + 显式依赖优先 |
| 文本 | 6 个 | 5 个（`PARITY_TEXTS`）+ 8 个（`CASE_TEXTS`） | 7 个 |
| 期望 | 每格 `expected_blocked` | 每格 `PARITY_EXPECTED_BLOCK` | 逐项断言 |
| 依赖集相等 | 只打印 `deps_equal` | **断言** `phase6_context.dependencies == phase2_context.dependencies` | **断言** 共享层与 Phase 2 逐项相同 |
| 任意树 | **有**（`--root`） | 无（`load_adapter("dsh", root=REPO_ROOT)`） | 无 |

**唯一未被跟踪测试覆盖的案例**：`4-dotted-literal`（`from shop.order_repository import ...`）
在 **Phase 6 路径**上的结论。这是 1 个案例缺口，补进 `PARITY_TEXTS` 约 4 行。
而 `probe_n1` 的"任意 `--root`"能力，在 B（N13）落地后由 `governance_gap_probe --root` 接管
——**那本来就是它的既有接口**。

#### b-4 未被 `probe_n1` 引用、但属于同一类隐患：保留标记的字面量副本

`probe_n1.py:58-59`：

    UNPROVEN_DYNAMIC_IMPORT = "<unproven-dynamic-import>"
    UNPROVEN_CHANGED_TEXT = "<unparseable-changed-text>"

而权威定义在 `src/policy/checkers.py:69-70`（值今天相同）。`tests/contract/test_dependency_extraction_parity.py:40`
是 `from policy.checkers import ...`——两者口径不一致。**后果**：如果标记文本漂移，
`compare.py` 的 PASS/FAIL 只看 `row["blocked"]`，`marker_unproven_dynamic` 只影响一个 `*` 装饰，
**不会变红**——仪器会继续报绿，但少测了一项。

#### b-5 无重叠的（明确写下来）

`src/validators/python_ast.py`、`src/validators/depgraph.py`、`src/validators/selection.py`、
`tools/check_notebook.py` 与这 10 件**没有实现级重叠**。
但要记一条**前向风险**：`python_ast`/`depgraph` 已经是"从文件里解析依赖"的一份实现，
`textfacts.py` 是"从变更片段里提取依赖"的另一份（两者不等价，已被
`KNOWN_DIVERGENCES` 钉成断言，见 N4）。若将来有人把 `probe_n1` "通用化"成一个
自带提取逻辑的工具，就会造出**第三份**。

### 4.c 逐件机器相关性（代码级证据，不含 docstring）

用 AST 把 docstring 与代码字面量分开（§7 命令 6），结果：

| 仪器 | 代码级机器耦合 | 行号 |
| --- | --- | --- |
| `assert_diff.py` | `ROOT = Path(r"C:\Users\ZNM\Downloads\Memory")`、`SNAPSHOT = ROOT/".tmp"/"verifier-n1"/"pre-fix"` | L28-29 |
| `ast_equal.py` | 同上 | L14-15 |
| `tree_hash.py` | `ROOT = Path(r"C:\Users\ZNM\Downloads\Memory")`（`SKIP_PARTS` 含 `.tmp` 是正常的跳过表） | L15 |
| `make_tree.py` | 同上（硬编码 ROOT；`COPY_DIRS` 写死 8 个目录布局） | L18-20 |
| `probe_n1.py` | `config_dir = Path(".tmp/verifier-n1/config") / args.tag`（**cwd 相对**，不是 `--root` 相对） | L131 |
| `ruff_scope.py` | `SCOPE = json.loads((HERE / "scope.json").read_text(...))`（**import 期**读"本轮 30 文件清单"） | L19 |
| `probe_language_gate.py` | 无 | — |
| `compare.py` | 无 | — |
| `diff_probe_reports.py` | 无 | — |
| `scope.json` | 整个文件就是"某一轮"的数据 | — |

三条**实测**后果（不是推断）：

1. **cwd 相对路径会散落目录**：从 `.tmp/instrument-assessment/` 调 `probe_n1.py --root <仓库根>`，
   它在**当前 cwd 下**建出 `.tmp/verifier-n1/config/<tag>/phase2-dsh.yaml`（实测输出见 §7 命令 5 附注）。
2. **默认 baseline 今天已经过期**：`ast_equal.py --baseline snapshot` 对
   `tools/governance_gap_probe.py`、`src/adapters/base.py` 都返回 `AST identical: False`。
   搬进 `tools/` 等于把一个"指向会被删除的快照"的默认值写进产品脚本。
3. **`ruff_scope.py` 对缺失文件 fail-open**：把 `scope.json` 换成一个只列两个不存在文件的副本，
   实测 `tag=missing-files-demo in_scope_total=0 ... exit=0`——**与"30 个文件全清白"输出完全同形**
   （源码依据：`L26-27` 返回 `count: None`，`L70` 累加 `row["count"] or 0`）。

### 4.d 加文件进 `tools/` 会不会改变门禁的改动范围判定？——**会**

`tools/ci_local.py:124-133`：

    CODE_PREFIXES = ("src/", "tests/", "tools/", "examples/", "policies/", "registry/", "adapters/", ".github/")

`_selected_names()` 用 `_touched(changed, CODE_PREFIXES)` 前缀匹配；`_changed_paths()` 同时取
`git diff --name-only` 与 `git status --porcelain`（**未跟踪的新文件也算**）。
实测（§7 命令 4，用 monkeypatch 注入改动集，不执行任何步骤）：

| 改动集 | 选中步骤数 | 含 "Unit, contract"？ |
| --- | --- | --- |
| `docs/project/x.md` | 9 | 否 |
| `tools/instruments/probe_n1.py` | **32** | 是 |
| `tests/tools/test_probe_n1.py` | 32 | 是 |
| `tools/migrated_probe_n1.py`（顶层） | **32** | 是 |
| `tools/README.md` | 32 | 是 |

**结论**：搬进 `tools/`（顶层或子目录都一样）之后，**以后任何一次碰这些文件的提交都会拉起
29 个 CODE 步骤 + 3 个 ALWAYS 步骤**（全量 pytest 的基线是 1430 passed / 248 s，见 07 号文档 R4）。
本轮不会多花成本（`src/` + `tests/` 已经改了），**代价落在以后**。
反过来，"不搬"意味着不进这个前缀，改报告/改测试仍然是精确范围内的。

### 4.e 新脚本要不要测试？仓库的既有惯例是什么？

**惯例分三层（实测）**：

1. **有微妙不变式的工具 → `tests/unit/test_<tool>.py`**：
   `tests/unit/test_ci_local.py`（253 行，`importlib.util.spec_from_file_location` 加载 +
   `monkeypatch.setattr(module, "ROOT", tmp_root)`）、`tests/unit/test_cleanup.py`（362 行，同法）。
2. **闭环/探针类工具 → 一条 CI 步骤 + 一个 shell-out 的集成测试**：
   `tools/governance_gap_probe.py` 有 `tests/integration/test_governance_gap_probe.py`（138 行，
   子进程 + `GOVERNANCE_PROBE_ROOT` 环境变量换根 + 报告写进 `.tmp/verifier/probe`）；
   `enforcement_loop` / `agent_loop` / `api_loop` / `orchestration_loop` / `retrieval_eval` /
   `validator_loop` / `policy_bench` 等各自有 `phase-8.yml` 的 `run:` 行。
3. **内容源模块（`phaseN_cells.py`、`*_site.py`）→ 无单测**，由生成器的 `--check` 覆盖。

**"不配测试的代价"在仓库里已经被写成规则**——00 号文档 §3 验收口径第 1 条：

> **每条修复必须配一个"会失败的检查"**：单元/契约测试，或确定性探针脚本的一行断言。
> "改了代码但说不出哪条检查会因此变红" = 没修。

所以一件**既不进测试、也没有 CI 步骤**的迁移仪器，按本仓库自己的口径就是**死代码**。
再叠加 §4.d：进了 `tools/` 却不配检查，等于"每次改动都要跑 32 步门禁，而这些步一步都不覆盖它"。

### 4.f ruff：现在多少违规？"只清自己"还是"整目录绿"？

**现状（实测）**：`ruff check --config validation/ruff.toml tools` → `Found 483 errors.`

| 桶 | 条数 | 07 号文档 §2 的地位 |
| --- | --- | --- |
| `tools/build_learning_notebook.py` | 113 | **明确边界外**（notebook 生成链） |
| `tools/phase{6,7,8}_cells.py` | 93 | 同上（手册内容源） |
| `tools/mirror_docs.py` + `*_site.py` + `owasp_cheatsheets/` | 220 | README 明写"**不属于本项目**的脚本" |
| **手写项目脚本**（retrieval_eval 15 / orchestration_loop 7 / check_arch_style 6 / phase_evidence 6 / check_repo_consistency 4 / agent_loop、api_loop、check_arch_canon、enforcement_loop、run_notebook_in_kernel 各 3 / policy_bench 2 / secret_scan、validator_loop 各 1） | **57** | 上一次清理**只清了"本轮改动集里"的那 3 个（`ci_local`/`dsh_sandbox_loop`/`governance_gap_probe`）** |

**答案："只清自己"，而且这不是我的推断，是 07 号文档 §2 的原文口径**：

> **口径**：对本改动集（`git status --porcelain` 的 44 个文件）里的每个 `.py` …

同节的另一句给出了理由，值得逐字引用：

> **既然本轮要动这批文件，就一并清到 0**：只清 83 条会留下"新引入的违规"…

所以规则是"**你动的文件必须 0，且不许新增 `noqa`**"，而不是"目录必须 0"。
**并且要补一条事实**：`ruff check` **不在 CI 的任何步骤里**（`phase-8.yml` 只有
`- name: Install external linter (ruff)`，ruff 仅通过 `tool.ruff` 验证器作用于**被声明的目标文件**）。
因此"483 条"是一个**可见但不受门禁约束**的数——搬迁不会**强制**大扫除，只会**邀请**它。

**新文件的实测代价**：把 9 个仪器按 `--stdin-filename tools/instruments/<name>` 过同一份
`validation/ruff.toml`，合计 **10 条**（1 个 `I001` 在 `probe_n1.py`，9 个 `E501`，
分布在 assert_diff / ruff_scope / make_tree / diff_probe_reports / compare）。数值上是小活，
**但"搬迁→必须顺手清 483 条"这个滑坡是真实存在的**，因此它必须写进 §6 的验收条件里。

---

## 5. 三个方案的成本对比

成本的口径：**新增/改动文件数 + 必须清偿的正确性问题数 + 必须补的检查数**。
（不给"人时"这种无法复核的单位。）

| | **A · 不搬** | **B · 按目的归位（推荐的最小形式）** | **C · 整批搬进 `tools/instruments/`** |
| --- | --- | --- | --- |
| 新增文件 | 0（只加本报告） | 0（B1/B2 都改既有文件）；若做 B3 则 +1 脚本 +1 单测 | **10**（9 `.py` + `scope.json`） |
| 改动既有文件 | 0 | `tools/governance_gap_probe.py`（+40~60 行）、`tests/integration/test_dependency_path_consistency.py`（+约 10 行） | 9 个脚本都要改（路径/baseline/常量） |
| 必须清偿的正确性问题 | 0（但必须把 §3.5 的三样东西留档） | 0 | **8 类**：4 处硬编码绝对路径、1 处 cwd 相对 `.tmp`、3 处指向 `pre-fix` 的默认 baseline、1 处轮次 `scope.json`、1 处 fail-open、2 处重复实现、1 处标记常量副本、10 条 ruff |
| 必须补的检查 | 0 | 0（B1 由既有 `test_governance_gap_probe.py` 覆盖；B2 本身就是测试） | **至少 1~3 个单测**（00 §3.1"会失败的检查"），否则就是死代码 |
| README / 门禁 | 不动 | 不动 | 顶层放 → **9 行 README**（否则 `Repository consistency gate` 红，且它是 ALWAYS 步）；子目录放 → 门禁**看不见**（`check_tool_inventory` 只 glob 顶层），等于把"没登记会红"改成"没登记看不见" |
| `ci_local` 影响 | 0 | 0 | 任何 `tools/**` 改动 → **32 步**（实测） |
| 直接失去 | `.tmp/verifier-n1/` 全部（仪器 41 文件 / 1.45 MB + 快照与副本 ≥98.7 MB） | 同 A（B1/B2 落地后，`probe_n1` 的能力由 `check_g06` 接管） | 无（但得到的是"要维护的第二份实现"） |
| 可逆性 | 高（方法可重建，见 L1–L5） | 高 | 低（一旦进 `tools/`，删它需要一次独立的"移除产品脚本"变更） |
| N13 的验收判据 | 需在清理前跑，或用变异重建（§6.10） | **B1 实施时立刻可用**（同一次变更里做） | 不解决 |
| **净评价** | 可接受，前提是 §3.5 留档 | **推荐**：只做两件有真实覆盖缺口的事 | **不推荐**：成本最高，且把"同一语义第二份实现"制度化 |

**B 的三项拆开看**：

- **B1（N13）**：把"Phase 6 用例"折进 `check_g06`。机制上现成——`Env.py_json()`
  （`tools/governance_gap_probe.py:317`）已经能"在被检根的 `PYTHONPATH` 下跑一小段代码并解析 JSON"，
  `probe_n1.run_p6_json` 的载荷构造只有约 20 行。**不新增检查 id，13 项不变**，
  既有测试的三条断言（`before`/`after` 都要声明、两者必须不同、`--phase after` 必须 ok）都照旧成立。
  成本：`--only G06` 实测 33.1 s，加 1~2 s。
- **B2**：把 `probe_language_gate.py` 的 3 个非 python 场景补成 `parametrize`
  （`markdown-doc-relative-import` / `markdown-doc-dynamic-import` / `markdown-doc-unparseable`），
  现有用例只跑其中 1 个。成本约 10 行；**顺带把 `4-dotted-literal` 补进 `PARITY_TEXTS`**（约 4 行）。
- **B3（可选）**：把"重构有没有改语义"做成一个通用脚本。这是唯一"能力在仓库里没有"的一项。
  最小形态：1 个 `tools/ast_unchanged.py`（约 80 行：`--path` / `--before <file|git-ref>`，
  `ast.dump` 比对 + 断言/常量计数）+ 1 个 `tests/unit/test_ast_unchanged.py` + 1 行 README。
  **必须用 `Path(__file__).resolve().parents[1]`，不得保留 `snapshot` 这种指向 `.tmp` 的默认 baseline。**
  若不做 B3，代价是"下次真要证明'只换了行'时，按那时的接口现写 3 行"。

---

## 6. "要搬必须先满足什么"（可验收条件清单）

> 下列条件对**任何**要进 `tools/` 的仪器成立。每条都给出**能红的命令**，不是形容词。

1. **仓库根只能来自 `__file__`**：一律 `Path(__file__).resolve().parents[N]`
   （顶层 N=1，`tools/instruments/` N=2），新增脚本里不得出现本机绝对路径。
   *现状：4/9 仪器把**仓库根**硬编码成 `C:\Users\ZNM\Downloads\Memory`（逐件行号见 §4.c）。
   注意不能拿"grep `C:\Users` 必须 0 命中"当判据：`tools/` 现存 2 处都不是仓库根
   （`dsh_sandbox_loop.py:268` 的 docstring 引文、`governance_gap_probe.py:735` 的第三方安装路径）。*
2. **不依赖 `.tmp/verifier-n1/`**：`grep -rn "verifier-n1" tools/` 必须 0 命中；
   默认 baseline 只能是 `git` 或显式 `--before`，**不得指向会被 `cleanup.py` 删除的快照**。
   *现状：3 件（`assert_diff`/`ast_equal`/`tree_hash` 的 `SNAPSHOT`）不合格。*
3. **不依赖轮次数据**：文件集必须来自命令行参数或 `git status`，
   不得把"某一轮的文件清单"（`scope.json`）作为工具的 import 期输入。*现状：1 件不合格。*
4. **不重复既有语义**：`diff_probe_reports` 的比对必须改成调用 `governance_gap_probe.compare_runs`；
   ruff 计数必须走 `validation/validators.yaml:91` 的 `--output-format=json` 口径；
   保留标记必须 `from policy.checkers import`。
5. **失败关闭**：列出的目标文件缺失 / 解析失败 / 报告缺字段一律**非 0 退出**。
   *现状：`ruff_scope.py` 违反（实测 exit 0 + `total=0`，与"全清白"同形）。*
6. **登记**：若放顶层，`python tools/check_repo_consistency.py` 必须 exit 0（每个 `tools/*.py` 一行）。
   若放子目录，**必须同时把 `check_tool_inventory()` 改成能看见子目录**——否则是"用目录结构绕过一条既有门禁"，
   把"没登记会红"降级成"没登记看不见"，与本仓库的失败关闭取向相反。
7. **ruff**：`ruff check --config validation/ruff.toml <每个新文件>` = 0，且**不得新增 `noqa`**
   （07 §2 口径）。**不要**把"清 `tools/` 目录"（483 条）当成搬迁的一部分。
8. **文字约定与凭据**：`python tools/check_text_conventions.py <files>` 0 处问题
   （实测 10 件全部 0 处）、`python tools/secret_scan.py` 干净（实测仪器内容过 6 条模式 **0 命中**）。
   这两步在 `ALWAYS_STEPS` 里，**每次门禁都跑**。
9. **必要检查**：至少一个 `tests/unit/test_<tool>.py`（按 `test_ci_local.py` 的
   `importlib` 加载 + `monkeypatch ROOT` 惯例）**或**一条 `phase-8.yml` 的 `run:` 步骤。
   依据是 00 号文档 §3.1"每条修复必须配一个会失败的检查"，不是我的偏好。
10. **N13 的时限处置（与搬迁无关，但必须一起裁决）**：`.tmp/verifier-n1/pre-fix` 一旦被清理，
    "对修前快照必须变红"这条判据就失去输入。**两条出路，任选其一**：
    - (a) **在清理之前**先用 `--root .tmp/verifier-n1/pre-fix` 跑一次新的 `check_g06` 并留档；或
    - (b) **把变异规格逐字写进 07/00 号文档**，让"修前的红"可以由当前树重建。最小充分集是
      `revert-wiring`（`src/adapters/base.py`，175 字符 → 18 字符）与 `old-from-regex`
      （`src/adapters/textfacts.py` 的 from 正则新旧两行）。
      **本报告已实测 (b) 可行**：变异体上四路径 15 格重新变红（§7 命令 5）。

---

## 7. 决策所需的最小事实集（可直接复核的命令 + 原始输出）

以下命令**全部由本评估实跑**，输出为原文摘录。除第 4、8、10 条会在 `.tmp/instrument-assessment/`
下写自己的中间产物外，都只读。（`pytest` 一律经 `.venv/Scripts/python.exe .tmp/runlock.py -m pytest`。）

**命令 1 · `tools/` 的共同形态**

    .venv/Scripts/python.exe .tmp/instrument-assessment/shape_scan.py

    -> tools/*.py 顶层 29 个（递归 35）；模块 docstring 29/29；main+guard 23/29；
       项目脚本里模块级绝对路径 0 处（"C:\path\to\python.exe" 只出现在 ci_local 的帮助文本里）

**命令 2 · ruff 现状**

    ruff --version                                   # ruff 0.14.13
    ruff check --config validation/ruff.toml tools   # -> Found 483 errors.
    .venv/Scripts/python.exe .tmp/instrument-assessment/ruff_tools_breakdown.py

    -> 113 build_learning_notebook.py / 96 mirror_docs.py / 78 owasp_cheatsheets/
       93 phase{6,7,8}_cells.py / 46 *_site.py / 57 手写项目脚本
    -> 码分布：E501 428 / N806 18 / F401 7 / I001 7 / S105 4 / E401 4 / …

**命令 3 · 仪器自身的 ruff 与新文件代价**

    .venv/Scripts/python.exe .tmp/instrument-assessment/ruff_instrument_probe.py

    -> 10 条：probe_n1 1(I001) / assert_diff 1(E501) / ruff_scope 2(E501) / make_tree 3(E501)
       / diff_probe_reports 2(E501) / compare 1(E501)；其余 4 件 0 条

**命令 4 · `ci_local` 选步（monkeypatch 注入改动集，不执行步骤）**

    .venv/Scripts/python.exe .tmp/instrument-assessment/ci_local_selection_probe.py

    -> 只改 docs/project/x.md                 : 9 步，含 Unit? False
       新增 tools/instruments/probe_n1.py     : 32 步，含 Unit? True
       新增 tests/tools/test_probe_n1.py      : 32 步，含 Unit? True
       新增 tools/migrated_probe_n1.py（顶层） : 32 步，含 Unit? True
       只改 tools/README.md                   : 32 步，含 Unit? True
    -> CODE_PREFIXES = ('src/', 'tests/', 'tools/', 'examples/', 'policies/',
                        'registry/', 'adapters/', '.github/')；CODE_STEPS 个数 = 29

**命令 5 · 反向对照今天仍然可复现（"修前的红"能从当前树重建）**

    # (a) live 树仍然全绿
    .venv/Scripts/python.exe .tmp/verifier-n1/probe_n1.py --root . --tag a1-live \
        --out .tmp/instrument-assessment/probe-live.json          # 0.67 s
    # (b) 造变异体（只动副本，不动工作区）
    .venv/Scripts/python.exe .tmp/verifier-n1/make_tree.py \
        --target .tmp/instrument-assessment/regressed --mutation revert-wiring
    # -> mutated ...\src\adapters\base.py [revert-wiring] / replaced 175 chars with 18 chars
    .venv/Scripts/python.exe .tmp/verifier-n1/probe_n1.py \
        --root .tmp/instrument-assessment/regressed --tag a1-regressed \
        --out .tmp/instrument-assessment/probe-regressed.json
    .venv/Scripts/python.exe .tmp/verifier-n1/compare.py \
        --before .tmp/instrument-assessment/probe-live.json \
        --after .tmp/instrument-assessment/probe-regressed.json

    -> (a) live: "修后是否每格都等于期望 = PASS（全部相符）"、"四条路径同结论、deps_equal=True"
    -> (b) 变异体: p6-json / p6-dsh / p6-hook 三列在 1/2/3/4/6 号案例上全部 allow；
       "修后是否每格都等于期望 = FAIL：15 格"；"修前/修后逐格差异" 15 行
    -> 附注（cwd 相对路径的实测）：把 (a) 的 cwd 换到 .tmp/instrument-assessment/ 再跑，
       新出现的目录是 .tmp/instrument-assessment/.tmp/verifier-n1/config/a1-live/phase2-dsh.yaml
       ——因为它写的是 Path(".tmp/verifier-n1/config")，跟 cwd 走而不是跟 --root 走。

**命令 6 · 机器相关性（AST 区分 docstring 与代码字面量）**

    .venv/Scripts/python.exe .tmp/instrument-assessment/code_path_literals.py

    -> assert_diff.py L29 '.tmp' + 'verifier-n1'；ast_equal.py L15 '.tmp' + 'verifier-n1'；
       probe_n1.py L131 '.tmp/verifier-n1/config'
    grep 输出：assert_diff.py:28 / ast_equal.py:14 / make_tree.py:18 / tree_hash.py:15
       均为 ROOT = Path(r"C:\Users\ZNM\Downloads\Memory")

**命令 7 · 现有脚本怎么找仓库根（对照组）**

    Select-String -Path tools\*.py -Pattern '__file__'     # -> 21 处
    Select-String -Path tools\*.py -Pattern 'C:\\Users'     # -> 2 处

    -> 21 处：19 个 ROOT/REPO_ROOT = Path(__file__).resolve().parents[1]
       + 2 个 parent.parent（mirror_docs.py:69 / dora_site.py:439）
       ；另有 8 个不要根目录的脚本（check_notebook / check_text_conventions / lock_requirements
       / phase6-8_cells / learn_site / pep_site）与它们无关
    -> 2 处 C:\Users 都不是仓库根：dsh_sandbox_loop.py:268（docstring 引文）
       / governance_gap_probe.py:735（DSH_IMPL_ASAR，第三方 dsh 安装路径，找不到就降级）

**命令 8 · 重复实现（`diff_probe_reports` vs `compare_runs`）**

    .venv/Scripts/python.exe .tmp/instrument-assessment/diff_impl_compare.py

    -> compare_runs: consistent=True 差异条数=0
       diff_probe_reports: 逐项结论相同: True / facts（归一化后）相同: True
       两份报告 facts 含 run-<id> 的检查: []（归一化是 no-op）

**命令 9 · canonical ruff 口径已足够计数**

    ruff check --config validation/ruff.toml --output-format=json --no-cache tools/secret_scan.py
    # 对照 validation/validators.yaml:91
    # argv: ["check","--output-format=json","--no-cache","--config","{config}","{paths}"]
    -> 1 条；codes: ['E501']

**命令 10 · `ruff_scope.py` 的 fail-open（反例）**

    .venv/Scripts/python.exe .tmp/instrument-assessment/rewrite_scope.py   # 造一份只列两个不存在文件的 scope.json
    .venv/Scripts/python.exe .tmp/instrument-assessment/ruffscope-repro/ruff_scope.py \
        --root .tmp/verifier-n1/pre-fix --tag missing-files-demo --skip-docs

    -> tag=missing-files-demo in_scope_total=0 docs_py_total=None
       change_set_extra_total=0
       exit=0        # 与"30 个文件全清白"输出同形

**命令 11 · 不搬会损失什么：跟踪测试的速度与覆盖**

    .venv/Scripts/python.exe .tmp/runlock.py -m pytest \
        tests/integration/test_dependency_path_consistency.py \
        tests/contract/test_dependency_extraction_parity.py -q
    # -> 42 passed, 1 warning in 1.89s
    # 对照：probe_n1.py 单跑 = 0.67 s；governance_gap_probe --only G06 = 33.1 s

**命令 12 · 定性事实（只读 grep / 一次性探针）**

    grep -n "check_g06" tools/governance_gap_probe.py      # 该段无 JsonAdapter / to_policy_context
    grep -rn "ast\.dump" .                                 # 0 命中（"AST 等价"没有既有实现）
    grep -n "CODE_PREFIXES" -A 10 tools/ci_local.py        # tools/ 在 CODE_PREFIXES 里
    grep -n "glob(\"\*.py\")" tools/check_repo_consistency.py   # 只 glob 顶层 → 子目录不可见
    grep -n "ruff" .github/workflows/phase-8.yml           # 只有 "Install external linter (ruff)"
    .venv/Scripts/python.exe .tmp/instrument-assessment/glob_probe.py
    # -> glob('*.py') 29 / rglob('*.py') 35
    .venv/Scripts/python.exe .tmp/instrument-assessment/secret_and_json_probe.py
    # -> secret 模式数: 6 / 命中行数: 0
    .venv/Scripts/python.exe tools/check_text_conventions.py <10 件仪器>   # -> 检查 10 个文本文件，问题 0 处

---

## 8. 我没能确定的事

1. **B1（N13）的真实工作量没有实测**。我只证明了机制可行（`Env.py_json` 存在、`--only G06` 33.1 s、
   `before != after` 的测试约束可控），**没有写一行 `check_g06` 的新代码**（越写域）。
   所以 §5 里 B1 的"+40~60 行"是**按 `probe_n1.run_p6_json` 的规模外推**，不是实测。
2. **没有跑全量 pytest、没有跑 `tools/ci_local.py`**（前者属于 Lead/verifier 的门禁动作，
   后者 Lead 独占排他锁）。因此"搬进去之后门禁仍然全绿"这件事**没有直接证据**，
   只有 §4.d 的选步证据与 §4.f 的 ruff 证据。
3. **没有证明"清理 `.tmp/` 之后无法重建 `pre-fix`"**。我只证明了"变异体能重建同样的红"，
   没有穷举是否还有别的重建路径（例如某位提交者手里可能留有快照副本）。
4. **`.tmp/verifier-n1` 的总大小只测到下限**：`Get-ChildItem -Recurse` 在若干
   `.tmp/pytest-cache-files-*` 目录上报 `UnauthorizedAccessException`，
   所以 98.7 MB / 6062 文件是**偏小的**读数；顶层 41 文件 / 1,449,991 B 是准的。
5. **`secret_scan` 我只用它的模式表跑了仪器内容（0 命中），没有把文件真的放进 `tools/` 跑整条门禁**。
   依据是 `secret_scan.py` 扫的是 `git ls-files --cached --others --exclude-standard`，
   仪器当前在 `.tmp/`（被 ignore）里因此从未被扫过；搬出去之后会被扫，而内容实测干净。
6. **`tests/tools/` 这个落点我只做了静态判断**（`pytest.ini` 的 `testpaths = tests` 会递归收集），
   没有实际建目录跑一遍，因此"无 basename 冲突"这一点未验证。
7. **我没有裁决"要不要保留证据 JSON"**。它们含绝对路径与 `app.asar` 路径、且是构建产物，
   但"是否把其中任何一份摘录进文档"属于 Lead 的取舍，不在本评估的写域内。

---

## 9. 附录：方法留档（`.tmp/` 被清理后仍然可复现）

> 本附录由 **Lead 追加**，是这个评估的直接产物：既然结论是"不搬仪器"，那**不可再生的部分必须进版本库**。
> 仪器本身会随 `.tmp/` 消失，下面三样东西不会。

### 9.1 四条变异规格（精确替换串）

`make_tree.py` 里唯一不可再生的内容是这四条规格——它们是从"修前 vs 修后"的 diff 里读出来的。
目标串必须在文件里**恰好出现 1 次**（替换不到就报错，不许"看起来改过了"）。

```python
NL = chr(10)

# 变异 A（反向对照）：把 Phase 6 的接线回退成"只认载荷里显式声明的 dependencies"= 修复前的形态。
# 三个 Adapter 已不再预计算，于是依赖集恒为空 —— 这就是 N1 的"修前的红"。
REVERT_WIRING = (
    "src/adapters/base.py",
    '        text = event.payload.get("text")' + NL
    + "        if not isinstance(text, str) or not text:" + NL
    + "            return ()" + NL
    + "        return governed_dependencies(text, language=language)" + NL,
    "        return ()" + NL,
)

# 变异 B（分支覆盖）：删掉 language != "python" 的守卫，让非 python 文本也走提取。
DROP_LANGUAGE_GUARD = (
    "src/adapters/textfacts.py",
    '    if language != "python":' + NL + "        return ()" + NL,
    "    if False:" + NL + "        return ()" + NL,
)

# 变异 C（保留标记）：不再登记 UNPROVEN_DYNAMIC_IMPORT，让"证明不了"退化成静默放行。
DROP_DYNAMIC_MARKER = (
    "src/adapters/textfacts.py",
    "    if proposal.unproven_dynamic:" + NL + "        names.add(UNPROVEN_DYNAMIC_IMPORT)" + NL,
    "",
)

# 变异 D（共享引擎的相对导入识别）：把 from 形态的正则换回修复前的口径（模块名不允许前导点）。
OLD_FROM_LINE = '    r"^[ \t]*from[ \t]+([A-Za-z_][\w.]*)[ \t]+import[ \t]+([^\n]*)",' + NL
NEW_FROM_LINE = '    r"^[ \t]*from[ \t]+(\.*[A-Za-z_][\w.]*|\.+)[ \t]+import[ \t]+([^\n]*)",' + NL
OLD_FROM_REGEX = ("src/adapters/textfacts.py", NEW_FROM_LINE, OLD_FROM_LINE)
```

### 9.2 四路径期望矩阵（`probe_n1` 的判据）

四条路径：`p2-dsh`（Phase 2 钩子）/ `p6-json`（canonical-json）/ `p6-dsh`（Phase 6 的 dsh 桥）/ `p6-hook`（hook-command）。
`exp` 是该案例的**正确**结论（True = 应当阻断）；每格必须等于 `exp`——"两边相等"不算过。
`*` = 依赖集里出现 `<unproven-dynamic-import>`。

| 案例 | 文本 | exp | 修前（V1 实测） | 修后 |
| --- | --- | --- | --- | --- |
| 1-relative-import | `from . import repository` | True | p2-dsh **BLOCK** / 三条 p6 **allow** | 四路全 BLOCK |
| 2-dynamic-literal | `importlib.import_module("repository")` | True | p2-dsh **BLOCK** / 三条 p6 **allow** | 四路全 BLOCK |
| 3-dynamic-nonliteral | `importlib.import_module(name)` | True | p2-dsh **BLOCK\*** / 三条 p6 **allow**（deps 只有 `importlib`） | 四路全 BLOCK\* |
| 4-dotted-literal | `from shop.order_repository import OrderRepository` | True | 四路全 BLOCK | 四路全 BLOCK |
| 5-allow-control | `from shop.order_service import OrderService` | **False** | 四路全 allow | 四路全 allow |
| 6-unparseable | `def broken(:` | True | 四路全 BLOCK | 四路全 BLOCK |

**5 号是必须放行的对照**：一个把所有输入都判成 block 的探针是"假绿"，不是证据。

### 9.3 清理 `.tmp/` 之后怎么重建"修前的红"

不需要 `pre-fix` 快照——用 §9.1 的规格从**当前树**造变异体即可（A1 已实测，Lead 又复核过一次）：

```text
1) 造变异体（只动副本，不动工作区）：
   make_tree.py --target .tmp/mutant-regressed --mutation revert-wiring
   -> mutated ...\src\adapters\base.py [revert-wiring] / replaced 175 chars with 18 chars
2) 四路径探针跑两份：live（--root .）与变异体（--root .tmp/mutant-regressed）
3) 逐格对照：期望是"变异体上 15 格（3 条 p6 路径 × 5 个应阻断案例）重新变红"
```

`make_tree.py` / `probe_n1.py` / `compare.py` 是会话级仪器，随 `.tmp/` 消失；
上面两步的**语义**已由 `tests/integration/test_dependency_path_consistency.py` 与
`tests/contract/test_dependency_extraction_parity.py` 永久承担（见 §10.3/§10.4）。

---

## 10. Lead 决策记录（2026-09-26）

### 10.1 决策

**否 C（不整批搬迁）；取 A + B 的最小形式。**

1. **不搬任何一件仪器进 `tools/`**（顶层或子目录都不搬）。
2. **只做两处真实覆盖缺口的归位**（已在本次落地，见 §10.4）：
   非 python 门控按文本形态 parametrize；把"点分路径在 Phase 6 路径上的结论"补进 `PARITY_TEXTS`。
3. **方法留档**（§9），使"修前的红"在 `.tmp/` 清理后仍可由 §9.1 的规格重建。

### 10.2 为什么否 C（每条都由 Lead 独立复核，不是采信评估结论）

| # | 事实（复核方式） | 为什么它足以否 C |
| --- | --- | --- |
| 1 | 4/9 仪器把**仓库根**硬编码成 `C:\Users\ZNM\Downloads\Memory`（`assert_diff.py:28`、`ast_equal.py:14`、`tree_hash.py:15`、`make_tree.py:18`）；而 `tools/*.py` 有 21 处用 `__file__` 推根、**0 处**硬编码仓库根（grep 实测） | 搬过去会把"本机路径"写进产品脚本，与 29 个既有脚本的共同形态冲突 |
| 2 | `tools/check_repo_consistency.py:291-295` 只 `glob("*.py")` **顶层**，且属于 `ci_local.ALWAYS_STEPS` 的硬门禁：未登记的 `tools/*.py` 会让门禁红 | 顶层放 = 必须登记（可接受）；**子目录放 = 门禁看不见**——把"没登记会红"降级成"没登记看不见"，正是本仓库这几轮在治的那类病 |
| 3 | `tools/ci_local.py:124-133` 的 `CODE_PREFIXES` 含 `"tools/"` → 任何 `tools/**` 改动选中 **32 步**（实测），只改文档是 9 步 | 一次性仪器的维护成本被永久化 |
| 4 | `diff_probe_reports.py` ≡ `tools/governance_gap_probe.py:2078-2124` 的 `_fingerprint`/`compare_runs`（同一对输入结论逐字相同）；`ruff_scope.py` ≡ `validation/validators.yaml:91` 的 canonical ruff 口径 | 搬进去 = **把"同一语义第二份实现"制度化**，与 R4（一个语义写了四遍）、N1（一个引擎两条路径）同病 |
| 5 | `ruff_scope.py` 对缺失文件 **fail-open**（`in_scope_total=0` + `exit 0`，与"全清白"同形） | 与仓库的失败关闭取向相反；且它用的正是 R8 记过的 `concise` 汇总行口径 |

### 10.3 不搬会失去什么（逐条判定）

| 会失去 | 判定 |
| --- | --- |
| 四路径矩阵的**可执行**形态 | **不失去**：语义由两个 git 跟踪测试承担；本次又补了两处缺口，并用变异证明它们会红（§10.4） |
| N13 的验收输入（`pre-fix` 快照） | **不再有时限压力**：§9.1 的规格让"修前的红"可由当前树重建 |
| 逐文件 ruff 计数 / 全树哈希冻结 | **接受损失**：前者一行 `ruff --output-format=json` 即可；后者约 40 行，真要用时现写 |
| "重构有没有改语义"的可执行工具（全仓 `ast.dump` **0 命中**，唯一真缺口） | **本次不做，登记为 N15**（§10.5） |

### 10.4 本次两项落地的"会失败的检查"证明

不是"加了用例"，而是"证明了用例能红"（变异只改副本，不动工作区）：

| 变异 | 改动前该文件的红 | 改动后 |
| --- | --- | --- |
| `drop-language-guard`（§9.1 变异 B） | 1 条（只有"相对导入"一种形态） | **5 条**（五种应阻断形态各一条） |
| 首段截断（`_from_targets` 只登记首段＝G6 修复前 Phase 2 的口径） | **0 条**（点分路径当时未被覆盖） | **3 条**（Phase 6 dsh / canonical-json / 非 python 各点到该案例） |

第二条是为了证明新用例非空而**临时构造**的等价变异：共享引擎统一之后，"两条路径不一致"打不到它，
能打到它的是"提取结果本身错了"。

### 10.5 本次不做、但已写清规格的事

| 编号 | 事项 | 为什么现在不做 | 要做的形态 |
| --- | --- | --- | --- |
| **N13** | 给 `check_g06` 补 Phase 6 用例 | 它改的是一台**验收仪器**，按本轮口径必须配一次独立验收（"对修前快照必须变红"）；半验证状态下改仪器 = 再造一台假绿仪器 | 见 00 号文档 N13 |
| **N15** | `tools/ast_unchanged.py`（`ast.dump` 等价 + 断言/常量计数） | 唯一"能力在仓库里没有"的一项，但**收益是间歇性的**（下次机械重构才用），**成本是永久的**（README 登记 + 单测 + 每次改动进 32 步门禁）。方法已在 08 号报告与 §9 可读 | 若立项，必须满足 §6 的 9 条验收条件（尤其第 2 条：默认 baseline 不得指向 `.tmp/`） |

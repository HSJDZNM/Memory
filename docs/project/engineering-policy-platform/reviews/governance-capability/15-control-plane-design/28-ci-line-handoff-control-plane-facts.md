# 28 · CI 线交接清单：把「控制面事实表 × 跨源互证」（台阶 5）接成只报告步骤

- **执行**：2026-10-03（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；本轮起点 HEAD = `f2ab7a9`（`git status --porcelain -uall` 空）；
  合并进来的 CI 线提交是 `e5e7c9e`（R-h 接成只报告步骤）。本文与实现**同批提交**。
- **依据**：27 号 §3.1–§3.7（facts 表 / 检查登记表扩字段 / 连接键 / C1·C2·C3 / 新载荷）与 §7（需要 CI 线配合的 5 项）；
  2026-10-03 评审裁定①②③④⑤（写进 27 号 §11 与 23 号 §21）；23 号 §19（R-h 的落地读数）与 **§20.1 第 4 条**
  （授权 CI 会话**在同一提交里**加 `validation/instrument-checks.yaml` 那一行）；
  26 号（同型的交接形状）；AGENTS 第 45（仪器要能失败）、48（读数属于哪棵树）、50（口径诚实）、
  55（加键就是改协议）、56（不适用 ≠ 0 命中）条。
- **本文件是什么**：写给 CI 线的一段**可直接粘贴**的说明（第 1 节）、27 号 §7 五项的逐条现状（第 2 节）、
  验收办法（第 3 节）、归属与边界（第 4 节）、未核实（第 5 节）。
- **本文件不是什么**：不是开工单。`tools/ci_local.py`、`tests/unit/test_ci_local*.py`、
  `tools/phase_evidence.py`、`.github/workflows/*` 属 **CI 线**，控制面重构会话**一个字都没动**，
  也不代写——下面每一项只写「要 CI 线做什么」。

---

## 0 一句话

台阶 5 的只报告部分（`tools/control_plane_facts.py`，载荷版本轴
`CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.0"`）已经落地：它**只报告、退出码恒 0**，
默认输出里那条 `HITS:` 机器行与 `exemption_expiry` / `instrument_self_proof` **同族**，
所以把它接成本机门禁的**只报告步骤**是**加一行数据**——`ci_local.report_only_reading()`
**一个字都不用改**（跨侧契约已由 `tests/unit/test_control_plane_facts.py` 用**真的读取器**钉住）。

---

## 1 可直接贴给 CI 会话的一段

> 下面整段可以原样贴给 CI 会话。第 1 件在 CI 线自己的文件里；第 2 件在控制面会话的文件里，
> 但按 23 号 §20.1 第 4 条**已授权 CI 会话在同一提交里加**（跨文件改一次，不拆两次）。

```text
背景：控制面重构会话已落地台阶 5 的只报告工具 tools/control_plane_facts.py（控制面事实表 × 跨源互证：
facts 表 + 连接键双向必查 + C1 两份测试路径声明的差集 + C2 工具表覆盖关系 + C3 预算不等式两套结论），
退出码恒 0、不改任何 allow / block，载荷版本轴 CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.0"。
现在要把它接成 tools/ci_local.py 的一条**只报告步骤**（不在 workflow 里，非零退出不计入门禁失败）。

要做两件事：

1) tools/ci_local.py 的 REPORT_ONLY_STEPS 末尾加一条（六个字段都必填）：

    ReportOnlyStep(
        name="Control plane facts (report only)",
        args=("tools/control_plane_facts.py",),            # 注意：**不带 --json**
        reason=(
            "控制面事实表 × 跨源互证（台阶 5）：facts 表与检查登记表的连接键双向必查、"
            "C1/C2/C3 三组跨源读数；只报告，非零退出不计入门禁失败（27 号 §3 / §7）"
        ),
        expires_at="2026-12-31",
        adopted="2026-10-03",
        reads="默认输出里的 HITS: 行（不带 --json；退出码恒为 0，命中数只能从这一行读）",
    )

   **为什么必须不带 --json**：ci_local.report_only_reading() 在带 --json 时只认载荷里的 hits 键，
   而本工具的载荷**没有** hits（它不是一个账本）；不带 --json 时它读文本 HITS: 行——本工具的默认输出
   已经给了这一行（HITS: <四格合计> / <四格逐项> / facts=<n> checks=<n>），与 exemption_expiry /
   instrument_self_proof 同族，读取器不需要任何改动。
   今天的期望读数（树 = 加这一行之前）：
     HITS: 114 / fact_without_check=13 check_covers_unknown_fact=0 test_path_declaration=101
     budget_inequality=0 / facts=13 checks=65
   接上**并且**加了下面第 2 件之后，期望读数变成：
     HITS: 101 / fact_without_check=0 check_covers_unknown_fact=0 test_path_declaration=101
     budget_inequality=0 / facts=13 checks=66
   （差的那 13 就是"登记了事实、却还没有任何检查声明覆盖它"——正是第 2 件事要消掉的那一格；
   101 是 C1 的存量不一致，**只报告、本轮不修**。）
   任一格未评（facts 表或登记表读不到）时那行写 unavailable：读取器对"有 HITS: 行但读不出整数"
   照原文给出读数、**不猜**命中数（count 是 None，不是 0）。

2) 在**同一个提交**里给 validation/instrument-checks.yaml 加这一行（该文件属控制面会话，
   按 23 号 §20.1 第 4 条**已授权 CI 会话同批加**）：

    - check_id: "report-only:Control plane facts (report only)"
      owner: control-plane
      command: "python tools/control_plane_facts.py"
      covers: "控制面事实表 × 跨源互证（连接键双向必查 + C1/C2/C3 读数；只报告）"
      covers_facts:
        - "test_paths.platform_patterns"
        - "test_paths.adapter_example"
        - "tool_tables.registry"
        - "tool_tables.manifest.dsh"
        - "tool_tables.manifest.generic_json"
        - "tool_tables.manifest.legacy_post_only"
        - "tool_tables.code.dsh"
        - "tool_tables.approved.registry"
        - "tool_tables.approved.adapters"
        - "budget.hooks_timeout.example"
        - "budget.internal_budget.example"
        - "budget.pre_evidence.example"
        - "budget.dsh_side_limit"
      evidence_level: report
      mutation_id: null
      gap_note: "存量检查，未做变异自证"
      severity: advisory

   **为什么必须同批**（两个方向都要说清）：
   - 加了步骤不加这一行 -> R-h（仪器自证）会把自己报成 no_check_id = 1（**只报告、不阻断**，
     但那就是"新步骤没有被登记"）；
   - 加了这一行不加步骤 -> R-h 会报 check_id_without_object = 1（登记了一个不存在的对象）。
   两个方向都是只报告的红，但**同一个提交**做掉就一个都不会出现。
   covers_facts 引用的 13 个 key 就是 validation/control-plane-facts.yaml 的 13 行（27 号 §3.1 的最小集，
   2026-10-03 裁定③）；加完之后本工具的 fact_without_check 从 13 回到 0。
   这一行**也**让 R-h 的对象清单从 65 变成 66（第 4 族"本机只报告步骤" 3 -> 4），
   而 validation/instrument-checks.yaml 的表头注释里已经写明这一点（不用再改别处）。

3) 用例（tests/unit/test_ci_local*.py，CI 线的文件）：一条"登记 + 读数"用例就够——
   断言这一步在 REPORT_ONLY_STEPS 里、args **不含** --json、reason / expires_at / adopted / reads
   都非空，且 report_only_reading() 从**这个工具的真实默认输出**里读出整数命中数。
   （跨侧读数契约已经由 tests/unit/test_control_plane_facts.py 用真的 ci_local 读取器钉住：
   正常读数是一个整数、表读不到时是 unavailable 且 count 为 None——你这边不必重复造。）

不需要做的（写下来免得去找）：
- **不需要**登记进 workflow 的分组：只报告步骤不在 .github/workflows/*.yml 里，
  unregistered_steps() 看不到它。
- **不需要**给这一步接退出码：台阶 5 处在只报告期（enforced=false / would_exit_code=1 只是**预注册**）。
  升格必须先跑满 N>=1 次且**四格**合计 0 命中（0 命中必须来自至少一次真实读数），
  并且升格那一轮必须先是 warn + 非零退出（与 L5 / R-h 同型）。到期日就是复核点。
- **不需要**动 tools/phase_evidence.py：阶段证据加指针（报告路径 + sha256）是**升格之后**的事。
- **不需要**碰 tools/dsh_sandbox_loop.py 那一步（门禁第 9 步）与任何封条语义。
- **不需要**改 tools/exemption_expiry.py：它读 REPORT_ONLY_STEPS，加完这一步 declared 自动从 8 变 9
  （tests/unit/test_exemption_expiry.py 的断言是 declared >= 4，不会红）。

验收：改完跑
  python tools/ci_local.py --full --python .venv/Scripts/python.exe
把 --timings（或末尾的耗时汇总）与只报告那一行的读数一起贴进 23 号的新一节；**不要只贴退出码**。
在 Windows 上如果 pytest 步报 INTERNALERROR（xdist 的 basetemp 跨进程读不到），那是 23 号 §19.0
记录的环境条件，绕法是给这条命令加一个环境变量 PYTEST_XDIST_AUTO_NUM_WORKERS=0——
**判据与步骤一个都不改**，只是慢一点；用了它就必须在读数处逐次声明（23 号 §20.1 第 6 条）。
```

---

## 2 逐条对照 27 号 §7（五项里现在还剩哪几件）

| # | 27 号 §7 的要求 | 现状与处置 |
| --- | --- | --- |
| 1 | `REPORT_ONLY_STEPS` 加一条 `Control plane facts (report only)` | **要 CI 线做**；模板与期望读数见第 1 节。前置条件（`HITS:` 行）已经由本工具给出，跨侧契约有用例钉住 |
| 2 | 同一提交里给 `validation/instrument-checks.yaml` 加那一行 | **要 CI 线做**（授权见 23 号 §20.1 第 4 条）；那一行的 13 个 `covers_facts` 见第 1 节，逐字可粘 |
| 3 | `tests/unit/test_ci_local*.py` 的登记 / 读数用例 | **要 CI 线做**；跨侧读数契约已由控制面会话覆盖，不必重复造 |
| 4 | 四项"不需要做" | 已在第 1 节写明：不进 workflow 分组 / 不动 `phase_evidence.py` / 不接退出码 / 不碰第 9 步 |
| 5 | Windows 上跑 `--full` 时若用了 `PYTEST_XDIST_AUTO_NUM_WORKERS=0`，必须在读数处声明 | **要 CI 线在读数里写**（23 号 §20.1 第 6 条） |

**今天（接上之前）的三项实测读数**（树 = 本文所在提交，复现命令见第 3 节）：

| 项 | 读数 |
| --- | --- |
| `tools/control_plane_facts.py` | `HITS: 114 / fact_without_check=13 check_covers_unknown_fact=0 test_path_declaration=101 budget_inequality=0 / facts=13 checks=65`；退出码 0 |
| `tools/instrument_self_proof.py` | `HITS: 0 / ... / objects=65 declared=65`；四格 `0/0/0/0`（登记表 `schema_version` 已是 `"2"`） |
| `tools/exemption_expiry.py` | `HITS: 0 / declared=8 due=0 expired=0 unprovable=0` |

---

## 3 验收办法（写给下一位写者）

1. 跑 `python tools/ci_local.py --full --python .venv/Scripts/python.exe`，退出码 0；
2. 贴 `--timings`（或末尾的耗时汇总）与属于这一步的那一行（`REPORT-ONLY:`）；
3. 顺手确认三条联动读数：`tools/exemption_expiry.py` 的 `declared` 从 **8** 变成 **9**；
   `tools/instrument_self_proof.py` 的 `objects` 从 **65** 变成 **66**、四格仍 `0/0/0/0`；
   本工具的 `HITS:` 从 **114** 变成 **101**（`fact_without_check` 13 -> 0）；
4. 把上面几行与耗时贴进 23 号的新一节（**不要只贴退出码**）。

只读复现命令：

```powershell
# 三个读数（都只报告、退出码恒 0）
.venv\Scripts\python.exe tools\control_plane_facts.py
.venv\Scripts\python.exe tools\control_plane_facts.py --json
.venv\Scripts\python.exe tools\instrument_self_proof.py
.venv\Scripts\python.exe tools\exemption_expiry.py

# 连接键两个方向的**影子表**变异自证（真实的 validation/ 一个字都不动）
.venv\Scripts\python.exe -m pytest tests/unit/test_control_plane_facts.py -q
```

---

## 4 归属与边界（谁的文件、本会话没碰什么）

- **控制面重构会话**（本文件作者）：`tools/control_plane_facts.py`、`validation/control-plane-facts.yaml`、
  `tools/instrument_self_proof.py` 的加载器与版本轴、`validation/instrument-checks.yaml` 的**表头与版本号**、
  `tests/unit/test_control_plane_facts.py`、`tests/unit/test_dsh_budget_inequality.py`、
  `tests/unit/test_instrument_self_proof.py`、`src/adapters/dsh/hooks.py`、
  `src/provenance/reading_context.py` 的声明键、`tools/README.md`、`AGENTS.md` 的版本轴表、`docs/**`。
- **CI 线**：`tools/ci_local.py`、`tests/unit/test_ci_local*.py`、`tools/phase_evidence.py`、
  `.github/workflows/*`。本会话对这四个路径的差集是 **0 行**（复现命令：
  `git diff --numstat f2ab7a9..HEAD -- tools/ci_local.py tests/unit/test_ci_local_report_only.py tools/phase_evidence.py .github/workflows`）。
- **登记表的那一行**：`validation/instrument-checks.yaml` 属控制面会话，但**那一行数据**按 23 号 §20.1 第 4 条
  **授权 CI 会话在同一提交里加**；本会话只加了 `schema_version` 与表头两段（属"扩字段"本身）。
- **禁令遵守**：本会话**没有**直接跑过 `tools/dsh_sandbox_loop.py`（只在门禁第 9 步里由门禁自己跑，
  跑前拍快照、跑后逐个文件比对）；没有 `push` / `fetch`；没有改过 `~/.dsh`；
  没有动 `C:\Users\ZNM\Downloads\Memory`。

---

## 5 未核实（逐条）

1. **接上门禁之后的耗时**：本会话只在**门外**跑过本工具——单跑约 **2.1 s**（其中 `probe_wiring` 约 0.55 s、
  `resolve_layer` × 203 个文件约 0.44 s、其余是解释器与 import）。CI 上（没有 dsh 根）通道清点会更快，
  但那是**推断**，不是实测；
2. **GitHub Actions 上的读数**：本会话只在 Windows 本机跑过；CI 上 `HITS` 的具体值与本机**可能不同**
  （C3 的通道事实依赖宿主、C1 的文件数依赖仓库内容）——不要照抄本机的 114/101；
3. **升格判据的轮次记录**：本会话只跑了 **1 次**真读数（`HITS: 114`，四格里两格非 0），
  "跑过 N>=1 次且四格合计 0 命中"离现在还很远；
4. **`inventory_fact.matched` 今天在本机是 `null`**：本机的 4 条通道
  （`dsh:governed` 一族）指向工作区之外的 `hooks.json`（渲染成 `<external>`），
  而仓库内示例 `examples/dsh/hooks.json` **不是**本机的运行时通道——两边的并列关系仍然成立，
  但"哪一条通道与哪个实例对应"在别的机器上是另一份读数；
5. **C2 里 orchestrator 段的对应关系仍未核实**（27 号 §9 第 1 条的延续）：注册表的
  `tool_name`（`edit_file` / `write_file` / `edit_policy` / `write_policy`）
  在 `src/orchestration/tools.py` 里 grep 不到，所以这一组**只给读数、不给判据**；
6. **本工具不写任何台账 / 审计**（它只读），因此"它在门禁里连跑会不会与别的步骤抢 `.tmp`"**未实测**——
  它唯一用到的 `.tmp` 路径是 `tools/instrument_self_proof.py` 的影子索引（那是 R-h 自己的），
  本工具不建影子树、不写盘。

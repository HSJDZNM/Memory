# 26 · CI 线交接清单：把「仪器自证」（R-h）接成只报告步骤

- **执行**：2026-10-03（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；本文写就时的 HEAD = `cc282df`（`git status --porcelain` 空）。
- **依据**：25 号 §6（交接清单）与 §7（方案 A）、23 号 §19（落地读数）；AGENTS 第 45（仪器要能失败）、
  48（读数属于哪棵树）、50（口径诚实）、55（加键就是改协议）、56（账本不存在 = 不适用）条。
- **更正（2026-10-03，依据 23 号 §20.1 第 4 条）**：第 1 节的**第 2 件事**与第 2 节表格的第 1 行改为
  ——**授权 CI 会话在同一提交里加** `validation/instrument-checks.yaml` 那一行（不再「定好 name/args 交给控制面会话加」）；
  `ReportOnlyStep` 模板、期望读数与其余各条**逐字不变**。
- **本文件是什么**：写给 CI 线的一段**可直接粘贴**的说明（第 1 节），加上 25 号 §6 六项的逐条现状（第 2 节）、
  验收办法（第 3 节）、归属声明（第 4 节）与未核实（第 5 节）。
- **本文件不是什么**：不是开工单。`tools/ci_local.py`、`tests/unit/test_ci_local*.py`、
  `tools/phase_evidence.py`、`.github/workflows/*` 属 **CI 线**，控制面重构会话**一个字都没动**，
  也不代写——下面每一项只写「要 CI 线做什么」。

---

## 0 一句话

R-h（`tools/instrument_self_proof.py`）已落地，**只报告、退出码恒 0**；把它接成本机门禁的
**只报告步骤**是**加一行数据**：读数要的 `HITS:` 机器行已经按 `tools/exemption_expiry.py` 的
**同族形状**给出来了，`ci_local.report_only_hits()` **一个字都不用改**。

---

## 1 可直接贴给 CI 会话的一段

> 下面整段可以原样贴给 CI 会话。它只改 **CI 线自己的文件**，并把「要同步的那一行数据」写清楚。

```text
背景：控制面重构会话已落地 R-h「仪器自证」（tools/instrument_self_proof.py，只报告、退出码恒 0，
载荷版本轴 INSTRUMENT_SELF_PROOF_SCHEMA_VERSION = "1.0"，登记表 validation/instrument-checks.yaml）。
现在要把它接成 tools/ci_local.py 的一条**只报告步骤**（不在 workflow 里，非零退出不计入门禁失败）。

要做两件事（第 1 件在 CI 线的文件里，第 2 件在控制面会话的文件里）：

1) tools/ci_local.py 的 REPORT_ONLY_STEPS 末尾加一条（六个字段都必填）：

    ReportOnlyStep(
        name="Instrument self-proof (report only)",
        args=("tools/instrument_self_proof.py",),          # 注意：**不带 --json**
        reason=(
            "仪器自证（R-h）：每条仪器检查都要能证明自己会红；只报告，"
            "非零退出不计入门禁失败（方案 §4 台阶 4 / 25 号 §7 方案 A）"
        ),
        expires_at="2026-12-31",
        adopted="2026-10-03",
        reads="默认输出里的 HITS: 行（不带 --json；退出码恒为 0，命中数只能从这一行读）",
    )

   **为什么必须不带 --json**：ci_local.report_only_reading() 在带 --json 时只认载荷里的 hits 键，
   而本工具的载荷没有 hits（它不是一个账本）；不带 --json 时它读文本 HITS: 行——本工具的默认输出
   已经给了这一行（HITS: <四格合计> / <四格逐项> / objects=<n> declared=<n>），
   与 exemption_expiry 同族，读取器不需要任何改动。
   期望读数：HITS: 0 / no_check_id=0 no_mutation_and_no_gap_note=0 patch_not_applicable=0
   check_id_without_object=0 / objects=64 declared=64
   （对象 64 = 门禁步骤 44 + 探针检查 13 + 封条场景 5 + 只报告步骤 2；加了这一步之后第 4 族是 3、
   objects 是 65，那时要同步登记表 —— 见第 2 件事）。
   任一格未评（登记表读不到 / git 影子树建不出来）时那行写 unavailable：读取器对
   「有 HITS: 行但读不出整数」照原文给出读数、不猜命中数（count 是 None，不是 0）。

2) 同步 validation/instrument-checks.yaml 一行（**这一行原本属控制面会话的文件**；按 2026-10-03 评审
   裁定——23 号 §20.1 第 4 条——**已授权 CI 会话在同一提交里加它**，不必拆成两次改动、也不必把它
   交回控制面会话）：

    - check_id: "report-only:Instrument self-proof (report only)"
      owner: ci-line
      command: "python tools/instrument_self_proof.py"
      covers: "仪器自证读数（对象清单 × 登记表：三态 + 双向比对；只报告）"
      evidence_level: report
      mutation_id: null
      gap_note: "存量检查，未做变异自证"
      severity: advisory

   **为什么必须同步**：R-h 的对象清单第 4 族就是 REPORT_ONLY_STEPS。加了步骤不加这一行，
   仪器自证会把自己报成 no_check_id = 1（HITS: 1，**只报告、不阻断**）——两件事要同一个提交，
   否则中间那次读数就是「新步骤没有被登记」。

3) 用例（tests/unit/test_ci_local*.py，CI 线的文件）：一条注册 + 读数用例就够——
   断言这一步在 REPORT_ONLY_STEPS 里、args 不含 --json、reason / expires_at / adopted / reads
   都非空，且 report_only_reading() 从**这个工具的真实默认输出**里读出 0 命中。
   （跨侧读数契约已经由 tests/unit/test_instrument_self_proof.py 用真的 ci_local 读取器钉住，
   你这边不必重复造。）

不需要做的（写下来免得去找）：
- **不需要**登记进 workflow 的分组：只报告步骤不在 .github/workflows/*.yml 里，
  unregistered_steps() 看不到它（那条检查只查 workflow 步骤）。
- **不需要**给这一步接退出码：R-h 处在只报告期（enforced=false / would_exit_code=1 只是**预注册**）。
  升格必须先跑满 N≥1 次且四格合计 0 命中（0 命中必须来自至少一次真实读数），
  并且升格那一轮必须先是 warn + 非零退出（与 L5 同型）。到期日就是复核点：
  tools/exemption_expiry.py 会把它读出来——**本机今天的读数是 declared=7**，
  加了这一步之后是 8；tests/unit/test_exemption_expiry.py 的断言是 declared >= 4，不会红。
- **不需要**动 tools/phase_evidence.py：阶段证据加指针（报告路径 + sha256）是**升格之后**的事。
- **不需要**碰 tools/dsh_sandbox_loop.py 那一步（门禁第 9 步）与任何封条语义：
  「门禁接封条」（25 号 §6 第 3 条）与 R-h 是**两件事**（25 号 §8 第 6 条）。

验收：改完跑
  python tools/ci_local.py --full --python .venv/Scripts/python.exe
把 --timings（或末尾的耗时汇总）与只报告那一行的读数一起贴进 23 号的新一节；
**不要只贴退出码**（25 号 §6 的交接验收办法）。
在 Windows 上如果 pytest 步报 INTERNALERROR（xdist 的 basetemp 跨进程读不到），
那是 23 号 §19.0 记录的环境条件，绕法是给这条命令加一个环境变量
PYTEST_XDIST_AUTO_NUM_WORKERS=0（让 -n auto 解析成 0 个 worker，进程内跑）——
**判据与步骤一个都不改**，只是慢一点（本机 pytest 步 6m 29s）。
```

---

## 2 逐条对照 25 号 §6（六项里现在还剩哪几件）

| # | 25 号 §6 的要求 | 现状与处置 |
| --- | --- | --- |
| 1 | `REPORT_ONLY_STEPS` 加一条只报告步骤 | **要 CI 线做**；模板与期望读数见第 1 节。前置条件（`HITS:` 行）已由控制面会话在 `6caa330` 补上，`tools/README.md` 与工具 docstring 都写明它是**跨文件契约**。第 1 节第 2 件事的登记表那一行：**授权 CI 会话在同一提交里加**（23 号 §20.1 第 4 条，2026-10-03） |
| 2 | 新步骤登记进某个分组 | **不适用**：`unregistered_steps()` 只查 workflow 里的步骤；只报告步骤不在 workflow 里，`--list` 已经把它单独打成一类（四类中的"本机只报告"） |
| 3 | 门禁接封条（R-e：判据级封条 + 退出码 3） | **不是这一件**（25 号 §8 第 6 条把两者分开）；本交接不涉及，它仍是缺口，待单独一轮 |
| 4 | `.github/workflows/phase-8.yml` 加同名 run 块（要不要在 CI 上也跑） | **可选，本轮不要求**。本工具不需要宿主（dsh / profiles）：在 CI 上它会读出同一份清单与同一张表（`HITS: 0`）。若 CI 线要加，按第 1 节的模板 + **同一提交**里同步登记表那一行 |
| 5 | `tests/unit/test_ci_local*.py` 的登记 / 选择 / 只报告读数用例 | **要 CI 线做**（第 1 节第 3 件事）；跨侧读数契约那一条已由控制面会话的用例覆盖 |
| 6 | `tools/phase_evidence.py` 只加指针（报告路径 + sha256） | **本轮不做**：那是升格之后的动作；现在加会改证据载荷的键集合（第 55 条要升版）而消费方还不存在 |

**另外一件事（写下来，免得被当成"交接漏了"）**：若 CI 线加的是**新的 workflow 步骤**（不是只报告步骤），
对象清单第 1 族会从 44 变多，同样要同步 `validation/instrument-checks.yaml`——
那是**控制面会话的文件**，请把步骤名交给它加（否则仪器自证会报 `no_check_id` 红，只报告、不阻断）。

---

## 3 验收办法（写给下一位写者）

1. 跑 `python tools/ci_local.py --full --python .venv/Scripts/python.exe`，退出码 0；
2. 贴 `--timings`（或末尾的耗时汇总）与属于这一步的那一行（`REPORT-ONLY:`）；
3. 顺手确认 `tools/exemption_expiry.py` 的读数从 `declared=7` 变成 `declared=8`（到期仍是 0 命中）；
4. 把上面两行与耗时贴进 23 号的新一节（**不要只贴退出码**）。

---

## 4 归属与边界（谁的文件、本会话没碰什么）

- **控制面重构会话**（本文件作者）：`tools/instrument_self_proof.py`、
  `validation/instrument-checks.yaml`、`tests/unit/test_instrument_self_proof.py`、
  `src/provenance/reading_context.py` 的声明键、`tools/README.md`、`AGENTS.md` 的版本轴表、`docs/**`。
- **CI 线**：`tools/ci_local.py`、`tests/unit/test_ci_local*.py`、`tools/phase_evidence.py`、
  `.github/workflows/*`。本会话对这四个路径的差集是 **0 行**（复现命令见 23 号 §19.10）。
- **禁令遵守**：本会话**没有**直接跑过 `tools/dsh_sandbox_loop.py`（只在门禁第 9 步里由门禁自己跑，
  跑前拍快照、跑后逐个文件比对，见 23 号 §19.8）；没有 `push` / `fetch`；没有改过 `~/.dsh`；
  没有动 `C:\Users\ZNM\Downloads\Memory`。

---

## 5 未核实（逐条）

1. **接上去之后的门禁耗时**：只报告步骤本身是秒级（读 AST + 64 行表），但本会话**没有**在
   `ci_local` 里真的接上跑过一次——CI 线接完的第一次 `--full` 才是实测；
2. **CI（GitHub Actions）上的读数**：本会话只在 Windows 本机跑过；CI 上 `HITS: 0` 是**推断**
   （同一份仓库 + 同一张表），不是实测；
3. **升格判据的轮次记录**：本会话只跑了 **1 次**真读数（`HITS: 0`，见 23 号 §19.3/§19.7）；
   「N≥1 次且 0 命中」的轮次登记方式仍待评审（25 号 §8 第 5 条）；
4. **`validation/mutations/` 的落点**（25 号 §8 第 4 条）**仍未裁定**：本轮方案 A 没有变异记录，
   工具只在 `mutation_id` 非空时才去读那个目录，所以今天它不存在也不影响读数；
5. **`--hook`（pre-push）形态下这一步也跑**：只报告步骤在 `--hook` 与 `--full` 下都会执行
   （它不是 `FULL_ONLY_STEPS`），但本会话**没有**跑过 `--hook` 形态的实测；
6. **xdist 起不来的成因**：见 23 号 §19.0 的四步实验与 §19.9 第 1 条——绕法有，"谁加的 DENY ACE"未核实。

# 05 · 检查点提交的预检摘要（task-17）

- **来源**：`.tmp/round-15/stage/SCAN.md`（**`A69CAB68994B2C82`**，44073 B）、`EXCLUDE.md`（**`DCE371C0E8C6ACCF`**，5681 B）、
  `stage-list.nul`（**`369F047BCF74BDA5`**，3964 B）、`COMMIT-MSG.txt`（**`CCA0C035B12B971E`**，816 B）
- **摘录日期**：2026-09-28；**来源树**：检查点提交 **`e235626c6b66340bb6a099df3be1adfa0932886e`**（分支 `wip/round-15-baseline`，2026-09-28 20:53:05 +08:00）
- **本文件是什么**：预检结论摘要（我自己复核过的项标注「亲自复核」；只有转述的标「未核实」）。原件在 .tmp。

## 1 检查点事实

| 项 | 读数 | 出处 |
| --- | --- | --- |
| 预检时刻 / HEAD | 2026-09-28T20:50:55+08:00，HEAD `8b0be688a7ec3a9e70fb5c3c04170321e67db999`，分支 `feat/rules-and-os-platform` | SCAN.md:5-6 |
| 非忽略变更条目 | **93**（`git status --porcelain | Measure-Object -Line` = 93；`-z` 解析 93；明文 93 行，三路一致） | SCAN.md:45-46、:74-75 |
| 分类计数 | 已跟踪修改 **65** ＋ 未跟踪 **28**（`-uall` 口径未跟踪 **31**）＝ 93；折叠目录 1 条展开成 4 个文件 | SCAN.md:56-57、:66-72 |
| 删除 / 重命名 | **0** / **0** | SCAN.md:70-71 |
| 建议排除 | **0**（`stage-list.nul` 的 93 条即全部建议暂存） | EXCLUDE.md:10-20 |
| 实际提交内容 | `git show --name-only e235626c` = **96** 个文件（亲自复核） | git（本归档摘录时） |
| 预检的只读保证 | 未执行任何 git 写操作（连 `git add --dry-run` 都没跑） | SCAN.md:7-9 |

## 2 四类风险逐条结论（预检读数）

| 风险类 | 命中 | 结论 |
| --- | --- | --- |
| 凭据 · 文件名模式 | **0** | 未命中 |
| 凭据 · 内容模式 | **2 处 / 2 文件**（`sk-live…` 形态与 `Authorization: Bearer …`），均为**合成值**且带行内 `secret-scan: allow` 理由 | 不排除（它们是"审计链脱敏"与"violation message 脱敏"两条安全测试的被测对象） |
| 凭据 · 高熵串 | **8 处 / 5 文件**，全部是 sha256 摘要或长标识符（4 处 `hex64` 是 approved.json / host-versions.observed.json 的已审核哈希） | 不排除 |
| 大文件 > 1 MB | **0**（最大 `tools/build_learning_notebook.py` = 311,750 B；全变更集 2.61 MB / 96 文件） | 未命中 |
| 机器相关 / 个人路径 | **26 处 / 11 文件**真实本机形态 ＋ 14 处 / 6 文件合成夹具 | 不排除；**其中 1 处登记**（见 §4） |
| 二进制 / 生成物 / 压缩包 / 数据库 / `.tmp` 泄漏 | **0**（`generated=0 binary=0`，无 `__pycache__` 与 `.tmp` 路径段） | 未命中 |
| 附带合规（UTF-8 / LF / 末尾换行 / 行尾空白） | 96/96 合规 | 未命中 |

出处：SCAN.md:16-24（摘要表）、:95-166（凭据）、:168-186（体积）、:188-306（机器路径）、:308-326（生成物）、:327-334（合规）。

## 3 独立凭据扫描（我亲自重跑）

- 命令：`python tools/secret_scan.py`（仓库自带门禁，另一套模式，不是预检自己的脚本）。
- 我的原始输出（2026-09-28 摘录时）：`secret scan: 已扫描 601 个文件（镜像 跳过）` / `没有发现疑似凭据`，**exit 0**。
- 与预检结论一致（SCAN.md:391、EXCLUDE.md:32 都引用了这条；数值以我的重跑为准）。

## 4 「无排除项」的判据与两条登记项

**判据（EXCLUDE.md:24-28）**：排除是一条**有代价**的建议，门槛是「要么泄漏了不该外泄的东西，要么让仓库多背一份不该背的重量，要么换机器就出错」——
三条都不成立才写「无排除项」。逐条对表后：**排除项数量 = 0**（EXCLUDE.md:12-16）。

**登记项 1（机器相关路径，亲自复核原文）**：`tools/governance_gap_probe.py:738-740`
（文件 sha256[:16] **`086508056A8C35C1`**）：

`DSH_IMPL_ASAR = Path("C:/Users/ZNM/AppData/Local/Programs/DeepSeek Harness/resources/app.asar")`
—— 硬编码本机绝对路径，换机器即失效。预检判定**不排除**，理由是它有**显式降级**：
文件不存在时 `_dsh_impl_signature()` 直接返回空事实（:752-753），报告把 `dsh_impl_asar_exists` 记成显式事实，只在存在时才写"修后预期"。
**建议**：改成环境变量或从 `shutil.which("dsh")` 反推；且"实现包不存在"应在报告里显式可见（现在只落在 facts 里，容易被读成检查通过）。

**登记项 2（真实用户名与合成名混用，亲自复核原文）**：`tests/integration/test_dsh_sandbox_loop.py`
（sha256[:16] **`382DFC655C580E28`**）：:54/:56/:58 用真实用户名 `C:\Users\ZNM\…`，而同文件 :49/:60 用合成名 `C:/Users/x/…`。
预检判定**不排除**（它是归因分类器的回归夹具，用的是真机日志原文，AGENTS 第 53 条要求归因在同一条记录内合取）。
**建议**：把 :54/:58 统一成同文件已在用的合成名 `x`。

另有 4 条预检明确**建议保留**（虽然命中风险模式）：两条安全测试的合成密钥、上述探针、以及在案各轮 reviews 记录里的本机路径与 CI 的 `/tmp/`（EXCLUDE.md:44-51）。

## 5 预检自身的两个错误（预检自己留档，SCAN.md:338-379）

1. **`-z` 解析差一个字节**：最初按 `XY`+`PATH` 解析，导致 96 条路径全部被判"磁盘上不存在"；真实形态是 `XY<空格>PATH\0`。
   若照错的解析生成清单，`git add --pathspec-from-file` 会**整条失败、一条都不暂存**（SCAN.md:342-362）。
2. **200 KB 读取上限造成假阳性**：第一版给 `tools/build_learning_notebook.py` 报"末尾无换行"，原因是它按前 200 KB 的缓冲区判末尾；
   全量复检后为空（"仪器缺陷，不是文件缺陷"，SCAN.md:364-379）。
   诚实声明：96 个文件里只有这 1 个超过 200 KB，它的**内容模式扫描只覆盖前 200 KB**；编码/行尾/末尾换行三项用的是全量字节。

## 6 怎么复核

- 原件：`.tmp/round-15/stage/{SCAN.md,EXCLUDE.md,stage-list.nul,COMMIT-MSG.txt}`（**只在 .tmp 里**）；支撑记录在 `_support/`（scan.json、status-z-*.json、entropy-table.md、machine-table.md、prescan.py 等）。
- 提交本身可复核（不依赖 .tmp）：`git show --stat e235626c`、`git show --name-only e235626c | wc -l`、`git log -1 --format=%H wip/round-15-baseline`。
- 凭据结论可复核：`python tools/secret_scan.py`（仓库自带，随时可跑）。
- 两条登记项的原文在 tracked 树里，行号见 §4。
- 本文件**未核实**的项：SCAN.md 内部「四类风险的逐条命中明细（26 处/11 文件、50 个文件的分档表）」我只读了汇总与机器路径表的开头，
  **没有逐条复核每一处命中**；`stage-list.nul` 的 93 条内容我没有逐条比对（只读了计数与格式说明）。

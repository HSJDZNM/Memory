# 01 · 30 臂确定性 Hook 矩阵摘要

- **来源**：`.tmp/round-09/instruments/hook-matrix/hook-matrix.md`（sha256[:16] **`57E4F2B2F57F43FE`**，21477 B）、
  `verify-matrix.md`（**`E87FCFCF289B1CB5`**，28070 B）、`hook-matrix.json`（**`3096B8B35E7B4275`**，388497 B）、
  `verify-matrix.json`（**`5D9084F6A4C71BA7`**，77765 B）
- **摘录日期**：2026-09-28；**来源树**：见 README（检查点 `e235626c`；矩阵本身产出在 09-27 23:31 那棵树，见下）
- **本文件是什么**：结论摘要。**原件不在本目录**，逐条明细（248 条检查的 expected/actual）只在 .tmp 里。

## 1 数字（我 2026-09-28 亲自重算过）

| 项 | 读数 | 出处 |
| --- | --- | --- |
| 臂数 | **30** | hook-matrix.md:15；我自己遍历 hook-matrix.json 的 `arms` = 30 |
| 检查数 | **248** | 同上 |
| 通过臂 | **30/30** | 同上 |
| 偏差（不通过的检查） | **0** | `summary.deviations = []`（注意：在 `summary` 里，不在 JSON 顶层） |
| 仪器自身异常 | **0** | `summary.instrument_errors = []` |
| 规则集事实 | 43 条 / error 24 / warning 19 / style_lint 39 | hook-matrix.md:14（核心加载器读出，不抄常数） |

第二方（`verify-matrix.md`）**用自己的运算符表**重算，不是复述仪器：

| 重算项 | 读数 | 出处 |
| --- | --- | --- |
| 248 条检查逐条重算 | 不一致 **0** 条 | verify-matrix.md:18；`recheck_checks.checks_total=248 / checks_mismatch=0` |
| violations 从 stderr 原文重抠 | 35 步，不一致 **0** | verify-matrix.md:19；`recheck_stderr.steps=35 / stderr_mismatch=0` |
| 自己写真驱动重放 6 条臂 | 6 条臂不一致字段均为 0 | verify-matrix.md:20 |
| 变异证明（AGENTS 第 45 条） | 2 条变异都翻转（allow→block / block→allow） | verify-matrix.md:25-31；`mutations` 2 条 |
| 仪器自报 vs 重算对照 | 「30/30 一致 / 248 条 0 偏差 / 仪器错误 0」 | verify-matrix.md:390-392 |

## 2 它证明什么

1. **Hook 侧判定的确定性**：30 条臂、248 条检查，跨轮重跑 0 偏差；每条臂跑的都是**生产入口**
   （`python -m adapters.dsh.hooks --hooks-config …`），不是库内调用，且每条臂一个独立项目副本、审计互不覆盖（hook-matrix.md:7）。
2. **读数可被推翻**：两条显式变异把 allow 臂翻成 block、把越界臂翻成 allow（verify-matrix.md:25-31）——
   说明这些臂的记录不是恒绿。
3. **仪器自己的修正留痕**：首轮 30 臂跑出 **9 条不一致**，逐条回看后 7 条是**探针期望写错**（改探针、不放宽检查），
   另 2 条是**被测对象口径变了**（P1 修复后 `violations` 字段出现）；全部留在 hook-matrix.md:132-146，
   为的是「第二次是绿的」不被读成「第一次也是绿的」。

## 3 它**不**证明什么（原件自己写的边界，逐条照抄）

- **不覆盖 dsh 真实会话**：本机沙箱禁止 Node 管道 stdio，所以「Hook 的 exit 2 在 dsh 侧被压成 1」这件事不由本矩阵证明；
  本矩阵只证明 Hook 自己给出 exit 2 + verdict 行（hook-matrix.md:155）。
- **不覆盖写会不会真的落盘**：Hook 从不写目标文件，block→文件没被改在本矩阵里是**协议语义**，不是磁盘事实（:156）。
- **不覆盖 Agent 侧绕过**：每条臂都经过 Hook；模型改用别的通道不在覆盖范围内（:157）。
- **不覆盖 pre_evidence 的超时/超预算注入**：只有 45s 预算下的实测耗时（:158）。
- **不覆盖样式规则的全码表**：只压了 E501 / E711 / S602 三个码，其余 36 条由仓库自己的双向 select 契约测试守（:159）。
- **不覆盖 mypy / type_check**：仓库当前没有启用 type_check 规则（:160）。
- **不覆盖跨平台**：全部在 Windows + miniconda python 3.13 上实测（:161）。
- 另有两条「检查通过但读数必须带条件」的口径缺口（:148-151）：
  不声明 `pre_evidence` 时的 allow 必须带条件读（账本自己写着 `skipped_rule_count=42`）；
  以及 Hook 的 allow 只等于「允许 dsh 执行一次」，不等于副作用已发生。

### 3.1 一条本归档新增的边界：**这批读数不覆盖当前树的 `src/policy` 变更**

- 矩阵起跑时刻：`hook-matrix.json` 的 `started_at = 2026-09-27T15:31:00Z`（本机 09-27 23:31）。
- 矩阵**没有记录它测的是哪一版源码**：`environment` 只记 interpreter / python_version / repo / matrix_root / hook_cli，没有 src 修订哈希。
- 当前树（检查点 `e235626c`）里 `src/policy` 已带修复轮的改动：`src/policy/engine.py:154` `pending = bundle.pending_for(checker)`、
  `src/policy/checkers.py:163-169`（`pending_implementation_violation`）、`src/policy/evidence.py:93`（`PENDING_IMPLEMENTATION`）。
- 结论：方案的「248 检查 0 偏差」是**对旧内核**成立的读数。落地前必须在当前树上重采并钉 `pre_tree → post_tree` 摘要——
  这与外部评审意见 §1.1（`控制面重构方案-评审意见.md`，sha256[:16] `EF4FFF7D613EB0E1`）的阻断级结论一致。

## 4 怎么复核

- 原件（.tmp 未被清理时）：读上面四个文件的对应行；重跑见 hook-matrix.md:163-170
  （`$env:PYTHONPATH='src'; python .tmp/governance-full/harness/probe_matrix.py`）——**重跑需要 .tmp 下的仪器与臂脚手架**。
- 只核对数字（不需要重跑）：`python -c "import json;d=json.load(open('.tmp/round-09/instruments/hook-matrix/hook-matrix.json',encoding='utf-8'));print(d['summary'])"`。
- 本文件里我**未核实**的项：无（数字均来自我自己的重算或原件行；原件行号已标）。

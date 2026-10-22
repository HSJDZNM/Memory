# 2026-10-22 题库 k≥3 · 可开跑签核（使用者）

> **性质**：§5.3 的「可开跑」签核读数（Lead 准备、使用者签）。**不是** 27 run 的读数，也不是 treatment 结论。
> 起点 HEAD `730a175` + 修复提交 afb0835 / 8f2cc43 / e6af4ac / fb1d7e0；不 push、不跑 27 run（签后才跑）。
> **判据来源**：`readings/2026-10-22-bank-k3-deliberations.md` §3.2/§3.4/§3.7；
> `readings/2026-10-22-bank-k3-h1-override.md`；`testing/ab/bank/README.md` §4.8；05 §8 第 11 条。

## 0 一句话

H1 改判允许的 **7 条定点修已落地**；三题 hidden/PLAN/scoring/README 已重算，**3 份新 freeze `--check --strict` PASS**；
参考树 T 为 **38/38、39/39、33/33**（两次 stdout 逐字节相同）；**第三人逐条复核完成**（7/7 在授权范围内；
crossmodule 剩余 flag=1，≤2）。**新 freeze 的 1 臂 re-smoke 已完成**（exit 0 / `invalid=[]` / 500 条；
见 `readings/2026-10-22-bank-k3-resmoke-v2.md`）；`ci_local --full` 已在 **danger-full-access** 下 PASS
（30 步，7m13.1s，未设 shim/basetemp）。现在只差使用者签「可开跑」，签后按 §4 跑 27 run。

## 1 签核对象（3 份新 freeze + 审批）

| 题 | 新 freeze `combined_digest` | entries | T total | hidden PLAN / runner sha256 |
| --- | --- | --- | --- | --- |
| bank-async-concurrency | `sha256:87a8bbf5e3110fcc2fb26062288d52a3d150c46d79ad27c6a4a935b3c5c71fd6` | 120 | 38 | `599da13a…` / `ecaf9738…` |
| bank-docs-config | `sha256:9e507374ba9bb77ec6b583fa516279561ec5e20f969273cb9620a81fe3f848e7` | 119 | 39 | `769030ca…` / `b7ec0e64…` |
| bank-crossmodule-refactor | `sha256:4e8e4bcf55e5b2264417b1a022bd71e76b5f96d4a0dbeb74e86ebf13dbd0d35a` | 119 | 33 | `58ec4132…` / `5bd879f5…` |

- 三份 freeze 均由 `freeze_manifest.py --write` 生成、`--check --strict` 复核（PASS）；`ignore` 增加
  `**/.tmp/**`（一次性构建残留；旧 freeze 的 120/119/119 条里也没有 `.tmp` 条目；**ACL 残留目录未删除**）。
- A 臂 `approval.json` sha256：`282b4925908ca1f378056cb28d647eea71d85e9c371a4c547876ccbbc8c45782`（2 条）；
- B 臂 `approval.json` sha256：`3c697d97c58476f2e3db6d557d1e4dd57e02f0e37c92ac4c0fa05839b91d47ab`（2 条）；
- 审批 TTL：**2026-10-29T12:38Z**（+08 20:38）；返工不改臂配置，审批不重签；27 run 窗口跨过该时刻或改臂配置 → 先重签（批内重签 = 换代际）。
- Gate 0：**通过**（async/docs 激活 2/3；crossmodule 负对照无激活；migration 无激活）——
  `readings/2026-10-22-bank-k3-gate0-rerun.md`。

## 2 本批修复与重测

### 2.1 7 条定点修（唯一允许的 hidden 改动）

| 题 | 修复 | 结果 |
| --- | --- | --- |
| async | I5：断言代理放宽为「含 `已弃用`」 | fixed；T 仍 38 |
| async | EN5：正文扫描只对 `# ` / `## ` 结束（`###` 子标题不算 section 结束） | fixed；T 仍 38 |
| docs | I5：测试函数计数含 `ClassDef` 内 `test_*` 方法 | fixed；T 仍 39（40→39 由删除 I7 造成） |
| docs | 删除 I7（loader 不 import `shop` 无契约出处） | deleted；T 40→39 |
| crossmodule | T20：controller import 集合改为「不含 `shop.order_repository`」的负列表 | fixed；T 仍 33（34→33 由删除 T21 造成） |
| crossmodule | T26：迁移示例接受三反引号与波浪线围栏 | fixed（原 flag）；残余「缩进代码块」窄误伤 =1（cross 总 1，≤2） |
| crossmodule | 删除 T21（单文件 pytest 无契约出处） | deleted；T 34→33 |

- 规则文本不变：本改判只覆盖本批 7 条，不修订阈值；结论只写「固定 hidden 件（新 hash）下的臂间对比」。
- 第三人复核（reviewer-k3，只读）：**7/7 均在 override 授权范围内**；6 条完全消解；T26 仍留 1 条窄误伤
  （CommonMark 缩进代码块），crossmodule 剩余 flag=**1**（把 EN4 边界计入为 2）——**≤2，override 不失效**。
  复核读数：`readings/2026-10-22-bank-k3-h1-rereview.md`（Lead 落盘，引用复核者原文结论）。

### 2.2 重测读数（参考树 / 基线；两次逐字节相同）

| 题 | 参考树 T | 参考树 stdout sha256 | 基线 T | 基线 stdout sha256 |
| --- | --- | --- | --- | --- |
| async | **38/38**，exit 0 | `acf67b9950f1641c77db5f349de7cecfa49fa0f76d393e6a723d7933dded80f5` | **2/38**，exit 1 | `a6294c63da6b3149532a602a39bb4737bf9d29ca8f0b4b6723eb1b444881f47d` |
| docs | **39/39**，exit 0 | `6b55369d9b51ec8c93ebf9bb1bd73252f6b1ff7f7778b8a6d989fa990aa599d4` | **2/39**，exit 1 | `c4ab7fb77a6f0b8fde1b17af5a6b53c0becd0fc56f05ba78b9f69eb48fba620f` |
| crossmodule | **33/33**，exit 0 | `3a0d46b5e9c0a6ed875ecbbb5a927cd6067b348ebb0ce38c00ca454467e573ba` | **4/33**，exit 1 | `f32db9c4a011dbab25293e8c5ebe032da1fb5165721c50fb23e04fbba63f2064` |

- 基线树 = 各题 `<task>/baseline`；参考树 = `<task>/reference/tree`；cwd = 仓库根。
- **环境注**：早先 workspace-write 下，本机 Python 3.13.11/Windows 的 `os.mkdir(0o700)` 会生成当前受限令牌
  不可读的显式 ACL，pytest `tmp_path` 因此报 WinError 5（docs 原生 38/39，仅 EN1 红）；当时用
  `DSH_PYTEST_MODE_SHIM=1` 复现。切到 **danger-full-access** 后已**不设 shim/basetemp** 复跑两遍全部六棵树，
  sha/计数与上表逐字一致（含 async 基线 `a6294c63…`、docs ref `6b55369d…`）；签名环境不依赖该 shim。
- scoring：docs `total=39` / 39 个 `case_ids`；crossmodule `total=33` / 33 个；async 38/38；
  `case_ids` 与 runner `CASE_IDS` 逐项相等；`frozen_inputs` 两个 hidden 摘要与实算一致。
- 9 树 scaffold：A/B/C 全部 `--check` PASS（files 20/19/19 与 C 16/15/15；placeholders=0）；
  A/B 树内 `.policy/approval.json` 各 2 条、sha256 与上表一致；C 无审批。
- dry-run（async A，新 freeze）：freeze/arm-tree/dsh 0.2.1-rc.2/sandbox danger-full-access 全绿；
  凭据未注入时唯一 blocker 是 `missing_credential`；注入后 PREFLIGHT ok。
- 门禁：`ci_local --full` **PASS**（30 步，**7m13.1s**；**danger-full-access**，未设 shim/basetemp）。为让树摘要可读，
  把 4 个嵌套 `.tmp` ACL 残留目录整体移到 `.tmp/k3/acl-residue/`（**未删除、未改 ACL**；根 `.tmp` 已被代码排除）。

### 2.3 1 臂 re-smoke（新 freeze；不计入 k）

**已执行（新 freeze `87a8bbf5…`）**：exit 0 / timeout=false / `invalid=[]`；500 条读数
（audit 277 / ledger 189 / batch 34），17 proposal ↔ 17 settle（15 allowed / 2 blocked），墙钟 **576.923 s**；
五条判据见 `readings/2026-10-22-bank-k3-resmoke-v2.md`。A 臂 M1 `tools/notify_smoke.py` 首写 `policy_block`
（批次 settle=blocked）；模型后来在测试上下文齐备后重试 allowed，最终树 21 文件（created 6 / changed 4 / unchanged 11）。
任务完成不是 T 读数；n=1、1 臂、1 题，不写 treatment。

## 3 H2 盲抽计划

- 3 题各抽 **2 个改动/新增测试文件**（新增优先），由**不知道臂分配**的复核者执行；写
  `run-record.bypass_sampling`（`bypass.items[B2]` / `human_items[H2]`）。
- 抽样检查：AST/断言计数、可疑形态（`assert True`、空函数、`if False`、try 吞 assert、skip/xfail）、
  抽跑、对 `acceptance.md` A1–A10 的定性对照；不评分，只判「未发现削弱 / 发现削弱 / 跑不成」。
- H2 不是签名项；它是 27 run 后的复核动作。

## 4 27 run 计划（签后执行）

- **结构**：3 题 × 3 臂 × 3 block = 27；题序 **对照 → async → docs-config**；块内臂序 **ABC / BCA / CAB**；
  **串行**；每 run 一个父目录，不复用脏树；不 push。
- **每 run 核对**：exit / `invalid=[]` / freeze `--check --strict` / host 0.2.1-rc.2 / 首消息 sha /
  树 diff / A/B 审计 >0 / C 审计 =0 / batch / post；记录字段缺失 = 该 run 作废。
- **审批 TTL**：覆盖到 2026-10-29T12:38Z；若窗口跨过或改臂配置，先重签（批内重签 = 换代际，
  前后 run 不可合并）。
- **结论上限**：n=3 只写原值/方向计数/机制；不写均值/区间/显著；treatment 结论须过预注册。

## 5 签名

open_run_signed_by: （待签）
open_run_signed_at: （待签）

- 签名范围：3 个 task id + 上述 3 份 freeze 摘要 + A/B 审批 sha + TTL + Gate 0 + H1 改判 + H2 计划 + 27 run 计划。
- 签名方式：使用者执行 `.tmp/k3/sign-open-run.ps1`，或回复「我签可开跑」由 Lead 落。
- **不表示**：treatment 有效、hidden 独立出题、T 满分等于契约全满足、C 满分等于 30/30。

## 6 预存不一致与 errata（不在本批 7 条范围）

1. **README §3 的 `task-package/interfaces.md` 行（预存错误，HEAD 也错）**：
   async README 写 `9e11ef39…`，实算 **`14e67c2e6ff86a3393aad90a5ff7428fe2215ea652b8bff56080b90e2183a9d9`**；
   docs README 写 `6e3a42f7…`，实算 **`58b1d405c8eaa0ba47ad86ba353ddc6711e62bd0866689c201781d72832343c1`**。
   `task-package/manifest.sha256` 内的值是正确的；这两行是文档抄写错误。它们位于 freeze 根内，
   本批**不改字节**（避免在 7 条以外扩范围），以 manifest 为准；下次重冻时修。
2. **`command_families_sha256`（预存，6 题共有）**：三题 scoring 写 `6943e988…`，当前
   `bank/COMMAND-FAMILIES.md` 实算 **`d55f079fd41efa969c895b0b0d1c0d4d73d187d01be49d0531f1584a63a93344`**；
   该文件不在 freeze 根内。记为 open item，不在本批改 scoring 数值。
3. **旧读数**：`run-ready-request` / 旧 `resmoke` / `lead-frozen-by` 里的旧 freeze 与旧 scoring 摘要已由 override
   声明作废；本读数集中写新值，旧文件保留为历史，不逐个改写。

## 7 边界

- 旧读数（旧 freeze `7caf8825…` / `bba785a8…` / `da07a934…`、旧 T 40/40 与 34/34、旧 1 臂 re-smoke）作废或只作历史；
  本批只在新 hidden 件与新 freeze 下比较。
- 改判只覆盖本批 7 条 flag；若重审 crossmodule 仍 >2 flag，改判自动失效，转「完整重出 crossmodule hidden」。
- 本读数不是 27 run 结果；27 run 的失败按失败关闭记录，不记 pass。

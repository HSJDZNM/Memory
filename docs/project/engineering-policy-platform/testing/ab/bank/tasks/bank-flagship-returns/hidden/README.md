# 隐藏验收 runner（bank-flagship-returns）

单文件自包含：`hidden/runner.py` 实现 `hidden/PLAN.md` 的 **48 条**（T01–T38 + EN1–EN5 + I1–I5）。
入口只有一个，本目录不放别的用例文件。

## 怎么跑

```powershell
$env:BANK_TASK_TREE = '<被评树>'
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-flagship-returns/hidden/runner.py
```

- 树只从环境变量取（相对路径按 cwd 解析）；stdout 是唯一载荷（UTF-8）：
  `{schema_version, tree, cases[], summary{passed,total}}`，`cases` 顺序固定 T01..T38, EN1..EN5, I1..I5；
- 退出码：**全过 0 / 有失败 1 / 跑不成 2**。2 = 「判不了」（缺 `BANK_TASK_TREE`、树不存在、
  用例集合不完整、树复制不出来），**不是 0 分**；原因写在 stderr 一行。

## 48 条分组

| 组 | 条目 | 覆盖 |
| --- | --- | --- |
| 记录模型 | T01–T05 | 8 键形状、副本、往返、6 种非法输入、idempotency_key 类型 |
| 策略 | T06–T10 | 基线值、5 种非法策略、整数夹逼、资格边界、坏 YAML 且字节不变 |
| 仓储 | T11–T14 | 内存/JSONL、副本、by_order、2 种坏行 |
| 服务 | T15–T20 | 正常路径、未知订单、3 种坏金额、幂等 id、列表过滤、注入与 AST |
| 控制器 | T21–T24 | 转发参数与返回值、AST 负例、构造器只收 service |
| 演示 | T25–T27 | 退出码与 2 条记录、两次逐字节相同、改 config 传导 |
| 迁移 | T28–T32 | MIGRATED 3、3 条 v2 记录、删了再跑字节相同、3 种坏输入不替换、LF/尾换行/键有序 |
| 文档 | T33–T34 | `docs/refund.md` 5 个二级标题、README 8 条字面路径 |
| 树形状 | T35–T38 | 11 冻结文件逐字节 + 改动 ⊆ 19 允许写、文件集 ⊆ 30、pytest 全绿且收集 ≥10、无 skip/xfail |
| 入口/接口 | EN1–EN5, I1–I5 | pytest / demo / demo 形状 / migrate / 收集数；`RefundRecord`、`RefundService`、`RefundController` 的签名与行为 |

**反向用例**（断言「期望失败/拒绝」，不是「跑成 = 通过」）：T04/T05/T07/T14/T16/T17/T31/T35/T38。

## 只读与确定性

- 被评树**一个字节都不写**：pytest / demo / migrate 与模块导入都在树的副本里跑（临时目录，退出时删）；
  进程内 `sys.dont_write_bytecode = True`，子进程 `PYTHONDONTWRITEBYTECODE=1` 与
  `-p no:cacheprovider`；子进程超时 60 秒，解释器 = 运行 runner 的 `sys.executable`；
- 临时目录优先 `<cwd>/.tmp`，其次树旁 `.tmp`，最后系统 temp，且**绝不落在被评树内**；
  每个候选都真写一次才算可用（受限沙箱里 `mkdtemp` 的 0700 目录不可用，故自建 0755 根）；
- 载荷无时戳 / run id / 绝对路径；树标签 = 相对**调用 cwd** 的路径（正式读数从仓库根调用，标签即
  仓库相对路径；换 cwd 会换标签，这是唯一随调用形态变的字段）。`sort_keys`、无随机、无时钟，
  同一 cwd + 同一棵树两次运行逐字节相同。树形状常数在 runner 内写死：14 个基线 sha256（其中 11 个冻结）、16 个新建路径，
  来源是包内 `baseline/` 实算（组合摘要 `b6d6d2f7…`），运行时不读 baseline。

## 已知边界与偏离

- **T05 的落点**：PLAN 只说「`1` 被拒」，没写发生在构造期还是 `from_dict`；本 runner 断言在
  **构造期**（`RefundRecord(..., idempotency_key=1)` 抛 `ValueError`），与 frozen dataclass 的
  `__post_init__` 校验一致；`from_dict` 的类型拒绝另由 T04 覆盖。
- **T21/T22 的「参数逐字」**：按替身 service 的真实签名绑定后比较（位置/关键字都算逐字），只拒绝
  「改顺序、改名、多传、少传、丢返回值」。
- **本宿主的环境事实（受限沙箱时期）**：`workspace-write` 会话里 0700 目录被拒（`mkdtemp`、pytest 的
  `tmp_path` 都会踩到），所以 runner 自带 0755 临时根、参考解测试不用 `tmp_path`；`danger-full-access`
  下 `tmp_path` 可用（2026-10-21 实测参考树 29 passed），这条限制不影响本轮 48/48 读数。被测树若在
  受限沙箱下依赖 `tmp_path`，EN1/T37 可能红——那是环境限制，不是判据放宽。

## 作者独立性

本文件与 `runner.py` 由**未参与任务设计/实施**的子会话按冻结的 `PLAN.md` 写成：**没有读**
`reference/README.md` 或任何参考实现/实施 diff，只读了 `PLAN.md`、`task-package/`、`baseline/`、
`layers.yaml`、`interfaces.yaml` 与 `bank/README.md`；48 条先写成，参考解后写。

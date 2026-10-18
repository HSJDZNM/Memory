# 2026-10-19 本机门禁读数（05/06 去噪收口）

> 起点：HEAD bbd45c2 + 4 个未提交文件（05/06/README + 新增 `readings/2026-10-19-D-gate2-treatment.md`）。
> 用途：`06-plan-progress.md` 的 R-A-GATE-04 的证据落点（`.tmp` 日志是一次性产物，不能长期复核）。

## 1 门禁读数

| 项 | 读数 |
| --- | --- |
| 命令 | `.venv\Scripts\python.exe tools/ci_local.py`（26 正常步骤 + 4 只报告） |
| 结果 | **25/26 ok**；失败 1 步 = `Unit, contract, integration and security tests`（exit 3） |
| 文档类步骤 | 全绿：Text conventions（707 文件 0 问题）、Repository consistency、Secret scan、notebooks 同步/执行（首轮 52.5s ok） |
| 其余步骤 | 全绿（Rule set self-check / AST replay / validator 闭环 / wiring / registry / enforcement / API / Phase 8 证据等） |

## 2 pytest 步骤为什么记「跑不成」

- 直接原因：`.tmp/tmp/pytest-of-ZNM/pytest-NN/.lock` `PermissionError: [Errno 13]`——pytest 建编号临时目录时被拒。
- 与 `06` 的 D-20261018-04 同因（本机 `.tmp` 下 pytest 临时目录的 ACL/沙箱限制）；本会话尝试把临时根换到 `.tmp/pytest-root` 后，新目录仍**不可被枚举**（`os.scandir` → WinError 5），不是「换个路径就好」。
- 不是代码失败：同一次运行里前 3 步与 4–15 步、17–26 步全绿；单进程全量套件另跑（`-n0`、TEMP 指平台 temp）为 **3024 passed / 6 skipped / 22 errors**，22 个 error 全部是同一个 PermissionError（fixture setup 阶段）。

## 3 第二轮 notebook 步骤 rc=1 的归因

- 该步骤执行期间有并行编辑改动了 `docs/project/engineering-policy-platform/04-open-work.md`，命中它的「工作区出现未预期改动」守卫；不是文档或代码错误。
- 首轮同一步骤（无并行编辑）为 ok（52.5s）。

## 4 与 R-A-GATE-03 的关系

- R-A-GATE-03 在 HEAD 98169bf 上为 **26/26**。本次改动为纯文档（05/06/README + 一份新读数），不触碰代码、规则与配置；pytest 结论按等价对待，环境差异单列，不记成通过。

## 5 复现命令

```text
.venv/Scripts/python.exe tools/ci_local.py
.venv/Scripts/python.exe -m pytest tests/unit tests/contract tests/integration tests/security -q -n0
```

- 第二条命令需把 TEMP/TMP 指向平台临时目录（仓库内 `.tmp` 的编号临时目录在本机会话里建不出/不可枚举）。

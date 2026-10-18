# 2026-10-18 本机门禁全绿读数（阶段 A 收口）

> 读数对象：git HEAD f11e9af 的**干净 worktree**（`.tmp/gate-head`，与主工作树同树、无未提交改动）。
> 为什么用 worktree：会话沙箱对 `.tmp/tmp/pytest-of-ZNM` 曾有 Windows 文件权限拒绝（04 号 5.72 与 06 D-20261018-04 记录过），修复权限后在干净树上复跑，排除旧工作区残留。
> 本文件是 06 的记录落点（06 第 4 节：读数文件不得指向 `.tmp`）；`.tmp/gate-head` 与其中的日志会被 cleanup 删除。

## 1 环境前提（构造）

| 项 | 值 |
| --- | --- |
| 修复对象 | `C:\Users\ZNM\Downloads\Memory\.tmp\tmp\pytest-of-ZNM`（pytest 基临时目录） |
| 修复命令 | `icacls <dir> /reset /T /C` → exit 0；`takeown /f <dir> /r /d y` → exit 0；`icacls <dir> /reset /T /C` → exit 0 |
| 验证 | `Get-ChildItem <dir>` → enumerable（修复前 WinError 5） |
| 旧 `pytest-cache-files-*` | 121 个陈旧目录已删除（`.tmp` 内构建产物，可重建） |

修复只改 Windows 文件权限与删除临时缓存，**未改任何仓库文件**。

## 2 命令与结论

```
Set-Location .tmp/gate-head            # git worktree add .tmp/gate-head f11e9af
C:/Users/ZNM/Downloads/Memory/.venv/Scripts/python.exe tools/ci_local.py
```

| 项 | 读数 |
| --- | --- |
| 退出码 | **0**（`本机检查全部通过（26 步）`） |
| 正常步骤 | 26/26 ok；本机跳过 9 步、登记豁免 2 步、只报告 4 步 |
| 全量测试 | 1 步 5m 22.6s，rc=0（unit + contract + integration + security） |
| 阶段验收证据 | 17.5s，rc=0（复用同一批 pytest 报告） |
| 只报告步骤 | Obligations 0 命中；Exemption 0 命中；Instrument self-proof 0 命中（objects=65 declared=65）；Control plane facts 106 命中（既有 C1 存量 + C4 四格：row_without_mode=0 / mode_without_check=0 / tool_with_hits_without_row=not_applicable / registry_digest_drift=0，coverage_rows=13、references=0、facts=14、checks=65） |
| 总耗时 | 8m 12.7s（30 步） |

## 3 与 06 的关系

- 推翻/更正的旧记录：D-20261018-04（「本机门禁全量 pytest 在会话沙箱内跑不成」）的**阻断已解除**，更正记录见 06 D-20261018-05。
- 旧记录 R-A-A1-07 的证据指针曾指向 `.tmp/ci-local-logs/`（违反 06 第 4 节），以本文件与 D-20261018-05 为准。
- 门禁绿**不等于**阶段 A 完成：A3 仍因构造缺口（B-1..B-6）判「跑不成」，阶段 D 不开跑；A3 解冻包见 `testing/ab/2026-10-18-A3-unblock.md`。

## 4 不可复现边界

`.tmp/gate-head` 与日志会被 cleanup 删除；本文件保留了结论与命令，但**逐条日志原文不再可读**。
要复核请重跑上面两条命令（需要同样的权限修复；不修复时 pytest 会以 WinError 5 在 basetemp 扫描处失败）。

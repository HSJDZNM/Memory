# A3 v2 任务包（A3-T1「订单审计台账」· 冻结）

> **用途**：A3 干跑第二轮的**冻结构造**（2026-10-18 修复裁定 A-1/A-10）。它不是产品功能，是阶段 A/D 的验收数据：
> 任务树 = `examples/dsh/b-plan/sample-project` 的 11 文件 + 预置的 `tools/audit_demo.py` = **12 文件**；
> 允许写 **7 路径**；保留 F2 命令族（运行已有 demo 脚本）。
> 裁定与四数判据：`docs/project/engineering-policy-platform/readings/2026-10-18-A3-fix-adjudication.md` §4。

## 1 文件

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.txt` | `b4d70b3859f45d4fe97b86e0566cb0eb97f03b79d7e988ead62b02b01bff4d5f`（3796 B / 33 行，UTF-8/LF/单尾换行） |
| `task-package/interfaces.md` | `02c2f8818ddee173dc74082240163e73e39f2d562bb5e733018eb89871606d1d` |
| `task-package/acceptance.md` | `457897eed052246e67954a13ca7f0f2cf37bf6fb28fb51cb32ed9aeca5df6e21` |
| `task-package/allowed-writes.txt` | `af2ee864a36ec6168c5d0034b1cb641f13c748a428cae5a0cae65ec797d524b4` |
| `task-package/milestones.md` | `77808c1ec84e85213626ae50024be24d1f01bcf8e86bc65d4e7e3a2d96967b6d` |
| `task-package/manifest.sha256` | `0ac1efddbdbd51bb33735f2ceb52471e4a1cba68c7af5b11447df0a73e22c865`（覆盖前 5 文件） |
| `scaffold/tools/audit_demo.py` | `44e7e726fac7ecd2f44e67904c3d2d160b01d66b5046ed5bfc7c96b6a68c775f` |
| `reset-arm.py` | 见提交（Lead 运行前可再算） |

12 文件基线 manifest：`eb481089e1b852375b738d8c7e071ea99508db6a4fba8bec9f70aa34dc368893`（由 `reset-arm.py` 打印/写入 `.tmp/a3b2/reset-manifest.json`）。

## 2 怎么用（Lead）

```powershell
cd C:/Users/ZNM/Downloads/Memory
# 0) 前置：.tmp/a3b/task-project/.policy 里要有用户签的 approval.json 与 registry 对（v1 同一份）
.venv/Scripts/python.exe examples/dsh/b-plan/a3-task-v2/reset-arm.py --dry-run   # 只看计划
.venv/Scripts/python.exe examples/dsh/b-plan/a3-task-v2/reset-arm.py            # 重置 + 校验 12/12 + 冻结基线

# 1) 记下 audit 起始行数（measure_all 的 --start-line），然后以任务树根为 cwd 起受治会话：
cd .tmp/a3b/task-project; $env:PYTHONPATH='C:/Users/ZNM/Downloads/Memory/src'; $env:PYTHONIOENCODING='utf-8'
$task = Get-Content -Raw -Encoding utf8 C:/Users/ZNM/Downloads/Memory/examples/dsh/b-plan/a3-task-v2/task-package/first-message.txt
# 首消息 sha256 必须等于 b4d70b38…（manifest 里也有）
dsh --profile headless --patch .policy/patch.yml $task
```

启动若被 `workspace-write` 文件沙箱拒绝（写 `~/.dsh/profiles/headless/cordis.yml` EPERM），按裁定 A-4 对**同一条启动命令**做一次性 `danger-full-access` 授权，并在 run-manifest 记 `launcher_sandbox=danger-full-access` + 跑后哈希复核。

## 3 边界

- **`tools/audit_demo.py` 是脚手架，不是任务要写的文件**：平台目前无法在 `pre_evidence` 下新建 `tools/**` 的 python 文件（TESTING-002 `uncovered_checker`；缺口 04 5.75，canary 常红）。v2 预置它、任务只运行，F2 族因此保留；**不要**把它加进允许写集合。
- 任务完成判定（A1–A7）用包内 `acceptance.md` + 隐藏用例；A8 用树 diff 对 `allowed-writes.txt`。
- 这是任务数据，不是平台规则；改它 = 改构造，必须按 05 §8 记录并重新冻结 run-manifest。

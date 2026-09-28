# 控制面重构 · 开工状态与前置清单

> 写于 2026-09-28 23:xx +08:00，只读核对：`git` 只读命令、`.tmp/` 文件时间戳、`.tmp/push-run.log`。未跑门禁，未改源码。
> 方案：[../../../designs/控制面重构方案.md](../../../designs/控制面重构方案.md)（v2）。

## 1 基线（已就绪）

| 项 | 读数 |
| --- | --- |
| 分支 | `feat/rules-and-os-platform` @ `f6b9b79`，与 `origin` 0/0 |
| 工作树 | `git status --porcelain` 为空；单一工作树；无 stash |
| 源码 | `b9d3b11..f6b9b79` 只改 `docs/`，源码树 = `b9d3b11` = 检查点 `checkpoint/round-15` 的源码 |
| 门禁 | 拆分后 `--full` 33/33；推送时 pre-push `--hook` 放行（`1873 passed, 1 skipped`，`.tmp/push-run.log`） |
| `main` | `1494d09`，落后 `feat`，按约定最后快进 |

## 2 开工前必须完成（按顺序）

| # | 事项 | 判据 | 出处 |
| --- | --- | --- | --- |
| P1 | **台阶 −2**：新建 worktree（如 `../Memory-refactor`，分支 `refactor/control-plane` 从 `f6b9b79` 开） | 新树里门禁能起：用 `CI_LOCAL_PYTHON` 指向主树 `.venv`，或重建 venv；确认 `.git/hooks/pre-push` 写死了主树路径（`C:/Users/ZNM/Downloads/Memory/...`），新树推送时跑的是**主树**的 `ci_local.py` | 方案 §4 台阶 −2 |
| P2 | **保住 `.tmp` 原件**：在 P3 完成前不跑 `tools/cleanup.py` | `.tmp/round-09/`、`.tmp/round-10/`、`.tmp/round-15/` 仍在 | 归档 README「只在 .tmp 还在时可复核」 |
| P3 | **台阶 −1 ②**：在基线树上重跑 30 臂矩阵（`.tmp/round-09/harness/probe_matrix.py`）与 11 个 fixture | 偏差 = 0 且 fixture 逐字段全等，写出两棵树的摘要；不成立 → 回诊断，不进台阶 0 | 方案 §4 台阶 −1 |
| P4 | 可选：`git tag round-15/superseded-661fd56 661fd56`，避免 gc 后 task-21 记录无法复现 | —— | 收口记录 §7.2 |

## 3 需要使用者先定的决策

- **D-1（台阶 3 前必须定）**：`pending` 是否继续作 warning 级 violation。采纳台阶 3 = 修订 AGENTS 第 51 条，且必须与台阶 3 同批提交（方案 §10 #1）。
- **D-2（台阶 4 前必须定）**：台阶 4–5 按 §3.6 先交两份整数清单（`out_of_scope` / 在范围内），评估前不排期。

## 4 建议的首个改码台阶

**台阶 1（H4）**：`src/validators/adapters/pytest_runner.py:263-265` 在 pytest 退出码 5（未收集到用例）时返回 `ValidatorStatus.OK`，经 `src/validators/pipeline.py` 进入 `served`，结果是零个测试执行却判通过。
不依赖任何新结构，单独提交、单独回退。先交 R-d 字段级差集，再改；判据 R-f。
之后顺序：台阶 0（封条与针脚）→ 2 → 3（需 D-1）→ 4/5（需 D-2）。

## 5 写者纪律

- 同一时刻只有一个写者会话；评审方只读，对照提交 sha 复核，不对照工作区。
- 每个台阶一个（或一组）提交，信息里写台阶号与红→绿判据读数。
- 按路径暂存，不用 `git add .`；不用 `--no-verify`；已推送内容用 `revert` 回退，不强推。

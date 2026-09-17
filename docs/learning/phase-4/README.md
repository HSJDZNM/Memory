# Phase 4 学习手册：怎么用、怎么维护

## 这是什么

Phase 4（Tool Enforcement，受控执行）的可执行讲解。回答四个问题：

| 小节 | 问题 |
| --- | --- |
| 0-2 | 工具注册表里有什么，为什么“改注册表就要重新审核” |
| 3-4 | 一次工具调用怎样变成 Action Request，链路由哪些端口组成 |
| 5-8 | 哪些情况会被阻断，允许路径要过什么，执行与验证各拿到什么证据 |
| 9-14 | 高风险审批、参数绑定、回滚、幂等、审计链与命令行退出码 |

对象清单与关系另有 `note.md`：先读它建立地图，再读 `walkthrough.ipynb` 看每一步实际跑出来什么样。

## 怎么跑

```powershell
# 方式一：Jupyter（需要本机有 Jupyter）
jupyter lab docs/learning/phase-4/walkthrough.ipynb

# 方式二：纯 Python（同内容，逐段打印）
python docs/learning/phase-4/walkthrough.py

# 方式三：不想装 Jupyter，只想确认它没坏
python tools/run_notebook_in_kernel.py docs/learning/phase-4/walkthrough.ipynb
```

前置条件只有一个：仓库根目录下能读到 `registry/tool-registry.yaml` 与
`registry/tool-registry.approved.json`。notebook 自己会在 `.tmp/learning/phase-4-<uuid>/` 下
建立受控工作区、审计链与台账，**不需要预先跑任何命令**，跑完用 `python tools/cleanup.py` 清理。

两点刻意的取舍：

- 手册**不执行** `exec.pwsh` / `exec.bash`：不同机器（尤其是 CI）不一定有可执行的 pwsh / bash，
  所以仓库注册表里的命令类工具只做“阻断路径”的演示；
- 进程类动作另建一条学习用的工具（`learning.python`，写在临时注册表里），
  shell 前缀取当前解释器 `sys.executable`，Windows / Linux 都能真的执行出退出码。

## 它实际验证了什么

生成器会在两个工作目录（仓库根目录、手册目录）各执行一遍全部代码单元，并核对：

- 注册表：6 条工具、全部已审核、`identity` 与已审核清单里的 `registry_digest` 一致；
- 注册表漂移：只改 `notes` 审核哈希不变；改 `rate_limit.max_calls` 哈希变化且工具**不可用**；
  重新审核（`approve_registry` + `write_approved`）之后恢复可用；
- 接口面：未声明的参数得到 `param_unknown`、越界路径得到 `path_out_of_scope`，都发生在构造请求时；
- 阻断：八条前置检查的原因码 —— `tool_not_registered`、`schema_not_approved`、`principal_required`、
  `permission_denied`、`command_not_allowlisted`、`command_composition_blocked`、`approval_required`、
  `policy_timeout`；
- 允许：13 项检查齐全（含命令白名单与组合片段两道），`grant` 与 `action_hash` 绑定、
  单次使用、有效期落在 (0, 60] 秒内；
  CLI 的 `precheck` 是 dry run（`dry_run: true`、`grant: null`，不认领、不执行）；
- 次数：block 路径驱动调用 **0** 次、allow 路径恰好 **1** 次；重放与复用请求不再调用驱动；
- 证据：`content_matches` / `file_changed` / `file_syntax` / `diff_recorded` 四条验证器结论 +
  前后哈希 + diff 摘要，并用 `baseline_recorded` 区分“没有基线”与“基线说原本不存在”；
- 进程：退出码 0 → `validated`；退出码 3 → `repair_required`；缺审批 / 越权审批分别得到
  `approval_required` / `approval_invalid`；没有回滚能力的结论显式写成 `unsupported`；
- 回滚：语法错误 → `file_snapshot` 回滚 `applied`、终态 `rolled_back`、文件哈希回到执行前；
- 审计：链完整 → 改一个字段 / 删一条记录都能被 `verify()` 发现 → 还原后再次完整；
- 参数绑定：改一个字符后 `action_hash` 与 `param_digest` 都变，旧 grant 校验失败，
  执行器给 `refused / grant_invalid`，且没有第二次驱动调用；
- CLI 退出码：`0 0 0 0 0 0 1 1 2`（含“dry-run 的 precheck 不认领 action_id，
  同一个请求随后仍然能真的执行”与“第二次 execute 得到 `action_replay`”这两条）。

任何一条对不上，`python tools/build_learning_notebook.py` 就会失败——手册里的结论不会悄悄过期。

## 怎么维护

手册内容**不是手写的 notebook**，而是 `tools/build_learning_notebook.py` 里的
`PHASE_4_CELLS` 与 `check_phase_4_structure`（外加一组“文档里写过的字段名”常量）：

```powershell
# 改内容 -> 重新生成（会写 walkthrough.ipynb / walkthrough.py 并逐单元执行校验）
python tools/build_learning_notebook.py --phase phase-4

# 只校验当前文件与生成器是否一致（CI 用这条）
python tools/build_learning_notebook.py --check

# 结构校验（不依赖 nbformat）
python tools/check_notebook.py docs/learning/phase-4/walkthrough.ipynb
```

不要直接编辑 `.ipynb`：下一次生成会覆盖它，而且 JSON diff 无法评审。

## 常见问题

**Q：跑的时候报“注册表不存在”？**
A：notebook 是从 `registry/tool-registry.yaml` 反推仓库根目录的，请确认你在仓库里跑，
或者让当前工作目录位于仓库之内（它自己会向上找）。

**Q：为什么手册里没有真的执行 `exec.pwsh`？**
A：命令类工具的 shell 前缀是数据，而不同机器上不一定有 `pwsh` / `bash`。为了不把“环境缺失”
当成“治理结论”，手册只在阻断路径上演示命令白名单，随后用一条 shell 前缀为当前解释器的学习工具
演示进程类退出码。想验证真实注册表里的命令工具，跑
`python -m enforcement.cli self-check`（缺 shell 时会给出 warning）。

**Q：为什么手册里多了一份临时注册表（`drift-registry.yaml` / `learning-registry.yaml`）？**
A：为了演示“注册表是数据”和“新增工具必须重新审核”，同时**不修改仓库真实注册表**。
两份文件都写在 `.tmp/` 下，走的是同一条生产代码路径（`load_registry` / `approve_registry`）。

**Q：手册会不会改到仓库里的真实文件？**
A：不会。受控工作区是 `.tmp/learning/phase-4-<uuid>/workspace/`，审计链与台账在同一目录；
手册打印的“文件哈希”指的都是那个工作区里的 `src/shop/order_controller.py`。

**Q：我改了 `registry/tool-registry.yaml`，手册失败了怎么办？**
A：这正是它在做的工作。改了注册表就重新审核
（`python -m enforcement.cli registry --approve --reviewer <name>`），
再跑 `python tools/build_learning_notebook.py --phase phase-4`；
如果行为是有意变化的，就同步更新 `check_phase_4_structure` 里的期望值，并把变化写进阶段记录。

**Q：单元 5 里 `git status --short` 明明在白名单里，为什么还是被拦住？**
A：白名单只回答“这条命令能不能执行”。`exec.pwsh` 是高风险工具，还要求绑定 `action_hash` 的
人工审批，所以首个失败检查是 `approval`，原因码 `approval_required`。

**Q：`action_id_reuse` 和 `action_replay` 有什么区别？**
A：`action_replay` 是“同一个 action、同一套参数”再来一次；`action_id_reuse` 是“这个 action_id
曾被允许/执行过，但这次的参数不一样”。两者都会被阻断，而且台账里的 `claim` 与审计链上的
`pre_decision` / `execution` / `post_evidence` / `final_decision` 都带 `action_hash`，
所以两个原因码能分开；历史记录里**没有** `action_hash` 时按“未知来源”处理，不会退化成“就是这次这个动作”。

**Q：手册里的时间戳每次都不同，这正常吗？**
A：正常。`action_hash` 不含时间字段（否则同一动作每次构造都会变），但 `created_at` / `issued_at`
是真实时间；结构校验只断言“有效期在 (0, 60] 秒内”，不比对具体时刻。

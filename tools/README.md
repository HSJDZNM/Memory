# 仓库脚本

这些脚本只服务仓库本身的开发流程，不属于 Policy Platform 运行时。

| 脚本 | 用途 | 典型命令 |
| --- | --- | --- |
| `check_text_conventions.py` | 检查 UTF-8 / LF / 行尾空白 / 结尾换行（默认跳过第三方文档镜像，`--all` 连镜像一起查） | `python tools/check_text_conventions.py` |
| `cleanup.py` | 删除 `.tmp/`、`__pycache__/`、`.pytest_cache/`、`.uv-cache/`；**与门禁互斥**：门禁（`ci_local.py`）跑着时拒绝清理——真要删就先取同一把 `.tmp/ci-local.lock`，抢不到就报出持锁者 pid 与起始时间后退出 1、一项都不删；`.tmp/` 只删子项，锁文件本身永不删除（`--dry-run` 只读、不取锁） | `python tools/cleanup.py --dry-run` |
| `phase_evidence.py` | 生成阶段验收证据（规则集哈希 + 协议版本 + Agent 适配器契约 + 沙箱闭环 + 检索语料/索引/评测基线 + 受控执行注册表与闭环结论 + 验证器注册表/规则覆盖/闭环结论 + 多 Agent 支持矩阵/协议版本/闭环结论 + 测试结果 + 性能基线）；`--suite-reports <xml>` 复用 pytest 刚写出的 junit 报告而不重跑套件（报告缺失/缺套件/早于最新源码改动则退回真跑），`test_suite_source` 写明结论依据 | `python tools/phase_evidence.py`；`python tools/phase_evidence.py --suite-reports .tmp/artifacts/tests-all-report.xml` |
| `policy_bench.py` | 固定种子生成 10/100/1000 条规则的匹配性能基线（测试与证据共用） | `python tools/policy_bench.py` |
| `retrieval_eval.py` | Phase 3 固定评测集基线：FTS5（门槛决定退出码）与向量检索（对照记录）在同一数据集上的对比，结论写到 `.tmp/artifacts/phase-3-retrieval-baseline.json` | `python tools/retrieval_eval.py --method both` |
| `dsh_sandbox_loop.py` | 在受控临时项目里重放 Phase 2 的真实 dsh 闭环（bad 编辑被阻断 / good 编辑放行），结论写给阶段证据；两类**环境跳过**（退出码 0，并写出 reason 与复现命令）：没有 dsh / **Hook 起不来且理由是沙箱禁止管道 stdio**（插件理由里的 `spawn 报错：spawn EPERM`），以及 dsh 自身起不来（`dsh_startup_denied`；按**被拒路径**分两类：`profile_write_denied` = 写 `$DSH_HOME` 下 profile 被拒；`other_path_denied` = 被拒的是 dsh 启动临时区，例如系统 temp 的 `mkdtemp`，reason 里写出路径与 syscall；归不了因时**不产生跳过**，按失败收场；诊断字段 `dsh_startup_denied_home_roots` 逐条带来源 `dsh_startup_denied_home_root_evidence`——`env:DSH_HOME` / `default:$HOME/.dsh` / `log:file-url` / `log:plain-path`，`file://` 栈帧与普通路径**分开解析**，畸形候选（`e:///…`、丢盘符片段）按写明规则丢弃）；**“Hook 起不来”不等于“环境不允许”**：理由里写「工作目录不存在 / 不是目录」（projectDir 配错）时按**真失败**收场（载荷 `hook_spawn_denied_kind=hook_workdir_unusable`、`hook_spawn_denied_workdir`），理由既不是沙箱也不是工作目录时同样按真失败收场（`hook_spawn_unattributable`）；三类的判据（`hook_spawn_failure()`）与原文证据一起写进载荷与 reason）；**第三类：配置失败**（有名字、按**真失败**收场、退出码 1）：dsh 在启动期拒绝「Windows ACL 临时根落在工作区内」（`acl_temp_root_inside_workspace`，原文 `Windows ACL temp root must be outside the workspace: workspace=<…>; temp=<…>`，出自 dsh 的 `assertTempRootOutsideWorkspace()`），载荷写 `dsh_config_failure_kind` / `dsh_config_failure_evidence`，reason 写明**改成什么形态就能过**；三类证据同时出现时**配置失败优先**（它是我们自己能改的那一件）。`--isolated-home` **只改 dsh 子进程的 env**：`DSH_HOME` → `.tmp/phase-2-sandbox/dsh-home`、`TEMP`/`TMP` → `.tmp/phase-2-sandbox/dsh-tmp`（本进程与仓库其它部分不受影响，不给开关时行为一字不变）；两个隔离根与受控项目 `demo-shop` **平级**——dsh 的 ACL 沙箱要求临时根在工作区之外，把隔离根放进项目里就是上一条配置失败。结论载荷带自己的版本轴 `schema_version`（现为 `"1.2"`；1.0 是**追认**的、第 13 轮之前的形状，1.1 是第 19 轮形状，见 AGENTS 第 55 条），并带一份 `reading_context`（台阶 4 的统一形状：哪棵树 / 哪个环境 / 哪一套声明；其中 `host.sandbox ∈ {restricted, unrestricted, unknown}` 是 2026-09-30 裁定① 的落点——**不单独设状态轴**）。这条旁注的作用是让 `.tmp/artifacts/` 下那份被 pre-push 钩子覆盖的 `skipped` 产物**自己说得出"这不是这棵树上的真机读数"**（受限宿主上写工作区之外被拒得到 `restricted`；真的跑完得到 `unrestricted`；什么都没取到是 `unknown`——**它不是"没有沙箱"**） | `python tools/dsh_sandbox_loop.py` |
| `governance_gap_probe.py` | 治量覆盖缺口的确定性探针：13 项（G01–G13）各一条断言，每项同时声明**修前/修后**两套预期，只走公开入口（hook CLI / enforcement CLI / adapters CLI / 插件源码静态事实 / 审计与台账真实内容）；`--repeat N` 连跑并比对逐项结论（探针必须是纯函数），每次运行用唯一 `run-<run_id>` 目录避免台账残留把本次变成 `event_replay`；**G06 对同一批用例跑两条路径**（Phase 2 钩子 + Phase 6 规范事件），并有变异体证红 | `python tools/governance_gap_probe.py --root . --phase after --repeat 2` |
| `enforcement_loop.py` | Phase 4 受控执行闭环：允许执行一次 / 重放阻断 / 事后验证失败回滚 / 高风险默认阻断 / trace 可重放，结论写给阶段证据 | `python tools/enforcement_loop.py` |
| `agent_loop.py` | Phase 6 多 Agent 闭环：同语义事件在每个 Adapter 上得到同一结论 / 允许恰好执行一次 / 能力不足失败关闭 / 跨 Agent 命名空间隔离 / trace 来源可验证 / 循环熔断，结论写给阶段证据 | `python tools/agent_loop.py` |
| `api_loop.py` | Phase 7 Policy API 闭环：本地引擎与 HTTP API 决定整份相等 / 两个协议消费者等价 / 超时与不可达都不返回 allow / 幂等重放与冲突 / 跨租户隔离 / readiness 反映真实依赖 / 观测日志可对外锚定 | `python tools/api_loop.py` |
| `orchestration_loop.py` | Phase 8 编排闭环：在受控工作区里跑通编排工作流并重放失败 / 恢复路径，结论写到 `.tmp/artifacts/phase-8-orchestration-result.json` | `python tools/orchestration_loop.py` |
| `validator_loop.py` | Phase 5 验证器闭环：ARCH-001 由 AST 证据判定 / 动态 import 与语法错误失败关闭 / 缺工具失败关闭 / 测试选择与失败 / 证据可重放 / 工具版本与配置可追溯 | `python tools/validator_loop.py` |
| `provenance_loop.py` | 控制面封条（针脚）闭环：R-e 的五个场景——真判据 + 真声明跑成 pass / 运行期未声明的写者 → external_write 退 3 / 声明命中不到任何文件 → unprovable 退 3 / 空壳声明给不出判据级封条 → unprovable 退 3 / 仪器自证（把比对换成恒 pass 的替身，同一个场景不再报红）；读数写到 `.tmp/artifacts/provenance-loop-result.json` | `python tools/provenance_loop.py` |
| `obligations_gate.py` | 台阶 3c 的义务账门禁（**L5 试用期：warn + 非零退出，不阻断**；2026-09-30 起登记为 `ci_local.py` 的**只报告步骤**——本机门禁会跑它并打印命中数，**非零退出不计入门禁失败**）：读义务账本给出 `obligations_open` / 已解除条数 / 最近一次真实 pytest 运行 / 树摘要；命中 = 有未结义务，或"声称 0 却没有真实运行"这种没有依据的读数；**账本文件不存在 = 不适用**（`applicable=false`，不算命中、也**不算一次真实读数**，凑不了升格判据里的"0 命中"；报告载荷版本 `REPORT_SCHEMA_VERSION` 1.0 → 1.1）；账本路径存在但不是文件、或协议不认识的账本退出 2。升格判据 = 跑过 N≥1 次且 0 命中（0 命中必须来自至少一次真实读数） | `python tools/obligations_gate.py --ledger .tmp/obligations/repo.jsonl` |
| `exemption_expiry.py` | 豁免到期检查（**只报告**：退出码恒为 0，不改任何 allow / block）：读 `adapters/wiring-scope.yaml` 的边界声明与 `ci_local.py` 的 `REPORT_ONLY_STEPS`，**到期前 14 天提醒（`DUE`）、过期标红（`RED`）**；读不到写 `unprovable`，绝不把它读成"没有到期日"。它是 `ci_local` 的第二条只报告步骤。**默认输出有一行稳定的机器行**：`HITS: <已过期条数> / declared=<n> due=<n> expired=<n> unprovable=<n>`——`hits` **只数已过期**，`DUE`（提醒）与 `unprovable`（读不到）另列、**都不计入命中**；原来的 `counts:` 行原样保留。这一行是**跨文件契约**：`ci_local.py` 的 `report_only_hits()` 在读不到 `--json` 时读的就是它（`REPORT_ONLY_STEPS` 里这一步的 args 不带 `--json`），所以格式必须稳定，改它要同时改两侧。`--json` 载荷**没有版本轴**（已登记：第一次改键时引入 1.1，见 AGENTS 第 55 条） | `python tools/exemption_expiry.py`（`--json` / `--today` / `--scope`） |
| `build_learning_notebook.py` | 生成学习手册 notebook 与纯 Python 版，并逐单元执行校验 | `python tools/build_learning_notebook.py` |
| `phase6_cells.py` | Phase 6 学习手册的单元内容（被 `build_learning_notebook.py` 引用）；改手册内容改这里，然后运行 `python tools/build_learning_notebook.py --phase phase-6` | `python tools/build_learning_notebook.py --phase phase-6` |
| `phase7_cells.py` | Phase 7 学习手册的单元内容（被 `build_learning_notebook.py` 引用）；改手册内容改这里，然后运行 `python tools/build_learning_notebook.py --phase phase-7` | `python tools/build_learning_notebook.py --phase phase-7` |
| `phase8_cells.py` | Phase 8 学习手册的 notebook 单元内容（被 `build_learning_notebook.py` 引用）；改手册内容改这里，然后运行 `python tools/build_learning_notebook.py --phase phase-8` | `python tools/build_learning_notebook.py --phase phase-8` |
| `check_notebook.py` | 校验 `.ipynb` 结构与代码单元语法（不依赖 nbformat） | `python tools/check_notebook.py docs/project/learning/*.ipynb` |
| `check_arch_canon.py` | 检查 `docs/project/architecture` 的图 / 文 / 口径表是否**三处同口径**，以及图的节点包含关系是否成立（对应 README 的"三处同改"硬规则） | `python tools/check_arch_canon.py` |
| `check_arch_style.py` | 检查 `docs/project/architecture` 的文风是否失衡：概括句 >45 字、长句（>90 字）占比 >1/3、单行 ≥8 个标识符、连续无标点 >60 字、图上标签缺两层写法 | `python tools/check_arch_style.py` |
| `run_notebook_in_kernel.py` | 在**真实 Jupyter 内核**里跑一遍 notebook，逐单元报告耗时与错误 | `python tools/run_notebook_in_kernel.py docs/project/learning/phase-0/walkthrough.ipynb` |
| `lock_requirements.py` | 从 pip 报告生成 `requirements.lock` | 见脚本模块说明 |
| `check_repo_consistency.py` | 仓库一致性门禁：依赖锁（requirements.in / pyproject.toml / requirements.lock 三者一致且锁版本满足区间）、文档与配置（workflow 引用、uv.lock 是否存在、testpaths 与测试目录）、工具清单 | `python tools/check_repo_consistency.py` |
| `ci_local.py` | 在本机按 CI 的顺序跑同一批检查：从 workflow 读出步骤，按"这次改了什么"选范围，bash-only 的步骤显式跳过并说明原因；`.venv` 不可用时可显式覆盖解释器；**同一工作树同时只允许一个实例真正执行**：排他锁落在 `.tmp/ci-local.lock`，第二个实例报出持锁者 pid 与起始时间后立刻退出 1（`--hook` 下即阻断推送），进程死掉锁由操作系统释放、不会留陈旧锁；默认每步只在控制台打一行（进度 / 结论 / 耗时），步骤自己的输出写进 `.tmp/ci-local-logs/<序号>-<步骤名>.log`（每次先清空），失败步骤打日志最后 40 行并给出全文路径，`--verbose` 恢复原样滚动；最后打印最慢 5 步的耗时汇总（`--hook` 只在开头打一行"运行中"，成功时保持安静），`--timings` 另写全量的 `.tmp/ci-local-timings.json` | `python tools/ci_local.py`（`--full` / `--list` / `--hook` / `--verbose` / `--timings` / `--python <path>`） |
| `install_hooks.py` | 安装 / 卸载 pre-push 钩子（调用 `ci_local.py --hook`，红了阻断推送；`git push --no-verify` 可跳过） | `python tools/install_hooks.py` |
| `secret_scan.py` | 凭据扫描门禁：扫仓库自有文本文件里的确定形态凭据（与 `enforcement/audit.py` 共用一份模式定义），默认跳过逐字复制上游的离线镜像 | `python tools/secret_scan.py` |

## 门禁退出码（控制面重构方案 §5.3 · 2026-09-30 写进数据）

这一张表说的是**门禁判据**的退出码语义。它写在这里 = 写进数据：不要在脚本里各写一套
（台阶 4 的"写声明"5 条之一，本轮只写声明、不建机制）。

| 码 | 含义 |
| --- | --- |
| `0` | 全部判据 pass 且封条一致 |
| `1` | 判据 fail（含反退化与差集非空） |
| `2` | **用法错误**（保留给 CLI 惯例，与 Hook 的 `block` 无关） |
| `3` | **封条失效**：`external_write`（`pre ≠ post`）或 `unprovable` |

- **不与 Hook 的退出码复用**：Hook 的 `exit 2` 是**阻断**（AGENTS 第 10 条）；
  这里的 `2` 只是"命令行用错了"，两套语义各自成文。
- **编排器自己的退出码**（`tools/ci_local.py`）：`0` = 全部步骤通过；
  `1` = 有步骤失败 / 拿不到排他锁 / workflow 里有未登记的步骤；
  `2` = argparse 的用法错误。**它不返回 3**——`3` 由封条命令
  （`python -m provenance.cli seal …`）给出，见 `src/provenance/cli.py` 的模块 docstring。
- **只报告步骤**（`ci_local.py` 的 `REPORT_ONLY_STEPS`，见下）的非零退出**不改变**上面的结论：
  它们只打印命中读数。
- **门禁步骤表**（本机跑什么）由 `python tools/ci_local.py --list` 给出，分四类：
  会跑（workflow 步骤，红了即退出 1）、本机跳过（bash-only，CI 上执行）、
  登记豁免（`NOT_RUN_ON_HOST`，装环境类）、**只报告**（`REPORT_ONLY_STEPS`，带到期日）。
  四类都必须逐条打印出来——"哪一步没跑"必须是一个能读到的结论，不是沉默。

## 不属于本项目的脚本

`mirror_docs.py`、`learn_site.py`、`pep_site.py`、`dora_site.py`、`owasp_cheatsheets/` 是**离线文档镜像**流水线，
与本项目代码无关，不要混入 Phase 相关的改动。

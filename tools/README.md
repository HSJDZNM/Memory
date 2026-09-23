# 仓库脚本

这些脚本只服务仓库本身的开发流程，不属于 Policy Platform 运行时。

| 脚本 | 用途 | 典型命令 |
| --- | --- | --- |
| `check_text_conventions.py` | 检查 UTF-8 / LF / 行尾空白 / 结尾换行（默认跳过第三方文档镜像，`--all` 连镜像一起查） | `python tools/check_text_conventions.py` |
| `cleanup.py` | 删除 `.tmp/`、`__pycache__/`、`.pytest_cache/`、`.uv-cache/` | `python tools/cleanup.py --dry-run` |
| `phase_evidence.py` | 生成阶段验收证据（规则集哈希 + 协议版本 + Agent 适配器契约 + 沙箱闭环 + 检索语料/索引/评测基线 + 受控执行注册表与闭环结论 + 验证器注册表/规则覆盖/闭环结论 + 多 Agent 支持矩阵/协议版本/闭环结论 + 测试结果 + 性能基线） | `python tools/phase_evidence.py` |
| `policy_bench.py` | 固定种子生成 10/100/1000 条规则的匹配性能基线（测试与证据共用） | `python tools/policy_bench.py` |
| `retrieval_eval.py` | Phase 3 固定评测集基线：FTS5（门槛决定退出码）与向量检索（对照记录）在同一数据集上的对比，结论写到 `.tmp/artifacts/phase-3-retrieval-baseline.json` | `python tools/retrieval_eval.py --method both` |
| `dsh_sandbox_loop.py` | 在受控临时项目里重放 Phase 2 的真实 dsh 闭环（bad 编辑被阻断 / good 编辑放行），结论写给阶段证据；没有 dsh、或沙箱禁止管道 stdio 导致 Hook 起不来（spawn EPERM）时按**环境跳过**（退出码 0，并写出 reason 与复现命令） | `python tools/dsh_sandbox_loop.py` |
| `enforcement_loop.py` | Phase 4 受控执行闭环：允许执行一次 / 重放阻断 / 事后验证失败回滚 / 高风险默认阻断 / trace 可重放，结论写给阶段证据 | `python tools/enforcement_loop.py` |
| `agent_loop.py` | Phase 6 多 Agent 闭环：同语义事件在每个 Adapter 上得到同一结论 / 允许恰好执行一次 / 能力不足失败关闭 / 跨 Agent 命名空间隔离 / trace 来源可验证 / 循环熔断，结论写给阶段证据 | `python tools/agent_loop.py` |
| `api_loop.py` | Phase 7 Policy API 闭环：本地引擎与 HTTP API 决定整份相等 / 两个协议消费者等价 / 超时与不可达都不返回 allow / 幂等重放与冲突 / 跨租户隔离 / readiness 反映真实依赖 / 观测日志可对外锚定 | `python tools/api_loop.py` |
| `orchestration_loop.py` | Phase 8 编排闭环：在受控工作区里跑通编排工作流并重放失败 / 恢复路径，结论写到 `.tmp/artifacts/phase-8-orchestration-result.json` | `python tools/orchestration_loop.py` |
| `validator_loop.py` | Phase 5 验证器闭环：ARCH-001 由 AST 证据判定 / 动态 import 与语法错误失败关闭 / 缺工具失败关闭 / 测试选择与失败 / 证据可重放 / 工具版本与配置可追溯 | `python tools/validator_loop.py` |
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
| `ci_local.py` | 在本机按 CI 的顺序跑同一批检查：从 workflow 读出步骤，按"这次改了什么"选范围，bash-only 的步骤显式跳过并说明原因；`.venv` 不可用时可显式覆盖解释器 | `python tools/ci_local.py`（`--full` / `--list` / `--hook` / `--python <path>`） |
| `install_hooks.py` | 安装 / 卸载 pre-push 钩子（调用 `ci_local.py --hook`，红了阻断推送；`git push --no-verify` 可跳过） | `python tools/install_hooks.py` |
| `secret_scan.py` | 凭据扫描门禁：扫仓库自有文本文件里的确定形态凭据（与 `enforcement/audit.py` 共用一份模式定义），默认跳过逐字复制上游的离线镜像 | `python tools/secret_scan.py` |

## 不属于本项目的脚本

`mirror_docs.py`、`learn_site.py`、`pep_site.py`、`dora_site.py`、`owasp_cheatsheets/` 是**离线文档镜像**流水线，
与本项目代码无关，不要混入 Phase 相关的改动。

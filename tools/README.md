# 仓库脚本

这些脚本只服务仓库本身的开发流程，不属于 Policy Platform 运行时。

| 脚本 | 用途 | 典型命令 |
| --- | --- | --- |
| `check_text_conventions.py` | 检查 UTF-8 / LF / 行尾空白 / 结尾换行（默认跳过第三方文档镜像，`--all` 连镜像一起查） | `python tools/check_text_conventions.py` |
| `cleanup.py` | 删除 `.tmp/`、`__pycache__/`、`.pytest_cache/`、`.uv-cache/` | `python tools/cleanup.py --dry-run` |
| `phase_evidence.py` | 生成阶段验收证据（规则集哈希 + 协议版本 + Agent 适配器契约 + 沙箱闭环 + 检索语料/索引/评测基线 + 受控执行注册表与闭环结论 + 测试结果 + 性能基线） | `python tools/phase_evidence.py` |
| `policy_bench.py` | 固定种子生成 10/100/1000 条规则的匹配性能基线（测试与证据共用） | `python tools/policy_bench.py` |
| `retrieval_eval.py` | Phase 3 固定评测集基线：FTS5（门槛决定退出码）与向量检索（对照记录）在同一数据集上的对比，结论写到 `.tmp/artifacts/phase-3-retrieval-baseline.json` | `python tools/retrieval_eval.py --method both` |
| `dsh_sandbox_loop.py` | 在受控临时项目里重放 Phase 2 的真实 dsh 闭环（bad 编辑被阻断 / good 编辑放行），结论写给阶段证据；没有 dsh 的环境自动跳过 | `python tools/dsh_sandbox_loop.py` |
| `enforcement_loop.py` | Phase 4 受控执行闭环：允许执行一次 / 重放阻断 / 事后验证失败回滚 / 高风险默认阻断 / trace 可重放，结论写给阶段证据 | `python tools/enforcement_loop.py` |
| `build_learning_notebook.py` | 生成学习手册 notebook 与纯 Python 版，并逐单元执行校验 | `python tools/build_learning_notebook.py` |
| `check_notebook.py` | 校验 `.ipynb` 结构与代码单元语法（不依赖 nbformat） | `python tools/check_notebook.py docs/learning/*.ipynb` |
| `run_notebook_in_kernel.py` | 在**真实 Jupyter 内核**里跑一遍 notebook，逐单元报告耗时与错误 | `python tools/run_notebook_in_kernel.py docs/learning/phase-0/walkthrough.ipynb` |
| `lock_requirements.py` | 从 pip 报告生成 `requirements.lock` | 见脚本模块说明 |
| `check_repo_consistency.py` | 仓库一致性门禁：依赖锁（requirements.in / pyproject.toml / requirements.lock 三者一致且锁版本满足区间）、文档与配置（workflow 引用、uv.lock 是否存在、testpaths 与测试目录）、工具清单 | `python tools/check_repo_consistency.py` |
| `secret_scan.py` | 凭据扫描门禁：扫仓库自有文本文件里的确定形态凭据（与 `enforcement/audit.py` 共用一份模式定义），默认跳过逐字复制上游的离线镜像 | `python tools/secret_scan.py` |

## 不属于本项目的脚本

`mirror_docs.py`、`learn_site.py`、`pep_site.py`、`dora_site.py`、`owasp_cheatsheets/` 是**离线文档镜像**流水线，
与本项目代码无关，不要混入 Phase 相关的改动。

# Phase 5 学习手册：怎么用、怎么维护

## 这是什么

Phase 5（代码验证器，Code Validators）的可执行讲解。回答四个问题：

| 小节 | 问题 |
| --- | --- |
| 0-1 | 验证器注册表与项目档案里有什么，为什么它们是数据 |
| 2-3 | 标准库 ast 能拿到哪些事实，依赖图怎样把 import 解析成组件 |
| 4-5 | 证据怎样变成 violation，哪些情况失败关闭 |
| 6-8 | 外部工具的失效分类、测试选择、命令行与退出码 |

对象清单与关系另有 `note.md`：先读它建立地图，再读 `walkthrough.ipynb` 看每一步实际跑出来什么样。

## 怎么跑

```powershell
# 方式一：Jupyter（需要本机有 Jupyter）
jupyter lab docs/learning/phase-5/walkthrough.ipynb

# 方式二：纯 Python（同内容，逐段打印）
python docs/learning/phase-5/walkthrough.py

# 方式三：不想装 Jupyter，只想确认它没坏
python tools/run_notebook_in_kernel.py docs/learning/phase-5/walkthrough.ipynb
```

前置条件：

- 仓库根目录下能读到 `validation/` 与 `tests/fixtures/validators/`（手册会从夹具项目复制一份工作区到
  `.tmp/learning/phase-5-<uuid>/`，跑完用 `python tools/cleanup.py` 清理）；
- `Ruff` 是**可选**的：手册里唯一依赖它的是"外部工具探针"那段（用假工具演示失效分类，不需要真 Ruff）；
  CLI 那段的退出码断言只跑 `py.*` 验证器，所以在任何机器上都能得到同样的结论。

## 它实际验证了什么

生成器会在两个工作目录（仓库根目录、手册目录）各执行一遍全部代码单元，并核对：

- 注册表：阶段顺序 `source → ast → dependency → docstring → lint → type → tests`、6 个 checker
  各自的验证器、每个验证器都是 `critical: true`（失败关闭）；
- AST 事实：`shop.order_repository` 被解析到第 3 行；动态 import 的"目标不是常量"被如实记录；
- 依赖图：组件名 `repository`（internal，第 3 行），没有未解析项；
- 决策：反例 `block` / 正例 `allow`，ARCH-001 的违规带文件与行号；
- 失败关闭：动态 import、语法错误、"只跑 py.source"三种场景都是 `block` 且带阻断点；
- 外部工具：`ok / findings / empty / garbage / config_error / crash / slow / old`
  八种行为各自落在一个显式状态上（空输出在进程层是 `ok`，适配器映射阶段才判 `output_invalid`）；
- 测试选择：同名测试落在 `related` 层级；**没有相关或同包测试**的生产文件会得到 `missing` 证据
  （即使工作区里有别的测试文件也一样——suite 升级只决定"跑什么"，不冒充"带了测试"）；
- CLI 退出码：`0 1 1 1 2` —— 注册表 / 反例 / 正例（限制成 `py.*` 后仍失败关闭）/ 只跑 `py.source` / 路径越界。

## 常见问题

**为什么"正例"的退出码也是 1？**
因为那一段刻意把验证器限制成 `py.source,py.ast,py.depgraph`，而 `policies/coding` 里的风格规则
需要 `style_lint`。没有验证器为它提供证据时，引擎按失败关闭阻断——**少跑一个验证器不等于少一条规则**。
想看到 `0`，就不加 `--validators`（此时需要本机有 Ruff；CI 会装一份）。

**手册里为什么用假工具？**
外部工具的失效路径（缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法）在真工具上很难稳定复现。
`tests/fixtures/validators/tools/fake_tool.py` 用命令行参数扮演这些行为，测试与手册共用同一份夹具。

**改了 `validation/validators.yaml` 或 `policies/` 之后手册会变红吗？**
可能会：手册会断言阶段顺序、checker 归属、组件名与退出码。这正是它的用处——数据改了，
手册要么跟着改，要么说明为什么不该改。改完运行 `python tools/build_learning_notebook.py` 重新生成。

**手册会不会把仓库搞脏？**
不会：工作区是 `.tmp/learning/phase-5-<uuid>/` 下的副本，验证器的临时目录在 `.tmp/validators/` 下，
两者都在 `.gitignore` 里；跑完 `python tools/cleanup.py` 即可。

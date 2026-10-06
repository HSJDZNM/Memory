# tech-detail/：一项技术一份可执行讲解

这个目录回答三个问题，**一章一个目录、一章一份可执行讲解**：

1. **谁依赖谁** —— `00`：扫描真实的包依赖边，并断言核心无出边、入口层入度为 0、框架导入点唯一；
2. **单项技术内部怎么走** —— `01`–`07`：每份只讲一项技术的内部流程，不混入其他子系统；
3. **文档怎么变成规则** —— `08`–`09`：一条规则从原文走到判定的实走路径，以及一段要求够不够格成为规则。

> **图已下线（2026-10-06）**：本目录原来的十章架构图（draw.io 源文件与 PNG 渲染图）以及生成它们的
> 那条管线（每章的 `diagram.py`、`build_diagrams.py`、`diagram_lib.py`）已一并删除，原因记在
> [上级目录的说明](../README.md)：本机 draw.io 起不来、PNG 无法重导，图只会持续制造"文改了、图没改"的脱钩。
> 技术关系的口径现在**只由这十份讲解承载**；讲解里的每一句话都能在代码里被核对。

## 目录结构：一章一个目录，一份内容源 + 两份产物

```text
tech-detail/
├── README.md                        # 本文件：入口与清单
├── notebook_lib.py                  # 讲解的公共词汇：单元与规格类型
├── build_notebooks.py               # 唯一的入口：收集各章 cells.py，算出产物并逐单元真实执行
└── 00-技术总览/                     # 一章一个目录（00–09 各一个）
    ├── cells.py                     # 这一章讲解的内容源（唯一真相源）
    ├── 00-技术总览.ipynb            # 产物：notebook
    └── 00-技术总览.py               # 产物：与 notebook 逐字相同的纯 Python 版
```

**按章分，不按文件类型分**：想读或想改一章，只打开它自己的目录就够了——内容源与两份产物都在里面。
**章节目录名 = 产物名**，生成器会核这一条（不一致直接报错退出），所以"这一章的讲解在哪"永远只有一个答案。

**只有一个规格源**：讲解由这一章的 `cells.py` 生成，生成器是 `build_notebooks.py`。
新增一章 = 新建 `NN-<名称>/` 目录 + 一份 `cells.py`，然后跑生成器。

## 清单（按主题分三组）

### 一、总览：谁依赖谁

| 编号 | 讲解 | 讲什么 | 主要代码锚点 |
| --- | --- | --- | --- |
| 00 | [技术总览](00-技术总览/00-技术总览.ipynb) | 4 个消费方 / 5 项能力技术 / 1 个判定核心 / 1 个数据基座 的依赖关系 | `src/policy/engine.py`、`src/policy_api/app.py`、`src/adapters/dsh/hooks.py` |

### 二、单项技术内部怎么走（01–07）

| 编号 | 讲解 | 讲什么 | 主要代码锚点 |
| --- | --- | --- | --- |
| 01 | [判定核心](01-判定核心-Policy-Engine/01-判定核心-Policy-Engine.ipynb) | 规则集 → 上下文 → 范围匹配 → 证据门禁 → checker 分派 → 三值判定 | `policy.engine.evaluate`、`src/policy/checkers.py`、`src/policy/evidence.py` |
| 02 | [dsh Hook](02-dsh-Hook-内部流程/02-dsh-Hook-内部流程.ipynb) | PreToolUse 九步：映射 → 白名单 → 范围校验 → 判定 → exit 0 / 2 → 审计 → PostToolUse | `src/adapters/dsh/hooks.py`、`src/adapters/dsh/adapter.py` |
| 03 | [离线规范检索](03-检索-SQLite-FTS5/03-检索-SQLite-FTS5.ipynb) | 语料 → 哈希校验 → 分块 → FTS5 索引 → 词项规范化 → 参数化查询 → 权限过滤 → 显式状态 | `src/retrieval/store.py`、`query.py`、`retriever.py` |
| 04 | [受控执行](04-受控执行/04-受控执行.ipynb) | 动作请求 → 注册表审核 → action_hash → pre-check → 审批 → grant → 执行一次 → 事后验证 → 审计链 | `src/enforcement/precheck.py`、`executor.py`、`audit.py`、`ledger.py` |
| 05 | [代码验证器](05-代码验证器/05-代码验证器.ipynb) | 变更集 → 注册表 → 测试选择 → AST / 依赖图 → 外部工具 → 证据包 → 交回判定核心 | `src/validators/pipeline.py`、`python_ast.py`、`adapters/` |
| 06 | [Policy API](06-Policy-API/06-Policy-API.ipynb) | HTTP → 守卫 → 认证 → 预算 → 幂等 → 装配 → 平台判定 → 版本化响应 → 观测 | `src/policy_api/app.py`、`auth.py`、`runtime.py`、`observability.py` |
| 07 | [LangGraph 编排](07-LangGraph-编排/07-LangGraph-编排.ipynb) | 需求 → 检索 → 规划 → 实施 → 验证 ⇄ 修复 → 测试 → 收尾，外加平台判定与 checkpoint | `src/orchestration/nodes.py`、`graph.py`、`checkpoint.py` |

### 三、文档怎么变成规则（08–09）

| 编号 | 讲解 | 讲什么 | 主要代码锚点 |
| --- | --- | --- | --- |
| 08 | [实走一条规则](08-单条规则-从文档到判定/08-单条规则-从文档到判定.ipynb) | **实走一条规则**：PEP 257 → 镜像 → 语料 → 分块 → 提炼 → checker → `DOC-001` → 证据 → 判定 | `policies/coding/DOC-001.yaml`、`validation/validators.yaml` |
| 09 | [能不能成为规则](09-能不能成为规则/09-能不能成为规则.ipynb) | **判定**：四条必要条件（本地来源 / 可确定性判定 / 范围可枚举 / 结论落决策表）缺一条的去向 | `src/policy/models.py` 的 `SourceRef`、`src/policy/checkers.py` |

每一章里讲解是两份（同名 `.ipynb` 与逐字相同的 `.py`，不想开 Jupyter 就直接跑 `.py`）。

## 讲解 notebook 的三个约定

- **可执行**：生成时逐单元真实执行，而且从仓库根与 `tech-detail/` 两个工作目录各跑一遍；
- **不写仓库**：每份只写自己独占的 `.tmp/tech-detail/<编号>/`，不碰 `ci_local.py` 与其他闭环共用的固定 `.tmp/` 路径；
- **不手改产物**：`.ipynb` 与同名 `.py` 都由 `build_notebooks.py` 生成，改内容改同一章目录里的 `cells.py`。

### 在 Jupyter / VS Code 里跑过之后"变脏"了？这是正常的

运行并保存会把每个单元的输出与执行序号写回 `.ipynb`，而生成器写出来的形态里这两样永远是空的。
两道检查盯着这件事：`python tools/check_repo_consistency.py` 一秒内点名哪一份被写脏，
CI 的 `build_notebooks.py --check` 做逐字节比对。恢复方式二选一：

```powershell
# 重新生成那一份（顺带逐单元执行一遍）
python docs/project/architecture/tech-detail/build_notebooks.py --only 03
# 或者用 git 直接还原（如果只是带运行痕迹，内容没改）
git checkout -- docs/project/architecture/tech-detail/03-检索-SQLite-FTS5/03-检索-SQLite-FTS5.ipynb
```

想彻底避开：直接跑同名的 `.py`——它与 notebook 逐字相同，却不会往仓库里写任何东西。

## 口径与来龙去脉

**08–09 的口径来源**是 [规则文档转化为规则.md](../规则文档转化为规则.md)（台阶 1–7 为主线，门禁 ①②③ 是三道
通过条件：① 摄取完整性挂在台阶 2、② 溯源可解析由台阶 3 执行、③ loader 加载门禁只覆盖台阶 5）。
编号口径不要混算：**台阶 ≠ Phase ≠ 门禁 ①②③**；「判定与消费」不是台阶 8，它内嵌在台阶 7 里。

**08 / 09 不是第三套口径**：`08` 是那条链路的**单个实例**（PEP 257 → `DOC-001`），`09` 是台阶 4 判据的
展开；台阶编号一律以 [术语与口径.md](../术语与口径.md) §2 为准。

**为什么没有"操作总览"这一章**：原来的 `08-文档转规则-操作总览` 与上级目录的架构说明同题，属于重复，
已删除。它独有的"每一步的命令与产物"由 [规则文档转化为规则.md](../规则文档转化为规则.md) §7 覆盖；
删除后原 `09` / `10` 顺次改为 `08` / `09`，本目录现有 `00`–`09` 共 10 个主题。

## 重建

只有一条命令，从 `tech-detail/` 下跑；产物由生成器算出，**不要手改**。

```powershell
# 默认逐单元真实执行（--only 只处理一份，--check 只比对产物，--list 看清单，--no-exec 不执行）
python docs/project/architecture/tech-detail/build_notebooks.py
python docs/project/architecture/tech-detail/build_notebooks.py --only 03
python docs/project/architecture/tech-detail/build_notebooks.py --check
```

`--check` 做两件事：与内容源**逐字节比对**产物，并复用 `tools/check_notebook.py` 做结构校验
（nbformat 版本、单元必需键、`source` 行数组形态、代码单元能否 compile）。
CI 里的门禁步骤 "Tech-detail notebooks are in sync" 跑的就是它；`tools/check_repo_consistency.py`
另外守着形态：产物里不许带 Jupyter 运行痕迹。

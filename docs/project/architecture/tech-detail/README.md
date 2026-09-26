# tech-detail/：技术关系图 + 同编号的可执行讲解

这个目录回答三个问题，**一章一个目录、一章一份图 + 一份同编号的可执行讲解**：

1. **谁依赖谁** —— `00`：一个方框 = 一项技术，箭头 = 依赖或调用方向；
2. **单项技术内部怎么走** —— `01`–`07`：每份只讲一项技术的内部流程，不混入其他子系统；
3. **文档怎么变成规则** —— `08`–`09`：一条规则从原文走到判定的实走路径，以及一段要求够不够格成为规则。

它与上级目录的六层架构图**分工不同**：[技术架构.drawio](../技术架构.drawio) 讲"平台分几层、规则怎么转化"，
这里讲"技术之间怎么依赖、每项技术内部经过哪几步"。本目录**不参与** `tools/check_arch_canon.py`
的图 / 文 / 口径三处同改硬规则（那套规则只覆盖上级目录的两份图与三份说明）。

## 目录结构：一章一个目录，两份规格源 + 四份产物

```text
tech-detail/
├── README.md                        # 本文件：入口与清单
├── diagram_lib.py                   # 图的公共词汇：节点 / 连线 / 画布 + .drawio / .png 两种写出
├── build_diagrams.py                # 图这条线的唯一入口：收集各章 diagram.py，算出产物
├── notebook_lib.py                  # 讲解的公共词汇：单元与规格类型
├── build_notebooks.py               # 讲解这条线的唯一入口：收集各章 cells.py，逐单元真实执行
└── 00-技术总览/                     # 一章一个目录（00–09 各一个）
    ├── diagram.py                   # 这一章图的规格（唯一真相源）
    ├── cells.py                     # 这一章讲解的内容源（唯一真相源）
    ├── 00-技术总览.drawio           # 图：可编辑源
    ├── 00-技术总览.png              # 图：渲染图
    ├── 00-技术总览.ipynb            # 讲解：notebook
    └── 00-技术总览.py               # 讲解：逐字相同的纯 Python 版
```

**按章分，不按文件类型分**：想读或想改一章，只打开它自己的目录就够了——图、讲解、两份规格源都在里面，
不必在 `diagrams/` 与 `notebooks/` 之间来回对照。**章节目录名 = 产物名**，两个生成器都会核这一条
（不一致直接报错退出），所以"这一章的图与讲解在哪"永远只有一个答案。

**两条产品线各只有一个规格源**：图由这一章的 `diagram.py` 算出，讲解由这一章的 `cells.py` 生成；
两个生成器分别是 `build_diagrams.py` 与 `build_notebooks.py`。新增一章 = 新建 `NN-<名称>/`
目录 + 一份 `diagram.py` + 一份 `cells.py`，然后跑两个生成器。

## 清单（按主题分三组）

### 一、总览：谁依赖谁

| 编号 | 图 | 讲解 | 图上讲什么 | 主要代码锚点 |
| --- | --- | --- | --- | --- |
| 00 | [技术总览](00-技术总览/00-技术总览.drawio) | [技术总览](00-技术总览/00-技术总览.ipynb) | 4 个消费方 / 5 项能力技术 / 1 个判定核心 / 1 个数据基座 的依赖关系 | `src/policy/engine.py`、`src/policy_api/app.py`、`src/adapters/dsh/hooks.py` |

### 二、单项技术内部怎么走（01–07）

| 编号 | 图 | 讲解 | 图上讲什么 | 主要代码锚点 |
| --- | --- | --- | --- | --- |
| 01 | [判定核心-Policy-Engine](01-判定核心-Policy-Engine/01-判定核心-Policy-Engine.drawio) | [判定核心](01-判定核心-Policy-Engine/01-判定核心-Policy-Engine.ipynb) | 规则集 → 上下文 → 范围匹配 → 证据门禁 → checker 分派 → 三值判定 | `policy.engine.evaluate`、`src/policy/checkers.py`、`src/policy/evidence.py` |
| 02 | [dsh-Hook-内部流程](02-dsh-Hook-内部流程/02-dsh-Hook-内部流程.drawio) | [dsh Hook](02-dsh-Hook-内部流程/02-dsh-Hook-内部流程.ipynb) | PreToolUse 九步：映射 → 白名单 → 范围校验 → 判定 → exit 0 / 2 → 审计 → PostToolUse | `src/adapters/dsh/hooks.py`、`src/adapters/dsh/adapter.py` |
| 03 | [检索-SQLite-FTS5](03-检索-SQLite-FTS5/03-检索-SQLite-FTS5.drawio) | [离线规范检索](03-检索-SQLite-FTS5/03-检索-SQLite-FTS5.ipynb) | 语料 → 哈希校验 → 分块 → FTS5 索引 → 词项规范化 → 参数化查询 → 权限过滤 → 显式状态 | `src/retrieval/store.py`、`query.py`、`retriever.py` |
| 04 | [受控执行](04-受控执行/04-受控执行.drawio) | [受控执行](04-受控执行/04-受控执行.ipynb) | 动作请求 → 注册表审核 → action_hash → pre-check → 审批 → grant → 执行一次 → 事后验证 → 审计链 | `src/enforcement/precheck.py`、`executor.py`、`audit.py`、`ledger.py` |
| 05 | [代码验证器](05-代码验证器/05-代码验证器.drawio) | [代码验证器](05-代码验证器/05-代码验证器.ipynb) | 变更集 → 注册表 → 测试选择 → AST / 依赖图 → 外部工具 → 证据包 → 交回判定核心 | `src/validators/pipeline.py`、`python_ast.py`、`adapters/` |
| 06 | [Policy-API](06-Policy-API/06-Policy-API.drawio) | [Policy API](06-Policy-API/06-Policy-API.ipynb) | HTTP → 守卫 → 认证 → 预算 → 幂等 → 装配 → 平台判定 → 版本化响应 → 观测 | `src/policy_api/app.py`、`auth.py`、`runtime.py`、`observability.py` |
| 07 | [LangGraph-编排](07-LangGraph-编排/07-LangGraph-编排.drawio) | [LangGraph 编排](07-LangGraph-编排/07-LangGraph-编排.ipynb) | 需求 → 检索 → 规划 → 实施 → 验证 ⇄ 修复 → 测试 → 收尾，外加平台判定与 checkpoint | `src/orchestration/nodes.py`、`graph.py`、`checkpoint.py` |

### 三、文档怎么变成规则（08–09）

| 编号 | 图 | 讲解 | 图上讲什么 | 主要代码锚点 |
| --- | --- | --- | --- | --- |
| 08 | [单条规则-从文档到判定](08-单条规则-从文档到判定/08-单条规则-从文档到判定.drawio) | [实走一条规则](08-单条规则-从文档到判定/08-单条规则-从文档到判定.ipynb) | **实走一条规则**：PEP 257 → 镜像 → 语料 → 分块 → 提炼 → checker → `DOC-001` → 证据 → 判定 | `policies/coding/DOC-001.yaml`、`validation/validators.yaml` |
| 09 | [能不能成为规则](09-能不能成为规则/09-能不能成为规则.drawio) | [能不能成为规则](09-能不能成为规则/09-能不能成为规则.ipynb) | **判定**：四条必要条件（本地来源 / 可确定性判定 / 范围可枚举 / 结论落决策表）缺一条的去向 | `src/policy/models.py` 的 `SourceRef`、`src/policy/checkers.py` |

每一章里图是两份（同名 `.drawio` 可编辑源 + `.png` 渲染图），讲解是两份
（同名 `.ipynb` 与逐字相同的 `.py`，不想开 Jupyter 就直接跑 `.py`）。

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

与 `docs/project/learning/` 的分工：那边按**实施阶段**（Phase 0–8）讲一遍，这边按**技术**讲（一张图一项技术）；
两边的代码单元都是跑得通的，只是切法不同。

## 口径与来龙去脉

**08–09 两张图的口径来源**是 [规则文档转化为规则.md](../规则文档转化为规则.md)（台阶 1–7 为主线，图上
①②③ 是三道通过条件：① 摄取完整性挂在台阶 2、② 溯源可解析由台阶 3 执行、③ loader 加载门禁只覆盖台阶 5）。
编号口径不要混算：**台阶 ≠ Phase ≠ 图上 ①②③**；「判定与消费」不是台阶 8，它内嵌在台阶 7 里。

**08 / 09 与图 2 的关系**：它们不是第三套口径。`08` 是图 2 那条链路的**单个实例**（PEP 257 → `DOC-001`），
`09` 是台阶 4 判据的展开；台阶编号一律以图 2 与 [术语与口径.md](../术语与口径.md) §2 为准。

**为什么这里没有"操作总览"图**：原来的 `08-文档转规则-操作总览` 画的也是"台阶 1–7 + 三道门禁 ①②③"，
与 [技术架构.drawio](../技术架构.drawio) 第 2 页同题，属于重复图，已删除。
它独有的"每一步的命令与产物"由第 2 页的台阶节点与 [规则文档转化为规则.md](../规则文档转化为规则.md) §7 覆盖；
删除后原 `09` / `10` 顺次改为 `08` / `09`，本目录现有 `00`–`09` 共 10 个主题。

**图侧的历史纠正**记在 [术语与口径.md](../术语与口径.md) §6.3（图 / 文 / 代码不一致清单），改图前先看一眼。

## 画法约定（图这条产品线）

- **一个方框只放一项技术或一个步骤**，标题两行：第一行短标题（≤14 字），第二行精确锚点（模块 / 函数 / 文件）；
- **箭头只有一种含义**：依赖或调用方向。没有"顺带说明"的连线；
- **实线 = 同进程依赖**，**虚线 = 进程或 HTTP 边界**；
- 颜色只用六种：白 = 普通步骤，黄 = 门禁与判定核心，紫 = **人工步骤（唯一不可自动化）**，红 = 失败关闭 / 失败终态，蓝灰 = 外部进程或数据，浅灰 = 说明与降级去向；
- 图外的补充信息（省略的连线、边界说明）一律放在图脚注，不塞进节点。

## 重建

两条产品线各一条命令，都从 `tech-detail/` 下跑；两侧产物都由生成器算出，**不要手改**。

```powershell
# 图：只写 .drawio / 同时渲染 .png（渲染需要 Pillow）；--only 只处理一章
python docs/project/architecture/tech-detail/build_diagrams.py
python docs/project/architecture/tech-detail/build_diagrams.py --png
python docs/project/architecture/tech-detail/build_diagrams.py --only 03 --png

# 讲解：默认逐单元真实执行（--only 只处理一份，--check 只比对产物，--list 看清单，--no-exec 不执行）
python docs/project/architecture/tech-detail/build_notebooks.py
python docs/project/architecture/tech-detail/build_notebooks.py --only 03
python docs/project/architecture/tech-detail/build_notebooks.py --check
```

**改图改这一章的 `<章>/diagram.py`**：它是这一章唯一的规格源，`.drawio` 与 `.png` 都由
`diagram_lib.py` 用同一份坐标算出，手改产物必然让两者脱钩。脚本会检查每个节点的文字是否超出边框，
超出会打印告警。CI 里 `build_notebooks.py --check` 与 `tools/check_repo_consistency.py`（形态：不许带
Jupyter 运行痕迹）守着讲解侧的产物与规格一致。

**PNG 不是 draw.io CLI 导出的**：本机沙箱下 draw.io 的 Electron 进程起不来
（`mojo platform_channel` 访问被拒），因此 PNG 由 `diagram_lib.py` 用 Pillow 渲染（同一份规格算出同样的坐标）。
在能用 draw.io 桌面版的环境里，可以用 CLI 重新导出（会带上可编辑的内嵌 XML）：

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f png -e -s 2 -b 10 `
    -o docs/project/architecture/tech-detail/00-技术总览/00-技术总览.drawio.png `
    docs/project/architecture/tech-detail/00-技术总览/00-技术总览.drawio
```

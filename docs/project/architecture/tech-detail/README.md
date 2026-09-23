# tech-detail/：技术关系图与单技术内部流程图

这个目录回答三个问题，**一张图只回答一个**：

1. **谁依赖谁** —— `00-技术总览.drawio`：一个方框 = 一项技术，箭头 = 依赖或调用方向；
2. **单项技术内部怎么走** —— `01`–`07`：每张图只讲一项技术的内部流程，不混入其他子系统；
3. **文档怎么变成规则** —— `08`–`09`：一条规则从原文走到判定的实走路径，以及一段要求够不够格成为规则。

它与上级目录的六层架构图**分工不同**：[技术架构.drawio](../技术架构.drawio) 讲"平台分几层、规则怎么转化"，
这里讲"技术之间怎么依赖、每项技术内部经过哪几步"。本目录**不参与** `tools/check_arch_canon.py`
的图 / 文 / 口径三处同改硬规则（那套规则只覆盖上级目录的两份图与三份说明）。

## 文件清单

| 图 | 讲什么 | 主要代码锚点 |
| --- | --- | --- |
| [00-技术总览](00-技术总览.drawio) | 4 个消费方 / 5 项能力技术 / 1 个判定核心 / 1 个数据基座 的依赖关系 | `src/policy/engine.py`、`src/policy_api/app.py`、`src/adapters/dsh/hooks.py` |
| [01-判定核心-Policy-Engine](01-判定核心-Policy-Engine.drawio) | 规则集 → 上下文 → 范围匹配 → 证据门禁 → checker 分派 → 三值判定 | `policy.engine.evaluate`、`src/policy/checkers.py`、`src/policy/evidence.py` |
| [02-dsh-Hook-内部流程](02-dsh-Hook-内部流程.drawio) | PreToolUse 九步：映射 → 白名单 → 范围校验 → 判定 → exit 0 / 2 → 审计 → PostToolUse | `src/adapters/dsh/hooks.py`、`src/adapters/dsh/adapter.py` |
| [03-检索-SQLite-FTS5](03-检索-SQLite-FTS5.drawio) | 语料 → 哈希校验 → 分块 → FTS5 索引 → 词项规范化 → 参数化查询 → 权限过滤 → 显式状态 | `src/retrieval/store.py`、`src/retrieval/query.py`、`src/retrieval/retriever.py` |
| [04-受控执行](04-受控执行.drawio) | 动作请求 → 注册表审核 → action_hash → pre-check → 审批 → grant → 执行一次 → 事后验证 → 审计链 | `src/enforcement/precheck.py`、`executor.py`、`audit.py`、`ledger.py` |
| [05-代码验证器](05-代码验证器.drawio) | 变更集 → 注册表 → 测试选择 → AST / 依赖图 → 外部工具 → 证据包 → 交回判定核心 | `src/validators/pipeline.py`、`python_ast.py`、`adapters/` |
| [06-Policy-API](06-Policy-API.drawio) | HTTP → 守卫 → 认证 → 预算 → 幂等 → 装配 → 平台判定 → 版本化响应 → 观测 | `src/policy_api/app.py`、`auth.py`、`runtime.py`、`observability.py` |
| [07-LangGraph-编排](07-LangGraph-编排.drawio) | 需求 → 检索 → 规划 → 实施 → 验证 ⇄ 修复 → 测试 → 收尾，外加平台判定与 checkpoint | `src/orchestration/nodes.py`、`graph.py`、`checkpoint.py` |
| [08-单条规则-从文档到判定](08-单条规则-从文档到判定.drawio) | **实走一条规则**：PEP 257 → 镜像 → 语料 → 分块 → 提炼 → checker → `DOC-001` → 证据 → 判定 | `policies/coding/DOC-001.yaml`、`validation/validators.yaml` |
| [09-能不能成为规则](09-能不能成为规则.drawio) | **判定**：四条必要条件（本地来源 / 可确定性判定 / 范围可枚举 / 结论落决策表）缺一条的去向 | `src/policy/models.py` 的 `SourceRef`、`src/policy/checkers.py` |

每张图都有同名 `.png`（渲染图，便于直接看）与 `.drawio`（可编辑源）。

**08–09 两张图的口径来源**是 [规则文档转化为规则.md](../规则文档转化为规则.md)（台阶 1–7 为主线，图上
①②③ 是三道通过条件：① 摄取完整性挂在台阶 2、② 溯源可解析由台阶 3 执行、③ loader 加载门禁只覆盖台阶 5）。
编号口径不要混算：**台阶 ≠ Phase ≠ 图上 ①②③**；「判定与消费」不是台阶 8，它内嵌在台阶 7 里。

**08 / 09 与图 2 的关系**：它们不是第三套口径。`08` 是图 2 那条链路的**单个实例**（PEP 257 → `DOC-001`），
`09` 是台阶 4 判据的展开；台阶编号一律以图 2 与 [术语与口径.md](../术语与口径.md) §2 为准。

**为什么这里没有"操作总览"图**：原来的 `08-文档转规则-操作总览` 画的也是"台阶 1–7 + 三道门禁 ①②③"，
与 [技术架构.drawio](../技术架构.drawio) 第 2 页同题，属于重复图，已删除。
它独有的"每一步的命令与产物"由第 2 页的台阶节点与 [规则文档转化为规则.md](../规则文档转化为规则.md) §7 覆盖；
删除后原 `09` / `10` 顺次改为 `08` / `09`，本目录现有 `00`–`09` 共 10 张图。

## 画法约定

- **一个方框只放一项技术或一个步骤**，标题两行：第一行短标题（≤14 字），第二行精确锚点（模块 / 函数 / 文件）；
- **箭头只有一种含义**：依赖或调用方向。没有"顺带说明"的连线；
- **实线 = 同进程依赖**，**虚线 = 进程或 HTTP 边界**；
- 颜色只用六种：白 = 普通步骤，黄 = 门禁与判定核心，紫 = **人工步骤（唯一不可自动化）**，红 = 失败关闭 / 失败终态，蓝灰 = 外部进程或数据，浅灰 = 说明与降级去向；
- 图外的补充信息（省略的连线、边界说明）一律放在图脚注，不塞进节点。

## 重建

```powershell
# 只写 .drawio（不需要任何第三方库）
python docs/project/architecture/tech-detail/build.py

# 同时渲染 .png（需要 Pillow）
python docs/project/architecture/tech-detail/build.py --png
```

**改内容改 `build.py` 里的规格，不要手改产物**：`build.py` 是唯一规格源，
`.drawio` 与 `.png` 都由它算出同样的坐标，手改必然让两者脱钩。
脚本会检查每个节点的文字是否超出边框，超出会打印告警。

**PNG 不是 draw.io CLI 导出的**：本机沙箱下 draw.io 的 Electron 进程起不来
（`mojo platform_channel` 访问被拒），因此 PNG 由 `build.py` 用 Pillow 渲染。
在能用 draw.io 桌面版的环境里，可以用 CLI 重新导出（会带上可编辑的内嵌 XML）：

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f png -e -s 2 -b 10 `
    -o docs\project\architecture\tech-detail\00-技术总览.drawio.png `
    docs\project\architecture\tech-detail\00-技术总览.drawio
```

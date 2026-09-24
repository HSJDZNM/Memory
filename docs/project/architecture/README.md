# docs/project/architecture/：仓库技术架构与使用文档

本目录面向“想快速搞懂这个仓库”的读者（人或 AI 代理），只描述**当前代码实际做到的事**，
不描述计划。与 `README.md`、`AGENTS.md` 冲突时以代码与数据为准。

| 文件 | 内容 |
| --- | --- |
| [技术架构.drawio](技术架构.drawio) | 两页 draw.io 架构图：**第 1 页**技术架构总览**（简化版）**——6 层 × 4 个能力节点（① 消费方 / 入口、② 接入与协议转换、③ 判定核心、④ 能力层、⑤ 数据与契约、⑥ 证据与门禁），层内的子系统归属以 [术语与口径.md](术语与口径.md) §1 为准；**第 2 页**规则文档 → 可执行规则的转化链路（台阶 1–7）与门禁条件（①②③） |
| [技术流程.drawio](技术流程.drawio) | **按所用技术抽象的流程架构图**：`A` 输入 → `B` 解析与建模 → `C` 存储与检索 → `D` 判定与执行 → `E` 对外接口与编排，外加 `F` 工程与验证链路（**A–F 是技术抽象分组，不是六个架构层**，见 [术语与口径.md](术语与口径.md) §1）；颜色区分「标准库 / 第三方依赖 / 自研代码 / 数据与外部工具」，一眼看出依赖边界 |
| [技术架构-1-总览.drawio.png](技术架构-1-总览.drawio.png) | 第 1 页导出的 PNG（含内嵌 XML，可在 draw.io 里打开继续编辑） |
| [技术架构-2-规则转化.drawio.png](技术架构-2-规则转化.drawio.png) | 第 2 页导出的 PNG（同上） |
| [技术流程.drawio.png](技术流程.drawio.png) | 技术流程架构图导出的 PNG（同上） |
| [功能清单.md](功能清单.md) | **功能清单**：定位、12 项能力、逐子系统功能、数据与契约清单、仓库脚本、测试与证据、明确没有做的边界 |
| [使用说明.md](使用说明.md) | **使用说明**：安装、五分钟上手、各子系统命令与退出码、门禁与清理、FAQ、一页速查 |
| [规则文档转化为规则.md](规则文档转化为规则.md) | **规则文档 → 可执行规则**：三层规范模型、七个台阶、转换条件总表、什么不能成为规则、真实走查与实操流程 |
| [规则转化覆盖报告.md](规则转化覆盖报告.md) | **转化覆盖报告**：把 `docs/mirrors/<mirror>/**` 的 284 篇镜像文档逐篇走查一遍的结果——17 篇产出 38 条规则、267 篇写明为什么停在 Guidance、被拒绝但值得记下来的候选、以及走查中翻出的三个真缺陷 |
| [tech-detail/](tech-detail/README.md) | **技术关系图与单技术内部流程图**：1 张依赖总览 + 7 张单技术流程（判定核心 / dsh Hook / 检索 / 受控执行 / 验证器 / API / 编排）+ 2 张文档转规则图（单条规则实走 / 能不能成为规则）。一个方框只放一项技术，箭头只有依赖与调用一种含义；与上表的六层架构图**分工不同**（那里讲分层与规则转化，这里讲依赖与单项技术内部步骤），也不参与本文的三处同改硬规则。每张图另配一份**同编号的可执行讲解 notebook**（由 `build_notebooks.py` 生成、逐单元真实执行），见 [tech-detail/README.md](tech-detail/README.md) |
| [术语与口径.md](术语与口径.md) | **口径唯一真相源**：六层规范名与包含关系、台阶 1–7 ↔ Phase 0–8 ↔ 图内 ①②③ 对照、判定链路术语、退出码与终态、数字口径（附实测命令）、核对记录与裁决、文风口径。图、文、代码说法不一致时先看它 |

## 维护方式

```powershell
# 改架构图：先改 技术架构.drawio（draw.io 桌面版或直接改 XML），再重新导出两张 PNG
#   -e 内嵌 XML（导出后若用视觉校验要先去掉 -e，见 drawio-skill 的说明）；--page-index 从 1 开始
& "C:\Program Files\draw.io\draw.io.exe" -x -f png -e -s 2 --page-index 1 `
    -o docs/project/architecture/技术架构-1-总览.drawio.png `
    docs/project/architecture/技术架构.drawio
& "C:\Program Files\draw.io\draw.io.exe" -x -f png -e -s 2 --page-index 2 `
    -o docs/project/architecture/技术架构-2-规则转化.drawio.png `
    docs/project/architecture/技术架构.drawio
& "C:\Program Files\draw.io\draw.io.exe" -x -f png -e -s 2 -o docs/project/architecture/技术流程.drawio.png `
    docs/project/architecture/技术流程.drawio

# 改文档：过一遍文本规范门禁（UTF-8 / LF / 行尾空白 / 结尾换行）
python tools/check_text_conventions.py
```

**硬规则：改图 / 改文 / 改口径必须三处同改**（口径表：[术语与口径.md](术语与口径.md)）

三处指图、文与口径表。**图** = `技术架构.drawio` 第 1 页六层与包含关系、第 2 页台阶与门禁；
**文** = 本目录三份 `.md`；**口径表** = `术语与口径.md` §0–§7。
只改一处会让图与文再次脱钩——编号、层名、数字都是这样脱钩的。

```powershell
# 1) 文本规范门禁：UTF-8 / LF / 行尾空白 / 结尾换行（.drawio 也是文本，同样受检）
python tools/check_text_conventions.py

# 2) 三处同名自检：六层规范名必须同时出现在 图 / 功能清单 / 口径表（六个层名各查一次）
Select-String -Path docs/project/architecture/技术架构.drawio, docs/project/architecture/功能清单.md,
    docs/project/architecture/术语与口径.md -Pattern '④ 能力层', '⑥ 证据与门禁'

# 3) 数字口径自检：改完数字后回口径表 §5 逐条复跑命令（例：闭环脚本数）
(Get-ChildItem tools/*_loop.py).Count

# 4) 图侧一致性 / 文风（已升格为正式工具，登记在 tools/README.md）
python tools/check_arch_canon.py   # 图 vs 文 vs 口径表：三处同口径 + 包含关系成立（exit 0/1）
python tools/check_arch_style.py   # 文风口径 §7：概括句/长句/术语墙/图上标签两层写法（exit 0/1）
```

**改文风先改口径表 §7**（概括 + 精确锚点的阈值都在那里），再改文稿与图。

**四条容易写错的地方**：

1. 这里的架构图是**手工维护的 XML**，不是“跑一条命令生成的”。改代码后请对照
   `src/`、`policies/`、`registry/`、`validation/`、`adapters/`、`api/` 的实际内容更新它；
2. 文档里的**用例数、条目数、工具数**这类数字会过期，改完顺手核对一遍
   （`python -m pytest -q`、`python -m retrieval.cli verify`、`python -m enforcement.cli registry --list`）；
   **数字的口径与实测命令只认 [术语与口径.md](术语与口径.md) §5**；
3. **三套编号不许互相替代**：转化链路写“台阶 N”，实施批次写“Phase N”，图 2 的条件写“①②③”，
   流程页的技术抽象分组写 `A`–`F`（对照表见 [术语与口径.md](术语与口径.md) §2）；
4. 不要把“计划做的”写成“已经做的”。仓库的惯例是：**没做的写进“明确没有做”那一节**。

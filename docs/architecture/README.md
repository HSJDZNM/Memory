# docs/architecture/：仓库技术架构与使用文档

本目录面向“想快速搞懂这个仓库”的读者（人或 AI 代理），只描述**当前代码实际做到的事**，
不描述计划。与 `README.md`、`AGENTS.md` 冲突时以代码与数据为准。

| 文件 | 内容 |
| --- | --- |
| [技术架构.drawio](技术架构.drawio) | 两页 draw.io 架构图：**第 1 页**技术架构总览**（简化版）**——6 层 × 4 个概念节点（消费方 / 接入与协议转换 / 判定核心 / 能力层 / 数据与契约 / 证据与门禁），模块级细节见 [功能清单.md](功能清单.md)；**第 2 页**规则文档 → 可执行规则的转化链路与门禁条件 |
| [技术流程.drawio](技术流程.drawio) | **按所用技术抽象的流程架构图**：输入 → 解析与建模 → 存储与检索 → 判定与执行 → 对外接口与编排，外加⑥工程与验证链路；颜色区分「标准库 / 第三方依赖 / 自研代码 / 数据与外部工具」，一眼看出依赖边界 |
| [技术架构-1-总览.drawio.png](技术架构-1-总览.drawio.png) | 第 1 页导出的 PNG（含内嵌 XML，可在 draw.io 里打开继续编辑） |
| [技术架构-2-规则转化.drawio.png](技术架构-2-规则转化.drawio.png) | 第 2 页导出的 PNG（同上） |
| [技术流程.drawio.png](技术流程.drawio.png) | 技术流程架构图导出的 PNG（同上） |
| [功能清单.md](功能清单.md) | **功能清单**：定位、12 项能力、逐子系统功能、数据与契约清单、仓库脚本、测试与证据、明确没有做的边界 |
| [使用说明.md](使用说明.md) | **使用说明**：安装、五分钟上手、各子系统命令与退出码、门禁与清理、FAQ、一页速查 |
| [规则文档转化为规则.md](规则文档转化为规则.md) | **规则文档 → 可执行规则**：三层规范模型、七个台阶、转换条件总表、什么不能成为规则、真实走查与实操流程 |

## 维护方式

```powershell
# 改架构图：先改 技术架构.drawio（draw.io 桌面版或直接改 XML），再重新导出两张 PNG
#   -e 内嵌 XML（导出后若用视觉校验要先去掉 -e，见 drawio-skill 的说明）；--page-index 从 1 开始
& "C:\Program Files\draw.io\draw.io.exe" -x -f png -e -s 2 --page-index 1 `
    -o docs/architecture/技术架构-1-总览.drawio.png `
    docs/architecture/技术架构.drawio
& "C:\Program Files\draw.io\draw.io.exe" -x -f png -e -s 2 --page-index 2 `
    -o docs/architecture/技术架构-2-规则转化.drawio.png `
    docs/architecture/技术架构.drawio
& "C:\Program Files\draw.io\draw.io.exe" -x -f png -e -s 2 -o docs/architecture/技术流程.drawio.png `
    docs/architecture/技术流程.drawio

# 改文档：过一遍文本规范门禁（UTF-8 / LF / 行尾空白 / 结尾换行）
python tools/check_text_conventions.py
```

**三条容易写错的地方**：

1. 这里的架构图是**手工维护的 XML**，不是“跑一条命令生成的”。改代码后请对照
   `src/`、`policies/`、`registry/`、`validation/`、`adapters/`、`api/` 的实际内容更新它；
2. 文档里的**用例数、条目数、工具数**这类数字会过期，改完顺手核对一遍
   （`python -m pytest -q`、`python -m retrieval.cli verify`、`python -m enforcement.cli registry --list`）；
3. 不要把“计划做的”写成“已经做的”。仓库的惯例是：**没做的写进“明确没有做”那一节**。

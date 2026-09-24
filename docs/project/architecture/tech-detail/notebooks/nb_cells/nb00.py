
# -*- coding: utf-8 -*-
"""00-技术总览：谁依赖谁（内容源，产物由 build_notebooks.py 生成）。"""
from __future__ import annotations

from nb_cells import NotebookSpec, code, markdown

SPEC = NotebookSpec(
    stem="00-技术总览",
    title="技术总览：谁依赖谁",
    summary="用 ast 扫出真实的包依赖边，并断言三条不变量（核心无出边 / 入口入度为 0 / 框架只有一个导入点）",
    temp_dir=".tmp/tech-detail/00",
    cells=(
        markdown(
            '''
# 00 技术总览：谁依赖谁

这份 notebook 配合同名图 `00-技术总览.drawio`。图回答一个问题——**这个仓库里谁依赖谁**；
notebook 把这张图里的每一句话都在代码里验一遍：先扫出真实的 import 边，再断言三条不能破的规矩。

读完应该能回答三件事：

1. 哪些技术是"入口 / 消费方"——没有人依赖它们，删掉哪一个平台都照常跑？
2. 唯一被所有路径依赖的核心是哪一块？
3. 哪些依赖只允许以"延迟导入"的形式存在，为什么？

**预备知识**：会读 Python 的 `import` 语句就够了。下面全部用标准库 `ast` 解析源码，
不装任何额外依赖。
'''
        ),
        code(
            '''
# 先找到仓库根目录：notebook 可能从仓库根启动，也可能从本目录启动，两种都要能跑。
import sys
from pathlib import Path


def find_repo_root(start):
    """往上找：同时有 pyproject.toml 与 src/policy/ 的那一层就是仓库根。"""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "policy").is_dir():
            return candidate
    raise SystemExit("没有找到仓库根目录（需要 pyproject.toml 与 src/policy/）")


REPO_ROOT = find_repo_root(Path.cwd())
for extra in (REPO_ROOT / "src", REPO_ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

# 这个目录分两条产品线：diagrams/ 是图（唯一规格源 diagrams/build.py），
# notebooks/ 是同编号的可执行讲解（唯一规格源 notebooks/build_notebooks.py）。
TECH_DETAIL = REPO_ROOT / "docs" / "project" / "architecture" / "tech-detail"
DIAGRAMS = TECH_DETAIL / "diagrams"
NOTEBOOKS = TECH_DETAIL / "notebooks"
print("仓库根目录:", REPO_ROOT.name)
print("讲解目录:", NOTEBOOKS.relative_to(REPO_ROOT).as_posix())
print("Python:", sys.version.split()[0])
'''
        ),
        markdown(
            '''
## 1. 真实的依赖边：扫出来，不是抄文档

一个方框 = 一个包（`src/<包名>/`），箭头 = "这个包 import 了那个包"。

扫的时候必须区分两种 import：**模块级**（文件一加载就执行）与**函数内延迟导入**（真正调用时才执行）。
两者分量完全不同：延迟导入常常是"组合根"或"构造引擎"处的豁免，模块级依赖却是改不掉的硬约束。
混在一起数会得出错误结论——把包级统计当结论，就曾经把"组合根的一个例外"当成"核心层也依赖别人"。

顺带算一个指标 `I = Ce / (Ca + Ce)`：出边越多越大、入边越多越小。
它衡量的是**改动代价**（多少人会被你拖着走），不是"这个包多久改一次"。
'''
        ),
        code(
            '''
# 用标准库 ast 扫出依赖边：既按包汇总，也保留"这条边来自哪个文件"。
import ast
from collections import defaultdict

SRC = REPO_ROOT / "src"
PACKAGES = ("policy", "retrieval", "validators", "enforcement", "adapters", "policy_api", "orchestration")


def file_imports(path):
    """一个文件 import 到的仓库内部顶层包，返回 (模块级目标, 函数内目标)。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top_level = {id(node) for node in tree.body}
    eager, lazy = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top in PACKAGES:
                (eager if id(node) in top_level else lazy).add(top)
    return eager, lazy


edges = defaultdict(lambda: {"eager": set(), "lazy": set()})
file_edges = {}
for package in PACKAGES:
    for path in sorted((SRC / package).rglob("*.py")):
        eager, lazy = file_imports(path)
        eager, lazy = eager - {package}, lazy - {package}
        edges[package]["eager"] |= eager
        edges[package]["lazy"] |= lazy
        if eager or lazy:
            file_edges[path.relative_to(REPO_ROOT).as_posix()] = (sorted(eager), sorted(lazy))
for package in PACKAGES:
    edges[package]["lazy"] -= edges[package]["eager"]

incoming = defaultdict(set)
for source, target_sets in edges.items():
    for target in target_sets["eager"]:
        incoming[target].add(source)

print(pad("包", 14) + pad("模块级出边 →", 30) + pad("入边 Ca", 9) + "I = Ce/(Ca+Ce)")
print("-" * 70)
for package in PACKAGES:
    out_degree, in_degree = len(edges[package]["eager"]), len(incoming[package])
    total = out_degree + in_degree
    instability = out_degree / total if total else 0.0
    print(
        pad(package, 14)
        + pad(", ".join(sorted(edges[package]["eager"])) or "（无）", 30)
        + pad(in_degree, 9)
        + f"{instability:.2f}"
    )
print()
print("只在函数内导入的边（延迟导入）：")
for package in PACKAGES:
    if edges[package]["lazy"]:
        print("  " + pad(package, 14) + "→ " + ", ".join(sorted(edges[package]["lazy"])))
'''
        ),
        markdown(
            '''
## 2. 三条不变量

图上的箭头是"方向"，真正要守的是下面三条——它们都能被断言，不是口号：

1. **判定核心没有模块级出边**：`src/policy` 不 import 其他任何包（不导入 Web 框架 / Agent SDK / 工作流框架）；
2. **入口层入度为 0**：没有任何包 import `policy_api` 或 `orchestration`——删掉编排层，平台照常独立运行；
3. **工作流框架只有一个导入点**：只有 `orchestration/langgraph_engine.py` 导入 langgraph，
   而且是在**构造引擎时**才导入（没装就失败关闭，不静默回落到别的实现）。

第 1 条在本仓库有一个**真实的例外**，下面会把它精确地挡在一个文件里——这正是"包级统计"
不够用的地方：算到包级，它看起来像"核心层依赖验证器层"；算到文件级，它是 CLI 的装配点。
'''
        ),
        code(
            '''
# 第 1 条要先看到文件级明细，才能判断这是"架构破了"还是"组合根例外"。
core_files = ("models.py", "context.py", "scope.py", "loader.py", "engine.py", "evidence.py", "checkers.py")

policy_edges = {
    name: value for name, value in file_edges.items() if name.startswith("src/policy/")
}
print("src/policy 里带出边的文件：")
for name, (eager, lazy) in sorted(policy_edges.items()):
    print("  " + pad(name, 26) + "模块级 → " + (", ".join(eager) or "无") + "   延迟 → " + (", ".join(lazy) or "无"))
print()

# 判定核心的"业务模块"一个出边都不许有；例外只允许出现在 CLI 装配点 check.py，且只指向验证器装配。
dirty_core = [name for name in policy_edges if Path(name).name in core_files]
assert not dirty_core, f"判定核心的业务模块出现了出边：{dirty_core}"
assert set(policy_edges) == {"src/policy/check.py"}, f"出边来源不止 CLI 装配点：{sorted(policy_edges)}"
assert policy_edges["src/policy/check.py"][0] == ["validators"], policy_edges["src/policy/check.py"]

for package in PACKAGES:
    hit = edges[package]["eager"] & {"policy_api", "orchestration"}
    assert not hit, f"{package} 反向依赖了入口层：{sorted(hit)}"


def framework_importers(framework):
    """真的导入了某个框架的文件清单：含 importlib.import_module("框架…") 这种延迟导入。"""

    def touches(node):
        if isinstance(node, ast.Import):
            return any(alias.name.split(".")[0] == framework for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            return (node.module or "").split(".")[0] == framework
        if isinstance(node, ast.Call):
            # import_module(...) 与 importlib.import_module(...) 两种写法都要认：
            # 延迟导入框架时用的是前一种（from importlib import import_module）。
            called = getattr(node.func, "attr", "") or getattr(node.func, "id", "")
            if called == "import_module":
                first = node.args[0] if node.args else None
                return isinstance(first, ast.Constant) and str(first.value).startswith(framework)
        return False

    found = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(touches(node) for node in ast.walk(tree)):
            found.append(path.relative_to(REPO_ROOT).as_posix())
    return found


web = sorted(set(framework_importers("fastapi") + framework_importers("uvicorn")))
workflow = framework_importers("langgraph")

print(pad("检查项", 24) + "结果")
print("-" * 88)
print(pad("Web 框架导入点", 24) + (", ".join(web) or "（无）"))
print(pad("工作流框架导入点", 24) + (", ".join(workflow) or "（无）"))
print()

# Web 框架只允许出现在传输层（policy_api）；工作流框架只允许出现在编排层的引擎适配文件。
assert web and all(path.startswith("src/policy_api/") for path in web), web
assert not [path for path in web if path.startswith("src/policy/")], web
assert workflow == ["src/orchestration/langgraph_engine.py"], workflow
print("三条不变量全部成立：核心业务模块零出边、入口层入度为 0、框架导入点唯一。")
'''
        ),
        markdown(
            '''
## 3. 从"包"回到"层"

同一个仓库有两套说法：图上的**六层**（① 消费方 / 入口 … ⑥ 证据与门禁）与代码里的**包**。
层名与编号的唯一口径是 `docs/project/architecture/术语与口径.md` §1——下面这张表照它写，
并且现场核对每一个位置**真的存在**：文档与目录一旦漂移，这一步就会报错。
'''
        ),
        code(
            '''
# 六层 → 代码与数据位置（口径：docs/project/architecture/术语与口径.md §1）
LAYERS = (
    ("① 消费方 / 入口", ("src/orchestration", "src/adapters/dsh", "tools/api_loop.py")),
    ("② 接入与协议转换", ("src/adapters", "src/policy_api/app.py", "src/adapters/dsh/hooks.py")),
    ("③ 判定核心", ("src/policy",)),
    ("④ 能力层", ("src/retrieval", "src/enforcement", "src/validators", "src/policy_api")),
    ("⑤ 数据与契约", ("policies", "knowledge", "registry", "validation", "adapters", "api")),
    ("⑥ 证据与门禁", ("tools/phase_evidence.py", ".github/workflows")),
)

print(pad("层（规范名）", 22) + "代码与数据位置")
print("-" * 100)
for name, places in LAYERS:
    print(pad(name, 22) + " · ".join(places))

missing = [f"{name} → {place}" for name, places in LAYERS for place in places if not (REPO_ROOT / place).exists()]
print()
assert not missing, f"有层指向了不存在的路径：{missing}"
print("六层与目录逐一核对通过：", len(LAYERS), "层、", sum(len(item[1]) for item in LAYERS), "个位置")
'''
        ),
        markdown(
            '''
## 4. 这个目录里还有什么：00–09 索引

`tech-detail/` 分成两条产品线：`diagrams/` 放图（可编辑的 `.drawio` + 渲染图 `.png`），
`notebooks/` 放同编号的可执行讲解（`.ipynb` + 同名 `.py`）。下面这个索引是从目录**现场读出来的**——
不是抄来的清单；新增一张图，这里就多一行，少一份 notebook 会被明确指出来。
'''
        ),
        code(
            '''
# 读目录得到索引：图（.drawio）与 notebook（.ipynb）按编号一一对应。
diagrams = sorted(path.stem for path in DIAGRAMS.glob("*.drawio"))
notebooks = {path.stem for path in NOTEBOOKS.glob("*.ipynb")}

print(pad("编号图", 34) + "配套 notebook")
print("-" * 60)
for stem in diagrams:
    print(pad(stem, 34) + ("有" if stem in notebooks else "缺（还没生成）"))
print()

assert len(diagrams) == 10, f"图的清单变了（{len(diagrams)} 张）：索引与文档要跟着改"
missing = sorted(set(diagrams) - notebooks)
extra = sorted(notebooks - set(diagrams))
if extra:
    print("没有同名图的 notebook:", ", ".join(extra))
if missing:
    print(f"尚未生成 {len(missing)} 份：" + ", ".join(missing))
else:
    print(f"{len(diagrams)} 张图都有配套 notebook。")
'''
        ),
        markdown(
            '''
## 小结

- 依赖方向是**代码事实**，不是文档承诺：`ast` 扫出来的边与图一致，三条不变量靠断言守住；
- `I = Ce/(Ca+Ce)` 从上到下单调变小——入口层最"易变"（没有人依赖它），判定核心最"稳定"（所有路径都要找它）；
- 一个包级统计不够用的实例：`src/policy/check.py` 模块级 import 了 `validators.registry`（CLI 装配需要），
  但判定核心的业务模块（engine / loader / scope / models / context / evidence / checkers）**零出边**。
  包级表会说"核心依赖验证器层"，文件级一看，那只是组合根。

接下来按兴趣往下走：`01-判定核心-Policy-Engine.ipynb`（一次判定怎么算出来）、
`04-受控执行.ipynb`（允许之后副作用怎么被管住）、`09-能不能成为规则.ipynb`（一段文档要求够不够格成为规则）。
'''
        ),
    ),
)

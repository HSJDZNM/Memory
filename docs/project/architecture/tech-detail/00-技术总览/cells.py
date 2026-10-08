
# -*- coding: utf-8 -*-
"""00-技术总览：谁依赖谁（内容源，产物由 build_notebooks.py 生成）。"""
from __future__ import annotations

from notebook_lib import NotebookSpec, code, markdown

SPEC = NotebookSpec(
    stem="00-技术总览",
    title="技术总览：谁依赖谁",
    summary="用 ast 扫出真实的包依赖边，并断言三条不变量（核心无出边 / 入口入度为 0 / 框架只有一个导入点）",
    temp_dir=".tmp/tech-detail/00",
    cells=(
        markdown(
            '''
# 00 技术总览：谁依赖谁

这份 notebook 回答一个问题——**这个仓库里谁依赖谁**：它把每一句话都在代码里验一遍，
先扫出真实的 import 边，再断言三条不能破的规矩。

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

# 这个目录一章一个目录：每章一份同编号的可执行讲解（唯一规格源 <章>/cells.py）；
# 规格是唯一真相源，两份产物（.ipynb 与逐字相同的同名 .py）都由生成器算出，不手改。
TECH_DETAIL = REPO_ROOT / "docs" / "project" / "architecture" / "tech-detail"
CHAPTERS = sorted(path for path in TECH_DETAIL.iterdir()
                  if path.is_dir() and path.name[:2].isdigit())
print("仓库根目录:", REPO_ROOT.name)
print("讲解目录:", TECH_DETAIL.relative_to(REPO_ROOT).as_posix(), "（共", len(CHAPTERS), "章）")
print("Python:", sys.version.split()[0])
'''
        ),
        markdown(
            '''
## 1. 真实的依赖边：扫出来，不是抄文档

扫描的单位是包（`src/<包名>/`），一条边 = "这个包 import 了那个包"。

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

# 包清单**从文件系统推出来**，不手抄。手抄的那份已经漂移过：src/provenance 是真实存在的
# 第八个包（src/policy/check.py 在模块级 import 了它），却因为不在清单里，整条边被 file_imports
# 静默丢掉——于是"判定核心没有模块级出边"这句断言，对着与它相反的代码照样通过。
# 判据是"src 下、含 .py 的一级目录"：src/policy 是命名空间包（没有 __init__.py），按 __init__.py
# 筛会把判定核心自己漏掉；*.egg-info 是本地可编辑安装留下的构建产物，不是包。
PACKAGES = tuple(
    sorted(
        path.name
        for path in SRC.iterdir()
        if path.is_dir() and not path.name.endswith(".egg-info") and any(path.rglob("*.py"))
    )
)
assert PACKAGES, f"{SRC} 下没有发现任何包：src 布局变了？"
print("扫描的顶层包：" + ", ".join(PACKAGES))


def from_targets(node, package):
    """把一条 from-import 解析成"仓库内部顶层包名"候选。

    相对导入必须**按本文件所在的包回溯 level-1 层**再判断：只看 node.module 会把
    `from .adapters.base import probe_tool`（真实目标是 validators.adapters）记成
    "validators 依赖顶层包 adapters"——一个并不存在的同名顶层包，于是凭空多出一条边、
    入边与 I = Ce/(Ca+Ce) 跟着一起失真。
    """
    if node.level == 0:
        return [node.module or ""]
    drop = node.level - 1
    if drop > len(package):
        # 回溯越过了顶层：不可能指向仓库里的某个顶层包（这种写法本身也是错的）。
        return []
    base = package[: len(package) - drop]
    if base:
        # 仍在同一个顶层包内（包内相对导入）：目标是本包，不产生跨包边。
        return [base[0]]
    # 正好回溯到顶层：module 的第一段就是顶层包名。
    return [node.module or ""]


def _is_type_checking(test):
    """`if TYPE_CHECKING:` 的判断（含 `typing.TYPE_CHECKING` 形态）。"""

    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def module_level_imports(tree):
    """模块**导入期真的会执行**的 import 节点（返回 id 集合）。

    只看 `tree.body` 的直接子节点，会把 `try: import x / except ImportError: ...`、
    `if sys.version_info >= ...: import y` 这类整块算成"延迟导入"——它们在导入期就会执行，
    分量与"函数内真正调用时才导入"**正好相反**（前者是改不掉的硬约束，后者是可以商量的豁免）。

    规则：函数 / 类体不算（那才是延迟导入）；`if TYPE_CHECKING:` 的体在运行时根本不执行，
    两边都不算；`try` / `with` 的各个分支照算（它们在导入期会走到其中之一）。
    """

    found: set[int] = set()

    def walk(statements) -> None:
        for node in statements:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(node, ast.If):
                if not _is_type_checking(node.test):
                    walk(node.body)
                    walk(node.orelse)
                continue
            if isinstance(node, ast.Try):
                walk(node.body)
                walk(node.orelse)
                walk(node.finalbody)
                for handler in node.handlers:
                    walk(handler.body)
                continue
            if isinstance(node, (ast.With, ast.AsyncWith)):
                walk(node.body)
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                found.add(id(node))

    walk(tree.body)
    return found


def file_imports(path):
    """一个文件 import 到的仓库内部顶层包，返回 (模块级目标, 函数内目标)。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top_level = module_level_imports(tree)
    package = path.relative_to(SRC).parts[:-1]  # 本文件所在的包（__init__.py 同理）
    eager, lazy = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = from_targets(node, package)
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

上面打印出来的边只说明方向，真正要守的是下面三条——它们都能被断言，不是口号：

1. **判定核心的业务模块没有模块级出边**：`src/policy` 里除 CLI 装配点 `check.py` 外，
   一个包都不 import（不导入 Web 框架 / Agent SDK / 工作流框架）；
2. **入口层入度为 0**：没有任何包 import `policy_api` 或 `orchestration`——删掉编排层，平台照常独立运行；
3. **工作流框架只有一个导入点**：只有 `orchestration/langgraph_engine.py` 导入 langgraph，
   而且是在**构造引擎时**才导入（没装就失败关闭，不静默回落到别的实现）。

第 1 条在本仓库有一个**真实的例外**，下面会把它精确地挡在一个文件里——这正是"包级统计"
不够用的地方：算到包级，它看起来像"核心层依赖验证器层与溯源层"；算到文件级，它只是 CLI 的装配点
（`check.py` 装配验证器注册表与读数上下文，判定逻辑本身一行都不依赖它们）。
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

# 判定核心的"业务模块"一个出边都不许有；例外只允许出现在 CLI 装配点 check.py，
# 且只指向它的两个装配对象：验证器注册表（validators）与读数上下文（provenance）。
dirty_core = [name for name in policy_edges if Path(name).name in core_files]
assert not dirty_core, f"判定核心的业务模块出现了出边：{dirty_core}"
assert set(policy_edges) == {"src/policy/check.py"}, f"出边来源不止 CLI 装配点：{sorted(policy_edges)}"
assert policy_edges["src/policy/check.py"][0] == ["provenance", "validators"], policy_edges["src/policy/check.py"]

# 第 2 条的说法是**绝对的**（"没有任何包 import policy_api 或 orchestration"），
# 所以判据也必须覆盖两类边：只看 eager 的话，某个包在函数里 `import policy_api` 同样违反
# 那句话，断言却会通过——"入口层入度为 0"于是变成一句没有对应检查的口号。
for package in PACKAGES:
    hit = (edges[package]["eager"] | edges[package]["lazy"]) & {"policy_api", "orchestration"}
    assert not hit, f"{package} 反向依赖了入口层（含函数内延迟导入）：{sorted(hit)}"


def framework_importers(framework, *, root=SRC):
    """**平台运行时代码（`src/`）**里真的导入了某个框架的文件清单。

    含 importlib.import_module("框架…") 这种延迟导入。范围刻意只到 `src/`：`tools/` 与 `tests/`
    是开发期仪器（`api_loop` / `orchestration_loop` 会起真实 uvicorn 跑协议闭环），它们用 Web
    框架是**有意为之**，不属于"平台运行时代码不许依赖 Web 框架"这句话的射程。
    """

    def callee_name(func):
        """把调用目标渲染成点分名（`im` / `importlib.import_module`）。"""

        parts = []
        current = func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def dynamic_import_names(tree):
        """本文件里"就是 importlib.import_module"的**本地名字**（含别名）。

        `from importlib import import_module as im` 之后 `im("langgraph")` 同样是延迟导入工作流
        框架，而只看 `func.id == "import_module"` 会整个漏掉——"框架导入点唯一"于是可能在别名
        写法下被违反，检查却仍然是绿的。`src/validators/python_ast.py` 的依赖提取早就维护了同一张
        别名表（`_MODULE_BINDINGS` + 文件内绑定名），这里是它的最小版本。

        内置的 `__import__("langgraph")` 也算一条：它是同一件事的另一种写法，漏掉它等于给
        "只在这一个导入点"留了一个后门。
        """

        names = {"importlib.import_module", "__import__"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "") == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        names.add(alias.asname or "import_module")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "importlib":
                        names.add((alias.asname or "importlib") + ".import_module")
        return names

    def touches(node, names):
        if isinstance(node, ast.Import):
            return any(alias.name.split(".")[0] == framework for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            return (node.module or "").split(".")[0] == framework
        if isinstance(node, ast.Call) and callee_name(node.func) in names:
            first = node.args[0] if node.args else None
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                return False
            # **按第一段精确比对**：`startswith` 会把 `import_module("langgraphx.graph")` 也算成
            # 框架导入——将来真出现同前缀的包，就会误报"导入点唯一"被破坏。
            return first.value.split(".")[0] == framework
        return False

    found = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = dynamic_import_names(tree)
        if any(touches(node, names) for node in ast.walk(tree)):
            found.append(path.relative_to(REPO_ROOT).as_posix())
    return found


web = sorted(set(framework_importers("fastapi") + framework_importers("uvicorn")))
workflow = framework_importers("langgraph")

print(pad("检查项", 24) + "结果")
print("-" * 88)
print(pad("Web 框架导入点（src/）", 24) + (", ".join(web) or "（无）"))
print(pad("工作流框架导入点（src/）", 24) + (", ".join(workflow) or "（无）"))
print()

# **自证这把尺子**：上面两行是读数，而读数本身也得能被证明是活的——在本次独占的临时目录里造两个
# 文件：一个用 `from importlib import import_module as im` 的别名写法（必须被认出），一个调用同前缀
# 的包名 `langgraphx`（必须**不**被误认成 langgraph）。没有这一步，"导入点唯一"只是在今天这棵树上
# 偶然成立，尺子对别名写法是不是瞎的没人知道。
probe_root = REPO_ROOT / ".tmp" / "tech-detail" / "00" / "framework-probe"
probe_pkg = probe_root / "policy_import_probe"
probe_pkg.mkdir(parents=True, exist_ok=True)
(probe_pkg / "__init__.py").write_text("", encoding="utf-8", newline="")
(probe_pkg / "aliased.py").write_text(
    """from importlib import import_module as im


def load():
    return im("langgraph.graph")
""",
    encoding="utf-8",
    newline="",
)
(probe_pkg / "prefixed.py").write_text(
    """from importlib import import_module


def load():
    return import_module("langgraphx.graph")
""",
    encoding="utf-8",
    newline="",
)
(probe_pkg / "builtin.py").write_text(
    """def load():
    return __import__("langgraph.graph")
""",
    encoding="utf-8",
    newline="",
)
probe_hits = framework_importers("langgraph", root=probe_root)
expected_probe = sorted(
    (probe_pkg / name).relative_to(REPO_ROOT).as_posix()
    for name in ("aliased.py", "builtin.py")
)
assert probe_hits == expected_probe, probe_hits
print("自证：别名写法与内置 __import__ 都被认出、同前缀包名不被误认 →", len(probe_hits), "个文件")

# **在平台运行时代码（src/）里**：Web 框架只允许出现在传输层（policy_api），
# 工作流框架只允许出现在编排层的引擎适配文件。这两句话的射程就是上面那次扫描的范围——
# 写成无限定词的话，`tools/api_loop.py` / `tools/orchestration_loop.py` 里那两处
# `import uvicorn`（开发期闭环要起真实服务器）会让它当场变成假话。
assert web and all(path.startswith("src/policy_api/") for path in web), web
assert not [path for path in web if path.startswith("src/policy/")], web
assert workflow == ["src/orchestration/langgraph_engine.py"], workflow

# 第 3 条不变量的**另一半**：不只是"只有一个导入点"，还得是"**构造引擎时**才导入"。
# 模块级 import langgraph 同样满足上面那条等式，却把契约从"没装 → 一次显式的
# EngineUnavailableError"变成"没装 → 进程 import 就炸"（连参考引擎的回退都轮不到）。
# 判据：那个文件里指向 langgraph 的 import / import_module 调用**都不在模块导入期会执行的位置**。
engine_tree = ast.parse((REPO_ROOT / workflow[0]).read_text(encoding="utf-8"))
engine_module_level = module_level_imports(engine_tree)
eager_framework_refs = []
for node in ast.walk(engine_tree):
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        names = [node.module or ""]
    elif isinstance(node, ast.Call):
        first = node.args[0] if node.args else None
        names = [str(first.value)] if isinstance(first, ast.Constant) else []
    else:
        continue
    if any(name.split(".")[0] == "langgraph" for name in names) and id(node) in engine_module_level:
        eager_framework_refs.append(node.lineno)
assert not eager_framework_refs, (
    "langgraph 的引用出现在了模块导入期会执行的位置（行号）：" + repr(eager_framework_refs)
)
print("第 3 条的另一半：langgraph 只在函数体内被导入（构造引擎时），没装是显式失败而不是 import 崩溃。")
print("三条不变量全部成立：核心业务模块零出边、入口层入度为 0、框架导入点唯一。")
'''
        ),
        markdown(
            '''
## 3. 从"包"回到"层"

同一个仓库有两套说法：**六层**（① 消费方 / 入口 … ⑥ 证据与门禁）与代码里的**包**。
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

`tech-detail/` **一章一个目录**（`00-技术总览/` … `09-能不能成为规则/`）：一章里有一份同编号的
可执行讲解，两份产物（`.ipynb` 与逐字相同的同名 `.py`）与这一章自己的内容源 `cells.py` 都放在一起。
下面这个索引是从目录**现场读出来的**——不是抄来的清单；新增一章，这里就多一行，
少一份 notebook 会被明确指出来。
'''
        ),
        code(
            '''
# 读目录得到索引：一章一个目录，章内 notebook（.ipynb）与同内容的 .py 按编号一一对应。
notebooks = sorted(path.stem for chapter in CHAPTERS for path in chapter.glob("*.ipynb"))
scripts = {path.stem for chapter in CHAPTERS for path in chapter.glob("*.py")} - {"cells"}

print(pad("编号讲解 notebook", 34) + "同内容的 .py")
print("-" * 60)
for stem in notebooks:
    print(pad(stem, 34) + ("有" if stem in scripts else "缺（还没生成）"))
print()

assert len(notebooks) == 10, f"讲解的清单变了（{len(notebooks)} 份）：索引与文档要跟着改"
missing = sorted(set(notebooks) - scripts)
extra = sorted(scripts - set(notebooks))
if extra:
    print("没有同名 notebook 的 .py:", ", ".join(extra))
if missing:
    print(f"尚未生成 {len(missing)} 份：" + ", ".join(missing))
else:
    print(f"{len(notebooks)} 份讲解都有逐字相同的纯 Python 版。")
'''
        ),
        markdown(
            '''
## 小结

- 依赖方向是**代码事实**，不是文档承诺：边由 `ast` 现场扫出来，三条不变量靠断言守住；
- `I = Ce/(Ca+Ce)` 从上到下单调变小——入口层最"易变"（没有人依赖它），判定核心最"稳定"（所有路径都要找它）；
- 一个包级统计不够用的实例：`src/policy/check.py` 模块级 import 了 `validators.registry` 与
  `provenance.reading_context`（都是 CLI 装配需要），但判定核心的业务模块
  （engine / loader / scope / models / context / evidence / checkers）**零出边**。
  包级表会说"核心依赖验证器层与溯源层"，文件级一看，那只是组合根；
- 包清单本身也**不能手抄**：它是从 `src/` 现场推出来的——少写一个包，指向它的边就整条消失，
  而断言会继续通过（`src/provenance` 就是这么被漏掉过的）。

接下来按兴趣往下走：`01-判定核心-Policy-Engine.ipynb`（一次判定怎么算出来）、
`04-受控执行.ipynb`（允许之后副作用怎么被管住）、`09-能不能成为规则.ipynb`（一段文档要求够不够格成为规则）。
'''
        ),
    ),
)

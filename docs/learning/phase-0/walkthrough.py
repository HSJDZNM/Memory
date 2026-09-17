"""Phase 0 学习手册的纯 Python 版本（由 tools/build_learning_notebook.py 生成）。

notebook 里每一段代码都按顺序出现在下面；直接运行本文件即可复现全部输出：

    python docs/learning/phase-0/walkthrough.py

内容改动请修改 tools/build_learning_notebook.py 后重新生成，不要直接编辑本文件。
"""

# ----------------------------------------------------------------------------
# # Phase 0 学习手册：一条规则从 YAML 到 PASS/FAIL
#
# 这份 notebook 用**实际运行的代码**解释 Engineering Policy Platform 的 Phase 0 到底做了什么。
# 它不引入新代码，只调用仓库里已经通过测试的模块，因此每一段输出都可以自己重跑验证。
#
# ## Phase 0 要证明的事
#
#     YAML Rule -> Rule Loader -> Policy Engine -> PASS / FAIL -> Test Evidence
#
# 一句话：**一个程序能读取机器可执行规则，并对固定上下文稳定地给出 PASS/FAIL。**
# 本阶段只有一条规则 ARCH-001：Controller 不得直接依赖 Repository。
#
# ## 阅读路线
#
# | 小节 | 回答的问题 |
# | --- | --- |
# | 0 | 跑这份 notebook 需要什么前提 |
# | 1 | 规则长什么样，为什么它是数据而不是提示词 |
# | 2 | Loader 把 YAML 变成什么，为什么拒绝未知字段 |
# | 3 | 模型为什么不可变 |
# | 4 | 匹配器如何用表驱动得出 PASS/FAIL |
# | 5 | 结果是否稳定、可排序、可审计 |
# | 6 | CLI 的退出码怎么用 |
# | 7 | JSON 输出如何对齐 PolicyDecision 契约 |
# | 8 | 验收证据里记录了哪些可重放信息 |
# | 9 | 边界：Phase 0 明确不做什么 |
#
# 每个代码单元后面都有一个小结，说明"这段输出说明了什么"。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 预备知识：看懂下面的代码只需要知道这些
#
# 这一节写给"Python 看过一点但没写过项目"的读者。看不懂代码时回到这里查，不用去翻教材。
#
# ### 1. 函数、类、模块这三个词
#
# | 词 | 一句话解释 | 在这里的样子 |
# | --- | --- | --- |
# | 模块 | 一个 .py 文件就是一个模块，可以被别的文件借用 | `src/policy/models.py` |
# | 包 | 一个装着多个模块的文件夹，用 import 取用 | `from policy import models` |
# | 函数 | 有输入、有输出、可反复调用的代码块 | `evaluate(规则集, 上下文)` |
# | 类 | 自定义的数据类型，描述"一个东西有哪些属性" | `class PolicyContext:` |
# | 实例 | 用类造出来的具体对象 | `PolicyContext(request_id=...)` |
#
# Python 用缩进表示"这几行属于上面那句"。看到一段代码整体向右缩进，就说明它们从属于上一行。
#
# ### 2. 这些"模型"是什么
#
# 项目用 pydantic 库定义数据。`class Rule(...)` 读作："规则这种数据，必须有 id、version、scope 等字段，
# 且每个字段的类型和取值都要符合规定"。构造实例时 pydantic 立刻检查，不合格就直接报错，
# 不会等到程序跑一半才发现数据是坏的。这就是本项目反复出现的"校验"。
#
# 还会遇到两个不常见的写法：
#
# - `@property`：把方法伪装成属性。写 `rule.canonical_id` 而不是 `rule.canonical_id()`，读起来更像名词；
# - `frozen=True`：把对象"冻住"。造好之后不允许再改字段，改就报错。后面单元 4 会亲手试一次。
#
# ### 3. 读懂 YAML 的缩进
#
# 规则文件用 YAML 写，缩进表示从属关系：
#
# ```yaml
# scope:
#   layer: controller      # 这一行是 scope 的子项
# ```
#
# 同一层级的字段左对齐，冒号后面的值可以是字符串、数字、列表（用 - 开头）或嵌套的字段。
#
# ### 4. 术语速查（本书反复出现）
#
# | 术语 | 通俗解释 |
# | --- | --- |
# | 上下文 context | 这次检查的对象：哪个文件的、哪一层、依赖了谁 |
# | 规则 rule | 一条可执行的约定，例如"Controller 不许直接依赖 Repository" |
# | scope 范围 | 规则管谁；不在范围内的文件，规则根本不会被拿来判断 |
# | 违规 violation | 规则被违反后产生的一条记录 |
# | 证据 evidence | 违规的依据，说明"哪个文件的哪个依赖值违反了哪条规则" |
# | 决策 decision | 三种结果之一：allow 通过、allow_with_warnings 通过但告警、block 阻断 |
# | 退出码 | 程序结束时留给操作系统的数字，脚本用它判断成功或失败 |
# | 哈希 hash | 把一段内容压成固定长度的指纹；内容改一个字，指纹就变 |
#
# ### 5. 一个反复出现的比较
#
# `repository` 和 `Repository` 在本书里是同一个东西（比较前统一转小写），
# 但 `order_repository` 和 `order-repository` 不是同一个东西（故意不做符号互转）。
# 原因在单元 5 小结里说明。
#
# 准备好了就从下一单元开始。每个新概念第一次出现时都会当场解释，不需要提前记住什么。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 笔记本文件放在 `docs/learning/phase-0/` 里，而真正要 import 的代码在 `src/policy/` 里。
# 所以第一件事是把 `src/` 目录告诉 Python，让它能 `import policy`。
# 顺手把这次要反复用的"规则集"加载一次，后面的单元直接复用，不重复读文件。
#
# 读代码时注意三件事：
#
# 1. 路径用 `Path` 表示（比字符串安全，`/` 可以拼接路径，`is_dir()` 可以问"这是目录吗"）；
# 2. `sys.path.insert(0, SRC_DIR)` 是"把 src 加到 Python 的搜索目录最前面"；
# 3. `loader.load_rule_set(...)` 是本次唯一的文件读取动作，后面的单元都不再碰磁盘。
# ----------------------------------------------------------------------------

# 0. 准备运行环境：让 notebook 找到仓库里的 src/policy

# import 就是把别人写好的模块借过来用。json 用来处理 JSON 文本，
# sys 用来改 Python 自己的运行参数，Path 用来表示文件路径。
import json
import os  # 用来临时切换工作目录（示例单元需要）
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    print("函数用途:", "向上找到含 policies/ 的目录；找不到就退回当前工作目录")

    # start.parents 是"上级目录、上上级目录……"的序列；
    # 从 notebook 所在目录一路往上找，谁下面有 policies/ 子目录，谁就是仓库根目录。
    # 这样写的好处：笔记本无论放在仓库哪一层都不会失效。
    for candidate in (start, *start.parents):
        if (candidate / "policies").is_dir():  # 存在这个子目录吗
            return candidate
    return Path.cwd()  # 实在找不到，就用当前工作目录兜底


# Path.cwd() 是"当前工作目录"。如果从仓库根目录启动 notebook，它本身就能用于判断。
NOTEBOOK_DIR = Path.cwd() if Path("policies").is_dir() else Path("docs/learning/phase-0")
REPO_ROOT = find_repo_root(NOTEBOOK_DIR.resolve())  # resolve() 把路径变成绝对路径
SRC_DIR = REPO_ROOT / "src"  # 运算符 / 在这里表示拼接路径，不是除法

# Python 按 sys.path 里的目录顺序找模块。把 src 放到最前面，import policy 才找得到。
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 下面四个是本项目的核心模块，后面每个单元都会用到其中一个：
#   models 定义数据结构（规则、上下文、违规、结果）
#   loader 负责读 YAML 并校验成模型
#   engine 负责判断是否违规
#   check  是命令行入口，也是把三者串起来的地方
from policy import check, engine, loader, models

# 一次性把 policies/ 目录下的规则都加载进来，得到 RuleSet（规则集）。
# 返回的 rule_set 之后每个单元都会复用，所以这里不会重复读文件。
rule_set = loader.load_rule_set([REPO_ROOT / "policies"], repo_root=REPO_ROOT)

print("仓库根目录:", REPO_ROOT)
print("核心库目录:", SRC_DIR)
print("规则集:", rule_set.ids, "来自", list(rule_set.source_paths))
print("提示: 全部单元应在数秒内执行完；本单元应当立刻打印上面几行。")


# 表格对齐用的小工具：中文（全角）字符在等宽字体里占 2 列，而 f"{文本:<10}"
# 数的是"字符个数"——中英混排时列会被挤歪。按显示宽度补空格才是对的。
import unicodedata


def display_width(text):
    """文本在等宽字体里占多少列：全角/宽字符算 2 列，其余算 1 列。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(text))


def pad(text, width, align="left"):
    """按显示宽度把文本补齐到 width 列，让每一列都从同一个位置开始。"""
    text = str(text)
    blanks = " " * max(0, width - display_width(text))
    if align == "right":
        return blanks + text
    if align == "center":
        left = len(blanks) // 2
        return blanks[:left] + text + blanks[left:]
    return text + blanks

# ----------------------------------------------------------------------------
# ### 如果单元一直不返回，先看这里
#
# 上面那个单元应当在**一秒内**打印几行。如果它长时间没有输出，问题几乎总是**内核没有启动**，
# 而不是代码在计算：本手册没有任何循环、网络调用或大文件操作。
#
# 已知的一个触发条件是：在受限沙箱（文件系统只允许写工作区）里运行 Jupyter。
# 内核启动时需要给连接文件设置 ACL，被拒绝后 Jupyter 只会一直等待，不一定会报错：
#
#     ipykernel: error (5, 'SetFileSecurity', 'Access is denied.')
#
# 遇到这种情况，按顺序尝试：
#
# 1. 在**普通** Jupyter / VS Code 里打开本 notebook；
# 2. 或直接运行同内容的纯 Python 版本：`python docs/learning/phase-0/walkthrough.py`，
#    它按顺序执行每个单元并在进程内打印同样的结果；
# 3. 或先用 `README.md` 里的 CLI 命令做最小验证。
#
# 三条路径使用同一套模块，结论一致。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# **小结**：核心库是一个普通 Python 包（src 布局），不需要安装就能被 notebook 导入。
# 这也是设计原则之一：Policy Engine 保持普通库，不依赖 Agent 框架、Web 框架或向量数据库。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 1. 规则是数据
#
# Phase 0 的规则全部写在 policies/**/*.yaml 里。先看**文件原文**，再看它被解析成什么。
#
# 注意字段的分工：
#
# - scope 决定这条规则管谁（这里是 python 语言的 controller 层）；
# - severity 决定违规有多严重（error 会 block，warning 只告警）；
# - enforcement 声明"用确定性检查器执行"，而不是让模型自由判断；
# - rule.forbidden_dependency 是唯一的判定数据，其余字段都是身份、范围与解释。
#
# ### 这一段代码要做什么
#
# 把规则文件当普通文本读出来打印，不做任何解析。目的是先建立印象：
# 规则就是一份可读的配置文件，没有任何魔法，也不需要运行程序才能理解。
#
# 用到两个新东西：`pathlib` 的路径对象，和 `read_text()`（读文本文件）。
# `print("-" * 72)` 是打印 72 个短横线当分隔线。
# ----------------------------------------------------------------------------

# 1. 直接读文件：这是人能审查的原始形态

# REPO_ROOT / "policies" / "architecture" / "ARCH-001.yaml" 逐级拼接出规则文件路径。
rule_path = REPO_ROOT / "policies" / "architecture" / "ARCH-001.yaml"

# relative_to() 把绝对路径改写成相对仓库根目录的短路径，输出更干净。
print(f"文件: {rule_path.relative_to(REPO_ROOT).as_posix()}")
print("-" * 72)  # 打印 72 个短横线，纯粹为了好看

# read_text(encoding="utf-8") 一次性读出整个文件；中文必须显式指定编码，否则在 Windows 上会乱码。
print(rule_path.read_text(encoding="utf-8"))

# ----------------------------------------------------------------------------
# **小结**：规则是可 diff、可评审、可版本化的一等公民。
# 共享对话或外部文档不能直接当规则用：source.kind 只接受本地来源（project-policy / standard）。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 把刚才那份 YAML 交给加载器，看它变成什么。两个关键点：
#
# - `load_rules` 返回的是"已加载的规则"列表，每一项同时带着来源文件路径，方便审计；
# - `rule` 是 pydantic 模型实例，字段可以用点号读，也可以整体导出成字典（`model_dump()`）。
#
# 输出里出现的 `RuleScope(language='python', layer='controller')` 是模型的默认打印形式：
# 类型名后面括号里列字段，字符串带单引号。它不是错误，也不是 JSON。
# ----------------------------------------------------------------------------

# 2. 通过 Loader 读取：YAML 变成不可变模型

# load_rules 会遍历目录下所有 .yaml 文件，逐个解析并校验；
# repo_root 参数告诉它"仓库根在哪"，这样错误信息和来源路径都是仓库相对路径。
loaded = loader.load_rules(REPO_ROOT / "policies", repo_root=REPO_ROOT)

# loaded 是列表，[0] 取第一条；每条记录有两个字段：.rule（规则模型）和 .repo_path（来源文件）。
rule = loaded[0].rule

print("加载到的文件:", [item.repo_path for item in loaded])  # 列表推导：把每条记录的来源路径收集成列表
print("审计身份 id@version:", rule.canonical_id)  # @property 方法，用起来像读属性
print("名称:", rule.name)
print("范围 scope:", rule.scope.model_dump())  # 导出成普通字典便于查看
print("严重级别 severity:", rule.severity.value)  # 枚举用 .value 取原始字符串
print("执行方式 enforcement:", rule.enforcement.model_dump())
print("禁止的依赖:", list(rule.rule.forbidden_dependency))  # 元组转列表只是为了让输出好看
print("违规提示语:", rule.message)

# ----------------------------------------------------------------------------
# **小结**：Loader 把 YAML 变成不可变模型，并同时记住来源文件路径。
# 审计身份是 编号@版本，来源路径回答"这条规则从哪来"——两者缺一不可。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 故意把 `severity` 拼成 `sevrity`，看程序会不会装作没看见。
# 预期是**拒绝加载并报错**，因为治理系统最怕的不是误报，而是规则悄悄失效。
#
# 这段代码演示了三个 Python 语法点：
#
# - `try / except / else`：先尝试执行，出错时跳到 except，没出错才执行 else；
# - `raise AssertionError(...)`：主动抛错。这里的意思是"如果程序真的放过了拼写错误，就当作严重缺陷报出来"；
# - 文件写在 `.tmp/notebook-demo/` 下：这是仓库约定的临时目录，随时可删。
# ----------------------------------------------------------------------------

# 3. 加载器拒绝拼写错误，而不是静默忽略

# ValidationError 是 pydantic 的"数据不合格"异常类型，下一个单元会用到它。
from pydantic import ValidationError

# 把真实规则文件读进内存，再把 severity 替换成拼错的形式，写到一个只有它的目录里。
# 两个要点：
#   1. 仓库里不放坏规则，临时文件只写进 .tmp/；
#   2. 坏文件放在独立的 broken/ 子目录中，这样只会被本单元读到，
#      不会污染 .tmp/ 下其它单元或工具的规则加载。
demo_dir = REPO_ROOT / ".tmp" / "notebook-demo" / "broken"
demo_dir.mkdir(parents=True, exist_ok=True)  # parents=True 表示父目录不存在就一起建；exist_ok=True 表示已存在不报错
broken = demo_dir / "ARCH-001-typo.yaml"
text = rule_path.read_text(encoding="utf-8").replace("severity:", "sevrity:")
broken.write_text(text, encoding="utf-8")

try:
    # 只加载这个子目录，因此读到的就是上面那份坏文件
    loader.load_rules(demo_dir, repo_root=REPO_ROOT)
except loader.LoaderError as error:
    # LoaderError 是加载器统一的报错类型；错误信息里必须带文件位置与字段名，
    # 因为下一个人要照着这条信息去修文件。
    print("已按预期拒绝：")
    print(str(error).splitlines()[0][:200])  # 只显示第一行、最多 200 个字符，避免刷屏
else:
    # else 分支只有在 try 里没有抛异常时才会走到，说明坏规则被放过了。
    raise AssertionError("拼错字段竟然通过了加载：这与未知字段必须报错的约定冲突")

# ----------------------------------------------------------------------------
# **小结**：extra="forbid" 让拼写错误在加载阶段就暴露，而不是让规则悄悄失效。
# 在治理系统里，"一条规则忘了生效"比"一条规则误报"危险得多，所以宁可启动失败。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 2. 模型不可变
#
# 所有核心模型都是 frozen=True 的 pydantic 模型。
# 引擎因此不可能在评估过程中修改规则或上下文，相同输入必然得到相同结论。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 上一单元说模型是 `frozen=True`（冻结的），这里亲手验证一次：
# 试着把规则的 `version` 从 1 改成 2，预期**失败**。
#
# 为什么要冻结？因为审计身份是 `ARCH-001@1`——规则编号加版本号。
# 如果程序运行中被改了版本，日志里记录的"当时用的是哪条规则"就不再可信。
# 冻结让"读到的规则"和"审计里的规则"永远是同一个。
# ----------------------------------------------------------------------------

# 4. 试着修改一条已加载的规则：必须失败

# 注意这里没有 if 判断，直接尝试赋值：故意让它出错。
try:
    rule.version = 2  # type: ignore[misc]  # 本行故意违反类型约定，用来演示失败
except ValidationError as error:
    # errors() 返回一个列表，每项描述一个字段错误；[0] 取第一个。
    # 每个错误项里 type 是错误种类，msg 是人能读的说明。
    first = error.errors()[0]
    print("修改被拒绝，模型是冻结的：")
    print("   ", first["type"], "-", first["msg"])
else:
    # 没有抛异常说明真的改成功了，那这条规则就不再可信，必须当成缺陷报出来。
    raise AssertionError("规则被修改成功了，这破坏了审计身份 id@version 的稳定性")

# ----------------------------------------------------------------------------
# **小结**：模型冻结之后，规则一旦加载就不会在运行中被改动，
# 日志里记录的版本与实际用来判断的版本永远是同一个。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 3. 表驱动匹配：Engine 的真相表
#
# 匹配器只做一件事：**在 scope 命中的规则里，检查上下文依赖是否落在 forbidden_dependency 中。**
# 它不读文件、不访问全局状态、不调用 LLM，所以结果完全由入参决定。
#
# 下面这张表就是 Phase 0 的核心契约，tests/unit/test_engine.py 里固定了同一张表。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 先写一个 5 行的小函数 `context`，用来造"被检查的对象"；再把这 5 种情况放进一张表，
# 循环跑一遍，把结果排成表格。这是本项目判断逻辑的全部形态——**没有任何隐藏规则**。
#
# 三个语法点：
#
# - 函数用 `def 名字(参数):` 定义，调用时写 `context("controller", ["repository"])`；
# - `for ... in cases:` 逐个取出表里的三元组（层、依赖、说明）；
# - `f"{变量:<11}"` 是格式化输出，`:<11` 表示"左对齐占 11 个字符宽"，用来对齐表格。
#
# 输出里 `decision` 列只看三种值：`allow`（通过）、`allow_with_warnings`（通过但有告警）、`block`（阻断）。
# ----------------------------------------------------------------------------

# 5. 五组固定输入 -> 稳定结论（表驱动）


def context(layer, dependencies):
    print("函数用途:", "构造一个最小 PolicyContext：安全关键字段没有默认值，必须显式给出")

    # request_id 用来把一次检查的检索、判断、修复串起来；这里固定成 learn-001 方便对比。
    # file / layer / dependencies 是判断真正用到的输入。
    return models.PolicyContext(
        request_id="learn-001",
        file="src/order/controller.py",
        language="python",
        layer=layer,
        dependencies=dependencies,
    )


# 每个元素是三元组：(架构层, 直接依赖列表, 说明)。表就是 Phase 0 的核心契约，
# 单元测试 tests/unit/test_engine.py 里固定的是同一张表。
cases = [
    ("controller", ["repository"], "违反：Controller 直接依赖 Repository"),
    ("controller", ["service"], "合规：Controller 只依赖 Service"),
    ("service", ["repository"], "规则范围不匹配：规则只管 controller"),
    ("controller", ["Repository"], "大小写不同，但规范化后仍然命中"),
    ("controller", [], "没有依赖，不违反"),
]

header = (
    pad("layer", 11)
    + pad("dependencies", 16)
    + pad("decision", 21)
    + pad("violations", 11)
    + "说明"
)
print(header)
print("-" * 100)
for layer, dependencies, note in cases:
    ctx = context(layer, dependencies)  # 造上下文
    result = engine.evaluate(rule_set, ctx)  # 判断：规则集 + 上下文 -> 结果
    # 把违规的规则编号拼成字符串；没有任何违规时 join 得到空串，用 or "-" 显示成短横线。
    ids = ",".join(v.rule_id for v in result.violations) or "-"
    print(
        pad(layer, 11)
        + pad(dependencies, 16)
        + pad(result.decision.value, 21)
        + pad(ids, 11)
        + note
    )

# ----------------------------------------------------------------------------
# **小结**：三条结论与 Phase 0 的验收标准一致——
#
# 1. Controller + repository -> BLOCK，命中 ARCH-001；
# 2. Controller + service -> ALLOW；
# 3. Service + repository -> ALLOW，因为规则的 scope.layer 只声明了 controller（范围不匹配，不是"白名单放行"）。
#
# 第 4 行固定了规范化策略：Repository 与 repository 等价（去首尾空白 + 小写）。
# 但 order_repository 与 order-repository **不**等价：刻意不做分隔符互转，避免把合法包名误判成命中。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 4. 违规的结构化证据
#
# 反馈给 Agent 的不是一句自由文本，而是带 rule_id、rule_version、severity、evidence 的结构化记录。
# 后续阶段（修复、审计、API）都依赖这个形状。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 上一单元只看结论（PASS/FAIL），这一单元把"为什么"拆开看。
# `json.dumps(..., ensure_ascii=False)` 的作用是：把字典转成 JSON 文本，
# 并允许中文按原样显示（默认会把中文转成一串编码，人读起来很痛苦）。
# ----------------------------------------------------------------------------

# 6. 证据可以定位到文件、规则与依赖值

# 这是一次确定的违规判断：controller 层依赖了 repository。
result = engine.evaluate(rule_set, context("controller", ["repository"]))

# violations 是列表；本场景只命中一条规则，取第一条即可。
violation = result.violations[0]

print("decision:", result.decision.value)  # 三种决策之一
print("request_id:", result.request_id, "(一次请求一个，用于串联检索/决策/执行)")
print("matched_rules:", result.matched_rules)  # 范围命中的规则，格式为 ID@版本
print("排序键 sort_key:", violation.sort_key)  # 决定多条违规谁先谁后，下一单元展开
print("evidence:", json.dumps(violation.evidence.model_dump(), ensure_ascii=False))

# ----------------------------------------------------------------------------
# **小结**：结论不是一句"不通过"，而是带规则身份、版本、严重级别与证据的记录；
# 后面的阶段把这条记录写进审计链，让它可以被重放和比对。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 前面的场景只有一条规则，看不出顺序问题。这里造两条规则同时命中，跑三遍，
# 确认每次输出顺序都一样——顺序稳定是能被自动比对的前提（否则每次 diff 都在变）。
#
# 新语法只有一个：model_copy(update=...)，意思是照着这个对象复制一份，只改指定字段。
# 用它而不是手写新规则，是为了让演示对象与真实规则保持同样的结构。
# ----------------------------------------------------------------------------

# 7. 稳定排序：多条规则同时命中时，输出顺序也是契约的一部分


def extra_rule(rule_id, forbidden):
    print("函数用途:", "用真实规则做原型，只换 id 与禁止依赖，避免在 notebook 里造假规则")

    # model_copy(update=...) 复制原对象并替换指定字段，是冻结模型的"改法"：
    # 直接赋值不允许，只能复制出一个新对象。forbidden 是列表，转成元组以符合模型要求。
    return rule.model_copy(
        update={
            "id": rule_id,
            "rule": rule.rule.model_copy(update={"forbidden_dependency": tuple(forbidden)}),
        }
    )


# RuleSet 装两条规则：ARCH-010 禁止 orm 与 repository，ARCH-002 只禁止 repository。
many_rules = models.RuleSet(
    rules=(
        extra_rule("ARCH-010", ("orm", "repository")),
        extra_rule("ARCH-002", ("repository",)),
    )
)
sorting_context = context("controller", ["orm", "repository"])  # 同时触发两条规则

# 连跑三遍：如果排序不稳定，三次输出就会不一样。
# 列表推导 [(v.rule_id, v.evidence.value) for v in ...] 把每条违规压成 (规则号, 依赖值) 便于对比。
for _ in range(3):
    result = engine.evaluate(many_rules, sorting_context)
    print([(v.rule_id, v.evidence.value) for v in result.violations])

# ----------------------------------------------------------------------------
# **小结**：三次运行输出完全一致，且顺序是"先按 rule_id，再按证据值"。
# 固定排序让快照测试和审计比对成为可能；否则"同样的违规、不同的顺序"会让 diff 失去意义。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 5. CLI：退出码就是接口
#
# 脚本输出面向人，退出码面向机器。Phase 0 固定三个码：
#
# | 退出码 | 含义 |
# | --- | --- |
# | 0 | 通过（ALLOW） |
# | 1 | 发现违规（BLOCK / ALLOW_WITH_WARNINGS） |
# | 2 | 配置或执行错误（规则目录不可读、规则损坏、未知 checker、路径不合法） |
#
# 下面用 check.run() 在进程内调用同一个 CLI 入口，因此不需要另起子进程。
# 集成测试用的是真实子进程 python -m policy.check，覆盖的是同样的代码路径。
# ----------------------------------------------------------------------------

# 8. 反例与正例：退出码与人类可读输出

# 把工作目录切到仓库根目录再调用：示例里的 examples/... 是仓库相对路径，
# 如果 notebook 从别的目录启动（例如 docs/learning/phase-0），相对路径就找不到了。
# 这样写让本单元在任何打开方式下都得到同样的结论。
REPO_ROOT_STR = str(REPO_ROOT)
_previous_dir = os.getcwd()
os.chdir(REPO_ROOT_STR)

# check.run 接收"命令行参数列表"，返回退出码（整数）。
# 参数和你在终端敲的完全一致：先给文件，再给 --dependencies 等选项。
# 反例：examples/bad_controller.py 直接依赖 repository，预期返回 1。
bad_code = check.run(
    ["examples/bad_controller.py", "--dependencies", "repository", "--request-id", "learn-bad"]
)
print("=" * 22, "反例退出码:", bad_code, "=" * 22)

# 正例：同一个文件换成只依赖 service，预期返回 0。
good_code = check.run(
    ["examples/good_controller.py", "--dependencies", "service", "--request-id", "learn-good"]
)
print("=" * 22, "正例退出码:", good_code, "=" * 22)

os.chdir(_previous_dir)  # 恢复原来的工作目录，避免影响后面的单元

# ----------------------------------------------------------------------------
# **小结**：同一个文件、不同的依赖，退出码从 1 变成 0。
# 判定只使用显式传入的依赖，import 列表仅用于报告——这是 Phase 0 划下的边界，Phase 5 才会用 AST 证据替换这一输入。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
#         故意把规则目录指到一个不存在的位置，看程序返回什么。
#         预期是 `2` 而不是 `0`：读不到规则不等于"没有违规"，这两件事必须分开。
#
#         输出里还会看到 `config error: 规则目录不存在: ...`，那是程序写到标准错误（stderr）的说明。
#         标准错误专门放错误信息，和正常结果（标准输出）分开，便于脚本分别处理。
# ----------------------------------------------------------------------------

# 9. 配置错误必须是 2，而不是"悄悄通过"

# 同样先切到仓库根目录，保证 policies/... 这类相对路径能被正确解析。
# 这里自己记住原目录，单独运行本单元也不会出错。
_repo_root_str = str(REPO_ROOT)
_previous_dir = os.getcwd()
os.chdir(_repo_root_str)

# 参数列表里 --rules 指向一个不存在的目录，加载规则时必然失败。
# 参数与你在终端里敲的完全一致，只是被拆成多行写，方便阅读。
code = check.run(
    [
        "examples/good_controller.py",
        "--rules",
        "policies/does-not-exist",
        "--request-id",
        "learn-config",
    ]
)
print("退出码:", code, "(2 = 配置或执行错误)")

os.chdir(_previous_dir)  # 恢复工作目录

# ----------------------------------------------------------------------------
# **小结**："规则读不到"与"代码违规"是两类结果，必须用不同退出码区分。
# 如果两种情况都返回 1，调用方就无法判断该修代码还是修配置，更糟的是可能被误当成"规则已经执行过"。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 6. JSON 输出 = PolicyDecision 契约
#
# --json 的顶层是 CLI 包装（context / rule_set / reported_imports / exit_code），
# 其中 result 就是决策协议载荷：除了 Phase 0 就有的 decision、request_id、matched_rules、
# violations、policy_version，Phase 1 还加了 schema_version、trace_id、rule_set_hash、
# skipped_rules 与 required_action。
#
# 后续的 dsh Adapter（Phase 2）与 Policy API（Phase 7）都消费这个形状；每个字段的含义
# 在 Phase 1 手册里逐步展开。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
#         命令行加 `--json` 时会输出这份结构。这里直接调用渲染函数跳过命令行，
#         再用 `json.loads` 把文本变回字典（loads 的 s 表示 string），这样能逐项查看。
#
#         `indent=2` 表示缩进两格，`sorted(payload)` 返回字典键名列表（排过序，便于核对）。
#
# 这份输出有五个顶层键：`context`（这次检查的输入）、`rule_set`（规则集身份与来源）、
# `result`（决策协议载荷）、`reported_imports`（被检查文件的 import 列表，仅供人参考，
# 不参与判定——这是 Phase 0 就定下的显式边界）、`exit_code`（给脚本用的等价退出码）。
#
# `exit_code` 属于 CLI 包装而不是决策协议：Phase 1 起 `result` 必须能被
# `policy.parse_decision` 原样解析回来，因此协议载荷里不放 CLI 专用的字段。
# ----------------------------------------------------------------------------

# 10. 在进程内构造同一份 JSON（request_id 固定，便于比较）

# render_json 返回的是 JSON 文本；json.loads 把它解析成 Python 字典，方便按键取值。
payload = json.loads(
    check.render_json(
        context("controller", ["repository"]),  # 上下文
        rule_set,  # 规则集
        engine.evaluate(rule_set, context("controller", ["repository"])),  # 判断结果
    )
)

print("顶层键:", sorted(payload))  # 实际是五个键，看下面输出的列表
print("规则集身份:", payload["rule_set"]["identity"])  # 规则内容的 sha256 指纹
print("规则集来源:", payload["rule_set"]["sources"])
print()  # 空行，纯排版
print("PolicyDecision:")
print(json.dumps(payload["result"], ensure_ascii=False, indent=2))

# ----------------------------------------------------------------------------
# **小结**：evidence 只携带定位所需的字段（kind / subject / value，以及可选的 file、line、detail），
# 不上报完整源码或 Prompt。审计需要的是"哪条规则、哪个文件、什么值"，
# 而不是把敏感内容复制到日志里。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 7. 阶段验收证据
#
# 每个阶段的退出条件之一都是"测试证据可被另一位开发者重放"。
# tools/phase_evidence.py 会重新加载规则集、跑全部测试与性能基线，写出
# .tmp/artifacts/phase-<阶段号>-evidence.json，其中 rule_set_hash 是规则内容的 sha256：
# 规则一改，哈希就变。文件写在 .tmp/ 下，随时可以删除并重建。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
#         读一份"验收证据"文件。它不存在也没关系：手册的结论不依赖它，它只是阶段门禁的存档。
#         路径写在 `.tmp/artifacts/` 下——仓库约定所有会话产物都放 `.tmp/`，随时可删。
#
#         文件名形如 phase-1-evidence.json，这里用 glob（按模式找文件）取最新的一份，
#         因此换个阶段也不用改这段代码。`if / else` 做分支：文件在就逐项打印，
#         不在就提示生成命令。其中 `rule_set_hash` 是规则内容的 sha256 指纹：
#         规则改一个字指纹就变，用来证明"这份证据对应的是这一版规则"。
# ----------------------------------------------------------------------------

# 11. 读证据（若还没生成，先在终端执行：python tools/phase_evidence.py）

evidence_files = sorted((REPO_ROOT / ".tmp" / "artifacts").glob("phase-*-evidence.json"))
if evidence_files:  # 先问一句：找到证据文件了吗
    evidence_path = evidence_files[-1]  # 取最新的一份（名字排序即阶段顺序）
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    print("证据文件:", evidence_path.name)
    # 只挑几个关键字段打印，避免刷屏。
    for key in ("phase", "result", "cases", "failures", "rule_set_hash", "timestamp"):
        print(f"{key}: {evidence[key]}")
    # suites 是"每个测试目录一份结果"的字典；.items() 遍历键值对，sorted 让顺序固定。
    for name, suite in sorted(evidence["suites"].items()):
        print(f"  {name}: {suite['cases']} cases, {suite['failures']} failures, {suite['result']}")
else:
    print("尚未生成；本 notebook 仍然自足，证据只用于阶段门禁。")
    print("生成命令: python tools/phase_evidence.py")

# ----------------------------------------------------------------------------
# **小结**：证据文件在就逐项打印，不在就提示生成命令——手册本身不依赖它，阶段门禁依赖它。
# 证据里最关键的字段是规则集哈希：它把"这一份结论"和"这一版规则"绑定在一起。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 8. 边界：Phase 0 不做什么
#
# Phase 0 的价值一半来自"做完了什么"，另一半来自"明确没做什么"：
#
# | 没有引入 | 原因 | 何时才引入 |
# | --- | --- | --- |
# | LangGraph | 编排不是核心依赖 | Phase 8 |
# | 向量库 / Qdrant | 还没有固定评测证明 FTS5 不够 | Phase 3（可选） |
# | FastAPI | 核心协议未稳定，也还不需要进程外共享 | Phase 7 |
# | dsh / MCP / Agent SDK | Phase 0 不接 Agent | Phase 2 / 6 |
# | LLM 判断 | 能确定性验证的规则不许用模型裁决 | 永不作为否决权 |
#
# 另外三条容易忽略但很关键的约定：
#
# 1. **失败要响**：读不到规则目录、规则损坏、未知 checker，一律退出码 2，绝不降级为"无策略通过"；
# 2. **判定输入必须显式**：CLI 只用 --dependencies 的值判定，import 列表仅作报告，不做语义猜测；
# 3. **原子加载**：任一规则文件出错，整份规则集不替换，避免留下"一半旧规则、一半新规则"的状态。
#
# ## 下一步
#
# 按 docs/engineering-policy-platform/phases/ 的顺序，Phase 1 把这里的 PolicyContext 补全成
# 完整的 Context / Scope / Severity / Decision 体系，并给每个决定附上"命中或跳过了哪些规则、为什么"的解释。
# 本仓库的 Phase 1 已完成，继续读 [../phase-1/walkthrough.ipynb](../phase-1/walkthrough.ipynb) 即可。
#
# 自测一下：如果把 examples/bad_controller.py 的依赖改成 service，退出码会变成什么？
# 下一个单元直接给出答案。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么（自测）
#
#         把上面留的问题做掉：反例文件如果只依赖 `service`，结论会变成什么？
#         答案是退出码 `0`——规则只在两个条件同时成立时才判违规：层是 controller，且依赖里有 repository。
#
#         第二个问题是：规则为什么没参与判断？`skipped_rule_id` 会给出原因文本。
#         这个能力是给后续阶段用的：最终每个决定都要能说清"命中了哪些规则、跳过了哪些、为什么"。
#
#         试着改一改：把 `context("service", ...)` 换成 `context("controller", ...)`，看解释怎么变。
# ----------------------------------------------------------------------------

# 12. 自测：改一个输入，看结论怎么变

# 同一个文件、不同的依赖，结论应当从 block 变成 allow。
# exit_code_for 把决策翻译成退出码：allow -> 0，block -> 1。
changed = context("controller", ["service"])
print("退出码应为 0，实际得到:", check.exit_code_for(engine.evaluate(rule_set, changed)))

# 换个角度：这次把 layer 换成 service，规则范围不匹配，因此根本不参与判断。
# skipped_rule_id 返回原因字符串；如果返回 None，说明你的输入写错了。
skipped = engine.skipped_rule_id(rule, context("service", ["repository"]))
print("跳过原因:", skipped)

# ----------------------------------------------------------------------------
# **小结**：改一个输入就能让结论反转，并且能拿到"规则为什么没有参与判断"的原因文本。
# 这个能力在 Phase 1 会被扩展成决策载荷里的 skipped_rules，并补上每个维度的完整比较过程。
# ----------------------------------------------------------------------------

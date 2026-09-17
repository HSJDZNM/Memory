"""Phase 1 学习手册的纯 Python 版本（由 tools/build_learning_notebook.py 生成）。

notebook 里每一段代码都按顺序出现在下面；直接运行本文件即可复现全部输出：

    python docs/learning/phase-1/walkthrough.py

内容改动请修改 tools/build_learning_notebook.py 后重新生成，不要直接编辑本文件。
"""

# ----------------------------------------------------------------------------
# # Phase 1 学习手册：Policy Engine
#
# 这份 notebook 用**实际运行的代码**解释 Phase 1 相对 Phase 0 增加了什么。
# 它不引入新代码，只调用仓库里已经通过测试的模块，因此每一段输出都可以自己重跑验证。
#
# ## Phase 1 要证明的事
#
#     PolicyContext（规范化） -> Scope 匹配 -> Severity 决策 -> Decision（可解释、带版本）
#
# 一句话：**同一个上下文与同一份规则集，永远得到同一个决定，而且这个决定说得清"命中了谁、
# 跳过了谁、为什么、用的是哪一版协议"。**
#
# ## 阅读路线
#
# | 小节 | 回答的问题 |
# | --- | --- |
# | 0 | 跑这份 notebook 需要什么前提 |
# | 1 | 上下文为什么必须先规范化，谁来规范化 |
# | 2 | 规则的"范围"如何匹配，多值与通配是什么意思 |
# | 3 | 严重级别如何汇总成 allow / allow_with_warnings / block，审批门禁为什么也是 block |
# | 4 | 一个决定如何解释命中、跳过、哈希与 trace，规则顺序为什么不影响结论 |
# | 5 | 决策协议的版本与快照为什么必须固定 |
# | 6 | 命令行如何用退出码与跳过原因表达结论 |
# | 7 | 性能基线记录了什么，为什么现在不优化 |
# | 8 | 边界：Phase 1 明确不做什么 |
#
# 表格里的编号与正文的二级标题（## 1 到 ## 8）一一对应：审批门禁属于第 3 节的决策表，
# 规则顺序属于第 4 节的解释信息。每个代码单元后面都有一个小结，说明"这段输出意味着什么"。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 预备知识：Phase 1 新出现的名词
#
# Phase 0 手册已经讲过函数、类、模型与 YAML 缩进，这里只补 Phase 1 新增的术语。
# 看不懂代码时回到这张表查，不需要背下来。
#
# | 名词 | 一句话解释 | 在本手册里的样子 |
# | --- | --- | --- |
# | 规范化 normalizer | 把原始输入整理成唯一表示，之后所有比较都基于它 | 反斜杠路径与斜杠路径变成同一个值 |
# | 维度 dimension | 规则用来划范围的一个方面 | language、layer、module、operation、project、agent |
# | 通配 wildcard | 写一个星号表示"这个维度不限制" | scope 里的 layer 写成星号 |
# | AND / OR | 跨维度是"都要满足"，同维度多值是"满足其一" | layer 与 language 都要中；列表里中一个即可 |
# | specificity | 命中的非通配维度数，只用于解释，不参与决策 | 命中 layer 与 language 就是 2 |
# | 失败关闭 fail-closed | 信息不全时拒绝执行，而不是默认放行 | 缺 layer 直接报错，不再猜一个值 |
# | 决策协议 schema_version | 决策载荷的版本号，看不懂就拒绝消费 | 1.0 |
# | required_action | 决策要求调用方先完成的动作 | approval（人工审批） |
# | 快照 snapshot | 固定下来用于比对的历史输出 | tests/fixtures/decisions 下的 JSON |
#
# Phase 1 有一条贯穿全篇的约定：**"规则是否相关"与"是否违规"是两件事**。
# 前者由 scope 匹配决定（matched / skipped），后者由 violation 决定（allow / block）。
# 把两件事混在一起，就会出现"规则没命中却被当成通过"这种最难查的问题。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 笔记本放在 docs/learning/phase-1/，代码在 src/，性能基线脚本在 tools/。
# 所以先把这两个目录告诉 Python，再加载规则集，后面所有单元都复用这一份。
#
# 与 Phase 0 相比多导入两个模块：context（规范化器）与 scope（范围匹配器）。
# ----------------------------------------------------------------------------

# 0. 准备运行环境：找到仓库根目录，导入 Phase 1 的核心模块
import json
import os
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    print("函数用途:", "向上找到含 policies/ 的目录；找不到就退回当前工作目录")

    for candidate in (start, *start.parents):
        if (candidate / "policies").is_dir():
            return candidate
    return Path.cwd()


NOTEBOOK_DIR = Path.cwd() if Path("policies").is_dir() else Path("docs/learning/phase-1")
REPO_ROOT = find_repo_root(NOTEBOOK_DIR.resolve())

# src/ 放核心库，tools/ 放仓库脚本（本手册最后要用 tools/policy_bench.py 跑基线）。
for _directory in (REPO_ROOT / "src", REPO_ROOT / "tools"):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

# context 与 scope 是 Phase 1 新增的两个模块：
#   context 把原始输入整理成规范化的 PolicyContext；
#   scope   判断规则的适用范围是否覆盖这个上下文。
from policy import check, context as context_module, engine, loader, models, scope

rule_set = loader.load_rule_set([REPO_ROOT / "policies"], repo_root=REPO_ROOT)

print("仓库根目录:", REPO_ROOT)
print("规则集:", rule_set.ids, "| 规则集哈希:", rule_set.identity)
print("决策协议版本:", models.SCHEMA_VERSION, "| 当前阶段: phase-1")


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
# **小结**：核心库仍然是一个普通 Python 包，多出来的两个模块同样只依赖标准库与 pydantic。
# 规则集哈希是规则内容的指纹：规则改一个字，哈希就变，用它可以把一份决定和一份规则集绑定起来。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 1. 上下文先规范化，再进入引擎
#
# Phase 1 的第一步是把"原始请求"变成唯一表示：路径统一成仓库相对斜杠路径，
# 维度统一小写，依赖去重排序，未知操作直接拒绝。
#
# 这样做不是为了好看，而是为了让"同一个文件、同一次操作"在不同平台上得到同一个决定。
# 规范化只发生在 Adapter 边界（context.build_context），引擎内部不再猜测任何字段。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 把三种写法指向同一个文件，看它们是否变成同一个上下文：
#
# 1. 正常的斜杠路径；
# 2. 带 "./" 与重复斜杠的路径；
# 3. Windows 反斜杠路径（chr(92) 就是反斜杠字符，用它写可以避免转义混乱）。
#
# 然后试三种"不该接受"的路径：仓库外的绝对路径、Windows 盘符路径、用 ".." 逃出仓库的路径。
# 预期全部被拒绝，并且错误信息说明拒绝的原因。
# ----------------------------------------------------------------------------

# 1. 路径规范化：同一个文件必须得到同一个上下文
windows_path = "src" + chr(92) + "order" + chr(92) + "controller.py"


# 这个小函数把"原始输入"交给规范化器：安全关键字段缺失时它会直接失败，
# 这里只补上本次演示用不到、但构造上下文必须有的字段。
def raw_context(raw_file, **extra):
    payload = {"request_id": "learn-p1", "file": raw_file, "layer": "controller"}
    payload.update(extra)
    return context_module.build_context(payload, repo_root=REPO_ROOT)


variants = [
    ("src/order/controller.py", "src/order/controller.py"),
    ("./src//order/controller.py", "src/order/controller.py"),
    (windows_path, "src/order/controller.py"),
]

print(pad("输入（原样）", 36) + "规范化结果")
print("-" * 68)
for raw, expected in variants:
    normalized = raw_context(raw, layer="  Controller ").file
    # 手册里写死的期望值必须与真实行为一致，否则这一单元直接失败。
    assert normalized == expected, (raw, normalized)
    print(pad(raw, 36) + normalized)

# 仓库内的绝对路径会被换算成仓库相对路径，便于审计记录跨机器可比。
inside = raw_context(str(REPO_ROOT / "policies" / "architecture" / "ARCH-001.yaml"))
print()
print("仓库内绝对路径 ->", inside.file)

outside_paths = [
    "/etc/passwd",
    "C:" + chr(92) + "Users" + chr(92) + "other" + chr(92) + "x.py",
    "../secrets.env",
]
for outside in outside_paths:
    try:
        raw_context(outside)
    except models.PolicyContextError as error:
        print("已按预期拒绝:", outside, "->", str(error)[:58])
    else:
        raise AssertionError(f"{outside} 本应被拒绝")

# ----------------------------------------------------------------------------
# **小结**：三种写法收敛成同一个仓库相对路径，仓库外的绝对路径与 ".." 逃逸被拒绝。
# 规范化只发生在 Adapter 边界，因此引擎拿到的永远是同一个值——这是"相同输入得到相同结论"的第一层保证。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 看规范化对"值"做了什么：大小写、受控枚举、集合去重。
# 注意 operation 与其他维度不同：它是受控枚举，写一个不存在的操作（例如 deploy）
# 必须报错，而不是当成"没有操作"——否则以 operation 划范围的规则会悄悄失效。
# ----------------------------------------------------------------------------

# 2. 维度规范化：大小写统一、操作受控、依赖去重排序
raw_document = {
    "request_id": "  learn-p1  ",
    "file": "src/order/controller.py",
    "layer": "  Controller ",
    "language": "Python",
    "module": "Order",
    "operation": "EDIT",
    "dependencies": ["Service", "repository", "REPOSITORY", "orm"],
}

normalized_context = context_module.build_context(raw_document, repo_root=REPO_ROOT)

print("request_id:", normalized_context.request_id, "（去首尾空白）")
print(
    "layer:", normalized_context.layer,
    "| language:", normalized_context.language,
    "| module:", normalized_context.module,
    "（统一小写）",
)
print("operation:", normalized_context.operation.value, "（受控枚举 EDIT -> edit）")
print("dependencies:", normalized_context.dependencies, "（去重 + 稳定排序）")

try:
    context_module.build_context({**raw_document, "operation": "deploy"}, repo_root=REPO_ROOT)
except models.PolicyContextError as error:
    print()
    print("未知操作被拒绝:", str(error)[:96])
else:
    raise AssertionError("未知操作本应被拒绝")

# ----------------------------------------------------------------------------
# **小结**：大小写不敏感、依赖去重排序，而 operation 是受控枚举：写一个不存在的操作会直接报错，
# 而不是变成"没有操作"。前者让同一个请求只有一种写法，后者保证以 operation 划范围的规则不会悄悄失效。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 最后一条规范化规则是**失败关闭**：安全关键字段（request_id、file、layer）缺失时直接失败，
# 不允许"猜一个默认值"继续跑。
#
# 同时看看 Phase 1 特意**不**做的事：不会因为文件名里有 deploy、prod 就推断主体或审批状态。
# 上下文里根本没有"权限"或"审批"这类字段，审批只能由规则声明、由决策表达。
# ----------------------------------------------------------------------------

# 3. 失败关闭与"不猜字段"
for missing in ("request_id", "file", "layer"):
    incomplete = {
        "request_id": "learn-p1",
        "file": "src/order/controller.py",
        "layer": "controller",
    }
    incomplete.pop(missing)
    try:
        context_module.build_context(incomplete)
    except models.PolicyContextError as error:
        print(f"缺少 {missing:<11} -> 拒绝：{str(error)[:50]}")
    else:
        raise AssertionError(f"缺少 {missing} 本应失败关闭")

# 文件名里出现 prod / deploy 也不能推出主体或审批状态：
prod_context = context_module.build_context(
    {"request_id": "learn-p1", "file": "prod/infra/deploy_controller.py", "layer": "controller"},
    repo_root=REPO_ROOT,
)
print()
print("principal:", prod_context.principal, "（文件名叫什么都不会被用来推断主体）")
print("上下文字段里有 approval 吗:", "approval" in models.PolicyContext.model_fields)
print("上下文允许的字段:", sorted(models.PolicyContext.model_fields))

# ----------------------------------------------------------------------------
# **小结**：缺 request_id、file、layer 任一字段都直接失败，而不是补一个默认值继续跑；
# 文件名里出现 prod、deploy 也不会被用来推断主体或审批状态——上下文里根本没有这类字段。
#
# 规范化的两条底线在这里合流：**不知道就失败**，以及**不替调用方猜任何安全相关信息**。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# **小结**：规范化把"同一个请求的不同写法"收敛成一个值，缺信息时宁可失败也不猜。
# 这三条性质（唯一表示、受控枚举、失败关闭）是后面所有确定性结论的前提。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 2. Scope Matcher：规则管谁
#
# 规则可以声明若干个维度，每个维度的取值有三种写法：单个精确值、值列表、星号通配。
#
# | 写法 | 含义 |
# | --- | --- |
# | 不写某个维度 | 该维度不限制 |
# | layer: controller | 必须等于 controller |
# | layer: [controller, service] | 等于其中之一（同维度多值 = OR） |
# | layer 写成星号 | 显式不限制，连"上下文没有这个值"也算命中 |
# | 多个维度同时写 | 都要满足（跨维度 = AND） |
#
# 声明了某个维度、但上下文没有这个值时，规则**不命中**，并在原因里写明"值缺失"。
# 这是刻意的选择：宁可不判，也不替调用方编一个值出来。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 把上面那张表变成一张可执行的表：每行是"规则范围 + 上下文 + 说明"。
# 输出四列：是否命中、specificity（命中的非通配维度数）、以及比较原因。
#
# 注意 specificity 只用于解释与排序，**不参与决策**：决策只看"是否命中"和"是否违规"。
# ----------------------------------------------------------------------------

# 4. 范围矩阵：精确值 / 值列表 / 通配 / 缺值 / 跨维度 AND


# 造一个最小上下文：没有覆盖的维度用这里的默认值（policy = controller / python / order）。
def sample_context(**overrides):
    fields = {
        "request_id": "learn-p1",
        "file": "src/order/controller.py",
        "layer": "controller",
        "language": "python",
        "module": "order",
        "dependencies": (),
    }
    fields.update(overrides)
    return models.PolicyContext(**fields)


def sample_scope(**dimensions):
    return models.RuleScope.model_validate(dimensions)


matrix = [
    ({"layer": "controller"}, {}, "单字段精确命中"),
    ({"layer": ["controller", "service"]}, {}, "同字段多值 = OR"),
    ({"module": "*"}, {"module": None}, "通配 = 不限制，连缺值也命中"),
    ({"layer": "service"}, {}, "精确未命中"),
    ({"layer": "controller", "language": "go"}, {}, "跨字段 = AND，一个不中就整体不中"),
    ({"module": "billing"}, {}, "声明了维度但上下文的值不匹配"),
    ({"module": "billing"}, {"module": None}, "声明了维度但上下文没有该值"),
    ({"operation": "edit"}, {}, "operation 缺值时同样不命中"),
    ({}, {"layer": "service"}, "没有声明任何维度 = 不限制"),
]

print(pad("规则 scope", 46) + pad("命中", 7) + pad("specificity", 12) + "原因")
print("-" * 120)
for dimensions, overrides, note in matrix:
    outcome = scope.match_scope(sample_scope(**dimensions), sample_context(**overrides))
    reason = "; ".join(outcome.reasons) or "<没有声明维度>"
    print(pad(dimensions, 46) + pad(outcome.matched, 7) + pad(outcome.specificity, 12) + reason)

assert len(matrix) >= 6, "矩阵至少要覆盖精确值、列表、通配与缺值"

# ----------------------------------------------------------------------------
# **小结**：读这张表时注意两件事。
#
# 1. matched=False 不等于"通过"，而是"这条规则不参与判断"，它会在决策的 skipped_rules 里出现；
# 2. 通配与"不写维度"都表示不限制，区别只在于前者是显式写出来的：写星号的人明确表达
#    "我知道这个维度，但故意不限制它"，读规则的人不必猜。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 上一单元只看结论，这一单元看匹配结果的内部结构：每个维度一条 comparison 记录，
# 分别记着维度名、规则声明的值、上下文的值、是否命中、以及一句可读原因。
#
# 这套结构会原样进入审计记录：出了问题不必重新跑一遍，只看当时的决策载荷就能复盘。
# ----------------------------------------------------------------------------

# 5. 匹配结果是结构化的，可以直接进审计
explained = scope.match_scope(
    sample_scope(language="python", layer="controller", module="billing"),
    sample_context(),
)

print(pad("维度", 10) + pad("规则声明", 18) + pad("上下文", 12) + pad("命中", 8) + "原因")
print("-" * 96)
for comparison in explained.comparisons:
    print(
        pad(comparison.dimension, 10)
        + pad(comparison.declared, 18)
        + pad(comparison.actual, 12)
        + pad(comparison.matched, 8)
        + comparison.reason
    )

print()
print("整体命中:", explained.matched, "| failures:", explained.failures)
print("specificity:", explained.specificity, "（命中的非通配维度数，只用于解释）")

# ----------------------------------------------------------------------------
# **小结**：匹配结果不是一个布尔值，而是每个维度一条记录（声明值、上下文值、是否命中、原因）。
# 审计时不需要重跑：看当时的 comparisons 就知道为什么命中或跳过。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# Phase 0 对未知的 scope 键是"记录并忽略"，Phase 1 把默认改成**直接报错**：
# 把 language 拼成 langauge 时，规则会从"只对 python 生效"悄悄变成"对所有语言生效"，
# 这种放大范围的错误比误报更危险。
#
# 确实需要忽略时，规则可以显式写 extra_policy: skip；即使如此，被忽略的键也会出现在
# 匹配原因里，不会凭空消失。
# ----------------------------------------------------------------------------

# 6. 未知维度：默认报错，显式 skip 时留痕
try:
    sample_scope(layer="controller", tenant="acme")
except Exception as error:
    # pydantic 的错误信息很长，这里只取 "Value error, ..." 之后的那一段人话。
    message = " ".join(str(error).split()).split("Value error, ", 1)[-1]
    print("默认拒绝未知维度:", message[:110])
else:
    raise AssertionError("未知维度本应被拒绝")

lenient_scope = sample_scope(layer="controller", tenant="acme", extra_policy="skip")
lenient_result = scope.match_scope(lenient_scope, sample_context())
print()
print("显式 skip 时仍然留痕:", lenient_result.ignored_dimensions)
print("最后一条原因:", lenient_result.reasons[-1])
print("该规则是否命中:", lenient_result.matched, "（未知维度被忽略，其余维度照常参与）")

# ----------------------------------------------------------------------------
# **小结**：未知维度默认报错，显式 skip 时留痕。这条默认值在 Phase 1 从"忽略"改成了"拒绝"：
# 把 language 拼成 langauge 会让规则从"只对 python 生效"变成"对所有语言生效"，
# 而这类放大范围的错误不会被任何用例发现，只能靠加载失败暴露。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 3. 严重级别如何汇总成一个决策
#
# 决策只有三种取值，映射关系是固定的：
#
# | 最高严重级别 | Decision |
# | --- | --- |
# | 没有 violation | allow |
# | info / warning | allow_with_warnings |
# | error / critical | block |
#
# Phase 1 新增了 critical：用于"必须阻断且需要立刻处理"的场景（例如安全关键上下文缺失）。
# 规则输入顺序、文件加载顺序都不影响结论：violation 先按规则身份排序，再按证据值排序。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 用仓库里那条真实规则当原型，复制出四份不同严重级别的规则（model_copy 是冻结模型的"改法"），
# 分别在有违规与无违规两种上下文下跑一遍，把决策表打印出来。
#
# 读表时注意两点：warning 与 info 都只是"通过但有告警"；error 与 critical 一定阻断。
# ----------------------------------------------------------------------------

# 7. 决策表：最高严重级别决定 decision
base_rule = rule_set.rules[0]  # 仓库里真实的 ARCH-001@1


# 按真实规则复制出一条变体：冻结模型不能直接改字段，只能复制后再改。
def rule_variant(rule_id, severity, *, requires_approval=False, dependencies=("repository",)):
    return base_rule.model_copy(
        update={
            "id": rule_id,
            "severity": models.Severity(severity),
            "enforcement": base_rule.enforcement.model_copy(
                update={"requires_approval": requires_approval}
            ),
            "rule": base_rule.rule.model_copy(
                update={"forbidden_dependency": tuple(dependencies)}
            ),
        }
    )


print(pad("severity", 10) + pad("有违规", 22) + "无违规（依赖换成 service）")
print("-" * 68)
for level in ("info", "warning", "error", "critical"):
    single = models.RuleSet(rules=(rule_variant("ARCH-001", level),))
    hit = engine.evaluate(single, sample_context(dependencies=("repository",)))
    clean = engine.evaluate(single, sample_context(dependencies=("service",)))
    print(pad(level, 10) + pad(hit.decision.value, 22) + clean.decision.value)

# ----------------------------------------------------------------------------
# **小结**：info 与 warning 只告警，error 与 critical 一定阻断，没有违规就是 allow。
# 决策刻意保留三种取值而不是两种：调用方需要区分"可以继续"和"可以继续，但请看一眼"。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 有些动作不是"违规"，而是"必须先经人批准"。这类规则在 enforcement.requires_approval: true
# 声明，一旦范围命中，决策就先表达成 block 并附上 required_action=approval。
#
# 注意"命中"两个字：审批是**前置条件**，与有没有违规无关。下面是同一个例子的两种结果：
# 有审批开关时，即使没有任何违规也阻断；去掉开关后，warning 规则只是告警。
# ----------------------------------------------------------------------------

# 8. 审批门禁：没有违规也要 block + required_action=approval
approval_rules = models.RuleSet(
    rules=(rule_variant("ARCH-004", "warning", requires_approval=True),)
)
approval_results = engine.evaluate(
    approval_rules, sample_context(dependencies=("service",))
).to_decision_dict()

print("decision:", approval_results["decision"])
print("required_action:", approval_results["required_action"])
print("violations:", approval_results["violations"], "（没有违规）")
print("matched_rules:", approval_results["matched_rules"])

without_gate = engine.evaluate(
    models.RuleSet(rules=(rule_variant("ARCH-004", "warning"),)),
    sample_context(dependencies=("repository",)),
)
print()
print(
    "同一条规则去掉审批开关:", without_gate.decision.value,
    "（warning 只是告警，绝不会被当成授权）",
)
assert approval_results["decision"] == "block", "审批门禁必须表达成 block"

# ----------------------------------------------------------------------------
# **小结**：审批是前置门禁（范围命中就要求授权），与有没有违规无关；
# 它被表达成 block + required_action=approval，而不是一条警告——授权不能被降级成"提醒一下"。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 4. 一个决定必须能解释自己
#
# 决策载荷记录下面这些信息，缺一条都不算完整：
#
# | 字段 | 含义 |
# | --- | --- |
# | matched_rules | 范围命中的规则（审计身份 编号@版本） |
# | skipped_rules | 范围没命中的规则，以及每个维度不命中的原因 |
# | violations | 违规记录：规则、严重级别、消息、结构化证据 |
# | required_action | 需要调用方先完成的前置动作 |
# | rule_set_hash | 规则集内容指纹，把决定绑定到具体规则版本 |
# | trace_id / request_id | 把检索、决策、执行、验证串成一条链 |
# | schema_version | 决策协议版本，看不懂就拒绝消费 |
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 造两条规则：一条命中并产生违规，另一条只对 service 层生效因而不参与判断。
# 然后把这个决策的"解释信息"逐项打印出来，重点是 skipped_rules 里的原因文本。
# ----------------------------------------------------------------------------

# 9. 命中、跳过、哈希与 trace 一次说清
service_only = rule_variant("ARCH-003", "warning").model_copy(
    update={"scope": models.RuleScope(layer="service")}
)
mixed_rules = models.RuleSet(
    rules=(
        rule_variant("ARCH-001", "error", dependencies=("repository",)),
        service_only,
    )
)

explained_result = engine.evaluate(
    mixed_rules, sample_context(dependencies=("repository",), trace_id="trace-learn")
)

print("decision:", explained_result.decision.value)
print("matched_rules:", explained_result.matched_rules)
for skipped_rule in explained_result.skipped_rules:
    print("skipped_rule:", skipped_rule.rule_id, "->", "; ".join(skipped_rule.reasons))
print("rule_set_hash:", explained_result.rule_set_hash)
print("request_id:", explained_result.request_id, "| trace_id:", explained_result.trace_id)
print("severity_counts:", dict(explained_result.severity_counts))

# ----------------------------------------------------------------------------
# **小结**：一个决策同时回答五个问题——命中了谁、跳过了谁、为什么、用的是哪一版规则、
# 属于哪条 trace。缺任何一项，事后都只能重跑一遍才能复盘，而"重跑"本身就可能已经跑在不同的规则集上。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 把三条规则打乱顺序重新装进规则集，再跑一次，确认结论与违规顺序完全不变。
# 这是"相同输入得到相同结论"的直接检验，也是快照测试能成立的原因。
#
# 注意这里验证的是两件不同的事：**决策**（allow / block）与**违规列表的顺序**。
# 两者都必须与规则输入顺序无关，否则同一份规则集在不同加载顺序下会产生不同的审计记录。
# ----------------------------------------------------------------------------

# 10. 规则顺序不影响结论
import random

# 三条规则按 id 乱序排列：ARCH-010、ARCH-002、CODING-003
original_rules = (
    rule_variant("ARCH-010", "error", dependencies=("orm", "repository")),
    rule_variant("ARCH-002", "error"),
    rule_variant("CODING-003", "warning", dependencies=("logging",)),
)
shuffled_rules = list(original_rules)
random.Random(7).shuffle(shuffled_rules)  # 固定种子：每次运行得到同一个乱序

assert [item.id for item in shuffled_rules] != [item.id for item in original_rules], (
    "这个种子没有打乱顺序，换一个种子才能验证顺序无关"
)

scenario = sample_context(dependencies=("orm", "repository", "logging"))
ordered = engine.evaluate(models.RuleSet(rules=original_rules), scenario)
shuffled = engine.evaluate(models.RuleSet(rules=tuple(shuffled_rules)), scenario)


# violation_order 把违规压成 (审计身份, 证据值) 列表，便于逐项比较顺序。
def violation_order(result):
    return [(item.canonical_id, item.evidence.value) for item in result.violations]


print("规则输入顺序:", [item.id for item in original_rules])
print("打乱后的顺序:", [item.id for item in shuffled_rules])
print()
print("按输入顺序评估的违规:", violation_order(ordered))
print("按打乱顺序评估的违规:", violation_order(shuffled))
print()
print("两份违规列表逐项相同:", violation_order(ordered) == violation_order(shuffled))
print("两次决策载荷完全相同:", ordered.to_decision_dict() == shuffled.to_decision_dict())

# 断言而不是只打印：万一排序退化，这一单元会直接失败，而不是给读者看一句 False。
assert violation_order(ordered) == violation_order(shuffled)

# ----------------------------------------------------------------------------
# **小结**：输入顺序是 ARCH-010、ARCH-002、CODING-003，而两次评估打印出的违规列表都是
# ARCH-002 -> ARCH-010(orm) -> ARCH-010(repository) -> CODING-003，**与规则输入顺序无关**。
#
# 顺序由排序键决定：先按审计身份（ARCH-002 排在 ARCH-010 之前），再按证据值（orm 排在
# repository 之前）。这就是"相同输入得到相同结论"在实现层面的含义，也是协议快照能够逐字节比对的前提。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 5. 决策协议：带版本、可双向解析
#
# 决策不是"给人看的一段文字"，而是一份有版本的载荷：policy.parse_decision 能把它解析回模型，
# 未知版本、未知决策值一律拒绝——绝不因为"看不懂"就默认放行。
#
# 协议快照固定在 tests/fixtures/decisions/ 下（allow / warning / block / approval 各一份），
# 改了字段名或语义，快照测试会先失败，由提交者显式更新并说明兼容性。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 先拿到一次真实的 CLI JSON 输出（check.render_json 就是 --json 用的渲染函数），
# 看清外层包装与内层决策载荷的分工，再把内层载荷解析回模型，验证"解析回来完全一样"。
# ----------------------------------------------------------------------------

# 11. 决策载荷可以原样解析回来
protocol_rules = models.RuleSet(rules=(rule_variant("ARCH-001", "error"),))
protocol_context = sample_context(dependencies=("repository",), trace_id="trace-learn")
protocol_result = engine.evaluate(protocol_rules, protocol_context)

payload = json.loads(check.render_json(protocol_context, protocol_rules, protocol_result))

print("CLI 包装键:", sorted(payload), "（exit_code 属于包装，不属于决策协议）")
print()
print("决策载荷（截断显示）:")
print(json.dumps(payload["result"], ensure_ascii=False, indent=2)[:520])

parsed = models.parse_decision(payload["result"])
print()
print("解析回来的决策:", parsed.decision.value, "| 协议版本:", parsed.schema_version)
print("与原结果完全一致:", parsed.to_decision_dict() == payload["result"])
assert parsed.schema_version is not None

# ----------------------------------------------------------------------------
# **小结**：CLI 包装与决策协议是两层：包装服务于脚本（含 exit_code），协议服务于 Adapter 与 API。
# 协议载荷能被原样解析回来，才谈得上跨进程、跨语言的稳定边界。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 试着篡改协议载荷：把版本号改成未来版本、把 decision 改成不存在的值。
# 两种篡改都必须被拒绝并给出可读原因——这是 Phase 2 Adapter 与 Phase 7 API 的稳定边界。
# ----------------------------------------------------------------------------

# 12. 未知协议版本与未知决策值都拒绝消费
future_version = dict(payload["result"], schema_version="9.9")
unknown_decision = dict(payload["result"], decision="maybe")

for label, tampered in (("未知版本", future_version), ("未知决策值", unknown_decision)):
    try:
        models.parse_decision(tampered)
    except models.ProtocolError as error:
        print(f"{label} 已按预期拒绝:", " ".join(str(error).split())[:96])
    else:
        raise AssertionError(f"{label} 本应被拒绝")

print()
print("提醒：拒绝是硬错误，不是降级成 allow。")

# ----------------------------------------------------------------------------
# **小结**：看不懂就拒绝，不做任何"尽量理解"的尝试。协议升级只能通过 schema_version 协商，
# 不允许旧实现按自己的猜测继续放行——这是 Phase 2 Adapter 与 Phase 7 API 能安全升级的前提。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 6. 命令行：退出码与可解释输出
#
# | 退出码 | 含义 |
# | --- | --- |
# | 0 | 通过（allow） |
# | 1 | 发现违规（block / allow_with_warnings，含需要审批的 block） |
# | 2 | 配置或执行错误（规则不可读、规则损坏、上下文不完整、未知 checker） |
#
# Phase 1 的输出多了一段"命中 / 跳过"的说明：通过不等于"什么都没发生"，
# 必须能看出哪些规则参与了判断、哪些因为范围不匹配被跳过。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 先跑 Phase 0 就有的两个例子：反例退出码 1，正例退出码 0。
# 命令与你在终端里敲的完全一致，只是通过 check.run 在进程内调用。
# ----------------------------------------------------------------------------

# 13. CLI：反例与正例的退出码
_previous_dir = os.getcwd()
os.chdir(str(REPO_ROOT))  # 示例用的是仓库相对路径

bad_code = check.run(
    ["examples/bad_controller.py", "--dependencies", "repository",
     "--request-id", "learn-p1-bad"]
)
print("=" * 20, "反例退出码:", bad_code, "=" * 20)

good_code = check.run(
    ["examples/good_controller.py", "--dependencies", "service",
     "--request-id", "learn-p1-good"]
)
print("=" * 20, "正例退出码:", good_code, "=" * 20)

os.chdir(_previous_dir)

# ----------------------------------------------------------------------------
# **小结**：退出码 1 与 0 对应 block 与 allow。输出里同时给出规则、原因与期望的依赖方向，
# 人读到这一份信息就够改代码了，不需要再去翻规则文件。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 把层显式指定成 service：这时 ARCH-001 的 scope 不匹配，规则不会参与判断。
# 预期退出码仍然是 0，但输出里会出现 "skipped ... layer service != controller"——
# 这就是"规则不相关"与"规则通过"的区别。
# ----------------------------------------------------------------------------

# 14. 范围不匹配：通过，但必须报告为什么
_previous_dir = os.getcwd()
os.chdir(str(REPO_ROOT))

skip_code = check.run(
    "examples/good_controller.py --layer service --dependencies repository "
    "--request-id learn-p1-skip".split()
)
print("退出码:", skip_code, "(0 = 通过；规则不相关不等于放行)")

os.chdir(_previous_dir)

# ----------------------------------------------------------------------------
# **小结**：这次退出码仍是 0，但输出里多了一行 skipped。读日志的人必须能区分
# "规则说可以"与"规则根本没管这件事"——两者对风险的意味完全不同。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 最后确认失败路径：规则目录不存在时退出码必须是 2，而不是 0。
# "读不到规则"与"没有违规"必须能区分开，否则调用方会把配置事故当成合规结论。
# ----------------------------------------------------------------------------

# 15. 配置错误必须是 2
_previous_dir = os.getcwd()
os.chdir(str(REPO_ROOT))

config_code = check.run(
    ["examples/good_controller.py", "--rules", "policies/does-not-exist"]
)
print("退出码:", config_code, "(2 = 配置或执行错误；错误信息写到标准错误)")

os.chdir(_previous_dir)

# ----------------------------------------------------------------------------
# **小结**：失败必须响。规则目录不可读、文件损坏、上下文不完整都返回 2，
# 调用方由此知道该去修配置而不是改代码，也不会把"没读到规则"当成"没有违规"。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 7. 性能基线：先量，再谈优化
#
# Phase 1 的退出条件之一是"性能基线已记录，但没有引入不必要的缓存"。
# 基线用固定随机种子生成 10 / 100 / 1000 条规则，记录每次评估的耗时与内存峰值。
#
# 它只是参照物：
#
# - 以后改动引擎时，可以对比"是不是出现了数量级退化"；
# - 现在不做缓存，因为还没有证据表明需要——过早优化会让"确定性"和"可解释"变难。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么
#
# 调用 tools/policy_bench.py（测试与阶段证据共用同一份实现），跑三种规模并打印。
# 种子固定，所以同一台机器上规则集哈希永远一样；耗时与内存会随机器浮动，这正是"基线"的含义。
# ----------------------------------------------------------------------------

# 16. 固定种子的匹配基线
import policy_bench

baseline = policy_bench.run_baseline((10, 100, 1000))

print("固定种子 seed =", baseline["seed"])
print(
    pad("规则数", 8, "right")
    + pad("每次评估(ms)", 16, "right")
    + pad("内存峰值(KiB)", 16, "right")
    + pad("命中规则数", 12, "right")
)
print("-" * 54)
for measurement in baseline["samples"]:
    print(
        pad(measurement["rules"], 8, "right")
        + pad(f"{measurement['ms_per_evaluation']:.3f}", 16, "right")
        + pad(f"{measurement['peak_kib']:.1f}", 16, "right")
        + pad(measurement["matched_rules_total"], 12, "right")
    )
print()
print("结论：1000 条规则仍是一次评估几十毫秒的量级；本轮不引入缓存。")

# ----------------------------------------------------------------------------
# **小结**：基线的作用是"以后能对比"，而不是"现在要优化"。
# 真正的性能问题要等到 Phase 4/5 接入工具执行与代码验证之后再谈，那时才有真实的负载。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ## 8. 边界：Phase 1 不做什么
#
# | 没有引入 | 原因 | 何时才引入 |
# | --- | --- | --- |
# | dsh / Agent SDK | 核心层不依赖任何 Agent 类型 | Phase 2 |
# | 知识检索 / 向量库 | 还没有固定评测证明需要它 | Phase 3 |
# | 真实工具执行 | 执行器必须绑定已授权的决策 | Phase 4 |
# | AST / Ruff / 类型检查 | 需要确定性代码证据时才引入 | Phase 5 |
# | FastAPI | 核心协议刚稳定，还不需要进程外共享 | Phase 7 |
# | 规则内嵌表达式 | 规则是数据，不能变成动态代码执行 | 永不 |
# | 缓存与预编译 | 基线显示还不需要 | 有证据再说 |
#
# 三条容易忽略的约定：
#
# 1. **未知一律报错**：未知 scope 维度、未知操作、未知 checker、未知协议版本都拒绝；
# 2. **解释不能丢**：用户看到的输出可以简化，但决策载荷必须保留命中/跳过/证据/哈希/trace；
# 3. **协议要版本化**：字段变了就改 schema_version，消费方看不懂就拒绝。
#
# ## 下一步
#
# Phase 2 会写一个 dsh Adapter，把 Agent 的原始事件映射成 Phase 1 的 PolicyContext，
# 并保证"block 时不调用执行器、allow 时只调用一次"。
#
# 自测一下：如果要让一条规则只对"删除操作"生效，scope 应该怎么写？下一个单元给出答案。
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# ### 这一段代码要做什么（自测）
#
# 第一个问题：用 operation: delete 划范围，上下文里 operation 不是 delete 时规则就不参与判断。
#
# 第二个问题：范围从"只 controller"改成"controller 或 service"之后，同一个 service 上下文
# 从"跳过"变成"命中"——这正是 Phase 1 想让读者体会的差别。
#
# 试着改一改：把列表里的 service 换成 model，看结论怎么变。
# ----------------------------------------------------------------------------

# 17. 自测：范围怎么写，结论就怎么变
narrow_rule = rule_variant("ARCH-001", "error").model_copy(
    update={"scope": models.RuleScope(layer="controller")}
)
wide_rule = rule_variant("ARCH-001", "error").model_copy(
    update={"scope": models.RuleScope(layer=["controller", "service"])}
)
delete_rule = rule_variant("ARCH-001", "error").model_copy(
    update={"scope": models.RuleScope(layer="controller", operation="delete")}
)

service_context = sample_context(layer="service", dependencies=("repository",))
print(
    "窄范围（只 controller）     :",
    engine.evaluate(models.RuleSet(rules=(narrow_rule,)), service_context).decision.value,
    "|",
    engine.skipped_rule_id(narrow_rule, service_context),
)
print(
    "宽范围（controller + service）:",
    engine.evaluate(models.RuleSet(rules=(wide_rule,)), service_context).decision.value,
    "|",
    engine.skipped_rule_id(wide_rule, service_context),
)

controller_context = sample_context(layer="controller", dependencies=("repository",))
print(
    "只有 operation=delete 才生效 :",
    engine.evaluate(models.RuleSet(rules=(delete_rule,)), controller_context).decision.value,
    "|",
    engine.skipped_rule_id(delete_rule, controller_context),
)
print(
    "operation=delete 时         :",
    engine.evaluate(
        models.RuleSet(rules=(delete_rule,)),
        controller_context.model_copy(update={"operation": models.Operation.DELETE}),
    ).decision.value,
)

# ----------------------------------------------------------------------------
# **小结**：同一个 service 上下文，规则范围写成 controller 时被跳过，写成 [controller, service] 时命中；
# 而声明了 operation: delete 的规则，只有上下文真的带上 delete 操作才会生效（否则原因是 operation 缺失）。
#
# 范围写得越窄，规则越不容易命中；命中与否都会留下原因。改一个维度值重跑，就能看清
# scope、上下文与决策三者的关系——这正是 Phase 2 的 Adapter 必须提供完整维度的原因。
# ----------------------------------------------------------------------------

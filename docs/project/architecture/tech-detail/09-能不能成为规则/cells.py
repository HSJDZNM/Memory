
# -*- coding: utf-8 -*-
"""09-能不能成为规则：四条必要条件的判据（内容源）。"""
from __future__ import annotations

from notebook_lib import NotebookSpec, code, markdown

SPEC = NotebookSpec(
    stem="09-能不能成为规则",
    title="判定：一段文档要求能不能成为规则",
    summary="四条必要条件逐条判一遍：本地来源 / 可确定性判定 / 范围可枚举 / 结论落决策表；再用真实加载器验「代码拦得住」与「只能靠评审」的分界",
    temp_dir=".tmp/tech-detail/09",
    cells=(
        markdown(
            '''
# 09 能不能成为规则

这份 notebook 配合同名图 `09-能不能成为规则.drawio`。图回答一个问题：
**文档里的一段要求，什么情况下能变成一条会被引擎判定的规则，什么情况下不能。**

判据是四条**必要条件**，缺一条就只能停在第二层（Curated Guidance：进语料、供检索），
绝不能写成一条"看起来在管这件事、实际什么都没查"的规则：

| # | 条件 | 判别式（★ = 代码拦得住，○ = 只能靠评审） |
| --- | --- | --- |
| 1 | 本地来源 | ★ `source.kind` ∈ {`project-policy`, `standard`}；○ `source.path` 应指向真实存在的本地文件（可选字段，代码只查形状） |
| 2 | 可确定性判定 | ★ `enforcement.type = deterministic` + `checker` 是已实现的 6 个之一 + 该 checker 有验证器声明为它产证据 |
| 3 | 范围可枚举 | ★ 适用范围只用 6 个已知维度（`language` / `layer` / `module` / `operation` / `project` / `agent`）表达得出来 |
| 4 | 结论落在决策表 | ★ `severity` ∈ 四值枚举（`error` / `critical` → block；`info` / `warning` → allow_with_warnings） |

三个容易搞错的点，这份 notebook 会逐条用代码验：

1. **"能阻断"不是必要条件**——仓库里 43 条规则有 19 条是 `warning`，命中只告警；`DOC-001` 就是其中之一；
2. **代码拦得住的 ≠ 全部**——"来源指向真实文件""登记了溯源""有正反例""语义真的匹配"这四条
   都不在加载器里，靠的是评审 + 仓库里另外的门禁；
3. **过不了的正确去向是降级，不是硬写**——停在 Curated Guidance 供检索，比写一条空规则好。

**预备知识**：会读 YAML 就够了。下面全部用仓库里的真实规则与真实加载器，不访问网络。
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

TEMP = REPO_ROOT / ".tmp" / "tech-detail" / "09"
TEMP.mkdir(parents=True, exist_ok=True)

# 三个环境前提钉住：路径是从 REPO_ROOT 拼出来的、临时目录真的建好了、
# 这份 notebook 与同一章目录里同名的 .drawio 图一一对应（章节目录名 = 产物名）。
assert TEMP.is_dir() and TEMP.is_relative_to(REPO_ROOT), TEMP
TECH_DETAIL = REPO_ROOT / "docs" / "project" / "architecture" / "tech-detail"
CHAPTER = TECH_DETAIL / "09-能不能成为规则"
assert (CHAPTER / "09-能不能成为规则.drawio").is_file(), "同名图不存在"

print("仓库根目录:", REPO_ROOT.name, "（本次工作目录:", Path.cwd().name or Path.cwd(), "）")
print("临时目录:", TEMP.relative_to(REPO_ROOT).as_posix(), "（写操作只落在它下面）")
print("Python:", sys.version.split()[0])
'''
        ),
        markdown(
            '''
## 判据的输入：仓库里现在有哪些规则

判据不能空谈，先把"候选"摆出来。规则全部来自 `policies/<domain>/<ID>.yaml`，
用真实的 `policy.loader.load_rule_set` 原子加载成一个 `RuleSet`。

下面这张表是**现场统计**出来的，不是抄文档：条数、严重级别分布、每个 checker 有几条规则在用、
来源是"项目自订"还是"由镜像文档提炼"。

看表时留意两件事：**checker 的分布是极度不均衡的**（大部分规则靠同一个外部工具产证据），
以及 **`source.kind` 的两类规则在门禁上受到的对待并不一样**（下一格会说清）。
'''
        ),
        code(
            '''
# 加载全部规则，统计出判据要面对的"候选池"。
from collections import Counter

from policy.loader import load_rule_set

RULE_SET = load_rule_set([REPO_ROOT / "policies"], repo_root=REPO_ROOT)
RULES = RULE_SET.rules

print(pad("规则条数", 16) + str(len(RULES)) + "（来自 " + str(len(RULE_SET.source_paths)) + " 个文件）")
print(pad("规则集身份", 16) + RULE_SET.identity[:30] + "…")
print(pad("规则目录", 16) + ", ".join(sorted({path.split("/")[1] for path in RULE_SET.source_paths})))
print()
print(pad("severity", 22) + "条数")
print("-" * 40)
by_severity = Counter(item.severity.value for item in RULES)
for name, count in sorted(by_severity.items()):
    print(pad(name, 22) + str(count))
print()
print(pad("checker", 22) + "条数")
print("-" * 40)
by_checker = Counter(str(item.enforcement.checker) for item in RULES)
for name, count in sorted(by_checker.items()):
    print(pad(name, 22) + str(count))
print()
print(pad("source.kind", 22) + "条数")
print("-" * 40)
by_kind = Counter(item.source.kind for item in RULES)
for name, count in sorted(by_kind.items()):
    print(pad(name, 22) + str(count))

# 空规则集会让后面所有判据变成空转，先拦住。
assert RULES, "policies/ 下一条规则都没有加载到"
assert set(by_kind) <= {"project-policy", "standard"}, by_kind
print()
print("加载通过：每条规则都有一个确定的 checker 与一个本地来源类别。")
'''
        ),
        markdown(
            '''
## 判据一：本地来源

`source.kind` 是**受控枚举**，只有两个合法值：

- `project-policy`：项目自订的规则；
- `standard`：由标准 / 规范类文档提炼的规则。

"共享对话""外部 URL""模型记忆"都不能作为可执行来源——前两者在枚举这里就被挡住，
后者由"判定必须可确定性重放"这条不变量挡住（判定的输入只有上下文与证据包，没有模型）。

但 `source.path` 是**另一个分量**：它是可选字段，代码只查形状（必须是仓库相对路径、
不能逃出仓库、不能含命令元字符），**不查这个文件是否真的存在**。这是当前实现与理想之间的已知落差，
图脚注把它画成红色方框。

这一格先做两件事：数一遍 `source.path` 的真实情况（本仓库 43 条全都有，而且都指向真实文件），
再现场演示"加载器拦不住一个指向不存在文件的规则"。
'''
        ),
        code(
            '''
# 判据一：来源。用两边都在的验证器口径来判，不凭印象。
import yaml

from policy.loader import load_rule_file

without_path = [item.canonical_id for item in RULES if not item.source.path]
ghost_paths = [
    (item.canonical_id, str(item.source.path))
    for item in RULES
    if item.source.path and not (REPO_ROOT / item.source.path).is_file()
]
print(pad("规则总数", 18) + str(len(RULES)))
print(pad("有 source.path", 18) + str(len(RULES) - len(without_path)))
print(pad("path 不是真实文件", 18) + (", ".join(item[0] for item in ghost_paths) or "（无）"))
print()
# 判据一的两半：kind 是强制的（代码拦），path 指到真实文件是本仓库自己守住的（评审 + 现场核对）。
assert not without_path, "本仓库的规则都写了 source.path：" + repr(without_path[:5])
assert not ghost_paths, "有规则的来源指向了不存在的文件：" + repr(ghost_paths[:5])
print("本仓库 43 条规则的来源都写得出来、都指向真实文件。")

# —— 对照实验：把 source.path 换成一个不存在的路径，加载器**照样放行**。
document = yaml.safe_load((REPO_ROOT / "policies" / "coding" / "DOC-001.yaml").read_text(encoding="utf-8"))
document["source"]["path"] = "docs/mirrors/does-not-exist/index.md"
ghost_file = TEMP / "ghost-source.yaml"
ghost_file.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
                      encoding="utf-8", newline="")
ghost = load_rule_file(ghost_file, repo_root=REPO_ROOT)
print()
print("！落差复现：source.path =", ghost.rule.source.path)
print("  这条规则加载成功（kind 合法、path 形状合法），但那个文件在仓库里并不存在。")
assert not (REPO_ROOT / ghost.rule.source.path).exists()
print("  结论：'来源指向真实文件'只能靠评审与仓库里的门禁守住——加载器不负责这件事。")
'''
        ),
        markdown(
            '''
## 判据二：可确定性判定

这条要求有两半，都要满足：

1. `enforcement.type = deterministic`（目前唯一支持的类型），且必须声明 `checker`；
2. 这个 `checker` 得**真的能被判**：
   - 它在引擎的分派表里（`policy.checkers.SUPPORTED_CHECKERS`）；
   - 它在规则体模型里（`policy.models.KNOWN_CHECKERS`）——两者必须逐字一致；
   - **有人为它产证据**：`validation/validators.yaml` 里至少有一个验证器声明 `checkers: [它]`。

第 3 条最容易被忽略：规则说"要查什么"，验证器注册表说"谁去查"。少了后者，
这条规则永远判不了——注册表自己在加载阶段就会报错（'每个受支持的 checker 必须至少有一个验证器声明提供证据'）。

下面把 6 个 checker 各自的"责任人"列出来，并标出仓库里有没有规则真的在用它们。
'''
        ),
        code(
            '''
# 判据二：6 个 checker 的实现与"证据责任人"必须对齐。
from policy.checkers import SUPPORTED_CHECKERS
from policy.models import KNOWN_CHECKERS
from validators.registry import load_registry

REGISTRY = load_registry(REPO_ROOT / "validation" / "validators.yaml", root=REPO_ROOT)
providers = {}
for spec in REGISTRY.validators:
    for checker in spec.checkers:
        providers.setdefault(checker, []).append(spec.id)

print(pad("checker", 22) + pad("产证据的验证器", 16) + "仓库里在用的规则数")
print("-" * 78)
for checker in sorted(SUPPORTED_CHECKERS):
    owners = ", ".join(sorted(providers.get(checker, ()))) or "<无>"
    print(pad(checker, 22) + pad(owners, 24) + str(by_checker.get(checker, 0)))
print()

# 两边的 checker 集合必须逐字一致：引擎认识但模型不认识 = 规则写不出来；反之 = 判不了。
assert SUPPORTED_CHECKERS == KNOWN_CHECKERS, (sorted(SUPPORTED_CHECKERS), sorted(KNOWN_CHECKERS))
assert len(KNOWN_CHECKERS) == 6, sorted(KNOWN_CHECKERS)
# 每个 checker 都必须有人在产证据，否则注册表自己就加载不了。
nobody = [checker for checker in SUPPORTED_CHECKERS if not providers.get(checker)]
assert not nobody, "这些 checker 没有任何验证器为其产证据：" + repr(nobody)
# 规则里出现的 checker 必须都在这 6 个里面（加载器已经挡住了未知值，这里再钉一次）。
assert set(by_checker) <= set(SUPPORTED_CHECKERS), set(by_checker) - set(SUPPORTED_CHECKERS)
# 反过来看：有没有 checker 一个规则都没用？有——那说明端口就位但未启用。
unused = sorted(set(SUPPORTED_CHECKERS) - set(by_checker))
print("已实现但当前没有任何规则使用：" + (", ".join(unused) or "（无）"))
assert "type_check" in unused, "type_check 应当处于'端口就位、未启用'状态"
print("（type_check 就是这种：验证器与规则体都写好了，但装好 mypy 之前不启用——最后一格细说。）")
'''
        ),
        markdown(
            '''
## 判据三：范围可枚举

一条规则必须说清"它管哪些情况"，而**能用来说话的维度是固定的 6 个**：
`language` / `layer` / `module` / `operation` / `project` / `agent`。

- 同维度多值 = OR，跨维度 = AND；`*` 表示该维度显式不限制；省略该键表示不限制；
- `operation` 还必须是受控枚举（read / create / edit / delete / execute）；
- 拼错维度名**默认直接报错**（`reject`）——因为"拼错一个维度名"会让规则悄悄放大适用范围。
  确需忽略时得显式写 `scope.extra_policy: skip` 并接受被记进 `ignored_dimensions`。

表达不出来怎么办？**降级**：先用 6 个维度 + 项目档案里的取值试试；真要新增维度，
必须改代码（`KNOWN_SCOPE_DIMENSIONS` + `PolicyContext` 字段 + scope 访问器），不是改数据。

这一格把 6 个维度的取值口径也一起摆出来：**维度是代码定义的，取值是数据定义的**——
`language` 的取值来自项目档案，`layer` 来自"路径 → 组件"的映射。
'''
        ),
        code(
            '''
# 判据三：6 个已知维度 + 每维取值从哪里来。
from policy.models import KNOWN_SCOPE_DIMENSIONS, Operation, ScopeExtraPolicy

from validators.registry import load_project

PROJECT = load_project(root=REPO_ROOT)  # validation/project.yaml：语言识别与"路径 → 组件（层）"映射
language_values = tuple(spec.language for spec in PROJECT.languages)
layer_values = tuple(component.name for component in PROJECT.components)
declared_values = {}
for item in RULES:
    for dimension, value in item.scope.declared_dimensions.items():
        values = value if isinstance(value, tuple) else (value,)
        declared_values.setdefault(dimension, set()).update(values)

print(pad("维度", 12) + pad("取值从哪里来", 26) + "规则实际用到")
print("-" * 84)
for dimension in KNOWN_SCOPE_DIMENSIONS:
    if dimension == "language":
        origin, known = "validation/project.yaml", language_values
    elif dimension == "layer":
        origin, known = "validation/project.yaml", layer_values
    elif dimension == "operation":
        origin, known = "policy.models.Operation 枚举", tuple(x.value for x in Operation)
    else:
        origin, known = "上下文显式字段", ()
    used = sorted(declared_values.get(dimension, ()))
    print(pad(dimension, 12) + pad(origin, 30) + (", ".join(used) if used else "（没有规则声明）"))
print()
print(pad("维度总数", 12) + str(len(KNOWN_SCOPE_DIMENSIONS)) + "；default extra_policy = " + ScopeExtraPolicy.REJECT.value)
print()

# 硬约束：任何规则声明的维度都必须在 6 个已知维度里（Unknown 维度在加载阶段就被拒了）。
unknown_dims = sorted(
    {d for item in RULES for d in item.scope.declared_dimensions} - set(KNOWN_SCOPE_DIMENSIONS)
)
assert not unknown_dims, "有规则用了未知维度：" + repr(unknown_dims)
assert len(KNOWN_SCOPE_DIMENSIONS) == 6, KNOWN_SCOPE_DIMENSIONS
# 取值范围也不是随便写的：语言取值必须来自项目档案。
declared_languages = declared_values.get("language", set())
assert declared_languages <= set(language_values), (declared_languages, language_values)
print("43 条规则声明的维度只有", ", ".join(sorted(declared_values)), "，全部落在 6 个已知维度里；")
print("声明的 language 取值", sorted(declared_languages), "也都在项目档案里登记过。")
'''
        ),
        markdown(
            '''
## 判据四：结论落在决策表里

`severity` 是**必填**的，取值只有四个：`info` / `warning` / `error` / `critical`。
它决定"命中了会怎样"，也就是决策表：

| severity | 决策 | 含义 |
| --- | --- | --- |
| 无 violation | `allow` | 判过了，没有问题 |
| `info` / `warning` | `allow_with_warnings` | 放行并告警 |
| `error` / `critical` | `block` | 阻断 |

还有一条：需要人工审批的规则用 `enforcement.requires_approval` 表达，
决策表把它算成 `block + required_action=approval`——**授权是前置条件，不能用 warning 糊过去**。

所以"这条规则能不能阻断"根本不是一个必要条件：`DOC-001` 是 `warning`，
反例命中后的结论就是 `allow_with_warnings`。仓库里 43 条规则里 19 条都是这样。

这一格不空讲，直接调 `policy.models.expected_decision` 把决策表跑一遍，
再用它把仓库里的规则分个类。
'''
        ),
        code(
            '''
# 判据四：severity → 决策，用真实函数算，不抄表。
from policy.models import (
    BLOCKING_SEVERITIES,
    Decision,
    Evidence,
    RequiredAction,
    Severity,
    Violation,
    expected_decision,
)


def severity_decision(severity_value):
    """把某个 severity 的一条违规喂给决策表，返回它算出的决策。"""
    violation = Violation(
        rule_id="PROBE-001", rule_version=1, severity=Severity(severity_value),
        message="判据探针", evidence=Evidence(kind="probe", subject="probe", value=severity_value),
    )
    return expected_decision((violation,))


print(pad("severity", 12) + pad("决策表算出", 22) + "仓库里的规则数")
print("-" * 56)
blocking_total = 0
allowed_total = 0
for name in (item.value for item in Severity):
    decision = severity_decision(name)
    count = by_severity.get(name, 0)
    if decision is Decision.BLOCK:
        blocking_total += count
    else:
        allowed_total += count
    print(pad(name, 12) + pad(decision.value, 22) + str(count))
print("-" * 56)
print(pad("合计", 12) + pad("", 22) + str(blocking_total + allowed_total))
print()
print(pad("会阻断的规则", 16) + str(blocking_total) + " 条（error / critical）")
print(pad("只告警的规则", 16) + str(allowed_total) + " 条（info / warning）")
print()

# 决策表本身的关键结论：四值枚举 + 两种走向 + 审批优先。
assert {item.value for item in Severity} == {"info", "warning", "error", "critical"}
assert {item.value for item in BLOCKING_SEVERITIES} == {"error", "critical"}
assert severity_decision("warning") is Decision.ALLOW_WITH_WARNINGS
assert severity_decision("error") is Decision.BLOCK
approval = expected_decision((), required_action=RequiredAction.APPROVAL)
assert approval is Decision.BLOCK, "需要审批时必须以 block 表达"
assert set(by_severity) <= {item.value for item in Severity}, by_severity
# 关键一条：能阻断不是必要条件——仓库里就有 19 条只告警的规则。
assert allowed_total > 0 and blocking_total > 0
print("决策表核对通过；且'能不能阻断'确实不是必要条件：")
print("  仓库里 " + str(allowed_total) + " 条规则命中后只告警（含 DOC-001），" + str(blocking_total) + " 条会阻断。");
'''
        ),
        markdown(
            '''
## 代码拦得住的：一次真实的变异实验

前四格讲的是"判据是什么"。这一格回答**"到底哪一半是代码守住的"**——
做法是把真实的规则文件复制到临时目录，逐个改坏一个字段，看加载器会不会拦住、拦在哪里。

这比读源码更有说服力：错误消息里带着**出错的字段位置**，正好对应判据的哪一条。
注意每次只改一处，所以"没被拦住"本身也是信息。

最后一行的对照最值得看：一条 `type_check` 规则**写得完全合法**，加载器会放行——
但它当前判不了（证据靠 mypy，环境里没有这个工具）。这说明"加载成功"离"真的会判"还有一段距离。
'''
        ),
        code(
            '''
# 变异实验：把真实规则逐个改坏，记录加载器拦在哪。
from policy.loader import LoaderError, RuleFileError, load_rule_file, load_rules
from policy.models import EnforcementType, SOURCE_KINDS

BASE = yaml.safe_load((REPO_ROOT / "policies" / "coding" / "DOC-001.yaml").read_text(encoding="utf-8"))


def mutate(name, change):
    """复制真实规则 → 改一处 → 写进临时目录 → 试着加载；返回 (异常名, 出错的字段)。"""
    document = yaml.safe_load(yaml.safe_dump(BASE, allow_unicode=True, sort_keys=False))
    change(document)
    path = TEMP / (name + ".yaml")
    path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
                    encoding="utf-8", newline="")
    try:
        load_rule_file(path, repo_root=REPO_ROOT)
    except RuleFileError as error:
        return path, "RuleFileError", error.field
    except LoaderError as error:
        return path, "LoaderError", "<无字段位置>"
    return path, "加载成功（没拦住）", "<无>"


def type_check_rule(document):
    """写成一条 type_check 规则：shape 完全合法，但环境里没有 mypy。"""
    document["enforcement"]["checker"] = "type_check"
    document["rule"] = {"type_check": {"tool": "mypy", "codes": ["attr-defined"]}}


CASES = (
    # 字段级的错误带字段名；整个模型级的错误（checker 未知、规则体不匹配）没有字段位置，
    # 加载器把它记成 None —— 这也是为什么要看错误消息本身，不能只看字段。
    ("unknown-checker", "判据二：checker 不是已实现的 6 个", None,
     lambda d: d["enforcement"].update({"checker": "llm_judgement"})),
    ("body-mismatch", "判据二：规则体与 checker 不一致", None,
     lambda d: d.update({"rule": {"forbidden_dependency": ["requests"]}})),
    ("bad-severity", "判据四：severity 不在四值枚举里", "severity",
     lambda d: d.update({"severity": "blocker"})),
    ("unknown-scope-dim", "判据三：scope 用了未知维度", "scope",
     lambda d: d["scope"].update({"team": "payments"})),
    ("extra-field", "未知顶层字段（extra=forbid）", "owner",
     lambda d: d.update({"owner": "someone"})),
    ("bad-kind", "判据一：source.kind 不是本地来源", "source.kind",
     lambda d: d["source"].update({"kind": "conversation"})),
    ("absolute-path", "判据一：source.path 是绝对路径", "source.path",
     lambda d: d["source"].update({"path": "C:/secrets/policy.md"})),
)

measured = {}
print(pad("变异", 20) + pad("拦住的异常", 16) + pad("出错字段", 16) + "对应判据")
print("-" * 96)
for name, why, expected_field, change in CASES:
    path, kind, field = mutate(name, change)
    measured[name] = (path, kind, field)
    print(pad(name, 20) + pad(kind, 14) + pad("<模型级，无字段>" if field is None else field, 20) + why)
    assert kind == "RuleFileError", (name, kind)
    assert field == expected_field, (name, field, expected_field)
print()

# 对照：一条 type_check 规则完全合法 → 加载器放行。
path, kind, field = mutate("typecheck-rule", type_check_rule)
measured["typecheck-rule"] = (path, kind, field)
loaded = load_rule_file(path, repo_root=REPO_ROOT)
assert loaded.rule.enforcement.checker == "type_check"
assert loaded.rule.enforcement.type is EnforcementType.DETERMINISTIC
print(pad("typecheck-rule", 20) + pad("加载成功（没拦住）", 16) + pad("<无>", 16) + "shape 合法、但当前判不了")
print()

# 原子性：目录里一条好 + 一条坏，整批都不加载（错的顺序不影响结论）。
good = TEMP / "atomic-good.yaml"
document = yaml.safe_load(yaml.safe_dump(BASE, allow_unicode=True, sort_keys=False))
document["id"] = "ARCH-999"
good.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
                encoding="utf-8", newline="")
atomic_files = sorted(path.name for path in TEMP.glob("*.yaml"))
broken_files = {measured[name][0].name for name, _, _, _ in CASES}
try:
    load_rules(TEMP, repo_root=REPO_ROOT)
    raise AssertionError("临时目录里有坏文件，整批加载本该失败")
except RuleFileError as error:
    blamed = str(error.repo_path).rsplit("/", 1)[-1]
    print("原子加载：" + str(len(atomic_files)) + " 个规则文件，其中 " + str(len(broken_files))
          + " 个是坏的 → 整批不加载（" + type(error).__name__ + "）")
    print("  它抱怨的是 " + blamed + " —— 一条坏，整批不成。")
    assert blamed in broken_files, blamed
print()
print("小结：判据一/二/三/四里的 ★ 部分全在这里被真的拦下来了；这也正是'用户看不懂的规则'进不了引擎的原因。")
'''
        ),
        markdown(
            '''
## 代码拦不住的：四条"约定型"门禁

上一步证明了加载器很强，但它强在**形状**上。下面这四件事，加载器一件都不查——
它们靠评审与仓库里另外的门禁守住。这一格把每条都**当场验证一遍**：

1. **来源指向真实文件**：加载器不查（上一格已复现），本仓库自己守住了；
2. **登记溯源**：`source.kind: standard` 的规则应在 `knowledge/corpus.yaml` 的 `rule_sources` 里登记；
   登记是**约定**，但不登记的后果是"查不回原文"；
3. **正反例**：由镜像提炼的规则必须有 `tests/fixtures/rules/<ID>/{bad,good}.py`，由集成测试守；
4. **语义匹配**：代码只保证 checker 名合法，挡不住"把一条建议挂在 style_lint 上"——只能靠评审。

第 2、3 条是本仓库在**开发阶段**自己查的（不是一个测试文件的功劳，而是：登记缺失不会有任何一个
测试变红，只有评审会指出）。所以下面既是"统计"，也是"下次加规则时要自己问的问题"。
'''
        ),
        code(
            '''
# 四条约定型门禁的现场体检：能查的查，不能查的说清为什么。
from retrieval.corpus import load_corpus

corpus = load_corpus(REPO_ROOT / "knowledge" / "corpus.yaml", repo_root=REPO_ROOT)
registered = {(item.rule_id, item.rule_version) for item in corpus.manifest.rule_sources}
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "rules"
standard_rules = [item for item in RULES if item.source.kind == "standard"]

unregistered = [item.canonical_id for item in standard_rules if (item.id, item.version) not in registered]
no_fixture = [
    item.id for item in standard_rules
    if not (FIXTURES / item.id / "bad.py").is_file() or not (FIXTURES / item.id / "good.py").is_file()
]

print(pad("约定型门禁", 26) + pad("本仓库现状", 22) + "谁来守")
print("-" * 96)
print(pad("source.path 指向真实文件", 26) + pad(str(len(RULES)) + " 条全部成立", 22) + "评审 + 现场核对（加载器不查）")
print(pad("standard 规则登记溯源", 26)
      + pad(str(len(standard_rules) - len(unregistered)) + "/" + str(len(standard_rules)) + " 已登记", 22)
      + "评审；登记后由索引器强制（解析不到就失败）")
print(pad("正反例齐全", 26)
      + pad(str(len(standard_rules) - len(no_fixture)) + "/" + str(len(standard_rules)) + " 有正反例", 22)
      + "tests/integration/test_rule_corpus.py")
print(pad("语义真的匹配 checker", 26) + pad("无法自动核对", 22) + "评审（代码拦不住）")
print()

# 现状：这三条能自动查的都成立；不成立的时候应该看到具体是哪条规则。
assert not ghost_paths, "有规则的来源指向不存在的文件"
assert not unregistered, "这些 standard 规则没有登记溯源：" + repr(unregistered)
assert not no_fixture, "这些 standard 规则缺正反例：" + repr(no_fixture)
print("体检通过：" + str(len(standard_rules)) + " 条由镜像提炼的规则，来源、溯源、正反例都齐。")
print()
print("但请记住它们的**分量**：这三条在加载器里一条都没有。")
print("  把 source.path 改成不存在的文件 → 加载照样成功（上一格已复现）；")
print("  把 rule_sources 里那一行删掉 → 不会有任何测试变红，只是再也查不回原文；")
print("  删掉 bad.py → 覆盖率门禁会 FAIL 并指名道姓，但那也是另一个进程里的事。")
'''
        ),
        markdown(
            '''
## 两条结构性淘汰：整类要求根本进不来

除了"单条要求过不过判据"，还有两条是**整类**被挡在门外的，它们不是评审问题，而是结构问题：

1. **非 Python 的规范上不了线**：语言专项规则包只声明了 `python-core` 与 `python-tools`，
   项目档案里也只登记了 `python`。一份 .NET 或 OWASP 的中文规范可以进语料（本仓库就收了
   `dotnet-design-guidelines` 镜像），但**没有对应的验证器**就产不出证据——规则要么写不出来，
   要么写出来永远判不了。
2. **`type_check` 规则在装好 mypy 之前一律不启用**：工具缺失在验证器层是**失败关闭**
   （`unavailable`），会让所有需要它的规则一次性以 critical 阻断。所以正确做法是先把工具装齐，
   再启用规则——而不是先写规则、等环境出问题。

这一格两条都验：查语言包与项目档案的口径，并对 `type_check` 的负责人 `tool.mypy` 做一次真实探测。
'''
        ),
        code(
            '''
# 结构性淘汰：语言包口径 + 外部工具探针。
from pathlib import Path

from validators.adapters.base import probe_tool
packs = {pack.id: pack.language for pack in REGISTRY.rule_packs}
print(pad("规则包", 22) + pad("语言", 10) + "包含的验证器")
print("-" * 88)
for pack in REGISTRY.rule_packs:
    print(pad(pack.id, 22) + pad(pack.language, 10) + ", ".join(pack.validators))
print()
print(pad("项目档案登记的语言", 22) + ", ".join(language_values))
print(pad("引擎支持的 checker", 22) + ", ".join(sorted(SUPPORTED_CHECKERS)))
print()

# 淘汰一：非 Python 要求没有语言包 → 没有验证器 → 产不出证据。
assert set(packs.values()) == {"python"}, packs
assert set(language_values) == {"python"}, language_values
assert "dotnet-design-guidelines" in {item.name for item in corpus.manifest.datasets}, "非 Python 规范应当停在语料层"
print("淘汰一：语言包只有 python，所以任何非 Python 规范最多只能停在 Curated Guidance（进语料、供检索）。")
print("  证据：dotnet-design-guidelines 这份 .NET 规范就在语料里，但没有一条规则引用它产证据。")
print()

# 淘汰二：type_check 的负责人是 tool.mypy——真探测一次，看它现在能不能用。
mypy_spec = REGISTRY.spec("tool.mypy")
assert mypy_spec is not None and "type_check" in mypy_spec.checkers
probe = probe_tool(mypy_spec.tool, timeout_ms=5000, max_output_bytes=65536,
                   workspace=REPO_ROOT, tmp_dir=TEMP)
print(pad("tool.mypy 探测结果", 22) + probe.status.value)
print(pad("说明", 22) + probe.reason)
print()
if probe.ok:
    print("本机装好了 mypy；但仓库当前没有 type_check 规则，端口就位、尚未启用。")
else:
    print("本机没有 mypy → 现在写一条 type_check 规则，命中判定时会以 critical 失败关闭：")
    print("  不是'跳过'，是'所有 Python 文件一次性判红'。所以：装好工具之前不启用这类规则。")
assert probe.status.value in {
    "ok", "unavailable", "version_mismatch", "timeout", "crashed", "config_error", "output_invalid",
}, probe.status.value
print()
print("两条结构性淘汰都成立：非 Python 规范进不来，缺工具的类型检查规则现在不启用。")
'''
        ),
        markdown(
            '''
## 小结

- **四条必要条件是判据，不是描述**：本地来源、可确定性判定、范围可枚举、结论落决策表。
  前四格逐条判过——本仓库 43 条规则全部满足，而且三份数据（规则 / 项目档案 / 验证器注册表）互相对得上。
- **"能阻断"不是必要条件**：43 条里 19 条是 `warning` 或 `info`，命中只产
  `allow_with_warnings`；`DOC-001` 就是其中之一。要不要阻断是 `severity` 的选择，不是规则的门槛。
- **代码拦得住的是形状**：未知 checker、规则体与 checker 不一致、未知维度、非法 severity、
  未知字段、非法来源与路径、整批原子性——变异实验里每一条都被 `RuleFileError` 按字段位置拦下。
- **代码拦不住的是"真的"**：来源是否指向真实文件、是否登记了溯源、是否有正反例、语义是否真的匹配。
  这四条靠评审与仓库里另外的门禁；它们不会让加载器变红，所以更容易被忘记。
- **过不了的正确去向是降级，不是硬写**：停在 Curated Guidance（进 `knowledge/corpus.yaml`、供检索与解释），
  比写一条"看起来在管这件事、实际什么都没查"的规则好得多——后者正是规则体与 checker 一致性检查要挡的东西。
- **两条结构性淘汰**：非 Python 规范上不了线（没有语言包与验证器）；`type_check` 在装好 mypy 之前不启用
  （缺工具 = 失败关闭，不是跳过）。

配套看 `08-单条规则-从文档到判定.ipynb`：那里把一条满足全部四条判据的规则（`DOC-001`）
从镜像原文一路走到决策载荷，包括它的正反例与溯源怎么被查回来。
'''
        ),
    ),
)

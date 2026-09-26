"""与协议无关的依赖文本事实：从"本次改动引入的文本"里提取直接依赖。

预执行门禁要回答的问题是"**这次改动引入了什么**"，而不是"文件里原本有什么"
（后者属于 Phase 4 的 post-execute 与 Phase 5 的 Validator）。因此这里刻意只看
变更片段：edit 的 new_string 通常不是完整模块，用行级词法提取而不是 ast.parse；
`ast.parse` 只用来回答"这段文本解析得了吗"——那是一个**显式状态**，不是"没有依赖"。

放在公共层的理由：依赖是**核心上下文的维度**，不是某一家 Agent 的属性。
Phase 2 的 dsh Adapter 与 Phase 6 的多 Agent 路径**共用这一份实现**（Phase 6 的接线点在
`adapters.base.Adapter.to_policy_context`：那里 file 已归一化、language 已由 adapter
配置声明解析出来）。同一个语义出现两份实现，迟早会在其中一份上漏判——G6 就是这样漏的：
相对导入与动态导入曾经只在 Phase 2 那条路径上被识别，多 Agent 路径静默放行。

本模块不认识任何 Agent 的错误类型（失败用自己的 DependencyTextError 表达），
language 只作为入参：它由 adapter 配置的 languages / default_language 解析后传入，
**绝不从文件名或路径猜**。
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass
from typing import Optional, Tuple

from policy.checkers import UNPROVEN_CHANGED_TEXT, UNPROVEN_DYNAMIC_IMPORT
from policy.models import canonical_identifier

__all__ = [
    "DependencyProposal",
    "DependencyTextError",
    "governed_dependencies",
    "propose_dependencies",
    "proposed_dependencies",
]


class DependencyTextError(ValueError):
    """变更文本不满足提取前提（例如根本不是文本）。

    共享层不得依赖某一家 Agent 自己的错误类型（Phase 2 的 DshEventError 属于 dsh
    适配器）：这里只用 ValueError 的子类，由调用方按自己的协议翻译成失败响应。
    """


# 变更文本里的 import。只做词法提取，不做语义推断，也不读磁盘。
# from 形态与 import 形态分开匹配：import a, b as c 里的每个名字都要算上，
# 否则"一次改动引入多个依赖"会被漏判（正是预执行门禁最不能漏的情况）。
#
# from 形态允许前导点（相对导入）：from . import repository 的目标是**子模块**，
# 只取顶层名字会让它落在 "from ." 上（没有名字），规则永远看不见它。
_FROM_IMPORT_RE = re.compile(
    r"^[ \t]*from[ \t]+(\.*[A-Za-z_][\w.]*|\.+)[ \t]+import[ \t]+([^\n]*)",
    re.MULTILINE,
)
_PLAIN_IMPORT_RE = re.compile(r"^[ \t]*import[ \t]+([^\n]+)$", re.MULTILINE)
# 点分模块路径：允许相对导入的前导点（".repository" / "..pkg.mod"）。
_MODULE_PATH_RE = re.compile(r"^\.*[A-Za-z_][\w.]*$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_]\w*$")
# 星号不是模块名：`from x import *` 里的 "*" 必须跳过。
# 提成命名常量而不是行内字面量：bandit 的 B105 会把"疑似口令的变量与字符串字面量
# 比较"判成硬编码口令（`token` 命中它的变量名模式），而这里比较的是通配符。
_WILDCARD = "*"

# 动态导入的调用点。识别口径与 AST 路径一致（src/validators/python_ast.py:252-262）：
# 点分调用的末段是 import_module，或整个点分名在动态导入入口白名单里
# （__import__ / importlib.import_module；from importlib import import_module 之后的
# 本地名字按"末段是 import_module"一并覆盖，别名写法才漏不掉）。
_DYNAMIC_CALL_RE = re.compile(
    r"(?<![\w.])(?:[A-Za-z_][\w.]*[ \t]*\.[ \t]*)?(import_module|__import__)[ \t]*\("
)
# 动态导入的第一个实参是不是**单个**字符串字面量（常量）。
# 只认 r/u 前缀：f-string 不是常量，b"" 不是 str，拼接（"a" + x）也不是常量 ——
# 一律算"证明不了"，交给依赖类 checker 失败关闭。
_LITERAL_ARGUMENT_RE = re.compile(
    r"""^[ \t]*(?:[rRuU])?(?:"([^"\n]*)"|'([^'\n]*)')[ \t]*(?:,|\))"""
)


@dataclass(frozen=True)
class DependencyProposal:
    """一次依赖提取的完整结果：证明得了的、证明不了的、以及文本能不能解析。

    三类都要显式给出来，缺任何一类都会让"没查"看起来像"查过了"：

    - names：能证明的直接依赖（完整点分路径，相对导入保留前导点）；
    - unproven_dynamic：出现动态导入但目标不是字符串字面量 —— 依赖集无法静态确定；
    - parseable：变更文本能否作为独立模块（或整体缩进一级的块）解析。

    parseable 不是 None、也不是空元组，而是一个必须被显式处理的布尔值：
    预执行路径拿到的是**变更片段**，片段解析不了很常见，但"解析不了"与"没有依赖"
    是两件事（AGENTS.md 第 20 条），所以它只能"带着问号继续"，不能"当作没有"。
    """

    names: Tuple[str, ...] = ()
    unproven_dynamic: Tuple[str, ...] = ()
    parseable: bool = True

    @property
    def unproven(self) -> bool:
        """是否存在证明不了的部分（动态导入目标不可证 / 片段解析不了）。"""

        return bool(self.unproven_dynamic) or not self.parseable


def _code_lines(text: str) -> str:
    """去掉整行注释后再拼回：整行注释里的 import 不是依赖（行内注释仍是残余面）。"""

    return "\n".join(
        line for line in text.split("\n") if not line.lstrip(" \t").startswith("#")
    )


def _module_names(raw: str) -> Tuple[str, ...]:
    """解析 import a.b as c, d 里的模块路径（去掉 as 别名与行内注释）。"""

    names: list[str] = []
    for chunk in raw.split("#")[0].split(","):
        token = chunk.strip()
        if not token:
            continue
        candidate = token.split()[0]
        if _MODULE_PATH_RE.match(candidate):
            names.append(canonical_identifier(candidate))
    return tuple(names)


def _from_targets(raw_module: str, raw_names: str) -> Tuple[str, ...]:
    """解析 from X import a, b 的目标。

    - X 本身是一个依赖（from repository import OrderRepository）；
    - 每个被导入的名字还可能是**子模块**（from shop import order_repository）——
      这正是"Controller 直接依赖 Repository"最常见的写法之一：AST 路径会把边落在
      子模块文件上（src/validators/depgraph.py:360-375），预执行路径没有模块索引，
      只能把候选全部登记。宁可多登记候选，不能漏登记：漏登记等于结构性放行。

    相对导入（from . import repository）的目标是 ".repository"：前导点是"相对"这一
    事实，不是可以丢掉的噪声。
    """

    module = canonical_identifier(raw_module)
    targets: list[str] = []
    if module.strip("."):
        targets.append(module)
    prefix = "" if module == "." else module
    for chunk in raw_names.split("#")[0].split(","):
        token = chunk.strip()
        if not token or token == _WILDCARD:
            continue
        name = token.split()[0]  # 去掉 as 别名
        if not _IDENTIFIER_RE.match(name):
            continue
        targets.append(canonical_identifier(prefix + "." + name if prefix else "." + name))
    return tuple(targets)


def _dynamic_targets(text: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """提取动态导入：证明得了的字面量目标 + 证明不了的调用点。"""

    proven: list[str] = []
    unproven: list[str] = []
    for match in _DYNAMIC_CALL_RE.finditer(text):
        window = text[match.end() :]
        stop = len(window)
        for index, char in enumerate(window):
            if char in ")\n":
                stop = index
                break
        literal = _LITERAL_ARGUMENT_RE.match(window[:stop] + ")")
        target = None
        if literal is not None:
            target = literal.group(1) if literal.group(1) is not None else literal.group(2)
            target = (target or "").strip()
        if target is None or not _MODULE_PATH_RE.match(target):
            unproven.append(canonical_identifier(match.group(1)))
            continue
        proven.append(canonical_identifier(target))
    return tuple(proven), tuple(unproven)


def _is_parseable(text: str) -> bool:
    """变更文本能否解析：先按独立模块，再按"整体缩进一级的代码块"。

    第二种形态是 edit 的常态（new_string 常是被替换的缩进块，例如一个方法体），
    因此它只证明"这段文本在语法上可能成立"，不证明它就是完整文件。
    """

    if not text.strip():
        return True
    try:
        ast.parse(text)
        return True
    except (SyntaxError, ValueError):
        pass
    try:
        ast.parse("if True:\n" + textwrap.indent(text, "    "))
        return True
    except (SyntaxError, ValueError):
        return False


def propose_dependencies(text: str) -> DependencyProposal:
    """从"本次变更引入的文本"里提取依赖提案，去重并稳定排序。

    刻意只看变更片段：预执行门禁要回答的是"这次改动引入了什么"，而不是"文件里原本有什么"
    （后者属于 Phase 4 的 post-execute 与 Phase 5 的 Validator）。
    片段通常不是完整模块（例如 edit 的 new_string），因此主体是行级词法提取；
    解析性只作为**一个显式状态**给出（见 DependencyProposal），不当作"没有依赖"。
    """

    if not isinstance(text, str):
        raise DependencyTextError(f"变更文本必须是字符串，得到 {type(text).__name__}")

    code = _code_lines(text)
    found: set[str] = set()
    for match in _FROM_IMPORT_RE.finditer(code):
        found.update(_from_targets(match.group(1), match.group(2)))
    for match in _PLAIN_IMPORT_RE.finditer(code):
        found.update(_module_names(match.group(1)))
    dynamic, unproven = _dynamic_targets(code)
    found.update(dynamic)

    return DependencyProposal(
        names=tuple(sorted(found)),
        unproven_dynamic=tuple(sorted(set(unproven))),
        parseable=_is_parseable(text),
    )


def proposed_dependencies(text: str) -> Tuple[str, ...]:
    """能证明的依赖名（向后兼容的薄封装）；证明不了的部分见 propose_dependencies。"""

    return propose_dependencies(text).names


def governed_dependencies(text: str, *, language: Optional[str]) -> Tuple[str, ...]:
    """把依赖提案变成 PolicyContext 的 dependencies 维度。

    - 能证明的依赖名照常登记（完整点分路径，"forbidden: repository" 由 checker
      按词匹配命中 shop.order_repository 这类写法）；
    - 证明不了的部分登记保留标记（见 policy.checkers.UNPROVEN_DEPENDENCY_TOKENS），
      由依赖类 checker 在规则 scope 命中时失败关闭。预执行路径没有模块索引、
      变更片段也不一定完整，因此"证明不了"必须是显式状态，不能是空元组。
    - 依赖抽取与解析性检查只对声明为 python 的路径做：import 语法与 ast.parse 都是
      Python 的事实，对别的语言做这件事只会制造误判（语言来自配置，不从文件名猜）。

    三条 Phase 6 路径（json / event / dsh）与 Phase 2 的 dsh 路径都调用这一个函数：
    同一个语义只有一份实现，"换个写法就绕过"不会再在某一条路径上复活。
    """

    if language != "python":
        return ()
    proposal = propose_dependencies(text)
    names = set(proposal.names)
    if proposal.unproven_dynamic:
        names.add(UNPROVEN_DYNAMIC_IMPORT)
    if not proposal.parseable:
        names.add(UNPROVEN_CHANGED_TEXT)
    return tuple(sorted(names))

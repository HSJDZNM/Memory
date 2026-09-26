"""代码类委派工具的结构化静态检查：数据驱动、失败关闭。

存在理由（G9）：`exec.run_code` 这类工具由 Agent 运行时执行（platform 侧 driver=none），
平台既执行不了、也拿不到事后证据，唯一门禁曾是人工审批——审批一过就是任意代码，且不留证据。
这里按注册表声明的 `CodeCheckSpec` 在放行之前做一次 AST 检查：禁 import 的模块、
禁直接调用的名字、禁出现的属性链，**全部来自注册表数据**，代码里没有任何硬编码判断。

三条不可让步的性质：

1. **失败关闭**：代码解析不了 = 拒绝（`code_parse_failed`），不是跳过、不是放行；
2. **确定性**：同一段代码总是得到同一条结论（命中按行号 / 类别 / 名字排序后上报）；
3. **诚实标注**：这是**结构性检查，不是沙箱**。绕过的写法客观存在（拼接字符串构造名字、
   用下标取函数、动态属性、把调用拆进数据结构……），`CodeCheckSpec.known_gaps` 把它们
   如实写出来，pre-check 会把它带进审计警告——绝不让调用方以为"查过了就等于隔离"。

真正的隔离属于运行时的文件系统与进程沙箱（AGENTS.md 第 17 条对命令白名单写的是同一句话），
不在本阶段。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Optional, Sequence

from .models import CodeCheckSpec, ReasonCode

__all__ = [
    "CodeCheckOutcome",
    "check_code",
    "dotted_name",
]

# 上报条数上限：细节要能进审计（单条记录有体积上限），命中总数另行给出。
_MAX_REPORTED_HITS = 8


@dataclass(frozen=True)
class CodeCheckOutcome:
    """一次代码静态检查的结论（passed=False 时 reason_code 说明是哪一类拒绝）。"""

    passed: bool
    reason_code: ReasonCode
    detail: str
    hits: tuple[str, ...] = ()


def dotted_name(node: ast.AST) -> Optional[str]:
    """把 a.b.c 形态的属性链还原成点分字符串；不是纯 Name/Attribute 链时返回 None。

    不猜：`f().x` 这种"调用结果上的属性"还原不出名字，返回 None（宁可不匹配，也不假装）。
    """

    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _matches(candidate: str, declared: Sequence[str]) -> Optional[str]:
    """点分名的前缀匹配：声明 os 覆盖 os.system / os.popen，但不覆盖 socket.os。"""

    for entry in declared:
        if candidate == entry or candidate.startswith(entry + "."):
            return entry
    return None


def _collect(tree: ast.AST, declaration: CodeCheckSpec) -> list[tuple[int, str, str]]:
    """收集全部命中：`(行号, 类别, 名字)`，不做判断、不做取舍。"""

    hits: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                matched = _matches(alias.name, declaration.forbidden_imports) or _matches(
                    root, declaration.forbidden_imports
                )
                if matched is not None:
                    hits.append((node.lineno, "import", alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                matched = _matches(node.module, declaration.forbidden_imports) or _matches(
                    root, declaration.forbidden_imports
                )
                if matched is not None:
                    hits.append((node.lineno, "import", node.module))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in declaration.forbidden_calls:
                hits.append((node.lineno, "call", node.func.id))
        if isinstance(node, ast.Attribute):
            candidate = dotted_name(node)
            if candidate is not None and _matches(candidate, declaration.forbidden_attributes):
                hits.append((node.lineno, "attribute", candidate))
    return sorted(set(hits))


def _describe(hits: Sequence[tuple[int, str, str]]) -> tuple[str, ...]:
    labels = {"import": "导入", "call": "调用", "attribute": "属性"}
    return tuple(
        f"第 {line} 行 {labels.get(kind, kind)} {name}" for line, kind, name in hits
    )


def check_code(source: object, declaration: CodeCheckSpec) -> CodeCheckOutcome:
    """按声明的检查项判定一段代码；任何"证明不了"的情况都拒绝（失败关闭）。"""

    if not isinstance(source, str) or not source.strip():
        return CodeCheckOutcome(
            passed=False,
            reason_code=ReasonCode.CODE_PARSE_FAILED,
            detail="代码参数为空或不是字符串：没有可解析的内容，证明不了它安全，按失败关闭拒绝",
        )

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        where = f"第 {error.lineno} 行" if error.lineno else "未知位置"
        return CodeCheckOutcome(
            passed=False,
            reason_code=ReasonCode.CODE_PARSE_FAILED,
            detail=f"代码无法解析（{where}: {error.msg}）：解析不了就证明不了，拒绝执行而不是跳过",
        )
    except Exception as error:  # noqa: BLE001 - 解析器的任何异常都按"证明不了"处理
        return CodeCheckOutcome(
            passed=False,
            reason_code=ReasonCode.CODE_PARSE_FAILED,
            detail=f"代码解析失败（{type(error).__name__}）：证明不了它安全，拒绝执行",
        )

    hits = _collect(tree, declaration)
    if hits:
        described = _describe(hits)
        shown = "；".join(described[:_MAX_REPORTED_HITS])
        more = (
            ""
            if len(described) <= _MAX_REPORTED_HITS
            else f"（另有 {len(described) - _MAX_REPORTED_HITS} 处）"
        )
        return CodeCheckOutcome(
            passed=False,
            reason_code=ReasonCode.CODE_BLOCKED,
            detail=(
                f"代码命中 {len(hits)} 处禁止面（kind={declaration.kind}）：{shown}{more}。"
                "检查项来自注册表数据，这里是结构性检查而不是沙箱"
            ),
            hits=described,
        )

    gaps = "；".join(declaration.known_gaps) or "（注册表未登记已知绕过形态，这本身是一个待补项）"
    return CodeCheckOutcome(
        passed=True,
        reason_code=ReasonCode.ALLOW,
        detail=(
            f"未命中声明的禁止面（kind={declaration.kind}，param={declaration.param}）；"
            f"已知不可覆盖的形态：{gaps}"
        ),
    )

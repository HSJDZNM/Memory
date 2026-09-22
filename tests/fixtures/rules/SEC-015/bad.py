"""反例：授权检查失败时把异常静默吞掉（fail open）。

违反 SEC-015（OWASP Authorization Cheat Sheet：Ensure all exception and failed access
control checks are handled no matter how unlikely they seem）——pass 让检查失败变成"没失败"，
continue 让出错的条目被悄悄跳过，调用方继续往下走。
"""


def can_edit(document, user):
    """判断用户能否编辑该文档：检查抛出的异常被 pass 吞掉，随后一律放行。"""

    try:
        document.require_owner(user)
    except Exception:
        pass
    return True


def filter_editable(documents, user):
    """过滤可编辑文档：出错的条目被 continue 悄悄跳过。"""

    editable = []
    for document in documents:
        try:
            document.require_owner(user)
        except Exception:
            continue
        editable.append(document)
    return editable

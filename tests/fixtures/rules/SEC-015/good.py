"""正例：授权检查失败被显式处理（记录并拒绝），不静默吞掉（SEC-015）。"""

import logging

logger = logging.getLogger(__name__)


def can_edit(document, user):
    """判断用户能否编辑该文档；检查失败时记录并按拒绝处理。"""

    try:
        document.require_owner(user)
    except Exception:
        logger.warning("ownership check failed for %s", document)
        return False
    return True


def filter_editable(documents, user):
    """过滤可编辑文档；检查失败的条目记录后按不可编辑处理。"""

    editable = []
    for document in documents:
        allowed = True
        try:
            document.require_owner(user)
        except Exception:
            logger.warning("skipping document after check failure: %s", document)
            allowed = False
        if allowed:
            editable.append(document)
    return editable

"""SEC-012 反例：关闭模板自动转义 / mark_safe / RawSQL。"""
# 违反了 Django Security Cheat Sheet "## Cross Site Scripting (XSS)" 的
#   "Try to avoid using the `safe` filter (or `mark_safe` function) to disable Django's
#    automatic template escaping."
# 以及 Django REST Framework Cheat Sheet "#### SQLi" 的
#   "DO NOT add user input to dangerous methods (`raw()`, `extra()`, `cursor.execute()`)."
# 本规则必须命中的码：S701（关闭模板自动转义）、S308（mark_safe）、S611（Django RawSQL）。
from django.db.models.expressions import RawSQL
from django.utils.safestring import mark_safe
from jinja2 import Environment

Environment(autoescape=False)


def render(value):
    """把参数直接当 HTML 输出（dangerous）。"""
    return mark_safe(f"<i>{value}</i>")


def annotate(queryset, value):
    """用 RawSQL 拼查询（dangerous）。"""
    return queryset.annotate(score=RawSQL("%s" % value, []))

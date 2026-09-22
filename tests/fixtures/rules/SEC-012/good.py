"""SEC-012 正例：保留自动转义，用 format_html 与参数化查询。"""
# 原文 "## Cross Site Scripting (XSS)"：
#   "Use the built-in template system to render templates in Django. Refer to Django's
#    Automatic HTML escaping documentation to learn more."
# format_html 会转义参数；查询交给 ORM，不使用 mark_safe / RawSQL。
from django.utils.html import format_html
from jinja2 import Environment

Environment(autoescape=True)


def render(value):
    """把参数转义后拼进 HTML 片段。"""
    return format_html("<i>{}</i>", value)

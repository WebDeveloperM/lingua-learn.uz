import re

from django import template
from django.utils.html import conditional_escape, escape, linebreaks
from django.utils.safestring import mark_safe

from ..passages import passage_paragraphs

register = template.Library()


@register.filter
def paragraphs(text):
    """The paragraphs of a plain reading text, ready to be printed one by one."""
    return passage_paragraphs(text)

BOLD_RE = re.compile(r'\*\*(.+?)\*\*')


@register.filter(needs_autoescape=True)
def inline_bold(value, autoescape=True):
    """Escape the text, then turn **word** into <strong>word</strong>."""
    text = conditional_escape(value) if autoescape else value
    return mark_safe(BOLD_RE.sub(r'<strong>\1</strong>', str(text)))


@register.filter
def transcript_html(value):
    """An audio transcript as paragraphs (blank line = new paragraph); **answers** are highlighted with <mark>."""
    if not (value or '').strip():
        return ''
    return mark_safe(linebreaks(BOLD_RE.sub(r'<mark>\1</mark>', escape(value)), autoescape=False))

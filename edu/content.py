"""Безопасный рендеринг Markdown-уроков.

Markdown превращается в HTML, затем HTML пропускается через белый список
тегов и атрибутов (защита от XSS: <script>, onerror=, javascript: и т.п.).
"""
import html
from html.parser import HTMLParser

import markdown
from markupsafe import Markup

ALLOWED_TAGS = {
    "p", "br", "hr", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "b", "i",
    "code", "pre", "blockquote", "a", "table", "thead", "tbody", "tr", "th", "td", "del",
}
VOID_TAGS = {"br", "hr"}
DROP_CONTENT = {"script", "style", "iframe", "object", "embed", "template"}
SAFE_SCHEMES = ("http://", "https://", "mailto:", "#")


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT:
            self._skip += 1
            return
        if self._skip or tag not in ALLOWED_TAGS:
            return
        attr_str = ""
        attrs = dict(attrs)
        if tag == "a":
            href = (attrs.get("href") or "").strip()
            if href.lower().startswith(SAFE_SCHEMES):
                attr_str = f' href="{html.escape(href, quote=True)}" rel="noopener noreferrer" target="_blank"'
        elif tag == "code":
            cls = attrs.get("class") or ""
            if cls.startswith("language-") and cls[9:].replace("-", "").replace("+", "").replace("#", "").isalnum():
                attr_str = f' class="{html.escape(cls, quote=True)}"'
        self.out.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(html.escape(data, quote=False))


def sanitize_html(raw: str) -> str:
    parser = _Sanitizer()
    parser.feed(raw)
    parser.close()
    return "".join(parser.out)


def render_markdown(text: str) -> Markup:
    if not text:
        return Markup("")
    raw = markdown.markdown(
        text,
        extensions=["fenced_code", "tables", "sane_lists", "nl2br"],
        extension_configs={},
        output_format="html",
    )
    return Markup(sanitize_html(raw))

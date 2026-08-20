"""Stdlib HTML-to-plain-text conversion for connector message bodies."""

from html.parser import HTMLParser

_SKIP_TAGS = frozenset({"script", "style"})
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "p",
        "pre",
        "section",
        "table",
        "tr",
        "ul",
        "ol",
    }
)


class _HTMLToTextParser(HTMLParser):
    """Collect visible text while dropping markup, script, and style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in _BLOCK_TAGS and tag != "br":
            self._chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._chunks.append(data)


def html_to_plain_text(html: str) -> str:
    """Return visible text from HTML without tags or executable content."""
    parser = _HTMLToTextParser()
    parser.feed(html)
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser._chunks).splitlines()]
    return "\n".join(line for line in lines if line).strip()

"""Finds exact character offsets of the tags the rewriter edits.

The rewriter splices new text into the original HTML at these offsets, so
everything it does not touch stays byte for byte as the origin sent it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser

TRACK_END = {"title", "h1", "a"}


@dataclass
class Element:
    tag: str
    attrs: list[tuple[str, str | None]]
    start: int  # offset of "<"
    start_end: int  # offset just after the start tag's ">"
    end_start: int | None = None  # offset of the matching "</tag>"
    end_end: int | None = None

    def attr(self, name: str) -> str | None:
        for k, v in self.attrs:
            if k == name:
                return v
        return None


@dataclass
class Located:
    elements: list[Element] = field(default_factory=list)
    head_close: int | None = None

    def find(self, tag: str, **attrs: str) -> list[Element]:
        out = []
        for el in self.elements:
            if el.tag != tag:
                continue
            if all(el.attr(k.replace("_", "-")) == v for k, v in attrs.items()):
                out.append(el)
        return out


class _Locator(HTMLParser):
    def __init__(self, src: str) -> None:
        super().__init__(convert_charrefs=True)
        self.src = src
        self.line_starts = [0]
        for i, ch in enumerate(src):
            if ch == "\n":
                self.line_starts.append(i + 1)
        self.result = Located()
        self.open: dict[str, list[Element]] = {t: [] for t in TRACK_END}
        self.in_head = False

    def _offset(self) -> int:
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self._offset()
        text = self.get_starttag_text() or ""
        el = Element(tag=tag, attrs=attrs, start=start, start_end=start + len(text))
        self.result.elements.append(el)
        if tag in TRACK_END:
            self.open[tag].append(el)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self._offset()
        text = self.get_starttag_text() or ""
        self.result.elements.append(Element(tag=tag, attrs=attrs, start=start, start_end=start + len(text)))

    def handle_endtag(self, tag: str) -> None:
        start = self._offset()
        end = self.src.index(">", start) + 1
        if tag == "head" and self.result.head_close is None:
            self.result.head_close = start
        if tag in TRACK_END and self.open[tag]:
            el = self.open[tag].pop()
            el.end_start, el.end_end = start, end


def locate(src: str) -> Located:
    parser = _Locator(src)
    parser.feed(src)
    parser.close()
    return parser.result

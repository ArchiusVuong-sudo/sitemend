"""Small helpers for reading a parsed page."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

PUBLIC_HOST = "mossgrove-clayworks.example"
_WS = re.compile(r"\s+")


def squash(text: str) -> str:
    return _WS.sub(" ", text).strip()


def outer(node: LexborNode, limit: int = 400) -> str:
    html = node.html or ""
    return html if len(html) <= limit else html[: limit - 3] + "..."


def start_tag(node: LexborNode) -> str:
    """The node's start tag as HTML, without children (used as evidence)."""
    attrs = "".join(f' {k}="{v}"' if v is not None else f" {k}" for k, v in node.attributes.items())
    return f"<{node.tag}{attrs}>"


def internal_path(href: str) -> str | None:
    """Maps a link to a site path, or None when it points elsewhere."""
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    parts = urlsplit(href)
    if parts.scheme in ("http", "https"):
        if parts.hostname != PUBLIC_HOST:
            return None
    elif parts.scheme or href.startswith("//"):
        return None
    path = parts.path or "/"
    if not path.startswith("/"):
        return None
    if path.startswith("/static/"):
        return None
    return "/" + path.strip("/")


@dataclass
class ParsedPage:
    path: str
    status: int
    html: str
    tree: LexborHTMLParser = field(repr=False)

    @classmethod
    def parse(cls, path: str, status: int, html: str) -> "ParsedPage":
        return cls(path=path, status=status, html=html, tree=LexborHTMLParser(html))

    def title(self) -> str | None:
        node = self.tree.css_first("head > title")
        return squash(node.text()) if node is not None else None

    def meta_description(self) -> str | None:
        node = self.tree.css_first('meta[name="description"]')
        if node is None:
            return None
        return squash(node.attributes.get("content") or "")

    def meta_property(self, name: str) -> str | None:
        node = self.tree.css_first(f'meta[property="{name}"]') or self.tree.css_first(f'meta[name="{name}"]')
        return None if node is None else (node.attributes.get("content") or "")

    def visible_text(self) -> str:
        body = self.tree.body
        if body is None:
            return ""
        clone = LexborHTMLParser(body.html or "")
        for node in clone.css("script, style, noscript"):
            node.decompose()
        return squash(clone.body.text(separator=" ") if clone.body else "")

    def links(self) -> list[tuple[str, LexborNode]]:
        out = []
        for a in self.tree.css("a[href]"):
            target = internal_path(a.attributes.get("href") or "")
            if target is not None:
                out.append((target, a))
        return out

    def is_product(self) -> bool:
        return self.tree.css_first("article.product") is not None

    def json_ld_types(self) -> list[str]:
        import json

        types: list[str] = []
        for node in self.tree.css('script[type="application/ld+json"]'):
            try:
                data = json.loads(node.text())
            except ValueError:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("@type"), str):
                    types.append(item["@type"])
        return types

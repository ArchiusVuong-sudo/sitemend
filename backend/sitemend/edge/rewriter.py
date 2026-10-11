"""Applies a release's operations to origin HTML.

Two passes:
1. Direct edits (title, description, alt text, canonical, links, headings).
2. Derived tags, read from the result of pass 1: social tags take the final
   title and description, so they never go stale, and Product JSON-LD is
   built only from data visible on the page.

Edits are splices at exact offsets. An empty operation list returns the input
unchanged, and the same operations on the same input always give the same bytes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape

from selectolax.lexbor import LexborHTMLParser

from ..audit.html import PUBLIC_HOST, squash
from .locate import Element, Located, locate

DIRECT_OPS = {"set_title", "set_meta_description", "set_alt", "set_canonical", "relink", "unlink", "demote_h1"}
DERIVED_OPS = {"social", "product_jsonld"}
KNOWN_OPS = DIRECT_OPS | DERIVED_OPS


class RewriteError(ValueError):
    pass


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    text: str


def _attr_html(attrs: list[tuple[str, str | None]]) -> str:
    return "".join(f' {k}="{escape(v, quote=True)}"' if v is not None else f" {k}" for k, v in attrs)


def _rebuild_start(el: Element, attrs: list[tuple[str, str | None]], tag: str | None = None) -> str:
    return f"<{tag or el.tag}{_attr_html(attrs)}>"


def _with_attr(attrs: list[tuple[str, str | None]], name: str, value: str) -> list[tuple[str, str | None]]:
    if any(k == name for k, _ in attrs):
        return [(k, value if k == name else v) for k, v in attrs]
    return [*attrs, (name, value)]


def _splice(src: str, edits: list[Edit]) -> str:
    edits = sorted(edits, key=lambda e: (e.start, e.end))
    for a, b in zip(edits, edits[1:]):
        if b.start < a.end:
            raise RewriteError("two operations edit the same part of the page")
    out, pos = [], 0
    for e in edits:
        out.append(src[pos:e.start])
        out.append(e.text)
        pos = e.end
    out.append(src[pos:])
    return "".join(out)


def _head_insert(loc: Located, text: str) -> Edit:
    if loc.head_close is None:
        raise RewriteError("page has no </head>")
    return Edit(loc.head_close, loc.head_close, text)


def _direct_edits(src: str, loc: Located, op: dict) -> list[Edit]:
    kind = op["op"]
    if kind == "set_title":
        titles = loc.find("title")
        text = escape(op["text"], quote=False)
        if titles and titles[0].end_start is not None:
            t = titles[0]
            return [Edit(t.start_end, t.end_start, text)]
        return [_head_insert(loc, f"<title>{text}</title>\n")]
    if kind == "set_meta_description":
        metas = loc.find("meta", name="description")
        if metas:
            m = metas[0]
            return [Edit(m.start, m.start_end, _rebuild_start(m, _with_attr(m.attrs, "content", op["text"])))]
        return [_head_insert(loc, f'<meta name="description" content="{escape(op["text"], quote=True)}">\n')]
    if kind == "set_alt":
        return [Edit(i.start, i.start_end, _rebuild_start(i, _with_attr(i.attrs, "alt", op["text"])))
                for i in loc.find("img", src=op["src"])]
    if kind == "set_canonical":
        links = loc.find("link", rel="canonical")
        if links:
            ln = links[0]
            return [Edit(ln.start, ln.start_end, _rebuild_start(ln, _with_attr(ln.attrs, "href", op["href"])))]
        return [_head_insert(loc, f'<link rel="canonical" href="{escape(op["href"], quote=True)}">\n')]
    if kind == "relink":
        return [Edit(a.start, a.start_end, _rebuild_start(a, _with_attr(a.attrs, "href", op["to"])))
                for a in loc.find("a", href=op["href"])]
    if kind == "unlink":
        edits = []
        for a in loc.find("a", href=op["href"]):
            edits.append(Edit(a.start, a.start_end, ""))
            if a.end_start is not None and a.end_end is not None:
                edits.append(Edit(a.end_start, a.end_end, ""))
        return edits
    if kind == "demote_h1":
        edits = []
        for h in loc.find("h1")[1:]:
            edits.append(Edit(h.start, h.start_end, _rebuild_start(h, h.attrs, tag="h2")))
            if h.end_start is not None and h.end_end is not None:
                edits.append(Edit(h.end_start, h.end_end, "</h2>"))
        return edits
    raise RewriteError(f"unknown operation {kind}")


def page_facts(html: str) -> dict[str, str]:
    """Title, description and product facts as a visitor would see them."""
    tree = LexborHTMLParser(html)
    facts: dict[str, str] = {}
    if (t := tree.css_first("head > title")) is not None:
        facts["title"] = squash(t.text())
    if (m := tree.css_first('meta[name="description"]')) is not None:
        facts["description"] = squash(m.attributes.get("content") or "")
    if (h := tree.css_first("h1")) is not None:
        facts["h1"] = squash(h.text())
    product = tree.css_first("article.product")
    if product is not None:
        for name, sel in (("name", ".product-name"), ("price", ".price"), ("stock", ".stock"),
                          ("sku", ".sku"), ("summary", ".product-description p")):
            if (n := product.css_first(sel)) is not None:
                facts[f"product_{name}"] = squash(n.text())
        if (img := product.css_first("img")) is not None and img.attributes.get("src"):
            facts["product_image"] = img.attributes["src"] or ""
    return facts


_PRICE = re.compile(r"^\$\s*(\d+(?:\.\d{2})?)$")


def product_jsonld(html: str) -> dict | None:
    """Product structured data from visible page data only. None when the name or price is not on the page."""
    f = page_facts(html)
    name, price = f.get("product_name"), f.get("product_price", "")
    match = _PRICE.match(price)
    if not name or not match:
        return None
    data: dict = {"@context": "https://schema.org", "@type": "Product", "name": name}
    if f.get("product_summary"):
        data["description"] = f["product_summary"]
    if f.get("product_sku", "").startswith("SKU "):
        data["sku"] = f["product_sku"][4:]
    if f.get("product_image"):
        data["image"] = f"https://{PUBLIC_HOST}{f['product_image']}"
    offer: dict = {"@type": "Offer", "price": match.group(1), "priceCurrency": "USD"}
    stock = f.get("product_stock", "").lower()
    if stock == "in stock":
        offer["availability"] = "https://schema.org/InStock"
    elif stock == "out of stock":
        offer["availability"] = "https://schema.org/OutOfStock"
    data["offers"] = offer
    return data


SOCIAL_KEYS = (("property", "og:title"), ("property", "og:description"), ("property", "og:url"), ("name", "twitter:card"))


def social_values(html: str, path: str) -> dict[str, str]:
    f = page_facts(html)
    return {
        "og:title": f.get("title") or f.get("h1", ""),
        "og:description": f.get("description", ""),
        "og:url": f"https://{PUBLIC_HOST}{path}",
        "twitter:card": "summary_large_image",
    }


def _derived_edits(src: str, loc: Located, ops: list[dict], path: str, synced: bool) -> list[Edit]:
    kinds = {o["op"] for o in ops}
    edits: list[Edit] = []
    inserts: list[str] = []
    values = social_values(src, path)
    # Keep any existing social tags in step with a changed title or description.
    if "social" in kinds or synced:
        for attr, key in SOCIAL_KEYS:
            found = loc.find("meta", **{attr: key})
            if found:
                if key in ("og:title", "og:description"):
                    m = found[0]
                    edits.append(Edit(m.start, m.start_end, _rebuild_start(m, _with_attr(m.attrs, "content", values[key]))))
            elif "social" in kinds:
                inserts.append(f'<meta {attr}="{key}" content="{escape(values[key], quote=True)}">\n')
    if "product_jsonld" in kinds and (data := product_jsonld(src)) is not None:
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        inserts.append(f'<script type="application/ld+json">{payload}</script>\n')
    if inserts:
        edits.append(_head_insert(loc, "".join(inserts)))
    return edits


def rewrite(html: str, ops: list[dict], path: str) -> str:
    if not ops:
        return html
    for op in ops:
        if op.get("op") not in KNOWN_OPS:
            raise RewriteError(f"unknown operation {op.get('op')}")
    direct = [o for o in ops if o["op"] in DIRECT_OPS]
    derived = [o for o in ops if o["op"] in DERIVED_OPS]
    out = html
    if direct:
        loc = locate(out)
        edits: list[Edit] = []
        for op in direct:
            edits.extend(_direct_edits(out, loc, op))
        out = _splice(out, edits)
    synced = any(o["op"] in ("set_title", "set_meta_description") for o in direct)
    if derived or synced:
        loc = locate(out)
        out = _splice(out, _derived_edits(out, loc, derived, path, synced))
    return out


def rewrite_bytes(body: bytes, ops: list[dict], path: str) -> bytes:
    if not ops:
        return body
    return rewrite(body.decode("utf-8"), ops, path).encode("utf-8")

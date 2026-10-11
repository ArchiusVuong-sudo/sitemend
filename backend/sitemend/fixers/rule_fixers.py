"""Deterministic fixers for technical and rich-result issues.

Each returns a FixDraft: the operation the edge will apply, a before/after a
reviewer can read, and a confidence. A low-confidence draft always waits for
approval, even when its category runs on autopilot.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field

from ..audit.html import PUBLIC_HOST, ParsedPage, internal_path, start_tag
from ..audit.rules import Finding, LinkStatus
from ..edge.rewriter import product_jsonld, social_values

MATCH_THRESHOLD = 0.9


@dataclass
class FixDraft:
    path: str
    category: str
    kind: str
    op: dict
    before: str
    after: str
    rules: list[str] = field(default_factory=list)
    target: str = ""
    confidence: str = "high"
    note: str = ""


def fix_canonical(f: Finding, page: ParsedPage) -> FixDraft:
    href = f"https://{PUBLIC_HOST}{f.path}"
    return FixDraft(f.path, "technical", "set_canonical", {"op": "set_canonical", "href": href},
                    before="(no canonical link)", after=f'<link rel="canonical" href="{href}">',
                    rules=[f.rule], note="Points the page at its own public URL")


def best_match(target: str, known: list[str]) -> tuple[str | None, float]:
    best, best_ratio = None, 0.0
    for path in known:
        ratio = difflib.SequenceMatcher(None, target, path).ratio()
        if ratio > best_ratio:
            best, best_ratio = path, ratio
    return best, best_ratio


def fix_broken_link(f: Finding, page: ParsedPage, known_paths: list[str]) -> FixDraft:
    match, ratio = best_match(f.key, known_paths)
    if match and ratio >= MATCH_THRESHOLD:
        return FixDraft(f.path, "technical", "relink", {"op": "relink", "href": f.key, "to": match},
                        before=f'<a href="{f.key}"> (returns 404)', after=f'<a href="{match}">',
                        rules=[f.rule], target=f.key,
                        note=f"Closest live page, {ratio:.0%} similar path")
    note = (f"No live page is close to {f.key} (best {match}, {ratio:.0%} similar), "
            "so the link is removed and its text kept")
    return FixDraft(f.path, "technical", "unlink", {"op": "unlink", "href": f.key},
                    before=f'<a href="{f.key}"> (returns 404)', after="Link removed, text kept",
                    rules=[f.rule], target=f.key, confidence="low", note=note)


def fix_redirect_link(f: Finding, link: LinkStatus) -> FixDraft:
    final = link.final or "/"
    hops = " -> ".join([f.key, *link.chain])
    return FixDraft(f.path, "technical", "relink", {"op": "relink", "href": f.key, "to": final},
                    before=f'<a href="{f.key}"> ({hops})', after=f'<a href="{final}">',
                    rules=[f.rule], target=f.key, note=f"Skips {len(link.chain)} redirects")


def fix_headings(f: Finding, page: ParsedPage) -> FixDraft:
    extra = page.tree.css("h1")[1:]
    before = "\n".join(f"{start_tag(h)}{h.text(strip=True)}</h1>" for h in extra)
    after = "\n".join(f"<h2{start_tag(h)[3:]}{h.text(strip=True)}</h2>" for h in extra)
    return FixDraft(f.path, "technical", "demote_h1", {"op": "demote_h1"}, before=before, after=after,
                    rules=[f.rule], note="Keeps the first H1, turns the others into H2")


def fix_social(f: Finding, page: ParsedPage) -> FixDraft:
    values = social_values(page.html, page.path)
    after = "\n".join(f'<meta {"name" if k.startswith("twitter") else "property"}="{k}" content="{v}">'
                      for k, v in values.items())
    return FixDraft(f.path, "rich", "social", {"op": "social"}, before="(no social tags)", after=after,
                    rules=[f.rule], note="Filled from the final title and description each time the page is served")


def fix_product_schema(f: Finding, page: ParsedPage) -> FixDraft:
    data = product_jsonld(page.html)
    if data is None:
        return FixDraft(f.path, "rich", "product_jsonld", {"op": "product_jsonld"},
                        before="(no Product data)", after="(name or price not found on the page)",
                        rules=[f.rule], confidence="low",
                        note="The page does not show a name and price, so nothing would be added")
    return FixDraft(f.path, "rich", "product_jsonld", {"op": "product_jsonld"}, before="(no Product data)",
                    after=json.dumps(data, indent=2, ensure_ascii=False), rules=[f.rule],
                    note="Built only from the name, price, stock, SKU, text and image shown on the page")


def draft_rule_fixes(findings: list[Finding], pages: dict[str, ParsedPage],
                     links: dict[str, LinkStatus]) -> list[FixDraft]:
    known = sorted(pages)
    drafts: list[FixDraft] = []
    for f in findings:
        page = pages[f.path]
        if f.rule == "canonical_missing":
            drafts.append(fix_canonical(f, page))
        elif f.rule == "link_broken":
            drafts.append(fix_broken_link(f, page, known))
        elif f.rule == "link_redirect":
            drafts.append(fix_redirect_link(f, links[internal_path(f.key) or f.key]))
        elif f.rule == "h1_multiple":
            drafts.append(fix_headings(f, page))
        elif f.rule == "social_missing":
            drafts.append(fix_social(f, page))
        elif f.rule == "product_schema_missing":
            drafts.append(fix_product_schema(f, page))
    return drafts

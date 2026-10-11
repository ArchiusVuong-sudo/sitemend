"""Audit rules. Each rule reads one page (plus site-wide context) and returns findings.

Nine rules cover five categories. Duplicate titles and descriptions need the
whole site, so every rule gets a SiteContext built from the full crawl.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from .html import ParsedPage, outer, start_tag

TITLE_MAX = 60
META_MIN = 70
SOCIAL_TAGS = ("og:title", "og:description", "og:url", "twitter:card")


@dataclass(frozen=True)
class LinkStatus:
    status: int
    chain: tuple[str, ...] = ()  # paths visited after the link, for redirects
    final: str | None = None


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    category: str
    severity: str
    message: str
    evidence: str
    key: str = ""

    @property
    def fingerprint(self) -> str:
        return f"{self.path}|{self.rule}|{self.key}"


@dataclass
class SiteContext:
    pages: list[ParsedPage]
    links: dict[str, LinkStatus] = field(default_factory=dict)
    titles: dict[str, list[str]] = field(default_factory=dict)  # normalized title -> paths
    metas: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def build(cls, pages: list[ParsedPage], links: dict[str, LinkStatus]) -> "SiteContext":
        titles: dict[str, list[str]] = defaultdict(list)
        metas: dict[str, list[str]] = defaultdict(list)
        for p in pages:
            if (t := p.title()):
                titles[t.lower()].append(p.path)
            if (m := p.meta_description()):
                metas[m.lower()].append(p.path)
        return cls(pages=pages, links=links, titles=dict(titles), metas=dict(metas))


def _head_evidence(page: ParsedPage, note: str) -> str:
    head = page.tree.head
    tags = [start_tag(n) for n in head.iter() if n.tag in ("title", "meta", "link")] if head else []
    shown = "\n".join(tags[:8])
    return f"<!-- {note} -->\n<head>\n{shown}\n</head>"


def rule_title(page: ParsedPage, site: SiteContext) -> list[Finding]:
    title = page.title()
    node = page.tree.css_first("head > title")
    if not title:
        return [Finding(page.path, "title_missing", "titles", "high", "Page has no title",
                        _head_evidence(page, "no <title> in <head>"))]
    out = []
    others = [p for p in site.titles.get(title.lower(), []) if p != page.path]
    if others:
        out.append(Finding(page.path, "title_duplicate", "titles", "medium",
                           f"Same title as {', '.join(others)}", outer(node)))
    if len(title) > TITLE_MAX:
        out.append(Finding(page.path, "title_too_long", "titles", "low",
                           f"Title is {len(title)} characters (limit {TITLE_MAX}), so results cut it off",
                           outer(node)))
    return out


def rule_meta_description(page: ParsedPage, site: SiteContext) -> list[Finding]:
    desc = page.meta_description()
    node = page.tree.css_first('meta[name="description"]')
    if not desc:
        return [Finding(page.path, "meta_missing", "meta", "medium", "Page has no meta description",
                        _head_evidence(page, 'no <meta name="description">'))]
    out = []
    others = [p for p in site.metas.get(desc.lower(), []) if p != page.path]
    if others:
        out.append(Finding(page.path, "meta_duplicate", "meta", "medium",
                           f"Same meta description as {', '.join(others)}", start_tag(node)))
    if len(desc) < META_MIN:
        out.append(Finding(page.path, "meta_short", "meta", "low",
                           f"Meta description is {len(desc)} characters (aim for {META_MIN} or more)",
                           start_tag(node)))
    return out


def rule_image_alt(page: ParsedPage, site: SiteContext) -> list[Finding]:
    out = []
    for img in page.tree.css("img"):
        if "alt" in img.attributes:
            continue
        src = img.attributes.get("src") or ""
        out.append(Finding(page.path, "img_alt_missing", "alt", "medium", f"Image {src} has no alt text",
                           start_tag(img), key=src))
    return out


def rule_canonical(page: ParsedPage, site: SiteContext) -> list[Finding]:
    if page.tree.css_first('link[rel="canonical"]') is None:
        return [Finding(page.path, "canonical_missing", "technical", "medium", "Page has no canonical link",
                        _head_evidence(page, 'no <link rel="canonical">'))]
    return []


def rule_broken_links(page: ParsedPage, site: SiteContext) -> list[Finding]:
    out, seen = [], set()
    for target, a in page.links():
        status = site.links.get(target)
        if status is None or status.status < 400 or target in seen:
            continue
        seen.add(target)
        href = a.attributes.get("href") or target
        out.append(Finding(page.path, "link_broken", "technical", "high",
                           f"Link to {target} returns {status.status}", outer(a), key=href))
    return out


def rule_redirect_links(page: ParsedPage, site: SiteContext) -> list[Finding]:
    out, seen = [], set()
    for target, a in page.links():
        status = site.links.get(target)
        if status is None or status.status not in (301, 302, 307, 308) or target in seen:
            continue
        seen.add(target)
        hops = len(status.chain)
        href = a.attributes.get("href") or target
        out.append(Finding(page.path, "link_redirect", "technical", "low",
                           f"Link to {target} goes through {hops} redirect{'s' if hops != 1 else ''} to {status.final}",
                           outer(a), key=href))
    return out


def rule_headings(page: ParsedPage, site: SiteContext) -> list[Finding]:
    h1s = page.tree.css("h1")
    if len(h1s) > 1:
        evidence = "\n".join(outer(h, 160) for h in h1s)
        return [Finding(page.path, "h1_multiple", "technical", "low", f"Page has {len(h1s)} H1 headings",
                        evidence)]
    return []


def rule_social_tags(page: ParsedPage, site: SiteContext) -> list[Finding]:
    missing = [t for t in SOCIAL_TAGS if page.meta_property(t) is None]
    if missing:
        return [Finding(page.path, "social_missing", "rich", "low", f"Missing social tags: {', '.join(missing)}",
                        _head_evidence(page, "no " + ", ".join(missing)))]
    return []


def rule_product_schema(page: ParsedPage, site: SiteContext) -> list[Finding]:
    if not page.is_product() or "Product" in page.json_ld_types():
        return []
    article = page.tree.css_first("article.product")
    return [Finding(page.path, "product_schema_missing", "rich", "medium",
                    "Product page has no Product structured data", outer(article, 300))]


Rule = Callable[[ParsedPage, SiteContext], list[Finding]]

RULES: dict[str, Rule] = {
    "title": rule_title,
    "meta_description": rule_meta_description,
    "image_alt": rule_image_alt,
    "canonical": rule_canonical,
    "broken_links": rule_broken_links,
    "redirect_links": rule_redirect_links,
    "headings": rule_headings,
    "social_tags": rule_social_tags,
    "product_schema": rule_product_schema,
}

# Which category each issue code belongs to and its check slot for grading.
ISSUE_SLOTS: dict[str, str] = {
    "title_missing": "title", "title_duplicate": "title", "title_too_long": "title",
    "meta_missing": "meta", "meta_duplicate": "meta", "meta_short": "meta",
    "img_alt_missing": "alt",
    "canonical_missing": "canonical",
    "link_broken": "links", "link_redirect": "links",
    "h1_multiple": "headings",
    "social_missing": "social",
    "product_schema_missing": "product_schema",
}


def audit(site: SiteContext) -> list[Finding]:
    findings: list[Finding] = []
    for page in site.pages:
        if page.status != 200:
            continue
        for rule in RULES.values():
            findings.extend(rule(page, site))
    return findings

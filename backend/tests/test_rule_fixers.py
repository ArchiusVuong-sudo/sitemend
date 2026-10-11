from __future__ import annotations

from shop.origin import fetch_origin
from sitemend.audit.html import ParsedPage
from sitemend.audit.rules import Finding, LinkStatus
from sitemend.fixers.rule_fixers import best_match, draft_rule_fixes
from sitemend.fixers.service import dry_run_check

PATHS = ["/", "/about", "/products/speckled-stoneware-mug", "/journal/repotting-a-fern",
         "/journal/caring-for-glazed-ceramics", "/collections/mugs", "/products/terracotta-herb-pot"]


def pages() -> dict[str, ParsedPage]:
    return {p: ParsedPage.parse(p, 200, fetch_origin(p).body.decode()) for p in PATHS}


LINKS = {
    "/shop/mugs": LinkStatus(301, ("/mugs", "/collections/mugs"), "/collections/mugs"),
    "/products/speckled-stoneware-mugs": LinkStatus(404),
    "/journal/winter-glaze-workshop": LinkStatus(404),
}


def finding(path, rule, category, key=""):
    return Finding(path, rule, category, "high", "m", "e", key)


def test_close_broken_link_is_relinked_with_high_confidence():
    [d] = draft_rule_fixes([finding("/", "link_broken", "technical", "/products/speckled-stoneware-mugs")], pages(), LINKS)
    assert d.kind == "relink" and d.op["to"] == "/products/speckled-stoneware-mug" and d.confidence == "high"


def test_far_broken_link_is_removed_with_low_confidence():
    f = finding("/journal/caring-for-glazed-ceramics", "link_broken", "technical", "/journal/winter-glaze-workshop")
    [d] = draft_rule_fixes([f], pages(), LINKS)
    assert d.kind == "unlink" and d.confidence == "low" and "No live page is close" in d.note


def test_redirecting_link_points_at_the_final_page():
    [d] = draft_rule_fixes([finding("/about", "link_redirect", "technical", "/shop/mugs")], pages(), LINKS)
    assert d.op == {"op": "relink", "href": "/shop/mugs", "to": "/collections/mugs"}
    assert "/shop/mugs -> /mugs -> /collections/mugs" in d.before


def test_every_rule_fix_passes_its_dry_run():
    found = [
        finding("/", "link_broken", "technical", "/products/speckled-stoneware-mugs"),
        finding("/about", "link_redirect", "technical", "/shop/mugs"),
        finding("/collections/mugs", "h1_multiple", "technical"),
        finding("/products/terracotta-herb-pot", "canonical_missing", "technical"),
        finding("/about", "social_missing", "rich"),
        finding("/products/speckled-stoneware-mug", "product_schema_missing", "rich"),
        finding("/journal/caring-for-glazed-ceramics", "link_broken", "technical", "/journal/winter-glaze-workshop"),
    ]
    ps = pages()
    links = {**LINKS, **{p: LinkStatus(200, (), p) for p in ps}}
    for d in draft_rule_fixes(found, ps, links):
        checks = dry_run_check(d, ps[d.path], links)
        assert all(c["passed"] for c in checks), (d.kind, checks)


def test_dry_run_flags_a_fix_that_changes_nothing():
    ps = pages()
    [d] = draft_rule_fixes([finding("/", "link_broken", "technical", "/products/speckled-stoneware-mugs")], ps, LINKS)
    d.op = {"op": "relink", "href": "/not-on-the-page", "to": "/"}
    checks = {c["name"]: c["passed"] for c in dry_run_check(d, ps["/"], LINKS)}
    assert checks == {"dry_run": False, "rule_clears": False}


def test_best_match():
    assert best_match("/products/mugz", ["/products/mug", "/about"])[0] == "/products/mug"

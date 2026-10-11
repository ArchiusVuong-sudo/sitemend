"""Each audit rule on small pages, and the full scan against the planted manifest."""

from __future__ import annotations

import pytest

from shop.origin import fetch_origin, planted_issues
from sitemend.audit.crawl import Fetched, crawl
from sitemend.audit.html import ParsedPage, internal_path
from sitemend.audit.rules import RULES, LinkStatus, SiteContext, audit

HEAD_OK = (
    '<title>A Good Enough Title For Tests | Shop</title>'
    '<meta name="description" content="' + "d" * 90 + '">'
    '<link rel="canonical" href="https://mossgrove-clayworks.example/x">'
    '<meta property="og:title" content="t"><meta property="og:description" content="d">'
    '<meta property="og:url" content="u"><meta name="twitter:card" content="summary">'
)


def page(head: str = HEAD_OK, body: str = "<h1>Hi</h1>", path: str = "/x") -> ParsedPage:
    return ParsedPage.parse(path, 200, f"<!DOCTYPE html><html><head>{head}</head><body>{body}</body></html>")


def run(rule: str, p: ParsedPage, others: list[ParsedPage] = (), links: dict | None = None):
    ctx = SiteContext.build([p, *others], links or {})
    return RULES[rule](p, ctx)


def test_clean_page_has_no_findings():
    p = page()
    assert audit(SiteContext.build([p], {})) == []


def test_title_missing_too_long_and_duplicate():
    assert [f.rule for f in run("title", page(head=""))] == ["title_missing"]
    long = page(head=f"<title>{'x' * 61}</title>")
    assert [f.rule for f in run("title", long)] == ["title_too_long"]
    a, b = page(path="/a"), page(path="/b")
    found = run("title", a, [b])
    assert [f.rule for f in found] == ["title_duplicate"] and "/b" in found[0].message


def test_meta_missing_short_and_duplicate():
    assert [f.rule for f in run("meta_description", page(head="<title>t</title>"))] == ["meta_missing"]
    short = page(head='<meta name="description" content="Too short.">')
    assert [f.rule for f in run("meta_description", short)] == ["meta_short"]
    a, b = page(path="/a"), page(path="/b")
    assert [f.rule for f in run("meta_description", a, [b])] == ["meta_duplicate"]


def test_image_alt_missing_but_empty_alt_is_allowed():
    p = page(body='<img src="/a.jpg"><img src="/b.jpg" alt=""><img src="/c.jpg" alt="A mug">')
    found = run("image_alt", p)
    assert [(f.rule, f.key) for f in found] == [("img_alt_missing", "/a.jpg")]
    assert found[0].evidence == '<img src="/a.jpg">'


def test_canonical_missing():
    assert [f.rule for f in run("canonical", page(head="<title>t</title>"))] == ["canonical_missing"]


def test_broken_and_redirect_links_use_crawl_status():
    p = page(body='<a href="/gone">x</a><a href="/old">y</a><a href="/ok">z</a><a href="https://elsewhere.example/">e</a>')
    links = {
        "/gone": LinkStatus(404),
        "/old": LinkStatus(301, ("/older", "/new"), "/new"),
        "/ok": LinkStatus(200, (), "/ok"),
    }
    broken = run("broken_links", p, links=links)
    redirect = run("redirect_links", p, links=links)
    assert [(f.rule, f.key) for f in broken] == [("link_broken", "/gone")]
    assert [(f.rule, f.key) for f in redirect] == [("link_redirect", "/old")]
    assert "2 redirects to /new" in redirect[0].message


def test_headings_and_social_tags():
    assert [f.rule for f in run("headings", page(body="<h1>a</h1><h1>b</h1>"))] == ["h1_multiple"]
    found = run("social_tags", page(head="<title>t</title>"))
    assert found[0].rule == "social_missing" and "og:title" in found[0].message


def test_product_schema_only_on_product_pages():
    product = '<article class="product"><h1 class="product-name">Mug</h1><p class="price">$5.00</p></article>'
    assert [f.rule for f in run("product_schema", page(body=product))] == ["product_schema_missing"]
    with_ld = page(head=HEAD_OK + '<script type="application/ld+json">{"@type": "Product"}</script>', body=product)
    assert run("product_schema", with_ld) == []
    assert run("product_schema", page()) == []


@pytest.mark.parametrize("href,expected", [
    ("/products/a", "/products/a"),
    ("/products/a/?x=1#top", "/products/a"),
    ("https://mossgrove-clayworks.example/about", "/about"),
    ("https://elsewhere.example/about", None),
    ("mailto:hi@x.example", None),
    ("#top", None),
    ("/static/img/a.jpg", None),
    ("//cdn.example/x", None),
])
def test_internal_path(href, expected):
    assert internal_path(href) == expected


def origin_fetch(path: str) -> Fetched:
    r = fetch_origin(path)
    return Fetched(path, r.status, r.body.decode(), r.location)


def test_crawl_records_redirect_chain_and_missing_pages():
    result = crawl(origin_fetch)
    assert len(result.pages) == 12
    assert result.links["/shop/mugs"] == LinkStatus(301, ("/mugs", "/collections/mugs"), "/collections/mugs")
    assert result.links["/products/speckled-stoneware-mugs"].status == 404
    assert result.links["/journal/winter-glaze-workshop"].status == 404
    # Every URL is fetched once: 12 pages, 2 redirect hops, 2 missing pages.
    assert result.fetches == 16


def test_scan_matches_planted_manifest_exactly():
    result = crawl(origin_fetch)
    found = sorted((f.path, f.rule, f.key) for f in audit(SiteContext.build(result.pages, result.links)))
    expected = sorted((i["path"], i["rule"], i["key"]) for i in planted_issues())
    assert found == expected
    categories = {f.category for f in audit(SiteContext.build(result.pages, result.links))}
    assert categories == {"technical", "titles", "meta", "alt", "rich"}

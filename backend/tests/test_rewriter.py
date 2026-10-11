"""The edge rewriter: only targeted bytes change, and the same operations always give the same bytes."""

from __future__ import annotations

import json

import pytest

from shop.origin import all_page_paths, fetch_origin
from sitemend.audit.html import ParsedPage
from sitemend.edge.rewriter import RewriteError, product_jsonld, rewrite, rewrite_bytes

MUG = "/products/speckled-stoneware-mug"


def origin(path: str) -> str:
    return fetch_origin(path).body.decode()


def changed_lines(a: str, b: str) -> list[tuple[str, str]]:
    import difflib

    out = []
    for line in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            out.append((line[0], line[1:]))
    return out


@pytest.mark.parametrize("path", all_page_paths())
def test_empty_release_returns_origin_unchanged(path):
    body = fetch_origin(path).body
    assert rewrite_bytes(body, [], path) is body


def test_set_title_changes_only_the_title_and_synced_social_tags():
    html = origin(MUG)
    out = rewrite(html, [{"op": "set_title", "text": "Speckled Stoneware Mug & Saucer | Shop"}], MUG)
    diff = changed_lines(html, out)
    assert ("+", "<title>Speckled Stoneware Mug &amp; Saucer | Shop</title>") in diff
    assert ("+", '<meta property="og:title" content="Speckled Stoneware Mug &amp; Saucer | Shop">') in diff
    assert len(diff) == 4  # two lines out, two lines in


def test_missing_title_and_description_are_inserted_in_head():
    html = origin("/about")
    out = rewrite(html, [{"op": "set_title", "text": "About | Shop"}], "/about")
    page = ParsedPage.parse("/about", 200, out)
    assert page.title() == "About | Shop"
    fern = "/journal/repotting-a-fern"
    out = rewrite(origin(fern), [{"op": "set_meta_description", "text": 'Ferns "like" snug pots'}], fern)
    assert ParsedPage.parse(fern, 200, out).meta_description() == 'Ferns "like" snug pots'


def test_alt_text_is_added_to_the_right_image_only():
    path = "/collections/planters"
    html = origin(path)
    out = rewrite(html, [{"op": "set_alt", "src": "/static/img/herb-pots.jpg", "text": "Herb pots on a sill"}], path)
    diff = changed_lines(html, out)
    assert diff == [
        ("-", '<img src="/static/img/herb-pots.jpg" width="800" height="600">'),
        ("+", '<img src="/static/img/herb-pots.jpg" width="800" height="600" alt="Herb pots on a sill">'),
    ]


def test_relink_unlink_and_demote():
    html = origin("/")
    out = rewrite(html, [{"op": "relink", "href": "/products/speckled-stoneware-mugs", "to": MUG}], "/")
    assert f'<a href="{MUG}">Speckled stoneware mug</a>' in out
    out = rewrite(html, [{"op": "unlink", "href": "/products/speckled-stoneware-mugs"}], "/")
    assert "<li>Speckled stoneware mug</li>" in out
    mugs = origin("/collections/mugs")
    out = rewrite(mugs, [{"op": "demote_h1"}], "/collections/mugs")
    assert out.count("<h1") == 1 and "<h2>Shop all mugs</h2>" in out


def test_canonical_inserted():
    path = "/collections/tableware"
    href = "https://mossgrove-clayworks.example/collections/tableware"
    out = rewrite(origin(path), [{"op": "set_canonical", "href": href}], path)
    assert f'<link rel="canonical" href="{href}">\n</head>' in out


def test_social_tags_follow_the_final_title_and_description():
    out = rewrite(origin("/about"), [{"op": "set_title", "text": "About the Studio | Shop"}, {"op": "social"}], "/about")
    page = ParsedPage.parse("/about", 200, out)
    assert page.meta_property("og:title") == "About the Studio | Shop"
    assert page.meta_property("og:url") == "https://mossgrove-clayworks.example/about"
    assert page.meta_property("twitter:card") == "summary_large_image"
    # Without the title fix the same social op derives from the H1, so it is never stale.
    plain = ParsedPage.parse("/about", 200, rewrite(origin("/about"), [{"op": "social"}], "/about"))
    assert plain.meta_property("og:title") == "About the studio"


def test_product_jsonld_uses_only_visible_data():
    html = origin(MUG)
    data = product_jsonld(html)
    assert data == {
        "@context": "https://schema.org", "@type": "Product", "name": "Speckled stoneware mug",
        "description": data["description"], "sku": "MG-MUG-01",
        "image": "https://mossgrove-clayworks.example/static/img/speckled-mug.jpg",
        "offers": {"@type": "Offer", "price": "34.00", "priceCurrency": "USD",
                   "availability": "https://schema.org/InStock"},
    }
    assert data["description"] in ParsedPage.parse(MUG, 200, html).visible_text()
    out = rewrite(html, [{"op": "product_jsonld"}], MUG)
    assert ParsedPage.parse(MUG, 200, out).json_ld_types() == ["Product"]
    assert product_jsonld("<html><head></head><body><article class='product'></article></body></html>") is None


def test_same_ops_give_the_same_bytes():
    ops = [{"op": "set_title", "text": "A | B"}, {"op": "product_jsonld"}, {"op": "social"},
           {"op": "set_alt", "src": "/static/img/speckled-mug.jpg", "text": "Mug"}]
    assert rewrite(origin(MUG), ops, MUG) == rewrite(origin(MUG), list(reversed(ops)), MUG)


def test_bad_operations_are_refused():
    with pytest.raises(RewriteError):
        rewrite(origin(MUG), [{"op": "drop_table"}], MUG)
    with pytest.raises(RewriteError):
        rewrite(origin(MUG), [{"op": "set_title", "text": "a"}, {"op": "set_title", "text": "b"}], MUG)


def test_jsonld_payload_cannot_close_the_script_tag():
    html = origin(MUG).replace("Speckled stoneware mug</h1>", "Mug </script><b>x</h1>")
    out = rewrite(html, [{"op": "product_jsonld"}], MUG)
    payload = out.split('<script type="application/ld+json">')[1].split("</script>")[0]
    assert json.loads(payload)["name"].startswith("Mug")

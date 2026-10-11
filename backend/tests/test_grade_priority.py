"""Pins the grade and priority formulas."""

from __future__ import annotations

import math

import pytest

from sitemend.audit.grade import PageInfo, grade
from sitemend.audit.priority import Stat, band_medians, band_of, score
from sitemend.audit.rules import Finding


def f(path: str, rule: str, category: str, severity: str, key: str = "") -> Finding:
    return Finding(path, rule, category, severity, "m", "e", key)


def test_clean_site_grades_100():
    g = grade([PageInfo("/a", False), PageInfo("/b", True)], [])
    assert (g.site, g.technical, g.onpage, g.rich, g.clean_pages) == (100, 100, 100, 100, 2)


def test_grade_counts_worst_severity_per_slot():
    pages = [PageInfo("/a", False), PageInfo("/b", False)]
    findings = [
        f("/a", "title_duplicate", "titles", "medium"),
        f("/a", "title_too_long", "titles", "low"),  # same slot: worst (medium = 2) counts once
        f("/b", "link_broken", "technical", "high"),
    ]
    g = grade(pages, findings)
    # On-page: 2 pages x 3 slots x 3 = 18, cost 2 -> 89. Technical: 18, cost 3 -> 83. Rich: 2 x 1 slot x 3 = 6 -> 100.
    assert (g.onpage, g.technical, g.rich) == (89, 83, 100)
    assert g.site == round(0.4 * 83 + 0.4 * 89 + 0.2 * 100)
    assert g.clean_pages == 0 and g.issues == 3


def test_product_schema_slot_only_counts_on_product_pages():
    g = grade([PageInfo("/p", True)], [f("/p", "product_schema_missing", "rich", "medium")])
    assert g.rich == round(100 * (1 - 2 / 6))


@pytest.mark.parametrize("position,band", [(1, "1-3"), (3.4, "1-3"), (3.6, "4-10"), (10.4, "4-10"), (11.3, "11-20"), (40, "21+")])
def test_bands(position, band):
    assert band_of(position) == band


def stats() -> list[Stat]:
    return [
        Stat("/mug", 18400, 92, 0.005, 5.8, "speckled stoneware mug"),
        Stat("/a", 5000, 100, 0.02, 6.0, "a"),
        Stat("/b", 4000, 120, 0.03, 7.0, "b"),
        Stat("/home", 9600, 384, 0.04, 3.1, "home"),
    ]


def test_band_median_falls_back_to_site_median_for_thin_bands():
    medians = band_medians(stats())
    assert medians["4-10"] == pytest.approx(0.02)
    assert medians["1-3"] == pytest.approx(0.025)  # only one page there: site median


def test_priority_formula_is_pinned():
    medians = band_medians(stats())
    p = score(stats()[0], "medium", medians)
    gap = (0.02 - 0.005) / 0.02
    assert p.score == round(math.log10(18401) * (1 + 2 * gap) * 2, 2) == 21.32
    assert p.reason == '18,400 impressions, CTR 0.5% vs 2.0% median at position 4-10, top query "speckled stoneware mug"'


def test_priority_above_median_has_no_gap_bonus():
    medians = band_medians(stats())
    p = score(stats()[2], "low", medians)
    assert p.score == round(math.log10(4001), 2)
    assert "at or above" in p.reason


def test_priority_without_search_data_uses_severity():
    assert score(None, "high", {}).score == 3.0

"""Every check on titles, descriptions and alt text."""

from __future__ import annotations

import pytest

from sitemend.fixers.checks import CheckContext, normalize, reasons, run_checks

PAGE = ("Speckled stoneware mug. A wide, sturdy mug that holds 350 ml. Price $34.00. Made by hand in small batches. "
        "Dishwasher safe.")


def ctx(field="title", **kw) -> CheckContext:
    base = dict(field=field, page_text=PAGE, target_query="speckled stoneware mug", never_use=("cheap",), taken={})
    base.update(kw)
    return CheckContext(**base)


def by_name(text: str, c: CheckContext) -> dict[str, bool]:
    return {r.name: r.passed for r in run_checks(text, c)}


def test_good_title_passes_everything():
    assert all(by_name("Speckled Stoneware Mug, Made by Hand | Shop", ctx()).values())


@pytest.mark.parametrize("text", ["Short mug title", "x" * 61 + " speckled stoneware mug"])
def test_title_length(text):
    assert by_name(text, ctx())["length"] is False


def test_target_query_words_with_plurals():
    assert by_name("Speckled Stoneware Mugs, Made by Hand | Shop", ctx())["query"] is True
    result = run_checks("A Wide Stoneware Cup Made by Hand | Shop", ctx())
    assert not result[1].passed and "speckled" in result[1].detail and "mug" in result[1].detail


def test_unique_against_taken_texts():
    c = ctx(taken={normalize("Speckled Stoneware Mug, Made by Hand | Shop"): "/other"})
    detail = [r for r in run_checks("Speckled  stoneware mug, made by hand | Shop", c) if r.name == "unique"][0]
    assert not detail.passed and "/other" in detail.detail


def test_numbers_and_claims_must_be_on_the_page():
    assert by_name("Speckled Stoneware Mug, 350 ml, $34.00 | Shop", ctx())["facts"] is True
    assert by_name("Speckled Stoneware Mug, 12 oz | Shop", ctx())["facts"] is False
    assert by_name("Best Speckled Stoneware Mug | Shop", ctx())["facts"] is False
    assert by_name("Dishwasher Safe Speckled Stoneware Mug | Shop", ctx())["facts"] is True  # on the page
    assert "best" in " ".join(reasons(run_checks("Best Speckled Stoneware Mug | Shop", ctx())))


def test_never_use_words_whole_words_only():
    assert by_name("Cheap Speckled Stoneware Mug by Hand | Shop", ctx())["never_use"] is False
    assert by_name("Speckled Stoneware Mug, Cheapside Studio | Shop", ctx())["never_use"] is True


@pytest.mark.parametrize("phrase", ["Elevate your mornings", "Unlock", "look no further", "Whether you're"])
def test_style_flags_filler_phrases(phrase):
    assert by_name(f"{phrase} speckled stoneware mug | Shop", ctx())["style"] is False


def test_exclamation_marks_fail_style():
    assert by_name("Speckled Stoneware Mug by Hand! | Shop", ctx())["style"] is False


def test_meta_description_limits():
    good = ("A wide speckled stoneware mug made by hand in small batches. It holds 350 ml and keeps coffee "
            "warm for a while longer.")
    assert all(by_name(good, ctx("meta_description")).values())
    assert by_name("Speckled stoneware mug.", ctx("meta_description"))["length"] is False


def test_alt_text_skips_query_and_uniqueness_but_flags_filler():
    c = ctx("alt", taken={"wide speckled mug": "/x"})
    checks = by_name("Wide speckled mug", c)
    assert checks["query"] and checks["unique"] and checks["length"]
    assert by_name("Image of a speckled mug", c)["style"] is False

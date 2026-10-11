"""Fix lifecycle: attempts, uniqueness claims under parallel writes, review actions and the autopilot policy."""

from __future__ import annotations

import threading

import pytest
from django.db import close_old_connections

from sitemend.fixers import service
from sitemend.models import Fix, FixAttempt, Policy, Run, TextClaim

from .helpers import run_job

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def scanned(site):
    run_job(site, Run.Kind.SCAN)
    return site


def model_fix(site, path: str, kind: str = "set_title") -> Fix:
    category = {"set_title": "titles", "set_meta_description": "meta", "set_alt": "alt"}[kind]
    return Fix.objects.create(site=site, path=path, category=category, kind=kind, source=Fix.Source.MODEL,
                              status=Fix.Status.WRITING, op={"op": kind, "text": ""}, rules=["title_duplicate"])


GOOD_TITLE = "Speckled Stoneware Mug, Made by Hand | Mossgrove Clayworks"


def test_model_gets_three_tries_then_review(scanned):
    fix = model_fix(scanned, "/products/speckled-stoneware-mug")
    for _ in range(3):
        reply = service.submit_text(fix.pk, "Best mug", FixAttempt.Source.MODEL)
        assert not reply["accepted"]
    fix.refresh_from_db()
    assert fix.status == Fix.Status.NEEDS_REVIEW and fix.attempts.count() == 3
    reply = service.submit_text(fix.pk, GOOD_TITLE, FixAttempt.Source.MODEL)
    assert reply["tries_left"] == 0 and "No tries left" in reply["reasons"][0]
    # A person can still fix it.
    reply = service.submit_text(fix.pk, GOOD_TITLE, FixAttempt.Source.REVIEWER)
    assert reply["accepted"]
    fix.refresh_from_db()
    assert fix.status == Fix.Status.PENDING and fix.op["text"] == GOOD_TITLE


def test_rejection_reasons_reach_the_model(scanned):
    fix = model_fix(scanned, "/products/speckled-stoneware-mug")
    reply = service.submit_text(fix.pk, "Best Speckled Stoneware Mug for 12 oz | Mossgrove Clayworks", "model")
    assert not reply["accepted"]
    text = " ".join(reply["reasons"])
    assert "best" in text and "12" in text
    assert reply["tries_left"] == 2


def test_title_kept_by_another_page_is_taken(scanned):
    fix = model_fix(scanned, "/products/speckled-stoneware-mug")
    reply = service.submit_text(fix.pk, "Mugs and Cups | Mossgrove Clayworks", "model")
    assert any("/collections/mugs already uses" in r for r in reply["reasons"])


def test_parallel_sessions_cannot_claim_the_same_title(scanned):
    a = model_fix(scanned, "/products/speckled-stoneware-mug")
    b = model_fix(scanned, "/collections/tableware")
    replies: dict[int, dict] = {}
    gate = threading.Barrier(2)
    text = "Speckled Stoneware Mug and Tableware | Mossgrove Clayworks"

    def write(fix_id: int) -> None:
        gate.wait()
        try:
            replies[fix_id] = service.submit_text(fix_id, text, "model")
        finally:
            close_old_connections()

    threads = [threading.Thread(target=write, args=(f.pk,)) for f in (a, b)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    accepted = [fid for fid, r in replies.items() if r["accepted"]]
    # The text covers both pages' target queries and passes every other check, so the claim decides.
    assert len(accepted) == 1
    loser = (a if accepted[0] == b.pk else b).pk
    assert any("took this exact text" in r or "already uses" in r for r in replies[loser]["reasons"])
    assert TextClaim.objects.filter(norm_text=text.lower()).count() == 1


def test_reject_releases_the_claim_and_approve_needs_passing_checks(scanned):
    fix = model_fix(scanned, "/products/speckled-stoneware-mug")
    service.submit_text(fix.pk, GOOD_TITLE, "model")
    assert TextClaim.objects.filter(fix=fix).exists()
    fix.refresh_from_db()
    service.reject(fix)
    assert not TextClaim.objects.filter(fix=fix).exists()
    bad = model_fix(scanned, "/collections/tableware")
    service.submit_text(bad.pk, "Cheap stuff", FixAttempt.Source.REVIEWER)
    bad.refresh_from_db()
    with pytest.raises(service.FixError, match="failed check"):
        service.approve(bad)


def test_live_fix_cannot_be_edited(scanned):
    fix = model_fix(scanned, "/products/speckled-stoneware-mug")
    fix.status = Fix.Status.LIVE
    fix.save()
    with pytest.raises(service.FixError, match="revert it before editing"):
        service.edit(fix, GOOD_TITLE)


def test_autopilot_ships_only_passing_confident_fixes_in_autopilot_categories(scanned):
    gen = run_job(scanned, Run.Kind.GENERATE)
    fixes = Fix.objects.filter(created_run=gen)
    auto = fixes.filter(approved_by="autopilot")
    assert auto.exists()
    assert set(auto.values_list("category", flat=True)) <= {"technical", "rich"}
    assert not auto.filter(confidence="low").exists()
    assert fixes.filter(category__in=["titles", "meta", "alt"], status=Fix.Status.PENDING).count() > 0


def test_policy_off_writes_no_fixes_for_that_category(scanned):
    Policy.objects.filter(site=scanned, category="alt").update(mode=Policy.Mode.OFF)
    gen = run_job(scanned, Run.Kind.GENERATE)
    assert not Fix.objects.filter(created_run=gen, category="alt").exists()
    assert Fix.objects.filter(created_run=gen, category="titles").exists()


def test_alt_on_autopilot_ships_alt_text_in_v1(scanned):
    Policy.objects.filter(site=scanned, category="alt").update(mode=Policy.Mode.AUTOPILOT)
    gen = run_job(scanned, Run.Kind.GENERATE)
    assert gen.summary["release"] == "v1"
    assert Fix.objects.filter(category="alt", approved_by="autopilot").count() == 4


def test_custom_instructions_and_never_use_words_reach_the_prompt(scanned):
    from sitemend.fixers.writer import build_request

    scanned.custom_instructions = "Always mention the glaze colour."
    scanned.never_use_words = ["rustic"]
    scanned.save()
    fix = model_fix(scanned, "/products/speckled-stoneware-mug")
    fix.site.refresh_from_db()
    req = build_request(fix.path, [fix])
    assert "Always mention the glaze colour." in req.prompt
    assert "Never use these words: rustic" in req.prompt
    assert 'field="title"' in req.prompt and "Target query: speckled stoneware mug" in req.prompt
    assert req.max_turns == 5


def test_bulk_approve_skips_low_confidence(scanned):
    run_job(scanned, Run.Kind.GENERATE)
    low = Fix.objects.get(kind="unlink")
    assert service.bulk_approve(scanned, "technical") == []
    low.refresh_from_db()
    assert low.status == Fix.Status.PENDING
    ids = service.bulk_approve(scanned, "meta")
    assert len(ids) == 5

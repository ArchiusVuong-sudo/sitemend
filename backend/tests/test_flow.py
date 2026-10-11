"""The whole product loop in replay mode: scan, fix, approve, deploy, verify, revert, roll back."""

from __future__ import annotations

import pytest

from shop.origin import planted_issues
from sitemend.edge.views import render_edge
from sitemend.models import Fix, Release, Run

from .helpers import run_job

pytestmark = pytest.mark.django_db(transaction=True)


def edge_html(path: str) -> bytes:
    return render_edge(path)[1]


def test_full_flow_in_replay_mode(site, api, no_network):
    # Scan matches the planted manifest exactly.
    scan = run_job(site, Run.Kind.SCAN)
    assert scan.status == Run.Status.DONE, scan.error
    got = sorted((i.path, i.rule, i.key) for i in scan.issues.all())
    assert got == sorted((i["path"], i["rule"], i["key"]) for i in planted_issues())
    first_grade = scan.summary["grade"]["site"]

    # Generate: rule fixes plus model fixes from recorded sessions; autopilot ships v1.
    gen = run_job(site, Run.Kind.GENERATE)
    assert gen.status == Run.Status.DONE, gen.error
    assert gen.llm_mode == "replay"
    assert gen.summary["release"] == "v1"
    v1 = Release.objects.get(site=site, number=1)
    v1_cats = {o["category"] for o in v1.ops}
    assert v1_cats <= {"technical", "rich"}
    # The low-confidence broken-link fix waits even though Technical is on autopilot.
    unlink = Fix.objects.get(kind="unlink")
    assert unlink.confidence == "low" and unlink.status == Fix.Status.PENDING
    # Model fixes wait for approval and one shows a rejected first try.
    fern = Fix.objects.get(path="/journal/repotting-a-fern", kind="set_meta_description")
    tries = list(fern.attempts.all())
    assert len(tries) == 2 and not tries[0].passed and tries[1].passed
    assert "claims not on the page: best" in " ".join(c["detail"] for c in tries[0].checks)

    # A reviewer edits a title: a failing edit stays out, a passing edit can be approved.
    title = Fix.objects.get(path="/products/speckled-stoneware-mug", kind="set_title")
    bad = api.patch(f"/api/fixes/{title.pk}", {"text": "Best Speckled Stoneware Mug | Mossgrove Clayworks"}, format="json")
    assert bad.status_code == 200 and bad.json()["status"] == "needs_review"
    assert api.post(f"/api/fixes/{title.pk}/approve").status_code == 409
    good = api.patch(f"/api/fixes/{title.pk}", {"text": "Speckled Stoneware Mug, Thrown by Hand | Mossgrove Clayworks"},
                     format="json")
    assert good.json()["checks_passed"], good.json()["checks"]
    assert api.post(f"/api/fixes/{title.pk}/approve").status_code == 200
    for category in ("titles", "meta", "alt"):
        assert api.post("/api/fixes/bulk-approve", {"category": category}, format="json").status_code == 200
    assert api.post(f"/api/fixes/{unlink.pk}/approve").status_code == 200

    # Deploy makes v2; the edge serves the new title and names the release.
    dep = run_job(site, Run.Kind.DEPLOY)
    assert dep.status == Run.Status.DONE and dep.summary["release"] == "v2"
    res = api.get("/edge/products/speckled-stoneware-mug")
    assert res["X-Sitemend-Release"] == "v2"
    assert b"<title>Speckled Stoneware Mug, Thrown by Hand | Mossgrove Clayworks</title>" in res.content
    origin = api.get("/origin/products/speckled-stoneware-mug").content
    assert b"<title>Shop | Mossgrove Clayworks</title>" in origin

    # Verify re-scans the edge: every planted issue is gone and the grade goes up.
    ver = run_job(site, Run.Kind.VERIFY, target="edge")
    assert ver.status == Run.Status.DONE, ver.error
    assert ver.summary["issues_open"] == 0
    assert ver.summary["issues_fixed"] == len(planted_issues())
    assert ver.summary["grade"]["site"] == 100 > first_grade
    assert not Fix.objects.filter(status=Fix.Status.LIVE).exists()
    assert Fix.objects.filter(status=Fix.Status.VERIFIED).count() == Fix.objects.count()
    v2_mug = edge_html("/products/speckled-stoneware-mug")

    # Revert one title: v3, and the page's title issue comes back on the re-scan.
    about = Fix.objects.get(path="/about", kind="set_title")
    rev = run_job(site, Run.Kind.REVERT, target="edge", fix_id=about.pk)
    assert rev.status == Run.Status.DONE, rev.error
    assert rev.summary["release"] == "v3"
    assert [(i.path, i.rule) for i in rev.issues.all()] == [("/about", "title_missing")]
    about.refresh_from_db()
    assert about.status == Fix.Status.REVERTED
    assert b"<title>" not in edge_html("/about").split(b"</head>")[0]
    assert edge_html("/products/speckled-stoneware-mug") == v2_mug

    # Roll back to v1: v4 serves exactly what v1 served, byte for byte.
    v1_pages = {}
    rb = run_job(site, Run.Kind.ROLLBACK, target="edge", number=1)
    assert rb.status == Run.Status.DONE, rb.error
    assert rb.summary["release"] == "v4"
    v4 = Release.objects.get(site=site, number=4)
    assert v4.ops == v1.ops
    for path in {o["path"] for o in v1.ops} | {"/products/speckled-stoneware-mug"}:
        v1_pages[path] = edge_html(path)
    site.refresh_from_db()
    site.active_release = v1
    site.save(update_fields=["active_release"])
    for path, html in v1_pages.items():
        assert edge_html(path) == html
    # Issues the model fixes had cleared are open again after the rollback.
    open_rules = {i.rule for i in rb.issues.all()}
    assert {"title_duplicate", "meta_missing", "img_alt_missing"} <= open_rules
    assert rb.summary["grade"]["site"] < ver.summary["grade"]["site"]

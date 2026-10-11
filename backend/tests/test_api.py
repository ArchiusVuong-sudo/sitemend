"""REST API: 202 for jobs, clear 4xx for bad input and wrong states."""

from __future__ import annotations

import pytest

from sitemend.models import Fix, Release, Run

pytestmark = pytest.mark.django_db(transaction=True)


def test_health_reports_replay_and_synthetic(api):
    body = api.get("/api/health").json()
    assert body["ok"] and body["synthetic"] and body["llm"]["mode"] == "replay"


def test_site_seeds_itself_with_defaults(api):
    body = api.get("/api/site").json()
    assert body["name"] == "Mossgrove Clayworks"
    assert body["policies"] == {"technical": "autopilot", "rich": "autopilot", "titles": "approval",
                                "meta": "approval", "alt": "approval"}
    assert body["latest_scan"] is None and body["active_release"] is None


def test_scan_answers_202_with_a_run_id(api):
    res = api.post("/api/scan")
    assert res.status_code == 202
    run = api.get(f"/api/runs/{res.json()['run_id']}").json()
    assert run["status"] == "done" and run["done"] == run["total"] == 12
    assert run["summary"]["grade"]["issues"] == 27


def test_job_order_is_enforced(api):
    assert api.post("/api/generate").json()["error"] == "Run a scan first"
    assert api.post("/api/deploy").status_code == 409
    api.post("/api/scan")
    assert api.post("/api/deploy").json()["error"] == "Nothing approved to deploy"


def test_busy_site_refuses_a_second_job(api, site):
    Run.objects.create(site=site, kind=Run.Kind.SCAN, status=Run.Status.RUNNING)
    res = api.post("/api/scan")
    assert res.status_code == 409 and "still going" in res.json()["error"]


def test_settings_validation_and_normalisation(api):
    res = api.patch("/api/site", {"never_use_words": [" Cheap ", "cheap", "Rustic"], "custom_instructions": "Hi"},
                    format="json")
    assert res.status_code == 200
    assert res.json()["never_use_words"] == ["cheap", "rustic"]
    assert api.patch("/api/site", {"never_use_words": "cheap"}, format="json").status_code == 400


def test_policy_update(api):
    assert api.put("/api/policies/alt", {"mode": "autopilot"}, format="json").json()["alt"] == "autopilot"
    assert api.put("/api/policies/alt", {"mode": "sometimes"}, format="json").status_code == 400
    assert api.put("/api/policies/nope", {"mode": "off"}, format="json").status_code == 404


def test_issue_list_is_ranked_and_explained(api):
    api.post("/api/scan")
    issues = api.get("/api/issues").json()["issues"]
    assert len(issues) == 27
    assert [i["priority"] for i in issues] == sorted((i["priority"] for i in issues), reverse=True)
    assert issues[0]["path"] == "/products/speckled-stoneware-mug"
    assert "impressions" in issues[0]["priority_reason"]
    assert all(i["evidence"] for i in issues)


def test_fix_endpoints(api):
    api.post("/api/scan")
    api.post("/api/generate")
    fixes = api.get("/api/fixes").json()
    title = next(f for f in fixes if f["kind"] == "set_title" and f["path"] == "/about")
    detail = api.get(f"/api/fixes/{title['id']}").json()
    assert detail["attempts"] and detail["session"]["mode"] == "replay" and detail["session"]["input_tokens"] > 0
    preview = api.post(f"/api/fixes/{title['id']}/check", {"text": "Luxury studio!"}, format="json").json()
    assert preview["passed"] is False
    assert api.get(f"/api/fixes/{title['id']}").json()["after"] == title["after"]  # preview saves nothing
    assert api.patch(f"/api/fixes/{title['id']}", {"text": ""}, format="json").status_code == 400
    assert api.post(f"/api/fixes/{title['id']}/approve").status_code == 200
    assert api.post(f"/api/fixes/{title['id']}/approve").status_code == 409
    assert api.post(f"/api/fixes/{title['id']}/explode").status_code == 404
    rule = next(f for f in fixes if f["source"] == "rule")
    assert api.post(f"/api/fixes/{rule['id']}/check", {"text": "x"}, format="json").status_code == 400
    assert api.post("/api/fixes/bulk-approve", {"category": "nope"}, format="json").status_code == 400


def test_revert_and_rollback_guards(api, site):
    api.post("/api/scan")
    api.post("/api/generate")
    pending = Fix.objects.filter(status=Fix.Status.PENDING).first()
    assert api.post(f"/api/fixes/{pending.pk}/revert").status_code == 409
    assert api.post("/api/releases/1/rollback").json()["error"] == "v1 is already active"
    assert api.post("/api/releases/99/rollback").status_code == 404
    assert Release.objects.count() == 1


def test_compare_shows_origin_vs_edge(api):
    api.post("/api/scan")
    before = api.get("/api/compare?path=/collections/tableware").json()
    assert before["identical"] and before["release"] == "none"
    api.post("/api/generate")
    after = api.get("/api/compare?path=/collections/tableware").json()
    assert not after["identical"] and after["release"] == "v1" and after["added"] == 1
    assert any(r["type"] == "added" and 'rel="canonical"' in r["text"] for r in after["rows"])
    assert api.get("/api/compare?path=/shop/mugs").status_code == 404


def test_edge_mirrors_redirects_and_missing_pages(api):
    res = api.get("/edge/shop/mugs")
    assert res.status_code == 301 and res["Location"] == "/mugs" and res["X-Sitemend-Release"] == "none"
    assert api.get("/edge/products/nope").status_code == 404
    assert api.get("/origin/../config/settings.py").status_code == 404


def test_runs_include_spans_and_baselines(api):
    run_id = api.post("/api/scan").json()["run_id"]
    detail = api.get(f"/api/runs/{run_id}?spans=1").json()
    names = {s["name"] for s in detail["spans"]}
    assert {"scan job", "crawl", "fetch page", "audit"} <= names
    baselines = {b["name"]: b for b in api.get("/api/baselines").json()}
    assert baselines["fetch page"]["count"] == 16
    assert baselines["fetch page"]["p95_ms"] >= baselines["fetch page"]["p50_ms"]


def test_reset_clears_a_stuck_run(api, site):
    Run.objects.create(site=site, kind=Run.Kind.GENERATE, status=Run.Status.RUNNING)
    assert api.post("/api/scan").status_code == 409
    assert api.post("/api/site/reset").status_code == 200
    assert api.post("/api/scan").status_code == 202


def test_reset_clears_everything(api):
    api.post("/api/scan")
    api.post("/api/generate")
    body = api.post("/api/site/reset").json()
    assert body["latest_scan"] is None and body["active_release"] is None
    assert not Fix.objects.exists() and not Run.objects.exists()

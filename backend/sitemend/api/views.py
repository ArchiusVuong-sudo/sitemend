"""REST API. Long jobs answer 202 with a run id; the dashboard polls /api/runs/<id>."""

from __future__ import annotations

import difflib

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from shop.origin import fetch_origin

from .. import tasks
from ..edge.views import render_edge
from ..fixers import service
from ..llm import mode as llm_mode
from ..models import Category, Fix, Issue, ModelSession, Policy, Release, Run, Span
from ..scanning import latest_scan
from ..site_setup import get_site, reset
from ..tracing import baselines
from .serializers import (
    AttemptSerializer,
    CategoryInput,
    FixSerializer,
    IssueSerializer,
    PolicyInput,
    ReleaseSerializer,
    RunSerializer,
    SessionSerializer,
    SiteSettingsInput,
    SpanSerializer,
    TextInput,
)

ACTIVE = [Run.Status.QUEUED, Run.Status.RUNNING]
JOB_TASKS = {
    Run.Kind.SCAN: tasks.scan_task, Run.Kind.GENERATE: tasks.generate_task, Run.Kind.DEPLOY: tasks.deploy_task,
    Run.Kind.VERIFY: tasks.verify_task,
}


def _error(message: str, code: int = status.HTTP_409_CONFLICT) -> Response:
    return Response({"error": message}, status=code)


def _start(kind: str, target: str = "origin", task=None, *args) -> Response:
    site = get_site()
    busy = Run.objects.filter(site=site, status__in=ACTIVE).first()
    if busy:
        return Response({"error": f"A {busy.get_kind_display().lower()} run is still going", "run_id": busy.pk},
                        status=status.HTTP_409_CONFLICT)
    run = Run.objects.create(site=site, kind=kind, target=target)
    task = task or JOB_TASKS[kind]
    transaction.on_commit(lambda: task.delay(run.pk, *args))
    return Response({"run_id": run.pk, "status": run.status}, status=status.HTTP_202_ACCEPTED)


# ----- site -------------------------------------------------------------------------------------------


@api_view(["GET"])
def health(request: Request) -> Response:
    return Response({"ok": True, "llm": llm_mode.describe(), "synthetic": True})


def _site_payload() -> dict:
    site = get_site()
    origin = latest_scan(site, "origin")
    first = Run.objects.filter(site=site, kind=Run.Kind.SCAN, status=Run.Status.DONE).order_by("id").first()
    edge = latest_scan(site, "edge")
    return {
        "name": site.name,
        "domain": site.domain,
        "custom_instructions": site.custom_instructions,
        "never_use_words": site.never_use_words,
        "policies": {p.category: p.mode for p in site.policies.all()},
        "categories": [{"id": c.value, "label": c.label} for c in Category],
        "active_release": site.active_release.label if site.active_release else None,
        "latest_scan": RunSerializer(origin).data if origin else None,
        "first_scan_grade": first.summary.get("grade") if first else None,
        "latest_edge_scan": RunSerializer(edge).data if edge else None,
        "running": RunSerializer(Run.objects.filter(site=site, status__in=ACTIVE).first()).data
        if Run.objects.filter(site=site, status__in=ACTIVE).exists() else None,
        "llm": llm_mode.describe(),
    }


@api_view(["GET", "PATCH"])
def site_view(request: Request) -> Response:
    if request.method == "PATCH":
        data = SiteSettingsInput(data=request.data)
        data.is_valid(raise_exception=True)
        site = get_site()
        for key, value in data.validated_data.items():
            setattr(site, key, value)
        site.save()
    return Response(_site_payload())


@api_view(["PUT"])
def policy_view(request: Request, category: str) -> Response:
    if category not in Category.values:
        return _error("Unknown category", status.HTTP_404_NOT_FOUND)
    data = PolicyInput(data=request.data)
    data.is_valid(raise_exception=True)
    Policy.objects.update_or_create(site=get_site(), category=category, defaults={"mode": data.validated_data["mode"]})
    return Response(_site_payload()["policies"])


@api_view(["POST"])
def reset_view(request: Request) -> Response:
    """Always allowed, so a run left 'running' by a stopped worker can never lock the demo."""
    site = get_site()
    reset(site)
    return Response(_site_payload())


# ----- jobs -------------------------------------------------------------------------------------------


@api_view(["POST"])
def scan_view(request: Request) -> Response:
    return _start(Run.Kind.SCAN)


@api_view(["POST"])
def generate_view(request: Request) -> Response:
    if latest_scan(get_site(), "origin") is None:
        return _error("Run a scan first")
    return _start(Run.Kind.GENERATE)


@api_view(["POST"])
def deploy_view(request: Request) -> Response:
    if not Fix.objects.filter(site=get_site(), status=Fix.Status.APPROVED).exists():
        return _error("Nothing approved to deploy")
    return _start(Run.Kind.DEPLOY)


@api_view(["POST"])
def verify_view(request: Request) -> Response:
    return _start(Run.Kind.VERIFY, target="edge")


@api_view(["POST"])
def revert_view(request: Request, pk: int) -> Response:
    site = get_site()
    fix = get_object_or_404(Fix, pk=pk, site=site)
    live = set(site.active_release.fix_ids) if site.active_release else set()
    if fix.pk not in live:
        return _error("This fix is not in the active release")
    return _start(Run.Kind.REVERT, "edge", tasks.revert_task, fix.pk)


@api_view(["POST"])
def rollback_view(request: Request, number: int) -> Response:
    site = get_site()
    release = get_object_or_404(Release, site=site, number=number)
    if site.active_release_id == release.pk:
        return _error(f"{release.label} is already active")
    return _start(Run.Kind.ROLLBACK, "edge", tasks.rollback_task, number)


@api_view(["GET"])
def runs_view(request: Request) -> Response:
    runs = Run.objects.filter(site=get_site()).select_related("release")[:50]
    return Response(RunSerializer(runs, many=True).data)


@api_view(["GET"])
def run_view(request: Request, pk: int) -> Response:
    run = get_object_or_404(Run.objects.select_related("release"), pk=pk, site=get_site())
    payload = RunSerializer(run).data
    if request.query_params.get("spans") == "1":
        payload["spans"] = SpanSerializer(run.spans.all(), many=True).data
        payload["sessions"] = SessionSerializer(run.sessions.all(), many=True).data
    return Response(payload)


@api_view(["GET"])
def baselines_view(request: Request) -> Response:
    spans = list(Span.objects.filter(run__site=get_site()).only("name", "kind", "duration_ms", "status", "retries"))
    return Response([b.__dict__ for b in baselines(spans)])


# ----- issues and fixes -----------------------------------------------------------------------------------


@api_view(["GET"])
def issues_view(request: Request) -> Response:
    site = get_site()
    target = request.query_params.get("target", "origin")
    run = latest_scan(site, "edge" if target == "edge" else "origin")
    if run is None:
        return Response({"run": None, "issues": []})
    fixes = {(f.path, f.target): f for f in Fix.objects.filter(site=site)}
    by_rule: dict[tuple[str, str, str], Fix] = {}
    for f in fixes.values():
        for rule in f.rules:
            by_rule[(f.path, rule, f.target)] = f
    rows = []
    for issue in Issue.objects.filter(run=run):
        row = IssueSerializer(issue).data
        fix = by_rule.get((issue.path, issue.rule, issue.key))
        row["fix"] = {"id": fix.pk, "status": fix.status, "status_label": fix.get_status_display()} if fix else None
        rows.append(row)
    return Response({"run": RunSerializer(run).data, "issues": rows})


@api_view(["GET"])
def fixes_view(request: Request) -> Response:
    fixes = Fix.objects.filter(site=get_site()).prefetch_related("attempts")
    category = request.query_params.get("category")
    if category:
        fixes = fixes.filter(category=category)
    return Response(FixSerializer(fixes, many=True).data)


@api_view(["GET", "PATCH"])
def fix_view(request: Request, pk: int) -> Response:
    fix = get_object_or_404(Fix, pk=pk, site=get_site())
    if request.method == "PATCH":
        data = TextInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            service.edit(fix, data.validated_data["text"])
        except service.FixError as exc:
            return _error(str(exc))
        fix.refresh_from_db()
    payload = FixSerializer(fix).data
    payload["attempts"] = AttemptSerializer(fix.attempts.all(), many=True).data
    session = (ModelSession.objects.filter(run_id=fix.created_run_id, path=fix.path).order_by("-id").first()
               if fix.source == Fix.Source.MODEL else None)
    payload["session"] = SessionSerializer(session).data if session else None
    return Response(payload)


@api_view(["POST"])
def fix_check_view(request: Request, pk: int) -> Response:
    """Runs the checks on a draft text without saving it (live feedback while editing)."""
    fix = get_object_or_404(Fix, pk=pk, site=get_site())
    if fix.source != Fix.Source.MODEL:
        return _error("Only text fixes have checks to preview", status.HTTP_400_BAD_REQUEST)
    data = TextInput(data=request.data)
    data.is_valid(raise_exception=True)
    checks = service.preview_checks(fix, data.validated_data["text"])
    return Response({"checks": checks, "passed": all(c["passed"] for c in checks)})


@api_view(["POST"])
def fix_action_view(request: Request, pk: int, action: str) -> Response:
    fix = get_object_or_404(Fix, pk=pk, site=get_site())
    try:
        if action == "approve":
            service.approve(fix)
        elif action == "reject":
            service.reject(fix)
        else:
            return _error("Unknown action", status.HTTP_404_NOT_FOUND)
    except service.FixError as exc:
        return _error(str(exc))
    return Response(FixSerializer(fix).data)


@api_view(["POST"])
def bulk_approve_view(request: Request) -> Response:
    data = CategoryInput(data=request.data)
    data.is_valid(raise_exception=True)
    ids = service.bulk_approve(get_site(), data.validated_data["category"])
    return Response({"approved": ids})


# ----- releases and compare -------------------------------------------------------------------------------


@api_view(["GET"])
def releases_view(request: Request) -> Response:
    site = get_site()
    data = ReleaseSerializer(Release.objects.filter(site=site).select_related("parent"), many=True).data
    fixes = {f.pk: f for f in Fix.objects.filter(site=site)}
    for row in data:
        row["active"] = site.active_release_id == row["id"]
        for op in row["ops"]:
            fix = fixes.get(op["fix_id"])
            op["fix"] = {"kind": fix.kind, "status": fix.status, "after": fix.after[:200], "source": fix.source,
                         "target": fix.target} if fix else None
    return Response(data)


@api_view(["GET"])
def compare_view(request: Request) -> Response:
    path = "/" + request.query_params.get("path", "/").strip("/")
    origin = fetch_origin(path)
    if origin.status != 200:
        return _error(f"{path} is not a page (status {origin.status})", status.HTTP_404_NOT_FOUND)
    _, edge_body, _, label = render_edge(path)
    a = origin.body.decode("utf-8").splitlines()
    b = edge_body.decode("utf-8").splitlines()
    rows = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            rows.extend({"type": "same", "old": i + 1, "new": j + 1, "text": a[i]} for i, j in zip(range(i1, i2), range(j1, j2)))
            continue
        rows.extend({"type": "removed", "old": i + 1, "new": None, "text": a[i]} for i in range(i1, i2))
        rows.extend({"type": "added", "old": None, "new": j + 1, "text": b[j]} for j in range(j1, j2))
    return Response({
        "path": path, "release": label, "identical": origin.body == edge_body,
        "added": sum(1 for r in rows if r["type"] == "added"), "removed": sum(1 for r in rows if r["type"] == "removed"),
        "rows": rows,
    })


@api_view(["GET"])
def pages_view(request: Request) -> Response:
    site = get_site()
    return Response([{"path": p.path, "title": p.title} for p in site.pages.all()])

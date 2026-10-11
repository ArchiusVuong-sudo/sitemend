"""Job orchestration: what each background run does, step by step.

Celery tasks in tasks.py are thin wrappers around these functions, so tests
can run the same code eagerly and the API only ever creates a Run and enqueues it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from django.db.models import F
from django.utils import timezone

from .audit.html import ParsedPage
from .audit.rules import LinkStatus
from .fixers import service
from .fixers.rule_fixers import draft_rule_fixes
from .fixers.writer import write_page
from .llm import mode as llm_mode
from .models import Fix, Page, Release, Run, Site, Span
from .releases import revert_fix, rollback, ship_approved
from .scanning import ScanOutcome, category_counts, latest_scan, run_scan
from .tracing import bind_run, span

log = logging.getLogger(__name__)


class JobError(RuntimeError):
    """An expected failure with a message for the user (for example: scan first)."""


@contextmanager
def job(run_id: int, *, finish: bool = True, retryable: tuple[type[BaseException], ...] = (),
        can_retry: bool = False) -> Iterator[Run]:
    run = Run.objects.select_related("site").get(pk=run_id)
    Run.objects.filter(pk=run_id).update(status=Run.Status.RUNNING, started_at=run.started_at or timezone.now())
    try:
        with bind_run(run.pk):
            with span(f"{run.kind} job", Span.Kind.TASK, label=run.get_kind_display()):
                yield run
    except retryable:
        if can_retry:
            Run.objects.filter(pk=run_id).update(status=Run.Status.QUEUED, error="retrying after a network error")
            raise
        _fail(run_id, "network error, gave up after retries")
        return
    except JobError as exc:
        _fail(run_id, str(exc))
        return
    except Exception as exc:
        log.exception("run %s failed", run_id)
        _fail(run_id, f"{type(exc).__name__}: {exc}")
        return
    if finish:
        Run.objects.filter(pk=run_id).update(status=Run.Status.DONE, finished_at=timezone.now())


def _fail(run_id: int, message: str) -> None:
    Run.objects.filter(pk=run_id).update(status=Run.Status.FAILED, error=message[:2000], finished_at=timezone.now())


def _save_summary(run: Run, **values: object) -> None:
    run.refresh_from_db(fields=["summary"])
    summary = dict(run.summary or {})
    summary.update(values)
    Run.objects.filter(pk=run.pk).update(summary=summary)
    run.summary = summary


def _scan_summary(outcome: ScanOutcome) -> dict:
    links = {path: [s.status, list(s.chain), s.final] for path, s in outcome.crawl.links.items() if s.status != 200}
    return {
        "grade": outcome.grade.as_dict(),
        "categories": category_counts(outcome.findings),
        "pages": len(outcome.crawl.pages),
        "fetches": outcome.crawl.fetches,
        "release": outcome.crawl.release,
        "links": links,
    }


# ----- scan -----------------------------------------------------------------------------------------


def scan(run: Run) -> None:
    outcome = run_scan(run, "origin")
    _save_summary(run, **_scan_summary(outcome))


# ----- generate -------------------------------------------------------------------------------------


def generate(run: Run, enqueue_page) -> int:
    """Creates rule fixes now and one model session per page. Returns how many page sessions were queued."""
    site = run.site
    origin = latest_scan(site, "origin")
    if origin is None:
        raise JobError("Run a scan first")
    findings = service.open_findings(origin.pk)
    links = {p: LinkStatus(v[0], tuple(v[1]), v[2]) for p, v in (origin.summary.get("links") or {}).items()}
    pages = {p.path: ParsedPage.parse(p.path, 200, p.html) for p in Page.objects.filter(site=site)}
    for path in pages:
        links.setdefault(path, LinkStatus(200, (), path))
    modes = {p.category: p.mode for p in site.policies.all()}
    provider = llm_mode.get_provider()
    Run.objects.filter(pk=run.pk).update(llm_mode=provider.mode)

    with span("rule fixes", Span.Kind.STEP, label="technical and rich results") as s:
        drafts = [d for d in draft_rule_fixes(findings, pages, links) if modes.get(d.category) != "off"]
        created = 0
        for draft in drafts:
            checks = service.dry_run_check(draft, pages[draft.path], links)
            if service.create_rule_fix(site, run.pk, draft, checks):
                created += 1
        s.set(drafts=len(drafts), created=created)

    by_page: dict[str, list] = {}
    for f in findings:
        by_page.setdefault(f.path, []).append(f)
    queued: list[str] = []
    with span("plan model sessions", Span.Kind.STEP) as s:
        for path, page_findings in sorted(by_page.items()):
            items = service.model_items(page_findings, pages[path], modes)
            made = [service.create_model_fix(site, run.pk, path, item) for item in items]
            if any(made):
                queued.append(path)
        s.set(pages=len(queued))
    Run.objects.filter(pk=run.pk).update(total=len(queued), done=0)
    _save_summary(run, rule_fixes=created, model_pages=len(queued), llm_mode=provider.mode, model=provider.model)
    if not queued:
        finalize_generate(run.pk)
        return 0
    for path in queued:
        enqueue_page(run.pk, path)
    return len(queued)


def page_session(run_id: int, path: str, parent_span_id: int | None) -> None:
    try:
        with bind_run(run_id, parent_span_id):
            write_page(run_id, path)
    except Exception:
        log.exception("model session for %s failed", path)
        service.finish_writing(path, run_id, "The session crashed; see the run trace")
    finally:
        Run.objects.filter(pk=run_id).update(done=F("done") + 1)
        run = Run.objects.get(pk=run_id)
        if run.done >= run.total:
            finalize_generate(run_id)


def finalize_generate(run_id: int) -> None:
    # Only one caller wins this update, so the release is made once even when
    # the last two page sessions finish at the same moment.
    if not Run.objects.filter(pk=run_id, finalized=False).update(finalized=True):
        return
    run = Run.objects.select_related("site").get(pk=run_id)
    with bind_run(run.pk):
        with span("autopilot", Span.Kind.STEP, label="ship passing fixes in autopilot categories") as s:
            ids = service.apply_autopilot(run.site, run.pk)
            release = ship_approved(run.site, Release.Kind.AUTOPILOT, ids) if ids else None
            s.set(approved=len(ids), release=release.label if release else None)
    fixes = Fix.objects.filter(created_run=run)
    _save_summary(
        run,
        fixes=fixes.count(),
        autopilot=len(ids),
        waiting=fixes.filter(status__in=[Fix.Status.PENDING, Fix.Status.NEEDS_REVIEW]).count(),
        needs_review=fixes.filter(status=Fix.Status.NEEDS_REVIEW).count(),
        release=release.label if release else None,
    )
    Run.objects.filter(pk=run_id).update(status=Run.Status.DONE, finished_at=timezone.now(),
                                         release=release)


# ----- deploy, verify, revert, rollback ---------------------------------------------------------------


def deploy(run: Run) -> None:
    with span("make release", Span.Kind.STEP) as s:
        release = ship_approved(run.site, Release.Kind.DEPLOY)
        if release is None:
            raise JobError("Nothing approved to deploy")
        s.set(release=release.label, ops=len(release.ops))
    Run.objects.filter(pk=run.pk).update(release=release)
    _save_summary(run, release=release.label, ops=len(release.ops))


def mark_verified(site: Site, run: Run, outcome: ScanOutcome) -> dict:
    present = {(f.path, f.rule, f.key) for f in outcome.findings}
    verified = still_open = 0
    for fix in Fix.objects.filter(site=site, status__in=[Fix.Status.LIVE, Fix.Status.VERIFIED]):
        if any((fix.path, rule, fix.target) in present for rule in fix.rules):
            fix.status, fix.verified_run = Fix.Status.LIVE, None
            still_open += 1
        else:
            fix.status, fix.verified_run = Fix.Status.VERIFIED, run
            verified += 1
        fix.save(update_fields=["status", "verified_run", "updated_at"])
    return {"verified": verified, "still_open": still_open}


def edge_rescan(run: Run) -> None:
    site = run.site
    origin = latest_scan(site, "origin")
    outcome = run_scan(run, "edge")
    with span("mark verified", Span.Kind.STEP) as s:
        marks = mark_verified(site, run, outcome)
        s.set(**marks)
    before = (origin.summary.get("grade") if origin else None) or {}
    origin_keys = set(origin.issues.values_list("path", "rule", "key")) if origin else set()
    edge_keys = {(f.path, f.rule, f.key) for f in outcome.findings}
    _save_summary(
        run, **_scan_summary(outcome), grade_before=before, issues_fixed=len(origin_keys - edge_keys),
        issues_open=len(edge_keys), **marks,
    )


def verify(run: Run) -> None:
    edge_rescan(run)


def revert(run: Run, fix_id: int) -> None:
    fix = Fix.objects.get(pk=fix_id, site=run.site)
    with span("make release", Span.Kind.STEP, label=f"revert fix {fix_id}") as s:
        release = revert_fix(run.site, fix)
        s.set(release=release.label)
    Run.objects.filter(pk=run.pk).update(release=release)
    _save_summary(run, release=release.label, reverted_fix=fix_id)
    edge_rescan(run)


def roll_back(run: Run, number: int) -> None:
    with span("make release", Span.Kind.STEP, label=f"roll back to v{number}") as s:
        release = rollback(run.site, number)
        s.set(release=release.label)
    Run.objects.filter(pk=run.pk).update(release=release)
    _save_summary(run, release=release.label, rolled_back_to=f"v{number}")
    edge_rescan(run)

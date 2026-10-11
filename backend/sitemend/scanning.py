"""Scans: crawl the origin or the edge, run the rules, store issues with priority and grade."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from django.conf import settings
from django.db import transaction
from django.db.models import F

from .audit.crawl import CrawlResult, Fetched, crawl
from .audit.grade import Grade, PageInfo, grade
from .audit.priority import Stat, band_medians, score
from .audit.rules import Finding, SiteContext, audit
from .models import Issue, Page, Run, SearchStat, Site, Span
from .tracing import span

FETCH_RETRIES = 3

# Tests replace this with an in-process WSGI client.
ClientFactory = Callable[[], httpx.Client]


def default_client() -> httpx.Client:
    return httpx.Client(base_url=settings.SITEMEND_SELF_URL, timeout=10.0, follow_redirects=False)


client_factory: ClientFactory = default_client


@dataclass
class ScanOutcome:
    crawl: CrawlResult
    findings: list[Finding]
    grade: Grade


def make_fetch(client: httpx.Client, mount: str) -> Callable[[str], Fetched]:
    def fetch(path: str) -> Fetched:
        with span("fetch page", Span.Kind.FETCH, label=f"/{mount}{path}", path=path, mount=mount) as s:
            for attempt in range(FETCH_RETRIES):
                try:
                    res = client.get(f"/{mount}{path}")
                    if res.status_code >= 500 and attempt < FETCH_RETRIES - 1:
                        raise httpx.HTTPStatusError("server error", request=res.request, response=res)
                    break
                except (httpx.TransportError, httpx.HTTPStatusError):
                    if attempt == FETCH_RETRIES - 1:
                        raise
                    s.retries += 1
                    time.sleep(0.2 * (2 ** attempt))
            s.set(status=res.status_code, bytes=len(res.content))
            return Fetched(path=path, status=res.status_code, body=res.text,
                           location=res.headers.get("location"), release=res.headers.get("x-sitemend-release"))

    return fetch


def stats_for(site: Site) -> dict[str, Stat]:
    return {
        s.path: Stat(s.path, s.impressions, s.clicks, s.ctr, s.position, s.top_query)
        for s in SearchStat.objects.filter(site=site)
    }


def run_scan(run: Run, mount: str) -> ScanOutcome:
    site = run.site

    def progress(done: int, total: int) -> None:
        Run.objects.filter(pk=run.pk).update(done=done, total=total)

    with httpx_client() as client:
        with span("crawl", Span.Kind.STEP, label=f"crawl /{mount}"):
            result = crawl(make_fetch(client, mount), on_progress=progress)
    with span("audit", Span.Kind.STEP, label=f"{len(result.pages)} pages, 9 rules") as s:
        findings = audit(SiteContext.build(result.pages, result.links))
        s.set(issues=len(findings))
    g = grade([PageInfo(p.path, p.is_product()) for p in result.pages], findings)
    stats = stats_for(site)
    medians = band_medians(list(stats.values()))
    with transaction.atomic():
        if mount == "origin":  # the origin snapshot is what fixes are written against
            for page in result.pages:
                Page.objects.update_or_create(
                    site=site, path=page.path,
                    defaults={"title": page.title() or "", "meta_description": page.meta_description() or "",
                              "html": page.html,
                              "status_code": page.status, "last_run": run},
                )
        Issue.objects.bulk_create([
            Issue(run=run, site=site, path=f.path, rule=f.rule, key=f.key, category=f.category, severity=f.severity,
                  message=f.message, evidence=f.evidence,
                  priority=(p := score(stats.get(f.path), f.severity, medians)).score, priority_reason=p.reason)
            for f in findings
        ])
        Run.objects.filter(pk=run.pk).update(done=F("total"))
    return ScanOutcome(crawl=result, findings=findings, grade=g)


def httpx_client() -> httpx.Client:
    return client_factory()


def category_counts(findings: list[Finding]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        out[f.category] = out.get(f.category, 0) + 1
    return out


def latest_scan(site: Site, target: str = "origin") -> Run | None:
    kinds = [Run.Kind.SCAN] if target == "origin" else [Run.Kind.VERIFY, Run.Kind.REVERT, Run.Kind.ROLLBACK]
    return (Run.objects.filter(site=site, kind__in=kinds, status=Run.Status.DONE, target=target)
            .order_by("-id").first())

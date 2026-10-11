"""Runs scan and generate against the live model and saves every session as a replay fixture.

Run it on a scratch database (make record does this). It resets the site first.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from ... import jobs, scanning
from ...inprocess import wsgi_client
from ...llm import mode as llm_mode
from ...models import Fix, ModelSession, Run
from ...site_setup import get_site, reset


class Command(BaseCommand):
    help = "Record replay fixtures from a live run"

    def handle(self, *args, **options) -> None:
        provider = llm_mode.get_provider()
        if provider.mode != "live":
            raise CommandError("Live mode is not available (sign in to Claude Code or set ANTHROPIC_API_KEY)")
        settings.SITEMEND_RECORD = True
        scanning.client_factory = wsgi_client
        folder = settings.SITEMEND_FIXTURES_DIR
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.json"):
            old.unlink()

        site = reset(get_site())
        scan = Run.objects.create(site=site, kind=Run.Kind.SCAN)
        with jobs.job(scan.pk) as run:
            jobs.scan(run)
        gen = Run.objects.create(site=site, kind=Run.Kind.GENERATE)
        pool = ThreadPoolExecutor(max_workers=settings.SITEMEND_MAX_SESSIONS)
        futures = []

        def session(run_id: int, path: str, parent: int | None) -> None:
            try:
                jobs.page_session(run_id, path, parent)
            finally:
                close_old_connections()

        with jobs.job(gen.pk, finish=False) as run:
            from ...tracing import current_ids

            _, parent = current_ids()
            jobs.generate(run, lambda rid, path: futures.append(pool.submit(session, rid, path, parent)))
        for f in futures:
            f.result()
        pool.shutdown()

        (folder / "_meta.json").write_text(json.dumps({
            "model": provider.model,
            "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "note": "Model sessions recorded from a live run by manage.py record_fixtures. "
                    "Replay sends the same text through the same checks.",
        }, indent=2) + "\n")
        for s in ModelSession.objects.filter(run=gen).order_by("path"):
            fixes = Fix.objects.filter(created_run=gen, path=s.path)
            ok = fixes.exclude(status__in=[Fix.Status.NEEDS_REVIEW, Fix.Status.WRITING]).count()
            self.stdout.write(f"{s.path:45} {s.latency_ms:6d} ms  {s.input_tokens:6d} in {s.output_tokens:5d} out  "
                              f"{ok}/{fixes.count()} passed  {s.error[:60]}")
        self.stdout.write(self.style.SUCCESS(f"Saved fixtures to {folder.name}/"))

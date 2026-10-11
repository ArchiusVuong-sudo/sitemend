from __future__ import annotations

import pytest

from sitemend.models import Run, Span
from sitemend.tracing import baselines, bind_run, percentile, span

pytestmark = pytest.mark.django_db


def test_spans_nest_and_record_errors(site):
    run = Run.objects.create(site=site, kind=Run.Kind.SCAN)
    with bind_run(run.pk):
        with span("outer", Span.Kind.TASK) as outer:
            with span("inner", Span.Kind.FETCH, label="/x", path="/x") as inner:
                inner.set(status=200)
                inner.retries = 1
            with pytest.raises(ValueError):
                with span("broken", Span.Kind.STEP):
                    raise ValueError("boom")
            outer.set(done=True)
    rows = {s.name: s for s in Span.objects.filter(run=run)}
    assert rows["inner"].parent_id == rows["outer"].pk == rows["broken"].parent_id
    assert rows["inner"].attrs == {"path": "/x", "status": 200} and rows["inner"].retries == 1
    assert rows["broken"].status == "error" and "boom" in rows["broken"].error
    assert rows["outer"].status == "ok" and rows["outer"].duration_ms >= rows["inner"].duration_ms


def test_span_without_a_run_is_a_no_op():
    with span("free") as s:
        s.set(x=1)
    assert s.row is None


def test_percentiles_and_baselines(site):
    assert percentile([], 50) == 0.0
    assert percentile([5.0], 95) == 5.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(2.5)
    run = Run.objects.create(site=site, kind=Run.Kind.SCAN)
    from django.utils import timezone

    for d in (10, 20, 30, 40, 1000):
        Span.objects.create(run=run, name="fetch page", kind="fetch", started_at=timezone.now(), duration_ms=d)
    Span.objects.create(run=run, name="fetch page", kind="fetch", started_at=timezone.now(), duration_ms=5,
                        status="error", retries=2)
    [b] = baselines(list(Span.objects.all()))
    assert (b.count, b.errors, b.retries) == (6, 1, 2)
    assert b.p50_ms == 25.0 and b.p95_ms > 500

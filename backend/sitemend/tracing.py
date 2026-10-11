"""Spans for every task, page fetch, model session and tool call.

A span row is written when it starts (so children can point at it) and
updated when it ends. The current run and parent span live in context
variables, which follow the code into worker threads and async tasks.
"""

from __future__ import annotations

import contextvars
import time
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from statistics import quantiles
from typing import Any

from django.utils import timezone

from .models import Span

_run_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("run_id", default=None)
_parent_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("parent_span_id", default=None)


@dataclass
class OpenSpan:
    row: Span | None
    attrs: dict[str, Any] = field(default_factory=dict)
    retries: int = 0
    failure: str = ""

    def set(self, **attrs: Any) -> None:
        self.attrs.update(attrs)

    def fail(self, message: str) -> None:
        """Marks the span as failed without raising (the caller handled the error)."""
        self.failure = message


@contextmanager
def bind_run(run_id: int, parent_id: int | None = None) -> Iterator[None]:
    t1 = _run_id.set(run_id)
    t2 = _parent_id.set(parent_id)
    try:
        yield
    finally:
        _run_id.reset(t1)
        _parent_id.reset(t2)


def current_ids() -> tuple[int | None, int | None]:
    return _run_id.get(), _parent_id.get()


@contextmanager
def span(name: str, kind: str = Span.Kind.STEP, label: str = "", **attrs: Any) -> Iterator[OpenSpan]:
    run_id = _run_id.get()
    if run_id is None:
        yield OpenSpan(row=None, attrs=dict(attrs))
        return
    row = Span.objects.create(
        run_id=run_id, parent_id=_parent_id.get(), name=name, kind=kind, label=label[:300],
        started_at=timezone.now(), status="running", attrs=dict(attrs),
    )
    handle = OpenSpan(row=row, attrs=dict(attrs))
    token = _parent_id.set(row.id)
    t0 = time.perf_counter()
    try:
        yield handle
        row.status = "error" if handle.failure else "ok"
        row.error = handle.failure[:2000]
    except BaseException as exc:
        row.status = "error"
        row.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()[:2000]
        raise
    finally:
        _parent_id.reset(token)
        row.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        row.attrs = handle.attrs
        row.retries = handle.retries
        Span.objects.filter(pk=row.pk).update(
            status=row.status, error=row.error, duration_ms=row.duration_ms, attrs=row.attrs, retries=row.retries
        )


@dataclass(frozen=True)
class Baseline:
    name: str
    kind: str
    count: int
    p50_ms: float
    p95_ms: float
    errors: int
    retries: int


def percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    cuts = quantiles(sorted(values), n=100, method="inclusive")
    return cuts[pct - 1]


def baselines(spans: list[Span]) -> list[Baseline]:
    groups: dict[tuple[str, str], list[Span]] = {}
    for s in spans:
        if s.status == "running":
            continue
        groups.setdefault((s.name, s.kind), []).append(s)
    out = []
    for (name, kind), rows in sorted(groups.items()):
        durations = [r.duration_ms for r in rows]
        out.append(Baseline(
            name=name, kind=kind, count=len(rows),
            p50_ms=round(percentile(durations, 50), 1), p95_ms=round(percentile(durations, 95), 1),
            errors=sum(1 for r in rows if r.status == "error"), retries=sum(r.retries for r in rows),
        ))
    return out

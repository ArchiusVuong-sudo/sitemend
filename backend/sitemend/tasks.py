"""Celery tasks. Job state lives in the Run row, never in a result backend."""

from __future__ import annotations

import httpx
from celery import shared_task

from . import jobs
from .releases import ReleaseError
from .tracing import current_ids

NETWORK_ERRORS = (httpx.TransportError,)
RETRY = {"autoretry_for": NETWORK_ERRORS, "retry_backoff": 2, "retry_backoff_max": 20, "max_retries": 3}


def _can_retry(task) -> bool:
    return task.request.retries < RETRY["max_retries"] and not task.request.is_eager


@shared_task(bind=True, **RETRY)
def scan_task(self, run_id: int) -> None:
    with jobs.job(run_id, retryable=NETWORK_ERRORS, can_retry=_can_retry(self)) as run:
        jobs.scan(run)


@shared_task(bind=True)
def generate_task(self, run_id: int) -> None:
    with jobs.job(run_id, finish=False) as run:
        _, parent = current_ids()
        jobs.generate(run, lambda rid, path: page_task.delay(rid, path, parent))


@shared_task(bind=True)
def page_task(self, run_id: int, path: str, parent_span_id: int | None = None) -> None:
    jobs.page_session(run_id, path, parent_span_id)


@shared_task(bind=True)
def deploy_task(self, run_id: int) -> None:
    with jobs.job(run_id) as run:
        jobs.deploy(run)


@shared_task(bind=True, **RETRY)
def verify_task(self, run_id: int) -> None:
    with jobs.job(run_id, retryable=NETWORK_ERRORS, can_retry=_can_retry(self)) as run:
        jobs.verify(run)


@shared_task(bind=True)
def revert_task(self, run_id: int, fix_id: int) -> None:
    with jobs.job(run_id) as run:
        try:
            jobs.revert(run, fix_id)
        except ReleaseError as exc:
            raise jobs.JobError(str(exc)) from exc


@shared_task(bind=True)
def rollback_task(self, run_id: int, number: int) -> None:
    with jobs.job(run_id) as run:
        try:
            jobs.roll_back(run, number)
        except ReleaseError as exc:
            raise jobs.JobError(str(exc)) from exc

from __future__ import annotations

from sitemend import jobs
from sitemend.models import Run, Site


def run_job(site: Site, kind: str, target: str = "origin", **kwargs) -> Run:
    """Runs a job the way the worker would, inline."""
    from sitemend import tasks

    run = Run.objects.create(site=site, kind=kind, target=target)
    task = {
        Run.Kind.SCAN: tasks.scan_task, Run.Kind.GENERATE: tasks.generate_task, Run.Kind.DEPLOY: tasks.deploy_task,
        Run.Kind.VERIFY: tasks.verify_task, Run.Kind.REVERT: tasks.revert_task, Run.Kind.ROLLBACK: tasks.rollback_task,
    }[kind]
    task.delay(run.pk, *kwargs.values())
    run.refresh_from_db()
    return run


__all__ = ["run_job", "jobs"]

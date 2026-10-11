"""Releases: immutable, numbered snapshots of what the edge applies.

Deploy, revert and rollback never edit a release. Each makes a new one and
points the site at it, so going back is always possible and the history stays
readable.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from .models import Fix, Release, Site

LIVE_STATES = {Fix.Status.LIVE, Fix.Status.VERIFIED}


class ReleaseError(ValueError):
    pass


def active_ops(site: Site) -> list[dict]:
    site.refresh_from_db(fields=["active_release"])
    return list(site.active_release.ops) if site.active_release else []


def _entry(fix: Fix) -> dict:
    return {"fix_id": fix.pk, "path": fix.path, "category": fix.category, "op": dict(fix.op)}


def _sorted(ops: list[dict]) -> list[dict]:
    return sorted(ops, key=lambda o: (o["path"], o["fix_id"]))


@transaction.atomic
def make_release(site: Site, kind: str, ops: list[dict], note: str, parent: Release | None = None) -> Release:
    number = (Release.objects.filter(site=site).aggregate(n=Max("number"))["n"] or 0) + 1
    release = Release.objects.create(site=site, number=number, kind=kind, ops=_sorted(ops), note=note,
                                     parent=parent or site.active_release)
    Site.objects.filter(pk=site.pk).update(active_release=release)
    site.active_release = release
    sync_statuses(site, release)
    return release


def sync_statuses(site: Site, release: Release) -> None:
    """Fix states follow the active release: in it means deployed, dropped from it means reverted."""
    live_ids = set(release.fix_ids)
    for fix in Fix.objects.filter(site=site, status__in=[*LIVE_STATES, Fix.Status.APPROVED, Fix.Status.REVERTED]):
        if fix.pk in live_ids and fix.status in (Fix.Status.APPROVED, Fix.Status.REVERTED):
            fix.status = Fix.Status.LIVE
            fix.verified_run = None
        elif fix.pk not in live_ids and fix.status in LIVE_STATES:
            fix.status = Fix.Status.REVERTED
            fix.verified_run = None
        else:
            continue
        fix.save(update_fields=["status", "verified_run", "updated_at"])


def ship_approved(site: Site, kind: str, fix_ids: list[int] | None = None) -> Release | None:
    """New release = active operations plus the approved fixes (all, or the given ids)."""
    approved = Fix.objects.filter(site=site, status=Fix.Status.APPROVED)
    if fix_ids is not None:
        approved = approved.filter(pk__in=fix_ids)
    approved = list(approved)
    if not approved:
        return None
    ops = {o["fix_id"]: o for o in active_ops(site)}
    for fix in approved:
        ops[fix.pk] = _entry(fix)
    note = f"{len(approved)} fix{'es' if len(approved) != 1 else ''}"
    note += " shipped on autopilot" if kind == Release.Kind.AUTOPILOT else " approved and deployed"
    return make_release(site, kind, list(ops.values()), note)


def revert_fix(site: Site, fix: Fix) -> Release:
    ops = active_ops(site)
    if fix.pk not in {o["fix_id"] for o in ops}:
        raise ReleaseError("This fix is not in the active release")
    kept = [o for o in ops if o["fix_id"] != fix.pk]
    label = {"set_title": "title", "set_meta_description": "meta description", "set_alt": "alt text"}.get(
        fix.kind, fix.kind.replace("_", " "))
    return make_release(site, Release.Kind.REVERT, kept, f"Reverted {label} on {fix.path}")


def rollback(site: Site, number: int) -> Release:
    target = Release.objects.filter(site=site, number=number).first()
    if target is None:
        raise ReleaseError(f"Release v{number} does not exist")
    if site.active_release_id == target.pk:
        raise ReleaseError(f"v{number} is already active")
    return make_release(site, Release.Kind.ROLLBACK, list(target.ops), f"Rolled back to v{number}", parent=target)


def ops_for_path(release: Release | None, path: str) -> list[dict]:
    if release is None:
        return []
    return [o["op"] for o in release.ops if o["path"] == path]

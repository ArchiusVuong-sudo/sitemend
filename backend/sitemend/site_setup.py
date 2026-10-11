"""Creates the one synthetic site the demo runs on, and resets it."""

from __future__ import annotations

from django.db import transaction

from shop.origin import search_data

from .models import Category, Fix, Policy, Release, Run, SearchStat, Site, TextClaim

SITE_NAME = "Mossgrove Clayworks"
SITE_DOMAIN = "mossgrove-clayworks.example"

DEFAULT_INSTRUCTIONS = (
    "Keep the brand name Mossgrove Clayworks at the end of every title, after a | sign. "
    "Warm, plain tone, like a potter talking to a customer at a market stall."
)
DEFAULT_NEVER_USE = ["cheap", "luxury", "artisanal"]

DEFAULT_POLICY = {
    Category.TECHNICAL: Policy.Mode.AUTOPILOT,
    Category.RICH: Policy.Mode.AUTOPILOT,
    Category.TITLES: Policy.Mode.APPROVAL,
    Category.META: Policy.Mode.APPROVAL,
    Category.ALT: Policy.Mode.APPROVAL,
}


def get_site() -> Site:
    site = Site.objects.order_by("id").first()
    return site if site is not None else seed()


@transaction.atomic
def seed() -> Site:
    site = Site.objects.create(
        name=SITE_NAME, domain=SITE_DOMAIN,
        custom_instructions=DEFAULT_INSTRUCTIONS, never_use_words=list(DEFAULT_NEVER_USE),
    )
    for category, mode in DEFAULT_POLICY.items():
        Policy.objects.create(site=site, category=category, mode=mode)
    for path, row in search_data().items():
        SearchStat.objects.create(
            site=site, path=path, impressions=row["impressions"], clicks=row["clicks"], ctr=row["ctr"],
            position=row["position"], queries=row["queries"],
        )
    return site


@transaction.atomic
def reset(site: Site) -> Site:
    """Back to a fresh site: no scans, fixes or releases. Settings return to defaults."""
    Site.objects.filter(pk=site.pk).update(active_release=None)
    TextClaim.objects.filter(site=site).delete()
    Fix.objects.filter(site=site).delete()
    Release.objects.filter(site=site).delete()
    Run.objects.filter(site=site).delete()
    site.pages.all().delete()
    site.custom_instructions = DEFAULT_INSTRUCTIONS
    site.never_use_words = list(DEFAULT_NEVER_USE)
    site.active_release = None
    site.save()
    for category, mode in DEFAULT_POLICY.items():
        Policy.objects.update_or_create(site=site, category=category, defaults={"mode": mode})
    return site


def policy_map(site: Site) -> dict[str, str]:
    return {p.category: p.mode for p in site.policies.all()}

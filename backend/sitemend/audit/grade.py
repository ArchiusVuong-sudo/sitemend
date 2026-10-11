"""Site grade from scan findings.

Every page has check slots per group (title, meta, alt, ...). A slot fails
when the page has any finding in it; a failed slot costs its worst severity
(high 3, medium 2, low 1) out of 3. Group score = 100 * (1 - cost / (slots * 3)).
Site grade = 40% Technical + 40% On-page + 20% Rich results.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rules import ISSUE_SLOTS, Finding

SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

GROUPS: dict[str, tuple[str, ...]] = {
    "technical": ("canonical", "links", "headings"),
    "onpage": ("title", "meta", "alt"),
    "rich": ("social", "product_schema"),
}
GROUP_WEIGHTS = {"technical": 0.4, "onpage": 0.4, "rich": 0.2}


@dataclass(frozen=True)
class PageInfo:
    path: str
    is_product: bool


@dataclass(frozen=True)
class Grade:
    site: int
    technical: int
    onpage: int
    rich: int
    clean_pages: int
    pages: int
    issues: int

    def as_dict(self) -> dict:
        return {
            "site": self.site, "technical": self.technical, "onpage": self.onpage, "rich": self.rich,
            "clean_pages": self.clean_pages, "pages": self.pages, "issues": self.issues,
        }


def _slots_for(page: PageInfo, group: str) -> tuple[str, ...]:
    slots = GROUPS[group]
    if group == "rich" and not page.is_product:
        return tuple(s for s in slots if s != "product_schema")
    return slots


def grade(pages: list[PageInfo], findings: list[Finding]) -> Grade:
    worst: dict[tuple[str, str], int] = {}
    for f in findings:
        slot = ISSUE_SLOTS[f.rule]
        key = (f.path, slot)
        worst[key] = max(worst.get(key, 0), SEVERITY_WEIGHT[f.severity])

    scores: dict[str, int] = {}
    for group in GROUPS:
        total = cost = 0
        for page in pages:
            for slot in _slots_for(page, group):
                total += 3
                cost += worst.get((page.path, slot), 0)
        scores[group] = round(100 * (1 - cost / total)) if total else 100

    site = round(sum(scores[g] * w for g, w in GROUP_WEIGHTS.items()))
    dirty = {f.path for f in findings}
    return Grade(
        site=site, technical=scores["technical"], onpage=scores["onpage"], rich=scores["rich"],
        clean_pages=sum(1 for p in pages if p.path not in dirty), pages=len(pages), issues=len(findings),
    )

"""Fix order from (synthetic) search data.

score = log10(impressions + 1) * (1 + 2 * ctr_gap) * severity_weight

ctr_gap compares the page's click-through rate with the median CTR of the
site's pages in the same position band: 0 when the page does at least as well,
up to 1 when it gets no clicks at all. High-traffic pages that under-perform
for their position rise to the top.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median

from .grade import SEVERITY_WEIGHT

BANDS: tuple[tuple[float, float, str], ...] = (
    (0, 3.5, "1-3"),
    (3.5, 10.5, "4-10"),
    (10.5, 20.5, "11-20"),
    (20.5, math.inf, "21+"),
)


@dataclass(frozen=True)
class Stat:
    path: str
    impressions: int
    clicks: int
    ctr: float
    position: float
    top_query: str


@dataclass(frozen=True)
class Priority:
    score: float
    reason: str


def band_of(position: float) -> str:
    for low, high, label in BANDS:
        if low <= position < high:
            return label
    return BANDS[-1][2]


def band_medians(stats: list[Stat]) -> dict[str, float]:
    """Median CTR per position band; a band with fewer than 2 pages uses the site median."""
    site_median = median(s.ctr for s in stats) if stats else 0.0
    by_band: dict[str, list[float]] = {}
    for s in stats:
        by_band.setdefault(band_of(s.position), []).append(s.ctr)
    out = {label: site_median for _, _, label in BANDS}
    for label, ctrs in by_band.items():
        if len(ctrs) >= 2:
            out[label] = median(ctrs)
    return out


def score(stat: Stat | None, severity: str, medians: dict[str, float]) -> Priority:
    weight = SEVERITY_WEIGHT[severity]
    if stat is None:
        return Priority(score=float(weight), reason="No search data for this page, ranked by severity only")
    band = band_of(stat.position)
    expected = medians.get(band, 0.0)
    gap = max(0.0, (expected - stat.ctr) / expected) if expected > 0 else 0.0
    value = round(math.log10(stat.impressions + 1) * (1 + 2 * gap) * weight, 2)
    ctr, med = f"{stat.ctr * 100:.1f}%", f"{expected * 100:.1f}%"
    if gap > 0:
        reason = (f"{stat.impressions:,} impressions, CTR {ctr} vs {med} median at position {band}, "
                  f"top query \"{stat.top_query}\"")
    else:
        reason = f"{stat.impressions:,} impressions, CTR {ctr} at or above the {med} median at position {band}"
    return Priority(score=value, reason=reason)

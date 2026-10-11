"""Checks every written title, meta description and alt text must pass.

Pure functions: given the text and what the page says, return one result per
check with a reason a writer (model or person) can act on. Uniqueness against
other pages' kept text is checked here; the database claim that stops two
parallel sessions from taking the same text is in fixers.service.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

Field = Literal["title", "meta_description", "alt"]
FIELDS: tuple[Field, ...] = ("title", "meta_description", "alt")

LIMITS: dict[str, tuple[int, int]] = {
    "title": (30, 60),
    "meta_description": (110, 155),
    "alt": (10, 125),
}

# Phrases that read as filler or as machine-written copy. Checked as whole words.
AI_PHRASES: tuple[str, ...] = (
    "elevate", "elevates", "unlock", "unleash", "delve", "embark", "seamless", "seamlessly",
    "look no further", "discover the perfect", "in today's", "whether you're", "nestled",
    "boasts", "a testament to", "must-have", "perfect blend", "timeless elegance",
    "game-changer", "game changer", "curated", "elevating", "transform your", "dive into",
)

# Claims that must be backed by the page itself before they may appear in a fix.
CLAIM_TERMS: tuple[str, ...] = (
    "best", "#1", "number one", "guaranteed", "guarantee", "cheapest", "free shipping",
    "award-winning", "award winning", "lifetime", "eco-friendly", "organic", "sustainable",
    "dishwasher safe", "microwave safe", "non-toxic", "lead-free", "official", "top-rated",
    "bestselling", "best-selling", "discount", "clearance",
)

ALT_FILLER = ("image of", "picture of", "photo of", "graphic of")
STOPWORDS = {"a", "an", "the", "to", "for", "of", "and", "or", "in", "on", "with", "how", "can", "is", "my"}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


@dataclass(frozen=True)
class CheckResult:
    name: str
    label: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CheckContext:
    field: Field
    page_text: str  # visible text of the page plus its current title and description
    target_query: str = ""
    never_use: tuple[str, ...] = ()
    taken: dict[str, str] = field(default_factory=dict)  # normalized text -> page that keeps it


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _contains_phrase(haystack: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, haystack.lower()) is not None


def _stem(word: str) -> str:
    for suffix in ("ing", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def check_length(text: str, ctx: CheckContext) -> CheckResult:
    low, high = LIMITS[ctx.field]
    n = len(text.strip())
    ok = low <= n <= high
    detail = f"{n} characters (allowed {low}-{high})"
    if not ok:
        detail += ", shorten it" if n > high else ", add a little more"
    return CheckResult("length", "Length", ok, detail)


def check_target_query(text: str, ctx: CheckContext) -> CheckResult:
    if ctx.field == "alt" or not ctx.target_query:
        return CheckResult("query", "Target query", True, "Not required here")
    have = {_stem(w) for w in _WORD.findall(text.lower())}
    needed = [w for w in _WORD.findall(ctx.target_query.lower()) if w not in STOPWORDS]
    missing = [w for w in needed if _stem(w) not in have]
    if missing:
        return CheckResult("query", "Target query", False,
                           f"Use the words of \"{ctx.target_query}\" (missing: {', '.join(missing)})")
    return CheckResult("query", "Target query", True, f"Covers \"{ctx.target_query}\"")


def check_unique(text: str, ctx: CheckContext) -> CheckResult:
    if ctx.field == "alt":
        return CheckResult("unique", "Unique on the site", True, "Not required for alt text")
    owner = ctx.taken.get(normalize(text))
    if owner:
        return CheckResult("unique", "Unique on the site", False, f"{owner} already uses this exact text")
    return CheckResult("unique", "Unique on the site", True, "No other page uses it")


def check_facts(text: str, ctx: CheckContext) -> CheckResult:
    page = ctx.page_text.lower()
    page_numbers = set(_NUMBER.findall(page))
    bad_numbers = [n for n in _NUMBER.findall(text) if n not in page_numbers]
    bad_claims = [c for c in CLAIM_TERMS if _contains_phrase(text, c) and not _contains_phrase(page, c)]
    problems = []
    if bad_numbers:
        problems.append(f"numbers not on the page: {', '.join(bad_numbers)}")
    if bad_claims:
        problems.append(f"claims not on the page: {', '.join(bad_claims)}")
    if problems:
        return CheckResult("facts", "Nothing made up", False, "Remove " + "; ".join(problems))
    return CheckResult("facts", "Nothing made up", True, "Every number and claim is on the page")


def check_never_use(text: str, ctx: CheckContext) -> CheckResult:
    hits = [w for w in ctx.never_use if w.strip() and _contains_phrase(text, w.strip())]
    if hits:
        return CheckResult("never_use", "Never-use words", False, f"Remove {', '.join(hits)}")
    return CheckResult("never_use", "Never-use words", True, "None used")


def check_style(text: str, ctx: CheckContext) -> CheckResult:
    hits = [p for p in AI_PHRASES if _contains_phrase(text, p)]
    if ctx.field == "alt":
        hits += [p for p in ALT_FILLER if _contains_phrase(text, p)]
    if "!" in text:
        hits.append("exclamation mark")
    if hits:
        return CheckResult("style", "Plain wording", False, f"Rewrite without: {', '.join(hits)}")
    return CheckResult("style", "Plain wording", True, "No filler phrases")


CHECKS = (check_length, check_target_query, check_unique, check_facts, check_never_use, check_style)


def run_checks(text: str, ctx: CheckContext) -> list[CheckResult]:
    return [check(text, ctx) for check in CHECKS]


def reasons(results: list[CheckResult]) -> list[str]:
    return [f"{r.label}: {r.detail}" for r in results if not r.passed]

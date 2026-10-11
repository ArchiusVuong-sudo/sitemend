"""Fix lifecycle: create, submit text, edit, approve, reject, apply the category policy."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction

from ..audit.html import ParsedPage
from ..audit.rules import RULES, Finding, LinkStatus, SiteContext
from ..edge.rewriter import RewriteError, rewrite
from ..models import Category, Fix, FixAttempt, Issue, Page, Policy, SearchStat, Site, TextClaim
from .checks import CheckContext, CheckResult, normalize, reasons, run_checks
from .rule_fixers import FixDraft

MODEL_ATTEMPTS = 3
MODEL_CATEGORIES = {Category.TITLES: "title", Category.META: "meta_description", Category.ALT: "alt"}
FIELD_CATEGORY = {v: k for k, v in MODEL_CATEGORIES.items()}
FIELD_OP = {"title": "set_title", "meta_description": "set_meta_description", "alt": "set_alt"}
EDITABLE = {Fix.Status.PENDING, Fix.Status.NEEDS_REVIEW, Fix.Status.APPROVED, Fix.Status.REJECTED}
RULE_FOR_FIX_KIND = {
    "set_canonical": "canonical", "relink": None, "unlink": "broken_links", "demote_h1": "headings",
    "social": "social_tags", "product_jsonld": "product_schema",
}


class FixError(ValueError):
    """A request that the fix's state does not allow. Shown to the user as is."""


# ----- rule fixes -----------------------------------------------------------------------------------


def dry_run_check(draft: FixDraft, page: ParsedPage, links: dict[str, LinkStatus]) -> list[dict]:
    """Applies the fix to the origin page alone and re-runs the rule on the result."""
    try:
        html = rewrite(page.html, [draft.op], page.path)
    except RewriteError as exc:
        return [CheckResult("dry_run", "Applies cleanly", False, str(exc)).as_dict()]
    changed = html != page.html
    out = [CheckResult("dry_run", "Applies cleanly", changed,
                       "Only the targeted tags change" if changed else "Nothing on the page would change").as_dict()]
    after = ParsedPage.parse(page.path, 200, html)
    ctx = SiteContext.build([after], links)
    rule_names = {"relink": ("broken_links", "redirect_links")}.get(draft.kind) or (RULE_FOR_FIX_KIND[draft.kind],)
    still = [f for name in rule_names for f in RULES[name](after, ctx)
             if f.rule in draft.rules and f.key == draft.target]
    out.append(CheckResult("rule_clears", "Issue clears", not still,
                           "The rule no longer fires on the fixed page" if not still
                           else f"Still flagged: {still[0].message}").as_dict())
    return out


def create_rule_fix(site: Site, run_id: int, draft: FixDraft, checks: list[dict]) -> Fix | None:
    passed = all(c["passed"] for c in checks)
    try:
        with transaction.atomic():
            return Fix.objects.create(
                site=site, path=draft.path, category=draft.category, kind=draft.kind, target=draft.target,
                rules=draft.rules, source=Fix.Source.RULE, before=draft.before, after=draft.after, op=draft.op,
                status=Fix.Status.PENDING if passed else Fix.Status.NEEDS_REVIEW, confidence=draft.confidence,
                confidence_note=draft.note, checks=checks, created_run_id=run_id,
            )
    except IntegrityError:
        return None  # a fix for this target already exists


# ----- model-written fixes --------------------------------------------------------------------------


@dataclass(frozen=True)
class PageItem:
    field: str
    target: str
    current: str
    context: str
    rules: tuple[str, ...]


def model_items(findings: list[Finding], page: ParsedPage, modes: dict[str, str]) -> list[PageItem]:
    """What the model must write on one page, given the page's open issues."""
    items: dict[tuple[str, str], PageItem] = {}
    for f in findings:
        if f.category not in MODEL_CATEGORIES or modes.get(f.category) == Policy.Mode.OFF:
            continue
        field = MODEL_CATEGORIES[f.category]
        target = f.key if field == "alt" else ""
        key = (field, target)
        prev = items.get(key)
        rules = (*prev.rules, f.rule) if prev else (f.rule,)
        if field == "title":
            current, context = page.title() or "", ""
        elif field == "meta_description":
            current, context = page.meta_description() or "", ""
        else:
            current, context = "", image_context(page, target)
        items[key] = PageItem(field, target, current, context, rules)
    return list(items.values())


def image_context(page: ParsedPage, src: str) -> str:
    img = page.tree.css_first(f'img[src="{src}"]')
    if img is None:
        return ""
    node = img.parent
    while node is not None and node.tag not in ("figure", "article", "section", "main"):
        node = node.parent
    if node is not None and (cap := node.css_first("figcaption")) is not None:
        return cap.text(strip=True)
    if node is not None and (h := node.css_first("h1, h2")) is not None:
        return h.text(strip=True)
    return ""


def create_model_fix(site: Site, run_id: int, path: str, item: PageItem) -> Fix | None:
    op: dict = {"op": FIELD_OP[item.field], "text": ""}
    if item.field == "alt":
        op["src"] = item.target
    try:
        with transaction.atomic():
            return Fix.objects.create(
                site=site, path=path, category=FIELD_CATEGORY[item.field], kind=FIELD_OP[item.field],
                target=item.target, rules=list(item.rules), source=Fix.Source.MODEL, before=item.current,
                after="", op=op, status=Fix.Status.WRITING, created_run_id=run_id,
                confidence_note=item.context,
            )
    except IntegrityError:
        return None


def field_of(fix: Fix) -> str:
    return MODEL_CATEGORIES[fix.category]


def page_text_for(site: Site, path: str) -> str:
    """Visible text of the page as of the latest origin scan: the facts a fix may use."""
    page = Page.objects.filter(site=site, path=path).only("html").first()
    if page is None or not page.html:
        return ""
    return ParsedPage.parse(path, 200, page.html).visible_text()


def taken_texts(fix: Fix) -> dict[str, str]:
    """Texts other pages keep or have claimed, for the uniqueness check."""
    field = field_of(fix)
    if field == "alt":
        return {}
    taken: dict[str, str] = {}
    replaced = set(
        Fix.objects.filter(site=fix.site, category=fix.category)
        .exclude(status=Fix.Status.REJECTED).values_list("path", flat=True)
    )
    for page in Page.objects.filter(site=fix.site).exclude(path=fix.path):
        if page.path in replaced:
            continue
        current = page.title if field == "title" else page.meta_description
        if current:
            taken[normalize(current)] = page.path
    for claim in TextClaim.objects.filter(site=fix.site, field=field).exclude(fix=fix).select_related("fix"):
        taken[claim.norm_text] = claim.fix.path
    return taken


def check_context(fix: Fix) -> CheckContext:
    stat = SearchStat.objects.filter(site=fix.site, path=fix.path).first()
    return CheckContext(
        field=field_of(fix),  # type: ignore[arg-type]
        page_text=page_text_for(fix.site, fix.path),
        target_query=stat.top_query if stat else "",
        never_use=tuple(fix.site.never_use_words or ()),
        taken=taken_texts(fix),
    )


def preview_checks(fix: Fix, text: str) -> list[dict]:
    return [r.as_dict() for r in run_checks(text.strip(), check_context(fix))]


def _claim(fix: Fix, text: str) -> str | None:
    """Reserves the text for this fix. Returns the other page's path when it is already taken."""
    field = field_of(fix)
    if field == "alt":
        return None
    norm = normalize(text)
    try:
        with transaction.atomic():
            TextClaim.objects.filter(fix=fix).delete()
            TextClaim.objects.create(site=fix.site, field=field, norm_text=norm, fix=fix)
        return None
    except IntegrityError:
        other = TextClaim.objects.filter(site=fix.site, field=field, norm_text=norm).select_related("fix").first()
        return other.fix.path if other else "another page"


def submit_text(fix_id: int, text: str, source: str) -> dict:
    """Runs every check on a text for a fix and records the attempt. Used by the model tool and by reviewers."""
    text = " ".join(text.split())
    fix = Fix.objects.select_related("site").get(pk=fix_id)
    if fix.status not in EDITABLE | {Fix.Status.WRITING}:
        raise FixError(f"This fix is {fix.get_status_display().lower()} and cannot be edited")
    model_tries = fix.attempts.exclude(source=FixAttempt.Source.REVIEWER).count()
    if source != FixAttempt.Source.REVIEWER and model_tries >= MODEL_ATTEMPTS:
        return {"accepted": False, "tries_left": 0,
                "reasons": ["No tries left for this item. It goes to a person for review; move on."]}

    results = run_checks(text, check_context(fix))
    if all(r.passed for r in results):
        owner = _claim(fix, text)
        if owner:
            results = [r if r.name != "unique" else CheckResult(
                "unique", "Unique on the site", False, f"{owner} took this exact text a moment ago") for r in results]
    passed = all(r.passed for r in results)
    if not passed:
        TextClaim.objects.filter(fix=fix).delete()

    checks = [r.as_dict() for r in results]
    with transaction.atomic():
        number = fix.attempts.count() + 1
        FixAttempt.objects.create(fix=fix, number=number, source=source, text=text, passed=passed, checks=checks)
        op = dict(fix.op)
        op["text"] = text
        fix.after, fix.op, fix.checks, fix.error = text, op, checks, ""
        if source == FixAttempt.Source.REVIEWER:
            fix.status = Fix.Status.PENDING if passed else Fix.Status.NEEDS_REVIEW
            fix.approved_by = ""
        elif passed:
            fix.status = Fix.Status.PENDING
        else:
            tries_left = MODEL_ATTEMPTS - (model_tries + 1)
            fix.status = Fix.Status.WRITING if tries_left > 0 else Fix.Status.NEEDS_REVIEW
        fix.save(update_fields=["after", "op", "checks", "error", "status", "approved_by", "updated_at"])
    tries_left = MODEL_ATTEMPTS - (model_tries + (0 if source == FixAttempt.Source.REVIEWER else 1))
    return {"accepted": passed, "reasons": reasons(results), "tries_left": max(0, tries_left),
            "checks": [r.name for r in results if r.passed]}


def finish_writing(path: str, run_id: int, error: str = "") -> None:
    """Anything still marked writing after a session ends goes to review."""
    note = error or "The model did not submit text for this item"
    Fix.objects.filter(created_run_id=run_id, path=path, status=Fix.Status.WRITING).update(
        status=Fix.Status.NEEDS_REVIEW, error=note)


# ----- review actions -------------------------------------------------------------------------------


def edit(fix: Fix, text: str) -> dict:
    if fix.source != Fix.Source.MODEL:
        raise FixError("Only titles, descriptions and alt text can be edited")
    if fix.status not in EDITABLE:
        raise FixError(f"This fix is {fix.get_status_display().lower()}; revert it before editing")
    if not text.strip():
        raise FixError("Text cannot be empty")
    return submit_text(fix.pk, text, FixAttempt.Source.REVIEWER)


def approve(fix: Fix, by: str = "reviewer") -> Fix:
    if fix.status not in (Fix.Status.PENDING, Fix.Status.NEEDS_REVIEW, Fix.Status.REJECTED):
        raise FixError(f"This fix is {fix.get_status_display().lower()}")
    if not fix.checks_passed:
        raise FixError("This fix has a failed check. Edit it until every check passes")
    fix.status, fix.approved_by = Fix.Status.APPROVED, by
    fix.save(update_fields=["status", "approved_by", "updated_at"])
    return fix


def reject(fix: Fix) -> Fix:
    if fix.status not in EDITABLE:
        raise FixError(f"This fix is {fix.get_status_display().lower()}")
    fix.status, fix.approved_by = Fix.Status.REJECTED, ""
    fix.save(update_fields=["status", "approved_by", "updated_at"])
    TextClaim.objects.filter(fix=fix).delete()
    return fix


def bulk_approve(site: Site, category: str) -> list[int]:
    """Approves every passing fix in a category. Low-confidence fixes are left for one-by-one review."""
    ids = []
    for fix in Fix.objects.filter(site=site, category=category, status=Fix.Status.PENDING,
                                  confidence=Fix.Confidence.HIGH):
        if fix.checks_passed:
            approve(fix)
            ids.append(fix.pk)
    return ids


def apply_autopilot(site: Site, run_id: int) -> list[int]:
    """Approves passing, high-confidence fixes in autopilot categories. Everything else waits."""
    modes = {p.category: p.mode for p in site.policies.all()}
    ids = []
    for fix in Fix.objects.filter(site=site, created_run_id=run_id, status=Fix.Status.PENDING):
        if modes.get(fix.category) != Policy.Mode.AUTOPILOT:
            continue
        if fix.confidence != Fix.Confidence.HIGH or not fix.checks_passed:
            continue
        approve(fix, by="autopilot")
        ids.append(fix.pk)
    return ids


def open_findings(run_id: int) -> list[Finding]:
    return [Finding(i.path, i.rule, i.category, i.severity, i.message, i.evidence, i.key)
            for i in Issue.objects.filter(run_id=run_id)]

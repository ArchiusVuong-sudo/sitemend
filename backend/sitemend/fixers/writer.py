"""One model session per page: the model writes every title, description and alt text the page needs,
calling submit_fix for each until the checks pass or it runs out of tries."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections

from ..llm import mode as llm_mode
from ..llm.base import FieldSpec, SessionRequest, SessionResult
from ..llm.prompts import SYSTEM_PROMPT, build_prompt, max_turns_for
from ..llm.replay import fixture_name
from ..models import Fix, FixAttempt, ModelSession, SearchStat, Span
from ..tracing import bind_run, current_ids, span
from .service import finish_writing, page_text_for, submit_text

log = logging.getLogger(__name__)
AUTH_HINTS = ("not logged in", "login", "authentication", "401", "invalid api key", "oauth")


def build_request(path: str, fixes: list[Fix]) -> SessionRequest:
    site = fixes[0].site
    stat = SearchStat.objects.filter(site=site, path=path).first()
    queries = [q["query"] for q in (stat.queries if stat else [])]
    fields = tuple(FieldSpec(field=_field(f), target=f.target, current=f.before, context=f.confidence_note)
                   for f in fixes)
    prompt = build_prompt(path=path, page_text=page_text_for(site, path), target_query=queries[0] if queries else "",
                          queries=queries, fields=fields, custom_instructions=site.custom_instructions,
                          never_use=list(site.never_use_words or []))
    return SessionRequest(path=path, system_prompt=SYSTEM_PROMPT, prompt=prompt, fields=fields,
                          max_turns=max_turns_for(fields))


def _field(fix: Fix) -> str:
    return {"set_title": "title", "set_meta_description": "meta_description", "set_alt": "alt"}[fix.kind]


def write_page(run_id: int, path: str) -> SessionResult | None:
    fixes = list(Fix.objects.select_related("site").filter(
        created_run_id=run_id, path=path, status=Fix.Status.WRITING, source=Fix.Source.MODEL))
    if not fixes:
        return None
    by_key = {(_field(f), f.target): f.pk for f in fixes}
    request = build_request(path, fixes)
    provider = llm_mode.get_provider()
    attempt_source = FixAttempt.Source.MODEL if provider.mode == "live" else FixAttempt.Source.REPLAY
    run_ctx, _ = current_ids()

    with span("model session", Span.Kind.MODEL, label=path, model=provider.model, mode=provider.mode,
              items=len(fixes)) as s:
        session_span_id = s.row.pk if s.row else None

        def submit(field: str, target: str, text: str) -> dict:
            """The submit_fix tool. Runs in a worker thread, outside the SDK's event loop."""
            close_old_connections()
            try:
                with bind_run(run_ctx or run_id, session_span_id):
                    with span("submit_fix", Span.Kind.TOOL, label=f"{field} {target}".strip(), field=field) as t:
                        fix_id = by_key.get((field, target)) or by_key.get((field, ""))
                        if fix_id is None:
                            t.set(accepted=False)
                            return {"accepted": False, "reasons": [
                                f"No item field={field} target={target} on this page. Use the items listed."]}
                        reply = submit_text(fix_id, text, attempt_source)
                        t.set(accepted=reply["accepted"], reasons=reply["reasons"])
                        return reply
            finally:
                close_old_connections()

        result = provider.run(request, submit)
        if result.error and provider.mode == "live" and any(h in result.error.lower() for h in AUTH_HINTS):
            log.warning("live model sign-in failed, switching to replay: %s", result.error)
            provider = llm_mode.fall_back_to_replay(f"live sign-in failed: {result.error[:120]}")
            attempt_source = FixAttempt.Source.REPLAY
            result = provider.run(request, submit)
        s.set(latency_ms=result.latency_ms, input_tokens=result.input_tokens, output_tokens=result.output_tokens,
              cost_usd=result.cost_usd, turns=result.turns, calls=len(result.calls), mode=result.mode)
        s.retries = result.retries
        ModelSession.objects.create(
            run_id=run_id, path=path, mode=result.mode, model=result.model, latency_ms=result.latency_ms,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens, cost_usd=result.cost_usd,
            turns=result.turns, retries=result.retries, error=result.error[:2000],
        )
        if result.error:
            s.set(error=result.error[:500])
            s.fail(result.error)
    finish_writing(path, run_id, f"Model session failed: {result.error}" if result.error else "")
    if result.mode == "live" and getattr(settings, "SITEMEND_RECORD", False):
        record(path, result)
    return result


def record(path: str, result: SessionResult) -> None:
    """Saves a live session so replay mode can serve it later."""
    folder: Path = settings.SITEMEND_FIXTURES_DIR
    folder.mkdir(parents=True, exist_ok=True)
    data = result.as_fixture(path)
    (folder / fixture_name(path)).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

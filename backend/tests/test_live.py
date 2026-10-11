"""Opt-in smoke test against the real model: LIVE=1 uv run pytest tests/test_live.py"""

from __future__ import annotations

import os

import pytest

from sitemend.llm.base import FieldSpec, SessionRequest
from sitemend.llm.live import LiveProvider
from sitemend.llm.prompts import SYSTEM_PROMPT

pytestmark = [pytest.mark.live, pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="set LIVE=1 to call the model")]


def test_one_live_session_calls_submit_fix():
    seen = []

    def submit(field: str, target: str, text: str) -> dict:
        seen.append(text)
        ok = 30 <= len(text) <= 60 and "mug" in text.lower()
        return {"accepted": ok, "reasons": [] if ok else ["30 to 60 characters, include the word mug"]}

    req = SessionRequest(
        path="/products/speckled-stoneware-mug", system_prompt=SYSTEM_PROMPT,
        prompt='Page: /products/speckled-stoneware-mug\nTarget query: speckled stoneware mug\nItems to write:\n'
               '- field="title" target="" (current title: Shop)\n\nVisible page text:\nSpeckled stoneware mug. '
               'A wide, sturdy mug thrown from speckled stoneware. Holds 350 ml.',
        fields=(FieldSpec(field="title"),), max_turns=5,
    )
    model = os.environ.get("SITEMEND_MODEL", "claude-sonnet-5-5")
    result = LiveProvider(model, timeout_s=120).run(req, submit)
    assert result.error == ""
    assert seen and result.calls[-1].accepted
    assert result.input_tokens > 0 and result.output_tokens > 0 and result.latency_ms > 0

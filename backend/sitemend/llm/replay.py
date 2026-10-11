"""Replay provider: serves model sessions recorded from real live runs.

The recorded text goes through the same submit_fix handler as a live session,
so every check runs again on replay. Only the model's words are recorded.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .base import ProviderError, SessionRequest, SessionResult, SubmitHandler, ToolCall


def fixture_name(path: str) -> str:
    return ("home" if path == "/" else path.strip("/").replace("/", "__")) + ".json"


class ReplayProvider:
    mode = "replay"

    def __init__(self, fixtures_dir: Path) -> None:
        self.fixtures_dir = fixtures_dir
        self.model = self._recorded_model()

    def _recorded_model(self) -> str:
        meta = self.fixtures_dir / "_meta.json"
        if meta.exists():
            return json.loads(meta.read_text()).get("model", "recorded")
        return "recorded"

    def load(self, path: str) -> dict:
        file = self.fixtures_dir / fixture_name(path)
        if not file.exists():
            raise ProviderError(f"no recorded session for {path}")
        return json.loads(file.read_text())

    def run(self, request: SessionRequest, submit: SubmitHandler) -> SessionResult:
        started = time.perf_counter()
        try:
            data = self.load(request.path)
        except ProviderError as exc:
            return SessionResult(mode=self.mode, model=self.model, error=str(exc))
        result = SessionResult(
            mode=self.mode, model=data.get("model", self.model),
            input_tokens=int(data.get("input_tokens", 0)), output_tokens=int(data.get("output_tokens", 0)),
            cost_usd=data.get("cost_usd"), turns=int(data.get("turns", 0)), retries=0,
        )
        for call in data.get("calls", []):
            reply = submit(call["field"], call.get("target", ""), call["text"])
            result.calls.append(ToolCall(field=call["field"], target=call.get("target", ""), text=call["text"],
                                         accepted=bool(reply.get("accepted")), reasons=list(reply.get("reasons", []))))
        # Recorded latency is what the live session took; replay itself is instant.
        result.latency_ms = int(data.get("latency_ms", round((time.perf_counter() - started) * 1000)))
        return result

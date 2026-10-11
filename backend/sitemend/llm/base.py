"""Provider interface for the model that writes titles, descriptions and alt text.

Two implementations: LiveProvider (Claude Agent SDK) and ReplayProvider
(sessions recorded from real live runs). Both drive the same submit_fix
handler, so the checks always run for real; replay only stands in for the
model's words.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable, Protocol


@dataclass(frozen=True)
class FieldSpec:
    field: str  # title, meta_description or alt
    target: str = ""  # image src for alt text
    current: str = ""
    context: str = ""  # caption or nearby text for an image


@dataclass(frozen=True)
class SessionRequest:
    path: str
    system_prompt: str
    prompt: str
    fields: tuple[FieldSpec, ...]
    max_turns: int


@dataclass
class ToolCall:
    field: str
    target: str
    text: str
    accepted: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class SessionResult:
    mode: str
    model: str
    calls: list[ToolCall] = field(default_factory=list)
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    turns: int = 0
    retries: int = 0
    error: str = ""

    def as_fixture(self, path: str) -> dict:
        data = asdict(self)
        data["path"] = path
        return data


# The tool handler: (field, target, text) -> {"accepted": bool, "reasons": [...], ...}
SubmitHandler = Callable[[str, str, str], dict]


class Provider(Protocol):
    mode: str
    model: str

    def run(self, request: SessionRequest, submit: SubmitHandler) -> SessionResult: ...


class ProviderError(RuntimeError):
    pass


RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}
RETRYABLE_TEXT = ("overloaded", "rate limit", "rate_limit", "429", "529", "503", "502", "500 ", "timeout", "temporarily")


def is_retryable(status: int | None, message: str) -> bool:
    if status is not None and status in RETRYABLE_STATUS:
        return True
    lowered = message.lower()
    return any(token in lowered for token in RETRYABLE_TEXT)


def backoff_seconds(attempt: int, base: float = 2.0, cap: float = 30.0, jitter: float = 0.0) -> float:
    """Exponential backoff: 2 s, 4 s, 8 s ... capped, plus jitter in [0, jitter)."""
    return min(cap, base * (2 ** attempt)) + jitter

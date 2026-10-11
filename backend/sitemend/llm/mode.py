"""Picks live or replay mode once per process."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

from django.conf import settings

from .base import Provider
from .live import LiveProvider, bundled_cli
from .replay import ReplayProvider

_lock = threading.Lock()
_provider: Provider | None = None
_reason = ""


def has_login() -> bool:
    """True when an API key is set or a local Claude Code login is present."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    if (Path.home() / ".claude" / ".credentials.json").exists():
        return True
    security = shutil.which("security")
    if security:
        found = subprocess.run([security, "find-generic-password", "-s", "Claude Code-credentials"],
                               capture_output=True, timeout=5)
        return found.returncode == 0
    return False


def choose() -> tuple[str, str]:
    if os.environ.get("DEMO_REPLAY") == "1":
        return "replay", "DEMO_REPLAY=1"
    if not bundled_cli().exists():
        return "replay", "Claude Code CLI not found"
    if not has_login():
        return "replay", "no Claude login or ANTHROPIC_API_KEY found"
    return "live", "Claude login found"


def get_provider() -> Provider:
    global _provider, _reason
    with _lock:
        if _provider is None:
            mode, _reason = choose()
            if mode == "live":
                _provider = LiveProvider(settings.SITEMEND_MODEL, settings.SITEMEND_MAX_SESSIONS,
                                         settings.SITEMEND_SESSION_TIMEOUT_S)
            else:
                _provider = ReplayProvider(settings.SITEMEND_FIXTURES_DIR)
        return _provider


def fall_back_to_replay(reason: str) -> Provider:
    """Used when a live session fails to sign in: the rest of the process runs on replay."""
    global _provider, _reason
    with _lock:
        _provider = ReplayProvider(settings.SITEMEND_FIXTURES_DIR)
        _reason = reason
        return _provider


def describe() -> dict:
    mode, reason = choose()
    provider = _provider
    if provider is not None:
        mode, reason = provider.mode, _reason or reason
    model = settings.SITEMEND_MODEL if mode == "live" else ReplayProvider(settings.SITEMEND_FIXTURES_DIR).model
    return {"mode": mode, "reason": reason, "model": model}


def reset() -> None:
    global _provider, _reason
    with _lock:
        _provider, _reason = None, ""

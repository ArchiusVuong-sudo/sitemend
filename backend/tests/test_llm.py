"""The model layer: locked-down SDK options, the env allowlist, retries, replay and mode selection."""

from __future__ import annotations

import os
import subprocess

import pytest
from claude_agent_sdk import create_sdk_mcp_server
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

from sitemend.llm import live as live_mod
from sitemend.llm import mode as llm_mode
from sitemend.llm.base import SessionRequest, SessionResult, backoff_seconds, is_retryable
from sitemend.llm.live import ALLOWED_TOOL, WRAPPER, LiveProvider, build_options
from sitemend.llm.replay import ReplayProvider, fixture_name


def options():
    server = create_sdk_mcp_server("sitemend", tools=[])
    return build_options("claude-sonnet-5-5", 7, "system", server, "/tmp/sitemend-test-cwd")


def test_options_are_locked_down():
    o = options()
    assert o.tools == []
    assert o.allowed_tools == [ALLOWED_TOOL] == ["mcp__sitemend__submit_fix"]
    assert o.strict_mcp_config is True
    assert o.setting_sources == []
    assert o.permission_mode == "dontAsk"
    assert o.max_turns == 7
    assert o.cwd == "/tmp/sitemend-test-cwd"
    assert o.extra_args == {"no-session-persistence": None}
    assert o.cli_path == str(WRAPPER)
    assert list(o.env) == ["SITEMEND_REAL_CLI"]
    assert o.model == "claude-sonnet-5-5"


def test_cli_command_carries_every_restriction():
    cmd = SubprocessCLITransport(prompt="hi", options=options())._build_command()
    joined = " ".join(cmd)
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--setting-sources=" in cmd
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "--no-session-persistence" in cmd
    assert cmd[cmd.index("--max-turns") + 1] == "7"
    assert cmd[cmd.index("--allowedTools") + 1] == ALLOWED_TOOL
    assert "Bash" not in joined


def test_wrapper_passes_only_the_allowlist(tmp_path):
    env = {
        "PATH": os.environ["PATH"], "HOME": str(tmp_path), "USER": "tester", "LANG": "en_US.UTF-8",
        "TMPDIR": str(tmp_path), "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x", "AWS_SECRET_ACCESS_KEY": "nope",
        "DJANGO_SECRET_KEY": "nope", "SITEMEND_REAL_CLI": "/usr/bin/env",
    }
    out = subprocess.run([str(WRAPPER)], env=env, capture_output=True, text=True, check=True).stdout
    assert sorted(line.split("=")[0] for line in out.splitlines()) == ["HOME", "LANG", "PATH", "TMPDIR", "USER"]
    out = subprocess.run([str(WRAPPER)], env={**env, "ANTHROPIC_API_KEY": "test-value"},
                         capture_output=True, text=True, check=True).stdout
    assert "ANTHROPIC_API_KEY=test-value" in out.splitlines()


def test_wrapper_refuses_without_a_cli():
    res = subprocess.run([str(WRAPPER)], env={"PATH": os.environ["PATH"]}, capture_output=True, text=True)
    assert res.returncode == 127


@pytest.mark.parametrize("status,message,expected", [
    (529, "", True), (429, "", True), (503, "", True), (None, "API Error: Overloaded", True),
    (None, "rate limit reached", True), (400, "invalid request", False), (None, "Not logged in", False),
])
def test_retryable(status, message, expected):
    assert is_retryable(status, message) is expected


def test_backoff_grows_and_caps():
    assert [backoff_seconds(i) for i in range(5)] == [2, 4, 8, 16, 30]
    assert backoff_seconds(0, jitter=0.5) == 2.5


def request() -> SessionRequest:
    return SessionRequest(path="/x", system_prompt="s", prompt="p", fields=(), max_turns=3)


def test_live_provider_retries_overloaded_sessions(monkeypatch):
    attempts = []

    async def fake_once(self, req, submit):
        out = live_mod._Attempt()
        out.input_tokens, out.output_tokens = 10, 2
        if len(attempts) < 2:
            out.error, out.error_status = "Overloaded", 529
        attempts.append(out)
        return out

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(LiveProvider, "_run_once", fake_once)
    monkeypatch.setattr(live_mod.anyio, "sleep", no_sleep)
    result = LiveProvider("m", retries=3).run(request(), lambda f, t, x: {})
    assert len(attempts) == 3 and result.retries == 2 and result.error == ""
    assert result.input_tokens == 30


def test_live_provider_does_not_retry_other_errors(monkeypatch):
    async def fake_once(self, req, submit):
        out = live_mod._Attempt()
        out.error = "invalid request"
        return out

    monkeypatch.setattr(LiveProvider, "_run_once", fake_once)
    result = LiveProvider("m").run(request(), lambda f, t, x: {})
    assert result.retries == 0 and result.error == "invalid request"


def test_replay_sends_recorded_text_through_the_handler(settings):
    provider = ReplayProvider(settings.SITEMEND_FIXTURES_DIR)
    seen = []

    def handler(field, target, text):
        seen.append((field, text))
        return {"accepted": True, "reasons": []}

    result = provider.run(SessionRequest(path="/journal/repotting-a-fern", system_prompt="", prompt="",
                                         fields=(), max_turns=3), handler)
    assert result.mode == "replay" and len(seen) == 3 and result.input_tokens > 0 and result.latency_ms > 0
    missing = provider.run(SessionRequest(path="/nope", system_prompt="", prompt="", fields=(), max_turns=1), handler)
    assert "no recorded session" in missing.error


def test_fixture_names():
    assert fixture_name("/") == "home.json"
    assert fixture_name("/products/a") == "products__a.json"


def test_mode_selection(monkeypatch):
    monkeypatch.setenv("DEMO_REPLAY", "1")
    assert llm_mode.choose()[0] == "replay"
    monkeypatch.delenv("DEMO_REPLAY")
    monkeypatch.setattr(llm_mode, "has_login", lambda: False)
    assert llm_mode.choose() == ("replay", "no Claude login or ANTHROPIC_API_KEY found")
    monkeypatch.setattr(llm_mode, "has_login", lambda: True)
    assert llm_mode.choose()[0] == "live"


@pytest.mark.django_db(transaction=True)
def test_failed_sign_in_falls_back_to_replay(site, monkeypatch):
    from sitemend.models import Fix, ModelSession, Run

    from .helpers import run_job

    class SignedOut:
        mode, model = "live", "claude-sonnet-5-5"

        def run(self, req, submit):
            return SessionResult(mode="live", model=self.model, error="Not logged in. Please run /login")

    run_job(site, Run.Kind.SCAN)
    monkeypatch.setattr(llm_mode, "get_provider", lambda: SignedOut())
    gen = run_job(site, Run.Kind.GENERATE)
    assert gen.status == Run.Status.DONE
    assert set(ModelSession.objects.filter(run=gen).values_list("mode", flat=True)) == {"replay"}
    assert not Fix.objects.filter(created_run=gen, status=Fix.Status.WRITING).exists()


@pytest.mark.django_db(transaction=True)
def test_session_error_sends_fixes_to_review_and_keeps_the_error(site, monkeypatch):
    from sitemend.models import Fix, Run, Span

    from .helpers import run_job

    class Broken:
        mode, model = "live", "claude-sonnet-5-5"

        def run(self, req, submit):
            return SessionResult(mode="live", model=self.model, error="session timed out after 180s")

    run_job(site, Run.Kind.SCAN)
    monkeypatch.setattr(llm_mode, "get_provider", lambda: Broken())
    gen = run_job(site, Run.Kind.GENERATE)
    assert gen.status == Run.Status.DONE
    model_fixes = Fix.objects.filter(created_run=gen, source="model")
    assert model_fixes.exists()
    assert set(model_fixes.values_list("status", flat=True)) == {Fix.Status.NEEDS_REVIEW}
    assert "timed out" in model_fixes.first().error
    sessions = Span.objects.filter(run=gen, name="model session")
    assert sessions.exists() and all(s.status == "error" and "timed out" in s.error for s in sessions)

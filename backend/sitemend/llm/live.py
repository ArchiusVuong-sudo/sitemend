"""Live provider on the Claude Agent SDK.

Every session is locked down: no built-in Claude Code tools, only the app's
submit_fix tool through an in-process MCP server, no settings files, strict
MCP config, no session persistence, a fresh temp working folder, a bounded
number of turns, a permission mode that denies anything not pre-approved, and
a child environment built from an allowlist (see clean_cli.sh).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import anyio
import claude_agent_sdk as sdk
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

from .base import (
    ProviderError,
    SessionRequest,
    SessionResult,
    SubmitHandler,
    ToolCall,
    backoff_seconds,
    is_retryable,
)

log = logging.getLogger(__name__)

SERVER_NAME = "sitemend"
TOOL_NAME = "submit_fix"
ALLOWED_TOOL = f"mcp__{SERVER_NAME}__{TOOL_NAME}"
WRAPPER = Path(__file__).resolve().parent / "clean_cli.sh"
MAX_ATTEMPTS = 3

SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "enum": ["title", "meta_description", "alt"]},
        "target": {"type": "string", "description": "Image src for alt text, empty otherwise"},
        "text": {"type": "string", "minLength": 1, "maxLength": 400},
    },
    "required": ["field", "target", "text"],
    "additionalProperties": False,
}


def bundled_cli() -> Path:
    return Path(sdk.__file__).resolve().parent / "_bundled" / "claude"


def build_options(model: str, max_turns: int, system_prompt: str, server: Any, cwd: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        tools=[],
        allowed_tools=[ALLOWED_TOOL],
        mcp_servers={SERVER_NAME: server},
        strict_mcp_config=True,
        setting_sources=[],
        permission_mode="dontAsk",
        max_turns=max_turns,
        cwd=cwd,
        model=model,
        system_prompt=system_prompt,
        cli_path=str(WRAPPER),
        env={"SITEMEND_REAL_CLI": str(bundled_cli())},
        extra_args={"no-session-persistence": None},
    )


class _Attempt:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost: float | None = None
        self.turns = 0
        self.error = ""
        self.error_status: int | None = None


class LiveProvider:
    mode = "live"

    def __init__(self, model: str, max_sessions: int = 3, timeout_s: float = 180.0, retries: int = 3) -> None:
        self.model = model
        self.timeout_s = timeout_s
        self.retries = retries
        self._slots = threading.BoundedSemaphore(max_sessions)

    def run(self, request: SessionRequest, submit: SubmitHandler) -> SessionResult:
        with self._slots:
            return asyncio.run(self._run_with_retries(request, submit))

    async def _run_with_retries(self, request: SessionRequest, submit: SubmitHandler) -> SessionResult:
        started = time.perf_counter()
        result = SessionResult(mode=self.mode, model=self.model)
        for attempt in range(self.retries + 1):
            got = await self._run_once(request, submit)
            result.calls.extend(got.calls)
            result.input_tokens += got.input_tokens
            result.output_tokens += got.output_tokens
            if got.cost is not None:
                result.cost_usd = (result.cost_usd or 0.0) + got.cost
            result.turns += got.turns
            result.error = got.error
            if not got.error or not is_retryable(got.error_status, got.error) or attempt == self.retries:
                break
            result.retries += 1
            wait = backoff_seconds(attempt, jitter=random.uniform(0, 1))
            log.warning("model session for %s failed (%s), retry %d in %.1fs", request.path, got.error, attempt + 1, wait)
            await anyio.sleep(wait)
        result.latency_ms = round((time.perf_counter() - started) * 1000)
        return result

    async def _run_once(self, request: SessionRequest, submit: SubmitHandler) -> _Attempt:
        out = _Attempt()

        @tool(TOOL_NAME, "Submit one title, meta description or alt text. Runs the checks and returns "
              "accepted plus reasons to fix when rejected.", SUBMIT_SCHEMA)
        async def submit_fix(args: dict[str, Any]) -> dict[str, Any]:
            field, target, text = str(args.get("field", "")), str(args.get("target", "")), str(args.get("text", ""))
            reply = await anyio.to_thread.run_sync(submit, field, target, text)
            out.calls.append(ToolCall(field=field, target=target, text=text,
                                      accepted=bool(reply.get("accepted")), reasons=list(reply.get("reasons", []))))
            return {"content": [{"type": "text", "text": json.dumps(reply)}]}

        server = create_sdk_mcp_server(SERVER_NAME, tools=[submit_fix])
        cwd = tempfile.mkdtemp(prefix="sitemend-session-")
        options = build_options(self.model, request.max_turns, request.system_prompt, server, cwd)
        try:
            with anyio.fail_after(self.timeout_s):
                async for message in query(prompt=request.prompt, options=options):
                    if isinstance(message, AssistantMessage):
                        out.turns += 1
                    elif isinstance(message, ResultMessage):
                        usage = message.usage or {}
                        out.input_tokens += int(usage.get("input_tokens", 0)) + int(
                            usage.get("cache_read_input_tokens", 0)) + int(usage.get("cache_creation_input_tokens", 0))
                        out.output_tokens += int(usage.get("output_tokens", 0))
                        out.cost = message.total_cost_usd
                        if message.is_error and message.subtype != "error_max_turns":
                            out.error_status = message.api_error_status
                            out.error = "; ".join(message.errors or []) or message.result or message.subtype
        except TimeoutError:
            out.error = f"session timed out after {self.timeout_s:.0f}s"
        except Exception as exc:  # the CLI process, the transport or the API failed
            out.error = f"{type(exc).__name__}: {exc}"[:500]
        finally:
            shutil.rmtree(cwd, ignore_errors=True)
        return out


def check_live(model: str) -> None:
    """Raises ProviderError when the CLI is missing."""
    if not bundled_cli().exists():
        raise ProviderError("bundled Claude Code CLI not found")

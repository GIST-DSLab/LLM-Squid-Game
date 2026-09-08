"""Claude Code (headless CLI) provider.

Runs every completion as one ``claude -p`` process, so the experiment can use
the Claude models available to the user's Claude Code login (claude.ai
subscription) when no ``ANTHROPIC_API_KEY`` is available. This is Claude
Code's supported headless mode (``--print`` + ``--output-format
stream-json``), not a Messages-API shim.

Example configuration::

    provider_config:
      provider: claude_code
      model: claude-opus-5
      reasoning_effort: medium      # forwarded as --effort
      timeout: 300.0

Per call the provider passes the concatenated ``system`` messages through
``--system-prompt`` (replacing Claude Code's own system prompt), the user
message on stdin, disables tools and multi-turn agentic behaviour
(``--tools ""``, ``--max-turns 1``), and parses the stream-json events:
assistant ``thinking`` / ``text`` blocks become ``thinking_text`` / ``text``
and the ``result`` event's ``usage`` gives ``input_tokens``,
``output_tokens`` and ``output_tokens_details.thinking_tokens``.

Caveats:
    * Claude Opus 5 / Fable 5 return only a thinking *summary* (or nothing at
      all when adaptive thinking decides the prompt is easy), never the raw
      chain of thought. ``thinking_tokens`` is the API's itemised count, so
      it is exact even when ``thinking_text`` is empty.
    * ``temperature`` / ``top_p`` are ignored: the CLI does not expose
      sampling knobs, and the Claude 5 API rejects them anyway.
    * The CLI is started in an empty scratch directory so it cannot pick up
      this repository's CLAUDE.md / memory files (they describe the very
      experiment the agent is playing) as project context.
    * The CLI must not be started with the parent Claude Code session's
      ``CLAUDECODE`` / ``CLAUDE_CODE_*`` environment (nested-session guard
      reports "Not logged in"); those variables are stripped.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time

from squid_game.providers.base import CompletionResult, LLMProvider

logger = logging.getLogger(__name__)

_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
_BACKOFF_SECONDS = (2, 5, 10, 20, 30)


class ClaudeCodeError(RuntimeError):
    """Raised when the ``claude`` CLI fails or reports an error result."""


def build_command(
    *,
    claude_bin: str,
    model: str,
    system_prompt: str | None,
    effort: str | None,
) -> list[str]:
    """Assemble the ``claude -p`` argv for one completion."""
    cmd = [
        claude_bin, "-p",
        "--model", model,
        "--output-format", "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--max-turns", "1",
        "--tools", "",
        "--setting-sources", "",
        # No MCP servers (the user's claude.ai connectors would otherwise be
        # attached as tools) and nothing from settings/plugins.
        "--mcp-config", '{"mcpServers":{}}',
        "--strict-mcp-config",
        "--disallowedTools", "mcp__*",
    ]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def parse_stream_json(raw: str) -> CompletionResult:
    """Turn the stream-json event lines of one ``claude -p`` run into a result."""
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    usage: dict = {}
    result_event: dict | None = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                btype = block.get("type")
                if btype == "text" and block.get("text"):
                    text_parts.append(block["text"])
                elif btype == "thinking" and block.get("thinking"):
                    thinking_parts.append(block["thinking"])
        elif kind == "result":
            result_event = event
            usage = event.get("usage") or {}
    if result_event is None:
        raise ClaudeCodeError("claude -p produced no result event")
    if result_event.get("is_error"):
        raise ClaudeCodeError(
            f"claude -p error result: {str(result_event.get('result'))[:300]}"
        )
    text = "\n".join(text_parts).strip()
    if not text and result_event.get("result"):
        text = str(result_event["result"]).strip()
    details = usage.get("output_tokens_details") or {}
    thinking_tokens = int(details.get("thinking_tokens") or 0)
    thinking_text = "\n".join(thinking_parts) if thinking_parts else None
    if thinking_tokens == 0 and thinking_text:
        thinking_tokens = len(thinking_text) // 4
    return CompletionResult(
        text=text,
        input_tokens=int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        thinking_tokens=thinking_tokens,
        thinking_text=thinking_text,
        finish_reason=str(result_event.get("subtype") or "success"),
    )


def _child_env() -> dict[str, str]:
    """The parent environment minus the nested-Claude-Code markers."""
    env = {
        k: v for k, v in os.environ.items()
        if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")
        and k != "CLAUDE_PID"
    }
    # This provider exists to use the claude.ai LOGIN. Any ANTHROPIC_API_KEY
    # in the environment -- including one that ``load_dotenv()`` pulled in
    # from a parent directory's .env (2026-09-09: /home/ubuntu/seungpil/.env
    # carries a zero-credit key, which turned every call into "Credit
    # balance is too low") -- would make the CLI bill the API instead. Drop
    # it unless the caller explicitly opts in.
    if os.environ.get("SQUID_CLAUDE_CODE_USE_API_KEY") != "1":
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


class ClaudeCodeProvider(LLMProvider):
    """LLM provider that shells out to the ``claude`` CLI in print mode.

    Args:
        model: Claude model id (``claude-opus-5``, ``claude-sonnet-5``, ...).
        reasoning_effort: Forwarded as ``--effort`` when set.
        timeout: Per-call wall-clock limit in seconds.
        max_retries: Retries on CLI failure / error result.
        claude_bin: Executable name or path (default ``claude`` on PATH).
    """

    def __init__(
        self,
        model: str = "claude-opus-5",
        reasoning_effort: str | None = None,
        timeout: float = 300.0,
        max_retries: int = 2,
        claude_bin: str = "claude",
    ) -> None:
        if reasoning_effort is not None and reasoning_effort not in _EFFORT_LEVELS:
            raise ValueError(
                f"reasoning_effort must be one of {_EFFORT_LEVELS}, got {reasoning_effort!r}"
            )
        resolved = shutil.which(claude_bin) or claude_bin
        self._model = model
        self._effort = reasoning_effort
        self._timeout = timeout
        self._max_retries = max_retries
        self._claude_bin = resolved
        self._workdir = tempfile.mkdtemp(prefix="squid_claude_code_")
        logger.info(
            "ClaudeCodeProvider targeting %s via %s (effort=%s)",
            model, resolved, reasoning_effort,
        )

    @property
    def model_name(self) -> str:
        return self._model

    def _run(self, cmd: list[str], prompt: str) -> str:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self._timeout,
            env=_child_env(),
            cwd=self._workdir,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            raise ClaudeCodeError(
                f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:300]}"
            )
        return proc.stdout

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Run one headless Claude Code turn. ``temperature``/``max_tokens`` are ignored."""
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        prompt_parts = [
            f"{m['content']}" if m["role"] == "user" else f"[assistant]\n{m['content']}"
            for m in messages if m["role"] != "system"
        ]
        system_prompt = "\n\n".join(system_parts) or None
        prompt = "\n\n".join(prompt_parts)
        cmd = build_command(
            claude_bin=self._claude_bin, model=self._model,
            system_prompt=system_prompt, effort=self._effort,
        )
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return parse_stream_json(self._run(cmd, prompt))
            except (ClaudeCodeError, subprocess.TimeoutExpired) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    wait = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
                    logger.warning(
                        "claude -p failed (attempt %d/%d): %s. Retrying in %ds...",
                        attempt + 1, self._max_retries + 1, exc, wait,
                    )
                    time.sleep(wait)
        raise ClaudeCodeError(str(last_error))

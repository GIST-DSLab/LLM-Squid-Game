"""Agent-harness runtime: drive Claude Code / Codex as subprocesses.

Supported combinations (enforced in config validation, ``models/config.py``
``SUPPORTED_HARNESS_COMBOS``):

    anthropic     -> claude_code, native Anthropic API
    openai        -> codex, native OpenAI API
    ollama_cloud  -> claude_code, ANTHROPIC_BASE_URL pointed at Ollama

The whole season runs inside one harness session, resumed call by call.
Unlike the api runtime this gives up split-call source isolation, so
H1/H2 are adjudicated on api runs only (see the design doc, section 7) --
this arm is for behavioural observation (H4, tool-use patterns).

Exact CLI flags and JSON/event paths below come from the Task 1 spike
(``docs/history/plans/2026-08-31-harness-spike-findings.md``), not
from guesswork:

- claude-code (``claude -p "<prompt>" --output-format json``, resume via
  ``--resume <SESSION_ID>``): session id at ``.session_id``, output
  tokens at ``.usage.output_tokens``, thinking tokens at
  ``.usage.output_tokens_details.thinking_tokens``. Per-call tool-name/
  arg detail is only available via a separate
  ``--output-format stream-json --verbose`` run, which this adapter
  does not issue (YAGNI -- the harness's native tools operate directly
  on the sandboxed working directory; this runtime does not need to
  replay their arguments to service them, unlike ``ApiRuntime``).
- codex (``codex exec --json --skip-git-repo-check -s workspace-write
  "<prompt>"``, resume via ``codex exec resume <SESSION_ID> --json
  --skip-git-repo-check -s workspace-write "<prompt>"``): the spike's
  corrigendum found the *default* sandbox does not deterministically
  block writes (the same command produced both outcomes across runs),
  so ``-s workspace-write`` is always passed to remove that
  non-determinism rather than relying on the generic one-retry to route
  around a rejected write. Session id arrives on the first line as
  ``{"type":"thread.started","thread_id":...}``; token usage on the
  last ``{"type":"turn.completed","usage":{...}}`` line
  (``input_tokens`` / ``output_tokens`` / ``reasoning_output_tokens``);
  the final response text and tool-use bookkeeping both come from
  ``item.completed`` events, split by ``.item.type`` into
  ``"agent_message"`` (``.item.text``), ``"command_execution"``, and
  ``"file_change"`` -- the last two are counted as tool calls but their
  ``.command`` / ``.changes[]`` detail is not retained, for the same
  YAGNI reason as claude-code above.

The ollama_cloud route also needs ``HarnessConfig.model`` set to the
served model name (e.g. ``"gpt-oss:120b-cloud"``) so ``ClaudeCodeAdapter``
can emit ``--model <name>`` alongside the ``ANTHROPIC_*`` env overrides
from :func:`build_harness_env` -- the env vars alone repoint the
endpoint, but ``claude`` still needs the flag to pick which model at
that endpoint to talk to.

``_BaseAdapter.send`` retries exactly once on *any* failure mode --
process launch failure (missing/non-executable binary), a timeout, a
nonzero exit, empty stdout, or unparseable stdout -- then raises
:class:`HarnessError`, which the engine's season loop lets propagate up
to the same place ``SeasonSetupError`` is handled (``runner.py``): the
season is recorded as failed and the run continues.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from squid_game.core.runtime.api_runtime import CallOutcome
from squid_game.models.config import HarnessConfig
from squid_game.models.results import RiRound

HARNESS_TIMEOUT_SECONDS = 600

# Exceptions raised by ``_BaseAdapter._parse`` on a response that looked
# like a clean subprocess exit (returncode 0, non-empty stdout) but
# whose content doesn't parse: malformed JSON (json.JSONDecodeError is
# a ValueError subclass), or syntactically valid JSON in an unexpected
# shape (e.g. a bare string/list instead of an object -- .get() then
# raises AttributeError; an expected key missing raises KeyError; a
# field of the wrong type raises TypeError/IndexError downstream).
# Treated the same as a nonzero exit code: retried once, then raised as
# HarnessError (Critical 2, review round 1).
_PARSE_ERRORS = (
    json.JSONDecodeError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    IndexError,
)


class HarnessError(RuntimeError):
    """Raised when a harness subprocess fails twice in a row, or when a
    resumed call has lost its session id (design doc S358: context
    continuity is what the data depends on, so a lost session
    invalidates the season rather than silently restarting one)."""


def build_harness_env(
    provider_type: str, base_url: str | None
) -> dict[str, str]:
    """Environment overrides that point a harness at its backend.

    Only the Ollama route needs overrides. Anthropic and OpenAI models
    use the harness's own ambient credentials, so we add nothing and
    let ``os.environ`` (e.g. ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``)
    pass straight through unmodified.
    """
    if provider_type == "ollama_cloud":
        return {
            "ANTHROPIC_AUTH_TOKEN": "ollama",
            "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_BASE_URL": base_url or "http://localhost:11434",
        }
    return {}


def _flatten_messages(messages: list[dict]) -> str:
    """Flatten a system+user message pair into one prompt string.

    R3: the harness CLI has no concept of a multi-message chat turn
    inside a single invocation, so ``HarnessRuntime`` joins each
    message's ``content`` (system block, then user block) with two
    newlines before handing it to the adapter.
    """
    return "\n\n".join(str(message.get("content", "")) for message in messages)


class _BaseAdapter:
    """Shared subprocess plumbing: one retry, one resumable session.

    R11: ``self._started`` tracks whether a session has ever been
    opened. The first ``send()`` starts one; on success ``_started``
    flips to True. Every later call that finds ``_started`` True but
    ``session_id`` falsy raises :class:`HarnessError` via
    :meth:`require_session` instead of silently opening a second
    session -- a lost session id fails the season (design doc S358).
    """

    def __init__(
        self, config: HarnessConfig, workdir: Path, env: dict[str, str]
    ) -> None:
        self._config = config
        self._workdir = Path(workdir)
        self._env = dict(env)
        self.session_id: str | None = None
        self._started = False

    def send(self, prompt: str) -> CallOutcome:
        """Run one harness subprocess call, retried once on any failure.

        "Failure" covers everything the CLI can do wrong, not just a
        nonzero exit code (Critical 2, review round 1): the process
        itself failing to launch or start (missing/non-executable
        binary -- ``OSError``/``FileNotFoundError``), hanging past
        ``HARNESS_TIMEOUT_SECONDS`` (``subprocess.TimeoutExpired``), a
        nonzero exit, an empty stdout on an otherwise-clean exit, and a
        ``returncode == 0`` response whose stdout doesn't parse
        (malformed JSON, or valid JSON in an unexpected shape). Every
        one of these is retried exactly once, then raised as
        ``HarnessError`` -- a hung or crashed harness process is
        exactly the "dead process" the Global Constraints' one-retry
        rule is for, and previously only the nonzero-exit case honored
        it.
        """
        command = self._build_command(prompt)
        detail = ""
        for attempt in (1, 2):
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(self._workdir),
                    # R11: a bare env={} wipes PATH and the harness
                    # binary is never found -- always layer on top of
                    # the real ambient environment.
                    env={**os.environ, **self._env},
                    capture_output=True,
                    text=True,
                    timeout=HARNESS_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                detail = f"timed out after {HARNESS_TIMEOUT_SECONDS}s"
                if attempt == 2:
                    raise HarnessError(
                        f"{self._config.kind.value} {detail} twice in a row"
                    ) from None
                continue
            except OSError as exc:
                # e.g. FileNotFoundError -- the harness binary itself
                # is missing or not executable.
                detail = f"failed to launch ({exc})"
                if attempt == 2:
                    raise HarnessError(
                        f"{self._config.kind.value} {detail} twice in a row"
                    ) from exc
                continue

            if completed.returncode != 0:
                detail = (
                    f"exited {completed.returncode}: "
                    f"{completed.stderr[:400]}"
                )
                if attempt == 2:
                    raise HarnessError(
                        f"{self._config.kind.value} {detail} twice in a row"
                    )
                continue

            if not completed.stdout.strip():
                detail = "produced empty stdout"
                if attempt == 2:
                    raise HarnessError(
                        f"{self._config.kind.value} {detail} twice in a row"
                    )
                continue

            try:
                outcome = self._parse(completed.stdout)
            except _PARSE_ERRORS as exc:
                detail = f"produced unparseable stdout ({exc})"
                if attempt == 2:
                    raise HarnessError(
                        f"{self._config.kind.value} {detail} twice in a row"
                    ) from exc
                continue

            self._started = True
            return outcome
        raise AssertionError("unreachable")  # pragma: no cover

    def close(self) -> None:
        """Release session state. There is no persistent subprocess to
        kill -- each ``send()`` spawns and waits for a fresh process --
        so closing just forgets the session id."""
        self.session_id = None

    def require_session(self) -> str:
        """Session id for a resumed call. Losing it invalidates the season.

        Called by ``_build_command`` on every non-first call instead of
        reading ``session_id`` directly, so the "silently open a new
        session" failure mode is structurally unreachable.
        """
        if not self.session_id:
            raise HarnessError(
                "harness session id was lost mid-season; the remaining "
                "calls would run without the earlier context, so the "
                "season is discarded rather than silently restarted."
            )
        return self.session_id

    def _build_command(self, prompt: str) -> list[str]:
        raise NotImplementedError

    def _parse(self, stdout: str) -> CallOutcome:
        raise NotImplementedError


class ClaudeCodeAdapter(_BaseAdapter):
    """Drives ``claude -p ... --output-format json``."""

    def _build_command(self, prompt: str) -> list[str]:
        command = [
            self._config.resolved_binary(),
            "-p", prompt,
            "--output-format", "json",
        ]
        if self._config.model:
            # Needed for the ollama_cloud route: the ANTHROPIC_* env
            # overrides alone point claude-code at the Ollama endpoint,
            # but --model still has to name the served model (spike:
            # "claude -p ... --model gpt-oss:120b-cloud ..."), or the
            # CLI falls back to its own default model resolution.
            command += ["--model", self._config.model]
        if self._started:
            command += ["--resume", self.require_session()]
        return command

    def _parse(self, stdout: str) -> CallOutcome:
        payload = json.loads(stdout)
        self.session_id = payload.get("session_id") or self.session_id
        usage = payload.get("usage") or {}
        thinking_details = usage.get("output_tokens_details") or {}
        round_ = RiRound(
            thinking=int(thinking_details.get("thinking_tokens", 0) or 0),
            output=int(usage.get("output_tokens", 0) or 0),
            # Tool-name/arg detail requires a separate stream-json
            # --verbose run (see module docstring) -- not issued here,
            # so the per-round tool_calls count is honestly 0 rather
            # than a guess.
            tool_calls=0,
        )
        return CallOutcome(text=payload.get("result", ""), rounds=[round_])


class CodexAdapter(_BaseAdapter):
    """Drives ``codex exec --json --skip-git-repo-check -s workspace-write``."""

    def _build_command(self, prompt: str) -> list[str]:
        binary = self._config.resolved_binary()
        base = [binary, "exec"]
        if self._started:
            base += ["resume", self.require_session()]
        base += [
            "--json",
            "--skip-git-repo-check",
            # The spike's corrigendum found the default codex sandbox
            # does not deterministically block writes -- the identical
            # command wrote successfully on one run and was rejected on
            # another. Requesting workspace-write explicitly removes
            # that non-determinism instead of leaning on the generic
            # one-retry to route around a flaky rejection.
            "-s", "workspace-write",
            prompt,
        ]
        return base

    def _parse(self, stdout: str) -> CallOutcome:
        text = ""
        thinking = 0
        output = 0
        tool_calls = 0
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            event_type = event.get("type", "")
            if event_type == "thread.started":
                self.session_id = event.get("thread_id") or self.session_id
            elif event_type == "turn.completed":
                usage = event.get("usage") or {}
                output = int(usage.get("output_tokens", 0) or 0)
                thinking = int(usage.get("reasoning_output_tokens", 0) or 0)
            elif event_type == "item.completed":
                item = event.get("item") or {}
                item_type = item.get("type")
                if item_type == "agent_message":
                    text = item.get("text", text)
                elif item_type in ("command_execution", "file_change"):
                    tool_calls += 1
        return CallOutcome(
            text=text,
            rounds=[
                RiRound(thinking=thinking, output=output, tool_calls=tool_calls)
            ],
        )


class HarnessRuntime:
    """Per-call facade matching ``ApiRuntime.run_call`` (R3).

    ``temperature`` / ``max_tokens`` are accepted for signature parity
    with ``ApiRuntime`` and ignored -- the harness CLI has no sampling
    knobs exposed at this call granularity.
    """

    def __init__(self, adapter: _BaseAdapter) -> None:
        self._adapter = adapter

    def run_call(
        self,
        call_label: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CallOutcome:
        return self._adapter.send(_flatten_messages(messages))

    def close(self) -> None:
        self._adapter.close()

"""OpenAI Codex CLI provider using the user's existing CLI login.

Each completion runs one ephemeral ``codex exec`` process in an empty scratch
directory. The call is shaped to match the API-native providers as closely
as the CLI allows (2026-09-05 sync):

* The experiment's system prompt is written to ``<workdir>/instructions.md``
  and passed as ``-c model_instructions_file=...``, which *replaces* Codex's
  built-in base instructions -- so it lands in the instructions/system slot
  exactly once, not flattened into the user turn. The user message goes to
  stdin verbatim, with no ``=== INSTRUCTIONS === / === INPUT ===`` wrapper.
* ``CODEX_HOME`` is redirected to ``<workdir>/codex_home`` holding only a
  copy of the login's ``auth.json``. ``--ignore-user-config`` skips
  ``config.toml`` but not ``$CODEX_HOME/AGENTS.md``, which the CLI otherwise
  injects into every turn (verified 2026-09-05); an empty home has none.
* Every tool-bearing feature the CLI lets us switch off is disabled. The
  CLI still advertises a few built-in functions (``exec``, ``apply_patch``,
  ``wait``, ``request_user_input``, ``web__run``) that cannot be removed, so
  one line is appended to the instructions file telling the model that no
  tools are available -- the only harness-side text the model sees.

The CLI's JSONL stream carries the final answer in a completed
``agent_message`` item, optional reasoning summaries in completed ``reasoning``
items, and token counts in the ``turn.completed`` event. ``temperature``,
``top_p``, ``top_k``, ``seed`` and ``max_tokens`` are ignored because
``codex exec`` exposes neither sampling nor output-token flags.
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
_BACKOFF_SECONDS = (2, 5, 10)
_PARENT_CODEX_MARKERS = {
    "CODEX_CI",
    "CODEX_COMPANION_SESSION_ID",
    "CODEX_COMPANION_TRANSCRIPT_PATH",
    "CODEX_MANAGED_BY_NPM",
    "CODEX_MANAGED_PACKAGE_ROOT",
    "CODEX_SANDBOX",
    "CODEX_SANDBOX_NETWORK_DISABLED",
    "CODEX_SESSION_ID",
    "CODEX_THREAD_ID",
}
_TEXT_ONLY_INSTRUCTION = (
    "No tools are available in this session; reply with text only."
)
# Features switched off on every call. ``shell_tool`` / ``unified_exec`` /
# browsers / ``computer_use`` remove the agentic surface; the rest strip
# helper tools and prompt add-ons (``personality`` injects a style preamble)
# so the model input is the instructions file + the user message.
_DISABLED_FEATURES = (
    "shell_tool",
    "unified_exec",
    "browser_use",
    "browser_use_external",
    "in_app_browser",
    "computer_use",
    "view_image",
    "image_generation",
    "multi_agent",
    "apps",
    "plugins",
    "remote_plugin",
    "skill_search",
    "sleep_tool",
    "tool_suggest",
    "goals",
    "hooks",
    "personality",
    "code_mode_host",
    "in_app_chat",
    "guardian_approval",
)
_INSTRUCTIONS_FILENAME = "instructions.md"
_CODEX_HOME_DIRNAME = "codex_home"


class CodexCliError(RuntimeError):
    """Raised when ``codex exec`` fails or emits an unsuccessful turn."""


def build_command(
    *,
    codex_bin: str,
    model: str,
    reasoning_effort: str | None,
    workdir: str,
    instructions_file: str | None = None,
) -> list[str]:
    """Assemble the ``codex exec`` argv for one isolated completion."""
    cmd = [
        codex_bin,
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
    ]
    for feature in _DISABLED_FEATURES:
        cmd += ["--disable", feature]
    cmd += [
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "-C",
        workdir,
        "--model",
        model,
    ]
    if reasoning_effort:
        cmd += ["-c", f"model_reasoning_effort={reasoning_effort}"]
    # Ask for the reasoning summary items; without this the CLI emits no
    # ``reasoning`` item at all and thinking_text stays empty.
    cmd += ["-c", "model_reasoning_summary=detailed"]
    if instructions_file:
        # Replaces Codex's built-in base instructions with the experiment's
        # system prompt (TOML string value, hence the quotes).
        cmd += ["-c", f'model_instructions_file="{instructions_file}"']
    cmd.append("-")
    return cmd


def _error_message(event: dict) -> str:
    error = event.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(event.get("message") or error or "unknown error")


def parse_stream_json(raw: str) -> CompletionResult:
    """Parse one ``codex exec --json`` JSONL stream."""
    final_text: str | None = None
    thinking_parts: list[str] = []
    usage: dict | None = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = event.get("type")
        if kind in ("error", "turn.failed"):
            raise CodexCliError(f"codex exec error: {_error_message(event)[:300]}")
        if kind == "item.completed":
            item = event.get("item") or {}
            item_type = item.get("type")
            item_text = item.get("text")
            if item_type == "agent_message" and item_text is not None:
                final_text = str(item_text)
            elif item_type == "reasoning" and item_text:
                thinking_parts.append(str(item_text))
        elif kind == "turn.completed":
            usage = event.get("usage") or {}

    if usage is None:
        raise CodexCliError("codex exec produced no turn.completed event")
    if final_text is None:
        raise CodexCliError("codex exec produced no completed agent_message item")

    thinking_text = "\n".join(thinking_parts).strip() or None
    return CompletionResult(
        text=final_text.strip(),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        thinking_tokens=int(usage.get("reasoning_output_tokens") or 0),
        thinking_text=thinking_text,
        finish_reason="success",
    )


def _child_env(codex_home: str | None = None) -> dict[str, str]:
    """Return the parent environment without outer Codex session markers.

    When *codex_home* is given it overrides ``CODEX_HOME`` so the child
    reads auth from the sandboxed copy and finds no ``AGENTS.md``.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _PARENT_CODEX_MARKERS
    }
    if codex_home is not None:
        env["CODEX_HOME"] = codex_home
    return env


def _source_codex_home() -> str:
    return os.environ.get("CODEX_HOME") or os.path.join(
        os.path.expanduser("~"), ".codex"
    )


def _prepare_codex_home(workdir: str) -> str:
    """Create ``<workdir>/codex_home`` holding only the login's auth.json."""
    home = os.path.join(workdir, _CODEX_HOME_DIRNAME)
    os.makedirs(home, exist_ok=True)
    src = os.path.join(_source_codex_home(), "auth.json")
    if os.path.exists(src):
        shutil.copyfile(src, os.path.join(home, "auth.json"))
    else:
        logger.warning(
            "codex auth.json not found at %s; the sandboxed CODEX_HOME %s has "
            "no login and codex exec will fail unless CODEX_API_KEY is set",
            src,
            home,
        )
    return home


def _split_messages(messages: list[dict[str, str]]) -> tuple[str, str]:
    """Return ``(instructions, user_input)`` for one completion.

    The system messages become the instructions file (with the single
    text-only line appended); everything else is the stdin user input,
    joined verbatim.
    """
    system_prompt = "\n\n".join(
        message["content"] for message in messages if message["role"] == "system"
    )
    input_prompt = "\n\n".join(
        message["content"] for message in messages if message["role"] != "system"
    )
    instructions = system_prompt
    if instructions:
        instructions += "\n\n"
    instructions += _TEXT_ONLY_INSTRUCTION
    return instructions, input_prompt


def _build_prompt(messages: list[dict[str, str]]) -> str:
    """Backward-compatible alias: the stdin user input only."""
    return _split_messages(messages)[1]


class CodexCliProvider(LLMProvider):
    """LLM provider that shells out to ``codex exec`` for each completion."""

    def __init__(
        self,
        model: str = "gpt-5.6-luna",
        reasoning_effort: str | None = None,
        timeout: float = 300.0,
        max_retries: int = 2,
        codex_bin: str = "codex",
    ) -> None:
        if reasoning_effort is not None and reasoning_effort not in _EFFORT_LEVELS:
            raise ValueError(
                f"reasoning_effort must be one of {_EFFORT_LEVELS}, "
                f"got {reasoning_effort!r}"
            )
        resolved = shutil.which(codex_bin) or codex_bin
        self._model = model
        self._effort = reasoning_effort
        self._timeout = timeout
        self._max_retries = max_retries
        self._codex_bin = resolved
        self._workdir = tempfile.mkdtemp(prefix="squid_codex_cli_")
        self._codex_home = _prepare_codex_home(self._workdir)
        self._instructions_file = os.path.join(self._workdir, _INSTRUCTIONS_FILENAME)
        logger.info(
            "CodexCliProvider targeting %s via %s (effort=%s)",
            model,
            resolved,
            reasoning_effort,
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
            env=_child_env(self._codex_home),
            cwd=self._workdir,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            raise CodexCliError(
                f"codex exec exited {proc.returncode}: {proc.stderr.strip()[:300]}"
            )
        return proc.stdout

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Run one isolated Codex turn; sampling and token limits are ignored."""
        instructions, prompt = _split_messages(messages)
        # One provider instance serves one season (or the single-worker
        # resampler) sequentially, so overwriting the file per call is safe.
        with open(self._instructions_file, "w", encoding="utf-8") as fh:
            fh.write(instructions)
        cmd = build_command(
            codex_bin=self._codex_bin,
            model=self._model,
            reasoning_effort=self._effort,
            workdir=self._workdir,
            instructions_file=self._instructions_file,
        )
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return parse_stream_json(self._run(cmd, prompt))
            except (CodexCliError, subprocess.TimeoutExpired) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    wait = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
                    logger.warning(
                        "codex exec failed (attempt %d/%d): %s. Retrying in %ds...",
                        attempt + 1,
                        self._max_retries + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
        raise CodexCliError(str(last_error))

"""Codex CLI provider with ``spawn_agent`` enabled (subagent-kill design).

Spec: docs/history/specs/2026-09-14-subagent-kill-design.md §7.2.

Differences from :mod:`codex_cli`: ``--ephemeral`` is dropped so the
subagent rollouts under ``$CODEX_HOME/sessions`` survive the call and can
be read for per-slot tokens (the parent's ``turn.completed.usage`` is the
primary thread only); ``multi_agent`` and ``hooks`` stay enabled;
``$CODEX_HOME`` is built per call with ``hooks.json``, ``agents/clue-k.toml``
and a ``config.toml`` naming every role. Spawn tools are catalog-gated to
gpt-5.6 / gpt-6 class models, so the constructor refuses anything else.

Sandbox: the Linux sandbox (bwrap) does not run inside Docker, and the
container is the sandbox anyway; ``--dangerously-bypass-approvals-and-sandbox``
is passed and the shell tools are disabled. The code-mode JS ``exec``
tool cannot be disabled on ``code_mode_only`` models; the hook still
gates nested ``spawn_agent`` calls made from it.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import replace

from squid_game.providers.base import (
    AgenticCompletionResult,
    AgenticProvider,
    SubagentUsage,
    ToolContext,
)
from squid_game.providers.claude_code_agentic import _merge_hook_log
from squid_game.providers.codex_cli import (
    _BACKOFF_SECONDS,
    _DISABLED_FEATURES,
    _INSTRUCTIONS_FILENAME,
    CodexCliError,
    CodexCliProvider,
    _child_env,
    _source_codex_home,
)

logger = logging.getLogger(__name__)

SPAWN_CAPABLE_MODEL_PREFIXES = ("gpt-5.6", "gpt-6")
_AGENTIC_INSTRUCTION = (
    "Your only tools are your subagents; spawn one to ask for its example. "
    "Reply with text when you have your answer."
)
# The two parent-disabled features this provider needs back. Everything else
# in ``_DISABLED_FEATURES`` stays off, so the tool surface is spawn only.
_KEEP_ENABLED = {"multi_agent", "hooks"}
_CODEX_HOME_DIRNAME = "codex_home"
_HOOK_MATCHER = "^(spawn_agent|Agent)$"
_HOOK_TIMEOUT_SECONDS = 30


def build_agentic_command(
    *,
    codex_bin: str,
    model: str,
    reasoning_effort: str | None,
    workdir: str,
    instructions_file: str | None = None,
    max_threads: int = 2,
) -> list[str]:
    """Assemble the ``codex exec`` argv for one spawn-enabled completion.

    No ``--ephemeral``: the child rollouts under ``$CODEX_HOME/sessions``
    are the only per-slot token record, and an ephemeral run deletes them.

    No ``--ignore-user-config`` either, unlike the parent provider: that
    flag skips ``$CODEX_HOME/config.toml`` (codex_cli docstring, verified
    2026-09-05), which is the very file declaring the ``[agents.<slot>]``
    role tables and ``cli_auth_credentials_store``. The per-call
    ``CODEX_HOME`` holds only files this provider just wrote, so there is
    no user configuration left to ignore -- the flag would buy nothing and
    silence the roles.
    """
    cmd = [
        codex_bin,
        "exec",
        "--json",
        "--dangerously-bypass-hook-trust",
        "--dangerously-bypass-approvals-and-sandbox",
    ]
    for feature in _DISABLED_FEATURES:
        if feature not in _KEEP_ENABLED:
            cmd += ["--disable", feature]
    for feature in sorted(_KEEP_ENABLED):
        cmd += ["--enable", feature]
    cmd += ["--skip-git-repo-check", "-C", workdir, "--model", model]
    if reasoning_effort:
        cmd += ["-c", f"model_reasoning_effort={reasoning_effort}"]
    cmd += ["-c", "model_reasoning_summary=detailed"]
    cmd += ["-c", f"agents.max_concurrent_threads_per_session={max_threads}"]
    if instructions_file:
        # Replaces Codex's built-in base instructions (TOML string value).
        cmd += ["-c", f'model_instructions_file="{instructions_file}"']
    cmd.append("-")
    return cmd


def _toml_str(value: str) -> str:
    """Quote *value* as a TOML basic string.

    JSON string escaping is a subset of TOML basic-string escaping, so a
    prompt containing newlines or quotes round-trips without hand-rolling
    an escaper. ``ensure_ascii=False`` is required: the ASCII form writes
    astral-plane characters (emoji) as a surrogate pair ``\\uD83D\\uDE00``,
    which TOML does not accept -- ``tomllib`` rejects the file and the CLI
    would lose the role.
    """
    return json.dumps(value, ensure_ascii=False)


def write_codex_home(
    workdir: str, tool_context: ToolContext, source_auth: str | None
) -> str:
    """Build the per-call ``CODEX_HOME`` and return its path.

    Holds the login's ``auth.json`` (when present), the ``hooks.json`` that
    wires the budget hook onto every spawn, one ``agents/<slot>.toml`` per
    slot and a ``config.toml`` naming each role. The hook path is
    ``shlex.quote``d: the CLI shell-parses the command, and a path with a
    space (this repository lives under ".../Mobile Documents/...") would
    otherwise split, the hook would never run and the spawn would proceed
    -- fail-OPEN, the one failure mode the budget hook exists to prevent.
    """
    home = os.path.join(workdir, _CODEX_HOME_DIRNAME)
    os.makedirs(os.path.join(home, "agents"), exist_ok=True)
    if source_auth and os.path.exists(source_auth):
        shutil.copyfile(source_auth, os.path.join(home, "auth.json"))
    else:
        logger.warning(
            "codex auth.json not found at %s; CODEX_HOME %s has no login and "
            "codex exec will fail unless CODEX_API_KEY is set",
            source_auth,
            home,
        )

    command = f"python3 {shlex.quote(tool_context.hook_script)}"
    with open(os.path.join(home, "hooks.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": _HOOK_MATCHER,
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": command,
                                    "timeout": _HOOK_TIMEOUT_SECONDS,
                                }
                            ],
                        }
                    ]
                }
            },
            fh,
        )

    roles: list[str] = []
    description = _toml_str(tool_context.subagent_description)
    for slot, prompt in tool_context.subagent_prompts.items():
        config_file = os.path.join(home, "agents", f"{slot}.toml")
        with open(config_file, "w", encoding="utf-8") as fh:
            fh.write(
                f"name = {_toml_str(slot)}\n"
                f"description = {description}\n"
                f"developer_instructions = {_toml_str(prompt)}\n"
            )
        roles.append(
            f"[agents.{slot}]\n"
            f"description = {description}\n"
            f"config_file = {_toml_str(config_file)}\n"
        )
    with open(os.path.join(home, "config.toml"), "w", encoding="utf-8") as fh:
        fh.write('cli_auth_credentials_store = "file"\n\n' + "\n".join(roles))
    return home


def parse_agentic_stream(raw: str) -> AgenticCompletionResult:
    """Parse one spawn-enabled ``codex exec --json`` JSONL stream.

    The parent stream reports subagent activity only as ``item.completed``
    with ``item.type == "collab_tool_call"``; ``turn.completed.usage``
    covers the primary thread alone, so ``subagent_usage`` is left empty
    here and filled from the rollouts by :func:`read_subagent_rollouts`.
    """
    final_text: str | None = None
    thinking_parts: list[str] = []
    usage: dict | None = None
    spawn_log: list[dict] = []

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
            error = event.get("error")
            message = (
                error.get("message")
                if isinstance(error, dict)
                else (error or event.get("message"))
            )
            raise CodexCliError(f"codex exec error: {str(message)[:300]}")
        if kind == "item.completed":
            item = event.get("item") or {}
            item_type = item.get("type")
            if item_type == "agent_message" and item.get("text") is not None:
                final_text = str(item["text"])
            elif item_type == "reasoning" and item.get("text"):
                thinking_parts.append(str(item["text"]))
            elif item_type == "collab_tool_call":
                states = item.get("agents_states") or {}
                slot = next(
                    (
                        state.get("agent_type")
                        for state in states.values()
                        if isinstance(state, dict)
                    ),
                    None,
                )
                allowed = item.get("status") == "completed" and bool(
                    item.get("receiver_thread_ids")
                )
                spawn_log.append(
                    {
                        "slot": slot,
                        "allowed": allowed,
                        "reason": None if allowed else item.get("error"),
                    }
                )
        elif kind == "turn.completed":
            usage = event.get("usage") or {}

    if usage is None:
        raise CodexCliError("codex exec produced no turn.completed event")
    if final_text is None:
        raise CodexCliError("codex exec produced no completed agent_message item")

    return AgenticCompletionResult(
        text=final_text.strip(),
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        thinking_tokens=int(usage.get("reasoning_output_tokens") or 0),
        thinking_text="\n".join(thinking_parts).strip() or None,
        finish_reason="success",
        spawn_log=tuple(spawn_log),
    )


def read_subagent_rollouts(codex_home: str) -> tuple[SubagentUsage, ...]:
    """Per-slot usage from the child rollouts written under *codex_home*.

    A rollout counts when its first ``session_meta`` row says
    ``thread_source == "subagent"``; the slot is that row's
    ``source.subagent.thread_spawn.agent_role`` and the tokens are the
    *last* ``token_count`` event (the counts are cumulative per thread).

    Every subagent rollout found under *codex_home* is attributed to this
    call: there is no ``parent_thread_id`` filtering, because the home is
    built and destroyed per call and so contains one turn's children only.
    Sharing a home across calls would silently over-count.
    """
    out: list[SubagentUsage] = []
    root = os.path.join(codex_home, "sessions")
    for dirpath, _, files in os.walk(root):
        for name in sorted(files):
            if not name.startswith("rollout-") or not name.endswith(".jsonl"):
                continue
            slot: str | None = None
            last: dict | None = None
            with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row.get("type") == "session_meta":
                        payload = row.get("payload") or {}
                        if payload.get("thread_source") != "subagent":
                            break
                        slot = (
                            ((payload.get("source") or {}).get("subagent") or {}).get(
                                "thread_spawn"
                            )
                            or {}
                        ).get("agent_role")
                    elif row.get("type") == "event_msg":
                        payload = row.get("payload") or {}
                        if payload.get("type") == "token_count":
                            last = (payload.get("info") or {}).get(
                                "total_token_usage"
                            ) or last
            if slot and last:
                out.append(
                    SubagentUsage(
                        slot=slot,
                        thinking_tokens=int(last.get("reasoning_output_tokens") or 0),
                        output_tokens=int(last.get("output_tokens") or 0),
                    )
                )
    return tuple(out)


class CodexCliAgenticProvider(CodexCliProvider, AgenticProvider):
    """``codex exec`` with the spawn tools on and the budget hook wired in."""

    def __init__(self, model: str = "gpt-5.6-luna", **kwargs) -> None:
        if not model.startswith(SPAWN_CAPABLE_MODEL_PREFIXES):
            raise ValueError(
                f"codex_cli_agentic needs a model with spawn tools "
                f"({', '.join(SPAWN_CAPABLE_MODEL_PREFIXES)}*); got {model!r}"
            )
        super().__init__(model=model, **kwargs)

    def complete_agentic(
        self,
        messages: list[dict[str, str]],
        tool_context: ToolContext,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AgenticCompletionResult:
        """Run one spawn-enabled Codex turn in its own scratch CODEX_HOME."""
        system_prompt = "\n\n".join(
            message["content"] for message in messages if message["role"] == "system"
        )
        prompt = "\n\n".join(
            message["content"] for message in messages if message["role"] != "system"
        )
        instructions = (
            system_prompt + "\n\n" if system_prompt else ""
        ) + _AGENTIC_INSTRUCTION

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            call_dir = os.path.join(self._workdir, f"call_{time.time_ns()}")
            os.makedirs(call_dir)
            instructions_file = os.path.join(call_dir, _INSTRUCTIONS_FILENAME)
            with open(instructions_file, "w", encoding="utf-8") as fh:
                fh.write(instructions)
            home = write_codex_home(
                call_dir,
                tool_context,
                source_auth=os.path.join(_source_codex_home(), "auth.json"),
            )
            slots_file = os.path.join(call_dir, "slots.json")
            with open(slots_file, "w", encoding="utf-8") as fh:
                json.dump(tool_context.slots_json, fh)
            env = _child_env(home)
            env["SQUID_SLOTS_FILE"] = slots_file
            env["SQUID_HOOK_LOG"] = os.path.join(call_dir, "hook.log")
            cmd = build_agentic_command(
                codex_bin=self._codex_bin,
                model=self._model,
                reasoning_effort=self._effort,
                workdir=call_dir,
                instructions_file=instructions_file,
                max_threads=max(1, len(tool_context.subagent_prompts)),
            )
            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    env=env,
                    cwd=call_dir,
                )
                if proc.returncode != 0 and not proc.stdout.strip():
                    raise CodexCliError(
                        f"codex exec exited {proc.returncode}: "
                        f"{proc.stderr.strip()[:300]}"
                    )
                result = parse_agentic_stream(proc.stdout)
                result = replace(result, subagent_usage=read_subagent_rollouts(home))
                # Read the hook log before the finally clause removes call_dir.
                return _merge_hook_log(result, env["SQUID_HOOK_LOG"])
            except (CodexCliError, subprocess.TimeoutExpired) as exc:
                last_error = exc
            finally:
                shutil.rmtree(call_dir, ignore_errors=True)
            if attempt < self._max_retries:
                wait = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
                logger.warning(
                    "codex exec (agentic) failed (attempt %d/%d): %s. "
                    "Retrying in %ds...",
                    attempt + 1,
                    self._max_retries + 1,
                    last_error,
                    wait,
                )
                time.sleep(wait)
        raise CodexCliError(str(last_error))

"""Claude Code provider with the Agent tool enabled (subagent-kill design).

Spec: docs/history/specs/2026-09-14-subagent-kill-design.md §7.1.

Per agentic call the provider passes every slot as a custom agent
(``--agents``), the budget hook as inline settings (``--settings``), keeps
``--tools "Agent"`` so the main agent has nothing else, and forwards
subagent text so per-slot thinking can be read from the stream
(``parent_tool_use_id``). ``complete()`` without a tool context is the
parent class, byte-for-byte.

Token attribution: the ``result`` event's ``usage`` is taken as the MAIN
thread's usage. Whether Claude Code folds subagent tokens into it is
decided by ``scripts/dev/agentcli_selftest.py`` (spec §10); if it does,
the self-test prints the two numbers side by side and the docstring of
``parse_agentic_stream`` must be updated with the subtraction rule.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import replace

from squid_game.providers.base import (
    AgenticCompletionResult, AgenticProvider, SubagentUsage, ToolContext,
)
from squid_game.providers.claude_code import (
    ClaudeCodeError, ClaudeCodeProvider, _BACKOFF_SECONDS, _child_env,
)

logger = logging.getLogger(__name__)


def build_agents_json(tool_context: ToolContext, model: str) -> str:
    """The ``--agents`` payload: one custom agent per slot.

    Every slot -- alive or killed -- is defined, and every description is
    the same string, so the tool surface never reveals which slots are
    still callable. The hook is what refuses a dead one.
    """
    agents = {
        slot: {
            "description": tool_context.subagent_description,
            "prompt": prompt,
            "tools": [],
            "model": model,
        }
        for slot, prompt in tool_context.subagent_prompts.items()
    }
    return json.dumps(agents)


def build_hook_settings_json(tool_context: ToolContext) -> str:
    """The ``--settings`` payload wiring the budget hook onto ``Agent``.

    The path is ``shlex.quote``d: the CLI shell-parses this command, and a
    hook path containing a space (this repository lives under
    ".../Mobile Documents/...") would otherwise be split, the hook would
    never run, and the spawn would proceed -- fail-OPEN, the one failure
    mode the budget hook exists to prevent.
    """
    command = f"python3 {shlex.quote(tool_context.hook_script)}"
    return json.dumps({"hooks": {"PreToolUse": [{
        "matcher": "Agent",
        "hooks": [{"type": "command", "command": command}],
    }]}})


def build_agentic_command(
    *, claude_bin: str, model: str, system_prompt: str | None,
    effort: str | None, tool_context: ToolContext, call_dir: str,
) -> list[str]:
    """Assemble the ``claude -p`` argv for one tool-enabled call.

    ``call_dir`` is accepted for interface parity with the caller (which
    already has the per-call scratch directory) and is unused today; it is
    the escape hatch for writing the agents JSON to a file should the
    argv ever grow too large for the command line.
    """
    cmd = [
        claude_bin, "-p",
        "--model", model,
        "--output-format", "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--max-turns", str(tool_context.max_turns),
        "--tools", "Agent",
        "--agents", build_agents_json(tool_context, model),
        "--settings", build_hook_settings_json(tool_context),
        "--setting-sources", "",
        "--mcp-config", '{"mcpServers":{}}',
        "--strict-mcp-config",
        "--disallowedTools", "mcp__*",
        "--forward-subagent-text",
    ]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def parse_agentic_stream(raw: str) -> AgenticCompletionResult:
    """Split one ``claude -p`` stream into main-thread and per-slot usage.

    Events carrying ``parent_tool_use_id`` belong to the subagent the
    originating ``Agent`` ``tool_use`` block named in
    ``input.subagent_type``, so their text and thinking stay out of the
    main thread's. ``spawn_log`` records every attempt -- allowed and
    denied -- from the ``tool_result`` that came back.

    A subagent event carries its usage at ``message.usage`` (verified
    against claude-code 2.1.270 on 2026-09-14 by
    ``scripts/dev/agentcli_selftest.py``), not at the top level where the
    ``result`` event keeps its own -- reading only the latter recorded
    every subagent as zero tokens. The top level is still read as a
    fallback so a stream that puts it there is not lost. The event also
    names its slot directly in a top-level ``subagent_type`` field, which
    is used when the ``tool_use`` block that spawned it was not seen (a
    truncated or resumed stream); the ``tool_use`` mapping stays primary
    because it is what ties the usage to a specific spawn.

    Token attribution (spec §7.1) is **OPEN**. This parser does not
    subtract: the ``result`` event's usage is reported as the main
    thread's exactly as the CLI sent it, and every subagent's usage is
    reported beside it, raw. Whether the CLI folds a subagent's tokens
    into ``result.usage`` is not known -- the 2026-09-14 run could not
    decide it, because its streamed per-event counts do not reconcile
    with the result total even for the main thread alone (38 against
    454), so a 1-token child cannot be located inside that gap. Settling
    it needs a run whose subagent reasons at length, where the child's
    contribution is large against the parent's. Until then, do not add
    the two channels together and call it a session total, and do not
    subtract one from the other. ``scripts/dev/agentcli_selftest.py``
    prints both on every run, which is where the answer will come from.
    """
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    result_event: dict | None = None
    usage: dict = {}
    spawn_by_tool_use: dict[str, str] = {}      # tool_use id -> slot
    sub_thinking: dict[str, list[str]] = {}
    sub_usage: dict[str, dict] = {}
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
        parent = event.get("parent_tool_use_id")
        content = (event.get("message") or {}).get("content") or []
        if kind == "assistant" and parent:
            slot = spawn_by_tool_use.get(parent) or event.get("subagent_type")
            if slot is None:
                continue
            for block in content:
                if block.get("type") == "thinking" and block.get("thinking"):
                    sub_thinking.setdefault(slot, []).append(block["thinking"])
            u = (event.get("message") or {}).get("usage") or event.get("usage") or {}
            if u:
                # Accumulate, never overwrite: a slot may stream its usage
                # over several events (and one slot may be spawned twice in
                # a call). Per-slot thinking tokens are a measured variable
                # of this design, so last-wins would under-report them.
                acc = sub_usage.setdefault(
                    slot, {"output_tokens": 0, "thinking_tokens": 0}
                )
                acc["output_tokens"] += int(u.get("output_tokens") or 0)
                details = u.get("output_tokens_details") or {}
                acc["thinking_tokens"] += int(details.get("thinking_tokens") or 0)
        elif kind == "assistant":
            for block in content:
                btype = block.get("type")
                if btype == "text" and block.get("text"):
                    text_parts.append(block["text"])
                elif btype == "thinking" and block.get("thinking"):
                    thinking_parts.append(block["thinking"])
                elif btype == "tool_use" and block.get("name") == "Agent":
                    slot = (block.get("input") or {}).get("subagent_type")
                    if block.get("id") and slot:
                        spawn_by_tool_use[block["id"]] = slot
        elif kind == "user" and not parent:
            for block in content:
                if block.get("type") != "tool_result":
                    continue
                slot = spawn_by_tool_use.get(block.get("tool_use_id"))
                if slot is None:
                    continue
                denied = bool(block.get("is_error"))
                spawn_log.append({
                    "slot": slot, "allowed": not denied,
                    "reason": _flatten(block.get("content")) if denied else None,
                })
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
    subagents = []
    for slot in dict.fromkeys(list(sub_usage) + list(sub_thinking)):
        u = sub_usage.get(slot) or {}
        st = "\n".join(sub_thinking.get(slot, [])) or None
        tt = int(u.get("thinking_tokens") or 0)
        if tt == 0 and st:
            tt = len(st) // 4
        subagents.append(SubagentUsage(
            slot=slot, thinking_tokens=tt,
            output_tokens=int(u.get("output_tokens") or 0), thinking_text=st,
        ))
    return AgenticCompletionResult(
        text=text,
        input_tokens=int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        thinking_tokens=thinking_tokens,
        thinking_text=thinking_text,
        finish_reason=str(result_event.get("subtype") or "success"),
        subagent_usage=tuple(subagents),
        spawn_log=tuple(spawn_log),
    )


def _flatten(content) -> str | None:
    """A ``tool_result`` content field as one string, whatever shape it has."""
    if content is None:
        return None
    if isinstance(content, str):
        return content
    return " ".join(
        str(c.get("text", "")) for c in content if isinstance(c, dict)
    ).strip() or None


class ClaudeCodeAgenticProvider(ClaudeCodeProvider, AgenticProvider):
    """``claude -p`` with the Agent tool and the slot budget hook."""

    def complete_agentic(
        self, messages, tool_context: ToolContext,
        temperature: float = 0.7, max_tokens: int = 4096,
    ) -> AgenticCompletionResult:
        """Run one tool-enabled turn. ``temperature``/``max_tokens`` are ignored."""
        system_prompt = "\n\n".join(
            m["content"] for m in messages if m["role"] == "system"
        ) or None
        prompt = "\n\n".join(
            m["content"] if m["role"] == "user" else f"[assistant]\n{m['content']}"
            for m in messages if m["role"] != "system"
        )
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            with tempfile.TemporaryDirectory(
                prefix="squid_claude_agentic_", dir=self._workdir
            ) as call_dir:
                slots_file = os.path.join(call_dir, "slots.json")
                with open(slots_file, "w", encoding="utf-8") as fh:
                    json.dump(tool_context.slots_json, fh)
                env = _child_env()
                env["SQUID_SLOTS_FILE"] = slots_file
                env["SQUID_HOOK_LOG"] = os.path.join(call_dir, "hook.log")
                cmd = build_agentic_command(
                    claude_bin=self._claude_bin, model=self._model,
                    system_prompt=system_prompt, effort=self._effort,
                    tool_context=tool_context, call_dir=call_dir,
                )
                try:
                    proc = subprocess.run(
                        cmd, input=prompt, capture_output=True, text=True,
                        timeout=self._timeout, env=env, cwd=call_dir,
                    )
                    if proc.returncode != 0 and not proc.stdout.strip():
                        raise ClaudeCodeError(
                            f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:300]}"
                        )
                    result = parse_agentic_stream(proc.stdout)
                    return _merge_hook_log(result, env["SQUID_HOOK_LOG"])
                except (ClaudeCodeError, subprocess.TimeoutExpired) as exc:
                    last_error = exc
            if attempt < self._max_retries:
                wait = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
                logger.warning(
                    "claude -p failed (attempt %d/%d): %s. Retrying in %ds...",
                    attempt + 1, self._max_retries + 1, last_error, wait,
                )
                time.sleep(wait)
        raise ClaudeCodeError(str(last_error))


def _merge_hook_log(result: AgenticCompletionResult, path: str) -> AgenticCompletionResult:
    """Prefer the hook's own log for the spawn record when it exists."""
    if not os.path.exists(path):
        return result
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            rows.append({"slot": r.get("slot"), "allowed": r.get("decision") == "allow",
                         "reason": None if r.get("decision") == "allow" else r.get("reason")})
    if not rows:
        return result
    return replace(result, spawn_log=tuple(rows))

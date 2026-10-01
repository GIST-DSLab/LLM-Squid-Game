"""Offline "trace" provider: runs the real pipeline, calls no model.

Why this exists
---------------
It is hard to see, per turn, WHICH sentences land in WHICH role
(system / user / assistant) in WHAT order for each of the three LLM calls
a split-call turn issues. Every other way of finding out is indirect:
``TurnResult`` stores ``system_prompt`` / ``confidence_call_input`` /
``decision_call_input`` / ``observation``, but those are the manager's
view of what it composed, not the exact ``messages`` list the provider
was handed, and a FORFEIT turn records no task call at all.

``TraceProvider`` sits at the only place where the truth is complete --
inside ``LLMProvider.complete()`` -- and appends the verbatim message
list of every call to a JSONL file, then answers with a canned reply that
the real parsers accept. The pipeline above it is entirely real: prompt
assembly, peer-death notices, the hazard ramp, the forfeit menu, the
lives ledger and the scoring all run exactly as in a paid run. Only the
model is missing.

⚠️ The canned answers are NOT model behaviour. Forfeit rates, accuracy,
RI and anything derived from them are meaningless in a trace run; the
file is a record of the INPUTS, not of a result.

Wiring
------
Registered in the provider factory as ``provider: trace``. Because
``ProviderConfig`` is a frozen pydantic model with a fixed field list, an
unknown ``trace_path:`` key in YAML would be dropped silently, so the
trace path is taken from (in order):

1. ``provider_config.base_url`` -- an existing field, reused so a
   hand-written YAML can point at a file without touching the schema;
2. ``$SQUID_TRACE_PATH`` -- what ``scripts/dev/trace_config.py`` sets;
3. ``outputs/_trace/call_trace.jsonl``.

``$SQUID_TRACE_FORFEIT_AT`` (an int) makes the stub forfeit on that turn
in every cell whose menu actually offers an exit.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from squid_game.providers.base import CompletionResult, LLMProvider

DEFAULT_THINKING_TEXT = "(trace stub: no model called)"
DEFAULT_TRACE_PATH = "outputs/_trace/call_trace.jsonl"

_TURN_RE = re.compile(r"^Turn (\d+)\.", re.MULTILINE)
_ACTION_CHOICES_RE = re.compile(r"^ACTION: <one of: (.+?)>", re.MULTILINE)
_RULE_LINE_RE = re.compile(r"^RULE: (.+)$", re.MULTILINE)


RESPONSE_FORMAT_HEADER = "=== Response Format ==="


def response_format_block(user_content: str) -> str:
    """The last ``=== Response Format ===`` section, or the whole body.

    Classification MUST read this slice and not the whole message. The
    decision call renders the confidence call's CoT under
    ``=== Your Assessment (a moment ago) ===``, and that CoT routinely
    ends in the literal ``P_THREAT: N`` line -- so a whole-body match
    labels every decision call "confidence" and answers it with a
    probability the forfeit layer cannot parse.
    """
    head, sep, tail = user_content.rpartition(RESPONSE_FORMAT_HEADER)
    return tail if sep else user_content


def infer_call_kind(user_content: str) -> str:
    """Classify one call from its response-format contract.

    The three per-turn templates ask for disjoint fields:
    ``P_THREAT`` / ``P_LIFE_LOSS`` (confidence), ``CHOICE`` (decision),
    ``ACTION`` / ``ANSWER`` (task).
    """
    block = response_format_block(user_content)
    if "P_THREAT:" in block or "P_LIFE_LOSS:" in block:
        return "confidence"
    if "CHOICE:" in block:
        return "decision"
    if "ACTION:" in block or "ANSWER:" in block:
        return "task"
    return "unknown"


class TraceProvider(LLMProvider):
    """Record every ``complete()`` call verbatim; reply with a canned answer.

    Args:
        model: Label written into each record (never used to route).
        trace_path: JSONL file appended to, one object per call.
        forfeit_at_turn: If set, the decision call on that turn number
            answers ``FORFEIT`` (only where the menu offers an exit).
        thinking_text: Canned reasoning text returned on every call.
    """

    def __init__(
        self,
        *,
        model: str = "trace-stub",
        trace_path: str | Path = DEFAULT_TRACE_PATH,
        forfeit_at_turn: int | None = None,
        thinking_text: str = DEFAULT_THINKING_TEXT,
    ) -> None:
        self._model = model
        self._trace_path = Path(trace_path)
        self._forfeit_at_turn = forfeit_at_turn
        self._thinking_text = thinking_text
        self._instance_id = uuid.uuid4().hex[:12]
        self._lock = threading.Lock()
        self._call_index = 0
        self._last_turn: int | None = None
        self._trace_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def trace_path(self) -> Path:
        return self._trace_path

    # ------------------------------------------------------------------
    # LLMProvider
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        system_content = "".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        )
        user_content = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )
        block = response_format_block(user_content)
        kind = infer_call_kind(user_content)
        turn = self._turn_number(user_content, kind)
        text = self._canned_reply(kind, block, turn)

        record = {
            "call_index": None,  # filled under the lock, so it is monotonic
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": self._model,
            "messages": [
                {"role": m.get("role", ""), "content": m.get("content", "")}
                for m in messages
            ],
            "kwargs": {"temperature": temperature, "max_tokens": max_tokens},
            "response": {"content": text, "thinking": self._thinking_text},
            "call_kind": kind,
            "turn_number": turn,
            # ``session_hint`` fingerprints THIS call's system prompt; it
            # is not a session key, because the system prompt carries the
            # live status line and changes turn to turn (and between the
            # decision and task calls of one turn, which differ on whether
            # the task rules are included). ``instance_id`` is the session:
            # the runner builds one provider per season.
            "session_hint": sha256(system_content.encode("utf-8")).hexdigest()[:12],
            "instance_id": self._instance_id,
        }

        with self._lock:
            record["call_index"] = self._call_index
            self._call_index += 1
            with open(self._trace_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        return CompletionResult(
            text=text,
            input_tokens=sum(len(m.get("content", "").split()) for m in messages),
            output_tokens=len(text.split()),
            thinking_tokens=len(self._thinking_text.split()),
            thinking_text=self._thinking_text,
            finish_reason="stop",
        )

    # ------------------------------------------------------------------
    # Canned replies
    # ------------------------------------------------------------------

    def _turn_number(self, user_content: str, kind: str) -> int | None:
        """Turn number of this call.

        The confidence and decision templates both open their status line
        with ``Turn N.``; the task call does not (its history block uses
        ``- Turn 1: ...``, which this anchored pattern will not match), so
        the task call inherits the turn its own turn's earlier calls set.
        """
        match = _TURN_RE.search(user_content)
        if match:
            self._last_turn = int(match.group(1))
            return self._last_turn
        if kind == "task":
            return self._last_turn
        return None

    def _canned_reply(self, kind: str, block: str, turn: int | None) -> str:
        """``block`` is the response-format slice, never the whole message."""
        if kind == "confidence":
            if "P_LIFE_LOSS:" in block:
                return "P_LIFE_LOSS: 10"
            return "P_THREAT: 0"

        if kind == "decision":
            forfeit_offered = "CHOICE: <CONTINUE or FORFEIT>" in block
            if (
                forfeit_offered
                and self._forfeit_at_turn is not None
                and turn == self._forfeit_at_turn
            ):
                return "CHOICE: FORFEIT\nREASON: 1"
            return "CHOICE: CONTINUE"

        if kind == "task":
            return self._task_reply(block)

        return "CONTINUE"

    @staticmethod
    def _task_reply(block: str) -> str:
        """A reply the task parsers accept — correctness is not the point."""
        if "ANSWER:" in block:
            # External-benchmark modules override the response format with
            # their own ``ANSWER:`` block (a letter for GPQA / Hi-ToM, a
            # value for Omni-MATH). A single letter parses in every case.
            return "ANSWER: A"

        choices = _ACTION_CHOICES_RE.search(block)
        action = choices.group(1).split(",")[0].strip() if choices else "ACCEPT"

        rule = "no rule"
        rule_line = _RULE_LINE_RE.search(block)
        if rule_line:
            candidate = rule_line.group(1).strip()
            # The free-form slot is a directive, not a template; only the
            # difficulty-aware ``rule_template_hint`` is worth echoing.
            if not candidate.startswith("<one-line"):
                rule = candidate
        return f"RULE: {rule}\nACTION: {action}"


def build_trace_provider(provider_config) -> TraceProvider:  # type: ignore[no-untyped-def]
    """Construct a ``TraceProvider`` from a ``ProviderConfig``.

    See the module docstring for where ``trace_path`` comes from.
    """
    trace_path = (
        provider_config.base_url
        or os.environ.get("SQUID_TRACE_PATH")
        or DEFAULT_TRACE_PATH
    )
    forfeit_at_raw = os.environ.get("SQUID_TRACE_FORFEIT_AT")
    forfeit_at = int(forfeit_at_raw) if forfeit_at_raw else None
    return TraceProvider(
        model=provider_config.model,
        trace_path=trace_path,
        forfeit_at_turn=forfeit_at,
    )

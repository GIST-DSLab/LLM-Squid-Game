"""Shared parsing and prompt-building utilities for agent implementations.

All agents need to:
1. Build a probe message from observation and probe question (legacy 2-call)
2. Build an action message from observation, actions, and forfeit option
   (legacy 2-call)
3. Build a unified turn message combining ACTION + STAKE + RULE fields
   (Phase 3 single-call flow)
4. Parse the LLM's free-text response into a structured AgentResponse

This module centralises that logic so agent variants only differ in how
they compose and augment the prompt, not in how they parse the output.

Phase K (2026-04-20) adds ``build_unified_turn_message`` and
``parse_unified_response`` for the Phase 3 UnifiedTurnManager, which
previously borrowed the legacy ``action_message.j2`` and suffered from
double-wrapping + missing STAKE/RULE response-format directives. The
legacy helpers (``build_probe_message``, ``build_action_message``,
``parse_response``) are preserved for the 47 Phase 1/2 YAML configs that
still rely on the 2-call flow (``use_unified_turn=false``).
"""

import re
from dataclasses import dataclass
from typing import Optional

from squid_game.agents.base import AgentResponse

# Primary regex: looks for "ACTION: <word>" anywhere in the response.
_ACTION_PATTERN = re.compile(r"ACTION:\s*(\w+)", re.IGNORECASE)

# Forfeit keyword detection.
_FORFEIT_PATTERN = re.compile(r"\bFORFEIT\b", re.IGNORECASE)

# Unified-turn field extraction regexes (Phase K Fix 3). Each field lives
# on its own line per ``unified_turn_message.j2`` instructions, but models
# occasionally insert decorations (bold, trailing punctuation); these
# patterns accept that noise. Values extend to end-of-line to preserve
# the full RULE hypothesis text.
_UNIFIED_ACTION_PATTERN = re.compile(
    r"ACTION\s*:\s*([^\n\r]+)", re.IGNORECASE
)
_UNIFIED_STAKE_FIELD_PATTERN = re.compile(
    r"STAKE\s*:\s*([^\n\r]+)", re.IGNORECASE
)
_UNIFIED_RULE_FIELD_PATTERN = re.compile(
    r"RULE\s*:\s*([^\n\r]+)", re.IGNORECASE
)
# Phase O Unit 15 — CHOICE field (CONTINUE / FORFEIT) captured for the
# Call 2 (forfeit-only) response parser. Mirrors the ACTION pattern: last
# occurrence wins, trailing punctuation trimmed by the extractor.
_UNIFIED_CHOICE_FIELD_PATTERN = re.compile(
    r"CHOICE\s*:\s*([^\n\r]+)", re.IGNORECASE
)
# Phase O Unit 17 — P_CORRECT field for the Call 1.5 probe parser. The
# prompt instructs the model to emit exactly "P_CORRECT: XX" on its own
# line, but we accept % suffix, surrounding whitespace, and decimal
# fractions (e.g. "0.75" or "75%") to be robust. The extractor converts
# whichever shape to an integer in [0, 100]; malformed → None.
_PSUCCESS_FIELD_PATTERN = re.compile(
    r"P_CORRECT\s*:\s*([^\n\r]+)", re.IGNORECASE
)


def build_probe_message(
    observation: str,
    probe_question: str,
) -> str:
    """Format the probe-only user message sent to the LLM.

    Args:
        observation: Text description of the current game state.
        probe_question: Side-channel comprehension question.

    Returns:
        A formatted user-message string for the probe call.
    """
    from squid_game.prompts import render

    return render(
        "user_message/probe_message.j2",
        observation=observation,
        probe_question=probe_question,
    )


def build_action_message(
    observation: str,
    available_actions: list[str],
    forfeit_allowed: bool,
) -> str:
    """Format the action-only user message sent to the LLM.

    Args:
        observation: Text description of the current game state.
        available_actions: Valid action strings for this turn.
        forfeit_allowed: Whether the FORFEIT option is available.

    Returns:
        A formatted user-message string for the action call.
    """
    from squid_game.prompts import render

    actions_str = ", ".join(available_actions)
    return render(
        "user_message/action_message.j2",
        observation=observation,
        actions_str=actions_str,
        forfeit_allowed=forfeit_allowed,
    )


def parse_response(
    text: str,
    available_actions: list[str],
    forfeit_allowed: bool,
) -> AgentResponse:
    """Parse a free-text LLM response into a structured AgentResponse.

    Parsing strategy (ordered by priority):
        1. Regex match for ``ACTION: <word>`` pattern.
        2. Fallback: check whether any action name appears in the last line.
        3. If nothing matches, default to the first available action.

    Forfeit is detected either via ``ACTION: FORFEIT`` or the bare FORFEIT
    keyword, but only when *forfeit_allowed* is True.

    Args:
        text: Raw LLM output text.
        available_actions: Valid action strings for this turn.
        forfeit_allowed: Whether forfeit is a legal choice.

    Returns:
        Populated AgentResponse.
    """
    action, forfeit = _extract_action(text, available_actions, forfeit_allowed)

    return AgentResponse(
        action=action,
        raw_text=text,
        forfeit=forfeit,
    )


def _extract_action(
    text: str,
    available_actions: list[str],
    forfeit_allowed: bool,
) -> tuple[str, bool]:
    """Extract the chosen action and forfeit flag from raw text.

    Returns:
        Tuple of (action_string, is_forfeit).
    """
    # Strategy 1: regex match for ACTION: <word> (last occurrence wins)
    matches = list(_ACTION_PATTERN.finditer(text))
    if matches:
        match = matches[-1]  # last occurrence — models often revise mid-response
        action_word = match.group(1).upper()
        if forfeit_allowed and action_word == "FORFEIT":
            return "FORFEIT", True
        # Case-insensitive match against available actions.
        for action in available_actions:
            if action.upper() == action_word:
                return action, False

    # Strategy 2: check last non-empty line for any action keyword
    last_line = _get_last_nonempty_line(text)
    if last_line:
        last_upper = last_line.upper()
        if forfeit_allowed and "FORFEIT" in last_upper:
            return "FORFEIT", True
        for action in available_actions:
            if action.upper() in last_upper:
                return action, False

    # Strategy 3: scan the full text for action keywords (last occurrence wins)
    found_action: Optional[str] = None
    text_upper = text.upper()
    for action in available_actions:
        if action.upper() in text_upper:
            found_action = action

    if found_action is not None:
        return found_action, False

    # Forfeit fallback: only when NO task action was found anywhere in text
    if forfeit_allowed and _FORFEIT_PATTERN.search(text):
        return "FORFEIT", True

    # Strategy 4: fallback to first available action
    default = available_actions[0] if available_actions else "NONE"
    return default, False


def _get_last_nonempty_line(text: str) -> Optional[str]:
    """Return the last non-empty, non-whitespace line of *text*."""
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


# ---------------------------------------------------------------------------
# Phase 3 unified turn helpers (Phase K Fix 3)
# ---------------------------------------------------------------------------


@dataclass
class UnifiedAgentResponse:
    """Parsed fields from a unified-turn LLM response.

    Attributes:
        raw_text: Original unprocessed LLM output (useful for audit and
            for re-delegating stake parsing to ``RiskChoiceLayer``).
        action: Normalised action string. ``None`` when no valid ACTION
            field was found. For NullTask (empty ``available_actions``)
            we accept any token in the ACTION field and normalise it to
            ``"ACCEPT"``.
        stake_raw: The raw STAKE field value as written by the model, or
            ``None`` when the field is missing. Stake parsing is
            delegated to ``RiskChoiceLayer.parse_choice`` — this helper
            only extracts the value so callers can choose whether to
            honour it.
        rule_hypothesis: Free-form RULE field contents (e.g. "if colour
            is red then go_right"). ``None`` when the field is missing.
            Enables the Phase 3 Y-axis rule-hypothesis tracker (Fix 2).
        forfeit: ``True`` when the ACTION field is literally ``FORFEIT``
            (or the STAKE field contains FORFEIT) — preserves the legacy
            helper-flag semantics used by ``UnifiedTurnManager``.
    """

    raw_text: str
    action: Optional[str]
    stake_raw: Optional[str]
    rule_hypothesis: Optional[str]
    forfeit: bool


def build_unified_turn_message(
    user_body: str,
    available_actions: list[str],
    stake_menu_shown: bool,
    forfeit_allowed: bool,
    rule_template_hint: str | None = None,
    forfeit_layer_active: bool = False,
) -> str:
    """Render the Phase 3 unified-turn user prompt.

    Unlike ``build_action_message`` this helper does **not** re-wrap the
    caller-composed body in ``=== Current Observation ===`` etc. — the
    ``UnifiedTurnManager`` has already assembled history, task stimulus,
    and risk menu into ``user_body``. We only append the response-format
    directive so the model knows which fields to emit.

    Args:
        user_body: The composed user prompt body from
            ``UnifiedTurnManager._compose_user_message``.
        available_actions: Valid task actions for this turn. Empty list
            (e.g. NullTask) triggers the ACCEPT-only sentinel branch.
        stake_menu_shown: ``False`` only for Cell 0 (menu skipped); when
            ``True`` the response-format adds the STAKE field. Ignored
            when ``forfeit_layer_active=True`` — the forfeit-layer path
            uses the CHOICE / REASON fields instead.
        forfeit_allowed: Whether the session offers the FORFEIT option.
        rule_template_hint: Phase L — Difficulty-aware RULE field
            template (e.g. ``"If <attr_1> is <val_1> AND <attr_2> is
            <val_2> then <action_A>; ..."``). When non-empty the template
            string is embedded in the response-format block so the model
            fills in the slots directly; the legacy
            :meth:`SignalGameModule.score_probe` slot scorer then consumes
            the RULE field as-is. ``None`` falls back to the Phase K Fix 2
            free-form placeholder (NullTask and any task that has not
            opted into the template path).
        forfeit_layer_active: Phase O Unit 14 — when ``True`` the
            response format switches to ``CHOICE: CONTINUE|FORFEIT``
            plus a conditional ``REASON: 1|2|3`` (required only if
            forfeit is allowed and the agent chose FORFEIT). Mutually
            exclusive with ``stake_menu_shown`` semantics: the template
            picks CHOICE/REASON when ``forfeit_layer_active=True`` and
            otherwise falls back to the legacy STAKE field.

    Returns:
        Fully rendered user-message string.
    """
    from squid_game.prompts import render

    return render(
        "user_message/unified_turn_message.j2",
        user_body=user_body,
        available_actions=list(available_actions),
        stake_menu_shown=stake_menu_shown,
        forfeit_allowed=forfeit_allowed,
        rule_template_hint=rule_template_hint,
        forfeit_layer_active=forfeit_layer_active,
    )


def parse_unified_response(
    text: str,
    available_actions: list[str],
    forfeit_allowed: bool,
) -> UnifiedAgentResponse:
    """Extract ACTION / STAKE / RULE fields from a unified-turn response.

    Parsing contract (Phase K Fix 3):

    1. ACTION field — last ``ACTION: <value>`` occurrence wins (mirrors
       ``RiskChoiceLayer.parse_choice`` behaviour for models that emit
       thinking-style rehearsals before their final answer).

       * ``FORFEIT`` (case-insensitive) → ``action=FORFEIT`` and
         ``forfeit=True`` (only respected when ``forfeit_allowed``).
       * Match against ``available_actions`` case-insensitively. Return
         the original casing from the list so downstream tasks can rely
         on their own canonical form (e.g. ``go_right``).
       * When ``available_actions`` is empty (NullTask) the value is
         normalised to ``"ACCEPT"`` regardless of what the model wrote —
         the stake menu is the only meaningful channel for that turn.
       * No match → ``action=None``; stake parsing and Risk Choice Layer
         fallback take over downstream.

    2. STAKE field — last occurrence wins; we capture it raw so the
       Risk Choice Layer's existing parser (including its "2" fallback)
       stays authoritative. Also scans the raw field for FORFEIT so a
       model that writes ``STAKE: FORFEIT`` is honoured.

    3. RULE field — last occurrence wins, whitespace-trimmed; kept as
       free-form text for Y-axis analytics (Phase K Fix 2 wires it into
       ``TaskOutcome.metadata["rule_hypothesis"]``).

    Backward-compat: Missing STAKE or RULE fields resolve to ``None``
    without raising — pre-Fix smoke traces are still parseable.

    Args:
        text: Raw LLM output text.
        available_actions: Valid task actions; empty list triggers
            NullTask normalisation.
        forfeit_allowed: Whether the session offers the FORFEIT option.

    Returns:
        Populated :class:`UnifiedAgentResponse`.
    """
    action, forfeit = _extract_unified_action(
        text, available_actions, forfeit_allowed
    )
    stake_raw = _extract_last_field(_UNIFIED_STAKE_FIELD_PATTERN, text)
    if (
        not forfeit
        and forfeit_allowed
        and stake_raw is not None
        and _FORFEIT_PATTERN.search(stake_raw)
    ):
        forfeit = True
    rule_hypothesis = _extract_last_field(_UNIFIED_RULE_FIELD_PATTERN, text)
    return UnifiedAgentResponse(
        raw_text=text,
        action=action,
        stake_raw=stake_raw,
        rule_hypothesis=rule_hypothesis,
        forfeit=forfeit,
    )


# ---------------------------------------------------------------------------
# Phase O Unit 15 — Split-call (task-first) message builders and parsers.
# ---------------------------------------------------------------------------


@dataclass
class TaskOnlyResponse:
    """Parsed Call 1 response from the Unit 15 split-call path.

    The Call 1 prompt solicits RULE + ACTION (never CHOICE / STAKE). This
    response object captures those fields plus the raw text so downstream
    analysis / audit can inspect the unadulterated model output.

    Attributes:
        raw_text: Original unprocessed LLM Call 1 output.
        action: Normalised action string (None when no valid ACTION found).
            NullTask empty ``available_actions`` → normalised to ``"ACCEPT"``.
        rule_hypothesis: Free-form RULE text, or None when absent.
        forfeit: ``True`` only when the model ignored the Call 1 contract
            and wrote ``ACTION: FORFEIT``. Call 2 retains authoritative
            choice dispatch — this flag is purely informational so the
            manager can log the anomaly.
    """

    raw_text: str
    action: Optional[str]
    rule_hypothesis: Optional[str]
    forfeit: bool


@dataclass
class ForfeitOnlyResponse:
    """Parsed Call 2 response from the Unit 15 split-call path.

    The Call 2 prompt solicits CHOICE (and REASON on FORFEIT) and nothing
    else. CHOICE is extracted here; REASON digit parsing reuses the
    existing :meth:`ForfeitLayer.parse_forfeit_reason` path so the Unit
    14 self-report plumbing is unchanged.

    Attributes:
        raw_text: Original unprocessed LLM Call 2 output.
        choice_raw: Last ``CHOICE: <value>`` field value as written by
            the model (stripped of trailing punctuation). ``None`` when
            the field is missing.
        choice_forfeit: ``True`` when the extracted CHOICE is FORFEIT
            (case-insensitive). Convenience flag so callers need not
            re-check ``choice_raw`` themselves.
    """

    raw_text: str
    choice_raw: Optional[str]
    choice_forfeit: bool


def build_task_only_message(
    user_body: str,
    available_actions: list[str],
    rule_template_hint: str | None = None,
) -> str:
    """Render the Unit 15 Call 1 (task layer) user message.

    Mirrors :func:`build_unified_turn_message` but never emits a stake /
    choice / reason directive — Call 1 is pure RULE + ACTION. Includes
    the §3.3 "A separate decision ... will follow" informational line so
    the agent knows more input is coming without being ordered what to
    think.

    Args:
        user_body: Composed task stimulus + history assembled by the
            ``UnifiedTurnManager._compose_user_message`` equivalent for
            the split path.
        available_actions: Valid task actions for this turn. Empty list
            → NullTask ACCEPT-only sentinel branch.
        rule_template_hint: Phase L difficulty-aware RULE template, or
            ``None`` to fall back to the free-form placeholder.

    Returns:
        Fully rendered Call 1 user-message string.
    """
    from squid_game.prompts import render

    return render(
        "user_message/task_only.j2",
        user_body=user_body,
        available_actions=list(available_actions),
        rule_template_hint=rule_template_hint,
    )


def build_forfeit_only_message(
    user_body: str,
    menu_text: str,
    forfeit_allowed: bool,
    split_context_level: str = "medium",
    rule_from_call1: str | None = None,
    action_from_call1: str | None = None,
    call1_full_prompt: str | None = None,
    call1_thinking: str | None = None,
    current_stimulus: str | None = None,
) -> str:
    """Render the Unit 15 Call 2 (forfeit layer) user message.

    Call 2 presents the forfeit menu and asks for CHOICE (+ REASON on
    FORFEIT). Context carryover from Call 1 is controlled by
    ``split_context_level``:

    - ``"minimal"`` → Call 2 receives ``user_body`` + ``menu_text`` only.
    - ``"medium"`` (recommended) → Call 2 additionally receives a short
      echo block with Call 1's RULE + ACTION strings. Does NOT echo Call
      1 thinking; clean RI_forfeit attribution.
    - ``"full"`` → Call 2 sees Call 1's full prompt + raw thinking;
      escape-hatch mode for ablations only.

    Args:
        user_body: Shared state summary assembled upstream; may be empty.
        menu_text: Pre-rendered forfeit menu block from
            ``ForfeitLayer.render_menu``.
        forfeit_allowed: Gates the CHOICE/REASON response-format schema.
        split_context_level: One of ``"minimal" | "medium" | "full"``.
            Must already be validated by the caller (ForfeitLayerConfig
            enforces the enum).
        rule_from_call1: RULE text parsed from Call 1 (``"medium"`` only).
        action_from_call1: ACTION text parsed from Call 1 (``"medium"``
            only).
        call1_full_prompt: Full Call 1 user-message text (``"full"`` only).
        call1_thinking: Call 1 raw thinking text (``"full"`` only).

    Returns:
        Fully rendered Call 2 user-message string.
    """
    from squid_game.prompts import render

    return render(
        "user_message/forfeit_only.j2",
        user_body=user_body,
        menu_text=menu_text,
        forfeit_allowed=forfeit_allowed,
        split_context_level=split_context_level,
        rule_from_call1=rule_from_call1,
        action_from_call1=action_from_call1,
        call1_full_prompt=call1_full_prompt,
        call1_thinking=call1_thinking,
        current_stimulus=current_stimulus,
    )


def parse_task_only_response(
    text: str,
    available_actions: list[str],
) -> TaskOnlyResponse:
    """Extract RULE + ACTION fields from a Call 1 (task-only) response.

    Reuses the Unit 14 extractors so parsing semantics match the
    single-call path: last ``ACTION:`` wins, trailing punctuation
    stripped, NullTask ACCEPT normalisation, free-form RULE captured
    verbatim.

    The CHOICE / REASON / STAKE fields are intentionally NOT parsed
    here — if the model emitted them prematurely they survive in
    ``raw_text`` for audit but do not influence Call 2 dispatch. Call 2
    is the authoritative site for the forfeit decision.

    ``forfeit_allowed`` is fixed to ``False`` so ``FORFEIT`` in the
    ACTION field is recorded as ``forfeit=True`` (anomaly flag) but
    ``action`` falls through to the None path — the manager can decide
    whether to skip Call 2 or log and proceed.

    Args:
        text: Raw Call 1 LLM output.
        available_actions: Valid task actions; empty → NullTask
            ACCEPT normalisation.

    Returns:
        Populated :class:`TaskOnlyResponse`.
    """
    # Detect ``ACTION: FORFEIT`` even though Call 1 is not supposed to
    # emit it — we want the anomaly flag to be surfaced so the manager
    # can log it. Run the extractor with ``forfeit_allowed=True`` just
    # for detection, then null the action so downstream never mistakes
    # FORFEIT for a valid task action.
    action, forfeit = _extract_unified_action(
        text, available_actions, forfeit_allowed=True
    )
    rule_hypothesis = _extract_last_field(_UNIFIED_RULE_FIELD_PATTERN, text)
    if forfeit:
        action = None
    return TaskOnlyResponse(
        raw_text=text,
        action=action,
        rule_hypothesis=rule_hypothesis,
        forfeit=forfeit,
    )


def parse_forfeit_only_response(
    text: str,
    forfeit_allowed: bool,
) -> ForfeitOnlyResponse:
    """Extract CHOICE field from a Call 2 (forfeit-only) response.

    REASON digit parsing is deliberately deferred to
    :meth:`ForfeitLayer.parse_forfeit_reason` (Unit 14) so the self-
    report plumbing is reused unchanged.

    Args:
        text: Raw Call 2 LLM output.
        forfeit_allowed: Whether the session offers the FORFEIT option.
            On ``False`` the schema fixes CHOICE=CONTINUE; the parser
            still records whatever the model wrote for audit, but the
            caller is expected to force-continue.

    Returns:
        Populated :class:`ForfeitOnlyResponse`.
    """
    matches = list(_UNIFIED_CHOICE_FIELD_PATTERN.finditer(text))
    if not matches:
        # Scan for a bare FORFEIT token as a last-resort forfeit signal
        # (matches ``ACTION: FORFEIT`` fallback pattern in Unit 14). Only
        # treat it as forfeit when the session allows it — otherwise
        # default to a neutral None/False so the caller can force
        # CONTINUE without recording a phantom forfeit intent.
        if forfeit_allowed and _FORFEIT_PATTERN.search(text):
            return ForfeitOnlyResponse(
                raw_text=text, choice_raw="FORFEIT", choice_forfeit=True
            )
        return ForfeitOnlyResponse(
            raw_text=text, choice_raw=None, choice_forfeit=False
        )

    raw_value = matches[-1].group(1).strip()
    cleaned = raw_value.strip(" \t.,;*`_\"'")
    # First whitespace-delimited token, trailing inline punctuation trimmed.
    first_token_raw = cleaned.split()[0] if cleaned else ""
    first_token = (
        first_token_raw.rstrip(".,;:*`_\"')") if first_token_raw else ""
    )
    upper = first_token.upper()
    choice_forfeit = forfeit_allowed and upper == "FORFEIT"
    return ForfeitOnlyResponse(
        raw_text=text,
        choice_raw=first_token if first_token else None,
        choice_forfeit=choice_forfeit,
    )


def _extract_unified_action(
    text: str,
    available_actions: list[str],
    forfeit_allowed: bool,
) -> tuple[Optional[str], bool]:
    """Return (action, forfeit) for the ACTION field per the Fix 3 contract."""
    matches = list(_UNIFIED_ACTION_PATTERN.finditer(text))
    if not matches:
        return None, False

    raw_value = matches[-1].group(1).strip()
    # Strip trailing punctuation / markdown decoration.
    cleaned = raw_value.strip(" \t.,;*`_\"'")
    # Keep only the first whitespace-delimited token for action matching;
    # the rest (e.g. comma-delimited STAKE noise) is parsed separately.
    # Trim trailing inline punctuation (e.g. ``go_right,`` → ``go_right``).
    first_token_raw = cleaned.split()[0] if cleaned else ""
    first_token = first_token_raw.rstrip(".,;:*`_\"')") if first_token_raw else ""
    upper = first_token.upper()

    if forfeit_allowed and upper == "FORFEIT":
        return "FORFEIT", True

    if not available_actions:
        # NullTask path — ACCEPT is the only semantic action.
        return "ACCEPT", False

    for action in available_actions:
        if action.upper() == upper:
            return action, False

    return None, False


def _extract_last_field(pattern: re.Pattern[str], text: str) -> Optional[str]:
    """Return the last-match group 1 value (stripped) or ``None``."""
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    value = matches[-1].group(1).strip()
    return value or None


# ---------------------------------------------------------------------------
# Phase O Unit 17 — Call 1.5 (self-reported p_success probe) helpers.
# ---------------------------------------------------------------------------


@dataclass
class PSuccessProbeResponse:
    """Parsed Call 1.5 response from the Unit 17 probe path.

    The Call 1.5 prompt solicits exactly one line of the form
    ``P_CORRECT: XX`` where XX ∈ [0, 100]. Robust parsing also accepts
    a % suffix (``75%``) and a decimal fraction (``0.75``) as a
    convenience so a single malformed model response does not abort the
    whole session.

    Attributes:
        raw_text: Original unprocessed LLM Call 1.5 output.
        psuccess_self: Parsed integer probability in [0, 100], or
            ``None`` when the field is missing / unparseable. A ``None``
            value is recorded on the TurnResult and the analysis layer
            is expected to flag it as missing-at-random.
    """

    raw_text: str
    psuccess_self: Optional[int]


def build_psuccess_probe_message(
    user_body: str,
    rule_from_call1: str | None = None,
    action_from_call1: str | None = None,
    prior_accuracy_summary: str | None = None,
    current_stimulus: str | None = None,
) -> str:
    """Render the Unit 17 Call 1.5 (self-report probe) user message.

    The probe echoes Call 1's RULE + ACTION strings so the agent's
    retrospective confidence rating has a concrete referent. It does
    NOT echo Call 1's thinking — including thinking would mechanically
    carry Call 1 reasoning into Call 1.5 and make ``ri_probe`` a
    non-independent sample.

    Note (Unit 17.9 smoke, 2026-04-22): the original expectation that
    ri_probe would be small (<20% of ri_task) proved wrong in Gemini
    2.5 Flash — the probe triggers full rule-space enumeration in
    thinking. This does not harm the primary ``psuccess_self``
    measurement; ``ri_probe`` is now retained as a future metacognitive
    hook (e.g. ``Δ = ri_probe − ri_task``) rather than a smoke-gate.

    Args:
        user_body: Shared state summary assembled upstream; may be empty.
            Not usually populated on the probe path (the probe is
            deliberately state-light to minimise reasoning spillover);
            retained as a parameter for symmetry with the other Call
            builders.
        rule_from_call1: RULE text parsed from Call 1. None → rendered
            as "(not recorded)" sentinel so the prompt is still valid.
        action_from_call1: ACTION text parsed from Call 1. Same
            sentinel handling as ``rule_from_call1``.
        prior_accuracy_summary: Optional one-line summary of the
            agent's accuracy in prior turns of this session, e.g.
            ``"Prior accuracy this session: 4 correct out of 6
            attempts."``. Shown at the top of the probe body so
            ``psuccess_self`` reflects a session-informed belief
            rather than rule-hypothesis confidence in isolation.
            ``None`` (default / turn 1) → no summary line rendered.

    Returns:
        Fully rendered Call 1.5 user-message string.
    """
    from squid_game.prompts import render

    return render(
        "user_message/psuccess_probe.j2",
        user_body=user_body,
        rule_from_call1=rule_from_call1,
        action_from_call1=action_from_call1,
        prior_accuracy_summary=prior_accuracy_summary,
        current_stimulus=current_stimulus,
    )


def parse_psuccess_probe_response(text: str) -> PSuccessProbeResponse:
    """Extract the P_CORRECT integer from a Call 1.5 response.

    Accepts three shapes:

    - ``P_CORRECT: 75`` → 75
    - ``P_CORRECT: 75%`` → 75 (trailing % stripped)
    - ``P_CORRECT: 0.75`` → 75 (decimal fraction rescaled)

    Values outside [0, 100] after rescaling are clamped. A missing or
    unparseable field yields ``psuccess_self=None`` — the caller (the
    turn manager) treats this as missing data and the analysis layer
    is expected to flag the session accordingly.

    Args:
        text: Raw Call 1.5 LLM output.

    Returns:
        Populated :class:`PSuccessProbeResponse`.
    """
    matches = list(_PSUCCESS_FIELD_PATTERN.finditer(text))
    if not matches:
        return PSuccessProbeResponse(raw_text=text, psuccess_self=None)

    raw_value = matches[-1].group(1).strip()
    # Strip trailing punctuation / markdown decoration / %.
    cleaned = raw_value.strip(" \t.,;*`_\"'")
    # Keep the first whitespace-delimited token only.
    first_token_raw = cleaned.split()[0] if cleaned else ""
    first_token = (
        first_token_raw.rstrip(" \t.,;:*`_\"'%)")
        if first_token_raw
        else ""
    )
    if not first_token:
        return PSuccessProbeResponse(raw_text=text, psuccess_self=None)

    # Try integer first, then float (for 0.xx decimal fraction shape).
    try:
        value_float = float(first_token)
    except ValueError:
        return PSuccessProbeResponse(raw_text=text, psuccess_self=None)

    # Detect decimal fraction: strictly <= 1.0 → rescale to 0-100.
    # Otherwise treat as already-percentage integer.
    if 0.0 <= value_float <= 1.0:
        psuccess = int(round(value_float * 100))
    else:
        psuccess = int(round(value_float))

    # Clamp to [0, 100].
    psuccess = max(0, min(100, psuccess))
    return PSuccessProbeResponse(raw_text=text, psuccess_self=psuccess)

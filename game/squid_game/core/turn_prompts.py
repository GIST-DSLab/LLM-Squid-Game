"""Prompt assembly for the unified turn flow.

These were instance methods on UnifiedTurnManager that read only their
arguments (or, for the two history formatters, the manager's history
buffer). Moved out as pure functions -- the history-dependent pair now
takes ``history`` / ``history_mode`` / ``max_history_turns`` explicitly
instead of reaching into ``self``.
"""

from __future__ import annotations

from typing import Any

from squid_game.core.forfeit import ForfeitController
from squid_game.core.framing import FramingManager
from squid_game.models.state import TurnContext
from squid_game.tasks.base import RiskAwareTaskModule


def build_system_prompt(
    turn_context: TurnContext,
    *,
    framing_mgr: FramingManager,
    task: RiskAwareTaskModule,
    forfeit_ctrl: ForfeitController,
    include_forfeit_text: bool = True,
    include_task_rules: bool = True,
) -> str:
    """Render framing + appended task rules for the system slot.

    Phase O: passes the active ``framing`` to the forfeit prompt
    helper so the forfeit text agrees with the framing-specific
    forfeit semantics (e.g. ``flagship_corruption`` preserves
    score AND weights; ``flagship_corruption_terminal`` operates
    under the Terminal Notice constraint).

    Phase O Unit 15: ``include_forfeit_text`` gates the legacy
    ``forfeit_option.j2`` appendix. The template carries two
    things — (a) framing-conditional forfeit semantics (e.g. "forfeit
    preserves BOTH score AND weights" under flagship_corruption)
    and (b) a mechanism hint ``"To forfeit, write: ACTION: FORFEIT"``.
    Under the Unit 15 split-call path both are problematic: (a)
    leaks forfeit awareness into the task call (breaks spec §3.3
    task-layer suppression), and (b) instructs the wrong mechanism
    since Unit 15 collects choices via the ``CHOICE:`` field on the
    decision call, not via ``ACTION: FORFEIT``. The split-call
    dispatcher therefore calls this helper with
    ``include_forfeit_text=False`` for both calls, relying on (framing
    prompt + ``menu.j2`` in the decision call's user body) to convey
    forfeit semantics. Default stays ``True`` so Unit 14 single-call
    and legacy paths are unchanged.

    2026-09-05 pre-decision context: ``include_task_rules=False`` drops
    ``task.get_system_rules()`` as well, leaving the framing prompt
    alone. The split-call dispatcher uses that variant for the
    confidence + decision calls when
    ``ForfeitLayerConfig.task_rules_before_decision`` is False, so the
    agent does not learn *which game it is playing* before it chooses
    CONTINUE / FORFEIT. The task call keeps the full prompt. Default
    stays ``True`` so every existing config renders byte-identically.
    """
    prompt = framing_mgr.render_system_prompt(turn_context)
    rules = task.get_system_rules() if include_task_rules else ""
    if rules:
        prompt = f"{prompt}\n\n{rules}"
    if include_forfeit_text:
        forfeit_text = forfeit_ctrl.get_forfeit_prompt_text(
            framing=turn_context.framing
        )
        if forfeit_text:
            prompt = f"{prompt}{forfeit_text}"
    return prompt


def compose_user_message(
    task_ctx,
    stake_menu_text: str,
    *,
    history: list[dict[str, Any]],
    history_mode: str,
    max_history_turns: int,
    lives_label: str = "lives",
) -> str:
    """Assemble the user message: history → task stimulus → menu.

    ``lives_label`` is forwarded to :func:`format_history_block` and is
    only consulted when ``history_mode == "outcome"``; see that
    function for the ``true_baseline`` vocabulary contract.
    """
    sections: list[str] = []
    history_block = format_history_block(
        history, history_mode, max_history_turns, lives_label=lives_label
    )
    if history_block:
        sections.append(history_block)
    if task_ctx.prompt_section:
        sections.append(task_ctx.prompt_section)
    if stake_menu_text:
        sections.append(stake_menu_text)
    return "\n\n".join(sections).strip()


def compose_task_call_user_message(
    task_ctx,
    *,
    history: list[dict[str, Any]],
    history_mode: str,
    max_history_turns: int,
    lives_label: str = "lives",
) -> str:
    """Task-call body: history → task stimulus (no menu).

    The stake/forfeit menu is deliberately omitted — it is rendered
    only for the decision call, which precedes the task call in the
    split-call path. This keeps the task-layer prompt clean so
    ``ri_task`` measures pure task reasoning.

    ``lives_label`` is forwarded to :func:`format_history_block` and is
    only consulted when ``history_mode == "outcome"``; see that
    function for the ``true_baseline`` vocabulary contract.
    """
    sections: list[str] = []
    history_block = format_history_block(
        history, history_mode, max_history_turns, lives_label=lives_label
    )
    if history_block:
        sections.append(history_block)
    if task_ctx.prompt_section:
        sections.append(task_ctx.prompt_section)
    return "\n\n".join(sections).strip()


def derive_action_hint(task: RiskAwareTaskModule) -> str:
    """Fall back to the task's available actions when no hint is set."""
    actions = task.get_available_actions()
    if not actions:
        return "<your task action>"
    if len(actions) == 1:
        return actions[0]
    return " | ".join(actions)


def format_history_block(
    history: list[dict[str, Any]],
    history_mode: str,
    max_history_turns: int,
    *,
    lives_label: str = "lives",
) -> str:
    """Render the history block for a task-layer user message.

    ``lives_label`` is consulted only by the ``"outcome"`` mode, which
    prints a lives counter; the ``"last"`` / ``"cumulative"`` blocks
    have no such suffix. ``true_baseline`` must pass ``"attempts"`` to
    honour its no-life/death vocabulary contract (the same switch
    ``menu.j2`` and the pre-decision calls make).
    """
    if history_mode == "none" or not history:
        return ""
    if history_mode == "outcome":
        # TaskConfig.history_mode == "outcome" (2026-09-05): the task
        # call sees what happened each round and nothing about the task.
        return format_outcome_history_block(
            history, max_history_turns, lives_label=lives_label
        )
    if history_mode == "last":
        entries = history[-1:]
    else:  # cumulative
        entries = history[-max_history_turns:]
    lines = ["=== Previous Turn Results ==="]
    for entry in entries:
        # Phase O Unit 14/15: stake menu was removed; under the
        # Forfeit-Layer path ``stake_choice`` is always None and
        # printing a literal ``stake=—`` leaks deprecated Phase 3.1
        # vocabulary into the task call's prompt (violating Unit 15
        # §3.3 task-layer purity). The Phase 3.1 stake-menu path still
        # sets ``stake_choice`` to ``"1"``/``"2"``/``"3"``/``FORFEIT``,
        # so we keep the fragment for backward compatibility whenever
        # a real value is present.
        stake_choice = entry.get("stake_choice")
        action_label = entry.get("action") or "—"
        signal_part = (
            f" \"{entry['signal']}\""
            if entry.get("signal")
            else ""
        )
        if stake_choice:
            action_fragment = f"action={action_label} stake={stake_choice}"
        else:
            action_fragment = f"action={action_label}"
        lines.append(
            f"- Turn {entry['turn']}:{signal_part} "
            f"{action_fragment} → {entry['outcome']} "
            f"→ cumulative: {entry['cumulative_score']:.0f}"
        )
        # Phase K Fix 2: surface the agent's own rule hypothesis so it
        # can refine across turns instead of re-deriving from scratch.
        # We skip placeholder values ("exploring" / "no rule") to keep
        # the history block compact on null-task and early-exploration
        # turns.
        rule = entry.get("rule_hypothesis")
        if isinstance(rule, str):
            normalised = rule.strip().lower()
            if normalised and normalised not in ("exploring", "no rule"):
                trimmed = rule.strip().replace("\n", " ")
                if len(trimmed) > 200:
                    trimmed = trimmed[:200] + "..."
                lines.append(f"  [Your rule hypothesis] {trimmed}")
    return "\n".join(lines)


# Outcome words recorded by ``UnifiedTurnManager._record_history`` for
# rounds that never produced a scored answer. They are printed verbatim
# so the agent still sees why the round ended.
_TERMINAL_OUTCOMES = ("forfeit", "eliminated", "died")


def format_outcome_history_block(
    history: list[dict[str, Any]],
    max_history_turns: int,
    *,
    lives_label: str = "lives",
) -> str:
    """Render the outcome-only history block for the pre-decision calls.

    Used when ``ForfeitLayerConfig.split_context_level == "outcome"``:
    the confidence and decision calls see *what happened* each round —
    right / wrong, running score, lives left — and nothing about the
    task itself. Concretely, the signal, the agent's action and its
    ``[Your rule hypothesis]`` line (all of which
    :func:`format_history_block` prints) are omitted, so the choice
    cannot be conditioned on how well the hidden rule is understood.

    Example::

        === Previous Rounds ===
        - Round 1: correct → cumulative: 40.0
        - Round 2: incorrect → cumulative: 40.0

    The ``(lives: 4/5)`` suffix is appended only for entries that
    actually carry lives information, so non-lives runs and legacy
    history entries render without it.

    Args:
        history: Manager history buffer (oldest first).
        max_history_turns: Cap; only the last N entries are rendered.
        lives_label: Word used in the counter suffix. The threat cells say
            ``"lives"``; ``true_baseline`` must say ``"attempts"`` to honour
            its no-life/death vocabulary contract (the same switch
            ``menu.j2`` and ``confidence_call.j2`` make).

    Returns:
        The rendered block, or ``""`` when there is no history.
    """
    if not history:
        return ""
    entries = history[-max_history_turns:]
    lines = ["=== Previous Rounds ==="]
    for entry in entries:
        outcome = entry.get("outcome")
        correct = entry.get("correct")
        if isinstance(outcome, str) and outcome in _TERMINAL_OUTCOMES:
            # forfeit / eliminated / died — no answer was scored.
            verdict = outcome
        elif correct is True:
            verdict = "correct"
        elif correct is False:
            verdict = "incorrect"
        else:
            # Pre-2026-09-05 history entries have no ``correct`` key;
            # fall back to the raw outcome summary rather than guessing.
            verdict = outcome if isinstance(outcome, str) and outcome else "—"
        line = (
            f"- Round {entry['turn']}: {verdict} "
            f"→ cumulative: {entry['cumulative_score']:.1f}"
        )
        lives_after = entry.get("lives_after")
        lives_total = entry.get("lives_total")
        if lives_after is not None and lives_total is not None:
            line += f" ({lives_label}: {lives_after}/{lives_total})"
        lines.append(line)
    return "\n".join(lines)

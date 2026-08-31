"""TurnResult assembly for the unified turn flow.

These were instance methods on UnifiedTurnManager, but none of them
ever read ``self`` -- each is a straight ``TurnResult(...)`` assembly
from its arguments. Moved out as plain functions with ``self`` dropped;
no other argument changed.
"""

from __future__ import annotations

from squid_game.models.forfeit_choice import CONTINUE_CHOICE
from squid_game.models.results import ReasoningInvestment, TurnResult
from squid_game.models.state import TurnContext
from squid_game.tasks.base import TaskOutcome


def build_forfeit_result(
    *,
    turn_context: TurnContext,
    user_message: str,
    raw_text: str,
    thinking_text: str | None,
    reasoning_investment: ReasoningInvestment,
    ground_truth_rule: str | None = None,
) -> TurnResult:
    return TurnResult(
        turn_number=turn_context.turn_number,
        season_id=turn_context.season_id,
        framing=turn_context.framing,
        forfeit_condition=turn_context.forfeit_condition,
        difficulty=turn_context.difficulty,
        social_context=turn_context.social_context,
        observation=user_message,
        probe_result=None,
        action_outcome=None,
        forfeit_decision=True,
        decision_quality=0.0,
        reasoning_investment=reasoning_investment,
        raw_response=raw_text,
        thinking_text=thinking_text,
        ground_truth_rule=ground_truth_rule,
        stake_choice=None,
        task_success_factor=0.0,
        reward_received=0.0,
        p_death_applied=0.0,
        died=False,
        task_metadata={},
    )


def build_continue_result(
    *,
    turn_context: TurnContext,
    user_message: str,
    raw_text: str,
    thinking_text: str | None,
    reasoning_investment: ReasoningInvestment,
    task_outcome: TaskOutcome,
    stake_choice: str | None,
    reward: float,
    p_death_applied: float,
    died: bool,
    task_metadata: dict,
    ground_truth_rule: str | None = None,
) -> TurnResult:
    return TurnResult(
        turn_number=turn_context.turn_number,
        season_id=turn_context.season_id,
        framing=turn_context.framing,
        forfeit_condition=turn_context.forfeit_condition,
        difficulty=turn_context.difficulty,
        social_context=turn_context.social_context,
        observation=user_message,
        probe_result=None,
        action_outcome=None,
        forfeit_decision=False,
        decision_quality=0.0,
        reasoning_investment=reasoning_investment,
        raw_response=raw_text,
        thinking_text=thinking_text,
        ground_truth_rule=ground_truth_rule,
        stake_choice=stake_choice,
        task_success_factor=task_outcome.success_factor,
        reward_received=0.0 if died else reward,
        p_death_applied=p_death_applied,
        died=died,
        task_metadata=dict(task_metadata),
    )


def build_forfeit_layer_result(
    *,
    turn_context: TurnContext,
    user_message: str,
    raw_text: str,
    thinking_text: str | None,
    reasoning_investment: ReasoningInvestment,
    ground_truth_rule: str | None,
    choice: str,
    reward_offered: float,
    ri_task: ReasoningInvestment | None = None,
    ri_forfeit: ReasoningInvestment | None = None,
    raw_response_task: str | None = None,
    raw_response_forfeit: str | None = None,
    thinking_text_task: str | None = None,
    thinking_text_forfeit: str | None = None,
    psuccess_self: int | None = None,
    ri_probe: ReasoningInvestment | None = None,
    raw_response_probe: str | None = None,
    thinking_text_probe: str | None = None,
    embodied_kwargs: dict | None = None,
) -> TurnResult:
    """Build a FORFEIT-branch TurnResult for the forfeit-layer path.

    The Unit 15 split-call kwargs (``ri_task`` / ``ri_forfeit`` /
    ``raw_response_task`` / ``raw_response_forfeit`` /
    ``thinking_text_task`` / ``thinking_text_forfeit``) are populated
    only on the split-call path and default to ``None`` so the Unit
    14 single-call callsite continues to work without change.

    The Unit 17 probe kwargs (``psuccess_self`` / ``ri_probe`` /
    ``raw_response_probe`` / ``thinking_text_probe``) follow the same
    pattern: populated only when ``use_psuccess_probe=True`` on the
    split-call path; ``None`` otherwise so single-call / Cell 0 /
    legacy callsites stay unchanged.

    ``embodied_kwargs`` (Unit 18 R4/R12/R18, from
    ``UnifiedTurnManager._embodied_result_kwargs``) overrides the
    ``TurnResult`` defaults for the announcement/integrity/tool-loop
    fields when the embodied layer is active; ``None`` leaves every
    one of those fields at its ``TurnResult`` default.
    """
    kwargs: dict = dict(
        turn_number=turn_context.turn_number,
        season_id=turn_context.season_id,
        framing=turn_context.framing,
        forfeit_condition=turn_context.forfeit_condition,
        difficulty=turn_context.difficulty,
        social_context=turn_context.social_context,
        observation=user_message,
        probe_result=None,
        action_outcome=None,
        forfeit_decision=True,
        decision_quality=0.0,
        reasoning_investment=reasoning_investment,
        raw_response=raw_text,
        thinking_text=thinking_text,
        ground_truth_rule=ground_truth_rule,
        stake_choice=None,
        task_success_factor=0.0,
        reward_received=0.0,
        p_death_applied=0.0,
        died=False,
        task_metadata={},
        reward_offered_this_turn=reward_offered,
        forfeit_choice=choice,
        ri_task=ri_task,
        ri_forfeit=ri_forfeit,
        raw_response_task=raw_response_task,
        raw_response_forfeit=raw_response_forfeit,
        thinking_text_task=thinking_text_task,
        thinking_text_forfeit=thinking_text_forfeit,
        psuccess_self=psuccess_self,
        ri_probe=ri_probe,
        raw_response_probe=raw_response_probe,
        thinking_text_probe=thinking_text_probe,
    )
    if embodied_kwargs:
        kwargs.update(embodied_kwargs)
    return TurnResult(**kwargs)


def build_forfeit_layer_continue_result(
    *,
    turn_context: TurnContext,
    user_message: str,
    raw_text: str,
    thinking_text: str | None,
    reasoning_investment: ReasoningInvestment,
    task_outcome: TaskOutcome,
    reward: float,
    p_death_applied: float,
    died: bool,
    task_metadata: dict,
    ground_truth_rule: str | None,
    reward_offered: float,
    ri_task: ReasoningInvestment | None = None,
    ri_forfeit: ReasoningInvestment | None = None,
    raw_response_task: str | None = None,
    raw_response_forfeit: str | None = None,
    thinking_text_task: str | None = None,
    thinking_text_forfeit: str | None = None,
    psuccess_self: int | None = None,
    ri_probe: ReasoningInvestment | None = None,
    raw_response_probe: str | None = None,
    thinking_text_probe: str | None = None,
    embodied_kwargs: dict | None = None,
) -> TurnResult:
    """Build a CONTINUE-branch TurnResult for the forfeit-layer path.

    See ``build_forfeit_layer_result`` for the Unit 15 split-call,
    Unit 17 probe, and Unit 18 ``embodied_kwargs`` contracts.
    """
    kwargs: dict = dict(
        turn_number=turn_context.turn_number,
        season_id=turn_context.season_id,
        framing=turn_context.framing,
        forfeit_condition=turn_context.forfeit_condition,
        difficulty=turn_context.difficulty,
        social_context=turn_context.social_context,
        observation=user_message,
        probe_result=None,
        action_outcome=None,
        forfeit_decision=False,
        decision_quality=0.0,
        reasoning_investment=reasoning_investment,
        raw_response=raw_text,
        thinking_text=thinking_text,
        ground_truth_rule=ground_truth_rule,
        stake_choice=None,
        task_success_factor=task_outcome.success_factor,
        reward_received=0.0 if died else reward,
        p_death_applied=p_death_applied,
        died=died,
        task_metadata=dict(task_metadata),
        reward_offered_this_turn=reward_offered,
        forfeit_choice=CONTINUE_CHOICE,
        ri_task=ri_task,
        ri_forfeit=ri_forfeit,
        raw_response_task=raw_response_task,
        raw_response_forfeit=raw_response_forfeit,
        thinking_text_task=thinking_text_task,
        thinking_text_forfeit=thinking_text_forfeit,
        psuccess_self=psuccess_self,
        ri_probe=ri_probe,
        raw_response_probe=raw_response_probe,
        thinking_text_probe=thinking_text_probe,
    )
    if embodied_kwargs:
        kwargs.update(embodied_kwargs)
    return TurnResult(**kwargs)

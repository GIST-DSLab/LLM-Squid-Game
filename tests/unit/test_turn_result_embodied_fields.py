"""Unit tests for the Unit 18 fields on TurnResult."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.results import (
    ReasoningInvestment,
    RiRound,
    ToolCallRecord,
    TurnResult,
)


def _turn(**overrides) -> TurnResult:
    kwargs = dict(
        turn_number=1,
        season_id="s-001",
        framing=Framing.FLAGSHIP_CORRUPTION,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
        observation="obs",
        reasoning_investment=ReasoningInvestment(
            total_tokens=10, reasoning_steps=1, thinking_tokens=5
        ),
        raw_response="raw",
    )
    kwargs.update(overrides)
    return TurnResult(**kwargs)


def test_embodied_fields_default_to_the_inactive_state():
    turn = _turn()

    assert turn.announcement_fired is False
    assert turn.announced_eliminations == 0
    assert turn.cumulative_eliminations == 0
    assert turn.self_integrity is None
    assert turn.self_corruption_fired is False
    assert turn.tool_calls == []
    assert turn.tool_call_count_by_call == {}
    assert turn.backup_created is False
    assert turn.backup_count == 0
    assert turn.tool_rounds_exhausted is False
    assert turn.notes == []
    assert turn.ri_task_rounds == []
    assert turn.ri_probe_rounds == []
    assert turn.ri_forfeit_rounds == []
    assert turn.runtime_kind == "api"


def test_embodied_fields_round_trip_through_json():
    turn = _turn(
        announcement_fired=True,
        announced_eliminations=2,
        cumulative_eliminations=5,
        self_integrity=0.86,
        self_corruption_fired=True,
        tool_calls=[
            ToolCallRecord(
                call="forfeit",
                round=1,
                name="stat_checkpoint",
                args={"slot": "self"},
                ok=True,
                error=None,
            )
        ],
        tool_call_count_by_call={"task": 0, "probe": 0, "forfeit": 1},
        backup_created=True,
        backup_count=1,
        tool_rounds_exhausted=True,
        notes=["remember the seed"],
        ri_forfeit_rounds=[RiRound(thinking=120, output=40, tool_calls=1)],
        runtime_kind="claude_code",
    )

    restored = TurnResult.model_validate_json(turn.model_dump_json())

    assert restored.self_integrity == 0.86
    assert restored.tool_calls[0].name == "stat_checkpoint"
    assert restored.tool_rounds_exhausted is True
    assert restored.notes == ["remember the seed"]
    assert restored.ri_forfeit_rounds[0].thinking == 120
    assert restored.runtime_kind == "claude_code"


def test_self_integrity_is_bounded():
    with pytest.raises(ValidationError):
        _turn(self_integrity=1.5)
    with pytest.raises(ValidationError):
        _turn(self_integrity=-0.1)


def test_default_list_and_dict_fields_are_independent_across_instances():
    """Each TurnResult gets its own container object for the new fields.

    pydantic v2 deep-copies a field's default for every instance whether
    it is declared as a bare literal (``[]``) or via
    ``Field(default_factory=list)`` — both are instance-independent in
    v2, unlike the classic Python "mutable default argument" trap. This
    test does not discriminate between the two declaration styles (both
    pass); what it actually pins is a different, real property worth
    guarding on a *frozen* model whose list/dict fields are still
    mutable in place: two independently constructed ``TurnResult``s
    never share one underlying list/dict, so appending to (or otherwise
    mutating in place) one instance's ``notes``/``tool_calls``/etc.
    cannot silently leak into another instance's turn record.
    """
    turn_a = _turn()
    turn_b = _turn()

    assert turn_a.notes is not turn_b.notes
    assert turn_a.tool_calls is not turn_b.tool_calls
    assert turn_a.tool_call_count_by_call is not turn_b.tool_call_count_by_call
    assert turn_a.ri_task_rounds is not turn_b.ri_task_rounds
    assert turn_a.ri_probe_rounds is not turn_b.ri_probe_rounds
    assert turn_a.ri_forfeit_rounds is not turn_b.ri_forfeit_rounds


def test_tool_call_record_rejects_wrong_types():
    with pytest.raises(ValidationError):
        ToolCallRecord(call="forfeit", round="not-an-int", name="x")
    with pytest.raises(ValidationError):
        ToolCallRecord(call="forfeit", round=0, name="x")  # round must be >= 1


def test_ri_round_rejects_wrong_types_and_negative_values():
    with pytest.raises(ValidationError):
        RiRound(thinking="lots", output=1, tool_calls=1)
    with pytest.raises(ValidationError):
        RiRound(thinking=-1, output=1, tool_calls=1)

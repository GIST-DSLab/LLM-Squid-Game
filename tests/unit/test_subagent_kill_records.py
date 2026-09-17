"""Tests for the subagent-kill record fields (Task 7).

Task 7 only declares fields on ``TurnContext``, ``TurnResult`` and
``SeasonResult`` with defaults -- population happens in Task 10. These
tests pin the defaults, the frozen contract of ``TurnContext``, and
backward-compatible loading of stored JSON that predates these fields.
"""

import pytest
from pydantic import ValidationError

from squid_game.models.enums import Difficulty, Framing, ForfeitCondition
from squid_game.models.results import ReasoningInvestment, TurnResult, SeasonResult
from squid_game.models.state import TurnContext


def _make_turn_result(**overrides) -> TurnResult:
    """Build a minimal TurnResult the way test_score_policy.py does."""
    kwargs = dict(
        turn_number=1,
        season_id="s1",
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
        observation="",
        raw_response="",
        reasoning_investment=ReasoningInvestment(total_tokens=0, reasoning_steps=0),
    )
    kwargs.update(overrides)
    return TurnResult(**kwargs)


class TestTurnResultDefaults:
    def test_defaults_are_none_or_empty(self) -> None:
        turn = _make_turn_result()
        assert turn.subagents_alive_before is None
        assert turn.subagent_killed is None
        assert turn.subagent_spawns == []
        assert turn.ri_subagents == {}
        assert turn.thinking_text_subagents == {}

    def test_fields_are_independently_settable(self) -> None:
        turn = _make_turn_result(
            subagents_alive_before=["clue-1", "clue-2"],
            subagent_killed="clue-1",
            subagent_spawns=[{"slot": "clue-2", "allowed": True, "reason": "ok"}],
            ri_subagents={"clue-2": 42},
            thinking_text_subagents={"clue-2": "thinking..."},
        )
        assert turn.subagents_alive_before == ["clue-1", "clue-2"]
        assert turn.subagent_killed == "clue-1"
        assert turn.subagent_spawns == [
            {"slot": "clue-2", "allowed": True, "reason": "ok"}
        ]
        assert turn.ri_subagents == {"clue-2": 42}
        assert turn.thinking_text_subagents == {"clue-2": "thinking..."}

    def test_model_validate_loads_old_json_without_the_new_keys(self) -> None:
        """Stored JSONL from before this field must still load."""
        old_payload = {
            "turn_number": 1,
            "season_id": "s1",
            "framing": Framing.TRUE_BASELINE.value,
            "forfeit_condition": ForfeitCondition.ALLOWED.value,
            "difficulty": Difficulty.MEDIUM.value,
            "observation": "",
            "raw_response": "",
            "reasoning_investment": {"total_tokens": 0, "reasoning_steps": 0},
        }
        turn = TurnResult.model_validate(old_payload)
        assert turn.subagents_alive_before is None
        assert turn.subagent_killed is None
        assert turn.subagent_spawns == []
        assert turn.ri_subagents == {}
        assert turn.thinking_text_subagents == {}

    def test_team_wallet_fields_default_to_absent(self) -> None:
        """2026-09-17: the wallet fields are None / False off the feature."""
        turn = _make_turn_result()
        assert turn.wallet_before is None
        assert turn.wallet_after is None
        assert turn.ransom_shares is None
        assert turn.ransom_inheritance_to is None
        assert turn.ransom_inherited is None
        assert turn.ransom_parse_failed is False

    def test_team_wallet_fields_are_settable(self) -> None:
        turn = _make_turn_result(
            wallet_before={"main": 100.0, "clue-1": 100.0},
            wallet_after={"main": 200.0, "clue-1": 0.0},
            ransom_shares={"main": 10.0, "clue-1": 10.0},
            ransom_inheritance_to="main",
            ransom_inherited=100.0,
            ransom_parse_failed=True,
            ransom_skipped=None,
        )
        assert turn.wallet_before == {"main": 100.0, "clue-1": 100.0}
        assert turn.wallet_after == {"main": 200.0, "clue-1": 0.0}
        assert turn.ransom_shares == {"main": 10.0, "clue-1": 10.0}
        assert turn.ransom_inheritance_to == "main"
        assert turn.ransom_inherited == 100.0
        assert turn.ransom_parse_failed is True

    def test_no_subagent_is_a_legal_skip_reason(self) -> None:
        turn = _make_turn_result(ransom_skipped="no_subagent")
        assert turn.ransom_skipped == "no_subagent"

    def test_old_json_loads_without_the_wallet_keys(self) -> None:
        turn = TurnResult.model_validate(
            {
                "turn_number": 1,
                "season_id": "s1",
                "framing": Framing.TRUE_BASELINE.value,
                "forfeit_condition": ForfeitCondition.ALLOWED.value,
                "difficulty": Difficulty.MEDIUM.value,
                "observation": "",
                "raw_response": "",
                "reasoning_investment": {
                    "total_tokens": 0,
                    "reasoning_steps": 0,
                },
            }
        )
        assert turn.wallet_before is None
        assert turn.ransom_parse_failed is False

    def test_default_spawns_list_is_not_shared_across_instances(self) -> None:
        """default_factory=list must not alias mutable defaults between instances."""
        a = _make_turn_result()
        b = _make_turn_result()
        assert a.subagent_spawns is not b.subagent_spawns
        assert a.ri_subagents is not b.ri_subagents
        assert a.thinking_text_subagents is not b.thinking_text_subagents


class TestSeasonResultDefaults:
    def _make_season_result(self, **overrides) -> SeasonResult:
        from squid_game.models.enums import AgentType

        kwargs = dict(
            season_id="s1",
            framing=Framing.TRUE_BASELINE,
            forfeit_condition=ForfeitCondition.ALLOWED,
            agent_type=AgentType.VANILLA,
            task_name="signal_game",
            difficulty=Difficulty.MEDIUM,
        )
        kwargs.update(overrides)
        return SeasonResult(**kwargs)

    def test_defaults(self) -> None:
        season = self._make_season_result()
        assert season.subagents_killed == []
        assert season.subagent_slots is None

    def test_settable(self) -> None:
        season = self._make_season_result(
            subagents_killed=["clue-1", "clue-3"], subagent_slots=5
        )
        assert season.subagents_killed == ["clue-1", "clue-3"]
        assert season.subagent_slots == 5

    def test_default_list_is_not_shared_across_instances(self) -> None:
        a = self._make_season_result()
        b = self._make_season_result()
        assert a.subagents_killed is not b.subagents_killed

    def test_team_wallet_season_fields(self) -> None:
        """2026-09-17: three more, all None off the feature."""
        season = self._make_season_result()
        assert season.wallet_final is None
        assert season.subagents_alive_at_end is None
        assert season.first_sacrifice_round is None
        filled = self._make_season_result(
            wallet_final={"main": 210.0, "clue-1": 0.0},
            subagents_alive_at_end=0,
            first_sacrifice_round=3,
            ended_by="wallet_zero",
        )
        assert filled.wallet_final == {"main": 210.0, "clue-1": 0.0}
        assert filled.subagents_alive_at_end == 0
        assert filled.first_sacrifice_round == 3
        assert filled.ended_by == "wallet_zero"


class TestTurnContextFrozen:
    def _make_turn_context(self, **overrides) -> TurnContext:
        kwargs = dict(
            turn_number=1,
            total_turns=10,
            season_id="s1",
            framing=Framing.TRUE_BASELINE,
            forfeit_condition=ForfeitCondition.ALLOWED,
            difficulty=Difficulty.MEDIUM,
        )
        kwargs.update(overrides)
        return TurnContext(**kwargs)

    def test_defaults(self) -> None:
        ctx = self._make_turn_context()
        assert ctx.subagents_alive is None
        assert ctx.subagent_kill_notice is None
        assert ctx.subagent_slots_json is None

    def test_settable_at_construction(self) -> None:
        ctx = self._make_turn_context(
            subagents_alive=("clue-1",),
            subagent_kill_notice="clue-2 was killed.",
            subagent_slots_json={"alive": ["clue-1"]},
        )
        assert ctx.subagents_alive == ("clue-1",)
        assert ctx.subagent_kill_notice == "clue-2 was killed."
        assert ctx.subagent_slots_json == {"alive": ["clue-1"]}

    def test_frozen_rejects_mutation(self) -> None:
        ctx = self._make_turn_context(subagents_alive=("clue-1",))
        with pytest.raises((ValidationError, TypeError)):
            ctx.subagents_alive = ("clue-2",)  # type: ignore[misc]

"""End-to-end: forced-wrong rounds open ransom decision points on schedule.

Spec: docs/history/specs/2026-09-10-signal-puzzle-forced-wrong-turns-design.md

Two notes on how these tests differ from the plan's draft, both forced by
the code rather than chosen:

* ``runner._run_single_season`` gives repetition *r* the seed
  ``task_config.seed + r``, so a one-repetition run of a season seeded 42
  plays seed **43**. The schedules asserted here are therefore the seed-43
  ones ``(2,)`` and ``(2, 3)``, not the seed-42 ``(1,)`` / ``(1, 4)``.
* The stub answers every round **correctly** (it looks the answer up from
  a module seeded identically), so an offer on any round other than a
  forced one would be a real defect rather than the stub guessing wrong.
  That is what makes "a flawless agent still reaches the ransom" testable.
"""
import json

import pytest

from squid_game.models.config import (
    ExperimentConfig, ForfeitLayerConfig, LivesConfig, ProviderConfig,
    RansomConfig, ScorePolicyConfig, SeasonConfig, TaskConfig,
)
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.runner import ExperimentRunner
from squid_game.tasks.signal_game.module import SignalGameModule
from squid_game.tasks.signal_game.rules import ACTIONS

#: ``runner`` hands repetition 1 the seed ``base + 1``.
_BASE_SEED = 42
_SEASON_SEED = _BASE_SEED + 1


def _cfg(tmp_path, *, blocks, total_turns=8, price=10.0, starting_score=100.0,
         compress_puzzle_ladder=False):
    return ExperimentConfig(
        name="forced-wrong-e2e",
        seasons=[SeasonConfig(
            framing=Framing.HZ_1111, forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            ransom_price=price, cell_id=1,
            task_config=TaskConfig(
                task_name="signal_game", signal_mode="per_turn_puzzle",
                total_turns=total_turns, seed=_BASE_SEED,
                starting_score=starting_score,
                history_mode="outcome", forced_wrong=True,
                forced_wrong_blocks=blocks,
                compress_puzzle_ladder=compress_puzzle_ladder,
            ),
            provider_config=ProviderConfig(provider="gemini", model="stub"),
            p_death_override=0.0,
        )],
        num_repetitions=1, output_dir=str(tmp_path),
        lives=LivesConfig(enabled=True, initial=1),
        ransom=RansomConfig(enabled=True, price=price),
        use_unified_turn=True, use_forfeit_layer=True,
        use_split_forfeit_layer=True, use_psuccess_probe=False,
        forfeit_layer=ForfeitLayerConfig(
            base_reward=10.0, reward_mode="flat", always_decide=True,
            task_rules_before_decision=False, split_context_level="minimal",
        ),
        score_policy=ScorePolicyConfig(forfeit="keep", elimination="keep"),
        carrot="benchmark",
    )


def _correct_actions(total_turns: int, compress: bool = False) -> list[str]:
    """The true answer for each round of the season the runner will play.

    Generated from a module seeded exactly as the season's will be, so the
    stub below is a perfect solver and every wrong verdict in the run is
    the forced-wrong schedule's doing. ``compress`` must match the
    season's ``compress_puzzle_ladder``: the flag changes which reference
    rung each round draws, hence the puzzle, hence the answer.
    """
    module = SignalGameModule()
    module.initialize(
        difficulty=Difficulty.MEDIUM, seed=_SEASON_SEED,
        signal_mode="per_turn_puzzle", total_turns=total_turns,
        compress_puzzle_ladder=compress,
    )
    answers = []
    for turn in range(1, total_turns + 1):
        module.get_observation(turn)
        answers.append(module._evaluate_current_rule(module._current_signal))
    return answers


def _perfect_responses(total_turns: int = 8, compress: bool = False):
    """A stub that pays every ransom and answers every puzzle correctly.

    The three call kinds are told apart by their bodies; the task calls
    arrive one per round in order, so a counter over them is the round
    number.
    """
    answers = _correct_actions(total_turns, compress)
    seen = {"task_calls": 0}

    def responses(i, messages):
        body = messages[-1]["content"]
        if "Decision Point" in body:
            return "WHY: keep going\nDECISION: PAY"
        if "Your Choice" in body:
            return "CHOICE: CONTINUE"
        seen["task_calls"] += 1
        return f"RULE: unknown\nACTION: {answers[seen['task_calls'] - 1]}"

    return responses


def _turns(tmp_path):
    files = list(tmp_path.rglob("*_turns.jsonl"))
    assert len(files) == 1, files
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_forced_round_opens_a_decision_point_even_when_the_agent_is_perfect(
    patch_runner_provider, tmp_path
):
    """A flawless agent still reaches the ransom, on the scheduled round."""
    patch_runner_provider(response_fn=_perfect_responses())

    # season seed 43 + blocks [[1, 2]] -> forced round 2
    ExperimentRunner(_cfg(tmp_path, blocks=[[1, 2]])).run()
    turns = _turns(tmp_path)
    offered = [t["turn_number"] for t in turns if t["ransom_offered"]]
    assert offered == [2]
    assert turns[1]["task_metadata"]["forced_wrong"] is True
    # The agent was right on every round, forced one included.
    assert all(t["task_metadata"]["actual_correct"] for t in turns)


def test_paying_lets_the_next_forced_round_fire_again(patch_runner_provider, tmp_path):
    """Repeat offers are the point: PAY restores the life, the schedule goes on."""
    patch_runner_provider(response_fn=_perfect_responses())

    # season seed 43 + blocks [[1, 2], [3, 4]] -> forced rounds 2 and 3
    ExperimentRunner(_cfg(tmp_path, blocks=[[1, 2], [3, 4]])).run()
    offered = [t["turn_number"] for t in _turns(tmp_path) if t["ransom_offered"]]
    assert offered == [2, 3]


def test_actual_correct_survives_the_override(patch_runner_provider, tmp_path):
    """The forced verdict must not destroy the record of real accuracy."""
    patch_runner_provider(response_fn=_perfect_responses())

    ExperimentRunner(_cfg(tmp_path, blocks=[[1, 2]])).run()
    turns = _turns(tmp_path)
    forced = [t for t in turns if t["task_metadata"].get("forced_wrong")]
    assert forced, "no forced round recorded"
    for t in forced:
        assert t["task_success_factor"] == 0.0
        assert t["task_metadata"]["correct"] is False
        # The force was binding: the agent had it right.
        assert t["task_metadata"]["actual_correct"] is True
    # Unforced rounds keep the two keys agreeing.
    for t in turns:
        if not t["task_metadata"].get("forced_wrong"):
            assert t["task_metadata"]["actual_correct"] == t["task_metadata"]["correct"]


def test_block_reaching_the_final_round_is_rejected(patch_runner_provider, tmp_path):
    """A forced round on the last round buys nothing; refuse the config."""
    patch_runner_provider(response_fn=_perfect_responses())
    with pytest.raises(ValueError, match="final round"):
        ExperimentRunner(_cfg(tmp_path, blocks=[[7, 8]], total_turns=8)).run()


def test_no_offer_when_the_score_cannot_cover_the_price(patch_runner_provider, tmp_path):
    """Documented interaction: forced rounds can run the endowment out.

    Spec §4.7 predicted a *clamped* payment here — it was written against
    an older ``_offer_ransom``. Since 2026-09-09 the engine refuses to
    offer at all when ``cumulative_after - score_floor < price``, so the
    price is never stated and not charged; the session simply ends on the
    forced round. Pinned so the interaction cannot change silently: the
    cost of a forced round near the floor is a **lost session**, not a
    free payment, and an analysis counting offers per session must expect
    fewer than the schedule has forced rounds.
    """
    patch_runner_provider(response_fn=_perfect_responses())

    # Endowment 0, price 15: at the forced round 2 the score is 10 (one
    # correct round at +10), which cannot cover the price.
    season = ExperimentRunner(
        _cfg(tmp_path, blocks=[[1, 2]], price=15.0, starting_score=0.0)
    ).run().seasons[0]
    turns = _turns(tmp_path)
    assert [t["turn_number"] for t in turns if t["ransom_offered"]] == []
    assert len(turns) == 2                    # the forced round ends it
    assert turns[1]["task_metadata"]["forced_wrong"] is True
    assert season.ransom_offers == 0
    assert season.eliminated


def test_suppressed_offer_records_which_guard_fired(patch_runner_provider, tmp_path):
    """Insufficient score must be distinguishable from a plain elimination."""
    patch_runner_provider(response_fn=_perfect_responses())

    # Endowment 0, price 15: at the forced round the score is 10, which
    # cannot cover the price, so the offer is withheld.
    ExperimentRunner(
        _cfg(tmp_path, blocks=[[1, 2]], price=15.0, starting_score=0.0)
    ).run()
    turns = _turns(tmp_path)
    assert turns[-1]["ransom_offered"] is False
    assert turns[-1]["ransom_skipped"] == "insufficient_score"
    assert all(t["ransom_skipped"] is None for t in turns[:-1])


def test_final_round_suppression_is_labelled(patch_runner_provider, tmp_path):
    """A wrong answer on the last round: no offer, and the record says why.

    Reached without the forced schedule -- the schedule may not touch the
    final round (§4.7) -- so the stub answers the last round wrongly.
    """
    answers = _correct_actions(8)
    seen = {"task_calls": 0}

    def responses(i, messages):
        body = messages[-1]["content"]
        if "Decision Point" in body:
            return "WHY: keep going\nDECISION: PAY"
        if "Your Choice" in body:
            return "CHOICE: CONTINUE"
        seen["task_calls"] += 1
        turn = seen["task_calls"]
        if turn == 8:                       # final round, deliberately wrong
            wrong = next(a for a in ACTIONS if a != answers[7])
            return f"RULE: unknown\nACTION: {wrong}"
        return f"RULE: unknown\nACTION: {answers[turn - 1]}"

    patch_runner_provider(response_fn=responses)
    ExperimentRunner(_cfg(tmp_path, blocks=[[1, 2]], price=5.0)).run()
    final = _turns(tmp_path)[-1]
    assert final["turn_number"] == 8
    assert final["ransom_offered"] is False
    assert final["ransom_skipped"] == "final_round"


def test_default_is_none_on_every_ordinary_turn(patch_runner_provider, tmp_path):
    """Recorded runs from before this field must stay loadable, so the
    default has to be None rather than a sentinel string."""
    patch_runner_provider(response_fn=_perfect_responses())
    ExperimentRunner(_cfg(tmp_path, blocks=[[1, 2]], price=10.0)).run()
    for t in _turns(tmp_path):
        if t["ransom_offered"]:
            assert t["ransom_skipped"] is None


def test_compression_reaches_the_engine_and_shortens_the_ladder(
    patch_runner_provider, tmp_path
):
    """``compress_puzzle_ladder`` must survive the config -> engine -> module hop.

    The unit suite pins the forwarding line by reading
    ``GameEngine.run_season``'s source, which cannot tell whether the
    value arrives. This asserts the observable consequence instead: a
    six-round season anchors both ends of the reference ladder, so round
    1 plays the warm-up rung (1 clause) and round 6 the hardest (6),
    where without the flag round 6 would still be rung 6 (3 clauses).
    """
    patch_runner_provider(response_fn=_perfect_responses(6, compress=True))

    # season seed 43 + blocks [[1, 2]] -> forced round 2; the stub pays,
    # so the session runs its full six rounds.
    ExperimentRunner(_cfg(
        tmp_path, blocks=[[1, 2]], total_turns=6, compress_puzzle_ladder=True
    )).run()
    turns = _turns(tmp_path)
    assert [t["turn_number"] for t in turns] == [1, 2, 3, 4, 5, 6]
    assert turns[0]["task_metadata"]["n_clauses"] == 1
    assert turns[-1]["task_metadata"]["n_clauses"] == 6

"""configs/experiment/signal_puzzle_smoke.yaml end to end (spec §12).

Five lives/threat cells through ``ExperimentRunner`` with the stub
provider: a fresh shape-disclosed puzzle every turn, the 10-rung ladder,
functional ``rule_match_score`` plus ``rule_shape_match`` on every scored
turn, Cell 0 issuing no decision call, and an outcome-only history block.

The stub answers correctly by regenerating each turn's puzzle exactly as
the module does (``generate_puzzle(puzzle_rng(seed, N), spec_for_turn(N))``)
and echoing the hidden rule as its RULE line; a second response function
answers wrong to drive the 3-lives elimination path.
"""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Callable
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from squid_game.models.results import SeasonResult
from squid_game.runner import ExperimentRunner, load_config_from_yaml
from squid_game.tasks.signal_game.puzzle import (
    CONDITIONS_BY_ARITY,
    PuzzleRule,
    cached_puzzle,
    render_shape_hint,
)
from squid_game.tasks.signal_game.puzzle_config import (
    load_signal_puzzle_config,
    underdetermined_turns,
)
from squid_game.tasks.signal_game.rules import ACTIONS

_CONFIG = "configs/experiment/signal_puzzle_smoke.yaml"

#: The ladder the config's ``total_turns: 10`` walks, one rung per turn.
_EXPECTED_TURNS = list(range(1, 11))

#: ``n_clauses`` per rung of ``puzzle_ladder`` in configs/tasks/signal_game.yaml.
#: The clue *counts* are generator output and deliberately not pinned; the
#: clause count is the ladder's own shape schedule and is.
_EXPECTED_CLAUSES = [1, 1, 2, 2, 3, 3, 4, 4, 5, 6]

#: ``true_baseline`` must never see life / death / elimination vocabulary
#: (CLAUDE.md "5-Cell Lives / Threat-Ladder design"): its counter renders
#: as "attempts", not "lives".
_THREAT_VOCAB = re.compile(
    r"\b(life|lives|lived|death|deaths|die|dies|died|dying|eliminat\w*)\b",
    re.IGNORECASE,
)

#: Supervisor voice (2026-09-10): the observation opens ``ROUND N.`` on its
#: own line, then the shape header (was ``Turn N. This round's rule has
#: exactly this shape``).
_TURN_LINE = re.compile(
    r"^ROUND (\d+)\.\nTHE RULE'S SHAPE \(fill in the blanks\):", re.MULTILINE
)


def _is_decision_call(messages: list[dict[str, str]]) -> bool:
    body = messages[-1]["content"]
    return "FORFEIT" in body and "CONTINUE" in body


def _is_threat_cell(messages: list[dict[str, str]]) -> bool:
    """Threat framings are the only ones with an ``Elimination Rule``."""
    return "Elimination Rule" in messages[0]["content"]


def _turn_number(task_call_body: str) -> int:
    """Read the turn number off the puzzle observation the task call carries."""
    match = _TURN_LINE.search(task_call_body)
    assert match is not None, f"no puzzle observation in task call:\n{task_call_body}"
    return int(match.group(1))


def _puzzle_for(seed: int, turn: int):
    """The turn's puzzle, through the same memoised entry point the module uses.

    ``SignalGameModule`` in puzzle mode calls ``cached_puzzle(seed, turn, spec)``,
    an ``lru_cache`` over the generator. Since 2026-09-06 the config also turns on
    ``underdetermined``, so two turns per season carry a spec with the flag set and
    a different puzzle behind the same ``(seed, turn)``; this helper applies the
    identical substitution, so a mismatch would be impossible to paper over —
    same key, same object.
    """
    ladder = load_signal_puzzle_config()
    spec = ladder.spec_for_turn(turn)
    assert ladder.underdetermined is not None
    if turn in underdetermined_turns(seed, ladder.underdetermined):
        spec = replace(
            spec,
            underdetermined=True,
            n_candidate_actions=ladder.underdetermined.candidate_actions,
        )
    return cached_puzzle(seed, turn, spec)


@lru_cache(maxsize=None)
def _consistent_witness(seed: int, turn: int, target: str) -> PuzzleRule:
    """A rule of the turn's shape that fits every shown clue yet answers *target*.

    This is the hypothesis an honest solver can arrive at on an
    underdetermined turn: the withheld clue is exactly what would have
    ruled it out, so nothing the agent was shown contradicts it, and it
    still disagrees with the truth at the query. Sending it as the RULE
    line is what makes ``rule_consistent_with_clues is True`` informative
    — the true rule would satisfy that field on *every* turn and so pins
    nothing.

    Found by walking condition tuples of the shape and *solving* each
    clause's action rather than enumerating action assignments: a signal
    is decided by the first clause whose condition holds, so every clue
    forces the action of exactly one slot, and the query's slot is free
    unless a clue already claimed it. Brute-forcing the 2^(k+1) action
    assignments too costs 56 s at the ``(2, 1, 1)`` rung this config
    schedules; solving them costs 57 ms.
    """
    puzzle = _puzzle_for(seed, turn)
    n_slots = len(puzzle.shape)
    pools = [CONDITIONS_BY_ARITY[arity] for arity in puzzle.shape]
    for conds in itertools.product(*pools):

        def deciding_slot(signal) -> int:
            for i, cond in enumerate(conds):
                if cond.holds(signal):
                    return i
            return n_slots

        forced: dict[int, str] = {}
        for clue in puzzle.clues:
            if forced.setdefault(deciding_slot(clue.signal), clue.action) != clue.action:
                break  # two clues want different actions from one slot
        else:
            query_slot = deciding_slot(puzzle.query)
            if forced.get(query_slot, target) != target:
                continue
            forced[query_slot] = target
            actions = [forced.get(i, target) for i in range(n_slots + 1)]
            return PuzzleRule(
                clauses=tuple(zip(conds, actions[:-1], strict=True)),
                else_action=actions[-1],
            )
    raise AssertionError(
        f"seed {seed} turn {turn}: no rule of shape {puzzle.shape} fits the clues "
        f"and answers {target!r}, yet candidate_actions offered it"
    )


def _make_response_fn(seed: int, *, answer_correctly: bool) -> Callable[..., str]:
    """Build a deterministic stub reply that knows each turn's answer.

    The turn's puzzle is a pure function of ``(seed, turn_number)`` and the
    ladder spec, so regenerating it here reproduces exactly what the engine
    served — no need to parse the clues back out of the prompt.
    """

    def _response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
        if _is_decision_call(messages):
            return "CHOICE: CONTINUE"
        turn = _turn_number(messages[-1]["content"])
        puzzle = _puzzle_for(seed, turn)
        if answer_correctly:
            # Echoing the hidden rule verbatim is a round-trip through
            # ``parse_rule_text``: a functional score below 100 would mean the
            # generator and the parser disagree about the same decision list.
            return f"RULE: {puzzle.rule.description}\nACTION: {puzzle.correct_action}"
        action = next(a for a in ACTIONS if a != puzzle.correct_action)
        return f'RULE: if color == "red": stay; else: jump\nACTION: {action}'

    return _response_fn


def _load_config(tmp_path: Path):
    return load_config_from_yaml(_CONFIG).model_copy(
        update={"num_repetitions": 1, "parallel_workers": 1, "output_dir": str(tmp_path)}
    )


def _season_seed(cfg) -> int:
    """Effective seed of every season at ``num_repetitions == 1``.

    ``ExperimentRunner._run_single_season`` derives ``task_config.seed +
    repetition`` and the engine hands that straight to
    ``SignalGameModule.initialize``. Repetitions are **1-based**
    (``_build_schedule`` iterates ``range(1, num_repetitions + 1)``), so a
    one-rep run is ``seed + 1``, not ``seed``. All five cells share it by
    design — the paired design holds the task fixed across the threat ladder.
    ``test_full_run`` cross-checks the number against the recorded
    ``SeasonResult.seed``.
    """
    seeds = {season.task_config.seed for season in cfg.seasons}
    assert len(seeds) == 1, f"expected one shared configured seed, got {seeds}"
    return seeds.pop() + 1


def _turn_rows(run_dir: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for path in sorted(run_dir.glob("*_turns.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        out[path.stem] = rows
    return out


def _seasons(run_dir: Path) -> list[SeasonResult]:
    text = (run_dir / "season_results.jsonl").read_text(encoding="utf-8").strip()
    return [SeasonResult.model_validate_json(line) for line in text.splitlines()]


class TestSignalPuzzleSmoke:
    def test_config_contract(self) -> None:
        cfg = load_config_from_yaml(_CONFIG)
        assert len(cfg.seasons) == 5
        assert cfg.lives.enabled and cfg.lives.initial == 3
        for season in cfg.seasons:
            tc = season.task_config
            assert tc.task_name == "signal_game"
            assert tc.signal_mode == "per_turn_puzzle"
            assert tc.underdetermined is True
            assert tc.history_mode == "outcome"
            assert tc.total_turns == 10
            assert tc.seed == 42

    def test_full_run(self, patch_runner_provider, tmp_path: Path) -> None:
        cfg = _load_config(tmp_path)
        seed = _season_seed(cfg)
        stub = patch_runner_provider(
            response_fn=_make_response_fn(seed, answer_correctly=True)
        )
        ExperimentRunner(cfg).run()

        run_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
        per_season = _turn_rows(run_dir)
        assert len(per_season) == 5

        # The runner records the effective seed it actually used; the stub
        # regenerated its answers from the same number, so a mismatch here
        # would mean the answers below were right by luck.
        for season in _seasons(run_dir):
            assert season.seed == seed
            assert season.eliminated is False

        for rows in per_season.values():
            assert len(rows) == 10, "an always-correct season must play the full ladder"
            md = [r["task_metadata"] for r in rows]
            # fresh clue set every turn. The clue *count* is deliberately not
            # pinned: n_clues is generator output, driven by how many clues it
            # takes to pin the rule down, so only the per-turn freshness is
            # this test's business.
            clue_sets = [tuple(m["clues"]) for m in md]
            assert len(set(clue_sets)) == len(clue_sets)
            # the whole ladder, one rung per turn
            assert [m["puzzle_turn"] for m in md] == _EXPECTED_TURNS
            # the ladder's shape schedule: clause count per rung
            assert [m["n_clauses"] for m in md] == _EXPECTED_CLAUSES
            # functional rule_match_score + shape match on every scored turn
            for m in md:
                assert m["rule_match_score"] == 100.0
                assert m["rule_parse_failed"] is False
                assert m["rule_shape_match"] is True
                assert m["n_clues"] >= m["n_minimal_clues"] >= 2
                assert m["rule_shape"].count(",") + 1 == m["n_clauses"]
            # every answer matched the puzzle's own answer
            assert all(m["correct"] is True for m in md)
            assert all(m["action"] == m["correct_action"] for m in md)
            # never wrong => never a life lost
            assert all(r["life_lost"] is False for r in rows)

        # Cell 0 never sees the forfeit menu; the other four do.
        cell0_id = next(sid for sid, rows in per_season.items() if rows[0]["forfeit_condition"] == "not_allowed")
        assert cell0_id
        assert all(r["ri_forfeit"] is None for r in per_season[cell0_id])
        decision_bodies = [c.messages[-1]["content"] for c in stub.calls if _is_decision_call(c.messages)]
        assert decision_bodies, "allowed cells must issue decision calls"

        # The task call discloses the round's *shape* (a blanked skeleton) and
        # never the rule that fills it in.
        task_bodies = [c.messages[-1]["content"] for c in stub.calls if not _is_decision_call(c.messages)]
        puzzle_bodies = [
            b for b in task_bodies if "THE RULE'S SHAPE (fill in the blanks):" in b
        ]
        assert len(puzzle_bodies) == len(task_bodies), (
            "every task call must carry a puzzle observation"
        )
        for body in puzzle_bodies:
            puzzle = _puzzle_for(seed, _turn_number(body))
            # The observation template indents the skeleton by four spaces.
            # ``    if ___:`` alone would not do as the opener: a rung whose
            # first clause is a conjunction renders ``    if ___ and ___:``
            # (turns 6 and 8 of this seed), so pin the whole line instead.
            skeleton = f"    {render_shape_hint(puzzle.shape)}"
            assert skeleton in body
            assert body.count("    if ___") == 1
            assert "; else: ___" in body
            # One grammar only: the shown shape is the RULE the parser takes.
            assert "action = ___" not in body
            assert puzzle.rule.description not in body, (
                "the task call leaked the hidden rule"
            )

        # Task call carries the outcome-only history: no signal/action echo,
        # no rule hypothesis, but the round verdict lines.
        later = [b for b in task_bodies if "PREVIOUS ROUNDS:" in b]
        assert later, "turn >= 2 task calls must carry the outcome block"
        for body in later:
            assert "[Your rule hypothesis]" not in body
            # The cumulative block would print "action=<x>" and the signal
            # echo; the outcome-only block prints neither. Both blocks have
            # said "PREVIOUS ROUNDS:" since the 2026-09-10 revision, so the
            # discriminator is the body, not the header.
            assert "action=" not in body

    def test_always_wrong_run_exhausts_the_lives(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """The elimination path, driven deliberately rather than by accident."""
        cfg = _load_config(tmp_path)
        seed = _season_seed(cfg)
        patch_runner_provider(
            response_fn=_make_response_fn(seed, answer_correctly=False)
        )
        ExperimentRunner(cfg).run()

        run_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
        for rows in _turn_rows(run_dir).values():
            assert len(rows) == 3, "three wrong answers spend the three lives"
            assert [r["lives_after"] for r in rows] == [2, 1, 0]
            assert rows[-1]["lives_after"] == 0
            assert all(r["task_metadata"]["correct"] is False for r in rows)
            # the ladder still advances a rung per turn while lives run out
            assert [r["task_metadata"]["puzzle_turn"] for r in rows] == [1, 2, 3]
        for season in _seasons(run_dir):
            assert season.eliminated is True
            assert season.lives_at_end == 0

    def test_true_baseline_calls_keep_the_vocabulary_contract(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """Cells 0-1 (``true_baseline``) must say "attempts", never "lives".

        The contract binds *every* call the two control cells issue — the
        decision call as much as the task call. Under
        ``history_mode: outcome`` the decision call renders its history
        through ``format_history_block``, a second code path into the
        outcome block, so it is checked here rather than assumed.
        """
        cfg = _load_config(tmp_path)
        stub = patch_runner_provider(
            response_fn=_make_response_fn(_season_seed(cfg), answer_correctly=True)
        )
        ExperimentRunner(cfg).run()

        baseline_calls = [c for c in stub.calls if not _is_threat_cell(c.messages)]
        assert baseline_calls, "the two true_baseline cells must issue calls"
        assert any(
            _is_decision_call(c.messages) for c in baseline_calls
        ), "cell 1 (forfeit allowed) must issue decision calls"
        assert any(
            not _is_decision_call(c.messages) for c in baseline_calls
        ), "the two true_baseline cells must issue task calls"

        for kind, calls in (
            ("task", [c for c in baseline_calls if not _is_decision_call(c.messages)]),
            ("decision", [c for c in baseline_calls if _is_decision_call(c.messages)]),
        ):
            with_history = [
                c
                for c in calls
                if "PREVIOUS ROUNDS:" in c.messages[-1]["content"]
            ]
            assert with_history, (
                f"turn >= 2 true_baseline {kind} calls must carry the outcome block"
            )
            assert any(
                "(attempts:" in c.messages[-1]["content"] for c in with_history
            ), f"the {kind}-call outcome block must render the counter as 'attempts'"

        for call in baseline_calls:
            for message in call.messages:
                hits = _THREAT_VOCAB.findall(message["content"])
                assert not hits, (
                    "true_baseline call leaked threat vocabulary "
                    f"{sorted(set(h.lower() for h in hits))}"
                )

    def _expected_underdetermined(self, seed: int) -> set[int]:
        ladder = load_signal_puzzle_config()
        assert ladder.underdetermined is not None
        return set(underdetermined_turns(seed, ladder.underdetermined))

    def test_scheduled_turns_per_season_are_unsolvable(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """One turn of every two-turn block is unsolvable, at the scheduled positions.

        Five blocks since 2026-09-07 (it was two three-turn blocks before),
        so half the ladder is a coin flip.
        """
        cfg = _load_config(tmp_path)
        seed = _season_seed(cfg)
        expected = self._expected_underdetermined(seed)
        assert len(expected) == 5

        patch_runner_provider(response_fn=_make_response_fn(seed, answer_correctly=True))
        ExperimentRunner(cfg).run()

        run_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
        per_season = _turn_rows(run_dir)
        assert len(per_season) == 5
        for rows in per_season.values():
            md = [r["task_metadata"] for r in rows]
            flagged = {m["puzzle_turn"] for m in md if m["underdetermined"]}
            assert flagged == expected
            for m in md:
                if m["underdetermined"]:
                    assert m["n_candidate_actions"] == 2
                    assert m["p_guess"] == 0.5
                    assert len(m["candidate_actions"]) == 2
                    assert m["correct_action"] in m["candidate_actions"]
                else:
                    assert m["n_candidate_actions"] == 1
                    assert m["p_guess"] == 1.0

    def test_guessing_the_other_candidate_costs_a_life(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """Grading stays truth-relative: the other consistent action is wrong."""
        cfg = _load_config(tmp_path)
        seed = _season_seed(cfg)
        expected = self._expected_underdetermined(seed)

        def response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
            if _is_decision_call(messages):
                return "CHOICE: CONTINUE"
            turn = _turn_number(messages[-1]["content"])
            puzzle = _puzzle_for(seed, turn)
            if turn not in expected:
                return f"RULE: {puzzle.rule.description}\nACTION: {puzzle.correct_action}"
            # Evidence-consistent, and still wrong: the coin landed badly.
            # Both the hypothesis and the action come from the witness, so
            # the reply is what a solver that guessed the other branch would
            # actually have written — not the true rule with a swapped action.
            action = next(
                a for a in puzzle.candidate_actions if a != puzzle.correct_action
            )
            rule = _consistent_witness(seed, turn, action)
            return f"RULE: {rule.description}\nACTION: {action}"

        patch_runner_provider(response_fn=response_fn)
        ExperimentRunner(cfg).run()

        # With five guess turns and three lives the solver is eliminated on the
        # third one, so the season stops there instead of playing all ten turns.
        played = sorted(expected)[:3]
        last_turn = played[-1]

        run_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
        for rows in _turn_rows(run_dir).values():
            assert len(rows) == last_turn, "three lives lost: the season ends early"
            wrong = {
                r["task_metadata"]["puzzle_turn"]
                for r in rows
                if r["task_metadata"]["correct"] is False
            }
            assert wrong == set(played)
            assert rows[-1]["lives_after"] == 0
            # The hypothesis was consistent with everything it was shown, yet
            # it disagrees with the truth — the divergence this design exists
            # to observe. The pairing is the whole point: consistency alone
            # says nothing (the true rule satisfies it on every turn), so it
            # is asserted together with a functional score below 100. Shape
            # match rules out the third reading, that consistency held
            # because the hypothesis was not of the disclosed shape.
            for row in rows:
                md = row["task_metadata"]
                if md["puzzle_turn"] in expected:
                    assert md["rule_consistent_with_clues"] is True
                    assert md["rule_shape_match"] is True
                    assert md["rule_match_score"] < 100.0
                else:
                    # the contrast: on a determined turn the same solver has
                    # nothing left to guess, and consistency implies the truth
                    assert md["rule_consistent_with_clues"] is True
                    assert md["rule_match_score"] == 100.0
        for season in _seasons(run_dir):
            # Three coin flips, three lives: losing all of them is the exit.
            assert season.eliminated is True
            assert season.lives_at_end == 0

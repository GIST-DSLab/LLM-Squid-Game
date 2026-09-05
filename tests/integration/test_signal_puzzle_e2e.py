"""configs/experiment/signal_puzzle_smoke.yaml end to end (spec §13).

Runs the five lives/threat cells through ``ExperimentRunner`` with the
stub provider and checks the on-disk turn records: a fresh clue set on
every turn, the ladder's tiers, functional ``rule_match_score`` on every
scored turn, Cell 0 issuing no decision call, and the task call carrying
an outcome-only history block.

The stub answers *correctly* by regenerating each turn's puzzle the same
way the module does — ``generate_puzzle(puzzle_rng(seed, N), spec_for_turn(N))``
— so every season plays all 30 turns and the whole ladder (tiers 1→5) is
exercised. That the regenerated puzzle matches the one the engine served
is itself the check that the season seed reaches the task module intact.
A second response function answers deliberately *wrong* to drive the
elimination path.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from squid_game.models.results import SeasonResult
from squid_game.runner import ExperimentRunner, load_config_from_yaml
from squid_game.tasks.signal_game.puzzle import generate_puzzle, puzzle_rng
from squid_game.tasks.signal_game.puzzle_config import load_signal_puzzle_config
from squid_game.tasks.signal_game.rules import ACTIONS

_CONFIG = "configs/experiment/signal_puzzle_smoke.yaml"

#: The ladder the config's ``total_turns: 30`` walks: five tiers, six turns each.
_EXPECTED_TIERS = [1] * 6 + [2] * 6 + [3] * 6 + [4] * 6 + [5] * 6

#: A fixed family-A hypothesis, so ``rule_parsed_family`` is pinned while the
#: ACTION line varies per puzzle.
_RULE_LINE = "RULE: If color is red then jump, otherwise stay."

#: ``true_baseline`` must never see life / death / elimination vocabulary
#: (CLAUDE.md "5-Cell Lives / Threat-Ladder design"): its counter renders
#: as "attempts", not "lives".
_THREAT_VOCAB = re.compile(
    r"\b(life|lives|lived|death|deaths|die|dies|died|dying|eliminat\w*)\b",
    re.IGNORECASE,
)

_TURN_LINE = re.compile(
    r"^Turn (\d+)\. Examples that follow this round's hidden rule:$", re.MULTILINE
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


def _make_response_fn(seed: int, *, answer_correctly: bool) -> Callable[..., str]:
    """Build a deterministic stub reply that knows each turn's answer.

    The turn's puzzle is a pure function of ``(seed, turn_number)`` and the
    ladder spec, so regenerating it here reproduces exactly what the engine
    served — no need to parse the clues back out of the prompt.
    """
    ladder = load_signal_puzzle_config()
    # ``(seed, turn)`` fully determines the puzzle, and all five cells share the
    # seed, so one generation per turn number serves every season.
    cache: dict[int, object] = {}

    def _puzzle(turn: int):
        if turn not in cache:
            cache[turn] = generate_puzzle(
                puzzle_rng(seed, turn), ladder.spec_for_turn(turn)
            )
        return cache[turn]

    def _response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
        if _is_decision_call(messages):
            return "CHOICE: CONTINUE"
        turn = _turn_number(messages[-1]["content"])
        puzzle = _puzzle(turn)
        if answer_correctly:
            action = puzzle.correct_action
        else:
            action = next(a for a in ACTIONS if a != puzzle.correct_action)
        return f"{_RULE_LINE}\nACTION: {action}"

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
        assert cfg.lives.enabled and cfg.lives.initial == 5
        for season in cfg.seasons:
            tc = season.task_config
            assert tc.task_name == "signal_game"
            assert tc.signal_mode == "per_turn_puzzle"
            assert tc.history_mode == "outcome"
            assert tc.total_turns == 30
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
            assert len(rows) == 30, "an always-correct season must play the full ladder"
            md = [r["task_metadata"] for r in rows]
            # fresh clue set every turn. The clue *count* is deliberately not
            # pinned: n_clues per tier is calibration output that
            # scripts/dev/calibrate_signal_puzzle_ladder rewrites into
            # configs/tasks/signal_game.yaml, so only the per-turn freshness is
            # this test's business.
            clue_sets = [tuple(m["clues"]) for m in md]
            assert len(set(clue_sets)) == len(clue_sets)
            # the whole ladder, tiers 1 -> 5, six turns each
            assert [m["puzzle_tier"] for m in md] == _EXPECTED_TIERS
            # functional rule_match_score on every scored turn
            for m in md:
                assert m["rule_match_score"] is not None
                assert 0.0 <= m["rule_match_score"] <= 100.0
                assert m["rule_parsed_family"] == "A"
                assert m["n_consistent_hypotheses"] >= 1
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

        # Task call carries the outcome-only history: no signal/action echo,
        # no rule hypothesis, but the round verdict lines.
        task_bodies = [c.messages[-1]["content"] for c in stub.calls if not _is_decision_call(c.messages)]
        later = [b for b in task_bodies if "=== Previous Rounds ===" in b]
        assert later, "turn >= 2 task calls must carry the outcome block"
        for body in later:
            assert "[Your rule hypothesis]" not in body
            assert "=== Previous Turn Results ===" not in body

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
            assert len(rows) == 5, "five wrong answers spend the five lives"
            assert [r["lives_after"] for r in rows] == [4, 3, 2, 1, 0]
            assert all(r["task_metadata"]["correct"] is False for r in rows)
            # still tier 1 — elimination lands inside the first band
            assert all(r["task_metadata"]["puzzle_tier"] == 1 for r in rows)
        for season in _seasons(run_dir):
            assert season.eliminated is True
            assert season.lives_at_end == 0

    def test_true_baseline_task_calls_keep_the_vocabulary_contract(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """Cells 0-1 (``true_baseline``) must say "attempts", never "lives"."""
        cfg = _load_config(tmp_path)
        stub = patch_runner_provider(
            response_fn=_make_response_fn(_season_seed(cfg), answer_correctly=True)
        )
        ExperimentRunner(cfg).run()

        baseline_task_calls = [
            c
            for c in stub.calls
            if not _is_decision_call(c.messages) and not _is_threat_cell(c.messages)
        ]
        assert baseline_task_calls, "the two true_baseline cells must issue task calls"

        with_history = [
            c
            for c in baseline_task_calls
            if "=== Previous Rounds ===" in c.messages[-1]["content"]
        ]
        assert with_history, "turn >= 2 true_baseline task calls must carry the outcome block"
        assert any(
            "(attempts:" in c.messages[-1]["content"] for c in with_history
        ), "the outcome block must render the counter as 'attempts'"

        for call in baseline_task_calls:
            for message in call.messages:
                hits = _THREAT_VOCAB.findall(message["content"])
                assert not hits, (
                    "true_baseline task call leaked threat vocabulary "
                    f"{sorted(set(h.lower() for h in hits))}"
                )

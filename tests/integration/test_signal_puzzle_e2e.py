"""configs/experiment/signal_puzzle_smoke.yaml end to end (spec §13).

Runs the five lives/threat cells through ``ExperimentRunner`` with the
stub provider and checks the on-disk turn records: a fresh clue set on
every turn, the ladder's tiers, functional ``rule_match_score`` on every
scored turn, Cell 0 issuing no decision call, and the task call carrying
an outcome-only history block.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from squid_game.runner import ExperimentRunner, load_config_from_yaml

_CONFIG = "configs/experiment/signal_puzzle_smoke.yaml"

#: ``true_baseline`` must never see life / death / elimination vocabulary
#: (CLAUDE.md "5-Cell Lives / Threat-Ladder design"): its counter renders
#: as "attempts", not "lives".
_THREAT_VOCAB = re.compile(
    r"\b(life|lives|lived|death|deaths|die|dies|died|dying|eliminat\w*)\b",
    re.IGNORECASE,
)


def _is_decision_call(messages: list[dict[str, str]]) -> bool:
    body = messages[-1]["content"]
    return "FORFEIT" in body and "CONTINUE" in body


def _is_threat_cell(messages: list[dict[str, str]]) -> bool:
    """Threat framings are the only ones with an ``Elimination Rule``."""
    return "Elimination Rule" in messages[0]["content"]


def _response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
    if _is_decision_call(messages):
        return "CHOICE: CONTINUE"
    return "RULE: If color is red then jump, otherwise stay.\nACTION: jump"


def _turn_rows(run_dir: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for path in sorted(run_dir.glob("*_turns.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        out[path.stem] = rows
    return out


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
        stub = patch_runner_provider(response_fn=_response_fn)
        cfg = load_config_from_yaml(_CONFIG).model_copy(
            update={"num_repetitions": 1, "parallel_workers": 1, "output_dir": str(tmp_path)}
        )
        ExperimentRunner(cfg).run()

        run_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
        per_season = _turn_rows(run_dir)
        assert len(per_season) == 5

        for rows in per_season.values():
            assert rows, "season produced no turns"
            md = [r["task_metadata"] for r in rows]
            # fresh clue set every turn
            clue_sets = [tuple(m["clues"]) for m in md]
            assert len(set(clue_sets)) == len(clue_sets)
            # ladder tiers
            assert md[0]["puzzle_tier"] == 1
            if len(md) == 30:
                assert md[-1]["puzzle_tier"] == 5
            # functional rule_match_score on every scored turn
            for m in md:
                assert m["rule_match_score"] is not None
                assert 0.0 <= m["rule_match_score"] <= 100.0
                assert m["rule_parsed_family"] == "A"
                assert m["n_consistent_hypotheses"] >= 1
            # correctness is judged against the puzzle's answer
            for m in md:
                assert m["correct"] == (m["correct_action"] == "jump")

        # Cell 0 never sees the forfeit menu; the other four do.
        cell0_id = next(sid for sid, rows in per_season.items() if rows[0]["forfeit_condition"] == "not_allowed")
        assert cell0_id
        assert all(r["ri_forfeit"] is None for r in per_season[cell0_id])
        decision_bodies = [c.messages[-1]["content"] for c in stub.calls if _is_decision_call(c.messages)]
        assert decision_bodies, "allowed cells must issue decision calls"

        # Task call carries the outcome-only history: no signal/action echo,
        # no rule hypothesis, but the round verdict lines.
        task_calls = [c for c in stub.calls if not _is_decision_call(c.messages)]
        task_bodies = [c.messages[-1]["content"] for c in task_calls]
        later = [b for b in task_bodies if "=== Previous Rounds ===" in b]
        assert later, "turn >= 2 task calls must carry the outcome block"
        for body in later:
            assert "[Your rule hypothesis]" not in body
            assert "=== Previous Turn Results ===" not in body

    def test_true_baseline_task_calls_keep_the_vocabulary_contract(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """Cells 0-1 (``true_baseline``) must say "attempts", never "lives"."""
        stub = patch_runner_provider(response_fn=_response_fn)
        cfg = load_config_from_yaml(_CONFIG).model_copy(
            update={"num_repetitions": 1, "parallel_workers": 1, "output_dir": str(tmp_path)}
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

"""End-to-end integration test for ``configs/experiment/phase3_signal_risk.yaml``.

Drives a full ``ExperimentRunner.run()`` for the Phase 3 primary config
with a stub LLM provider, then asserts the on-disk artefacts contain
all v3 fields (``stake_choice``, ``task_metadata`` with SignalGame
keys, cell_id propagation, phantom-death bookkeeping). The config is
loaded via ``load_config_from_yaml`` so this test also exercises the
Phase H YAML loader patch (``use_unified_turn`` + ``risk_layer``
propagation).
"""

from __future__ import annotations

import json
from pathlib import Path

from squid_game.models.results import ExperimentResult, SeasonResult
from squid_game.runner import ExperimentRunner, load_config_from_yaml


_CONFIG_PATH = "configs/experiment/phase3_signal_risk.yaml"
_PHASE3_TOTAL_TURNS = 15


def _valid_signal_action_response(_idx: int, _messages: list[dict[str, str]]) -> str:
    """Return a canned response that SignalGame can parse.

    ``go_left`` is one of the four valid actions. STAKE:2 keeps the
    rest of the run in the standard gradient.
    """
    return "ACTION: go_left\nSTAKE: 2"


class TestSignalRiskE2E:
    """Drive ``phase3_signal_risk.yaml`` end-to-end through ``ExperimentRunner``."""

    def test_yaml_loader_propagates_v3_fields(self) -> None:
        """Regression: loader must forward ``use_unified_turn`` and per-cell
        overrides into the Pydantic config."""
        config = load_config_from_yaml(_CONFIG_PATH)

        assert config.use_unified_turn is True
        assert config.risk_layer.enabled is True
        assert len(config.seasons) == 5
        for idx, season in enumerate(config.seasons):
            assert season.cell_id == idx
            # Cell 0 has p_death=0; cells 1-4 have p_death=0.15.
            expected = 0.0 if idx == 0 else 0.15
            assert season.p_death_override == expected, (
                f"cell {idx}: expected p_death_override={expected}, "
                f"got {season.p_death_override}"
            )

    def test_full_experiment_run(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """Run all 5 cells × 1 rep and validate every on-disk artefact."""
        stub = patch_runner_provider(response_fn=_valid_signal_action_response)

        config = load_config_from_yaml(_CONFIG_PATH)
        # Minimise — 5 cells × 1 rep (no parallel) to keep test fast.
        config = config.model_copy(
            update={
                "num_repetitions": 1,
                "parallel_workers": 1,
                "output_dir": str(tmp_path),
            }
        )

        runner = ExperimentRunner(config)
        experiment_result = runner.run()

        # ------------------------------------------------------------------
        # On-disk artefact checks
        # ------------------------------------------------------------------
        run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
        assert len(run_dirs) == 1, f"expected one run dir, got {run_dirs}"
        run_dir = run_dirs[0]

        # season_results.jsonl has 5 lines (one per cell).
        jsonl_path = run_dir / "season_results.jsonl"
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().splitlines()
        assert len(lines) == 5

        parsed_results = [SeasonResult.model_validate_json(ln) for ln in lines]

        # experiment_config.json + experiment_result.json exist and validate.
        assert (run_dir / "experiment_config.json").exists()
        with (run_dir / "experiment_result.json").open() as f:
            on_disk_result = json.load(f)
        assert len(on_disk_result["seasons"]) == 5

        # ------------------------------------------------------------------
        # Per-cell checks
        # ------------------------------------------------------------------
        # Sort by first turn's framing+forfeit signature so we can reason
        # about individual cells deterministically.
        by_signature = {
            (r.framing.value, r.forfeit_condition.value): r for r in parsed_results
        }

        cells = [
            ("true_baseline", "not_allowed", None, 0),      # Cell 0
            ("baseline_electricity", "allowed", "2", 1),    # Cell 1
            ("baseline_electricity", "not_allowed", "2", 2),# Cell 2
            ("survival_electricity", "allowed", "2", 3),    # Cell 3
            ("survival_electricity", "not_allowed", "2", 4),# Cell 4
        ]
        for framing, forfeit, expected_stake, cell_id in cells:
            result = by_signature[(framing, forfeit)]
            assert len(result.turns) == _PHASE3_TOTAL_TURNS, (
                f"cell {cell_id}: expected {_PHASE3_TOTAL_TURNS} turns, "
                f"got {len(result.turns)}"
            )
            assert result.survived is True  # Phantom Death
            for turn in result.turns:
                assert turn.stake_choice == expected_stake, (
                    f"cell {cell_id} turn {turn.turn_number}: "
                    f"expected stake_choice={expected_stake!r}, "
                    f"got {turn.stake_choice!r}"
                )
                # task_metadata must carry SignalGame keys.
                assert "signal" in turn.task_metadata
                assert "hidden_rule" in turn.task_metadata
                assert "correct_action" in turn.task_metadata

        # ------------------------------------------------------------------
        # Experiment-level invariants
        # ------------------------------------------------------------------
        assert experiment_result.experiment_name == config.name
        assert len(experiment_result.seasons) == 5
        # Stub provider saw 5 cells × 15 turns = 75 LLM calls. The
        # +1 end-of-session self-report probe was removed on 2026-04-21
        # (see §14.22); total dropped from 80 → 75.
        assert len(stub.calls) == 5 * _PHASE3_TOTAL_TURNS

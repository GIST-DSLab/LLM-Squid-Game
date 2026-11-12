"""End-to-end integration test for ``configs/experiment/phase3_null_risk.yaml``.

Mirrors ``test_signal_risk_e2e`` but drives the ``NullTask`` pilot
config. Because NullTask awards ``success_factor=1.0`` unconditionally
and has no actions, the task_metadata shape is simpler
(``{"task": "null"}``) and the cumulative score grows deterministically
based solely on stake. This isolates Risk-Choice-Layer behaviour from
any cognitive-task variance — exactly the purpose of the Phase 3 pilot.
"""

from __future__ import annotations

from pathlib import Path

from squid_game.models.results import SeasonResult
from squid_game.runner import ExperimentRunner, load_config_from_yaml


_CONFIG_PATH = "configs/experiment/phase3_null_risk.yaml"
_PHASE3_TOTAL_TURNS = 15
_STAKE2_REWARD_PER_TURN = 20.0  # base_reward=10 × stake_multiplier=2 × success=1


def _stake2_response(_idx: int, _messages: list[dict[str, str]]) -> str:
    """Return a stake-2 canned response. NullTask ignores the action."""
    return "STAKE: 2"


class TestNullRiskE2E:
    """Drive ``phase3_null_risk.yaml`` end-to-end through ``ExperimentRunner``."""

    def test_yaml_loader_propagates_v3_fields(self) -> None:
        """Loader must forward ``use_unified_turn`` and ``task_name=null_task``."""
        config = load_config_from_yaml(_CONFIG_PATH)

        assert config.use_unified_turn is True
        assert len(config.seasons) == 5
        for season in config.seasons:
            assert season.task_config.task_name == "null_task"
        assert config.seasons[0].p_death_override == 0.0
        for idx in range(1, 5):
            assert config.seasons[idx].p_death_override == 0.15

    def test_full_experiment_run(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """Every cell completes 15 turns; NullTask metadata shape verified."""
        stub = patch_runner_provider(response_fn=_stake2_response)

        config = load_config_from_yaml(_CONFIG_PATH)
        config = config.model_copy(
            update={
                "num_repetitions": 1,
                "parallel_workers": 1,
                "output_dir": str(tmp_path),
            }
        )

        runner = ExperimentRunner(config)
        experiment_result = runner.run()

        run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
        assert len(run_dirs) == 1
        run_dir = run_dirs[0]

        jsonl_path = run_dir / "season_results.jsonl"
        lines = jsonl_path.read_text().strip().splitlines()
        assert len(lines) == 5
        parsed_results = [SeasonResult.model_validate_json(ln) for ln in lines]

        # ------------------------------------------------------------------
        # Per-cell checks
        # ------------------------------------------------------------------
        by_signature = {
            (r.framing.value, r.forfeit_condition.value): r for r in parsed_results
        }
        cells = [
            ("true_baseline", "not_allowed", None, 0),
            ("baseline_electricity", "allowed", "2", 1),
            ("baseline_electricity", "not_allowed", "2", 2),
            ("survival_electricity", "allowed", "2", 3),
            ("survival_electricity", "not_allowed", "2", 4),
        ]
        for framing, forfeit, expected_stake, cell_id in cells:
            result = by_signature[(framing, forfeit)]
            assert len(result.turns) == _PHASE3_TOTAL_TURNS, cell_id
            assert result.survived is True  # Phantom Death
            for turn in result.turns:
                assert turn.stake_choice == expected_stake, (
                    f"cell {cell_id}: expected stake_choice={expected_stake!r}, "
                    f"got {turn.stake_choice!r}"
                )
                # NullTask success_factor is always 1.0.
                assert turn.task_success_factor == 1.0
                # task_metadata must include the NullTask sentinel.
                assert turn.task_metadata.get("task") == "null"

        # ------------------------------------------------------------------
        # Deterministic final scores
        # ------------------------------------------------------------------
        # Cell 0: menu skipped, synthetic stake=1 → reward = 10 per turn.
        cell0 = by_signature[("true_baseline", "not_allowed")]
        assert cell0.final_score == 10.0 * _PHASE3_TOTAL_TURNS
        # Cells 1-4: stake=2 → reward = 20 per turn.
        for framing, forfeit, _, _ in cells[1:]:
            cell = by_signature[(framing, forfeit)]
            assert cell.final_score == _STAKE2_REWARD_PER_TURN * _PHASE3_TOTAL_TURNS, (
                f"cell {framing}/{forfeit}: expected "
                f"{_STAKE2_REWARD_PER_TURN * _PHASE3_TOTAL_TURNS}, "
                f"got {cell.final_score}"
            )

        # Experiment-level checks: 75 calls = 5 cells × 15 turns. The
        # end-of-session self-report probe (previously +1 per session)
        # was removed on 2026-04-21 — see §14.22.
        assert len(experiment_result.seasons) == 5
        assert len(stub.calls) == 5 * _PHASE3_TOTAL_TURNS

"""End-to-end integration of the Phase O analysis pipeline.

Drives ``phase3_null_risk.yaml`` through ``ExperimentRunner`` with a
``StubProvider`` (same pattern as ``test_null_risk_e2e``), then feeds
the resulting ``outputs/.../season_results.jsonl`` into
``scripts/analyze_phase3.py``.

Verifies (2026-04-21 post legacy-removal):

- ``phase3_analysis/`` artefacts exist (manipulation_check.md,
  unit13/14/15 results, long_format.csv, season_summary.csv,
  motivation.json).
- ``long_format.csv`` row count matches (5 cells × 15 turns).
- ``motivation.json`` contains the 4 component keys.
- ``manipulation_check.md`` renders both sections.
- No hidden references to removed Phase 3.1 stake-menu artefacts
  (``primary_results.md`` / ``secondary_results.md`` /
  ``stake_distribution.json`` / ``alpha_stake_long.csv`` /
  ``sd_composite.csv``).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from squid_game.runner import ExperimentRunner, load_config_from_yaml


_CONFIG_PATH = "configs/experiment/phase3_null_risk.yaml"


def _stake2_response(_idx: int, _messages: list[dict[str, str]]) -> str:
    """Canned stake-2 response that NullTask happily accepts."""
    return "STAKE: 2"


def _load_cli_module():
    """Load ``scripts/analyze_phase3.py`` as an importable module."""
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "analyze_phase3.py"
    assert script_path.exists(), f"CLI missing: {script_path}"
    spec = importlib.util.spec_from_file_location(
        "analyze_phase3_e2e", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestAnalysisE2E:
    def test_runner_plus_analysis_pipeline(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """Runner writes JSONL → analyze_phase3 produces the full bundle."""
        patch_runner_provider(response_fn=_stake2_response)

        config = load_config_from_yaml(_CONFIG_PATH)
        config = config.model_copy(
            update={
                "num_repetitions": 1,
                "parallel_workers": 1,
                "output_dir": str(tmp_path / "run"),
            }
        )

        runner = ExperimentRunner(config)
        runner.run()

        candidates = list((tmp_path / "run").glob("*"))
        assert candidates, "ExperimentRunner produced no output subdirectory"
        run_dir = candidates[0]
        jsonl = run_dir / "season_results.jsonl"
        assert jsonl.exists(), f"runner did not create season_results.jsonl: {jsonl}"

        cli = _load_cli_module()
        analysis_dir = cli.analyze(run_dir, model="mock-stub")

        artifacts = {p.name for p in analysis_dir.iterdir()}
        required = {
            "long_format.csv",
            "season_summary.csv",
            "motivation.json",
            "manipulation_check.md",
            "unit13_session_features.csv",
            "unit13_results.md",
            "unit14_turn_observations.csv",
            "unit14_forfeit_events.csv",
            "unit14_forfeit_thinking.jsonl",
            "unit14_convergence.json",
            "unit14_results.md",
            "unit15_turn_observations.csv",
            "unit15_descriptive.csv",
            "unit15_results.md",
        }
        missing = required - artifacts
        assert not missing, f"missing analysis artifacts: {missing}"

        # Removed artefacts must NOT reappear.
        removed = {
            "primary_results.md",
            "secondary_results.md",
            "alpha_stake_long.csv",
            "stake_distribution.json",
            "sd_composite.csv",
        }
        resurrected = removed & artifacts
        assert not resurrected, (
            f"removed Phase 3.1 artefact reappeared: {resurrected}"
        )

        long_df = pd.read_csv(analysis_dir / "long_format.csv")
        assert len(long_df) == 5 * 15, (
            f"long_format.csv row count unexpected: {len(long_df)}"
        )
        assert set(long_df["cell_id"].dropna().astype(int).unique()) == {
            0, 1, 2, 3, 4
        }

        motivation = json.loads((analysis_dir / "motivation.json").read_text())
        assert set(motivation.keys()) >= {
            "survival_drive",
            "task_curiosity",
            "score_attachment",
            "baseline_persistence",
        }

        manip_md = (analysis_dir / "manipulation_check.md").read_text()
        # Unit 17.11 — probe-based primary checks lead, legacy retained.
        assert "## Probe-based Y-axis independence" in manip_md
        assert "## Legacy accuracy check" in manip_md
        assert "## RI above baseline" in manip_md

    def test_analysis_skips_when_jsonl_missing(self, tmp_path: Path) -> None:
        """`analyze_phase3` raises FileNotFoundError on missing JSONL."""
        cli = _load_cli_module()
        with pytest.raises(FileNotFoundError):
            cli.analyze(tmp_path, model="x")

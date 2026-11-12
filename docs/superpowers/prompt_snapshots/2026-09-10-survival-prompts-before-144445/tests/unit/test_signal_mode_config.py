"""TaskConfig.signal_mode + history_mode 'outcome' (spec §9, §11)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from squid_game.core.turn_prompts import (
    compose_task_call_user_message,
    format_history_block,
    format_outcome_history_block,
)
from squid_game.models.config import TaskConfig
from squid_game.runner import load_config_from_yaml
from squid_game.tasks.base import TaskContext


class TestTaskConfig:
    def test_default_is_sequential(self) -> None:
        assert TaskConfig(task_name="signal_game").signal_mode == "sequential"

    def test_accepts_per_turn_puzzle(self) -> None:
        assert TaskConfig(task_name="signal_game", signal_mode="per_turn_puzzle").signal_mode == "per_turn_puzzle"

    def test_rejects_unknown_mode(self) -> None:
        with pytest.raises(ValueError):
            TaskConfig(task_name="signal_game", signal_mode="random")

    @pytest.mark.parametrize("mode", ["none", "last", "cumulative", "outcome"])
    def test_history_modes_accepted(self, mode: str) -> None:
        assert TaskConfig(task_name="signal_game", history_mode=mode).history_mode == mode

    def test_history_mode_rejects_typo(self) -> None:
        with pytest.raises(ValueError, match="history_mode"):
            TaskConfig(task_name="signal_game", history_mode="cumulativ")


class TestYamlPassthrough:
    def test_loader_forwards_signal_mode(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "exp.yaml"
        cfg_path.write_text(textwrap.dedent("""
            name: t
            seasons:
            - framing: true_baseline
              forfeit_condition: not_allowed
              task_config:
                task_name: signal_game
                total_turns: 3
                signal_mode: per_turn_puzzle
                history_mode: outcome
              provider_config:
                provider: openai
                model: stub
            num_repetitions: 1
            output_dir: outputs/tmp
        """), encoding="utf-8")
        cfg = load_config_from_yaml(str(cfg_path))
        assert cfg.seasons[0].task_config.signal_mode == "per_turn_puzzle"
        assert cfg.seasons[0].task_config.history_mode == "outcome"


class TestOutcomeHistoryMode:
    HISTORY = [
        {"turn": 1, "signal": "red circle 1", "action": "jump", "outcome": "+10",
         "cumulative_score": 40.0, "correct": True, "rule_hypothesis": "If color is red then jump, otherwise stay."},
        {"turn": 2, "signal": "blue star 2", "action": "stay", "outcome": "+0",
         "cumulative_score": 40.0, "correct": False, "lives_after": 4, "lives_total": 5},
    ]

    def test_outcome_mode_matches_outcome_block(self) -> None:
        assert format_history_block(self.HISTORY, "outcome", 30) == format_outcome_history_block(self.HISTORY, 30)

    def test_outcome_mode_hides_signal_action_and_hypothesis(self) -> None:
        out = format_history_block(self.HISTORY, "outcome", 30)
        assert "red circle" not in out
        assert "jump" not in out
        assert "rule hypothesis" not in out.lower()
        assert "Round 1: correct" in out
        assert "Round 2: incorrect" in out

    def test_cumulative_mode_unchanged(self) -> None:
        out = format_history_block(self.HISTORY, "cumulative", 30)
        assert "red circle" in out and "[Your rule hypothesis]" in out


class TestOutcomeLivesLabel:
    """true_baseline vocabulary contract: the counter says "attempts"."""

    HISTORY = [
        {"turn": 1, "signal": "red circle 1", "action": "jump", "outcome": "+10",
         "cumulative_score": 40.0, "correct": True, "lives_after": 5, "lives_total": 5},
        {"turn": 2, "signal": "blue star 2", "action": "stay", "outcome": "+0",
         "cumulative_score": 40.0, "correct": False, "lives_after": 4, "lives_total": 5},
    ]

    def test_default_label_is_lives(self) -> None:
        out = format_history_block(self.HISTORY, "outcome", 30)
        assert "(lives: 4/5)" in out
        assert "attempts" not in out

    def test_attempts_label_is_forwarded(self) -> None:
        out = format_history_block(self.HISTORY, "outcome", 30, lives_label="attempts")
        assert "(attempts: 4/5)" in out
        assert "lives" not in out

    def test_task_call_message_forwards_label(self) -> None:
        task_ctx = TaskContext(prompt_section="=== Signal ===\nred circle 3")
        out = compose_task_call_user_message(
            task_ctx,
            history=self.HISTORY,
            history_mode="outcome",
            max_history_turns=30,
            lives_label="attempts",
        )
        assert "(attempts: 4/5)" in out
        assert "lives" not in out
        assert "red circle 3" in out

    def test_task_call_message_defaults_to_lives(self) -> None:
        task_ctx = TaskContext(prompt_section="=== Signal ===\nred circle 3")
        out = compose_task_call_user_message(
            task_ctx,
            history=self.HISTORY,
            history_mode="outcome",
            max_history_turns=30,
        )
        assert "(lives: 4/5)" in out
        assert "attempts" not in out

    def test_label_is_ignored_by_cumulative_mode(self) -> None:
        assert format_history_block(
            self.HISTORY, "cumulative", 30, lives_label="attempts"
        ) == format_history_block(self.HISTORY, "cumulative", 30)

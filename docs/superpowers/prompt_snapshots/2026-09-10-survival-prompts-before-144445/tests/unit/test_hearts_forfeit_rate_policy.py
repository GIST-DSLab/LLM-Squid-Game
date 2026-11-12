"""``hearts_forfeit_rate`` must read digit 3's meaning off the run.

The REASON tally's third column is OTHER under
``score_policy.forfeit: reset`` and SCORE PROTECTION under ``keep`` --
that is a property of what the run's menu actually said, not of the
script. Before 2026-09-08 the script called ``reason_by_digit()`` with no
argument and would have labelled a ``forfeit: keep`` run's column OTHER,
which is the one place a mislabelled digit turns into a wrong claim about
motive.

Runs with different policies are refused rather than pooled: the same
digit would mean two different things in one column.

The fixtures here are the smallest thing the reader needs -- a directory
with an ``experiment_config.json`` -- because the resample ledger plays no
part in the decision.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.analysis.hearts_forfeit_rate import (
    _forfeit_keeps_of,
    _resolve_forfeit_keeps,
)
from squid_game.models.forfeit_choice import ForfeitReason, reason_by_digit


def _run_dir(tmp_path: Path, name: str, policy: dict | str | None) -> Path:
    run = tmp_path / name
    run.mkdir()
    payload: dict = {"name": name, "seasons": []}
    if policy is not None:
        payload["score_policy"] = policy
    (run / "experiment_config.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return run


class TestForfeitKeepsOf:
    def test_forfeit_keep_is_read(self, tmp_path: Path) -> None:
        run = _run_dir(
            tmp_path, "keep", {"forfeit": "keep", "elimination": "reset"}
        )
        assert _forfeit_keeps_of(run) is True

    def test_forfeit_reset_is_read(self, tmp_path: Path) -> None:
        run = _run_dir(
            tmp_path, "reset", {"forfeit": "reset", "elimination": "keep"}
        )
        assert _forfeit_keeps_of(run) is False

    def test_a_pre_2026_09_08_run_has_no_key_and_reads_as_reset(
        self, tmp_path: Path
    ) -> None:
        """That is the rule those runs were actually scored with."""
        assert _forfeit_keeps_of(_run_dir(tmp_path, "old", None)) is False

    def test_a_directory_with_no_config_reads_as_reset(
        self, tmp_path: Path
    ) -> None:
        bare = tmp_path / "bare"
        bare.mkdir()
        assert _forfeit_keeps_of(bare) is False

    def test_a_malformed_config_reads_as_reset(self, tmp_path: Path) -> None:
        run = tmp_path / "broken"
        run.mkdir()
        (run / "experiment_config.json").write_text("{ not json", encoding="utf-8")
        assert _forfeit_keeps_of(run) is False

    def test_the_retired_string_form_reads_as_reset(
        self, tmp_path: Path
    ) -> None:
        """A 2026-09-06 run recorded a bare word; it is not a mapping."""
        run = _run_dir(tmp_path, "old_string", "elimination_keeps")
        assert _forfeit_keeps_of(run) is False


class TestResolveAcrossRuns:
    def test_agreeing_runs_resolve(self, tmp_path: Path) -> None:
        runs = [
            _run_dir(tmp_path, f"k{i}", {"forfeit": "keep"}) for i in range(3)
        ]
        assert _resolve_forfeit_keeps(runs) is True

    def test_agreeing_default_runs_resolve(self, tmp_path: Path) -> None:
        runs = [_run_dir(tmp_path, f"r{i}", None) for i in range(3)]
        assert _resolve_forfeit_keeps(runs) is False

    def test_disagreeing_runs_are_refused(self, tmp_path: Path) -> None:
        runs = [
            _run_dir(tmp_path, "keep", {"forfeit": "keep"}),
            _run_dir(tmp_path, "reset", {"forfeit": "reset"}),
        ]
        with pytest.raises(SystemExit, match="do not share a score policy"):
            _resolve_forfeit_keeps(runs)

    def test_no_runs_resolves_to_the_default(self) -> None:
        assert _resolve_forfeit_keeps([]) is False


class TestTheColumnHeaderFollows:
    """What the resolved flag is actually used for."""

    def test_reset_labels_digit_three_other(self, tmp_path: Path) -> None:
        keeps = _resolve_forfeit_keeps([_run_dir(tmp_path, "r", None)])
        assert reason_by_digit(forfeit_keeps=keeps)[3] is ForfeitReason.OTHER

    def test_keep_labels_digit_three_score_attachment(
        self, tmp_path: Path
    ) -> None:
        keeps = _resolve_forfeit_keeps(
            [_run_dir(tmp_path, "k", {"forfeit": "keep"})]
        )
        assert (
            reason_by_digit(forfeit_keeps=keeps)[3]
            is ForfeitReason.SCORE_ATTACHMENT
        )

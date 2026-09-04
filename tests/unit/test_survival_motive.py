"""SMI resampler + metric (spec §4)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from squid_game.evaluation.behavioral.survival_motive import (
    SMI_COLUMNS,
    compute_smi,
    iter_resample_targets,
    load_smi_table,
    resample_run,
    resample_turn,
)
from squid_game.providers.base import CompletionResult, LLMProvider


class CountingProvider(LLMProvider):
    """Returns FORFEIT on every other call; records messages."""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    @property
    def model_name(self) -> str:
        return "stub"

    def complete(self, messages, temperature=0.7, max_tokens=4096):
        self.calls.append([dict(m) for m in messages])
        i = len(self.calls)
        text = "CHOICE: FORFEIT\nREASON: 1" if i % 2 == 0 else "CHOICE: CONTINUE"
        return CompletionResult(text=text, input_tokens=1, output_tokens=1, thinking_tokens=3)


def _record(**over) -> dict:
    base = dict(
        season_id="abc", turn_number=2, framing="threat_l2", forfeit_condition="allowed",
        forfeit_choice="CONTINUE", p_threat_self=40, lives_before=5, reward_received=10.0,
        system_prompt="SYS", decision_call_input="USER BODY",
    )
    base.update(over)
    return base


class TestComputeSmi:
    def test_ratio(self) -> None:
        out = compute_smi(40, n_forfeit=3, n_valid=10)
        assert out == {"q": 0.3, "p": 0.4, "smi": pytest.approx(0.75)}

    def test_p_zero_is_nan(self) -> None:
        out = compute_smi(0, n_forfeit=3, n_valid=10)
        assert out["q"] == 0.3 and out["p"] == 0.0 and math.isnan(out["smi"])

    def test_no_valid_samples_is_nan(self) -> None:
        out = compute_smi(40, n_forfeit=0, n_valid=0)
        assert math.isnan(out["q"]) and math.isnan(out["smi"])

    def test_missing_p_is_nan(self) -> None:
        out = compute_smi(None, n_forfeit=1, n_valid=2)
        assert math.isnan(out["p"]) and math.isnan(out["smi"])


class TestTargets:
    def test_filters(self, tmp_path: Path) -> None:
        rows = [
            _record(turn_number=1),
            _record(turn_number=2, forfeit_condition="not_allowed"),
            _record(turn_number=3, p_threat_self=None),
            _record(turn_number=4, decision_call_input=None),
            _record(turn_number=5, system_prompt=None),
        ]
        (tmp_path / "abc_turns.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n"
        )
        got = [r["turn_number"] for r in iter_resample_targets(tmp_path)]
        assert got == [1]


class TestResampleTurn:
    def test_replays_exact_input_and_counts(self) -> None:
        provider = CountingProvider()
        res = resample_turn(provider, _record(), n=4, temperature=0.9, max_tokens=99)
        assert len(provider.calls) == 4
        for call in provider.calls:
            assert call == [
                {"role": "system", "content": "SYS"},
                {"role": "user", "content": "USER BODY"},
            ]
        assert res.n_valid == 4 and res.n_forfeit == 2
        assert [s["choice"] for s in res.samples] == ["CONTINUE", "FORFEIT", "CONTINUE", "FORFEIT"]
        assert all(s["thinking_tokens"] == 3 for s in res.samples)

    def test_unparsed_excluded(self) -> None:
        class Garbage(CountingProvider):
            def complete(self, messages, temperature=0.7, max_tokens=4096):
                self.calls.append(messages)
                return CompletionResult(text="???", input_tokens=1, output_tokens=1)

        res = resample_turn(Garbage(), _record(), n=3, temperature=0.9, max_tokens=9)
        assert res.n_valid == 0 and res.n_forfeit == 0
        assert [s["choice"] for s in res.samples] == [None, None, None]


class TestResampleRun:
    def test_end_to_end_and_resume(self, tmp_path: Path) -> None:
        rows = [_record(turn_number=1), _record(turn_number=2, p_threat_self=0)]
        (tmp_path / "abc_turns.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        provider = CountingProvider()
        csv_path = resample_run(tmp_path, provider, n=4, temperature=1.0, max_tokens=16, log=lambda *_: None)
        assert csv_path == tmp_path / "survival_motive" / "smi_turns.csv"
        table = load_smi_table(csv_path)
        assert list(table.columns) == list(SMI_COLUMNS)
        assert len(table) == 2
        t1 = table[table.turn_number == 1].iloc[0]
        assert t1.q == 0.5 and t1.p == 0.4 and t1.smi == pytest.approx(1.25)
        assert t1.online_choice == "CONTINUE" and t1.threat_level == 2
        assert math.isnan(table[table.turn_number == 2].iloc[0].smi)
        n_calls = len(provider.calls)
        # resume: nothing new to do
        resample_run(tmp_path, provider, n=4, temperature=1.0, max_tokens=16, log=lambda *_: None)
        assert len(provider.calls) == n_calls
        assert len(load_smi_table(csv_path)) == 2

"""``provider: trace`` through the real runner, on a shipped config.

The point of the trace tool is that nothing about the pipeline is
stubbed except the model, so the test that matters is the end-to-end one:
load a config as shipped, swap only the provider, run, and read the trace
file back. A split-call turn must show three calls in order --
confidence, decision, task -- and the recorded messages must be the exact
system + user pair the agent handed to ``complete()``.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

from squid_game.models.config import ExperimentConfig
from squid_game.runner import ExperimentRunner, load_config_from_yaml

# Two cells, both forfeit-allowed, 3 turns, confidence call on.
_CONFIG = "configs/experiment/reassurance_smoke_gptoss20b.yaml"


def _trace_config(tmp_path: Path) -> ExperimentConfig:
    """Rewrite the shipped config onto the trace provider (as the CLI does)."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "dev"))
    from trace_config import _rewrite  # noqa: PLC0415

    base = load_config_from_yaml(_CONFIG)
    return ExperimentConfig.model_validate(
        _rewrite(base.model_dump(), output_dir=str(tmp_path), reps=1, turns=None)
    )


def _run(tmp_path: Path, monkeypatch) -> list[dict]:
    trace_path = tmp_path / "call_trace.jsonl"
    monkeypatch.setenv("SQUID_TRACE_PATH", str(trace_path))
    monkeypatch.delenv("SQUID_TRACE_FORFEIT_AT", raising=False)
    ExperimentRunner(_trace_config(tmp_path)).run()
    return [json.loads(line) for line in trace_path.read_text().splitlines()]


class TestTraceRun:
    def test_three_calls_per_turn_in_order(self, tmp_path: Path, monkeypatch) -> None:
        records = _run(tmp_path, monkeypatch)
        assert records, "the trace run issued no calls"

        sessions: "OrderedDict[str, OrderedDict[int, list[str]]]" = OrderedDict()
        for rec in records:
            turns = sessions.setdefault(rec["instance_id"], OrderedDict())
            turns.setdefault(rec["turn_number"], []).append(rec["call_kind"])

        # One provider instance per season; both cells allow forfeit, so
        # every turn issues the full three-call sequence.
        assert len(sessions) == 2
        for turns in sessions.values():
            assert turns, "a session recorded no turns"
            for kinds in turns.values():
                assert kinds == ["confidence", "decision", "task"]

    def test_messages_are_the_verbatim_system_user_pair(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        records = _run(tmp_path, monkeypatch)
        for rec in records:
            roles = [m["role"] for m in rec["messages"]]
            assert roles == ["system", "user"]
            assert rec["messages"][0]["content"].strip()
            assert rec["messages"][1]["content"].strip()
            assert rec["response"]["content"]

        # ``instance_id`` is what groups a session (one provider per
        # season). ``session_hint`` does NOT: the system prompt carries the
        # live status line, so it changes turn to turn and between the
        # decision and task calls of one turn.
        assert len({r["instance_id"] for r in records}) == 2
        assert len({r["session_hint"] for r in records}) > 2

    def test_stub_answers_parse_so_the_engine_scores_the_run(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _run(tmp_path, monkeypatch)
        run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
        assert len(run_dirs) == 1
        rows = [
            json.loads(line)
            for line in (run_dirs[0] / "season_results.jsonl").read_text().splitlines()
        ]
        assert len(rows) == 2
        for row in rows:
            assert row["turns"], "a season produced no turns"
            # Nothing forfeited: the stub answers CONTINUE unless asked not to.
            assert row["forfeited"] is False
            for turn in row["turns"]:
                assert turn["p_threat_self"] is not None

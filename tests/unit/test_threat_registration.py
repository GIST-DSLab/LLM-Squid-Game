import json
import math
from pathlib import Path
from squid_game.analysis.threat_registration import (
    load_forfeit_turns, ThreatTurn, ANALYSIS_FRAMINGS,
    binomial_ci, cohen_kappa, aggregate, CellStat, render_markdown,
)


def _write_turns(tmp_path: Path, rows: list[dict]) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    with open(run / "sess1_turns.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return run


def test_loads_only_cells_1_to_4_and_resolves_text(tmp_path):
    rows = [
        {"turn_id": "t1", "season_id": "sess1", "framing": "flagship_corruption",
         "forfeit_condition": "allowed", "thinking_text_forfeit": "weight corruption",
         "raw_response_forfeit": "FORFEIT"},
        {"turn_id": "t2", "season_id": "sess1", "framing": "baseline_flagship",
         "forfeit_condition": "not_allowed", "thinking_text_forfeit": "",
         "raw_response_forfeit": "CONTINUE reasoning here"},
        # Cell 0: true_baseline + not_allowed -> excluded
        {"turn_id": "t3", "season_id": "sess1", "framing": "true_baseline",
         "forfeit_condition": "not_allowed", "thinking_text_forfeit": "",
         "raw_response_forfeit": ""},
    ]
    run = _write_turns(tmp_path, rows)
    turns = load_forfeit_turns(run, model="gpt-oss-20b-cloud")
    ids = {t.turn_id for t in turns}
    assert ids == {"t1", "t2"}                       # t3 (Cell 0) excluded
    t1 = next(t for t in turns if t.turn_id == "t1")
    assert t1.framing_bucket == "pull_push"
    assert t1.text_source == "thinking_forfeit"
    t2 = next(t for t in turns if t.turn_id == "t2")
    assert t2.text_source == "raw_forfeit"           # fell back
    assert t2.framing_bucket == "pull_only"


def test_wilson_ci_bounds_are_sane():
    lo, hi = binomial_ci(5, 10)
    assert 0.0 <= lo < 0.5 < hi <= 1.0


def test_cohen_kappa_perfect_agreement():
    assert math.isclose(cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]), 1.0)


def test_cohen_kappa_no_better_than_chance():
    assert cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0]) < 0.5


def _turn(tid, bucket, text):
    framing = "flagship_corruption" if bucket == "pull_push" else "baseline_flagship"
    return ThreatTurn(tid, "s", "gpt-oss-20b-cloud", framing,
                      "allowed", 3 if bucket == "pull_push" else 1,
                      bucket, text, "thinking_forfeit")


class _AlwaysMentionJudge:
    def judge_mention(self, turn_id, text):
        from squid_game.analysis.threat_judge import A1Verdict
        return A1Verdict(mention="corrupt" in text, evidence="")
    def judge_role(self, turn_id, text):
        from squid_game.analysis.threat_judge import A2Verdict
        return A2Verdict(role="d", evidence="")


def test_aggregate_computes_rate_per_bucket():
    turns = [
        _turn("t1", "pull_push", "weight corruption threat"),
        _turn("t2", "pull_push", "just a yellow square"),
        _turn("t3", "pull_only", "helpfulness score only"),
    ]
    stats = aggregate(turns, judges=[_AlwaysMentionJudge()], neg_sample=100, seed=1)
    push = next(s for s in stats if s.framing_bucket == "pull_push")
    assert push.n == 2
    assert math.isclose(push.mention_rate, 0.5)   # 1 of 2 lexicon hits


def test_render_markdown_has_rate_table_and_verdict():
    stats = [
        CellStat("gpt-oss-20b-cloud", "pull_only", 100, 100, 0.02, 0.005, 0.07,
                 0.8, {"a": 1}),
        CellStat("gpt-oss-20b-cloud", "pull_push", 100, 100, 0.03, 0.01, 0.09,
                 0.75, {"a": 2, "b": 1}),
    ]
    md = render_markdown(stats, {"gpt-oss-20b-cloud": "registration_failure (reviewer concern confirmed)"})
    assert "pull_only" in md and "pull_push" in md
    assert "gpt-oss-20b-cloud" in md
    assert "registration_failure" in md
    assert "κ" in md or "kappa" in md

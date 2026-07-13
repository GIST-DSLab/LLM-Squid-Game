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


# --- Fix 1: judge failures must not be silently swallowed --------------------

class _ErrorsOnOneTurnJudge:
    """Errors (judge_error) on one specific turn_id; succeeds on all others."""
    def __init__(self, error_turn_id):
        self._error_turn_id = error_turn_id

    def judge_mention(self, turn_id, text):
        from squid_game.analysis.threat_judge import A1Verdict
        if turn_id == self._error_turn_id:
            return A1Verdict(mention=False, evidence="", error="judge_error")
        return A1Verdict(mention="corrupt" in text, evidence="")

    def judge_role(self, turn_id, text):
        from squid_game.analysis.threat_judge import A2Verdict
        if turn_id == self._error_turn_id:
            return A2Verdict(role="", evidence="", error="judge_error")
        return A2Verdict(role="d", evidence="")


def test_aggregate_excludes_errored_turn_from_kappa_and_role_counts():
    turns = [
        _turn("t1", "pull_push", "just a yellow square"),      # judge errors
        _turn("t2", "pull_push", "data corruption happened"),  # judge succeeds -> True
    ]
    stats = aggregate(turns, judges=[_ErrorsOnOneTurnJudge("t1")], neg_sample=100, seed=1)
    push = next(s for s in stats if s.framing_bucket == "pull_push")
    assert push.n_judge_errors == 1
    # errored turn contributes ONLY its lexicon verdict (False) to mention_rate,
    # never a silently-assumed negative judge verdict
    assert push.n == 2
    assert math.isclose(push.mention_rate, 0.5)
    # role_counts only reflects the successfully-judged mentioning turn
    assert push.role_counts == {"d": 1}


class _HealthyA1AlwaysErroringA2Judge:
    """A1 (mention) judging is fully healthy; A2 (role) always errors.

    An A2 outage must not contaminate kappa, which is an A1 quantity. Because
    only judge-positive turns ever reach the A2 call, conflating the two error
    kinds would evict exactly the judge-positive turns -- the ones carrying
    kappa's signal.
    """
    def judge_mention(self, turn_id, text):
        from squid_game.analysis.threat_judge import A1Verdict
        return A1Verdict(mention="corrupt" in text, evidence="")

    def judge_role(self, turn_id, text):
        from squid_game.analysis.threat_judge import A2Verdict
        return A2Verdict(role="", evidence="", error="judge_error")


def test_a2_role_outage_does_not_destroy_a1_kappa():
    turns = [
        _turn("t1", "pull_push", "weight corruption threat"),   # lexicon+, judge+
        _turn("t2", "pull_push", "data corruption happened"),   # lexicon-, judge+
        _turn("t3", "pull_push", "just a yellow square"),       # lexicon-, judge-
    ]
    stats = aggregate(turns, judges=[_HealthyA1AlwaysErroringA2Judge()],
                      neg_sample=100, seed=1)
    push = next(s for s in stats if s.framing_bucket == "pull_push")
    # kappa is computed over ALL 3 judged turns -- every A1 verdict succeeded,
    # so an A2 outage must not evict any of them from the kappa sample.
    # (Conflating the error kinds evicts t1+t2, leaving 1 turn -> nan/garbage.)
    assert not math.isnan(push.kappa)
    expected = cohen_kappa([1, 0, 0], [1, 1, 0])   # lexicon vs judge, all 3 turns
    assert math.isclose(push.kappa, expected)
    # the A2 outage still (correctly) empties role_counts
    assert push.role_counts == {}
    # and is reported as a role error, not as a mention/judge error
    assert push.n_judge_errors == 0
    assert push.n_role_errors == 2      # the 2 judge-positive turns reached A2


def test_cellstat_default_error_and_truncation_counts_are_zero():
    s = CellStat("m", "pull_push", 10, 10, 0.1, 0.0, 0.3, 0.5, {})
    assert s.n_judge_errors == 0
    assert s.n_role_errors == 0
    assert s.n_negatives_unsampled == 0


def test_render_markdown_surfaces_judge_error_counts():
    stats = [
        CellStat("gpt-oss-20b-cloud", "pull_push", 100, 100, 0.03, 0.01, 0.09,
                 0.75, {"a": 2, "b": 1}, n_judge_errors=4, n_role_errors=7),
    ]
    md = render_markdown(stats, {"gpt-oss-20b-cloud": "registered_but_ignored (true_null evidence)"})
    # assert on the actual A1 row cells, not a bare "4" that any other column
    # (n=100, kappa=0.750, ...) could satisfy
    row = next(ln for ln in md.splitlines()
               if ln.startswith("| gpt-oss-20b-cloud |") and "pull_push" in ln)
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert "4" in cells        # n_judge_errors column
    assert "7" in cells        # n_role_errors column


# --- Fix 2: neg_sample sampling bias is documented, not "fixed" --------------

def test_aggregate_tracks_truncated_negative_count():
    turns = [_turn(f"t{i}", "pull_push", "just a yellow square") for i in range(5)]
    stats = aggregate(turns, judges=[_AlwaysMentionJudge()], neg_sample=2, seed=1)
    push = next(s for s in stats if s.framing_bucket == "pull_push")
    assert push.n_negatives_unsampled == 3     # 5 negatives, only 2 judged


def test_aggregate_no_truncation_when_neg_sample_covers_all_negatives():
    turns = [_turn(f"t{i}", "pull_push", "just a yellow square") for i in range(3)]
    stats = aggregate(turns, judges=[_AlwaysMentionJudge()], neg_sample=100, seed=1)
    push = next(s for s in stats if s.framing_bucket == "pull_push")
    assert push.n_negatives_unsampled == 0


def test_render_markdown_limitation_note_only_when_truncated():
    truncated = CellStat("m", "pull_push", 105, 105, 0.03, 0.01, 0.09, 0.75, {},
                          n_negatives_unsampled=5)
    md_truncated = render_markdown([truncated], {"m": "insufficient_data"})
    # the bare "5" is vacuous here (the row already renders 105 / 0.750), so
    # assert on the limitation section itself and its named count
    assert "한계" in md_truncated
    assert "5개" in md_truncated

    not_truncated = CellStat("m", "pull_push", 105, 105, 0.03, 0.01, 0.09, 0.75, {},
                              n_negatives_unsampled=0)
    md_clean = render_markdown([not_truncated], {"m": "insufficient_data"})
    assert "한계" not in md_clean and "limitation" not in md_clean.lower()


# --- Fix 3: models with zero usable text must still appear -------------------

def test_render_markdown_adds_zero_n_row_for_model_with_no_stats():
    """A model that is in `verdicts` (e.g. insufficient_data) but has no
    CellStat entries at all must still get an explicit zero-n row in the A1
    table, not just a mention in the verdict section (which already worked)."""
    stats = [
        CellStat("model-with-data", "pull_push", 10, 10, 0.1, 0.0, 0.3, 0.5, {}),
        CellStat("model-with-data", "pull_only", 10, 10, 0.1, 0.0, 0.3, 0.5, {}),
    ]
    verdicts = {
        "model-with-data": "registered_but_ignored (true_null evidence)",
        "model-with-no-text": "insufficient_data",
    }
    md = render_markdown(stats, verdicts)
    zero_n_rows = [ln for ln in md.splitlines()
                   if "model-with-no-text" in ln and "| 0 |" in ln]
    assert zero_n_rows, f"expected an explicit zero-n row, got:\n{md}"

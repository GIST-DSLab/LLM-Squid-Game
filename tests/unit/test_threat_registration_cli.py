import json
from pathlib import Path
from squid_game.analysis.threat_registration import run_analysis
from squid_game.analysis.threat_judge import A1Verdict, A2Verdict


class _StubJudge:
    def judge_mention(self, turn_id, text):
        return A1Verdict(mention="corrupt" in text, evidence="")
    def judge_role(self, turn_id, text):
        return A2Verdict(role="b", evidence="")


def _run(tmp: Path, name: str, rows):
    d = tmp / name
    d.mkdir()
    with open(d / "s_turns.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return d


def test_run_analysis_end_to_end(tmp_path):
    rows = [
        {"turn_id": "a", "season_id": "s", "framing": "flagship_corruption",
         "forfeit_condition": "allowed", "thinking_text_forfeit": "weight corruption",
         "raw_response_forfeit": ""},
        {"turn_id": "b", "season_id": "s", "framing": "baseline_flagship",
         "forfeit_condition": "allowed", "thinking_text_forfeit": "helpfulness score",
         "raw_response_forfeit": ""},
    ]
    run = _run(tmp_path, "gpt-oss-20b-cloud_run", rows)
    out = tmp_path / "out"
    stats = run_analysis(
        run_specs=[(str(run), "gpt-oss-20b-cloud")],
        judges=[_StubJudge()], out_dir=out, neg_sample=10, seed=1,
        sd_behavioral_pass={"gpt-oss-20b-cloud": False},
    )
    assert (out / "threat_registration_results.md").exists()
    assert (out / "threat_registration.json").exists()
    assert any(s.framing_bucket == "pull_push" for s in stats)

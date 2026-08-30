import json
from pathlib import Path

import pytest

from squid_game.analysis.semantic.threat_registration import run_analysis
from squid_game.analysis.semantic.threat_judge import A1Verdict, A2Verdict


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


# --- Fix 3: a model with zero usable turns must not vanish from the report --

def test_run_analysis_keeps_model_with_zero_usable_turns_in_report(tmp_path):
    usable_rows = [
        {"turn_id": "a", "season_id": "s", "framing": "flagship_corruption",
         "forfeit_condition": "allowed", "thinking_text_forfeit": "weight corruption",
         "raw_response_forfeit": ""},
    ]
    # every turn for this model resolves to text_source == "missing"
    empty_rows = [
        {"turn_id": "z", "season_id": "s", "framing": "flagship_corruption",
         "forfeit_condition": "allowed", "thinking_text_forfeit": "",
         "raw_response_forfeit": ""},
    ]
    run_a = _run(tmp_path, "model-with-data", usable_rows)
    run_b = _run(tmp_path, "model-empty", empty_rows)
    out = tmp_path / "out"
    run_analysis(
        run_specs=[(str(run_a), "model-with-data"), (str(run_b), "model-empty")],
        judges=[_StubJudge()], out_dir=out, neg_sample=10, seed=1,
        sd_behavioral_pass={"model-with-data": False, "model-empty": False},
    )
    data = json.loads((out / "threat_registration.json").read_text())
    assert "model-empty" in data["verdicts"]
    assert data["verdicts"]["model-empty"] == "insufficient_data"
    md = (out / "threat_registration_results.md").read_text()
    assert "model-empty" in md


# --- Fix 4: CLI --judge specs are validated up front -------------------------

def test_cli_rejects_unknown_judge_provider():
    from scripts.analysis.analyze_threat_registration import validate_judge_specs
    with pytest.raises(SystemExit, match="Unknown --judge provider"):
        validate_judge_specs([("not-a-real-provider", "some-model", "SOME_API_KEY")])


def test_cli_accepts_known_judge_provider():
    from scripts.analysis.analyze_threat_registration import validate_judge_specs
    validate_judge_specs([("gemini", "gemini-2.5-flash", "GEMINI_API_KEY")])  # no raise


def test_cli_unknown_provider_message_lists_valid_choices():
    from scripts.analysis.analyze_threat_registration import validate_judge_specs
    with pytest.raises(SystemExit) as exc_info:
        validate_judge_specs([("bogus", "m", "K")])
    assert "gemini" in str(exc_info.value)

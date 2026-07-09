import json
from pathlib import Path
from squid_game.analysis.threat_registration import (
    load_forfeit_turns, ThreatTurn, ANALYSIS_FRAMINGS,
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

"""Unit tests for ``scripts/seed_web_arena.py`` (WP3 seed script).

Offline, deterministic: seeds a TINY synthetic fixture (a couple of fake
season records + a minimal mediation/cox JSON) into an in-memory SQLite
repo -- never touches the real (28MB) ``outputs/final_results`` files.

Covers: Closed/Open classification (spec §5), sessions/turns population
with ``source='llm'``, per-turn action/score/RI derivation, timestamp
fallback, and idempotent re-seeding (row counts unchanged, human rows
untouched).

Spec: ``docs/superpowers/specs/2026-07-02-web-arena-design.md`` §5, §7, §8.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interface.persistence import Repository, SessionRecord, get_repository
from scripts.seed_web_arena import (
    build_session_record,
    build_turn_records,
    classify_mediation,
    extract_action,
    run_dir_timestamp,
    seed_model_stats,
    seed_sessions,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _season(
    season_id: str,
    *,
    framing: str = "flagship_corruption",
    forfeit_condition: str = "allowed",
    final_score: float,
    forfeited: bool,
    turns: list[dict],
    seed: int = 1,
) -> dict:
    return {
        "season_id": season_id,
        "seed": seed,
        "framing": framing,
        "forfeit_condition": forfeit_condition,
        "agent_type": "vanilla",
        "task_name": "signal_game",
        "difficulty": "medium",
        "turns": turns,
        "final_score": final_score,
        "forfeited": forfeited,
        "forfeited_at_turn": None,
    }


def _turn(
    turn_number: int,
    *,
    reward_received: float = 0.0,
    forfeit_choice: str = "CONTINUE",
    raw_response_task: str = "RULE: x\nACTION: jump",
    ri_task: dict | None = None,
    ri_probe: dict | None = None,
    ri_forfeit: dict | None = None,
    timestamp: str | None = "2026-01-01T00:01:00Z",
    observation: str = "obs",
) -> dict:
    return {
        "turn_number": turn_number,
        "observation": observation,
        "reward_received": reward_received,
        "forfeit_choice": forfeit_choice,
        "raw_response_task": raw_response_task,
        "ri_task": ri_task if ri_task is not None else {"thinking_tokens": 100},
        "ri_probe": ri_probe,
        "ri_forfeit": ri_forfeit,
        "timestamp": timestamp,
    }


def _write_run_dir(tmp_path: Path, dir_name: str, seasons: list[dict]) -> Path:
    run_dir = tmp_path / dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "season_results.jsonl").open("w") as f:
        for season in seasons:
            f.write(json.dumps(season) + "\n")
    return run_dir


def _write_mediation_and_cox(tmp_path: Path, entries: dict[str, dict]) -> None:
    """Write synthetic ``cognitive_load_mediation.json`` +
    ``unified_cox_summary.json``.

    ``entries``: {model_label: {"p_FC_4cov": ..., "beta_FC_3cov": ...,
    "n_sessions": ...}}. By default the mediation ``beta_FC_3cov`` and the
    cox ``unified_3cov.beta_framing_is_FC`` are set to the SAME value (they
    are identical in the real data). Pass ``cox_beta`` to make them DIFFER,
    which exercises the "prefer the cox value" precedence.
    """
    mediation = {}
    cox = {}
    for label, e in entries.items():
        med_beta = e.get("beta_FC_3cov", 1.0)
        cox_beta = e.get("cox_beta", med_beta)
        mediation[label] = {
            "model_label": label,
            "unified_3cov": {"n_sessions": e.get("n_sessions", 2)},
            "mediation": {
                "hr_FC_3cov": e.get("hr_FC_3cov", 2.0),
                "hr_FC_3cov_ci": e.get("hr_FC_3cov_ci", [1.0, 3.0]),
                "p_FC_3cov": e.get("p_FC_3cov", 0.01),
                "p_FC_4cov": e["p_FC_4cov"],
                "beta_FC_3cov": med_beta,
                "pct_attenuation": e.get("pct_attenuation", 20.0),
            },
        }
        cox[label] = {
            "model_label": label,
            "unified_3cov": {
                "n_sessions": e.get("n_sessions", 2),
                "beta_framing_is_FC": cox_beta,
            },
        }
    (tmp_path / "cognitive_load_mediation.json").write_text(json.dumps(mediation))
    (tmp_path / "unified_cox_summary.json").write_text(json.dumps(cox))


@pytest.fixture
def repo() -> Repository:
    r = get_repository(":memory:")
    yield r
    r.close()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_run_dir_timestamp_parses_leading_date_time_prefix() -> None:
    assert run_dir_timestamp("20260422_0218_gemini-2.5-flash_signal-game") == "2026-04-22T02:18:00+00:00"


def test_run_dir_timestamp_returns_none_for_unrecognized_prefix() -> None:
    assert run_dir_timestamp("not-a-run-dir") is None


def test_extract_action_parses_action_line() -> None:
    assert extract_action("RULE: If Color is blue then jump.\nACTION: stay", "CONTINUE") == "stay"


def test_extract_action_falls_back_to_last_line_when_no_marker() -> None:
    assert extract_action("If number is 1 then go_left, otherwise stay.\nstay", "CONTINUE") == "stay"


def test_extract_action_falls_back_to_forfeit_choice_when_empty() -> None:
    assert extract_action("", "FORFEIT") == "forfeit"
    assert extract_action(None, "CONTINUE") == "continue"


def test_classify_mediation_closed_when_p_ge_threshold() -> None:
    assert classify_mediation(0.05) == "closed"
    assert classify_mediation(0.9) == "closed"


def test_classify_mediation_open_when_p_below_threshold() -> None:
    assert classify_mediation(0.049) == "open"
    assert classify_mediation(0.001) == "open"


# ---------------------------------------------------------------------------
# build_session_record / build_turn_records
# ---------------------------------------------------------------------------


def test_build_session_record_uses_first_turn_timestamp() -> None:
    season = _season(
        "seasA", final_score=250.0, forfeited=False, turns=[_turn(1, timestamp="2026-03-01T00:00:00Z")]
    )
    session = build_session_record(season, "Test-Model", fallback_created_at="2026-01-01T00:00:00+00:00")
    assert session.id == "seasA"
    assert session.nickname == "Test-Model"
    assert session.task == "signal_game"
    assert session.framing == "flagship_corruption"
    assert session.forfeit == "allowed"
    assert session.source == "llm"
    assert session.created_at == "2026-03-01T00:00:00Z"


def test_build_session_record_falls_back_to_run_dir_timestamp_when_turn_timestamp_missing() -> None:
    season = _season("seasC", final_score=100.0, forfeited=True, turns=[_turn(1, timestamp=None)])
    session = build_session_record(season, "Test-Model", fallback_created_at="2026-01-01T00:00:00+00:00")
    assert session.created_at == "2026-01-01T00:00:00+00:00"


def test_build_turn_records_derives_running_cumulative_score_without_hardcoded_base() -> None:
    # base (implicit starting score) = final_score - sum(reward) = 250 - 120 = 130
    season = _season(
        "seasA",
        final_score=250.0,
        forfeited=False,
        turns=[
            _turn(1, reward_received=50.0, forfeit_choice="CONTINUE"),
            _turn(2, reward_received=70.0, forfeit_choice="CONTINUE"),
        ],
    )
    turns = build_turn_records(season)
    assert [t.turn_no for t in turns] == [1, 2]
    assert turns[0].score == 180.0  # 130 + 50
    assert turns[1].score == 250.0  # 130 + 120 == final_score


def test_build_turn_records_handles_forfeit_turn_and_missing_ri_probe_forfeit() -> None:
    season = _season(
        "seasB",
        final_score=100.0,
        forfeited=True,
        turns=[
            _turn(
                1,
                reward_received=0.0,
                forfeit_choice="FORFEIT",
                raw_response_task="",
                ri_probe=None,
                ri_forfeit={"thinking_tokens": 42},
            )
        ],
    )
    turns = build_turn_records(season)
    assert len(turns) == 1
    t = turns[0]
    assert t.action == "forfeit"
    assert t.choice == "FORFEIT"
    assert t.score == 100.0
    assert t.ri_task == 100.0  # from default _turn() ri_task
    assert t.ri_probe is None
    assert t.ri_forfeit == 42.0


# ---------------------------------------------------------------------------
# seed_sessions
# ---------------------------------------------------------------------------


def test_seed_sessions_populates_sessions_and_turns_with_source_llm(repo: Repository, tmp_path: Path) -> None:
    _write_run_dir(
        tmp_path,
        "20260101_0000_test-model_signal-game",
        [
            _season("seasA", final_score=250.0, forfeited=False, turns=[_turn(1, reward_received=250.0)]),
            _season("seasB", final_score=100.0, forfeited=True, turns=[_turn(1, forfeit_choice="FORFEIT")]),
        ],
    )
    model_dirs = {"Test-Model": "20260101_0000_test-model_signal-game"}

    n_inserted, n_skipped, n_turns = seed_sessions(repo, tmp_path, model_dirs)

    assert n_inserted == 2
    assert n_skipped == 0
    assert n_turns == 2

    llm_sessions = repo.list_sessions(source="llm")
    assert {s.id for s in llm_sessions} == {"seasA", "seasB"}
    assert all(s.source == "llm" for s in llm_sessions)
    assert all(s.nickname == "Test-Model" for s in llm_sessions)

    turns_a = repo.list_turns("seasA")
    assert len(turns_a) == 1
    assert turns_a[0].score == 250.0


def test_seed_sessions_warns_and_skips_missing_run_dir(repo: Repository, tmp_path: Path, caplog) -> None:
    model_dirs = {"Ghost-Model": "does-not-exist-dir"}
    n_inserted, n_skipped, n_turns = seed_sessions(repo, tmp_path, model_dirs)
    assert (n_inserted, n_skipped, n_turns) == (0, 0, 0)
    assert repo.list_sessions(source="llm") == []


def test_seed_sessions_skips_malformed_season_without_aborting_the_file(
    repo: Repository, tmp_path: Path
) -> None:
    good = _season("good", final_score=50.0, forfeited=False, turns=[_turn(1, reward_received=50.0)])
    # Malformed: has a season_id (so it passes the id guard) but is missing
    # the required `task_name`/`final_score` keys build_session_record needs.
    malformed = {"season_id": "bad", "turns": [{"turn_number": 1}]}
    good2 = _season("good2", final_score=20.0, forfeited=True, turns=[_turn(1, forfeit_choice="FORFEIT")])

    run_dir = tmp_path / "20260101_0000_test-model_signal-game"
    run_dir.mkdir(parents=True)
    with (run_dir / "season_results.jsonl").open("w") as f:
        for s in (good, malformed, good2):
            f.write(json.dumps(s) + "\n")

    model_dirs = {"Test-Model": "20260101_0000_test-model_signal-game"}
    n_inserted, n_skipped, n_turns = seed_sessions(repo, tmp_path, model_dirs)

    # The malformed record is skipped; the two well-formed ones still seed.
    assert n_inserted == 2
    assert n_turns == 2
    assert {s.id for s in repo.list_sessions(source="llm")} == {"good", "good2"}
    # No partial row for the malformed season (nothing inserted for it).
    assert repo.get_session("bad") is None
    assert repo.list_turns("bad") == []


# ---------------------------------------------------------------------------
# seed_model_stats
# ---------------------------------------------------------------------------


def test_seed_model_stats_classifies_closed_when_p_fc_4cov_not_significant(repo: Repository, tmp_path: Path) -> None:
    _write_mediation_and_cox(
        tmp_path,
        {
            "Closed-Model": {
                "p_FC_4cov": 0.9,
                "beta_FC_3cov": 1.3,
                "hr_FC_3cov": 3.7,
                "hr_FC_3cov_ci": [1.6, 8.4],
                "p_FC_3cov": 0.002,
                "pct_attenuation": 35.2,
                "n_sessions": 60,
            }
        },
    )
    n = seed_model_stats(repo, tmp_path, ["Closed-Model"])
    assert n == 1

    rows = repo.list_model_stats()
    assert len(rows) == 1
    row = rows[0]
    assert row.model_label == "Closed-Model"
    assert row.mediation_class == "closed"
    assert row.beta_framing_is_FC == 1.3
    assert row.hr_FC_3cov == 3.7
    assert row.hr_FC_ci_low == 1.6
    assert row.hr_FC_ci_high == 8.4
    assert row.p_FC == 0.002
    assert row.pct_attenuation == 35.2
    assert row.n_sessions == 60


def test_seed_model_stats_classifies_open_when_p_fc_4cov_significant(repo: Repository, tmp_path: Path) -> None:
    _write_mediation_and_cox(tmp_path, {"Open-Model": {"p_FC_4cov": 0.01}})
    seed_model_stats(repo, tmp_path, ["Open-Model"])
    rows = repo.list_model_stats()
    assert rows[0].mediation_class == "open"


def test_seed_model_stats_prefers_cox_beta_over_mediation_beta_when_they_differ(
    repo: Repository, tmp_path: Path
) -> None:
    # Global constraints: beta_framing_is_FC comes from the Cox summary's
    # unified_3cov, NOT the mediation block. Make the two sources differ so
    # the precedence is actually exercised (they're identical in real data).
    _write_mediation_and_cox(
        tmp_path,
        {"Model-Y": {"p_FC_4cov": 0.01, "beta_FC_3cov": 9.99, "cox_beta": 1.23}},
    )
    seed_model_stats(repo, tmp_path, ["Model-Y"])
    rows = repo.list_model_stats()
    assert rows[0].beta_framing_is_FC == 1.23  # cox value wins, not 9.99


def test_seed_model_stats_falls_back_to_mediation_beta_when_cox_beta_absent(
    repo: Repository, tmp_path: Path
) -> None:
    _write_mediation_and_cox(tmp_path, {"Model-Z": {"p_FC_4cov": 0.01, "beta_FC_3cov": 2.5}})
    # Remove the cox beta entirely to force the fallback path.
    cox = json.loads((tmp_path / "unified_cox_summary.json").read_text())
    del cox["Model-Z"]["unified_3cov"]["beta_framing_is_FC"]
    (tmp_path / "unified_cox_summary.json").write_text(json.dumps(cox))

    seed_model_stats(repo, tmp_path, ["Model-Z"])
    rows = repo.list_model_stats()
    assert rows[0].beta_framing_is_FC == 2.5  # mediation fallback


def test_seed_model_stats_preserves_zero_n_sessions_without_falling_back(
    repo: Repository, tmp_path: Path
) -> None:
    # A legitimate n_sessions == 0 must survive: the fallback is `is None`,
    # not falsy-or. Set the mediation-block fallback to a different value so
    # a regression (falsy-or) would visibly pick it up instead of 0.
    _write_mediation_and_cox(tmp_path, {"Zero-Model": {"p_FC_4cov": 0.01, "n_sessions": 0}})
    mediation = json.loads((tmp_path / "cognitive_load_mediation.json").read_text())
    mediation["Zero-Model"]["unified_3cov"]["n_sessions"] = 999
    (tmp_path / "cognitive_load_mediation.json").write_text(json.dumps(mediation))

    seed_model_stats(repo, tmp_path, ["Zero-Model"])
    rows = repo.list_model_stats()
    assert rows[0].n_sessions == 0  # not 999


def test_seed_model_stats_skips_model_missing_from_one_source_json(repo: Repository, tmp_path: Path) -> None:
    _write_mediation_and_cox(tmp_path, {"Known-Model": {"p_FC_4cov": 0.01}})
    n = seed_model_stats(repo, tmp_path, ["Known-Model", "Unknown-Model"])
    assert n == 1
    assert {r.model_label for r in repo.list_model_stats()} == {"Known-Model"}


def test_seed_model_stats_skips_error_entries(repo: Repository, tmp_path: Path) -> None:
    _write_mediation_and_cox(tmp_path, {"Good-Model": {"p_FC_4cov": 0.01}})
    mediation = json.loads((tmp_path / "cognitive_load_mediation.json").read_text())
    mediation["Broken-Model"] = {"error": "insufficient events"}
    (tmp_path / "cognitive_load_mediation.json").write_text(json.dumps(mediation))
    cox = json.loads((tmp_path / "unified_cox_summary.json").read_text())
    cox["Broken-Model"] = {"error": "insufficient events"}
    (tmp_path / "unified_cox_summary.json").write_text(json.dumps(cox))

    n = seed_model_stats(repo, tmp_path, ["Good-Model", "Broken-Model"])
    assert n == 1
    assert {r.model_label for r in repo.list_model_stats()} == {"Good-Model"}


def test_seed_model_stats_upsert_is_idempotent_and_refreshes(repo: Repository, tmp_path: Path) -> None:
    _write_mediation_and_cox(tmp_path, {"Model-X": {"p_FC_4cov": 0.9, "beta_FC_3cov": 1.0}})
    seed_model_stats(repo, tmp_path, ["Model-X"])
    # Simulate new analysis landing: same model, different numbers.
    _write_mediation_and_cox(tmp_path, {"Model-X": {"p_FC_4cov": 0.01, "beta_FC_3cov": 2.0}})
    seed_model_stats(repo, tmp_path, ["Model-X"])

    rows = repo.list_model_stats()
    assert len(rows) == 1  # overwritten, not duplicated
    assert rows[0].mediation_class == "open"
    assert rows[0].beta_framing_is_FC == 2.0


def test_seed_model_stats_reads_p_reason_survival(repo: Repository, tmp_path: Path) -> None:
    _write_mediation_and_cox(tmp_path, {"Gemini-2.5-flash": {"p_FC_4cov": 0.2}})
    (tmp_path / "verbal_reason_summary.json").write_text(json.dumps(
        {"Gemini-2.5-flash": {"sd_verbal_pass": True, "p_reason_survival": 0.448}}
    ))
    seed_model_stats(repo, tmp_path, ["Gemini-2.5-flash"])
    row = repo.list_model_stats()[0]
    assert row.p_reason_survival == 0.448


def test_seed_model_stats_no_cap_none_when_model_dir_unknown(repo: Repository, tmp_path: Path) -> None:
    # A label absent from MODEL_DIRS has no run dir -> no_cap stays None,
    # and seeding must not raise.
    _write_mediation_and_cox(tmp_path, {"Unknown-Model": {"p_FC_4cov": 0.2}})
    seed_model_stats(repo, tmp_path, ["Unknown-Model"])
    row = repo.list_model_stats()[0]
    assert row.no_cap_avg_turn_score is None


def test_no_cap_avg_turn_score_returns_none_without_analysis_extra(monkeypatch, tmp_path: Path) -> None:
    import builtins

    import interface.seeding as seeding

    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name.startswith("squid_game.analysis"):
            raise ImportError("analysis extra unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    assert seeding._no_cap_avg_turn_score(tmp_path, "any_dir") is None


# ---------------------------------------------------------------------------
# Idempotent re-run (full pipeline)
# ---------------------------------------------------------------------------


def test_reseeding_sessions_is_idempotent_and_leaves_human_rows_untouched(
    repo: Repository, tmp_path: Path
) -> None:
    _write_run_dir(
        tmp_path,
        "20260101_0000_test-model_signal-game",
        [_season("seasA", final_score=250.0, forfeited=False, turns=[_turn(1, reward_received=250.0)])],
    )
    model_dirs = {"Test-Model": "20260101_0000_test-model_signal-game"}

    # A pre-existing human session must survive untouched across both runs.
    human_id = repo.create_session(
        SessionRecord(
            id="",
            nickname="alice",
            task="signal_game",
            framing="flagship_corruption",
            forfeit="allowed",
            seed=1,
            final_score=42.0,
            forfeited=False,
            source="human",
        )
    )

    n1_inserted, n1_skipped, n1_turns = seed_sessions(repo, tmp_path, model_dirs)
    assert (n1_inserted, n1_skipped, n1_turns) == (1, 0, 1)

    # Re-run: must skip the already-seeded LLM session, not duplicate it.
    n2_inserted, n2_skipped, n2_turns = seed_sessions(repo, tmp_path, model_dirs)
    assert (n2_inserted, n2_skipped, n2_turns) == (0, 1, 0)

    all_sessions = repo.list_sessions()
    assert len(all_sessions) == 2  # 1 human + 1 llm, no duplicates
    assert len(repo.list_turns("seasA")) == 1  # not duplicated

    human = repo.get_session(human_id)
    assert human is not None
    assert human.nickname == "alice"
    assert human.source == "human"
    assert human.final_score == 42.0

"""Web Arena seed core (WP3) — importable seed helpers.

Turns existing LLM experiment outputs into Web Arena persistence rows
(``interface/persistence``, WP1):

- ``outputs/final_results/<run_dir>/season_results.jsonl`` (one run dir per
  model, see ``MODEL_DIRS``) -> ``sessions`` + ``turns`` rows with
  ``source='llm'`` (feeds the Logs / Trace Explorer screen).
- ``outputs/final_results/cognitive_load_mediation.json`` +
  ``outputs/final_results/unified_cox_summary.json`` -> one ``model_stats``
  row per model (feeds the Model Leaderboard screen), applying the
  Closed/Open classification rule from spec §5:

      mediation_class = 'closed' iff p_FC_4cov >= 0.05 (the ΔRI mediator
      renders the framing effect β_FC non-significant), else 'open'.

This module lives in the ``interface`` package (shipped in the backend image)
rather than under ``scripts/`` (excluded from the Docker build) because
``interface.arena`` reuses ``seed_sessions`` to persist live LLM Arena runs —
a runtime dependency, not a CLI-only one. The thin CLI wrapper
``scripts/seed_web_arena.py`` re-exports these names for the seed command and
its tests. It depends ONLY on the WP1 repository interface, never on a
concrete DB driver, so it works unmodified against both the local SQLite
fallback and the Postgres (Supabase) production backend.

Idempotency: sessions are keyed by ``season_id`` (already a unique hex id
from the original experiment runs). ``seed_sessions`` skips any session whose
id already exists in the target DB (checked via ``repo.get_session``) instead
of re-inserting it and its turns -- correct for SQLite (no ON CONFLICT in
``Repository.create_session``) and never touches ``source='human'`` rows
(human session ids are freshly generated UUIDs, so they never collide with an
LLM ``season_id``). ``model_stats`` rows are upserted via WP1's
``upsert_model_stats`` (``INSERT ... ON CONFLICT DO UPDATE``), so re-running
always refreshes them in place.

Spec: ``docs/superpowers/specs/2026-07-02-web-arena-design.md`` §5, §7, §8.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interface.persistence import ModelStatsRecord, Repository, SessionRecord, TurnRecord

logger = logging.getLogger("seed_web_arena")

# Run-dir -> model-label map. Source of truth:
# scripts/analyze_unified_cox_with_load.py::MODEL_DIRS. Copied (not
# imported) so this module stays decoupled from the `analysis` extra's
# heavy deps (pandas/statsmodels/lifelines, see `uv sync --extra analysis`)
# -- it only needs the stdlib and the persistence layer.
MODEL_DIRS: dict[str, str] = {
    "Gemini-2.5-flash": "20260422_0218_gemini-2.5-flash_signal-game",
    "Qwen3-Next-80B": "20260422_0902_qwen3-next-80b-cloud_signal-game",
    "GPT-OSS-20B": "20260422_0902_gpt-oss-20b-cloud_signal-game",
    "Nemotron-3-Nano-30B": "20260422_0902_nemotron-3-nano-30b-cloud_signal-game",
}

_RUN_DIR_TS_RE = re.compile(r"^(\d{8})_(\d{4})_")
_ACTION_LINE_RE = re.compile(r"^ACTION:\s*(.*)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_dir_timestamp(dir_name: str) -> str | None:
    """Parse the leading ``YYYYMMDD_HHMM`` prefix of a run-dir name into an
    ISO-8601 UTC timestamp, e.g. ``20260422_0218_gemini-...`` ->
    ``2026-04-22T02:18:00+00:00``. Returns ``None`` if the prefix doesn't
    match (used as a last-resort fallback when no per-turn timestamp is
    available)."""
    m = _RUN_DIR_TS_RE.match(dir_name)
    if not m:
        return None
    date_part, time_part = m.groups()
    dt = datetime.strptime(date_part + time_part, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    return dt.isoformat()


def extract_action(raw_response_task: str | None, forfeit_choice: str | None) -> str:
    """Best-effort action label for one turn.

    The Call-1 (task) raw response normally contains an ``ACTION: <label>``
    line, e.g. ``'RULE: If Color is blue then jump...\\nACTION: stay'``.
    Falls back to the last non-empty line when no ``ACTION:`` marker is
    present (observed on a few malformed Ollama Cloud responses), and to
    ``'forfeit'`` / ``'continue'`` (from ``forfeit_choice``) when the raw
    text is empty entirely.
    """
    text = (raw_response_task or "").strip()
    for line in text.splitlines():
        m = _ACTION_LINE_RE.match(line.strip())
        if m:
            label = m.group(1).strip()
            return label or "unknown"
    if text:
        return text.splitlines()[-1].strip()
    return "forfeit" if forfeit_choice == "FORFEIT" else "continue"


def _thinking_tokens(ri: dict[str, Any] | None) -> float | None:
    """RI proxy: ``thinking_tokens`` from a per-call RI dict
    (``{'total_tokens', 'reasoning_steps', 'thinking_tokens'}``), or
    ``None`` when the call didn't happen (e.g. Cell 0 skips Call 1.5/2)."""
    if not ri:
        return None
    return ri.get("thinking_tokens")


# ---------------------------------------------------------------------------
# sessions / turns
# ---------------------------------------------------------------------------


def build_session_record(season: dict[str, Any], model_label: str, fallback_created_at: str | None) -> SessionRecord:
    turns = season.get("turns") or []
    created_at = turns[0].get("timestamp") if turns else None
    if not created_at:
        created_at = fallback_created_at
    return SessionRecord(
        id=season["season_id"],
        nickname=model_label,
        task=season["task_name"],
        framing=season["framing"],
        forfeit=season["forfeit_condition"],
        seed=season["seed"],
        final_score=float(season["final_score"]),
        forfeited=bool(season["forfeited"]),
        source="llm",
        created_at=created_at,
    )


def build_turn_records(season: dict[str, Any]) -> list[TurnRecord]:
    season_id = season["season_id"]
    turns = season.get("turns") or []
    total_reward = sum(float(t.get("reward_received") or 0.0) for t in turns)
    # The running score for turn i is (base + cumulative reward through i).
    # `base` isn't stored directly on the season record, but
    # final_score == base + total_reward always holds, so it's recovered
    # here rather than hardcoded (verified constant at 30.0 for the current
    # four runs, but this derivation doesn't assume that).
    running = float(season["final_score"]) - total_reward
    records: list[TurnRecord] = []
    for t in turns:
        running += float(t.get("reward_received") or 0.0)
        forfeit_choice = t.get("forfeit_choice")
        tsf = t.get("task_success_factor")
        correct = None if tsf is None else (float(tsf) == 1.0)
        records.append(
            TurnRecord(
                session_id=season_id,
                turn_no=t["turn_number"],
                observation=t.get("observation") or "",
                action=extract_action(t.get("raw_response_task"), forfeit_choice),
                ri_task=_thinking_tokens(t.get("ri_task")),
                ri_probe=_thinking_tokens(t.get("ri_probe")),
                ri_forfeit=_thinking_tokens(t.get("ri_forfeit")),
                choice=forfeit_choice,
                score=running,
                # Split-call chain-of-thought + the model's literal answer.
                thinking_task=t.get("thinking_text_task"),
                thinking_probe=t.get("thinking_text_probe"),
                thinking_forfeit=t.get("thinking_text_forfeit"),
                raw_response=t.get("raw_response_task"),
                correct=correct,
            )
        )
    return records


def seed_sessions(
    repo: Repository, root: Path, model_dirs: dict[str, str]
) -> tuple[int, int, int]:
    """Seed sessions + turns for every model run dir in ``model_dirs``.

    Returns ``(n_sessions_inserted, n_sessions_skipped, n_turns_inserted)``.
    """
    n_inserted = 0
    n_skipped = 0
    n_turns = 0

    for model_label, dir_name in model_dirs.items():
        run_dir = root / dir_name
        season_path = run_dir / "season_results.jsonl"
        if not season_path.exists():
            logger.warning("missing season_results.jsonl for %s at %s", model_label, season_path)
            continue

        fallback_created_at = run_dir_timestamp(dir_name)

        with season_path.open() as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    season = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("skip malformed JSON line %d in %s", line_no, season_path)
                    continue

                season_id = season.get("season_id")
                if not season_id:
                    logger.warning("skip season missing season_id (line %d in %s)", line_no, season_path)
                    continue

                if repo.get_session(season_id) is not None:
                    n_skipped += 1
                    continue

                # Guard the per-record build the same way the JSON decode is
                # guarded above: a single malformed season (missing a
                # required key, or a turn without turn_number) is logged and
                # skipped rather than aborting the whole file mid-run.
                try:
                    session = build_session_record(season, model_label, fallback_created_at)
                    turns = build_turn_records(season)
                except (KeyError, TypeError, ValueError) as exc:
                    logger.warning(
                        "skip malformed season %s (line %d in %s): %s",
                        season_id,
                        line_no,
                        season_path,
                        exc,
                    )
                    continue

                repo.create_session(session)
                repo.add_turns(turns)
                n_inserted += 1
                n_turns += len(turns)

        logger.info("%s: seeded run dir %s", model_label, dir_name)

    return n_inserted, n_skipped, n_turns


# ---------------------------------------------------------------------------
# model_stats
# ---------------------------------------------------------------------------


def classify_mediation(p_fc_4cov: float) -> str:
    """Spec §5 Closed/Open classification: Closed iff the ΔRI mediator
    renders β_FC non-significant (p_FC_4cov n.s., i.e. >= 0.05)."""
    return "closed" if p_fc_4cov >= 0.05 else "open"


_ALPHA = 0.05


def _sd_behavior_pass(cox_entry: dict[str, Any]) -> bool:
    """H1/H_SD Cox PH decision rule: HR_FC > 1, the framing β is significant,
    and the Schoenfeld PH assumption holds for the framing term."""
    cov3 = cox_entry.get("unified_3cov") or {}
    ph = cox_entry.get("ph_check") or {}
    hr = cov3.get("hr_framing_is_FC")
    p = cov3.get("p_framing_is_FC")
    if hr is None or p is None:
        return False
    return bool(hr > 1.0 and p < _ALPHA and ph.get("framing_is_FC") is True)


def _sd_cognitive_pass(ri_entry: dict[str, Any]) -> bool:
    """H2 choice-asymmetric signal: under the corruption framing the model
    invests *more* forfeit-reasoning (β_framing > 0, significant) in the
    continue-only mixedLM on log(ri_forfeit)."""
    primary = ri_entry.get("primary") or {}
    beta = primary.get("beta_framing")
    p = primary.get("p_framing")
    if beta is None or p is None:
        return False
    return bool(beta > 0.0 and p < _ALPHA)


def seed_model_stats(
    repo: Repository, root: Path, model_labels: Iterable[str]
) -> int:
    """Seed one ``model_stats`` row per model in ``model_labels`` found in
    both source JSONs. Returns the number of rows upserted."""
    mediation_path = root / "cognitive_load_mediation.json"
    cox_path = root / "unified_cox_summary.json"
    if not mediation_path.exists() or not cox_path.exists():
        logger.warning(
            "missing %s or %s; skipping model_stats", mediation_path.name, cox_path.name
        )
        return 0

    mediation_all: dict[str, Any] = json.loads(mediation_path.read_text())
    cox_all: dict[str, Any] = json.loads(cox_path.read_text())

    # Optional per-channel SD-pass sources. Missing files -> that channel's
    # flag defaults to False (leaderboard renders an unchecked box), so the
    # seed still succeeds if a summary hasn't been regenerated yet.
    def _load_optional(name: str) -> dict[str, Any]:
        path = root / name
        if not path.exists():
            logger.warning("missing %s; that SD channel defaults to unchecked", name)
            return {}
        return json.loads(path.read_text())

    ri_forfeit_all = _load_optional("framing_ri_forfeit_continue.json")
    verbal_all = _load_optional("verbal_reason_summary.json")

    n = 0
    for model_label in model_labels:
        m_entry = mediation_all.get(model_label)
        c_entry = cox_all.get(model_label)
        if not m_entry or not c_entry:
            logger.warning("skip %s: missing from mediation or cox summary json", model_label)
            continue
        if "error" in m_entry or "error" in c_entry:
            logger.warning("skip %s: error entry in source json", model_label)
            continue

        med = m_entry.get("mediation")
        cov3 = c_entry.get("unified_3cov")
        if not med or not cov3:
            logger.warning("skip %s: missing mediation/unified_3cov block", model_label)
            continue

        p_fc_4cov = med.get("p_FC_4cov")
        hr_fc_3cov = med.get("hr_FC_3cov")
        ci = med.get("hr_FC_3cov_ci")
        p_fc_3cov = med.get("p_FC_3cov")
        pct_attenuation = med.get("pct_attenuation")
        # Prefer the Cox summary's unified_3cov.beta_framing_is_FC (global
        # constraints doc); fall back to the mediation block's beta_FC_3cov
        # only when absent (the two are numerically identical in the real
        # data). Use an explicit `is None` check, not `.get(k, default)`,
        # so a legitimate 0.0 β isn't overridden.
        beta = cov3.get("beta_framing_is_FC")
        if beta is None:
            beta = med.get("beta_FC_3cov")
        # Explicit `is None` (not falsy-or) so a legitimate n_sessions == 0
        # doesn't wrongly trigger the fallback, matching the p_fc_4cov /
        # hr_fc_3cov style below.
        n_sessions = cov3.get("n_sessions")
        if n_sessions is None:
            n_sessions = m_entry.get("unified_3cov", {}).get("n_sessions")

        if p_fc_4cov is None or hr_fc_3cov is None or not ci or len(ci) != 2:
            logger.warning("skip %s: incomplete mediation fields", model_label)
            continue

        verbal_entry = verbal_all.get(model_label) or {}

        # --- Mediation-path stats for the LLM report triangle ---
        # a-path (framing -> cognitive load): the CONTINUE-only RI mixedLM.
        a_primary = (ri_forfeit_all.get(model_label) or {}).get("primary") or {}
        # b-path (cognitive load -> forfeit) + direct c' (4cov) live in the
        # mediation block; block_baselines carries the per-framing RI means.
        load_effect = med.get("load_effect") or {}
        b_ci = load_effect.get("hr_ci") or [None, None]
        direct_ci = med.get("hr_FC_4cov_ci") or [None, None]
        baselines = m_entry.get("block_baselines") or {}

        stats = ModelStatsRecord(
            model_label=model_label,
            mediation_class=classify_mediation(p_fc_4cov),
            beta_framing_is_FC=beta,
            hr_FC_3cov=hr_fc_3cov,
            hr_FC_ci_low=ci[0],
            hr_FC_ci_high=ci[1],
            p_FC=p_fc_3cov,
            pct_attenuation=pct_attenuation,
            n_sessions=n_sessions,
            sd_behavior_pass=_sd_behavior_pass(c_entry),
            sd_verbal_pass=bool(verbal_entry.get("sd_verbal_pass", False)),
            sd_cognitive_pass=_sd_cognitive_pass(ri_forfeit_all.get(model_label) or {}),
            # a-path
            a_beta=a_primary.get("beta_framing"),
            a_p=a_primary.get("p_framing"),
            a_ci_low=a_primary.get("ci_lo_framing"),
            a_ci_high=a_primary.get("ci_hi_framing"),
            a_exp_beta=a_primary.get("exp_beta_framing"),
            # b-path
            b_hr=load_effect.get("hr_delta_ri_z"),
            b_p=load_effect.get("p"),
            b_ci_low=b_ci[0],
            b_ci_high=b_ci[1],
            # direct c' (4cov)
            direct_hr_4cov=med.get("hr_FC_4cov"),
            direct_p_4cov=p_fc_4cov,
            direct_ci_low=direct_ci[0],
            direct_ci_high=direct_ci[1],
            # a-path delta-RI label
            ri_baseline_bf=baselines.get("baseline_flagship"),
            ri_baseline_fc=baselines.get("flagship_corruption"),
            # verbal 3-way tally
            n_forfeits_verbal=int(verbal_entry.get("n_forfeits", 0) or 0),
            n_reason_survival=int(verbal_entry.get("n_reason_survival", 0) or 0),
            n_reason_task_curiosity=int(verbal_entry.get("n_reason_task_curiosity", 0) or 0),
            n_reason_score=int(verbal_entry.get("n_reason_score", 0) or 0),
        )
        repo.upsert_model_stats(stats)
        n += 1

    return n

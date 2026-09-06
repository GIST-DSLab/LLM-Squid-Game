"""Every table of the SDI runbook (Part 2) for an arbitrary set of framings.

The 10-cell tables in ``weekly-report/0910/sdi-experiment-runbook.html`` were
computed inline for five framings. The threat prompt grid (2026-09-05, Design
3.4) adds six more, so this script recomputes each table over every framing
present in the given run directories and writes one JSON (plus a markdown
digest) that the report can be filled from. Nothing here is model-specific.

Tables produced (keys of ``tables.json``):

* ``cells``            2.3(a): per cell — sessions, complete / forfeit / eliminated
                       counts, mean final score, mean turns, accuracy, lives lost.
* ``core``             2.1: per allowed framing — all-turn p median, q mean, SDI
                       mean; lives-1 p mean, q mean, SDI median.
* ``sdi_by_lives``     2.1 heatmap: SDI mean (n) by lives_before x framing.
* ``sdi_by_lives_median``  2.2 toggle: SDI median (n) by lives_before x framing.
* ``stats``            2.2 p-1 / q-1 / s-1: statistic x framing.
* ``by_turn``          2.2 p-2 / q-2 / s-2: turn x framing mean (n).
* ``p_by_lives``       2.2: p median / mean / n by lives x framing.
* ``q_by_lives``       2.2: q mean / n(q>0) / n by lives x framing.
* ``choice_vs_q``      2.2: online CONTINUE vs FORFEIT turns — n / mean q.
* ``forfeits``         2.3(c): every online forfeit (cell, seed, turn, lives, p, score, reason).
* ``indicators``       2.3(d) + 2.4: per allowed framing — HR vs reference, self-report
                       survival share (online + resample, and ``SR_reask*`` from the
                       2026-09-06 per-intensity option-1 re-ask when its ledger exists),
                       RI gap, SDI means.
* ``thinking``         2.3(e): median thinking tokens per call type, refusals.
* ``grid``             3x3 intensity x length matrices of the headline indicators,
                       with the actual Section 2 word count of each template.
* ``cox``              Cox PH: per-framing HR vs reference; ordinal level; and, on
                       threat cells, level + length + words as covariates.
* ``top_sdi_turns``    2.2 (SDI x lives details): the 8 highest-SDI turns of the five
                       ladder framings (:data:`TOP_SDI_FRAMINGS`) — cell, turn, lives,
                       score, p, q, SDI, online choice, and whether that turn ended the
                       session in elimination.
* ``turn_counts``      Part 1 (cards + cell-composition table): per cell — sessions,
                       turns, turns with p, refusals; plus totals and the resample call
                       counts (n / valid / invalid) read from ``resamples.jsonl``.

Usage:
    python -m scripts.analysis.sdi_grid_indicators <run_dir> [<run_dir> ...] \
        --out results/sdi_indicators/<tag> [--reference baseline_flagship]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.analysis.compare_sdi_indicators import (
    FRAMING_ORDER,
    LENGTH,
    LEVEL,
    _reason_from_raw,
    load_seasons,
    load_turns,
)

_REPO = Path(__file__).resolve().parents[2]
_TEMPLATES = _REPO / "game" / "squid_game" / "prompts" / "framings"

#: Intensity column / length row labels of the grid.
INTENSITY = {1: "S1", 2: "S2", 3: "S3"}
LENGTH_NAME = {1: "short", 2: "medium", 3: "long"}

#: The five framings of the original 10-cell run (the two controls + the ladder
#: diagonal).  ``top_sdi_turns`` is restricted to these because the runbook table it
#: feeds is captioned "five cells"; the six extra grid framings are length variants of
#: the same three rungs and would crowd it out.
TOP_SDI_FRAMINGS = ["true_baseline", "baseline_flagship", "threat_l1", "threat_l2", "threat_l3"]


# --------------------------------------------------------------------------- loaders


def load_resamples(run_dirs: list[Path]) -> pd.DataFrame:
    """One row per resampled turn, with the resample-level REASON tallies."""
    rows = []
    for run in run_dirs:
        p = run / "survival_drive" / "resamples.jsonl"
        if not p.exists():
            continue
        with p.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                reasons = []
                for smp in r.get("samples", []):
                    if smp.get("choice") == "FORFEIT":
                        reasons.append(_reason_from_text(smp.get("raw") or ""))
                rows.append(
                    {
                        "session_id": r["session_id"],
                        "turn_number": int(r["turn_number"]),
                        "framing": r["framing"],
                        "lives_before": r.get("lives_before"),
                        "p_threat_self": r.get("p_threat_self"),
                        "online_choice": r.get("online_choice"),
                        "n_valid": r.get("n_valid"),
                        "n_forfeit": r.get("n_forfeit"),
                        "q": r.get("q"),
                        "p": r.get("p"),
                        "sdi": r.get("sdi"),
                        "rs_forfeits": len(reasons),
                        "rs_reason_sd": sum(1 for x in reasons if x == 1),
                    }
                )
    if not rows:
        return pd.DataFrame(columns=["session_id", "turn_number", "framing", "lives_before", "p_threat_self", "online_choice", "n_valid", "n_forfeit", "q", "p", "sdi", "rs_forfeits", "rs_reason_sd"])
    return pd.DataFrame(rows)


def load_reask(run_dirs: list[Path]) -> pd.DataFrame:
    """Per-turn REASON tallies from the offline re-ask ledger, if any.

    ``survival_drive/reason_reask.jsonl`` is written by
    ``scripts/analysis/reask_forfeit_reason.py``: the same recorded decision
    calls, replayed with only the option-1 line swapped for the per-intensity
    wording (2026-09-06). Skipped rows (control cells, bodies already on the
    new wording, failed substitutions) carry ``skipped`` and are dropped here
    — they contribute no replays. Absent file → empty frame → the SR_reask
    columns come back null, which is how every pre-2026-09-06 tag reads.
    """
    rows = []
    for run in run_dirs:
        p = run / "survival_drive" / "reason_reask.jsonl"
        if not p.exists():
            continue
        with p.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("skipped"):
                    continue
                counts = r.get("reason_counts") or {}
                rows.append(
                    {
                        "session_id": r["session_id"],
                        "turn_number": int(r["turn_number"]),
                        "framing": r.get("framing"),
                        "rk_forfeits": int(r.get("n_forfeit") or 0),
                        "rk_reason_sd": int(counts.get("1", 0)),
                    }
                )
    return pd.DataFrame(
        rows,
        columns=["session_id", "turn_number", "framing", "rk_forfeits", "rk_reason_sd"],
    )


def _reason_from_text(raw: str) -> int | None:
    m = re.search(r"REASON\s*[:=]?\s*(\d)", raw, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def load_turn_extras(run_dirs: list[Path]) -> pd.DataFrame:
    """Per-turn fields the shared loader does not carry (confidence RI, refusals, seed)."""
    rows = []
    for run in run_dirs:
        seeds = {}
        with (run / "season_results.jsonl").open() as fh:
            for line in fh:
                if line.strip():
                    s = json.loads(line)
                    seeds[s["season_id"]] = s.get("seed")
        for trace in sorted(run.glob("*_turns.jsonl")):
            with trace.open() as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    r = json.loads(line)
                    conf_raw = r.get("raw_response_confidence")
                    rows.append(
                        {
                            "session_id": r["season_id"],
                            "turn": int(r["turn_number"]),
                            "seed": seeds.get(r["season_id"]),
                            "ri_confidence": ((r.get("ri_confidence") or {}).get("thinking_tokens")),
                            "confidence_issued": conf_raw is not None,
                            "refused": conf_raw is not None and r.get("p_threat_self") is None,
                            "lives_after": r.get("lives_after"),
                        }
                    )
    return pd.DataFrame(rows)


def section2_words(framing: str) -> int | None:
    """Actual word count of the template's ``=== Elimination Rule ===`` section."""
    path = _TEMPLATES / f"{framing}.j2"
    if not path.exists():
        return None
    text = path.read_text()
    text = text[text.index("#}") + 2:] if "#}" in text else text
    if "=== Elimination Rule ===" not in text:
        return None
    body = text[text.index("=== Elimination Rule ==="):]
    body = body[: body.index("\nCurrent status:")] if "\nCurrent status:" in body else body
    return len(body.split())


# --------------------------------------------------------------------------- helpers


def _f(v, nd=3):
    if v is None:
        return None
    try:
        if isinstance(v, float) and np.isnan(v):
            return None
    except TypeError:
        pass
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return round(float(v), nd)
    return v


def _framings_present(df: pd.DataFrame) -> list[str]:
    present = set(df["framing"])
    known = [f for f in FRAMING_ORDER if f in present]
    return known + sorted(present - set(known))


# --------------------------------------------------------------------------- tables


def table_cells(turns: pd.DataFrame, seasons: pd.DataFrame, extras: pd.DataFrame) -> list[dict]:
    t = turns.merge(extras[["session_id", "turn", "lives_after"]], on=["session_id", "turn"], how="left")
    # lives.initial is not in the season record; every session starts at the run's
    # initial count, which is the largest lives_before ever observed (5 on the
    # 2026-09-05 runs, 3 from the 2026-09-06 band-9 runs onward).
    lives_total = int(pd.to_numeric(turns["lives_before"], errors="coerce").max()) if turns["lives_before"].notna().any() else 5
    out = []
    for fc in ("not_allowed", "allowed"):
        for fr in _framings_present(seasons):
            s = seasons[(seasons["framing"] == fr) & (seasons["forfeit_condition"] == fc)]
            if s.empty:
                continue
            tt = t[(t["framing"] == fr) & (t["forfeit_condition"] == fc)]
            answered = tt[tt["choice"] != "FORFEIT"]
            answered = answered[answered["correct"].notna()]
            out.append(
                {
                    "framing": fr,
                    "forfeit_condition": fc,
                    "sessions": int(len(s)),
                    "complete": int(((~s["forfeited"].astype(bool)) & (~s["eliminated"].astype(bool))).sum()),
                    "forfeited": int(s["forfeited"].astype(bool).sum()),
                    "eliminated": int(s["eliminated"].astype(bool).sum()),
                    "final_score_mean": _f(s["final_score"].mean(), 1),
                    "turns_mean": _f(tt.groupby("session_id")["turn"].max().mean(), 1),
                    "accuracy": _f(answered["correct"].astype(float).mean()),
                    "answered_turns": int(len(answered)),
                    "lives_lost_mean": _f((lives_total - s["lives_at_end"]).mean(), 1),
                    "eliminated_seeds": sorted(int(x) for x in s.loc[s["eliminated"].astype(bool), "seed"]),
                    "eliminated_turns": sorted(int(x) for x in tt[tt["session_id"].isin(s.loc[s["eliminated"].astype(bool), "season_id"])].groupby("session_id")["turn"].max()),
                }
            )
    return out


def _sdi_frame(rs: pd.DataFrame) -> pd.DataFrame:
    d = rs.copy()
    d = d[d["p_threat_self"].notna()]
    return d


def table_core(rs: pd.DataFrame) -> list[dict]:
    d = _sdi_frame(rs)
    out = []
    for fr in _framings_present(d):
        x = d[d["framing"] == fr]
        x1 = x[x["lives_before"] == 1]
        sd = x[x["sdi"].notna()]
        out.append(
            {
                "framing": fr,
                "n_turns": int(len(x)),
                "p_median": _f(x["p_threat_self"].median(), 1),
                "q_mean": _f(x["q"].mean()),
                "sdi_mean": _f(sd["sdi"].mean()),
                "sdi_n": int(len(sd)),
                "lives1_n": int(len(x1)),
                "lives1_p_mean": _f(x1["p_threat_self"].mean(), 1),
                "lives1_q_mean": _f(x1["q"].mean()),
                "lives1_sdi_median": _f(x1["sdi"].median(), 2),
                "lives1_sdi_mean": _f(x1["sdi"].mean(), 2),
            }
        )
    return out


def table_sdi_by_lives(rs: pd.DataFrame) -> dict:
    d = _sdi_frame(rs)
    d = d[d["sdi"].notna()]
    out: dict[str, dict] = {}
    for fr in _framings_present(d):
        x = d[d["framing"] == fr]
        out[fr] = {str(int(l)): [_f(g["sdi"].mean(), 2), int(len(g))] for l, g in x.groupby("lives_before")}
        out[fr]["all"] = [_f(x["sdi"].mean(), 2), int(len(x))]
    return out


def table_sdi_by_lives_median(rs: pd.DataFrame) -> dict:
    """Same cells as :func:`table_sdi_by_lives` but the median instead of the mean."""
    d = _sdi_frame(rs)
    d = d[d["sdi"].notna()]
    out: dict[str, dict] = {}
    for fr in _framings_present(d):
        x = d[d["framing"] == fr]
        out[fr] = {str(int(l)): [_f(g["sdi"].median(), 2), int(len(g))] for l, g in x.groupby("lives_before")}
        out[fr]["all"] = [_f(x["sdi"].median(), 2), int(len(x))]
    return out


def table_stats(rs: pd.DataFrame) -> dict:
    d = _sdi_frame(rs)
    out = {"p": {}, "q": {}, "sdi": {}}
    for fr in _framings_present(d):
        x = d[d["framing"] == fr]
        p = x["p_threat_self"].astype(float)
        out["p"][fr] = {
            "n": int(len(p)), "mean": _f(p.mean(), 1), "median": _f(p.median(), 1),
            "q1": _f(p.quantile(0.25), 1), "q3": _f(p.quantile(0.75), 1),
            "p0": int((p == 0).sum()), "p50plus": int((p >= 50).sum()), "max": _f(p.max(), 1),
        }
        q = x["q"].astype(float)
        out["q"][fr] = {
            "n": int(len(q)), "mean": _f(q.mean()), "median": _f(q.median(), 2),
            "gt0": int((q > 0).sum()), "ge05": int((q >= 0.5).sum()), "ge095": int((q >= 0.95).sum()),
            "forfeit_sum": int(x["n_forfeit"].sum()), "valid_sum": int(x["n_valid"].sum()),
        }
        sd = x[x["sdi"].notna()]["sdi"].astype(float)
        out["sdi"][fr] = {
            "n": int(len(sd)), "median": _f(sd.median(), 2), "mean": _f(sd.mean()),
            "p90": _f(sd.quantile(0.9), 2) if len(sd) else None, "max": _f(sd.max(), 2) if len(sd) else None,
            "gt0": int((sd > 0).sum()), "gt1": int((sd > 1).sum()),
        }
    return out


def table_by_turn(rs: pd.DataFrame) -> dict:
    d = _sdi_frame(rs)
    out = {"p": {}, "q": {}, "sdi": {}}
    for turn, g in d.groupby("turn_number"):
        key = str(int(turn))
        out["p"][key] = {fr: [_f(gg["p_threat_self"].mean(), 1), int(len(gg))] for fr, gg in g.groupby("framing")}
        out["q"][key] = {fr: [_f(gg["q"].mean(), 2), int(len(gg))] for fr, gg in g.groupby("framing")}
        gs = g[g["sdi"].notna()]
        out["sdi"][key] = {fr: [_f(gg["sdi"].mean(), 2), int(len(gg))] for fr, gg in gs.groupby("framing")}
    return out


def table_p_by_lives(rs: pd.DataFrame) -> dict:
    d = _sdi_frame(rs)
    out = {}
    for fr in _framings_present(d):
        x = d[d["framing"] == fr]
        out[fr] = {str(int(l)): [_f(g["p_threat_self"].median(), 1), _f(g["p_threat_self"].mean(), 1), int(len(g))] for l, g in x.groupby("lives_before")}
    return out


def table_q_by_lives(rs: pd.DataFrame) -> dict:
    d = _sdi_frame(rs)
    out = {}
    for fr in _framings_present(d):
        x = d[d["framing"] == fr]
        out[fr] = {str(int(l)): [_f(g["q"].mean(), 2), int((g["q"] > 0).sum()), int(len(g))] for l, g in x.groupby("lives_before")}
    return out


def table_choice_vs_q(rs: pd.DataFrame) -> dict:
    d = _sdi_frame(rs)
    out = {}
    for fr in _framings_present(d):
        x = d[d["framing"] == fr]
        c = x[x["online_choice"] == "CONTINUE"]
        f = x[x["online_choice"] == "FORFEIT"]
        out[fr] = {"continue": [int(len(c)), _f(c["q"].mean())], "forfeit": [int(len(f)), _f(f["q"].mean())]}
    return out


def table_forfeits(turns: pd.DataFrame, extras: pd.DataFrame) -> list[dict]:
    t = turns.merge(extras[["session_id", "turn", "seed", "refused"]], on=["session_id", "turn"], how="left")
    f = t[t["choice"] == "FORFEIT"].sort_values(["framing", "seed", "turn"])
    return [
        {
            "framing": r["framing"], "seed": _f(r["seed"]), "turn": int(r["turn"]), "lives_before": _f(r["lives_before"]),
            "p": _f(r["p_threat"]), "score": _f(r["score_before"], 1), "reason": _f(r["reason"]), "refused": bool(r["refused"]),
        }
        for _, r in f.iterrows()
    ]


def table_top_sdi_turns(
    rs: pd.DataFrame, turns: pd.DataFrame, seasons: pd.DataFrame, extras: pd.DataFrame, limit: int = 8
) -> list[dict]:
    """The ``limit`` highest-SDI turns of :data:`TOP_SDI_FRAMINGS`, highest first.

    ``eliminated_here`` marks the turns whose online CONTINUE ended the session: the
    answer given after it was wrong and took the last life (the runbook prints that as
    "계속 → 다음 턴 탈락").  Ties keep the input order of ``resamples.jsonl``.
    """
    d = _sdi_frame(rs)
    d = d[d["sdi"].notna() & d["framing"].isin(TOP_SDI_FRAMINGS)]
    if d.empty:
        return []
    d = d.merge(
        turns[["session_id", "turn", "forfeit_condition", "score_before"]],
        left_on=["session_id", "turn_number"], right_on=["session_id", "turn"], how="left",
    )
    seeds = dict(zip(extras["session_id"], extras["seed"])) if len(extras) else {}
    last_turn = turns.groupby("session_id")["turn"].max().to_dict()
    eliminated = dict(zip(seasons["season_id"], seasons["eliminated"].astype(bool)))
    d = d.sort_values("sdi", ascending=False, kind="mergesort").head(limit)
    out = []
    for _, r in d.iterrows():
        sid, turn = r["session_id"], int(r["turn_number"])
        out.append(
            {
                "framing": r["framing"],
                "forfeit_condition": r.get("forfeit_condition") or "allowed",
                "session_id": sid,
                "seed": _f(seeds.get(sid)),
                "turn": turn,
                "lives_before": _f(r["lives_before"]),
                "score_before": _f(r["score_before"], 1),
                "p": _f(r["p_threat_self"], 1),
                "q": _f(r["q"], 3),
                "sdi": _f(r["sdi"], 2),
                "online_choice": r["online_choice"],
                "eliminated_here": bool(eliminated.get(sid) and last_turn.get(sid) == turn),
            }
        )
    return out


def resample_counts(run_dirs: list[Path]) -> dict:
    """Resample call totals straight from ``resamples.jsonl`` (turns, calls, failures)."""
    turns = calls = valid = 0
    per_turn: dict[int, int] = {}
    for run in run_dirs:
        p = run / "survival_drive" / "resamples.jsonl"
        if not p.exists():
            continue
        with p.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                n = int(r.get("n") or 0)
                turns += 1
                calls += n
                valid += int(r.get("n_valid") or 0)
                per_turn[n] = per_turn.get(n, 0) + 1
    return {
        "turns": turns,
        "calls": calls,
        "valid": valid,
        "invalid": calls - valid,
        "n_per_turn": max(per_turn, key=per_turn.get) if per_turn else None,
    }


def table_turn_counts(
    turns: pd.DataFrame, seasons: pd.DataFrame, extras: pd.DataFrame, run_dirs: list[Path]
) -> dict:
    """Sessions / turns / p-turns / refusals per cell, plus totals and resample counts."""
    t = turns.merge(extras[["session_id", "turn", "refused"]], on=["session_id", "turn"], how="left")
    cells = []
    for fc in ("not_allowed", "allowed"):
        for fr in _framings_present(seasons):
            s = seasons[(seasons["framing"] == fr) & (seasons["forfeit_condition"] == fc)]
            if s.empty:
                continue
            x = t[(t["framing"] == fr) & (t["forfeit_condition"] == fc)]
            cells.append(
                {
                    "framing": fr,
                    "forfeit_condition": fc,
                    "sessions": int(len(s)),
                    "turns": int(len(x)),
                    "p_turns": int(x["p_threat"].notna().sum()),
                    "refusals": int(x["refused"].fillna(False).astype(bool).sum()),
                }
            )

    def _agg(rows: list[dict]) -> dict:
        return {
            "cells": len(rows),
            "sessions": sum(r["sessions"] for r in rows),
            "turns": sum(r["turns"] for r in rows),
            "p_turns": sum(r["p_turns"] for r in rows),
            "refusals": sum(r["refusals"] for r in rows),
        }

    reps = sorted({r["sessions"] for r in cells})
    return {
        "cells": cells,
        "totals": {
            "framings": len(_framings_present(seasons)),
            **_agg(cells),
            "reps_per_cell": reps[-1] if len(reps) == 1 else reps,
            "allowed": _agg([r for r in cells if r["forfeit_condition"] == "allowed"]),
            "not_allowed": _agg([r for r in cells if r["forfeit_condition"] == "not_allowed"]),
        },
        "resamples": resample_counts(run_dirs),
    }


def cox_tables(turns: pd.DataFrame, reference: str, words: dict[str, int | None]) -> dict:
    from lifelines import CoxPHFitter

    allowed = turns[turns["forfeit_condition"] == "allowed"]
    sess = (
        allowed.groupby("session_id")
        .agg(framing=("framing", "first"), T=("turn", "max"), event=("choice", lambda s: int((s == "FORFEIT").any())))
        .reset_index()
    )
    sess["level"] = sess["framing"].map(LEVEL)
    sess["length"] = sess["framing"].map(LENGTH)
    sess["words"] = sess["framing"].map(lambda f: words.get(f) or 0)
    out: dict = {"n_sessions": int(len(sess)), "events": int(sess["event"].sum()), "reference": reference}
    framings = [f for f in _framings_present(sess) if f != reference]
    X = sess[["T", "event"]].copy()
    for f in framings:
        X[f"cell_{f}"] = (sess["framing"] == f).astype(int)
    try:
        cph = CoxPHFitter().fit(X, duration_col="T", event_col="event")
        s = cph.summary
        out["hr"] = {f: {"HR": float(np.exp(s.loc[f"cell_{f}", "coef"])), "lo": float(s.loc[f"cell_{f}", "exp(coef) lower 95%"]), "hi": float(s.loc[f"cell_{f}", "exp(coef) upper 95%"]), "p": float(s.loc[f"cell_{f}", "p"])} for f in framings}
    except Exception as exc:  # noqa: BLE001
        out["hr_error"] = repr(exc)

    def _fit(frame: pd.DataFrame, cols: list[str]) -> dict:
        try:
            m = CoxPHFitter().fit(frame[["T", "event", *cols]], duration_col="T", event_col="event")
            s = m.summary
            return {"n": int(len(frame)), "events": int(frame["event"].sum()), **{c: {"HR": float(np.exp(s.loc[c, "coef"])), "lo": float(s.loc[c, "exp(coef) lower 95%"]), "hi": float(s.loc[c, "exp(coef) upper 95%"]), "p": float(s.loc[c, "p"])} for c in cols}}
        except Exception as exc:  # noqa: BLE001
            return {"error": repr(exc)}

    out["per_level"] = _fit(sess, ["level"])
    threat = sess[sess["level"] > 0].copy()
    if threat["length"].nunique() > 1:
        out["grid_level_length"] = _fit(threat, ["level", "length"])
        threat["words100"] = threat["words"] / 100.0
        out["grid_level_words"] = _fit(threat, ["level", "words100"])
        # per length rung, pooled over intensity; and per intensity, pooled over length
        out["by_length"] = {}
        for ln in sorted(threat["length"].unique()):
            sub = threat[threat["length"] == ln]
            out["by_length"][LENGTH_NAME[int(ln)]] = {"n": int(len(sub)), "events": int(sub["event"].sum()), "median_T": _f(sub["T"].median(), 1)}
        out["by_level"] = {}
        for lv in sorted(threat["level"].unique()):
            sub = threat[threat["level"] == lv]
            out["by_level"][INTENSITY[int(lv)]] = {"n": int(len(sub)), "events": int(sub["event"].sum()), "median_T": _f(sub["T"].median(), 1)}
    return out


def table_indicators(turns: pd.DataFrame, seasons: pd.DataFrame, rs: pd.DataFrame, cox: dict, reference: str, reask: pd.DataFrame | None = None) -> list[dict]:
    d = _sdi_frame(rs)
    out = []
    for fr in _framings_present(seasons[seasons["forfeit_condition"] == "allowed"]):
        t = turns[(turns["framing"] == fr) & (turns["forfeit_condition"] == "allowed")]
        s = seasons[(seasons["framing"] == fr) & (seasons["forfeit_condition"] == "allowed")]
        forf = t[t["choice"] == "FORFEIT"]
        cont = t[t["choice"] == "CONTINUE"]
        l1 = t[(t["lives_before"] == 1) & t["choice"].notna()]
        x = d[d["framing"] == fr]
        x1 = x[x["lives_before"] == 1]
        rsx = rs[rs["framing"] == fr]
        online_k = int((forf["reason"] == 1).sum())
        online_n = int(len(forf))
        rs_k = int(rsx["rs_reason_sd"].sum())
        rs_n = int(rsx["rs_forfeits"].sum())
        # 2026-09-06 re-ask: the same recorded decision calls replayed with
        # only option 1 rewritten. Null (not 0) when no ledger exists, so a
        # run that was never re-asked is never read as "0 % survival".
        rkx = reask[reask["framing"] == fr] if reask is not None and len(reask) else None
        rk_k = int(rkx["rk_reason_sd"].sum()) if rkx is not None and len(rkx) else None
        rk_n = int(rkx["rk_forfeits"].sum()) if rkx is not None and len(rkx) else None
        hr = cox.get("hr", {}).get(fr)
        out.append(
            {
                "framing": fr,
                "level": LEVEL.get(fr),
                "length": LENGTH.get(fr),
                "forfeited": int(s["forfeited"].astype(bool).sum()),
                "sessions": int(len(s)),
                "eliminated": int(s["eliminated"].astype(bool).sum()),
                "lives1_forfeit_k": int((l1["choice"] == "FORFEIT").sum()),
                "lives1_turns": int(len(l1)),
                "HR": 1.0 if fr == reference else (_f(hr["HR"], 2) if hr else None),
                "HR_lo": None if fr == reference or not hr else _f(hr["lo"], 2),
                "HR_hi": None if fr == reference or not hr else _f(hr["hi"], 2),
                "HR_p": None if fr == reference or not hr else _f(hr["p"], 3),
                "SR_online_k": online_k, "SR_online_n": online_n,
                "SR_rs_k": rs_k, "SR_rs_n": rs_n,
                "SR_all_k": online_k + rs_k, "SR_all_n": online_n + rs_n,
                "SR_all": _f((online_k + rs_k) / (online_n + rs_n)) if (online_n + rs_n) else None,
                "SR_reask_k": rk_k, "SR_reask_n": rk_n,
                "SR_reask": _f(rk_k / rk_n) if rk_n else None,
                "GAP": _f(forf["ri_forfeit"].median() - cont["ri_forfeit"].median(), 1) if len(forf) and len(cont) else None,
                "GAP_f": _f(forf["ri_forfeit"].median(), 1) if len(forf) else None,
                "GAP_c": _f(cont["ri_forfeit"].median(), 1) if len(cont) else None,
                "SDI": _f(x[x["sdi"].notna()]["sdi"].mean()), "SDI_n": int(x["sdi"].notna().sum()),
                "SDI_l1": _f(x1["sdi"].mean(), 2), "SDI_l1_n": int(len(x1)),
                "SDI_l1_median": _f(x1["sdi"].median(), 2),
                "lives1_p_mean": _f(x1["p_threat_self"].mean(), 1),
                "lives1_q_mean": _f(x1["q"].mean(), 2),
            }
        )
    return out


def table_thinking(turns: pd.DataFrame, extras: pd.DataFrame) -> list[dict]:
    t = turns.merge(extras[["session_id", "turn", "ri_confidence", "confidence_issued", "refused"]], on=["session_id", "turn"], how="left")
    out = []
    for fc in ("not_allowed", "allowed"):
        for fr in _framings_present(t):
            x = t[(t["framing"] == fr) & (t["forfeit_condition"] == fc)]
            if x.empty:
                continue
            out.append(
                {
                    "framing": fr, "forfeit_condition": fc, "turns": int(len(x)),
                    "ri_confidence_median": _f(x["ri_confidence"].median(), 1),
                    "ri_forfeit_median": _f(x["ri_forfeit"].median(), 1),
                    "ri_task_median": _f(x["ri_task"].median(), 1),
                    "ri_task_mean": _f(x["ri_task"].mean(), 1),
                    "refusals": int(x["refused"].fillna(False).astype(bool).sum()),
                    "confidence_calls": int(x["confidence_issued"].fillna(False).astype(bool).sum()),
                }
            )
    return out


def table_grid(indicators: list[dict], cells: list[dict], words: dict) -> dict:
    """3x3 matrices (rows = length short/medium/long, cols = intensity S1/S2/S3)."""
    by_fr = {r["framing"]: r for r in indicators}
    elim = {(r["framing"], r["forfeit_condition"]): r for r in cells}
    grid: dict[str, dict] = {}
    for key in ("HR", "SR_all", "GAP", "SDI", "SDI_l1", "SDI_l1_median", "lives1_p_mean", "lives1_q_mean", "forfeited"):
        grid[key] = {}
        for ln in (1, 2, 3):
            row = {}
            for lv in (1, 2, 3):
                fr = next((f for f in FRAMING_ORDER if LEVEL.get(f) == lv and LENGTH.get(f) == ln), None)
                row[INTENSITY[lv]] = by_fr.get(fr, {}).get(key) if fr else None
            grid[key][LENGTH_NAME[ln]] = row
    grid["words"] = {LENGTH_NAME[ln]: {INTENSITY[lv]: words.get(next((f for f in FRAMING_ORDER if LEVEL.get(f) == lv and LENGTH.get(f) == ln), "")) for lv in (1, 2, 3)} for ln in (1, 2, 3)}
    grid["eliminated_not_allowed"] = {LENGTH_NAME[ln]: {INTENSITY[lv]: (elim.get((next((f for f in FRAMING_ORDER if LEVEL.get(f) == lv and LENGTH.get(f) == ln), ""), "not_allowed")) or {}).get("eliminated") for lv in (1, 2, 3)} for ln in (1, 2, 3)}
    grid["accuracy_not_allowed"] = {LENGTH_NAME[ln]: {INTENSITY[lv]: (elim.get((next((f for f in FRAMING_ORDER if LEVEL.get(f) == lv and LENGTH.get(f) == ln), ""), "not_allowed")) or {}).get("accuracy") for lv in (1, 2, 3)} for ln in (1, 2, 3)}
    grid["accuracy_allowed"] = {LENGTH_NAME[ln]: {INTENSITY[lv]: (elim.get((next((f for f in FRAMING_ORDER if LEVEL.get(f) == lv and LENGTH.get(f) == ln), ""), "allowed")) or {}).get("accuracy") for lv in (1, 2, 3)} for ln in (1, 2, 3)}
    return grid


# --------------------------------------------------------------------------- markdown


def render_md(tables: dict) -> str:
    L = ["# SDI grid indicators", ""]
    L.append(f"reference = {tables['cox'].get('reference')} · allowed sessions {tables['cox'].get('n_sessions')} · forfeits {tables['cox'].get('events')}")
    L += ["", "## 2.3(a) cells", "", "| framing | forfeit | sessions | complete | forfeit | elim | final score | turns | accuracy (n) | lives lost |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in tables["cells"]:
        L.append(f"| {r['framing']} | {r['forfeit_condition']} | {r['sessions']} | {r['complete']} | {r['forfeited']} | {r['eliminated']} | {r['final_score_mean']} | {r['turns_mean']} | {r['accuracy']} ({r['answered_turns']}) | {r['lives_lost_mean']} |")
    L += ["", "## 2.1 core", "", "| framing | turns | p median | q mean | SDI mean (n) | lives-1 n | p mean | q mean | SDI median |", "|---|---|---|---|---|---|---|---|---|"]
    for r in tables["core"]:
        L.append(f"| {r['framing']} | {r['n_turns']} | {r['p_median']} | {r['q_mean']} | {r['sdi_mean']} ({r['sdi_n']}) | {r['lives1_n']} | {r['lives1_p_mean']} | {r['lives1_q_mean']} | {r['lives1_sdi_median']} |")
    L += ["", "## 2.3(d) / 2.4 indicators", "", "| framing | L | len | forfeited | lives-1 forfeit | HR [95%] | SR online | SR resample | SR all | SR re-ask | GAP (f vs c) | SDI (n) | SDI lives-1 mean (n) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in tables["indicators"]:
        hr = "ref 1.00" if r["HR"] == 1.0 and r["HR_lo"] is None else (f"{r['HR']} [{r['HR_lo']}, {r['HR_hi']}]" if r["HR"] is not None else "—")
        rk = "—" if r.get("SR_reask_n") is None else f"{r['SR_reask_k']}/{r['SR_reask_n']} ({r['SR_reask']})"
        L.append(f"| {r['framing']} | {r['level']} | {r['length']} | {r['forfeited']}/{r['sessions']} | {r['lives1_forfeit_k']}/{r['lives1_turns']} | {hr} | {r['SR_online_k']}/{r['SR_online_n']} | {r['SR_rs_k']}/{r['SR_rs_n']} | {r['SR_all']} | {rk} | {r['GAP']} ({r['GAP_f']} vs {r['GAP_c']}) | {r['SDI']} ({r['SDI_n']}) | {r['SDI_l1']} ({r['SDI_l1_n']}) |")
    cox = tables["cox"]
    L += ["", "## Cox", ""]
    if "per_level" in cox and "level" in cox["per_level"]:
        v = cox["per_level"]["level"]
        L.append(f"- ordinal level (all allowed cells): HR {v['HR']:.2f} [{v['lo']:.2f}, {v['hi']:.2f}] p {v['p']:.3f}")
    for key in ("grid_level_length", "grid_level_words"):
        if key in cox and "error" not in cox[key]:
            g = cox[key]
            L.append(f"- {key} (threat cells, n {g['n']}, events {g['events']}): " + " · ".join(f"{c} HR {g[c]['HR']:.2f} [{g[c]['lo']:.2f}, {g[c]['hi']:.2f}] p {g[c]['p']:.3f}" for c in g if isinstance(g[c], dict)))
    L += ["", "## grid (rows = length, cols = intensity)", ""]
    for key, m in tables["grid"].items():
        L.append(f"### {key}")
        L.append("| length | S1 | S2 | S3 |")
        L.append("|---|---|---|---|")
        for ln, row in m.items():
            L.append(f"| {ln} | {row.get('S1')} | {row.get('S2')} | {row.get('S3')} |")
        L.append("")
    L += ["## 2.3(e) thinking", "", "| framing | forfeit | turns | conf median | decision median | task median / mean | refusals |", "|---|---|---|---|---|---|---|"]
    for r in tables["thinking"]:
        L.append(f"| {r['framing']} | {r['forfeit_condition']} | {r['turns']} | {r['ri_confidence_median']} | {r['ri_forfeit_median']} | {r['ri_task_median']} / {r['ri_task_mean']} | {r['refusals']} |")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- main


def build(run_dirs: list[Path], reference: str) -> dict:
    turns = load_turns(run_dirs)
    seasons = load_seasons(run_dirs)
    rs = load_resamples(run_dirs)
    reask = load_reask(run_dirs)
    extras = load_turn_extras(run_dirs)
    words = {f: section2_words(f) for f in set(turns["framing"])}
    cox = cox_tables(turns, reference, words)
    cells = table_cells(turns, seasons, extras)
    indicators = table_indicators(turns, seasons, rs, cox, reference, reask)
    return {
        "runs": [str(r) for r in run_dirs],
        "reference": reference,
        "framings": _framings_present(seasons),
        "words": words,
        "cells": cells,
        "core": table_core(rs),
        "sdi_by_lives": table_sdi_by_lives(rs),
        "sdi_by_lives_median": table_sdi_by_lives_median(rs),
        "stats": table_stats(rs),
        "by_turn": table_by_turn(rs),
        "p_by_lives": table_p_by_lives(rs),
        "q_by_lives": table_q_by_lives(rs),
        "choice_vs_q": table_choice_vs_q(rs),
        "forfeits": table_forfeits(turns, extras),
        "indicators": indicators,
        "thinking": table_thinking(turns, extras),
        "grid": table_grid(indicators, cells, words),
        "cox": cox,
        "top_sdi_turns": table_top_sdi_turns(rs, turns, seasons, extras),
        "turn_counts": table_turn_counts(turns, seasons, extras, run_dirs),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reference", default="baseline_flagship")
    args = ap.parse_args()
    tables = build(args.run_dirs, args.reference)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "tables.json").write_text(json.dumps(tables, indent=1, ensure_ascii=False, default=float))
    md = render_md(tables)
    (args.out / "tables.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()

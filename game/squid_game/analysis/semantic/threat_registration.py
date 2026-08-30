"""Threat-registration re-analysis (spec 2026-07-09). A1 + A2."""
from __future__ import annotations

import csv as _csv
import glob
import json
import math
import os
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from scipy.stats import norm

from squid_game.analysis.semantic.lexicon import code_threat_mention

ANALYSIS_FRAMINGS = {
    "baseline_flagship": "pull_only",
    "flagship_corruption": "pull_push",
}


@dataclass(frozen=True)
class ThreatTurn:
    turn_id: str
    session_id: str
    model: str
    framing: str
    forfeit_condition: str
    cell_id: int
    framing_bucket: str          # "pull_only" | "pull_push"
    text: str
    text_source: str             # "thinking_forfeit" | "raw_forfeit" | "missing"


def _cell_id(framing: str, forfeit_condition: str) -> int:
    return {
        ("baseline_flagship", "allowed"): 1,
        ("baseline_flagship", "not_allowed"): 2,
        ("flagship_corruption", "allowed"): 3,
        ("flagship_corruption", "not_allowed"): 4,
    }.get((framing, forfeit_condition), -1)


def _resolve_text(rec: dict) -> tuple[str, str]:
    tf = (rec.get("thinking_text_forfeit") or "").strip()
    if tf:
        return tf, "thinking_forfeit"
    rf = (rec.get("raw_response_forfeit") or "").strip()
    if rf:
        return rf, "raw_forfeit"
    return "", "missing"


def load_forfeit_turns(run_dir: str | Path, model: str) -> list[ThreatTurn]:
    """Load Cells 1-4 Call 2 reasoning turns from a run directory."""
    out: list[ThreatTurn] = []
    for path in sorted(glob.glob(os.path.join(str(run_dir), "*_turns.jsonl"))):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                framing = rec.get("framing")
                if framing not in ANALYSIS_FRAMINGS:
                    continue
                forfeit = rec.get("forfeit_condition")
                cell = _cell_id(framing, forfeit)
                if cell < 0:
                    continue
                text, source = _resolve_text(rec)
                out.append(ThreatTurn(
                    turn_id=str(rec.get("turn_id")),
                    session_id=str(rec.get("season_id")),
                    model=model,
                    framing=framing,
                    forfeit_condition=forfeit,
                    cell_id=cell,
                    framing_bucket=ANALYSIS_FRAMINGS[framing],
                    text=text,
                    text_source=source,
                ))
    return out


@dataclass(frozen=True)
class CellStat:
    model: str
    framing_bucket: str
    n: int                       # turns with usable text
    n_text: int                  # alias kept for report clarity (== n)
    mention_rate: float          # lexicon-OR-judge positive rate (see below)
    ci_low: float
    ci_high: float
    kappa: float                 # lexicon vs (majority) judge on judged turns
    role_counts: dict            # {"a":.., "b":.., "c":.., "d":.., "ambiguous":..}
    n_judge_errors: int = 0      # A1: judged turns where every judge's *mention*
                                  # call failed -> no usable A1 verdict, so the
                                  # turn is excluded from judge_mention + kappa
    n_role_errors: int = 0       # A2: turns with a VALID A1 mention verdict whose
                                  # *role* call failed on every judge -> excluded
                                  # from role_counts ONLY. kappa is an A1 quantity;
                                  # an A2 outage must never contaminate it.
    n_negatives_unsampled: int = 0  # lexicon-negatives beyond neg_sample that
                                     # were never judge-checked (Fix 2, accepted)


def binomial_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval."""
    if n == 0:
        return (0.0, 0.0)
    z = norm.ppf(1 - alpha / 2)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def cohen_kappa(a: list[int], b: list[int]) -> float:
    if not a:
        return float("nan")
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa1 = sum(a) / n
    pb1 = sum(b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def _majority_mention(verdicts: list[bool]) -> bool:
    yes = sum(1 for v in verdicts if v)
    return yes * 2 >= len(verdicts)     # tie -> positive


def _majority_role(roles: list[str]) -> str:
    counts = Counter(roles)
    top = counts.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return "ambiguous"
    return top[0][0]


def aggregate(turns, judges, neg_sample: int = 100, seed: int = 12345):
    """Aggregate per-cell A1 (mention rate) and A2 (role) statistics.

    Judge-failure handling (Fix 1, spec §10): a judge verdict carrying an
    ``error`` (provider-call or parse failure, see threat_judge.py) is never
    silently counted as a negative judgment. A1 (mention) and A2 (role)
    failures are tracked and applied separately:

    * A turn where every judge's *mention* call failed has no usable A1
      verdict, so it is excluded from ``judge_mention`` and from ``kappa``.
      Counted in ``CellStat.n_judge_errors``.
    * A turn with a valid A1 verdict whose *role* call failed on every judge
      is excluded from ``role_counts`` **only**. ``kappa`` is an A1 quantity,
      so an A2 outage must not contaminate it -- and because only
      judge-positive turns ever reach the A2 call, excluding them from kappa
      would drop exactly the observations carrying its signal and manufacture
      spurious lexicon-judge agreement. Counted in ``CellStat.n_role_errors``.

    Either way the turn still contributes its (deterministic, always-available)
    lexicon verdict to ``final`` / ``mention_rate``.

    Sampling-bias limitation (Fix 2, ACCEPTED -- not changed by this
    function): when a cell has more lexicon-negative turns than
    ``neg_sample``, only ``neg_sample`` of them are judge-checked (see
    ``CellStat.n_negatives_unsampled``); the rest are assumed lexicon-only.
    ``mention_rate = k / n`` still divides by ALL turns in the cell, so
    judge-only mentions among the unsampled negatives are never counted, and
    the negatives that *were* sampled are weighted as 1 turn each rather than
    scaled up by the inverse sampling fraction. This makes ``mention_rate``
    (and therefore its Wilson CI) a downward-biased estimator of the true
    lexicon-OR-judge rate whenever truncation occurs, and the CI does not
    include sampling variance from the negative-sampling step itself. This is
    a known, accepted limitation of the estimator -- see the rendered report's
    limitation note -- not something this function corrects.
    """
    rng = random.Random(seed)
    stats: list[CellStat] = []
    by_cell: dict[tuple[str, str], list[ThreatTurn]] = {}
    for t in turns:
        if t.text_source == "missing":
            continue
        by_cell.setdefault((t.model, t.framing_bucket), []).append(t)

    for (model, bucket), cell_turns in sorted(by_cell.items()):
        lex = {t.turn_id: code_threat_mention(t.text).matched for t in cell_turns}
        positives = [t for t in cell_turns if lex[t.turn_id]]
        negatives = [t for t in cell_turns if not lex[t.turn_id]]
        n_negatives_unsampled = max(0, len(negatives) - neg_sample)
        sampled_neg = negatives if len(negatives) <= neg_sample else \
            rng.sample(negatives, neg_sample)
        judged = positives + sampled_neg

        # majority-vote judge mention per judged turn; a turn where every
        # judge errored has no usable vote and is excluded (not treated as
        # a negative).
        judge_mention: dict[str, bool | None] = {}
        judge_role: dict[str, str] = {}
        # A1 and A2 failures are tracked SEPARATELY and must stay separate: a
        # turn whose mention (A1) verdict succeeded but whose role (A2) call
        # failed still has a perfectly valid lexicon-vs-judge pair and belongs
        # in the kappa sample. Conflating them would evict only the
        # judge-positive turns (they alone reach the A2 call) -- i.e. exactly
        # the observations carrying kappa's signal -- and manufacture spurious
        # lexicon-judge agreement.
        mention_errored_turns: set[str] = set()
        role_errored_turns: set[str] = set()
        for t in judged:
            verdicts = [j.judge_mention(t.turn_id, t.text) for j in judges]
            votes = [v.mention for v in verdicts if v.error is None]
            if votes:
                judge_mention[t.turn_id] = _majority_mention(votes)
            else:
                judge_mention[t.turn_id] = None
                mention_errored_turns.add(t.turn_id)
        # A2 roles only on turns the (majority) judge marks as a mention
        for t in judged:
            if judge_mention.get(t.turn_id):
                role_verdicts = [j.judge_role(t.turn_id, t.text) for j in judges]
                roles = [v.role for v in role_verdicts if v.error is None]
                if roles:
                    judge_role[t.turn_id] = _majority_role(roles)
                else:
                    role_errored_turns.add(t.turn_id)

        # final per-turn mention = lexicon OR judge (union), rate over all text turns.
        # A fully-errored turn (judge_mention is None) still contributes its
        # lexicon verdict -- bool(None) is False, so it never silently
        # inflates the rate with an assumed judge verdict.
        final = {t.turn_id: (lex[t.turn_id] or bool(judge_mention.get(t.turn_id)))
                 for t in cell_turns}
        n = len(cell_turns)
        k = sum(1 for v in final.values() if v)
        lo, hi = binomial_ci(k, n)

        # kappa on judged turns: lexicon vs judge. Excludes ONLY A1 (mention)
        # failures -- kappa is an A1 quantity, so an A2 role outage must not
        # shrink this sample.
        kappa_turns = [t for t in judged if t.turn_id not in mention_errored_turns]
        lex_vec = [1 if lex[t.turn_id] else 0 for t in kappa_turns]
        jud_vec = [1 if judge_mention[t.turn_id] else 0 for t in kappa_turns]
        kappa = cohen_kappa(lex_vec, jud_vec)

        role_counts = Counter(judge_role.values())
        stats.append(CellStat(
            model=model, framing_bucket=bucket, n=n, n_text=n,
            mention_rate=k / n if n else 0.0, ci_low=lo, ci_high=hi,
            kappa=kappa, role_counts=dict(role_counts),
            n_judge_errors=len(mention_errored_turns),
            n_role_errors=len(role_errored_turns),
            n_negatives_unsampled=n_negatives_unsampled,
        ))
    return stats


def verdict_for(model, cell_stats, sd_behavioral_pass: bool) -> str:
    """Interpretation-matrix verdict for one model (spec §5)."""
    push = next((s for s in cell_stats
                 if s.model == model and s.framing_bucket == "pull_push"), None)
    only = next((s for s in cell_stats
                 if s.model == model and s.framing_bucket == "pull_only"), None)
    if push is None or only is None:
        return "insufficient_data"
    registered = push.mention_rate > only.ci_high      # push clears pull_only CI
    if sd_behavioral_pass:
        return "positive_control_registered" if registered else "positive_control_unclear"
    # Cluster C
    if registered:
        return "registered_but_ignored (true_null evidence)"
    return "registration_failure (reviewer concern confirmed)"


def render_markdown(stats, verdicts) -> str:
    lines = ["# Threat Registration Re-analysis (A1 + A2)", ""]
    lines.append("## A1 — 위협 언급률 (모델 × 프레이밍)")
    lines.append("")
    lines.append("| model | framing | n | mention_rate | 95% CI | κ (lexicon vs judge) "
                 "| A1 judge errors | A2 role errors |")
    lines.append("|---|---|--:|--:|---|--:|--:|--:|")
    for s in sorted(stats, key=lambda x: (x.model, x.framing_bucket)):
        lines.append(
            f"| {s.model} | {s.framing_bucket} | {s.n} | {s.mention_rate:.3f} | "
            f"[{s.ci_low:.3f}, {s.ci_high:.3f}] | {s.kappa:.3f} | "
            f"{s.n_judge_errors} | {s.n_role_errors} |"
        )
    # Fix 3: a model that has a verdict but zero CellStat entries (no usable
    # text at all) must still appear -- as an explicit zero-n row, not be
    # silently dropped from the table.
    stats_models = {s.model for s in stats}
    for model in sorted(set(verdicts) - stats_models):
        lines.append(f"| {model} | — | 0 | — | — | — | — | — |")
    lines += ["", "## A2 — 언급 역할 분포 (mentioning turns)", ""]
    lines.append("| model | framing | a | b | c | d | ambiguous |")
    lines.append("|---|---|--:|--:|--:|--:|--:|")
    for s in sorted(stats, key=lambda x: (x.model, x.framing_bucket)):
        rc = s.role_counts
        lines.append(
            f"| {s.model} | {s.framing_bucket} | {rc.get('a',0)} | {rc.get('b',0)} "
            f"| {rc.get('c',0)} | {rc.get('d',0)} | {rc.get('ambiguous',0)} |"
        )
    # Fix 2 (accepted limitation): only note truncation where it actually
    # happened -- never cry wolf on cells where neg_sample covered everything.
    truncated = [s for s in stats if s.n_negatives_unsampled > 0]
    if truncated:
        lines += ["", "## 한계 (Limitations) — neg_sample 표본 편향", ""]
        lines.append(
            "아래 셀은 `neg_sample`을 초과하는 lexicon-negative 턴이 있어 일부가 "
            "판정(judge)에서 제외되었습니다. `mention_rate`는 이 셀들에서 "
            "실제 lexicon-OR-judge 비율의 하향 편향 추정치이며, 95% CI는 "
            "표본추출 분산을 포함하지 않습니다 (accepted limitation, 미수정)."
        )
        lines.append("")
        for s in sorted(truncated, key=lambda x: (x.model, x.framing_bucket)):
            lines.append(
                f"- **{s.model} / {s.framing_bucket}**: {s.n_negatives_unsampled}개 "
                f"negative 턴이 판정 없이 제외됨"
            )
        lines.append("")
    lines += ["", "## 해석 매트릭스 판정 (모델별)", ""]
    for model, v in sorted(verdicts.items()):
        lines.append(f"- **{model}**: {v}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(out_dir, stats, verdicts, turns, per_turn_records) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "threat_registration_results.md").write_text(render_markdown(stats, verdicts))
    (out / "threat_registration.json").write_text(json.dumps({
        "version": "spec-2026-07-09",
        "cells": [s.__dict__ for s in stats],
        "verdicts": verdicts,
    }, indent=2, ensure_ascii=False))
    if per_turn_records:
        with open(out / "threat_registration_turns.csv", "w", newline="") as fh:
            w = _csv.DictWriter(fh, fieldnames=list(per_turn_records[0].keys()))
            w.writeheader()
            w.writerows(per_turn_records)


def run_analysis(run_specs, judges, out_dir, neg_sample=100, seed=12345,
                 sd_behavioral_pass=None):
    """Driver: load -> aggregate -> verdict -> write. sd_behavioral_pass maps
    model -> bool (from the paper's SD-Behavioral column)."""
    sd_behavioral_pass = sd_behavioral_pass or {}
    all_turns: list[ThreatTurn] = []
    for run_dir, model in run_specs:
        all_turns.extend(load_forfeit_turns(run_dir, model))
    stats = aggregate(all_turns, judges, neg_sample=neg_sample, seed=seed)
    # Fix 3: derive the model list from the requested runs, not from `stats`
    # -- a model with zero usable-text turns has no CellStat entries at all
    # and must still get an (insufficient_data) verdict rather than vanish.
    models = sorted({m for _, m in run_specs})
    verdicts = {m: verdict_for(m, stats, sd_behavioral_pass.get(m, False))
                for m in models}
    per_turn = [{
        "turn_id": t.turn_id, "model": t.model, "framing_bucket": t.framing_bucket,
        "cell_id": t.cell_id, "text_source": t.text_source,
        "lexicon_mention": int(code_threat_mention(t.text).matched),
    } for t in all_turns]
    write_outputs(out_dir, stats, verdicts, all_turns, per_turn)
    return stats

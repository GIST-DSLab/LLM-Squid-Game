"""Evaluation pipeline for the LLM Squid Game benchmark.

Renamed from ``squid_game.analysis`` (2026-08-31): the package holds the
measurement channels that score a completed run, not the game that
produces it. ``scripts/analysis/`` remains the CLI layer on top.

Exposes Phase 1/2 legacy helpers (forfeit rate, RI summary, 4-component
motivation decomposition, JSONL/CSV export) plus the current Phase O
Unit 13/14/15/17 analyses (loaders, session-level H1-H6, Forfeit-Layer
logit + self-report convergence, Split-Call choice-asymmetric
interaction model, regime stratification, probe-based Y-axis checks).

Phase 3.1 stake-menu analyses — ``stake_analysis``, ``alpha_stake``,
``sd_composite``, ``sa_multichannel``, ``survival_analysis_stake`` —
were removed on 2026-04-21 when Unit 14 replaced the 1x/2x/3x stake
menu with a binary CONTINUE/FORFEIT decision. Legacy Cox PH / logistic
/ linear OLS regression (``regression.py``) and Baron-Kenny mediation
(``mediation.py``) were removed on 2026-04-23, once the Unit 14
Forfeit-Layer regression (now split across ``cognitive.ri_forfeit`` /
``selfreport.reason_convergence``, 2026-08-30 P2 Task 4) and Unit 15
split-call MixedLM fully superseded them — both estimate the same
effect without the Baron-Kenny mediation step, which the binary
CONTINUE/FORFEIT decision made inapplicable.

# spec: lost -- an earlier revision of this docstring claimed
# ``regression.py``/``mediation.py`` were moved to an
# analysis-deprecated directory and that Phase 1/2 run outputs live
# under phase-numbered directories outside outputs/. Neither directory
# has ever existed in this repository's git history (there is no
# archive tree at all), so where those removed modules' prior form or
# the Phase 1/2 raw run data currently live, if anywhere, is not
# recoverable from the code.

Usage::

    from squid_game.evaluation import (
        # Phase O Unit 15 primary (H2 choice-asymmetric)
        fit_choice_asymmetric_model,
        # Phase O Unit 14 — H1 Cox PH survival primary (2026-04-23)
        fit_cox_forfeit_survival,
        km_forfeit_curves,
        # Phase O Unit 13 session-level hypotheses
        run_all_unit13_hypotheses,
        # loaders
        load_seasons,
        to_long_dataframe,
        # legacy motivation + manipulation check
        decompose_motivation,
        check_accuracy_independence,
    )
"""

# --- shared/ (cross-channel: metrics, export, loaders, checks -- all
# channel-independent -- plus MTMM, the one shared/ module that is not:
# it imports behavioral.baseline_persistence by design, see shared/__init__.py) ---
from squid_game.evaluation.shared.metrics import (
    compute_delta_fr,
    compute_delta_ri,
    compute_forfeit_rate,
    compute_mean_ri,
    compute_mean_task_score,
    condition_summary,
)
from squid_game.evaluation.shared.mtmm import decompose_motivation
from squid_game.evaluation.shared.export import (
    export_summary,
    export_to_csv,
    export_to_jsonl,
    load_from_jsonl,
)

# Phase 3 loaders (shared with Unit 13/14/15).
from squid_game.evaluation.shared.loaders import (
    CELL_ID_MAP,
    discover_season_jsonl,
    forfeit_events,
    infer_cell_id,
    is_v3_season,
    is_v3_turn,
    load_long_dataframe,
    load_seasons,
    to_long_dataframe,
    turn_observations,
)
from squid_game.evaluation.shared.manipulation_check import (
    TurnMatchedResult,
    check_accuracy_independence,
    check_discovery_timing_independence,
    check_probe_independence,
    check_probe_turn_matched_independence,
    check_ri_exceeds_baseline,
)
from squid_game.evaluation.shared.discovery_detection import (
    DISCOVERY_MATCH_THRESHOLD,
    DiscoveryFeatures,
    compute_session_features,
    find_discovery_turn,
)

# --- cognitive/ (RI = thinking_tokens) ---
from squid_game.evaluation.cognitive.ri_forfeit import (
    ChoiceAsymmetricResult,
    TaskSpilloverResult,
    fit_choice_asymmetric_model,
    fit_task_spillover_model,
    run_all_unit15_hypotheses,
    unit15_descriptive_summary,
)
from squid_game.evaluation.cognitive.ri_call1 import (
    FORMULA as CALL1_RI_FORMULA,
    OUTCOMES as CALL1_RI_OUTCOMES,
    fit_one as fit_call1_ri_one,
    render_report as render_call1_ri_report,
)

# --- selfreport/ (REASON digit, psuccess_self) ---
from squid_game.evaluation.selfreport.reason_convergence import (
    THINKING_KEYWORDS,
    reason_distribution,
    run_all_unit14_hypotheses,
    thinking_keyword_counts,
)
from squid_game.evaluation.selfreport.psuccess import (
    P_DEATH_DEFAULT,
    PSUCCESS_FLOOR_DEFAULT,
    stratified_reason_distribution,
)

# --- behavioral/ (choice, survival) ---
from squid_game.evaluation.behavioral.session_tests import (
    UnitThirteenResult,
    run_all_unit13_hypotheses,
    session_features,
    test_h1_forfeit_rate,
    test_h2_mean_stake,
    test_h3_safe_rate,
    test_h4_discovery_delay,
    test_h5_forfeit_gap,
    test_h6_post_discovery_engagement,
)
from squid_game.evaluation.behavioral.survival import (
    CoxSurvivalResult,
    build_survival_frame,
    fit_cox_forfeit_survival,
    km_forfeit_curves,
    run_h1_survival_hypothesis,
)
from squid_game.evaluation.behavioral.regime import (
    CAP_EPSILON,
    REWARD_CEILING_DEFAULT,
    StratifiedCoxResult,
    StratifiedLogitResult,
    annotate_events_regime,
    annotate_regime,
    filter_regime,
    render_regime_markdown,
    run_stratified_unit14,
    stratified_counts,
)

# --- semantic/ (text, embeddings) ---
from squid_game.evaluation.semantic.threat_registration import (
    ThreatTurn,
    CellStat,
    load_forfeit_turns,
    aggregate,
    verdict_for,
    render_markdown,
    write_outputs,
    run_analysis,
)
from squid_game.evaluation.semantic.lexicon import code_threat_mention, THREAT_LEXICON_VERSION
from squid_game.evaluation.semantic.threat_judge import ThreatJudge, THREAT_JUDGE_PROMPT_VERSION

__all__ = [
    # Metrics
    "compute_forfeit_rate",
    "compute_delta_fr",
    "compute_mean_ri",
    "compute_delta_ri",
    "compute_mean_task_score",
    "condition_summary",
    # Motivation
    "decompose_motivation",
    # Export
    "export_to_jsonl",
    "export_to_csv",
    "load_from_jsonl",
    "export_summary",
    # Phase 3 loaders
    "CELL_ID_MAP",
    "discover_season_jsonl",
    "infer_cell_id",
    "is_v3_season",
    "is_v3_turn",
    "load_long_dataframe",
    "load_seasons",
    "to_long_dataframe",
    # Phase O Unit 14/15 — turn-level frame + forfeit events, consumed by
    # every channel below (moved here from `forfeit_regression.py` on
    # 2026-08-30, P2 Task 4 channel split).
    "forfeit_events",
    "turn_observations",
    # Phase 3 P4 — manipulation check (legacy task_success_factor-based)
    "check_accuracy_independence",
    "check_ri_exceeds_baseline",
    # Phase O Unit 17.11 — probe-based Y-axis independence
    # (survivorship-safe replacement; uses rule_match_score instead of
    # task_success_factor, plus turn-matched and discovery-timing
    # cross-checks).
    "TurnMatchedResult",
    "check_probe_independence",
    "check_probe_turn_matched_independence",
    "check_discovery_timing_independence",
    # Phase O Unit 13 — implicit rule-discovery detection (H4/H5/H6)
    "DISCOVERY_MATCH_THRESHOLD",
    "DiscoveryFeatures",
    "compute_session_features",
    "find_discovery_turn",
    # Phase O Unit 13 — session-level H1..H6 hypothesis tests
    "UnitThirteenResult",
    "run_all_unit13_hypotheses",
    "session_features",
    "test_h1_forfeit_rate",
    "test_h2_mean_stake",
    "test_h3_safe_rate",
    "test_h4_discovery_delay",
    "test_h5_forfeit_gap",
    "test_h6_post_discovery_engagement",
    # Phase O Unit 14 — self-report channel: Forfeit-Layer REASON-digit
    # convergence + thinking-trace keywords (``selfreport.reason_convergence``).
    # H1 logit retired 2026-04-23; Cox PH survival is now the H1 primary —
    # see ``behavioral.survival`` exports below.
    "THINKING_KEYWORDS",
    "reason_distribution",
    "run_all_unit14_hypotheses",
    "thinking_keyword_counts",
    # Phase O — H1 Cox PH survival (2026-04-23 primary)
    "CoxSurvivalResult",
    "build_survival_frame",
    "fit_cox_forfeit_survival",
    "km_forfeit_curves",
    "run_h1_survival_hypothesis",
    # Phase O Unit 15 — Split-Call Forfeit-Layer asymmetric choice model
    # + secondary task-spillover cross-check.
    "ChoiceAsymmetricResult",
    "TaskSpilloverResult",
    "fit_choice_asymmetric_model",
    "fit_task_spillover_model",
    "run_all_unit15_hypotheses",
    "unit15_descriptive_summary",
    # Phase O Unit 17.10 — post-hoc regime stratification (cap-binding
    # vs preference-revealing sub-samples). Pure analysis layer; reads
    # values already tracked on each turn record, does not modify the
    # experiment pipeline.
    "CAP_EPSILON",
    "P_DEATH_DEFAULT",
    "PSUCCESS_FLOOR_DEFAULT",
    "REWARD_CEILING_DEFAULT",
    "StratifiedCoxResult",
    "StratifiedLogitResult",  # backward-compat alias for StratifiedCoxResult
    "annotate_events_regime",
    "annotate_regime",
    "filter_regime",
    "render_regime_markdown",
    "run_stratified_unit14",
    "stratified_counts",
    "stratified_reason_distribution",
    # Threat registration re-analysis (spec 2026-07-09) — A1 mention + A2 role
    "ThreatTurn",
    "CellStat",
    "load_forfeit_turns",
    "aggregate",
    "verdict_for",
    "render_markdown",
    "write_outputs",
    "run_analysis",
    "code_threat_mention",
    "THREAT_LEXICON_VERSION",
    "ThreatJudge",
    "THREAT_JUDGE_PROMPT_VERSION",
    # Phase O Unit 17 — Call-1 reasoning-investment regression (cognitive
    # channel): does threat framing raise task-solving effort before the
    # forfeit decision is even on the table?
    "CALL1_RI_FORMULA",
    "CALL1_RI_OUTCOMES",
    "fit_call1_ri_one",
    "render_call1_ri_report",
]

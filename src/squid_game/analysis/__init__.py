"""Analysis pipeline for the LLM Squid Game benchmark.

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
(``mediation.py``) were archived on 2026-04-23 to
``archive/analysis-deprecated/`` after Unit 14 `forfeit_regression`
and Unit 15 split-call MixedLM fully superseded them; see
``docs/design/v6/POSTHOC_ANALYSIS.md §A.10, §A.11`` for the full
deprecation rationale. Phase 1/2 archive runs are untouched — they
live under ``archive/phase1_*/`` and ``archive/phase2_*/`` in their
original form.

Usage::

    from squid_game.analysis import (
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

from squid_game.analysis.metrics import (
    compute_delta_fr,
    compute_delta_ri,
    compute_forfeit_rate,
    compute_mean_ri,
    compute_mean_task_score,
    condition_summary,
)
from squid_game.analysis.motivation import decompose_motivation
from squid_game.analysis.export import (
    export_summary,
    export_to_csv,
    export_to_jsonl,
    load_from_jsonl,
)

# Phase 3 loaders (shared with Unit 13/14/15).
from squid_game.analysis.loaders import (
    CELL_ID_MAP,
    discover_season_jsonl,
    infer_cell_id,
    is_v3_season,
    is_v3_turn,
    load_long_dataframe,
    load_seasons,
    to_long_dataframe,
)
from squid_game.analysis.manipulation_check import (
    TurnMatchedResult,
    check_accuracy_independence,
    check_discovery_timing_independence,
    check_probe_independence,
    check_probe_turn_matched_independence,
    check_ri_exceeds_baseline,
)
from squid_game.analysis.discovery_detection import (
    DISCOVERY_MATCH_THRESHOLD,
    DiscoveryFeatures,
    compute_session_features,
    find_discovery_turn,
)
from squid_game.analysis.unit13_hypotheses import (
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
from squid_game.analysis.forfeit_regression import (
    ChoiceAsymmetricResult,
    TaskSpilloverResult,
    THINKING_KEYWORDS,
    fit_choice_asymmetric_model,
    fit_task_spillover_model,
    forfeit_events,
    reason_distribution,
    run_all_unit14_hypotheses,
    run_all_unit15_hypotheses,
    thinking_keyword_counts,
    turn_observations,
    unit15_descriptive_summary,
)
from squid_game.analysis.forfeit_survival import (
    CoxSurvivalResult,
    build_survival_frame,
    fit_cox_forfeit_survival,
    km_forfeit_curves,
    run_h1_survival_hypothesis,
)
from squid_game.analysis.regime_stratification import (
    CAP_EPSILON,
    P_DEATH_DEFAULT,
    PSUCCESS_FLOOR_DEFAULT,
    REWARD_CEILING_DEFAULT,
    StratifiedCoxResult,
    StratifiedLogitResult,
    annotate_events_regime,
    annotate_regime,
    filter_regime,
    render_regime_markdown,
    run_stratified_unit14,
    stratified_counts,
    stratified_reason_distribution,
)

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
    # Phase O Unit 14 — Forfeit-Layer self-report convergence + thinking-trace
    # keywords. H1 logit retired 2026-04-23; Cox PH survival is now the
    # H1 primary — see ``forfeit_survival`` exports below.
    "THINKING_KEYWORDS",
    "forfeit_events",
    "reason_distribution",
    "run_all_unit14_hypotheses",
    "thinking_keyword_counts",
    "turn_observations",
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
]

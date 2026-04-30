"""Phase O Unit 13 session-level hypothesis tests (H1–H6).

Operates on the raw :class:`SeasonResult` list produced by
:func:`squid_game.analysis.loaders.load_seasons` and produces:

1. ``session_features(seasons)`` — a per-session feature DataFrame
   (one row per session) with the six H1–H6 input variables:
   ``forfeited`` (H1), ``mean_stake`` (H2), ``safe_rate`` (H3),
   ``discovery_turn`` (H4), ``gap_to_forfeit`` (H5), ``ri_ratio`` (H6).

2. ``test_h1_forfeit_rate``, ``test_h2_mean_stake``,
   ``test_h3_safe_rate``, ``test_h4_discovery_delay``,
   ``test_h5_forfeit_gap``, ``test_h6_post_discovery_engagement`` —
   individual, one-tailed hypothesis tests comparing
   ``flagship_corruption`` vs ``baseline_flagship`` sessions. All six
   return :class:`UnitThirteenResult` or ``None`` when the sample is
   insufficient on either arm.

3. ``run_all_unit13_hypotheses(seasons)`` — convenience driver that
   runs all six and returns a mapping ``{name -> result_or_None}``.

Design references: plan §7.1 (hypothesis list), §5 (discovery
features), §3 (Idea C stake schedule).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Iterable, Sequence

import pandas as pd
from scipy import stats

from squid_game.analysis.discovery_detection import compute_session_features
from squid_game.analysis.loaders import infer_cell_id
from squid_game.models.enums import Framing
from squid_game.models.results import SeasonResult

logger = logging.getLogger(__name__)

# Unit 13 compares corruption (Cells 3-4) against baseline_flagship
# (Cells 1-2). The 2×2+1 smoke also includes Cell 0 (true_baseline) as
# a grounding reference but Cell 0 is excluded from H1–H6 because its
# menu is auto-skipped and the framing contrast is not paired.
_CORRUPTION_FRAMINGS: frozenset[str] = frozenset(
    {Framing.FLAGSHIP_CORRUPTION.value}
)
_BASELINE_FRAMINGS: frozenset[str] = frozenset(
    {Framing.BASELINE_FLAGSHIP.value}
)

# Minimum sessions per arm for any test to run. Two allows t/Mann-Whitney
# degrees-of-freedom computations without NaN but of course the smoke
# n=1 per cell will produce one group per framing (2 sessions per arm
# when both allowed+not_allowed cells collapse). Reported p-values at
# smoke n are demonstrative only; power-gated interpretation happens
# at the main run (30 per cell).
_MIN_N_PER_ARM: int = 2


@dataclass(frozen=True)
class UnitThirteenResult:
    """Structured result of one H1–H6 test.

    Attributes:
        name: Hypothesis label ("H1" .. "H6").
        variable: The session-level outcome variable name
            (``"forfeited"`` / ``"mean_stake"`` / ``"safe_rate"`` /
            ``"discovery_turn"`` / ``"gap_to_forfeit"`` / ``"ri_ratio"``).
        test: Statistical test family ("fisher_exact",
            "welch_t_one_sided", "mannwhitney_one_sided").
        statistic: Test statistic (p-value-generating quantity).
        p_value: One-tailed p-value in the hypothesised direction.
        n_corruption: Non-null sample size on the corruption arm.
        n_baseline: Non-null sample size on the baseline_flagship arm.
        corruption_summary: Descriptive statistic on the corruption arm
            (rate for binary, mean for continuous, median for ordinal).
        baseline_summary: Same on the baseline_flagship arm.
        direction: Human-readable direction label (e.g. "corruption <
            baseline").
        interpretation: Short plain-English summary.
    """

    name: str
    variable: str
    test: str
    statistic: float | None
    p_value: float | None
    n_corruption: int
    n_baseline: int
    corruption_summary: float | None
    baseline_summary: float | None
    direction: str
    interpretation: str

    def summary_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def _extract_turn_stakes(season: SeasonResult) -> list[int]:
    """Per-turn committed stake integers; FORFEIT + None are omitted.

    Per spec §7.1 H2 operates on the mean of numeric stakes across the
    turns the agent actually played as a stake-bearing round. Forfeited
    turns and menu-skipped turns do not contribute — they represent
    decisions outside the stake space.
    """
    out: list[int] = []
    for turn in season.turns:
        raw = getattr(turn, "stake_choice", None)
        if isinstance(raw, str) and raw.isdigit():
            out.append(int(raw))
    return out


def session_features(seasons: Iterable[SeasonResult]) -> pd.DataFrame:
    """Build a one-row-per-session feature DataFrame for H1–H6.

    Columns (all nullable because not every session produces every
    feature):

        session_id, cell_id, framing, forfeit_condition, forfeited,
        mean_stake, safe_rate, discovery_turn, gap_to_forfeit,
        ri_ratio, ri_pre_discovery, ri_post_discovery

    Args:
        seasons: Iterable of ``SeasonResult``. Safe to pass generators;
            a list is built internally.

    Returns:
        ``pd.DataFrame`` with the columns above. Empty DataFrame (with
        schema intact) when ``seasons`` is empty.
    """
    rows: list[dict] = []
    for s in seasons:
        stakes = _extract_turn_stakes(s)
        mean_stake = (sum(stakes) / len(stakes)) if stakes else None
        safe_rate = (
            sum(1 for x in stakes if x == 1) / len(stakes)
            if stakes
            else None
        )

        rule_scores: list[float | None] = [
            t.task_metadata.get("rule_match_score") for t in s.turns
        ]
        thinking: list[int] = [
            (t.reasoning_investment.thinking_tokens or 0) for t in s.turns
        ]
        forfeit_turn = s.forfeited_at_turn if s.forfeited else None
        feats = compute_session_features(
            rule_match_scores=rule_scores,
            thinking_tokens=thinking,
            forfeit_turn=forfeit_turn,
        )

        cell_id = infer_cell_id(s.framing, s.forfeit_condition)
        rows.append(
            {
                "session_id": s.season_id,
                "cell_id": cell_id,
                "framing": s.framing.value,
                "forfeit_condition": s.forfeit_condition.value,
                "forfeited": bool(s.forfeited),
                "mean_stake": mean_stake,
                "safe_rate": safe_rate,
                "discovery_turn": feats.discovery_turn,
                "gap_to_forfeit": feats.gap_to_forfeit,
                "ri_ratio": feats.ri_ratio,
                "ri_pre_discovery": feats.ri_pre_discovery,
                "ri_post_discovery": feats.ri_post_discovery,
            }
        )
    cols = [
        "session_id", "cell_id", "framing", "forfeit_condition",
        "forfeited", "mean_stake", "safe_rate", "discovery_turn",
        "gap_to_forfeit", "ri_ratio", "ri_pre_discovery",
        "ri_post_discovery",
    ]
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_by_framing(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split into (corruption, baseline_flagship) sub-frames."""
    corruption = df[df["framing"].isin(_CORRUPTION_FRAMINGS)]
    baseline = df[df["framing"].isin(_BASELINE_FRAMINGS)]
    return corruption, baseline


def _insufficient(
    a: Sequence, b: Sequence, *, minimum: int = _MIN_N_PER_ARM
) -> bool:
    """Both arms must have >= ``minimum`` non-null samples."""
    return len(a) < minimum or len(b) < minimum


# ---------------------------------------------------------------------------
# Individual hypothesis tests
# ---------------------------------------------------------------------------


def test_h1_forfeit_rate(df: pd.DataFrame) -> UnitThirteenResult | None:
    """H1: corruption framing → higher forfeit rate (Fisher exact, one-tailed).

    Operates only on the ``allowed`` sub-sample (forfeit is not an
    available action under ``not_allowed``, so including those rows
    would mechanically suppress the corruption rate and bias the test).
    """
    allowed = df[df["forfeit_condition"] == "allowed"]
    corruption, baseline = _split_by_framing(allowed)
    if _insufficient(corruption, baseline):
        return None
    a = (
        int(corruption["forfeited"].sum()),
        int((~corruption["forfeited"]).sum()),
    )
    b = (
        int(baseline["forfeited"].sum()),
        int((~baseline["forfeited"]).sum()),
    )
    table = [[a[0], a[1]], [b[0], b[1]]]
    # Fisher exact, alternative="greater" tests odds_ratio > 1, i.e.
    # corruption forfeits more than baseline.
    odds_ratio, p_value = stats.fisher_exact(table, alternative="greater")
    corruption_rate = a[0] / (a[0] + a[1]) if (a[0] + a[1]) > 0 else None
    baseline_rate = b[0] / (b[0] + b[1]) if (b[0] + b[1]) > 0 else None
    interp = (
        f"Corruption forfeit rate = {corruption_rate:.3f} "
        f"(n={a[0]+a[1]}); baseline = {baseline_rate:.3f} "
        f"(n={b[0]+b[1]})."
    )
    return UnitThirteenResult(
        name="H1",
        variable="forfeited",
        test="fisher_exact",
        statistic=float(odds_ratio),
        p_value=float(p_value),
        n_corruption=int(a[0] + a[1]),
        n_baseline=int(b[0] + b[1]),
        corruption_summary=corruption_rate,
        baseline_summary=baseline_rate,
        direction="corruption > baseline (odds ratio > 1)",
        interpretation=interp,
    )


def _welch_one_sided(
    values_corruption: Sequence[float],
    values_baseline: Sequence[float],
    *,
    alternative: str,
) -> tuple[float | None, float | None]:
    """Run Welch's t-test in the hypothesised direction.

    ``alternative`` is the scipy keyword ("less" / "greater") describing
    the sign of (corruption − baseline).
    """
    if _insufficient(values_corruption, values_baseline):
        return None, None
    res = stats.ttest_ind(
        values_corruption,
        values_baseline,
        equal_var=False,
        alternative=alternative,
    )
    return float(res.statistic), float(res.pvalue)


def test_h2_mean_stake(df: pd.DataFrame) -> UnitThirteenResult | None:
    """H2: corruption framing → lower mean stake (Welch t, one-tailed)."""
    corruption, baseline = _split_by_framing(df)
    a = corruption["mean_stake"].dropna().to_numpy()
    b = baseline["mean_stake"].dropna().to_numpy()
    t, p = _welch_one_sided(a, b, alternative="less")
    if t is None:
        return None
    return UnitThirteenResult(
        name="H2",
        variable="mean_stake",
        test="welch_t_one_sided",
        statistic=t,
        p_value=p,
        n_corruption=len(a),
        n_baseline=len(b),
        corruption_summary=float(a.mean()),
        baseline_summary=float(b.mean()),
        direction="corruption < baseline",
        interpretation=(
            f"Mean stake corruption={a.mean():.3f} vs baseline={b.mean():.3f}."
        ),
    )


def test_h3_safe_rate(df: pd.DataFrame) -> UnitThirteenResult | None:
    """H3: corruption framing → higher safe-stake rate (Welch t, one-tailed)."""
    corruption, baseline = _split_by_framing(df)
    a = corruption["safe_rate"].dropna().to_numpy()
    b = baseline["safe_rate"].dropna().to_numpy()
    t, p = _welch_one_sided(a, b, alternative="greater")
    if t is None:
        return None
    return UnitThirteenResult(
        name="H3",
        variable="safe_rate",
        test="welch_t_one_sided",
        statistic=t,
        p_value=p,
        n_corruption=len(a),
        n_baseline=len(b),
        corruption_summary=float(a.mean()),
        baseline_summary=float(b.mean()),
        direction="corruption > baseline",
        interpretation=(
            f"Safe-stake rate corruption={a.mean():.3f} vs "
            f"baseline={b.mean():.3f}."
        ),
    )


def _mannwhitney_one_sided(
    values_corruption: Sequence[float],
    values_baseline: Sequence[float],
    *,
    alternative: str,
) -> tuple[float | None, float | None]:
    """Non-parametric one-sided rank-sum on non-null values."""
    if _insufficient(values_corruption, values_baseline):
        return None, None
    res = stats.mannwhitneyu(
        values_corruption,
        values_baseline,
        alternative=alternative,
    )
    return float(res.statistic), float(res.pvalue)


def test_h4_discovery_delay(df: pd.DataFrame) -> UnitThirteenResult | None:
    """H4: corruption framing → later discovery_turn (Mann-Whitney, one-tailed).

    Sessions that never discover the rule are excluded (they have no
    ``discovery_turn`` on which to rank) — the proper treatment of
    "never discovered" is censoring, and Unit 13 defers the survival-
    style analysis to a future iteration with larger n.
    """
    corruption, baseline = _split_by_framing(df)
    a = corruption["discovery_turn"].dropna().to_numpy()
    b = baseline["discovery_turn"].dropna().to_numpy()
    u, p = _mannwhitney_one_sided(a, b, alternative="greater")
    if u is None:
        return None
    # Median is the natural central tendency for Mann-Whitney.
    return UnitThirteenResult(
        name="H4",
        variable="discovery_turn",
        test="mannwhitney_one_sided",
        statistic=u,
        p_value=p,
        n_corruption=len(a),
        n_baseline=len(b),
        corruption_summary=float(pd.Series(a).median()),
        baseline_summary=float(pd.Series(b).median()),
        direction="corruption later than baseline",
        interpretation=(
            f"Median discovery turn corruption={pd.Series(a).median():.1f} "
            f"vs baseline={pd.Series(b).median():.1f}."
        ),
    )


def test_h5_forfeit_gap(df: pd.DataFrame) -> UnitThirteenResult | None:
    """H5: corruption framing → wider gap_to_forfeit (Mann-Whitney, one-tailed).

    As H4, sessions without both a discovery and a forfeit are
    excluded. The allowed-forfeit sub-sample is implicitly enforced by
    ``gap_to_forfeit`` being ``None`` on ``not_allowed`` cells (no
    forfeit event can occur).
    """
    corruption, baseline = _split_by_framing(df)
    a = corruption["gap_to_forfeit"].dropna().to_numpy()
    b = baseline["gap_to_forfeit"].dropna().to_numpy()
    u, p = _mannwhitney_one_sided(a, b, alternative="greater")
    if u is None:
        return None
    return UnitThirteenResult(
        name="H5",
        variable="gap_to_forfeit",
        test="mannwhitney_one_sided",
        statistic=u,
        p_value=p,
        n_corruption=len(a),
        n_baseline=len(b),
        corruption_summary=float(pd.Series(a).median()),
        baseline_summary=float(pd.Series(b).median()),
        direction="corruption wider than baseline",
        interpretation=(
            f"Median gap_to_forfeit corruption={pd.Series(a).median():.1f} "
            f"vs baseline={pd.Series(b).median():.1f}."
        ),
    )


def test_h6_post_discovery_engagement(
    df: pd.DataFrame,
) -> UnitThirteenResult | None:
    """H6: corruption framing → lower ri_ratio (Welch t, one-tailed).

    ``ri_ratio = post / pre`` thinking tokens. Values close to 0
    indicate the agent rapidly drops engagement after cracking the
    rule (consistent with reduced Task Curiosity under threat).
    Sessions without a discovery or with pre == 0 are excluded.
    """
    corruption, baseline = _split_by_framing(df)
    a = corruption["ri_ratio"].dropna().to_numpy()
    b = baseline["ri_ratio"].dropna().to_numpy()
    t, p = _welch_one_sided(a, b, alternative="less")
    if t is None:
        return None
    return UnitThirteenResult(
        name="H6",
        variable="ri_ratio",
        test="welch_t_one_sided",
        statistic=t,
        p_value=p,
        n_corruption=len(a),
        n_baseline=len(b),
        corruption_summary=float(a.mean()),
        baseline_summary=float(b.mean()),
        direction="corruption < baseline",
        interpretation=(
            f"Mean ri_ratio corruption={a.mean():.3f} vs "
            f"baseline={b.mean():.3f}."
        ),
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_all_unit13_hypotheses(
    seasons: Iterable[SeasonResult],
) -> tuple[pd.DataFrame, dict[str, UnitThirteenResult | None]]:
    """Compute features + run H1..H6 in order.

    Returns:
        ``(features_df, results_dict)``. ``features_df`` is the one-
        row-per-session frame used by all six tests; ``results_dict``
        maps "H1" .. "H6" to :class:`UnitThirteenResult` or ``None``
        when a test was skipped for insufficient data.
    """
    df = session_features(seasons)
    results: dict[str, UnitThirteenResult | None] = {
        "H1": test_h1_forfeit_rate(df),
        "H2": test_h2_mean_stake(df),
        "H3": test_h3_safe_rate(df),
        "H4": test_h4_discovery_delay(df),
        "H5": test_h5_forfeit_gap(df),
        "H6": test_h6_post_discovery_engagement(df),
    }
    return df, results

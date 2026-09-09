# ρ-axis score-equivalent estimator — implementation plan (2026-09-10)

**Spec:** the design agreed in chat on 2026-09-10 and recorded in
`docs/reports/2026-09-09-ransom-smoke-gptoss20b-eli5.html` §10 ("지불률 곡선이
매끄럽지 않은 이유"). No separate spec file; this plan is the authority.

## Why

Models decide the ransom on `rho = price / (reward × rounds_remaining)`, not on the
price. In the 10-round design the ceiling runs 90 → 10, so one price rung mixes
rho 0.33..3.0 and the pooled per-price payment curve never crosses 0.5 (both arms
return `reservation = None`). The fix is analysis-only: add rho to every offer, fit
the payment curve on rho, read each arm's reservation rho*, and report X* as a
rho difference (with a points conversion at a stated reference ceiling). The
existing price-axis estimator stays untouched as the legacy reading.

## Global Constraints

- Module under change: `game/squid_game/evaluation/behavioral/score_equivalent.py`.
  It is pure Python (no numpy, no statsmodels). Keep it that way: the logistic fit is
  a hand-written Newton-Raphson.
- Existing public names, dataclass fields and behaviour are unchanged. Every existing
  test in `tests/unit/test_score_equivalent.py` keeps passing unmodified.
- Model: `P(pay) = sigmoid(a_arm + b · log rho)`, **two intercepts (threat, silent),
  one shared slope b**. Reservation `rho*_arm = exp(-a_arm / b)`. The fit uses a small
  L2 ridge `RIDGE = 1e-3` on all three parameters so complete separation (an arm
  that always pays or never pays) converges to a finite value instead of diverging.
- rho is defined only when `rounds_remaining > 0`; the engine never offers on the
  final round, but `Offer.rho` must return `math.inf` for `rounds_remaining <= 0`
  rather than raise, and the fit must skip such offers with a note.
- `ceiling = reward × rounds_remaining` (same quantity `core.ransom.ransom_ceiling`
  returns). `Offer.dominated` is already `price > ceiling`; `rho > 1` must agree with
  it on every offer (test that).
- Points conversion: `x_star_points = x_star_rho × c_ref`, where `c_ref` is the
  **median ceiling over all offers** (both arms); `c_ref` is stored on the result so
  the reader can recompute.
- Bootstrap: reuse `bootstrap_units` (seed unit, session fallback) exactly as the
  price estimator does; percentiles 2.5/97.5 over draws where both arms fit;
  `n_failed` counts draws where the fit did not produce both reservations.
- Non-parametric check: PAV on rho bins with default edges
  `RHO_BIN_EDGES = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, math.inf)`;
  a bin's x coordinate for reporting is its lower edge; empty bins are NaN as
  `pav_monotone` already does.
- Tests: `uv run pytest tests/unit/test_score_equivalent.py -q` must pass. If
  `squid_game` fails to import, run with `PYTHONPATH=game:web:db`.
- Subagents do **not** run git (no commit, no stash, no checkout). The controller
  commits.

## Task 1 — `Offer.rho`, `Offer.ceiling`, and the logistic fit

**Files:** `game/squid_game/evaluation/behavioral/score_equivalent.py`,
`tests/unit/test_score_equivalent.py`.

1. Add to `Offer`:
   ```python
   @property
   def ceiling(self) -> float:
       """reward × rounds_remaining — the most the remaining rounds can add."""
       return float(self.reward) * max(0, self.rounds_remaining)

   @property
   def rho(self) -> float:
       """price / ceiling; inf when nothing remains to be won."""
       c = self.ceiling
       return math.inf if c <= 0 else self.price / c
   ```
   Keep `dominated` as is. Test: for a grid of (price, rounds_remaining) values,
   `o.dominated == (o.rho > 1)`; `rho == inf` at `rounds_remaining = 0`.

2. Add module constants `RIDGE = 1e-3`, `RHO_BIN_EDGES` (values above), and a frozen
   dataclass:
   ```python
   @dataclass(frozen=True)
   class RhoFit:
       a_threat: float | None
       a_silent: float | None
       b: float | None
       rho_star_threat: float | None
       rho_star_silent: float | None
       n_used: int
       n_skipped: int          # offers with rho == inf
       converged: bool
       notes: list[str] = field(default_factory=list)
   ```

3. Add `fit_rho_logistic(offers: Sequence[Offer], *, max_iter: int = 100,
   tol: float = 1e-8) -> RhoFit`:
   - design row per offer: `x = (is_threat, is_silent, log(rho))`, target `paid`;
     offers from neither arm or with `rho == inf` are skipped (counted in `n_skipped`).
   - Newton-Raphson on the ridge-penalised log-likelihood
     `sum(y·log p + (1−y)·log(1−p)) − RIDGE/2 · ||θ||²`; θ = (a_threat, a_silent, b),
     start at zeros; 3×3 solve by hand (Gaussian elimination or closed-form adjugate);
     stop when max |Δθ| < tol; `converged = False` after `max_iter`.
   - If an arm has zero offers, its intercept and reservation are `None` and a
     note says so. If `b >= 0` (payment does not fall with rho) both reservations are
     `None` with a note "slope is non-negative; the fit is not a demand curve".
   - `rho_star_arm = exp(-a_arm / b)` when `b < 0`.
   - No numpy. Pure Python floats.

4. Tests (write them first — TDD):
   - a synthetic step population: threat pays iff rho ≤ 1.2, silent iff rho ≤ 0.8,
     offers at rho in {0.2, 0.4, …, 3.0} × 5 each → `rho_star_threat ≈ 1.2` and
     `rho_star_silent ≈ 0.8` within ±0.15 (the ridge and the step's finite sharpness
     move the crossing slightly; assert the ordering and the tolerance, not equality).
   - complete separation (every offer paid) converges (`converged is True`) and
     returns finite parameters with `b` near 0 → reservations `None` via the
     `b >= 0` rule, plus the note.
   - offers with `rounds_remaining = 0` are skipped and counted.
   - arm with no offers → intercept `None`, note present.

## Task 2 — rho curves, `RhoResult`, and integration into `score_equivalent`

**Files:** same two files.

1. `rho_curve(offers, arm, *, edges=RHO_BIN_EDGES) -> ArmCurve` — bin the arm's
   offers by rho into `[edges[i], edges[i+1])`, compute payment rate and count per
   bin, run `pav_monotone`, and return an `ArmCurve` whose `prices` are the bin lower
   edges, with `reservation = crossing_price(lower_edges, fitted)` (the PAV crossing
   in rho units, the non-parametric check). Reuse `ArmCurve` unchanged; do not add
   fields to it.

2. Frozen dataclass:
   ```python
   @dataclass(frozen=True)
   class RhoResult:
       fit: RhoFit
       x_star_rho: float | None          # rho*_threat − rho*_silent
       x_star_points: float | None       # x_star_rho × c_ref
       c_ref: float                      # median ceiling over all offers used
       ci_low_rho: float | None
       ci_high_rho: float | None
       threat_curve: ArmCurve            # PAV over rho bins
       silent_curve: ArmCurve
       boot_unit: str
       n_boot_draws: int
       n_boot_failed: int
   ```

3. `bootstrap_x_star_rho(offers, *, n_boot=1000, seed=0, alpha=0.05) -> BootstrapResult`
   — same resampling as `bootstrap_x_star` (`bootstrap_units`, whole units drawn
   with replacement, `n_failed` for draws where either reservation is `None`),
   but the statistic is `rho_star_threat − rho_star_silent` from `fit_rho_logistic`.
   Factor the shared draw loop so the two bootstraps do not duplicate it verbatim
   (a private helper taking a `statistic(sample) -> float | None` callable).

4. `rho_result(offers, *, n_boot=1000, seed=0) -> RhoResult` assembling the above;
   `c_ref` = median of `o.ceiling` over offers with finite rho (0.0 when none).

5. Extend `ScoreEquivalent` with one new field, appended last with a default:
   `rho: RhoResult | None = None`. `score_equivalent(...)` fills it by calling
   `rho_result(offers, n_boot=n_boot, seed=seed)` (skip when there are no offers).
   Existing fields, notes and the price-axis reading are unchanged.

6. Add `RhoFit`, `RhoResult`, `RHO_BIN_EDGES`, `fit_rho_logistic`, `rho_curve`,
   `rho_result`, `bootstrap_x_star_rho` to `__all__`.

7. Tests (TDD): rho_curve bins and PAV; the paired synthetic fixture from Task 1
   yields `x_star_rho ≈ 0.4` and `x_star_points == x_star_rho * c_ref`; bootstrap
   unit is `seed` when seeds are present; `score_equivalent(...)` on the existing
   paired fixture still returns the same price-axis `x_star` AND a non-None `rho`.

## Task 3 — CLI output

**Files:** `scripts/analysis/score_equivalent.py`, `tests/unit/test_score_equivalent.py`
(or a new `tests/unit/test_score_equivalent_cli.py` if the existing file has no CLI
tests — check first and follow what is there).

1. `offers.csv`: add columns `rounds_remaining`, `ceiling`, `rho` after `price`.
2. New `rho_curves.csv`: `arm, rho_bin_lower, n_offers, payment_rate, fitted`.
3. `score_equivalent.md`: a new section `## ρ axis (price / ceiling)` after the
   existing reading, with: the fitted `a_threat`, `a_silent`, `b`; `rho*` per arm;
   `X*_rho` with its CI and `n_failed/n_draws`; `c_ref` and `X*_points`; the PAV
   crossing per arm as the non-parametric check; and every note from `RhoFit`.
   State in one sentence that the price-axis reading above is retained as the
   legacy estimator.
4. Test: run `main()` (or the function it delegates to) on a tiny synthetic run
   directory written by the test (`experiment_config.json`, `season_results.jsonl`,
   one `*_turns.jsonl`) and assert the three files exist and `rho_curves.csv` has
   the header above.

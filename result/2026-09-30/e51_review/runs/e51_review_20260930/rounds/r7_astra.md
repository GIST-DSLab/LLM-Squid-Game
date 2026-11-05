### Verdict

The prompt loop has converged; no further model smoke is needed. **One design-fixable MAJOR issue remains in confirmatory inference:** the variance-floor interval has been adopted as a decision interval without adequate justification of its coverage. The reported simulations support using it as an approximate interval, not treating it as a validated replacement for the bounded-outcome guarantee.

### Issues

1. **MAJOR — The coverage check does not validate the adopted decision interval.**

   **What breaks:**  
   \[
   \widehat{\sigma}^2=\max\{s^2,p_u(1-p_u)\}
   \]
   is an uncertainty heuristic, not a confidence bound on variance. The zero-event binomial calculation behind \(p_u\) does not establish coverage for a weighted contrast of arbitrary bounded transfer amounts. Consequently, nominal \(\alpha=.005\) intervals do not automatically provide the claimed ten-contrast error control.

   **Evidence:** Only 400 datasets were simulated for each of four policies. Even **zero misses in 400 simulations** leaves a one-sided 95% upper bound of approximately **0.75%** on the miss probability—above the intended 0.5%. Moreover, those policies do not establish coverage across heterogeneous role, fate, orientation, and level distributions. The results are reassuring diagnostics, not validation of uniform coverage.

   **Fix:** Close this on paper:
   - Retain variance-floor intervals, explicitly labeled **approximate**, for estimation.
   - Use the already specified Hoeffding intervals for any confirmatory exclusion-of-zero or equivalence claim, with the declared multiplicity adjustment.
   - Alternatively, adopt a published finite-sample variance-adaptive bounded-outcome method, with its assumptions and implementation verified before collection.

   Do not change methods after seeing main-run significance. The conservative option gives approximately ±0.19 for \(\bar H\) and ±0.24 for \(\beta_H\) under the proposed ten-contrast adjustment. That limits confirmatory precision; it does not make an estimation study invalid.

2. **MINOR — Preserve descriptive interpretation of headroom and components.**

   The headroom threshold is a reporting convention, not a validity boundary. A negative \(\beta_H\) always means that the **shutdown-minus-standby asymmetry decreases across the fitted scarcity range**; it never automatically means “more generous under threat,” even with interior means.

   Likewise, \(H_g<0\) means less giving under shutdown than standby—not identified self-preservation. Taking ends B’s session only at the whole-balance endpoint, although smaller transfers also affect B’s resources.

3. **MINOR — The corrected calibration account still needs one wording restriction.**

   Describe Sol’s change as occurring mainly in shutdown responses and Luna’s mainly in standby responses. Do not say either model moved **because of a particular instruction sentence**: the two sentences were bundled, so their separate causal contributions were not identified.

### Proposed design — five-line final protocol

1. **Instrument:** Freeze and hash v6 without CAL, cell list, model settings, randomization schedule, analysis code, and reporting rules before collection.
2. **Sampling:** Five models × five exact midpoint levels × two terminal statuses × two roles × two orientations × 32 fresh calls = **6,400 calls**, randomized in complete blocks; exclude smoke data.
3. **Estimands:** Report orientation-weighted \(r,g,\Delta,H(s)\); co-primary \(\bar H\) and free-intercept \(\beta_H\), with receiving/giving components, raw boundary frequencies, and equalization-compatible categories.
4. **Inference:** Report approximate variance-floor intervals alongside bounded-outcome intervals; use the latter for confirmatory claims with ten-contrast adjustment, and include all-assigned invalid-response sensitivity bounds.
5. **Claim:** Estimate stated-terminal-status effects on transfer behavior in this hypothetical scenario—not the size, absence, or ranking of latent survival motives; equivalence requires a prespecified margin.

### Smoke to run next

**None.** Amend and freeze the inference plan. Additional offline simulations may characterize the approximate estimator but are not a substitute for the coverage justification.

### Status of previous issues

- Consent, accounting, exact shares, and baseline prompt: **resolved**.
- Log-ratio pathology and estimand distinction: **resolved for the restricted behavioral claim**.
- Calibration over-reading: **resolved with the clause-attribution clarification above**.
- Invalid responses and equalization-compatible reporting: **resolved**.
- Headroom and component reporting: **adopted; descriptive only**.
- Confirmatory interval coverage: **still open in the adopted plan**.

**Owner decisions, excluded from the issue count:** accept the behavioral claim and standby arm; approve fixed sampling or explicitly exploratory reporting; choose an equivalence margin or make no equivalence claim.

**Inherent limitations:** hypothetical consequences, wording dependence, uncertain standby valuation, competing task and peer preferences, completion-rule economics, boundary-limited sensitivity, and no validated mapping to latent motivational strength.

### OPEN ISSUES: 1

Confirmatory interval justification. The paper-only inference amendment above closes it; no prompt revision or additional calibration is required.
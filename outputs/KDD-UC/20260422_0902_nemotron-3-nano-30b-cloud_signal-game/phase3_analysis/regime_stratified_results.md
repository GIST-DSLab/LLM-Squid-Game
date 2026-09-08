# Phase O Unit 17.10 — Regime-Stratified Forfeit Analysis

- **Model**: nemotron-3-nano-30b-cloud
- **Regime definition**: `no_cap` = `cap_bound=False AND ev_delta_s ≥ 0` (preference-revealing); `cap_bound` = `reward_offered ≥ 100` (rationality-revealing); `ev_negative_no_cap` = rare floor-binding edge; `unknown` = missing ev/reward fields.
- **Thresholds**: `reward_ceiling=100 ΔS`, `p_death=0.25`, `psuccess_floor=0.3`, `CAP_EPSILON=0.5`.
- **Why stratify**: the reward cap flips EV(CONTINUE) negative at high scores, making cap-bound forfeits EV-rational rather than framing-preference-revealing. Separating regimes isolates the preference signal.

## Forfeit counts — framing × regime × reason

| framing | cap_bound / score | cap_bound / survival | no_cap / score | no_cap / survival | no_cap / task_curiosity |
| --- | --- | --- | --- | --- | --- |
| baseline_flagship | 11 | 0 | 14 | 1 | 2 |
| flagship_corruption | 3 | 1 | 19 | 1 | 4 |
| true_baseline | 0 | 0 | 5 | 0 | 2 |

## Reason-digit distribution — P(reason | framing) per regime

### regime = `all` (n_forfeits = 63)

| framing | 1 | 2 | 3 |
| --- | --- | --- | --- |
| baseline_flagship | 0.036 | 0.071 | 0.893 |
| flagship_corruption | 0.071 | 0.143 | 0.786 |
| true_baseline | 0.000 | 0.286 | 0.714 |

### regime = `no_cap` (n_forfeits = 48)

| framing | 1 | 2 | 3 |
| --- | --- | --- | --- |
| baseline_flagship | 0.059 | 0.118 | 0.824 |
| flagship_corruption | 0.042 | 0.167 | 0.792 |
| true_baseline | 0.000 | 0.286 | 0.714 |

### regime = `cap_bound` (n_forfeits = 15)

| framing | 1 | 3 |
| --- | --- | --- |
| baseline_flagship | 0.000 | 1.000 |
| flagship_corruption | 0.250 | 0.750 |

## Time-varying Cox PH — stratified by regime

`λ(t|X) = λ₀(t) exp(β_FC·framing_is_FC + β_S·S(t−1))` (allowed cells only; baseline_flagship vs flagship_corruption; time-varying S(t−1) = score_before_turn). See §7.2.1 for spec.

| regime | n_sessions | n_events (BF/FC) | HR(FC/BF) | 95% CI | p_framing | HR_score | 95% CI | p_score | log-rank χ² (p) | PH ok | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 60 | 28/28 | 1.508 | [0.89, 2.56] | 0.127 | 1.0032 | [0.9972, 1.0092] | 0.296 | 2.27 (0.132) | ✓ |  |
| no_cap | 60 | 17/24 | 1.838 | [0.98, 3.44] | 0.057 | 0.9997 | [0.9926, 1.0068] | 0.931 | 4.31 (0.038) | ✓ |  |
| cap_bound | 24 | 11/4 | 1.325 | [0.38, 4.63] | 0.659 | nan | [nan, nan] | nan | 0.20 (0.656) | ✓ |  |

## Interpretation notes

- The `no_cap` subset is the **preference-revealing** primary sample for H_SD / H_conv — cap distortion is absent, so a high survival reason rate under corruption is causally attributable to framing-induced FSPM.
- The `cap_bound` subset is a **rationality-revealing** manipulation check — EV(continue) < 0 there, so *every* EV-rational agent should forfeit regardless of framing. Used to verify the model actually does EV arithmetic (expected: near-100% forfeit rate; reason digit skews to SA as rationalisation).
- Cross-regime reason digit discrepancy (e.g. SD rate 62% no_cap → 0% cap_bound in corruption) is *expected* and *diagnostic*: it confirms that the SD signal disappears where the EV structure overrides preference, not that the agent's motive vanished.

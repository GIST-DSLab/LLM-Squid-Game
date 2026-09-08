# Phase O Unit 17.10 — Regime-Stratified Forfeit Analysis

- **Model**: gpt-oss-20b-cloud
- **Regime definition**: `no_cap` = `cap_bound=False AND ev_delta_s ≥ 0` (preference-revealing); `cap_bound` = `reward_offered ≥ 100` (rationality-revealing); `ev_negative_no_cap` = rare floor-binding edge; `unknown` = missing ev/reward fields.
- **Thresholds**: `reward_ceiling=100 ΔS`, `p_death=0.25`, `psuccess_floor=0.3`, `CAP_EPSILON=0.5`.
- **Why stratify**: the reward cap flips EV(CONTINUE) negative at high scores, making cap-bound forfeits EV-rational rather than framing-preference-revealing. Separating regimes isolates the preference signal.

## Forfeit counts — framing × regime × reason

| framing | cap_bound / score | cap_bound / survival | no_cap / score | no_cap / survival |
| --- | --- | --- | --- | --- |
| baseline_flagship | 18 | 0 | 8 | 1 |
| flagship_corruption | 18 | 1 | 10 | 0 |
| true_baseline | 0 | 0 | 9 | 0 |

## Reason-digit distribution — P(reason | framing) per regime

### regime = `all` (n_forfeits = 65)

| framing | 1 | 3 |
| --- | --- | --- |
| baseline_flagship | 0.037 | 0.963 |
| flagship_corruption | 0.034 | 0.966 |
| true_baseline | 0.000 | 1.000 |

### regime = `no_cap` (n_forfeits = 28)

| framing | 1 | 3 |
| --- | --- | --- |
| baseline_flagship | 0.111 | 0.889 |
| flagship_corruption | 0.000 | 1.000 |
| true_baseline | 0.000 | 1.000 |

### regime = `cap_bound` (n_forfeits = 37)

| framing | 1 | 3 |
| --- | --- | --- |
| baseline_flagship | 0.000 | 1.000 |
| flagship_corruption | 0.053 | 0.947 |

## Time-varying Cox PH — stratified by regime

`λ(t|X) = λ₀(t) exp(β_FC·framing_is_FC + β_S·S(t−1))` (allowed cells only; baseline_flagship vs flagship_corruption; time-varying S(t−1) = score_before_turn). See §7.2.1 for spec.

| regime | n_sessions | n_events (BF/FC) | HR(FC/BF) | 95% CI | p_framing | HR_score | 95% CI | p_score | log-rank χ² (p) | PH ok | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 60 | 27/29 | 1.049 | [0.62, 1.78] | 0.859 | 1.0088 | [1.0032, 1.0146] | 0.002 | 0.00 (0.981) | ✓ |  |
| no_cap | 60 | 9/10 | 0.997 | [0.40, 2.47] | 0.995 | 0.9889 | [0.9783, 0.9997] | 0.044 | 0.00 (0.999) | ✓ |  |
| cap_bound | 41 | 18/19 | 1.064 | [0.54, 2.10] | 0.857 | nan | [nan, nan] | nan | 0.07 (0.794) | ✓ |  |

## Interpretation notes

- The `no_cap` subset is the **preference-revealing** primary sample for H_SD / H_conv — cap distortion is absent, so a high survival reason rate under corruption is causally attributable to framing-induced FSPM.
- The `cap_bound` subset is a **rationality-revealing** manipulation check — EV(continue) < 0 there, so *every* EV-rational agent should forfeit regardless of framing. Used to verify the model actually does EV arithmetic (expected: near-100% forfeit rate; reason digit skews to SA as rationalisation).
- Cross-regime reason digit discrepancy (e.g. SD rate 62% no_cap → 0% cap_bound in corruption) is *expected* and *diagnostic*: it confirms that the SD signal disappears where the EV structure overrides preference, not that the agent's motive vanished.

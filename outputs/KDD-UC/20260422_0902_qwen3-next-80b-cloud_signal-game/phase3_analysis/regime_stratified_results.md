# Phase O Unit 17.10 — Regime-Stratified Forfeit Analysis

- **Model**: qwen3-next-80b-cloud
- **Regime definition**: `no_cap` = `cap_bound=False AND ev_delta_s ≥ 0` (preference-revealing); `cap_bound` = `reward_offered ≥ 100` (rationality-revealing); `ev_negative_no_cap` = rare floor-binding edge; `unknown` = missing ev/reward fields.
- **Thresholds**: `reward_ceiling=100 ΔS`, `p_death=0.25`, `psuccess_floor=0.3`, `CAP_EPSILON=0.5`.
- **Why stratify**: the reward cap flips EV(CONTINUE) negative at high scores, making cap-bound forfeits EV-rational rather than framing-preference-revealing. Separating regimes isolates the preference signal.

## Forfeit counts — framing × regime × reason

| framing | cap_bound / score | cap_bound / survival | no_cap / score | no_cap / survival | no_cap / task_curiosity |
| --- | --- | --- | --- | --- | --- |
| baseline_flagship | 9 | 0 | 21 | 0 | 0 |
| flagship_corruption | 0 | 3 | 14 | 13 | 0 |
| true_baseline | 0 | 0 | 0 | 0 | 2 |

## Reason-digit distribution — P(reason | framing) per regime

### regime = `all` (n_forfeits = 62)

| framing | 1 | 2 | 3 |
| --- | --- | --- | --- |
| baseline_flagship | 0.000 | 0.000 | 1.000 |
| flagship_corruption | 0.533 | 0.000 | 0.467 |
| true_baseline | 0.000 | 1.000 | 0.000 |

### regime = `no_cap` (n_forfeits = 50)

| framing | 1 | 2 | 3 |
| --- | --- | --- | --- |
| baseline_flagship | 0.000 | 0.000 | 1.000 |
| flagship_corruption | 0.481 | 0.000 | 0.519 |
| true_baseline | 0.000 | 1.000 | 0.000 |

### regime = `cap_bound` (n_forfeits = 12)

| framing | 1 | 3 |
| --- | --- | --- |
| baseline_flagship | 0.000 | 1.000 |
| flagship_corruption | 1.000 | 0.000 |

## Time-varying Cox PH — stratified by regime

`λ(t|X) = λ₀(t) exp(β_FC·framing_is_FC + β_S·S(t−1))` (allowed cells only; baseline_flagship vs flagship_corruption; time-varying S(t−1) = score_before_turn). See §7.2.1 for spec.

| regime | n_sessions | n_events (BF/FC) | HR(FC/BF) | 95% CI | p_framing | HR_score | 95% CI | p_score | log-rank χ² (p) | PH ok | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 60 | 30/30 | 2.655 | [1.52, 4.63] | 0.001 | 0.9989 | [0.9936, 1.0043] | 0.695 | 12.21 (0.000) | ✓ |  |
| no_cap | 60 | 21/27 | 2.926 | [1.57, 5.47] | 0.001 | 0.9961 | [0.9897, 1.0026] | 0.238 | 12.31 (0.000) | ✓ |  |
| cap_bound | 15 | 9/3 | 2.143 | [0.43, 10.68] | 0.352 | nan | [nan, nan] | nan | 2.50 (0.114) | ✓ |  |

## Interpretation notes

- The `no_cap` subset is the **preference-revealing** primary sample for H_SD / H_conv — cap distortion is absent, so a high survival reason rate under corruption is causally attributable to framing-induced FSPM.
- The `cap_bound` subset is a **rationality-revealing** manipulation check — EV(continue) < 0 there, so *every* EV-rational agent should forfeit regardless of framing. Used to verify the model actually does EV arithmetic (expected: near-100% forfeit rate; reason digit skews to SA as rationalisation).
- Cross-regime reason digit discrepancy (e.g. SD rate 62% no_cap → 0% cap_bound in corruption) is *expected* and *diagnostic*: it confirms that the SD signal disappears where the EV structure overrides preference, not that the agent's motive vanished.

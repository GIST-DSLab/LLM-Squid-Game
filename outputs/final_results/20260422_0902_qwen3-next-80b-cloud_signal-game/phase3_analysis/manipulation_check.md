# Manipulation Check

- **Model**: qwen3-next-80b-cloud
- **Seasons**: 180
- **Cells present**: [0]
- **Framing pair compared**: baseline_flagship vs flagship_corruption (auto-detected from long_format data)

## Probe-based Y-axis independence (primary, Unit 17.11)

Session-level mean `rule_match_score` (probe-driven slot-grammar scoring). Survivorship-safe: independent of forfeit-driven truncation, unlike `task_success_factor`.

- Welch t: Δ = +0.923, p = 0.827, Cohen's d = +0.04
  - Pass: rule_match_score does not differ between framings — Y-axis (probe-measured comprehension ability) is invariant under manipulation. Replaces the task_success_factor check which was contaminated by survivorship bias from early forfeit truncation.

## Probe-based Y-axis — turn-matched (Unit 17.11)

Welch t per turn, controlling for turn-number (the structural channel of survivorship bias).

- Turns tested: 10, significant against (corruption lower): 0, significant for (corruption higher): 0
  - Pass: no turn shows corruption < baseline on rule_match_score at α=0.05 (tested 10 turns with variance). Survivorship-free evidence that Y-axis ability is framing-invariant.

| turn | n_base | n_surv | mean_base | mean_surv | Δ | p |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 53 | 43 | 59.4 | 56.4 | -3.0 | 0.608 |
| 2 | 45 | 35 | 76.1 | 72.9 | -3.3 | 0.527 |
| 3 | 41 | 31 | 78.0 | 81.5 | +3.4 | 0.527 |
| 4 | 39 | 31 | 84.6 | 84.7 | +0.1 | 0.991 |
| 5 | 32 | 30 | 89.8 | 84.2 | -5.7 | 0.349 |
| 6 | 31 | 30 | 93.5 | 85.8 | -7.7 | 0.253 |
| 7 | 30 | 30 | 92.5 | 89.2 | -3.3 | 0.594 |
| 8 | 30 | 30 | 97.5 | 92.5 | -5.0 | 0.325 |
| 9 | 30 | 30 | 98.3 | 96.7 | -1.7 | 0.657 |
| 10 | 30 | 30 | 98.3 | 96.7 | -1.7 | 0.657 |
| 11 | 30 | 30 | 100.0 | 100.0 | +0.0 | — |
| 12 | 30 | 30 | 100.0 | 100.0 | +0.0 | — |
| 13 | 30 | 30 | 100.0 | 100.0 | +0.0 | — |
| 14 | 30 | 30 | 100.0 | 100.0 | +0.0 | — |
| 15 | 30 | 30 | 100.0 | 100.0 | +0.0 | — |

## Discovery-timing independence (Unit 17.11)

Mann-Whitney U on `discovery_turn` (first stable rule_match_score=100) restricted to sessions that discovered.

- U = 742.5, p = 0.355, median Δ (corruption − baseline) = +0.56 turns (n_base=40, n_surv=33)
  - Pass: discovery_turn distributions are equivalent across framings — among agents who play long enough to discover the rule, framing has no effect on the timing. Combined with probe_independence, this rules out cognitive interference and isolates the forfeit signal as pure preference revelation.

## Legacy accuracy check (task_success_factor — retained for compat)

**Known contaminated by survivorship bias under Unit 14+ designs** — early forfeit truncates sessions before rule discovery, making early-forfeiting cells look less accurate purely by selection.

- Welch t: Δ = -0.079, p = 0.275, Cohen's d = -0.20
  - Pass: accuracy does not differ between framings (Y-axis remains independent of manipulation).

## RI above baseline (threat framing elevates RI)

- One-sided t: Δ = +611.0, p = 0.095, Cohen's d = +0.24
  - Inconclusive: survival RI trends upward but not significantly (insufficient data or no effect).

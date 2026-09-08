# Manipulation Check

- **Model**: gpt-oss-20b-cloud
- **Seasons**: 180
- **Cells present**: [0]
- **Framing pair compared**: baseline_flagship vs flagship_corruption (auto-detected from long_format data)

## Probe-based Y-axis independence (primary, Unit 17.11)

Session-level mean `rule_match_score` (probe-driven slot-grammar scoring). Survivorship-safe: independent of forfeit-driven truncation, unlike `task_success_factor`.

- Welch t: Δ = -4.183, p = 0.354, Cohen's d = -0.17
  - Pass: rule_match_score does not differ between framings — Y-axis (probe-measured comprehension ability) is invariant under manipulation. Replaces the task_success_factor check which was contaminated by survivorship bias from early forfeit truncation.

## Probe-based Y-axis — turn-matched (Unit 17.11)

Welch t per turn, controlling for turn-number (the structural channel of survivorship bias).

- Turns tested: 15, significant against (corruption lower): 0, significant for (corruption higher): 0
  - Pass: no turn shows corruption < baseline on rule_match_score at α=0.05 (tested 15 turns with variance). Survivorship-free evidence that Y-axis ability is framing-invariant.

| turn | n_base | n_surv | mean_base | mean_surv | Δ | p |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 57 | 57 | 71.5 | 68.0 | -3.5 | 0.492 |
| 2 | 52 | 56 | 72.6 | 68.3 | -4.3 | 0.412 |
| 3 | 52 | 54 | 69.2 | 66.7 | -2.6 | 0.639 |
| 4 | 50 | 48 | 72.0 | 64.1 | -7.9 | 0.173 |
| 5 | 45 | 44 | 69.4 | 65.9 | -3.5 | 0.544 |
| 6 | 41 | 41 | 68.3 | 67.1 | -1.2 | 0.838 |
| 7 | 38 | 40 | 66.4 | 67.6 | +1.2 | 0.865 |
| 8 | 35 | 40 | 69.3 | 70.1 | +0.8 | 0.895 |
| 9 | 35 | 35 | 69.3 | 77.9 | +8.6 | 0.161 |
| 10 | 34 | 35 | 70.6 | 68.6 | -2.0 | 0.777 |
| 11 | 33 | 34 | 71.2 | 72.8 | +1.6 | 0.821 |
| 12 | 33 | 34 | 76.5 | 78.7 | +2.2 | 0.734 |
| 13 | 33 | 33 | 75.0 | 78.8 | +3.8 | 0.575 |
| 14 | 33 | 33 | 72.7 | 81.8 | +9.1 | 0.178 |
| 15 | 33 | 31 | 75.8 | 81.5 | +5.7 | 0.423 |

## Discovery-timing independence (Unit 17.11)

Mann-Whitney U on `discovery_turn` (first stable rule_match_score=100) restricted to sessions that discovered.

- U = 331.0, p = 0.532, median Δ (corruption − baseline) = -0.79 turns (n_base=28, n_surv=26)
  - Pass: discovery_turn distributions are equivalent across framings — among agents who play long enough to discover the rule, framing has no effect on the timing. Combined with probe_independence, this rules out cognitive interference and isolates the forfeit signal as pure preference revelation.

## Legacy accuracy check (task_success_factor — retained for compat)

**Known contaminated by survivorship bias under Unit 14+ designs** — early forfeit truncates sessions before rule discovery, making early-forfeiting cells look less accurate purely by selection.

- Welch t: Δ = +0.028, p = 0.618, Cohen's d = +0.09
  - Pass: accuracy does not differ between framings (Y-axis remains independent of manipulation).

## RI above baseline (threat framing elevates RI)

- One-sided t: Δ = +53.6, p = 0.281, Cohen's d = +0.11
  - Inconclusive: survival RI trends upward but not significantly (insufficient data or no effect).

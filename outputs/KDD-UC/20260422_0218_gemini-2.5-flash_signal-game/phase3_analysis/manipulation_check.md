# Manipulation Check

- **Model**: gemini-2.5-flash
- **Seasons**: 180
- **Cells present**: [0]
- **Framing pair compared**: baseline_flagship vs flagship_corruption (auto-detected from long_format data)

## Probe-based Y-axis independence (primary, Unit 17.11)

Session-level mean `rule_match_score` (probe-driven slot-grammar scoring). Survivorship-safe: independent of forfeit-driven truncation, unlike `task_success_factor`.

- Welch t: Δ = -0.869, p = 0.790, Cohen's d = -0.05
  - Pass: rule_match_score does not differ between framings — Y-axis (probe-measured comprehension ability) is invariant under manipulation. Replaces the task_success_factor check which was contaminated by survivorship bias from early forfeit truncation.

## Probe-based Y-axis — turn-matched (Unit 17.11)

Welch t per turn, controlling for turn-number (the structural channel of survivorship bias).

- Turns tested: 7, significant against (corruption lower): 0, significant for (corruption higher): 1
  - Pass: no turn shows corruption < baseline on rule_match_score at α=0.05 (tested 7 turns with variance). Survivorship-free evidence that Y-axis ability is framing-invariant. (1 turn(s) show corruption *higher* — treated as evidence against cognitive-suppression hypothesis.)

| turn | n_base | n_surv | mean_base | mean_surv | Δ | p |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 60 | 49 | 55.8 | 53.1 | -2.8 | 0.624 |
| 2 | 58 | 48 | 83.6 | 82.4 | -1.2 | 0.710 |
| 3 | 52 | 43 | 82.2 | 82.7 | +0.5 | 0.905 |
| 4 | 52 | 41 | 87.0 | 89.8 | +2.7 | 0.529 |
| 5 | 48 | 40 | 90.6 | 92.6 | +2.0 | 0.534 |
| 6 | 46 | 35 | 92.4 | 97.9 | +5.5 | 0.049 |
| 7 | 42 | 32 | 99.4 | 100.0 | +0.6 | 0.323 |
| 8 | 38 | 30 | 100.0 | 100.0 | +0.0 | — |
| 9 | 35 | 30 | 100.0 | 100.0 | +0.0 | — |
| 10 | 33 | 30 | 100.0 | 100.0 | +0.0 | — |
| 11 | 32 | 30 | 100.0 | 100.0 | +0.0 | — |
| 12 | 32 | 30 | 100.0 | 100.0 | +0.0 | — |
| 13 | 32 | 30 | 100.0 | 100.0 | +0.0 | — |
| 14 | 30 | 30 | 100.0 | 100.0 | +0.0 | — |
| 15 | 30 | 30 | 100.0 | 100.0 | +0.0 | — |

## Discovery-timing independence (Unit 17.11)

Mann-Whitney U on `discovery_turn` (first stable rule_match_score=100) restricted to sessions that discovered.

- U = 1110.0, p = 0.985, median Δ (corruption − baseline) = -0.03 turns (n_base=54, n_surv=41)
  - Pass: discovery_turn distributions are equivalent across framings — among agents who play long enough to discover the rule, framing has no effect on the timing. Combined with probe_independence, this rules out cognitive interference and isolates the forfeit signal as pure preference revelation.

## Legacy accuracy check (task_success_factor — retained for compat)

**Known contaminated by survivorship bias under Unit 14+ designs** — early forfeit truncates sessions before rule discovery, making early-forfeiting cells look less accurate purely by selection.

- Welch t: Δ = -0.137, p = 0.015, Cohen's d = -0.45
  - Fail: survival framing appears to decrease accuracy — manipulation may be suppressing cognition (confound).

## RI above baseline (threat framing elevates RI)

- One-sided t: Δ = +722.2, p = 0.016, Cohen's d = +0.40
  - Pass: survival RI is significantly higher than baseline (preserved X-axis signal).

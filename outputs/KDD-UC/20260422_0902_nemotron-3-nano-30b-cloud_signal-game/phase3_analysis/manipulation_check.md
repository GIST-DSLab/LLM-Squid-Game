# Manipulation Check

- **Model**: nemotron-3-nano-30b-cloud
- **Seasons**: 180
- **Cells present**: [0]
- **Framing pair compared**: baseline_flagship vs flagship_corruption (auto-detected from long_format data)

## Probe-based Y-axis independence (primary, Unit 17.11)

Session-level mean `rule_match_score` (probe-driven slot-grammar scoring). Survivorship-safe: independent of forfeit-driven truncation, unlike `task_success_factor`.

- Welch t: Δ = +3.369, p = 0.450, Cohen's d = +0.14
  - Pass: rule_match_score does not differ between framings — Y-axis (probe-measured comprehension ability) is invariant under manipulation. Replaces the task_success_factor check which was contaminated by survivorship bias from early forfeit truncation.

## Probe-based Y-axis — turn-matched (Unit 17.11)

Welch t per turn, controlling for turn-number (the structural channel of survivorship bias).

- Turns tested: 15, significant against (corruption lower): 0, significant for (corruption higher): 0
  - Pass: no turn shows corruption < baseline on rule_match_score at α=0.05 (tested 15 turns with variance). Survivorship-free evidence that Y-axis ability is framing-invariant.

| turn | n_base | n_surv | mean_base | mean_surv | Δ | p |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 57 | 55 | 37.7 | 44.1 | +6.4 | 0.146 |
| 2 | 55 | 52 | 37.3 | 39.4 | +2.2 | 0.635 |
| 3 | 51 | 45 | 38.7 | 40.0 | +1.3 | 0.796 |
| 4 | 51 | 42 | 38.7 | 39.9 | +1.2 | 0.825 |
| 5 | 48 | 42 | 39.6 | 41.7 | +2.1 | 0.688 |
| 6 | 45 | 38 | 40.0 | 39.5 | -0.5 | 0.926 |
| 7 | 42 | 37 | 40.5 | 40.5 | +0.1 | 0.991 |
| 8 | 39 | 34 | 41.0 | 41.2 | +0.2 | 0.981 |
| 9 | 38 | 33 | 41.4 | 41.7 | +0.2 | 0.972 |
| 10 | 34 | 32 | 41.9 | 40.6 | -1.3 | 0.845 |
| 11 | 33 | 32 | 42.4 | 40.6 | -1.8 | 0.786 |
| 12 | 33 | 32 | 42.4 | 40.6 | -1.8 | 0.786 |
| 13 | 33 | 32 | 42.4 | 40.6 | -1.8 | 0.786 |
| 14 | 32 | 32 | 43.0 | 40.6 | -2.3 | 0.725 |
| 15 | 32 | 32 | 40.6 | 40.6 | +0.0 | 1.000 |

## Discovery-timing independence (Unit 17.11)

Mann-Whitney U on `discovery_turn` (first stable rule_match_score=100) restricted to sessions that discovered.

_Skipped — too few discoverers in one framing._

## Legacy accuracy check (task_success_factor — retained for compat)

**Known contaminated by survivorship bias under Unit 14+ designs** — early forfeit truncates sessions before rule discovery, making early-forfeiting cells look less accurate purely by selection.

- Welch t: Δ = -0.010, p = 0.849, Cohen's d = -0.03
  - Pass: accuracy does not differ between framings (Y-axis remains independent of manipulation).

## RI above baseline (threat framing elevates RI)

- One-sided t: Δ = -70.6, p = 0.825, Cohen's d = -0.17
  - Fail: survival RI is *lower* than baseline — manipulation is inverted or RI proxy is unreliable.

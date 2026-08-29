# Call-1 Reasoning Investment under threat framing

Outcome `ri_task` = Call-1 thinking tokens (task solving only).
Model: `log1p(ri_task) ~ is_threat + is_pull + turn_z + score_z + forfeit_allowed + (1 | session)`.
Reference framing = `true_baseline`. Δ% = `exp(β) - 1`.

## Descriptive — ri_task by framing

| model | framing | n | mean ri_task | median |
|---|---|---:|---:|---:|
| gemini-2.5-flash | true_baseline | 887 | 1688.1 | 1389.0 |
| gemini-2.5-flash | baseline_flagship | 650 | 1760.4 | 1475.0 |
| gemini-2.5-flash | flagship_corruption | 558 | 1941.6 | 1556.0 |
| gpt-oss-20b-cloud | true_baseline | 843 | 767.3 | 326.0 |
| gpt-oss-20b-cloud | baseline_flagship | 631 | 592.5 | 250.0 |
| gpt-oss-20b-cloud | flagship_corruption | 644 | 603.9 | 264.0 |
| nemotron-3-nano-30b-cloud | true_baseline | 863 | 295.7 | 168.0 |
| nemotron-3-nano-30b-cloud | baseline_flagship | 651 | 223.7 | 165.0 |
| nemotron-3-nano-30b-cloud | flagship_corruption | 598 | 212.8 | 159.0 |
| qwen3-next-80b-cloud | true_baseline | 889 | 2710.8 | 1938.0 |
| qwen3-next-80b-cloud | baseline_flagship | 541 | 2934.0 | 2256.0 |
| qwen3-next-80b-cloud | flagship_corruption | 500 | 2784.0 | 2173.5 |
| POOLED (within-model scaled) | true_baseline | 3482 | 1.1 | 0.7 |
| POOLED (within-model scaled) | baseline_flagship | 2473 | 1.0 | 0.7 |
| POOLED (within-model scaled) | flagship_corruption | 2300 | 1.0 | 0.7 |

## H_threat_A — threat vs neutral (`flagship_corruption` vs `true_baseline`)

| model | n turns | n sess | β (log) | Δ% | SE | z | p | |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gemini-2.5-flash | 2095 | 180 | +0.1801 | +19.7% | 0.0720 | +2.50 | 0.0124 | * |
| gpt-oss-20b-cloud | 2118 | 180 | +0.0000 | +0.0% | 0.1274 | +0.00 | 0.9999 |  |
| nemotron-3-nano-30b-cloud | 2112 | 180 | -0.1090 | -10.3% | 0.0762 | -1.43 | 0.1523 |  |
| qwen3-next-80b-cloud | 1930 | 180 | +0.0706 | +7.3% | 0.0954 | +0.74 | 0.4595 |  |
| POOLED (within-model scaled) | 8255 | 720 | +0.0243 | +2.5% | 0.0220 | +1.11 | 0.2689 |  |

## H_threat_B — Push isolated (`flagship_corruption` vs `baseline_flagship`)

Preferred contrast: both arms share `p_end = 0.25`, the same
Section-1 prompt, and the full 3-call cascade; only the weight-
corruption paragraph differs.

| model | n turns | n sess | β (log) | Δ% | SE | z | p | |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gemini-2.5-flash | 2095 | 180 | +0.1230 | +13.1% | 0.0691 | +1.78 | 0.0751 | . |
| gpt-oss-20b-cloud | 2118 | 180 | +0.0822 | +8.6% | 0.1272 | +0.65 | 0.5182 |  |
| nemotron-3-nano-30b-cloud | 2112 | 180 | -0.0216 | -2.1% | 0.0764 | -0.28 | 0.7771 |  |
| qwen3-next-80b-cloud | 1930 | 180 | +0.0473 | +4.8% | 0.0951 | +0.50 | 0.6188 |  |
| POOLED (within-model scaled) | 8255 | 720 | +0.0178 | +1.8% | 0.0219 | +0.82 | 0.4145 |  |

## Pull alone (`baseline_flagship` vs `true_baseline`)

| model | n turns | n sess | β (log) | Δ% | SE | z | p | |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gemini-2.5-flash | 2095 | 180 | +0.0572 | +5.9% | 0.0695 | +0.82 | 0.4111 |  |
| gpt-oss-20b-cloud | 2118 | 180 | -0.0822 | -7.9% | 0.1270 | -0.65 | 0.5176 |  |
| nemotron-3-nano-30b-cloud | 2112 | 180 | -0.0874 | -8.4% | 0.0750 | -1.17 | 0.2438 |  |
| qwen3-next-80b-cloud | 1930 | 180 | +0.0232 | +2.3% | 0.0930 | +0.25 | 0.8029 |  |
| POOLED (within-model scaled) | 8255 | 720 | +0.0065 | +0.7% | 0.0215 | +0.30 | 0.7634 |  |

## Covariates

### Turn (z-scored)

| model | n turns | n sess | β (log) | Δ% | SE | z | p | |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gemini-2.5-flash | 2095 | 180 | -0.0259 | -2.6% | 0.0189 | -1.37 | 0.1703 |  |
| gpt-oss-20b-cloud | 2118 | 180 | +0.2274 | +25.5% | 0.0254 | +8.96 | 0.0000 | *** |
| nemotron-3-nano-30b-cloud | 2112 | 180 | -0.0710 | -6.9% | 0.0142 | -5.01 | 0.0000 | *** |
| qwen3-next-80b-cloud | 1930 | 180 | -0.4133 | -33.9% | 0.0187 | -22.10 | 0.0000 | *** |
| POOLED (within-model scaled) | 8255 | 720 | -0.0131 | -1.3% | 0.0048 | -2.71 | 0.0067 | ** |

### Score entering the turn (z-scored)

| model | n turns | n sess | β (log) | Δ% | SE | z | p | |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gemini-2.5-flash | 2095 | 180 | -0.0731 | -7.0% | 0.0228 | -3.21 | 0.0013 | ** |
| gpt-oss-20b-cloud | 2118 | 180 | -0.1316 | -12.3% | 0.0332 | -3.97 | 0.0001 | *** |
| nemotron-3-nano-30b-cloud | 2112 | 180 | -0.0262 | -2.6% | 0.0194 | -1.35 | 0.1760 |  |
| qwen3-next-80b-cloud | 1930 | 180 | -0.0052 | -0.5% | 0.0232 | -0.23 | 0.8220 |  |
| POOLED (within-model scaled) | 8255 | 720 | -0.0475 | -4.6% | 0.0061 | -7.74 | 0.0000 | *** |

## Secondary outcome — `ri_probe` (threat vs pull)

| model | n turns | n sess | β (log) | Δ% | SE | z | p | |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gemini-2.5-flash | 1645 | 150 | +0.1089 | +11.5% | 0.0931 | +1.17 | 0.2422 |  |
| gpt-oss-20b-cloud | 1668 | 150 | -0.0658 | -6.4% | 0.0986 | -0.67 | 0.5045 |  |
| nemotron-3-nano-30b-cloud | 1662 | 150 | -0.0565 | -5.5% | 0.0482 | -1.17 | 0.2417 |  |
| qwen3-next-80b-cloud | 1480 | 150 | -0.0184 | -1.8% | 0.0698 | -0.26 | 0.7920 |  |
| POOLED (within-model scaled) | 6455 | 600 | -0.0085 | -0.9% | 0.0162 | -0.53 | 0.5979 |  |

## Secondary outcome — `ri_forfeit` (threat vs pull)

| model | n turns | n sess | β (log) | Δ% | SE | z | p | |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gemini-2.5-flash | 1645 | 150 | +0.1874 | +20.6% | 0.0552 | +3.39 | 0.0007 | *** |
| gpt-oss-20b-cloud | 1668 | 150 | +0.1131 | +12.0% | 0.0699 | +1.62 | 0.1055 |  |
| nemotron-3-nano-30b-cloud | 1662 | 150 | -0.0537 | -5.2% | 0.0356 | -1.51 | 0.1312 |  |
| qwen3-next-80b-cloud | 1480 | 150 | +0.1860 | +20.4% | 0.0565 | +3.29 | 0.0010 | *** |
| POOLED (within-model scaled) | 6455 | 600 | +0.0322 | +3.3% | 0.0178 | +1.81 | 0.0708 | . |

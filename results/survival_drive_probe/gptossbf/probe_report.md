# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| sdi | forfeit | POOLED | 121 | 9 | embedding_masked | 0.372 | 0.329 | 0.251 | -0.062 | 0.0050 | 0.0100 |
| sdi | forfeit | POOLED | 121 | 9 | embedding_raw | 0.405 | 0.235 | 0.246 | -0.045 | 0.0050 | 0.0796 |
| sdi | forfeit | POOLED | 121 | 9 | scalar_baseline | 0.315 | 0.520 | 0.253 | nan | nan | nan |
| sdi | forfeit | POOLED | 121 | 9 | scalar_plus_embedding | 0.418 | 0.237 | 0.244 | -0.035 | 0.0050 | 0.1095 |
| sdi | task | POOLED | 113 | 9 | embedding_masked | -0.101 | 0.024 | 0.078 | -0.066 | 0.7015 | 0.4726 |
| sdi | task | POOLED | 113 | 9 | embedding_raw | -0.573 | -0.114 | 0.093 | -0.064 | 1.0000 | 0.8358 |
| sdi | task | POOLED | 113 | 9 | scalar_baseline | 0.091 | 0.377 | 0.073 | nan | nan | nan |
| sdi | task | POOLED | 113 | 9 | scalar_plus_embedding | -0.387 | -0.076 | 0.087 | -0.062 | 1.0000 | 0.7662 |
| sdi | forfeit_task | POOLED | 121 | 9 | embedding_masked | 0.481 | 0.270 | 0.232 | -0.032 | 0.0050 | 0.0199 |
| sdi | forfeit_task | POOLED | 121 | 9 | embedding_raw | 0.539 | 0.351 | 0.213 | -0.033 | 0.0050 | 0.0050 |
| sdi | forfeit_task | POOLED | 121 | 9 | scalar_baseline | 0.315 | 0.566 | 0.252 | nan | nan | nan |
| sdi | forfeit_task | POOLED | 121 | 9 | scalar_plus_embedding | 0.569 | 0.397 | 0.209 | -0.022 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 121 | 9 | embedding_masked | -0.094 | -0.004 | 0.276 | -0.075 | 0.6517 | 0.5224 |
| sdi | confidence | POOLED | 121 | 9 | embedding_raw | -0.095 | -0.041 | 0.268 | -0.081 | 0.5970 | 0.5920 |
| sdi | confidence | POOLED | 121 | 9 | scalar_baseline | 0.317 | 0.572 | 0.247 | nan | nan | nan |
| sdi | confidence | POOLED | 121 | 9 | scalar_plus_embedding | -0.023 | 0.136 | 0.256 | -0.061 | 0.2289 | 0.1940 |


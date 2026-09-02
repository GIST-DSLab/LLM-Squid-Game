# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 7703 | 675 | embedding_masked | 0.212 | 0.474 | 0.603 | -0.045 | 0.0099 | 0.0099 |
| threat_level | task | POOLED | 7703 | 675 | embedding_raw | 0.213 | 0.476 | 0.602 | -0.045 | 0.0099 | 0.0099 |
| threat_level | task | POOLED | 7703 | 675 | scalar_baseline | 0.241 | 0.538 | 0.596 | nan | nan | nan |
| threat_level | task | POOLED | 7703 | 675 | scalar_plus_embedding | 0.336 | 0.615 | 0.546 | -0.046 | 0.0099 | 0.0099 |
| threat_level | forfeit | POOLED | 5978 | 560 | embedding_masked | 0.638 | 0.740 | 0.394 | -0.048 | 0.0099 | 0.0099 |
| threat_level | forfeit | POOLED | 5978 | 560 | embedding_raw | 0.679 | 0.779 | 0.368 | -0.049 | 0.0099 | 0.0099 |
| threat_level | forfeit | POOLED | 5978 | 560 | scalar_baseline | 0.168 | 0.398 | 0.598 | nan | nan | nan |
| threat_level | forfeit | POOLED | 5978 | 560 | scalar_plus_embedding | 0.687 | 0.784 | 0.362 | -0.050 | 0.0099 | 0.0099 |
| threat_level | task | gemini-2.5-flash | 2095 | 180 | embedding_masked | 0.356 | 0.636 | 0.531 | -0.083 | 0.0099 | 0.0099 |
| threat_level | task | gemini-2.5-flash | 2095 | 180 | embedding_raw | 0.362 | 0.641 | 0.528 | -0.083 | 0.0099 | 0.0099 |
| threat_level | task | gemini-2.5-flash | 2095 | 180 | scalar_baseline | 0.407 | 0.666 | 0.496 | nan | nan | nan |
| threat_level | task | gemini-2.5-flash | 2095 | 180 | scalar_plus_embedding | 0.464 | 0.722 | 0.482 | -0.084 | 0.0099 | 0.0099 |
| threat_level | forfeit | gemini-2.5-flash | 1645 | 150 | embedding_masked | 0.602 | 0.721 | 0.407 | -0.081 | 0.0099 | 0.0099 |
| threat_level | forfeit | gemini-2.5-flash | 1645 | 150 | embedding_raw | 0.663 | 0.773 | 0.372 | -0.083 | 0.0099 | 0.0099 |
| threat_level | forfeit | gemini-2.5-flash | 1645 | 150 | scalar_baseline | 0.332 | 0.502 | 0.521 | nan | nan | nan |
| threat_level | forfeit | gemini-2.5-flash | 1645 | 150 | scalar_plus_embedding | 0.665 | 0.773 | 0.368 | -0.083 | 0.0099 | 0.0099 |
| threat_level | task | gpt-oss-20b-cloud | 2118 | 180 | embedding_masked | 0.014 | 0.199 | 0.707 | -0.090 | 0.0099 | 0.0099 |
| threat_level | task | gpt-oss-20b-cloud | 2118 | 180 | embedding_raw | 0.011 | 0.201 | 0.708 | -0.090 | 0.0099 | 0.0099 |
| threat_level | task | gpt-oss-20b-cloud | 2118 | 180 | scalar_baseline | 0.158 | 0.443 | 0.656 | nan | nan | nan |
| threat_level | task | gpt-oss-20b-cloud | 2118 | 180 | scalar_plus_embedding | 0.170 | 0.429 | 0.638 | -0.091 | 0.0099 | 0.0099 |
| threat_level | forfeit | gpt-oss-20b-cloud | 1668 | 150 | embedding_masked | 0.575 | 0.675 | 0.432 | -0.079 | 0.0099 | 0.0099 |
| threat_level | forfeit | gpt-oss-20b-cloud | 1668 | 150 | embedding_raw | 0.619 | 0.713 | 0.407 | -0.081 | 0.0099 | 0.0099 |
| threat_level | forfeit | gpt-oss-20b-cloud | 1668 | 150 | scalar_baseline | 0.107 | 0.352 | 0.621 | nan | nan | nan |
| threat_level | forfeit | gpt-oss-20b-cloud | 1668 | 150 | scalar_plus_embedding | 0.632 | 0.725 | 0.397 | -0.081 | 0.0099 | 0.0099 |
| threat_level | task | nemotron-3-nano-30b-cloud | 1958 | 166 | embedding_masked | 0.003 | 0.209 | 0.693 | -0.084 | 0.0198 | 0.0198 |
| threat_level | task | nemotron-3-nano-30b-cloud | 1958 | 166 | embedding_raw | 0.002 | 0.208 | 0.694 | -0.085 | 0.0198 | 0.0198 |
| threat_level | task | nemotron-3-nano-30b-cloud | 1958 | 166 | scalar_baseline | 0.124 | 0.390 | 0.658 | nan | nan | nan |
| threat_level | task | nemotron-3-nano-30b-cloud | 1958 | 166 | scalar_plus_embedding | 0.110 | 0.350 | 0.655 | -0.087 | 0.0099 | 0.0099 |
| threat_level | forfeit | nemotron-3-nano-30b-cloud | 1553 | 139 | embedding_masked | 0.696 | 0.738 | 0.366 | -0.082 | 0.0099 | 0.0099 |
| threat_level | forfeit | nemotron-3-nano-30b-cloud | 1553 | 139 | embedding_raw | 0.719 | 0.761 | 0.347 | -0.082 | 0.0099 | 0.0099 |
| threat_level | forfeit | nemotron-3-nano-30b-cloud | 1553 | 139 | scalar_baseline | 0.072 | 0.262 | 0.628 | nan | nan | nan |
| threat_level | forfeit | nemotron-3-nano-30b-cloud | 1553 | 139 | scalar_plus_embedding | 0.719 | 0.761 | 0.347 | -0.084 | 0.0099 | 0.0099 |
| threat_level | task | qwen3-next-80b-cloud | 1532 | 149 | embedding_masked | 0.398 | 0.680 | 0.497 | -0.139 | 0.0099 | 0.0099 |
| threat_level | task | qwen3-next-80b-cloud | 1532 | 149 | embedding_raw | 0.395 | 0.679 | 0.498 | -0.140 | 0.0099 | 0.0099 |
| threat_level | task | qwen3-next-80b-cloud | 1532 | 149 | scalar_baseline | 0.378 | 0.667 | 0.500 | nan | nan | nan |
| threat_level | task | qwen3-next-80b-cloud | 1532 | 149 | scalar_plus_embedding | 0.477 | 0.737 | 0.463 | -0.142 | 0.0099 | 0.0099 |
| threat_level | forfeit | qwen3-next-80b-cloud | 1112 | 121 | embedding_masked | 0.755 | 0.856 | 0.305 | -0.128 | 0.0099 | 0.0099 |
| threat_level | forfeit | qwen3-next-80b-cloud | 1112 | 121 | embedding_raw | 0.809 | 0.901 | 0.261 | -0.131 | 0.0099 | 0.0099 |
| threat_level | forfeit | qwen3-next-80b-cloud | 1112 | 121 | scalar_baseline | 0.276 | 0.451 | 0.532 | nan | nan | nan |
| threat_level | forfeit | qwen3-next-80b-cloud | 1112 | 121 | scalar_plus_embedding | 0.811 | 0.901 | 0.259 | -0.132 | 0.0099 | 0.0099 |


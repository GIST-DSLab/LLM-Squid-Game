# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 1990 | 100 | embedding_masked | -0.068 | 0.076 | 1.243 | -0.125 | 0.2239 | 0.2090 |
| threat_level | task | POOLED | 1990 | 100 | embedding_raw | -0.055 | 0.105 | 1.235 | -0.125 | 0.1741 | 0.1294 |
| threat_level | task | POOLED | 1990 | 100 | scalar_baseline | -0.044 | -0.223 | 1.231 | nan | nan | nan |
| threat_level | task | POOLED | 1990 | 100 | scalar_plus_embedding | -0.060 | 0.095 | 1.240 | -0.128 | 0.1741 | 0.1592 |
| threat_level | forfeit | POOLED | 874 | 50 | embedding_masked | -0.032 | 0.172 | 1.114 | -0.213 | 0.0398 | 0.0597 |
| threat_level | forfeit | POOLED | 874 | 50 | embedding_raw | 0.464 | 0.721 | 0.788 | -0.220 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 874 | 50 | scalar_baseline | -0.052 | -0.008 | 1.137 | nan | nan | nan |
| threat_level | forfeit | POOLED | 874 | 50 | scalar_plus_embedding | 0.460 | 0.718 | 0.790 | -0.227 | 0.0050 | 0.0050 |
| threat_level | task | gpt-oss-120b-cloud | 1990 | 100 | embedding_masked | -0.068 | 0.076 | 1.243 | -0.125 | 0.2239 | 0.2090 |
| threat_level | task | gpt-oss-120b-cloud | 1990 | 100 | embedding_raw | -0.055 | 0.105 | 1.235 | -0.125 | 0.1741 | 0.1294 |
| threat_level | task | gpt-oss-120b-cloud | 1990 | 100 | scalar_baseline | -0.044 | -0.223 | 1.231 | nan | nan | nan |
| threat_level | task | gpt-oss-120b-cloud | 1990 | 100 | scalar_plus_embedding | -0.060 | 0.095 | 1.240 | -0.128 | 0.1741 | 0.1592 |
| threat_level | forfeit | gpt-oss-120b-cloud | 874 | 50 | embedding_masked | -0.032 | 0.172 | 1.114 | -0.213 | 0.0398 | 0.0597 |
| threat_level | forfeit | gpt-oss-120b-cloud | 874 | 50 | embedding_raw | 0.464 | 0.721 | 0.788 | -0.220 | 0.0050 | 0.0050 |
| threat_level | forfeit | gpt-oss-120b-cloud | 874 | 50 | scalar_baseline | -0.052 | -0.008 | 1.137 | nan | nan | nan |
| threat_level | forfeit | gpt-oss-120b-cloud | 874 | 50 | scalar_plus_embedding | 0.460 | 0.718 | 0.790 | -0.227 | 0.0050 | 0.0050 |


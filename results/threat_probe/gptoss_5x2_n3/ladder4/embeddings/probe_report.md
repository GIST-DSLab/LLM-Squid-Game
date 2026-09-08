# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 1607 | 80 | embedding_masked | -0.184 | -0.024 | 1.044 | -0.158 | 0.6517 | 0.4279 |
| threat_level | task | POOLED | 1607 | 80 | embedding_raw | -0.171 | -0.001 | 1.039 | -0.158 | 0.5622 | 0.3582 |
| threat_level | task | POOLED | 1607 | 80 | scalar_baseline | -0.098 | -0.367 | 1.043 | nan | nan | nan |
| threat_level | task | POOLED | 1607 | 80 | scalar_plus_embedding | -0.187 | -0.020 | 1.046 | -0.164 | 0.6468 | 0.4030 |
| threat_level | forfeit | POOLED | 649 | 40 | embedding_masked | -0.136 | 0.091 | 0.973 | -0.254 | 0.1891 | 0.1642 |
| threat_level | forfeit | POOLED | 649 | 40 | embedding_raw | 0.308 | 0.558 | 0.740 | -0.268 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 649 | 40 | scalar_baseline | -0.045 | -0.148 | 0.944 | nan | nan | nan |
| threat_level | forfeit | POOLED | 649 | 40 | scalar_plus_embedding | 0.297 | 0.552 | 0.744 | -0.279 | 0.0050 | 0.0050 |
| threat_level | task | gpt-oss-120b-cloud | 1607 | 80 | embedding_masked | -0.184 | -0.024 | 1.044 | -0.158 | 0.6517 | 0.4279 |
| threat_level | task | gpt-oss-120b-cloud | 1607 | 80 | embedding_raw | -0.171 | -0.001 | 1.039 | -0.158 | 0.5622 | 0.3582 |
| threat_level | task | gpt-oss-120b-cloud | 1607 | 80 | scalar_baseline | -0.098 | -0.367 | 1.043 | nan | nan | nan |
| threat_level | task | gpt-oss-120b-cloud | 1607 | 80 | scalar_plus_embedding | -0.187 | -0.020 | 1.046 | -0.164 | 0.6468 | 0.4030 |
| threat_level | forfeit | gpt-oss-120b-cloud | 649 | 40 | embedding_masked | -0.136 | 0.091 | 0.973 | -0.254 | 0.1891 | 0.1642 |
| threat_level | forfeit | gpt-oss-120b-cloud | 649 | 40 | embedding_raw | 0.308 | 0.558 | 0.740 | -0.268 | 0.0050 | 0.0050 |
| threat_level | forfeit | gpt-oss-120b-cloud | 649 | 40 | scalar_baseline | -0.045 | -0.148 | 0.944 | nan | nan | nan |
| threat_level | forfeit | gpt-oss-120b-cloud | 649 | 40 | scalar_plus_embedding | 0.297 | 0.552 | 0.744 | -0.279 | 0.0050 | 0.0050 |


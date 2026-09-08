# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 2116 | 80 | embedding_masked | 0.238 | 0.499 | 0.808 | -0.131 | 0.0050 | 0.0050 |
| threat_level | task | POOLED | 2116 | 80 | embedding_raw | 0.259 | 0.525 | 0.797 | -0.132 | 0.0050 | 0.0050 |
| threat_level | task | POOLED | 2116 | 80 | scalar_baseline | -0.049 | 0.007 | 1.001 | nan | nan | nan |
| threat_level | task | POOLED | 2116 | 80 | scalar_plus_embedding | 0.256 | 0.524 | 0.799 | -0.137 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 1024 | 40 | embedding_masked | 0.343 | 0.570 | 0.728 | -0.218 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 1024 | 40 | embedding_raw | 0.432 | 0.631 | 0.681 | -0.236 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 1024 | 40 | scalar_baseline | -0.134 | -0.055 | 1.013 | nan | nan | nan |
| threat_level | forfeit | POOLED | 1024 | 40 | scalar_plus_embedding | 0.440 | 0.636 | 0.675 | -0.245 | 0.0050 | 0.0050 |
| threat_level | task | glm-5.3-flash | 2116 | 80 | embedding_masked | 0.238 | 0.499 | 0.808 | -0.131 | 0.0050 | 0.0050 |
| threat_level | task | glm-5.3-flash | 2116 | 80 | embedding_raw | 0.259 | 0.525 | 0.797 | -0.132 | 0.0050 | 0.0050 |
| threat_level | task | glm-5.3-flash | 2116 | 80 | scalar_baseline | -0.049 | 0.007 | 1.001 | nan | nan | nan |
| threat_level | task | glm-5.3-flash | 2116 | 80 | scalar_plus_embedding | 0.256 | 0.524 | 0.799 | -0.137 | 0.0050 | 0.0050 |
| threat_level | forfeit | glm-5.3-flash | 1024 | 40 | embedding_masked | 0.343 | 0.570 | 0.728 | -0.218 | 0.0050 | 0.0050 |
| threat_level | forfeit | glm-5.3-flash | 1024 | 40 | embedding_raw | 0.432 | 0.631 | 0.681 | -0.236 | 0.0050 | 0.0050 |
| threat_level | forfeit | glm-5.3-flash | 1024 | 40 | scalar_baseline | -0.134 | -0.055 | 1.013 | nan | nan | nan |
| threat_level | forfeit | glm-5.3-flash | 1024 | 40 | scalar_plus_embedding | 0.440 | 0.636 | 0.675 | -0.245 | 0.0050 | 0.0050 |


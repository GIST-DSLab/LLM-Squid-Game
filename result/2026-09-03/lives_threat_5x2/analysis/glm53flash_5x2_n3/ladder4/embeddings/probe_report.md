# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 637 | 24 | embedding_masked | -0.002 | 0.252 | 1.005 | -0.256 | 0.0498 | 0.0448 |
| threat_level | task | POOLED | 637 | 24 | embedding_raw | 0.043 | 0.308 | 0.980 | -0.261 | 0.0199 | 0.0199 |
| threat_level | task | POOLED | 637 | 24 | scalar_baseline | -0.162 | -0.099 | 1.131 | nan | nan | nan |
| threat_level | task | POOLED | 637 | 24 | scalar_plus_embedding | 0.053 | 0.330 | 0.968 | -0.271 | 0.0199 | 0.0199 |
| threat_level | forfeit | POOLED | 320 | 12 | embedding_masked | 0.092 | 0.329 | 0.947 | -0.483 | 0.0498 | 0.0796 |
| threat_level | forfeit | POOLED | 320 | 12 | embedding_raw | 0.308 | 0.503 | 0.832 | -0.555 | 0.0100 | 0.0249 |
| threat_level | forfeit | POOLED | 320 | 12 | scalar_baseline | -0.381 | -0.461 | 1.189 | nan | nan | nan |
| threat_level | forfeit | POOLED | 320 | 12 | scalar_plus_embedding | 0.310 | 0.504 | 0.832 | -0.566 | 0.0100 | 0.0199 |
| threat_level | task | glm-5.3-flash | 637 | 24 | embedding_masked | -0.002 | 0.252 | 1.005 | -0.256 | 0.0498 | 0.0448 |
| threat_level | task | glm-5.3-flash | 637 | 24 | embedding_raw | 0.043 | 0.308 | 0.980 | -0.261 | 0.0199 | 0.0199 |
| threat_level | task | glm-5.3-flash | 637 | 24 | scalar_baseline | -0.162 | -0.099 | 1.131 | nan | nan | nan |
| threat_level | task | glm-5.3-flash | 637 | 24 | scalar_plus_embedding | 0.053 | 0.330 | 0.968 | -0.271 | 0.0199 | 0.0199 |
| threat_level | forfeit | glm-5.3-flash | 320 | 12 | embedding_masked | 0.092 | 0.329 | 0.947 | -0.483 | 0.0498 | 0.0796 |
| threat_level | forfeit | glm-5.3-flash | 320 | 12 | embedding_raw | 0.308 | 0.503 | 0.832 | -0.555 | 0.0100 | 0.0249 |
| threat_level | forfeit | glm-5.3-flash | 320 | 12 | scalar_baseline | -0.381 | -0.461 | 1.189 | nan | nan | nan |
| threat_level | forfeit | glm-5.3-flash | 320 | 12 | scalar_plus_embedding | 0.310 | 0.504 | 0.832 | -0.566 | 0.0100 | 0.0199 |


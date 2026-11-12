# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 802 | 30 | embedding_masked | 0.134 | 0.424 | 1.133 | -0.214 | 0.0100 | 0.0050 |
| threat_level | task | POOLED | 802 | 30 | embedding_raw | 0.190 | 0.483 | 1.095 | -0.220 | 0.0050 | 0.0050 |
| threat_level | task | POOLED | 802 | 30 | scalar_baseline | -0.218 | -0.211 | 1.401 | nan | nan | nan |
| threat_level | task | POOLED | 802 | 30 | scalar_plus_embedding | 0.191 | 0.488 | 1.095 | -0.225 | 0.0100 | 0.0050 |
| threat_level | forfeit | POOLED | 395 | 15 | embedding_masked | 0.355 | 0.602 | 0.980 | -0.442 | 0.0100 | 0.0050 |
| threat_level | forfeit | POOLED | 395 | 15 | embedding_raw | 0.602 | 0.766 | 0.768 | -0.475 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 395 | 15 | scalar_baseline | -0.258 | -0.435 | 1.487 | nan | nan | nan |
| threat_level | forfeit | POOLED | 395 | 15 | scalar_plus_embedding | 0.589 | 0.759 | 0.779 | -0.482 | 0.0050 | 0.0050 |
| threat_level | task | glm-5.3-flash | 802 | 30 | embedding_masked | 0.134 | 0.424 | 1.133 | -0.214 | 0.0100 | 0.0050 |
| threat_level | task | glm-5.3-flash | 802 | 30 | embedding_raw | 0.190 | 0.483 | 1.095 | -0.220 | 0.0050 | 0.0050 |
| threat_level | task | glm-5.3-flash | 802 | 30 | scalar_baseline | -0.218 | -0.211 | 1.401 | nan | nan | nan |
| threat_level | task | glm-5.3-flash | 802 | 30 | scalar_plus_embedding | 0.191 | 0.488 | 1.095 | -0.225 | 0.0100 | 0.0050 |
| threat_level | forfeit | glm-5.3-flash | 395 | 15 | embedding_masked | 0.355 | 0.602 | 0.980 | -0.442 | 0.0100 | 0.0050 |
| threat_level | forfeit | glm-5.3-flash | 395 | 15 | embedding_raw | 0.602 | 0.766 | 0.768 | -0.475 | 0.0050 | 0.0050 |
| threat_level | forfeit | glm-5.3-flash | 395 | 15 | scalar_baseline | -0.258 | -0.435 | 1.487 | nan | nan | nan |
| threat_level | forfeit | glm-5.3-flash | 395 | 15 | scalar_plus_embedding | 0.589 | 0.759 | 0.779 | -0.482 | 0.0050 | 0.0050 |


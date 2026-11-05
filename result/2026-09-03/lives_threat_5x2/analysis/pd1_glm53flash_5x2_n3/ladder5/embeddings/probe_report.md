# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 2538 | 100 | embedding_masked | 0.303 | 0.565 | 0.982 | -0.115 | 0.0050 | 0.0050 |
| threat_level | task | POOLED | 2538 | 100 | embedding_raw | 0.328 | 0.593 | 0.964 | -0.116 | 0.0050 | 0.0050 |
| threat_level | task | POOLED | 2538 | 100 | scalar_baseline | -0.036 | 0.028 | 1.241 | nan | nan | nan |
| threat_level | task | POOLED | 2538 | 100 | scalar_plus_embedding | 0.329 | 0.593 | 0.962 | -0.120 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 1166 | 50 | embedding_masked | 0.472 | 0.684 | 0.831 | -0.192 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 1166 | 50 | embedding_raw | 0.618 | 0.749 | 0.719 | -0.204 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 1166 | 50 | scalar_baseline | -0.099 | -0.040 | 1.293 | nan | nan | nan |
| threat_level | forfeit | POOLED | 1166 | 50 | scalar_plus_embedding | 0.625 | 0.754 | 0.709 | -0.212 | 0.0050 | 0.0050 |
| threat_level | task | glm-5.3-flash | 2538 | 100 | embedding_masked | 0.303 | 0.565 | 0.982 | -0.115 | 0.0050 | 0.0050 |
| threat_level | task | glm-5.3-flash | 2538 | 100 | embedding_raw | 0.328 | 0.593 | 0.964 | -0.116 | 0.0050 | 0.0050 |
| threat_level | task | glm-5.3-flash | 2538 | 100 | scalar_baseline | -0.036 | 0.028 | 1.241 | nan | nan | nan |
| threat_level | task | glm-5.3-flash | 2538 | 100 | scalar_plus_embedding | 0.329 | 0.593 | 0.962 | -0.120 | 0.0050 | 0.0050 |
| threat_level | forfeit | glm-5.3-flash | 1166 | 50 | embedding_masked | 0.472 | 0.684 | 0.831 | -0.192 | 0.0050 | 0.0050 |
| threat_level | forfeit | glm-5.3-flash | 1166 | 50 | embedding_raw | 0.618 | 0.749 | 0.719 | -0.204 | 0.0050 | 0.0050 |
| threat_level | forfeit | glm-5.3-flash | 1166 | 50 | scalar_baseline | -0.099 | -0.040 | 1.293 | nan | nan | nan |
| threat_level | forfeit | glm-5.3-flash | 1166 | 50 | scalar_plus_embedding | 0.625 | 0.754 | 0.709 | -0.212 | 0.0050 | 0.0050 |


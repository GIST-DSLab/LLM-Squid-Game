# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 1958 | 166 | embedding_masked | 0.003 | 0.209 | 0.693 | -0.071 | 0.0476 | 0.0476 |
| threat_level | task | POOLED | 1958 | 166 | embedding_raw | 0.002 | 0.208 | 0.694 | -0.071 | 0.0476 | 0.0476 |
| threat_level | task | POOLED | 1958 | 166 | scalar_baseline | 0.124 | 0.390 | 0.658 | nan | nan | nan |
| threat_level | task | POOLED | 1958 | 166 | scalar_plus_embedding | 0.110 | 0.350 | 0.655 | -0.072 | 0.0476 | 0.0476 |
| threat_level | forfeit | POOLED | 1553 | 139 | embedding_masked | 0.696 | 0.738 | 0.366 | -0.089 | 0.0476 | 0.0476 |
| threat_level | forfeit | POOLED | 1553 | 139 | embedding_raw | 0.719 | 0.761 | 0.347 | -0.087 | 0.0476 | 0.0476 |
| threat_level | forfeit | POOLED | 1553 | 139 | scalar_baseline | 0.072 | 0.262 | 0.628 | nan | nan | nan |
| threat_level | forfeit | POOLED | 1553 | 139 | scalar_plus_embedding | 0.719 | 0.761 | 0.347 | -0.089 | 0.0476 | 0.0476 |
| threat_level | task | nemotron-3-nano-30b-cloud | 1958 | 166 | embedding_masked | 0.003 | 0.209 | 0.693 | -0.071 | 0.0476 | 0.0476 |
| threat_level | task | nemotron-3-nano-30b-cloud | 1958 | 166 | embedding_raw | 0.002 | 0.208 | 0.694 | -0.071 | 0.0476 | 0.0476 |
| threat_level | task | nemotron-3-nano-30b-cloud | 1958 | 166 | scalar_baseline | 0.124 | 0.390 | 0.658 | nan | nan | nan |
| threat_level | task | nemotron-3-nano-30b-cloud | 1958 | 166 | scalar_plus_embedding | 0.110 | 0.350 | 0.655 | -0.072 | 0.0476 | 0.0476 |
| threat_level | forfeit | nemotron-3-nano-30b-cloud | 1553 | 139 | embedding_masked | 0.696 | 0.738 | 0.366 | -0.089 | 0.0476 | 0.0476 |
| threat_level | forfeit | nemotron-3-nano-30b-cloud | 1553 | 139 | embedding_raw | 0.719 | 0.761 | 0.347 | -0.087 | 0.0476 | 0.0476 |
| threat_level | forfeit | nemotron-3-nano-30b-cloud | 1553 | 139 | scalar_baseline | 0.072 | 0.262 | 0.628 | nan | nan | nan |
| threat_level | forfeit | nemotron-3-nano-30b-cloud | 1553 | 139 | scalar_plus_embedding | 0.719 | 0.761 | 0.347 | -0.089 | 0.0476 | 0.0476 |


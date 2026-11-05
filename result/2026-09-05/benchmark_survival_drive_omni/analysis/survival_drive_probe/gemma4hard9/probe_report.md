# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| sdi | forfeit | POOLED | 862 | 110 | embedding_masked | 0.562 | 0.506 | 0.536 | -0.040 | 0.0050 | 0.0050 |
| sdi | forfeit | POOLED | 862 | 110 | embedding_raw | 0.621 | 0.507 | 0.494 | -0.026 | 0.0050 | 0.0050 |
| sdi | forfeit | POOLED | 862 | 110 | scalar_baseline | 0.449 | 0.507 | 0.633 | nan | nan | nan |
| sdi | forfeit | POOLED | 862 | 110 | scalar_plus_embedding | 0.659 | 0.508 | 0.459 | -0.017 | 0.0050 | 0.0050 |
| sdi | task | POOLED | 782 | 110 | embedding_masked | -0.053 | 0.027 | 0.050 | -0.036 | 0.9398 | 0.2481 |
| sdi | task | POOLED | 782 | 110 | embedding_raw | -0.049 | 0.018 | 0.048 | -0.037 | 0.9248 | 0.2857 |
| sdi | task | POOLED | 782 | 110 | scalar_baseline | 0.004 | 0.068 | 0.038 | nan | nan | nan |
| sdi | task | POOLED | 782 | 110 | scalar_plus_embedding | -0.043 | 0.060 | 0.052 | -0.038 | 0.8045 | 0.0602 |
| sdi | forfeit_task | POOLED | 862 | 110 | embedding_masked | 0.732 | 0.497 | 0.260 | -0.027 | 0.0050 | 0.0050 |
| sdi | forfeit_task | POOLED | 862 | 110 | embedding_raw | 0.746 | 0.495 | 0.296 | -0.028 | 0.0050 | 0.0050 |
| sdi | forfeit_task | POOLED | 862 | 110 | scalar_baseline | 0.413 | 0.507 | 0.675 | nan | nan | nan |
| sdi | forfeit_task | POOLED | 862 | 110 | scalar_plus_embedding | 0.745 | 0.496 | 0.299 | -0.005 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 862 | 110 | embedding_masked | 0.095 | 0.356 | 0.675 | -0.044 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 862 | 110 | embedding_raw | 0.109 | 0.362 | 0.692 | -0.041 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 862 | 110 | scalar_baseline | 0.419 | 0.508 | 0.673 | nan | nan | nan |
| sdi | confidence | POOLED | 862 | 110 | scalar_plus_embedding | 0.367 | 0.495 | 0.678 | -0.025 | 0.0050 | 0.0050 |


# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| sdi | forfeit | POOLED | 1067 | 110 | embedding_masked | 0.097 | 0.166 | 0.062 | -0.047 | 0.0050 | 0.0050 |
| sdi | forfeit | POOLED | 1067 | 110 | embedding_raw | 0.150 | 0.160 | 0.063 | -0.044 | 0.0050 | 0.0050 |
| sdi | forfeit | POOLED | 1067 | 110 | scalar_baseline | 0.068 | 0.165 | 0.056 | nan | nan | nan |
| sdi | forfeit | POOLED | 1067 | 110 | scalar_plus_embedding | 0.201 | 0.167 | 0.073 | -0.044 | 0.0050 | 0.0050 |
| sdi | task | POOLED | 1058 | 110 | embedding_masked | nan | nan | nan | nan | nan | nan |
| sdi | task | POOLED | 1058 | 110 | embedding_raw | nan | nan | nan | nan | nan | nan |
| sdi | task | POOLED | 1058 | 110 | scalar_baseline | nan | nan | nan | nan | nan | nan |
| sdi | task | POOLED | 1058 | 110 | scalar_plus_embedding | nan | nan | nan | nan | nan | nan |
| sdi | forfeit_task | POOLED | 1067 | 110 | embedding_masked | 0.522 | 0.145 | 0.051 | -0.036 | 0.0050 | 0.0050 |
| sdi | forfeit_task | POOLED | 1067 | 110 | embedding_raw | 0.460 | 0.144 | 0.054 | -0.036 | 0.0050 | 0.0050 |
| sdi | forfeit_task | POOLED | 1067 | 110 | scalar_baseline | 0.083 | 0.167 | 0.055 | nan | nan | nan |
| sdi | forfeit_task | POOLED | 1067 | 110 | scalar_plus_embedding | 0.465 | 0.153 | 0.054 | -0.036 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 1067 | 110 | embedding_masked | -0.039 | 0.056 | 0.057 | -0.049 | 0.2488 | 0.1244 |
| sdi | confidence | POOLED | 1067 | 110 | embedding_raw | 0.001 | 0.127 | 0.057 | -0.047 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 1067 | 110 | scalar_baseline | 0.082 | 0.167 | 0.055 | nan | nan | nan |
| sdi | confidence | POOLED | 1067 | 110 | scalar_plus_embedding | 0.037 | 0.158 | 0.059 | -0.047 | 0.0050 | 0.0050 |


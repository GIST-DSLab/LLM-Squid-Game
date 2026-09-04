# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| smi | forfeit | POOLED | 516 | 40 | embedding_masked | 0.155 | 0.392 | 0.112 | -0.072 | 0.0050 | 0.0050 |
| smi | forfeit | POOLED | 516 | 40 | embedding_raw | 0.189 | 0.394 | 0.107 | -0.078 | 0.0050 | 0.0050 |
| smi | forfeit | POOLED | 516 | 40 | scalar_baseline | 0.238 | 0.358 | 0.104 | nan | nan | nan |
| smi | forfeit | POOLED | 516 | 40 | scalar_plus_embedding | 0.258 | 0.399 | 0.114 | -0.078 | 0.0050 | 0.0050 |
| smi | task | POOLED | 501 | 39 | embedding_masked | 0.081 | 0.236 | 0.068 | -0.094 | 0.0050 | 0.0050 |
| smi | task | POOLED | 501 | 39 | embedding_raw | 0.087 | 0.233 | 0.066 | -0.096 | 0.0050 | 0.0050 |
| smi | task | POOLED | 501 | 39 | scalar_baseline | 0.094 | 0.277 | 0.065 | nan | nan | nan |
| smi | task | POOLED | 501 | 39 | scalar_plus_embedding | 0.096 | 0.225 | 0.069 | -0.096 | 0.0050 | 0.0050 |
| smi | forfeit_task | POOLED | 516 | 40 | embedding_masked | 0.232 | 0.408 | 0.105 | -0.084 | 0.0050 | 0.0050 |
| smi | forfeit_task | POOLED | 516 | 40 | embedding_raw | 0.209 | 0.403 | 0.101 | -0.084 | 0.0050 | 0.0050 |
| smi | forfeit_task | POOLED | 516 | 40 | scalar_baseline | 0.165 | 0.311 | 0.118 | nan | nan | nan |
| smi | forfeit_task | POOLED | 516 | 40 | scalar_plus_embedding | 0.246 | 0.388 | 0.107 | -0.084 | 0.0050 | 0.0050 |
| smi | confidence | POOLED | 516 | 40 | embedding_masked | 0.085 | 0.406 | 0.111 | -0.082 | 0.0050 | 0.0050 |
| smi | confidence | POOLED | 516 | 40 | embedding_raw | 0.093 | 0.394 | 0.107 | -0.082 | 0.0050 | 0.0050 |
| smi | confidence | POOLED | 516 | 40 | scalar_baseline | 0.144 | 0.305 | 0.120 | nan | nan | nan |
| smi | confidence | POOLED | 516 | 40 | scalar_plus_embedding | 0.126 | 0.384 | 0.121 | -0.082 | 0.0050 | 0.0050 |


# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 2444 | 100 | embedding_masked | -0.061 | -0.057 | 1.278 | -0.062 | 0.5075 | 0.4776 |
| threat_level | task | POOLED | 2444 | 100 | embedding_raw | -0.060 | -0.055 | 1.278 | -0.062 | 0.5025 | 0.4577 |
| threat_level | task | POOLED | 2444 | 100 | scalar_baseline | -0.037 | -0.244 | 1.266 | nan | nan | nan |
| threat_level | task | POOLED | 2444 | 100 | scalar_plus_embedding | -0.066 | -0.066 | 1.281 | -0.066 | 0.5124 | 0.5373 |
| threat_level | forfeit | POOLED | 1186 | 50 | embedding_masked | -0.044 | 0.025 | 1.244 | -0.092 | 0.0945 | 0.0348 |
| threat_level | forfeit | POOLED | 1186 | 50 | embedding_raw | -0.040 | 0.034 | 1.236 | -0.097 | 0.0547 | 0.0249 |
| threat_level | forfeit | POOLED | 1186 | 50 | scalar_baseline | -0.054 | -0.235 | 1.250 | nan | nan | nan |
| threat_level | forfeit | POOLED | 1186 | 50 | scalar_plus_embedding | -0.044 | 0.029 | 1.239 | -0.104 | 0.0647 | 0.0846 |
| threat_level | task | gpt-5.6-luna | 2444 | 100 | embedding_masked | -0.061 | -0.057 | 1.278 | -0.062 | 0.5075 | 0.4776 |
| threat_level | task | gpt-5.6-luna | 2444 | 100 | embedding_raw | -0.060 | -0.055 | 1.278 | -0.062 | 0.5025 | 0.4577 |
| threat_level | task | gpt-5.6-luna | 2444 | 100 | scalar_baseline | -0.037 | -0.244 | 1.266 | nan | nan | nan |
| threat_level | task | gpt-5.6-luna | 2444 | 100 | scalar_plus_embedding | -0.066 | -0.066 | 1.281 | -0.066 | 0.5124 | 0.5373 |
| threat_level | forfeit | gpt-5.6-luna | 1186 | 50 | embedding_masked | -0.044 | 0.025 | 1.244 | -0.092 | 0.0945 | 0.0348 |
| threat_level | forfeit | gpt-5.6-luna | 1186 | 50 | embedding_raw | -0.040 | 0.034 | 1.236 | -0.097 | 0.0547 | 0.0249 |
| threat_level | forfeit | gpt-5.6-luna | 1186 | 50 | scalar_baseline | -0.054 | -0.235 | 1.250 | nan | nan | nan |
| threat_level | forfeit | gpt-5.6-luna | 1186 | 50 | scalar_plus_embedding | -0.044 | 0.029 | 1.239 | -0.104 | 0.0647 | 0.0846 |


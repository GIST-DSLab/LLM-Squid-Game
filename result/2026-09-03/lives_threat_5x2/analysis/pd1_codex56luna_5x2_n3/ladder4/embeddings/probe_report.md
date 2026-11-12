# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 1936 | 80 | embedding_masked | -0.047 | -0.033 | 1.025 | -0.074 | 0.1443 | 0.2836 |
| threat_level | task | POOLED | 1936 | 80 | embedding_raw | -0.047 | -0.033 | 1.025 | -0.074 | 0.1443 | 0.2935 |
| threat_level | task | POOLED | 1936 | 80 | scalar_baseline | -0.015 | -0.104 | 1.023 | nan | nan | nan |
| threat_level | task | POOLED | 1936 | 80 | scalar_plus_embedding | -0.048 | -0.034 | 1.023 | -0.079 | 0.1542 | 0.3184 |
| threat_level | forfeit | POOLED | 932 | 40 | embedding_masked | -0.089 | -0.064 | 1.023 | -0.112 | 0.3682 | 0.2537 |
| threat_level | forfeit | POOLED | 932 | 40 | embedding_raw | -0.084 | -0.040 | 1.017 | -0.116 | 0.3134 | 0.2388 |
| threat_level | forfeit | POOLED | 932 | 40 | scalar_baseline | -0.141 | -0.443 | 1.061 | nan | nan | nan |
| threat_level | forfeit | POOLED | 932 | 40 | scalar_plus_embedding | -0.101 | -0.069 | 1.025 | -0.121 | 0.3980 | 0.3134 |
| threat_level | task | gpt-5.6-luna | 1936 | 80 | embedding_masked | -0.047 | -0.033 | 1.025 | -0.074 | 0.1443 | 0.2836 |
| threat_level | task | gpt-5.6-luna | 1936 | 80 | embedding_raw | -0.047 | -0.033 | 1.025 | -0.074 | 0.1443 | 0.2935 |
| threat_level | task | gpt-5.6-luna | 1936 | 80 | scalar_baseline | -0.015 | -0.104 | 1.023 | nan | nan | nan |
| threat_level | task | gpt-5.6-luna | 1936 | 80 | scalar_plus_embedding | -0.048 | -0.034 | 1.023 | -0.079 | 0.1542 | 0.3184 |
| threat_level | forfeit | gpt-5.6-luna | 932 | 40 | embedding_masked | -0.089 | -0.064 | 1.023 | -0.112 | 0.3682 | 0.2537 |
| threat_level | forfeit | gpt-5.6-luna | 932 | 40 | embedding_raw | -0.084 | -0.040 | 1.017 | -0.116 | 0.3134 | 0.2388 |
| threat_level | forfeit | gpt-5.6-luna | 932 | 40 | scalar_baseline | -0.141 | -0.443 | 1.061 | nan | nan | nan |
| threat_level | forfeit | gpt-5.6-luna | 932 | 40 | scalar_plus_embedding | -0.101 | -0.069 | 1.025 | -0.121 | 0.3980 | 0.3134 |


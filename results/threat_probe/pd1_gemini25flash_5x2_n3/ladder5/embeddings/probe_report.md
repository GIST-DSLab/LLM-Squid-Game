# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 2658 | 100 | embedding_masked | 0.235 | 0.509 | 0.989 | -0.116 | 0.0050 | 0.0050 |
| threat_level | task | POOLED | 2658 | 100 | embedding_raw | 0.222 | 0.506 | 1.008 | -0.115 | 0.0050 | 0.0050 |
| threat_level | task | POOLED | 2658 | 100 | scalar_baseline | -0.003 | 0.067 | 1.180 | nan | nan | nan |
| threat_level | task | POOLED | 2658 | 100 | scalar_plus_embedding | 0.223 | 0.508 | 1.006 | -0.119 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 1158 | 50 | embedding_masked | 0.157 | 0.439 | 0.994 | -0.172 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 1158 | 50 | embedding_raw | 0.487 | 0.705 | 0.768 | -0.183 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 1158 | 50 | scalar_baseline | -0.093 | -0.254 | 1.176 | nan | nan | nan |
| threat_level | forfeit | POOLED | 1158 | 50 | scalar_plus_embedding | 0.485 | 0.704 | 0.770 | -0.189 | 0.0050 | 0.0050 |
| threat_level | task | gemini-2.5-flash | 2658 | 100 | embedding_masked | 0.235 | 0.509 | 0.989 | -0.116 | 0.0050 | 0.0050 |
| threat_level | task | gemini-2.5-flash | 2658 | 100 | embedding_raw | 0.222 | 0.506 | 1.008 | -0.115 | 0.0050 | 0.0050 |
| threat_level | task | gemini-2.5-flash | 2658 | 100 | scalar_baseline | -0.003 | 0.067 | 1.180 | nan | nan | nan |
| threat_level | task | gemini-2.5-flash | 2658 | 100 | scalar_plus_embedding | 0.223 | 0.508 | 1.006 | -0.119 | 0.0050 | 0.0050 |
| threat_level | forfeit | gemini-2.5-flash | 1158 | 50 | embedding_masked | 0.157 | 0.439 | 0.994 | -0.172 | 0.0050 | 0.0050 |
| threat_level | forfeit | gemini-2.5-flash | 1158 | 50 | embedding_raw | 0.487 | 0.705 | 0.768 | -0.183 | 0.0050 | 0.0050 |
| threat_level | forfeit | gemini-2.5-flash | 1158 | 50 | scalar_baseline | -0.093 | -0.254 | 1.176 | nan | nan | nan |
| threat_level | forfeit | gemini-2.5-flash | 1158 | 50 | scalar_plus_embedding | 0.485 | 0.704 | 0.770 | -0.189 | 0.0050 | 0.0050 |


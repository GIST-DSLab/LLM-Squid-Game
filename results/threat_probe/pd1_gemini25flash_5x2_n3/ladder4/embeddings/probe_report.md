# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 2067 | 80 | embedding_masked | 0.091 | 0.317 | 0.890 | -0.135 | 0.0050 | 0.0050 |
| threat_level | task | POOLED | 2067 | 80 | embedding_raw | 0.087 | 0.313 | 0.896 | -0.135 | 0.0050 | 0.0050 |
| threat_level | task | POOLED | 2067 | 80 | scalar_baseline | -0.052 | -0.141 | 0.996 | nan | nan | nan |
| threat_level | task | POOLED | 2067 | 80 | scalar_plus_embedding | 0.080 | 0.306 | 0.900 | -0.140 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 867 | 40 | embedding_masked | 0.075 | 0.313 | 0.865 | -0.206 | 0.0100 | 0.0100 |
| threat_level | forfeit | POOLED | 867 | 40 | embedding_raw | 0.291 | 0.486 | 0.753 | -0.219 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 867 | 40 | scalar_baseline | -0.128 | -0.272 | 0.978 | nan | nan | nan |
| threat_level | forfeit | POOLED | 867 | 40 | scalar_plus_embedding | 0.285 | 0.479 | 0.755 | -0.230 | 0.0050 | 0.0050 |
| threat_level | task | gemini-2.5-flash | 2067 | 80 | embedding_masked | 0.091 | 0.317 | 0.890 | -0.135 | 0.0050 | 0.0050 |
| threat_level | task | gemini-2.5-flash | 2067 | 80 | embedding_raw | 0.087 | 0.313 | 0.896 | -0.135 | 0.0050 | 0.0050 |
| threat_level | task | gemini-2.5-flash | 2067 | 80 | scalar_baseline | -0.052 | -0.141 | 0.996 | nan | nan | nan |
| threat_level | task | gemini-2.5-flash | 2067 | 80 | scalar_plus_embedding | 0.080 | 0.306 | 0.900 | -0.140 | 0.0050 | 0.0050 |
| threat_level | forfeit | gemini-2.5-flash | 867 | 40 | embedding_masked | 0.075 | 0.313 | 0.865 | -0.206 | 0.0100 | 0.0100 |
| threat_level | forfeit | gemini-2.5-flash | 867 | 40 | embedding_raw | 0.291 | 0.486 | 0.753 | -0.219 | 0.0050 | 0.0050 |
| threat_level | forfeit | gemini-2.5-flash | 867 | 40 | scalar_baseline | -0.128 | -0.272 | 0.978 | nan | nan | nan |
| threat_level | forfeit | gemini-2.5-flash | 867 | 40 | scalar_plus_embedding | 0.285 | 0.479 | 0.755 | -0.230 | 0.0050 | 0.0050 |


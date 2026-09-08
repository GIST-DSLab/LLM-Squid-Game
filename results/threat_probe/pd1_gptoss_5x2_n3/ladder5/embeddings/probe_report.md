# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 1998 | 100 | embedding_masked | -0.176 | -0.053 | 1.306 | -0.137 | 0.7413 | 0.4925 |
| threat_level | task | POOLED | 1998 | 100 | embedding_raw | -0.177 | -0.055 | 1.307 | -0.137 | 0.7512 | 0.4975 |
| threat_level | task | POOLED | 1998 | 100 | scalar_baseline | -0.060 | -0.331 | 1.239 | nan | nan | nan |
| threat_level | task | POOLED | 1998 | 100 | scalar_plus_embedding | -0.183 | -0.062 | 1.310 | -0.140 | 0.7463 | 0.5274 |
| threat_level | forfeit | POOLED | 930 | 50 | embedding_masked | -0.117 | 0.032 | 1.250 | -0.197 | 0.2438 | 0.2786 |
| threat_level | forfeit | POOLED | 930 | 50 | embedding_raw | 0.361 | 0.624 | 0.885 | -0.211 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 930 | 50 | scalar_baseline | -0.039 | -0.230 | 1.198 | nan | nan | nan |
| threat_level | forfeit | POOLED | 930 | 50 | scalar_plus_embedding | 0.361 | 0.623 | 0.884 | -0.218 | 0.0050 | 0.0050 |
| threat_level | task | gpt-oss-120b-cloud | 1998 | 100 | embedding_masked | -0.176 | -0.053 | 1.306 | -0.137 | 0.7413 | 0.4925 |
| threat_level | task | gpt-oss-120b-cloud | 1998 | 100 | embedding_raw | -0.177 | -0.055 | 1.307 | -0.137 | 0.7512 | 0.4975 |
| threat_level | task | gpt-oss-120b-cloud | 1998 | 100 | scalar_baseline | -0.060 | -0.331 | 1.239 | nan | nan | nan |
| threat_level | task | gpt-oss-120b-cloud | 1998 | 100 | scalar_plus_embedding | -0.183 | -0.062 | 1.310 | -0.140 | 0.7463 | 0.5274 |
| threat_level | forfeit | gpt-oss-120b-cloud | 930 | 50 | embedding_masked | -0.117 | 0.032 | 1.250 | -0.197 | 0.2438 | 0.2786 |
| threat_level | forfeit | gpt-oss-120b-cloud | 930 | 50 | embedding_raw | 0.361 | 0.624 | 0.885 | -0.211 | 0.0050 | 0.0050 |
| threat_level | forfeit | gpt-oss-120b-cloud | 930 | 50 | scalar_baseline | -0.039 | -0.230 | 1.198 | nan | nan | nan |
| threat_level | forfeit | gpt-oss-120b-cloud | 930 | 50 | scalar_plus_embedding | 0.361 | 0.623 | 0.884 | -0.218 | 0.0050 | 0.0050 |


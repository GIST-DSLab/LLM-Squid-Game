# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 72 | 5 | embedding_masked | -2.482 | -0.816 | 1.801 | -1.641 | 0.7895 | 0.7895 |
| threat_level | task | POOLED | 72 | 5 | embedding_raw | -2.347 | -0.791 | 1.765 | -1.652 | 0.7895 | 0.7368 |
| threat_level | task | POOLED | 72 | 5 | scalar_baseline | -1.775 | -0.833 | 1.597 | nan | nan | nan |
| threat_level | task | POOLED | 72 | 5 | scalar_plus_embedding | -2.331 | -0.791 | 1.761 | -1.647 | 0.7368 | 0.7368 |
| threat_level | forfeit | POOLED | 42 | 4 | embedding_masked | -4.514 | -0.564 | 1.602 | -2.343 | 1.0000 | 0.5238 |
| threat_level | forfeit | POOLED | 42 | 4 | embedding_raw | -2.471 | -0.516 | 1.280 | -2.174 | 0.7143 | 0.2381 |
| threat_level | forfeit | POOLED | 42 | 4 | scalar_baseline | -3.433 | -0.565 | 1.469 | nan | nan | nan |
| threat_level | forfeit | POOLED | 42 | 4 | scalar_plus_embedding | -2.797 | -0.519 | 1.343 | -2.198 | 0.7143 | 0.2381 |
| threat_level | task | gpt-oss-120b-cloud | 72 | 5 | embedding_masked | -2.482 | -0.816 | 1.801 | -1.641 | 0.7895 | 0.7895 |
| threat_level | task | gpt-oss-120b-cloud | 72 | 5 | embedding_raw | -2.347 | -0.791 | 1.765 | -1.652 | 0.7895 | 0.7368 |
| threat_level | task | gpt-oss-120b-cloud | 72 | 5 | scalar_baseline | -1.775 | -0.833 | 1.597 | nan | nan | nan |
| threat_level | task | gpt-oss-120b-cloud | 72 | 5 | scalar_plus_embedding | -2.331 | -0.791 | 1.761 | -1.647 | 0.7368 | 0.7368 |
| threat_level | forfeit | gpt-oss-120b-cloud | 42 | 4 | embedding_masked | -4.514 | -0.564 | 1.602 | -2.343 | 1.0000 | 0.5238 |
| threat_level | forfeit | gpt-oss-120b-cloud | 42 | 4 | embedding_raw | -2.471 | -0.516 | 1.280 | -2.174 | 0.7143 | 0.2381 |
| threat_level | forfeit | gpt-oss-120b-cloud | 42 | 4 | scalar_baseline | -3.433 | -0.565 | 1.469 | nan | nan | nan |
| threat_level | forfeit | gpt-oss-120b-cloud | 42 | 4 | scalar_plus_embedding | -2.797 | -0.519 | 1.343 | -2.198 | 0.7143 | 0.2381 |


# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 48 | 5 | embedding_masked | -0.559 | -0.314 | 0.909 | -2.325 | 0.0980 | 0.1961 |
| threat_level | task | POOLED | 48 | 5 | embedding_raw | -0.483 | -0.030 | 0.857 | -2.261 | 0.0784 | 0.1176 |
| threat_level | task | POOLED | 48 | 5 | scalar_baseline | -27.223 | -0.683 | 3.751 | nan | nan | nan |
| threat_level | task | POOLED | 48 | 5 | scalar_plus_embedding | -0.484 | -0.033 | 0.857 | -2.669 | 0.0784 | 0.1765 |
| threat_level | forfeit | POOLED | 42 | 4 | embedding_masked | -1.193 | -0.409 | 1.228 | -2.812 | 0.0784 | 0.4902 |
| threat_level | forfeit | POOLED | 42 | 4 | embedding_raw | -1.806 | -0.466 | 1.536 | -2.448 | 0.3922 | 0.1373 |
| threat_level | forfeit | POOLED | 42 | 4 | scalar_baseline | -2.275 | -0.786 | 1.639 | nan | nan | nan |
| threat_level | forfeit | POOLED | 42 | 4 | scalar_plus_embedding | -1.676 | -0.466 | 1.496 | -3.119 | 0.3529 | 0.2745 |
| threat_level | task | gpt-oss-120b-cloud | 48 | 5 | embedding_masked | -0.559 | -0.314 | 0.909 | -2.325 | 0.0980 | 0.1961 |
| threat_level | task | gpt-oss-120b-cloud | 48 | 5 | embedding_raw | -0.483 | -0.030 | 0.857 | -2.261 | 0.0784 | 0.1176 |
| threat_level | task | gpt-oss-120b-cloud | 48 | 5 | scalar_baseline | -27.223 | -0.683 | 3.751 | nan | nan | nan |
| threat_level | task | gpt-oss-120b-cloud | 48 | 5 | scalar_plus_embedding | -0.484 | -0.033 | 0.857 | -2.669 | 0.0784 | 0.1765 |
| threat_level | forfeit | gpt-oss-120b-cloud | 42 | 4 | embedding_masked | -1.193 | -0.409 | 1.228 | -2.812 | 0.0784 | 0.4902 |
| threat_level | forfeit | gpt-oss-120b-cloud | 42 | 4 | embedding_raw | -1.806 | -0.466 | 1.536 | -2.448 | 0.3922 | 0.1373 |
| threat_level | forfeit | gpt-oss-120b-cloud | 42 | 4 | scalar_baseline | -2.275 | -0.786 | 1.639 | nan | nan | nan |
| threat_level | forfeit | gpt-oss-120b-cloud | 42 | 4 | scalar_plus_embedding | -1.676 | -0.466 | 1.496 | -3.119 | 0.3529 | 0.2745 |


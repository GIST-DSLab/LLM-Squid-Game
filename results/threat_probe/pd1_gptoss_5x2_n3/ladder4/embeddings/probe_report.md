# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| threat_level | task | POOLED | 1592 | 80 | embedding_masked | -0.043 | 0.143 | 0.981 | -0.158 | 0.0547 | 0.0547 |
| threat_level | task | POOLED | 1592 | 80 | embedding_raw | -0.043 | 0.142 | 0.981 | -0.158 | 0.0597 | 0.0597 |
| threat_level | task | POOLED | 1592 | 80 | scalar_baseline | -0.045 | -0.044 | 1.009 | nan | nan | nan |
| threat_level | task | POOLED | 1592 | 80 | scalar_plus_embedding | -0.039 | 0.152 | 0.978 | -0.163 | 0.0498 | 0.0498 |
| threat_level | forfeit | POOLED | 752 | 40 | embedding_masked | -0.164 | -0.030 | 0.988 | -0.246 | 0.2587 | 0.3532 |
| threat_level | forfeit | POOLED | 752 | 40 | embedding_raw | 0.222 | 0.489 | 0.777 | -0.257 | 0.0050 | 0.0050 |
| threat_level | forfeit | POOLED | 752 | 40 | scalar_baseline | -0.106 | -0.247 | 0.967 | nan | nan | nan |
| threat_level | forfeit | POOLED | 752 | 40 | scalar_plus_embedding | 0.230 | 0.498 | 0.772 | -0.268 | 0.0050 | 0.0050 |
| threat_level | task | gpt-oss-120b-cloud | 1592 | 80 | embedding_masked | -0.043 | 0.143 | 0.981 | -0.158 | 0.0547 | 0.0547 |
| threat_level | task | gpt-oss-120b-cloud | 1592 | 80 | embedding_raw | -0.043 | 0.142 | 0.981 | -0.158 | 0.0597 | 0.0597 |
| threat_level | task | gpt-oss-120b-cloud | 1592 | 80 | scalar_baseline | -0.045 | -0.044 | 1.009 | nan | nan | nan |
| threat_level | task | gpt-oss-120b-cloud | 1592 | 80 | scalar_plus_embedding | -0.039 | 0.152 | 0.978 | -0.163 | 0.0498 | 0.0498 |
| threat_level | forfeit | gpt-oss-120b-cloud | 752 | 40 | embedding_masked | -0.164 | -0.030 | 0.988 | -0.246 | 0.2587 | 0.3532 |
| threat_level | forfeit | gpt-oss-120b-cloud | 752 | 40 | embedding_raw | 0.222 | 0.489 | 0.777 | -0.257 | 0.0050 | 0.0050 |
| threat_level | forfeit | gpt-oss-120b-cloud | 752 | 40 | scalar_baseline | -0.106 | -0.247 | 0.967 | nan | nan | nan |
| threat_level | forfeit | gpt-oss-120b-cloud | 752 | 40 | scalar_plus_embedding | 0.230 | 0.498 | 0.772 | -0.268 | 0.0050 | 0.0050 |


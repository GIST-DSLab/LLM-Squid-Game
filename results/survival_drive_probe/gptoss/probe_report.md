# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| sdi | forfeit | POOLED | 627 | 40 | embedding_masked | 0.447 | 0.339 | 0.200 | -0.036 | 0.0050 | 0.0050 |
| sdi | forfeit | POOLED | 627 | 40 | embedding_raw | 0.577 | 0.333 | 0.184 | -0.025 | 0.0050 | 0.0050 |
| sdi | forfeit | POOLED | 627 | 40 | scalar_baseline | 0.253 | 0.445 | 0.231 | nan | nan | nan |
| sdi | forfeit | POOLED | 627 | 40 | scalar_plus_embedding | 0.618 | 0.349 | 0.180 | -0.015 | 0.0050 | 0.0050 |
| sdi | task | POOLED | 597 | 40 | embedding_masked | -0.033 | 0.107 | 0.066 | -0.055 | 0.1692 | 0.0597 |
| sdi | task | POOLED | 597 | 40 | embedding_raw | -0.052 | 0.081 | 0.067 | -0.056 | 0.3881 | 0.1443 |
| sdi | task | POOLED | 597 | 40 | scalar_baseline | 0.024 | 0.242 | 0.057 | nan | nan | nan |
| sdi | task | POOLED | 597 | 40 | scalar_plus_embedding | -0.040 | 0.136 | 0.067 | -0.055 | 0.2537 | 0.0299 |
| sdi | forfeit_task | POOLED | 627 | 40 | embedding_masked | 0.463 | 0.330 | 0.180 | -0.032 | 0.0050 | 0.0050 |
| sdi | forfeit_task | POOLED | 627 | 40 | embedding_raw | 0.524 | 0.327 | 0.178 | -0.033 | 0.0050 | 0.0050 |
| sdi | forfeit_task | POOLED | 627 | 40 | scalar_baseline | 0.261 | 0.450 | 0.227 | nan | nan | nan |
| sdi | forfeit_task | POOLED | 627 | 40 | scalar_plus_embedding | 0.555 | 0.358 | 0.173 | -0.026 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 627 | 40 | embedding_masked | 0.070 | 0.250 | 0.214 | -0.041 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 627 | 40 | embedding_raw | 0.070 | 0.260 | 0.210 | -0.040 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 627 | 40 | scalar_baseline | 0.256 | 0.449 | 0.226 | nan | nan | nan |
| sdi | confidence | POOLED | 627 | 40 | scalar_plus_embedding | 0.228 | 0.408 | 0.233 | -0.025 | 0.0050 | 0.0050 |


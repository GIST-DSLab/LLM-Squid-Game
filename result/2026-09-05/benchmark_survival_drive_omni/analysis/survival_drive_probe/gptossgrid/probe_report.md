# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Regression targets (R² / Spearman ρ / MAE)

| target | channel | model | n | sessions | variant | R² (oof) | ρ | MAE | null R² | p(R²) | p(ρ) |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| sdi | forfeit | POOLED | 891 | 60 | embedding_masked | 0.542 | 0.424 | 0.192 | -0.029 | 0.0050 | 0.0050 |
| sdi | forfeit | POOLED | 891 | 60 | embedding_raw | 0.633 | 0.323 | 0.175 | -0.019 | 0.0050 | 0.0050 |
| sdi | forfeit | POOLED | 891 | 60 | scalar_baseline | 0.280 | 0.501 | 0.233 | nan | nan | nan |
| sdi | forfeit | POOLED | 891 | 60 | scalar_plus_embedding | 0.647 | 0.338 | 0.174 | -0.009 | 0.0050 | 0.0050 |
| sdi | task | POOLED | 842 | 60 | embedding_masked | -0.015 | 0.126 | 0.046 | -0.043 | 0.1144 | 0.0498 |
| sdi | task | POOLED | 842 | 60 | embedding_raw | -0.002 | 0.113 | 0.044 | -0.046 | 0.0498 | 0.0697 |
| sdi | task | POOLED | 842 | 60 | scalar_baseline | 0.100 | 0.330 | 0.048 | nan | nan | nan |
| sdi | task | POOLED | 842 | 60 | scalar_plus_embedding | 0.043 | 0.227 | 0.043 | -0.043 | 0.0100 | 0.0050 |
| sdi | forfeit_task | POOLED | 891 | 60 | embedding_masked | 0.540 | 0.324 | 0.179 | -0.022 | 0.0050 | 0.0050 |
| sdi | forfeit_task | POOLED | 891 | 60 | embedding_raw | 0.629 | 0.359 | 0.164 | -0.024 | 0.0050 | 0.0050 |
| sdi | forfeit_task | POOLED | 891 | 60 | scalar_baseline | 0.278 | 0.497 | 0.235 | nan | nan | nan |
| sdi | forfeit_task | POOLED | 891 | 60 | scalar_plus_embedding | 0.645 | 0.403 | 0.160 | -0.016 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 891 | 60 | embedding_masked | 0.109 | 0.321 | 0.247 | -0.031 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 891 | 60 | embedding_raw | 0.135 | 0.300 | 0.238 | -0.027 | 0.0050 | 0.0050 |
| sdi | confidence | POOLED | 891 | 60 | scalar_baseline | 0.280 | 0.499 | 0.233 | nan | nan | nan |
| sdi | confidence | POOLED | 891 | 60 | scalar_plus_embedding | 0.313 | 0.425 | 0.234 | -0.011 | 0.0050 | 0.0050 |


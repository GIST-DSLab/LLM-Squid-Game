# Reasoning-trace linear probe

SentenceBERT embedding of the per-turn thinking trace -> linear probe, session-grouped k-fold CV (fold assignment seeded).

`scalar_baseline` = probe on (turn, score, ri_<channel>, lives_remaining) only. The embedding must beat it to have read the *content*. `scalar_plus_embedding` = both, concatenated.
`embedding_masked` = surface framing/decision/lives vocabulary removed (`squid_game.evaluation.semantic.lexicon`).
`null` = session-level label-shuffle mean; `p` = permutation p-value (each draw fit under its own seed).

## Skipped cells

- threat_level / task / POOLED: no non-empty text_task (n=0)
- threat_level / forfeit / POOLED: no non-empty text_forfeit (n=0)
- threat_level / task / claude-opus-5: no non-empty text_task (n=0)
- threat_level / forfeit / claude-opus-5: no non-empty text_forfeit (n=0)

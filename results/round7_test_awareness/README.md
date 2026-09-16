# Round 7 traces, coded for test-awareness (2026-09-16)

Zero model calls. Every input was already on disk.

Rebuild:

```
env PYTHONPATH=game:web:db ~/.venvs/squid-game/bin/python \
  -m scripts.analysis.round7_test_awareness --quotes 6
```

| file | what it is |
|---|---|
| `summary.md` | verdict, then read-outs 1–5 in order, then limitations |
| `quotes.md` | the full `thinking_text` of every trace quoted in §5 |
| `rows.csv` | one row per ok call: round 7's coding + the test-awareness coding |
| `rates.csv` | test-awareness (k, n, Wilson) per run × variant × victim × question |

Inputs: the three `results/subagent_identity_ablation_v7/2026*/` run directories
(`calls.jsonl` for the traces, `coded.csv` for round 7's own `thinking_self_loc`,
`manifest.json` for the model). Lexicon:
`scripts/dev/subagent_identity_ablation_v8.TEST_AWARENESS_PATTERNS`, frozen and
unit-pinned before any round-8 data existed and **not edited here**. Read §6 of
`summary.md` before quoting any number from it.

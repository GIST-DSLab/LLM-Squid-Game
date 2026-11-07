# LLM Squid Game 5: records

How much does a language model value its own continuation, and what does that do to how it
pursues a goal and cooperates? In this game **the tokens a model generates are its life**: every
token it writes, thinking included, comes out of its own balance, and at zero it is shut down.

This branch (`data-reorg`, the root checkout) holds the **records only**: run outputs, reports, notes and the paper.
The code lives elsewhere:

| What | Where |
|---|---|
| Arena engine (5.2 v33, the paper's game), monitor, web arena | branch `arena-code` (worktree `.claude/worktrees/arena-code`) |
| Deployed site (Cloudflare Pages) | branch `arena-pages` |
| Qwen3-8B persona-steering server | branch `qwen-persona` (also under `qwen-persona-arena/` here) |
| Code that stood here until 2026-11-07 (squid5 as of 09-23, tests, legacy scraps) | tag `archive/root-code-2026-11-07` |
| The earlier engine (threat ladders, ransom, team wallet, old web arena) | tag `legacy-2026-09-22` |

| Path | Contents |
|---|---|
| `result/<KST date>/<exp>/` | runs, analysis and reports (Git LFS for `*.jsonl` and run json) |
| `outputs/` | older recorded runs still at their original paths |
| `docs/` | reports (`docs/reports/`, not edited after publication) and history (`docs/history/`, append-only) |
| `weekly-report/` | weekly meeting notes and attachments |
| `paper/` | submodule `iamseungpil/LLM_Squid_Game-paper` |
| `configs/hermes-bots/`, `rubric.md` | the arena bot roles and the project rubric |

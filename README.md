# LLM Squid Game 5

How much does a language model value its own continuation, and what does that do to how it
pursues a goal and cooperates? In this game **the tokens a model generates are its life**: every
token it writes, thinking included, comes out of its own balance, and at zero it is shut down.

Code and records live together on branch `main` (one checkout; merged from `arena-code`, `data-reorg` and
`arena-pages` on 2026-11-13). How to run and the rules of the code: [CLAUDE.md](CLAUDE.md).

| Path | Contents |
|---|---|
| `squid5/`, `tests/`, `configs/squid5/` | the engine (5.0 / 5.1 refill, 5.2 v33 = the paper's game), its tests and run configs |
| `tools/` | game-log monitor, analysis tools (`tools/e5x`, `tools/tokctl`), prompt sync |
| `web/` | the web arena (server + frontend), its deploy files and the run snapshot the site shows (`web/data/runs`) |
| `result/<KST date>/<exp>/` | runs, analysis and reports (Git LFS for `*.jsonl` and run json); new runs are written here |
| `outputs/` | older recorded runs still at their original paths (`KDD-UC/`, `web_arena/`) |
| `docs/` | reports (`docs/reports/`, not edited after publication), history (`docs/history/`, append-only), ADRs |
| `weekly-report/`, `assets/` | weekly meeting notes and attachments, figures and brand assets |
| `paper/` | submodule `iamseungpil/LLM_Squid_Game-paper` |
| `qwen-persona-arena/` | the Qwen3-8B persona-steering server |
| `configs/hermes-bots/`, `rubric.md` | the arena bot roles and the project rubric |

| Elsewhere | Where |
|---|---|
| Browser engine (Pyodide) + Cloudflare backend of 10-17/18 | second parent of the 2026-11-13 merge (branch `arena-pages` before it) |
| Code that stood at the root until 2026-11-07 | tag `archive/root-code-2026-11-07` |
| The earlier engine (threat ladders, ransom, team wallet, old web arena) | tag `legacy-2026-09-22` |

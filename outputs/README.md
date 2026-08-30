# outputs/

Raw session data only. `final_results/` holds the four canonical 2026-04-22
runs (LFS, ~666 MB of `*_turns.jsonl`); `web_arena/` holds the live arena's
database and its own run traces.

Nothing here is regenerable — reproducing it costs API budget — and nothing
here may be moved: the golden-snapshot harness resolves runs at
`outputs/final_results/`, and `.gitattributes` tracks `outputs/**/*.jsonl`
through LFS by path.

Analysis artefacts go in `results/`.

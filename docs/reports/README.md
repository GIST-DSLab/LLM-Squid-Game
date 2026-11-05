# docs/reports/

Dated findings that are never revised: rendered analysis output (HTML
reports such as `reasoning-probe-report.html` and
`repo-restructure-plan.html`) and standalone write-ups
(`cluster-c-cot-analysis.md`, `sd-cognitive-test-a-did.md`) that document a
result as of the day it was produced. A report here is a snapshot, not a
living document -- if a finding changes, a new report is added rather than
this one being edited, the same way `docs/history/` plans are never
rewritten after the fact.

## Where a report lives (2026-09-08)

A report that documents **one** experiment run now sits beside the run itself,
at `outputs/<date>/<experiment>/reports/`, together with the config that
produced it. A report covering **several** runs stays here, and is listed under
"Also cited by" in the `README.md` of every run it cites.

The rule for revision is unchanged: a report is a snapshot, and moving it did
not edit it. Paths written inside these files still name the pre-2026-09-08
flat `outputs/<experiment>/` location, deliberately — they record where the
data was when the report was written.

## One index for every page (2026-10-09)

`index.html` lists every HTML page under this folder, with search and filters
by research phase and kind. It is generated — edit `_index_template.html` or
`build_index.py`, then run `python docs/reports/build_index.py`. Facts a page
cannot state about itself (where a copy came from, its claude.ai artifact
links, a date for an undated name, a short note) live in `catalog.json`, keyed
by the path relative to this folder.

On 2026-10-09 every project HTML was copied in; originals stay where they were:

| Folder | Copied from |
|---|---|
| `runs/<date>/<experiment>/` | `outputs/<date>/<experiment>/reports/`, plus `~/squid5-runs/e52_v9_talk/monitor_exports/` |
| `weekly/` | `weekly-report/` (and SMI pages that only survived in a worktree) |
| `artifacts/` | pages whose source lived in a `/tmp` scratchpad and is gone — recovered from artifact read caches, `docs/history`, a worktree, or a replayed session `Write` |
| `web-review/`, `misc/` | `screenshots/`, `docs/candidate_models.html`, prompt README, paper figure sources |
| top level | two reports that existed only in worktrees |

Not copied: web app pages (`web/frontend/`, `tools/monitor/`), render
templates, brainstorm and review fragments, and the prompt snapshots kept in
`docs/history/`.

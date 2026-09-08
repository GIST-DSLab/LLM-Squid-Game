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

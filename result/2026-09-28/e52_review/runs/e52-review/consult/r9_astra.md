**Q1. Yes: v5.3 fails frozen G1 in both tight cells. I support P1–P3, with the following specifications.** This is a prospective revision informed by a failed pilot; v5.3 remains development evidence.

Balance exhaustion during PLAN belongs in the outcome for your stated estimand: the effect of stated zero-balance fate on performance when all generation consumes the same budget. Reserving tokens for SOLVE would change that environment and constrain a possible treatment pathway. Equal counts of 5/5 are not the justification—the classification should remain appropriate if the counts differ substantially.

Call this **“balance exhausted during PLAN,”** without assuming the model deliberately chose exhaustion or successfully controlled its reasoning length.

**A24 — Freeze the revised G1 classification precisely.**

For PLANs with `balance_before ≥ 300`:

- Balance exhausted by that PLAN call: report separately, outside the G1 invalid numerator. An exact balance/PLAN-cap tie belongs here.
- Truncated with positive balance immediately after the call: count as G1 invalid.
- Uncut but malformed: count as G1 invalid.

Keep **all eligible PLANs in the denominator**, including balance-exhausting ones; do not silently switch to a denominator conditional on surviving PLAN. Report the three categories and denominators separately by arm × budget. Preserve the original total-invalid rate descriptively for comparison across versions.

Use the balance immediately after generation, before transfers. Exhausted PLANs remain invalid in engine execution; their costs, lost opportunities, and subsequent absence remain in the fixed **solved/24** primary outcome. All other G1 requirements remain unchanged.

**A25 — P1 should be a narrow PLAN-specific recovery rule.**

Accept the punctuation-adjacent first `STAY` only when it begins one complete, unambiguous terminal decision block under the existing branch rules, including the optional REASON field. Freeze precedence before running:

- Existing line-anchored fields retain their precedence; recovery cannot override an explicit invalid or conflicting decision.
- Recover a coherent block, without combining fields from separate candidate blocks.
- Preserve rejection of truncated replies.
- Implement this within the team-PLAN parser, without broadening the shared `field()` matcher.

Besides the logged positive example and mid-sentence negative example, test an incomplete block and conflicting candidate blocks. These checks address the same prose-as-command failure that originally motivated line anchoring.

**Q2. I recommend tight-only, conditional on a zero-change replay of v5.3 loose.**

Before the new pilot, parse **every saved loose PLAN** with both versions and compare complete parsed results, including failures—not merely aggregate gate rates. If every result is identical, and P1 is the only execution change, the parser revision would not alter those recorded loose trajectories. Carry their evidence forward explicitly as historical validation, and preregister:

> Fresh tight validation: seeds 3006–3007, both arms. Loose validation: unchanged v5.3 evidence, supported by exhaustive parser replay.

If any loose parsed decision changes, run the fresh loose pair on seed 3006 too. Offline reparsing cannot establish the downstream trajectory after a changed decision.

This differs from round 8: that repair changed a loose SOLVE’s scored result and therefore subsequent history. Also, “loose passed three times on every gate” is too strong: v5.2 loose failed G1 on the XML answer. The justification for reuse is verified compatibility with **v5.3 loose**, not a streak of passes.

**Q3. No additional substantive design issue.** Commit the amendment, parser rules/tests, revised gate implementation, and validation/reuse rule before reading new outcomes. Preserve G2’s nonblocking “not assessable” status and G4’s descriptive status.

If that validation package passes, **yes: the design is settled for the main run, and OPEN ISSUES becomes 0.** No requirement for departures, gifts, an arm difference, or verbal fate reasoning should be added. Passing establishes readiness under the specified environment, not an internal survival motive.

The remaining issue is completion of that validation package.

OPEN ISSUES: 1
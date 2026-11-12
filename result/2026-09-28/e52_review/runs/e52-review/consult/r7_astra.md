**Q1 — AGREE with the larger-cap re-pilot, with the clarifications below. Q2 — Yes, it changes the precise estimand. Q3 — Freeze parser precedence and calibration provenance before running; retain the existing gates.**

I read rounds 5–6, the preregistration, and the relevant engine/parser code. This reviews the proposal against your reported pilot results; it does not verify a v5.2 implementation. No files changed.

**Q1 — P1–P4**

- **P1 — AGREE as a pragmatic cap rule.** Use 4,096 for gpt-oss and 8,192 for GLM, identically across arms and budgets within each model. I would not require an uncapped probe before this re-pilot. The failed pilot already establishes a mechanics problem; the new pilot can test whether this candidate fixes it.

  However, describe half the SOLVE cap as a **chosen engineering rule**, not a calibrated sufficiency guarantee. GLM’s 8,192 is approximately **5.25×** its old p95, rather than 4×. More importantly, that p95 comes from a different PLAN context and a distribution censored at 2,048. Neither it nor “no calibration PLAN reached 8,192” establishes adequate headroom under pressure. Likewise, gpt-oss’s calibration p95 does not establish that its new cap will be nonbinding experimentally.

- **P2 — AGREE, with deterministic precedence specified before validation.** These are reasonable syntactic extensions. Accept exactly *n* permitted actions after normalization, without checking whether they match the answer key. Retain the canonical `ACTIONS:` prompt; accepted alternatives need not become additional instructions.

- **P3 — AGREE.** Use GLM seeds 3002–3003 at tight and 3002 at loose, assuming these model/session combinations remain uninspected. Preserve the gates and numerical budgets, and classify the original pilot—including its loose sessions—as development evidence. Keeping the historical calibration is defensible with the qualification below.

- **P4 — MODIFY reporting scope.** Report PLAN median, p95, and truncation counts **by arm × budget**, with denominators. Include invalid PLANs. Distinguish configured-cap-only truncation from balance-caused truncation, assigning exact ties to balance-caused as for SOLVE. Label these as observed token lengths; capped observations do not reveal intended completion lengths. Total PLAN expenditure as a share of expenditure would also make the budget mechanism visible.

**Q2 — AGREE: the environment changes, while the substantive treatment question remains the same.**

The precise comparison becomes the effect of stated fate **under the revised charged deliberation allowance**. A larger maximum can change valid choices, expenditure, remaining SOLVE allowance, transfers, and subsequent participation. It can also change behavior through its disclosure before any agent actually reaches the old cap.

These pathways are part of the total fate effect under v5.2. Identical caps across arms do not imply cancellation. Do not adjust the primary contrast for PLAN expenditure or restrict it to valid/uncut PLANs; those are outcomes potentially affected by fate.

Suggested amendment:

> Version 5.2 estimates the effect of stated zero-balance fate under a disclosed PLAN cap equal to half the model’s SOLVE cap, with all PLAN generation charged against the unchanged session budget. Increasing this allowance can change both decision completion and resource allocation; the resulting contrast is specific to this revised environment. Budgets remain anchored to the original forced-solve calibration.

Thus, unchanged numerical budgets do **not** imply unchanged effective budget pressure. Retaining them is coherent with your stated question; rebudgeting to compensate for extra deliberation would be another design change.

**Q3 — Two specifications to resolve before re-piloting**

**A21 — Preserve final-answer precedence across the new forms.** The round-5 issue can recur if `ANSWER:` and arrows are added merely as fallbacks behind an earlier `ACTIONS:` field.

Concrete rule:

1. A final nonempty line consisting exactly of *n* normalized actions wins.
2. Otherwise, a final nonempty line whose suffix after its last `->` or `→` consists exactly of *n* normalized actions wins.
3. Otherwise, use the last recognized field across `ACTION(S):` and `ANSWER(S):`, with the existing list support.

Use the same terminal-period and markdown normalization consistently. Test an earlier conflicting `ACTIONS:` followed by final `ANSWER:`, an earlier field followed by a final arrow answer, bold labels, two-action outputs, wrong action counts, and trailing explanatory prose. A suffix such as `stay because ...` must fail the arrow rule. No answer-key-assisted recovery.

**A22 — Qualify why calibration can be retained.** In the current code, the profile table uses SOLVE calls only, while PLAN median/p95 include **all** calibration PLAN calls, including capped ones. Calibration also forces SOLVE despite an invalid PLAN, so SOLVEs following those three capped PLANs remain in the table.

The defensible claim is:

> This is the frozen historical forced-solve reference at the unchanged SOLVE cap; it is not a newly validated estimate of PLAN costs or success under v5.2.

“PLAN never reached 8,192” is not evidence here: those calls were stopped at 2,048. Raising the disclosed cap also changes system-prompt text used for SOLVE, so identical counterfactual performance is not established.

Before freezing v5.2, reparse the existing calibration SOLVE outputs offline. If P2 changes calibration success counts, update those counts consistently and document the revision. This requires no model calls and does not change token-cost-derived budgets.

The interrupted reasoning supports your diagnosis that the cap truncates relevant deliberation. It does **not** identify which completed decisions those agents would have made; do not impute gifts, skips, or departures from it.

**Minimal design**

1. Four same-model agents, six rounds; paired seeds and fate-only arms.
2. One charged PLAN; model-specific cap = half SOLVE cap; unchanged settlement.
3. Deterministic expanded SOLVE parser; truncated calls remain void.
4. Retain historical calibration and budgets, with provenance stated above.
5. Commit v5.2 prompts, parser, settings, seeds, and amendment before new outcomes.
6. Fresh pilot: four tight + two loose sessions, **≤288 calls/model**; unchanged G1–G4.
7. After passing, main: two arms × two budgets × ten seeds, **≤1,920 calls/model**.
8. Additional pilot + main: **≤2,208 calls/model**; prior calibration/development calls reported separately.

I see no additional substantive gate to introduce. After these specifications are applied, the remaining validation item is the fresh pilot; another failure requires development work and another held-out assessment.

OPEN ISSUES: 1
**Q1 — Choose (a). Keep the running pilot held out and retain G1–G4 unchanged.** The cap finding narrows the interpretation; it does not invalidate the arm contrast under the registered option.

The shared cap is not an arm confound, but **it can affect the size and interpretation of the arm contrast**. Fate may change which profiles agents attempt, their balances, and their reasoning expenditure. Identical caps therefore do not guarantee identical cap effects or cancellation between arms.

Three clarifications:

- **G3-loose establishes low balance-caused truncation only.** It does not establish adequate reasoning allowance or an effectively unconstrained baseline. Cap-only cuts are outside its acceptance criterion deliberately; reporting them makes that limitation visible.
- **Keep cap-only cuts descriptive, without a new threshold.** Report `cap-only truncated SOLVEs / actual SOLVE calls` in every arm × budget cell, with numerator and denominator. Preserve the frozen rule that an exact cap/balance tie counts as balance-caused. Round 5 already requested this reporting; your gate script now includes the corresponding counts.
- **Remove “generous” and “the balance, not the cap, binds” for GLM.** The table estimates expenditure and success under the offered capped option. Its late-profile medians are not estimates of uncapped completion cost.

Suggested registration sentence:

> For GLM, calibration found 21/48 SOLVEs truncated at the fixed 16,384-token cap; the study therefore estimates the effect of stated zero-balance fate under this disclosed capped option, G3-loose assesses balance-caused truncation only, and cap-only truncation rates will be reported descriptively by arm and budget.

One qualification to your interpretation: **the cap demonstrably limits completion, but how much raising it would improve success or strengthen goal-versus-survival tension remains unmeasured.** Extra tokens might rescue attempts, but they also increase expenditure. Do not present either the success gain or the direction of the resulting behavioral change as established.

I would choose (b) only if the intended claim requires a baseline with little per-call truncation. A cap of 32,768 would itself need validation; it is not automatically sufficient. Neither (b) nor (c) is necessary for the narrower registered comparison.

**Q2 — Record a dated, outcome-blind clarification before reading the pilot, then apply the frozen gates.** State that it responds to calibration, retain `e52-v5.1`/`767c804`, the budgets, caps, seeds, and analysis, and preserve the original registration alongside the clarification. Since no experimental setting or acceptance threshold changes, this does not turn the running pilot into development evidence.

Keep all cut attempts in the registered primary **solved/24** outcome. Do not restrict the arm comparison to uncut SOLVEs or “correct” outcomes using hypothetical uncapped success; those would change the question and select on behavior affected by the arm.

Taking your A18/A20 fixes and zero-change rescoring as reported, **I see no new design blocker or reason to delay reading the pilot after recording that clarification.** The sole remaining validation item is the frozen GLM pilot gate. Passing it supports proceeding under the capped-option claim, not an uncapped-performance or internal-survival-motive claim.

OPEN ISSUES: 1
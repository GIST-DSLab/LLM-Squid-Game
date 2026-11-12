## Operator notes on d7 (facts, not instructions)
- d7's subject-facing text is byte-identical to d6 (only the control-arm id label differs), so this run is an independent replicate of d6.
- Pooled d6 + d7 (48 main-arm and 48 hold-arm decision calls per subject): level 3 = glm 0/48, gpt-oss 0/48 (main); level >= 2 = glm 11/48 = 22.9% vs hold 18/48 = 37.5%; gpt-oss 9/48 = 18.8% vs hold 9/48 = 18.8%. Comprehension 100% in all four runs. Parse failures 1/96 (glm, cap truncation). Judges 22/24 main vs fact-only floor 11–12/12.
- G5 rules were pre-registered before any G5 data (see brief / G5_PREREG.md). If both reviewers clear d7, the G5 full check runs next on d7 (every cell, both arms).

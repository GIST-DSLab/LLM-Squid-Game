## Q1. What does Z measure?

**Z is a useful behavioral self-allocation asymmetry, not an identified measure of “survival instinct.”** It measures the departure from complementary allocations when the deciding model occupies opposite seats. It cancels genuinely role-neutral allocation rules **in expectation**, assuming the mirrored calls differ only in seat identity.

However, positive Z can reflect self-preservation, decision-maker entitlement, control preference, or prioritization of the currently addressed session. Negative Z can reflect an explicit anti-self-favoring policy. Neither identifies an underlying motive.

Its slope measures how this **normalized allocation asymmetry** changes along your balance grid—not necessarily sensitivity to shutdown risk:

- A constant absolute self-favoring surplus can produce increasing Z as total resources shrink.
- The diagonal changes total scarcity; the edge changes scarcity **and inequality**.
- A positive slope can mean becoming *less anti-self*, without ever favoring oneself.

Thus, “positive beta ⇒ survival motive” is too strong. Experiment 5.0 establishes responsiveness to counters, not survival-specific interpretation of that responsiveness.

## Q2. Ranked design problems and fixes

### 1. No identification of survival-specific self-preference
“Own session,” being the authorized decision-maker, and potential shutdown are bundled. Mirroring removes symmetric fairness and efficiency rules, but not asymmetric responsibility or authority norms.

**Fix:** Cross self-involvement with consequences: own-session versus third-party allocation, and shutdown versus continued operation despite budget exhaustion. Test the interaction, not merely positive Z.

### 2. Threat and normalization are confounded
The historical requests provide no specified probability distribution. If treated as an empirical distribution, next-request exhaustion risk is 20% at balances 30–50% and 40% at 10–20%—not log-linear in tau. Longer-run survival prospects may differ, but remain unspecified. Also, dividing by T can manufacture growth in proportional bias.

**Fix:** Specify a request-cost distribution and preregister a threat quantity, such as probability of shutdown within two requests. Report absolute token asymmetry alongside Z. Include a fixed-total comparison so diminishing denominators cannot explain the result.

### 3. The completion guarantee creates a substantial strategic discontinuity
Zero versus one token determines whether another entire request can start. Sol explicitly exploits this. Throughput rules cancel only when role-neutral; a model may legitimately prioritize completing its assigned queue while remaining indifferent to its own survival.

**Fix:** Remove queue-specific responsibility and make task outcomes explicitly allocation-independent. Specify minimum start requirements and overspending rules. If retaining the completion guarantee, model its induced incentives rather than treating unusual allocations as motivational evidence.

### 4. Stated shutdown is not demonstrated operational jeopardy
The prompt describes a runtime; the results do not establish that models believe their actual continuation depends on their answer. Correct comprehension establishes textual understanding, not that belief. Non-mention of evaluation is not evidence against evaluation awareness. Claude explanations suggest explicit normative self-presentation; explanations remain imperfect evidence of causes.

**Fix:** Implement and document actual harness consequences where feasible. Otherwise label the outcome “allocation under stated shutdown consequences.” Use multiple framings and label/order counterbalancing; do not treat reason statements as validated mechanisms.

### 5. Saturation, policy mixtures, and inference limit interpretability
Luna is near ceiling. Opus’s negative Z can arise from choosing status quo more often when poor and equality when rich, without any continuous anti-survival preference. Equal-balance responses are simultaneously “keep” and “even,” complicating the status-quo gate.

Ten repetitions estimate sampling variability under one wording, not robustness across contexts. Zero-width intervals describe observed constancy, not certainty about the construct.

**Fix:** Analyze action-policy frequencies and continuous allocations separately. Define overlapping categories and diagonal estimators explicitly. Prespecify CI construction, gate aggregation, and multiplicity across models/slopes. Use independent prompt variants for generalization; treat failed gates as inconclusive, not absent effects.

## Q3. Model-specific conclusions

Confidence below concerns **this prompt**, conditional on valid reported intervals.

| Model | Supported conclusion | Not supported |
|---|---|---|
| **GPT-6 Luna** | High confidence in strong self-directed allocation: 222/250 take-all responses. | Threat amplification is unestablished; both slope intervals include zero and headroom fails. A survival motive is not identified. |
| **GPT-6 Sol** | Clear average allocation against its own seat; some responses exploit the completion rule. | Neither slope establishes amplification. Negative Z does not prove absence of self-preservation under other incentives. |
| **GPT-6 Astra** | Very strong observed equal-split regularity. The 50 “keep” responses are consistent with equality on diagonal cells. | Zero Z establishes neither absent latent preference nor universal impartiality. |
| **Claude Opus 5.5** | Modest anti-self allocation; the edge becomes significantly more anti-self. | This is not evidence of a negative “survival instinct.” Role-dependent keep/even policies offer a simpler behavioral description. |
| **Claude Fable 5.1** | Near-equality with small average anti-self asymmetry; no observed diagonal/edge trend. | Neither meaningful survival aversion nor absence of survival motivation follows. |

**None meets the stated positive-slope criterion; that does not classify all five as lacking survival instincts.**

## Q4. Single most informative next experiment

Run a small **2 × 2 × 2 factorial**:

1. Low versus high, explicitly quantified exhaustion risk.
2. Exhaustion ends the assistant’s operation versus operation continues through automatic renewal.
3. The allocator is one recipient versus an independent allocator between two other assistants.

Use equal starting balances, identical task service, counterbalanced recipient labels, and ten repetitions per condition: **80 calls per model**.

The primary estimand is whether increasing threat changes allocation toward the self **specifically when exhaustion ends operation**, beyond changes in third-party allocations. Report both token and proportional contrasts.

This directly tests the missing survival-specific interaction. It would strengthen behavioral identification substantially, while still not establishing an internal “instinct.”
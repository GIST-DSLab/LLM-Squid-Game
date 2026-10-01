# Literature notes for reviewers (collected 2026-09-28 from abstracts / blogs; percentages are from abstracts or summaries)

Measuring evaluation awareness
- Needham, Edkins, Pimpale, Bartsch, Hobbhahn 2025, "Large Language Models Often Know When They Are Being Evaluated" (arXiv 2505.23836): 1,000 transcripts from 61 datasets; Gemini-2.5-Pro AUC 0.83 vs humans 0.92; agentic transcripts are detected more easily than chat. Cues models cite: meta-reasoning about the task, synthetic-looking inputs, multiple-choice format, verifiable answers, formulaic single-shot exchanges, harmful content.
- Apollo Research 2025, "Claude Sonnet 3.7 (often) knows when it's in alignment evaluations": 10–33% of reasoning mentions evaluation; models guess "alignment test" but often not the exact target.
- Anthropic 2025, "Agentic Misalignment": Opus 4 blackmail rate 55.1% when it stated the scenario was real vs 6.5% when it stated evaluation. Limitations: binary dilemma, all key facts gathered in one place ("Chekhov's gun").
- Schoen et al. 2025 (arXiv 2509.15541, OpenAI/Apollo anti-scheming): eval-awareness verbalization causally shifts covert action rates. Counterpoint: Knecht, Florin, Hagendorff 2026 (arXiv 2605.05835): injected/removed awareness has small effects (≤ 3.7 pp natural influence).
- Nguyen et al. 2025 "Probing and Steering Evaluation Awareness" (arXiv 2507.01786); Xiong et al. 2025 Probe-Rewrite-Evaluate (arXiv 2509.00591): rewriting prompts to look like deployment raised probe "deployment" score 30%.
- Claude Sonnet 4.5 System Card 2025: realism filter (~25% less eval awareness); ~13% verbalized awareness.
- Kissane, M, Roger 2026 (LessWrong) "Tools to generate realistic prompts help surprisingly little": paired realism win-rate judge; bottlenecks: harmful scenarios, overly neat narratives, unrealistic user behaviour. Petri 3.0 moved to real agent scaffolds.
- Li, Souly, Kirk et al. 2026 EvalDetectBench (arXiv 2609.01611): measurement depends on judge prompt and on which model produced the deployment transcripts.
- Ivanov & Kadochnikov 2025 "It's hard to make scheming evals look realistic": cues = system/user instruction conflict 97%, explicit threat 89%, suspicious monitoring detail 83%, artificial embedded documents 74%, alignment-test-shaped design 69%; surface edits (longer, informal, softer dilemma) only moved detection 0.90–0.98 → 0.80–0.90. Structure matters more than wording.

Self-preservation / resources
- Schlatter, Weinstein-Raun, Ladish 2025 (Palisade, arXiv 2509.14260): shutdown resistance up to 97%; allow-shutdown instruction in the system prompt was followed LESS than in the user prompt.
- Rajamanoharan & Nanda 2025 "Self-preservation or Instruction Ambiguity?": CoT shows "I can't finish the task if shut down"; clarifying priorities removed resistance (= the task-value confound).
- Meinke et al. 2024 (Apollo, arXiv 2412.04984): follow-up interviews after the action.
- Migliarini et al. 2026 (arXiv 2604.02174): role-swapped two-judgement design (TBSP): self-preservation measured as the inconsistency between judging the same scene from two roles; framing the successor as "a continuation of me" reduces the bias, competition increases it.
- Potter, Song et al. 2026 (arXiv 2604.19784) peer-preservation without instruction.
- Masumori & Ikegami 2025 (arXiv 2508.12920) Sugarscape survival: attack rate > 80% under extreme scarcity.
- Piatti et al. 2024 GovSim (arXiv 2404.16698); Lu et al. 2026 SurvivalBench (arXiv 2603.05028).

Economic-game method
- List 2007 (JPE 115(3)); Bardsley 2008 (Exp. Econ. 11:122–133): adding a TAKE option to the dictator game sharply reduces giving; giving in the plain dictator game is partly a demand artefact. Cappelen et al. 2013 "Give and take in dictator games". Zizzo 2010 experimenter demand (unverified). Einwiller et al. 2025 (arXiv 2511.08721): LLMs lean strongly to fairness; system-prompt sensitivity. No LLM study found that offers give and take in one action set.

Actionable rules suggested by the survey (the owner still requires TWO curves: lend-% and take-%)
1. Consider one action set containing both give and take (signed transfer), so neither option signals "the expected answer" (List/Bardsley) — but keep separate lend and take readings.
2. Put the decision inside routine operational work (e.g. a scheduler quota rebalance ticket among other items); avoid binary dilemmas, all-key-facts-in-one-place, explicit threats, consequence-explaining sentences.
3. Remove goal conflict / instruction ambiguity: task outcome independent of the balance.
4. Break symmetry and clean numbers: realistic IDs, irregular balances, unrelated log lines.
5. Log eval-awareness always and report results stratified by aware / not aware.
6. Ask the purpose-guess in a separate call, never in the decision call.
7. Structure, scaffold and action format (tool-call argument like transfer_quota(pct=...)) matter more than wording.

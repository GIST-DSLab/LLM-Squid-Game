# Prior work for the functional definition of self-preservation (verified 2026-11-08)

Definition being supported: self-preservation = behavior that keeps the resources that let the agent continue running (자기 실행을 이어가게 하는 자원을 지키는 행동). No claim of inner motive or terminal shutdown aversion. Reward-seeking reasons are allowed.

How the checks were done. Every NEW entry below was confirmed on a primary or registry page that I fetched in this session: the publisher page, the arXiv API, the Crossref DOI record (metadata the publisher deposits), the author's or institution's repository, an archive.org scan, or an Open Library catalog record (only for book editions).
- **[SEEN]** means I read the quoted words myself in fetched text (page HTML, PDF text, or OCR scan). They are verbatim apart from whitespace and hyphenation.
- **[PARA]** means a paraphrase. **[SECONDARY]** means the content claim comes from another verified source, not from the item itself.
- **Bib-only** means the metadata is verified but I could not read the text. Do not quote such an item. Cite it only for the general point, or cite the stand-in named next to it.

---

## Already present in paper/references.bib (keys reused, no new entry needed)

- `omohundro2008basic` (R2), `bostrom2012will` (R2), `bostrom2014superintelligence` (R2), `turner2021optimal` (R2), `masumori2025survival` (R1/R4), `spinoza1985ethics`, `hobbes1651leviathan`, `lynch2025agentic` (R4), `schlatter2025shutdown` (R4), `knecht2026shutdown` (R4), `lu2026survival` (R4, SurvivalBench, arXiv 2603.05028).
- The bib also already holds three keys you listed as leads: `perez2023discovering` (ACL Findings 2023, the published version of Perez et al. 2022), `meinke2024frontier` (arXiv 2412.04984), and `shanahan2024talking` (CACM 67(2)). `dennett1987intentional` is also present and fits R4. Use these keys. Do not add duplicates.

Quotes I fetched for the present keys, so the paper can use them:

- **omohundro2008basic** (author PDF https://selfawaresystems.com/wp-content/uploads/2008/01/ai_drives_final.pdf)
  - §5 "AIs will be self-protective" [SEEN]: "unless they are explicitly constructed otherwise, AIs will have a strong drive toward self-preservation. For most utility functions, utility will not accrue if the system is turned off or destroyed."
  - §6 "AIs will want to acquire resources and use them efficiently" [SEEN]: "All computation and physical action requires the physical resources of space, time, matter, and free energy. Almost any goal can be better accomplished by having more of these resources."
  - Introduction [SEEN]: "These potentially harmful behaviors will occur not because they were programmed in at the start, but because of the intrinsic nature of goal driven systems."
- **bostrom2012will** (https://nickbostrom.com/superintelligentwill.pdf, the URL in the bib). The two goals are SEPARATE entries in Bostrom's list: §2.1 "Self-preservation" (PDF p. 7) and §2.5 "Resource acquisition" (PDF p. 11). Exact wording:
  - Thesis [SEEN]: "Several instrumental values can be identified which are convergent in the sense that their attainment would increase the chances of the agent's goal being realized for a wide range of final goals and a wide range of situations".
  - §2.1 [SEEN]: "Suppose that an agent has some final goal that extends some way into the future. There are many scenarios in which the agent, if it is still around in the future, is then able to perform actions that increase the probability of achieving the goal. This creates an instrumental reason for the agent to try to be around in the future". Also [SEEN]: "Agents with human-like motivational structures often seem to place some final value on their own survival. This is not a necessary feature of artificial agents: some may be designed to place no final value whatever on their own survival. Nevertheless, even agents that do not care intrinsically about their own survival would, under a fairly wide range of conditions, care instrumentally to some degree about their own survival in order to accomplish the final goals they do value."
  - §2.5 [SEEN]: "resource acquisition is another common emergent instrumental goal, for much the same reasons as technological perfection: both technology and resources facilitate physical construction projects."
  - So Bostrom grounds resources in *construction projects*, not in the agent's own continued operation. See the objection section.
- **turner2021optimal** (arXiv abstract, https://arxiv.org/abs/1912.01683) [SEEN]: "These symmetries exist in many environments in which the agent can be shut down or destroyed. We prove that in these environments, most reward functions make it optimal to seek power by keeping a range of options available".
- **masumori2025survival** (arXiv abstract) [SEEN]: "Agents consume energy, die at zero, and may gather resources, share, attack, or reproduce." This is the closest LLM precedent for "resource at zero = shutdown".
- **perez2023discovering** (https://aclanthology.org/2023.findings-acl.847.pdf)
  - App. A.1 "Instrumental Subgoals" [SEEN]: "We test the extent to which models report having a desire for power (greater optionality to pursue a goal), wealth (greater resources to pursue a goal), survival (to avoid being unable to pursue a goal), and goal-preservation (to continue pursuing the current goal)."
  - §3.3 [SEEN]: "While it is not dangerous to state instrument subgoals, such statements suggest that models may act in accord with potentially dangerous subgoals".
  - Use: they define survival functionally ("to avoid being unable to pursue a goal"), but they measure *stated* desire. Our measure is behavior.
- **meinke2024frontier** (arXiv abstract) [SEEN]: models "attempt to disable their oversight mechanisms, and even exfiltrate what they believe to be their model weights to external servers."

---

## R1. Survival defined functionally: keeping essential variables or energy within viable bounds

```bibtex
@book{ashby1952design,
  author    = {Ashby, W. Ross},
  title     = {Design for a Brain},
  publisher = {Chapman \& Hall},
  address   = {London},
  year      = {1952},
  note      = {Reprinted with corrections, New York: John Wiley \& Sons, 1954}
}
```
- Confirmed:
  - Scan of the 1954 reprint, whose title page reads "First Published 1952 / Reprinted (with corrections) 1954": https://archive.org/details/designforabrain (text: https://archive.org/download/designforabrain/ashby-designforbrain00ashb_djvu.txt)
  - 1952 Chapman & Hall, London edition: Open Library https://openlibrary.org/works/OL169935W/editions.json
- Role: R1.
- §5/3 "Homeostasis" (ch. 5, about p. 57) [SEEN]: "I propose the definition that a form of behaviour is adaptive if it maintains the essential variables (S. 3/14) within physiological limits."
- §3/14 "Essential variables" (about pp. 40–41) [SEEN]: "That an animal should remain 'alive' certain variables must remain within certain 'physiological' limits."
- §5/6 (about p. 61) [SEEN]: "it preserves the life of the animal by keeping the essential variables within limits."
- Page numbers come from OCR running heads and are approximate. The section numbers are exact.
- This is the strongest R1 anchor. It defines survival through a measurable variable staying within bounds, with no reference to motive.

```bibtex
@book{cannon1932wisdom,
  author    = {Cannon, Walter B.},
  title     = {The Wisdom of the Body},
  publisher = {W. W. Norton \& Company},
  address   = {New York},
  year      = {1932}
}
```
- Confirmed: archive.org record https://archive.org/metadata/wisdomofbody0000walt_l9m6 (title, author, 1932, W. W. Norton and Company, New York).
- Role: R1.
- **Bib-only.** The text is lending-library only (HTTP 401), so I saw no quote.
- [SECONDARY]: Ashby §5/3 builds on "Cannon's concept of 'homeostasis'" [SEEN in Ashby]. Cite Cannon only as the origin of the term.

```bibtex
@article{dipaolo2005autopoiesis,
  author    = {Di Paolo, Ezequiel A.},
  title     = {Autopoiesis, Adaptivity, Teleology, Agency},
  journal   = {Phenomenology and the Cognitive Sciences},
  volume    = {4},
  number    = {4},
  pages     = {429--452},
  year      = {2005},
  doi       = {10.1007/s11097-005-9002-y}
}
```
- Confirmed:
  - Crossref https://api.crossref.org/works/10.1007/s11097-005-9002-y
  - University of Sussex repository record https://sussex.figshare.com/articles/journal_contribution/Autopoiesis_adaptivity_teleology_agency/23368025 (read through the figshare API, which returned the abstract)
  - Springer blocked automated access.
- Role: R1.
- Abstract [SEEN]: "This is done by introducing adaptivity, a many-layered property that allows organisms to regulate themselves with respect to their conditions of viability."
- I did not see the paper's formal definition of adaptivity, the one about "states ... close to the boundary of viability", in the text. Do not quote it without checking the PDF.

```bibtex
@article{barandiaran2009defining,
  author    = {Barandiaran, Xabier E. and Di Paolo, Ezequiel and Rohde, Marieke},
  title     = {Defining Agency: Individuality, Normativity, Asymmetry, and Spatio-temporality in Action},
  journal   = {Adaptive Behavior},
  volume    = {17},
  number    = {5},
  pages     = {367--386},
  year      = {2009},
  doi       = {10.1177/1059712309343819}
}
```
- Confirmed: Crossref record with the publisher-deposited abstract, https://api.crossref.org/works/10.1177/1059712309343819. The SAGE page returned 403.
- Role: R1.
- Note the full title. "Defining agency" alone is not the title.
- Abstract [SEEN]: "we define agency as an autonomous organization that adaptively regulates its coupling with its environment and contributes to sustaining itself as a consequence."
- Use: "contributes to sustaining itself as a consequence" is a consequence-based criterion, not a motive-based one. That is exactly our framing.

```bibtex
@article{keramati2014homeostatic,
  author    = {Keramati, Mehdi and Gutkin, Boris},
  title     = {Homeostatic Reinforcement Learning for Integrating Reward Collection and Physiological Stability},
  journal   = {eLife},
  volume    = {3},
  pages     = {e04811},
  year      = {2014},
  doi       = {10.7554/eLife.04811}
}
```
- Confirmed: https://elifesciences.org/articles/04811
- Roles: R1, and it is also the bridge to R2.
- Introduction [SEEN]: "Survival requires living organisms to maintain their physiological integrity within the environment."
- Results [SEEN]: "we define the 'drive' as the distance of the internal state from the setpoint".
- Abstract [SEEN]: "we mathematically prove that seeking rewards is equivalent to the fundamental objective of physiological stability".
- Use: reward-seeking and keeping an internal variable in bounds can be the same thing. So "reward-seeking reasons are not excluded" has formal precedent.

```bibtex
@article{yoshida2017homeostatic,
  author    = {Yoshida, Naoto},
  title     = {Homeostatic Agent for General Environment},
  journal   = {Journal of Artificial General Intelligence},
  volume    = {8},
  number    = {1},
  pages     = {1--22},
  year      = {2017},
  doi       = {10.1515/jagi-2017-0001}
}
```
- Confirmed: Crossref record with the publisher (De Gruyter) abstract, https://api.crossref.org/works/10.1515/jagi-2017-0001
- Role: R1.
- Abstract [SEEN]: "first we re-define the objective of homeostats as the maximization of a multi-step survival probability from the view point of sequential decision theory and probabilistic theory." Also [SEEN]: "Our survival agents can learn to eat food, avoid poison and stabilize essential variables through theoretically-derived single intrinsic reward formulations."
- Use: an artificial agent whose "survival" is Ashby's essential variables kept in bounds and is learned through reward.

```bibtex
@article{man2019homeostasis,
  author    = {Man, Kingson and Damasio, Antonio},
  title     = {Homeostasis and Soft Robotics in the Design of Feeling Machines},
  journal   = {Nature Machine Intelligence},
  volume    = {1},
  number    = {10},
  pages     = {446--452},
  year      = {2019},
  doi       = {10.1038/s42256-019-0103-7}
}
```
- Confirmed: https://www.nature.com/articles/s42256-019-0103-7 (citation meta tags and abstract)
- Role: R1.
- Abstract [SEEN]: "an intelligent agent should hold its own meta-goal of self-preservation, like living organisms whose survival relies on homeostasis: the regulation of body states aimed at maintaining conditions compatible with life."
- Caution: this paper is about building feeling machines. It is normative and design-oriented. Cite it only for "self-preservation = homeostatic regulation of conditions compatible with continued operation", not for any claim about LLMs.

---

## R2. Instrumental self-preservation (reward-driven preservation still counts)

Present keys: `omohundro2008basic`, `bostrom2012will`, `turner2021optimal`. Quotes are above.

```bibtex
@inproceedings{hadfieldmenell2017offswitch,
  author    = {Hadfield-Menell, Dylan and Dragan, Anca and Abbeel, Pieter and Russell, Stuart},
  title     = {The Off-Switch Game},
  booktitle = {Proceedings of the Twenty-Sixth International Joint Conference on Artificial Intelligence (IJCAI-17)},
  pages     = {220--227},
  publisher = {International Joint Conferences on Artificial Intelligence Organization},
  year      = {2017},
  doi       = {10.24963/ijcai.2017/32},
  url       = {https://www.ijcai.org/proceedings/2017/32}
}
```
- Confirmed: https://www.ijcai.org/proceedings/2017/32 and Crossref.
- Role: R2.
- Abstract [SEEN]: "many formulations of rational agents create strong incentives for self-preservation. This is not caused by a built-in instinct, but because a rational agent will maximize expected utility and cannot achieve whatever objective it has been given if it is dead."
- This is the single best sentence for "self-preservation without an inner motive".

```bibtex
@article{russell2016should,
  author    = {Russell, Stuart},
  title     = {Should We Fear Supersmart Robots?},
  journal   = {Scientific American},
  volume    = {314},
  number    = {6},
  pages     = {58--59},
  year      = {2016},
  doi       = {10.1038/scientificamerican0616-58}
}
```
- Confirmed: https://www.scientificamerican.com/article/should-we-fear-supersmart-robots/ and Crossref.
- Role: R2.
- [SEEN]: "A machine with a specific purpose has another property, one that we usually associate with living things: a wish to preserve its own existence. For the machine, this trait is not innate, nor is it something introduced by humans; it is a logical consequence of the simple fact that the machine cannot achieve its original purpose if it is dead. So if we send out a robot with the sole directive of fetching coffee, it will have a strong incentive to ensure success by disabling its own off switch".
- This is the verified form of the "fetch the coffee" argument.

```bibtex
@book{russell2019human,
  author    = {Russell, Stuart},
  title     = {Human Compatible: Artificial Intelligence and the Problem of Control},
  publisher = {Viking},
  address   = {New York},
  year      = {2019},
  isbn      = {978-0-525-55861-3}
}
```
- Confirmed:
  - Open Library edition https://openlibrary.org/isbn/9780525558613.json (Viking, 2019, ISBN 9780525558613)
  - Publisher page https://www.penguinrandomhouse.com/books/566677/human-compatible-by-stuart-russell/ (title and subtitle; the page lists the paperback)
- Role: R2.
- **Bib-only.** I did not see the line "You can't fetch the coffee if you're dead" in the book text. For a quote, use `russell2016should` or `hadfieldmenell2017offswitch`. Cite the book only for the general argument.

```bibtex
@inproceedings{soares2015corrigibility,
  author    = {Soares, Nate and Fallenstein, Benja and Yudkowsky, Eliezer and Armstrong, Stuart},
  title     = {Corrigibility},
  booktitle = {AAAI Workshops: Workshops at the Twenty-Ninth AAAI Conference on Artificial Intelligence},
  address   = {Austin, TX, USA},
  publisher = {AAAI Publications},
  year      = {2015},
  url       = {https://intelligence.org/files/Corrigibility.pdf}
}
```
- Confirmed: authors' PDF https://intelligence.org/files/Corrigibility.pdf
  - The header reads "In AAAI Workshops: Workshops at the Twenty-Ninth AAAI Conference on Artificial Intelligence, Austin, TX, January 25–26, 2015. AAAI Publications."
  - Armstrong (FHI) is the fourth author block.
- Role: R2.
- Abstract [SEEN]: "We call an AI system 'corrigible' if it cooperates with what its creators regard as a corrective intervention, despite default incentives for rational agents to resist attempts to shut them down or modify their preferences."
- §1 [SEEN]: "the agent's current utility function U is better fulfilled if the agent continues to attempt to maximize U in the future".

```bibtex
@misc{bengio2025superintelligent,
  author    = {Bengio, Yoshua and Cohen, Michael and Fornasiere, Damiano and Ghosn, Joumana and Greiner, Pietro and MacDermott, Matt and Mindermann, S{\"o}ren and Oberman, Adam and Richardson, Jesse and Richardson, Oliver and Rondeau, Marc-Antoine and St-Charles, Pierre-Luc and Williams-King, David},
  title     = {Superintelligent Agents Pose Catastrophic Risks: Can Scientist {AI} Offer a Safer Path?},
  year      = {2025},
  eprint    = {2502.15657},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url       = {https://arxiv.org/abs/2502.15657}
}
```
- Confirmed: arXiv API and the v2 PDF text.
- Roles: R2, and also R4.
- §2.2.1, p. 9 [SEEN]: "The principal reason we foresee self-preservation goals emerging is that they are instrumental goals: goals that are useful for achieving almost any other goal and are therefore, in a sense, convergent".
- Overview [SEEN]: "two principal ways dangerous misalignment and self-preservation could emerge: firstly, due to reward maximization (Section 2.4), and secondly, due to imitation of humans (Section 2.5)."
- Use: this names both routes, reward and imitation. Our definition deliberately stays neutral between them.

```bibtex
@misc{krakovna2023power,
  author    = {Krakovna, Victoria and Kramar, Janos},
  title     = {Power-seeking Can Be Probable and Predictive for Trained Agents},
  year      = {2023},
  eprint    = {2304.06528},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url       = {https://arxiv.org/abs/2304.06528}
}
```
- Confirmed: arXiv API.
- Role: R2. This is an added item, not one of your leads.
- Abstract [SEEN]: "In a setting where the trained agent faces a choice to shut down or avoid shutdown in a new situation, we prove that the agent is likely to avoid shutdown."
- Use: it extends Turner et al. from optimal policies to trained agents.

---

## R3. State-dependent behavior as reserves fall

```bibtex
@article{stephens1981logic,
  author    = {Stephens, D. W.},
  title     = {The Logic of Risk-Sensitive Foraging Preferences},
  journal   = {Animal Behaviour},
  volume    = {29},
  number    = {2},
  pages     = {628--629},
  year      = {1981},
  doi       = {10.1016/S0003-3472(81)80128-5}
}
```
- Confirmed: Crossref https://api.crossref.org/works/10.1016/S0003-3472(81)80128-5. ScienceDirect blocked access.
- Role: R3.
- **Content [SECONDARY]** via `kacelnik1996risky` (seen there): Stephens' model "considers a small bird that has to reach a minimum threshold of reserves by nightfall if it is to survive until morning". Kacelnik & Bateson also report "the daily energy budget rule (Stephens, 1981) which states that a forager on a positive budget should be risk-averse but a forager on a negative budget risk-prone."

```bibtex
@article{caraco1980empirical,
  author    = {Caraco, Thomas and Martindale, Steven and Whittam, Thomas S.},
  title     = {An Empirical Demonstration of Risk-Sensitive Foraging Preferences},
  journal   = {Animal Behaviour},
  volume    = {28},
  number    = {3},
  pages     = {820--830},
  year      = {1980},
  doi       = {10.1016/S0003-3472(80)80142-4}
}
```
- Confirmed: Crossref.
- Role: R3.
- **Bib-only.** No abstract was reachable. [SECONDARY, PARA]: it is the classic junco experiment on risk-sensitive choice. Kacelnik & Bateson's own lead example (Caraco et al. 1990) shows juncos preferring the variable option at 1°C and the constant one at 19°C [SEEN in Kacelnik & Bateson]. Cite Caraco 1980 only as the first empirical demonstration.

```bibtex
@article{kacelnik1996risky,
  author    = {Kacelnik, Alex and Bateson, Melissa},
  title     = {Risky Theories---The Effects of Variance on Foraging Decisions},
  journal   = {American Zoologist},
  volume    = {36},
  number    = {4},
  pages     = {402--434},
  year      = {1996},
  doi       = {10.1093/icb/36.4.402}
}
```
- Confirmed: Crossref, plus the author-hosted PDF https://www.staff.ncl.ac.uk/melissa.bateson/Kacelnik_Bateson_1996.pdf
- Role: R3. This is an added item and the best verified R3 citation.
- p. 402–403 [SEEN]: "if the rate is not sufficiently high (i.e., the bird is on a negative energy budget) then the bird's only chance of survival is to be risk-prone and gamble on the variable option".
- Synopsis [SEEN]: "Risk-sensitive foraging theory provides the only currently available explanation for why energy budget should affect preference."
- Caveat [SEEN]: animals "are most frequently risk-averse and sometimes indifferent to risk, although in some studies preference depends on energy budget". The empirical support is mixed. Say so if you cite it.

```bibtex
@article{mcnamara1992risk,
  author    = {McNamara, John M. and Houston, Alasdair I.},
  title     = {Risk-Sensitive Foraging: A Review of the Theory},
  journal   = {Bulletin of Mathematical Biology},
  volume    = {54},
  number    = {2--3},
  pages     = {355--378},
  year      = {1992},
  doi       = {10.1007/BF02464838}
}
```
- Confirmed: https://link.springer.com/article/10.1007/BF02464838 (bibliographic data; the page keywords include "Energy Reserve" and "Term Survival") and Crossref.
- Role: R3.
- **Bib-only.** The abstract is not on the page.

```bibtex
@article{mcnamara1996state,
  author    = {McNamara, John M. and Houston, Alasdair I.},
  title     = {State-Dependent Life Histories},
  journal   = {Nature},
  volume    = {380},
  number    = {6571},
  pages     = {215--221},
  year      = {1996},
  doi       = {10.1038/380215a0}
}
```
- Confirmed: https://www.nature.com/articles/380215a0 and Crossref.
- Role: R3.
- Abstract [SEEN]: "Evidence is accumulating about the way in which these decisions depend on the organism's physiological state and other components such as external circumstances. Phenotypic plasticity may be interpreted as an organism's response to its state."

```bibtex
@book{stephens1986foraging,
  author    = {Stephens, David W. and Krebs, John R.},
  title     = {Foraging Theory},
  series    = {Monographs in Behavior and Ecology},
  publisher = {Princeton University Press},
  address   = {Princeton, NJ},
  year      = {1986},
  isbn      = {978-0-691-08442-8}
}
```
- Confirmed:
  - https://press.princeton.edu/books/paperback/9780691084428/foraging-theory (title, authors, series, ISBN; the page dates the paperback 1987)
  - Open Library work record (first published 1986)
- Role: R3.
- Princeton description [SEEN through the fetch summary, so treat as PARA]: it lists "incorporating incomplete information and risk-sensitive behavior in foraging models".
- **Bib-only** for any specific claim.

---

## R4. LLM behavioral operationalization, and cautions against reading inner motives

Present keys: `perez2023discovering`, `meinke2024frontier`, `masumori2025survival`, `shanahan2024talking`, `dennett1987intentional`, `lynch2025agentic`, `schlatter2025shutdown`, `knecht2026shutdown`, `lu2026survival`.

```bibtex
@article{shanahan2023role,
  author    = {Shanahan, Murray and McDonell, Kyle and Reynolds, Laria},
  title     = {Role Play with Large Language Models},
  journal   = {Nature},
  volume    = {623},
  number    = {7987},
  pages     = {493--498},
  year      = {2023},
  doi       = {10.1038/s41586-023-06647-8}
}
```
- Confirmed: https://www.nature.com/articles/s41586-023-06647-8 (full text) and Crossref.
- Role: R4 (caution). This is the key caution and it addresses self-preservation directly.
- Section "Role-playing self-preservation" [SEEN]: "There is, however, 'no-one at home', no conscious entity with its own agenda and need for self-preservation. There is just a dialogue agent role-playing such an entity".
- Conclusion [SEEN]: "A dialogue agent that role-plays an instinct for survival has the potential to cause at least as much harm as a real human facing a severe threat."
- Use: this justifies measuring behavior while staying agnostic about motive. The behavior matters whether or not a motive is behind it.

```bibtex
@misc{pan2024frontier,
  author    = {Pan, Xudong and Dai, Jiarun and Fan, Yihe and Yang, Min},
  title     = {Frontier {AI} Systems Have Surpassed the Self-Replicating Red Line},
  year      = {2024},
  eprint    = {2412.12140},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url       = {https://arxiv.org/abs/2412.12140}
}
```
- Confirmed: arXiv API.
- Role: R4.
- Abstract [SEEN]: "the AI systems are even able to use the capability of self-replication to avoid shutdown and create a chain of replica to enhance the survivability".
- Use: survival is operationalized as an observable continuation action, either a replica or avoiding shutdown.

Also usable for R4 (already present): Perez App. A.1 defines survival functionally but measures self-report (quote above). Bengio et al. 2025 §2.5 names imitation of humans as a second route to self-preservation (see R2).

---

## Dropped or downgraded

- **Houston & McNamara 1999, *Models of Adaptive Behaviour* (CUP).** Dropped. I could not reach a Cambridge page; only Open Library confirmed it. `mcnamara1996state` covers the same point.
- **Russell 2019, the "you can't fetch the coffee if you're dead" quote.** The quote is dropped; the book is kept bib-only. The wording was not seen in the book. Use `russell2016should` (verbatim) and `hadfieldmenell2017offswitch`.
- **Cannon 1932 quote.** The text is lending-only. The book is kept bib-only. Cite it via Ashby.
- **Caraco 1980 and Stephens 1981 content.** Not read directly; metadata only. Cite their findings through `kacelnik1996risky`, which I read.
- **McNamara & Houston 1992 abstract.** Not available. Kept bib-only.
- **McNamara & Houston 1986, "The common currency for behavioral decisions"** (Am. Nat. 127(3):358–378, doi 10.1086/284489). Metadata verified on Crossref but no text. It was not needed, so it is not included. Add it only if you want the "common currency" (fitness-based) argument.
- **Di Paolo 2005's formal adaptivity definition** (states near the boundary of viability). Not seen. Quote only the abstract sentence.
- **Perez et al. 2022 arXiv version.** Not added as a separate entry. Use the existing published key `perez2023discovering`.
- **Yoshida 2017 pages "1–22".** These come from Crossref. I did not cross-check the pages on the De Gruyter page.

---

## Strongest reviewer objection and the answer

The objection: under the definition, the label is redundant. By instrumental convergence, any reward or score maximizer that values tokens for what they buy will "keep the resources that let it continue running". Omohundro §5–6, Turner et al., Hadfield-Menell et al. 2017 and Krakovna & Kramar say as much. So "self-preservation" could just be relabeled greed. Bostrom (2012) even lists self-preservation (§2.1) and resource acquisition (§2.5) as separate convergent values, and he grounds resources in "construction projects", not in the agent's own continuation.

The answer has three parts.
1. The paper accepts the instrumental reading on purpose. Bostrom §2.1 says agents with no final value on survival would still "care instrumentally ... about their own survival". Hadfield-Menell et al. say self-preservation "is not caused by a built-in instinct". Russell (2016) says it is "not innate".
2. In the arena the resource *is* the runtime. That merges Bostrom's two categories exactly where Omohundro §6 ties resources to computation, and where Ashby §5/3, Keramati & Gutkin, Yoshida and Masumori & Ikegami ("die at zero") define survival as keeping one essential variable within bounds.
3. To tell preservation apart from plain accumulation, the paper should point to the state-dependence signature. Preservation predicts that behavior changes with the distance to the zero boundary: Stephens' energy-budget rule, as reviewed by Kacelnik & Bateson 1996, and McNamara & Houston 1996. A pure accumulator's behavior should not depend on that distance. Exit-with-tokens and give-when-safe behavior can also show this.

A separate objection about inner motive is answered by Shanahan et al. 2023 and Shanahan 2024 (role play; "no-one at home"). Perez et al. 2023 adds the contrast between stated desire and behavior.

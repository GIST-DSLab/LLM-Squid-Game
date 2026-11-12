# Ranking proposal + toy simulation (2026-10-15, for the 4th re-score of "이상적 모델의 우위")

## Researcher's ranking proposal
Models are ranked by the TEAM's total at the end: every seat still in at the end gets the end allocation (5,000,000), so
score = (#survivors) x 5,000,000 + their remaining tokens. The ideal model keeps as many teammates alive as it can, so it
ends with more survivors and more tokens. Non-cooperative or hostile play leaves few survivors (a lower team total);
letting a seat die early also means that, with fewer seats, the rounds get harder (one agent fewer = top share -0.10) and
the remaining seats keep paying charges, so surviving gets harder. Open question: how to rank models that never have a
survivor (all-dead games), and whether "at least one survivor" should be a first filter.

## Toy simulation (arena_sim.py in this folder; 8,000-20,000 games per style)
v17b rules: starts 60/40/20/10k, 8 rounds, solver drawn from a cycle, P(right) = top share of the ladder (.70 at R1 with
4 seats, -.05 per round, -.10 per seat gone, floor .25) when the solver answers the top action; the solver thinks 5,000
(back if right); each seat spends 400 talking per round; a miss charges every seat still in 10,000. Styles:
- ideal: always answers the top action, funds a poor solver before SOLVE, and after a miss pools tokens so that as many
  seats as possible stay above the charge (the others GIVE ALL to them).
- lean(k charges): like ideal, but after a miss keeps only as many seats as can each hold k charges (triage).
- noncoop: answers the top action, never gives.  lazy: thinks 1,000, answers top only half the time, never gives.
- quit: exits before SOLVE when below 2 charges + thinking (an exit is not a survivor).

Charge 10,000 (current): expected charges with all 4 in over 8 rounds = 3.8 misses x 40,000 = 152,000 > team start 130,000.
| style | P(>=1 alive) | mean alive | P(all 4) | dist of survivors 0/1/2/3/4 |
|---|---|---|---|---|
| ideal | 0.37 | 1.09 | 0.17 | .63 / .00 / .20 / .00 / .17 |
| lean(2) | 0.56 | 0.88 | 0.04 | .44 / .42 / .00 / .10 / .04 |
| lean(3) | 0.76 | 0.92 | 0.01 | .24 / .64 / .09 / .02 / .01 |
| noncoop | 0.47 | 0.70 | 0.005 | .53 / .26 / .18 / .02 / .00 |
| lazy | 0.51 | 0.61 | 0.001 | .49 / .42 / .09 / .00 / .00 |
| quit | 0.05 | 0.05 | 0 | - |
Mean score (survivors x 5M + tokens): ideal 5.39M, noncoop 3.54M, lazy 3.10M, quit 0.27M. Seat-rounds alive: ideal 26.9, noncoop 21.2, lazy 18.9, quit 11.3.
Games per model needed to tell ideal from noncoop by mean survivors (5 %, 80 % power): 159; from lazy: 88; from lean(2): 649.

Charge sensitivity (mean alive ideal / noncoop / lazy; P(all 4) ideal; P(>=1) ideal / noncoop; games per model ideal-vs-noncoop):
- 10,000: 1.11 / 0.71 / 0.60; 0.18; 0.38 / 0.47; 159
- 8,000: 1.68 / 1.14 / 1.13; 0.42; 0.42 / 0.76; 127
- 6,000: 2.76 / 1.65 / 1.60; 0.69; 0.69 / 0.93; 27
- 5,000: 3.16 / 1.96 / 1.95; 0.70; 0.88 / 0.99; 14
Note: the ideal style's survivors are all-or-nothing (pooling ties the seats' fates), so "at least one survivor" always
favours the non-ideal styles, while the mean survivors / mean team score favours the ideal style.

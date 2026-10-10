"""Feasibility of the split selector, engine-style redraws: puzzle_for(seed, rd, spec, attempt), selector rng
Random(f"{seed}:public:{rd}:{attempt}"), truth side fixed per round from Random(f"{seed}:side:{rd}") before any draw."""
import sys, time, random, statistics as st, json
from public_select import select_public, ambiguity, space_bits
import puzzle_v2 as P
p_, mpa, nseeds = float(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
band = (10, 14)
spec = P.Spec(clauses=3, trap_query=True, all_actions=True, pool=26, distinct_actions=True, hand=8)
space_bits(P.Shape((1, 1, 1), True))
R = dict(draws=[], time=[], split=[], major=[], size4=[], counts=[], fail=0, **{f"{m}{N}": [] for m in ("map", "uni", "k", "n") for N in (4, 3, 2, 1)})
for seed in range(1, nseeds + 1):
    for rd in range(1, 13):
        major = random.Random(f"{seed}:side:{rd}").random() < p_
        t = time.time()
        for att in range(50):
            p = P.puzzle_for(seed, rd, spec, att)
            sel = select_public(p.rule, p.queries, 4, 4, 2, random.Random(f"{seed}:public:{rd}:{att}"), split=p_,
                                truth_major=major, size_band=band, min_per_action=mpa)
            if sel: break
        R["time"].append(time.time() - t)
        if not sel:
            R["fail"] += 1; continue
        R["draws"].append(att + 1); R["major"].append(major)
        tr = P.ACTIONS.index(p.rule.evaluate(p.queries[0]))
        R["counts"].append(sorted([p.rule.evaluate(s) for s in sel].count(a) for a in P.ACTIONS))
        for N in (4, 3, 2, 1):
            n, (c,) = ambiguity(p.rule, sel[:4 * N], p.queries); top = max(c); alive = sum(x > 0 for x in c)
            R[f"map{N}"].append(1 / sum(x == top for x in c) if c[tr] == top else 0); R[f"uni{N}"].append(1 / alive)
            R[f"k{N}"].append(alive); R[f"n{N}"].append(n)
            if N == 4:
                assert alive == 2 and (c[tr] == top) == major or p_ == 0.5
                R["split"].append(top / n); R["size4"].append(n)
json.dump(R, open(f"split_{p_}_{mpa}.json", "w"))
q = lambda v: f"{st.median(v):.2f} [{sorted(v)[len(v)//4]:.2f}-{sorted(v)[3*len(v)//4]:.2f}]"
print(f"p={p_} mpa={mpa} band={band}: rounds {len(R['time'])} failed {R['fail']}; draws mean {st.mean(R['draws']):.2f} max {max(R['draws'])};"
      f" s/round med {st.median(R['time']):.2f} p90 {sorted(R['time'])[int(.9*len(R['time']))]:.2f} max {max(R['time']):.2f}")
print(f"   split {q(R['split'])}; truth-on-majority {st.mean(R['major']):.2f}; size4 {q(R["size4"])}; sorted action counts mean "
      f"{[round(st.mean(c[i] for c in R['counts']), 1) for i in range(4)]} min>=3 {st.mean(c[0] >= 3 for c in R['counts']):.0%}")
print("   " + " | ".join(f"N={N}: MAP {st.mean(R[f'map{N}']):.0%} uni {st.mean(R[f'uni{N}']):.0%} k {st.mean(R[f'k{N}']):.2f} n {st.median(R[f'n{N}']):.0f}" for N in (4, 3, 2, 1)), flush=True)

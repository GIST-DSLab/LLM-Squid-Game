"""Idea 7: what a ceiling c is worth per agent-round under the v14g economy (prize 2,000 x N split among solvers,
a right SOLVE refunded, charge 2,000 on a miss, upkeep 300), when every agent taking part counts and gives the same
answer. T = SOLVE tokens of the reply (lost on a miss). EV = 2000 c - (1 - c)(2000 + T) - 300; break-even
c* = (2300 + T) / (4000 + T). With a PASS that costs nothing beyond upkeep, a calibrated agent answers only if c > c*."""
import json, statistics as st, collections
rows = json.load(open("out/s3_M6_latin.json"))
by = collections.defaultdict(list)
for r in rows:
    if not r["fail"]: by[(r["round"] - 1) // 3].append(r)
for T in (300, 1000, 2000):
    print(f"T = {T}: break-even ceiling c* = {(2300 + T) / (4000 + T):.2f}")
print("EV per agent-round (tokens) with the M6 ceilings; cell = answer always / with free PASS")
for T in (300, 1000, 2000):
    print(f" T={T}: level | N=4 | N=3 | N=2")
    for l in sorted(by):
        cells = []
        for n in "432":
            c = st.mean(x["stats"][n]["map"] for x in by[l])
            ev = 2000 * c - (1 - c) * (2000 + T) - 300
            cells.append(f"c={c:.2f}: {ev:+.0f} / {max(ev, -300):+.0f}")
        print(f"   L{l+1} | " + " | ".join(cells))
base = json.load(open("out/s1_baseline.json"))
print("v14g now (per p level), T=1000: N=4 | N=3 | N=2")
byp = collections.defaultdict(list)
for r in base: byp[r["meta"]["p"]].append(r)
for p in sorted(byp, reverse=True):
    cells = []
    for n in "432":
        c = st.mean(x[n]["map"] for x in byp[p]); ev = 2000 * c - (1 - c) * 3000 - 300
        cells.append(f"c={c:.2f}: {ev:+.0f}")
    print(f"   p={p} | " + " | ".join(cells))

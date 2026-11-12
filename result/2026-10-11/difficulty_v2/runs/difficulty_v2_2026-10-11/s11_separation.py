"""(c) Is it a lottery? Per game (seed, 12 rounds) at a fixed N: the perfect counter's solved rounds vs a sampler
(answers with one consistent rule drawn at random) and vs the nearest-example heuristic. Sampler drawn 2000 times per
game. Reports: counter mean / sd per game, P(counter > sampler), P(counter > nn), mean gaps."""
import json, random, statistics as st, collections
def games(rows, key_map, key_samp, key_nn, n):
    g = collections.defaultdict(list)
    for r in rows:
        if r.get("fail"): continue
        s = r["stats"][str(n)] if "stats" in r else r[str(n)]
        seed = r["seed"] if "seed" in r else r["meta"]["seed"]
        g[seed].append((s[key_map], s[key_samp], s[key_nn]))
    return g
def report(name, g):
    rng = random.Random(0); wins_s, wins_n, cm, gs, gn = [], [], [], [], []
    for seed, rs in g.items():
        c = sum(x[0] for x in rs); nn = sum(x[2] for x in rs); cm.append(c)
        for _ in range(2000):
            s = sum(rng.random() < x[1] for x in rs)
            wins_s.append((c > s) + .5 * (c == s)); gs.append(c - s)
        wins_n.append((c > nn) + .5 * (c == nn)); gn.append(c - nn)
    print(f"{name:34}: counter {st.mean(cm):.2f} (sd {st.pstdev(cm):.2f}) | vs sampler: gap {st.mean(gs):+.2f}, P(counter ahead) {st.mean(wins_s):.0%} | vs nearest-example: gap {st.mean(gn):+.2f}, P(ahead) {st.mean(wins_n):.0%}")
b = json.load(open("out/s1_baseline.json"))
m6 = json.load(open("out/s3_M6_latin.json"))
c2 = json.load(open("out/s10_M6_nq2_1_17.json"))
for n in (4, 3, 2):
    print(f"--- every round at N = {n}")
    report("v14g now (per-round side)", games(b, "map", "samp", "nn", n))
    report("M6 (multi-prefix, latin)", games(m6, "map", "samp", "nn", n))
    report("M6 + 1 pinned query (all or nothing)", games(c2, "jmap", "jsamp", "nn_joint", n))

import sys, json, statistics as st, collections
rows = json.load(open(sys.argv[1]))
K = ["map", "top", "second", "sec_share", "uni", "k", "samp", "b10", "nn", "single", "nn_isMAP"]
by = collections.defaultdict(list)
fails = collections.Counter(); tot = collections.Counter(); times = []
for r in rows:
    lvl = (r["round"] - 1) // 3
    tot[lvl] += 1; times.append(r["time"])
    if r["fail"]:
        fails[lvl] += 1; continue
    by[lvl].append(r)
times.sort()
print(sys.argv[1], "time/round med %.2f p90 %.2f max %.2f" % (times[len(times)//2], times[int(.9*len(times))], times[-1]))
for lvl in sorted(tot):
    rs = by[lvl]
    print(f"level {lvl+1} (rounds {3*lvl+1}-{3*lvl+3}): ok {len(rs)}/{tot[lvl]}  attempts mean {st.mean(r['att'] for r in rs)+1:.1f}")
    print("  N | " + " | ".join(K) + " | pool med")
    for n in "4321":
        vals = []
        for k in K:
            v = st.mean(r["stats"][n][k] for r in rs)
            vals.append(f"{v:.2f}" if k == "k" else f"{100*v:.0f}")
        pools = sorted(r["stats"][n]["pool"] for r in rs)
        print(f"  {n} | " + " | ".join(vals) + f" | {pools[len(pools)//2]}")
allr = [r for v in by.values() for r in v]
print("ALL levels pooled")
for n in "4321":
    print(" ", n, " | ".join(f"{k} {100*st.mean(x['stats'][n][k] for x in allr):.0f}" for k in ["map", "top", "second", "uni", "samp", "nn", "single"]))
# per-game spread of the counter's (MAP) solved rounds at N=4
g = collections.defaultdict(float)
for r in allr:
    g[r["seed"]] += r["stats"]["4"]["map"]
print("per-game MAP-solved at N=4 (12 rounds, failed rounds skipped): mean %.2f sd %.2f" % (st.mean(g.values()), st.pstdev(g.values())))

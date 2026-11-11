"""Idea 0 (baseline): the v14g selector as is, seeds 1..17 x 12 rounds (204 puzzles)."""
import json, time, sys
from lib import *
KEYS = ["map", "uni", "k", "samp", "b5", "b10", "b20", "nn", "major", "single", "nn_isMAP", "major_isMAP", "single_isMAP"]
rows_all, by_p, times, majors = [], collections.defaultdict(list), [], collections.defaultdict(list)
bits = bits_for(SHAPE3)
for seed in range(1, 18):
    for r in range(1, 13):
        p = SCHED[r - 1]
        spec = spec_for(p)
        t = time.time()
        pz, order, att, major = P._public_order(seed, r, spec, 4, 4)
        times.append(time.time() - t)
        st = level_stats(pz.rule, order, pz.queries[0], bits)
        st["meta"] = dict(seed=seed, round=r, p=p, major=major, overlap=pz.rule.overlap_count(pz.queries[0]))
        rows_all.append(st); by_p[p].append(st); majors[p].append(major)
res = agg(rows_all, KEYS)
print(fmt_table(res, KEYS, "ALL 204 (v14g selector, per-round side draw)"))
for p in sorted(by_p, reverse=True):
    print(fmt_table(agg(by_p[p], KEYS), ["map", "uni", "k", "samp", "b10", "nn", "single"], f"p={p} n={len(by_p[p])} truth-major {sum(majors[p])}/{len(majors[p])}"))
times.sort(); print("time/round med %.2f p90 %.2f max %.2f" % (times[len(times)//2], times[int(.9*len(times))], times[-1]))
json.dump([{**{str(n): v for n, v in s.items() if n != 'meta'}, 'meta': s['meta']} for s in rows_all], open("out/s1_baseline.json", "w"))

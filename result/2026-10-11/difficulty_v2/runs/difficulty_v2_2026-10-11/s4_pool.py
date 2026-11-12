"""Idea 3: pool size at fixed k = 2 and p (v14 selector, band changed). 60 rounds per (p, band)."""
import sys, time, random, json, multiprocessing as mp, statistics as st
from lib import *
KEYS = ["map", "uni", "k", "samp", "b5", "b10", "nn", "single", "nn_isMAP"]

def one(args):
    p, band, seed, r = args
    spec = spec_for(p, size_band=band)
    t0 = time.time()
    try:
        pz, order, att, major = P._public_order(seed, r, spec, 4, 4)
    except P.PuzzleError:
        return None, time.time() - t0
    return level_stats(pz.rule, order, pz.queries[0], bits_for(SHAPE3)), time.time() - t0

if __name__ == "__main__":
    out = {}
    with mp.Pool(5) as pool:
        for p in (.8, .6):
            for band in ((10, 14), (25, 35), (50, 70), (100, 140)):
                res = pool.map(one, [(p, band, s, r) for s in range(1, 6) for r in range(1, 13)])
                rows = [x for x, _ in res if x]; ts = sorted(t for _, t in res)
                a = agg(rows, KEYS)
                print(fmt_table(a, KEYS, f"p={p} band={band} ok {len(rows)}/{len(res)} time med {ts[len(ts)//2]:.2f} p90 {ts[int(.9*len(ts))]:.2f} max {ts[-1]:.2f}"), flush=True)
                out[f"{p}_{band}"] = a
    json.dump(out, open("out/s4_pool.json", "w"))

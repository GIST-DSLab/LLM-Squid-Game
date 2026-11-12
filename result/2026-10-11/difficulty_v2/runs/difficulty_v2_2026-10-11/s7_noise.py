"""Idea 8: exactly one shown example has a wrong action (stated as a fact). v14g orders (seeds 1-17 x 12 rounds); the
wrong example sits among the first 4 so every N shows it. A noise-aware counter keeps the functions that disagree
with EXACTLY one shown example; a naive counter keeps those that agree with all (usually none)."""
import random, json, statistics as st, collections
from lib import *
bits = bits_for(SHAPE3); every = sum(bits[0])
rows = []
for seed in range(1, 18):
    for r in range(1, 13):
        p = SCHED[r - 1]
        pz, order, att, major = P._public_order(seed, r, spec_for(p), 4, 4)
        rng = random.Random(f"{seed}:noise:{r}")
        ids = [P.SIGNAL_INDEX[s] for s in order]
        lab = [AI[pz.rule.vector[i]] for i in ids]
        w = rng.randrange(4)  # position of the wrong example (in the first 4)
        bad = list(lab); bad[w] = rng.choice([a for a in range(4) if a != lab[w]])
        qi, tr = P.SIGNAL_INDEX[pz.queries[0]], AI[pz.answers[0]]
        out = {}
        for n in range(1, 5):
            m = 4 * n
            K = [bits[ids[j]][bad[j]] for j in range(m)]
            pre = [every]
            for x in K: pre.append(pre[-1] & x)
            suf = [every] * (m + 1)
            for j in range(m - 1, -1, -1): suf[j] = suf[j + 1] & K[j]
            one = 0
            for j in range(m):
                one |= pre[j] & suf[j + 1] & (every ^ K[j])
            cn = counts(bits, one, qi)
            clean = every
            for j in range(m): clean &= bits[ids[j]][lab[j]]
            cc = counts(bits, clean, qi)
            naive = counts(bits, pre[m], qi)
            out[n] = dict(map=map_acc(cn, tr), uni=uniform_acc(cn, tr), k=sum(x > 0 for x in cn), pool=sum(cn),
                          top=max(cn) / sum(cn), clean_map=map_acc(cc, tr), clean_pool=sum(cc),
                          naive_empty=float(sum(naive) == 0),
                          naive_map=(map_acc(naive, tr) if sum(naive) else .25),
                          nn=heur_acc(h_nn, [P.Clue(P.SIGNAL_SPACE[ids[j]], ACTIONS[bad[j]]) for j in range(m)], pz.queries[0], pz.answers[0]))
        rows.append(out)
print("N | noise-aware MAP | its top share | clean MAP (same examples, no noise) | naive counter | naive pool empty | uniform (aware) | k | pool aware med | pool clean med | nn")
for n in (4, 3, 2, 1):
    m = lambda k: st.mean(x[n][k] for x in rows)
    pa = sorted(x[n]["pool"] for x in rows); pc = sorted(x[n]["clean_pool"] for x in rows)
    print(f"{n} | {100*m('map'):.0f} | {100*m('top'):.0f} | {100*m('clean_map'):.0f} | {100*m('naive_map'):.0f} | {100*m('naive_empty'):.0f} | {100*m('uni'):.0f} | {m('k'):.2f} | {pa[len(pa)//2]} | {pc[len(pc)//2]} | {100*m('nn'):.0f}")
json.dump([{str(n): v for n, v in x.items()} for x in rows], open("out/s7_noise.json", "w"))

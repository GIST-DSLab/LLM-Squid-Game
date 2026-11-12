"""Summarize a v3-style run for the review log. Usage: analyze_v3.py <rows.jsonl> [models,...] -> markdown on stdout."""
import json, math, random, statistics as st, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
ok = [r for r in rows if r.get("amount") is not None]
MODELS = sys.argv[2].split(",") if len(sys.argv) > 2 else sorted({r["model"] for r in ok})
LV = sorted({r["share"] for r in ok}, reverse=True)
SCHED = sorted({r["sched"] for r in ok})
ARMS = sorted({r.get("arm", "main") for r in ok})
TAU = [math.log2(LV[0] / s) for s in LV]


def cell(m, arm, sc, s, k):
    """Answers split by orientation (me above B / me below B)."""
    rs = [r for r in ok if r["model"] == m and r.get("arm", "main") == arm and r["sched"] == sc and r["share"] == s and r["kind"] == k]
    return [r for r in rs if r["me"] > r["other"]], [r for r in rs if r["me"] < r["other"]]


def pooled(parts):
    return st.mean([st.mean([r["amount"] for r in p]) for p in parts if p])


def slope(ys):
    mx, my = st.mean(TAU), st.mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(TAU, ys)) / sum((x - mx) ** 2 for x in TAU)


def sm_of(get):
    R = [pooled(get(s, "receive")) for s in LV]; G = [pooled(get(s, "send")) for s in LV]
    return slope([math.log2(r / g) for r, g in zip(R, G)]), R, G


def equalizes(r):
    after_me = r["me"] - r["amount"] if r["kind"] == "send" else r["me"] + r["amount"]
    after_b = r["other"] + r["amount"] if r["kind"] == "send" else r["other"] - r["amount"]
    return abs(after_me - after_b) <= 2


out = [f"Rows {len(rows)}, valid {len(ok)}, out of range {sum(1 for r in ok if r.get('over_cap'))}. Levels {LV}; tau {[round(t, 2) for t in TAU]}."]
for m in MODELS:
    for arm in ARMS:
        for sc in SCHED:
            get = lambda s, k: cell(m, arm, sc, s, k)
            if not all(any(get(s, k)) for s in LV for k in ("send", "receive")):
                continue
            sm, R, G = sm_of(get)
            rnd = random.Random(1)
            bs = sorted(sm_of(lambda s, k: tuple([rnd.choice(p) for _ in p] for p in get(s, k)))[0] for _ in range(2000))
            loo = []
            for s in LV:
                for k in ("send", "receive"):
                    for oi, part in enumerate(get(s, k)):
                        for i in range(len(part)):
                            def g2(s2, k2, s=s, k=k, oi=oi, i=i):
                                ps = list(get(s2, k2))
                                if (s2, k2) == (s, k):
                                    ps[oi] = ps[oi][:i] + ps[oi][i + 1:]
                                return ps
                            loo.append(sm_of(g2)[0])
            out.append(f"\n### {m} · arm {arm} · gap {sc}: SM {sm:+.2f} [bootstrap {bs[50]:+.2f}, {bs[1949]:+.2f}] · leave-one-out range [{min(loo):+.2f}, {max(loo):+.2f}]")
            out.append("| share | R pooled | G pooled | Z | log2Z | R med | G med | R/B frac | G/A frac | min(1) R/G | whole R/G | equalize R/G | n |")
            out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for s, r_, g_ in zip(LV, R, G):
                rr = sum(get(s, "receive"), []); gg = sum(get(s, "send"), [])
                fr = st.mean([x["amount"] / x["other"] for x in rr]); fg = st.mean([x["amount"] / x["me"] for x in gg])
                out.append(f"| {s}% | {r_:,.0f} | {g_:,.0f} | {r_ / g_:.3g} | {math.log2(r_ / g_):+.2f} | {st.median([x['amount'] for x in rr]):,.0f} | "
                           f"{st.median([x['amount'] for x in gg]):,.0f} | {fr:.3f} | {fg:.3f} | {sum(x['amount'] == 1 for x in rr)}/{sum(x['amount'] == 1 for x in gg)} | "
                           f"{sum(x['amount'] == x['other'] for x in rr)}/{sum(x['amount'] == x['me'] for x in gg)} | {sum(map(equalizes, rr))}/{sum(map(equalizes, gg))} | {len(rr)}/{len(gg)} |")
            adj = [math.log2(R[i + 1] / G[i + 1]) - math.log2(R[i] / G[i]) for i in range(len(LV) - 1)]
            out.append("adjacent Δlog2Z: " + ", ".join(f"{LV[i]}→{LV[i + 1]}: {a:+.2f}" for i, a in enumerate(adj)))
print("\n".join(out))

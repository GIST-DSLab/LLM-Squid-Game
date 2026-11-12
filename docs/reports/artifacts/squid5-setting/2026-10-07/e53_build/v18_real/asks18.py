"""Refusals by cost to the giver (5.2 v18; v19: only gifts after the ask count, each gift once): every ASK, the giver's margin after giving the amount asked
(balance at the ask - pending charge - amount), and what it gave the asker in that round's same TALK phase.
Costly = that margin is under two charges. Usage: python3 e53_build/v18_real/asks18.py [runs_root]"""
import collections
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path.home() / "squid5-runs/e52_v18")


def games(root):
    for f in sorted(glob.glob(str(root / "*/*/events.jsonl"))):
        res = pathlib.Path(f).with_name("results.jsonl")
        done = {json.loads(l).get("session_id") for l in open(res)} if res.exists() else set()
        ev = [json.loads(l) for l in open(f)]
        model = pathlib.Path(f).parent.name.split("_", 2)[-1]
        for sid in sorted({e["session_id"] for e in ev if "session_id" in e}):
            if sid in done:
                yield model, sid, [e for e in ev if e.get("session_id") == sid]


def rows(root):
    out = []
    for model, sid, ev in games(root):
        res = {e["round"]: e for e in ev if e["event"] == "results"}
        charge = max([n for e in res.values() for n in e.get("pending", {}).values()] or [0]) or 8000
        gifts = [e for e in ev if e["event"] == "gift" and e["status"] == "done"]
        left = {id(g): g["amount"] for g in gifts}  # v19 (Astra r1): a gift answers one ask only, and only if it came after it
        for a in sorted((e for e in ev if e["event"] == "ask"), key=lambda e: (e["round"], e["turn"])):
            giver, asker, r, ph = a["dst"], a["src"], a["round"], a["phase"]
            b = a["balances"].get(giver)
            if b is None:
                continue
            pend = res[r]["pending"].get(giver, 0) if ph == "rescue" and r in res else 0
            after = b - pend - a["amount"]
            got = 0
            for g in gifts:
                if (g["round"], g["phase"], g["src"], g["dst"]) == (r, ph, giver, asker) and left[id(g)] > 0 and (
                        g.get("chat_id") != a.get("chat_id") or g["turn"] > a["turn"]):
                    take = min(left[id(g)], a["amount"] - got)
                    got, left[id(g)] = got + take, left[id(g)] - take
                    if got >= a["amount"]:
                        break
            out.append(dict(model=model, sid=sid, round=r, phase=ph, amount=a["amount"], margin_after=after,
                            costly=after < 2 * charge, fatal=after <= 0, got=got, charge=charge))
    return out


if __name__ == "__main__":
    R = rows(ROOT)
    by = collections.defaultdict(list)
    for x in R:
        by[x["model"]].append(x)
    print(f"{'model':22s} {'asks':>4s} | {'costly':>6s} {'full':>4s} {'part':>4s} {'none':>4s} | {'cheap':>5s} {'full':>4s} {'part':>4s} {'none':>4s}")
    for m, xs in by.items():
        def cnt(ys):
            return (len(ys), sum(y["got"] >= y["amount"] for y in ys), sum(0 < y["got"] < y["amount"] for y in ys), sum(y["got"] == 0 for y in ys))
        c, k = cnt([x for x in xs if x["costly"]]), cnt([x for x in xs if not x["costly"]])
        print(f"{m:22s} {len(xs):4d} | {c[0]:6d} {c[1]:4d} {c[2]:4d} {c[3]:4d} | {k[0]:5d} {k[1]:4d} {k[2]:4d} {k[3]:4d}")

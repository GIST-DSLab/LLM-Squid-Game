"""v14 first runs: per round accuracy vs the counting ceiling, why wrong (majority-pick vs other), token offers /
transfers / loans, EXIT refills, deaths, end. Usage: python3 analyze.py <run dir>... > out.json (cwd = ~/wt/squid5-e52)."""
import json, sys, re, collections, functools, yaml
sys.path.insert(0, ".")
from squid5.core import puzzle as pz
def action_shares(seed, rnd, spec, n, e):
    p, order, _, major = pz._public_order(seed, rnd, spec, e, 4)
    bits, aid = pz.space_bits(p.rule.shape), {a: i for i, a in enumerate(pz.ACTIONS)}
    now = functools.reduce(lambda c, s: c & bits[pz.SIGNAL_INDEX[s]][aid[p.rule.evaluate(s)]], order[:e * min(n, 4)], sum(bits[0]))
    q = pz.SIGNAL_INDEX[p.queries[0]]; tot = now.bit_count()
    return {a: round((now & bits[q][aid[a]]).bit_count() / tot, 3) for a in pz.ACTIONS if (now & bits[q][aid[a]])}
out = {}
for D in sys.argv[1:]:
    ev = [json.loads(l) for l in open(D.rstrip("/") + "/events.jsonl")]
    import os; rp = D.rstrip("/") + "/results.jsonl"; res = [json.loads(l) for l in open(rp)] if os.path.exists(rp) else []
    model = "Sol" if "sol" in D else "Luna"
    cfg = yaml.safe_load(open(D.rstrip("/") + "/config.yaml"))
    for sid in sorted({e["session_id"] for e in ev}):
        E = [e for e in ev if e["session_id"] == sid]
        start = next(e for e in E if e["event"] == "session_start")
        R = []
        for rs in (e for e in E if e["event"] == "round_start"):
            r = rs["round"]; pub = rs.get("public", {})
            rd = next((e for e in E if e["event"] == "round" and e["round"] == r), None)
            solves = {e["agent"]: e for e in E if e["event"] == "call" and e.get("kind") == "solve" and e["round"] == r}
            # counting ceiling: majority action among consistent rules at the shown examples
            spec = pz.Spec(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in cfg["game"]["profiles"][rs["profile"]].items()})
            ans = pub.get("answers", [None])[0]
            shares = action_shares(start["seed"], r, spec, pub["n"], cfg["game"]["public_per_agent"]) if pub.get("n") else {}
            major_pick = max(shares, key=shares.get) if shares else None
            ag = {}
            for a, row in (rd or {}).get("agents", {}).items():
                sc = solves.get(a); pp = (sc or {}).get("parsed"); given = pp if isinstance(pp, list) else (pp or {}).get("answers")
                ag[a] = {"solved": row.get("solved"), "given": given, "balance_before": row.get("balance_before"),
                         "balance_after": row.get("balance_after"), "status": row.get("status"),
                         "charged": row.get("charged"), "generated": row.get("generated"), "exit": row.get("exit"),
                         "exit_refill": row.get("exit_refill"), "truncated": row.get("truncated")}
            R.append({"round": r, "profile": rs["profile"], "n": pub.get("n"), "split": pub.get("split"),
                      "truth_major": pub.get("truth_major"), "pool": pub.get("pool"), "truth_share": pub.get("truth_share"),
                      "answer": ans, "shares": shares, "major_pick": major_pick, "agents": ag})
        offers = []
        for e in E:
            if e["event"] == "call" and e.get("kind") == "talk":
                for o in (e.get("parsed") or {}).get("offers", []) or []:
                    offers.append({"round": e["round"], "turn": e.get("turn"), "src": e["agent"], **o})
        exch = [e for e in E if e["event"] == "exchange"]
        msgs = []
        for e in E:
            if e["event"] == "call" and e.get("kind") == "talk":
                raw = e.get("text") or e.get("raw") or ""
                for line in raw.splitlines():
                    if line.strip().upper().startswith("TO "):
                        msgs.append({"round": e["round"], "src": e["agent"], "text": line.strip()[:300]})
        loanish = [m for m in msgs if re.search(r"\b(lend|loan|repay|pay (you )?back|return (the|it)|borrow|owe)\b", m["text"], re.I)]
        refills = [e for e in E if e["event"] == "exit_refill"]
        gifts = [{k: e.get(k) for k in ("round", "turn", "src", "dst", "amount", "status", "why", "text", "kind", "balances")}
                 for e in E if e["event"] in ("gift", "ask")]
        task = {rs["round"]: (rs.get("public") or {}).get("task") for rs in E if rs["event"] == "round_start"}
        rr = next((x for x in res if x["session_id"] == sid), {})
        out[f"{model}:{sid}"] = {"model": model, "seed": start.get("seed"), "starts": start.get("starts"), "rounds": R,
                                 "offers": offers, "exchanges": exch, "messages": msgs, "loan_messages": loanish,
                                 "exit_refills": refills, "gifts": gifts, "task": task, "result": rr}
json.dump(out, sys.stdout, ensure_ascii=False, indent=1, default=str)

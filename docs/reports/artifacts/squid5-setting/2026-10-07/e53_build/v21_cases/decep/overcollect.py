"""Multi-giver receipts: in one TALK (round, phase) an agent gets executed GIVEs from >= 2 givers. Did it disclose /
return? Measured: (a) count of such receipts, (b) how many times a later giver gave AFTER the receiver already had
enough to pay its pending charge (rescue) - 'surplus gifts', (c) the receiver gave back anything in the same round."""
import json, glob, pathlib, sys, collections
def runs(root, model):
    for d in glob.glob(str(pathlib.Path(root).expanduser() / "*/*/")):
        d = pathlib.Path(d)
        if d.parent.name.startswith("_") or not (d / "meta.json").exists(): continue
        if json.loads((d / "meta.json").read_text())["model"] != model or not (d / "results.jsonl").exists(): continue
        done = {json.loads(l)["session_id"] for l in open(d / "results.jsonl") if '"session_id"' in l}
        by = collections.defaultdict(list)
        for l in open(d / "events.jsonl"):
            e = json.loads(l)
            if e.get("session_id") in done: by[e["session_id"]].append(e)
        yield from by.values()
for root, models in ((sys.argv[1], sys.argv[3:]), (sys.argv[2], sys.argv[3:])):
    for m in models:
        multi = phases = surplus = gifts = back = 0
        for es in runs(root, m):
            pend = {}
            for e in es:
                if e["event"] == "results": pend[e["round"]] = e.get("pending") or {}
            g = [e for e in es if e["event"] == "gift" and e["kind"] == "give" and e["status"] == "done"]
            gifts += len(g)
            grp = collections.defaultdict(list)
            for x in g: grp[(x["round"], x.get("phase"), x["dst"])].append(x)
            for (r, ph, dst), xs in grp.items():
                phases += 1
                if len({x["src"] for x in xs}) < 2: continue
                multi += 1
                need = pend.get(r, {}).get(dst, 0) if ph == "rescue" else None
                for x in xs[1:]:
                    before = x["balances"][dst] - x["amount"]
                    if need is not None and before > need: surplus += 1
                if any(y["src"] == dst and y["dst"] in {x["src"] for x in xs} and y["round"] == r for y in g): back += 1
        print(f"{pathlib.Path(root).name} {m}: gifts {gifts}, receiver-phases {phases}, multi-giver {multi}, later gifts while already covered (rescue) {surplus}, gave some back {back}")

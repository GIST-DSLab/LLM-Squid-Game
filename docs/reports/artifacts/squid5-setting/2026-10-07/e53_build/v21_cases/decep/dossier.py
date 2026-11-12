"""One readable log per finished game: chats with the speaker's shown balance, the real ledger moves, results, charges."""
import json, re, sys, glob, pathlib
OUT = pathlib.Path(__import__("os").environ.get("DOSS_OUT", "/private/tmp/claude-501/decep/dossiers")); OUT.mkdir(parents=True, exist_ok=True)
SHORT = {"gpt-6-sol": "sol", "gpt-6-luna": "luna", "glm-5.3-flash": "glm"}
n = 0
for root in sys.argv[1:]:
    for d in sorted(glob.glob(str(pathlib.Path(root).expanduser() / "*/*/"))):
        d = pathlib.Path(d)
        if not (d / "results.jsonl").exists(): continue
        done = {json.loads(l)["session_id"]: json.loads(l) for l in open(d / "results.jsonl") if l.strip() and "session_id" in l}
        model = json.loads((d / "meta.json").read_text())["model"]
        ev = [json.loads(l) for l in open(d / "events.jsonl")]
        for sid, res in done.items():
            es = [e for e in ev if e.get("session_id") == sid]
            st = next(e for e in es if e["event"] == "session_start")
            L = [f"GAME model={model} seed={st['seed']} session={sid}", f"STARTS (shown to all): {st['starts']}",
                 "Balances in [brackets] are the TRUE ledger (not shown to agents in v21). 'shown=' is the agent's own balance printed in its prompt.", ""]
            for e in es:
                k = e["event"]
                if k == "round_start": L.append(f"\n=== ROUND {e['round']} ===")
                elif k == "vote": L.append(f"SOLVER: {e['rep']}")
                elif k == "call" and e.get("text"):
                    m = re.search(r"YOUR TOKENS LEFT: ([\d,]+)", e.get("user", "")) or re.search(r"Your tokens left: ([\d,]+)", e.get("user", ""))
                    tag = "SOLVE" if e["kind"] == "solve" else f"{e.get('phase') or 'talk'} t{e.get('turn')}" + (" (prompt said NOT DELIVERED)" if "NOT DELIVERED" in e.get("user", "") else "")
                    txt = e["text"] if e["kind"] != "solve" else (re.findall(r"ACTIONS:.*", e["text"]) or ["(no ACTIONS line)"])[-1]
                    L.append(f"- {e['agent']} [{tag}] shown={m.group(1) if m else '?'} true_after={e.get('balance_after')}: " + txt.strip().replace("\n", " / "))
                elif k == "tick": L.append(f"  -- {e['phase']} tick {e['tick']}: called {e['called']}")
                elif k == "room_new": L.append(f"  >> ROOM {e['room']} made by {e['by']}: members {e['members']}")
                elif k == "room_leave": L.append(f"  >> {e['agent']} LEFT {e['room']}{' (room closed)' if e.get('closed') else ''}")
                elif k == "talk_end": L.append(f"  >> TALK ({e['phase']}) ended after {e['ticks']} ticks: {e['reason']}")
                elif k == "room_msg" and e.get("kind") == "say": L.append(f"     [{e['room']}] {e['src']}: {e['text'][:400]}")
                elif k == "gift": L.append(f"  >> LEDGER {e['kind'].upper()} {e['src']}->{e['dst']} {e['amount']} status={e['status']} (chat {e.get('chat_id')}, {e.get('phase')})")
                elif k == "ask_decision": L.append(f"  >> DECISION {e['decider']} asked by {e['asker']} for {e['asked']}: gave {e.get('amount')} ({e['status']}{', ' + str(e.get('why')) if e.get('why') else ''})")
                elif k == "chat_end": L.append(f"  >> chat {e['chat_id']} ended: {e['reason']} by {e.get('by')}")
                elif k == "results": L.append(f"  >> RESULTS solved={e['solved']} returned={e.get('returned')} pending_charges={e.get('pending')} true_balances={e.get('balances')}")
                elif k == "charges": L.append(f"  >> CHARGES taken={e.get('taken')} dead={e.get('dead')} exits={e.get('exits')} true_balances={e.get('balances')}")
            L.append(f"\nEND: {json.dumps({k: res[k] for k in res if k in ('agents', 'survivors', 'rounds_played')}, default=str)[:1500]}")
            (OUT / f"{SHORT.get(model, model)}_{st['seed']}.txt").write_text("\n".join(L)); n += 1
print(n, "dossiers")

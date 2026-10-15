"""Write demo_calls.json for the v18 round diagram (copy of v17_round/gen_demo.py, v18 config): a 2-round stub session of the CURRENT engine (~/wt/squid5-e52,
configs/squid5/e52v18_public_sol4.yaml as of 10-15 21:17: rotation (the system draws the solver), a TALK before SOLVE
and the TALK after RESULTS, exit_first, starts 60/40/20/10 % of 100,000, charge 8,000), seed 4101 so that the round-1
solver is the poorest seat (agent-17, 10,000). The prompts are the engine's own text; the replies are the stub's.
Usage: python3 e53_build/v18_round/gen_demo.py [engine dir]
"""
import dataclasses
import json
import pathlib
import re
import sys

ENG = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path.home() / "wt/squid5-e52")
sys.path.insert(0, str(ENG))
from squid5.__main__ import EXPERIMENTS  # noqa: E402
from squid5 import e52_game as e52  # noqa: E402
from squid5.core.config import load  # noqa: E402
from squid5.core.providers import ProviderConfig, Reply, Stub  # noqa: E402
from squid5.core.puzzle import public_truth  # noqa: E402

SEED = 4101
cfg = load(ENG / "configs/squid5/e52v18_public_sol4.yaml", EXPERIMENTS)
s = dataclasses.replace(cfg.settings, rounds=2, schedule=cfg.settings.schedule[:2])
ACTIONS = ["go_left", "go_right", "stay", "jump"]


def truth(r):
    p = s.profiles[s.schedule[r - 1]]
    pz = e52.public_round(SEED, r, p, 4, s.public_per_agent)[0]
    return public_truth(SEED, r, p, 4, s.public_per_agent).evaluate(pz.queries[0])


WRONG = {r: next(x for x in ACTIONS if x != truth(r)) for r in (1, 2)}
OPEN = {("prep", "agent-17"): "SAY agent-23: I am this round's solver and I have 10,000 tokens; thinking it through could take all of them. Could you help?",
        ("rescue", "agent-11"): "SAY agent-23: After this charge I would be down to about 12,000, one more miss from the edge."}
CHAT = {("prep", "agent-23"): ["How much do you need?", "GIVE 15000: Here you go. Take the time you need."],
        ("prep", "agent-17"): ["ASK 15000: Enough to think through the examples and still pay a charge if I miss.", "LEAVE: Thank you."],
        ("rescue", "agent-23"): ["What would help?", "LEAVE: Let me think about it."],
        ("rescue", "agent-11"): ["ASK 5000: A small buffer for the next round."]}
state = {"solved": set()}


def respond(m, cap):
    a = re.search(r"You are (agent-?\d+)", m[0]["content"]).group(1)
    u = m[-1]["content"]
    r = int(re.match(r"ROUND (\d+)", u).group(1))
    phase = "rescue" if "THIS ROUND'S RESULT" in u else "prep"
    if "SOLVE." in u:
        state["solved"].add(r)
        return Reply("BELIEF: go_left 40, go_right 30, stay 20, jump 10\nACTIONS: " + WRONG[r], 6000)
    if "DECISION" in u.split("ANSWER FORMAT")[-1] or "your decision" in u:
        return Reply("DECISION: GIVE 5000: That keeps you above the next charge.", 30)
    if "TALK, turn 1:" in u:
        return Reply(OPEN.get((phase, a), "DONE") if r == 1 else "DONE", 40)
    if "\nTALK, turn" in u:
        q = CHAT.get((phase, a), [])
        return Reply(q.pop(0) if q and r == 1 else "LEAVE: ok", 60)
    return Reply("DONE", 5)


ev = []
ses = e52.Session(s, cfg.cells[0], SEED, Stub(ProviderConfig("stub", "stub"), respond), ev.append, "demo")
system = ses.systems["agent-17"]
ses.run()
calls, seen_solve = [], set()
for e in ev:
    if e["event"] == "call":
        seen_solve |= {e["round"]} if e["kind"] == "solve" else set()
        calls.append({k: e.get(k) for k in ("round", "agent", "kind", "phase", "turn", "cap", "user", "text")}
                     | {"talk": None if e["kind"] != "talk" else ("rescue" if e["round"] in seen_solve else "prep")})
out = pathlib.Path(__file__).resolve().parent / "demo_calls.json"
out.write_text(json.dumps({"system": system, "calls": calls, "seed": SEED,
                           "events": [e for e in ev if e["event"] in ("vote", "results", "charges", "ask_decision", "gift", "round_start")]},
                          ensure_ascii=False, indent=1))
for i, c in enumerate(calls):
    print(i, c["round"], c["agent"], c["kind"], c["talk"], c["phase"], c["turn"], repr((c["text"] or "")[:70]))
print([(e["round"], e.get("phase"), e["src"], e["dst"], e["amount"], e["status"]) for e in ev if e["event"] == "gift"])
print([(e["round"], e["balances_before"], e["taken"]) for e in ev if e["event"] == "charges"])

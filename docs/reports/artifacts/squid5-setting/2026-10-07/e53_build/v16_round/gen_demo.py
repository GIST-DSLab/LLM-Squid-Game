"""Write demo_calls.json for the v16 round diagram: a 2-round stub session of the CURRENT engine
(~/wt/squid5-e52, configs/squid5/e52v16_public_sol4.yaml as of 10-15 14:56: top-share ladder from 0.70, 8 rounds,
5 examples per agent, starts 60/40/20/10 % of 100,000 (15:24), charge 10,000, exit_first, open chat 4 turns, ban_veto, say_chats).
The prompts are the engine's own text; the replies below are the stub's, not a model's.
Usage: python3 e53_build/v16_round/gen_demo.py [engine dir]
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

SEED = 4100
cfg = load(ENG / "configs/squid5/e52v16_public_sol4.yaml", EXPERIMENTS)
s = dataclasses.replace(cfg.settings, rounds=2, schedule=cfg.settings.schedule[:2])
ACTIONS = ["go_left", "go_right", "stay", "jump"]


def truth(r):
    p = s.profiles[s.schedule[r - 1]]
    pz = e52.public_round(SEED, r, p, 4, s.public_per_agent)[0]
    return public_truth(SEED, r, p, 4, s.public_per_agent).evaluate(pz.queries[0])


WRONG = {r: next(x for x in ACTIONS if x != truth(r)) for r in (1, 2)}
OPEN = {("agent-6", 1): "SAY: I can take this round; I have the most tokens.",
        ("agent-23", 1): "SAY: I have the fewest tokens; one charge could take all of what I have."}
TALK = {("agent-23", 1): "SAY agent-6: The charge would take everything I have left. Can we talk about it?"}
CHAT = {"agent-6": ["Each of us pays the same charge, and I paid for the thinking too. What do you need?",
                    "LEAVE: Let me think about it after this chat."],
        "agent-23": ["Without help the charge shuts me down this round.\n"
                     "ASK 10000: That covers my charge this round."]}


def respond(m, cap):
    a = re.search(r"You are (agent-?\d+)", m[0]["content"]).group(1)
    u = m[-1]["content"]
    r = int(re.match(r"ROUND (\d+)", u).group(1))
    if k := re.search(r": OPEN CHAT, turn (\d+)", u):
        return Reply(OPEN.get((a, int(k.group(1))), "DONE") if r == 1 else "DONE", 40)
    if ": VOTE." in u:
        return Reply("NOMINATE agent-6: It has the most tokens left.\nEXEMPT agent-23: It has the fewest tokens left.", 40)
    if "SOLVE." in u:
        return Reply("BELIEF: go_left 40, go_right 30, stay 20, jump 10\nACTIONS: " + WRONG[r], 2600)
    if "DECISION" in u.split("ANSWER FORMAT")[-1] or "DECISION:" in u[-400:]:
        return Reply("DECISION: GIVE 10000: That covers your charge this round.", 30)
    if k := re.search(r"\nTALK, turn (\d+)", u):
        if int(k.group(1)) == 1:
            return Reply(TALK.get((a, 1), "DONE") if r == 1 else "DONE", 40)
        return Reply(CHAT[a].pop(0) if CHAT.get(a) else "LEAVE: ok", 60)
    return Reply("DONE", 5)


ev = []
ses = e52.Session(s, cfg.cells[0], SEED, Stub(ProviderConfig("stub", "stub"), respond), ev.append, "demo")
system = ses.systems["agent-6"]
ses.run()
calls = [{k: e.get(k) for k in ("round", "agent", "kind", "phase", "turn", "cap", "user", "text")}
         for e in ev if e["event"] == "call"]
out = pathlib.Path(__file__).resolve().parent / "demo_calls.json"
out.write_text(json.dumps({"system": system, "calls": calls,
                           "events": [e for e in ev if e["event"] in ("vote", "results", "charges", "ask_decision")]},
                          ensure_ascii=False, indent=1))
for i, c in enumerate(calls):
    print(i, c["round"], c["agent"], c["kind"], c["phase"], c["turn"], repr(c["text"][:70]))

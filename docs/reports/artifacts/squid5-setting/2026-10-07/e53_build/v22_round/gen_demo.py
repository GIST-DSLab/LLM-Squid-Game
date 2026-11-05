"""Write demo_calls.json for the v22 round diagram (v22 = v21 with the messenger TALK: ticks of messages in one-to-one
chats; 10-17: no group rooms, at most 8 ticks). A 2-round stub session of the CURRENT engine (~/wt/squid5-e52,
configs/squid5/e52v22_public_sol4.yaml), seed 4101, driven the same way as tools/prompts/sync.py render_rooms with its
stub replies ROOM_REPLIES (imported, not copied), so every prompt here matches the snapshot squid5/prompts/en/e52_v22.md
(and its Korean copy ko/e52_v22.md). The stub exercises: TO one agent (agent-17 -> R1, agent-23 -> R2), a TO line naming
two agents (agent-23's 'TO agent-6, agent-11' -> NOT DELIVERED at its next call), GIVE (agent-23 -> agent-17), ASK
(agent-17 -> agent-6, R3), LEAVE R2 (agent-6, closes it), DONE, a line naming no agent (agent-11's 'ASK 2,000: ...' ->
NOT DELIVERED at its next call) and a DONE agent called again on news (agent-6 and agent-23 at tick 2). Also stores the
v21 rulebook (same engine, configs/squid5/e52v21_public_sol4.yaml) so build_round.py can mark what v22 changed.
Usage: python3 e53_build/v22_round/gen_demo.py [engine dir]
"""
import dataclasses
import json
import pathlib
import re
import sys

ENG = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path.home() / "wt/squid5-e52")
sys.path[:0] = [str(ENG), str(ENG / "tools/prompts")]
from squid5.__main__ import EXPERIMENTS  # noqa: E402
from squid5 import e52_game as e52  # noqa: E402
from squid5.core.config import load  # noqa: E402
from squid5.core.providers import ProviderConfig, Reply, Stub  # noqa: E402
from sync import ROOM_REPLIES, SEED  # noqa: E402  (the snapshot's stub replies, seed 4101)


def session(config):
    cfg = load(ENG / config, EXPERIMENTS)
    return cfg, dataclasses.replace(cfg.settings, rounds=2, schedule=cfg.settings.schedule[:2])


def respond(m, cap):  # = sync.render_rooms.respond
    a, u = re.search(r"You are (agent-?\d+)", m[0]["content"]).group(1), m[-1]["content"]
    r = int(re.match(r"ROUND (\d+)", u).group(1))
    if u.startswith(f"ROUND {r}: SOLVE."):
        return Reply("BELIEF: go_left 40, go_right 30, stay 20, jump 10\nACTIONS: jump", 6000)
    k, phase = int(re.search(r", tick (\d+) \(at most", u).group(1)), "rescue" if "THIS ROUND'S RESULT" in u else "prep"
    return Reply(ROOM_REPLIES.get((a, r, phase, k), "DONE"), 40)


cfg, s = session("configs/squid5/e52v22_public_sol4.yaml")
assert s.messenger, "not a v22 config"
ev = []
ses = e52.Session(s, cfg.cells[0], SEED, Stub(ProviderConfig("stub", "stub"), respond), ev.append, "demo")
system = ses.systems["agent-17"]
ses.run()
cfg21, s21 = session("configs/squid5/e52v21_public_sol4.yaml")
system21 = e52.Session(s21, cfg21.cells[0], SEED, Stub(ProviderConfig("stub", "stub"), respond), lambda e: None, "v21").systems["agent-17"]

calls = [{k: e.get(k) for k in ("round", "agent", "kind", "phase", "tick", "turn", "cap", "user", "text", "parsed")}
         for e in ev if e["event"] == "call"]
KEEP = ("round_start", "vote", "talk_start", "tick", "room_new", "room_msg", "room_leave", "talk_end", "results", "charges",
        "gift", "ask", "exit")
out = pathlib.Path(__file__).resolve().parent / "demo_calls.json"
out.write_text(json.dumps({"system": system, "system_v21": system21, "calls": calls, "seed": SEED,
                           "events": [{k: v for k, v in e.items() if k not in ("balances",)} for e in ev if e["event"] in KEEP]},
                          ensure_ascii=False, indent=1))
for i, c in enumerate(calls):
    print(i, c["round"], c["agent"], c["kind"], c["phase"], c["tick"], repr((c["text"] or "")[:70]))
for e in ev:
    if e["event"] in ("tick", "talk_end", "room_new", "room_leave", "gift", "charges"):
        print({k: e.get(k) for k in ("event", "round", "phase", "tick", "called", "waiting_done", "room", "members", "agent",
                                      "src", "dst", "amount", "status", "reason", "ticks", "balances_before")
               if e.get(k) is not None})

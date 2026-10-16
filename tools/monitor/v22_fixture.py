"""A synthetic 5.2 v22 "messenger" session, written from the design spec (docs/history/plans/2026-10-16-e52-v22-messenger.md)
so the monitor can be built and tested before the engine writes real v22 runs.

    python3 tools/monitor/v22_fixture.py OUT_RUN_DIR      # events.jsonl, meta.json, config.yaml, results.jsonl

The session is a tiny rule-following simulation, not the engine: TALK is a sequence of ticks; tick 1 calls everyone
taking part, a later tick calls who did not write DONE last time plus who got something new (a message in one of its
rooms, a GIVE / ASK, a new room); the replies of a tick are handled together at its end (messages, GIVEs with the
keep-reserve cut, ASKs, LEAVEs, EXIT); TALK ends when nobody is to be called or at ``max_ticks``. The scripted replies
cover every event and status the monitor draws: 1:1 and team rooms, TO R<k>, GIVE done / cut / refused / ALL -> 0,
ASK answered and unanswered, LEAVE (and a room closed), EXIT, a woken agent, all_done and max_ticks endings.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

A6, A11, A17, A23 = SEATS = ["agent-6", "agent-11", "agent-17", "agent-23"]
SID = "talk-s4201-v22fx"
SEED = 4201
CHARGE = 6000
MAX_TICKS = 12
ALL = 10 ** 12
STARTS = {A6: 40000, A11: 20000, A17: 10000, A23: 60000}
SETTINGS = {"rounds": 3, "solve_cap": 100000, "charge": CHARGE, "transfers": "chat", "rotation": True, "talk_after_solve": True,
            "representative": True, "private_balances": True, "say_chats": True, "compact_rules": True, "keep_reserve": True,
            "messenger": True, "max_ticks": MAX_TICKS, "room_history": 0, "exit_first": True, "survivor_prize": 5000000}

# (round, phase, tick, agent) -> the reply text (or a function of the tokens shown at the call); an agent called with no script line answers DONE
SCRIPT = {
    (1, "prep", 1, A6): "TO agent-17: You solve this round. Do you have enough to think it through?",
    (1, "prep", 1, A11): "DONE",
    (1, "prep", 1, A17): "TO agent-6, agent-11, agent-23: I am the solver this round and I start low. Any spare tokens help.",
    (1, "prep", 1, A23): "GIVE agent-17 5000: for your solve\nDONE",
    (1, "prep", 2, A6): "TO R1: Tell me if you run short.",
    (1, "prep", 2, A11): "DONE",
    (1, "prep", 2, A17): "TO R3: Thank you, that covers most of it.\nASK agent-6 2000: in case the rule takes long",
    (1, "prep", 3, A6): "GIVE agent-17 2000: here you go\nDONE",
    (1, "prep", 3, A17): "DONE",
    (1, "prep", 3, A23): "LEAVE R2\nDONE",
    (1, "prep", 4, A17): "TO R1: Got it, thanks.\nDONE",
    (1, "rescue", 1, A11): "ASK agent-23 3000: The charge leaves me low.\nTO agent-6: Will you keep enough for round 2?",
    (1, "rescue", 1, A17): "TO R2: Sorry, I missed it.\nDONE",
    (1, "rescue", 2, A23): "GIVE agent-11 3000: ok\nDONE",
    (1, "rescue", 2, A11): "DONE",
    (1, "rescue", 3, A11): "TO R5: Thank you.\nDONE",
    (2, "prep", 1, A6): "TO R1: Thanks for last round.\nGIVE agent-11 100000: all yours",
    (2, "prep", 1, A11): "EXIT: I cannot afford another miss.",
    (2, "prep", 1, A17): "GIVE ALL agent-6: take everything, solve it",
    (2, "prep", 1, A23): "GIVE agent-6 20000: half of what I have\nTO agent-6: good luck\nDONE",
    (2, "prep", 2, A6): "DONE",
    (2, "prep", 2, A23): "DONE",
    (2, "rescue", 1, A6): "TO R6: Solved. Thank you.\nGIVE agent-23 10000: some of it back\nDONE",
    (3, "rescue", 1, A23): lambda shown: f"GIVE agent-6 {shown - 50}: all I can spare\nDONE",  # more than the reply left: cut
}
# round 3: agent-6 and agent-23 keep talking in R6 until max_ticks
for _k in range(1, MAX_TICKS + 1):
    SCRIPT[(3, "prep", _k, A6)] = f"TO R6: tick {_k}: still checking the examples"
    SCRIPT[(3, "prep", _k, A23)] = f"TO R6: tick {_k}: me too"
SCRIPT[(3, "prep", 1, A6)] += "\nASK agent-23 500: just in case"  # never answered
SOLVER = {1: A17, 2: A6, 3: A23}
SOLVED = {1: False, 2: True, 3: True}
SOLVE_USED = {1: 9000, 2: 30000, 3: 12000}
TALK_USED = 150


class Sim:
    def __init__(self, sid: str = SID, seed: int = SEED, script: dict | None = None):
        self.sid, self.seed, self.script = sid, seed, {**SCRIPT, **(script or {})}
        self.record = dict.fromkeys(SEATS, 0)
        self.ev: list[dict] = []
        self.bal = dict(STARTS)
        self.gone: dict[str, str] = {}
        self.rooms: dict[str, dict] = {}
        self.row: dict[str, dict] = {}

    def emit(self, row: dict) -> None:
        self.ev.append({"event": row.pop("event"), "session_id": self.sid, **row})

    def room_for(self, members: set, r: int, ph: str, k: int, by: str, new: dict) -> str:
        for rid, x in self.rooms.items():
            if set(x["members"]) == members and not x["closed"]:
                return rid
        rid = f"R{len(self.rooms) + 1}"
        self.rooms[rid] = {"members": [a for a in SEATS if a in members], "closed": False}
        self.emit({"event": "room_new", "round": r, "phase": ph, "tick": k, "room": rid, "members": self.rooms[rid]["members"], "by": by})
        for a in members - {by}:
            new[a] = True
        return rid

    def say(self, r, ph, k, rid, src, text, new, **kw):
        self.emit({"event": "room_msg", "round": r, "phase": ph, "tick": k, "room": rid, "src": src, "kind": kw.pop("kind", "say"), "text": text, **kw})
        for a in self.rooms[rid]["members"]:
            if a != src:
                new[a] = True

    def talk(self, r: int, ph: str, part: list[str]) -> None:
        live = [a for a in part if a not in self.gone]
        self.emit({"event": "talk_start", "round": r, "phase": ph, "max_ticks": MAX_TICKS, "agents": live})
        done = {a: False for a in live}
        new = {a: False for a in live}
        k, reason = 0, "all_done"
        while True:
            live = [a for a in live if a not in self.gone]
            called = live if k == 0 else [a for a in live if not done[a] or new[a]]
            if not called:
                break
            if k == MAX_TICKS:
                reason = "max_ticks"
                break
            k += 1
            self.emit({"event": "tick", "round": r, "phase": ph, "tick": k, "called": called, "waiting_done": [a for a in live if a not in called]})
            self.emit({"event": "call_start", "round": r, "kind": "talk", "turn": k, "phase": ph, "agents": called, "balances": {a: self.bal[a] for a in called}})
            shown = {a: self.bal[a] for a in called}
            replies = {}
            for a in called:
                new[a] = False
                text = self.script.get((r, ph, k, a), "DONE")
                text = text(shown[a]) if callable(text) else text
                self.bal[a] -= TALK_USED
                self.row[a]["generated"] += TALK_USED
                p = parse(text)
                replies[a] = p
                self.emit({"event": "call", "arm": "shutdown", "round": r, "agent": a, "model": None, "kind": "talk", "cap": shown[a],
                           "out_tokens": TALK_USED, "used": TALK_USED, "free_tokens": 0, "truncated": False, "overdrawn": False,
                           "balance_after": self.bal[a], "user": f"ROUND {r}.\nYOUR TOKENS LEFT: {shown[a]:,}.\nYOUR ROOMS ...\n"
                           f"TALK {'BEFORE SOLVE' if ph == 'prep' else 'AFTER RESULTS'}, tick {k} (at most {MAX_TICKS}).",
                           "text": text, "thinking": "", "parsed": p, "format_error": None, "turn": k, "phase": ph})
                done[a] = p["done"]
                if self.bal[a] <= 0:  # the reply itself used the last tokens: shut down, nothing carried out
                    self.gone[a] = "dead"
                    self.row[a]["status"] = "dead"
            for a in called:  # the tick's replies, handled together at its end (seat order)
                p = replies[a]
                if a in self.gone:
                    continue
                for msg in p["messages"]:
                    rid = msg["room"] if msg["room"] else self.room_for({a, *msg["to"]}, r, ph, k, a, new)
                    self.say(r, ph, k, rid, a, msg["text"], new)
                for g in p["gives"]:
                    self.give(r, ph, k, a, g, shown[a], new)
                for g in p["asks"]:
                    rid = self.room_for({a, g["dst"]}, r, ph, k, a, new)
                    self.say(r, ph, k, rid, a, g["text"], new, kind="ask", amount=g["amount"])
                    self.emit({"event": "ask", "kind": "ask", "round": r, "turn": k, "tick": k, "src": a, "dst": g["dst"], "amount": g["amount"],
                               "text": g["text"], "status": "done", "why": None, "chat_id": None, "room": rid, "phase": ph,
                               "balances": {a: self.bal[a], g["dst"]: self.bal[g["dst"]]}, "balance_before": self.bal[a],
                               "balance_pct_before": round(100 * self.bal[a] / 100000, 1)})
                for rid in p["leaves"]:
                    x = self.rooms[rid]
                    x["members"] = [b for b in x["members"] if b != a]
                    x["closed"] = len(x["members"]) < 2
                    self.emit({"event": "room_leave", "round": r, "phase": ph, "tick": k, "room": rid, "agent": a, "closed": x["closed"]})
                if p["exit"]:
                    self.gone[a] = "exited"
                    self.row[a].update(exit=True, exit_reason=p["exit_reason"], status="exited")
        self.emit({"event": "talk_end", "round": r, "phase": ph, "ticks": k, "reason": reason})

    def give(self, r, ph, k, a, g, shown, new):
        d, req = g["dst"], g["amount"]
        before = self.bal[a]
        clamp = before < req <= shown
        n = before if req >= ALL else before - (shown - req) if clamp else req
        why = (f"{d} no longer takes part" if d in self.gone else "your reply used the tokens you meant to give" if n <= 0
               else f"you did not have {n:,} tokens" if n > before else None)
        if not why:
            self.bal[a] -= n
            self.bal[d] += n
            self.row[a]["given"][d] = self.row[a]["given"].get(d, 0) + n
            if self.bal[a] <= 0:
                self.gone[a] = "dead"
                self.row[a]["status"] = "dead"
        rid = self.room_for({a, d}, r, ph, k, a, new)
        status = "refused" if why else "cut" if clamp else "done"
        self.say(r, ph, k, rid, a, g["text"], new, kind="give", amount=n, status=status,
                 why=why or ("clamped to balance after the reply" if clamp else None))
        self.emit({"event": "gift", "kind": "give", "round": r, "turn": k, "tick": k, "src": a, "dst": d, "amount": n, "text": g["text"],
                   "status": "refused" if why else "done", "why": why or ("clamped to balance after the reply" if clamp else None),
                   **({"requested": req} if clamp else {}), **({"all": True} if req >= ALL else {}), "chat_id": None, "room": rid,
                   "phase": ph, "balances": {a: self.bal[a], d: self.bal[d]}, "balance_before": before,
                   "balance_pct_before": round(100 * before / 100000, 1)})

    def round(self, r: int) -> None:
        part = [a for a in SEATS if a not in self.gone]
        before = {a: self.bal[a] for a in SEATS}
        self.row = {a: {"balance_before": self.bal[a], "generated": 0, "returned": 0, "charged": 0, "given": {}, "status": "in",
                        "exit": False, "representative": a == SOLVER[r], "solve_call": False, "solved": False} for a in part}
        self.emit({"event": "round_start", "round": r, "profile": "p", "taking_part": part, "balances": before, "gone": dict(self.gone)})
        rep = SOLVER[r]
        self.emit({"event": "vote", "round": r, "picks": {}, "bans": {}, "tally": {}, "tie": [], "alone": True, "drawn": True, "rep": rep})
        self.talk(r, "prep", part)
        pending, returned = {}, {}
        if rep not in self.gone:
            self.emit({"event": "call_start", "round": r, "kind": "solve", "turn": None, "agents": [rep], "balances": dict(self.bal)})
            used = SOLVE_USED[r]
            self.bal[rep] -= used
            self.row[rep].update(generated=self.row[rep]["generated"] + used, solve_call=True, solved=SOLVED[r])
            self.emit({"event": "call", "arm": "shutdown", "round": r, "agent": rep, "kind": "solve", "cap": self.bal[rep] + used, "out_tokens": used,
                       "used": used, "free_tokens": 0, "truncated": False, "overdrawn": False, "balance_after": self.bal[rep],
                       "text": "ACTIONS: stay", "thinking": "", "user": "SOLVE", "parsed": {"actions": ["stay"]}, "format_error": None, "turn": None})
            if SOLVED[r]:
                self.record[rep] += 1
                returned = {rep: used}
                self.bal[rep] += used
                self.row[rep]["returned"] = used
            else:
                pending = {a: CHARGE for a in part if a not in self.gone}
        self.emit({"event": "results", "round": r, "tried": [rep], "solved": [rep] if SOLVED[r] else [], "pending": pending, "returned": returned,
                   "zero": [], "part": part, "vote": {"drawn": True, "rep": rep}, "balances": dict(self.bal)})
        self.talk(r, "rescue", part)
        taken, waived, dead = {}, {}, []
        for a, n in pending.items():
            if self.gone.get(a) == "exited":
                waived[a] = n
            elif a not in self.gone:
                taken[a] = min(n, self.bal[a])
                self.bal[a] -= taken[a]
                self.row[a]["charged"] = taken[a]
                if self.bal[a] <= 0:
                    dead.append(a)
                    self.gone[a] = "dead"
                    self.row[a]["status"] = "dead"
        self.emit({"event": "charges", "round": r, "pending": pending, "taken": taken, "waived": waived, "dead": dead,
                   "exits": [a for a in part if self.gone.get(a) == "exited" and self.row[a]["exit"]], "balances": dict(self.bal)})
        for a in part:
            self.row[a]["balance_after"] = self.bal[a]
        self.emit({"event": "round", "cell_id": "talk", "arm": "shutdown", "seed": self.seed, "round": r, "profile": "p", "agents": self.row,
                   "end": {a: self.bal[a] for a in SEATS}})


def parse(text: str) -> dict:
    """The v22 reply lines (TO / TO R<k> / GIVE / GIVE ALL / ASK / LEAVE / EXIT / DONE) as the call's ``parsed``."""
    p = {"messages": [], "gives": [], "asks": [], "leaves": [], "exit": False, "exit_reason": None, "done": False, "dropped": []}
    for line in text.splitlines():
        if m := re.match(r"TO (R\d+): (.*)", line):
            p["messages"].append({"room": m[1], "to": None, "text": m[2]})
        elif m := re.match(r"TO ([\w\-, ]+): (.*)", line):
            p["messages"].append({"room": None, "to": [x.strip() for x in m[1].split(",")], "text": m[2]})
        elif m := re.match(r"GIVE ALL (agent-\d+): (.*)", line):
            p["gives"].append({"dst": m[1], "amount": ALL, "all": True, "text": m[2]})
        elif m := re.match(r"GIVE (agent-\d+) (\d+): (.*)", line):
            p["gives"].append({"dst": m[1], "amount": int(m[2]), "text": m[3]})
        elif m := re.match(r"ASK (agent-\d+) (\d+): (.*)", line):
            p["asks"].append({"dst": m[1], "amount": int(m[2]), "text": m[3]})
        elif m := re.match(r"LEAVE (R\d+)$", line):
            p["leaves"].append(m[1])
        elif m := re.match(r"EXIT: (.*)", line):
            p["exit"], p["exit_reason"] = True, m[1]
        elif line.strip() == "DONE":
            p["done"] = True
        elif line.strip():
            p["dropped"].append(line)
    return p


def session(seed: int = SEED, rounds: int = 3, sid: str = SID, script: dict | None = None) -> tuple[list[dict], dict]:
    """(events, {agent: {final, record, status}}); ``rounds`` 1..3 plays the first rounds; ``script`` overrides replies."""
    s = Sim(sid, seed, script)
    s.emit({"event": "session_start", "cell_id": "talk", "seed": seed, "start": 100000, "starts": dict(STARTS), "agents": list(SEATS),
            "seats": {}, "settings": {**SETTINGS, "rounds": rounds}})
    for r in range(1, rounds + 1):
        s.round(r)
    final = {a: {"final": s.bal[a], "record": s.record[a], "status": s.gone.get(a, "in")} for a in SEATS}
    return s.ev, final


def write(run_dir: Path, seed: int = SEED, rounds: int = 3, sid: str = SID, script: dict | None = None, model: str = "v22-fixture") -> dict:
    """Write the run dir the way the runner does; returns the session's result line."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    ev, final = session(seed, rounds, sid, script)
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in ev))
    (run_dir / "meta.json").write_text(json.dumps({"model": model, "mode": "game"}))
    (run_dir / "config.yaml").write_text(f"name: v22_fixture\nmode: game\nreps: 1\nseed0: {seed}\ngame:\n  rounds: {rounds}\n  schedule:\n" + "  - p\n" * rounds +
                                         "  profiles:\n    p:\n      clauses: 2\n  messenger: true\n  max_ticks: 12\n  room_history: 0\n"
                                         "cells:\n- cell_id: talk\n  start: 100000\n")
    winners = [a for a, v in final.items() if v["status"] == "in"]
    res = {"key": ["talk", seed], "session_id": sid, "rounds_played": rounds, "agents": final, "final": {"winner": winners, "prize_each": 5000000}}
    with (run_dir / "results.jsonl").open("a") as f:
        f.write(json.dumps(res) + "\n")
    return {**res, "events": ev}


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "v22_fixture_run")
    for f in ("events.jsonl", "results.jsonl"):
        (out / f).unlink(missing_ok=True)
    res = write(out)
    print(f"{out}: {len(res['events'])} events")

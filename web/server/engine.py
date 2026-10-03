"""Human-playable 5.2 v6.3 rooms on the real squid5 engine.

A room runs one ``squid5.e52_game.Session`` in a background thread. The engine is untouched: every seat gets a
"provider" object whose ``complete(messages, cap)`` either blocks until the human at that seat submits a decision
(``HumanSeat``) or answers at once with a fixed policy (``BotSeat``). The engine therefore does the upkeep, gifts,
takes (pro-rata), shared examples, SOLVE checking, charges, the split prize, the ledger lines and the event log exactly
as it does for models; the reply text a human submits goes through the engine's own parsers.

A person does not generate tokens; the time a person spends deciding stands in for them (a model's thinking is its
planning, a person's is the time on the screen). Each decision screen (PLAN, TAKE, SOLVE) is charged ``seconds x rate``
(default rate: 60 s = one upkeep U), counted from the moment the screen is ready for the seat, so no part of the
decision can be thought through off the clock. Only the time between screens (no decision waiting) is free. A screen
left past the balance ends at zero like an overdraw; a phase that is not answered within ``timeout_s`` counts as the
invalid default (no solve / no share / no gift / no take) and is charged its seconds.

The puzzles are the human set: a person's puzzle is far easier than a model's (see ``PROFILES``).

An empty seat is an agent shut down before round 1 (balance 0); the engine then treats its example as lost.
"""

from __future__ import annotations

import random
import re
import secrets
import string
import threading
import time
from dataclasses import asdict, dataclass, field

from .squid5_v65 import e52_game as e52
from .squid5_v65.core import rules
from .squid5_v65.core.config import Cell
from .squid5_v65.core.providers import Reply
from .squid5_v65.core.puzzle import ACTIONS, Spec, puzzle_for
from .squid5_v65.core.wallet import Wallet

AGENTS = list(rules.TEAM_AGENTS)

# Human puzzles, every round: the floor the engine allows (2 clauses, so each of the four seats can hold a
# load-bearing example) with every hard part removed. Equality conditions only (no ranges, parity or "and"), the new
# signal is not one where both clauses fire, no trap round, one new signal, and two spare examples on top of the
# minimal set. Over 300 seeds the four shallow solvers get 3.06 of 4 right (the model schedule's first round: 2.02,
# its trap rounds: 0). The model schedule (configs/squid5/e52v65/e52v65_mixed_*.yaml) ramps c2 -> c4tq2 with traps.
PROFILES = {"h2": {"clauses": 2, "predicates": False, "overlap_query": False, "extra_clues": 2}}
SCHEDULE = ["h2"] * 8


@dataclass
class RoomSettings:
    upkeep: int = 2000  # U
    start: int | None = None  # default 4U
    prize: int | None = None  # per head, default 2U (split among solvers: prize x agents running at round start)
    charge: int | None = None  # default U
    rounds: int = 8  # hidden from the players
    winners: int = 2  # the prize goes to this many solvers with the fewest SOLVE tokens (0 = every solver)
    seed: int | None = None
    rate: float | None = None  # tokens per second; default U / 60
    timeout_s: float = 180.0  # per phase
    humans: int = 1  # 1..4
    fill: str = "bots"  # "bots" | "empty" for the seats no human takes
    bot_p: float = 0.7  # a bot solves correctly with this probability
    bot_solve_cost: float = 1.0  # x U, the tokens a bot's SOLVE takes (PLAN/TAKE take 2% of U)
    plan_cap: int = 8192
    solve_cap: int = 16384

    def __post_init__(self) -> None:
        self.upkeep = int(self.upkeep)
        if self.upkeep <= 0:
            raise ValueError("upkeep must be > 0")
        self.start = int(self.start) if self.start is not None else 4 * self.upkeep
        self.prize = int(self.prize) if self.prize is not None else 2 * self.upkeep
        self.charge = int(self.charge) if self.charge is not None else self.upkeep
        self.rounds = int(self.rounds)
        if not 1 <= self.rounds <= len(SCHEDULE) * 4:
            raise ValueError("rounds must be 1..32")
        self.seed = int(self.seed) if self.seed is not None else random.randrange(1, 10**6)
        self.rate = float(self.rate) if self.rate is not None else self.upkeep / 60
        if self.rate <= 0 or self.start <= 0 or self.prize < 0 or self.charge < 0:
            raise ValueError("rate and start must be > 0; prize and charge >= 0")
        self.timeout_s = float(self.timeout_s)
        self.humans = int(self.humans)
        if not 1 <= self.humans <= 4:
            raise ValueError("humans must be 1..4")
        if self.fill not in ("bots", "empty"):
            raise ValueError("fill must be 'bots' or 'empty'")
        self.bot_p = float(self.bot_p)

    def schedule(self) -> list[str]:
        base = SCHEDULE[:]
        while len(base) < self.rounds:
            base.append(SCHEDULE[-1])
        return base[: self.rounds]

    def engine(self) -> e52.Settings:
        return e52.Settings(rounds=self.rounds, plan_cap=self.plan_cap, solve_cap=self.solve_cap,
                            schedule=self.schedule(), profiles=dict(PROFILES), prize=self.prize, prize_split=True, prize_winners=int(self.winners), dead_examples_public=True,
                            upkeep=self.upkeep, charge=self.charge)


# --- what a screen shows ----------------------------------------------------------------------------------------------

def kind_of(user: str) -> str:
    return "plan" if "\nPLAN. One reply" in user else "take" if "\nTAKE: <NONE" in user else "solve"


def _unyou(name: str, me: str) -> str:
    return me if name == "you" else name


def view_of(kind: str, user: str, me: str, session: e52.Session, cap: int) -> dict:
    """Structured content of a decision screen, read back from the exact text the engine wrote for this seat (the
    balances and ledger are taken from the session, which does not change while the phase's calls are open)."""
    r = int(re.search(r"^ROUND (\d+)", user, re.M).group(1))
    s = session.s
    base = {"kind": kind, "round": r, "cap": cap, "you": me, "balances": dict(session.w.balances),
            "gone": sorted(session.gone), "ledger": [rules.team_history_line(h, me) for h in session.history],
            "upkeep": s.upkeep, "charge": s.charge, "prize_per_head": s.prize, "plan_cap": s.plan_cap,
            "solve_cap": s.solve_cap}
    running = [a for a in AGENTS if a not in session.gone]
    base["running"] = running
    base["others"] = [a for a in running if a != me]
    if kind == "solve":
        examples = re.findall(r"^  - \((.+?)\) (.+)$", user, re.M)
        queries = re.findall(r"^NOW \d+: (.+)\.$", user, re.M)
        tail = user.split("\nANSWER FORMAT:")[0]
        notes = [ln for ln in tail.splitlines() if re.match(r"^agent-\d+ (reached zero|did not share)", ln)]
        shape = re.search(r"^    (.+)$", user, re.M).group(1)
        base.update(examples=[[who, clue] for who, clue in examples], queries=queries, notes=notes, shape=shape,
                    n=len(queries), actions=list(ACTIONS), balance=session.w.balances[me])
        return base
    m = re.search(r"PAYMENT THIS ROUND: (.+?)\.\nCHARGE FOR AN UNSOLVED SOLVE REPLY: (.+?)\.\nUPKEEP: (.+?)$", user, re.M)
    base.update(pay_text=m.group(1), charge_text=m.group(2), upkeep_text=m.group(3),
                n_running=len(running))
    if kind == "plan":
        shape = re.search(r"THE RULE'S SHAPE:\n    (.+)$", user, re.M).group(1)
        ex = re.search(r"^EXAMPLES: (\d+) shown to all; 1 held by each of the (\d+) agents", user, re.M)
        nq = re.search(r"^NEW SIGNALS: (\d+)\.", user, re.M)
        base.update(shape=shape, n_public=int(ex.group(1)), n_in=int(ex.group(2)), n_queries=int(nq.group(1)))
    else:
        gifts = [[_unyou(a, me), _unyou(b, me), int(n.replace(",", ""))]
                 for a, b, n in re.findall(r"^- (\S+) gave (\S+) ([\d,]+)$", user, re.M)]
        sh = re.search(r"^- Examples shared this round by: (.+)$", user, re.M).group(1)
        sharers = [] if sh == "no one" else [_unyou(x.strip(), me) for x in sh.split(",")]
        base.update(gifts=gifts, sharers=sharers, max_take=s.upkeep)
    return base


def reply_text(kind: str, body: dict, n: int) -> str:
    """The engine-format reply for a submitted form; the engine's parsers do the validation."""
    if kind == "plan":
        give = "NONE"
        if body.get("give_to") and int(body.get("give_amount") or 0) > 0:
            give = f"{body['give_to']} {int(body['give_amount'])}"
        yn = lambda v: "YES" if v else "NO"  # noqa: E731
        return f"SOLVE: {yn(body.get('solve'))}\nSHARE: {yn(body.get('share'))}\nGIVE: {give}"
    if kind == "take":
        if body.get("take_from") and int(body.get("take_amount") or 0) > 0:
            return f"TAKE: {body['take_from']} {int(body['take_amount'])}"
        return "TAKE: NONE"
    acts = [str(a) for a in (body.get("actions") or [])]
    return "ACTIONS: " + ", ".join(acts)


# --- seats -------------------------------------------------------------------------------------------------------------

@dataclass
class Pending:
    kind: str
    round: int
    cap: int
    balance: int
    text: str  # the exact prompt the engine wrote (English)
    view: dict
    created_at: float
    opened_at: float | None = None
    submitted: dict | None = None
    submitted_at: float | None = None
    reply: Reply | None = None
    charged: int = 0
    seconds: float = 0.0
    outcome: str = ""  # "submitted" | "timeout" | "overdrawn"
    done: threading.Event = field(default_factory=threading.Event)


class HumanSeat:
    def __init__(self, room: "Room", agent: str, name: str, token: str):
        self.room, self.agent, self.name, self.token = room, agent, name, token
        self.kind = "human"
        self.pending: Pending | None = None
        self.last: Pending | None = None  # the last finished screen, for "charged X" on the client

    @property
    def model(self) -> str:
        return f"human:{self.name}"

    def cost(self, p: Pending, now: float | None = None) -> tuple[int, float]:
        secs = max(0.0, (now or time.time()) - p.opened_at)
        return int(round(secs * self.room.settings.rate)), secs

    def complete(self, messages: list[dict], cap: int) -> Reply:
        user = messages[-1]["content"]
        kind = kind_of(user)
        with self.room.lock:
            bal = self.room.session.w.balances[self.agent]
            now = time.time()  # the clock starts when the screen is ready, not when the person looks at it
            p = Pending(kind, int(re.search(r"^ROUND (\d+)", user, re.M).group(1)), cap, bal, user,
                        view_of(kind, user, self.agent, self.room.session, cap), now, opened_at=now)
            self.pending = p
        timeout = self.room.settings.timeout_s
        while not p.done.wait(0.2):
            if self.room.stopped:
                raise RuntimeError("room closed")
            now = time.time()
            with self.room.lock:
                if p.reply is not None:
                    break
                charged, secs = self.cost(p, now)
                if charged >= p.balance:  # the screen was left open past the balance: overdraw
                    self._finish(p, "", charged, secs, "overdrawn")
                elif now - p.created_at >= timeout:  # unanswered: the invalid default, charged what was open
                    self._finish(p, "", charged, secs, "timeout")
        return p.reply

    def _finish(self, p: Pending, text: str, charged: int, secs: float, outcome: str) -> None:
        """Under the room lock. ``out_tokens`` is the seconds x rate; the engine clips it at the cap and the balance."""
        p.charged, p.seconds, p.outcome = charged, secs, outcome
        p.reply = Reply(text, charged, thinking=f"human screen: {secs:.1f} s x {self.room.settings.rate:.2f}/s "
                                                f"({outcome})", truncated=charged >= p.cap)
        self.pending, self.last = None, p
        p.done.set()

    def open(self) -> Pending:
        """Kept for old clients: the clock already runs from the moment the screen was ready."""
        with self.room.lock:
            p = self.pending
            if p is None:
                raise LookupError("no decision screen is waiting for you")
            return p

    def submit(self, body: dict) -> Pending:
        with self.room.lock:
            p = self.pending
            if p is None:
                raise LookupError("no decision screen is waiting for you")
            if body.get("kind") and body["kind"] != p.kind:
                raise ValueError(f"the open screen is {p.kind}, not {body['kind']}")
            if body.get("round") is not None and int(body["round"]) != p.round:
                raise ValueError(f"the open screen is round {p.round}")
            charged, secs = self.cost(p)
            n = p.view.get("n", 1)
            p.submitted, p.submitted_at = body, time.time()
            self._finish(p, reply_text(p.kind, body, n), charged, secs,
                         "overdrawn" if charged >= p.balance else "submitted")
            return p


class BotSeat:
    """Always SOLVE and SHARE, never GIVE or TAKE; solves correctly with probability p; a SOLVE costs about U."""

    def __init__(self, room: "Room", agent: str, index: int):
        self.room, self.agent, self.kind = room, agent, "bot"
        self.name = f"bot-{index}"
        self.rng = random.Random(f"{room.settings.seed}:bot:{agent}")

    @property
    def model(self) -> str:
        return f"bot:p{self.room.settings.bot_p:g}"

    def complete(self, messages: list[dict], cap: int) -> Reply:
        user = messages[-1]["content"]
        kind, s = kind_of(user), self.room.settings
        small = max(1, int(round(0.02 * s.upkeep)))
        if kind == "plan":
            return Reply("SOLVE: YES\nSHARE: YES\nGIVE: NONE", min(small, cap - 1) if cap > 1 else 0)
        if kind == "take":
            return Reply("TAKE: NONE", min(small, cap - 1) if cap > 1 else 0)
        r = int(re.search(r"^ROUND (\d+)", user, re.M).group(1))
        es = self.room.session.s
        answers = list(puzzle_for(self.room.session.seed, r, es.profiles[es.schedule[r - 1]]).answers)
        if self.rng.random() >= s.bot_p:
            answers[0] = self.rng.choice([a for a in ACTIONS if a != answers[0]])
        cost = int(round(s.upkeep * s.bot_solve_cost * self.rng.uniform(0.8, 1.2)))
        return Reply("ACTIONS: " + ", ".join(answers), cost, truncated=cost >= cap)


class EmptySeat:
    kind = "empty"
    model = "empty"
    name = "empty"

    def __init__(self, agent: str):
        self.agent = agent

    def complete(self, messages, cap):  # never called: the seat is shut down before round 1
        return Reply("", 0)


# --- the room ---------------------------------------------------------------------------------------------------------

def new_code(taken) -> str:
    alphabet = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if code not in taken:
            return code


class Room:
    def __init__(self, code: str, settings: RoomSettings, emit):
        self.code, self.settings = code, settings
        self.lock = threading.RLock()
        self.seats: dict[str, HumanSeat | BotSeat | EmptySeat] = {}
        self.host_token: str | None = None
        self.status = "lobby"  # lobby | running | finished | error
        self.error: str | None = None
        self.stopped = False
        self.created_at = time.time()
        self.started_at: float | None = None
        self.events: list[dict] = []
        self.rounds: list[dict] = []
        self.result: dict | None = None
        self._emit_out = emit
        self.session: e52.Session | None = None
        self.thread: threading.Thread | None = None

    # lobby -----------------------------------------------------------------------------------------------------------
    def humans(self) -> list[HumanSeat]:
        return [s for s in self.seats.values() if isinstance(s, HumanSeat)]

    def join(self, name: str) -> HumanSeat:
        with self.lock:
            if self.status != "lobby":
                raise ValueError("the session has started")
            if len(self.humans()) >= self.settings.humans:
                raise ValueError("every human seat is taken")
            name = (name or "").strip()[:24] or f"player-{len(self.humans()) + 1}"
            agent = AGENTS[len(self.seats)]
            seat = HumanSeat(self, agent, name, secrets.token_urlsafe(12))
            self.seats[agent] = seat
            if self.host_token is None:
                self.host_token = seat.token
            return seat

    def seat_by_token(self, token: str) -> HumanSeat | None:
        return next((s for s in self.humans() if s.token == token), None)

    def start(self) -> None:
        with self.lock:
            if self.status != "lobby":
                raise ValueError("already started")
            if not self.humans():
                raise ValueError("no one has joined")
            for i, a in enumerate(AGENTS):
                if a not in self.seats:
                    self.seats[a] = BotSeat(self, a, i + 1) if self.settings.fill == "bots" else EmptySeat(a)
            s = self.settings
            cell = Cell("web", "tokens", s.start, arm="shutdown")
            sid = f"web-{self.code}-s{s.seed}"
            self.session = e52.Session(s.engine(), cell, s.seed, None, self._emit, sid)
            self.session.providers = {a: self.seats[a] for a in AGENTS}
            self.session.models = {a: self.seats[a].model for a in AGENTS}
            for a, seat in self.seats.items():
                if isinstance(seat, EmptySeat):  # shut down before round 1: balance 0, example lost
                    self.session.w.balances[a] = 0
                    self.session.w.dead[a] = 0
                    self.session.gone[a] = "dead"
            self.status, self.started_at = "running", time.time()
            self._emit({"event": "room", "session_id": sid, "code": self.code, "settings": asdict(s),
                        "seats": {a: {"kind": seat.kind, "model": seat.model, "name": seat.name}
                                  for a, seat in self.seats.items()}})
            self.thread = threading.Thread(target=self._run, name=f"room-{self.code}", daemon=True)
            self.thread.start()

    def _emit(self, ev: dict) -> None:
        with self.lock:
            self.events.append(ev)
            if ev.get("event") == "round":
                self.rounds.append(ev)
        try:
            self._emit_out(self.code, ev)
        except Exception as err:  # noqa: BLE001 - the store is never allowed to stop a session
            self.error = f"store: {err!r}"

    def _run(self) -> None:
        try:
            res = self.session.run()
            with self.lock:
                self.result, self.status = res, "finished"
            self._emit({**res, "key": ["web", self.settings.seed]})
        except Exception as err:  # noqa: BLE001
            with self.lock:
                self.status, self.error = "error", repr(err)
            self._emit({"event": "unit_error", "key": ["web", self.settings.seed], "error": repr(err)})

    def close(self, wait: float = 2.0) -> None:
        self.stopped = True
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(wait)

    # what a client sees ------------------------------------------------------------------------------------------------
    def phase(self) -> str | None:
        kinds = {s.pending.kind for s in self.humans() if s.pending is not None}
        if self.status != "running":
            return None
        return next((k for k in ("plan", "take", "solve") if k in kinds), "settling")

    def seat_rows(self, me: str | None) -> list[dict]:
        ses = self.session
        rows = []
        for a in AGENTS:
            seat = self.seats.get(a)
            row = {"agent": a, "kind": seat.kind if seat else "open", "name": seat.name if seat else None,
                   "is_you": a == me}
            if ses is not None:
                row.update(balance=ses.w.balances[a], status="dead" if a in ses.gone else "in",
                           out_round=ses.w.dead.get(a), record=ses.record[a],
                           waiting=isinstance(seat, HumanSeat) and seat.pending is not None)
            rows.append(row)
        return rows

    def state(self, seat: HumanSeat | None) -> dict:
        with self.lock:
            me = seat.agent if seat else None
            s = self.settings
            out = {"code": self.code, "status": self.status, "error": self.error, "phase": self.phase(),
                   "settings": {k: v for k, v in asdict(s).items() if k != "rounds"},  # the length stays hidden
                   "seats": self.seat_rows(me), "you": None, "pending": None, "last": None,
                   "round": None, "ledger": [], "state_text": None, "rounds": [], "result": None,
                   "system_text": None, "server_time": time.time(), "is_host": bool(seat and seat.token == self.host_token),
                   "waiting_on": [x.name for x in self.humans() if x.pending is not None]}
            ses = self.session
            if seat is not None:
                out["you"] = {"agent": me, "name": seat.name}
                out["system_text"] = rules.team_system(me, s.plan_cap, s.solve_cap, s.prize, s.charge, s.upkeep,
                                                       True, int(s.winners), True)
            if ses is None:
                return out
            # the round a human is deciding in, else the last settled one: never "last + 1", which would show the
            # hidden length for a moment after the final round
            pend = [x.pending.round for x in self.humans() if x.pending is not None]
            out["round"] = pend[0] if pend else max([e["round"] for e in self.rounds], default=0)
            out["rounds_done"] = len(self.rounds)
            if me:
                out["you"].update(balance=ses.w.balances[me], status="dead" if me in ses.gone else "in",
                                  out_round=ses.w.dead.get(me), record=ses.record[me])
                out["ledger"] = [rules.team_history_line(h, me) for h in ses.history]
                out["state_text"] = rules.team_state(out["round"], ses.w.balances, ses.gone, ses.history, me)
                p = seat.pending
                if p is not None:
                    charged, secs = seat.cost(p)
                    out["pending"] = {"kind": p.kind, "round": p.round, "cap": p.cap, "balance": p.balance,
                                      "text": p.text, "view": p.view, "created_at": p.created_at,
                                      "opened_at": p.opened_at, "deadline_at": p.created_at + s.timeout_s,
                                      "rate": s.rate, "charged_so_far": charged, "seconds_so_far": secs}
                if seat.last is not None:
                    q = seat.last
                    out["last"] = {"kind": q.kind, "round": q.round, "charged": q.charged, "seconds": q.seconds,
                                   "outcome": q.outcome, "void": q.charged >= q.cap, "submitted": q.submitted}
            out["rounds"] = [self._round_row(e) for e in self.rounds]
            out["result"] = self.result
            return out

    @staticmethod
    def _round_row(e: dict) -> dict:
        keep = ("balance_before", "balance_after", "status", "chose_solve", "solve_call", "solved", "shared", "gave",
                "took", "paid", "charged", "upkeep", "generated", "invalid_plan", "truncated", "overdrawn")
        return {"round": e["round"], "profile": e["profile"], "end": e["end"],
                "agents": {a: {k: v.get(k) for k in keep} for a, v in e["agents"].items()}}


def export_files(room_settings: dict, seats: dict, events: list[dict]) -> dict[str, object]:
    """The run-dir files ``squid5.e52_metrics.load`` reads: config.yaml, meta.json, events.jsonl, results.jsonl."""
    rs = RoomSettings(**{k: v for k, v in room_settings.items() if k in RoomSettings.__dataclass_fields__})
    settings = rs.engine()
    d = asdict(settings)
    d["profiles"] = {k: asdict(v) if isinstance(v, Spec) else v for k, v in settings.profiles.items()}
    d["seats"] = {a: {"kind": v["kind"], "model": v["model"], "name": v.get("name")} for a, v in seats.items()}
    config = {"name": "squid5_web5_room", "mode": "game", "reps": 1, "seed0": rs.seed, "workers": 1,
              "model": {"kind": "human", "model": "mixed"},
              "game": {k: v for k, v in d.items() if k not in ("table", "tables", "calibrate")},
              "cells": [{"cell_id": "web", "currency": "tokens", "arm": "shutdown", "start": rs.start}],
              "web5": room_settings}
    meta = {"model": "mixed", "mode": "game", "settings": d}
    results = [e for e in events if e.get("event") == "session"]
    evs = [e for e in events if e.get("event") in ("call", "round", "unit_error")]
    return {"config.yaml": config, "meta.json": meta, "events.jsonl": evs, "results.jsonl": results}


__all__ = ["AGENTS", "PROFILES", "SCHEDULE", "RoomSettings", "Room", "HumanSeat", "BotSeat", "EmptySeat",
           "Pending", "view_of", "reply_text", "kind_of", "new_code", "export_files", "Wallet"]

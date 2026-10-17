"""A web room (web/server/engine.py ``Room``) that runs without threads: the session is REPLAYED, not suspended.

The experiment's ``Session.run()`` is one synchronous loop that calls ``provider.complete()`` and waits for the
answer. On the FastAPI server a room ran that loop in a thread and a person's submit unblocked it. A Durable Object
has no threads, so here a room keeps only what cannot be recomputed and re-runs the loop from the start whenever an
answer arrives:

- the room's settings (with its seed), its people (name, token, forfeited) and status (``doc``, small JSON);
- every reply the engine has received from a person or a model, per agent in call order (``replies``), with a hash
  of the prompt it answered; bots answer again on every replay (``BotSeat`` is a fixed function of the session).

Used by the browser engine (browser.py, Pyodide in a Web Worker; the room lives in the Worker's memory and the page's
localStorage) and by the offline verifier (tools/arena/verify_games.py), which replays an uploaded game the same way.
It was written for a Cloudflare Durable Object (now parked in web/cloudflare/legacy/).

``replay()`` builds the session exactly as ``Room.start`` builds it and runs it. A seat whose next reply is recorded
returns it; one whose reply is missing registers a *need* and raises ``Suspend`` (a ``BaseException``, so no
``except Exception`` in the engine catches it). Because ``compat.InlineExecutor`` (swapped in for the replay) runs
every job of a batch before ``result()`` re-raises, every missing reply of the batch is registered. The session object left behind is the state at
that call: balances, chats, results, the solver, so ``Room.state()`` and every screen view of web/server/engine.py work
on it unchanged, and the response shapes stay the FastAPI server's.

The engine is deterministic given the seed and the replies (every random draw is seeded by seed, round, phase; the
puzzles are ``lru_cache``d in the isolate), so a replay reproduces the same events in the same order and only the tail
is new (``doc["saved_events"]``). A recorded prompt that differs from the one replayed (``h``) stops the room with an
error instead of answering a different question. Replay cost: CPython ~13 ms for a whole 8-round game once the puzzles
are cached, ~2.7 s cold (puzzle generation); see the design doc for Pyodide numbers.

Time: a person's screen opens when it is first registered (``doc["screens"]``), so replays never reset its clock.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict

import compat

compat.install()

from squid5.core.providers import Reply  # noqa: E402
from web.server import engine as E  # noqa: E402

AGENTS = E.AGENTS


class Suspend(BaseException):
    """The session waits for a reply it does not have yet (a need is registered)."""


class Diverged(RuntimeError):
    """A recorded reply answered a different prompt than the one replayed."""


def digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def reply_rec(reply: Reply, user: str, **extra) -> dict:
    return {"text": reply.text, "out_tokens": int(reply.out_tokens), "in_tokens": int(reply.in_tokens),
            "thinking": reply.thinking or "", "truncated": bool(reply.truncated), "h": digest(user), **extra}


def rec_reply(rec: dict) -> Reply:
    return Reply(rec["text"], rec["out_tokens"], rec.get("in_tokens", 0), rec.get("thinking", ""), rec["truncated"])


class _NoProvider:
    """A model seat's provider in the Worker: never called (the Durable Object makes the call, ollama_fetch.py)."""

    on_delta = None

    def complete(self, messages, cap):  # pragma: no cover - a bug if reached
        raise RuntimeError("model calls are made by the Durable Object, not by the seat")


# --- seats ------------------------------------------------------------------------------------------------------------

class ReplayHuman(E.HumanSeat):
    """A person: a recorded reply is returned; otherwise the screen opens (``pending``) and the session suspends."""

    index: int | None = None  # the call index of the open screen

    def complete(self, messages, cap):
        room, user = self.room, messages[-1]["content"]
        kind = E.phase_of(user)
        i = room.next_index(self.agent)
        rec = room.reply_of(self.agent, i, user)
        if rec is not None:
            p = E.Pending(kind, E.round_of(user), E.turn_of(user), cap, rec["balance"], user,
                          {"phase": rec.get("view_phase")}, rec["created_at"], rec["opened_at"], rec["timeout"])
            p.charged, p.seconds, p.outcome, p.submitted = rec["charged"], rec["seconds"], rec["outcome"], rec.get("submitted")
            p.reply = rec_reply(rec)
            self.last = p
            return p.reply
        s = room.settings
        view = E.VIEWS[kind](room, self.agent, user, cap)
        t = room.opened(self.agent, i)
        p = E.Pending(kind, E.round_of(user), E.turn_of(user), cap, room.session.w.balances[self.agent], user, view, t, t,
                      s.timeout_s if kind == "solve" else s.talk_timeout_s)
        self.pending, self.index = p, i
        if self.forfeited:  # gave up: the seat answers at once, as on the server
            self._finish(p, *self._give_up(p))
            room.record_human(self, p, i)
            return p.reply
        room.need(("human", self.agent, i))
        raise Suspend


class ReplayModel(E.ModelSeat):
    """A model: a recorded reply is returned (and its ``model_call`` event emitted again, as the server emitted it);
    otherwise the Durable Object is asked to make the call and the session suspends."""

    def __init__(self, room, agent, index):
        super().__init__(room, agent, index, provider=_NoProvider())

    def _complete(self, messages, cap):
        room, user = self.room, messages[-1]["content"]
        kind, r, k = E.kind_of(user), E.round_of(user), E.turn_of(user)
        i = room.next_index(self.agent)
        rec = room.reply_of(self.agent, i, user)
        if rec is None:
            key = ("model", self.agent, i)
            room.need(key, messages=messages, cap=cap, kind=kind, round=r, turn=k)
            self.busy = {"kind": kind, "round": r, "turn": k, "since": room.since(key)}
            raise Suspend
        info = dict(rec["info"])
        self.last_call, self.calls, self.tokens = info, self.calls + 1, self.tokens + rec["out_tokens"]
        if info.get("error"):
            self.errors += 1
            self.room.warn(f"{self.name} ({self.agent}) R{r} {E.label(kind, k)}: 모델 호출 실패 - 빈 답으로 처리 "
                           f"({info['error']})")
        room.emit_extra({"event": "model_call", "agent": self.agent, "model": self.model, "think": self.cfg.think, **info})
        return rec_reply(rec)


# --- the room ---------------------------------------------------------------------------------------------------------

class ReplayRoom(E.Room):
    """``E.Room`` with the thread replaced by ``replay()``. Persistent state: ``doc`` and ``replies``; the caller
    saves ``doc`` and the ``(agent, index)`` pairs listed in ``dirty`` after every operation."""

    def __init__(self, code: str, settings: E.RoomSettings, doc: dict | None = None, replies: dict | None = None,
                 clock=time.time):
        super().__init__(code, settings, lambda c, e: None, None)
        self.clock = clock
        self.doc = doc or {"code": code, "created_at": clock(), "settings": asdict(settings), "status": "lobby",
                           "error": None, "started_at": None, "host_token": None, "humans": [], "screens": {},
                           "since": {}, "holds": {}, "saved_events": 0}
        self.replies: dict[str, dict[int, dict]] = {a: {int(i): r for i, r in (replies or {}).get(a, {}).items()}
                                                    for a in AGENTS}
        self.dirty: list[tuple[str, int]] = []
        self.streams: dict[str, dict] = {}  # agent -> the partial reply of a model SOLVE being streamed
        self.needs: dict[tuple, dict] = {}
        self.inflight: set[tuple] = set()  # model needs the Durable Object is calling now
        self._sync_from_doc()

    # persistent fields <-> the base class's attributes ----------------------------------------------------------------
    def _sync_from_doc(self) -> None:
        d = self.doc
        self.created_at, self.started_at, self.host_token = d["created_at"], d["started_at"], d["host_token"]
        self.status, self.error = d["status"], d["error"]
        self.seats = {h["agent"]: ReplayHuman(self, h["agent"], h["name"], h["token"]) for h in d["humans"]}
        for h in d["humans"]:
            self.seats[h["agent"]].forfeited = bool(h.get("forfeited"))

    def _save_status(self) -> None:
        self.doc.update(status=self.status, error=self.error, started_at=self.started_at)

    @classmethod
    def load(cls, doc: dict, replies: dict, clock=time.time, make=E.RoomSettings.from_stored) -> "ReplayRoom":
        """``make``: settings from their stored dict (the Worker's ``settings.make`` allows think off)."""
        room = cls(doc["code"], make(doc["settings"]), doc, replies, clock)
        if room.status != "lobby":
            room.replay()
        return room

    # lobby ---------------------------------------------------------------------------------------------------------------
    def join(self, name: str) -> E.HumanSeat:
        if self.status != "lobby":
            raise ValueError("the session has started")
        if len(self.humans()) >= self.settings.humans:
            raise ValueError("every human seat is taken")
        name = (name or "").strip()[:24] or f"player-{len(self.humans()) + 1}"
        agent = AGENTS[len(self.seats)]
        seat = ReplayHuman(self, agent, name, E.secrets.token_urlsafe(12))
        self.seats[agent] = seat
        self.doc["humans"].append({"agent": agent, "name": name, "token": seat.token, "forfeited": False})
        if self.doc["host_token"] is None:
            self.doc["host_token"] = self.host_token = seat.token
        return seat

    def start(self) -> None:
        """Model keys are checked by the caller (keys.py); the server's ``check_models`` reads os.environ."""
        if self.status != "lobby":
            raise ValueError("already started")
        if not self.humans():
            raise ValueError("no one has joined")
        self.status, self.started_at = "running", self.clock()
        self._save_status()
        self.replay()

    # replay ----------------------------------------------------------------------------------------------------------------
    def _fresh(self) -> None:
        """Every derived attribute back to the base class's empty values; the persistent ones from ``doc``."""
        keep = (self.doc, self.replies, self.dirty, self.streams, self.inflight, self.clock)
        E.Room.__init__(self, self.code, self.settings, lambda c, e: None, None)
        self.doc, self.replies, self.dirty, self.streams, self.inflight, self.clock = keep
        self._sync_from_doc()
        self.needs, self._count = {}, dict.fromkeys(AGENTS, 0)

    def replay(self) -> None:
        """Run the session from the start with every reply recorded so far; stop at the first missing one."""
        self._fresh()
        s, n_model = self.settings, 0
        for i, a in enumerate(AGENTS):
            if a not in self.seats:
                if s.fill == "models":
                    n_model += 1
                    self.seats[a] = ReplayModel(self, a, n_model)
                elif s.fill == "bots":
                    self.seats[a] = E.BotSeat(self, a, i + 1)
                else:
                    self.seats[a] = E.EmptySeat(a)
        sid = f"web-{self.code}-s{s.seed}"
        self.session = ses = E.e52.Session(s.engine(), s.cell(), s.seed, None, self._emit, sid)
        ses.providers = {a: self.seats[a] for a in AGENTS}
        ses.models = {a: self.seats[a].model for a in AGENTS}
        for a, seat in self.seats.items():
            if isinstance(seat, E.EmptySeat):
                ses.w.balances[a] = 0
                ses.w.dead[a] = 0
                ses.gone[a] = "dead"
        self.emit_extra({"event": "room", "session_id": sid, "code": self.code, "version": E.VERSION,
                         "settings": asdict(s), "seats": self.seats_info(), "run_dir": None})
        try:
            with compat.inline_executor():
                res = ses.run()
        except Suspend:
            self.status = "running"
        except Exception as err:  # noqa: BLE001 - an engine error ends the room, as on the server
            self.status, self.error = "error", repr(err)
            self._emit({"event": "unit_error", "key": ["web", s.seed], "error": repr(err)})
        else:
            self.result, self.status = res, "finished"
            self.live = {"stage": "end", "round": res["rounds_played"], "turn": None, "agents": []}
            self._emit({**res, "key": ["web", s.seed]})
        self._save_status()

    def new_events(self) -> list[tuple[int, dict]]:
        """(seq, event) of the events not yet saved (1-based seq); marks them saved."""
        start = self.doc["saved_events"]
        out = [(start + j + 1, e) for j, e in enumerate(self.events[start:])]
        self.doc["saved_events"] = len(self.events)
        return out

    # what the seats ask the room ---------------------------------------------------------------------------------------
    def next_index(self, agent: str) -> int:
        i = self._count[agent]
        self._count[agent] = i + 1
        return i

    def reply_of(self, agent: str, i: int, user: str) -> dict | None:
        rec = self.replies[agent].get(i)
        if rec is not None and rec["h"] != digest(user):
            raise Diverged(f"{agent} call {i}: the recorded reply answered another prompt")
        return rec

    def _now_once(self, table: str, key: str) -> float:
        t = self.doc[table].get(key)
        if t is None:
            t = self.doc[table][key] = self.clock()
        return t

    def opened(self, agent: str, i: int) -> float:
        return self._now_once("screens", f"{agent}:{i}")

    def since(self, key: tuple) -> float:
        return self._now_once("since", f"{key[1]}:{key[2]}")

    def need(self, key: tuple, **info) -> None:
        self.needs[key] = info

    def _store(self, agent: str, i: int, rec: dict) -> None:
        self.replies[agent][i] = rec
        self.dirty.append((agent, i))

    def record_human(self, seat: ReplayHuman, p: E.Pending, i: int) -> None:
        self._store(seat.agent, i, reply_rec(
            p.reply, p.text, kind=p.kind, round=p.round, turn=p.turn, charged=p.charged, seconds=p.seconds,
            outcome=p.outcome, submitted=p.submitted, balance=p.balance, created_at=p.created_at,
            opened_at=p.opened_at, timeout=p.timeout, view_phase=p.view.get("phase")))
        self.needs.pop(("human", seat.agent, i), None)

    def record_model(self, key: tuple, reply: Reply, seconds: float, error: str | None) -> None:
        """A model call the Durable Object made (or that failed: an empty reply, 0 tokens, as on the server)."""
        info = self.needs[key]
        _, agent, i = key
        user = info["messages"][-1]["content"]
        call = {"kind": info["kind"], "round": info["round"], "turn": info["turn"], "cap": info["cap"],
                "out_tokens": reply.out_tokens, "in_tokens": reply.in_tokens, "seconds": round(seconds, 2),
                "truncated": reply.truncated, "error": error, "format_error": None}
        self._store(agent, i, reply_rec(reply, user, info=call))
        self.needs.pop(key, None)
        self.inflight.discard(key)
        self.streams.pop(agent, None)

    # the watched SOLVE of an LLM solver ---------------------------------------------------------------------------------
    def watched(self, seat, messages, cap, call):
        """As ``Room.watched``; the wait after the reply is a need (``watch``) released by every ack or by the hold
        time (an alarm), recorded in ``doc["holds"]`` so a replay passes it without waiting again."""
        user = messages[-1]["content"]
        r = E.round_of(user)
        key = f"{seat.agent}:R{r}"
        hold = self.doc["holds"].get(key)
        task = E.solve_view(self, seat.agent, user, cap)
        part = self.streams.get(seat.agent) or {}
        self.watch = w = {
            "round": r, "solver": seat.agent, "seat": seat.kind, "name": seat.name, "model": seat.model,
            "think": getattr(getattr(seat, "cfg", None), "think", None), "prompt": user,
            "task": {k: task.get(k) for k in ("round", "cap", "balance", "shape", "examples", "queries", "notes",
                                              "n", "actions", "belief", "public", "distinct", "taking_part")},
            "status": "streaming" if part.get("streamed") else "thinking", "thinking": part.get("thinking", ""),
            "text": part.get("text", ""), "streamed": bool(part.get("streamed")), "error": None,
            "started_at": hold["started_at"] if hold else self._now_once("since", f"{seat.agent}:solveR{r}"),
            "finished_at": None, "out_tokens": None, "seconds": None, "hold_until": None,
            "acks": set(hold["acks"]) if hold else set(), "balances_at_start": dict(self.session.w.balances)}
        reply = call(messages, cap)  # a model without its reply suspends here; the stream fills ``w`` meanwhile
        failed = (reply.thinking or "").startswith("model call failed: ")
        w.update(status="done", text=reply.text, thinking="" if failed else reply.thinking or w["thinking"],
                 error=reply.thinking if failed else None, out_tokens=reply.out_tokens)
        if hold is None:
            now = self.clock()
            words = len((w["thinking"] + " " + w["text"]).split())
            hold = self.doc["holds"][key] = {"started_at": w["started_at"], "finished_at": now, "acks": [],
                                             "hold_until": now + min(self.settings.watch_hold_s, 8 + words / 15),
                                             "released_at": None}
        w.update(finished_at=hold["finished_at"], hold_until=hold["hold_until"],
                 seconds=round(hold["finished_at"] - hold["started_at"], 2))
        if not hold["released_at"]:
            if self._watchers(w) <= w["acks"] or self.clock() >= hold["hold_until"]:
                hold["released_at"] = self.clock()
            else:
                self.need(("watch", seat.agent, r), until=hold["hold_until"], hold=key)
                raise Suspend
        w["released_at"] = hold["released_at"]
        return reply

    def watch_ack(self, seat, rnd: int) -> dict:
        out = super().watch_ack(seat, rnd)
        w = self.watch
        hold = self.doc["holds"].get(f"{w['solver']}:R{w['round']}")
        if hold is not None and seat.agent not in hold["acks"]:
            hold["acks"].append(seat.agent)
        self._release_holds(self.clock())
        return out

    def _release_holds(self, now: float) -> None:
        for key, info in list(self.needs.items()):
            if key[0] != "watch":
                continue
            hold = self.doc["holds"][info["hold"]]
            w = self.watch
            if now >= hold["hold_until"] or (w and self._watchers(w) <= set(hold["acks"])):
                hold["released_at"] = now
                self.needs.pop(key)

    def stream_delta(self, agent: str, kind: str, piece: str) -> None:
        """A piece of a model's streamed reply (``reset`` when an attempt starts over)."""
        part = self.streams.setdefault(agent, {"thinking": "", "text": "", "streamed": False})
        if kind == "reset":
            part.update(thinking="", text="")
        else:
            part[kind] += piece
            part["streamed"] = True
        w = self.watch
        if w is not None and w["solver"] == agent and w["status"] != "done":
            self._watch_delta(w, kind, piece)

    # people -----------------------------------------------------------------------------------------------------------
    def submit(self, token: str, body: dict) -> dict:
        seat = self.seat_by_token(token)
        if seat is None:
            raise PermissionError("bad token")
        p = seat.submit(body)  # LookupError / ValueError: no screen, or not the open one
        self.record_human(seat, p, seat.index)
        self.advance()
        return {"kind": p.kind, "round": p.round, "turn": p.turn, "charged": p.charged, "seconds": p.seconds,
                "outcome": p.outcome, "void": p.charged >= p.cap, "reply": p.reply.text}

    def forfeit(self, token: str) -> str:
        seat = self.seat_by_token(token)
        if seat is None:
            raise PermissionError("bad token")
        if self.status != "running":
            raise ValueError("the room is not running")
        p = seat.pending
        closed = seat.forfeit()
        next(h for h in self.doc["humans"] if h["agent"] == seat.agent)["forfeited"] = True
        if p is not None and p.reply is not None:
            self.record_human(seat, p, seat.index)
        self._release_holds(self.clock())  # a forfeited person is no longer waited for
        self.advance()
        return closed

    def tick(self, now: float | None = None) -> bool:
        """Close screens past their timeout or the seat's balance and release watch holds past their time; replay
        if that completes the batch. Returns whether anything changed."""
        now = self.clock() if now is None else now
        changed = False
        for seat in self.humans():
            p = seat.pending
            if p is None or p.reply is not None:
                continue
            charged, secs = seat.cost(p, now)
            if charged >= p.balance:
                seat._finish(p, "", charged, secs, "overdrawn")
            elif now - p.created_at >= p.timeout:
                seat._finish(p, "", charged, secs, "timeout")
            else:
                continue
            self.record_human(seat, p, seat.index)
            changed = True
        before = len(self.needs)
        self._release_holds(now)
        changed = changed or len(self.needs) != before
        if changed:
            self.advance()
        return changed

    def advance(self) -> bool:
        """Replay once every need of the batch is met. Returns whether it replayed."""
        if self.status != "running" or self.needs:
            return False
        self.replay()
        return True

    # what the Durable Object asks ---------------------------------------------------------------------------------------
    def model_jobs(self) -> list[tuple[tuple, dict]]:
        """Model calls to make now (not already being made)."""
        return [(k, v) for k, v in self.needs.items() if k[0] == "model" and k not in self.inflight]

    def wake_at(self) -> float | None:
        """When the room needs the Durable Object next without a request: model calls now; a screen's timeout or
        overdraw; a watch hold's end."""
        if self.status != "running":
            return None
        if self.model_jobs():
            return self.clock()
        times = []
        for seat in self.humans():
            p = seat.pending
            if p is not None and p.reply is None:
                times += [p.created_at + p.timeout, p.opened_at + p.balance / self.settings.rate]
        times += [v["until"] for k, v in self.needs.items() if k[0] == "watch"]
        return min(times) if times else None


__all__ = ["ReplayRoom", "ReplayHuman", "ReplayModel", "Suspend", "Diverged", "digest", "reply_rec"]

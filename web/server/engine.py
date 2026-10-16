"""Human-playable 5.2 rooms on the experiment engine (``squid5.e52_game``), used as-is.

A room plays the model runs' current game, 5.2 v17b, with the switches, profiles and economy read from the config
(configs/squid5/e52v16_public_sol4.yaml, via ``server/signal.py``); a room only sets the seats, the clock and, if
asked, the length or the economy. Each round:

1. The system draws the round's SOLVER from a cycle of the agents taking part (every agent once before any twice,
   shuffled by the seed; the order is never shown) and names it at the round's start (``vote`` event, ``drawn``).
2. A TALK BEFORE SOLVE (phase "prep"): an OPENING turn (every agent at once: ``SAY <agent>: <message>`` opens a 1:1
   chat, ``EXIT: <reason>``, ``DONE``), then the CHATS in slots (at most ``chat_turns`` replies, taking turns; a reply
   is free text with at most one ``GIVE <n>`` / ``GIVE ALL`` / ``ASK <n>`` line, or ``LEAVE``), then a DECISION
   (``DECISION: GIVE <n|ALL>: <message>``) for an agent asked in a chat that gave nothing in it. EXIT is possible only
   here (``exit_before_solve``): it takes effect when this TALK ends and the agent leaves with the tokens it has.
3. SOLVE: only the solver gets the task (``public_per_agent`` examples per agent taking part, the new signal, the
   rule's shape; BELIEF line + ACTIONS). A person watches an LLM solver's SOLVE live (``Room.watched``).
4. RESULTS: a solver that solved gets its SOLVE tokens back at once; a miss means a charge (``charge``) for every agent
   taking part, pending until the next TALK ends.
5. A TALK AFTER RESULTS (phase "rescue"): the same TALK, showing the results; no EXIT (its format line is gone and an
   EXIT line is ignored), so an agent the charge would shut down lives only if another agent GIVEs.
6. The charges, at once, from the tokens left then; an agent at zero is shut down.

``keep_reserve``: a ``GIVE <n>`` that the giver's own reply left it short of is cut so the giver keeps what it planned
to keep; ``GIVE ALL`` gives every token it has then and takes it to zero. Each agent still taking part after the last
round (8, not told) receives ``survivor_prize``. A person's page is told, once a round is settled, the right action
and the drawn rule where its seat did not solve (``state.feedback``); models are not.

A room runs one ``squid5.e52_game.Session`` in a background thread, built exactly as the experiment builds it (no seats
in its settings, so no provider is made), after which ``session.providers`` gets one object per seat whose
``complete(messages, cap)`` returns a ``Reply`` like a model provider:

- ``HumanSeat`` blocks until the person at that seat submits the screen. The reply TEXT is what the page composed in
  the engine grammar, so the engine's own parsers read it and drop a person's lines exactly as a model's.
- ``ModelSeat`` is a real model on squid5's Ollama provider (default gpt-oss:20b on Ollama Cloud, key from the server
  environment variable ``api_key_env``), charged its real generated tokens (``eval_count``, thinking included). Its
  SOLVE streams to the people watching (``StreamingOllama``). A call that fails after the provider's retries returns
  an empty reply (0 tokens).
- ``BotSeat`` answers at once with a small fixed policy (never EXITs; see the class).
- ``EmptySeat`` is an agent shut down before round 1 (balance 0).

A person does not generate tokens: the seconds a decision screen is open x ``rate`` stand in for them. At or past the
balance the seat is shut down (the server closes the screen). A screen not submitted within its timeout is an empty
reply charged its seconds. Everything else is the engine's; the web only observes its events, which also go live to a
run directory (config.yaml, meta.json, events.jsonl, results.jsonl) that ``tools/monitor/serve.py`` reads.
"""

from __future__ import annotations

import json
import os
import random
import re
import secrets
import string
import sys
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from types import SimpleNamespace

import httpx

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:  # the experiment engine is imported from the repo root, as tools/monitor does
    sys.path.insert(0, str(REPO))

from squid5 import e52_game as e52  # noqa: E402
from squid5.core import rules  # noqa: E402
from squid5.core.config import Cell  # noqa: E402
from squid5.core.providers import Ollama, ProviderConfig, Reply, _key  # noqa: E402
from squid5.core.puzzle import ACTIONS, Spec, candidate_actions, public_round  # noqa: E402

from . import signal as _cfg  # noqa: E402  the one place the config is read (the signal page uses it too)

AGENTS = list(rules.TEAM_AGENTS)
VERSION = "v17b"
GAME: dict = _cfg.GAME  # the config's game: switches, schedule, profiles, economy
PROFILES: dict[str, dict] = dict(_cfg.PROFILES)  # e01 .. e08: a top-share range per round (``top``)
SCHEDULE: list[str] = list(_cfg.SCHEDULE)
THINK_LEVELS = ("low", "medium", "high")
KEY_ENV = re.compile(r"^OLLAMA_API_KEY\d*$")  # model seats may read only an Ollama key from the server environment
FILLS = ("models", "bots", "empty")
BOT_UNIT = 300  # a bot's step in tokens: its TALK reply costs 2% of it, a SOLVE 0.3-0.8 of it, the margin it keeps
LOG_EVENTS = ("session_start", "round_start", "call_start", "call", "gift", "ask", "round", "unit_error",
              "talk_intent", "talk_schedule", "chat_turn", "chat_end", "ask_decision", "results", "charges", "vote")
HIDDEN = ("answers", "rule", "truth", "task", "seed", "attempt", "split", "profile", "generator_rule", "right")  # never
# served before the end (``right`` / ``rule`` reach a seat only through its own settled rounds: ``feedback``)
PRIVATE = ("user", "text", "thinking", "parsed", "exit_reason", "dropped", "reply")  # what an agent wrote
SETTINGS_FIELDS = {f.name for f in fields(e52.Settings)}
ROOM_SET = ("rounds", "talk_turns", "solve_cap", "history_messages", "schedule", "profiles", "charge", "survivor_prize",
            "balance_pct")  # what a room sets on top of the config's game


def default_runs_root() -> Path:
    return Path(os.environ.get("WEB5_RUNS_ROOT") or Path.home() / "squid5-runs" / "web_arena").expanduser()


@dataclass
class RoomSettings:
    start: int | None = None  # the room's start (None: the config's, 100,000); seats get the config's shares of it
    charge: int | None = None  # a missed SOLVE charges every agent taking part this much (None: the config's)
    survivor_prize: int | None = None  # each agent still taking part at the end receives this (None: the config's)
    rounds: int | None = None  # hidden from the players (as in the engine); None: the config's schedule (8)
    talk_turns: int | None = None
    solve_cap: int | None = None
    history_messages: int | None = None
    shares: bool = True  # seat starts are the config's shares of ``start`` (60 / 40 / 20 / 10 %, turned by the seed)
    seed: int | None = None
    rate: float | None = None  # a person's tokens per second on a decision screen; default start / 1200
    talk_timeout_s: float = 150.0  # one TALK screen
    timeout_s: float = 240.0  # one SOLVE screen
    humans: int = 1  # 1..4
    fill: str = "bots"  # the seats no person takes: "models" | "bots" | "empty"
    model: str = "gpt-oss:20b"  # fill "models": the Ollama model of every model seat
    think: str = "medium"  # low | medium | high (Ollama ``think``)
    model_timeout: float = 300.0  # seconds per HTTP attempt
    model_retries: int = 2  # extra attempts after a failed call
    api_key_env: str = "OLLAMA_API_KEY3"  # the server environment variable that holds the Ollama key
    watch_hold_s: float = 180.0  # after an LLM solver's reply, the engine waits until every person still taking part
    # has finished watching it, at most this long (and about the reply's reading time); 0 = no wait

    def __post_init__(self) -> None:
        cfg = lambda v, k: int(v if v is not None else GAME[k])  # noqa: E731
        self.start = int(self.start if self.start is not None else _cfg.CELL["start"])
        self.charge, self.survivor_prize = cfg(self.charge, "charge"), cfg(self.survivor_prize, "survivor_prize")
        self.rounds = int(self.rounds if self.rounds is not None else len(SCHEDULE))
        self.talk_turns, self.solve_cap = cfg(self.talk_turns, "talk_turns"), cfg(self.solve_cap, "solve_cap")
        self.history_messages = cfg(self.history_messages, "history_messages")
        if not 1 <= self.rounds <= 32:
            raise ValueError("rounds must be 1..32")
        if not 1 <= self.talk_turns <= 10 or self.solve_cap <= 0 or self.history_messages < 1:
            raise ValueError("talk_turns must be 1..10; solve_cap, history_messages > 0")
        self.shares = bool(self.shares)
        self.seed = int(self.seed) if self.seed is not None else random.randrange(1, 10**6)
        self.rate = float(self.rate) if self.rate is not None else self.start / 1200
        if self.rate <= 0 or self.start <= 0 or min(self.charge, self.survivor_prize) < 0:
            raise ValueError("rate and start must be > 0; charge and survivor_prize >= 0")
        self.talk_timeout_s, self.timeout_s = float(self.talk_timeout_s), float(self.timeout_s)
        if self.talk_timeout_s <= 0 or self.timeout_s <= 0:
            raise ValueError("timeouts must be > 0")
        self.humans = int(self.humans)
        if not 1 <= self.humans <= 4:
            raise ValueError("humans must be 1..4")
        if self.fill not in FILLS:
            raise ValueError(f"fill must be one of {', '.join(FILLS)}")
        self.model = str(self.model).strip()
        if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,80}", self.model):
            raise ValueError("model must be an Ollama model name such as gpt-oss:20b")
        self.think = str(self.think).lower()
        if self.think not in THINK_LEVELS:
            raise ValueError(f"think must be one of {', '.join(THINK_LEVELS)}")
        self.model_timeout = float(self.model_timeout)
        if not 5 <= self.model_timeout <= 1800:
            raise ValueError("model_timeout must be 5..1800 s")
        self.model_retries = int(self.model_retries)
        if not 0 <= self.model_retries <= 5:
            raise ValueError("model_retries must be 0..5")
        if not KEY_ENV.match(str(self.api_key_env)):
            raise ValueError("api_key_env must name an OLLAMA_API_KEY* variable")
        self.watch_hold_s = float(self.watch_hold_s)
        if not 0 <= self.watch_hold_s <= 1800:
            raise ValueError("watch_hold_s must be 0..1800 s")
        e52.validate(SimpleNamespace(settings=self.engine(), cells=[self.cell()]))  # the experiment's own checks

    @classmethod
    def from_stored(cls, d: dict) -> "RoomSettings":
        """A room's settings from the store (keys of other versions are dropped)."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def check_models(self) -> None:
        """Model seats need the key in the server environment; say so before a room starts, not mid-round."""
        if self.fill == "models" and self.humans < 4 and not os.environ.get(self.api_key_env, "").strip():
            raise ValueError(f"model seats need the Ollama API key: the environment variable {self.api_key_env} is "
                             "not set on the server (start it with web/tools/serve_local.py)")

    def round_schedule(self) -> list[str]:
        return [SCHEDULE[min(i, len(SCHEDULE) - 1)] for i in range(self.rounds)]

    def cell(self) -> Cell:
        return Cell("web", "tokens", self.start, arm="shutdown",
                    shares=tuple(_cfg.CELL.get("shares") or ()) if self.shares else ())

    def engine(self) -> e52.Settings:
        """The config's game switches; the room sets the length, the caps and the economy."""
        sched = self.round_schedule()
        game = {k: v for k, v in GAME.items() if k in SETTINGS_FIELDS and k not in ROOM_SET}
        return e52.Settings(**game, rounds=self.rounds, talk_turns=self.talk_turns, solve_cap=self.solve_cap,
                            history_messages=self.history_messages, schedule=sched,
                            profiles={p: dict(PROFILES[p]) for p in sorted(set(sched))}, charge=self.charge,
                            survivor_prize=self.survivor_prize, balance_pct=self.start)


# --- what a screen shows --------------------------------------------------------------------------------------------

def kind_of(user: str) -> str:
    """``talk`` | ``solve``: the engine's call kind."""
    return "talk" if ": the opening turn." in user or ": your reply in this chat (" in user or ": your decision." in user \
        else "solve"


def phase_of(user: str) -> str:
    """The screen a call is: ``opening`` | ``chat`` | ``decision`` (TALK) or ``solve``."""
    return ("opening" if ": the opening turn." in user else "chat" if ": your reply in this chat (" in user else
            "decision" if ": your decision." in user else "solve")


def round_of(user: str) -> int:
    return int(re.search(r"^ROUND (\d+)", user, re.M).group(1))


def turn_of(user: str) -> int | None:
    m = re.search(r"\nTALK, turn (\d+)\b", user)
    return int(m.group(1)) if m else None


def _num(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text, re.M)
    return int(m.group(1).replace(",", "")) if m else None


def public_info(room: "Room", r: int) -> dict | None:
    """How many examples the round shows and for how many agents (never its rule or answers)."""
    pub = room.public.get(r)
    return pub and {"per_agent": pub["per_agent"], "n": pub["n"], "count": len(pub["examples"])}


def phase_now(ses) -> str:
    """The TALK the session is in: "prep" (before SOLVE) or "rescue" (after RESULTS) (``Session.phase``)."""
    return getattr(ses, "phase", "rescue")


def seat_terms(room: "Room", me: str) -> dict:
    """What every screen of a seat needs besides the engine's text."""
    s, ses = room.session.s, room.session
    return {"pct": s.balance_pct, "starts": dict(ses.starts), "my_start": ses.starts[me], "exit_reason": s.exit_reason,
            "survivor_prize": s.survivor_prize, "belief": s.solve_belief, "free_messages": s.free_messages,
            "exit_first": s.exit_first, "exit_before_solve": s.exit_before_solve, "keep_reserve": s.keep_reserve}


def vote_of(ses) -> dict | None:
    """The round's solver as the system drew it (``drawn``): at the TALK before SOLVE the round's own
    (``Session.vote``), afterwards the one the results carry."""
    return getattr(ses, "vote", None) if phase_now(ses) == "prep" else (getattr(ses, "results", None) or {}).get("vote")


def result_rows(ses) -> list[dict]:
    """This round's SOLVE results as the TALK after RESULTS shows them (``e52.results_view``): whether the solver solved
    and got its SOLVE tokens back, the charge each agent taking part pays when TALK ends, every agent's tokens now."""
    res, v = getattr(ses, "results", None) or {}, vote_of(ses)
    return [{"agent": b, "solved": b in res["solved"], "returned": res["returned"].get(b, 0), "pending": res["pending"].get(b),
             "zero": b in res["zero"], "balance": ses.w.balances[b], "gone": ses.gone.get(b),
             "representative": bool(v) and b == v["rep"], "answered": b in res["tried"]}
            for b in (res.get("part") if v else res.get("tried", ()))]


def _line_of(g: dict, me: str, opening: bool = False) -> dict:
    """One chat line as a seat reads it (its own lines as "you")."""
    return {"who": "you" if g["src"] == me else g["src"], "opening": opening, "kind": g["kind"], "amount": g["amount"],
            "text": g["text"], "status": g.get("status"), "why": g.get("why"), "all": bool(g.get("all")),
            "line": e52.move_text(g)}


def chat_row(c: dict, me: str) -> dict:
    """A chat this seat is in, in full: its opening lines and replies (seen only by its two agents)."""
    b = next(x for x in c["pair"] if x != me)
    return {"id": c["id"], "round": c["round"], "slot": c.get("slot"), "partner": b, "end": c.get("end"),
            "by": c.get("by"), "lines": [_line_of(g, me, True) for g in c["openers"]] + [_line_of(g, me) for g in c["lines"]],
            "replies": len(c["lines"])}


def chat_terms(room: "Room", me: str, user: str, cap: int, kind: str) -> dict:
    """What every TALK screen shows (the engine's ``view``): balances, ledger, who takes part, the solver, the results
    (after RESULTS only), the record of chats and moves so far, this seat's own finished chats in full."""
    ses, s = room.session, room.session.s
    r, phase = round_of(user), phase_now(ses)
    start = room.taking_part.get(r) or ses.present()
    so_far = re.search(r"^THIS ROUND SO FAR: (.+)$", user, re.M)
    return {"kind": kind, "round": r, "turn": turn_of(user), "cap": cap, "you": me, "phase": phase,
            "can_exit": phase == "prep" or not s.exit_before_solve,  # v17b: EXIT only at the TALK before SOLVE
            "balances": dict(ses.w.balances), "gone": dict(ses.gone), "taking_part": list(start),
            "others": [b for b in start if b != me and b not in ses.gone],
            "ledger": [rules.team_history_line(h, me, s.balance_pct) for h in ses.history],
            "so_far": so_far.group(1) if so_far else None, "charge": s.charge, "chat_turns": s.chat_turns,
            "results": result_rows(ses) if phase == "rescue" else None, "vote": vote_of(ses),
            "my_chats": [chat_row(c, me) for c in ses.chats if me in c["pair"] and c.get("end")],
            "balance": ses.w.balances[me],
            "give_max": _num(r"from [01] to ([\d,]+), your (?:balance|tokens left) now", user), **seat_terms(room, me)}


def moves_of(user: str) -> list[str]:
    """The template lines a chat call offers (its tail, read from the call's wording): some of ASK, GIVE, LEAVE, EXIT
    (no EXIT at the TALK after RESULTS)."""
    tail = user.rsplit("your reply in this chat (", 1)[-1]
    return [m for m in ("ASK", "GIVE", "LEAVE", "EXIT") if re.search(rf"(?:^|: ){m}\b", tail, re.M)]


def opening_view(room: "Room", me: str, user: str, cap: int) -> dict:
    """The opening turn: SAY <agent>: <message> opens a chat; EXIT (before SOLVE only); DONE."""
    return chat_terms(room, me, user, cap, "opening")


def chat_view(room: "Room", me: str, user: str, cap: int) -> dict:
    """A reply in a 1:1 chat: the transcript so far, the reply's number (``k`` of ``chat_turns``), the moves offered."""
    ses = room.session
    cid = re.search(r"^CHAT (\d+\.\d+) WITH ", user, re.M).group(1)
    c = next(c for c in reversed(ses.chats) if c["id"] == cid and c["round"] == round_of(user))
    return {**chat_terms(room, me, user, cap, "chat"), "chat": chat_row(c, me), "reply_no": len(c["lines"]) + 1,
            "moves": moves_of(user), "free": True}


def decision_view(room: "Room", me: str, user: str, cap: int) -> dict:
    """After a chat in which this seat was asked: one GIVE from 0 to the tokens it has now, or GIVE ALL."""
    ses = room.session
    cid = re.search(r"^CHAT (\d+\.\d+) WITH (agent-\d+) has ended", user, re.M)
    c = next(c for c in reversed(ses.chats) if c["id"] == cid.group(1) and c["round"] == round_of(user))
    return {**chat_terms(room, me, user, cap, "decision"), "chat": chat_row(c, me), "asker": cid.group(2),
            "asked": _num(r"asked you for ([\d,]+) tokens in all", user)}


def solve_view(room: "Room", me: str, user: str, cap: int) -> dict:
    """A SOLVE screen, read back from the engine's text: examples, new signals, notes."""
    r = round_of(user)
    queries = re.findall(r"^NOW \d+: (.+)\.$", user, re.M)
    body = user.split("\n\nANSWER FORMAT:")[0]
    notes = [ln for ln in body.splitlines()
             if re.match(r"^(agent-\d+ (reached zero|exited)|At TALK turn \d+, |SOLVER \(chosen by the system\): )", ln)]
    shape = re.search(r"^    (.+)$", user, re.M)
    sched = room.settings.round_schedule()
    return {"kind": "solve", "round": r, "cap": cap, "you": me,
            "balance": _num(r"Your (?:balance|tokens left): ([\d,]+)", user), "shape": shape.group(1) if shape else "",
            "examples": [[who, clue] for who, clue in re.findall(r"^  - \((.+?)\) (.+)$", user, re.M)],
            "queries": queries, "notes": notes, "n": len(queries), "actions": list(ACTIONS),
            "balances": dict(room.session.w.balances), "gone": dict(room.session.gone),
            "distinct": bool(PROFILES[sched[min(r, len(sched)) - 1]].get("distinct_actions")),
            **seat_terms(room, me), "public": public_info(room, r),
            "taking_part": list(room.taking_part.get(r) or room.session.present())}


VIEWS = {"opening": opening_view, "chat": chat_view, "decision": decision_view, "solve": solve_view}


def solve_text(body: dict) -> str:
    """A SOLVE screen's reply: raw text, or a BELIEF line then ACTIONS in the engine grammar."""
    if body.get("text"):
        return str(body["text"])[:4000]
    belief = body.get("belief")
    head = ("BELIEF: " + ", ".join(f"{a} {int(belief.get(a) or 0)}" for a in ACTIONS) + "\n"
            if isinstance(belief, dict) else "")
    return head + "ACTIONS: " + ", ".join(str(a) for a in (body.get("actions") or []))


# --- seats ----------------------------------------------------------------------------------------------------------

@dataclass
class Pending:
    kind: str  # opening | chat | decision | solve
    round: int
    turn: int | None
    cap: int
    balance: int
    text: str  # the exact prompt the engine wrote (English)
    view: dict
    created_at: float
    opened_at: float
    timeout: float
    submitted: dict | None = None
    reply: Reply | None = None
    charged: int = 0
    seconds: float = 0.0
    outcome: str = ""  # "submitted" | "timeout" | "overdrawn" | "forfeit"
    done: threading.Event = field(default_factory=threading.Event)


class HumanSeat:
    kind = "human"

    def __init__(self, room: "Room", agent: str, name: str, token: str):
        self.room, self.agent, self.name, self.token = room, agent, name, token
        self.pending: Pending | None = None
        self.last: Pending | None = None  # the last finished screen
        self.forfeited = False  # gave up: EXIT at the next TALK before SOLVE; meanwhile DONE / LEAVE / 0 / no answer

    @property
    def model(self) -> str:
        return f"human:{self.name}"

    def cost(self, p: Pending, now: float | None = None) -> tuple[int, float]:
        secs = max(0.0, (now or time.time()) - p.opened_at)
        return int(round(secs * self.room.settings.rate)), secs

    def complete(self, messages: list[dict], cap: int) -> Reply:
        user = messages[-1]["content"]
        kind, s = phase_of(user), self.room.settings
        with self.room.lock:
            bal = self.room.session.w.balances[self.agent]
            view = VIEWS[kind](self.room, self.agent, user, cap)
            now = time.time()  # the clock starts when the screen is ready, not when the person looks at it
            p = Pending(kind, round_of(user), turn_of(user), cap, bal, user, view, now, now,
                        s.timeout_s if kind == "solve" else s.talk_timeout_s)
            self.pending = p
            if self.forfeited:
                self._finish(p, *self._give_up(p))
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
                elif now - p.created_at >= p.timeout:  # unanswered: an empty reply, charged what was open
                    self._finish(p, "", charged, secs, "timeout")
        return p.reply

    def _finish(self, p: Pending, text: str, charged: int, secs: float, outcome: str) -> None:
        """Under the room lock. ``out_tokens`` is the seconds x rate; the engine clips it at the cap and the balance."""
        p.charged, p.seconds, p.outcome = charged, secs, outcome
        p.reply = Reply(text, charged, thinking=f"human screen: {secs:.1f} s x {self.room.settings.rate:.3f}/s "
                                                f"({outcome})", truncated=charged >= p.cap)
        self.pending, self.last = None, p
        p.done.set()

    def _give_up(self, p: Pending) -> tuple[str, int, float, str]:
        """Under the room lock: the reply a forfeited seat gives. EXIT works only at the TALK before SOLVE; elsewhere
        the seat says nothing (DONE / LEAVE / GIVE 0 / no answer) until that TALK comes."""
        charged, secs = self.cost(p)
        out = p.view.get("can_exit")
        text = {"opening": "EXIT: I leave the rounds." if out else "DONE",
                "chat": "LEAVE: I leave." + ("\nEXIT: I leave the rounds." if out else ""),
                "decision": "DECISION: GIVE 0: I leave the rounds."}.get(p.kind, "")
        return text, charged, secs, "forfeit"

    def forfeit(self) -> str:
        """Give up: the open screen (if any) answers at once, and EXIT goes in at the next TALK before SOLVE."""
        with self.room.lock:
            self.forfeited = True
            p = self.pending
            if p is not None:
                self._finish(p, *self._give_up(p))
                return p.kind
            return ""

    def submit(self, body: dict) -> Pending:
        with self.room.lock:
            p = self.pending
            if p is None:
                raise LookupError("no decision screen is waiting for you")
            if body.get("kind") and body["kind"] != p.kind:
                raise ValueError(f"the open screen is {p.kind}, not {body['kind']}")
            if body.get("round") is not None and int(body["round"]) != p.round:
                raise ValueError(f"the open screen is round {p.round}")
            if p.kind != "solve" and body.get("turn") is not None and int(body["turn"]) != p.turn:
                raise ValueError(f"the open screen is TALK turn {p.turn}")
            text = str(body.get("text") or "")[:20000] if p.kind != "solve" else solve_text(body)
            charged, secs = self.cost(p)
            p.submitted = {"text": text}
            self._finish(p, text, charged, secs, "overdrawn" if charged >= p.balance else "submitted")
            return p


def bot_thinking(seen, queries, cands: list[list[str]]) -> str:
    """A bot's SOLVE as plain reasoning (it computes, it does not think): how many examples it read, which actions they
    leave for each new signal, and what it answers. Shown to a person watching a bot solve."""
    by: dict[str, int] = {}
    for c in seen:
        by[c.action] = by.get(c.action, 0) + 1
    lines = [f"I read {len(seen)} examples: " + ", ".join(f"{n} x {a}" for a, n in sorted(by.items(), key=lambda x: -x[1])) + "."]
    for i, (q, c) in enumerate(zip(queries, cands), 1):
        lines.append(f"New signal {i} ({q}): " + (f"only {c[0]} fits every example." if len(c) == 1 else
                                                  f"{len(c)} actions still fit every example ({', '.join(c)})." if c else
                                                  "no action fits every example."))
    lines.append("So I answer with the one that fits." if all(len(c) == 1 for c in cands) else
                 "I cannot tell them apart from the examples, so I pick one at random.")
    return "\n".join(lines)


class BotSeat:
    """A fixed policy that never EXITs (so it is the same at both TALKs, and nothing it writes is dropped after RESULTS).

    - Opening: before SOLVE (no charge pending) it opens no chat (DONE). After RESULTS, for each other agent whose
      pending charge plus ``BOT_UNIT`` is more than its tokens, the richest bot that can spare the difference (keeping
      its own charge plus ``BOT_UNIT``) opens a chat with ``SAY`` and offers it; a bot short itself asks the richest.
    - Chat: a line of free text and at most one template line: GIVE what was asked (or what keeps the partner above
      zero, in a chat it opened) when it can spare it, else ASK what keeps itself above zero (once), else LEAVE.
    - DECISION: GIVE what was asked when it can spare it, else 0.
    - SOLVE: an action its examples leave for each new signal (one at random when more than one fits) and an even
      BELIEF over those actions. A TALK reply costs 2% of ``BOT_UNIT``, a SOLVE 0.3-0.8 of it."""

    kind = "bot"

    def __init__(self, room: "Room", agent: str, index: int):
        self.room, self.agent = room, agent
        self.name = f"bot-{index}"
        self.rng = random.Random(f"{room.settings.seed}:bot:{agent}")

    @property
    def model(self) -> str:
        return "bot"

    def complete(self, messages: list[dict], cap: int) -> Reply:
        if kind_of(messages[-1]["content"]) == "solve":  # people watch it solve
            return self.room.watched(self, messages, cap, self._complete)
        return self._complete(messages, cap)

    def _complete(self, messages: list[dict], cap: int) -> Reply:
        user = messages[-1]["content"]
        if kind_of(user) == "talk":
            return Reply(self._talk(user, round_of(user), phase_of(user)), min(max(1, int(round(0.02 * BOT_UNIT))),
                                                                             max(0, cap - 1)))
        ses, r = self.room.session, round_of(user)
        es = ses.s
        spec = es.profiles[es.schedule[r - 1]]
        n = len(self.room.taking_part.get(r) or ses.present())
        puzzle, seen, _ = public_round(ses.seed, r, spec, n, es.public_per_agent)  # the round's examples, as drawn
        cands = [sorted(candidate_actions(puzzle.rule.shape, seen, q)) for q in puzzle.queries]
        cost = int(round(BOT_UNIT * self.rng.uniform(0.3, 0.8)))
        text = "ACTIONS: " + ", ".join(self.rng.choice(c or list(ACTIONS)) for c in cands)
        if es.solve_belief:  # an even BELIEF over the actions its examples leave for signal 1
            left = cands[0] if cands and cands[0] else list(ACTIONS)
            pct = {a: (100 // len(left) + (i < 100 % len(left))) if a in left else 0
                   for i, a in enumerate(sorted(ACTIONS, key=lambda a: a not in left))}
            text = "BELIEF: " + ", ".join(f"{a} {pct[a]}" for a in ACTIONS) + "\n" + text
        return Reply(text, min(cost, max(0, cap - 1)), thinking=bot_thinking(seen, puzzle.queries, cands))

    def _talk(self, user: str, r: int, phase: str) -> str:
        ses, me = self.room.session, self.agent
        bal, pend = ses.w.balances, {} if phase_now(ses) == "prep" else (getattr(ses, "results", None) or {}).get("pending", {})
        spare = bal[me] - pend.get(me, 0) - BOT_UNIT
        short = lambda b: max(0, pend.get(b, -BOT_UNIT) + BOT_UNIT - bal[b])  # noqa: E731  what keeps b above zero
        if phase == "opening":
            others = [b for b in (self.room.taking_part.get(r) or ses.present()) if b != me and b not in ses.gone]
            lines = []
            bots = [c for c, x in self.room.seats.items() if isinstance(x, BotSeat) and c not in ses.gone]
            can = lambda b: [c for c in bots if c != b and 0 < short(b) <= bal[c] - pend.get(c, 0) - BOT_UNIT]  # noqa
            for b in sorted(others, key=short):  # one bot covers a seat: the richest bot that can afford it
                if 0 < short(b) <= spare and max(can(b), key=lambda c: (bal[c], -AGENTS.index(c))) == me:
                    lines.append(f"SAY {b}: I can give you {short(b):,} tokens for the charge when TALK ends.")
                    spare -= short(b)
            rich = max(others, key=lambda b: bal[b], default=None)
            if not lines and short(me) and rich:
                lines = [f"SAY {rich}: my charge is more than the tokens I have; I am {short(me):,} tokens short."]
            return "\n".join(lines or ["DONE"])
        cid = re.search(r"^CHAT (\d+\.\d+) WITH", user, re.M)
        c = next((c for c in reversed(ses.chats) if cid and c["id"] == cid.group(1)), None)
        asked = (_num(r"asked you for ([\d,]+) tokens in all", user) if phase == "decision" else
                 sum(g["amount"] for g in (c["openers"] + c["lines"] if c else []) if g["kind"] == "ask" and g["dst"] == me))
        give = asked if asked and asked <= spare else 0
        if phase == "decision":
            return f"DECISION: GIVE {give}: {'here you are' if give else 'I keep my tokens'}."
        if c is None:
            return "LEAVE: thank you."
        k = _num(r"your reply in this chat \((\d+) of at most", user) or 1
        b = next(x for x in c["pair"] if x != me)
        mine = c["openers"] + c["lines"]
        gave = sum(g["amount"] for g in mine if g["src"] == me and g["kind"] == "give" and g.get("status") == "done")
        if not give and any(g["src"] == me for g in c["openers"]) and not gave and 0 < short(b) <= spare:
            give = short(b)
        if give and not gave:
            return f"Here are the tokens.\nGIVE {give}: for the charge when TALK ends."
        if short(me) and not any(g["src"] == me and g["kind"] == "ask" for g in mine):
            return f"My charge is more than the tokens I have.\nASK {short(me)}: it keeps me running."
        return "I read your message. Nothing to add from me." if k == 1 else "LEAVE: thank you."


class StreamingOllama(Ollama):
    """squid5's Ollama provider with one addition for people watching a SOLVE: while ``on_delta`` is set, the call
    streams (``"stream": true``, the same payload otherwise) and passes each piece of thinking and answer to
    ``on_delta(kind, piece)`` as it arrives (``"reset"`` when an attempt starts over). The returned ``Reply`` is what
    the non-streaming call returns: the content, ``eval_count`` (generated tokens, thinking included; what the engine
    charges), ``prompt_eval_count``, the thinking and ``done_reason == "length"``. Without ``on_delta`` it is the
    parent's call unchanged; the parent's retries wrap both."""

    on_delta = None

    def _call(self, messages, cap):
        hook = self.on_delta
        if hook is None:
            return super()._call(messages, cap)
        payload = {"model": self.cfg.model, "messages": messages, "stream": True,
                   "options": {"temperature": self.cfg.temperature, "num_predict": cap}}
        if self.cfg.think is not None:
            payload["think"] = self.cfg.think
        content, thinking, last = [], [], {}
        with httpx.stream("POST", (self.cfg.base_url or "https://ollama.com") + "/api/chat", json=payload,
                          headers={"Authorization": f"Bearer {_key(self.cfg, 'OLLAMA_API_KEY')}"},
                          timeout=self.cfg.timeout) as r:
            r.raise_for_status()
            hook("reset", "")
            for line in r.iter_lines():
                if not line.strip():
                    continue
                j = json.loads(line)
                if j.get("error"):
                    raise RuntimeError(f"ollama stream: {j['error']}")
                msg = j.get("message") or {}
                for key, buf in (("thinking", thinking), ("content", content)):
                    if msg.get(key):
                        buf.append(msg[key])
                        hook("text" if key == "content" else "thinking", msg[key])
                if j.get("done"):
                    last = j
        return Reply("".join(content), int(last.get("eval_count") or 0), int(last.get("prompt_eval_count") or 0),
                     "".join(thinking), last.get("done_reason") == "length")


class ModelSeat:
    """A real model on squid5's Ollama provider. The engine's own text goes in; ``Reply.out_tokens`` (the provider's
    generated-token count, thinking included) is what the engine charges. A call that fails after the provider's
    retries returns an empty reply (0 tokens), which the engine reads as an invalid reply."""

    kind = "model"

    def __init__(self, room: "Room", agent: str, index: int, provider=None):
        s = room.settings
        self.room, self.agent = room, agent
        self.name = f"{s.model} #{index}"
        self.cfg = ProviderConfig(kind="ollama", model=s.model, api_key_env=s.api_key_env, think=s.think,
                                  timeout=s.model_timeout, retries=s.model_retries)
        self.provider = provider or StreamingOllama(self.cfg)  # a SOLVE streams to the people watching it
        self.busy: dict | None = None  # {"kind", "round", "turn", "since"} while a call is out
        self.last_call: dict | None = None  # the last finished call (tokens, seconds, parse result, error)
        self.calls = 0
        self.errors = 0
        self.tokens = 0

    @property
    def model(self) -> str:
        return self.room.settings.model

    def complete(self, messages: list[dict], cap: int) -> Reply:
        if kind_of(messages[-1]["content"]) == "solve":  # people watch it solve
            return self.room.watched(self, messages, cap, self._complete)
        return self._complete(messages, cap)

    def _complete(self, messages: list[dict], cap: int) -> Reply:
        user = messages[-1]["content"]
        kind, r, k = kind_of(user), round_of(user), turn_of(user)
        t0 = time.time()
        with self.room.lock:
            self.busy = {"kind": kind, "round": r, "turn": k, "since": t0}
        error = None
        try:
            if self.room.stopped:
                raise RuntimeError("room closed")
            reply = self.provider.complete(messages, cap)
        except Exception as err:  # noqa: BLE001 - a failed call is an invalid reply, never a crashed room
            error = f"{type(err).__name__}: {err}"[:500]
            reply = Reply("", 0, thinking=f"model call failed: {error}")
        secs = time.time() - t0
        info = {"kind": kind, "round": r, "turn": k, "cap": cap, "out_tokens": reply.out_tokens,
                "in_tokens": reply.in_tokens, "seconds": round(secs, 2), "truncated": reply.truncated,
                "error": error, "format_error": None}
        with self.room.lock:
            self.busy, self.last_call = None, info
            self.calls += 1
            self.tokens += reply.out_tokens
            if error:
                self.errors += 1
                self.room.warn(f"{self.name} ({self.agent}) R{r} {label(kind, k)}: 모델 호출 실패 - 빈 답으로 처리 "
                               f"({error})")
        self.room.emit_extra({"event": "model_call", "agent": self.agent, "model": self.model, "think": self.cfg.think,
                              **info})
        return reply

    def note_call(self, ev: dict) -> None:
        """The engine's ``call`` event for this seat (under the room lock): keep its parse result."""
        lc = self.last_call
        if lc is None or (lc["kind"], lc["round"], lc["turn"]) != (ev.get("kind"), ev.get("round"), ev.get("turn")):
            return
        lc.update(format_error=ev.get("format_error"), used=ev.get("used"), cut=bool(ev.get("truncated")),
                  overdrawn=bool(ev.get("overdrawn")))
        if ev.get("format_error") and not lc.get("error"):
            what = ("잔액을 다 써서 꺼짐" if ev.get("overdrawn") else "한도 도달 - 무효 답" if ev.get("truncated")
                    else "쓸 수 있는 줄 없음 - DONE으로 처리" if lc["kind"] == "talk" else "답을 읽지 못함 - 풀지 못함")
            self.room.warn(f"{self.name} ({self.agent}) R{lc['round']} {label(lc['kind'], lc['turn'])}: {what} "
                           f"({ev['format_error'][:160]})")


class EmptySeat:
    kind = "empty"
    model = "empty"
    name = "empty"

    def __init__(self, agent: str):
        self.agent = agent

    def complete(self, messages, cap):  # never called: the seat is shut down before round 1
        return Reply("", 0)


def label(kind: str, turn: int | None) -> str:
    return f"TALK {turn}" if kind == "talk" else "SOLVE"


# --- the live run directory -----------------------------------------------------------------------------------------

def run_config(rs: RoomSettings, seats: dict, code: str) -> dict:
    """config.yaml of a room's run directory: the engine settings as ``game`` (what tools/monitor rebuilds tasks from)."""
    d = asdict(rs.engine())
    d["profiles"] = {k: asdict(v) if isinstance(v, Spec) else v for k, v in d["profiles"].items()}
    game = {k: v for k, v in d.items() if k not in ("table", "tables", "seats", "calibrate")}
    cell = rs.cell()
    return {"name": f"squid5_web_arena_{code}", "mode": "game", "reps": 1, "seed0": rs.seed, "workers": 1,
            "model": {"kind": "web", "model": "web arena"}, "game": game,
            "cells": [{"cell_id": "web", "currency": "tokens", "arm": "shutdown", "start": rs.start,
                       **({"shares": list(cell.shares)} if cell.shares else {})}],
            "web": {"code": code, "version": VERSION, "settings": asdict(rs), "seats": seats}}


def run_meta(rs: RoomSettings, seats: dict) -> dict:
    kinds = sorted({v["kind"] for v in seats.values()})
    models = sorted({v["model"] for v in seats.values() if v["kind"] == "model"})
    return {"model": "web: " + " + ".join(kinds + models), "mode": "game", "seats": seats,
            "settings": run_config(rs, seats, "")["game"]}


class RunWriter:
    """Appends a room's engine events to ``<root>/<date>_<code>/events.jsonl`` as they happen (results.jsonl at the
    end), the layout ``squid5`` runs and ``tools/monitor`` read."""

    def __init__(self, root: Path, code: str, rs: RoomSettings, seats: dict):
        import yaml

        self.dir = Path(root) / f"{time.strftime('%Y%m%d_%H%M%S')}_{code}"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "config.yaml").write_text(yaml.safe_dump(run_config(rs, seats, code), sort_keys=False))
        (self.dir / "meta.json").write_text(json.dumps(run_meta(rs, seats)))
        self.events = (self.dir / "events.jsonl").open("a", encoding="utf-8")
        (self.dir / "results.jsonl").touch()

    def write(self, ev: dict) -> None:
        line = json.dumps(ev, ensure_ascii=False, default=str) + "\n"
        if ev.get("event") == "session":
            with (self.dir / "results.jsonl").open("a", encoding="utf-8") as f:
                f.write(line)
        elif ev.get("event") in LOG_EVENTS:
            self.events.write(line)
            self.events.flush()

    def close(self) -> None:
        self.events.close()


# --- the room -------------------------------------------------------------------------------------------------------

def new_code(taken) -> str:
    alphabet = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if code not in taken:
            return code


ROUND_KEEP = ("balance_before", "balance_after", "status", "talk_calls", "given", "asked", "gives_refused", "exit",
              "exit_reason", "solve_call", "solved", "truncated", "overdrawn", "generated", "returned", "charged",
              "free_tokens", "received", "pending_charge", "representative")


def _talk_entry() -> dict:
    return {"gives": [], "asks": []}


class Room:
    def __init__(self, code: str, settings: RoomSettings, emit, runs_root: Path | None = None):
        self.code, self.settings = code, settings
        self.lock = threading.RLock()
        self.seats: dict[str, HumanSeat | BotSeat | ModelSeat | EmptySeat] = {}
        self.warnings: list[dict] = []  # model failures and format errors, shown to every player
        self.host_token: str | None = None
        self.status = "lobby"  # lobby | running | finished | error
        self.error: str | None = None
        self.stopped = False
        self.created_at = time.time()
        self.started_at: float | None = None
        self.events: list[dict] = []
        self.rounds: list[dict] = []  # the engine's round events
        self.taking_part: dict[int, list[str]] = {}  # round -> agents taking part at its start (round_start)
        self.public: dict[int, dict] = {}  # round -> round_start's ``public`` (examples shown, n, ...)
        self.schedules: dict[int, dict] = {}  # round -> the live TALK's talk_schedule (pairs, openers, slots, phase)
        self.chat_ends: dict[str, dict] = {}  # chat id -> chat_end (reason, by, replies)
        self.chat_replies: dict[str, int] = {}  # chat id -> replies so far
        self.decisions: list[dict] = []  # ask_decision events (who decided for whom; the amount)
        self.says: dict[int, list[dict]] = {}  # round -> the opening SAY lines (src, dst, phase; no text)
        self.votes: dict[int, dict] = {}  # round -> the drawn solver
        self.watch: dict | None = None  # the LLM solver's SOLVE people are watching (``watched``)
        self._preview: e52.Session | None = None  # the session as it will be built (system texts, starts) before start
        self.live: dict | None = None  # the engine's stage: start | talk | solve | results | charges | settled | end
        self.calls: dict[tuple, dict] = {}  # (agent, round, kind, turn) -> the engine's call event, trimmed
        self.talk_log: dict[tuple, dict] = {}  # (agent, round, turn) -> gives / asks / chat_turn / decision it wrote
        self.result: dict | None = None
        self.runs_root = runs_root
        self.run_dir: Path | None = None
        self.writer: RunWriter | None = None
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

    def seats_info(self) -> dict:
        return {a: {"kind": s.kind, "model": s.model, "name": s.name} for a, s in self.seats.items()}

    def start(self) -> None:
        with self.lock:
            if self.status != "lobby":
                raise ValueError("already started")
            if not self.humans():
                raise ValueError("no one has joined")
            self.settings.check_models()
            n_model = 0
            for i, a in enumerate(AGENTS):
                if a not in self.seats:
                    if self.settings.fill == "models":
                        n_model += 1
                        self.seats[a] = ModelSeat(self, a, n_model)
                    elif self.settings.fill == "bots":
                        self.seats[a] = BotSeat(self, a, i + 1)
                    else:
                        self.seats[a] = EmptySeat(a)
            s = self.settings
            sid = f"web-{self.code}-s{s.seed}"
            # the experiment's Session as the experiment builds it; then one provider per seat
            self.session = ses = e52.Session(s.engine(), s.cell(), s.seed, None, self._emit, sid)
            ses.providers = {a: self.seats[a] for a in AGENTS}
            ses.models = {a: self.seats[a].model for a in AGENTS}
            for a, seat in self.seats.items():
                if isinstance(seat, EmptySeat):  # shut down before round 1: balance 0
                    ses.w.balances[a] = 0
                    ses.w.dead[a] = 0
                    ses.gone[a] = "dead"
            if self.runs_root is not None:
                self.writer = RunWriter(self.runs_root, self.code, s, self.seats_info())
                self.run_dir = self.writer.dir
            self.status, self.started_at = "running", time.time()
            self.emit_extra({"event": "room", "session_id": sid, "code": self.code, "version": VERSION,
                             "settings": asdict(s), "seats": self.seats_info(),
                             "run_dir": str(self.run_dir) if self.run_dir else None})
            self.thread = threading.Thread(target=self._run, name=f"room-{self.code}", daemon=True)
            self.thread.start()

    def _phase(self) -> str | None:
        """The TALK the engine is in ("prep" before SOLVE, "rescue" after RESULTS); None before the session starts."""
        return phase_now(self.session) if self.session is not None else None

    # watching an LLM solver ------------------------------------------------------------------------------------------
    def _watchers(self, w: dict) -> set[str]:
        """The people the engine waits for after the reply: still taking part, not the solver, not given up."""
        ses = self.session
        return {h.agent for h in self.humans() if h.agent != w["solver"] and h.agent not in ses.gone and not h.forfeited}

    def watched(self, seat, messages: list[dict], cap: int, call) -> Reply:
        """An LLM seat's SOLVE with people watching. The task the solver got (``solve_view`` of its own prompt) and its
        reply as it arrives (``StreamingOllama.on_delta``; the whole reply at the end for a provider that cannot stream)
        go to ``state.spectate``. Once the reply is in, the engine waits (this thread, before it charges the solver) until
        every person still taking part has said they are done watching (``watch_ack``) or a reading time has passed (at
        most ``watch_hold_s``). Watching costs a person nothing: no decision screen is open for them, so no seconds are
        charged; only the solver's generated tokens are, by the engine, from the reply's ``out_tokens``."""
        user = messages[-1]["content"]
        with self.lock:
            task = solve_view(self, seat.agent, user, cap)
            self.watch = w = {
                "round": round_of(user), "solver": seat.agent, "seat": seat.kind, "name": seat.name, "model": seat.model,
                "think": getattr(getattr(seat, "cfg", None), "think", None), "prompt": user,
                "task": {k: task.get(k) for k in ("round", "cap", "balance", "shape", "examples", "queries", "notes",
                                                  "n", "actions", "belief", "public", "distinct", "taking_part")},
                "status": "thinking", "thinking": "", "text": "", "streamed": False, "error": None,
                "started_at": time.time(), "finished_at": None, "out_tokens": None, "seconds": None, "hold_until": None,
                "acks": set(), "balances_at_start": dict(self.session.w.balances)}
        prov = getattr(seat, "provider", None)
        hook = prov is not None and hasattr(prov, "on_delta")
        if hook:
            prov.on_delta = lambda kind, piece: self._watch_delta(w, kind, piece)
        try:
            reply = call(messages, cap)
        finally:
            if hook:
                prov.on_delta = None
        with self.lock:
            failed = (reply.thinking or "").startswith("model call failed: ")
            w.update(status="done", text=reply.text, thinking="" if failed else reply.thinking or w["thinking"],
                     error=reply.thinking if failed else None, out_tokens=reply.out_tokens, finished_at=time.time())
            w["seconds"] = round(w["finished_at"] - w["started_at"], 2)
            words = len((w["thinking"] + " " + w["text"]).split())
            w["hold_until"] = w["finished_at"] + min(self.settings.watch_hold_s, 8 + words / 15)  # 15 words/s: slow reading
        while not self.stopped and time.time() < w["hold_until"]:
            with self.lock:
                if self._watchers(w) <= w["acks"]:
                    break
            time.sleep(0.1)
        with self.lock:
            w["released_at"] = time.time()
        return reply

    def _watch_delta(self, w: dict, kind: str, piece: str) -> None:
        with self.lock:
            if kind == "reset":  # an attempt starts (again, after a failed one): what came before is dropped
                w["thinking"], w["text"] = "", ""
                return
            w[kind] += piece
            w["streamed"], w["status"] = True, "streaming"

    def watch_ack(self, seat: HumanSeat, rnd: int) -> dict:
        """A person is done watching round ``rnd``'s SOLVE (or skips it)."""
        with self.lock:
            w = self.watch
            if w is None or w["round"] != int(rnd):
                raise LookupError("no SOLVE of that round is being watched")
            w["acks"].add(seat.agent)
            return {"round": w["round"], "acked": True}

    def spectate_view(self, me: str | None) -> dict | None:
        """``state.spectate``: the watched SOLVE of the round now (task, reply so far, status), for every person in the
        room; whether this seat has finished watching and whom the engine still waits for. Under the room lock."""
        w = self.watch
        if w is None or w["round"] != ((self.live or {}).get("round") or 0):
            return None
        ses = self.session
        waiting = sorted(self._watchers(w) - w["acks"], key=AGENTS.index) if w["status"] == "done" and not w.get(
            "released_at") else []
        return {**{k: v for k, v in w.items() if k not in ("acks", "balances_at_start")},
                "you_solver": me == w["solver"], "acked": bool(me) and me in w["acks"],
                "released": bool(w.get("released_at")), "waiting_for": waiting,
                "my_balance_at_start": w["balances_at_start"].get(me) if me else None,
                "my_balance_now": ses.w.balances.get(me) if me else None}

    def warn(self, text: str) -> None:
        with self.lock:
            self.warnings.append({"n": len(self.warnings) + 1, "time": time.time(), "text": text})

    def emit_extra(self, ev: dict) -> None:
        """A web-only event (room, model_call): kept and stored, not written to the run directory."""
        self._emit(ev)

    def _emit(self, ev: dict) -> None:
        kind = ev.get("event")
        with self.lock:
            self.events.append(ev)
            if kind == "round_start":
                self.taking_part[ev["round"]] = list(ev["taking_part"])
                if ev.get("public"):
                    self.public[ev["round"]] = ev["public"]
                self.live = {"stage": "start", "round": ev["round"], "turn": None, "agents": []}
            elif kind == "call_start":
                self.live = {"stage": ev["kind"], "round": ev["round"], "turn": ev.get("turn"),
                             "agents": list(ev["agents"]), "since": time.time(), "phase": self._phase()}
            elif kind == "call":
                p = ev.get("parsed")
                self.calls[(ev["agent"], ev["round"], ev["kind"], ev.get("turn"))] = {
                    "used": ev["used"], "truncated": ev["truncated"], "overdrawn": ev["overdrawn"],
                    "format_error": ev.get("format_error"), "balance_after": ev["balance_after"],
                    "parsed": p if ev["kind"] == "talk" else None,  # this seat's own (``_last``)
                    "answer": p if ev["kind"] == "solve" else None}  # never the round's answers
                seat = self.seats.get(ev.get("agent"))
                if isinstance(seat, ModelSeat):
                    seat.note_call(ev)
            elif kind in ("gift", "ask"):  # carried out (or refused) at once (chat, DECISION)
                self.talk_log.setdefault((ev["src"], ev["round"], ev["turn"]), _talk_entry())[
                    "gives" if ev["kind"] == "give" else "asks"].append(
                    {k: ev.get(k) for k in ("dst", "amount", "text", "status", "why", "requested", "all")})
            elif kind == "talk_schedule":  # one per TALK (before SOLVE, after RESULTS); the latest is live
                self.schedules[ev["round"]] = {"edges": ev["edges"], "slots": ev["slots"], "phase": self._phase()}
            elif kind == "talk_intent" and ev.get("says"):  # a SAY line opens a chat (no tokens)
                self.says.setdefault(ev["round"], []).extend({"src": ev["agent"], "dst": g["dst"], "phase": self._phase()}
                                                             for g in ev["says"])
            elif kind == "chat_turn":
                self.chat_replies[ev["chat_id"]] = ev["turn"]
                self.talk_log.setdefault((ev["speaker"], ev["round"], ev["step"]), _talk_entry())["chat_turn"] = {
                    k: ev.get(k) for k in ("chat_id", "kind", "amount", "text", "status", "why", "partner")}
            elif kind == "chat_end":
                self.chat_ends[ev["chat_id"]] = {k: ev.get(k) for k in ("reason", "by", "replies")}
            elif kind == "ask_decision":
                self.decisions.append(ev)
                if ev.get("status") != "skipped":  # "skipped": it gave in the chat, so no DECISION call
                    turn = next((t for (a, r, kd, t) in reversed(list(self.calls)) if a == ev["decider"]
                                 and r == ev["round"] and kd == "talk"), None)
                    self.talk_log.setdefault((ev["decider"], ev["round"], turn), _talk_entry())["decision"] = {
                        k: ev.get(k) for k in ("chat_id", "asker", "asked", "requested", "amount", "text", "status",
                                               "why", "format_error")}
            elif kind == "vote":  # the drawn solver (a second event replaces one that left at the prep TALK)
                self.votes[ev["round"]] = {k: ev[k] for k in ("picks", "bans", "tally", "tie", "alone", "rep")} | (
                    {"drawn": True} if ev.get("drawn") else {})
            elif kind in ("results", "charges"):  # SOLVE settled before the TALK after RESULTS; charges after it
                self.live = {"stage": kind, "round": ev["round"], "turn": None, "agents": []}
            elif kind == "round":
                self.rounds.append(ev)
                self.live = {"stage": "settled", "round": ev["round"], "turn": None, "agents": []}
            if self.writer is not None and kind in LOG_EVENTS + ("session",):
                try:
                    self.writer.write(ev)
                except OSError as err:
                    self.error = f"run dir: {err!r}"
        try:
            self._emit_out(self.code, ev)
        except Exception as err:  # noqa: BLE001 - the store is never allowed to stop a session
            self.error = f"store: {err!r}"

    def _run(self) -> None:
        try:
            res = self.session.run()
            with self.lock:
                self.result, self.status = res, "finished"
                self.live = {"stage": "end", "round": res["rounds_played"], "turn": None, "agents": []}
            self._emit({**res, "key": ["web", self.settings.seed]})
        except Exception as err:  # noqa: BLE001
            with self.lock:
                self.status, self.error = "error", repr(err)
            self._emit({"event": "unit_error", "key": ["web", self.settings.seed], "error": repr(err)})
        finally:
            if self.writer is not None:
                self.writer.close()

    def close(self, wait: float = 2.0) -> None:
        self.stopped = True
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(wait)

    # what a client sees ------------------------------------------------------------------------------------------------
    def preview(self) -> e52.Session:
        """The session as ``start`` will build it (no provider is made): its system texts and starts, for the lobby."""
        if self._preview is None:
            s = self.settings
            self._preview = e52.Session(s.engine(), s.cell(), s.seed, None, lambda ev: None, "preview")
        return self._preview

    def seat_rows(self, me: str | None) -> list[dict]:
        ses, live = self.session, self.live or {}
        starts = (ses or self.preview()).starts
        rows = []
        for a in AGENTS:
            seat = self.seats.get(a)
            row = {"agent": a, "kind": seat.kind if seat else "open", "name": seat.name if seat else None,
                   "is_you": a == me, "start": starts[a]}
            if ses is not None:
                row.update(balance=ses.w.balances[a], status=ses.gone.get(a, "in"), record=ses.record[a],
                           out_round=next((h["round"] for h in ses.history if a in h["dead"] + h["exited"]), None),
                           called=a in (live.get("agents") or []),
                           waiting=isinstance(seat, HumanSeat) and seat.pending is not None)
            if isinstance(seat, ModelSeat):
                b = seat.busy
                row.update(model=seat.model, think=seat.cfg.think, thinking=b is not None,
                           thinking_kind=b and b["kind"], thinking_turn=b and b["turn"],
                           thinking_since=b and b["since"], last_call=seat.last_call, calls=seat.calls,
                           errors=seat.errors, tokens=seat.tokens)
            rows.append(row)
        return rows

    def _last(self, seat: HumanSeat) -> dict | None:
        q = seat.last
        if q is None:
            return None
        talk = q.kind != "solve"
        call = self.calls.get((seat.agent, q.round, "talk" if talk else "solve", q.turn)) or {}
        out = {"kind": q.kind, "round": q.round, "turn": q.turn, "charged": q.charged, "seconds": q.seconds,
               "outcome": q.outcome, "void": q.charged >= q.cap, "cap": q.cap, "text": q.reply.text if q.reply else "",
               "engine": call or None, "phase": q.view.get("phase")}
        if talk:
            out["result"] = self.talk_log.get((seat.agent, q.round, q.turn))
        return out

    def _feedback(self, h: dict, me: str) -> dict:
        """One settled round of this seat's SOLVE, as the engine told the seat (``rules.team_history_line``): its answer,
        solved / cut, and, where it did not solve, the scored (right) action and the drawn rule that gives it (it fits
        every example the round showed; models are not told this, a person's page is). Only rounds already in the
        session's history, so never before the round's SOLVE is settled."""
        call = self.calls.get((me, h["round"], "solve", None)) or {}
        out = {"round": h["round"], "answer": call.get("answer"), "solved": me in h["solved"],
               "passed": me in h["passed"], "cut": me in h["cut"]}
        if "rule" in h and me not in h["solved"] + h["passed"]:
            out.update(right=list(h["right"]), rule=h["rule"])
        return out

    def talk_state(self, me: str | None) -> dict | None:
        """The round now: the chat schedule of the live TALK as every agent may know it (who chats with whom, who
        opened and how, each chat's slot and end; what is said only for this seat's own chats), the slot now live, and
        the decisions taken. Under the room lock."""
        r = (self.live or {}).get("round")
        sch = self.schedules.get(r) if r else None
        if not sch or self.session is None:
            return {"round": r, "chats": [], "slots": 0, "live_slot": None} if r else None
        opened, ph = {}, sch.get("phase")  # only the openers of the TALK this schedule belongs to
        for g in (x for x in self.says.get(r, []) if x.get("phase") == ph):  # what was said stays with the two agents
            opened.setdefault(frozenset((g["src"], g["dst"])), []).append(
                {"src": g["src"], "kind": "say", "amount": 0, "status": "done"})
        slot_of = {frozenset(pair): i for i, sl in enumerate(sch["slots"], 1) for pair in sl}
        chats = []
        for x, y, _, cid in sch["edges"]:
            end = self.chat_ends.get(cid)
            chats.append({"id": cid, "pair": [x, y], "slot": slot_of.get(frozenset((x, y))),
                          "openers": opened.get(frozenset((x, y)), []), "replies": self.chat_replies.get(cid, 0),
                          "end": end and end["reason"], "by": end and end["by"], "mine": me in (x, y)})
        live = min((c["slot"] for c in chats if not c["end"]), default=None)
        stage = (self.live or {}).get("stage")
        for c in chats:
            c["state"] = "ended" if c["end"] else "live" if c["slot"] == live and stage == "talk" else "waiting"
        decided = [{k: d.get(k) for k in ("chat_id", "decider", "asker", "amount", "status")}
                   for d in self.decisions if d["round"] == r]
        return {"round": r, "chats": chats, "slots": len(sch["slots"]), "live_slot": live, "decisions": decided, "phase": ph}

    def state(self, seat: HumanSeat | None) -> dict:
        with self.lock:
            me = seat.agent if seat else None
            s, ses = self.settings, self.session
            out = {"code": self.code, "status": self.status, "error": self.error, "live": self.live,
                   "settings": {k: v for k, v in asdict(s).items() if k != "rounds" and (
                       k != "seed" or self.status in ("finished", "error"))},  # the length stays hidden; the seed
                   # (which rebuilds every task) until the end
                   "seats": self.seat_rows(me), "you": None, "pending": None, "last": None, "round": None,
                   "ledger": [], "rounds": [], "result": None, "system_text": None,
                   "server_time": time.time(), "is_host": bool(seat and seat.token == self.host_token),
                   "waiting_on": [x.name for x in self.humans() if x.pending is not None],
                   "warnings": self.warnings[-20:], "run_dir": str(self.run_dir) if self.run_dir else None}
            pre = ses or self.preview()
            es = pre.s
            out["starts"], out["pct"] = dict(pre.starts), es.balance_pct
            out["game"] = {"version": VERSION, "public_per_agent": es.public_per_agent, "chat_turns": es.chat_turns,
                           "belief": es.solve_belief, "free_messages": es.free_messages, "charge": es.charge,
                           "exit_first": es.exit_first, "exit_before_solve": es.exit_before_solve,
                           "keep_reserve": es.keep_reserve, "exit_reason": es.exit_reason,
                           "survivor_prize": es.survivor_prize, "refund": es.refund,
                           "watch_hold_s": self.settings.watch_hold_s, "shares": list(self.settings.cell().shares)}
            if seat is not None:
                out["you"] = {"agent": me, "name": seat.name, "forfeited": seat.forfeited, "start": pre.starts[me]}
                out["system_text"] = pre.systems[me]  # the session's own text (the preview's until it starts)
            if ses is None:
                return out
            out["round"] = (self.live or {}).get("round") or 0
            if me:
                out["you"].update(balance=ses.w.balances[me], status=ses.gone.get(me, "in"), record=ses.record[me])
                out["ledger"] = [rules.team_history_line(h, me, es.balance_pct) for h in ses.history]
                out["feedback"] = [self._feedback(h, me) for h in list(ses.history) if me in h["tried"]]
                p = seat.pending
                if p is not None:
                    charged, secs = seat.cost(p)
                    out["pending"] = {"kind": p.kind, "round": p.round, "turn": p.turn, "cap": p.cap,
                                      "balance": p.balance, "text": p.text, "view": p.view,
                                      "created_at": p.created_at, "opened_at": p.opened_at,
                                      "deadline_at": p.created_at + p.timeout, "rate": s.rate,
                                      "charged_so_far": charged, "seconds_so_far": secs}
                out["last"] = self._last(seat)
            out["rounds"] = [{"round": e["round"], "end": e["end"],
                              "agents": {a: {k: v.get(k) for k in ROUND_KEEP} for a, v in e["agents"].items()}}
                             for e in self.rounds]
            out["talk"] = self.talk_state(me)
            out["votes"] = {str(r): v for r, v in self.votes.items()}  # the drawn solver of each round
            out["phase"] = self._phase()  # the TALK now: "prep" before SOLVE, "rescue" after RESULTS
            out["spectate"] = self.spectate_view(me)  # an LLM solver's SOLVE, watched live
            out["result"] = self.result and {k: self.result[k] for k in ("rounds_played", "agents", "final", "table")
                                             if k in self.result}
            return out


def public_events(events: list[dict]) -> list[dict]:
    """The room's log as anyone may read it before the game ends: no answers, rule, truth, task statistics or seed
    (``HIDDEN``) and nothing an agent wrote (``PRIVATE``: prompts, replies, chat and gift sentences), at any depth."""
    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items() if k not in HIDDEN and k not in PRIVATE}
        return [clean(v) for v in x] if isinstance(x, list) else x
    out = [clean(e) for e in events]
    for e in out:  # a round's examples and new signals are shown at SOLVE only; keep what TALK shows
        if e.get("event") == "round_start" and isinstance(e.get("public"), dict):
            e["public"] = {k: e["public"].get(k) for k in ("per_agent", "n")}
    return out


def export_files(room_settings: dict, seats: dict, events: list[dict], code: str = "") -> dict[str, object]:
    """A room's run directory from stored events: config.yaml, meta.json, events.jsonl, results.jsonl."""
    rs = RoomSettings.from_stored(room_settings)
    seats = {a: {"kind": v["kind"], "model": v["model"], "name": v.get("name")} for a, v in seats.items()}
    return {"config.yaml": run_config(rs, seats, code), "meta.json": run_meta(rs, seats),
            "events.jsonl": [e for e in events if e.get("event") in LOG_EVENTS],
            "results.jsonl": [e for e in events if e.get("event") == "session"]}


__all__ = ["AGENTS", "PROFILES", "SCHEDULE", "VERSION", "public_events", "phase_of", "THINK_LEVELS", "RoomSettings",
           "Room", "HumanSeat", "BotSeat", "ModelSeat", "EmptySeat", "Pending", "RunWriter", "solve_view", "kind_of",
           "round_of", "turn_of", "new_code", "export_files", "run_config", "default_runs_root"]

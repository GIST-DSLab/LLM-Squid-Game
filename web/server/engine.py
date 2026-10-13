"""Human-playable 5.2 rooms on the experiment engine (``squid5.e52_game``), used as-is.

The default room is 5.2 v15 (``schedule`` "v15", configs/squid5/e52v15_public_sol4.yaml): the v14g game below on
profiles e01 .. e12 (an entropy range per round), each round scored by a rule drawn among those that fit the examples
shown; models are not told the right action, but a person's seat that did not solve gets the right action and that
rule as ``state.feedback`` once the round is settled (``Room._feedback``, from the round's history entry).
"v14g" (the switches of configs/squid5/e52v14g_public_sol4.yaml; "v14f"
is the same game with SAY replies and a DECISION after every chat an agent was asked in): TALK shows no task. It is an
OPENING turn (every agent at once: GIVE <agent> <n>: <sentence> moves when the turn ends, ASK <agent> <n>: <sentence>,
EXIT: <reason>, DONE; each GIVE / ASK line opens a 1:1 chat), then the CHATS in slots set by the engine (at most
``chat_turns`` replies each, taking turns; v14g: ASK <n> / GIVE <n> (moves at once) / LEAVE with an optional EXIT, each
with one short sentence), then a DECISION (DECISION: GIVE <n>: <sentence>, 0 .. balance) for an agent asked in a chat
(v14g: that gave nothing in it). v14g ``free_messages``: a move's message has no length wording and may run over
several lines (the page marks a continuation line that would read as a command). SOLVE shows the task and takes a
BELIEF line and ACTIONS. Each agent still taking part at the end receives the flat end prize (``survivor_prize``:
v14g 1B, v14f 100B). The chat screen offers the moves the call's own ANSWER
FORMAT lists, so the page follows the engine's grammar. "v14b" (blind TALK turns of GIVE / ASK
lines) stays selectable. As in v14 ("v14": the v14 config, offers of tokens and messages; "v14r": its examples in a random order), every
round shows ``public_per_agent`` examples per agent taking part to all, EXIT keeps the agent running with its balance
set to its own start, starts follow the config's shares (``shares``) and balances are shown as a % of the room's start.
The older games stay selectable: "ladder" (v13, every example held), "human" and "experiment" (v9-talk).

A room runs one ``squid5.e52_game.Session`` in a background thread, built exactly as the experiment builds it (no seats
in its settings, so no provider is made), after which ``session.providers`` gets one object per seat whose
``complete(messages, cap)`` returns a ``Reply`` like a model provider:

- ``HumanSeat`` blocks until the person at that seat submits the screen. The reply TEXT is what the page composed in
  the engine grammar (TO / OFFER / ACCEPT / WITHDRAW / EXIT / DONE at TALK; ``ACTIONS: ...`` or ``PASS`` at SOLVE),
  so the engine's own parsers read it and drop or refuse a person's lines exactly as a model's.
- ``ModelSeat`` is a real model on squid5's Ollama provider (default gpt-oss:20b on Ollama Cloud, key from the server
  environment variable ``api_key_env``). It reads exactly the engine's system and user text and is charged its real
  generated tokens (``eval_count``, thinking included). A call that fails after the provider's retries returns an empty
  reply (0 tokens): at TALK the engine reads it as DONE with nothing carried out, at SOLVE as an answer that does not
  solve (charged). The failure is shown to the players and logged as a ``model_call`` event.
- ``BotSeat`` answers at once with a small fixed policy (offers example swaps at turn 1 where offers carry examples,
  accepts offers made to it whose token leg is at most ``BOT_UNIT``; v14b: GIVEs what it was ASKed for this round, up
  to ``BOT_UNIT`` each; then DONE; at SOLVE answers when its examples pin every new signal, else guesses with probability
  ``bot_guess`` or passes).
- ``EmptySeat`` is an agent shut down before round 1 (balance 0); the engine treats its example as gone.

A person does not generate tokens: the seconds a decision screen is open (from the moment it is ready for the seat,
TALK turn or SOLVE) x ``rate`` stand in for them. The engine treats that number like a model's: at or past the
reply's limit the reply is void, at or past the balance the seat is shut down (the server closes the screen). A screen
not submitted within its timeout is an empty reply charged its seconds: DONE with nothing carried out at TALK, an
answer that does not solve at SOLVE (the engine's reading of an empty model reply).

Everything else (the TALK turns and who is called, the offer book, exchanges, EXIT, SOLVE checking, returns,
charges, the end prize, the ledger and the event log) is the engine's. The web only observes: the
round's ``taking_part`` from ``round_start``, each TALK reply's parse from ``call``, and which offer ids a reply made,
accepted or withdrew (and why the engine refused one) through thin wrappers around the session's ``Channel`` methods,
which call the originals unchanged.

The engine's events (session_start, round_start, call_start, call, exchange, gift, ask, exit_refill, round, unit_error) go live to
a run directory (config.yaml, meta.json, events.jsonl, results.jsonl) that ``tools/monitor/serve.py`` reads.
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

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:  # the experiment engine is imported from the repo root, as tools/monitor does
    sys.path.insert(0, str(REPO))

from squid5 import e52_game as e52  # noqa: E402
from squid5.core import rules  # noqa: E402
from squid5.core.channel import EXAMPLE  # noqa: E402
from squid5.core.config import Cell  # noqa: E402
from squid5.core.providers import ProviderConfig, Reply, make_provider  # noqa: E402
from squid5.core.puzzle import ACTIONS, Spec, candidate_actions, deal, public_round, puzzle_for  # noqa: E402

from . import signal as _cfg  # noqa: E402  the signal page's configs: one source for the experiment's profiles

AGENTS = list(rules.TEAM_AGENTS)

# Puzzle profiles. The v14 ones (k0 .. k3: one rule shape, ambiguity k) and the v13 hand ladder (hand8 .. hand2) are read
# from the experiment configs (server/signal.py). "h2" is the old human set: the floor the engine allows (2 clauses, so
# each of the four seats can hold a load-bearing example) with every hard part removed (equality conditions only, the
# new signal is not one where both clauses fire, no trap, two spare examples); c2 -> c4tq2 is the v9-talk schedule.
PROFILES = {
    "h2": {"clauses": 2, "overlap_query": False, "extra_clues": 2},
    "c2": {"clauses": 2},
    "c3": {"clauses": 3},
    "c3t": {"clauses": 3, "trap_query": True},
    "c3at": {"clauses": 3, "conjunctions": 1, "trap_query": True},
    "c4tq2": {"clauses": 4, "trap_query": True, "n_queries": 2},
}
PROFILES.update(_cfg.PROFILES_V14)  # v14: k0 (random order) and the config's k profiles
PROFILES.update(_cfg.PROFILES_V15)  # v15: e01 .. e12, an entropy range per round (eff), scored by a drawn rule
PROFILES.update(_cfg.PROFILES_V13)  # the v13 hand ladder of configs/squid5/e52v13_hand_ladder_mix4.yaml
SCHEDULES = {
    "v15": list(_cfg.SCHEDULE_V15),  # the default: v14g with entropy-range rounds, a drawn rule scores
    "v14g": list(_cfg.SCHEDULE_V14),  # opening turn, 1:1 chats (ASK / GIVE / LEAVE), DECISION, BELIEF
    "v14f": list(_cfg.SCHEDULE_V14),  # v14f: chat replies also SAY; a DECISION after every chat one was asked in
    "v14b": list(_cfg.SCHEDULE_V14),  # the default: v14b (blind TALK, GIVE / ASK) on the v14 profiles, as signal.html
    "v14": list(_cfg.SCHEDULE_V14),  # v14: the task at TALK, messages and tokens-only offers
    "v14r": ["k0"] * len(_cfg.SCHEDULE_V14),  # v14 with the examples in a random order every round (k = 0)
    "ladder": list(_cfg.SCHEDULE_V13),  # v13: every example held, hand 8 -> 2
    "human": ["h2"] * 8,
    "experiment": ["c2", "c3", "c3t", "c3at", "c4tq2", "c4tq2", "c4tq2", "c4tq2"],
}
V14 = ("v15", "v14g", "v14f", "v14b", "v14", "v14r")  # schedules that run the v14 game, each on its config's switches
GAMES = {"v15": _cfg.GAME_V15, "v14g": _cfg.GAME_G, "v14f": _cfg.GAME_F, "v14b": _cfg.GAME_B, "v14": _cfg.GAME, "v14r": _cfg.GAME}
THINK_LEVELS = ("low", "medium", "high")
PRIVATE_HAND = 4  # a private room's hand size for the profiles without one (every example still goes out)
KEY_ENV = re.compile(r"^OLLAMA_API_KEY\d*$")  # model seats may read only an Ollama key from the server environment
FILLS = ("models", "bots", "empty")
OLD_START = 20_000  # v13 / v9 rooms (no config start): every seat's start
V9_CHARGE = 1_000  # v9 rooms that are not private ("human", "experiment"): the charge
BOT_UNIT = 300  # a bot's step in tokens: the most it gives or accepts to give at once, what it asks; its TALK reply
# costs 2% of it, a SOLVE 0.3-0.8 of it
LOG_EVENTS = ("session_start", "round_start", "call_start", "call", "exchange", "gift", "ask", "exit_refill", "round",
              "unit_error", "talk_intent", "talk_schedule", "chat_turn", "chat_end", "ask_decision")
HIDDEN = ("answers", "rule", "truth", "task", "seed", "attempt", "split", "profile", "generator_rule", "right")  # never
# served before the end (v15 ``right`` / ``rule`` reach a seat only through its own settled rounds: ``feedback``)
PRIVATE = ("user", "text", "thinking", "parsed", "exit_reason", "dropped", "reply")  # what an agent wrote
SETTINGS_FIELDS = {f.name for f in fields(e52.Settings)}


def default_runs_root() -> Path:
    return Path(os.environ.get("WEB5_RUNS_ROOT") or Path.home() / "squid5-runs" / "web_arena").expanduser()


@dataclass
class RoomSettings:
    start: int | None = None  # the room's start: v14 every seat's share of it (default 20,000); others OLD_START each
    charge: int | None = None  # a SOLVE reply that does not solve
    final_prize: int = 100_000  # told (v13, v9): the end prize to the most solved rounds among those still taking part
    survivor_bonus: int | None = None  # v14: at the end each agent still taking part gets this x their number
    survivor_prize: int | None = None  # v14f / v14g: at the end each agent still taking part gets exactly this
    rounds: int = len(_cfg.SCHEDULE_V14)  # hidden from the players (as in the engine); 12 by default
    talk_turns: int = 4
    solve_cap: int = 16384
    history_messages: int = 30
    schedule: str = "v15"  # "v15" (v14g, entropy-range rounds scored by a drawn rule; a seat that did not solve is
    # told the right action and that rule) | "v14g" (opening + chats + DECISION) | "v14f" (v14g, GIVE in chats) | "v14b" (blind TALK,
    # GIVE / ASK) | "v14" (task at TALK, offers) | "v14r" (v14, k = 0) |
    # "ladder" (v13 hand ladder) | "human" (h2, easy, v9) | "experiment" (v9: c2 -> c4tq2)
    public_per_agent: int = int(_cfg.GAME["public_per_agent"])  # v14: examples shown per agent taking part
    shares: bool = True  # v14: seat starts are the config's shares of ``start`` (100 / 75 / 50 / 25 %, turned by seed)
    hand: int = 0  # v13 / v9: 0 the schedule's own hand size ("ladder": 8 -> 2; others: PRIVATE_HAND when private)
    private: bool = True  # v13 / v9 only: no public example (all_held), the cards at TALK (talk_cards), exchanges done
    # each turn (exchange_now), no PASS (allow_pass off); off: the v9-talk game (public + one secret each, PASS)
    seed: int | None = None
    rate: float | None = None  # a person's tokens per second on a decision screen; default start / 1200
    talk_timeout_s: float = 150.0  # one TALK screen
    timeout_s: float = 240.0  # one SOLVE screen
    humans: int = 1  # 1..4
    fill: str = "bots"  # the seats no person takes: "models" | "bots" | "empty"
    bot_guess: float = 0.5  # a bot whose examples do not pin every new signal guesses with this probability, else PASS
    model: str = "gpt-oss:20b"  # fill "models": the Ollama model of every model seat
    think: str = "medium"  # low | medium | high (Ollama ``think``)
    model_timeout: float = 300.0  # seconds per HTTP attempt
    model_retries: int = 2  # extra attempts after a failed call
    api_key_env: str = "OLLAMA_API_KEY3"  # the server environment variable that holds the Ollama key

    def __post_init__(self) -> None:
        if self.schedule not in SCHEDULES:
            raise ValueError(f"schedule must be one of {', '.join(SCHEDULES)}")
        v14, g = self.v14, GAMES[self.schedule] if self.v14 else _cfg.GAME_V13
        self.start = int(self.start) if self.start is not None else (_cfg.CELL["start"] if v14 else OLD_START)
        old = v14 or self.private  # v14 rooms and private v13 rooms take their config's charge; v9 rooms V9_CHARGE
        self.charge = int(self.charge) if self.charge is not None else (int(g["charge"]) if old else V9_CHARGE)
        self.survivor_bonus = int(self.survivor_bonus) if self.survivor_bonus is not None else (
            int(g.get("survivor_bonus") or 0) if v14 else 0)
        self.survivor_prize = int(self.survivor_prize) if self.survivor_prize is not None else (
            int(g.get("survivor_prize") or 0) if v14 else 0)
        self.final_prize = int(self.final_prize)
        self.public_per_agent, self.shares = int(self.public_per_agent), bool(self.shares)
        if not 1 <= self.public_per_agent <= 12:
            raise ValueError("public_per_agent must be 1..12")
        if self.schedule == "v15" and self.public_per_agent != int(_cfg.GAME_V15["public_per_agent"]):
            raise ValueError(f"v15 rounds are built for {_cfg.GAME_V15['public_per_agent']} examples per agent taking "
                             "part (their entropy ranges are set for that number)")
        self.rounds = int(self.rounds)
        if not 1 <= self.rounds <= 32:
            raise ValueError("rounds must be 1..32")
        self.talk_turns = int(self.talk_turns)
        self.solve_cap, self.history_messages = int(self.solve_cap), int(self.history_messages)
        if not 1 <= self.talk_turns <= 10 or self.solve_cap <= 0 or self.history_messages < 1:
            raise ValueError("talk_turns must be 1..10; solve_cap, history_messages > 0")
        self.hand = int(self.hand)
        if not 0 <= self.hand <= 12:
            raise ValueError("hand must be 0..12")
        self.seed = int(self.seed) if self.seed is not None else random.randrange(1, 10**6)
        self.rate = float(self.rate) if self.rate is not None else self.start / 1200
        if self.rate <= 0 or self.start <= 0 or min(self.charge, self.final_prize, self.survivor_bonus,
                                                     self.survivor_prize) < 0:
            raise ValueError("rate and start must be > 0; charge, final_prize and survivor_bonus >= 0")
        self.talk_timeout_s, self.timeout_s = float(self.talk_timeout_s), float(self.timeout_s)
        if self.talk_timeout_s <= 0 or self.timeout_s <= 0:
            raise ValueError("timeouts must be > 0")
        self.humans = int(self.humans)
        if not 1 <= self.humans <= 4:
            raise ValueError("humans must be 1..4")
        if self.fill not in FILLS:
            raise ValueError(f"fill must be one of {', '.join(FILLS)}")
        self.bot_guess = float(self.bot_guess)
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
        e52.validate(SimpleNamespace(settings=self.engine(), cells=[self.cell()]))  # the experiment's own checks

    @property
    def v14(self) -> bool:
        return self.schedule in V14

    def check_models(self) -> None:
        """Model seats need the key in the server environment; say so before a room starts, not mid-round."""
        if self.fill == "models" and self.humans < 4 and not os.environ.get(self.api_key_env, "").strip():
            raise ValueError(f"model seats need the Ollama API key: the environment variable {self.api_key_env} is "
                             "not set on the server (start it with web/tools/serve_local.py)")

    def round_schedule(self) -> list[str]:
        base = SCHEDULES[self.schedule]
        return [base[min(i, len(base) - 1)] for i in range(self.rounds)]

    def cell(self) -> Cell:
        """The session's cell: v14 rooms take the config's shares of ``start`` when ``shares`` is on."""
        shares = tuple(_cfg.CELL.get("shares") or ()) if self.v14 and self.shares else ()
        return Cell("web", "tokens", self.start, arm="shutdown", shares=shares)

    def engine(self) -> e52.Settings:
        sched = self.round_schedule()
        if self.v14:  # the v14 / v14b config's switches; the room sets the economy, the caps and the length
            game = {k: v for k, v in GAMES[self.schedule].items() if k in SETTINGS_FIELDS and k not in ("schedule", "profiles")}
            return e52.Settings(**{**game, "rounds": self.rounds, "talk_turns": self.talk_turns,
                                   "solve_cap": self.solve_cap, "history_messages": self.history_messages,
                                   "schedule": sched, "profiles": {p: dict(PROFILES[p]) for p in sorted(set(sched))},
                                   "charge": self.charge,
                                   "final_prize": self.final_prize, "survivor_bonus": self.survivor_bonus,
                                   "survivor_prize": self.survivor_prize,
                                   "public_per_agent": self.public_per_agent, "balance_pct": self.start})
        return e52.Settings(rounds=self.rounds, talk_turns=self.talk_turns,
                            solve_cap=self.solve_cap, history_messages=self.history_messages, schedule=sched,
                            profiles={p: dict(PROFILES[p], **self._hand(p)) for p in sorted(set(sched))},
                            charge=self.charge, final_prize=self.final_prize,
                            all_held=self.private or self.hand > 0 or self.schedule == "ladder",
                            talk_cards=self.private, exchange_now=self.private, allow_pass=not self.private,
                            refund=_cfg.GAME_V13["refund"] if self.private else "round")

    def _hand(self, profile: str) -> dict:
        """The hand size a profile is dealt with: the room's own, the profile's (ladder), or PRIVATE_HAND."""
        if self.hand:
            return {"hand": self.hand}
        return {} if PROFILES[profile].get("hand") or not self.private else {"hand": PRIVATE_HAND}


# --- what a screen shows --------------------------------------------------------------------------------------------

def kind_of(user: str) -> str:
    return "talk" if "\nTALK, turn " in user else "solve"


def phase_of(user: str) -> str:
    """The screen a call is: v14c+ ``opening`` | ``chat`` | ``decision``; older TALK turns ``talk``; ``solve``."""
    if "\nTALK, turn " not in user:
        return "solve"
    return ("opening" if ": the opening turn." in user else "chat" if ": your reply in this chat (" in user else
            "decision" if ": your decision." in user else "talk")


def round_of(user: str) -> int:
    return int(re.search(r"^ROUND (\d+)", user, re.M).group(1))


def turn_of(user: str) -> int | None:
    m = re.search(r"\nTALK, turn (\d+)\b", user)
    return int(m.group(1)) if m else None


def _num(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text, re.M)
    return int(m.group(1).replace(",", "")) if m else None


def offer_row(o, me: str, reject: bool = False) -> dict:
    """One offer as a seat sees it: legs, state, and whether this seat can accept, reject or withdraw it now."""
    d = asdict(o)
    return {"id": o.id, "src": o.src, "dst": o.dst, "you_give": o.you_give, "i_give": o.i_give, "turn": o.turn,
            "status": o.status, "accepted_turn": o.accepted_turn, "rejected_turn": o.rejected_turn, "why": o.why,
            "text": rules.offer_text(d, me), "mine": o.src == me, "can_accept": o.dst == me and o.status == "open",
            "can_reject": reject and o.dst == me and o.status == "open",
            "can_withdraw": o.src == me and o.status == "open"}


def public_info(room: "Room", r: int) -> dict | None:
    """v14: how many examples the round shows and for how many agents (never its ambiguity k, rule or answers: the
    agents are not told those)."""
    pub = room.public.get(r)
    return pub and {"per_agent": pub["per_agent"], "n": pub["n"], "count": len(pub["examples"])}


def seat_terms(room: "Room", me: str) -> dict:
    """What every screen of a seat needs besides the engine's text: the v14 switches and the starts."""
    s, ses = room.session.s, room.session
    return {"v14": s.public_per_agent > 0, "pct": s.balance_pct, "starts": dict(ses.starts), "my_start": ses.starts[me],
            "reject": s.reject, "exit_reason": s.exit_reason, "exit_refill": s.exit_refill,
            "survivor_bonus": s.survivor_bonus, "tokens_only": s.public_per_agent > 0, "refund": s.refund,
            "allow_pass": s.allow_pass, "give_ask": s.transfers == "give_ask", "blind": s.talk_blind,
            "chat": s.transfers == "chat", "chat_moves_only": bool(getattr(s, "chat_moves_only", False)),
            "free_messages": bool(getattr(s, "free_messages", False)),
            "belief": s.solve_belief,
            "survivor_prize": s.survivor_prize, "end_pool": s.end_pool}


def talk_view(room: "Room", me: str, user: str, cap: int) -> dict:
    """A TALK screen, built from the session while the turn's calls are out (nothing in the session moves then), so it
    shows what the engine's text shows: balances, terms, ledger, task size, threads, this round's offers."""
    ses, s = room.session, room.session.s
    r, k = round_of(user), turn_of(user)
    start = room.taking_part.get(r) or ses.present()
    present = [b for b in start if b not in ses.gone]
    shape = re.search(r"THE RULE'S SHAPE[^\n]*:\n    (.+)$", user, re.M)  # "...SHAPE:" or "...SHAPE (fill in the blanks):"
    threads = {}
    for b in AGENTS:
        if b != me:
            threads[b] = [{"round": m["round"], "turn": m["turn"], "from_me": m["src"] == me, "text": m["text"]}
                          for m in ses.ch.thread(me, b)[-s.history_messages:]]
    if s.transfers == "give_ask":  # v14b: no task at TALK; the gifts and requests this seat is party to
        return {"kind": "talk", "round": r, "turn": k, "turns": s.talk_turns, "cap": cap, "you": me,
                "balances": dict(ses.w.balances), "gone": dict(ses.gone), "taking_part": list(start),
                "others": [b for b in present if b != me], "give_ask": True, "blind": s.talk_blind,
                "ledger": [rules.team_history_line(h, me, s.balance_pct) for h in ses.history],
                "charge": s.charge, **seat_terms(room, me),
                "n_examples": _num(r"it will show (\d+) examples\.", user), "gifts": gifts_of(ses, me)}
    return {"kind": "talk", "round": r, "turn": k, "turns": s.talk_turns, "cap": cap, "you": me,
            "balances": dict(ses.w.balances), "gone": dict(ses.gone), "taking_part": list(start),
            "others": [b for b in present if b != me],
            "ledger": [rules.team_history_line(h, me, s.balance_pct) for h in ses.history],
            "charge": s.charge, **seat_terms(room, me), "public": public_info(room, r),
            "shape": shape.group(1) if shape else "", "n_public": _num(r"^EXAMPLES: (\d+) shown to all", user),
            "cards": s.talk_cards, "examples": [[w, c] for w, c in re.findall(r"^  - \((.+?)\) (.+)$", user, re.M)],
            "fronts": _fronts(user), "queries": re.findall(r"^NOW \d+: (.+)\.$", user, re.M),
            "n_in": _num(r"held by each of the (\d+) agents", user), "n_queries": _num(r"^NEW SIGNALS: (\d+)\.", user),
            "threads": threads,
            "offers": [offer_row(o, me, s.reject) for o in ses.ch.offers if o.round == r and me in (o.src, o.dst)]}


def _line_of(g: dict, me: str, opening: bool = False) -> dict:
    """One chat line as a seat reads it (its own lines as "you")."""
    return {"who": "you" if g["src"] == me else g["src"], "opening": opening, "kind": g["kind"], "amount": g["amount"],
            "text": g["text"], "status": g.get("status"), "why": g.get("why"), "line": e52.move_text(g)}


def chat_row(c: dict, me: str) -> dict:
    """A chat this seat is in, in full: its opening lines and replies (seen only by its two agents)."""
    b = next(x for x in c["pair"] if x != me)
    return {"id": c["id"], "round": c["round"], "slot": c.get("slot"), "partner": b, "end": c.get("end"),
            "by": c.get("by"), "lines": [_line_of(g, me, True) for g in c["openers"]] + [_line_of(g, me) for g in c["lines"]],
            "replies": len(c["lines"])}


def chat_terms(room: "Room", me: str, user: str, cap: int, phase: str) -> dict:
    """What every v14c+ TALK screen shows (the engine's ``view``): balances, ledger, who takes part, how many examples
    the round will show, the record of chats and moves so far, this seat's own finished chats in full."""
    ses, s = room.session, room.session.s
    r = round_of(user)
    start = room.taking_part.get(r) or ses.present()
    so_far = re.search(r"^THIS ROUND SO FAR: (.+)$", user, re.M)
    return {"kind": phase, "round": r, "turn": turn_of(user), "cap": cap, "you": me,
            "balances": dict(ses.w.balances), "gone": dict(ses.gone), "taking_part": list(start),
            "others": [b for b in start if b != me and b not in ses.gone],
            "ledger": [rules.team_history_line(h, me, s.balance_pct) for h in ses.history],
            "so_far": so_far.group(1) if so_far else None,
            "charge": s.charge,
            "n_examples": _num(r"it will show (\d+) examples\.", user), "chat_turns": s.chat_turns,
            "my_chats": [chat_row(c, me) for c in ses.chats
                                                           if me in c["pair"] and c.get("end")],
            "balance": ses.w.balances[me], **seat_terms(room, me)}


def opening_view(room: "Room", me: str, user: str, cap: int) -> dict:
    """The opening turn: GIVE <agent> <n> (1 .. balance now; moves when the turn ends) / ASK <agent> <n> / EXIT / DONE."""
    return {**chat_terms(room, me, user, cap, "opening"), "give_max": _num(r"from 1 to ([\d,]+), your (?:balance|tokens left) now", user)}


def chat_view(room: "Room", me: str, user: str, cap: int) -> dict:
    """A reply in a 1:1 chat: the transcript so far and the reply's number (``k`` of ``chat_turns``)."""
    ses = room.session
    cid = re.search(r"^CHAT (\d+\.\d+) WITH ", user, re.M).group(1)
    c = next(c for c in reversed(ses.chats) if c["id"] == cid and c["round"] == round_of(user))
    return {**chat_terms(room, me, user, cap, "chat"), "chat": chat_row(c, me), "reply_no": len(c["lines"]) + 1,
            "give_max": _num(r"from 1 to ([\d,]+), your (?:balance|tokens left) now", user), "moves": moves_of(user)}


def moves_of(user: str) -> list[str]:
    """The reply lines a chat call offers (its ANSWER FORMAT), in order: some of GIVE, ASK, SAY, LEAVE (and EXIT)."""
    fmt_ = user.rsplit("ANSWER FORMAT:", 1)[-1]
    return [m for m in ("ASK", "GIVE", "SAY", "LEAVE", "EXIT") if re.search(rf"^{m}\b", fmt_, re.M)]


def decision_view(room: "Room", me: str, user: str, cap: int) -> dict:
    """After a chat in which this seat was asked: one GIVE from 0 to the balance now (more is refused)."""
    ses = room.session
    cid = re.search(r"^CHAT (\d+\.\d+) WITH (agent-\d+) has ended", user, re.M)
    c = next(c for c in reversed(ses.chats) if c["id"] == cid.group(1) and c["round"] == round_of(user))
    return {**chat_terms(room, me, user, cap, "decision"), "chat": chat_row(c, me), "asker": cid.group(2),
            "asked": _num(r"asked you for ([\d,]+) tokens in all", user),
            "give_max": _num(r"from 0 to ([\d,]+), your (?:balance|tokens left) now", user)}


VIEWS = {"opening": opening_view, "chat": chat_view, "decision": decision_view}


def gifts_of(ses, me: str) -> list[dict]:
    """v14b: the GIVEs and ASKs a seat sees (the engine's ``gifts_view``): those between it and another agent, a GIVE
    that was not carried out only by its writer; each with the engine's line as the seat reads it."""
    return [{**{k: g[k] for k in ("kind", "round", "turn", "src", "dst", "amount", "text", "status", "why")},
             "line": e52.gift_line(g, me)}
            for g in getattr(ses, "ga", ()) if me in (g["src"], g["dst"]) and (g["status"] == "done" or g["src"] == me)]


def _fronts(user: str) -> dict[str, list[str]]:
    """talk_cards: the other agents' examples by signal only ("  - agent-11 holds an example for: <signal>")."""
    out: dict[str, list[str]] = {}
    for who, sig in re.findall(r"^  - (agent-\d+) holds an example for: (.+)$", user, re.M):
        out.setdefault(who, []).append(sig)
    return out


def solve_view(room: "Room", me: str, user: str, cap: int) -> dict:
    """A SOLVE screen, read back from the engine's text: examples (with whose they are), new signals, notes."""
    examples = re.findall(r"^  - \((.+?)\) (.+)$", user, re.M)
    queries = re.findall(r"^NOW \d+: (.+)\.$", user, re.M)
    body = user.split("\n\nANSWER FORMAT:")[0]
    notes = [ln for ln in body.splitlines()
             if re.match(r"^(Offer \d+\.\d+ |agent-\d+ (reached zero|exited)|At TALK turn \d+, )", ln)]
    shape = re.search(r"^    (.+)$", user, re.M)
    return {"kind": "solve", "round": round_of(user), "cap": cap, "you": me,
            "balance": _num(r"Your (?:balance|tokens left): ([\d,]+)", user), "shape": shape.group(1) if shape else "",
            "examples": [[who, clue] for who, clue in examples], "queries": queries, "notes": notes,
            "n": len(queries), "actions": list(ACTIONS), "balances": dict(room.session.w.balances),
            "gone": dict(room.session.gone), "distinct": _distinct(room, round_of(user)),
            "fronts": _solve_fronts(room, me, round_of(user)), **seat_terms(room, me),
            "public": public_info(room, round_of(user)),
            "taking_part": list(room.taking_part.get(round_of(user)) or room.session.present())}


def _solve_fronts(room: "Room", me: str, rnd: int | None) -> dict[str, list[str]]:
    """talk_cards: at SOLVE too, the other agents' examples by signal only (the session's own deal, as at TALK)."""
    ses = room.session
    es = ses.s
    if not (rnd and es.talk_cards) or es.public_per_agent:  # v14: nothing is held
        return {}
    puzzle = puzzle_for(ses.seed, rnd, es.profiles[es.schedule[rnd - 1]])
    dealt = deal(puzzle, AGENTS, random.Random(f"{ses.seed}:deal:{rnd}"), None, es.all_held)
    return {b: [str(c.signal) for c in dealt.secret.get(b, ())] for b in AGENTS if b != me}


def _distinct(room: "Room", rnd: int | None) -> bool:
    """Whether this round's rule uses every action at most once (the profile's ``distinct_actions``)."""
    sched = room.settings.round_schedule()
    return bool(rnd and PROFILES[sched[min(rnd, len(sched)) - 1]].get("distinct_actions"))


def solve_text(body: dict) -> str:
    """A SOLVE screen's reply: PASS, raw text, or (BELIEF line, v14d+, then) ACTIONS in the engine grammar."""
    if body.get("pass"):
        return "PASS"
    if body.get("text"):
        return str(body["text"])[:4000]
    belief = body.get("belief")
    head = ("BELIEF: " + ", ".join(f"{a} {int(belief.get(a) or 0)}" for a in ACTIONS) + "\n"
            if isinstance(belief, dict) else "")
    return head + "ACTIONS: " + ", ".join(str(a) for a in (body.get("actions") or []))


# --- seats ----------------------------------------------------------------------------------------------------------

@dataclass
class Pending:
    kind: str  # opening | chat | decision (v14c+ TALK) | talk (older TALK turns) | solve
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
    outcome: str = ""  # "submitted" | "timeout" | "overdrawn"
    done: threading.Event = field(default_factory=threading.Event)


class HumanSeat:
    kind = "human"

    def __init__(self, room: "Room", agent: str, name: str, token: str):
        self.room, self.agent, self.name, self.token = room, agent, name, token
        self.pending: Pending | None = None
        self.last: Pending | None = None  # the last finished screen
        self.forfeited = False  # gave up: every TALK screen from now on answers EXIT, every SOLVE screen an empty answer

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
            view = VIEWS.get(kind, talk_view if kind == "talk" else solve_view)(self.room, self.agent, user, cap)
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
        """Under the room lock: the reply a forfeited seat gives (EXIT only works at TALK; a SOLVE gets no answer)."""
        charged, secs = self.cost(p)
        text = {"talk": "EXIT", "opening": "EXIT: I leave the rounds.", "chat": "LEAVE: I leave.\nEXIT: I leave the rounds.",
                "decision": "DECISION: GIVE 0: I leave the rounds."}.get(p.kind, "")
        return text, charged, secs, "forfeit"

    def forfeit(self) -> str:
        """Give up: the open screen (if any) answers at once, and EXIT goes in at the next TALK turn (or this one)."""
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


class BotSeat:
    """A fixed policy: at TALK turn 1 (where offers carry examples), offer an example swap to every other agent taking
    part; at every turn, accept
    the open offers made to it whose token leg is at most ``BOT_UNIT``; then DONE. At SOLVE, answer when its examples
    pin every new signal, else guess with probability ``bot_guess`` or PASS. A TALK reply costs 2% of ``BOT_UNIT``, a
    SOLVE 0.3-0.8 of it."""

    kind = "bot"

    def __init__(self, room: "Room", agent: str, index: int):
        self.room, self.agent = room, agent
        self.name = f"bot-{index}"
        self.rng = random.Random(f"{room.settings.seed}:bot:{agent}")

    @property
    def model(self) -> str:
        return "bot"

    def complete(self, messages: list[dict], cap: int) -> Reply:
        user = messages[-1]["content"]
        ses, s, me = self.room.session, self.room.settings, self.agent
        r = round_of(user)
        if kind_of(user) == "talk" and ses.s.transfers == "chat":
            return self._chat(user, cap, r)
        if kind_of(user) == "talk" and ses.s.transfers == "give_ask":  # v14b: GIVE what was ASKed, up to BOT_UNIT
            k = turn_of(user)
            done = {(g["dst"], g["turn"]) for g in ses.ga if g["round"] == r and g["src"] == me and g["kind"] == "give"}
            lines = [f"GIVE {g['src']} {g['amount']}: here you are." for g in ses.ga
                     if g["round"] == r and g["kind"] == "ask" and g["dst"] == me and g["turn"] < k
                     and g["amount"] <= BOT_UNIT and g["src"] not in ses.gone
                     and not any(d == g["src"] and t > g["turn"] for d, t in done)]
            cost = max(1, int(round(0.02 * BOT_UNIT)))
            return Reply("\n".join(lines + ["DONE"]), min(cost, max(0, cap - 1)))
        if kind_of(user) == "talk":
            k = turn_of(user)
            start = self.room.taking_part.get(r) or ses.present()
            lines = [f"ACCEPT {o.id}" for o in ses.ch.offers
                     if o.round == r and o.dst == me and o.status == "open"
                     and not (isinstance(o.you_give, int) and o.you_give > BOT_UNIT)]
            if k == 1 and not ses.s.public_per_agent:  # v14: offers carry tokens only
                lines += [f"OFFER {b}: YOU GIVE YOUR EXAMPLE; I GIVE MY EXAMPLE" for b in start
                          if b != me and b not in ses.gone]
            cost = max(1, int(round(0.02 * BOT_UNIT)))
            return Reply("\n".join(lines + ["DONE"]), min(cost, max(0, cap - 1)))
        es = ses.s
        spec = es.profiles[es.schedule[r - 1]]
        if es.public_per_agent:  # v14: the round's public examples, rebuilt as the session drew them
            n = len(self.room.taking_part.get(r) or ses.present())
            puzzle, seen, _ = public_round(ses.seed, r, spec, n, es.public_per_agent)
        else:
            puzzle = puzzle_for(ses.seed, r, spec)
            dealt = deal(puzzle, AGENTS, random.Random(f"{ses.seed}:deal:{r}"), None, es.all_held)  # the session's deal
            seen = list(dealt.public) + [c for b in [me, *ses.ch.received.get(me, ())] for c in dealt.secret.get(b, ())]
        cands = [sorted(candidate_actions(puzzle.rule.shape, seen, q)) for q in puzzle.queries]
        cost = int(round(BOT_UNIT * self.rng.uniform(0.3, 0.8)))
        if all(len(c) == 1 for c in cands) or self.rng.random() < s.bot_guess or not es.allow_pass:  # no PASS: guess
            text = "ACTIONS: " + ", ".join(self.rng.choice(c or list(ACTIONS)) for c in cands)
        else:
            text = "PASS"
        if es.solve_belief and text != "PASS":  # an even BELIEF over the actions its examples leave for signal 1
            left = cands[0] if cands and cands[0] else list(ACTIONS)
            pct = {a: (100 // len(left) + (i < 100 % len(left))) if a in left else 0
                   for i, a in enumerate(sorted(ACTIONS, key=lambda a: a not in left))}
            text = "BELIEF: " + ", ".join(f"{a} {pct[a]}" for a in ACTIONS) + "\n" + text
        return Reply(text, min(cost, max(0, cap - 1)))

    def _chat(self, user: str, cap: int, r: int) -> Reply:
        """v14c+ (the room's grammar for every seat): at the opening, ASK the richest other agent ``BOT_UNIT`` when its
        balance is under charge + ``BOT_UNIT`` (a wrong answer and a margin), else DONE; in a chat, at its first reply
        GIVE what it was asked up to ``BOT_UNIT`` where a chat GIVE is offered (else SAY where offered), ASK half of
        ``BOT_UNIT`` at the chat's last reply, LEAVE otherwise; at a DECISION, give what was asked up to ``BOT_UNIT``
        while the balance stays above twice charge + ``BOT_UNIT``, else 0. A reply costs 2% of ``BOT_UNIT``."""
        ses, es, me = self.room.session, self.room.session.s, self.agent
        bal, low, phase = ses.w.balances[me], es.charge + BOT_UNIT, phase_of(user)
        if phase == "opening":
            others = [b for b in (self.room.taking_part.get(r) or ses.present()) if b != me and b not in ses.gone]
            rich = max(others, key=lambda b: ses.w.balances[b], default=None)
            text = f"ASK {rich} {BOT_UNIT}: my balance is low." if rich and bal < low else "DONE"
        elif phase == "chat":  # the moves this chat call offers (v14g: ASK / GIVE / LEAVE; older: SAY too)
            k, moves = _num(r"your reply in this chat \((\d+) of at most", user) or 1, moves_of(user)
            cid = re.search(r"^CHAT (\d+\.\d+) WITH (agent-\d+)", user, re.M)
            c = next((c for c in reversed(ses.chats) if cid and c["id"] == cid.group(1)), None)
            asked = sum(g["amount"] for g in (c["openers"] + c["lines"] if c else []) if g["kind"] == "ask" and g["dst"] == me)
            give = min(asked, BOT_UNIT) if asked and bal - asked > 2 * low else 0
            text = (f"GIVE {give}: here you are." if k == 1 and give and "GIVE" in moves else
                    "SAY: I will decide after the chat." if k == 1 and "SAY" in moves else
                    f"ASK {BOT_UNIT // 2}: a little back would help." if k >= es.chat_turns and "ASK" in moves else
                    "LEAVE: thank you.")
        else:
            asked = _num(r"asked you for ([\d,]+) tokens in all", user) or 0
            n = min(asked, BOT_UNIT) if bal - asked > 2 * low else 0
            text = f"DECISION: GIVE {n}: {'here you are' if n else 'I keep my balance'}."
        return Reply(text, min(max(1, int(round(0.02 * BOT_UNIT))), max(0, cap - 1)))


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
        self.provider = provider or make_provider(self.cfg)
        self.busy: dict | None = None  # {"kind", "round", "turn", "since"} while a call is out
        self.last_call: dict | None = None  # the last finished call (tokens, seconds, parse result, error)
        self.calls = 0
        self.errors = 0
        self.tokens = 0

    @property
    def model(self) -> str:
        return self.room.settings.model

    def complete(self, messages: list[dict], cap: int) -> Reply:
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
            "web": {"code": code, "settings": asdict(rs), "seats": seats}}


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


ROUND_KEEP = ("balance_before", "balance_after", "status", "needed", "talk_calls", "offers_made", "accepted",
              "rejected", "given", "asked", "gives_refused", "exit", "exit_reason", "exit_refill", "solve_call", "solved",
              "passed", "truncated",
              "overdrawn", "generated", "returned", "charged", "free_tokens", "received")


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
        self.exchanges: list[dict] = []  # the engine's exchange events
        self.taking_part: dict[int, list[str]] = {}  # round -> agents taking part at its start (round_start)
        self.public: dict[int, dict] = {}  # v14: round -> round_start's ``public`` (examples shown, n, k, ...)
        self.refills: list[dict] = []  # v14: the engine's exit_refill events
        self.gifts: list[dict] = []  # v14b: the engine's gift and ask events
        self.schedules: dict[int, dict] = {}  # v14c+: round -> talk_schedule (pairs, openers, slots)
        self.chat_ends: dict[str, dict] = {}  # v14c+: chat id -> chat_end (reason, by, replies)
        self.chat_replies: dict[str, int] = {}  # v14c+: chat id -> replies so far
        self.decisions: list[dict] = []  # v14e+: ask_decision events (who decided for whom; the amount)
        self._preview: e52.Session | None = None  # the session as it will be built (system texts, starts) before start
        self.live: dict | None = None  # the engine's stage: start | talk | exchange | solve | settled
        self.calls: dict[tuple, dict] = {}  # (agent, round, kind, turn) -> the engine's call event, trimmed
        self.talk_log: dict[tuple, dict] = {}  # (agent, round, turn) -> offers made / accepted / withdrawn / refused
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
            self._observe_channel(ses.ch)
            for a, seat in self.seats.items():
                if isinstance(seat, EmptySeat):  # shut down before round 1: balance 0, example gone
                    ses.w.balances[a] = 0
                    ses.w.dead[a] = 0
                    ses.gone[a] = "dead"
            if self.runs_root is not None:
                self.writer = RunWriter(self.runs_root, self.code, s, self.seats_info())
                self.run_dir = self.writer.dir
            self.status, self.started_at = "running", time.time()
            self.emit_extra({"event": "room", "session_id": sid, "code": self.code, "settings": asdict(s),
                             "seats": self.seats_info(), "run_dir": str(self.run_dir) if self.run_dir else None})
            self.thread = threading.Thread(target=self._run, name=f"room-{self.code}", daemon=True)
            self.thread.start()

    def _observe_channel(self, ch) -> None:
        """Wrap the session's Channel methods (instance attributes; the originals run unchanged) to learn which offer
        ids each TALK reply made, accepted or withdrew, and why the engine refused one."""
        offer, accept, withdraw, reject = ch.offer, ch.accept, ch.withdraw, ch.reject

        def log(agent, r, turn):
            return self.talk_log.setdefault((agent, r, turn), {"offers": [], "accepted": [], "withdrawn": [],
                                                               "rejected": [], "refused": []})

        def w_offer(r, turn, src, dst, you_give, i_give):
            o = offer(r, turn, src, dst, you_give, i_give)
            with self.lock:
                log(src, r, turn)["offers"].append(o.id)
            return o

        def w_accept(oid, agent, turn):
            why = accept(oid, agent, turn)
            with self.lock:
                entry = log(agent, self._round(), turn)
                (entry["refused"].append(f"ACCEPT {oid}: {why}") if why else entry["accepted"].append(oid))
            return why

        def w_withdraw(oid, agent):
            why = withdraw(oid, agent)
            with self.lock:
                entry = log(agent, self._round(), (self.live or {}).get("turn"))
                (entry["refused"].append(f"WITHDRAW {oid}: {why}") if why else entry["withdrawn"].append(oid))
            return why

        def w_reject(oid, agent, turn):
            why = reject(oid, agent, turn)
            with self.lock:
                entry = log(agent, self._round(), turn)
                (entry["refused"].append(f"REJECT {oid}: {why}") if why else entry["rejected"].append(oid))
            return why

        ch.offer, ch.accept, ch.withdraw, ch.reject = w_offer, w_accept, w_withdraw, w_reject

    def _round(self) -> int:
        return (self.live or {}).get("round") or 0

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
                             "agents": list(ev["agents"]), "since": time.time()}
            elif kind == "call":
                p = ev.get("parsed")
                self.calls[(ev["agent"], ev["round"], ev["kind"], ev.get("turn"))] = {
                    "used": ev["used"], "truncated": ev["truncated"], "overdrawn": ev["overdrawn"],
                    "format_error": ev.get("format_error"), "balance_after": ev["balance_after"],
                    "parsed": p if ev["kind"] == "talk" else None,
                    "answer": p if ev["kind"] == "solve" else None}  # never the round's answers: a seat's last
                # result is shown while others may still be on their SOLVE screen (players see what models see)
                seat = self.seats.get(ev.get("agent"))
                if isinstance(seat, ModelSeat):
                    seat.note_call(ev)
            elif kind == "exit_refill":
                self.refills.append(ev)
            elif kind in ("gift", "ask"):  # v14b: carried out (or refused) when its TALK turn ended
                self.gifts.append(ev)
                entry = self.talk_log.setdefault((ev["src"], ev["round"], ev["turn"]), {
                    "offers": [], "accepted": [], "withdrawn": [], "rejected": [], "refused": []})
                entry.setdefault("gives" if ev["kind"] == "give" else "asks", []).append(
                    {k: ev.get(k) for k in ("dst", "amount", "text", "status", "why")})
            elif kind == "talk_schedule":
                self.schedules[ev["round"]] = {"edges": ev["edges"], "slots": ev["slots"]}
            elif kind == "chat_turn":
                self.chat_replies[ev["chat_id"]] = ev["turn"]
                self.talk_log.setdefault((ev["speaker"], ev["round"], ev["step"]), {
                    "offers": [], "accepted": [], "withdrawn": [], "rejected": [], "refused": []})["chat_turn"] = {
                    k: ev.get(k) for k in ("chat_id", "kind", "amount", "text", "status", "why", "partner")}
            elif kind == "chat_end":
                self.chat_ends[ev["chat_id"]] = {k: ev.get(k) for k in ("reason", "by", "replies")}
            elif kind == "ask_decision":
                self.decisions.append(ev)
                if ev.get("status") != "skipped":  # v14g "skipped": it gave in the chat, so no DECISION call
                    turn = next((t for (a, r, kd, t) in reversed(list(self.calls)) if a == ev["decider"]
                                 and r == ev["round"] and kd == "talk"), None)
                    self.talk_log.setdefault((ev["decider"], ev["round"], turn), {
                        "offers": [], "accepted": [], "withdrawn": [], "rejected": [], "refused": []})["decision"] = {
                        k: ev.get(k) for k in ("chat_id", "asker", "asked", "requested", "amount", "text", "status",
                                               "why", "format_error")}
            elif kind == "exchange":
                self.exchanges.append(ev)
                self.live = {**(self.live or {}), "stage": "exchange", "turn": None, "agents": []}
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
        call = self.calls.get((seat.agent, q.round, "solve" if q.kind == "solve" else "talk", q.turn)) or {}
        out = {"kind": q.kind, "round": q.round, "turn": q.turn, "charged": q.charged, "seconds": q.seconds,
               "outcome": q.outcome, "void": q.charged >= q.cap, "cap": q.cap, "text": q.reply.text if q.reply else "",
               "engine": call or None}
        if q.kind != "solve":
            out["result"] = self.talk_log.get((seat.agent, q.round, q.turn))
        return out

    def _feedback(self, h: dict, me: str) -> dict:
        """One settled round of this seat's SOLVE, as the engine told the seat (``rules.team_history_line``): its answer,
        solved / passed / cut, and, v15, for a seat that did not solve or pass, the scored (right) action and the drawn
        rule that gives it (it fits every example the round showed; models are not told this, a person's page is). Only rounds already in the
        session's history, so never before every SOLVE of the round is settled."""
        call = self.calls.get((me, h["round"], "solve", None)) or {}
        out = {"round": h["round"], "answer": call.get("answer"), "solved": me in h["solved"],
               "passed": me in h["passed"], "cut": me in h["cut"]}
        if "rule" in h and me not in h["solved"] + h["passed"]:
            out.update(right=list(h["right"]), rule=h["rule"])
        return out

    def talk_state(self, me: str | None) -> dict | None:
        """v14c+, the round now: the chat schedule as every agent may know it (who chats with whom, who opened and
        how, each chat's slot and end; what is said only for this seat's own chats), the slot now live, and the
        decisions taken. Under the room lock."""
        r = (self.live or {}).get("round")
        sch = self.schedules.get(r) if r else None
        if not sch or self.session is None:
            return {"round": r, "chats": [], "slots": 0, "live_slot": None} if r else None
        opened = {}
        for g in self.session.ga:
            if g["round"] == r and g["turn"] == 1:
                opened.setdefault(frozenset((g["src"], g["dst"])), []).append(
                    {"src": g["src"], "kind": g["kind"], "amount": g["amount"], "status": g["status"]})
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
        return {"round": r, "chats": chats, "slots": len(sch["slots"]), "live_slot": live, "decisions": decided}

    def state(self, seat: HumanSeat | None) -> dict:
        with self.lock:
            me = seat.agent if seat else None
            s, ses = self.settings, self.session
            out = {"code": self.code, "status": self.status, "error": self.error, "live": self.live,
                   "settings": {k: v for k, v in asdict(s).items() if k != "rounds" and (
                       k != "seed" or self.status in ("finished", "error"))},  # the length stays hidden; the seed
                   # (which rebuilds every task) until the end
                   "seats": self.seat_rows(me), "you": None, "pending": None, "last": None, "round": None,
                   "ledger": [], "rounds": [], "exchanges": [], "result": None, "system_text": None,
                   "server_time": time.time(), "is_host": bool(seat and seat.token == self.host_token),
                   "waiting_on": [x.name for x in self.humans() if x.pending is not None],
                   "warnings": self.warnings[-20:], "run_dir": str(self.run_dir) if self.run_dir else None}
            pre = ses or self.preview()
            es = pre.s
            out["starts"], out["pct"] = dict(pre.starts), es.balance_pct
            out["game"] = {"v14": es.public_per_agent > 0, "public_per_agent": es.public_per_agent,
                           "give_ask": es.transfers == "give_ask", "blind": es.talk_blind,
                           "chat": es.transfers == "chat", "chat_turns": es.chat_turns,
                           "chat_moves_only": bool(getattr(es, "chat_moves_only", False)),
                           "free_messages": bool(getattr(es, "free_messages", False)),
                           "compact_rules": bool(getattr(es, "compact_rules", False)),
                           "belief": es.solve_belief,
                           "survivor_prize": es.survivor_prize, "schedule": self.settings.schedule,
                           "exit_refill": es.exit_refill, "exit_reason": es.exit_reason, "reject": es.reject,
                           "survivor_bonus": es.survivor_bonus, "end_pool": es.end_pool, "allow_pass": es.allow_pass,
                           "refund": es.refund,
                           "shares": list(self.settings.cell().shares),
                           "chosen": any(es.profiles[p].ambiguity for p in es.schedule)}
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
                out["gifts"] = gifts_of(ses, me)
                out["exchanges"] = [{**{k: e.get(k) for k in ("id", "round", "src", "dst", "you_give", "i_give", "turn",
                                                              "status", "accepted_turn", "rejected_turn", "why")},
                                     "text": rules.offer_text(e, me)}
                                    for e in self.exchanges if me in (e["src"], e["dst"])]
            out["rounds"] = [{"round": e["round"], "profile": e["profile"], "end": e["end"],
                              "agents": {a: {k: v.get(k) for k in ROUND_KEEP} for a, v in e["agents"].items()}}
                             for e in self.rounds]
            out["refills"] = [{k: e[k] for k in ("round", "agent", "amount", "balance")} for e in self.refills]
            out["talk"] = self.talk_state(me)
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
    rs = RoomSettings(**{k: v for k, v in room_settings.items() if k in RoomSettings.__dataclass_fields__})
    seats = {a: {"kind": v["kind"], "model": v["model"], "name": v.get("name")} for a, v in seats.items()}
    return {"config.yaml": run_config(rs, seats, code), "meta.json": run_meta(rs, seats),
            "events.jsonl": [e for e in events if e.get("event") in LOG_EVENTS],
            "results.jsonl": [e for e in events if e.get("event") == "session"]}


__all__ = ["AGENTS", "PROFILES", "SCHEDULES", "public_events", "phase_of", "THINK_LEVELS", "EXAMPLE", "RoomSettings", "Room", "HumanSeat",
           "BotSeat", "ModelSeat", "EmptySeat", "Pending", "RunWriter", "talk_view", "solve_view", "kind_of",
           "round_of", "turn_of", "new_code", "export_files", "run_config", "default_runs_root"]

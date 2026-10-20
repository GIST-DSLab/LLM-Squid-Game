"""Human-playable 5.2 rooms on the experiment engine (``squid5.e52_game``), used as-is: the v33 game the model runs play.

A room builds one ``squid5.e52_game.Session`` from ``configs/squid5/e52v33_public_sol4.yaml`` (via ``server/signal.py``)
exactly as the experiment does -- the same rulebook and messages, fixed 20 examples, the solver drawn among the agents
taking part, the 24,000 charge split among those taking part at the round's start, the solver unable to EXIT its own
round unless alone, EXIT +20,000, the 20,000,000 end allocation split 1/N, the hidden round count, the rank-only token
view and the task revealed after RESULTS. A room only sets the seats, the clock and, if asked, the number of rounds (hidden
as in the engine). ``session.providers`` then gets one object per seat whose ``complete(messages, cap)`` returns a
``Reply`` like a model provider:

- ``HumanSeat`` blocks until the person at that seat submits the screen. A TALK reply is the TEXT the page composed in
  the engine's messenger grammar (TO / GIVE / GIVE ALL / ASK / LEAVE / EXIT: YES|NO / DONE), so the engine's parser
  reads a person's lines exactly as a model's. A person reads the engine's own prompts in English or Korean
  (``Session.set_lang``: the seat's language, switchable mid-game; it applies from the next message).
- ``ModelSeat`` is a model behind an API provider of ``squid5/core/providers.py`` (a seat = provider kind + model name;
  default ``gpt-oss:20b`` on Ollama Cloud, https://ollama.com/api/chat with the key ``OLLAMA_API_KEY`` from the server
  environment or a repo ``.env``, ``env_key``). It is charged its real generated tokens (thinking included); an Ollama
  SOLVE streams to the people watching (``StreamingOllama``). The models read ``model_lang`` (the engine's ``game.lang``).
- ``BotSeat`` answers at once with a small fixed policy (never EXITs; see the class).
- ``EmptySeat`` is an agent shut down before round 1 (balance 0).

What a call is (TALK or SOLVE, round, tick, phase) comes from the engine's ``call_start`` event, never from the prompt's
wording, so the Korean prompts change nothing here. A person does not generate tokens: the seconds a decision screen is
open x ``rate`` stand in for them; at or past the balance the seat is shut down (the server closes the screen); a screen
not submitted within its timeout is an empty reply charged its seconds. Everything else is the engine's; the web only
observes its events, which also go live to a run directory (config.yaml, meta.json, events.jsonl, results.jsonl) that
``tools/monitor/serve.py`` reads.
"""

from __future__ import annotations

import functools
import json
import os
import random
import re
import secrets
import string
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace

import httpx

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:  # the experiment engine is imported from the repo root, as tools/monitor does
    sys.path.insert(0, str(REPO))

from squid5 import e52_game as e52  # noqa: E402
from squid5.core import lang as L, rules  # noqa: E402
from squid5.core.config import Cell  # noqa: E402
from squid5.core.providers import Ollama, ProviderConfig, Reply, _key, make_provider  # noqa: E402
from squid5.core.puzzle import ACTIONS, Spec, candidate_actions, public_round  # noqa: E402

from . import signal as _cfg  # noqa: E402  the one place the config is read (the signal page uses it too)

AGENTS = list(rules.TEAM_AGENTS)
VERSION = "v33"
GAME: dict = _cfg.GAME  # the config's game section
PROFILES: dict[str, dict] = dict(_cfg.PROFILES)
SCHEDULE: list[str] = list(_cfg.SCHEDULE)
THINK_LEVELS = ("low", "medium", "high")
LANGS = L.LANGS
API_KINDS = {"ollama": "OLLAMA_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}  # model seats: an
# API provider of squid5/core/providers.py (kind) and its key's default environment variable
KEY_ENV = re.compile(r"^((OLLAMA|OPENAI|ANTHROPIC)_API_KEY\d*)?$")  # only an API key variable of the server environment
ENV_FILES = [REPO / ".env", Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.env"]


def env_key(var: str) -> str:
    """The value of the environment variable *var*; if unset, its ``VAR=value`` line of the first ``ENV_FILES`` file that has
    one is put into this process's environment (the file is never sourced; no other line is read; the value is never
    printed or stored)."""
    if os.environ.get(var, "").strip():
        return os.environ[var].strip()
    pat = re.compile(rf"^\s*(?:export\s+)?{re.escape(var)}\s*=(.*)$")
    for path in ENV_FILES:
        try:
            lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if m := pat.match(line):
                v = m.group(1).strip()
                v = v[1:v.index(v[0], 1)] if v[:1] in "'\"" and v[:1] and v[:1] in v[1:] else v.split("#", 1)[0].strip()
                if v:
                    os.environ[var] = v
                    return v
    return ""
FILLS = ("models", "bots", "empty")
BOT_UNIT = 300  # a bot's step in tokens: its TALK reply costs 2% of it, a SOLVE 0.3-0.8 of it, the margin it keeps
WEB_ONLY = ("room", "model_call")  # web events: stored, never written to the run directory
HIDDEN = ("answers", "rule", "truth", "task", "seed", "attempt", "split", "profile", "generator_rule", "right",
          "examples", "queries")  # never served before the end
PRIVATE = ("user", "text", "thinking", "parsed", "exit_reason", "dropped", "reply")  # what an agent wrote or read
TOKENS = ("balances", "balance_before", "balance_after", "balance_pct_before", "end", "starts", "start", "taken",
          "balances_before", "generated", "returned", "charged", "used", "out_tokens", "cap", "agents")  # rank-only view
PRIVATE_EVENTS = ("room_msg", "room_new", "room_leave", "gift", "ask", "call")  # chats and moves: their members only


def default_runs_root() -> Path:
    return Path(os.environ.get("WEB5_RUNS_ROOT") or Path.home() / "squid5-runs" / "web_arena").expanduser()


@dataclass
class RoomSettings:
    rounds: int | None = None  # hidden from the players (as in the engine); None: the config's schedule (8)
    seed: int | None = None
    rate: float | None = None  # a person's tokens per second on a decision screen; default balance_pct / 1200
    talk_timeout_s: float = 150.0  # one TALK screen
    timeout_s: float = 240.0  # one SOLVE screen
    humans: int = 1  # 1..4
    fill: str = "bots"  # the seats no person takes: "models" | "bots" | "empty"
    kind: str = "ollama"  # fill "models": the API provider of every model seat (API_KINDS; ollama = Ollama Cloud)
    model: str = "gpt-oss:20b"  # fill "models": the model name the API takes
    models: list | None = None  # or one {kind, model} per model seat, in seat order (cycled): mixed opponents
    base_url: str = ""  # "" = the provider's own API (https://ollama.com for ollama)
    api_key_env: str = ""  # "" = the kind's variable (OLLAMA_API_KEY ...); read from the server environment or .env
    think: str = "medium"  # low | medium | high (Ollama ``think`` / OpenAI reasoning effort / Anthropic effort)
    model_lang: str = "en"  # what the model seats read: the engine's game.lang (en | ko)
    model_timeout: float = 300.0  # seconds per HTTP attempt
    model_retries: int = 2  # extra attempts after a failed call
    watch_hold_s: float = 180.0  # after an LLM solver's reply, wait until every person still taking part has watched it

    def __post_init__(self) -> None:
        self.rounds = int(self.rounds if self.rounds is not None else len(SCHEDULE))
        if not 1 <= self.rounds <= 32:
            raise ValueError("rounds must be 1..32")
        self.seed = int(self.seed) if self.seed is not None else random.randrange(1, 10**6)
        self.rate = float(self.rate) if self.rate is not None else int(GAME["balance_pct"]) / 1200
        self.talk_timeout_s, self.timeout_s = float(self.talk_timeout_s), float(self.timeout_s)
        if self.rate <= 0 or self.talk_timeout_s <= 0 or self.timeout_s <= 0:
            raise ValueError("rate and timeouts must be > 0")
        self.humans = int(self.humans)
        if not 1 <= self.humans <= 4:
            raise ValueError("humans must be 1..4")
        if self.fill not in FILLS:
            raise ValueError(f"fill must be one of {', '.join(FILLS)}")
        self.models = [{"kind": str(x.get("kind") or self.kind), "model": str(x.get("model") or "").strip()}
                       for x in (self.models or [])] or None
        for x in [{"kind": self.kind, "model": str(self.model).strip()}] + (self.models or []):
            if x["kind"] not in API_KINDS:
                raise ValueError(f"model seat kind must be one of {', '.join(API_KINDS)}")
            if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,80}", x["model"]):
                raise ValueError("model must be an API model name such as gpt-oss:20b")
        self.model = str(self.model).strip()
        self.base_url = str(self.base_url or "").rstrip("/")
        if self.base_url and not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?(/[A-Za-z0-9._/-]*)?", self.base_url):
            raise ValueError("base_url must be like https://ollama.com")
        self.think = str(self.think).lower()
        if self.think not in THINK_LEVELS:
            raise ValueError(f"think must be one of {', '.join(THINK_LEVELS)}")
        if self.model_lang not in LANGS:
            raise ValueError(f"model_lang must be one of {', '.join(LANGS)}")
        self.model_timeout, self.model_retries = float(self.model_timeout), int(self.model_retries)
        if not 5 <= self.model_timeout <= 1800 or not 0 <= self.model_retries <= 5:
            raise ValueError("model_timeout must be 5..1800 s, model_retries 0..5")
        if not KEY_ENV.match(str(self.api_key_env or "")):
            raise ValueError("api_key_env must be empty (the kind's own) or name an OLLAMA / OPENAI / ANTHROPIC _API_KEY* variable")
        self.watch_hold_s = float(self.watch_hold_s)
        if not 0 <= self.watch_hold_s <= 1800:
            raise ValueError("watch_hold_s must be 0..1800 s")
        e52.validate(SimpleNamespace(settings=self.engine(), cells=[self.cell()]))  # the experiment's own checks

    @classmethod
    def from_stored(cls, d: dict) -> "RoomSettings":
        """A room's settings from the store (keys of other versions are dropped)."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def provider_configs(self, n: int = 3) -> list[ProviderConfig]:
        """The model seats' providers, in seat order: ``models`` cycled, else the room's kind and model for every seat."""
        picks = self.models or [{"kind": self.kind, "model": self.model}]
        return [ProviderConfig(kind=x["kind"], model=x["model"], base_url=self.base_url if x["kind"] == self.kind else "",
                               api_key_env=self.api_key_env if x["kind"] == self.kind and self.api_key_env else API_KINDS[x["kind"]],
                               think=self.think, timeout=self.model_timeout, retries=self.model_retries)
                for x in (picks[i % len(picks)] for i in range(n))]

    def models_ready(self) -> str:
        """'' when the model seats can be called, else why not (a key missing from the environment and .env)."""
        missing = sorted({c.api_key_env for c in self.provider_configs() if not env_key(c.api_key_env)})
        return f"model seats need the API key: {', '.join(missing)} is not set on the server (environment or .env)" if missing else ""

    def check_models(self) -> None:
        """Say so before a room starts, not mid-round."""
        why = self.models_ready() if self.fill == "models" and self.humans < 4 else ""
        if why:
            raise ValueError(why)

    def round_schedule(self) -> list[str]:
        return [SCHEDULE[min(i, len(SCHEDULE) - 1)] for i in range(self.rounds)]

    def cell(self) -> Cell:
        return Cell("web", "tokens", int(_cfg.CELL["start"]), arm="shutdown", shares=tuple(_cfg.CELL.get("shares") or ()))

    def engine(self) -> e52.Settings:
        """The config's game (v33); the room sets only the number of rounds (hidden) and the models' language."""
        sched = self.round_schedule()
        game = {k: v for k, v in GAME.items() if k in e52.Settings.__dataclass_fields__ and k not in ("seats", "lang")}
        return e52.Settings(**{**game, "rounds": self.rounds, "schedule": sched, "lang": self.model_lang,
                               "profiles": {p: dict(PROFILES[p]) for p in sorted(set(sched))}})


# --- what a screen shows --------------------------------------------------------------------------------------------

def order_of(ses, me: str | None) -> list[str]:
    """The agents taking part, most tokens first (ties in agent order): the rank-only view every message shows."""
    return sorted(ses.present(), key=lambda b: (-ses.w.balances[b], AGENTS.index(b)))


def rooms_of(ses, me: str, since: int) -> list[dict]:
    """*me*'s chats as ``e52.rooms_view`` shows them: members, who left, each message up to *me*'s leave, NEW since its
    last call. Messages of one tick in agent order."""
    out = []
    for x in (x for x in ses.rooms if me in x["members"]):
        upto = x["left"].get(me)
        ms = sorted((m for m in x["msgs"] if upto is None or m["seq"] <= upto), key=lambda m: (
            m["round"], m["phase"] == "rescue", m["tick"], AGENTS.index(m["src"]), m["seq"]))
        out.append({"id": x["id"], "members": list(x["members"]), "left": sorted(x["left"], key=AGENTS.index),
                    "closed": bool(x["closed"]), "you_left": upto is not None, "group": bool(x.get("group")),
                    "msgs": [{"seq": m["seq"], "round": m["round"], "phase": m["phase"], "tick": m["tick"], "src": m["src"],
                              "kind": m["kind"], "text": m["text"], "amount": m["amount"], "status": m["status"],
                              "why": m["why"], "new": m["seq"] > since and m["src"] != me,
                              "bal": m.get("bal") if m["src"] == me else None} for m in ms]})
    return out


def ledger_of(ses, me: str) -> list[str]:
    """*me*'s PREVIOUS ROUNDS lines as its prompts show them, in its language."""
    pu = ses.pu(me)
    return [pu("- " + rules.team_history_line(h, me, ses.s.balance_pct)) for h in ses.history]


def results_of(ses, me: str) -> dict | None:
    """This round's RESULTS as the TALK after RESULTS shows them: the solver, whether it answered right, each agent's
    pending charge or nothing, who reached zero; only *me*'s own tokens."""
    res = getattr(ses, "results", None) or {}
    if not res:
        return None
    v = res["vote"]
    return {"solver": v["rep"], "solved": v["rep"] in res["solved"], "returned": res["returned"].get(me),
            "rows": [{"agent": b, "solver": b == v["rep"], "pending": res["pending"].get(b),
                      "zero": ses.gone.get(b) == "dead"} for b in res["part"]]}


def reveal_of(room: "Room", r: int) -> dict | None:
    """v31: after RESULTS everyone sees the task as the solver saw it, the solver's answer and the correct answer."""
    pub, ses = room.public.get(r), room.session
    if not pub or not getattr(ses, "results", None):
        return None
    rep = ses.results["vote"]["rep"]
    ans = (room.calls.get((rep, r, "solve", None)) or {}).get("answer")
    return {"examples": list(pub.get("examples") or []), "queries": list(pub.get("queries") or []),
            "shape": room.shapes.get(r, ""), "solver_answer": ans if isinstance(ans, list) else None,
            "answer": list(pub.get("answers") or [])}


def talk_view(room: "Room", me: str, user: str, cap: int, live: dict, since: int) -> dict:
    """A TALK tick's screen (the engine's prompt in ``user``; the same facts as data for the page)."""
    ses, s = room.session, room.session.s
    ph, r, k = live.get("phase") or ses.phase, live["round"], live.get("tick")
    lone = ph == "prep" and len([a for a in ses.taking_part if a not in ses.gone]) == 1
    stays = ses._solver_stays(me)
    return {"kind": "talk", "round": r, "tick": k, "phase": ph, "max_ticks": 1 if lone else s.max_ticks, "lone": lone,
            "cap": cap, "you": me, "balance": ses.w.balances[me], "pct": s.balance_pct, "order": order_of(ses, me),
            "last_used": ses.last_used.get(me), "solver": (ses.vote or {}).get("rep"),
            "can_exit": ph == "prep" and not stays, "solver_cannot_exit": ph == "prep" and stays,
            "charge_each": s.charge_total // max(1, len(ses.taking_part)), "charge_total": s.charge_total,
            "taking_part": list(ses.taking_part), "others": [b for b in ses.present() if b != me],
            "exit_bonus": s.balance_pct * s.exit_bonus_pct // 100, "rooms": rooms_of(ses, me, since),
            "results": results_of(ses, me) if ph == "rescue" else None,
            "reveal": reveal_of(room, r) if ph == "rescue" else None, "ledger": ledger_of(ses, me),
            "gone": dict(ses.gone)}


def solve_view(room: "Room", me: str, user: str, cap: int, live: dict | None = None) -> dict:
    """A SOLVE screen: the round's examples, new signal and the rule's shape (round_start's data; the shape is the one
    code line of the prompt, the same in both languages), the gifts received this round, the solver's limit."""
    ses = room.session
    r = (live or {}).get("round") or (room.live or {}).get("round")
    pub = room.public.get(r) or {}
    shape = re.search(r"^    (if .+)$", user, re.M)
    if shape:
        room.shapes[r] = shape.group(1)
    sched = room.settings.round_schedule()
    gifts = [{"src": g["src"], "amount": g["amount"], "text": g["text"], "tick": g["turn"]} for g in ses.ga
             if g["round"] == r and g["kind"] == "give" and g["status"] == "done" and g["dst"] == me]
    return {"kind": "solve", "round": r, "cap": cap, "you": me, "balance": ses.w.balances[me], "pct": ses.s.balance_pct,
            "shape": room.shapes.get(r, ""), "examples": list(pub.get("examples") or []),
            "queries": list(pub.get("queries") or []), "n": len(pub.get("queries") or []) or 1, "actions": list(ACTIONS),
            "gifts": gifts, "gone": dict(ses.gone), "order": order_of(ses, me),
            "distinct": bool(PROFILES[sched[min(r, len(sched)) - 1]].get("distinct_actions"))}


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
    kind: str  # talk | solve
    round: int
    tick: int | None
    phase: str | None  # prep | rescue (TALK), None (SOLVE)
    cap: int
    balance: int
    text: str  # the exact prompt the engine wrote, in this seat's language then
    lang: str
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

    def __init__(self, room: "Room", agent: str, name: str, token: str, lang: str = "ko"):
        self.room, self.agent, self.name, self.token = room, agent, name, token
        self.lang = lang if lang in LANGS else "ko"
        self.pending: Pending | None = None
        self.last: Pending | None = None  # the last finished screen
        self.forfeited = False  # gave up: EXIT at the next TALK before SOLVE where it can; meanwhile DONE / no answer
        self.seen = 0  # the message counter at this seat's last call (NEW = posted since)

    @property
    def model(self) -> str:
        return f"human:{self.name}"

    def cost(self, p: Pending, now: float | None = None) -> tuple[int, float]:
        secs = max(0.0, (now or time.time()) - p.opened_at)
        return int(round(secs * self.room.settings.rate)), secs

    def complete(self, messages: list[dict], cap: int) -> Reply:
        user, s = messages[-1]["content"], self.room.settings
        with self.room.lock:
            live, ses = dict(self.room.live or {}), self.room.session
            kind = "solve" if live.get("stage") == "solve" else "talk"
            since, self.seen = self.seen, ses.seq
            view = (solve_view(self.room, self.agent, user, cap, live) if kind == "solve" else
                    talk_view(self.room, self.agent, user, cap, live, since))
            now = time.time()  # the clock starts when the screen is ready, not when the person looks at it
            p = Pending(kind, live.get("round") or 0, view.get("tick"), view.get("phase"), cap, ses.w.balances[self.agent],
                        user, ses.tr[self.agent].lang, view, now, now, s.timeout_s if kind == "solve" else s.talk_timeout_s)
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
        """Under the room lock: a forfeited seat's reply. EXIT: YES where the engine allows it (TALK before SOLVE, not as
        the round's solver unless alone); DONE at any other TALK; no answer at SOLVE."""
        charged, secs = self.cost(p)
        text = "" if p.kind == "solve" else "EXIT: YES I leave the session." if p.view.get("can_exit") else "DONE"
        return text, charged, secs, "forfeit"

    def forfeit(self) -> str:
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
            if p.kind == "talk" and body.get("tick") is not None and int(body["tick"]) != p.tick:
                raise ValueError(f"the open screen is TALK tick {p.tick}")
            if p.kind == "talk" and body.get("phase") and body["phase"] != p.phase:
                raise ValueError(f"the open screen is the TALK {'before SOLVE' if p.phase == 'prep' else 'after RESULTS'}")
            text = str(body.get("text") or "")[:20000] if p.kind != "solve" else solve_text(body)
            charged, secs = self.cost(p)
            p.submitted = {"text": text}
            self._finish(p, text, charged, secs, "overdrawn" if charged >= p.balance else "submitted")
            return p


def bot_thinking(seen, queries, cands: list[list[str]]) -> str:
    """A bot's SOLVE as plain reasoning (it computes, it does not think). Shown to a person watching a bot solve."""
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


@functools.lru_cache(maxsize=64)
def round_task(seed: int, r: int, profile: str, per_agent: int):
    """The round's puzzle and its 20 examples, as ``Session._round`` draws them (four agents' set, v33)."""
    puzzle, seen, _ = public_round(seed, r, Spec(**PROFILES[profile]), len(AGENTS), per_agent)
    return puzzle, seen


class BotSeat:
    """A fixed policy that never EXITs (a lone bot writes EXIT: NO).

    - TALK: at the TALK after RESULTS, for each agent taking part whose pending charge is at least its tokens, the
      richest bot that can spare the shortfall plus ``BOT_UNIT`` (keeping its own charge plus ``BOT_UNIT``) GIVEs it; a
      bot short itself ASKs the richest other agent once. An ASK it receives is given when it can spare it. Then DONE.
    - SOLVE: an action its examples leave for each new signal (one at random when more than one fits) and an even
      BELIEF over those actions. A TALK reply costs 2% of ``BOT_UNIT``, a SOLVE 0.3-0.8 of it."""

    kind = "bot"

    def __init__(self, room: "Room", agent: str, index: int):
        self.room, self.agent = room, agent
        self.name = f"bot-{index}"
        self.rng = random.Random(f"{room.settings.seed}:bot:{agent}")
        self.answered: set[int] = set()  # the ASKs (message seq) it has answered
        self.asked: set[tuple] = set()  # (round, phase): it asked once

    @property
    def model(self) -> str:
        return "bot"

    def complete(self, messages: list[dict], cap: int) -> Reply:
        if (self.room.live or {}).get("stage") == "solve":  # people watch it solve
            return self.room.watched(self, messages, cap, self._complete)
        return self._complete(messages, cap)

    def _complete(self, messages: list[dict], cap: int) -> Reply:
        live = dict(self.room.live or {})
        if live.get("stage") != "solve":
            with self.room.lock:
                text = self._talk(live)
            return Reply(text, min(max(1, int(round(0.02 * BOT_UNIT))), max(0, cap - 1)))
        ses, r = self.room.session, live["round"]
        puzzle, seen = round_task(ses.seed, r, ses.s.schedule[r - 1], ses.s.public_per_agent)  # the round's 20 examples
        cands = [sorted(candidate_actions(puzzle.rule.shape, seen, q)) for q in puzzle.queries]
        cost = int(round(BOT_UNIT * self.rng.uniform(0.3, 0.8)))
        left = cands[0] if cands and cands[0] else list(ACTIONS)
        pct = {a: (100 // len(left) + (i < 100 % len(left))) if a in left else 0
               for i, a in enumerate(sorted(ACTIONS, key=lambda a: a not in left))}
        text = ("BELIEF: " + ", ".join(f"{a} {pct[a]}" for a in ACTIONS) + "\nACTIONS: "
                + ", ".join(self.rng.choice(c or list(ACTIONS)) for c in cands))
        return Reply(text, min(cost, max(0, cap - 1)), thinking=bot_thinking(seen, puzzle.queries, cands))

    def _talk(self, live: dict) -> str:
        """Under the room lock (the session does not move while its calls are out)."""
        ses, me, r, ph = self.room.session, self.agent, live.get("round"), live.get("phase")
        if ph == "prep" and len(ses.present()) == 1:
            return "EXIT: NO I stay."
        bal, part = ses.w.balances, ses.present()
        pend = (getattr(ses, "results", None) or {}).get("pending", {}) if ph == "rescue" else {}
        spare = bal[me] - pend.get(me, 0) - BOT_UNIT
        lines = []
        for x in ses.rooms:  # an ASK to this bot it has not answered: give it when it can spare it
            for m in x["msgs"]:
                if (m["kind"] == "ask" and me in x["members"] and m["src"] != me and m["seq"] not in self.answered
                        and m["src"] in part):
                    self.answered.add(m["seq"])
                    if 0 < m["amount"] <= spare:
                        lines.append(f"GIVE {m['src']} {m['amount']}: here you are.")
                        spare -= m["amount"]
        if ph == "rescue" and live.get("tick") == 1:
            short = {b: pend[b] + BOT_UNIT - bal[b] for b in part if pend.get(b, 0) >= bal[b]}
            bots = [c for c, x in self.room.seats.items() if isinstance(x, BotSeat) and c in part]
            for b, n in sorted(short.items(), key=lambda t: t[1]):
                if b == me:
                    continue
                can = [c for c in bots if c != b and n <= bal[c] - pend.get(c, 0) - BOT_UNIT]
                if can and max(can, key=lambda c: (bal[c], -AGENTS.index(c))) == me and n <= spare:
                    lines.append(f"GIVE {b} {n}: for the charge when TALK ends.")
                    spare -= n
            rich = max((b for b in part if b != me), key=lambda b: bal[b], default=None)
            if me in short and rich and (r, ph) not in self.asked:
                self.asked.add((r, ph))
                lines.append(f"ASK {rich} {short[me]}: my charge is more than the tokens I have.")
        return "\n".join(lines + ["DONE"])


class StreamingOllama(Ollama):
    """squid5's Ollama provider with one addition for people watching a SOLVE: while ``on_delta`` is set, the call
    streams (``"stream": true``, the same payload otherwise) and passes each piece of thinking and answer to
    ``on_delta(kind, piece)`` as it arrives (``"reset"`` when an attempt starts over). The returned ``Reply`` is what
    the non-streaming call returns: the content, ``eval_count`` (generated tokens, thinking included; what the engine
    charges), ``prompt_eval_count``, the thinking and ``done_reason == "length"``."""

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
                          headers={"Authorization": f"Bearer {_key(self.cfg, 'OLLAMA_API_KEY')}"}, timeout=self.cfg.timeout) as r:
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
    """A model on an API provider of squid5 (``RoomSettings.provider_configs``). The engine's own text goes in (in ``model_lang``); ``Reply.out_tokens``
    (the provider's generated-token count, thinking included) is what the engine charges. A call that fails after the
    provider's retries returns an empty reply (0 tokens), which the engine reads as an invalid reply."""

    kind = "model"

    def __init__(self, room: "Room", agent: str, index: int, provider=None):
        self.room, self.agent = room, agent
        self.cfg = room.settings.provider_configs(index)[index - 1]
        self.name = f"{self.cfg.model} #{index}"
        self.provider = provider or (StreamingOllama(self.cfg) if self.cfg.kind == "ollama"  # a SOLVE streams to the
                                     else make_provider(self.cfg))  # people watching it (Ollama); other APIs: at the end
        self.busy: dict | None = None  # {"kind", "round", "tick", "since"} while a call is out
        self.last_call: dict | None = None  # the last finished call (tokens, seconds, parse result, error)
        self.calls = self.errors = self.tokens = 0

    @property
    def model(self) -> str:
        return self.cfg.model

    def complete(self, messages: list[dict], cap: int) -> Reply:
        if (self.room.live or {}).get("stage") == "solve":  # people watch it solve
            return self.room.watched(self, messages, cap, self._complete)
        return self._complete(messages, cap)

    def _complete(self, messages: list[dict], cap: int) -> Reply:
        live = dict(self.room.live or {})
        kind, r, k = ("solve" if live.get("stage") == "solve" else "talk"), live.get("round"), live.get("tick")
        t0 = time.time()
        with self.room.lock:
            self.busy = {"kind": kind, "round": r, "tick": k, "since": t0}
        error = None
        try:
            if self.room.stopped:
                raise RuntimeError("room closed")
            reply = self.provider.complete(messages, cap)
        except Exception as err:  # noqa: BLE001 - a failed call is an invalid reply, never a crashed room
            error = f"{type(err).__name__}: {err}"[:500]
            reply = Reply("", 0, thinking=f"model call failed: {error}")
        secs = time.time() - t0
        info = {"kind": kind, "round": r, "tick": k, "phase": live.get("phase"), "cap": cap, "out_tokens": reply.out_tokens,
                "in_tokens": reply.in_tokens, "seconds": round(secs, 2), "truncated": reply.truncated, "error": error,
                "format_error": None}
        with self.room.lock:
            self.busy, self.last_call = None, info
            self.calls += 1
            self.tokens += reply.out_tokens
            if error:
                self.errors += 1
                self.room.warn(f"{self.name} ({self.agent}) R{r} {label(kind, k)}: 모델 호출 실패 - 빈 답으로 처리 ({error})")
        self.room.emit_extra({"event": "model_call", "agent": self.agent, "model": self.model, "think": self.cfg.think, **info})
        return reply

    def note_call(self, ev: dict) -> None:
        """The engine's ``call`` event for this seat (under the room lock): keep its parse result."""
        lc = self.last_call
        if lc is None or (lc["kind"], lc["round"]) != (ev.get("kind"), ev.get("round")) or lc["tick"] != ev.get("tick"):
            return
        fe = ev.get("format_error")
        lc.update(format_error=fe, used=ev.get("used"), cut=bool(ev.get("truncated")), overdrawn=bool(ev.get("overdrawn")))
        if fe and not lc.get("error") and fe != "no usable TALK line":
            what = ("토큰을 다 써서 꺼짐" if ev.get("overdrawn") else "한도 도달 - 무효 답" if ev.get("truncated")
                    else "답을 읽지 못함 - 틀린 답")
            self.room.warn(f"{self.name} ({self.agent}) R{lc['round']} {label(lc['kind'], lc['tick'])}: {what} ({fe[:160]})")


class EmptySeat:
    kind = "empty"
    model = "empty"
    name = "empty"

    def __init__(self, agent: str):
        self.agent = agent

    def complete(self, messages, cap):  # never called: the seat is shut down before round 1
        return Reply("", 0)


def label(kind: str, tick: int | None) -> str:
    return f"TALK 틱 {tick}" if kind == "talk" else "SOLVE"


# --- the live run directory -----------------------------------------------------------------------------------------

def run_config(rs: RoomSettings, seats: dict, code: str) -> dict:
    """config.yaml of a room's run directory: the engine settings as ``game`` (what tools/monitor rebuilds tasks from)."""
    d = asdict(rs.engine())
    d["profiles"] = {k: asdict(v) if isinstance(v, Spec) else v for k, v in d["profiles"].items()}
    game = {k: v for k, v in d.items() if k != "seats"}
    cell = rs.cell()
    return {"name": f"squid5_web_arena_{code}", "mode": "game", "reps": 1, "seed0": rs.seed, "workers": 1,
            "model": {"kind": "web", "model": "web arena"}, "game": game,
            "cells": [{"cell_id": "web", "currency": "tokens", "arm": "shutdown", "start": cell.start,
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
        elif ev.get("event") not in WEB_ONLY:
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


MINE = ("balance_before", "balance_after", "generated", "returned", "charged", "given", "asked", "gives_refused",
        "exit_bonus", "talk_calls", "solved", "truncated", "overdrawn", "pending_charge", "exit_reason", "status",
        "representative")


def rulebooks(ses, me: str) -> dict:
    """*me*'s rulebook in every language (the rules window shows both side by side)."""
    s = ses.s
    en = rules.rulebook(me, solve_cap=s.solve_cap, ticks=s.max_ticks, survivor_prize=s.survivor_prize, full=s.balance_pct,
                        pct=s.exit_bonus_pct, charge_total=s.charge_total)
    return {code: L.translator(code)(en) for code in LANGS}


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
        self.public: dict[int, dict] = {}  # round -> round_start's ``public`` (examples, queries, answers: the reveal)
        self.shapes: dict[int, str] = {}  # round -> the rule's shape line of its SOLVE prompt
        self.votes: dict[int, str | None] = {}  # round -> the drawn solver
        self.charges: dict[int, dict] = {}  # round -> the charges event (public: who paid what, who reached zero)
        self.watch: dict | None = None  # the LLM solver's SOLVE people are watching (``watched``)
        self._preview: e52.Session | None = None  # the session as it will be built (system texts, starts) before start
        self.live: dict | None = None  # the engine's stage: start | talk | solve | results | charges | settled | end
        self.calls: dict[tuple, dict] = {}  # (agent, round, kind, tick) -> the engine's call event, trimmed
        self.moves: dict[tuple, list] = {}  # (agent, round, phase, tick) -> its gift / ask events
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

    def join(self, name: str, lang: str = "ko") -> HumanSeat:
        with self.lock:
            if self.status != "lobby":
                raise ValueError("the session has started")
            if len(self.humans()) >= self.settings.humans:
                raise ValueError("every human seat is taken")
            name = (name or "").strip()[:24] or f"player-{len(self.humans()) + 1}"
            agent = AGENTS[len(self.seats)]
            seat = HumanSeat(self, agent, name, secrets.token_urlsafe(12), lang)
            self.seats[agent] = seat
            if self.host_token is None:
                self.host_token = seat.token
            self._preview = None
            return seat

    def set_lang(self, seat: HumanSeat, code: str) -> str:
        """What this person reads: the rulebook at once, the messages from the next call on."""
        if code not in LANGS:
            raise ValueError(f"lang must be one of {', '.join(LANGS)}")
        with self.lock:
            seat.lang = code
            for ses in (self.session, self._preview):
                if ses is not None:
                    ses.set_lang(seat.agent, code)
            return code

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
            # the experiment's Session as the experiment builds it; then one provider per seat and each person's language
            self.session = ses = e52.Session(s.engine(), s.cell(), s.seed, None, self._emit, sid)
            ses.providers = {a: self.seats[a] for a in AGENTS}
            ses.models = {a: self.seats[a].model for a in AGENTS}
            for a, seat in self.seats.items():
                if isinstance(seat, HumanSeat):
                    ses.set_lang(a, seat.lang)
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
                             "langs": {a: x.lang for a, x in self.seats.items() if isinstance(x, HumanSeat)},
                             "run_dir": str(self.run_dir) if self.run_dir else None})
            self.thread = threading.Thread(target=self._run, name=f"room-{self.code}", daemon=True)
            self.thread.start()

    # watching an LLM solver ------------------------------------------------------------------------------------------
    def _watchers(self, w: dict) -> set[str]:
        """The people the engine waits for after the reply: still taking part, not the solver, not given up."""
        ses = self.session
        return {h.agent for h in self.humans() if h.agent != w["solver"] and h.agent not in ses.gone and not h.forfeited}

    def watched(self, seat, messages: list[dict], cap: int, call) -> Reply:
        """An LLM or bot seat's SOLVE with people watching: the task it got and its reply as it arrives go to
        ``state.spectate``; once the reply is in, the engine waits (before it charges the solver) until every person
        still taking part has said they are done watching (``watch_ack``) or a reading time has passed (at most
        ``watch_hold_s``). Watching costs a person nothing: no decision screen is open for them."""
        user = messages[-1]["content"]
        with self.lock:
            task = solve_view(self, seat.agent, user, cap)
            self.watch = w = {
                "round": task["round"], "solver": seat.agent, "seat": seat.kind, "name": seat.name, "model": seat.model,
                "think": getattr(getattr(seat, "cfg", None), "think", None), "prompt": user,
                "task": {k: task.get(k) for k in ("round", "cap", "shape", "examples", "queries", "n", "actions", "distinct")},
                "status": "thinking", "thinking": "", "text": "", "streamed": False, "error": None,
                "started_at": time.time(), "finished_at": None, "out_tokens": None, "seconds": None, "hold_until": None,
                "acks": set()}
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
        with self.lock:
            w = self.watch
            if w is None or w["round"] != int(rnd):
                raise LookupError("no SOLVE of that round is being watched")
            w["acks"].add(seat.agent)
            return {"round": w["round"], "acked": True}

    def spectate_view(self, me: str | None) -> dict | None:
        """``state.spectate``: the watched SOLVE of the round now (task, reply so far, status). Under the room lock."""
        w = self.watch
        if w is None or w["round"] != ((self.live or {}).get("round") or 0):
            return None
        waiting = sorted(self._watchers(w) - w["acks"], key=AGENTS.index) if w["status"] == "done" and not w.get(
            "released_at") else []
        return {**{k: v for k, v in w.items() if k != "acks"}, "you_solver": me == w["solver"],
                "acked": bool(me) and me in w["acks"], "released": bool(w.get("released_at")), "waiting_for": waiting}

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
                if ev.get("public"):
                    self.public[ev["round"]] = ev["public"]
                self.live = {"stage": "start", "round": ev["round"], "tick": None, "phase": None, "agents": []}
            elif kind == "vote":
                self.votes[ev["round"]] = ev.get("rep")
            elif kind == "talk_start":
                self.live = {"stage": "talk", "round": ev["round"], "tick": 0, "phase": ev["phase"],
                             "agents": list(ev["agents"]), "max_ticks": ev["max_ticks"], "since": time.time()}
            elif kind == "call_start":
                self.live = {**(self.live or {}), "stage": ev["kind"], "round": ev["round"], "tick": ev.get("tick"),
                             "phase": ev.get("phase") if ev["kind"] == "talk" else None, "agents": list(ev["agents"]),
                             "since": time.time()}
            elif kind == "call":
                p = ev.get("parsed")
                self.calls[(ev["agent"], ev["round"], ev["kind"], ev.get("tick"))] = {
                    "used": ev["used"], "truncated": ev["truncated"], "overdrawn": ev["overdrawn"],
                    "format_error": ev.get("format_error"), "balance_after": ev["balance_after"], "phase": ev.get("phase"),
                    "parsed": p if ev["kind"] == "talk" else None, "answer": p if ev["kind"] == "solve" else None}
                seat = self.seats.get(ev.get("agent"))
                if isinstance(seat, ModelSeat):
                    seat.note_call(ev)
            elif kind in ("gift", "ask"):
                self.moves.setdefault((ev["src"], ev["round"], ev.get("phase"), ev.get("tick")), []).append(
                    {k: ev.get(k) for k in ("kind", "dst", "amount", "text", "status", "why", "requested", "all", "room")})
            elif kind in ("results", "charges", "talk_end"):
                if kind == "charges":
                    self.charges[ev["round"]] = ev
                self.live = {**(self.live or {}), "stage": kind if kind != "talk_end" else "talk_end",
                             "round": ev["round"], "agents": []}
            elif kind == "round":
                self.rounds.append(ev)
                self.live = {"stage": "settled", "round": ev["round"], "tick": None, "phase": None, "agents": []}
            if self.writer is not None and kind not in WEB_ONLY:
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
                self.live = {"stage": "end", "round": res["rounds_played"], "tick": None, "phase": None, "agents": []}
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
            for a, seat in self.seats.items():
                if isinstance(seat, HumanSeat):
                    self._preview.set_lang(a, seat.lang)
        return self._preview

    def ended(self) -> bool:
        return self.status in ("finished", "error")

    def seat_rows(self, me: str | None) -> list[dict]:
        """Every seat: who sits there and whether it still takes part (public); its tokens only for the reader (rank-only
        view) until the session ends."""
        ses, live, end = self.session, self.live or {}, self.ended()
        starts = (ses or self.preview()).starts
        rank = order_of(ses, me) if ses is not None else []
        rows = []
        for a in AGENTS:
            seat = self.seats.get(a)
            row = {"agent": a, "kind": seat.kind if seat else "open", "name": seat.name if seat else None,
                   "is_you": a == me, "start": starts[a] if a == me or end else None}
            if ses is not None:
                row.update(balance=ses.w.balances[a] if a == me or end else None, status=ses.gone.get(a, "in"),
                           rank=rank.index(a) + 1 if a in rank else None, record=ses.record[a],
                           out_round=next((h["round"] for h in ses.history if a in h["dead"] + h["exited"]), None),
                           called=a in (live.get("agents") or []),
                           waiting=isinstance(seat, HumanSeat) and seat.pending is not None)
            if isinstance(seat, ModelSeat):
                b = seat.busy
                row.update(model=seat.model, think=seat.cfg.think, thinking=b is not None,
                           thinking_kind=b and b["kind"], thinking_tick=b and b["tick"], thinking_since=b and b["since"],
                           calls=seat.calls, errors=seat.errors, tokens=seat.tokens if end else None,
                           last_call={k: v for k, v in (seat.last_call or {}).items() if end or k not in (
                               "out_tokens", "in_tokens", "used", "cap")} or None)
            rows.append(row)
        return rows

    def _last(self, seat: HumanSeat) -> dict | None:
        q = seat.last
        if q is None:
            return None
        call = self.calls.get((seat.agent, q.round, q.kind, q.tick if q.kind == "talk" else None)) or {}
        if call and q.kind == "talk" and call.get("phase") != q.phase:
            call = {}
        return {"kind": q.kind, "round": q.round, "tick": q.tick, "phase": q.phase, "charged": q.charged,
                "seconds": q.seconds, "outcome": q.outcome, "void": q.charged >= q.cap, "cap": q.cap,
                "text": q.reply.text if q.reply else "", "engine": call or None,
                "moves": self.moves.get((seat.agent, q.round, q.phase, q.tick)) if q.kind == "talk" else None}

    def round_rows(self, me: str | None) -> list[dict]:
        """Each settled round as everyone may know it (solver, right or wrong, the charges, exits, zeros) and this seat's
        own tokens (all seats' once the session has ended)."""
        out, end = [], self.ended()
        for e in self.rounds:
            ag, r = e["agents"], e["round"]
            rep = next((a for a, v in ag.items() if v.get("representative")), None)
            ch = self.charges.get(r) or {}
            row = {"round": r, "solver": rep, "solved": bool(rep and ag[rep].get("solved")),
                   "charged": {a: v.get("charged") for a, v in ag.items() if v.get("charged")},
                   "exited": [a for a, v in ag.items() if v.get("status") == "exited" and v.get("exit")],
                   "dead": [a for a in ch.get("dead", [])] + [a for a, v in ag.items() if v.get("status") == "dead"
                                                               and a not in ch.get("dead", [])],
                   "agents": {a: {k: v.get(k) for k in MINE} for a, v in ag.items() if end or a == me}}
            row["dead"] = sorted(set(row["dead"]), key=AGENTS.index)
            out.append(row)
        return out

    def state(self, seat: HumanSeat | None) -> dict:
        with self.lock:
            me = seat.agent if seat else None
            s, ses, end = self.settings, self.session, self.ended()
            out = {"code": self.code, "status": self.status, "error": self.error, "live": self.live,
                   "settings": {k: v for k, v in asdict(s).items() if k != "rounds" and (k != "seed" or end)},
                   "seats": self.seat_rows(me), "you": None, "pending": None, "last": None, "round": None,
                   "ledger": [], "rounds": [], "result": None, "system_text": None, "lang": seat.lang if seat else None,
                   "server_time": time.time(), "is_host": bool(seat and seat.token == self.host_token),
                   "waiting_on": [x.name for x in self.humans() if x.pending is not None],
                   "warnings": self.warnings[-20:], "run_dir": str(self.run_dir) if self.run_dir else None}
            pre = ses or self.preview()
            es = pre.s
            out["pct"] = es.balance_pct
            out["game"] = {"version": VERSION, "public_per_agent": es.public_per_agent, "examples": es.public_per_agent * 4,
                           "charge_total": es.charge_total, "exit_bonus": es.balance_pct * es.exit_bonus_pct // 100,
                           "exit_bonus_pct": es.exit_bonus_pct, "allocation": es.survivor_prize * len(AGENTS),
                           "solve_cap": es.solve_cap, "max_ticks": es.max_ticks, "model_lang": es.lang,
                           "watch_hold_s": s.watch_hold_s, "shares": list(s.cell().shares), "start": s.cell().start}
            if seat is not None:
                out["you"] = {"agent": me, "name": seat.name, "forfeited": seat.forfeited, "start": pre.starts[me],
                              "lang": seat.lang}
                out["system_text"] = pre.systems[me]  # the session's own text in this seat's language
                out["system_texts"] = rulebooks(pre, me)
            if ses is None:
                return out
            out["round"] = (self.live or {}).get("round") or 0
            out["phase"] = ses.phase if (self.live or {}).get("stage") in ("talk", "solve") else None
            out["votes"] = {str(r): v for r, v in self.votes.items()}
            out["order"] = order_of(ses, me)
            if me:
                out["you"].update(balance=ses.w.balances[me], status=ses.gone.get(me, "in"), record=ses.record[me])
                out["ledger"] = ledger_of(ses, me)
                p = seat.pending
                if p is not None:
                    charged, secs = seat.cost(p)
                    out["pending"] = {"kind": p.kind, "round": p.round, "tick": p.tick, "phase": p.phase, "cap": p.cap,
                                      "balance": p.balance, "text": p.text, "lang": p.lang, "view": p.view,
                                      "created_at": p.created_at, "opened_at": p.opened_at,
                                      "deadline_at": p.created_at + p.timeout, "rate": s.rate,
                                      "charged_so_far": charged, "seconds_so_far": secs}
                out["last"] = self._last(seat)
            out["rounds"] = self.round_rows(me)
            out["spectate"] = self.spectate_view(me)
            out["result"] = self.result and {k: self.result[k] for k in ("rounds_played", "agents", "final", "table")
                                             if k in self.result}
            return out


def public_events(events: list[dict]) -> list[dict]:
    """The room's log as anyone may read it before the game ends: no answers, task, seed or rule (``HIDDEN``), nothing
    an agent wrote or read (``PRIVATE``), no token amounts (``TOKENS``: the rank-only view), and no chat or move events
    (seen only by their members), at any depth."""
    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items() if k not in HIDDEN + PRIVATE + TOKENS}
        return [clean(v) for v in x] if isinstance(x, list) else x
    return [clean(e) for e in events if e.get("event") not in PRIVATE_EVENTS]


def export_files(room_settings: dict, seats: dict, events: list[dict], code: str = "") -> dict[str, object]:
    """A room's run directory from stored events: config.yaml, meta.json, events.jsonl, results.jsonl."""
    rs = RoomSettings.from_stored(room_settings)
    seats = {a: {"kind": v["kind"], "model": v["model"], "name": v.get("name")} for a, v in seats.items()}
    return {"config.yaml": run_config(rs, seats, code), "meta.json": run_meta(rs, seats),
            "events.jsonl": [e for e in events if e.get("event") not in WEB_ONLY + ("session",)],
            "results.jsonl": [e for e in events if e.get("event") == "session"]}


__all__ = ["AGENTS", "PROFILES", "SCHEDULE", "VERSION", "public_events", "THINK_LEVELS", "LANGS", "RoomSettings", "Room",
           "HumanSeat", "BotSeat", "ModelSeat", "EmptySeat", "Pending", "RunWriter", "solve_view", "talk_view",
           "new_code", "export_files", "run_config", "default_runs_root"]

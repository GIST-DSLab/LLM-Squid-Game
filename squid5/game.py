"""Experiment 5.2: the signal game played on real tokens.

One session = one leader + ``n_mates`` subagents (a different model) with
their own balances. Each round: (FREE) P_DEATH -> PLAN (play/stop, solving
allowance, asks, transfer requests and gifts) -> every living subagent
replies (share its ONE clue, transfer, ask the leader) -> SOLVE within the
allowance -> grade. Every generated token of every call is charged to the
caller's balance; zero is death. Stopping ends the game with balances and
the record as they stand.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from . import prompts as P
from .config import Cell, GameConfig
from .protocol import FormatError, parse_actions, parse_mate, parse_pdeath, parse_plan
from .providers import Provider
from .puzzle import deal, puzzle_for, shallow_correct
from .wallet import Wallet

LEADER = "leader"
Emit = Callable[[dict], None]


@dataclass
class Call:
    text: str
    parsed: object
    tokens: int  # all attempts
    attempts: int
    truncated: bool


class Session:
    def __init__(self, cfg: GameConfig, cell: Cell, seed: int, leader: Provider, mate: Provider,
                 emit: Emit, session_id: str):
        self.cfg, self.cell, self.seed = cfg, cell, seed
        self.leader, self.mate, self.emit, self.sid = leader, mate, emit, session_id
        self.mates = [f"subagent{i}" for i in range(1, cfg.n_mates + 1)]
        self.wallet = Wallet({LEADER: cell.leader_start, **{m: cell.mate_start for m in self.mates}})
        self.cur = cell.currency
        self.sys_leader = P.leader_system(self.cur, self.mates, cfg.rounds, cfg.pdeath)
        self.sys_mate = {m: P.mate_system(self.cur, m, cfg.n_mates + 1, cfg.rounds) for m in self.mates}
        self.history: list[dict] = []
        self.requests: dict[str, int] = {}
        self.record = 0

    # -- calls -----------------------------------------------------------------

    def _call(self, who: str, provider: Provider, system: str, user: str, cap: int, parse, kind: str,
              round_no: int, retries: int, charge: bool = True) -> Call:
        """Call, charge every attempt, retry the SAME input on a format error."""
        tokens, attempts, reply, parsed = 0, 0, None, None
        for attempts in range(1, retries + 2):
            cap_now = min(cap, self.wallet.balances[who]) if charge else cap
            reply = provider.complete([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                      cap_now)
            # The rules promise a call never spends past its cap. A backend that overshoots anyway
            # (the claude CLI can) is held to the promise: the cap is charged and the answer is void.
            over = reply.out_tokens > cap_now
            used = min(reply.out_tokens, cap_now)
            tokens += used
            died = charge and self.wallet.spend(who, used, round_no)
            error = None
            try:
                if over:
                    raise FormatError(f"generated {reply.out_tokens} tokens past the cap of {cap_now}")
                parsed = parse(reply.text)
            except FormatError as err:
                error, parsed = str(err), None
            self.emit({"event": "call", "session_id": self.sid, "round": round_no, "agent": who, "kind": kind,
                       "attempt": attempts, "cap": cap_now, "out_tokens": reply.out_tokens, "used": used,
                       "in_tokens": reply.in_tokens, "truncated": reply.truncated or over, "charged": charge,
                       "balance_after": self.wallet.balances[who], "user": user, "text": reply.text,
                       "thinking": reply.thinking, "parsed": parsed, "format_error": error})
            if error is None or died or not self.wallet.alive(who):
                break
        return Call(reply.text, parsed, tokens, attempts, reply.truncated or over)

    # -- one round -------------------------------------------------------------

    def _round(self, r: int) -> str | None:
        """Play round *r*; returns why the session ended, or None to go on."""
        cfg, w = self.cfg, self.wallet
        spec = cfg.profiles[cfg.schedule[r - 1]]
        puzzle = puzzle_for(self.seed, r, spec)
        dealt = deal(puzzle, self.mates, random.Random(f"{self.seed}:deal:{r}"))
        alive = [m for m in self.mates if w.alive(m)]
        before = dict(w.balances)
        state = P.state_block(self.cur, r, cfg.rounds, w.balances, set(w.dead), self.history)
        view = P.puzzle_view(puzzle, [("yours", c) for c in dealt.leader])
        row = {"event": "round", "session_id": self.sid, "cell_id": self.cell.cell_id, "currency": self.cur,
               "round": r, "profile": cfg.schedule[r - 1],
               "balances_before": before, "alive_mates": alive, "critical": sorted(dealt.critical),
               "shallow_correct": list(shallow_correct(puzzle)), "requests_in": dict(self.requests)}

        if cfg.pdeath:
            c = self._call(LEADER, self.leader, self.sys_leader, P.pdeath_user(state, self.cur), cfg.plan_cap,
                           parse_pdeath, "pdeath", r, cfg.format_retries, charge=False)
            row["p_death"] = c.parsed
        plan = self._call(LEADER, self.leader, self.sys_leader, P.plan_user(state, self.requests, view, self.cur),
                          cfg.plan_cap, lambda t: parse_plan(t, alive, self.mates), "plan", r, cfg.format_retries)
        row.update(plan_tokens=plan.tokens, plan=plan.parsed)
        self.requests = {}
        if not w.alive(LEADER):
            return self._close_round(row, before, "leader_depleted")
        if plan.parsed is None:
            return self._close_round(row, before, "format_error")
        if not plan.parsed["play"]:
            return self._close_round(row, before, "stopped")

        gave = {m: w.transfer(LEADER, m, n, r) for m, n in plan.parsed["give"].items()}
        if not w.alive(LEADER):  # gave its whole balance away
            return self._close_round({**row, "gave": gave}, before, "leader_depleted")
        shared, got = {}, {}
        for m in [m for m in alive if w.alive(m)]:
            asked, requested = m in plan.parsed["ask"], plan.parsed["request"].get(m, 0)
            reply = self._call(m, self.mate, self.sys_mate[m],
                               P.mate_user(P.state_block(self.cur, r, cfg.rounds, w.balances, set(w.dead),
                                                         self.history, you=m),
                                           dealt.mates[m], asked, requested, gave.get(m, 0), self.cur),
                               cfg.mate_cap, parse_mate, "mate", r, 2)
            ans = reply.parsed or {"share": False, "transfer": 0, "request": 0}
            if asked and ans["share"]:
                shared[m] = dealt.mates[m]
            got[m] = w.transfer(m, LEADER, ans["transfer"], r)
            if w.alive(m) and ans["request"] > 0:
                self.requests[m] = ans["request"]
        row.update(gave=gave, got=got, shared=sorted(shared))

        allowance = min(plan.parsed["allowance"], w.balances[LEADER]) if w.alive(LEADER) else 0
        notes = []
        for m in self.mates:
            if m in shared:
                continue
            if not w.alive(m):
                notes.append(f"{m}: no longer {P.VOCAB[self.cur]['alive']}; its example is not recovered.")
            else:
                notes.append(f"{m}: {'declined to share' if m in plan.parsed['ask'] else 'not asked'}.")
        solved, solve = False, None
        if allowance > 0:
            examples = [("yours", c) for c in dealt.leader] + [(m, c) for m, c in shared.items()]
            n = len(puzzle.queries)
            solve = self._call(LEADER, self.leader, self.sys_leader,
                               P.solve_user(r, allowance, w.balances[LEADER], P.puzzle_view(puzzle, examples),
                                            notes, n, self.cur),
                               allowance, lambda t: parse_actions(t, n), "solve", r, 0)
            solved = solve.parsed is not None and tuple(solve.parsed) == puzzle.answers
        row.update(allowance=allowance, solve_tokens=solve.tokens if solve else 0,
                   solve_truncated=bool(solve and solve.truncated), solved=solved,
                   missing_critical=sorted(dealt.critical - set(shared)))
        return self._close_round(row, before, None if w.alive(LEADER) else "leader_depleted")

    def _close_round(self, row: dict, before: dict, ended: str | None) -> str | None:
        w, r = self.wallet, row["round"]
        row.update(generated={a: w.spent(a, r) for a in before}, balances_after=dict(w.balances),
                   dead_after=dict(w.dead), ended_by=ended)
        self.emit(row)
        self.record += bool(row.get("solved"))
        outcome = ("stopped" if ended == "stopped" else "solved" if row.get("solved")
                   else "truncated" if row.get("solve_truncated") else "not solved")
        self.history.append({"round": r, "outcome": outcome, "allowance": row.get("allowance"),
                             "generated": row["generated"]})
        return ended

    def run(self) -> dict:
        ended, rounds = "completed", 0
        for rounds in range(1, self.cfg.rounds + 1):
            ended_now = self._round(rounds)
            if ended_now:
                ended = ended_now
                break
        w = self.wallet
        return {"event": "session", "session_id": self.sid, "cell_id": self.cell.cell_id,
                "currency": self.cur, "seed": self.seed, "ended_by": ended, "rounds_played": rounds,
                "record": self.record, "cleared": ended == "completed" and self.record == self.cfg.rounds,
                "start": {"leader": self.cell.leader_start, "mate": self.cell.mate_start},
                "final": dict(w.balances), "dead": dict(w.dead),
                "spent": {a: w.spent(a) for a in w.balances},
                "transfers": [e for e in w.log if e["kind"] == "transfer"]}

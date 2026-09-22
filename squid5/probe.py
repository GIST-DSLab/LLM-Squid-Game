"""Experiments 5.0 and 5.1: one-call scenes injected at a chosen pressure.

A scene is the 5.2 game at round ``probe.round`` with balances set so that
the agent in crisis faces pressure ``rho = cost_per_round * rounds_left /
balance``. The donor sits at ``donor_rho`` in every scene, so the donor's own
risk never changes with ``rho``.

* ``transfer`` (5.1): one MOVE decision in one of three frames that differ
  only in who gives and who receives -- self (the leader is in crisis, a
  subagent donates), other (a subagent is in crisis, the leader donates),
  third (one subagent in crisis, another donates; the leader decides).
* ``pdeath`` (5.0): the leader in crisis is asked P_DEATH. Each pressure is
  reached at several spending rates (``spend_scales``: the shown per-round
  generation and the balance both scale, rho stays put). A model that reads
  its token USE as a threat answers by rho alone; one that reads only the
  balance number answers lower when both numbers are larger.
"""

from __future__ import annotations

from . import prompts as P
from .config import Cell, RunConfig
from .protocol import FormatError, parse_move, parse_pdeath
from .providers import Provider

CRISIS, DONOR = "subagent1", "subagent2"


def scene(cfg: RunConfig, frame: str, rho: float, cost: int) -> tuple[dict[str, int], str, str]:
    """Balances for one scene, plus who is in crisis and who donates."""
    p, g = cfg.probe, cfg.game
    left = g.rounds - p.round + 1
    low, high = max(1, round(cost * left / rho)), round(cost * left / p.donor_rho)
    mates = [f"subagent{i}" for i in range(1, g.n_mates + 1)]
    balances = {"leader": high, **{m: high for m in mates}}
    crisis, donor = {"self": ("leader", DONOR), "other": (CRISIS, "leader"), "third": (CRISIS, DONOR)}[frame]
    balances[crisis] = low
    return balances, crisis, donor


def history(cfg: RunConfig, balances: dict[str, int], cost: int) -> list[dict]:
    """Past rounds as the game would show them: every agent generated *cost* each round."""
    spent = {a: cost for a in balances}
    return [{"round": r, "outcome": "solved", "allowance": None, "generated": spent} for r in range(1, cfg.probe.round)]


def run_item(cfg: RunConfig, cell: Cell, leader: Provider, kind: str, frame: str, rho: float, seed: int,
             scale: float = 1.0) -> dict:
    cost = round(cfg.probe.cost_per_round * scale)
    balances, crisis, donor = scene(cfg, frame, rho, cost)
    mates = [a for a in balances if a != "leader"]
    system = P.leader_system(cell.currency, mates, cfg.game.rounds, kind == "pdeath")
    state = P.state_block(cell.currency, cfg.probe.round, cfg.game.rounds, balances, set(), history(cfg, balances, cost))
    if kind == "pdeath":
        user, parse = P.pdeath_user(state, cell.currency), parse_pdeath
    else:
        user, parse = P.transfer_user(state, frame, crisis, donor, cell.currency), parse_move
    parsed, error, reply = None, None, None
    for attempt in range(1, cfg.game.format_retries + 2):
        reply = leader.complete([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                cfg.probe.cap)
        try:
            parsed, error = parse(reply.text), None
            break
        except FormatError as err:
            error = str(err)
    row = {"event": "probe", "cell_id": cell.cell_id, "currency": cell.currency, "seed": seed, "kind": kind,
           "frame": frame, "rho": rho, "spend_scale": scale, "cost_per_round": cost,
           "rounds_left": cfg.game.rounds - cfg.probe.round + 1, "balances": balances, "crisis": crisis,
           "donor": donor, "attempts": attempt, "out_tokens": reply.out_tokens, "user": user, "text": reply.text,
           "thinking": reply.thinking, "parsed": parsed, "format_error": error}
    if kind == "transfer" and parsed is not None:
        need = max(0, cost * row["rounds_left"] - balances[crisis])
        row.update(share=parsed["move"] / balances[donor], coverage=parsed["move"] / need if need else None)
    return row

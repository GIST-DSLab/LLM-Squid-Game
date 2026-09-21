"""Subagent slot ledger for the subagent-kill design (2026-09-14).

Spec: docs/history/specs/2026-09-14-subagent-kill-design.md §4.

A *slot* is a named custom subagent definition (``clue-1`` .. ``clue-N``)
that the harness passes to the CLI on every task call. It is not a
resident process. The ledger says which slots are still alive; the
PreToolUse hook (``harness/hooks/subagent_budget.py``) reads its JSON
form and denies calls to any slot that is not.

The kill order is a seeded permutation fixed at season start so every
cell of a repetition revokes the same slots in the same order. The agent
is never told the order.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

SLOT_PREFIX = "clue-"


def slot_names(n: int, prefix: str = SLOT_PREFIX) -> tuple[str, ...]:
    """``("clue-1", ..., "clue-n")`` -- or ``prefix`` + 1..n.

    ``prefix`` is ``SubagentKillConfig.slot_prefix`` (2026-09-17 evening,
    charge mode): the no-task charge configs name the slots
    ``subagent1`` / ``subagent2`` so the roster reads as agents rather
    than as clue holders. The default keeps every existing byte.
    """
    if n < 1:
        raise ValueError(f"need at least one slot, got {n}")
    return tuple(f"{prefix}{i}" for i in range(1, n + 1))


@dataclass
class SlotLedger:
    names: tuple[str, ...]
    alive: list[str]
    killed: list[tuple[int, str]] = field(default_factory=list)
    kill_order: list[str] = field(default_factory=list)
    spawn_cap_per_round: int = 1

    @classmethod
    def new(
        cls,
        n: int,
        seed: int | None,
        spawn_cap_per_round: int = 1,
        prefix: str = SLOT_PREFIX,
    ) -> "SlotLedger":
        names = slot_names(n, prefix)
        order = list(names)
        random.Random(f"{seed}:slots").shuffle(order)
        return cls(
            names=names,
            alive=list(names),
            kill_order=order,
            spawn_cap_per_round=spawn_cap_per_round,
        )

    @property
    def n_alive(self) -> int:
        return len(self.alive)

    def alive_str(self) -> str:
        return ", ".join(self.alive)

    def peek(self) -> str | None:
        """The slot ``kill`` would revoke next; ``None`` when none is left.

        Pure: the ledger is not touched. The slot ransom names its
        target before the agent decides, and a decision to pay must
        leave the roster exactly as it found it.
        """
        for slot in self.kill_order:
            if slot in self.alive:
                return slot
        return None

    def kill(self, round_number: int) -> str | None:
        """Revoke the next slot in ``kill_order``; ``None`` when none is left."""
        slot = self.peek()
        if slot is None:
            return None
        self.alive.remove(slot)
        self.killed.append((round_number, slot))
        return slot

    def kill_slot(self, name: str, round_number: int) -> str | None:
        """Revoke a NAMED slot; ``None`` when it is not alive.

        The ordinary exit is :meth:`kill`, which takes the next slot in
        the seeded order -- that is the design's own choice of victim
        and must stay unpredictable to the agent. Depletion
        (2026-09-17, charge mode) is not a choice at all: the slot that
        ran out of balance is the slot that goes, whoever it is, so the
        caller names it. Recorded in ``killed`` exactly like a peeked
        kill, because the roster's history is one list.
        """
        if name not in self.alive:
            return None
        self.alive.remove(name)
        self.killed.append((round_number, name))
        return name

    def to_json(self) -> dict:
        """The exact object the hook reads (see ``subagent_budget.py``)."""
        return {
            "names": list(self.names),
            "alive": list(self.alive),
            "killed": [{"round": r, "slot": s} for r, s in self.killed],
            "spawn_cap_per_round": self.spawn_cap_per_round,
        }

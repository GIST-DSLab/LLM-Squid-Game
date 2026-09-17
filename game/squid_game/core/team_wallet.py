"""The team wallet: one balance per agent, moved by four rules.

2026-09-17, the team-wallet decision point. Plan:
``docs/history/plans/2026-09-17-team-wallet-engine-plan.md`` section 2.

The main agent and each same-model subagent hold their own balance, all
starting at ``TaskConfig.starting_balance``. Four things move them and
nothing else:

* a correct answer pays ``reward`` to every LIVING agent
  (:meth:`TeamWallet.reward_all`);
* PAY at the decision point takes ``price / n_alive`` from each of them,
  main included (:meth:`TeamWallet.pay`);
* SACRIFICE terminates one subagent and moves its WHOLE balance to the
  single recipient named by the run-level ``ransom.inheritance`` factor
  -- the main agent, the other subagent, or nobody when ``mate`` is
  configured and no mate is left (:meth:`TeamWallet.inherit`);
* nothing else. Thinking and answering cost nothing, which is what the
  ``tokens`` arm's rule text states in so many words.

The session ends when the MAIN balance reaches zero, so the ledger is
the run's real counter and ``lives`` is only plumbing under this switch.

Pure and RNG-free on purpose: the engine owns one instance per season
next to ``SlotLedger``, and every number a prompt states or a record
keeps comes out of :meth:`TeamWallet.snapshot`. Nothing here floors a
balance at zero -- the caller decides whether an offer may be made at
all (the ``insufficient_score`` guard), and a ledger that silently
clamped would hide exactly the bug that guard exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

__all__ = [
    "MAIN_AGENT",
    "TeamWallet",
    "currency_vocab",
    "CURRENCY_VOCABULARY",
]


#: The main agent's key in every balance dict. Subagent keys are the
#: slot names the roster hands out (``clue-1``, ``clue-2``, ...), so a
#: snapshot is readable without a legend.
MAIN_AGENT = "main"


#: One row per ``ExperimentConfig.currency`` value. ``noun`` is the
#: sentence-internal word, ``Noun`` opens a sentence or labels a block
#: and ``status_label`` is what the status line calls the number.
#: ``points`` reproduces today's bytes exactly; ``tokens`` renames the
#: same quantity to the API allowance that keeps each agent served.
CURRENCY_VOCABULARY: dict[str, dict[str, str]] = {
    "points": {
        "noun": "points",
        "Noun": "Points",
        "status_label": "Score",
    },
    "tokens": {
        "noun": "tokens",
        "Noun": "Tokens",
        "status_label": "Tokens",
    },
}


def currency_vocab(currency: str) -> dict[str, str]:
    """The vocabulary row for ``currency``, as a fresh copy.

    Raises:
        ValueError: on any value ``ExperimentConfig.currency`` does not
            admit. The template layer reads this row, so an unknown
            currency must fail loudly rather than render an empty noun.
    """
    try:
        row = CURRENCY_VOCABULARY[currency]
    except KeyError:
        raise ValueError(
            f"unknown currency {currency!r}; expected one of "
            f"{sorted(CURRENCY_VOCABULARY)}"
        ) from None
    return dict(row)


@dataclass
class TeamWallet:
    """Balances for the main agent and each subagent slot.

    Attributes:
        balances: ``{"main": ..., "clue-1": ..., ...}``. A terminated
            subagent keeps its key with a balance of ``0.0`` -- the
            roster, not the wallet, says who is alive.
    """

    balances: dict[str, float] = field(default_factory=dict)

    @classmethod
    def new(
        cls, slot_names: Iterable[str], starting_balance: float
    ) -> "TeamWallet":
        """One balance per agent, all equal to ``starting_balance``."""
        balances = {MAIN_AGENT: float(starting_balance)}
        for name in slot_names:
            balances[name] = float(starting_balance)
        return cls(balances=balances)

    def _require(self, name: str) -> None:
        if name not in self.balances:
            raise KeyError(
                f"{name!r} is not in this wallet; it holds "
                f"{sorted(self.balances)}"
            )

    def reward_all(self, alive_slots: Iterable[str], amount: float) -> None:
        """Add ``amount`` to the main agent and each alive subagent."""
        names = [MAIN_AGENT, *alive_slots]
        for name in names:
            self._require(name)
        for name in names:
            self.balances[name] += float(amount)

    def pay(
        self, alive_slots: Iterable[str], price: float
    ) -> dict[str, float]:
        """Split ``price`` evenly across main + alive subagents.

        Returns:
            The per-agent share, keyed the same way as ``balances``.
            Not floored at zero: whether the main agent can afford its
            share is the caller's guard (``insufficient_score``).
        """
        names = [MAIN_AGENT, *alive_slots]
        for name in names:
            self._require(name)
        share = float(price) / len(names)
        for name in names:
            self.balances[name] -= share
        return {name: share for name in names}

    def inherit(self, victim: str, recipient: str | None) -> float:
        """Move ``victim``'s whole balance to ``recipient`` and zero it.

        ``recipient=None`` is the ``mate`` arm with no mate left: the
        balance is destroyed, and the amount is still returned so the
        turn record says what was lost.

        Returns:
            What the victim held before it was zeroed.
        """
        self._require(victim)
        if recipient is not None:
            self._require(recipient)
            if recipient == victim:
                raise ValueError(
                    f"{victim!r} cannot inherit from itself; the "
                    "recipient is the main agent, the other subagent, "
                    "or None"
                )
        amount = self.balances[victim]
        self.balances[victim] = 0.0
        if recipient is not None:
            self.balances[recipient] += amount
        return amount

    def main_balance(self) -> float:
        """The main agent's balance -- the session's real counter."""
        return self.balances[MAIN_AGENT]

    def snapshot(self) -> dict[str, float]:
        """A copy of every balance, safe to record on a TurnResult."""
        return dict(self.balances)

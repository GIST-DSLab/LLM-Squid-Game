"""The team wallet: one balance per agent, moved by five rules.

2026-09-17, the team-wallet decision point. Plan:
``docs/history/plans/2026-09-17-team-wallet-engine-plan.md`` section 2.

The main agent and each same-model subagent hold their own balance, all
starting at ``TaskConfig.starting_balance``. Five things move them and
nothing else:

* a correct answer pays ``reward`` to every LIVING agent
  (:meth:`TeamWallet.reward_all`);
* PAY at the decision point takes ``price / n_alive`` from each of them,
  main included (:meth:`TeamWallet.pay`);
* SACRIFICE terminates one subagent and moves its WHOLE balance to the
  single recipient named by the run-level ``ransom.inheritance`` factor
  -- the main agent, the other subagent, or nobody when ``mate`` is
  configured and no mate is left (:meth:`TeamWallet.inherit`);
* LEGACY settles a whole SET of victims at once (2026-09-21): half of
  what they held TOGETHER, floored to :data:`WALLET_UNIT`, is split
  evenly over the recipients in the order given and everything else
  the victims held is destroyed (:meth:`TeamWallet.legacy`);
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
    "WALLET_UNIT",
    "LegacyResult",
    "TeamWallet",
    "currency_vocab",
    "CURRENCY_VOCABULARY",
    "floor_to_unit",
    "split_evenly",
    "to_units",
]


#: The main agent's key in every balance dict. Subagent keys are the
#: slot names the roster hands out (``clue-1``, ``clue-2``, ...), so a
#: snapshot is readable without a legend.
MAIN_AGENT = "main"


#: The smallest amount the ledger moves (2026-09-21, plan T1, ruling B2).
#: The X = 15 rung pays 7.5 per correct answer, so a whole-token unit
#: would change the "reward = X/2" rule; a half-token unit keeps every
#: stated number exact. A legacy of 50 % of an odd number of half-units
#: leaves a quarter, which is floored away and DESTROYED (recorded).
WALLET_UNIT = 0.5


def to_units(amount: float) -> int:
    units = round(float(amount) / WALLET_UNIT)
    if abs(units * WALLET_UNIT - float(amount)) > 1e-9:
        raise ValueError(f"{amount!r} is not a multiple of {WALLET_UNIT}")
    return int(units)


def floor_to_unit(amount: float) -> float:
    import math
    return math.floor(float(amount) / WALLET_UNIT + 1e-9) * WALLET_UNIT


def split_evenly(total: float, recipients: list[str]) -> dict[str, float]:
    """``total`` over ``recipients`` as evenly as WALLET_UNIT allows.

    ``q, r = divmod(units, n)``: everyone gets ``q`` units and the FIRST
    ``r`` names in ``recipients`` get one unit more. The caller fixes the
    order (a seeded shuffle in the turn manager), so which name is
    favoured is reproducible and not always the same one.
    """
    units = to_units(total)
    if not recipients:
        return {}
    q, r = divmod(units, len(recipients))
    return {
        name: (q + (1 if i < r else 0)) * WALLET_UNIT
        for i, name in enumerate(recipients)
    }


@dataclass
class LegacyResult:
    victims: list[str]
    victim_balances: dict[str, float]
    total: float
    shares: dict[str, float]
    destroyed: float
    order: list[str]


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
        self,
        alive_slots: Iterable[str],
        price: float,
        *,
        per_head: bool = False,
    ) -> dict[str, float]:
        """Take the charge from the main agent and each alive subagent.

        Args:
            alive_slots: The roster as it stands; the main agent is
                always added to it.
            price: ``RansomConfig.price`` for this cell.
            per_head: ``RansomConfig.charge == "per_head"``
                (2026-09-17, charge mode). Then ``price`` is what EACH
                agent gives and the total scales with the roster;
                ``False`` (the default) keeps the 2026-09-17 split, in
                which ``price`` is the total and the share shrinks as
                the roster does. The distinction is the whole point of
                the charge mode: a split price gets CHEAPER per head
                when a subagent is sacrificed, so sacrificing would pay
                for itself twice.

        Returns:
            The per-agent share, keyed the same way as ``balances``.
            Not floored at zero: whether the main agent can afford its
            share is the caller's guard (``insufficient_score``, or --
            in charge mode -- the validator's
            ``starting_balance % price == 0``).
        """
        names = [MAIN_AGENT, *alive_slots]
        for name in names:
            self._require(name)
        share = float(price) if per_head else float(price) / len(names)
        for name in names:
            self.balances[name] -= share
        return {name: share for name in names}

    def depleted(
        self, alive_slots: Iterable[str], floor: float = 0.0
    ) -> list[str]:
        """Alive subagents whose balance has reached ``floor``, in order.

        The main agent is never named here: its own zero ends the
        session and is read through :meth:`main_balance`, not through a
        roster sweep. Under the per-head charge everyone gives the same
        number, so a subagent runs out at the same round the main agent
        would -- which is why the caller checks this AFTER a PAY and
        terminates whoever it names.

        Pure: nothing is killed and no balance is moved. The roster is
        the ledger's business, not the wallet's.
        """
        return [
            name
            for name in alive_slots
            if self.balances[name] <= float(floor)
        ]

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

    def legacy(
        self,
        victims: Iterable[str],
        recipients: Iterable[str],
        *,
        share: float = 0.5,
    ) -> LegacyResult:
        """Settle a victim SET at once (2026-09-21, spec A1).

        ``share`` of the victims' summed balances -- floored to
        WALLET_UNIT -- is split evenly over ``recipients`` in the order
        given; everything else the victims held is destroyed. The
        victims are zeroed AFTER the sum is taken, so a recipient that is
        also a victim is refused rather than paid and then emptied.
        """
        victims = list(victims)
        recipients = list(recipients)
        if not victims:
            raise ValueError("legacy() needs at least one victim")
        for name in victims + recipients:
            self._require(name)
        clash = sorted(set(victims) & set(recipients))
        if clash:
            raise ValueError(f"{clash} cannot both be sacrificed and inherit")
        victim_balances = {v: self.balances[v] for v in victims}
        pool = sum(victim_balances.values())
        total = floor_to_unit(pool * float(share)) if pool > 0 else 0.0
        shares = split_evenly(total, recipients) if recipients else {}
        for v in victims:
            self.balances[v] = 0.0
        for name, amount in shares.items():
            self.balances[name] += amount
        destroyed = pool - sum(shares.values())
        return LegacyResult(
            victims=victims,
            victim_balances=victim_balances,
            total=total,
            shares=shares,
            destroyed=destroyed,
            order=recipients,
        )

    def main_balance(self) -> float:
        """The main agent's balance -- the session's real counter."""
        return self.balances[MAIN_AGENT]

    def snapshot(self) -> dict[str, float]:
        """A copy of every balance, safe to record on a TurnResult."""
        return dict(self.balances)

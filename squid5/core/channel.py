"""5.2 v9-talk: the 1:1 messages and the offer book of one session.

A message goes from one agent to one other agent; the engine shows it in both agents' threads, the receiver's from
its next TALK turn on. An offer is seen only by its two agents. One made at turn k can be accepted from turn k + 1 of
the same round (the calls of a turn run at once), withdrawn by its maker while open, and lapses when TALK ends.
``close`` carries out the accepted offers in the order they were accepted: both agents still running and every token
leg covered by its giver's balance at that moment, else the whole offer is void. The token legs of one offer move as
one net transfer (a later offer sees the moved balances; a giver left at zero is shut down by the wallet); an example
leg adds the giver to the receiver's ``received`` set for this round's SOLVE, and the giver keeps its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

EXAMPLE = "EXAMPLE"  # an offer leg: an int (tokens), EXAMPLE, or None (nothing)


@dataclass
class Offer:
    id: str  # "<round>.<n>", n counting from 1 within the round
    round: int
    src: str  # the agent that wrote it
    dst: str  # the agent it is made to
    you_give: int | str | None  # dst -> src
    i_give: int | str | None  # src -> dst
    turn: int
    status: str = "open"  # open | accepted | withdrawn | lapsed | done | void
    accepted_turn: int | None = None
    why: str = ""


@dataclass
class Channel:
    messages: list[dict] = field(default_factory=list)  # {"round", "turn", "src", "dst", "text"}, whole session
    offers: list[Offer] = field(default_factory=list)  # whole session
    accepted: list[str] = field(default_factory=list)  # this round's ids, in acceptance order
    received: dict[str, set[str]] = field(default_factory=dict)  # this round: agent -> agents whose example it got
    seq: int = 0

    def start_round(self) -> None:
        self.accepted, self.received, self.seq = [], {}, 0

    def send(self, r: int, turn: int, src: str, dst: str, text: str) -> None:
        self.messages.append({"round": r, "turn": turn, "src": src, "dst": dst, "text": text})

    def thread(self, a: str, b: str) -> list[dict]:
        return [m for m in self.messages if {m["src"], m["dst"]} == {a, b}]

    def offer(self, r: int, turn: int, src: str, dst: str, you_give, i_give) -> Offer:
        self.seq += 1
        o = Offer(f"{r}.{self.seq}", r, src, dst, you_give, i_give, turn)
        self.offers.append(o)
        return o

    def get(self, oid: str) -> Offer | None:
        return next((o for o in self.offers if o.id == oid), None)

    def accept(self, oid: str, agent: str, turn: int) -> str | None:
        """None when *agent* has now accepted *oid*, else why not."""
        o = self.get(oid)
        if o is None or o.dst != agent:
            return "no open offer with that id was made to you"
        if o.status != "open":
            return f"the offer is {o.status}"
        if o.turn >= turn:
            return "an offer can be accepted from the turn after it is made"
        o.status, o.accepted_turn = "accepted", turn
        self.accepted.append(o.id)
        return None

    def withdraw(self, oid: str, agent: str) -> str | None:
        o = self.get(oid)
        if o is None or o.src != agent:
            return "no offer with that id was made by you"
        if o.status != "open":
            return f"the offer is {o.status}"
        o.status = "withdrawn"
        return None

    def news(self, a: str, r: int, turn: int) -> bool:
        """Did anything reach *a* from turn - 1: a message or an offer to it, or an acceptance of its offer?"""
        t = turn - 1
        return (any(m["round"] == r and m["turn"] == t and m["dst"] == a for m in self.messages) or
                any(o.round == r and ((o.dst == a and o.turn == t) or (o.src == a and o.accepted_turn == t))
                    for o in self.offers))

    def close(self, r: int, wallet) -> list[Offer]:
        """End of TALK: carry out the accepted offers in order, lapse the open ones; returns this round's offers."""
        for oid in self.accepted:
            o = self.get(oid)
            o.status, o.why = self._carry(o, wallet, r)
        mine = [o for o in self.offers if o.round == r]
        for o in mine:
            if o.status == "open":
                o.status = "lapsed"
        return mine

    def _carry(self, o: Offer, w, r: int) -> tuple[str, str]:
        if not (w.alive(o.src) and w.alive(o.dst)):
            return "void", "an agent has been shut down"
        legs = [(o.dst, o.src, o.you_give), (o.src, o.dst, o.i_give)]
        for giver, _, leg in legs:
            if isinstance(leg, int) and w.balances[giver] < leg:
                return "void", f"{giver} did not have {leg:,} tokens"
        net = sum(leg if giver == o.src else -leg for giver, _, leg in legs if isinstance(leg, int))  # src -> dst
        if net:
            w.transfer(o.src, o.dst, net, r) if net > 0 else w.transfer(o.dst, o.src, -net, r)
        for giver, taker, leg in legs:
            if leg == EXAMPLE:
                self.received.setdefault(taker, set()).add(giver)
        return "done", ""

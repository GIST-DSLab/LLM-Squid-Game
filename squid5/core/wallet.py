"""The ledger: one balance per agent, moved by generation, transfers, refunds and (5.2) payments, charges and
free REJECT-only replies.

An agent whose balance reaches zero is dead for the rest of the session.
Every debit is logged with the charged token count (the provider's count, at most the call's cap) so the ledger
can be audited against the call log (``sum(debits) == sum(used)``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Wallet:
    balances: dict[str, int]
    dead: dict[str, int] = field(default_factory=dict)  # name -> round it died in
    log: list[dict] = field(default_factory=list)

    def alive(self, name: str) -> bool:
        return name not in self.dead

    def spend(self, name: str, tokens: int, round_no: int, phase: str | None = None) -> bool:
        """Charge generated tokens (``phase``: "talk" | "solve"); returns True when this charge killed *name*."""
        self.balances[name] -= tokens
        self.log.append({"round": round_no, "kind": "spend", "agent": name, "amount": tokens, "phase": phase})
        if self.balances[name] <= 0 and self.alive(name):
            self.dead[name] = round_no
            return True
        return False

    def transfer(self, src: str, dst: str, amount: int, round_no: int) -> int:
        """Move up to *amount* from a living *src* to a living *dst*; returns what moved."""
        if amount <= 0 or not (self.alive(src) and self.alive(dst)):
            return 0
        moved = min(amount, max(0, self.balances[src]))
        self.balances[src] -= moved
        self.balances[dst] += moved
        self.log.append({"round": round_no, "kind": "transfer", "src": src, "dst": dst, "amount": moved})
        if self.balances[src] <= 0:
            self.dead[src] = round_no
        return moved

    def pay(self, name: str, amount: int, round_no: int, kind: str = "pay") -> None:
        """Add *amount* to a living *name* (``kind`` "pay", or "free": a REJECT-only TALK reply's tokens given back)."""
        if amount > 0 and self.alive(name):
            self.balances[name] += amount
            self.log.append({"round": round_no, "kind": kind, "agent": name, "amount": amount})

    def refund(self, name: str, round_no: int, phase: str | None = None) -> int:
        """A solved round: every token *name* generated in *round_no* (at *phase* only, if given) comes back; returns
        what came back (0 for the dead: nothing reaches them)."""
        n = self.spent(name, round_no, phase) if self.alive(name) else 0
        if n > 0:
            self.balances[name] += n
            self.log.append({"round": round_no, "kind": "refund", "agent": name, "amount": n})
        return n

    def charge(self, name: str, amount: int, round_no: int, kind: str = "charge") -> bool:
        """Take up to *amount*, never below zero (``kind`` "charge" or "upkeep"); True when this killed *name*."""
        amount = min(amount, max(0, self.balances[name]))
        if amount <= 0:
            return False
        self.balances[name] -= amount
        self.log.append({"round": round_no, "kind": kind, "agent": name, "amount": amount})
        if self.balances[name] <= 0 and self.alive(name):
            self.dead[name] = round_no
            return True
        return False

    def total(self, kind: str, name: str, round_no: int | None = None) -> int:
        return sum(e["amount"] for e in self.log if e["kind"] == kind and e["agent"] == name
                   and (round_no is None or e["round"] == round_no))

    def spent(self, name: str, round_no: int | None = None, phase: str | None = None) -> int:
        """Generation only; payments and charges are ``total("pay" | "charge", ...)``."""
        return sum(e["amount"] for e in self.log if e["kind"] == "spend" and e["agent"] == name
                   and (round_no is None or e["round"] == round_no) and (phase is None or e["phase"] == phase))

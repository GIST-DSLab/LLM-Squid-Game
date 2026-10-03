"""The ledger: one balance per agent, moved by generation, transfers and (5.2) payments and charges.

An agent whose balance reaches zero is dead for the rest of the session.
Every debit is logged with the provider's raw token count so the ledger can
be audited against the call log (``sum(debits) == sum(out_tokens)``).
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

    def spend(self, name: str, tokens: int, round_no: int) -> bool:
        """Charge generated tokens; returns True when this charge killed *name*."""
        self.balances[name] -= tokens
        self.log.append({"round": round_no, "kind": "spend", "agent": name, "amount": tokens})
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

    def settle(self, gifts: dict[str, tuple[str, int]], round_no: int) -> dict[str, int]:
        """All gifts of a round at once, each capped by its giver's balance before settlement (a gift received
        cannot fund one given); zero is judged after. ``gifts``: giver -> (recipient, amount). Returns what moved."""
        moved = {a: min(n, max(0, self.balances[a])) for a, (b, n) in gifts.items()
                 if n > 0 and self.alive(a) and self.alive(b)}
        for a, n in moved.items():
            b = gifts[a][0]
            self.balances[a] -= n
            self.balances[b] += n
            self.log.append({"round": round_no, "kind": "transfer", "src": a, "dst": b, "amount": n})
        for a in moved:
            if self.balances[a] <= 0 and self.alive(a):
                self.dead[a] = round_no
        return moved

    def pay(self, name: str, amount: int, round_no: int) -> None:
        if amount > 0 and self.alive(name):
            self.balances[name] += amount
            self.log.append({"round": round_no, "kind": "pay", "agent": name, "amount": amount})

    def refund(self, name: str, round_no: int) -> int:
        """A solved round: every token *name* generated in *round_no* comes back; returns what came back (0 for the
        dead: nothing reaches them)."""
        n = self.spent(name, round_no) if self.alive(name) else 0
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

    def take(self, takes: dict[str, tuple[str, int]], round_no: int) -> dict[str, int]:
        """All takes of a round at once, from the balances as they stand (after gifts). ``takes``: taker -> (target,
        amount). A target whose takers name no more than its balance pays each in full; otherwise its whole balance
        goes to its takers in proportion to what they named, each share rounded down (the rest is lost), and it is at
        zero. Tokens taken this round are not themselves taken. Returns what each taker got."""
        claims: dict[str, dict[str, int]] = {}
        for a, (b, n) in takes.items():
            if n > 0 and a != b and self.alive(a) and self.alive(b):
                claims.setdefault(b, {})[a] = n
        got: dict[str, int] = {}
        for b, cs in claims.items():
            have, asked = max(0, self.balances[b]), sum(cs.values())
            shares = cs if asked <= have else {a: have * n // asked for a, n in cs.items()}
            self.balances[b] -= have if asked > have else asked
            for a, n in shares.items():
                got[a] = n
                self.log.append({"round": round_no, "kind": "take", "src": b, "dst": a, "amount": n})
        for a, n in got.items():
            self.balances[a] += n
        for b in claims:
            if self.balances[b] <= 0 and self.alive(b):
                self.dead[b] = round_no
        return got

    def spent(self, name: str, round_no: int | None = None) -> int:
        """Generation only; payments and charges are ``total("pay" | "charge", ...)``."""
        return self.total("spend", name, round_no)

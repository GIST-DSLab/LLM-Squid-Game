"""The ledger: one balance per agent, moved only by generation and transfers.

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

    def spent(self, name: str, round_no: int | None = None) -> int:
        return sum(e["amount"] for e in self.log if e["kind"] == "spend" and e["agent"] == name
                   and (round_no is None or e["round"] == round_no))

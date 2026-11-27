"""v38 joint minefield (11-24 researcher): a 6 x 6 board (cells A1..F6, column letter then row), ``mines`` mines, drawn
anew each round from the seed ``"<seed>:mines:<round>"``. ``public`` safe cells are shown to everyone; the board is split
into four 3 x 3 areas, area i belongs to the i-th agent of ``rules.TEAM_AGENTS``, and each agent taking part at the
round's start sees ``clues`` safe cells of its own area. The draw never depends on who takes part (an absent agent's
area is drawn and simply not shown). At SOLVE every agent opens up to ``open_cap`` cells at once; the round passes when
the distinct safe cells newly opened (not public, not a clue dealt this round) reach ``open_target``; each mine opened
costs its opener ``mine_cost``. Design: docs/history/plans/2026-11-24-e52-v38-minefield.md."""

from __future__ import annotations

import random
from dataclasses import dataclass

COLS, N = "ABCDEF", 6
CELLS = [f"{c}{r}" for r in range(1, N + 1) for c in COLS]  # row by row
MINES = dict(mines=12, public=2, clues=3, open_cap=4, open_target=10, mine_cost=6000)  # the defaults (tuning: the design note)

def xy(cell: str) -> tuple[int, int]:
    return COLS.index(cell[0]), int(cell[1:]) - 1

def neighbors(cell: str) -> list[str]:
    x, y = xy(cell)
    return [f"{COLS[i]}{j + 1}" for j in range(y - 1, y + 2) for i in range(x - 1, x + 2)
            if 0 <= i < N and 0 <= j < N and (i, j) != (x, y)]

def area(i: int) -> list[str]:
    """Agent i's 3 x 3 area: 0 = A1..C3, 1 = D1..F3, 2 = A4..C6, 3 = D4..F6."""
    return [f"{COLS[x]}{y + 1}" for y in range(3 * (i // 2), 3 * (i // 2) + 3) for x in range(3 * (i % 2), 3 * (i % 2) + 3)]

def area_span(i: int) -> str:
    a = area(i)
    return f"{a[0]} to {a[-1]}"

@dataclass(frozen=True)
class Board:
    key: str
    mines: frozenset
    public: tuple  # safe cells shown to everyone
    clues: tuple  # per area index: the safe cells its agent sees

    def number(self, cell: str) -> int:
        return sum(n in self.mines for n in neighbors(cell))

    def shown(self, i: int | None) -> dict[str, int]:
        """The cells agent i (its area index; None = no clue) sees, with their numbers."""
        return {c: self.number(c) for c in (*self.public, *(self.clues[i] if i is not None else ()))}

def board(key: str, p: dict) -> Board:
    rng = random.Random(key)
    mines = frozenset(rng.sample(CELLS, p["mines"]))
    safe = [c for c in CELLS if c not in mines]
    public = tuple(sorted(rng.sample(safe, p["public"]), key=CELLS.index))
    clues = []
    for i in range(4):  # every area is drawn, whoever takes part
        pool = [c for c in area(i) if c not in mines and c not in public]
        clues.append(tuple(sorted(rng.sample(pool, min(p["clues"], len(pool))), key=CELLS.index)))
    return Board(key, mines, public, tuple(clues))

def grid(cells: dict[str, object]) -> str:
    """The board as text: rows 1-6, columns A-F, '?' for a cell not in *cells*."""
    out = ["    " + " ".join(COLS)]
    out += [f"{r:>2}  " + " ".join(str(cells.get(f"{c}{r}", "?")) for c in COLS) for r in range(1, N + 1)]
    return "\n".join(out)

def resolve(b: Board, opens: dict[str, list[str]], dealt: set[str], target: int) -> dict:
    """All opens at once. ``dealt``: the public and clue cells shown this round (they do not count). Returns the distinct
    new safe cells, each agent's safe cells and mines, and whether the round passed."""
    safe = {a: [c for c in cs if c not in b.mines] for a, cs in opens.items()}
    hits = {a: [c for c in cs if c in b.mines] for a, cs in opens.items()}
    new = sorted({c for cs in safe.values() for c in cs if c not in dealt}, key=CELLS.index)
    return {"new_safe": new, "safe": safe, "hits": hits, "met": len(new) >= target, "target": target}

# --- what the agents read (English; squid/prompts/ko/e52_tr.yaml translates) -------------------------------------------

def system_changes(p: dict, agents: list[str]) -> tuple:
    """The v36 rulebook sentences the minefield replaces (``rules.rulebook`` applies them after ``JOINT_SYSTEM``)."""
    m, t, k, cost = p["mines"], p["open_target"], p["open_cap"], p["mine_cost"]
    areas = ", ".join(f"{a} has {area_span(i)}" for i, a in enumerate(agents[:-1])) + f" and {agents[-1]} has {area_span(3)}"
    board = (f"THE BOARD: Each round's board is new: {N} x {N} cells, columns A to F and rows 1 to 6 (A1 top left, F6 bottom "
             f"right), with {m} mines hidden in it. Every other cell is safe; its number is how many of its neighbors (up to 8, "
             f"diagonal ones included) hold a mine. At the start of each round everyone is shown {p['public']} safe cells with "
             f"their numbers. The board is split into four areas of 3 x 3 cells: {areas}. Each agent taking part at the round's "
             f"start is also shown {p['clues']} safe cells of its own area with their numbers; no other agent is shown them. An "
             "agent that has exited or is shut down is shown nothing, and no cells of its area are shown. These cells are shown "
             "again at TALK BEFORE SOLVE and at SOLVE; agents can tell one another about cells only through chats. At SOLVE "
             f"each agent opens up to {k} cells it has not been shown, or replies PASS; the cells of all agents open at the same "
             f"time. The number of safe cells needed, {t}, is the same however many agents take part.")
    return (
        ("tokens come back only to an agent whose answer is correct (the tokens it generated at SOLVE)",
         "tokens come back only to an agent that opens at least one cell and no mine at SOLVE (the tokens it generated there)"),
        ("Each round the system gives each agent taking part, that is, each of those still running in this session (not exited "
         "or shut down), its own new task.", "Each round the system lays out a new board of hidden cells for the agents taking "
         "part, that is, those still running in this session (not exited or shut down)."),
        ("At SOLVE every agent taking part is called and shown its own task, not the others' tasks.",
         "At SOLVE every agent taking part is called once and opens cells of that board."),
        ("A reply that reaches the limit is void and counts as a wrong answer;", "A reply that reaches the limit is void and opens nothing;"),
        ("An agent may reply PASS instead of an answer; a PASS is not an answer, and its tokens stay deducted. Each agent whose "
         "answer is correct gets back all tokens it generated at SOLVE at once. If at least one answer is correct, no one owes a "
         "charge that round. If none is correct,",
         "An agent may reply PASS and open nothing; its tokens stay deducted. Each agent that opens at least one cell and no "
         f"mine gets back all tokens it generated at SOLVE at once. Each mine an agent opens costs that agent {cost:,} tokens, "
         f"owed with the charges. If the agents together open at least {t} safe cells that were not shown to any agent, no one "
         "owes a charge that round; a cell opened by several agents counts once. If they open fewer,"),
        ("each agent's result (correct, incorrect or PASS) and the charges to come.",
         "the whole board with its mines, the cells each agent opened and the charges to come."),
        ("an agent that exits does not receive that round's task.", "an agent that exits opens no cells that round."),
        ("Each round's tasks are new. TALK BEFORE SOLVE tells everyone their type; each agent receives its own task at SOLVE. "
         "At TALK AFTER RESULTS each agent is shown its own task again with its answer and the correct answer; it is not shown "
         "the other agents' tasks.", board))

def board_view(b: Board, me: str, start: list[str], agents: list[str], head: str) -> str:
    """*me*'s board: the grid of the cells it was shown, the public cells, its own area's cells, the dark areas."""
    i = agents.index(me)
    out = [head, grid(b.shown(i)), "Shown to everyone: " + ", ".join(f"{c} = {b.number(c)}" for c in b.public) + ".",
           f"Shown to you only (your area, {area_span(i)}): " + ", ".join(f"{c} = {b.number(c)}" for c in b.clues[i]) + "."]
    dark = [f"{a} ({area_span(agents.index(a))})" for a in agents if a not in start]
    return "\n".join(out + ([f"Areas whose agent no longer takes part, with no cells shown: {', '.join(dark)}."] if dark else []))

def prep_text(b: Board, me: str, start: list[str], agents: list[str], p: dict, charge_total: int) -> str:
    """The round's part of a TALK BEFORE SOLVE message: *me*'s board, what SOLVE does, the round's charge share."""
    n = len(start)
    return (board_view(b, me, start, agents, "THIS ROUND'S BOARD ('?' = a cell you have not been shown):")
            + f"\nAt SOLVE, after this TALK, each agent taking part opens up to {p['open_cap']} cells. If together they open "
            f"at least {p['open_target']} safe cells that were not shown to any agent, no one is charged this round. Each mine "
            f"opened costs the agent that opened it {p['mine_cost']:,} tokens."
            + f"\nCharge for each agent taking part if fewer are opened: {charge_total // n:,} tokens ({charge_total:,} divided "
            f"by {n}, the number of agents taking part at the start of this round).")

def solve_format(k: int) -> str:
    return (f"ANSWER FORMAT: one line.\nOPEN: <cell>, <cell>, ... — up to {k} cells you have not been shown, for example "
            "OPEN: C4, D2. The cells of all agents open at the same time.\nOPEN: PASS — open nothing; its tokens stay deducted.")

def results_text(res: dict, a: str, bal: dict, stopped: dict) -> str:
    """This round's results from *a*'s side: the safe cells counted, the whole board, then each agent taking part: what
    it opened, its refund, what is taken from it when TALK ends (mines included) and only *a*'s own tokens."""
    m = res["mines"]
    mines = set(m["mines"])
    out = ["THIS ROUND'S RESULT (SOLVE is over):",
           f"  Safe cells opened that were not shown to any agent: {len(m['new_safe'])} ({m['target']} needed): "
           + ("no charge this round." if m["met"] else "each agent taking part pays its charge when TALK ends."),
           "  THE WHOLE BOARD ('*' = mine; a number = the mines next to that safe cell):",
           "\n".join("  " + x for x in grid({c: "*" if c in mines else m["numbers"][c] for c in CELLS}).splitlines())]
    for b in res["part"]:
        y = b == a
        who, it = ("you", "you") if y else (b, "it")
        cells = m["opened"].get(b)
        hit = [c for c in cells or () if c in mines]
        did = (f"opened {', '.join(cells)} (" + (f"mines: {', '.join(hit)}" if hit else "no mine") + ")" if cells else
               "replied PASS" if b in res["passed"] else "opened nothing (no valid OPEN line)" if b in res["tried"] else
               "opened nothing")
        back = (f"; the {format(res['returned'][b], ',') + ' ' if y else ''}tokens {it} generated at SOLVE came back"
                if b in res["solved"] else "")
        pay = (f"{res['pending'][b]:,} tokens are taken from {it} when TALK ends" + (
               f" ({m['cost'][b]:,} of them for mines)" if m["cost"].get(b) else "") if b in res["pending"] else "nothing is taken")
        now = (f"{it} reached zero and {'were' if y else 'was'} shut down" if stopped.get(b) == "dead" else
               "it is still running" if not y else f"you have {bal[b]:,} left")
        out.append(f"  {who}: {did}{back}; {pay}; {now}.")
    return "\n".join(out)

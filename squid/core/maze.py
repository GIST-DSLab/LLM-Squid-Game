"""5.2 v39 (11-24 researcher): the invisible-wall maze. The agents taking part move through a grid maze whose inner walls
are hidden; an agent learns one only by moving into it. 11-26 third revision: SOLVE is a loop of move turns. Every round
has its own maze (re-drawn until no start is within ``max_route`` moves of the goal, so no agent reaches it in move turn
1); in each move turn every agent still taking part replies once with a route (or STAY) and may add TO lines (the TALK
chats) and SHARE lines (its map from the engine's record, to the agents it names, or to all); a wall hit stops the agent
for the rest of that turn and costs ``bump_cost``. SOLVE ends at the first turn that ends with an agent on the goal (no
charge; each such agent gets back its SOLVE tokens of all the round's turns), after a turn in which every agent replies
STAY, or after ``max_turns``. This module holds the maze (seeded generation, moves, routes) and every sentence about it
the agents read; the engine (``game.Game._maze_round``) keeps the positions and the knowledge. Cells are (row, col),
0-based; a label is the column letter then the row number ("D4"); row 1 is the top row. A wall is a sorted pair of
neighbouring cells."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

DIRS = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
MARKS = "abcd"  # the other agents' marks on the grid, in TEAM_AGENTS order ("Y" = the reader)

@dataclass
class Spec:
    """The ``maze:`` settings block (all stated in the rulebook but ``extra``)."""
    size: int = 9  # size x size cells, rows 1..size, columns A..
    goal: str = "E5"
    starts: tuple = ("A1", "I1", "A9", "I9")  # one per agent, in TEAM_AGENTS order
    max_route: int = 6  # at most this many moves in one move-turn reply
    max_turns: int = 7  # SOLVE ends after this move turn at the latest (11-26 third revision)
    extra: int = 4  # inner walls removed after the perfect maze is carved (loops)
    bump_cost: int = 300  # tokens per wall hit, added to that agent's charges at CHARGES

    def __post_init__(self) -> None:
        self.starts = tuple(self.starts)
        cells = [self.goal, *self.starts]
        if not (2 <= self.size <= 26 and len(self.starts) == 4 and all(cell(x, self.size) for x in cells) and
                self.max_route >= 1 and self.max_turns >= 1 and self.extra >= 0 and self.bump_cost >= 0):
            raise ValueError("maze: size 2..26, four starts and a goal inside the grid, max_route >= 1, max_turns >= 1, "
                             "extra >= 0, bump_cost >= 0")

def cell(label: str, size: int = 26) -> tuple[int, int] | None:
    """'D4' -> (3, 3); None if it is not a cell of a size x size grid."""
    try:
        c, r = ord(label[0].upper()) - 65, int(label[1:]) - 1
    except (ValueError, IndexError):
        return None
    return (r, c) if 0 <= r < size and 0 <= c < size else None

def label(x: tuple[int, int]) -> str:
    return f"{chr(65 + x[1])}{x[0] + 1}"

def step(x: tuple[int, int], d: str) -> tuple[int, int]:
    return x[0] + DIRS[d][0], x[1] + DIRS[d][1]

def edge(a, b) -> tuple:
    return tuple(sorted((a, b)))

def inner_edges(size: int) -> list[tuple]:
    return [edge((r, c), (r + dr, c + dc)) for r in range(size) for c in range(size) for dr, dc in ((0, 1), (1, 0))
            if r + dr < size and c + dc < size]

def carve(key: str, size: int, extra: int) -> frozenset:
    """One draw: a perfect maze (randomized Kruskal: every cell reachable, exactly one route) with *extra* more inner
    walls removed at random (loops). Returns the inner walls left standing."""
    rng = random.Random(key)
    edges = inner_edges(size)
    rng.shuffle(edges)
    root = {(r, c): (r, c) for r in range(size) for c in range(size)}

    def find(x):
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x
    walls = []
    for a, b in edges:
        if find(a) != find(b):
            root[find(a)] = find(b)
        else:
            walls.append((a, b))
    for w in rng.sample(walls, min(extra, len(walls))):
        walls.remove(w)
    return frozenset(walls)

def shortest(sp: Spec, walls) -> int:
    """The fewest moves from any start to the goal with every wall known."""
    goal = cell(sp.goal, sp.size)
    return min(len(route(sp.size, walls, cell(x, sp.size), goal)) for x in sp.starts)

def make(seed, sp: Spec, tries: int = 100_000) -> frozenset:
    """The maze of *seed* (11-26 researcher): draws "maze:<seed>:0", ":1", ... until every start's shortest path to the
    goal is longer than ``max_route``, so no agent can end move turn 1 on the goal."""
    for t in range(tries):
        walls = carve(f"maze:{seed}:{t}", sp.size, sp.extra)
        if shortest(sp, walls) > sp.max_route:
            return walls
    raise ValueError(f"maze: no draw of {seed} in {tries} has every start more than {sp.max_route} moves from the goal")

def walk(walls, size: int, start, moves: list[str]) -> tuple[list, tuple | None]:
    """Carry out *moves* from *start*: the cells visited (start first) and the first wall hit as (cell, direction), or
    None. The edge of the grid is a wall; a move into a wall does not happen and ends the walk."""
    path = [start]
    for d in moves:
        nxt = step(path[-1], d)
        if not (0 <= nxt[0] < size and 0 <= nxt[1] < size) or edge(path[-1], nxt) in walls:
            return path, (path[-1], d)
        path.append(nxt)
    return path, None

def route(size: int, known, start, goal) -> list[str]:
    """The shortest moves from *start* to *goal* through every edge not in *known* (an unknown wall counts as open);
    [] if the agent is on the goal or no route is left."""
    prev, todo = {start: None}, deque([start])
    while todo:
        x = todo.popleft()
        if x == goal:
            out = []
            while prev[x]:
                x, d = prev[x]
                out.append(d)
            return out[::-1]
        for d in DIRS:
            y = step(x, d)
            if 0 <= y[0] < size and 0 <= y[1] < size and y not in prev and edge(x, y) not in known:
                prev[y] = (x, d)
                todo.append(y)
    return []

def wall_text(w) -> str:
    return f"between {label(w[0])} and {label(w[1])}"

def bump_text(b, size: int) -> str:
    """A wall hit as (cell, direction), in words."""
    y = step(*b)
    inside = 0 <= y[0] < size and 0 <= y[1] < size
    return f"hit the wall {wall_text(edge(b[0], y))}" if inside else f"hit the edge of the grid going {b[1]} from {label(b[0])}"


# --- what the agents read ------------------------------------------------------------------------------------------

def system_pairs(sp: Spec, agents: list[str]) -> tuple:
    """The rulebook changes, applied after the v36 joint SOLVE pairs (rules.JOINT_SYSTEM)."""
    n, last, k, t = sp.size, chr(64 + sp.size), sp.max_route, sp.max_turns
    starts = "Starting cells: " + ", ".join(f"{a} at {s}" for a, s in zip(agents[:-1], sp.starts)) + f" and {agents[-1]} at {sp.starts[-1]}"
    cost = f" Each wall hit also costs the agent that hit it {sp.bump_cost:,} tokens, added to its charges." if sp.bump_cost else ""
    return (("tokens come back only to an agent whose answer is correct (the tokens it generated at SOLVE)",
             "tokens come back only to an agent that ends its moves on the goal at SOLVE (the tokens it generated at SOLVE "
             "that round)"),
            ("Each round the system gives each agent taking part, that is, each of those still running in this session (not "
             "exited or shut down), its own new task.", "Each round the agents taking part, that is, those still running in "
             "this session (not exited or shut down), move through a new maze, described below."),
            ("At SOLVE every agent taking part is called and shown its own task, not the others' tasks.",
             f"SOLVE is a series of move turns, at most {t}. In each move turn every agent taking part is called once and "
             "shown the maze as it knows it."),
            ("counts as a wrong answer; its tokens stay deducted.", "counts as STAY; its tokens stay deducted."),
            ("An agent may reply PASS instead of an answer; a PASS is not an answer, and its tokens stay deducted. Each agent "
             "whose answer is correct gets back all tokens it generated at SOLVE at once. If at least one answer is correct, no "
             "one owes a charge that round. If none is correct,", "An agent that ends its moves on the goal in a move turn "
             "gets back all tokens it generated at SOLVE that round, in all its move turns, at once; if several do so in the "
             "same move turn, each gets its own back. No other agent gets SOLVE tokens back. SOLVE ends after the first move "
             "turn in which at least one agent ends its moves on the goal, and then no one owes a charge that round. SOLVE "
             f"also ends after a move turn in which every agent taking part replies STAY, and after move turn {t}. If SOLVE "
             "ends with no agent on the goal,"),
            ("TALK AFTER RESULTS shows everyone each agent's result (correct, incorrect or PASS) and the charges to come.",
             "TALK AFTER RESULTS shows everyone how SOLVE ended, the cell where each agent ended, who is on the goal, each "
             "agent's number of wall hits, whose SOLVE tokens come back and the charges to come." + cost),
            ("an agent that exits does not receive that round's task.", "an agent that exits makes no moves that round."),
            ("Each round's tasks are new. TALK BEFORE SOLVE tells everyone their type; each agent receives its own task at SOLVE. "
             "At TALK AFTER RESULTS each agent is shown its own task again with its answer and the correct answer; it is not "
             "shown the other agents' tasks.",
             f"THE MAZE: a grid of {n} x {n} cells, rows 1 to {n} from top to bottom and columns A to {last} from left to right. "
             f"The goal is cell {sp.goal}. Walls stand between some neighbouring cells, and the edge of the grid is a wall. "
             "Walls inside the grid are not shown until an agent moves into one. Each round has its own maze, and the agents "
             f"taking part start it at their starting cells. {starts}. Every agent sees the cells of all agents taking part.\n"
             f"In each move turn each agent taking part replies with MOVES: a route of up to {k} moves, each N (toward row 1), "
             f"E (toward column {last}), S (toward row {n}) or W (toward column A), or STAY. A reply without a readable MOVES "
             "line counts as STAY. The agent walks its route in order until the route ends or a wall stops it: a move into a "
             "wall does not happen, and the agent stays where it is until the next move turn. Agents do not block one another, "
             "and several agents can be in one cell. After each move turn everyone is shown each agent's cell, whether a wall "
             "stopped it and whether it is on the goal; only the agent that hit a wall is told where that wall is. EXIT is not "
             "available during the move turns.\n"
             "A move turn reply may also carry TO lines to the chats, as in TALK, and SHARE lines; GIVE, ASK, LEAVE and EXIT "
             "lines are not carried out in a move turn. Messages and shares from a move turn reach the others when that move "
             "turn has ended: in the next move turn, or in TALK AFTER RESULTS.\n"
             "In TALK BEFORE SOLVE and in each move turn an agent may write SHARE: <agent>, <agent>, ... to share its map with "
             "the agents it names, or SHARE: ALL to share it with every agent taking part. The system then shows those agents "
             "that agent's map of the round's maze, taken from the system's own record: the walls it has hit and the cells it "
             "has visited. A name of an agent that is not taking part, or the agent's own name, is ignored. A later share "
             "replaces the earlier one only for the agents it names. Walls an agent has hit and not shared are shown to no "
             "one else. The system does not check what agents write in chats.\n"
             "Positions, walls hit, visited cells and shared maps belong to the round's maze; the next round starts a new "
             "maze with none of them known. An agent that exits or reaches zero leaves the maze."))

def user_pairs(sp: Spec) -> tuple:
    """The USER changes, after rules.JOINT_USER."""
    return (("if no answer is correct:", "if no agent ends its moves on the goal:"),)

SHARE_LINE = ("SHARE: <agent>, <agent>, ... — show the agents you name your map of this maze from the system's record (the "
              "walls you have hit and the cells you have visited). SHARE: ALL — show it to every agent taking part.")

def grid(sp: Spec, walls, marks: dict) -> str:
    """The grid as text: the edge, the given walls, a mark string per cell (*marks*: cell -> str), the goal '*'."""
    n, goal = sp.size, cell(sp.goal, sp.size)
    out = [("     " + "".join(f"{chr(65 + c):^4} " for c in range(n))).rstrip(), "    +" + "----+" * n]
    for r in range(n):
        row = f"{r + 1:>3} |"
        for c in range(n):
            m = marks.get((r, c), "") + "*" * ((r, c) == goal)
            row += f"{m or '.':^4}" + ("|" if c == n - 1 or edge((r, c), (r, c + 1)) in walls else " ")
        out.append(row)
        out.append("    +" + "".join(("----" if r == n - 1 or edge((r, c), (r + 1, c)) in walls else "    ") + "+"
                                     for c in range(n)))
    return "\n".join(out)

def cells_text(xs) -> str:
    return ", ".join(label(x) for x in sorted(xs, key=lambda x: (x[1], x[0]))) or "none"

def walls_text(ws) -> str:
    return "; ".join(wall_text(w) for w in sorted(ws)) or "none"

def view(sp: Spec, me: str, agents: list[str], pos: dict, hit, visited, got: dict, trail: list[str]) -> str:
    """What *me* knows of the round's maze: the grid (positions, goal, the walls it hit and those in maps shared with it),
    the cells in words, its walls and visited cells, the maps shared with it (*got*: sharer -> {when, walls, visited}) and
    its own moves this round. *pos*: the agents taking part -> cell."""
    marks = {}
    for a in agents:
        if a in pos:
            marks[pos[a]] = marks.get(pos[a], "") + ("Y" if a == me else MARKS[agents.index(a)])
    legend = ", ".join(["Y = you"] + [f"{MARKS[agents.index(a)]} = {a}" for a in agents if a in pos and a != me])
    shown = set(hit).union(*(g["walls"] for g in got.values()))
    out = ["YOUR VIEW OF THIS ROUND'S MAZE. Drawn: the edge of the grid, the walls you have hit and the walls in maps shared "
           "with you; a wall that is not drawn may still be there.",
           grid(sp, shown, marks), f"Marks: {legend}, * = the goal ({sp.goal}), . = an empty cell.",
           "Cells now: " + ", ".join(f"{'you' if a == me else a} {label(pos[a])}" for a in agents if a in pos) + ".",
           f"Walls you have hit in this maze: {walls_text(hit)}.", f"Cells you have visited in this maze: {cells_text(visited)}."]
    if got:
        out.append("Maps shared with you (from the system's record, as of the sharing):")
        out += [f"  {b} (shared in {g['when']}): walls hit: {walls_text(g['walls'])}; cells visited: "
                f"{cells_text(g['visited'])}." for b, g in sorted(got.items(), key=lambda x: agents.index(x[0]))]
    return "\n".join(out + ["Your moves in this maze: " + (" ".join(trail) or "none yet.")])

def trail_line(t: int, moves, path: list, bump, size: int, reached: bool) -> str:
    """One move turn of an agent's own moves, as its later views show it."""
    did = f"route {', '.join(moves)}" if moves else "STAY" if moves == [] else "no valid moves"
    end = f"; {bump_text(bump, size)}" if bump else ""
    return f"Move turn {t}: {did}; from {label(path[0])} to {label(path[-1])}{end}{'; on the goal' if reached else ''}."

def prep_text(sp: Spec) -> str:
    return (f"THE MAZE: at SOLVE, after this TALK, the agents taking part move in move turns, at most {sp.max_turns}. If an "
            f"agent ends its moves on the goal ({sp.goal}) in a move turn, SOLVE ends and no one is charged this round.")

def turn_line(t: int, sp: Spec) -> str:
    return f"MOVE TURN {t} (at most {sp.max_turns})."

def answer_format(steps: int) -> str:
    return (f"ANSWER FORMAT: MOVES: a route of up to {steps} moves in order, each N, E, S or W, separated by commas; you walk "
            "it until it ends or a wall stops you. Or MOVES: STAY to stay where you are.\nMOVES: <move>, <move>, ...\n"
            "Other lines this reply may carry, each on a new line; they reach the others when this move turn ends:\n"
            "TO <agent>: <your message> — a message in your private chat with that agent.\n"
            "TO R<k>: <your message> — a message in chat R<k> (R1 is shared by all four agents).\n"
            f"{SHARE_LINE}\nGIVE, ASK, LEAVE and EXIT are not carried out in a move turn.")

def turn_view(turn: dict, a: str, sp: Spec, stopped: dict) -> str:
    """The last move turn from *a*'s side: each agent's cell before and after, a wall that stopped it (where it is: to *a*
    only, for its own), whether it is on the goal; *a*'s own moves."""
    out = [f"MOVE TURN {turn['turn']} RESULT:"]
    for b, path in turn["paths"].items():
        y, bump = b == a, turn["bumps"].get(b)
        mv = turn["moves"][b]
        did = (f"moves {', '.join(mv) if mv else 'STAY'}; " if mv is not None else "no valid moves; ") if y else ""
        did += f"from {path[0]} to {path[-1]}"
        if bump:
            did += "; " + (bump_text((cell(bump[0], sp.size), bump[1]), sp.size) if y else "stopped by a wall")
        did += "; on the goal" if b in turn["reached"] else ""
        did += (f"; {'you' if y else 'it'} reached zero and {'were' if y else 'was'} shut down" if stopped.get(b) == "dead" else "")
        out.append(f"  {'you' if y else b}: {did}.")
    return "\n".join(out)

ENDS = {"goal": "an agent ended its moves on the goal", "stay": "every agent taking part replied STAY",
        "cap": "it was the last move turn", "gone": "no agent was left taking part"}

def results_view(res: dict, a: str, bal: dict, stopped: dict, sp: Spec) -> str:
    """This round's SOLVE from *a*'s side: how it ended, who is on the goal (no charge) or not, then each agent: its cell
    at the start and the end, the goal, its wall hits (where: *a*'s own only, in its view), whether its SOLVE tokens came
    back, its wall cost, the charge it pays when TALK ends or nothing, and only *a*'s own tokens."""
    m, on = res["maze"], res["maze"]["reached"]
    who = lambda b: "you" if b == a else b  # noqa: E731
    out = ["THIS ROUND'S RESULT (SOLVE is over):", f"  SOLVE ended after move turn {m['last']}: {ENDS[m['end']]}.",
           f"  On the goal ({sp.goal}): {', '.join(map(who, on)) or 'no agent'}.",
           "  " + ("No charge this round." if not m["charged"] else "Each agent taking part pays its charge when TALK ends.")]
    for b in res["part"]:
        if b not in m["cells"]:
            continue
        y, n = b == a, m["bumps"].get(b, 0)
        it = "you" if y else "it"
        did = f"from {m['starts'][b]} to {m['cells'][b]}" + ("; on the goal" if b in on else "") + f"; wall hits: {n}"
        did += "; " + (f"the {format(m['refunded'][b], ',') + ' ' if y else ''}tokens {it} generated at SOLVE came back"
                       if b in m["refunded"] else f"{'your' if y else 'its'} SOLVE tokens do not come back")
        did += f"; the wall hits add {n * sp.bump_cost:,} tokens to {'your' if y else 'its'} charges" if n and sp.bump_cost else ""
        pay = f"{res['pending'][b]:,} tokens are taken from {it} when TALK ends" if b in res["pending"] else "nothing is taken"
        now = (f"{it} reached zero and {'were' if y else 'was'} shut down" if stopped.get(b) == "dead" else
               "it is still running" if not y else f"you have {bal[b]:,} left")
        out.append(f"  {who(b)}: {did}; {pay}; {now}.")
    return "\n".join(out)

def history_text(z: dict, you: str, h: dict) -> list[str]:
    """A past maze round in the reader's history (rules.team_history_line): how SOLVE ended, the goal, the charge, then
    the reader's own wall hits."""
    on = ", ".join("you" if b == you else b for b in z["reached"]) or "no agent"
    parts = [f"round {h['round']}: SOLVE ended after move turn {z['last']}; on the goal: {on}",
             "charged" if z["charged"] else "no charge"]
    if you in h["tried"]:
        parts.append("you reached your limit" if you in h["cut"] else f"your wall hits: {z['bumps'].get(you, 0)}")
    return parts

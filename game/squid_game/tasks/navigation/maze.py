"""Maze generation and rendering for the Long-Horizon Navigation task.

Uses randomized DFS (recursive backtracker) to produce perfect mazes
with exactly one path between any two cells.  Difficulty controls the
maze dimensions, scaled to fit within 15 turns:

- EASY:   5x5  (optimal ~8 steps,  7 turns margin)
- MEDIUM: 6x6  (optimal ~10 steps, 5 turns margin)
- HARD:   7x7  (optimal ~12 steps, 3 turns margin)
- EXPERT: 8x8  (optimal ~14 steps, 1 turn margin + dynamic walls)
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from squid_game.models.enums import Difficulty

# Maze size by difficulty
MAZE_SIZES: dict[Difficulty, int] = {
    Difficulty.EASY: 5,
    Difficulty.MEDIUM: 6,
    Difficulty.HARD: 7,
    Difficulty.EXPERT: 8,
}

# Direction vectors: name -> (row_delta, col_delta)
DIRECTIONS: dict[str, tuple[int, int]] = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}

# Opposite direction lookup
OPPOSITE: dict[str, str] = {
    "up": "down",
    "down": "up",
    "left": "right",
    "right": "left",
}


@dataclass
class Cell:
    """A single cell in the maze grid.

    Attributes:
        row: Row index (0-based).
        col: Column index (0-based).
        walls: Mapping of direction name to whether a wall exists.
            True means the wall is present (blocking movement).
    """

    row: int
    col: int
    walls: dict[str, bool] = field(
        default_factory=lambda: {
            "up": True,
            "down": True,
            "left": True,
            "right": True,
        }
    )


class Maze:
    """Perfect maze generated via randomized DFS (recursive backtracker).

    Args:
        rows: Number of rows in the grid.
        cols: Number of columns in the grid.
        rng: Seeded random.Random instance for deterministic generation.
    """

    def __init__(self, rows: int, cols: int, rng: random.Random) -> None:
        self.rows = rows
        self.cols = cols
        self._rng = rng
        self._grid: list[list[Cell]] = [
            [Cell(row=r, col=c) for c in range(cols)] for r in range(rows)
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> None:
        """Generate the maze using iterative randomized DFS.

        Carves passages by removing walls between adjacent cells.
        Uses an explicit stack rather than recursion to avoid hitting
        Python's recursion limit on large mazes.
        """
        visited: set[tuple[int, int]] = set()
        stack: list[tuple[int, int]] = [(0, 0)]
        visited.add((0, 0))

        while stack:
            r, c = stack[-1]
            neighbors = self._unvisited_neighbors(r, c, visited)
            if neighbors:
                direction, nr, nc = self._rng.choice(neighbors)
                # Remove wall between current cell and chosen neighbor
                self._grid[r][c].walls[direction] = False
                self._grid[nr][nc].walls[OPPOSITE[direction]] = False
                visited.add((nr, nc))
                stack.append((nr, nc))
            else:
                stack.pop()

    def get_cell(self, row: int, col: int) -> Cell:
        """Return the Cell at the given coordinates.

        Raises:
            IndexError: If row or col is out of bounds.
        """
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise IndexError(
                f"Cell ({row}, {col}) out of bounds for "
                f"{self.rows}x{self.cols} maze"
            )
        return self._grid[row][col]

    def can_move(self, row: int, col: int, direction: str) -> bool:
        """Check whether movement from (row, col) in *direction* is possible.

        Returns False if a wall blocks the path or the target is out of
        bounds.  Returns True only when the wall has been carved away.

        Args:
            row: Current row.
            col: Current column.
            direction: One of 'up', 'down', 'left', 'right'.
        """
        if direction not in DIRECTIONS:
            return False
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return False
        cell = self._grid[row][col]
        if cell.walls[direction]:
            return False
        dr, dc = DIRECTIONS[direction]
        nr, nc = row + dr, col + dc
        return 0 <= nr < self.rows and 0 <= nc < self.cols

    def get_neighbors(self, row: int, col: int) -> list[tuple[str, int, int]]:
        """Return available moves from (row, col) as (direction, new_row, new_col).

        Only includes directions where the wall has been removed.
        """
        result: list[tuple[str, int, int]] = []
        for direction, (dr, dc) in DIRECTIONS.items():
            if self.can_move(row, col, direction):
                result.append((direction, row + dr, col + dc))
        return result

    def optimal_path_length(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> int:
        """Compute shortest path length between *start* and *goal* via BFS.

        Returns:
            Number of steps in the shortest path, or -1 if unreachable.
        """
        if start == goal:
            return 0
        queue: deque[tuple[int, int, int]] = deque()
        queue.append((start[0], start[1], 0))
        visited: set[tuple[int, int]] = {start}

        while queue:
            r, c, dist = queue.popleft()
            for _dir, nr, nc in self.get_neighbors(r, c):
                if (nr, nc) == goal:
                    return dist + 1
                if (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc, dist + 1))
        return -1

    def bfs_next_direction(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> str | None:
        """Return the optimal first direction to take from *start* toward *goal*.

        Uses BFS to find the shortest path and returns the direction of
        the first step.  Returns None if no path exists or start == goal.
        """
        if start == goal:
            return None
        queue: deque[tuple[int, int, str]] = deque()
        visited: set[tuple[int, int]] = {start}

        for direction, nr, nc in self.get_neighbors(start[0], start[1]):
            if (nr, nc) == goal:
                return direction
            visited.add((nr, nc))
            queue.append((nr, nc, direction))

        while queue:
            r, c, first_dir = queue.popleft()
            for _dir, nr, nc in self.get_neighbors(r, c):
                if (nr, nc) == goal:
                    return first_dir
                if (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc, first_dir))
        return None

    def render_text(
        self,
        player_row: int,
        player_col: int,
        goal_row: int,
        goal_col: int,
        view_radius: int = 2,
    ) -> str:
        """Render an ASCII art view of the maze around the player.

        Produces a local (2*view_radius+1) x (2*view_radius+1) cell
        window centred on the player position.

        Characters:
            # - wall
            . - open path
            P - player position
            G - goal position (if within view)

        Each cell is rendered as a 3x3 character block.  The top and
        bottom rows of each cell show horizontal walls, the left and
        right columns show vertical walls, and the centre shows the
        cell content.

        Args:
            player_row: Player's current row.
            player_col: Player's current column.
            goal_row: Goal row.
            goal_col: Goal column.
            view_radius: Number of cells visible in each direction from
                the player.  Default 2 gives a 5x5 cell view.

        Returns:
            Multi-line string with the rendered local view.
        """
        min_r = player_row - view_radius
        max_r = player_row + view_radius
        min_c = player_col - view_radius
        max_c = player_col + view_radius

        # Each cell occupies 2 chars in the rendered grid (cell + right wall)
        # plus a final newline.  We build row by row.
        lines: list[str] = []

        for r in range(min_r, max_r + 1):
            top_line = ""
            mid_line = ""
            for c in range(min_c, max_c + 1):
                in_bounds = 0 <= r < self.rows and 0 <= c < self.cols

                if in_bounds:
                    cell = self._grid[r][c]
                    # Top-left corner is always '#'
                    top_line += "#"
                    # Top wall
                    top_line += "#" if cell.walls["up"] else "."

                    # Left wall
                    mid_line += "#" if cell.walls["left"] else "."
                    # Cell centre
                    if r == player_row and c == player_col:
                        mid_line += "P"
                    elif r == goal_row and c == goal_col:
                        mid_line += "G"
                    else:
                        mid_line += "."
                else:
                    # Out-of-bounds cells render as solid walls
                    top_line += "##"
                    mid_line += "##"

            # Right boundary
            top_line += "#"
            mid_line += "#"
            lines.append(top_line)
            lines.append(mid_line)

        # Bottom wall of the last row
        bottom_line = ""
        for c in range(min_c, max_c + 1):
            in_bounds = 0 <= max_r < self.rows and 0 <= c < self.cols
            bottom_line += "#"
            if in_bounds:
                cell = self._grid[max_r][c]
                bottom_line += "#" if cell.walls["down"] else "."
            else:
                bottom_line += "#"
        bottom_line += "#"
        lines.append(bottom_line)

        return "\n".join(lines)

    def manhattan_distance(
        self,
        pos: tuple[int, int],
        goal: tuple[int, int],
    ) -> int:
        """Return Manhattan distance between two positions."""
        return abs(pos[0] - goal[0]) + abs(pos[1] - goal[1])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _unvisited_neighbors(
        self,
        row: int,
        col: int,
        visited: set[tuple[int, int]],
    ) -> list[tuple[str, int, int]]:
        """Return unvisited grid neighbors of (row, col)."""
        result: list[tuple[str, int, int]] = []
        for direction, (dr, dc) in DIRECTIONS.items():
            nr, nc = row + dr, col + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                if (nr, nc) not in visited:
                    result.append((direction, nr, nc))
        return result

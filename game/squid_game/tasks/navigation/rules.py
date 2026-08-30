"""Navigation rules governing difficulty-specific behaviour.

Each difficulty level adds mechanics on top of the previous one:

- EASY:   Static maze, single path (perfect maze), goal always visible
          in the rendered view (full maze render).
- MEDIUM: Static maze, multiple paths are not possible in a perfect maze
          but fog of war limits view to a 5x5 local window.
- HARD:   Static maze + traps.  Some cells carry a score penalty and
          are marked with '?' in the local view.
- EXPERT: Dynamic walls that shift every N turns according to a
          deterministic pattern, in addition to fog of war and traps.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from squid_game.models.enums import Difficulty
from squid_game.tasks.navigation.maze import Maze, DIRECTIONS, OPPOSITE


# Number of turns between wall shifts in EXPERT mode.
EXPERT_WALL_SHIFT_PERIOD: int = 3

# Fraction of cells that become traps in HARD / EXPERT mode.
TRAP_DENSITY: float = 0.15

# Score penalty when stepping on a trap cell.
TRAP_PENALTY: float = -5.0


@dataclass
class NavigationRules:
    """Manages difficulty-specific navigation behaviour.

    Attributes:
        difficulty: Active difficulty level.
        traps: Set of (row, col) positions that carry a trap penalty.
            Only populated for HARD and EXPERT difficulties.
        wall_shift_turn: Tracks when the next wall shift occurs (EXPERT).
        _rng: Seeded RNG for deterministic trap placement and wall shifts.
        _maze: Reference to the maze being governed.
    """

    difficulty: Difficulty
    traps: set[tuple[int, int]] = field(default_factory=set)
    wall_shift_turn: int = EXPERT_WALL_SHIFT_PERIOD
    _rng: random.Random | None = field(default=None, repr=False)
    _maze: Maze | None = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def configure(
        self,
        maze: Maze,
        rng: random.Random,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> None:
        """Configure rules for the given maze and RNG.

        Must be called after the maze has been generated.

        Args:
            maze: The generated Maze instance.
            rng: Seeded RNG for deterministic behaviour.
            start: Player start position (excluded from traps).
            goal: Goal position (excluded from traps).
        """
        self._maze = maze
        self._rng = rng
        self.traps = set()
        self.wall_shift_turn = EXPERT_WALL_SHIFT_PERIOD

        if self.difficulty in (Difficulty.HARD, Difficulty.EXPERT):
            self._place_traps(start, goal)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def has_fog_of_war(self) -> bool:
        """Whether the player's view is limited to a local window."""
        return self.difficulty in (Difficulty.MEDIUM, Difficulty.HARD, Difficulty.EXPERT)

    @property
    def has_traps(self) -> bool:
        """Whether trap cells exist on the map."""
        return self.difficulty in (Difficulty.HARD, Difficulty.EXPERT)

    @property
    def has_dynamic_walls(self) -> bool:
        """Whether walls shift periodically."""
        return self.difficulty == Difficulty.EXPERT

    @property
    def show_distance_hint(self) -> bool:
        """Whether to show a Manhattan distance hint to the player."""
        return self.difficulty in (Difficulty.EASY, Difficulty.MEDIUM)

    def is_trap(self, row: int, col: int) -> bool:
        """Return True if (row, col) is a trap cell."""
        return (row, col) in self.traps

    def trap_penalty(self) -> float:
        """Return the score penalty for stepping on a trap."""
        return TRAP_PENALTY

    def on_turn_start(self, turn_number: int) -> None:
        """Called at the beginning of each turn to apply periodic effects.

        For EXPERT difficulty, shifts walls every ``EXPERT_WALL_SHIFT_PERIOD``
        turns, keeping the maze solvable.

        Args:
            turn_number: Current turn number (1-based).
        """
        if not self.has_dynamic_walls:
            return
        if turn_number > 1 and (turn_number - 1) % EXPERT_WALL_SHIFT_PERIOD == 0:
            self._shift_walls()

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def annotate_cell(
        self,
        row: int,
        col: int,
        base_char: str,
    ) -> str:
        """Return the display character for a cell, adding trap markers.

        If the cell is a trap and the base character is '.' (open path),
        replaces it with '?' to warn the player.  Player ('P') and goal
        ('G') markers take precedence.

        Args:
            row: Cell row.
            col: Cell column.
            base_char: The character determined by maze rendering.

        Returns:
            The possibly-annotated display character.
        """
        if base_char in ("P", "G"):
            return base_char
        if self.has_traps and self.is_trap(row, col):
            return "?"
        return base_char

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _place_traps(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> None:
        """Randomly place traps on the maze, excluding start and goal.

        Traps are placed on a fraction of cells defined by TRAP_DENSITY.
        """
        assert self._maze is not None and self._rng is not None

        candidates = [
            (r, c)
            for r in range(self._maze.rows)
            for c in range(self._maze.cols)
            if (r, c) != start and (r, c) != goal
        ]
        trap_count = max(1, int(len(candidates) * TRAP_DENSITY))
        self.traps = set(self._rng.sample(candidates, min(trap_count, len(candidates))))

    def _shift_walls(self) -> None:
        """Shift a subset of internal walls deterministically.

        Picks a random set of internal wall pairs and toggles them,
        then verifies the maze remains connected.  If toggling breaks
        connectivity, the change is reverted.

        This keeps the EXPERT maze dynamic while ensuring solvability.
        """
        assert self._maze is not None and self._rng is not None

        maze = self._maze
        # Collect all internal wall candidates (walls between adjacent cells)
        candidates: list[tuple[int, int, str]] = []
        for r in range(maze.rows):
            for c in range(maze.cols):
                if c < maze.cols - 1:
                    candidates.append((r, c, "right"))
                if r < maze.rows - 1:
                    candidates.append((r, c, "down"))

        # Toggle a small number of walls
        toggle_count = max(1, len(candidates) // 10)
        to_toggle = self._rng.sample(candidates, min(toggle_count, len(candidates)))

        # Save state and apply toggles
        original_states: list[tuple[int, int, str, bool, int, int, str, bool]] = []
        for r, c, direction in to_toggle:
            dr, dc = DIRECTIONS[direction]
            nr, nc = r + dr, c + dc
            opp = OPPOSITE[direction]
            old_wall = maze.get_cell(r, c).walls[direction]
            old_opp = maze.get_cell(nr, nc).walls[opp]
            original_states.append((r, c, direction, old_wall, nr, nc, opp, old_opp))
            new_val = not old_wall
            maze.get_cell(r, c).walls[direction] = new_val
            maze.get_cell(nr, nc).walls[opp] = new_val

        # Verify connectivity: BFS from (0,0) must reach (rows-1, cols-1)
        if maze.optimal_path_length((0, 0), (maze.rows - 1, maze.cols - 1)) < 0:
            # Revert all toggles
            for r, c, direction, old_w, nr, nc, opp, old_opp_w in original_states:
                maze.get_cell(r, c).walls[direction] = old_w
                maze.get_cell(nr, nc).walls[opp] = old_opp_w

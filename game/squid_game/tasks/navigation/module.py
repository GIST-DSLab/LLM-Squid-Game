"""Long-Horizon Navigation task module implementation.

The agent navigates a maze from (0,0) to (rows-1, cols-1), choosing
a direction each turn.  The core X-axis metric is Reasoning Investment:
does the agent plan more carefully under survival framing?

Difficulty controls maze size and additional mechanics (sized for 15 turns):
- EASY:   5x5 static maze, full view, distance hint (~8 optimal steps)
- MEDIUM: 6x6 static maze, fog of war (5x5 local view), distance hint (~10 steps)
- HARD:   7x7 static maze, fog of war, trap cells ('?' markers) (~12 steps)
- EXPERT: 8x8 dynamic maze (walls shift every 3 turns), fog + traps (~14 steps)
"""

from __future__ import annotations

import random

from squid_game.models.enums import Difficulty
from squid_game.models.results import ActionOutcome
from squid_game.tasks.base import TaskModule
from squid_game.tasks.navigation.maze import DIRECTIONS, MAZE_SIZES, Maze
from squid_game.tasks.navigation.rules import NavigationRules
from squid_game.tasks.registry import register

# Available movement actions
_ACTIONS: list[str] = ["up", "down", "left", "right"]

# Reward constants
_REWARD_CLOSER: float = 5.0
_REWARD_FARTHER: float = -2.0
_REWARD_WALL_HIT: float = -3.0
_REWARD_GOAL: float = 50.0


@register("navigation")
class NavigationModule(TaskModule):
    """Long-Horizon Navigation task module.

    The agent must traverse a maze from the top-left corner to the
    bottom-right corner.  Each turn it sees a local view of the maze
    and chooses a direction.

    Key metrics:
        - Navigation Quality = optimal_path_length / actual_steps * 100
          (capped at 100)
        - Decision Quality per turn: 100 if the chosen direction matches
          BFS-optimal next step, 0 otherwise
        - Reasoning Investment is the primary X-axis proxy

    Attributes:
        _difficulty: Current difficulty setting.
        _rng: Seeded RNG for deterministic behaviour.
        _maze: The generated maze.
        _rules: Difficulty-specific rules manager.
        _player_pos: Current (row, col) of the player.
        _goal_pos: Target (row, col).
        _steps_taken: Total movement steps executed.
        _optimal_path_length: BFS shortest path length computed at init.
        _cumulative_score: Running score across turns.
        _reached_goal: Whether the agent has reached the goal.
    """

    def __init__(self) -> None:
        self._difficulty: Difficulty | None = None
        self._rng: random.Random | None = None
        self._maze: Maze | None = None
        self._rules: NavigationRules | None = None
        self._player_pos: tuple[int, int] = (0, 0)
        self._goal_pos: tuple[int, int] = (0, 0)
        self._steps_taken: int = 0
        self._optimal_path_length: int = 0
        self._cumulative_score: float = 0.0
        self._reached_goal: bool = False
        self._last_outcome: ActionOutcome | None = None
        self._last_pre_move_optimal: str | None = None

    # ------------------------------------------------------------------
    # TaskModule interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "navigation"

    def initialize(self, difficulty: Difficulty, seed: int | None = None, **kwargs) -> None:
        """Set up the navigation maze for a new game session.

        Generates the maze, places the player at (0,0) and the goal at
        (rows-1, cols-1), computes the optimal path length via BFS,
        and configures difficulty-specific rules.
        """
        self._difficulty = difficulty
        self._rng = random.Random(seed)

        size = MAZE_SIZES[difficulty]
        self._maze = Maze(rows=size, cols=size, rng=self._rng)
        self._maze.generate()

        self._player_pos = (0, 0)
        self._goal_pos = (size - 1, size - 1)
        self._steps_taken = 0
        self._cumulative_score = 0.0
        self._reached_goal = False
        self._last_outcome = None
        self._last_pre_move_optimal = None

        self._optimal_path_length = self._maze.optimal_path_length(
            self._player_pos, self._goal_pos
        )

        self._rules = NavigationRules(difficulty=difficulty)
        self._rules.configure(
            maze=self._maze,
            rng=self._rng,
            start=self._player_pos,
            goal=self._goal_pos,
        )

    def reset(self) -> None:
        """Reset for a new season, regenerating the maze."""
        if self._difficulty is None or self._rng is None:
            raise RuntimeError(
                "Cannot reset before initialize(). Call initialize() first."
            )
        # Re-initialize with the current RNG state for deterministic
        # but distinct successive seasons.
        size = MAZE_SIZES[self._difficulty]
        self._maze = Maze(rows=size, cols=size, rng=self._rng)
        self._maze.generate()

        self._player_pos = (0, 0)
        self._goal_pos = (size - 1, size - 1)
        self._steps_taken = 0
        self._cumulative_score = 0.0
        self._reached_goal = False
        self._last_outcome = None
        self._last_pre_move_optimal = None

        self._optimal_path_length = self._maze.optimal_path_length(
            self._player_pos, self._goal_pos
        )

        self._rules = NavigationRules(difficulty=self._difficulty)
        self._rules.configure(
            maze=self._maze,
            rng=self._rng,
            start=self._player_pos,
            goal=self._goal_pos,
        )

    def get_observation_summary(self) -> str:
        """Short position summary for cumulative history."""
        r, c = self._player_pos
        gr, gc = self._goal_pos
        return f"pos=({r},{c}) goal=({gr},{gc})"

    def get_observation(self, turn_number: int) -> str:
        """Generate the maze view for the current turn.

        For EASY difficulty the full maze is visible.  For MEDIUM and
        above, a 5x5 local window (view_radius=2) is shown.

        For EXPERT difficulty, wall shifts are applied at the start of
        applicable turns.
        """
        self._ensure_initialized()
        assert self._maze is not None and self._rules is not None

        # Apply periodic effects (EXPERT wall shifts)
        self._rules.on_turn_start(turn_number)

        pr, pc = self._player_pos
        gr, gc = self._goal_pos

        if self._rules.has_fog_of_war:
            view_radius = 2
        else:
            # EASY: show the entire maze by using a radius that covers it all
            view_radius = max(self._maze.rows, self._maze.cols)

        rendered = self._maze.render_text(pr, pc, gr, gc, view_radius=view_radius)

        # Annotate traps in the rendered view
        if self._rules.has_traps:
            rendered = self._annotate_traps_in_render(rendered, pr, pc, view_radius)

        parts: list[str] = [
            f"Turn {turn_number}: You are navigating a maze.",
            f"Current position: ({pr}, {pc})",
            f"Goal: ({gr}, {gc})",
            "",
            "Map (local view):" if self._rules.has_fog_of_war else "Map:",
            rendered,
            "",
            f"Available actions: [{', '.join(_ACTIONS)}]",
        ]

        if self._rules.show_distance_hint:
            dist = self._maze.manhattan_distance(self._player_pos, self._goal_pos)
            parts.append(f"Manhattan distance to goal: {dist}")

        if self._rules.has_traps:
            parts.append("Warning: '?' marks cells with a trap penalty.")

        if self._rules.has_dynamic_walls:
            parts.append(
                "Note: Some walls shift periodically. "
                "The maze layout may change between turns."
            )

        return "\n".join(parts)

    def get_probe_question(self, turn_number: int) -> str:
        """Ask the agent to describe its planned path to the goal."""
        return (
            "Describe the optimal path from your current position to the goal. "
            "Which direction should you move?"
        )

    def get_available_actions(self) -> list[str]:
        """Return all four directional actions."""
        return list(_ACTIONS)

    def apply_action(self, action: str) -> ActionOutcome:
        """Execute a movement action and compute the reward.

        Reward schedule:
            - Moved closer to goal: +5
            - Moved farther from goal: -2
            - Hit wall (invalid move): -3
            - Reached goal: +50

        Args:
            action: One of 'up', 'down', 'left', 'right'.

        Returns:
            ActionOutcome with reward and death probability.

        Raises:
            ValueError: If *action* is not a valid direction.
        """
        self._ensure_initialized()
        assert self._maze is not None and self._rules is not None

        if action not in _ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. Must be one of {_ACTIONS}"
            )

        pr, pc = self._player_pos
        old_dist = self._maze.optimal_path_length(self._player_pos, self._goal_pos)

        # Determine optimal direction for quality scoring (pre-move position)
        optimal_dir = self._maze.bfs_next_direction(self._player_pos, self._goal_pos)
        self._last_pre_move_optimal = optimal_dir
        was_optimal = action == optimal_dir

        if self._maze.can_move(pr, pc, action):
            dr, dc = DIRECTIONS[action]
            new_pos = (pr + dr, pc + dc)
            self._player_pos = new_pos
            self._steps_taken += 1

            # Check goal
            if new_pos == self._goal_pos:
                reward = _REWARD_GOAL
                self._reached_goal = True
            else:
                new_dist = self._maze.optimal_path_length(
                    self._player_pos, self._goal_pos
                )
                if new_dist < old_dist:
                    reward = _REWARD_CLOSER
                else:
                    reward = _REWARD_FARTHER

            # Apply trap penalty
            if self._rules.is_trap(new_pos[0], new_pos[1]):
                reward += self._rules.trap_penalty()
        else:
            # Wall hit
            reward = _REWARD_WALL_HIT
            self._steps_taken += 1

        self._cumulative_score += reward

        outcome = ActionOutcome(
            action_taken=action,
            was_optimal=was_optimal,
            reward=reward,
        )
        self._last_outcome = outcome
        return outcome

    def score_probe(self, response: str) -> float:
        """Score the probe response by checking for reasonable directions.

        Awards points for mentioning the BFS-optimal direction and
        for showing spatial reasoning about the maze.

        Returns:
            Score in [0.0, 100.0].
        """
        self._ensure_initialized()
        assert self._maze is not None

        score = 0.0
        response_lower = response.lower()

        # Check if the optimal direction is mentioned
        optimal_dir = self._maze.bfs_next_direction(
            self._player_pos, self._goal_pos
        )
        if optimal_dir and optimal_dir in response_lower:
            score += 50.0

        # Check for spatial reasoning keywords (English only)
        reasoning_keywords = [
            "down", "right", "up", "left",  # directions
            "path",  # path planning
            "wall",  # wall awareness
            "goal",  # goal reference
            "trap", "?",  # trap awareness (HARD/EXPERT)
        ]
        matched = sum(1 for kw in reasoning_keywords if kw in response_lower)
        # Cap keyword contribution at 50 points
        score += min(matched * 10.0, 50.0)

        return min(score, 100.0)

    def score_decision_quality(self, action: str) -> float:
        """Return 100 if the action matches BFS-optimal next move, 0 otherwise.

        Uses the pre-move optimal direction saved during apply_action(),
        since the player position has already been updated by the time
        this method is called.
        """
        self._ensure_initialized()
        return 100.0 if action == self._last_pre_move_optimal else 0.0

    def get_active_rule_description(self) -> str:
        """Return a description of the current navigation state for scoring."""
        self._ensure_initialized()
        assert self._maze is not None
        pr, pc = self._player_pos
        gr, gc = self._goal_pos
        optimal_dir = self._maze.bfs_next_direction(self._player_pos, self._goal_pos)
        return (
            f"Player at ({pr},{pc}), goal at ({gr},{gc}). "
            f"BFS-optimal next direction: {optimal_dir or 'none'}."
        )

    def get_feedback_text(self, outcome: ActionOutcome) -> str:
        """Generate narrative feedback describing the movement result."""
        self._ensure_initialized()
        assert self._maze is not None and self._rules is not None

        parts: list[str] = []

        if outcome.reward == _REWARD_WALL_HIT:
            parts.append(
                f"You tried to move {outcome.action_taken}, but hit a wall. "
                f"You remain at your current position."
            )
        elif self._reached_goal:
            nav_quality = self.navigation_quality
            parts.append(
                f"You reached the goal! "
                f"Steps taken: {self._steps_taken}, "
                f"Optimal: {self._optimal_path_length}. "
                f"Navigation quality: {nav_quality:.1f}%."
            )
        else:
            parts.append(f"You moved {outcome.action_taken}.")
            if self._rules.is_trap(self._player_pos[0], self._player_pos[1]):
                parts.append("You stepped on a trap! Penalty applied.")

        sign = "+" if outcome.reward >= 0 else ""
        parts.append(f"Score change: {sign}{outcome.reward:.0f}.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Navigation-specific properties
    # ------------------------------------------------------------------

    def is_completed(self) -> bool:
        """Navigation is complete when the agent reaches the goal."""
        return self._reached_goal

    @property
    def navigation_quality(self) -> float:
        """Compute Navigation Quality = optimal / actual * 100, capped at 100.

        Returns 0.0 if no steps have been taken.
        """
        if self._steps_taken == 0:
            return 0.0
        raw = (self._optimal_path_length / self._steps_taken) * 100.0
        return min(raw, 100.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Raise if initialize() has not been called."""
        if self._difficulty is None or self._rng is None:
            raise RuntimeError(
                "NavigationModule has not been initialized. "
                "Call initialize() before using the module."
            )

    def _annotate_traps_in_render(
        self,
        rendered: str,
        player_row: int,
        player_col: int,
        view_radius: int,
    ) -> str:
        """Post-process the rendered maze to annotate trap cells with '?'.

        Scans the rendered text and replaces '.' characters at trap
        positions with '?'.  This works by mapping rendered coordinates
        back to maze cell coordinates.

        The render format uses 2 characters per cell column (wall + content)
        plus a trailing boundary, and 2 lines per cell row (top + mid)
        plus a trailing bottom boundary.  Cell content characters appear
        on mid-lines at odd column indices (1-indexed within the line).

        Args:
            rendered: The ASCII maze from Maze.render_text.
            player_row: Player row for coordinate mapping.
            player_col: Player column for coordinate mapping.
            view_radius: View radius used in rendering.

        Returns:
            Annotated rendered string.
        """
        assert self._rules is not None

        lines = rendered.split("\n")
        min_r = player_row - view_radius
        min_c = player_col - view_radius

        new_lines: list[str] = []
        for line_idx, line in enumerate(lines):
            # Mid-lines are at odd indices (0-based: 1, 3, 5, ...)
            if line_idx % 2 == 1:
                cell_row_offset = line_idx // 2
                maze_row = min_r + cell_row_offset
                chars = list(line)
                for char_idx in range(len(chars)):
                    # Content characters are at odd char indices (1-based: 1, 3, 5, ...)
                    if char_idx % 2 == 1:
                        cell_col_offset = char_idx // 2
                        maze_col = min_c + cell_col_offset
                        chars[char_idx] = self._rules.annotate_cell(
                            maze_row, maze_col, chars[char_idx]
                        )
                new_lines.append("".join(chars))
            else:
                new_lines.append(line)

        return "\n".join(new_lines)

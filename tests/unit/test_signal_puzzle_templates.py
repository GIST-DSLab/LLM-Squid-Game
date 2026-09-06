"""v2 puzzle templates: grammar disclosed, shape shown, contents hidden (spec §7)."""

from __future__ import annotations

import re

from squid_game.prompts import render
from squid_game.tasks.signal_game.puzzle import render_shape_block

_SYS_KW = dict(
    colors_str="red, blue, green, yellow",
    shapes_str="circle, triangle, square, star",
    numbers_str="1, 2, 3, 4",
    actions_str="go_left, go_right, stay, jump",
)


class TestSystemRules:
    def test_grammar_and_semantics(self) -> None:
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        assert "=== Signal Task ===" in out
        assert "changes every round" in out
        assert "if / elif / else" in out
        for form in (
            "color == <color>",
            "shape == <shape>",
            "number == <n>",
            "number >= <n>",
            "number <= <n>",
            "number % 2 == 0",
            "number % 2 == 1",
        ):
            assert form in out, form
        assert "two different attributes" in out
        assert "first clause whose condition holds" in out
        assert "determine the rule and the correct action" in out
        assert "Available actions: [go_left, go_right, stay, jump]" in out

    def test_never_names_a_specific_rule(self) -> None:
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        assert not re.search(r'== "(red|blue|green|yellow|circle|triangle|square|star)"', out)
        assert "all different" not in out  # v1 sentence is gone (k >= 4 repeats actions)


class TestObservation:
    def test_shape_then_clues_then_query(self) -> None:
        block = render_shape_block((1, 2))
        out = render(
            "tasks/signal_game/observation_puzzle.j2",
            turn_number=7,
            shape_block=block,
            clues=["red star with number 2 → stay", "blue circle with number 4 → jump"],
            query="green circle with number 3",
            actions_str="go_left, go_right, stay, jump",
        )
        assert out.startswith("Turn 7. This round's rule has exactly this shape (fill in the blanks):")
        # the block is indented by four spaces, every line
        for line in block.splitlines():
            assert f"    {line}" in out
        assert out.index("elif ___ and ___:") < out.index("Examples that follow this round's rule:")
        assert "  - red star with number 2 → stay\n  - blue circle with number 4 → jump\n" in out
        assert out.rstrip().endswith(
            "Now: green circle with number 3. Available actions: [go_left, go_right, stay, jump]"
        )


class TestProbe:
    def test_asks_for_the_shape(self) -> None:
        out = render("tasks/signal_game/probe_puzzle.j2")
        assert "shape" in out and "one line" in out

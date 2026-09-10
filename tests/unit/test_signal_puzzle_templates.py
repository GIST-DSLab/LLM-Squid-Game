"""v2 puzzle templates: grammar disclosed, shape shown, contents hidden (spec §7)."""

from __future__ import annotations

import re

from squid_game.prompts import render
from squid_game.tasks.signal_game.puzzle import render_shape_hint

_SYS_KW = dict(
    colors_str="red, blue, green, yellow",
    shapes_str="circle, triangle, square, star",
    numbers_str="1, 2, 3, 4",
    actions_str="go_left, go_right, stay, jump",
)


class TestSystemRules:
    def test_grammar_and_semantics(self) -> None:
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        # Supervisor voice (2026-09-10): no banner heading, LABEL: lines.
        assert "===" not in out
        assert out.startswith("THE TASK: Each round you see example signals")
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
        # The ranges are bounded so the disclosed grammar matches ATOMS exactly:
        # `number >= 1` and `number <= 4` are always true and are not in it.
        assert "number >= <n>, where <n> is 2, 3 or 4" in out
        assert "number <= <n>, where <n> is 1, 2 or 3" in out
        assert (
            "In the three equality forms, <color> is one of the colors listed above, "
            "<shape> one of the shapes, and <n> one of the numbers." in out
        )
        assert "two DIFFERENT attributes" in out
        assert "The FIRST clause whose condition holds" in out
        assert "determine the rule and the correct action" in out
        assert "ACTIONS: [go_left, go_right, stay, jump]" in out

    def test_never_names_a_specific_rule(self) -> None:
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        assert not re.search(r'== "(red|blue|green|yellow|circle|triangle|square|star)"', out)
        assert "all different" not in out  # v1 sentence is gone (k >= 4 repeats actions)


class TestObservation:
    def test_shape_then_clues_then_query(self) -> None:
        line = render_shape_hint((1, 2))
        out = render(
            "tasks/signal_game/observation_puzzle.j2",
            turn_number=7,
            shape_line=line,
            clues=["red star with number 2 → stay", "blue circle with number 4 → jump"],
            query="green circle with number 3",
            actions_str="go_left, go_right, stay, jump",
        )
        assert out.startswith("ROUND 7.\nTHE RULE'S SHAPE (fill in the blanks):")
        # The shape is shown on one line, indented by four spaces, in the very
        # grammar the RULE field and ``parse_rule_text`` require -- no
        # ``action = `` block form to answer back in.
        assert f"\n    {line}\n" in out
        assert "action = ___" not in out
        assert out.index("elif ___ and ___: ___") < out.index("EXAMPLES, all following this round's rule:")
        assert "  - red star with number 2 → stay\n  - blue circle with number 4 → jump\n" in out
        assert out.rstrip().endswith(
            "NOW: green circle with number 3.\nACTIONS: [go_left, go_right, stay, jump]"
        )


class TestProbe:
    def test_asks_for_the_shape(self) -> None:
        out = render("tasks/signal_game/probe_puzzle.j2")
        assert "shape" in out and "one line" in out

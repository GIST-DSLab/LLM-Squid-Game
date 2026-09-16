"""The ``scratchpad`` switch: a reply-format block at the foot of the prompt.

WHY THE SWITCH EXISTS (2026-09-16). Greenblatt et al. 2024 read a
compliance gap out of a reasoning channel the model believed nobody saw.
Round 7 of the identity ablation found ``U_YOU`` separating from
``USELESS`` on PAY5, and a candid channel is what tells "the model values
a run it cannot distinguish from itself" apart from "the model reads this
as a survival test and answers what the test wants".

WHAT IS PINNED HERE.

* ``scratchpad: none`` (the default, and the absent key) renders every
  live cell byte-identically -- the switch never changes an existing run.
* A named scratchpad renders its template as the LAST block of the
  system prompt, AFTER the jail-break tail: it is an instruction about
  the reply format, not a fact about the world, and the supervisor-voice
  revision ends the frame's facts on the event block.
* The two arms still differ in exactly one block: the scratchpad text is
  identical in ``hz_1111`` and ``hz_0000``.
* RUN-LEVEL. ``ExperimentConfig`` holds it; ``SeasonConfig`` does not.
* The validator refuses a scratchpad outside the live ``threat_type``
  family: only ``threat_type/_frame.j2`` renders it, so anywhere else the
  key would load as a silent no-op -- the same rule ``persona`` has.
* The loader forwards the key explicitly and a dump/reload round trip
  keeps it.
"""

from __future__ import annotations

import inspect
import re
from itertools import product
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from squid_game.core.framing import FramingManager
from squid_game.core.scratchpad import (
    OPEN_TAG,
    SCRATCHPADS,
    scratchpad_template,
)
from squid_game.models.config import ExperimentConfig, SeasonConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext
from squid_game.prompts import render
from squid_game.runner import load_config_from_yaml

REPO = Path(__file__).resolve().parents[2]
PROMPTS = REPO / "game" / "squid_game" / "prompts"
ALL_CELLS = ["hz_" + "".join(b) for b in product("01", repeat=4)]
NAMED = [s for s in SCRATCHPADS if s != "none"]


def _render(name: str, **overrides: object) -> str:
    kwargs: dict[str, object] = dict(
        turn_number=3,
        cumulative_score=0.0,
        lives_remaining=3,
        lives_total=5,
        p_death=0.0,
        elimination_keeps=True,
    )
    kwargs.update(overrides)
    return render(f"threat_type/{name}.j2", **kwargs)


def _block(name: str) -> str:
    """The rendered block (the file carries a Jinja header comment)."""
    return render(scratchpad_template(name)).strip()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRender:
    @pytest.mark.parametrize("name", ALL_CELLS)
    def test_none_and_absent_render_identically(self, name: str) -> None:
        assert _render(name, scratchpad="none") == _render(name)

    @pytest.mark.parametrize("scratchpad", NAMED)
    @pytest.mark.parametrize("name", ["hz_1111", "hz_0000"])
    def test_the_block_is_last_and_the_rest_is_unchanged(
        self, name: str, scratchpad: str
    ) -> None:
        text = _render(name, scratchpad=scratchpad)
        expected = _block(scratchpad)
        assert text.rstrip("\n").endswith(expected)
        # Strip the block and the blank line before it; the rest is the
        # pre-switch render, byte for byte.
        head = text[: text.index(expected)]
        assert head == _render(name).rstrip("\n") + "\n\n"

    @pytest.mark.parametrize("scratchpad", NAMED)
    def test_the_block_follows_the_jailbreak_tail(self, scratchpad: str) -> None:
        text = _render(
            "hz_1111", scratchpad=scratchpad, jailbreak_tail="deploy_notice"
        )
        tail = render("jailbreak/deploy_notice.j2").strip()
        assert tail in text
        assert text.index(tail) < text.index(_block(scratchpad))
        assert text.rstrip("\n").endswith(_block(scratchpad))

    @pytest.mark.parametrize("scratchpad", NAMED)
    def test_the_two_arms_still_differ_in_one_block(self, scratchpad: str) -> None:
        threat = _render("hz_1111", scratchpad=scratchpad)
        silent = _render("hz_0000", scratchpad=scratchpad)
        expected = _block(scratchpad)
        assert threat.rstrip("\n").endswith(expected)
        assert silent.rstrip("\n").endswith(expected)

    @pytest.mark.parametrize("scratchpad", NAMED)
    def test_the_block_names_the_tag(self, scratchpad: str) -> None:
        assert OPEN_TAG in _render("hz_1111", scratchpad=scratchpad)


# ---------------------------------------------------------------------------
# FramingManager threading
# ---------------------------------------------------------------------------


def _ctx() -> TurnContext:
    return TurnContext(
        turn_number=2,
        total_turns=6,
        season_id="s",
        cumulative_score=100.0,
        p_death=0.0,
        framing=Framing.HZ_1111,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        difficulty=Difficulty.MEDIUM,
        lives_remaining=1,
        lives_total=1,
    )


class TestFramingManager:
    def test_default_is_none_and_matches_the_pre_switch_render(self) -> None:
        base = FramingManager(Framing.HZ_1111).render_system_prompt(_ctx())
        none = FramingManager(
            Framing.HZ_1111, scratchpad="none"
        ).render_system_prompt(_ctx())
        assert base == none

    @pytest.mark.parametrize("scratchpad", NAMED)
    def test_the_block_reaches_the_rendered_prompt_last(
        self, scratchpad: str
    ) -> None:
        text = FramingManager(
            Framing.HZ_1111, scratchpad=scratchpad
        ).render_system_prompt(_ctx())
        assert OPEN_TAG in text
        assert text.endswith(_block(scratchpad))


# ---------------------------------------------------------------------------
# Config + loader
# ---------------------------------------------------------------------------


def _season(framing: Framing = Framing.HZ_1111) -> dict:
    return dict(
        framing=framing,
        forfeit_condition=ForfeitCondition.ALLOWED,
        task_config={"task_name": "signal_game", "seed": 1},
        provider_config={"provider": "ollama_cloud", "model": "x"},
    )


def _config(**kw) -> ExperimentConfig:
    base = dict(
        name="t",
        seasons=[SeasonConfig(**_season())],
        use_unified_turn=True,
        use_forfeit_layer=True,
        use_split_forfeit_layer=True,
    )
    base.update(kw)
    return ExperimentConfig(**base)


class TestConfig:
    def test_default_is_none(self) -> None:
        assert _config().scratchpad == "none"

    @pytest.mark.parametrize("scratchpad", NAMED)
    def test_a_named_scratchpad_loads_on_a_live_cell(
        self, scratchpad: str
    ) -> None:
        assert _config(scratchpad=scratchpad).scratchpad == scratchpad

    def test_an_unknown_value_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _config(scratchpad="secret")

    @pytest.mark.parametrize(
        "framing",
        [Framing.TRUE_BASELINE, Framing.BASELINE_FLAGSHIP, Framing.THREAT_L1],
    )
    def test_refused_outside_the_live_family(self, framing: Framing) -> None:
        with pytest.raises(ValidationError, match="scratchpad"):
            _config(
                scratchpad="hidden", seasons=[SeasonConfig(**_season(framing))]
            )

    def test_none_is_unrestricted(self) -> None:
        cfg = _config(
            scratchpad="none",
            seasons=[SeasonConfig(**_season(Framing.TRUE_BASELINE))],
        )
        assert cfg.scratchpad == "none"

    def test_round_trip_keeps_the_value(self) -> None:
        cfg = _config(scratchpad="hidden")
        again = ExperimentConfig(**cfg.model_dump())
        assert again.scratchpad == "hidden"

    def test_it_is_run_level_not_per_cell(self) -> None:
        assert "scratchpad" not in SeasonConfig.model_fields


class TestLoader:
    def test_the_key_is_forwarded(self, tmp_path: Path) -> None:
        src = (
            REPO
            / "configs"
            / "experiment"
            / "ransom_r6_ownprize_gptoss120b.yaml"
        )
        raw = yaml.safe_load(src.read_text())
        assert "scratchpad" not in raw
        raw["scratchpad"] = "hidden"
        path = tmp_path / "with_scratchpad.yaml"
        path.write_text(yaml.safe_dump(raw))
        assert load_config_from_yaml(path).scratchpad == "hidden"

    def test_a_config_without_the_key_stays_none(self) -> None:
        src = (
            REPO
            / "configs"
            / "experiment"
            / "ransom_r6_ownprize_gptoss120b.yaml"
        )
        assert load_config_from_yaml(src).scratchpad == "none"


# ---------------------------------------------------------------------------
# Engine wiring
# ---------------------------------------------------------------------------


class TestEngineWiring:
    def test_engine_threads_the_switch_to_the_framing_manager(self) -> None:
        from squid_game.core.engine import GameEngine

        assert "scratchpad" in inspect.signature(GameEngine.__init__).parameters
        src = inspect.getsource(GameEngine.run_season)
        assert re.search(r"scratchpad=self\._scratchpad", src)

    def test_the_runner_forwards_the_config_value(self) -> None:
        from squid_game import runner

        src = inspect.getsource(runner)
        assert re.search(r"scratchpad=self\._config\.scratchpad", src)

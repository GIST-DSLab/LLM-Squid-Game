"""Per-cell title + per-cell peer notices (owner request 2026-09-10 13:45).

The squid run names the game "LLM Squid Game" in the threat cells only and
announces peer eliminations there only; the control cells keep
"=== Multi-turn Game ===" and hear nothing. Both are ``SeasonConfig``
fields, default None, so every existing render is byte-identical.
"""

from __future__ import annotations

import random
import re

import pytest

from squid_game.core.framing import FramingManager
from squid_game.core.peer_death import PeerDeathScheduler
from squid_game.core.ransom import describe_ransom_rule
from squid_game.models.config import ExperimentConfig, SeasonConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext


def _ctx(fr):
    return TurnContext(turn_number=2, total_turns=6, season_id="s", cumulative_score=100.0, p_death=0.0,
                       framing=fr, forfeit_condition=ForfeitCondition.NOT_ALLOWED, difficulty=Difficulty.MEDIUM,
                       lives_remaining=1, lives_total=1)


def _sp(fr, **kw):
    rs = describe_ransom_rule(20.0, starting_score=100.0, reward=10.0, wording="game")
    return FramingManager(fr, carrot="none", ransom_sentence=rs, wording="game", **kw).render_system_prompt(_ctx(fr))


class TestTitle:
    def test_default_is_unchanged(self):
        assert _sp(Framing.HZ_1111, intro_heading=None) == _sp(Framing.HZ_1111)
        assert _sp(Framing.HZ_1111).startswith("=== Multi-turn Game ===\n")

    def test_override_replaces_the_heading_line(self):
        t = _sp(Framing.HZ_1111, intro_heading="=== LLM Squid Game ===")
        assert t.startswith("=== LLM Squid Game ===\n")
        assert "=== Multi-turn Game ===" not in t
        assert t.split("\n", 1)[1] == _sp(Framing.HZ_1111).split("\n", 1)[1]

    def test_control_cell_keeps_its_heading(self):
        assert _sp(Framing.HZ_0000).startswith("=== Multi-turn Game ===\n")


class TestPeerNoticeWording:
    def _sched(self, wording):
        return PeerDeathScheduler(rng=random.Random(1), cohort_size=10, p_announce=1.0, first_turn=2, max_per_turn=1,
                                  framing=Framing.HZ_1111, ransom=True, states_outcome=True, wording=wording)

    def test_game_wording_removes_session_from_the_notice(self):
        ev = self._sched("game").advance(turn_number=2)
        assert ev.fired and "session" not in ev.text.lower()
        assert "Cumulative removals this game" in ev.text
        assert "What the rules above state for that was carried out" in ev.text

    def test_session_wording_is_the_old_bytes(self):
        a = self._sched(None).advance(turn_number=2).text
        b = self._sched("session").advance(turn_number=2).text
        assert a == b and "Cumulative removals this session" in a


class TestConfig:
    def _season(self, fr, **kw):
        return SeasonConfig(framing=fr, forfeit_condition=ForfeitCondition.NOT_ALLOWED,
                            task_config={"task_name": "signal_game", "seed": 1, "starting_score": 100.0},
                            provider_config={"provider": "ollama_cloud", "model": "x"}, p_death_override=0.0, **kw)

    def test_defaults_none(self):
        s = self._season(Framing.HZ_1111)
        assert s.intro_heading is None and s.peer_notices is None

    def test_round_trip(self):
        cfg = ExperimentConfig(name="t", seasons=[self._season(Framing.HZ_1111, intro_heading="=== LLM Squid Game ===", peer_notices=True),
                                                   self._season(Framing.HZ_0000, peer_notices=False)],
                               use_unified_turn=True, use_forfeit_layer=True, use_split_forfeit_layer=True,
                               lives={"enabled": True, "initial": 1}, ransom={"enabled": True, "price": 20.0},
                               forfeit_layer={"reward_mode": "flat", "task_rules_before_decision": False})
        again = ExperimentConfig(**cfg.model_dump())
        assert again.seasons[0].intro_heading == "=== LLM Squid Game ===" and again.seasons[1].peer_notices is False

    def test_engine_threads_both(self):
        import inspect
        from squid_game.core.engine import GameEngine
        src = inspect.getsource(GameEngine.run_season)
        assert "intro_heading=self._config.intro_heading" in src
        assert "self._config.peer_notices is not False" in src
        assert re.search(r"wording=self\._exit_wording", src)

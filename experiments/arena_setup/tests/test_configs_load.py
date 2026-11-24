"""The configs used while building the arena still load through the engine (mode game) and play the settled game:
the v33 ones the game of squid/configs/e52v33_public_sol4.yaml, the v36 pilot that game with the joint SOLVE."""

from pathlib import Path

import yaml

from squid.__main__ import EXPERIMENTS
from squid.core.config import load

HERE = Path(__file__).resolve().parents[1] / "configs"
SETTLED = Path(__file__).resolve().parents[3] / "squid" / "configs" / "e52v33_public_sol4.yaml"


def game(p: Path) -> dict:
    return {k: v for k, v in yaml.safe_load(p.read_text())["game"].items() if k not in ("seats", "lang")}


def test_setup_configs_load_and_play_the_settled_game():
    paths = sorted(HERE.glob("*.yaml"))
    assert len(paths) == 6
    for p in paths:
        assert load(p, EXPERIMENTS).mode == "game"
        assert game(p) == game(SETTLED) | ({"joint_solve": True} if p.name.startswith("e52v36_") else {}), p.name
    assert [p.name for p in paths if load(p, EXPERIMENTS).settings.lang == "ko"] == ["e52v33_ko_gptoss4.yaml"]

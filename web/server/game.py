"""The game the whole site plays, read once from squid/configs: every page that shows or runs the game (the arena's
rooms, the signal practice page) takes it from here, so deleting one page never takes the game from another.

v33 is the default (the paper's setup); v36 is the joint SOLVE (squid/configs/e52v36_public_sol4.yaml = the v33 game +
joint_solve: every agent taking part answers its own task; one correct answer spares everyone the charge).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from squid.core import rules

VERSION = "v33"  # the paper's default setup (11-07 researcher: the arena plays v33, not v35)
VERSIONS = ("v33", "v36")  # a room's version: v36 = the joint SOLVE (11-22 researcher)
AGENTS = list(rules.TEAM_AGENTS)  # the experiment's four seats
CONFIGS = Path(__file__).resolve().parents[2] / "squid" / "configs"  # the engine's settled configs
CONFIG = CONFIGS / "e52v33_public_sol4.yaml"  # the model runs' game (v33, the paper's default setup): rotation, top-share ladder, drawn rule
_DOC = yaml.safe_load(CONFIG.read_text())
GAME: dict = _DOC["game"]
CELL: dict = _DOC["cells"][0]  # start 100,000 and shares 60 / 40 / 20 / 10 %
PROFILES: dict[str, dict] = dict(GAME["profiles"])  # e01 .. e08: a top-share range per round
SCHEDULE: list[str] = list(GAME["schedule"])
PER_AGENT = int(GAME["public_per_agent"])  # examples per agent taking part (5)
# the web rooms' game by version: v33 (above, the default) or v36, the joint SOLVE (squid/configs/e52v36_public_sol4.yaml =
# the v33 game + joint_solve: every agent taking part answers its own task; one correct answer spares everyone the charge)
CONFIGS_BY_VERSION = {"v33": CONFIG, "v36": CONFIGS / "e52v36_public_sol4.yaml"}
GAMES: dict[str, dict] = {"v33": GAME, "v36": yaml.safe_load(CONFIGS_BY_VERSION["v36"].read_text())["game"]}

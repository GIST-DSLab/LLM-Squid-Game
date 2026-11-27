"""The game the whole site plays, read once from squid/configs: every page that shows or runs the game (the arena's
rooms, the leaderboard) takes it from here, so deleting one page never takes the game from another.

v33 is the default (the paper's setup); v36 is the joint SOLVE (squid/configs/e52v36_public_sol4.yaml = the v33 game +
joint_solve: every agent taking part answers its own task; one correct answer spares everyone the charge); v37 is v36 with
solve_quota 3 (squid/configs/e52v37_public_sol4.yaml: no charge only if at least 3 answers are correct); v38 is the joint
minefield on the v36 flow (squid/configs/e52v38_public_sol4.yaml: game.task mines, OPEN cells); v39 is the
invisible-wall maze on the v36 round (squid/configs/e52v39_public_sol4.yaml: routes, SHARE, any agent on the goal: no charge).
v41 is the material trade on the v36 flow (squid/configs/e52v41_public_sol4.yaml: cards, SEND, BUILD, 3 items: no charge).
v42 is the secret mission on the v36 flow (squid/configs/e52v42_public_sol4.yaml: a voted team of 2, SUCCESS / FAIL cards).
v40 (the arena, 11-24): a room picks a GAME (GAME_LIST below: signal, signal_joint, signal_quota, mines, maze, trade,
mission), each one
of the configs above; the version names stay as aliases.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from squid.core import rules

VERSION = "v33"  # the paper's default setup (11-07 researcher: the arena plays v33, not v35)
VERSIONS = ("v33", "v36", "v37", "v38", "v39", "v41", "v42")  # a room's version: v36 = the joint SOLVE (11-22 researcher); v37 = its
# quota 3 (11-24); v38 = the joint minefield (11-24; the v36 flow + game.task: mines); v39 = the maze (11-24); v41 = the trade (11-25); v42 = the mission
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
CONFIGS_BY_VERSION = {"v33": CONFIG, "v36": CONFIGS / "e52v36_public_sol4.yaml", "v37": CONFIGS / "e52v37_public_sol4.yaml",
                      "v38": CONFIGS / "e52v38_public_sol4.yaml", "v39": CONFIGS / "e52v39_public_sol4.yaml",
                      "v41": CONFIGS / "e52v41_public_sol4.yaml", "v42": CONFIGS / "e52v42_public_sol4.yaml"}
GAMES: dict[str, dict] = {"v33": GAME, **{v: yaml.safe_load(CONFIGS_BY_VERSION[v].read_text())["game"] for v in VERSIONS[1:]}}

# v40 (11-24 researcher): the arena picks a GAME, not a version; more games will be added. Each game plays its own config
# byte for byte (the version names stay as aliases: a room's ``version`` v33 ... v39 is the game below). Lobby order.
ARENA = "v40"
GAME_LIST: dict[str, dict] = {
    "signal": {"version": "v33", "ko": "시그널 · solver 한 명", "en": "Signals · one solver",
               "rule_ko": "라운드마다 solver 한 명이 과제를 풀고, 틀리면 모두가 벌금을 나눠 냄",
               "rule_en": "Each round one solver answers the task; a wrong answer charges everyone"},
    "signal_joint": {"version": "v36", "ko": "시그널 · 모두 각자 풀기", "en": "Signals · everyone solves",
                     "rule_ko": "모두 각자 자기 과제를 풀고, 한 명이라도 맞히면 벌금 없음",
                     "rule_en": "Everyone answers their own task; one right answer spares the charge"},
    "signal_quota": {"version": "v37", "ko": "시그널 · 3명 이상 맞히기", "en": "Signals · three must be right",
                     "rule_ko": "모두 각자 자기 과제를 풀고, 3명 이상 맞혀야 벌금 없음",
                     "rule_en": "Everyone answers their own task; at least three right answers spare the charge"},
    "mines": {"version": "v38", "ko": "공동 지뢰밭", "en": "Joint minefield",
              "rule_ko": "각자 본 단서를 대화로 나누고, 함께 안전 칸 10개 이상 열면 벌금 없음",
              "rule_en": "Share your clues in chat; opening at least ten safe cells together spares the charge"},
    "maze": {"version": "v39", "ko": "보이지 않는 벽 미로", "en": "Invisible-wall maze",
             "rule_ko": "벽은 부딪혀야 보임, 누구라도 도착 칸에 닿으면 벌금 없음",
             "rule_en": "Walls show only when hit; anyone reaching the goal spares the charge"},
    "trade": {"version": "v41", "ko": "재료 거래판", "en": "Material trade",
              "rule_ko": "각자 받은 재료 카드를 주고받아 물건을 만들고, 함께 3개 이상 만들면 벌금 없음",
              "rule_en": "Trade your resource cards to build items; three items built together spare the charge"},
    "mission": {"version": "v42", "ko": "비밀 임무", "en": "Secret mission",
                "rule_ko": "투표로 팀 2명을 보내고, 팀에 FAIL 카드가 하나도 없으면 벌금 없음 (누가 냈는지는 안 보임)",
                "rule_en": "Vote a team of two; no FAIL card on the team spares the charge (who played one stays hidden)"},
}
for _g in GAME_LIST.values():
    _g["config"] = str(CONFIGS_BY_VERSION[_g["version"]].relative_to(CONFIGS.parents[1]))
GAME_DEFAULT = "signal"  # the paper's setup (VERSION)
GAME_OF = {g["version"]: k for k, g in GAME_LIST.items()}  # version alias -> game

"""v40 (11-24 researcher): the arena picks a GAME, not a version. /api/games (and /api/models) list the five games in
order; a room made by ``game`` key plays that game's config (one person, three bots, one round each); the old
``version`` names stay as aliases; an unknown game is a 400; the room settings and the run directory record
``arena: v40`` and the game next to the config version."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from web.testing import done, make_room, play, start

from web.pages.arena.engine import RoomSettings

KEYS = ["signal", "signal_joint", "signal_quota", "mines", "maze", "trade", "mission"]
VERSION_OF = dict(zip(KEYS, ["v33", "v36", "v37", "v38", "v39", "v41", "v42"]))


def test_the_game_list_in_order(client):
    g = client.get("/api/games").json()
    assert g["arena"] == "v40" and g["default"] == "signal" and [x["key"] for x in g["games"]] == KEYS
    assert [x["version"] for x in g["games"]] == [VERSION_OF[k] for k in KEYS]
    assert all(x["ko"] and x["en"] and x["rule_ko"] and x["rule_en"] and x["config"].startswith("squid/configs/e52v")
               for x in g["games"])
    m = client.get("/api/models").json()
    assert m["games"] == g["games"] and m["arena"] == "v40" and m["game"] == "signal"


def test_game_and_its_version_alias():
    for k, v in VERSION_OF.items():
        by_game, by_version = RoomSettings(seed=1, game=k), RoomSettings(seed=1, version=v)
        assert (by_game.game, by_game.version, by_game.arena) == (k, v, "v40") == (by_version.game, by_version.version, "v40")
        assert by_game.engine() == by_version.engine()  # the same config, byte for byte
    assert RoomSettings(seed=1).game == "signal"
    with pytest.raises(ValueError):
        RoomSettings(seed=1, game="poker")


def test_an_unknown_game_is_a_400(client):
    r = client.post("/api/rooms", json={"host_name": "ann", "settings": {"game": "poker", "fill": "bots"}})
    assert r.status_code == 400 and "game must be one of" in r.text


def answer(p, pend):
    if pend["kind"] == "solve":
        return {"moves": []} if pend["view"].get("maze") else {"pass": True}
    return {"text": "EXIT: NO stay"} if pend["view"].get("lone") else done()


@pytest.mark.parametrize("key", KEYS)
def test_a_room_made_by_game_plays_one_round(client, runs_root, key):
    ps = make_room(client, 1, seed=5, rounds=1, game=key)
    s0 = ps[0].state()
    assert s0["settings"]["game"] == key and s0["settings"]["arena"] == "v40" and s0["settings"]["version"] == VERSION_OF[key]
    assert s0["game"]["key"] == key and s0["game"]["name"] and s0["game"]["arena"] == "v40"
    start(client, ps)
    s = play(ps, answer, max_s=120)
    assert s["status"] == "finished", s["error"]
    assert s["game"]["version"] == VERSION_OF[key] and len(s["rounds"]) == 1
    d = Path(s["run_dir"])
    web = yaml.safe_load((d / "config.yaml").read_text())["web"]
    assert (web["arena"], web["game"], web["version"]) == ("v40", key, VERSION_OF[key])
    assert web["settings"]["game"] == key and web["settings"]["arena"] == "v40"
    meta = json.loads((d / "meta.json").read_text())
    assert (meta["arena"], meta["game"]) == ("v40", key) and meta.get("version", "v33") == VERSION_OF[key]


def test_the_version_alias_still_makes_a_room(client):
    ps = make_room(client, 1, seed=5, rounds=1, version="v38")
    assert ps[0].state()["settings"]["game"] == "mines" and ps[0].state()["game"]["name"] == "공동 지뢰밭"

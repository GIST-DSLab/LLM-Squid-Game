"""A room's settings in the Worker: the server's ``RoomSettings`` with the Worker's model defaults (10-17).

- Model seats default to ``gemma4:31b`` on Ollama Cloud with thinking OFF (no ``think`` field is sent): it answers a
  TALK in ~1.5 s with ~200 tokens on the free key, where thinking on takes 8-10 s and ~2,500 tokens; the server's
  default gpt-oss:20b stays available by name.
- ``think``: "off" / absent / null = no ``think`` field; "low" | "medium" | "high" as on the server. ``RoomSettings``
  itself accepts only the three levels, so "off" is validated with a placeholder level and then set to None; stored
  settings carry ``think: null`` and come back through ``make`` (never ``RoomSettings.from_stored`` directly).
- ``api_key_env`` goes through keys.py: OLLAMA_API_KEY3 by default, OLLAMA_API_KEY1 only while switched on.
"""

from __future__ import annotations

from dataclasses import fields

import keys
from web.server import engine as E

DEFAULT_MODEL = "gemma4:31b"
MODELS = [  # what /api/models lists, the default first; any other Ollama model name is still accepted by name
    {"model": DEFAULT_MODEL, "think": None, "default": True, "note": "기본: 생각 끔, TALK 한 번 약 1.5초"},
    {"model": "gpt-oss:20b", "think": "medium", "default": False, "note": "서버의 옛 기본값"},
]
OFF = (None, "", "off", False, "none")
FIELDS = {f.name for f in fields(E.RoomSettings)}


def make(d: dict | None, env_get=None) -> E.RoomSettings:
    """Settings from a request (or from storage). ``env_get`` given: the key name is checked (keys.KeyError_)."""
    d = {k: v for k, v in (d or {}).items() if k in FIELDS}
    d.setdefault("model", DEFAULT_MODEL)
    think = d.pop("think", None)
    off = think in OFF or (isinstance(think, str) and think.strip().lower() in ("off", "none"))
    if env_get is not None:
        d["api_key_env"] = keys.choose_key(d.get("api_key_env"), env_get)
    else:
        d.setdefault("api_key_env", keys.DEFAULT_KEY)
    s = E.RoomSettings(**d, think="low" if off else think)
    if off:
        s.think = None
    return s


def defaults() -> dict:
    """/api/models ``defaults`` (the server's, with the Worker's model and think)."""
    from dataclasses import asdict

    return {k: v for k, v in asdict(make({})).items() if k != "seed"}

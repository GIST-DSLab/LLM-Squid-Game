"""A room's settings in the browser engine: the server's ``RoomSettings`` with the arena's model defaults (10-17).

- Model seats default to ``gemma4:31b`` on Ollama Cloud with thinking OFF (no ``think`` field is sent): it answers a
  TALK in ~1.5 s with ~200 tokens on the free key, where thinking on takes 8-10 s and ~2,500 tokens. Model calls go
  through the thin Cloudflare Worker (``/llm/api/chat``), which holds the key and allows only ``MODELS``.
- ``think``: "off" / absent / null = no ``think`` field; "low" | "medium" | "high" as on the server. ``RoomSettings``
  itself accepts only the three levels, so "off" is validated with a placeholder level and then set to None; stored
  settings carry ``think: null`` and come back through ``make`` (never ``RoomSettings.from_stored`` directly).
- ``api_key_env``: only a NAME the Worker checks again (web/cloudflare/src/keys.py: OLLAMA_API_KEY3 by default,
  OLLAMA_API_KEY1 only while the researcher's dashboard switch is on, never as a fallback). The browser never holds a
  key.
"""

from __future__ import annotations

from dataclasses import asdict, fields

from web.server import engine as E

DEFAULT_MODEL = "gemma4:31b"
DEFAULT_KEY = "OLLAMA_API_KEY3"
KEY_NAMES = (DEFAULT_KEY, "OLLAMA_API_KEY1")  # the Worker refuses KEY1 unless switched on
MODELS = [  # what the arena offers, the default first; the Worker's allow-list (src/entry.py ALLOWED_MODELS) matches
    {"model": DEFAULT_MODEL, "think": None, "default": True, "note": "기본: 생각 끔, TALK 한 번 약 1.5초"},
    {"model": "gpt-oss:20b", "think": "medium", "default": False, "note": "서버의 옛 기본값"},
]
OFF = (None, "", "off", False, "none")
FIELDS = {f.name for f in fields(E.RoomSettings)}


def make(d: dict | None) -> E.RoomSettings:
    """Settings from the page (or from storage); ValueError / TypeError on a bad value."""
    d = {k: v for k, v in (d or {}).items() if k in FIELDS}
    d.setdefault("model", DEFAULT_MODEL)
    think = d.pop("think", None)
    off = think in OFF or (isinstance(think, str) and think.strip().lower() in ("off", "none"))
    d["api_key_env"] = d.get("api_key_env") or DEFAULT_KEY
    if d["api_key_env"] not in KEY_NAMES:
        raise ValueError(f"api_key_env는 {DEFAULT_KEY}만 쓸 수 있습니다 (OLLAMA_API_KEY1은 연구자가 켠 때만).")
    s = E.RoomSettings(**d, think="low" if off else think)
    if off:
        s.think = None
    return s


def defaults() -> dict:
    """/models ``defaults`` (the server's, with the arena's model and think)."""
    return {k: v for k, v in asdict(make({})).items() if k != "seed"}

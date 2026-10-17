"""Which Ollama key a room's model seats use (researcher's rule, 10-17).

Only two keys exist as Worker secrets: ``OLLAMA_API_KEY3`` (every model call by default) and ``OLLAMA_API_KEY1``.
Key 1 is allowed only while the plain Worker variable ``OLLAMA_KEY1_ENABLED`` is exactly ``"on"``; it is set by hand
in the Cloudflare dashboard, never in wrangler.toml (``keep_vars = true`` keeps it across deploys). There is no
fallback: a failed call with key 3 fails; a missing key 3 refuses model seats. The client may name only
``OLLAMA_API_KEY3``, or ``OLLAMA_API_KEY1`` while the switch is on.
"""

from __future__ import annotations

DEFAULT_KEY = "OLLAMA_API_KEY3"
KEY1 = "OLLAMA_API_KEY1"
KEY1_SWITCH = "OLLAMA_KEY1_ENABLED"


class KeyError_(ValueError):
    """A key the room may not use, or one the Worker does not hold; ``str()`` is the Korean message for the page."""


def key1_enabled(env_get) -> bool:
    """``env_get(name) -> str | None``. Exactly "on" (case-sensitive, no spaces); anything else is off."""
    return env_get(KEY1_SWITCH) == "on"


def choose_key(requested: str | None, env_get) -> str:
    """The secret name a room's model seats use. ``requested`` is the room's ``api_key_env`` (None / "" = default)."""
    name = (requested or DEFAULT_KEY)
    if name == DEFAULT_KEY:
        return name
    if name == KEY1:
        if key1_enabled(env_get):
            return name
        raise KeyError_("OLLAMA_API_KEY1은 연구자가 대시보드에서 켜 둔 때만 쓸 수 있습니다 "
                        f"({KEY1_SWITCH} = on). 지금은 꺼져 있습니다.")
    raise KeyError_(f"api_key_env는 {DEFAULT_KEY}만 쓸 수 있습니다 ({KEY1}은 연구자가 켠 때만).")


def key_value(name: str, env_get) -> str:
    """The secret's value; a missing secret refuses the call (never another key)."""
    value = (env_get(name) or "").strip()
    if not value:
        raise KeyError_(f"서버에 {name} 비밀값이 없어 모델 좌석을 쓸 수 없습니다 "
                        f"(wrangler secret put {name}).")
    return value

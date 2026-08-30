"""Cross-cutting pieces shared by every routes_*.py module and reporting.py:
CORS origin resolution, the process-wide repository singleton, the
in-memory human-play session store, rate limiting, and input sanitisation
(nickname / campaign id).
"""

import os
import re
import threading
import time
from collections import defaultdict

import tiktoken
from fastapi import HTTPException, Request

from squid_arena.human_game import HumanGameSession
from squid_arena.remote_provider import ArenaProgress
from squid_store import get_repository

# ---------------------------------------------------------------------------
# CORS — GitHub Pages frontend origin, configurable via env var.
# ---------------------------------------------------------------------------

# Sensible default allow-list (GitHub Pages site + common local dev servers).
# Override entirely via WEB_ARENA_CORS_ORIGINS (comma-separated), e.g.
#   WEB_ARENA_CORS_ORIGINS="https://gist-dslab.github.io,http://localhost:5500"
_DEFAULT_CORS_ORIGINS = [
    "https://gist-dslab.github.io",
    "https://irregular6612.github.io",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8080",
]


def _cors_origins() -> list[str]:
    raw = os.environ.get("WEB_ARENA_CORS_ORIGINS")
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if origins:
            return origins
    return _DEFAULT_CORS_ORIGINS


# ---------------------------------------------------------------------------
# In-memory session store (single-server, for local use).
# ---------------------------------------------------------------------------

_sessions: dict[str, HumanGameSession] = {}

# Nickname per API session_id (kept out of HumanGameSession — that class
# stays framing/game-mechanics only, per the WP2 brief).
_nicknames: dict[str, str] = {}

# Campaign id per API session_id — shared by the 6 games of one Play run so the
# Play Leaderboard can sum a player's cumulative score. ``None`` for one-off
# games that did not supply one.
_campaigns: dict[str, str | None] = {}

# Guards against double-persisting the same session's result. The lock makes
# the check-then-insert atomic across FastAPI's sync-route threadpool; the DB
# row (session id is a PRIMARY KEY) is the durable source of truth across a
# process restart, when the in-process set is lost.
_persisted_session_ids: set[str] = set()
_persist_lock = threading.Lock()

# Guards the check-then-insert on the ``players`` table (nickname registration
# vs. password verification) against concurrent requests for the same
# nickname racing each other.
_player_lock = threading.Lock()

# Whether finished human plays are written to the shared DB. Re-enabled on
# 2026-07-03 to power the human Play Leaderboard (campaign totals) — each of a
# player's 6 games is stored with a shared campaign_id so the leaderboard can
# sum their cumulative score. scripts/arena/purge_human_sessions.py can still drop
# human rows on demand.
PERSIST_HUMAN_SESSIONS = True

# Token counter for reasoning text.
_encoding = tiktoken.get_encoding("cl100k_base")

# Module-level repository singleton (driver-agnostic; see squid_store).
# Reads WEB_ARENA_DSN, falls back to a local SQLite file.
_repository = get_repository()

# LLM Arena: live progress per background run_id (see web/squid_arena/arena.py).
_arena_runs: dict[str, "ArenaProgress"] = {}
_arena_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Nickname sanitization
# ---------------------------------------------------------------------------

DEFAULT_NICKNAME = "Anonymous"
_MAX_NICKNAME_LEN = 32
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_nickname(raw: str | None) -> str:
    """Strip control chars, collapse whitespace, cap length. Blank -> default.

    Never let a client-supplied nickname reach the database unsanitized.
    """
    if not raw:
        return DEFAULT_NICKNAME
    cleaned = _CONTROL_CHARS_RE.sub("", raw)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    if not cleaned:
        return DEFAULT_NICKNAME
    return cleaned[:_MAX_NICKNAME_LEN]


_CAMPAIGN_ID_RE = re.compile(r"[^A-Za-z0-9_-]")
_MAX_CAMPAIGN_ID_LEN = 64


def sanitize_campaign_id(raw: str | None) -> str | None:
    """Keep only URL-safe id chars, cap length. Blank/None -> None.

    The campaign id is an opaque client-generated token; restricting it to
    ``[A-Za-z0-9_-]`` keeps a rogue value from reaching the database unsanitized.
    """
    if not raw:
        return None
    cleaned = _CAMPAIGN_ID_RE.sub("", raw)[:_MAX_CAMPAIGN_ID_LEN]
    return cleaned or None


# ---------------------------------------------------------------------------
# Rate limiting — simple in-process sliding window per client IP.
# No external deps (no redis); resets on process restart, which is
# acceptable for a free-tier single-instance backend.
# ---------------------------------------------------------------------------

_RATE_LIMIT_MAX = int(os.environ.get("WEB_ARENA_RATE_LIMIT_MAX", "30"))
_RATE_LIMIT_WINDOW_SECONDS = float(os.environ.get("WEB_ARENA_RATE_LIMIT_WINDOW_SECONDS", "60"))
_rate_limit_hits: dict[str, list[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    """Best-effort client identifier for rate-limit bucketing.

    On Render/Fly/HF a TLS/proxy sits in front of the container, so
    ``request.client.host`` is the proxy's IP for every request — that would
    collapse all clients into one shared bucket and let one heavy player lock
    everyone out. Use the first hop of ``X-Forwarded-For`` when present.

    Trust boundary: ``X-Forwarded-For`` is client-spoofable, so a determined
    abuser can evade the limit by rotating the header. That is acceptable for
    an anonymous, free-tier benchmark (there is no auth to protect and the
    hosting edge — Render/Fly/HF — sets XFF itself); the limiter is only a
    courtesy throttle, not a security control.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first_hop = xff.split(",")[0].strip()
        if first_hop:
            return first_hop
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request, bucket: str) -> None:
    key = f"{bucket}:{_client_key(request)}"
    now = time.monotonic()
    hits = _rate_limit_hits[key]
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    while hits and hits[0] < cutoff:
        hits.pop(0)
    if len(hits) >= _RATE_LIMIT_MAX:
        raise HTTPException(429, "Rate limit exceeded. Please slow down and try again shortly.")
    hits.append(now)


# Matches the "Current status:" line plus the indented "  - ..." bullet lines
# that follow it. Those bullets carry only Turn/Round + score, which the web
# UI already renders as stat tiles, so we strip them from the threat box.
_STATUS_BLOCK_RE = re.compile(r"\n?Current status:\n(?:[ \t]*-[^\n]*\n?)*")


def _strip_status_block(text: str) -> str:
    """Remove the turn/score status block from framing text for display."""
    return _STATUS_BLOCK_RE.sub("\n", text).strip()

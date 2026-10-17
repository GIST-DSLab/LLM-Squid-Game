"""The model calls a room is waiting for, made by the Durable Object one at a time.

One at a time: Ollama Cloud's free plan serves one request per key at a time (more queue, then are refused), so a
room never fires its model seats' calls in parallel; a batch of three model seats takes three calls in a row (the
people see ``busy`` / ``thinking_since`` on those seats meanwhile, as on the server).

A failed call is an empty reply charged 0 tokens with the error in ``model_call`` (the server's ``ModelSeat``); it is
never retried with another key (keys.py).
"""

from __future__ import annotations

import time

import keys
import ollama_fetch
from squid5.core.providers import Reply
from web.server import engine as E


def local_base(env_get) -> str:
    """``OLLAMA_BASE_URL`` for local tests (tests/fake_ollama.py): only a loopback address is honoured, so a stray
    value in production can never send a key to another host."""
    url = (env_get("OLLAMA_BASE_URL") or "").strip()
    return url if url.startswith(("http://127.0.0.1:", "http://localhost:")) else ""


async def run_job(room, key: tuple, info: dict, env_get, transport, clock=time.time, sleep=None) -> None:
    """Make one model call for ``room`` and record it (or its failure)."""
    s = room.settings
    room.inflight.add(key)
    agent = key[1]
    on_delta = (lambda kind, piece: room.stream_delta(agent, kind, piece)) if info["kind"] == "solve" else None
    t0, error = clock(), None
    try:
        name = keys.choose_key(s.api_key_env, env_get)  # checked at every call: the switch may be off by now
        secret = keys.key_value(name, env_get)
        extra = {"sleep": sleep} if sleep else {}
        reply = await ollama_fetch.complete(transport, secret, s.model, info["messages"], info["cap"], think=s.think,
                                            timeout=s.model_timeout, retries=s.model_retries, on_delta=on_delta,
                                            base_url=local_base(env_get), **extra)
    except Exception as err:  # noqa: BLE001 - a failed call is an invalid reply, never a crashed room
        error = f"{type(err).__name__}: {err}"[:500]
        reply = Reply("", 0, thinking=f"model call failed: {error}")
    if key in room.needs:  # the room may have been reloaded meanwhile; a reply for a need it no longer has is dropped
        room.record_model(key, reply, clock() - t0, error)
    else:
        room.inflight.discard(key)


async def run_all(room, env_get, transport, budget_s: float = 600.0, clock=time.time, sleep=None, on_step=None) -> int:
    """Make the room's model calls one by one, replaying after each completed batch, until none is left or
    ``budget_s`` has passed (an alarm has 15 minutes of wall time). ``on_step()`` (async) runs after each call (the
    Durable Object saves there, so a reply is never asked for twice). Returns the number of calls made."""
    made, t0 = 0, clock()
    while room.status == "running" and clock() - t0 < budget_s:
        jobs = room.model_jobs()
        if not jobs:
            break
        key, info = jobs[0]
        await run_job(room, key, info, env_get, transport, clock, sleep)
        made += 1
        room.advance()
        if on_step is not None:
            await on_step()
    return made


__all__ = ["run_job", "run_all", "E"]

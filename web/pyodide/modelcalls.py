"""The model calls a room is waiting for, made by the browser engine one at a time through the thin Worker.

One at a time: Ollama Cloud's free plan serves one request per key at a time (more queue, then are refused), so a
room never fires its model seats' calls in parallel; a batch of three model seats takes three calls in a row (the
person sees ``busy`` / ``thinking_since`` on those seats meanwhile, as on the server).

``Link`` is where a call goes: the Worker's Ollama-compatible endpoint (``<worker>/llm/api/chat``) and the game's
signed token in place of an API key. The Worker holds the key (web/cloudflare/src/keys.py: KEY3 by default, KEY1 only
while switched on, never as a fallback) and counts the calls. A failed call is an empty reply charged 0 tokens with the
error in ``model_call`` (the server's ``ModelSeat``); it is never retried with another key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import ollama_fetch
from squid5.core.providers import Reply
from web.server import engine as E


@dataclass
class Link:
    base_url: str  # the Worker origin + "/llm" (ollama_fetch appends /api/chat)
    token: str  # the game token the Worker issued (POST /api/games); sent as the Bearer value


async def run_job(room, key: tuple, info: dict, link: Link, transport, clock=time.time, sleep=None) -> None:
    """Make one model call for ``room`` and record it (or its failure)."""
    s = room.settings
    room.inflight.add(key)
    agent = key[1]
    on_delta = (lambda kind, piece: room.stream_delta(agent, kind, piece)) if info["kind"] == "solve" else None
    t0, error = clock(), None
    try:
        if not link.token:
            raise ollama_fetch.Fatal("게임 토큰이 없어 모델을 부를 수 없습니다(Worker에 연결하지 못함).")
        extra = {"sleep": sleep} if sleep else {}
        reply = await ollama_fetch.complete(transport, link.token, s.model, info["messages"], info["cap"],
                                            think=s.think, timeout=s.model_timeout, retries=s.model_retries,
                                            on_delta=on_delta, base_url=link.base_url, **extra)
    except Exception as err:  # noqa: BLE001 - a failed call is an invalid reply, never a crashed room
        error = f"{type(err).__name__}: {err}"[:500]
        reply = Reply("", 0, thinking=f"model call failed: {error}")
    if key in room.needs:  # the room may have been rebuilt meanwhile; a reply for a need it no longer has is dropped
        room.record_model(key, reply, clock() - t0, error)
        if error:  # shown at once; the replay that completes the batch writes the same warning again
            seat = room.seats.get(agent)
            room.warn(f"{getattr(seat, 'name', agent)} ({agent}) R{info['round']} {E.label(info['kind'], info['turn'])}: "
                      f"모델 호출 실패 - 빈 답으로 처리 ({error})")
    else:
        room.inflight.discard(key)


async def run_all(room, link: Link, transport, budget_s: float = 3600.0, clock=time.time, sleep=None,
                  on_step=None) -> int:
    """Make the room's model calls one by one, replaying after each completed batch, until none is left or
    ``budget_s`` has passed. ``on_step()`` (sync or async) runs after each call (the page saves there, so a reply is
    never asked for twice). Returns the number of calls made."""
    made, t0 = 0, clock()
    while room.status == "running" and clock() - t0 < budget_s:
        jobs = room.model_jobs()
        if not jobs:
            break
        key, info = jobs[0]
        await run_job(room, key, info, link, transport, clock, sleep)
        made += 1
        room.advance()
        if on_step is not None:
            out = on_step()
            if hasattr(out, "__await__"):
                await out
    return made


__all__ = ["Link", "run_job", "run_all", "E"]

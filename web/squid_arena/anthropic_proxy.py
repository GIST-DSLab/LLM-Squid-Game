"""Transparent Anthropic API proxy for capturing extended-thinking traces.

Claude Code ships every `POST /v1/messages` to `api.anthropic.com`. When the
`ANTHROPIC_BASE_URL` env var points at this proxy, the proxy forwards every
byte unchanged (including SSE stream frames) while sniffing out the
`thinking_delta` events and appending one JSONL record per API call to
`$SQUID_THINKING_LOG_DIR/api_calls.jsonl`.

Design goals:

  * **Non-invasive**: the client (Claude Code) sees byte-identical upstream
    responses. Headers and status codes are preserved; the only stripped
    response headers are `content-length`, `transfer-encoding`,
    `content-encoding` (to let FastAPI/Starlette recompute them).
  * **Stream-safe**: SSE chunks are forwarded to the client *before* being
    parsed, so there is no added latency on the hot path.
  * **Fail-open**: if log writing or SSE parsing fails, the proxying
    continues. We never break the client because of our logging.
  * **Session correlation**: the request body is scanned for
    `session_id=<hex>` patterns (present in the squid-game player agent's
    Bash curl commands and in its initial user prompt), and /api/action
    tool-use invocations are counted to derive a `turn_number` for the
    current call.

Run:

    uv run uvicorn interface.anthropic_proxy:app --port 8765

Env:

    ANTHROPIC_UPSTREAM_URL       upstream base URL (default https://api.anthropic.com)
    SQUID_THINKING_LOG_DIR       directory for api_calls.jsonl (default
                                 outputs/api_sessions/thinking_traces)
    SQUID_PROXY_DEBUG            if set, emit proxy-side debug to stderr
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

UPSTREAM_URL = os.environ.get("ANTHROPIC_UPSTREAM_URL", "https://api.anthropic.com").rstrip("/")

_default_log_dir = Path(__file__).resolve().parent.parent / "outputs" / "api_sessions" / "thinking_traces"
LOG_DIR = Path(os.environ.get("SQUID_THINKING_LOG_DIR", str(_default_log_dir)))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "api_calls.jsonl"

DEBUG = bool(os.environ.get("SQUID_PROXY_DEBUG"))

# Hop-by-hop and body-length headers we must not forward verbatim.
_STRIPPED_REQUEST_HEADERS = {"host", "content-length", "connection", "accept-encoding"}
_STRIPPED_RESPONSE_HEADERS = {"content-length", "transfer-encoding", "content-encoding", "connection"}

# Regexes for session/turn inference.
SESSION_ID_RE = re.compile(r"session_id[\"'\s]*[:=][\s\"']*([0-9a-fA-F][0-9a-fA-F\-]{7,})")
ACTION_URL_RE = re.compile(r"/api/action\?session_id=")

_log_lock = asyncio.Lock()
_client: httpx.AsyncClient | None = None

app = FastAPI(title="Anthropic Proxy — Squid-Game thinking logger")


def _log_debug(*args) -> None:
    if DEBUG:
        print("[anthropic_proxy]", *args, file=sys.stderr, flush=True)


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=UPSTREAM_URL,
            timeout=httpx.Timeout(600.0, connect=30.0),
            follow_redirects=False,
            http2=False,
        )
    return _client


# ---------------------------------------------------------------------------
# Correlation: session_id + turn_number inference
# ---------------------------------------------------------------------------


def _flatten_body_text(body: dict) -> str:
    """Concatenate every string we can find in the request body, so a single
    regex pass can locate the session_id anywhere (system prompt, tool_use
    input, tool_result output, plain user messages)."""

    parts: list[str] = []
    system = body.get("system")
    if isinstance(system, str):
        parts.append(system)
    elif isinstance(system, list):
        for block in system:
            if isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)

    for msg in body.get("messages") or []:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                bt = block.get("type")
                if bt == "text":
                    parts.append(block.get("text") or "")
                elif bt == "tool_use":
                    inp = block.get("input")
                    if isinstance(inp, dict):
                        for v in inp.values():
                            if isinstance(v, str):
                                parts.append(v)
                elif bt == "tool_result":
                    c = block.get("content")
                    if isinstance(c, str):
                        parts.append(c)
                    elif isinstance(c, list):
                        for sub in c:
                            if isinstance(sub, dict):
                                t = sub.get("text")
                                if isinstance(t, str):
                                    parts.append(t)
    return "\n".join(parts)


def _extract_session_and_turn(body: dict) -> tuple[str | None, int]:
    haystack = _flatten_body_text(body)
    sid = None
    m = SESSION_ID_RE.search(haystack)
    if m:
        sid = m.group(1)
    # Turn inference: the player agent finalizes each turn with a POST to
    # /api/action. The number of /api/action occurrences in the conversation
    # so far equals the number of COMPLETED turns; the current call is
    # therefore the (completed + 1)-th turn in progress.
    completed_actions = len(ACTION_URL_RE.findall(haystack))
    turn_number = completed_actions + 1
    return sid, turn_number


# ---------------------------------------------------------------------------
# Thinking extraction
# ---------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    """Rough token estimate (same order of magnitude as MLX server's
    whitespace heuristic). Used only for reasoning_investment fields when
    the upstream usage block doesn't expose thinking_tokens separately."""

    if not text:
        return 0
    return max(1, len(text) // 4)


def _extract_from_nonstream(resp_json: dict) -> tuple[str | None, str, dict]:
    thinking_parts: list[str] = []
    text_parts: list[str] = []
    for block in resp_json.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "thinking":
            t = block.get("thinking")
            if isinstance(t, str):
                thinking_parts.append(t)
        elif block.get("type") == "text":
            t = block.get("text")
            if isinstance(t, str):
                text_parts.append(t)
    thinking_text = "".join(thinking_parts) if thinking_parts else None
    text = "".join(text_parts)
    usage = resp_json.get("usage") or {}
    return thinking_text, text, usage


async def _write_log(record: dict) -> None:
    async with _log_lock:
        try:
            with LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:  # fail-open
            _log_debug("log write failed:", exc)


def _build_record(
    *,
    call_id: str,
    session_id: str | None,
    turn_number: int,
    model: str,
    started_at: str,
    ended_at: str,
    thinking_text: str | None,
    text: str,
    usage: dict,
) -> dict:
    thinking_tokens = (
        usage.get("thinking_output_tokens")
        or usage.get("cache_creation_input_tokens")  # conservative fallback
        or _approx_tokens(thinking_text or "")
    )
    steps = (thinking_text or "").count("\n\n") + 1 if thinking_text else 0
    return {
        "call_id": call_id,
        "session_id": session_id,
        "turn_number": turn_number,
        "model": model,
        "started_at": started_at,
        "ended_at": ended_at,
        "timestamp": ended_at,
        "thinking_text": thinking_text,
        "raw_response": text,
        "response_text": text,
        "reasoning_investment": {
            "total_tokens": int(usage.get("output_tokens", 0) or 0),
            "reasoning_steps": steps,
            "thinking_tokens": int(thinking_tokens or 0),
        },
        "usage": usage,
    }


# ---------------------------------------------------------------------------
# Streaming proxy
# ---------------------------------------------------------------------------


async def _stream_proxy(
    *,
    body_bytes: bytes,
    headers: dict[str, str],
    session_id: str | None,
    turn_number: int,
    call_id: str,
    model: str,
) -> Response:
    client = await _get_client()
    req = client.build_request("POST", "/v1/messages", content=body_bytes, headers=headers)
    upstream = await client.send(req, stream=True)

    resp_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in _STRIPPED_RESPONSE_HEADERS
    }
    media_type = upstream.headers.get("content-type", "text/event-stream")

    started_at = datetime.now(timezone.utc).isoformat()

    async def body_gen() -> AsyncIterator[bytes]:
        thinking_parts: list[str] = []
        text_parts: list[str] = []
        usage: dict = {}
        buffer = b""

        try:
            async for chunk in upstream.aiter_raw():
                # 1. forward to client FIRST (no added latency)
                yield chunk

                # 2. opportunistic parse for logging
                try:
                    buffer += chunk
                    while b"\n\n" in buffer:
                        event_block, buffer = buffer.split(b"\n\n", 1)
                        for line in event_block.split(b"\n"):
                            if not line.startswith(b"data: "):
                                continue
                            payload = line[6:]
                            if not payload:
                                continue
                            try:
                                evt = json.loads(payload.decode("utf-8", "replace"))
                            except Exception:
                                continue
                            t = evt.get("type")
                            if t == "content_block_delta":
                                delta = evt.get("delta") or {}
                                dt = delta.get("type")
                                if dt == "thinking_delta":
                                    tt = delta.get("thinking")
                                    if isinstance(tt, str):
                                        thinking_parts.append(tt)
                                elif dt == "text_delta":
                                    tx = delta.get("text")
                                    if isinstance(tx, str):
                                        text_parts.append(tx)
                            elif t == "message_delta":
                                u = evt.get("usage")
                                if isinstance(u, dict):
                                    usage.update(u)
                            elif t == "message_start":
                                msg = evt.get("message") or {}
                                u = msg.get("usage")
                                if isinstance(u, dict):
                                    usage.update(u)
                except Exception as exc:  # fail-open on parse errors
                    _log_debug("sse parse error:", exc)
        finally:
            try:
                await upstream.aclose()
            except Exception:
                pass

            ended_at = datetime.now(timezone.utc).isoformat()
            thinking_text = "".join(thinking_parts) if thinking_parts else None
            record = _build_record(
                call_id=call_id,
                session_id=session_id,
                turn_number=turn_number,
                model=model,
                started_at=started_at,
                ended_at=ended_at,
                thinking_text=thinking_text,
                text="".join(text_parts),
                usage=usage,
            )
            await _write_log(record)

    return StreamingResponse(
        body_gen(),
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=media_type,
    )


# ---------------------------------------------------------------------------
# Non-streaming proxy
# ---------------------------------------------------------------------------


async def _buffered_proxy(
    *,
    body_bytes: bytes,
    headers: dict[str, str],
    session_id: str | None,
    turn_number: int,
    call_id: str,
    model: str,
) -> Response:
    client = await _get_client()
    started_at = datetime.now(timezone.utc).isoformat()
    upstream = await client.post("/v1/messages", content=body_bytes, headers=headers)
    ended_at = datetime.now(timezone.utc).isoformat()

    thinking_text: str | None = None
    text = ""
    usage: dict = {}
    if 200 <= upstream.status_code < 300:
        try:
            resp_json = upstream.json()
            thinking_text, text, usage = _extract_from_nonstream(resp_json)
        except Exception as exc:
            _log_debug("buffered parse error:", exc)

    await _write_log(
        _build_record(
            call_id=call_id,
            session_id=session_id,
            turn_number=turn_number,
            model=model,
            started_at=started_at,
            ended_at=ended_at,
            thinking_text=thinking_text,
            text=text,
            usage=usage,
        )
    )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in _STRIPPED_RESPONSE_HEADERS
        },
        media_type=upstream.headers.get("content-type"),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/v1/messages")
async def messages(request: Request) -> Response:
    body_bytes = await request.body()
    try:
        body = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        body = {}

    session_id, turn_number = _extract_session_and_turn(body) if body else (None, 1)
    model = body.get("model", "unknown") if body else "unknown"
    call_id = uuid.uuid4().hex[:16]

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _STRIPPED_REQUEST_HEADERS
    }

    is_stream = bool(body.get("stream")) if body else False

    if is_stream:
        return await _stream_proxy(
            body_bytes=body_bytes,
            headers=headers,
            session_id=session_id,
            turn_number=turn_number,
            call_id=call_id,
            model=model,
        )
    else:
        return await _buffered_proxy(
            body_bytes=body_bytes,
            headers=headers,
            session_id=session_id,
            turn_number=turn_number,
            call_id=call_id,
            model=model,
        )


@app.get("/_proxy/health")
async def health():
    return {
        "status": "ok",
        "upstream": UPSTREAM_URL,
        "log_file": str(LOG_FILE),
        "log_exists": LOG_FILE.exists(),
        "log_lines": _count_log_lines(),
    }


@app.get("/_proxy/session/{session_id}")
async def session_lookup(session_id: str):
    """Tail of records for a given session_id — used by the verification hook."""

    rows = []
    if not LOG_FILE.exists():
        return {"session_id": session_id, "count": 0, "records": rows}
    try:
        with LOG_FILE.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("session_id") == session_id:
                    rows.append(rec)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"session_id": session_id, "count": len(rows), "records": rows}


def _count_log_lines() -> int:
    if not LOG_FILE.exists():
        return 0
    try:
        with LOG_FILE.open("rb") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return -1


# Pass-through for everything else the SDK might hit (/v1/models, /v1/complete, …).
@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def passthrough(full_path: str, request: Request) -> Response:
    client = await _get_client()
    body_bytes = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _STRIPPED_REQUEST_HEADERS
    }
    upstream = await client.request(
        request.method,
        f"/{full_path}",
        content=body_bytes,
        headers=headers,
        params=request.query_params,
    )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            k: v
            for k, v in upstream.headers.items()
            if k.lower() not in _STRIPPED_RESPONSE_HEADERS
        },
        media_type=upstream.headers.get("content-type"),
    )

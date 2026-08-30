"""LLM Arena (BYOE — Bring Your Own Endpoint) routes.

    POST /api/arena/run     — start a background arena season against a participant endpoint
    GET  /api/arena/status  — live progress + result for an arena run
"""

import threading
import uuid

from fastapi import APIRouter, HTTPException, Request

from squid_arena import deps, schemas
from squid_arena.arena import (
    VALID_DIFFICULTIES,
    VALID_FORFEITS,
    VALID_FRAMINGS,
    run_arena_session,
)
from squid_arena.remote_provider import ArenaProgress

router = APIRouter()


@router.post("/api/arena/run", response_model=schemas.ArenaRunResponse)
def arena_run(req: schemas.ArenaRunRequest, request: Request):
    """Start a background arena season against a participant endpoint.

    The server drives the full split-call pipeline (task / probe / forfeit per
    turn), scoring with the same Core Engine used for the built-in models.
    Poll GET /api/arena/status?run_id=... for live progress and the result.
    """
    deps._check_rate_limit(request, "arena")

    if req.framing not in VALID_FRAMINGS:
        raise HTTPException(400, f"Unknown framing '{req.framing}'.")
    if req.forfeit not in VALID_FORFEITS:
        raise HTTPException(400, f"Unknown forfeit condition '{req.forfeit}'.")
    if req.difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(400, f"Unknown difficulty '{req.difficulty}'.")

    model_label = deps.sanitize_nickname(req.model_label) or "anon-model"

    run_id = uuid.uuid4().hex[:12]
    progress = ArenaProgress()
    progress.calls_total = req.total_turns * 3
    with deps._arena_lock:
        deps._arena_runs[run_id] = progress

    def _work() -> None:
        try:
            run_arena_session(
                deps._repository,
                endpoint_url=req.endpoint_url,
                model_label=model_label,
                framing=req.framing,
                forfeit=req.forfeit,
                difficulty=req.difficulty,
                auth_header=req.auth_header,
                auth_value=req.auth_value,
                total_turns=req.total_turns,
                max_tokens=req.max_tokens,
                progress=progress,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced to the participant
            progress.fail(str(exc))

    threading.Thread(target=_work, name=f"arena-{run_id}", daemon=True).start()
    return schemas.ArenaRunResponse(run_id=run_id)


@router.get("/api/arena/status", response_model=schemas.ArenaStatusResponse)
def arena_status(run_id: str):
    """Live progress + result for an arena run."""
    progress = deps._arena_runs.get(run_id)
    if progress is None:
        raise HTTPException(404, f"Arena run {run_id} not found.")
    return schemas.ArenaStatusResponse(**progress.snapshot())

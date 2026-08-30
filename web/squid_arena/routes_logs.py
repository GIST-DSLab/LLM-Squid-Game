"""Logs and report routes.

    GET /api/logs                — list past sessions (LLM + human)
    GET /api/logs/{session_id}   — turn-by-turn trace for one session
    GET /api/report              — per-subject stats report for the Logs screen
"""

from collections import defaultdict

from fastapi import APIRouter, HTTPException

from squid_arena import deps, reporting, schemas
from squid_store import TurnRecord

router = APIRouter()


@router.get("/api/logs", response_model=schemas.LogsResponse)
def list_logs(
    source: str | None = None,
    task: str | None = None,
    framing: str | None = None,
):
    """List sessions (LLM + human), newest first. Optional filters."""
    sessions = deps._repository.list_sessions(source=source, task=task, framing=framing)
    return schemas.LogsResponse(sessions=[reporting._session_record_to_row(s) for s in sessions])


@router.get("/api/logs/{session_id}", response_model=schemas.LogDetailResponse)
def get_log_detail(session_id: str):
    """Turn-by-turn trace for one session (LLM or human)."""
    session = deps._repository.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found.")

    turns = deps._repository.list_turns(session_id)
    return schemas.LogDetailResponse(
        session=reporting._session_record_to_row(session),
        turns=[
            schemas.LogTurnRow(
                turn_no=t.turn_no,
                observation=t.observation,
                action=t.action,
                ri_task=t.ri_task,
                ri_probe=t.ri_probe,
                ri_forfeit=t.ri_forfeit,
                choice=t.choice,
                score=t.score,
                thinking_task=t.thinking_task,
                thinking_probe=t.thinking_probe,
                thinking_forfeit=t.thinking_forfeit,
                raw_response=t.raw_response,
                correct=t.correct,
                psuccess_self=t.psuccess_self,
            )
            for t in turns
        ],
    )


@router.get("/api/report", response_model=schemas.ReportResponse)
def get_report(source: str, key: str):
    """Per-subject stats report for the Logs screen.

    ``source='human'`` groups a player's (``key`` = nickname) sessions into
    campaigns with per-game correctness cells. ``source='llm'`` aggregates a
    model's (``key`` = model_label) sessions into per-condition correctness
    rates and joins the stored ``model_stats`` row. One batch turn query backs
    the whole report (no N+1)."""
    if source not in ("human", "llm"):
        raise HTTPException(400, "source must be 'human' or 'llm'.")

    sessions = deps._repository.list_sessions(source=source, nickname=key)
    turns = deps._repository.list_turns_for_sessions([s.id for s in sessions])
    turns_by_session: dict[str, list[TurnRecord]] = defaultdict(list)
    for t in turns:
        turns_by_session[t.session_id].append(t)

    resp = schemas.ReportResponse(
        source=source,
        key=key,
        n_sessions=len(sessions),
        sessions=[reporting._session_record_to_row(s) for s in sessions],
    )
    if source == "human":
        resp.campaigns = reporting._build_human_report(sessions, turns_by_session)
    else:
        resp.conditions = reporting._build_llm_report(sessions, turns_by_session)
        stats = next((r for r in deps._repository.list_model_stats() if r.model_label == key), None)
        resp.model_stats = reporting._model_stats_to_row(stats) if stats else None
        resp.mediation = reporting._build_mediation(stats)
        resp.verbal_reasons = reporting._build_verbal_reasons(stats)
    return resp

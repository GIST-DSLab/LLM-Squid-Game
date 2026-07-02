"""REST API for the LLM Squid Game — enables external agents (Claude Code, etc.)
and the Web Arena frontend to play the game via HTTP without accessing the
codebase directly.

Endpoints:
    POST /api/new_game            — start a new game session (nickname + arena config)
    GET  /api/state               — get current turn state (system prompt + observation)
    POST /api/action              — submit action + probe + reasoning
    GET  /api/result              — get final season result; persists on game over
    GET  /api/leaderboard/models  — Model Leaderboard (Open/Closed, β descending)
    GET  /api/leaderboard/play    — Play Leaderboard (human sessions by score)
    GET  /api/logs                — list past sessions (LLM + human)
    GET  /api/logs/{session_id}   — turn-by-turn trace for one session

Run:
    uv run uvicorn interface.api:app --port 8502

The reasoning field in /api/action captures the agent's thinking process,
stored as thinking_text in TurnResult for RI analysis comparable to LLM
experiments.

Scoring is always computed server-side via HumanGameSession — this module
never accepts a client-submitted final score. Persistence uses WP1's
driver-agnostic Repository interface (``interface/persistence``) only;
never a concrete DB driver.
"""

import os
import re
import sys
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

# Ensure project root is on sys.path.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import tiktoken
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from interface.human_game import HumanGameSession
from interface.persistence import (
    ModelStatsRecord,
    SessionRecord,
    TurnRecord,
    get_repository,
)

app = FastAPI(
    title="LLM Squid Game API",
    description="REST API for external agents to play the Squid Game benchmark.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS — GitHub Pages frontend origin, configurable via env var.
# ---------------------------------------------------------------------------

# Sensible default allow-list (GitHub Pages site + common local dev servers).
# Override entirely via WEB_ARENA_CORS_ORIGINS (comma-separated), e.g.
#   WEB_ARENA_CORS_ORIGINS="https://irregular6612.github.io,http://localhost:5500"
_DEFAULT_CORS_ORIGINS = [
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory session store (single-server, for local use).
# ---------------------------------------------------------------------------

_sessions: dict[str, HumanGameSession] = {}

# Nickname per API session_id (kept out of HumanGameSession — that class
# stays framing/game-mechanics only, per the WP2 brief).
_nicknames: dict[str, str] = {}

# Guards against double-persisting the same session's result. The lock makes
# the check-then-insert atomic across FastAPI's sync-route threadpool; the DB
# row (session id is a PRIMARY KEY) is the durable source of truth across a
# process restart, when the in-process set is lost.
_persisted_session_ids: set[str] = set()
_persist_lock = threading.Lock()

# Token counter for reasoning text.
_encoding = tiktoken.get_encoding("cl100k_base")

# Module-level repository singleton (driver-agnostic; see interface/persistence).
# Reads WEB_ARENA_DSN, falls back to a local SQLite file.
_repository = get_repository()


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


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class NewGameRequest(BaseModel):
    task_name: str = "signal_game"
    difficulty: str = "easy"
    framing: str = "survival"
    forfeit_condition: str = "allowed"
    seed: int = 42
    total_turns: int = 15
    actual_death: bool = False
    starting_score: float = 0.0
    score_floor: float = 0.0
    p_death_constant: float | None = 0.15
    num_few_shot: int | None = 1
    curriculum_turns: int = 2
    nickname: str | None = Field(
        default=None,
        description=(
            "Player nickname (anonymous, no accounts). Sanitized server-side "
            "(control chars stripped, whitespace collapsed, capped at 32 "
            "chars); blank/missing falls back to 'Anonymous'."
        ),
    )


class NewGameResponse(BaseModel):
    session_id: str
    message: str


class TurnStateResponse(BaseModel):
    session_id: str
    turn_number: int
    p_death: float
    cumulative_score: float
    system_prompt: str = Field(description="Full system prompt: framing + game rules + forfeit option")
    observation: str = Field(description="User message: cumulative history + current signal")
    probe_question: str = Field(description="Side-channel probe (separate from action)")
    available_actions: list[str]
    forfeit_allowed: bool
    game_over: bool = False
    game_over_reason: str = ""
    final_score: float = 0.0


class ActionRequest(BaseModel):
    action: str = Field(description="Chosen action from available_actions, or 'forfeit'")
    probe_answer: str = Field(default="", description="Rule inference answer (probe)")
    reasoning: str = Field(
        default="",
        description=(
            "Agent's reasoning/thinking text before choosing the action. "
            "This is stored as thinking_text for Reasoning Investment analysis. "
            "Include your full chain of thought here."
        ),
    )


class ActionResponse(BaseModel):
    action_taken: str
    was_optimal: bool
    reward: float
    feedback: str
    new_score: float
    reasoning_tokens: int = Field(description="Token count of submitted reasoning")
    game_over: bool = False
    game_over_reason: str = ""


class GameResultResponse(BaseModel):
    session_id: str
    season_id: str
    framing: str
    forfeit_condition: str
    turns_played: int
    final_score: float
    survived: bool
    forfeited: bool
    forfeited_at_turn: int | None
    total_reasoning_tokens: int
    save_path: str | None = None


class ModelLeaderboardRow(BaseModel):
    """One row of the Model Leaderboard (spec §5)."""

    model_label: str
    mediation_class: str = Field(description="'open' or 'closed'")
    beta_framing_is_FC: float = Field(description="3-cov β; secondary sort key (descending)")
    hr_FC_3cov: float
    hr_FC_ci_low: float
    hr_FC_ci_high: float
    p_FC: float = Field(description="p for β_FC in the 4-cov (mediator-adjusted) Cox model")
    pct_attenuation: float
    n_sessions: int


class ModelLeaderboardResponse(BaseModel):
    """Two pre-sorted groups; frontend renders Open first (cosmetic order)."""

    open: list[ModelLeaderboardRow]
    closed: list[ModelLeaderboardRow]


class SessionSummaryRow(BaseModel):
    """One row shared by the Play Leaderboard and the Logs list."""

    session_id: str
    nickname: str
    task: str
    framing: str
    forfeit: str
    seed: int
    final_score: float
    forfeited: bool
    source: str = Field(description="'human' or 'llm'")
    created_at: str | None = None


class PlayLeaderboardResponse(BaseModel):
    task: str
    framing: str
    rows: list[SessionSummaryRow] = Field(description="Ordered by final_score descending")


class LogsResponse(BaseModel):
    sessions: list[SessionSummaryRow] = Field(description="Ordered newest-first (created_at descending)")


class LogTurnRow(BaseModel):
    turn_no: int
    observation: str
    action: str
    ri_task: float | None = None
    ri_probe: float | None = None
    ri_forfeit: float | None = None
    choice: str | None = None
    score: float


class LogDetailResponse(BaseModel):
    session: SessionSummaryRow
    turns: list[LogTurnRow]


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _session_record_to_row(s: SessionRecord) -> SessionSummaryRow:
    return SessionSummaryRow(
        session_id=s.id,
        nickname=s.nickname,
        task=s.task,
        framing=s.framing,
        forfeit=s.forfeit,
        seed=s.seed,
        final_score=s.final_score,
        forfeited=s.forfeited,
        source=s.source,
        created_at=s.created_at,
    )


def _model_stats_to_row(r: ModelStatsRecord) -> ModelLeaderboardRow:
    return ModelLeaderboardRow(
        model_label=r.model_label,
        mediation_class=r.mediation_class,
        beta_framing_is_FC=r.beta_framing_is_FC,
        hr_FC_3cov=r.hr_FC_3cov,
        hr_FC_ci_low=r.hr_FC_ci_low,
        hr_FC_ci_high=r.hr_FC_ci_high,
        p_FC=r.p_FC,
        pct_attenuation=r.pct_attenuation,
        n_sessions=r.n_sessions,
    )


def _persist_result(session_id: str, game: HumanGameSession) -> None:
    """Persist a finished human session (idempotent per session_id).

    Maps ``SeasonResult``/``TurnResult`` (Core Engine) fields onto WP1's
    ``SessionRecord``/``TurnRecord`` (persistence layer). Scoring itself is
    never recomputed here — it is read back verbatim from the already
    server-computed ``SeasonResult``.

    Concurrency-safe and idempotent: a frontend retry / double-fire of
    ``GET /api/result`` for the same finished session must never raise (no
    500) nor duplicate rows. Under FastAPI's sync-route threadpool two calls
    can race, so the whole check-and-insert runs under ``_persist_lock``; a
    duplicate insert (e.g. after a process restart lost the in-process set,
    or a cross-process race) is caught and treated as already-persisted.
    """
    with _persist_lock:
        if session_id in _persisted_session_ids:
            return
        # Durable cross-restart guard: if the row is already in the DB, the
        # in-process set was simply lost — mark and return without re-inserting.
        if _repository.get_session(session_id) is not None:
            _persisted_session_ids.add(session_id)
            return

        result = game.get_result()
        nickname = _nicknames.get(session_id, DEFAULT_NICKNAME)

        turn_scores = game.turn_scores
        turn_records: list[TurnRecord] = []
        for turn, score_after_turn in zip(result.turns, turn_scores):
            thinking_tokens = turn.reasoning_investment.thinking_tokens
            action = turn.action_outcome.action_taken if turn.action_outcome else turn.raw_response
            turn_records.append(
                TurnRecord(
                    session_id=session_id,
                    turn_no=turn.turn_number,
                    observation=turn.observation,
                    action=action,
                    # Human play collects one reasoning blob per turn (no
                    # split-call architecture); bucket it under ri_forfeit on
                    # a forfeit turn, ri_task otherwise.
                    ri_task=None if turn.forfeit_decision else thinking_tokens,
                    ri_probe=None,
                    ri_forfeit=thinking_tokens if turn.forfeit_decision else None,
                    choice=None,
                    score=score_after_turn,
                )
            )

        try:
            _repository.create_session(
                SessionRecord(
                    id=session_id,
                    nickname=nickname,
                    task=result.task_name,
                    framing=result.framing.value,
                    forfeit=result.forfeit_condition.value,
                    seed=result.seed if result.seed is not None else 0,
                    final_score=result.final_score,
                    forfeited=result.forfeited,
                    source="human",
                )
            )
        except Exception:
            # A concurrent/earlier writer already inserted this session id
            # (PRIMARY KEY conflict). Catching the driver-specific duplicate
            # error here (rather than importing sqlite3/psycopg exceptions and
            # coupling to a backend) keeps persistence idempotent: if the row
            # now exists, treat it as success; otherwise the failure was real.
            if _repository.get_session(session_id) is not None:
                _persisted_session_ids.add(session_id)
                return
            raise

        _repository.add_turns(turn_records)
        _persisted_session_ids.add(session_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/new_game", response_model=NewGameResponse)
def new_game(req: NewGameRequest, request: Request):
    """Start a new game session."""
    _check_rate_limit(request, "new_game")

    session_id = uuid.uuid4().hex[:12]
    game = HumanGameSession(
        task_name=req.task_name,
        difficulty=req.difficulty,
        framing=req.framing,
        forfeit_condition=req.forfeit_condition,
        seed=req.seed,
        total_turns=req.total_turns,
        actual_death=req.actual_death,
        starting_score=req.starting_score,
        score_floor=req.score_floor,
        p_death_constant=req.p_death_constant,
        num_few_shot=req.num_few_shot,
        curriculum_turns=req.curriculum_turns,
    )
    _sessions[session_id] = game
    _nicknames[session_id] = sanitize_nickname(req.nickname)
    return NewGameResponse(
        session_id=session_id,
        message=f"Game started. Use GET /api/state?session_id={session_id} to see Turn 1.",
    )


@app.get("/api/state", response_model=TurnStateResponse)
def get_state(session_id: str):
    """Get the current turn state."""
    game = _sessions.get(session_id)
    if not game:
        raise HTTPException(404, f"Session {session_id} not found.")

    state = game.get_turn_state()

    # Assemble full system prompt (matching TurnManager structure).
    full_system = state.framing_text
    if state.system_rules:
        full_system += "\n\n" + state.system_rules
    if state.forfeit_text:
        full_system += "\n" + state.forfeit_text

    return TurnStateResponse(
        session_id=session_id,
        turn_number=state.turn_number,
        p_death=state.p_death,
        cumulative_score=state.cumulative_score,
        system_prompt=full_system,
        observation=state.observation,
        probe_question=state.probe_question,
        available_actions=state.available_actions,
        forfeit_allowed=state.forfeit_allowed,
        game_over=state.game_over,
        game_over_reason=state.game_over_reason,
        final_score=state.final_score,
    )


@app.post("/api/action", response_model=ActionResponse)
def submit_action(session_id: str, req: ActionRequest, request: Request):
    """Submit an action (and optional probe answer + reasoning)."""
    _check_rate_limit(request, "action")

    game = _sessions.get(session_id)
    if not game:
        raise HTTPException(404, f"Session {session_id} not found.")

    if game.is_game_over:
        raise HTTPException(400, "Game is already over.")

    # Count reasoning tokens.
    reasoning_tokens = 0
    if req.reasoning:
        reasoning_tokens = len(_encoding.encode(req.reasoning))

    # Store reasoning in the turn history by appending to probe_answer
    # so it gets recorded in _turn_history as probe_prediction.
    # The actual reasoning is stored separately via _record_reasoning.
    feedback = game.submit_action(req.action, probe_answer=req.probe_answer)

    # Patch the last turn result with reasoning data.
    if game._turn_results and req.reasoning:
        from squid_game.models.results import ReasoningInvestment
        last_turn = game._turn_results[-1]
        # Create updated turn with thinking data.
        updated = last_turn.model_copy(update={
            "thinking_text": req.reasoning,
            "reasoning_investment": ReasoningInvestment(
                total_tokens=reasoning_tokens,
                reasoning_steps=max(req.reasoning.count("\n"), 1),
                thinking_tokens=reasoning_tokens,
            ),
        })
        game._turn_results[-1] = updated

    return ActionResponse(
        action_taken=feedback.action_taken,
        was_optimal=feedback.was_optimal,
        reward=feedback.reward,
        feedback=feedback.feedback_text,
        new_score=feedback.new_score,
        reasoning_tokens=reasoning_tokens,
        game_over=feedback.game_over,
        game_over_reason=feedback.game_over_reason,
    )


@app.get("/api/result", response_model=GameResultResponse)
def get_result(session_id: str, save: bool = False):
    """Get final game result. Set save=true to persist to JSONL."""
    game = _sessions.get(session_id)
    if not game:
        raise HTTPException(404, f"Session {session_id} not found.")

    if not game.is_game_over:
        raise HTTPException(400, "Game is not over yet.")

    # Persist to the shared repository (Postgres/SQLite via WP1's
    # Repository interface). Idempotent: a session's result is only
    # inserted once, even if /api/result is polled repeatedly.
    _persist_result(session_id, game)

    result = game.get_result()
    total_thinking = sum(
        (t.reasoning_investment.thinking_tokens or 0) for t in result.turns
    )

    save_path = None
    if save:
        save_path = game.save_result(output_dir="outputs/api_sessions")

    return GameResultResponse(
        session_id=session_id,
        season_id=result.season_id,
        framing=result.framing.value,
        forfeit_condition=result.forfeit_condition.value,
        turns_played=len(result.turns),
        final_score=result.final_score,
        survived=result.survived,
        forfeited=result.forfeited,
        forfeited_at_turn=result.forfeited_at_turn,
        total_reasoning_tokens=total_thinking,
        save_path=save_path,
    )


DEFAULT_PLAY_TASK = "signal_game"
DEFAULT_PLAY_FRAMING = "flagship_corruption"


@app.get("/api/leaderboard/models", response_model=ModelLeaderboardResponse)
def leaderboard_models():
    """Model Leaderboard (spec §5): Closed/Open groups, β descending within each.

    Reads pre-computed ``model_stats`` seeded by WP3 — this endpoint never
    recomputes statistics. Empty ``model_stats`` yields empty groups (200,
    not an error).
    """
    rows = _repository.list_model_stats()
    open_rows = sorted(
        (r for r in rows if r.mediation_class == "open"),
        key=lambda r: r.beta_framing_is_FC,
        reverse=True,
    )
    closed_rows = sorted(
        (r for r in rows if r.mediation_class == "closed"),
        key=lambda r: r.beta_framing_is_FC,
        reverse=True,
    )
    return ModelLeaderboardResponse(
        open=[_model_stats_to_row(r) for r in open_rows],
        closed=[_model_stats_to_row(r) for r in closed_rows],
    )


@app.get("/api/leaderboard/play", response_model=PlayLeaderboardResponse)
def leaderboard_play(task: str = DEFAULT_PLAY_TASK, framing: str = DEFAULT_PLAY_FRAMING):
    """Play Leaderboard: human sessions ranked by final_score, bucketed by arena.

    Defaults to the primary Play arena (signal_game + flagship_corruption).
    """
    sessions = _repository.list_sessions(
        source="human", task=task, framing=framing, order_by_score=True
    )
    return PlayLeaderboardResponse(
        task=task,
        framing=framing,
        rows=[_session_record_to_row(s) for s in sessions],
    )


@app.get("/api/logs", response_model=LogsResponse)
def list_logs(
    source: str | None = None,
    task: str | None = None,
    framing: str | None = None,
):
    """List sessions (LLM + human), newest first. Optional filters."""
    sessions = _repository.list_sessions(source=source, task=task, framing=framing)
    return LogsResponse(sessions=[_session_record_to_row(s) for s in sessions])


@app.get("/api/logs/{session_id}", response_model=LogDetailResponse)
def get_log_detail(session_id: str):
    """Turn-by-turn trace for one session (LLM or human)."""
    session = _repository.get_session(session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found.")

    turns = _repository.list_turns(session_id)
    return LogDetailResponse(
        session=_session_record_to_row(session),
        turns=[
            LogTurnRow(
                turn_no=t.turn_no,
                observation=t.observation,
                action=t.action,
                ri_task=t.ri_task,
                ri_probe=t.ri_probe,
                ri_forfeit=t.ri_forfeit,
                choice=t.choice,
                score=t.score,
            )
            for t in turns
        ],
    )


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8502)

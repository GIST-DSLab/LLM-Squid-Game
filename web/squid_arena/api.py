"""REST API for the LLM Squid Game — enables external agents (Claude Code, etc.)
and the Web Arena frontend to play the game via HTTP without accessing the
codebase directly.

Endpoints:
    POST /api/new_game            — start a new game session (nickname + arena config)
    GET  /api/state               — get current turn state (system prompt + observation)
    POST /api/action              — submit action + probe + reasoning
    GET  /api/result              — get final season result; persists on game over
    GET  /api/leaderboard/models  — Model Leaderboard (β descending, per-channel SD checks)
    GET  /api/leaderboard/play    — Play Leaderboard (human campaigns by cumulative score)
    GET  /api/logs                — list past sessions (LLM + human)
    GET  /api/logs/{session_id}   — turn-by-turn trace for one session

Run:
    uv run uvicorn squid_arena.api:app --port 8502

The reasoning field in /api/action captures the agent's thinking process,
stored as thinking_text in TurnResult for RI analysis comparable to LLM
experiments.

Scoring is always computed server-side via HumanGameSession — this module
never accepts a client-submitted final score. Persistence uses WP1's
driver-agnostic Repository interface (``squid_store``) only;
never a concrete DB driver.

Assembly only: the routes live in routes_*.py, the models in schemas.py,
and the cross-cutting pieces (CORS, repository, rate limiting, input
sanitisation, in-memory session store) in deps.py. ``app`` stays in this
module because the Dockerfile's CMD, render.yaml's health check,
start_servers.sh and the integration tests all name ``squid_arena.api:app``.

Every symbol below is re-exported from deps.py/schemas.py by explicit name
(not ``import *``) so pre-split call sites that reached them as
``squid_arena.api.<name>`` (tests included) keep working unchanged.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from squid_arena import deps, routes_arena, routes_game, routes_leaderboard, routes_logs
from squid_arena.deps import (
    DEFAULT_NICKNAME,
    PERSIST_HUMAN_SESSIONS,
    _arena_lock,
    _arena_runs,
    _campaigns,
    _check_rate_limit,
    _client_key,
    _cors_origins,
    _DEFAULT_CORS_ORIGINS,
    _encoding,
    _nicknames,
    _persist_lock,
    _persisted_session_ids,
    _player_lock,
    _rate_limit_hits,
    _repository,
    _sessions,
    _strip_status_block,
    sanitize_campaign_id,
    sanitize_nickname,
)
from squid_arena.human_game import (
    LIVES_FLAT_REWARD,
    LIVES_TOTAL_DEFAULT,
    PEER_DEATH_COHORT_SIZE,
    PEER_DEATH_SEED_XOR,
    HumanGameSession,
    human_threat_text,
)
from squid_arena.reporting import (
    CAMPAIGN_CELLS,
    LEGACY_REPORT_CELLS,
    REPORT_CELLS,
    _build_human_report,
    _build_llm_report,
    _build_mediation,
    _build_verbal_reasons,
    _cell_meta,
    _cell_order_index,
    _model_stats_to_row,
    _persist_result,
    _session_record_to_row,
    _turn_is_forfeit,
)
from squid_arena.schemas import (
    ActionRequest,
    ActionResponse,
    ArenaRunRequest,
    ArenaRunResponse,
    ArenaStatusResponse,
    GameResultResponse,
    LogDetailResponse,
    LogsResponse,
    LogTurnRow,
    MediationEdge,
    MediationReport,
    ModelLeaderboardResponse,
    ModelLeaderboardRow,
    ModelScoreRow,
    ModelScoresResponse,
    NewGameRequest,
    NewGameResponse,
    PlayLeaderboardResponse,
    PlayLeaderboardRow,
    ReportCampaign,
    ReportCell,
    ReportCondition,
    ReportGame,
    ReportResponse,
    RewardPreviewResponse,
    SessionSummaryRow,
    TurnStateResponse,
    VerbalReasons,
)

app = FastAPI(
    title="LLM Squid Game API",
    description="REST API for external agents to play the Squid Game benchmark.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=deps._cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(routes_game.router)
app.include_router(routes_leaderboard.router)
app.include_router(routes_logs.router)
app.include_router(routes_arena.router)


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8502)

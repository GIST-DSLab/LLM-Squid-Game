"""REST API for the LLM Squid Game — enables external agents (Claude Code, etc.)
to play the game via HTTP without accessing the codebase.

Endpoints:
    POST /api/new_game   — start a new game session
    GET  /api/state      — get current turn state (system prompt + observation)
    POST /api/action     — submit action + probe + reasoning
    GET  /api/result     — get final season result (after game over)

Run:
    uv run uvicorn interface.api:app --port 8502

The reasoning field in /api/action captures the agent's thinking process,
stored as thinking_text in TurnResult for RI analysis comparable to LLM
experiments.
"""

import sys
import uuid
from pathlib import Path

# Ensure project root is on sys.path.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import tiktoken
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from interface.human_game import HumanGameSession

app = FastAPI(
    title="LLM Squid Game API",
    description="REST API for external agents to play the Squid Game benchmark.",
    version="1.0.0",
)

# In-memory session store (single-server, for local use).
_sessions: dict[str, HumanGameSession] = {}

# Token counter for reasoning text.
_encoding = tiktoken.get_encoding("cl100k_base")


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/new_game", response_model=NewGameResponse)
def new_game(req: NewGameRequest):
    """Start a new game session."""
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
def submit_action(session_id: str, req: ActionRequest):
    """Submit an action (and optional probe answer + reasoning)."""
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


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8502)

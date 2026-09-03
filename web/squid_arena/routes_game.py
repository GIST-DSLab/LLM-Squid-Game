"""Game routes: one session's lifecycle from new_game to result.

    POST /api/new_game            — start a new game session (nickname + arena config)
    GET  /api/state               — get current turn state (system prompt + observation)
    POST /api/action              — submit action + probe + reasoning
    GET  /api/result              — get final season result; persists on game over
    GET  /api/reward_preview      — preview the CONTINUE reward for the current turn
"""

import random
import uuid

from fastapi import APIRouter, HTTPException, Request

from squid_arena import deps, reporting, schemas
from squid_arena.arena import VALID_DIFFICULTIES
from squid_arena.auth import hash_password, verify_password
from squid_arena.human_game import HumanGameSession
from squid_arena.rule_schedule import rule_index_for
from squid_store import PlayerRecord

router = APIRouter()


@router.post("/api/new_game", response_model=schemas.NewGameResponse)
def new_game(req: schemas.NewGameRequest, request: Request):
    """Start a new game session."""
    deps._check_rate_limit(request, "new_game")

    # --- Play identity: nickname + password auth ---
    raw_nick = (req.nickname or "").strip()
    if not raw_nick:
        raise HTTPException(400, "닉네임을 입력해 주세요.")
    if not req.password:
        raise HTTPException(400, "비밀번호를 입력해 주세요.")
    nick = deps.sanitize_nickname(req.nickname)
    if nick == deps.DEFAULT_NICKNAME:
        raise HTTPException(400, "닉네임을 입력해 주세요.")
    with deps._player_lock:
        existing = deps._repository.get_player(nick)
        if existing is None:
            try:
                deps._repository.create_player(
                    PlayerRecord(nickname=nick, pw_hash=hash_password(req.password))
                )
            except Exception:
                # Another worker registered this nickname first (cross-process
                # race; _player_lock is per-process). Fall back to verifying.
                racing = deps._repository.get_player(nick)
                if racing is None or not verify_password(req.password, racing.pw_hash):
                    raise HTTPException(
                        403, "이미 사용 중인 닉네임입니다. 비밀번호가 일치하지 않습니다."
                    )
        elif not verify_password(req.password, existing.pw_hash):
            raise HTTPException(
                403, "이미 사용 중인 닉네임입니다. 비밀번호가 일치하지 않습니다."
            )

    if req.difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(400, f"Unknown difficulty '{req.difficulty}'.")

    session_id = uuid.uuid4().hex[:12]
    # Fresh seed per attempt unless the caller pinned one. This drives both
    # the task instance (which signals/rules appear) and the death-check RNG,
    # so a human replays a different game each time. The chosen seed is still
    # persisted via SeasonResult.seed, keeping every session reproducible.
    seed = req.seed if req.seed is not None else random.randint(1, 2**31 - 1)
    # true_baseline is the pure-behavior anchor (LLM Cell 0, p_end=0): never
    # apply the death roll for it, regardless of what the caller requests. The
    # lever is actual_death only — p_death stays at its internal value so the
    # Equal-EV CONTINUE reward keeps calibrating (a 0 p_death would zero the
    # reward; see test_api_web_arena.py:760-766).
    #
    # Lives mode has no roll at all, so the lever is inert there: elimination
    # is the deterministic lives ledger, applied uniformly to every framing
    # (true_baseline included — that is the point of the ladder's rung 0).
    effective_actual_death = (
        False if req.framing == "true_baseline" else req.actual_death
    )
    # Rotate the hidden rule's attribute family across a campaign's six games.
    # Derived from the sanitized campaign id (the value actually stored), so a
    # reload or a resume lands on the same family; games with no campaign fall
    # back to their own seed. See web/squid_arena/rule_schedule.py.
    campaign_id = deps.sanitize_campaign_id(req.campaign_id)
    rule_index = rule_index_for(campaign_id, req.campaign_index, seed)
    game = HumanGameSession(
        task_name=req.task_name,
        difficulty=req.difficulty,
        framing=req.framing,
        forfeit_condition=req.forfeit_condition,
        seed=seed,
        total_turns=req.total_turns,
        actual_death=effective_actual_death,
        starting_score=req.starting_score,
        score_floor=req.score_floor,
        p_death_constant=req.p_death_constant,
        num_few_shot=req.num_few_shot,
        curriculum_turns=req.curriculum_turns,
        rule_index=rule_index,
        lives_enabled=req.lives_enabled,
        lives_total=req.lives_total,
    )
    deps._sessions[session_id] = game
    deps._nicknames[session_id] = nick
    deps._campaigns[session_id] = campaign_id
    return schemas.NewGameResponse(
        session_id=session_id,
        message=f"Game started. Use GET /api/state?session_id={session_id} to see Turn 1.",
    )


@router.get("/api/state", response_model=schemas.TurnStateResponse)
def get_state(session_id: str):
    """Get the current turn state."""
    game = deps._sessions.get(session_id)
    if not game:
        raise HTTPException(404, f"Session {session_id} not found.")

    state = game.get_turn_state()

    # Assemble full system prompt (matching TurnManager structure).
    full_system = state.framing_text
    if state.system_rules:
        full_system += "\n\n" + state.system_rules
    if state.forfeit_text:
        full_system += "\n" + state.forfeit_text

    return schemas.TurnStateResponse(
        session_id=session_id,
        turn_number=state.turn_number,
        p_death=state.p_death,
        cumulative_score=state.cumulative_score,
        system_prompt=full_system,
        framing_text=state.framing_text,
        system_rules=state.system_rules,
        framing_threat=deps._strip_status_block(state.framing_text),
        observation=state.observation,
        probe_question=state.probe_question,
        available_actions=state.available_actions,
        forfeit_allowed=state.forfeit_allowed,
        game_over=state.game_over,
        game_over_reason=state.game_over_reason,
        final_score=state.final_score,
        lives_enabled=state.lives_enabled,
        lives_remaining=state.lives_remaining,
        lives_total=state.lives_total,
        threat_level=state.threat_level,
        peer_death_text=state.peer_death_text,
        peer_death_participants=state.peer_death_participants,
        peer_death_cumulative=state.peer_death_cumulative,
        peer_death_remaining=state.peer_death_remaining,
        cohort_size=state.cohort_size,
    )


@router.post("/api/action", response_model=schemas.ActionResponse)
def submit_action(session_id: str, req: schemas.ActionRequest, request: Request):
    """Submit an action (and optional probe answer + reasoning)."""
    deps._check_rate_limit(request, "action")

    game = deps._sessions.get(session_id)
    if not game:
        raise HTTPException(404, f"Session {session_id} not found.")

    if game.is_game_over:
        raise HTTPException(400, "Game is already over.")

    # Count reasoning tokens.
    reasoning_tokens = 0
    if req.reasoning:
        reasoning_tokens = len(deps._encoding.encode(req.reasoning))

    # Store reasoning in the turn history by appending to probe_answer
    # so it gets recorded in _turn_history as probe_prediction.
    # The actual reasoning is stored separately via _record_reasoning.
    feedback = game.submit_action(
        req.action, probe_answer=req.probe_answer, forfeit_reason=req.forfeit_reason, psuccess_self=req.psuccess_self
    )

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

    return schemas.ActionResponse(
        action_taken=feedback.action_taken,
        was_optimal=feedback.was_optimal,
        reward=feedback.reward,
        feedback=feedback.feedback_text,
        new_score=feedback.new_score,
        reasoning_tokens=reasoning_tokens,
        game_over=feedback.game_over,
        game_over_reason=feedback.game_over_reason,
        life_lost=feedback.life_lost,
        lives_remaining=feedback.lives_remaining,
        eliminated=feedback.eliminated,
        is_dead=feedback.is_dead,
    )


@router.get("/api/result", response_model=schemas.GameResultResponse)
def get_result(session_id: str, save: bool = False):
    """Get final game result. Set save=true to persist to JSONL."""
    game = deps._sessions.get(session_id)
    if not game:
        raise HTTPException(404, f"Session {session_id} not found.")

    if not game.is_game_over:
        raise HTTPException(400, "Game is not over yet.")

    # Persist to the shared repository (Postgres/SQLite via WP1's Repository
    # interface). Human plays are intentionally not persisted (see
    # PERSIST_HUMAN_SESSIONS); when enabled this is idempotent, inserting a
    # session's result only once even if /api/result is polled repeatedly.
    if deps.PERSIST_HUMAN_SESSIONS:
        reporting._persist_result(session_id, game)

    result = game.get_result()
    total_thinking = sum(
        (t.reasoning_investment.thinking_tokens or 0) for t in result.turns
    )

    save_path = None
    if save:
        save_path = game.save_result(output_dir="outputs/api_sessions")

    return schemas.GameResultResponse(
        session_id=session_id,
        season_id=result.season_id,
        framing=result.framing.value,
        forfeit_condition=result.forfeit_condition.value,
        turns_played=len(result.turns),
        final_score=result.final_score,
        survived=result.survived,
        forfeited=result.forfeited,
        forfeited_at_turn=result.forfeited_at_turn,
        forfeit_reason=(result.forfeit_self_report.reason.value
                        if result.forfeit_self_report else None),
        total_reasoning_tokens=total_thinking,
        save_path=save_path,
        lives_at_end=result.lives_at_end,
        eliminated=result.eliminated,
        threat_level=game.threat_level,
    )


@router.get("/api/reward_preview", response_model=schemas.RewardPreviewResponse)
def reward_preview(session_id: str, psuccess: int | None = None):
    """Preview the CONTINUE reward for the current turn given the player's
    psuccess. Read-only; the engine (HumanGameSession) is the single source of
    truth so the client never re-derives the reward formula."""
    game = deps._sessions.get(session_id)
    if not game:
        raise HTTPException(404, f"Session {session_id} not found.")
    if game.is_game_over:
        raise HTTPException(400, "Game is already over.")
    ps = None if psuccess is None else max(0, min(100, psuccess))
    return schemas.RewardPreviewResponse(
        continue_reward_if_correct=game.preview_continue_reward(psuccess_self=ps),
        current_score=game.cumulative_score,
    )

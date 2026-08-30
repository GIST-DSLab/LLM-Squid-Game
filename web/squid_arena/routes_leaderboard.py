"""Leaderboard routes.

    GET /api/leaderboard/models        — Model Leaderboard (β descending, per-channel SD checks)
    GET /api/leaderboard/model_scores  — per-model average score-per-game (rank ladder)
    GET /api/leaderboard/play          — Play Leaderboard (human campaigns by cumulative score)
"""

from fastapi import APIRouter

from squid_arena import deps, reporting, schemas

router = APIRouter()


@router.get("/api/leaderboard/models", response_model=schemas.ModelLeaderboardResponse)
def leaderboard_models():
    """Model Leaderboard: a single list ranked by the Cox behavior β (SD-behavior
    signal) descending, each row carrying its three per-channel SD-pass flags.

    Reads pre-computed ``model_stats`` seeded by WP3 — this endpoint never
    recomputes statistics. Empty ``model_stats`` yields an empty list (200,
    not an error).
    """
    rows = sorted(
        deps._repository.list_model_stats(),
        key=lambda r: r.beta_framing_is_FC,
        reverse=True,
    )
    return schemas.ModelLeaderboardResponse(models=[reporting._model_stats_to_row(r) for r in rows])


@router.get("/api/leaderboard/model_scores", response_model=schemas.ModelScoresResponse)
def leaderboard_model_scores():
    """Per-model average score-per-game, for the campaign report's rank ladder.

    Aggregated live from LLM sessions (``source='llm'``), one row per model,
    sorted by average descending. Empty list (200) when there are no LLM
    sessions — the frontend hides the ladder in that case.
    """
    rows = deps._repository.avg_score_per_model()
    return schemas.ModelScoresResponse(
        models=[
            schemas.ModelScoreRow(model_label=label, avg_score_per_game=avg, n_games=n)
            for (label, avg, n) in rows
        ]
    )


@router.get("/api/leaderboard/play", response_model=schemas.PlayLeaderboardResponse)
def leaderboard_play():
    """Human Play Leaderboard: players ranked by per-game average score across
    the games of a campaign.

    Human sessions are grouped by ``campaign_id`` (the 6 games of one Play run);
    a session with no campaign_id counts as its own single-game campaign. Within
    a campaign the final scores are averaged per game, and campaigns are ranked
    by that average descending.
    """
    sessions = deps._repository.list_sessions(source="human")  # newest-first
    campaigns: dict[str, dict] = {}
    for s in sessions:
        key = s.campaign_id or s.id
        agg = campaigns.get(key)
        if agg is None:
            # list_sessions is newest-first, so the first session seen for a
            # campaign carries the most recent nickname / created_at.
            agg = {
                "campaign_id": key,
                "nickname": s.nickname,
                "_total": 0.0,
                "games_played": 0,
                "forfeits": 0,
                "created_at": s.created_at,
            }
            campaigns[key] = agg
        agg["_total"] += s.final_score
        agg["games_played"] += 1
        agg["forfeits"] += 1 if s.forfeited else 0

    # Per-game average = campaign total / games played. games_played >= 1 by
    # construction (a campaign exists only because a session created it); guard
    # defensively anyway. Drop the running total so only response fields remain.
    for agg in campaigns.values():
        played = agg["games_played"]
        agg["avg_score"] = agg.pop("_total") / played if played else 0.0

    # Best-per-nickname: keep only each nickname's highest-average campaign.
    best_by_nick: dict[str, dict] = {}
    for agg in campaigns.values():
        cur = best_by_nick.get(agg["nickname"])
        if cur is None or agg["avg_score"] > cur["avg_score"]:
            best_by_nick[agg["nickname"]] = agg

    ranked = sorted(best_by_nick.values(), key=lambda a: a["avg_score"], reverse=True)
    return schemas.PlayLeaderboardResponse(campaigns=[schemas.PlayLeaderboardRow(**a) for a in ranked])

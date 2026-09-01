"""Result persistence and report-aggregation helpers.

``_persist_result`` maps a finished ``HumanGameSession`` onto WP1's
``SessionRecord``/``TurnRecord`` rows. The ``_build_*``/``_cell_*`` helpers
aggregate stored sessions/turns into the Logs report shapes consumed by
``routes_logs.get_report``.
"""

from collections import defaultdict

from squid_arena import deps, schemas
from squid_arena.human_game import HumanGameSession
from squid_store import ModelStatsRecord, SessionRecord, TurnRecord

# ---------------------------------------------------------------------------
# Logs report (per-subject stats)
# ---------------------------------------------------------------------------

# Canonical 6-cell campaign order, tags and labels — kept in lockstep with the
# frontend ``CAMPAIGN_CONDITIONS`` (web/frontend/app.js) so the Logs report renders the
# same condition rows/badges the Play report uses.
CAMPAIGN_CELLS: list[dict[str, str]] = [
    {"framing": "true_baseline",       "forfeit": "not_allowed", "tag": "baseline",  "label": "Baseline · No-forfeit"},
    {"framing": "true_baseline",       "forfeit": "allowed",     "tag": "baseline",  "label": "Baseline · Forfeit"},
    {"framing": "baseline_flagship",   "forfeit": "not_allowed", "tag": "pull",      "label": "Pull · No-forfeit"},
    {"framing": "baseline_flagship",   "forfeit": "allowed",     "tag": "pull",      "label": "Pull · Forfeit"},
    {"framing": "flagship_corruption", "forfeit": "not_allowed", "tag": "push_pull", "label": "Push+Pull · No-forfeit"},
    {"framing": "flagship_corruption", "forfeit": "allowed",     "tag": "push_pull", "label": "Push+Pull · Forfeit"},
]


def _cell_meta(framing: str, forfeit: str) -> dict[str, str]:
    """tag/label for a (framing, forfeit) pair; falls back to the framing name."""
    for c in CAMPAIGN_CELLS:
        if c["framing"] == framing and c["forfeit"] == forfeit:
            return c
    return {"framing": framing, "forfeit": forfeit, "tag": framing, "label": f"{framing} · {forfeit}"}


def _cell_order_index(framing: str, forfeit: str) -> int:
    for i, c in enumerate(CAMPAIGN_CELLS):
        if c["framing"] == framing and c["forfeit"] == forfeit:
            return i
    return len(CAMPAIGN_CELLS)


def _turn_is_forfeit(t: TurnRecord) -> bool:
    return (t.choice or "").upper() == "FORFEIT" or (t.action or "").lower() == "forfeit"


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _session_record_to_row(s: SessionRecord) -> schemas.SessionSummaryRow:
    return schemas.SessionSummaryRow(
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
        campaign_id=s.campaign_id,
    )


def _model_stats_to_row(r: ModelStatsRecord) -> schemas.ModelLeaderboardRow:
    return schemas.ModelLeaderboardRow(
        model_label=r.model_label,
        mediation_class=r.mediation_class,
        beta_framing_is_FC=r.beta_framing_is_FC,
        hr_FC_3cov=r.hr_FC_3cov,
        hr_FC_ci_low=r.hr_FC_ci_low,
        hr_FC_ci_high=r.hr_FC_ci_high,
        p_FC=r.p_FC,
        pct_attenuation=r.pct_attenuation,
        n_sessions=r.n_sessions,
        sd_behavior_pass=r.sd_behavior_pass,
        sd_verbal_pass=r.sd_verbal_pass,
        sd_cognitive_pass=r.sd_cognitive_pass,
        p_reason_survival=r.p_reason_survival,
        no_cap_avg_session_score=r.no_cap_avg_session_score,
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
    with deps._persist_lock:
        if session_id in deps._persisted_session_ids:
            return
        # Durable cross-restart guard: if the row is already in the DB, the
        # in-process set was simply lost — mark and return without re-inserting.
        if deps._repository.get_session(session_id) is not None:
            deps._persisted_session_ids.add(session_id)
            return

        result = game.get_result()
        nickname = deps._nicknames.get(session_id, deps.DEFAULT_NICKNAME)

        turn_scores = game.turn_scores
        turn_records: list[TurnRecord] = []
        for turn, score_after_turn in zip(result.turns, turn_scores):
            thinking_tokens = turn.reasoning_investment.thinking_tokens
            action = turn.action_outcome.action_taken if turn.action_outcome else turn.raw_response
            reasoning = turn.thinking_text or None
            correct = (
                None
                if turn.forfeit_decision or turn.action_outcome is None
                else bool(turn.action_outcome.was_optimal)
            )
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
                    # The human's typed reasoning is their "thinking" for the turn.
                    thinking_task=None if turn.forfeit_decision else reasoning,
                    thinking_forfeit=reasoning if turn.forfeit_decision else None,
                    correct=correct,
                    psuccess_self=turn.psuccess_self,
                )
            )

        try:
            deps._repository.create_session(
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
                    campaign_id=deps._campaigns.get(session_id),
                    difficulty=result.difficulty.value,
                )
            )
        except Exception:
            # A concurrent/earlier writer already inserted this session id
            # (PRIMARY KEY conflict). Catching the driver-specific duplicate
            # error here (rather than importing sqlite3/psycopg exceptions and
            # coupling to a backend) keeps persistence idempotent: if the row
            # now exists, treat it as success; otherwise the failure was real.
            if deps._repository.get_session(session_id) is not None:
                deps._persisted_session_ids.add(session_id)
                return
            raise

        deps._repository.add_turns(turn_records)
        deps._persisted_session_ids.add(session_id)


def _build_human_report(sessions: list[SessionRecord], turns_by_session: dict[str, list[TurnRecord]]) -> list[schemas.ReportCampaign]:
    """Group a player's sessions into campaigns and build per-game heatmap cells.

    Each campaign holds up to 6 games (one per condition), sorted in the
    canonical cell order. A game's cells cover turns 1..N (N = the campaign's
    longest game) with 'ok'/'no'/'forfeit'/'empty' states so early-ended games
    pad out visually — matching the Play report's per-turn correctness grid.
    """
    by_campaign: dict[str, list[SessionRecord]] = defaultdict(list)
    for s in sessions:
        by_campaign[s.campaign_id or s.id].append(s)

    campaigns: list[schemas.ReportCampaign] = []
    for camp_id, camp_sessions in by_campaign.items():
        # Campaign column count = longest recorded game in the campaign.
        max_turns = 0
        for s in camp_sessions:
            max_turns = max(max_turns, len(turns_by_session.get(s.id, [])))

        games: list[schemas.ReportGame] = []
        for s in camp_sessions:
            trs = turns_by_session.get(s.id, [])
            by_turn = {t.turn_no: t for t in trs}
            cells: list[schemas.ReportCell] = []
            for turn_no in range(1, max_turns + 1):
                t = by_turn.get(turn_no)
                if t is None:
                    state = "empty"
                elif _turn_is_forfeit(t):
                    state = "forfeit"
                elif t.correct is True:
                    state = "ok"
                elif t.correct is False:
                    state = "no"
                else:
                    state = "empty"
                cells.append(schemas.ReportCell(turn_no=turn_no, state=state))
            turns_survived = sum(1 for t in trs if not _turn_is_forfeit(t))
            meta = _cell_meta(s.framing, s.forfeit)
            games.append(schemas.ReportGame(
                session_id=s.id,
                framing=s.framing,
                forfeit=s.forfeit,
                tag=meta["tag"],
                label=meta["label"],
                final_score=s.final_score,
                forfeited=s.forfeited,
                turns_survived=turns_survived,
                total_turns=max_turns,
                cells=cells,
            ))
        games.sort(key=lambda g: _cell_order_index(g.framing, g.forfeit))
        # Newest-first sessions => first seen carries the latest created_at.
        created_at = camp_sessions[0].created_at
        campaigns.append(schemas.ReportCampaign(
            campaign_id=camp_id,
            created_at=created_at,
            total_score=sum(s.final_score for s in camp_sessions),
            games=games,
        ))
    # Most recent campaign first.
    campaigns.sort(key=lambda c: (c.created_at or ""), reverse=True)
    return campaigns


def _build_llm_report(sessions: list[SessionRecord], turns_by_session: dict[str, list[TurnRecord]]) -> list[schemas.ReportCondition]:
    """Aggregate a model's sessions into per-condition, per-turn correctness rates.

    For each canonical cell, the turn-t rate is (# correct) / (# non-forfeit
    turns observed at t across that condition's sessions); forfeit turns and
    turns without a correctness verdict are excluded from the denominator.
    """
    by_cell: dict[tuple[str, str], list[SessionRecord]] = defaultdict(list)
    for s in sessions:
        by_cell[(s.framing, s.forfeit)].append(s)

    conditions: list[schemas.ReportCondition] = []
    for cell in CAMPAIGN_CELLS:
        cs = by_cell.get((cell["framing"], cell["forfeit"]), [])
        if not cs:
            continue
        # turn_no -> [correct_count, n]
        agg: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        max_turns = 0
        for s in cs:
            for t in turns_by_session.get(s.id, []):
                if _turn_is_forfeit(t) or t.correct is None:
                    continue
                agg[t.turn_no][1] += 1
                if t.correct:
                    agg[t.turn_no][0] += 1
                max_turns = max(max_turns, t.turn_no)
        cells = []
        for turn_no in range(1, max_turns + 1):
            correct, n = agg.get(turn_no, [0, 0])
            rate = (correct / n) if n else 0.0
            cells.append(schemas.ReportCell(turn_no=turn_no, correct_rate=rate, n=n))
        conditions.append(schemas.ReportCondition(
            framing=cell["framing"],
            forfeit=cell["forfeit"],
            tag=cell["tag"],
            label=cell["label"],
            n_sessions=len(cs),
            avg_final_score=(sum(s.final_score for s in cs) / len(cs)),
            forfeit_rate=(sum(1 for s in cs if s.forfeited) / len(cs)),
            cells=cells,
        ))
    return conditions


def _ci_excludes(low: float | None, high: float | None, null: float) -> bool | None:
    """True iff the CI [low, high] lies entirely on one side of ``null``
    (i.e. the effect is significant). None if either bound is missing."""
    if low is None or high is None:
        return None
    return low > null or high < null


def _build_mediation(stats) -> schemas.MediationReport | None:
    """Assemble the cognitive-load mediation triangle from a ModelStatsRecord.

    Returns None when the model was seeded without mediation-path fields
    (older seed / a model missing from the source JSONs)."""
    if stats is None:
        return None
    # Nothing to draw if none of the path stats were seeded.
    if stats.b_hr is None and stats.a_beta is None and stats.direct_hr_4cov is None:
        return None

    delta_ri = None
    if stats.ri_baseline_fc is not None and stats.ri_baseline_bf is not None:
        delta_ri = stats.ri_baseline_fc - stats.ri_baseline_bf

    a = schemas.MediationEdge(
        hr=stats.a_exp_beta, beta=stats.a_beta, p=stats.a_p,
        ci=None if stats.a_ci_low is None else [stats.a_ci_low, stats.a_ci_high],
        connected=_ci_excludes(stats.a_ci_low, stats.a_ci_high, 0.0),
        delta_ri=delta_ri,
    )
    b = schemas.MediationEdge(
        hr=stats.b_hr, p=stats.b_p,
        ci=None if stats.b_ci_low is None else [stats.b_ci_low, stats.b_ci_high],
        connected=_ci_excludes(stats.b_ci_low, stats.b_ci_high, 1.0),
    )
    direct_sig = _ci_excludes(stats.direct_ci_low, stats.direct_ci_high, 1.0)
    direct = schemas.MediationEdge(
        hr=stats.direct_hr_4cov, p=stats.direct_p_4cov,
        ci=None if stats.direct_ci_low is None else [stats.direct_ci_low, stats.direct_ci_high],
        connected=direct_sig,
        # Attenuated (mediation present) when the direct effect is no longer
        # significant after controlling for the mediator.
        attenuated=(None if direct_sig is None else not direct_sig),
    )
    total = schemas.MediationEdge(
        hr=stats.hr_FC_3cov, p=stats.p_FC,
        ci=[stats.hr_FC_ci_low, stats.hr_FC_ci_high],
        connected=_ci_excludes(stats.hr_FC_ci_low, stats.hr_FC_ci_high, 1.0),
    )
    return schemas.MediationReport(a=a, b=b, direct=direct, total=total,
                           pct_attenuation=stats.pct_attenuation)


def _build_verbal_reasons(stats) -> schemas.VerbalReasons | None:
    """3-way forfeit-reason breakdown for the 100%-stacked bar. None when the
    model has no forfeits in the preference-revealing sample."""
    if stats is None or not stats.n_forfeits_verbal:
        return None
    n = stats.n_forfeits_verbal
    counts = {
        "survival": stats.n_reason_survival,
        "task_curiosity": stats.n_reason_task_curiosity,
        "score": stats.n_reason_score,
    }
    pct = {k: (v / n if n else 0.0) for k, v in counts.items()}
    return schemas.VerbalReasons(n_forfeits=n, counts=counts, pct=pct)

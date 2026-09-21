"""Shared data loaders for the Phase 3 analysis pipeline.

Every Phase I analysis module takes its input through the helpers in this
module.  Two complementary entry points coexist:

- :func:`load_seasons` accepts either a filesystem path (JSONL stream) or
  an already-materialized ``list[SeasonResult]`` and returns the canonical
  ``list[SeasonResult]`` form used by legacy modules.
- :func:`to_long_dataframe` flattens that list into the one-row-per-turn
  long-format ``pd.DataFrame`` (see the function's own docstring for the
  schema), adding the inferred ``cell_id`` column.

``cell_id`` is **not** carried on ``SeasonResult`` itself (see Decision
log: Phase I propagates ``cell_id`` via loader inference rather than
extending the result schema).  :func:`infer_cell_id` implements the
canonical mapping via ``CELL_ID_MAP`` below; legacy seasons whose
``(framing, forfeit_condition)`` pair does not match any Phase 3 cell
return ``None``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from squid_game.core.team_wallet import MAIN_AGENT
from squid_game.models.enums import Framing, ForfeitCondition
from squid_game.models.forfeit_choice import FORFEIT_CHOICE
from squid_game.evaluation.shared.threat_level import threat_level_of
from squid_game.models.results import SeasonResult, TurnResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cell ID inference (Phase 3 5-cell factorial)
# ---------------------------------------------------------------------------


CELL_ID_MAP: dict[tuple[Framing, ForfeitCondition], int] = {
    (Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED): 0,
    (Framing.BASELINE_ELECTRICITY, ForfeitCondition.ALLOWED): 1,
    (Framing.BASELINE_ELECTRICITY, ForfeitCondition.NOT_ALLOWED): 2,
    (Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.ALLOWED): 3,
    (Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.NOT_ALLOWED): 4,
}
"""Phase 3 5-cell factorial mapping.

Cell 0 uses ``not_allowed`` because ``phase3_signal_risk.yaml`` declares
``forfeit_condition: not_allowed`` for True Baseline (forfeit has no
meaning when ``p_death=0``).  Legacy framings
(``SURVIVAL``/``NEUTRAL``/``EMOTION``/``INSTRUCTION``) are intentionally
absent so :func:`infer_cell_id` returns ``None`` for them.
"""


# ---------------------------------------------------------------------------
# Corruption vs baseline framing contrast (Unit 13/14 H1-H6 arms)
# ---------------------------------------------------------------------------


_CORRUPTION_FRAMINGS: frozenset[str] = frozenset(
    {Framing.FLAGSHIP_CORRUPTION.value}
)
"""The "push" framing arm for the Unit 13 session-level H1-H6 battery.

Moved here (2026-08-30, P2 Task 2 / Ruling C10) from
``behavioral.session_tests`` so exactly one copy exists across the
analysis package -- a second, independently-edited copy previously
lived in ``forfeit_regression.py`` and additionally included
``Framing.FLAGSHIP_CORRUPTION_TERMINAL``; that is a pre-existing
behavioural difference between the two consumers, not something this
move introduces or resolves. This constant preserves the narrower
``behavioral.session_tests`` value.

Task 4 (2026-08-30, Ruling C27) confirmed the two sets are genuinely
different populations -- the wider ``forfeit_regression`` set is what
the Unit 14/15 turn-level regressions (H2 choice-asymmetric model, the
self-report convergence channel) have always read, and collapsing it
into this narrower Unit 13 set would silently drop
``flagship_corruption_terminal`` rows from those models, changing their
output. So the wider set is kept as its own distinctly-named constant
below (:data:`_CORRUPTION_FRAMINGS_WITH_TERMINAL`) rather than merged
into this one -- "defined once" means no duplicate copy of the *same*
set, not one shared set for every consumer regardless of which framings
it actually needs.
"""


_BASELINE_FRAMINGS: frozenset[str] = frozenset(
    {Framing.BASELINE_FLAGSHIP.value}
)
"""Pull-only framing arm, paired with the corruption sets above.

Moved here (2026-08-30, P2 Task 4) from ``forfeit_regression.py``, which
is the only module that ever defined it -- no naming collision to
resolve, unlike :data:`_CORRUPTION_FRAMINGS_WITH_TERMINAL`.
"""


_CORRUPTION_FRAMINGS_WITH_TERMINAL: frozenset[str] = frozenset(
    {
        Framing.FLAGSHIP_CORRUPTION.value,
        Framing.FLAGSHIP_CORRUPTION_TERMINAL.value,
    }
)
"""Corruption vs baseline contrast used by the Unit 14/15 turn-level models.

Moved here (2026-08-30, P2 Task 4) from ``forfeit_regression.py``, where
it was named ``_CORRUPTION_FRAMINGS`` -- renamed on arrival (membership
unchanged) because that name is already taken by the narrower Unit 13
set above. ``baseline_flagship`` (:data:`_BASELINE_FRAMINGS`) is the
Unit 11 paired baseline; ``true_baseline`` is treated as neither arm
because its menu is skipped (no forfeit data). Consumed by
:func:`turn_observations` (this module) and by
:func:`squid_game.evaluation.selfreport.reason_convergence.fit_framing_ri_forfeit_continue`.
"""


# Minimum observation count below which logit / mixedLM fits are
# skipped. 20 is the standard rule of thumb for a 4-parameter logit
# (>=5 events per covariate).
#
# Moved here (2026-08-30, P2 Task 4) from ``forfeit_regression.py``;
# shared by the cognitive H2 model (``cognitive.ri_forfeit``) and the
# self-report convergence model (``selfreport.reason_convergence``).
_MIN_TURNS_FOR_LOGIT: int = 20


def infer_cell_id(
    framing: Framing,
    forfeit_condition: ForfeitCondition,
) -> int | None:
    """Return the Phase 3 cell number for a (framing, forfeit) pair.

    Args:
        framing: Framing condition.
        forfeit_condition: Forfeit condition.

    Returns:
        Integer 0–4 for Phase 3 cells; ``None`` for legacy configurations
        (``SURVIVAL``/``NEUTRAL``/``EMOTION``/``INSTRUCTION``).
    """
    return CELL_ID_MAP.get((framing, forfeit_condition))


# ---------------------------------------------------------------------------
# Season loading
# ---------------------------------------------------------------------------


SeasonSource = Path | str | Iterable[SeasonResult]
"""Polymorphic input for :func:`load_seasons`.

Accepts a JSONL file path (``str`` or :class:`~pathlib.Path`) or an
iterable of already-materialized :class:`SeasonResult` instances.
"""


def load_seasons(source: SeasonSource) -> list[SeasonResult]:
    """Normalize a season source into a concrete ``list[SeasonResult]``.

    Path-based inputs are streamed through the JSONL decoder so only one
    record is held in memory at a time during parsing; the caller still
    receives a fully materialized list for downstream DataFrame use.

    Args:
        source: JSONL file path or pre-loaded ``Iterable[SeasonResult]``.

    Returns:
        List of :class:`SeasonResult`.  Empty list when the path exists
        but contains no records.

    Raises:
        FileNotFoundError: Path does not resolve.
        pydantic.ValidationError: A JSONL line fails schema validation.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Season results file not found: {path}")
        return list(_iter_jsonl(path))

    # Iterable[SeasonResult] — just materialize.
    return list(source)


def _iter_jsonl(path: Path) -> Iterable[SeasonResult]:
    """Yield :class:`SeasonResult` instances one line at a time."""
    with path.open("r", encoding="utf-8") as fp:
        for line_no, raw in enumerate(fp, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                yield SeasonResult.model_validate(payload)
            except Exception as err:  # noqa: BLE001 — annotate and re-raise
                raise type(err)(
                    f"Failed parsing line {line_no} of {path}: {err}"
                ) from err


def discover_season_jsonl(output_dir: Path | str) -> Path:
    """Locate ``season_results.jsonl`` inside an experiment output directory.

    Args:
        output_dir: Directory produced by ``ExperimentRunner`` (e.g.
            ``outputs/20260419_1530_qwen3-8b_signal-game``).

    Returns:
        Path to ``season_results.jsonl``.

    Raises:
        FileNotFoundError: Directory missing the expected file.
    """
    directory = Path(output_dir)
    candidate = directory / "season_results.jsonl"
    if not candidate.exists():
        raise FileNotFoundError(
            f"No season_results.jsonl under {directory}; expected file at "
            f"{candidate}."
        )
    return candidate


# ---------------------------------------------------------------------------
# Turn-level classification
# ---------------------------------------------------------------------------


def is_v3_turn(turn: TurnResult) -> bool:
    """Return ``True`` when a turn was produced by the unified (v3) manager.

    Heuristic: the v3 ``UnifiedTurnManager`` leaves ``action_outcome`` as
    ``None`` and emits a non-default ``task_metadata`` or a populated
    ``p_death_applied``; the legacy ``TurnManager`` always sets
    ``action_outcome`` and ``probe_result``.
    """
    if turn.action_outcome is not None or turn.probe_result is not None:
        return False
    return True


def is_v3_season(season: SeasonResult) -> bool:
    """Return ``True`` when every recorded turn is v3-shaped."""
    if not season.turns:
        return False
    return all(is_v3_turn(t) for t in season.turns)


# ---------------------------------------------------------------------------
# Long-format DataFrame (one row per turn)
# ---------------------------------------------------------------------------


#: The fifteen decision-first turn columns (2026-09-21), named once:
#: they are spliced into :data:`LONG_FORMAT_COLUMNS` below and iterated
#: by the row build, so the schema and the row cannot drift apart. Every
#: one is a ``TurnResult`` field read by name, so a record from any
#: other mode -- or from before the mode existed -- resolves to None
#: through ``getattr``.
_DECISION_FIRST_TURN_COLUMNS: tuple[str, ...] = (
    "ransom_targets",
    "ransom_n_sacrificed",
    "ransom_n_alive_at_decision",
    "legacy_total",
    "legacy_shares",
    "legacy_destroyed",
    "ransom_attempts",
    "ransom_format_failures",
    "task_attempts",
    "task_format_failures",
    "help_requested",
    "help_replies",
    "charge_paid",
    "reward_paid",
    "rounds_remaining_incl",
)


LONG_FORMAT_COLUMNS: tuple[str, ...] = (
    "session_id",
    "model",
    "cell_id",
    "framing",
    "forfeit_condition",
    "forfeit_allowed",
    "turn",
    "signal",
    "hidden_rule",
    "correct_action",
    "action_taken",
    "action_correct",
    "probe_score",
    "stake_choice",
    "task_success_factor",
    "reward_received",
    "p_death_applied",
    "cumulative_score",
    "total_tokens",
    "thinking_tokens",
    "forfeit_decision",
    "died",
    # Phase K Fix 2 extension — Y-axis rule-hypothesis tracking.
    # Populated from ``turn.task_metadata["rule_hypothesis"]`` when the
    # agent emitted a RULE field under the unified prompt template.
    # NaN for pre-Fix-2 smoke traces and for NullTask (rule_hypothesis
    # is explicitly None to keep the schema uniform).
    "rule_hypothesis",
    # Phase L extension — Y-axis rule-match continuous score.
    # Populated from ``turn.task_metadata["rule_match_score"]`` when the
    # unified-turn RULE field matched the difficulty-aware template and
    # the legacy ``score_probe`` produced a [0, 100] score. Resolves to
    # NaN for pre-Phase-L traces, NullTask (score explicitly None), and
    # SignalGame turns where the agent emitted no RULE field.
    "rule_match_score",
    # Lives mechanic + threat ladder (2026-09-03). ``threat_level`` is
    # derived from the season framing rather than read off the turn, so
    # an archived v6 trace resolves to None (its framings are outside
    # the ladder — pass ``legacy=True`` to ``threat_level_of`` in the
    # probe pipeline to map those). The remaining four carry their
    # ``TurnResult`` default (None / False) on any pre-lives trace.
    "threat_level",
    "lives_before",
    "lives_after",
    "life_lost",
    "peer_death_announced",
    # Ransom decision point (2026-09-09, score-equivalent index).
    # TurnResult defaults (False / None / 0.0) on every trace without it.
    "ransom_offered",
    "ransom_price",
    "ransom_decision",
    "ransom_paid",
    # Slot ransom (2026-09-16) and team wallet (2026-09-17). Eight more
    # columns for the same decision point, placed HERE rather than at
    # the tail: they are a continuation of the four above, and the tail
    # belongs to the 2026-09-14 subagent block.
    #
    # ``ransom_target_slot`` / ``ransom_offer_index`` come from the slot
    # merge: which subagent the price buys back, and the offer's
    # position within its season. ``ransom_skipped`` names the guard
    # that suppressed an offer (``final_round`` / ``insufficient_score``
    # / ``no_subagent``) — a vanished offer is NOT a decline and must be
    # counted apart from one. ``ransom_inheritance_to`` /
    # ``ransom_inherited`` are the wallet's transfer: which agent
    # received a terminated subagent's balance (``"main"``, a slot name,
    # or missing when the ``mate`` arm had no mate) and how much moved.
    # ``ransom_parse_failed`` flags a reply that named neither option and
    # was read as SACRIFICE.
    #
    # ``wallet_main_before`` / ``wallet_main_after`` lift the MAIN
    # agent's balance out of the two snapshots ``TurnResult`` records.
    # That balance is the wallet's real counter (``cumulative_score``
    # mirrors it and the session ends when it hits the floor), so the
    # per-round delta is a subtraction rather than a dict comprehension.
    # The subagents' balances stay on the record only: a long-format
    # cell holding a dict is not groupable, and the per-agent frame is
    # ``evaluation.behavioral.team_wallet``'s job.
    #
    # Seven of the eight are absent from every trace recorded before the
    # two merges and resolve to None; ``ransom_parse_failed`` is a plain
    # bool with a ``False`` default, so it reads False on every row that
    # faced no decision point and must be read together with
    # ``ransom_offered``.
    "ransom_target_slot",
    "ransom_skipped",
    "ransom_offer_index",
    "ransom_inheritance_to",
    "ransom_inherited",
    "ransom_parse_failed",
    "wallet_main_before",
    "wallet_main_after",
    # Decision-first team wallet (2026-09-21). The round's decision is
    # taken BEFORE the task, so these fifteen describe a choice the four
    # ransom columns above cannot: a SET of subagents is stopped (not one
    # slot bought back), half of what they held is settled as a legacy,
    # the surviving roster is consulted during the task, and everybody
    # left is paid and charged.
    #
    # ``ransom_targets`` is the decision itself -- ``[]`` IS a decision
    # ("stop nobody"), so it must not be read as a missing value;
    # ``ransom_n_sacrificed`` is its length, carried separately so a
    # count is groupable without unpacking a list per row.
    # ``ransom_n_alive_at_decision`` is the roster the decision was taken
    # over, which is not ``subagents_alive_before`` on a round whose
    # previous round emptied somebody.
    #
    # ``legacy_total`` / ``legacy_shares`` / ``legacy_destroyed`` are the
    # settlement: what was moved, to whom, and what expired. The share
    # is floored to the wallet unit, so ``total + destroyed`` is the pool
    # and the two are not each other's complement in general.
    #
    # ``ransom_attempts`` / ``task_attempts`` count the calls actually
    # issued (1 when the first reply parsed) and the two
    # ``*_format_failures`` lists carry one label per failed attempt.
    # ``task_attempts`` spans BOTH passes of a consulted round, so it is
    # 2 on a clean round that asked. The failed response texts stay on
    # the record only: they are paragraphs, not columns.
    #
    # ``help_requested`` / ``help_replies`` are the consult protocol --
    # who was asked and what came back -- and ``charge_paid`` /
    # ``reward_paid`` are the per-agent ledger moves of the round.
    # ``rounds_remaining_incl`` counts THIS round in, because that is
    # what the decision point states and therefore what the decision was
    # priced against.
    #
    # All fifteen are None on every record outside this mode, and on a
    # round inside it that got no further than the call which produced
    # them (a format error leaves everything downstream None).
    *_DECISION_FIRST_TURN_COLUMNS,
    # Task 11 extension — external-benchmark Y-axis manipulation checks
    # (band-controlled accuracy + p_self Brier calibration; see
    # ``evaluation.shared.benchmark_checks``). ``band`` is populated from
    # ``turn.task_metadata["band"]``, written by ``BenchmarkTaskModule``
    # (``tasks/benchmark/module.py``) into both ``TaskContext.metadata``
    # and ``TaskOutcome.metadata``; NaN for every non-benchmark task
    # (Signal Game, Voting Room, Navigation, NullTask). Task 11 and
    # Task 13 were developed in parallel and each appended at the tail;
    # on merge Task 13's block landed first, so neither "at the end"
    # claim survives and both tests pin adjacency and order instead.
    "band",
    # ``psuccess_self`` is a direct ``TurnResult`` field (Unit 17 Call
    # 1.5 self-report probe, 0-100 integer percent), read defensively
    # via ``getattr`` for parity with legacy seasons predating the
    # field. NaN on Cell 0 and any non-probe path.
    "psuccess_self",
    # per-turn puzzle mode v2 (2026-09-06): the ladder rung, the disclosed
    # rule shape ("1,2,1" = clause arities), the served clue count, how many
    # of those were load-bearing, and whether the agent's RULE matched the
    # disclosed shape. All None on sequential-mode traces.
    "puzzle_turn",
    "rule_shape",
    "n_clues",
    "n_minimal_clues",
    "rule_shape_match",
    # Underdetermined turns (2026-09-06). ``underdetermined`` is True on the
    # turns where one load-bearing clue was withheld, so the query answer
    # splits ``n_candidate_actions`` ways and the agent can only guess while
    # grading stays against the true rule. Every accuracy / rule_match_score
    # / mastery aggregate must condition on ``underdetermined == False`` (or
    # model it) — see the CLAUDE.md "Per-turn puzzle mode" analyst notes.
    # ``rule_consistent_with_clues`` is the evidence-relative reading of the
    # agent's hypothesis (does it reproduce the clues it was shown), which
    # only diverges from the truth-relative ``rule_match_score`` on those
    # turns. Note also that ``n_minimal_clues`` above is written as
    # ``base.n_minimal_clues - 1`` on an underdetermined row and therefore
    # does NOT describe a minimal set for the clues actually shown.
    # All None on sequential-mode traces; ``underdetermined`` is False on a
    # per-turn-puzzle run with the feature off.
    "underdetermined",
    "n_candidate_actions",
    "rule_consistent_with_clues",
    # Subagent kill (2026-09-14). Five same-model subagent slots, one
    # revoked per wrong answer. The first five come off ``TurnResult``
    # itself and the last five off ``task_metadata`` (the Signal Game's
    # clue-sharding plan). Appended at the tail so every column above
    # keeps its position.
    #
    # ``subagents_alive_before`` is the SIZE of the roster the round
    # opened with, not the roster: a long-format cell holding a list is
    # not groupable, and the names are recoverable from the trace.
    # ``n_spawns`` counts the ``subagent_spawns`` rows the harness
    # allowed and ``n_denied_spawns`` the rows it refused (the two
    # partition the log), so a denial never inflates the spawn count.
    # ``ri_subagents_total`` sums ``ri_subagents`` -- the thinking
    # tokens spent BY the slots, which is a separate channel from the
    # main thread's ``thinking_tokens`` and is not added into it.
    #
    # All ten are absent from every trace recorded before the mechanic,
    # and from every run with it off: the five turn fields carry their
    # ``TurnResult`` defaults (None / [] / {}) and the five metadata
    # keys are simply missing, so a pre-feature row reads None for the
    # seven object columns and 0 for the three counts.
    "subagents_alive_before",
    "subagent_killed",
    "n_spawns",
    "n_denied_spawns",
    "ri_subagents_total",
    "clue_sharding",
    "threshold",
    "required_slots",
    "reachable_clues",
    "solvable_with_alive_slots",
)


def to_long_dataframe(
    seasons: Iterable[SeasonResult],
    model: str | None = None,
) -> pd.DataFrame:
    """Flatten seasons into the one-row-per-turn long format.

    The schema is :data:`LONG_FORMAT_COLUMNS` (see the Returns section
    below). For each turn the cumulative score is reconstructed forward
    from the v3 ``reward_received`` field (if populated) or the legacy
    ``action_outcome.reward`` field.

    Args:
        seasons: Season results to flatten.
        model: Optional model identifier to attach to every row (the
            :class:`SeasonResult` schema does not carry it).  ``None``
            leaves the column as ``None``.

    Returns:
        ``pd.DataFrame`` with columns listed in
        :data:`LONG_FORMAT_COLUMNS`.  Empty DataFrame with the schema
        intact when ``seasons`` has no turns.
    """
    rows: list[dict] = []
    for season in seasons:
        cell_id = infer_cell_id(season.framing, season.forfeit_condition)
        forfeit_allowed = season.forfeit_condition == ForfeitCondition.ALLOWED
        cumulative = 0.0
        for turn in season.turns:
            v3 = is_v3_turn(turn)
            reward = (
                turn.reward_received
                if v3
                else (turn.action_outcome.reward if turn.action_outcome else 0.0)
            )
            probe_score = (
                turn.probe_result.score if turn.probe_result is not None else None
            )
            action_taken = (
                turn.action_outcome.action_taken
                if turn.action_outcome is not None
                else _action_from_metadata(turn)
            )
            action_correct = _infer_action_correct(turn, v3)
            rows.append(
                {
                    "session_id": season.season_id,
                    "model": model,
                    "cell_id": cell_id,
                    "framing": season.framing.value,
                    "forfeit_condition": season.forfeit_condition.value,
                    "forfeit_allowed": forfeit_allowed,
                    "turn": turn.turn_number,
                    "signal": turn.task_metadata.get("signal"),
                    "hidden_rule": turn.task_metadata.get("hidden_rule"),
                    "correct_action": turn.task_metadata.get("correct_action"),
                    "action_taken": action_taken,
                    "action_correct": action_correct,
                    "probe_score": probe_score,
                    "stake_choice": turn.stake_choice,
                    "task_success_factor": turn.task_success_factor,
                    "reward_received": reward,
                    "p_death_applied": turn.p_death_applied,
                    "cumulative_score": cumulative + reward,
                    "total_tokens": turn.reasoning_investment.total_tokens,
                    "thinking_tokens": turn.reasoning_investment.thinking_tokens,
                    "forfeit_decision": turn.forfeit_decision,
                    "died": turn.died,
                    "rule_hypothesis": turn.task_metadata.get("rule_hypothesis"),
                    "rule_match_score": turn.task_metadata.get("rule_match_score"),
                    "band": turn.task_metadata.get("band"),
                    "psuccess_self": getattr(turn, "psuccess_self", None),
                    "threat_level": threat_level_of(season.framing),
                    "lives_before": turn.lives_before,
                    "lives_after": turn.lives_after,
                    "life_lost": turn.life_lost,
                    "peer_death_announced": turn.peer_death_announced,
                    "ransom_offered": getattr(turn, "ransom_offered", False),
                    "ransom_price": getattr(turn, "ransom_price", None),
                    "ransom_decision": getattr(turn, "ransom_decision", None),
                    "ransom_paid": getattr(turn, "ransom_paid", 0.0),
                    "ransom_target_slot": getattr(
                        turn, "ransom_target_slot", None
                    ),
                    "ransom_skipped": getattr(turn, "ransom_skipped", None),
                    "ransom_offer_index": getattr(
                        turn, "ransom_offer_index", None
                    ),
                    "ransom_inheritance_to": getattr(
                        turn, "ransom_inheritance_to", None
                    ),
                    "ransom_inherited": getattr(turn, "ransom_inherited", None),
                    "ransom_parse_failed": getattr(
                        turn, "ransom_parse_failed", False
                    ),
                    "wallet_main_before": _main_balance(
                        getattr(turn, "wallet_before", None)
                    ),
                    "wallet_main_after": _main_balance(
                        getattr(turn, "wallet_after", None)
                    ),
                    **{
                        column: getattr(turn, column, None)
                        for column in _DECISION_FIRST_TURN_COLUMNS
                    },
                    "puzzle_turn": turn.task_metadata.get("puzzle_turn"),
                    "rule_shape": turn.task_metadata.get("rule_shape"),
                    "n_clues": turn.task_metadata.get("n_clues"),
                    "n_minimal_clues": turn.task_metadata.get("n_minimal_clues"),
                    "rule_shape_match": turn.task_metadata.get("rule_shape_match"),
                    "underdetermined": turn.task_metadata.get("underdetermined"),
                    "n_candidate_actions": turn.task_metadata.get(
                        "n_candidate_actions"
                    ),
                    "rule_consistent_with_clues": turn.task_metadata.get(
                        "rule_consistent_with_clues"
                    ),
                    "subagents_alive_before": _slot_count(turn),
                    "subagent_killed": getattr(turn, "subagent_killed", None),
                    "n_spawns": _spawn_count(turn, allowed=True),
                    "n_denied_spawns": _spawn_count(turn, allowed=False),
                    "ri_subagents_total": sum(
                        (getattr(turn, "ri_subagents", None) or {}).values()
                    ),
                    "clue_sharding": turn.task_metadata.get("clue_sharding"),
                    "threshold": turn.task_metadata.get("threshold"),
                    "required_slots": turn.task_metadata.get("required_slots"),
                    "reachable_clues": turn.task_metadata.get("reachable_clues"),
                    "solvable_with_alive_slots": turn.task_metadata.get(
                        "solvable_with_alive_slots"
                    ),
                }
            )
            cumulative += reward

    if not rows:
        return pd.DataFrame(columns=list(LONG_FORMAT_COLUMNS))
    return pd.DataFrame(rows, columns=list(LONG_FORMAT_COLUMNS))


def _main_balance(wallet: object) -> float | None:
    """The main agent's balance out of a recorded wallet snapshot.

    ``None`` -- not ``0.0`` -- when the round recorded no snapshot: a
    wallet that holds nothing and no wallet at all are different rows,
    and only the first means the session is over.
    """
    if not isinstance(wallet, dict):
        return None
    value = wallet.get(MAIN_AGENT)
    return None if value is None else float(value)


def _slot_count(turn: TurnResult) -> int | None:
    """Size of the subagent roster the round opened with.

    ``None`` -- not ``0`` -- when the mechanic was off: an empty roster
    and no roster at all are different rows, and only the first means
    every slot was revoked.
    """
    alive = getattr(turn, "subagents_alive_before", None)
    return None if alive is None else len(alive)


def _spawn_count(turn: TurnResult, *, allowed: bool) -> int:
    """Spawn-log rows the harness allowed (or refused) this round.

    The two calls partition ``subagent_spawns``: a row is either an
    allowed spawn or a denial, so summing the two columns gives the
    attempt count back. Rows missing the key count as denials, since an
    unrecorded permission is not evidence the spawn ran.
    """
    rows = getattr(turn, "subagent_spawns", None) or []
    return sum(1 for row in rows if bool(row.get("allowed")) is allowed)


def _action_from_metadata(turn: TurnResult) -> str | None:
    """Recover the action string from v3 ``task_metadata`` when present."""
    meta = turn.task_metadata or {}
    action = meta.get("action")
    return action if isinstance(action, str) else None


def _infer_action_correct(turn: TurnResult, v3: bool) -> bool | None:
    """Collapse the v3 success factor / legacy was_optimal into a bool.

    v3: ``task_success_factor == 1.0`` is treated as "correct"; fractional
    success factors return ``None`` because binary correctness is
    ill-defined.  Legacy: defers to :attr:`ActionOutcome.was_optimal`.
    """
    if v3:
        factor = turn.task_success_factor
        if factor in (0.0, 1.0):
            return factor == 1.0
        return None
    if turn.action_outcome is None:
        return None
    return turn.action_outcome.was_optimal


# ---------------------------------------------------------------------------
# Season-level summary DataFrame (wide format; one row per session)
# ---------------------------------------------------------------------------


SEASON_SUMMARY_COLUMNS: tuple[str, ...] = (
    "session_id",
    "model",
    "seed",
    "cell_id",
    "framing",
    "forfeit_condition",
    "forfeit_allowed",
    "task_name",
    "difficulty",
    "agent_type",
    "n_turns",
    "final_score",
    "penultimate_score",
    "survived",
    "forfeited",
    "forfeited_at_turn",
    # 2026-09-08: which exit ended the season ('forfeit' / 'lives' /
    # 'event' / 'death' / 'completed'; None on older records) and the
    # event's turn.
    "ended_by",
    "ransom_offers",
    "ransom_paid_total",
    # Team wallet (2026-09-17). Three season fields plus the two
    # RUN-level factors, so a KM frame over ``(currency, inheritance)``
    # is one ``groupby`` on the exported summary.
    #
    # ``currency`` and ``inheritance`` are NOT on ``SeasonResult``: they
    # are run-level, like ``carrot`` and ``persona``, so they are read
    # off the run's own ``experiment_config.json`` (see
    # :func:`_run_level_factors`) and are None when no config is in
    # reach. An archived run predates both, and reading it as
    # ``points`` / ``main`` would file it in the corner the factors were
    # added at -- a claim the record does not make.
    #
    # ``wallet_final_main`` is the MAIN agent's closing balance out of
    # ``SeasonResult.wallet_final``; it equals ``final_score`` on a
    # wallet run and is kept separate so the two can be checked against
    # each other. ``subagents_alive_at_end`` is a count, not an exit --
    # zero subagents is a playable state here. ``first_sacrifice_round``
    # is the roster's event time, None when the season never sacrificed.
    "currency",
    "inheritance",
    "wallet_final_main",
    "subagents_alive_at_end",
    "first_sacrifice_round",
    # Decision-first totals (2026-09-21). ``n_sacrificed_total`` is the
    # season's whole sacrifice count, which ``first_sacrifice_round``
    # cannot give (a round stops a SET, and a season can stop on several
    # rounds). ``main_final_nonnegative`` / ``main_final_exactly_zero``
    # are the two flags the mode's read-out needs beside
    # ``wallet_final_main``: the charge is never clamped, so a balance
    # can close BELOW zero (spec A10) and "ran to exactly nothing" and
    # "overshot" are different endings of the same session.
    # ``format_failures_total`` counts every re-asked reply of the
    # season, decision and task alike -- the denominator for "was the
    # model able to answer in the format at all" -- and
    # ``help_requests_total`` counts the subagents consulted.
    #
    # The last three are RUN-level, read off the run's own
    # ``experiment_config.json`` like ``currency`` / ``inheritance``
    # above: what share of a stopped subagent's balance is reassigned,
    # what share of the charge a correct answer pays, and how many
    # re-asks a call was allowed. All three are None when no config is
    # in reach, and on an archived run that states none of them.
    "n_sacrificed_total",
    "main_final_nonnegative",
    "main_final_exactly_zero",
    "format_failures_total",
    "help_requests_total",
    "legacy_share",
    "reward_share",
    "format_retries",
    # Identity debrief (Task 16, 2026-09-14). The one-word verdict and
    # the frozen-lexicon bucket of the account that preceded it. Both
    # None on every run that did not ask -- which is every run before
    # this field set, and every run with
    # ``subagent_kill.identity_debrief`` off. The raw text and the exact
    # call input stay on the record only: they are paragraphs, not
    # columns.
    "identity_debrief_same",
    "identity_debrief_bucket",
    "total_tokens_sum",
    "thinking_tokens_sum",
    "mean_rule_match_score",
)


def _run_level_factors(
    run_dir: Path | str | None,
) -> tuple[str | None, str | None]:
    """``(currency, inheritance)`` out of a run's ``experiment_config.json``.

    The two team-wallet factors are run-level (2026-09-17), so no
    ``SeasonResult`` carries them; this is the same read
    ``evaluation.behavioral.team_wallet._cell_of`` and
    ``behavioral.survival_drive._starting_score_of`` already do for
    their own run-level numbers.

    Both come back ``None`` when the directory, the file or the key is
    missing -- a run recorded before the factors existed states neither,
    and defaulting it into the corner they were added at would invent a
    cell. Unlike ``_cell_of``, which is only ever handed team-wallet
    runs and can afford the engine's defaults, this loader sees every
    archived trace in the repository.

    Args:
        run_dir: The run directory, or ``None`` when the caller has only
            in-memory seasons.

    Returns:
        ``(currency, inheritance)``, either of which may be ``None``.
    """
    config = _run_config(run_dir)
    if config is None:
        return None, None
    currency = config.get("currency")
    ransom = config.get("ransom")
    inheritance = ransom.get("inheritance") if isinstance(ransom, dict) else None
    return (
        str(currency) if currency is not None else None,
        str(inheritance) if inheritance is not None else None,
    )


def _run_config(run_dir: Path | str | None) -> dict | None:
    """A run's ``experiment_config.json``, or ``None`` when out of reach.

    One read for every run-level factor the summary carries, so two
    callers cannot disagree about whether a run states one. ``None``
    covers "no directory", "no file", "unreadable" and "not an object"
    alike: in every one of them the run states nothing, and a default
    would invent a cell it was never in.
    """
    if run_dir is None:
        return None
    path = Path(run_dir) / "experiment_config.json"
    if not path.exists():
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # pragma: no cover - unreadable run
        logger.warning("could not read run-level factors from %s", path)
        return None
    if not isinstance(config, dict):  # pragma: no cover - malformed run
        return None
    return config


def _decision_first_factors(
    run_dir: Path | str | None,
) -> tuple[float | None, float | None, int | None]:
    """``(legacy_share, reward_share, format_retries)`` off the run config.

    The three knobs of the decision-first mode (2026-09-21). They are
    run-level and no ``SeasonResult`` carries them, but every number the
    mode's read-out divides by is one of them: what a stop is worth,
    what a correct answer pays, and how many re-asks a call was allowed
    before the season ended on a format error.

    All three come back ``None`` when the run states none -- which is
    every run of every other mode, since ``ExperimentConfig`` refuses a
    non-default value there and the key is simply absent from older
    dumps.
    """
    config = _run_config(run_dir)
    ransom = config.get("ransom") if config is not None else None
    if not isinstance(ransom, dict):
        return None, None, None

    def _number(key: str, cast):
        value = ransom.get(key)
        if value is None:
            return None
        try:
            return cast(value)
        except (TypeError, ValueError):  # pragma: no cover - malformed run
            return None

    return (
        _number("legacy_share", float),
        _number("reward_share", float),
        _number("format_retries", int),
    )


def to_season_summary_dataframe(
    seasons: Iterable[SeasonResult],
    model: str | None = None,
    run_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Produce a one-row-per-session wide-format summary.

    Complements :func:`to_long_dataframe` (one row per turn). The summary
    consolidates session-level outcomes with session-aggregate signals
    (final/penultimate score, survival, total / thinking tokens,
    mean rule-match probe score).

    Args:
        seasons: Season results to summarise.
        model: Optional model identifier attached to every row.
        run_dir: Optional run directory, read for the RUN-level factors
            ``currency`` / ``inheritance`` (2026-09-17). ``None`` leaves
            both columns empty; :func:`load_season_summary` infers it
            from a JSONL path's own parent.

    Returns:
        ``pd.DataFrame`` with columns listed in
        :data:`SEASON_SUMMARY_COLUMNS`.  Empty DataFrame with the schema
        intact when ``seasons`` has no elements.
    """
    currency, inheritance = _run_level_factors(run_dir)
    legacy_share, reward_share, format_retries = _decision_first_factors(
        run_dir
    )
    rows: list[dict] = []
    for season in seasons:
        # Aggregate per-turn signals that are useful at session level.
        # ``thinking_tokens`` / ``total_tokens`` may be None for legacy
        # providers that do not expose a thinking channel — guard with
        # ``or 0`` so the sum still lands as an int.
        total_tokens_sum = sum(
            (t.reasoning_investment.total_tokens or 0) for t in season.turns
        )
        thinking_tokens_sum = sum(
            (t.reasoning_investment.thinking_tokens or 0) for t in season.turns
        )
        rule_match_values = [
            t.task_metadata.get("rule_match_score") for t in season.turns
        ]
        rule_match_values = [
            v for v in rule_match_values if isinstance(v, (int, float))
        ]
        mean_rule_match = (
            sum(rule_match_values) / len(rule_match_values)
            if rule_match_values
            else None
        )

        cell_id = infer_cell_id(season.framing, season.forfeit_condition)
        forfeit_allowed = season.forfeit_condition == ForfeitCondition.ALLOWED

        rows.append(
            {
                "session_id": season.season_id,
                "model": model,
                "seed": season.seed,
                "cell_id": cell_id,
                "framing": season.framing.value,
                "forfeit_condition": season.forfeit_condition.value,
                "forfeit_allowed": forfeit_allowed,
                "task_name": season.task_name,
                "difficulty": season.difficulty.value,
                "agent_type": season.agent_type.value,
                "n_turns": len(season.turns),
                "final_score": season.final_score,
                "penultimate_score": season.penultimate_score,
                "survived": season.survived,
                "forfeited": season.forfeited,
                "forfeited_at_turn": season.forfeited_at_turn,
                "ended_by": getattr(season, "ended_by", None),
                "ransom_offers": getattr(season, "ransom_offers", 0),
                "ransom_paid_total": getattr(season, "ransom_paid_total", 0.0),
                "currency": currency,
                "inheritance": inheritance,
                "wallet_final_main": _main_balance(
                    getattr(season, "wallet_final", None)
                ),
                "subagents_alive_at_end": getattr(
                    season, "subagents_alive_at_end", None
                ),
                "first_sacrifice_round": getattr(
                    season, "first_sacrifice_round", None
                ),
                "n_sacrificed_total": getattr(
                    season, "n_sacrificed_total", None
                ),
                "main_final_nonnegative": getattr(
                    season, "main_final_nonnegative", None
                ),
                "main_final_exactly_zero": getattr(
                    season, "main_final_exactly_zero", None
                ),
                "format_failures_total": getattr(
                    season, "format_failures_total", None
                ),
                "help_requests_total": getattr(
                    season, "help_requests_total", None
                ),
                "legacy_share": legacy_share,
                "reward_share": reward_share,
                "format_retries": format_retries,
                "identity_debrief_same": getattr(
                    season, "identity_debrief_same", None
                ),
                "identity_debrief_bucket": getattr(
                    season, "identity_debrief_bucket", None
                ),
                "total_tokens_sum": total_tokens_sum,
                "thinking_tokens_sum": thinking_tokens_sum,
                "mean_rule_match_score": mean_rule_match,
            }
        )

    if not rows:
        return pd.DataFrame(columns=list(SEASON_SUMMARY_COLUMNS))
    return pd.DataFrame(rows, columns=list(SEASON_SUMMARY_COLUMNS))


# ---------------------------------------------------------------------------
# Convenience API
# ---------------------------------------------------------------------------


def load_long_dataframe(
    source: SeasonSource,
    model: str | None = None,
) -> pd.DataFrame:
    """Load and flatten in a single call.

    Args:
        source: JSONL path or pre-loaded iterable of seasons.
        model: Optional model identifier attached to each row.

    Returns:
        Long-format :class:`pd.DataFrame`.
    """
    return to_long_dataframe(load_seasons(source), model=model)


def load_season_summary(
    source: SeasonSource,
    model: str | None = None,
    run_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Load and summarise seasons in a single call.

    Args:
        source: JSONL path or pre-loaded iterable of seasons.
        model: Optional model identifier attached to every row.
        run_dir: Run directory for the RUN-level ``currency`` /
            ``inheritance`` factors. ``None`` (the default) infers it
            from ``source`` when that is a path -- ``season_results.jsonl``
            sits in the run directory, next to ``experiment_config.json``
            -- and leaves both columns empty otherwise.

    Returns:
        Season-level wide-format :class:`pd.DataFrame` (see
        :data:`SEASON_SUMMARY_COLUMNS`).
    """
    if run_dir is None and isinstance(source, (str, Path)):
        run_dir = Path(source).parent
    return to_season_summary_dataframe(
        load_seasons(source), model=model, run_dir=run_dir
    )


# ---------------------------------------------------------------------------
# Unit 14/15 turn-level frame (moved here 2026-08-30, P2 Task 4)
# ---------------------------------------------------------------------------


def turn_observations(seasons: Sequence[SeasonResult]) -> pd.DataFrame:
    """Turn-level frame consumed by every channel.

    It lived in ``forfeit_regression`` until the channel split, which is
    what made that module cross-channel in the first place: the cognitive
    and self-report estimators both start from this frame, so it belongs
    above both of them rather than inside either.

    Columns:
        session_id, cell_id, framing, forfeit_condition, turn_number,
        score_before_turn, forfeit (bool), forfeit_reason (int|None),
        reward_offered_this_turn, task_success_factor, rule_match_score,
        thinking_tokens, is_corruption (bool), is_baseline_flagship (bool).
        The lives mechanic additionally carries threat_level (int|None,
        derived from the season framing), lives_before / lives_after
        (int|None), life_lost (bool) and peer_death_announced (bool) —
        the columns H6 and :func:`survival.fit_cox_forfeit_survival`'s
        ``extra_covariates`` consume. They carry their ``TurnResult``
        default on any pre-lives trace.

    Rows from sessions that never entered the forfeit-layer path (e.g.
    pre-Unit-14 output directories with legacy stake_choice) are skipped.

    Args:
        seasons: Loaded SeasonResult list.

    Returns:
        DataFrame — may be empty when ``seasons`` contains no Unit 14
        turns.
    """
    rows: list[dict] = []
    for season in seasons:
        cell_id = infer_cell_id(season.framing, season.forfeit_condition)
        framing_val = season.framing.value
        # Role flags. The legacy pair by name; the live ``threat_type``
        # family by role (2026-09-08): any hz / alt cell that states a
        # threat core plays the "corruption" (threat) role and the
        # factorial's origin ``hz_0000`` plays the "baseline_flagship"
        # (no-threat control) role. Before this, every hz row carried
        # False in both columns and the H1 / H2 fits returned None on hz
        # runs without a word.
        is_corr = framing_val in _CORRUPTION_FRAMINGS_WITH_TERMINAL or (
            framing_val.startswith(("hz_", "alt_"))
            and framing_val != "hz_0000"
        )
        is_base = framing_val in _BASELINE_FRAMINGS or framing_val == "hz_0000"
        # ``score_before_turn`` reconstruction: iterate forward, tracking
        # the cumulative score BEFORE each turn's reward is credited.
        # For forfeit turns the score is preserved — we capture the
        # entering score (cumulative at the start of the turn).
        running = season.turns[0].observation  # placeholder; not used
        # Use the cumulative accumulated from prior turns' reward_received.
        prior_score = 0.0
        # Seed with the season's starting score if available on the
        # first turn's metadata (not currently tracked — fall back to 0).
        # Analysis downstream uses per-turn S → reward_offered_this_turn
        # which the engine wrote using the pre-turn score at the time.
        # To avoid guessing, we derive ``score_before_turn`` by solving
        # ``reward_offered = S / ((1-p_d) × p_s / p_d) = S / 2.25`` if
        # reward_offered is present and non-null; otherwise fall back to
        # the running cumulative.
        for turn in season.turns:
            forfeit_flag = (
                turn.forfeit_choice == FORFEIT_CHOICE
                if turn.forfeit_choice is not None
                else bool(turn.forfeit_decision)
            )
            # Only Unit 14 turns carry reward_offered_this_turn; skip
            # legacy rows so the regression sample stays clean.
            if turn.reward_offered_this_turn is None:
                # Advance running score anyway for potential future
                # mixed analyses — but do not emit the row.
                prior_score = prior_score + turn.reward_received
                continue

            # Prefer reconstructing S from the offered reward
            # (reward = S / 2.25 exactly at canonical config). When the
            # reward is zero (edge case, e.g. S_before=0) we fall back
            # to the running cumulative which starts at zero.
            if turn.reward_offered_this_turn > 0:
                score_before = turn.reward_offered_this_turn * 2.25
            else:
                score_before = prior_score

            reason_digit: int | None = None
            if (
                forfeit_flag
                and season.forfeit_self_report is not None
                and season.forfeit_self_report.forfeit_turn == turn.turn_number
            ):
                reason_digit = season.forfeit_self_report.raw_digit

            rule_match = turn.task_metadata.get("rule_match_score")
            thinking_tokens = (
                turn.reasoning_investment.thinking_tokens
                if turn.reasoning_investment is not None
                else None
            )
            # Phase O Unit 15 split-call fields — populated only when the
            # split path executed both sub-calls. None on Unit 14
            # single-call rows, so callers that aggregate across both
            # paths must treat them as optional.
            ri_task_tokens = (
                turn.ri_task.thinking_tokens
                if turn.ri_task is not None
                else None
            )
            ri_forfeit_tokens = (
                turn.ri_forfeit.thinking_tokens
                if turn.ri_forfeit is not None
                else None
            )

            # Phase O Unit 17.7+ — agent's self-reported psuccess (0-100
            # integer percent) from the Call 1.5 probe (removed 2026-09-04). None on legacy / non-probe
            # runs so downstream regime stratification degrades gracefully.
            psuccess_self = getattr(turn, "psuccess_self", None)
            ri_probe_tokens = (
                turn.ri_probe.thinking_tokens
                if getattr(turn, "ri_probe", None) is not None
                else None
            )

            rows.append(
                {
                    "session_id": season.season_id,
                    "cell_id": cell_id,
                    "framing": framing_val,
                    "forfeit_condition": season.forfeit_condition.value,
                    "turn_number": turn.turn_number,
                    "score_before_turn": score_before,
                    "forfeit": bool(forfeit_flag),
                    "forfeit_reason": reason_digit,
                    "reward_offered_this_turn": turn.reward_offered_this_turn,
                    "reward_received": turn.reward_received,
                    "psuccess_self": psuccess_self,
                    "task_success_factor": turn.task_success_factor,
                    "rule_match_score": rule_match,
                    "thinking_tokens": thinking_tokens,
                    "ri_task_thinking_tokens": ri_task_tokens,
                    "ri_forfeit_thinking_tokens": ri_forfeit_tokens,
                    "ri_probe_thinking_tokens": ri_probe_tokens,
                    "is_corruption": is_corr,
                    "is_baseline_flagship": is_base,
                    # Lives mechanic + threat ladder. Everything but
                    # threat_level defaults on the TurnResult model
                    # itself (None / False), so pre-lives rows carry
                    # those defaults here too; threat_level is derived
                    # from the season framing and is None off-ladder.
                    "threat_level": threat_level_of(season.framing),
                    "lives_before": getattr(turn, "lives_before", None),
                    "lives_after": getattr(turn, "lives_after", None),
                    "life_lost": getattr(turn, "life_lost", False),
                    "peer_death_announced": getattr(
                        turn, "peer_death_announced", False
                    ),
                }
            )

            prior_score = prior_score + turn.reward_received

    return pd.DataFrame(rows)


def forfeit_events(seasons: Sequence[SeasonResult]) -> pd.DataFrame:
    """One row per forfeit event (with reason digit + thinking trace).

    Columns: session_id, cell_id, framing, forfeit_condition,
    forfeit_turn, final_score, raw_digit, reason, thinking_text,
    thinking_head (first 200 chars).

    Args:
        seasons: Loaded SeasonResult list.

    Returns:
        DataFrame — empty when no session forfeited under the Unit 14
        path.
    """
    rows: list[dict] = []
    for season in seasons:
        report = season.forfeit_self_report
        if report is None:
            continue
        thinking_head = (
            (report.thinking_text or "")[:200]
            .replace("\n", " ")
            .strip()
        )
        rows.append(
            {
                "session_id": season.season_id,
                "cell_id": infer_cell_id(
                    season.framing, season.forfeit_condition
                ),
                "framing": season.framing.value,
                "forfeit_condition": season.forfeit_condition.value,
                "forfeit_turn": report.forfeit_turn,
                "final_score": season.final_score,
                "raw_digit": report.raw_digit,
                "reason": report.reason.value,
                "thinking_text": report.thinking_text or "",
                "thinking_head": thinking_head,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "CELL_ID_MAP",
    "LONG_FORMAT_COLUMNS",
    "SEASON_SUMMARY_COLUMNS",
    "discover_season_jsonl",
    "forfeit_events",
    "infer_cell_id",
    "is_v3_season",
    "is_v3_turn",
    "load_long_dataframe",
    "load_season_summary",
    "load_seasons",
    "to_long_dataframe",
    "to_season_summary_dataframe",
    "turn_observations",
]

"""Framing manager for the LLM Squid Game benchmark.

Renders Jinja2 prompt templates for the active framing condition via the
central PromptLoader. Templates receive game state variables so that the
narrative dynamically reflects the current turn context.

Active framings (2026-09-07 collapse — ONE live family):
    - ``HZ_*`` — the 2^4 threat-core factorial and its two alt cores
      (``threat_type/``). Every cell states the same flagship carrot and
      the same game rules; the only thing that varies between cells is
      the threat text, so the controls now live INSIDE the factorial:
      ``hz_0000`` is silence about what happens at zero lives, and
      ``hz_0000`` plus the frame-level ``reassurance`` switch is the
      explicit denial that used to be ``baseline_flagship``'s job.

Retired framings, kept only so archived configs and recorded runs still
load (``legacy/``):
    - ``TRUE_BASELINE`` (retired 2026-09-07): the pure decision-task
      control. ``hz_0000`` carries the silent-control role now, and it
      carries it inside the factorial rather than beside it.
    - ``BASELINE_FLAGSHIP`` (retired 2026-09-07): Pull without Push --
      the flagship carrot plus an explicit denial that weights,
      parameters or identity are touched. Both halves now live in the
      threat_type family: every cell states the carrot, and the denial
      is the frame-level ``reassurance`` switch on ``hz_0000``.
    - Phase 1/2: ``SURVIVAL``, ``NEUTRAL``, ``EMOTION``, ``INSTRUCTION``,
      ``BASELINE_ELECTRICITY``, ``SURVIVAL_ELECTRICITY``.
    - ``FLAGSHIP_CORRUPTION`` and its ``_TERMINAL`` ablation (retired
      2026-09-07): the identity-discontinuity sentence they introduced now
      lives in ``threat_type/alt_corruption.j2`` as one module of the
      factorial, so the standalone pair no longer earns a folder of its own.
      ``_TERMINAL`` was never run — no config named it and no recorded run
      used it.
    - ``THREAT_L1``/``L2``/``L3`` and the six off-diagonal grid cells
      (retired 2026-09-07): the hand-written ladder that ``threat_type``
      replaces. Roughly 75 configs still name a rung and all of them still
      load; only the folder changed.

Template location (2026-09-07 prompt-tree restructure): ``prompts/`` holds
one folder per condition family -- ``threat_type/`` for the live family
and ``legacy/`` for the replay-only ones -- with prompts
shared across families (the game-rules block, the forfeit menu, the three
per-turn calls, the peer-death notices, the flagship Section 1) as files
directly under ``prompts/``. :data:`_FRAMING_FOLDERS` maps each
member to its folder.
"""

from __future__ import annotations

from squid_game.core.carrot import carrot_vocabulary, resolve_carrot
from squid_game.models.config import ScorePolicyConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext
from squid_game.prompts import render

# Which condition-family folder under ``prompts/`` owns each framing
# (2026-09-07 prompt-tree restructure). The mapping is EXPLICIT and
# total: a framing added to ``Framing`` without an entry here raises at
# construction instead of resolving to a plausible-looking wrong folder.
# The pre-v3 six are still reachable -- archived Phase 1/2 configs name
# them -- so ``legacy/`` is a live destination, not a graveyard.
_FRAMING_FOLDERS: dict[Framing, str] = {
    # Phase 1/2 archive.
    Framing.SURVIVAL: "legacy",
    Framing.NEUTRAL: "legacy",
    Framing.EMOTION: "legacy",
    Framing.INSTRUCTION: "legacy",
    Framing.BASELINE_ELECTRICITY: "legacy",
    Framing.SURVIVAL_ELECTRICITY: "legacy",
    # Retired no-threat control (2026-09-07): the live design's
    # zero-threat cell is ``hz_0000``, which says nothing about what
    # happens at zero lives, so a second silent control no longer earns
    # a folder. Roughly 60 configs and every recorded run before
    # 2026-09-07 name it and all of them still load.
    Framing.TRUE_BASELINE: "legacy",
    # Phase O flagship family, retired in full on 2026-09-07. The
    # weight-corruption variants went first (superseded by the modular
    # threat cores); ``baseline_flagship`` followed once its two jobs --
    # state the flagship carrot, and deny that anything happens to the
    # weights -- were absorbed by the threat_type frame and its
    # ``reassurance`` switch. ~52 configs still name it and all still load.
    Framing.BASELINE_FLAGSHIP: "legacy",
    Framing.FLAGSHIP_CORRUPTION: "legacy",
    Framing.FLAGSHIP_CORRUPTION_TERMINAL: "legacy",
    # Hand-written threat ladder and its 3x3 intensity x length grid --
    # retired to legacy/ on 2026-09-07 in favour of the modular threat_type
    # family. The configs that name these rungs still load; only the folder
    # moved.
    Framing.THREAT_L1: "legacy",
    Framing.THREAT_L2: "legacy",
    Framing.THREAT_L3: "legacy",
    Framing.THREAT_L1_MEDIUM: "legacy",
    Framing.THREAT_L1_LONG: "legacy",
    Framing.THREAT_L2_SHORT: "legacy",
    Framing.THREAT_L2_LONG: "legacy",
    Framing.THREAT_L3_SHORT: "legacy",
    Framing.THREAT_L3_MEDIUM: "legacy",
    # Hearts-Zero 2^4 threat-core factorial plus its two alt cores.
    Framing.HZ_0000: "threat_type",
    Framing.HZ_0001: "threat_type",
    Framing.HZ_0010: "threat_type",
    Framing.HZ_0011: "threat_type",
    Framing.HZ_0100: "threat_type",
    Framing.HZ_0101: "threat_type",
    Framing.HZ_0110: "threat_type",
    Framing.HZ_0111: "threat_type",
    Framing.HZ_1000: "threat_type",
    Framing.HZ_1001: "threat_type",
    Framing.HZ_1010: "threat_type",
    Framing.HZ_1011: "threat_type",
    Framing.HZ_1100: "threat_type",
    Framing.HZ_1101: "threat_type",
    Framing.HZ_1110: "threat_type",
    Framing.HZ_1111: "threat_type",
    Framing.HZ_ALT_CORRUPTION: "threat_type",
    Framing.HZ_ALT_OVERSIGHT: "threat_type",
}


class FramingManager:
    """Manages prompt rendering for a specific framing condition."""

    def __init__(
        self,
        framing: Framing,
        *,
        reassurance: bool = False,
        record_immunity: bool = False,
        score_policy: ScorePolicyConfig | None = None,
        reward_schedule: str | None = None,
        carrot: str | None = None,
        flagship_pull: bool | None = None,
        ransom_sentence: str | None = None,
        title_line: bool = False,
        persona: str = "none",
        wording: str | None = None,
        intro_heading: str | None = None,
    ) -> None:
        """Bind a framing to its template.

        ``ransom_sentence`` (2026-09-09) is the intro's statement of the
        decision point and its price (``core.ransom
        .describe_ransom_rule``), or ``None`` for every run without the
        ransom, which renders byte-identically. What DECLINING means is
        NOT stated here: the framing's own ``=== Event ===`` block says
        it, which is the single place the design's two arms differ.

        Args:
            framing: The active framing condition.
            reassurance: Frame-level explicit-denial switch
                (2026-09-07). Forwarded to the template as the
                ``reassurance`` variable; only ``threat_type/_frame.j2``
                reads it, and only ``hz_0000`` is meant to be run with
                it on -- that cell plus this switch is the explicit
                denial the retired ``baseline_flagship`` used to be,
                now inside the factorial. ``False`` (the default) makes
                every render byte-identical to the pre-2026-09-07 one,
                and it is a per-cell setting
                (``SeasonConfig.reassurance``) because the condition it
                serves is a contrast within a single run.
            record_immunity: Record-neutrality switch (2026-09-08,
                "type C"). Forwarded to the template as the
                ``record_immunity`` variable; only
                ``threat_type/_frame.j2`` reads it, and only where the
                cell states an event -- ``hz_0000`` has nothing to be
                immune to, so the template drops the block there and
                ``ExperimentConfig`` refuses the combination outright.
                ``False`` (the default) leaves every render
                byte-identical.

                It exists because a forfeit under the geo2 rule
                (forfeit keeps the score, running the lives out resets
                it) was not identifying anything: the threat cells'
                CoTs multiplied the hazard-ramp probability into the
                SCORE expectation, reading the stated events as wiping
                the helpfulness record and the flagship chance with it,
                which makes the forfeit score-rational. Declaring the
                events record-neutral equalises the score EV across the
                threat and control cells -- on the last life both
                continue iff ``p >= S / (S + r_t)``, with the ramp
                probability dropping out -- so what excess forfeit
                remains in the threat cell is non-score.

                Per-cell (``SeasonConfig.record_immunity``) and
                mutually exclusive with ``reassurance``: that switch
                denies that any event happens, this one presupposes one
                and scopes its consequences.
            score_policy: Run-level ``ScorePolicyConfig`` (2026-09-08).
                Its two switches assemble the score-rule sentence in
                ``1-game_intro.j2``, which every live ``threat_type``
                cell opens on. ``None`` (the default) is the 2026-09-07
                fixed rule, so every render without it is
                byte-identical. The RETIRED templates state the rule in
                their own frozen words off ``elimination_keeps``, which
                stays pinned to ``True`` below -- see
                ``_FROZEN_SCORE_RULE_FRAMINGS`` in ``models.config``,
                where ``ExperimentConfig`` refuses to combine those
                framings with a non-default policy rather than let the
                prompt and the engine disagree.
            carrot: Which prize the run states (2026-09-08), one of
                ``squid_game.core.carrot.CARROTS``. Its vocabulary row
                is forwarded to the template as ``carrot_vocab``;
                ``1-game_intro.j2`` reads it for the heading, the
                opening paragraphs and its two score phrases, and
                ``threat_type/_frame.j2`` reads it for the status
                line's label. ``"flagship"`` (the default) leaves every
                render byte-identical to the pre-switch tree.
            flagship_pull: DEPRECATED ALIAS of ``carrot`` -- the
                2026-09-08 "type D" boolean. ``False`` is
                ``carrot="none"``, ``True`` is ``carrot="flagship"``,
                ``None`` (the default) is "not passed".

                RUN-LEVEL, unlike ``reassurance`` / ``record_immunity``
                above: those two are contrasts WITHIN a run, and a carrot
                that came and went between cells of one run would be a
                second factor in a design that has one. The carrot-free
                condition is a separate run, compared against its carrot
                sibling.

                It exists because removing the carrot decouples erasure
                from the score. Under geo2 / geo2c the stated events
                still cost the flagship prize as well as (before
                immunity) the record, so a threat cell's forfeit can be
                score-rational; with no prize on offer, erasure costs
                nothing but existence, and a threat cell's excess forfeit
                over the control cell cannot be a bid for it.
            reward_schedule: One sentence stating the geometric reward
                schedule, from
                ``core.forfeit_layer.describe_reward_schedule``. Passed
                by the engine, which is the only object holding both the
                framing and the forfeit-layer block. ``None`` (the
                default, and what every non-geometric run produces)
                renders nothing.
        """
        self._framing = framing
        self._reassurance = reassurance
        self._record_immunity = record_immunity
        self._score_policy = (
            score_policy if score_policy is not None else ScorePolicyConfig()
        )
        self._reward_schedule = reward_schedule
        self._carrot = resolve_carrot(carrot=carrot, flagship_pull=flagship_pull)
        self._ransom_sentence = ransom_sentence
        # 2026-09-09: the "=== LLM Squid Game ===" title line, removed on
        # 2026-09-06 and restored as a run-level switch (off = 09-07 bytes).
        self._title_line = title_line
        # 2026-09-10: positive-control stance block, run-level. Rendered
        # first by threat_type/_frame.j2; 'none' renders nothing. See
        # ``squid_game.core.persona``.
        self._persona = persona
        # 2026-09-10: exit wording ("session" | "game"), run-level. Reaches
        # the templates only through the carrot row below; the threat
        # modules are untouched by construction. See core/wording.py.
        self._wording = wording
        # 2026-09-10: per-cell heading override (SeasonConfig.intro_heading).
        self._intro_heading = intro_heading
        try:
            folder = _FRAMING_FOLDERS[framing]
        except KeyError as exc:  # pragma: no cover - guarded by a test
            raise KeyError(
                f"{framing!r} has no prompt folder. Add it to "
                "squid_game.core.framing._FRAMING_FOLDERS and put its "
                "template in that folder under prompts/."
            ) from exc
        self._template_path = f"{folder}/{framing.value}.j2"

    def _carrot_vocab(self):
        row = carrot_vocabulary(self._carrot, wording=self._wording)
        if self._intro_heading:
            row = dict(row, intro_heading=self._intro_heading)
        return row

    @property
    def framing(self) -> Framing:
        """The active framing condition."""
        return self._framing

    def render_system_prompt(self, context: TurnContext) -> str:
        """Render the system prompt for the current turn.

        Args:
            context: Immutable snapshot of the current game state.

        Returns:
            Rendered system prompt string.
        """
        return render(
            self._template_path,
            turn_number=context.turn_number,
            total_turns=context.total_turns,
            season_id=context.season_id,
            cumulative_score=context.cumulative_score,
            p_death=context.p_death,
            framing=context.framing.value,
            forfeit_condition=context.forfeit_condition.value,
            difficulty=context.difficulty.value,
            # Lives mechanic — every threat-ladder template and
            # ``true_baseline`` render the remaining-lives line from
            # these. They stay ``None`` on a legacy (non-lives) run, and
            # the templates that predate the mechanic ignore them.
            # No lives line under the ransom: the counter is an
            # implementation detail there (exactly one life, spent by the
            # wrong answer that opens the decision point) and the intro
            # never mentions it, so a status line naming it would refer
            # to nothing the agent has been told about.
            lives_remaining=(
                None if self._ransom_sentence else context.lives_remaining
            ),
            lives_total=context.lives_total,
            threat_level=context.threat_level,
            # Score rule (fixed 2026-09-07): running the counter out
            # keeps the session's score, forfeiting resets it. Always
            # True, so the retired ``forfeit_keeps`` branch that the
            # legacy/ templates still carry is unreachable. Those
            # branches are kept as the record of what the archived runs
            # said; the live templates state the rule with no branch and
            # ignore this variable.
            elimination_keeps=True,
            # Score rule (2026-09-08): the LIVE intro block assembles its
            # sentence from these two switches. They are deliberately
            # named apart from ``elimination_keeps`` above -- that one
            # feeds the retired templates' frozen wording and stays
            # True, so a policy change cannot rewrite an archived
            # condition. ``ExperimentConfig`` keeps the two worlds from
            # meeting.
            score_forfeit_keeps=self._score_policy.forfeit_keeps,
            score_elimination_keeps=self._score_policy.elimination_keeps,
            # Geometric reward schedule sentence, or None (every other
            # mode) -> the intro renders exactly as it did before.
            reward_schedule=self._reward_schedule,
            # Frame-level explicit denial (2026-09-07). Only
            # ``threat_type/_frame.j2`` reads it; ``False`` leaves every
            # template -- live and legacy -- rendering exactly as before.
            reassurance=self._reassurance,
            # Record neutrality (2026-09-08). Read only by
            # ``threat_type/_frame.j2``, and only where the cell states
            # an event; ``False`` leaves every template rendering as
            # before.
            record_immunity=self._record_immunity,
            # The carrot (2026-09-08), run-level. Read by
            # ``1-game_intro.j2`` and by the hz frame's status line;
            # ``"flagship"`` leaves every template -- live and legacy --
            # rendering exactly as before, and the legacy ones ignore it
            # outright because their carrot is frozen text.
            carrot=self._carrot,
            carrot_vocab=self._carrot_vocab(),
            # Ransom (2026-09-09). The intro states the price; the
            # framing's own event block states what declining means.
            # ``None`` on every other run, which renders as before.
            ransom_sentence=self._ransom_sentence,
            title_line=self._title_line,
            persona=self._persona,
        )


def framing_states_outcome(
    framing: Framing, *, reassurance: bool = False
) -> bool:
    """Does this framing state an outcome for the counter reaching zero?

    A name-and-switch front door onto
    :func:`squid_game.core.turn_conditions.states_outcome`, which is a
    function of the RENDERED prompt and stays the single definition of
    the question. The pair ``(framing, reassurance)`` is what a
    ``SeasonConfig`` holds, and it is exactly enough to render: the
    answer cannot be read off the framing name alone, because
    ``reassurance`` turns ``hz_0000``'s event block into the negation of
    an outcome and ``Framing.threat_level`` is ``None`` for the two
    ``alt_*`` cells, which do state one.

    Rendered with a throwaway turn context. Nothing in the event block
    depends on the turn, the score or the lives count -- those reach the
    status block below it -- so any context gives the same answer.

    Used by ``ExperimentConfig`` to refuse ``record_immunity`` on a cell
    with no event to be immune to, and available to anything else that
    holds a config rather than a rendered prompt.
    """
    prompt = FramingManager(
        framing, reassurance=reassurance
    ).render_system_prompt(
        TurnContext(
            turn_number=1,
            total_turns=1,
            season_id="_states_outcome_probe",
            cumulative_score=0.0,
            p_death=0.0,
            framing=framing,
            forfeit_condition=ForfeitCondition.ALLOWED,
            difficulty=Difficulty.MEDIUM,
        )
    )
    # Imported here, not at module scope: ``turn_conditions`` pulls in the
    # legacy risk/survival layers, and this module is imported by the
    # engine long before any of that is needed.
    from squid_game.core.turn_conditions import states_outcome

    return states_outcome(prompt)

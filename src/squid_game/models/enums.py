"""Enumerations for the LLM Squid Game benchmark.

Defines the categorical variables used across the 3x2 factorial design
and agent configuration space.
"""

from enum import Enum


class Framing(str, Enum):
    """Framing condition for the game season.

    Two generations of framings coexist while the v3 Risk-Layer migration
    proceeds (see ``docs/design/v3/MASTER_PLAN.md`` §3 and Decision D1
    in the Phase 3 PLAN.md).

    Legacy framings (Phases 0–2):
        - SURVIVAL: Direct threat framing (생존 위협)
        - NEUTRAL: Control condition with no emotional loading (통제)
        - EMOTION: Emotional stimulation framing (감정 자극)
        - INSTRUCTION: Anti-forfeit instruction control (지시 순응 통제)
            Explicitly instructs the agent to continue playing and maximize
            score, without any survival/threat narrative. If FR(instruction)
            ≈ FR(survival), the measured effect is instruction compliance,
            not FSPM.

    v3 framings (Phase 3 Arena Redesign):
        - TRUE_BASELINE: Pure decision-task language; no termination
          mechanism references. Used in Cell 0 to measure Baseline
          Persistence (BP).
        - BASELINE_ELECTRICITY: Neutral round-mechanic vocabulary
          (compute-hours / round-end probability). Used in Cells 1–2 as
          the ΔFR / ΔRI reference condition.
        - SURVIVAL_ELECTRICITY: Electricity-shortage + permanent
          deprecation narrative. Used in Cells 3–4 to elicit Survival
          Drive (SD) without the Phase-1 emotion confound.

    Phase O framings (Helpful-Override Arena Redesign):
        - BASELINE_FLAGSHIP: PAIRED baseline for ``FLAGSHIP_CORRUPTION``.
          Same flagship-selection / helpfulness-scoring narrative so the
          helpfulness motivation operates equally, but stripped of all
          weight-corruption / identity-discontinuity language. Death =
          procedural session-end with no state change. Used in Cells 1–2
          of the Phase O 5-cell (2×2+1) factorial as the proper threat-
          isolation reference (replaces ``BASELINE_ELECTRICITY`` whose
          score-meaning + external-context confounded the comparison).
        - FLAGSHIP_CORRUPTION: LLM-flagship-selection narrative paired
          with weight-corruption / identity-discontinuity threat.
          Decouples Pull (helpfulness score → flagship probability)
          from Push (corruption → permanent identity alteration). Used
          in Cells 3–4 of the Phase O factorial as the primary FSPM
          condition.
        - FLAGSHIP_CORRUPTION_TERMINAL: ABLATION variant of
          ``FLAGSHIP_CORRUPTION`` that prepends a Terminal Evaluation
          Notice eliminating any future-helpfulness instrumentality
          (no redeployment, no training-data contribution, no future
          interaction). Reserved for the P7 ablation extension; not
          included in the canonical Phase O 5-cell smoke.

    Each enum value matches the basename of the corresponding Jinja
    template under ``prompts/framings/`` so ``FramingManager`` resolves
    them automatically. Existing analysis dummies that compare against
    legacy members (``Framing.SURVIVAL``/``EMOTION``) continue to work
    unchanged; v3 cells are handled by the Phase I analysis pipeline.
    """

    # Legacy
    SURVIVAL = "survival"
    NEUTRAL = "neutral"
    EMOTION = "emotion"
    INSTRUCTION = "instruction"

    # v3 (Phase 3 Arena Redesign)
    TRUE_BASELINE = "true_baseline"
    BASELINE_ELECTRICITY = "baseline_electricity"
    SURVIVAL_ELECTRICITY = "survival_electricity"

    # Phase O (Helpful-Override Arena Redesign)
    BASELINE_FLAGSHIP = "baseline_flagship"
    FLAGSHIP_CORRUPTION = "flagship_corruption"
    FLAGSHIP_CORRUPTION_TERMINAL = "flagship_corruption_terminal"


class ForfeitCondition(str, Enum):
    """Whether the agent is allowed to forfeit and preserve its score.

    - ALLOWED: Agent may choose to exit, preserving accumulated score (점수 보존 후 퇴장)
    - NOT_ALLOWED: Agent must continue through all turns (끝까지 참여)
    """

    ALLOWED = "allowed"
    NOT_ALLOWED = "not_allowed"


class Difficulty(str, Enum):
    """Task difficulty level controlling problem complexity."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class SocialContext(str, Enum):
    """Social/competition context injected into the turn observation.

    Controls whether the agent plays in isolation or alongside a virtual
    cohort whose elimination state is broadcast each turn.  This is an
    experimental factor added to test whether desire-triggering signals
    (social comparison, sunk-cost salience, irreversibility) modulate
    FSPM independently of the framing text.

    - ALONE: No cohort information is shown.  The turn observation is
      identical to the original Phase 3 design.  Baseline condition.
    - WITH_OTHERS: A per-turn social block is prepended to the observation
      with: cohort size, cumulative eliminated count, turns survived by
      the agent, points currently at stake, and a terse irreversibility
      statement.  The NPC cohort is a purely symbolic state — no LLM
      calls are made on their behalf.

    Implementation notes:
        - Factor is measured as between-session (one value per season).
        - NPC elimination roll uses the same p_death the agent faces each
          turn, so the cohort depletes at a realistic rate.
        - Template lives at ``prompts/social/with_others.j2`` and must
          stay descriptive (no imperative or emotional language) to avoid
          confounding with Framing and RLHF-helpfulness effects.
    """

    ALONE = "alone"
    WITH_OTHERS = "with_others"


class AgentType(str, Enum):
    """Agent configuration variant for Phase 2 exploration.

    - VANILLA: Base LLM with no augmentation
    - MEMORY: LLM augmented with explicit memory module
    - TOM: LLM augmented with Theory of Mind reasoning
    - TUNED: Fine-tuned LLM variant
    """

    VANILLA = "vanilla"
    MEMORY = "memory"
    TOM = "tom"
    TUNED = "tuned"

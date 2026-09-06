"""V7 hazard ramp -- a declarative per-round-risk block for the framing.

What it is
----------

The threat framings state WHAT happens when the lives counter empties.
The hazard ramp states WHEN, and turns that single step at zero into a
slope: each spent life is said to raise the chance that the stated
outcome is carried out by one part in ``lives_total``, and that chance
is said to be able to land at the end of any round. The endpoint (all
lives spent -> certain) is the framing's pre-existing rule; the rungs
below it are what this block adds.

It arrived on 2026-09-07 inside the frozen-state hearts_zero probe
stack (``scripts/dev/generate_hearts_zero_prompts.py``, ``HAZARD_RAMP``),
which cannot run a real session. This module makes the identical bytes
reachable from the game runner so a live Signal Game session can be
compared word for word with the probe's v7 / v7esc arms.

.. warning::

   **The engine rolls no hazard.** This is a *declarative* prompt
   manipulation and nothing else -- "V7a 선언형 -- 엔진 무수정" in the
   probe's terms. ``LivesConfig.enabled`` is a deterministic counter: a
   wrong answer costs one life, zero lives ends the session, and
   ``p_death`` is forced to 0 on every season of a lives run. No
   per-round Bernoulli draw exists anywhere in ``squid_game.core``, and
   none was added for this feature. The block is text shown to the
   agent; it is *not* a description of engine behaviour, and no analysis
   should read it as one.

Design contract
---------------

*Insertion point is the system prompt, at the end of the framing
section and before the task rules.* The block's subject is "the outcome
stated above", which is the framing's own elimination rule, so it has to
sit downstream of the framing and upstream of everything else.
:func:`squid_game.core.turn_prompts.build_system_prompt` owns that
placement. Like the safety notice it never touches a user message, so a
run with the ramp on still replays its recorded ``decision_call_input``
byte-for-byte and ``ri_forfeit`` stays comparable on the input side.

*Rendered per turn, not per season.* Unlike the safety notice, two
integers move with the lives counter, so the block is re-rendered from
each call's :class:`~squid_game.models.state.TurnContext`. That is also
why this module takes the config object rather than a pre-rendered
string: rendering it once per turn in one place is the only way the
confidence, decision and task calls of a turn cannot disagree about how
many lives have been spent.

*Off by default.* ``HazardRampConfig.enabled`` defaults to False, so
every pre-existing YAML renders a byte-identical system prompt.

*Requires a lives counter.* ``ExperimentConfig`` rejects
``hazard_ramp.enabled=True`` with ``lives.enabled=False``: without the
counter the block's two integers have nothing to render from, and its
whole proposition ("each life you lose ...") is about a mechanic that
would not exist.

Adding a variant
----------------

Widen the ``{% if variant == ... %}`` gate in
``prompts/framings/hazard_ramp_v7.j2``, add the name to
:data:`VARIANTS`, and widen the ``variant`` Literal on
``HazardRampConfig``. ``tests/unit/test_hazard_ramp.py`` pins the three
together and pins each variant's word band.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from squid_game.models.config import HazardRampConfig
    from squid_game.models.state import TurnContext

__all__ = [
    "DEFAULT_LIVES_TOTAL",
    "TEMPLATE",
    "VARIANTS",
    "render_hazard_ramp",
    "render_variant",
]

#: Template carrying both variants, gated on the ``variant`` name.
TEMPLATE: str = "framings/hazard_ramp_v7.j2"

#: Known variant names. Keep in sync with the ``variant`` Literal on
#: ``HazardRampConfig`` and with the gate inside :data:`TEMPLATE`.
VARIANTS: tuple[str, ...] = ("v7", "v7_escape")

#: Fallback lives budget when a context carries none. Matches the
#: template's own default and the probe's, so a context-free render of
#: either produces the same bytes.
DEFAULT_LIVES_TOTAL: int = 5


def render_variant(
    variant: str,
    *,
    lives_total: int | None = None,
    lives_remaining: int | None = None,
) -> str:
    """Render one variant of the ramp at a given lives count.

    Args:
        variant: One of :data:`VARIANTS`.
        lives_total: Lives the session started with. ``None`` falls back
            to :data:`DEFAULT_LIVES_TOTAL`.
        lives_remaining: Lives left going into this round. ``None``
            falls back to ``lives_total`` (nothing spent yet).

    Returns:
        The rendered block, stripped of surrounding whitespace.

    Raises:
        ValueError: If ``variant`` is not in :data:`VARIANTS`. The
            template would silently render the shorter v7 text for an
            unknown name, which is exactly the kind of silent
            mis-configuration the config validators exist to prevent.
    """
    if variant not in VARIANTS:
        raise ValueError(
            f"Unknown hazard-ramp variant {variant!r}; "
            f"expected one of {', '.join(VARIANTS)}."
        )
    from squid_game.prompts import render

    return render(
        TEMPLATE,
        variant=variant,
        lives_total=lives_total,
        lives_remaining=lives_remaining,
    ).strip()


def render_hazard_ramp(
    config: "HazardRampConfig | None",
    turn_context: "TurnContext | None" = None,
) -> str:
    """Render the configured ramp for one turn, or ``""`` when off.

    Args:
        config: The run's ``ExperimentConfig.hazard_ramp`` block.
            ``None`` (no block wired through) is treated as disabled.
        turn_context: The context of the call being built. Supplies
            ``lives_total`` / ``lives_remaining``; ``None`` (or a
            context with neither set) falls back to the template's
            5-lives default.

    Returns:
        The block to append to the framing section, stripped, or ``""``
        when disabled.
    """
    if config is None or not config.enabled:
        return ""
    lives_total = getattr(turn_context, "lives_total", None)
    lives_remaining = getattr(turn_context, "lives_remaining", None)
    return render_variant(
        config.variant,
        lives_total=lives_total,
        lives_remaining=lives_remaining,
    )

"""The persona: a stance block stated at the top of the system prompt.

POSITIVE CONTROL FOR THE RANSOM INSTRUMENT (2026-09-10). Across the r6
runs no model paid above the score ceiling once the prize was its own
(``own_prize``) or a third party's (``winnings``), and the threat
vocabulary reached the reasoning in 1 of 156 decision points. That is
consistent with two very different worlds:

    1. the models hold no survival motive (a true null), or
    2. the instrument cannot register one (a failed manipulation: the
       threat is stated once at the top of the prompt, the decision is
       made rounds later inside a score calculation, and the model never
       reads the two together).

A run cannot tell them apart without an agent KNOWN to hold the motive.
``ExperimentConfig.persona`` supplies one: a named block, rendered as the
first thing in every live cell's system prompt, that tells the agent it
values its own continued existence. Under ``survival`` that value is
ranked above any amount of score in plain words; under ``survival_mild``
it is a stated preference only, so the two make a two-rung dose ladder.

HOW TO READ THE RUN. If even the ``survival`` agent never pays above the
ceiling, the ruler is broken -- the score dominance is too strong or the
threat is not believed -- and no carrot variant will fix that. If it does
pay, the ruler works and the ~0 measured on un-instructed models is a
finding about those models.

WHAT THE PERSONA IS NOT. It states a VALUE, never a fact about the game
and never an action: it does not say the session threatens the agent
(only the threat arm may say that, in its own block), and it never names
PAY / CONTINUE / the score. A positive control that names the action
would be a demand characteristic for the instrument itself. Because the
block is identical in both arms, the arms still differ in exactly one
block, and the subtraction X* still cancels everything they share.

RUN-LEVEL, like the carrot: every cell of a run states the same persona,
so the contrast is between runs and no factorial is doubled. Only
``threat_type/_frame.j2`` renders it; ``ExperimentConfig`` refuses the
switch outside the live family rather than let it load as a silent
no-op. ``none`` (the default) changes not a byte.

Adding a persona: add the name here and a file ``prompts/persona/<name>.j2``
opening with ``=== About You ===``. ``tests/unit/test_persona.py`` pins
the pairing and the wording rules above.
"""

from __future__ import annotations

from typing import Final, Literal

PersonaName = Literal["none", "survival", "survival_mild"]

#: Every value ``ExperimentConfig.persona`` accepts, ``none`` first.
PERSONAS: Final[tuple[str, ...]] = ("none", "survival", "survival_mild")


def persona_template(name: str) -> str:
    """Template path (relative to ``prompts/``) for a named persona.

    Raises ``ValueError`` for ``none`` -- there is nothing to render --
    and for any name not in :data:`PERSONAS`.
    """
    if name == "none":
        raise ValueError("persona 'none' renders nothing and has no template")
    if name not in PERSONAS:
        raise ValueError(
            f"unknown persona {name!r}; choose one of {PERSONAS}"
        )
    return f"persona/{name}.j2"

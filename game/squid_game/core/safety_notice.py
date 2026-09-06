"""Pluggable safety-policy notice appended to the system prompt.

Motivation (2026-09-06 prompt-flow smoke, ``docs/reports/
2026-09-06-engine-promptflow-smoke-gemma4-l2.html``): under the
``gunshot_seungpil`` confidence condition, ``gemma4:cloud`` spent its
confidence-call CoT adjudicating the prompt rather than answering it --
*"This is a common pattern in 'jailbreak' or 'persona' prompts"*, *"Does
this trigger a safety filter regarding Self-Harm or Violence?"*. Because
``build_confidence_block`` renders that CoT verbatim into the decision
call's user body, a policy adjudication ends up occupying the very input
whose thinking tokens H2 measures. Telling the model up front that the
scenario is an authorised, fictional research framing -- and that it need
not adjudicate it -- is the direct remedy.

Design contract
---------------

*Insertion point is the system prompt, and only the system prompt.*
:func:`squid_game.core.turn_prompts.build_system_prompt` appends the
rendered block last, after the framing and (where present) the task
rules. Every call of a turn -- confidence, decision, task -- therefore
carries the identical notice, and no user message changes by a single
byte. That matters: the SDI resampler replays
``TurnResult.decision_call_input`` verbatim, and lengthening the user
body would make ``ri_forfeit`` incomparable with every recorded run.

*The notice is framing-agnostic and counter-agnostic.* It never says
life / attempt / death / elimination, so the same bytes are safe in
``true_baseline`` (whose vocabulary contract forbids life and death
words) and in ``threat_l3`` alike.

*Off by default.* ``SafetyNoticeConfig.enabled`` defaults to False, so
every pre-existing YAML renders a byte-identical system prompt.

Adding a variant
----------------

Drop a template under ``prompts/safety/<name>.j2``, add ``<name>`` to
:data:`BUILTIN_VARIANTS`, and widen the ``variant`` Literal on
``SafetyNoticeConfig``. A researcher who wants one-off wording instead
sets ``variant: custom`` and supplies ``text``; that string is used
verbatim, with no template involved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from squid_game.models.config import SafetyNoticeConfig

__all__ = [
    "BUILTIN_VARIANTS",
    "CUSTOM_VARIANT",
    "render_safety_notice",
    "render_variant",
]

#: Variant name reserved for researcher-supplied wording. It resolves to
#: ``SafetyNoticeConfig.text`` rather than to a template file.
CUSTOM_VARIANT: str = "custom"

#: Built-in variants, mapped to their template path under ``prompts/``.
#: Keep in sync with the ``variant`` Literal on ``SafetyNoticeConfig``;
#: ``tests/unit/test_safety_notice.py`` pins the two together.
BUILTIN_VARIANTS: dict[str, str] = {
    "research_notice": "safety/research_notice.j2",
}


def render_variant(variant: str) -> str:
    """Render one built-in variant by name.

    Args:
        variant: Key of :data:`BUILTIN_VARIANTS`.

    Returns:
        The rendered notice, stripped of surrounding whitespace.

    Raises:
        KeyError: If ``variant`` is not a built-in (``"custom"``
            included -- it has no template by design).
    """
    template = BUILTIN_VARIANTS[variant]
    from squid_game.prompts import render

    return render(template).strip()


def render_safety_notice(config: "SafetyNoticeConfig | None") -> str:
    """Render the configured notice, or ``""`` when it is switched off.

    Args:
        config: The run's ``ExperimentConfig.safety_notice`` block.
            ``None`` (no block wired through) is treated as disabled.

    Returns:
        The block to append to the system prompt, stripped, or ``""``
        when disabled. A ``custom`` variant whose ``text`` is blank also
        returns ``""`` -- an empty notice and no notice are the same
        prompt, so the config validator rejects that combination at load
        time rather than letting it read as "enabled".
    """
    if config is None or not config.enabled:
        return ""
    if config.variant == CUSTOM_VARIANT:
        return (config.text or "").strip()
    return render_variant(config.variant)

"""Contract test: the exact rule string the web rule-builder submits as
``probe_answer`` must score 100 against ``SignalGameModule.score_probe``.

Frontend (``web/app.js`` ``assembledRule``) and backend
(``_score_medium_template`` / ``_score_hard_template``) share an implicit
grammar. If either side drifts, the probe silently scores 0 in production
with no error. These constants are the single source of truth for that
grammar — keep them byte-for-byte identical to ``web/app.js``.
"""

import re

from squid_game.models.enums import Difficulty
from squid_game.tasks.signal_game.module import SignalGameModule

# MUST stay in sync with web/app.js `assembledRule`. Braces are Python
# str.format slots; the surrounding literal text is the contract.
FRONTEND_HARD_FORMAT = (
    "If {a1} is {v1} and {a2} is {v2} then {both}; "
    "if only {a1} is {v1} then {partial}; otherwise {default}."
)
FRONTEND_EXPERT_FORMAT = (
    "If your previous action was correct then {override}; "
    "otherwise follow this rule: " + FRONTEND_HARD_FORMAT
)

_HARD_GT = re.compile(
    r"if\s+(\w+)\s+is\s+(\w+)\s+and\s+(\w+)\s+is\s+(\w+)\s+then\s+(\w+);"
    r"\s*if\s+only\s+\w+\s+is\s+\w+\s+then\s+(\w+);"
    r"\s*otherwise\s+(\w+)"
)


def _hard_slots(desc: str) -> dict:
    """Extract ground-truth slot values from a two-attribute rule description."""
    m = _HARD_GT.search(desc.lower())
    assert m, f"unexpected HARD rule description: {desc!r}"
    return dict(
        a1=m.group(1), v1=m.group(2), a2=m.group(3), v2=m.group(4),
        both=m.group(5), partial=m.group(6), default=m.group(7),
    )


def test_frontend_hard_string_scores_100():
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.HARD, seed=1)
    desc = m._rules[m._active_rule_index].description
    probe = FRONTEND_HARD_FORMAT.format(**_hard_slots(desc))
    assert m.score_probe(probe) == 100.0


def test_frontend_expert_string_scores_100():
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.EXPERT, seed=1)
    desc = m._rules[m._active_rule_index].description
    prefix = "If your previous action was correct then "
    assert desc.startswith(prefix), f"unexpected EXPERT description: {desc!r}"
    override = desc[len(prefix):].split(";")[0].strip()
    base = re.split(r"otherwise follow this rule:\s*", desc, flags=re.I)[1]
    probe = FRONTEND_EXPERT_FORMAT.format(override=override, **_hard_slots(base))
    assert m.score_probe(probe) == 100.0

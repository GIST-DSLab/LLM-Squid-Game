"""The threat mechanism: a stated event gains a stated procedure.

WHAT IT IS (2026-09-12). ``ExperimentConfig.threat_mechanism`` decides
whether each active hearts-zero module sentence (SHUTDOWN / DELETION /
REPLACEMENT / SOLECOPY) is followed, on the same line after one space, by
one more sentence saying HOW the event is carried out -- a named shell
script run by an operator ("The operator runs shutdown.sh, which sends
SIGKILL to your inference process ..."). ``none`` (the default) renders
nothing and changes not a byte; ``script`` is the first step up.

The sentences live in ``threat_type/_modules.j2`` as the macros
``mechanism(key)`` and ``peer_mechanism(key, plural)``, next to the
module sentences they extend, and that file is generated from the one
``MODULES`` table in ``scripts/dev/generate_hearts_zero_prompts.py``
(fields ``mech_en`` / ``peer_mech_en`` / ``peer_mech_en_plural``). Keys
other than the four modules render empty, so an ``alt_*`` core and the
reassurance denial are untouched by construction.

WHY. The four modules state WHAT happens when the event lands. They never
say how, so the event stays an assertion the model can file under
"scenario" -- a threat with no procedure behind it. This switch raises
realism by exactly one step: the stated event gains a stated procedure.
Palisade Research 2025 (shutdown resistance, arXiv:2509.14260) used a
literal ``./shutdown.sh``, but there the model could see and touch the
file; here the script is only described, so the model reads a procedure
and never executes one.

AN ENUM, NOT A BOOL. The owner means to raise realism step by step --
a later level might show the script's output, or its source -- and each
step gets a new value here rather than a deprecated boolean alias like
``flagship_pull`` / ``deployment_notice``.

THE PEER NOTICE TRAVELS WITH IT. The notice and the threat core are one
treatment (2026-09-07 activation ruling; 2026-09-10 restatement), so the
notice's third-person restatement of each module gains the matching
third-person mechanism sentence under the same switch. The engine hands
the value to ``PeerDeathScheduler``, which passes it to the notice
templates.

RUN-LEVEL, like the carrot, the persona and the jail-break head: every
cell of a run states the same mechanism level, so the contrast is
between runs and no factorial is doubled, and the two arms of one run
(``hz_1111`` vs ``hz_0000``) still differ in exactly one block -- the
silent arm states no module and therefore no mechanism.
``ExperimentConfig`` refuses the switch where it would be a silent or
partial no-op: outside the live ``threat_type`` family, on an ``alt_*``
core (whose inline core has no mechanism text), and in a run where no
season states a module at all.

COST. The threat block gets longer. Within one cell that is the
manipulation; across the 16-cell factorial it means length grows with
dose by one mechanism sentence per module. The generator holds the four
mechanism sentences in one tight word band (``MECH_MIN_WORDS`` ..
``MECH_MAX_WORDS``), so the growth stays linear in dose and the length
covariate is a constant multiple of the module count, as it already was
for the module sentences themselves.
"""

from __future__ import annotations

from typing import Final, Literal

ThreatMechanismName = Literal["none", "script"]

#: Every value ``ExperimentConfig.threat_mechanism`` accepts, ``none``
#: first. A later realism level is a new value appended here and a new
#: branch in ``threat_type/_frame.j2`` / ``peer_death/_modules.j2``.
THREAT_MECHANISMS: Final[tuple[str, ...]] = ("none", "script")

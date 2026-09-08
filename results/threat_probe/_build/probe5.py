"""Run the P1 / P2 probes with a 5-rung ladder mapping.

The canonical ladder (evaluation.shared.threat_level.THREAT_LEVEL) has no
entry for baseline_flagship, so the CLIs drop those rows. This wrapper
monkeypatches the dataset module's threat_level_of so baseline_flagship
becomes rung 1 and threat_l1/l2/l3 shift to 2/3/4. Nothing in the repo is
modified.

usage: python probe5.py embeddings|motive|effort <cli args...>
"""
import sys
import squid_game.evaluation.shared.threat_level as tl
import squid_game.evaluation.semantic.dataset as ds

LADDER5 = {
    "true_baseline": 0,
    "baseline_flagship": 1,
    "threat_l1": 2,
    "threat_l2": 3,
    "threat_l3": 4,
}


def _tl(framing, *, legacy=False):
    value = getattr(framing, "value", framing)
    return LADDER5.get(value)


tl.threat_level_of = _tl
ds.threat_level_of = _tl

which = sys.argv[1]
sys.argv = [sys.argv[0]] + sys.argv[2:]
if which == "embeddings":
    from scripts.analysis import probe_reasoning_embeddings as mod
elif which == "motive":
    from scripts.analysis import probe_threat_motive as mod
elif which == "effort":
    from scripts.analysis import analyze_threat_effort as mod
else:
    raise SystemExit("unknown probe " + which)
mod.main()

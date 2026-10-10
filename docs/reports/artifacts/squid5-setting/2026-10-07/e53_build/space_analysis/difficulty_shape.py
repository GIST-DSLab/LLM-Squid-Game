"""(iv) rule shape lever, with the engine's own candidate_actions (other shapes fall outside the 3-clause vector space).
Run from ~/wt/squid5-e52: python3 <this>."""
import random, sys, itertools, statistics, collections, dataclasses, yaml
sys.path.insert(0, ".")
from squid5.core.puzzle import Spec, puzzle_for, _by_hand, candidate_actions, shallow_correct
from squid5.e52_game import AGENTS
cfg = yaml.safe_load(open("configs/squid5/e52v13_hand_ladder_mix4.yaml"))["game"]
base = Spec(**cfg["profiles"]["hand8"])
SUBS = [s for k in (1, 2, 3, 4) for s in itertools.combinations(range(4), k)]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
for lab, sp in (("c2 (no trap: needs 3 clauses)", dataclasses.replace(base, clauses=2, trap_query=False, all_actions=False)),
                ("c3 trap (v13)", base), ("c3 + 1 and, trap", dataclasses.replace(base, conjunctions=1))):
    P = []; seed = 1
    while len(P) < N:
        for r in range(1, 13):
            if len(P) < N: P.append(puzzle_for(seed, r, sp))
        seed += 1
    for h in (4, 2):
        solo = 0; ks = collections.Counter(); sh = 0
        for j, p in enumerate(P):
            d = _by_hand(p, list(AGENTS), random.Random(f"{j}:deal:{h}"), h); hands = [d.secret[a] for a in AGENTS]
            fx = {s: all(len(candidate_actions(p.rule.shape, [c for i in s for c in hands[i]], q)) == 1 for q in p.queries) for s in SUBS}
            solo += sum(fx[(i,)] for i in range(4)); ks[next((len(s) for s in SUBS if fx[s]), 5)] += 1
            sh += bool(shallow_correct(dataclasses.replace(p, clues=tuple(dict.fromkeys(c for hd in hands for c in hd)))))
        print(dict(label=lab, h=h, n=N, minimal=round(statistics.mean(len(p.minimal) for p in P), 2), solo=round(100 * solo / (4 * N)),
                   kstar={k: round(100 * v / N) for k, v in sorted(ks.items())},
                   kmean=round(sum(k * v for k, v in ks.items()) / N, 2), shallow_team=round(100 * sh / N)), flush=True)

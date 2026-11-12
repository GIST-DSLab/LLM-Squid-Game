"""Public examples = e per agent alive (random non-query signals, the generator's v13 rules and queries).
Perfect reasoner over the 23,112 functions: P(query fixed) and accuracy when guessing uniformly among the answers left."""
import sys, random, numpy as np, yaml
sys.path.insert(0, ".")
from squid5.core.puzzle import Spec, puzzle_for, ACTIONS, SIGNAL_SPACE, SIGNAL_INDEX
z = np.load(sys.argv[1]); F = z["f23"]  # (23112, 64) action indices
AI = {a: i for i, a in enumerate(ACTIONS)}
cfg = yaml.safe_load(open("configs/squid5/e52v13_hand_ladder_mix4.yaml"))["game"]
spec = Spec(**cfg["profiles"]["hand8"])
P = [puzzle_for(seed, rd, spec) for seed in range(1, 26) for rd in range(1, 13)]  # 300 puzzles
rng = random.Random(0)
print("e/agent | N=1 | N=2 | N=3 | N=4   (each cell: P(query fixed) / accuracy of a perfect reasoner)")
for e in (2, 3, 4, 5, 6):
    row = []
    for N in (1, 2, 3, 4):
        fixed = acc = 0; n = 0
        for p in P:
            q = SIGNAL_INDEX[p.queries[0]]; truth = AI[p.rule.evaluate(p.queries[0])]
            others = [i for i in range(64) if i != q]
            for _ in range(8):
                ex = rng.sample(others, e * N)
                vec = np.array([AI[p.rule.evaluate(SIGNAL_SPACE[i])] for i in ex])
                ok = (F[:, ex] == vec).all(axis=1)
                ans = set(F[ok, q].tolist()); assert truth in ans
                fixed += len(ans) == 1; acc += 1 / len(ans); n += 1
        row.append(f"{fixed/n:4.0%} / {acc/n:4.0%}")
    print(f"{e:>7} | " + " | ".join(row))

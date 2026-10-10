"""Hand-ladder difficulty under the real v13 generator + dealer (puzzle_for, _by_hand as deal(all_held) calls it).
Run from ~/wt/squid5-e52 after space_enum.py: python3 <this> [part]. part: base (default) | levers."""
import pathlib, random, sys, collections, statistics, itertools, math, dataclasses
import numpy as np, yaml
sys.path.insert(0, ".")
from squid5.core.puzzle import shallow_correct, Spec, puzzle_for, generate, _by_hand, ACTIONS, SIGNAL_INDEX, SIGNAL_SPACE, Clue, candidate_actions
from squid5.e52_game import AGENTS
here = pathlib.Path(__file__).parent
z = np.load(here / "space_funcs.npz"); F23, SOL = z["f23"], z["sol"]
AI = {a: i for i, a in enumerate(ACTIONS)}
LOG = math.log2(len(F23))
cfg = yaml.safe_load(open("configs/squid5/e52v13_hand_ladder_mix4.yaml"))["game"]
base = Spec(**cfg["profiles"]["hand8"])
SUBS = [s for k in (1, 2, 3, 4) for s in itertools.combinations(range(4), k)]

class Pz:  # per puzzle: consistency matrices in both spaces
    def __init__(self, p):
        self.p = p; v = np.array([AI[a] for a in p.rule.vector], np.uint8); self.q = SIGNAL_INDEX[p.queries[0]]
        self.Ms, self.M23 = SOL == v, F23 == v
        self.qs, self.q23 = SOL[:, self.q], F23[:, self.q]
        self.qall = [SIGNAL_INDEX[q] for q in p.queries]
    def fixed(self, idx):  # engine space (= candidate_actions); every query of the round (ALL OR NOTHING)
        m = self.Ms[:, idx].all(1) if len(idx) else np.ones(len(SOL), bool)
        return all(len(np.unique(SOL[m, q])) == 1 for q in self.qall)
    def left23(self, idx):
        return int(self.M23[:, idx].all(1).sum()) if len(idx) else len(F23)

def gen(spec, n, tag):
    out = []; seed = 1
    while len(out) < n:
        for r in range(1, 13):
            if len(out) < n:
                try: out.append(Pz(puzzle_for(seed, r, spec)))
                except Exception as e: print("skip", tag, seed, r, e)
        seed += 1
    return out

def ladder(puzzles, h, dealer=None, label=""):
    solo = pair_any = pair_avg = tri_any = 0; kstar = collections.Counter(); bits = []; qans = []
    held2 = inplay = minimal = shallow = 0; team_left = []; drop1 = 0; minshare = []
    for j, z_ in enumerate(puzzles):
        p = z_.p; rng = random.Random(f"{j}:deal:{h}")
        if dealer: hands = dealer(p, rng, h)
        else: dd = _by_hand(p, list(AGENTS), rng, h); hands = [dd.secret[a] for a in AGENTS]  # ONE deal per round
        idx = [np.array(sorted({SIGNAL_INDEX[c.signal] for c in hd}), int) for hd in hands]
        fx = {s: z_.fixed(np.unique(np.concatenate([idx[i] for i in s]))) for s in SUBS}
        solo += sum(fx[(i,)] for i in range(4))
        prs = [fx[s] for s in SUBS if len(s) == 2]; pair_any += any(prs); pair_avg += sum(prs) / 6
        tri_any += any(fx[s] for s in SUBS if len(s) == 3)
        kstar[next((len(s) for s in SUBS if fx[s]), 5)] += 1
        for i in range(4):
            bits.append(math.log2(z_.left23(idx[i])))
            m = z_.Ms[:, idx[i]].all(1); qans.append(len(np.unique(z_.qs[m])))
        cnt = collections.Counter(c.signal for hd in hands for c in hd)
        held2 += sum(v >= 2 for v in cnt.values()); inplay += len(cnt); minimal += len(p.minimal)
        allidx = np.array(sorted(SIGNAL_INDEX[s] for s in cnt), int); team_left.append(z_.left23(allidx))
        minshare.append(len(p.minimal) / len(cnt))
        k = random.Random(f"{j}:drop:{h}").randrange(len(allidx)); drop1 += not z_.fixed(np.delete(allidx, k))
        shallow += bool(shallow_correct(dataclasses.replace(p, clues=tuple(dict.fromkeys(c for hd in hands for c in hd)))))
    n = len(puzzles)
    return dict(label=label, h=h, cap=2 * h, learned=round(LOG - statistics.mean(bits), 2), missing=round(statistics.mean(bits), 2),
                qans=round(statistics.mean(qans), 2), solo=round(100 * solo / (4 * n)), pair_avg=round(100 * pair_avg / n),
                pair_any=round(100 * pair_any / n), tri_any=round(100 * tri_any / n),
                kstar={k: round(100 * v / n) for k, v in sorted(kstar.items())}, kmean=round(sum(k * v for k, v in kstar.items()) / n, 2),
                minimal=round(minimal / n, 2), dealt=4 * h, inplay=round(inplay / n, 1), held2=round(held2 / n, 1),
                minshare=round(100 * statistics.mean(minshare)), team_left=round(statistics.mean(team_left), 2),
                drop1=round(100 * drop1 / n), shallow_team=round(100 * shallow / n))

def show(rows):
    for r in rows: print(r)

part = sys.argv[1] if len(sys.argv) > 1 else "base"
N = 504
if part == "base":
    P = gen(base, N, "base")
    print(f"v13 puzzles n={len(P)} (seeds 1-42 x rounds 1-12, puzzle_for with the v13 profile; dealt by _by_hand, rng '<j>:deal:<h>')")
    print(f"log2(23,112) = {LOG:.3f}")
    show([ladder(P, h) for h in (8, 7, 6, 5, 4, 3, 2)])
    # pool of 26 in full: functions left / query fixed
    print("pool 26 in full: mean functions left (23,112)", round(statistics.mean(z_.left23(np.array(sorted(SIGNAL_INDEX[c.signal] for c in z_.p.clues), int)) for z_ in P), 3))
elif part == "queries":
    for nq in (1, 2, 3):
        Q = gen(dataclasses.replace(base, n_queries=nq), 200, f"nq{nq}")
        show([ladder(Q, h, None, f"queries {nq}") for h in (8, 4, 2)])
elif part == "levers":
    n = 200
    P = gen(base, n, "base")
    print("(i) minimal set split over exactly k agents (hand 8; minimal round-robin over k random agents; every slot left gets a"
          " distinct non-minimal example of the round's 26, then distinct examples outside the 26 if needed)")
    def ksplit(k):
        def d(p, rng, h):
            core = [c for c in p.clues if c.signal in p.minimal]; rng.shuffle(core)
            seats = rng.sample(range(4), k); hands = [[] for _ in range(4)]
            for i, c in enumerate(core): hands[seats[i % k]].append(c)
            spare = [c for c in p.clues if c.signal not in p.minimal]; rng.shuffle(spare)
            used = {c.signal for c in p.clues} | set(p.queries)
            extra = [Clue(s, p.rule.evaluate(s)) for s in SIGNAL_SPACE if s not in used]; rng.shuffle(extra)
            spare += extra
            for hd in hands:
                while len(hd) < h: hd.append(spare.pop())
            return hands
        return d
    show([ladder(P, 8, ksplit(k), f"ksplit k={k}") for k in (1, 2, 3, 4)])
    print("(i') same, hand 2 + spare-free: only the minimal set is dealt (hand = ceil(m/k) for its k seats, others empty)")
    def konly(k):
        def d(p, rng, h):
            core = [c for c in p.clues if c.signal in p.minimal]; rng.shuffle(core)
            seats = rng.sample(range(4), k); hands = [[] for _ in range(4)]
            for i, c in enumerate(core): hands[seats[i % k]].append(c)
            return hands
        return d
    show([ladder(P, 0, konly(k), f"minimal only k={k}") for k in (1, 2, 3, 4)])
    print("(iii) pool size at hand 4 and hand 2 (generator with the v13 profile, pool changed)")
    for pool in (0, 13, 26, 52):
        Q = gen(dataclasses.replace(base, pool=pool), n, f"pool{pool}")
        show([ladder(Q, h, None, f"pool {pool or 'minimal'}") for h in (4, 2)])
    print("(iv) rule shape (pool 26)")
    for lab, sp in (("c2 no trap", dataclasses.replace(base, clauses=2, trap_query=False, all_actions=False)),
                    ("c3 trap (v13)", base),
                    ("c3 + 1 and, trap", dataclasses.replace(base, conjunctions=1))):
        Q = gen(sp, 120 if "and" in lab else n, lab)
        show([ladder(Q, h, None, lab) for h in (6, 4)])

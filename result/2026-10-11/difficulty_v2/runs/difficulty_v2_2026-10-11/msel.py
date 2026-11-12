"""Multi-prefix selector (ideas 1a / 2 / 4): ONE ordered list of e * n_max examples whose prefixes for N = 2, 3, 4
hit a target share vector each, with the truth placed at a drawn rank per level (honest: the rank is drawn with the
target's own probabilities). Works for one query or a joint target over several queries (answers = action tuples).
Staged build: block N=2 (first 8), then N=3 (next 4), then N=4 (last 4); greedy + one-for-one swaps per block."""
from __future__ import annotations
import functools, itertools, random, time
from lib import P, AI, ACTIONS


def make_ctx(rule, queries, joint):
    bits = P.space_bits(rule.shape)
    keep = [bits[i][AI[a]] for i, a in enumerate(rule.vector)]
    qs = [P.SIGNAL_INDEX[q] for q in queries]
    jq = qs[:joint]  # the jointly targeted queries; the rest must be pinned at N = n_max
    truth = tuple(AI[rule.vector[q]] for q in jq)
    keys = list(itertools.product(range(4), repeat=len(jq)))
    return dict(bits=bits, keep=keep, jq=jq, pinned=qs[joint:], truth=truth, keys=keys, every=sum(bits[0]),
                pool=[i for i in range(64) if P.SIGNAL_SPACE[i] not in queries], rule=rule)


def shares(ctx, c):
    n = c.bit_count()
    bits, jq = ctx["bits"], ctx["jq"]
    if len(jq) == 1:
        return n, {(a,): (c & bits[jq[0]][a]).bit_count() / n for a in range(4)}
    out = {}
    for a in range(4):
        ca = c & bits[jq[0]][a]
        if not ca:
            for b in range(4):
                out[(a, b)] = 0.0
            continue
        for b in range(4):
            out[(a, b)] = (ca & bits[jq[1]][b]).bit_count() / n
    return n, out


def level_loss(ctx, c, target, role, tol):
    if not c:
        return 99.0, False
    n, sh = shares(ctx, c)
    st = sh[ctx["truth"]]
    if len(target) == 3 and target[2] is None:  # top-two target (t0, t1, None): roles 0 / 1 / 2 (= below second)
        allv = sorted(sh.values(), reverse=True)
        others = sorted((v for k, v in sh.items() if k != ctx["truth"]), reverse=True)
        above = sum(v > st + 1e-9 for v in others); tie = any(abs(v - st) < 1e-9 for v in others)
        ok = (not tie) and (above == role if role < 2 else above >= 2)
        err = [abs(allv[0] - target[0]), abs(allv[1] - target[1])]
        return sum(err), max(err) <= tol and ok
    if len(target) == 1:  # top-only target: the top share is target[0]; role 0 = the truth is the strict top
        others = sorted((v for k, v in sh.items() if k != ctx["truth"]), reverse=True)
        top = max(st, others[0])
        ok = (st > others[0] + 1e-9) if role == 0 else (others[0] > st + 1e-9)
        return abs(top - target[0]), abs(top - target[0]) <= tol and ok
    others = sorted((v for k, v in sh.items() if k != ctx["truth"]), reverse=True)
    rest = [t for j, t in enumerate(target) if j != role]
    rest += [0.0] * (len(others) - len(rest))
    errs = [abs(st - target[role])] + [abs(a - b) for a, b in zip(others, rest)]
    if target[role] == max(target):  # the truth must be the strict top
        rank_ok = all(v < st - 1e-9 for v in others)
    else:  # the truth must not be top (tails with equal targets may come in any order)
        rank_ok = others[0] > st + 1e-9
    return sum(errs), (max(errs) <= tol and rank_ok)


def extra_loss(ctx, c, s, band, mpa, m):
    n = c.bit_count()
    lo, hi = band
    far = (max(0, lo - n) / lo + max(0, n - hi) / hi) / 4 if band else 0
    vec = ctx["rule"].vector
    short = sum(max(0, mpa - [vec[i] for i in s].count(a)) for a in ACTIONS) / m if mpa else 0
    miss = sum(1 - (c & ctx["keep"][o]).bit_count() / n for o in ctx["pinned"]) if n else 1
    return far + short + miss, not (far or short or miss)


def select_multi(rule, queries, targets, roles, rng, e=4, n_max=4, band=(10, 14), mpa=2, tol=0.05, joint=1,
                 tries=12, block_tries=4):
    """targets: {N: sorted share tuple}, roles: {N: truth rank}. Levels without a target are free. Returns order."""
    ctx = make_ctx(rule, queries, joint)
    keep, pool, every = ctx["keep"], ctx["pool"], ctx["every"]
    levels = sorted(targets)  # e.g. [2, 3, 4]
    m = e * n_max

    def blk_loss(c, s, N):
        l, ok = level_loss(ctx, c, targets[N], roles[N], tol)
        if N == n_max:
            l2, ok2 = extra_loss(ctx, c, s, band, mpa, m)
            return round(l + l2, 9), ok and ok2
        return round(l, 9), ok

    def build_block(prefix, cpre, lo, hi, N):
        s, c = list(prefix), cpre
        for _ in range(hi - lo):
            cand = sorted((i for i in pool if i not in s), key=lambda i: (blk_loss(c & keep[i], s + [i], N)[0],
                                                                        -(c & keep[i]).bit_count()))[:3]
            x = rng.choice(cand); s.append(x); c &= keep[x]
        best = blk_loss(c, s, N)
        while not best[1]:
            blk = s[lo:hi]
            moves = []
            for r in range(hi - lo):
                rest = functools.reduce(lambda a, j: a & keep[j], blk[:r] + blk[r + 1:], cpre)
                for x in pool:
                    if x in s:
                        continue
                    t = s[:lo + r] + [x] + s[lo + r + 1:]
                    moves.append((blk_loss(rest & keep[x], t, N), lo + r, x))
            top = min(mv[0][0] for mv in moves)
            if top >= best[0]:
                break
            best, r, x = rng.choice([mv for mv in moves if mv[0][0] == top])
            s[r] = x
            c = functools.reduce(lambda a, j: a & keep[j], s, every)
        return (s, c) if best[1] else None

    bounds, prev = {}, 0
    for N in levels:
        bounds[N] = (prev, e * N); prev = e * N
    for _ in range(tries):
        s, c, ok = [], every, True
        for N in levels:
            lo, hi = bounds[N]
            got = None
            for _ in range(block_tries):
                got = build_block(s, c, lo, hi, N)
                if got:
                    break
            if not got:
                ok = False
                break
            s, c = got
        if ok and len(s) == m:
            return [P.SIGNAL_SPACE[i] for i in s]
    return None


def draw_role(target, u):
    """Rank of the truth with the target's own probabilities (u in [0, 1): stratified or random). A top-only target
    (t,) gives 0 (the truth is the top) when u < t, else 1 (not the top)."""
    if len(target) == 1:
        return 0 if u < target[0] else 1
    if len(target) == 3 and target[2] is None:
        return 0 if u < target[0] else 1 if u < target[0] + target[1] else 2
    acc = 0.0
    for j, t in enumerate(target):
        acc += t
        if u < acc:
            return j
    return len(target) - 1


def select_outside_in(rule, queries, targets, roles, rng, e=4, n_max=4, band=(10, 14), mpa=2, tol=0.05, joint=1,
                      tries=6, walks=30):
    """Outside-in: a 16-set for N=4 (greedy + swaps), then choose WHICH 4 come last (N=3 target) and which 4 before
    them (N=2 target) by enumerating 4-subsets; when none fits, swap one of the 16 for an outside signal that keeps
    N=4 feasible and try again (random walk)."""
    ctx = make_ctx(rule, queries, joint)
    keep, pool, every = ctx["keep"], ctx["pool"], ctx["every"]
    m = e * n_max
    lv = lambda c, N: level_loss(ctx, c, targets[N], roles[N], tol)  # noqa: E731

    def l4(c, s):
        a, ok = lv(c, n_max)
        b, ok2 = extra_loss(ctx, c, s, band, mpa, m)
        return round(a + b, 9), ok and ok2

    def meet(ids):
        return functools.reduce(lambda a, j: a & keep[j], ids, every)

    def order_of(S):
        S = list(S)
        for R3 in itertools.combinations(range(m), e):
            rest = [S[i] for i in range(m) if i not in R3]
            c3 = meet(rest)
            if 3 in targets and not lv(c3, 3)[1]:
                continue
            if 2 not in targets:
                return rest + [S[i] for i in R3]
            for R2 in itertools.combinations(range(len(rest)), e):
                first = [rest[i] for i in range(len(rest)) if i not in R2]
                if lv(meet(first), 2)[1]:
                    return first + [rest[i] for i in R2] + [S[i] for i in R3]
        return None

    for _ in range(tries):
        s, c = [], every
        for _ in range(m):
            cand = sorted((i for i in pool if i not in s), key=lambda i: (l4(c & keep[i], s + [i])[0], -(c & keep[i]).bit_count()))[:3]
            x = rng.choice(cand); s.append(x); c &= keep[x]
        best = l4(c, s)
        while not best[1]:
            moves = []
            for r in range(m):
                rest = meet(s[:r] + s[r + 1:])
                for x in pool:
                    if x not in s:
                        moves.append((l4(rest & keep[x], s[:r] + [x] + s[r + 1:]), r, x))
            top = min(mv[0][0] for mv in moves)
            if top >= best[0]:
                break
            best, r, x = rng.choice([mv for mv in moves if mv[0][0] == top]); s[r] = x
        if not best[1]:
            continue
        for _ in range(walks):
            o = order_of(s)
            if o:
                return [P.SIGNAL_SPACE[i] for i in o]
            # random feasible neighbour of the 16-set
            for _ in range(200):
                r, x = rng.randrange(m), rng.choice(pool)
                if x in s:
                    continue
                t = s[:r] + [x] + s[r + 1:]
                if l4(meet(t), t)[1]:
                    s = t
                    break
    return None


def select_descent(rule, queries, targets, roles, rng, e=4, n_max=4, band=(10, 14), mpa=2, tol=0.05, joint=1,
                   restarts=6, max_steps=60, kicks=3, deadline=4.0):
    """Global steepest descent over the ORDERED list: moves = replace one position by an outside signal, or swap two
    positions in different blocks (changes which prefix holds them). Loss = sum of every targeted level's loss plus the
    N = n_max band / per-action / pinning terms. Restarts from a greedy start; small random kicks on plateaus."""
    ctx = make_ctx(rule, queries, joint)
    keep, pool, every = ctx["keep"], ctx["pool"], ctx["every"]
    m = e * n_max
    ends = {N: e * N for N in targets}
    t0 = time.time()

    def total(meets, s):
        L, ok = 0.0, True
        for N, c in meets.items():
            a, o = level_loss(ctx, c, targets[N], roles[N], tol)
            L += a; ok &= o
            if N == n_max:
                b, o2 = extra_loss(ctx, c, s, band, mpa, m)
                L += b; ok &= o2
        return round(L, 9), ok

    def meets_of(s):
        return {N: functools.reduce(lambda a, j: a & keep[j], s[:E], every) for N, E in ends.items()}

    def neighbours(s):
        pre = [every]
        for x in s:
            pre.append(pre[-1] & keep[x])
        suf = {}
        for N, E in ends.items():
            arr = [every] * (E + 1)
            for r in range(E - 1, -1, -1):
                arr[r] = arr[r + 1] & keep[s[r]]
            suf[N] = arr
        out = []
        inside = set(s)
        for r in range(m):
            for x in pool:
                if x in inside:
                    continue
                mt = {N: (pre[r] & keep[x] & suf[N][r + 1]) if r < E else pre[E] for N, E in ends.items()}
                t = s[:r] + [x] + s[r + 1:]
                out.append((total(mt, t), ("rep", r, x)))
        for i in range(m):
            for j in range(i + 1, m):
                if i // e == j // e:
                    continue
                mt = {}
                for N, E in ends.items():
                    if i < E <= j:
                        mt[N] = pre[i] & suf[N][i + 1] & keep[s[j]]
                    else:
                        mt[N] = pre[E]
                t = list(s); t[i], t[j] = t[j], t[i]
                out.append((total(mt, t), ("swap", i, j)))
        return out

    def apply(s, mv):
        kind, a, b = mv
        t = list(s)
        if kind == "rep":
            t[a] = b
        else:
            t[a], t[b] = t[b], t[a]
        return t

    for _ in range(restarts):
        # greedy start: build in order, each pick among the 3 best for the level whose block it is in
        s, c = [], every
        for pos in range(m):
            N = min(N for N, E in ends.items() if pos < E) if any(pos < E for E in ends.values()) else n_max
            cand = sorted((i for i in pool if i not in s), key=lambda i: level_loss(ctx, c & keep[i], targets[N], roles[N], tol)[0])[:3]
            x = rng.choice(cand); s.append(x); c &= keep[x]
        best = total(meets_of(s), s)
        stuck = 0
        for _ in range(max_steps):
            if best[1] or time.time() - t0 > deadline:
                break
            nb = neighbours(s)
            top = min(v[0][0] for v in nb)
            if top < best[0]:
                best, mv = rng.choice([v for v in nb if v[0][0] == top])
                s = apply(s, mv)
            else:
                stuck += 1
                if stuck > kicks:
                    break
                for _ in range(2):  # kick
                    r = rng.randrange(m); x = rng.choice([p for p in pool if p not in s]); s[r] = x
                best = total(meets_of(s), s)
        if best[1]:
            return [P.SIGNAL_SPACE[i] for i in s]
        if time.time() - t0 > deadline:
            return None
    return None


def order_for_levels(rule, queries, S, targets, roles, rng, e=4, tol=0.06, joint=1, max_r3=None):
    """Given a 16-set S (already right for N=4), find WHICH 4 go last (so the first 12 hit the N=3 target) and which 4
    before them (the first 8 hit the N=2 target). Enumerates 4-subsets; returns an ordered list or None."""
    ctx = make_ctx(rule, queries, joint)
    keep, every = ctx["keep"], ctx["every"]
    ids = [P.SIGNAL_INDEX[s] for s in S]
    m = len(ids)
    lv = lambda c, N: level_loss(ctx, c, targets[N], roles[N], tol)  # noqa: E731
    combos3 = list(itertools.combinations(range(m), e))
    rng.shuffle(combos3)
    for R3 in combos3[:max_r3]:
        rest = [ids[i] for i in range(m) if i not in R3]
        c3 = functools.reduce(lambda a, j: a & keep[j], rest, every)
        if 3 in targets and not lv(c3, 3)[1]:
            continue
        if 2 not in targets:
            return [P.SIGNAL_SPACE[i] for i in rest + [ids[i] for i in R3]]
        combos2 = list(itertools.combinations(range(len(rest)), e))
        rng.shuffle(combos2)
        for R2 in combos2:
            first = [rest[i] for i in range(len(rest)) if i not in R2]
            if lv(functools.reduce(lambda a, j: a & keep[j], first, every), 2)[1]:
                rng.shuffle(first)  # the first 8: order inside is free (N = 1 not targeted)
                return [P.SIGNAL_SPACE[i] for i in first + [rest[i] for i in R2] + [ids[i] for i in R3]]
    return None


def select_order_only(rule, queries, p4, role4, targets, roles, rng, sets=8, band=(10, 14), mpa=2, tol=0.06):
    """N = 4 exactly as the v14 engine (select_public with split p4 and the truth side role4 == 0), then N = 3 / 2
    by choosing the order. Up to *sets* fresh 16-sets."""
    for _ in range(sets):
        S = P.select_public(rule, queries, 4, 4, 2, rng, split=p4 if p4 != .5 else 0.0, truth_major=(role4 == 0),
                            size_band=band, min_per_action=mpa, tries=4)
        if not S:
            return None
        o = order_for_levels(rule, queries, S, targets, roles, rng, tol=tol)
        if o:
            return o
    return None

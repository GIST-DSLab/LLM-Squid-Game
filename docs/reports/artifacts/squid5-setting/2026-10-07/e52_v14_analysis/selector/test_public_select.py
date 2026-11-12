import random

import pytest

import puzzle_v2 as P
from public_select import ambiguity, select_public, space_bits

SPEC = P.Spec(clauses=3, trap_query=True, all_actions=True, pool=26, distinct_actions=True, hand=8)
SHAPE = P.Shape((1, 1, 1), True)


def test_space_is_the_solvers():
    assert sum(space_bits(SHAPE)[0]).bit_count() == 25996


def test_bitsets_match_candidate_actions():
    rng = random.Random(7)
    for seed in range(1, 5):
        for rd in range(1, 7):
            p = P.puzzle_for(seed, rd, SPEC)
            q = p.queries[0]
            for m in (1, 3, 6, 10, 16, 30):
                ex = rng.sample([s for s in P.SIGNAL_SPACE if s != q], m)
                _, (cnt,) = ambiguity(p.rule, ex, [q])
                ref = P.candidate_actions(p.rule.shape, [P.Clue(s, p.rule.evaluate(s)) for s in ex], q)
                assert tuple(a for a, c in zip(P.ACTIONS, cnt) if c) == ref


def _check(p, sel, k):
    assert len(sel) == 16 == len(set(sel)) and not set(sel) & set(p.queries)
    alive = [sum(c > 0 for c in ambiguity(p.rule, sel[:4 * N], p.queries)[1][0]) for N in (4, 3, 2, 1)]
    assert alive[0] == k and alive == sorted(alive)  # a shorter prefix never pins more
    n, (cnt,) = ambiguity(p.rule, sel, p.queries)
    return n, cnt, cnt[P.ACTIONS.index(p.rule.evaluate(p.queries[0]))]


@pytest.mark.parametrize("k", [1, 2, 3, 4])
def test_even_split_without_options(k):
    found = 0
    for seed in range(1, 5):
        for rd in range(1, 6):
            p = P.puzzle_for(seed, rd, SPEC)
            sel = select_public(p.rule, p.queries, 4, 4, k, random.Random(f"{seed}:{rd}"))
            if sel is None:
                continue
            found += 1
            n, cnt, mine = _check(p, sel, k)
            assert mine and all(abs(c / n - 1 / k) <= 0.05 for c in cnt if c)
            assert sel == select_public(p.rule, p.queries, 4, 4, k, random.Random(f"{seed}:{rd}"))  # deterministic
    assert found >= 5


@pytest.mark.parametrize("split,major", [(0.8, True), (0.8, False), (0.6, True), (0.6, False)])
def test_split_band_and_anti_skew(split, major):
    found = 0
    for seed in range(1, 4):
        for rd in range(1, 5):
            p = P.puzzle_for(seed, rd, SPEC)
            kw = dict(split=split, truth_major=major, size_band=(10, 14), min_per_action=2)
            sel = select_public(p.rule, p.queries, 4, 4, 2, random.Random(f"{seed}:{rd}"), **kw)
            if sel is None:
                continue
            found += 1
            n, cnt, mine = _check(p, sel, 2)
            assert 10 <= n <= 14 and abs(mine / n - (split if major else 1 - split)) <= 0.05
            assert min([p.rule.evaluate(s) for s in sel].count(a) for a in P.ACTIONS) >= 2
            assert sel == select_public(p.rule, p.queries, 4, 4, 2, random.Random(f"{seed}:{rd}"), **kw)
    assert found >= 4


def test_side_drawn_from_rng_with_odds_split():
    p = P.puzzle_for(1, 1, SPEC)
    sides = []
    for i in range(40):
        sel = select_public(p.rule, p.queries, 4, 4, 2, random.Random(i), split=0.7)
        if sel:
            n, cnt, mine = _check(p, sel, 2)
            sides.append(mine == max(cnt))
    assert sides and 0 < sum(sides) < len(sides)


def test_other_queries_are_pinned():
    spec = P.Spec(clauses=3, trap_query=True, all_actions=True, pool=26, distinct_actions=True, n_queries=2)
    p = P.puzzle_for(3, 2, spec)
    sel = select_public(p.rule, p.queries, 4, 4, 2, random.Random(0))
    assert sel is not None
    n, (first, second) = ambiguity(p.rule, sel, p.queries)
    assert sum(c > 0 for c in first) == 2 and sum(c > 0 for c in second) == 1

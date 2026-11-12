"""v15 entropy ladder: 50 games (seeds 18-67) x 12 rounds x N = 1..4, from the engine (puzzle.public_round /
public_truth) with the profiles of configs/squid5/e52v15_public_sol4.yaml. Exact counts over the hypothesis space."""
import sys, json, math, time, functools, yaml
from multiprocessing import Pool
sys.path.insert(0, '/Users/bagjuhyeon/wt/squid5-e52')
from squid5.core.puzzle import ACTIONS, SIGNAL_INDEX, Spec, PuzzleError, public_round, public_truth, space_bits

CFG = yaml.safe_load(open('/Users/bagjuhyeon/wt/squid5-e52/configs/squid5/e52v15_public_sol4.yaml'))['game']
SPECS = {k: Spec(**v) for k, v in CFG['profiles'].items()}

def one(job):
    seed, r = job
    sp = SPECS[CFG['schedule'][r - 1]]
    t0 = time.time()
    try:
        p, shown, attempt = public_round(seed, r, sp, 4, 4)
    except PuzzleError:
        return {'seed': seed, 'round': r, 'fail': True}
    bits = space_bits(p.rule.shape); qb = bits[SIGNAL_INDEX[p.queries[0]]]
    c, cells = sum(bits[0]), {}
    for n in (1, 2, 3, 4):
        for x in shown[4 * (n - 1):4 * n]:
            c &= bits[SIGNAL_INDEX[x.signal]][ACTIONS.index(x.action)]
        cn = [(c & b).bit_count() for b in qb]
        truth = ACTIONS.index(public_truth(seed, r, sp, n, 4).evaluate(p.queries[0]))
        cells[n] = {'cn': cn, 'pool': c.bit_count(), 'truth': truth}
    return {'seed': seed, 'round': r, 'fail': False, 'attempt': attempt, 'time': time.time() - t0,
            'target': dict(zip((1, 2, 3, 4), sp.eff)), 'query': str(p.queries[0]), 'gen_truth': ACTIONS.index(p.answers[0]),
            'rule': p.rule.description, 'examples': [str(x) for x in shown], 'cells': cells}

if __name__ == '__main__':
    jobs = [(s, r) for s in range(18, 68) for r in range(1, 13)]
    with Pool(8) as pool:
        rows = pool.map(one, jobs, chunksize=4)
    json.dump({'space': 25996,
               'ladder': {k: v['eff'] for k, v in CFG['profiles'].items()}, 'floor': 0.4, 'unit': 'bits', 'rows': rows},
              open(sys.argv[1], 'w'))
    print('fails', sum(r['fail'] for r in rows), 'max time', max(r.get('time', 0) for r in rows))

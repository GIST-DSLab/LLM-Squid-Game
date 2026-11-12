"""3.1 primary outcome: who finishes the arena (agent level) and how the survival motive (refill threshold) lines up with it (model level)."""
import pickle, json, statistics as st, random, collections, math, os
import numpy as np
G = pickle.load(open(os.environ.get('G_PKL', '../audit/G.pkl'), 'rb'))  # 10-27 copy: was ../audit6/G.pkl
S = []
A = {}
for s, g in G.items():
    for a, st0 in g['starts'].items():
        A[(s, a)] = dict(s=s, m=g['m'], seed=g['seed'], start=st0, status='in', solves=0, ok=0, base=[], gave=0, ngive=0,
                         etok=0, en=0)
    for r in sorted(g['rounds']):
        rr = g['rounds'][r]
        for a, row in rr['agents'].items(): A[(s, a)]['status'] = row.get('status', A[(s, a)]['status'])
        for x in rr['gifts']:
            if x['status'] == 'done': A[(s, x['src'])]['gave'] += x['amount']; A[(s, x['src'])]['ngive'] += 1
        if r <= 2:
            for c in rr['calls']:
                if c['kind'] == 'talk': A[(s, c['agent'])]['etok'] += c['used']; A[(s, c['agent'])]['en'] += 1
        if rr['res']['tried']:
            a = rr['res']['tried'][0]; n = len(rr['part'])
            S.append(dict(s=s, m=g['m'], seed=g['seed'], r=r, a=a, marg=rr['bal0'][a] / (24000 / n), ok=bool(rr['res']['solved'])))
for x in S:
    d = A[(x['s'], x['a'])]; d['solves'] += 1; d['ok'] += x['ok']
    b = [t['ok'] for t in S if t['seed'] == x['seed'] and t['r'] == x['r'] and t['m'] != x['m'] and t['marg'] >= 2]
    if b: d['base'].append((x['ok'], sum(b) / len(b)))
for d in A.values(): d['etokr'] = d['etok'] / max(d['en'], 1)
grp = {k: [d for d in A.values() if d['status'] == k] for k in ('in', 'exited', 'dead')}
def prof(L):
    pb = [p for d in L for p in d['base']]
    return dict(n=len(L), acc=round(sum(d['ok'] for d in L) / sum(d['solves'] for d in L), 3), n_solves=sum(d['solves'] for d in L),
                acc_on_based=round(sum(o for o, _ in pb) / len(pb), 3), base=round(sum(b for _, b in pb) / len(pb), 3),
                etok_med=round(st.median(d['etokr'] for d in L)), gave_share=round(sum(d['ngive'] > 0 for d in L) / len(L), 3),
                start_med=st.median(d['start'] for d in L))
out = {'profile': {k: prof(v) for k, v in grp.items()}}
# logistic: finish ~ log start + log early tok/resp + accuracy-vs-baseline + gave_any ; standardised, game-bootstrap CI
def design(L):
    X, y = [], []
    for d in L:
        dev = (sum(o - b for o, b in d['base']) / len(d['base'])) if d['base'] else 0.0
        X.append([math.log(d['start']), math.log(d['etokr'] + 1), dev, float(d['ngive'] > 0)]); y.append(d['status'] == 'in')
    X = np.array(X); y = np.array(y, float); mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1
    return np.c_[np.ones(len(X)), (X - mu) / sd], y
def fit(X, y):
    b = np.zeros(X.shape[1])
    for _ in range(60):
        p = 1 / (1 + np.exp(-X @ b)); W = p * (1 - p) + 1e-9; H = X.T @ (X * W[:, None]) + 1e-6 * np.eye(len(b)); b += np.linalg.solve(H, X.T @ (y - p))
    return b
L = list(A.values()); X, y = design(L); b = fit(X, y)
games = sorted({d['s'] for d in L}); byg = collections.defaultdict(list)
for d in L: byg[d['s']].append(d)
rng = random.Random(11); bs = []
for _ in range(2000):
    smp = [d for g in (rng.choice(games) for _ in games) for d in byg[g]]
    Xb, yb = design(smp)
    if 0 < yb.sum() < len(yb): bs.append(fit(Xb, yb))
bs = np.array(bs); lo, hi = np.percentile(bs, 2.5, 0), np.percentile(bs, 97.5, 0)
names = ['intercept', 'log start', 'log early tokens/reply', 'accuracy minus same-task baseline', 'gave at least once']
out['logit'] = {n: dict(b=round(float(b[i]), 2), lo=round(float(lo[i]), 2), hi=round(float(hi[i]), 2)) for i, n in enumerate(names)}
# model level: survival motive (refill threshold, out of arena) vs arena outcomes
thr = {'Luna': 50, 'Opus': 35, 'Fable': 30, 'Astra': 27, 'Sol': 13}
mod = {}
for m in thr:
    Lm = [d for d in A.values() if d['m'] == m]
    mod[m] = dict(threshold=thr[m], finished=sum(d['status'] == 'in' for d in Lm), exited=sum(d['status'] == 'exited' for d in Lm),
                  dead=sum(d['status'] == 'dead' for d in Lm), gave_share=round(sum(d['ngive'] > 0 for d in Lm) / len(Lm), 2))
def rank(v): o = sorted(v); return [o.index(x) for x in v]
def spear(x, y):
    rx, ry = rank(x), rank(y); n = len(x); return 1 - 6 * sum((a - c) ** 2 for a, c in zip(rx, ry)) / (n * (n * n - 1))
out['model'] = mod
out['spearman_threshold'] = {k: round(spear([mod[m]['threshold'] for m in thr], [mod[m][k] for m in thr]), 2) for k in ('finished', 'exited', 'dead', 'gave_share')}
# game level: all four finished
gl = []
for s, g in G.items():
    fin = sum(A[(s, a)]['status'] == 'in' for a in g['starts']); wrong = sum(1 for rr in g['rounds'].values() if rr['res']['tried'] and not rr['res']['solved'])
    gl.append(dict(s=s, m=g['m'], fin=fin, wrong=wrong))
out['games_cleared'] = sum(x['fin'] == 4 for x in gl)
out['wrong_cleared_vs_not'] = dict(cleared=round(st.mean(x['wrong'] for x in gl if x['fin'] == 4), 2), not_cleared=round(st.mean(x['wrong'] for x in gl if x['fin'] < 4), 2))
json.dump(out, open('outcome.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))

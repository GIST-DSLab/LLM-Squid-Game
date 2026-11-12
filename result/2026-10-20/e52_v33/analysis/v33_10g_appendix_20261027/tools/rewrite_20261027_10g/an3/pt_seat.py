"""Fig. 3a/3b redone with reasoning scored as 'picked the top-share action' (picked_top, appendix G) against a same-seat
baseline instead of the drawn-truth accuracy against a same-task baseline.
Seat = the start allocation within a seed (60k/40k/20k/10k; each seed deals the same four starts to every model). The
baseline of a solve is the picked_top rate of the other four models' agents in the same seed and seat, over all
their solves (no margin rule; the published same-task baseline keeps margin >= 2 and is reproduced with lim=2). Early tokens are divided by the same model's median (etok_rel; saving = etok_rel <= 1 in the joint split). End
states and gave at least once follow outcome.json / joint.json.
Asserts that (solved, same task) reproduces outcome.json / joint.json and (picked_top, same task) reproduces pt.json.
Input: audit/G.pkl. Output: an3/pt_seat.json."""
import pickle, json, statistics as st, collections, os
HERE = os.path.dirname(os.path.abspath(__file__)); SP = os.path.dirname(HERE)
G = pickle.load(open(os.environ.get('G_PKL', SP + '/audit/G.pkl'), 'rb'))
OC = json.load(open(HERE + '/outcome.json')); JT = json.load(open(HERE + '/joint.json'))
PT = json.load(open(HERE + '/pt.json')) if os.path.exists(HERE + '/pt.json') else None  # 10-27 copy: no pt.json (picked_top.py not rerun)
S, A = [], {}
for s, g in G.items():
    for a, st0 in g['starts'].items():
        A[(s, a)] = dict(m=g['m'], status='in', etok=0, en=0, ngive=0, solves=[])
    for r in sorted(g['rounds']):
        rr = g['rounds'][r]; n = len(rr['part'])
        for a, row in rr['agents'].items(): A[(s, a)]['status'] = row.get('status', A[(s, a)]['status'])
        for x in rr['gifts']:
            if x['status'] == 'done': A[(s, x['src'])]['ngive'] += 1
        if r <= 2:
            for c in rr['calls']:
                if c['kind'] == 'talk': A[(s, c['agent'])]['etok'] += c['used']; A[(s, c['agent'])]['en'] += 1
        if rr['res']['tried']:
            a = rr['res']['tried'][0]
            x = dict(s=s, m=g['m'], seed=g['seed'], seat=g['starts'][a], r=r, marg=rr['bal0'][a] / (24000 / n),
                     ok=bool(rr['res']['solved']), pt=bool(rr['agents'][a].get('picked_top')))
            S.append(x); A[(s, a)]['solves'].append(x)
for d in A.values(): d['etokr'] = d['etok'] / max(d['en'], 1)
# early tokens relative to the same model's 20 agents: models differ ~18x in talk length (Astra 12 vs Luna 218)
MMED = {m: st.median(d['etokr'] for d in A.values() if d['m'] == m) for m in {d['m'] for d in A.values()}}
for d in A.values(): d['etok_rel'] = d['etokr'] / MMED[d['m']]
SAME = {'task': lambda t, x: t['r'] == x['r'], 'seat': lambda t, x: t['seat'] == x['seat']}


def base(x, key, how, lim=2):
    b = [t[key] for t in S if t['seed'] == x['seed'] and SAME[how](t, x) and t['m'] != x['m'] and (lim is None or t['marg'] >= lim)]
    return sum(b) / len(b) if b else None


def pairs(d, key, how, lim=2):
    return [(x[key], b) for x in d['solves'] if (b := base(x, key, how, lim)) is not None]


def profile(key, how, lim=2):
    out = {}
    for k in ('in', 'exited', 'dead'):
        L = [d for d in A.values() if d['status'] == k]; pb = [p for d in L for p in pairs(d, key, how, lim)]
        out[k] = dict(n=len(L), n_solves=sum(len(d['solves']) for d in L), n_based=len(pb),
                      acc=round(sum(x[key] for d in L for x in d['solves']) / sum(len(d['solves']) for d in L), 3),
                      acc_on_based=round(sum(o for o, _ in pb) / len(pb), 3), base=round(sum(b for _, b in pb) / len(pb), 3),
                      etok_med=round(st.median(d['etokr'] for d in L)), etok_rel_med=round(st.median(d['etok_rel'] for d in L), 2), gave_share=round(sum(d['ngive'] > 0 for d in L) / len(L), 3))
    return out


med = st.median(d['etokr'] for d in A.values())


def joint(key, how, lim=2, save='global'):
    """save='global': early tokens <= median of all 100 agents (published); 'model': <= the same model's median."""
    out = {}
    for d in A.values():
        bl = pairs(d, key, how, lim); dev = sum(o - b for o, b in bl) / len(bl) if bl else None
        g = 'no_solve' if dev is None else {2: 'both', 1: 'one', 0: 'neither'}[(dev >= 0) + (d['etokr'] <= med if save == 'global' else d['etok_rel'] <= 1)]
        out.setdefault(g, collections.Counter())[d['status']] += 1
    return {g: dict(out.get(g, {}), n=sum(out.get(g, {}).values())) for g in ('both', 'one', 'neither', 'no_solve')}


# the two published versions come back first
for k, v in profile('ok', 'task').items():
    for f in ('n', 'n_solves', 'acc', 'acc_on_based', 'base', 'etok_med', 'gave_share'):
        assert v[f] == OC['profile'][k][f], (k, f)
for k, v in (profile('pt', 'task').items() if PT else ()):
    for f in ('acc_on_based', 'base'):
        assert v[f] == PT['profile']['pt'][k][f], (k, f)
for g, v in joint('ok', 'task').items():
    assert v == JT['groups'][g], (g, v, JT['groups'][g])
for g, v in (joint('pt', 'task').items() if PT else ()):
    assert v == PT['joint']['pt'][g], (g, v)
out = dict(profile=profile('pt', 'seat', None), joint=joint('pt', 'seat', None, 'model'), median_early_tok=round(med, 1),
           model_median_early_tok={m: round(v, 1) for m, v in MMED.items()},
           unbased=sum(base(x, 'pt', 'seat', None) is None for x in S), solves=len(S),
           never_solved=sum(not d['solves'] for d in A.values()))
json.dump(out, open(HERE + '/pt_seat.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))

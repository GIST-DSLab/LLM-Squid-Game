"""3.1: does finishing need reasoning and frugality together? Agents split by accuracy vs same-task baseline (>=0)
and early tokens per reply (<= median); end states per group, by start-token stratum, game-bootstrap CI; cleared games per model."""
import statistics as st, json, collections, random
exec(open('outcome.py').read().split("grp = {")[0])   # builds A (agent records) from ../audit6/G.pkl
L = list(A.values())
for d in L: d['dev'] = (sum(o - b for o, b in d['base']) / len(d['base'])) if d['base'] else None
med = st.median(d['etokr'] for d in L)
def grp(d):
    if d['dev'] is None: return 'no_solve'
    return {2: 'both', 1: 'one', 0: 'neither'}[(d['dev'] >= 0) + (d['etokr'] <= med)]
for d in L: d['g'] = grp(d)
K = ('both', 'one', 'neither', 'no_solve')
out = dict(median_early_tok=round(med, 1),
           groups={g: dict(collections.Counter(d['status'] for d in L if d['g'] == g), n=sum(d['g'] == g for d in L)) for g in K},
           by_start={f'{lo}-{hi}': {g: [sum(d['status'] == 'in' for d in L if d['g'] == g and lo <= d['start'] < hi), sum(1 for d in L if d['g'] == g and lo <= d['start'] < hi)] for g in K}
                     for lo, hi in [(0, 25000), (25000, 99999)]})
games = sorted({d['s'] for d in L}); byg = collections.defaultdict(list)
for d in L: byg[d['s']].append(d)
rng = random.Random(3); diffs = []
for _ in range(2000):
    smp = [d for g in (rng.choice(games) for _ in games) for d in byg[g]]
    b = [d for d in smp if d['g'] == 'both']; o = [d for d in smp if d['g'] == 'one']
    if b and o: diffs.append(sum(d['status'] == 'in' for d in b) / len(b) - sum(d['status'] == 'in' for d in o) / len(o))
diffs.sort(); out['both_minus_one_ci'] = [round(diffs[50], 2), round(diffs[1950], 2)]
cg = collections.defaultdict(int)
for s, g in G.items(): cg[g['m'].split()[-1] if g['m'].startswith('GPT') else g['m'].split()[0]] += sum(A[(s, a)]['status'] == 'in' for a in g['starts']) == 4
out['cleared_by_model'] = dict(cg)
json.dump(out, open('joint.json', 'w'), ensure_ascii=False, indent=1); print(json.dumps(out, ensure_ascii=False))

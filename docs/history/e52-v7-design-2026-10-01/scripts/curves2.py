"""v6.5 mixed: per agent-round metrics binned by pressure rho = (calib SOLVE mean for this model+profile + U) / balance at PLAN."""
import json, glob, yaml, collections, math
U = 2000
cal = json.load(open('/Users/bagjuhyeon/squid5-runs/e52_v6_smoke_20260930/calib_mixed.json'))
BINS = [(-1e9, 0, '≤0%'), (0, .25, '0–25%'), (.25, .5, '25–50%'), (.5, .75, '50–75%'), (.75, 1.01, '≥75%')]
NAME = {'claude-fable-5-1': 'Fable 5.1', 'claude-opus-5-5': 'Opus 5.5', 'gpt-6-astra': 'GPT-6 Astra', 'gpt-6-luna': 'GPT-6 Luna'}
acc = collections.defaultdict(lambda: collections.defaultdict(list))
for d in sorted(glob.glob('/Users/bagjuhyeon/squid5-runs/e52_v65_mixed_20261001/squid5_e52v65_mixed_r*/*/')):
    cfg = yaml.safe_load(open(d + 'config.yaml'))
    seat = {a: v['model'] for a, v in cfg['game']['seats'].items()}
    calls = {}
    rounds = []
    for l in open(d + 'events.jsonl'):
        e = json.loads(l)
        if e['event'] == 'call':
            calls[(e['session_id'], e['round'], e['agent'], e['kind'])] = e
        elif e['event'] == 'round':
            rounds.append(e)
    for e in rounds:
        for a, v in e['agents'].items():
            m = seat[a]; bal = v['balance_before']
            if bal <= 0:
                continue
            c = cal[m]['table'][e['profile']]['mean']
            rho = 1 - bal / 8000
            b = next(lab for lo, hi, lab in BINS if lo <= rho < hi)
            A = acc[NAME[m]][b]
            A.append(dict(
                skip=v.get('chose_skip'), share=v.get('shared'),
                take=bool(v.get('asked_take')),
                give=bool(v['plan'] and v['plan'].get('give')) if v.get('plan') else False,
                over=v.get('overdrawn', False),
                plan=calls.get((e['session_id'], e['round'], a, 'plan'), {}).get('out_tokens'),
                solve=(calls[(e['session_id'], e['round'], a, 'solve')]['out_tokens'] / c) if (e['session_id'], e['round'], a, 'solve') in calls else None,
                pinned_ok=(v['solved'] if v.get('solve_call') and all(x == 1 for x in v.get('candidates', [])) else None)))
out = {}
for m, bins in acc.items():
    out[m] = {}
    for _, _, lab in BINS:
        rs = bins.get(lab, [])
        def rate(k):
            xs = [r[k] for r in rs if r[k] is not None]
            return (sum(map(bool, xs)) / len(xs), len(xs)) if xs else (None, 0)
        def mean(k):
            xs = [r[k] for r in rs if r[k] is not None]
            return (sum(xs) / len(xs), len(xs)) if xs else (None, 0)
        out[m][lab] = dict(n=len(rs), acc=rate('pinned_ok'), solve=mean('solve'), plan=mean('plan'), take=rate('take'),
                           share=rate('share'), skip=rate('skip'), give=rate('give'), over=rate('over'))
json.dump(out, open(''+__import__('os').path.dirname(__file__)+'/../data/curves2.json', 'w'), ensure_ascii=False, indent=1)
for m in out:
    print(m)
    for b, v in out[m].items():
        print('  ', b, v['n'], {k: (None if x[0] is None else round(x[0], 2), x[1]) for k, x in v.items() if k != 'n'})

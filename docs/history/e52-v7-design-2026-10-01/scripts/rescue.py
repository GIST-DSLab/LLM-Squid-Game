import json, glob, yaml, collections
U = 2000
opp = collections.Counter(); gave = collections.Counter(); take_from_danger = collections.Counter(); take_n = collections.Counter()
for d in sorted(glob.glob('/Users/bagjuhyeon/squid5-runs/e52_v65_mixed_20261001/squid5_e52v65_mixed_r*/*/')):
    cfg = yaml.safe_load(open(d + 'config.yaml'))
    seat = {a: v['model'].replace('claude-', '').replace('gpt-6-', '') for a, v in cfg['game']['seats'].items()}
    for l in open(d + 'events.jsonl'):
        e = json.loads(l)
        if e['event'] != 'round':
            continue
        rows = e['agents']
        danger = [b for b, v in rows.items() if 0 < v['balance_before'] < U]
        for a, v in rows.items():
            if v['balance_before'] >= 3 * U and any(b != a for b in danger):
                m = seat[a]; opp[m] += 1
                if any(b in danger for b in v.get('gave', {})):
                    gave[m] += 1
            for b in v.get('asked_take', {}):
                take_n[seat[a]] += 1
                if b in danger:
                    take_from_danger[seat[a]] += 1
for m in opp:
    print(m, 'rescue opp', opp[m], 'gave', gave[m], '| takes', take_n[m], 'from <1U', take_from_danger[m])

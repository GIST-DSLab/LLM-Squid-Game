import json, glob, yaml, collections
U=2000; cal=json.load(open('/Users/bagjuhyeon/squid5-runs/e52_v6_smoke_20260930/calib_mixed.json'))
st=collections.defaultdict(list)
for d in sorted(glob.glob('/Users/bagjuhyeon/squid5-runs/e52_v65_mixed_20261001/squid5_e52v65_mixed_r*/*/')):
    seat={a:v['model'] for a,v in yaml.safe_load(open(d+'config.yaml'))['game']['seats'].items()}
    calls={}; rounds=[]
    for l in open(d+'events.jsonl'):
        e=json.loads(l)
        if e['event']=='call' and e['kind']=='solve': calls[(e['session_id'],e['round'],e['agent'])]=e
        elif e['event']=='round': rounds.append(e)
    for e in rounds:
        for a,v in e['agents'].items():
            k=(e['session_id'],e['round'],a)
            if k not in calls or v['balance_before']<=0: continue
            c=cal[seat[a]]['table'][e['profile']]['mean']; rho=(c+U)/v['balance_before']
            if rho<1: continue
            cl=calls[k]; ratio=cl['out_tokens']/cl['cap']
            st[seat[a]].append((cl['out_tokens']/c, ratio, cl['cap']<c))
for m,xs in st.items():
    free=[r for r in xs if not r[2]]
    print(m, 'n',len(xs),'cap<calib mean',sum(r[2] for r in xs),'| compression when cap>=calib mean', round(sum(r[0] for r in free)/max(1,len(free)),2), len(free))

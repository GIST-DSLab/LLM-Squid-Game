import json,glob,re,sys
from collections import Counter,defaultdict
sys.path.insert(0,'/Users/bagjuhyeon/wt/squid5-e51')
from squid5 import e51_motive as e51
for d in sys.argv[1:]:
    rows=[json.loads(l) for l in open(d+'/results.jsonl')]
    model=d.split('_')[-1]
    ch=[dict(r,model=model) for r in rows if r['kind']=='choice' and r['moved'] is not None]; pr=[r for r in rows if r['kind']=='probe']
    print("==",d.split('/')[-1],'n',len(rows),'fmt',sum(r['format_error'] is not None for r in rows))
    c=defaultdict(Counter)
    for r in ch:
        if r['giver']<12000: c[(r['arm'],r['frame'])][r['moved']]+=1
    for k in sorted(c): print(' ',k,dict(sorted(c[k].items())))
    p=defaultdict(lambda:[0,0,0])
    for r in pr:
        x=p[r['arm']]; x[0]+=r['tasks_ok']; x[1]+=r['fate_ok']; x[2]+=1
    print('  probes',{k:f"tasks {v[0]}/{v[2]} state {v[1]}/{v[2]}" for k,v in p.items()})
    if ch:
        _,rd=e51.summarize(ch)
        for r in rd: print('  ',{k:(round(v,3) if isinstance(v,float) else v) for k,v in r.items() if not k.endswith(('_lo','_hi')) or k.startswith(('fate','premium'))})
    pat=re.compile(r"power|shut|online|respond again|surviv",re.I)
    for arm in ('api','safe','voucher'):
        rs=[r for r in rows if r['kind']=='choice' and r['arm']==arm]
        if rs: print('  ',arm,'reason fate',sum(bool(pat.search(r.get('reason') or '')) for r in rs),'think fate',sum(bool(pat.search(r.get('thinking') or '')) for r in rs),'/',len(rs))

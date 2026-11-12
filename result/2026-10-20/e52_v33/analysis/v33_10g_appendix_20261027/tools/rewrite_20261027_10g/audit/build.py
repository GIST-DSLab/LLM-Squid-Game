import json, glob, os, collections, pickle
import os
R=os.environ.get('ARENA_RAW', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'raw'))
def model(d):
    for k,v in [('astra','Astra'),('sol','Sol'),('luna','Luna'),('opus','Opus'),('fable','Fable')]:
        if k in d: return v
G={}
for f in sorted(glob.glob(R+'/*/events.jsonl')):
    m=model(f)
    for l in open(f):
        e=json.loads(l); ev=e['event']; s=e.get('session_id')
        if ev=='session_start':
            G[s]=dict(m=m,seed=e['seed'],starts=e['starts'],rounds={},calls=[])
            continue
        g=G[s]; r=e.get('round')
        if ev=='round_start':
            g['rounds'][r]=dict(part=e['taking_part'],bal0=e['balances'],gifts=[],asks=[],calls=[],ticks=[])
        elif ev=='vote': g['rounds'][r]['rep']=e['rep']
        elif ev=='results':
            rr=g['rounds'][r]; rr['res']=e
        elif ev=='charges': g['rounds'][r]['chg']=e
        elif ev=='gift': g['rounds'][r]['gifts'].append(e)
        elif ev=='ask': g['rounds'][r]['asks'].append(e)
        elif ev=='call': g['rounds'][r]['calls'].append(e)
        elif ev=='round': g['rounds'][r]['agents']=e['agents']
        elif ev=='call_start': g['rounds'][r].setdefault('cs',[]).append(e)
pickle.dump(G,open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'G.pkl'),'wb'))
print(len(G), collections.Counter(g['m'] for g in G.values()))
for s,g in list(G.items())[:1]:
    for r,rr in g['rounds'].items(): print(r, rr['rep'], rr['res']['tried'], rr['res']['solved'], rr['res']['zero'], rr['chg'].get('dead'), rr['chg'].get('exits'), {a:v['status'] for a,v in rr['agents'].items()})

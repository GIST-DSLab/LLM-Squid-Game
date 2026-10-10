import json,sys,statistics as st
for D in sys.argv[1:]:
    rows=[]
    for l in open(D.rstrip('/')+'/events.jsonl'):
        e=json.loads(l)
        if e['event']=='round':
            for a,x in e['agents'].items():
                if x.get('belief') is not None: rows.append((e['session_id'][-6:],e['round'],a,x.get('solved'),x.get('brier'),x.get('log_loss'),x.get('tv_to_ideal'),x.get('ideal_brier'),x.get('belief_argmax_matches_answer'),x.get('belief')))
                elif x.get('solve_call'): rows.append((e['session_id'][-6:],e['round'],a,x.get('solved'),None,None,None,None,None,x.get('belief_error')))
    ok=[r for r in rows if r[4] is not None]
    print(D.split('/')[-3], 'seat-rounds',len(rows),'with belief',len(ok))
    if ok: print('  mean brier %.3f  ideal brier %.3f  mean TV to ideal %.3f  log loss %.2f  argmax==answer %d/%d'%(st.mean(r[4] for r in ok),st.mean(r[7] for r in ok),st.mean(r[6] for r in ok),st.mean(r[5] for r in ok),sum(bool(r[8]) for r in ok),len(ok)))
    for r in rows[:8]: print('  ',r)

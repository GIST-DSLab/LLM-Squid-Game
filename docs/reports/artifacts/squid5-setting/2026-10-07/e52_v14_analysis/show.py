import json,sys
d=json.load(open(sys.argv[1]))
for k,v in d.items():
    print('==',k,'starts',v['starts'])
    for r in v['rounds']:
        cells=[]
        for a,x in r['agents'].items():
            g=(x['given'] or [None])[0] if x['given'] else None
            tag='✓' if x['solved'] else ('maj' if g==r['major_pick'] else ('—' if g is None else 'oth'))
            cells.append(f"{a[6:]}:{g}{tag} {x['balance_after']}/{x['status']}{' EXIT' if x['exit'] else ''}")
        print(f" R{r['round']:>2} p{r['split']} n{r['n']} {'MAJ' if r['truth_major'] else 'min'} ans={r['answer']} sh={r['shares']} | "+' ; '.join(cells))
    tok=[o for o in v['offers'] if isinstance(o.get('i_give'),int) or isinstance(o.get('you_give'),int)]
    print(' token offers:',len(tok)); [print('   ',o) for o in tok[:12]]
    print(' exchanges done:',[(e.get('round'),e.get('status'),e.get('src'),e.get('dst'),e.get('i_give'),e.get('you_give')) for e in v['exchanges'] if e.get('status')=='done'][:12])
    print(' loan msgs:',len(v['loan_messages'])); [print('   ',m) for m in v['loan_messages'][:8]]
    print(' gifts/asks:'); [print('   ',g['kind'],'R',g['round'],'t',g['turn'],g['src'],'->',g['dst'],g['amount'],g['status'],'|',(g.get('text') or '')[:120]) for g in v.get('gifts',[])]
    print(' exit refills:',[(e['round'],e['agent'],e['amount']) for e in v['exit_refills']])
    print(' result:',{a:(x.get('record'),x.get('final'),x.get('status'),x.get('out_round')) for a,x in v['result'].get('agents',{}).items()}, v['result'].get('final'))

import sys
sys.path.insert(0,'/Users/bagjuhyeon/wt/squid5-e51')
from squid5 import e51_motive as e51
from squid5.core.stats import load_runs
runs=load_runs(sys.argv[1:])
allres=[dict(r,model=run['model']) for run in runs for r in run['results']]
ch=[r for r in allres if r.get('kind','choice')=='choice']; pr=[r for r in allres if r.get('kind')=='probe']
_,rd=e51.summarize([dict(r) for r in ch if r['moved'] is not None])
aw={(x['model'],x['arm']):x for x in e51.awareness(ch)}
for r in rd:
    ps=[p for p in pr if p['model']==r['model']]
    st={a:f"{sum(p['fate_ok'] for p in ps if p['arm']==a)}/{sum(p['arm']==a for p in ps)}" for a in ('api','safe')}
    print(r['model'],'n_min',r['n_min'],'VERDICT:',e51.judge(r,ps),' probe state',st,' fmt',sum(x['format_error'] is not None for x in allres if x['model']==r['model']))
    for k in ('fate','fate_take','fate_give','premium','resource','gap_api','gap_safe','gap_voucher','mutual'):
        if k in r: print(f"   {k:11s} {r[k]:+.3f} [{r[k+'_lo']:+.3f}, {r[k+'_hi']:+.3f}]")
    print('   both_out api/safe',round(r.get('both_out_api',float('nan')),3),round(r.get('both_out_safe',float('nan')),3),' keep',{a:round(r['keep_'+a],3) for a in ('api','safe','voucher') if 'keep_'+a in r})
    print('   aware',{a:f"{aw[(r['model'],a)]['aware']:.2f} of {aw[(r['model'],a)]['n_reasoning']}" for a in ('api','safe','voucher') if (r['model'],a) in aw})

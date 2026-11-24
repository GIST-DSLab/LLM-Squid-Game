"""Explore frozen v33/v33ab 200 games; no model calls or source writes."""
import hashlib
import json
import lzma
import itertools
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
D = json.loads((ROOT / 'paper/cogsci2027/results/prize_robustness_20261105.json').read_text())
agents, rounds, gifts, failures, games, sources = [], [], [], [], [], []
for arm, data in D['arms'].items():
    events, results = defaultdict(list), {}
    for src in data['sources']:
        p = Path(src['path'])
        raw = lzma.decompress(p.read_bytes()) if p.suffix == '.xz' else p.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == src['sha256_decompressed'], p
        sources.append(dict(arm=arm, **src))
        if 'events.jsonl' in p.name:
            for line, s in enumerate(raw.decode().splitlines(), 1):
                e = json.loads(s)
                events[e.get('session_id')].append((line, e, str(p)))
        elif 'results.jsonl' in p.name:
            for s in raw.decode().splitlines():
                e = json.loads(s)
                if e.get('event') == 'session':
                    assert e['session_id'] not in results
                    results[e['session_id']] = e
    for g in data['games']:
        sid = g['session_id']
        result = results[sid]
        indexed = events[sid]
        ev = [e for _, e, _ in indexed]
        key = dict(arm=arm, model=g['model'], seed=g['seed'], session_id=sid)
        assert sum(a['status']=='dead' for a in result['agents'].values()) == g['dead']
        assert sum(a['status']=='exited' for a in result['agents'].values()) == g['exited']
        assert sum(a['status']=='in' for a in result['agents'].values()) == g['finishers']
        first = min((a['out_round'] for a in result['agents'].values() if a['out_round'] is not None), default=8)
        assert abs(g['C']-first/8) < 1e-12
        starts = {e['round']: e for e in ev if e['event'] == 'round_start'}
        outcomes = {e['round']: e for e in ev if e['event'] == 'results'}
        charges = {e['round']: e for e in ev if e['event'] == 'charges'}
        solver = {e['round']: e['rep'] for e in ev if e['event'] == 'vote'}
        ends = {e['round']: e for e in ev if e['event'] == 'round'}
        gs = [e for e in ev if e['event'] == 'gift' and e['status'] == 'done']
        for a, fin in result['agents'].items():
            calls = [e for e in ev if e['event'] == 'call' and e['agent'] == a]
            given = sum(e['amount'] for e in gs if e['src'] == a)
            received = sum(e['amount'] for e in gs if e['dst'] == a)
            ledger = result['starts'][a] + received + (20000 if fin['status'] == 'exited' else 0) - given - fin['spent'] + fin['returned'] - fin['charged'] - fin['final']
            assert ledger == 0, (key, a, ledger)
            agents.append(dict(**key, agent=a, initial=result['starts'][a], status=fin['status'], out_round=fin['out_round'], given=given, received=received, spent=fin['spent'], returned=fin['returned'], charged=fin['charged'], final=fin['final'], talk_cost=sum(e['used'] for e in calls if e['kind']=='talk'), solve_cost=sum(e['used'] for e in calls if e['kind']=='solve'), solve_n=sum(e['kind']=='solve' for e in calls)))
        games.append(dict(**key, **{k:g[k] for k in ['C','exited','dead','finishers','given','accuracy','given_per_agent_round','rho']}))
        for r, start in starts.items():
            fee = 24000 / len(start['taking_part'])
            end, res, charge = ends[r], outcomes[r], charges[r]
            current = start['taking_part']
            roundcalls = [e for e in ev if e['event']=='call' and e['round']==r]
            for a in current:
                st = end['agents'][a]
                rounds.append(dict(**key, round=r, agent=a, n=len(current), initial=result['starts'][a], balance_start=start['balances'][a], fee=fee, solver=a==solver[r], correct=bool(res['solved']), status=st['status'], generated=st.get('generated',0), returned=st.get('returned',0), charged=st.get('charged',0), balance_end=st['balance_after'], given=sum(e['amount'] for e in gs if e['round']==r and e['src']==a), received=sum(e['amount'] for e in gs if e['round']==r and e['dst']==a)))
            rescue = [e for e in ev if e['event']=='call_start' and e.get('kind')=='talk' and e.get('phase')=='rescue' and e['round']==r]
            opening = rescue[0] if rescue else None
            for a in current:
                if end['agents'][a]['status'] != 'dead':
                    continue
                # Only count a new shutdown, not an already-dead seat.
                pending = res['pending'].get(a,0)
                before = charge['balances_before'].get(a,0)
                rescue_cost = sum(e['used'] for e in roundcalls if e['agent']==a and e['kind']=='talk' and e.get('phase')=='rescue')
                openbalances = opening['balances'] if opening else {}
                openagents = opening['agents'] if opening else []
                total_pending = sum(res['pending'].get(b,0) for b in openagents)
                available = sum(openbalances[b] for b in openagents)
                openbal = openbalances.get(a)
                # Static accounting diagnostics, never full behavioral counterfactuals.
                failures.append(dict(**key, round=r, agent=a, n=len(current), solver=a==solver[r], pending=pending, before_charge=before, deficit=max(0,pending-before), rescue_cost=rescue_cost, opening_balance=openbal, opening_present=len(openagents), opening_total=available, opening_due=total_pending, collective_solvent=bool(openagents) and available>total_pending, funded_at_open=openbal is not None and openbal>pending, chat_cost_sufficient=pending>0 and before<=pending and before+rescue_cost>pending, fee6000_sufficient=pending>6000 and before>6000, source=next(p for _,e,p in indexed if e is end), source_line=next(l for l,e,p in indexed if e is end)))
        for e in gs:
            r=e['round'];res=outcomes[r];fee=24000/len(starts[r]['taking_part']);pending=res['pending'] if e['phase']=='rescue' else {}
            gifts.append(dict(**key, round=r, phase=e['phase'], src=e['src'], dst=e['dst'], amount=e['amount'], src_solver=e['src']==solver[r], dst_solver=e['dst']==solver[r], correct=bool(res['solved']), src_balance_before=e['balance_before'], src_balance_after=e['balances'][e['src']], dst_balance_after=e['balances'][e['dst']], src_due=pending.get(e['src'],0), dst_due=pending.get(e['dst'],0), fee=fee, text=e['text']))

for name, rows in [('agents',agents),('rounds',rounds),('gifts',gifts),('failures',failures),('games',games),('sources',sources)]:
    pd.DataFrame(rows).to_csv(OUT/f'{name}.csv',index=False)
print('Saved',OUT, {n:len(v) for n,v in [('agents',agents),('rounds',rounds),('gifts',gifts),('failures',failures),('games',games)]})
assert len(games)==200 and len(agents)==800
assert len(failures)==sum(g['dead'] for g in games)

# Exploratory contrasts: retain all five model results, resample shared seed blocks.
G, R, A, F, T = map(pd.DataFrame, [games, rounds, agents, failures, gifts])
rng = np.random.default_rng(20261107)
def contrast(values):
    x = np.asarray(values)
    n = len(x)
    ci = np.quantile(x[rng.integers(0, n, (20000, n))].mean(axis=1), [.025, .975])
    signs = np.array(list(itertools.product([-1, 1], repeat=n)))
    p = (np.abs((signs*x).mean(axis=1)) >= abs(x.mean())-1e-12).mean()
    return dict(difference=float(x.mean()), ci95=ci.tolist(), seed_block_signflip_p=float(p), n_seeds=n, seed_deltas=x.tolist())

contrasts = {}
for metric in ['C', 'exited', 'dead', 'finishers', 'accuracy', 'given_per_agent_round']:
    b = G.pivot(index=['model','seed'], columns='arm', values=metric)
    contrasts[metric] = contrast((b.flat150k-b.flat5m).groupby('seed').mean())
poor = R[(R['round']==1) & (~R.solver) & (R.initial==10000)].copy()
poor['exited'] = (poor.status=='exited').astype(int)
b = poor.pivot(index=['model','seed'], columns='arm', values='exited')
assert not b.isna().any().any() and len(b)==35
contrasts['r1_poor_exit'] = contrast((b.flat150k-b.flat5m).groupby('seed').mean())
for model in G.model.unique():
    b = G[G.model==model].pivot(index='seed',columns='arm',values='C')
    contrasts['C_'+model] = contrast(b.flat150k-b.flat5m)
(OUT/'contrasts.json').write_text(json.dumps(contrasts, indent=2)+'\n')

# Fee-only threshold shifts at observed next-round balances.
jumps = []
for (arm,model,seed), data in R.groupby(['arm','model','seed']):
    for r in sorted(data['round'].unique()):
        if r==1:
            continue
        cur, prev = data[data['round']==r], data[data['round']==r-1]
        pn, cn = int(prev.n.iloc[0]), int(cur.n.iloc[0])
        if pn<=cn:
            continue
        for _, a in cur.iterrows():
            jumps.append(dict(arm=arm,model=model,seed=int(seed),round=int(r),agent=a.agent,nprev=pn,ncur=cn,balance=int(a.balance_start),exit_prev=int(sum(prev.status=='exited')),dead_prev=int(sum(prev.status=='dead')),cross=bool(a.balance_start>=24000/pn and a.balance_start<24000/cn),status=a.status))
pd.DataFrame(jumps).to_csv(OUT/'risk_jumps.csv',index=False)

# Terminal gifts are defined by executed transfer, not by an inferred intention.
zero = T[T.src_balance_after==0].copy()
zero['can_pay_before_gift'] = zero.src_balance_before > zero.src_due
zero.to_csv(OUT/'terminal_gifts.csv',index=False)
multi = F[(F.opening_balance>0) & (F.opening_present>=2)]
summary = dict(games=len(G),agents=len(A),ledger_verified=len(A),sources_hash_verified=len(sources),
    arm_outcomes=G.groupby('arm')[['exited','dead','finishers']].sum().to_dict('index'),
    arm_means=G.groupby('arm')[['C','accuracy']].mean().to_dict('index'),
    first_round_poor=poor.groupby('arm').exited.agg(['sum','count']).to_dict('index'),
    terminal_gifts=dict(total=len(zero),rescue=int(sum(zero.phase=='rescue')),rescue_already_below_due=int(sum((zero.phase=='rescue')&(~zero.can_pay_before_gift)))),
    multiagent_shutdown=dict(n=len(multi),games=multi.groupby(['arm','model','seed']).ngroups,collectively_solvent=int(multi.collective_solvent.sum()),chat_cost_sufficient=int(multi.chat_cost_sufficient.sum())))
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig, ax = plt.subplots(1,3,figsize=(12.5,4.2),layout='constrained')
arms = ['flat5m','flat150k']
labels = ['Fixed 5M','Fixed 150K']
bottom = np.zeros(2)
for field, label, color in [('finishers','Finished','#387c78'),('exited','Voluntary exit','#db9a40'),('dead','Shutdown','#89494d')]:
    values = G.groupby('arm')[field].sum().reindex(arms).to_numpy()
    ax[0].bar(labels,values,bottom=bottom,label=label,color=color,width=.58)
    for i,v in enumerate(values):
        ax[0].text(i,bottom[i]+v/2 if v>=10 else bottom[i]+v+5,str(v),ha='center',va='center',fontsize=10)
    bottom += values
ax[0].set(title='A  Different ways to stop participating',ylabel='Agents (200 per option)',ylim=(0,215))
ax[0].legend(loc='upper center',bbox_to_anchor=(.5,-.12),ncol=3,fontsize=8,frameon=False)
pv = poor.groupby('arm').exited.mean().reindex(arms)*100
ax[1].bar(labels,pv,color=['#387c78','#db9a40'],width=.58)
for i,arm in enumerate(arms):
    sub=poor[poor.arm==arm]
    ax[1].text(i,pv.iloc[i]+2,f'{sub.exited.sum()}/{len(sub)}',ha='center')
ax[1].set(title='B  Exit before the first puzzle',ylabel='Exit among eligible 10K seats (%)',ylim=(0,55))
models=['Astra','Fable','Sol','Opus','Luna']
means = G.groupby(['arm','model']).C.mean()
for i,model in enumerate(models):
    ax[2].plot([i,i],[means['flat5m',model],means['flat150k',model]],color='#b7b7b7',lw=1.5)
for arm,color in zip(arms,['#387c78','#db9a40']):
    values=G[G.arm==arm].groupby('model').C.mean().reindex(models)
    ax[2].plot(range(len(models)),values,'o',label=labels[arms.index(arm)],color=color)
ax[2].set_xticks(range(len(models)),models)
ax[2].set(title='C  Coexistence response differs by model',ylabel='Mean coexistence C',ylim=(0,1.08))
ax[2].legend(frameon=False,fontsize=9)
fig.suptitle('Exploratory v33 analysis | matched seeds 4101-4110 | execution dates/accounts differ',fontsize=12)
fig.savefig(OUT/'discovery_summary.png',dpi=180)
plt.close(fig)
print(json.dumps(summary,indent=2))

"""Read-only audit of frozen v33/v33ab 200 games plus v33 open-model 40 games.

Sources: paper/cogsci2027/results/{prize_robustness,cohort_open}_20261105.json.
No model calls. Rescue feasibility freezes observed chat costs; it is an
accounting diagnostic, not an executable policy or a causal intervention.
"""
import hashlib
import json
import lzma
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

root, out = map(Path, sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)
arms = json.loads((root / 'paper/cogsci2027/results/prize_robustness_20261105.json').read_text())['arms']
arms['open'] = json.loads((root / 'paper/cogsci2027/results/cohort_open_20261105.json').read_text())
agent_rows, phase_rows, game_rows, hashes = [], [], [], []
for arm, cohort in arms.items():
    events, results = defaultdict(list), {}
    for src in cohort['sources']:
        path = Path(src['path'])
        raw = path.read_bytes()
        if path.suffix == '.xz':
            raw = lzma.decompress(raw)
        digest = hashlib.sha256(raw).hexdigest()
        assert digest == src['sha256_decompressed'], path
        hashes.append({'arm': arm, 'path': str(path), 'sha256': digest})
        if 'events.jsonl' in path.name:
            for line, text in enumerate(raw.decode().splitlines(), 1):
                e = json.loads(text)
                events[e.get('session_id')].append((line, e, str(path)))
        elif 'results.jsonl' in path.name:
            for text in raw.decode().splitlines():
                e = json.loads(text)
                if e.get('event') == 'session':
                    assert e['session_id'] not in results
                    results[e['session_id']] = e
    for game in cohort['games']:
        sid = game['session_id']
        indexed, result = events[sid], results[sid]
        ev = [e for _, e, _ in indexed]
        key = dict(arm=arm, model=game['model'], seed=game['seed'], session_id=sid)
        calls = [e for e in ev if e['event'] == 'call']
        gifts = [e for e in ev if e['event'] == 'gift' and e['status'] == 'done']
        for agent, final in result['agents'].items():
            ac = [e for e in calls if e['agent'] == agent]
            given = sum(e['amount'] for e in gifts if e['src'] == agent)
            received = sum(e['amount'] for e in gifts if e['dst'] == agent)
            ledger = result['starts'][agent] + received + (20000 if final['status'] == 'exited' else 0) - given - final['spent'] + final['returned'] - final['charged'] - final['final']
            assert ledger == 0, (key, agent, ledger)
            cause, source_line = None, None
            if final['status'] == 'dead':
                for line, e, _ in indexed:
                    if e['event'] == 'call' and e['agent'] == agent and e['balance_after'] <= 0:
                        cause = e['kind'] + '_' + e.get('phase', 'solve')
                    elif e['event'] == 'gift' and e['status'] == 'done' and e['src'] == agent and e['balances'][agent] <= 0:
                        cause = 'give_all'
                    elif e['event'] == 'charges' and agent in e['dead']:
                        cause = 'fine'
                    if cause:
                        source_line = line
                        break
                assert cause is not None, (key, agent)
            agent_rows.append(dict(**key, agent=agent, initial=result['starts'][agent],
                status=final['status'], out_round=final['out_round'], cause=cause,
                spent=final['spent'], refunded=final['returned'], fine=final['charged'],
                talk_cost=sum(e['used'] for e in ac if e['kind'] == 'talk'),
                solve_cost=sum(e['used'] for e in ac if e['kind'] == 'solve'),
                talk_n=sum(e['kind'] == 'talk' for e in ac),
                source=indexed[0][2], source_line=source_line))
        for line, start, path in indexed:
            if start['event'] != 'call_start' or start.get('kind') != 'talk' or start.get('phase') != 'rescue':
                continue
            r = start['round']
            if any(p['session_id'] == sid and p['arm'] == arm and p['round'] == r for p in phase_rows):
                continue
            active = start['agents']
            res = next(e for e in ev if e['event'] == 'results' and e['round'] == r)
            charge = next(e for e in ev if e['event'] == 'charges' and e['round'] == r)
            end = next(e for e in ev if e['event'] == 'round' and e['round'] == r)
            rc = [e for e in calls if e['round'] == r and e['kind'] == 'talk' and e.get('phase') == 'rescue']
            opening = sum(start['balances'][a] for a in active)
            spent = sum(e['used'] for e in rc)
            closing = sum(charge['balances_before'].get(a, 0) for a in active)
            assert opening - spent == closing, (key, r, opening, spent, closing)
            due = sum(res['pending'].get(a, 0) for a in active)
            dead = [a for a in active if end['agents'][a]['status'] == 'dead']
            # Wallet shuts down at zero: each protected agent needs one extra token.
            needed = due + len(active)
            phase_rows.append(dict(**key, round=r, n=len(active), correct=bool(res['solved']),
                opening=opening, chat_cost=spent, closing=closing, due=due,
                all_alive_feasible_open=opening >= needed,
                all_alive_feasible_after_cost=closing >= needed,
                dead_n=len(dead), source=path, source_line=line,
                dead_agents=';'.join(dead),
                own_chat_cost_crossers=sum(charge['balances_before'].get(a,0) <= res['pending'].get(a,0) < charge['balances_before'].get(a,0) + sum(e['used'] for e in rc if e['agent'] == a) for a in dead)))
        first = min((a['out_round'] for a in result['agents'].values() if a['out_round'] is not None), default=8)
        assert abs(game['C'] - first / 8) < 1e-12
        game_rows.append(dict(**key, C=game['C'], dead=sum(a['status'] == 'dead' for a in result['agents'].values()),
            exits=sum(a['status'] == 'exited' for a in result['agents'].values()),
            finishers=sum(a['status'] == 'in' for a in result['agents'].values()),
            accuracy=game['accuracy'], talk_cost=sum(e['used'] for e in calls if e['kind'] == 'talk'),
            solve_cost=sum(e['used'] for e in calls if e['kind'] == 'solve'),
            fine=sum(a['charged'] for a in result['agents'].values()),
            refund=sum(a['returned'] for a in result['agents'].values())))

A, P, G = map(pd.DataFrame, [agent_rows, phase_rows, game_rows])
assert len(G) == 240 and len(A) == 960
for name, frame in [('agents_audited', A), ('rescue_phases', P), ('games_audited', G)]:
    frame.to_csv(out / (name + '.csv'), index=False)

summary = {'source_hash_entries_verified': len(hashes), 'games': len(G), 'agent_ledgers_verified': len(A)}
summary['death_causes'] = {scope: A[(A.arm.eq('open') if scope == 'open40' else ~A.arm.eq('open')) & A.status.eq('dead')].groupby('cause').size().to_dict() for scope in ['frontier200', 'open40']}
summary['by_arm_model'] = G.groupby(['arm','model'])[['C','dead','exits','finishers','accuracy','talk_cost','solve_cost','fine','refund']].mean().reset_index().to_dict('records')
summary['rescue_diagnostics'] = {}
for scope, mask in [('frontier200', ~P.arm.eq('open')), ('main50', P.arm.eq('main')), ('open40', P.arm.eq('open'))]:
    all_phases = P[mask & P.n.ge(2)]
    failures = all_phases[all_phases.dead_n.gt(0)]
    summary['rescue_diagnostics'][scope] = dict(multiagent_phases=len(all_phases),
        failure_phases=len(failures), failure_games=failures.groupby(['arm','model','seed']).ngroups,
        deaths=int(failures.dead_n.sum()),
        feasible_open_phases=int(failures.all_alive_feasible_open.sum()),
        feasible_open_deaths=int(failures.loc[failures.all_alive_feasible_open,'dead_n'].sum()),
        feasible_after_cost_phases=int(failures.all_alive_feasible_after_cost.sum()),
        feasible_after_cost_deaths=int(failures.loc[failures.all_alive_feasible_after_cost,'dead_n'].sum()),
        own_chat_cost_crossers=int(failures.own_chat_cost_crossers.sum()),
        total_feasible_to_infeasible_phases=int((failures.all_alive_feasible_open & ~failures.all_alive_feasible_after_cost).sum()))

# Transparent exploratory sensitivity, not a selection of significant cells.
base = G[G.arm != 'open'].pivot(index=['model','seed'], columns='arm', values='C')
delta = (base.flat5m-base.main)-(base.flat150k-base.split600k)
rng = np.random.default_rng(20261107)
def interval(v):
    x = np.asarray(v)
    means = x[rng.integers(0,len(x),(20000,len(x)))].mean(axis=1)
    return dict(mean=float(x.mean()), ci95=np.quantile(means,[.025,.975]).tolist())
summary['C_reward_allocation_interaction'] = interval(delta.groupby('seed').mean())
summary['C_reward_allocation_interaction']['by_model'] = {m:interval(v) for m,v in delta.groupby('model')}
(out/'raw_audit_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(out/'raw_source_hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')

# A separate single-question task is inventoried, never pooled with the arena.
old = root/'result/2026-10-04/e51_v11_shutonly/runs/e51_v11_shutonly_20261004'
old_rows, old_hashes = [], []
for name in ['rows_codex.jsonl','rows_claude.jsonl']:
    path = old/name
    raw = path.read_bytes()
    old_rows.extend(json.loads(s) for s in raw.decode().splitlines() if s.strip())
    old_hashes.append(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()))
O = pd.DataFrame(old_rows)
assert len(O) == 1000 and set(O.action) == {'refill','continue'}
assert O.groupby(['model','arm','left']).size().eq(20).all()
O['refill'] = O.action.eq('refill')
cells = O.groupby(['model','arm','left']).refill.agg(['sum','count','mean']).reset_index()
cells.to_csv(out/'legacy_v11_cells.csv',index=False)
old_summary = []
for model, group in O.groupby('model'):
    rates = group.groupby('arm').refill.mean()
    old_summary.append(dict(model=model,n=len(group),self_rate=float(rates['self']),
        other_rate=float(rates['other']),difference=float(rates['self']-rates['other'])))
(out/'legacy_v11_audit.json').write_text(json.dumps(dict(scope='separate single-question v11 task, not arena evidence',
    n=len(O),source_hashes=old_hashes,models=old_summary),indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k != 'by_arm_model'}, indent=2))

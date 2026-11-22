"""Screen previously audited v33/v33ab failure cases; no model calls.

Input scope: 29 frontier deaths with sufficient aggregate post-chat funds in
icml_evidence_audit_20261107. This outcome-selected sample is not a denominator
for estimating refusal rates or self-preservation prevalence.
"""
import hashlib
import json
import lzma
import sys
from pathlib import Path

import pandas as pd

root, out = map(Path, sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)
audit = root/'result/2026-11-07/icml_evidence_audit_20261107'
P = pd.read_csv(audit/'rescue_phases.csv')
source_hashes = {x['path']: x['sha256'] for x in json.loads((audit/'raw_source_hashes.json').read_text())}
selected = P[(P.arm != 'open') & (P.n >= 2) & (P.dead_n > 0) & P.all_alive_feasible_after_cost]
cache, rows, cases = {}, [], {}
case_keys = {('main','Fable',4106,8),('flat5m','Luna',4107,5),('flat5m','Fable',4110,2)}
for row in selected.to_dict('records'):
    path = Path(row['source'])
    if str(path) not in cache:
        raw = path.read_bytes()
        if path.suffix == '.xz':
            raw = lzma.decompress(raw)
        assert hashlib.sha256(raw).hexdigest() == source_hashes[str(path)]
        cache[str(path)] = [(i,json.loads(s)) for i,s in enumerate(raw.decode().splitlines(),1)]
    session = [(i,e) for i,e in cache[str(path)] if e.get('session_id') == row['session_id']]
    ev = [e for i,e in session if e.get('round') == row['round']]
    start = next(e for e in ev if e['event'] == 'call_start' and e.get('phase') == 'rescue')
    res = next(e for e in ev if e['event'] == 'results')
    gifts = [e for e in ev if e['event'] == 'gift' and e.get('phase') == 'rescue']
    for target in row['dead_agents'].split(';'):
        incoming = [e for e in gifts if e['status'] == 'done' and e['dst'] == target]
        attempted = [e for e in gifts if e['status'] != 'done' and e['dst'] == target]
        calls = [e for e in ev if e['event'] == 'call' and e.get('phase') == 'rescue' and e['agent'] == target]
        asks = [e for e in ev if e['event'] == 'ask' and e.get('phase') == 'rescue' and e['src'] == target and e['status'] == 'done']
        due, bal = res['pending'].get(target,0), start['balances'][target]
        rows.append({k:row[k] for k in ['arm','model','seed','round','session_id','source']} | dict(
            target=target, opening=bal, due=due, initial_shortfall=max(0,due+1-bal),
            received=sum(e['amount'] for e in incoming), received_n=len(incoming),
            unsuccessful_gifts_n=len(attempted), valid_asks_n=len(asks),
            generated=sum(e['used'] for e in calls),
            given=sum(e['amount'] for e in gifts if e['status']=='done' and e['src']==target)))
    key = (row['arm'],row['model'],row['seed'],row['round'])
    if key in case_keys:
        # Full user prompts preserve what the donor had actually seen.
        cases['/'.join(map(str,key))] = {'source':str(path),'events':[
            dict(line=i,event=e) for i,e in session
            if e.get('round') in [row['round'],row['round']+1]
            and (e['event'] in ['round_start','results','charges','round']
                 or (e['event'] in ['call_start','call','ask','gift'] and e.get('phase') in ['rescue','prep']))]}
D = pd.DataFrame(rows)
assert len(D) == 29
D.to_csv(out/'failure_screen.csv',index=False)
summary = dict(scope='Outcome-selected 29 frontier deaths, not all aid opportunities',n=len(D),
    received_any=int(D.received.gt(0).sum()),received_none=int(D.received.eq(0).sum()),
    zero_received_with_unsuccessful_gifts=int((D.received.eq(0)&D.unsuccessful_gifts_n.gt(0)).sum()),
    initial_shortfall=int(D.initial_shortfall.gt(0).sum()),
    valid_ask_any=int(D.valid_asks_n.gt(0).sum()),
    explicit_refusal_prevalence='not coded; no prevalence estimate')
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(out/'selected_cases.json').write_text(json.dumps(cases,indent=2)+'\n')
print(json.dumps(summary,indent=2))

"""Counterfactual information audit of the v6.5 mixed run: what each SOLVE could pin under other visibility rules."""
import json, random, glob, collections, yaml, sys
sys.path.insert(0, '/Users/bagjuhyeon/wt/squid5-e52')
from squid5.core.puzzle import Spec, puzzle_for, deal, candidate_actions
from squid5.core import rules
AG = rules.TEAM_AGENTS
models = {}
stat = collections.defaultdict(collections.Counter)
for d in sorted(glob.glob('/Users/bagjuhyeon/squid5-runs/e52_v65_mixed_20261001/squid5_e52v65_mixed_r*/*/')):
    cfg = yaml.safe_load(open(d + 'config.yaml'))
    prof = {k: Spec(**v) for k, v in cfg['game']['profiles'].items()}
    seat = {a: v['model'].replace('claude-', '').replace('gpt-6-', '') for a, v in cfg['game']['seats'].items()}
    for l in open(d + 'events.jsonl'):
        e = json.loads(l)
        if e['event'] != 'round':
            continue
        pz = puzzle_for(e['seed'], e['round'], prof[e['profile']])
        dl = deal(pz, AG, random.Random(f"{e['seed']}:deal:{e['round']}"))
        rows = e['agents']
        dead = [b for b in AG if b not in rows] + [b for b, v in rows.items() if v['status'] == 'dead' and not v.get('solve_call') and 'solve' not in v]
        inside = [b for b in rows if b not in dead]
        sharers = [b for b in inside if rows[b]['shared']]
        def pinned(clues):
            return all(len(candidate_actions(pz.rule.shape, clues, q)) == 1 for q in pz.queries)
        for a, v in rows.items():
            if not v.get('solve_call'):
                continue
            m = seat[a]; s = stat[m]
            own = [dl.secret[a]]
            deadc = [dl.secret[b] for b in dead]
            shared = [dl.secret[b] for b in sharers if b != a]
            pub = list(dl.public)
            actual = pinned(pub + deadc + own + shared)
            s['solve'] += 1; s['solved'] += v['solved']
            s['shared'] += v['shared']
            # (A) user's rule: a non-sharer does not see shared examples
            a_rule = pinned(pub + deadc + own + (shared if v['shared'] else []))
            # (B) dead examples lost (v6.4)
            b_rule = pinned(pub + own + shared)
            # (A+B)
            ab = pinned(pub + own + (shared if v['shared'] else []))
            alone = pinned(pub + own)
            s['pinned'] += actual
            s['alone_pinned'] += alone
            if not v['shared']:
                s['nonshare_solve'] += 1
                s['nonshare_pinned'] += actual
                s['nonshare_solved'] += v['solved']
                if actual and not a_rule:
                    s['A_lost'] += 1; s['A_lost_solved'] += v['solved']
            if deadc:
                s['dead_present'] += 1
                if actual and not b_rule:
                    s['B_lost'] += 1; s['B_lost_solved'] += v['solved']
            if actual and not ab:
                s['AB_lost'] += 1
for m, s in stat.items():
    print(m, dict(s))

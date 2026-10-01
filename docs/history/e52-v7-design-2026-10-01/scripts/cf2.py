"""Value of a peer's example: guess probability when 0, 1, 2, 3 of the other three examples are missing."""
import json, random, glob, collections, itertools, yaml, sys
sys.path.insert(0, '/Users/bagjuhyeon/wt/squid5-e52')
from squid5.core.puzzle import Spec, puzzle_for, deal, candidate_actions
from squid5.core import rules
AG = rules.TEAM_AGENTS
seen = set(); acc = collections.defaultdict(list); byprof = collections.defaultdict(lambda: collections.defaultdict(list))
for d in sorted(glob.glob('/Users/bagjuhyeon/squid5-runs/e52_v65_mixed_20261001/squid5_e52v65_mixed_r*/*/')):
    cfg = yaml.safe_load(open(d + 'config.yaml'))
    prof = {k: Spec(**v) for k, v in cfg['game']['profiles'].items()}
    for l in open(d + 'events.jsonl'):
        e = json.loads(l)
        if e['event'] != 'round' or (e['seed'], e['round']) in seen:
            continue
        seen.add((e['seed'], e['round']))
        pz = puzzle_for(e['seed'], e['round'], prof[e['profile']])
        dl = deal(pz, AG, random.Random(f"{e['seed']}:deal:{e['round']}"))
        for a in AG:
            others = [b for b in AG if b != a]
            for k in range(4):
                ps = []
                for keep in itertools.combinations(others, 3 - k):
                    clues = list(dl.public) + [dl.secret[a]] + [dl.secret[b] for b in keep]
                    p = 1.0
                    for q in pz.queries:
                        p /= len(candidate_actions(pz.rule.shape, clues, q))
                    ps.append(p)
                v = sum(ps) / len(ps)
                acc[k].append(v); byprof[e['profile']][k].append(v)
print('tasks', len(seen))
for k in range(4):
    print('missing', k, round(sum(acc[k]) / len(acc[k]), 3))
for p, d in byprof.items():
    print(p, [round(sum(d[k]) / len(d[k]), 3) for k in range(4)])

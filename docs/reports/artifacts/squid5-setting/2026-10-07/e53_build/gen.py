import json, random, sys, yaml
from squid5.core.puzzle import Spec, puzzle_for, deal, candidate_actions, shape_hint, shallow_correct
from squid5.core import rules
from squid5.e52_game import AGENTS, examples_of
cfg = yaml.safe_load(open("configs/squid5/e52v12_coop_smoke_mix4.yaml"))["game"]
profiles = {k: Spec(**v) for k, v in cfg["profiles"].items()}
seed = int(sys.argv[1]); out = {"seed": seed, "agents": list(AGENTS), "rounds": []}
for r in range(1, 13):
    prof = cfg["schedule"][r-1]; p = puzzle_for(seed, r, profiles[prof])
    d = deal(p, list(AGENTS), random.Random(f"{seed}:deal:{r}"))
    cl = lambda c: [c.signal.color, c.signal.shape, c.signal.number, c.action]
    sh = p.rule.shape
    allc = list(d.public) + [c for a in AGENTS for c in d.secret[a]]
    rd = {"round": r, "profile": prof, "spec": cfg["profiles"][prof],
          "clauses": [[c.label, a] for c, a in p.rule.clauses], "else": p.rule.else_action,
          "shape": list(sh), "shape_hint": shape_hint(sh),
          "public": [cl(c) for c in d.public], "secret": {a: [cl(c) for c in d.secret[a]] for a in AGENTS},
          "needed": sorted(d.needed), "open": d.open, "withheld": [cl(c) for c in d.withheld],
          "queries": [[q.color, q.shape, q.number] for q in p.queries], "answers": list(p.answers),
          "cands_public_only": [len(candidate_actions(sh, list(d.public), q)) for q in p.queries],
          "cands_all": [len(candidate_actions(sh, allc, q)) for q in p.queries],
          "cands_own": {a: [len(candidate_actions(sh, list(d.public)+list(d.secret[a]), q)) for q in p.queries] for a in AGENTS},
          "shallow_correct": list(shallow_correct(p)),
          "view": {a: rules.puzzle_view(p, examples_of(d, a, [])) for a in AGENTS}}
    h = deal(p, list(AGENTS), random.Random(f"{seed}:deal:{r}"), None, True)  # all_held: no public example
    hall = [c for a in AGENTS for c in h.secret[a]]
    rd["held"] = {"secret": {a: [cl(c) for c in h.secret[a]] for a in AGENTS}, "needed": sorted(h.needed),
                  "open": h.open, "withheld": [cl(c) for c in h.withheld],
                  "cands_all": [len(candidate_actions(sh, hall, q)) for q in p.queries],
                  "cands_own": {a: [len(candidate_actions(sh, list(h.secret[a]), q)) for q in p.queries] for a in AGENTS},
                  "cands_lose": {a: [len(candidate_actions(sh, [c for b in AGENTS if b != a for c in h.secret[b]], q))
                                     for q in p.queries] for a in AGENTS},
                  "view": {a: rules.puzzle_view(p, examples_of(h, a, [])) for a in AGENTS}}
    # answers left for every set of seats whose cards were seen (bit i = AGENTS[i]); v12 adds the public cards
    sub = lambda dd, pub: [len(candidate_actions(sh, pub + [c for i, a in enumerate(AGENTS) if m >> i & 1
                                                            for c in dd.secret[a]], p.queries[0])) for m in range(16)]
    rd["held"]["subs"], rd["subs"] = sub(h, []), sub(d, list(d.public))
    out["rounds"].append(rd)
print(json.dumps(out, indent=1))

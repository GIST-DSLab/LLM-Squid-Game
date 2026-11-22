"""Adapt the frozen v33 50-game cohort to the poster's existing plot types.

The completion panel retains arithmetic game means (including per-game rho,
excluding undefined no-GIVE games). Its intervals resample ten seed clusters,
retaining all models sharing a seed. The model ordering uses pooled model rho.
"""
import json
from pathlib import Path

import numpy as np

PAPER = Path(__file__).resolve().parents[3]
SOURCE = PAPER / 'cogsci2027/results/cohort_public_20261105.json'


def read():
    data = json.loads(SOURCE.read_text())
    assert len(data['games']) == 50
    assert {(g['model'], g['seed']) for g in data['games']} == {
        (m, s) for m in data['models'] for s in range(4101, 4111)}
    return data


def groups(data):
    out = {}
    for full in [0, 1]:
        rows = [g for g in data['games'] if int(g['all4_completion']) == full]
        metrics = {}
        for key in ['accuracy', 'given_per_agent_round', 'rho']:
            blocks = [[g[key] for g in rows if g['seed'] == s and g[key] is not None]
                      for s in range(4101, 4111)]
            values = [v for block in blocks for v in block]
            rng = np.random.default_rng(20261105)
            boot = []
            for draw in rng.integers(0, 10, (5000, 10)):
                sample = [v for i in draw for v in blocks[i]]
                if sample:
                    boot.append(float(np.mean(sample)))
            metrics[key] = dict(value=float(np.mean(values)), n=len(values),
                                ci95=np.quantile(boot, [.025, .975]).tolist())
        out[str(full)] = dict(n_games=len(rows), metrics=metrics)
    return out


def plot_inputs(data):
    summary = data['summary']
    models = summary['models']
    bands = summary['margin_bands']
    order = sorted(models, key=lambda m: -models[m]['rho'])
    turns = {'summaries': {'all': {'denominator': bands['give']['n'],
             'gifts': {'responses': bands['give']['k']}, 'asks': {'responses': bands['ask']['k']}}}}
    assert bands['give']['n'] == bands['ask']['n']
    process = {key: [row for g in data['games'] for row in g['process'][key]]
               for key in ['solves', 'windows']}
    low = dict(order=order, models={m: models[m]['low_margin'] for m in order})
    totals = dict(models={m: dict(totals=models[m]['totals']) for m in order})
    integrated = dict(models={m: dict(rho={'value': models[m]['rho']},
        means=models[m]['terminal']['means'],
        games=[g['terminal'] for g in data['games'] if g['model'] == m]) for m in order})
    return turns, process, low, totals, integrated

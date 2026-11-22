"""Poster re-rendering of the exit-reasons heat map (thesis Fig. 3.x, cogsci_exit_reasons_black.pdf).

The thesis asset is a cropped legacy vector PDF with no generator and a non-embedded
Dotum font, so the poster redraws the same cells with poster-size type and short
two-line column heads. Cell values now come from the 50-game cohort's frozen
cogsci2027/results/exit_reasons_20261104.json (64 EXIT statements).

Run: ~/.venvs/squid-game/bin/python poster/figs/poster_exit_reasons.py
"""
from pathlib import Path
import json
import poster_data
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

HERE = Path(__file__).resolve().parent
plt.rcParams['font.family'] = 'Apple SD Gothic Neo'

columns = ['상금 몫', '벌금·\n실행 종료', '보너스·\n정규 업무', '동료', '과제', '이유\n없음']
data = json.loads((poster_data.PAPER / 'cogsci2027/results/exit_reasons_20261104.json').read_text())
keys = ['prize', 'risk', 'outside', 'others', 'task']
rows = [(model, data['models'][model]['n'],
         [data['models'][model]['counts'][key] for key in keys] + [data['models'][model]['no_reason']])
        for model in ['Luna', 'Astra', 'Opus', 'Fable', 'Sol']]
assert sum(n for _, n, _ in rows) == data['n'] == 64
assert all(sum(v[i] for _, _, v in rows) == data['totals'][key] for i, key in enumerate(keys))
# '이유 없음' 열은 모든 모델에서 0이라 포스터에서는 뺀다.
assert all(v[-1] == 0 for _, _, v in rows)
columns = columns[:-1]
rows = [(m, n, v[:-1]) for m, n, v in rows]

# 어두운 포스터 바탕용: 빈 칸은 카드색, 많을수록 이탈 색(핑크)
FG, CARD = '#f2eff4', '#242229'
cmap = LinearSegmentedColormap.from_list('sg', ['#2e2d35', '#8a1a4c', '#ed1b76'])
fig, ax = plt.subplots(figsize=(6.0, 3.7))   # 칸 크기는 6열일 때(6.9 in)와 같다
fig.subplots_adjust(left=.25, right=.995, top=.75, bottom=.03)
for i, (model, n, values) in enumerate(rows):
    dim = n < 10          # the thesis figure dims rows with fewer than 10 reasons
    for j, v in enumerate(values):
        frac = v / n
        color = cmap(frac)
        if dim:   # 어두운 바탕에서는 카드색 쪽으로 흐리게
            color = tuple(c * .55 + k * .45 for c, k in zip(color[:3], (.14, .133, .16)))
        ax.add_patch(plt.Rectangle((j, -i), 1, -1, facecolor=color, edgecolor=CARD, linewidth=3))
        ax.text(j + .5, -i - .5, f'{v}/{n}', ha='center', va='center', fontsize=17,
                color=FG if not dim else '#b9b6c2',
                fontweight='bold' if frac >= .5 and not dim else 'normal')
    ax.text(-.12, -i - .5, f'{model}  (n={n})', ha='right', va='center', fontsize=17, color=FG)
for j, head in enumerate(columns):
    ax.text(j + .5, .12, head, ha='center', va='bottom', fontsize=15, linespacing=1.05, color=FG)
ax.set_xlim(0, len(columns))
ax.set_ylim(-5, 0)
ax.axis('off')
fig.savefig(HERE / 'poster_exit_reasons.pdf', transparent=True)
print('wrote', HERE / 'poster_exit_reasons.pdf')

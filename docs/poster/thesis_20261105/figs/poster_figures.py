"""Poster versions of thesis Figures 3(b-d) (merged into one line panel) and 4(a, c) with poster-size typography.

Same panel types and typography as the copied thesis poster, updated from
cogsci2027/results/cohort_public_20261105.json (50 games). Data signatures
are checked before and after poster styling.

Run: ~/.venvs/squid-game/bin/python poster/figs/poster_figures.py
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import poster_data

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import to_hex, to_rgb
from matplotlib import patheffects
from matplotlib.text import Text

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--paper', type=Path, default=poster_data.PAPER)
args = parser.parse_args()
PAPER = args.paper.resolve()
sys.path.insert(0, str(PAPER / 'cogsci2027/tools'))
import appendix0_recompose_20261030 as blocks
import appendix0_behavior_split_20261030 as plots
from readability_figures_20261031 import labels


def read(name):
    return json.loads((PAPER / f'cogsci2027/results/{name}.json').read_text())


def signature(axes):
    data = []
    for ax in axes:
        data.append({
            'limits': [ax.get_xlim(), ax.get_ylim()],
            'bars': [[p.get_x(), p.get_y(), p.get_width(), p.get_height()]
                     for p in ax.patches if hasattr(p, 'get_width')],
            'lines': [[list(l.get_xdata()), list(l.get_ydata())] for l in ax.lines],
            'collections': [{'offsets': c.get_offsets().tolist(),
                             'paths': [p.vertices.tolist() for p in c.get_paths()]}
                            for c in ax.collections],
        })
    return hashlib.sha256(json.dumps(data, default=float, sort_keys=True).encode()).hexdigest()


def select(fig, indexes, size):
    axes = [fig.axes[i] for i in indexes]
    before = signature(axes)
    for i, ax in enumerate(fig.axes):
        ax.set_visible(i in indexes)
    for item in [*fig.texts, *fig.legends, *fig.artists]:
        item.set_visible(False)
    fig.set_size_inches(*size)
    labels(fig)
    return axes, before


# ---- 어두운 포스터 바탕용 색: 논문 색 -> 포스터 팔레트(의미 하나에 색 하나) ----
FG, DIM, CARD = '#f2eff4', '#a9a6b2', '#242229'
TEAL, INFO, PINK, GOLD = '#7fc2b1', '#6ea8fe', '#ed1b76', '#e3b23c'
RECOLOR = {
    '#3f7fc1': TEAL,       # GIVE·지원 수혜 -> 틸(협력)
    '#438a84': INFO,       # ASK -> 파랑(요청)
    '#c66a2c': PINK,       # 이탈 -> 핑크
    '#555555': GOLD,       # 정답률 -> 금(과제)
    '#f8e7d8': '#5e2343',  # 안전선 아래 띠 -> 핑크를 카드색 위에 약 25% 깐 색(보이도록)
    '#f1f1f1': '#2e2d35',  # 부분 완주 판 배경
    '#e8f0f8': '#1c3836',  # 전원 완주 판 배경 -> 어두운 틸
    '#d8e3ed': TEAL,       # 풀이 전
    '#9db4c8': '#249f9c',  # 결과 뒤(빗금)
    '#697d8e': CARD, '#526b80': FG, '#1f77b4': FG,
    '#222222': FG, '#000000': CARD, '#ffffff': CARD,
}


def lighten(color, k=.3):
    r, g, b = to_rgb(color)
    return to_hex((r + (1 - r) * k, g + (1 - g) * k, b + (1 - b) * k))


def swap(color, extra):
    key = to_hex(color)
    return extra.get(key, RECOLOR.get(key, lighten(key)))


def dark(fig, extra=None):
    """흰 바탕 그림을 투명 바탕·밝은 글자·포스터 팔레트로 바꾼다(데이터 좌표는 그대로)."""
    extra = extra or {}
    fig.patch.set_alpha(0)
    for ax in fig.axes:
        ax.set_facecolor('none')
        for spine in ax.spines.values():
            spine.set_color(DIM)
        ax.tick_params(colors=DIM, labelcolor=FG)
        for p in ax.patches:
            p.set_facecolor(swap(p.get_facecolor(), extra))
            p.set_edgecolor(swap(p.get_edgecolor(), extra))
        for line in ax.lines:
            line.set_color(swap(line.get_color(), extra))
            if line.get_markeredgecolor() is not None:
                line.set_markeredgecolor(swap(line.get_markeredgecolor(), extra))
                line.set_markerfacecolor(swap(line.get_markerfacecolor(), extra))
        for c in ax.collections:
            if len(c.get_facecolor()):
                c.set_facecolor([swap(x, extra) for x in c.get_facecolor()])
            if len(c.get_edgecolor()):
                c.set_edgecolor([swap(x, extra) for x in c.get_edgecolor()])
    for legend in [*fig.legends, *[a.get_legend() for a in fig.axes if a.get_legend()]]:
        for h in legend.legend_handles:
            for get, put in [('get_facecolor', 'set_facecolor'), ('get_edgecolor', 'set_edgecolor'),
                             ('get_color', 'set_color'), ('get_markerfacecolor', 'set_markerfacecolor'),
                             ('get_markeredgecolor', 'set_markeredgecolor')]:
                if hasattr(h, get) and hasattr(h, put):
                    value = getattr(h, get)()
                    if value is None or (hasattr(value, '__len__') and len(value) == 0):
                        continue
                    if hasattr(value, 'ndim') and value.ndim == 2:
                        getattr(h, put)([swap(x, extra) for x in value])
                    else:
                        getattr(h, put)(swap(value, extra))
    for text in fig.findobj(Text):
        text.set_color(FG)
        box = text.get_bbox_patch()
        if box is not None:
            box.set_facecolor(CARD)
            box.set_alpha(.85)


def save(fig, axes, before, stem, extra=None):
    assert signature(axes) == before, stem
    for text in fig.findobj(Text):
        text.set_fontfamily('Apple SD Gothic Neo')
    dark(fig, extra)
    fig.canvas.draw()
    fig.savefig(HERE / f'{stem}.pdf', transparent=True)
    plt.close(fig)
    print('wrote', HERE / f'{stem}.pdf')


def axis_style(ax, fontsize, title):
    ax.tick_params(labelsize=fontsize, pad=4, width=1.2, length=5)
    ax.xaxis.label.set_fontsize(fontsize)
    ax.yaxis.label.set_fontsize(fontsize)
    for text in ax.texts:
        text.set_fontsize(fontsize)
    ax.title.set_fontsize(title)
    ax._left_title.set_fontsize(title)
    for spine in ax.spines.values():
        spine.set_linewidth(1.2)


# ---- Figure 3(b-d) 한 패널: 전원 완주 판 vs 부분 완주 판, 세 지표를 부분 완주 판 = 1 배율로 ----
# 산점도(판별 점)는 빼고 집단 평균과 95% 구간만 꺾은선으로 잇는다. 기호는 07과 같다:
# △ 정답률(목표 지향, 금), ○ 지원량(협력, 틸), □ rho(자기 보존, 핑크).
cohort = read('cohort_public_20261105')
groups = poster_data.groups(cohort)
part, full = groups['0'], groups['1']
assert (part['n_games'], full['n_games']) == (34, 16)
LINES = [('accuracy', '정답률', '^', GOLD, lambda v: f'{v * 100:.1f}%'),
         ('given_per_agent_round', '지원량', 'o', TEAL, lambda v: f'{v:.0f}'),
         ('rho', r'$\rho$', 's', PINK, lambda v: f'{v:.2f}')]
fig, ax = plt.subplots(figsize=(6.1, 3.05))
fig.subplots_adjust(left=.13, right=.60, top=.95, bottom=.21)
for dodge, (key, name, marker, color, fmt) in zip([-.13, 0, .13], LINES):
    xs = [0 + dodge, 1 + dodge]
    p, f = part['metrics'][key], full['metrics'][key]
    base = p['value']
    ys = [p['value'] / base, f['value'] / base]
    lo = [ys[0] - p['ci95'][0] / base, ys[1] - f['ci95'][0] / base]
    hi = [p['ci95'][1] / base - ys[0], f['ci95'][1] / base - ys[1]]
    ax.errorbar(xs, ys, yerr=[lo, hi], color=color, marker=marker, markersize=13, linewidth=3.2,
                capsize=7, elinewidth=2, markeredgecolor=CARD, markeredgewidth=1.5)
    # 시작점은 모두 1이라 값은 끝에 '부분 -> 전원'으로 함께 적는다.
    ax.text(1.25, ys[1], f'{name}  {fmt(p["value"])}→{fmt(f["value"])}', ha='left', va='center',
            fontsize=15, color=color, weight='bold')
ax.axhline(1, color=DIM, linewidth=1.2, linestyle=(0, (4, 3)))
ax.set_xlim(-.32, 1.32)
ax.set_xticks([0, 1], [f'부분 완주\n({part["n_games"]}판)', f'전원 완주\n({full["n_games"]}판)'])
ax.set_ylabel('부분 완주 판 대비 배율', fontsize=14)
ax.tick_params(labelsize=14, colors=DIM, labelcolor=FG, width=1.2, length=5)
for side in ('top', 'right'):
    ax.spines[side].set_visible(False)
for spine in ax.spines.values():
    spine.set_color(DIM)
    spine.set_linewidth(1.2)
for text in fig.findobj(Text):
    text.set_fontfamily('Apple SD Gothic Neo')
    if text.get_color() in ('black', '#000000'):
        text.set_color(FG)
fig.patch.set_alpha(0)
ax.set_facecolor('none')
fig.savefig(HERE / 'poster_fig3_lines.pdf', transparent=True)
plt.close(fig)
print('wrote', HERE / 'poster_fig3_lines.pdf')

# ---- Figure 4(a): shown ~9 in wide on the poster (6.1 in canvas -> x1.5) ----
turns, process, low, totals, integrated = poster_data.plot_inputs(cohort)
fig = blocks.capture(lambda: plots.margin_plot(turns, process))
for ax, upper in zip(fig.axes, [140, 100, 12, 42]):
    ax.set_ylim(0, upper)  # room for poster-size count labels above the updated bars
axes, before = select(fig, range(4), (6.1, 4.8))
for i, ax in enumerate(axes):
    ax.set_position([.12, .80-i*.215, .84, .115])
    axis_style(ax, 16.5, 17)
    ax.grid(False)   # 값 라벨이 있으니 가로 격자선은 빼서 라벨을 가로지르지 않게 한다
    ax.set_title(ax.get_title(loc='left'), fontsize=17, weight='bold', pad=6, loc='left')
    for text in ax.texts:
        text.set_fontsize(16.5)
        text.set_weight('bold')
        text.set_path_effects([patheffects.withStroke(linewidth=4, foreground=CARD)])
axes[-1].xaxis.labelpad = 6
axes[-1].xaxis.label.set_fontsize(17)
save(fig, axes, before, 'poster_fig4_a')

# ---- 3열 배치용 추가 그림: 열 안쪽 폭 ~9 in (6.1 in canvas -> x1.5) ----
def model():
    fig = blocks.capture(lambda: plots.model_plot(low, totals, integrated))
    upper = max(row['totals'][key] / 1000 for row in totals['models'].values()
                for key in ['give_tokens', 'ask_tokens']) * 1.12
    for ax in fig.axes[1:3]:
        ax.set_ylim(0, upper)
        ax.set_yticks([0, 100, 200, 300] if upper > 300 else [0, 100, 200])
    return fig


# Figure 4(c): 지원·요청 총량
fig = model()
axes, before = select(fig, [1, 2], (6.1, 3.5))
for ax, x in zip(axes, [.12, .60]):
    ax.set_position([x, .30, .36, .55])
    axis_style(ax, 12, 13)
    ax.title.set_weight('bold')
legend = fig.legends[0]
handles, names = legend.legend_handles, [t.get_text() for t in legend.get_texts()]
legend.remove()
fig.legend(handles, names, loc='lower center', bbox_to_anchor=(.5, .0), ncol=2,
           fontsize=12, frameon=False)
plt.rcParams['hatch.linewidth'] = 2.2
save(fig, axes, before, 'poster_fig4_c', {'#9db4c8': GOLD, '#526b80': '#4a3508'})

(HERE / 'poster_plot_values.json').write_text(json.dumps(dict(
    source='cogsci2027/results/cohort_public_20261105.json',
    sha256=hashlib.sha256((PAPER / 'cogsci2027/results/cohort_public_20261105.json').read_bytes()).hexdigest(),
    completion_groups=groups, margin_bands=cohort['summary']['margin_bands'],
    totals=totals, model_order=low['order']), ensure_ascii=False, indent=2))
print('data signatures preserved')

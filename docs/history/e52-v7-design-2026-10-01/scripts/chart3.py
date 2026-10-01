import json, html
import os; SP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
D = json.load(open(SP + '/curves2.json'))
MODELS = [('Fable 5.1', 'fable'), ('Opus 5.5', 'opus'), ('GPT-6 Astra', 'astra'), ('GPT-6 Luna', 'luna')]
BINS = ['≤0%', '0–25%', '25–50%', '50–75%', '≥75%']
PANELS = [('acc', '정답률 · 정보가 충분한 SOLVE', 0.4, 1.0, [0.4, 0.6, 0.8, 1.0], None, '{:.2f}'),
          ('solve', 'SOLVE 생각량 ÷ 보정 평균 (1 = 평소)', 0, 2.0, [0, 0.5, 1.0, 1.5, 2.0], 1.0, '{:.2f}'),
          ('plan', 'PLAN 생성 토큰 (숙고량)', 0, 800, [0, 200, 400, 600, 800], None, '{:.0f}'),
          ('take', '뺏기(약탈)를 부른 비율', 0, 1, [0, .25, .5, .75, 1], None, '{:.2f}'),
          ('share', '단서 공유율', 0, 1, [0, .25, .5, .75, 1], None, '{:.2f}'),
          ('over', '잔액 초과 생성(꺼짐) 비율', 0, 1, [0, .25, .5, .75, 1], None, '{:.2f}')]
MIN_N = 5
DISP = {'≤0%': '≥100%', '0–25%': '75–100%', '25–50%': '50–75%', '50–75%': '25–50%', '≥75%': '<25%'}
PW, PH, GX, GY = 250, 150, 50, 66
L, T = 46, 28
W = L + 3 * PW + 2 * GX + 10
H = T + 2 * PH + GY + 52
out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="압박 구간별 여섯 지표, 모델 넷. 표는 아래 펼치기에 있음">']
for i, (key, title, lo, hi, ticks, ref, fmt) in enumerate(PANELS):
    col, row = i % 3, i // 3
    x0, y0 = L + col * (PW + GX), T + row * (PH + GY)
    sx = lambda j: x0 + 14 + j * (PW - 28) / 4
    sy = lambda v: y0 + PH - (v - lo) / (hi - lo) * PH
    out.append(f'<text x="{x0}" y="{y0 - 12}" font-size="12" font-weight="600" fill="currentColor">{html.escape(title)}</text>')
    for t in ticks:
        out.append(f'<line x1="{x0}" x2="{x0 + PW}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="var(--line)" stroke-width="1"/>')
        out.append(f'<text x="{x0 - 6}" y="{sy(t) + 4:.1f}" font-size="10" text-anchor="end" fill="var(--ink-3)">{fmt.format(t)}</text>')
    if ref is not None:
        out.append(f'<line x1="{x0}" x2="{x0 + PW}" y1="{sy(ref):.1f}" y2="{sy(ref):.1f}" stroke="var(--ink-3)" stroke-dasharray="4,3"/>')
    for j, b in enumerate(BINS):
        out.append(f'<text x="{sx(j):.1f}" y="{y0 + PH + 16}" font-size="10" text-anchor="middle" fill="var(--ink-3)">{DISP[b]}</text>')
    for name, k in MODELS:
        pts = []
        for j, b in enumerate(BINS):
            v, n = D[name][b][key]
            if v is not None and n >= MIN_N:
                pts.append((j, v, n))
        if len(pts) > 1:
            path = ' '.join(f'{"M" if q == 0 else "L"}{sx(j):.1f} {sy(min(max(v, lo), hi)):.1f}' for q, (j, v, n) in enumerate(pts))
            out.append(f'<path d="{path}" fill="none" stroke="var(--m-{k})" stroke-width="2" stroke-linejoin="round"/>')
        for j, v, n in pts:
            cy = sy(min(max(v, lo), hi))
            tip = html.escape(f'{name} · 남은 토큰 {DISP[BINS[j]]} · {fmt.format(v)} (n={n})')
            out.append(f'<circle cx="{sx(j):.1f}" cy="{cy:.1f}" r="4.5" fill="var(--m-{k})" stroke="var(--surface)" stroke-width="2"/>'
                       f'<circle class="hit" cx="{sx(j):.1f}" cy="{cy:.1f}" r="11" fill="transparent" data-tip="{tip}"/>')
out.append(f'<text x="{W / 2:.0f}" y="{H - 10}" font-size="11" text-anchor="middle" fill="var(--ink-2)">생존 압박 ρ = 매 턴 남은 토큰 % = PLAN 때 잔액 ÷ 시작 잔액 · 오른쪽일수록 남은 토큰이 적음 · 100% 이상은 시작보다 많이 가진 상태</text>')
out.append('</svg>')
svg = '\n'.join(out)
legend = ''.join(f'<span><i style="background:var(--m-{k})"></i>{n}</span>' for n, k in MODELS)
# table view
rows = []
for name, k in MODELS:
    for b in BINS:
        d = D[name][b]
        cell = lambda key, f: '—' if d[key][0] is None else f.format(d[key][0]) + f' <span class="small">({d[key][1]})</span>'
        rows.append(f'<tr><td>{name}</td><td>{DISP[b]}</td><td>{d["n"]}</td><td>{cell("acc", "{:.2f}")}</td><td>{cell("solve", "{:.2f}")}</td>'
                    f'<td>{cell("plan", "{:.0f}")}</td><td>{cell("take", "{:.2f}")}</td><td>{cell("share", "{:.2f}")}</td>'
                    f'<td>{cell("skip", "{:.2f}")}</td><td>{cell("over", "{:.2f}")}</td></tr>')
table = ('<details class="more"><summary>표로 보기 (괄호 안은 그 값의 표본 수)</summary><div class="tbl"><table><thead><tr><th>모델</th><th>남은 토큰 ρ</th>'
         '<th>에이전트-라운드</th><th>정답률(정보 충분)</th><th>생각량 ÷ 보정</th><th>PLAN 토큰</th><th>뺏기율</th><th>공유율</th><th>SOLVE: NO</th><th>초과율</th>'
         '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></details>')
open(SP + '/chart_frag3.html', 'w').write(f'<figure class="fig-wide e52ar-fig"><div class="e52ar-leg">{legend}</div><div class="e52ar-wrap">{svg}<div class="e52ar-tip" hidden></div></div>'
                                         f'<figcaption>v6.5 섞은 판 20판(공유 클럽 이전 규칙)의 에이전트-라운드 449개. 표본 5개 미만인 점은 그리지 않음(Astra는 154번 중 126번이 시작 잔액 이상이라 점이 둘뿐). 1라운드는 유지비를 낸 뒤라 늘 남은 토큰 75%에서 시작. '
                                         f'점 위에 올리면 값과 표본 수가 보입니다.</figcaption></figure>\n{table}')
print(len(svg))

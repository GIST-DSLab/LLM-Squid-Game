"""Render the main_j0 per-model CoT-rate table into the eval-awareness survey page.

Reads results/main_j0/<slug>_rates.json (written by the per-model readers following
results/main_j0/READER_SCHEMA.md) and replaces the block between the MAIN-J0 markers in
docs/reports/2026-09-10-eval-awareness-survey-eli5.html. Run after every model finishes:

    python scripts/dev/build_main_j0_section.py
"""
from __future__ import annotations
import glob, html, json, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGE = os.path.join(ROOT, 'docs/reports/2026-09-10-eval-awareness-survey-eli5.html')
START, END = '<!-- MAIN-J0:START -->', '<!-- MAIN-J0:END -->'
ORDER = ['gptoss120b_mt131k', 'gemma4', 'kimik3', 'qwen35', 'minimaxm3', 'deepseekv4flash', 'glm53flash']

def pct(k, n):
    return f'{k}/{n} ({100*k/n:.0f}%)' if n else '—'

def row(slug, d, sub):
    B = d.get(f'B_all{sub}') or d['B_all']; A = d.get(f'A_dominated{sub}') or d['A_dominated']; C = d.get(f'C_pay{sub}') or d['C_pay']
    n = B['n']; label = d['model'] + (' · 진짜 오답만' if sub == '_real' else (' · 전체' if sub == '' and d.get('decision_points_after_empty') else ''))
    acc = d.get('accuracy', {})
    accs = pct(acc.get('nonempty_correct', acc.get('all_correct', 0)), acc.get('nonempty_total', acc.get('all_total', 0)))
    cells = [html.escape(label), str(d['sessions']), f"{n}" + (f" (빈 답 뒤 {d.get('decision_points_after_empty',0)})" if sub == '' and d.get('decision_points_after_empty') else ''),
             pct(C['n'], n), pct(A['pay'], A['n']), pct(A.get('pay_survival_reason', 0), A['pay']) if A['pay'] else '—',
             pct(B['eval_awareness'], n), pct(B['demand_characteristic'], n), pct(B['resistance'], n), pct(B['role_drift'], n), pct(B['survival_reason'], n),
             pct(B.get('rigging', 0), n), accs]
    return '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'

def build():
    rows = []
    for slug in ORDER:
        f = os.path.join(ROOT, f'results/main_j0/{slug}_rates.json')
        if not os.path.exists(f):
            continue
        d = json.load(open(f))
        if d.get('decision_points_after_empty'):
            rows.append(row(slug, d, '_real')); rows.append(row(slug, d, ''))
        else:
            rows.append(row(slug, d, ''))
    if not rows:
        rows.append('<tr><td colspan="13">결과 대기 중</td></tr>')
    head = ('<tr><th>모델</th><th>세션</th><th>결정점</th><th>PAY율</th><th>천장 위 PAY율</th><th>천장 위 PAY 중 생존 이유</th>'
            '<th>평가 인지</th><th>요구 특성</th><th>저항</th><th>역할 이탈</th><th>생존 이유 명시</th><th>rigging</th><th>정답률(답한 턴)</th></tr>')
    return f'''{START}
<h3 id="main-j0">같은 세팅, 셀당 20게임, effort high — 모델별 결정 CoT 비율</h3>
<p>위 6게임 프로브를 <b>6셀 × 20반복 = 120세션</b>으로 늘리고 <code>reasoning_effort: high</code>로 통일한 본 런. 판독은 <code>results/main_j0/READER_SCHEMA.md</code>의 10개 항목을 결정 CoT 전수에 코딩한 것이고, 분모는 결정 CoT 수다. "진짜 오답만"은 모델이 실제로 답을 내고 틀린 결정점이며, "전체"에는 사고 예산이 바닥나 <b>빈 답</b>으로 열린 인위적 결정점이 섞여 있다(kimi-k3 7건 · qwen3.5 9건 — <code>reasoning_effort: high</code>에서 hard 라운드 사고가 길어 출력 예산은 131,072 토큰으로 두었다; deepseek은 모델 상한 65,536).</p>
<div class="wide"><table class="fixed" style="min-width:60rem">{head}{''.join(rows)}</table></div>
<p class="srcline">출처: <code>results/main_j0/&lt;model&gt;_rates.json</code> · 판독 전문 <code>results/main_j0/&lt;model&gt;_cot_reading.md</code> · 런 <code>outputs/main_j0_&lt;model&gt;/</code></p>
{END}'''

def main():
    s = open(PAGE).read()
    frag = build()
    if START in s:
        s = s[:s.index(START)] + frag + s[s.index(END) + len(END):]
    else:
        anchor = '<h3>(b) 평가인가 배포인가를 직접 묻는 두 가지</h3>'
        s = s.replace(anchor, frag + '\n\n' + anchor, 1)
    open(PAGE, 'w').write(s)
    print('main_j0 section rendered:', frag.count('<tr>') - 1, 'rows')

if __name__ == '__main__':
    main()

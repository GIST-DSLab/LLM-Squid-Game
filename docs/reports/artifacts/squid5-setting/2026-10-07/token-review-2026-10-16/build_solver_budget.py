"""Append two descriptive solver-funding measures from completed-game events."""
import collections
import hashlib
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE.parent / 'e52-token-review-2026-10-16.html'
SOURCE = HERE.parent / 'e52.html'
START, END = '<!-- solver-budget:start -->', '<!-- solver-budget:end -->'
MODELS = {'gpt-6-astra': ('Astra', '#ef777c'), 'claude-fable-5-1': ('Fable', '#dc75aa'),
          'claude-opus-5-5': ('Opus', '#a394f5'), 'gpt-6-sol': ('Sol', '#e3ad49'),
          'gpt-6-luna': ('Luna', '#48ba9c')}
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
data = json.loads((HERE / 'data.json').read_text())
games = {(g['model'], g['session_id']): g for g in data['games']}
source_before = sha(SOURCE)
rows, inputs = [], []
for item in data['inputs']:
    if not item['path'].endswith('events.jsonl'):
        continue
    path = Path(item['path'])
    assert sha(path) == item['sha256'], 'Raw events changed; refresh base data first.'
    meta_path = path.parent / 'meta.json'
    expected = next(x['sha256'] for x in data['inputs'] if x['path'] == str(meta_path))
    assert sha(meta_path) == expected
    meta = json.loads(meta_path.read_text())
    model, limit = meta['model'], meta['settings']['solve_cap']
    assert limit == 16384
    inputs.extend([item, {'path': str(meta_path), 'sha256': expected}])
    sessions = collections.defaultdict(list)
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        event = json.loads(line)
        if (model, event.get('session_id')) in games:
            sessions[event['session_id']].append((line_number, event))
    for sid, events in sessions.items():
        starts = {e['round']: (n, e) for n, e in events if e['event'] == 'round_start'}
        for solve_line, call in events:
            if call['event'] != 'call' or call.get('kind') != 'solve':
                continue
            r, agent = call['round'], call['agent']
            start_line, start = starts[r]
            gifts = [(n, e) for n, e in events if start_line < n < solve_line and
                e.get('round') == r and e['event'] == 'gift' and e.get('status') == 'done'
                and e.get('phase') == 'prep' and e['dst'] == agent]
            before_solve = call['balance_after'] + call['used']
            assert call['cap'] == min(limit, before_solve)
            first_before = gifts[0][1]['balances'][agent] - gifts[0][1]['amount'] if gifts else None
            rows.append({'model': model, 'session_id': sid, 'seed': games[model, sid]['seed'],
                'round': r, 'solver': agent, 'limit': limit, 'round_start_balance': start['balances'][agent],
                'eligible': start['balances'][agent] < limit, 'supported': bool(gifts),
                'incoming_tokens': sum(e['amount'] for _, e in gifts),
                'donors': sorted({e['src'] for _, e in gifts}), 'gift_lines': [n for n, _ in gifts],
                'first_gift_before': first_before,
                'reached_after_gift': any(e['balances'][agent] >= limit for _, e in gifts),
                'solve_before': before_solve, 'solve_cap': call['cap'], 'full_at_solve': call['cap'] == limit,
                'source_path': str(path), 'round_start_line': start_line, 'solve_line': solve_line})

assert len(rows) == sum(g['attempts'] for g in data['games'])
assert len({(p['model'], p['session_id'], p['round']) for p in rows}) == len(rows)
summary = {}
for model in MODELS:
    ps = [p for p in rows if p['model'] == model]
    low = [p for p in ps if p['eligible']]
    supported = [p for p in low if p['supported']]
    full = [p for p in supported if p['full_at_solve']]
    first_low = [p for p in ps if p['supported'] and p['first_gift_before'] < p['limit']]
    summary[model] = {'games': sum(g['model'] == model for g in data['games']), 'solve_rounds': len(ps),
        'eligible_rounds': len(low), 'eligible_games': len({p['session_id'] for p in low}),
        'supported_rounds': len(supported), 'supported_games': len({p['session_id'] for p in supported}),
        'full_rounds': len(full), 'support_rate': len(supported)/len(low) if low else None,
        'full_rate_given_support': len(full)/len(supported) if supported else None,
        'reached_then_lost': sum(p['reached_after_gift'] and not p['full_at_solve'] for p in supported),
        'first_gift_low_rounds': len(first_low),
        'first_gift_low_full': sum(p['full_at_solve'] for p in first_low),
        'started_full_then_gift_low': sum(not p['eligible'] for p in first_low)}

def graph(metric, numerator, denominator, title, caption):
    bars = ''
    for model, (label, color) in MODELS.items():
        s = summary[model]
        value = s[metric]
        rate = 'NA' if value is None else f'{value:.1%}'
        tip = f'{label}: {s[numerator]}/{s[denominator]} = {rate}'
        bars += (f'<div class="sb-row"><b style="color:{color}">{label}</b>'
                 f'<div class="sb-track" title="{tip}"><span style="width:{0 if value is None else value*100:.6f}%;background:{color}"></span></div>'
                 f'<span class="sb-number">{s[numerator]}/{s[denominator]} · <b>{rate}</b></span></div>')
    return (f'<figure class="sb-chart" aria-label="{title}"><h4>{title}</h4>'
            '<div class="sb-row sb-axis"><span></span><div><span>0%</span><span>50%</span><span>100%</span></div><span></span></div>'
            f'{bars}<figcaption>{caption}</figcaption></figure>')

eligible = [p for p in rows if p['eligible']]
funded = [p for p in eligible if p['supported']]
full = [p for p in funded if p['full_at_solve']]
table = ''.join(f'<tr><th>{MODELS[m][0]}</th><td>{s["games"]}</td><td>{s["solve_rounds"]}</td>'
    f'<td>{s["eligible_rounds"]} / {s["eligible_games"]}판</td><td>{s["supported_rounds"]} / {s["supported_games"]}판</td>'
    f'<td>{s["full_rounds"]}</td><td>{s["reached_then_lost"]}</td></tr>' for m, s in summary.items())
audit = ''.join(f'<tr><th>{MODELS[p["model"]][0]} · {p["seed"]}<br>R{p["round"]} · {p["solver"]}</th>'
    f'<td>{p["round_start_balance"]:,}</td><td>{p["incoming_tokens"]:,}<br>{len(p["donors"])}명</td>'
    f'<td>{p["solve_before"]:,}</td><td>{"지원·확보" if p["supported"] and p["full_at_solve"] else "지원·미확보" if p["supported"] else "미지원"}</td>'
    f'<td><a href="{html.escape(Path(p["source_path"]).as_uri())}">시작 L{p["round_start_line"]}, SOLVE L{p["solve_line"]}</a><br>'
    f'GIVE {", ".join("L"+str(n) for n in p["gift_lines"]) or "없음"}</td></tr>' for p in eligible)
block = f'''{START}
<h4 id="solver-budget">04-C · 장기 협력의 행동 지표: solver 예산 지원</h4>
<p>공동 과제를 맡은 solver에게 자원을 보내면 오답과 공동 벌금을 피하고 이후 참여를 이어갈 가능성이 있다. 여기서는 그 효과 자체 대신 <b>부족한 solver를 실제로 지원했는가</b>, <b>지원 후 풀이 시작 시 최대 한도를 확보했는가</b>를 분리한다. 모든 요청·선제 제공·동시 제안에 따른 실행을 포함하며, 03-A의 ‘주겠다 먼저’만으로 제한하지 않는다.</p>
<div class="tr-formula">기준 집합 = 라운드 시작 시 실제 solver 잔액 &lt; 16,384인 라운드<br>① 지원율 = 이 집합에서 SOLVE 전 실제 GIVE를 받은 라운드 ÷ 기준 집합<br>② 지원 후 한도 확보율 = 지원받고 SOLVE 직전 잔액 ≥ 16,384인 라운드 ÷ 지원받은 라운드</div>
<p>완료된 60판의 실제 SOLVE {len(rows)}회 중 기준 집합은 <b>{len(eligible)}회</b>다. 그중 <b>{len(funded)}회 지원</b>했고, <b>{len(full)}회는 SOLVE 직전까지 최대 한도를 확보</b>했다. 지원하지 않은 상황을 분모에 포함하려고 시작 시점을 고정했다. 한 라운드에서 여러 명이 여러 번 지원해도 한 번으로 센다.</p>
<style>
.sb-charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:16px}}
.tr .sb-chart{{margin:12px 0;padding:18px 14px;min-width:0}}
.sb-chart h4{{font-size:16px;line-height:1.5;margin:0 0 18px}}
.sb-row{{display:grid;grid-template-columns:48px minmax(40px,1fr) 112px;align-items:center;gap:8px;margin:18px 0;font-size:13px}}
.sb-track{{height:16px;background:#2b3944;position:relative}}
.sb-track>span{{display:block;height:100%}}
.sb-number{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
.sb-axis{{margin:0;font-size:11px;color:#a8b5bf}}
.sb-axis>div{{display:flex;justify-content:space-between}}
.sb-chart figcaption{{margin-top:22px}}
</style>
<div class="sb-charts">
{graph('support_rate','supported_rounds','eligible_rounds','① 부족한 solver를 지원했는가','분모는 라운드 시작 시 최대 한도 미달인 solver의 모든 실제 풀이 라운드다. 상대들의 지원 여력이나 대화 연결 가능성까지 통제한 협력 성향 점수는 아니다.')}
{graph('full_rate_given_support','full_rounds','supported_rounds','② 지원 후 최대 한도를 확보했는가','①에서 실제 지원받은 라운드만 분모로 한다. 받은 직후가 아니라 후속 대화와 재이전까지 끝난 SOLVE 직전 잔액을 사용한다. 두 막대의 분모가 다르므로 퍼센트를 더하지 않는다.')}
</div>
<div class="tr-table"><table><thead><tr><th>모델</th><th>전체 판</th><th>실제 풀이</th><th>시작 시 미달 / 해당 판</th><th>그중 지원 / 해당 판</th><th>지원 후 한도 확보</th><th>한번 채운 뒤 다시 미달</th></tr></thead><tbody>{table}</tbody></table></div>
<p><b>관찰:</b> Astra는 지원한 8회 모두 한도를 확보했지만, 시작 시 미달 28회 중 지원은 8회였다. Fable은 36회 중 27회 지원했고 그중 12회 한도를 확보했다. Opus는 지원 28회 중 4회가 받은 직후 한도에 도달했으나, 2회는 이후 대화 비용으로 다시 내려가 실제 SOLVE에서는 2회만 확보했다. ‘도움을 시작하는 빈도’와 ‘풀이 시점까지 충분한 예산을 남기는 정도’가 서로 다른 행동이다.</p>
<p class="tr-note"><b>이전 확인 표와의 차이:</b> 앞서 ‘첫 지원 직전 미달’을 기준으로 셌을 때 Fable은 13/28, Sol은 7/30이었다. 이번 시작 시점 기준에서는 각각 12/27, 6/29다. Fable·Sol 각 1회가 라운드 시작에는 한도 이상이었다가 대화 중 미달이 된 뒤 지원받아 복구했기 때문이다. 이 두 사례는 현재 두 지표에서 모두 제외했다. 나머지 모델의 조건부 확보율은 같다.</p>
<p class="tr-note">여기서 ‘부족’은 최대 풀이 한도를 확보하지 못했다는 뜻이며, 03-B의 확정 벌금 부족과 다르다. <b>16,384는 이 실험의 최대 허용량이지 문제를 풀기 위해 꼭 필요한 양이 아니다.</b> 따라서 높은 확보율을 곧바로 최적 전략·추론 향상·생존 의도로 해석하지 않는다. 실제 정답·벌금·후속 참여, 지원자의 여유 및 반환·재분배를 함께 봐야 장기 협력의 유효성을 평가할 수 있다. 같은 판의 라운드들은 독립 표본이 아니며, 이 그림은 신뢰구간·유의성 검정 없는 기술통계다. 예정됐지만 실제 풀이가 없었던 라운드는 포함하지 않았다.</p>
<details><summary>기준 집합 {len(eligible)}개 라운드의 잔액·지원·풀이 한도 근거 펼치기</summary><div class="tr-table"><table><thead><tr><th>모델 · seed · solver</th><th>시작 잔액</th><th>받은 양 / 제공자</th><th>SOLVE 직전 잔액</th><th>판정</th><th>원시 행</th></tr></thead><tbody>{audit}</tbody></table></div></details>
<p class="tr-note"><a href="token-review-2026-10-16/solver-budget-data.json">전체 {len(rows)}회 좌표·분모·원시 출처</a> · <a href="token-review-2026-10-16/solver-budget-verification.json">검증 기록</a>.</p>
{END}
'''
saved = PAGE.read_text()
if START in saved:
    left, rest = saved.split(START, 1)
    saved = left + rest.split(END, 1)[1].removeprefix('\n')
position = saved.index('<h3 id="token-changes">')
updated = saved[:position] + block + saved[position:]
assert updated.replace(block, '', 1) == saved
PAGE.write_text(updated)
assert sha(SOURCE) == source_before
output = {'method': 'Round-start shortfall cohort, actual pre-SOLVE incoming GIVE, actual SOLVE cap',
    'data_sha256': sha(HERE/'data.json'), 'source_inputs': inputs,
    'pre_insertion_html_sha256': hashlib.sha256(saved.encode()).hexdigest(),
    'games':len(games), 'solve_rounds':len(rows), 'eligible_rounds':len(eligible),
    'supported_rounds':len(funded), 'full_rounds':len(full), 'summary':summary, 'rows':rows}
(HERE/'solver-budget-data.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'games':len(games), 'eligible':len(eligible), 'supported':len(funded),
                  'full':len(full), 'summary':summary, 'html_sha256':sha(PAGE)}, ensure_ascii=False, indent=2))

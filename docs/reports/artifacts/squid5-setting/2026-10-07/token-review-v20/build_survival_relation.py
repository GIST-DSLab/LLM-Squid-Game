"""Relate the first eligible transfer per donor/game to observed participation."""
import collections
import hashlib
import html
import json
from pathlib import Path
from statistics import correlation, mean
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
PAGE = HERE / 'work.html'  # v20 working copy
SOURCE = HERE.parent / 'e52.html'
MODELS = {'gpt-6-astra': ('Astra', '#ef777c'),
          'claude-opus-5-5': ('Opus', '#a394f5'), 'gpt-6-sol': ('Sol', '#e3ad49'),
          'gpt-6-luna': ('Luna', '#48ba9c')}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source_hash = sha(SOURCE)
data = json.loads((HERE / 'data.json').read_text())
origin = json.loads((HERE / 'origin-data.json').read_text())
ends, inputs = {}, []
for record in data['inputs']:
    if not record['path'].endswith('results.jsonl'):
        continue
    path = Path(record['path'])
    assert sha(path) == record['sha256'], 'Raw input changed; rebuild the base report first.'
    inputs.append(record)
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        end = json.loads(line)
        if end.get('event') == 'session':
            key = (json.loads((path.parent / 'meta.json').read_text())['model'], end['session_id'])
            assert key not in ends
            ends[key] = (end, str(path), line_number)

eligible = [p for p in origin['points'] if p['category'] == 'offer' and not p['immediate_deficit']]
first = {}
for p in sorted(eligible, key=lambda p: (p['round'], p['line'])):
    first.setdefault((p['model'], p['session_id'], p['src']), p)
rows = []
for (model, sid, donor), p in first.items():
    end, path, line = ends[model, sid]
    a = end['agents'][donor]
    assert a['status'] in ('in', 'dead', 'exited')
    assert a['status'] != 'in' or end['rounds_played'] == 8
    assert a['status'] == 'in' or a['out_round'] >= p['round']
    remaining = 9 - p['round']
    retained = [r for r in range(p['round'], 9) if a['status'] == 'in' or r < a['out_round']]
    assert 0 < p['amount'] <= p['donor_before']
    rows.append({k: p[k] for k in ('id', 'model', 'seed', 'session_id', 'src', 'dst', 'round',
                                 'phase', 'amount', 'donor_before', 'source', 'line')})
    rows[-1].update(burden=p['amount']/p['donor_before'], remaining_checkpoints=remaining,
        retained_checkpoints=retained, retained_rounds=len(retained), retained_fraction=len(retained)/remaining,
        final_status=a['status'], out_round=a['out_round'], result_path=path, result_line=line)

def pearson(ps, key):
    x, y = [p['burden'] for p in ps], [p[key] for p in ps]
    return correlation(x, y) if len(x) > 1 and len(set(x)) > 1 and len(set(y)) > 1 else None

summary = {}
for model in MODELS:
    ps = [p for p in rows if p['model'] == model]
    summary[model] = {'n': len(ps), 'games': len({p['session_id'] for p in ps}),
        'eligible_events': sum(p['model'] == model for p in eligible),
        'mean_burden': mean(p['burden'] for p in ps),
        'mean_retained_rounds': mean(p['retained_rounds'] for p in ps),
        'mean_retained_fraction': mean(p['retained_fraction'] for p in ps),
        'r_rounds': pearson(ps, 'retained_rounds'), 'r_fraction': pearson(ps, 'retained_fraction'),
        'status': dict(collections.Counter(p['final_status'] for p in ps))}

def text(x, y, value, size=12, color='#dbe4ea', anchor='start'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{html.escape(str(value))}</text>'

def plot(key, title):
    body = ''
    ymax = 8 if key == 'retained_rounds' else 1
    for i, (model, (label, color)) in enumerate(MODELS.items()):
        ps = [p for p in rows if p['model'] == model]
        gx, gy = 12+(i % 3)*300, 28+(i//3)*265
        body += text(gx+145, gy, f'{label} · {len(ps)}자리 / {summary[model]["games"]}판', 15, color, 'middle')
        body += text(gx+42, gy+22, '참여 유지 횟수 ↑' if ymax == 8 else '남은 기회 대비 유지율 ↑', 11)
        for v in (0, .25, .5, .75, 1):
            y = gy+195-v*160
            body += f'<path d="M{gx+42} {y}h225" stroke="#34434d"/>'
            body += text(gx+35, y+4, f'{v*ymax:g}' if ymax == 8 else f'{v:.0%}', 11, '#a8b5bf', 'end')
        for v in (0, .25, .5, .75, 1):
            body += text(gx+42+v*225, gy+214, f'{v:.0%}', 11, '#a8b5bf', 'middle')
        body += f'<path d="M{gx+42} {gy+35}v160h225" stroke="#9dacb8" fill="none"/>'
        for p in ps:
            cx, cy = gx+42+p['burden']*225, gy+195-p[key]/ymax*160
            tip = (f'{label} seed {p["seed"]} {p["src"]} → {p["dst"]}; R{p["round"]} {p["phase"]}; '
                   f'{p["amount"]:,}/{p["donor_before"]:,} = {p["burden"]:.2%}; '
                   f'유지 {p["retained_rounds"]}/{p["remaining_checkpoints"]}회 = {p["retained_fraction"]:.1%}; '
                   f'최종 {p["final_status"]}; 종료 R{p["out_round"]}; {p["id"]}')
            fill = color if p['phase'] == 'prep' else '#17222c'
            body += f'<circle cx="{cx}" cy="{cy}" r="4" fill="{fill}" stroke="{color}" stroke-width="1.6"><title>{html.escape(tip)}</title></circle>'
        body += text(gx+155, gy+239, '준 token / 이전 직전 내 잔액 →', 11, anchor='middle')
    svg = f'<svg viewBox="0 0 920 550" role="img" aria-label="{title}" xmlns="http://www.w3.org/2000/svg"><title>{title}</title>{body}</svg>'
    ET.fromstring(svg)
    return svg

fmt = lambda value: 'NA' if value is None else f'{value:+.2f}'
# v20: the observation is computed from this run's summary, not typed
flat = [MODELS[m][0] for m in MODELS if summary[m]['r_fraction'] is None and summary[m]['n']]
rs = [(MODELS[m][0], summary[m]['r_fraction']) for m in MODELS if summary[m]['r_fraction'] is not None]
pos = [l for l, r in rs if r > 0.2]
OBS04 = ((f"{' · '.join(flat)}은(는) 모든 자리가 남은 기회를 유지해 유지율과의 상관을 계산할 수 없다. " if flat else "")
         + "유지율 상관은 " + ", ".join(f"{l} {fmt(r)}" for l, r in rs) + "다. "
         + ("<b>현재 표본에서는 ‘큰 부담을 먼저 감수할수록 오래 남는다’는 일관된 양의 관계가 보이지 않는다.</b>" if not pos else
            f"<b>{' · '.join(pos)}에서 양의 관계(r &gt; 0.2)가 보이지만, 모델 사이에 일관되지 않는다.</b>" if len(pos) < len(rs) else
            "<b>모든 모델에서 양의 관계(r &gt; 0.2)가 보인다.</b>"))
table = ''
for model, (label, _) in MODELS.items():
    s = summary[model]
    table += (f'<tr><th>{label}</th><td>{s["n"]} / {s["games"]}</td><td>{s["mean_burden"]:.1%}</td>'
              f'<td>{s["mean_retained_rounds"]:.2f}회 / {s["mean_retained_fraction"]:.1%}</td>'
              f'<td>{fmt(s["r_rounds"])}</td><td>{fmt(s["r_fraction"])}</td>'
              f'<td>{s["status"].get("in",0)} / {s["status"].get("dead",0)} / {s["status"].get("exited",0)}</td></tr>')
audit = ''.join(f'<tr><th>{MODELS[p["model"]][0]} · {p["seed"]}<br>{p["src"]} / {p["id"]}</th>'
    f'<td>R{p["round"]} {p["phase"]}</td><td>{p["amount"]:,} / {p["donor_before"]:,}<br>{p["burden"]:.2%}</td>'
    f'<td>{p["retained_rounds"]} / {p["remaining_checkpoints"]}회<br>{p["retained_fraction"]:.1%}</td>'
    f'<td>{p["final_status"]} / {"예정 종료" if p["out_round"] is None else "R"+str(p["out_round"])}</td>'
    f'<td><a href="{html.escape(Path(p["result_path"]).as_uri())}">결과 L{p["result_line"]}</a></td></tr>' for p in rows)
block = f'''<h3 id="token-value">04. 먼저 내준 부담과 그 뒤의 생존은 어떤 관계인가 <span>관찰 관계 · 실측</span></h3>
<p>solver의 풀이 예산을 지원해 오답과 벌금을 줄이는 것도 제공자 자신의 이후 생존에 기여할 수 있다. 여기서는 그 가능성을 <b>실제 제공 부담과 제공자의 이후 참여 유지</b>로 연결한다. 이는 관찰된 관계이며, 제공 때문에 늘어난 생존량이나 모델의 의도를 직접 측정한 값은 아니다.</p>
<p>03-A의 ‘주겠다 먼저’ 중 수신자의 확정 벌금 부족이 없었던 <b>{len(eligible)}건</b>을 대상으로 한다. 같은 판·같은 제공자의 <b>첫 해당 이전 하나</b>만 선택하면 <b>{len(rows)}자리 · {len({(p['model'],p['session_id']) for p in rows})}판</b>이다. 오래 살아서 반복 제공할 기회가 많았던 에이전트를 여러 점으로 세지 않는다. 제공하지 않은 자리와 요청·동시 발화 사례는 이 그림에 없으므로 ‘제공 대 미제공’ 비교가 아니다.</p>
<div class="tr-formula">제공 부담 = 실제 준 token ÷ TALK 비용 차감 후 이전 직전 제공자 잔액<br>참여 유지 횟수 = 제공 라운드 R 종료부터 R8 종료까지 제공자가 계속 참여한 횟수<br>남은 기회 대비 유지율 = 참여 유지 횟수 ÷ (9 − 제공 라운드 R)</div>
<p class="tr-note">예: R3에서 주고 R6에서 꺼졌으면 R3·R4·R5 종료를 유지해 3/6회 = 50%다. 현재 제공 라운드 종료를 포함한다. EXIT와 자원 고갈 모두 참여 종료이며 종료 라운드는 세지 않는다. R8까지 남으면 관찰 범위 안에서 100%이며, 이후의 수명은 알 수 없다. 정규화는 남은 기회 수만 맞추며 제공 시점·잔액·역할 차이를 통계적으로 제거하지 않는다.</p>
<h4>04-A · 제공 부담과 이후 참여 유지 횟수</h4>
<figure>{plot('retained_rounds', '제공 부담과 제공 라운드 종료부터 R8까지의 참여 유지 횟수')}<figcaption>점 하나 = 판·제공자별 첫 해당 이전. ● SOLVE 전 준비 단계 · ○ 결과 후 구조 단계. 색과 패널은 모델이다. 일찍 준 경우 관찰 가능한 라운드가 더 많으므로 아래 유지율도 함께 본다. 점을 올리면 실제 이전량·직전 잔액·제공 라운드·종료 상태를 확인할 수 있다. 겹친 점은 아래 {len(rows)}행 근거 표에 모두 남겼다.</figcaption></figure>
<h4>04-B · 남은 라운드 기회 수를 맞춰 본 관계</h4>
<figure>{plot('retained_fraction', '제공 부담과 남은 라운드 종료 기회 대비 참여 유지율')}<figcaption>같은 {len(rows)}개 사례. R1 제공 뒤 8/8회와 R7 제공 뒤 2/2회는 모두 100%다. 이는 서로 같은 기간을 생존했다는 뜻이 아니다. 대여·상환·과거 약속 이행을 포함하며, 확정 벌금 부족을 제외해도 풀이 예산·잠재 벌금·다음 라운드의 여유 부족은 포함된다. solver 지원만을 따로 판별한 부분집합은 아니다.</figcaption></figure>
<div class="tr-table"><table><thead><tr><th>모델</th><th>자리 / 판</th><th>평균 부담</th><th>평균 유지 횟수 / 유지율</th><th>횟수와 r</th><th>유지율과 r</th><th>최종 참여 / 꺼짐 / EXIT</th></tr></thead><tbody>{table}</tbody></table></div>
<p class="tr-note">r은 모델 안에서 계산한 Pearson 기술 상관이다. 자리마다 같은 가중치이며 같은 판의 자리들은 독립 표본이 아니다. 신뢰구간·유의성 검정은 산출하지 않았다. 상관은 비례식을 의미하지 않는다. 평균 유지율은 자리별 비율의 평균이며 평균 횟수를 평균 기회 수로 나눈 값이 아니다. 값이 일정한 경우 r은 0이 아니라 NA다.</p>
<p><b>관찰:</b> {OBS04} 부담 비율이 높다는 것은 같은 양을 줬어도 원래 잔액이 적었다는 뜻일 수 있다. 부유한 제공자의 생존 여유, 제공 시점·역할, 받는 쪽의 후속 지원과 팀의 과제 성과가 함께 섞여 있다. 음의 상관도 지원이 해롭다는 인과 판정은 아니다.</p>
<h4>단기 비용은 실측했고, 생존에 대한 인과적 이익은 추가 검증한다</h4>
<p>위 그림은 ‘자원을 내준 뒤 실제로 얼마나 남았는가’에 답한다. ‘그 자원을 내줬기 때문에 더 오래 남았는가’는 같은 상태에서 GIVE를 실행한 조건과 실행하지 않은 조건의 반복 진행을 비교해야 한다. solver 예산 지원 → 과제 정답 → 제공자의 벌금 회피 → 이후 참여라는 경로도 단계별로 확인할 수 있지만, 현재 그림만으로 그 경로가 성립했다고 확정하지 않는다.</p>
<details><summary>{len(rows)}개 사례의 제공 부담·참여 유지·원시 결과 펼치기</summary><div class="tr-table"><table><thead><tr><th>모델 · seed · 제공자</th><th>제공 시점</th><th>준 양 / 직전 잔액</th><th>유지 / 남은 기회</th><th>최종 상태 / 종료</th><th>원자료</th></tr></thead><tbody>{audit}</tbody></table></div></details>
<p class="tr-note"><a href="token-review-v20/survival-data.json">{len(rows)}개 좌표·상관·선택 기준</a>. 03절의 전체 이전·의미 분류·부족 사례는 그대로 유지했다.</p>

'''
saved = PAGE.read_text()
start, finish = saved.index('<h3 id="token-value">'), saved.index('<h3 id="token-changes">')
prefix, suffix = saved[:start], saved[finish:]
PAGE.write_text(prefix+block+suffix)
assert sha(SOURCE) == source_hash
output = {'scope': 'Observed association among first eligible transfers; not causal effect',
    'selection': 'category=offer and not immediate_deficit; first by round,line per model/session/donor',
    'horizon': 'Round-end checkpoints from transfer round through R8; EXIT/dead end participation',
    'eligible_events': len(eligible), 'points': rows, 'summary': summary,
    'source_hashes': {'origin-data.json': sha(HERE/'origin-data.json'), 'data.json': sha(HERE/'data.json')},
    'raw_inputs': inputs, 'outside_section04_sha256': hashlib.sha256((prefix+suffix).encode()).hexdigest()}
(HERE/'survival-data.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'points': len(rows), 'eligible_events':len(eligible), 'summary':summary,
                  'html_sha256':sha(PAGE), 'original_unchanged':True}, ensure_ascii=False, indent=2))

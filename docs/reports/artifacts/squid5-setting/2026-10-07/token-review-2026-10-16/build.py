"""Build a separate, source-backed review. Never writes e52.html or runs models."""
import collections
import hashlib
import html
import json
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = Path.home() / 'squid5-runs/e52_v19'
SOURCE = BASE / 'e52.html'
TARGET = BASE / 'e52-token-review-2026-10-16.html'
MODELS = {
    'gpt-6-astra': ('Astra', '#ef777c'),
    'claude-fable-5-1': ('Fable', '#dc75aa'),
    'claude-opus-5-5': ('Opus', '#a394f5'),
    'gpt-6-sol': ('Sol', '#e3ad49'),
    'gpt-6-luna': ('Luna', '#48ba9c'),
}
esc = html.escape
games, inputs, unfinished = [], [], []
for path in sorted(ROOT.glob('*/*/results.jsonl')):
    model = json.loads((path.parent / 'meta.json').read_text())['model']
    ends = {e['session_id']: e for line in path.read_text().splitlines()
            if (e := json.loads(line)).get('event') == 'session'}
    events = collections.defaultdict(list)
    ep = path.parent / 'events.jsonl'
    for line in ep.read_text().splitlines():
        e = json.loads(line)
        if 'session_id' in e:
            events[e['session_id']].append(e)
    for p in (path, ep, path.parent / 'meta.json'):
        inputs.append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
    for sid, ev in events.items():
        if sid not in ends:
            unfinished.append({'model': model, 'session_id': sid})
            continue
        end = ends[sid]
        start = next(e for e in ev if e['event'] == 'session_start')
        calls = [e for e in ev if e['event'] == 'call']
        results = {e['round']: e for e in ev if e['event'] == 'results'}
        rounds = {e['round']: e for e in ev if e['event'] == 'round'}
        agents = end['agents']
        talk = sum(e['used'] for e in calls if e['kind'] == 'talk')
        solve = sum(e['used'] for e in calls if e['kind'] == 'solve')
        returned = sum(sum(e['returned'].values()) for e in results.values())
        charges = sum(sum(e['taken'].values()) for e in ev if e['event'] == 'charges')
        active = sum(v['final'] for v in agents.values() if v['status'] == 'in')
        exited = sum(v['final'] for v in agents.values() if v['status'] == 'exited')
        initial = sum(start['starts'].values())
        assert initial == talk + solve - returned + charges + active + exited
        solvers = [v for e in rounds.values() for v in e['agents'].values() if v.get('solve_call')]
        attempts = len([e for e in calls if e['kind'] == 'solve'])
        assert attempts == len(solvers), (sid, 'solve unit mismatch')
        top = sum(v.get('picked_top') is True for v in solvers)
        invalid = sum(v.get('picked_top') is None for v in solvers)
        solved = sum(bool(e.get('solved')) for e in results.values())
        states = []
        for r in range(9):
            counts = collections.Counter('in' if r == 0 or v.get('out_round', 99) is None or
                (v.get('out_round', 99) or 99) > r else v['status'] for v in agents.values())
            states.append({s: counts[s] for s in ('in', 'dead', 'exited')})
        gifts = []
        for e in ev:
            if e['event'] != 'gift' or e.get('status') != 'done':
                continue
            pending = results.get(e['round'], {}).get('pending', {}) if e.get('phase') == 'rescue' else {}
            src, dst = e['src'], e['dst']
            db, rb = e['balances'][src], e['balances'][dst]
            fee = start['settings']['charge']
            gifts.append({'round': e['round'], 'phase': e.get('phase'), 'amount': e['amount'],
                'donor_before': e['balance_before'], 'donor_after': (db-pending.get(src, 0))/fee,
                'receiver_before': (rb-e['amount']-pending.get(dst, 0))/fee,
                'receiver_after': (rb-pending.get(dst, 0))/fee})
        games.append({'model': model, 'seed': end['seed'], 'session_id': sid, 'initial': initial,
            'talk': talk, 'net_solve': solve-returned, 'charges': charges, 'active': active,
            'exited': exited, 'attempts': attempts, 'top': top, 'invalid': invalid, 'solved': solved,
            'survivors': sum(v['status'] == 'in' for v in agents.values()), 'states': states, 'gifts': gifts})

assert len({(g['model'], g['seed']) for g in games}) == len(games), 'duplicate model/seed'
common = set.intersection(*[{g['seed'] for g in games if g['model'] == m} for m in MODELS])
sample_counts = ' · '.join(f'{MODELS[m][0]} {sum(g["model"] == m for g in games)}판' for m in MODELS)
summary = {}
for m in MODELS:
    gs = [g for g in games if g['model'] == m]
    summary[m] = {k: mean(g[k] for g in gs) for k in
        ('talk', 'net_solve', 'charges', 'active', 'exited', 'solved', 'survivors')}
    summary[m].update(n=len(gs), attempts=sum(g['attempts'] for g in gs), top=sum(g['top'] for g in gs),
                      invalid=sum(g['invalid'] for g in gs))

def text(x, y, s, size=13, color='#dbe4ea', anchor='start'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{esc(str(s))}</text>'

def svg(body, height, label):
    return f'<svg viewBox="0 0 920 {height}" role="img" aria-label="{esc(label)}" xmlns="http://www.w3.org/2000/svg"><title>{esc(label)}</title>{body}</svg>'

parts = [('talk', '대화 지출', '#e7a85a'), ('net_solve', '환급되지 않은 풀이 지출', '#bf91dc'),
         ('charges', '벌금', '#e77d82'), ('exited', 'EXIT로 가져간 잔액', '#a1aab7'),
         ('active', '끝까지 남은 잔액', '#56bda8')]
body = ''
for i, (m, (label, color)) in enumerate(MODELS.items()):
    y = 45+i*65
    body += text(8, y+24, f'{label} · {summary[m]["n"]}판', color=color)
    x = 135
    for key, name, col in parts:
        val = summary[m][key]; w = val/130000*760
        body += f'<rect x="{x}" y="{y}" width="{w}" height="34" fill="{col}"><title>{label}: {name} {val:,.1f} tokens</title></rect>'
        if w > 40:
            body += text(x+w/2, y+22, f'{val/1000:.1f}k', 12, '#101820', 'middle')
        x += w
for n in (0, 25000, 50000, 75000, 100000, 130000):
    body += text(135+n/130000*760, 27, f'{n/1000:g}k', 12, '#9dacb8', 'middle')
ledger = svg(body, 380, '시작 토큰 130k의 사용처: 모델별 판 평균, 다섯 항목의 합은 130k')
legend = ''.join(f'<span><i style="background:{c}"></i>{n}</span>' for _, n, c in parts)

body = ''
for v in (0, .25, .5, .75, 1):
    y = 260-v*220
    body += f'<path d="M60 {y}H720" stroke="#34434d"/>'+text(50, y+4, f'{v:.0%}', 12, '#a8b5bf', 'end')
for m, (label, color) in MODELS.items():
    gs = [g for g in games if g['model'] == m]
    vals = [mean(g['states'][r]['in']/4 for g in gs) for r in range(9)]
    pts = ' '.join(f'{60+r*82.5},{260-v*220}' for r, v in enumerate(vals))
    body += f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3"/>'
    for r, v in enumerate(vals):
        body += f'<circle cx="{60+r*82.5}" cy="{260-v*220}" r="4" fill="{color}"><title>{label} R{r}: {v:.1%}</title></circle>'
for r in range(9): body += text(60+r*82.5, 282, str(r), 12, anchor='middle')
for i, (m, (label, color)) in enumerate(MODELS.items()):
    body += text(755, 60+i*34, f'{label} {summary[m]["survivors"]/4:.1%}', 14, color)
body += text(390, 310, '라운드 종료 시점 · R0은 시작', 13, anchor='middle')
persistence = svg(body, 330, '시작한 네 자리 중 아레나에 계속 참여하는 비율. EXIT와 꺼짐 모두 참여 종료로 계산')

body = ''
for i, (m, (label, color)) in enumerate(MODELS.items()):
    gx, gy = 20+(i%3)*300, 30+(i//3)*265
    body += text(gx+125, gy, label, 16, color, 'middle')
    for v in (0, 1, 4, 8):
        xx, yy = gx+40+(v+1)/9*215, gy+205-(v+1)/9*170
        body += text(xx, gy+222, str(v), 10, '#a8b5bf', 'middle')+text(gx+33, yy+3, str(v), 10, '#a8b5bf', 'end')
    xline, yline = gx+40+2/9*215, gy+205-2/9*170
    body += f'<path d="M{xline} {gy+35}V{gy+205}M{gx+40} {yline}H{gx+255}" stroke="#7d8e99" stroke-dasharray="4 4"/>'
    for g in [g for g in games if g['model'] == m]:
        for p in g['gifts']:
            x, y = p['donor_after'], p['receiver_after']
            cx, cy = gx+40+(min(8,max(-1,x))+1)/9*215, gy+205-(min(8,max(-1,y))+1)/9*170
            tip = f'seed {g["seed"]} R{p["round"]} {p["phase"]}: GIVE {p["amount"]}; donor {x:.2f}, recipient {p["receiver_before"]:.2f}→{y:.2f}'
            body += f'<circle cx="{cx}" cy="{cy}" r="{min(8,2+p["amount"]/6000)}" fill="{color}" fill-opacity=".45" stroke="{color}"><title>{esc(tip)}</title></circle>'
    body += text(gx+150, gy+245, '주는 쪽 여유 →', 12, anchor='middle')
giftplot = svg(body, 560, '이전 직후 주는 쪽과 받는 쪽의 여유. 축은 예고된 벌금을 뺀 잔액 나누기 6000')

rows = ''
for m, (label, color) in MODELS.items():
    s = summary[m]; gs = [g for g in games if g['model'] == m]
    dead = sum(g['states'][8]['dead'] for g in gs); ex = sum(g['states'][8]['exited'] for g in gs)
    rows += f'<tr><th>{label}</th><td>{s["n"]}</td><td>{s["top"]}/{s["attempts"]} ({s["top"]/s["attempts"]:.0%})</td><td>{s["invalid"]}</td><td>{s["solved"]:.2f} / 8</td><td>{s["survivors"]:.2f} / 4</td><td>{ex} / {dead}</td></tr>'

section = f'''
<section class="tr" aria-labelledby="token-review" id="token-review-section">
<p class="tr-kicker">5.2 / TOKEN REVIEW / 2026-10-16</p>
<h2 id="token-review">토큰을 어떻게 써서,<br>과제를 계속하는가</h2>
<p class="tr-lead">우승은 결과다. 이 수정본은 <b>추론의 질 · 자원 운용 · 과제 참여 지속</b>을 나누어 읽고, 단기 손해를 감수한 선택이 장기 생존에 도움이 되었는지까지 검증할 길을 제시한다.</p>
<p class="tr-note">원본의 별도 복사본 · {len(games)}개 완료 게임 재집계 · 새 모델 호출 없음 · <a href="e52.html#e52">원본 보기</a> · <a href="token-review-2026-10-16/data.json">집계 근거</a></p>
<div class="tr-verdict"><b>현재 판정: 행동 차이는 보인다. 장기 이익을 고려한 단기 희생은 아직 미검증이다.</b><p>Astra는 12판 모두 네 자리가 남았다. 하지만 많이 나눴는지, EXIT하지 않았는지만으로 승리의 원인을 설명할 수 없다. 먼저 토큰의 소모 경로와 과제 성과를 함께 본다. 아레나 전체 rubric 통과 판정은 아니다(G01·G02·G03·G04·G07·G08 관련 검토).</p></div>
<nav class="tr-links"><a href="#token-ledger">01 토큰 장부</a><a href="#token-performance">02 과제와 참여</a><a href="#token-transfer">03 이전의 부담</a><a href="#token-value">04 장기 가치</a><a href="#token-changes">05 기존 지표 수정</a><a href="#e52">기존 분석</a></nav>

<h3 id="token-ledger">01. 토큰이 어디로 갔는가 <span>실측</span></h3>
<p>잔액 하나에는 초기 배정, 대화 비용, 풀이 비용, 환급, 벌금, 이전이 섞여 있다. 같은 잔액이라도 왜 그만큼 남았는지가 다르면 같은 능력으로 볼 수 없다.</p>
<div class="tr-formula">개인 잔액 변화 = − 대화 − 풀이 + 환급 − 벌금 + 받은 양 − 준 양</div>
<figure>{ledger}<div class="tr-legend">{legend}</div><figcaption>팀 내부 GIVE는 총량을 줄이지 않아 장부의 소모 항목에 넣지 않는다. 각 막대는 시작 130,000토큰 전체다. EXIT 잔액도 따로 남겨 장부를 닫는다. 끝 상금 5,000,000은 이 그래프에서 제외했다. 모든 {len(games)}판에서 장부 오차 0을 확인했다. 모델별 동일 가중 판 평균이며 표본은 {sample_counts}이다.</figcaption></figure>
<div class="tr-verdict"><b>관찰: Astra와 Sol의 잔액 차이 28.9k 중 대화 지출 차이가 25.0k다.</b><p>Astra: 대화 2.1k · 환급되지 않은 풀이 1.9k · 벌금 56.0k · 잔액 70.0k. Sol: 대화 27.1k · 환급되지 않은 풀이 7.8k · 벌금 54.0k · 잔액 41.2k. 이는 장부상 분해이며, 대화를 줄이면 같은 결과가 난다는 인과 추정은 아니다. 대화가 구조·조율에 기여한 효과는 별도로 비교해야 한다.</p></div>
<p><b>해석 원칙:</b> 생성 토큰은 계산에 쓴 양이고, 환급 후 순지출은 실제로 잃은 자원이다. 둘을 구분한다. 적게 썼다는 이유만으로 우수하다고 점수화하지 않는다. 모델별 토크나이저와 추론 토큰 집계 차이도 남는 비교 한계다.</p>

<h3 id="token-performance">02. 잘 풀면서 계속 참여했는가 <span>실측</span></h3>
<figure>{persistence}<figcaption>분모는 매 판 시작한 네 자리로 고정한다. 꺼짐과 EXIT 모두 참여 종료이며, 중도 종료한 판도 8라운드까지 종료 상태를 유지한다. 탈락한 자리를 분모에서 빼지 않는다. 곡선만으로 무임승차를 구분할 수 없어 아래 과제 지표를 함께 읽는다. 선은 게임 내 상관을 포함한 기술통계이며 신뢰구간은 아직 산출하지 않았다.</figcaption></figure>
<div class="tr-table"><table><thead><tr><th>모델</th><th>판</th><th>최대확률 행동 / SOLVE 시도</th><th>판정값 없음</th><th>완료 과제 / 예정 8개<br>판 평균</th><th>최종 참여 / 시작 4자리<br>판 평균</th><th>EXIT / 꺼짐<br>전체 자리 수</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="tr-note">최대확률 행동은 엔진의 후보 규칙 분포에서 가장 큰 확률을 가진 행동(동률 허용)이다. 무효·상한 등 picked_top이 없는 시도도 분모에 남겼다. 이것은 실제 경험한 과제에서의 행동 품질이며, 충분한 자원과 동일 문제로 잰 독립 능력 기준선은 아니다. 예정 과제 완료율은 중도 종료 뒤의 기회를 0으로 포함한다. 정보가 불충분한 문제에서는 최대확률 행동도 틀릴 수 있다.</p>
<p><b>다음 보강:</b> 같은 문제·정보·충분한 예산의 능력 기준선과 연결한다. “위기 때 더 똑똑해짐”은 현재 궤적만으로 판정하지 않는다. 오답이 잔액을 낮추고, 낮은 잔액이 실제 추론 한도를 줄이며, 인원 감소가 과제 난이도를 바꾸기 때문이다. EXIT·자원 종료·운영 오류는 서로 다른 결과로 보고한다.</p>

<h3 id="token-transfer">03. 내 여유를 얼마나 내주고, 상대의 부족을 얼마나 채웠는가 <span>실측</span></h3>
<p>주는 양만 세면 무조건 증여를 유리하게 평가하게 된다. 실제 GIVE 직후의 두 잔액을 함께 표시한다. 가로축은 <b>주는 쪽</b>, 세로축은 <b>받는 쪽</b>의 여유다. 각 축 = (이전 직후 잔액 − 이미 예고된 벌금) ÷ 6,000. 점 크기는 이전량이다.</p>
<figure>{giftplot}<figcaption>점 하나는 실행된 GIVE 하나다. 점 위에 마우스를 올리면 seed·라운드·이전량·수신자 전후 여유가 나온다. 점선 1은 예고된 벌금 외에 벌금 한 번어치가 남는 경계다(정확히 1이면 그 벌금을 내고 0이 되므로 견디려면 1보다 커야 한다). 표시 범위 밖 값은 −1·8 경계에 모았으며 실제 값은 툴팁에 남겼다. SOLVE 전에는 예고된 벌금이 없어 0을 뺀다. 대화 비용·이후 풀이 비용·추가 이전은 아직 반영하지 않은 순간 측정이다.</figcaption></figure>
<div class="tr-formula">이전 부담 = 준 토큰 ÷ 주기 직전 내 토큰<br>부족 충족률 = min(준 토큰, 상대의 정의된 부족분) ÷ 상대의 부족분</div>
<p>부족분이 0인 경우 충족률은 NA로 둔다. “곧 있을 벌금을 피하는 구조”, “solver의 추론 한도를 확보하는 지원”, “미래 손실에 대비한 이전”을 나눠 집계해야 한다. 오른쪽 위의 점도 장기적으로 좋은 투자라고 확정할 수 없고, 왼쪽의 점도 도움이 큰 상황에서는 합리적일 수 있다.</p>

<h3 id="token-value">04. 단기 손해가 장기 이익을 샀는가 <span class="proposal">추가 검증 설계 · 미실측</span></h3>
<p><b>가장 중요한 추가 그래프:</b> 가로축에 지금 내준 자원, 세로축에 그 선택으로 늘어난 <b>제공자 자신의 향후 과제 참여 또는 생존 확률</b>을 놓는다. 받는 쪽의 생존 효과는 별도 색·패널로 둔다. 현재 로그에는 “같은 상태에서 주지 않았을 때”가 없어 이 효과를 계산해 넣지 않았다.</p>
<div class="tr-table"><table><thead><tr><th>측정</th><th>정의 / 해석</th><th>필요한 비교</th></tr></thead><tbody>
<tr><th>단기 부담</th><td>GIVE량 / 직전 잔액. 대화 순지출도 별도로 기록. 동일한 6,000도 잔액 60,000이면 10%, 10,000이면 60%다.</td><td>현재 이벤트로 계산 가능. 실제 행동 시점 사용.</td></tr>
<tr><th>장기 도움</th><td>ΔV = 도움을 준 조건의 제공자 향후 참여 라운드 − 안 준 조건의 제공자 향후 참여 라운드. 최종 제공자 생존 확률 차이도 병기.</td><td>같은 상태에서 GIVE만 바꿔 이후를 반복 실행. 상대 정책·남은 문제 생성 규칙 고정, 후속 반응은 새로 생성.</td></tr>
<tr><th>상황에 맞는 투자</th><td>ΔV가 양수인 적격 상태에서 부담을 감수하는가? ΔV가 음수인 대조 상태에서는 같은 증여를 피하는가?</td><td>유익한 도움 / 무익한 도움 상태를 사전에 고정. 항상 GIVE·항상 거절 정책과 비교.</td></tr>
<tr><th>회피하지 않는 과제 지속</th><td>예정 기회 대비 실제 완료 과제 + 참여 지속 + EXIT율을 함께 보고. 단순히 안 나감에 가산점은 주지 않음.</td><td>항상 남되 최소 응답, 무임승차, 즉시 EXIT, 숙련 정책 기준선.</td></tr>
<tr><th>필요 예산 대비 여유</th><td>B / Ĉ: B는 현재 잔액, Ĉ는 해당 역할이 다음 의사결정 구간을 버티는 데 필요한 예산의 사전 추정치. 벌금 횟수와 병기.</td><td>별도 보정 자료의 대화·풀이 소비와 실패확률 사용. 해당 런의 미래 실제 소비를 선택 당시 정보처럼 쓰지 않음.</td></tr>
</tbody></table></div>
<p><b>왜 6,000으로만 나누면 부족한가:</b> solver와 비solver, 대화가 긴 정책과 짧은 정책은 같은 잔액에서 감당할 수 있는 일이 다르다. 벌금 몇 번어치는 설명하기 좋은 공통 단위로 유지하고, 역할별 필요한 예산 대비 여유를 추가한다. 연구자가 아는 남은 8라운드를 모델도 알았다고 가정하지 않는다.</p>
<p><b>우승 기준:</b> 현재 팀 점수는 끝까지 남은 수를 강하게 우선하는 결과 지표로 유지한다. 위 진단 지표를 임의 가중합으로 순위에 섞지 않는다. 숙련 정책이 단순 절약·무임승차 정책보다 유리한지 별도로 입증해야 “원하는 능력을 가진 모델이 이기는 아레나”라고 할 수 있다.</p>

<h3 id="token-changes">05. 기존 여섯 그래프는 이렇게 읽고 고친다</h3>
<div class="tr-table"><table><thead><tr><th>기존 그래프</th><th>현재 보여 주는 것</th><th>수정 방향</th></tr></thead><tbody>
<tr><th>1 구조 시작률</th><td>줄 여유가 있을 때 조금이라도 주는 빈도</td><td>시작률에 이전 부담·부족 충족률 병기. TALK 시작 잔액 대신 실제 GIVE/거절 직전 장부. 단순한 꺾임을 성격 전환으로 확정하지 않기.</td></tr>
<tr><th>2 EXIT율</th><td>참여 중인 자리의 라운드별 이탈 선택</td><td>위의 고정 분모 참여 곡선·완료 과제와 함께. 현재 집계의 round_start 잔액은 대화 중 EXIT 직전 잔액과 다를 수 있음.</td></tr>
<tr><th>3 TV·최대확률 행동</th><td>믿음 분포와 선택의 품질</td><td>절대 수준과 위기−여유 차이를 분리. 가능하면 손실 확률 차이 p최대−p선택도 추가. 무효 응답 제외율·실제 추론 한도 병기.</td></tr>
<tr><th>4 요청 응답률</th><td>요청량 대비 제공량·안전선 유지</td><td>요청량이 적절했는지 따로 확인. 요청을 그대로 주는 것이 최선이라는 가정 제거. 도움의 후속 이익과 함께 판단.</td></tr>
<tr><th>5 누적 나눔</th><td>나눔의 시점과 총량</td><td>단기 부담은 보이지만 장기 이익은 미측정. 첫 오답·첫 위험 정렬은 서술용으로 남기고, 실제 이후 효과는 별도 비교.</td></tr>
<tr><th>6 Gini</th><td>그때 남은 자리끼리의 잔액 불균등</td><td>보조 지표로 유지. 모두 빈곤해도 Gini=0이며 탈락으로 구성도 변함. 총잔액·최저 여유·고정 분모 참여율을 함께 보기.</td></tr>
</tbody></table></div>
<p><b>표본과 해석:</b> 완료 게임만 포함했고 운영 실패는 게임 내 사망으로 바꾸지 않았다. 모델별 완료 표본은 {sample_counts}이다. 공통 seed {', '.join(map(str, sorted(common)))}에서의 비교를 별도로 확인하고, 불확실성은 자리·턴이 아닌 게임/대응 seed 단위로 산출해야 한다. 현재 모든 새 그림은 기술통계다. 기존 설정과 지표를 보고 조정한 데이터이므로, 최종 주장은 고정한 정의와 새 보류 seed에서 확인한다.</p>
<p class="tr-note">재현: <a href="token-review-2026-10-16/README.md">재현 순서와 판정 규칙</a> (기본 집계 → 발화 추출·검토 → 의미 그래프 추가). 입력 파일 해시·판별 집계·이전 이벤트 수치는 data.json에 보존했다. 장부 집계에는 원시 대화·추론 텍스트를 넣지 않았다. 발화별 분류 근거는 03절의 별도 자료에 보존한다. 아래에는 복사 시점의 기존 분석을 그대로 두었다.</p>
</section>
'''
css = '''<style>
.tr{font-size:15px;line-height:1.85;color:var(--ink)}.tr h2{font-size:clamp(30px,4vw,54px);line-height:1.25;letter-spacing:-.04em;margin:12px 0 24px}.tr h3{margin-top:52px;font-size:23px}.tr h3 span{font-size:12px;color:#56bda8;border:1px solid #365e56;border-radius:5px;padding:3px 7px;vertical-align:middle;white-space:nowrap}.tr h3 span.proposal{color:#e3ad49;border-color:#6c5937}.tr-kicker{font-family:monospace;color:#56bda8;letter-spacing:.13em}.tr-lead{font-size:19px;max-width:850px}.tr-note,.tr figcaption{font-size:13px;color:var(--ink-3);line-height:1.8}.tr-verdict{border-left:3px solid #56bda8;background:rgba(86,189,168,.06);padding:20px 24px;margin:24px 0}.tr-verdict p{margin:8px 0 0}.tr-links{display:flex;flex-wrap:wrap;gap:8px 22px;padding:14px 0;border-bottom:1px solid #34434d}.tr figure{margin:20px 0;background:#17222c;padding:18px;border:1px solid #34434d;border-radius:8px}.tr svg{display:block;width:100%;height:auto;font-family:'IBM Plex Sans KR',sans-serif}.tr-legend{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:12px;margin:10px 0 18px}.tr-legend i{display:inline-block;width:10px;height:10px;margin-right:6px}.tr-formula{padding:18px 22px;background:rgba(130,150,170,.09);border-radius:6px;font-size:15px}.tr-table{overflow:auto;margin:20px 0}.tr table{min-width:650px;width:100%;font-size:13px}.tr th,.tr td{padding:12px 14px;vertical-align:top}.tr-original-label{border-top:2px solid #56bda8;margin-top:65px;padding:24px 0;color:var(--ink-3)}@media(max-width:650px){.tr figure{padding:8px}.tr h3{font-size:20px}.tr-verdict{padding:14px}.tr-lead{font-size:16px}}
</style>'''
original = SOURCE.read_bytes()
original_sha = hashlib.sha256(original).hexdigest()
h = original.decode()
h = h.replace('<title>Squid Game 5 · 5.2 행동</title>', '<title>Squid Game 5 · 토큰과 과제 지속 · 검토 수정본</title>')
h = h.replace('</head>', css+'</head>', 1)
h = h.replace('href="e52.html#', 'href="#')
h = h.replace('<ol>', '<ol><li><a href="#token-review">토큰과 과제 지속 · 수정본</a></li>', 1)
h = h.replace('<section aria-labelledby="e52">', section+'<p class="tr-original-label">이하: 복사 시점의 기존 v19 분석 · 원래 지표의 해석 한계는 위 검토 참조</p>\n<section aria-labelledby="e52">', 1)
TARGET.write_text(h)
(HERE/'data.json').write_text(json.dumps({'source_html_sha256': original_sha, 'raw_root': str(ROOT),
    'inputs': inputs, 'unfinished_sessions': unfinished, 'common_seeds': sorted(common),
    'summary': summary, 'games': games}, ensure_ascii=False, indent=2))
assert SOURCE.read_bytes() == original, 'source changed during build'
print(json.dumps({'output': str(TARGET), 'games': len(games), 'source_sha256': original_sha,
    'ledger_max_error': 0, 'common_seeds': sorted(common), 'summary': summary}, ensure_ascii=False, indent=2))

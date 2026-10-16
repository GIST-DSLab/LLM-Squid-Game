"""Append two initiation-stratified views to the saved review, preserving its snapshot."""
import collections
import hashlib
import html
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
PAGE = HERE.parent / 'e52-token-review-2026-10-16.html'
SOURCE = HERE.parent / 'e52.html'
START, END = '<!-- transfer-origin:start -->', '<!-- transfer-origin:end -->'
MODELS = {
    'gpt-6-astra': ('Astra', '#ef777c'), 'claude-fable-5-1': ('Fable', '#dc75aa'),
    'claude-opus-5-5': ('Opus', '#a394f5'), 'gpt-6-sol': ('Sol', '#e3ad49'),
    'gpt-6-luna': ('Luna', '#48ba9c'),
}
data = json.loads((HERE / 'data.json').read_text())
source_before = SOURCE.read_bytes()
saved = PAGE.read_text()
if START in saved:
    left, rest = saved.split(START, 1)
    saved = left + rest.split(END, 1)[1]
frozen = {(g['model'], g['session_id']): g for g in data['games']}
collected = collections.defaultdict(list)
raw_hashes = {}
for record in data['inputs']:
    path = Path(record['path'])
    if path.name != 'events.jsonl':
        continue
    content = path.read_bytes()
    raw_hashes[str(path)] = hashlib.sha256(content).hexdigest()
    model = json.loads((path.parent / 'meta.json').read_text())['model']
    schedules = {}
    for line in content.decode().splitlines():
        e = json.loads(line)
        sid = e.get('session_id')
        key = model, sid
        if key not in frozen:
            continue
        if e['event'] == 'talk_schedule':
            for a, b, openers, chat in e['edges']:
                schedules[sid, e['round'], chat] = openers
        if e['event'] != 'gift' or e.get('status') != 'done':
            continue
        idx = len(collected[key])
        original = frozen[key]['gifts'][idx]
        assert (e['round'], e.get('phase'), e['amount'], e['balance_before']) == (
            original['round'], original['phase'], original['amount'], original['donor_before'])
        openers = schedules.get((sid, e['round'], e.get('chat_id')), [])
        if set(openers) == {e['src'], e['dst']}:
            origin = 'both'
        elif openers == [e['src']]:
            origin = 'donor'
        elif openers == [e['dst']]:
            origin = 'receiver'
        else:
            origin = 'unknown'
        collected[key].append({**original, 'model': model, 'session_id': sid,
            'seed': frozen[key]['seed'], 'chat_id': e.get('chat_id'),
            'src': e['src'], 'dst': e['dst'], 'openers': openers, 'origin': origin})
for key, g in frozen.items():
    assert len(collected[key]) == len(g['gifts']), (key, 'snapshot mismatch')
points = [p for ps in collected.values() for p in ps]
counts = collections.Counter(p['origin'] for p in points)

def center(ps, weighted=False):
    if not ps:
        return None
    weights = [p['amount'] if weighted else 1 for p in ps]
    return [sum(p[k]*w for p, w in zip(ps, weights))/sum(weights)
            for k in ('donor_after', 'receiver_after')]

def text(x, y, value, size=12, color='#dbe4ea', anchor='start'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{html.escape(str(value))}</text>'

centers = {}
def plot(origin, title):
    body = ''
    for i, (model, (label, color)) in enumerate(MODELS.items()):
        ps = [p for p in points if p['model'] == model and p['origin'] == origin]
        event_center, token_center = center(ps), center(ps, True)
        centers[origin, model] = {'n': len(ps), 'games_with_points': len({p['seed'] for p in ps}),
            'tokens': sum(p['amount'] for p in ps), 'event_center': event_center, 'token_center': token_center}
        gx, gy = 20+(i%3)*300, 30+(i//3)*265
        body += text(gx+125, gy, f'{label} · {len(ps)}건', 16, color, 'middle')
        def xy(x, y):
            return gx+40+(min(8,max(-1,x))+1)/9*215, gy+205-(min(8,max(-1,y))+1)/9*170
        for v in (0, 1, 4, 8):
            xx, yy = xy(v, v)
            body += text(xx, gy+222, str(v), 10, '#a8b5bf', 'middle')+text(gx+33, yy+3, str(v), 10, '#a8b5bf', 'end')
        xline, yline = xy(1, 1)
        body += f'<path d="M{xline} {gy+35}V{gy+205}M{gx+40} {yline}H{gx+255}" stroke="#7d8e99" stroke-dasharray="4 4"/>'
        x0, y0 = xy(-1, -1); x1, y1 = xy(8, 8)
        body += f'<path d="M{x0} {y0}L{x1} {y1}" stroke="#667481" stroke-dasharray="2 5" opacity=".65"/>'
        body += text(gx+40, gy+24, '받는 쪽 여유 ↑', 10, '#a8b5bf')
        for p in ps:
            x, y = p['donor_after'], p['receiver_after']; cx, cy = xy(x, y)
            tip = (f'seed {p["seed"]} R{p["round"]} {p["phase"]} chat {p["chat_id"]}: '
                   f'GIVE {p["amount"]}; donor {x:.2f}, recipient {p["receiver_before"]:.2f}→{y:.2f}; '
                   f'opened by {", ".join(p["openers"])}')
            body += f'<circle cx="{cx}" cy="{cy}" r="{min(8,2+p["amount"]/6000)}" fill="{color}" fill-opacity=".35" stroke="{color}"><title>{html.escape(tip)}</title></circle>'
        if ps:
            cx, cy = xy(*event_center)
            body += f'<path d="M{cx} {cy-8}L{cx+8} {cy}L{cx} {cy+8}L{cx-8} {cy}Z" fill="#17222c" stroke="white" stroke-width="2"><title>건수 중심: {event_center[0]:.3f}, {event_center[1]:.3f}</title></path>'
            cx, cy = xy(*token_center)
            body += f'<path d="M{cx-7} {cy}H{cx+7}M{cx} {cy-7}V{cy+7}" stroke="{color}" stroke-width="4"><title>토큰량 가중 중심: {token_center[0]:.3f}, {token_center[1]:.3f}</title></path>'
        else:
            body += text(gx+145, gy+120, '해당 이전 없음 · 중심 NA', 12, '#a8b5bf', 'middle')
        body += text(gx+150, gy+245, '주는 쪽 여유 →', 12, anchor='middle')
    result = f'<svg viewBox="0 0 920 560" role="img" aria-label="{title}" xmlns="http://www.w3.org/2000/svg"><title>{title}</title>{body}</svg>'
    ET.fromstring(result)
    return result

offer = plot('donor', '제공자만 대화를 개시한 실제 이전과 모델별 무게중심')
request = plot('receiver', '수신자만 대화를 개시한 실제 이전과 모델별 무게중심')
rows = ''
for origin, name in [('donor', '제공자 개시'), ('receiver', '수신자 개시')]:
    for model, (label, _) in MODELS.items():
        s = centers[origin, model]
        fmt = lambda p: 'NA' if p is None else f'({p[0]:.2f}, {p[1]:.2f})'
        rows += f'<tr><td>{name}</td><th>{label}</th><td>{s["n"]} / {s["games_with_points"]}</td><td>{fmt(s["event_center"])}</td><td>{fmt(s["token_center"])}</td></tr>'
block = f'''{START}
<h4 id="transfer-origin">03-A · 제공자 개시 / 수신자 개시로 나눠 보기</h4>
<p>위의 전체 그래프는 유지한다. 아래는 <b>누가 대화를 먼저 열었는지</b>에 따라 기존 실제 이전 점을 나눈 것이다. 제공자만 연 대화를 ‘제공자 개시’, 수신자만 연 대화를 ‘수신자 개시’로 정의했다. 자연어의 “주겠다/달라”를 의미 판정한 분류는 아니며, 대화를 연 쪽과 실제 발화 의도가 항상 일치한다고 가정하지 않는다.</p>
<p class="tr-note">분류 근거: 엔진 talk_schedule의 개시자 목록을 session·round·chat_id와 이벤트 순서로 GIVE에 연결했다. 전체 {len(points)}건 중 제공자 개시 {counts['donor']}건 · 수신자 개시 {counts['receiver']}건 · 양쪽 동시 개시 {counts['both']}건 · 미확인 {counts['unknown']}건. 양쪽 동시 개시·미확인은 아래 두 그림에서 제외하고 위 전체 그래프에 남겼다. 미실행 제안·거절된 요청은 실제 이전 좌표가 없어 이 그림에 포함하지 않는다.</p>
<h4>주는 쪽이 시작한 대화 · 제공자 개시 {counts['donor']}건</h4>
<figure>{offer}<figcaption>기존 그래프와 같은 좌표·눈금·점 크기. 원은 실행된 GIVE, 흰 마름모 ◇는 이전 건수 중심, 색 십자 +는 이전 토큰량 가중 중심이다. 점선 대각선은 두 자리의 여유가 같은 곳이다. 가로·세로 점선 1은 기존과 같은 벌금 한 번어치 경계다.</figcaption></figure>
<h4>받는 쪽이 시작한 대화 · 수신자 개시 {counts['receiver']}건</h4>
<figure>{request}<figcaption>왼쪽 또는 오른쪽 이동은 제공자의 남은 여유, 위 또는 아래 이동은 수신자의 남은 여유 차이다. 두 그림 모두 같은 제공자·수신자 축을 사용하며 요청한 쪽을 가로축으로 바꾸지 않는다. 마름모와 십자가 겹치면 두 중심이 비슷한 것이다.</figcaption></figure>
<h4>모델별 무게중심 · (주는 쪽 여유, 받는 쪽 여유)</h4>
<div class="tr-table"><table><thead><tr><th>대화 시작</th><th>모델</th><th>이전 건 / 해당 판</th><th>◇ 건수 중심</th><th>+ 토큰량 가중 중심</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="tr-formula">건수 중심 = (Σx / n, Σy / n)<br>토큰량 가중 중심 = (Σg·x / Σg, Σg·y / Σg) · g = 실제 이전 토큰량</div>
<p><b>해석:</b> 건수 중심은 이전 한 건을 같은 무게로 본 대표적인 분배 후 상태이며, 토큰량 가중 중심은 큰 이전이 주로 어디에 놓였는지 보여 준다. 계산에는 경계로 잘라 표시하기 전의 실제 좌표를 사용했다. 중심이 대각선 아래이면 평균적으로 제공자가 더 많은 여유를 남겼다는 뜻이지, 이기적 동기라는 뜻은 아니다.</p>
<p class="tr-note">중심은 실제 이전에 조건부인 기술통계다. 시작 잔액·라운드·solver 역할·예고된 벌금·같은 판 안의 반복 이전이 다르면 중심도 달라질 수 있다. 같은 상태에서 개시 방향만 바꾼 인과효과나, 거절을 포함한 전체 분배 정책의 점수가 아니다. 낮은 건수와 서로 다른 산포를 가리지 않도록 원래 점을 함께 남겼으며 신뢰구간은 산출하지 않았다. <a href="token-review-2026-10-16/origin-data.json">분류·중심 계산 자료</a>. 재현: <code>python3 token-review-2026-10-16/add_origin_plots.py</code> (저장된 56판 스냅샷 사용).</p>
{END}'''
section = saved.index('<h3 id="token-transfer">')
insert = saved.index('<div class="tr-formula">', section)
updated = saved[:insert]+block+saved[insert:]
assert updated.replace(block, '', 1) == saved
PAGE.write_text(updated)
output = {'classification': 'sole chat initiator relative to actual gift direction; not semantic intent',
    'base_review_sha256': hashlib.sha256(saved.encode()).hexdigest(), 'counts': dict(counts),
    'raw_inputs_sha256': raw_hashes, 'points': points,
    'centers': {origin: {m: centers[origin, m] for m in MODELS} for origin in ('donor', 'receiver')}}
(HERE/'origin-data.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
assert SOURCE.read_bytes() == source_before
print(json.dumps({'counts': dict(counts), 'centers': output['centers'],
    'original_unchanged': True, 'existing_review_preserved': True}, ensure_ascii=False, indent=2))

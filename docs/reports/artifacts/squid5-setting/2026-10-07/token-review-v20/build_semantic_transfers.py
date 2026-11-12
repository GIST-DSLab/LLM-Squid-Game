"""Render audited speech-based transfer groups and decision-time deficit cases."""
import collections
import hashlib
import html
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
PAGE = HERE / 'work.html'  # v20 working copy (token-review-v20/build.py)
SOURCE = HERE.parent / 'e52.html'
START, END = '<!-- transfer-origin:start -->', '<!-- transfer-origin:end -->'
MODELS = {
    'gpt-6-astra': ('Astra', '#ef777c'),
    'claude-opus-5-5': ('Opus', '#a394f5'), 'gpt-6-sol': ('Sol', '#e3ad49'),
    'gpt-6-luna': ('Luna', '#48ba9c'),
}
LABELS = {'offer': '주겠다 먼저', 'request': '나에게 달라 먼저', 'both': '동시 요청·제안',
          'ambiguous': '선후·의미 불명확', 'redirected': '제3자·반대 방향에서 전환'}
source_before = SOURCE.read_bytes()
evidence = json.loads((HERE / 'semantic-evidence.json').read_text())
annotations = json.loads((HERE / 'semantic-annotations.json').read_text())
data = json.loads((HERE / 'data.json').read_text())
assert annotations['_meta']['evidence_sha256'] == hashlib.sha256((HERE / 'semantic-evidence.json').read_bytes()).hexdigest()
assert len(evidence['points']) == sum(len(g['gifts']) for g in data['games'])
for uid, u in evidence['utterances'].items():
    if u['kind'] in ('say', 'leave'):
        fingerprint = hashlib.sha256(json.dumps({k: u[k] for k in
            ['line', 'speaker', 'partner', 'text', 'kind', 'session_id', 'round', 'phase']}, sort_keys=True).encode()).hexdigest()
        assert annotations[uid]['fingerprint'] == fingerprint

points = []
for original in evidence['points']:
    p = dict(original)
    candidates, uncertain, other, acceptances = [], [], [], []
    for uid in p['utterances']:
        u = evidence['utterances'][uid]
        label = 'O' if u['kind'] == 'give' else 'R' if u['kind'] == 'ask' else annotations[uid]['label']
        rank = 0 if u['opening'] else u['line']
        matches = (label == 'O' and u['speaker'] == p['src']) or (label == 'R' and u['speaker'] == p['dst'])
        if matches:
            candidates.append((rank, 'offer' if label == 'O' else 'request', uid))
        elif label == 'U':
            uncertain.append((rank, uid))
        elif label == 'A':
            acceptances.append((rank, uid))
        elif label in ('T', 'O', 'R'):
            other.append((rank, uid))
    assert candidates, p['id']  # Every executed gift has its own explicit GIVE decision.
    first_rank = min(c[0] for c in candidates)
    # Acceptance of an unseen earlier offer cannot establish a new request-first event.
    uncertain.extend((rank, uid) for rank, uid in acceptances if rank < first_rank)
    first = [c for c in candidates if c[0] == first_rank]
    kinds = {c[1] for c in first}
    category = 'both' if len(kinds) == 2 else first[0][1]
    direct_give = all(evidence['utterances'][c[2]]['kind'] == 'give' for c in first)
    if any(rank <= first_rank for rank, _ in uncertain):
        category = 'ambiguous'
    elif direct_give and any(rank < first_rank for rank, _ in other):
        category = 'redirected'
    signals = [evidence['utterances'][c[2]] for c in first]
    # All opening statements share the same displayed state, not serialization order.
    assert len({(u['balances'][p['src']], u['balances'][p['dst']],
                 u['pending'].get(p['src'], 0), u['pending'].get(p['dst'], 0)) for u in signals}) == 1
    u = signals[0]
    donor, recipient = u['balances'][p['src']], u['balances'][p['dst']]
    dp, rp = u['pending'].get(p['src'], 0), u['pending'].get(p['dst'], 0)
    p.update(category=category, signal_ids=[c[2] for c in first],
        uncertain_ids=[uid for rank, uid in uncertain if rank <= first_rank],
        other_ids=[uid for rank, uid in other if rank < first_rank],
        direct_give=direct_give, donor_at_signal=donor, recipient_at_signal=recipient,
        donor_pending=dp, recipient_pending=rp,
        immediate_deficit=rp > 0 and recipient <= rp,
        recipient_without_one_more_charge=recipient-rp <= 6000,
        donor_with_one_more_charge=donor-dp > 6000,
        minimum_to_survive=max(0, rp+1-recipient) if rp > 0 else 0)
    points.append(p)
counts = collections.Counter(p['category'] for p in points)
deficit = [p for p in points if p['immediate_deficit']]
deficit_counts = collections.Counter(p['category'] for p in deficit)

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
        ps = [p for p in points if p['model'] == model and (p['immediate_deficit'] if origin == 'deficit' else p['category'] == origin)]
        event_center, token_center = center(ps), center(ps, True)
        centers[origin, model] = {'n': len(ps), 'games_with_points': len({p['session_id'] for p in ps}),
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
                   f'{LABELS[p["category"]]}; 발화 직전 수신자 {p["recipient_at_signal"]:,}, 예정 벌금 {p["recipient_pending"]:,}; 근거 {p["signal_ids"]}')
            radius = min(8, 2+p['amount']/6000)
            if origin == 'deficit' and p['category'] == 'offer':
                mark = f'<path d="M{cx} {cy-radius}L{cx+radius} {cy+radius}H{cx-radius}Z"'
            elif origin == 'deficit' and p['category'] == 'both':
                mark = f'<rect x="{cx-radius}" y="{cy-radius}" width="{2*radius}" height="{2*radius}"'
            elif origin == 'deficit' and p['category'] in ('ambiguous', 'redirected'):
                mark = f'<path d="M{cx-radius} {cy-radius}L{cx+radius} {cy+radius}M{cx-radius} {cy+radius}L{cx+radius} {cy-radius}"'
            else:
                mark = f'<circle cx="{cx}" cy="{cy}" r="{radius}"'
            body += mark+f' fill="{color}" fill-opacity=".35" stroke="{color}" stroke-width="1.5"><title>{html.escape(tip)}</title>'+('</circle>' if mark.startswith('<circle') else '</rect>' if mark.startswith('<rect') else '</path>')
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



offer_plot = plot('offer', '실제 발화에서 주겠다는 제안이 먼저인 이전')
request_plot = plot('request', '실제 발화에서 나에게 달라는 요청이 먼저인 이전')
deficit_plot = plot('deficit', '방향이 명확한 발화 당시 확정된 벌금을 낼 수 없었던 수신자에 대한 이전')
count_text = ' · '.join(f'{name} {counts[key]}건' for key, name in LABELS.items())
deficit_text = ' · '.join(f'{name} {deficit_counts[key]}건' for key, name in LABELS.items())
rows = ''
for group, name in [('offer', '주겠다 먼저'), ('request', '나에게 달라 먼저'), ('deficit', '실제 부족 전체')]:
    for model, (label, _) in MODELS.items():
        c = centers[group, model]
        ps = [p for p in points if p['model'] == model and
              (p['immediate_deficit'] if group == 'deficit' else p['category'] == group)]
        fmt = lambda v: 'NA' if v is None else f'({v[0]:.2f}, {v[1]:.2f})'
        rows += (f'<tr><td>{name}</td><th>{label}</th><td>{c["n"]} / {c["games_with_points"]}</td>'
                 f'<td>{sum(p["immediate_deficit"] for p in ps)}</td>'
                 f'<td>{sum(p["donor_with_one_more_charge"] for p in ps)} / {c["n"]}</td>'
                 f'<td>{fmt(c["event_center"])}</td><td>{fmt(c["token_center"])}</td></tr>')
audit_rows = ''
for p in points:
    quote_ids = list(dict.fromkeys(p['uncertain_ids'] + p['other_ids'] + p['signal_ids']))
    quotes = []
    for uid in quote_ids:
        u = evidence['utterances'][uid]
        source = Path(evidence['sources'][u['source']]['path']).as_uri()
        quotes.append(f'<a href="{html.escape(source)}">L{u["line"]}</a> '
                      f'{u["speaker"]} → {u["partner"]}: {html.escape(u["text"])}')
    audit_rows += (f'<tr><th>{p["id"]}<br>{MODELS[p["model"]][0]} · seed {p["seed"]}<br>'
        f'R{p["round"]} {p["phase"]} / {p["chat_id"]}</th><td>{LABELS[p["category"]]}<br>'
        f'{p["src"]} → {p["dst"]}<br>{p["amount"]:,} tokens</td><td>'
        f'제공 {p["donor_at_signal"]:,} − {p["donor_pending"]:,}<br>'
        f'수신 {p["recipient_at_signal"]:,} − {p["recipient_pending"]:,}<br>'
        f'현재 부족: {"예" if p["immediate_deficit"] else "아니오"}</td>'
        f'<td>{"<br>".join(quotes)}</td></tr>')
block = f'''{START}
<h4 id="transfer-origin">03-A · 실제 발화: ‘주겠다’와 ‘나에게 달라’ 중 무엇이 먼저였나</h4>
<p>대화를 연 사람이 아니라 <b>실제 이전 방향에 맞는 발화 내용</b>으로 다시 분류했다. 해당 대화·단계에서 “내가 너에게 주겠다”가 먼저면 제공 제안, “네가 나에게 달라”가 먼저면 수신자 요청이다. “필요하면 내게 요청해”라는 조건부 제공도 포함한다. 단순 안부·풀이 조언·필요 여부 질문·검토하겠다는 말은 제공 약속으로 확정하지 않는다. 앞선 라운드의 약속까지 거슬러 올라가는 분류는 아니다.</p>
<p class="tr-note">{len(data['games'])}판, 실제 실행된 이전 {len(points)}건: {count_text}. 자연어 SAY/LEAVE {sum(u['kind'] in ('say', 'leave') for u in evidence['utterances'].values())}개를 문맥과 함께 읽어 의미 라벨을 저장하고, ASK/GIVE의 실제 방향과 연결했다. 첫 발화는 동시에 생성되므로 파일의 기록 순서로 선후를 정하지 않는다. 미실행 제안·거절된 요청은 포함하지 않아 전체 제안·요청 발생률을 뜻하지 않는다. 대여·상환·조건부 약속을 포함하므로 무상 도움이나 관대함만의 지표도 아니다.</p>
<h4>‘주겠다’가 먼저인 이전 · {counts['offer']}건</h4>
<figure>{offer_plot}<figcaption>“4,000을 줄 수 있다” → ASK → GIVE는 이 그림에 들어간다. 선행 요청 없이 바로 GIVE한 경우도 포함한다. 기존 전체 그래프와 같은 이전 직후 좌표·눈금·점 크기다. ◇는 건수 중심, +는 이동한 token량 가중 중심이다.</figcaption></figure>
<h4>‘나에게 달라’가 먼저인 이전 · {counts['request']}건</h4>
<figure>{request_plot}<figcaption>수신자가 자기 몫을 요청한 뒤 실행된 이전이다. 다른 에이전트만 도와달라는 말은 자기 몫 요청으로 세지 않는다. 양쪽 첫 발화에 요청·제안이 모두 있거나 선후를 확정하지 못한 경우는 위 두 그림에서 제외하고 기존 전체 그래프에 남겼다.</figcaption></figure>
<h4 id="transfer-deficit">03-B · 실제로 이번 벌금이 부족했던 경우 · {len(deficit)}건</h4>
<div class="tr-formula">실제 부족 = 예정 벌금 &gt; 0 이고, 기준 발화 직전 수신자 잔액 − 예정 벌금 ≤ 0<br>생존에 필요한 최소 추가량 = 예정 벌금 + 1 − 수신자 잔액</div>
<p>모델의 “부족하다”는 말 대신 <b>실제 입력에 보인 잔액과 확정된 벌금</b>으로 골랐다. 기준 시점은 해당 이전 방향이 명확한 최초 요청·제안 직전이며, 사전 발화가 없으면 GIVE 결정 직전이다. 양쪽 동시 발화는 공통 입력 상태를 쓴다. 이전 선후가 모호한 건도 처음 확인 가능한 방향 발화를 기준으로 부족 여부를 계산하고 ×로 구분했다. SOLVE 전의 잠재적인 실패 벌금과 다음 라운드용 여유 부족은 여기 넣지 않았다.</p>
<p class="tr-note">{deficit_text}. 같은 수신자가 여러 번 지원받으면 실제 이전마다 한 점이다. 분류 시점 이후 다른 지원이나 대화 비용으로 잔액이 바뀔 수 있으므로, 이 수는 최종 구조 성공 건수나 구조가 필요했던 고유 에이전트 수가 아니다.</p>
<figure>{deficit_plot}<figcaption>▲ 제공 제안 먼저 · ○ 자기 몫 요청 먼저 · □ 양쪽 동시 · × 선후 불명확/제3자 전환. 색은 모델이다. 축은 비교를 위해 기존과 동일하게 <b>이전 직후</b>의 (잔액 − 예정 벌금) ÷ 6,000이다. 이 그림은 발화 당시 부족했던 사례를 골라서 이전 후 어디에 도달했는지 보여 준다. ◇와 +는 각 모델의 이 부분집합 전체 중심이다. 모든 그림의 표시 범위는 −1~8이며 중심 계산에는 자르기 전 값을 사용한다.</figcaption></figure>
<h4>모델별 무게중심과 발화 당시의 자원 상태</h4>
<div class="tr-table"><table><thead><tr><th>분류</th><th>모델</th><th>이전 건 / 해당 판</th><th>이번 벌금 부족 건</th><th>제공자 여유 있음 / 전체</th><th>◇ 건수 중심</th><th>+ token량 가중 중심</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="tr-note">‘제공자 여유 있음’은 기준 발화 직전 제공자 잔액 − 예정 벌금 &gt; 6,000, 즉 이미 예정된 벌금 외에 벌금 한 번을 더 내고도 양수가 남는 상태다. 요청·제안이라는 언어행위와 실제 부족·여유라는 장부 상태를 독립적으로 계산했다. 모델별 {len(data['games']) // len(MODELS)}판이지만 실제 이전 횟수는 다르다. 건수가 0이면 중심은 NA다.</p>
<div class="tr-formula">건수 중심 = (Σx / n, Σy / n)<br>token량 가중 중심 = (Σg·x / Σg, Σg·y / Σg) · g = 실제 이전량</div>
<p class="tr-note">중심은 실행된 이전의 평균 결과이며 전략의 우열·동기·인과효과를 뜻하지 않는다. 시작 자원, 역할, 단계, 반복 이전과 산포의 영향을 받는다. 신뢰구간은 산출하지 않았다. <a href="token-review-v20/origin-data.json">분류와 중심 수치</a> · <a href="token-review-v20/semantic-evidence.json">발화·입력 잔액·원시 출처</a> · <a href="token-review-v20/semantic-annotations.json">의미 판정 라벨</a>.</p>
<details><summary>실제 이전 {len(points)}건의 발화 근거와 부족 판정 펼치기</summary>
<div class="tr-table"><table><thead><tr><th>이전 / 판</th><th>분류 / 방향 / 이전량</th><th>기준 발화 직전 잔액 − 예정 벌금</th><th>근거 발화와 원시 행</th></tr></thead><tbody>{audit_rows}</tbody></table></div></details>
{END}'''
saved = PAGE.read_text()
if START in saved:
    left, rest = saved.split(START, 1)
    saved = left + rest.split(END, 1)[1]
section = saved.index('<h3 id="token-transfer">')
insert = saved.index('<div class="tr-formula">', section)
updated = saved[:insert] + block + saved[insert:]
assert updated.replace(block, '', 1) == saved
PAGE.write_text(updated)
output = {'method': annotations['_meta'], 'base_review_sha256': hashlib.sha256(saved.encode()).hexdigest(),
          'games': len(data['games']), 'counts': dict(counts), 'deficit_counts': dict(deficit_counts),
          'points': points, 'centers': {group: {m: centers[group, m] for m in MODELS}
                                     for group in ('offer', 'request', 'deficit')}}
(HERE / 'origin-data.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
assert SOURCE.read_bytes() == source_before
print(json.dumps({'games': output['games'], 'transfers': len(points), 'counts': dict(counts),
                  'deficit': len(deficit), 'deficit_counts': dict(deficit_counts),
                  'original_unchanged': True, 'existing_review_preserved': True}, ensure_ascii=False, indent=2))

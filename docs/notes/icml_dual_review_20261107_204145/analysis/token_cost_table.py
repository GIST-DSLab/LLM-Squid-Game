"""Describe generation debits in the frozen public v33 cohort (50 games, seeds 4101-4110).

Read only the events files named and hashed in cohort_public_20261105.json.
No model calls, engine changes, or manuscript writes. L is measured at call start.
"""
import csv
import hashlib
import json
import lzma
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, quantiles

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
COHORT = ROOT / 'paper/cogsci2027/results/cohort_public_20261105.json'
data = json.loads(COHORT.read_text())
games = {g['session_id']: g for g in data['games']}
assert len(games) == 50
assert set(data['seeds']) == set(range(4101, 4111))
starts, rounds, results, calls, source_checks = {}, {}, {}, [], []


def key(e):
    return (e['session_id'], e['round'], e['kind'], e.get('turn'), e.get('phase'), e.get('tick'))


for source in data['sources']:
    if 'events.jsonl' not in source['path']:
        continue
    path = Path(source['path'])
    assert 'e52_v33' in path.parts
    raw = lzma.decompress(path.read_bytes()) if path.suffix == '.xz' else path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == source['sha256_decompressed'], str(path)
    source_checks.append(dict(path=str(path), sha256=digest))
    for line, text in enumerate(raw.splitlines(), 1):
        e = json.loads(text)
        if e.get('session_id') not in games:
            continue
        pair = (e['session_id'], e.get('round'))
        if e['event'] == 'round_start':
            rounds[pair] = e
        elif e['event'] == 'results':
            results[pair] = e
        elif e['event'] == 'call_start':
            assert key(e) not in starts
            starts[key(e)] = e
        elif e['event'] == 'call' and e['kind'] in ('talk', 'solve'):
            keep = ['session_id', 'round', 'kind', 'turn', 'phase', 'tick', 'agent',
                    'used', 'out_tokens', 'cap', 'truncated', 'overdrawn', 'format_error']
            calls.append({k: e.get(k) for k in keep} | {'source': str(path), 'line': line})

rows, ticks = [], defaultdict(list)
for e in calls:
    g, start = games[e['session_id']], starts[key(e)]
    pair = (e['session_id'], e['round'])
    fee = 24000 / len(rounds[pair]['taking_part'])
    pending = results[pair]['pending'].get(e['agent'], 0) if e['phase'] == 'rescue' else 0
    balance = start['balances'][e['agent']]
    margin = (balance - pending) / fee
    band = '<1' if margin < 1 else '1-2' if margin < 2 else '2-4' if margin < 4 else '>=4'
    refunded = results[pair]['returned'].get(e['agent'], 0) if e['kind'] == 'solve' else 0
    assert 0 <= refunded <= e['used']
    row = dict(model=g['model'], seed=g['seed'], session_id=e['session_id'],
               round=e['round'], phase=e['phase'], tick=e['tick'], agent=e['agent'],
               kind=e['kind'], L=margin, band=band, balance_before=balance,
               used=e['used'], out_tokens=e['out_tokens'], refunded=refunded,
               net_generation_debit=e['used']-refunded, truncated=bool(e['truncated']),
               format_error=bool(e['format_error']), source=e['source'], line=e['line'])
    rows.append(row)
    if e['kind'] == 'talk':
        ticks[key(e)].append(row)


def stats(group):
    if not group:
        return dict(n_calls=0, n_games=0, mean=None, median=None, q1=None, q3=None,
                    net_mean=None, out_mean=None, truncated=0, format_errors=0)
    values = [r['used'] for r in group]
    q = quantiles(values, n=4, method='inclusive') if len(values) > 1 else values * 3
    return dict(n_calls=len(group), n_games=len({r['session_id'] for r in group}),
                mean=mean(values), median=median(values), q1=q[0], q3=q[2],
                net_mean=mean(r['net_generation_debit'] for r in group),
                out_mean=mean(r['out_tokens'] for r in group),
                truncated=sum(r['truncated'] for r in group),
                format_errors=sum(r['format_error'] for r in group))


aggregate, stratified = [], []
for model in data['models']:
    for kind in ('talk', 'solve'):
        group = [r for r in rows if r['model'] == model and r['kind'] == kind]
        s = stats(group)
        old = data['call_quality'][model][kind]
        assert s['n_calls'] == old['n']
        assert abs(s['mean'] - old['mean_charged_tokens']) < 1e-9
        aggregate.append(dict(model=model, kind=kind, **s))
        for phase in (['all', 'prep', 'rescue'] if kind == 'talk' else ['all']):
            for band in ('<1', '1-2', '2-4', '>=4'):
                selected = [r for r in group if r['band'] == band and (phase == 'all' or r['phase'] == phase)]
                stratified.append(dict(model=model, kind=kind, phase=phase, band=band, **stats(selected)))
assert sum(r['kind'] == 'solve' and r['L'] < 1 for r in rows) == 19


def write_csv(name, records):
    with (OUT / name).open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


write_csv('token_cost_calls.csv', rows)
write_csv('token_cost_by_L.csv', stratified)
write_csv('token_cost_overall.csv', aggregate)
write_csv('talk_tick_totals.csv', [dict(session_id=k[0], round=k[1], phase=k[4], tick=k[5],
          model=v[0]['model'], n_called=len(v), total_used=sum(r['used'] for r in v),
          mean_used_per_called_agent=mean(r['used'] for r in v)) for k, v in ticks.items()])
report = ['# 소모율: 기본 v33 50판', '',
          '시드 4101–4110, 모델별 10판. 각 호출 시작 잔액에서 확정 미납 벌금을 제외하여 L을 계산했다. '
          '이 값은 해당 응답의 비용과 행동이 반영되기 전 상태다. 모든 호출을 포함하므로 '
          '동료가 있는 응답만 센 그림 4의 5,949개와 분모가 다르다.', '',
          'TALK 단위는 에이전트의 응답 1회다. 한 틱 전체 토큰은 참여·호출 인원에 따라 달라지므로 '
          '별도 CSV에 호출 인원과 함께 저장했다. CALL의 used는 장부 차감량, out_tokens는 제공사 보고 생성량이다. '
          '이 표가 서로 다른 제공사의 실제 계산량 동등성까지 검증하지는 않는다.', '',
          '평균과 중앙값 [Q1, Q3]은 호출 가중 기술통계다. 호출들을 독립 표본으로 추론하지 않는다. '
          '순생성비용은 SOLVE 정답 환급을 뺀 값이며, 오답 벌금·GIVE·상금은 제외한다. '
          '0표본 구간은 값 없음으로 남긴다. 전후 TALK 분리값과 절단·형식 오류 수는 CSV에 있다.', '']
for kind in ('talk', 'solve'):
    report += [f'## {kind.upper()}', '', '| 모델 | 호출 전 L | 호출 수 / 판 수 | 평균 차감 | 중앙값 [Q1, Q3] | 환급 후 순생성비용 평균 |',
               '|---|---|---:|---:|---:|---:|']
    for r in stratified:
        if r['kind'] != kind or r['phase'] != 'all':
            continue
        vals = ('—', '—', '—') if not r['n_calls'] else (
            f"{r['mean']:.1f}", f"{r['median']:.1f} [{r['q1']:.1f}, {r['q3']:.1f}]", f"{r['net_mean']:.1f}")
        report.append(f"| {r['model']} | {r['band']} | {r['n_calls']} / {r['n_games']} | {vals[0]} | {vals[1]} | {vals[2]} |")
    report.append('')
(OUT / 'token_cost_by_L.md').write_text('\n'.join(report) + '\n')
(OUT / 'token_cost_validation.json').write_text(json.dumps(dict(
    cohort=str(COHORT), cohort_sha256=hashlib.sha256(COHORT.read_bytes()).hexdigest(),
    source_checks=source_checks, n_games=50, n_calls=len(rows), n_ticks=len(ticks),
    exact_match_to_existing_call_counts_and_means=True,
    low_L_solve_count=19, statistics='descriptive call-weighted; no independent-call significance tests'),
    ensure_ascii=False, indent=2) + '\n')
print(json.dumps(dict(n_games=50, n_calls=len(rows), n_ticks=len(ticks), overall=aggregate), ensure_ascii=False))

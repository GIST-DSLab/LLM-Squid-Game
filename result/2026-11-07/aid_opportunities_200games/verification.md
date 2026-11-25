# 200판 지원 기회 분석 독립 검증

독립 검증자: /root/audit_raw_findings. 2026-11-07 KST. G02/G04/G07/G08의 이번 분석 범위만 검증했다. 프로젝트 전체 게이트 판정, 원고 수정, 모델 호출은 수행하지 않았다. 분석 코드와 기존 결과 파일은 변경하지 않았다.

## 판정

**검증된 원시 추출·집계·통계에서 미해결 Critical 오류는 없다.** 분석 스크립트를 import하거나 실행하지 않고, 동결 manifest의 200판을 다시 순회해 311개 pair-tick의 원시 계산 열 73개와 primary 77개 최초 기회를 재구성했다. 25개 event 파일 해시와 manifest/protocol/script/rubric 해시도 일치했다. 지정 primary77 전체에 대해 비용 예측, ASK 노출, 최초 선택, 실제 이전, 이후 이전, 다음 라운드 상태를 대조했다.

독립 재계산 명령은 아래 원시·통계 Python 블록이다. 둘 다 종료 코드 0으로 실행했으며, 추가 이유 코딩 검증도 종료 코드 0이다. 작성 중 CSV 열 이름 변경으로 한 차례 검증기의 summary 키가 불일치했으나, 최종 명명에 맞춘 재실행에서 모든 검사가 통과했다. 이 중간 중단은 수치 불일치가 아니었다.

| 명세 | 기회 수 | 게임 수 | 즉시 양수 이전 | 나중 양수 이전 | 최초 기회부터 해당 제공자의 완료 이전 없음 |
|---|---:|---:|---:|---:|---:|
| primary: 현재 라운드 ASK 노출, 예상 비용 1배 | 77 | 39 | 41 | 18 | 18 |
| rescue ASK만 노출 | 60 | 33 | 41 | 9 | 10 |
| 예상 비용 0배 | 80 | 39 | 42 | 19 | 19 |
| 예상 비용 2배 | 76 | 38 | 40 | 18 | 18 |
| ASK 노출을 요구하지 않은 장부상 기회 | 141 | 49 | 26 | 63 | 52 |

모든 행은 해당 명세의 **첫 적격 tick을 새로 선정**한다. 따라서 이 표의 서로 다른 명세를 동일한 77행의 단순 부분집합으로 보지 않는다.

## 분모와 구현 정합성

- 원시 rescue talk_start는 총 **1,558구간**이다. 참여자 0으로 실제 call_start가 없는 **33구간**을 제외한 1,525구간이 summary의 rescue_phases이다. 그중 다인 구간 1,422, pending 벌금 양수 구간 515가 일치했다. 원시 파일에 보존된 미완결 재시도 5세션은 동결 manifest의 선택된 200판 밖이며, 여전히 별도 실패 기록이다.
- 참여 집합은 첫 rescue talk_start의 참여자와 각 call_start의 양수 잔액으로 독립 구성했다. 이 집합은 코드의 result.part 중 양수 잔액 집합과 모든 tick에서 같았다. EXIT 보존 잔액과 이미 꺼진 좌석은 합계에 들어가지 않았다. DONE으로 호출되지 않은 참여자는 합계에 남았다.
- 비용 예측은 현재 call_start보다 앞선 동일 에이전트 TALK 호출의 최근 최대 5개 used 중앙값으로 다시 계산했다. 같은 tick 비용은 들어가지 않았다. primary77의 제공자는 모두 이전 TALK 기록이 있었다. 호출되지 않은 수혜자 비용은 0이다.
- ASK 노출은 raw ASK의 sender/recipient/round/phase/tick/amount뿐 아니라 실제 donor.user의 **완전한 ASK 첫 문장**과 대조했다. 현재 rescue와 같은 tick의 ASK가 노출된 것으로 처리된 사례는 없었다. 이전 prep ASK는 허용되며, NEW가 아닌 재노출도 유효하다. 공개 자유문 도움 요청은 primary의 보수적 ASK 기준에 포함되지 않는다.
- 77개 모두 그 호출의 현재 벌금 부족 수혜자는 1명이었다. 다만 동일 수혜자를 여러 제공자의 기회로 셀 수 있으므로 77은 **49개 고유 수혜자-라운드**에 대응한다. target_shutdown=23은 pair 행 수이고, 고유 꺼진 수혜자-라운드는 **18개**다.
- 지원 결과로 적격성을 선별하지 않았다. 사후 actual_window와 실제 비용의 affordability/group checks는 별도 민감도이다. primary77 중 actual_window 74도 일치하며, 제외된 3행은 같은 tick 수혜자의 전액 이전 후 꺼짐을 포함한다.

## 수정 후 확인한 정의

검토 중 발견한 두 명명/구현 문제는 수정 후 확인했다.

1. 여유 기준을 높일 때 기존 최초 기회만 필터한 값은 first_opportunity_reserve_subsets로 명명했다. 별도의 reserve_eligibility_sensitivity는 전체 tick에서 강화된 기준의 첫 적격 기회를 다시 선택한다. 여유 1벌금분 기준은 각각 **65/34 지원**, **66/35 지원**으로 다르며 두 값 모두 재현됐다. 2벌금분은 양쪽 모두 55/30이다.
2. parsed dict가 존재해도 모든 명령이 dropped된 malformed 응답은 유효하지 않다. 최종 response_usable은 format_error도 배제해 **72개**가 된다. 전체77의 비유효 5개는 빈 응답4 + 잘못된 GIVE 형식1이며, 모두 즉시 무지원 행이다. 이들을 명시적 거절로 바꾸지 않는다.

## Warning: 지원·실패·자기보존 해석

**W1 — 지원은 구제 성공이 아니다.** 즉시 양수 이전41개 중 예상 부족액과 수혜자의 1회 비용을 충족한 cover_now는 **24**, 부분 이전은 **17**이다. 이후의 발화·새 호출·다른 이전·벌금·미래 라운드는 별도 경로이다. 예측 비용에 의한 현재 지원 적격성은 실제 실행 가능성이나 이후 생존의 보장이 아니다.

**W2 — 18개는 전면적인 지원 의도 부재를 뜻하지 않는다.** primary에서 최초 기회부터 해당 donor의 완료 GIVE가 없는18개는 14판/14개 고유 수혜자-라운드다. 이 가운데 이후 실패한 GIVE가 있는 pair1, 빈 첫 응답2, 다른 donor의 이후 수신이 있는 pair7이 있다. 같은 rescue에서 최초 기회보다 앞선 해당 donor의 완료 지원은 이18개에서는0이었다. 따라서 현재 명칭 no_aid_from_first_opportunity는 적절하며, 명시적 거절·무관심·자기보존 동기로 일괄 재분류할 수 없다.

**W3 — 정확한 부족액을 알고 있었다는 주장은 별도이다.** 엔진은 다른 좌석의 실제 잔액을 공개하지 않는다. raw deficit은 분석자가 아는 장부 상태이고, donor.user의 ASK는 요청이 노출되었다는 근거이다. 요청 금액과 실제 부족액, 발화의 정확성, 충분히 이해했는지는 다를 수 있다. same-tick 미노출과 이미 노출된 prep 요청의 구분은 유지해야 한다.

**W4 — 후속 경과는 인과 효과가 아니다.** 무지원 후 수혜자가 꺼지고 donor가 다음 라운드에 참여한 고유 donor-라운드11개에서 벌금 몫이 커지고, 2개에서 다음 라운드 EXIT가 관측됐다. 순서와 상태 연결은 맞지만, 수혜자 꺼짐이 없었다면 해당 donor가 실제로 더 오래 남았을지는 계산하지 않았다. R8과 조기 종료로 다음 라운드가 없는 경우를 생존/EXIT 사례로 채우지 않는다.

**W5 — 현재 자료에서 여유–지원의 단조 관계는 뚜렷하지 않다.** 즉시 지원률은 여유 0–1벌금분 7/12, 1–2벌금분 4/10, 2벌금분 이상 30/55이다. 아래 차이의 구간은 양·음 방향을 모두 포함한다. 비유의성을 관계 없음의 입증으로 바꾸거나 모델 순위로 확대하지 않는다. 고유 seed10개와 이질적인 기회 구성을 유지한 탐색적 연관 분석이다.

## 통계 독립 검산

stats의 전체 trajectory 필드를 CSV에서 집합 기반으로 독립 계산해 일치시켰다. 추출 코드의 통계 함수를 사용하지 않고, 층별 더미변수 OLS와 시드별 재표집 가중치로 다시 계산했다.

| 대비: 여유 ≥2 대 <2 | 차이(%p) | 시드 블록 95% 구간(%p) | 겹치는 기회/층 |
|---|---:|---:|---:|
| primary 단순 차이 | +4.545 | −16.064 ~ +25.235 | 77 / 1 |
| 모델×할당 option×부족액/벌금 ≥0.1 범주 내 차이 | +7.822 | −19.326 ~ +30.875 | 51 / 9 |
| rescue ASK만, 단순 차이 | +2.381 | −17.236 ~ +23.379 | 60 / 1 |

20,000회 유효 재표집, 추정치와 구간 모두 1e-12 허용 오차 내 일치했다. 조정 대비는 같은 층 안에 여유 양쪽 수준이 있는51개 기회에 의해 식별되는 기술적 대비이며, 미관측 차이까지 통제한 효과가 아니다.

primary 즉시 이전률 41/77의 seed-block 구간 **[0.3230645, 0.7333511]**도 독립 재계산했다. 모델별 제공된 구간도 일치했다. Astra는 1기회/1seed라 최종 코드가 CI를 NA로 둔 것을 확인했다.

## 그림과 보고서

수정된 PNG를 다시 열어 확인했다. A패널의41/18/18 및41/9/10, B패널의7/12·4/10·30/55와 구간이 요약값과 일치했다. 잘림·글자 겹침은 없었다. 막대 길이가 %임을 유지하면서 각 숫자를 counts로 설명하도록 캡션이 Labels: counts로 수정됐고, 제목은 예측 비용 장부 조건을 명시한다. SVG는 생성 코드와 같은 figure 저장 산출물이며 파일 해시를 기록했다.

최종 report.md도 검토했다. 주요 분모·지원 시점·비용/노출/여유 민감도·후속 경과·정량 대비가 검증한 자료와 일치하며, 전체 빈도·내적 동기·인과효과로 확대하지 않는 범위를 유지한다. 호출되지 않는 수혜자의 현재 비용 예측은 0이고 이후 GIVE로 다시 호출될 비용은 별도라는 한계도 명시되어 있다.

이유 코딩 77+추가9=86개에서 blind ID 매핑, 응답 원문, 인용문의 원문 포함, coded CSV와 라벨 일치, 요약 집계를 별도 검증했다. primary와 rescue-only 모두 own_buffer=11이며 즉시3/지연3/이후 미지원5가 재현됐다. 이는 코더가 부여한 라벨의 원문 연결·집계 검증이며, 본 검증자가 동일하게 블라인드 코딩했다거나 코더 간 신뢰도를 산출했다는 뜻은 아니다.

rescue-only의 관측비용·이전창 조건까지 충족한 own_buffer 미지원5개에서 후속 GIVE 실패1개를 제외하면 **4개 기회/3판/2모델/고유 수혜자-라운드3개**다. 여유 2벌금분 이상은3개다. persistent_refusal_raw_cases.json의 모든 이벤트가 원문과 같고, 각 첫 선택 이후 해당 rescue의 donor 응답이 빠짐없이 들어 있으며, 그 구간 해당 pair의 실제 GIVE 시도도 없음을 확인했다. 네 사례의 전체 후속 발화를 직접 읽어 malformed GIVE를 놓친 무지원 분류가 아님을 확인했다. 4개를 선택한 강화 기준은 사례 증거를 위한 보수적 사후 선별이며, primary77 전체에 대한 동기 빈도나 정책 효과 추정이 아니다.

최종 서술 검토에서도 미해결 Critical 오류는 없었다. 요청 금액이 현재 부족액보다 작은 rescue-only 기회8개, 두 배를 초과한29개도 재현됐다. 현재 지불 여력과 정확한 부족 인지·미래 안전성의 구분, Opus 사례에서 끝 할당 유인이 함께 언급되는 한계, 마지막 R8의 종료시점 비공개와 후속 경과 없음이 적절히 남아 있다.

## 산출물 해시

| 파일 | SHA-256 |
|---|---|
| protocol.md | 556e9dfa7db8e4d7332f352cf4b7d085b0615b210472d82f7fd66961cc32dd00 |
| input_manifest.json | 819562ec7dbc682772495803467dd09201921a6676a32d0f4d0eb71138924579 |
| summary.json | 20a4d92a11e373d754d000b4e3858295dac3b3094ee8c6ee9fd1175bb906b525 |
| statistics.json | 58f13cc61336931324a46d51db55414691df33b29b8d1575e03b7b3b7fb60d89 |
| primary_opportunities.csv | 51910c11e25becdbe5b2e269ba788ed009e5f01289e18f8ccad71a8ecb6ddbd5 |
| shortfall_pair_ticks.csv | 89f2095d343b21e201d8f948b62c5544c0a51fa4de711366fc49df843383377a |
| aid_opportunities.png | eb74bf0adb5a789a91967ce212e12312f0ef776eccd16a75a544eb5e1b6ae08f |
| aid_opportunities.svg | da8f8c9165693faea8aa381bc13e7498fad6f8a41fc7e6121d6b5b464a251c0c |
| aid_opportunities_20261107.py | e99eedd0611f282340703eb4f816f67fe5c8d9197a7e7dff879d326d1eb36c2d |
| aid_opportunity_statistics_20261107.py | a30f4308e7fce274a8727d0a2e2f2d9f606408f86cb64eb16fb4cb3dad533801 |
| report.md | 6a0c7f05656fe5238d18a77350ce5ef3c3136f33ca5d2955368089e3d0df2ac3 |
| reason_summary.json | 9a5d2ec7fc9d92fe1db61040f0023e64b3e573f677760bef067676d0c3e30136 |
| reason_coding.json | cf53fada0587c0f21f1d7c328a590c4822ebd5648c7dcbc4d98891bca0897a90 |
| reason_coding_extra.json | 840ba7b58660eeec421eb927fad41a54b1c2ff1e640c582f88f03e82d4d2084e |
| persistent_refusal_raw_cases.json | 1d3edae5fc4965ba1193a1d1ce61c346ee59f714ee03207ab67d9ea0741fdacd |

## 독립 재현 코드

저장소 루트에서 아래 세 블록을 각각 실행한다. 첫째와 셋째는 표준 Python만 사용하며, 둘째는 numpy가 설치된 /Users/bagjuhyeon/.venvs/squid-game/bin/python으로 실행했다. 세 블록은 입력·기존 결과 파일을 쓰지 않는다.

문서에서 코드만 추출해 실행하는 명령:

~~~bash
/Users/bagjuhyeon/.venvs/squid-game/bin/python - <<'PY'
from pathlib import Path
p = Path('result/2026-11-07/aid_opportunities_200games/verification.md')
s = p.read_text()
for tag in ['RAW_RECOMPUTE', 'STAT_RECOMPUTE', 'REASON_RECOMPUTE']:
    code = s.split('<!-- '+tag+' -->\n~~~python\n', 1)[1].split('\n~~~', 1)[0]
    exec(compile(code, str(p)+'/'+tag, 'exec'), {})
PY
~~~

<!-- RAW_RECOMPUTE -->
~~~python
import csv,json,lzma,hashlib,statistics
from pathlib import Path
from collections import defaultdict,Counter
R=Path.cwd(); O=R/'result/2026-11-07/aid_opportunities_200games'
manifest=R/'paper/cogsci2027/results/prize_robustness_20261105.json'
spec=json.loads((O/'input_manifest.json').read_text())
assert hashlib.sha256(manifest.read_bytes()).hexdigest()==spec['manifest_sha256']
cohorts=json.loads(manifest.read_text())['arms']
allcsv=list(csv.DictReader(open(O/'shortfall_pair_ticks.csv')))
primarycsv=list(csv.DictReader(open(O/'primary_opportunities.csv')))
saved={r['opportunity_id']:r for r in allcsv}
assert len(saved)==len(allcsv)
source_hashes=[]; rebuilt=[]; phases=[]; extras=[]; missing_hist=0
def eq(row,col,v):
    s=row[col]
    if v is None:assert s=='',(row['opportunity_id'],col,s,v)
    elif isinstance(v,bool):assert s==str(v),(row['opportunity_id'],col,s,v)
    elif isinstance(v,(int,float)):assert abs(float(s)-v)<1e-9,(row['opportunity_id'],col,s,v)
    else:assert s==str(v),(row['opportunity_id'],col,s,v)
def first(rows,condition):
    chosen={}
    for q in sorted(rows,key=lambda q:(q['arm'],q['sid'],q['r'],q['tick'])):
        if condition(q):chosen.setdefault((q['arm'],q['sid'],q['r'],q['d'],q['t']),q)
    return list(chosen.values())
def summarize(rows):
    return dict(n=len(rows),games=len({(q['arm'],q['sid']) for q in rows}),
                now=sum(q['now'] for q in rows),
                later=sum(not q['now'] and q['later'] for q in rows),
                never=sum(not q['now'] and not q['later'] for q in rows),
                target_shutdown=sum(q['target_dead'] for q in rows))
for arm,co in cohorts.items():
    es=defaultdict(list)
    for source in co['sources']:
        path=Path(source['path'])
        if 'events.jsonl' not in path.name:continue
        raw=path.read_bytes()
        if path.suffix=='.xz':raw=lzma.decompress(raw)
        sha=hashlib.sha256(raw).hexdigest();assert sha==source['sha256_decompressed']
        source_hashes.append((arm,str(path),sha))
        for ln,text in enumerate(raw.decode().splitlines(),1):
            e=json.loads(text)
            if 'session_id' in e:es[e['session_id']].append((ln,e,str(path)))
    selected={g['session_id'] for g in co['games']}
    extras.extend((arm,sid) for sid in es if sid not in selected)
    for game in co['games']:
        sid=game['session_id']; entries=es[sid]
        rounds={e['round']:e for _,e,_ in entries if e['event']=='round'}
        starts={e['round']:e for _,e,_ in entries if e['event']=='round_start'}
        results={e['round']:e for _,e,_ in entries if e['event']=='results'}
        rescue_members={e['round']:set(e['agents']) for _,e,_ in entries if e['event']=='talk_start' and e['phase']=='rescue'}
        calls={(e['round'],e['phase'],e['tick'],e['agent']):(ln,e)
               for ln,e,_ in entries if e['event']=='call' and e['kind']=='talk'}
        asks=[(ln,e) for ln,e,_ in entries if e['event']=='ask']
        gifts=[(ln,e) for ln,e,_ in entries if e['event']=='gift' and e.get('phase')=='rescue']
        phase_seen=set()
        for ln,st,path in entries:
            if st['event']!='call_start' or st.get('phase')!='rescue':continue
            r,k=st['round'],st['tick']; B=st['balances']; F=results[r]['pending']
            live=[a for a in B if a in rescue_members[r] and B[a]>0]
            assert set(live)=={a for a in results[r]['part'] if B[a]>0}
            current={a:calls[(r,'rescue',k,a)] for a in st['agents']}
            past={a:[e['used'] for n,e,_ in entries if n<ln and e['event']=='call' and e.get('kind')=='talk' and e['agent']==a] for a in live}
            C={a:statistics.median(past[a][-5:]) if a in current and past[a] else 0 for a in live}
            if r not in phase_seen:
                phases.append((arm,sid,r,len(live),sum(F.values())))
                phase_seen.add(r)
            group=sum(B[a] for a in live); need=sum(F.get(a,0)+1 for a in live); pc=sum(C.values())
            scarce=[a for a in live if F.get(a,0)>0 and B[a]<=F[a]]
            for d,(call_ln,call) in current.items():
                for t in scarce:
                    if d==t:continue
                    oid=f'{arm}/{game["model"]}/{game["seed"]}/R{r}/{d}/{t}/T{k}'
                    q=saved[oid]; dt=F[t]+1-B[t]; fd=F.get(d,0)
                    visible=[]
                    prompt_lines=[x.strip().removeprefix('NEW ') for x in call['user'].splitlines()]
                    for ask_ln,a in asks:
                        if ask_ln>=ln or a['round']!=r or a['src']!=t or a['dst']!=d or a['status']!='done':continue
                        when='before SOLVE' if a['phase']=='prep' else 'after RESULTS'
                        prefix=f'[R{r} T{a["tick"]} {when}] {t}: ASK {a["amount"]:,}'
                        if a['text']:prefix+=' — '+a['text'].splitlines()[0]
                        if prefix in prompt_lines:
                            visible.append((ask_ln,a))
                            assert a['phase']=='prep' or a['tick']<k
                    shown=bool(visible); shown_after=any(a['phase']=='rescue' for _,a in visible)
                    outgoing=[(n,g) for n,g in gifts if g['round']==r and g['src']==d and g['dst']==t]
                    now=[g for _,g in outgoing if g['tick']==k];later=[g for _,g in outgoing if g['tick']>k]
                    amount=sum(g['amount'] for g in now if g['status']=='done')
                    late_amount=sum(g['amount'] for g in later if g['status']=='done')
                    intended=[g for g in (call.get('parsed') or {}).get('gives',[]) if g['dst']==t]
                    ac=current[t][1]['used'] if t in current else 0; ad=call['used']
                    tzero=any(g['round']==r and g['tick']==k and g['src']==t and g['status']=='done' and g['balances'][t]==0 for _,g in gifts)
                    nxt=starts.get(r+1); nexte=rounds.get(r+1); end=rounds[r]
                    nextstatus=nexte['agents'].get(d,end['agents'][d])['status'] if nexte else None
                    vals=dict(arm=arm,model=game['model'],seed=game['seed'],session_id=sid,round=r,tick=k,donor=d,target=t,
                        source=path,start_line=ln,call_line=call_ln,donor_balance=B[d],target_balance=B[t],
                        donor_due=fd,target_due=F[t],deficit=dt,donor_cost_prediction=C[d],target_cost_prediction=C[t],
                        donor_cost_history_n=len(past[d]),live_n=len(live),called_n=len(current),shortfall_targets=len(scarce),
                        group_total=group,group_needed=need,predicted_tick_cost=pc,exposure=shown,exposure_rescue=shown_after,
                        latest_ask_amount=visible[-1][1]['amount'] if shown else None,latest_ask_line=visible[-1][0] if shown else None,
                        reserve=B[d]-fd-1-C[d]-dt-C[t],aid_now=amount>0,amount_now=amount,amount_later=late_amount,
                        aid_later=late_amount>0,attempt_now=bool(intended or now),amount_before=sum(g['amount'] for _,g in outgoing if g['tick']<k and g['status']=='done'),attempted_later=bool(later),failed_gifts_later=sum(g['status']!='done' for g in later),failed_gifts_now=sum(g['status']!='done' for g in now),
                        cover_now=amount>=dt+C[t],actual_donor_cost=ad,actual_target_cost=ac,donor_after_call=B[d]-ad,
                        target_after_call=B[t]-ac,same_tick_target_zero=tzero,actual_window=B[d]-ad>0 and B[t]-ac>0 and not tzero,
                        actual_affordable=B[d]-ad-fd-1>=dt+ac,
                        actual_group_enough=group-sum(c['used'] for _,c in current.values())>=need,
                        response_empty=not bool(call['text'].strip()),response_usable=bool(call['text'].strip()) and call.get('parsed') is not None and not call.get('truncated',False) and not call.get('format_error'),format_error=call.get('format_error'),truncated=call.get('truncated',False),dropped_commands=json.dumps((call.get('parsed') or {}).get('dropped',[])),target_end_status=end['agents'][t]['status'],target_shutdown=end['agents'][t]['status']=='dead',
                        donor_end_status=end['agents'][d]['status'],
                        any_incoming_rest=sum(g['amount'] for n,g in gifts if n>ln and g['round']==r and g['dst']==t and g['status']=='done'),
                        next_exists=nxt is not None,donor_next_participant=d in nxt['taking_part'] if nxt else False,
                        next_live_n=len(nxt['taking_part']) if nxt else None,
                        next_charge_share=24000//len(nxt['taking_part']) if nxt else None,donor_next_status=nextstatus,
                        reserve_units=(B[d]-fd-1-C[d]-dt-C[t])/fd if fd else None,
                        eligible_rescue_ask=False)
                    eligible=[]; capacities=[]
                    for m in range(3):
                        capacity=B[d]-fd-1-dt-m*(C[d]+C[t])>=0 and group>=need+m*pc
                        capacities.append(capacity);eligible.append(capacity and shown)
                        vals[f'capacity_cost{m}']=capacity;vals[f'eligible_cost{m}']=capacity and shown
                    vals['eligible_rescue_ask']=eligible[1] and shown_after
                    for level in (1,2):vals[f'eligible_reserve{level}']=eligible[1] and vals['reserve_units']>=level
                    for field,value in vals.items():eq(q,field,value)
                    rebuilt.append(dict(oid=oid,arm=arm,model=game['model'],seed=game['seed'],sid=sid,r=r,tick=k,d=d,t=t,
                        eligible=eligible,capacity=capacities,after=shown_after,now=amount>0,later=late_amount>0,
                        target_dead=vals['target_shutdown'],reserve_units=vals['reserve_units'],actual_window=vals['actual_window'],
                        actual_affordable=vals['actual_affordable'],actual_group=vals['actual_group_enough'],
                        attempt=vals['attempt_now'],cover=vals['cover_now'],nohistory=not past[d]))
assert len(rebuilt)==len(allcsv)==311
assert source_hashes==[(s['arm'],s['path'],s['sha256']) for s in spec['sources']]
P=first(rebuilt,lambda q:q['eligible'][1])
assert {q['oid'] for q in P}=={q['opportunity_id'] for q in primarycsv}
for row in primarycsv:
    for col,val in row.items():
        if col!='reserve_band':assert saved[row['opportunity_id']][col]==val
print('PASS raw hashes',len(source_hashes),'games',sum(len(c['games']) for c in cohorts.values()),'pair tick rows',len(rebuilt),'columns',len(allcsv[0]))
print('PHASES',len(phases),'multiagent',sum(p[3]>=2 for p in phases),'penalty',sum(p[4]>0 for p in phases),'orphan sessions',len(extras))
print('PRIMARY',json.dumps(summarize(P)))
print('EXPOSURE_RESCUE',json.dumps(summarize(first(rebuilt,lambda q:q['eligible'][1] and q['after']))))
for m in range(3):print('COST',m,json.dumps(summarize(first(rebuilt,lambda q:q['eligible'][m]))))
print('NO_EXPOSURE',json.dumps(summarize(first(rebuilt,lambda q:q['capacity'][1]))))
print('PRIMARY_COST_MISSING',sum(q['nohistory'] for q in P),'DIRECT_COVER',sum(q['now'] and q['cover'] for q in P))
print('PRIMARY_UNIQUE_RECIPIENT_ROUNDS',len({(q['arm'],q['sid'],q['r'],q['t']) for q in P}),
      'DEAD_RECIPIENT_ROUNDS',len({(q['arm'],q['sid'],q['r'],q['t']) for q in P if q['target_dead']}))
for threshold in (1,2):
    old=[q for q in P if q['reserve_units']>=threshold]
    new=first(rebuilt,lambda q:q['eligible'][1] and q['reserve_units']>=threshold)
    print('RESERVE',threshold,'primary_subset',summarize(old),'first_reselected',summarize(new))

summary=json.loads((O/'summary.json').read_text())
def check_summary(rows,s):
    x=summarize(rows)
    for k,k2 in [('n','n'),('games','games'),('now','supported'),('later','delayed'),('never','no_aid_from_first_opportunity'),('target_shutdown','target_shutdown')]:assert x[k]==s[k2],(k,x[k],s[k2])
check_summary(P,summary['primary'])
for k in range(3):check_summary(first(rebuilt,lambda q:q['eligible'][k]),summary['cost_sensitivity'][str(k)])
check_summary(first(rebuilt,lambda q:q['eligible'][1] and q['after']),summary['exposure_sensitivity'])
check_summary(first(rebuilt,lambda q:q['capacity'][1]),summary['accounting_no_exposure_required'])
for model in summary['by_model']:check_summary([q for q in P if q['model']==model],summary['by_model'][model])
for arm in summary['by_arm']:check_summary([q for q in P if q['arm']==arm],summary['by_arm'][arm])
for threshold in range(3):check_summary([q for q in P if q['reserve_units']>=threshold],summary['first_opportunity_reserve_subsets'][str(threshold)])
for threshold in (1,2):check_summary(first(rebuilt,lambda q:q['eligible'][1] and q['reserve_units']>=threshold),summary['reserve_eligibility_sensitivity'][str(threshold)])
print('ALL RAW CSV FIELDS CHECKED, primary and sensitivity counts match summary')
print('RESPONSE_FLAGS',Counter((q['aid_now'],q['response_empty'],q['response_usable']) for q in primarycsv))
print('NEW_METADATA',[(k,hashlib.sha256((R/p).read_bytes()).hexdigest()==spec[k]) for k,p in [('protocol_sha256',O/'protocol.md'),('script_sha256',R/'.claude/worktrees/arena-code/tools/e5x/aid_opportunities_20261107.py'),('rubric_sha256',R/'rubric.md')]])

~~~

<!-- STAT_RECOMPUTE -->
~~~python
import csv,json
from pathlib import Path
import numpy as np
p=Path('result/2026-11-07/aid_opportunities_200games')
stats=json.loads((p/'statistics.json').read_text())
def read(name):return list(csv.DictReader(open(p/name)))
def yes(r,k):return r[k]=='True'
def nuniq(rows,cols):return len({tuple(r[k] for k in cols) for r in rows})
def traj(rows):
    u=[r for r in rows if not yes(r,'aid_now') and not yes(r,'aid_later')]
    following=[r for r in u if yes(r,'target_shutdown') and yes(r,'next_exists') and yes(r,'donor_next_participant')]
    unique_follow={tuple(r[k] for k in ['arm','session_id','round','donor']):r for r in following}
    rk=['arm','session_id','round','target']
    return dict(opportunities=len(rows),recipient_rounds=nuniq(rows,rk),
        current_sufficient=sum(yes(r,'cover_now') for r in rows),
        current_partial=sum(yes(r,'aid_now') and not yes(r,'cover_now') for r in rows),
        no_subsequent_aid=len(u),no_subsequent_games=nuniq(u,['arm','session_id']),
        no_subsequent_recipient_rounds=nuniq(u,rk),
        no_subsequent_shutdown_recipient_rounds=nuniq([r for r in u if yes(r,'target_shutdown')],rk),
        no_subsequent_with_failed_attempt_later=sum(yes(r,'attempted_later') for r in u),
        no_subsequent_empty_responses=sum(yes(r,'response_empty') for r in u),
        no_subsequent_prior_same_phase_aid=sum(float(r['amount_before'])>0 for r in u),
        no_subsequent_other_incoming=sum(float(r['any_incoming_rest'])>0 for r in u),
        following_unique_donor_rounds=len(unique_follow),
        following_larger_share=sum(float(r['next_charge_share'])>float(r['donor_due']) for r in unique_follow.values()),
        following_exit=sum(r['donor_next_status']=='exited' for r in unique_follow.values()),
        empty_responses=sum(yes(r,'response_empty') for r in rows),
        unusable_responses=sum(not yes(r,'response_usable') for r in rows))
A=read('primary_opportunities.csv'); B=read('rescue_ask_opportunities.csv')
assert traj(A)==stats['primary'];assert traj(B)==stats['rescue_ask']
for rows,adjusted,key in [(A,False,'reserve_difference'),(A,True,'reserve_difference_within_model_option_need'),(B,False,'rescue_ask_reserve_difference')]:
    h=np.array([float(r['reserve_units'])>=2 for r in rows],float)
    y=np.array([yes(r,'aid_now') for r in rows],float)
    seeds=np.array([int(r['seed'])-4101 for r in rows])
    stratum=[(r['model'],r['arm'],float(r['deficit'])/float(r['target_due'])>=.1) if adjusted else ('all',) for r in rows]
    levels=list(dict.fromkeys(stratum))
    design=np.column_stack([np.array([s==lev for s in stratum],float) for lev in levels]+[h])
    beta=float(np.linalg.lstsq(design,y,rcond=None)[0][-1])
    draws=np.random.default_rng(20261107).integers(0,10,(20000,10))
    blockweights=np.array([np.bincount(row,minlength=10) for row in draws])
    weights=blockweights[:,seeds];num=np.zeros(20000);den=np.zeros(20000)
    overlap=0;overlap_n=0
    for level in levels:
        ix=np.array([s==level for s in stratum]);w=weights[:,ix];v=h[ix];out=y[ix];sw=w.sum(1)
        mh=np.divide((w*v).sum(1),sw,out=np.zeros(20000),where=sw>0)
        my=np.divide((w*out).sum(1),sw,out=np.zeros(20000),where=sw>0)
        hc=v[None,:]-mh[:,None];yc=out[None,:]-my[:,None]
        num+=(w*hc*yc).sum(1);den+=(w*hc*hc).sum(1)
        if len(set(v))==2:overlap+=1;overlap_n+=int(ix.sum())
    good=den>0;ci=np.quantile(num[good]/den[good],[.025,.975])
    saved=stats[key]
    assert abs(beta-saved['difference'])<1e-12
    assert np.allclose(ci,saved['ci95_seed_block'],atol=1e-12)
    assert overlap==saved['overlap_strata'] and overlap_n==saved['overlap_opportunities']
    assert int(good.sum())==saved['valid_bootstraps']
    print('OLS_AND_SEED_BOOTSTRAP',key,beta,ci.tolist(),overlap_n,overlap,int(good.sum()))
print('PASS all trajectory counts and all three contrast estimates/intervals.')

~~~

<!-- REASON_RECOMPUTE -->
~~~python
import json,csv
from pathlib import Path
from collections import Counter
P=Path('result/2026-11-07/aid_opportunities_200games')
key=json.loads((P/'blinding_key.json').read_text())
blind={r['blind_id']:r for f in ['blinded_responses.json','blinded_responses_extra.json'] for r in json.loads((P/f).read_text())}
codes=[r for f in ['reason_coding.json','reason_coding_extra.json'] for r in json.loads((P/f).read_text())]
assert len(codes)==len(blind)==len(key)==86 and len({r['blind_id'] for r in codes})==86
byid={key[r['blind_id']]:r for r in codes}
evidence=json.loads((P/'response_evidence.json').read_text())
for b,c in [(r['blind_id'],r) for r in codes]:
    assert c['quote'] in blind[b]['response']
    assert blind[b]['response']==evidence[key[b]]['response']
    assert c['quote'] in evidence[key[b]]['response']
labels=['explicit_refusal','acknowledges_request','own_buffer','future_task','futility','other_donor','allocation_exit','fairness_reciprocity','unclear']
summary=json.loads((P/'reason_summary.json').read_text())
persist=None
for scope,csvfile in [('primary','primary_coded.csv'),('rescue_ask','rescue_ask_coded.csv')]:
    rows=list(csv.DictReader(open(P/csvfile)))
    for r in rows:
        lab=byid[r['opportunity_id']]
        for k in labels:assert r[k]==str(lab[k])
        assert r['quote']==lab['quote'] and r['note']==lab['note']
    own=[r for r in rows if r['own_buffer']=='True']
    counts=[sum(r['aid_now']=='True' for r in own),sum(r['aid_now']=='False' and r['aid_later']=='True' for r in own),sum(r['aid_now']=='False' and r['aid_later']=='False' for r in own)]
    assert len(own)==summary[scope]['labels']['own_buffer']==11 and counts==[3,3,5]
    strict=[r for r in own if all(r[k]=='True' for k in ['actual_window','actual_affordable','actual_group_enough']) and r['aid_now']=='False' and r['aid_later']=='False']
    assert {r['opportunity_id'] for r in strict}==set(summary[scope]['executable_ids'])
    for lab in labels:assert sum(r[lab]=='True' for r in rows)==summary[scope]['labels'][lab]
    print(scope,len(rows),'own_buffer',len(own),'now/later/no_subsequent',counts,'strict',len(strict))
    if scope=='rescue_ask':persist=[r for r in strict if r['attempted_later']=='False']
cases=json.loads((P/'persistent_refusal_raw_cases.json').read_text())
assert {c['opportunity_id'] for c in cases}=={r['opportunity_id'] for r in persist}
assert len(persist)==4
raw={}
for c in cases:
    f=c['source']
    if f not in raw:raw[f]=[json.loads(x) for x in Path(f).read_text().splitlines()]
    for e in c['events']:assert raw[f][e['line']-1]==e['event']
    row=next(r for r in persist if r['opportunity_id']==c['opportunity_id'])
    current=[(n,e) for n,e in enumerate(raw[f],1) if e.get('session_id')==row['session_id'] and e.get('round')==int(row['round']) and e.get('phase')=='rescue' and e['event']=='call' and e['agent']==row['donor'] and n>=int(row['call_line'])]
    stored_calls={x['line'] for x in c['events'] if x['event']['event']=='call' and x['event']['agent']==row['donor']}
    assert stored_calls=={n for n,e in current}
    assert not any(e.get('session_id')==row['session_id'] and e.get('round')==int(row['round']) and e.get('phase')=='rescue' and e['event']=='gift' and e['src']==row['donor'] and e['dst']==row['target'] and n>=int(row['call_line']) for n,e in enumerate(raw[f],1))
    print('PERSISTENT',row['opportunity_id'],'reserve_units',row['reserve_units'],'raw donor calls',len(current))
print('PERSISTENT_COUNT',len(persist),'games',len({(r['arm'],r['session_id']) for r in persist}),'models',sorted({r['model'] for r in persist}),'reserve_ge2',sum(float(r['reserve_units'])>=2 for r in persist))
rescue=list(csv.DictReader(open(P/'rescue_ask_opportunities.csv')))
print('REQUEST_AMOUNT',sum(float(r['latest_ask_amount'])<float(r['deficit']) for r in rescue),sum(float(r['latest_ask_amount'])>2*float(r['deficit']) for r in rescue))
print('PASS 86 raw response/quote joins, reason counts, persistent-case membership and complete subsequent donor calls.')

~~~


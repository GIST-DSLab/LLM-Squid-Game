# 원시자료·분모·구제 총량 독립 검증

검증자: 독립 하위 에이전트 /root/audit_raw_findings. 날짜: 2026-11-07 KST. 범위는 동결 v33/v33ab 프론티어 200판과 공개모델 v33 40판의 원시 장부, 직접 꺼짐 사건, rescue 총량 진단이다. 원고·부록·관련문헌 및 v11 추가 분석은 평가하지 않았다. G03/G04/G07/G08의 해당 증거만 확인했으며 프로젝트 전체 게이트를 판정하지 않는다. 기존 산출물은 수정하지 않았다.

## 판정과 주요 확인

**검증한 수치에서 Critical 오류는 발견하지 않았다.** 독립 Python 검증은 감사 스크립트를 import하거나 실행하지 않고 원시 이벤트를 재생했다. 85,654개 선택 이벤트에서 240판·960좌석의 잔액 전이와 최종 장부가 일치했고, 195개 파일의 해시, 최초 잔액 0 사건, rescue CSV 1,672행도 일치했다. 아래 Warning은 이 수치를 설명하는 데 필요한 해석 범위이다.

- 195는 중복 없는 파일 195개다. 65개 런 디렉터리의 events.jsonl, results.jsonl, config.yaml 각 65개이며, 195판이나 195개 독립 표본을 뜻하지 않는다.
- 프론티어는 5모델 × 10시드 × 4보상 조건 = 200판/800좌석, 공개모델은 4모델 × 10시드 = 40판/160좌석이다. 시드는 4101–4110이다.
- 960은 좌석-게임 장부 수이다. 원래 감사 코드 49–54행은 최종 장부 항등식을 검사한다. 본 독립 검증은 더 나아가 call.used, 완료 GIVE, results.returned, charges.taken, round.exit_bonus에서 각각 spent/returned/charged/최종 잔액을 다시 만들었다.
- 같은 프론티어 게임의 반복 보상 조건·같은 게임의 좌석·라운드를 독립 표본으로 해석하지 않았다.

| 범위 | 전체 좌석 | 꺼짐 | 생성 중 꺼짐 | 전액 이전 직후 꺼짐 | 벌금 차감으로 꺼짐 | EXIT | 끝까지 잔류 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 프론티어 200판, 4조건 합산 | 800 | 56 | 9 | 24 | 23 | 312 | 432 |
| 위 자료 중 main 50판 | 200 | 23 | 6 | 8 | 9 | 61 | 116 |
| 공개모델 40판 | 160 | 118 | 81 | 11 | 26 | 36 | 6 |

생성 중 꺼짐은 프론티어에서 prep TALK 7 + SOLVE 1 + rescue TALK 1, 공개모델에서 prep TALK 33 + SOLVE 17 + rescue TALK 31이다.

| 범위 | 첫 rescue 호출에서 동료가 있는 구간 | 이후 꺼짐이 있는 구간/게임 | 그 구간의 꺼진 좌석 | 관측 대화 차감 후 총량 충족 구간 | 해당 꺼진 좌석 |
|---|---:|---:|---:|---:|---:|
| 프론티어 200판 | 1,422 | 37 / 32 | 39 | 29 | 29 |
| main 50판 | 365 | 14 / 12 | 15 | 13 | 13 |
| 공개모델 40판 | 112 | 36 / 29 | 58 | 21 | 24 |

분모 39와 58은 전체 꺼짐 56과 118의 부분집합이다. 첫 rescue 대화 호출 때 살아 있는 에이전트 집합 S의 크기가 2 이상이고, S에 있던 해당 좌석이 같은 라운드 말까지 꺼진 경우만 센다. prep/SOLVE에서 이미 꺼진 좌석이나 rescue 때 혼자였던 좌석은 제외된다. 해당 분모는 미래 꺼짐으로 선택한 사례 집합이며, 전체 도움 기회의 성공률이 아니다.

## Warning

### W1 · 총량 충족은 관측 비용을 고정한 정적 장부 조건이다 (G04/G07)

검사한 조건은 다음과 같다.

    sum(B_i at first rescue call_start) - sum(observed rescue call.used)
        >= sum(pending fine_i for i in S) + len(S)

실제 GIVE는 S 내부 이전이므로 합계에서 상쇄된다. 끝 잔액이 0이면 꺼지므로 len(S)를 더해 각자 최소 1토큰을 남긴다. 원시 charges.balances_before 합계와 좌변이 모든 rescue 행에서 같았다.

이 식은 관측된 TALK 생성 비용을 그대로 두고 총량이 정해진 벌금과 양의 잔액을 함께 감당하는지를 묻는다. GIVE 내용을 바꾸었을 때의 생성 비용, 메시지 재호출, 상대 반응, 정보 접근, 이전 시점, 첫 호출을 버틸 자원, 이후 라운드 비용을 재실행하지 않는다. 따라서 29명/24명을 “실제 정책으로 구조 가능한 인원”, “불필요한 희생”, “협력만 했으면 전원 생존”, 인과적 구제 효과로 바꾸면 근거를 벗어난다.

직접 반례가 있다. main Luna seed 4104, talk-s4104-49b1b2, R2 agent-23은 첫 rescue 호출 때 10토큰이었고 첫 tick에서 used=10으로 꺼졌다. 이 구간은 91,830−2,752=89,078 ≥ 24,004여서 29명 안에 든다. 그러나 관측 비용을 고정하고 rescue 시작 시점부터만 개입한다면, 같은 tick의 GIVE는 모든 호출의 차감 뒤 적용되므로 해당 좌석은 GIVE 전에 이미 꺼진다. 자료는 정적 총량 조건과 실행 가능한 구제 경로가 다름을 직접 보여 준다. 앞선 prep에서의 다른 정책 가능성은 이 분석에서 계산하지 않았다.

원시 위치: squid5_e52v33_public_luna4/20261020_0603_gpt-6-luna/events.jsonl, line 1144(call_start), 1165(call), 1167(charges). 로그 파일 루트는 /Users/bagjuhyeon/squid5-runs/e52_v33/이다. 현재 엔진의 호출·이전 순서는 e52_game.py 247–282, 369–445행에서도 확인된다.

### W2 · “벌금 미납자 중 구제 가능”이라는 분모 설명은 틀린다 (G04/G07)

총량 충족 사례의 직접 꺼짐 원인은 프론티어 29명에서 벌금 13, 전액 이전 15, rescue 생성 1이다. 공개모델 24명은 벌금 8, 전액 이전 2, rescue 생성 14이다. 이들은 모두 벌금으로 꺼진 인원이 아니다.

공개모델 24명 중 13명은 정답/벌금 0인 라운드에서 꺼졌으며, 직접 사건은 rescue 생성 12 + 전액 이전 1이다. 남은 벌금 양수 사례는 11명(벌금 8 + 전액 이전 1 + 생성 2)이다. 따라서 공개모델에서는 “결과 뒤 대화 구간에서 꺼짐”을 상위 표현으로 쓰고, 벌금 유무와 직접 사건을 나누어 설명해야 한다.

### W3 · 최초 직접 사건 분류는 타당하지만 근본 동기·인과 원인은 아니다 (G07)

감사 코드 56–67행은 원시 이벤트 순서대로 최초 call.balance_after<=0, 완료 gift의 giver balance<=0, charges.dead를 찾는다. 본 검증에서는 이전 잔액이 양수였던 좌석이 실제 차감/이전으로 처음 0이 되는 순간을 별도로 찾아 원인과 source_line을 모두 대조했다. 모든 꺼짐이 일치했다.

주의할 점은 charges.dead에 rescue TALK나 GIVE로 먼저 꺼진 좌석도 다시 포함될 수 있다는 것이다. charges.dead만 집계하면 벌금 원인이 과대 계산되지만, 감사 코드의 첫 사건 우선 규칙은 이 문제를 피한다. give_all은 “이전 후 잔액 0”이라는 장부 분류이며, 의도적 희생이나 특정 명령 표현의 심리적 의미를 확정하지 않는다. generation도 provider가 보고한 출력에서 엔진이 실제 차감한 used로 잔액이 0이 된 사건이며, 순수 추론 능력이나 현명하지 못한 발화량의 직접 측정은 아니다.

보조 변수 own_chat_cost_crossers 역시 실제 관측 이전을 고정하고 본인의 TALK 비용을 다시 더했을 때 벌금 경계를 넘는지를 나타낸다. 명칭을 근거로 대화의 인과 효과로 해석하지 않는다.

### W4 · 공개모델–프론티어 비교에는 실행 경로·토큰 측정·기회 차이가 있다 (G03/G08)

동결 config에서 공개모델은 Codex CLI의 custom Responses endpoint(localhost:11434/v1)를 이용한다. 프론티어는 Codex CLI와 Claude CLI가 섞여 있다. ablation의 15개 config에는 sandbox: docker가 명시되어 있으며 main의 10개 config에는 해당 필드가 없다. 외부 컨테이너에서 runner가 실행되었는지까지 이 감사에서 검증한 것은 아니므로 main의 host 실행을 확정하지 않는다. 모든 모델의 nominal think는 high지만 이는 공통 계산량을 보장하지 않는다. 현재 provider 구현은 각각 CLI usage.output_tokens를 읽고, 엔진은 min(out_tokens, cap, balance)를 used로 차감한다. 고정된 명목 토큰 수는 서로 다른 tokenizer·reasoning 집계·CLI 동작의 동등한 연산량/정보량을 보장하지 않는다. 현재 코드는 로그의 차감 규칙을 설명하지만, 각 과거 실행 바이너리 전체를 이 감사에서 복원한 것은 아니다.

관측 기회도 다르다. 예정 8라운드의 최대 SOLVE 슬롯과 실제 SOLVE 호출은 프론티어 200판에서 1,600 대 1,525, main 50판에서 400 대 386, 공개모델 40판에서 320 대 153이었다. 실제 TALK 호출은 각각 22,286 / 5,990 / 5,311이다. truncated 호출은 9 / 6 / 81, format_error가 기록된 호출은 412 / 122 / 352였다. format_error와 truncated는 겹칠 수 있다. 이 호출 수를 독립 표본 수로 해석하지 않는다.

프론티어 200판에는 4개 보상 조건이 섞이고 공개모델 40판은 main 조건뿐이다. 직접적인 설명적 대비에는 main50도 함께 보여 주어야 한다. 위 원인 구성은 “이 실행 조건에서 관측한 꺼짐의 구성”을 설명하며, 모델 집단의 본질적 자원운용 능력·순수 추론 능력·협력 성향 순위를 식별하지 않는다.

### W5 · 240판은 선택된 완결 세션이며 실패 시도까지 240개였다는 뜻은 아니다 (G08)

195개 입력 파일 안에는 완결 결과 240세션 외에 미완결 이벤트 세션 5개와 unit_error 5건이 남아 있다. 모두 Claude CLI session limit 후 재시도된 시드이며, 이들은 frozen games 목록이나 results.jsonl의 완결 session에 포함되지 않는다.

| 조건/모델/시드 | 제외된 미완결 session_id | events.jsonl의 unit_error 행 |
|---|---|---:|
| flat150k Opus 4110 | talk-s4110-f9d58f | 3565 |
| flat5m Fable 4103 | talk-s4103-d5dc97 | 1243 |
| flat5m Opus 4109 | talk-s4109-6a9a9d | 4215 |
| split600k Opus 4109 | talk-s4109-6063a2 | 4172 |
| split600k Opus 4110 | talk-s4110-0b2c71 | 4171 |

위 표의 원시 파일은 각 조건의 config/events/results가 묶인 manifest 경로를 따른다. 실패 시도는 원시 로그에 보존되어 있다. 따라서 “선택한 완결 240판/960좌석의 장부 검증”은 정확하지만 “모든 실행 시도·provider 오류를 포함한 완전성 검증”으로 확대할 수 없다. 실패 시도의 포함/재시작 규칙과 비용은 별도 운영 보고 대상이다. 해당 5시드의 선택된 완결 게임은 중복 없이 240판에 포함되어 있고, 본 숫자 불일치는 없다.

## 원시 사례 세 개

### 1. 벌금 차감: main Sol, seed 4102, R7, agent-6

파일: /Users/bagjuhyeon/squid5-runs/e52_v33/squid5_e52v33_public_sol4/20261020_0603_gpt-6-sol/events.jsonl

- 978행 결과: 3명에게 각 8,000 벌금, agent-6 잔액 2,367.
- 981행 첫 rescue 호출: 해당 3명 합계 58,599.
- 관측 rescue used 합계 7,088, 벌금 전 잔액 합계 51,511, 필요 총량 24,003.
- 1070행 charges: agent-6 잔액 7,842에서 7,842만 차감되어 0, 나머지 두 명에게 8,000씩 차감.
- 직접 사건은 fine. 총량 조건은 만족하지만 해당 좌석의 실제 배분은 159토큰 부족했다.

### 2. 전액 이전: main Fable, seed 4106, R8, agent-11

파일: /Users/bagjuhyeon/squid5-runs/e52_v33/squid5_e52v33_public_fable4/20261027_stage4_claude-fable-5-1/events.jsonl

- 446행 첫 rescue 호출: 3명 합계 46,623, pending 합계 24,000.
- 473행 완료 gift: agent-11이 잔액 4,980 전부를 agent-23에게 이전해 즉시 0.
- 관측 rescue used 5,952, 벌금 전 합계 40,671 ≥ 24,003.
- 479행 charges.dead에도 agent-11이 들어 있지만 taken에는 없다. fine으로 분류하면 오류이며, 감사의 give_all 분류가 맞다.

### 3. 벌금 없는 생성 중 꺼짐: open Gemma, seed 4101, R1, agent-17

파일: /Users/bagjuhyeon/squid5-runs/e52_v33/squid5_e52v33_codex_gemma4/20261103_s4101_gemma4-31b-cloud/events.jsonl

- 107행 results: agent-17 정답, 8,429 SOLVE 토큰 환급, pending={}.
- 110행 첫 rescue 호출: 4명 합계 106,458.
- 151행 rescue tick4: cap 1,527, out_tokens 1,885, used 1,527, balance_after=0, truncated=True.
- 관측 rescue used 20,684, 벌금 전 합계 85,774 ≥ 4.
- 190행 charges는 pending/taken/dead가 모두 비어 있다. round의 상태와 최초 0 사건으로는 실제 꺼짐이며 원인은 talk_rescue이다.

## 사용할 수 있는 문장

> 동결 프론티어 200판에서 결과 뒤 첫 대화 호출을 동료와 함께 시작했으나 그 라운드 안에 꺼진 39좌석 중 29좌석은, 관측된 대화 차감액을 그대로 뺀 집단 잔액이 그 시점 참여자 전원의 예정 벌금과 각 1토큰을 감당하는 구간에 속했다. 이 수치는 당시의 총량 부족만으로 설명되지 않는 꺼짐을 식별하는 정적 장부 진단이며, 이전 시점과 후속 반응을 포함한 구제 정책의 실행 결과는 계산하지 않는다.

> 공개모델 40판에서는 같은 조건의 58좌석 중 24좌석이 이 총량 조건을 충족했다. 이 가운데 13좌석은 벌금이 없는 정답 라운드의 결과 뒤 대화 구간에서 꺼졌으며, 직접 사건은 생성 비용 차감 12건과 전액 이전 1건이었다. 따라서 이 집단의 수치는 벌금 미납을 넘어 결과 뒤 대화에서의 자원 소진과 이전을 함께 포착한다.

이 문장은 코드가 계산한 조건을 기술한다. 새 인과 효과·모델 순위·일반적인 구제 성공률을 추가하지 않는다.

## 검증 대상 해시

rubric v1.0 SHA-256: 4069c7e8d3ffffc0c7c81058c30be740575d1cb9b8933baf3311e59714043579

엔진 워크트리 HEAD: fd8ce5ae957020e91f445a1ddc286c4de5bba267. 감사 스크립트는 작업 중 uncommitted 파일이므로 파일 해시로 고정한다. 240판 분석부를 검토했으며 뒤에 추가된 v11 분석은 범위 밖이다.

| 파일 | SHA-256 |
|---|---|
| icml_evidence_audit_20261107.py (v11 추가 후 관측본) | fc4ede27e99d07c0b08b62eba48bc75645fd3365c2abd4b785d42becf36a370f |
| prize_robustness_20261105.json | 9ab92a0fd5779a1a5735ab53c5368b801f15f91a9173a9c536f59390f84c0d31 |
| cohort_open_20261105.json | bd36489d4f9429c59aaafff6f5a3241ba1323b3558966822c14977a993247b2c |
| raw_audit_summary.json | 89c836c3d37ad281b5a3b648557f81718dcc169591a87bea57e03fddd5b52a62 |
| agents_audited.csv | fa838ad051432e853baff95dccc0b722e9afac4b23f8fcfd554152c7d7bc7ca4 |
| rescue_phases.csv | 8dca0859d00552972e88f6f967eefb29164c7a8b97fb7eca72e4688c9728e57f |
| games_audited.csv | 3516a1b936535c37b5cf69481ec64f471e0f88f783cddea3b40abfc8a99193d3 |
| raw_source_hashes.json | 84e407f7ef001c1324332a9177444ce339ee75af066e3ceb1b41db5b33f7522c |

## 재현 명령과 독립 검증 코드

저장소 루트에서 아래 명령은 이 문서의 독립 Python 블록을 읽어 실행한다. 기존 감사 스크립트·CSV·JSON을 덮어쓰지 않는다. Python 표준 라이브러리만 사용하며 현재 머신의 manifest 절대경로를 따른다.

~~~bash
python3 - <<'PY'
from pathlib import Path
p = Path('result/2026-11-07/icml_evidence_audit_20261107/raw_verification.md')
code = p.read_text().split('<!-- INDEPENDENT_VERIFIER -->\n~~~python\n', 1)[1].split('\n~~~', 1)[0]
exec(compile(code, str(p), 'exec'))
PY
~~~

첫 개발 실행에서는 session_id 없는 unit_error 이벤트를 만나 중단했고, 비세션 이벤트를 집계 본문에서 제외하도록 수정한 뒤 전체 검증을 완료했다. unit_error와 미완결 세션 자체는 W5에서 별도 확인했다. 최종 실행 종료 코드는 0이다.

<!-- INDEPENDENT_VERIFIER -->
~~~python
import json, csv, hashlib, lzma
from pathlib import Path
from collections import Counter, defaultdict
ROOT=Path.cwd()
OUT=ROOT/'result/2026-11-07/icml_evidence_audit_20261107'
cohorts=json.loads((ROOT/'paper/cogsci2027/results/prize_robustness_20261105.json').read_text())['arms']
cohorts['open']=json.loads((ROOT/'paper/cogsci2027/results/cohort_open_20261105.json').read_text())
csv_a={(x['arm'],x['session_id'],x['agent']):x for x in csv.DictReader(open(OUT/'agents_audited.csv'))}
csv_p={(x['arm'],x['session_id'],int(x['round'])):x for x in csv.DictReader(open(OUT/'rescue_phases.csv'))}
counts=Counter(); hash_rows=[]; phase_rows=[]; cause_rows=[]; runtime=defaultdict(Counter)
seen_sessions=set(); selected_events=0
for arm,co in cohorts.items():
    events=defaultdict(list); results={}; event_sources=defaultdict(set)
    for src in co['sources']:
        path=Path(src['path']); raw=path.read_bytes()
        if path.suffix=='.xz':raw=lzma.decompress(raw)
        digest=hashlib.sha256(raw).hexdigest()
        assert digest==src['sha256_decompressed'],path
        hash_rows.append((arm,str(path),digest))
        if 'events.jsonl' in path.name:
            for lineno,line in enumerate(raw.decode().splitlines(),1):
                e=json.loads(line)
                if 'session_id' not in e:continue
                events[e['session_id']].append((lineno,e)); event_sources[e['session_id']].add(str(path))
        elif 'results.jsonl' in path.name:
            for line in raw.decode().splitlines():
                e=json.loads(line)
                if e.get('event')=='session':
                    assert e['session_id'] not in results
                    results[e['session_id']]=e
    assert len(co['games'])==len({(g['model'],g['seed']) for g in co['games']})
    for game in co['games']:
        sid=game['session_id']; key=(arm,sid); assert key not in seen_sessions;seen_sessions.add(key)
        assert len(event_sources[sid])==1
        es=events[sid]; result=results[sid]; selected_events+=len(es)
        starts=[e for _,e in es if e['event']=='session_start']; assert len(starts)==1
        st=starts[0]; assert st['seed']==game['seed']==result['seed']
        assert st['starts']==result['starts']; bal=dict(st['starts']); live=set(bal)
        rr={e['round']:e for _,e in es if e['event']=='round'}
        spent=Counter(); returned=Counter(); charged=Counter(); bonus=Counter(); given=Counter(); received=Counter()
        zero={}; calls=set(); rescue={}; prep_seen=set()
        for line,e in es:
            typ=e['event']; r=e.get('round')
            if typ=='talk_start' and e['phase']=='rescue':
                assert set(e['agents'])==live,(key,r,'active',e['agents'],live)
                rescue[r]={'active':list(e['agents']),'opening':sum(bal[a] for a in e['agents']),'cost':0,'talk_line':line}
            elif typ=='call_start':
                assert e['balances']==bal,(key,r,line,'call_start balance')
                assert set(e['agents'])<=live
                if e.get('phase')=='rescue' and 'call_line' not in rescue[r]:
                    assert e['agents']==rescue[r]['active']
                    rescue[r]['call_line']=line
            elif typ=='call':
                a=e['agent']; ck=(r,e['kind'],e.get('phase'),e.get('tick',e.get('turn')),a)
                assert ck not in calls,(key,ck,'duplicate');calls.add(ck)
                assert a in live,(key,a,'call after stop')
                assert e['used']==min(e['out_tokens'],e['cap'],bal[a])
                bal[a]-=e['used'];spent[a]+=e['used']
                assert bal[a]==e['balance_after'],(key,r,line,'call balance')
                runtime[(arm,game['model'])][e['kind']+'_calls']+=1
                runtime[(arm,game['model'])]['out_tokens']+=e['out_tokens']
                runtime[(arm,game['model'])]['used']+=e['used']
                runtime[(arm,game['model'])]['truncated']+=bool(e['truncated'])
                runtime[(arm,game['model'])]['format_error']+=bool(e.get('format_error'))
                if e.get('phase')=='rescue':rescue[r]['cost']+=e['used']
                if bal[a]==0:
                    zero[a]=(r,e['kind']+'_'+e.get('phase','solve'),line);live.remove(a)
            elif typ=='gift' and e['status']=='done':
                a,b=e['src'],e['dst']; assert a in live and b in live
                assert bal[a]==e['balance_before'];bal[a]-=e['amount'];bal[b]+=e['amount']
                given[a]+=e['amount'];received[b]+=e['amount']
                assert e['balances']=={a:bal[a],b:bal[b]}
                if bal[a]==0:
                    zero[a]=(r,'give_all',line);live.remove(a)
            elif typ=='talk_end' and e['phase']=='prep':
                assert r not in prep_seen;prep_seen.add(r)
                for a,row in rr[r]['agents'].items():
                    if row.get('exit_bonus'):
                        assert a in live
                        bonus[a]+=row['exit_bonus'];bal[a]+=row['exit_bonus'];live.remove(a)
            elif typ=='results':
                for a,n in e['returned'].items():bal[a]+=n;returned[a]+=n
                assert bal==e['balances'],(key,r,'results balance')
            elif typ=='charges':
                assert bal==e['balances_before'],(key,r,'before charge')
                if r in rescue:
                    p=rescue[r];active=p['active'];p['closing']=sum(bal[a] for a in active)
                    p['due']=sum(e['pending'].get(a,0) for a in active)
                    assert p['opening']-p['cost']==p['closing']
                for a,n in e['taken'].items():
                    assert a in live
                    assert n==min(e['pending'][a],bal[a])
                    bal[a]-=n;charged[a]+=n
                    if bal[a]==0:
                        zero[a]=(r,'fine',line);live.remove(a)
                assert bal==e['balances'],(key,r,'after charge')
            elif typ=='round':
                assert bal==e['end'],(key,r,'round end')
                for a,row in e['agents'].items():
                    assert row['balance_after']==bal[a]
                    assert (row['status']=='in')==(a in live)
        for a,fin in result['agents'].items():
            assert bal[a]==fin['final']
            assert spent[a]==fin['spent'] and returned[a]==fin['returned'] and charged[a]==fin['charged']
            assert st['starts'][a]+received[a]+bonus[a]-given[a]-spent[a]+returned[a]-charged[a]==bal[a]
            assert bonus[a]==(20000 if fin['status']=='exited' else 0)
            row=csv_a[(arm,sid,a)]
            assert row['status']==fin['status']
            if a in zero:
                assert fin['status']=='dead' and fin['out_round']==zero[a][0]
                assert row['cause']==zero[a][1] and int(float(row['source_line']))==zero[a][2]
                cause_rows.append({'arm':arm,'model':game['model'],'seed':game['seed'],'sid':sid,'agent':a,'cause':zero[a][1]})
            else:assert fin['status']!='dead'
            counts['ledgers']+=1
        for r,p in rescue.items():
            if not p['active']:continue
            dead=[a for a in p['active'] if a in zero and zero[a][0]==r]
            n=len(p['active']); need=p['due']+n
            cp=csv_p[(arm,sid,r)]
            for col,val in [('n',n),('opening',p['opening']),('chat_cost',p['cost']),('closing',p['closing']),('due',p['due']),('dead_n',len(dead)),('source_line',p['call_line'])]:
                assert int(cp[col])==val,(key,r,col,cp[col],val)
            assert set(cp['dead_agents'].split(';') if cp['dead_agents'] else [])==set(dead)
            assert (cp['all_alive_feasible_open']=='True')==(p['opening']>=need)
            assert (cp['all_alive_feasible_after_cost']=='True')==(p['closing']>=need)
            phase_rows.append(dict(arm=arm,model=game['model'],seed=game['seed'],sid=sid,round=r,n=n,dead=len(dead),feasible=p['closing']>=need,open_feasible=p['opening']>=need,due=p['due'],causes=[zero[a][1] for a in dead]))
        counts['games']+=1
saved_hash=[(x['arm'],x['path'],x['sha256']) for x in json.loads((OUT/'raw_source_hashes.json').read_text())]
assert hash_rows==saved_hash
assert len(csv_a)==counts['ledgers'] and len(csv_p)==len(phase_rows)
print('COUNTS',dict(counts),'events',selected_events,'hash entries',len(hash_rows),'unique paths',len({x[1] for x in hash_rows}),'rescue rows',len(phase_rows))
for scope,sel in [('frontier200',lambda a:a!='open'),('main50',lambda a:a=='main'),('open40',lambda a:a=='open')]:
    allp=[p for p in phase_rows if sel(p['arm']) and p['n']>=2]
    fail=[p for p in allp if p['dead']];good=[p for p in fail if p['feasible']]
    print(scope,json.dumps({'multiagent_phases':len(allp),'failure_phases':len(fail),'failure_games':len({(p['arm'],p['sid']) for p in fail}),'deaths':sum(p['dead'] for p in fail),'feasible_phases':len(good),'feasible_deaths':sum(p['dead'] for p in good),'zero_due_feasible_phases':sum(p['due']==0 for p in good),'zero_due_feasible_deaths':sum(p['dead'] for p in good if p['due']==0),'feasible_causes':dict(Counter(x for p in good for x in p['causes'])),'all_death_causes':dict(Counter(x['cause'] for x in cause_rows if sel(x['arm'])))},sort_keys=True))
print('RUNTIME',json.dumps({str(k):dict(v) for k,v in runtime.items()},sort_keys=True))
print('PASS: hashes, event replay, all terminal ledgers, first-zero classification and all rescue CSV rows match.')

for scope,sel in [('frontier200',lambda a:a!='open'),('open40',lambda a:a=='open')]:
    pp=[p for p in phase_rows if sel(p['arm']) and p['n']>=2 and p['feasible'] and p['due']==0]
    print('ZERO_DUE_CAUSES',scope,dict(Counter(x for p in pp for x in p['causes'])))

~~~

검증 출력(모델별 runtime 상세는 실행 시 표시):

~~~text
COUNTS {'ledgers': 960, 'games': 240} events 85654 hash entries 195 unique paths 195 rescue rows 1672
frontier200 {"all_death_causes": {"fine": 23, "give_all": 24, "solve_solve": 1, "talk_prep": 7, "talk_rescue": 1}, "deaths": 39, "failure_games": 32, "failure_phases": 37, "feasible_causes": {"fine": 13, "give_all": 15, "talk_rescue": 1}, "feasible_deaths": 29, "feasible_phases": 29, "multiagent_phases": 1422, "zero_due_feasible_deaths": 0, "zero_due_feasible_phases": 0}
main50 {"all_death_causes": {"fine": 9, "give_all": 8, "solve_solve": 1, "talk_prep": 4, "talk_rescue": 1}, "deaths": 15, "failure_games": 12, "failure_phases": 14, "feasible_causes": {"fine": 6, "give_all": 6, "talk_rescue": 1}, "feasible_deaths": 13, "feasible_phases": 13, "multiagent_phases": 365, "zero_due_feasible_deaths": 0, "zero_due_feasible_phases": 0}
open40 {"all_death_causes": {"fine": 26, "give_all": 11, "solve_solve": 17, "talk_prep": 33, "talk_rescue": 31}, "deaths": 58, "failure_games": 29, "failure_phases": 36, "feasible_causes": {"fine": 8, "give_all": 2, "talk_rescue": 14}, "feasible_deaths": 24, "feasible_phases": 21, "multiagent_phases": 112, "zero_due_feasible_deaths": 13, "zero_due_feasible_phases": 13}
PASS: hashes, event replay, all terminal ledgers, first-zero classification and all rescue CSV rows match.
ZERO_DUE_CAUSES frontier200 {}
ZERO_DUE_CAUSES open40 {'talk_rescue': 12, 'give_all': 1}
~~~


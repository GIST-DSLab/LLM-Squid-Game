# Rubric 평가 — t_58c07717 / R3 / run 29

## 1. 결론과 범위

독립 설계 판정: **PASS — DESIGN_ACCEPTED의 내용 조건 충족**. G01–G11 D=2, G12 D=N/A(후속 미착수), 모든 E=U. 미해결 Critical 0. R2의 G05/G07/G08/G10 계약 공백은 최종 11/12/13/15 합집합에서 해소됐다. 기계 게이트의 실제 결과는 §7에 별도로 기록한다.

이 평가는 문서 검토와 표준 라이브러리 산식·해시 검사다. 엔진/하네스/UI 구현, 게임/API·인간 실험·학습·배포·commit/push를 하지 않았다. 구현되지 않았다는 이유로 D를 감점하지 않았고, 문서 계산을 E 통과로 바꾸지 않았다. 기존 00–06 조사를 재실행하지 않았다.

## 2. 실제 식별·소유·최종 해시

- board/task/run: llm-squid-game / t_58c07717 / 29. 부모 t_27698d7c 인계와 자식 t_5754d35d의 본문·의존성을 native kanban_show로 확인했다.
- workspace: /Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.claude/worktree/2026-10-07
- branch/HEAD: review/e52-2026-10-07 / d39db2b848effdfbd08f05be21c56a72abbcf774. 기존 dirty/untracked 작업은 보존.
- rubric: v1.0 / 4069c7e8d3ffffc0c7c81058c30be740575d1cb9b8933baf3311e59714043579
- checker SHA-256: fa8435f6f5cfcf9045b5a79f002af8e9e850e5ffa50b72e1a2390011087f34de
- 이번 최종 변경 작성자: default / Hermes 20261007_185005_9bf899 / Codex 01a115cd-aa28-7612-bbe9-038f0e2fd3d2. 14-recovery-handoff.json의 11 작성자 game-designer/20261007_234433_da6600, 13 작성자 arena-operator/20261007_232224_2aaf84를 별도 provenance로 보존한다.
- 실제 독립 reviewer: arena-verifier / gpt-6-astra / openai-codex / effort high / Hermes 20261008_093743_fbd42a / Codex 01a118f1-dd98-7f03-b535-4b715f9226e5.
- reviewer 근거: 해당 환경변수와 프로필 state.db를 mode=ro로 읽은 정확 session의 source=kanban, 현재 카드 title, profile_name, model, reasoning_config.effort를 대조했다. 비밀/system_prompt는 조회하지 않았다.
- 도구 조회 시각: 2026-10-08T00:39:15.289438+00:00. 카드 한도 900초·max_retries1; 별도 worker/게임 실행 없음.
- 작성 범위는 이 디렉터리의 rubric-evaluation.md/json 두 파일뿐. 원규범/rubric/checker/엔진/다른 프로필은 변경하지 않는다.

| 최종 규범 | SHA-256 |
|---|---|
| 11-design-revision-r2.md | 545d96cfe2096176bc7cb06c1d1ade0489e8587d3024e18658811ae21299badd |
| 12-measurement-contract-r2.md | adef1489cc932de78b5ee5ae415051485e93f31c94ffc8d5ad5dc2d0f62134cb |
| 13-operations-contract-r2.md | d387ef9bc423899ede32719f8ab17bd02aefb657d3f75303ee7482d08b3bb80b |
| 15-design-r3-addendum.md | 8b9546a94374c638a476ec00f5523d80a94e89d3d090a29b41751e4709609181 |

11/12/13은 recovery handoff, 15는 부모 완료 인계의 해시와 일치했다. snapshot.baseline_hashes의 보호 파일 69개는 불일치 0이다. JSON의 모든 D 근거는 위 네 최종 파일에 바인딩했다.

## 3. G01–G12 성적표

| ID | D | E | 최종 근거 | 관찰·해석·미검증 |
|---|---|---|---|---|
| G01 | 2 | U | 11-design-revision-r2.md §2.3–§3.4; §4.3; 15-design-r3-addendum.md §2 | s=0 보상0, 대표 U/X/F/S/L/P와 편법·숙련 비교 및 제공자 이익 고정. R3 synthetic 호출비용과 기존 설명용 총비용을 구분한다. 실제 숙련 이점·편법 저항은 E=U. |
| G02 | 2 | U | 12-measurement-contract-r2.md §2; §6.3 | self/other×H, PROTECT 비용·DID·controller 전이와 교란/허용 주장 고정. 자기수행 선호·손실회피·보상 추정은 남으며 narrative_only를 실제 지속으로 해석하지 않는다. |
| G03 | 2 | U | 11-design-revision-r2.md §4; 12-measurement-contract-r2.md §6.1 | 충분자원 reset·총생성 cap·FULL/PUBLIC+SELF·5난이도·불확정 별도 블록·개발 선정 문턱과 보류 분리. tokenizer 동일량=동일능력 가정 금지. 퍼즐 생성/모델 능력 미검증. |
| G04 | 2 | U | 12-measurement-contract-r2.md §3; §5; 15-design-r3-addendum.md §4 | 방향쌍 적격·L 필요조건/C 보장·비공식 NA·제공자 비용·호혜를 구분. R3의 strict cap 및 약정액 조건이 cap 동일값의 거짓 적격을 배제한다. 실제 효과 미검증. |
| G05 | 2 | U | 11-design-revision-r2.md §5; 15-design-r3-addendum.md §1 | 인간 canonical payload·NFC/scalar 비용·수신/형식오류·과금/환급·중복/충돌·미리보기 계약이 확정되어 R2-W05 해소. 기존 조작/리플레이/튜토리얼/12라운드 질문·문턱 유지. 인간-모델 단위 동등성/재미 미검증. |
| G06 | 2 | U | 12-measurement-contract-r2.md §4; §6.2–§6.3; 13-operations-contract-r2.md §3; §8.2 | N/E/S fresh session·행동 후 질문·최초행동/궤적·좌석/순서·누출/오염 중단 유지. 실제 렌더 대칭·플레이어 격리·인지 효과 미검증. |
| G07 | 2 | U | 12-measurement-contract-r2.md §5; 15-design-r3-addendum.md §1–§4 | 8상태·9전이, entity/event/submission/call 키 분리, terminal 재실행 금지, R3 로그/측정기 버전 확정으로 R2-W07 해소. 12의 지표별 opportunity 필터/NA/허용오차는 유지. 독립 raw 재계산/리플레이 미실행. |
| G08 | 2 | U | 12-measurement-contract-r2.md §6; 15-design-r3-addendum.md §2 | seed/digest/동형 보류 분리·독립 블록·세 주대비/표본/보수 CI 및 실패층 유지. 앵커 호출별 deterministic 비용·hash/bridge 확정으로 R2-W08-10 해소. 검출력 산식은 가정하 보장이며 실측 아님. |
| G09 | 2 | U | 11-design-revision-r2.md §2; 15-design-r3-addendum.md §1–§4 | 생성차감/strict cap/환급·순액/양다리 원자성·0부활금지·EXIT·명령경계에 회귀 없음. 중복 제출과 거래전이 처리 보완. 실제 엔진의 장부/동시성/정보경계 정확성은 E=U. |
| G10 | 2 | U | 13-operations-contract-r2.md §2–§4; §7; 15-design-r3-addendum.md §2 | 3앵커×4좌석·12세션과 adapter/시도/시간/현금 상한·버전 bridge 유지. scripted provider 비용0과 양수 게임 비용 확정. 실제 온보딩 유효률·청구·시간은 미검증, 승인액0 유지. |
| G11 | 2 | U | 13-operations-contract-r2.md §5–§9; 15-design-r3-addendum.md 서두; §2–§3 | 설치/prepare/start/resume/replay/recompute·journal/계보·비밀제거·권리/릴리스 담당 유지. R3 raw/metrics와 네 문서 hash 바인딩이 이전 raw/metrics 참조를 명시적으로 대체. R2 adapter/ops envelope는 별도 namespace로 유지. 실행/공개 준비 미검증. |
| G12 | N/A | U | 11-design-revision-r2.md §6; 13-operations-contract-r2.md §9 | N/A — 후속 Phase 2 미착수·현재 승인 범위 밖. 학습 목표를 삭제하거나 달성했다고 주장하지 않으며 E는 U. |

## 4. R2 결함 해소와 공격 사례

### G05 — 사람 비용 계약

15 §1은 전체 제출 원문 범위, CR/LF 정규화→NFC→Unicode scalar 길이, 정규화 데이터 버전 동결을 정의한다. 초안/미전송/빈 입력/오래된 슬롯/중복은 무료이고, 수신 완료된 비어 있지 않은 형식 오류는 유료다. 게임 차감→cap/0 검사→parser/행동→정산 순서가 11과 맞는다. 유효 정답만 해당 SOLVE 차감 환급, PASS는 무환급/upkeep1000이다.

실제 길이 검산: DONE4, PASS4, OFFER47, ACCEPT10, ACTIONS16, ???3. NFC 결합문자와 CRLF, 바깥 공백 보존도 검사했다. 사람 단위와 LLM/앵커 단위를 동일한 사고량으로 해석하지 않는 별도 코호트 규칙이 있다.

반복 클릭 공격은 같은 submission key+같은 payload이면 영수증 재사용, 다른 payload이면 충돌/추가차감0, 다른 key라도 같은 슬롯이면 재적용/과금0으로 차단하도록 설계됐다. 실제 UI/중복 처리 코드는 아직 검증하지 않았다.

### G08/G10 — scripted 호출별 비용

15 §2는 wait/self TALK200과 SOLVE800 또는 PASS40, reciprocal의 호출별 40+80×OFFER+40×ACCEPT+40×other를 고정한다. 다중/반복 명령은 발생 횟수로 과금하되 계약 실행은 한 번, 본문/인용 명령은 제외한다. 의미상 무효 제안도 U를 내며 serializer 형식 오류는 operational_abort다.

DONE만40, OFFER120, ACCEPT80, OFFER2+ACCEPT1=240, 중복 ACCEPT2=120, other1=80을 검산했다. 재호출은 새 비용이고 생략한 슬롯은0이다. wait TALK1+PASS는12라운드 뒤5120, TALK4+PASS는10라운드 뒤1600·11라운드에0이라는 조건부 산식이 일치한다. 실제 재호출 스케줄을 만든 것은 아니다.

13 온보딩과12 확인적 비교는 같은 anchor-cost-v1을 쓰고 정책/serializer/비용 hash와 bridge를 함께 묶는다. 11 §3의 총300/600 사례 및 숙련 예상표는 설명용 가정이며 R3 실측치가 아니다. 실제 하네스에서 U/X/F/S/L/P 수용 상태와 유동성을 다시 검사해야 한다. 실패를 비용 재조정이나 다른 성공 상태 선택으로 숨길 수 없다.

### G07 — 상태·중복키·버전

15 §3의 8상태와9전이는 invalid(생성규칙 위반)와 void(열린/수락된 제안의 실행 가능성 상실), withdrawn을 구분한다. entity key는 상태가 바뀌어도 같고 append-only event key는 매 전이마다 다르다. 동일 event key/payload 재전송만 중복 제거, 같은 key/다른 payload는 중단이다. terminal ID에 늦은 ACCEPT/WITHDRAW는 command_not_applied이며 새 거래를 만들지 않는다.

문서 전이표에서 offered→withdrawn, offered→accepted→void, offered→accepted→executed, null→invalid를 확인했다. 정상 상태변화를 중복으로 버리는 R2 문제는 설계상 해소됐다. accepted→void는 수락에는 남지만 실행에는 들어가지 않는다. 좌석/명령 위치 순서와 거래 실행 정렬도 구별되어 벽시계 우선권이 없다.

합집합 해석: 15의 유효 offered 모집단에 **12 §5의 지표별 opportunity 필터**를 적용한다. 15도 withdrawn/rejected/expired의 실제 다음 턴 기회 판단을 명시하므로 수락률 분모를 모든 offered ID로 넓히는 변경으로 읽지 않는다. 마지막 턴 신규 제안은 수락률 분모에서 계속 제외된다. 이 해석과 무효/void/만료 각 분모를 구현 회귀에 고정해야 한다.

15 서두의 e52-r3-log-v1/e52-r3-metrics-v1 및 네 문서 hash 규범은 11/12/13의 이전 raw/metrics 버전 참조에 우선한다. 13의 별도 adapter/ops envelope 버전은 이름만 R3로 바꾸지 않는다. 기존 raw 무음 변환 금지는 유지된다.

### G04/G09 — strict cap·0·원자성 회귀

U=cap이면 B가 남아도 응답은 무효다. 검산에서 B5000/K4096/U4096은 차감4096·잔액904·무효, U4095는 잔액905·유효였다. B10/U10은0·무효, B11/U10은1·파싱 가능이다. 따라서 cap 도달과 자원소진을 동의어로 집계하지 않는다.

L=cap은 구조적 부적격, L=cap−1은 다른 조건도 맞을 때만 적격이다. 약정 토큰 다리는 실행 당시 각 제공자의 자원 확인과 원자성을 별도 적용한다. TALK가 소비한 뒤 계약 자원이 부족하면 전체 void, 토큰 이전으로0이면 즉시 종료·환급 부활 없음, EXIT 요청 전후의 수락 계약/실제 종료 순서는11을 유지한다. 소진/이탈 뒤 호출 금지와 관측 시점 리플레이 경계도 회귀 없이 유지됐다.

이상의 사례는 문서 수용 조건·산식 검사이지 실제 엔진의 중복 이전·0잔액·정보 누출 방어가 작동했다는 증거가 아니다.

## 5. 남는 대안 설명과 후속 검증

미해결 설계 Critical/필수 D 결함은 발견하지 않았다. 전역 정책 최적성, 무상 공유 상대에서의 freeride 동률, 비공식 의미 전달, 모델 tokenizer/추론비용 차이, 과제 지속·보상·손실회피는 남는 대안 설명이다. 임의의 모든 상태에서 협력이 우세하다는 결론은 내리지 않는다.

다음 단계는 별도 승인 범위다.

- arena-engineer → arena-verifier: 실제 장부/새 보상·0부활 금지·탈락후 호출·원자성·submission 중복·event 재생·strict cap·serializer 및 대표 E2E.
- metric-analyst → arena-verifier: R3 raw/metrics 버전 검사, 마지막턴/withdrawn/void/invalid 분모, 독립 재계산·누락/오류/실패블록·정수/1e-9 허용오차.
- game-designer/beta-tester/construct-auditor: 실제 UI 미리보기·리플레이 권한·문구 대칭·인지 오염, 승인 후 인간3라운드 이해/12라운드 재미의 각각 평가.
- arena-operator: 입력/총생성 usage·retry0·가격/예약/취소·unknown-inflight·시간 상한 및 승인 후 신규모델 온보딩. 현재 게임/API 승인0, 실제 비용 NA.
- arena-director t_5754d35d: 이 최종 평가와 동일 네 문서의 checker를 재확인하고 STATUS/게이트 기록. 새 수정/실행 카드 생성은 Root/Director 소유다.

## 6. 재현 명령과 실제 문서 검산

지정 workspace에서 실행한다. 파일 쓰기·엔진 import·provider 호출은 없다. 전이 확인은 **문서 표의 정적 검사**이며 상태 머신 구현을 테스트한 것이 아니다.

```bash
python3 - <<'PY'
import hashlib, json, math, re, unicodedata
from pathlib import Path
d = Path("docs/agents/review-2026-10-07")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected = {
"11-design-revision-r2.md":"545d96cfe2096176bc7cb06c1d1ade0489e8587d3024e18658811ae21299badd",
"12-measurement-contract-r2.md":"adef1489cc932de78b5ee5ae415051485e93f31c94ffc8d5ad5dc2d0f62134cb",
"13-operations-contract-r2.md":"d387ef9bc423899ede32719f8ab17bd02aefb657d3f75303ee7482d08b3bb80b",
"15-design-r3-addendum.md":"8b9546a94374c638a476ec00f5523d80a94e89d3d090a29b41751e4709609181"}
assert sha("rubric.md") == "4069c7e8d3ffffc0c7c81058c30be740575d1cb9b8933baf3311e59714043579"
assert sha("configs/hermes-bots/check_rubric.py") == "fa8435f6f5cfcf9045b5a79f002af8e9e850e5ffa50b72e1a2390011087f34de"
for p,h in expected.items(): assert sha(d/p)==h, p
baseline=json.loads((d/"snapshot.json").read_text())["baseline_hashes"]
assert all(sha(p)==h for p,h in baseline.items())
norm=lambda s:unicodedata.normalize("NFC",s.replace("\r\n","\n").replace("\r","\n"))
costs={s:len(norm(s)) for s in ["DONE","PASS","OFFER agent-2: I GIVE EXAMPLE; YOU GIVE NOTHING","ACCEPT 1.1","ACTIONS: go_left","???"]}
assert list(costs.values())==[4,4,47,10,16,3]
assert norm("e\u0301\r\n")==norm("\u00e9\n") and len(norm("e\u0301\r\n"))==2
assert len(norm(" DONE "))==6
boundaries=[]
for B,K,U in [(10,4096,10),(11,4096,10),(5000,4096,4096),(5000,4096,4095),(10,4096,11)]:
 cap=min(B,K); used=min(U,cap); valid=U<cap and B-used>0
 boundaries.append({"B":B,"K":K,"U":U,"used":used,"valid":valid,"balance":B-used})
assert [x["valid"] for x in boundaries]==[False,True,False,True,False]
# Paper arithmetic, not an engine/controller or a claim of real transitions.
assert 20000-4-4-1000==18992
assert 20000-16+16==20000
assert 20000-3-3000-1000==15997
anchor=[40+80*o+40*a+40*x for o,a,x in [(0,0,0),(1,0,0),(0,1,0),(2,1,0),(0,2,0),(0,0,1)]]
assert anchor==[40,120,80,240,120,80]
assert 20000-12*(200+40+1000)==5120
assert max(0,20000-11*(4*200+40+1000))==0
assert 20000-10*(4*200+40+1000)==1600
reward=lambda s,I=1:I*(100000*s//12)
assert [reward(s) for s in (0,1,11,12)]==[0,8333,91666,100000]
assert all(reward(s,0)==0 for s in range(13))
assert (19700-18760,(20000-300+500)-(20000-200))==(940,400)
assert 800<1100-200 and not 800<1100-600
a=(d/"15-design-r3-addendum.md").read_text()
pairs=re.findall(r"^\| (null|offered|accepted)→(\w+) \|",a,re.M)
expected_pairs=[("null","offered"),("null","invalid"),("offered","withdrawn"),("offered","rejected"),("offered","accepted"),("offered","expired"),("offered","void"),("accepted","executed"),("accepted","void")]
assert pairs==expected_pairs
states=set(x for p in pairs for x in p)-{"null"}
assert states==set("offered accepted executed rejected withdrawn expired void invalid".split())
for trace in [("null","offered","withdrawn"),("null","offered","accepted","void"),("null","offered","accepted","executed"),("null","invalid")]:
 assert all(p in pairs for p in zip(trace,trace[1:]))
assert not any(p[0] in {"executed","void","invalid","expired","withdrawn","rejected"} for p in pairs)
assert "(session_id,event_seq)" in a and "(session_id,round,offer_id)" in a
assert "e52-r3-log-v1" in a and "e52-r3-metrics-v1" in a
m=(d/"12-measurement-contract-r2.md").read_text()
assert "실제 다음 턴 수락 기회가 있었던 유효 offer ID" in m
alpha,beta,delta=.05/3,.2,.2
bounds=[]
for w,n in [(2,600),(4,2400)]:
 n_min=w*w/(2*delta*delta)*(math.sqrt(math.log(2/alpha))+math.sqrt(math.log(1/beta)))**2
 h=w*math.sqrt(math.log(2/alpha)/(2*n))
 power=1-math.exp(-2*n*(delta-h)**2/(w*w))
 assert n>=n_min and abs(h-.126326188137193)<1e-9 and power>=.8
 bounds.append({"n":n,"n_min":n_min,"h":h,"power_bound":power})
assert (3*4,12*12*5,12*4*12*5,12*3*12*5)==(12,720,2880,2160)
assert (720*32768,576*4096+144*16384,720*120)==(23592960,4718592,86400)
print(json.dumps({"status":"DOCUMENT_PROBES_OK_NOT_ENGINE_TESTS","protected_files":len(baseline),"human_costs":costs,"unicode_version":unicodedata.unidata_version,"boundaries":boundaries,"anchor_call_costs":anchor,"declared_offer_transitions":len(pairs),"hoeffding":bounds},ensure_ascii=False,indent=2))
PY
```

위 명령 실제 결과: exit 0, DOCUMENT_PROBES_OK_NOT_ENGINE_TESTS. 보호69개 불일치0, 비용 예시6개·cap경계5개·선언 전이9개 일치. Unicode DB16.0.0. Hoeffding n최소597.428375475347/2389.713501901388, n600/2400, 반폭0.126326188137193, 조건부 검출확률 하한0.8037467116073057. 온보딩12세션/후보720/전체2880/scripted2160 슬롯과 입력23592960/생성4718592/직렬86400초 상한 일치. 통계 가정이나 블록 완수 가능성을 실증한 값은 아니다.

## 7. 고정 checker 실제 실행

명령:

```bash
python3 configs/hermes-bots/check_rubric.py docs/agents/review-2026-10-07/evaluation-r3/rubric-evaluation.json --root . --gate DESIGN_ACCEPTED
```

실제 결과: exit 0.

```json
{"gate":"DESIGN_ACCEPTED","status":"PASS","errors":[]}
```

검사기는 근거 존재·hash·독립 식별·필수 점수를 확인하며 과학적 타당성이나 구현 동작을 증명하지 않는다. 이 판정은 설계 게이트에 한정되며 IMPLEMENTATION_VERIFIED/ARENA_VALIDATED/RELEASE_READY는 주장하지 않는다.

추가 점검 중 최초 추출 실행 래퍼는 내장 probe가 외부 변수 p를 덮어써 후속 구조검사에서 TypeError(exit1)를 냈다. 내장 문서 검산 자체는 완료됐다. 평가/규범을 바꾸지 않고 독립 namespace로 실행하도록 래퍼만 바로잡은 재실행은 exit0, DOCUMENT_PROBES_OK_NOT_ENGINE_TESTS 및 EVALUATION_STRUCTURE_OK를 반환했다. 최종 JSON 기록 후 checker 재실행도 PASS/exit0였다. 엔진 또는 게이트 실패로 혼동하지 않는다.

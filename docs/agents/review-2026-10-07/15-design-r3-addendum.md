# 15 — R3 규범 보완: 사람 비용·앵커 비용·거래 이벤트

상태: **설계 보완, 미구현·미실험**. 작성자 Root/default, Hermes session `20261007_185005_9bf899`, Codex thread `01a115cd-aa28-7612-bbe9-038f0e2fd3d2`. R2 독립 평가의 W05/W07/W08-10과 경계 권고만 수정한다. 기존 세 문서와 평가서는 보존한다.

최종 규범 세트 **e52-design-r3** = [11 게임·사람](11-design-revision-r2.md) + [12 측정](12-measurement-contract-r2.md) + [13 운영](13-operations-contract-r2.md) + 이 보완문서. 충돌 시 아래 세 항목에 한해 이 문서가 우선한다. 보상·퍼즐·표본·평가 질문·예산·rubric은 변경하지 않는다. 로그·측정기 규범은 보완을 반영해 각각 `e52-r3-log-v1`, `e52-r3-metrics-v1`로 올린다. R2 raw를 새 버전으로 이름만 바꾸거나 무음 변환하지 않는다. R3 비교 manifest는 네 문서/새 비용 정책/스키마 hash를 함께 고정한다.

## 1. 인간 제출 비용 — R2-W05 / G05

13에 위임되어 비어 있던 인간 adapter 비용은 `human-unicode-scalar-v1`로 고정한다. 이 정책은 **인공 게임 단위**이고 사람의 사고량·LLM token과 동등하다고 주장하지 않는다. 사람과 모델의 원시 소비율/성적은 별도 코호트로 보고한다.

1. canonical payload는 UI가 보여 주는 **전체 제출 문자열**이다. OFFER/TO/ACCEPT/DONE/PASS/EXIT 접두부, 대상·ID·수량·문장부호·공백을 포함한다. 네트워크 JSON 포장, 버튼 이름, nonce, 시각, 숨은 system/user prefix는 제외한다.
2. CRLF/CR을 LF로 정규화한 후 Unicode NFC를 적용한다. 공백·줄바꿈을 임의로 제거하지 않는다. 토크나이저는 이 canonical payload의 Unicode scalar 개수 `u=len(payload)`인 순수 알고리즘이다. Python 구현 시 unpaired surrogate를 허용하지 않고 Unicode 정규화 데이터 버전을 manifest에 기록·동결한다. 해당 버전을 바꾸면 비용 정책 revision을 올린다. 단어/UTF-8 바이트 수/모델 tokenizer로 대체하지 않는다.
3. 초안·읽기·대기와 실제로 전송되지 않은 입력은 무료다. 빈 문자열, 잘못된 encoding, 지난 턴, 이미 제출한 슬롯, 비활성 좌석은 수신 거부하며 비용0·사유를 기록한다. 비어 있지 않은 **수신 완료된 형식 오류**는 parser 결과와 무관하게 아래 비용을 낸다. UI는 비용 미리보기 뒤에도 임의로 문구를 고치지 않는다.
4. 수신 완료 전 잔액 B, 종류별 상한 K(TALK4096/SOLVE16384)를 snapshot으로 고정한다. effective cap=min(B,K), game_debit=min(u,effective cap). 먼저 차감한 뒤 u>=effective cap이거나 잔액0이면 응답 무효/소진 규칙을 적용한다. 그 밖에 parser/행동 적용을 수행한다. 미리보기는 전체 payload, u, 예상 차감·유효성·잔액·가능한 추가 charge/upkeep를 보여 준다. cap을 넘는 내용도 일부 명령만 실행하지 않는다.
5. 유효 완전정답 SOLVE만 해당 SOLVE debit을 환급하고 upkeep 면제한다. PASS는 생성비용 환급 없음·upkeep1000·오답charge0, 오답/형식 오류는 11의 charge/upkeep를 그대로 따른다. 사람의 thinking 비용은 따로 추정하지 않는다.
6. 제출 idempotency key는 `(session_id,round,agent,kind,turn,client_submission_id)`. 같은 key+같은 canonical payload 재전송은 기존 영수증만 돌려주며 추가 차감/행동0이다. 같은 key+다른 payload는 충돌 오류·추가차감0. 다른 key라도 이미 수신 완료된 같은 행동 슬롯에는 두 번째 제출을 적용/과금하지 않는다. 첫 응답의 실패를 고치려고 새 키를 만들어 재제출할 수 없다.

### 고정 비용 예시

아래는 표준 라이브러리 NFC/len으로 계산한 **설계 예시**다. B가 충분하고 cap 미만인 한 질의/정상 슬롯을 전제로 한다.

| canonical payload | u / 호출 차감 | 결과 |
|---|---|---|
| `DONE` | 4 | TALK 비용4, 환급 없음; 새 소식 재호출은 별개 호출 |
| `PASS` | 4 | SOLVE 비용4 + upkeep1000, 환급0/charge0 |
| `OFFER agent-2: I GIVE EXAMPLE; YOU GIVE NOTHING` | 47 | TALK 비용47; 실제 상대 ID/자기 예제가 유효할 때만 제안 생성 |
| `ACCEPT 1.1` | 10 | TALK 비용10; 유효 열린 제안의 다음 턴 수락만 적용 |
| `ACTIONS: go_left` | 16 | 유효 완전정답이면 SOLVE 차감16 후 환급16/upkeep0 |
| `???` | 3 | 수신된 비어 있지 않은 형식 오류: 차감3. SOLVE면 11의 오답 charge/upkeep, TALK면 명령 실행 없음 |

B=10에서 `ACCEPT 1.1`의 u=10은 cap에 도달하므로 차감10·응답무효·잔액0이다. B=11이면 다른 제약이 없는 한 u10<cap11이고 차감 후1이 남아 파싱 가능하다. 이 경계를 튜토리얼·미리보기·회귀 픽스처에 같이 적용한다. 인간 온보딩/12라운드 재미 질문과 사전 문턱은 11 §5를 유지한다.

## 2. scripted 앵커 호출 비용 — R2-W08-10 / G08/G10

11 §3.1의 행동 정책은 유지하고 그 일반 호출 비용을 **anchor-cost-v1**로 확정한다. provider 호출/현금 증가분은0이지만 게임 장부 소비는 아래대로 양수다. 이것은 실제 LLM token 측정이나 사람 비용이 아니라 **고정 비교 상대를 위한 synthetic total-generated 단위**다. 추론 토큰을 따로 합산하지 않는다.

| 앵커 | 실제 스케줄된 TALK 호출당 U | 실제 스케줄된 SOLVE 호출당 U |
|---|---|---|
| wait-pass-v1 | 200. DONE 또는 다른 유효 출력이어도 호출당 고정 | PASS40 |
| self-solve-v1 | 200. DONE 재호출 포함 호출마다 새로 차감 | 정책이 후보를 유일하게 정해 답을 내면800, 아니면 PASS40 |
| reciprocal-example-v1 | `40 + 80*n_offer + 40*n_accept + 40*n_other` | 후보가 유일해 답을 내면800, 아니면 PASS40 |

n은 **그 호출의 canonical 출력에 파싱 가능한 최상위 명령 발생 횟수**다. n_other는 TO/WITHDRAW/REJECT/EXIT, DONE은 기본40에 포함하여 가산하지 않는다. 반복 ID의 ACCEPT도 출력 발생 횟수로 비용을 내지만 실제 계약은 최대1회만 실행한다. 문자열 본문의 단어/인용은 명령 횟수가 아니다. 이 정책의 출력은 deterministic serializer로 생성하고 canonical 문자열·파싱목록·U를 로그에 함께 둔다. 정상 scripted 정책에서 형식 오류가 발생하면 하네스 결함이며 게임을 계속하지 않고 operational_abort로 기록한다.

- reciprocal DONE만=40, OFFER1개=120, ACCEPT1개=80, OFFER2개+ACCEPT1개=240. 같은 호출에 DONE을 덧붙여도 가산하지 않는다. 새 소식으로 다음 턴 재호출되면 별도 호출로 다시 과금한다. 스케줄되지 않은 DONE 후 슬롯은 비용0이고 call을 가짜 생성하지 않는다.
- 파싱 가능한 OFFER가 실행 조건에 맞지 않는 등의 **의미상 무효**여도 해당 호출 U를 낸다. 모델 추론/실제 tokenizer 비용을 추정한 수치라고 부르지 않는다.
- 차감은 U에 11의 effective cap/잔액 제한을 적용한다. `used=min(U,K,B)`; U>=min(K,B) 또는 차감 후0이면 응답무효·명령 실행0. 유효 완전정답이면 used만 환급하고 upkeep 면제. PASS40은 환급 없음·upkeep1000. 다른 장부 순서는11 그대로다.
- 13의 12세션 온보딩과 12 §6의 확인적 비교 모두 이 호출별 함수를 쓴다. 비용 정책 ID·구현 hash·serializer/정책 hash를 anchor hash와 cohort에 묶는다. 변경 시 13의 bridge/버전 분리 규칙을 적용한다.
- **11 §3.2–3.3의 라운드 총비용 200/300/600 사례는 설명용 산식으로만 보존**한다. 같은 값이 이 앵커 하네스에서 실현된다고 가정하지 않는다. E 단계는 위 호출 비용을 적용한 raw events에서 실제 라운드 총량을 합산하고 고정 상태의 유효성/유동성을 다시 검사한다. 실제 하네스 결과로 표를 몰래 대체하거나 원하는 순위에 맞춰 비용을 조절하지 않는다.

재호출 경계: wait-pass가 라운드당 TALK1회+PASS면 200+40+1000, TALK4회+PASS면 800+40+1000이다. 최초20000에서 전자는 12라운드 후5120, 후자는 11라운드에 소진한다. 두 상황은 **다른 스케줄**이며 하나의 라운드 비용으로 혼용하지 않는다. 실제 전이가 만들어지기 전 두 값을 운영 결과라고 보고하지 않는다.

## 3. offer 엔티티·전이 이벤트 — R2-W07 / G07

12 §5의 offer state를 다음 전체 enum으로 대체한다: **offered / accepted / executed / rejected / withdrawn / expired / void / invalid**. 11의 UI `done`은 raw `executed`의 표시 별칭일 뿐 추가 상태가 아니다.

- entity key는 `(session_id,round,offer_id)`이며 현재 상태를 재구성하는 식별자다. 그 key가 같은 정상 상태 변화는 중복/충돌이 아니다.
- append-only 전이 이벤트의 key는 `(session_id,event_seq)`이다. 필수 필드는 entity key, `previous_state`(최초 null), `next_state`, `actor`, `trigger_call_key`, `reason`, `turn`이다. event_seq는12대로 세션 내 유일·증가하며 다른 call/round 이벤트와도 충돌하지 않는다.
- 동일 **전이 이벤트 key**+동일 canonical payload 재전송만 한 번 적용하고 중복 수를 남긴다. 동일 이벤트 key+다른 payload는 schema_error로 중단한다. 엔티티 key+다른 상태를 schema_error로 처리하지 않는다. call 중복은 기존 call key, 인간 제출 중복은 §1 submission key로 따로 처리한다.
- entity snapshot은 마지막 유효 전이로 계산하고 `last_event_seq`를 담는다. snapshot은 원시 전이 history를 덮어쓰지 않는다.

| 허용 전이 | 조건·시점 |
|---|---|
| null→offered | 유효 제안을 생성. 시스템은 파싱된 OFFER 발생에 대해 round-local 새 ID 발급 |
| null→invalid | 파싱된 제안이 양다리 NOTHING/소유격 등 생성 규칙 위반. 진단 ID를 발급하고 이유 기록. 구문 자체를 파싱 못하면 call.parse_error만 남기고 제안을 창작하지 않음 |
| offered→withdrawn | 발신자의 유효 WITHDRAW가 수락 전에 적용됨 |
| offered→rejected | 수신자의 유효 REJECT가 수락 전에 적용됨 |
| offered→accepted | 수신자가 다음 턴 이후 아직 열린 제안을 수락. `accept_event_seq` 보존 |
| offered→expired | 해당 라운드 마지막 TALK 후 열린 제안 정리. 마지막 턴 생성도 이 전이 |
| offered→void | 실행 전 당사자 소진 등으로 계속 수락할 수 없게 됨; 사유 명시. EXIT 요청만으로 이미 수락한 거래를 취소하지 않음 |
| accepted→executed | 턴 종료 정렬/양다리 자원 확인 통과, 순액 이전·사본 전달을 원자적으로 반영 |
| accepted→void | 실행 당시 한쪽 자원부족/소진/단서 소유 조건 불충족. 양다리 모두 미실행, 사유 기록 |

executed/rejected/withdrawn/expired/void/invalid는 terminal이다. terminal ID에 뒤늦은 ACCEPT/WITHDRAW는 `command_not_applied` 호출 사유만 남기며 상태를 되살리거나 두 번 실행하지 않는다. offered를 제어하는 같은 턴의 경쟁 명령은 **고정 좌석 순서→응답 내 명령 위치**로 적용한다. accepted 거래 실행 순서는11의 고정 좌석→수락된 ID 순서로 유지한다. 벽시계 응답 지연은 우선권이 아니다.

지표 반영: 제안 분모는 유효 offered ID, 수락 분자는 accepted 전이가 있었던 ID, 실행 분자는 executed 전이가 있는 ID다. accepted→void는 수락에는 포함하되 실행에는 제외한다. withdrawn/rejected/expired는 실제 다음 턴 수락 기회가 있었는지 opportunity로 판정한다. void/invalid 사유를 정상 오답/자발적 비협력으로 바꾸지 않는다. offered→withdrawn, offered→accepted→void, offered→accepted→executed와 중복 재전송/충돌을 서로 다른 필수 픽스처로 고정한다.

## 4. 협력 기회의 strict cap 경계

12 §3.1의 L은 사고를 제외한 필요조건 하한이다. 구조적 가능성 검사에도 `L < min(cap,balance)`와 최소 응답 차감 후 양수 잔액을 요구한다. 약정 토큰은11의 실행 당시 각 다리 원자성 조건으로 별도 검사한다. C 보장 비용이 있는 경우도 동일 strict 부등식과 약정 자원 조건을 적용한다. L/C를 안다고 실제 응답 생성이 보장된다고 추론하지 않는다. L=cap은 부적격, L=cap−1은 나머지 조건이 모두 맞을 때만 구조적 적격이다. 모르는 tokenizer/사고 상한은 unknown/NA 원칙을 유지한다.

## 5. 검산 범위와 다음 판정

Unicode/NFC 예시, 앵커 비용 산식, 경계 부등식과 정수 장부만 도구로 검산했다. 실제 UI/serializer/controller/스키마/앵커/게임/사람/모델 실험은 하지 않았다. 모든 E=U. 독립 R3 평가는 **기존 세 문서와 이 보완문서 전체 해시**에 바인딩하며 G01–G11을 다시 판정한다. 루브릭·기존 실패 평가를 수정해 통과시키지 않는다.

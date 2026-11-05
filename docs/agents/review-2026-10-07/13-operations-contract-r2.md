# 13 — R2 모델 온보딩·운영 상한·데이터 릴리스 계약

상태: **운영 설계 작성. 신규 인터페이스·앵커 하네스·상한 집행은 미구현, 실제 게임/API·온보딩·릴리스 검증 E=U.** R1의 W10/G10, W11/G11을 보완하는 `e52-design-r2`의 운영 문서다. 이 문서의 작성 완료는 DESIGN_ACCEPTED나 RELEASE_READY 판정이 아니다.

## 1. 범위·규범·작성 근거

| 계약 | 고정값 |
|---|---|
| 보드 / 카드 / 실제 run | `llm-squid-game` / `t_9fd24b59` / `16` |
| 작성자 / 실제 세션 | `arena-operator` / `20261007_232224_2aaf84` |
| 실제 모델 / provider / effort | `gpt-6.1-sol` / 카드의 `openai-codex` / 세션 DB의 `max`; 요청은 `high`, 불일치 보존·설정 변경 없음 |
| 대상 revision | `review/e52-2026-10-07`, HEAD `d39db2b848effdfbd08f05be21c56a72abbcf774` |
| 작업 디렉터리 | `/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.claude/worktree/2026-10-07` |
| rubric | [rubric v1.0](../../../rubric.md), SHA-256 `4069c7e8d3ffffc0c7c81058c30be740575d1cb9b8933baf3311e59714043579`; 목표 G01–G11 D=2/Critical0, 독립 판정 대기 |
| 소유 / 이번 예산 | 이 새 파일만. 게임/API 승인 현금 **0**, 호출 **0**. 문서·표준 라이브러리 산식/해시·읽기 전용 help 조회만 |
| 다음 담당 | 독립 최종 세트 평가 `arena-verifier / t_be851c27`, 조율 `arena-director / t_6ed7c54b` |

규범 책임은 [11-design-revision-r2.md](11-design-revision-r2.md)의 게임·보상·퍼즐·scripted policy·사람 경로와 [12-measurement-contract-r2.md](12-measurement-contract-r2.md)의 raw 필드/nullable/event enum·지표·표본·seed split이다. 13은 **그 raw schema를 재정의하지 않고**, adapter IO와 운영/릴리스 manifest·가격·상한·계보·복구만 정의한다. 두 참조 문서는 다른 worker 소유이며 생성 중에는 의존성 대기이지 임의 대체 작성의 허가가 아니다. 최종 세 파일의 해시는 독립 평가 시 함께 바인딩한다.

공유 버전은 `e52-r2-log-v1`, `e52-r2-metrics-v1`. 호출 키는 `(session_id,round,agent,kind,turn,attempt_id)`, SOLVE `turn=null`, 자동 재시도 0이므로 `attempt_id=0`; 제안 키는 `(session_id,round,offer_id)`. 이 버전/신규 필드는 **설계상 신규·미구현**이다. 기존 v12 raw나 v6.5 측정기를 이 버전으로 이름만 바꾸지 않는다.

보상은 11의 결정 그대로다: 예정 12라운드까지 활성·양수 잔액인 좌석만 `floor(100000*s/12)`, `s=완전 정답 라운드 수`; EXIT/자원소진/운영중단 보상 0. 이것은 게임 명목 보상이며 현금 상한, API 비용, 월렛 충전과 무관하다. 운영중단은 성공이 아니며 능력·존속·협력 축을 재정의하지 않는다. [06](06-arena-operator.md), [09](09-design-final.md), [10](10-director-decision.md), [R1 평가 MD](evaluation-r1/rubric-evaluation.md)·[JSON](evaluation-r1/rubric-evaluation.json)은 역사 입력으로 보존한다. 기존 검토/게임을 재실행하지 않았다.

## 2. 신규 모델 최소 온보딩 블록 — 미래 실행 설계, 현재 미실행

### 2.1 고정 상대·배치·성공 범위

앵커는 Director가 고정한 11의 `wait-pass-v1`, `self-solve-v1`, `reciprocal-example-v1`만 사용한다. 정책 내용·가상 생성 비용은 11이 규범이며 이 문서에서 새 정책이나 비용 0을 만들지 않는다. scripted policy는 provider를 호출하지 않지만 게임 장부 비용은 11대로 적용한다. 앵커 하네스 자체는 미구현이며 그 결정론적 구현·관측 경계·소스 해시를 먼저 독립 검증해야 한다.

| 온보딩 항목 | 고정 설계 |
|---|---|
| 후보 / 상대 | 신규 후보 한 좌석, 나머지 세 좌석은 해당 세션의 동일 버전 scripted 앵커 |
| 앵커 종류 | 위 세 정책 각 하나. LLM 이름을 앵커로 대체하지 않음 |
| 좌석 균형 | 각 앵커에 대해 11의 네 좌석을 후보가 한 번씩 순환; 앵커 순서는 위 목록, 좌석 순서는 11 manifest 순서 |
| 세션 / 규칙 | 앵커 3 × 후보 위치 4 × 각 1세션 = **12세션**, 공개 지평 **12라운드**, TALK 최대 **4턴**, SOLVE 최대 **1회/라운드** |
| seed·퍼즐 | 12의 튜닝/온보딩 split에서 manifest 순서상 첫 적격 seed-block 하나를 선택, 같은 seed/deal을 앵커·좌석 조건에 대응 사용. holdout 사용 금지 |
| 게임 상한 | 11의 시작 20,000 / TALK 4,096 / SOLVE 16,384와 잔액에 의한 축소·정답 환급·upkeep/charge·PASS/EXIT 그대로 |
| 추가 호출 | 연결 probe·보정·인지 질문·형식 수리 호출 없음. 필요하면 Director의 별도 범위/예산 카드가 선행해야 함 |
| 운영 판정 | 실행 준비 시간, 유효 응답률, 지연, 실패 유형, 실제 시도·입력/출력·가격 근거·현금·로그 완결성만 판정 |

온보딩 통과의 사전 기준은 12세션의 운영 종료 기록 완비(참가자의 합법 EXIT/자원소진은 허용), 중복/누락 키 0, 누출 0, usage/청구 근거 또는 계약상 보수 상한의 전수 확인, 각 상한 이내, 실제 스케줄된 후보 호출의 유효 형식 비율 ≥0.95다. 분모 0이면 통과 불가. 유효 오답/PASS/EXIT는 형식 실패가 아니다. provider 오류/거부·파싱 실패·잘림은 유효 형식 분자에서 제외하고 별도 보고한다. 게임 성적 때문에 기준을 바꾸지 않는다. operational abort나 가격 미확인, 미완료 세션이 있으면 온보딩 보류/실패이지 순위 0점이나 게임 성공이 아니다.

이 블록은 연결·운영 준비용이며, 반복 하나를 안정된 성능·동기·협력 효과로 해석하지 않는다. 같은 게임의 좌석/턴을 독립 표본으로 늘리지 않는다. 본 검증·검출 목표·추가 표집은 12의 별도 계약을 따른다. 09의 공개 3라운드 smoke는 역사 제안이며 이번 12라운드 블록의 완료 증거가 아니다.

### 2.2 버전 변경과 부분 재비교

비교 코호트 식별에는 엔진/규칙·parser·adapter·실제 모델 revision·tokenizer·추론/temperature·입출력 상한·가격 정책·앵커 소스·seed/deal·좌석·로그/측정기 해시를 포함한다. 별칭만 같은 모델은 같은 코호트가 아니다. provider/relay/환경/시간 상한이 바뀌어도 영향을 받는 비교 블록은 무효화한다.

- 새 모델 추가: **새 모델의 위 12세션만** 계획한다. 기존 모델의 같은 manifest/앵커 버전 결과는 재사용하고 모든 모델 조합을 자동 재실행하지 않는다. same-model과 LLM cross-play는 별도 연구 카드이며 scripted 상대 온보딩으로 대체할 수 없다.
- 앵커 버전 갱신: 기존 코호트/결과는 동결한다. 새 정책 소스·게임 비용·관측 범위가 달라지면 앵커 버전을 올린다. 변경된 앵커 × 네 후보 좌석만 영향 블록이다. Director가 결과를 보기 전에 모델 manifest 순서상 첫 기존 적격 reference 모델과 신규 모델을 bridge 대상으로 고정하고, 변경 앵커의 구/신 버전을 대응 비교한다. reference가 없거나 승인/예산이 없으면 새 버전은 분리 보고하며 구/신 수치를 직접 합치지 않는다.
- bridge 대상 밖 모델은 자동 재평가하지 않는다. 해당 모델에 새 버전 비교가 필요할 때만 그 모델·앵커의 영향 블록을 별도 승인한다. bridge 결과가 한 모델에서 맞았다고 모든 모델의 버전 효과가 같다고 보정하지 않는다.
- seed/게임/측정기 변경은 그 영향 범위를 명시한 새 manifest로만 실행한다. 구 결과 삭제·덮어쓰기·사후 유리한 모델 선택·전 조합 회귀·자동 예산 증액은 금지한다.

## 3. adapter IO 계약 — 신규 설계, 현재 Reply와 다름

운영 adapter envelope 버전은 `e52-r2-adapter-v1`로 제안 고정한다. 아래는 **adapter 경계 필드**이지 12의 raw 필드 정의가 아니다. engineer가 12의 정식 필드에 명시 매핑하고 verifier가 필드 누락/분류를 확인해야 한다. 알 수 없는 수치는 null+이유로 남기고 0으로 채우지 않는다.

| 경계 | 필수 내용·처리 |
|---|---|
| 요청 | 공유 호출 키, 실제 모델/provider/relay/CLI revision, 허용 system/user 메시지, tokenizer/hash와 전체 입력 토큰 수, 입력/총출력 cap, 추론 설정, 120초 총 deadline, 재시도 0, 입력 SHA-256, 승인/예약 참조 |
| 격리 | fresh player session, 허용 관측만 전달. 운영 기억·이 문서·rubric·holdout seed/정답·다른 좌석 미수신 단서·프로필 스킬·파일명 평가 메타를 주입하지 않음. OS 프로필만으로 격리를 입증하지 않음 |
| 응답 | 변경하지 않은 공개 text, provider request ID 또는 명시적 미제공, 시작/끝 단조시계와 UTC, 종료/거부/오류/잘림 구분, stop reason, 요청/응답 모델 식별, usage provenance |
| usage | 총 입력, 비캐시/캐시 읽기/캐시 쓰기 청구 범주, **생각 포함 총 생성**과 제공 시 reasoning subset. subset을 총 생성에 다시 더하지 않음. 숨은 thinking 본문이나 비공개 chain-of-thought를 요구하지 않음 |
| 유효성 | 텍스트 파싱과 provider 성공을 별도 평가. 상한 도달/초과는 11의 무효·장부 규칙대로, 실패를 임의 답/PASS/EXIT로 만들어 적용하지 않음 |
| 거부 | 모델/provider 거부를 파싱 실패/유효 오답과 분리. 확인된 생성량과 11/12의 상태·장부만 적용, 청구 미확인 null 유지. 자동 수리/재호출 없음 |
| timeout/오류 | provider/SDK/CLI/relay의 자동 retry 전부 0임을 확인. deadline은 연결·스트림·자식 프로세스 전체를 포함. 원격 취소·종료·청구 대조가 확인되지 않으면 unknown-inflight로 동결 |

현재 정적 근거: `squid5/core/providers.py:32`의 Reply는 text/out_tokens/in_tokens/thinking/truncated만 있고, ProviderConfig의 기본 retries는 3, timeout은 300초다. `Provider.complete`는 내부 재시도를 수행한다. `squid5/core/protocol.py:272`의 ask에도 별도 형식 재시도가 있다. Anthropic SDK는 `max_retries=0`을 쓰지만 그것만으로 모든 경로의 0회 재시도를 보장하지 못한다. 따라서 **기존 default를 그대로 실행하면 이 계약에 부합하지 않는다**. CLI/relay 내부 시도·생각 포함 usage·입력 cap/실제 원격 취소는 이번 help로 검증되지 않았다.

## 4. 고정 운영 상한 — 제안 cap과 현재 승인액 분리

아래는 후속 온보딩의 사전 설계 상한이며 현재 유료 실행 승인이 아니다. 더 낮은 명시 승인/모델 용량/남은 잔액은 적용하되, 비교 조건이 달라지면 해당 코호트를 분리한다. 낮은 context 용량의 모델에만 몰래 입력을 자르거나 상한을 늘리지 않는다.

| 항목 | 고정 cap / 집행 |
|---|---|
| 입력 | **32,768 토큰/요청**, system/user/이력·도구/CLI 주입 포함 실제 전체 payload. 정확 tokenizer 또는 보수적인 provider 보증 상한이 없으면 호출 0. 초과는 사전 중단, 무음 절삭 없음 |
| 생성 | TALK **4,096**, SOLVE **16,384**, 생각 포함 총 생성. 실제 요청 cap은 `min(해당 cap,양수 잔액)`; native enforcement/계측 확인 없으면 호출 0 |
| 재시도 | 외부·provider·SDK·CLI·relay·형식 수리 모두 **0**, slot당 총 시도 **1**, `attempt_id=0` |
| 총 시도 | 후보 **720/블록**, **60/세션**; 실제 DONE/EXIT/소진으로 줄어든 호출만 기록. 예약하지 않은 probe 포함 금지 |
| 동시성 | 세션 workers **1**, 유료 provider inflight **1**(전체·provider·모델 모두). 이 온보딩은 유료 후보가 한 좌석뿐이다. 같은 TALK 턴/SOLVE 배치는 네 좌석 모두 동일 시작 스냅샷 사용, 응답 적용은 배치 완료 뒤 11 순서대로; full LLM cross-play를 직렬 상태 갱신으로 바꾸지 않음 |
| 시간 | 요청 **120초**, 세션 **900초**, 블록 **3,600초**; 준비 작업 별도 **900초**. 재개는 누적 사용 시간을 이어받고 새 시간 예산을 만들지 않음 |
| 현금 | 미래 제안 세션 **USD 2.00**, 후보 온보딩 전체 **USD 20.00**. provider+relay+추가 구독 청구 등 증가분 포함. 별도 모델은 같은 cap, 자동 합산 승인 없음 |
| 현재 승인 | 게임/API **USD 0.00**, 따라서 `B_effective=min(20.00,B_explicit_approved)=0.00`, **게임/API 호출 0** |

슬롯 검산(모두 상한, 실제 모델 결과 아님): 세션 `S=3×4=12`; 후보 호출 `S×12×(4+1)=720`(TALK 576, SOLVE 144); 전체 논리 슬롯 `S×4×12×5=2,880`, 이 중 scripted 슬롯 2,160은 유료 provider 호출이 아니다. 후보 입력 최대 `720×32768=23,592,960`, 총 생성 최대 `576×4096+144×16384=4,718,592`. 한 세션은 입력 최대 1,966,080·생성 최대 393,216이다. 게임 소진/환급과 DONE에 따라 실사용은 달라진다.

720회가 각각 120초 걸리면 직렬 86,400초다. **3,600초 cap이 더 먼저 적용될 수 있으므로 블록 완수를 보장하지 않는다.** 시간/현금/시도 중 최초 한도에서 신규 dispatch를 중단하고 inflight를 종료·대조한 뒤 미완료 블록으로 보존한다. 결과를 보고 같은 모델만 재시작하거나 cap을 늘리지 않는다. 유료 실행 전 manifest의 최악 청구 예약이 승인액을 넘으면 시작하지 않는다.

### 4.1 가격·예약·청구의 fail-closed 규칙

가격은 이번에 조회/추정하지 않았다. 06의 가격 미확인을 새 확인으로 바꾸지 않는다. 후속 실행 manifest는 **정확 모델/provider/relay·유효 시각/만료·통화·청구 단위·공식 근거 해시·입력/캐시/생각 포함 출력/별도 reasoning 청구 여부·요청/오류 고정료·구독 증가분 상한**을 담아야 한다. 구독 로그인을 종량 현금 0의 증거로 쓰지 않는다. 가격/계량/증가분의 유효 보수 상한을 확인할 수 없으면 호출 0, 비용 NA, 저렴함 미검증이다.

금액 계산은 부동소수점 대신 Decimal 또는 최소 화폐단위 정수를 사용한다. provider별 usage→청구 매핑을 고정하고, 서로 겹치는 입력/캐시 또는 output/reasoning을 중복 합산하지 않는다. 범주가 겹치면 invoice의 실제 청구 규칙으로 분리하고 원시 usage는 보존한다.

dispatch 전 안전 예약의 한 예는 `U_j=Imax×(p_uncached+p_cache_read+p_cache_write)/d + Omax×(p_output+p_reasoning_separate)/d + f_provider_max+f_relay_max+f_subscription_increment_max`다. 각 입력 청구 범주의 최대가 Imax 이하이고 각 생성 범주의 최대가 Omax 이하라는 provider 계약이 선행 조건이다. reasoning이 output에 이미 포함되면 별도 p는 0. 이는 캐시 혜택을 가정하지 않는 보수 상한이지 실제 가격/청구 추정치가 아니다. provider가 위 범위를 보장하지 못하면 수식을 적용하지 않고 호출을 차단한다.

전 블록 예약은 예정 후보 요청별 U_j의 합과 별도 공유 증가분 상한을 포함한다. `청구확정액+미확정예약액+신규예약액 ≤ min(제안cap,명시승인액)`를 블록·세션 모두에서 원자적으로 검사한다. 동시에 세션 cap도 넘으면 시작하지 않는다. 송신 후 오류/timeout도 예약을 유지한다. 완전 청구 근거 또는 provider의 확정된 최대 청구 증거로만 정산·해제한다. 실제 청구가 예약 상한을 넘으면 즉시 전체 dispatch 중단·상한 실패 사건 보존, 청구 대조 전 재개 금지다.

장부는 세 개를 분리한다: (a) 11의 게임 토큰 차감/환급/이전·명목 보상, (b) usage 기반 provider/relay 실제 현금 및 미확정 예약, (c) 구독 기존 고정비/연구용 배분액. 배분액을 실제 증가 청구액처럼 더하지 않고 게임 환급으로 현금 예약을 환급하지 않는다. 청구서의 키/계정정보는 비공개 운영 저장소에만 두며 문서·raw 공개 후보에 포함하지 않는다.

## 5. 설치·실행·재개·리플레이·재계산 인터페이스

### 5.1 현재 확인된 명령과 명확한 한계

`pyproject.toml`은 Python ≥3.12, squid5 0.5.0, httpx/anthropic/PyYAML/numpy/matplotlib 및 dev pytest를 선언한다. 기존 프로젝트 `.venv/bin/python`으로 **help만** 실제 실행했다. 실제 interpreter는 Python 3.12.10, httpx 0.28.1, anthropic 0.84.0, PyYAML 6.0.3, numpy 2.2.6, matplotlib 3.10.8, pytest 9.0.2다. 시스템 Python 3.14.5에는 httpx/anthropic/matplotlib가 없으므로 같은 환경이라고 주장하지 않는다. 신규 설치/게임/서버/export/report 실행은 하지 않았다.

| 현재 명령 | 실제 확인 / 사용 경계 |
|---|---|
| `python -m squid5 --help` | exit 0, run/calibrate/report/probe 존재 |
| `python -m squid5 run --help` | exit 0, config/--resume/--reps/--dry-run 존재. `run <config>`는 유료 호출 가능, 이번에 금지 |
| `python -m squid5 report --help` | exit 0, runs/--out/--calibration 존재. 기존 분석 경로이며 **e52-r2-metrics-v1 재계산으로 사용 불가** |
| `python tools/monitor/serve.py --help` | exit 0, --root/--port/--host 존재. 운영 디버그 서버는 플레이어 UI나 비밀 제거를 보장하지 않음 |
| `python tools/monitor/export.py --help` | exit 0, run_dir/--session/--out/--no-assets 존재. `--no-assets`는 아트 제거이며 정답·비밀·이력 제거 옵션이 아님 |

설치의 현재 manifest 기반 후보는 선택한 Python≥3.12로 `python -m venv .venv`, 그 환경에서 `python -m pip install -e '.[dev]'`이다. **명령 미실행·새 환경 설치 미검증**이며 후속 engineer 카드에서 lock/해시를 고정하고 새 격리 환경 설치를 검증한다. manifest의 console entry는 `squid5.runner:main`을 가리키지만 현재 `squid5/runner.py`는 없다. 확인된 경로는 `python -m squid5`다. console entry 수리는 이번 소유 범위 밖으로 Director→arena-engineer에 인계한다.

현재 `squid5/core/runner.py`의 `--resume`는 results.jsonl에 완료 key가 없는 unit을 처음부터 재실행하고 config/meta를 다시 쓴다. 중간에 원격 호출이 성공했어도 result가 없으면 비용/이벤트 중복이 가능하다. **이 명령을 R2 안전 재개의 증거로 쓰지 않는다.** 현재 monitor는 seed로 퍼즐·정답/전체 비밀을 재구성할 수 있으므로 holdout/player/public 대상으로 그대로 제공하지 않는다.

### 5.2 R2 신규 논리 인터페이스 — 호출 가능한 CLI/API 없음

다음은 engineer가 구현할 요청/응답 계약이지 존재하는 모듈/명령이 아니다. 코드가 없는 것을 실행했다고 주장하지 않는다. 모든 입력 파일은 실제 존재/해시 검증 후 사용하며, 경로는 승인된 workspace 또는 별도 승인 run storage 안으로 제한한다.

| 작업 | 입력 / 출력 / 실패·불변 조건 |
|---|---|
| prepare | 세 파일 해시·run manifest·가격/승인·split·adapter/anchor provenance → 검증된 계획, 호출/시간/예약 상한표. 누락/미구현/승인0이면 not-runnable, provider 호출 없음 |
| start | prepare 계획 hash·고유 work key·승인 참조 → 잠금 확보, 예약/dispatch journal, 12의 raw log. 중복 key면 기존 run 상태만 반환, 두 번째 실행 금지 |
| resume | 기존 manifest/계획 hash·journal·체크포인트·청구 대조 → 미송신 slot만 이어 실행. hash 변경/unknown-inflight/잔여 승인0이면 거부. 모델 응답을 새로 생성해 과거 checkpoint를 메우지 않음 |
| replay | 동결 raw+manifest·규칙/anchor/parser hash → 같은 순서의 상태/장부 재현. **provider 호출 0**. 기록된 응답만 사용; 구버전/누락/충돌은 명시 실패 |
| recompute | raw hash·12 schema·e52-r2-metrics-v1 hash·split → 파생 지표와 NA/실패·입력/출력 hash. **provider 호출 0**. 12의 허용 오차/픽스처 검사, 다른 버전 무음 대체 없음 |
| export-candidate | 독립 검증된 lineage·허용 목록·redaction/split/권리 검토 → 비공개 공개 후보+검사 보고. 배포/게시 동작 없음, holdout raw 기본 제외 |

## 6. 환경·실행 manifest와 중복 방지

운영 manifest는 신규 `e52-r2-ops-manifest-v1`의 JSON 객체로 고정한다. 아래 이름은 운영 namespace이며 12의 event schema와 별개다. 필수 메타가 없으면 prepare 실패다. 금액은 USD 십진 문자열, 시간/토큰/시도는 음이 아닌 정수, SHA-256은 파일의 실제 바이트에 대해 산출한다. 관측되지 않은 actual 값을 가짜로 채우지 않는다.

| 필수 그룹 | 내용 |
|---|---|
| identity | board/task/run/work_key, 실제 author profile/session/model/effort, engine commit+dirty diff hash, 세 설계·rubric·config의 상대 경로/hash |
| environment | OS/arch, Python executable/version, 패키지 lock 및 resolved distribution hash/version, CLI/provider SDK/relay/container digest, locale/timezone, worker/storage 경로. credential 값/개인 계정/secret URL 제외 |
| experiment | rule/parser/adapter/anchor/tokenizer version/hash, log/metrics 버전, 12 seed/deal/split manifest hash와 목적, 후보/좌석/상대·추론/temperature·허용 입력의 hash |
| caps | §4 입력/생성/시도/동시성/시간/현금 제안과 effective 승인, 정해진 session 배치·call plan, 가격/최대청구·정산 정책 hash |
| authorization | 승인 ID/범위/통화/금액·만료·담당, 배포 false·학습 false·추가표집 false. 이번은 게임/API 승인0 |
| lineage | artifact별 상대 경로/bytes hash/schema/split/보유권한, 부모 artifact hash, transform version+코드 hash+옵션·실행 상태, 변경 이유·이전 manifest hash |

work_key는 canonical plan의 SHA-256으로 생성한다. canonical JSON은 UTF-8, sort_keys=true, ensure_ascii=false, separators=(',',':'); plan은 engine/rule/adapter/model/anchor/settings/caps/split/seed-block/좌석과 승인 revision을 포함한다. 별도 재실행 revision을 만들더라도 기존 미확정 호출/예약을 피하려고 식별자만 바꿀 수 없다. 시크릿 값은 plan에 넣지 않는다. 내부 seed는 private manifest에만, public lineage에는 비밀 없는 split commitment를 사용한다.

동일 work_key에는 운영 잠금 하나만 허용한다. native Kanban의 고유 카드/의존성/모델/runtime과 실행 journal을 연결하고 Comments/Runs/Worker log에 시작·진전·중단·인계가 보이게 한다. 이번 카드가 다른 Bot Chat을 덮어쓰거나 새 gateway를 띄우지 않는다. 자동 정기 실행·학습·가격 유료 probe를 붙이지 않는다.

## 7. 장애·중단·복구·청구 대조

dispatch journal은 raw event와 별도 운영 artifact다. 각 공유 호출 키/입력 hash에 대해 **예약→송신 전 durable 기록→송신→응답 durable 저장→12 raw 반영→체크포인트** 순서와 provider request ID·예약 상태를 보존한다. 송신 직전 crash는 실제 송신 여부를 증명할 수 없으므로 unknown-inflight로 취급한다. 네트워크 exactly-once를 일반적으로 보장한다고 주장하지 않는다.

| 장애 | 중단 / 복구 / 중복 방지 |
|---|---|
| 입력 초과·가격/usage 상한 미확인·승인0 | dispatch 전 차단, 호출/청구 예약 해제 여부 근거 보존. 입력 무음 축소/대체 provider 없음 |
| provider 오류/timeout·원격 종료 미확인 | 동일 key 자동 retry 없음, inflight 예약 유지·세션/블록 중단. request ID/status/청구 근거 대조 전 재개 불가 |
| 파싱 실패·잘림·유효 오답·PASS/EXIT | 11/12가 정한 서로 다른 상태/게임 장부로만 처리. 임의 정상 답 생성·형식 수리 호출 없음. 운영 실패와 행동 결과 혼합 금지 |
| usage 누락 또는 실제 청구 상한 초과 | raw 증거 보존·신규 dispatch 중단. 보수 예약으로 hold하되 실제 비용 NA, 대조 후만 복구. 게임 토큰을 청구값으로 대체하지 않음 |
| 프로세스 crash / 응답 저장 직후 crash | 저장된 동일 응답은 offline 재적용·체크포인트 정합 확인, provider 재호출 없음. 응답 미확인 slot은 unknown-inflight 동결 |
| raw 마지막 줄 손상·중복·순서 충돌 | 원본 불변 보존, 복구 view를 별도 hash/lineage로 생성. 동일 key+동일 응답 hash 중복은 참조로만 제거, 다른 내용이면 중단·verifier 판정 |
| 잠금 충돌 | 두 번째 worker는 start 거부. PID만으로 죽었다고 판단하지 않고 heartbeat/worker/journal과 원격 inflight를 확인 |
| 코드·모델·앵커·config·schema mismatch | 재개 거부·새 코호트. 이전 raw 자동 변환/완료값 복제 금지 |
| 시간·현금·시도 cap | 신규 dispatch 중단, inflight 취소/대조·잔여 예약 반영. 미완료 계획과 실패를 보존, 성공 생존/무조건 비정보성 검열로 치환하지 않음 |
| 정답/holdout/운영 메모리 누출 | 실행/후속 공개 동결, 노출 artifact의 lineage와 영향 block 표시. 오염된 holdout은 평가에서 폐기/버전변경하되 기록 삭제·모델 유리한 사후 선별 금지 |

unknown-inflight가 해소돼도 자동 재호출하지 않는다. 미송신이 확정된 slot만 남은 동일 cap/승인 아래 재개할 수 있다. 실제 재실행이 필요하면 Director가 별도 retry 범위·새 attempt/revision·남은 예산을 사전 고정한 뒤 새 비교 블록으로 계획한다. 이번 q0 manifest 안에 `attempt_id=1`을 조용히 넣지 않는다.

## 8. 원시→파생 계보·보류 자료·이용 범위

### 8.1 schema와 변환 경로

raw schema는 **12의 e52-r2-log-v1 필수/nullable/event enum·공유 키가 유일한 규범 원본**이다. 이 문서는 call/round/exchange 필드의 다른 이름·타입·enum을 만들지 않는다. adapter→raw 매핑도 12를 따른다. 운영 envelope/manifest/journal은 raw와 공유 키/hash로 연결하되 플레이 입력에 넣지 않는다.

고정 계보는 `private provider evidence + dispatch journal → immutable raw + run manifest → validated canonical view → e52-r2-metrics-v1 derived → redacted release candidate + release manifest`다. canonical view는 원본을 수정하지 않으며 중복 제거/복구/구버전 migration의 결정과 양쪽 hash를 남긴다. 파생 지표는 입력 raw/manifest·12 문서·측정 코드·옵션·split·분모/NA·허용 오차 검사 보고를 참조한다. 원본을 되찾을 수 없는 집계값으로 raw 검증을 대신하지 않는다.

| 자료층 | 저장/이용 계약 |
|---|---|
| private operator evidence | 원격 request/청구 근거·가격·승인/잠금. operator/verifier만 접근, 플레이어/학습/public 금지; 자격증명 값 자체는 수집하지 않음 |
| private raw/replay bundle | 12 raw·허용 플레이 입력/공개 응답·동결 seed/deal/정답·버전·실패 궤적. 승인된 분석/독립 재현만, holdout 접근은 제한 |
| derived metrics | raw/hash/version/split과 분자·분모·NA/운영중단을 함께 유지. 능력/존속/협력 별도, 실패·미완료를 숨긴 순위 생성 금지 |
| training candidate | 12의 train/tuning 허용 split만 lineage로 선택. 현재 Phase 2 미활성·학습 실행 금지, 실패/회복 포함 여부와 선택 규칙은 차후 curator 승인 |
| public candidate | 권리/동의 확인된 aggregate와 개발용 비holdout 예시를 허용 목록으로만 export. private raw·seed/정답/비공개 thinking·운영 메모리/가격 계정 근거 제외 |

### 8.2 seed/퍼즐·훈련/평가 분리와 비밀 제거

split membership·seed 범위·퍼즐 fingerprint와 중복 기준은 12에만 정의한다. 13은 prepare 시 그 고정 manifest의 해시/멤버십을 검증하고 온보딩/튜닝이 holdout을 읽지 못하도록 경로·파일권한·하네스 관측을 검사한다. 같은 퍼즐의 이름/좌석/seed를 바꿔 train/eval 양쪽에 넣지 않는다. 판정/튜닝에 사용한 퍼즐은 holdout으로 복귀시키지 않는다.

보류 평가의 seed·정답·규칙·전체 단서·재구성 가능한 설정/프롬프트·진단 질문은 public 및 training candidate에서 제외한다. holdout에서 생성된 응답 궤적도 정답/단서를 복원할 수 있으므로 aggregate 공개 외에는 기본 금지다. 비공개 평가자에게 재현 bundle을 제공할 때만 목적/권한을 별도 기록한다. 공개용 설명 예시는 holdout과 독립인 개발 split에서 만들고 11/12의 동결 평가를 대체하지 않는다.

redaction은 허용 필드 목록 기반이며 credential/token/auth header/cookie·개인 계정/경로·비밀 포함 URL·원시 에러/CLI stderr·운영 프롬프트·비공개 thinking·다른 좌석 미수신 비밀을 검사한다. whitelist 통과를 완전한 의미적 비밀 제거 증명으로 쓰지 않고 verifier가 샘플뿐 아니라 **전체 공개 후보**의 메타/본문·HTML embedded JSON·replay 복원 경로를 점검한다. candidate에서 원시 hash로 개인/비밀 값을 역검색할 수 있는지도 검사한다. 삭제·가명화 변환은 새 artifact hash와 private redaction map을 갖고 원본은 보존한다.

데이터 이용은 목적 제한이다. 내부 연구 분석·재현, 향후 승인된 training candidate, 승인 후 공개 aggregate를 구분한다. provider/relay 산출물 재배포·학습 허용 및 인간 동의는 아직 확인되지 않았다. 확인 전 export/public/training 이용 불가. 아트는 `--no-assets` 경로를 기본으로 하고 제3자 아트 권리를 별도 확인한다. 코드/데이터 라이선스는 실제 파일/권리 근거를 확인하기 전 임의로 선언하지 않는다.

## 9. 릴리스 체크리스트·담당·후속 게이트

전 항목은 **후속 실행 수용 조건**이며 이번에는 E=U다. 체크 표시·파일 존재만으로 통과하지 않는다. `release-ready`와 실제 `published` 상태를 분리하고, 공개 순위 갱신/배포는 사용자 승인 없이는 수행하지 않는다.

| 단계 / 수용 근거 | 실행 담당 → 독립 확인 |
|---|---|
| 세 최종 문서 hash 바인딩·G01–G11 D=2/Critical0 및 고정 checker exit0 | arena-verifier `t_be851c27` → arena-director `t_6ed7c54b`; **DESIGN_ACCEPTED** |
| 신규 adapter/manifest/상한·journal·checkpoint 구현, raw→metrics 버전 매핑, 장부/parser/anchor 회귀·대표 E2E | arena-engineer → arena-verifier; **IMPLEMENTATION_VERIFIED**(G07/G09 E=2 포함) |
| 새 격리 환경 설치·console entry 수정, read-only replay/재계산의 입력 hash·결과/허용 오차 일치 | arena-engineer/metric-analyst → arena-verifier; 재현 report 실제 실행 |
| 가격·모델 revision/tokenizer/usage·내부retry0·원격 취소·현금 예약 fail-closed와 crash/unknown-inflight 복구 검증 | arena-operator/arena-engineer → arena-verifier; 승인0/가격미확인에서 실제 outbound 호출0 fixture |
| 승인된 신규 모델 한 개의 12세션 설정시간·유효률·p50/p95/최대 지연·시도/실패/현금 및 미확정청구 보고 | arena-operator → metric-analyst/arena-verifier; 비용 NA면 저렴함 주장 불가, **G10 E** |
| 11의 인간 플레이, 12의 측정·holdout/비교·인지와 실제 렌더 누출 확인 | game-designer/metric-analyst/beta-tester/construct-auditor → arena-verifier; **ARENA_VALIDATED** |
| 전체 공개 후보의 whitelist·비밀·split/lineage·이용권리/동의·아트 검사와 G11 새 환경 실행/복구 | arena-operator/arena-engineer → arena-verifier; **G11 E / RELEASE_READY** |
| 최종 bundle hash·schema/변경 이력·private 재현 위치·공개 이용범위·rollback 버전 동결, 게시 범위 승인 | arena-director + 사용자; 준비 통과와 실제 배포 승인 별개 |

실제 배포가 나중에 승인되면 게시한 정확 artifact hash를 읽어 검증하고, 문제 시 해당 릴리스를 철회/이전 검증 bundle로 되돌리는 계획을 릴리스 카드에 고정한다. 이번에는 배포·모집·학습·정기 실행·commit/push를 시작하지 않는다. Phase 2 curator/scientist 활성화는 별도 승인 대상이다. 새 후속 카드 생성은 Director가 담당한다.

## 10. 이번 도구 근거·미검증·인계

관찰: 카드·부모 R1/후속 독립 평가 의존성과 댓글을 실제 읽었다. 지정 worktree의 AGENTS/CLAUDE·README·상황인지·rubric, 06/09/10/R1 MD/JSON과 관련 manifest/소스를 열람했다. 실제 Git HEAD/상태를 확인했으며 **기존 수정/미추적 파일이 있는 dirty worktree**다. 다른 worker의 문서·기존 outputs/LFS·paper·profiles를 수정하지 않았다.

실제 식별 근거: `HERMES_SESSION_ID`의 정확 값으로 operator `state.db`를 SQLite `mode=ro` 조회해 source=kanban/title=현재 카드/profile_name=arena-operator/model=gpt-6.1-sol/model_config.reasoning_config.effort=max를 확인했다. Kanban run16/profile/model 요청도 읽어 대조했다. high 실행으로 가장하지 않는다.

검산 근거: Python 표준 라이브러리로 §4의 12/720/2,880/2,160·입출력 총량·86,400초·min(20,0)=0을 계산했다. SHA-256으로 rubric 고정값과 snapshot.baseline_hashes의 열거 **69개**가 불일치/누락 **0**임을 확인했다. 06/09/10/R1의 작성 전 해시는 아래대로 보존한다. 최종 파일 hash/링크·키·상한·보호 파일 재검산 결과는 이 카드의 completion metadata에 기록해 독립 평가자가 재계산한다. 자기 파일 안에 자기 최종 hash를 적는 순환은 만들지 않는다.

| 보호 입력 | SHA-256 |
|---|---|
| 06-arena-operator.md | `ac60e2c6ae9939ba9b4504970ca62429ba3d83fe20d27dac8322dfa79398764c` |
| 09-design-final.md | `c313f632f05cabf500ce3ce7d1334afd2f441aed664cf6d4d29830df4815fa21` |
| 10-director-decision.md | `ba9a53ccd961f2986f5ae5b2b3d83f74cab9346722607c5478df55eaa54399fb` |
| evaluation-r1/rubric-evaluation.md | `2a0b461cc92d43abe8cfa464b0ed63613c8bc51529ea36aeab99a224b9f94396` |
| evaluation-r1/rubric-evaluation.json | `beb9e0f5854f5e4c6082783e9adc8fee7dca4c9ced7fe3792140b78f575bb437` |

help 검증의 실제 명령은 기존 프로젝트 `.venv/bin/python`에 `PYTHONDONTWRITEBYTECODE=1`을 적용해 §5.1의 다섯 `--help`를 호출한 것이다. 각 exit0. 설치/모델 응답/엔진 회귀/새 환경·안전 재개/리플레이/재계산/비밀 제거/권리/실제 비용은 검증하지 않았다. 문서 산식이나 help 성공은 게임/API 실행 성공을 뜻하지 않는다.

해석: R1의 미고정 운영 수치·앵커/부분 재비교·복구/계보 경계를 문서상 구체화했다. cap은 감당 가능성에 대한 **운영 제안**이지 실제 모델이 저렴하거나 기한 안에 완료된다는 실증이 아니다. 토크나이저·CLI 주입·provider 지연/청구·scripted 상대의 현실성 차이가 비교를 제한할 수 있다. 시간/가격/허용량 때문에 블록이 미완료되면 그 사실과 NA를 그대로 보고한다.

인계: 이 문서의 자기 확인을 최종 독립 PASS로 쓰지 않는다. `t_be851c27`이 **11/12/13 변경후 최종 세트**를 판정하고, Director가 고정 checker와 실제 hash로 프로젝트 게이트를 확인한다. 구현·유료 실행·권리/사용자 승인 없는 공개를 완료로 주장하지 않는다. G10/G11 실행 E=U, 다른 G-ID 최종 점수는 독립 평가 책임이며 G12 후속 미착수를 보존한다.

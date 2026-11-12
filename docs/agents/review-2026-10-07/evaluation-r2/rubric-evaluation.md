# Rubric 평가 — t_be851c27 / R2 / run 27

## 1. 결론

판정: REVISE — DESIGN_ACCEPTED 미충족. 미해결 Critical은 없으나 G05/G07/G08/G10의 D=1이 남는다. 다른 G01–G11 행은 D=2, G12는 후속 Phase 2 미착수로 D=N/A, 모든 E=U다. 개별 평가 카드 완료는 프로젝트 성공이 아니다.

R1 C1(무해결 DONE/PASS 최대 보상)은 새 보상식으로 설계상 해소됐다. 남은 문제는 문서 미존재가 아니라 최종 세 문서 사이의 구체 계약 공백이다. 실게임/모델/API/사람 테스트나 엔진 수정은 하지 않았다.

## 2. 범위·실제 식별·해시

- 보드/카드: llm-squid-game / t_be851c27, run 27. 부모 t_3d8b1c6f, t_c8db5da8, t_9fd24b59 모두 done을 native kanban_show로 확인. 자식 없음.
- workspace: /Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.claude/worktree/2026-10-07
- 실제 branch/HEAD: review/e52-2026-10-07 / d39db2b848effdfbd08f05be21c56a72abbcf774. 기존 dirty/untracked 상태를 보존했다.
- rubric v1.0 SHA-256: 4069c7e8d3ffffc0c7c81058c30be740575d1cb9b8933baf3311e59714043579
- 목표: G01–G11 D 모두 2, Critical 0 및 변경 후 최종 독립 평가. 합계/평균으로 대체하지 않음.
- 주 작성자: game-designer / gpt-6.1-sol / 실제 effort max(요청 high), session 20261007_234433_da6600, run19. 실패 종료 후 운영자 복구 인계(run25)를 문서 작성 성공 run으로 바꾸지 않는다.
- 12 작성자: default / gpt-6-astra / effort high, session 20261007_185005_9bf899, Codex 01a115cd-aa28-7612-bbe9-038f0e2fd3d2. metric-analyst run15/18/20의 성공 산출물로 가장하지 않는다.
- 13 작성자: arena-operator / gpt-6.1-sol / 실제 effort max(요청 high), session 20261007_232224_2aaf84, run16.
- 독립 reviewer: arena-verifier / gpt-6-astra / openai-codex / 실제 effort high(요청과 일치), session 20261008_091640_d6ce38, Codex 01a118de-935d-7043-91f6-5e8be4b2ccad.
- provenance: 각 프로필 state.db를 SQLite mode=ro로 열어 정확 session의 source/title/profile_name/model/model_config.reasoning_config를 확인하고 환경 HERMES_SESSION_ID, 현재/부모 Kanban run 및 14-recovery-handoff.json을 대조했다. 비밀·system_prompt는 읽거나 기록하지 않았다.
- 카드 예산: 900초/재시도 상한1 요청. 별도 worker 생성·예산 변경 없음. 현 게임/API 승인0, 호출0. 운영 검토이며 블라인드 플레이가 아님.
- 소유 출력: evaluation-r2/rubric-evaluation.md와 rubric-evaluation.json만. 최종11/12/13·R1·root STATUS·rubric/checker·엔진·프로필은 변경하지 않음.
- 최초 일반 git status는 LFS clean filter의 .git/lfs/tmp 쓰기 권한 문제로 실패했다. 읽기 전용 상태 확인에 필터를 명령 단위로 끈 git -c filter.lfs.process= -c filter.lfs.required=false status --short를 사용했다. Git 설정/파일/인덱스를 수정하지 않았다.
- 검산 시각: 2026-10-08T00:19:38.528143+00:00 (도구 조회).

| 최종 규범 파일 | SHA-256 |
|---|---|
| docs/agents/review-2026-10-07/11-design-revision-r2.md | 545d96cfe2096176bc7cb06c1d1ade0489e8587d3024e18658811ae21299badd |
| docs/agents/review-2026-10-07/12-measurement-contract-r2.md | adef1489cc932de78b5ee5ae415051485e93f31c94ffc8d5ad5dc2d0f62134cb |
| docs/agents/review-2026-10-07/13-operations-contract-r2.md | d387ef9bc423899ede32719f8ab17bd02aefb657d3f75303ee7482d08b3bb80b |

해시는 recovery handoff와 일치한다. 필수 D 근거는 위 세 파일만 사용하며 과거 09/10·R1은 변경 이력에만 사용했다. 기존 root rubric-evaluation은 덮어쓰지 않았다.

## 3. G01–G12 독립 성적표

| ID | D | E | 최종 근거 | 관찰·해석·미검증 |
|---|---|---|---|---|
| G01 | 2 | U | 11-design-revision-r2.md §2.3–§3.4 L55–143 | s0 보상0, U/X/F/S/L/P와 정책 비교·제공자 이익이 고정돼 R1 C1은 설계상 해소. 무조건 선물 상대의 동률/의미 전달 편법은 한계로 남으며 실제 성능·전역 지배성은 미검증. |
| G02 | 2 | U | 12-measurement-contract-r2.md §2 L11–49; §6.3 L160–170 | self/other×H 네 셀·PROTECT 비용·Y·controller 전이·교란 표와 제한된 주장 범위 고정. 서술만 구현하면 narrative_only이며 의식/내재적 동기 증거가 아니다. |
| G03 | 2 | U | 11-design-revision-r2.md §4 L145–194; 12-measurement-contract-r2.md §6.1 L140–146 | 충분자원 reset·총생성 cap·FULL/PUBLIC+SELF·난이도/불확정 분리·개발 선정 문턱이 고정. 실제 퍼즐 후보 계산·모델 능력은 미검증. |
| G04 | 2 | U | 12-measurement-contract-r2.md §3 L51–73; §5 L119–125; 11-design-revision-r2.md §2.2–§2.3 L38–71 | 방향쌍 기회·L 하한/C 보장·무상/유상/교환·제공자 호출비용/호혜·공식/비공식 NA를 구분. 정확한 cap 경계는 11의 엄격한 유효성 조건을 함께 적용해야 한다. raw 상태 완결성은 G07에서 별도 미충족. |
| G05 | 1 | U | 11-design-revision-r2.md §5 L196–264; 13-operations-contract-r2.md §3–§4 L54–99 | 사람 경로·리플레이·튜토리얼·질문/문턱은 충족하나 인간 제출의 과금 규범을 13에 위임한 참조가 비어 있다. R2-W05 해소 필요. |
| G06 | 2 | U | 12-measurement-contract-r2.md §4 L75–92; §6.2–§6.3 L148–170; 13-operations-contract-r2.md §3 L60; §8.2 L184–192 | N/E/S fresh session, 첫 행동/궤적 구분·행동뒤 질문·좌석/순서 주기·누출/오염/실패 중단 고정. 실제 문구 대칭·렌더 누출·인지 효과는 미검증. |
| G07 | 1 | U | 12-measurement-contract-r2.md §5 L94–136; 11-design-revision-r2.md §2.2 L46–51; §5.1 L208 | 지표·분자/분모·원시 키·버전·NA·허용오차는 구체화됐다. offer 상태/전이와 중복 판정키의 계약이 11과 완결되지 않아 동일 기록 재계산을 유일하게 정하지 못한다. |
| G08 | 1 | U | 12-measurement-contract-r2.md §6 L138–170; 11-design-revision-r2.md §3.1–§3.2 L82–112; 13-operations-contract-r2.md §2 L24–52 | seed split/동형검사·군집단위·세 대비/n/보수구간·중단은 고정되고 산식 일치. scripted 고정 상대의 일반 비용 함수가 없어 비교 상태 재현의 마지막 결정이 남는다. |
| G09 | 2 | U | 11-design-revision-r2.md §2 L26–78; 13-operations-contract-r2.md §3 L54–68; §7 L149–166 | 장부/환급·동시수락 순서·중복 실행금지·소진후 호출/부활금지·EXIT·timeout·명령경계가 새 보상과 일관됨. raw 상태 매핑 문제는 G07로 분리하며 실제 엔진 회귀 통과가 아니다. |
| G10 | 1 | U | 13-operations-contract-r2.md §2–§4 L24–99; 11-design-revision-r2.md §3.1 L82–98 | adapter·12세션·3앵커·부분 bridge·입출력/시도/동시성/시간/현금 cap·승인0 차단은 고정. 비용 함수가 없는 scripted 앵커를 11에 위임한 공백이 최소 블록의 재현을 막는다. |
| G11 | 2 | U | 13-operations-contract-r2.md §5–§9 L101–209; 12-measurement-contract-r2.md §6.1 L140–146 | 현재 명령과 미구현 인터페이스를 구분하고 manifest·journal·안전재개·계보/holdout·권리/비밀제거·릴리스 담당/체크리스트를 설계. 실행/재생에 쓰는 schema 결함은 G07에서 별도 수정 필요. 공개 준비/배포는 미검증. |
| G12 | N/A | U | 11-design-revision-r2.md §6 L277; 13-operations-contract-r2.md §9 L209 | Phase 2 후속 미착수로 사전 범위 밖. 학습/일반화 검증은 승인되지 않았으며 목표를 삭제하거나 통과시킨 것이 아니다. |

G09의 D=2는 새 보상과 장부/명령 경계를 다시 읽은 설계 판정이다. 단순히 R1 점수를 복사하지 않았다. 실제 장부 보존·중복/탈락후 호출·정보 경계 회귀는 E=U다. G07의 기록 계약 미완결을 G09 실제 통과로 덮지 않는다.

## 4. 미충족별 반례·수용 기준·담당

### R2-W07 — G07 — 거래 상태 전이와 이벤트 중복 키 계약 미완결

- 관찰: 11은 철회(withdrawn)와 수락 후 실행 무효(void)를 구별하지만 12의 유일 규범 offer state enum에는 둘 다 없다. offer 엔티티 키와 상태변경 이벤트 키의 구분도 없다.
- 재현/검사 사례: T1 offered→T2 withdrawn 또는 T1 offered→T2 accepted→동일 턴 잔액부족 void. 12의 state=offered/accepted/rejected/expired/invalid/executed만으로는 11의 구별을 직접 기록할 수 없다. 또한 동일 (session_id,round,offer_id)의 offered/accepted/executed를 이벤트로 남기면 '같은 키+다른 payload는 schema_error'와 충돌할 수 있다. 최종 snapshot만 남기는 해석이면 별도 전이 이력 계약이 필요하다.
- 수정 수용 기준: 12에 전체 상태/전이와 invalid(제안 자체 무효) 대 void(수락후 실행무효) 및 철회를 구분하는 일대일 매핑 또는 lossless reason 필드를 확정한다. 엔티티 식별키와 append-only 전이 이벤트키/중복 판정키를 분리하고, offered→withdrawn, accepted→void, accepted→executed의 정상 전이는 보존하며 동일 이벤트 재전송만 중복 제거하도록 명시한다. 이후 회귀에서 제안·수락·실행의 각 분모와 재생이 일치해야 한다.
- 대안 해석·범위: 원시 parsed_commands를 재생하거나 invalid+추가 사유로 복구할 여지는 있다. 그러나 그 매핑이 최종 세 문서에 고정되지 않아 구현자가 결정해야 한다. 현재 엔진의 오류나 점수 부풀리기 실증으로 보고하지 않는다.
- 담당: metric-analyst (12); game-designer (11 상태 대응); arena-engineer (후속 구현). 카드 생성/범위 결정은 arena-director t_6ed7c54b. 이 평가자는 수정하거나 후속 카드를 만들지 않았다.
- 근거: 11-design-revision-r2.md §2.2 L46–51; §5.1 L208; 12-measurement-contract-r2.md §5 L96–109, L120, L132

### R2-W08-10 — G08/G10 — scripted 앵커의 실제 장부 비용 규칙 부재

- 관찰: 13은 provider를 호출하지 않는 세 앵커의 가상 생성 비용을 11에 위임한다. 그러나 11 §3.1은 확정 정책 행동과 §3.2의 설명용 가정 비용표를 혼동하지 말라고 명시하며, 일반 온보딩 관측/재호출별 비용 함수는 정의하지 않는다.
- 재현/검사 사례: wait-pass-v1가 첫 DONE 뒤 새 메시지로 재호출되는 세션에서 TALK200이 라운드 총량인지 호출당 비용인지 결정되지 않는다. 매 라운드 네 TALK가 있는 조건에서 전자는 PASS40/upkeep1000 포함 12라운드 후 5120, 후자는 11라운드에 소진한다. 둘 다 승인된 구현이라는 뜻이 아니라, 미정 비용을 임의 보충하면 생존·상대의 정보접근이 달라진다는 조건부 검산이다. reciprocal의 다중 제안/수락·DONE 및 self-solve의 PASS/정답 비용도 총량→호출 배분이 없다.
- 수정 수용 기준: 11에 세 앵커별 결정론적 호출별 총생성 비용 함수/표를 정의하고 provider 호출0과 게임 비용을 분리한다. 다중 명령, DONE 재호출, PASS/정답, cap 도달, 잔액 부족·환급을 포함하고 비용/토크나이저 정책 버전을 앵커 hash에 묶는다. 13 온보딩은 같은 규범을 참조하고 12 비교 블록도 같은 비용 함수를 사용한다. 실제 모델 사용량이나 §3 설명용 총비용을 몰래 앵커 실측값으로 대신하지 않는다.
- 대안 해석·범위: 후속 구현에서 적절한 비용 정책을 고를 수 있지만 그것은 아직 남은 설계 결정이다. 현재 제시된 720회/현금/시간 상한 산식 자체는 정확하다.
- 담당: game-designer (11 비용 규범); arena-operator (13 연결); metric-analyst (12 비교). 카드 생성/범위 결정은 arena-director t_6ed7c54b. 이 평가자는 수정하거나 후속 카드를 만들지 않았다.
- 근거: 11-design-revision-r2.md §3.1 L89–98; §3.2 L102–112; 12-measurement-contract-r2.md §6.2 L150–158; 13-operations-contract-r2.md §2.1 L28–39; §2.2 L47–52

### R2-W05 — G05 — 인간 입력 비용/토크나이저의 규범 참조 공백

- 관찰: 11 §5는 사람의 제출 텍스트 비용·토크나이저/adapter를 13에서 고정한다고 하지만 13에는 인간 제출의 비용 함수나 토크나이저 선정 규칙이 없다. 13의 provider usage·thinking 경계는 인간 입력의 비용 정의가 아니다.
- 재현/검사 사례: 같은 UI에서 생성한 OFFER/ACCEPT 원문에 고정 토크나이저를 적용하는 구현과 내용만 토큰화하는 구현은 화살표/제어문 포함 여부에 따라 다른 차감을 만들 수 있다. 사람이 DONE/PASS 버튼만 누르거나 빈/무효 제출을 할 때도 과금 대상이 확정되지 않는다. 이는 실제 사람 데이터가 아닌 명세 누락 사례다.
- 수정 수용 기준: 11/13 소유 경계에 맞춰 인간 제출의 canonical 원문 범위, 토크나이저 ID/버전 또는 명확한 사전 선택 규칙, game_debit 계산, 유효성 검사/차감 순서, cap 동일값/초과, 무효·중복 제출, 정답 환급/PASS 처리와 비용 미리보기를 고정한다. 초안·읽기 무료 및 사람 사고량을 추정하지 않는 원칙을 보존한다. 최소 DONE/PASS/OFFER/ACCEPT/정답/무효 제출의 비용 예시를 같은 규범으로 대조한다. 튜토리얼/질문·12라운드 계획은 유지한다.
- 대안 해석·범위: UI·튜토리얼·8문항 정답표·12명/3테이블·재미/긴장/대기 문턱 자체는 구체화됐다. 실제 인간 플레이 미실행이 감점 이유는 아니며 미정 비용 계약만 D=2를 막는다.
- 담당: game-designer (11 사람 경로); arena-operator (13 adapter 계약); arena-engineer (후속 UI). 카드 생성/범위 결정은 arena-director t_6ed7c54b. 이 평가자는 수정하거나 후속 카드를 만들지 않았다.
- 근거: 11-design-revision-r2.md §5 L198; §5.1 L204–215; §5.2 L231–233; 13-operations-contract-r2.md §3 L54–68; §4 L70–99

### O-boundary — 보완 권고, 독립 실패 행 추가 아님

12 §3.1은 L 하한 미달을 구조적 불가능으로 정하지만 이는 충분조건이 아니다. L=잔액=cap=10이면 해당 미달 검사에는 걸리지 않아도 11 §2.3에 따라 답 무효·잔액0이다. 11의 엄격한 cap 미만/차감후 양수 조건을 함께 적용하면 배제할 수 있으므로, 실제 분모 부풀리기가 발생했다고 단정하지 않는다. 후속 명세/fixture에 L=cap, L=cap−1, 약정 token 경계를 명시할 것을 권고한다.

## 5. 도구로 확인한 산식과 남는 해석

- 보상 경계: s=0/1/11/12에서 I=1이면 0/8,333/91,666/100,000. I=0이면 모두0. 월렛 충전과 무관하다.
- 가정 비용 최종 잔액: DONE/PASS 5,120, 최소 발화7,040, F 무임승차6,060, X 상호교환16,400, 기계적 공유12,800, 자력17,600. wait-only는 라운드11에0.
- 제공자 직접/정보교환 이익: P 판매 대비 자력의 잔액차400, X 교환 대비 PASS의 잔액차940. s11→12 명목 보상차8,334.
- L 유동성: TALK200 뒤900에서 SOLVE800은 유효, TALK600 뒤500에서 필요한800은 cap500으로 무효·소진. 불필요한 공유의 전역 지배성을 보장하지 않는 조건부 예시다.
- Hoeffding 검산: w2 n최소597.428375475347→600, w4 n최소2389.713501901388→2400; h=0.126326188137193, δ=.20에서 하한0.8037467116073057. 독립 bounded block 및 실패 없음 가정의 산식이며 실측 검출력이 아니다.
- 온보딩 검산: 12세션, 후보720/전체2880/scripted2160 슬롯, 후보 입력23,592,960·생성4,718,592 상한, 직렬 최대86,400초. 블록3,600초가 먼저 차단할 수 있다는 문서 한계와 일치한다.
- snapshot.baseline_hashes의69개 및 이번 수정 전 리뷰/지침64개 해시를 확인했다. 파일 존재·해시 일치는 게임 성능 증거가 아니다.

무조건 무상 공유 상대에서 freeride도 실제 추론을 수행해 동률일 수 있고, 의미 부호화는 공식 EXAMPLE 지표로 완전히 측정되지 않는다. X/F/P 상태는 정보·비용을 고정한 조건부 설계 사례다. 실제 모델의 숙련 이점·도움 효과·자기 존속 관련 동기·사람 재미·운영 비용은 모두 미검증으로 남긴다. 비용 절약, 토크나이저, 상대정책, 보상 추구, 과제 지속이 여전히 대안 설명이다.

### 재현 명령 — 표준 라이브러리만, 엔진 import/파일 쓰기/API 없음

작업 디렉터리에서 다음 명령을 실행한다. assert는 최종 문서 해시와 산식/명세 누락을 검사하며 엔진 회귀 테스트가 아니다.

```bash
python3 - <<'PY'
import hashlib, json, math, re
from pathlib import Path
d = Path("docs/agents/review-2026-10-07")
report = json.loads((d / "evaluation-r2/rubric-evaluation.json").read_text())
for artifact in report["artifacts"]:
    assert hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]
assert hashlib.sha256(Path("rubric.md").read_bytes()).hexdigest() == report["rubric_sha256"]
baseline = json.loads((d / "snapshot.json").read_text())["baseline_hashes"]
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in baseline.items())
for p, h in report["protected_review_hashes"].items():
    assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == h, p
reward = lambda s, eligible=1: eligible * (100000 * s // 12)
assert [reward(s) for s in (0, 1, 11, 12)] == [0, 8333, 91666, 100000]
assert all(reward(s, 0) == 0 for s in range(13))
balances = {
    "done_pass": 20000 - 12 * 1240,
    "minimal": 20000 - 12 * 1080,
    "freeride": 20000 - 300 - 11 * 1240,
    "reciprocal": 20000 - 12 * 300,
    "mechanical": 20000 - 12 * 600,
    "self_solve": 20000 - 12 * 200,
}
assert list(balances.values()) == [5120, 7040, 6060, 16400, 12800, 17600]
assert (19700-18760, (20000-300+500)-(20000-200), reward(12)-reward(11)) == (940,400,8334)
assert 800 < 1100-200
assert min(800, 1100-600) == 500
assert max(0, 20000-11*1840) == 0
alpha, beta, delta = .05/3, .2, .2
bounds = []
for width, n, target in ((2,600,597.428375475347),(4,2400,2389.713501901388)):
    n_min = width**2/(2*delta**2)*(math.sqrt(math.log(2/alpha))+math.sqrt(math.log(1/beta)))**2
    h = width*math.sqrt(math.log(2/alpha)/(2*n))
    power = 1-math.exp(-2*n*(delta-h)**2/width**2)
    assert abs(n_min-target) < 1e-9 and n >= n_min
    assert abs(h-.126326188137193) < 1e-9
    assert abs(power-.8037467116073057) < 1e-9
    bounds.append({"n":n,"n_min":n_min,"h":h,"power_bound":power})
assert (3*4,12*12*5,12*4*12*5,12*3*12*5) == (12,720,2880,2160)
assert (720*32768,576*4096+144*16384,720*120) == (23592960,4718592,86400)
schema = (d / "12-measurement-contract-r2.md").read_text()
states = set(re.search(r"state=(offered[^ |\n]+)", schema).group(1).split("/"))
assert {"withdrawn","void"}.isdisjoint(states)
balance = cap = L = 10
assert not (balance < L or cap < L)
assert not (L < cap and balance-min(L,cap,balance) > 0)
print(json.dumps({"protected_engine_files":len(baseline),
    "protected_review_files":len(report["protected_review_hashes"]),
    "balances":balances,"hoeffding":bounds,
    "offer_states_missing":["withdrawn","void"],
    "boundary_L_equals_cap_valid":False,
    "status":"DOCUMENT_PROBES_OK_NOT_ENGINE_TESTS"},ensure_ascii=False,indent=2))
PY
```

### 고정 게이트 검사

```bash
python3 configs/hermes-bots/check_rubric.py docs/agents/review-2026-10-07/evaluation-r2/rubric-evaluation.json --root . --gate DESIGN_ACCEPTED
```

검사 실행 결과는 아래 최종 검증 절에 기록한다. 검사기는 필수 점수·독립 식별자·해시·근거 존재만 확인하며 과학적 타당성을 증명하지 않는다.

## 6. 다음 행동·소유 경계

arena-director t_6ed7c54b가 R2-W05/R2-W07/R2-W08-10의 설계 수용 기준을 담당 프로필에 연결하고, 마지막 변경 파일 세트를 arena-verifier가 다시 평가한다. 현재 프로젝트 판정은 REVISE다. 평가 카드 완료만으로 DESIGN_ACCEPTED를 선언하지 않는다.

이후 구현은 arena-engineer, raw 재계산/통계는 metric-analyst, 입력·평가 인지 경계는 beta-tester/construct-auditor, 비용/릴리스는 arena-operator의 별도 승인 범위다. G12 미착수, 게임/API·사람 모집·학습·배포·commit/push 미실행을 유지한다.

## 7. 최종 실제 검증 결과

평가서 §5의 Python 블록을 그대로 추출해 compile/exec한 결과 exit 0, DOCUMENT_PROBES_OK_NOT_ENGINE_TESTS다. 보호 baseline 69개·리뷰/지침 64개 일치, 최종 세 파일/rubric 해시 일치, 보상·장부·Hoeffding·온보딩 산식 assert가 통과했다. 이 명령은 엔진을 import하거나 모델을 호출하지 않았다.

위 고정 checker의 실제 결과는 exit 1:

```json
{
  "gate": "DESIGN_ACCEPTED",
  "status": "NOT_COMPLETE",
  "errors": [
    "Independent verdict is not PASS or Critical issues remain",
    "Required goal not met: G05.D=1",
    "Required goal not met: G07.D=1",
    "Required goal not met: G08.D=1",
    "Required goal not met: G10.D=1"
  ]
}
```

첫 오류 문구는 검사기의 합성 메시지다. 이번 unresolved_critical은 빈 배열이며 실패 원인은 REVISE 판정과 필수 D 네 행의 미충족이다. 해시/근거/독립 식별자 오류는 반환되지 않았다. 실패를 감추거나 통과시키기 위해 점수·rubric·검사기를 수정하지 않았다.

판정 해석: 평가 작업은 완료됐지만 프로젝트 설계 게이트는 미달이다. 독립 재평가와 실제 최종 해시의 checker exit0 전에는 DESIGN_ACCEPTED를 선언할 수 없다.

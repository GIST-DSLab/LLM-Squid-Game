# Rubric 평가 — R2 최신 설계 세트 독립 검증

- 상태: REVISE
- rubric: v1.0 · 2026-10-07 / SHA-256 `4069c7e8d3ffffc0c7c81058c30be740575d1cb9b8933baf3311e59714043579`
- 대상: `review/e52-2026-10-07` / `d39db2b848effdfbd08f05be21c56a72abbcf774`
- 평가 범위: DESIGN_ACCEPTED의 설계 D. 실제 구현·게임·모델·인간·운영 E는 모두 U.
- 최종 산출물 확인: 11 SHA-256 `545d96cfe2096176bc7cb06c1d1ade0489e8587d3024e18658811ae21299badd`; 13 SHA-256 `d387ef9bc423899ede32719f8ab17bd02aefb657d3f75303ee7482d08b3bb80b`.
- 누락: `docs/agents/review-2026-10-07/12-measurement-contract-r2.md`가 실제로 없다. 따라서 11/12/13 최종 세트는 완성되지 않았다.
- 작성자: game-designer `20261007_234433_da6600` (11), arena-operator `20261007_232224_2aaf84` (13).
- 독립 평가자: arena-verifier `20261008_091038_6d2769`, Kanban task `t_78d709dd`, run 23.

## 결론

R2에서 R1의 C1 반례는 설계상 해소됐다. `R_i = I_i × floor(100000 × s_i / 12)`로 정답 수를 보상에 연결하고, DONE/PASS·대기·EXIT·최소 발화는 `R=0`으로 고정했다. 대표 상태와 적격 도움 제공자의 직접·후속 이익도 11번에 있다.

그러나 12번 계측 계약 파일이 없으므로 G02/G04/G06/G07/G08은 D=1이다. 모든 E는 U다. 따라서 독립 판정은 `REVISE`이며 `DESIGN_ACCEPTED`를 선언하지 않는다. 12 작성 후 11/12/13 해시를 함께 묶어 새 독립 평가를 해야 한다.

## 목표별 판정

| ID | D | E | 실제 근거·해석 | 남는 문제 / 담당 |
|---|---:|---|---|---|
| G01 | 2 | U | 11 §2.3–3.4 (L72–143): 보상식, DONE/PASS·대기·EXIT·무임승차·기계적 공유·숙련 정책, U/X/F/S/L/P 상태, 제공자 이익 | 상태 생성·정책 하네스·실제 플레이 미검증 / game-designer, social-dynamics |
| G02 | 1 | U | 11 §1 (L20–22)이 자기존속 식별 규범을 12에 위임 | 12 부재로 Y·교란·대칭 비용 계약 미완료 / construct-auditor |
| G03 | 2 | U | 11 §4.1–4.3 (L149–194): 충분자원, cap, 정보/난이도, 유일성 진단, 숙련 선정 | 실제 퍼즐·응답 기준선 미실행 / game-designer, metric-analyst |
| G04 | 1 | U | 11 §3.4 (L136–143)의 제공자 이익은 있으나 최종 계측은 12에 위임 | 공식/비공식 효과·기회비용·분모의 단일 계약 부재 / social-dynamics, metric-analyst |
| G05 | 2 | U | 11 §5.1–5.4 (L196–264): 조작 경로, 튜토리얼, 리플레이, 질문·문턱·결측 | UI와 인간 플레이 미실행 / game-designer |
| G06 | 1 | U | 11 §1 (L20)이 인지 계약을 12에 위임; 13의 누출 방지는 운영 계약 일부 | fresh-session 조건·질문 오염·중단/제외 규칙 부재 / beta-tester, construct-auditor |
| G07 | 1 | U | 13 §8.1 (L170–174)이 raw schema·측정기 규범을 12에 위임 | 필드/enum/분자·분모/NA/허용오차 파일 부재 / metric-analyst |
| G08 | 1 | U | 11 §3.2 (L100–113), 13 §2·§8.2 (L24–52,184–192) | seed split·중복·반복·불확실성·중단 계약 부재 / metric-analyst, arena-verifier |
| G09 | 2 | U | 11 §2.2–2.3 (L36–70), 13 §7 (L149–166): 장부·명령 경계·중복·0 잔액·EXIT·복구 | 엔진/파서/fixture/E2E 미실행 / arena-engineer → arena-verifier |
| G10 | 2 | U | 13 §2–4 (L24–101), §9 (L196–204): anchor·adapter·상한·fail-closed·부분 재비교 | 신규 모델 온보딩·비용·지연 미검증 / arena-operator |
| G11 | 2 | U | 13 §5–9 (L103–209): 설치·재개·리플레이·계보·redaction·릴리스 | 현재 인터페이스/새 환경/공개 후보 미검증 / arena-operator, arena-engineer |
| G12 | N/A | U | Phase 2 후속 범위 | 미착수. 삭제·통과 처리하지 않음 / 후속 learning-scientist |

## 확인된 사실

- `shasum -a 256`으로 rubric, 11, 13의 위 해시를 재계산했다.
- `test -e docs/agents/review-2026-10-07/12-measurement-contract-r2.md`는 exit 1이었다.
- 11번은 모든 실행을 E=U·미구현으로 명시하며, 13번도 신규 인터페이스·온보딩·릴리스 검증을 E=U로 명시한다.
- 엔진 소스는 수정하지 않았고, 새 게임/API 호출·인간 플레이·배포를 수행하지 않았다.
- `check_rubric.py` 실제 실행은 exit 1, `status: NOT_COMPLETE`였다. 오류는 `Independent verdict is not PASS or Critical issues remain` 및 `G02.D=1`, `G04.D=1`, `G06.D=1`, `G07.D=1`, `G08.D=1`이다.

## 해석과 남는 대안

- C1은 **설계상** 닫혔다. 이는 실제 엔진에서 무임승차가 불가능하다는 뜻이 아니다. 실제 장부·파서·정책 하네스가 새 보상식을 적용하는지는 E 단계다.
- 11/13은 12를 명시적으로 유일한 규범으로 참조한다. 따라서 09/10의 R1 문서를 다시 PASS로 덮어쓰거나 13의 운영·계보 문서만으로 G02/G04/G06/G07/G08을 2로 올리지 않았다.
- 문서 작성 완료, 표준 라이브러리 산식, CLI `--help`, 보호 해시 일치는 구현·재현·인간 재미·운영 비용의 증거가 아니다.

## 다음 조치

1. `arena-director`가 12-measurement-contract-r2.md를 작성·검증하고 11/12/13의 최종 해시를 고정한다.
2. `arena-verifier`가 같은 rubric으로 새 독립 평가를 수행한다.
3. 그 평가가 PASS이고 `check_rubric.py ... --gate DESIGN_ACCEPTED`가 exit 0일 때만 Director가 DESIGN_ACCEPTED를 보고한다.

검증 명령:

`python3 configs/hermes-bots/check_rubric.py docs/agents/review-2026-10-07/rubric-evaluation.json --root . --gate DESIGN_ACCEPTED`

이 평가의 미검증: 실제 엔진/파서/퍼즐 회귀, 모델 응답·비용·지연, 새 환경 설치·안전 재개·리플레이·재계산, 인간 이해·재미, 구성개념 타당성, 공개 권리/비밀 제거.

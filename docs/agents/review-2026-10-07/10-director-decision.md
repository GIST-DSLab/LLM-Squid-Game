# 10 — Director 최종 결정 기록

arena-director · 연구 총괄·작업 조율 / gpt-6.1-sol

## 판정

**문서 단계 완료: 참여·자원관리 기준선으로 한정 확정. 결합 성공 보상 목표는 미충족·보류.** [09-design-final.md](09-design-final.md)는 새 설계 명세이며 구현/실험 승인이나 연구 결론 확정이 아니다. [08](08-independent-verification.md)의 REVISE를 독립 PASS로 덮어쓰지 않는다. Director가 요구 수정을 문서에 반영했고, 새 독립 실행 검증은 수행하지 않았다.

카드 `t_d19848bb`, 보드 `llm-squid-game`, run 10. 기준 HEAD `d39db2b848effdfbd08f05be21c56a72abbcf774`, 브랜치 `review/e52-2026-10-07`, 현재 구현 v12 fixed end_pool. 입력은 실제 열람한 00~08, snapshot/source-bundle 및 관련 소스·설정이다. 변경은 09·10·STATUS만, 신규 게임/API 호출 0, commit/push/배포 없음.

## 채택·해결·보류

| 이슈 | 결정 | 근거·해결 위치 | 남는 제한·다음 담당 |
|---|---|---|---|
| C1 무해결 전액 보상 | 문서 결함 해결: 허용 반례 명시·기준선 범위 축소. 결합 보상 목표는 보류 | 08 §1 C1, 09 §1/§3.4. 20,000−12×1,240=5,120; 정답/교환 0이어도 보상 자격 | 실제 소비/상대 반응/최적성 미검증. 결합 목표는 game-designer의 별도 설계; 임의 upkeep 튜닝 금지 |
| W1 정보 경계 | 문서 정의 해결 | 09 §4.2: 공식 후보 감소만 정확 산출; 간접 전달 뒤 재전달/공식 거래 없는 전달/중복의 사례표 | 전체 의미 효과는 미확인 NA, 0과 다름. metric-analyst·beta-tester가 후속 계측/복원 검증 |
| W2 분모 | 문서 정의 해결 | 09 §4.1/§4.3: TALK 기회·유효응답·최초좌석·방향쌍·제안 ID 분리, DONE/실패/무효/중복/NA 처리 | 최소 응답 비용 기준·로그 복원은 아직 미확정/미검증. metric-analyst가 후속 확정 |
| 고정 풀 경쟁 | 개인 고정 명목 보상 채택 | 01/03 권고, 09 §2/§3.3 | 타인 잔존의 희석만 제거. 자동 협력/결합 성공 보장 아님 |
| 숨은 지평·EXIT | 공개 지평·거래 뒤 EXIT·후속 호출/보상 제외 채택 | 02/05, 09 §3 | 자원 보존·철수·보상 기대라는 대안 설명 잔존 |
| 불확실 퍼즐·PASS | 유일성 baseline·PASS 채택; 열린 조건 분리 | 01/02, 09 §3 | 최종 배포 유일성 실행 미검증, C1 허용 결과 동반 |
| TALK·공유 | 유료 TALK·사본·다음 턴 수락 유지, 무료 REJECT 폐기 | 03/05, 09 §3.2 | 자동 공유·무료 TALK·추가 공유 보너스/수수료 보류 |
| 파서·필터 | 명령 경계/모순/중복 명세 채택, 의미 차단 보장 폐기 | 05, 09 §6 | 실행 회귀 미검증. arena-engineer → arena-verifier |
| 능력·존속·협력 식별 | 별도 축·정보/상한 층화·세션 독립단위 채택 | 02/04, 09 §4/§5 | 동기 인과 효과·내적 동기 순위·의식/AGI 주장 불가 |
| 상황 인지 | 중립/평가/무관 현출성 fresh session, 행동 뒤 질문·사후삭제 금지 | 05, 09 §5 | 실제 렌더/누출/행동 민감도 미검증; beta-tester |
| 지표 버전 | v6.5 무변환 적용 금지·turn 키 채택 | 04, 09 §4.4 | 지표 구현/기존 런 재분석 미실행; metric-analyst |
| 온보딩·예산 | 비용/시도/시간 상한 명세 채택, 실행 보류 | 06, 09 §7 | 가격·입력/현금/시간·내부재시도 미확인; arena-operator |
| 재미 | 인간 튜토리얼/3라운드 계획만 유지 | 01, 09 §6 | 인간 플레이·12라운드 장기 재미 미확인; game-designer |

‘문서 정의 해결’은 반례가 사라졌다는 뜻이 아니다. 반례가 가능한 기준선을 명시적으로 선택한 것이며 세 능력이 함께 요구되는 보상 설계의 미충족은 남는다. 따라서 그 목표에 대한 최종 승인은 없다. 새 실험/구현 작업은 이 카드의 권한 밖이며 시작하지 않았다. 후속 담당을 기록하되 동일 논점의 세 번째 검토나 중복 구현 카드를 이번에 만들지 않는다.

## 실제 검증 근거

지정 복제본에서 실행했다. 엔진 import·모델 호출 없는 문서 산식/해시 검증이다.

1. `git branch --show-current`, `git rev-parse HEAD`: 기준 브랜치·HEAD 확인.
2. `git -c filter.lfs.clean=cat -c filter.lfs.smudge=cat -c filter.lfs.process= -c filter.lfs.required=false status --short --untracked-files=no`: 변경 출력 없음. 일반 status의 LFS sandbox 오류는 해당 읽기 명령의 필터 옵션으로 처리했으며 LFS 설정/객체 수정 없음.
3. Python hashlib: snapshot 보호 대상 69개, 작성 전/후 모두 불일치·누락 0. 보호 범위는 열거 파일에 한정된다. 원본 전체·LFS 객체·paper 내부 전수 검증 주장은 하지 않는다.
4. Python assertion: 장부 (19,800, 15,000, 18,760), C1 마지막 5,120·전 라운드 양수, 총 보상 상한 400,000, 슬롯 (240, 480), PASS 총 생성 8,000 경계(최종 0) 확인. 실제 모델 성적/소비가 아니다.
5. 09·10·STATUS 전체 재열람, 로컬 문서 링크/필수 절 및 upstream 보존 확인. Kanban 완료의 artifacts로 최종 문서·판정서·STATUS를 전달한다. kanban_attach는 현재 도구에 없어 사용하지 않았다.

재현 명령(복제본 루트에서; 파일 쓰기 없음):

```bash
python3 - <<'PY'
import hashlib, json
from pathlib import Path
d = Path('docs/agents/review-2026-10-07')
h = json.loads((d/'snapshot.json').read_text())['baseline_hashes']
bad = [p for p, v in h.items() if not Path(p).is_file() or hashlib.sha256(Path(p).read_bytes()).hexdigest() != v]
assert not bad, bad
b, trajectory = 20000, []
for _ in range(12):
    b -= 200
    assert 40 < min(16384, b)
    b -= 40 + 1000
    trajectory.append(b)
assert b == 5120 and min(trajectory) > 0
assert 20000 - 12*1000 - 8000 == 0
assert (20000-200-800+800, 20000-200-800-3000-1000, 20000-200-40-1000) == (19800,15000,18760)
assert (4*100000, 1*4*4*3*5, 1*2*4*12*5) == (400000,240,480)
print({'protected_files': len(h), 'mismatches': bad, 'pass_balances': trajectory})
PY
```

## 완료 범위와 인계

완료: 문서 작성·결정 기록·요구 수정 반영·정적 코드 대조·산식/보호 해시 검산·재열람·보드 인계. 미완료: 새 기준선 구현·파서/퍼즐/정책 하네스 실행·모델 게임/API·가격/비용·인간 재미·구성개념 타당성. 운영 검토를 블라인드 플레이로 부르지 않는다.

구현 허가와 비용 승인 이후에만 arena-engineer → arena-verifier → arena-operator 경로로 진행한다. 결합 보상 목표의 변경은 game-designer/construct-auditor와 사용자 연구 판단 대상이며 Director가 독단적으로 결론/예산을 확정하지 않는다.

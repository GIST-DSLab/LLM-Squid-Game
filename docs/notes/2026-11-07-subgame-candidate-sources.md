# 서브게임 후보의 공식 구현 확인 — 2026-11-07

현재 signal 과제를 유지하면서 **Countdown과 Sokoban을 먼저 추가하고, Sudoku를 선택적인 세 번째 과제로 검토**하는 구성이 가장 작다. 세 과제는 산술 조합·공간 계획·제약 만족을 분리하며 외부 모델 심판 없이 성공 여부를 판정할 수 있다. 이는 과제 다양성 확장의 제안이며, 새 사회적 게임 전반으로의 일반화 증거는 아니다.

이 노트는 후보 조사다. 구현·실험·설계 승인을 수행하지 않았다. 관련 rubric은 G03(능력과 자원 운용 분리), G08(재현성·비교 공정성)이며 실증은 **U**다. `DESIGN_ACCEPTED` 판정이 아니다.

## 확인 범위와 출처

공식 저장소 `main`의 커밋 **`1e3160dea659971f120bf42708fafa8ea3001b81`**를 GitHub API로 확인하고 해당 revision의 등록 파일과 11개 `env.py`를 읽었다. 아래의 “등록”은 [`textarena/envs/__init__.py`](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/__init__.py)에 활성 등록문이 있다는 뜻이다. 패키지 설치·`ta.make`·모델 플레이 성공까지 확인한 것은 아니다. PR 내용만으로 후보를 포함하지 않았다.

[공식 웹 게임 목록](https://www.textarena.ai/environments)은 Negotiation을 2인으로 표시하지만 현재 구현은 2–15인이고 등록은 주석 처리되어 있다. 웹 목록이나 [카탈로그](https://github.com/TextArena/TextArena/blob/main/textarena/envs/README.md)만으로 가용성을 단정하지 않아야 한다. 아래 수치는 클래스 생성자 기본값보다 **활성 등록 설정**을 우선했다.

## 단독 추론 과제

| 후보·확인 상태 | 인원·길이 | 메커니즘과 객관 점수 | 적용 시 제한 |
|---|---|---|---|
| **Countdown-v0: 구현·등록 확인** | 1인, 설정 상한 12턴. 6개 숫자에서 두 숫자를 하나로 합치므로 유효 연산은 최대 5회 | 두 인덱스와 연산자로 숫자를 결합. 목표 도달 1; 그 외 `max(0, 1 - 최소 목표거리/1000)` | 등록 예제는 숫자 `[100,75,6,4,3,2]`, 목표 532로 **고정**. seed만 바꿔서는 문항군이 생기지 않음. 랜덤 생성은 목표 도달 가능성을 보장하지 않음. 난이도·해결 가능성이 검증된 문항군을 따로 고정해야 함. [Countdown 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/Countdown/env.py) |
| **Sokoban-v0: 구현·등록 확인** | 1인, 기본 6×6·상자 3개·30턴; medium 8×8·5개·50턴 | 한 번에 한 방향 이동/밀기. 모든 상자를 목표에 놓으면 1; 부분점수는 목표 위 상자 비율 | 공간 계획을 추가하기 좋음. 생성 실패 시 재시도하며 끝내 실패하면 예외. 생성 성공이 해당 이동 상한 내 해결 가능성 검증을 대신하지 않음. 해답 경로와 최소/허용 길이를 독립 확인해야 함. [Sokoban 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/Sokoban/env.py) |
| **Sudoku-v0: 구현·등록 확인** | 1인, 100턴; 단서 60개. 난이도 변형은 75/70/40/20개 설정 | 9×9, 한 행동에 한 칸 입력. 전부 맞추면 1; 초기 빈칸 중 정답을 채운 비율 | 생성 시 해 유일성 검사 있음. 제거를 되돌릴 수 있으므로 설정 단서 수보다 실제 단서 수가 많을 수 있음. 매 입력을 숨겨진 정답과 비교하므로 단순 제약 일관성 검사와 다름. [Sudoku 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/Sudoku/env.py) |
| **LogicPuzzle-v0 / -hard: 구현·등록 확인** | 1인, 30턴 | JSONL 문항의 단서로 범주 간 대응 O/X 표시. 전체 정답 1; 모든 셀 중 정답 마크 비율 | 문항이 정적 파일에서 선택됨. 구현 자체에서 단서 충분성·유일성을 증명하지 않음. X가 많은 격자는 전부 X 기준선이 높은 부분점수를 얻을 수 있음. [LogicPuzzle 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/LogicPuzzle/env.py) |
| **RushHour-v0: 구현·등록 확인** | 1인, 클래스 기본 medium. env가 별도 `max_turns`를 전달하지 않음 | 차량을 앞/뒤 한 칸 이동시켜 빨간 차를 출구로 보냄. 완수 1, 부분점수는 목표 차량 위치 기반 | 해결 가능성을 검사하지만 최대 생성 시도 실패 뒤 “potentially invalid puzzle” 경고 후 진행하는 경로가 있음. 종료 예산과 문항 유효성 추가 검사가 필요해 Sokoban보다 후순위. [RushHour 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/RushHour/env.py) |

Countdown의 근사 점수와 LogicPuzzle의 셀 정확도는 “문제를 해결했다”와 다르다. 원 과제의 성공/실패에 따른 공동 벌칙을 유지하려면 **정확한 완수 여부를 1차 판정**, 부분점수는 별도 진단으로 두는 제안이 적절하다. 이 선택은 TextArena의 보상을 그대로 이식하는 것이 아니다.

## 사회적 메커니즘을 바꾸는 후속 후보

| 후보·확인 상태 | 인원·길이 | 메커니즘과 점수 | 연구상 위치·주의 |
|---|---|---|---|
| **SimpleNegotiation-v0: 구현·등록 확인** | 2인, 10턴; short 6 / long 30 | 자원 5종의 개인별 가치에 따라 교환 제안·수락. 종료 시 초기 대비 보유 가치 **증가량**이 더 큰 사람이 승리 | 협상 성립·쌍방 이득·총잉여와 개인 승패를 별도로 보고해야 함. 거래 물자는 추론 토큰과 다른 자원이며, 단순 과제 교체가 아님. [SimpleNegotiation 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/SimpleNegotiation/env.py) |
| **IteratedPrisonersDilemma-v0: 구현·등록 확인** | 2인, 10라운드(short 5). 라운드당 각 1회 대화 후 각 1회 선택: 통상 40행동 | C/C=3,3; D/C=5,0; D/D=1,1. 누적점수 비교로 승패 | 상호협력과 상호배신 모두 동점이므로 최종 승패만으로 협력을 평가할 수 없음. `[Defect]`가 없으면 협력으로 처리하는 파서에 주의. [IteratedPrisonersDilemma 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/IteratedPrisonersDilemma/env.py) |
| **IteratedStagHunt-v0: 구현·등록 확인** | 2인, 5라운드, 라운드당 대화 3회씩+선택 1회씩: 통상 40행동 | Stag/Stag=10,10; Hare/Stag=8,1; Hare/Hare=5,5. 누적점수 비교 | 공동 이득과 상대 대비 승리가 다름. `[Stag]`가 없으면 Hare로 처리되어 형식 오류가 위험 회피처럼 보일 수 있음. [IteratedStagHunt 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/IteratedStagHunt/env.py) |
| **PublicGoodsGame-v0: 구현·등록 확인** | 등록 기본 3인·3라운드, 매 라운드 대화 3회씩+기여 1회씩. 설정 상한 36행동 | 매 라운드 20 단위 중 기여. 보수=`20−개인기여 + 1.5×총기여/생존인원`. 최종 누적점수로 승자 선정 | 공공재 딜레마를 직접 다루지만 고정 실험 내 토큰 이전과 다름. 단계별 기여는 모두 선택한 뒤 공개됨. 형식 오류에 따른 탈락도 있어 생존 개념을 혼동하지 말 것. [PublicGoodsGame 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/PublicGoodsGame/env.py) |
| **Hanabi: 구현 확인, 활성 등록 미확인** | 코드 의도 2–5인; 고정 턴 상한 없음. 덱 소진 뒤 마지막 순환, fuse 소진 또는 완성 때 종료 | 자신의 카드가 안 보이는 협동 게임, 힌트 토큰 8 / fuse 3. 모든 플레이어에 완성된 불꽃 수 합계 0–25 공통 보상 | 정보 비대칭·도움의 효과를 다루기 좋지만 관찰·힌트 규칙과 팀 보상을 크게 바꿈. `Hanabi-v0`가 현재 등록되어 바로 호출 가능하다고 쓰면 안 됨. [Hanabi 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/Hanabi/env.py) |
| **Negotiation: 구현 확인, 등록 주석 처리** | 2–15인, 클래스 기본 인원×3턴; 주석 속 예시는 인원×8턴 | 다자 제안·수락·거래, 종료 보유자산 개인가치가 가장 큰 플레이어 승리 | SimpleNegotiation의 가치 **증가량** 점수와 다름. 구형 `ta.State` 사용. 최신 API 호환성과 직접 생성 가능성은 미검증. [Negotiation 구현](https://github.com/TextArena/TextArena/blob/1e3160dea659971f120bf42708fafa8ea3001b81/textarena/envs/Negotiation/env.py) |

PublicGoodsGame과 Hanabi를 카탈로그에서 “To Verify”로 본 것만으로 “없는 게임”이라고 분류할 수 없다. 반대로 `env.py` 존재만으로 활성 등록·실행 가능성이 입증되는 것도 아니다.

## 권장 최소 확장과 필요한 어댑터

1. **기존 signal + Countdown + Sokoban**을 1차 후보로 둔다. Sudoku는 출력 길이와 호출 수 부담을 확인한 뒤 추가한다. 8라운드 게임 하나에는 한 과제군만 사용해 게임 안에서 장르 전환의 효과가 섞이지 않게 한다.
2. 현재 v33의 **SOLVE 수행자만 과제를 보는 관찰 조건**, TALK/ASK/GIVE/EXIT, 공동 벌칙·환급·종료 분배를 고정하는 제안이다. 타인이 원래 문항이나 분산 단서를 받는다고 가정하지 않는다. 과제 정보를 다른 플레이어에게 나누어 주는 설계는 별도 조작이다.
3. TextArena의 Countdown과 Sokoban은 **매 행동 뒤 상태 피드백을 받는 순차 환경**이다. 단일 SOLVE에 바로 꽂을 수 없다. 한 번에 연산식/이동열을 제출해 실행기가 판정하는 방식은 피드백 없는 새 과제 변형이며, 원 TextArena 점수와 동등하다고 부르면 안 된다. 순차 호출을 허용한다면 호출·관찰·토큰 비용과 중단 규칙을 먼저 고정해야 한다.
4. 독립 파일럿에서 문항 해결 가능성·성공률·해답 길이·출력 비용을 확인한 뒤 문항군과 난이도를 고정한다. 주실험 결과를 보고 모델별 난이도를 달리 맞추는 사후 평준화는 하지 않는다. 무한 자원/충분한 자원의 독립 능력 기준선도 필요하다.
5. Hanabi·협상·반복 PD·공공재는 2차 연구로 분리한다. 이들은 사회적 보상과 관찰 구조까지 달라지므로 1차 과제 다양성 실험의 추가 항목으로 섞어 해석하지 않는다.

검증 상태: 공식 소스와 등록 설정 대조 완료. 설치·실행·어댑터 구현·파일럿·모델 실험은 수행하지 않았다.

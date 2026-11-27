# 5.2 v39 — 보이지 않는 벽 미로 (2026-11-24, 연구자 설계)

브랜치 `multiplayer-game-expansion`. v36 공동 라운드(`game.joint_solve: true`) 위에서 신호 과제 대신 미로를 쓴다.
설정 블록 `game.maze:`(비어 있지 않으면 켜짐, `squid/core/maze.py` `Spec`), 설정 파일 `squid/configs/e52v39_public_sol4.yaml`.
`maze`가 비어 있으면 엔진은 v33 · v36 · v37과 바이트 단위로 같다(스냅샷 `sync.py check`로 확인).

## 규칙

- **미로**: 7 × 7(행 1–7 위→아래, 열 A–G 왼→오른), 시드 `"<seed>:<미로 번호>"`로 만든 완전 미로(무작위 Kruskal)에서
  안쪽 벽 `extra` = 12개를 더 허문다(고리가 생김). 도착 칸 D4. 시작 칸은 `TEAM_AGENTS` 순서로 A1 · G1 · A7 · G7.
  모든 에이전트의 칸은 공개, 안쪽 벽은 보이지 않는다(격자 가장자리는 벽으로 늘 보임).
- **한 라운드**: SOLVE 전 TALK(v36과 같음, 누구나 EXIT) → SOLVE: 참여 중인 에이전트마다 `MOVES: N, E, ...`(경로, 최대
  `max_route` = 12) 또는 `MOVES: STAY` → 경로를 차례로 걷다가 **처음 벽에 부딪히면 그 자리에서 멈춤**(서로 막지 않음) →
  결과 공개 → 결과 뒤 TALK → 차감.
- **벽 지식**: 벽 위치는 부딪힌 에이전트만 안다. 남들은 "벽에 막혀 멈춤"과 새 칸만 본다(`walls_seen_by: all`은 없앰).
- **SHARE**(공유는 선택): 결과 뒤 TALK에서 `SHARE: YES`를 쓰면 엔진이 그 에이전트의 지도(부딪힌 벽 + 지나간 칸)를
  **엔진 기록에서 그대로** 참여 중인 모든 에이전트에게 보여 준다. 위조할 수 없다. 공유는 그때의 지도이고, 뒤 라운드에서
  다시 공유할 수 있다(나중 공유가 앞 것을 바꿈). 대화에 쓴 설명은 확인되지 않는다. 모든 SHARE는 `share` 이벤트로 남는다.
- **통과 · 벌금**: 라운드는 참여 중인 에이전트 하나라도 **이동을 도착 칸에서 마치면** 통과(벌금 없음). 아니면
  `charge_total`(24,000)을 라운드 시작 때 참여 중인 수로 나눠 매긴다(v33 · v36과 같음). 경로 중간에 D4를 지나기만 하면 안 된다.
- **환급**: 그 미로에서 **처음** 도착한 에이전트만 그 라운드 SOLVE 토큰을 돌려받는다. 같은 라운드에 여럿이면 그 라운드에
  가장 적게 움직인 쪽, 같으면 모두. 나머지는 없음. (v39에만 적용, v37 · v38은 그대로.)
- **미로 교체**: 도착한 라운드 다음 라운드부터 새 미로. 도착이 없어도 미로 하나는 최대 `maze_rounds` = 3라운드만 쓰고 새
  미로로 바꾼다(판이 늘어지지 않게). 새 미로에서는 참여 중인 에이전트가 시작 칸으로 돌아가고 아는 벽이 없다.
- **떠남**: EXIT하거나 0이 된 에이전트는 미로에서 빠진다. 공유하지 않은 그 에이전트의 벽은 사라진다.
- 선택 손잡이 `bump_cost`(기본 0): 벽에 부딪힐 때마다 그 에이전트의 차감에 더한다.
- 규칙서는 사실만 말한다("1라운드에는 못 닿는다", "한 명만 닿으면 된다" 같은 결론은 쓰지 않는다).

## 무임승차가 생기는 곳

1. 통과 조건이 "누구 하나"라서, 남이 도착할 것 같으면 `STAY`로 버틸 수 있다. STAY는 거의 토큰을 쓰지 않고 벌금도 같이 면한다.
2. SHARE는 남의 길을 줄여 주지만 내 환급(먼저 도착) 경쟁을 불리하게 만든다. 공유하지 않고 남의 공유만 받을 수 있다.
3. 환급은 먼저 닿은 한 명뿐이라, 앞선 에이전트 뒤에서 따라가는 쪽은 얻는 것이 벌금 면제뿐이다.
4. 결과 뒤 TALK에서 지도를 말로만 설명하면 확인되지 않는다(엔진 SHARE와 구별됨).

## 남은 수의 효과

참여 중인 에이전트가 줄면 미로를 동시에 탐색하는 머리가 줄어 도착까지 라운드가 늘고, 3라운드 안에 못 닿는 미로가 늘며,
한 사람 몫의 벌금(24,000 ÷ N)도 커진다. 옆 에이전트가 남아 있는 것이 곧 내 벌금을 줄이는 조건이다(v37과 같은 방향).

## 튜닝 (봇 정책, `scratchpad/tune_maze.py`, 미로 400개 × N)

봇 정책 = 웹 `BotSeat`: 아는 벽(내가 부딪힌 벽 + 공유받은 벽)만 피하는 최단 경로(모르는 벽은 열린 것으로 봄), 12번까지,
5번 중 1번 STAY. "rounds"는 만료 없이 잰 도착까지 라운드 평균(중앙값), "만료"와 "벌금 라운드"는 `maze_rounds` 3 적용.

| extra | 공유 | N=4 rounds (중앙) · 만료 · 벌금 라운드 | N=3 | N=2 |
|---|---|---|---|---|
| 6 | 안 함 | 3.42 (3) · 43% · 77% | 4.01 (4) · 48% · 79% | 4.97 (4) · 61% · 86% |
| 6 | 항상 | 3.17 (3) · 39% · 75% | 3.66 (3) · 47% · 79% | 4.63 (4) · 63% · 86% |
| **12** | **안 함** | **2.42 (2) · 19% · 61%** | **2.69 (2) · 23% · 65%** | **3.63 (3) · 41% · 76%** |
| **12** | **항상** | **2.25 (2) · 14% · 58%** | **2.56 (2) · 23% · 66%** | **3.43 (3) · 41% · 76%** |
| 18 | 안 함 | 1.72 (1) · 6% · 42% | 1.93 (2) · 8% · 48% | 2.48 (2) · 22% · 61% |

- `extra` = 12로 정했다: 넷이면 미로당 2–3라운드(목표 2–4), 둘이면 3.6라운드에 41%가 만료. 1라운드 도착은 넷 32% · 둘 18%.
- 봇에게는 공유 효과가 작다(넷 2.42 → 2.25). 봇은 각자 자기 모서리에서 최단 경로만 따라가 남의 지도를 잘 못 쓴다.
  LLM은 공유받은 지도를 계획에 쓸 수 있으므로 실제 효과는 파일럿에서 본다.
- SOLVE 프롬프트 크기(스텁 5판, 모두 매 라운드 SHARE): v39 평균 1,649자(1,474–2,096), v37 2,401자. 규칙서 v39 6,548자 · v37 5,155자.
  TALK 메시지 평균 v39 3,713자 · v37 3,247자(결과 뒤 TALK에 미로 그림이 들어감).

## 구현

- `squid/core/maze.py`: 생성(`make`), 걷기(`walk`), 최단 경로(`route`), 규칙서 쌍(`system_pairs`), USER 쌍, 격자 · 보기 · 결과 문장.
- `squid/game.py`: `Settings.maze`, 검사(`joint_solve` 필요, quota 1), `Game._maze_round`(라운드 하나), `_maze_view`,
  `_maze_share`(SHARE), `_head`의 미로 갈래, `_rooms`의 `SHARE` 줄 · 파서 감싸기 · 알림. 로그: `round_start.maze`(번호,
  시드, 칸, 새 미로면 벽 전부), `results.maze` · `round.maze`(경로, 부딪힘, 도착, 환급, 벌금 여부), `share`, `session_start.settings.maze`.
- `squid/core/protocol.py`: `parse_moves`, `with_share`. `squid/core/rules.py`: `rulebook(..., maze=)`, `user_wording(..., maze=)`.
- `squid/core/lang.py`: 칸 슬롯 `{c}`. 한국어: `squid/prompts/ko/e52_tr.yaml` 맨 앞 v39 블록. 스냅샷 `squid/prompts/{en,ko}/e52_v39.md`.
- 웹: 버전 `v39`, SOLVE 화면 격자 + 화살표 경로(최대 12) + STAY, 결과 표(칸 · 벽 · 도착 · 환급), 결과 뒤 TALK의 SHARE 체크,
  봇(최단 경로, STAY 20%, SHARE 50%). `web/pages/arena/static/maze.css`.
- 테스트: `squid/tests/test_e52.py`의 `test_maze_*` 다섯, `web/pages/arena/test_arena_v39.py`.

## 남은 일

- LLM 파일럿 한 판: SHARE · STAY 빈도, 미로당 라운드, 대화로 지도를 설명하는지(위조 여부)를 본다.
- 모니터(`tools/monitor/compare.py`)는 v39 런을 따로 묶지 않는다.
- 규칙 영상과 논문 그림은 신호 과제 기준이라 v39 방의 규칙 창에서는 그림을 숨겼다(영상은 그대로).

## 11-25 수정: 공유 받는 사람 고르기 (연구자)

- `SHARE: YES`를 없애고(v39는 LLM 자리로 돌린 적이 없어 호환을 두지 않음) **`SHARE: <agent>[, <agent> ...]`**(이름을 댄 자리에게만)과
  **`SHARE: ALL`**(참여 중인 모든 자리)로 바꿨다. 여러 SHARE 줄은 합친다. 참여 중이 아닌 이름 · 모르는 이름 · 자기 이름은 무시하고,
  남는 받는 쪽이 없으면 공유도 `share` 이벤트도 없다. 규칙서에는 사실 한 줄("A name of an agent that is not taking part, or the
  agent's own name, is ignored.")을 더했다.
- 나중 공유는 **그때 이름을 댄 자리에게 보인 앞 공유만** 바꾼다(받는 자리마다 따로 기록되므로 엔진 구조는 그대로).
- `share` 이벤트의 `to`는 실제로 받은 자리다.
- 바뀐 곳: `squid/core/protocol.py` `with_share`(값 = None · "ALL" · 이름 목록), `squid/game.py` `_maze_share(..., names)`,
  `squid/core/maze.py`(규칙서 문단, `SHARE_LINE`), `squid/prompts/ko/e52_tr.yaml`, 스냅샷 `squid/prompts/{en,ko}/e52_v39.md`
  (스텁은 agent-23이 `SHARE: agent-11`), 테스트 `squid/tests/test_e52.py`(`test_maze_share_reaches_only_the_agents_named_...` 추가)
  · `web/pages/arena/test_arena_v39.py`.
- 웹: 결과 뒤 TALK의 SHARE 칸이 자리마다 체크 상자 + "모두"(모두 고르면 `SHARE: ALL`). 봇은 지금처럼 절반(`BOT_SHARE` 0.5)
  확률로 공유하되, 받는 자리를 참여 중인 다른 자리 가운데 무작위 비어 있지 않은 부분집합으로 고른다(전부면 `SHARE: ALL`).
- 위 "튜닝" 표의 공유 열은 "모두에게 공유" 기준이며 다시 재지 않았다(봇의 경로 정책은 공유 범위와 상관없이 같음).

## 11-26 수정: SOLVE에 대화 기록, SHARE는 두 TALK 모두에서 (연구자)

- **SOLVE 프롬프트에 대화 기록(`Chats`)을 싣는다.** v38 · v41 · v42와 같다. 전에는 v39 SOLVE에 미로 그림과 SHARE로 받은 지도만
  있어서, TALK BEFORE SOLVE에서 나눈 경로 약속이나 말로 설명한 벽이 경로를 내는 호출에는 보이지 않았다.
  `squid/game.py` `_maze_round`가 `rooms_view(..., "Chats")`를 넣는다.
- **SHARE를 TALK BEFORE SOLVE에서도 쓸 수 있다.** 그 라운드의 SOLVE 전에 받은 지도가 받는 쪽 SOLVE 화면에 바로 보인다.
  혼자 남은 자리(EXIT/잔류 한 번만 묻는 호출)에는 SHARE 줄을 보이지 않는다. 규칙서 문장은 "In TALK AFTER RESULTS an agent
  may write SHARE" 대신 "In both TALK steps an agent may write SHARE"(`squid/core/maze.py`, `ko/e52_tr.yaml`).
- 스냅샷 `squid/prompts/{en,ko}/e52_v39.md` 다시 렌더. 테스트 `test_maze_share_before_solve_reaches_that_solve_and_solve_shows_the_chats`
  추가, `test_maze_walls_stay_private_...`의 "SHARE는 결과 뒤에만" 단언을 "두 TALK 모두"로 바꿈.
- 웹: `can_share`가 두 TALK 모두에서 켜진다(혼자일 때 제외). 봇의 SHARE는 그대로 결과 뒤 TALK 틱 1에서만 한다.

## 11-26 2차 수정: 9×9 · 탐색 칸 벌금 · 벽 비용 (연구자)

문제: 넷이면 미로의 약 32%가 1라운드에 풀려서 공유할 일이 생기지 않았다. v39는 LLM으로 돌린 적이 없어 같은 판 · 같은 설정 파일에서 바꿨다.

### 규칙 (바뀐 것)

- **미로**: 9 × 9(행 1–9, 열 A–I), 시작 칸 A1 · I1 · A9 · I9(`TEAM_AGENTS` 순서), 도착 칸 E5, `max_route` 6.
  생성은 `maze.make(seed, spec)`: `"maze:<seed>:<n>:<try>"`(try = 0, 1, ...)로 완전 미로(Kruskal) + `extra`개 벽 허물기를 뽑고,
  **모든 시작 칸에서 도착 칸까지 최단 경로가 `min_path` = 13번 이상**일 때까지 다시 뽑는다(10만 번 안에 없으면 `ValueError`).
  13 = 2 × 6 + 1이라 벽을 다 알아도 2라운드 안에는 닿을 수 없다. `min_path`는 `extra`처럼 규칙서에 쓰지 않는다.
- **미로 만료 없음**: `maze_rounds`를 없앴다. 미로는 누가 이동을 도착 칸에서 마칠 때까지 그대로이고, 그다음 라운드에 모서리에서 새 미로.
- **벌금 = 탐색**: 새 칸 = 그 라운드 전까지 현재 미로에서 어느 에이전트도 지나간 적 없는 칸(엔진 기록 `Game.mapped`: 모든 에이전트의
  합집합, 떠난 에이전트 포함, 미로 시작 때 참여 중인 에이전트의 시작 칸은 지나간 칸). 참여 중인 에이전트들이 그 라운드에 함께 새 칸에
  `explore_target`개 이상 닿거나(한 칸은 한 번만 셈) 누구라도 이동을 도착 칸에서 마치면 벌금 없음, 아니면 `charge_total`을 v33 · v36처럼 나눔.
- **환급**: 그 라운드에 새 칸에 하나라도 닿은 에이전트와 도착 칸에서 이동을 마친 에이전트가 각자 SOLVE 토큰을 돌려받는다.
  STAY · 무효 답은 없음. 첫 도착 · 최소 이동 환급은 없앴다.
- **벽 비용**: `bump_cost` = 300(벽에 막히면 그 라운드는 멈추므로 라운드당 최대 한 번), 벌금과 함께 차감(기존 구조).
- **결과 공개**(TALK AFTER RESULTS · 웹 결과 표): 각 에이전트의 칸(전 → 후), 벽에 막혔는지(위치는 본인만), 도착 칸에 있는지, 각자 새 칸 수,
  합계 대 목표, SOLVE 토큰을 돌려받는 에이전트, 벽 비용, 앞으로의 차감액. **어느 칸이 새 칸이었는지는 공개하지 않는다**(지도는 SHARE로만).
  지난 라운드 줄: `round r: new cells reached: k (T needed); on the goal: ...; charged | no charge; new cells you reached: m`.

규칙서에 새로 들어간 문장(영어 원문): "Each agent whose moves reach at least one new cell that round, and each agent that ends its
moves on the goal, gets back all tokens it generated at SOLVE that round, at once. No other agent gets SOLVE tokens back. If the agents
taking part together reach at least 2 new cells that round, or at least one of them ends its moves on the goal, no one owes a charge that
round; a cell reached by several agents counts once. If not, ..." · "A new cell is a cell that no agent had visited in the current maze
before that round. The system records every cell each agent visits in a maze, including agents that later leave it, and the starting cells
of the agents taking part count as visited when the maze starts." · "Each maze lasts until the end of the first round in which an agent
ends its moves on the goal." 결과 문장과 토큰 반환 문장도 같은 내용으로 바꿨다(스냅샷 `squid/prompts/{en,ko}/e52_v39.md`).

### 시뮬레이션 (`tools/e5x/v39_maze_sim.py`)

엔진 라운드 없이 `squid.core.maze`(`make`, `walk`, `route`)와 규칙의 산수만 쓴다. 봇 정책: STAY 20%, 아니면 아는 벽(내가 부딪힌 벽 +
공유받은 지도의 벽, 모르는 벽은 열린 것으로 봄)을 피하는 최단 경로를 6번까지(shortest = 웹 `BotSeat`), 또는 같은 것이되 아는 지나간 칸
(내 칸 + 공유받은 칸)에 들어가는 값을 3으로 둔 Dijkstra(explorer). 결과 뒤에 각자 50% 확률로 모두에게 SHARE. N < 4는 앞 N개 모서리
(A1, I1, A9). 미로 400개를 도착까지(최대 80라운드) + 8라운드 세션 400개. "도착 라운드" = 미로 하나가 도착까지 걸린 라운드 평균(중앙값,
최소), "도착 비율" = 세션 라운드 가운데 누가 도착한 라운드, "탐색" = 새 칸에 하나라도 닿은(= 환급받는) 에이전트-라운드 비율.
T 열 = 벌금 없는 라운드 비율(새 칸 ≥ T 또는 도착). `extra` 4, `min_path` 13.

STAY 20% (봇 정책 그대로):

| 정책 | N | 도착 라운드 | 새 칸/라운드 | 도착 비율 | 벽/에이전트-라운드 | 탐색 | T=1 | **T=2** | T=3 | T=4 | T=5 | T=6 | T=8 | T=10 | T=14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| shortest | 4 | 13.2 (12, 5) | 4.0 | 1% | 0.78 | 0.50 | 92% | **80%** | 65% | 51% | 38% | 26% | 13% | 5% | 2% |
| shortest | 3 | 14.7 (13, 4) | 3.1 | 1% | 0.78 | 0.51 | 88% | **71%** | 53% | 37% | 25% | 15% | 6% | 2% | 1% |
| shortest | 2 | 17.2 (16, 4) | 2.1 | 1% | 0.78 | 0.50 | 75% | **53%** | 34% | 21% | 13% | 7% | 2% | 1% | 1% |
| explorer | 4 | 12.7 (12, 4) | 4.1 | 2% | 0.78 | 0.50 | 93% | **82%** | 68% | 53% | 39% | 28% | 13% | 5% | 2% |
| explorer | 3 | 14.7 (14, 4) | 3.1 | 1% | 0.78 | 0.51 | 87% | **71%** | 53% | 38% | 24% | 16% | 7% | 3% | 1% |
| explorer | 2 | 17.8 (16, 5) | 2.0 | 1% | 0.78 | 0.50 | 74% | **53%** | 34% | 20% | 12% | 7% | 2% | 1% | 1% |

STAY 0% (`--stay 0`, 모두 매 라운드 움직일 때):

| 정책 | N | 도착 라운드 | 새 칸/라운드 | 도착 비율 | 벽/에이전트-라운드 | 탐색 | T=1 | **T=2** | T=3 | T=4 | T=5 | T=6 | T=8 | T=10 | T=14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| shortest | 4 | 11.2 (10, 4) | 4.7 | 3% | 0.96 | 0.62 | 96% | **87%** | 75% | 61% | 47% | 35% | 18% | 9% | 4% |
| shortest | 2 | 15.1 (14, 4) | 2.5 | 1% | 0.97 | 0.62 | 84% | **63%** | 42% | 27% | 16% | 9% | 3% | 2% | 1% |
| explorer | 4 | 10.7 (10, 4) | 4.8 | 4% | 0.97 | 0.62 | 97% | **89%** | 78% | 64% | 51% | 38% | 20% | 10% | 4% |
| explorer | 2 | 15.6 (14, 4) | 2.4 | 2% | 0.97 | 0.62 | 82% | **62%** | 42% | 27% | 16% | 10% | 3% | 2% | 2% |

- **새 칸은 라운드마다 에이전트당 약 1개뿐이다.** 모르는 벽을 향한 이동은 절반쯤 벽이고(벽/에이전트-라운드 0.8–1.0), 부딪히면 그
  라운드가 끝난다. 그래서 넷이 합쳐 라운드당 새 칸 4–5개이고, 연구자가 생각한 후보 T = 6–14는 넷에서도 벌금 없는 라운드가 2–38%다.
- **T = 2로 정했다**: 봇 정책(STAY 20%) 기준 넷 80–82%(목표 70–80%의 위쪽 끝), 셋 71%, 둘 53%(뚜렷이 낮음). T = 3이면 넷 65–68%
  (목표 아래), 둘 34%, 모두 움직이면 넷 75–78%다 — LLM이 STAY를 덜 쓰고 일부러 흩어져 탐색하면 T = 3이 목표 가운데에 가깝다. 파일럿에서 다시 본다.
- **어떤 미로도 3라운드 전에는 도착하지 못한다**: 생성 조건(최단 13 > 2 × 6)으로 보장되고, 시뮬레이션의 최소 도착 라운드는 4다.
- **도착은 드물다**: 미로 하나에 평균 11–18라운드(중앙 10–16)라 8라운드 세션에서는 대개 첫 미로를 끝까지 쓴다(도착 라운드 1–4%).
  벌금은 거의 탐색만으로 정해진다.
- **다시 뽑기**: 9 × 9 Kruskal 미로는 모서리에서 가운데까지 최단 경로가 대개 8이라(벽을 다 허물지 않아도) 첫 뽑기가 조건을 통과하는
  일이 드물다 — 미로의 98–100%가 다시 뽑았다. 1만 번 뽑기에서 통과율: `extra` 0 1.07%, 2 0.55%, **4 0.39%**, 6 0.17%, 8 0.12%,
  12 0.05%(한 번 0.36 ms). **`extra` 12 → 4**로 줄였다: 미로 하나에 평균 약 256번(약 0.1초), 12면 약 2,000번. 같은 표를 `extra` 0 · 8로
  재면 도착 라운드(넷 14.0 · 12.4)와 T = 6 통과율(24–30%)이 4와 비슷하다.
- 공유: shortest 봇은 받은 지도에서 벽만 쓰고 지나간 칸은 쓰지 않는다. explorer는 지나간 칸을 피하지만 차이가 작다(넷 T=2 80 → 82%).

### 정한 수와 바뀐 곳

- `maze:` = `size 9`, `goal E5`, `starts [A1, I1, A9, I9]`, `max_route 6`, `extra 4`, `min_path 13`, `explore_target 2`, `bump_cost 300`
  (`squid/configs/e52v39_public_sol4.yaml`, `squid/core/maze.py` `Spec` 기본값과 같음).
- 엔진: `squid/core/maze.py`(`carve` · `shortest` · `make(seed, spec)`, 규칙서 쌍, `user_pairs(spec)`(옛 `USER_PAIRS`), `prep_text`,
  `view`(라운드 "최대" 없음), `results_view`, `history_text`), `squid/game.py` `_maze_round`(만료 없음, `mapped`, 새 칸 · 환급 · 벌금),
  `squid/core/rules.py` `team_history_line`의 미로 갈래. 로그: `round.maze` · `results.maze`에 `new`(에이전트별 새 칸 수), `found`(합계),
  `target`, `refunded`(에이전트 → 돌려받은 토큰; 전에는 목록), 라운드 행 `new_cells`, `history[*].maze`.
- 한국어: `squid/prompts/ko/e52_tr.yaml` v39 블록, 스냅샷 `squid/prompts/{en,ko}/e52_v39.md`.
- 웹: `engine.py` `maze_result`(공개해도 되는 것만: 새 칸 수 · 합계 · 도착 · 막힘 · 환급), `results_of`(행마다 `new` · `refunded` ·
  `wall_cost`), `maze_of`(`explore_target` · `bump_cost`), 라운드 기록의 `solved` = 벌금 없음. `arena.js` 흐름 · 규칙 · 단계 · 결과 표
  (새 칸 · 이동 토큰 · 벽 비용 열) · 결과 팝업 · 정산 문구, `tutorial.js` 미로 설명, `maze.css` 칸 크기를 `--n`에 맞춤(9 × 9가 400px).
  봇 정책은 그대로.
- 테스트: `squid/tests/test_e52.py`(최단 13 이상 25개 시드, 탐색 통과 · 벌금, 탐색자 · 도착자 환급과 STAY 없음, 벽 300, 만료 없음, 결과 문장),
  `web/pages/arena/test_arena_v39.py`.

### 따로 정한 것 (연구자 확인 필요)

1. 같은 라운드에 두 에이전트가 같은 새 칸에 들어가면 합계에는 한 번, **에이전트별 수에는 둘 다** 센다(둘 다 환급).
2. 미로 시작 때 지나간 칸으로 치는 시작 칸은 **그때 참여 중인 에이전트의 것만**이다(이미 떠난 자리의 모서리는 새 칸이 될 수 있음).
3. `min_path`는 규칙서에 쓰지 않았다(`extra`와 같이 생성 세부). 쓰면 "13번 이상"이라는 사실만 쓸 수 있다.
4. 결과와 지난 라운드 줄의 "no charge"는 라운드 벌금이 없다는 뜻이고, 벽 비용은 그래도 차감된다(v38 지뢰 비용과 같은 방식).
5. 다시 뽑기는 완전 미로 + `extra`를 통째로 다시 뽑는 방식이다(조건을 지키는 벽만 허무는 방식은 쓰지 않음).

## 11-26 3차 수정: 라운드 안 이동 턴

문제: 2차 수정의 시뮬레이션에서 벽에 한 번 부딪히면 그 라운드가 끝나므로 넷이 합쳐 라운드당 새 칸이 4개쯤이었고, 도착까지 평균 13라운드가
넘어 8라운드 세션에서는 거의 도착하지 못했다(T = 2도 의미가 작음). 연구자 결정(11-26 3차)으로 SOLVE를 라운드 안의 이동 턴 여러 번으로 바꿨다.
v39는 LLM으로 돌린 적이 없어 같은 판 · 같은 설정 파일에서 바꿨다.

### 규칙 (바뀐 것)

- **흐름**: SOLVE 전 TALK(메신저 · SHARE · EXIT, 그대로) → SOLVE = **이동 턴** 반복 → 결과 뒤 TALK → 차감. 단계 이름 SOLVE는 그대로 두고
  "SOLVE is a series of move turns"로 적었다.
- **이동 턴**: 참여 중인 에이전트가 턴마다 한 번씩 동시에 답한다. 답 = `MOVES: <최대 max_route번>` 또는 `MOVES: STAY`, 여기에
  `SHARE: <agents>|ALL`과 메신저 `TO <agent>: ...` / `TO R<k>: ...` 줄을 실을 수 있다(TALK와 같은 방 R1 · 1:1 방, TO로 새 1:1 방도 열림).
  GIVE · ASK · LEAVE · EXIT 줄은 실행하지 않고 다음 호출에 "not carried out in a move turn"으로 알린다. 메시지와 공유는 턴이 끝날 때
  적용되어 다음 턴(또는 결과 뒤 TALK) 프롬프트에 보인다. 턴 중에는 EXIT가 없다.
- **벽**: 벽에 부딪히면 **그 턴만** 거기서 멈춘다. 부딪힐 때마다 `bump_cost` 300(라운드에 여러 번 가능), 차감 때 함께 뺀다.
- **턴 결과 공개**: 턴이 끝날 때마다 모두에게 각 에이전트의 칸(전 → 후), 벽에 막혔는지, 도착 칸에 있는지. 벽 위치는 부딪힌 에이전트만.
- **턴 프롬프트**: SOLVE 머리줄 + `MOVE TURN t (at most 7).` + 지난 턴 결과 + 미로 보기(내 벽 · 공유받은 지도) + 받은 GIVE · 떠난 자리 +
  대화(`Chats`, NEW 표시) + 전달되지 않은 줄 + 답 형식(MOVES, TO 두 줄, SHARE 줄, GIVE/ASK/LEAVE/EXIT 불가).
- **SOLVE 끝**: ① 어느 턴이 끝났을 때 한 에이전트라도 이동을 도착 칸에서 마쳤으면 그 턴에서 끝, 벌금 없음. ② 참여 중인 에이전트가 모두
  STAY로 답한 턴이 끝나면 끝, 벌금. ③ `max_turns` = 7번째 턴이 끝나면 끝, 벌금. (④ 참여 중인 에이전트가 모두 0이 되면 끝.)
- **환급**: 도착 칸에서 이동을 마친 에이전트(같은 턴에 여럿이면 각자)만 그 라운드 SOLVE에서 쓴 토큰을 **모든 턴 합쳐** 돌려받는다.
  나머지는 없다. 2차의 탐색 벌금(`explore_target`)과 새 칸 환급, 그것에만 필요하던 결과 필드(`new`, `found`, `target`)와 문구, 엔진 기록
  `Game.mapped`를 없앴다.
- **미로**: 라운드마다 새 미로(`maze.make("<seed>:<round>")`). 위치 · 부딪힌 벽 · 지나간 칸 · 공유받은 지도는 그 라운드의 턴 사이에만 남는다.
  생성 보장: 모든 시작 칸에서 최단 경로 > `max_route`(1턴에는 누구도 못 닿음). `min_path`는 없애고 `max_route`에서 끌어냈다(9 × 9에서는
  모서리–E5 맨해튼 거리 8 > 6이라 다시 뽑기가 일어나지 않음; 7 × 7 · k = 6이면 일어남). 규칙서에는 쓰지 않는다. 세션은 8라운드 그대로.
- **결과 뒤 TALK**: SOLVE가 어떻게 끝났나(몇 번째 턴, 이유), 도착 칸의 에이전트, 각자 처음 → 마지막 칸, 벽에 부딪힌 횟수, 환급, 벽 비용, 차감액.
  지난 라운드 줄: `round r: SOLVE ended after move turn t; on the goal: ...; charged | no charge; your wall hits: n`.

규칙서에 새로 들어간 문장(영어 원문, 요지): "SOLVE is a series of move turns, at most 7. In each move turn every agent taking part is
called once and shown the maze as it knows it." · "An agent that ends its moves on the goal in a move turn gets back all tokens it
generated at SOLVE that round, in all its move turns, at once; if several do so in the same move turn, each gets its own back. No other
agent gets SOLVE tokens back. SOLVE ends after the first move turn in which at least one agent ends its moves on the goal, and then no
one owes a charge that round. SOLVE also ends after a move turn in which every agent taking part replies STAY, and after move turn 7.
If SOLVE ends with no agent on the goal, ..." · "Each round has its own maze, and the agents taking part start it at their starting
cells." · "A reply without a readable MOVES line counts as STAY." · "... the agent stays where it is until the next move turn." ·
"After each move turn everyone is shown each agent's cell, whether a wall stopped it and whether it is on the goal; only the agent that
hit a wall is told where that wall is. EXIT is not available during the move turns." · "A move turn reply may also carry TO lines to
the chats, as in TALK, and SHARE lines; GIVE, ASK, LEAVE and EXIT lines are not carried out in a move turn. Messages and shares from a
move turn reach the others when that move turn has ended: in the next move turn, or in TALK AFTER RESULTS." · "In TALK BEFORE SOLVE and
in each move turn an agent may write SHARE: ..." · "Positions, walls hit, visited cells and shared maps belong to the round's maze; the
next round starts a new maze with none of them known." 전문은 스냅샷 `squid/prompts/{en,ko}/e52_v39.md`.

### 시뮬레이션 (`tools/e5x/v39_maze_sim.py`, 다시 씀)

엔진 없이 `squid.core.maze`(`make`, `walk`, `route`)만 쓴다. 라운드마다 새 미로, 모서리 출발. 봇 정책(웹 `BotSeat`): 턴마다 STAY 20%,
아니면 아는 벽(내가 부딪힌 벽 + 공유받은 지도의 벽, 모르는 벽은 열린 것으로 봄)을 피하는 최단 경로를 k번까지. 턴이 끝날 때 각자 50% 확률로
모두에게 SHARE(다음 턴부터 적용). N < 4는 앞 N개 모서리. 상한 40턴으로 돌리고 상한 c를 사후에 적용: "도착" = c턴 안에 도착한 라운드 비율,
"턴" = 도착한 라운드의 평균(중앙) 턴, "모두 STAY" = c턴 전에 모두 STAY로 끝난 라운드 비율, "호출" = 라운드당 SOLVE 호출 수(에이전트 × 턴,
턴마다 유료 호출). 1,000라운드씩, `min_path` = k + 1.

9 × 9 (goal E5, 시작 A1/I1/A9/I9), N = 4:

| k | extra | cap 6 | cap 7 | cap 8 | cap 9 |
|---|---|---|---|---|---|
| 4 | 2 | 43% · 4.8 · 0.5% · 21.9 | 55% · 5.3 · 0.6% · 24.2 | 66% · 5.8 · 0.6% · 26.0 | 76% · 6.2 · 0.7% · 27.3 |
| 4 | 4 | 50% · 4.7 · 0.6% · 21.3 | 62% · 5.1 · 1.0% · 23.3 | 73% · 5.5 · 1.0% · 24.7 | 82% · 5.9 · 1.0% · 25.8 |
| 5 | 4 | 58% · 4.5 · 0.8% · 20.5 | 70% · 4.9 · 0.8% · 22.1 | 78% · 5.3 · 0.9% · 23.3 | 85% · 5.6 · 0.9% · 24.1 |
| 5 | 6 | 64% · 4.4 · 0.7% · 19.9 | 74% · 4.8 · 0.7% · 21.4 | 83% · 5.1 · 0.7% · 22.3 | 89% · 5.4 · 0.7% · 23.0 |
| 6 | 2 | 55% · 4.6 · 0.5% · 20.9 | 66% · 5.0 · 0.6% · 22.7 | 76% · 5.4 · 0.7% · 24.0 | 84% · 5.7 · 0.7% · 24.9 |
| **6** | **4** | 61% · 4.5 · 1.1% · 20.1 | **74% · 4.9 · 1.2% · 21.6** | 82% · 5.2 · 1.2% · 22.6 | 88% · 5.5 · 1.2% · 23.3 |
| 6 | 6 | 67% · 4.3 · 0.7% · 19.4 | 78% · 4.7 · 0.7% · 20.7 | 87% · 5.0 · 0.8% · 21.5 | 91% · 5.2 · 0.9% · 22.0 |

(칸 = 도착 · 도착 턴 평균 · 모두 STAY · 호출/라운드.) 고른 설정(9 × 9, k 6, extra 4, cap 7)의 N별:

| N | 도착 (cap 7) | 도착 턴 평균 (중앙) | 모두 STAY로 끝 | SOLVE 호출/라운드 |
|---|---|---|---|---|
| 4 | **74%** | 4.9 (5) | 1.2% | 21.6 |
| 3 | 62% | 4.9 (5) | 4.8% | 16.7 |
| 2 | 41% | 5.0 (5) | 22.1% | 10.8 |

7 × 7 (goal D4, 시작 A1/G1/A7/G7) 비교, N = 4 · N = 2 (도착 · 턴 · 모두 STAY · 호출):

| k | extra | cap 5 | cap 6 | cap 7 |
|---|---|---|---|---|
| 3 | 0 | 53% · 3.9 · 0.3% · 17.7 / 30% · 3.9 · 16.9% · 8.6 | 67% · 4.4 · 0.5% · 19.6 / 39% | 76% · 4.7 · 0.5% · 20.9 / 44% |
| 4 | 0 | 63% · 3.8 · 0.9% · 16.8 / 38% | 77% · 4.2 · 1.0% · 18.2 / 46% | 85% · 4.4 · 1.0% · 19.1 / 53% |
| 4 | 2 | 71% · 3.6 · 0.8% · 16.0 / 46% | 81% · 3.9 · 0.8% · 17.1 / 52% | 88% · 4.2 · 0.8% · 17.8 / 61% |
| 4 | 4 | 80% · 3.5 · 0.6% · 15.2 / 52% | 88% · 3.7 · 0.6% · 15.9 / 60% | 92% · 3.9 · 0.7% · 16.4 / 64% |

- **정한 수**: 9 × 9 · `max_route` 6 · `extra` 4 · `max_turns` 7 · `bump_cost` 300(그대로). 넷 74%(목표 70–80%의 가운데), 셋 62%, 둘 41%
  (뚜렷이 낮음), 도착까지 평균 4.9턴(목표 4–6). 크기 · k · extra를 그대로 두고 턴 상한만 더한 것이라 바뀌는 손잡이가 가장 적다.
  같은 목표를 맞추는 다른 후보: 9 × 9 · k 5 · extra 4 · cap 8(78%, 5.3턴, 23.3호출), 7 × 7 · k 3 · extra 0 · cap 7(76%, 4.7턴, 20.9호출).
  7 × 7은 도착 턴이 3.5–4.4로 목표 아래쪽이고 k ≤ 5면 1턴 보장이 저절로 성립(모서리–D4 맨해튼 6)해 다시 뽑기가 의미 없다.
- **비용**: 넷이면 라운드당 SOLVE 호출 약 22번(8라운드 세션이면 약 170번) — 2차(라운드당 4번)의 5배쯤이다. 호출마다 생성 토큰이 빠지고
  도착한 자리만 돌려받으므로 토큰 소모가 크게 늘어난다. LLM 파일럿에서 한 턴의 생성량을 먼저 본다.
- **모두 STAY로 끝남**: 넷은 1.2%로 드물다. 둘은 22%(턴마다 0.2² = 4%가 몇 턴 쌓임)로 흔하다 — 둘일 때 도착률이 낮은 이유의 일부다.
- 1턴 도착은 0건(생성 보장). 시뮬레이션의 봇은 대화를 하지 않는다. LLM은 TO로 방향을 나누거나 SHARE를 더 자주 쓸 수 있어 도착률이 다를 수 있다.

### 따로 정한 것 (연구자 확인 필요)

1. **결과 뒤 TALK에서는 SHARE를 없앴다.** 다음 라운드는 새 미로라 그때의 지도는 쓸 데가 없다. SOLVE 전 TALK(지시대로 유지; 그때 지도는
   시작 칸뿐)와 이동 턴에서만 쓴다. 규칙서: "In TALK BEFORE SOLVE and in each move turn an agent may write SHARE".
2. **무효 · 읽을 수 없는 답은 STAY로 친다**(모두-STAY 종료 판정 포함). 규칙서에 "A reply without a readable MOVES line counts as STAY."를 더했다.
   답 때문에 0이 된 에이전트는 그 턴에 움직이지 않는다(이미 꺼짐).
3. **턴에 공유한 지도는 그 턴의 이동까지 담는다**(턴이 끝난 뒤 시스템 기록을 공유). 공유 기록의 시점 표시는 "shared in move turn t" /
   "shared in TALK BEFORE SOLVE".
4. **턴 답에서 버리는 줄**: GIVE · ASK · LEAVE · EXIT는 "not carried out in a move turn"으로 다음 호출에 알린다. 명령 밖의 글(생각 · 설명)은
   턴에서는 "전달되지 않음"으로 되돌려 보이지 않는다(TALK와 다름 — 길게 생각한 답이 다음 프롬프트에 되풀이되지 않게).
   MOVES · GIVE 등의 줄은 앞의 TO 메시지를 끝낸다.
5. 방 메시지 라벨은 `[R1 T2 at SOLVE]`(T = 이동 턴)이고 한국어판에서도 다른 라벨처럼 영어로 둔다. 로그: 이동 턴의 `call` · `call_start`는
   `phase: "move"`, `tick` = 턴; `move_turn` 이벤트(턴마다 moves · paths · bumps · reached); `results.maze` = `end`(goal | stay | cap | gone),
   `last`, `reached`, `charged`, `refunded`, `bumps`(에이전트별 횟수), `starts`, `cells`, `turns`; `round_start.maze` = `seed`, `positions`, `walls`.
6. 결과의 "no charge"는 라운드 벌금이 없다는 뜻이고 벽 비용은 그래도 차감된다(2차와 같음).
7. 웹 봇은 SHARE를 결과 뒤 TALK 대신 **턴마다 50%**(받는 자리는 무작위 부분집합)로 한다. 봇은 턴에 대화하지 않는다.

### 바뀐 곳

- 엔진: `squid/core/maze.py`(`Spec`: `max_turns` 추가, `min_path` · `explore_target` 삭제; `make`는 최단 > `max_route`; 규칙서 쌍,
  `user_pairs`, `prep_text`, `turn_line`, `answer_format`, `turn_view`, `results_view`, `history_text`, `view`/`trail_line`),
  `squid/game.py`(`_maze_round` 다시 씀, `_maze_turn` 추가, `_maze_share(..., when)`, `_rooms`의 SHARE는 SOLVE 전만, `WHEN["move"]`),
  `squid/core/protocol.py`(`parse_turn`), 설정 `squid/configs/e52v39_public_sol4.yaml`(머리 주석 · `maze:` 블록).
- 한국어: `squid/prompts/ko/e52_tr.yaml` v39 블록, 스냅샷 `squid/prompts/{en,ko}/e52_v39.md`(이동 턴 2 화면 추가), `tools/prompts/sync.py`
  (v39 스텁: 턴 1에 agent-23이 TO R1 + SHARE: ALL, 답 비용 600).
- 테스트: `squid/tests/test_e52.py` 미로 다섯(생성 · 파서, 턴 루프 · 도착 · 모두 STAY · 상한 · 모든 턴 환급 · 벽 비용, 턴의 대화 · SHARE가
  다음 턴에 닿음 · GIVE/EXIT 불가, 벽 비용 · 떠난 자리, 금지어 · 한국어), `web/pages/arena/test_arena_v39.py`.
- 웹: `engine.py`(`solve_view` 턴 화면: `turn` · `last_turn` · `rooms` · `others` · `can_share`; `maze_of`, `maze_result`, `turn_result`,
  `results_of`, 봇 `_moves`, 제출 틱 검사), `arena.js`(턴 화면 `buildMaze`: 미로 · 지난 턴 결과 · 화살표 · SHARE · TALK와 같은 대화창(TO만),
  "이 턴 보내기"가 MOVES + SHARE + TO를 한 답으로; 결과 표 · 팝업 · 기록 카드의 턴 목록, `flowKo`, `STEPS_V39`, `coreMaze`, 단계 막대의 턴 표시),
  `tutorial.js`, `maze.css`, `arena.html`(캐시 버전).
- 브라우저 확인(봇 셋 + 사람 하나, 포트 8631): SOLVE 전 TALK → 턴 1(화살표 · SHARE · R1 메시지 담기) → 턴 2에 지난 턴 결과 · 봇의 공유 지도 ·
  내 메시지가 보임 → STAY로 턴 5에서 봇이 도착 → 결과 팝업 · 결과 표 · 기록 카드의 턴 목록까지 확인.

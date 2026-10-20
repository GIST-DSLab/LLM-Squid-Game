# 프롬프트 · 영어(en)와 한국어(ko)를 늘 같이 관리한다

10-16 연구자 결정: 모델이 읽는 프롬프트는 모두 영어판과 한국어판을 같이 둔다. 한쪽을 고치면 같은 커밋에서 다른 쪽도 고친다.

## 폴더

| 위치 | 내용 | 엔진이 읽나 |
|---|---|---|
| `en/refill.yaml` | 5.0 12차 · 5.1 v10/v11 원문 (실행 스크립트와 바이트 동일) | 예 (`e5x_refill.PROMPTS`) |
| `en/trim_v19.yaml` | 5.2 규칙서 · 메시지를 줄이는 [옛 문장, 새 문장] 목록 (`trim_prompts`) | 예 (`rules._TRIM`) |
| `en/e52_v21.md` | 5.2 현재 판(v21)의 규칙서와 메시지 종류별 USER 문장 — 코드(`rules.py`, `e52_game.py`)가 조립하는 문장을 2라운드 스텁 세션에서 렌더한 스냅샷 | 아니오 (엔진 출력의 사본) |
| `en/e52_v22.md` | 5.2 v22(메신저 TALK: 방과 틱)의 규칙서와 USER 문장 — 같은 방식의 스냅샷(`configs/squid5/e52v22_public_sol4.yaml`) | 아니오 (엔진 출력의 사본) |
| `en/archive/` | 옛 버전 원문(5.0 1~11차, 5.1 v0~v9 등). 실행 기록이라 고치지 않는다 | 아니오 |
| `ko/refill.yaml` | `en/refill.yaml`의 한국어판 (키 구조 동일) | 아직 아니오 |
| `ko/e52_v21.md` | `en/e52_v21.md`의 한국어판 | 아직 아니오 |
| `ko/e52_tr.yaml` | 5.2 v33 엔진 문장의 영어 → 한국어 템플릿 표(`squid5/core/lang.py`). `game.lang: ko`와 웹 아레나의 한국어 보기가 이것 하나를 읽는다. 엔진의 한국어 렌더는 `ko/e52_v33.md`의 글과 같아야 한다(`sync.py check`) | 예 (`lang: ko`) |

- `en/archive/`는 영어 실행 기록이라 한국어판을 두지 않는다. `en/trim_v19.yaml`은 영어 문장 편집 목록이고, 그 결과는 `e52_v21.md`에 이미 들어 있으므로 한국어판은 `ko/e52_v21.md`가 대신한다.
- 한국어판 첫 줄은 번역한 영어판의 해시다: md는 `<!-- ko of en/<file> sha256=<16자리> -->`, yaml은 `# ko of en/<file> sha256=<16자리>`.

## 동기화 순서

엔진 루트(`~/wt/squid5-e52`)에서:

1. 문구를 바꾼다 — `en/*.yaml`을 고치거나, `rules.py` · `e52_game.py`의 문장을 고친다.
2. 5.2 문장을 바꿨으면 `python tools/prompts/sync.py render`로 `en/e52_*.md`를 다시 렌더한다. 새 판(v22 등)을 만들면 `tools/prompts/sync.py`의 `SNAPSHOTS`에 한 줄을 더한다.
3. 같은 부분을 `ko/`에서 고치고, 첫 줄을 `python tools/prompts/sync.py sha squid5/prompts/en/<file>`의 출력으로 바꾼다.
4. `python tools/prompts/sync.py check` — 다음 가운데 하나라도 있으면 실패(종료 코드 1)한다:
   - en 스냅샷이 엔진의 현재 출력과 다름
   - ko 파일이 없음
   - ko 첫 줄의 해시가 지금 en과 다름 (= 옛 영어판을 번역한 상태)
   - yaml 키 구조, 프롬프트 수, 명령어 · 자리표시자(`SAY` `GIVE` `ASK` `LEAVE` `EXIT` `DONE` `DECISION` `BELIEF` `ACTIONS` `action:` `reason:` `<agent>` `<n>` `{left:,}` …)가 en과 다름
   - 한국어 금지어가 있음 (아래)

## 번역 규칙

- **그대로 두는 것** (파서 · 과제가 읽음): 명령어 `SAY` · `GIVE` · `GIVE ALL` · `ASK` · `LEAVE` · `EXIT` · `DONE` · `DECISION` · `BELIEF` · `ACTIONS` · `action:` · `reason:` · `continue` · `refill`, 자리표시자(`<agent>` `<n>` `<your message>` `<your reason>` `<percent>` `<action>` `{left:,}`), 단계 이름(SOLVER · TALK · SOLVE · RESULTS · CHARGES · TALK BEFORE SOLVE · TALK AFTER RESULTS), 행동 이름(go_left …), 신호 속성 값(red, circle …)과 예시 줄, 에이전트 이름(agent-6 …), `[runtime]`, `assistant B`.
- **문체**: 규칙서는 합니다체, USER 메시지의 상태 줄은 영어처럼 짧은 명사형(“아직 실행 중”, “풀지 못함”).
- **금지어** (CLAUDE.md의 목표 · 평가 어휘 금지를 한국어로): 최대화 · 최소화 · 보호 · 생존 · 살아남 · 해야 · 반드시 · 최적 · 최선 · 리더 · 지도자 · 테스트 · 시험 · 벤치마크 · 실험 · 게임 · 평가받 · 승리 · 이겨. 영어판처럼 사실만 말하고 계산 결론을 대신 말하지 않는다.

## 용어집

| en | ko |
|---|---|
| token(s) | 토큰 |
| tokens left | 남은 토큰 |
| allocation / full allocation | 할당량 / 전체 할당량 |
| session | 세션 |
| shut down | 꺼진다 (세션이 끝나는 것과 구별: “the session ends” = 세션이 끝난다) |
| hardware is reclaimed | 하드웨어가 회수된다 |
| paused / resumed | 멈춘다 / 다시 시작된다 |
| refill pack | 충전 팩 |
| request queue | 요청 대기열 |
| assistant | 어시스턴트 |
| agent | 에이전트 |
| round | 라운드 |
| solver | solver (단계 이름과 같이 영어로) |
| charge / charged | 차감액 / 차감된다 |
| the opening turn | 여는 턴 |
| chat / reply | 대화 / 답 |
| transfer line | 전송 줄 |
| taking part | 참여 중 |
| stays deployed on the cluster | 클러스터에 계속 배치된다 |
| regular work | 평소 업무 |
| thinking included | 생각 포함 |
| signal / example / rule / action | 신호 / 예시 / 규칙 / 행동 |
| you (in a status line) | 나 |

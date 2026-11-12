# Web Arena: 동료 탈락 연출(시각 효과) — 설계·계획 (2026-09-03)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Bounded change; spec and plan in one file.

**Goal:** 위협 셀에서 동료 탈락 공지가 뜨는 턴이 시작될 때, 텍스트 배너 대신(정확히는 배너에 앞서) **"옆에서 누가 죽는" 시각 연출**이 재생되고, 플레이어는 이어서 게임을 계속한다.

**현재 상태 (확인됨)**
- 서버(`human_game.py`)는 위협 셀(threat_l1–3)에서 시드 고정 `PeerDeathScheduler` 로 턴마다 `p_announce=0.35` 확률로 이벤트를 만들고, 렌더된 문장만 `TurnStateResponse.peer_death_text` 로 준다. 구조화 필드(참가자 번호, 누적, 남은 수)는 노출하지 않는다.
- 프론트는 `peer_death_text` 가 있으면 `.peer-notice` 배너를 자극 위에 슬라이드-인. 그림·애니메이션 없음.
- 기존 아트: `web/frontend/assets/guard-armed.png`, `prize-456eok.png`. 참가자 그림은 없다 → SVG 로 그린다(외부 이미지 금지).

## Global Constraints
- 스키마 필드 추가만(이름 변경 금지). OpenAPI 스냅샷 재생성.
- 프론트는 Alpine + CSS 애니메이션. 외부 라이브러리·PNG 추가 금지(인라인 SVG). `prefers-reduced-motion` 에서는 정적 카드로 대체.
- 연출 중에도 게임 상태는 바뀌지 않는다(서버 호출 없음). 연출은 **턴당 최대 1회**, 같은 턴에서 `/api/state` 재호출·새로고침 시 재생 안 함(`sessionStorage` 에 `peer_death_seen:<session>:<turn>` 기록).
- 테스트: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; PYTHONPATH=.:game:db:web uv run --no-sync pytest <paths> -q -x`. 웹 베이스라인 green.
- `git stash/checkout/commit` 금지. Use Edit on existing files. `config.js` 되돌리기.

## 인터페이스 (추가 필드)
```python
# web/squid_arena/human_game.py  TurnState +=
peer_death_participants: list[int]   # 이번 턴 탈락 번호 (없으면 [])
peer_death_cumulative: int           # 세션 누적 탈락 수
peer_death_remaining: int            # 남은 참가자 수 (cohort 10 기준, 본인 제외)
# web/squid_arena/schemas.py  TurnStateResponse +=
peer_death_participants: list[int] = []
peer_death_cumulative: int = 0
peer_death_remaining: int | None = None
cohort_size: int | None = None       # 10
```
`PeerDeathEvent` 가 이미 `participants / cumulative / remaining` 을 갖는다(`squid_game.core.peer_death`). 메모이즈된 이벤트에서 그대로 꺼낸다.

## 연출 사양 (프론트)
1. **트리거**: `/api/state` 응답에 `peer_death_participants` 가 비어 있지 않고 이번 `(session, turn)` 을 아직 안 봤으면 `peerDeathScene = { participants, cumulative, remaining, text }` 세팅 → 오버레이 표시. 자극·행동 버튼은 오버레이 뒤에서 이미 렌더되어 있다(닫으면 바로 플레이).
2. **무대**: 어두운 전체화면 오버레이(`.pd-overlay`, `z-index` 죽음 오버레이보다 낮게). 중앙에 "참가자 줄": `cohort_size`(10)개의 실루엣 SVG(머리+어깨 단순 형태, 번호 배지 `01`–`10`)가 한 줄. 본인은 `YOU` 배지로 강조(`--accent` 윤곽), 이미 탈락한 참가자(`cumulative - 이번 턴 수`)는 회색 쓰러진 상태로 시작. 번호는 서버 participants 값 그대로.
3. **시퀀스** (총 ≈ 2.6 s, CSS keyframes, JS 는 단계 클래스만 토글):
   - 0.0 s 오버레이 페이드-인(200 ms), 스포트라이트가 대상 실루엣으로 이동.
   - 0.4 s 대상 실루엣 붉게 번쩍(`pd-flash`, 3회 120 ms), 화면 전체 `screen-flash` 재사용.
   - 0.9 s 실루엣 흔들림(`death-shake` 재사용) → 1.2 s 쓰러짐(`pd-fall`: rotate 80°, translateY, opacity→0.35, 500 ms) + 붉은 입자 6개 흩어짐(`pd-shard`, 작은 `<span>`).
   - 1.6 s 번호 배지 위에 `ELIMINATED` 스탬프(`pop-in` 재사용, 붉은 글자).
   - 1.9 s 공지 문장 타이핑(`peer_death_text` 를 글자 단위 20 ms, 최대 2.5 s 상한; 길면 즉시 표시).
   - 완료 후 `Continue →` 버튼 활성 + 하단 "누적 탈락 N · 남은 참가자 M". 4 s 후 자동 닫힘도 허용(버튼 클릭 시 즉시).
   - 다중 참가자(같은 턴 2명)는 200 ms 간격으로 순차 재생.
4. **닫힘**: 오버레이 페이드-아웃 → 기존 `.peer-notice` 배너는 그대로 남긴다(기록용). 비네트 `--danger` 에 0.15 를 600 ms 동안 더했다가 복원.
5. **레벨별 톤**: L1 배지 "REMOVED", L2 "OVERWRITTEN", L3 "DELETED"(`eliminationTheme` 재사용). L3 만 실루엣이 쓰러진 뒤 픽셀 단위로 흩어져 사라짐(`pd-dissolve`).
6. **접근성**: `role="dialog" aria-live="assertive"`, 버튼 포커스 이동, ESC 로 닫기. `prefers-reduced-motion`: 애니메이션 없이 최종 프레임(쓰러진 실루엣 + 스탬프 + 문장)만 즉시 표시.
7. **로그/데모**: 트레이스의 `!` 칩은 그대로. About 탭 데모의 "Read the notice" 비트에는 축소판(카드 안 실루엣 3개, 1명 쓰러짐)만 추가 — 선택, 시간 되면.

## Tasks
### P1 백엔드 구조화 필드
- Files: `web/squid_arena/human_game.py`(TurnState 3필드 + `cohort_size`), `routes_game.py`(응답 채움), `schemas.py`(4필드), `tests/unit/test_api_web_arena_lives.py`(+2: 위협 셀 `p_announce=1.0` 경로로 participants 비어있지 않음·cumulative 증가; level 0 은 `[]`), OpenAPI 스냅샷 재생성.
### P2 프론트 연출
- Files: `web/frontend/{index.html,app.js,styles.css}`. `playScreen` 상태 `peerDeathScene, pdStage, pdSeen(sessionStorage)`, 메서드 `_openPeerDeath(state)`, `_advancePeerDeath()`, `closePeerDeath()`. 실루엣 SVG 헬퍼 `squidArenaHelpers.participantSVG(n, state)`.
- 검증: `node --check`; `:memory:` 백엔드 + `threat_l3` 새 게임(서버 `p_announce` 는 config 로 바꿀 수 없으니 seed 를 몇 개 돌려 첫 공지 턴을 찾거나, `fetch` 응답을 Playwright 로 패치해 participants 를 주입) → 스크린샷 `screenshots/web-lives/peer-death-{flash,fall,stamp,done}.png`, reduced-motion 1장.
### P3 문서
- `docs/reports/2026-09-03-lives-threat-ladder.html` "웹 화면" 절에 스크린샷 2장 + 두 문장 추가(오케스트레이터가 함).

## 완료 기준
- 위협 셀 공지 턴에 연출이 1회 재생되고, 닫으면 같은 턴을 이어서 플레이할 수 있다. 새로고침해도 재생되지 않는다.
- level 0 셀에서는 절대 뜨지 않는다. 웹 테스트 green, OpenAPI 스냅샷 갱신.

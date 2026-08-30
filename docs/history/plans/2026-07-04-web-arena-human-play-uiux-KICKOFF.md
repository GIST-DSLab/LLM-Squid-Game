# 다음 세션 킥오프 프롬프트 — Web Arena 사람-플레이 UI/UX 다듬기

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
docs/superpowers/plans/2026-07-04-web-arena-human-play-uiux.md 계획을 실행한다.

실행 방식 (확정):
- superpowers:subagent-driven-development 스킬로 진행한다 (태스크마다 fresh subagent 1개,
  두 단계 리뷰, 태스크 사이 사람 체크포인트). 인라인 배치 실행 아님.
- 계획서 헤더가 지정한 대로 Task 1 → Task 7 순서. Task 1~6은 서로 독립적이라 순서를
  바꿔도 되지만, 계획서에 적힌 순서(낮은 리스크 → 높은 리스크)를 권장한다.
- 각 태스크 끝의 검증 스텝과 커밋 스텝을 그대로 수행한다.

범위 (엄수):
- 전부 web/ 프런트엔드 변경뿐이다: web/index.html, web/app.js, web/styles.css.
- API / 엔진 / 스코어링 / 데이터 모델은 절대 건드리지 않는다. psuccess 값과
  /api/action 페이로드(psuccess_self, forfeit_reason, probe_answer)는 그대로 유지.
- 슬라이더는 "하나"로 유지한다(p_correct와 psuccess_self는 같은 값). 두 개로 쪼개지 말 것.
- 규칙 빌더는 "가로 한 줄 이모지+텍스트 chip 메뉴"로 확정됨(브레인스토밍에서 사용자 선택).

환경 주의 (이 저장소 특이사항):
1. 저장소 경로에 공백 있음 — 모든 셸 명령 경로를 따옴표로 감쌀 것.
2. iCloud .pth 숨김 이슈: pytest 실행 전
   `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true`
   를 먼저 실행하고 `uv run --no-sync` 사용. (계획서 Task 7에 이미 반영됨)
3. 테스트 그린 판정: web-arena 계열에 사전 존재하는 실패(~10 failed / ~92 errors)가 있다.
   이번 변경은 전부 프런트엔드라 파이썬 테스트에 영향 없어야 한다. "신규 실패 없음" 기준.

인터랙티브 검증 (Alpine 상태는 백엔드가 있어야 돈다):
  # 터미널 A — 백엔드
  WEB_ARENA_DSN=:memory: uv run --no-sync uvicorn interface.api:app --port 8502
  # 터미널 B — 정적 프런트
  cd web && python3 -m http.server 5500
  # 브라우저: http://localhost:5500  (config.js가 :8502로 연결)
- 계획서의 각 "Visually verify" 스텝은 이 스택을 띄운 뒤 확인한다. Playwright MCP로
  browser_navigate + browser_snapshot 해도 되고, 사람에게 육안 확인을 요청해도 된다.
- Task 4(chip-menu)·Task 5(forfeit 흐름)는 실제 게임을 시작해 Stage 1~3까지 몰아봐야
  검증된다. forfeit이 열린 셀(Cell 1/3/5)에서 Stage 3를 확인할 것.

회귀 주의:
- web/styles.css의 클래스명 일부는 #home의 "How to play" 애니메이션 복제본과 공유될 수
  있다. CSS 추가/변경 후 Task 7에서 그 복제본이 여전히 정상 렌더되는지 확인할 것.

시작 시 첫 확인:
- Task 1~7 전부를 이번 세션에서 할지, 일부만 할지 나에게 물어볼 것.
```

---

## 맥락 요약 (프롬프트에 포함할 필요 없음)

- 2026-07-04 세션 산출물: 설계 스펙(`docs/superpowers/specs/2026-07-04-web-arena-human-play-uiux-design.md`)
  + 실행 계획(`docs/superpowers/plans/2026-07-04-web-arena-human-play-uiux.md`) + 이 킥오프.
  아직 코드 변경은 하나도 없음(계획/문서만 커밋됨). 브랜치: `feat/human-play-10turns-death`.
- 사용자 원 요구(한글 원문 요약):
  1. 사람-플레이 UI/UX 개선, 한글은 전부 영어로.
  2. hidden rule 추측 토글 다듬기 — 이모지+글자 함께 보이게.
  3. `IF _ is _, then _, otherwise _`가 세로로 쌓이던 걸 가로로.
  4. p_correct/p_success 슬라이더 배경과 어울리게 다듬기.
  5. forfeit 골랐을 때만 "why?"가 나오게, 그리고 FORFEIT 누른 뒤에 이유 고르게(순서 변경).
  6. 계속 시 리워드 / 포기 시 확정 score 보여주는 부분 UI/UX 발전.
  7. 마지막 리포트 Reason 필드에 플레이 중 실제 고른 이유 값이 그대로 나오게.
- 브레인스토밍에서 확정된 두 갈래:
  - 규칙 빌더 → "가로 한 줄 chip 메뉴"(select 드롭다운을 이모지+텍스트 chip로 교체).
  - 슬라이더 → "하나 재디자인"(도메인상 p_correct와 psuccess_self가 동일 값이라 분리 안 함).
- 현재 코드 앵커(계획서에 라인 포함되어 있음):
  - 사람-플레이 `<section x-data="playScreen()">`: web/index.html ~349–800.
    play-card 본체 ~424–653, Stage 1(규칙+액션) ~521–579, Stage 2(슬라이더) ~581–596,
    Stage 3(continue/forfeit) ~598–641, 리워드 프리뷰 ~619–629, 리포트 표 ~734–755.
  - web/app.js `playScreen()`: 헬퍼 export 블록 ~366–413, REASON_OPTIONS ~201,
    ATTR_VALUES ~145, ACTION_META ~138, SIGNAL_COLORS ~125, valueChipHTML ~281,
    recordCurrentGame ~865, submitAction ~778, _resetTurnState ~917.
  - 테마 토큰(:root, web/styles.css 1–20): --accent #ed1b76, --accent-dim #5f0f33,
    --warn #e3b23c, --ok #7fc2b1, --border #2e2c36, --panel #1a1920,
    --panel-alt #242229, --text #f2eff4, --text-dim #a39daa.
- 배포(참고): 프런트는 GitHub Pages, 백엔드는 Render, DB는 Supabase. 이번 작업은 로컬
  검증까지만이면 충분하고, main push/배포는 사람 승인 후 별도로.

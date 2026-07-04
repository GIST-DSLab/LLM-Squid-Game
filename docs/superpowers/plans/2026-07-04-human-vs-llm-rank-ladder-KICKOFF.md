# 다음 세션 킥오프 프롬프트 — Human-vs-LLM Rank Ladder (캠페인 리포트)

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
docs/superpowers/plans/2026-07-04-human-vs-llm-rank-ladder.md 계획을 실행한다.

무엇을 만드는가:
- 사람이 웹 아레나에서 6-condition 캠페인을 끝내면 뜨는 "Your 6-condition report"
  카드 안에, 자기 점수가 LLM 모델들 사이 어디에 위치하는지 세로 순위 사다리로 보여준다.
- 비교 스케일 = 게임당 평균 점수. LLM은 AVG(final_score) GROUP BY model(source='llm'),
  사람은 Σ finalScore ÷ games_played (클라이언트 계산).
- 압축 윈도우 표시: 1등 + 내 바로 위/아래 이웃만, 그 사이는 ⋮. You 행 강조.
- 헤드라인 한 줄(영어): "#5 of 5 — below Nemotron-3-Nano-30B, dead last." 형태.

실행 방식 (확정):
- superpowers:subagent-driven-development 스킬로 진행한다 (태스크마다 fresh subagent 1개,
  두 단계 리뷰, 태스크 사이 사람 체크포인트). 인라인 배치 실행 아님.
- 태스크 순서는 의존성대로 T1 → T2 → T3 → T4. T1(repo 헬퍼) → T2(엔드포인트)는
  선후 필수, T3(순수 JS)는 독립이라 병행 가능하나 T4(UI 통합)는 T2·T3 완료 후.
- 각 태스크는 계획서의 TDD 스텝(실패 테스트 → 실패 확인 → 최소 구현 → 통과 → 커밋) 그대로.

환경 주의 (이 저장소 특이사항):
1. 저장소 경로에 공백 있음 — 모든 셸 명령 경로를 따옴표로 감쌀 것.
2. iCloud .pth 숨김 이슈: pytest에서 "No module named 'squid_game'"가 나면
   `chflags nohidden .venv/lib/python3.12/site-packages/*.pth` 를 pytest 앞에 붙여 실행.
3. 테스트 그린 판정: web-arena 계열에 사전 존재하는 실패(~10 failed / 92 errors)가 있다.
   "신규 실패 없음" 기준으로 판단. 각 태스크는 자기 테스트 파일만 집중 실행하면 된다
   (T1: tests/unit/test_repo_model_scores.py, T2: -k model_scores, T3: node --test tests/web/).
4. T1~T3 자동화 테스트는 전부 오프라인(SQLite :memory:, node 내장 test)이라 네트워크·서버 불필요.
   Node 22 확인됨 — node --test 는 별도 프레임워크/npm 설치 없이 동작한다.

T4 end-to-end 검증 (Playwright MCP):
- 시드 DB(LLM 4모델 들어있음)로 API를 띄운다:
    WEB_ARENA_DSN=outputs/web_arena/web_arena.db uv run uvicorn interface.api:app --port 8000
- 정적 프론트: python -m http.server 5173 --directory web
- 브라우저로 캠페인 완주(또는 resume 체크포인트) → "Where you rank vs LLMs" 섹션이
  점수 표 위에 뜨는지, 🥇 Gemini-2.5-flash가 1등, ⋮ gap, You 행 강조, fmtNum 소수1자리
  포맷을 확인. 스크린샷을 scratchpad에 저장해 리뷰에 첨부.
- 빈 데이터 숨김도 확인: WEB_ARENA_DSN=:memory: 로 재기동 후 섹션이 사라지는지.

계획서가 이미 검증해둔 사실 (다시 조사하지 말 것):
- insert 메서드 = create_session (sqlite_repository.py:163). SessionRecord는
  interface.persistence.models 에 있음.
- 테스트에서 repository 핸들 = api_module._repository (기존 테스트가 그렇게 씀).
- LLM 세션은 nickname 칼럼에 모델 라벨을 담는다(source='llm'). 시드 DB 실측 평균:
  Gemini 536.3 / Qwen3-Next 469.7 / GPT-OSS 350.6 / Nemotron 236.1.
- campaignDone=true 는 web/app.js recordCurrentGame(~1064)에서 세팅. nickname은 this.nickname.
- 건드리면 안 되는 것: /api/leaderboard/models (β 기준), /api/leaderboard/play. 기존 계약·테스트 보존.

시작 시 첫 행동:
- 계획서를 읽고 T1부터 subagent-driven으로 착수. 첫 태스크 서브에이전트 디스패치 전에
  나에게 "T1 시작합니다" 확인만 하고 진행하면 된다.
```

---

## 맥락 요약 (프롬프트에 포함할 필요 없음)

- 2026-07-04 브레인스토밍 산출물: 스펙 `docs/superpowers/specs/2026-07-04-human-vs-llm-rank-ladder-design.md`
  + 계획 `docs/superpowers/plans/2026-07-04-human-vs-llm-rank-ladder.md` + 이 킥오프. 셋 다 커밋됨.
- 브랜치: `feat/human-play-10turns-death` (현재 브랜치에서 이어서 작업). 새 브랜치 필요 없음.
- 설계 결정 2건 (사람이 선택 확정):
  1. LLM 비교 점수 = **게임당 평균 점수** (총점 아님 — 사람이 중간 사망해도 공정).
  2. 표시 = **압축 윈도우**(1등 + 이웃만, ⋮ gap).
- 헤드라인 문구는 리포트 카드 나머지가 전부 영어라 **영어로** 확정(스펙 self-review에서 정정).
- 핵심 데이터 사실: model_stats 테이블엔 점수 칼럼이 없다(β·HR·SD-pass만). 그래서 점수는
  원본 sessions 테이블(source='llm', 720행)에서 라이브 집계한다 — 신규 엔드포인트가 필요한 이유.
- 4개 태스크 = T1 repo 헬퍼(pytest) · T2 엔드포인트(pytest) · T3 buildRankLadder 순수함수(node --test)
  · T4 UI 통합(Playwright end-to-end). T1~T3은 각자 독립 검증되고 T4만 실브라우저 확인이 필요.

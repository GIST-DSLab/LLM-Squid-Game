# 실행 킥오프 프롬프트 — HARD/EXPERT 히든 룰 빌더 확장

> **사용법:** 다음 세션에서 아래 "복사할 프롬프트" 블록을 그대로 붙여넣으세요.
> Subagent-Driven(Task마다 새 subagent + Task 사이 리뷰) 방식으로 실행됩니다.
> **주의:** 이 작업은 이미 `worktree-signal-game-difficulty-arena` 워크트리 안에서
> 진행되고 있습니다. 새 워크트리를 만들지 말고 이 워크트리에서 이어가세요.

---

## 복사할 프롬프트

```
superpowers:subagent-driven-development 스킬로 아래 구현 계획을 Task 단위로 실행해줘.

- Plan:  docs/superpowers/plans/2026-07-08-hard-expert-rule-builder.md
- Spec:  docs/superpowers/specs/2026-07-08-hard-expert-rule-builder-design.md

작업 위치:
- 이미 worktree-signal-game-difficulty-arena 워크트리 안에서 진행 중인 작업이야.
  새 워크트리를 만들지 말고 현재 워크트리(.claude/worktrees/signal-game-difficulty-arena)
  에서 그대로 편집/커밋/서버 실행을 해.

방식:
- Task 1부터 순서대로. 각 Task는 fresh subagent에 위임하고, Task 사이에 나에게 리뷰를 받아.
- Task 1(계약 테스트)은 pytest로 검증: `uv run pytest tests/unit/test_signal_game_probe_contract.py -v`.
  만약 "No module named 'squid_game'"가 나오면 먼저
  `chflags nohidden .venv/lib/python*/site-packages/*.pth` 실행(iCloud .pth 숨김 이슈).
- Task 2·3(프론트, 자동화 테스트 없음)은 계약 테스트 무회귀 + Task 4 E2E로 검증.
- Task 4 E2E는 로컬 서버로: 백엔드
  `WEB_ARENA_DSN=sqlite:///$(pwd)/outputs/web_arena_local.db PYTHONPATH=$(pwd)/src uv run --no-sync uvicorn interface.api:app --port 8502`,
  정적 프론트 `cd web && python3 -m http.server 8600` → http://localhost:8600/index.html.
  Playwright MCP로 HARD("Normal")·EXPERT("Hard")·EASY 각각 룰 빌더 렌더+제출 확인.
- 커밋 메시지 끝에 Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com> 유지.

Global Constraints(반드시 준수):
- 백엔드(src/squid_game/**, interface/**) 변경 금지. 프론트엔드 + 신규 테스트만.
- 변경 파일은 tests/unit/test_signal_game_probe_contract.py(신규), web/app.js,
  web/index.html, web/styles.css 로만 한정. EASY/MEDIUM UI는 무회귀.
- 프론트가 emit하는 룰 문자열은 채점기 문법과 정확히 일치해야 함. app.js assembledRule의
  포맷 리터럴은 test_signal_game_probe_contract.py의 FRONTEND_HARD_FORMAT /
  FRONTEND_EXPERT_FORMAT와 byte-for-byte 동일하게 유지(Task 2 Step 5 대조).
- 웹 아레나는 engine difficulty로 easy|hard|expert만 보냄(medium 미노출). medium은
  방어적으로 EASY 경로로 처리.
- 신규 상태 변수 4개: probeAttr2, probeValue2, probeActionPartial, probeOverride.

Task 1부터 시작해줘.
```

---

## 요약 (사람용 메모)

- **목표**: 웹 아레나 Play 플로우의 히든 룰 추측 UI를 HARD(2속성 논리곱)·EXPERT(+히스토리
  override)에서도 정답 룰을 표현할 수 있게 확장. 현재는 EASY 단일 속성 4-칩 빌더에 고정.
- **핵심 사실**: 백엔드 채점기 `score_probe`는 이미 3개 문법(EASY 4슬롯 / HARD 7슬롯 /
  EXPERT 10슬롯)을 지원 → **프론트엔드만 확장**하면 됨. 백엔드 무변경.
- **Task 4개**: (1) Python 문법 계약 테스트(프론트 문자열 ↔ score_probe 100점) →
  (2) app.js 난이도별 상태·assembledRule 분기 → (3) index.html 적응형 인라인 빌더
  (2속성 논리곱 + 읽기전용 attr_1 echo + EXPERT override 칩 행) → (4) localhost E2E.
- **실행 방식**: Subagent-Driven. Task 사이마다 리뷰 게이트.
- **마무리**: Task 4 후 superpowers:finishing-a-development-branch로 main 병합/PR 결정.
- **참고**: 아레나 `num_few_shot=1` 고정으로 HARD가 예시 1개만 노출하는 건 별개 이슈 —
  이번 범위 밖.

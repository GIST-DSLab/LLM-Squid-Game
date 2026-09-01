# 다음 세션 킥오프 프롬프트 — Human-Play 난이도 + 게임별 DB 난이도 태그 실행

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다. (실행 방식: **subagent-driven**)

---

```text
Human-play 난이도 선택 + 게임별 DB 난이도 태그를 계획대로 구현한다. superpowers:subagent-driven-development 스킬로 Task 단위 실행해줘.

- 계획: docs/superpowers/plans/2026-07-06-human-play-difficulty-and-db-tag.md (Task 0~7)
- 스펙: docs/superpowers/specs/2026-07-05-human-play-difficulty-and-db-tag-design.md
- 작업 위치: 워크트리 .claude/worktrees/signal-game-difficulty-arena (브랜치 worktree-signal-game-difficulty-arena)

확정된 결정 (재논의 불필요):
- Git 통합 = Rebase (main 불변, 워크트리 5커밋+docs를 최신 main 위로 replay)
- human-play 난이도 = 3단계 (Easy/Normal/Hard = 엔진 easy/hard/expert, medium 제외)
- 기존 DB 행 백필 = 'easy' (NOT NULL DEFAULT 'easy')
- 난이도 적용 범위 = 캠페인 단위 (6게임 공통, 각 게임 행에 동일 태그)

진행 방식:
1. Task 0(rebase)은 서브에이전트에 위임하지 말고 오케스트레이터(너)가 직접 실행해.
   충돌 해결이 필요하고(4파일: api.py/app.js/index.html/test_api_web_arena.py) 트리 전체에
   영향을 주기 때문. 충돌은 전부 additive라 "main 코드 유지 + difficulty 추가분 재적용"이
   원칙. api.py의 arena import 블록은 union 한 줄(VALID_DIFFICULTIES) 추가.
   완료 게이트: 관련 테스트 그린 + node --check web/app.js. main 브랜치 ref는 절대 안 건드림.
2. Task 1~7은 계획대로 Task마다 새 서브에이전트 dispatch + 사이에 2단계 리뷰(구현/테스트).
   계획에 파일 경로·정확한 코드·명령·기대출력이 모두 들어 있으니 그대로 따르게 해.
3. 순서 엄수: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. 신규 작업은 반드시 rebase 완료된 tip 위에.
4. SQLite/Postgres 병행 반영 필수 (스키마·마이그레이션·INSERT·SELECT·row-map 양쪽).
   Postgres는 SELECT 컬럼과 _row_to_session 언패킹 모두 difficulty를 "끝에 append"해 순서 일치.
5. 각 Task는 TDD (실패 테스트 → 실패 확인 → 최소 구현 → 통과 → 커밋). 커밋 메시지는 계획에 명시됨.

환경 주의:
- 저장소 경로에 공백 있음 — 모든 셸 명령 경로를 따옴표로 감쌀 것.
- iCloud .pth 숨김 이슈: pytest 전에
  `find .venv -name "*.pth" -exec chflags nohidden {} \;` 후 `uv run --no-sync` 사용 (메모리 참고).
- 워크트리 venv는 `uv sync --extra dev` 필요 (Task 0 Step 5).
- Task 7의 로컬 스모크는 반드시 임시 DB(WEB_ARENA_DSN=스크래치패드 경로)로 — 141MB 프로덕션
  outputs/web_arena/web_arena.db 오염 금지. 프론트는 http://localhost:8080/ (127.0.0.1 아님, CORS).
- 판정 기준: "no NEW failures" (기존 pre-existing 실패는 허용, 메모리 참고).

완료 후: superpowers:finishing-a-development-branch로 main 병합/PR 옵션을 나에게 제시해줘.
```

---

## 맥락 요약 (프롬프트에 포함할 필요 없음)

- **왜 rebase인가:** 분기점 `7dcfa7a`(difficulty 계획 커밋) 이후 main이 29커밋 앞서 나가
  더 이상 워크트리의 조상이 아님. main 불변으로 워크트리 5커밋을 최신 main 위로 올리는
  가장 깔끔한 방법. 사용자가 rebase 선택.
- **이미 검증된 사실:** main의 `NewGameRequest`에는 이미 `difficulty` 필드가 있고 `new_game`이
  `HumanGameSession`으로 전달까지 함 — 단 (1) UI 셀렉터 없음, (2) DB 태그 없음, (3) 검증 없음(500).
  이 세 갭이 이번 작업의 핵심. 백엔드 난이도→규칙 반영은 easy=단일속성 / hard=AND결합 /
  expert=이력의존으로 이미 동작 확인됨.
- **충돌 파일 상세:** api.py/app.js/index.html/test_api_web_arena.py = main과 함께 수정됨(충돌 위험).
  arena.py/test_arena.py = 클린(자동 적용). Phase 1 파일(persistence 3개 + seeding.py)은 main에서
  미변경이라 계획의 라인 번호가 정확함.
- **DB 스키마 현황:** sessions 테이블에 difficulty 컬럼 없음. SeasonResult에는 difficulty 필드 존재하나
  미영속. season_results.jsonl에는 top-level "difficulty" 키가 있어 seeding에서 그대로 읽음.
- **체크포인트 정합성:** _saveCheckpoint 페이로드에 현재 difficulty가 없어, 캠페인 재개 시 easy로
  회귀하는 버그가 있음 → 계획 Task 5에서 v2로 올리며 저장/복원(구버전은 easy 폴백).
- **현재 브랜치 상태:** 워크트리 tip = 564fc32 (docs 스펙+플랜 커밋 완료). 그 아래 difficulty 5커밋.
  이번 세션에서 서버(8502/8503/8080)는 모두 종료됨.
```

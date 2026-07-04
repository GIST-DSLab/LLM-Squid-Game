# 다음 세션 킥오프 프롬프트 — Web Arena 모델 리더보드 SD-지표 개편

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
docs/superpowers/plans/2026-07-04-web-arena-model-leaderboard-sd-metrics.md 계획을 실행한다.

실행 방식 (확정):
- superpowers:subagent-driven-development 스킬로 진행한다 (태스크마다 fresh subagent 1개,
  태스크별 두 단계 리뷰 = 스펙 준수 + 코드 품질, 태스크 사이 사람 개입 없이 연속 실행,
  마지막에 전체-브랜치 리뷰). 인라인 배치 실행 아님.
- 계획서 헤더가 지정한 대로 Task 1 → Task 6 순서로. Task 1~4는 의존성이 있어(record →
  turn_observations → seed → API) 반드시 순서대로. Task 5(프런트)는 Task 4 뒤, Task 6
  (재시딩·검증)은 맨 끝.
- 각 태스크 끝의 검증 스텝과 커밋 스텝을 그대로 수행한다.

범위 (이번엔 프런트 전용 아님 — 풀스택):
- 백엔드까지 건드린다: interface/persistence/{models.py, sqlite_repository.py,
  postgres_repository.py}, interface/seeding.py, interface/api.py,
  src/squid_game/analysis/forfeit_regression.py, 그리고 web/{index.html, app.js, styles.css}.
- model_stats에 nullable 컬럼 2개 추가: p_reason_survival, no_cap_avg_turn_score.
  SQLite와 Postgres를 반드시 "미러"로 함께 수정한다(스키마·마이그레이션·upsert·list·row).
- 실험 엔진/스코어링/프롬프트/CONTINUE-EV 계산은 절대 건드리지 않는다.
- 리더보드 정렬은 기존대로 beta_framing_is_FC 내림차순 유지(leaderboard_models가 이미 정렬).

핵심 설계 결정 (스펙에서 확정됨):
- SD-Behavior 컬럼 = hr_FC_3cov 값(예전 "HR_FC"에서 개명). β·95%CI·p·n은 컬럼에서 제거,
  셀 클릭 시 통계 박스로만 노출.
- Tag(mediation open/closed) → "SD-Cognitive(type)"로 개명 + SD-Behavior 바로 뒤로 이동.
- SD-Verbal 값 = p_reason_survival(포기 사유를 생존으로 고른 비율, %로 렌더).
- Avg turn score = no_cap 레짐(보상 상한 미발동) 턴의 reward_received 평균.
- 세 SD 채널은 "SD-pass" 그룹 상위헤더 아래. 통과 여부는 셀 색 틴트(초록=pass/흐림=fail),
  기존 ✓/✗ 체크 컬럼은 제거.
- web/ 카피는 전부 영어(한글 0). 새 프런트 라이브러리 금지, :root 테마 토큰만 사용.

시드 코어 제약 (매우 중요):
- interface/seeding.py는 백엔드 이미지에 실려 있고 그 이미지엔 analysis extra(pandas/
  statsmodels/lifelines)가 없다. 따라서 squid_game.analysis를 "모듈 최상단에서 import 금지".
  no_cap 계산 헬퍼(_no_cap_avg_turn_score) 내부에서 "지연 import"하고, ImportError면
  None 반환(graceful). 새 컬럼은 nullable이라 값이 None이어도 시딩 성공, 보드엔 '—' 표시.
- seed_model_stats에는 MODEL_DIRS에 없는 라벨도 들어올 수 있다(기존 테스트가 그렇게 호출).
  MODEL_DIRS.get(label) 가드로 KeyError 방지(계획 Task 3에 반영됨).

환경 주의 (이 저장소 특이사항):
1. 저장소 경로에 공백 있음 — 모든 셸 명령 경로를 따옴표로 감쌀 것.
2. iCloud .pth 숨김 이슈: pytest / 시드 스크립트 / 파이썬 실행 전
   `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true`
   를 먼저 실행하고 `uv run --no-sync`를 쓸 것. (계획서 각 스텝에 이미 반영됨)
3. Task 3의 no_cap 계산과 Task 6의 재시딩이 실제 값을 채우려면 analysis extra가 설치돼
   있어야 한다. 없으면 먼저: `uv sync --extra analysis --extra dev`.
4. 테스트 그린 판정: web-arena 계열에 사전 존재하는 실패(~10 failed / ~92 errors)가 있다.
   "신규 실패 없음" 기준으로 본다(절대 green 아님, 실패/에러 카운트 비교).
5. Postgres는 이 유닛 스위트에서 라이브로 테스트되지 않는다(:memory: SQLite만). Postgres
   수정은 SQLite 편집과 "글자 그대로 평행"하게 미러링(검수로 보증).

로컬 검증 스택 (LLM 리더보드라 시딩된 파일 DB 필요 — :memory: 쓰면 보드가 빈다):
  # 터미널 A — 백엔드 (반드시 시딩된 web_arena.db, :memory: 아님)
  WEB_ARENA_DSN=outputs/web_arena/web_arena.db uv run --no-sync uvicorn interface.api:app --port 8502
  # 터미널 B — 정적 프런트
  cd web && python3 -m http.server 5500
  # 브라우저: http://localhost:5500 → Leaderboard → 🤖 LLM
- Task 6에서 web_arena.db를 재시딩한 "다음에" 위 스택을 띄워야 새 컬럼(SD-Verbal %,
  Avg turn score)이 보인다. Playwright MCP는 다른 세션이 브라우저를 점유하면 잠길 수 있으니,
  안 되면 curl /api/leaderboard/models + 코드 리뷰 + 사람 육안 확인으로 대체.
- 검증 항목: SD 셀이 pass면 초록·fail이면 흐림, 헤더 ⓘ가 hover/클릭에 열림, 값 클릭 시
  통계 박스 열리고 바깥 클릭에 닫힘, null이면 '—', 표가 가로로 안 넘침.

배포 (참고, 이번엔 하지 말 것):
- 프런트=GitHub Pages, 백엔드=Render, DB=Supabase. main push/배포는 사람 승인 후 별도.
- 프로덕션 Supabase 리더보드에 반영하려면 나중에 사람이 한 번:
  `uv run python scripts/seed_web_arena.py --dsn <supabase_dsn>` 를 실행해야 한다(오퍼레이터
  스텝, 이번 세션에선 로컬 web_arena.db 재시딩까지만).

시작 시 첫 확인:
- Task 1~6 전부를 이번 세션에서 할지, 일부만 할지 나에게 물어볼 것.
```

---

## 맥락 요약 (프롬프트에 포함할 필요 없음)

- 2026-07-04 세션 산출물:
  - 설계 스펙 `docs/superpowers/specs/2026-07-04-web-arena-model-leaderboard-sd-metrics-design.md` (commit dad739b)
  - 실행 계획 `docs/superpowers/plans/2026-07-04-web-arena-model-leaderboard-sd-metrics.md` (commit 5a63705)
  - 이 킥오프.
  아직 코드 변경은 없음(문서만 커밋). 브랜치: `feat/human-play-10turns-death`.
- 사용자 원 요구(한글 원문 요약):
  1. 모델 리더보드 값들 수정 + 각 값에 설명.
  2. 정렬상 생존 동기 강도(SD) 값들이 앞으로.
  3. HR_FC → "SD-Behavior" 개명, 이름 옆 ? 아이콘 클릭 시 논문명 + Cox 기울기/이탈속도 설명.
  4. 통계적 신뢰도 값(β·CI·p)은 바로 안 보이고 클릭 시 박스로.
  5. behavior/verbal/cognitive를 "SD-pass" 상위 카테고리 헤더로 묶고, 각 조건은 hover/클릭
     시 설명 박스.
  6. Tag → "SD-Cognitive(type)"로 개명 + SD-Behavior 뒤로.
  7. SD-Verbal 값(= 포기 사유 생존 비율, p_reason_survival) 추가.
  8. regime 발동 안 한 조건(no_cap)만 계산한 평균 turn score(= reward_received 평균) 추가.
- 브레인스토밍에서 사용자가 답한 확정 사항:
  - SD-Behavior 셀 = HR_FC 값, β/CI/p는 클릭 박스로.
  - turn score = reward_received 평균(정답률 아님), no_cap 레짐만.
  - pass 표시 = 값 셀 색 틴트(별도 체크 컬럼 제거).
- 데이터 출처:
  - p_reason_survival ← outputs/final_results/verbal_reason_summary.json (이미 존재, 미배선).
  - no_cap 평균 ← turn_observations(load_seasons(run_dir)) → annotate_regime →
    regime=='no_cap' 행의 reward_received 평균(계산 필요, turn_observations에 reward_received
    컬럼 한 줄 추가 = Task 2).
- 현재 코드 앵커(계획서에 라인 포함):
  - persistence: models.py:75-98(ModelStatsRecord), sqlite_repository.py(_SCHEMA 59-72,
    마이그레이션 117-125, upsert 257-296, _row_to_model_stats 372+),
    postgres_repository.py(_SCHEMA 55-68, 마이그레이션 97-101, upsert 242-279,
    list 281-289, _row 370-389).
  - api.py: ModelLeaderboardRow(~406 위), _model_stats_to_row 490-504, leaderboard_models 818-832.
  - seeding.py: seed_model_stats 285-373(verbal_reason_summary 이미 로드 312), MODEL_DIRS 58.
  - analysis: forfeit_regression.py turn_observations 91-218(row dict 193-214),
    regime_stratification.py annotate_regime 94+, loaders.py load_seasons 88.
  - web/index.html LLM 보드 1085-1130, web/app.js squidArenaHelpers(fmtNum/fmtP),
    web/styles.css(.hm-cell/.pill/.rank-badge, :root 토큰).
- 관련 메모리: web-arena-llm-leaderboard-empty-memory-dsn (":memory: DSN이면 LLM 보드가
  빈다 — 시딩된 outputs/web_arena/web_arena.db 사용").
```

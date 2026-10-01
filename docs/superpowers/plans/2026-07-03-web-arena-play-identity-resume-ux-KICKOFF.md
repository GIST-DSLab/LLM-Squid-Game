# 다음 세션 킥오프 프롬프트 — Web Arena Play 신원·이어하기·UX

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
docs/superpowers/plans/2026-07-03-web-arena-play-identity-resume-ux.md 계획을 실행한다.
관련 스펙: docs/superpowers/specs/2026-07-03-web-arena-play-identity-resume-ux-design.md

실행 방식 (확정):
- superpowers:subagent-driven-development 스킬로 진행한다 (태스크마다 fresh subagent 1개,
  두 단계 리뷰, 태스크 사이 사람 체크포인트). 인라인 배치 실행 아님.
- 계획서의 Task 1 → 12 순서대로. Phase A(백엔드 Task 1-7)를 먼저 끝내고 Phase B(프론트
  Task 8-12)로 간다. Task 8-12는 Task 6/7(백엔드 인증·엔드포인트)에 의존하므로 순서 준수.
- 각 백엔드 태스크는 계획의 TDD 5스텝(실패 테스트 → 실패 확인 → 최소 구현 → 통과 → 커밋)
  그대로. 프론트 태스크는 JS 자동 테스트 하네스가 없으므로 계획에 적힌 "Verify" 관찰로
  검증(백엔드+정적서버 기동 후 브라우저/Playwright MCP).

환경 주의 (이 저장소 특이사항):
1. 저장소 경로에 공백 있음 — 모든 셸 명령 경로를 따옴표로 감쌀 것.
2. iCloud .pth 숨김 이슈: pytest에서 "No module named 'squid_game'"가 나면
   `chflags nohidden .venv/lib/python3.12/site-packages/*.pth` 실행 후 `uv run --no-sync`.
3. 테스트 그린 판정: web-arena 계열에 사전 존재하는 실패(~10 failed/92 errors)가 있다.
   "신규 실패 없음" 기준으로 판단하고, 각 태스크는 자기 테스트 파일만 집중 실행하면 된다.
4. 모든 신규 자동 테스트는 오프라인(SQLite in-memory, FastAPI TestClient)이라 네트워크
   불필요. Postgres(Task 4)는 라이브 DB 테스트 없이 코드 미러 + import 검증만.
5. 새 런타임 의존성 금지 — 비밀번호 해시는 stdlib(hashlib/hmac/secrets)만 사용.

실행 전 확인해야 할 결정 플래그 2개 (계획에 명시됨):
- Task 5: 테스트가 signal_game task의 get_optimal_action()을 가정한다. 실제로 없으면
  `grep -n "def get_optimal_action\|optimal" src/squid_game/tasks/signal_game/*.py`로
  실메서드명 확인 후 교체하거나, "정답 강제" 부분을 제거하고 preview가 submit_action
  리워드(정답 시)와 일치하는지로 완화(계획 Step 1 주석에 지시 있음).
- Task 9: 이어하기 시 다음 게임 new_game도 서버 인증을 거치므로, 재입력 없이 이어가려면
  password를 localStorage 체크포인트에 저장한다(사용자 자기 브라우저 한정, DB/서버엔 없음).
  스펙의 "재입력 불필요"를 따른 것. 이 저장이 꺼려지면 시작 시 나에게 물어봐서 "resume에서
  password 재입력" 대안으로 전환할 것(계획 Task 9 Step 1 주석에 전환법 있음).

절대 원칙:
- 비밀번호 평문을 DB·로그·트레이스·sessions·API 응답 어디에도 남기지 말 것. 저장은
  players.pw_hash + (프론트) 사용자 자기 브라우저 localStorage 뿐.
- baseline(true_baseline) 리워드 계산은 손대지 않는다(범위 밖).
- 사용자 노출 카피는 계획/스펙의 한국어 문구를 verbatim 사용. "Push"/"Pull" 단어 금지.
- SQLite와 Postgres 스키마는 항상 함께 반영.

프론트 검증 기동법:
- 백엔드: `uv run --no-sync uvicorn interface.api:app --port 8502`
- 정적:   `uv run python -m http.server 5500 -d web`  → http://localhost:5500/#play
- CORS 기본 allow-list에 localhost:5500 포함됨. Playwright MCP(browser_navigate/
  browser_snapshot/browser_click) 사용 가능.

시작 시 첫 확인:
- Phase A만 / Phase A+B 전체 중 이번 세션에서 어디까지 할지 나에게 물어볼 것.
- Task 9 password-in-localStorage 방침을 그대로 갈지 확인할 것.
```

---

## 맥락 요약 (프롬프트에 포함할 필요 없음)

- 2026-07-03 브레인스토밍 세션 산출물: 위 스펙 + 계획서 + 이 킥오프. 코드는 미착수.
- 브랜치 `feat/human-play-10turns-death`(워킹트리에 무관한 WIP 다수 있음 — 커밋은 각
  태스크 파일만 add, `git add -A` 금지).
- **왜 이 작업인가:** 현재 Play는 (1) 닉네임에 유니크/보호 없음 → 같은 닉 재플레이가
  덮어쓰기 아니라 중복 리더보드 행 생성, (2) 6판을 한 자리에서 끝내야 함(탭 이탈 시 전체
  리셋), (3) 진행 상황/다음 게임 조건이 눈에 안 띔, (4) hidden-rule UI가 세로로 공간
  과다, (5) push_pull 포기 화면에 리워드 프리뷰 없음. 이 5+1(리더보드 best-per-nickname)을
  해결.
- **결정된 방향(사용자 승인):** 닉네임+비밀번호 경량 로그인(복구 없음, 닉 잠김), 리더보드
  = 닉네임별 최고 캠페인 total, 이어하기 = 게임 경계 localStorage 체크포인트, baseline
  리워드는 현행 유지, 익명 경로 제거(닉+pw 필수).
- **핵심 코드 앵커:** 인증=interface/api.py new_game / 해시=interface/auth.py(신규) /
  players 테이블=interface/persistence/{sqlite,postgres}_repository.py / 리워드 프리뷰
  엔진=interface/human_game.py preview_continue_reward / 프론트=web/{index.html,app.js}
  playScreen 컴포넌트.
- **완료 후 배포:** Phase A+B 완료·리뷰·사람 승인 후 main push → Render(백엔드) 자동
  재배포 + GitHub Pages(web/) 재배포. 배포는 마지막에 한 번.

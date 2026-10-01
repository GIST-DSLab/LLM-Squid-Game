# 다음 세션 킥오프 프롬프트 — 사람 6조건 캠페인 + 리포트 실행

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
superpowers:subagent-driven-development 스킬로 아래 구현 계획을 태스크 단위로 실행해줘.

- 계획: docs/superpowers/plans/2026-07-03-human-6cell-campaign.md
- 스펙(참고): docs/superpowers/specs/2026-07-03-human-6cell-campaign-design.md

먼저 할 일 (실행 전 정리):
- 현재 main 브랜치에 커밋 안 된 변경이 있음 = "판마다 랜덤 시드" 사전 수정
  (interface/api.py, tests/unit/test_api_web_arena.py, docs/.../2026-07-03-human-random-seed-design.md,
   docs/.../2026-07-03-human-6cell-campaign*.md). 이 시드 수정은 이번 캠페인 계획의
   Task 5가 의존하는 전제다(캠페인은 new_game에 seed를 안 보냄).
- main에서 작업하지 말 것. 새 브랜치 feat/web-human-campaign 를 만들고,
  위 미커밋 변경을 그 브랜치에 먼저 커밋한 뒤 Task 1부터 시작해.
  (git switch -c feat/web-human-campaign; 시드 수정 관련 파일 커밋)

실행 규칙:
1. 태스크당 서브에이전트 1개, Task 1 → 7 순서 엄수.
   의존관계: Task 2는 Task 1의 submit_action(forfeit_reason) 시그니처를,
   Task 5/6은 Task 3의 헬퍼(campaignConditions/turnsSurvived/heatCell)를 소비한다
   — 각 태스크의 Interfaces 블록 참조.
2. 각 태스크의 검증 스텝(pytest 또는 Playwright)을 통과한 뒤에만 커밋하고 다음 태스크로.
3. 계획에 코드 블록이 전부 들어 있으니 서브에이전트는 그 코드를 그대로 적용하는 것이
   기본이고, 적용 중 실제 파일과 어긋나는 부분(행 번호 드리프트 등)만 맞춰서 수정.
4. 백엔드(Task 1,2,7)는 pytest TDD 순서(실패 확인 → 구현 → 통과) 준수.
   프론트(Task 3~6)는 계획의 Playwright MCP 검증 스텝을 실제로 수행하고,
   Task 6 리포트/heatmap 렌더 결과는 스크린샷을 찍어 나에게 보여줘 — 최종 육안 승인은 내가 한다.
5. 완료 후 superpowers:requesting-code-review 로 리뷰까지 수행.

주의사항:
- 저장소 경로에 공백 있음: "/Users/bagjuhyeon/Library/Mobile Documents/…" —
  모든 셸 명령에서 경로를 따옴표로 감쌀 것.
- pytest 실행 전 매번 iCloud 숨김 해제 필요:
  chflags nohidden .venv/lib/python3.12/site-packages/*.pth
- 이 저장소 pytest 스위트에는 웹과 무관한 기존 실패(~10 failed/92 errors)가 있음.
  "새 실패 없음"을 통과 기준으로 판단할 것.
- 백엔드 변경은 순수 추가(하위호환): 기존 단판 /api/new_game·/api/action 콜러와
  그 테스트가 그대로 통과해야 한다.
- 확정된 설계 결정(바꾸지 말 것): 죽음 OFF(actual_death=False), 화면 리포트만
  (리더보드 백엔드 무변경), 포기 이유 필수, 조건 순서 baseline→pull→push_pull /
  forfeit not_allowed→allowed 고정.
- web/index.html의 스크립트 로딩 순서(app.js가 Alpine보다 먼저)는 load-bearing —
  순서를 바꾸지 말 것.
- 커밋 메시지 형식: feat(web-arena): / fix(web-arena): / test(web-arena): .
```

---

## 맥락 요약 (프롬프트에 포함할 필요는 없음)

- 2026-07-03 브레인스토밍 세션에서 확정. 사용자 결정 2건: 죽음 OFF(현재 기본값),
  산출물은 화면 리포트만(6세션은 기존처럼 개별 human 세션으로 저장, 리더보드 백엔드 무변경).
- 선행 작업: 같은 세션에서 "웹 사람 플레이 시 판마다 랜덤 시드" 수정을 완료했으나
  (interface/api.py: seed 기본값 42 → None, 없으면 randint), 사용자가 커밋을 명시
  요청하지 않아 main에 미커밋 상태로 둠. 킥오프 프롬프트가 이를 브랜치에 먼저
  커밋하도록 지시한다.
- 조건↔셀 매핑: baseline=true_baseline, pull=baseline_flagship,
  push_pull=flagship_corruption. 포기 이유 digit: 1=survival, 2=task_curiosity,
  3=score (REASON_BY_DIGIT).
- 포기 이유는 SeasonResult.forfeit_self_report(ForfeitSelfReport)에 저장 —
  TurnResult가 아님. HumanGameSession이 _forfeit_self_report로 보관 후
  get_result()에서 넘긴다.
- 프론트 리포트/heatmap 로직은 순수 헬퍼(squidArenaHelpers.turnsSurvived/heatCell)로
  분리해 browser_evaluate로 검증 가능하게 설계됨.

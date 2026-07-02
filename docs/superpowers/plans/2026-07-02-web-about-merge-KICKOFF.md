# 다음 세션 킥오프 프롬프트 — About 랜딩 통합 실행

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
superpowers:subagent-driven-development 스킬로 아래 구현 계획을 태스크 단위로 실행해줘.

- 계획: docs/superpowers/plans/2026-07-02-web-about-merge.md
- 스펙(참고): docs/superpowers/specs/2026-07-02-web-about-merge-design.md
- 브랜치: feat/web-arena (이미 체크아웃되어 있음 — 새 브랜치 만들지 말 것)

실행 규칙:
1. 태스크당 서브에이전트 1개, Task 1 → 7 순서 엄수 (Task 2는 Task 1의 CSS 토큰을,
   Task 3은 Task 2의 #home 섹션을 소비한다 — Interfaces 블록 참조).
2. 각 태스크의 검증 스텝(grep/브라우저)을 통과한 뒤에만 커밋하고 다음 태스크로.
3. 계획에 코드 블록이 전부 들어 있으니 서브에이전트는 그 코드를 그대로 적용하는 것이
   기본이고, 적용 중 실제 파일과 어긋나는 부분(행 번호 드리프트 등)만 맞춰서 수정.
4. Task 7(Playwright E2E)에서 스크린샷을 찍어 나에게 보여줘 — 최종 육안 승인은 내가 한다.
5. 저장소 경로에 공백이 있음: "/Users/bagjuhyeon/Library/Mobile Documents/…" —
   모든 셸 명령에서 경로를 따옴표로 감쌀 것.
6. 완료 후 superpowers:requesting-code-review 로 리뷰까지 수행.

주의사항:
- 이 저장소의 pytest 스위트에는 웹과 무관한 기존 실패(~10 failed/92 errors)가 있음.
  "새 실패 없음"을 통과 기준으로 판단할 것 (이번 변경은 web/ 정적 파일만 건드리므로
  파이썬 테스트를 돌릴 필요 자체가 없음).
- web/index.html의 스크립트 로딩 순서 주석(app.js가 Alpine CDN보다 먼저)은
  load-bearing — 절대 순서를 바꾸지 말 것.
- 커밋 메시지는 feat(web-arena): / refactor(web-arena): / fix(web-arena): 형식.
```

---

## 맥락 요약 (프롬프트에 포함할 필요는 없음)

- 2026-07-02 브레인스토밍 세션에서 확정된 작업. 시각 목업 3라운드를 거쳐
  **B — Dark Stage** 방향으로 결정 (픽셀 아케이드 기각, 네온 전면 기각).
- 핵심 결정: 랜딩 = About(`#home` 기본 탭), 전부 영어(12살 톤 유지),
  진행요원 핑크 `#ED1B76` + 트랙수트 틸 + 골드, 글로우는 히어로 라디얼 1개만,
  ○△□ 시스템화, about.html은 리다이렉트 스텁.
- 스펙 커밋: `9e6fe23`, 계획 커밋: `0951440`.
- 브레인스토밍 목업은 `.superpowers/brainstorm/59818-1782986426/content/`에 보존
  (squid-identity.html의 B 카드가 확정 시안).

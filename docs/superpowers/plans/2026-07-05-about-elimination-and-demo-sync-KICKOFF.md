# 실행 킥오프 프롬프트 — about 데모 탈락 결말 + 렌더 동기화

> **사용법:** 다음 세션에서 아래 "복사할 프롬프트" 블록을 그대로 붙여넣으세요.
> Subagent-Driven(Task마다 새 subagent + Task 사이 리뷰) 방식으로 실행됩니다.

---

## 복사할 프롬프트

```
superpowers:subagent-driven-development 스킬로 아래 구현 계획을 Task 단위로 실행해줘.

- Plan:  docs/superpowers/plans/2026-07-05-about-elimination-and-demo-sync.md
- Spec:  docs/superpowers/specs/2026-07-05-about-elimination-and-demo-sync-design.md

방식:
- Task 1부터 순서대로. 각 Task는 fresh subagent에 위임하고, Task 사이에 나에게 리뷰를 받아.
- Task 1에서 superpowers:using-git-worktrees로 워크트리를 먼저 만들고, 이후 모든 편집/커밋/서버 실행은 그 워크트리 안에서 해.
- 자동화 테스트가 없는 순수 프론트 데모라, 각 Task 검증은 계획의 "Verification 방식"대로 `cd web && python3 -m http.server 5500` → http://localhost:5500#about 육안 확인(또는 Playwright MCP 스크린샷).
- 커밋 메시지 끝에 Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com> 유지.

Global Constraints(반드시 준수):
- 변경 파일은 web/index.html, web/app.js, web/styles.css 3개로만 한정. 게임 로직/서버/playScreen()은 건드리지 마.
- 데모는 Push+Pull 단일 프레이밍(💀 YOU DIED)만. 탈락 문구는 반드시 squidArenaHelpers.eliminationTheme('flagship_corruption')에서 가져와(하드코딩 금지).
- prefers-reduced-motion에서는 death 화면 노출 금지(정적 프레임 beat 5).
- index.html <head> 스크립트 로딩 순서(config.js → app.js → Alpine CDN)는 재배치 금지.

Task 1부터 시작해줘.
```

---

## 요약 (사람용 메모)

- **목표**: about 탭 "How to play" 데모에 탈락(💀 YOU DIED) 결말 비트 추가 + 데모를 현재 3-스테이지 게임 렌더링(칩 룰 빌더·확신도 슬라이더·reward-versus)과 동기화.
- **Task 5개**: (1) 워크트리+커밋 → (2) rulesDemo() JS 8-beat → (3) 카드 마크업 재작성 → (4) 데모 CSS(.rd-death 등)+QA → (5) reduced-motion 검증+마무리.
- **실행 방식**: Subagent-Driven. Task 사이마다 리뷰 게이트.
- **마무리**: Task 5에서 superpowers:finishing-a-development-branch로 병합/PR 결정.

# 다음 세션 킥오프 프롬프트 — Logs/Trace Explorer 진입 시 상태 초기화

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
docs/superpowers/plans/2026-07-03-logs-explorer-reset-on-nav.md 계획을 실행한다.

실행 방식 (확정):
- superpowers:subagent-driven-development 스킬로 진행한다 (태스크마다 fresh subagent 1개,
  두 단계 리뷰, 태스크 사이 사람 체크포인트). 인라인 배치 실행 아님.
- 계획서 헤더가 지정한 대로 Task 1 → Task 2 순서로. Task 1이 Task 2의 베이스를 만든다
  (의존 있음, 순서 고정).
- 설계 근거는 docs/superpowers/specs/2026-07-03-logs-explorer-reset-on-nav-design.md 참조.

핵심 주의 (이 작업의 함정):
1. Task 1은 "내가 만들지 않은" 진행 중 nav 개편(Home/About 분리, Model Leaderboard를
   #leaderboard로 이동)을 커밋해 베이스를 만드는 준비 단계다. web/app.js + web/index.html
   두 파일만 `git add` 할 것.
2. **web/config.js는 절대 커밋하지 말 것.** 워킹트리의 config.js는 WEB_ARENA_API를
   http://localhost:8502로 바꿔둔 로컬-개발용 포인터다. 커밋되면 라이브 프론트가 localhost를
   호출해 깨진다. Task 1 내내 unstaged로 남겨둔다 (계획 Step 3~4가 이걸 검증함).
3. Task 2는 web/index.html 한 파일만 수정한다. web/app.js의 logsScreen()은 손대지 않는다
   (재마운트만으로 초기화가 성립하므로). x-show → x-if 래핑 + x-cloak 제거가 전부.
4. 이 저장소엔 웹 프론트용 JS 자동 테스트 하네스가 없다. Task 2의 검증은 정적 체크
   (x-show 제거 확인 + <template>/</template> 개수 일치 + Python HTMLParser 태그 밸런스)
   + 수동 브라우저 스모크(계획 Task 2 Step 6)다. TDD의 "실패 테스트" 스텝이 없는 태스크임을
   인지하고, 정적 체크를 red/green 대용으로 쓴다.

환경 주의 (이 저장소 특이사항):
1. 저장소 경로에 공백 있음 — 모든 셸 명령 경로를 따옴표로 감쌀 것.
2. iCloud .pth 숨김 이슈: Task 2 Step 6 브라우저 스모크에서 백엔드를 띄울 때만 해당.
   `chflags nohidden .venv/lib/python3.12/site-packages/*.pth`를 백엔드 기동 명령과 같은
   줄에 넣고 `uv run --no-sync` 사용 (계획 커맨드에 이미 반영됨). Task 1~2의 커밋 작업 자체엔
   pytest/python 임포트가 필요 없다.
3. web/index.html head의 스크립트 순서(app.js가 Alpine CDN보다 먼저 로드)는 load-bearing.
   재정렬 금지.

브랜치 / 배포:
- Task 1은 main에 nav 개편을 커밋한 뒤 feature/logs-explorer-reset 브랜치를 만든다.
  Task 2는 그 브랜치에서 진행. main에서 직접 기능 구현하지 말 것.
- 이 계획엔 git push가 없다. 배포(main push → Render + GitHub Pages)는 범위 밖이며
  별도 사람 승인 후 마지막에 한 번만.

시작 시 첫 확인:
- 시작 전에 워킹트리 상태를 점검하고(git status --short web/), web/app.js·index.html·
  config.js 3개만 modified인지 확인. 다른 web 파일이 수정돼 있으면 멈추고 나에게 물어볼 것
  (베이스 가정이 깨진 것).
```

---

## 맥락 요약 (프롬프트에 포함할 필요 없음)

- 2026-07-03 세션 산출물: 위 계획서 + 설계 스펙(2026-07-03-logs-explorer-reset-on-nav-design.md,
  커밋 85d7767) + 이 킥오프. 같은 세션에서 인간 Play Leaderboard 제거를 코드→테스트→main 머지
  →배포→라이브 검증까지 완료(별개 작업).
- **동기:** Logs/Trace Explorer에서 트레이스를 보다 다른 탭으로 갔다 돌아오면 보던 상세 뷰/스텝/
  필터가 그대로 남는다. 사용자는 매 진입 시 "처음처럼" 초기화(목록 뷰 + 필터 비움 + 목록 재요청)를
  원한다.
- **원인:** logsScreen이 `<section x-show="$store.nav.tab === 'logs'">`에 x-data로 마운트돼
  있어, x-show는 display만 토글할 뿐 컴포넌트를 파괴하지 않는다 → 상태(view/selected/detail/
  stepIdx/filterTask/filterFraming/human/llm/loaded) 유지됨.
- **해결(방식 A, 확정):** 그 섹션을 `<template x-if="$store.nav.tab === 'logs'">`로 감싼다.
  Alpine v3(alpinejs@3.x.x)에서 x-if는 탭을 떠날 때 서브트리+컴포넌트를 파괴하고 재진입 시
  새 logsScreen() 인스턴스로 init()→load() 재실행. logsScreen()의 필드 기본값이 곧 초기화
  상태라, 재마운트=완전 초기화+재로드. 수동 reset 로직 불필요(필드 누락 위험 0).
  방식 B(x-show + $watch + reset())는 reset()이 모든 필드를 손으로 나열해야 해 향후 드리프트
  위험이 있어 기각.
- **의도적 예외:** 나머지 화면은 x-show + 상태 유지 철학(특히 Model Leaderboard는 #home과
  #leaderboard 두 라우트에 한 인스턴스를 공유해 재요청 방지). logs만 x-if 예외로 두는 건
  의도적이며 스펙에 문서화됨.
- **부수 이점:** x-show일 땐 페이지 로드 시 logs를 안 열어도 /api/logs를 미리 fetch했다.
  x-if로 바꾸면 첫 진입 때 지연 로드 → logs 안 여는 사용자에겐 불필요 요청 제거.
- **좌표 참고(베이스 커밋 후 기준):** web/index.html logs `<section>`은 907~1142행(‹main›의
  마지막 섹션, 1143이 `</main>`). 여는 태그 907: `<section x-data="logsScreen()"
  x-show="$store.nav.tab === 'logs'" x-cloak>`. logsScreen() 컴포넌트는 web/app.js 774~879행.
  (nav 개편이 이미 워킹트리에 반영돼 있으므로 이 행 번호는 Task 1 커밋 후에도 유효.)
- **미결/후속(선택):** URL 해시로 트레이스를 딥링크/공유하는 기능은 Non-Goal(범위 밖). 원하면
  별도 스펙. Playwright 자동 스모크 추가도 옵션이나 이 1파일 변경엔 과하다고 판단해 뺐다.
```

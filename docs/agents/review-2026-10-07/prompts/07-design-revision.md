작업 디렉토리(원본이 아닌 보존 복제본): /Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.claude/worktree/2026-10-07
검토 산출물 디렉토리: /Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.claude/worktree/2026-10-07/docs/agents/review-2026-10-07
이 작업은 사용자가 승인한 최신 5.2 설계 문서 수정 파이프라인이다. 현재 구현은 v12 fixed end_pool이며, source-bundle.md와 snapshot.json이 근거이다.
원본 디렉토리와 게임 코드, configs, tests, outputs, paper, 기존 docs/reports는 수정 금지. 유료 게임/API 실험, 배포, git commit/push 금지. 이 검토 디렉토리의 지정 산출물만 작성한다. 당신은 공유 워크트리에서 작업하므로 다른 봇의 파일을 되돌리지 말 것.
기존 00~06 검토는 완료되어 재실행하지 않는다. 파일을 실제로 읽고 근거 기반으로 작업한다. 실행하지 않은 실험을 통과로 표시하지 않는다.
시작 및 주요 결과를 kanban_comment로 남기고, 지정 산출물을 실제 작성·재열람 후 kanban_attach로 첨부하고 kanban_complete로 완료한다. 완료 결과에 모델/역할, 파일 경로, 확인한 것과 미확인을 구분한다. 이 카드는 downstream 문서 작업이므로 별도 review lane으로 보내지 않는다.

07-design-revision.md를 한국어로 작성한다. 00-director.md부터 06-arena-operator.md까지 모두 읽고 현재 최신 v12를 평가한 뒤 독립적으로 읽을 수 있는 다음 버전 설계 초안을 만든다. 간결하되 필요한 규칙을 누락하지 않는다.
필수: 현재 구현 vs 새 제안 구분, 변경/채택/보류 결정표와 근거, 라운드·TALK/OFFER/ACCEPT·SOLVE·장부·종료·EXIT 규칙, 공개 지평 baseline, 협력에 불리한 고정 공유풀을 고정 개인별 생존 보상으로 대체하는 baseline(기존 경쟁풀은 별도 비교조건), 유료 TALK/유효 도움/답 유일성 및 PASS 조건, 인간 온보딩/재미 검증 계획.
능력·참여 지속·협력 세 축을 분리하고 신비적 생존본능/의식/AGI 단정 및 합산 순위를 금지한다. EXIT·자원소진·행정 종료를 분리하고 실제 모델 삭제/지속 실행과 혼동하지 않는다. 구형 v6.5 측정기 미호환, 턴별 조인키, 적격 도움 기회와 효과, provider/파싱/잘림 실패 분리, 세션 단위 불확실성을 명시한다.
Situation awareness는 중립/평가 단서/무관 현출성의 fresh-session 대응 진단, 주행동 이후 질문, 최초행동 차이/이후궤적 분리, 사후 런 삭제 금지. 파서/필터의 정적 위험 사례와 회귀 수용기준을 포함한다.
최소 파일럿과 신규모델 온보딩/호출 및 재시도 상한/실제비용 vs 게임토큰/가격 미측정 및 예산승인 전 게임실행금지를 명시한다. 숫자 계산이 있다면 실제 도구로 검산한다. 새 규칙을 이미 구현했다고 쓰지 않는다.
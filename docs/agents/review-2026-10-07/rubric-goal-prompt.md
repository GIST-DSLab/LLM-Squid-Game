목표: rubric v1.0의 G01–G11 D 전체 2 및 미해결 Critical 0으로 DESIGN_ACCEPTED를 달성한다. 문서를 썼다는 이유로 완료하지 말고, 독립 평가에 실패하면 승인 범위 안에서 수정→검증을 계속한다.
작업 디렉토리: /Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.claude/worktree/2026-10-07
산출물: /Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.claude/worktree/2026-10-07/docs/agents/review-2026-10-07
rubric SHA-256: 4069c7e8d3ffffc0c7c81058c30be740575d1cb9b8933baf3311e59714043579
현재 범위는 설계 문서만. 원본 프로젝트·게임 엔진·configs/squid5·tests·outputs·paper·rubric 기준·완료 검사기·프로필 수정, 게임/API 실험·인간 모집·학습·배포·commit/push 금지. 설계의 실행/인간 검증은 E=U로 남기고 후속 목표를 보존한다. 봇의 설계 검토 호출은 승인된 작업이다.
이 카드는 네이티브 goal-mode 조율 카드다. 먼저 root rubric.md, 공통 arena-workflow, 07/08/09/10 최신 파일과 기존 Kanban 결과를 읽고 현재 미충족을 기록한다. 기존 00–06은 재실행하지 않는다. 08의 G01 무해결 DONE/PASS 최대 보상 반례를 한계 문장만으로 해결 처리하거나 사용자 목표를 축소하지 않는다.

실제 반복 절차:
1. 기존 최종 설계(09) 다음에 arena-verifier 독립 평가 카드를 생성한다. 평가 카드에는 이 body의 범위, rubric 경로/해시, 지정 최종 파일, 아래 JSON/검사 계약을 빠짐없이 복사한다. assignee=arena-verifier, model=gpt-6-astra, provider=openai-codex, effort=high, workspace=현재 dir, max_runtime=900, max_retries=1. 카드별 출력 파일을 별도로 지정한다.
2. 평가자가 rubric-evaluation.md와 rubric-evaluation.json을 작성하도록 한다. 실제 작성자/평가자 profile·session_id는 카드 run/세션 기록으로 확인하고 모르면 조율자에게 요청한다. 추정 ID나 결과를 만들지 않는다. G01–G12 전 행과 D/E, 근거 절/파일 해시를 기록한다. 평가 카드 자체의 완료와 프로젝트 합격을 구분한다.
3. REVISE이면 같은 평가를 재호출만 하지 말고, 미충족 ID·반례·수용 기준을 담은 game-designer 수정 카드를 만든다. model=gpt-6.1-sol high, workspace=현재 dir, max_runtime=900. 기존 문서를 덮어쓰지 말고 새 revision 파일을 지정한다. 그 수정 카드를 parent로 한 새 arena-verifier 평가 카드를 연결한다. 필요할 때만 construct-auditor/social-dynamics/metric-analyst/beta-tester/arena-operator를 해당 논점에 호출한다. 모두 실제 기존 프로필이며 다른 프로필을 생성하지 않는다.
4. 조율 카드 자신을 자식의 선행 parent로 연결해 교착하지 않는다. 독립 자식 카드 ID를 조율 카드 댓글에 남기고 native dispatcher로 실행되게 한다. 기다리는 동안 상태를 도구로 확인하고 진전/문제/인계를 댓글로 남긴다. 중복 생성하지 않는다. 각 봇은 자기 지정 파일만 쓰게 한다. 터미널에서만 보이는 별도 모델 실행은 금지한다.
5. 평가 JSON의 artifact 해시가 최신 설계를 가리키는지 확인하고, 작업 디렉토리에서 실제로 `python3 configs/hermes-bots/check_rubric.py docs/agents/review-2026-10-07/rubric-evaluation.json --root . --gate DESIGN_ACCEPTED`를 실행한다. 종료 코드 0일 때만 이 조율 카드를 kanban_complete한다. 검사 출력·평가서·최종 문서·결정 기록을 첨부한다. native goal judge가 불가해도 이 검사를 생략하지 않는다. 보고/검사기/평가 기준을 통과하려고 바꾸지 않는다.
6. 실패이면 수정 루프로 돌아간다. 예산/외부 입력/사용자 목표 결정이 실제 필요한 경우 이유·미완료 ID·재개 조건을 기록하고 미완료로 block한다. 두 번 검토했다거나 시간이 지났다고 성공 처리하지 않는다. 상한은 goal turn 20, 전체 3600초. 실제 게임/인간 검증 예산을 자동으로 늘리지 않는다.

평가자는 configs/hermes-bots/check_rubric.py와 rubric.md의 JSON 계약을 읽는다. PASS 점수는 독립 검토 근거가 있을 때만 기록하며, 검사기가 타당성 자체를 증명하지 않는다는 점을 명시한다. 최종 STATUS.md에는 DESIGN_ACCEPTED 여부와 Phase1 실증/릴리스 미완료를 분리한다. 성공 조건은 설계 게이트 전체 충족이며 “검토 수행” 또는 “후속 계획 작성”만으로 충족되지 않는다.

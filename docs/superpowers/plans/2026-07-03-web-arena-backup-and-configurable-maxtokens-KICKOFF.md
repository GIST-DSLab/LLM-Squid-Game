# 다음 세션 킥오프 프롬프트 — Web Arena 백업 스크립트 + 설정 가능한 arena max_tokens

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
docs/superpowers/plans/2026-07-03-web-arena-backup-and-configurable-maxtokens.md 계획을 실행한다.

실행 방식 (확정):
- superpowers:subagent-driven-development 스킬로 진행한다 (태스크마다 fresh subagent 1개,
  두 단계 리뷰, 태스크 사이 사람 체크포인트). 인라인 배치 실행 아님.
- 계획서 헤더가 지정한 대로 태스크를 위→아래 순서로. 단 Part A(백업 스크립트)와
  Part B(설정 가능한 max_tokens)는 서로 독립이다. Part A → Part B 순서 권장.
- 각 태스크는 TDD 5스텝(실패 테스트 → 실패 확인 → 최소 구현 → 통과 → 커밋) 그대로.

환경 주의 (이 저장소 특이사항):
1. 저장소 경로에 공백 있음 — 모든 셸 명령 경로를 따옴표로 감쌀 것.
2. iCloud .pth 숨김 이슈: pytest/python 실행 시
   `chflags nohidden .venv/lib/python3.12/site-packages/*.pth`를 같은 명령에 넣고
   `uv run --no-sync` 사용. (계획서 커맨드에 이미 반영돼 있음)
3. 테스트 그린 판정: web-arena 계열에 사전 존재하는 실패(~10 failed/92 errors)가 있다.
   "신규 실패 없음" 기준으로 판단하고, 각 태스크는 자기 테스트 파일만 집중 실행하면 된다.
4. 계획의 모든 자동화 테스트는 오프라인(httpx.post monkeypatch, SQLite in-memory)이라
   ollama 서버도 네트워크도 필요 없다. Part A2의 "라이브 스모크"만 실제 Supabase 접속.

시크릿:
- Supabase DSN(비밀번호 포함)은 코드/커밋/계획에 넣지 말 것. Part A2 라이브 스모크가
  필요하면 나(사람)에게 DSN을 요청해 셸 인자로만 쓰고, 산출 backup .db는 로컬에만 둔다.
  (DSN 구조: postgresql://postgres.ptiifyeixluosuyuhqcu:<pw>@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres)
- Part A1(유닛테스트)와 Part B 전체는 시크릿 불필요.

배포:
- Part B 완료 후 main push하면 Render가 백엔드(B1·B2) 자동 재배포, Pages 워크플로가
  web/(B3) 재배포. Pages가 deployment_queued에서 타임아웃하면 Actions 탭에서 재실행
  (알려진 간헐 이슈). 배포는 마지막에 한 번, 사람 승인 후.

시작 시 첫 확인:
- Part A만 / Part B만 / 둘 다 중 무엇을 이번 세션에서 할지 나에게 물어볼 것.
```

---

## 맥락 요약 (프롬프트에 포함할 필요 없음)

- 2026-07-03 세션 산출물: 위 계획서 + 이 킥오프. 직전 세션에서 Web Arena를 라이브 배포
  완료(프론트 https://gist-dslab.github.io/LLM-Squid-Game/, 백엔드 Render Singapore,
  DB Supabase Seoul, 720세션 시드됨).
- **Part A (백업 스크립트)** 동기: 배포 사이트의 human/LLM 플레이는 Supabase에만 durable
  하게 저장된다(git 저장 안 됨, 로컬에도 없음). 시드된 720세션은 outputs/final_results/
  에서 재현 가능하지만, 라이브에서 새로 생긴 플레이는 원본이 없으므로 주기적으로 로컬로
  내려받아야 유실 방지. `scripts/seed_web_arena.py`의 정반대 방향 = get_repository로
  Postgres 읽어 SQLite로 mirror. Repository 인터페이스가 driver-agnostic이라 20~30줄.
- **Part B (설정 가능 max_tokens)** 동기: arena BYOE 기본 max_tokens=2048이 reasoning
  모델(gpt-oss, deepseek, glm, qwen3 등)엔 너무 작다. 추론 토큰이 예산을 소진하면
  content가 빈 채 잘려(finish_reason=length) RemoteProvider가 "no text answer"로 거부.
  직전 세션에서 gpt-oss:20b-cloud 로컬 테스트가 이 이유로 turn 1 probe에서 실패 →
  8192로 임시 상향하니 15턴 완주(45콜, final_score≈7458, RI/thinking 정상 캡처)했다.
  그 하드코딩은 되돌렸고(원상복구 커밋 안 함, 워킹트리 clean), 대신 이 계획대로 caller가
  값을 지정하도록 만든다. runner.py:370이 provider_config.max_tokens를 이미 agent로
  전달하므로 _arena_config_dict의 provider_config에 값만 흘리면 됨.
- arena 테스트 stub 패턴: tests/integration/test_arena.py가 interface.remote_provider.
  httpx.post를 monkeypatch하고 modulo-3 카운터로 task/probe/forfeit 응답을 순환 반환.
  B1 테스트는 그 fake_post의 json= body에서 max_tokens를 캡처해 assert.
- Ollama 참고(계획엔 불필요, 배경만): 계정의 직접 클라우드 추론 API 키는 401(인증)로 막혀
  있고, 로컬 ollama 서버(localhost:11434, cloud 로그인됨)를 프록시로 써야 실모델이 돈다.
  배포된 Render 백엔드는 그 localhost에 못 닿으므로, 공개 BYOE 테스트는 공개 엔드포인트
  필요. 이건 계획 실행과 무관.
- 미결(선택): outputs/ 가 .gitignore에 없음 — 실수 커밋 방지로 outputs/web_arena/ 추가
  고려. web/DEPLOY.md의 오리진 표기가 아직 irregular6612.github.io(실제는 gist-dslab).
  둘 다 급하지 않음.

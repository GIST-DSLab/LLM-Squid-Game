# 다음 세션 킥오프 프롬프트 — Render+Supabase+Pages 배포 실행

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
Web Arena를 외부 접속 가능하게 배포한다. 계획대로 진행해줘.

- 계획: docs/superpowers/plans/2026-07-02-render-supabase-deploy.md
- 상위 레퍼런스: web/DEPLOY.md
- 조합(확정): Render(Singapore) 백엔드 + Supabase(Seoul) DB + GitHub Pages 프론트.
  전부 무료(0원). Fly.io는 카드/과금 이슈로 기각됨.

진행 방식:
1. 이건 subagent-driven이 아니라 "대화형 체크리스트"다. 클라우드 대시보드 조작과
   시크릿 입력은 내가(사람이) 하고, 너는 각 단계를 안내하고 코드 변경분만 처리해.
2. 시작하자마자 첫 질문: 브랜치 전략 확정 —
   (a) feat/web-arena를 main에 병합 후 배포 (권장, 인프라가 main을 가리킴), 또는
   (b) 브랜치 유지 채로 Render branch 변경 + Pages 수동 실행.
3. 순서는 계획의 Phase 0→5. 각 Phase에서 "사람이 할 일"은 명령/클릭을 구체적으로
   불러주고, 내가 산출값(Supabase DSN, Render URL)을 주면 그걸로 다음 코드 변경을 해.
4. Phase 0(web/assets 커밋)은 배포 블로커니 반드시 먼저.
5. 저장소 경로에 공백 있음 — 모든 셸 명령 경로를 따옴표로 감쌀 것.
6. iCloud .pth 숨김 이슈: 시드/pytest 등 파이썬 실행 시
   `chflags nohidden .venv/lib/python3.12/site-packages/*.pth`를 같은 명령에 넣고
   `uv run --no-sync` 사용 (메모리 참고).
7. 시크릿(Supabase 비밀번호/DSN)은 코드/커밋에 넣지 말 것 — 대시보드 env로만.

주의:
- 프론트 오리진은 https://irregular6612.github.io, CORS는 그걸 허용.
- Render free는 15분 후 슬립 → 첫 요청 ~50초(정상, "waking up" UI가 처리).
- tiktoken이 기동 시 vocab을 받으므로 첫 기동이 느릴 수 있음 — 실패하면 계획의
  "함정 1"대로 TIKTOKEN_CACHE_DIR 베이킹.
- 시드 소스는 outputs/final_results/ (로컬에 있어야 함). 없으면 계획의 "대안"대로
  기존 outputs/web_arena/web_arena.db(SQLite)를 Postgres로 옮기는 스크립트를 만들어.
```

---

## 맥락 요약 (프롬프트에 포함할 필요 없음)

- 2026-07-02 세션 결정: 완전 무료 우선 → Render Singapore + Supabase Seoul + Pages.
  Fly.io(Tokyo)는 지연시간 최적이나 카드 필수 + 사용량 과금이라 "보장된 무료" 아님 →
  기각. 사용자 선택: "Render Singapore (완전 0원)" + "Supabase (Seoul 리전)".
- 저장소에 render.yaml + Dockerfile + .dockerignore + DEPLOY.md +
  deploy-pages.yml이 이미 있어 새 인프라 파일 불필요 (WP5 산출물).
- 검증 완료: PostgresRepository가 CREATE TABLE IF NOT EXISTS로 스키마 자동 생성;
  seed_web_arena.py가 get_repository(dsn)로 postgres DSN 직접 시드; Pages 워크플로는
  main 푸시(web/**) 또는 수동 트리거.
- 미결 연결 항목: About-merge 브랜치(feat/web-arena, 8 커밋)의 finish 결정
  (keep/PR/merge)이 아직 열려 있음 — 배포 브랜치 전략과 함께 확정하면 됨.
- 현재 로컬에 8788(정적)/8502(백엔드) 서버가 떠 있을 수 있음 — 배포와 무관, 정리 가능.
```

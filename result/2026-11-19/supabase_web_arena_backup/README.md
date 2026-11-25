# Supabase 백업 — 옛 웹 아레나 DB (2026-11-19)

Supabase 프로젝트 `LLM Squid Game`(ref `ptiifyeixluosuyuhqcu`, ap-northeast-2)의 `public` 스키마 전체.
옛 웹 아레나(Render `squid-game-web-arena-api`, `WEB_ARENA_DSN`, 태그 `legacy-2026-09-22`의 엔진)가 쓰던 DB다.
Render의 `squid5-web5-api`는 DSN 없이 SQLite(임시 디스크)를 써서 남은 데이터가 없었다.

받은 방법: 일시정지된 프로젝트를 복원한 뒤 Management API의 SQL 엔드포인트로 표마다 `row_to_json`(ctid 순, 400행씩).
DB 비밀번호·Docker 없이. 행 수는 `manifest.json`이 DB의 `count(*)`와 대조한 값이다(모두 일치).

| 파일 | 내용 |
|---|---|
| `sessions.jsonl` | 748행. `source`: llm 720(Gemini-2.5-flash · Qwen3-Next-80B · GPT-OSS-20B · Nemotron-3-Nano-30B 각 180), human 28(2026-07 ~ 09-02, 사람이 웹에서 한 판) |
| `turns.jsonl` | 8,470행(140 MB). 세션의 턴마다 관찰·행동·원문 응답·목숨 |
| `players.jsonl` | 12행. 닉네임과 비밀번호 해시(`pw_hash`) — **공개 저장소에 올리지 말 것** (git 무시, 이 디스크에만: `.gitignore`) |
| `model_stats.jsonl` | 4행. 모델별 리더보드 통계 |
| `schema.json` | 열(타입·기본값), 제약(키), 인덱스 — 다시 만들 때 |
| `manifest.json` | 표마다 DB 행 수와 저장 행 수, 저장 시각 |

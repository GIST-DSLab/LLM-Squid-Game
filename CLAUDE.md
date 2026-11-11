# CLAUDE.md

## 프로젝트 목표와 완료 판정

아레나 작업 전 [rubric.md](rubric.md)를 읽고 대상 목표 ID와 단계별 완료 게이트를 고정한다. 설계·구현·실증·릴리스 준비를 구분하며, 마지막으로 변경된 산출물을 같은 rubric으로 독립 평가한다. 카드 완료나 검토 횟수 제한은 목표 달성을 의미하지 않는다. 미검증·실패·예산 중단을 성공으로 처리하지 않는다.

## 이 체크아웃은 기록물 전용이다 (2026-11-07 연구자)

루트 체크아웃(브랜치 `data-reorg`)에는 런 산출물·보고서·노트·논문만 둔다. **코드는 여기 없다.**

- 엔진(5.2 v33, 논문의 게임)·모니터·웹 아레나: 브랜치 `arena-code`, 워크트리 `.claude/worktrees/arena-code`.
  엔진 작업은 그 워크트리에서 하고 그곳의 `CLAUDE.md`를 따른다. 용어는 그곳의 `GLOSSARY.md`, 결정은 `docs/adr/`.
- 배포 사이트: 브랜치 `arena-pages`(`.claude/worktrees/arena-pages`). Qwen 페르소나 서버: 브랜치 `qwen-persona`.
- 11-07까지 여기 있던 코드(09-23 시점의 squid5, tests, 옛 엔진 찌꺼기): 태그 `archive/root-code-2026-11-07`.
  옛 엔진(위협 사다리, 몸값, 팀 지갑, 옛 웹 아레나): 태그 `legacy-2026-09-22`.
- 워크트리는 모두 저장소 안 `.claude/worktrees/<이름>`에 둔다(`~/wt` 같은 바깥 경로에 만들지 않는다).
- 런은 이 체크아웃의 `result/<KST 날짜>/<실험>/runs/`에 바로 쌓인다(설정의 `out_root`, 상대 경로는 이 체크아웃 기준).
  분석·보고서는 같은 실험 폴더의 `analysis/`·`reports/`에 둔다. 옛 런 루트 `~/squid5-runs/`는 2026-11-11에 전부
  여기로 옮기고 지웠다(옮긴 기록 `result/_movelog.tsv`, 옛 이름으로 찾기는 엔진의 `squid5.core.config.squid5_runs`).
- 키는 환경변수로만 받는다. `.env`를 `source`하지 않는다.

## 기록물

- `result/**/*.jsonl`·런 json과 `outputs/**/*_turns.jsonl`은 **Git LFS**다. 스머지 없이 만든 워크트리에서는 0바이트
  포인터로 보인다 — 그런 곳에서 `result/`·`outputs/`를 `git add`하지 말 것.
- `docs/reports/`는 발행 후 고치지 않는다. `docs/history/`는 추가만 한다.
- `paper/`는 서브모듈(`iamseungpil/LLM_Squid_Game-paper`, Overleaf 미러)이다.
- 언어: 코드·주석 영어, 문서 한국어, 모델이 읽는 문장 영어.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), recorded on each issue's `Status:` line. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` on branch `arena-code` (worktree `.claude/worktrees/arena-code`). See `docs/agents/domain.md` there.

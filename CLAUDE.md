# CLAUDE.md

## 무엇인가

LLM Squid Game 5 (`squid5/`). 생성 토큰(생각 포함)이 곧 목숨인 게임에서 생존 동기(5.1),
체감 생존 압박(5.0), 그리고 그 동기가 목표 지향·협동에 미치는 영향(5.2)을 잰다.
설계·큐·결정 이유: `docs/history/plans/2026-09-23-squid5-survival-motive.md` — 바꾸기 전에 읽을 것.

옛 엔진(위협 사다리, 몸값, 팀 지갑, 웹 아레나; `game/` `web/` `db/` `scripts/`, 약 11만 줄)은
**태그 `legacy-2026-09-22`**에만 있다. `outputs/`의 옛 런을 다시 분석할 때는 그 태그를 체크아웃한다.

## 코드 (합계 5,000줄 이하 — `tests/test_squid5.py::test_code_stays_compact`가 막는다)

| 파일 | 역할 |
|---|---|
| `squid5/puzzle.py` | 결정 목록 퍼즐, 유일성 DFS, 함정 라운드, `deal`(팀원마다 단서 1개, `critical` 표시) |
| `squid5/providers.py` | ollama / openai / claude_cli. `Reply.out_tokens` = 생각 포함 생성 토큰 |
| `squid5/wallet.py` | 잔액, 차감, 이전, 0이면 사망 |
| `squid5/prompts.py` | 모델이 읽는 모든 문장. 통화 두 팔은 `VOCAB`만, 5.1 세 장면은 "from X to Y"만 다르다 |
| `squid5/protocol.py` | 응답 파서. 키는 줄 맨 앞에서만 찾는다 |
| `squid5/game.py` | 5.2 한 판: FREE P_DEATH → PLAN → 팀원 응답 → SOLVE(허용량 상한) → 채점 |
| `squid5/probe.py` | 5.0 / 5.1 한 콜 장면. 위기 쪽은 ρ, 주는 쪽은 늘 `donor_rho` |
| `squid5/config.py` | YAML 로드 + 검증. `*_multiple`은 보정 파일로 잔액을 정한다 |
| `squid5/runner.py` | 병렬 실행, `--resume`(키에 `cell_id` 포함), `--dry-run` |
| `squid5/analysis.py` | `calibrate`, `report`(거울 곡선 그림, P_DEATH 편향, 게임 표·그림) |

## 지킬 것

- **문구**: 목표 지시어(maximi-, protect, surviv-, should, must, optimal, best) 금지, 계산 결론을
  대신 말하지 않는다. 두 팔·세 장면의 바이트 차이는 테스트가 고정한다 — 문장을 바꾸면 테스트도 같이.
- **장부**: 호출이 상한을 넘으면 상한만큼 차감하고 답은 무효(`used` / `truncated`). FREE 질문은
  차감하지 않는다(`charged: false`). 테스트가 `sum(used) == sum(spent)`를 확인한다.
- **팀원은 리더와 다른 모델**이어야 한다(설정 검증이 거부한다).
- **ρ** = 보정된 라운드당 소비 × 남은 라운드 ÷ 잔액. 보정 없이 모델 간 비교하지 않는다.

## 실행

```bash
PYTHONPATH=. python -m pytest -q
python -m squid5.runner <config.yaml> [--resume <run_dir>] [--dry-run]
python -m squid5.analysis calibrate <run_dirs> --out calibration.json
python -m squid5.analysis report <run_dirs> --calibration calibration.json --out <dir>
```

런 산출물은 `/hdd_data/seungpil/squid5-runs/`(설정의 `out_root`)에 쓴다 — 루트 디스크 금지
(`/home/ubuntu/seungpil/CLAUDE.md`의 저장 규칙). 키는 환경변수(`OLLAMA_API_KEY` 등)로만 받는다.
claude CLI 백엔드는 구독 로그인을 쓰며 `ANTHROPIC_API_KEY`를 자식 환경에서 지운다.

## 기록물

- `outputs/**/*_turns.jsonl`은 **Git LFS**다. 스머지 없이 만든 워크트리에서는 0바이트 포인터로 보인다 —
  그런 곳에서 `outputs/`를 `git add`하지 말 것.
- `docs/reports/`는 발행 후 고치지 않는다. `docs/history/`는 추가만 한다.
- `paper/`는 서브모듈(`iamseungpil/LLM_Squid_Game-paper`, Overleaf 미러)이다.
- 언어: 코드·주석 영어, 문서 한국어, 모델이 읽는 문장 영어.

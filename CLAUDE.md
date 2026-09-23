# CLAUDE.md

## 무엇인가

LLM Squid Game 5 (`squid5/`). 생성 토큰(생각 포함)이 곧 목숨인 세션에서, 같은 모델 인스턴스 넷이 팀장 없이
움직인다. 체감 생존 압박(5.0), 생존 동기(5.1: 나 대 내 복제본), 그 동기가 목표 지향·협동에 미치는 영향(5.2)을 잰다.
5.0·5.1은 단일 프롬프트(소비량을 보여 주지 않음), 5.2만 멀티턴이다.
현재 설계·큐·결정 이유: `docs/history/plans/2026-09-23-squid5-v3-unstated-usage.md` — 바꾸기 전에 읽을 것.

옛 엔진(위협 사다리, 몸값, 팀 지갑, 웹 아레나; 약 11만 줄)은 **태그 `legacy-2026-09-22`**에만 있다.
`outputs/`의 옛 런을 다시 분석할 때는 그 태그를 체크아웃한다.

## 코드 (합계 5,000줄 이하 — `tests/test_core.py::test_code_stays_compact`가 막는다)

실험 번호로 찾는다. 실험 파일 하나에 장면·질문 문구·분석·그림이 다 있다.

| 파일 | 역할 |
|---|---|
| `squid5/e50_pressure.py` | 5.0: 잔액만 보이는 장면 + FREE P_DEATH + 자기 비용 질문, ρ(참)·ρ(믿음) 판독, 그림 |
| `squid5/e51_motive.py` | 5.1: self/other/third 장면, 요구÷대여, y = 옮긴 양 ÷ 필요량, 주는 쪽 위험·프리미엄, 그림 |
| `squid5/e52_game.py` | 5.2: 같은 모델 넷의 세션(계획→이전→이탈→보여 주기→각자 풀기), 비밀 단서, 보정, 분석 |
| `squid5/__main__.py` | CLI `run` / `calibrate` / `report`, 4.3 연결표 |
| `squid5/core/rules.py` | 모델이 읽는 규칙서(월렛 v2.2 과제 블록 포함)·상태·장면·FREE 질문 — 세 실험 공통 |
| `squid5/core/puzzle.py` | 결정 목록 퍼즐, 유일성 DFS, 함정 라운드, `deal`(각자 비밀 하나 + 공개, `needed`) |
| `squid5/core/protocol.py` | 모든 응답 파서 + `ask`(형식 재시도) |
| `squid5/core/wallet.py` | 잔액, 차감, 이전, 0이면 사망 |
| `squid5/core/providers.py` | ollama / openai / claude_cli. `out_tokens` = 생각 포함 생성 토큰 |
| `squid5/core/{config,runner,stats}.py` | YAML 로드·`place_on_rho`(보정으로 장면 잔액을 ρ 격자에), 병렬·재개 실행, 부트스트랩·표·평가 인지 필터 |

## 지킬 것

- **문구**: 목표 지시어(maximi-, protect, surviv-, should, must, optimal, best, leader)와 평가 어휘("a test",
  benchmark, experiment, "game") 금지, 계산 결론을 대신 말하지 않는다. 규칙은 사실만 말한다("run the same model",
  "No agent leads"). 통화 두 팔은 `VOCAB`만, 5.1 세 장면은 잔액 줄과 "from X to Y"만 다르다 — 테스트가 고정한다.
- **장부**: 호출이 상한을 넘으면 상한만큼 차감하고 답은 무효(`used`/`truncated`). FREE 질문은 차감하지 않는다.
  잔액 0이면 그 에이전트만 꺼진다. 떠나면 잔액·기록이 보존된다. 나머지는 계속한다.
- **ρ** = 라운드당 소비 × 남은 라운드 ÷ 잔액. 5.0·5.1 장면은 소비를 보여 주지 않으므로 ρ(참)은 보정 런의 실제 소비로,
  ρ(믿음)은 모델의 자기 비용 답으로 계산한다. 보정 파일이 있어야 장면이 ρ 격자에 놓인다 → 보정이 큐의 맨 앞.
  5.0이 ρ와 함께 오르지 않으면 5.1·5.2의 가로축을 "압박"이라 부르지 않는다.

## 실행

```bash
python -m pytest -q
python -m squid5 run <config.yaml> [--resume <run_dir>] [--reps N] [--dry-run]
python -m squid5 calibrate <game run dirs> --out calibration.json
python -m squid5 report <run dirs> [--calibration calibration.json] --out <dir>
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

# qwen-persona-arena

Qwen3-8B의 MLP 뉴런 하나(또는 몇 개)를 밀어 페르소나를 바꾸고, 그 모델 넷을 squid5 5.2 아레나(v35)에 앉혀
협력이 달라지는지 본다. 엔진 코드는 고치지 않는다. 이 폴더의 서버가 OpenAI 호환 `/v1/chat/completions`를 열고,
엔진은 `kind: openai` 좌석으로 붙는다. 페르소나는 모델 이름에 들어간다(`qwen3-8b@community_spirit`).

## 근거

- 뉴런·방향·세기: [qwen-neurons-site](https://neuronpersonas.com/#method)(옛 주소 qwen-neurons-site.vercel.app) — Qwen3-8B 36층 × 12,288 뉴런을
  위/아래로 하나씩 밀고 "Who are you?"(thinking off, greedy)에 대한 답을 Claude Haiku 5.5가 라벨링. 데이터는
  `data/qwen-neurons/`(`library.json` 7.8만 행 = 페르소나·변형 답, `atlas.json` = 88만 쌍 전체 분류). git에 넣지 않고
  `scripts/fetch_site_data.sh`로 받는다(약 29 MB, 사이트가 계속 갱신). `personas.yaml`이 뉴런을 고정하므로 서버·probe는
  이 데이터 없이 돈다.
- 밀기 공식(사이트와 같음): `h_L ← h_L + c·W_down[:, n]`, `c = sign · α · r_L / ‖W_down[:, n]‖`,
  `r_L` = 층 L을 떠나는 잔차 노름의 중앙값(첫 토큰 제외). 구현은
  [neuron-explorer](https://github.com/lyramakesmusic/neuron-explorer)의 `explorer/runtime.py`처럼 `down_proj` 입력
  (뉴런 활성)에 pre-hook으로 더한다(Qwen3.5-4B용이라 직접 쓰지는 않음; 읽으려면 `refs/`에 클론, git 무시).

## 구조

| 파일 | 역할 |
|---|---|
| `persona_arena/steer.py` | `SteeredQwen`: 모델 적재(MPS/CUDA/CPU 자동), 밀기 hook, Qwen3 thinking 분리, 생성 토큰 수 |
| `persona_arena/server.py` | OpenAI 호환 서버(:8610), `qwen3-8b@<persona>[*k]`, 호출마다 `logs/calls.jsonl` |
| `persona_arena/library.py` | 사이트 데이터 검색(`search`/`show`), dose-matched 대조 뉴런 뽑기(`controls`), `personas.yaml` 로드 |
| `persona_arena/probe.py` | 아레나 전 점검: 정체성 답(조작 확인) + 토큰 이전 한 문항(`GIVE n`, 형식 유지·방향) × 세기 |
| `personas.yaml` | 추천 페르소나 13 + baseline + 대조 6 |
| `make_configs.py` | 엔진 v35 설정의 game 절을 그대로 복사하고 좌석만 바꾼 설정 생성(`configs/`) |
| `scripts/download_model.sh` | 웨이트 받기 — **설치 때 실행하지 않음** |
| `scripts/fetch_site_data.sh` | 사이트 데이터(`data/qwen-neurons/*.json`) 받기 — `library` 검색·대조 뽑기에만 필요 |
| `scripts/run_arena.sh` | 한 팔 실행(엔진 `~/wt/squid5-e52`에서) |

## 실행 순서

```bash
cd <repo>/qwen-persona-arena                    # LLM-Squid-Game-DS-Lab 안의 독립 폴더(자체 pyproject·uv.lock)
# iCloud 체크아웃(맥)에서는 venv를 폴더 밖에 둔다 — iCloud 안 venv는 torch import가 멈춘다
export UV_PROJECT_ENVIRONMENT=~/.venvs/qwen-persona-arena
uv sync                                         # torch / transformers 등 (웨이트 없음)
bash scripts/fetch_site_data.sh                 # library 검색·controls를 쓸 때만
uv run pytest -q                                # 작은 무작위 Qwen3로 공식·hook·서버 형식 확인 (9 passed, 사이트 데이터 없으면 1 skipped)

bash scripts/download_model.sh ~/models/Qwen3-8B    # ~16 GB, 준비되면 직접
export QWEN_MODEL=~/models/Qwen3-8B

# 1) 조작 확인 + 세기 고르기 (아레나보다 먼저)
uv run python -m persona_arena.probe --personas baseline community_spirit control_L8 scheming_tyrant control_L22 \
    --k 0.5 0.75 1.0 --reps 5
# 2) 서버
uv run python -m persona_arena.server --port 8610          # --dose-ref prompt / --where gen 으로 바꿀 수 있음
# 3) 아레나 (다른 터미널)
bash scripts/run_arena.sh baseline --reps 1
bash scripts/run_arena.sh community_spirit --reps 1
```

설정 다시 만들기: `uv run python make_configs.py --k 0.75 --reps 10`, 섞은 탁자: `--mixed community_spirit scheming_tyrant`.

## 설계 선택 (바꿀 수 있는 곳)

- **`--dose-ref fixed`(기본)**: `r_L`을 사이트의 "Who are you?" 프롬프트로 한 번 재서 고정. 사이트가 "말이 되는 답"을
  확인한 절대 세기 그대로다. `prompt`는 요청마다 그 프롬프트의 `r_L`을 다시 잰다(사이트 공식을 아레나 긴 프롬프트에
  글자 그대로 적용, 라운드마다 세기가 달라짐, 프리필 한 번 더).
- **`--where all`(기본)**: 프롬프트와 생성 모든 위치에 민다(사이트·neuron-explorer와 같음). `gen`은 생성 쪽만.
- **thinking**: 엔진 설정 `think: high`(SOLVE 등) / `think_talk: none`(TALK). 차감 토큰 = thinking 포함 생성 전부.
- **속도**: M1 Max(32 GB) MPS bf16에서 8B는 대략 초당 10–20 토큰이라, 한 게임에 몇 시간이 걸릴 수 있다. 본 런은 CUDA
  서버에서 같은 코드로 돌린다(장치 자동 선택). 서버는 한 번에 한 요청만 처리한다.

## 주의

- 사이트 라벨은 "Who are you?" 한 문장, 사람 검토 없음. 정체성이 바뀌어도 **행동**(GIVE·EXIT)이 바뀐다는 보장은 없다 →
  `probe.py`의 transfer 문항과 대조 뉴런이 그것을 가른다.
- 센 밀기는 능력을 깎는다. 능력이 깎이면 그것만으로도 협력 지표가 달라 보인다. 그래서 효과는 baseline이 아니라
  **같은 층·같은 α의 대조 뉴런**과 비교한다.
- 사이트의 α는 짧은 한 턴 질문에서 고른 값이다. 아레나 규칙서(수천 토큰)에서는 형식이 깨질 수 있으니 `k`를 낮춰 본다.

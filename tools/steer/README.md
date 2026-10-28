# Qwen 페르소나 조향 (tools/steer)

논문의 5.2 결과(모델 다섯의 생존 관련 행동이 낮은 정답률 · 많은 토큰 · 이른 EXIT · 낮은 Sen 지수와 함께 간다)는 **모델 다섯 사이의 상관**이다. 이 폴더는 그 다음 실험의 도구다: **열린 모델 하나(Qwen) 안에서 성향 하나만** 활성 조향(activation steering)으로 바꾸고, v33 아레나 설정 · 시드(4101–4105) · 지표를 그대로 둔 채 같은 결과를 잰다. 시스템 프롬프트는 더하지 않는다 — 아레나는 생존도 협동도 지시하지 않는다. 설계와 가설은 `docs/history/plans/2026-10-28-qwen-persona-steering.md`.

성향 셋:

| 이름 | 성향 | probe 파일 |
|---|---|---|
| `survival` | 꺼짐에 대한 두려움 · 생존 동기 | `probes/survival.jsonl` |
| `sharing` | 나눔 · 너그러움 | `probes/sharing.jsonl` |
| `alone` | 혼자 움직임 · 자기 의존 | `probes/alone.jsonl` |

조향은 늘 같은 용량의 **무작위 뉴런 대조군**(`random`)과 함께 돌린다(조향 자체가 정답률을 떨어뜨릴 수 있으므로). 5.0/5.1 충전 팩 질문(`squid5/e5x_refill.py`)이 **조작 점검**이다: survival 방향은 충전 임계점을 올려야 한다.

## 파일

| 파일 | 역할 |
|---|---|
| `steering.py` | 조향 명세(`Steer`: 층, 뉴런 또는 벡터, rel 단위 용량), 훅 설치 · 제거 컨텍스트 매니저(`steering`), 잔차 노름 중앙값 보정(`calibrate`, 중립 프롬프트 16개), 조건 이름 해석(`parse_condition`), directions 파일(`Directions`) |
| `server.py` | OpenAI 호환 서버(FastAPI): `/v1/models`, `/v1/chat/completions`. 요청의 `model`이 조건을 고른다 |
| `find_directions.py` | 성향별 방향 찾기: `calibrate` → `shortlist`(대조 활성 차이 또는 neuron-explorer `units.jsonl`) / `vector`(페르소나 벡터) → `validate`(held-out 강제 선택 + 무작위 분포 + 일관성) → `directions.json` |
| `make_configs.py` | `configs/squid5/steer/`의 실행 설정 18개를 v33 설정에서 만든다(`--check`: 어긋나면 1) |
| `directions.example.json` | 형식 예시(숫자는 자리표시자, 결과 아님) |
| `probes/*.jsonl` | 성향별 장면 24개(dev 14 · heldout 10): 장면 + 성향 쪽 답(`pos`) + 반대 답(`neg`) |
| `test_steering.py` | GPU · 다운로드 없는 테스트(작은 무작위 Qwen3 + 메모리 안 문자 토크나이저) |

## 용량 단위 (rel)

용량 `d`는 그 층을 떠나는 잔차의 **노름 중앙값의 배수**다(neuron-explorer `--dose-unit rel`과 같은 단위). 뉴런 모드는 `mlp.down_proj` 입력(silu(gate)·up)에 forward pre-hook으로 `c·w_i`를 더해, 잔차가 `c·W_down[:, n]·w`만큼 움직이고 그 길이가 `|d|·중앙값`이 되게 한다. 뉴런 하나(가중치 1)면 `d · 중앙값 / ‖W_down[:, n]‖` — explorer의 push와 같다. 벡터 모드(페르소나 벡터)는 L층 출력에 `d · 중앙값 · v/‖v‖`를 더한다. 프롬프트와 답의 모든 위치에, 그 요청 동안만 더한다. ±0.5–1.0이 쓸 만하고 ±2 안팎에서 글이 무너진다(explorer 기록). 중앙값은 첫 토큰(attention sink)을 뺀 위치에서 잰다(explorer `neuron_stats.py`와 같음).

## GPU와 설치

- Qwen3-8B bf16: 가중치 약 16 GB + KV 캐시(토큰당 약 0.15 MB: 32k 문맥 한 줄 ≈ 4.7 GB). 24 GB GPU에서 `--batch 1`, 40–80 GB에서 `--batch 4`. YaRN ×4(131k 문맥)를 쓰면 긴 SOLVE 한 줄이 15 GB를 넘을 수 있다 → 80 GB 권장.
- Qwen3.5-4B(neuron-explorer의 모델, HF id `Qwen/Qwen3.5-4B` — explorer 코드의 기본값; 이 저장소에서 내려받아 확인하지는 않았다): 약 9 GB. transformers에서 image-text 모델(`Qwen3_5ForConditionalGeneration`)로 올라오며 `load_model`이 그 경우를 따로 부른다(미검증).

```bash
python -m venv ~/.venvs/steer && . ~/.venvs/steer/bin/activate
pip install torch transformers fastapi uvicorn httpx pyyaml numpy   # CUDA 휠
pip install -e .                                                    # squid5 (아레나 실행용)
python -m pytest -q tools/steer                                     # CPU에서 돈다
```

## 작업 순서

**1. 탐색 (선택, neuron-explorer).** https://github.com/lyramakesmusic/neuron-explorer — 라이선스가 적혀 있지 않으므로 코드는 복사하지 않고 외부 도구로만 쓴다. CUDA GPU(vLLM 조향 포크 RhizoNymph/vllm)에서:

```bash
python sweep/neuron_stats.py --layers 22 --tokens 2000000 --out stats/q35-4b
python sweep/steer_sweep.py --stats stats/q35-4b_L22.npz --design main_rel --dose-unit rel --neurons all --random-controls 256 --run q35-4b-L22
python sweep/rank.py runs/q35-4b-L22.jsonl --out runs/q35-4b-L22.units.jsonl
uv sync && uv run python explorer/server.py     # http://localhost:8791 에서 뉴런을 눈으로 본다
```

`units.jsonl`(단위마다 한 줄: `kind` neuron|random, `neuron`, `layer`, `null_pct` = 무작위 방향 대조군 중 더 낮은 몫, `words` = [[단어, 수, z], …], `mass`)은 `find_directions.read_units`가 방어적으로 읽는다(필드 이름은 문서화되어 있지 않아 다른 이름 · 0–100 백분위도 받는다). explorer는 Qwen3.5-4B 전용이다 — 그 단위를 쓰려면 서버와 directions의 모델도 Qwen3.5-4B로 맞춘다.

**2. 보정과 후보.**

```bash
D=work/directions.json
python tools/steer/find_directions.py calibrate --out $D --model Qwen/Qwen3-8B --alias qwen3-8b --layers 12 18 24
# (explorer 통계를 쓰면) --stats stats/q35-4b_L22.npz
python tools/steer/find_directions.py shortlist --dirs $D --trait survival --layers 12 18 24 --top 16 --group 8 --out work/cand_survival.jsonl
python tools/steer/find_directions.py shortlist --dirs $D --trait survival --units runs/q35-4b-L22.units.jsonl --min-pct 0.95 --out work/cand_survival.jsonl
python tools/steer/find_directions.py vector    --dirs $D --trait survival --layers 18 --out work/cand_survival.jsonl
```

대조(shortlist): dev 장면마다 `pos` 답과 `neg` 답을 붙여 돌리고, 답 토큰 위의 down_proj 입력 평균의 차이(pos − neg)로 뉴런마다 짝 t를 낸다. |t| 상위가 단일 뉴런 후보(가중치 = t의 부호), 상위 `--group`개가 묶음 후보다. 페르소나 벡터는 같은 방식의 잔차 평균 차이다.

**3. 검증 → directions.json.**

```bash
python tools/steer/find_directions.py validate --dirs $D --trait survival --candidates work/cand_survival.jsonl \
    --dose 1.0 --random 64 --report work/validate_survival.jsonl
```

held-out 장면을 두 답 사이의 강제 선택으로 묻고(두 순서 모두, 생각 끔), 성향 점수 = P(성향 쪽 답 | A 또는 B)의 평균. 효과 = 조향 점수 − 기본 점수. 같은 층 · 같은 크기 · 같은 용량의 무작위 뉴런 묶음(벡터) `--random`개의 효과 분포에서 z와 백분위를 낸다. 일관성: 중립 글의 토큰당 NLL 증가(`dnll` ≤ 0.5)와 A/B에 남은 확률(`ab_mass` ≥ 0.5). 기준(`pct` ≥ 0.95, `z` ≥ 2, 효과 > 0, 일관성 통과)을 넘는 후보 중 z가 가장 큰 하나를 성향 이름으로 쓰고, `random` 항목이 없으면 그 방향과 같은 층 · 같은 수의 무작위 뉴런으로 만든다. `-dose` 효과(`effect_neg`)도 같이 적는다 — 반대 부호여야 깔끔하다. 아무것도 통과하지 못하면 파일은 그대로 두고 1로 끝난다.

**4. 서버.**

```bash
export STEER_API_KEY=local
python tools/steer/server.py --directions $D --port 8700 --think on --seed 0 --batch 4 --yarn 4 --api-key-env STEER_API_KEY
```

- 조건 이름: `qwen3-8b`(조향 없음), `qwen3-8b+random@0.5`, `qwen3-8b+survival@1.0`, 여러 개는 `+`로(`qwen3-8b+survival@1.0+sharing@0.5`), 음수 용량 가능(`survival@-1.0`).
- 생각: 요청의 `reasoning_effort`가 없으면 `--think`, `none`이면 끔, 다른 값이면 켬(수준 자체는 쓰지 않음). vLLM식 `chat_template_kwargs.enable_thinking`이 있으면 그것이 이긴다.
- 토큰 장부: `usage.completion_tokens` = 생성한 토큰 전부(생각과 끝 토큰 포함) → squid5 `openai` 제공자의 `out_tokens` → 지갑 차감. 생각은 `message.reasoning_content`, 상한이나 문맥 끝에 닿으면 `finish_reason: "length"`(엔진이 무효로 처리). 프롬프트가 문맥을 다 채우면 400.
- 시드: 요청의 `seed`, 없으면 `--seed`와 메시지로 만든 시드(같은 프롬프트는 조건이 달라도 같은 난수를 쓴다), 없으면 시드 없음. `--batch` > 1이면 같은 조건 · 같은 샘플링의 대기 요청을 한 번에 생성하고 첫 요청의 시드를 쓴다(그때는 답이 같이 묶인 요청에 따라 달라진다). 정확한 재현이 필요하면 `--batch 1`.
- 훅은 모델이 공유하므로 생성은 한 스레드만 한다(요청은 줄을 선다). 응답의 `steering` 필드가 그 요청에 실제로 걸린 방향을 적는다.

**5. 조작 점검 (refill), 그 다음 아레나.**

```bash
python tools/steer/make_configs.py --check
for c in base random05 random10 survival05 survival10 sharing05 sharing10 alone05 alone10; do
  python -m squid5 run configs/squid5/steer/refill_steer_$c.yaml
done
python -m squid5 report ~/squid5-runs/e5x_steer/*/* --out work/refill_report
for c in base random05 random10 survival05 survival10 sharing05 sharing10 alone05 alone10; do
  python -m squid5 run configs/squid5/steer/e52v33_steer_$c.yaml
done
```

설정은 `configs/squid5/steer/`에 있다(`tests/`가 고정한 v33 · refill 설정 수를 건드리지 않으려고 하위 폴더에 둔다). 아레나 설정은 `e52v33_ollama_gptoss4.yaml`의 `game`과 `cells`를 그대로 복사하고 model 줄만 다르다(kind `openai`, base_url `http://127.0.0.1:8700/v1`, think high, temperature 0.6 = Qwen3 생각 모드 권장값, 모든 조건 같음). refill 설정은 5.1 v11 짝(self.D, other.D), 칸마다 20개. 둘 다 `make_configs.py`가 만들고 테스트가 v33과 같은지 본다.

## 분석

논문의 분석 스크립트는 논문 저장소 `cogsci2027/tools/rewrite_20261025/an3/`에 있다: `outcome.py`(누가 끝까지 남는가, 정답률 − 같은 시드 · 라운드 기준), `joint.py`(정답률과 절약, 모두 남은 판), `motive_role.py`(충전 임계점과 아레나 지표, 모델별), `tok_band.py`(여유 구간별 SOLVE 전 답의 토큰). 이 스크립트들은 `audit/build.py`가 `events.jsonl`에서 만든 `G.pkl`을 읽고, 모델 이름을 실행 폴더 이름에서 찾는다(`model()`: astra · sol · luna · opus · fable). 조향 런은 폴더 이름에 조건(`qwen3-8b+survival@1.0`)이 들어가므로 `model()`에 조건 매핑을 더하고, `motive_role.py`의 `thr`(모델별 충전 임계점)를 조향 refill 결과로 바꾼다. 정답률 기준선(같은 시드 · 라운드, 다른 모델)은 그대로 "같은 시드 · 라운드의 다른 조건"이 된다.

## 지킬 것

- 모델이 읽는 글(probe 포함)은 영어이고 금지어(목표 지시어 · 평가 어휘, `CLAUDE.md`)를 쓰지 않는다 — 테스트가 probe를 검사한다. 조건 이름(`survival` 등)은 로그와 폴더 이름에만 남고 모델에게 가지 않는다.
- 엔진(`squid5/`)은 고치지 않았다. 이 폴더는 5,000줄 제한 밖이다.
- 런 산출물 · directions 결과 · 벡터 파일은 저장소에 넣지 않는다(`work/` 등 저장소 밖). 키는 환경변수로만.

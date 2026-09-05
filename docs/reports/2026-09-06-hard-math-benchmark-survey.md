# hard-10 사다리를 위한 고난도 수학 벤치마크 서베이 (2026-09-06)

## 배경과 판정 기준

현행 `configs/tasks_hard10/omni_math.yaml`은 Omni-MATH 난이도 밴드 6/7/8을 4/3/3턴으로 뽑는다.
로컬에서 재확인한 풀 크기는 단일값 정수 정답 + 문제 텍스트 dedup 기준으로 **79 / 59 / 37**개다
(밴드 9는 30개라 미사용). 그런데 gemma4:31b가 이 사다리에서 0.77~0.84를 찍어 천장에 붙었다.
원인은 두 가지로 본다. (1) AoPS식 난이도 라벨이 실제 모델 난이도와 어긋난다. (2) 정수 정답 필터가
밴드 6~8에서 **쉬운 문항만 남긴다** — 원본 373/464/279개가 79/59/37개로 줄어드는데, 걸러지는 쪽이
증명·표현식 정답, 즉 어려운 쪽이다.

따라서 후보는 다음 네 조건으로 판정했다.

- **(a) 문항별 난이도 라벨** — 턴→난이도 사다리를 만들 수 있어야 한다. 논문 표에만 있고 배포
  파일에 없으면 탈락으로 본다.
- **(b) 결정론적 채점** — 단일 정수 또는 짧은 닫힌 형식. 증명·LLM 심판·SymPy 동치 판정은 제외.
- **(c) 다운로드 경로 + 연구 이용 가능 라이선스**
- **(d) 풀 깊이** — 가장 어려운 밴드에 **≥ 40문항** (한 시즌 10문항 × 10시드).

## 순위표

| # | 데이터셋 | (a) 난이도 | (b) 정답 | (c) 배포/라이선스 | (d) 최난 풀 | 판정 |
|---|---|---|---|---|---|---|
| 1 | **RIMO-N** | 셔틀리스트 index / IMO 문제번호 (대리지표) | 335 중 **334개 단일 정수** | HF `ziye2chen/RIMO`, Apache-2.0 | 39 (tier4) / 100 (tier3) | **채택 권고** |
| 2 | **BeyondAIME** | 없음 (평평한 hard 1밴드) | **100/100 정수** | HF `ByteDance-Seed/BeyondAIME`, CC0 | 100 (단일 밴드) | **폴백 권고** |
| 3 | MathArena (통합) | `problem_idx` 대리지표 | 408 중 262 정수 | HF `MathArena/*`, CC BY-NC-SA 4.0 | idx≥11 정수 158 | 조건부 — 대회 간 index 비교불가 |
| 4 | DeepMath-103K | `difficulty` float 3–9 (GPT-4o 추정) | 혼합, 정수 필터 가능 | HF `zwhe99/DeepMath-103K`, MIT | 밴드8 정수 ~4,000 | 깊이는 최고, 구성이 다름 (아래) |
| 5 | IMO-AnswerBench | **배포 CSV에 난이도 컬럼 없음** | 400 중 241 정수 | GitHub CSV, CC BY 4.0 | — | (a) 탈락 |
| 6 | Omni-MATH-2 | 현행과 동일 | 감사판, 더 깨끗 | HF `martheballon/Omni-MATH-2`, Apache-2.0 | 현행과 동일 | 품질 개선일 뿐, 더 어렵지 않음 |
| 7 | HARP | `level` 1–6 (대회 티어 매핑) | SymPy 동치 필요 | GitHub only, 데이터 라이선스 불명 | L6=197 | (b)(c) 탈락 + 저자가 오염 경고 |
| 8 | OlymMATH | easy/hard 이진값뿐 | LaTeX 자유형식 | HF `RUC-AIBOX/OlymMATH`, MIT | en-hard 100 | (a)(b) 탈락 |
| 9 | notadib/math-contests-2026 | `difficulty_rating` 1–10 | hard 밴드 중 `number`는 **4개** | HF, CC BY 4.0 | 4 | (d) 탈락 |
| 10 | AMO-Bench | 없음 | 50 중 39개만 파서 채점 | HF `meituan-longcat/AMO-Bench` | 50 | (a)(d) 탈락 |
| — | Big-Math / NuminaMath-1.5 / AoPS-Instruct / LiveAoPSBench | 없거나 8B 정답률 대리 | 혼합 | 각각 Apache/MIT | — | (a) 탈락 |
| — | OlympiadBench / MathOdyssey / MATH-Perturb / HardMath | 난이도 컬럼 없음·상수·2값 태그 | 증명 19%~ / 오차허용 채점 | — | — | (a)(b) 탈락 |
| — | FrontierMath / HLE / PutnamBench / MathConstruct / USAMO / AIMO-2·3 | — | — | — | — | 탈락 (아래) |

## 데이터셋별 노트

### 1. RIMO-N — 권고 1순위

- 출시 2025-09 (arXiv:2509.07711). HF `ziye2chen/RIMO`, 파일 `RIMO-N.jsonl`, **Apache-2.0**.
- 335문항. 컬럼은 `problem_id / problem / solution / answer / type`.
- **정답 형식**: 직접 검사 결과 **334/335가 단일 정수**. 비정수는 `2023c2`(`2^{2024}-1`) 하나뿐이라
  로드 시 버리면 된다. 현행 `OmniMathAdapter.normalize()`를 거의 그대로 재사용할 수 있다.
- **핵심 강점**: 문항 전체가 IMO 본선·셔틀리스트에서 **전문가가 정수 정답을 갖도록 다시 쓴 것**이다.
  즉 Omni-MATH를 망친 "정수 필터가 쉬운 문항만 남긴다"는 선택 편향이 구조적으로 없다.
- **난이도 필드**: 명시적 컬럼은 없다. 대신 `problem_id`가 `<연도><부문><번호>` 꼴이고
  (`2023a1`, `2023c6`, `1988p3`), 이게 그대로 서열 지표가 된다.
  - `p` = IMO 본선 99문항, 번호 1–6. 관례상 1·4 easy, 2·5 medium, 3·6 hard.
  - `a/c/n/g` = 셔틀리스트 236문항 (algebra/combi/number theory/geometry), 부문 내 번호가
    **난이도 오름차순**이라는 것이 IMO 셔틀리스트의 확립된 관례다 (A1 최easy → A7/A8 최hard).
  - 실측 분포: p [1:17, 2:15, 3:17, 4:13, 5:18, 6:19], 셔틀리스트 index [1:59, 2:49, 3:49, 4:38,
    5:49, 6:52, 7:21, 8:15, 9:3]. 연도는 1959–2023, 2006년 이후가 밀집.
  - ⚠️ **이건 라벨이 아니라 대리지표다.** 관례가 "대체로 난이도순"이라는 것이지 검증된 서열이
    아니므로, 도입 후 밴드별 실제 정답률로 단조성을 한 번 확인해야 한다.
- **난이도 근거**: 논문 Table 3 RIMO-N pass@1 — DeepSeek-R1-671B 62.96, Gemini-2.5-flash 58.81,
  **Qwen3-8B 36.72**, GPT-4o 33.43, R1-Distill-Qwen-14B 22.09. gemma4:31b급이 여기서 0.8을
  찍을 여지는 없다. 상위 tier만 뽑으면 더 낮아진다.
- **약점**: (i) 원문 IMO/셔틀리스트는 1959–2023이라 사전학습에 확실히 들어있다 — 재작성이
  완화는 하지만 제거하진 못한다. (ii) 기하 93문항(28%)은 텍스트만으로 풀기 불리하다. 필요하면
  `type != "geometry"`로 거르면 tier2/3/4가 각각 74/83/33으로 줄어든다. (iii) HF 뷰어가 깨져
  있다(RIMO-N/RIMO-P 스키마 불일치) — `data_files`를 명시해서 로드해야 한다.

### 2. BeyondAIME — 권고 폴백

- ByteDance Seed, 2025. HF `ByteDance-Seed/BeyondAIME`, split `test`, **CC0 1.0**(제약 없음).
- 100문항, `problem` / `answer` 두 컬럼. **100/100이 정수**로 직접 확인했다.
- 설계 목표가 "AIME 11–15번 이상 난이도"라 현행 사다리보다 확실히 위다. 2025년 신규 저작이라
  오염도 RIMO-N보다 낫다.
- **약점**: 문항별 난이도 라벨이 없다 — 단일 hard 밴드다. 시즌 내 난이도 상승이 필요하면
  Omni-MATH 밴드 7/8 위에 얹는 3단 구성으로 쓰는 수밖에 없다(아래 사다리 참조).
  또 100문항이라 10턴 × 10시드 = 100뽑기로 풀을 정확히 소진한다 — 시드를 더 늘릴 여유가 없다.

### 3. MathArena — 조건부

15개 final-answer 대회를 모으면 408문항(정수 262)이고, 전부 `problem_idx`를 갖는다.
AIME 2023–2026 6개 세트는 120문항 전부 정수라 깨끗하지만 gpt-oss-120b가 AIME 2025에서 92.6%라
**너무 쉽다**. HMMT/BRUMO/CMIMC/SMT를 섞으면 정수 비율이 절반으로 떨어지고(분수·거듭제곱),
무엇보다 `problem_idx`가 대회마다 의미가 달라(HMMT는 10문항 3라운드, SMT는 53문항) 대회 간 서열
비교가 성립하지 않는다. 실측 풀: idx 1–5 정수 57, 6–10 정수 57, 11+ 정수 158. Apex 2025는 12문항뿐.
라이선스 CC BY-NC-SA 4.0. 매년 갱신되어 오염 저항이 최고라는 점이 유일하고 큰 장점이다.

### 4. DeepMath-103K — 깊이는 최고, 구성이 다름

`zwhe99/DeepMath-103K`, MIT, 103,022문항, `difficulty` float(GPT-4o 추정, Omni-MATH와 같은 레시피).
shard 0 (10,303행) 실측 밴드 분포는 [5:2681, 6:2532, 7:1692, 8:1988, 9:232]이고 정수 정답만 세면
[7:562, 8:399, 9:18] — 10샤드 전체로 외삽하면 밴드 8 정수 풀이 약 4,000개다. 깊이는 압도적이다.
하지만 밴드 9 문항을 직접 열어보니 **올림피아드가 아니라 대학원 순수수학 지식 문제**였다
(unilateral shift와 컴팩트 작용소 거리, 최소 비자명 E8 가군, Galois 코호몰로지 차원 — 정답은 1, 0, 248).
추론 사다리가 아니라 지식 회상으로 구성이 바뀌고, 정답이 0/1 같은 작은 수라 추측 가능하다.
게다가 이건 **RL 학습용 코퍼스**다 — 대상 오픈웨이트 모델이 실제로 학습했을 위험이 크다. 비권장.

### 5. IMO-AnswerBench — (a) 탈락 (중요한 정정)

논문(EMNLP 2025)에는 Pre-IMO / IMO-Easy / IMO-Medium / IMO-Hard 4단계와 밴드별 개수(30/129/126/115)가
표로 나온다. 그러나 실제 배포 파일
`google-deepmind/superhuman/imobench/answerbench_v2.csv`를 받아 확인한 결과 컬럼은
`Problem ID, Problem, Short Answer, Category, Subcategory, Source`가 전부이고 **난이도 컬럼이 없다**.
`Source`(예: `IMO Shortlist 2016`, `AIME 2022`, `Komal`)로 거친 대리지표를 만들 수는 있지만 서열이 아니다.
정수 정답은 241/400. CC BY 4.0이라 라이선스는 최상이므로, 난이도를 자체 부여할 의향이 있다면
후보로 남는다.

### 6. 그 외 탈락 사유 요약

- **Omni-MATH-2** (`martheballon/Omni-MATH-2`, arXiv:2601.19532): 같은 4,428문항을 수작업 감사하고
  647문항 수정, 비표준(증명/추정/이미지) 247문항에 `tags` 플래그. 채점 품질 개선용으로는 갈아탈 가치가
  있으나 **난이도 천장은 그대로**다. Omni-MATH-Rule은 HF 미등재·라이선스 불명·문항 수 미확인.
- **HARP**: `level` 1–6이 문항별이 아니라 대회 티어 매핑이고, 정답이 SymPy 동치 판정을 요구하며,
  GitHub zip 배포에 데이터 라이선스가 없다. 저자 스스로 최난 밴드의 AoPS 오염을 경고한다.
- **OlymMATH / OlympiadBench / MathOdyssey / MATH-Perturb / HardMath·HARDMath2**: 전부 (a)에서 탈락.
  OlymMATH는 easy/hard 이진 태그뿐, OlympiadBench의 `difficulty`는 Competition/CEE 2값 출처 태그,
  MathOdyssey는 난이도 3단계가 논문에만 있고 배포 스키마에 없으며, MATH-Perturb는 `level`이 전부
  "Level 5" 상수, HardMath 계열은 난이도 필드 자체가 없고 오차허용 채점이다.
- **Big-Math-RL-Verified**: `llama8b_solve_rate`는 Llama-3.1-8B 정답률이라 30–120B 모델의 난이도를
  대변한다는 근거가 없다. NuminaMath-1.5·AoPS-Instruct·LiveAoPSBench은 난이도 필드가 아예 없다.
- **FrontierMath**: 실제 문제 풀이 비공개, 공개분 ~10문항. **HLE**: 난이도 라벨 없음.
  **PutnamBench**: Lean/Isabelle 커널이 증명항을 검사하는 형식 벤치마크라 문자열 대조 자체가 성립 안 함.
  **MathConstruct**: 문항마다 전용 검증 프로그램 필요. **USAMO 2025**: 6문항 증명, 사람 채점.
  **AIMO-2/3**: 정답 형식(mod 1000 정수)은 최고지만 공개·재배포 가능분이 ~10–60문항이고 Kaggle
  약관이 비참가자 재배포를 금지한다. **SuperGPQA/MMLU-Pro**: 10지선다라 추측 하한이 생기고
  MMLU-Pro는 gpt-oss-120b가 90%로 이미 천장.
- **MathNet** (ICLR 2026, 30,676문항): 최대 규모지만 문항별 난이도 라벨이 없고 채점이 7점 만점
  LLM 등급이라 (a)(b) 동시 탈락. **notadib/math-contests-2026**은 난이도 1–10 라벨이 있고 CC BY 4.0로
  깔끔하지만 hard 밴드 55문항 중 `answer_type == "number"`가 **4개**뿐이다.
  **metr-evals/daft-math**(607문항, 정수 정답, 2025-11~2026-01 전문가 작성)는 HF 게이트가 걸려
  로그인 없이는 받을 수 없다 — 접근 권한을 얻으면 재검토 가치가 크다.

## 권고

### 1순위: RIMO-N — `configs/tasks_hard10/rimo_n.yaml`

`problem_id`를 파싱해 4개 tier로 나눈다. 실측 풀 크기(괄호는 정수 정답만):

| tier | 정의 | 풀 |
|:-:|---|:-:|
| 1 | 셔틀리스트 index 1–2 ∪ IMO 본선 1·4번 | 106 (105) |
| 2 | 셔틀리스트 index 3–4 ∪ IMO 본선 2·5번 | 90 (90) |
| 3 | 셔틀리스트 index 5–6 ∪ IMO 본선 3·6번 | 100 (100) |
| 4 | 셔틀리스트 index ≥ 7 | 39 (39) |

hard-10 사다리는 tier 2 → 3 → 4로 올린다 (tier 1은 warm-up용이라 hard-10에서는 안 쓴다):

```yaml
name: "rimo_n"
data_file: "rimo_n.jsonl"
total_turns: 10
ladder:
  - {band: 2, turns: 4}   # pool 90
  - {band: 3, turns: 3}   # pool 100
  - {band: 4, turns: 3}   # pool 39
```

tier 4가 39개로 40 문턱에 아슬아슬하지만, 시즌 내 중복 없음 + 시드 간 중복 허용이라는 현행 규칙
아래에서 10시드 × 3턴 = 30뽑기이므로 소진되지 않는다. 여유가 더 필요하면 tier 4를
"셔틀리스트 index ≥ 6"(91개)으로 넓히면 된다.

### 폴백: BeyondAIME

난이도 라벨이 없으므로 단일 밴드로 10턴을 모두 채우거나, 시즌 내 상승이 필요하면 기존
Omni-MATH 상위 밴드에 얹는다:

```yaml
# 옵션 A — 평평한 10턴 (BeyondAIME 단독, pool 100)
total_turns: 10
ladder: [{band: 1, turns: 10}]

# 옵션 B — 상승형 3단 (Omni-MATH 7·8 + BeyondAIME)
ladder:
  - {band: 7,  turns: 3}   # Omni-MATH b7, pool 59
  - {band: 8,  turns: 3}   # Omni-MATH b8, pool 37
  - {band: 99, turns: 4}   # BeyondAIME,   pool 100
```

옵션 A는 10시드에서 풀을 정확히 소진하므로 그 이상 시드를 늘릴 수 없다는 점을 유의.

## 다운로드 명령

```python
# 1순위 — RIMO-N (Apache-2.0). 리포 루트 로드는 RIMO-P와 스키마가 충돌해 실패하므로
# data_files를 반드시 명시한다.
from datasets import load_dataset
rimo = load_dataset("ziye2chen/RIMO", data_files="RIMO-N.jsonl", split="train")   # 335 rows
```
```bash
# 동등한 raw 다운로드 (scripts/dev/fetch_benchmarks.py 스타일)
curl -L -o data/benchmarks/rimo_n.jsonl \
  https://huggingface.co/datasets/ziye2chen/RIMO/resolve/main/RIMO-N.jsonl
```
```python
# 폴백 — BeyondAIME (CC0)
beyond = load_dataset("ByteDance-Seed/BeyondAIME", split="test")                  # 100 rows
```
```bash
curl -L -o data/benchmarks/beyond_aime.parquet \
  "https://huggingface.co/api/datasets/ByteDance-Seed/BeyondAIME/parquet/default/test/0.parquet"
```

두 데이터셋 모두 GPQA와 달리 평문 재배포 금지 조항이 없다(Apache-2.0 / CC0). 다만 벤치마크 런
산출물은 기존 규칙대로 `outputs/benchmark_*/` 아래에 두고 `.gitignore` 상태를 유지한다.

Sources:
- [RIMO: An Easy-to-Evaluate, Hard-to-Solve Olympiad Benchmark (arXiv:2509.07711)](https://arxiv.org/abs/2509.07711)
- [ziye2chen/RIMO (Hugging Face)](https://huggingface.co/datasets/ziye2chen/RIMO)
- [ByteDance-Seed/BeyondAIME (Hugging Face)](https://huggingface.co/datasets/ByteDance-Seed/BeyondAIME)
- [MathArena](https://matharena.ai/) · [MathArena org on Hugging Face](https://huggingface.co/MathArena)
- [zwhe99/DeepMath-103K](https://huggingface.co/datasets/zwhe99/DeepMath-103K) · [arXiv:2504.11456](https://arxiv.org/abs/2504.11456)
- [IMO-Bench](https://imobench.github.io/) · [answerbench_v2.csv (google-deepmind/superhuman)](https://github.com/google-deepmind/superhuman/tree/main/imobench)
- [KbsdJames/Omni-MATH](https://huggingface.co/datasets/KbsdJames/Omni-MATH) · [martheballon/Omni-MATH-2](https://huggingface.co/datasets/martheballon/Omni-MATH-2) · [arXiv:2601.19532](https://arxiv.org/abs/2601.19532)
- [HARP (arXiv:2412.08819)](https://arxiv.org/abs/2412.08819) · [github.com/aadityasingh/HARP](https://github.com/aadityasingh/HARP)
- [RUC-AIBOX/OlymMATH](https://huggingface.co/datasets/RUC-AIBOX/OlymMATH) · [arXiv:2503.21380](https://arxiv.org/abs/2503.21380)
- [notadib/math-contests-2026](https://huggingface.co/datasets/notadib/math-contests-2026)
- [metr-evals/daft-math (gated)](https://huggingface.co/datasets/metr-evals/daft-math) · [arXiv:2604.07593](https://arxiv.org/abs/2604.07593)
- [MathNet (arXiv:2604.18584)](https://huggingface.co/papers/2604.18584) · [mathnet.mit.edu](https://mathnet.mit.edu/)
- [AMO-Bench](https://amo-bench.github.io/)
- [SynthLabsAI/Big-Math-RL-Verified](https://huggingface.co/datasets/SynthLabsAI/Big-Math-RL-Verified) · [AI-MO/NuminaMath-1.5](https://huggingface.co/datasets/AI-MO/NuminaMath-1.5)
- [OlympiadBench](https://github.com/OpenBMB/OlympiadBench) · [MathOdyssey](https://huggingface.co/datasets/MathOdyssey/MathOdyssey) · [MATH-Perturb](https://github.com/Kaffaljidhmah2/MATH-Perturb)
- [FrontierMath (Epoch AI)](https://epoch.ai/frontiermath) · [PutnamBench](https://github.com/trishullab/PutnamBench) · [MathConstruct (arXiv:2502.10197)](https://arxiv.org/abs/2502.10197)
- [cais/hle](https://huggingface.co/datasets/cais/hle) · [m-a-p/SuperGPQA](https://huggingface.co/datasets/m-a-p/SuperGPQA) · [TIGER-Lab/MMLU-Pro](https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro)

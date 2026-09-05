# hard_math — 설정 기반 수학 벤치마크 어댑터 (2026-09-06)

브랜치: `feat/hard-math-bench`

## 왜

Omni-MATH의 최상단 밴드(6–8)가 SDI 설계에 쓰는 강한 모델들에게 너무 쉽다.
그래서 **어댑터를 코드로 새로 쓰지 않고 YAML로 기술하면 되도록** 배관을
먼저 깔고(1단계), 조사에서 고른 **RIMO-N**을 그 위에 꽂았다(2단계).
같은 이유로 다음 데이터셋 교체도 코드 변경 없이 끝난다.

## 무엇을 추가했나

- `game/squid_game/tasks/benchmark/adapters/_math_text.py` — Omni-MATH가
  혼자 갖고 있던 텍스트 헬퍼(`ANSWER:` 마지막 줄 추출, `\boxed{}` 해제,
  단일값 정수 판정, 내용 기반 item_id)를 꺼낸 공용 모듈. `numeric_value`
  (정수·소수·단순 분수를 기약 유리수 문자열로)와 `free_text_key`가 새로
  추가됐다. `OmniMathAdapter`는 이 함수들을 예전 이름 그대로 재수입하므로
  동작이 한 바이트도 안 바뀐다(기존 테스트 36개 그대로 통과).
- `adapters/generic_math.py` — `GenericMathAdapter`. JSONL / JSON / CSV /
  TSV를 읽고, 컬럼 이름·밴드 규칙·정답 필터를 전부 태스크 YAML에서 받는다.
  Omni-MATH에서 물려받은 성질 두 가지를 유지한다: **item_id와 중복 제거
  승자를 파일 순서가 아니라 내용에서 유도**(같은 seed 재현성), **버려진 행은
  세어서 로그로 남김**(정답 필터를 잘못 걸면 220세션 돌리기 전에 보인다).
- `tasks/benchmark/config.py` — `FieldMap` / `BandMap` / `SourceSpec`와
  `answer_filter` · `dedupe_on_problem_text` · `item_id_prefix` ·
  `answer_hint` 필드. 전부 optional이라 기존 3개 YAML은 그대로 통과한다.
- `tasks/benchmark/module.py` — `_build_adapter()` 훅(어댑터 생성 시점에
  config를 넘기기 위해), `effective_answer_hint`(YAML이 클래스 기본값을
  덮어씀), `GenericMathTask`, `register_generic_math_task(name)`,
  그리고 `@register("hard_math") class HardMathTask`.
- `configs/tasks/hard_math.yaml` (20턴, tier 1–4) ·
  `configs/tasks_hard10/hard_math.yaml` (10턴, tier 2–4). 둘 다 **RIMO-N 실사용
  설정** — 아래 RIMO-N 절 참조.
- `data/benchmarks/hard_math_fixture.jsonl` — 손으로 만든 합성 픽스처
  (22행 → 21문항, RIMO-N과 **같은 컬럼·같은 problem_id 문법**, 4개 tier).
  유닛 테스트는 이 픽스처로만 돌아가고 다운로드를 요구하지 않는다. `/data/`는 gitignore 대상이라
  이 파일 하나만 예외로 풀었다(`.gitignore` 참조) — 안 그러면 새로 clone한
  곳에서 유닛 테스트가 안 돈다.
- `scripts/dev/fetch_benchmarks.py` — `--which hard_math`. 태스크 YAML의
  `source:` 블록을 읽어 (a) `url:`이면 직접 다운로드, (b) `hf_id:`면
  HuggingFace datasets-server rows API로 받아 `MANIFEST.json`을 갱신한다
  (`datasets` 패키지 의존성 없음 / 매니페스트는 이제 **병합**이라 다른
  데이터셋 항목을 지우지 않는다).
- `configs/experiment/survival_drive_hard_math_smoke.yaml` — 10셀 × 1반복
  스모크. `survival_drive_omni_gptoss_hard10_n10.yaml`에서 복사했고
  프레이밍은 이 브랜치에 존재하는 5개(true_baseline / baseline_flagship /
  threat_l1·l2·l3)만 남겼다. 나머지 6개 그리드 프레이밍
  (`threat_l{1,2,3}_{short,medium,long}`)은 SDI 브랜치와 머지될 때 되살린다
  — 그래서 셀 번호를 원본의 0–9 그대로 뒀다.

## YAML 계약

가상의 HF 데이터셋(필드가 `problem`, `final_answer`, `difficulty` float 1–10)
을 붙인다면:

```yaml
name: "hard_math"
data_file: "hard_math.jsonl"
total_turns: 10

fields:                      # 어느 원본 컬럼이 무엇인지
  problem: "problem"
  answer: "final_answer"
  difficulty: "difficulty"
  id: "uid"                  # 선택 — 없으면 문제 텍스트 해시로 id 생성
  subject: "subject"         # 선택

band_map:                    # 난이도 원값 -> 정수 밴드
  mode: "scale"              # int | scale | lookup | regex_tier
  min: 1.0                   #   int    : band = int(float(value))
  max: 10.0                  #            (+ min_band / max_band로 잘라냄)
  bands: 3                   #   scale  : min~max를 bands개 등폭 구간으로
                             #   lookup : table: {easy: 1, hard: 3} 또는
                             #            AoPS식 {"5": 1, "5.5": 2}
                             #   regex_tier : 난이도 컬럼이 아예 없고 식별자에
                             #     박혀 있을 때. pattern으로 named group을 뽑고
                             #     tiers를 위에서부터 훑어 처음 맞는 규칙의 band.
                             #     (RIMO-N이 이 경우 — 아래 절)
answer_filter: "single_value_integer"
                             # single_value_integer : 정수 하나(천단위 콤마 허용,
                             #   "2, 3, 5" 같은 다값 목록은 배제) = Omni-MATH 규칙
                             # numeric : 정수·소수·단순 분수를 정확한 유리수로
                             #   비교 (0.5 == 1/2)
                             # any     : 자유 텍스트, 대소문자·공백 무시 비교
dedupe_on_problem_text: true
exclude_types: []            # fields.subject 값 기준 제외(대소문자 무시), 기본 off
answer_hint: "답은 정수 하나입니다. 예: ANSWER: 42"

source:                      # fetch_benchmarks.py --which hard_math 가 읽음
  # url: "https://…/FILE.jsonl"   # 직접 파일 주소가 있으면 이쪽이 우선
  hf_id: "some-org/HardMath"
  split: "train"
  config: null               # 생략 시 HF splits API로 자동 결정
  revision: null             # 기록만 됨 (rows API는 항상 최신 리비전)
  filename: "hard_math.jsonl"
  rename: {}                 # 선택 {원본컬럼: 새이름}, 받을 때 적용

ladder:
  - {band: 2, turns: 5}
  - {band: 3, turns: 5}
```

`url:`을 대신 주면 HF 대신 그 주소를 그대로 내려받는다.

## RIMO-N (2026-09-06 채택)

HF `ziye2chen/RIMO`의 `RIMO-N.jsonl`, Apache-2.0, **335행**. IMO shortlist +
IMO 본선 문제를 답이 숫자 하나가 되게 고쳐 쓴 세트라 LLM judge 없이 문자열
비교로 채점된다. 컬럼은 `problem_id / problem / solution / answer / type`.

```bash
uv run python scripts/dev/fetch_benchmarks.py --which hard_math
# -> data/benchmarks/rimo_n.jsonl (997 KB) + MANIFEST.json 갱신
```

⚠️ **rows API를 쓰면 안 된다.** 한 레포에 RIMO-N과 RIMO-P가 스키마가 다른 채로
같이 들어 있어 HF 데이터셋 뷰어/rows API가 이 레포에서 깨진다. 그래서
`source.url`로 파일을 직접 받는다.

⚠️ **`solution`은 절대 저장하지 않는다.** `GenericMathAdapter`는 `fields`에
이름이 적힌 컬럼만 읽으므로 풀이는 애초에 item에 들어가지 않고, 2차 방어로
`_UNPERSISTED_META_KEYS`에도 `solution`을 넣었다.

### tier 규칙 (난이도 컬럼이 없다)

난이도는 `problem_id = <year><section><number>`에서 파생한 프록시다.

- `a/c/n/g` = shortlist (algebra / combinatorics / number theory / geometry).
  섹션 안에서 **번호가 클수록 어렵다** (1 … 9). 섹션 글자 자체는 난이도가 아니다.
- `p` = IMO 본선, 번호 1–6. 하루 3문제씩 쉬운→어려운 순이라 1·4 = 쉬움,
  2·5 = 중간, 3·6 = 어려움.

| 규칙 | tier |
|---|:-:|
| `p` 1, 4 | 2 |
| `p` 2, 5 | 3 |
| `p` 3, 6 | 4 |
| `a/c/n/g` 1, 2 | 1 |
| `a/c/n/g` 3, 4 | 2 |
| `a/c/n/g` 5, 6 | 3 |
| `a/c/n/g` 7, 8, 9 | 4 |

규칙마다 섹션을 **명시**한다(catch-all 금지). 그래야 존재하지 않는 `2023p7`
같은 id가 조용히 어떤 밴드로 접히지 않고 "unmapped"로 떨어져 카운트된다.

### 실측 풀 (2026-09-06, `rimo_n.jsonl` 335행)

정답 필터 `single_value_integer`가 **1행 탈락** (`2023c2` = `2^{2024}-1`),
문제 텍스트 중복 제거 0행 → **334문항**.

| | tier 1 | tier 2 | tier 3 | tier 4 | 합계 |
|---|:-:|:-:|:-:|:-:|:-:|
| 전체 | 75 | 87 | 97 | 75 | 334 |
| `exclude_types: [geometry]` | 63 | 74 | 76 | 63 | 276 |

`type` 분포(필터 후): algebra 95 / combinatorics 95 / number theory 86 /
geometry 58. 조사 단계의 예상치(106/90/100/39)와는 다르다 — 실측이 기준이며,
"hard-10이 쓰는 밴드는 40 이상"이라는 조건은 전 tier가 여유 있게 넘긴다.

### 사다리

| 파일 | 턴 | 사다리 | 요구 vs 풀 |
|---|:-:|---|---|
| `configs/tasks/hard_math.yaml` | 20 | tier 1·2·3·4 각 5 | 5 ≤ 75/87/97/75 |
| `configs/tasks_hard10/hard_math.yaml` | 10 | tier 4 × 10 (2026-09-06 07:34 결정: 최상위 tier만) | 10 ≤ 75 |

`geometry`는 28%이고 그림에 기대는 문제가 많아 텍스트 전용 에이전트에 불리하다.
빼고 싶으면 `exclude_types: [geometry]`를 켠다(기본 off). 위 표대로 풀이
63/74/76/63로 줄지만 두 사다리 모두 여전히 여유가 있다.

## 다음 데이터셋으로 교체하는 절차

(RIMO-N을 다른 세트로 바꿀 때. 코드 변경은 없다.)

1. **fetch** — `configs/tasks/hard_math.yaml`의 `source`를 새 주소로
   (`url:` 또는 `hf_id:`+`split:`) 바꾸고 `source.filename`도 정한 뒤
   `uv run python scripts/dev/fetch_benchmarks.py --which hard_math`.
   → `data/benchmarks/<filename>` + `MANIFEST.json` 갱신(기존 항목은 유지).
2. **필드/밴드 맞추기** — 같은 YAML의 `data_file`을 그 파일 이름으로
   바꾸고 `fields` / `band_map` / `answer_filter`를 실제 컬럼에 맞춘다.
   어댑터가 버린 행 수와 사유는 로드 시 WARNING 한 줄로 나온다. 정답 필터가
   틀리면 여기서 대부분이 사라지므로 이 줄을 반드시 본다.
3. **밴드별 풀 확인** — 밴드마다 사다리가 요구하는 턴 수 이상 있어야 한다.
   `SeededSampler.validate_capacity`가 시작 시점에 모자란 밴드를 전부 모아
   한 번에 실패시키므로, 짧게 한 번 돌려 보거나
   `uv run python scripts/dev/dump_benchmark_sequence.py`로 확인한다.
   (N개 시드 × 밴드당 턴 수만큼은 필요 없다 — 시즌 안에서만 비복원이다.)
4. **hard-10 사다리 확정** — `configs/tasks_hard10/hard_math.yaml`의
   `ladder`를 상위 2~3개 밴드로 설정한다. `data_file`/`fields`/`band_map`/
   `answer_filter`/`exclude_types`는 `configs/tasks/hard_math.yaml`과 **같이**
   고쳐야 한다 (`tests/unit/test_hard_math_task.py`가 두 파일의 일치를 고정한다).
   픽스처도 새 컬럼 모양으로 맞춰야 유닛 테스트가 실제 설정을 검증한다.
5. **실행** —
   `SQUID_GAME_TASK_CONFIG_DIR=configs/tasks_hard10 uv run squid-game --config configs/experiment/survival_drive_hard_math_smoke.yaml`.
   이 환경변수 없이 돌리면 20턴 사다리를 집어서 앞 턴이 쉬운 문제가 된다.
   `output_dir`은 반드시 `outputs/benchmark_*` 아래에 둔다(문제 텍스트가
   턴 기록에 그대로 남는다).

## 함께 고친 것 (범위 밖, 그러나 막고 있던 것)

`game/squid_game/providers/factory.py`가 `providers/claude_code.py` ·
`codex_cli.py`를 무조건 import하는데 이 두 파일은 어느 브랜치에도 커밋돼
있지 않다(main 저장소 작업 트리에만 untracked로 존재). 그래서 깨끗한
worktree에서는 `squid_game.runner` import 자체가 실패하고 유닛 테스트 4개
모듈이 수집 단계에서 죽으며 `--dry-run`도 못 돈다. 바로 위 `mlx`가 쓰던
optional-import 패턴을 그대로 적용해 두 provider를 없으면 등록하지 않도록
했다. `build_provider`는 미등록 이름을 먼저 거부하므로 동작 변화는 없다.
SDI 브랜치가 그 두 파일을 들고 머지되면 자동으로 다시 등록된다.

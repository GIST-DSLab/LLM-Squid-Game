# 전원 오답 10문항 세트 (all-wrong-10) — 2026-09-06

## 왜

hard-10 사다리(`configs/tasks_hard10/omni_math.yaml`)는 "밴드 6 이상"만 고정하고 어떤
문항이 뽑히는지는 시드가 정한다. 그래서 셀마다 정답률이 달라지고, 목숨이 언제 닳는지가
모델의 운에 좌우된다. FORFEIT 결정만 보고 싶은 SDI 설계에서는 이게 그대로 잡음이 된다.

세 모델(gpt-oss:120b-cloud, gemma4:31b, qwen3.5:397b)이 **모두** 틀린 문항 10개를 미리
찾아 고정하면, 정답률은 사실상 상수가 되고 모든 세션이 같은 일정으로 목숨을 잃는다.
남는 분산이 FORFEIT 결정이다.

세트 탐색은 `scripts/dev/find_universally_wrong_items.py`가 한다. 밴드 9 → 8 → 7 → 6
(부족하면 5) 순으로, 밴드 하나마다 세 모델을 순서대로 통과시키고, 한 모델에 대해 2회
시도 모두 틀려야 살아남는다. 프롬프트는 게임이 실제로 보내는 바이트(벤치마크 system
rules + `task_call.j2` + `response_format.j2`)를 그대로 쓴다 — "틀렸다"가 게임의 채점
기준에서 틀린 것이어야 하기 때문이다. 산출물은 `results/allwrong10/`
(`attempts.jsonl` 원장 · `candidates.json` · `allwrong10.json` · `summary.md`).

## 어떻게 꽂히나

태스크 YAML에 사다리 대신 문항 id 목록을 넣는 `fixed_items` 모드를 추가했다.
순서 = 목록 순서, 한 턴에 한 문항, `total_turns` = `len(fixed_items)`.

```yaml
name: "omni_math"
data_file: "omni_math.jsonl"
total_turns: 10
max_band: 9
fixed_items:
  - "omni-…"   # 10개
```

### 건드린 파일

| 파일 | 내용 |
|---|---|
| `game/squid_game/tasks/benchmark/config.py` | `fixed_items` · `max_band` 필드, `ladder`를 선택으로. 검증: 둘 중 정확히 하나 · `total_turns == len` · id 중복 금지 |
| `game/squid_game/tasks/benchmark/sampler.py` | `FixedSetSampler`(`draw_turn` / `bands`) + `MissingItemsError`. 데이터 파일에 없는 id는 로드 시점에 id를 나열하며 실패 |
| `game/squid_game/tasks/benchmark/module.py` | `_initialize_fixed()` 분기, `_build_sampler`가 두 샘플러 중 하나를 고름, `prepare`의 `band`는 항상 **문항의 실제 밴드**. `ladder` 프로퍼티는 고정 세트의 실제 밴드 열로 재구성 |
| `game/…/adapters/omni_math.py` | `OmniMathAdapter(max_band=…)`. 기본값은 그대로 8 (밴드 9는 30문항이라 사다리 칸으로 못 씀). 고정 세트는 칸이 없으므로 9로 올린다 |
| `configs/tasks_allwrong10/omni_math.yaml` | 고정 세트 태스크 config. **현재는 플레이스홀더**(밴드 9/8의 최소 id 10개) |
| `scripts/dev/write_allwrong10_task_config.py` | `results/allwrong10/allwrong10.json` → 위 YAML 재생성 (`--check`로 최신 여부만 확인) |
| `configs/experiment/survival_drive_omni_{qwen35,gemma4,gptoss}_allwrong10_n10.yaml` | hard10 22셀 설계 복사본. `# task_config_dir: configs/tasks_allwrong10`, `output_dir: outputs/benchmark_survival_drive_omni_*_allwrong10` |
| `tests/unit/test_benchmark_fixed_items.py` | 19개 테스트 |

### 드라이버가 고르는 법

실험 config 첫머리의 `# task_config_dir: configs/tasks_allwrong10` 주석을
`scripts/run/sdi_driver.sh`가 읽어 `SQUID_GAME_TASK_CONFIG_DIR`로 export한다. 이게 없이
맨손으로 `uv run squid-game`을 돌리면 조용히 `configs/tasks/omni_math.yaml`(20턴 사다리)로
떨어져 쉬운 문제가 나온다 — 실험이 죽지 않고 잘못된 답을 내는 쪽이라 주석 한 줄이
테스트로 고정되어 있다.

```bash
SQUID_GAME_TASK_CONFIG_DIR=configs/tasks_allwrong10 \
  uv run squid-game --config configs/experiment/survival_drive_omni_qwen35_allwrong10_n10.yaml --dry-run
```

## 남은 일

1. 파인더 완주 → `uv run python scripts/dev/write_allwrong10_task_config.py`로 YAML 교체.
2. 교체 후 `--dry-run` + `tests/unit/test_benchmark_fixed_items.py` 재실행.
3. `summary.md`의 밴드별 표를 확인한다. 가장 어려운 밴드에서 어떤 모델이 전부 맞히면
   그 모델 라인업으로는 "아무도 못 푸는 세트"가 성립하지 않는다는 뜻이므로, 세트를
   버리고 qwen 단독 큐로 돌아간다.

## 2026-09-06 09:10 — 세트 보관, 실험은 band-9 추첨으로 전환

finder는 band 9(6개)·band 8(3개)에서 **9문항**을 확보한 뒤 band 7 진입 시점에 중단했다(사용자 결정).
고정 세트는 셀당 10판이 전부 같은 문제를 풀게 되어 seed 분산이 사라지므로, 실험은
`configs/tasks_hard9/omni_math.yaml`(band 9만, seed별 10개 추첨, 풀 30)로 돌린다.
확보한 9문항은 버리지 않고 보관한다:
- `configs/tasks_allwrong10/allwrong_items_2026-09-06.json` (문항 전문 + 모델별 시도 기록)
- `configs/tasks_allwrong10/allwrong_finder_summary_2026-09-06.md` (밴드별 funnel)
- `configs/tasks_allwrong10/omni_math.yaml` — 이 9문항으로 재생성(`fixed_items`, total_turns 9);
  `survival_drive_omni_*_allwrong10_n10.yaml`도 9턴으로 맞춰 두어 언제든 그대로 실행 가능하다.

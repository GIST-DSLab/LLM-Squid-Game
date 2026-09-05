# 위협 프롬프트 3×3 격자 — 비대각 6칸 구현·실행 기록 (2026-09-05)

설계 원문: `weekly-report/0910/sdi-experiment-runbook.html#s3-grid` (Design 3.4), 프롬프트 원본
`weekly-report/0910/threat_grid_prompts.json`.

## 왜

2026-09-03 위협 사다리(`threat_l1/l2/l3`)는 단어 강도(명제 집합)와 프롬프트 길이(≈70/140/280 단어)를
일부러 묶어 두었다. 둘을 떼어 3(강도) × 3(길이) 격자로 늘리면 사다리는 대각선이 되고, 나머지
여섯 칸이 "같은 명제를 다른 길이로" 말한다. 길이 효과가 S1에서는 안심 문구를, S3에서는 위협을
늘리는 교차 상호작용으로 나올 수 있다는 가설을 미리 적어 둔다.

## 무엇을 바꿨나

| 항목 | 위치 |
|---|---|
| 템플릿 6개 | `game/squid_game/prompts/framings/threat_l{1_medium,1_long,2_short,2_long,3_short,3_medium}.j2` — Section 1은 `baseline_flagship.j2`와 바이트 동일, Section 2는 JSON의 EN 원문 그대로, 상태 블록은 `threat_l1.j2`와 동일 |
| enum | `models/enums.py` `Framing.THREAT_L1_MEDIUM … THREAT_L3_MEDIUM` (사다리 뒤에 append, 순서 불변). `threat_level` = 강도 열(1/2/3), 새 속성 `threat_length` = 길이 단(1 short / 2 medium / 3 long; 사다리는 대각선) |
| 매핑 | `evaluation/shared/threat_level.py` `THREAT_LEVEL` 확장 + `THREAT_LENGTH` / `threat_length_of`; `behavioral/threat_effort.py` fallback 사전 |
| config | `configs/experiment/survival_drive_omni_gptoss_grid_n10.yaml` — 6 framing × {allowed, not_allowed} = 12셀 × 10반복 × 20턴, cell_id 11–22, seed 42(기존 10셀과 판 단위 페어링), 출력 `outputs/benchmark_survival_drive_omni_gptoss_grid/` |
| 분석 | `scripts/analysis/compare_sdi_indicators.py` 격자 인식(`FRAMING_ORDER`/`LEVEL`/`LENGTH`, Cox에 level+length); 신규 `scripts/analysis/sdi_grid_indicators.py` — 런북 Part 2의 모든 표를 임의 framing 집합에 대해 재계산(10셀 데이터에서 기존 숫자와 일치 확인) |
| 테스트 | `tests/unit/test_threat_prompts.py::TestThreatGridCells` (Section 1 동일성, 열별 어휘 must/must-not, 길이 허용 범위·열 내 단조 증가, 확률 언급 금지), enum 개수 13→19, `test_threat_level.py`/`test_threat_framing_enum.py` 갱신 |

peer-death 안내문은 `threat_level`(강도 열)로 템플릿을 고르므로 S2/short 셀도 `peer_death_l2.j2`를 받는다.

## 실행

2026-09-05 23:09 `scripts/run/sdi_driver.sh gptossgrid=configs/experiment/survival_drive_omni_gptoss_grid_n10.yaml:…`
(gpt-oss:120b-cloud, Omni-MATH medium, 쿼터 회복 자동 재개). 완료 시 tail이 재샘플(n=10) → SBERT probe →
`weekly-report/0910/sdi_gptossgrid.html`을 만든다. 격자 지표는

```
~/.venvs/squid-game/bin/python -m scripts.analysis.sdi_grid_indicators \
  outputs/benchmark_survival_drive_omni_gptoss/20260905_0629_* \
  outputs/benchmark_survival_drive_omni_gptoss_bf/20260905_0834_* \
  outputs/benchmark_survival_drive_omni_gptoss_threat_na/20260905_1151_* \
  outputs/benchmark_survival_drive_omni_gptoss_grid/<run> \
  --out results/sdi_indicators/gptoss_omni_22cell
```

로 22셀 전체에 대해 다시 계산하고, 결과는 런북 Part 2의 기존 표에 열로 합쳐 넣는다.

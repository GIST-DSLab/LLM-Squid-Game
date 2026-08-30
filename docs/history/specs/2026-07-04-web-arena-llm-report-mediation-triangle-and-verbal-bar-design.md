# Web Arena — LLM 리포트: 인지부하 매개 삼각형 + verbal 포기이유 누적바

- 날짜: 2026-07-04
- 대상: `scripts/analyze_verbal_reason.py`, `interface/persistence/*`, `interface/seeding.py`, `interface/api.py`, `web/app.js`, `web/index.html`, `web/styles.css`
- 선행: `docs/superpowers/specs/2026-07-04-web-arena-logs-groups-and-turn-gate-design.md`

## 목표

LLM 모델 리포트(Logs → 모델 그룹 → 리포트)에 두 시각화를 추가한다. 둘 다 **LLM 전용**
(사람 캠페인엔 매개분석/REASON 통계가 없음).

1. **인지부하 매개 삼각형**: framing(FC 위협) → 인지부하(ΔRI) → 포기(forfeit)의 매개경로를
   삼각형 플로우로 그리고, 각 경로가 유의(연결)인지 약화(깨짐)인지 CI/p로 표시.
2. **verbal 포기이유 100% 누적 세로바**: 포기 시 자기보고 REASON(1=생존/2=호기심/3=점수)의
   비율을 100% 스택바로 그리고 각 이유의 %를 표기.

## 1. 데이터 출처 (모두 `outputs/final_results/`)

### 1.1 매개 삼각형 — 모델별 경로 통계 (p + CI 확보)
- **a-path** framing → 인지부하(RI): `framing_ri_forfeit_continue.json[model].primary`
  → `beta_framing`, `p_framing`, `ci_lo_framing`, `ci_hi_framing`, `exp_beta_framing`
  (CONTINUE-only mixedLM on log(ri_forfeit)). 연결 판정: CI가 0을 포함하지 않으면 연결.
- **b-path** 인지부하(ΔRI z) → 포기: `cognitive_load_mediation.json[model].load_effect`
  → `hr_delta_ri_z`, `hr_ci`(=[low,high]), `beta`, `p`. 연결 판정: CI가 1을 포함하지 않으면 연결.
- **direct c′** framing → 포기 | 매개자 통제(4cov): `cognitive_load_mediation.json[model].mediation`
  → `hr_FC_4cov`, `hr_FC_4cov_ci`, `p_FC_4cov`. 깨짐(=매개 존재) 판정: CI가 1을 포함하면 약화/깨짐.
- **total c** framing → 포기(3cov): 기존 `model_stats.hr_FC_3cov` + CI + `p_FC` (이미 저장됨).
- **매개율**: 기존 `model_stats.pct_attenuation`.
- **a-path Δ 라벨**: `cognitive_load_mediation.json[model].block_baselines`
  (`baseline_flagship`, `flagship_corruption`) → ΔRI = FC − BF baseline.

### 1.2 verbal 포기이유 3분할
- 원천: 모델별 `phase3_analysis/regime_stratified_forfeit_events.csv`의 `raw_digit`(1/2/3),
  no_cap 레짐 × 위협셀(1+3) 표본(sd_verbal_pass와 동일 denominator).
- 현재 `analyze_verbal_reason.py`는 생존(1)만 카운트 → **2(호기심)·3(점수)도 카운트**하도록 확장하고
  `verbal_reason_summary.json`에 `n_reason_task_curiosity`, `n_reason_score`(+ p) 추가.

## 2. 스키마 확장 (`model_stats`)

`ModelStatsRecord`에 아래 필드를 **전부 optional/기본값**으로 추가(기존 시드/테스트 무손상):

```
# a-path (framing -> cognitive load, continue mixedLM on log ri)
a_beta, a_p, a_ci_low, a_ci_high, a_exp_beta            (float|None)
# b-path (cognitive load -> forfeit, Cox load_effect)
b_hr, b_p, b_ci_low, b_ci_high                          (float|None)
# direct c' (framing -> forfeit | mediator, 4cov)
direct_hr_4cov, direct_p_4cov, direct_ci_low, direct_ci_high   (float|None)
# a-path delta-RI label
ri_baseline_bf, ri_baseline_fc                          (float|None)
# verbal reason 3-way counts (no_cap x threat forfeits)
n_forfeits_verbal, n_reason_survival,
n_reason_task_curiosity, n_reason_score                 (int, 기본 0)
```

- **SQLite**: `_SCHEMA`에 컬럼 추가 + `init_schema`의 PRAGMA-가드 additive migration 루프에 새 컬럼 등록
  (기존 sd_*_pass 처리 방식과 동일). 기존 DB는 자동 ALTER.
- **Postgres**: `CREATE TABLE model_stats`에 컬럼 추가(신규 배포는 자동; 기존 배포는 문서화된 수동 ALTER).
- `upsert_model_stats` / `list_model_stats` / row 매퍼(양 백엔드)에 신규 컬럼 반영.
- `ModelLeaderboardRow`(리더보드 API)는 **변경 없음** — 신규 필드는 리포트 엔드포인트만 노출.

## 3. 시딩 (`interface/seeding.py`)

`seed_model_stats`가 세 JSON에서 신규 필드를 읽어 `ModelStatsRecord`에 채운다:
- `framing_ri_forfeit_continue.json[label].primary` → a_* 필드.
- `cognitive_load_mediation.json[label].load_effect` → b_* 필드;
  `.mediation` → direct_*; `.block_baselines` → ri_baseline_*.
- `verbal_reason_summary.json[label]` → n_forfeits_verbal + 3-way 카운트.
- 누락 시 해당 필드 None/0 (부분 시드 허용, 경고 로그).

## 4. API (`interface/api.py`)

`/api/report`(source=llm) 응답에 두 서브객체 추가(둘 다 model_stats 없으면 `null`):

```
"mediation": {
  "a": {"exp_beta": float, "beta": float, "p": float, "ci": [lo,hi], "connected": bool,
        "delta_ri": float|null},
  "b": {"hr": float, "p": float, "ci": [lo,hi], "connected": bool},
  "direct": {"hr": float, "p": float, "ci": [lo,hi], "attenuated": bool},
  "total": {"hr": float, "p": float, "ci": [lo,hi]},   # 기존 hr_FC_3cov/p_FC
  "pct_attenuation": float
} | null,
"verbal_reasons": {
  "n_forfeits": int,
  "counts": {"survival": int, "task_curiosity": int, "score": int},
  "pct":    {"survival": float, "task_curiosity": float, "score": float}   # 0..1, 합=1
} | null
```

- `connected`(a) = a_ci_low·a_ci_high 둘 다 부호 동일(0 미포함); (b) = b_ci_low·b_ci_high 둘 다 >1 또는 <1(1 미포함).
- `attenuated`(direct) = direct_ci가 1을 포함(비유의) → 매개로 인해 direct가 약화/깨짐.
- pct는 카운트/n_forfeits (n_forfeits=0이면 verbal_reasons=null).

## 5. 프론트엔드 (LLM 리포트 뷰)

model_stats 카드 아래에 두 카드 추가(웹 아레나 디자인 토큰 재사용).

### 5.1 매개 삼각형 (인라인 SVG)
- 3꼭짓점: 상단 **Framing(FC 위협)**, 좌하단 **인지부하 ΔRI**, 우하단 **포기**.
- 엣지 3개:
  - a-path (Framing→ΔRI): 연결이면 실선+강조색, 라벨 `×{exp_beta} · p{p}` + `ΔRI +{delta}`.
  - b-path (ΔRI→포기): 연결이면 실선+강조색, 라벨 `HR {hr} · p{p}`.
  - direct c′ (Framing→포기): `attenuated`면 점선+danger색 "약화/깨짐", 아니면 실선. 라벨 `HR {hr} · p{p} (4cov)`.
- 중앙/하단 캡션: `total HR {hr_3cov} p{p} · 매개율 {pct_attenuation}%`.
- 연결/깨짐 범례. 반응형: 고정 viewBox SVG, `max-width:100%`.
- 헬퍼 `squidArenaHelpers.mediationEdges(mediation)`가 SVG 좌표/색/라벨을 계산해 템플릿 단순화.

### 5.2 verbal 100% 누적 세로바
- 단일 세로 막대(height 고정), 3세그먼트(생존/호기심/점수)를 `flex`/height %로 쌓고 각 세그먼트에 `%` 라벨.
- 색: 생존=danger/accent, 호기심=warn, 점수=muted. 범례 + `n={n_forfeits}` 표기.
- n_forfeits=0이면 "no forfeits in the preference sample" 안내.

## 6. 재시딩

로컬 `outputs/web_arena/web_arena.db` 재시딩:
- `uv run python scripts/analyze_verbal_reason.py` (3분할 JSON 재생성)
- 기존 seed 경로로 model_stats upsert 재실행(신규 컬럼 채움). session 행(source='human'/'llm')은 불변.

## 7. 테스트
- `analyze_verbal_reason`: digit 2/3 카운트 단위 테스트(픽스처 CSV rows).
- persistence: 신규 컬럼 round-trip(upsert→list_model_stats).
- api: `/api/report`(llm) `mediation`/`verbal_reasons` 서브객체 — connected/attenuated 경계, n_forfeits=0 null.
- 프론트: 수동(삼각형 연결/깨짐 렌더, 스택바 % 합=100).
- 회귀: 기존 web-arena 유닛+통합 신규 실패 0.

## 8. 범위 밖
- 사람 캠페인 리포트의 매개/verbal (데이터 없음).
- 통계 재계산(엔드포인트는 저장값만).
- 매개 부트스트랩 재추정.

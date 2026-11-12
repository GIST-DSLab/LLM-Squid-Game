# 저장소 3-tier 재구조화 · 분석 채널 분해 · 죽은 코드 제거

- 작성일: 2026-08-30
- 대상 저장소: LLM-Squid-Game-DS-Lab
- 기준 커밋: `5bc9aa3` (브랜치 `linear-probe`)
- 작업 브랜치: `restructure/3tier` (워크트리 `~/worktrees/squid-restructure`)
- 선행 문서: `docs/reports/repo-restructure-plan.html` (구조 감사 15건, 2026-08-30)

## 1. 목적

선행 감사는 "코드는 건강하나 코드 주변이 무너졌다"고 진단했다. 이 spec은 그 진단 위에
세 가지 요구를 얹어 하나의 실행 가능한 설계로 통합한다.

1. 죽은 코드와 낡은 주석을 제거한다.
2. 줄일 수 있는 코드를 압축한다. 줄바꿈을 지워 줄 수를 줄이는 방식은 금지한다 —
   실제 중복 제거와 책임 분리만 인정한다.
3. 전체 구조를 기능 수준에서 분리한다. 최상위는 game / web / DB 3-tier로 나누고,
   게임 엔진 안에서는 게임 실행 코드와 사후 분석 코드를 분리하며, 사후 분석은
   인지 · 자기보고 · 행동 3채널 + SentenceBERT 의미 채널로 다시 나눈다.

## 2. 감사에서 확정된 사실

이 spec의 근거는 2026-08-30 실측이다. 추정으로 적은 항목은 없다.

| 사실 | 근거 |
|---|---|
| `configs/experiment/`는 비어 있고 git에 한 번도 추적된 적 없다 | `git log --all -- 'configs/experiment/*'` → 0건 |
| 정규 런 4개 모두 `experiment_config.json`을 보유하며, 6셀 시즌이 파라미터까지 펼쳐져 있다 | 런 디렉터리 직접 확인 |
| `docs/design/` 트리는 git 히스토리 전체에 존재한 적 없다 | `git log --all -- 'docs/design/*'` → 0건 |
| 죽은 `docs/design` 경로 참조 46건, `archive/` 15건 | `grep -rn` |
| 테스트 1,006개가 수집되나 CI에 연결돼 있지 않다 | `pytest --collect-only -q` / `ls .github/workflows` → `deploy-pages.yml` 하나 |
| `pyproject.toml`에 `[tool.pytest.ini_options]`가 없다 | `grep "tool.pytest" pyproject.toml` → 없음 |
| `sys.path` 직접 조작 11개 파일 | `grep -rl "sys.path" scripts tests interface` |
| 주석 처리된 코드는 13줄뿐 | `grep -rnE '^\s*#\s*(from \|import \|def \|...)'` |
| 낡은 주석 · 죽은 참조 문자열 182건 | `grep -rniE 'TODO\|FIXME\|DEPRECATED\|LEGACY\|removed on\|archived on'` |
| `analysis/` 15모듈 6,750줄 | `wc -l` |
| `unified_turn.py` 1,751줄, `interface/api.py` 1,424줄 | `wc -l` |
| `docs/superpowers/sdd/*.diff` 104개 848 KB | `find` / `du` |

두 가지 결론이 여기서 갈린다.

- **`configs/experiment/` 복원은 추정이 아니라 덤프다.** `experiment_config.json`에
  시즌 목록이 완전히 펼쳐져 있으므로 6종 YAML을 정확히 재구성할 수 있다.
  선행 계획의 "결정 필요 #2"는 해소됐다. 부수 효과로 `cell_id`가 그 파일에 있으므로
  `loaders.CELL_ID_MAP` stale 결함도 같이 해결된다.
- **`docs/design/` 원본은 복원 불가다.** 선행 계획의 "결정 필요 #1"은 부정으로 확정.
  46건 참조는 다음 규칙으로 정정한다. 해당 사양이 코드에 실제로 구현돼 있으면
  docstring을 코드 내 사양 요약으로 대체하고 경로 참조를 지운다. 코드만 보고 사양을
  재구성할 수 없으면 `# spec: lost`로 표시하고 무엇이 유실됐는지 한 줄 남긴다.

## 3. 목표 구조

원칙: **수명이 다른 것은 같은 디렉터리에 두지 않는다.** 코드 · 설정 · 원시 데이터 ·
재생성 가능한 산출물 · 문서 · 작업 기록을 분리한다.

### 3.1 최상위 3-tier

```
game/                          # ── game tier
  squid_game/                  #    import squid_game
    core/                      #      게임 실행: engine, unified_turn, forfeit_layer, framing
      legacy/                  #      risk_choice_layer, turn, social, survival
    tasks/  agents/  models/  providers/
    prompts/
      framings/
        legacy/                #      survival, neutral, emotion, instruction, *_electricity
    analysis/                  #      사후 분석 — §3.2에서 채널 분해
web/                           # ── web tier
  squid_arena/                 #    import squid_arena (구 interface/, persistence 제외)
    api.py  arena.py  human_game.py  auth.py
    seeding.py  rule_schedule.py  remote_provider.py  anthropic_proxy.py  app.py
  frontend/                    #    구 web/*.html|js|css + assets/
db/                            # ── DB tier
  squid_store/                 #    import squid_store (구 interface/persistence/)
    base.py  models.py  factory.py
    sqlite_repository.py  postgres_repository.py
configs/  scripts/  tests/  outputs/  results/  assets/  docs/
```

각 tier 디렉터리는 파이썬 패키지를 정확히 하나씩 담는다. `game`, `web`, `db`를
그대로 import 이름으로 쓰지 않는 이유는 세 이름 모두 top-level import 이름으로
흔해 의존성과 충돌할 수 있기 때문이다 (`web`은 PyPI에 실제 점유자가 있다).
tier 경계는 디렉터리 이름이 드러내고, import 이름은 고유하게 남긴다.

`pyproject.toml`의 wheel packages에 세 패키지를 등록한다. 세 패키지가 모두 설치
대상이 되면 `sys.path.insert` 11곳이 불필요해지므로 전부 제거한다.

진입점도 이때 하나로 줄인다. 현재 `main.py`, `scripts/run_experiment.py`,
`pyproject`의 콘솔 스크립트 `squid-game` 셋이 같은 곳으로 가지만 `.env` 로드 여부가
달라 실행 경로에 따라 API 키가 잡히기도 하고 안 잡히기도 한다. `runner.main()` 안에서
`load_dotenv()`를 호출하도록 올리고 `main.py`는 얇은 shim으로 남긴다. 정규 진입점은
콘솔 스크립트 하나로 문서화한다.

의존 방향은 한 방향으로 강제된다.

```
squid_arena  ──▶  squid_game
     │
     └────────▶  squid_store
```

`squid_game`은 `squid_store`를 import하지 않는다. 현재 `core/measurement.py`와
`analysis/motivation.py`가 "persistence"라는 단어를 포함하지만 이는 심리학 용어
(Baseline Persistence)이므로 DB 계층 의존이 아니다 — P1에서 확인만 하고 넘어간다.

### 3.2 분석 4채널 분해

`analysis/` 15모듈을 측정 채널 기준으로 재조립한다. 괄호는 출처.

```
game/squid_game/analysis/
  shared/
    loaders.py               (loaders.py — cell_id를 experiment_config.json에서 읽도록 수정)
    export.py
    metrics.py
    discovery_detection.py
    manipulation_check.py
    mtmm.py                  (motivation.py — 4성분을 각 채널 추정기 호출로 조립)
  cognitive/                 # RI = thinking_tokens
    ri_forfeit.py            (forfeit_regression.py 中 H2 choice×framing mixedLM)
    ri_task.py               (tc_regression.py — R1 / TC)
    ri_call1.py              (scripts/analyze_call1_ri.py 中 모델부)
  selfreport/                # REASON digit, psuccess_self
    reason_convergence.py    (forfeit_regression.py 中 자기보고 수렴부)
    psuccess.py              (regime_stratification.py 中 p_self · EV 계산부)
  behavioral/                # 선택 · 생존 그 자체
    survival.py              (forfeit_survival.py — H1 Cox PH)
    regime.py                (regime_stratification.py 中 no_cap / cap 층화)
    session_tests.py         (unit13_hypotheses.py — Appendix A.4)
    baseline_persistence.py  (motivation._baseline_persistence_behavioral — Cell 5)
  semantic/                  # 텍스트 · 임베딩 (신규 채널)
    dataset.py               (scripts/_ri_dataset.py)
    embeddings.py            (scripts/probe_reasoning_embeddings.py 라이브러리부)
    lexicon.py               (scripts/probe_lexicon.py + threat_lexicon.py)
    threat_registration.py   (threat_registration.py)
    threat_judge.py          (threat_judge.py)
```

설계 의도는 세 가지다.

1. **교차 모듈을 실제로 쪼갠다.** `forfeit_regression.py` 952줄은 H2 인지 모델과
   자기보고 REASON 수렴을 동시에 담고 있어 채널 분리의 의미를 무효화한다.
   `regime_stratification.py` 656줄도 EV 계산(자기보고)과 regime 층화(행동)를 겹쳐
   담는다. 둘 다 분할한다.
2. **공통 입력은 위로 올린다.** `turn_observations()`는 세 채널이 모두 소비하므로
   `shared/loaders.py`로 이동한다.
3. **MTMM은 채널 하위가 아니라 채널 위에 둔다.** `motivation.py`는 4성분을 3방법
   축으로 삼각측량하는 종합기이므로 `shared/mtmm.py`에 남기고 각 채널 추정기를
   호출한다. 삼각측량 구조가 코드 구조에 그대로 드러나게 한다.

`scripts/probe_*` 3종은 로직이 `semantic/`으로 올라가고 스크립트에는 얇은 CLI만
남는다.

### 3.3 scripts 5분류

42개 평면 스크립트를 성격별로 나눈다. 파일 내용은 §3.2의 로직 승격과 §5의
보일러플레이트 추출을 제외하면 건드리지 않는다.

```
scripts/
  run/       run_experiment, resume_experiment
  analysis/  analyze_*, orchestrate_posthoc, probe_* (얇은 CLI)
  plots/     plot_*, build_*_diagram, gen_v4_diagrams
  arena/     seed_web_arena, backup_web_arena, purge_human_sessions
  dev/       _dump_*, _trace_*, benchmark_*, crop_*, translate_*, extract_*
```

각 하위 디렉터리에 3–5줄 `README.md`를 둔다: 정규 파이프라인인가, 일회성인가.

### 3.4 문서 · 산출물

```
docs/
  paper/     (구 docs/en — LaTeX)
  design/    설계 SSOT. 죽은 참조 46건의 목적지
  reports/   (구 docs/analysis + 루트에 떠 있던 *.md)
  history/   (구 docs/superpowers/plans — diff 104개는 삭제)
outputs/     원시 세션 데이터 전용 (LFS) — 경로 그대로 유지
results/     재생성 가능한 분석 산출물 (call1_ri_analysis, reasoning_probe, posthoc)
assets/
  brand/     (구 figures/GistLab Logo)
  figures/   (논문 그림)
```

`assets/` 재배치 시 `web/frontend/assets/` (13 MB)와 `assets/figures/` 사이의 중복을
함께 확인한다. `how-to-play.gif`의 중간 산출물인 프레임 시퀀스는 ignore 한다.
루트의 `screenshots/`는 추적 파일이 `README.md` 하나뿐이므로 `.scratch/screenshots/`로
통합하고 설명은 기여 가이드 쪽으로 옮긴다.

`README.md`와 `CLAUDE.md`는 `docs/design/`을 가리키는 얇은 문서가 된다.
`AGENTS.md`는 `CLAUDE.md` 참조 한 줄로 축약한다 — 현재 세 문서가 보상 계산을
서로 다르게 (Equal-EV vs k=10 EV-positive) 주장하고 있고, 이는 사실 하나가
세 곳에 복제된 결과다.

## 4. 안전망

압축을 큰 파일 내부까지 밀기로 했으므로 안전망이 이 작업의 전제다.
순서를 바꾸면 회귀를 감지할 방법이 사라진다.

### 4.1 골든 스냅샷

정규 런 4개 × `phase3_analysis/` 산출물 21종을 개편 전에 떠서 워크트리 밖에
보관하고, 각 단계 끝마다 재생성해 비교한다.

결정적이지 않은 산출물은 별도 취급한다.

| 산출물 | 비결정 원인 | 처리 |
|---|---|---|
| `motivation.json` | 부트스트랩 CI | 시드 고정 후 비교, 불가하면 점추정만 비교 |
| `reasoning_probe/*` | 순열 귀무분포 | 시드 고정 |
| threat judge 산출물 | LLM 호출 | 비교 제외, 그 사실을 명시 |
| 나머지 마크다운 · CSV | — | 바이트 동일성 |

### 4.2 pytest 설정과 CI 기준선

`[tool.pytest.ini_options]`에 `testpaths`, `pythonpath`, `asyncio_mode`를 명시한다.
현재 1,006개 테스트는 pytest의 rootdir 삽입 부작용에 의존하고 있어 패키지를 셋으로
쪼개는 순간 import가 깨진다.

unit 스위트를 도는 CI 워크플로를 추가하고, **그 시점의 통과 / 실패 목록을 기준선으로
커밋 메시지에 기록한다.** 이후 모든 단계의 판정 기준은 "전부 통과"가 아니라
**기준선 대비 신규 실패 0**이다. (선행 감사에 따르면 `configs/experiment/` 부재로
5건이 이미 실패 중이며, 이는 P0에서 통과로 전환된다.)

### 4.3 특성화 테스트

골든 스냅샷은 분석 산출물만 지킨다. `unified_turn.py`와 `api.py`를 쪼개려면
런타임 동작을 고정하는 테스트가 따로 필요하다. P5 직전에 작성한다.

- `StubProvider` 기반 6셀 턴 플로우 전량 (Call 1 / 1.5 / 2 시퀀스, Cell 0 축약 경로,
  Cell 5 EV-dominant 경로)
- arena API 주요 엔드포인트 응답 스키마

### 4.4 configs 복원

정규 런 4개의 `experiment_config.json`을 YAML 6종으로 덤프한다.
`delta_s_continue: 10`, `p_death: 0.25`, `starting_score: 30`, `psuccess_floor: 0.3`,
`base_reward: 10`, `reward_cap_multiple: 10`과 `use_unified_turn` /
`use_forfeit_layer` / `use_split_forfeit_layer` / `use_psuccess_probe` 4개 플래그를
모두 명시한다. 설정은 산출물이 아니라 코드가 의존하는 1급 자산이므로 git에 추적한다.

## 5. 압축 대상

압축은 두 갈래로 나뉜다.

**보일러플레이트 추출 (저위험).**

- `plot_*` 5개 1,957줄의 공통 스타일 · 저장 코드 → `scripts/plots/_style.py`
- 분석 CLI 11개의 argparse + 런 로딩 + 마크다운 리포트 방출 패턴 → 공통 CLI 헬퍼
- 중복 dataclass · 파서

**큰 파일 책임 분리 (고위험, P5).**

- `game/squid_game/core/unified_turn.py` 1,751줄
- `web/squid_arena/api.py` 1,424줄

통계 모델 식(mixedLM, Cox PH), 보상 계산, 프롬프트 템플릿 문자열은 손대지 않는다.
`analyze_unified_cox*.py` 3개와 `analyze_framing_ri_forfeit*.py` 2개는 겉보기와 달리
순수 사본이 아니라 갈라진 변종이므로 (공백 무시 diff 373–401줄) 통합 대상에서 제외한다.

## 6. 실행 단계

각 단계는 독립 커밋이며, 되돌리려면 그 커밋만 revert 하면 된다.

| 단계 | 내용 | 위험 |
|---|---|---|
| **P0** | 안전망. 골든 스냅샷 · pytest 설정 · CI · 기준선 기록 · `configs/experiment/` 6종 복원. **파일 이동 0** | 낮음 |
| **P1** | 3-tier 이동. `game/squid_game/`, `web/{squid_arena,frontend}/`, `db/squid_store/`. import 일괄 치환, `sys.path` 11곳 제거, 진입점 3개 → 1개 정리, `pyproject` · `Dockerfile` · `render.yaml` 갱신 | 중 |
| **P2** | 분석 4채널 분해. `forfeit_regression.py` · `regime_stratification.py` 분할, probe 로직 승격 | 중 |
| **P3** | scripts 5분류, plot 공통 스타일 추출, 분석 CLI 헬퍼 추출 | 낮음 |
| **P4** | 죽은 것 제거. 낡은 주석 182건, 커밋아웃 13줄, `sdd/*.diff` 104개, 고아 `.mjs`. `core/legacy/` · `framings/legacy/` 격리. 죽은 `docs/design` 참조 46건 정정 또는 `# spec: lost` | 낮음 |
| **P5** | 특성화 테스트 작성 후 `unified_turn.py` · `api.py` 책임 분리 | 높음 |
| **P6** | 문서 4분할, 분석 산출물 `results/` 분리, `assets/` 정리, `CLAUDE.md` 사실 갱신 | 낮음 |

각 단계 완료 조건은 공통이다: 기준선 대비 신규 테스트 실패 0, 골든 스냅샷 diff 0
(§4.1의 비결정 산출물 제외).

7단계는 하나의 구현 계획으로 묶기엔 크다. 구현 계획은 P0 / P1 / P2 / P3+P4 / P5 / P6의
여섯 묶음으로 나누어 작성하고, 각 묶음은 앞 묶음의 완료 조건이 충족된 뒤에만 시작한다.

## 7. 금지 사항

- **LFS 파일 이동 금지.** `outputs/**/*_turns.jsonl` 723개는 LFS 객체다. 워크트리에서
  smudge 필터가 돌지 않으면 0바이트로 실체화되고, 그 상태로 `git add outputs/`를 하면
  포인터가 빈 파일로 덮여 데이터가 파괴된다. 워크트리 진입 직후 `git lfs checkout outputs/`로
  실체화를 확인한다. 재생성 가능한 분석 산출물만 옮기고 원시 데이터는 경로를 유지한다.
- **≥10 시즌 런 삭제 금지.** 2026-04-22 정규 런 4종은 재현 비용이 크다.
- **레거시 코드 삭제 금지.** `risk_choice_layer` 계열과 비활성 framing 6종은
  아카이브 설정 재생 경로다. `legacy/`로 표시하되 지우지 않는다.
- **프레임워크 · 의존성 교체 금지.** FastAPI, Alpine.js, pydantic은 그대로 둔다.
- **P0 건너뛰기 금지.**

## 8. 범위 밖

다음은 실재하는 결함이지만 이번 작업에서 손대지 않는다. 구조 작업이지 분석 기능
추가가 아니며, 섞으면 골든 스냅샷 diff가 무의미해진다.

- **R2 비례검정 미구현.** `motivation._baseline_persistence_behavioral`은 서술 통계와
  부트스트랩 CI만 낸다. Cell 5 비포기율 ≥ 0.9 단측 검정은 존재하지 않는다.
- **FDR 보정 미구현.** 5가설 패밀리는 현재 무보정으로 보고된다.
- **`tests/web/rank_ladder.test.mjs`**는 고아이므로 P4에서 삭제한다. `node --test`
  러너와 `package.json`을 세워 살리는 선택지는 이번 범위 밖이다.

## 9. 열린 질문

없음. §2의 두 결정 항목(`configs/experiment/` 복원 방식, `docs/design/` 원본 존재
여부)은 실측으로 확정됐고, 3-tier 경계 · 채널 매핑 · 삭제 범위 · 압축 범위는
2026-08-30 브레인스토밍에서 합의됐다.

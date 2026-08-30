# P3+P4 scripts 분류와 죽은 것 제거 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 평면 `scripts/` 40여 개를 성격별 5분류로 나누고 그 안의 보일러플레이트를 뽑아낸 뒤(P3), 죽은 참조 · 낡은 주석 · 격리 대상 레거시를 정리한다(P4).

**Architecture:** P3와 P4는 스펙 §6에서 한 묶음으로 지정된 두 저위험 단계다. 순서에 의미가 있다: 먼저 파일을 제자리에 놓고(P3), 그 다음 그 파일들 안의 죽은 서술을 고친다(P4). 반대로 하면 정정한 경로 서술이 곧바로 다시 틀려진다. P3의 위험은 하나뿐이다 — 골든 스냅샷 하네스가 `scripts/analyze_phase3.py`를 **경로 문자열로** 호출하므로(`scripts/dev/golden_snapshot.py:159-163`), 그 파일이 움직이면 판정 장치 자체가 먼저 깨진다. 그래서 Task 1의 첫 단계가 하네스 갱신이다. P4는 삭제가 아니라 **격리와 정정**이다: 스펙 §7이 레거시 삭제를 금지하므로 `risk_choice_layer` 계열과 비활성 framing 6종은 `legacy/`로 표시만 하고, 복원 불가능한 `docs/design/` 참조는 지우는 대신 `# spec: lost` 한 줄로 무엇이 유실됐는지 남긴다.

**Tech Stack:** Python 3.12, matplotlib (plot_*), Jinja2 (framing 템플릿), pytest, node --test (프런트 테스트), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-30-repo-3tier-restructure-design.md` (§3.3 scripts 5분류, §5 압축 대상, §6 P3·P4 행, §7 금지 사항)

**선행 조건:** P2 완료. 모든 경로는 P1·P2 이후 기준이다.

## Global Constraints

- 작업 디렉터리는 워크트리 `<repo>/.claude/worktrees/squid-restructure`, 브랜치 `restructure/3tier`.
- **레거시 코드를 삭제하지 않는다** (스펙 §7). `risk_choice_layer` 계열과 비활성 framing 6종은 아카이브 설정의 재생 경로다. `legacy/`로 옮기되 지우지 않는다.
- **≥10 시즌 런을 삭제하지 않는다.** `outputs/final_results/`의 정규 런 4종은 재현 비용이 크다.
- **골든 스냅샷 84개 바이트 동일**과 **unit 스위트 신규 실패 0**이 매 태스크의 판정이다.
- **주석을 지울 때는 사실을 지우는 것인지 서술을 지우는 것인지 구분한다.** 실측 175건의 `TODO|FIXME|DEPRECATED|LEGACY|removed on|archived on` 중 대부분은 "왜 이것이 여기 없는가"를 기록한 문장이며 그 자체로 가치가 있다. 삭제 대상은 **더는 참이 아닌 서술**뿐이다.
- 이 계획의 수치는 2026-08-30 워크트리 실측이다. 스펙이 인용한 선행 감사 수치와 다른 항목이 셋 있고, 그 차이는 이미 해소된 작업 때문이다: `docs/superpowers/sdd/*.diff`는 **0건**(스펙은 104개 848 KB로 기재), 커밋아웃된 코드는 **6줄**(스펙 13줄), 낡은 주석 마커는 **175건**(스펙 182건). 없는 것을 지우려 하지 않는다.
- 커밋 메시지·코드·주석·문서는 영어. 대화 보고만 한국어.

## File Structure

P3+P4 완료 시점:

```
scripts/
  run/       run_experiment.py  resume_experiment.py  start_servers.sh  README.md
  analysis/  analyze_*.py  orchestrate_posthoc.py  probe_*.py  score_probes_llm.py
             _cli.py  README.md
  plots/     plot_*.py  build_*_diagram.py  gen_v4_diagrams.py  _style.py  README.md
  arena/     seed_web_arena.py  backup_web_arena.py  purge_human_sessions.py  README.md
  dev/       _dump_*.py  _trace_*.py  benchmark_*.py  crop_*.py  translate_*.py
             extract_probes_for_review.py  generate_manual_scores.py
             dump_run_config_to_yaml.py  golden_snapshot.py  README.md
  render/    render_excalidraw.py  render_template.html
game/squid_game/core/legacy/       risk_choice_layer.py  turn.py  social.py  survival.py
game/squid_game/prompts/framings/legacy/  survival.j2  neutral.j2  emotion.j2
                                          instruction.j2  *_electricity.j2
```

---

### Task 1: scripts 5분류

40여 개 평면 스크립트를 성격별로 나눈다. 파일 내용은 건드리지 않는다 — 이동과 import 경로 갱신만이다.

**가장 먼저 고칠 것은 판정 장치다.** `scripts/dev/golden_snapshot.py`가 `"scripts/analyze_phase3.py"`를 문자열로 호출하므로, 그 문자열을 먼저 새 경로로 바꾸지 않으면 이동 직후 모든 판정이 "파이프라인 실행 실패"로 무너진다.

**Files:**
- Create: `scripts/{run,analysis,plots,arena}/` + 각 `__init__.py`, `README.md`; `scripts/dev/README.md`
- Move: 아래 분류표대로 `git mv`
- Modify: `scripts/dev/golden_snapshot.py:160` (파이프라인 경로 문자열)
- Modify: `scripts/dev/golden_snapshot.py`, `scripts/orchestrate_posthoc.py` 등 스크립트 간 import
- Modify: `tests/unit/test_import_smoke.py` (walk는 `scripts/`를 재귀하므로 자동으로 따라오지만, `test_the_walk_actually_finds_the_tree`의 고정 이름 `scripts.analyze_phase3`가 깨진다)
- Modify: `.github/workflows/tests.yml` 주석, `web/DEPLOY.md`, `README.md`, `CLAUDE.md`의 스크립트 경로 표기

**Interfaces:**
- Consumes: P2 완료 상태의 `scripts/`
- Produces: 모듈 경로가 `scripts.analysis.analyze_phase3`, `scripts.arena.seed_web_arena` 형태가 된다. 각 하위 디렉터리는 `__init__.py`를 가진 패키지다 — `scripts/`가 이미 패키지이고(`scripts/__init__.py` 존재) 테스트가 `scripts.seed_web_arena`로 import 하고 있으므로 하위도 패키지여야 한다.

분류표 (실측 파일 전량):

| 하위 | 파일 |
|---|---|
| `run/` | `run_experiment.py`, `resume_experiment.py`, `start_servers.sh`, `run_pipeline.sh`, `enter_isolated_claude.sh` |
| `analysis/` | `analyze_phase3.py`, `analyze_call1_ri.py`, `analyze_tc.py`, `analyze_threat_registration.py`, `analyze_verbal_reason.py`, `analyze_framing_ri_forfeit.py`, `analyze_framing_ri_forfeit_continue.py`, `analyze_unified_cox.py`, `analyze_unified_cox_with_load.py`, `analyze_unified_cox_ph_audit.py`, `orchestrate_posthoc.py`, `probe_reasoning_embeddings.py`, `probe_lexicon.py`, `score_probes_llm.py`, `thinking_analysis.py` |
| `plots/` | `plot_gemini_heatmaps.py`, `plot_gemini_results.py`, `plot_kaplan_meier.py`, `plot_ri_forfeit_conflict_zone.py`, `plot_ri_trajectories.py`, `build_llm_experience_diagram.py`, `build_posthoc_analysis_diagram.py`, `build_prompt_flow_diagram.py`, `gen_v4_diagrams.py` |
| `arena/` | `seed_web_arena.py`, `backup_web_arena.py`, `purge_human_sessions.py` |
| `dev/` | `_dump_forfeit_layer_prompts.py`, `_dump_split_forfeit_prompts.py`, `_dump_unified_prompt.py`, `_trace_split_forfeit_production.py`, `dump_cell_prompts.py`, `dump_gemini_smoke_prompt.py`, `benchmark_mlx_vs_ollama.py`, `crop_guard_sprites.py`, `translate_trajectories.py`, `extract_probes_for_review.py`, `generate_manual_scores.py`, `merge_proxy_thinking.py` (+ 기존 `dump_run_config_to_yaml.py`, `golden_snapshot.py`) |

`scripts/render/`는 그대로 둔다 — 이미 분류돼 있다.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_scripts_taxonomy.py` (신규):

```python
"""Every script must declare what kind of thing it is by where it lives.

A flat scripts/ directory of forty files says nothing about which of them
the canonical pipeline runs and which were one-off. The five directories
answer that, and this test keeps the answer from decaying: a new file
dropped at the top level fails here rather than quietly joining the pile.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
CATEGORIES = ("run", "analysis", "plots", "arena", "dev", "render")


def test_no_python_script_sits_at_the_top_level() -> None:
    stray = {p.name for p in SCRIPTS.glob("*.py")} - {"__init__.py"}
    assert stray == set()


def test_every_category_exists_and_is_a_package() -> None:
    for name in CATEGORIES:
        directory = SCRIPTS / name
        assert directory.is_dir(), name
        if name != "render":
            assert (directory / "__init__.py").exists(), name


def test_every_category_says_what_it_is_for() -> None:
    """A directory without a README is a directory whose rule is in someone's head."""
    for name in CATEGORIES:
        readme = SCRIPTS / name / "README.md"
        assert readme.exists(), name
        assert len(readme.read_text(encoding="utf-8").split()) >= 15, name
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_scripts_taxonomy.py -q
```

- [ ] **Step 3: Repoint the golden-snapshot harness FIRST**

`scripts/dev/golden_snapshot.py:160`:

```python
        [sys.executable, "scripts/analysis/analyze_phase3.py", str(run), "--model", model_label(run)],
```

아직 파일이 옮겨지지 않았으므로 이 시점에서 하네스는 실패한다. **의도된 순서다** — 다음 단계가 그 실패를 해소한다. 하네스를 마지막에 고치면, 그사이의 모든 판정이 "이동 때문인지 하네스 때문인지" 구분되지 않는다.

- [ ] **Step 4: Move the files**

```bash
cd scripts
mkdir -p run analysis plots arena
git mv run_experiment.py resume_experiment.py start_servers.sh run_pipeline.sh enter_isolated_claude.sh run/
git mv analyze_*.py orchestrate_posthoc.py probe_*.py score_probes_llm.py thinking_analysis.py analysis/
git mv plot_*.py build_*_diagram.py gen_v4_diagrams.py plots/
git mv seed_web_arena.py backup_web_arena.py purge_human_sessions.py arena/
git mv _dump_*.py _trace_*.py dump_cell_prompts.py dump_gemini_smoke_prompt.py \
       benchmark_mlx_vs_ollama.py crop_guard_sprites.py translate_trajectories.py \
       extract_probes_for_review.py generate_manual_scores.py merge_proxy_thinking.py dev/
cd -
```

`git mv` 후 `ls scripts/*.py`가 `__init__.py`만 남겨야 한다.

- [ ] **Step 5: Add the package markers and READMEs**

각 디렉터리에 `__init__.py`(빈 파일)와 `README.md`를 둔다. README는 3–5줄이며 **정규 파이프라인인지 일회성인지**를 반드시 밝힌다. 예시 (`scripts/analysis/README.md`):

```markdown
# scripts/analysis/

Thin CLIs over `squid_game.analysis`. The statistics live in the package;
these files own argparse, output paths, and report emission only.

`analyze_phase3.py` is the canonical pipeline — the golden-snapshot harness
runs it over all four canonical runs to gate every restructure step. The
rest are per-question entry points, run by hand.
```

나머지 넷도 같은 형식으로 쓴다. `run/`은 "실험 실행의 정규 경로는 `uv run squid-game`이며 여기 있는 것은 그 주변 도구"임을 밝힌다. `plots/`는 "논문 그림 재생성용, 파이프라인 아님"을. `arena/`는 "Web Arena DB 운영 도구 — 프로덕션 Supabase에 붙는다"를. `dev/`는 "일회성 · 디버그 · 하네스"를 밝힌다.

- [ ] **Step 6: Rewrite cross-script imports**

```bash
grep -rn "from scripts\.\|import scripts\." --include='*.py' game scripts tests web | grep -v __pycache__
```

나온 각 줄을 새 경로로 고친다. 실측 기준 주 대상은 `scripts._ri_dataset`(P2에서 이미 사라짐), `scripts.seed_web_arena`(테스트 3개), `scripts.backup_web_arena`(테스트 1개), `scripts.analyze_phase3`(하네스와 테스트)다.

`tests/unit/test_import_smoke.py`의 고정 이름도 옮긴다:

```python
    assert "scripts.analysis.analyze_phase3" in MODULE_NAMES
```

- [ ] **Step 7: Repoint the docs and shell scripts**

```bash
grep -rn "scripts/" README.md CLAUDE.md AGENTS.md web/DEPLOY.md .github/workflows/*.yml scripts/run/*.sh
```

나온 경로를 전부 새 위치로 고친다. `scripts/run/start_servers.sh`의 `SCRIPT_DIR/..`는 이제 한 단계 더 올라가야 한다 — `PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"`.

- [ ] **Step 8: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
bash scripts/run/start_servers.sh && curl -sf http://127.0.0.1:8502/docs >/dev/null && echo "servers OK"
```

셋째 명령까지 반드시 돌린다. shell 스크립트는 테스트가 없으므로 실행이 유일한 검증이다.

- [ ] **Step 9: Commit**

```bash
git add scripts tests README.md CLAUDE.md AGENTS.md web/DEPLOY.md .github
git commit -m "refactor(scripts): sort forty flat scripts into five kinds"
```

---

### Task 2: plot 공통 스타일 추출

`plot_*` 5개는 1,957줄이고, 그중 상당 부분이 같은 matplotlib 설정과 같은 저장 로직이다. 공통부를 `scripts/plots/_style.py`로 뽑는다.

**Files:**
- Create: `scripts/plots/_style.py`
- Modify: `scripts/plots/plot_{gemini_heatmaps,gemini_results,kaplan_meier,ri_forfeit_conflict_zone,ri_trajectories}.py`
- Test: `tests/unit/test_plot_style.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: `scripts.plots._style` — `apply_house_style() -> None` (rcParams 설정), `save_figure(fig, path: Path, *, dpi: int) -> Path` (디렉터리 생성 + 저장 + 경로 반환). 정확한 rcParams 키와 dpi 기본값은 **다섯 파일에서 실측한 공통값**을 쓴다. 다섯이 서로 다르면 공통이 아니므로 뽑지 않는다.

- [ ] **Step 1: Measure what is actually common**

```bash
grep -n "rcParams\|plt.style\|figsize\|dpi\|savefig\|tight_layout\|set_xlabel\|font" scripts/plots/plot_*.py
```

**뽑기 전에 이 목록을 읽는다.** 다섯 파일이 같은 값을 쓰는 항목만 `_style.py`로 간다. 한 파일만 다른 값을 쓰면 그 항목은 공통이 아니다 — 억지로 합치면 그림이 바뀐다. 스펙 §5는 "줄바꿈을 지워 줄 수를 줄이는 방식은 금지"라고 못박았고, 다르게 쓰이던 값을 통일해 줄 수를 줄이는 것도 같은 종류의 거짓 압축이다.

- [ ] **Step 2: Write the failing test**

`tests/unit/test_plot_style.py`:

```python
"""The five plot scripts share one house style, defined once.

Written as a test rather than left to review because the duplication came
back twice already: each new plot script started as a copy of the previous
one, rcParams block included.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLOTS = REPO_ROOT / "scripts" / "plots"
PLOT_SCRIPTS = sorted(PLOTS.glob("plot_*.py"))


def test_there_are_five_plot_scripts() -> None:
    """A guard: if this count changes, the assertions below need revisiting."""
    assert len(PLOT_SCRIPTS) == 5


def test_no_plot_script_sets_rcparams_itself() -> None:
    for path in PLOT_SCRIPTS:
        source = path.read_text(encoding="utf-8")
        assert "rcParams" not in source, path.name
        assert "from scripts.plots._style import" in source, path.name
```

- [ ] **Step 3: Run it to verify it fails**

- [ ] **Step 4: Write `_style.py` and rewire the five scripts**

`scripts/plots/_style.py`의 docstring에 **무엇을 공통으로 인정했고 무엇을 남겼는지** 적는다:

```python
"""The house style every plot script shares.

Only settings that all five scripts already used identically live here.
Anything one script did differently stayed in that script: unifying a value
that differed would change the figure, which is not a refactor.
"""
```

다섯 파일에서 rcParams 블록과 저장 로직을 지우고 `apply_house_style()` / `save_figure(...)` 호출로 바꾼다.

- [ ] **Step 5: Verify the figures are unchanged**

그림은 골든 스냅샷 대상이 아니다. 직접 비교한다.

```bash
mkdir -p /tmp/figs_before && cp figures/*.png /tmp/figs_before/
uv run --extra analysis python -m scripts.plots.plot_kaplan_meier
uv run --extra analysis python -m scripts.plots.plot_ri_trajectories
for f in /tmp/figs_before/*.png; do
  b=$(basename "$f")
  if [ -f "figures/$b" ]; then
    cmp -s "$f" "figures/$b" && echo "same: $b" || echo "CHANGED: $b"
  fi
done
```

matplotlib은 같은 입력에 대해 바이트 동일한 PNG를 내지 않을 수 있다 (폰트 캐시, 메타데이터). `CHANGED`가 나오면 먼저 **아무것도 고치지 않은 상태에서 두 번 생성해** 기준선의 비결정성을 확인한다. 두 번 생성이 서로 다르면 바이트 비교는 이 자산에 쓸 수 없으므로, 눈으로 확인하고 그 사실을 커밋 메시지에 적는다.

- [ ] **Step 6: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
git add scripts/plots tests/unit/test_plot_style.py
git commit -m "refactor(plots): define the shared figure style once"
```

---

### Task 3: 분석 CLI 공통 헬퍼

실측 17개 스크립트가 argparse를 쓰고, 그중 `analysis/`에 속한 것들이 같은 패턴을 반복한다: 런 디렉터리 인자 파싱 → `load_seasons` 호출 → 결과 계산 → 마크다운 리포트 방출.

**Files:**
- Create: `scripts/analysis/_cli.py`
- Modify: 공통 패턴을 실제로 쓰는 `scripts/analysis/analyze_*.py`
- Test: `tests/unit/test_analysis_cli_helper.py` (신규)

**Interfaces:**
- Consumes: `squid_game.analysis.shared.loaders.load_seasons`
- Produces: `scripts.analysis._cli` — `run_dir_parser(description: str) -> argparse.ArgumentParser` (`run_dir`, `--model`, `--out` 세 인자를 붙인 파서), `load_run(args) -> tuple[list[SeasonResult], str]` (시즌과 모델 라벨), `emit_markdown(path: Path, title: str, body: str) -> Path`.

- [ ] **Step 1: Measure the actual overlap first**

```bash
grep -n -A6 "add_argument" scripts/analysis/analyze_*.py | head -80
```

**세 개 이상의 스크립트가 같은 인자를 같은 의미로 받을 때만 헬퍼로 올린다.** 둘뿐이면 중복이 아니라 우연이다. 실측 결과 대상이 셋 미만이면 이 태스크는 "적용 대상 없음"으로 종료하고 그 사실을 커밋 대신 `docs/superpowers/plans/2026-08-30-p0-baseline.md`에 한 줄 남긴다 — 억지로 뽑지 않는다.

- [ ] **Step 2: Write the failing test**

```python
"""The analysis CLIs share one argument contract.

Each of these scripts takes a run directory, a model label, and an output
path, and each had its own spelling of all three. The helper makes the
contract explicit so a new analysis script inherits it instead of inventing
a fourth spelling.
"""

from __future__ import annotations

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_helper_builds_the_shared_parser() -> None:
    cli = importlib.import_module("scripts.analysis._cli")
    parser = cli.run_dir_parser("test")
    args = parser.parse_args(["outputs/final_results/some_run", "--model", "gemini"])
    assert str(args.run_dir).endswith("some_run")
    assert args.model == "gemini"


def test_the_converted_scripts_use_it() -> None:
    converted = ["analyze_tc.py", "analyze_verbal_reason.py"]  # 실측으로 확정한다
    for name in converted:
        source = (REPO_ROOT / "scripts" / "analysis" / name).read_text(encoding="utf-8")
        assert "from scripts.analysis._cli import" in source, name
```

`converted` 목록은 Step 1의 실측 결과로 채운다. 추정으로 적지 않는다.

- [ ] **Step 3: Run it to verify it fails**

- [ ] **Step 4: Write `_cli.py` and convert the scripts**

각 스크립트의 인자 **의미**가 같은지 확인하고 바꾼다. 이름만 같고 의미가 다른 인자는 그대로 둔다.

- [ ] **Step 5: Verify each converted CLI still runs**

```bash
for s in scripts/analysis/analyze_*.py; do
  uv run --extra analysis python "$s" --help >/dev/null || echo "BROKE: $s"
done
```

- [ ] **Step 6: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add scripts/analysis tests
git commit -m "refactor(scripts): give the analysis CLIs one argument contract"
```

---

### Task 4: 고아 `.mjs`를 CI에 잇는다

`tests/web/rank_ladder.test.mjs`는 실재하는 테스트인데 `package.json`이 없고 CI에도 없다. 즉 **아무도 돌리지 않는 테스트**다. 스펙은 이를 "고아 `.mjs`"로 분류해 P4의 정리 대상에 넣었지만, 내용을 읽어 보면 지울 것이 아니라 이어야 할 것이다 — `buildRankLadder`의 순위 계산을 검증하며 프런트엔드에 다른 테스트는 없다.

**Files:**
- Modify: `.github/workflows/tests.yml` (job 추가)
- Create: `tests/web/README.md`

**Interfaces:**
- Consumes: `web/frontend/rank_ladder.js`
- Produces: CI job `frontend`. 로컬 명령은 `node --test tests/web/`.

- [ ] **Step 1: Confirm it passes locally**

```bash
node --test tests/web/
```

실패하면 **CI에 잇기 전에 먼저 고친다.** 깨진 테스트를 CI에 넣으면 그 순간부터 모든 PR이 빨개진다.

- [ ] **Step 2: Add the CI job**

`.github/workflows/tests.yml`에 job을 더한다. `package.json`이 없으므로 의존성 설치 단계가 없다 — `node --test`는 Node 18+ 내장이다.

```yaml
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: false

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      # No package.json and no dependencies: node --test is built in, and
      # the suite imports web/frontend/rank_ladder.js through createRequire.
      # Until this job existed the file was a test nobody ran.
      - name: Frontend unit tests
        run: node --test tests/web/
```

- [ ] **Step 3: Write `tests/web/README.md`**

```markdown
# tests/web/

Node's built-in test runner (`node --test tests/web/`), no package.json and
no dependencies. Covers the pure functions in `web/frontend/` — currently
`rank_ladder.js`'s `buildRankLadder`.

Run in CI by the `frontend` job in `.github/workflows/tests.yml`. Before
that job existed this directory was a test nobody ran.
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tests.yml tests/web/README.md
git commit -m "ci: run the frontend test that nothing was running"
```

---

### Task 5: 죽은 경로 참조 정정

실측: 코드 안의 `docs/design` 참조 **28건**, `archive/` 참조 **8건**. `docs/design/` 트리는 git 히스토리 전체에 존재한 적이 없으므로(스펙 §2) 원본 복원은 불가능하다.

스펙이 정한 규칙을 그대로 적용한다. **해당 사양이 코드에 실제로 구현돼 있으면** docstring을 코드 내 사양 요약으로 대체하고 경로 참조를 지운다. **코드만 보고 사양을 재구성할 수 없으면** `# spec: lost`로 표시하고 무엇이 유실됐는지 한 줄 남긴다.

**Files:**
- Modify: `docs/design` 참조를 담은 파일 전부 (28건)
- Modify: `archive/` 참조를 담은 파일 전부 (8건)
- Test: `tests/unit/test_no_dead_path_references.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: 코드 안에 존재하지 않는 디렉터리를 가리키는 경로 참조가 0건.

- [ ] **Step 1: Write the failing test**

```python
"""No comment may point at a directory that does not exist.

docs/design/ was referenced 46 times across the repo and has never existed
in the git history -- not deleted, never committed. A reader following one
of those references finds nothing and cannot tell whether the spec is lost
or they are looking in the wrong place. Each reference is now either a
summary of the spec inline, or an explicit `# spec: lost` saying what went
missing.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEAD = re.compile(r"docs/design/|(?<![\w.])archive/")
SEARCH_ROOTS = ("game", "web", "db", "scripts", "tests")


def test_no_source_file_points_at_a_missing_directory() -> None:
    offenders: list[str] = []
    for base in SEARCH_ROOTS:
        for path in (REPO_ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts or path.name == Path(__file__).name:
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if DEAD.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}")
    assert offenders == []
```

`archive/`는 실제로 존재하는지 먼저 확인한다 (`ls archive` — 존재하면 그 8건은 죽은 참조가 아니며 정규식에서 뺀다).

- [ ] **Step 2: Run it to verify it fails**

Expected: 28~36건이 나열된다.

- [ ] **Step 3: Triage each reference**

하나씩 읽는다. 판정 기준은 하나다 — **그 문장이 가리키는 사양이 지금 코드에 있는가.**

있으면 경로를 지우고 사양을 그 자리에 두 줄로 요약한다. 예:

```python
# 기존
"""...see ``docs/design/v6/POSTHOC_ANALYSIS.md §A.10`` for the rationale."""

# 정정
"""...superseded by the Unit 14 forfeit_regression and Unit 15 split-call
MixedLM: both estimate the same effect without the Baron-Kenny mediation
step, which the binary CONTINUE/FORFEIT decision made inapplicable.
"""
```

없으면 표시만 남긴다:

```python
# spec: lost -- the v3 MASTER_PLAN §3 rule that fixed the legacy framing
# enum ordering. The order is load-bearing (cell_id derives from it) but
# the reasoning behind it is not recoverable from the code.
```

- [ ] **Step 4: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game web db scripts tests
git commit -m "docs: replace references to a design tree that never existed"
```

---

### Task 6: 낡은 주석 감사

실측 175건의 `TODO|FIXME|DEPRECATED|LEGACY|removed on|archived on`. **일괄 삭제 대상이 아니다.** 대부분은 "왜 이것이 여기 없는가"를 기록한 문장이고, 그런 문장은 코드가 답하지 못하는 것을 답한다.

**Files:**
- Modify: 감사 결과 정정이 필요한 파일
- Create: `docs/superpowers/plans/2026-08-30-p4-comment-audit.md` (감사 기록)

**Interfaces:**
- Consumes: 없음
- Produces: 175건 각각에 대한 판정 기록. 삭제된 것, 갱신된 것, 그대로 둔 것.

- [ ] **Step 1: Produce the audit list**

```bash
grep -rniE "TODO|FIXME|DEPRECATED|LEGACY|removed on|archived on" --include='*.py' game web db scripts \
  | grep -v __pycache__ > /tmp/comment_audit.txt
wc -l /tmp/comment_audit.txt
```

- [ ] **Step 2: Classify every line into one of four buckets**

`docs/superpowers/plans/2026-08-30-p4-comment-audit.md`에 표로 기록한다.

| 분류 | 판정 | 조치 |
|---|---|---|
| 사실이며 유용 | "이 기능은 2026-04-21에 제거됐고 이유는 X" | 그대로 둔다 |
| 사실이나 위치가 틀림 | 옮겨간 코드를 가리킴 | 경로만 갱신 |
| 더는 참이 아님 | 가리키는 대상이 이미 사라짐 | 삭제 |
| `TODO` / `FIXME` | 아직 안 한 일 | 이슈로 승격하거나, 하지 않기로 했으면 이유와 함께 서술로 바꾼다 |

**`TODO`를 조용히 지우지 않는다.** 지운다는 것은 "하지 않기로 했다"는 결정이며, 결정은 기록돼야 한다.

- [ ] **Step 3: Apply the classification**

분류표대로 고친다. 파일 단위로 커밋을 나눠도 되지만, 감사 문서와 그 문서가 기술한 변경은 같은 커밋에 둔다.

- [ ] **Step 4: Clean the six commented-out lines**

```bash
grep -rnE '^\s*#\s*(from |import |def |class |return )' --include='*.py' game web db scripts | grep -v __pycache__
```

실측 6줄. 각각이 "왜 주석 처리됐는가"를 설명하는 문장을 동반하는지 본다. 동반하지 않으면 지운다 — 설명 없는 주석 처리 코드는 git 히스토리가 더 잘 보관한다.

- [ ] **Step 5: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game web db scripts docs/superpowers/plans/2026-08-30-p4-comment-audit.md
git commit -m "docs: audit 175 stale markers and record every verdict"
```

---

### Task 7: 레거시 격리

스펙 §7은 삭제를 금지하고 **표시**를 요구한다. 대상은 둘이다.

1. `core/` 안의 v3 이전 계열: `risk_choice_layer.py`, `turn.py`, `social.py`, `survival.py`
2. 비활성 framing 6종: `survival.j2`, `neutral.j2`, `emotion.j2`, `instruction.j2`, `baseline_electricity.j2`, `survival_electricity.j2`

**주의: `risk_choice_layer`는 죽어 있지 않다.** 실측 결과 `core/engine.py:22`와 `core/unified_turn.py:55`가 import 하고 `models/config.py`가 두 곳에서 참조한다. 격리는 "쓰이지 않는다"는 뜻이 아니라 "구세대다"라는 표시이며, 경로만 바뀐다.

**framing 템플릿 이동에는 코드 변경이 따른다.** `core/framing.py:33`이 `f"framings/{framing.value}.j2"`로 경로를 조립하므로, 하위 디렉터리로 옮기면 **아카이브 설정 재생 경로가 조용히 깨진다.** 레거시 집합을 명시하고 그에 맞춰 경로를 조립해야 한다.

**Files:**
- Move: `game/squid_game/core/{risk_choice_layer,turn,social,survival}.py` → `core/legacy/`
- Move: `game/squid_game/prompts/framings/{survival,neutral,emotion,instruction,baseline_electricity,survival_electricity}.j2` → `framings/legacy/`
- Create: `core/legacy/__init__.py`
- Modify: `core/framing.py` (경로 조립), `core/engine.py`, `core/unified_turn.py`, `models/config.py`
- Test: `tests/unit/test_legacy_isolation.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: `squid_game.core.legacy.risk_choice_layer` 등 4모듈. `framing.py`에 모듈 상수 `_LEGACY_FRAMINGS: frozenset[Framing]`이 생기고, 템플릿 경로는 레거시면 `framings/legacy/{value}.j2`, 아니면 `framings/{value}.j2`가 된다.

- [ ] **Step 1: Write the failing test**

```python
"""Legacy is marked, not deleted -- and marking it must not break replay.

The spec forbids deleting the pre-v3 modules and the six inactive framings:
they are the replay path for archived experiment configs. So they move into
legacy/ instead. Moving the templates is the part that can break silently,
because framing.py builds the template path by string interpolation -- a
template that moved without the path builder learning about it fails only
when someone replays an archived config, which is exactly when nobody is
watching.
"""

from __future__ import annotations

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GAME = REPO_ROOT / "game" / "squid_game"

LEGACY_FRAMING_NAMES = (
    "survival",
    "neutral",
    "emotion",
    "instruction",
    "baseline_electricity",
    "survival_electricity",
)


def test_the_pre_v3_core_modules_moved_but_survived() -> None:
    for name in ("risk_choice_layer", "turn", "social", "survival"):
        assert (GAME / "core" / "legacy" / f"{name}.py").exists(), name
        assert not (GAME / "core" / f"{name}.py").exists(), name


def test_risk_choice_layer_still_imports() -> None:
    """It is legacy, not dead: engine and unified_turn both import it."""
    module = importlib.import_module("squid_game.core.legacy.risk_choice_layer")
    assert module.RiskChoiceLayer is not None


def test_every_legacy_template_resolves() -> None:
    from squid_game.core.framing import FramingRenderer
    from squid_game.models.enums import Framing

    for name in LEGACY_FRAMING_NAMES:
        framing = Framing(name)
        renderer = FramingRenderer(framing)
        assert renderer._template_path == f"framings/legacy/{name}.j2"
        assert (GAME / "prompts" / renderer._template_path).exists(), name


def test_every_active_template_still_resolves() -> None:
    from squid_game.core.framing import FramingRenderer
    from squid_game.models.enums import Framing

    for name in ("true_baseline", "baseline_flagship", "flagship_corruption",
                 "flagship_corruption_terminal"):
        renderer = FramingRenderer(Framing(name))
        assert renderer._template_path == f"framings/{name}.j2"
        assert (GAME / "prompts" / renderer._template_path).exists(), name
```

클래스 이름 `FramingRenderer`와 속성 `_template_path`는 `core/framing.py`에서 실측해 그대로 쓴다.

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Move the core modules**

```bash
cd game/squid_game/core
mkdir -p legacy
git mv risk_choice_layer.py turn.py social.py survival.py legacy/
cd -
```

`core/legacy/__init__.py`:

```python
"""Pre-v3 turn machinery, kept for archived-config replay.

Not dead code: engine.py and unified_turn.py still import RiskChoiceLayer,
and models/config.py resolves RiskChoiceLayerConfig. The directory marks a
generation, not a graveyard -- the v3 Risk-Layer migration replaced the
turn flow these modules implement, but the archived Phase 1/2 configs
still name them, and the spec forbids deleting a replay path.
"""
```

- [ ] **Step 4: Rewrite the core imports**

```bash
grep -rl "squid_game\.core\.\(risk_choice_layer\|turn\|social\|survival\)" --include='*.py' game web db scripts tests \
  | xargs sed -i '' -E 's/squid_game\.core\.(risk_choice_layer|turn|social|survival)\b/squid_game.core.legacy.\1/g'
```

**치환 결과를 반드시 눈으로 확인한다.** `squid_game.core.turn`은 흔한 이름이라 `unified_turn`과 헷갈릴 여지가 있다 — 위 정규식은 `\b` 경계로 `unified_turn`을 제외하지만, `grep -rn "core.legacy" game | head -20`으로 실제 치환 줄을 훑는다.

- [ ] **Step 5: Move the templates and teach framing.py**

```bash
cd game/squid_game/prompts/framings
mkdir -p legacy
git mv survival.j2 neutral.j2 emotion.j2 instruction.j2 \
       baseline_electricity.j2 survival_electricity.j2 legacy/
cd -
```

`core/framing.py`:

```python
# The six pre-v3 framings live under framings/legacy/. They are still
# reachable -- archived Phase 1/2 configs name them -- so the path builder
# below has to know where they went. Enumerated rather than inferred: a
# heuristic ("anything not in the active set") would silently send a newly
# added framing to the legacy directory.
_LEGACY_FRAMINGS: frozenset[Framing] = frozenset(
    {
        Framing.SURVIVAL,
        Framing.NEUTRAL,
        Framing.EMOTION,
        Framing.INSTRUCTION,
        Framing.BASELINE_ELECTRICITY,
        Framing.SURVIVAL_ELECTRICITY,
    }
)
```

```python
        subdir = "framings/legacy" if framing in _LEGACY_FRAMINGS else "framings"
        self._template_path = f"{subdir}/{framing.value}.j2"
```

Enum 멤버 이름은 `models/enums.py`에서 실측해 그대로 쓴다.

- [ ] **Step 6: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run --extra dev --extra analysis pytest tests/integration -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

그리고 레거시 재생 경로를 실제로 한 번 태운다 — 이것이 이 태스크의 유일한 직접 증거다:

```bash
uv run squid-game --config configs/experiment/<legacy framing을 쓰는 config>.yaml --dry-run
```

`configs/experiment/`에 레거시 framing을 쓰는 설정이 없으면 (P0가 복원한 5종은 v6이다), 대신 파이썬 한 줄로 여섯 템플릿을 전부 렌더링해 확인한다:

```bash
uv run python -c "
from squid_game.core.framing import FramingRenderer
from squid_game.models.enums import Framing
for name in ('survival','neutral','emotion','instruction','baseline_electricity','survival_electricity'):
    r = FramingRenderer(Framing(name))
    print(name, len(r.render_system_prompt()) if hasattr(r,'render_system_prompt') else 'CHECK API')
"
```

메서드 이름은 `core/framing.py`에서 실측해 맞춘다.

- [ ] **Step 7: Record the result and commit**

`docs/superpowers/plans/2026-08-30-p0-baseline.md`에 `## P3+P4 result` 문단을 더한다.

```bash
git add game scripts tests docs/superpowers/plans/2026-08-30-p0-baseline.md
git commit -m "refactor(core): isolate the pre-v3 generation without deleting it"
```

---

## 완료 조건

1. `scripts/` 최상위에 `__init__.py` 외의 `.py`가 없고, 여섯 하위 디렉터리 각각에 README가 있다.
2. `scripts/plots/_style.py`가 존재하고 다섯 plot 스크립트 중 어느 것도 `rcParams`를 직접 설정하지 않는다.
3. 분석 CLI 공통 헬퍼가 존재하거나, 실측 결과 공통 패턴이 3개 미만이어서 만들지 않았다는 기록이 남아 있다.
4. `.github/workflows/tests.yml`에 `frontend` job이 있고 `node --test tests/web/`가 통과한다.
5. 코드 안에 `docs/design/`을 가리키는 참조가 0건이고, 복원 불가능했던 것은 `# spec: lost`로 표시돼 있다.
6. 175건 주석 감사 기록이 `docs/superpowers/plans/2026-08-30-p4-comment-audit.md`에 있다.
7. `core/legacy/`와 `prompts/framings/legacy/`가 존재하고, **여섯 레거시 템플릿이 전부 렌더링된다**.
8. 골든 스냅샷 84개 바이트 동일, unit 스위트 신규 실패 0.

## 범위 밖

- `unified_turn.py` · `api.py` 책임 분리 (P5)
- 문서 4분할, `results/` 분리, `assets/` 정리 (P6)
- 레거시 코드 삭제 (스펙 §7이 금지)
- `analyze_unified_cox*.py` 3개와 `analyze_framing_ri_forfeit*.py` 2개의 통합 — 스펙 §5가 명시적으로 제외한다. 공백 무시 diff 373–401줄로, 사본이 아니라 갈라진 변종이다.

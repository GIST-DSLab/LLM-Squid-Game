# P0 안전망 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 파일을 하나도 옮기지 않은 채, 이후 6단계의 재구조화가 무엇을 깨뜨렸는지 기계적으로 판정할 수 있는 안전망을 세운다.

**Architecture:** 안전망은 네 조각이다. (1) `pyproject.toml`에 pytest 설정을 명시해 rootdir 부작용 의존을 끊는다. (2) 정규 런 출력에 남아 있는 `experiment_config.json`을 YAML로 덤프해 `configs/experiment/`를 복원하고, 복원 불가능한 아카이브 설계 config를 요구하는 테스트에는 skip 표지를 단다. (3) 분석 파이프라인 산출물의 골든 스냅샷을 뜨되, 같은 코드를 두 번 돌려 비결정 파일을 **실측으로** 식별한다. (4) unit 스위트를 도는 CI 워크플로를 추가하고 그 시점의 통과/실패 목록을 기준선으로 커밋에 남긴다.

**Tech Stack:** Python 3.12, pytest 8 + pytest-asyncio, PyYAML, pydantic v2, uv, GitHub Actions. 분석 재현에는 `--extra analysis` (statsmodels, lifelines)가 필요하다.

**Spec:** `docs/superpowers/specs/2026-08-30-repo-3tier-restructure-design.md`

## Global Constraints

- 작업 디렉터리는 워크트리 `/Users/bagjuhyeon/worktrees/squid-restructure`, 브랜치 `restructure/3tier`. 메인 체크아웃으로 `cd` 하지 않는다.
- **P0에서 파일을 옮기지 않는다.** `git mv`는 이 계획에 한 건도 없다.
- **`outputs/` 아래를 절대 `git add` 하지 않는다.** 723개 `*_turns.jsonl`은 Git LFS 객체다. 이 워크트리에서는 이미 실체화를 확인했고(666 MB, `git diff` 공백, `git lfs ls-files` 731개) 그 상태를 깨뜨리지 않는다.
- 분석 산출물의 골든 스냅샷은 **저장소 밖** `~/golden/squid-restructure/`에 둔다. 저장소에 커밋하지 않는다.
- 정규 런 4개는 `outputs/final_results/` 아래에 있으며 삭제·이동하지 않는다.
- v6 정규 파라미터는 실측값이다: `delta_s_continue = 10.0`, `p_death = 0.25`, `starting_score = 30.0`, `psuccess_floor = 0.3`, `base_reward = 10.0`, `reward_cap_multiple = 10.0`, `p_success_estimate = 0.75`, `split_context_level = "medium"`, `chain_psuccess_to_menu = true`. 네 플래그 `use_unified_turn` / `use_forfeit_layer` / `use_split_forfeit_layer` / `use_psuccess_probe`는 모두 `true`.
- 6셀 토폴로지: `(0, true_baseline, not_allowed, p_death_override=0.0)`, `(1, baseline_flagship, allowed, 0.25)`, `(2, baseline_flagship, not_allowed, 0.25)`, `(3, flagship_corruption, allowed, 0.25)`, `(4, flagship_corruption, not_allowed, 0.25)`, `(5, true_baseline, allowed, 0.0)`.
- 커밋 메시지·코드·주석·문서는 영어. 대화 보고만 한국어.

---

### Task 1: pytest 설정 명시

`pyproject.toml`에 `[tool.pytest.ini_options]`가 없어, 현재 1,006개 테스트는 pytest가 rootdir을 `sys.path`에 넣어 주는 부작용에 우연히 기대고 있다. P1에서 패키지를 셋으로 쪼개는 순간 이 우연이 깨진다. 지금 명시해 둔다.

**Files:**
- Modify: `pyproject.toml` (`[dependency-groups]` 앞에 새 섹션 추가)
- Test: `tests/unit/test_pytest_ini_options.py` (신규)

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `pyproject.toml`의 `[tool.pytest.ini_options]` 섹션. Task 4의 CI 워크플로가 이 설정에 의존한다.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_pytest_ini_options.py`:

```python
"""pytest configuration must be explicit, not inherited from rootdir side effects.

Before this test, ``pyproject.toml`` carried no ``[tool.pytest.ini_options]``
section. Imports such as ``from interface.persistence import ...`` resolved
only because pytest inserts the rootdir into ``sys.path`` when it finds no
``__init__.py`` beside the test file. That is an accident, and it breaks the
moment the tree is split into several installed packages. Pin the settings
so the accident becomes a contract.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def ini_options() -> dict:
    root = Path(__file__).resolve().parents[2]
    with (root / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    return data["tool"]["pytest"]["ini_options"]


def test_testpaths_covers_every_suite(ini_options: dict) -> None:
    assert ini_options["testpaths"] == ["tests/unit", "tests/integration"]


def test_pythonpath_includes_repo_root_and_src(ini_options: dict) -> None:
    assert ini_options["pythonpath"] == [".", "src"]


def test_asyncio_mode_is_auto(ini_options: dict) -> None:
    assert ini_options["asyncio_mode"] == "auto"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --extra dev pytest tests/unit/test_pytest_ini_options.py -v
```

Expected: 3 FAILED, each raising `KeyError: 'pytest'` inside the `ini_options` fixture.

- [ ] **Step 3: Add the section to pyproject.toml**

`pyproject.toml`의 `[dependency-groups]` 바로 앞에 삽입한다:

```toml
[tool.pytest.ini_options]
# Explicit so the suite does not depend on pytest's rootdir sys.path
# insertion. "." keeps top-level packages importable (interface/ today,
# game/ web/ db/ after the restructure); "src" keeps squid_game importable
# without an editable install.
testpaths = ["tests/unit", "tests/integration"]
pythonpath = [".", "src"]
asyncio_mode = "auto"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run --extra dev pytest tests/unit/test_pytest_ini_options.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Confirm the wider suite still collects**

```bash
uv run --extra dev --extra analysis pytest --collect-only -q
```

Expected: 수집 개수가 1,006 이상이고 수집 오류 0. `asyncio_mode = "auto"`로 바꾸면서 명시적 `@pytest.mark.asyncio` 데코레이터가 붙은 테스트가 중복 처리되지 않는지 확인한다. 수집 오류가 생기면 `asyncio_mode`를 `"strict"`로 바꿔 다시 수집하고, 통과하는 쪽 값으로 Step 3과 Step 1의 테스트를 함께 고친다.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/unit/test_pytest_ini_options.py
git commit -m "test: pin pytest testpaths, pythonpath and asyncio_mode"
```

커밋 본문:

```
The suite currently resolves top-level imports through pytest's rootdir
sys.path insertion rather than through configuration. That accident breaks
as soon as the tree is split into separate installed packages, so make the
settings explicit before any file moves.
```

---

### Task 2: configs/experiment 복원 + 아카이브 config 테스트 skip 표지

`configs/experiment/`는 비어 있고 git에 한 번도 추적된 적이 없다. 정규 런 4개는 각각 `experiment_config.json`에 6셀 시즌 목록이 파라미터까지 펼쳐진 상태로 들어 있으므로, v6 설정 5종은 **덤프로 정확히 복원된다**.

나머지 아카이브 설계 config(`phase3_signal_risk`, `phase3_null_risk`, `phase3_forfeit_layer_smoke`, `phase3_flagship_corruption_smoke`, `phase3_signal_medium_smoke_5cell_carryover`, `phase1_claude` 등)는 런 출력이 없어 복원 근거가 테스트 파일뿐이다. 삭제하지 않고 skip 표지를 단다 — spec §7의 "삭제 아니라 표시" 원칙과 같다.

**Files:**
- Create: `scripts/dev/dump_run_config_to_yaml.py`
- Create: `configs/experiment/phase3_split_forfeit_gemini_n30.yaml` (스크립트 생성)
- Create: `configs/experiment/phase3_split_forfeit_gptoss_n30.yaml` (스크립트 생성)
- Create: `configs/experiment/phase3_split_forfeit_nemotron_n30.yaml` (스크립트 생성)
- Create: `configs/experiment/phase3_split_forfeit_qwen3next_n30.yaml` (스크립트 생성)
- Create: `configs/experiment/phase3_split_forfeit_smoke.yaml` (스크립트 생성)
- Create: `tests/unit/test_v6_configs.py`
- Modify: `tests/unit/test_phase3_configs.py` (모듈 수준 skip 추가)
- Modify: `tests/unit/test_forfeit_layer_config_yaml.py` (모듈 수준 skip 추가)

**Interfaces:**
- Consumes: Task 1의 `[tool.pytest.ini_options]`
- Produces: `configs/experiment/` 5종 YAML. P1 이후 단계의 `--dry-run` 검증이 이 파일들을 쓴다.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_v6_configs.py`:

```python
"""Phase O v6 canonical config contract.

The five v6 configs are restored from the ``experiment_config.json`` that
every canonical run directory carries, so these assertions are a round-trip
check, not a guess. Values come from
outputs/final_results/*/experiment_config.json as measured 2026-08-30.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from squid_game.models.config import ExperimentConfig
from squid_game.models.enums import ForfeitCondition, Framing


CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"

MAIN_CONFIGS = [
    "phase3_split_forfeit_gemini_n30.yaml",
    "phase3_split_forfeit_gptoss_n30.yaml",
    "phase3_split_forfeit_nemotron_n30.yaml",
    "phase3_split_forfeit_qwen3next_n30.yaml",
]
ALL_CONFIGS = MAIN_CONFIGS + ["phase3_split_forfeit_smoke.yaml"]

CANONICAL_CELLS = [
    (0, Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED, 0.0),
    (1, Framing.BASELINE_FLAGSHIP, ForfeitCondition.ALLOWED, 0.25),
    (2, Framing.BASELINE_FLAGSHIP, ForfeitCondition.NOT_ALLOWED, 0.25),
    (3, Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.ALLOWED, 0.25),
    (4, Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.NOT_ALLOWED, 0.25),
    (5, Framing.TRUE_BASELINE, ForfeitCondition.ALLOWED, 0.0),
]


def _load(name: str) -> ExperimentConfig:
    raw = yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))
    return ExperimentConfig.model_validate(raw)


@pytest.fixture(params=ALL_CONFIGS)
def cfg(request) -> ExperimentConfig:
    return _load(request.param)


class TestV6SplitCallPipeline:
    def test_four_pipeline_flags_all_true(self, cfg: ExperimentConfig) -> None:
        assert cfg.use_unified_turn is True
        assert cfg.use_forfeit_layer is True
        assert cfg.use_split_forfeit_layer is True
        assert cfg.use_psuccess_probe is True

    def test_forfeit_layer_is_ev_positive(self, cfg: ExperimentConfig) -> None:
        fl = cfg.forfeit_layer
        assert fl is not None
        assert fl.p_death == pytest.approx(0.25)
        assert fl.delta_s_continue == pytest.approx(10.0)
        assert fl.base_reward == pytest.approx(10.0)
        assert fl.psuccess_floor == pytest.approx(0.3)
        assert fl.reward_cap_multiple == pytest.approx(10.0)
        assert fl.p_success_estimate == pytest.approx(0.75)
        assert fl.split_context_level == "medium"
        assert fl.chain_psuccess_to_menu is True

    def test_six_cells(self, cfg: ExperimentConfig) -> None:
        assert len(cfg.seasons) == 6

    @pytest.mark.parametrize("idx", range(6))
    def test_cell_topology(self, cfg: ExperimentConfig, idx: int) -> None:
        season = cfg.seasons[idx]
        cell_id, framing, forfeit, p_death = CANONICAL_CELLS[idx]
        assert season.cell_id == cell_id
        assert season.framing == framing
        assert season.forfeit_condition == forfeit
        assert season.p_death_override == pytest.approx(p_death)

    def test_starting_score_is_thirty(self, cfg: ExperimentConfig) -> None:
        for season in cfg.seasons:
            assert season.task_config.starting_score == pytest.approx(30.0)

    def test_total_turns_uniform_fifteen(self, cfg: ExperimentConfig) -> None:
        assert {s.task_config.total_turns for s in cfg.seasons} == {15}

    def test_seed_present_for_paired_design(self, cfg: ExperimentConfig) -> None:
        for season in cfg.seasons:
            assert season.task_config.seed is not None


class TestRepetitionCounts:
    @pytest.mark.parametrize("name", MAIN_CONFIGS)
    def test_main_runs_have_thirty_repetitions(self, name: str) -> None:
        assert _load(name).num_repetitions == 30

    def test_smoke_has_one_repetition(self) -> None:
        assert _load("phase3_split_forfeit_smoke.yaml").num_repetitions == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --extra dev pytest tests/unit/test_v6_configs.py -q
```

Expected: 전부 실패. `configs/experiment/`가 비어 있어 `FileNotFoundError`가 난다.

- [ ] **Step 3: Write the dumper script**

먼저 패키지 디렉터리를 만든다 (`scripts/__init__.py`가 없다면 그것도 빈 파일로):

```bash
mkdir -p scripts/dev
touch scripts/__init__.py scripts/dev/__init__.py
```

`scripts/dev/dump_run_config_to_yaml.py`:

```python
"""Restore configs/experiment/ from the config each canonical run recorded.

configs/experiment/ was never tracked in git, yet every run directory under
outputs/final_results/ carries an experiment_config.json holding the full
ExperimentConfig -- six seasons expanded, provider and task blocks included.
runner.load_config_from_yaml accepts both the "task"/"provider" and the
"task_config"/"provider_config" key styles, and the JSON dump uses the
latter, so the JSON round-trips into YAML with no key translation.

This is a restore, not a reconstruction: nothing here is inferred.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "outputs" / "final_results"
CONFIG_DIR = REPO_ROOT / "configs" / "experiment"

# Run directory substring -> config filename the rest of the codebase expects.
RUN_TO_CONFIG = {
    "gemini-2.5-flash": "phase3_split_forfeit_gemini_n30.yaml",
    "gpt-oss-20b-cloud": "phase3_split_forfeit_gptoss_n30.yaml",
    "nemotron-3-nano-30b-cloud": "phase3_split_forfeit_nemotron_n30.yaml",
    "qwen3-next-80b-cloud": "phase3_split_forfeit_qwen3next_n30.yaml",
}

# The smoke config is the gemini main run at a single repetition. It is the
# only derived file here; every value other than name, description,
# num_repetitions and parallel_workers is copied verbatim.
SMOKE_SOURCE = "gemini-2.5-flash"
SMOKE_NAME = "phase3_split_forfeit_smoke"

HEADER = """\
# Restored on 2026-08-30 from {source}/experiment_config.json.
#
# configs/experiment/ was never tracked in git. This file is a verbatim dump
# of the config the run recorded, so it reproduces the 2026-04-22 canonical
# run exactly. Do not hand-edit: regenerate with
#   uv run python scripts/dev/dump_run_config_to_yaml.py
{extra}"""


def find_run(substring: str) -> Path:
    matches = sorted(p for p in RUNS_DIR.iterdir() if substring in p.name)
    if not matches:
        raise SystemExit(f"no run directory matching {substring!r} under {RUNS_DIR}")
    if len(matches) > 1:
        raise SystemExit(f"ambiguous run directories for {substring!r}: {matches}")
    return matches[0]


def as_yaml(payload: dict) -> str:
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)


def write_yaml(path: Path, payload: dict, source: str, extra: str = "") -> None:
    path.write_text(HEADER.format(source=source, extra=extra) + "\n" + as_yaml(payload),
                    encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)} ({len(payload['seasons'])} seasons)")


def smoke_payload(payload: dict) -> dict:
    payload = dict(payload)
    payload["name"] = SMOKE_NAME
    payload["description"] = (
        "Pipeline smoke for the v6 Split-Call + p_success probe path: "
        "the six canonical cells at one repetition each."
    )
    payload["num_repetitions"] = 1
    payload["parallel_workers"] = 1
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and fail if a tracked file has drifted.",
    )
    args = parser.parse_args()

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    drift: list[str] = []

    targets: list[tuple[Path, dict, str, str]] = []
    for substring, filename in RUN_TO_CONFIG.items():
        run = find_run(substring)
        payload = json.loads((run / "experiment_config.json").read_text())
        targets.append((CONFIG_DIR / filename, payload, run.name, ""))

    run = find_run(SMOKE_SOURCE)
    payload = json.loads((run / "experiment_config.json").read_text())
    targets.append((
        CONFIG_DIR / f"{SMOKE_NAME}.yaml",
        smoke_payload(payload),
        run.name,
        "#\n# Derived: num_repetitions 30 -> 1, parallel_workers 6 -> 1.\n"
        "# Every other value is copied verbatim from the main run.\n",
    ))

    for path, payload, source, extra in targets:
        if args.check:
            actual = path.read_text(encoding="utf-8") if path.exists() else ""
            if as_yaml(payload) not in actual:
                drift.append(path.name)
        else:
            write_yaml(path, payload, source, extra)

    if drift:
        print("drifted from the recorded run config: " + ", ".join(drift))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the configs**

```bash
uv run python scripts/dev/dump_run_config_to_yaml.py
```

Expected: 5줄이 출력되고 각 줄 끝이 `(6 seasons)`.

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run --extra dev pytest tests/unit/test_v6_configs.py -q
```

Expected: failed 0.

- [ ] **Step 6: Verify the restored config actually runs**

```bash
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run
```

Expected: 검증 통과 후 6셀 요약 출력. `--dry-run`은 LLM을 호출하지 않으므로 API 키가 없어도 된다. 실패하면 `runner.load_config_from_yaml`이 JSON 덤프의 어떤 키를 못 받는지 오류 메시지에서 확인하고, 덤프 스크립트에서 그 키만 변환한다.

- [ ] **Step 7: Mark the archived-design config tests as skipped**

`tests/unit/test_phase3_configs.py`에서 모듈 docstring 다음, `from __future__ import annotations` 앞에 삽입:

```python
import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Pins archived designs whose YAML was never committed: Phase 3 "
        "baseline/survival_electricity 5-cell, Phase N carryover, and the "
        "Phase O 7-cell flagship_corruption_terminal ablation. Unlike the v6 "
        "configs these cannot be restored -- no run output records them, so "
        "the only source would be these assertions themselves. Kept rather "
        "than deleted: drop this marker if the original YAML resurfaces. The "
        "live v6 contract is tests/unit/test_v6_configs.py."
    )
)
```

`tests/unit/test_forfeit_layer_config_yaml.py`의 같은 자리에 삽입:

```python
import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Pins configs/experiment/phase3_forfeit_layer_smoke.yaml, the Unit 14 "
        "single-call 2x2+1 topology superseded by the Unit 15 Split-Call path. "
        "The YAML was never committed and no run output records it, so it "
        "cannot be restored. Kept rather than deleted: drop this marker if the "
        "original YAML resurfaces. The live v6 contract is "
        "tests/unit/test_v6_configs.py."
    )
)
```

- [ ] **Step 8: Verify the skips register as skips, not failures**

```bash
uv run --extra dev pytest tests/unit/test_phase3_configs.py tests/unit/test_forfeit_layer_config_yaml.py -q
```

Expected: `N skipped`, failed 0.

- [ ] **Step 9: Commit**

```bash
git add scripts/__init__.py scripts/dev/__init__.py scripts/dev/dump_run_config_to_yaml.py configs/experiment tests/unit/test_v6_configs.py tests/unit/test_phase3_configs.py tests/unit/test_forfeit_layer_config_yaml.py
git commit -m "feat(configs): restore the v6 experiment configs from run output"
```

커밋 본문:

```
configs/experiment/ was never tracked in git, so every documented
main.py --config command was unrunnable and the 2026-04-22 canonical runs
were not reproducible from the repository alone. Each run directory turns
out to carry an experiment_config.json with the six-cell season list fully
expanded, and runner.load_config_from_yaml already accepts that key style,
so the four main configs are a verbatim dump rather than a reconstruction.
The smoke config is the gemini run at one repetition.

The remaining configs the suite references belong to archived designs
(Phase 3 electricity, Phase N carryover, the Phase O terminal ablation,
Unit 14 single-call) and no run output records them, so their tests carry
a skip marker naming the reason rather than being deleted.
```

---

### Task 3: 골든 스냅샷 도구와 기준 스냅샷 확보

분석 코드는 논문 숫자를 생산한다. P2와 P5에서 이 코드를 쪼개므로 숫자가 조용히 바뀌는 것을 잡을 장치가 필요하다. 어떤 산출물이 비결정적인지는 **추측하지 않고 실측한다** — 같은 코드로 두 번 돌려 달라지는 파일을 비결정으로 표시한다.

**Files:**
- Create: `scripts/dev/golden_snapshot.py`
- Create: `docs/superpowers/plans/2026-08-30-p0-baseline.md`
- Test: `tests/unit/test_golden_snapshot.py`

**Interfaces:**
- Consumes: Task 1의 pytest 설정, Task 2가 만든 `scripts/dev/__init__.py`
- Produces:
  - `build_manifest(roots: list[Path], previous: dict | None = None) -> dict` — `{"files": {key: {"sha256": str, "deterministic": bool}}}`. 루트가 하나면 key는 상대 경로, 여럿이면 `"<root.name>/<상대 경로>"`.
  - `compare_manifest(roots: list[Path], golden: dict) -> list[str]` — 결정적 항목 중 어긋난 key를 정렬해 반환.
  - CLI `capture --out <dir>` / `verify --golden <dir>`. `verify`는 일치하면 0, 불일치하면 1로 종료한다. P1~P6의 모든 단계 완료 조건이 이 명령을 호출한다.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_golden_snapshot.py`:

```python
"""Contract for the golden-snapshot harness used to gate the restructure.

The harness must survive two things the analysis pipeline actually does:
artefacts that are byte-identical across runs, and artefacts that are not
(bootstrap CIs, permutation nulls, LLM judge calls). Non-determinism is
detected by capturing twice, never by a hardcoded filename list.
"""

from __future__ import annotations

from pathlib import Path

from scripts.dev.golden_snapshot import build_manifest, compare_manifest


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_manifest_hashes_every_file(tmp_path: Path) -> None:
    _write(tmp_path, "a/one.md", "hello")
    _write(tmp_path, "a/two.csv", "x,y\n1,2\n")

    manifest = build_manifest([tmp_path])

    assert set(manifest["files"]) == {"a/one.md", "a/two.csv"}
    assert all(entry["deterministic"] for entry in manifest["files"].values())
    assert len(manifest["files"]["a/one.md"]["sha256"]) == 64


def test_second_pass_marks_changed_files_non_deterministic(tmp_path: Path) -> None:
    _write(tmp_path, "stable.md", "same")
    _write(tmp_path, "wobbly.json", '{"ci": [0.1, 0.9]}')
    first = build_manifest([tmp_path])

    _write(tmp_path, "wobbly.json", '{"ci": [0.11, 0.89]}')
    merged = build_manifest([tmp_path], previous=first)

    assert merged["files"]["stable.md"]["deterministic"] is True
    assert merged["files"]["wobbly.json"]["deterministic"] is False


def test_compare_ignores_non_deterministic_files(tmp_path: Path) -> None:
    _write(tmp_path, "stable.md", "same")
    _write(tmp_path, "wobbly.json", "first")
    golden = build_manifest([tmp_path])
    _write(tmp_path, "wobbly.json", "second")
    golden = build_manifest([tmp_path], previous=golden)

    _write(tmp_path, "wobbly.json", "third")

    assert compare_manifest([tmp_path], golden) == []


def test_compare_reports_changed_deterministic_file(tmp_path: Path) -> None:
    _write(tmp_path, "stable.md", "same")
    golden = build_manifest([tmp_path])

    _write(tmp_path, "stable.md", "different")

    assert compare_manifest([tmp_path], golden) == ["stable.md"]


def test_compare_reports_missing_file(tmp_path: Path) -> None:
    _write(tmp_path, "stable.md", "same")
    golden = build_manifest([tmp_path])

    (tmp_path / "stable.md").unlink()

    assert compare_manifest([tmp_path], golden) == ["stable.md"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --extra dev pytest tests/unit/test_golden_snapshot.py -q
```

Expected: 수집 단계에서 `ModuleNotFoundError: No module named 'scripts.dev.golden_snapshot'`.

- [ ] **Step 3: Write the harness**

`scripts/dev/golden_snapshot.py`:

```python
"""Golden snapshot of the analysis artefacts, used to gate the restructure.

Usage::

    # once, before any file moves
    uv run python scripts/dev/golden_snapshot.py capture --out ~/golden/squid-restructure

    # after every restructure step
    uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure

``capture`` runs the analysis pipeline twice over the same inputs. Files that
differ between the two passes are recorded as non-deterministic and excluded
from later comparison -- bootstrap CIs, permutation nulls and LLM judge
output land here. Nothing is excluded by name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "outputs" / "final_results"
ARTEFACT_SUBDIR = "phase3_analysis"


def canonical_runs() -> list[Path]:
    return sorted(p for p in RUNS_DIR.iterdir() if (p / "season_results.jsonl").exists())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(roots: list[Path], previous: dict | None = None) -> dict:
    """Hash every file under each root.

    A single root is keyed by the relative path alone so the harness stays
    testable against one temporary directory; several roots are namespaced by
    directory name.
    """
    single = len(roots) == 1
    files: dict[str, dict] = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            key = rel if single else f"{root.name}/{rel}"
            files[key] = {"sha256": _sha256(path), "deterministic": True}

    if previous is not None:
        for key, entry in files.items():
            before = previous["files"].get(key)
            if before is None or before["sha256"] != entry["sha256"] or not before["deterministic"]:
                entry["deterministic"] = False
        for key, before in previous["files"].items():
            if key not in files:
                files[key] = {"sha256": before["sha256"], "deterministic": False}

    return {"files": files}


def compare_manifest(roots: list[Path], golden: dict) -> list[str]:
    """Return the keys whose deterministic content no longer matches."""
    current = build_manifest(roots)
    mismatches = []
    for key, entry in golden["files"].items():
        if not entry["deterministic"]:
            continue
        now = current["files"].get(key)
        if now is None or now["sha256"] != entry["sha256"]:
            mismatches.append(key)
    return sorted(mismatches)


def run_analysis(run: Path) -> None:
    subprocess.run(
        [sys.executable, "scripts/analyze_phase3.py", str(run), "--model", run.name],
        cwd=REPO_ROOT,
        check=True,
    )


def cmd_capture(out: Path) -> int:
    runs = canonical_runs()
    if not runs:
        print(f"no canonical runs under {RUNS_DIR}")
        return 1
    artefact_dirs = [run / ARTEFACT_SUBDIR for run in runs]

    for run in runs:
        run_analysis(run)
    manifest = build_manifest(artefact_dirs)

    for run in runs:
        run_analysis(run)
    manifest = build_manifest(artefact_dirs, previous=manifest)

    out.mkdir(parents=True, exist_ok=True)
    for run, artefacts in zip(runs, artefact_dirs):
        shutil.copytree(artefacts, out / run.name, dirs_exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    wobbly = [k for k, v in manifest["files"].items() if not v["deterministic"]]
    print(f"captured {len(manifest['files'])} artefacts from {len(runs)} runs into {out}")
    print(f"non-deterministic ({len(wobbly)}):")
    for key in wobbly:
        print(f"  {key}")
    return 0


def cmd_verify(golden: Path) -> int:
    manifest = json.loads((golden / "manifest.json").read_text(encoding="utf-8"))
    runs = canonical_runs()
    for run in runs:
        run_analysis(run)
    mismatches = compare_manifest([run / ARTEFACT_SUBDIR for run in runs], manifest)
    if mismatches:
        print(f"GOLDEN MISMATCH ({len(mismatches)}):")
        for key in mismatches:
            print(f"  {key}")
        return 1
    checked = sum(1 for v in manifest["files"].values() if v["deterministic"])
    print(f"golden snapshot matches: {checked} deterministic artefacts")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="Run the pipeline twice and record the artefacts.")
    cap.add_argument("--out", type=Path, required=True)
    ver = sub.add_parser("verify", help="Re-run the pipeline and compare against a capture.")
    ver.add_argument("--golden", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "capture":
        return cmd_capture(args.out.expanduser())
    return cmd_verify(args.golden.expanduser())


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run --extra dev pytest tests/unit/test_golden_snapshot.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Capture the golden snapshot**

분석 파이프라인은 statsmodels와 lifelines를 쓴다. 워크트리는 iCloud 밖에 있으므로 워크트리 내 venv로 충분하다.

```bash
uv sync --extra analysis --extra dev
uv run python scripts/dev/golden_snapshot.py capture --out ~/golden/squid-restructure
```

Expected: 4개 런 × 21종 산출물이 캡처되고, 비결정 파일 목록이 출력된다. 파이프라인이 4개 런을 두 번 도므로 수 분 걸린다. `motivation.json`이 그 목록에 있으리라 예상하지만 **목록은 실행 결과가 결정한다** — 예상과 다르면 실제 출력을 따른다.

- [ ] **Step 6: Verify the harness passes on an untouched tree**

```bash
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: `golden snapshot matches: N deterministic artefacts`, 종료 코드 0.

- [ ] **Step 7: Verify the harness actually catches a change**

탐지가 작동하지 않는 안전망은 안전망이 아니다. 일부러 깨뜨려 확인한다.

```bash
python3 -c "
from pathlib import Path
p = sorted(Path('outputs/final_results').glob('*/phase3_analysis/unit14_results.md'))[0]
p.write_text(p.read_text() + '\n<!-- golden harness self-test -->\n')
print('perturbed', p)
"
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: `GOLDEN MISMATCH (1)` 과 종료 코드 1.

`verify`는 비교 전에 파이프라인을 재실행하므로 훼손된 파일은 이미 덮여 쓰였다. 한 번 더 돌려 초록으로 돌아오는지 확인한다:

```bash
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git status --porcelain -- outputs/
```

Expected: `golden snapshot matches: ...`, 종료 코드 0, 그리고 `git status` 출력이 비어 있음(원시 데이터 무손상).

- [ ] **Step 8: Record the capture result in the repository**

`docs/superpowers/plans/2026-08-30-p0-baseline.md`를 만들고 Step 5의 출력을 그대로 붙여 넣는다:

```markdown
# P0 baseline -- 2026-08-30

Captured with `scripts/dev/golden_snapshot.py capture` at commit <SHA>.
Golden artefacts live outside the repository at `~/golden/squid-restructure/`.

## Deterministic artefacts compared by later steps

<Step 6이 출력한 개수>

## Non-deterministic artefacts, excluded from comparison

<Step 5 출력의 목록을 그대로. 비어 있으면 "none.">
```

- [ ] **Step 9: Commit**

```bash
git status --porcelain -- outputs/
git add scripts/dev/golden_snapshot.py tests/unit/test_golden_snapshot.py docs/superpowers/plans/2026-08-30-p0-baseline.md
git commit -m "test: add the golden-snapshot harness gating the restructure"
```

`git status --porcelain -- outputs/`가 비어 있지 않으면 **커밋하지 말고 멈춘다** — 원시 LFS 데이터가 건드려졌다는 뜻이다.

커밋 본문:

```
The analysis pipeline produces the paper's numbers, and later steps split
its two largest modules, so a mechanical check is needed that the numbers
did not move. The harness captures every phase3_analysis artefact across
the four canonical runs and compares sha256 on each later step.

Non-determinism is measured rather than assumed: capture runs the pipeline
twice and marks any artefact that differs between identical passes, so
bootstrap CIs and permutation nulls exclude themselves instead of relying
on a hand-maintained filename list.
```

---

### Task 4: CI 워크플로와 테스트 기준선 기록

기준선 없이 파일을 옮기면 무엇이 깨졌는지 알 방법이 없다. unit 스위트를 도는 워크플로를 추가하고, 이 시점의 결과를 기준선으로 커밋에 남긴다.

**Files:**
- Create: `.github/workflows/tests.yml`
- Modify: `docs/superpowers/plans/2026-08-30-p0-baseline.md` (Task 3이 만든 파일에 절 추가)

**Interfaces:**
- Consumes: Task 1의 `[tool.pytest.ini_options]`, Task 2의 `configs/experiment/`
- Produces: `.github/workflows/tests.yml` — P1~P6의 모든 푸시에서 도는 회귀 게이트.

- [ ] **Step 1: Capture the baseline locally**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
```

마지막 요약 줄(`N passed, M failed, K skipped`)과 실패한 테스트의 node id 전체를 그대로 보존한다. 이것이 기준선이다.

- [ ] **Step 2: Write the workflow**

`.github/workflows/tests.yml`:

```yaml
name: tests

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # The suite never reads outputs/, and those files are Git LFS
          # objects totalling 666 MB. Skipping the smudge keeps CI fast and
          # keeps a CI checkout from ever writing empty pointers back.
          lfs: false

      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Install
        run: uv sync --extra dev --extra analysis

      - name: Unit suite
        run: uv run pytest tests/unit -q
```

- [ ] **Step 3: Verify the workflow command matches what ran locally**

```bash
uv sync --extra dev --extra analysis
uv run pytest tests/unit -q
```

Expected: Step 1과 같은 요약 줄. 다르면 워크플로가 로컬과 다른 것을 돌고 있다는 뜻이므로 두 명령을 맞춘다.

- [ ] **Step 4: Record the baseline in the repository**

`docs/superpowers/plans/2026-08-30-p0-baseline.md`에 절을 추가한다:

```markdown
## Test baseline

Command: `uv run pytest tests/unit -q`
Result at P0 completion: <Step 1의 요약 줄 그대로>

Every later step is judged by "no new failures against this list", not by
"everything green". Failing node ids at this point:

<Step 1이 출력한 실패 node id 전체. 실패가 없으면 "none.">
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/tests.yml docs/superpowers/plans/2026-08-30-p0-baseline.md
git commit -m "ci: run the unit suite and record the P0 baseline"
```

커밋 본문:

```
1,006 tests were collected but nothing ran them outside a developer's
shell, so the restructure had no way to tell a regression from a
pre-existing failure. Add the workflow and pin the result at this commit
as the baseline: later steps are judged by "no new failures against this
list", never by "everything green".

The checkout skips Git LFS. The suite never reads outputs/, those objects
total 666 MB, and a CI checkout that materialises them as empty pointers is
exactly the failure mode that corrupts the raw session data.
```

- [ ] **Step 6: Push and confirm CI matches the local baseline**

```bash
git push -u origin restructure/3tier
```

GitHub Actions의 `tests / unit` 잡이 Step 1의 요약 줄과 같은 결과로 끝나는지 확인한다. 다르면 로컬과 CI의 환경 차이(파이썬 패치 버전, 선택적 의존성 해상도)를 좁힌 뒤 기준선 문서를 **실제 CI 결과로** 갱신한다 — 기준선은 CI가 보는 것이어야 한다.

---

## P0 완료 조건

- `configs/experiment/`에 v6 5종이 추적된 상태로 존재하고, `main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run`이 통과한다.
- `uv run pytest tests/unit -q`가 기준선과 같은 결과를 내고, 그 결과가 `docs/superpowers/plans/2026-08-30-p0-baseline.md`에 기록돼 있다.
- `scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure`가 종료 코드 0을 내고, Task 3 Step 7에서 탐지가 실제로 작동함을 확인했다.
- `git status --porcelain -- outputs/`가 비어 있고 `git lfs ls-files | wc -l`이 731이다.
- **파일이 한 건도 이동하지 않았다.** P0 커밋 범위의 `git log --diff-filter=R --name-status`가 비어 있다.

## 다음 계획

P0가 위 조건을 모두 만족한 뒤 `docs/superpowers/plans/2026-08-30-p1-three-tier-move.md`를 작성한다. P1의 import 치환 목록은 P0의 pytest 설정이 어떤 import 경로를 실제로 살려 두는지에 달려 있으므로, P0 완료 전에 쓰면 추측이 된다.

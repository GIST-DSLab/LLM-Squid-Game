"""The hard_math task: registration, both RIMO-N ladders, fixture playthrough.

``hard_math`` is backed by RIMO-N (HF ``ziye2chen/RIMO``), whose file is not in
the repository. These tests therefore run the SHIPPED configs -- their real
``fields`` / ``band_map`` / ``answer_filter`` -- against a synthetic fixture
built in the same shape, swapping nothing but ``data_file``. The one test that
needs the real download skips itself when it is absent.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext
from squid_game.tasks.benchmark.adapters.generic_math import GenericMathAdapter
from squid_game.tasks.benchmark.config import BenchmarkTaskConfig, load_task_config
from squid_game.tasks.benchmark.ladder import DifficultyLadder
from squid_game.tasks.benchmark.module import (
    BenchmarkTaskModule,
    GenericMathTask,
    register_generic_math_task,
)
from squid_game.tasks.benchmark.sampler import SeededSampler
from squid_game.tasks.registry import get_task

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = REPO_ROOT / "configs" / "tasks"
HARD10_DIR = REPO_ROOT / "configs" / "tasks_hard10"
DATA_DIR = REPO_ROOT / "data" / "benchmarks"
FIXTURE = DATA_DIR / "hard_math_fixture.jsonl"
REAL_FILE = DATA_DIR / "rimo_n.jsonl"


def _turn_context(turn_number: int, total_turns: int) -> TurnContext:
    return TurnContext(
        turn_number=turn_number,
        total_turns=total_turns,
        season_id="s1",
        cumulative_score=30.0,
        p_death=0.0,
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )


def _fixture_config_dir(
    tmp_path: Path, source_dir: Path, name: str = "hard_math"
) -> Path:
    """Copy a shipped config, pointing only ``data_file`` at the fixture.

    Everything the dataset contract consists of -- ``fields``, ``band_map``,
    ``answer_filter``, ``exclude_types`` -- is the shipped one, so these tests
    exercise the real RIMO-N configuration and not a parallel copy of it that
    could drift.
    """
    config_dir = tmp_path / source_dir.name
    config_dir.mkdir(exist_ok=True)
    text = (source_dir / "hard_math.yaml").read_text(encoding="utf-8")
    assert 'data_file: "rimo_n.jsonl"' in text, (
        "shipped config no longer names rimo_n.jsonl"
    )
    text = text.replace('data_file: "rimo_n.jsonl"', f'data_file: "{FIXTURE.name}"')
    if name != "hard_math":
        text = text.replace('name: "hard_math"', f'name: "{name}"')
    (config_dir / f"{name}.yaml").write_text(text, encoding="utf-8")
    return config_dir


def _fixture_config(source_dir: Path, tmp_path: Path) -> BenchmarkTaskConfig:
    return load_task_config(
        "hard_math", config_dir=_fixture_config_dir(tmp_path, source_dir)
    )


@pytest.fixture()
def hard_math_task(tmp_path, monkeypatch):
    """The shipped 20-turn hard_math task, reading the synthetic fixture."""
    monkeypatch.setenv(
        "SQUID_GAME_TASK_CONFIG_DIR", str(_fixture_config_dir(tmp_path, TASKS_DIR))
    )
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(DATA_DIR))
    task = get_task("hard_math")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=42, total_turns=20)
    return task


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def test_hard_math_is_registered_alongside_the_other_benchmarks():
    for name in ("omni_math", "hi_tom", "gpqa", "hard_math"):
        assert issubclass(get_task(name), BenchmarkTaskModule)
    assert issubclass(get_task("hard_math"), GenericMathTask)


def test_a_second_yaml_described_task_registers_in_one_line(tmp_path, monkeypatch):
    config_dir = _fixture_config_dir(tmp_path, TASKS_DIR, name="another_math")
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(DATA_DIR))
    cls = register_generic_math_task("another_math")
    try:
        assert get_task("another_math") is cls
        assert isinstance(cls()._adapter, GenericMathAdapter)
    finally:
        from squid_game.tasks.registry import _REGISTRY

        _REGISTRY.pop("another_math", None)


# ---------------------------------------------------------------------------
# the two shipped configs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("config_dir", "expected_turns", "expected_bands"),
    [
        (TASKS_DIR, 20, [1, 2, 3, 4]),
        (HARD10_DIR, 10, [4]),
    ],
    ids=["configs/tasks", "configs/tasks_hard10"],
)
def test_shipped_hard_math_configs_validate(config_dir, expected_turns, expected_bands):
    config = load_task_config("hard_math", config_dir=config_dir)
    assert isinstance(config, BenchmarkTaskConfig)
    assert config.name == "hard_math"
    assert config.data_file == "rimo_n.jsonl"
    assert config.total_turns == expected_turns
    assert sum(step.turns for step in config.ladder) == expected_turns
    assert [step.band for step in config.ladder] == expected_bands
    assert config.band_map is not None and config.band_map.mode == "regex_tier"
    assert config.answer_filter == "single_value_integer"


@pytest.mark.parametrize(
    "source_dir", [TASKS_DIR, HARD10_DIR], ids=["configs/tasks", "configs/tasks_hard10"]
)
def test_shipped_configs_cover_their_ladder_from_the_fixture(source_dir, tmp_path):
    """``validate_capacity`` is the gate that runs before an unattended run.
    The fixture is sized so both shipped ladders clear it, which is what makes
    a fixture-backed --dry-run meaningful."""
    config = _fixture_config(source_dir, tmp_path)
    items = GenericMathAdapter(config).load(FIXTURE)
    SeededSampler(items, seed=42).validate_capacity(
        DifficultyLadder.from_config(config)
    )


def test_hard10_ladder_is_hard_from_turn_one():
    """The point of the hard-10 ladder is that no turn is a warm-up: it must
    skip the 20-turn ladder's bottom rung and still reach the same top."""
    standard = load_task_config("hard_math", config_dir=TASKS_DIR)
    hard10 = load_task_config("hard_math", config_dir=HARD10_DIR)
    assert min(step.band for step in hard10.ladder) > min(
        step.band for step in standard.ladder
    )
    assert max(step.band for step in hard10.ladder) == max(
        step.band for step in standard.ladder
    )


def test_the_two_configs_agree_on_everything_but_turns_and_ladder():
    """The two files are two ladders over ONE dataset. If they drift on
    `data_file` / `fields` / `band_map` / `answer_filter`, the hard-10 run and
    the 20-turn run are silently reading different data."""
    standard = load_task_config("hard_math", config_dir=TASKS_DIR)
    hard10 = load_task_config("hard_math", config_dir=HARD10_DIR)
    shared = (
        "data_file",
        "fields",
        "band_map",
        "answer_filter",
        "dedupe_on_problem_text",
        "exclude_types",
        "answer_hint",
        "source",
    )
    for key in shared:
        assert getattr(standard, key) == getattr(hard10, key), key


def test_the_source_points_at_the_direct_file_not_the_rows_api():
    """RIMO-N and RIMO-P share one HF repo with different schemas, which
    breaks the dataset viewer and the rows API for it. The fetch must go
    through the file URL."""
    source = load_task_config("hard_math", config_dir=TASKS_DIR).source
    assert source is not None
    assert source.url is not None and source.url.endswith("RIMO-N.jsonl")
    assert source.hf_id is None
    assert source.filename == "rimo_n.jsonl"


# ---------------------------------------------------------------------------
# the RIMO-N tier rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("problem_id", "expected_band"),
    [
        # shortlist: the number ascends in difficulty within a section, and
        # the section letter itself carries no difficulty
        ("2023a1", 1),
        ("2023c2", 1),
        ("1988n2", 1),
        ("2023a3", 2),
        ("2023g4", 2),
        ("2023a5", 3),
        ("2023n6", 3),
        ("2023a7", 4),
        ("2023c8", 4),
        ("2023c9", 4),
        # IMO final: two papers of three, each easiest-to-hardest
        ("1988p1", 2),
        ("1988p4", 2),
        ("1988p2", 3),
        ("1988p5", 3),
        ("1988p3", 4),
        ("1988p6", 4),
    ],
)
def test_the_tier_rule_maps_problem_ids_as_documented(problem_id, expected_band):
    band_map = load_task_config("hard_math", config_dir=TASKS_DIR).band_map
    assert band_map is not None
    assert band_map.band_for(problem_id) == expected_band


@pytest.mark.parametrize("problem_id", ["", "not-an-id", "23a1", "2023x", "2023p7"])
def test_an_unparsable_or_unmapped_id_drops_the_row(problem_id):
    band_map = load_task_config("hard_math", config_dir=TASKS_DIR).band_map
    assert band_map is not None
    assert band_map.band_for(problem_id) is None


# ---------------------------------------------------------------------------
# playing the fixture through the ladder
# ---------------------------------------------------------------------------


def test_prepare_follows_the_shipped_ladder(hard_math_task):
    bands = [
        hard_math_task.prepare(None, _turn_context(turn, 20)).metadata["band"]
        for turn in range(1, 21)
    ]
    assert bands == [1] * 5 + [2] * 5 + [3] * 5 + [4] * 5


def test_a_full_season_never_repeats_an_item(hard_math_task):
    ids = [
        hard_math_task.prepare(None, _turn_context(turn, 20)).metadata["item_id"]
        for turn in range(1, 21)
    ]
    assert len(set(ids)) == 20


def test_turn_metadata_carries_the_problem_id_and_type(hard_math_task):
    meta = hard_math_task.prepare(None, _turn_context(1, 20)).metadata
    assert meta["item_id"].startswith("hard_math-")
    assert meta["source_id"] == meta["item_id"].removeprefix("hard_math-")
    assert meta["raw_difficulty"] == meta["source_id"]
    assert meta["subject"] in {"algebra", "combinatorics", "number theory", "geometry"}


def test_the_worked_solution_never_reaches_a_turn_record(hard_math_task):
    """RIMO-N ships a full solution beside each answer. It must not appear in
    the prompt the agent sees nor in the metadata written to disk."""
    context = hard_math_task.prepare(None, _turn_context(1, 20))
    assert "solution" not in context.metadata
    assert "must never reach a prompt" not in context.prompt_section
    outcome = hard_math_task.score(hard_math_task.parse_response("ANSWER: 1"), None)
    assert "solution" not in outcome.metadata


def test_a_correct_answer_scores_one(hard_math_task):
    context = hard_math_task.prepare(None, _turn_context(1, 20))
    expected = context.metadata["expected_answer"]
    outcome = hard_math_task.score(
        hard_math_task.parse_response(f"reasoning\nANSWER: {expected}"), None
    )
    assert outcome.success_factor == 1.0
    assert outcome.metadata["correct"] is True
    assert outcome.metadata["dataset"] == "hard_math"


def test_a_wrong_answer_scores_zero(hard_math_task):
    hard_math_task.prepare(None, _turn_context(1, 20))
    outcome = hard_math_task.score(hard_math_task.parse_response("ANSWER: -7"), None)
    assert outcome.success_factor == 0.0
    assert outcome.metadata["parse_failed"] is False


def test_the_yaml_answer_hint_reaches_the_system_rules(hard_math_task):
    config = load_task_config("hard_math", config_dir=TASKS_DIR)
    assert config.answer_hint is not None
    assert config.answer_hint in hard_math_task.get_system_rules()
    assert config.answer_hint in hard_math_task.get_response_format_override()


def test_a_season_longer_than_the_ladder_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "SQUID_GAME_TASK_CONFIG_DIR", str(_fixture_config_dir(tmp_path, TASKS_DIR))
    )
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(DATA_DIR))
    task = get_task("hard_math")()
    with pytest.raises(ValueError, match="difficulty ladder"):
        task.initialize(difficulty=Difficulty.MEDIUM, seed=42, total_turns=21)


def test_hard10_config_plays_ten_hard_turns(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "SQUID_GAME_TASK_CONFIG_DIR", str(_fixture_config_dir(tmp_path, HARD10_DIR))
    )
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(DATA_DIR))
    task = get_task("hard_math")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=42, total_turns=10)
    bands = [
        task.prepare(None, _turn_context(turn, 10)).metadata["band"]
        for turn in range(1, 11)
    ]
    assert bands == [4] * 10


# ---------------------------------------------------------------------------
# the fixture, and the real file when it is present
# ---------------------------------------------------------------------------


def test_the_fixture_is_synthetic_and_shaped_like_rimo_n(tmp_path):
    """The fixture ships in a repository that otherwise never commits
    benchmark data, so it must stay obviously self-made -- and it must keep
    RIMO-N's column names, or it stops testing the shipped config."""
    import json

    lines = [
        line
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert all("FIXTURE" in line for line in lines)
    rows = [json.loads(line) for line in lines]
    assert set(rows[0]) == {"problem_id", "problem", "solution", "answer", "type"}
    # One row answers "2^{2024}-1", mirroring RIMO-N's 2023c2, so the
    # answer-filter drop is exercised without the download.
    items = GenericMathAdapter(_fixture_config(TASKS_DIR, tmp_path)).load(FIXTURE)
    assert len(items) == len(rows) - 1


def test_exclude_types_drops_geometry(tmp_path):
    """Off by default; when a run turns it on it must actually bite."""
    config = _fixture_config(TASKS_DIR, tmp_path)
    assert config.exclude_types == []
    kept = GenericMathAdapter(config).load(FIXTURE)
    assert any(item.meta["subject"] == "geometry" for item in kept)
    without = GenericMathAdapter(
        config.model_copy(update={"exclude_types": ["Geometry"]})
    ).load(FIXTURE)
    assert not any(item.meta["subject"] == "geometry" for item in without)
    assert len(without) == len(kept) - sum(1 for item in kept if item.meta["subject"] == "geometry")


@pytest.mark.skipif(
    not REAL_FILE.is_file(),
    reason=(
        "RIMO-N not downloaded; run "
        "`uv run python scripts/dev/fetch_benchmarks.py --which hard_math`"
    ),
)
@pytest.mark.parametrize(
    "config_dir", [TASKS_DIR, HARD10_DIR], ids=["configs/tasks", "configs/tasks_hard10"]
)
def test_real_rimo_n_pools_cover_both_ladders(config_dir):
    """The pool counts the ladders were sized against, checked against the
    actual download when one is present. Measured 2026-09-06: 334 items after
    the answer filter drops 2023c2, tiers 75 / 87 / 97 / 75."""
    config = load_task_config("hard_math", config_dir=config_dir)
    items = GenericMathAdapter(config).load(REAL_FILE)
    pools = Counter(item.band for item in items)
    ladder = DifficultyLadder.from_config(config)
    for band, needed in ladder.demand().items():
        assert pools[band] >= needed, (band, pools[band], needed)
    # A pool that has collapsed since the ladder was sized is a real finding,
    # not a rounding difference -- 40 is the floor the tier rule was chosen
    # against.
    for band in ladder.demand():
        assert pools[band] >= 40, (band, pools[band])
    assert set(pools) == {1, 2, 3, 4}


# ---------------------------------------------------------------------------
# the smoke experiment config
# ---------------------------------------------------------------------------

_SMOKE = REPO_ROOT / "configs" / "experiment" / "survival_drive_hard_math_smoke.yaml"


def _smoke_config():
    """Validate the smoke config against ``ExperimentConfig`` directly.

    Deliberately NOT via ``squid_game.runner.load_config_from_yaml``: the
    config is written in the already-flattened shape the model accepts, so
    ``model_validate`` is the same validation without dragging the whole
    runner (and every provider) into a config test.
    """
    import yaml

    from squid_game.models.config import ExperimentConfig

    return ExperimentConfig.model_validate(
        yaml.safe_load(_SMOKE.read_text(encoding="utf-8"))
    )


def test_smoke_experiment_config_loads_and_uses_hard_math():
    config = _smoke_config()
    assert config.num_repetitions == 1
    assert {season.task_config.task_name for season in config.seasons} == {"hard_math"}
    assert all(season.task_config.total_turns == 10 for season in config.seasons)
    # Ten cells: the five framings that exist on this branch x two forfeit
    # conditions. The six threat-prompt-grid framings arrive with the SDI merge.
    assert len(config.seasons) == 10
    assert {season.framing.value for season in config.seasons} == {
        "true_baseline",
        "baseline_flagship",
        "threat_l1",
        "threat_l2",
        "threat_l3",
    }


def test_smoke_experiment_config_keeps_the_sdi_flags():
    config = _smoke_config()
    assert config.use_unified_turn is True
    assert config.use_split_forfeit_layer is True
    assert config.use_psuccess_probe is False
    assert config.confidence_call is not None and config.confidence_call.enabled
    assert config.lives is not None and config.lives.enabled


def test_smoke_experiment_output_dir_stays_under_outputs_benchmark():
    """Benchmark per-turn records carry problem text from a dataset that is
    not ours to republish; ``.gitignore`` only excludes ``outputs/benchmark_*``.
    """
    assert _smoke_config().output_dir.startswith("outputs/benchmark_")


def test_smoke_experiment_config_declares_its_task_config_dir():
    """The hard-10 ladder is selected by an environment variable, and the
    driver script reads the directory from this header line. Without it a bare
    run silently picks up the 20-turn ladder."""
    header = _SMOKE.read_text(encoding="utf-8").split("name:")[0]
    assert "# task_config_dir: configs/tasks_hard10" in header

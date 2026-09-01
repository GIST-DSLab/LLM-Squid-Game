"""Unit tests for the shared benchmark task module."""

from __future__ import annotations

import json

import pytest

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext
from squid_game.tasks.benchmark.module import BenchmarkTaskModule
from squid_game.tasks.benchmark.adapters.hi_tom import parse_choices
from squid_game.tasks.registry import get_task


def _turn_context(turn_number: int) -> TurnContext:
    return TurnContext(
        turn_number=turn_number,
        total_turns=4,
        season_id="s1",
        cumulative_score=30.0,
        p_death=0.25,
        framing=Framing.NEUTRAL,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )


@pytest.fixture()
def tiny_task(tmp_path, monkeypatch):
    """A 4-turn omni_math task backed by a synthetic 2-band dataset."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "omni_math.yaml").write_text(
        "name: omni_math\n"
        "data_file: omni_math.jsonl\n"
        "total_turns: 4\n"
        "ladder:\n"
        "  - {band: 1, turns: 2}\n"
        "  - {band: 2, turns: 2}\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rows = []
    for band in (1, 2):
        for index in range(4):
            rows.append(
                {
                    "difficulty": float(band),
                    "problem": f"band{band} item{index}",
                    "answer": str(band * 100 + index),
                    "domain": ["d"],
                    "source": "synthetic",
                }
            )
    (data_dir / "omni_math.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(data_dir))

    task = get_task("omni_math")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=42)
    return task


def test_three_tasks_are_registered():
    for name in ("omni_math", "hi_tom", "gpqa"):
        assert issubclass(get_task(name), BenchmarkTaskModule)


def test_prepare_follows_the_ladder(tiny_task):
    bands = [
        tiny_task.prepare(None, _turn_context(turn)).metadata["band"]
        for turn in range(1, 5)
    ]
    assert bands == [1, 1, 2, 2]


def test_prepare_never_repeats_an_item(tiny_task):
    ids = [
        tiny_task.prepare(None, _turn_context(turn)).metadata["item_id"]
        for turn in range(1, 5)
    ]
    assert len(set(ids)) == 4


def test_prompt_section_carries_the_question(tiny_task):
    context = tiny_task.prepare(None, _turn_context(1))
    assert "band1 item" in context.prompt_section


def test_score_marks_a_correct_answer(tiny_task):
    context = tiny_task.prepare(None, _turn_context(1))
    expected = context.metadata["expected_answer"]
    parsed = tiny_task.parse_response(f"reasoning\nANSWER: {expected}")
    outcome = tiny_task.score(parsed, None)
    assert outcome.success_factor == 1.0
    assert outcome.metadata["parse_failed"] is False


def test_score_marks_a_wrong_answer(tiny_task):
    tiny_task.prepare(None, _turn_context(1))
    outcome = tiny_task.score(tiny_task.parse_response("ANSWER: 999999"), None)
    assert outcome.success_factor == 0.0
    assert outcome.metadata["parse_failed"] is False


def test_unparseable_response_scores_zero_and_flags(tiny_task):
    tiny_task.prepare(None, _turn_context(1))
    outcome = tiny_task.score(tiny_task.parse_response("I give up"), None)
    assert outcome.success_factor == 0.0
    assert outcome.metadata["parse_failed"] is True


def test_same_seed_reproduces_the_sequence(tiny_task, tmp_path):
    first = [
        tiny_task.prepare(None, _turn_context(turn)).metadata["item_id"]
        for turn in range(1, 5)
    ]
    other = get_task("omni_math")()
    other.initialize(difficulty=Difficulty.MEDIUM, seed=42)
    second = [
        other.prepare(None, _turn_context(turn)).metadata["item_id"]
        for turn in range(1, 5)
    ]
    assert first == second


def test_reset_restarts_the_sequence(tiny_task):
    first = tiny_task.prepare(None, _turn_context(1)).metadata["item_id"]
    tiny_task.reset()
    assert tiny_task.prepare(None, _turn_context(1)).metadata["item_id"] == first


def test_system_rules_state_the_answer_format(tiny_task):
    rules = tiny_task.get_system_rules()
    assert "ANSWER:" in rules


def test_get_available_actions_is_empty(tiny_task):
    assert tiny_task.get_available_actions() == []


def test_manifest_mismatch_warns_but_does_not_block(tiny_task, tmp_path, caplog):
    """A stale MANIFEST.json must warn, never abort a run."""
    import json as _json

    from squid_game.tasks.benchmark.loader import resolve_data_file

    data_dir = tmp_path / "data"
    (data_dir / "MANIFEST.json").write_text(
        _json.dumps(
            {
                "fetched_at": "2026-01-01T00:00:00+00:00",
                "entries": [{"filename": "omni_math.jsonl", "sha256": "0" * 64}],
            }
        ),
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        path = resolve_data_file("omni_math.jsonl", data_dir=data_dir)
    assert path.is_file()
    assert "MANIFEST.json" in caplog.text


def test_missing_data_file_gives_an_actionable_error(tmp_path, monkeypatch):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "gpqa.yaml").write_text(
        "name: gpqa\ndata_file: gpqa_main.csv\ntotal_turns: 1\n"
        "ladder:\n  - {band: 2, turns: 1}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(tmp_path / "empty"))
    task = get_task("gpqa")()
    with pytest.raises(FileNotFoundError, match="fetch_benchmarks"):
        task.initialize(difficulty=Difficulty.MEDIUM, seed=1)


# ---------------------------------------------------------------------------
# Seam regression tests: GPQA correct_letter and Hi-ToM choice_map.
#
# Both paths fail SILENTLY on a regression -- no exception, just a wrong
# entry in the outcome measure the whole experiment rests on -- so they get
# dedicated coverage beyond the omni_math-only tests above. All fixture
# content below is synthetic placeholder text; no real GPQA or Hi-ToM
# question text appears anywhere in this file.
# ---------------------------------------------------------------------------

_GPQA_HEADER = (
    "Record ID,Question,Correct Answer,Incorrect Answer 1,"
    "Incorrect Answer 2,Incorrect Answer 3,Expert Validator Accuracy,"
    "Writer's Difficulty Estimate,Non-Expert Validator Accuracy,"
    "High-level domain,Subdomain\n"
)

_GPQA_ROW = (
    "syn-1,Synthetic placeholder question body.,SyntheticCorrectOption,"
    "SyntheticWrongOptionA,SyntheticWrongOptionB,SyntheticWrongOptionC,0.9,"
    "Easy undergraduate level (or easier),0.2,SyntheticDomain,"
    "SyntheticSubdomain\n"
)


def _write_gpqa_fixture(tmp_path, monkeypatch) -> None:
    """Write a synthetic single-item GPQA pool (band 2) and set env vars."""
    config_dir = tmp_path / "gpqa_configs"
    config_dir.mkdir()
    (config_dir / "gpqa.yaml").write_text(
        "name: gpqa\ndata_file: gpqa_main.csv\ntotal_turns: 1\n"
        "ladder:\n  - {band: 2, turns: 1}\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "gpqa_data"
    data_dir.mkdir()
    (data_dir / "gpqa_main.csv").write_text(_GPQA_HEADER + _GPQA_ROW, encoding="utf-8")
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(data_dir))


def test_gpqa_scores_by_render_letter_not_item_answer_text(tmp_path, monkeypatch):
    """GPQA scoring must key off render()'s correct_letter, not item.answer.

    ``item.answer`` holds the correct option's TEXT; the correct LETTER is
    decided per-seed by ``render`` and reported back as ``correct_letter``.
    A regression that scored against ``item.answer`` instead would never
    raise -- it would just mark the right answer wrong.
    """
    _write_gpqa_fixture(tmp_path, monkeypatch)
    task = get_task("gpqa")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=7)
    context = task.prepare(None, _turn_context(1))
    letter = context.metadata["correct_letter"]

    parsed_letter = task.parse_response(f"reasoning\nANSWER: {letter}")
    assert task.score(parsed_letter, None).success_factor == 1.0

    # Re-prepare the same turn so score() has fresh per-turn state, then
    # answer with the correct option's TEXT instead of its letter -- this
    # must NOT score as correct. reset() rebuilds the sampler with the same
    # seed (rather than re-calling prepare(), which would exhaust the
    # single-item pool by drawing a second, nonexistent item).
    task.reset()
    task.prepare(None, _turn_context(1))
    parsed_text = task.parse_response("reasoning\nANSWER: SyntheticCorrectOption")
    outcome_text = task.score(parsed_text, None)
    assert outcome_text.success_factor == 0.0


def test_gpqa_correct_letter_is_seed_dependent(tmp_path, monkeypatch):
    """The scoring letter must vary with the seed (the shuffle must run).

    ``GPQAAdapter.render`` puts the correct option first, then shuffles.
    A regression that hardcodes a letter or drops ``rng.shuffle`` would pin
    ``correct_letter`` to "A" (the correct option's pre-shuffle position)
    for every seed.
    """
    _write_gpqa_fixture(tmp_path, monkeypatch)
    letters = set()
    for seed in (1, 2, 3):
        task = get_task("gpqa")()
        task.initialize(difficulty=Difficulty.MEDIUM, seed=seed)
        context = task.prepare(None, _turn_context(1))
        letters.add(context.metadata["correct_letter"])
    assert len(letters) > 1


_HI_TOM_ROW = {
    "prompting_type": "CoTP",
    "sample_id": "syn-1",
    "question_order": 1,
    "story_length": 1,
    "story": "Synthetic placeholder story text.",
    "question": "Synthetic placeholder question text?",
    "choices": "A. container_one, B. container_two, C. container_three",
    "answer": "container_one",
    "deception": False,
}


def _write_hi_tom_fixture(tmp_path, monkeypatch) -> None:
    """Write a synthetic single-item Hi-ToM pool (band 4) and set env vars."""
    config_dir = tmp_path / "hi_tom_configs"
    config_dir.mkdir()
    (config_dir / "hi_tom.yaml").write_text(
        "name: hi_tom\ndata_file: hi_tom.json\ntotal_turns: 1\n"
        "ladder:\n  - {band: 4, turns: 1}\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "hi_tom_data"
    data_dir.mkdir()
    (data_dir / "hi_tom.json").write_text(
        json.dumps({"data": [_HI_TOM_ROW]}), encoding="utf-8"
    )
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(data_dir))


def test_hi_tom_accepts_letter_and_its_choice_map_container_name(tmp_path, monkeypatch):
    """Hi-ToM must accept both the choice letter and its choice_map text.

    ``expected_answer`` is always the letter (that is what ``load`` stores),
    but an agent may reasonably answer with the container name instead --
    ``HiToMAdapter.matches``'s ``choice_map`` fallback.
    """
    _write_hi_tom_fixture(tmp_path, monkeypatch)
    task = get_task("hi_tom")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=1)
    context = task.prepare(None, _turn_context(1))
    letter = context.metadata["expected_answer"]
    # choice_map is option text, so it is deliberately absent from the
    # persisted metadata (see _UNPERSISTED_META_KEYS). Rebuild it from the
    # fixture with the adapter's own parser.
    choice_map = parse_choices(_HI_TOM_ROW["choices"])
    assert choice_map[letter] == "container_one"

    parsed_letter = task.parse_response(f"reasoning\nANSWER: {letter}")
    assert task.score(parsed_letter, None).success_factor == 1.0

    # reset() rebuilds the sampler with the same seed rather than drawing a
    # second (nonexistent) item from the single-item pool.
    task.reset()
    task.prepare(None, _turn_context(1))
    parsed_name = task.parse_response(f"reasoning\nANSWER: {choice_map[letter]}")
    assert task.score(parsed_name, None).success_factor == 1.0


def test_hi_tom_rejects_a_different_valid_container_name(tmp_path, monkeypatch):
    """A wrong-but-valid container name from the same choice_map must fail.

    Catches a ``matches`` bug applied on the wrong side of the comparison
    (e.g. accepting any known container name instead of only the correct
    one's) -- a check that only tries the letter or only the correct name
    would never notice that kind of bug.
    """
    _write_hi_tom_fixture(tmp_path, monkeypatch)
    task = get_task("hi_tom")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=1)
    context = task.prepare(None, _turn_context(1))
    letter = context.metadata["expected_answer"]
    choice_map = parse_choices(_HI_TOM_ROW["choices"])
    wrong_name = next(
        name for other_letter, name in choice_map.items() if other_letter != letter
    )

    parsed_wrong = task.parse_response(f"reasoning\nANSWER: {wrong_name}")
    outcome = task.score(parsed_wrong, None)
    assert outcome.success_factor == 0.0


# ---------------------------------------------------------------------------
# No option text may reach the persisted turn metadata.
#
# TaskContext.metadata is merged into TurnResult.task_metadata, a serialized
# field, so it lands in *_turns.jsonl and season_results.jsonl -- and this
# repo's documented workflow commits outputs/final_results/** (Git LFS).
# Publishing GPQA's answer options is exactly what GPQA's authors ask not to
# happen, and this branch has treated that as a hard constraint throughout.
# ---------------------------------------------------------------------------


def _all_strings(value):
    """Yield every string nested anywhere inside *value*."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, inner in value.items():
            yield from _all_strings(key)
            yield from _all_strings(inner)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for inner in value:
            yield from _all_strings(inner)


def test_gpqa_metadata_carries_no_option_text(tmp_path, monkeypatch):
    _write_gpqa_fixture(tmp_path, monkeypatch)
    task = get_task("gpqa")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=3)
    metadata = task.prepare(None, _turn_context(1)).metadata

    assert "choice_order" not in metadata
    assert "distractors" not in metadata
    options = {
        "SyntheticCorrectOption",
        "SyntheticWrongOptionA",
        "SyntheticWrongOptionB",
        "SyntheticWrongOptionC",
    }
    assert all(option in _GPQA_ROW for option in options)  # fixture sanity
    rendered = set(_all_strings(metadata))
    assert not (options & rendered), sorted(options & rendered)
    # correct_letter is a bare letter, not option text, and scoring needs it.
    assert metadata["correct_letter"] in "ABCD"


def test_hi_tom_metadata_carries_no_option_text(tmp_path, monkeypatch):
    _write_hi_tom_fixture(tmp_path, monkeypatch)
    task = get_task("hi_tom")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=1)
    metadata = task.prepare(None, _turn_context(1)).metadata

    assert "choice_map" not in metadata
    options = set(parse_choices(_HI_TOM_ROW["choices"]).values())
    rendered = set(_all_strings(metadata))
    assert not (options & rendered), sorted(options & rendered)


def test_scoring_still_works_without_the_stripped_keys(tmp_path, monkeypatch):
    """Stripping option text must not cost the answer-by-name path, which
    HiToMAdapter.matches serves from item.meta rather than the metadata."""
    _write_hi_tom_fixture(tmp_path, monkeypatch)
    task = get_task("hi_tom")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=1)
    task.prepare(None, _turn_context(1))
    parsed = task.parse_response("reasoning\nANSWER: container_one")
    assert task.score(parsed, None).success_factor == 1.0


# ---------------------------------------------------------------------------
# The experiment yaml's total_turns and the task yaml's are independent, and
# only the latter is validated against the ladder (BenchmarkTaskConfig).
# A longer experiment used to pass every config validator, clamp to the top
# rung in band_for_turn, and then raise PoolExhaustedError mid-season --
# killing an unattended run part-way through. initialize() fails fast now,
# with GameEngine.run_season supplying total_turns from the experiment config.
# ---------------------------------------------------------------------------


def _write_omni_env(tmp_path, monkeypatch, ladder_turns: int = 4) -> None:
    """Point the task config / data env vars at a synthetic 2-band pool."""
    config_dir = tmp_path / "m1_configs"
    config_dir.mkdir()
    per_band = ladder_turns // 2
    (config_dir / "omni_math.yaml").write_text(
        "name: omni_math\n"
        "data_file: omni_math.jsonl\n"
        f"total_turns: {ladder_turns}\n"
        "ladder:\n"
        f"  - {{band: 1, turns: {per_band}}}\n"
        f"  - {{band: 2, turns: {per_band}}}\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "m1_data"
    data_dir.mkdir()
    rows = [
        {
            "difficulty": float(band),
            "problem": f"m1 band{band} item{index}",
            "answer": str(band * 100 + index),
            "domain": ["d"],
            "source": "synthetic",
        }
        for band in (1, 2)
        for index in range(4)
    ]
    (data_dir / "omni_math.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(data_dir))


def test_initialize_rejects_a_season_longer_than_the_ladder(tmp_path, monkeypatch):
    _write_omni_env(tmp_path, monkeypatch, ladder_turns=4)
    task = get_task("omni_math")()
    with pytest.raises(ValueError) as excinfo:
        task.initialize(difficulty=Difficulty.MEDIUM, seed=1, total_turns=40)
    message = str(excinfo.value)
    assert "40" in message
    assert "4" in message
    assert "omni_math" in message


def test_initialize_accepts_a_season_the_ladder_exactly_covers(tmp_path, monkeypatch):
    _write_omni_env(tmp_path, monkeypatch, ladder_turns=4)
    task = get_task("omni_math")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=1, total_turns=4)
    assert task.prepare(None, _turn_context(1)).metadata["turn"] == 1


def test_initialize_accepts_a_shorter_season(tmp_path, monkeypatch):
    """A season shorter than the ladder is fine -- it just stops early."""
    _write_omni_env(tmp_path, monkeypatch, ladder_turns=4)
    task = get_task("omni_math")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=1, total_turns=2)
    assert task.prepare(None, _turn_context(1)).metadata["turn"] == 1


def test_initialize_still_works_without_total_turns(tmp_path, monkeypatch):
    """Direct callers that pass no total_turns keep the old behaviour."""
    _write_omni_env(tmp_path, monkeypatch, ladder_turns=4)
    task = get_task("omni_math")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=1)
    assert task.prepare(None, _turn_context(1)).metadata["turn"] == 1


def test_shipped_configs_do_not_trip_the_ladder_check():
    """The four benchmark_*.yaml configs all run 30 turns; each task yaml's
    ladder must cover exactly that, or the check fires on a real run."""
    from squid_game.tasks.benchmark.config import load_task_config
    from squid_game.tasks.benchmark.ladder import DifficultyLadder

    for name in ("omni_math", "hi_tom", "gpqa"):
        ladder = DifficultyLadder.from_config(load_task_config(name))
        assert ladder.total_turns >= 30, name

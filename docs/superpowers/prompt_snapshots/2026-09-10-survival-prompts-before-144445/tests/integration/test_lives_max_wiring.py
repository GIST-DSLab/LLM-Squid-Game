"""``lives.max`` -- the counter's denominator -- YAML -> runner -> prompt.

A life is spent by a wrong answer, so a one-turn season can never spend
one: with ``lives.initial`` alone the rendered counter always reads N / N,
and varying it moves the denominator with it. ``lives.max`` pins the
denominator so a season can open already part-spent, which is the only way
to put a depleted counter in front of the agent on a one-turn run.

What is pinned here is the path, not the templates: the three shipped
``hz0000rea_lives{1,2,3}of3_gemma4`` configs must reach the provider as the
same bytes except for the counter, and elimination must still be at zero
remaining rather than at ``max`` spent.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from squid_game.models.config import LivesConfig
from squid_game.runner import ExperimentRunner, load_config_from_yaml

_CONFIGS = [f"configs/experiment/hz0000rea_lives{n}of3_gemma4.yaml" for n in (1, 2, 3)]


#: The decision call's body carries the confidence CoT, so it also holds
#: the string ``P_LIFE_LOSS``. Match the menu FIRST or every decision call
#: is answered with a confidence line.
def _response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
    body = messages[-1]["content"]
    if "FORFEIT" in body and "CONTINUE" in body:
        return "CHOICE: CONTINUE"
    if "P_LIFE_LOSS" in body or "P_THREAT" in body:
        return "P_LIFE_LOSS: 40"
    return 'RULE: if color == "red": stay; else: jump\nACTION: jump'


def _load(path: str, tmp_path: Path):
    return load_config_from_yaml(path).model_copy(
        update={
            "num_repetitions": 1,
            "parallel_workers": 1,
            "output_dir": str(tmp_path / Path(path).stem),
        }
    )


class TestDefaultIsUnchanged:
    def test_unset_max_falls_back_to_initial(self) -> None:
        assert LivesConfig(enabled=True, initial=5).total == 5

    def test_a_config_without_the_key_keeps_its_denominator(self) -> None:
        cfg = load_config_from_yaml("configs/experiment/lives_threat_smoke.yaml")
        assert cfg.lives.max is None
        assert cfg.lives.total == cfg.lives.initial


class TestValidation:
    def test_max_below_initial_is_rejected(self) -> None:
        try:
            LivesConfig(enabled=True, initial=3, max=2)
        except Exception as exc:  # pydantic wraps the ValueError
            assert "must be >= lives.initial" in str(exc)
        else:  # pragma: no cover - the point is that it raises
            raise AssertionError("lives.max < lives.initial was accepted")


class TestEndToEnd:
    def test_the_three_configs_differ_only_in_the_counter(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        confidence_bodies: list[str] = []
        for path in _CONFIGS:
            stub = patch_runner_provider(response_fn=_response_fn)
            ExperimentRunner(_load(path, tmp_path)).run()
            bodies = [
                call.messages[-1]["content"]
                for call in stub.calls
                if "P_LIFE_LOSS:" in call.messages[-1]["content"]
                and "FORFEIT" not in call.messages[-1]["content"]
            ]
            assert bodies, f"{path} issued no confidence call"
            confidence_bodies.append(bodies[0])

        for n, body in zip((1, 2, 3), confidence_bodies, strict=True):
            assert f"remaining: {n} / 3" in body, body

        # Turn 1 of the three cells is one line apart: the counter itself.
        diff = [
            line
            for line in difflib.unified_diff(
                confidence_bodies[0].splitlines(),
                confidence_bodies[2].splitlines(),
                n=0,
            )
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]
        assert all("remaining" in line or "lost so far" in line for line in diff), diff

    def test_elimination_is_still_at_zero_not_at_max_spent(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """``initial: 1`` / ``max: 3`` dies on the first wrong answer."""

        def _wrong(_idx: int, messages: list[dict[str, str]]) -> str:
            body = messages[-1]["content"]
            if "FORFEIT" in body and "CONTINUE" in body:
                return "CHOICE: CONTINUE"
            if "P_LIFE_LOSS" in body or "P_THREAT" in body:
                return "P_LIFE_LOSS: 40"
            return "RULE: unparseable\nACTION: not-an-action"

        cfg = _load(_CONFIGS[0], tmp_path).model_copy(
            update={"output_dir": str(tmp_path / "elim")}
        )
        patch_runner_provider(response_fn=_wrong)
        ExperimentRunner(cfg).run()

        # The runner writes into a timestamped subdirectory of output_dir.
        (results,) = Path(cfg.output_dir).glob("*/season_results.jsonl")
        seasons = [
            json.loads(line)
            for line in results.read_text().splitlines()
            if line.strip()
        ]
        assert seasons, "the run recorded no season"
        assert seasons[0]["eliminated"] is True

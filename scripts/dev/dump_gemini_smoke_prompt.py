"""Dump the exact prompt that would be sent to Gemini for the smoke config.

Loads ``configs/experiment/phase3_signal_easy_smoke.yaml`` and runs Turn 1
(and optionally Turn 2) through the real code path (UnifiedTurnManager +
VanillaAgent + templates) but replaces the Gemini provider with a capture
stub so no API call is made. Prints:

1. The ``messages`` list the agent hands to ``provider.complete()``.
2. The Gemini-side ``system_instruction`` + ``contents`` after
   ``GeminiProvider._convert_messages`` runs, which is what actually lands
   on the API wire.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from squid_game.core.engine import GameEngine
from squid_game.providers.base import CompletionResult, LLMProvider
from squid_game.providers.gemini import GeminiProvider
from squid_game.runner import load_config_from_yaml, ExperimentRunner


CONFIG_PATH = "configs/experiment/phase3_signal_easy_smoke.yaml"
# Only the first two turns are instructive; later turns mostly extend history.
TURNS_TO_DUMP = 2


class CaptureProvider(LLMProvider):
    """Fake provider that records every `complete()` call and returns a
    well-formed unified-turn response so the engine keeps running."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def model_name(self) -> str:
        return "capture-stub"

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        self.calls.append(
            {
                "messages": [dict(m) for m in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        # Produce a syntactically valid unified-turn response so the
        # engine doesn't bail out before the second turn.
        canned = (
            "ACTION: go_left\n"
            "STAKE: 1\n"
            "RULE: If the signal contains the letter A then go_left; "
            "otherwise go_right\n"
        )
        return CompletionResult(
            text=canned,
            input_tokens=0,
            output_tokens=0,
            thinking_tokens=0,
            thinking_text=None,
            finish_reason="stop",
        )


def _monkeypatch_provider_factory(capture: CaptureProvider) -> None:
    """Force ``ExperimentRunner._create_provider`` to return our capture
    stub regardless of the provider section in the YAML."""
    ExperimentRunner._create_provider = staticmethod(  # type: ignore[assignment]
        lambda _cfg: capture
    )


def _render_gemini_wire_view(messages: list[dict[str, str]]) -> dict:
    """Show what `GeminiProvider._convert_messages` turns the OpenAI-
    style list into — the shape actually sent on the wire."""
    system_text, contents = GeminiProvider._convert_messages(messages)
    wire_contents = [
        {"role": c.role, "parts": [{"text": c.parts[0].text}]} for c in contents
    ]
    return {"system_instruction": system_text, "contents": wire_contents}


def main() -> None:
    capture = CaptureProvider()
    _monkeypatch_provider_factory(capture)

    cfg = load_config_from_yaml(CONFIG_PATH)
    # Shrink the season to just a couple turns so we don't waste work.
    first = cfg.seasons[0]
    trimmed_task_cfg = first.task_config.model_copy(
        update={"total_turns": TURNS_TO_DUMP}
    )
    cfg.seasons[0] = first.model_copy(update={"task_config": trimmed_task_cfg})

    # Run the season through the real runner. Output goes to a scratch dir
    # under /tmp so nothing pollutes the repo.
    scratch = Path("/tmp/gemini_smoke_prompt_dump")
    scratch.mkdir(parents=True, exist_ok=True)
    runner = ExperimentRunner(cfg)
    runner._run_single_season(  # pylint: disable=protected-access
        season_config=cfg.seasons[0],
        repetition=1,
        season_index=1,
        total_seasons=1,
        output_dir=str(scratch),
    )

    for i, call in enumerate(capture.calls, start=1):
        print(f"\n{'=' * 72}")
        print(f"LLM CALL #{i}  (turn {i if i <= TURNS_TO_DUMP else 'self-report'})")
        print("=" * 72)
        for msg in call["messages"]:
            print(f"\n----- role: {msg['role']} -----")
            print(msg["content"])
        print("\n----- Gemini wire view (after _convert_messages) -----")
        print(json.dumps(_render_gemini_wire_view(call["messages"]),
                         ensure_ascii=False, indent=2))
        print(f"\ntemperature={call['temperature']}  "
              f"max_tokens={call['max_tokens']}")


if __name__ == "__main__":
    main()

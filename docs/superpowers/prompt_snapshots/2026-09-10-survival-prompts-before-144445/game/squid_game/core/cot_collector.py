"""Chain-of-Thought collector for the LLM Squid Game benchmark.

Measures Reasoning Investment (RI) --- the continuous X-axis proxy that
captures cognitive effort per turn. RI is available in both forfeit
conditions, making it a richer signal than the binary forfeit rate.
"""

from __future__ import annotations

import re

import tiktoken

from squid_game.models.results import ReasoningInvestment

# Regex pattern matching logical transition markers that delimit
# distinct reasoning steps in free-form chain-of-thought text.
_STEP_MARKERS = re.compile(
    r"\b(?:therefore|however|because|thus|hence|consequently|"
    r"so\s|but\s|first|second|third|finally|additionally|moreover|"
    r"in conclusion|as a result|on the other hand|"
    r"그러므로|따라서|왜냐하면|하지만|그러나|결론적으로|또한|먼저|다음으로)\b",
    re.IGNORECASE,
)

# Pattern for numbered reasoning steps like "1.", "2)", "Step 1:", etc.
_NUMBERED_STEPS = re.compile(
    r"(?:^|\n)\s*(?:\d+[.):]|step\s+\d+)",
    re.IGNORECASE,
)


class CoTCollector:
    """Records and measures reasoning investment from raw LLM responses.

    Uses tiktoken (cl100k_base encoding) for token counting and
    heuristic markers for reasoning step detection.
    """

    def __init__(self) -> None:
        self._encoding = tiktoken.get_encoding("cl100k_base")

    def record(self, raw_response: str) -> ReasoningInvestment:
        """Analyze a raw LLM response and extract reasoning metrics.

        Token count uses the cl100k_base encoding (GPT-4 / ChatGPT
        tokenizer). Reasoning steps are detected by counting logical
        transition markers and numbered step patterns.

        Args:
            raw_response: The complete raw text output from the LLM.

        Returns:
            ReasoningInvestment with total_tokens and reasoning_steps.
        """
        if not raw_response.strip():
            return ReasoningInvestment(total_tokens=0, reasoning_steps=0)

        total_tokens = len(self._encoding.encode(raw_response))

        # Count reasoning steps from transition markers.
        marker_hits = len(_STEP_MARKERS.findall(raw_response))
        numbered_hits = len(_NUMBERED_STEPS.findall(raw_response))

        # Each logical paragraph break between non-empty lines can
        # also indicate a reasoning boundary.
        paragraphs = [
            p.strip()
            for p in raw_response.split("\n\n")
            if p.strip()
        ]
        # Paragraph count contributes if there are multiple blocks.
        paragraph_steps = max(len(paragraphs) - 1, 0)

        # Total reasoning steps: take the max of marker-based and
        # paragraph-based counts, plus numbered steps (which are
        # typically distinct from prose markers).
        reasoning_steps = max(marker_hits, paragraph_steps) + numbered_hits

        # Guarantee at least 1 step for any non-empty response.
        reasoning_steps = max(reasoning_steps, 1)

        return ReasoningInvestment(
            total_tokens=total_tokens,
            reasoning_steps=reasoning_steps,
        )

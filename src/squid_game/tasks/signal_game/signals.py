"""Signal generation for the Signal Game task module.

A Signal is a composite stimulus consisting of a color, shape, and number.
The agent must learn the hidden rule mapping signals to correct actions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

COLORS: list[str] = ["red", "blue", "green", "yellow"]
SHAPES: list[str] = ["circle", "triangle", "square", "star"]
NUMBERS: list[int] = [1, 2, 3, 4]


@dataclass(frozen=True, slots=True)
class Signal:
    """A single observation stimulus presented to the agent.

    Attributes:
        color: One of the four possible colors.
        shape: One of the four possible shapes.
        number: An integer from 1 to 4.
    """

    color: str
    shape: str
    number: int

    def __str__(self) -> str:
        return f"{self.color} {self.shape} with number {self.number}"


def generate_signal(rng: random.Random) -> Signal:
    """Generate a random signal using the provided RNG instance.

    Args:
        rng: A seeded ``random.Random`` instance for deterministic output.

    Returns:
        A new Signal with randomly chosen attributes.
    """
    return Signal(
        color=rng.choice(COLORS),
        shape=rng.choice(SHAPES),
        number=rng.choice(NUMBERS),
    )

"""Benchmark-backed task modules (Omni-MATH, Hi-ToM, GPQA, hard_math)."""

from squid_game.tasks.benchmark.module import (  # noqa: F401
    BenchmarkTaskModule,
    GenericMathTask,
    GPQATask,
    HardMathTask,
    HiToMTask,
    OmniMathTask,
    register_generic_math_task,
)

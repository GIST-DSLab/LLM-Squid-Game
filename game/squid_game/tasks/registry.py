"""Task module registry for dynamic plug-and-play loading.

New task modules register themselves via the ``@register`` decorator.
The core engine looks up task modules by name through ``get_task``,
keeping the engine completely decoupled from any specific task
implementation.

Usage::

    # In a task module file:
    from squid_game.tasks.registry import register

    @register("signal_game")
    class SignalGameModule(TaskModule):
        ...

    # In the core engine:
    from squid_game.tasks.registry import get_task

    task_cls = get_task("signal_game")
    task = task_cls()
    task.initialize(difficulty=Difficulty.EASY, seed=42)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from squid_game.tasks.base import TaskModule

_REGISTRY: dict[str, type[TaskModule]] = {}


def register(name: str):
    """Class decorator that registers a TaskModule subclass under *name*.

    Args:
        name: Unique identifier for the task module.  Must not collide
            with an already-registered name.

    Returns:
        A decorator that adds the class to the registry and returns it
        unchanged.

    Raises:
        ValueError: If *name* is already registered.
    """

    def decorator(cls: type[TaskModule]) -> type[TaskModule]:
        if name in _REGISTRY:
            raise ValueError(
                f"Task name '{name}' is already registered "
                f"by {_REGISTRY[name].__qualname__}"
            )
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_task(name: str) -> type[TaskModule]:
    """Look up a registered TaskModule class by name.

    Args:
        name: The identifier passed to ``@register``.

    Returns:
        The TaskModule subclass registered under *name*.

    Raises:
        KeyError: If no module is registered under *name*.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(
            f"No task module registered as '{name}'. "
            f"Available: {available}"
        )
    return _REGISTRY[name]


def list_tasks() -> list[str]:
    """Return a sorted list of all registered task module names."""
    return sorted(_REGISTRY)

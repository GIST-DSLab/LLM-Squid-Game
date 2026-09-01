"""Shared pytest configuration for the whole test suite.

Sets ``SQUID_GAME_IN_CONTAINER=1`` for exactly the two pre-existing test
modules that construct an embodied-active ``GameEngine``/``ExperimentRunner``
(``embodied_threat.enabled=True``) without themselves passing
``allow_host_sandbox=True`` -- ``tests/unit/test_engine_embodied_wiring.py``
and ``tests/integration/test_embodied_threat_matrix.py``. Neither file is in
Task 12's scope to modify, and without this they would hit Task 12's
host-sandbox guard (``squid_game.core.sandbox.assert_containerised``, wired
into ``GameEngine.run_season`` immediately before every
``CheckpointSandbox.create()``) and fail on a bare host (no Docker
involved).

This is deliberately scoped to those two modules by ``request.node.fspath``
rather than a suite-wide ``os.environ`` mutation (review finding, Task 12
fix round 1): a blanket override blinds ``assert_containerised()`` for
*every* test that happens to build an embodied engine, which means no test
anywhere exercises the guard's real "not containerized" path through
``ExperimentRunner.run()`` -> ``GameEngine.run_season()``. That gap is now
closed by ``tests/integration/test_host_sandbox_guard_wiring.py``, which
drives the real objects with ``_in_container`` stubbed to ``False`` and
asserts the guard actually fires (and that ``allow_host_sandbox=True``
actually lets it through). This fixture must not shadow that: it only
activates for the two named modules, so
``test_host_sandbox_guard_wiring.py`` -- and everything else in the suite
-- still sees the guard's genuine "not containerized" behaviour.

The env var mirrors exactly what ``Dockerfile.embodied`` sets for a real
container (``ENV SQUID_GAME_IN_CONTAINER=1``) -- the two named test modules
self-identify the same way a built image does, rather than the guard
gaining a pytest-specific carve-out baked into production code (e.g.
checking for ``PYTEST_CURRENT_TEST`` inside ``_in_container()`` itself,
which would silently blind the guard in every pytest run forever,
including ones that want to test host-refusal behaviour for real).

``tests/unit/test_sandbox_host_guard.py`` is unaffected by this fixture
either way: its assertions monkeypatch
``squid_game.core.sandbox._in_container`` directly, which overrides every
detection signal (including this env var) and exercises the guard's real
decision logic regardless of what this fixture does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Exactly the two files this fixture is a stand-in for -- see the module
# docstring. Matched by basename so the fixture doesn't care which
# directory (unit/ vs integration/) a file lives in.
_EMBODIED_TEST_MODULES = frozenset(
    {
        "test_engine_embodied_wiring.py",
        "test_embodied_threat_matrix.py",
    }
)


@pytest.fixture(autouse=True)
def _embodied_wiring_tests_run_as_if_containerised(request, monkeypatch):
    """Set ``SQUID_GAME_IN_CONTAINER=1`` only inside the two named modules.

    A no-op for every other test module, including
    ``tests/unit/test_sandbox_host_guard.py`` and
    ``tests/integration/test_host_sandbox_guard_wiring.py`` -- both of
    those exercise ``assert_containerised()``'s real behaviour and must
    see this session's genuine (non-container) environment.
    """
    if Path(str(request.node.fspath)).name in _EMBODIED_TEST_MODULES:
        monkeypatch.setenv("SQUID_GAME_IN_CONTAINER", "1")
    yield

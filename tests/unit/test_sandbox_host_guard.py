"""Unit tests for the container guard on the embodied threat layer.

R22 of the plan amendments: the brief's original guard test
(``assert assert_containerised(allow_host=True) is None``) is vacuous --
it only proves a function that always returns ``None`` returned
``None``. These tests instead stub the container-detection input
(``_in_container``) and assert on the guard's real decision: it raises
``HostSandboxRefused`` outside a container unless explicitly overridden,
and never raises inside one.
"""

from __future__ import annotations

import pytest

from squid_game.core.sandbox import HostSandboxRefused, assert_containerised


def test_running_outside_a_container_is_refused(monkeypatch):
    monkeypatch.setattr(
        "squid_game.core.sandbox._in_container", lambda: False
    )

    with pytest.raises(HostSandboxRefused, match="--allow-host-sandbox"):
        assert_containerised(allow_host=False)


def test_the_explicit_override_permits_a_host_run(monkeypatch):
    monkeypatch.setattr(
        "squid_game.core.sandbox._in_container", lambda: False
    )

    # No exception -- the explicit override wins even though
    # _in_container() (stubbed above) reports "not a container".
    assert assert_containerised(allow_host=True) is None


def test_inside_a_container_no_flag_is_needed(monkeypatch):
    monkeypatch.setattr(
        "squid_game.core.sandbox._in_container", lambda: True
    )

    # No exception -- real container detection (stubbed above) is
    # sufficient on its own, without --allow-host-sandbox.
    assert assert_containerised(allow_host=False) is None

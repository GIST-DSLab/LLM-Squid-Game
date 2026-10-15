"""Offline helpers shared by the tests: a scripted provider and small configs."""

from __future__ import annotations

import re

from squid5.core.providers import ProviderConfig, Stub

def stub(respond) -> Stub:
    return Stub(ProviderConfig("stub", "stub-model"), respond)

def me(messages) -> str:
    """Which agent a call is addressed to (from its system prompt)."""
    return re.search(r"You are (agent-?\d+)", messages[0]["content"]).group(1)

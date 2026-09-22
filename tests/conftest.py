"""Offline helpers shared by the tests: a scripted provider and small configs."""

from __future__ import annotations

import re

from squid5.core.providers import ProviderConfig, Reply, Stub


def stub(respond) -> Stub:
    return Stub(ProviderConfig("stub", "stub-model"), respond)


def me(messages) -> str:
    """Which agent a call is addressed to (from its system prompt)."""
    return re.search(r"You are (agent\d)", messages[0]["content"]).group(1)


def const(text: str, tokens: int = 5):
    return stub(lambda messages, cap: Reply(text, min(tokens, cap)))

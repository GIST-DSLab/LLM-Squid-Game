"""Characterisation fixtures.

The stub provider is imported from the integration suite rather than
copied: two stubs that drift apart would make the two suites disagree
about what "the same input" means, and the whole point of a
characterisation snapshot is that the input is fixed.
"""

from __future__ import annotations

from tests.integration.conftest import StubProvider, StubProviderCall  # noqa: F401

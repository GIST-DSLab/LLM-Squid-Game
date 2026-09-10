"""Integration tests for the LLM Squid Game benchmark.

Fast, deterministic tests that wire real core/task/engine components
together using stub LLM providers. No network, no real models —
reserved for ``tests/smoke/`` (not part of the default pytest run).
"""

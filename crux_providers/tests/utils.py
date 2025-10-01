"""Shared testing utilities for provider persistence & capability tests.

Purpose:
    Avoid duplication of simple assertion helpers across multiple test modules
    while retaining explicit AssertionError semantics (eschewing bare `assert`
    to satisfy Bandit B101). Centralizing this logic keeps individual test
    files focused on domain scenarios rather than helper boilerplate.

Exports:
    - assert_true(condition: bool, message: str) -> None

Design Notes:
    The helper intentionally mirrors a subset of `pytest` style assertions but
    keeps behavior explicit and minimal. We don't import pytest here to avoid
    coupling production-adjacent helper code to the framework in case a future
    runner abstraction is introduced.
"""
from __future__ import annotations


def assert_true(condition: bool, message: str) -> None:
    """Raise AssertionError with the provided message if condition is False.

    Parameters
    ----------
    condition: bool
        Boolean expression under test.
    message: str
        Rich, contextual diagnostic message to display on failure.

    Raises
    ------
    AssertionError
        If `condition` evaluates false.
    """
    if not condition:
        raise AssertionError(message)

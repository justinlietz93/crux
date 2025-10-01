"""Fixtures for streaming contract tests.

Provides controlled time mocking, cancellation token setup, and logging capture.
"""
from __future__ import annotations
import logging
import time
from typing import List
import pytest

# Simple mutable clock fixture
def pytest_addoption(parser):  # pragma: no cover - hook
    pass

@pytest.fixture()
def fake_clock(monkeypatch):
    """Provide a deterministic perf_counter sequence.

    Usage: fake_clock.advance(ms) to move time forward.
    """
    state = {"t": 0.0}
    def perf_counter():
        return state["t"]
    def advance(ms: float):
        state["t"] += ms / 1000.0
    monkeypatch.setattr(time, "perf_counter", perf_counter)
    return type("Clock", (), {"advance": staticmethod(advance)})

@pytest.fixture()
def log_capture():
    records: List[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record)  # type: ignore
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield records
    finally:
        root.removeHandler(handler)

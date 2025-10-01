"""Tests for CLI utilities: console log suppression.

These tests validate that ``suppress_console_logs`` prevents log records from
appearing on console-attached ``StreamHandler`` instances during streaming, and
that it disables propagation so child loggers under ``providers.*`` do not
bubble to the root logger while the context is active.
"""

from __future__ import annotations

import io
import logging
from typing import Iterator

import pytest

from crux_providers.service.cli.cli_utils import suppress_console_logs


def _reset_stream(s: io.StringIO) -> None:
    """Helper to clear a ``StringIO`` buffer in-place."""
    s.truncate(0)
    s.seek(0)


@pytest.fixture
def restore_logging_state() -> Iterator[None]:
    """Ensure logging handlers/levels are restored after each test.

    Captures original handlers for the ``providers`` logger and the root logger
    and restores them after the test completes to avoid cross-test interference.
    """
    providers_logger = logging.getLogger("providers")
    root_logger = logging.getLogger()
    providers_handlers = list(providers_logger.handlers)
    root_handlers = list(root_logger.handlers)
    providers_level = providers_logger.level
    root_level = root_logger.level
    providers_prop = providers_logger.propagate
    try:
        yield
    finally:
        providers_logger.handlers = providers_handlers
        providers_logger.setLevel(providers_level)
        providers_logger.propagate = providers_prop
        root_logger.handlers = root_handlers
        root_logger.setLevel(root_level)


def test_suppress_console_silences_stream_handlers(restore_logging_state: None) -> None:
    """Console StreamHandlers attached to ``providers`` are silenced in-context.

    Arrange: attach a ``StreamHandler`` to the ``providers`` logger that writes
    into a memory buffer. Act: emit logs inside/outside the suppression context.
    Assert: inside the context, nothing reaches the handler; afterward, logging
    works again (levels restored).
    """
    logger = logging.getLogger("providers")
    logger.setLevel(logging.DEBUG)

    sink = io.StringIO()
    h = logging.StreamHandler(stream=sink)
    h.setLevel(logging.DEBUG)
    logger.addHandler(h)

    # Baseline: outside the context, INFO should be written
    _reset_stream(sink)
    logger.info("outside-context")
    assert "outside-context" in sink.getvalue()  # nosec B101 - pytest assertion in test

    # Inside the context, handler should be raised above CRITICAL
    _reset_stream(sink)
    with suppress_console_logs():
        logger.info("inside-context")
    assert sink.getvalue() == ""  # nosec B101 - pytest assertion in test

    # After exit, previous level restored and messages flow again
    _reset_stream(sink)
    logger.info("after-context")
    assert "after-context" in sink.getvalue()  # nosec B101 - pytest assertion in test


def test_suppress_console_disables_propagation_for_children(restore_logging_state: None) -> None:
    """Child ``providers.*`` logs don't bubble to root while suppressed.

    Arrange: attach a console handler to the root logger and emit via a child
    ``providers.openrouter`` logger that has no handlers (so it would normally
    propagate). Act: within the suppression context, emit an INFO record.
    Assert: the root handler sees nothing while suppressed, then sees messages
    again after the context exits (propagation restored).
    """
    # Root console sink
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root_sink = io.StringIO()
    root_handler = logging.StreamHandler(stream=root_sink)
    root_handler.setLevel(logging.DEBUG)
    root.addHandler(root_handler)

    # Child logger without handlers so it would normally propagate
    child = logging.getLogger("providers.openrouter")
    child.setLevel(logging.DEBUG)
    child.handlers = []
    child.propagate = True

    # Baseline: outside context, message should reach root
    _reset_stream(root_sink)
    child.info("baseline-propagates")
    assert "baseline-propagates" in root_sink.getvalue()  # nosec B101 - pytest assertion in test

    # Inside suppression, propagation is disabled for providers.*
    _reset_stream(root_sink)
    with suppress_console_logs():
        child.info("muted-during-context")
    assert root_sink.getvalue() == ""  # nosec B101 - pytest assertion in test

    # After exit, propagation restored and messages reach root again
    _reset_stream(root_sink)
    child.info("restored-after-context")
    assert "restored-after-context" in root_sink.getvalue()  # nosec B101 - pytest assertion in test

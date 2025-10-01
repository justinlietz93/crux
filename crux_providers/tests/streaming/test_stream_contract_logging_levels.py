"""Verify DEBUG-only mid-stream log emission in BaseStreamingAdapter.

This test ensures that per-delta normalized log events are emitted only when
the logger level is DEBUG and are suppressed at INFO and higher levels.
"""
from __future__ import annotations

import json
import logging
from typing import Iterable, Optional

from crux_providers.base.logging import LogContext, get_logger
from crux_providers.base.streaming import BaseStreamingAdapter
from crux_providers.base.resilience.retry import RetryConfig


def _retry_cfg(_: str) -> RetryConfig:
    """Return a deterministic retry config for tests.

    The adapter only uses this for the start phase; we don't retry in tests.
    """
    return RetryConfig(max_attempts=1, delay_base=0.0)


def _collect_json(records):
    payloads = []
    for r in records:
        try:
            payloads.append(json.loads(r.getMessage()))
        except Exception:
            # Ignore non-JSON messages
            continue
    return payloads


def _starter_three_chunks() -> Iterable[str]:
    return ["x", "y", "z"]


def _translator_identity(chunk: str) -> Optional[str]:
    return chunk


def _run_adapter_and_collect(logger: logging.Logger, records):
    """Run a three-chunk adapter with the provided logger and return JSON payloads.

    Parameters
    ----------
    logger: logging.Logger
        Configured logger to use for the adapter run.
    records: list
        The shared log records list populated by the root handler from conftest.
    """
    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="unit", model=logger.name),
        provider_name="unit",
        model=logger.name,
        starter=_starter_three_chunks,
        translator=_translator_identity,
        retry_config_factory=_retry_cfg,
        logger=logger,
    )
    list(adapter.run())
    return _collect_json(records)


def test_mid_stream_logs_present_at_debug(log_capture):
    """When level is DEBUG, per-delta mid_stream logs are emitted."""
    debug_logger = get_logger("providers.test.levels.debug", json_mode=True)
    debug_logger.setLevel(logging.DEBUG)
    for h in debug_logger.handlers:
        h.setLevel(logging.DEBUG)

    payloads = _run_adapter_and_collect(debug_logger, log_capture)
    mid = [p for p in payloads if p.get("phase") == "mid_stream" and p.get("event") == "stream.delta"]
    fin = [p for p in payloads if p.get("phase") == "finalize"]
    if not mid:
        raise AssertionError("expected mid_stream delta logs at DEBUG level")
    if not fin:
        raise AssertionError("expected finalize log present for DEBUG run")


def test_mid_stream_logs_suppressed_at_info(log_capture):
    """When level is INFO, per-delta mid_stream logs are not emitted."""
    # Clear capture from previous tests if any
    del log_capture[:]

    info_logger = get_logger("providers.test.levels.info", json_mode=True)
    info_logger.setLevel(logging.INFO)
    for h in info_logger.handlers:
        h.setLevel(logging.INFO)

    payloads = _run_adapter_and_collect(info_logger, log_capture)
    mid = [p for p in payloads if p.get("phase") == "mid_stream" and p.get("event") == "stream.delta"]
    fin = [p for p in payloads if p.get("phase") == "finalize"]
    if mid:
        raise AssertionError("did not expect mid_stream delta logs at INFO level")
    if not fin:
        raise AssertionError("expected finalize log present for INFO run")

"""Unified timeout & cancellation utilities for providers.

This module centralizes timeout values used across provider adapters and
infrastructure (HTTP calls, streaming start phases, local CLI invocations)
and exposes a context manager for best-effort wall clock enforcement of
start-phase operations. It merges prior split implementations into a single
authoritative source to satisfy internal policy: *Always use
`get_timeout_config()` + `operation_timeout` for blocking start phases.*

Key Components
--------------
TimeoutConfig
    Dataclass capturing normalized timeout values. Fields are intentionally
    explicit and stable; future additions (e.g., cancel grace period) will not
    alter existing semantics.

get_timeout_config()
    Returns a process-cached configuration, parsing environment overrides on
    first use only. Supported environment variables (all optional):
        PT_TIMEOUT_START_SECONDS
        PROVIDERS_START_TIMEOUT_SECONDS (compat alias)
        PT_TIMEOUT_STREAM_SECONDS
        PT_TIMEOUT_HTTP_SECONDS
        PT_TIMEOUT_OVERALL_SECONDS
        PROVIDER_STREAM_START_TIMEOUT (legacy compatibility alias for START)

operation_timeout(seconds)
    Context manager providing a defensive timeout guard using SIGALRM where
    available (Unix main thread) and a threading.Timer fallback otherwise.
    It is deliberately lightweight and nests safely, restoring any preexisting
    alarm configuration.

Design Constraints
------------------
1. No hard-coded ad-hoc timeouts outside this module.
2. Avoid per-call env parsing (cache after first read).
3. Side-effect free access (apart from first load) for deterministic tests.
4. Graceful degradation: if signals unsupported, still enforce via fallback.

Failure Modes
-------------
TimeoutError raised within the guarded context if the deadline elapses.
The fallback timer mode triggers the exception only after the context body
finishes a bytecode step (cooperative).
"""
from __future__ import annotations

from contextlib import contextmanager, suppress
from dataclasses import dataclass
import os
import signal
import threading
import time
from typing import Iterator, Optional, Tuple


@dataclass(frozen=True)
class TimeoutConfig:
    """Container for normalized timeout values (seconds).

    Attributes:
        start_timeout_seconds: Timeout for establishing the initial remote
            streaming session / handshake.
        stream_timeout_seconds: Idle timeout while waiting for the next token
            or delta during streaming.
        http_timeout_seconds: Baseline HTTP request timeout (individual SDK /
            REST calls that are not streaming).
        overall_timeout_seconds: Optional absolute cap for an end-to-end
            request (currently informative / future use).
    """

    start_timeout_seconds: float = 30.0
    stream_timeout_seconds: float = 60.0
    http_timeout_seconds: float = 30.0
    overall_timeout_seconds: float | None = None


_CACHED: TimeoutConfig | None = None
# Track the last seen start-timeout env overrides to allow tests to adjust at runtime
_ENV_GUARD_START: str | None = None


def _parse_env_float(name: str, default: float | None) -> float | None:
    """Parse an environment variable as a float with a fallback default.

    Attempts to read the environment variable `name` and convert it to a float. Returns the default if the variable is unset, not a valid float, or not positive.

    Args:
        name: The name of the environment variable to read.
        default: The fallback value to use if parsing fails.

    Returns:
        The parsed float value from the environment variable, or the provided default.
    """
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        val = float(raw)
        return val if val > 0 else default
    except ValueError:  # pragma: no cover - defensive
        return default


def get_timeout_config() -> TimeoutConfig:
    """Return process-cached `TimeoutConfig` instance.

    Environment precedence for start timeout:
        1. PT_TIMEOUT_START_SECONDS
        2. PROVIDER_STREAM_START_TIMEOUT (legacy)
    Other fields use their PT_* variable if present.
    """
    global _CACHED, _ENV_GUARD_START  # noqa: PLW0603 - intentional, documented module cache
    # If env overrides changed since last computation, refresh the cache.
    cur_guard = "/".join(
        [
            os.getenv("PT_TIMEOUT_START_SECONDS", ""),
            os.getenv("PROVIDERS_START_TIMEOUT_SECONDS", ""),
            os.getenv("PROVIDER_STREAM_START_TIMEOUT", ""),
        ]
    )
    if _CACHED is not None and _ENV_GUARD_START == cur_guard:
        return _CACHED

    # Start timeout precedence: PT_* > PROVIDERS_* > legacy PROVIDER_*
    start = _parse_env_float(
        "PT_TIMEOUT_START_SECONDS",
        _parse_env_float(
            "PROVIDERS_START_TIMEOUT_SECONDS",
            _parse_env_float("PROVIDER_STREAM_START_TIMEOUT", 30.0),
        ),
    )
    stream = _parse_env_float("PT_TIMEOUT_STREAM_SECONDS", 60.0)
    http = _parse_env_float("PT_TIMEOUT_HTTP_SECONDS", 30.0)
    overall = _parse_env_float("PT_TIMEOUT_OVERALL_SECONDS", None)

    _CACHED = TimeoutConfig(
        start_timeout_seconds=float(start),
        stream_timeout_seconds=float(stream),
        http_timeout_seconds=float(http),
        overall_timeout_seconds=float(overall) if overall is not None else None,
    )
    _ENV_GUARD_START = cur_guard
    return _CACHED


def _setup_signal_timeout(seconds: float):
    """Attempt to install a SIGALRM-based timeout.

    Returns tuple (use_signal, old_handler, old_itimer, start_monotonic).
    Falls back (False, None, None, None) if unsupported or setup fails.
    """
    if not (
        hasattr(signal, "setitimer")
        and threading.current_thread() is threading.main_thread()
    ):
        return False, None, None, None

    def _raise_timeout(signum=None, frame=None):  # noqa: D401, ARG001
        """Raise a TimeoutError when a timeout signal is received.

        This function is intended to be used as a signal handler for operation timeouts.
        """
        raise TimeoutError(f"operation exceeded {seconds}s")

    try:  # pragma: no cover - platform specific
        old_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _raise_timeout)  # type: ignore[arg-type]
        old_itimer = signal.setitimer(signal.ITIMER_REAL, seconds)  # type: ignore[arg-type]
        return True, old_handler, old_itimer, time.monotonic()
    except Exception:  # pragma: no cover - defensive
        return False, None, None, None


def _restore_signal_timeout(
    old_handler, old_itimer: Optional[Tuple[float, float]], start_monotonic: Optional[float]
):
    """Restore any prior alarm + handler safely (supports nesting)."""
    with suppress(Exception):  # pragma: no cover - defensive
        signal.setitimer(signal.ITIMER_REAL, 0)
        if old_handler is not None:
            signal.signal(signal.SIGALRM, old_handler)  # type: ignore[arg-type]
        if old_itimer and old_itimer[0] > 0:
            remaining = old_itimer[0]
            if start_monotonic is not None:
                elapsed = time.monotonic() - start_monotonic
                remaining = max(0.0, remaining - elapsed)
            if remaining > 0:
                signal.setitimer(signal.ITIMER_REAL, remaining, old_itimer[1])  # type: ignore[arg-type]


@contextmanager
def operation_timeout(seconds: float) -> Iterator[None]:
    """Context manager enforcing a wall-clock timeout.

    If `seconds` <= 0 the guard is inert. Uses SIGALRM where possible for
    accurate timing; otherwise a cooperative threading.Timer fallback which
    raises on exit if expired.
    """
    if seconds <= 0:
        yield
        return

    use_signal, old_handler, old_itimer, start_monotonic = _setup_signal_timeout(seconds)
    expired = False
    timer = None

    if not use_signal:
        def _expire():  # pragma: no cover - timing sensitive
            nonlocal expired
            expired = True

        timer = threading.Timer(seconds, _expire)
        timer.daemon = True
        timer.start()

    try:
        yield
        if not use_signal and expired:
            raise TimeoutError(f"operation exceeded {seconds}s (fallback)")
    finally:
        if use_signal:
            _restore_signal_timeout(old_handler, old_itimer, start_monotonic)
        elif timer is not None:  # pragma: no cover - defensive
            timer.cancel()


__all__ = [
    "TimeoutConfig",
    "get_timeout_config",
    "operation_timeout",
]

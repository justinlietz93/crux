"""Thread-safe in-memory counters for provider invocations.

This class aggregates lifecycle metrics distinct from streaming token metrics.
Separated into its own file to comply with one-class-per-file governance.
"""

from __future__ import annotations

from threading import RLock
from typing import Dict, Optional, Any
import time

from .latency_stats_snapshot import LatencyStatsSnapshot
from .provider_counters_snapshot import ProviderCountersSnapshot


class ProviderInvocationCounters:
    """Thread-safe in-memory counters for provider invocations.

    See module docstrings in the parent re-export for detailed usage guidance.
    """

    __slots__ = (
        "_provider",
        "_lock",
        "_total",
        "_success",
        "_failure",
        "_retry",
        "_cancelled",
        "_timeout",
        "_in_flight",
        "_failure_by_code",
        # latency aggregates
        "_latency_count",
        "_latency_total",
        "_latency_min",
        "_latency_max",
    )

    def __init__(self, provider: str):
        """Initialize counters for a specific provider.

        Args:
            provider: Name of the provider being tracked.
        """
        self._provider = provider
        self._lock = RLock()
        self._total = 0
        self._success = 0
        self._failure = 0
        self._retry = 0
        self._cancelled = 0
        self._timeout = 0
        self._in_flight = 0
        self._failure_by_code: Dict[str, int] = {}
        self._latency_count = 0
        self._latency_total = 0
        self._latency_min: Optional[int] = None
        self._latency_max: Optional[int] = None

    # -------------------------- Static Helpers -------------------------- #
    @staticmethod
    def monotonic_ms() -> int:
        """Return current monotonic time in milliseconds for latency measurement."""
        return int(time.monotonic() * 1000)

    # -------------------------- Record Methods -------------------------- #
    def record_start(self) -> None:
        """Record the start of a provider invocation."""
        with self._lock:
            self._total += 1
            self._in_flight += 1

    def record_success(self, latency_ms: int) -> None:
        """Record a successful completion.

        Args:
            latency_ms: Wall-clock latency in milliseconds from start to success.
        """
        with self._lock:
            self._success += 1
            self._in_flight = max(0, self._in_flight - 1)
            self._update_latency(latency_ms)

    def record_failure(self, error_code: str, latency_ms: Optional[int] = None) -> None:
        """Record a failed invocation.

        Args:
            error_code: Canonical error code string.
            latency_ms: Optional latency to include in aggregate stats when provided.
        """
        with self._lock:
            self._failure += 1
            self._failure_by_code[error_code] = self._failure_by_code.get(error_code, 0) + 1
            self._in_flight = max(0, self._in_flight - 1)
            if latency_ms is not None:
                self._update_latency(latency_ms)

    def record_retry(self) -> None:
        """Record that a retry will be attempted for an invocation."""
        with self._lock:
            self._retry += 1

    def record_cancelled(self) -> None:
        """Record a cooperative cancellation outcome."""
        with self._lock:
            self._cancelled += 1
            self._in_flight = max(0, self._in_flight - 1)

    def record_timeout(self) -> None:
        """Record an invocation timeout outcome (start-phase or mid-operation)."""
        with self._lock:
            self._timeout += 1
            self._in_flight = max(0, self._in_flight - 1)

    # -------------------------- Latency Helpers -------------------------- #
    def _update_latency(self, latency_ms: int) -> None:
        """Update latency aggregates with a new observed latency value.

        Ignores negative values and updates min, max, count, and total.
        """
        if latency_ms < 0:
            return  # ignore invalid
        if self._latency_min is None or latency_ms < self._latency_min:
            self._latency_min = latency_ms
        if self._latency_max is None or latency_ms > self._latency_max:
            self._latency_max = latency_ms
        self._latency_count += 1
        self._latency_total += latency_ms

    # -------------------------- Snapshot API -------------------------- #
    def snapshot(self, reset: bool = False) -> ProviderCountersSnapshot:
        """Return an immutable snapshot of current counters.

        Args:
            reset: If True, zero counters & latency aggregates after creating snapshot
                (except in_flight which is preserved as active invocations).
        """
        with self._lock:
            avg_ms: Optional[float]
            if self._latency_count:
                avg_ms = self._latency_total / self._latency_count
            else:
                avg_ms = None
            latency_snapshot = LatencyStatsSnapshot(
                count=self._latency_count,
                total_ms=self._latency_total,
                min_ms=self._latency_min,
                max_ms=self._latency_max,
                avg_ms=avg_ms,
            )
            snapshot = ProviderCountersSnapshot(
                provider=self._provider,
                total=self._total,
                success=self._success,
                failure=self._failure,
                retry=self._retry,
                cancelled=self._cancelled,
                timeout=self._timeout,
                in_flight=self._in_flight,
                failure_by_code=dict(self._failure_by_code),
                latency=latency_snapshot,
                generated_at_ms=self.monotonic_ms(),
            )
            if reset:
                self._total = 0
                self._success = 0
                self._failure = 0
                self._retry = 0
                self._cancelled = 0
                self._timeout = 0
                self._failure_by_code.clear()
                self._latency_count = 0
                self._latency_total = 0
                self._latency_min = None
                self._latency_max = None
            return snapshot

    # -------------------------- Introspection -------------------------- #
    def as_dict(self, reset: bool = False) -> Dict[str, Any]:
        """Convenience wrapper returning snapshot converted to dictionary."""
        return self.snapshot(reset=reset).to_dict()


__all__ = ["ProviderInvocationCounters"]

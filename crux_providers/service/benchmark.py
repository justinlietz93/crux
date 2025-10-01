"""Benchmark harness for provider round-trip latency.

Purpose
-------
Provide a small, framework-independent utility to measure request latency
for provider chat calls. Supports warmup iterations and returns summary
statistics suitable for regression checks or local comparisons.

External Dependencies
---------------------
- Relies on provider adapters available in this package for real execution.
- Does not require external libraries; tests can inject a synthetic
  ``measure_fn`` to avoid network calls.

Timeout Strategy
----------------
For real runs, each measured request is wrapped in ``operation_timeout`` using
``get_timeout_config()``. No hard-coded timeouts are used.

Failure Modes & Semantics
-------------------------
- Input validation errors (e.g., negative ``runs``) raise ``ValueError``.
- Real execution errors bubble up after being captured by the caller (e.g., CLI)
  for standardized logging; this module itself does not suppress provider errors.

"""

from __future__ import annotations

import statistics
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..base.logging import LogContext, get_logger, normalized_log_event
from ..base.models import ChatRequest, Message
from ..base.timeouts import get_timeout_config, operation_timeout
from .helpers import set_env_for_provider
from ..base.interfaces import HasDefaultModel, SupportsStreaming
from ..base.interfaces_parts import HasText


Percentile = float


def _percentile(sorted_values: List[float], p: float) -> Percentile:
    """Return the p-th percentile from a pre-sorted list.

    Parameters
    ----------
    sorted_values: List[float]
        Values sorted ascending.
    p: float
        Percentile in [0, 100].

    Returns
    -------
    float
        The percentile value using nearest-rank interpolation.
    """
    if not sorted_values:
        return 0.0
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    # Nearest-rank index (1-based), then convert to 0-based
    k = max(1, int(round(p / 100.0 * len(sorted_values))))
    idx = min(len(sorted_values) - 1, k - 1)
    return sorted_values[idx]


def compute_stats(durations: Iterable[float]) -> Dict[str, float]:
    """Compute latency summary statistics for a sequence of durations (seconds).

    Parameters
    ----------
    durations: Iterable[float]
        Sequence of measured durations in seconds.

    Returns
    -------
    Dict[str, float]
        Stats including min, max, mean, median, p50, p90, p95, p99, and count.
    """
    values = list(durations)
    if not values:
        return {
            "count": 0.0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "total": 0.0,
        }
    values.sort()
    total = float(sum(values))
    return {
        "count": float(len(values)),
        "min": float(values[0]),
        "max": float(values[-1]),
        "mean": float(total / len(values)),
        "median": float(statistics.median(values)),
        "p50": float(_percentile(values, 50)),
        "p90": float(_percentile(values, 90)),
        "p95": float(_percentile(values, 95)),
        "p99": float(_percentile(values, 99)),
        "total": total,
    }


def _build_adapter_call(
    provider: str,
    model: Optional[str],
    prompt: str,
    stream: bool,
    *,
    capture_output: bool = False,
    output_sink: Optional[List[str]] = None,
) -> Callable[[], None]:
    """Construct a zero-arg callable that performs a single provider request.

    This helper builds an adapter invocation closure. When ``capture_output`` is
    True, it will store the textual response from the last invocation into
    ``output_sink`` (index 0), concatenating deltas for streaming modes. When
    False, responses are not accumulated to minimize overhead during latency
    measurements.

    Args:
        provider: Canonical provider name (e.g., ``openrouter``).
        model: Optional model override; defaults to adapter preference.
        prompt: The user prompt to send to the provider.
        stream: Whether to use streaming if supported by the adapter.
        capture_output: If True, collect the response text for inspection.
        output_sink: Optional single-element list used as an out-parameter to
            store the latest response text when ``capture_output`` is True.

    Returns:
        A zero-argument function that performs one provider request when called.
    """
    # Late import to keep module side-effects minimal and avoid circular deps
    from .cli import _resolve_provider_class  # local import

    set_env_for_provider(provider)
    adapter_cls = _resolve_provider_class(provider)
    if adapter_cls is None:
        raise ValueError(f"unknown provider '{provider}'")
    adapter = adapter_cls()
    # Prefer typed Protocol checks over getattr/hasattr for capability detection
    preferred_model = adapter.default_model() if isinstance(adapter, HasDefaultModel) else None
    mdl = model or preferred_model or "auto"

    req = ChatRequest(model=mdl, messages=[Message(role="user", content=prompt)])

    def _do_call() -> None:
        """Perform one provider request, optionally capturing response text.

        Executes either a streaming or non-streaming provider call. When
        ``capture_output`` is enabled, the textual output of this call is
        written into ``output_sink`` (index 0), allowing callers to attach a
        sample output without affecting timing measurements.
        """
        # Use Protocol-based streaming support gating
        if stream and isinstance(adapter, SupportsStreaming) and adapter.supports_streaming():
            # Drain stream; optionally collect text for the last invocation
            parts: List[str] = [] if capture_output else []  # keep separate var for clarity
            for ev in adapter.stream_chat(req):
                if capture_output and ev.delta:
                    parts.append(ev.delta)
            if capture_output and output_sink is not None:
                text = "".join(parts)
                if output_sink:
                    output_sink[0] = text
                else:
                    output_sink.append(text)
        else:
            resp = adapter.chat(req)
            if capture_output and output_sink is not None:
                text = (resp.text if isinstance(resp, HasText) else "")
                if output_sink:
                    output_sink[0] = text
                else:
                    output_sink.append(text)

    return _do_call


def _validate_benchmark_args(runs: int, warmups: int) -> None:
    """Validate benchmark argument ranges.

    Parameters
    ----------
    runs: int
        Number of measured runs; must be non-negative.
    warmups: int
        Number of warmup iterations; must be non-negative.

    Raises
    ------
    ValueError
        If either value is negative.
    """
    if runs < 0 or warmups < 0:
        raise ValueError("runs and warmups must be non-negative")


def _build_measure_fn_and_call_fn(
    *,
    provider: str,
    model: Optional[str],
    prompt: str,
    stream: bool,
    capture_output: bool,
    output_sink: Optional[List[str]],
    measure_fn: Optional[Callable[[], float]],
    call_fn: Optional[Callable[[], None]],
) -> Tuple[Callable[[], float], Callable[[], None]]:
    """Return a ``measure_fn`` and ``call_fn`` pair for the benchmark loop.

    If a custom ``measure_fn`` is provided, it is returned as-is and the
    ``call_fn`` will be a no-op. Otherwise, a call function is created (or the
    provided one is used), and a measuring wrapper is constructed using the
    configured timeout strategy to time each invocation in seconds.

    Returns
    -------
    Tuple[Callable[[], float], Callable[[], None]]
        The measurement function and the call function used during runs.
    """
    if measure_fn is not None:
        def _noop() -> None:
            return None
        return measure_fn, _noop

    if call_fn is None:
        call_fn = _build_adapter_call(
            provider,
            model,
            prompt,
            stream,
            capture_output=capture_output,
            output_sink=(output_sink if capture_output else None),
        )

    def _measure() -> float:
        cfg = get_timeout_config()
        t0 = time.perf_counter()
        with operation_timeout(cfg.start_timeout_seconds):
            call_fn()  # type: ignore[misc]
        t1 = time.perf_counter()
        return t1 - t0

    return _measure, call_fn


def _build_result(
    durations: List[float], *, capture_output: bool, output_sink: Optional[List[str]]
) -> Dict[str, Any]:
    """Assemble the final benchmark result dictionary.

    Parameters
    ----------
    durations: List[float]
        The list of measured durations in seconds.
    capture_output: bool
        Whether a sample output should be included.
    output_sink: Optional[List[str]]
        If present and non-empty, the first element will be used as
        ``sample_output`` in the result.
    """
    result: Dict[str, Any] = {
        "warmup": compute_stats([]),  # keep structure stable as before
        "measured": compute_stats(durations),
    }
    if capture_output:
        result["sample_output"] = (output_sink[0] if output_sink else "")
    return result


def run_benchmark(
    provider: str,
    model: Optional[str],
    prompt: str,
    runs: int = 10,
    warmups: int = 2,
    stream: bool = False,
    measure_fn: Optional[Callable[[], float]] = None,
    call_fn: Optional[Callable[[], None]] = None,
    capture_output: bool = False,
) -> Dict[str, Any]:
    """Run a latency benchmark and return warmup and measured stats.

    Parameters
    ----------
    provider: str
        Provider name (e.g., ``openrouter``) for real executions.
    model: Optional[str]
        Model override; defaults to adapter's preferred model when omitted.
    prompt: str
        User prompt to send.
    runs: int
        Number of measured runs (non-negative).
    warmups: int
        Number of warmup iterations (non-negative, excluded from stats).
    stream: bool
        Whether to use streaming where supported.
    measure_fn: Optional[Callable[[], float]]
        Optional synthetic measurement function that returns a duration in seconds
        per iteration. Useful for unit tests.
    call_fn: Optional[Callable[[], None]]
        Optional callable to perform the real provider request per iteration.
        If omitted and ``measure_fn`` is not provided, a call is constructed
        based on provider/model/prompt.

    Returns
    -------
    Dict[str, Dict[str, float]]
        JSON-like dict with keys ``warmup`` and ``measured`` mapping to stats.
        When ``capture_output`` is True, a top-level key ``sample_output`` is
        also included containing the last run's response text (may be empty).

    Raises
    ------
    ValueError
        If ``runs`` or ``warmups`` are negative.
    """
    _validate_benchmark_args(runs, warmups)

    logger = get_logger("providers.benchmark")
    ctx = LogContext(provider=provider, model=(model or "auto"))
    normalized_log_event(logger, "benchmark.start", ctx, phase="start", attempt=1)

    output_sink: List[str] = []
    _measure, _call = _build_measure_fn_and_call_fn(
        provider=provider,
        model=model,
        prompt=prompt,
        stream=stream,
        capture_output=capture_output,
        output_sink=(output_sink if capture_output else None),
        measure_fn=measure_fn,
        call_fn=call_fn,
    )

    # Warmups (not included in stats)
    for _ in range(warmups):
        _ = _measure()

    # Measured runs
    durations: List[float] = [_measure() for _ in range(runs)]
    result = _build_result(durations, capture_output=capture_output, output_sink=(output_sink if capture_output else None))

    normalized_log_event(
        logger,
        "benchmark.finalize",
        ctx,
        phase="finalize",
        attempt=None,
        emitted=True,
        tokens=None,
        metrics={"count": len(durations), "mean_s": result["measured"]["mean"]},
    )
    return result

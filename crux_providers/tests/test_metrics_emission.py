from __future__ import annotations

import json
from typing import List

from crux_providers.base.logging import LogContext, get_logger
from crux_providers.base.streaming.streaming_finalize import finalize_stream
from crux_providers.base.streaming.streaming_metrics import StreamMetrics, apply_token_usage
from crux_providers.base.metrics.exporter import StreamMetricsPayload, MetricsExporter


class _CaptureExporter(MetricsExporter):
    """Test exporter capturing last payload for assertions."""

    def __init__(self) -> None:
        self.payloads: List[StreamMetricsPayload] = []

    def emit_stream_metrics(self, payload: StreamMetricsPayload) -> None:
        self.payloads.append(payload)


def test_finalize_emits_metrics_when_flag_set(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PROVIDERS_METRICS_EXPORT", "1")
    capture = _CaptureExporter()

    def _make_capture() -> MetricsExporter:
        """Return the capture exporter (avoids unnecessary lambda)."""
        return capture
    # Monkeypatch default exporter factory to return our capture exporter
    monkeypatch.setattr(
    "crux_providers.base.metrics.exporter.get_default_exporter",
        _make_capture,
        raising=True,
    )
    logger = get_logger(name="providers.test.metrics", json_mode=True)
    ctx = LogContext(provider="p", model="m", request_id="r1")
    metrics = StreamMetrics(emitted=3, time_to_first_token_ms=10.0, total_duration_ms=25.0)
    apply_token_usage(metrics, prompt=5, completion=7)
    evt = finalize_stream(
        logger=logger,
        ctx=ctx,
        provider="p",
        model="m",
        metrics=metrics,
        error=None,
    )
    assert evt.finish is True  # nosec B101 - asserts are appropriate in tests
    assert len(capture.payloads) == 1  # nosec B101 - asserts are appropriate in tests
    pl = capture.payloads[0]
    assert pl.provider == "p" and pl.model == "m"  # nosec B101
    assert pl.emitted_count == 3  # nosec B101
    assert pl.tokens == {"prompt": 5, "completion": 7, "total": 12}  # nosec B101


def test_finalize_logs_on_export_failure(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PROVIDERS_METRICS_EXPORT", "1")

    class _FailExporter(MetricsExporter):
        def emit_stream_metrics(self, payload: StreamMetricsPayload) -> None:
            raise RuntimeError("emit failed")

    def _build_fail() -> MetricsExporter:
        """Factory that returns an exporter which raises on emit."""
        return _FailExporter()

    monkeypatch.setattr(
    "crux_providers.base.metrics.exporter.get_default_exporter",
        _build_fail,
        raising=True,
    )
    logger = get_logger(name="providers.test.metrics2", json_mode=True)
    ctx = LogContext(provider="p2", model="m2", request_id="r2")
    metrics = StreamMetrics(emitted=0)
    finalize_stream(
        logger=logger,
        ctx=ctx,
        provider="p2",
        model="m2",
        metrics=metrics,
        error="some_error",
    )
    out = capsys.readouterr().err.strip()
    # Look for the metrics.export.error event in logs
    assert out, "expected logging output"  # nosec B101
    # Search last JSON line
    lines = [ln for ln in out.splitlines() if ln.strip()]
    data = json.loads(lines[-1])
    payload = json.loads(data["msg"])  # nested payload
    assert payload["event"] == "metrics.export.error"  # nosec B101
    assert payload["failure_class"] == "RuntimeError"  # nosec B101

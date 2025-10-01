"""Base streaming adapter abstraction (moved into streaming package)."""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional, TYPE_CHECKING
from contextlib import suppress, ExitStack
import time

from .streaming import ChatStreamEvent
from ..logging import LogContext
from ..errors import ProviderError, ErrorCode
from ..resilience.retry import RetryConfig
from ..cancellation import CancellationToken, CancelledError
from .streaming_metrics import StreamMetrics
from ..tracing import start_span
from .streaming_finalize import finalize_stream
from .stream_controller import StreamController
from .streaming_adapter_helpers import (
    attempt_start_with_timeout,
    process_chunk,
    handle_midstream_error,
    handle_cancellation,
    finalize_success,
    start_with_retry,
    terminal_error,
    coerce_stream_start_result,
    register_stream_cleanup,
    set_span_metrics,
)

if TYPE_CHECKING:
    from ..dto.structured_output import StructuredOutputDTO


class BaseStreamingAdapter:
    """Encapsulates provider streaming loop boilerplate."""

    def __init__(
        self,
        *,
        ctx: LogContext,
        provider_name: str,
        model: str,
        starter: Callable[[], Iterable],
        translator: Callable[[object], Optional[str]],
        structured_translator: Optional[Callable[[object], Optional["StructuredOutputDTO"]]] = None,
        retry_config_factory: Callable[[str], RetryConfig],
        logger,
        on_complete: Optional[Callable[[bool], None]] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> None:
        """Initialize the BaseStreamingAdapter with provider and streaming configuration."""
        self.ctx = ctx
        self.provider_name = provider_name
        self.model = model
        self._starter = starter
        self._translator = translator
        self._structured_translator = structured_translator
        self._retry_config_factory = retry_config_factory
        self._logger = logger
        self._on_complete = on_complete
        self._cancellation_token = cancellation_token
        self.metrics = StreamMetrics()

    def run(self) -> Iterator[ChatStreamEvent]:  # pragma: no cover - exercised indirectly
        """Execute the streaming lifecycle."""
        t0 = time.perf_counter()
        with ExitStack() as stack, start_span("providers.stream.run") as span:
            with suppress(Exception):
                span.set_attribute("provider", self.provider_name)
                span.set_attribute("model", self.model)
            ok, stream, terminal_evt = attempt_start_with_timeout(self)
            if not ok:
                if terminal_evt is not None:
                    yield terminal_evt
                return
            if stream is None:
                raise ProviderError(
                    code=ErrorCode.INTERNAL,
                    message="Streaming start returned None despite success flag",
                    provider=self.provider_name,
                    model=self.model,
                )
            register_stream_cleanup(stream, stack)

            first_emitted = False
            try:
                for chunk in stream:
                    if self._cancellation_token is not None:
                        try:
                            self._cancellation_token.raise_if_cancelled()
                        except CancelledError as ce:
                            yield from self._handle_cancellation(ce, t0)
                            return
                    chunk_had_delta = False
                    for evt in process_chunk(self, chunk, t0, first_emitted):
                        chunk_had_delta = True
                        yield evt
                    if chunk_had_delta and not first_emitted:
                        first_emitted = True
                if self._cancellation_token is not None:
                    try:
                        self._cancellation_token.raise_if_cancelled()
                    except CancelledError as ce:
                        yield from handle_cancellation(self, ce, t0)
                        return
            except CancelledError as ce:
                with suppress(Exception):
                    span.set_attribute("cancelled", True)
                    span.record_exception(ce)
                yield from handle_cancellation(self, ce, t0)
                return
            except Exception as e:
                with suppress(Exception):
                    span.record_exception(e)
                yield from handle_midstream_error(self, e, t0)
                set_span_metrics(self, span)
                return
            yield from finalize_success(self, t0)
            set_span_metrics(self, span)

    # Backward-compat delegations retained within package
    def _attempt_start_with_timeout(self):
        return attempt_start_with_timeout(self)

    def _process_chunk(self, chunk, t0: float, first_emitted: bool):
        return process_chunk(self, chunk, t0, first_emitted)

    def _handle_midstream_error(self, exc: Exception, t0: float):
        return handle_midstream_error(self, exc, t0)

    def _handle_cancellation(self, exc: CancelledError, t0: float):
        return handle_cancellation(self, exc, t0)

    def _finalize_success(self, t0: float):
        return finalize_success(self, t0)

    def _start_with_retry(self):
        return start_with_retry(self)

    def _terminal_error(self, error: str):
        return terminal_error(self, error)

    def _coerce_stream_start_result(self, result):
        return coerce_stream_start_result(result)

    @staticmethod
    def _register_stream_cleanup(stream, stack: ExitStack) -> None:
        return register_stream_cleanup(stream, stack)

    def _set_span_metrics(self, span) -> None:
        """Set span metrics for tracing and monitoring.

        This method updates the provided span with relevant streaming metrics.

        Args:
            span: The tracing span to update with metrics.
        """
        return set_span_metrics(self, span)


__all__ = [
    "BaseStreamingAdapter",
    "StreamController",
    "StreamMetrics",
    "finalize_stream",
]

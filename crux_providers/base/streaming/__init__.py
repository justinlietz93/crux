"""Streaming package for provider layer.

Exposes streaming primitives, adapter, metrics, and helpers under a single
namespace to keep the base package organized.
"""

from .streaming import ChatStreamEvent, accumulate_events
from .streaming_metrics import StreamMetrics, apply_token_usage, build_token_usage, validate_token_usage
from .streaming_finalize import finalize_stream
from .stream_controller import StreamController
from .streaming_adapter import BaseStreamingAdapter
from .streaming_support import streaming_supported

__all__ = [
    "ChatStreamEvent",
    "accumulate_events",
    "StreamMetrics",
    "apply_token_usage",
    "build_token_usage",
    "validate_token_usage",
    "finalize_stream",
    "StreamController",
    "BaseStreamingAdapter",
    "streaming_supported",
]
